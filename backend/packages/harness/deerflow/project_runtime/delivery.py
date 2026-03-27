from __future__ import annotations

from dataclasses import replace
from collections.abc import Mapping
from typing import Any

from deerflow.project_runtime.prompts import build_delivery_prompt
from deerflow.project_runtime.registry import get_specialist_config, specialist_uses_acp_by_default, tool_names_for_specialist
from deerflow.project_runtime.types import AgentReport, DeliverySummary, WorkOrder, WorkOrderStatus
from deerflow.tools import get_available_tools


def _normalize_work_order(value: WorkOrder | Mapping[str, Any]) -> WorkOrder:
    return WorkOrder.model_validate(value)


def _normalize_report(value: AgentReport | Mapping[str, Any]) -> AgentReport:
    return AgentReport.model_validate(value)


def _phase_specialists_enabled() -> bool:
    try:
        from deerflow.config import get_app_config

        return bool(getattr(get_app_config().project_runtime, "enable_phase_specialists", False))
    except FileNotFoundError:
        return False


def _deterministic_phase_fallback_allowed() -> bool:
    try:
        from deerflow.config import get_app_config

        return bool(getattr(get_app_config().project_runtime, "allow_deterministic_phase_fallback", True))
    except FileNotFoundError:
        return True


def _default_executor_cls():
    from deerflow.subagents.executor import SubagentExecutor

    return SubagentExecutor


def build_delivery_summary(state: Mapping[str, Any]) -> DeliverySummary:
    work_orders = [_normalize_work_order(item) for item in state.get("work_orders") or []]
    reports = {_normalize_report(item).work_order_id: _normalize_report(item) for item in state.get("agent_reports") or []}
    qa_gate = state.get("qa_gate") or {}

    completed_work: list[dict[str, str]] = []
    artifacts: list[str] = []
    verification: list[str] = []
    follow_ups: list[str] = []

    for work_order in work_orders:
        if work_order.status is not WorkOrderStatus.COMPLETED:
            continue
        report = reports.get(work_order.id)
        completed_work.append(
            {
                "work_order_id": work_order.id,
                "title": work_order.title,
                "summary": report.summary if report is not None else "",
            }
        )
        if report is not None:
            artifacts.extend(report.changes)
            verification.extend(report.verification)
            follow_ups.extend(report.risks)

    verification.extend(str(item) for item in qa_gate.get("findings") or [])
    follow_ups.extend(str(item) for item in qa_gate.get("required_rework") or [])
    artifacts.extend(str(item) for item in state.get("artifacts") or [])

    def _dedupe(items: list[str]) -> list[str]:
        return list(dict.fromkeys(item for item in items if item))

    return DeliverySummary.model_validate(
        {
            "completed_work": completed_work,
            "artifacts": _dedupe(artifacts),
            "verification": _dedupe(verification),
            "follow_ups": _dedupe(follow_ups),
        }
    )


def execute_delivery_phase(
    state: Mapping[str, Any],
    *,
    thread_id: str | None,
    parent_model: str | None = None,
    available_tools: list[Any] | None = None,
    executor_cls=None,
) -> DeliverySummary:
    specialist_config = get_specialist_config("delivery-agent")
    if specialist_config is None:
        raise ValueError("delivery-agent specialist config is not available")

    if available_tools is None:
        available_tools = get_available_tools(subagent_enabled=False)
    if executor_cls is None:
        executor_cls = _default_executor_cls()

    acp_enabled = any(getattr(tool, "name", None) == "invoke_acp_agent" for tool in available_tools)
    filtered_tool_names = tool_names_for_specialist(
        "delivery-agent",
        available_tools,
        acp_enabled=acp_enabled and specialist_uses_acp_by_default("delivery-agent"),
    )
    scoped_config = replace(specialist_config, tools=list(filtered_tool_names))
    executor = executor_cls(
        config=scoped_config,
        tools=available_tools,
        parent_model=parent_model,
        sandbox_state=state.get("sandbox"),
        thread_data=state.get("thread_data"),
        thread_id=thread_id,
    )
    deterministic_summary = build_delivery_summary(state)
    prompt = build_delivery_prompt(
        project_brief=state.get("project_brief") if isinstance(state.get("project_brief"), Mapping) else None,
        work_orders=[_normalize_work_order(item).model_dump(mode="json") for item in state.get("work_orders") or []],
        agent_reports=[_normalize_report(item).model_dump(mode="json") for item in state.get("agent_reports") or []],
        qa_gate=state.get("qa_gate") if isinstance(state.get("qa_gate"), Mapping) else None,
        artifacts=[str(item) for item in state.get("artifacts") or []],
    )
    result = executor.execute(prompt)
    status = str(getattr(result, "status", "") or "").lower()
    if status != "completed":
        raise RuntimeError(getattr(result, "error", None) or f"delivery-agent execution finished with status {status or 'unknown'}")

    from deerflow.project_runtime.planning import _extract_json_payload

    payload = _extract_json_payload(str(getattr(result, "result", "") or ""))
    summary = DeliverySummary.model_validate(payload)
    if not summary.completed_work:
        return deterministic_summary
    return summary


def run_delivery(
    state: Mapping[str, Any],
    *,
    thread_id: str | None = None,
    parent_model: str | None = None,
    available_tools: list[Any] | None = None,
    executor_cls=None,
) -> dict[str, Any]:
    phase_artifacts = dict(state.get("phase_artifacts") or {})
    phase_attempts = dict(state.get("phase_attempts") or {})
    try:
        if not _phase_specialists_enabled():
            raise RuntimeError("phase specialists disabled")
        summary = execute_delivery_phase(
            state,
            thread_id=thread_id,
            parent_model=parent_model,
            available_tools=available_tools,
            executor_cls=executor_cls,
        )
        phase_artifacts["delivery"] = {
            "mode": "specialist",
            "delivery_summary": summary.model_dump(mode="json"),
        }
    except Exception:
        if not _deterministic_phase_fallback_allowed():
            raise
        summary = build_delivery_summary(state)
        phase_artifacts["delivery"] = {
            "mode": "deterministic",
            "delivery_summary": summary.model_dump(mode="json"),
        }

    phase_attempts["delivery"] = int(phase_attempts.get("delivery", 0)) + 1
    return {
        "phase": "delivery",
        "delivery_summary": summary.model_dump(mode="json"),
        "phase_artifacts": phase_artifacts,
        "phase_attempts": phase_attempts,
    }

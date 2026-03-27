from __future__ import annotations

import re
import shlex
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any

from deerflow.project_runtime.registry import get_specialist_config, specialist_uses_acp_by_default, tool_names_for_specialist
from deerflow.project_runtime.types import AgentReport, ProjectBrief, QAGate, QAGateResult, WorkOrder, WorkOrderStatus
from deerflow.tools import get_available_tools

_EXECUTABLE_COMMANDS = {"pytest", "uv", "python", "make", "npm", "pnpm", "yarn", "ruff", "mypy", "bash", "sh"}
_ENV_ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=.*$")


@dataclass(frozen=True)
class AcceptanceCheckResult:
    check: str
    passed: bool
    details: str
    executable: bool


def _normalize_work_order(value: WorkOrder | Mapping[str, Any]) -> WorkOrder:
    return WorkOrder.model_validate(value)


def _normalize_report(value: AgentReport | Mapping[str, Any]) -> AgentReport:
    return AgentReport.model_validate(value)


def _normalize_brief(value: ProjectBrief | Mapping[str, Any] | None) -> ProjectBrief | None:
    if value is None:
        return None
    return ProjectBrief.model_validate(value)


def _default_executor_cls():
    from deerflow.subagents.executor import SubagentExecutor

    return SubagentExecutor


def _is_executable_check(check: str) -> bool:
    stripped = check.strip()
    if not stripped:
        return False
    try:
        tokens = shlex.split(stripped, posix=True)
    except ValueError:
        return False
    if not tokens:
        return False
    index = 0
    while index < len(tokens) and _ENV_ASSIGNMENT_RE.match(tokens[index]):
        index += 1
    if index >= len(tokens):
        return False
    return tokens[index] in _EXECUTABLE_COMMANDS


def _parse_verdict(text: str) -> bool | None:
    for line in text.splitlines():
        if not line.upper().startswith("VERDICT:"):
            continue
        verdict = line.split(":", 1)[1].strip().upper()
        if verdict == "PASS":
            return True
        if verdict == "FAIL":
            return False
    return None


def _build_acceptance_check_task(
    state: Mapping[str, Any],
    work_order: WorkOrder,
    check: str,
    *,
    thread_id: str | None,
) -> str:
    project_brief = _normalize_brief(state.get("project_brief"))
    report = next(
        (
            _normalize_report(item).model_dump(mode="json")
            for item in state.get("agent_reports") or []
            if _normalize_report(item).work_order_id == work_order.id
        ),
        {},
    )
    lines = [
        "You are executing a deterministic QA acceptance check for the project runtime.",
        f"Thread ID: {thread_id or 'unknown'}",
        "ProjectBrief",
        str(project_brief.model_dump(mode='json') if project_brief is not None else {}),
        "WorkOrder",
        str(work_order.model_dump(mode="json")),
        "AgentReport",
        str(report),
        "Run this acceptance check exactly.",
        "Return plain text using this exact format:",
        "VERDICT: PASS or VERDICT: FAIL",
        "EVIDENCE: one concise sentence with the command outcome",
        "Do not omit the VERDICT line.",
        check,
    ]
    return "\n".join(lines)


def run_acceptance_check(
    state: Mapping[str, Any],
    work_order: WorkOrder | Mapping[str, Any],
    check: str,
    *,
    thread_id: str | None,
    parent_model: str | None = None,
    available_tools: list[Any] | None = None,
    executor_cls=None,
) -> AcceptanceCheckResult:
    normalized_work_order = _normalize_work_order(work_order)
    stripped = check.strip()

    if not _is_executable_check(stripped):
        return AcceptanceCheckResult(
            check=stripped,
            passed=True,
            details="Recorded as a non-executable QA finding for manual review.",
            executable=False,
        )

    specialist_config = get_specialist_config("qa-agent")
    if specialist_config is None:
        raise ValueError("qa-agent specialist config is not available")

    if available_tools is None:
        available_tools = get_available_tools(subagent_enabled=False)
    if executor_cls is None:
        executor_cls = _default_executor_cls()

    acp_enabled = any(getattr(tool, "name", None) == "invoke_acp_agent" for tool in available_tools)
    filtered_tool_names = tool_names_for_specialist(
        "qa-agent",
        available_tools,
        acp_enabled=acp_enabled and specialist_uses_acp_by_default("qa-agent"),
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
    result = executor.execute(
        _build_acceptance_check_task(
            state,
            normalized_work_order,
            stripped,
            thread_id=thread_id,
        )
    )
    status = str(getattr(result, "status", "") or "").lower()
    if status != "completed":
        details = str(getattr(result, "error", "") or f"Acceptance check failed with status {status or 'unknown'}")
        return AcceptanceCheckResult(check=stripped, passed=False, details=details, executable=True)

    details = str(getattr(result, "result", "") or "")
    verdict = _parse_verdict(details)
    if verdict is True:
        return AcceptanceCheckResult(
            check=stripped,
            passed=True,
            details=details or "Acceptance check passed",
            executable=True,
        )
    if verdict is False:
        return AcceptanceCheckResult(
            check=stripped,
            passed=False,
            details=details or "Acceptance check failed",
            executable=True,
        )
    return AcceptanceCheckResult(check=stripped, passed=False, details=details, executable=True)


def run_qa_gate(
    state: Mapping[str, Any],
    *,
    thread_id: str | None,
    parent_model: str | None = None,
    available_tools: list[Any] | None = None,
    executor_cls=None,
) -> dict[str, Any]:
    work_orders = [_normalize_work_order(item) for item in state.get("work_orders") or []]
    reports = [_normalize_report(item) for item in state.get("agent_reports") or []]
    report_ids = {report.work_order_id for report in reports}

    if state.get("build_error"):
        payload = QAGate(
            result=QAGateResult.BLOCKED,
            findings=[f"Build is blocked by a prior error: {state['build_error']}"],
            required_rework=[],
        )
        return payload.model_dump(mode="json")

    if state.get("active_work_order_ids"):
        payload = QAGate(
            result=QAGateResult.BLOCKED,
            findings=["Build still has active work orders and cannot enter delivery."],
            required_rework=[],
        )
        return payload.model_dump(mode="json")

    unresolved = [
        work_order.id
        for work_order in work_orders
        if work_order.status not in {WorkOrderStatus.COMPLETED, WorkOrderStatus.CANCELLED}
    ]
    if unresolved:
        payload = QAGate(
            result=QAGateResult.BLOCKED,
            findings=[f"Non-terminal work orders remain: {', '.join(unresolved)}"],
            required_rework=[],
        )
        return payload.model_dump(mode="json")

    findings: list[str] = []
    required_rework: list[str] = []

    for work_order in work_orders:
        if work_order.status is WorkOrderStatus.CANCELLED:
            continue
        if work_order.id not in report_ids:
            findings.append(f"Work order {work_order.id} is completed but has no agent report.")
            required_rework.append(f"Replan or re-run {work_order.id} to produce a canonical agent report.")
            continue

        for check in work_order.acceptance_checks:
            result = run_acceptance_check(
                state,
                work_order,
                check,
                thread_id=thread_id,
                parent_model=parent_model,
                available_tools=available_tools,
                executor_cls=executor_cls,
            )
            if not result.executable:
                findings.append(f"Manual QA review noted for {work_order.id}: {result.check}")
                continue
            if result.passed:
                findings.append(f"Acceptance check passed for {work_order.id}: {result.check}")
                continue
            findings.append(f"Acceptance check failed for {work_order.id}: {result.check} ({result.details})")
            required_rework.append(f"Rework {work_order.id} to satisfy acceptance check: {result.check}")

    qa_result = QAGateResult.FAIL if required_rework else QAGateResult.PASS
    payload = QAGate(result=qa_result, findings=findings, required_rework=required_rework)
    return payload.model_dump(mode="json")

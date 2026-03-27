from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any, Literal

from deerflow.project_runtime.registry import get_specialist_config, specialist_uses_acp_by_default, tool_names_for_specialist
from deerflow.project_runtime.state import merge_active_work_order_ids, merge_work_orders
from deerflow.project_runtime.types import AgentReport, ProjectBrief, WorkOrder, WorkOrderStatus
from deerflow.tools import get_available_tools


@dataclass(frozen=True)
class DispatchBuildOutcome:
    kind: Literal["completed", "failed"]
    update: dict[str, Any]
    work_order_id: str
    error: str | None = None


def _normalize_work_order(value: WorkOrder | Mapping[str, Any]) -> WorkOrder:
    return WorkOrder.model_validate(value)


def _normalize_report(value: AgentReport | Mapping[str, Any]) -> AgentReport:
    return AgentReport.model_validate(value)


def _normalize_brief(value: ProjectBrief | Mapping[str, Any] | None) -> ProjectBrief | None:
    if value is None:
        return None
    return ProjectBrief.model_validate(value)


def _status_name(value: Any) -> str:
    if value is None:
        return ""
    status_value = getattr(value, "value", value)
    return str(status_value).lower()


def _completed_status_name() -> str:
    return "completed"


def _default_executor_cls():
    from deerflow.subagents.executor import SubagentExecutor

    return SubagentExecutor


def _replace_work_order_status(
    work_orders: list[WorkOrder | Mapping[str, Any]],
    *,
    work_order_id: str,
    status: WorkOrderStatus,
) -> list[dict[str, Any]]:
    updated: list[dict[str, Any]] = []
    for item in work_orders:
        work_order = _normalize_work_order(item)
        if work_order.id == work_order_id:
            work_order = work_order.model_copy(update={"status": status})
        updated.append(work_order.model_dump(mode="json"))
    return updated


def _dependency_statuses(work_orders: list[WorkOrder]) -> dict[str, WorkOrderStatus]:
    return {work_order.id: work_order.status for work_order in work_orders}


def _is_dependency_satisfied(status: WorkOrderStatus) -> bool:
    return status is WorkOrderStatus.COMPLETED


def select_runnable_work_orders(state: Mapping[str, Any]) -> list[WorkOrder]:
    work_orders = [_normalize_work_order(item) for item in state.get("work_orders") or []]
    active_ids = set(state.get("active_work_order_ids") or [])
    dependency_statuses = _dependency_statuses(work_orders)
    runnable_statuses = {
        WorkOrderStatus.PENDING,
        WorkOrderStatus.READY,
        WorkOrderStatus.FAILED,
        WorkOrderStatus.BLOCKED,
    }
    runnable: list[WorkOrder] = []

    for work_order in work_orders:
        if work_order.id in active_ids:
            continue
        if work_order.status not in runnable_statuses:
            continue
        if any(not _is_dependency_satisfied(dependency_statuses.get(dependency, WorkOrderStatus.BLOCKED)) for dependency in work_order.dependencies):
            continue
        runnable.append(work_order)

    return runnable


def build_specialist_task_input(
    state: Mapping[str, Any],
    work_order: WorkOrder | Mapping[str, Any],
    *,
    thread_id: str | None,
) -> str:
    normalized_work_order = _normalize_work_order(work_order)
    project_brief = _normalize_brief(state.get("project_brief"))
    dependency_ids = set(normalized_work_order.dependencies)
    prior_reports = [
        _normalize_report(item).model_dump(mode="json")
        for item in state.get("agent_reports") or []
        if _normalize_report(item).work_order_id in dependency_ids
    ]

    lines = [
        "You are executing a scoped project-runtime work order.",
        f"Thread ID: {thread_id or 'unknown'}",
        "ProjectBrief",
        str(project_brief.model_dump(mode="json") if project_brief is not None else {}),
        "WorkOrder",
        str(normalized_work_order.model_dump(mode="json")),
        "Prior reports",
        str(prior_reports),
        "Return a concise summary of changes, risks, and verification.",
    ]
    return "\n".join(lines)


def dispatch_work_order(
    state: Mapping[str, Any],
    work_order: WorkOrder | Mapping[str, Any],
    *,
    thread_id: str | None,
    available_tools: list[Any] | None = None,
    executor_cls=None,
) -> AgentReport:
    normalized_work_order = _normalize_work_order(work_order)
    specialist_config = get_specialist_config(normalized_work_order.owner_agent)
    if specialist_config is None:
        raise ValueError(f"Unknown specialist owner_agent: {normalized_work_order.owner_agent}")

    if available_tools is None:
        available_tools = get_available_tools(subagent_enabled=False)
    if executor_cls is None:
        executor_cls = _default_executor_cls()

    acp_enabled = any(getattr(tool, "name", None) == "invoke_acp_agent" for tool in available_tools)
    filtered_tool_names = tool_names_for_specialist(
        normalized_work_order.owner_agent,
        available_tools,
        acp_enabled=acp_enabled and specialist_uses_acp_by_default(normalized_work_order.owner_agent),
    )
    scoped_config = replace(specialist_config, tools=list(filtered_tool_names))
    executor = executor_cls(
        config=scoped_config,
        tools=available_tools,
        parent_model=None,
        sandbox_state=state.get("sandbox"),
        thread_data=state.get("thread_data"),
        thread_id=thread_id,
    )
    result = executor.execute(
        build_specialist_task_input(
            state,
            normalized_work_order,
            thread_id=thread_id,
        )
    )
    if _status_name(result.status) != _completed_status_name():
        result_status = _status_name(result.status) or "unknown"
        raise RuntimeError(result.error or f"Subagent execution finished with status {result_status}")

    return AgentReport(
        work_order_id=normalized_work_order.id,
        agent_name=normalized_work_order.owner_agent,
        summary=result.result or "",
        changes=[],
        risks=[],
        verification=[],
    )


def dispatch_build_step(
    state: Mapping[str, Any],
    *,
    thread_id: str | None,
    available_tools: list[Any] | None = None,
    executor_cls=None,
) -> DispatchBuildOutcome:
    runnable = select_runnable_work_orders(state)
    if not runnable:
        raise ValueError("No runnable work orders are available for dispatch")

    next_work_order = runnable[0]
    initial_active_ids = merge_active_work_order_ids(
        state.get("active_work_order_ids"),
        [*(state.get("active_work_order_ids") or []), next_work_order.id],
    )
    try:
        report = dispatch_work_order(
            state,
            next_work_order,
            thread_id=thread_id,
            available_tools=available_tools,
            executor_cls=executor_cls,
        )
    except ValueError:
        raise
    except Exception as exc:
        failed_work_orders = _replace_work_order_status(
            state.get("work_orders") or [],
            work_order_id=next_work_order.id,
            status=WorkOrderStatus.FAILED,
        )
        return DispatchBuildOutcome(
            kind="failed",
            work_order_id=next_work_order.id,
            error=str(exc),
            update={
                "work_orders": failed_work_orders,
                "active_work_order_ids": [work_order_id for work_order_id in initial_active_ids if work_order_id != next_work_order.id],
            },
        )

    completed_work_orders = _replace_work_order_status(
        state.get("work_orders") or [],
        work_order_id=next_work_order.id,
        status=WorkOrderStatus.COMPLETED,
    )
    return DispatchBuildOutcome(
        kind="completed",
        work_order_id=next_work_order.id,
        update={
            "work_orders": completed_work_orders,
            "active_work_order_ids": [work_order_id for work_order_id in initial_active_ids if work_order_id != next_work_order.id],
            "agent_reports": [report.model_dump(mode="json")],
        },
    )


def apply_dispatch_update(state: Mapping[str, Any], update: Mapping[str, Any]) -> dict[str, Any]:
    next_state = dict(state)
    next_state["work_orders"] = merge_work_orders(state.get("work_orders"), update.get("work_orders"))
    next_state["active_work_order_ids"] = merge_active_work_order_ids(
        state.get("active_work_order_ids"),
        update.get("active_work_order_ids"),
    )
    next_state["agent_reports"] = [*list(state.get("agent_reports") or []), *list(update.get("agent_reports") or [])]
    return next_state


def build_can_proceed_to_qa(state: Mapping[str, Any]) -> bool:
    work_orders = [_normalize_work_order(item) for item in state.get("work_orders") or []]
    if not work_orders:
        return True
    return all(work_order.status in {WorkOrderStatus.COMPLETED, WorkOrderStatus.CANCELLED} for work_order in work_orders)
def dispatch_build_phase(
    state: Mapping[str, Any],
    *,
    thread_id: str | None,
    available_tools: list[Any] | None = None,
    executor_cls=None,
    parent_model: str | None = None,  # kept for compatibility with graph tests and future callers
) -> dict[str, Any]:
    runnable = select_runnable_work_orders(state)
    if not runnable:
        if build_can_proceed_to_qa(state):
            return {
                "phase": "build",
                "work_orders": [
                    _normalize_work_order(item).model_dump(mode="json")
                    for item in state.get("work_orders") or []
                ],
                "active_work_order_ids": list(state.get("active_work_order_ids") or []),
                "agent_reports": list(state.get("agent_reports") or []),
                "build_error": None,
                "goto": "qa_gate",
            }
        unresolved = [
            _normalize_work_order(item).id
            for item in state.get("work_orders") or []
            if _normalize_work_order(item).status not in {WorkOrderStatus.COMPLETED, WorkOrderStatus.CANCELLED}
        ]
        raise RuntimeError(f"No runnable work orders remain: {', '.join(unresolved)}")

    outcome = dispatch_build_step(
        state,
        thread_id=thread_id,
        available_tools=available_tools,
        executor_cls=executor_cls,
    )
    next_state = apply_dispatch_update(state, outcome.update)
    if outcome.kind == "failed":
        return {
            "phase": "build",
            "work_orders": [
                _normalize_work_order(item).model_dump(mode="json")
                for item in next_state.get("work_orders") or []
            ],
            "active_work_order_ids": list(next_state.get("active_work_order_ids") or []),
            "agent_reports": list(next_state.get("agent_reports") or []),
            "build_error": outcome.error or f"Failed to dispatch {outcome.work_order_id}",
            "goto": "__end__",
        }

    return {
        "phase": "build",
        "work_orders": [
            _normalize_work_order(item).model_dump(mode="json")
            for item in next_state.get("work_orders") or []
        ],
        "active_work_order_ids": list(next_state.get("active_work_order_ids") or []),
        "agent_reports": list(next_state.get("agent_reports") or []),
        "build_error": None,
        "goto": "qa_gate" if build_can_proceed_to_qa(next_state) else "build",
    }

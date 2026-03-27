from collections.abc import Mapping
from typing import Annotated, Any, NotRequired

from deerflow.agents.thread_state import ThreadState
from deerflow.project_runtime.types import AgentReport, WorkOrder


def merge_agent_reports(
    existing: list[AgentReport | dict[str, Any]] | None,
    new: list[AgentReport | dict[str, Any]] | None,
) -> list[AgentReport | dict[str, Any]]:
    if existing is None:
        return list(new or [])
    if new is None:
        return list(existing)
    return [*existing, *new]


def merge_active_work_order_ids(existing: list[str] | None, new: list[str] | None) -> list[str]:
    if new is None:
        return list(existing or [])
    return list(dict.fromkeys(new))


def _work_order_id(value: WorkOrder | Mapping[str, Any]) -> str | None:
    if isinstance(value, Mapping):
        work_order_id = value.get("id")
        return work_order_id if isinstance(work_order_id, str) else None
    return value.id


def merge_work_orders(
    existing: list[WorkOrder | dict[str, Any]] | None,
    new: list[WorkOrder | dict[str, Any]] | None,
) -> list[WorkOrder | dict[str, Any]]:
    merged = list(existing or [])
    if not new:
        return merged

    index_by_id = {
        work_order_id: index
        for index, item in enumerate(merged)
        if (work_order_id := _work_order_id(item)) is not None
    }
    for item in new:
        work_order_id = _work_order_id(item)
        if work_order_id is None:
            merged.append(item)
            continue
        existing_index = index_by_id.get(work_order_id)
        if existing_index is None:
            index_by_id[work_order_id] = len(merged)
            merged.append(item)
            continue
        merged[existing_index] = item
    return merged


class ProjectThreadState(ThreadState):
    phase: NotRequired[str]
    plan_status: NotRequired[str]
    project_brief: NotRequired[dict | None]
    work_orders: NotRequired[Annotated[list[WorkOrder | dict[str, Any]], merge_work_orders]]
    active_work_order_ids: NotRequired[Annotated[list[str], merge_active_work_order_ids]]
    agent_reports: NotRequired[Annotated[list[AgentReport | dict[str, Any]], merge_agent_reports]]
    build_error: NotRequired[str | None]
    qa_gate: NotRequired[dict | None]
    delivery_summary: NotRequired[dict | None]
    project_runtime_version: NotRequired[str]


def make_project_thread_state_defaults() -> dict:
    return {
        "phase": "intake",
        "plan_status": "draft",
        "project_brief": None,
        "work_orders": [],
        "active_work_order_ids": [],
        "agent_reports": [],
        "build_error": None,
        "qa_gate": None,
        "delivery_summary": None,
        "project_runtime_version": "m1",
    }

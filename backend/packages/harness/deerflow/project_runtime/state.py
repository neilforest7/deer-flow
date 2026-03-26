from typing import NotRequired

from deerflow.agents.thread_state import ThreadState


class ProjectThreadState(ThreadState):
    phase: NotRequired[str]
    plan_status: NotRequired[str]
    project_brief: NotRequired[dict | None]
    work_orders: NotRequired[list]
    active_work_order_ids: NotRequired[list[str]]
    agent_reports: NotRequired[list]
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
        "qa_gate": None,
        "delivery_summary": None,
        "project_runtime_version": "m1",
    }

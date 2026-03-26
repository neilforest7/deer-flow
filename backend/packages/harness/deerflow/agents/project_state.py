"""Project runtime state for the project delivery graph."""

from typing import NotRequired, TypedDict

from deerflow.agents.thread_state import ThreadState


class ProjectBrief(TypedDict):
    objective: str
    target_users: list[str]
    deliverables: list[str]
    scope_in: list[str]
    scope_out: list[str]
    constraints: list[str]
    success_criteria: list[str]
    project_tags: list[str]


class WorkOrderState(TypedDict):
    id: str
    owner_agent: str
    description: str
    prompt: str
    goal: NotRequired[str]
    read_scope: NotRequired[list[str]]
    write_scope: NotRequired[list[str]]
    dependencies: NotRequired[list[str]]
    verification_steps: NotRequired[list[str]]
    done_definition: NotRequired[list[str]]
    status: str
    phase: str
    result: str
    updated_at: str


class AgentReportState(TypedDict):
    id: str
    owner_agent: str
    summary: str
    details: str
    changes_or_findings: NotRequired[list[str]]
    risks: NotRequired[list[str]]
    verification: NotRequired[list[str]]
    blockers: NotRequired[list[str]]
    handoff_to: NotRequired[list[str]]
    updated_at: str


class GateDecisionState(TypedDict):
    status: str
    blocking_issues: list[str]
    residual_risks: list[str]
    required_rework: list[str]
    updated_at: str


class DeliveryPackState(TypedDict):
    status: str
    artifacts: list[str]
    notes: list[str]
    updated_at: str


class ProjectControlState(TypedDict):
    pause_requested: bool
    abort_requested: bool
    updated_at: str


class ActiveBatchState(TypedDict):
    batch_id: str
    phase: str
    work_order_ids: list[str]
    status: str
    started_at: str
    updated_at: str


class ProjectState(ThreadState):
    project_id: NotRequired[str | None]
    team_name: NotRequired[str | None]
    project_status: NotRequired[str | None]
    project_phase: NotRequired[str | None]
    project_title: NotRequired[str | None]
    project_brief: NotRequired[ProjectBrief | None]
    work_orders: NotRequired[list[WorkOrderState] | None]
    agent_reports: NotRequired[list[AgentReportState] | None]
    gate_decision: NotRequired[GateDecisionState | None]
    delivery_pack: NotRequired[DeliveryPackState | None]
    active_batch: NotRequired[ActiveBatchState | None]
    control_flags: NotRequired[ProjectControlState | None]

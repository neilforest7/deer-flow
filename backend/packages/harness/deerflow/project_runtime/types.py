from enum import Enum

from pydantic import BaseModel, Field, field_validator


class Phase(str, Enum):
    INTAKE = "intake"
    DISCOVERY = "discovery"
    PLANNING = "planning"
    AWAITING_APPROVAL = "awaiting_approval"
    BUILD = "build"
    QA_GATE = "qa_gate"
    DELIVERY = "delivery"
    DONE = "done"


class PlanStatus(str, Enum):
    DRAFT = "draft"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    NEEDS_REVISION = "needs_revision"


class WorkOrderStatus(str, Enum):
    PENDING = "pending"
    READY = "ready"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


class QAGateResult(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    BLOCKED = "blocked"


class ProjectBrief(BaseModel):
    objective: str
    scope: list[str]
    constraints: list[str]
    deliverables: list[str]
    success_criteria: list[str]


class WorkOrder(BaseModel):
    id: str
    owner_agent: str
    title: str
    goal: str
    read_scope: list[str] = Field(default_factory=list)
    write_scope: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    acceptance_checks: list[str]
    status: WorkOrderStatus = WorkOrderStatus.PENDING

    @field_validator("acceptance_checks")
    @classmethod
    def validate_acceptance_checks(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("acceptance_checks must not be empty")
        return value


class AgentReport(BaseModel):
    work_order_id: str
    agent_name: str
    summary: str
    changes: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    verification: list[str] = Field(default_factory=list)


class QAGate(BaseModel):
    result: QAGateResult
    findings: list[str] = Field(default_factory=list)
    required_rework: list[str] = Field(default_factory=list)


class PlanningOutput(BaseModel):
    project_brief: ProjectBrief
    work_orders: list[WorkOrder]

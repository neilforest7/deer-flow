import pytest
from pydantic import ValidationError

from deerflow.project_runtime import (
    AgentReport,
    Phase,
    PlanStatus,
    PlanningOutput,
    ProjectBrief,
    QAGate,
    QAGateResult,
    WorkOrder,
    WorkOrderStatus,
)


def test_project_brief_accepts_valid_payload():
    brief = ProjectBrief(
        objective="Ship M1 runtime contracts",
        scope=["backend runtime"],
        constraints=["Do not change lead_agent"],
        deliverables=["types", "state"],
        success_criteria=["tests pass"],
    )

    assert brief.objective == "Ship M1 runtime contracts"
    assert brief.scope == ["backend runtime"]


def test_work_order_accepts_valid_payload():
    order = WorkOrder(
        id="wo-1",
        owner_agent="backend-agent",
        title="Add contracts",
        goal="Create canonical runtime models",
        read_scope=["backend/docs"],
        write_scope=["backend/packages/harness/deerflow/project_runtime"],
        dependencies=[],
        acceptance_checks=["pytest backend/tests/test_project_runtime_types.py"],
    )

    assert order.status is WorkOrderStatus.PENDING
    assert order.acceptance_checks == ["pytest backend/tests/test_project_runtime_types.py"]


@pytest.mark.parametrize(
    ("payload", "expected_error"),
    [
        (
            {
                "id": "wo-2",
                "owner_agent": "backend-agent",
                "title": "Missing checks",
                "goal": "Invalid because acceptance checks are empty",
                "read_scope": [],
                "write_scope": [],
                "dependencies": [],
                "acceptance_checks": [],
            },
            "acceptance_checks",
        ),
        (
            {
                "id": "wo-3",
                "owner_agent": "backend-agent",
                "title": "Wrong dependency shape",
                "goal": "Dependencies must be a list",
                "read_scope": [],
                "write_scope": [],
                "dependencies": "wo-1",
                "acceptance_checks": ["pytest"],
            },
            "dependencies",
        ),
        (
            {
                "id": "wo-4",
                "owner_agent": "backend-agent",
                "title": "Wrong status",
                "goal": "Status must be canonical",
                "read_scope": [],
                "write_scope": [],
                "dependencies": [],
                "acceptance_checks": ["pytest"],
                "status": "running",
            },
            "status",
        ),
    ],
)
def test_work_order_rejects_malformed_payload(payload, expected_error):
    with pytest.raises(ValidationError, match=expected_error):
        WorkOrder.model_validate(payload)


def test_agent_report_verification_must_be_a_list():
    with pytest.raises(ValidationError, match="verification"):
        AgentReport(
            work_order_id="wo-1",
            agent_name="backend-agent",
            summary="done",
            changes=["types.py"],
            risks=[],
            verification="pytest",
        )


def test_qa_gate_accepts_canonical_result():
    qa_gate = QAGate(
        result=QAGateResult.PASS,
        findings=["All acceptance checks passed"],
        required_rework=[],
    )

    assert qa_gate.result is QAGateResult.PASS


def test_planning_output_rejects_malformed_planner_payload():
    with pytest.raises(ValidationError):
        PlanningOutput.model_validate(
            {
                "project_brief": {
                    "objective": "Build runtime",
                    "scope": ["backend"],
                    "constraints": ["no lead_agent changes"],
                    "deliverables": ["types"],
                    "success_criteria": ["green tests"],
                },
                "work_orders": [
                    {
                        "id": "wo-5",
                        "owner_agent": "backend-agent",
                        "title": "Invalid order",
                        "goal": "acceptance checks missing",
                        "read_scope": [],
                        "write_scope": [],
                        "dependencies": [],
                        "acceptance_checks": [],
                    }
                ],
            }
        )


def test_enums_expose_canonical_values():
    assert Phase.AWAITING_APPROVAL.value == "awaiting_approval"
    assert PlanStatus.AWAITING_APPROVAL.value == "awaiting_approval"
    assert WorkOrderStatus.COMPLETED.value == "completed"
    assert QAGateResult.BLOCKED.value == "blocked"

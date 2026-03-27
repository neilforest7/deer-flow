from types import SimpleNamespace

import pytest

from deerflow.project_runtime.dispatcher import (
    apply_dispatch_update,
    build_can_proceed_to_qa,
    build_specialist_task_input,
    dispatch_build_phase,
    dispatch_build_step,
    select_runnable_work_orders,
)
from deerflow.project_runtime.types import WorkOrderStatus


def _state_with_work_orders():
    return {
        "project_brief": {
            "objective": "Implement backend runtime approval flow",
            "scope": ["backend runtime"],
            "constraints": ["keep lead_agent unchanged"],
            "deliverables": ["validated work orders"],
            "success_criteria": ["tests pass"],
        },
        "work_orders": [
            {
                "id": "wo-1",
                "owner_agent": "backend-agent",
                "title": "Backend work",
                "goal": "Implement backend runtime approval flow",
                "read_scope": ["backend/docs"],
                "write_scope": ["backend/packages/harness/deerflow/project_runtime"],
                "dependencies": [],
                "acceptance_checks": ["pytest"],
                "status": WorkOrderStatus.COMPLETED.value,
            },
            {
                "id": "wo-2",
                "owner_agent": "frontend-agent",
                "title": "Frontend work",
                "goal": "Implement frontend wiring",
                "read_scope": ["frontend"],
                "write_scope": ["frontend"],
                "dependencies": ["wo-1"],
                "acceptance_checks": ["test"],
                "status": WorkOrderStatus.PENDING.value,
            },
            {
                "id": "wo-3",
                "owner_agent": "backend-agent",
                "title": "Blocked work",
                "goal": "Wait on dependency",
                "read_scope": ["backend"],
                "write_scope": ["backend"],
                "dependencies": ["wo-99"],
                "acceptance_checks": ["pytest"],
                "status": WorkOrderStatus.PENDING.value,
            },
            {
                "id": "wo-4",
                "owner_agent": "backend-agent",
                "title": "Active work",
                "goal": "Already active",
                "read_scope": ["backend"],
                "write_scope": ["backend"],
                "dependencies": [],
                "acceptance_checks": ["pytest"],
                "status": WorkOrderStatus.ACTIVE.value,
            },
        ],
        "active_work_order_ids": ["wo-4"],
        "agent_reports": [
            {
                "work_order_id": "wo-1",
                "agent_name": "backend-agent",
                "summary": "Completed dependency",
                "changes": ["backend/packages/harness/deerflow/project_runtime/graph.py"],
                "risks": [],
                "verification": ["pytest"],
            }
        ],
    }


def test_select_runnable_work_orders_only_returns_dependency_satisfied_items():
    runnable = select_runnable_work_orders(_state_with_work_orders())

    assert [work_order.id for work_order in runnable] == ["wo-2"]


def test_build_specialist_task_input_contains_brief_work_order_reports_and_thread_id():
    task_input = build_specialist_task_input(_state_with_work_orders(), _state_with_work_orders()["work_orders"][1], thread_id="thread-123")

    assert "thread-123" in task_input
    assert "Implement backend runtime approval flow" in task_input
    assert "wo-2" in task_input
    assert "Completed dependency" in task_input


def test_dispatch_build_step_completes_work_order_and_appends_report():
    captured = {}

    class FakeExecutor:
        def __init__(self, config, tools, parent_model=None, sandbox_state=None, thread_data=None, thread_id=None):
            captured["config"] = config
            captured["tools"] = tools
            captured["thread_id"] = thread_id

        def execute(self, task):
            captured["task"] = task
            return SimpleNamespace(
                task_id="task-1",
                trace_id="trace-1",
                status="completed",
                result="Implemented frontend wiring",
            )

    outcome = dispatch_build_step(
        _state_with_work_orders(),
        thread_id="thread-123",
        available_tools=[
            SimpleNamespace(name="read_file"),
            SimpleNamespace(name="write_file"),
            SimpleNamespace(name="task"),
            SimpleNamespace(name="invoke_acp_agent"),
            SimpleNamespace(name="web_search"),
        ],
        executor_cls=FakeExecutor,
    )

    assert outcome.kind == "completed"
    assert outcome.work_order_id == "wo-2"
    assert outcome.update["work_orders"][1]["status"] == WorkOrderStatus.COMPLETED.value
    assert outcome.update["active_work_order_ids"] == ["wo-4"]
    assert outcome.update["agent_reports"][0]["summary"] == "Implemented frontend wiring"
    assert captured["config"].name == "frontend-agent"
    assert captured["config"].tools == ["read_file", "write_file", "web_search"]
    assert captured["thread_id"] == "thread-123"
    assert "thread-123" in captured["task"]


def test_dispatch_build_step_rejects_unknown_owner_before_executor_runs():
    state = {
        "project_brief": _state_with_work_orders()["project_brief"],
        "work_orders": [
            {
                "id": "wo-1",
                "owner_agent": "unknown-agent",
                "title": "Broken owner",
                "goal": "Should fail before dispatch",
                "read_scope": [],
                "write_scope": [],
                "dependencies": [],
                "acceptance_checks": ["pytest"],
                "status": WorkOrderStatus.PENDING.value,
            }
        ],
        "active_work_order_ids": [],
        "agent_reports": [],
    }

    class ExplodingExecutor:
        def __init__(self, *args, **kwargs):  # pragma: no cover - must never be reached
            raise AssertionError("Executor should not be created for an unknown owner")

    with pytest.raises(ValueError, match="Unknown specialist owner_agent"):
        dispatch_build_step(
            state,
            thread_id="thread-123",
            available_tools=[SimpleNamespace(name="read_file")],
            executor_cls=ExplodingExecutor,
        )


def test_dispatch_build_step_marks_failed_and_clears_active_id_on_execution_error():
    class FailingExecutor:
        def __init__(self, config, tools, parent_model=None, sandbox_state=None, thread_data=None, thread_id=None):
            pass

        def execute(self, task):
            return SimpleNamespace(
                task_id="task-1",
                trace_id="trace-1",
                status="failed",
                error="tool failure",
            )

    outcome = dispatch_build_step(
        _state_with_work_orders(),
        thread_id="thread-123",
        available_tools=[SimpleNamespace(name="read_file"), SimpleNamespace(name="write_file")],
        executor_cls=FailingExecutor,
    )

    assert outcome.kind == "failed"
    assert "tool failure" in (outcome.error or "")
    assert outcome.update["work_orders"][1]["status"] == WorkOrderStatus.FAILED.value
    assert outcome.update["active_work_order_ids"] == ["wo-4"]


def test_apply_dispatch_update_combines_new_report_and_work_order_status():
    outcome = {
        "work_orders": [
            {
                "id": "wo-2",
                "owner_agent": "frontend-agent",
                "title": "Frontend work",
                "goal": "Implement frontend wiring",
                "read_scope": ["frontend"],
                "write_scope": ["frontend"],
                "dependencies": ["wo-1"],
                "acceptance_checks": ["test"],
                "status": WorkOrderStatus.COMPLETED.value,
            }
        ],
        "active_work_order_ids": [],
        "agent_reports": [
            {
                "work_order_id": "wo-2",
                "agent_name": "frontend-agent",
                "summary": "done",
                "changes": [],
                "risks": [],
                "verification": [],
            }
        ],
    }

    next_state = apply_dispatch_update(_state_with_work_orders(), outcome)

    assert next_state["work_orders"][1]["status"] == WorkOrderStatus.COMPLETED.value
    assert len(next_state["agent_reports"]) == 2


def test_dispatch_build_phase_returns_after_one_completed_work_order_for_checkpointing():
    captured: list[str] = []

    class FakeExecutor:
        def __init__(self, config, tools, parent_model=None, sandbox_state=None, thread_data=None, thread_id=None):
            pass

        def execute(self, task):
            captured.append(task)
            return SimpleNamespace(
                task_id="task-1",
                trace_id="trace-1",
                status="completed",
                result="Implemented frontend wiring",
            )

    state = _state_with_work_orders()
    state["work_orders"].append(
        {
            "id": "wo-5",
            "owner_agent": "backend-agent",
            "title": "Second runnable work",
            "goal": "Continue build",
            "read_scope": ["backend"],
            "write_scope": ["backend"],
            "dependencies": [],
            "acceptance_checks": ["pytest"],
            "status": WorkOrderStatus.PENDING.value,
        }
    )

    result = dispatch_build_phase(
        state,
        thread_id="thread-123",
        available_tools=[SimpleNamespace(name="read_file"), SimpleNamespace(name="write_file")],
        executor_cls=FakeExecutor,
    )

    assert result["goto"] == "build"
    assert result["work_orders"][1]["status"] == WorkOrderStatus.COMPLETED.value
    assert result["work_orders"][4]["status"] == WorkOrderStatus.PENDING.value
    assert result["agent_reports"][-1]["work_order_id"] == "wo-2"
    assert result["build_error"] is None
    assert len(captured) == 1


def test_dispatch_build_phase_persists_failure_without_losing_prior_progress():
    class FlakyExecutor:
        call_count = 0

        def __init__(self, config, tools, parent_model=None, sandbox_state=None, thread_data=None, thread_id=None):
            pass

        def execute(self, task):
            type(self).call_count += 1
            if type(self).call_count == 1:
                return SimpleNamespace(
                    task_id="task-1",
                    trace_id="trace-1",
                    status="completed",
                    result="Implemented frontend wiring",
                )
            return SimpleNamespace(
                task_id="task-2",
                trace_id="trace-2",
                status="failed",
                error="tool failure",
            )

    state = _state_with_work_orders()
    state["work_orders"].append(
        {
            "id": "wo-5",
            "owner_agent": "backend-agent",
            "title": "Second runnable work",
            "goal": "Continue build",
            "read_scope": ["backend"],
            "write_scope": ["backend"],
            "dependencies": [],
            "acceptance_checks": ["pytest"],
            "status": WorkOrderStatus.PENDING.value,
        }
    )

    first_result = dispatch_build_phase(
        state,
        thread_id="thread-123",
        available_tools=[SimpleNamespace(name="read_file"), SimpleNamespace(name="write_file")],
        executor_cls=FlakyExecutor,
    )
    second_result = dispatch_build_phase(
        first_result,
        thread_id="thread-123",
        available_tools=[SimpleNamespace(name="read_file"), SimpleNamespace(name="write_file")],
        executor_cls=FlakyExecutor,
    )

    assert first_result["work_orders"][1]["status"] == WorkOrderStatus.COMPLETED.value
    assert first_result["agent_reports"][-1]["work_order_id"] == "wo-2"
    assert second_result["goto"] == "__end__"
    assert second_result["work_orders"][4]["status"] == WorkOrderStatus.FAILED.value
    assert second_result["agent_reports"][-1]["work_order_id"] == "wo-2"
    assert second_result["build_error"] == "tool failure"


def test_dispatch_build_phase_goes_to_qa_once_all_work_orders_are_terminal():
    result = dispatch_build_phase(
        {
            "work_orders": [
                {
                    "id": "wo-1",
                    "owner_agent": "backend-agent",
                    "title": "Backend work",
                    "goal": "Complete",
                    "read_scope": [],
                    "write_scope": [],
                    "dependencies": [],
                    "acceptance_checks": ["pytest"],
                    "status": WorkOrderStatus.COMPLETED.value,
                }
            ],
            "active_work_order_ids": [],
            "agent_reports": [],
        },
        thread_id="thread-123",
    )

    assert result["goto"] == "qa_gate"
    assert result["build_error"] is None


def test_build_can_proceed_to_qa_requires_all_orders_to_be_terminal():
    assert build_can_proceed_to_qa({"work_orders": []}) is True
    assert build_can_proceed_to_qa(_state_with_work_orders()) is False
    assert build_can_proceed_to_qa(
        {
            "work_orders": [
                {
                    "id": "wo-1",
                    "owner_agent": "backend-agent",
                    "title": "Backend work",
                    "goal": "Complete",
                    "read_scope": [],
                    "write_scope": [],
                    "dependencies": [],
                    "acceptance_checks": ["pytest"],
                    "status": WorkOrderStatus.COMPLETED.value,
                }
            ]
        }
    ) is True

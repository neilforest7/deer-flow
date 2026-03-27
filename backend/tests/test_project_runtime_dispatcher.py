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
        def __init__(
            self,
            config,
            tools,
            parent_model=None,
            sandbox_state=None,
            thread_data=None,
            thread_id=None,
            trace_id=None,
            run_metadata=None,
        ):
            captured["config"] = config
            captured["tools"] = tools
            captured["thread_id"] = thread_id
            captured["parent_model"] = parent_model
            captured["trace_id"] = trace_id
            captured["run_metadata"] = run_metadata

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
        parent_model="project-model",
        trace_id="trace-build-1",
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
    assert captured["parent_model"] == "project-model"
    assert captured["thread_id"] == "thread-123"
    assert captured["trace_id"] == "trace-build-1"
    assert captured["run_metadata"]["runtime"] == "project_team"
    assert captured["run_metadata"]["phase"] == "build"
    assert captured["run_metadata"]["execution_kind"] == "build_specialist"
    assert captured["run_metadata"]["work_order_id"] == "wo-2"
    assert captured["run_metadata"]["owner_agent"] == "frontend-agent"
    assert captured["run_metadata"]["trace_id"] == "trace-build-1"
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
        def __init__(self, config, tools, parent_model=None, sandbox_state=None, thread_data=None, thread_id=None, trace_id=None, run_metadata=None):
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
        trace_id="trace-build-fail",
        available_tools=[SimpleNamespace(name="read_file"), SimpleNamespace(name="write_file")],
        executor_cls=FailingExecutor,
    )

    assert outcome.kind == "failed"
    assert "tool failure" in (outcome.error or "")
    assert outcome.update["work_orders"][1]["status"] == WorkOrderStatus.FAILED.value
    assert outcome.update["active_work_order_ids"] == ["wo-4"]


def test_dispatch_build_step_keeps_thread_id_and_thread_data_isolated_across_threads():
    captures: list[dict[str, object]] = []

    class CapturingExecutor:
        def __init__(self, config, tools, parent_model=None, sandbox_state=None, thread_data=None, thread_id=None, trace_id=None, run_metadata=None):
            captures.append(
                {
                    "config_name": config.name,
                    "thread_id": thread_id,
                    "thread_data": thread_data,
                    "trace_id": trace_id,
                    "run_metadata": run_metadata,
                }
            )

        def execute(self, task):
            captures[-1]["task"] = task
            return SimpleNamespace(
                task_id="task-1",
                trace_id="trace-1",
                status="completed",
                result="done",
            )

    first_state = _state_with_work_orders()
    first_state["thread_data"] = {"workspace_path": "/tmp/thread-a/workspace"}
    second_state = _state_with_work_orders()
    second_state["thread_data"] = {"workspace_path": "/tmp/thread-b/workspace"}

    first_outcome = dispatch_build_step(
        first_state,
        thread_id="thread-a",
        trace_id="trace-thread-a",
        available_tools=[SimpleNamespace(name="read_file"), SimpleNamespace(name="write_file")],
        executor_cls=CapturingExecutor,
    )
    second_outcome = dispatch_build_step(
        second_state,
        thread_id="thread-b",
        trace_id="trace-thread-b",
        available_tools=[SimpleNamespace(name="read_file"), SimpleNamespace(name="write_file")],
        executor_cls=CapturingExecutor,
    )

    assert first_outcome.kind == "completed"
    assert second_outcome.kind == "completed"
    assert captures[0]["thread_id"] == "thread-a"
    assert captures[1]["thread_id"] == "thread-b"
    assert captures[0]["thread_data"] == {"workspace_path": "/tmp/thread-a/workspace"}
    assert captures[1]["thread_data"] == {"workspace_path": "/tmp/thread-b/workspace"}
    assert captures[0]["trace_id"] == "trace-thread-a"
    assert captures[1]["trace_id"] == "trace-thread-b"
    assert captures[0]["run_metadata"]["runtime"] == "project_team"
    assert captures[1]["run_metadata"]["runtime"] == "project_team"
    assert "thread-a" in str(captures[0]["task"])
    assert "thread-b" in str(captures[1]["task"])
    assert "thread-b" not in str(captures[0]["task"])
    assert "thread-a" not in str(captures[1]["task"])


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
        def __init__(self, config, tools, parent_model=None, sandbox_state=None, thread_data=None, thread_id=None, trace_id=None, run_metadata=None):
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
        trace_id="trace-phase-1",
        available_tools=[SimpleNamespace(name="read_file"), SimpleNamespace(name="write_file")],
        executor_cls=FakeExecutor,
    )

    assert result["goto"] == "build"
    assert result["work_orders"][1]["status"] == WorkOrderStatus.COMPLETED.value
    assert result["work_orders"][4]["status"] == WorkOrderStatus.PENDING.value
    assert result["agent_reports"][-1]["work_order_id"] == "wo-2"
    assert result["build_error"] is None
    assert result["trace_id"] == "trace-phase-1"
    assert len(captured) == 1


def test_dispatch_build_phase_persists_failure_without_losing_prior_progress():
    class FlakyExecutor:
        call_count = 0

        def __init__(self, config, tools, parent_model=None, sandbox_state=None, thread_data=None, thread_id=None, trace_id=None, run_metadata=None):
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
        trace_id="trace-phase-2",
        available_tools=[SimpleNamespace(name="read_file"), SimpleNamespace(name="write_file")],
        executor_cls=FlakyExecutor,
    )
    second_result = dispatch_build_phase(
        first_result,
        thread_id="thread-123",
        trace_id="trace-phase-2",
        available_tools=[SimpleNamespace(name="read_file"), SimpleNamespace(name="write_file")],
        executor_cls=FlakyExecutor,
    )

    assert first_result["work_orders"][1]["status"] == WorkOrderStatus.COMPLETED.value
    assert first_result["agent_reports"][-1]["work_order_id"] == "wo-2"
    assert second_result["goto"] == "__end__"
    assert second_result["work_orders"][4]["status"] == WorkOrderStatus.FAILED.value
    assert second_result["agent_reports"][-1]["work_order_id"] == "wo-2"
    assert second_result["build_error"] == "tool failure"
    assert second_result["trace_id"] == "trace-phase-2"


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
        trace_id="trace-phase-qa",
    )

    assert result["goto"] == "qa_gate"
    assert result["build_error"] is None
    assert result["trace_id"] == "trace-phase-qa"


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

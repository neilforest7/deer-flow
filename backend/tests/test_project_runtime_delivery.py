from types import SimpleNamespace

import pytest

from deerflow.project_runtime.delivery import build_delivery_summary, execute_delivery_phase, run_delivery


def test_build_delivery_summary_contains_completed_work_artifacts_verification_and_follow_ups():
    summary = build_delivery_summary(
        {
            "work_orders": [
                {
                    "id": "wo-1",
                    "owner_agent": "backend-agent",
                    "title": "Implement runtime",
                    "goal": "Ship runtime",
                    "read_scope": [],
                    "write_scope": [],
                    "dependencies": [],
                    "acceptance_checks": ["pytest"],
                    "status": "completed",
                }
            ],
            "agent_reports": [
                {
                    "work_order_id": "wo-1",
                    "agent_name": "backend-agent",
                    "summary": "Implemented runtime changes",
                    "changes": ["backend/packages/harness/deerflow/project_runtime/graph.py"],
                    "risks": ["Need broader regression coverage"],
                    "verification": ["pytest -q"],
                }
            ],
            "qa_gate": {
                "result": "pass",
                "findings": ["Acceptance check passed for wo-1: pytest"],
                "required_rework": [],
            },
            "artifacts": ["backend/packages/harness/deerflow/project_runtime/graph.py"],
        }
    )

    assert [item.work_order_id for item in summary.completed_work] == ["wo-1"]
    assert summary.artifacts == ["backend/packages/harness/deerflow/project_runtime/graph.py"]
    assert "pytest -q" in summary.verification
    assert "Acceptance check passed for wo-1: pytest" in summary.verification
    assert "Need broader regression coverage" in summary.follow_ups


def test_execute_delivery_phase_uses_delivery_agent_output():
    class DeliveryExecutor:
        def __init__(self, config, tools, parent_model=None, sandbox_state=None, thread_data=None, thread_id=None):
            self.config = config

        def execute(self, task):
            payload = {
                "completed_work": [{"work_order_id": "wo-1", "title": "Implement runtime", "summary": "done"}],
                "artifacts": ["artifact.txt"],
                "verification": ["pytest -q"],
                "follow_ups": ["monitor rollout"],
            }
            return SimpleNamespace(status="completed", result=str(payload).replace("'", '"'))

    summary = execute_delivery_phase(
        {
            "work_orders": [
                {
                    "id": "wo-1",
                    "owner_agent": "backend-agent",
                    "title": "Implement runtime",
                    "goal": "Ship runtime",
                    "read_scope": [],
                    "write_scope": [],
                    "dependencies": [],
                    "acceptance_checks": ["pytest"],
                    "status": "completed",
                }
            ],
            "agent_reports": [{"work_order_id": "wo-1", "agent_name": "backend-agent", "summary": "done"}],
            "qa_gate": {"result": "pass", "findings": [], "required_rework": []},
            "artifacts": [],
        },
        thread_id="thread-1",
        available_tools=[SimpleNamespace(name="read_file"), SimpleNamespace(name="present_files")],
        executor_cls=DeliveryExecutor,
    )

    assert summary.completed_work[0].work_order_id == "wo-1"
    assert summary.artifacts == ["artifact.txt"]


def test_run_delivery_falls_back_to_deterministic_summary(monkeypatch):
    class FailingExecutor:
        def __init__(self, config, tools, parent_model=None, sandbox_state=None, thread_data=None, thread_id=None):
            pass

        def execute(self, task):
            return SimpleNamespace(status="failed", error="boom")

    monkeypatch.setattr("deerflow.project_runtime.delivery._deterministic_phase_fallback_allowed", lambda: True)

    result = run_delivery(
        {
            "work_orders": [
                {
                    "id": "wo-1",
                    "owner_agent": "backend-agent",
                    "title": "Implement runtime",
                    "goal": "Ship runtime",
                    "read_scope": [],
                    "write_scope": [],
                    "dependencies": [],
                    "acceptance_checks": ["pytest"],
                    "status": "completed",
                }
            ],
            "agent_reports": [{"work_order_id": "wo-1", "agent_name": "backend-agent", "summary": "done"}],
            "qa_gate": {"result": "pass", "findings": [], "required_rework": []},
            "artifacts": [],
        },
        thread_id="thread-1",
        available_tools=[SimpleNamespace(name="read_file"), SimpleNamespace(name="present_files")],
        executor_cls=FailingExecutor,
    )

    assert result["phase_artifacts"]["delivery"]["mode"] == "deterministic"
    assert result["delivery_summary"]["completed_work"][0]["work_order_id"] == "wo-1"


def test_run_delivery_raises_when_specialist_fails_and_fallback_is_disabled(monkeypatch):
    class FailingExecutor:
        def __init__(self, config, tools, parent_model=None, sandbox_state=None, thread_data=None, thread_id=None):
            pass

        def execute(self, task):
            return SimpleNamespace(status="failed", error="boom")

    monkeypatch.setattr("deerflow.project_runtime.delivery._deterministic_phase_fallback_allowed", lambda: False)

    with pytest.raises(RuntimeError, match="boom"):
        run_delivery(
            {
                "work_orders": [
                    {
                        "id": "wo-1",
                        "owner_agent": "backend-agent",
                        "title": "Implement runtime",
                        "goal": "Ship runtime",
                        "read_scope": [],
                        "write_scope": [],
                        "dependencies": [],
                        "acceptance_checks": ["pytest"],
                        "status": "completed",
                    }
                ],
                "agent_reports": [{"work_order_id": "wo-1", "agent_name": "backend-agent", "summary": "done"}],
                "qa_gate": {"result": "pass", "findings": [], "required_rework": []},
                "artifacts": [],
            },
            thread_id="thread-1",
            available_tools=[SimpleNamespace(name="read_file"), SimpleNamespace(name="present_files")],
            executor_cls=FailingExecutor,
        )

from deerflow.project_runtime.delivery import build_delivery_summary


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

    assert [item["work_order_id"] for item in summary["completed_work"]] == ["wo-1"]
    assert summary["artifacts"] == ["backend/packages/harness/deerflow/project_runtime/graph.py"]
    assert "pytest -q" in summary["verification"]
    assert "Acceptance check passed for wo-1: pytest" in summary["verification"]
    assert "Need broader regression coverage" in summary["follow_ups"]

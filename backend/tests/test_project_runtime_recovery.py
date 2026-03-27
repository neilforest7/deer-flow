from langgraph.checkpoint.memory import InMemorySaver

from deerflow.project_runtime import Phase, PlanStatus
from deerflow.project_runtime.graph import compile_project_team_agent


def test_build_recovery_resumes_from_checkpoint_without_repeating_completed_work(monkeypatch):
    graph = compile_project_team_agent(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "recovery-build-thread"}, "recursion_limit": 20}
    graph.invoke({"messages": []}, config=config)

    call_count = 0

    def fake_dispatch(state, *, thread_id, parent_model=None, trace_id=None, available_tools=None, executor_cls=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return {
                "phase": "build",
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
                    },
                    {
                        "id": "wo-2",
                        "owner_agent": "backend-agent",
                        "title": "Follow-up",
                        "goal": "Ship runtime",
                        "read_scope": [],
                        "write_scope": [],
                        "dependencies": [],
                        "acceptance_checks": ["pytest"],
                        "status": "pending",
                    },
                ],
                "active_work_order_ids": [],
                "agent_reports": [{"work_order_id": "wo-1", "agent_name": "backend-agent", "summary": "done"}],
                "build_error": None,
                "goto": "build",
            }
        assert state["work_orders"][0]["status"] == "completed"
        return {
            "phase": "build",
            "work_orders": [
                state["work_orders"][0],
                {
                    "id": "wo-2",
                    "owner_agent": "backend-agent",
                    "title": "Follow-up",
                    "goal": "Ship runtime",
                    "read_scope": [],
                    "write_scope": [],
                    "dependencies": [],
                    "acceptance_checks": ["pytest"],
                    "status": "completed",
                },
            ],
            "active_work_order_ids": [],
            "agent_reports": [
                {"work_order_id": "wo-1", "agent_name": "backend-agent", "summary": "done"},
                {"work_order_id": "wo-2", "agent_name": "backend-agent", "summary": "done"},
            ],
            "build_error": None,
            "goto": "qa_gate",
        }

    monkeypatch.setattr("deerflow.project_runtime.graph.dispatch_build_phase", fake_dispatch)
    monkeypatch.setattr(
        "deerflow.project_runtime.graph.run_qa_gate",
        lambda state, *, thread_id, parent_model=None, trace_id=None, available_tools=None, executor_cls=None: {
            "result": "blocked",
            "findings": ["awaiting resume"],
            "required_rework": [],
        },
    )

    graph.invoke({"plan_status": PlanStatus.APPROVED.value}, config=config)
    graph.invoke({}, config=config)

    assert call_count == 2
    assert graph.get_state(config).values["phase"] == Phase.QA_GATE.value


def test_delivery_recovery_rebuilds_summary_idempotently():
    graph = compile_project_team_agent(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "recovery-delivery-thread"}, "recursion_limit": 20}

    graph.invoke(
        {
            "phase": Phase.DELIVERY.value,
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
        },
        config=config,
    )
    first_summary = graph.get_state(config).values["delivery_summary"]

    graph.invoke({"phase": Phase.DELIVERY.value}, config=config)
    second_summary = graph.get_state(config).values["delivery_summary"]

    assert first_summary == second_summary
    assert graph.get_state(config).values["phase"] == Phase.DONE.value

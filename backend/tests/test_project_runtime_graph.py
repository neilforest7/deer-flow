import json
from pathlib import Path

import pytest
from langgraph.graph import END, START, StateGraph
from langgraph.checkpoint.memory import InMemorySaver

from deerflow.project_runtime import Phase, PlanStatus, ProjectThreadState
from deerflow.project_runtime.graph import (
    make_project_team_agent,
    resolve_approval_transition,
    resolve_qa_transition,
    route_from_phase,
)
from deerflow.project_runtime.types import WorkOrderStatus


def test_project_team_agent_compiles_with_project_thread_state():
    graph = make_project_team_agent()

    assert graph.builder.state_schema is ProjectThreadState


def test_project_team_agent_contains_required_phase_topology():
    graph = make_project_team_agent()
    edges = {(edge.source, edge.target, edge.conditional) for edge in graph.get_graph().edges}

    assert edges == {
        ("__start__", "intake", True),
        ("__start__", "discovery", True),
        ("__start__", "planning", True),
        ("__start__", "awaiting_approval", True),
        ("__start__", "build", True),
        ("__start__", "qa_gate", True),
        ("__start__", "delivery", True),
        ("__start__", "done", True),
        ("intake", "discovery", False),
        ("discovery", "planning", False),
        ("planning", "awaiting_approval", False),
        ("awaiting_approval", "__end__", False),
        ("build", "__end__", False),
        ("qa_gate", "__end__", False),
        ("delivery", "done", False),
        ("done", "__end__", False),
    }


def test_project_team_agent_does_not_expose_unsupported_transitions():
    graph = make_project_team_agent()
    edges = {(edge.source, edge.target) for edge in graph.get_graph().edges}

    assert ("planning", "build") not in edges
    assert ("build", "delivery") not in edges
    assert ("qa_gate", "done") not in edges
    assert ("awaiting_approval", "awaiting_approval") not in edges
    assert ("qa_gate", "qa_gate") not in edges


def test_start_router_resumes_from_persisted_phase():
    assert route_from_phase({}) == "intake"
    assert route_from_phase({"phase": Phase.DISCOVERY.value}) == "discovery"
    assert route_from_phase({"phase": Phase.PLANNING.value}) == "planning"
    assert route_from_phase({"phase": Phase.AWAITING_APPROVAL.value}) == "awaiting_approval"
    assert route_from_phase({"phase": Phase.BUILD.value}) == "build"
    assert route_from_phase({"phase": Phase.QA_GATE.value}) == "qa_gate"
    assert route_from_phase({"phase": Phase.DELIVERY.value}) == "delivery"
    assert route_from_phase({"phase": Phase.DONE.value}) == "done"


def test_awaiting_approval_transition_respects_plan_status():
    assert resolve_approval_transition({"plan_status": PlanStatus.APPROVED.value}) == "build"
    assert resolve_approval_transition({"plan_status": PlanStatus.NEEDS_REVISION.value}) == "planning"
    assert resolve_approval_transition({"phase": Phase.DONE.value}) == "done"
    assert resolve_approval_transition({"plan_status": PlanStatus.AWAITING_APPROVAL.value}) == "__end__"


def test_qa_gate_transition_respects_qa_result():
    assert resolve_qa_transition({"qa_gate": {"result": "pass"}}) == "delivery"
    assert resolve_qa_transition({"qa_gate": {"result": "fail"}}) == "planning"
    assert resolve_qa_transition({"qa_gate": {"result": "blocked"}}) == "__end__"
    assert resolve_qa_transition({}) == "__end__"


def test_initial_run_pauses_at_awaiting_approval_without_recursing():
    graph = make_project_team_agent(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "approval-thread"}, "recursion_limit": 20}

    result = graph.invoke({"messages": []}, config=config)

    assert result["phase"] == Phase.AWAITING_APPROVAL.value
    assert result["plan_status"] == PlanStatus.AWAITING_APPROVAL.value
    assert graph.get_state(config).values["phase"] == Phase.AWAITING_APPROVAL.value


def test_approved_run_materializes_build_before_pausing_at_qa_gate():
    graph = make_project_team_agent(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "build-thread"}, "recursion_limit": 20}
    graph.invoke({"messages": []}, config=config)
    seen_thread_ids: list[str] = []
    call_count = 0

    def fake_dispatch(_state, *, thread_id, parent_model=None, available_tools=None, executor_cls=None):
        nonlocal call_count
        call_count += 1
        seen_thread_ids.append(thread_id)
        return {
            "phase": Phase.BUILD.value,
            "work_orders": [
                {
                    "id": "wo-backend-implementation",
                    "owner_agent": "backend-agent",
                    "title": "Implement project runtime changes",
                    "goal": "Clarify the project runtime request",
                    "acceptance_checks": ["uv run pytest backend/tests/test_project_runtime_graph.py"],
                    "status": WorkOrderStatus.PENDING.value if call_count == 1 else WorkOrderStatus.COMPLETED.value,
                }
            ],
            "active_work_order_ids": [],
            "agent_reports": [] if call_count == 1 else [
                {"work_order_id": "wo-backend-implementation", "agent_name": "backend-agent", "summary": "done"}
            ],
            "build_error": None,
            "goto": "build" if call_count == 1 else "qa_gate",
        }

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr("deerflow.project_runtime.graph.dispatch_build_phase", fake_dispatch)
    updates = list(graph.stream({"plan_status": PlanStatus.APPROVED.value}, config=config, stream_mode="updates"))
    monkeypatch.undo()

    assert seen_thread_ids == ["build-thread", "build-thread"]
    assert sum(1 for chunk in updates if chunk.get("build", {}).get("phase") == Phase.BUILD.value) == 1
    assert graph.get_state(config).values["phase"] == Phase.QA_GATE.value
    assert graph.get_state(config).values["agent_reports"][-1]["work_order_id"] == "wo-backend-implementation"


def test_qa_pass_materializes_delivery_before_done():
    graph = make_project_team_agent(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "delivery-thread"}, "recursion_limit": 20}
    graph.invoke({"messages": []}, config=config)

    def fake_dispatch(_state, *, thread_id, parent_model=None, available_tools=None, executor_cls=None):
        assert thread_id == "delivery-thread"
        return {
            "phase": Phase.BUILD.value,
            "work_orders": [
                {
                    "id": "wo-backend-implementation",
                    "owner_agent": "backend-agent",
                    "title": "Implement project runtime changes",
                    "goal": "Clarify the project runtime request",
                    "acceptance_checks": ["uv run pytest backend/tests/test_project_runtime_graph.py"],
                    "status": WorkOrderStatus.COMPLETED.value,
                }
            ],
            "active_work_order_ids": [],
            "agent_reports": [
                {"work_order_id": "wo-backend-implementation", "agent_name": "backend-agent", "summary": "done"}
            ],
            "build_error": None,
            "goto": "qa_gate",
        }

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr("deerflow.project_runtime.graph.dispatch_build_phase", fake_dispatch)
    graph.invoke({"plan_status": PlanStatus.APPROVED.value}, config=config)

    updates = list(graph.stream({"qa_gate": {"result": "pass"}}, config=config, stream_mode="updates"))
    monkeypatch.undo()

    assert any(chunk.get("delivery") == {"phase": Phase.DELIVERY.value} for chunk in updates)
    assert graph.get_state(config).values["phase"] == Phase.DONE.value


def test_build_failure_is_checkpointed_without_reusing_default_thread():
    graph = make_project_team_agent(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "failure-thread"}, "recursion_limit": 20}
    graph.invoke({"messages": []}, config=config)

    def fake_dispatch(_state, *, thread_id, parent_model=None, available_tools=None, executor_cls=None):
        assert thread_id == "failure-thread"
        return {
            "phase": Phase.BUILD.value,
            "work_orders": [
                {
                    "id": "wo-backend-implementation",
                    "owner_agent": "backend-agent",
                    "title": "Implement project runtime changes",
                    "goal": "Clarify the project runtime request",
                    "acceptance_checks": ["uv run pytest backend/tests/test_project_runtime_graph.py"],
                    "status": WorkOrderStatus.FAILED.value,
                }
            ],
            "active_work_order_ids": [],
            "agent_reports": [],
            "build_error": "tool failure",
            "goto": "__end__",
        }

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr("deerflow.project_runtime.graph.dispatch_build_phase", fake_dispatch)
    result = graph.invoke({"plan_status": PlanStatus.APPROVED.value}, config=config)
    monkeypatch.undo()

    assert result["phase"] == Phase.BUILD.value
    assert result["build_error"] == "tool failure"
    assert graph.get_state(config).values["work_orders"][0]["status"] == WorkOrderStatus.FAILED.value


def test_langgraph_registers_project_team_agent_without_removing_lead_agent():
    langgraph_path = Path(__file__).parent.parent / "langgraph.json"
    payload = json.loads(langgraph_path.read_text(encoding="utf-8"))

    assert payload["graphs"] == {
        "lead_agent": "deerflow.agents:make_lead_agent",
        "project_team_agent": "deerflow.project_runtime:make_project_team_agent",
    }


def test_project_thread_state_allows_parallel_agent_report_updates():
    def route(_state: ProjectThreadState) -> list[str]:
        return ["report_a", "report_b"]

    def report_a(_state: ProjectThreadState) -> dict:
        return {
            "agent_reports": [
                {
                    "work_order_id": "wo-1",
                    "agent_name": "agent-a",
                    "summary": "done",
                }
            ]
        }

    def report_b(_state: ProjectThreadState) -> dict:
        return {
            "agent_reports": [
                {
                    "work_order_id": "wo-2",
                    "agent_name": "agent-b",
                    "summary": "done",
                }
            ]
        }

    graph = StateGraph(ProjectThreadState)
    graph.add_node("report_a", report_a)
    graph.add_node("report_b", report_b)
    graph.add_conditional_edges(START, route, ["report_a", "report_b"])
    graph.add_edge("report_a", END)
    graph.add_edge("report_b", END)

    result = graph.compile().invoke({})

    assert [report["work_order_id"] for report in result["agent_reports"]] == ["wo-1", "wo-2"]


def test_project_thread_state_allows_parallel_work_order_updates():
    def route(_state: ProjectThreadState) -> list[str]:
        return ["activate", "complete"]

    def activate(_state: ProjectThreadState) -> dict:
        return {
            "work_orders": [
                {
                    "id": "wo-1",
                    "owner_agent": "backend-agent",
                    "title": "Build",
                    "goal": "Ship runtime",
                    "acceptance_checks": ["pytest"],
                    "status": WorkOrderStatus.ACTIVE.value,
                }
            ]
        }

    def complete(_state: ProjectThreadState) -> dict:
        return {
            "work_orders": [
                {
                    "id": "wo-1",
                    "owner_agent": "backend-agent",
                    "title": "Build",
                    "goal": "Ship runtime",
                    "acceptance_checks": ["pytest"],
                    "status": WorkOrderStatus.COMPLETED.value,
                }
            ]
        }

    graph = StateGraph(ProjectThreadState)
    graph.add_node("activate", activate)
    graph.add_node("complete", complete)
    graph.add_conditional_edges(START, route, ["activate", "complete"])
    graph.add_edge("activate", END)
    graph.add_edge("complete", END)

    result = graph.compile().invoke({})

    assert result["work_orders"] == [
        {
            "id": "wo-1",
            "owner_agent": "backend-agent",
            "title": "Build",
            "goal": "Ship runtime",
            "acceptance_checks": ["pytest"],
            "status": WorkOrderStatus.COMPLETED.value,
        }
    ]

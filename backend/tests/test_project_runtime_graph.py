import json
from pathlib import Path

from deerflow.project_runtime import Phase, PlanStatus, ProjectThreadState
from deerflow.project_runtime.graph import (
    make_project_team_agent,
    route_after_awaiting_approval,
    route_after_qa_gate,
)


def test_project_team_agent_compiles_with_project_thread_state():
    graph = make_project_team_agent()

    assert graph.builder.state_schema is ProjectThreadState


def test_project_team_agent_contains_required_phase_topology():
    graph = make_project_team_agent()
    edges = {(edge.source, edge.target, edge.conditional) for edge in graph.get_graph().edges}

    assert edges == {
        ("__start__", "intake", False),
        ("intake", "discovery", False),
        ("discovery", "planning", False),
        ("planning", "awaiting_approval", False),
        ("awaiting_approval", "build", True),
        ("awaiting_approval", "planning", True),
        ("awaiting_approval", "done", True),
        ("awaiting_approval", "awaiting_approval", True),
        ("build", "qa_gate", False),
        ("qa_gate", "delivery", True),
        ("qa_gate", "planning", True),
        ("qa_gate", "qa_gate", True),
        ("delivery", "done", False),
        ("done", "__end__", False),
    }


def test_project_team_agent_does_not_expose_unsupported_transitions():
    graph = make_project_team_agent()
    edges = {(edge.source, edge.target) for edge in graph.get_graph().edges}

    assert ("planning", "build") not in edges
    assert ("build", "delivery") not in edges
    assert ("qa_gate", "done") not in edges


def test_awaiting_approval_router_only_allows_supported_destinations():
    assert route_after_awaiting_approval({"phase": Phase.BUILD.value}) == "build"
    assert route_after_awaiting_approval({"phase": Phase.PLANNING.value}) == "planning"
    assert route_after_awaiting_approval({"phase": Phase.DONE.value}) == "done"
    assert route_after_awaiting_approval({"phase": Phase.AWAITING_APPROVAL.value}) == "awaiting_approval"


def test_qa_gate_router_only_allows_supported_destinations():
    assert route_after_qa_gate({"phase": Phase.DELIVERY.value}) == "delivery"
    assert route_after_qa_gate({"phase": Phase.PLANNING.value}) == "planning"
    assert route_after_qa_gate({"phase": Phase.QA_GATE.value}) == "qa_gate"


def test_langgraph_registers_project_team_agent_without_removing_lead_agent():
    langgraph_path = Path(__file__).parent.parent / "langgraph.json"
    payload = json.loads(langgraph_path.read_text(encoding="utf-8"))

    assert payload["graphs"] == {
        "lead_agent": "deerflow.agents:make_lead_agent",
        "project_team_agent": "deerflow.project_runtime:make_project_team_agent",
    }

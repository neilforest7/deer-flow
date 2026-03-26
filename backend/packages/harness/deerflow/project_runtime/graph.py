from typing import Literal

from langgraph.graph import END, START, StateGraph

from deerflow.project_runtime.state import ProjectThreadState, make_project_thread_state_defaults
from deerflow.project_runtime.types import Phase, PlanStatus


def intake_node(state: ProjectThreadState) -> dict:
    defaults = make_project_thread_state_defaults()
    defaults["phase"] = Phase.INTAKE.value
    defaults["messages"] = state.get("messages", [])
    return defaults


def discovery_node(state: ProjectThreadState) -> dict:
    return {"phase": Phase.DISCOVERY.value}


def planning_node(state: ProjectThreadState) -> dict:
    return {
        "phase": Phase.AWAITING_APPROVAL.value,
        "plan_status": PlanStatus.AWAITING_APPROVAL.value,
    }


def awaiting_approval_node(state: ProjectThreadState) -> dict:
    return {}


def build_node(state: ProjectThreadState) -> dict:
    return {"phase": Phase.QA_GATE.value}


def qa_gate_node(state: ProjectThreadState) -> dict:
    return {}


def delivery_node(state: ProjectThreadState) -> dict:
    return {"phase": Phase.DONE.value}


def done_node(state: ProjectThreadState) -> dict:
    return {"phase": Phase.DONE.value}


def route_after_awaiting_approval(
    state: ProjectThreadState,
) -> Literal["build", "planning", "done", "awaiting_approval"]:
    phase = state.get("phase")
    if phase == Phase.BUILD.value:
        return "build"
    if phase == Phase.PLANNING.value:
        return "planning"
    if phase == Phase.DONE.value:
        return "done"
    return "awaiting_approval"


def route_after_qa_gate(state: ProjectThreadState) -> Literal["delivery", "planning", "qa_gate"]:
    phase = state.get("phase")
    if phase == Phase.DELIVERY.value:
        return "delivery"
    if phase == Phase.PLANNING.value:
        return "planning"
    return "qa_gate"


def make_project_team_agent(*, checkpointer=None):
    graph = StateGraph(ProjectThreadState)
    graph.add_node("intake", intake_node)
    graph.add_node("discovery", discovery_node)
    graph.add_node("planning", planning_node)
    graph.add_node("awaiting_approval", awaiting_approval_node)
    graph.add_node("build", build_node)
    graph.add_node("qa_gate", qa_gate_node)
    graph.add_node("delivery", delivery_node)
    graph.add_node("done", done_node)

    graph.add_edge(START, "intake")
    graph.add_edge("intake", "discovery")
    graph.add_edge("discovery", "planning")
    graph.add_edge("planning", "awaiting_approval")
    graph.add_conditional_edges(
        "awaiting_approval",
        route_after_awaiting_approval,
        {
            "build": "build",
            "planning": "planning",
            "done": "done",
            "awaiting_approval": "awaiting_approval",
        },
    )
    graph.add_edge("build", "qa_gate")
    graph.add_conditional_edges(
        "qa_gate",
        route_after_qa_gate,
        {
            "delivery": "delivery",
            "planning": "planning",
            "qa_gate": "qa_gate",
        },
    )
    graph.add_edge("delivery", "done")
    graph.add_edge("done", END)

    return graph.compile(checkpointer=checkpointer)

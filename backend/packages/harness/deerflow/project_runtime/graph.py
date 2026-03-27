from typing import Literal

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from deerflow.project_runtime.state import ProjectThreadState, make_project_thread_state_defaults
from deerflow.project_runtime.types import Phase, PlanStatus, QAGateResult

GraphNode = Literal[
    "intake",
    "discovery",
    "planning",
    "awaiting_approval",
    "build",
    "qa_gate",
    "delivery",
    "done",
]


def intake_node(state: ProjectThreadState) -> dict:
    defaults = make_project_thread_state_defaults()
    defaults["phase"] = Phase.INTAKE.value
    defaults["messages"] = state.get("messages", [])
    return defaults


def discovery_node(state: ProjectThreadState) -> dict:
    return {"phase": Phase.DISCOVERY.value}


def planning_node(state: ProjectThreadState) -> dict:
    return {
        "phase": Phase.PLANNING.value,
        "plan_status": PlanStatus.AWAITING_APPROVAL.value,
    }


def awaiting_approval_node(state: ProjectThreadState) -> dict | Command:
    transition = resolve_approval_transition(state)
    if transition == END:
        return Command(
            update={
                "phase": Phase.AWAITING_APPROVAL.value,
                "plan_status": PlanStatus.AWAITING_APPROVAL.value,
            },
            goto=END,
        )
    if transition == "build":
        return Command(update={"phase": Phase.BUILD.value}, goto="build")
    if transition == "planning":
        return Command(update={"phase": Phase.PLANNING.value}, goto="planning")
    return Command(update={"phase": Phase.DONE.value}, goto="done")


def build_node(state: ProjectThreadState) -> dict:
    return {"phase": Phase.BUILD.value}


def qa_gate_node(state: ProjectThreadState) -> dict | Command:
    transition = resolve_qa_transition(state)
    if transition == END:
        return Command(update={"phase": Phase.QA_GATE.value}, goto=END)
    if transition == "delivery":
        return Command(update={"phase": Phase.DELIVERY.value}, goto="delivery")
    return Command(update={"phase": Phase.PLANNING.value}, goto="planning")


def delivery_node(state: ProjectThreadState) -> dict:
    return {"phase": Phase.DELIVERY.value}


def done_node(state: ProjectThreadState) -> dict:
    return {"phase": Phase.DONE.value}


def route_from_phase(state: ProjectThreadState) -> GraphNode:
    phase = state.get("phase", Phase.INTAKE.value)
    if phase == Phase.DISCOVERY.value:
        return "discovery"
    if phase == Phase.PLANNING.value:
        return "planning"
    if phase == Phase.AWAITING_APPROVAL.value:
        return "awaiting_approval"
    if phase == Phase.BUILD.value:
        return "build"
    if phase == Phase.QA_GATE.value:
        return "qa_gate"
    if phase == Phase.DELIVERY.value:
        return "delivery"
    if phase == Phase.DONE.value:
        return "done"
    return "intake"


def resolve_approval_transition(state: ProjectThreadState) -> Literal["build", "planning", "done", "__end__"]:
    plan_status = state.get("plan_status")
    if plan_status == PlanStatus.APPROVED.value:
        return "build"
    if plan_status == PlanStatus.NEEDS_REVISION.value:
        return "planning"
    if state.get("phase") == Phase.DONE.value:
        return "done"
    return END


def resolve_qa_transition(state: ProjectThreadState) -> Literal["delivery", "planning", "__end__"]:
    qa_gate = state.get("qa_gate") or {}
    result = qa_gate.get("result")
    if result == QAGateResult.PASS.value:
        return "delivery"
    if result == QAGateResult.FAIL.value:
        return "planning"
    return END


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

    graph.add_conditional_edges(
        START,
        route_from_phase,
        {
            "intake": "intake",
            "discovery": "discovery",
            "planning": "planning",
            "awaiting_approval": "awaiting_approval",
            "build": "build",
            "qa_gate": "qa_gate",
            "delivery": "delivery",
            "done": "done",
        },
    )
    graph.add_edge("intake", "discovery")
    graph.add_edge("discovery", "planning")
    graph.add_edge("planning", "awaiting_approval")
    graph.add_edge("build", "qa_gate")
    graph.add_edge("delivery", "done")
    graph.add_edge("done", END)

    return graph.compile(checkpointer=checkpointer)

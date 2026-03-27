from typing import Literal

from langgraph.config import get_config
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from langgraph.types import Command

from deerflow.project_runtime.approval import resolve_approval_update
from deerflow.project_runtime.dispatcher import dispatch_build_phase
from deerflow.project_runtime.planning import run_discovery, run_planning
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
    return run_discovery(state)


def planning_node(state: ProjectThreadState) -> dict:
    return run_planning(state)


def awaiting_approval_node(state: ProjectThreadState) -> dict | Command:
    transition = resolve_approval_update(state)
    if transition["goto"] == END:
        return Command(
            update={
                "phase": Phase.AWAITING_APPROVAL.value,
                "plan_status": PlanStatus.AWAITING_APPROVAL.value,
            },
            goto=END,
        )
    if transition["goto"] == "build":
        return Command(update={"phase": Phase.BUILD.value, "plan_status": PlanStatus.APPROVED.value}, goto="build")
    if transition["goto"] == "planning":
        return Command(update={"phase": Phase.PLANNING.value, "plan_status": PlanStatus.NEEDS_REVISION.value}, goto="planning")
    return Command(update={"phase": Phase.DONE.value, "plan_status": transition["plan_status"]}, goto="done")


def _resolve_build_thread_id(runtime: Runtime | None = None) -> str:
    context = getattr(runtime, "context", None) or {}
    if isinstance(context, dict):
        thread_id = context.get("thread_id")
        if isinstance(thread_id, str) and thread_id:
            return thread_id

    configurable = get_config().get("configurable", {})
    thread_id = configurable.get("thread_id") if isinstance(configurable, dict) else None
    if isinstance(thread_id, str) and thread_id:
        return thread_id

    return "default"


def build_node(state: ProjectThreadState, runtime: Runtime | None = None) -> dict | Command:
    transition = dispatch_build_phase(state, thread_id=_resolve_build_thread_id(runtime))
    goto = transition.pop("goto", "qa_gate")
    if goto == "qa_gate":
        transition.pop("phase", None)
    return Command(update=transition, goto=goto)


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
    graph.add_edge("delivery", "done")
    graph.add_edge("done", END)

    return graph.compile(checkpointer=checkpointer)

from langchain_core.messages import HumanMessage

from deerflow.project_runtime.approval import parse_approval_intent
from deerflow.project_runtime.graph import awaiting_approval_node
from deerflow.project_runtime.types import Phase, PlanStatus


def test_parse_approval_intent_accepts_only_explicit_approve_command():
    assert parse_approval_intent([HumanMessage(content="/approve")]) == "approve"
    assert parse_approval_intent([HumanMessage(content="go ahead")]) == "ambiguous"


def test_parse_approval_intent_treats_natural_language_revision_as_revise():
    assert parse_approval_intent([HumanMessage(content="split backend and QA into separate work orders")]) == "revise"


def test_parse_approval_intent_handles_cancel_command():
    assert parse_approval_intent([HumanMessage(content="/cancel")]) == "cancel"


def test_awaiting_approval_node_routes_approve_to_build():
    result = awaiting_approval_node(
        {
            "phase": Phase.AWAITING_APPROVAL.value,
            "plan_status": PlanStatus.AWAITING_APPROVAL.value,
            "messages": [HumanMessage(content="/approve")],
        }
    )

    assert result.goto == "build"
    assert result.update["plan_status"] == PlanStatus.APPROVED.value


def test_awaiting_approval_node_routes_revise_to_planning():
    result = awaiting_approval_node(
        {
            "phase": Phase.AWAITING_APPROVAL.value,
            "plan_status": PlanStatus.AWAITING_APPROVAL.value,
            "messages": [HumanMessage(content="/revise tighten the acceptance checks")],
        }
    )

    assert result.goto == "planning"
    assert result.update["plan_status"] == PlanStatus.NEEDS_REVISION.value


def test_awaiting_approval_node_routes_cancel_to_done():
    result = awaiting_approval_node(
        {
            "phase": Phase.AWAITING_APPROVAL.value,
            "plan_status": PlanStatus.AWAITING_APPROVAL.value,
            "messages": [HumanMessage(content="/cancel")],
        }
    )

    assert result.goto == "done"
    assert result.update["phase"] == Phase.DONE.value


def test_awaiting_approval_node_keeps_ambiguous_reply_paused():
    result = awaiting_approval_node(
        {
            "phase": Phase.AWAITING_APPROVAL.value,
            "plan_status": PlanStatus.AWAITING_APPROVAL.value,
            "messages": [HumanMessage(content="looks good")],
        }
    )

    assert result.goto == "__end__"
    assert result.update["phase"] == Phase.AWAITING_APPROVAL.value

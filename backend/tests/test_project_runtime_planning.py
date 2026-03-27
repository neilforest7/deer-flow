from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

from deerflow.project_runtime import (
    PlanningOutput,
    Phase,
    build_discovery_result,
    build_planning_result,
    compile_project_team_agent,
    make_project_team_agent,
    synthesize_project_brief,
    synthesize_work_orders,
    validate_planning_output,
)
from deerflow.project_runtime.types import WorkOrderStatus


def test_discovery_synthesizes_canonical_project_brief():
    brief = synthesize_project_brief(
        {"messages": [HumanMessage(content="Implement backend runtime approval flow")]}
    )

    assert brief.objective == "Implement backend runtime approval flow"
    assert "backend runtime" in brief.scope
    assert "Keep lead_agent behavior unchanged" in brief.constraints


def test_planning_synthesizes_canonical_work_orders_from_user_request():
    work_orders = synthesize_work_orders(
        {"messages": [HumanMessage(content="Implement backend runtime approval flow")]}
    )

    assert len(work_orders) == 1
    assert work_orders[0].owner_agent == "backend-agent"
    assert work_orders[0].acceptance_checks


def test_planning_matches_owner_keywords_on_tokens_instead_of_substrings():
    work_orders = synthesize_work_orders(
        {"messages": [HumanMessage(content="Build backend API")]}
    )

    assert [work_order.owner_agent for work_order in work_orders] == ["backend-agent"]


def test_planning_matches_frontend_owner_for_standalone_ui_token():
    work_orders = synthesize_work_orders(
        {"messages": [HumanMessage(content="Update UI for auth flow")]}
    )

    assert [work_order.owner_agent for work_order in work_orders] == ["frontend-agent"]


def test_planning_matches_multiple_owners_for_tokenized_request():
    work_orders = synthesize_work_orders(
        {"messages": [HumanMessage(content="backend API + UI integration")]}
    )

    assert [work_order.owner_agent for work_order in work_orders] == [
        "frontend-agent",
        "integration-agent",
        "backend-agent",
    ]


def test_planning_keeps_frontend_only_docker_requests_scoped_to_frontend_agent():
    work_orders = synthesize_work_orders(
        {
            "messages": [
                HumanMessage(
                    content=(
                        "write a env file generator with web ui. it is deployed by docker. frontend is on web. "
                        "user can toggle the variables on and off, and fill in key value of variables. once done, "
                        "user click download and a .env file is generated and downloaded to user. default template "
                        "is for deer-flow env."
                    )
                )
            ]
        }
    )

    assert [work_order.owner_agent for work_order in work_orders] == ["frontend-agent"]


def test_planning_still_assigns_devops_for_backend_docker_requests():
    work_orders = synthesize_work_orders(
        {"messages": [HumanMessage(content="Implement backend API deployed by docker")]}
    )

    assert [work_order.owner_agent for work_order in work_orders] == ["devops-agent", "backend-agent"]


def test_discovery_scope_does_not_treat_build_as_ui():
    brief = synthesize_project_brief(
        {"messages": [HumanMessage(content="Build backend API")]}
    )

    assert brief.scope == ["backend runtime"]


def test_validate_planning_output_rejects_unknown_dependencies():
    payload = {
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
                "read_scope": [],
                "write_scope": [],
                "dependencies": ["wo-2"],
                "acceptance_checks": ["pytest"],
            }
        ],
    }

    try:
        validate_planning_output(payload)
    except ValueError as exc:
        assert "unknown dependencies" in str(exc)
    else:
        raise AssertionError("Expected validate_planning_output() to reject unknown dependencies")


def test_validate_planning_output_rejects_self_dependencies():
    payload = {
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
                "read_scope": [],
                "write_scope": [],
                "dependencies": ["wo-1"],
                "acceptance_checks": ["pytest"],
            }
        ],
    }

    try:
        validate_planning_output(payload)
    except ValueError as exc:
        assert "cannot depend on itself" in str(exc)
    else:
        raise AssertionError("Expected validate_planning_output() to reject self dependencies")


def test_validate_planning_output_rejects_empty_acceptance_checks():
    payload = {
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
                "read_scope": [],
                "write_scope": [],
                "dependencies": [],
                "acceptance_checks": [],
            }
        ],
    }

    try:
        validate_planning_output(payload)
    except Exception as exc:
        assert "acceptance_checks" in str(exc)
    else:
        raise AssertionError("Expected validate_planning_output() to reject empty acceptance checks")


def test_validate_planning_output_rejects_non_build_owner_agents():
    payload = {
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
                "owner_agent": "planner-agent",
                "title": "Invalid owner",
                "goal": "Implement backend runtime approval flow",
                "read_scope": [],
                "write_scope": [],
                "dependencies": [],
                "acceptance_checks": ["pytest"],
            }
        ],
    }

    try:
        validate_planning_output(payload)
    except ValueError as exc:
        assert "invalid owner_agent" in str(exc)
        assert "planner-agent" in str(exc)
    else:
        raise AssertionError("Expected validate_planning_output() to reject non-build owner agents")


def test_build_planning_result_replans_failed_qa_work_orders_and_clears_stale_state():
    result = build_planning_result(
        {
            "project_brief": {
                "objective": "Ship runtime",
                "scope": ["backend runtime"],
                "constraints": ["keep lead_agent unchanged"],
                "deliverables": ["runtime"],
                "success_criteria": ["tests pass"],
            },
            "work_orders": [
                {
                    "id": "wo-1",
                    "owner_agent": "backend-agent",
                    "title": "Backend work",
                    "goal": "Ship runtime",
                    "read_scope": ["backend"],
                    "write_scope": ["backend"],
                    "dependencies": [],
                    "acceptance_checks": ["pytest"],
                    "status": WorkOrderStatus.COMPLETED.value,
                },
                {
                    "id": "wo-2",
                    "owner_agent": "frontend-agent",
                    "title": "Frontend work",
                    "goal": "Ship runtime UI",
                    "read_scope": ["frontend"],
                    "write_scope": ["frontend"],
                    "dependencies": ["wo-1"],
                    "acceptance_checks": ["test"],
                    "status": WorkOrderStatus.COMPLETED.value,
                },
            ],
            "qa_gate": {
                "result": "fail",
                "findings": ["Acceptance check failed for wo-1"],
                "required_rework": ["Rework wo-1 to satisfy acceptance check: pytest"],
            },
            "active_work_order_ids": ["wo-1"],
            "build_error": "old build error",
            "delivery_summary": {"summary": "stale"},
        }
    )

    assert result["phase"] == "planning"
    assert result["plan_status"] == "awaiting_approval"
    assert result["active_work_order_ids"] == []
    assert result["build_error"] is None
    assert result["qa_gate"] is None
    assert result["delivery_summary"] is None
    assert result["work_orders"][0]["id"] == "wo-1"
    assert result["work_orders"][0]["status"] == WorkOrderStatus.PENDING.value
    assert "QA rework: Rework wo-1 to satisfy acceptance check: pytest" in result["work_orders"][0]["goal"]
    assert result["work_orders"][1]["status"] == WorkOrderStatus.COMPLETED.value


def test_graph_reaches_awaiting_approval_with_validated_plan():
    graph = compile_project_team_agent(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "planning-thread"}, "recursion_limit": 20}

    result = graph.invoke({"messages": [HumanMessage(content="Implement backend runtime approval flow")]}, config=config)

    assert result["phase"] == Phase.AWAITING_APPROVAL.value
    assert result["project_brief"]["objective"] == "Implement backend runtime approval flow"
    assert result["work_orders"]
    PlanningOutput.model_validate(
        {
            "project_brief": result["project_brief"],
            "work_orders": result["work_orders"],
        }
    )


def test_discovery_and_planning_result_helpers_emit_canonical_payloads():
    state = {"messages": [HumanMessage(content="Implement backend runtime approval flow")]}

    discovery_update = build_discovery_result(state)
    planning_update = build_planning_result({**state, **discovery_update})

    assert discovery_update["phase"] == "discovery"
    assert planning_update["phase"] == "planning"
    assert planning_update["work_orders"]

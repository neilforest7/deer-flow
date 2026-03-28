from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from types import SimpleNamespace

import pytest

from deerflow.project_runtime import (
    PlanningOutput,
    Phase,
    build_discovery_result,
    build_planning_result,
    compile_project_team_agent,
    execute_discovery_phase,
    execute_planning_phase,
    make_project_team_agent,
    run_discovery,
    run_planning,
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


def test_execute_discovery_phase_merges_multiple_specialist_briefs():
    seen_trace_ids: list[str | None] = []
    seen_run_metadata: dict[str, dict] = {}

    class DiscoveryExecutor:
        def __init__(
            self,
            config,
            tools,
            parent_model=None,
            sandbox_state=None,
            thread_data=None,
            thread_id=None,
            trace_id=None,
            run_metadata=None,
        ):
            self.config = config
            seen_trace_ids.append(trace_id)
            seen_run_metadata[config.name] = dict(run_metadata or {})

        def execute(self, task):
            payloads = {
                "discovery-agent": {
                    "objective": "Ship runtime",
                    "scope": ["backend runtime"],
                    "constraints": ["Keep lead_agent behavior unchanged"],
                    "deliverables": ["Validated project brief"],
                    "success_criteria": ["Plan is clear"],
                },
                "architect-agent": {
                    "objective": "Ship runtime",
                    "scope": ["service boundaries"],
                    "constraints": ["Respect thread isolation"],
                    "deliverables": ["Architecture notes"],
                    "success_criteria": ["Dependencies mapped"],
                },
            }
            return SimpleNamespace(status="completed", result=str(payloads[self.config.name]).replace("'", '"'))

    brief, specialists, used_specialists = execute_discovery_phase(
        {
            "messages": [HumanMessage(content="Implement backend runtime approval flow")],
            "plan_status": "draft",
            "phase_attempts": {"discovery": 1},
        },
        thread_id="thread-1",
        trace_id="trace-root",
        available_tools=[SimpleNamespace(name="read_file"), SimpleNamespace(name="web_search")],
        executor_cls=DiscoveryExecutor,
    )

    assert used_specialists is True
    assert specialists == ["discovery-agent", "architect-agent"]
    assert seen_trace_ids == ["trace-root", "trace-root"]
    assert seen_run_metadata["discovery-agent"]["execution_kind"] == "discovery_specialist"
    assert seen_run_metadata["architect-agent"]["execution_kind"] == "discovery_specialist"
    assert seen_run_metadata["discovery-agent"]["work_order_id"] == "phase:discovery:discovery-agent:attempt:2"
    assert seen_run_metadata["architect-agent"]["work_order_id"] == "phase:discovery:architect-agent:attempt:2"
    assert "backend runtime" in brief.scope
    assert "service boundaries" in brief.scope


def test_execute_discovery_phase_scopes_design_agent_to_read_only_tools():
    seen_tools: dict[str, tuple[str, ...]] = {}

    class DiscoveryExecutor:
        def __init__(
            self,
            config,
            tools,
            parent_model=None,
            sandbox_state=None,
            thread_data=None,
            thread_id=None,
            trace_id=None,
            run_metadata=None,
        ):
            self.config = config
            seen_tools[config.name] = tuple(config.tools or [])

        def execute(self, task):
            payload = {
                "objective": "Ship runtime",
                "scope": ["frontend application"],
                "constraints": ["Keep lead_agent behavior unchanged"],
                "deliverables": ["Validated project brief"],
                "success_criteria": ["Plan is clear"],
            }
            return SimpleNamespace(status="completed", result=str(payload).replace("'", '"'))

    execute_discovery_phase(
        {"messages": [HumanMessage(content="Improve UI design for approval flow")]},
        thread_id="thread-1",
        available_tools=[
            SimpleNamespace(name="read_file"),
            SimpleNamespace(name="write_file"),
            SimpleNamespace(name="str_replace"),
            SimpleNamespace(name="web_search"),
            SimpleNamespace(name="image_search"),
            SimpleNamespace(name="view_image"),
            SimpleNamespace(name="tool_search"),
        ],
        executor_cls=DiscoveryExecutor,
    )

    assert seen_tools["design-agent"] == (
        "read_file",
        "web_search",
        "image_search",
        "view_image",
        "tool_search",
    )


def test_execute_planning_phase_validates_planner_output():
    seen_trace_ids: list[str | None] = []
    seen_run_metadata: list[dict] = []

    class PlannerExecutor:
        def __init__(
            self,
            config,
            tools,
            parent_model=None,
            sandbox_state=None,
            thread_data=None,
            thread_id=None,
            trace_id=None,
            run_metadata=None,
        ):
            self.config = config
            seen_trace_ids.append(trace_id)
            seen_run_metadata.append(dict(run_metadata or {}))

        def execute(self, task):
            payload = {
                "project_brief": {
                    "objective": "Ship runtime",
                    "scope": ["backend runtime"],
                    "constraints": ["Keep lead_agent behavior unchanged"],
                    "deliverables": ["Validated work orders"],
                    "success_criteria": ["Tests pass"],
                },
                "work_orders": [
                    {
                        "id": "wo-1",
                        "owner_agent": "backend-agent",
                        "title": "Backend implementation",
                        "goal": "Ship runtime",
                        "read_scope": ["backend/docs"],
                        "write_scope": ["backend/packages/harness/deerflow/project_runtime"],
                        "dependencies": [],
                        "acceptance_checks": ["pytest"],
                        "status": "pending",
                    }
                ],
            }
            return SimpleNamespace(status="completed", result=str(payload).replace("'", '"'))

    output = execute_planning_phase(
        {
            "project_brief": {
                "objective": "Ship runtime",
                "scope": ["backend runtime"],
                "constraints": ["Keep lead_agent behavior unchanged"],
                "deliverables": ["Validated work orders"],
                "success_criteria": ["Tests pass"],
            },
            "messages": [HumanMessage(content="Implement backend runtime approval flow")],
            "plan_status": "awaiting_approval",
            "phase_attempts": {"planning": 2},
        },
        thread_id="thread-1",
        trace_id="planning-trace",
        available_tools=[SimpleNamespace(name="read_file"), SimpleNamespace(name="web_search")],
        executor_cls=PlannerExecutor,
    )

    assert output.work_orders[0].owner_agent == "backend-agent"
    assert seen_trace_ids == ["planning-trace"]
    assert seen_run_metadata[0]["phase"] == "planning"
    assert seen_run_metadata[0]["execution_kind"] == "planning_specialist"
    assert seen_run_metadata[0]["owner_agent"] == "planner-agent"
    assert seen_run_metadata[0]["work_order_id"] == "phase:planning:planner-agent:attempt:3"


def test_run_discovery_falls_back_to_deterministic_when_specialist_execution_fails(monkeypatch):
    class FailingExecutor:
        def __init__(
            self,
            config,
            tools,
            parent_model=None,
            sandbox_state=None,
            thread_data=None,
            thread_id=None,
            trace_id=None,
            run_metadata=None,
        ):
            pass

        def execute(self, task):
            return SimpleNamespace(status="failed", error="boom")

    monkeypatch.setattr("deerflow.project_runtime.planning._deterministic_phase_fallback_allowed", lambda: True)

    result = run_discovery(
        {"messages": [HumanMessage(content="Implement backend runtime approval flow")]},
        thread_id="thread-1",
        available_tools=[SimpleNamespace(name="read_file")],
        executor_cls=FailingExecutor,
    )

    assert result["phase_artifacts"]["discovery"]["mode"] == "deterministic"
    assert result["project_brief"]["objective"] == "Implement backend runtime approval flow"


def test_run_planning_uses_specialist_output_when_enabled(monkeypatch):
    class PlannerExecutor:
        def __init__(
            self,
            config,
            tools,
            parent_model=None,
            sandbox_state=None,
            thread_data=None,
            thread_id=None,
            trace_id=None,
            run_metadata=None,
        ):
            self.config = config

        def execute(self, task):
            payload = {
                "project_brief": {
                    "objective": "Ship runtime",
                    "scope": ["backend runtime"],
                    "constraints": ["Keep lead_agent behavior unchanged"],
                    "deliverables": ["Validated work orders"],
                    "success_criteria": ["Tests pass"],
                },
                "work_orders": [
                    {
                        "id": "wo-1",
                        "owner_agent": "backend-agent",
                        "title": "Backend implementation",
                        "goal": "Ship runtime",
                        "read_scope": [],
                        "write_scope": [],
                        "dependencies": [],
                        "acceptance_checks": ["pytest"],
                        "status": "pending",
                    }
                ],
            }
            return SimpleNamespace(status="completed", result=str(payload).replace("'", '"'))

    monkeypatch.setattr("deerflow.project_runtime.planning._deterministic_phase_fallback_allowed", lambda: True)

    result = run_planning(
        {
            "project_brief": {
                "objective": "Ship runtime",
                "scope": ["backend runtime"],
                "constraints": ["Keep lead_agent behavior unchanged"],
                "deliverables": ["Validated work orders"],
                "success_criteria": ["Tests pass"],
            },
            "messages": [HumanMessage(content="Implement backend runtime approval flow")],
        },
        thread_id="thread-1",
        available_tools=[SimpleNamespace(name="read_file"), SimpleNamespace(name="web_search")],
        executor_cls=PlannerExecutor,
    )

    assert result["phase_artifacts"]["planning"]["mode"] == "specialist"
    assert result["work_orders"][0]["id"] == "wo-1"


def test_run_planning_falls_back_to_deterministic_when_specialist_fails(monkeypatch):
    class FailingExecutor:
        def __init__(
            self,
            config,
            tools,
            parent_model=None,
            sandbox_state=None,
            thread_data=None,
            thread_id=None,
            trace_id=None,
            run_metadata=None,
        ):
            pass

        def execute(self, task):
            return SimpleNamespace(status="failed", error="boom")

    monkeypatch.setattr("deerflow.project_runtime.planning._deterministic_phase_fallback_allowed", lambda: True)

    result = run_planning(
        {
            "project_brief": {
                "objective": "Ship runtime",
                "scope": ["backend runtime"],
                "constraints": ["Keep lead_agent behavior unchanged"],
                "deliverables": ["Validated work orders"],
                "success_criteria": ["Tests pass"],
            },
            "messages": [HumanMessage(content="Implement backend runtime approval flow")],
        },
        thread_id="thread-1",
        available_tools=[SimpleNamespace(name="read_file"), SimpleNamespace(name="web_search")],
        executor_cls=FailingExecutor,
    )

    assert result["phase_artifacts"]["planning"]["mode"] == "deterministic"
    assert result["work_orders"][0]["owner_agent"] == "backend-agent"


def test_run_planning_raises_when_specialist_fails_and_fallback_is_disabled(monkeypatch):
    class FailingExecutor:
        def __init__(
            self,
            config,
            tools,
            parent_model=None,
            sandbox_state=None,
            thread_data=None,
            thread_id=None,
            trace_id=None,
            run_metadata=None,
        ):
            pass

        def execute(self, task):
            return SimpleNamespace(status="failed", error="boom")

    monkeypatch.setattr("deerflow.project_runtime.planning._deterministic_phase_fallback_allowed", lambda: False)

    with pytest.raises(RuntimeError, match="boom"):
        run_planning(
            {
                "project_brief": {
                    "objective": "Ship runtime",
                    "scope": ["backend runtime"],
                    "constraints": ["Keep lead_agent behavior unchanged"],
                    "deliverables": ["Validated work orders"],
                    "success_criteria": ["Tests pass"],
                },
                "messages": [HumanMessage(content="Implement backend runtime approval flow")],
            },
            thread_id="thread-1",
            available_tools=[SimpleNamespace(name="read_file"), SimpleNamespace(name="web_search")],
            executor_cls=FailingExecutor,
        )


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


def test_make_project_team_agent_returns_graph_instance():
    graph = make_project_team_agent()

    assert graph is not None

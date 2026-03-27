from unittest.mock import MagicMock, patch

from langchain_core.messages import HumanMessage

from deerflow.client import DeerFlowClient, StreamEvent


def _mock_config():
    model = MagicMock()
    model.name = "test-model"
    model.model = "test-model"
    model.supports_thinking = False
    model.supports_reasoning_effort = False

    config = MagicMock()
    config.models = [model]
    config.project_runtime.acp_allowed_specialists = []
    config.project_runtime.default_model_name = None
    return config


def test_project_stream_targets_project_team_agent_runtime():
    with patch("deerflow.client.get_app_config", return_value=_mock_config()):
        client = DeerFlowClient()

    graph = MagicMock()
    graph.stream.return_value = iter([{"messages": [], "phase": "planning", "artifacts": []}])

    with patch("deerflow.project_runtime.graph.make_project_team_agent", return_value=graph):
        events = list(client.project_stream("hi", thread_id="thread-1"))

    assert events[-1].type == "end"
    config = graph.stream.call_args.kwargs["config"]
    assert config["configurable"]["runtime_name"] == "project_team_agent"


def test_project_chat_targets_project_team_agent_runtime():
    with patch("deerflow.client.get_app_config", return_value=_mock_config()):
        client = DeerFlowClient()

    with patch.object(client, "project_stream", return_value=iter([StreamEvent(type="messages-tuple", data={"type": "ai", "content": "done"}), StreamEvent(type="end", data={})])) as mock_stream:
        result = client.project_chat("ship it", thread_id="thread-1")

    assert result == "done"
    assert mock_stream.call_args.kwargs == {"thread_id": "thread-1"}


def test_project_stream_surfaces_project_runtime_values_and_synthesizes_ai_text():
    with patch("deerflow.client.get_app_config", return_value=_mock_config()):
        client = DeerFlowClient()

    graph = MagicMock()
    graph.stream.return_value = iter(
        [
            {
                "messages": [HumanMessage(content="ship it")],
                "phase": "planning",
                "plan_status": "awaiting_approval",
                "project_brief": {"objective": "Ship runtime"},
                "work_orders": [{"id": "wo-1", "title": "Implement runtime"}],
                "artifacts": [],
            }
        ]
    )

    with patch("deerflow.project_runtime.graph.make_project_team_agent", return_value=graph):
        events = list(client.project_stream("ship it", thread_id="thread-1"))

    values_event = next(event for event in events if event.type == "values")
    ai_event = next(event for event in events if event.type == "messages-tuple" and event.data.get("type") == "ai")
    assert values_event.data["phase"] == "planning"
    assert values_event.data["project_brief"] == {"objective": "Ship runtime"}
    assert values_event.data["work_orders"] == [{"id": "wo-1", "title": "Implement runtime"}]
    assert "\"objective\": \"Ship runtime\"" in ai_event.data["content"]


def test_project_chat_returns_synthesized_delivery_summary_when_runtime_emits_no_ai_messages():
    with patch("deerflow.client.get_app_config", return_value=_mock_config()):
        client = DeerFlowClient()

    graph = MagicMock()
    graph.stream.return_value = iter(
        [
            {
                "messages": [],
                "phase": "delivery",
                "delivery_summary": {"completed_work": [{"work_order_id": "wo-1", "summary": "done"}]},
                "artifacts": [],
            }
        ]
    )

    with patch("deerflow.project_runtime.graph.make_project_team_agent", return_value=graph):
        result = client.project_chat("ship it", thread_id="thread-1")

    assert "\"delivery_summary\"" in result
    assert "\"wo-1\"" in result


def test_project_runtime_uses_default_model_override_when_no_model_is_provided():
    config = _mock_config()
    config.project_runtime.default_model_name = "qa-model"
    with patch("deerflow.client.get_app_config", return_value=config):
        client = DeerFlowClient()

    runnable_config = client._get_runnable_config("thread-1", runtime_name="project_team_agent")

    assert runnable_config["configurable"]["model_name"] == "qa-model"


def test_ensure_agent_builds_project_team_runtime_without_touching_lead_agent_factory():
    with patch("deerflow.client.get_app_config", return_value=_mock_config()):
        client = DeerFlowClient()

    config = client._get_runnable_config("thread-1", runtime_name="project_team_agent")
    graph = MagicMock()

    with (
        patch("deerflow.project_runtime.graph.make_project_team_agent", return_value=graph) as mock_make_project,
        patch("deerflow.client.create_agent") as mock_create_agent,
    ):
        client._ensure_agent(config)

    assert client._agent is graph
    mock_make_project.assert_called_once()
    mock_create_agent.assert_not_called()

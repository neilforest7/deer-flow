"""Tests for built-in project delivery specialist subagents."""

from deerflow.subagents.registry import get_subagent_config, get_subagent_names


def test_project_delivery_specialists_are_registered():
    names = set(get_subagent_names())

    assert {
        "discovery-agent",
        "architect-agent",
        "planner-agent",
        "frontend-agent",
        "backend-agent",
        "integration-agent",
        "qa-agent",
        "delivery-agent",
    }.issubset(names)


def test_qa_agent_uses_validation_oriented_tools():
    qa_agent = get_subagent_config("qa-agent")

    assert qa_agent is not None
    assert qa_agent.tools == [
        "bash",
        "ls",
        "read_file",
        "view_image",
        "web_search",
        "web_fetch",
        "tool_search",
    ]
    assert "task" in qa_agent.disallowed_tools
    assert "present_files" in qa_agent.disallowed_tools

from types import SimpleNamespace

from deerflow.project_runtime import Phase
from deerflow.project_runtime.registry import (
    get_default_phase_owners,
    get_specialist_config,
    get_specialist_names,
    specialist_uses_acp_by_default,
    tool_names_for_specialist,
)


def test_specialist_roster_matches_prd():
    assert get_specialist_names() == (
        "discovery-agent",
        "architect-agent",
        "planner-agent",
        "design-agent",
        "frontend-agent",
        "backend-agent",
        "integration-agent",
        "devops-agent",
        "data-agent",
        "qa-agent",
        "delivery-agent",
        "general-purpose",
        "bash",
    )


def test_phase_owners_match_prd():
    assert get_default_phase_owners(Phase.DISCOVERY) == (
        "discovery-agent",
        "architect-agent",
        "design-agent",
    )
    assert get_default_phase_owners(Phase.PLANNING) == ("planner-agent",)
    assert get_default_phase_owners(Phase.BUILD) == (
        "frontend-agent",
        "backend-agent",
        "integration-agent",
        "devops-agent",
        "data-agent",
        "design-agent",
    )
    assert get_default_phase_owners(Phase.QA_GATE) == ("qa-agent",)
    assert get_default_phase_owners(Phase.DELIVERY) == ("delivery-agent",)


def test_fallback_specialists_are_not_default_phase_owners():
    owners = {owner for phase in Phase for owner in get_default_phase_owners(phase)}

    assert "general-purpose" not in owners
    assert "bash" not in owners


def test_acp_defaults_are_conservative():
    for specialist_name in get_specialist_names():
        assert specialist_uses_acp_by_default(specialist_name) is False


def test_task_is_always_filtered_out_of_runtime_tool_policy():
    available_tools = [
        SimpleNamespace(name="read_file"),
        SimpleNamespace(name="write_file"),
        SimpleNamespace(name="task"),
        SimpleNamespace(name="invoke_acp_agent"),
        SimpleNamespace(name="web_search"),
    ]

    planner_tools = tool_names_for_specialist("planner-agent", available_tools)
    frontend_tools = tool_names_for_specialist("frontend-agent", available_tools)

    assert planner_tools == ("read_file", "web_search")
    assert frontend_tools == ("read_file", "write_file", "web_search")


def test_delivery_agent_can_present_files_without_acp():
    available_tools = [
        SimpleNamespace(name="read_file"),
        SimpleNamespace(name="present_files"),
        SimpleNamespace(name="invoke_acp_agent"),
        SimpleNamespace(name="task"),
    ]

    assert tool_names_for_specialist("delivery-agent", available_tools) == (
        "read_file",
        "present_files",
    )


def test_design_agent_is_read_only_during_discovery():
    available_tools = [
        SimpleNamespace(name="read_file"),
        SimpleNamespace(name="write_file"),
        SimpleNamespace(name="str_replace"),
        SimpleNamespace(name="web_search"),
        SimpleNamespace(name="image_search"),
        SimpleNamespace(name="view_image"),
        SimpleNamespace(name="tool_search"),
        SimpleNamespace(name="task"),
    ]

    assert tool_names_for_specialist("design-agent", available_tools, phase=Phase.DISCOVERY) == (
        "read_file",
        "web_search",
        "image_search",
        "view_image",
        "tool_search",
    )


def test_design_agent_retains_write_tools_during_build():
    available_tools = [
        SimpleNamespace(name="read_file"),
        SimpleNamespace(name="write_file"),
        SimpleNamespace(name="str_replace"),
        SimpleNamespace(name="web_search"),
    ]

    assert tool_names_for_specialist("design-agent", available_tools, phase=Phase.BUILD) == (
        "read_file",
        "write_file",
        "str_replace",
        "web_search",
    )


def test_specialist_config_is_resolved_deterministically():
    config = get_specialist_config("backend-agent")

    assert config is not None
    assert config.name == "backend-agent"
    assert "task" in (config.disallowed_tools or [])
    assert config.max_turns == 100
    assert "stop immediately" in config.system_prompt.lower()

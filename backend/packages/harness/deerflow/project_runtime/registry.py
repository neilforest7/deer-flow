from dataclasses import replace
from typing import Protocol

from deerflow.config import get_app_config
from deerflow.project_runtime.types import Phase
from deerflow.subagents.builtins import BASH_AGENT_CONFIG, GENERAL_PURPOSE_CONFIG
from deerflow.subagents.config import SubagentConfig


class _NamedTool(Protocol):
    name: str


def _make_specialist(
    name: str,
    description: str,
    *,
    tools: list[str] | None = None,
    disallowed_tools: list[str] | None = None,
) -> SubagentConfig:
    return SubagentConfig(
        name=name,
        description=description,
        system_prompt=f"You are {name}. Execute only the scoped work assigned by the project runtime and report concise results.",
        tools=tools,
        disallowed_tools=disallowed_tools or ["task"],
    )


_SPECIALIST_CONFIGS: dict[str, SubagentConfig] = {
    "discovery-agent": _make_specialist(
        "discovery-agent",
        "Clarifies objective, scope, and constraints before planning.",
    ),
    "architect-agent": _make_specialist(
        "architect-agent",
        "Translates product goals into technical architecture and delivery boundaries.",
    ),
    "planner-agent": _make_specialist(
        "planner-agent",
        "Owns canonical work-order planning for the project runtime.",
    ),
    "design-agent": _make_specialist(
        "design-agent",
        "Owns design system, UX, and UI implementation work orders.",
    ),
    "frontend-agent": _make_specialist(
        "frontend-agent",
        "Implements frontend behavior and presentation changes.",
    ),
    "backend-agent": _make_specialist(
        "backend-agent",
        "Implements backend runtime, API, and service changes.",
    ),
    "integration-agent": _make_specialist(
        "integration-agent",
        "Implements cross-system integration and contract alignment work.",
    ),
    "devops-agent": _make_specialist(
        "devops-agent",
        "Implements infrastructure, CI, and deployment changes.",
    ),
    "data-agent": _make_specialist(
        "data-agent",
        "Implements schema, storage, and data-processing changes.",
    ),
    "qa-agent": _make_specialist(
        "qa-agent",
        "Owns QA gate verification and rework findings.",
    ),
    "delivery-agent": _make_specialist(
        "delivery-agent",
        "Packages delivery summaries, artifacts, and follow-up notes.",
    ),
    "general-purpose": replace(GENERAL_PURPOSE_CONFIG),
    "bash": replace(BASH_AGENT_CONFIG),
}

_PHASE_OWNERS: dict[Phase, tuple[str, ...]] = {
    Phase.INTAKE: (),
    Phase.DISCOVERY: ("discovery-agent", "architect-agent", "design-agent"),
    Phase.PLANNING: ("planner-agent",),
    Phase.AWAITING_APPROVAL: (),
    Phase.BUILD: (
        "frontend-agent",
        "backend-agent",
        "integration-agent",
        "devops-agent",
        "data-agent",
        "design-agent",
    ),
    Phase.QA_GATE: ("qa-agent",),
    Phase.DELIVERY: ("delivery-agent",),
    Phase.DONE: (),
}

_TOOL_POLICIES: dict[str, frozenset[str]] = {
    "discovery-agent": frozenset({"ls", "read_file", "web_search", "web_fetch", "image_search", "view_image", "tool_search"}),
    "architect-agent": frozenset({"ls", "read_file", "web_search", "web_fetch", "tool_search"}),
    "planner-agent": frozenset({"ls", "read_file", "web_search", "web_fetch", "tool_search"}),
    "design-agent": frozenset({"ls", "read_file", "write_file", "str_replace", "web_search", "web_fetch", "image_search", "view_image", "tool_search"}),
    "frontend-agent": frozenset({"ls", "read_file", "write_file", "str_replace", "bash", "web_search", "web_fetch", "view_image", "tool_search"}),
    "backend-agent": frozenset({"ls", "read_file", "write_file", "str_replace", "bash", "web_search", "web_fetch", "tool_search"}),
    "integration-agent": frozenset({"ls", "read_file", "write_file", "str_replace", "bash", "web_search", "web_fetch", "tool_search"}),
    "devops-agent": frozenset({"ls", "read_file", "write_file", "str_replace", "bash", "tool_search"}),
    "data-agent": frozenset({"ls", "read_file", "write_file", "str_replace", "bash", "web_search", "web_fetch", "tool_search"}),
    "qa-agent": frozenset({"ls", "read_file", "bash", "web_search", "web_fetch", "tool_search"}),
    "delivery-agent": frozenset({"ls", "read_file", "present_files"}),
    "general-purpose": frozenset(),
    "bash": frozenset({"bash", "ls", "read_file", "write_file", "str_replace"}),
}

_TASK_TOOL_NAME = "task"
_ACP_TOOL_NAME = "invoke_acp_agent"


def get_specialist_names() -> tuple[str, ...]:
    return tuple(_SPECIALIST_CONFIGS.keys())


def get_specialist_config(name: str) -> SubagentConfig | None:
    config = _SPECIALIST_CONFIGS.get(name)
    if config is None:
        return None
    return replace(config)


def get_default_phase_owners(phase: Phase) -> tuple[str, ...]:
    return _PHASE_OWNERS[phase]


def specialist_uses_acp_by_default(name: str) -> bool:
    try:
        app_config = get_app_config()
    except FileNotFoundError:
        return False
    project_runtime = getattr(app_config, "project_runtime", None)
    allowed = getattr(project_runtime, "acp_allowed_specialists", [])
    return name in allowed


def tool_names_for_specialist(
    specialist_name: str,
    available_tools: list[_NamedTool],
    *,
    acp_enabled: bool = False,
) -> tuple[str, ...]:
    allowed = _TOOL_POLICIES[specialist_name]
    resolved: list[str] = []

    for tool in available_tools:
        tool_name = tool.name
        if tool_name == _TASK_TOOL_NAME:
            continue
        if tool_name == _ACP_TOOL_NAME and not (acp_enabled and specialist_uses_acp_by_default(specialist_name)):
            continue
        if allowed and tool_name not in allowed:
            continue
        resolved.append(tool_name)

    return tuple(resolved)

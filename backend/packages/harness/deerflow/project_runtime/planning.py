from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage

from deerflow.project_runtime.prompts import build_discovery_prompt, build_planning_prompt
from deerflow.project_runtime.types import PlanStatus, PlanningOutput, ProjectBrief, WorkOrder

_DEFAULT_CONSTRAINTS = [
    "Keep lead_agent behavior unchanged",
    "Require explicit /approve before build",
]
_DEFAULT_DELIVERABLES = [
    "Validated project brief",
    "Validated work orders",
]
_DEFAULT_SUCCESS_CRITERIA = [
    "Project runtime pauses in awaiting_approval with canonical state",
]
_AGENT_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("design-agent", "design"),
    ("design-agent", "ux"),
    ("frontend-agent", "frontend"),
    ("frontend-agent", "ui"),
    ("integration-agent", "integration"),
    ("integration-agent", "contract"),
    ("devops-agent", "deploy"),
    ("devops-agent", "ci"),
    ("devops-agent", "docker"),
    ("data-agent", "data"),
    ("data-agent", "database"),
    ("data-agent", "schema"),
    ("backend-agent", "backend"),
    ("backend-agent", "runtime"),
    ("backend-agent", "api"),
    ("backend-agent", "service"),
)
_WRITE_SCOPE_BY_AGENT = {
    "design-agent": ["frontend"],
    "frontend-agent": ["frontend"],
    "integration-agent": ["backend", "frontend"],
    "devops-agent": [".github", "backend"],
    "data-agent": ["backend"],
    "backend-agent": ["backend/packages/harness/deerflow/project_runtime"],
}
_READ_SCOPE_BY_AGENT = {
    "design-agent": ["frontend", "backend/docs"],
    "frontend-agent": ["frontend", "backend/docs"],
    "integration-agent": ["backend", "frontend"],
    "devops-agent": ["backend", ".github"],
    "data-agent": ["backend"],
    "backend-agent": ["backend/docs", "backend/packages/harness/deerflow/project_runtime"],
}
_ACCEPTANCE_CHECK_BY_AGENT = {
    "design-agent": "Review UX and visual consistency for requested changes",
    "frontend-agent": "Run relevant frontend checks for the touched area",
    "integration-agent": "Verify cross-system contract compatibility for the changed path",
    "devops-agent": "Validate CI or deployment changes in the affected workflow",
    "data-agent": "Validate schema and data compatibility for the changed path",
    "backend-agent": "PYTHONPATH=. uv run pytest tests/test_project_runtime_graph.py -q",
}


def _extract_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
                continue
            if isinstance(block, Mapping):
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(part for part in parts if part)
    return str(content) if content is not None else ""


def _message_role(message: Any) -> str | None:
    if isinstance(message, HumanMessage):
        return "human"
    if isinstance(message, BaseMessage):
        return getattr(message, "type", None)
    if isinstance(message, Mapping):
        role = message.get("type") or message.get("role")
        return role if isinstance(role, str) else None
    return None


def _message_text(message: Any) -> str:
    if isinstance(message, BaseMessage):
        return _extract_text(message.content)
    if isinstance(message, Mapping):
        return _extract_text(message.get("content"))
    return ""


def get_latest_user_message_text(state: Mapping[str, Any]) -> str:
    messages = state.get("messages") or []
    for message in reversed(messages):
        if _message_role(message) in {"human", "user"}:
            return _message_text(message).strip()
    return ""


def validate_project_brief(payload: ProjectBrief | Mapping[str, Any]) -> ProjectBrief:
    return ProjectBrief.model_validate(payload)


def validate_planning_output(payload: PlanningOutput | Mapping[str, Any]) -> PlanningOutput:
    output = PlanningOutput.model_validate(payload)
    seen_ids: set[str] = set()
    work_order_ids = {work_order.id for work_order in output.work_orders}

    for work_order in output.work_orders:
        if work_order.id in seen_ids:
            raise ValueError(f"Duplicate work order id: {work_order.id}")
        seen_ids.add(work_order.id)
        if work_order.id in work_order.dependencies:
            raise ValueError(f"Work order {work_order.id} cannot depend on itself")
        missing_dependencies = [dependency for dependency in work_order.dependencies if dependency not in work_order_ids]
        if missing_dependencies:
            raise ValueError(
                f"Work order {work_order.id} has unknown dependencies: {', '.join(missing_dependencies)}"
            )

    return output


def _request_tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def synthesize_project_brief(state: Mapping[str, Any]) -> ProjectBrief:
    latest_request = get_latest_user_message_text(state)
    prompt = build_discovery_prompt(
        latest_user_request=latest_request,
        existing_brief=state.get("project_brief") if isinstance(state.get("project_brief"), Mapping) else None,
    )
    objective = latest_request or "Clarify project requirements for the project runtime"
    scope = [latest_request] if latest_request else ["Clarify project requirements"]
    scope = _derive_scope(latest_request)
    brief_payload = {
        "objective": objective,
        "scope": scope,
        "constraints": [*(_DEFAULT_CONSTRAINTS), f"Discovery prompt prepared with {len(prompt)} characters"],
        "deliverables": list(_DEFAULT_DELIVERABLES),
        "success_criteria": list(_DEFAULT_SUCCESS_CRITERIA),
    }
    return validate_project_brief(brief_payload)


def _derive_scope(latest_request: str) -> list[str]:
    tokens = _request_tokens(latest_request)
    scope: list[str] = []
    if {"backend", "runtime"} & tokens:
        scope.append("backend runtime")
    if {"frontend", "ui"} & tokens:
        scope.append("frontend application")
    if {"qa", "test"} & tokens:
        scope.append("verification")
    if not scope:
        scope.append(latest_request or "Clarify project requirements")
    return scope


def _infer_owner_agents(latest_request: str) -> list[str]:
    tokens = _request_tokens(latest_request)
    owners: list[str] = []
    for owner_agent, keyword in _AGENT_KEYWORDS:
        if keyword in tokens and owner_agent not in owners:
            owners.append(owner_agent)
    if not owners and latest_request:
        owners.append("backend-agent")
    return owners


def synthesize_work_orders(
    state: Mapping[str, Any],
    *,
    project_brief: ProjectBrief | Mapping[str, Any] | None = None,
) -> list[WorkOrder]:
    validated_brief = validate_project_brief(project_brief or synthesize_project_brief(state))
    latest_request = get_latest_user_message_text(state)
    prompt = build_planning_prompt(
        project_brief=validated_brief.model_dump(mode="json"),
        latest_user_request=latest_request,
    )
    owner_agents = _infer_owner_agents(latest_request)
    work_orders: list[WorkOrder] = []

    for index, owner_agent in enumerate(owner_agents, start=1):
        work_orders.append(
            WorkOrder(
                id=f"wo-{index}",
                owner_agent=owner_agent,
                title=f"{owner_agent} implementation",
                goal=validated_brief.objective,
                read_scope=list(_READ_SCOPE_BY_AGENT.get(owner_agent, [])),
                write_scope=list(_WRITE_SCOPE_BY_AGENT.get(owner_agent, [])),
                dependencies=[],
                acceptance_checks=[
                    _ACCEPTANCE_CHECK_BY_AGENT.get(owner_agent, "Run the targeted checks relevant to this work order"),
                    f"Planning prompt prepared with {len(prompt)} characters",
                ],
            )
        )

    return work_orders


def build_discovery_result(state: Mapping[str, Any]) -> dict[str, Any]:
    project_brief = synthesize_project_brief(state)
    return {
        "phase": "discovery",
        "project_brief": project_brief.model_dump(mode="json"),
    }


def build_planning_result(state: Mapping[str, Any]) -> dict[str, Any]:
    project_brief = validate_project_brief(state.get("project_brief") or synthesize_project_brief(state))
    planning_output = validate_planning_output(
        {
            "project_brief": project_brief.model_dump(mode="json"),
            "work_orders": [work_order.model_dump(mode="json") for work_order in synthesize_work_orders(state, project_brief=project_brief)],
        }
    )
    return {
        "phase": "planning",
        "project_brief": planning_output.project_brief.model_dump(mode="json"),
        "work_orders": [work_order.model_dump(mode="json") for work_order in planning_output.work_orders],
        "plan_status": PlanStatus.AWAITING_APPROVAL.value,
    }


def run_discovery(state: Mapping[str, Any]) -> dict[str, Any]:
    return build_discovery_result(state)


def run_planning(state: Mapping[str, Any]) -> dict[str, Any]:
    return build_planning_result(state)


def run_discovery(state: Mapping[str, Any]) -> dict[str, Any]:
    return build_discovery_result(state)


def run_planning(state: Mapping[str, Any]) -> dict[str, Any]:
    return build_planning_result(state)


def synthesize_planning_output(
    project_brief: ProjectBrief | Mapping[str, Any],
    *,
    latest_user_request: str = "",
) -> PlanningOutput:
    validated_brief = validate_project_brief(project_brief)
    planning_output = {
        "project_brief": validated_brief.model_dump(mode="json"),
        "work_orders": [
            work_order.model_dump(mode="json")
            for work_order in synthesize_work_orders({"messages": [{"type": "human", "content": latest_user_request}]}, project_brief=validated_brief)
        ],
    }
    return validate_planning_output(planning_output)

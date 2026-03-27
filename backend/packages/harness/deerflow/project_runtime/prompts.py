from __future__ import annotations

import json
from typing import Any


def build_discovery_prompt(*, latest_user_request: str, existing_brief: dict[str, Any] | None = None) -> str:
    payload = {
        "latest_user_request": latest_user_request,
        "existing_brief": existing_brief,
        "required_schema": {
            "objective": "string",
            "scope": ["string"],
            "constraints": ["string"],
            "deliverables": ["string"],
            "success_criteria": ["string"],
        },
    }
    return "\n".join(
        [
            "Synthesize a canonical ProjectBrief for the project runtime.",
            "Return JSON only.",
            json.dumps(payload, ensure_ascii=True, indent=2),
        ]
    )


def build_delivery_prompt(
    *,
    project_brief: dict[str, Any] | None,
    work_orders: list[dict[str, Any]],
    agent_reports: list[dict[str, Any]],
    qa_gate: dict[str, Any] | None,
    artifacts: list[str],
) -> str:
    payload = {
        "project_brief": project_brief,
        "work_orders": work_orders,
        "agent_reports": agent_reports,
        "qa_gate": qa_gate,
        "artifacts": artifacts,
        "required_schema": {
            "completed_work": [
                {
                    "work_order_id": "string",
                    "title": "string",
                    "summary": "string",
                }
            ],
            "artifacts": ["string"],
            "verification": ["string"],
            "follow_ups": ["string"],
        },
    }
    return "\n".join(
        [
            "Create a canonical delivery summary for the project runtime.",
            "Return JSON only.",
            json.dumps(payload, ensure_ascii=True, indent=2),
        ]
    )


def build_planning_prompt(
    *,
    project_brief: dict[str, Any],
    latest_user_request: str,
    allowed_owner_agents: list[str] | tuple[str, ...],
) -> str:
    payload = {
        "project_brief": project_brief,
        "latest_user_request": latest_user_request,
        "allowed_owner_agents": list(allowed_owner_agents),
        "required_schema": {
            "project_brief": "ProjectBrief",
            "work_orders": [
                {
                    "id": "string",
                    "owner_agent": "one of allowed_owner_agents",
                    "title": "string",
                    "goal": "string",
                    "read_scope": ["string"],
                    "write_scope": ["string"],
                    "dependencies": ["string"],
                    "acceptance_checks": ["string"],
                    "status": "pending|ready|active|completed|failed|blocked|cancelled",
                }
            ],
        },
    }
    return "\n".join(
        [
            "Create canonical WorkOrder records for the project runtime.",
            "Return JSON only.",
            json.dumps(payload, ensure_ascii=True, indent=2),
        ]
    )

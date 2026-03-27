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


def build_planning_prompt(*, project_brief: dict[str, Any], latest_user_request: str) -> str:
    payload = {
        "project_brief": project_brief,
        "latest_user_request": latest_user_request,
        "required_schema": {
            "project_brief": "ProjectBrief",
            "work_orders": [
                {
                    "id": "string",
                    "owner_agent": "string",
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

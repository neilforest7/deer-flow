"""Repositories backed by LangGraph BaseStore."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from langgraph.store.base import BaseStore

from deerflow.subagents.builtins.project_delivery import PROJECT_DELIVERY_SPECIALIST_SUMMARIES

DEFAULT_PROJECT_TEAM_NAME = "software-delivery-default"
MEMORY_GLOBAL_NAMESPACE = ("memory", "global")
MEMORY_AGENT_NAMESPACE = ("memory", "agents")
PROJECT_INDEX_NAMESPACE = ("projects", "index")
PROJECT_SNAPSHOT_NAMESPACE = ("projects", "snapshots")
PROJECT_CONTROL_NAMESPACE = ("projects", "controls")
PROJECT_TEAM_NAMESPACE = ("project-teams",)


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def build_default_team_definition() -> dict[str, Any]:
    return {
        "name": DEFAULT_PROJECT_TEAM_NAME,
        "description": "Built-in software project delivery operating model for DeerFlow.",
        "visible_agent_name": "lead-agent",
        "phases": [
            "intake",
            "discovery",
            "architecture",
            "planning",
            "build",
            "qa_gate",
            "delivery",
            "closed",
        ],
        "specialists": [
            {
                "name": name,
                "summary": summary,
            }
            for name, summary in PROJECT_DELIVERY_SPECIALIST_SUMMARIES.items()
            if name not in {"general-purpose", "bash"}
        ],
        "routing_policy": {
            "default_parallelism": 3,
            "builder_agents": [
                "design-agent",
                "frontend-agent",
                "backend-agent",
                "integration-agent",
                "data-agent",
                "devops-agent",
            ],
            "qa_agent": "qa-agent",
            "delivery_agent": "delivery-agent",
        },
        "qa_policy": {
            "required_gate_statuses": ["pass", "pass_with_risk", "fail"],
        },
        "delivery_policy": {
            "artifact_root": "/mnt/user-data/outputs",
        },
        "updated_at": utc_now(),
    }


class MemoryStoreRepository:
    """Read/write DeerFlow memory profiles from a LangGraph store."""

    def __init__(self, store: BaseStore):
        self._store = store

    def _namespace(self, agent_name: str | None = None) -> tuple[str, ...]:
        if agent_name is None:
            return MEMORY_GLOBAL_NAMESPACE
        return (*MEMORY_AGENT_NAMESPACE, agent_name)

    def get_memory(self, agent_name: str | None = None) -> dict[str, Any] | None:
        item = self._store.get(self._namespace(agent_name), "profile")
        return deepcopy(item.value) if item is not None else None

    def put_memory(self, memory_data: dict[str, Any], agent_name: str | None = None) -> dict[str, Any]:
        payload = deepcopy(memory_data)
        payload["lastUpdated"] = utc_now()
        self._store.put(self._namespace(agent_name), "profile", payload)
        return payload


class ProjectStoreRepository:
    """Read/write project metadata, snapshots, controls, and team definitions."""

    def __init__(self, store: BaseStore):
        self._store = store

    def ensure_default_team(self) -> dict[str, Any]:
        existing = self.get_team(DEFAULT_PROJECT_TEAM_NAME)
        if existing is not None:
            return existing
        team = build_default_team_definition()
        self.put_team(DEFAULT_PROJECT_TEAM_NAME, team)
        return team

    def put_project_index(self, project_id: str, value: dict[str, Any]) -> dict[str, Any]:
        payload = deepcopy(value)
        payload["project_id"] = project_id
        payload["updated_at"] = utc_now()
        self._store.put(PROJECT_INDEX_NAMESPACE, project_id, payload)
        return payload

    def get_project_index(self, project_id: str) -> dict[str, Any] | None:
        item = self._store.get(PROJECT_INDEX_NAMESPACE, project_id)
        return deepcopy(item.value) if item is not None else None

    def list_projects(self, *, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        items = self._store.search(PROJECT_INDEX_NAMESPACE, limit=limit, offset=offset)
        projects = [deepcopy(item.value) for item in items]
        return sorted(projects, key=lambda p: p.get("updated_at", ""), reverse=True)

    def delete_project(self, project_id: str) -> None:
        self._store.delete(PROJECT_INDEX_NAMESPACE, project_id)
        self._store.delete(PROJECT_SNAPSHOT_NAMESPACE, project_id)
        self._store.delete(PROJECT_CONTROL_NAMESPACE, project_id)

    def put_project_snapshot(self, project_id: str, value: dict[str, Any]) -> dict[str, Any]:
        payload = deepcopy(value)
        payload["project_id"] = project_id
        payload["updated_at"] = utc_now()
        self._store.put(PROJECT_SNAPSHOT_NAMESPACE, project_id, payload)
        return payload

    def get_project_snapshot(self, project_id: str) -> dict[str, Any] | None:
        item = self._store.get(PROJECT_SNAPSHOT_NAMESPACE, project_id)
        return deepcopy(item.value) if item is not None else None

    def put_project_control(self, project_id: str, value: dict[str, Any]) -> dict[str, Any]:
        payload = deepcopy(value)
        payload["updated_at"] = utc_now()
        self._store.put(PROJECT_CONTROL_NAMESPACE, project_id, payload)
        return payload

    def get_project_control(self, project_id: str) -> dict[str, Any]:
        item = self._store.get(PROJECT_CONTROL_NAMESPACE, project_id)
        return deepcopy(item.value) if item is not None else {"pause_requested": False, "abort_requested": False}

    def put_team(self, team_name: str, value: dict[str, Any]) -> dict[str, Any]:
        payload = deepcopy(value)
        payload["name"] = team_name
        payload["updated_at"] = utc_now()
        self._store.put(PROJECT_TEAM_NAMESPACE, team_name, payload)
        return payload

    def get_team(self, team_name: str) -> dict[str, Any] | None:
        item = self._store.get(PROJECT_TEAM_NAMESPACE, team_name)
        return deepcopy(item.value) if item is not None else None

    def list_teams(self, *, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        self.ensure_default_team()
        items = self._store.search(PROJECT_TEAM_NAMESPACE, limit=limit, offset=offset)
        teams = [deepcopy(item.value) for item in items]
        return sorted(teams, key=lambda t: t.get("name", ""))

    def delete_team(self, team_name: str) -> None:
        if team_name == DEFAULT_PROJECT_TEAM_NAME:
            raise ValueError("The default project team cannot be deleted.")
        self._store.delete(PROJECT_TEAM_NAMESPACE, team_name)

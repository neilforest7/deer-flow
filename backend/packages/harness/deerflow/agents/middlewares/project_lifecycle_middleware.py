"""Middleware for project delivery runtime state."""

from __future__ import annotations

from typing import Any, override

from langchain.agents.middleware import AgentMiddleware
from langgraph.runtime import Runtime

from deerflow.agents.project_state import ProjectState
from deerflow.projects import (
    PROJECT_GRAPH_ID,
    compute_project_state_projection,
)
from deerflow.store import (
    DEFAULT_PROJECT_TEAM_NAME,
    ProjectStoreRepository,
    get_store,
)


def _utc_now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()


def _default_project_brief(title: str) -> dict[str, Any]:
    return {
        "objective": title,
        "target_users": [],
        "deliverables": [],
        "scope_in": [],
        "scope_out": [],
        "constraints": [],
        "success_criteria": [],
        "project_tags": ["software-project"],
    }


class ProjectLifecycleMiddleware(AgentMiddleware[ProjectState]):
    """Sync project runtime state into LangGraph state + store snapshots."""

    state_schema = ProjectState

    def _resolve_parallelism(self, state: ProjectState, runtime: Runtime) -> int:
        repo = ProjectStoreRepository(get_store())
        configured_parallelism = int((runtime.config.get("configurable", {}) or {}).get("max_concurrent_subagents", 3))
        team_name = str(state.get("team_name") or DEFAULT_PROJECT_TEAM_NAME)
        team = repo.get_team(team_name) or {}
        routing_policy = team.get("routing_policy")
        if isinstance(routing_policy, dict):
            default_parallelism = routing_policy.get("default_parallelism")
            if isinstance(default_parallelism, int) and default_parallelism > 0:
                return default_parallelism
        return max(1, configured_parallelism)

    def _get_project_id(self, state: ProjectState, runtime: Runtime) -> str | None:
        if state.get("project_id"):
            return state.get("project_id")
        context = runtime.context or {}
        if context.get("project_id"):
            return str(context["project_id"])
        config = runtime.config.get("configurable", {}) if runtime.config else {}
        if config.get("project_id"):
            return str(config["project_id"])
        return None

    def _get_thread_id(self, runtime: Runtime) -> str | None:
        context = runtime.context or {}
        if context.get("thread_id"):
            return str(context["thread_id"])
        config = runtime.config.get("configurable", {}) if runtime.config else {}
        if config.get("thread_id"):
            return str(config["thread_id"])
        return None

    def _ensure_index(self, project_id: str, thread_id: str | None, state: ProjectState) -> dict[str, Any]:
        repo = ProjectStoreRepository(get_store())
        repo.ensure_default_team()
        existing = repo.get_project_index(project_id)
        if existing is not None:
            return existing

        title = state.get("project_title") or state.get("title") or f"Project {project_id[:8]}"
        created = _utc_now()
        return repo.put_project_index(
            project_id,
            {
                "title": title,
                "description": "",
                "thread_id": thread_id,
                "assistant_id": PROJECT_GRAPH_ID,
                "status": "draft",
                "phase": "intake",
                "team_name": DEFAULT_PROJECT_TEAM_NAME,
                "created_at": created,
            },
        )

    @override
    def before_agent(self, state: ProjectState, runtime: Runtime) -> dict | None:
        project_id = self._get_project_id(state, runtime)
        if project_id is None:
            return None

        thread_id = self._get_thread_id(runtime)
        index = self._ensure_index(project_id, thread_id, state)
        repo = ProjectStoreRepository(get_store())
        snapshot = repo.get_project_snapshot(project_id) or {}
        control_flags = repo.get_project_control(project_id)

        phase = "closed" if control_flags.get("abort_requested") else index.get("phase", "intake")
        status = "aborted" if control_flags.get("abort_requested") else ("paused" if control_flags.get("pause_requested") else index.get("status", "draft"))
        title = state.get("project_title") or index.get("title") or state.get("title")

        return {
            "project_id": project_id,
            "project_title": title,
            "team_name": index.get("team_name", DEFAULT_PROJECT_TEAM_NAME),
            "project_phase": phase,
            "project_status": status,
            "project_brief": state.get("project_brief") or snapshot.get("project_brief") or _default_project_brief(title or f"Project {project_id[:8]}"),
            "work_orders": state.get("work_orders") or snapshot.get("work_orders") or [],
            "agent_reports": state.get("agent_reports") or snapshot.get("agent_reports") or [],
            "gate_decision": state.get("gate_decision") or snapshot.get("gate_decision"),
            "delivery_pack": state.get("delivery_pack") or snapshot.get("delivery_pack"),
            "active_batch": state.get("active_batch") or snapshot.get("active_batch"),
            "control_flags": control_flags,
        }

    @override
    def after_agent(self, state: ProjectState, runtime: Runtime) -> dict | None:
        project_id = self._get_project_id(state, runtime)
        if project_id is None:
            return None

        thread_id = self._get_thread_id(runtime)
        repo = ProjectStoreRepository(get_store())
        control_flags = repo.get_project_control(project_id)
        projection = compute_project_state_projection(
            state,
            control_flags=control_flags,
            max_parallelism=self._resolve_parallelism(state, runtime),
            now=_utc_now(),
        )

        title = state.get("project_title") or state.get("title") or f"Project {project_id[:8]}"
        repo.put_project_index(
            project_id,
            {
                "title": title,
                "description": state.get("project_brief", {}).get("objective", ""),
                "thread_id": thread_id,
                "assistant_id": PROJECT_GRAPH_ID,
                "status": projection["project_status"],
                "phase": projection["project_phase"],
                "team_name": state.get("team_name") or DEFAULT_PROJECT_TEAM_NAME,
                "created_at": (repo.get_project_index(project_id) or {}).get("created_at") or _utc_now(),
                "artifacts": list(state.get("artifacts") or []),
                "latest_gate": projection["gate_decision"],
            },
        )
        repo.put_project_snapshot(
            project_id,
            {
                "project_title": title,
                "project_brief": state.get("project_brief") or _default_project_brief(title),
                "work_orders": projection["work_orders"],
                "agent_reports": projection["agent_reports"],
                "gate_decision": projection["gate_decision"],
                "delivery_pack": projection["delivery_pack"],
                "active_batch": projection["active_batch"],
                "artifacts": list(state.get("artifacts") or []),
            },
        )

        return {
            "project_title": title,
            "project_phase": projection["project_phase"],
            "project_status": projection["project_status"],
            "work_orders": projection["work_orders"],
            "agent_reports": projection["agent_reports"],
            "gate_decision": projection["gate_decision"],
            "delivery_pack": projection["delivery_pack"],
            "active_batch": projection["active_batch"],
            "control_flags": control_flags,
        }

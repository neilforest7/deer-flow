"""Project-only middleware for batch scheduling and task dispatch guards."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any, override

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.runtime import Runtime
from langgraph.types import Command

from deerflow.agents.project_state import ProjectState
from deerflow.projects import (
    PROJECT_BATCHED_PHASES,
    compute_project_state_projection,
    project_work_order_by_id,
)
from deerflow.store import DEFAULT_PROJECT_TEAM_NAME, ProjectStoreRepository, get_store

logger = logging.getLogger(__name__)


class ProjectDispatchMiddleware(AgentMiddleware[ProjectState]):
    """Keep project specialist dispatch aligned with the planned active batch."""

    state_schema = ProjectState

    def _resolve_parallelism(self, state: ProjectState, runtime: Runtime | None) -> int:
        configured_parallelism = 3
        if runtime is not None:
            configured_parallelism = int((runtime.config.get("configurable", {}) or {}).get("max_concurrent_subagents", 3))

        team_name = str(state.get("team_name") or DEFAULT_PROJECT_TEAM_NAME)
        team = ProjectStoreRepository(get_store()).get_team(team_name) or {}
        team_parallelism = (
            team.get("routing_policy", {}).get("default_parallelism")
            if isinstance(team.get("routing_policy"), dict)
            else None
        )
        if isinstance(team_parallelism, int) and team_parallelism > 0:
            return team_parallelism
        return max(1, configured_parallelism)

    def _projection(self, state: ProjectState, runtime: Runtime | None) -> dict[str, Any]:
        return compute_project_state_projection(
            state,
            control_flags=state.get("control_flags"),
            max_parallelism=self._resolve_parallelism(state, runtime),
        )

    def _project_state_update(self, projection: dict[str, Any]) -> dict[str, Any]:
        return {
            "project_phase": projection["project_phase"],
            "project_status": projection["project_status"],
            "work_orders": projection["work_orders"],
            "agent_reports": projection["agent_reports"],
            "gate_decision": projection["gate_decision"],
            "delivery_pack": projection["delivery_pack"],
            "active_batch": projection["active_batch"],
        }

    def _filter_task_calls(self, state: ProjectState, runtime: Runtime) -> dict[str, Any] | None:
        messages = state.get("messages", [])
        if not messages:
            return self._project_state_update(self._projection(state, runtime))

        last_message = messages[-1]
        tool_calls = getattr(last_message, "tool_calls", None)
        if getattr(last_message, "type", None) != "ai" or not tool_calls:
            return self._project_state_update(self._projection(state, runtime))

        base_state = dict(state)
        base_state["messages"] = list(messages[:-1])
        projection_before_dispatch = self._projection(base_state, runtime)
        phase = projection_before_dispatch["project_phase"]
        active_batch = projection_before_dispatch.get("active_batch") or {}
        if phase not in PROJECT_BATCHED_PHASES:
            return self._project_state_update(self._projection(state, runtime))

        active_ids = set(active_batch.get("work_order_ids") or [])
        work_orders_by_id = project_work_order_by_id(projection_before_dispatch["work_orders"])
        filtered_tool_calls = []
        changed = False

        for tool_call in tool_calls:
            if tool_call.get("name") != "task":
                filtered_tool_calls.append(tool_call)
                continue

            args = tool_call.get("args", {}) or {}
            work_order_id = str(args.get("work_order_id") or "").strip()
            owner_agent = str(args.get("subagent_type") or "").strip()
            expected_order = work_orders_by_id.get(work_order_id)

            if not work_order_id or work_order_id not in active_ids or expected_order is None:
                changed = True
                logger.warning(
                    "Dropping project task call outside active batch: phase=%s work_order_id=%s tool_call_id=%s",
                    phase,
                    work_order_id or "<missing>",
                    tool_call.get("id"),
                )
                continue

            if owner_agent != str(expected_order.get("owner_agent") or ""):
                changed = True
                logger.warning(
                    "Dropping project task call with mismatched owner: phase=%s work_order_id=%s expected=%s actual=%s",
                    phase,
                    work_order_id,
                    expected_order.get("owner_agent"),
                    owner_agent,
                )
                continue

            filtered_tool_calls.append(tool_call)

        candidate_state = state
        if changed:
            candidate_state = dict(state)
            candidate_state["messages"] = [
                *list(messages[:-1]),
                last_message.model_copy(update={"tool_calls": filtered_tool_calls}),
            ]
        projection_after_dispatch = self._projection(candidate_state, runtime)
        update = self._project_state_update(projection_after_dispatch)
        if changed:
            update["messages"] = [candidate_state["messages"][-1]]
        return update

    def _validate_task_call(self, request: ToolCallRequest) -> ToolMessage | None:
        state = request.state
        if not isinstance(state, dict):
            return None

        projection = self._projection(state, request.runtime)
        phase = projection["project_phase"]
        if phase not in PROJECT_BATCHED_PHASES:
            return None

        active_batch = projection.get("active_batch") or {}
        active_ids = set(active_batch.get("work_order_ids") or [])
        args = request.tool_call.get("args", {}) or {}
        work_order_id = str(args.get("work_order_id") or "").strip()
        owner_agent = str(args.get("subagent_type") or "").strip()
        work_orders_by_id = project_work_order_by_id(projection["work_orders"])
        expected_order = work_orders_by_id.get(work_order_id)

        if not work_order_id:
            return ToolMessage(
                content=(
                    "Error: Project delivery tasks in the current phase must include a `work_order_id` "
                    "from the active batch."
                ),
                tool_call_id=str(request.tool_call.get("id") or "missing_tool_call_id"),
                name="task",
                status="error",
            )

        if work_order_id not in active_ids or expected_order is None:
            return ToolMessage(
                content=(
                    f"Error: Work order '{work_order_id}' is not in the current active batch for phase "
                    f"'{phase}'. Dispatch only the ready, non-conflicting batch."
                ),
                tool_call_id=str(request.tool_call.get("id") or "missing_tool_call_id"),
                name="task",
                status="error",
            )

        if owner_agent != str(expected_order.get("owner_agent") or ""):
            return ToolMessage(
                content=(
                    f"Error: Work order '{work_order_id}' must be owned by "
                    f"'{expected_order.get('owner_agent')}', not '{owner_agent}'."
                ),
                tool_call_id=str(request.tool_call.get("id") or "missing_tool_call_id"),
                name="task",
                status="error",
            )

        return None

    @override
    def before_model(self, state: ProjectState, runtime: Runtime) -> dict | None:
        return self._project_state_update(self._projection(state, runtime))

    @override
    async def abefore_model(self, state: ProjectState, runtime: Runtime) -> dict | None:
        return self.before_model(state, runtime)

    @override
    def after_model(self, state: ProjectState, runtime: Runtime) -> dict | None:
        return self._filter_task_calls(state, runtime)

    @override
    async def aafter_model(self, state: ProjectState, runtime: Runtime) -> dict | None:
        return self._filter_task_calls(state, runtime)

    @override
    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command],
    ) -> ToolMessage | Command:
        if request.tool_call.get("name") != "task":
            return handler(request)

        validation_error = self._validate_task_call(request)
        if validation_error is not None:
            return validation_error
        return handler(request)

    @override
    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command]],
    ) -> ToolMessage | Command:
        if request.tool_call.get("name") != "task":
            return await handler(request)

        validation_error = self._validate_task_call(request)
        if validation_error is not None:
            return validation_error
        return await handler(request)

"""Project delivery graph entrypoint."""

from __future__ import annotations

import logging
from typing import Any

from langchain.agents import create_agent
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from deerflow.agents.lead_agent.agent import _build_middlewares, _resolve_model_name
from deerflow.agents.lead_agent.prompt import apply_prompt_template
from deerflow.agents.middlewares.project_dispatch_middleware import ProjectDispatchMiddleware
from deerflow.agents.middlewares.project_lifecycle_middleware import ProjectLifecycleMiddleware
from deerflow.agents.project_state import ProjectState
from deerflow.config.app_config import get_app_config
from deerflow.models import create_chat_model
from deerflow.projects import (
    PROJECT_GRAPH_ID,
    PROJECT_MEMORY_SCOPE,
    PROJECT_PHASES,
    PROJECT_VISIBLE_AGENT_NAME,
    compute_project_state_projection,
)
from deerflow.store import ProjectStoreRepository, get_store

logger = logging.getLogger(__name__)


def _build_project_middlewares(config: RunnableConfig, model_name: str | None):
    middlewares = _build_middlewares(
        config,
        model_name=model_name,
        agent_name=None,
        memory_scope=PROJECT_MEMORY_SCOPE,
    )
    insert_at = max(len(middlewares) - 2, 0)
    middlewares.insert(insert_at, ProjectLifecycleMiddleware())
    middlewares.insert(insert_at + 1, ProjectDispatchMiddleware())
    return middlewares


def _build_phase_prompt(
    *,
    phase: str,
    subagent_enabled: bool,
    max_concurrent_subagents: int,
) -> str:
    phase_prompt = apply_prompt_template(
        subagent_enabled=subagent_enabled,
        max_concurrent_subagents=max_concurrent_subagents,
        agent_name=None,
        memory_scope=PROJECT_MEMORY_SCOPE,
        project_delivery_mode=True,
    )
    return (
        phase_prompt
        + f"\n<project_runtime_phase>{phase}</project_runtime_phase>\n"
        "<project_runtime_rule>Prefer the latest `project_phase`, `active_batch`, and `work_orders` in state when they become more specific during the run.</project_runtime_rule>"
    )


def build_project_lead_graph(
    config: RunnableConfig,
    *,
    checkpointer=None,
):
    """Build the project delivery graph.

    The outer LangGraph DAG owns project checkpoint continuity.
    Each run routes to the current project phase and executes exactly one
    `lead-agent` phase turn, with long-term project memory isolated to the
    shared `lead-agent` namespace.
    """
    from deerflow.tools import get_available_tools

    cfg = config.get("configurable", {})
    thinking_enabled = cfg.get("thinking_enabled", True)
    reasoning_effort = cfg.get("reasoning_effort", None)
    model_name = cfg.get("model_name") or cfg.get("model") or _resolve_model_name()
    subagent_enabled = cfg.get("subagent_enabled", True)
    max_concurrent_subagents = cfg.get("max_concurrent_subagents", 3)

    app_config = get_app_config()
    model_config = app_config.get_model_config(model_name) if model_name else None
    if model_config is None:
        raise ValueError("No chat model could be resolved for project_lead_agent.")
    if thinking_enabled and not model_config.supports_thinking:
        logger.warning(
            "Thinking requested for project_lead_agent but model %s does not support it; disabling thinking.",
            model_name,
        )
        thinking_enabled = False

    config.setdefault("metadata", {})
    config["metadata"].update(
        {
            "assistant_id": PROJECT_GRAPH_ID,
            "agent_name": PROJECT_VISIBLE_AGENT_NAME,
            "memory_scope": PROJECT_MEMORY_SCOPE,
            "model_name": model_name or "default",
            "thinking_enabled": thinking_enabled,
            "reasoning_effort": reasoning_effort,
            "subagent_enabled": subagent_enabled,
        }
    )

    shared_agent_kwargs: dict[str, Any] = {
        "model": create_chat_model(
            name=model_name,
            thinking_enabled=thinking_enabled,
            reasoning_effort=reasoning_effort,
        ),
        "tools": get_available_tools(
            model_name=model_name,
            subagent_enabled=subagent_enabled,
        ),
        "middleware": _build_project_middlewares(config, model_name=model_name),
        "state_schema": ProjectState,
        "store": get_store(),
    }

    phase_agents = {
        phase: create_agent(
            **shared_agent_kwargs,
            system_prompt=_build_phase_prompt(
                phase=phase,
                subagent_enabled=subagent_enabled,
                max_concurrent_subagents=max_concurrent_subagents,
            ),
            name=f"{PROJECT_GRAPH_ID}:{phase}",
        )
        for phase in PROJECT_PHASES[:-1]
    }

    repo = ProjectStoreRepository(get_store())

    def _route_entry(state: ProjectState) -> str:
        project_id = state.get("project_id")
        if project_id:
            control_flags = repo.get_project_control(project_id)
            if control_flags.get("abort_requested"):
                return "closed"
            if control_flags.get("pause_requested"):
                return "paused"

            projection = compute_project_state_projection(
                state,
                control_flags=control_flags,
                max_parallelism=3,
            )
            phase = projection.get("project_phase") or state.get("project_phase") or "intake"
        else:
            phase = state.get("project_phase") or "intake"
        if phase not in PROJECT_PHASES:
            return "intake"
        return phase

    def _build_phase_node(phase: str):
        async def _run_phase(
            state: ProjectState,
            runtime: Runtime[dict[str, Any]],
            config: RunnableConfig,
        ) -> dict[str, Any]:
            project_state = dict(state)
            configurable = (config.get("configurable", {}) or {}) if config else {}
            projection = compute_project_state_projection(
                project_state,
                control_flags=project_state.get("control_flags"),
                max_parallelism=int(configurable.get("max_concurrent_subagents", 3)),
            )
            project_state.update(projection)
            project_state["project_phase"] = phase
            project_state.setdefault("project_status", "draft" if phase == "intake" else "active")
            return await phase_agents[phase].ainvoke(
                project_state,
                config=config,
                context=runtime.context,
            )

        return _run_phase

    def _paused_node(state: ProjectState) -> dict[str, Any]:
        control_flags = state.get("control_flags") or {}
        return {
            "project_phase": state.get("project_phase") or "intake",
            "project_status": "paused",
            "control_flags": {
                **control_flags,
                "pause_requested": True,
            },
        }

    def _closed_node(state: ProjectState) -> dict[str, Any]:
        control_flags = state.get("control_flags") or {}
        status = state.get("project_status") or "completed"
        if control_flags.get("abort_requested"):
            status = "aborted"
        return {
            "project_phase": "closed",
            "project_status": status,
            "control_flags": control_flags,
        }

    workflow = StateGraph(ProjectState)
    for phase in PROJECT_PHASES[:-1]:
        workflow.add_node(phase, _build_phase_node(phase))
        workflow.add_edge(phase, END)
    workflow.add_node("paused", _paused_node)
    workflow.add_node("closed", _closed_node)
    workflow.add_edge("paused", END)
    workflow.add_edge("closed", END)
    workflow.add_conditional_edges(
        START,
        _route_entry,
        {
            **{phase: phase for phase in PROJECT_PHASES[:-1]},
            "paused": "paused",
            "closed": "closed",
        },
    )

    compile_kwargs: dict[str, Any] = {
        "store": get_store(),
        "name": PROJECT_GRAPH_ID,
    }
    if checkpointer is not None:
        compile_kwargs["checkpointer"] = checkpointer
    return workflow.compile(**compile_kwargs)


def make_project_lead_agent(config: RunnableConfig):
    return build_project_lead_graph(config)

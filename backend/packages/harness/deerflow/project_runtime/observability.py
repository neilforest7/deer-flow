from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from langgraph.config import get_config
from langgraph.runtime import Runtime

_PROJECT_RUNTIME_NAME = "project_team"
_PROJECT_RUNTIME_VERSION = "m1"


def project_runtime_version() -> str:
    return _PROJECT_RUNTIME_VERSION


def resolve_trace_id(
    state: Mapping[str, Any] | None = None,
    *,
    runtime: Runtime | None = None,
) -> str:
    if isinstance(state, Mapping):
        trace_id = state.get("trace_id")
        if isinstance(trace_id, str) and trace_id:
            return trace_id

    context = getattr(runtime, "context", None) or {}
    if isinstance(context, Mapping):
        trace_id = context.get("trace_id")
        if isinstance(trace_id, str) and trace_id:
            return trace_id

    try:
        config = get_config()
    except RuntimeError:
        config = {}
    metadata = config.get("metadata", {}) if isinstance(config, Mapping) else {}
    if isinstance(metadata, Mapping):
        trace_id = metadata.get("trace_id")
        if isinstance(trace_id, str) and trace_id:
            return trace_id

    return str(uuid.uuid4())[:8]


def build_runtime_metadata(
    *,
    thread_id: str | None,
    phase: str,
    plan_status: str | None,
    trace_id: str,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "runtime": _PROJECT_RUNTIME_NAME,
        "thread_id": thread_id or "default",
        "phase": phase,
        "plan_status": plan_status,
        "project_runtime_version": _PROJECT_RUNTIME_VERSION,
        "trace_id": trace_id,
    }
    return metadata


def _build_specialist_metadata(
    *,
    thread_id: str | None,
    phase: str,
    plan_status: str | None,
    trace_id: str,
    work_order_id: str,
    owner_agent: str,
    execution_kind: str,
) -> dict[str, Any]:
    metadata = build_runtime_metadata(
        thread_id=thread_id,
        phase=phase,
        plan_status=plan_status,
        trace_id=trace_id,
    )
    metadata.update(
        {
            "work_order_id": work_order_id,
            "owner_agent": owner_agent,
            "execution_kind": execution_kind,
        }
    )
    return metadata


def _build_phase_execution_work_order_id(
    *,
    phase: str,
    owner_agent: str,
    attempt: int,
) -> str:
    return f"phase:{phase}:{owner_agent}:attempt:{attempt}"


def build_specialist_metadata(
    *,
    thread_id: str | None,
    plan_status: str | None,
    trace_id: str,
    work_order_id: str,
    owner_agent: str,
) -> dict[str, Any]:
    return _build_specialist_metadata(
        thread_id=thread_id,
        phase="build",
        plan_status=plan_status,
        trace_id=trace_id,
        work_order_id=work_order_id,
        owner_agent=owner_agent,
        execution_kind="build_specialist",
    )


def build_discovery_specialist_metadata(
    *,
    thread_id: str | None,
    plan_status: str | None,
    trace_id: str,
    owner_agent: str,
    attempt: int,
) -> dict[str, Any]:
    phase = "discovery"
    return _build_specialist_metadata(
        thread_id=thread_id,
        phase=phase,
        plan_status=plan_status,
        trace_id=trace_id,
        work_order_id=_build_phase_execution_work_order_id(
            phase=phase,
            owner_agent=owner_agent,
            attempt=attempt,
        ),
        owner_agent=owner_agent,
        execution_kind="discovery_specialist",
    )


def build_planning_specialist_metadata(
    *,
    thread_id: str | None,
    plan_status: str | None,
    trace_id: str,
    attempt: int,
    owner_agent: str = "planner-agent",
) -> dict[str, Any]:
    phase = "planning"
    return _build_specialist_metadata(
        thread_id=thread_id,
        phase=phase,
        plan_status=plan_status,
        trace_id=trace_id,
        work_order_id=_build_phase_execution_work_order_id(
            phase=phase,
            owner_agent=owner_agent,
            attempt=attempt,
        ),
        owner_agent=owner_agent,
        execution_kind="planning_specialist",
    )


def build_delivery_specialist_metadata(
    *,
    thread_id: str | None,
    plan_status: str | None,
    trace_id: str,
    attempt: int,
    owner_agent: str = "delivery-agent",
) -> dict[str, Any]:
    phase = "delivery"
    return _build_specialist_metadata(
        thread_id=thread_id,
        phase=phase,
        plan_status=plan_status,
        trace_id=trace_id,
        work_order_id=_build_phase_execution_work_order_id(
            phase=phase,
            owner_agent=owner_agent,
            attempt=attempt,
        ),
        owner_agent=owner_agent,
        execution_kind="delivery_specialist",
    )


def build_qa_metadata(
    *,
    thread_id: str | None,
    plan_status: str | None,
    trace_id: str,
    work_order_id: str,
) -> dict[str, Any]:
    return _build_specialist_metadata(
        thread_id=thread_id,
        phase="qa_gate",
        plan_status=plan_status,
        trace_id=trace_id,
        work_order_id=work_order_id,
        owner_agent="qa-agent",
        execution_kind="qa_check",
    )

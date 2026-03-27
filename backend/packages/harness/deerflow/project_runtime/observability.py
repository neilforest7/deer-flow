from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

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
    context = getattr(runtime, "context", None) or {}
    if isinstance(context, Mapping):
        trace_id = context.get("trace_id")
        if isinstance(trace_id, str) and trace_id:
            return trace_id

    if isinstance(state, Mapping):
        trace_id = state.get("trace_id")
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
        "project_runtime_version": _PROJECT_RUNTIME_VERSION,
        "trace_id": trace_id,
    }
    if plan_status:
        metadata["plan_status"] = plan_status
    return metadata


def build_specialist_metadata(
    *,
    thread_id: str | None,
    plan_status: str | None,
    trace_id: str,
    work_order_id: str,
    owner_agent: str,
) -> dict[str, Any]:
    metadata = build_runtime_metadata(
        thread_id=thread_id,
        phase="build",
        plan_status=plan_status,
        trace_id=trace_id,
    )
    metadata.update(
        {
            "work_order_id": work_order_id,
            "owner_agent": owner_agent,
            "execution_kind": "build_specialist",
        }
    )
    return metadata


def build_qa_metadata(
    *,
    thread_id: str | None,
    plan_status: str | None,
    trace_id: str,
    work_order_id: str,
) -> dict[str, Any]:
    metadata = build_runtime_metadata(
        thread_id=thread_id,
        phase="qa_gate",
        plan_status=plan_status,
        trace_id=trace_id,
    )
    metadata.update(
        {
            "work_order_id": work_order_id,
            "owner_agent": "qa-agent",
            "execution_kind": "qa_check",
        }
    )
    return metadata

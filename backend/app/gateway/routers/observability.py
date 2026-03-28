from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from langsmith import Client
from langsmith.utils import LangSmithError
from pydantic import BaseModel, Field

from deerflow.config import get_tracing_config
from deerflow.config.tracing_config import TracingConfig

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/observability/langsmith", tags=["observability"])


class LangSmithConfigResponse(BaseModel):
    enabled: bool = Field(..., description="Whether LangSmith tracing is enabled by configuration.")
    configured: bool = Field(..., description="Whether LangSmith tracing is both enabled and has an API key.")
    api_key_present: bool = Field(..., description="Whether an API key is present in environment variables.")
    project: str = Field(..., description="Default LangSmith project name.")
    endpoint: str = Field(..., description="LangSmith API endpoint.")


class LangSmithRunSummary(BaseModel):
    id: str = Field(..., description="Run ID.")
    name: str | None = Field(default=None, description="Run name.")
    run_type: str | None = Field(default=None, description="Run type such as chain, llm, tool.")
    trace_id: str | None = Field(default=None, description="Root trace ID for the run tree.")
    parent_run_id: str | None = Field(default=None, description="Immediate parent run ID.")
    status: str | None = Field(default=None, description="Run status.")
    error: Any | None = Field(default=None, description="Run error payload if present.")
    start_time: datetime | None = Field(default=None, description="Run start time.")
    end_time: datetime | None = Field(default=None, description="Run end time.")
    tags: list[str] = Field(default_factory=list, description="Run tags.")
    thread_id: str | None = Field(default=None, description="Thread ID stored in run metadata, if available.")
    request_id: str | None = Field(default=None, description="Request ID stored in run metadata, if available.")
    custom_trace_id: str | None = Field(default=None, description="Custom application trace_id stored in run metadata, if available.")


class LangSmithRunsResponse(BaseModel):
    project: str = Field(..., description="LangSmith project queried.")
    count: int = Field(..., description="Number of runs returned.")
    runs: list[LangSmithRunSummary] = Field(default_factory=list, description="Runs in reverse chronological order.")


class LangSmithTraceResponse(BaseModel):
    project: str = Field(..., description="LangSmith project queried.")
    trace_id: str = Field(..., description="Trace ID / root run ID.")
    run_count: int = Field(..., description="Total number of runs in the returned trace tree.")
    root_run: dict[str, Any] = Field(..., description="Root run payload including child_runs when requested.")


def _build_langsmith_client(config: TracingConfig) -> Client:
    return Client(api_url=config.endpoint, api_key=config.api_key)


def _require_tracing_config() -> TracingConfig:
    config = get_tracing_config()
    if not config.is_configured:
        raise HTTPException(status_code=503, detail="LangSmith tracing is not configured.")
    return config


def _get_langsmith_client() -> Client:
    return _build_langsmith_client(_require_tracing_config())


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _extract_metadata(run: Any) -> dict[str, Any]:
    extra = getattr(run, "extra", None)
    if not isinstance(extra, Mapping):
        return {}
    metadata = extra.get("metadata")
    if isinstance(metadata, Mapping):
        return dict(metadata)
    return {}


def _run_matches_metadata_filters(run: Any, *, thread_id: str | None, custom_trace_id: str | None) -> bool:
    metadata = _extract_metadata(run)
    if thread_id is not None and metadata.get("thread_id") != thread_id:
        return False
    if custom_trace_id is not None and metadata.get("trace_id") != custom_trace_id:
        return False
    return True


def _run_to_summary(run: Any) -> LangSmithRunSummary:
    metadata = _extract_metadata(run)
    return LangSmithRunSummary(
        id=str(getattr(run, "id")),
        name=getattr(run, "name", None),
        run_type=getattr(run, "run_type", None),
        trace_id=_string_or_none(getattr(run, "trace_id", None)),
        parent_run_id=_string_or_none(getattr(run, "parent_run_id", None)),
        status=getattr(run, "status", None),
        error=getattr(run, "error", None),
        start_time=getattr(run, "start_time", None),
        end_time=getattr(run, "end_time", None),
        tags=list(getattr(run, "tags", []) or []),
        thread_id=_string_or_none(metadata.get("thread_id")),
        request_id=_string_or_none(metadata.get("request_id")),
        custom_trace_id=_string_or_none(metadata.get("trace_id")),
    )


def _count_runs_in_tree(run_payload: Mapping[str, Any]) -> int:
    total = 1
    child_runs = run_payload.get("child_runs")
    if not isinstance(child_runs, list):
        return total
    for child in child_runs:
        if isinstance(child, Mapping):
            total += _count_runs_in_tree(child)
    return total


@router.get(
    "/config",
    response_model=LangSmithConfigResponse,
    summary="Get LangSmith Tracing Configuration",
    description="Return the effective LangSmith tracing configuration without exposing secrets.",
)
def get_langsmith_config() -> LangSmithConfigResponse:
    config = get_tracing_config()
    return LangSmithConfigResponse(
        enabled=config.enabled,
        configured=config.is_configured,
        api_key_present=bool(config.api_key),
        project=config.project,
        endpoint=config.endpoint,
    )


@router.get(
    "/runs",
    response_model=LangSmithRunsResponse,
    summary="List LangSmith Runs",
    description="List recent LangSmith runs, with optional filtering by trace ID, thread ID, or custom trace metadata.",
)
def list_langsmith_runs(
    limit: int = Query(default=20, ge=1, le=200),
    project_name: str | None = Query(default=None, description="Override the default LangSmith project."),
    trace_id: str | None = Query(default=None, description="Filter by LangSmith trace ID."),
    thread_id: str | None = Query(default=None, description="Filter by DeerFlow thread_id stored in metadata."),
    custom_trace_id: str | None = Query(default=None, description="Filter by DeerFlow custom trace_id stored in metadata."),
    run_type: str | None = Query(default=None, description="Filter by LangSmith run type."),
    root_only: bool = Query(default=False, description="Return only root runs / traces."),
    error: bool | None = Query(default=None, description="Filter by whether the run has an error."),
    start_time: datetime | None = Query(default=None, description="Return only runs that start after this ISO timestamp."),
) -> LangSmithRunsResponse:
    config = _require_tracing_config()
    project = project_name or config.project
    client = _build_langsmith_client(config)

    fetch_limit = limit
    if thread_id is not None or custom_trace_id is not None:
        fetch_limit = min(max(limit * 10, 100), 500)

    try:
        runs = list(
            client.list_runs(
                project_name=project,
                trace_id=trace_id,
                run_type=run_type,
                is_root=True if root_only else None,
                error=error,
                start_time=start_time,
                limit=fetch_limit,
            )
        )
    except LangSmithError as exc:
        logger.exception("Failed to list LangSmith runs")
        raise HTTPException(status_code=502, detail=f"Failed to query LangSmith runs: {exc}") from exc

    filtered = [
        run
        for run in runs
        if _run_matches_metadata_filters(run, thread_id=thread_id, custom_trace_id=custom_trace_id)
    ]
    summaries = [_run_to_summary(run) for run in filtered[:limit]]

    return LangSmithRunsResponse(project=project, count=len(summaries), runs=summaries)


@router.get(
    "/traces/{trace_id}",
    response_model=LangSmithTraceResponse,
    summary="Get LangSmith Trace",
    description="Fetch a LangSmith root run by trace ID and optionally include child runs.",
)
def get_langsmith_trace(
    trace_id: str,
    project_name: str | None = Query(default=None, description="Override the default LangSmith project in the response payload."),
    load_child_runs: bool = Query(default=True, description="Include child runs in the returned trace tree."),
) -> LangSmithTraceResponse:
    config = _require_tracing_config()
    client = _build_langsmith_client(config)

    try:
        run = client.read_run(trace_id, load_child_runs=load_child_runs)
    except LangSmithError as exc:
        if "404" in str(exc):
            raise HTTPException(status_code=404, detail=f"LangSmith trace not found: {trace_id}") from exc
        logger.exception("Failed to read LangSmith trace %s", trace_id)
        raise HTTPException(status_code=502, detail=f"Failed to query LangSmith trace: {exc}") from exc

    payload = run.model_dump(mode="json")
    return LangSmithTraceResponse(
        project=project_name or config.project,
        trace_id=trace_id,
        run_count=_count_runs_in_tree(payload),
        root_run=payload,
    )

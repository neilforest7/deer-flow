"""Project Delivery OS API router."""

from __future__ import annotations

import logging
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from langgraph_sdk import get_client
from pydantic import BaseModel, Field

from app.gateway.config import get_gateway_config
from deerflow.projects import (
    PROJECT_ACTIONS,
    PROJECT_GRAPH_ID,
    PROJECT_MEMORY_SCOPE,
    apply_project_action_payload,
    build_initial_project_state,
    build_project_index,
    compose_project_record,
    create_project_id,
)
from deerflow.store import DEFAULT_PROJECT_TEAM_NAME, ProjectStoreRepository, get_store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["projects"])


def _get_langgraph_client():
    return get_client(url=get_gateway_config().langgraph_url)


def _normalize_thread_values(thread_state: Any) -> dict[str, Any]:
    if isinstance(thread_state, dict):
        values = thread_state.get("values")
        return values if isinstance(values, dict) else {}
    values = getattr(thread_state, "values", None)
    return values if isinstance(values, dict) else {}


async def _sync_project_control_flags(thread_id: str, control_flags: dict[str, Any]) -> None:
    await _get_langgraph_client().threads.update_state(
        thread_id,
        {"control_flags": control_flags},
        as_node="project_control",
    )


async def _start_project_run(thread_id: str, project_id: str) -> None:
    await _get_langgraph_client().runs.create(
        thread_id,
        PROJECT_GRAPH_ID,
        input={"messages": []},
        context={
            "thread_id": thread_id,
            "project_id": project_id,
            "agent_name": PROJECT_MEMORY_SCOPE,
        },
        config={
            "configurable": {
                "thread_id": thread_id,
                "project_id": project_id,
                "subagent_enabled": True,
            }
        },
    )


class ProjectCreateRequest(BaseModel):
    title: str = Field(..., description="Project title")
    objective: str | None = Field(default=None, description="Initial project objective")
    team_name: str = Field(default=DEFAULT_PROJECT_TEAM_NAME, description="Project team template name")
    project_id: str | None = Field(default=None, description="Optional explicit project_id")


class ProjectActionRequest(BaseModel):
    action: Literal["pause", "resume", "abort"]


class ProjectTeamRequest(BaseModel):
    description: str = Field(default="", description="Team description")
    visible_agent_name: str = Field(default="lead-agent", description="User-facing coordinator name")
    phases: list[str] = Field(default_factory=list, description="Project phases supported by the team")
    specialists: list[dict[str, Any]] = Field(default_factory=list, description="Specialist catalog")
    routing_policy: dict[str, Any] = Field(default_factory=dict, description="Dispatch policy")
    qa_policy: dict[str, Any] = Field(default_factory=dict, description="QA gate policy")
    delivery_policy: dict[str, Any] = Field(default_factory=dict, description="Delivery policy")


class ProjectRecordResponse(BaseModel):
    project_id: str
    thread_id: str
    assistant_id: str
    visible_agent_name: str = "lead-agent"
    title: str
    description: str
    status: str
    phase: str
    team_name: str
    created_at: str | None = None
    updated_at: str | None = None
    project_title: str | None = None
    project_brief: dict[str, Any] | None = None
    work_orders: list[dict[str, Any]] = Field(default_factory=list)
    agent_reports: list[dict[str, Any]] = Field(default_factory=list)
    gate_decision: dict[str, Any] | None = None
    delivery_pack: dict[str, Any] | None = None
    active_batch: dict[str, Any] | None = None
    artifacts: list[str] = Field(default_factory=list)
    control_flags: dict[str, Any] = Field(default_factory=dict)
    latest_gate: dict[str, Any] | None = None


class ProjectListResponse(BaseModel):
    projects: list[ProjectRecordResponse]


class ProjectTeamResponse(BaseModel):
    name: str
    description: str = ""
    visible_agent_name: str = "lead-agent"
    phases: list[str] = Field(default_factory=list)
    specialists: list[dict[str, Any]] = Field(default_factory=list)
    routing_policy: dict[str, Any] = Field(default_factory=dict)
    qa_policy: dict[str, Any] = Field(default_factory=dict)
    delivery_policy: dict[str, Any] = Field(default_factory=dict)
    updated_at: str | None = None


class ProjectTeamListResponse(BaseModel):
    teams: list[ProjectTeamResponse]


async def _get_project_record(project_id: str) -> dict[str, Any]:
    repo = ProjectStoreRepository(get_store())
    index = repo.get_project_index(project_id)
    if index is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")

    snapshot = repo.get_project_snapshot(project_id)
    control_flags = repo.get_project_control(project_id)
    runtime_values: dict[str, Any] | None = None
    try:
        thread_state = await _get_langgraph_client().threads.get_state(index["thread_id"])
        runtime_values = _normalize_thread_values(thread_state)
    except Exception:
        logger.debug("Failed to fetch runtime state for project %s", project_id, exc_info=True)

    return compose_project_record(
        index,
        snapshot=snapshot,
        control_flags=control_flags,
        runtime_values=runtime_values,
    )


@router.post(
    "/projects",
    response_model=ProjectRecordResponse,
    status_code=201,
    summary="Create Project",
    description="Create a new project delivery thread backed by `project_lead_agent`.",
)
async def create_project(request: ProjectCreateRequest) -> ProjectRecordResponse:
    repo = ProjectStoreRepository(get_store())
    repo.ensure_default_team()
    if repo.get_team(request.team_name) is None:
        raise HTTPException(status_code=404, detail=f"Project team '{request.team_name}' not found")

    project_id = request.project_id or create_project_id()
    thread_id = project_id

    try:
        await _get_langgraph_client().threads.create(
            thread_id=thread_id,
            graph_id=PROJECT_GRAPH_ID,
        )
        initial_state = build_initial_project_state(
            project_id=project_id,
            title=request.title,
            objective=request.objective,
            team_name=request.team_name,
        )
        await _get_langgraph_client().threads.update_state(
            thread_id,
            initial_state,
            as_node="project_bootstrap",
        )
    except Exception as exc:
        logger.exception("Failed to create project thread %s", project_id)
        raise HTTPException(status_code=502, detail=f"Failed to create LangGraph project thread: {exc}") from exc

    index_payload = build_project_index(
        project_id=project_id,
        thread_id=thread_id,
        title=request.title,
        objective=request.objective,
        team_name=request.team_name,
    )
    repo.put_project_index(project_id, index_payload)
    repo.put_project_snapshot(
        project_id,
        {
            "project_title": request.title,
            "project_brief": initial_state["project_brief"],
            "work_orders": [],
            "agent_reports": [],
            "gate_decision": None,
            "delivery_pack": None,
            "active_batch": None,
            "artifacts": [],
        },
    )
    repo.put_project_control(project_id, initial_state["control_flags"])

    return ProjectRecordResponse(**(await _get_project_record(project_id)))


@router.get(
    "/projects",
    response_model=ProjectListResponse,
    summary="List Projects",
    description="List project delivery records from LangGraph Store.",
)
async def list_projects(limit: int = 100, offset: int = 0) -> ProjectListResponse:
    repo = ProjectStoreRepository(get_store())
    repo.ensure_default_team()
    projects = []
    for index in repo.list_projects(limit=limit, offset=offset):
        projects.append(await _get_project_record(index["project_id"]))
    return ProjectListResponse(projects=[ProjectRecordResponse(**item) for item in projects])


@router.get(
    "/projects/{project_id}",
    response_model=ProjectRecordResponse,
    summary="Get Project",
    description="Get the latest project board projection for one project.",
)
async def get_project(project_id: str) -> ProjectRecordResponse:
    return ProjectRecordResponse(**(await _get_project_record(project_id)))


@router.post(
    "/projects/{project_id}/actions",
    response_model=ProjectRecordResponse,
    summary="Control Project",
    description="Apply a cooperative control action (`pause`, `resume`, `abort`) to a project thread.",
)
async def control_project(project_id: str, request: ProjectActionRequest) -> ProjectRecordResponse:
    if request.action not in PROJECT_ACTIONS:
        raise HTTPException(status_code=422, detail=f"Unsupported project action '{request.action}'")

    repo = ProjectStoreRepository(get_store())
    index = repo.get_project_index(project_id)
    if index is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")

    previous_control = repo.get_project_control(project_id)
    current_record = await _get_project_record(project_id)
    if request.action == "resume" and (
        previous_control.get("abort_requested")
        or current_record.get("status") == "aborted"
        or current_record.get("phase") == "closed"
    ):
        raise HTTPException(status_code=409, detail="Aborted projects cannot be resumed")

    updated_control = apply_project_action_payload(
        previous_control,
        request.action,
    )
    repo.put_project_control(project_id, updated_control)

    try:
        await _sync_project_control_flags(index["thread_id"], updated_control)
    except Exception:
        logger.debug("Failed to sync control flags into thread state for %s", project_id, exc_info=True)

    should_resume_run = (
        request.action == "resume"
        and bool(previous_control.get("pause_requested"))
        and current_record.get("status") == "paused"
    )
    if should_resume_run:
        try:
            await _start_project_run(index["thread_id"], project_id)
        except Exception as exc:
            repo.put_project_control(project_id, previous_control)
            try:
                await _sync_project_control_flags(index["thread_id"], previous_control)
            except Exception:
                logger.debug("Failed to rollback control flags for %s", project_id, exc_info=True)
            logger.exception("Failed to resume project run %s", project_id)
            raise HTTPException(status_code=502, detail=f"Failed to resume project run: {exc}") from exc

    return ProjectRecordResponse(**(await _get_project_record(project_id)))


@router.get(
    "/project-teams",
    response_model=ProjectTeamListResponse,
    summary="List Project Teams",
    description="List project team definitions stored in LangGraph Store.",
)
async def list_project_teams(limit: int = 100, offset: int = 0) -> ProjectTeamListResponse:
    repo = ProjectStoreRepository(get_store())
    teams = repo.list_teams(limit=limit, offset=offset)
    return ProjectTeamListResponse(teams=[ProjectTeamResponse(**team) for team in teams])


@router.post(
    "/project-teams/{team_name}",
    response_model=ProjectTeamResponse,
    status_code=201,
    summary="Create Project Team",
    description="Create a new reusable project team definition.",
)
async def create_project_team(team_name: str, request: ProjectTeamRequest) -> ProjectTeamResponse:
    repo = ProjectStoreRepository(get_store())
    if repo.get_team(team_name) is not None:
        raise HTTPException(status_code=409, detail=f"Project team '{team_name}' already exists")

    payload = repo.put_team(team_name, request.model_dump())
    return ProjectTeamResponse(**payload)


@router.get(
    "/project-teams/{team_name}",
    response_model=ProjectTeamResponse,
    summary="Get Project Team",
    description="Retrieve one project team definition.",
)
async def get_project_team(team_name: str) -> ProjectTeamResponse:
    repo = ProjectStoreRepository(get_store())
    team = repo.get_team(team_name)
    if team is None:
        raise HTTPException(status_code=404, detail=f"Project team '{team_name}' not found")
    return ProjectTeamResponse(**team)


@router.put(
    "/project-teams/{team_name}",
    response_model=ProjectTeamResponse,
    summary="Update Project Team",
    description="Update one project team definition.",
)
async def update_project_team(team_name: str, request: ProjectTeamRequest) -> ProjectTeamResponse:
    repo = ProjectStoreRepository(get_store())
    if repo.get_team(team_name) is None:
        raise HTTPException(status_code=404, detail=f"Project team '{team_name}' not found")

    payload = repo.put_team(team_name, request.model_dump())
    return ProjectTeamResponse(**payload)


@router.delete(
    "/project-teams/{team_name}",
    summary="Delete Project Team",
    description="Delete one project team definition.",
)
async def delete_project_team(team_name: str) -> dict[str, Any]:
    repo = ProjectStoreRepository(get_store())
    if repo.get_team(team_name) is None:
        raise HTTPException(status_code=404, detail=f"Project team '{team_name}' not found")

    try:
        repo.delete_team(team_name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {"success": True, "team_name": team_name}

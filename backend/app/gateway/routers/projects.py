"""Projects API router for project_team_agent runtime."""
import logging
from typing import Any
import aiosqlite

from fastapi import APIRouter, HTTPException
from langgraph_sdk import get_client
from pydantic import BaseModel

from deerflow.config import get_app_config

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/projects", tags=["projects"])


# Response Models
class ProjectBrief(BaseModel):
    """Project brief schema."""
    objective: str
    scope: list[str]
    constraints: list[str]
    deliverables: list[str]
    success_criteria: list[str]


class WorkOrder(BaseModel):
    """Work order schema."""
    id: str
    owner_agent: str
    title: str
    goal: str
    read_scope: list[str]
    write_scope: list[str]
    dependencies: list[str]
    acceptance_checks: list[str]
    status: str


class AgentReport(BaseModel):
    """Agent report schema."""
    work_order_id: str
    agent_name: str
    summary: str
    changes: list[str]
    risks: list[str]
    verification: list[str]


class QAGate(BaseModel):
    """QA gate schema."""
    result: str
    findings: list[str]
    required_rework: list[str]


class DeliverySummary(BaseModel):
    """Delivery summary schema."""
    completed_work: list[dict[str, Any]]
    artifacts: list[str]
    verification: list[str]
    follow_ups: list[str]


class Project(BaseModel):
    """Project list item."""
    id: str
    title: str
    phase: str
    plan_status: str
    created_at: str
    updated_at: str


class ProjectDetail(Project):
    """Full project detail."""
    project_brief: ProjectBrief | None
    work_orders: list[WorkOrder]
    agent_reports: list[AgentReport]
    qa_gate: QAGate | None
    delivery_summary: DeliverySummary | None
    phase_artifacts: dict[str, Any]


class ProjectsListResponse(BaseModel):
    """Response for listing projects."""
    projects: list[Project]


class CreateProjectRequest(BaseModel):
    """Request to create a new project."""
    objective: str


class CreateProjectResponse(BaseModel):
    """Response for creating a project."""
    thread_id: str


class ReviseProjectRequest(BaseModel):
    """Request to revise a project plan."""
    feedback: str


# Helper functions
def get_checkpointer():
    """Get LangGraph checkpointer instance."""
    return make_checkpointer()


def get_langgraph_client():
    """Get LangGraph SDK client."""
    return get_client(url="http://localhost:2024")


def _extract_project_title(state: dict[str, Any]) -> str:
    """Extract project title from state."""
    project_brief = state.get("project_brief")
    if project_brief and isinstance(project_brief, dict):
        objective = project_brief.get("objective", "").strip()
        if objective:
            return objective
    return "Untitled Project"


def _state_to_project(thread_id: str, checkpoint_data: dict[str, Any]) -> Project:
    """Convert checkpoint data to Project."""
    state = checkpoint_data.get("checkpoint", {}).get("channel_values", {})
    metadata = checkpoint_data.get("metadata", {})

    return Project(
        id=thread_id,
        title=_extract_project_title(state),
        phase=state.get("phase", "intake"),
        plan_status=state.get("plan_status", "draft"),
        created_at=checkpoint_data.get("created_at", ""),
        updated_at=checkpoint_data.get("updated_at", "")
    )


def _state_to_project_detail(thread_id: str, checkpoint_data: dict[str, Any]) -> ProjectDetail:
    """Convert checkpoint data to ProjectDetail."""
    state = checkpoint_data.get("checkpoint", {}).get("channel_values", {})

    # Extract project brief
    project_brief_data = state.get("project_brief")
    project_brief = ProjectBrief(**project_brief_data) if project_brief_data else None

    # Extract work orders
    work_orders = [WorkOrder(**wo) for wo in state.get("work_orders", [])]

    # Extract agent reports
    agent_reports = [AgentReport(**report) for report in state.get("agent_reports", [])]

    # Extract QA gate
    qa_gate_data = state.get("qa_gate")
    qa_gate = QAGate(**qa_gate_data) if qa_gate_data else None

    # Extract delivery summary
    delivery_data = state.get("delivery_summary")
    delivery_summary = DeliverySummary(**delivery_data) if delivery_data else None

    return ProjectDetail(
        id=thread_id,
        title=_extract_project_title(state),
        phase=state.get("phase", "intake"),
        plan_status=state.get("plan_status", "draft"),
        created_at=checkpoint_data.get("created_at", ""),
        updated_at=checkpoint_data.get("updated_at", ""),
        project_brief=project_brief,
        work_orders=work_orders,
        agent_reports=agent_reports,
        qa_gate=qa_gate,
        delivery_summary=delivery_summary,
        phase_artifacts=state.get("phase_artifacts", {})
    )


# API Endpoints
@router.get("/", response_model=ProjectsListResponse)
async def list_projects() -> ProjectsListResponse:
    """List all project_team_agent threads."""
    # LangGraph stores checkpoints in its own database
    db_path = "/app/backend/.deer-flow/langgraph.db"

    try:
        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute("""
                SELECT DISTINCT thread_id, checkpoint, metadata
                FROM checkpoints
                WHERE json_extract(metadata, '$.assistant_id') = 'project_team_agent'
                ORDER BY thread_ts DESC
            """)
            rows = await cursor.fetchall()
    except Exception as e:
        logger.warning(f"Failed to query checkpoints: {e}")
        # Return empty list if database doesn't exist or has no tables yet
        return ProjectsListResponse(projects=[])

    projects = []
    for row in rows:
        thread_id, checkpoint_data, metadata = row
        # Parse checkpoint to get state
        import json
        state = json.loads(checkpoint_data).get("channel_values", {})

        projects.append(Project(
            id=thread_id,
            title=_extract_project_title(state),
            phase=state.get("phase", "intake"),
            plan_status=state.get("plan_status", "draft"),
            created_at="",
            updated_at=""
        ))

    return ProjectsListResponse(projects=projects)

    return ProjectsListResponse(projects=projects)


@router.get("/{thread_id}", response_model=ProjectDetail)
async def get_project_detail(thread_id: str) -> ProjectDetail:
    """Get detailed project information."""
    client = get_langgraph_client()

    try:
        state = await client.threads.get_state(thread_id)
    except Exception:
        raise HTTPException(status_code=404, detail=f"Project {thread_id} not found")

    # Verify it's a project_team_agent thread
    metadata = state.get("metadata", {})
    if metadata.get("assistant_id") != "project_team_agent":
        raise HTTPException(status_code=404, detail=f"Project {thread_id} not found")

    values = state.get("values", {})
    return ProjectDetail(
        id=thread_id,
        title=_extract_project_title(values),
        phase=values.get("phase", "intake"),
        plan_status=values.get("plan_status", "draft"),
        created_at=state.get("created_at", ""),
        updated_at=state.get("updated_at", ""),
        project_brief=values.get("project_brief"),
        work_orders=values.get("work_orders", []),
        agent_reports=values.get("agent_reports", []),
        qa_gate=values.get("qa_gate"),
        delivery_summary=values.get("delivery_summary"),
        phase_artifacts=values.get("phase_artifacts", {})
    )


@router.post("/", response_model=CreateProjectResponse)
async def create_project(request: CreateProjectRequest) -> CreateProjectResponse:
    """Create a new project."""
    client = get_langgraph_client()

    # Create thread with project_team_agent
    thread = await client.threads.create()
    thread_id = thread["thread_id"]

    # Send initial message with objective
    await client.runs.create(
        thread_id,
        "project_team_agent",
        input={"messages": [{"role": "user", "content": request.objective}]}
    )

    return CreateProjectResponse(thread_id=thread_id)


@router.post("/{thread_id}/approve")
async def approve_project(thread_id: str) -> dict[str, str]:
    """Approve project plan."""
    client = get_langgraph_client()

    await client.runs.create(
        thread_id,
        "project_team_agent",
        input={"messages": [{"role": "user", "content": "/approve"}]}
    )

    return {"status": "approved"}


@router.post("/{thread_id}/revise")
async def revise_project(thread_id: str, request: ReviseProjectRequest) -> dict[str, str]:
    """Revise project plan with feedback."""
    client = get_langgraph_client()

    await client.runs.create(
        thread_id,
        "project_team_agent",
        input={"messages": [{"role": "user", "content": f"/revise {request.feedback}"}]}
    )

    return {"status": "revision_requested"}


@router.post("/{thread_id}/cancel")
async def cancel_project(thread_id: str) -> dict[str, str]:
    """Cancel project."""
    client = get_langgraph_client()

    await client.runs.create(
        thread_id,
        "project_team_agent",
        input={"messages": [{"role": "user", "content": "/cancel"}]}
    )

    return {"status": "cancelled"}


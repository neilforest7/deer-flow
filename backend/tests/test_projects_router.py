"""Tests for projects API router."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.gateway.routers import projects


@pytest.fixture
def mock_checkpointer():
    """Mock LangGraph checkpointer."""
    checkpointer = MagicMock()
    return checkpointer


@pytest.fixture
def mock_langgraph_client():
    """Mock LangGraph SDK client."""
    client = MagicMock()
    client.threads = MagicMock()
    client.runs = MagicMock()
    return client


@pytest.fixture
def sample_project_state():
    """Sample ProjectThreadState."""
    return {
        "messages": [],
        "phase": "awaiting_approval",
        "plan_status": "awaiting_approval",
        "project_brief": {
            "objective": "Build user authentication system",
            "scope": ["Login", "Registration"],
            "constraints": ["Use JWT"],
            "deliverables": ["Auth API"],
            "success_criteria": ["Tests pass"]
        },
        "work_orders": [
            {
                "id": "wo-1",
                "owner_agent": "backend-agent",
                "title": "Implement JWT auth",
                "goal": "Create JWT authentication",
                "read_scope": ["src/auth/"],
                "write_scope": ["src/auth/jwt.py"],
                "dependencies": [],
                "acceptance_checks": ["Unit tests pass"],
                "status": "pending"
            }
        ],
        "agent_reports": [],
        "qa_gate": None,
        "delivery_summary": None,
        "phase_artifacts": {}
    }


def test_list_projects_empty(mock_checkpointer):
    """Test listing projects when no project threads exist."""
    with patch.object(projects, "get_checkpointer", return_value=mock_checkpointer):
        mock_checkpointer.list.return_value = []

        result = projects.list_projects()

        assert len(result.projects) == 0


def test_list_projects_filters_project_team_agent(mock_checkpointer):
    """Test that only project_team_agent threads are returned."""
    with patch.object(projects, "get_checkpointer", return_value=mock_checkpointer):
        # Mock checkpointer returning mixed threads
        mock_checkpointer.list.return_value = [
            {
                "thread_id": "thread-1",
                "checkpoint": {
                    "channel_values": {
                        "phase": "planning",
                        "plan_status": "draft",
                        "project_brief": {"objective": "Project 1"}
                    }
                },
                "metadata": {"assistant_id": "project_team_agent"},
                "created_at": "2026-03-30T10:00:00Z",
                "updated_at": "2026-03-30T14:00:00Z"
            },
            {
                "thread_id": "thread-2",
                "checkpoint": {"channel_values": {}},
                "metadata": {"assistant_id": "lead_agent"},  # Should be filtered out
                "created_at": "2026-03-30T11:00:00Z",
                "updated_at": "2026-03-30T15:00:00Z"
            }
        ]

        result = projects.list_projects()

        assert len(result.projects) == 1
        assert result.projects[0].id == "thread-1"
        assert result.projects[0].title == "Project 1"


def test_list_projects_uses_untitled_fallback(mock_checkpointer):
    """Test that projects without objective use 'Untitled Project' as title."""
    with patch.object(projects, "get_checkpointer", return_value=mock_checkpointer):
        mock_checkpointer.list.return_value = [
            {
                "thread_id": "thread-1",
                "checkpoint": {
                    "channel_values": {
                        "phase": "intake",
                        "plan_status": "draft",
                        "project_brief": None
                    }
                },
                "metadata": {"assistant_id": "project_team_agent"},
                "created_at": "2026-03-30T10:00:00Z",
                "updated_at": "2026-03-30T14:00:00Z"
            }
        ]

        result = projects.list_projects()

        assert result.projects[0].title == "Untitled Project"


def test_get_project_detail_success(mock_checkpointer, sample_project_state):
    """Test getting project detail."""
    with patch.object(projects, "get_checkpointer", return_value=mock_checkpointer):
        mock_checkpointer.get.return_value = {
            "checkpoint": {"channel_values": sample_project_state},
            "metadata": {"assistant_id": "project_team_agent"},
            "created_at": "2026-03-30T10:00:00Z",
            "updated_at": "2026-03-30T14:00:00Z"
        }

        result = projects.get_project_detail("thread-123")

        assert result.id == "thread-123"
        assert result.title == "Build user authentication system"
        assert result.phase == "awaiting_approval"
        assert len(result.work_orders) == 1


def test_get_project_detail_not_found(mock_checkpointer):
    """Test getting non-existent project."""
    with patch.object(projects, "get_checkpointer", return_value=mock_checkpointer):
        mock_checkpointer.get.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            projects.get_project_detail("nonexistent")

        assert exc_info.value.status_code == 404


def test_create_project_success(mock_langgraph_client):
    """Test creating a new project."""
    with patch.object(projects, "get_langgraph_client", return_value=mock_langgraph_client):
        mock_langgraph_client.threads.create = AsyncMock(return_value={"thread_id": "new-thread-123"})
        mock_langgraph_client.runs.create = AsyncMock()

        request = projects.CreateProjectRequest(objective="Build auth system")
        result = asyncio.run(projects.create_project(request))

        assert result.thread_id == "new-thread-123"
        mock_langgraph_client.threads.create.assert_called_once()


def test_approve_project_success(mock_langgraph_client):
    """Test approving a project plan."""
    with patch.object(projects, "get_langgraph_client", return_value=mock_langgraph_client):
        mock_langgraph_client.runs.create = AsyncMock()

        result = asyncio.run(projects.approve_project("thread-123"))

        assert result["status"] == "approved"
        mock_langgraph_client.runs.create.assert_called_once()
        call_args = mock_langgraph_client.runs.create.call_args
        assert "/approve" in str(call_args)


def test_revise_project_success(mock_langgraph_client):
    """Test revising a project plan with feedback."""
    with patch.object(projects, "get_langgraph_client", return_value=mock_langgraph_client):
        mock_langgraph_client.runs.create = AsyncMock()

        request = projects.ReviseProjectRequest(feedback="Add error handling")
        result = asyncio.run(projects.revise_project("thread-123", request))

        assert result["status"] == "revision_requested"
        mock_langgraph_client.runs.create.assert_called_once()
        call_args = mock_langgraph_client.runs.create.call_args
        assert "/revise" in str(call_args)
        assert "Add error handling" in str(call_args)


def test_cancel_project_success(mock_langgraph_client):
    """Test canceling a project."""
    with patch.object(projects, "get_langgraph_client", return_value=mock_langgraph_client):
        mock_langgraph_client.runs.create = AsyncMock()

        result = asyncio.run(projects.cancel_project("thread-123"))

        assert result["status"] == "cancelled"
        mock_langgraph_client.runs.create.assert_called_once()
        call_args = mock_langgraph_client.runs.create.call_args
        assert "/cancel" in str(call_args)

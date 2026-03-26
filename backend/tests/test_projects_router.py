from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.gateway.routers import projects
from deerflow.projects import build_initial_project_state
from deerflow.store import ProjectStoreRepository


class _StoreItem:
    def __init__(self, value):
        self.value = value


class FakeStore:
    def __init__(self):
        self._data: dict[tuple[str, ...], dict[str, dict]] = {}

    def get(self, namespace, key):
        value = self._data.get(tuple(namespace), {}).get(key)
        return _StoreItem(value) if value is not None else None

    def put(self, namespace, key, value):
        self._data.setdefault(tuple(namespace), {})[key] = value

    def delete(self, namespace, key):
        self._data.get(tuple(namespace), {}).pop(key, None)

    def search(self, namespace, limit=100, offset=0):
        values = list(self._data.get(tuple(namespace), {}).values())
        sliced = values[offset : offset + limit]
        return [_StoreItem(value) for value in sliced]


class FakeThreadsClient:
    def __init__(self):
        self.created: list[dict] = []
        self.updated: list[dict] = []
        self.states: dict[str, dict] = {}

    async def create(self, **kwargs):
        self.created.append(kwargs)
        thread_id = kwargs["thread_id"]
        self.states.setdefault(thread_id, {"values": {}})
        return {"thread_id": thread_id}

    async def update_state(self, thread_id, values, **kwargs):
        self.updated.append({"thread_id": thread_id, "values": values, **kwargs})
        current_values = self.states.setdefault(thread_id, {"values": {}})["values"]
        current_values.update(values or {})
        return {"thread_id": thread_id}

    async def get_state(self, thread_id, *args, **kwargs):
        return self.states.get(thread_id, {"values": {}})


class FakeRunsClient:
    def __init__(self):
        self.created: list[dict] = []
        self.fail_with: Exception | None = None

    async def create(self, thread_id, assistant_id, **kwargs):
        if self.fail_with is not None:
            raise self.fail_with
        self.created.append(
            {
                "thread_id": thread_id,
                "assistant_id": assistant_id,
                **kwargs,
            }
        )
        return {"run_id": "run-123"}


class FakeLangGraphClient:
    def __init__(self):
        self.threads = FakeThreadsClient()
        self.runs = FakeRunsClient()


def test_create_project_route_bootstraps_project_thread():
    fake_store = FakeStore()
    fake_client = FakeLangGraphClient()
    app = FastAPI()
    app.include_router(projects.router)

    with (
        patch("app.gateway.routers.projects.get_store", return_value=fake_store),
        patch("app.gateway.routers.projects._get_langgraph_client", return_value=fake_client),
    ):
        with TestClient(app) as client:
            response = client.post(
                "/api/projects",
                json={
                    "title": "Project Delivery OS",
                    "objective": "Ship the project runtime",
                },
            )

    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "Project Delivery OS"
    assert body["assistant_id"] == "project_lead_agent"
    assert body["thread_id"] == body["project_id"]
    assert fake_client.threads.created[0]["graph_id"] == "project_lead_agent"


def test_control_project_route_updates_control_flags():
    fake_store = FakeStore()
    fake_client = FakeLangGraphClient()
    repo = ProjectStoreRepository(fake_store)
    repo.ensure_default_team()

    project_id = "project-123"
    thread_id = project_id
    initial_state = build_initial_project_state(
        project_id=project_id,
        title="Project Delivery OS",
        objective="Ship the project runtime",
    )
    repo.put_project_index(
        project_id,
        {
            "project_id": project_id,
            "thread_id": thread_id,
            "assistant_id": "project_lead_agent",
            "visible_agent_name": "lead-agent",
            "title": "Project Delivery OS",
            "description": "Ship the project runtime",
            "status": "draft",
            "phase": "intake",
            "team_name": "software-delivery-default",
            "created_at": "2026-03-26T00:00:00Z",
        },
    )
    repo.put_project_snapshot(
        project_id,
        {
            "project_title": "Project Delivery OS",
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
    fake_client.threads.states[thread_id] = {"values": initial_state}

    app = FastAPI()
    app.include_router(projects.router)

    with (
        patch("app.gateway.routers.projects.get_store", return_value=fake_store),
        patch("app.gateway.routers.projects._get_langgraph_client", return_value=fake_client),
    ):
        with TestClient(app) as client:
            pause_response = client.post(
                f"/api/projects/{project_id}/actions",
                json={"action": "pause"},
            )
            resume_response = client.post(
                f"/api/projects/{project_id}/actions",
                json={"action": "resume"},
            )

    assert pause_response.status_code == 200
    assert pause_response.json()["control_flags"]["pause_requested"] is True
    assert resume_response.status_code == 200
    assert resume_response.json()["control_flags"]["pause_requested"] is False


def test_resume_project_route_starts_new_run_for_paused_project():
    fake_store = FakeStore()
    fake_client = FakeLangGraphClient()
    repo = ProjectStoreRepository(fake_store)
    repo.ensure_default_team()

    project_id = "project-paused"
    initial_state = build_initial_project_state(
        project_id=project_id,
        title="Paused Project",
        objective="Resume work",
    )
    initial_state["project_status"] = "paused"
    repo.put_project_index(
        project_id,
        {
            "project_id": project_id,
            "thread_id": project_id,
            "assistant_id": "project_lead_agent",
            "visible_agent_name": "lead-agent",
            "title": "Paused Project",
            "description": "Resume work",
            "status": "paused",
            "phase": "build",
            "team_name": "software-delivery-default",
            "created_at": "2026-03-26T00:00:00Z",
        },
    )
    repo.put_project_snapshot(
        project_id,
        {
            "project_title": "Paused Project",
            "project_brief": initial_state["project_brief"],
            "work_orders": [],
            "agent_reports": [],
            "gate_decision": None,
            "delivery_pack": None,
            "active_batch": None,
            "artifacts": [],
        },
    )
    paused_control = dict(initial_state["control_flags"])
    paused_control["pause_requested"] = True
    repo.put_project_control(project_id, paused_control)
    fake_client.threads.states[project_id] = {"values": initial_state}

    app = FastAPI()
    app.include_router(projects.router)

    with (
        patch("app.gateway.routers.projects.get_store", return_value=fake_store),
        patch("app.gateway.routers.projects._get_langgraph_client", return_value=fake_client),
    ):
        with TestClient(app) as client:
            response = client.post(
                f"/api/projects/{project_id}/actions",
                json={"action": "resume"},
            )

    assert response.status_code == 200
    assert response.json()["control_flags"]["pause_requested"] is False
    assert len(fake_client.runs.created) == 1
    created_run = fake_client.runs.created[0]
    assert created_run["thread_id"] == project_id
    assert created_run["assistant_id"] == "project_lead_agent"
    assert created_run["context"]["project_id"] == project_id
    assert created_run["config"]["configurable"]["subagent_enabled"] is True


def test_resume_project_route_rolls_back_control_flags_when_run_creation_fails():
    fake_store = FakeStore()
    fake_client = FakeLangGraphClient()
    fake_client.runs.fail_with = RuntimeError("boom")
    repo = ProjectStoreRepository(fake_store)
    repo.ensure_default_team()

    project_id = "project-fail-resume"
    initial_state = build_initial_project_state(
        project_id=project_id,
        title="Paused Project",
        objective="Resume work",
    )
    initial_state["project_status"] = "paused"
    repo.put_project_index(
        project_id,
        {
            "project_id": project_id,
            "thread_id": project_id,
            "assistant_id": "project_lead_agent",
            "visible_agent_name": "lead-agent",
            "title": "Paused Project",
            "description": "Resume work",
            "status": "paused",
            "phase": "build",
            "team_name": "software-delivery-default",
            "created_at": "2026-03-26T00:00:00Z",
        },
    )
    repo.put_project_snapshot(
        project_id,
        {
            "project_title": "Paused Project",
            "project_brief": initial_state["project_brief"],
            "work_orders": [],
            "agent_reports": [],
            "gate_decision": None,
            "delivery_pack": None,
            "active_batch": None,
            "artifacts": [],
        },
    )
    paused_control = dict(initial_state["control_flags"])
    paused_control["pause_requested"] = True
    repo.put_project_control(project_id, paused_control)
    fake_client.threads.states[project_id] = {"values": initial_state}

    app = FastAPI()
    app.include_router(projects.router)

    with (
        patch("app.gateway.routers.projects.get_store", return_value=fake_store),
        patch("app.gateway.routers.projects._get_langgraph_client", return_value=fake_client),
    ):
        with TestClient(app) as client:
            response = client.post(
                f"/api/projects/{project_id}/actions",
                json={"action": "resume"},
            )

    assert response.status_code == 502
    assert repo.get_project_control(project_id)["pause_requested"] is True


def test_project_teams_router_crud():
    fake_store = FakeStore()
    app = FastAPI()
    app.include_router(projects.router)

    with patch("app.gateway.routers.projects.get_store", return_value=fake_store):
        with TestClient(app) as client:
            create_response = client.post(
                "/api/project-teams/custom-team",
                json={
                    "description": "Custom delivery team",
                    "visible_agent_name": "lead-agent",
                    "phases": ["intake", "build"],
                    "specialists": [{"name": "backend-agent"}],
                    "routing_policy": {},
                    "qa_policy": {},
                    "delivery_policy": {},
                },
            )
            list_response = client.get("/api/project-teams")

    assert create_response.status_code == 201
    assert create_response.json()["name"] == "custom-team"
    assert list_response.status_code == 200
    team_names = [team["name"] for team in list_response.json()["teams"]]
    assert "custom-team" in team_names
    assert "software-delivery-default" in team_names

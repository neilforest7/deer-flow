from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.gateway.routers import observability
from deerflow.config.tracing_config import TracingConfig


class DummyRun:
    def __init__(
        self,
        *,
        run_id: str,
        name: str,
        run_type: str,
        trace_id: str,
        parent_run_id: str | None = None,
        status: str | None = "success",
        thread_id: str | None = None,
        request_id: str | None = None,
        custom_trace_id: str | None = None,
        child_runs: list[dict] | None = None,
    ) -> None:
        self.id = run_id
        self.name = name
        self.run_type = run_type
        self.trace_id = trace_id
        self.parent_run_id = parent_run_id
        self.status = status
        self.error = None
        self.start_time = datetime(2026, 3, 29, 1, 2, 3, tzinfo=UTC)
        self.end_time = datetime(2026, 3, 29, 1, 3, 3, tzinfo=UTC)
        self.tags = ["project-team"]
        self.extra = {
            "metadata": {
                "thread_id": thread_id,
                "request_id": request_id,
                "trace_id": custom_trace_id,
            }
        }
        self._child_runs = child_runs or []

    def model_dump(self, mode: str = "python") -> dict:
        payload = {
            "id": self.id,
            "name": self.name,
            "run_type": self.run_type,
            "trace_id": self.trace_id,
            "parent_run_id": self.parent_run_id,
            "status": self.status,
            "child_runs": self._child_runs,
        }
        if mode == "json":
            payload["start_time"] = self.start_time.isoformat()
            payload["end_time"] = self.end_time.isoformat()
        return payload


class FakeLangSmithClient:
    def __init__(self, runs: list[DummyRun] | None = None, trace: DummyRun | None = None) -> None:
        self.runs = runs or []
        self.trace = trace
        self.list_runs_kwargs: dict | None = None
        self.read_run_kwargs: dict | None = None

    def list_runs(self, **kwargs):
        self.list_runs_kwargs = kwargs
        return iter(self.runs)

    def read_run(self, run_id: str, load_child_runs: bool = False):
        self.read_run_kwargs = {"run_id": run_id, "load_child_runs": load_child_runs}
        if self.trace is None:
            raise AssertionError("trace not configured")
        return self.trace


def _make_client() -> TestClient:
    app = FastAPI()
    app.include_router(observability.router)
    return TestClient(app)


def test_get_langsmith_config_returns_effective_settings(monkeypatch):
    monkeypatch.setattr(
        observability,
        "get_tracing_config",
        lambda: TracingConfig(
            enabled=True,
            api_key="lsv2_test",
            project="deerflow-teamv2",
            endpoint="https://smith.example.com",
        ),
    )

    with _make_client() as client:
        response = client.get("/api/observability/langsmith/config")

    assert response.status_code == 200
    assert response.json() == {
        "enabled": True,
        "configured": True,
        "api_key_present": True,
        "project": "deerflow-teamv2",
        "endpoint": "https://smith.example.com",
    }


def test_list_langsmith_runs_filters_by_thread_metadata(monkeypatch):
    config = TracingConfig(
        enabled=True,
        api_key="lsv2_test",
        project="deerflow-teamv2",
        endpoint="https://smith.example.com",
    )
    fake_client = FakeLangSmithClient(
        runs=[
            DummyRun(
                run_id="run-1",
                name="LangGraph",
                run_type="chain",
                trace_id="trace-1",
                thread_id="thread-a",
                request_id="req-a",
                custom_trace_id="custom-a",
            ),
            DummyRun(
                run_id="run-2",
                name="LangGraph",
                run_type="chain",
                trace_id="trace-2",
                thread_id="thread-b",
                request_id="req-b",
                custom_trace_id="custom-b",
            ),
        ]
    )
    monkeypatch.setattr(observability, "_require_tracing_config", lambda: config)
    monkeypatch.setattr(observability, "_build_langsmith_client", lambda _config: fake_client)

    with _make_client() as client:
        response = client.get("/api/observability/langsmith/runs?root_only=true&thread_id=thread-b&limit=20")

    assert response.status_code == 200
    body = response.json()
    assert body["project"] == "deerflow-teamv2"
    assert body["count"] == 1
    assert body["runs"][0]["id"] == "run-2"
    assert body["runs"][0]["thread_id"] == "thread-b"
    assert body["runs"][0]["custom_trace_id"] == "custom-b"
    assert fake_client.list_runs_kwargs == {
        "project_name": "deerflow-teamv2",
        "trace_id": None,
        "run_type": None,
        "is_root": True,
        "error": None,
        "start_time": None,
        "limit": 100,
    }


def test_list_langsmith_runs_returns_503_when_tracing_not_configured(monkeypatch):
    monkeypatch.setattr(
        observability,
        "_require_tracing_config",
        lambda: (_ for _ in ()).throw(
            observability.HTTPException(status_code=503, detail="LangSmith tracing is not configured.")
        ),
    )

    with _make_client() as client:
        response = client.get("/api/observability/langsmith/runs")

    assert response.status_code == 503
    assert response.json()["detail"] == "LangSmith tracing is not configured."


def test_get_langsmith_trace_returns_tree(monkeypatch):
    config = TracingConfig(
        enabled=True,
        api_key="lsv2_test",
        project="deerflow-teamv2",
        endpoint="https://smith.example.com",
    )
    trace = DummyRun(
        run_id="trace-1",
        name="LangGraph",
        run_type="chain",
        trace_id="trace-1",
        child_runs=[
            {
                "id": "child-1",
                "name": "__start__",
                "run_type": "chain",
                "trace_id": "trace-1",
                "child_runs": [
                    {
                        "id": "grandchild-1",
                        "name": "build",
                        "run_type": "chain",
                        "trace_id": "trace-1",
                        "child_runs": [],
                    }
                ],
            }
        ],
    )
    fake_client = FakeLangSmithClient(trace=trace)

    monkeypatch.setattr(observability, "_require_tracing_config", lambda: config)
    monkeypatch.setattr(observability, "_build_langsmith_client", lambda _config: fake_client)

    with _make_client() as client:
        response = client.get("/api/observability/langsmith/traces/trace-1")

    assert response.status_code == 200
    body = response.json()
    assert body["project"] == "deerflow-teamv2"
    assert body["trace_id"] == "trace-1"
    assert body["run_count"] == 3
    assert body["root_run"]["id"] == "trace-1"
    assert body["root_run"]["child_runs"][0]["id"] == "child-1"
    assert fake_client.read_run_kwargs == {"run_id": "trace-1", "load_child_runs": True}

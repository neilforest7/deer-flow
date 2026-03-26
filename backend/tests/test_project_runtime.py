from types import SimpleNamespace
from unittest.mock import patch

from langchain_core.messages import AIMessage, ToolMessage

from deerflow.agents.middlewares.project_dispatch_middleware import ProjectDispatchMiddleware
from deerflow.projects import (
    compute_project_state_projection,
    merge_canonical_work_orders,
    select_active_batch,
)


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


def _runtime(max_parallelism: int = 3):
    return SimpleNamespace(config={"configurable": {"max_concurrent_subagents": max_parallelism}}, context={})


def test_select_active_batch_skips_conflicting_writers_and_blocked_dependencies():
    work_orders = [
        {
            "id": "backend-api",
            "owner_agent": "backend-agent",
            "description": "Build API",
            "prompt": "",
            "goal": "Build API",
            "write_scope": ["backend/api"],
            "read_scope": [],
            "dependencies": [],
            "verification_steps": [],
            "done_definition": [],
            "status": "planned",
            "phase": "build",
            "result": "",
            "updated_at": "2026-03-26T00:00:00Z",
        },
        {
            "id": "backend-models",
            "owner_agent": "backend-agent",
            "description": "Build models",
            "prompt": "",
            "goal": "Build models",
            "write_scope": ["backend/api/models"],
            "read_scope": [],
            "dependencies": [],
            "verification_steps": [],
            "done_definition": [],
            "status": "planned",
            "phase": "build",
            "result": "",
            "updated_at": "2026-03-26T00:00:00Z",
        },
        {
            "id": "frontend-ui",
            "owner_agent": "frontend-agent",
            "description": "Build UI",
            "prompt": "",
            "goal": "Build UI",
            "write_scope": ["frontend/src/app"],
            "read_scope": [],
            "dependencies": ["backend-api"],
            "verification_steps": [],
            "done_definition": [],
            "status": "planned",
            "phase": "build",
            "result": "",
            "updated_at": "2026-03-26T00:00:00Z",
        },
    ]

    batch = select_active_batch(work_orders, phase="build", max_parallelism=3, now="2026-03-26T00:00:00Z")

    assert batch is not None
    assert batch["work_order_ids"] == ["backend-api"]
    assert batch["status"] == "ready"


def test_compute_project_state_projection_promotes_planner_work_orders():
    planner_report = """
## summary
- Planned the implementation

```json
{
  "work_orders": [
    {
      "id": "backend-api",
      "owner_agent": "backend-agent",
      "description": "Implement API",
      "goal": "Implement API",
      "write_scope": ["backend/api"],
      "read_scope": [],
      "dependencies": [],
      "verification_steps": ["pytest backend/tests/test_api.py"],
      "done_definition": ["API tests pass"]
    },
    {
      "id": "frontend-ui",
      "owner_agent": "frontend-agent",
      "description": "Implement UI",
      "goal": "Implement UI",
      "write_scope": ["frontend/src/app"],
      "read_scope": [],
      "dependencies": [],
      "verification_steps": ["pnpm check"],
      "done_definition": ["UI renders correctly"]
    }
  ]
}
```
"""
    state = {
        "project_phase": "planning",
        "project_status": "active",
        "control_flags": {"pause_requested": False, "abort_requested": False},
        "work_orders": [],
        "agent_reports": [],
        "artifacts": [],
        "messages": [
            AIMessage(
                content="",
                id="ai-1",
                tool_calls=[
                    {
                        "name": "task",
                        "id": "planner-call",
                        "args": {
                            "description": "execution plan",
                            "prompt": "Plan the work",
                            "subagent_type": "planner-agent",
                        },
                    }
                ],
            ),
            ToolMessage(content=planner_report, tool_call_id="planner-call", name="task"),
        ],
    }

    projection = compute_project_state_projection(state, control_flags=state["control_flags"], max_parallelism=3)
    work_order_ids = {item["id"] for item in projection["work_orders"]}

    assert "backend-api" in work_order_ids
    assert "frontend-ui" in work_order_ids
    assert projection["project_phase"] == "build"
    assert projection["active_batch"]["work_order_ids"] == ["backend-api", "frontend-ui"]


def test_compute_project_state_projection_qa_fail_invalidates_delivery_pack():
    state = {
        "project_phase": "delivery",
        "project_status": "ready_for_delivery",
        "control_flags": {"pause_requested": False, "abort_requested": False},
        "work_orders": [],
        "agent_reports": [],
        "delivery_pack": {
            "status": "packaged",
            "artifacts": ["artifact.zip"],
            "notes": ["ready"],
            "updated_at": "2026-03-26T00:00:00Z",
        },
        "artifacts": ["artifact.zip"],
        "messages": [
            AIMessage(
                content="",
                id="ai-qa",
                tool_calls=[
                    {
                        "name": "task",
                        "id": "qa-call",
                        "args": {
                            "description": "qa gate",
                            "prompt": "Validate the release",
                            "subagent_type": "qa-agent",
                            "work_order_id": "qa-gate",
                        },
                    }
                ],
            ),
            ToolMessage(
                content="""
## summary
- QA found a blocking regression
## blockers
- login flow fails
Status: fail
""",
                tool_call_id="qa-call",
                name="task",
            ),
        ],
    }

    projection = compute_project_state_projection(state, control_flags=state["control_flags"], max_parallelism=1)

    assert projection["gate_decision"]["status"] == "fail"
    assert projection["delivery_pack"] is None
    assert projection["project_status"] == "rework_required"
    assert projection["project_phase"] in {"planning", "build"}


def test_merge_canonical_work_orders_preserves_completed_status():
    existing_orders = [
        {
            "id": "backend-api",
            "owner_agent": "backend-agent",
            "description": "Build API",
            "prompt": "",
            "goal": "Build API",
            "write_scope": ["backend/api"],
            "read_scope": [],
            "dependencies": [],
            "verification_steps": [],
            "done_definition": [],
            "status": "completed",
            "phase": "build",
            "result": "implemented and verified",
            "updated_at": "2026-03-26T00:00:00Z",
        },
        {
            "id": "frontend-ui",
            "owner_agent": "frontend-agent",
            "description": "Build UI",
            "prompt": "",
            "goal": "Build UI",
            "write_scope": ["frontend/src/app"],
            "read_scope": [],
            "dependencies": ["backend-api"],
            "verification_steps": [],
            "done_definition": [],
            "status": "planned",
            "phase": "build",
            "result": "",
            "updated_at": "2026-03-26T00:00:00Z",
        },
    ]

    canonical_orders = [
        {
            "id": "backend-api",
            "owner_agent": "backend-agent",
            "description": "Build API",
            "goal": "Build API",
            "write_scope": ["backend/api"],
            "read_scope": [],
            "dependencies": [],
            "verification_steps": [],
            "done_definition": [],
        },
        {
            "id": "frontend-ui",
            "owner_agent": "frontend-agent",
            "description": "Build UI",
            "goal": "Build UI",
            "write_scope": ["frontend/src/app"],
            "read_scope": [],
            "dependencies": ["backend-api"],
            "verification_steps": [],
            "done_definition": [],
        },
    ]

    merged_orders = merge_canonical_work_orders(
        existing_orders,
        canonical_orders,
        now="2026-03-26T01:00:00Z",
    )
    merged_by_id = {item["id"]: item for item in merged_orders}
    batch = select_active_batch(
        merged_orders,
        phase="build",
        max_parallelism=3,
        now="2026-03-26T01:00:00Z",
    )

    assert merged_by_id["backend-api"]["status"] == "completed"
    assert merged_by_id["backend-api"]["result"] == "implemented and verified"
    assert batch is not None
    assert batch["work_order_ids"] == ["frontend-ui"]


def test_project_dispatch_middleware_filters_to_active_batch():
    fake_store = FakeStore()
    middleware = ProjectDispatchMiddleware()
    state = {
        "team_name": "software-delivery-default",
        "project_phase": "build",
        "project_status": "active",
        "control_flags": {"pause_requested": False, "abort_requested": False},
        "work_orders": [
            {
                "id": "backend-api",
                "owner_agent": "backend-agent",
                "description": "Build API",
                "prompt": "",
                "goal": "Build API",
                "write_scope": ["backend/api"],
                "read_scope": [],
                "dependencies": [],
                "verification_steps": [],
                "done_definition": [],
                "status": "planned",
                "phase": "build",
                "result": "",
                "updated_at": "2026-03-26T00:00:00Z",
            },
            {
                "id": "frontend-ui",
                "owner_agent": "frontend-agent",
                "description": "Build UI",
                "prompt": "",
                "goal": "Build UI",
                "write_scope": ["frontend/src/app"],
                "read_scope": [],
                "dependencies": ["backend-api"],
                "verification_steps": [],
                "done_definition": [],
                "status": "planned",
                "phase": "build",
                "result": "",
                "updated_at": "2026-03-26T00:00:00Z",
            },
            {
                "id": "delivery-pack",
                "owner_agent": "delivery-agent",
                "description": "Package deliverables",
                "prompt": "",
                "goal": "Package deliverables",
                "write_scope": ["/mnt/user-data/outputs"],
                "read_scope": [],
                "dependencies": [],
                "verification_steps": [],
                "done_definition": [],
                "status": "planned",
                "phase": "delivery",
                "result": "",
                "updated_at": "2026-03-26T00:00:00Z",
            },
        ],
        "agent_reports": [],
        "artifacts": [],
        "messages": [
            AIMessage(
                content="",
                id="ai-build",
                tool_calls=[
                    {
                        "name": "task",
                        "id": "valid-build",
                        "args": {
                            "description": "Build API",
                            "prompt": "Implement the API",
                            "subagent_type": "backend-agent",
                            "work_order_id": "backend-api",
                        },
                    },
                    {
                        "name": "task",
                        "id": "blocked-build",
                        "args": {
                            "description": "Build UI",
                            "prompt": "Implement the UI",
                            "subagent_type": "frontend-agent",
                            "work_order_id": "frontend-ui",
                        },
                    },
                    {
                        "name": "task",
                        "id": "wrong-phase",
                        "args": {
                            "description": "Package release",
                            "prompt": "Package the release",
                            "subagent_type": "delivery-agent",
                            "work_order_id": "delivery-pack",
                        },
                    },
                ],
            )
        ],
    }

    with patch("deerflow.agents.middlewares.project_dispatch_middleware.get_store", return_value=fake_store):
        update = middleware.after_model(state, _runtime())

    assert update is not None
    assert update["active_batch"]["work_order_ids"] == ["backend-api"]
    filtered_ids = [tool_call["args"]["work_order_id"] for tool_call in update["messages"][0].tool_calls]
    assert filtered_ids == ["backend-api"]


def test_project_dispatch_middleware_wrap_tool_call_requires_work_order_id():
    fake_store = FakeStore()
    middleware = ProjectDispatchMiddleware()
    state = {
        "team_name": "software-delivery-default",
        "project_phase": "build",
        "project_status": "active",
        "control_flags": {"pause_requested": False, "abort_requested": False},
        "work_orders": [
            {
                "id": "backend-api",
                "owner_agent": "backend-agent",
                "description": "Build API",
                "prompt": "",
                "goal": "Build API",
                "write_scope": ["backend/api"],
                "read_scope": [],
                "dependencies": [],
                "verification_steps": [],
                "done_definition": [],
                "status": "planned",
                "phase": "build",
                "result": "",
                "updated_at": "2026-03-26T00:00:00Z",
            }
        ],
        "agent_reports": [],
        "artifacts": [],
        "messages": [],
    }
    request = SimpleNamespace(
        state=state,
        runtime=_runtime(),
        tool_call={
            "name": "task",
            "id": "tool-call-1",
            "args": {
                "description": "Build API",
                "prompt": "Implement the API",
                "subagent_type": "backend-agent",
            },
        },
    )

    with patch("deerflow.agents.middlewares.project_dispatch_middleware.get_store", return_value=fake_store):
        result = middleware.wrap_tool_call(
            request,
            lambda _request: ToolMessage(
                content="ok",
                tool_call_id="tool-call-1",
                name="task",
            ),
        )

    assert isinstance(result, ToolMessage)
    assert result.status == "error"
    assert "work_order_id" in str(result.content)

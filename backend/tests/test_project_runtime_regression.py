import json
from pathlib import Path

from deerflow.agents import make_lead_agent
from deerflow.agents.middlewares.memory_middleware import MemoryMiddleware
from deerflow.agents.middlewares.tool_error_handling_middleware import build_subagent_runtime_middlewares
from deerflow.client import DeerFlowClient


def test_langgraph_only_registers_lead_agent():
    langgraph_path = Path(__file__).parent.parent / "langgraph.json"
    payload = json.loads(langgraph_path.read_text(encoding="utf-8"))

    assert payload["graphs"]["lead_agent"] == "deerflow.agents:make_lead_agent"


def test_lead_agent_entrypoint_remains_available():
    assert callable(make_lead_agent)


def test_client_defaults_do_not_enable_project_runtime():
    client = DeerFlowClient.__new__(DeerFlowClient)
    client._model_name = None
    client._thinking_enabled = True
    client._subagent_enabled = False
    client._plan_mode = False

    config = client._get_runnable_config("thread-1")

    assert config["configurable"]["thread_id"] == "thread-1"
    assert config["configurable"]["subagent_enabled"] is False
    assert "runtime_name" not in config["configurable"]


def test_project_runtime_import_does_not_change_harness_boundary():
    from deerflow import project_runtime

    assert project_runtime is not None


def test_project_runtime_subagents_do_not_include_memory_writeback_middleware():
    middlewares = build_subagent_runtime_middlewares(lazy_init=True)

    assert not any(isinstance(middleware, MemoryMiddleware) for middleware in middlewares)

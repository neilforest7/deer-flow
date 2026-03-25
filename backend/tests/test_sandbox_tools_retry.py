from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import deerflow.sandbox.tools as tools_module
from deerflow.sandbox.exceptions import SandboxTransportError


class FailingSandbox:
    def __init__(self) -> None:
        self.writes: list[tuple[str, str, bool]] = []

    def write_file(self, path: str, content: str, append: bool = False) -> None:
        self.writes.append((path, content, append))
        raise SandboxTransportError(
            "connection refused",
            operation="write_file",
            sandbox_url="http://stale-sandbox",
        )


class HealthySandbox:
    def __init__(self) -> None:
        self.writes: list[tuple[str, str, bool]] = []

    def write_file(self, path: str, content: str, append: bool = False) -> None:
        self.writes.append((path, content, append))


def test_write_file_tool_retries_after_transport_error(monkeypatch):
    runtime = SimpleNamespace(
        state={"sandbox": {"sandbox_id": "stale-sandbox"}},
        context={"thread_id": "thread-1"},
        config={},
    )
    provider = MagicMock()
    healthy_sandbox = HealthySandbox()
    sandboxes = [FailingSandbox(), healthy_sandbox]

    def fake_ensure_sandbox_initialized(current_runtime):
        sandbox = sandboxes.pop(0)
        if sandbox is healthy_sandbox:
            current_runtime.state["sandbox"] = {"sandbox_id": "healthy-sandbox"}
        return sandbox

    monkeypatch.setattr(tools_module, "get_sandbox_provider", lambda: provider)
    monkeypatch.setattr(tools_module, "ensure_sandbox_initialized", fake_ensure_sandbox_initialized)
    monkeypatch.setattr(tools_module, "ensure_thread_directories_exist", lambda _runtime: None)
    monkeypatch.setattr(tools_module, "is_local_sandbox", lambda _runtime: False)

    result = tools_module.write_file_tool.func(
        runtime=runtime,
        description="save artifact",
        path="/mnt/user-data/outputs/index.html",
        content="<html></html>",
    )

    assert result == "OK"
    provider.destroy.assert_called_once_with("stale-sandbox")
    assert healthy_sandbox.writes == [
        ("/mnt/user-data/outputs/index.html", "<html></html>", False)
    ]
    assert runtime.state["sandbox"] == {"sandbox_id": "healthy-sandbox"}


def test_write_file_tool_stops_after_second_transport_error(monkeypatch):
    runtime = SimpleNamespace(
        state={"sandbox": {"sandbox_id": "stale-sandbox"}},
        context={"thread_id": "thread-1"},
        config={},
    )
    provider = MagicMock()
    sandboxes = [FailingSandbox(), FailingSandbox()]

    def fake_ensure_sandbox_initialized(_runtime):
        return sandboxes.pop(0)

    monkeypatch.setattr(tools_module, "get_sandbox_provider", lambda: provider)
    monkeypatch.setattr(tools_module, "ensure_sandbox_initialized", fake_ensure_sandbox_initialized)
    monkeypatch.setattr(tools_module, "ensure_thread_directories_exist", lambda _runtime: None)
    monkeypatch.setattr(tools_module, "is_local_sandbox", lambda _runtime: False)

    result = tools_module.write_file_tool.func(
        runtime=runtime,
        description="save artifact",
        path="/mnt/user-data/outputs/index.html",
        content="<html></html>",
    )

    assert result.startswith("Error: connection refused")
    provider.destroy.assert_called_once_with("stale-sandbox")
    assert runtime.state == {}


def test_write_file_tool_retry_preserves_append_flag(monkeypatch):
    runtime = SimpleNamespace(
        state={"sandbox": {"sandbox_id": "stale-sandbox"}},
        context={"thread_id": "thread-1"},
        config={},
    )
    provider = MagicMock()
    failing_sandbox = FailingSandbox()
    healthy_sandbox = HealthySandbox()
    sandboxes = [failing_sandbox, healthy_sandbox]

    def fake_ensure_sandbox_initialized(current_runtime):
        sandbox = sandboxes.pop(0)
        if sandbox is healthy_sandbox:
            current_runtime.state["sandbox"] = {"sandbox_id": "healthy-sandbox"}
        return sandbox

    monkeypatch.setattr(tools_module, "get_sandbox_provider", lambda: provider)
    monkeypatch.setattr(tools_module, "ensure_sandbox_initialized", fake_ensure_sandbox_initialized)
    monkeypatch.setattr(tools_module, "ensure_thread_directories_exist", lambda _runtime: None)
    monkeypatch.setattr(tools_module, "is_local_sandbox", lambda _runtime: False)

    result = tools_module.write_file_tool.func(
        runtime=runtime,
        description="append artifact",
        path="/mnt/user-data/outputs/index.html",
        content="<footer></footer>",
        append=True,
    )

    assert result == "OK"
    provider.destroy.assert_called_once_with("stale-sandbox")
    assert failing_sandbox.writes == [
        ("/mnt/user-data/outputs/index.html", "<footer></footer>", True),
    ]
    assert healthy_sandbox.writes == [
        ("/mnt/user-data/outputs/index.html", "<footer></footer>", True),
    ]
    assert runtime.state["sandbox"] == {"sandbox_id": "healthy-sandbox"}

from __future__ import annotations

import threading
from unittest.mock import MagicMock

import deerflow.community.aio_sandbox.aio_sandbox_provider as provider_module
from deerflow.community.aio_sandbox.sandbox_info import SandboxInfo


def _make_provider() -> provider_module.AioSandboxProvider:
    provider = provider_module.AioSandboxProvider.__new__(provider_module.AioSandboxProvider)
    provider._lock = threading.Lock()
    provider._sandboxes = {}
    provider._sandbox_infos = {}
    provider._thread_sandboxes = {}
    provider._thread_locks = {}
    provider._last_activity = {}
    provider._warm_pool = {}
    provider._backend = MagicMock()
    return provider


def test_adopt_sandbox_info_rejects_unready_endpoint(monkeypatch):
    provider = _make_provider()
    info = SandboxInfo(sandbox_id="stale-1", sandbox_url="http://stale")

    provider._backend.is_alive.return_value = False
    monkeypatch.setattr(provider_module, "wait_for_sandbox_ready", lambda _url, timeout=10: False)

    adopted = provider._adopt_sandbox_info("thread-1", info, source="discovered")

    assert adopted is None
    provider._backend.destroy.assert_called_once_with(info)
    assert provider._sandboxes == {}
    assert provider._sandbox_infos == {}


def test_adopt_sandbox_info_rejects_ready_but_not_alive(monkeypatch):
    provider = _make_provider()
    info = SandboxInfo(sandbox_id="stale-2", sandbox_url="http://ready-but-dead")

    provider._backend.is_alive.return_value = False
    monkeypatch.setattr(provider_module, "wait_for_sandbox_ready", lambda _url, timeout=10: True)

    adopted = provider._adopt_sandbox_info("thread-2", info, source="warm-pool")

    assert adopted is None
    provider._backend.destroy.assert_called_once_with(info)
    assert provider._sandboxes == {}
    assert provider._sandbox_infos == {}


def test_acquire_recreates_stale_warm_pool_sandbox(monkeypatch):
    provider = _make_provider()
    thread_id = "thread-1"
    sandbox_id = provider_module.AioSandboxProvider._deterministic_sandbox_id(thread_id)
    info = SandboxInfo(sandbox_id=sandbox_id, sandbox_url="http://stale")
    provider._warm_pool[sandbox_id] = (info, 0.0)
    provider._backend.is_alive.return_value = False
    provider._backend.discover.return_value = None

    monkeypatch.setattr(provider_module, "wait_for_sandbox_ready", lambda _url, timeout=10: False)
    monkeypatch.setattr(provider, "_create_sandbox", lambda _thread_id, _sandbox_id: "fresh-sandbox")

    acquired = provider._acquire_internal(thread_id)

    assert acquired == "fresh-sandbox"
    provider._backend.destroy.assert_called_once_with(info)
    assert sandbox_id not in provider._warm_pool

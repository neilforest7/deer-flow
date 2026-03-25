from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

import scripts.cleanup_stale_langgraph_runs as cleanup_module
from scripts.cleanup_stale_langgraph_runs import find_stale_runs, is_stale_run


def _ts(hour: int, minute: int) -> str:
    return datetime(2026, 3, 25, hour, minute, tzinfo=UTC).isoformat()


def test_is_stale_run_only_matches_running_runs_older_than_boot() -> None:
    boot_time = datetime(2026, 3, 25, 2, 23, 38, tzinfo=UTC)

    assert is_stale_run({"status": "running", "created_at": _ts(2, 0)}, boot_time)
    assert not is_stale_run({"status": "pending", "created_at": _ts(2, 0)}, boot_time)
    assert not is_stale_run({"status": "success", "created_at": _ts(2, 0)}, boot_time)
    assert not is_stale_run({"status": "running", "created_at": _ts(3, 0)}, boot_time)
    assert not is_stale_run({"status": "running"}, boot_time)


def test_find_stale_runs_filters_to_busy_threads_with_stale_running_runs() -> None:
    boot_time = datetime(2026, 3, 25, 2, 23, 38, tzinfo=UTC)
    threads = [
        {"thread_id": "busy-thread", "status": "busy"},
        {"thread_id": "idle-thread", "status": "idle"},
    ]
    runs_by_thread = {
        "busy-thread": [
            {"run_id": "old-running", "status": "running", "created_at": _ts(2, 0)},
            {"run_id": "new-pending", "status": "pending", "created_at": _ts(3, 0)},
            {"run_id": "success", "status": "success", "created_at": _ts(1, 0)},
        ],
        "idle-thread": [
            {"run_id": "ignored", "status": "running", "created_at": _ts(1, 0)},
        ],
    }

    assert find_stale_runs(threads, runs_by_thread, boot_time) == [
        ("busy-thread", "old-running", "running"),
    ]


def test_find_stale_runs_ignores_old_pending_runs() -> None:
    boot_time = datetime(2026, 3, 25, 2, 23, 38, tzinfo=UTC)
    threads = [{"thread_id": "busy-thread", "status": "busy"}]
    runs_by_thread = {
        "busy-thread": [
            {"run_id": "old-pending", "status": "pending", "created_at": _ts(2, 0)},
            {"run_id": "old-running", "status": "running", "created_at": _ts(2, 0)},
        ],
    }

    assert find_stale_runs(threads, runs_by_thread, boot_time) == [
        ("busy-thread", "old-running", "running"),
    ]


def test_list_busy_threads_pages_over_all_busy_threads(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    def fake_json_request(base_url: str, path: str, *, method: str = "GET", payload=None, include_headers: bool = False):
        assert base_url == "http://langgraph"
        assert path == "/threads/search"
        assert method == "POST"
        assert include_headers is True
        calls.append(payload)
        pages = {
            0: [{"thread_id": "busy-1", "status": "busy"}, {"thread_id": "busy-2", "status": "busy"}],
            2: [{"thread_id": "busy-3", "status": "busy"}],
        }
        next_offsets = {0: "2"}
        return pages.get(payload["offset"], []), {"x-pagination-next": next_offsets.get(payload["offset"])}

    monkeypatch.setattr(cleanup_module, "json_request", fake_json_request)

    assert cleanup_module.list_busy_threads("http://langgraph", search_limit=2) == [
        {"thread_id": "busy-1", "status": "busy"},
        {"thread_id": "busy-2", "status": "busy"},
        {"thread_id": "busy-3", "status": "busy"},
    ]
    assert calls == [
        {
            "status": "busy",
            "limit": 2,
            "offset": 0,
            "sort_by": "thread_id",
            "sort_order": "asc",
            "select": ["thread_id", "status"],
        },
        {
            "status": "busy",
            "limit": 2,
            "offset": 2,
            "sort_by": "thread_id",
            "sort_order": "asc",
            "select": ["thread_id", "status"],
        },
    ]


def test_list_busy_threads_returns_none_for_invalid_pagination_header(monkeypatch) -> None:
    def fake_json_request(base_url: str, path: str, *, method: str = "GET", payload=None, include_headers: bool = False):
        assert base_url == "http://langgraph"
        assert path == "/threads/search"
        assert include_headers is True
        return [{"thread_id": "busy-1", "status": "busy"}], {"x-pagination-next": "bad-offset"}

    monkeypatch.setattr(cleanup_module, "json_request", fake_json_request)

    assert cleanup_module.list_busy_threads("http://langgraph", search_limit=1) is None


def test_list_thread_runs_pages_over_all_runs(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(cleanup_module, "RUN_SEARCH_LIMIT", 1)

    def fake_json_request(base_url: str, path: str, *, method: str = "GET", payload=None, include_headers: bool = False):
        assert base_url == "http://langgraph"
        assert method == "GET"
        assert include_headers is False
        calls.append(path)
        parsed = urlparse(path)
        query = parse_qs(parsed.query)
        offset = int(query["offset"][0])
        assert query["limit"] == ["1"]
        assert query["select"] == ["run_id", "status", "created_at"]
        pages = {
            0: [{"run_id": "run-1", "status": "success", "created_at": _ts(3, 0)}],
            1: [{"run_id": "run-2", "status": "running", "created_at": _ts(2, 0)}],
        }
        return pages.get(offset, [])

    monkeypatch.setattr(cleanup_module, "json_request", fake_json_request)

    assert cleanup_module.list_thread_runs("http://langgraph", "busy-1") == [
        {"run_id": "run-1", "status": "success", "created_at": _ts(3, 0)},
        {"run_id": "run-2", "status": "running", "created_at": _ts(2, 0)},
    ]
    assert calls == [
        "/threads/busy-1/runs?limit=1&offset=0&select=run_id&select=status&select=created_at",
        "/threads/busy-1/runs?limit=1&offset=1&select=run_id&select=status&select=created_at",
        "/threads/busy-1/runs?limit=1&offset=2&select=run_id&select=status&select=created_at",
    ]


def test_cleanup_stale_runs_cancels_stale_runs_found_on_later_search_pages(monkeypatch) -> None:
    boot_time = datetime(2026, 3, 25, 2, 23, 38, tzinfo=UTC)
    cancelled: list[str] = []
    monkeypatch.setattr(cleanup_module, "RUN_SEARCH_LIMIT", 1)

    def fake_json_request(base_url: str, path: str, *, method: str = "GET", payload=None, include_headers: bool = False):
        assert base_url == "http://langgraph"
        if path == "/threads/search":
            pages = {
                0: [{"thread_id": "busy-1", "status": "busy"}],
                7: [{"thread_id": "busy-2", "status": "busy"}],
            }
            next_offsets = {0: "7"}
            return pages.get(payload["offset"], []), {"x-pagination-next": next_offsets.get(payload["offset"])}
        if path == "/threads/busy-1/runs?limit=1&offset=0&select=run_id&select=status&select=created_at":
            return [{"run_id": "fresh", "status": "running", "created_at": _ts(3, 0)}]
        if path == "/threads/busy-1/runs?limit=1&offset=1&select=run_id&select=status&select=created_at":
            return []
        if path == "/threads/busy-2/runs?limit=1&offset=0&select=run_id&select=status&select=created_at":
            return [{"run_id": "fresh-2", "status": "success", "created_at": _ts(3, 0)}]
        if path == "/threads/busy-2/runs?limit=1&offset=1&select=run_id&select=status&select=created_at":
            return [{"run_id": "stale", "status": "running", "created_at": _ts(2, 0)}]
        if path == "/threads/busy-2/runs?limit=1&offset=2&select=run_id&select=status&select=created_at":
            return []
        if path == "/threads/busy-2/runs/stale/cancel":
            cancelled.append(path)
            return None
        raise AssertionError(f"Unexpected request: {method} {path} {payload}")

    monkeypatch.setattr(cleanup_module, "json_request", fake_json_request)

    assert cleanup_module.cleanup_stale_runs("http://langgraph", boot_time, search_limit=1) == 1
    assert cancelled == ["/threads/busy-2/runs/stale/cancel"]


def test_cleanup_stale_runs_collects_all_pages_before_cancelling(monkeypatch) -> None:
    boot_time = datetime(2026, 3, 25, 2, 23, 38, tzinfo=UTC)
    cancelled = False
    request_order: list[str] = []
    monkeypatch.setattr(cleanup_module, "RUN_SEARCH_LIMIT", 1)

    def fake_json_request(base_url: str, path: str, *, method: str = "GET", payload=None, include_headers: bool = False):
        nonlocal cancelled
        assert base_url == "http://langgraph"
        request_order.append(path)
        if path == "/threads/search":
            offset = payload["offset"]
            if offset == 0:
                return [{"thread_id": "busy-1", "status": "busy"}], {"x-pagination-next": "1"}
            if offset == 1:
                if cancelled:
                    return [], {}
                return [{"thread_id": "busy-2", "status": "busy"}], {"x-pagination-next": "2"}
            return [], {}
        if path == "/threads/busy-1/runs?limit=1&offset=0&select=run_id&select=status&select=created_at":
            return [{"run_id": "stale-1", "status": "running", "created_at": _ts(2, 0)}]
        if path == "/threads/busy-1/runs?limit=1&offset=1&select=run_id&select=status&select=created_at":
            return []
        if path == "/threads/busy-2/runs?limit=1&offset=0&select=run_id&select=status&select=created_at":
            return [{"run_id": "stale-2", "status": "pending", "created_at": _ts(2, 0)}]
        if path == "/threads/busy-2/runs?limit=1&offset=1&select=run_id&select=status&select=created_at":
            return []
        if path == "/threads/busy-1/runs/stale-1/cancel":
            cancelled = True
            return None
        raise AssertionError(f"Unexpected request: {method} {path} {payload}")

    monkeypatch.setattr(cleanup_module, "json_request", fake_json_request)

    assert cleanup_module.cleanup_stale_runs("http://langgraph", boot_time, search_limit=1) == 1
    assert request_order[:3] == [
        "/threads/search",
        "/threads/search",
        "/threads/search",
    ]


def test_cleanup_stale_runs_aborts_when_run_listing_is_unexpected(monkeypatch) -> None:
    boot_time = datetime(2026, 3, 25, 2, 23, 38, tzinfo=UTC)

    def fake_json_request(base_url: str, path: str, *, method: str = "GET", payload=None, include_headers: bool = False):
        assert base_url == "http://langgraph"
        if path == "/threads/search":
            pages = {0: [{"thread_id": "busy-1", "status": "busy"}]}
            return pages.get(payload["offset"], []), {"x-pagination-next": None}
        if path == "/threads/busy-1/runs?limit=100&offset=0&select=run_id&select=status&select=created_at":
            return {"unexpected": True}
        raise AssertionError(f"Unexpected request: {method} {path} {payload}")

    monkeypatch.setattr(cleanup_module, "json_request", fake_json_request)

    assert cleanup_module.cleanup_stale_runs("http://langgraph", boot_time, search_limit=1) == 0


def test_cleanup_stale_runs_counts_only_successful_cancellations(monkeypatch) -> None:
    boot_time = datetime(2026, 3, 25, 2, 23, 38, tzinfo=UTC)

    def fake_json_request(base_url: str, path: str, *, method: str = "GET", payload=None, include_headers: bool = False):
        assert base_url == "http://langgraph"
        if path == "/threads/search":
            pages = {0: [{"thread_id": "busy-1", "status": "busy"}]}
            return pages.get(payload["offset"], []), {"x-pagination-next": None}
        if path == "/threads/busy-1/runs?limit=100&offset=0&select=run_id&select=status&select=created_at":
            return [
                {"run_id": "stale-1", "status": "running", "created_at": _ts(2, 0)},
                {"run_id": "stale-2", "status": "running", "created_at": _ts(2, 1)},
                {"run_id": "old-pending", "status": "pending", "created_at": _ts(2, 0)},
            ]
        if path == "/threads/busy-1/runs/stale-1/cancel":
            return None
        if path == "/threads/busy-1/runs/stale-2/cancel":
            raise RuntimeError("cancel failed")
        raise AssertionError(f"Unexpected request: {method} {path} {payload}")

    monkeypatch.setattr(cleanup_module, "json_request", fake_json_request)

    assert cleanup_module.cleanup_stale_runs("http://langgraph", boot_time, search_limit=1) == 1

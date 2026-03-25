from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

STALE_RUN_STATUSES = {"running"}
THREAD_SEARCH_LIMIT_MAX = 1000
THREAD_SEARCH_FIELDS = ["thread_id", "status"]
RUN_SEARCH_LIMIT = 100
RUN_SEARCH_FIELDS = ["run_id", "status", "created_at"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Cancel stale LangGraph runs left behind by a previous server instance.",
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:2024",
        help="LangGraph base URL. Defaults to http://127.0.0.1:2024",
    )
    parser.add_argument(
        "--boot-time",
        required=True,
        help="UTC ISO8601 timestamp captured before the current LangGraph process starts.",
    )
    parser.add_argument(
        "--ready-timeout",
        type=float,
        default=60.0,
        help="Seconds to wait for LangGraph readiness before giving up.",
    )
    parser.add_argument(
        "--search-limit",
        type=int,
        default=200,
        help="Number of busy threads to fetch per /threads/search page during cleanup.",
    )
    return parser.parse_args()


def parse_timestamp(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def json_request(
    base_url: str,
    path: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    include_headers: bool = False,
) -> Any:
    data = None
    headers: dict[str, str] = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = Request(
        f"{base_url.rstrip('/')}{path}",
        data=data,
        headers=headers,
        method=method,
    )
    with urlopen(request, timeout=20) as response:
        body = response.read()
        parsed_body = None if not body else json.loads(body)
        if include_headers:
            return parsed_body, response.headers
        return parsed_body


def wait_until_ready(base_url: str, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            request = Request(f"{base_url.rstrip('/')}/ok", method="GET")
            with urlopen(request, timeout=5) as response:
                if response.status == 200:
                    return True
        except (HTTPError, URLError, TimeoutError):
            pass
        time.sleep(1)
    return False


def is_stale_run(run: dict[str, Any], boot_time: datetime) -> bool:
    status = run.get("status")
    created_at = run.get("created_at")
    if status not in STALE_RUN_STATUSES or not isinstance(created_at, str):
        return False
    try:
        return parse_timestamp(created_at) < boot_time
    except ValueError:
        return False


def find_stale_runs(
    threads: list[dict[str, Any]],
    runs_by_thread: dict[str, list[dict[str, Any]]],
    boot_time: datetime,
) -> list[tuple[str, str, str]]:
    stale: list[tuple[str, str, str]] = []
    for thread in threads:
        if thread.get("status") != "busy":
            continue
        thread_id = thread.get("thread_id")
        if not isinstance(thread_id, str):
            continue
        for run in runs_by_thread.get(thread_id, []):
            run_id = run.get("run_id")
            status = run.get("status")
            if not isinstance(run_id, str) or not isinstance(status, str):
                continue
            if is_stale_run(run, boot_time):
                stale.append((thread_id, run_id, status))
    return stale


def list_busy_threads(base_url: str, search_limit: int) -> list[dict[str, Any]] | None:
    page_size = max(1, min(search_limit, THREAD_SEARCH_LIMIT_MAX))
    offset = 0
    threads: list[dict[str, Any]] = []

    while True:
        response = json_request(
            base_url,
            "/threads/search",
            method="POST",
            payload={
                "status": "busy",
                "limit": page_size,
                "offset": offset,
                "sort_by": "thread_id",
                "sort_order": "asc",
                "select": THREAD_SEARCH_FIELDS,
            },
            include_headers=True,
        )
        if not (
            isinstance(response, tuple)
            and len(response) == 2
            and isinstance(response[0], list)
        ):
            return None
        page, headers = response

        threads.extend(thread for thread in page if isinstance(thread, dict))
        # LangGraph exposes pagination via X-Pagination-Next; fall back to page length only when absent.
        next_offset_raw = headers.get("x-pagination-next")
        if next_offset_raw is None:
            if len(page) < page_size:
                return threads
            offset += len(page)
            continue

        try:
            next_offset = int(next_offset_raw)
        except (TypeError, ValueError):
            return None
        if next_offset <= offset:
            return None
        offset = next_offset


def list_thread_runs(base_url: str, thread_id: str) -> list[dict[str, Any]] | None:
    offset = 0
    runs: list[dict[str, Any]] = []

    while True:
        query = urlencode(
            {
                "limit": RUN_SEARCH_LIMIT,
                "offset": offset,
                "select": RUN_SEARCH_FIELDS,
            },
            doseq=True,
        )
        page = json_request(base_url, f"/threads/{thread_id}/runs?{query}")
        if not isinstance(page, list):
            return None

        runs.extend(run for run in page if isinstance(run, dict))
        if len(page) < RUN_SEARCH_LIMIT:
            return runs
        offset += len(page)


def cleanup_stale_runs(base_url: str, boot_time: datetime, search_limit: int) -> int:
    threads = list_busy_threads(base_url, search_limit)
    if threads is None:
        print("Stale-run cleanup skipped: unexpected /threads/search response.", file=sys.stderr)
        return 0

    runs_by_thread: dict[str, list[dict[str, Any]]] = {}
    for thread in threads:
        thread_id = thread.get("thread_id")
        if thread.get("status") != "busy" or not isinstance(thread_id, str):
            continue
        runs = list_thread_runs(base_url, thread_id)
        if runs is None:
            print(
                f"Stale-run cleanup skipped: unexpected /threads/{thread_id}/runs response.",
                file=sys.stderr,
            )
            return 0
        runs_by_thread[thread_id] = runs

    stale_runs = find_stale_runs(threads, runs_by_thread, boot_time)
    cancelled_count = 0
    for thread_id, run_id, status in stale_runs:
        try:
            json_request(
                base_url,
                f"/threads/{thread_id}/runs/{run_id}/cancel",
                method="POST",
                payload={},
            )
            print(
                f"Cancelled stale running LangGraph run {run_id} ({status}) on thread {thread_id}.",
                flush=True,
            )
            cancelled_count += 1
        except Exception as exc:  # pragma: no cover - defensive logging path
            print(
                f"Failed to cancel stale LangGraph run {run_id} on thread {thread_id}: {exc}",
                file=sys.stderr,
                flush=True,
            )
    return cancelled_count


def main() -> int:
    args = parse_args()
    boot_time = parse_timestamp(args.boot_time)
    if not wait_until_ready(args.base_url, args.ready_timeout):
        print(
            f"Stale-run cleanup skipped: LangGraph not ready at {args.base_url} within {args.ready_timeout:.0f}s.",
            file=sys.stderr,
            flush=True,
        )
        return 0

    cancelled = cleanup_stale_runs(args.base_url, boot_time, args.search_limit)
    print(f"Stale-run cleanup completed. Cancelled {cancelled} run(s).", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env bash
set -euo pipefail

BOOT_TIME="$(python3 - <<'PY'
from datetime import datetime, timezone

print(datetime.now(timezone.utc).isoformat())
PY
)"

cleanup_stale_runs() {
    NO_COLOR=1 uv run python scripts/cleanup_stale_langgraph_runs.py \
        --base-url "http://127.0.0.1:${LANGGRAPH_PORT:-2024}" \
        --boot-time "$BOOT_TIME"
}

cleanup_stale_runs &
exec uv run langgraph dev --no-browser --allow-blocking --no-reload "$@"

#!/usr/bin/env bash
#
# deploy-fridge-teamv2.sh - Deploy a branch to the Fridge test machine.
#
# This script connects to a remote host via SSH, updates the repo at the
# target directory using git, reuses the remote-local config files, runs the
# existing Docker production deployment flow, and performs smoke checks.

set -euo pipefail

usage() {
    cat <<'EOF'
Usage:
  ./scripts/deploy-fridge-teamv2.sh --host <ssh-target> [options]

Options:
  --host <ssh-target>   Remote SSH target, for example user@fridge
  --branch <branch>     Git branch to deploy (default: current local branch)
  --remote <name>       Git remote name on the server (default: origin)
  --repo-dir <path>     Remote repo path (default: /opt/deer-flow-teamv2)
  --port <port>         External HTTP port (default: 2026)
  --help                Show this help message
EOF
}

require_cmd() {
    local cmd="$1"
    if ! command -v "$cmd" >/dev/null 2>&1; then
        echo "Missing required command: $cmd" >&2
        exit 1
    fi
}

HOST=""
BRANCH=""
REMOTE_NAME="origin"
REPO_DIR="/opt/deer-flow-teamv2"
PORT="2026"

while [ "$#" -gt 0 ]; do
    case "$1" in
        --host)
            HOST="${2:-}"
            shift 2
            ;;
        --branch)
            BRANCH="${2:-}"
            shift 2
            ;;
        --remote)
            REMOTE_NAME="${2:-}"
            shift 2
            ;;
        --repo-dir)
            REPO_DIR="${2:-}"
            shift 2
            ;;
        --port)
            PORT="${2:-}"
            shift 2
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            echo "Unknown argument: $1" >&2
            usage >&2
            exit 1
            ;;
    esac
done

if [ -z "$HOST" ]; then
    echo "--host is required" >&2
    usage >&2
    exit 1
fi

require_cmd git
require_cmd ssh

if [ -z "$BRANCH" ]; then
    BRANCH="$(git branch --show-current)"
fi

if [ -z "$BRANCH" ]; then
    echo "Unable to determine current git branch. Pass --branch explicitly." >&2
    exit 1
fi

LOCAL_COMMIT="$(git rev-parse --short HEAD)"

echo "=========================================="
echo "  Fridge Test Deployment"
echo "=========================================="
echo ""
echo "Host:        $HOST"
echo "Repo dir:    $REPO_DIR"
echo "Remote:      $REMOTE_NAME"
echo "Branch:      $BRANCH"
echo "Local HEAD:  $LOCAL_COMMIT"
echo "Port:        $PORT"
echo ""

ssh "$HOST" \
    "BRANCH=$(printf '%q' "$BRANCH") REMOTE_NAME=$(printf '%q' "$REMOTE_NAME") REPO_DIR=$(printf '%q' "$REPO_DIR") PORT=$(printf '%q' "$PORT") bash -s" <<'EOF'
set -euo pipefail

print_step() {
    echo ""
    echo "==> $1"
}

fail() {
    echo ""
    echo "✗ $1" >&2
    exit 1
}

require_cmd() {
    local cmd="$1"
    if ! command -v "$cmd" >/dev/null 2>&1; then
        fail "Missing required command on remote host: $cmd"
    fi
}

prepare_compose_env() {
    export DEER_FLOW_HOME="${DEER_FLOW_HOME:-$REPO_DIR/backend/.deer-flow}"
    export DEER_FLOW_CONFIG_PATH="${DEER_FLOW_CONFIG_PATH:-$REPO_DIR/config.yaml}"
    export DEER_FLOW_EXTENSIONS_CONFIG_PATH="${DEER_FLOW_EXTENSIONS_CONFIG_PATH:-$REPO_DIR/extensions_config.json}"
    export DEER_FLOW_DOCKER_SOCKET="${DEER_FLOW_DOCKER_SOCKET:-/var/run/docker.sock}"
    export DEER_FLOW_REPO_ROOT="${DEER_FLOW_REPO_ROOT:-$REPO_DIR}"

    if [ -z "${BETTER_AUTH_SECRET:-}" ]; then
        local secret_file="$DEER_FLOW_HOME/.better-auth-secret"
        if [ -f "$secret_file" ]; then
            BETTER_AUTH_SECRET="$(cat "$secret_file")"
        else
            BETTER_AUTH_SECRET="placeholder"
        fi
        export BETTER_AUTH_SECRET
    fi
}

compose_cmd() {
    prepare_compose_env
    docker compose -p deer-flow -f "$REPO_DIR/docker/docker-compose.yaml" "$@"
}

http_local() {
    curl --noproxy '127.0.0.1,localhost,::1' -fsS "$@"
}

retry_capture() {
    local output_var="$1"
    local attempts="$2"
    local delay_seconds="$3"
    shift 3

    local attempt=""
    local response=""
    for attempt in $(seq 1 "$attempts"); do
        if response="$("$@" 2>/dev/null)"; then
            printf -v "$output_var" '%s' "$response"
            return 0
        fi

        if [ "$attempt" -lt "$attempts" ]; then
            sleep "$delay_seconds"
        fi
    done

    if ! response="$("$@")"; then
        return 1
    fi

    printf -v "$output_var" '%s' "$response"
}

show_failure_diagnostics() {
    local compose_file="$REPO_DIR/docker/docker-compose.yaml"
    if [ -f "$compose_file" ] && command -v docker >/dev/null 2>&1; then
        echo ""
        echo "----- docker compose ps -----"
        compose_cmd ps || true
        for service in nginx gateway langgraph frontend; do
            echo ""
            echo "----- logs: $service -----"
            compose_cmd logs --tail 80 "$service" || true
        done
    fi
}

detect_sandbox_mode() {
    local config_path="$REPO_DIR/config.yaml"
    local sandbox_use=""
    local provisioner_url=""

    [ -f "$config_path" ] || { echo "local"; return; }

    sandbox_use=$(awk '
        /^[[:space:]]*sandbox:[[:space:]]*$/ { in_sandbox=1; next }
        in_sandbox && /^[^[:space:]#]/ { in_sandbox=0 }
        in_sandbox && /^[[:space:]]*use:[[:space:]]*/ {
            line=$0; sub(/^[[:space:]]*use:[[:space:]]*/, "", line); print line; exit
        }
    ' "$config_path")

    provisioner_url=$(awk '
        /^[[:space:]]*sandbox:[[:space:]]*$/ { in_sandbox=1; next }
        in_sandbox && /^[^[:space:]#]/ { in_sandbox=0 }
        in_sandbox && /^[[:space:]]*provisioner_url:[[:space:]]*/ {
            line=$0; sub(/^[[:space:]]*provisioner_url:[[:space:]]*/, "", line); print line; exit
        }
    ' "$config_path")

    if [[ "$sandbox_use" == *"deerflow.community.aio_sandbox:AioSandboxProvider"* ]]; then
        if [ -n "$provisioner_url" ]; then
            echo "provisioner"
        else
            echo "aio"
        fi
    else
        echo "local"
    fi
}

trap 'show_failure_diagnostics' ERR

print_step "Remote environment"
echo "Host:       $(hostname)"
echo "Repo dir:   $REPO_DIR"
echo "Remote:     $REMOTE_NAME"
echo "Branch:     $BRANCH"
echo "Port:       $PORT"

require_cmd git
require_cmd docker
require_cmd curl
require_cmd python3

if ! docker compose version >/dev/null 2>&1; then
    fail "docker compose is unavailable"
fi

if [ ! -d "$REPO_DIR/.git" ]; then
    fail "Remote path is not a git repository: $REPO_DIR"
fi

cd "$REPO_DIR"

print_step "Remote git update"
if [ -n "$(git status --short --untracked-files=no)" ]; then
    fail "Remote repo has uncommitted tracked changes"
fi

git fetch "$REMOTE_NAME" || fail "git fetch failed for remote $REMOTE_NAME"

if ! git show-ref --verify --quiet "refs/remotes/$REMOTE_NAME/$BRANCH"; then
    fail "Remote branch not found: $REMOTE_NAME/$BRANCH"
fi

if git show-ref --verify --quiet "refs/heads/$BRANCH"; then
    git checkout "$BRANCH" || fail "git checkout failed for branch $BRANCH"
else
    git checkout -b "$BRANCH" --track "$REMOTE_NAME/$BRANCH" || \
        fail "git checkout failed for new tracking branch $BRANCH"
fi
git pull --ff-only "$REMOTE_NAME" "$BRANCH" || fail "git pull --ff-only failed"

DEPLOY_COMMIT="$(git rev-parse --short HEAD)"
echo "Remote HEAD: $DEPLOY_COMMIT"

print_step "Config preflight"
for path in "$REPO_DIR/config.yaml" "$REPO_DIR/.env" "$REPO_DIR/frontend/.env"; do
    if [ ! -f "$path" ]; then
        fail "Required config file is missing: $path"
    fi
    echo "✓ Found $path"
done

SANDBOX_MODE="$(detect_sandbox_mode)"
echo "Detected sandbox mode: $SANDBOX_MODE"

if [ "$SANDBOX_MODE" != "local" ] && [ ! -S /var/run/docker.sock ]; then
    fail "Docker socket missing at /var/run/docker.sock for sandbox mode $SANDBOX_MODE"
fi
if [ "$SANDBOX_MODE" != "local" ]; then
    echo "✓ Docker socket available"
fi

print_step "Deploy"
./scripts/deploy.sh down
./scripts/deploy.sh up

print_step "Container status"
compose_cmd ps

print_step "HTTP smoke tests"
retry_capture HEALTH_JSON 30 1 http_local "http://127.0.0.1:$PORT/health"
python3 - "$HEALTH_JSON" <<'PY'
import json, sys
data = json.loads(sys.argv[1])
if data.get("status") != "healthy":
    raise SystemExit(f"Unexpected /health payload: {data}")
print(f"✓ /health -> {data}")
PY

retry_capture MODELS_JSON 15 1 http_local "http://127.0.0.1:$PORT/api/models"
python3 - "$MODELS_JSON" <<'PY'
import json, sys
data = json.loads(sys.argv[1])
if isinstance(data, list):
    models = data
elif isinstance(data, dict) and isinstance(data.get("models"), list):
    models = data["models"]
else:
    raise SystemExit(f"Unexpected /api/models payload: {data}")
print(f"✓ /api/models -> {len(models)} model entries")
PY

retry_capture THREAD_JSON 15 1 http_local -X POST "http://127.0.0.1:$PORT/api/langgraph/threads" \
    -H 'Content-Type: application/json' \
    -d '{}'
THREAD_ID="$(python3 - "$THREAD_JSON" <<'PY'
import json, sys
data = json.loads(sys.argv[1])
thread_id = data.get("thread_id") or data.get("thread", {}).get("thread_id")
if not thread_id:
    raise SystemExit(f"Unexpected /api/langgraph/threads payload: {data}")
print(thread_id)
PY
)"
echo "✓ /api/langgraph/threads -> created thread $THREAD_ID"

http_local "http://127.0.0.1:$PORT/api/langgraph/threads/$THREAD_ID/state" >/dev/null
echo "✓ /api/langgraph/threads/$THREAD_ID/state"

http_local -X DELETE "http://127.0.0.1:$PORT/api/langgraph/threads/$THREAD_ID" >/dev/null || true
http_local -X DELETE "http://127.0.0.1:$PORT/api/threads/$THREAD_ID" >/dev/null || true
echo "✓ Cleaned temporary thread $THREAD_ID"

print_step "Deployment complete"
echo "Branch:      $BRANCH"
echo "Commit:      $DEPLOY_COMMIT"
echo "Application: http://$(hostname):$PORT"
EOF

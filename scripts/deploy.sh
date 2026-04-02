#!/usr/bin/env bash
#
# deploy.sh - Build and start (or stop) DeerFlow production services
#
# Usage:
#   deploy.sh [up]   — build images and start containers (default)
#   deploy.sh down   — stop and remove containers
#
# Must be run from the repo root directory.

set -e

CMD="${1:-up}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

DOCKER_DIR="$REPO_ROOT/docker"
COMPOSE_CMD=(docker compose --env-file "$REPO_ROOT/.env" -p deer-flow -f "$DOCKER_DIR/docker-compose.yaml")

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

load_dotenv_value() {
    local key="$1"
    local env_file="$REPO_ROOT/.env"

    [ -f "$env_file" ] || return 0

    python3 - "$env_file" "$key" <<'EOF'
import sys
from pathlib import Path

env_file, key = sys.argv[1], sys.argv[2]
for raw_line in Path(env_file).read_text().splitlines():
    line = raw_line.strip()
    if not line or line.startswith('#') or '=' not in line:
        continue
    name, value = line.split('=', 1)
    if name.strip() != key:
        continue
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        value = value[1:-1]
    print(value)
    break
EOF
}

append_no_proxy_entry() {
    local value="$1"
    local entry="$2"

    case ",$value," in
        *",$entry,"*)
            printf '%s' "$value"
            ;;
        "")
            printf '%s' "$entry"
            ;;
        *)
            printf '%s,%s' "$value" "$entry"
            ;;
    esac
}

ensure_internal_no_proxy() {
    local current="${NO_PROXY:-}"
    local public_host
    local entry

    if [ -z "$current" ]; then
        current="$(load_dotenv_value NO_PROXY)"
    fi
    if [ -z "$current" ]; then
        current="${no_proxy:-}"
    fi
    if [ -z "$current" ]; then
        current="$(load_dotenv_value no_proxy)"
    fi

    public_host="$(printf '%s' "$BETTER_AUTH_BASE_URL" | sed -E 's#^[a-zA-Z]+://([^/:]+).*#\1#')"

    for entry in \
        localhost \
        127.0.0.1 \
        ::1 \
        host.docker.internal \
        gateway \
        langgraph \
        frontend \
        nginx \
        postgres \
        provisioner \
        deer-flow-gateway \
        deer-flow-langgraph \
        deer-flow-frontend \
        deer-flow-nginx \
        deer-flow-postgres \
        deer-flow-provisioner \
        "$public_host"; do
        [ -n "$entry" ] || continue
        current="$(append_no_proxy_entry "$current" "$entry")"
    done

    export NO_PROXY="$current"
    export no_proxy="$current"
}

if [ -z "$PORT" ]; then
    export PORT="$(load_dotenv_value PORT)"
fi
if [ -z "$PORT" ]; then
    export PORT=2026
fi

if [ -z "$BETTER_AUTH_BASE_URL" ]; then
    export BETTER_AUTH_BASE_URL="$(load_dotenv_value BETTER_AUTH_BASE_URL)"
fi
if [ -z "$BETTER_AUTH_BASE_URL" ]; then
    _public_host="${DEER_FLOW_PUBLIC_HOST:-}"
    if [ -z "$_public_host" ]; then
        _public_host="$(hostname -I 2>/dev/null | awk '{print $1}')"
    fi
    if [ -z "$_public_host" ]; then
        _public_host=localhost
    fi
    export BETTER_AUTH_BASE_URL="http://$_public_host:$PORT"
fi
echo -e "${GREEN}✓ BETTER_AUTH_BASE_URL=$BETTER_AUTH_BASE_URL${NC}"

if [ -z "$NEXT_PUBLIC_LANGGRAPH_BASE_URL" ]; then
    export NEXT_PUBLIC_LANGGRAPH_BASE_URL="$(load_dotenv_value NEXT_PUBLIC_LANGGRAPH_BASE_URL)"
fi
if [ -z "$NEXT_PUBLIC_LANGGRAPH_BASE_URL" ]; then
    export NEXT_PUBLIC_LANGGRAPH_BASE_URL=/api/langgraph
fi
echo -e "${GREEN}✓ NEXT_PUBLIC_LANGGRAPH_BASE_URL=$NEXT_PUBLIC_LANGGRAPH_BASE_URL${NC}"

ensure_internal_no_proxy
echo -e "${GREEN}✓ NO_PROXY includes DeerFlow internal hosts${NC}"

if [ -z "$DEER_FLOW_HOME" ]; then
    export DEER_FLOW_HOME="$REPO_ROOT/backend/.deer-flow"
fi
echo -e "${BLUE}DEER_FLOW_HOME=$DEER_FLOW_HOME${NC}"
mkdir -p "$DEER_FLOW_HOME"

export DEER_FLOW_REPO_ROOT="$REPO_ROOT"

if [ -z "$DEER_FLOW_CONFIG_PATH" ]; then
    export DEER_FLOW_CONFIG_PATH="$REPO_ROOT/config.yaml"
fi

if [ ! -f "$DEER_FLOW_CONFIG_PATH" ]; then
    if [ -f "$REPO_ROOT/config.example.yaml" ]; then
        cp "$REPO_ROOT/config.example.yaml" "$DEER_FLOW_CONFIG_PATH"
        echo -e "${GREEN}✓ Seeded config.example.yaml → $DEER_FLOW_CONFIG_PATH${NC}"
        echo -e "${YELLOW}⚠ config.yaml was seeded from the example template.${NC}"
        echo "  Edit $DEER_FLOW_CONFIG_PATH and set your model API keys before use."
    else
        echo -e "${RED}✗ No config.yaml found.${NC}"
        echo "  Run 'make config' from the repo root to generate one,"
        echo "  then set the required model API keys."
        exit 1
    fi
else
    echo -e "${GREEN}✓ config.yaml: $DEER_FLOW_CONFIG_PATH${NC}"
fi

if [ -z "$DEER_FLOW_EXTENSIONS_CONFIG_PATH" ]; then
    export DEER_FLOW_EXTENSIONS_CONFIG_PATH="$REPO_ROOT/extensions_config.json"
fi

if [ ! -f "$DEER_FLOW_EXTENSIONS_CONFIG_PATH" ]; then
    if [ -f "$REPO_ROOT/extensions_config.json" ]; then
        cp "$REPO_ROOT/extensions_config.json" "$DEER_FLOW_EXTENSIONS_CONFIG_PATH"
        echo -e "${GREEN}✓ Seeded extensions_config.json → $DEER_FLOW_EXTENSIONS_CONFIG_PATH${NC}"
    else
        echo '{"mcpServers":{},"skills":{}}' > "$DEER_FLOW_EXTENSIONS_CONFIG_PATH"
        echo -e "${YELLOW}⚠ extensions_config.json not found, created empty config at $DEER_FLOW_EXTENSIONS_CONFIG_PATH${NC}"
    fi
else
    echo -e "${GREEN}✓ extensions_config.json: $DEER_FLOW_EXTENSIONS_CONFIG_PATH${NC}"
fi

_secret_file="$DEER_FLOW_HOME/.better-auth-secret"
if [ -z "$BETTER_AUTH_SECRET" ]; then
    if [ -f "$_secret_file" ]; then
        export BETTER_AUTH_SECRET
        BETTER_AUTH_SECRET="$(cat "$_secret_file")"
        echo -e "${GREEN}✓ BETTER_AUTH_SECRET loaded from $_secret_file${NC}"
    else
        export BETTER_AUTH_SECRET
        BETTER_AUTH_SECRET="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
        echo "$BETTER_AUTH_SECRET" > "$_secret_file"
        chmod 600 "$_secret_file"
        echo -e "${GREEN}✓ BETTER_AUTH_SECRET generated → $_secret_file${NC}"
    fi
fi

detect_sandbox_mode() {
    local sandbox_use=""
    local provisioner_url=""

    [ -f "$DEER_FLOW_CONFIG_PATH" ] || { echo "local"; return; }

    sandbox_use=$(awk '
        /^[[:space:]]*sandbox:[[:space:]]*$/ { in_sandbox=1; next }
        in_sandbox && /^[^[:space:]#]/ { in_sandbox=0 }
        in_sandbox && /^[[:space:]]*use:[[:space:]]*/ {
            line=$0; sub(/^[[:space:]]*use:[[:space:]]*/, "", line); print line; exit
        }
    ' "$DEER_FLOW_CONFIG_PATH")

    provisioner_url=$(awk '
        /^[[:space:]]*sandbox:[[:space:]]*$/ { in_sandbox=1; next }
        in_sandbox && /^[^[:space:]#]/ { in_sandbox=0 }
        in_sandbox && /^[[:space:]]*provisioner_url:[[:space:]]*/ {
            line=$0; sub(/^[[:space:]]*provisioner_url:[[:space:]]*/, "", line); print line; exit
        }
    ' "$DEER_FLOW_CONFIG_PATH")

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

if [ "$CMD" = "down" ]; then
    export DEER_FLOW_HOME="${DEER_FLOW_HOME:-$REPO_ROOT/backend/.deer-flow}"
    export DEER_FLOW_CONFIG_PATH="${DEER_FLOW_CONFIG_PATH:-$DEER_FLOW_HOME/config.yaml}"
    export DEER_FLOW_EXTENSIONS_CONFIG_PATH="${DEER_FLOW_EXTENSIONS_CONFIG_PATH:-$DEER_FLOW_HOME/extensions_config.json}"
    export DEER_FLOW_DOCKER_SOCKET="${DEER_FLOW_DOCKER_SOCKET:-/var/run/docker.sock}"
    export DEER_FLOW_REPO_ROOT="${DEER_FLOW_REPO_ROOT:-$REPO_ROOT}"
    export BETTER_AUTH_SECRET="${BETTER_AUTH_SECRET:-placeholder}"
    "${COMPOSE_CMD[@]}" down
    exit 0
fi

echo "=========================================="
echo "  DeerFlow Production Deployment"
echo "=========================================="
echo ""

sandbox_mode="$(detect_sandbox_mode)"
echo -e "${BLUE}Sandbox mode: $sandbox_mode${NC}"

if [ "$sandbox_mode" = "provisioner" ]; then
    services=""
    extra_args="--profile provisioner"
else
    services="frontend gateway langgraph nginx"
    extra_args=""
fi

if [ -z "$DEER_FLOW_DOCKER_SOCKET" ]; then
    export DEER_FLOW_DOCKER_SOCKET="/var/run/docker.sock"
fi

if [ "$sandbox_mode" != "local" ]; then
    if [ ! -S "$DEER_FLOW_DOCKER_SOCKET" ]; then
        echo -e "${RED}⚠ Docker socket not found at $DEER_FLOW_DOCKER_SOCKET${NC}"
        echo "  AioSandboxProvider (DooD) will not work."
        exit 1
    else
        echo -e "${GREEN}✓ Docker socket: $DEER_FLOW_DOCKER_SOCKET${NC}"
    fi
fi

echo ""
echo "Building images and starting containers..."
echo ""

# shellcheck disable=SC2086
"${COMPOSE_CMD[@]}" $extra_args up --build -d --remove-orphans $services

echo ""
echo "=========================================="
echo "  DeerFlow is running!"
echo "=========================================="
echo ""
echo "  🌐 Application: $BETTER_AUTH_BASE_URL"
echo "  📡 API Gateway: $BETTER_AUTH_BASE_URL/api/*"
echo "  🤖 LangGraph:   $BETTER_AUTH_BASE_URL/api/langgraph/*"
echo ""
echo "  Manage:"
echo "    make down        — stop and remove containers"
echo "    make docker-logs — view logs"
echo ""

#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"

RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
NC='\033[0m'

log() { echo -e "${CYAN}[$1]${NC} $2"; }

force_kill_port() {
  local label="$1" port="$2"
  local pids
  pids=$(lsof -ti:"$port" 2>/dev/null || true)
  if [ -n "$pids" ]; then
    log "$label" "Force killing processes on port $port..."
    echo "$pids" | xargs kill -9 2>/dev/null || true
  else
    log "$label" "Port $port is free"
  fi
}

# ── Force kill by port ────────────────────────────────────────────

force_kill_port "UI"  3000
force_kill_port "API" 8000

# ── Force stop & remove Docker containers ─────────────────────────

log "DB" "Force stopping Docker containers..."
docker compose -f "$ROOT_DIR/docker-compose.yml" kill 2>/dev/null || true
docker compose -f "$ROOT_DIR/docker-compose.yml" down 2>/dev/null || true

# ── Kill anything still on port 27017 ─────────────────────────────

force_kill_port "DB" 27017

echo ""
echo -e "${GREEN}All services force stopped. Ports 3000, 8000, 27017 are free.${NC}"

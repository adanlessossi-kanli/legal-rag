#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

PIDS=()

cleanup() {
  echo ""
  echo -e "${YELLOW}Shutting down...${NC}"
  for pid in "${PIDS[@]}"; do
    kill -9 "$pid" 2>/dev/null || true
  done
  docker compose -f "$ROOT_DIR/docker-compose.yml" kill 2>/dev/null || true
  docker compose -f "$ROOT_DIR/docker-compose.yml" down 2>/dev/null || true
  echo -e "${GREEN}Stopped.${NC}"
  exit 0
}

trap cleanup SIGINT SIGTERM

log() { echo -e "${CYAN}[$1]${NC} $2"; }
err() { echo -e "${RED}[ERROR]${NC} $1" >&2; exit 1; }

# ── Preflight checks ──────────────────────────────────────────────

command -v docker >/dev/null 2>&1   || err "docker is not installed"
command -v node >/dev/null 2>&1     || err "node is not installed"
command -v python3 >/dev/null 2>&1 && PYTHON=python3 || PYTHON=python
command -v "$PYTHON" >/dev/null 2>&1 || err "python3 is not installed"

[ -f "$BACKEND_DIR/.env" ] || err "backend/.env not found. Copy backend/.env.example to backend/.env and configure it."

# ── 1. MongoDB ─────────────────────────────────────────────────────

log "DB" "Starting MongoDB..."
docker compose -f "$ROOT_DIR/docker-compose.yml" up -d

log "DB" "Waiting for MongoDB to be healthy (up to 60s)..."
for i in $(seq 1 60); do
  STATUS=$(docker inspect --format='{{.State.Health.Status}}' legal-rag-mongodb 2>/dev/null || echo "missing")
  if [ "$STATUS" = "healthy" ]; then
    log "DB" "MongoDB is healthy"
    break
  fi
  if [ "$STATUS" = "unhealthy" ]; then
    err "MongoDB container is unhealthy. Run 'docker logs legal-rag-mongodb' for details."
  fi
  [ "$i" -eq 60 ] && err "MongoDB did not become healthy within 60s (status: $STATUS)"
  sleep 1
done

# ── 2. Vector search index ─────────────────────────────────────────

log "DB" "Ensuring vector search index exists..."
(cd "$BACKEND_DIR" && "$PYTHON" "$ROOT_DIR/scripts/create_vector_index.py")

# ── 3. Backend ─────────────────────────────────────────────────────

log "API" "Setting up backend..."

if [ ! -d "$BACKEND_DIR/venv" ]; then
  log "API" "Creating Python virtual environment..."
  (cd "$BACKEND_DIR" && "$PYTHON" -m venv venv)
fi

# Activate venv
source "$BACKEND_DIR/venv/bin/activate"

log "API" "Installing Python dependencies..."
pip install -q -r "$BACKEND_DIR/requirements.txt"

log "API" "Starting backend on http://localhost:8000..."
(cd "$BACKEND_DIR" && uvicorn main:app --reload --host 0.0.0.0 --port 8000) &
PIDS+=($!)

# ── 4. Frontend ────────────────────────────────────────────────────

log "UI" "Setting up frontend..."

if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
  log "UI" "Installing npm dependencies..."
  (cd "$FRONTEND_DIR" && npm install)
fi

log "UI" "Starting frontend on http://localhost:3000..."
(cd "$FRONTEND_DIR" && npm run dev) &
PIDS+=($!)

# ── Ready ──────────────────────────────────────────────────────────

echo ""
echo -e "${GREEN}═══════════════════════════════════════════${NC}"
echo -e "${GREEN}  Legal RAG is starting up!${NC}"
echo -e "${GREEN}  Frontend : http://localhost:3000${NC}"
echo -e "${GREEN}  Backend  : http://localhost:8000${NC}"
echo -e "${GREEN}  API docs : http://localhost:8000/docs${NC}"
echo -e "${GREEN}  MongoDB  : localhost:27017${NC}"
echo -e "${GREEN}═══════════════════════════════════════════${NC}"
echo -e "${YELLOW}  Press Ctrl+C to stop all services${NC}"
echo ""

wait

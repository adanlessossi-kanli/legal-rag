@echo off
setlocal enabledelayedexpansion

set "ROOT_DIR=%~dp0"
set "ROOT_DIR=%ROOT_DIR:~0,-1%"
set "BACKEND_DIR=%ROOT_DIR%\backend"
set "FRONTEND_DIR=%ROOT_DIR%\frontend"

:: ── Preflight checks ──────────────────────────────────────────────

where docker >nul 2>&1 || (
  echo [ERROR] docker is not installed
  exit /b 1
)
where node >nul 2>&1 || (
  echo [ERROR] node is not installed
  exit /b 1
)
where python >nul 2>&1 || (
  echo [ERROR] python is not installed
  exit /b 1
)
if not exist "%BACKEND_DIR%\.env" (
  echo [ERROR] backend\.env not found. Copy backend\.env.example to backend\.env and configure it.
  exit /b 1
)

:: ── 1. MongoDB ─────────────────────────────────────────────────────

echo [DB] Starting MongoDB...
docker compose -f "%ROOT_DIR%\docker-compose.yml" up -d

echo [DB] Waiting for MongoDB to be healthy (up to 60s)...
set "READY=0"
for /l %%i in (1,1,60) do (
  if !READY! equ 0 (
    for /f "delims=" %%s in ('docker inspect --format "{{.State.Health.Status}}" legal-rag-mongodb 2^>nul') do (
      if "%%s"=="healthy" (
        echo [DB] MongoDB is healthy
        set "READY=1"
      )
      if "%%s"=="unhealthy" (
        echo [ERROR] MongoDB container is unhealthy. Run 'docker logs legal-rag-mongodb' for details.
        exit /b 1
      )
    )
    if !READY! equ 0 ping -n 2 127.0.0.1 >nul
  )
)
if !READY! equ 0 (
  echo [ERROR] MongoDB did not become healthy within 60s
  exit /b 1
)

:: ── 2. Vector search index ─────────────────────────────────────────

echo [DB] Ensuring vector search index exists...
pushd "%BACKEND_DIR%"
python "%ROOT_DIR%\scripts\create_vector_index.py"
popd

:: ── 3. Backend ─────────────────────────────────────────────────────

echo [API] Setting up backend...

if not exist "%BACKEND_DIR%\venv" (
  echo [API] Creating Python virtual environment...
  pushd "%BACKEND_DIR%"
  python -m venv venv
  popd
)

echo [API] Installing Python dependencies...
call "%BACKEND_DIR%\venv\Scripts\activate.bat"
pip install -q -r "%BACKEND_DIR%\requirements.txt"

echo [API] Starting backend on http://localhost:8000...
start "Legal RAG - Backend" cmd /c "cd /d "%BACKEND_DIR%" && call venv\Scripts\activate.bat && uvicorn main:app --reload --host 0.0.0.0 --port 8000"

:: ── 4. Frontend ────────────────────────────────────────────────────

echo [UI] Setting up frontend...

if not exist "%FRONTEND_DIR%\node_modules" (
  echo [UI] Installing npm dependencies...
  pushd "%FRONTEND_DIR%"
  call npm install
  popd
)

echo [UI] Starting frontend on http://localhost:3000...
start "Legal RAG - Frontend" cmd /c "cd /d "%FRONTEND_DIR%" && npm run dev"

:: ── Ready ──────────────────────────────────────────────────────────

echo.
echo ═══════════════════════════════════════════
echo   Legal RAG is starting up!
echo   Frontend : http://localhost:3000
echo   Backend  : http://localhost:8000
echo   API docs : http://localhost:8000/docs
echo   MongoDB  : localhost:27017
echo ═══════════════════════════════════════════
echo.
echo   Backend and Frontend are running in separate windows.
echo   Run stop.bat to shut down all services.
echo.

endlocal

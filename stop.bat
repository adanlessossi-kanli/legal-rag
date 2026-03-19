@echo off
setlocal enabledelayedexpansion

set "ROOT_DIR=%~dp0"
set "ROOT_DIR=%ROOT_DIR:~0,-1%"

:: ── Force kill by port ────────────────────────────────────────────

call :force_kill_port "UI"  3000
call :force_kill_port "API" 8000

:: ── Force stop & remove Docker containers ─────────────────────────

echo [DB] Force stopping Docker containers...
docker compose -f "%ROOT_DIR%\docker-compose.yml" kill >nul 2>&1
docker compose -f "%ROOT_DIR%\docker-compose.yml" down >nul 2>&1

:: ── Kill anything still on port 27017 ─────────────────────────────

call :force_kill_port "DB" 27017

echo.
echo All services force stopped. Ports 3000, 8000, 27017 are free.

endlocal
exit /b 0

:: ── Subroutine ────────────────────────────────────────────────────

:force_kill_port
set "LABEL=%~1"
set "PORT=%~2"
set "KILLED=0"
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":!PORT!.*LISTENING" 2^>nul') do (
  if %%p neq 0 (
    echo [!LABEL!] Force killing PID %%p on port !PORT!...
    taskkill /PID %%p /T /F >nul 2>&1
    set "KILLED=1"
  )
)
if !KILLED! equ 0 echo [!LABEL!] Port !PORT! is free
exit /b 0

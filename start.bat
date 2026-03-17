@echo off
setlocal EnableDelayedExpansion

set "ROOT=%~dp0"
set "DASHBOARD=%ROOT%dashboard"
set "LOGFILE=%ROOT%fraudshield.log"

echo [%date% %time%] FraudShield starting... >> "%LOGFILE%"
echo [FraudShield] Starting...

REM ── Kill any leftover processes from a previous run ──────────────────────
taskkill /f /im ngrok.exe >nul 2>&1
taskkill /f /fi "WINDOWTITLE eq FS-Dashboard*" >nul 2>&1
timeout /t 2 /nobreak >nul

REM ── Wait for internet ─────────────────────────────────────────────────────
:wait_internet
ping -n 1 8.8.8.8 >nul 2>&1
if errorlevel 1 (
    echo [FraudShield] No internet, retrying in 5s...
    timeout /t 5 /nobreak >nul
    goto wait_internet
)
echo [FraudShield] Internet OK.

REM ── Wait for Docker Desktop to be running ─────────────────────────────────
echo [FraudShield] Waiting for Docker...
:wait_docker
docker info >nul 2>&1
if errorlevel 1 (
    echo [FraudShield] Docker not ready, retrying in 5s...
    timeout /t 5 /nobreak >nul
    goto wait_docker
)
echo [FraudShield] Docker is ready.

REM ── Start backend stack (minus dashboard container) ───────────────────────
echo [FraudShield] Starting backend services...
cd /d "%ROOT%"
docker-compose up -d --remove-orphans >nul 2>&1
docker-compose stop dashboard >nul 2>&1
echo [FraudShield] Backend services started.

REM ── Wait for api-gateway to be healthy ────────────────────────────────────
echo [FraudShield] Waiting for api-gateway...
set /a GTRIES=0
:wait_api
timeout /t 5 /nobreak >nul
curl -s http://localhost:8080/health >nul 2>&1
if not errorlevel 1 goto api_ready
set /a GTRIES+=1
if !GTRIES! lss 24 goto wait_api
echo [FraudShield] WARNING: api-gateway not healthy after 2 min, continuing anyway...
:api_ready
echo [FraudShield] API gateway is up.

REM ── Start dashboard ───────────────────────────────────────────────────────
:start_dashboard
echo [FraudShield] Starting dashboard...
start "FS-Dashboard" cmd /k "title FS-Dashboard && cd /d "%DASHBOARD%" && npm run dev"

REM Wait for vite to be ready (up to 60s)
set /a TRIES=0
:wait_dashboard
timeout /t 3 /nobreak >nul
curl -s -o nul -w "%%{http_code}" http://localhost:3000 2>nul | findstr /r "^[23]" >nul 2>&1
if not errorlevel 1 goto dashboard_ready
set /a TRIES+=1
if !TRIES! lss 20 goto wait_dashboard
echo [FraudShield] Dashboard failed to start. Retrying...
taskkill /f /fi "WINDOWTITLE eq FS-Dashboard*" >nul 2>&1
timeout /t 3 /nobreak >nul
goto start_dashboard

:dashboard_ready
echo [FraudShield] Dashboard is up on port 3000.

REM ── Start ngrok ───────────────────────────────────────────────────────────
:start_ngrok
taskkill /f /im ngrok.exe >nul 2>&1
timeout /t 2 /nobreak >nul
echo [FraudShield] Starting ngrok...
start "FS-Ngrok" cmd /k "title FS-Ngrok && ngrok http 3000"
timeout /t 5 /nobreak >nul

REM ── Monitor loop ──────────────────────────────────────────────────────────
:monitor
timeout /t 15 /nobreak >nul

REM Check internet
ping -n 1 8.8.8.8 >nul 2>&1
if errorlevel 1 (
    echo [FraudShield] Internet lost. Waiting...
    :wait_reconnect
    timeout /t 5 /nobreak >nul
    ping -n 1 8.8.8.8 >nul 2>&1
    if errorlevel 1 goto wait_reconnect
    echo [FraudShield] Internet restored. Restarting ngrok...
    taskkill /f /im ngrok.exe >nul 2>&1
    goto start_ngrok
)

REM Check dashboard still up
curl -s -o nul -w "%%{http_code}" http://localhost:3000 2>nul | findstr /r "^[23]" >nul 2>&1
if errorlevel 1 (
    echo [FraudShield] Dashboard down! Restarting...
    echo [%date% %time%] Dashboard crashed, restarting >> "%LOGFILE%"
    taskkill /f /fi "WINDOWTITLE eq FS-Dashboard*" >nul 2>&1
    taskkill /f /im ngrok.exe >nul 2>&1
    timeout /t 3 /nobreak >nul
    goto start_dashboard
)

REM Check ngrok still running
tasklist /fi "IMAGENAME eq ngrok.exe" 2>nul | findstr /i "ngrok.exe" >nul 2>&1
if errorlevel 1 (
    echo [FraudShield] Ngrok died! Restarting...
    echo [%date% %time%] Ngrok died, restarting >> "%LOGFILE%"
    goto start_ngrok
)

goto monitor

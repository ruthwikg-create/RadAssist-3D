@echo off
setlocal
cd /d "%~dp0"

echo.
echo ============================================================
echo   RadAssist 3D - Local Research Workstation - FINAL VERIFIED
echo ============================================================
echo.

if not exist "backend\venv\Scripts\python.exe" (
  echo [RadAssist] Backend environment is missing.
  echo [RadAssist] Run setup-local.cmd first.
  echo.
  pause
  exit /b 1
)

if not exist "frontend\node_modules" (
  echo [RadAssist] Frontend dependencies are missing.
  echo [RadAssist] Run setup-local.cmd first.
  echo.
  pause
  exit /b 1
)

if exist "frontend\.next" rmdir /s /q "frontend\.next"

if not exist "E:\RadAssistTemp" mkdir "E:\RadAssistTemp"
if not exist "E:\RadAssistPipCache" mkdir "E:\RadAssistPipCache"

start "RadAssist Backend" /D "%~dp0backend" cmd /k "call venv\Scripts\activate.bat && set TEMP=E:\RadAssistTemp && set TMP=E:\RadAssistTemp && set PIP_CACHE_DIR=E:\RadAssistPipCache && python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000"

start "RadAssist Frontend" /D "%~dp0frontend" cmd /k "set NEXT_TELEMETRY_DISABLED=1 && npm run dev"

for /l %%I in (1,1,30) do (
  powershell -NoProfile -Command "$ok=Test-NetConnection -ComputerName 127.0.0.1 -Port 3000 -InformationLevel Quiet; if($ok){exit 0}else{exit 1}" >nul 2>&1
  if not errorlevel 1 goto open_browser
  timeout /t 1 /nobreak >nul
)

echo [RadAssist] Frontend is still starting.
echo [RadAssist] Open http://localhost:3000 when ready.
goto :eof

:open_browser
start "" "http://localhost:3000"
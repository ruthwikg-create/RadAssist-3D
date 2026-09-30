@echo off
setlocal
cd /d "%~dp0backend"
if not exist "venv\Scripts\python.exe" (
  echo [RadAssist] Backend environment not found. Run setup-local.cmd first.
  pause
  exit /b 1
)
if not exist "E:\RadAssistTemp" mkdir "E:\RadAssistTemp"
if not exist "E:\RadAssistPipCache" mkdir "E:\RadAssistPipCache"
call "venv\Scripts\activate.bat"
set "TEMP=E:\RadAssistTemp"
set "TMP=E:\RadAssistTemp"
set "PIP_CACHE_DIR=E:\RadAssistPipCache"
set "NEXT_TELEMETRY_DISABLED=1"
echo.
echo [RadAssist] FastAPI: http://127.0.0.1:8000
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000

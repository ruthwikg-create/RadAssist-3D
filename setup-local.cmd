@echo off
setlocal
cd /d "%~dp0"

echo.
echo ============================================================
echo   RadAssist 3D - First-time local setup
 echo ============================================================
echo.

if not exist "E:\RadAssistTemp" mkdir "E:\RadAssistTemp"
if not exist "E:\RadAssistPipCache" mkdir "E:\RadAssistPipCache"

if not exist "backend\venv\Scripts\python.exe" (
  echo [1/3] Creating backend virtual environment...
  python -m venv backend\venv
  if errorlevel 1 goto fail
) else (
  echo [1/3] Backend virtual environment already exists.
)

call "backend\venv\Scripts\activate.bat"
set "TEMP=E:\RadAssistTemp"
set "TMP=E:\RadAssistTemp"
set "PIP_CACHE_DIR=E:\RadAssistPipCache"
set "NEXT_TELEMETRY_DISABLED=1"

echo [2/3] Installing backend dependencies...
python -m pip install -r backend\requirements.txt
if errorlevel 1 goto fail

deactivate

echo [3/3] Installing frontend dependencies...
cd /d "%~dp0frontend"
npm install
if errorlevel 1 goto fail

cd /d "%~dp0"
echo.
echo [RadAssist] Local setup completed successfully.
echo [RadAssist] Start with: start-radassist.cmd
echo.
pause
exit /b 0

:fail
cd /d "%~dp0"
echo.
echo [RadAssist] Setup failed. Read the error above.
echo.
pause
exit /b 1

@echo off
setlocal
cd /d "%~dp0"
echo [RadAssist] Running local verification...
python scripts\verify_project.py
if errorlevel 1 (
  echo.
  echo [RadAssist] Verification failed. Read the message above.
  pause
  exit /b 1
)
echo.
echo [RadAssist] Source verification passed.
if exist "frontend\node_modules" (
  echo [RadAssist] Running TypeScript check and production build...
  cd /d "%~dp0frontend"
  call npm run lint
  if errorlevel 1 exit /b 1
  call npm run build
  if errorlevel 1 exit /b 1
  echo.
  echo [RadAssist] Frontend lint + build passed.
) else (
  echo [RadAssist] frontend\node_modules not found. Run npm install first.
)

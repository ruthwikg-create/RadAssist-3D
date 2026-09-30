@echo off
setlocal
cd /d "%~dp0frontend"
if not exist "package.json" (
  echo [RadAssist] Frontend package.json not found.
  pause
  exit /b 1
)
if not exist "node_modules" (
  echo [RadAssist] Frontend dependencies not found. Run setup-local.cmd first.
  pause
  exit /b 1
)
if exist ".next" rmdir /s /q ".next"
echo.
set "NEXT_TELEMETRY_DISABLED=1"
echo [RadAssist] Next.js: http://localhost:3000
npm run dev

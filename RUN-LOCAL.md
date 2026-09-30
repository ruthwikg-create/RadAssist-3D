# RadAssist 3D — Local Windows Run

This build is intended to run locally with CMD. Docker is not required for the development workflow.

## First time

1. Open CMD in this folder.
2. Run `setup-local.cmd`.
3. Run `start-radassist.cmd`.
4. Open http://localhost:3000.

The setup script places Python temporary files and the pip cache on `E:` to avoid a low-space `C:` temporary-directory failure.

## Manual

Backend:
`backend\venv\Scripts\activate.bat`
`python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000`

Frontend:
`npm run dev` from `frontend`.

## Verification

Run `VERIFY-LOCAL.cmd` after installation. It checks source structure and, when `frontend\node_modules` exists, runs TypeScript checks and the production build.

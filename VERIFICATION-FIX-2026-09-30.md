# Verification Fix — 2026-09-30

Fixed `scripts/verify_project.py` for Windows Node/npm resolution.

The verifier now explicitly resolves `npm.cmd` (falling back to `npm`) before running:
- `npm run lint`
- `npm run build`

This fixes the Windows `FileNotFoundError: [WinError 2]` that occurred even though `where npm` showed `C:\Program Files\nodejs\npm.cmd` and `npm --version` worked in CMD.

The verification remains strict: frontend lint and production build are still executed whenever `frontend\\node_modules` exists.

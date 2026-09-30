# Verification Fix

`VERIFY-LOCAL.cmd` now resolves TypeScript from `frontend\node_modules` instead of requiring a globally installed root-level `typescript` package.

After `npm install` in `frontend`, run `VERIFY-LOCAL.cmd`.

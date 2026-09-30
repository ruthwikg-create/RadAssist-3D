# RadAssist 3D — Final verified build notes

## Build baseline

This package is the consolidated final local baseline after the v5.1–v5.3 fixes.

### Frontend reliability

- Uses Next.js 16.3.6 with the explicit webpack build path.
- Uses self-hosted Fontsource Figtree Variable and Noto Sans Variable instead of `next/font/google`, avoiding build-time Google font retrieval.
- TypeScript is pinned to 5.9.2 and the required React/Node type packages are included.
- Demo MPR remains browser-local and does not feed synthetic data through the NIfTI decompression pipeline.
- Real NIfTI MPR follows Cornerstone's documented imageId-first NIfTI workflow and shared volume setup.
- 3D mesh validation and WebGL failure handling are guarded.

### Backend reliability

- Python backend source compiles successfully with `compileall`.
- Model absence is handled as a degraded backend state rather than an import/startup crash.
- Real AI segmentation remains intentionally blocked until the SegResNet checkpoint is installed.
- Upload, path, ZIP extraction, measurement provenance, and case-artifact safeguards remain enabled.

### Verification reliability

- Verification checks match the actual `next build --webpack` script.
- Verification checks are source-aware and do not assert stale version strings inside UI code.
- `VERIFY-LOCAL.cmd` runs source verification first and then TypeScript/build checks when frontend dependencies exist.

## Validation performed for this package

- Python `compileall`: PASS
- TypeScript/TSX syntax parsing of all 14 source files: PASS
- Required-file/source verification: PASS
- Medical-QC/provenance source checks: PASS
- Relative frontend import existence checks: PASS
- External dependency declarations checked against `package.json`: PASS

A Windows browser, GPU/WebGL context, local npm dependency installation, and real clinical dataset cannot be reproduced inside this packaging environment. Therefore this package does not claim that clinical accuracy, regulatory compliance, or Windows browser execution has been independently certified here.

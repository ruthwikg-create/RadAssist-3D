# RadAssist 3D — Final Verification Package

This package is intended to be the stable local baseline for the RadAssist 3D research workstation.

## Verified in package source

- Python backend source compiles with `py_compile`.
- Required backend/frontend/design-system/model-training files are present.
- Frontend TypeScript configuration is strict and uses the local TypeScript compiler.
- Frontend uses self-hosted Fontsource Figtree Variable and Noto Sans Variable; no Google-font download is required during build.
- Demo MPR is browser-local and does not enter the NIfTI decompression path.
- Real NIfTI MPR uses the documented Cornerstone imageId-first NIfTI workflow and a shared volume for orthographic viewports.
- 3D surface viewer validates vertices/faces and guards WebGL failures.
- Backend exposes health, case history, segmentation, volume, mask, bundle, and demo endpoints.
- Measurement-quality and model-provenance fields are represented explicitly.
- Verification checks are aligned with the actual webpack build script.

## Local verification

From the project root:

```cmd
VERIFY-LOCAL.cmd
```

After dependencies are installed, this runs TypeScript checking and the production build.

## Local run

```cmd
start-radassist.cmd
```

Frontend: `http://localhost:3000`
Backend: `http://127.0.0.1:8000`
Backend health: `http://127.0.0.1:8000/health`
API docs: `http://127.0.0.1:8000/docs`

## Important medical-use limitation

The application is a research/engineering workstation. A successful software build or synthetic demo does not establish clinical accuracy, diagnostic performance, regulatory clearance, or medical-device-grade measurement accuracy. Patient-facing or clinical use requires appropriate validation, representative datasets, calibration/traceability, uncertainty analysis, clinical evaluation, cybersecurity controls, and applicable regulatory processes.

## AI model requirement

Real segmentation requires:

`backend/models/spleen_segresnet.pth`

If the checkpoint is absent, the backend remains available in degraded mode and the synthetic demo remains available, but real AI segmentation is intentionally blocked.

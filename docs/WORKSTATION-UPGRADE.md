# RadAssist 3D workstation upgrade

## Implemented in this phase

- Heart 2D UNet inference across the full 3D source volume, with the native SimpleITK geometry copied to the output labelmap.
- Separate cardiac LV blood-pool, myocardium, and RV meshes/volumes plus connected-component and mesh/labelmap QA.
- Cornerstone orthographic MPR with shared volume, synchronized W/L, pan/zoom, crosshair and measurement tools.
- Three.js surface visibility, opacity, wireframe, axes/grid, clipping and fullscreen controls, extended with structure isolation, show-all and PNG capture.
- Structured result-only AI assistance, QA, advanced measurements, provenance and performance inspection.
- Offline Dice/IoU validation utility for comparing a saved prediction with an external reference mask.

## Safety boundary

The AI assistance panel summarizes validated numeric result fields only. It does not diagnose, prognosticate, or recommend treatment. Model benchmark metrics remain separate from patient-specific accuracy.

## Validation

\`\`\`cmd
.venv\Scripts\python.exe scripts\validate_segmentation.py <prediction.nii.gz> <reference.nii.gz> --labels 1,2
\`\`\`

Reference masks are intentionally external; patient data is not committed to the repository.

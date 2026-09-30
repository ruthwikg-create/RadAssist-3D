# RadAssist 3D — Workstation Phases 1–3

This branch implements the requested workstation upgrade while preserving the research/engineering-only boundary.

## Phase 1
- Per-label connected-component cleanup for Heart and Prostate.
- Largest anatomical component retained by default.
- Separate label meshes remain the visualization source.
- Taubin-style mesh smoothing is applied to rendered surfaces.
- Surface area and closed-mesh volume are calculated from the same rendered mesh.
- Labelmap volume remains the primary measurement; mesh volume is an independent cross-check.
- Equivalent sphere diameter is calculated from labelmap volume.
- MRI source-intensity statistics are calculated from the original source image inside the cleaned segmentation mask.
- Quantitative QA now reports component counts, largest-component fraction, boundary contact, mesh/labelmap difference, and explicit review flags.

## Phase 2
- Three.js structure visibility and opacity controls.
- Functional wireframe, axes, grid, reset and fullscreen controls.
- Interactive 3D clipping plane.
- Cornerstone CrosshairsTool for linked axial/sagittal/coronal reference lines.
- Length and bidirectional measurement tools in MPR.
- Structured report export from the study workspace.
- Existing study history and case bundle export retained.

## Phase 3
- DICOM series identity integrity checks for StudyInstanceUID, SeriesInstanceUID, FrameOfReferenceUID and Modality.
- Input geometry/modality validation before persistence.
- Structured measurement schema.
- Explicit uncertainty and patient-specific accuracy status.
- Reproducible model/checkpoint provenance retained in the result.
- DICOM SEG-compatible and DICOM SR-compatible result architecture records. These are architecture records, not emitted DICOM SEG/SR files yet.
- Per-case JSONL audit trail.
- Exportable structured JSON report.
- Regression tests for connected-component cleanup and mesh geometry/smoothing.

## Validation boundary
These changes improve engineering correctness and traceability but do not establish clinical accuracy, regulatory clearance, or patient-specific diagnostic performance.

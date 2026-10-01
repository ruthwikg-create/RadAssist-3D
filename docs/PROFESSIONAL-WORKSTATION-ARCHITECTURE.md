# RadAssist 3D — Professional Workstation Architecture

## Product direction

RadAssist 3D is being structured as a research-oriented radiology workstation rather than a generic AI dashboard.

Primary workflow:

**Study intake → protocol selection → input validation → image viewing → optional AI segmentation → 2D/MPR review → 3D reconstruction → quantitative analysis → QA/provenance → export**

The interface should feel closer to a specialist imaging workstation than a consumer SaaS application.

## Imaging modalities

The application maintains an explicit modality registry for CT, MRI, X-Ray, PET, SPECT, PET/CT, Ultrasound, Mammography, Fluoroscopy, DEXA, and NIfTI research volumes.

Import/viewing capability is intentionally separated from AI segmentation capability. A modality being supported by the viewer does not imply that an AI model is validated for it.

## Current segmentation protocols

| Target | Modality | Current role |
|---|---|---|
| Spleen | CT | Segmentation + 3D + quantitative workflow |
| Heart | MRI | Cardiac structure segmentation + 3D |
| Prostate | MRI | Zonal segmentation + 3D |

Additional MONAI-compatible models can be introduced through the model registry after their input contract, labels, preprocessing, provenance, and validation status are documented.

## AI/model layer

The model layer should use an adapter contract:

1. Identify modality and anatomy.
2. Validate dimensions, orientation, spacing, and required sequences.
3. Normalize/resample using the model's documented contract.
4. Run inference.
5. Preserve model name/version/checksum/source.
6. Store segmentation mask and structured measurements.
7. Surface uncertainty/QA state to the reviewer.
8. Never silently substitute a different model.

MONAI Model Zoo bundles are useful research model sources because bundles package model weights, configuration, and inference code together. Model selection must remain anatomy/modality specific.

## Clinical-review principles

RadAssist should provide information that a clinician can independently inspect:

- Original images remain accessible.
- Segmentation overlays can be hidden.
- Slice position and voxel spacing remain visible.
- Measurements are derived from the stored mask and physical spacing.
- Model provenance is exposed.
- Warnings are explicit.
- Failed or unsupported protocols are blocked rather than guessed.
- Synthetic/demo data is clearly marked.

The application must not present research segmentation as a validated diagnosis, surgical plan, or patient-specific treatment directive.

## UI/UX direction

### Visual language

- Dark neutral radiology-console foundation.
- Figtree for compact headings and workstation controls.
- Noto Sans for dense technical metadata.
- Restrained teal/cyan accent for active tools.
- Amber for review-required states.
- Red only for actual errors or safety warnings.
- No excessive gradients, giant hero sections, glassmorphism, AI sparkles, or marketing-style cards.

### Workspace layout

**Top bar**
- Study identifier
- Modality
- Series
- Acquisition metadata
- Backend/model status

**Left rail**
- Study intake
- Modality
- Anatomy/protocol
- Series list
- Tool groups

**Center**
- MPR viewer
- 3D surface viewer
- synchronized crosshair/slice position
- overlay controls

**Right inspector**
- Structures
- Segmentation controls
- Measurements
- QA
- Provenance

**Bottom status bar**
- Current slice
- voxel spacing
- window/level
- processing state
- warnings

### Motion

Animations should communicate state, not decorate the page:

- 150–220 ms control transitions.
- 300–450 ms workspace entrance.
- Skeleton/progress during long operations.
- Subtle scanline only during active processing.
- Respect the browser reduced-motion preference.

## Engineering quality bar

Every new modality/model must have:

- input validation tests
- deterministic metadata tests
- segmentation adapter tests
- failure-path tests
- artifact export tests
- UI loading/error/empty states
- provenance entry
- documented limitations

A feature is not considered complete merely because its button renders.

## Integration candidates

- Cornerstone3D for browser-side medical image rendering and MPR.
- DICOMweb-compatible archive integration for PACS/research archives.
- Orthanc for a local development DICOM archive.
- MONAI for model execution.
- PyTorch for inference.
- SimpleITK/NiBabel/pydicom for image I/O and preprocessing.
- Three.js for interactive surface visualization.

External AI/cloud APIs should be optional adapters, never hard dependencies for local imaging or segmentation.

## Regulatory boundary

Medical-image analysis can fall within medical-device/software regulation depending on intended use and functionality. RadAssist therefore remains explicitly research/educational until appropriate clinical validation, quality-system controls, cybersecurity controls, and regulatory assessment are completed.

See the repository's medical-QC documentation before positioning the software for clinical use.

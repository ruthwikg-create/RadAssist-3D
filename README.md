# RadAssist 3D — Medical Imaging Research Workstation

RadAssist 3D is a research/engineering-oriented browser workstation for 3D CT segmentation, MPR review, volumetric measurements, HU statistics, 3D surface visualization, and reproducible model provenance.

## Local Windows run (no Docker)

Backend CMD:

```cmd
cd /d "<RadAssist-3D>\backend"
venv\Scripts\activate
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Frontend CMD:

```cmd
cd /d "<RadAssist-3D>\frontend"
npm install
npm run dev
```

Open `http://localhost:3000`.

## Medical-measurement guardrails

RadAssist computes target volume from the binary labelmap and the source image voxel spacing, and it separately reports surface area / mesh-volume cross-checks. Intensity statistics are calculated from the original source CT, not from the normalized network input.

For DICOM CT, the UI marks the intensity domain as HU only when the source is identified as DICOM CT. For NIfTI, the unit semantics are explicitly treated as source-dependent rather than silently calling them HU.

The model Dice displayed by the application is the held-out validation benchmark stored in the model checkpoint. It is not a per-patient accuracy score.

## Validation status

A visually polished interface or a good retrospective benchmark does not, by itself, make a product a clinical medical device. Clinical deployment requires intended-use definition, representative validation cohorts, independent test data, verification/validation evidence, risk management, traceability, cybersecurity, change control, and the applicable regulatory pathway.

The current project is therefore labeled for research/engineering use only.

## Inspired architecture

The workstation borrows proven interaction patterns from open-source imaging systems such as OHIF and 3D Slicer: study context at the left/top, imaging workspace in the center, quantitative/measurement inspection on the right, explicit provenance, and separation of model benchmarks from per-case measurements.


## Medical-measurement architecture

The workstation follows common open-source radiology UI patterns: study context on the left/top, image viewport and tools in the center, quantitative inspection on the right. OHIF documents a Basic Viewer layout with a study panel, viewport, right measurement panel, and toolbar; its measurement tooling includes length, bidirectional, annotation, ellipse and calibration workflows. 3D Slicer documents labelmap-based volume as voxel count × voxel volume and also exposes surface, centroid and scalar-intensity statistics.

RadAssist uses the native source geometry for final volume calculations rather than the browser preview. Surface-mesh volume is an independent cross-check. HU status is conservative: DICOM is marked HU-verified only when an explicit CT rescale transform with HU type is available; NIfTI is not assumed to be HU without independent provenance.

This improves traceability and measurement QA, but it does not make the software a clinically validated medical device. Clinical deployment requires formal verification/validation, risk management, usability/human-factors work and evidence supporting safety and effectiveness appropriate to the intended use.

## Final verified baseline

The repository includes automated source checks, backend regression tests, and frontend TypeScript/build verification. Runtime model inference still requires the configured model checkpoints and should be validated locally against representative test volumes before any research result is relied upon.

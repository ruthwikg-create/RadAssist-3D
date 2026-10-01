# RadAssist 3D

### From Medical Images to Quantitative 3D Analysis

**RadAssist 3D** is a research-oriented medical-imaging workstation that brings together **DICOM/NIfTI ingestion, anatomy-specific AI segmentation, multiplanar visualization, 3D anatomical reconstruction, quantitative measurement, segmentation QA, provenance, interoperability, and patient-data security** in one browser-based workflow.

> **Created by Ruthwik Goparaju**  
> Biomedical Engineering Student — University College of Engineering, Osmania University, Hyderabad, India

RadAssist 3D is being developed as a biomedical-engineering research project, not as a claim of clinical certification or diagnostic performance.

---

## Why I started this project

Medical imaging contains an enormous amount of anatomical information, but that information is often spread across separate tools: one for viewing images, another for segmentation, another for measurements, and another for exporting or documenting results.

As a biomedical engineering student, I wanted to explore a different question:

> **What would a modern, research-focused imaging workstation look like if visualization, AI segmentation, quantitative analysis, quality checks, provenance, interoperability, and security were designed as one system?**

That question became RadAssist 3D.

The project evolved from a medical-image visualization concept into a broader engineering study involving:

- medical-image geometry and coordinate systems
- AI-assisted segmentation
- 2D/3D visualization
- quantitative biomedical measurements
- DICOM interoperability
- model and input provenance
- segmentation quality assurance
- cybersecurity and patient-data protection
- software verification and reproducibility

The goal is not to make an interface that merely *looks medical*. The goal is to understand how a serious medical-imaging software system should be engineered, tested, documented, and eventually validated.

---

## The research idea

RadAssist 3D explores a workflow in which a medical image moves through a traceable analysis pipeline:

~~~text
DICOM / NIfTI
      │
      ▼
Input & Geometry QC
      │
      ▼
Model Registry
      │
      ▼
AI Segmentation
      │
      ▼
Segmentation QA
      │
      ├──────────────► Stability / Uncertainty research
      │
      ▼
MPR + 3D Visualization
      │
      ▼
Physical Measurements
      │
      ├──► DICOM SEG
      ├──► DICOM SR
      ├──► JSON
      └──► NIfTI
      │
      ▼
Provenance + Audit + Security
~~~

This architecture is deliberately designed around **traceability**: a measurement should be connected to its source geometry, segmentation, model configuration, and processing history rather than appearing as an unexplained number.

---

## What RadAssist 3D can do today

### Medical imaging

- DICOM and NIfTI-oriented research workflow
- CT and MRI support
- Input dimension and spacing validation
- DICOM series identity integrity checks
- Source-geometry-aware processing

### AI-assisted segmentation

Current anatomy-specific research models include:

| Anatomy | Modality | Research task |
|---|---|---|
| Spleen | CT | Organ segmentation |
| Heart | MRI | Ventricular / myocardial segmentation |
| Prostate | MRI | Zonal segmentation |

The system keeps **model benchmark performance separate from patient-specific accuracy**.

A validation Dice value shown by the application is treated as a model benchmark, not as a statement that the current patient's segmentation is correct.

### MPR and 3D

- Axial / sagittal / coronal visualization
- Cornerstone-based MPR tooling
- Crosshair interaction
- Length measurement
- Bidirectional measurement
- 3D anatomical surface rendering
- Label-specific meshes
- Visibility and opacity controls
- Clipping
- Wireframe
- Axes and grid
- Fullscreen workspace

### Anatomy, model and education workspace

The advanced workstation now includes an **Anatomy & Models** workspace that makes the model contract visible before a result is interpreted:

- image/source type
- modality
- expected model input
- model architecture
- anatomical label classes
- model-domain compatibility status
- physical geometry and spacing
- source → labelmap → physical geometry → mesh → QA explanation
- per-structure 3D anatomy and quantitative review
- education workflow for anatomy, MPR planes, 3D surfaces and quantitative concepts
- clinician/research review checklist

A dedicated whole-heart multi-structure model target is represented separately from the current ventricular short-axis model. The application does not turn the current ventricular model into a whole-heart model by smoothing or filling gaps.

### Tumor and lesion research layer

RadAssist also contains an explicit pathology-model registry for optional lesion workflows. The registry can expose anatomy-specific model slots for brain MRI tumor segmentation, lung CT nodule detection, liver focal lesions and prostate MRI lesions.

The important design rule is:

> **No tumor finding is produced by placeholder thresholds or by re-labeling anatomical segmentation artifacts.**

An actual lesion result requires a pathology-specific checkpoint, a declared input contract, provenance, uncertainty/review metadata, and an appropriate validation program. This keeps the tumor workflow inspectable instead of presenting an unvalidated detector as a diagnostic feature.

### Quantitative analysis

RadAssist calculates measurements from the native image/labelmap geometry rather than relying on browser preview dimensions.

Current engineering outputs include:

- segmented volume
- voxel count
- equivalent sphere diameter
- surface area
- mesh-volume cross-check
- connected-component statistics
- largest-component fraction
- boundary-contact checks
- source-intensity statistics
- measurement quality flags

For MRI, intensity values are treated as **source signal intensity**, not automatically as Hounsfield Units.

For CT, HU interpretation is handled conservatively and depends on trustworthy source metadata.

### DICOM interoperability

For authoritative DICOM source series, the workstation can generate:

- **DICOM SEG** segmentation objects
- **DICOM SR** measurement reports using a TID-1500-oriented structure

NIfTI-only data is intentionally not converted into DICOM SEG/SR without a trustworthy DICOM frame of reference.

### Provenance and auditability

The result model records information such as:

- request identity
- source type
- modality
- image geometry
- model provenance
- measurement methodology
- structured measurements
- uncertainty status
- input validation
- segmentation/export status
- audit events
- SHA-256 input fingerprints

This is intended to make research results easier to reproduce and inspect.

---

## Security and patient-data protection

Medical images can contain highly sensitive information. Security is therefore part of the architecture, not a later add-on.

Current controls include:

- optional bearer-token API authentication
- trusted-host protection
- API response no-cache controls
- browser security headers
- API documentation disabled by default
- demo mode disabled by default
- path-traversal protection
- source-filename minimization in provenance manifests
- configurable case-artifact retention
- environment-based secret configuration
- protected artifact retrieval
- security documentation
- regression testing for security-sensitive behavior

The repository also documents a recommended protected deployment:

~~~text
User
  │
  ▼
HTTPS / Identity Provider
  │
  ▼
Reverse Proxy
  │
  ├── Frontend
  │
  └── Private Backend
          │
          ▼
     Protected Storage
          │
          ▼
       DICOM/PACS
~~~

These controls reduce common application-level risks, but they **do not constitute regulatory certification, institutional privacy compliance, HIPAA/GDPR compliance, or clinical cybersecurity certification**.

For medical-device cybersecurity, the project direction is informed by established risk-management concepts such as the NIST Cybersecurity Framework 2.0 and current FDA medical-device cybersecurity guidance. These references inform engineering direction; they are not claims of compliance.

---

## What makes the project research-oriented

RadAssist 3D is intentionally built around several research questions.

### 1. Geometry matters

A segmentation can look correct while its physical measurements are wrong if spacing, orientation, or coordinate conversion is mishandled.

The project therefore separates:

- native voxel geometry
- labelmap measurements
- rendered mesh geometry
- browser visualization

and uses independent checks where possible.

### 2. AI benchmark ≠ patient accuracy

A model's held-out Dice score cannot be presented as the accuracy of an individual patient's result.

RadAssist explicitly separates these concepts.

### 3. Reproducibility matters

A useful research result should answer:

> Which input was processed, with which model, using which geometry and processing configuration?

That is why provenance, hashes, structured results, and audit events are part of the application architecture.

### 4. Security matters

A medical-imaging system can produce technically impressive segmentation while still being unsuitable for real-world use if patient information is exposed.

RadAssist therefore treats privacy and cybersecurity as engineering requirements.

### 5. Interoperability matters

A research workstation should not become an isolated visualization demo.

The DICOM SEG/SR direction is intended to make derived results easier to move into standards-based imaging workflows when the source evidence is sufficient.

---

## Development approach

RadAssist 3D has been developed using an **AI-assisted engineering workflow**.

AI tools have been used to accelerate:

- architecture exploration
- code generation and refactoring
- debugging
- test design
- documentation
- research-oriented technical analysis
- UI/UX iteration
- security review
- repository auditing

The important distinction is that AI assistance is treated as an engineering accelerator, **not as a substitute for testing, source inspection, validation, or human responsibility**.

The repository is progressively hardened through source review, automated tests, build checks, model-provenance checks, and runtime testing against representative imaging data.

---

## Technology stack

### Frontend

- Next.js
- React
- TypeScript
- Tailwind CSS
- Three.js
- React Three Fiber
- Cornerstone3D

### Backend

- Python
- FastAPI
- Pydantic
- SimpleITK
- NiBabel
- NumPy
- scikit-image

### AI / medical imaging

- PyTorch
- MONAI
- anatomy-specific model adapters
- sliding-window inference
- DICOM / NIfTI processing
- highdicom
- pydicom

### Engineering

- GitHub
- GitHub Actions
- automated regression tests
- TypeScript/build verification
- provenance and audit records
- Docker support

---

## Architecture

~~~text
┌─────────────────────────────────────────────────────────┐
│                    RadAssist 3D UI                      │
│                                                         │
│  Study Context │ MPR │ Measurements │ 3D │ QA │ Export │
└──────────────────────────┬──────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│                    FastAPI Backend                      │
├─────────────────────────────────────────────────────────┤
│ Input Validation │ Case Management │ Security           │
├─────────────────────────────────────────────────────────┤
│ Model Registry   │ AI Inference │ Segmentation QA       │
├─────────────────────────────────────────────────────────┤
│ Geometry         │ Measurements │ Provenance            │
├─────────────────────────────────────────────────────────┤
│ DICOM SEG        │ DICOM SR     │ JSON / NIfTI          │
└──────────────────────────┬──────────────────────────────┘
                           │
                           ▼
                Protected Case Storage
~~~

---

## Current development roadmap

| Capability | Status |
|---|---|
| DICOM/NIfTI ingestion | Implemented |
| Input geometry/QC checks | Implemented |
| Spleen CT segmentation | Implemented |
| Heart MRI segmentation | Implemented |
| Prostate MRI segmentation | Implemented |
| MPR visualization | Implemented |
| 3D anatomical visualization | Implemented |
| Quantitative measurements | Implemented |
| Segmentation QA | Implemented |
| Model/input provenance | Implemented |
| Audit trail | Implemented |
| DICOM SEG export | Implemented for authoritative DICOM source studies |
| DICOM SR export | Implemented for authoritative DICOM source studies |
| Patient-data security controls | Implemented / hardening in progress |
| Model registry | In progress |
| Interactive segmentation refinement | Next |
| Registration / image fusion | Next |
| Segmentation stability / uncertainty analysis | Next |
| DICOMweb / PACS integration | Planned integration layer |
| Longitudinal comparison | Planned |
| Independent clinical validation | External research/validation program |

---

## What is intentionally *not* claimed

RadAssist 3D does **not** currently claim:

- clinical diagnostic accuracy
- patient-specific segmentation accuracy
- medical-device certification
- regulatory clearance
- clinical deployment readiness
- universal DICOM compatibility
- validated measurement accuracy for every anatomy/modality
- automatic diagnosis

Those claims require evidence beyond a software build.

A serious medical-imaging product needs representative datasets, independent validation, verification and validation evidence, risk management, cybersecurity, usability/human-factors work, traceability, change control, and an appropriate regulatory pathway.

---

## Research and validation direction

The next stage is not simply adding more UI features.

The project is moving toward measurable validation:

1. **Input validation**
   - geometry
   - modality
   - DICOM series consistency
   - corrupted/incomplete study detection

2. **Model validation**
   - held-out datasets
   - per-class metrics
   - sensitivity/specificity where appropriate
   - Hausdorff / surface-distance metrics
   - failure-case analysis

3. **Segmentation robustness**
   - perturbation testing
   - preprocessing sensitivity
   - repeatability
   - uncertainty/stability measures

4. **Measurement validation**
   - voxel-volume calculations
   - mesh cross-checks
   - physical phantom/reference comparisons where appropriate

5. **Software verification**
   - regression tests
   - integration tests
   - security testing
   - dependency and container scanning
   - reproducible builds

6. **Clinical research**
   - representative cohorts
   - expert annotation
   - inter-observer analysis
   - prospective/retrospective study design
   - intended-use definition

---

## Repository structure

~~~text
RadAssist-3D/
├── backend/
│   ├── main.py
│   ├── pipeline.py
│   ├── multimodel_engine.py
│   ├── model_adapter.py
│   ├── heart_model_adapter.py
│   ├── prostate_model_adapter.py
│   ├── engineering.py
│   ├── dicom_export.py
│   ├── case_store.py
│   └── test_workstation_regression.py
│
├── frontend/
│   ├── components/
│   ├── lib/
│   └── package.json
│
├── model_training/
│   └── train_spleen_segresnet.py
│
├── scripts/
│   └── verify_project.py
│
├── .github/
│   └── workflows/
│
├── ADVANCED-WORKSTATION-ROADMAP.md
├── SECURITY.md
├── PHASES-1-3-IMPLEMENTATION.md
└── README.md
~~~

---

## Run locally

### Backend — Windows

~~~cmd
cd /d "<RadAssist-3D>\backend"
venv\Scripts\activate
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
~~~

### Frontend

~~~cmd
cd /d "<RadAssist-3D>\frontend"
npm install
npm run dev
~~~

Open:

~~~text
http://localhost:3000
~~~

For protected deployments, configure the environment variables documented in SECURITY.md and .env.example.

---

## Verification philosophy

The project uses automated checks because a medical-imaging application should not depend only on visual inspection.

The repository includes:

- Python compilation checks
- backend regression tests
- frontend TypeScript checks
- production frontend builds
- geometry regression tests
- provenance checks
- security-oriented tests
- GitHub Actions verification

Runtime inference must still be tested locally with the actual configured model checkpoints and representative datasets.

---

## Research references and engineering context

The project architecture is informed by established medical-imaging and software-engineering ecosystems, including:

- DICOM standards for imaging objects and structured reporting
- MONAI for medical AI workflows
- Cornerstone3D for web-based imaging visualization
- highdicom / pydicom for DICOM interoperability
- NIST Cybersecurity Framework 2.0 for cybersecurity risk-management concepts
- FDA guidance concerning medical-device software and cybersecurity

These references inform the engineering direction of the project. They should not be interpreted as evidence that RadAssist 3D conforms to a regulatory standard.

---

## Author

**Ruthwik Goparaju**  
Biomedical Engineering Student  
University College of Engineering, Osmania University  
Hyderabad, India

RadAssist 3D is an independent biomedical-engineering research project exploring the intersection of:

**Biomedical Engineering × Medical Imaging × AI × 3D Visualization × Quantitative Analysis × Software Engineering × Cybersecurity**

---

## Project statement

> **The objective of RadAssist 3D is not simply to generate a segmentation. It is to explore how an AI-assisted medical-imaging result can become a measurable, inspectable, reproducible, interoperable, and security-conscious research artifact.**

Built as a student research project.  
Designed with engineering discipline.  
Developed with AI-assisted tools.  
Validated through testing where evidence is available.  
Built with the long-term goal of learning what it takes to move from a prototype toward a responsibly engineered medical-imaging system.

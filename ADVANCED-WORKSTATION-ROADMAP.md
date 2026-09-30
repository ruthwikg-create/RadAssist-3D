# RadAssist 3D — Advanced Workstation Roadmap

## Product focus

RadAssist 3D is a multimodal medical-imaging research workstation focused on:

- DICOM/NIfTI ingestion and input quality control
- anatomy-specific AI segmentation for spleen CT, heart MRI and prostate MRI
- synchronized MPR and 3D anatomical visualization
- physical-coordinate quantitative measurements
- segmentation QA and model/input provenance
- interoperable research-result export

## Capability status

| Capability | Status | Scope |
|---|---|---|
| DICOM SEG generation | **Implemented** | Real DICOM SEG for DICOM source studies; NIfTI-only cases remain non-DICOM |
| DICOM SR generation | **Implemented** | TID1500 measurement report generated with DICOM source evidence |
| Interactive segmentation | **Next implementation** | Cornerstone Brush/Scissor editing with persisted labelmap revisions |
| Registration / fusion | **Next implementation** | Rigid-first multimodal/longitudinal registration with geometry QA |
| Segmentation stability / uncertainty | **Next implementation** | Perturbation/ensemble stability metrics; never presented as patient-specific accuracy |
| DICOMweb / PACS integration | **Integration layer** | Orthanc/DICOMweb research integration; optional, not required for local workstation mode |
| Longitudinal comparison | **Planned** | Study-to-study registration, volume change and measurement deltas |
| Model registry | **In progress** | Checkpoint hash, architecture, preprocessing and benchmark provenance |
| Verification / validation framework | **In progress** | Automated regression + representative dataset testing |
| Clinical validation | **Not a software feature** | Requires an independent clinical validation program, intended-use definition, risk management and applicable regulatory evidence |

## Deliberately removed from the product promise

### Clinical validation

This is not represented as a checkbox feature. Software can provide verification tooling and validation infrastructure, but clinical validation is an external evidence program involving representative data, independent evaluation, intended use, risk management, human factors and regulatory requirements.

### Generic AI diagnosis

RadAssist does not automatically diagnose disease from the segmentation results. The product remains focused on image analysis, segmentation, measurements, visualization, QA and reproducibility.

### Generic chatbot / medical advice

A general-purpose medical chatbot is outside the core project theme and would dilute the imaging workstation architecture.

### Decorative AI features

Features that do not improve imaging analysis, measurement, segmentation, QA, interoperability or reproducibility should not be added merely to make the UI look more advanced.

## Advanced target architecture

```
DICOM / NIfTI
      |
      v
Input QC + Geometry Integrity
      |
      v
Model Registry -> Checkpoint + Preprocessing + Hash
      |
      v
AI Segmentation
      |
      +--> Segmentation QA / Stability
      |
      v
Labelmap Refinement
      |
      +--> Registration / Fusion
      |
      v
MPR <-> 3D Visualization
      |
      v
Physical Measurements
      |
      +--> DICOM SEG
      +--> DICOM SR
      +--> Research JSON / NIfTI
      |
      v
Provenance + Audit Trail
```

The current DICOM SEG/SR implementation is intentionally restricted to authoritative DICOM source studies. Converting a standalone NIfTI volume into DICOM without a trustworthy source-image frame of reference would create false interoperability metadata.

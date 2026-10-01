# Advanced Workstation Implementation

## Purpose

This phase turns RadAssist 3D from a segmentation viewer into a transparent imaging workstation with an anatomy/model library, explicit model-domain compatibility, education workflow, pathology-model slots, quantitative review, and provenance-aware research output.

## Workflows

1. **Study ingestion** — DICOM/NIfTI source and geometry are retained.
2. **Model selection** — the UI exposes modality, architecture, expected input and label classes.
3. **Compatibility review** — the backend reports model-domain limitations instead of silently treating an arbitrary volume as a validated model input.
4. **MPR review** — source images remain the primary evidence.
5. **AI segmentation** — anatomical labelmaps are preserved with model provenance.
6. **3D reconstruction** — physical spacing, origin and direction are retained while surfaces are generated from labelmaps.
7. **Quantitative QA** — connected components, boundary contact, mesh/labelmap agreement and morphology are reported.
8. **Education mode** — structures, MPR planes, 3D surfaces and quantitative concepts can be reviewed as a teaching workflow.
9. **Research review** — provenance, model hash and reproducible artifacts are retained.
10. **Interoperability** — structured report, DICOM SEG/SR and research bundle remain available when source requirements are satisfied.

## Tumor / lesion module

The workstation now contains a pathology-model registry and a dedicated review surface. It intentionally does **not** fabricate tumor findings from intensity thresholds or anatomy masks.

The registry supports explicit checkpoint slots for:

- brain MRI tumor subregion segmentation;
- chest CT lung-nodule detection;
- liver focal-lesion models;
- prostate MRI lesion models.

A lesion model is considered available only when its checkpoint is explicitly configured and its modality/anatomy contract is satisfied. The intended result contract includes candidate mask/localization, 3D representation, volume/diameter where supported, uncertainty/confidence metadata, review status and model provenance.

For brain tumor work, a suitable external research model is the MONAI BraTS MRI segmentation bundle, which expects four MRI channels (T1c, T1, T2 and FLAIR) and produces tumor-core, whole-tumor and enhancing-tumor outputs. The MONAI model metadata explicitly describes it as an example and not for diagnostic use. RadAssist therefore requires the bundle/checkpoint to be installed and configured before exposing an actual finding.

## Clinical/research boundary

The UI is designed to make clinician/researcher review easier, not to claim clinical validity. A professional interface cannot substitute for external validation, representative datasets, reader studies, calibration/uncertainty analysis, regulatory assessment or deployment controls.

## Current heart limitation

The current heart adapter is a ventricular short-axis cardiac-MR research model. It is not a whole-heart anatomical model. The new compatibility panel makes this explicit and flags NIfTI studies for series/sequence verification. A complete multi-structure heart requires a model trained for those structures or a manual/interactive annotation workflow; smoothing a fragmented mask is not an acceptable substitute.

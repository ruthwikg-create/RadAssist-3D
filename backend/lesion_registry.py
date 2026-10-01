from __future__ import annotations

import os
from pathlib import Path
from typing import Any

LESION_MODEL_REGISTRY = (
    {
        "id": "brain_mri_lesion",
        "name": "Brain MRI Lesion / Tumor",
        "modality": "MR",
        "anatomy": "brain",
        "output": ["candidate lesion mask", "volume", "longest diameter", "3D surface"],
        "environment_variable": "RADASSIST_LESION_BRAIN_MODEL_PATH",
        "reference_model": "MONAI BraTS MRI segmentation",
        "input_contract": "4-channel T1c/T1/T2/FLAIR MRI at 1 mm isotropic resolution",
    },
    {
        "id": "lung_ct_lesion",
        "name": "Chest CT Lesion / Nodule",
        "modality": "CT",
        "anatomy": "chest",
        "output": ["candidate lesion mask", "volume", "longest diameter", "3D surface"],
        "environment_variable": "RADASSIST_LESION_LUNG_MODEL_PATH",
        "reference_model": "MONAI lung_nodule_ct_detection",
        "input_contract": "Chest CT volume matching the selected MONAI bundle contract",
    },
    {
        "id": "liver_ct_mri_lesion",
        "name": "Liver Focal Lesion",
        "modality": "CT/MR",
        "anatomy": "liver",
        "output": ["candidate lesion mask", "volume", "diameter", "3D surface"],
        "environment_variable": "RADASSIST_LESION_LIVER_MODEL_PATH",
    },
    {
        "id": "prostate_mri_lesion",
        "name": "Prostate MRI Lesion",
        "modality": "MR",
        "anatomy": "prostate",
        "output": ["candidate lesion map", "3D mask", "zonal context"],
        "environment_variable": "RADASSIST_LESION_PROSTATE_MODEL_PATH",
    },
)


def get_lesion_capabilities() -> list[dict[str, Any]]:
    capabilities: list[dict[str, Any]] = []
    for item in LESION_MODEL_REGISTRY:
        configured = os.getenv(item["environment_variable"])
        path = Path(configured).expanduser() if configured else None
        exists = bool(path and path.is_file())
        capabilities.append(
            {
                **item,
                "status": "CONFIGURED" if exists else "CHECKPOINT_REQUIRED",
                "checkpoint_present": exists,
                "clinical_use": False,
                "research_validation_required": True,
                "note": (
                    "No lesion finding is generated until a pathology-specific "
                    "checkpoint and validation protocol are configured."
                ),
            }
        )
    return capabilities

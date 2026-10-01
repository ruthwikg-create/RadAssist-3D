"""Central registry for RadAssist imaging modalities and analysis capabilities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Capability = Literal["viewer", "mpr", "segmentation", "surface3d", "quantification", "fusion"]
Status = Literal["available", "viewer-only", "planned"]


@dataclass(frozen=True)
class ModalityProtocol:
    label: str
    formats: tuple[str, ...]
    capabilities: tuple[Capability, ...]
    status: Status


MODALITY_PROTOCOLS: dict[str, ModalityProtocol] = {
    "CT": ModalityProtocol("Computed Tomography", ("DICOM", "NIfTI"), ("viewer", "mpr", "segmentation", "surface3d", "quantification"), "available"),
    "MR": ModalityProtocol("Magnetic Resonance Imaging", ("DICOM", "NIfTI"), ("viewer", "mpr", "segmentation", "surface3d", "quantification"), "available"),
    "XR": ModalityProtocol("X-Ray", ("DICOM", "PNG", "JPG"), ("viewer",), "viewer-only"),
    "PET": ModalityProtocol("Positron Emission Tomography", ("DICOM", "NIfTI"), ("viewer", "mpr", "surface3d", "quantification"), "viewer-only"),
    "SPECT": ModalityProtocol("SPECT", ("DICOM", "NIfTI"), ("viewer", "mpr", "surface3d", "quantification"), "viewer-only"),
    "PET_CT": ModalityProtocol("PET/CT", ("DICOM",), ("viewer", "mpr", "fusion", "surface3d", "quantification"), "viewer-only"),
    "US": ModalityProtocol("Ultrasound", ("DICOM", "PNG", "JPG"), ("viewer",), "viewer-only"),
    "MG": ModalityProtocol("Mammography", ("DICOM",), ("viewer",), "viewer-only"),
    "FLUORO": ModalityProtocol("Fluoroscopy", ("DICOM",), ("viewer",), "viewer-only"),
    "DXA": ModalityProtocol("DEXA", ("DICOM",), ("viewer", "quantification"), "viewer-only"),
    "NIFTI": ModalityProtocol("NIfTI Research Volume", (".nii", ".nii.gz"), ("viewer", "mpr", "surface3d"), "available"),
}

SEGMENTATION_PROTOCOLS: dict[str, tuple[str, ...]] = {
    "spleen": ("CT",),
    "heart": ("MR",),
    "prostate": ("MR",),
}


def normalize_modality(value: str | None) -> str:
    if not value:
        return "AUTO"
    value = value.strip().upper()
    aliases = {"MRI": "MR", "MAGNETIC RESONANCE": "MR", "X-RAY": "XR", "XRAY": "XR", "PET/CT": "PET_CT", "PETCT": "PET_CT", "ULTRASOUND": "US"}
    return aliases.get(value, value)


def validate_segmentation_protocol(target: str, modality: str | None) -> tuple[str, list[str]]:
    normalized = normalize_modality(modality)
    allowed = SEGMENTATION_PROTOCOLS.get(target)
    if not allowed:
        raise ValueError(f"Unknown segmentation target: {target}")
    if normalized == "AUTO":
        return allowed[0], []
    if normalized not in allowed:
        expected = ", ".join(allowed)
        raise ValueError(f"{target.title()} segmentation is currently validated only for {expected}; received {normalized}.")
    return normalized, []


def public_registry() -> dict[str, dict]:
    return {
        key: {
            "label": value.label,
            "formats": list(value.formats),
            "capabilities": list(value.capabilities),
            "status": value.status,
        }
        for key, value in MODALITY_PROTOCOLS.items()
    }

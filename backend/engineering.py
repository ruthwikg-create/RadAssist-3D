from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import numpy as np
except ImportError:
    np = None

SCHEMA_VERSION = "radassist-result-1.0"
DICOM_SEG_COMPATIBILITY = "segmentation-labelmap-reference-architecture"
DICOM_SR_COMPATIBILITY = "TID-1500-compatible-measurement-architecture"


def _json_safe(value: Any) -> Any:
    """Convert scientific Python values into strict JSON-safe primitives."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if np is not None:
        if isinstance(value, np.ndarray):
            return _json_safe(value.tolist())
        if isinstance(value, np.generic):
            return _json_safe(value.item())
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_input_contract(*, source_type: str, modality: str, dimensions: list[int], spacing_mm: list[float]) -> dict[str, Any]:
    errors: list[str] = []
    if len(dimensions) != 3 or any(int(v) <= 0 for v in dimensions):
        errors.append("INPUT_DIMENSIONS_INVALID")
    if len(spacing_mm) != 3 or any(float(v) <= 0 for v in spacing_mm):
        errors.append("INPUT_SPACING_INVALID")
    if source_type not in {"DICOM", "NIFTI", "SYNTHETIC"}:
        errors.append("INPUT_SOURCE_TYPE_UNSUPPORTED")
    if modality not in {"CT", "MR", "UNKNOWN"}:
        errors.append("INPUT_MODALITY_UNSUPPORTED")
    return {"status": "PASS" if not errors else "FAIL", "errors": errors}


def build_structured_measurements(*, result: dict[str, Any]) -> dict[str, Any]:
    quality = result.get("measurement_quality") or {}
    return {
        "schema_version": SCHEMA_VERSION,
        "target": result.get("target"),
        "measurements": [
            {"name": "segmented_volume", "value": result.get("volume_cm3"), "unit": "cm3", "method": quality.get("measurement_method")},
            {"name": "surface_area", "value": quality.get("surface_area_cm2"), "unit": "cm2", "method": "smoothed marching-cubes triangular mesh"},
            {"name": "mesh_volume", "value": quality.get("mesh_volume_cm3"), "unit": "cm3", "method": "closed-triangle-mesh signed-volume cross-check"},
            {"name": "equivalent_sphere_diameter", "value": quality.get("equivalent_diameter_mm"), "unit": "mm", "method": "volume-equivalent sphere"},
        ],
        "uncertainty_status": {
            "patient_specific_accuracy": "NOT_ESTABLISHED",
            "measurement_uncertainty": "NOT_ESTIMATED",
            "model_validation_status": "BENCHMARK_ONLY" if result.get("validation_benchmark", {}).get("validation_dice") is not None else "NOT_AVAILABLE",
        },
    }


def build_dicom_seg_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "compatibility": DICOM_SEG_COMPATIBILITY,
        "schema_version": SCHEMA_VERSION,
        "modality": "SEG",
        "source_reference": {
            "source_type": result.get("source_type"),
            "original_modality": result.get("modality"),
            "dimensions": result.get("original_dimensions"),
            "spacing_mm": result.get("original_spacing_mm"),
        },
        "segments": [
            {
                "segment_number": metric.get("label"),
                "segment_label": metric.get("name"),
                "voxel_count": metric.get("voxel_count"),
            }
            for metric in result.get("label_metrics", [])
        ],
        "pixel_data_artifact": "segmentation_mask.nii.gz",
        "status": "ARCHITECTURE_ONLY_NOT_DICOM_FILE",
    }


def build_dicom_sr_result(result: dict[str, Any]) -> dict[str, Any]:
    quality = result.get("measurement_quality") or {}
    structured = build_structured_measurements(result=result)
    return {
        "compatibility": DICOM_SR_COMPATIBILITY,
        "schema_version": SCHEMA_VERSION,
        "modality": "SR",
        "measurement_groups": [
            {
                "tracking_identifier": f"RadAssist:{result.get('request_id')}",
                "finding": result.get("target"),
                "measurements": structured["measurements"],
                "qa": {
                    "status": quality.get("status"),
                    "flags": quality.get("flags", []),
                },
            }
        ],
        "status": "ARCHITECTURE_ONLY_NOT_DICOM_FILE",
    }


def build_provenance(result: dict[str, Any]) -> dict[str, Any]:
    structured = build_structured_measurements(result=result)
    return {
        "schema_version": SCHEMA_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "request_id": result.get("request_id"),
        "source": {
            "type": result.get("source_type"),
            "modality": result.get("modality"),
            "dimensions": result.get("original_dimensions"),
            "spacing_mm": result.get("original_spacing_mm"),
        },
        "model": result.get("model_provenance", {}),
        "measurement": result.get("measurement_quality", {}),
        "structured_measurements": structured,
        "dicom_seg": build_dicom_seg_result(result),
        "dicom_sr": build_dicom_sr_result(result),
    }


def write_report_bundle(case_directory: Path, result: dict[str, Any]) -> None:
    report = _json_safe(build_provenance(result))
    (case_directory / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False),
        encoding="utf-8",
    )


def append_audit_event(case_directory: Path, event: str, **details: Any) -> None:
    audit = _json_safe({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event,
        **details,
    })
    with (case_directory / "audit.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(audit, sort_keys=True, allow_nan=False) + "\n")

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import SimpleITK as sitk

import highdicom as hd
from pydicom import dcmread
from pydicom.sr.codedict import codes


def _find_dicom_files(input_paths: list[Path], extraction_root: Path) -> list[Path]:
    candidates: list[Path] = []
    for root in [*input_paths, extraction_root]:
        if root.is_file() and root.suffix.lower() in {".dcm", ".dicom"}:
            candidates.append(root)
        elif root.is_dir():
            candidates.extend(
                p for p in root.rglob("*")
                if p.is_file() and p.suffix.lower() in {".dcm", ".dicom"}
            )
    # ZIP extraction may produce extensionless DICOM files. Probe files by DICOM preamble.
    if extraction_root.exists():
        for p in extraction_root.rglob("*"):
            if not p.is_file() or p in candidates:
                continue
            try:
                with p.open("rb") as handle:
                    if handle.read(132)[128:132] == b"DICM":
                        candidates.append(p)
            except OSError:
                continue
    return sorted(set(candidates))


def _load_sorted_sources(paths: list[Path]) -> list[Any]:
    datasets = [hd.imread(str(path)) for path in paths]
    return hd.spatial.sort_datasets(datasets)


def _property_type(target: str):
    mapping = {
        "spleen": getattr(codes.SCT, "Spleen", None),
        "heart": getattr(codes.SCT, "Heart", None),
        "prostate": getattr(codes.SCT, "Prostate", None),
    }
    return mapping.get(target) or hd.sr.CodedConcept(
        value="91723000",
        scheme_designator="SCT",
        meaning="Anatomical Structure",
    )


def _segment_description(target: str, label_number: int, label_name: str):
    algorithm_identification = hd.AlgorithmIdentificationSequence(
        name="RadAssist 3D AI Segmentation",
        version="1.0",
        family=codes.cid7162.ArtificialIntelligence,
    )
    return hd.seg.SegmentDescription(
        segment_number=label_number,
        segment_label=label_name[:64],
        segmented_property_category=codes.SCT.AnatomicalStructure,
        segmented_property_type=_property_type(target),
        algorithm_type=hd.seg.SegmentAlgorithmTypeValues.AUTOMATIC,
        algorithm_identification=algorithm_identification,
        tracking_id=f"RadAssist-{target}-{label_number}",
        tracking_uid=hd.UID(),
    )


def export_dicom_seg_and_sr(
    *,
    input_paths: list[Path],
    extraction_root: Path,
    mask_path: Path,
    output_directory: Path,
    target: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    """Create interoperable DICOM SEG and TID1500 SR for a DICOM source study.

    NIfTI-only cases are intentionally not converted to DICOM because there is
    no authoritative DICOM source image series to reference.
    """
    dicom_paths = _find_dicom_files(input_paths, extraction_root)
    if not dicom_paths:
        return {
            "status": "NOT_AVAILABLE",
            "reason": "A DICOM source image series is required for SEG/SR export.",
        }

    sources = _load_sorted_sources(dicom_paths)
    if not sources:
        raise ValueError("No readable DICOM source images were found.")

    mask_image = sitk.ReadImage(str(mask_path))
    mask = sitk.GetArrayFromImage(mask_image).astype(np.uint8, copy=False)

    source_shape = (
        len(sources),
        int(sources[0].Rows),
        int(sources[0].Columns),
    )
    if tuple(mask.shape) != source_shape:
        raise ValueError(
            "DICOM SEG export requires the final mask geometry to match the "
            f"source series. Mask={tuple(mask.shape)}, source={source_shape}."
        )

    labels = sorted(int(v) for v in np.unique(mask) if int(v) != 0)
    if not labels:
        raise ValueError("Cannot create DICOM SEG from an empty segmentation.")

    label_names = {
        int(item.get("label")): str(item.get("name", f"Label {item.get('label')}"))
        for item in result.get("label_metrics", [])
        if item.get("label") is not None
    }

    stacked = np.stack(
        [(mask == label).astype(np.uint8) for label in labels],
        axis=-1,
    )
    descriptions = [
        _segment_description(
            target,
            index,
            label_names.get(label, f"{target.title()} label {label}"),
        )
        for index, label in enumerate(labels, start=1)
    ]

    output_directory.mkdir(parents=True, exist_ok=True)
    seg_path = output_directory / "radassist_segmentation.dcm"
    sr_path = output_directory / "radassist_measurements_sr.dcm"

    seg_dataset = hd.seg.Segmentation(
        source_images=sources,
        pixel_array=stacked,
        segmentation_type=hd.seg.SegmentationTypeValues.BINARY,
        segment_descriptions=descriptions,
        series_instance_uid=hd.UID(),
        series_number=700,
        sop_instance_uid=hd.UID(),
        instance_number=1,
        manufacturer="RadAssist 3D",
        manufacturer_model_name="RadAssist 3D Research Workstation",
        software_versions="audit-1.0",
        series_description=f"RadAssist AI segmentation - {target.title()}",
    )
    seg_dataset.save_as(str(seg_path), write_like_original=False)

    # Build a TID1500 measurement report linked to the generated segment.
    observer_context = hd.sr.ObservationContext(
        observer_device_context=hd.sr.ObserverContext(
            observer_type=codes.DCM.Device,
            observer_identifying_attributes=hd.sr.DeviceObserverIdentifyingAttributes(
                uid=hd.UID(),
                manufacturer="RadAssist 3D",
                model_name="Research Workstation",
            ),
        )
    )

    volume_mm3 = float(result.get("volume_cm3", 0.0)) * 1000.0
    measurement = hd.sr.Measurement(
        name=codes.SCT.Volume,
        value=volume_mm3,
        unit=codes.UCUM.CubicMillimeter,
        tracking_identifier=hd.sr.TrackingIdentifier(
            identifier=f"RadAssist-{target}-volume",
            uid=hd.UID(),
        ),
    )

    referenced_segment = hd.sr.ReferencedSegment.from_segmentation(
        segmentation=seg_dataset,
        segment_number=1,
    )
    group = hd.sr.VolumetricROIMeasurementsAndQualitativeEvaluations(
        referenced_segment=referenced_segment,
        tracking_identifier=hd.sr.TrackingIdentifier(
            identifier=f"RadAssist-{target}-measurement",
            uid=hd.UID(),
        ),
        finding_category=codes.SCT.AnatomicalStructure,
        finding_type=_property_type(target),
        measurements=[measurement],
    )

    procedure_code = (
        getattr(codes.LN, "CTUnspecifiedBodyRegion", None)
        if str(result.get("modality", "")).upper() == "CT"
        else getattr(codes.LN, "MRUnspecifiedBodyRegion", None)
    )
    procedure_code = procedure_code or codes.LN.CTUnspecifiedBodyRegion

    report = hd.sr.MeasurementReport(
        observation_context=observer_context,
        procedure_reported=procedure_code,
        imaging_measurements=[group],
        title=codes.DCM.ImagingMeasurementReport,
    )
    sr_dataset = hd.sr.Comprehensive3DSR(
        evidence=sources,
        content=report,
        series_number=701,
        series_instance_uid=hd.UID(),
        sop_instance_uid=hd.UID(),
        instance_number=1,
        manufacturer="RadAssist 3D",
        series_description=f"RadAssist quantitative measurements - {target.title()}",
    )
    sr_dataset.save_as(str(sr_path), write_like_original=False)

    return {
        "status": "GENERATED",
        "segmentation": {
            "path": seg_path.name,
            "sop_class_uid": str(seg_dataset.SOPClassUID),
            "sop_instance_uid": str(seg_dataset.SOPInstanceUID),
            "segments": len(labels),
        },
        "structured_report": {
            "path": sr_path.name,
            "sop_class_uid": str(sr_dataset.SOPClassUID),
            "sop_instance_uid": str(sr_dataset.SOPInstanceUID),
            "template": "TID1500 Measurement Report",
        },
    }

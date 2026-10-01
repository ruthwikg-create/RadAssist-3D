from __future__ import annotations

import hashlib
import io
import shutil
import zipfile
from pathlib import Path
from typing import Any

import numpy as np
import pydicom
import highdicom as hd
from pydicom.dataset import Dataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid
from pydicom.sr.codedict import codes


PHI_TAG_NAMES = (
    "PatientName",
    "PatientID",
    "PatientBirthDate",
    "PatientBirthTime",
    "PatientSex",
    "OtherPatientIDs",
    "OtherPatientNames",
    "OtherPatientIDsSequence",
    "PatientAddress",
    "PatientTelephoneNumbers",
    "PatientMotherBirthName",
    "EthnicGroup",
    "Occupation",
    "MilitaryRank",
    "MedicalRecordLocator",
    "MedicalAlerts",
    "Allergies",
    "AdditionalPatientHistory",
    "ReferringPhysicianName",
    "ReferringPhysicianAddress",
    "ReferringPhysicianTelephoneNumbers",
    "PerformingPhysicianName",
    "NameOfPhysiciansReadingStudy",
    "OperatorsName",
    "InstitutionName",
    "InstitutionAddress",
    "InstitutionalDepartmentName",
    "AccessionNumber",
    "StudyID",
    "StudyDescription",
    "SeriesDescription",
    "StationName",
    "DeviceSerialNumber",
)

DATE_TAG_NAMES = (
    "StudyDate",
    "SeriesDate",
    "AcquisitionDate",
    "ContentDate",
    "StudyTime",
    "SeriesTime",
    "AcquisitionTime",
    "ContentTime",
)

UID_TAG_NAMES = (
    "StudyInstanceUID",
    "SeriesInstanceUID",
    "SOPInstanceUID",
    "FrameOfReferenceUID",
)


def _safe_value(ds: Dataset, name: str) -> str | None:
    value = getattr(ds, name, None)
    if value is None:
        return None
    if isinstance(value, (bytes, bytearray)):
        return None
    return str(value)


def summarize_dataset(ds: Dataset) -> dict[str, Any]:
    keys = (
        "Modality", "SOPClassUID", "SOPInstanceUID",
        "StudyInstanceUID", "SeriesInstanceUID",
        "FrameOfReferenceUID", "StudyDescription",
        "SeriesDescription", "SeriesNumber", "InstanceNumber",
        "Rows", "Columns", "NumberOfFrames",
        "PixelSpacing", "SliceThickness", "SpacingBetweenSlices",
        "ImageOrientationPatient", "ImagePositionPatient",
        "Manufacturer", "ManufacturerModelName",
        "BodyPartExamined", "ProtocolName",
    )
    return {key: _safe_value(ds, key) for key in keys if _safe_value(ds, key) is not None}


def collect_dicom_files(root: Path) -> list[Path]:
    files = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        try:
            ds = pydicom.dcmread(str(path), stop_before_pixels=True, force=False)
            if getattr(ds, "SOPInstanceUID", None):
                files.append(path)
        except Exception:
            continue
    return files


def series_metadata(root: Path) -> dict[str, Any]:
    files = collect_dicom_files(root)
    if not files:
        raise ValueError("No readable DICOM instances were found.")

    datasets = [pydicom.dcmread(str(path), stop_before_pixels=True) for path in files]
    studies = sorted({str(getattr(ds, "StudyInstanceUID", "")) for ds in datasets if getattr(ds, "StudyInstanceUID", None)})
    series = sorted({str(getattr(ds, "SeriesInstanceUID", "")) for ds in datasets if getattr(ds, "SeriesInstanceUID", None)})
    modalities = sorted({str(getattr(ds, "Modality", "")) for ds in datasets if getattr(ds, "Modality", None)})

    return {
        "status": "PASS" if len(series) == 1 else "REVIEW",
        "instance_count": len(files),
        "study_count": len(studies),
        "series_count": len(series),
        "modalities": modalities,
        "study_instance_uids": studies,
        "series_instance_uids": series,
        "representative": summarize_dataset(datasets[0]),
        "phi_fields_present": sorted(
            name for name in PHI_TAG_NAMES + DATE_TAG_NAMES
            if getattr(datasets[0], name, None) not in (None, "")
        ),
        "warning": "Pixel data may contain burned-in identifiers; this metadata operation does not inspect pixels.",
    }


def _replacement_uid(original: str, salt: str) -> str:
    digest = hashlib.sha256((salt + original).encode("utf-8")).hexdigest()
    # Generate a deterministic numeric suffix under the DICOM UID length limit.
    return "2.25." + str(int(digest[:30], 16))


def anonymize_dataset(ds: Dataset, salt: str, retain_uids: bool = False) -> Dataset:
    ds = ds.copy()
    ds.remove_private_tags()

    # Conservative Basic Confidentiality-style removal for research use.
    for name in PHI_TAG_NAMES:
        if hasattr(ds, name):
            try:
                delattr(ds, name)
            except Exception:
                pass

    for name in DATE_TAG_NAMES:
        if hasattr(ds, name):
            try:
                delattr(ds, name)
            except Exception:
                pass

    if not retain_uids:
        for name in UID_TAG_NAMES:
            value = getattr(ds, name, None)
            if value:
                setattr(ds, name, _replacement_uid(str(value), salt))

    ds.PatientIdentityRemoved = "YES"
    ds.DeidentificationMethod = (
        "RadAssist 3D research de-identification: "
        "Basic confidentiality-style attribute removal; "
        "private tags removed; identifiers replaced; "
        "pixel burned-in text not inspected or removed."
    )
    if hasattr(ds, "DeidentificationMethodCodeSequence"):
        del ds.DeidentificationMethodCodeSequence

    if hasattr(ds, "file_meta"):
        ds.file_meta = ds.file_meta.copy()
        if getattr(ds.file_meta, "MediaStorageSOPInstanceUID", None):
            ds.file_meta.MediaStorageSOPInstanceUID = getattr(ds, "SOPInstanceUID", generate_uid())
        ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian

    return ds


def anonymize_directory(source: Path, destination: Path, salt: str) -> dict[str, Any]:
    files = collect_dicom_files(source)
    if not files:
        raise ValueError("No DICOM instances found to anonymize.")

    destination.mkdir(parents=True, exist_ok=True)
    mapping: dict[str, str] = {}
    output_files: list[str] = []

    for source_file in files:
        ds = pydicom.dcmread(str(source_file), force=False)
        original_sop = str(getattr(ds, "SOPInstanceUID", source_file.name))
        anon = anonymize_dataset(ds, salt=salt, retain_uids=False)
        out = destination / (source_file.stem + ".dcm")
        anon.save_as(str(out), write_like_original=False)
        output_files.append(str(out))
        mapping[original_sop] = str(getattr(anon, "SOPInstanceUID", ""))

    return {
        "status": "PASS",
        "instance_count": len(output_files),
        "files": output_files,
        "uid_replacements": mapping,
        "pixel_deidentification": "NOT_PERFORMED",
    }


def zip_directory(source: Path) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(source).as_posix())
    return buffer.getvalue()


def _segment_code(name: str):
    normalized = name.lower()
    mapping = {
        "spleen": codes.SCT.Spleen,
        "heart": codes.SCT.Heart,
        "myocardium": codes.SCT.Myocardium,
        "lv blood pool": codes.SCT.LeftVentricle,
        "rv blood pool": codes.SCT.RightVentricle,
        "central gland": codes.SCT.Prostate,
        "peripheral zone": codes.SCT.Prostate,
        "prostate": codes.SCT.Prostate,
    }
    return mapping.get(normalized, codes.SCT.Tissue)


def create_segmentation(
    source_files: list[Path],
    mask_array_zyx: np.ndarray,
    label_names: dict[int, str],
    output_path: Path,
    algorithm_name: str,
    algorithm_version: str = "1.0",
) -> dict[str, Any]:
    if not source_files:
        raise ValueError("DICOM SEG requires source DICOM instances.")

    source_images = [pydicom.dcmread(str(path), force=False) for path in source_files]
    source_images = hd.spatial.sort_datasets(source_images)

    if mask_array_zyx.ndim != 3:
        raise ValueError("Segmentation mask must be a 3D labelmap.")

    expected = (len(source_images), int(source_images[0].Rows), int(source_images[0].Columns))
    if tuple(mask_array_zyx.shape) != expected:
        raise ValueError(
            f"SEG geometry mismatch: mask={tuple(mask_array_zyx.shape)} source={expected}. "
            "Refusing to create a spatially ambiguous DICOM SEG."
        )

    labels = [label for label in sorted(label_names) if label != 0]
    if not labels or not np.any(mask_array_zyx > 0):
        raise ValueError("Cannot create DICOM SEG from an empty segmentation.")

    algorithm = hd.AlgorithmIdentificationSequence(
        name=algorithm_name,
        version=algorithm_version,
        family=codes.cid7162.ArtificialIntelligence,
    )

    descriptions = []
    for segment_number, label_value in enumerate(labels, start=1):
        descriptions.append(
            hd.seg.SegmentDescription(
                segment_number=int(segment_number),
                segment_label=label_names[label_value],
                segmented_property_category=codes.SCT.AnatomicalStructure,
                segmented_property_type=_segment_code(label_names[number]),
                algorithm_type=hd.seg.SegmentAlgorithmTypeValues.AUTOMATIC,
                algorithm_identification=algorithm,
                tracking_uid=hd.UID(),
                tracking_id=f"RadAssist-{label_names[label_value]}",
            )
        )

    pixel_array = np.stack(
        [(mask_array_zyx == label) for label in labels],
        axis=3,
    ).astype(np.uint8)

    seg = hd.seg.Segmentation(
        source_images=source_images,
        pixel_array=pixel_array,
        segmentation_type=hd.seg.SegmentationTypeValues.BINARY,
        segment_descriptions=descriptions,
        series_instance_uid=hd.UID(),
        series_number=900,
        sop_instance_uid=hd.UID(),
        instance_number=1,
        manufacturer="RadAssist 3D",
        manufacturer_model_name="RadAssist 3D Research Workstation",
        software_versions=algorithm_version,
        device_serial_number="RADASSIST-RESEARCH",
        transfer_syntax_uid=ExplicitVRLittleEndian,
        series_description="RadAssist 3D AI Segmentation",
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    seg.save_as(str(output_path), write_like_original=False)

    return {
        "status": "CREATED",
        "path": str(output_path),
        "sop_instance_uid": str(seg.SOPInstanceUID),
        "series_instance_uid": str(seg.SeriesInstanceUID),
        "segment_count": len(labels),
        "source_instance_count": len(source_images),
        "sop_class_uid": str(seg.SOPClassUID),
    }


def create_structured_report(
    source_files: list[Path],
    measurements: list[dict[str, Any]],
    target: str,
    output_path: Path,
) -> dict[str, Any]:
    if not source_files:
        raise ValueError("DICOM SR requires source DICOM instances.")

    source_datasets = [pydicom.dcmread(str(path), force=False) for path in source_files]
    source = source_datasets[0]

    observer = hd.sr.ObserverContext(
        observer_type=codes.DCM.Device,
        observer_identifying_attributes=hd.sr.DeviceObserverIdentifyingAttributes(
            uid=hd.UID(),
            name="RadAssist 3D",
            manufacturer="RadAssist 3D",
            model_name="Research Workstation",
        ),
    )
    context = hd.sr.ObservationContext(observer_device_context=observer)

    source_refs = [hd.sr.SourceImageForMeasurementGroup.from_source_image(ds) for ds in source_datasets]
    group_measurements = []
    for item in measurements:
        value = item.get("value")
        if not isinstance(value, (int, float)) or not np.isfinite(value):
            continue
        unit = item.get("unit")
        if unit == "cm3":
            unit_code = codes.UCUM.CubicCentimeter
        elif unit == "cm2":
            unit_code = codes.UCUM.SquareCentimeter
        elif unit == "mm":
            unit_code = codes.UCUM.Millimeter
        else:
            unit_code = codes.UCUM.NoUnits
        group_measurements.append(
            hd.sr.Measurement(
                name=codes.SCT.Volume if item["name"] == "segmented_volume" else (
                    hd.sr.CodedConcept(value="RADASSIST-SURFACE-AREA", scheme_designator="99RADASSIST", meaning="Surface area") if item["name"] == "surface_area" else codes.SCT.Volume
                ),
                value=float(value),
                unit=unit_code,
                tracking_identifier=hd.sr.TrackingIdentifier(
                    uid=hd.UID(),
                    identifier=str(item["name"]),
                ),
            )
        )

    if not group_measurements:
        raise ValueError("No finite measurements available for DICOM SR.")

    group = hd.sr.MeasurementsAndQualitativeEvaluations(
        source_images=source_refs,
        tracking_identifier=hd.sr.TrackingIdentifier(
            uid=hd.UID(),
            identifier=f"RadAssist-{target}-measurements",
        ),
        measurements=group_measurements,
    )

    procedure = (
        getattr(codes.LN, "MRUnspecifiedBodyRegion", codes.LN.CTUnspecifiedBodyRegion)
        if str(getattr(source, "Modality", "")) == "MR"
        else codes.LN.CTUnspecifiedBodyRegion
    )
    report = hd.sr.MeasurementReport(
        observation_context=context,
        procedure_reported=procedure,
        imaging_measurements=[group],
        title=codes.DCM.ImagingMeasurementReport,
    )
    sr = hd.sr.Comprehensive3DSR(
        evidence=source_datasets,
        content=report,
        series_number=901,
        series_instance_uid=hd.UID(),
        sop_instance_uid=hd.UID(),
        instance_number=1,
        manufacturer="RadAssist 3D",
        series_description="RadAssist 3D Quantitative Measurements",
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sr.save_as(str(output_path), write_like_original=False)
    return {
        "status": "CREATED",
        "path": str(output_path),
        "sop_instance_uid": str(sr.SOPInstanceUID),
        "sop_class_uid": str(sr.SOPClassUID),
    }

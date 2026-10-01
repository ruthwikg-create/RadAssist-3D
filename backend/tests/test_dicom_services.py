from __future__ import annotations

import numpy as np
import pydicom
import highdicom as hd
from pydicom.data import get_testdata_file

from backend.dicom_services import (
    anonymize_dataset,
    create_segmentation,
    create_structured_report,
    series_metadata,
)


def _ct_dataset():
    path = get_testdata_file("CT_small.dcm")
    assert path is not None
    return pydicom.dcmread(path)


def test_anonymization_removes_identifiers_and_replaces_uids():
    ds = _ct_dataset()
    original_study = str(ds.StudyInstanceUID)
    original_series = str(ds.SeriesInstanceUID)
    original_sop = str(ds.SOPInstanceUID)

    anon = anonymize_dataset(ds, salt="unit-test-salt")

    assert getattr(anon, "PatientIdentityRemoved", None) == "YES"
    assert not hasattr(anon, "PatientName")
    assert not hasattr(anon, "PatientID")
    assert str(anon.StudyInstanceUID) != original_study
    assert str(anon.SeriesInstanceUID) != original_series
    assert str(anon.SOPInstanceUID) != original_sop
    assert len(str(anon.StudyInstanceUID)) <= 64


def test_dicom_seg_round_trip(tmp_path):
    source = _ct_dataset()
    source_path = tmp_path / "source.dcm"
    source.save_as(source_path, write_like_original=False)

    mask = np.zeros((1, int(source.Rows), int(source.Columns)), dtype=np.uint8)
    mask[0, 20:40, 30:50] = 1

    output = tmp_path / "segmentation.dcm"
    result = create_segmentation(
        source_files=[source_path],
        mask_array_zyx=mask,
        label_names={1: "spleen"},
        output_path=output,
        algorithm_name="RadAssist Unit Test",
    )

    assert result["status"] == "CREATED"
    seg = pydicom.dcmread(output)
    assert seg.SOPClassUID == "1.2.840.10008.5.1.4.1.1.66.4"
    assert int(seg.SegmentSequence[0].SegmentNumber) == 1
    assert seg.SegmentSequence[0].SegmentLabel == "spleen"
    assert len(seg.ReferencedSeriesSequence) == 1
    parsed_seg = hd.seg.segread(str(output))
    assert parsed_seg.number_of_segments == 1


def test_dicom_sr_round_trip(tmp_path):
    source = _ct_dataset()
    source_path = tmp_path / "source.dcm"
    source.save_as(source_path, write_like_original=False)

    output = tmp_path / "structured_report.dcm"
    result = create_structured_report(
        source_files=[source_path],
        measurements=[
            {"name": "segmented_volume", "value": 12.5, "unit": "cm3"},
            {"name": "surface_area", "value": 8.0, "unit": "cm2"},
        ],
        target="spleen",
        output_path=output,
    )

    assert result["status"] == "CREATED"
    sr = pydicom.dcmread(output)
    assert sr.SOPClassUID == "1.2.840.10008.5.1.4.1.1.88.22"
    assert sr.ContentTemplateSequence[0].TemplateIdentifier == "1500"
    parsed_sr = hd.sr.srread(str(output))
    assert parsed_sr.SOPClassUID == sr.SOPClassUID


def test_series_metadata_reports_single_series(tmp_path):
    source = _ct_dataset()
    path = tmp_path / "source.dcm"
    source.save_as(path, write_like_original=False)

    metadata = series_metadata(tmp_path)
    assert metadata["status"] == "PASS"
    assert metadata["instance_count"] == 1
    assert metadata["series_count"] == 1

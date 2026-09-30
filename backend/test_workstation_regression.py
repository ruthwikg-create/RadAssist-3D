from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import SimpleITK as sitk

try:
    from backend.multimodel_engine import _largest_component_per_label, _smooth_mesh
    from backend.pipeline import (
        MeshData,
        _mesh_geometry_metrics,
        _physical_mesh_from_mask,
        advanced_shape_metrics,
        load_medical_volume,
    )
    from backend.engineering import build_input_manifest
    from backend.case_store import case_dir
except ModuleNotFoundError:
    from multimodel_engine import _largest_component_per_label, _smooth_mesh
    from pipeline import (
        MeshData,
        _mesh_geometry_metrics,
        _physical_mesh_from_mask,
        advanced_shape_metrics,
        load_medical_volume,
    )
    from engineering import build_input_manifest
    from case_store import case_dir


class WorkstationRegressionTests(unittest.TestCase):
    def test_component_filter_keeps_largest_label_island(self) -> None:
        array = np.zeros((12, 12, 12), dtype=np.uint8)
        array[2:7, 2:7, 2:7] = 1
        array[9:11, 9:11, 9:11] = 1
        image = sitk.GetImageFromArray(array)
        image.SetSpacing((1.0, 1.0, 1.0))

        cleaned, qa = _largest_component_per_label(image)
        result = sitk.GetArrayFromImage(cleaned)

        self.assertEqual(int((result == 1).sum()), 125)
        self.assertEqual(qa["1"]["raw_connected_components"], 2)
        self.assertEqual(qa["1"]["removed_voxel_count"], 8)

    def test_mesh_geometry_is_nonzero(self) -> None:
        vertices = [
            [0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1],
        ]
        faces = [[0, 2, 1], [0, 1, 3], [0, 3, 2], [1, 2, 3]]
        mesh = MeshData(vertices, faces, 4, 4)
        area, volume = _mesh_geometry_metrics(mesh)
        self.assertIsNotNone(area)
        self.assertIsNotNone(volume)
        self.assertGreater(area or 0, 0)
        self.assertGreater(volume or 0, 0)

    def test_mesh_smoothing_preserves_topology(self) -> None:
        mesh = MeshData(
            [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]],
            [[0, 2, 1], [0, 1, 3], [0, 3, 2], [1, 2, 3]],
            4,
            4,
        )
        smoothed = _smooth_mesh(mesh, iterations=2)
        self.assertEqual(smoothed.vertex_count, mesh.vertex_count)
        self.assertEqual(smoothed.face_count, mesh.face_count)
        self.assertEqual(smoothed.faces, mesh.faces)

    def test_physical_mesh_applies_spacing_once(self) -> None:
        array = np.zeros((8, 8, 8), dtype=np.uint8)
        array[2:4, 2:4, 2:4] = 1
        image = sitk.GetImageFromArray(array)
        image.SetSpacing((2.0, 3.0, 4.0))

        mesh = _physical_mesh_from_mask(image, step_size=1)

        self.assertGreater(mesh.vertex_count, 0)
        vertices = np.asarray(mesh.vertices, dtype=float)
        extent = vertices.max(axis=0) - vertices.min(axis=0)

        # Two occupied voxels along each axis produce a four/eight/twelve mm
        # physical extent according to the native X/Y/Z spacing.
        np.testing.assert_allclose(
            extent,
            np.asarray([4.0, 6.0, 8.0]),
            atol=0.01,
        )

    def test_advanced_shape_metrics_are_physical_and_finite(self) -> None:
        array = np.zeros((10, 10, 10), dtype=np.uint8)
        array[2:6, 2:6, 2:6] = 1
        image = sitk.GetImageFromArray(array)
        image.SetSpacing((2.0, 3.0, 4.0))

        metrics = advanced_shape_metrics(image, surface_area_cm2=1.0, mesh_volume_cm3=1.0)

        self.assertEqual(metrics["foreground_voxels"], 64)
        np.testing.assert_allclose(
            metrics["bounding_box_mm"],
            [8.0, 12.0, 16.0],
            atol=0.001,
        )
        self.assertTrue(all(np.isfinite(metrics["principal_spread_mm"])))
        self.assertGreater(metrics["sphericity"], 0)
        self.assertGreater(metrics["compactness"], 0)

    def test_four_dimensional_nifti_selects_declared_frame(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            volume = np.zeros((2, 6, 6, 6), dtype=np.float32)
            volume[0, 2:4, 2:4, 2:4] = 10
            volume[1, 1:5, 1:5, 1:5] = 20

            # NIfTI is written with [X,Y,Z,T] through SimpleITK's 4D array convention.
            image = sitk.GetImageFromArray(volume, isVector=False)
            path = root / "four_dimensional.nii.gz"
            sitk.WriteImage(image, str(path))

            with patch.dict("os.environ", {"RADASSIST_NIFTI_FRAME_INDEX": "1"}):
                loaded = load_medical_volume([path], root / "extract")

            self.assertEqual(loaded.image.GetDimension(), 3)
            self.assertEqual(loaded.image.GetSize(), (6, 6, 6))
            self.assertTrue(loaded.input_notes)
            self.assertIn("frame 1 of 2", loaded.input_notes[0])

    def test_input_manifest_hashes_without_source_filename(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "patient-name.dcm"
            path.write_bytes(b"radassist-test")
            manifest = build_input_manifest([path])
            self.assertEqual(manifest[0]["index"], 0)
            self.assertEqual(manifest[0]["size_bytes"], 14)
            self.assertNotIn("patient-name.dcm", manifest[0].values())

    def test_input_manifest_contains_no_source_filename(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "patient_name_123.dcm"
            path.write_bytes(b"radassist-test")
            from backend.engineering import build_input_manifest
            manifest = build_input_manifest([path])
            self.assertNotIn("patient_name_123.dcm", str(manifest))
            self.assertEqual(len(manifest[0]["sha256"]), 64)

    def test_case_identifier_rejects_path_traversal(self) -> None:
        with self.assertRaises(ValueError):
            case_dir("../outside")
        with self.assertRaises(ValueError):
            case_dir("case/../../outside")


if __name__ == "__main__":
    unittest.main()

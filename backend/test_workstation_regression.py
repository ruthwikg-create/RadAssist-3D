from __future__ import annotations

import unittest

import numpy as np
import SimpleITK as sitk

try:
    from backend.multimodel_engine import _largest_component_per_label, _smooth_mesh
    from backend.pipeline import MeshData, _mesh_geometry_metrics
except ModuleNotFoundError:
    from multimodel_engine import _largest_component_per_label, _smooth_mesh
    from pipeline import MeshData, _mesh_geometry_metrics


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
        from backend.pipeline import _physical_mesh_from_mask

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


if __name__ == "__main__":
    unittest.main()

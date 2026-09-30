from __future__ import annotations

import threading
from pathlib import Path
from time import perf_counter
from typing import Any

import numpy as np
import SimpleITK as sitk


# Support both:
#   python -c "from backend.multimodel_engine import ..."
# and direct backend-style imports.
try:
    from .heart_model_adapter import CardiacVentricularAdapter
    from .pipeline import (
        create_mesh,
        _mesh_geometry_metrics,
        advanced_shape_metrics,
        MeshData,
        load_medical_volume,
        write_sanitized_mask,
        write_sanitized_nifti,
    )
    from .prostate_model_adapter import ProstateMRIAdapter
except ImportError:
    from heart_model_adapter import CardiacVentricularAdapter
    from pipeline import (
        create_mesh,
        _mesh_geometry_metrics,
        advanced_shape_metrics,
        MeshData,
        load_medical_volume,
        write_sanitized_mask,
        write_sanitized_nifti,
    )
    from prostate_model_adapter import ProstateMRIAdapter


TARGETS = {
    "heart": {
        "display_name": "Heart",
        "modality": "MR",
        "labels": {
            0: "background",
            1: "LV blood pool",
            2: "myocardium",
            3: "RV blood pool",
        },
    },
    "prostate": {
        "display_name": "Prostate",
        "modality": "MR",
        "labels": {
            0: "background",
            1: "central gland",
            2: "peripheral zone",
        },
    },
}


# Phase 1/3 engineering controls. These are deliberately conservative defaults:
# retain the largest connected component per anatomical label, keep the raw
# segmentation available for provenance, and smooth only the rendered surface.
KEEP_LARGEST_COMPONENT = True
MESH_SMOOTH_ITERATIONS = 3
MESH_SMOOTH_LAMBDA = 0.35
MESH_SMOOTH_MU = -0.40


def _largest_component_per_label(mask: sitk.Image) -> tuple[sitk.Image, dict[str, dict[str, Any]]]:
    """Remove disconnected islands independently for every foreground label."""
    array = sitk.GetArrayFromImage(mask).astype(np.uint8, copy=False)
    cleaned = np.zeros_like(array, dtype=np.uint8)
    qa: dict[str, dict[str, Any]] = {}

    for label in sorted(int(v) for v in np.unique(array) if int(v) != 0):
        label_array = (array == label).astype(np.uint8)
        before = int(label_array.sum())
        if before == 0:
            continue

        binary = sitk.GetImageFromArray(label_array)
        binary.CopyInformation(mask)
        connected = sitk.ConnectedComponent(binary)
        stats = sitk.LabelShapeStatisticsImageFilter()
        stats.Execute(connected)
        components = list(stats.GetLabels())
        sizes = [int(stats.GetNumberOfPixels(component)) for component in components]

        if KEEP_LARGEST_COMPONENT and components:
            largest_component = components[int(np.argmax(sizes))]
            retained = sitk.GetArrayFromImage(connected) == largest_component
        else:
            retained = label_array.astype(bool)

        retained_count = int(retained.sum())
        cleaned[retained] = np.uint8(label)
        qa[str(label)] = {
            "raw_connected_components": len(components),
            "raw_voxel_count": before,
            "retained_voxel_count": retained_count,
            "removed_voxel_count": before - retained_count,
            "largest_component_fraction_pct": round(
                100.0 * max(sizes) / before, 3
            ) if sizes else None,
        }

    output = sitk.GetImageFromArray(cleaned)
    output.CopyInformation(mask)
    output.SetSpacing(mask.GetSpacing())
    output.SetOrigin(mask.GetOrigin())
    output.SetDirection(mask.GetDirection())
    return output, qa


def _smooth_mesh(mesh: Any, iterations: int = MESH_SMOOTH_ITERATIONS) -> Any:
    """Taubin-style surface smoothing without adding a runtime dependency."""
    if mesh.vertex_count < 4 or mesh.face_count < 4 or iterations <= 0:
        return mesh

    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    faces = np.asarray(mesh.faces, dtype=np.int64)
    adjacency: list[set[int]] = [set() for _ in range(len(vertices))]

    for a, b, c in faces:
        if not (0 <= a < len(vertices) and 0 <= b < len(vertices) and 0 <= c < len(vertices)):
            continue
        adjacency[a].update((int(b), int(c)))
        adjacency[b].update((int(a), int(c)))
        adjacency[c].update((int(a), int(b)))

    for _ in range(iterations):
        for factor in (MESH_SMOOTH_LAMBDA, MESH_SMOOTH_MU):
            updated = vertices.copy()
            for index, neighbors in enumerate(adjacency):
                if not neighbors:
                    continue
                mean = vertices[list(neighbors)].mean(axis=0)
                updated[index] = vertices[index] + factor * (mean - vertices[index])
            vertices = updated

    smoothed = type(mesh)(
        vertices=np.round(vertices, 4).tolist(),
        faces=faces.astype(np.int32).tolist(),
        vertex_count=int(len(vertices)),
        face_count=int(len(faces)),
    )
    return smoothed


def _source_intensity_statistics(
    image: sitk.Image,
    mask: sitk.Image,
) -> dict[str, float | None]:
    source = sitk.GetArrayFromImage(image).astype(np.float32, copy=False)
    foreground = sitk.GetArrayFromImage(mask) > 0
    values = source[foreground]
    values = values[np.isfinite(values)]
    if values.size == 0:
        return {
            "mean_hu": None, "std_hu": None, "min_hu": None,
            "max_hu": None, "median_hu": None,
            "p05_hu": None, "p95_hu": None,
        }
    return {
        # Field names are retained for API compatibility. For MRI these are
        # source signal intensities, never HU.
        "mean_hu": float(np.mean(values)),
        "std_hu": float(np.std(values)),
        "min_hu": float(np.min(values)),
        "max_hu": float(np.max(values)),
        "median_hu": float(np.median(values)),
        "p05_hu": float(np.percentile(values, 5)),
        "p95_hu": float(np.percentile(values, 95)),
    }


class MultiModelInferenceEngine:
    """
    Dispatcher for the non-spleen RadAssist research models.

    Spleen intentionally remains in RadAssistInferenceEngine.

    Supported targets:
        heart
        prostate
    """

    def __init__(
        self,
        heart_model: CardiacVentricularAdapter,
        prostate_model: ProstateMRIAdapter,
    ) -> None:
        self.models = {
            "heart": heart_model,
            "prostate": prostate_model,
        }

        self.locks = {
            "heart": threading.Lock(),
            "prostate": threading.Lock(),
        }

    @staticmethod
    def _load_input(
        input_paths: list[Path],
        extraction_root: Path,
        target: str,
    ):
        loaded = load_medical_volume(
            input_paths,
            extraction_root,
        )

        # NIfTI files do not necessarily contain a reliable modality tag.
        # For the MRI models, the selected model defines the expected
        # research modality.
        if loaded.source_type == "NIFTI":
            loaded.modality = "MR"

        expected_modality = TARGETS[target]["modality"]

        if loaded.modality not in {
            expected_modality,
            "UNKNOWN",
        }:
            raise ValueError(
                f"{target.title()} model expects "
                f"{expected_modality}, "
                f"but the supplied study is tagged as "
                f"{loaded.modality}."
            )

        if loaded.image.GetDimension() != 3:
            raise ValueError(
                "RadAssist MRI models currently require "
                "a 3D volume."
            )

        return loaded

    @staticmethod
    def _empty_mesh() -> dict[str, Any]:
        return {
            "vertices": [],
            "faces": [],
            "vertex_count": 0,
            "face_count": 0,
        }

    @staticmethod
    def _centroid_mm(
        mask: sitk.Image,
    ) -> list[float] | None:
        array = sitk.GetArrayFromImage(mask)

        coords = np.argwhere(array > 0)

        if coords.size == 0:
            return None

        # SimpleITK array indexing is Z,Y,X.
        zyx = coords.mean(axis=0)

        index_xyz = [
            float(zyx[2]),
            float(zyx[1]),
            float(zyx[0]),
        ]

        point = mask.TransformContinuousIndexToPhysicalPoint(
            index_xyz
        )

        return [float(v) for v in point]

    @staticmethod
    def _measurement_quality(
        image: sitk.Image,
        mask: sitk.Image,
        surface_area_cm2: float | None,
        mesh_volume_cm3: float | None,
        intensity_stats: dict[str, float | None],
    ) -> dict[str, Any]:
        mask_array = sitk.GetArrayFromImage(mask)
        foreground = mask_array > 0
        voxel_count = int(np.count_nonzero(foreground))
        voxel_volume_mm3 = float(np.prod(mask.GetSpacing()))
        labelmap_volume_cm3 = voxel_count * voxel_volume_mm3 / 1000.0
        total_voxels = int(mask_array.size)
        mask_fraction_pct = 100.0 * voxel_count / total_voxels if total_voxels else 0.0
        equivalent_diameter_mm = (
            (6.0 * labelmap_volume_cm3 * 1000.0 / np.pi) ** (1.0 / 3.0)
            if labelmap_volume_cm3 > 0 else None
        )

        connected_components = 0
        largest_component_fraction = None
        if foreground.any():
            binary = sitk.GetImageFromArray(foreground.astype(np.uint8))
            binary.CopyInformation(mask)
            cc = sitk.ConnectedComponent(binary)
            stats = sitk.LabelShapeStatisticsImageFilter()
            stats.Execute(cc)
            sizes = [int(stats.GetNumberOfPixels(label)) for label in stats.GetLabels()]
            connected_components = len(sizes)
            largest_component_fraction = (
                100.0 * max(sizes) / voxel_count if sizes else None
            )

        touches_boundary = bool(
            foreground.any() and (
                foreground[0].any() or foreground[-1].any()
                or foreground[:, 0, :].any() or foreground[:, -1, :].any()
                or foreground[:, :, 0].any() or foreground[:, :, -1].any()
            )
        )

        flags = [
            "PATIENT_SPECIFIC_ACCURACY_NOT_ESTIMATED",
            "MR_SOURCE_INTENSITY_IS_NOT_HU",
        ]
        status = "PASS" if voxel_count else "FAIL"
        if voxel_count == 0:
            flags.append("EMPTY_SEGMENTATION")
        if connected_components > 1:
            status = "REVIEW" if status != "FAIL" else status
            flags.append(f"Post-processed segmentation still contains {connected_components} connected components.")
        if largest_component_fraction is not None and largest_component_fraction < 95.0:
            status = "REVIEW" if status != "FAIL" else status
            flags.append("Largest connected component contains less than 95% of the foreground.")
        if touches_boundary:
            status = "REVIEW" if status != "FAIL" else status
            flags.append("Segmentation touches the source-volume boundary; review for truncation or leakage.")
        if mesh_volume_cm3 is not None and labelmap_volume_cm3 > 0:
            difference = abs(mesh_volume_cm3 - labelmap_volume_cm3) / labelmap_volume_cm3 * 100.0
            if difference > 5.0:
                status = "REVIEW" if status != "FAIL" else status
                flags.append(f"Mesh/labelmap volume difference is {difference:.1f}%.")
        else:
            difference = None

        return {
            "status": status,
            "measurement_method": "Native labelmap voxel volume with independent smoothed-mesh geometry cross-check",
            "voxel_volume_mm3": voxel_volume_mm3,
            "labelmap_volume_cm3": labelmap_volume_cm3,
            "equivalent_diameter_mm": equivalent_diameter_mm,
            "mask_fraction_pct": mask_fraction_pct,
            "connected_components": connected_components,
            "largest_component_fraction_pct": largest_component_fraction,
            "touches_volume_boundary": touches_boundary,
            "surface_area_cm2": surface_area_cm2,
            "mesh_volume_cm3": mesh_volume_cm3,
            "volume_difference_pct": difference,
            "centroid_mm": MultiModelInferenceEngine._centroid_mm(mask),
            "intensity_domain": "MR source intensity values (uncalibrated)",
            "hu_calibrated": False,
            "rescale_slope": None,
            "rescale_intercept": None,
            "flags": flags,
            **intensity_stats,
        }

    @staticmethod
    def _label_metrics(
        mask: sitk.Image,
        labels: dict[int, str],
    ) -> list[dict[str, Any]]:
        array = sitk.GetArrayFromImage(
            mask
        )

        voxel_volume_cm3 = (
            float(
                np.prod(
                    mask.GetSpacing()
                )
            )
            / 1000.0
        )

        total_voxels = int(
            array.size
        )

        metrics: list[dict[str, Any]] = []

        for label_id, label_name in labels.items():
            if label_id == 0:
                continue

            count = int(
                np.count_nonzero(
                    array == label_id
                )
            )

            volume_cm3 = (
                count
                * voxel_volume_cm3
            )

            fraction_pct = (
                100.0 * count / total_voxels
                if total_voxels
                else 0.0
            )

            metrics.append(
                {
                    "label": label_id,
                    "name": label_name,
                    "voxel_count": count,
                    "volume_cm3": round(
                        volume_cm3,
                        4,
                    ),
                    "fraction_pct": round(
                        fraction_pct,
                        4,
                    ),
                }
            )

        return metrics

    def _heart_predict(
        self,
        image: sitk.Image,
    ) -> sitk.Image:
        """
        Run Heart 2D slice-based inference on a 3D volume.

        SimpleITK array:
            [Z,Y,X]

        Heart adapter:
            [X,Y,Z]
        """

        array_zyx = (
            sitk.GetArrayFromImage(
                image
            )
            .astype(
                np.float32,
                copy=False,
            )
        )

        if array_zyx.ndim != 3:
            raise ValueError(
                "Heart MRI input must be a 3D volume."
            )

        array_xyz = np.transpose(
            array_zyx,
            (2, 1, 0),
        )

        prediction_xyz = (
            self.models["heart"].predict(
                array_xyz
            )
        )

        prediction_zyx = np.transpose(
            prediction_xyz,
            (2, 1, 0),
        )

        mask = sitk.GetImageFromArray(
            prediction_zyx.astype(
                np.uint8,
                copy=False,
            )
        )

        mask.CopyInformation(image)

        return mask

    def _prostate_predict(
        self,
        image: sitk.Image,
    ) -> sitk.Image:
        return self.models[
            "prostate"
        ].predict_sitk(
            image
        )

    def segment(
        self,
        target: str,
        input_paths: list[Path],
        extraction_root: Path,
        case_directory: Path,
    ) -> tuple[
        dict[str, Any],
        sitk.Image,
        sitk.Image,
    ]:
        target = target.strip().lower()

        if target not in self.models:
            raise ValueError(
                f"Unsupported MRI model target: "
                f"{target}"
            )

        start = perf_counter()

        loaded = self._load_input(
            input_paths,
            extraction_root,
            target,
        )

        image = loaded.image

        original_spacing = [
            float(v)
            for v in image.GetSpacing()
        ]

        original_dimensions = [
            int(v)
            for v in image.GetSize()
        ]

        # Keep model execution serialized per model.
        with self.locks[target]:
            if target == "heart":
                mask = self._heart_predict(
                    image
                )
            else:
                mask = self._prostate_predict(
                    image
                )

                # Post-process independently per anatomical label. The raw model
        # prediction is preserved only in provenance/QA; quantitative output
        # uses the cleaned labelmap to prevent fragmented islands dominating
        # meshes and measurements.
        raw_mask = mask
        mask, component_cleanup = _largest_component_per_label(mask)

        label_meshes: dict[str, Any] = {}
        label_mesh_steps: list[int] = []

        for label_value, label_name in TARGETS[target]["labels"].items():
            if label_value == 0:
                continue

            label_mask = sitk.Cast(
                mask == int(label_value),
                sitk.sitkUInt8,
            )

            try:
                label_mesh_data, label_step = create_mesh(label_mask)
                label_mesh_data = _smooth_mesh(label_mesh_data)

                label_meshes[str(label_value)] = {
                    "label": int(label_value),
                    "name": label_name,
                    "vertices": label_mesh_data.vertices,
                    "faces": label_mesh_data.faces,
                    "vertex_count": label_mesh_data.vertex_count,
                    "face_count": label_mesh_data.face_count,
                    "mesh_step_size": label_step,
                }

                label_mesh_steps.append(label_step)

            except Exception:
                # Keep the anatomical label in the response even when
                # surface extraction fails. The original segmentation
                # remains available for quantitative analysis.
                label_meshes[str(label_value)] = {
                    "label": int(label_value),
                    "name": label_name,
                    "vertices": [],
                    "faces": [],
                    "vertex_count": 0,
                    "face_count": 0,
                    "mesh_step_size": 0,
                }

        # Preserve the combined foreground mesh for backwards compatibility.
        foreground = sitk.Cast(
            mask > 0,
            sitk.sitkUInt8,
        )

        mesh_data = MeshData([], [], 0, 0)
        try:
            mesh_data, actual_step = create_mesh(foreground)
            mesh_data = _smooth_mesh(mesh_data)

            mesh = {
                "vertices": mesh_data.vertices,
                "faces": mesh_data.faces,
                "vertex_count": mesh_data.vertex_count,
                "face_count": mesh_data.face_count,
            }

            mesh_volume_cm3 = None

        except Exception:
            mesh = self._empty_mesh()
            actual_step = max(
                label_mesh_steps,
                default=0,
            )
            mesh_volume_cm3 = None

        label_metrics = (
            self._label_metrics(
                mask,
                TARGETS[target]["labels"],
            )
        )

        # Per-label connected-component QA. This is review metadata only;
        # it does not modify the original segmentation mask.
        label_component_qa: dict[str, Any] = {}

        mask_array = sitk.GetArrayFromImage(mask)

        for label_value, label_name in TARGETS[target]["labels"].items():
            if label_value == 0:
                continue

            label_array = (
                mask_array == int(label_value)
            )

            voxel_count_for_label = int(
                np.count_nonzero(label_array)
            )

            if voxel_count_for_label == 0:
                label_component_qa[str(label_value)] = {
                    "label": int(label_value),
                    "name": label_name,
                    "connected_components": 0,
                    "largest_component_fraction_pct": None,
                }
                continue

            binary = sitk.GetImageFromArray(
                label_array.astype(np.uint8)
            )
            binary.CopyInformation(mask)

            connected = sitk.ConnectedComponent(
                binary
            )

            statistics = (
                sitk.LabelShapeStatisticsImageFilter()
            )
            statistics.Execute(connected)

            component_sizes = [
                statistics.GetNumberOfPixels(component)
                for component in statistics.GetLabels()
            ]

            largest_fraction = (
                100.0
                * max(component_sizes)
                / voxel_count_for_label
                if component_sizes
                else None
            )

            label_component_qa[str(label_value)] = {
                "label": int(label_value),
                "name": label_name,
                "connected_components": len(component_sizes),
                "largest_component_fraction_pct": (
                    round(
                        largest_fraction,
                        3,
                    )
                    if largest_fraction is not None
                    else None
                ),
            }

        mask_array = sitk.GetArrayFromImage(
            mask
        )

        voxel_count = int(
            np.count_nonzero(
                mask_array > 0
            )
        )

        volume_cm3 = (
            voxel_count
            * float(
                np.prod(
                    image.GetSpacing()
                )
            )
            / 1000.0
        )

        metric_mesh = mesh_data if "mesh_data" in locals() else MeshData([], [], 0, 0)
        surface_area_cm2, mesh_volume_cm3 = _mesh_geometry_metrics(metric_mesh)
        intensity_stats = _source_intensity_statistics(image, mask)
        quality = self._measurement_quality(
            image,
            mask,
            surface_area_cm2,
            mesh_volume_cm3,
            intensity_stats,
        )
        quality["component_cleanup"] = component_cleanup
        advanced_metrics = advanced_shape_metrics(
            mask,
            surface_area_cm2=surface_area_cm2,
            mesh_volume_cm3=mesh_volume_cm3,
        )

        model = self.models[target]

        # The two official bundle configurations provide different
        # validation metadata, so keep those distinctions explicit.
        if target == "heart":
            validation_per_class: dict[
                str, float
            ] = {}

            validation_dice = None

            warnings = [
                (
                    "Heart model is intended "
                    "for research purposes only."
                ),
                (
                    "No patient-specific accuracy "
                    "is established by this result."
                ),
                (
                    "The bundle metadata does not "
                    "provide a single validation "
                    "Dice value."
                ),
            ]

            raw_provenance = model.provenance()

            provenance = {
                "name": (
                    "MONAI Ventricular Short Axis "
                    "3-Label Segmentation"
                ),
                "architecture": raw_provenance.get(
                    "architecture",
                    "MONAI UNet 2D",
                ),
                "dataset": (
                    "Cardiac MRI short-axis research model"
                ),
                "checkpoint_loaded": bool(
                    raw_provenance.get("checkpoint_sha256")
                ),
                "checkpoint_sha256": raw_provenance.get(
                    "checkpoint_sha256"
                ),
                "preprocessing": {
                    "orientation": (
                        "Native cardiac MRI slice orientation retained"
                    ),
                    "spacing_mm": original_spacing,
                    "input_shape": raw_provenance.get(
                        "input_shape",
                        [256, 256],
                    ),
                    "roi_size": raw_provenance.get(
                        "roi_size",
                        [256, 256],
                    ),
                    "normalization": (
                        "MONAI ScaleIntensity"
                    ),
                    "inferer": raw_provenance.get(
                        "inferer",
                        "SliceInferer",
                    ),
                    "device": raw_provenance.get(
                        "device",
                        "cpu",
                    ),
                },
                "labels": {
                    str(k): v
                    for k, v in TARGETS[target]["labels"].items()
                },
            }
        else:
            validation_per_class = {
                "central gland": 0.88,
                "peripheral zone": 0.75,
            }

            # These are bundle-level reference metrics,
            # not patient-specific accuracy.
            validation_dice = None

            warnings = [
                (
                    "Prostate model is an example "
                    "research model and is not for "
                    "diagnostic use."
                ),
                (
                    "Reported Dice values are "
                    "bundle-level validation metrics, "
                    "not patient-specific accuracy."
                ),
            ]
            raw_provenance = model.provenance()

            provenance = {
                "name": "MONAI Prostate MRI Anatomy",
                "architecture": raw_provenance.get(
                    "architecture",
                    "MONAI UNet 3D",
                ),
                "dataset": "Prostate158",
                "checkpoint_loaded": bool(
                    raw_provenance.get("checkpoint_sha256")
                ),
                "checkpoint_sha256": raw_provenance.get(
                    "checkpoint_sha256"
                ),
                "preprocessing": {
                    "orientation": "RAS",
                    "spacing_mm": raw_provenance.get(
                        "target_spacing_mm",
                        [0.5, 0.5, 0.5],
                    ),
                    "input_shape": [96, 96, 96],
                    "roi_size": raw_provenance.get(
                        "roi_size",
                        [96, 96, 96],
                    ),
                    "normalization": (
                        "ScaleIntensity to [0, 1] "
                        "followed by NormalizeIntensity"
                    ),
                    "inferer": raw_provenance.get(
                        "inferer",
                        "SlidingWindowInferer",
                    ),
                    "sw_batch_size": raw_provenance.get(
                        "sw_batch_size",
                        1,
                    ),
                    "overlap": raw_provenance.get(
                        "overlap",
                        0.5,
                    ),
                    "device": raw_provenance.get(
                        "device",
                        "cpu",
                    ),
                },
                "labels": {
                    str(k): v
                    for k, v in TARGETS[target]["labels"].items()
                },
            }

        elapsed = (
            perf_counter() - start
        )

        case_id = (
            case_directory.name
        )

        preview_path = (
            case_directory
            / "preview.nii"
        )

        mask_path = (
            case_directory
            / "segmentation_mask.nii.gz"
        )

        # Preserve the source image in a sanitized NIfTI
        # for the workstation viewer.
        write_sanitized_nifti(
            image,
            preview_path,
        )

        write_sanitized_mask(
            mask,
            mask_path,
        )

        payload = {
            "request_id": case_id,
            "target": target,
            "source_type": (
                loaded.source_type
            ),
            "modality": (
                loaded.modality
            ),
            "is_demo": False,

            "volume_cm3": round(
                volume_cm3,
                4,
            ),

            "voxel_count": voxel_count,

            # MRI does not have HU semantics.
            "hu_statistics": intensity_stats,

            "validation_benchmark": {
                "validation_dice": (
                    validation_dice
                ),
                "target_threshold": 0.0,
                "per_class": (
                    validation_per_class
                ),
            },

            "measurement_quality": quality,

            "advanced_metrics": advanced_metrics,

            "input_notes": loaded.input_notes or [],

            "model_provenance": (
                provenance
            ),

            "label_metrics": label_metrics,

            # Separate anatomical surfaces for multi-label visualization.
            # The original combined mesh remains available for compatibility.
            "label_meshes": label_meshes,

            # Per-label connected-component QA. This describes the
            # segmentation without changing the original mask.
            "label_component_qa": {
                **label_component_qa,
                "cleanup": component_cleanup,
            },

            "mesh": mesh,

            "original_spacing_mm": (
                original_spacing
            ),

            "original_dimensions": (
                original_dimensions
            ),

            "processing_seconds": round(
                elapsed,
                3,
            ),

            "mesh_step_size": (
                actual_step
            ),

            "preview": {
                "volume_url": (
                    f"/api/v1/cases/"
                    f"{case_id}/volume"
                ),
                "mask_url": (
                    f"/api/v1/cases/"
                    f"{case_id}/mask"
                ),
            },

            "warnings": warnings,
        }

        return (
            payload,
            image,
            mask,
        )
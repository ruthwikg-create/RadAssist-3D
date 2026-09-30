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
        load_medical_volume,
        write_sanitized_mask,
        write_sanitized_nifti,
    )
    from .prostate_model_adapter import ProstateMRIAdapter
except ImportError:
    from heart_model_adapter import CardiacVentricularAdapter
    from pipeline import (
        create_mesh,
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
        mesh_volume_cm3: float | None,
    ) -> dict[str, Any]:
        """
        Build generic MRI labelmap quality information.

        MRI intensity is not treated as Hounsfield Units.
        """

        # Keep argument explicitly referenced so the function contract
        # remains clear and stable.
        _ = image

        mask_array = sitk.GetArrayFromImage(mask)
        foreground = mask_array > 0

        voxel_count = int(
            np.count_nonzero(foreground)
        )

        voxel_volume_mm3 = float(
            np.prod(mask.GetSpacing())
        )

        labelmap_volume_cm3 = (
            voxel_count
            * voxel_volume_mm3
            / 1000.0
        )

        total_voxels = int(
            mask_array.size
        )

        mask_fraction_pct = (
            100.0 * voxel_count / total_voxels
            if total_voxels
            else 0.0
        )

        touches_boundary = False

        if foreground.any():
            touches_boundary = bool(
                foreground[0, :, :].any()
                or foreground[-1, :, :].any()
                or foreground[:, 0, :].any()
                or foreground[:, -1, :].any()
                or foreground[:, :, 0].any()
                or foreground[:, :, -1].any()
            )

        connected_components = 0
        largest_component_fraction = None

        if foreground.any():
            binary = sitk.GetImageFromArray(
                foreground.astype(np.uint8)
            )

            binary.CopyInformation(mask)

            cc = sitk.ConnectedComponent(
                binary
            )

            stats = (
                sitk.LabelShapeStatisticsImageFilter()
            )

            stats.Execute(cc)

            component_sizes = [
                stats.GetNumberOfPixels(label)
                for label in stats.GetLabels()
            ]

            connected_components = len(
                component_sizes
            )

            if (
                component_sizes
                and voxel_count > 0
            ):
                largest_component_fraction = (
                    100.0
                    * max(component_sizes)
                    / voxel_count
                )

        flags = [
            "PATIENT_SPECIFIC_ACCURACY_NOT_ESTIMATED",
            "MR_SOURCE_INTENSITY_IS_NOT_HU",
        ]

        if voxel_count == 0:
            status = "FAIL"
            flags.append(
                "EMPTY_SEGMENTATION"
            )
        else:
            status = "REVIEW"

        return {
            "status": status,
            "measurement_method": (
                "Voxel-count labelmap volume"
            ),
            "voxel_volume_mm3": (
                voxel_volume_mm3
            ),
            "labelmap_volume_cm3": (
                labelmap_volume_cm3
            ),
            "equivalent_diameter_mm": None,
            "mask_fraction_pct": (
                mask_fraction_pct
            ),
            "connected_components": (
                connected_components
            ),
            "largest_component_fraction_pct": (
                largest_component_fraction
            ),
            "touches_volume_boundary": (
                touches_boundary
            ),
            "surface_area_cm2": None,
            "mesh_volume_cm3": (
                mesh_volume_cm3
            ),
            "volume_difference_pct": None,
            "centroid_mm": (
                MultiModelInferenceEngine
                ._centroid_mm(mask)
            ),
            "intensity_domain": (
                "MR source intensity values"
            ),
            "hu_calibrated": False,
            "rescale_slope": None,
            "rescale_intercept": None,
            "flags": flags,
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

                # Keep the original multiclass mask intact for all quantitative
        # measurements. Build separate visualization meshes for each
        # anatomical label so multi-label models remain distinguishable.
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
                label_mesh_data, label_step = create_mesh(
                    label_mask
                )

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

        try:
            mesh_data, actual_step = create_mesh(
                foreground
            )

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

        quality = (
            self._measurement_quality(
                image,
                mask,
                mesh_volume_cm3,
            )
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
            "hu_statistics": {
                "mean_hu": None,
                "std_hu": None,
                "min_hu": None,
                "max_hu": None,
                "median_hu": None,
                "p05_hu": None,
                "p95_hu": None,
            },

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

            "model_provenance": (
                provenance
            ),

            "label_metrics": label_metrics,

            # Separate anatomical surfaces for multi-label visualization.
            # The original combined mesh remains available for compatibility.
            "label_meshes": label_meshes,

            # Per-label connected-component QA. This describes the
            # segmentation without changing the original mask.
            "label_component_qa": label_component_qa,

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
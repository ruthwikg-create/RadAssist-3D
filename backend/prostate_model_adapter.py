from __future__ import annotations

import hashlib
import os
from pathlib import Path

import numpy as np
import SimpleITK as sitk
import torch
from monai.inferers import SlidingWindowInferer
from monai.networks.nets import UNet


DEFAULT_MODEL_PATH = (
    Path(__file__).resolve().parent
    / "models"
    / "prostate_mri"
    / "model.pt"
)

MODEL_ENV = "RADASSIST_PROSTATE_MODEL_PATH"

PROSTATE_LABELS = {
    0: "background",
    1: "central gland",
    2: "peripheral zone",
}

TARGET_SPACING_MM = (0.5, 0.5, 0.5)
ROI_SIZE = (96, 96, 96)
OVERLAP = 0.5


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


class ProstateMRIAdapter:
    """
    Research-use adapter for the MONAI Prostate MRI Anatomy bundle.

    Output labels:
        0 background
        1 central gland
        2 peripheral zone
    """

    ARCHITECTURE = "MONAI UNet 3D"
    TASK = "Prostate MRI Zonal Segmentation"
    MODALITY = "MR"

    def __init__(self, checkpoint_path: str | Path | None = None) -> None:
        configured = os.getenv(MODEL_ENV)

        self.checkpoint_path = Path(
            configured
            or checkpoint_path
            or DEFAULT_MODEL_PATH
        ).expanduser().resolve()

        if not self.checkpoint_path.exists():
            raise FileNotFoundError(
                f"Prostate checkpoint not found: {self.checkpoint_path}"
            )

        self.device = torch.device(
            "cuda:0" if torch.cuda.is_available() else "cpu"
        )

        self.model = UNet(
            spatial_dims=3,
            in_channels=1,
            out_channels=3,
            channels=(16, 32, 64, 128, 256, 512),
            strides=(2, 2, 2, 2, 2),
            num_res_units=4,
            norm="batch",
            act="prelu",
            dropout=0.15,
        )

        state = torch.load(
            self.checkpoint_path,
            map_location="cpu",
            weights_only=True,
        )

        self.model.load_state_dict(state, strict=True)
        self.model.to(self.device)
        self.model.eval()

        self.sw_batch_size = (
            1 if self.device.type == "cpu" else 4
        )

        self.inferer = SlidingWindowInferer(
            roi_size=ROI_SIZE,
            sw_batch_size=self.sw_batch_size,
            overlap=OVERLAP,
        )

        self.checkpoint_sha256 = sha256_file(
            self.checkpoint_path
        )

    @staticmethod
    def _resample_to_spacing(
        image: sitk.Image,
        spacing: tuple[float, float, float],
        interpolation: int,
    ) -> sitk.Image:
        original_spacing = image.GetSpacing()
        original_size = image.GetSize()

        new_size = [
            max(
                1,
                int(
                    round(
                        original_size[i]
                        * original_spacing[i]
                        / spacing[i]
                    )
                ),
            )
            for i in range(3)
        ]

        return sitk.Resample(
            image,
            new_size,
            sitk.Transform(),
            interpolation,
            image.GetOrigin(),
            spacing,
            image.GetDirection(),
            0.0,
            image.GetPixelID(),
        )

    @staticmethod
    def _normalize(array: np.ndarray) -> np.ndarray:
        """
        Match the bundle's:
            ScaleIntensityd(minv=0,maxv=1)
            NormalizeIntensityd()
        """
        array = np.asarray(array, dtype=np.float32)

        finite = np.isfinite(array)

        if not finite.any():
            return np.zeros_like(array, dtype=np.float32)

        values = array[finite]

        low = float(values.min())
        high = float(values.max())

        if high <= low:
            scaled = np.zeros_like(
                array,
                dtype=np.float32,
            )
        else:
            scaled = (array - low) / (high - low)

        scaled[~finite] = 0.0

        mean = float(scaled.mean())
        std = float(scaled.std())

        if std <= 1e-8:
            return np.zeros_like(
                scaled,
                dtype=np.float32,
            )

        normalized = (scaled - mean) / std

        return normalized.astype(
            np.float32,
            copy=False,
        )

    @staticmethod
    def _keep_largest_components(
        mask: sitk.Image,
    ) -> sitk.Image:
        """
        Keep the largest connected component for labels 1 and 2,
        matching the bundle's KeepLargestConnectedComponentd behavior.
        """
        result_array = sitk.GetArrayFromImage(mask).astype(
            np.uint8,
            copy=False,
        )

        output = np.zeros_like(
            result_array,
            dtype=np.uint8,
        )

        for label in (1, 2):
            binary_array = (
                result_array == label
            ).astype(np.uint8)

            if binary_array.max() == 0:
                continue

            binary = sitk.GetImageFromArray(binary_array)
            binary.CopyInformation(mask)

            cc = sitk.ConnectedComponent(binary)

            stats = sitk.LabelShapeStatisticsImageFilter()
            stats.Execute(cc)

            labels = list(stats.GetLabels())

            if not labels:
                continue

            largest = max(
                labels,
                key=stats.GetNumberOfPixels,
            )

            largest_mask = (
                sitk.GetArrayFromImage(cc)
                == largest
            )

            output[largest_mask] = label

        result = sitk.GetImageFromArray(output)
        result.CopyInformation(mask)

        return result

    @torch.inference_mode()
    def predict_sitk(
        self,
        original_image: sitk.Image,
    ) -> sitk.Image:
        """
        Run the full prostate-specific preprocessing and inference
        and return a mask in the original image geometry.
        """
        if original_image.GetDimension() != 3:
            raise ValueError(
                "Prostate MRI inference requires a 3D image."
            )

        # Bundle preprocessing:
        # Orientationd(..., RAS)
        # Spacingd(..., 0.5mm)
        ras_image = sitk.DICOMOrient(
            original_image,
            "RAS",
        )

        resampled = self._resample_to_spacing(
            ras_image,
            TARGET_SPACING_MM,
            sitk.sitkLinear,
        )

        array_zyx = sitk.GetArrayFromImage(
            resampled
        ).astype(
            np.float32,
            copy=False,
        )

        normalized = self._normalize(
            array_zyx
        )

        # SimpleITK array is [Z,Y,X].
        # MONAI tensor needs [B,C,X,Y,Z].
        array_xyz = np.transpose(
            normalized,
            (2, 1, 0),
        )

        tensor = torch.from_numpy(
            np.ascontiguousarray(array_xyz)
        )

        tensor = (
            tensor
            .unsqueeze(0)
            .unsqueeze(0)
            .to(self.device)
        )

        logits = self.inferer(
            inputs=tensor,
            network=self.model,
        )

        prediction = torch.argmax(
            logits,
            dim=1,
        )[0].to(
            torch.uint8
        ).cpu().numpy()

        # Return to SimpleITK [Z,Y,X].
        prediction_zyx = np.transpose(
            prediction,
            (2, 1, 0),
        )

        predicted_ras = sitk.GetImageFromArray(
            prediction_zyx
        )

        predicted_ras.CopyInformation(
            resampled
        )

        predicted_ras = self._keep_largest_components(
            predicted_ras
        )

        # Return to the exact original CT/MRI geometry.
        restored = sitk.Resample(
            predicted_ras,
            original_image,
            sitk.Transform(),
            sitk.sitkNearestNeighbor,
            0,
            sitk.sitkUInt8,
        )

        return restored

    def predict(
        self,
        volume_xyz: np.ndarray,
    ) -> np.ndarray:
        """
        Convenience API for already-preprocessed XYZ data.

        This path assumes the caller has already performed
        the bundle-specific orientation and spacing operations.
        """
        array = np.asarray(
            volume_xyz,
            dtype=np.float32,
        )

        if array.ndim != 3:
            raise ValueError(
                f"Prostate input must be 3D, got {array.shape}"
            )

        normalized = self._normalize(array)

        tensor = torch.from_numpy(
            np.ascontiguousarray(normalized)
        ).unsqueeze(0).unsqueeze(0)

        tensor = tensor.to(self.device)

        logits = self.inferer(
            inputs=tensor,
            network=self.model,
        )

        prediction = torch.argmax(
            logits,
            dim=1,
        )[0].cpu().numpy().astype(
            np.uint8,
            copy=False,
        )

        return prediction

    def provenance(self) -> dict:
        return {
            "model": self.TASK,
            "architecture": self.ARCHITECTURE,
            "modality": self.MODALITY,
            "checkpoint": str(self.checkpoint_path),
            "checkpoint_sha256": self.checkpoint_sha256,
            "device": str(self.device),
            "target_spacing_mm": list(
                TARGET_SPACING_MM
            ),
            "roi_size": list(ROI_SIZE),
            "sw_batch_size": self.sw_batch_size,
            "overlap": OVERLAP,
            "labels": dict(PROSTATE_LABELS),
            "clinical_use": False,
            "intended_use": (
                "Example research model; "
                "not for diagnostic purposes"
            ),
        }
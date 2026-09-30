from __future__ import annotations

import hashlib
import os
from pathlib import Path

import numpy as np
import torch
from monai.inferers import SliceInferer
from monai.networks.nets import UNet


DEFAULT_MODEL_PATH = (
    Path(__file__).resolve().parent
    / "models"
    / "heart_ventricular"
    / "model.pt"
)

MODEL_ENV = "RADASSIST_HEART_MODEL_PATH"

HEART_LABELS = {
    0: "lv_pool",
    1: "myocardium",
    2: "rv_pool",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


class CardiacVentricularAdapter:
    """
    Research-use adapter for the MONAI
    Ventricular Short Axis 3-Label Segmentation bundle.

    Bundle inference configuration:
        - 2D MONAI UNet
        - 1 input channel
        - 4 output classes
        - ScaleIntensity preprocessing
        - SliceInferer
        - roi_size=(256, 256)
        - spatial_dim=2
        - argmax postprocessing

    Expected modality:
        Cardiac MR

    Expected geometry:
        2D short-axis slices stacked along Z.

    Output labels:
        0 background
        1 LV blood pool
        2 myocardium
        3 RV blood pool
    """

    ARCHITECTURE = "MONAI UNet 2D"
    TASK = "Cardiac MRI Ventricular Segmentation"
    MODALITY = "MR"

    INPUT_SPATIAL_SHAPE = (256, 256)

    OUTPUT_LABELS = {
        0: "background",
        1: "lv_pool",
        2: "myocardium",
        3: "rv_pool",
    }

    def __init__(self, checkpoint_path: str | Path | None = None) -> None:
        configured = os.getenv(MODEL_ENV)

        self.checkpoint_path = Path(
            configured
            or checkpoint_path
            or DEFAULT_MODEL_PATH
        ).expanduser().resolve()

        if not self.checkpoint_path.exists():
            raise FileNotFoundError(
                f"Heart checkpoint not found: {self.checkpoint_path}"
            )

        self.device = torch.device(
            "cuda:0" if torch.cuda.is_available() else "cpu"
        )

        self.model = UNet(
            spatial_dims=2,
            in_channels=1,
            out_channels=4,
            channels=(16, 32, 64, 128, 256),
            strides=(2, 2, 2, 2),
            num_res_units=2,
        )

        state = torch.load(
            self.checkpoint_path,
            map_location="cpu",
            weights_only=True,
        )

        self.model.load_state_dict(state, strict=True)
        self.model.to(self.device)
        self.model.eval()

        self.inferer = SliceInferer(
            roi_size=(256, 256),
            spatial_dim=2,
        )

        self.checkpoint_sha256 = sha256_file(
            self.checkpoint_path
        )

    @staticmethod
    def _scale_intensity(array: np.ndarray) -> np.ndarray:
        """
        Match MONAI ScaleIntensityd with its default
        channel_wise=False behavior.

        The bundle scales the complete image using its
        minimum and maximum intensity values.

        No spatial resizing is performed.
        """
        array = np.asarray(array, dtype=np.float32)

        finite = np.isfinite(array)

        if not finite.any():
            return np.zeros_like(
                array,
                dtype=np.float32,
            )

        values = array[finite]

        low = float(values.min())
        high = float(values.max())

        if high <= low:
            return np.zeros_like(
                array,
                dtype=np.float32,
            )

        output = (array - low) / (high - low)

        output[~finite] = 0.0

        return np.clip(
            output,
            0.0,
            1.0,
        ).astype(
            np.float32,
            copy=False,
        )

    @torch.inference_mode()
    def predict(
        self,
        volume_xyz: np.ndarray,
    ) -> np.ndarray:
        """
        Predict a ventricular segmentation.

        Input:
            volume_xyz: [X, Y, Z]

        Output:
            uint8 label map [X, Y, Z]

        Important:
            The bundle does NOT resize the input volume to
            256x256. SliceInferer handles the 256x256
            inference ROI internally.
        """
        array = np.asarray(
            volume_xyz,
            dtype=np.float32,
        )

        if array.ndim == 2:
            array = array[:, :, None]

        if array.ndim != 3:
            raise ValueError(
                f"Heart input must be 2D or 3D, got shape {array.shape}"
            )

        original_shape = array.shape

        # Bundle preprocessing:
        # LoadImaged -> EnsureChannelFirstd -> ScaleIntensityd
        # -> EnsureTyped
        array = self._scale_intensity(array)

        tensor = torch.from_numpy(array).unsqueeze(0).unsqueeze(0)

        tensor = tensor.to(
            self.device,
            non_blocking=True,
        )

        # tensor shape:
        # [B, C, X, Y, Z]
        #
        # The original bundle uses:
        # SliceInferer(roi_size=[256,256], spatial_dim=2)
        #
        # Therefore we deliberately DO NOT resize X/Y here.
        logits = self.inferer(
            tensor,
            self.model,
        )

        # Bundle postprocessing:
        # Activationsd(softmax=True)
        # -> Invertd
        # -> AsDiscreted(argmax=True)
        #
        # For the final discrete segmentation, argmax(logits)
        # is equivalent to argmax(softmax(logits)).
        labels = torch.argmax(
            logits,
            dim=1,
        ).to(torch.uint8)

        result = labels[0].cpu().numpy()

        # SliceInferer should preserve the original spatial
        # dimensions. Keep this guard for robustness only.
        if result.shape != original_shape:
            raise RuntimeError(
                "Heart inference produced an unexpected spatial shape: "
                f"expected {original_shape}, got {result.shape}"
            )

        if volume_xyz.ndim == 2:
            return result[:, :, 0]

        return result

    def provenance(self) -> dict:
        return {
            "model": self.TASK,
            "architecture": self.ARCHITECTURE,
            "modality": self.MODALITY,
            "checkpoint": str(self.checkpoint_path),
            "checkpoint_sha256": self.checkpoint_sha256,
            "device": str(self.device),
            "input_shape": list(self.INPUT_SPATIAL_SHAPE),
            "inferer": "SliceInferer",
            "roi_size": [256, 256],
            "spatial_dim": 2,
            "preprocessing": [
                "LoadImaged",
                "EnsureChannelFirstd",
                "ScaleIntensityd",
                "EnsureTyped",
            ],
            "postprocessing": [
                "Activationsd(softmax=True)",
                "Invertd",
                "AsDiscreted(argmax=True)",
            ],
            "labels": dict(self.OUTPUT_LABELS),
            "clinical_use": False,
            "intended_use": "Research purposes only",
        }
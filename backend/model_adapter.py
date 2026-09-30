from __future__ import annotations

import hashlib
import os
from pathlib import Path

import numpy as np
import torch
from monai.inferers import SlidingWindowInferer
from monai.networks.nets import UNet


DEFAULT_MODEL_PATH = (
    Path(__file__).resolve().parent
    / "models"
    / "spleen_unet_model.pt"
)

MODEL_PATH = Path(
    os.environ.get(
        "RADASSIST_MODEL_PATH",
        str(DEFAULT_MODEL_PATH),
    )
)


class SpleenUNetAdapter:
    """RadAssist adapter for the verified MONAI 3D UNet."""

    ARCHITECTURE = "MONAI UNet 3D"
    TASK = "Spleen segmentation from CT"

    INPUT_CHANNELS = 1
    OUTPUT_CLASSES = 2

    ROI_SIZE = (96, 96, 96)

    CLASS_MAP = {
        0: "background",
        1: "spleen",
    }

    INTENSITY_A_MIN = -57.0
    INTENSITY_A_MAX = 164.0

    SPACING = (1.5, 1.5, 2.0)

    def __init__(
        self,
        checkpoint_path: Path = MODEL_PATH,
    ):
        self.checkpoint_path = Path(
            checkpoint_path
        )

        if not self.checkpoint_path.exists():
            raise FileNotFoundError(
                "Model checkpoint not found: "
                f"{self.checkpoint_path}"
            )

        self.device = torch.device(
            "cuda"
            if torch.cuda.is_available()
            else "cpu"
        )

        self.model = UNet(
            spatial_dims=3,
            in_channels=1,
            out_channels=2,
            channels=(
                16,
                32,
                64,
                128,
                256,
            ),
            strides=(2, 2, 2, 2),
            num_res_units=2,
            norm="batch",
        )

        checkpoint = torch.load(
            self.checkpoint_path,
            map_location="cpu",
            weights_only=True,
        )

        self.model.load_state_dict(
            checkpoint,
            strict=True,
        )

        self.model.to(self.device)
        self.model.eval()

        self.inferer = SlidingWindowInferer(
            roi_size=self.ROI_SIZE,
            sw_batch_size=(
                1
                if self.device.type == "cpu"
                else 4
            ),
            overlap=0.5,
        )

        self.checkpoint_sha256 = (
            self._sha256(
                self.checkpoint_path
            )
        )

    @staticmethod
    def _sha256(
        path: Path,
    ) -> str:
        digest = hashlib.sha256()

        with path.open("rb") as handle:
            for chunk in iter(
                lambda: handle.read(
                    1024 * 1024
                ),
                b"",
            ):
                digest.update(chunk)

        return digest.hexdigest()

    @classmethod
    def scale_ct_intensity(
        cls,
        volume: np.ndarray,
    ) -> np.ndarray:
        volume = np.asarray(
            volume,
            dtype=np.float32,
        )

        volume = np.clip(
            volume,
            cls.INTENSITY_A_MIN,
            cls.INTENSITY_A_MAX,
        )

        volume = (
            volume - cls.INTENSITY_A_MIN
        ) / (
            cls.INTENSITY_A_MAX
            - cls.INTENSITY_A_MIN
        )

        return volume.astype(
            np.float32,
            copy=False,
        )

    @torch.inference_mode()
    def predict_logits(
        self,
        volume: np.ndarray,
    ) -> np.ndarray:
        volume = np.asarray(
            volume,
            dtype=np.float32,
        )

        if volume.ndim != 3:
            raise ValueError(
                "Expected a 3D volume, "
                f"got shape {volume.shape}"
            )

        tensor = torch.from_numpy(
            np.ascontiguousarray(volume)
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

        return (
            logits[0]
            .detach()
            .cpu()
            .numpy()
            .astype(np.float32)
        )

    @torch.inference_mode()
    def predict(
        self,
        volume: np.ndarray,
        already_scaled: bool = True,
    ) -> np.ndarray:
        volume = np.asarray(
            volume,
            dtype=np.float32,
        )

        if volume.ndim != 3:
            raise ValueError(
                "Expected a 3D volume, "
                f"got shape {volume.shape}"
            )

        if not already_scaled:
            volume = (
                self.scale_ct_intensity(
                    volume
                )
            )

        logits = self.predict_logits(
            volume
        )

        mask = np.argmax(
            logits,
            axis=0,
        )

        return mask.astype(
            np.uint8,
            copy=False,
        )

    def metadata(self) -> dict:
        return {
            "name":
                "RadAssist Spleen CT Segmentation",
            "architecture":
                self.ARCHITECTURE,
            "task":
                self.TASK,
            "device":
                str(self.device),
            "checkpoint_loaded":
                True,
            "checkpoint_path":
                str(self.checkpoint_path),
            "checkpoint_sha256":
                self.checkpoint_sha256,
            "input_channels":
                self.INPUT_CHANNELS,
            "output_classes":
                self.OUTPUT_CLASSES,
            "roi_size":
                list(self.ROI_SIZE),
            "sw_batch_size":
                (
                    1
                    if self.device.type == "cpu"
                    else 4
                ),
            "overlap":
                0.5,
            "required_spacing_mm":
                list(self.SPACING),
            "required_orientation":
                "RAS",
            "intensity_range_hu":
                [
                    self.INTENSITY_A_MIN,
                    self.INTENSITY_A_MAX,
                ],
            "class_map":
                {
                    str(k): v
                    for k, v
                    in self.CLASS_MAP.items()
                },
            "clinical_use":
                False,
        }
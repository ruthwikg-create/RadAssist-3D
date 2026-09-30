from __future__ import annotations

import hashlib
import os
from typing import Any
from pathlib import Path

import numpy as np
import torch
from monai.inferers import SlidingWindowInferer
from monai.networks.nets import SegResNet, UNet


BACKEND_DIR = Path(__file__).resolve().parent
REPO_DIR = BACKEND_DIR.parent

DEFAULT_MODEL_PATH = (
    BACKEND_DIR
    / "models"
    / "spleen_unet_model.pt"
)

TRAINED_MODEL_PATHS = (
    BACKEND_DIR / "models" / "spleen_segresnet.pth",
    REPO_DIR / "checkpoints" / "spleen_segresnet.pth",
    REPO_DIR / "model_training" / "checkpoints" / "spleen_segresnet.pth",
)

_configured_model_path = os.environ.get("RADASSIST_MODEL_PATH")

# A stale container path in a copied .env file should not make a valid local
# checkpoint appear offline. An explicitly configured path wins only when it
# resolves to an existing file; otherwise known local candidates are searched.
_configured_candidate = (
    Path(_configured_model_path).expanduser()
    if _configured_model_path
    else None
)

MODEL_PATH = (
    _configured_candidate
    if _configured_candidate is not None and _configured_candidate.exists()
    else next(
        (
            candidate
            for candidate in (DEFAULT_MODEL_PATH, *TRAINED_MODEL_PATHS)
            if candidate.exists()
        ),
        _configured_candidate or TRAINED_MODEL_PATHS[0],
    )
)


class SpleenUNetAdapter:
    """Checkpoint-aware spleen adapter supporting legacy UNet and metadata-bearing SegResNet checkpoints."""

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

        checkpoint = torch.load(
            self.checkpoint_path,
            map_location="cpu",
            weights_only=True,
        )
        if not isinstance(checkpoint, dict):
            raise ValueError("Checkpoint must deserialize to a mapping.")

        self.checkpoint = checkpoint

        if isinstance(checkpoint, dict) and "state_dict" in checkpoint:
            config = checkpoint.get("config", {})
            self.architecture = str(config.get("architecture", "SegResNet"))
            if self.architecture.lower() != "segresnet":
                raise ValueError(f"Unsupported metadata-bearing spleen architecture: {self.architecture}")
            self.ROI_SIZE = tuple(int(v) for v in config.get("roi_size", self.ROI_SIZE))
            self.SPACING = tuple(float(v) for v in config.get("target_spacing_mm", self.SPACING))
            self.INTENSITY_A_MIN = float(config.get("hu_min", -175.0))
            self.INTENSITY_A_MAX = float(config.get("hu_max", 250.0))
            self.NORMALIZE_NONZERO = bool(config.get("normalize_nonzero", True))
            self.validation_dice = float(checkpoint["best_val_dice"]) if checkpoint.get("best_val_dice") is not None else None
            self.model = SegResNet(
                spatial_dims=3,
                init_filters=int(config.get("init_filters", 16)),
                in_channels=int(config.get("in_channels", 1)),
                out_channels=int(config.get("out_channels", 2)),
                dropout_prob=float(config.get("dropout_prob", 0.0)),
                blocks_down=tuple(config.get("blocks_down", [1, 2, 2, 4])),
                blocks_up=tuple(config.get("blocks_up", [1, 1, 1])),
            )
            state_dict = checkpoint["state_dict"]
        else:
            self.architecture = "MONAI UNet 3D"
            self.NORMALIZE_NONZERO = False
            self.validation_dice = None
            self.model = UNet(
                spatial_dims=3,
                in_channels=1,
                out_channels=2,
                channels=(16, 32, 64, 128, 256),
                strides=(2, 2, 2, 2),
                num_res_units=2,
                norm="batch",
            )
            state_dict = checkpoint

        if not isinstance(state_dict, dict):
            raise ValueError("Checkpoint does not contain a valid model state_dict.")
        self.model.load_state_dict(state_dict, strict=True)

        self.model.to(self.device)
        self.model.eval()

        self.sw_batch_size = 1 if self.device.type == "cpu" else 4
        self.sw_overlap = 0.25 if self.architecture.lower() == "segresnet" else 0.5
        inferer_kwargs = {
            "roi_size": self.ROI_SIZE,
            "sw_batch_size": self.sw_batch_size,
            "overlap": self.sw_overlap,
            "mode": "gaussian",
        }
        if self.device.type == "cuda":
            inferer_kwargs.update(sw_device=self.device, device=torch.device("cpu"))
        self.inferer = SlidingWindowInferer(**inferer_kwargs)

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

    def _prepare_intensity(
        self,
        volume: np.ndarray,
        already_scaled: bool,
    ) -> np.ndarray:
        volume = np.asarray(volume, dtype=np.float32)

        if not already_scaled:
            volume = self.scale_ct_intensity(volume)

        if not getattr(self, "NORMALIZE_NONZERO", False):
            return volume.astype(np.float32, copy=False)

        nonzero = volume[np.isfinite(volume) & (volume != 0)]
        if nonzero.size == 0:
            return np.zeros_like(volume, dtype=np.float32)

        mean = float(nonzero.mean())
        std = float(nonzero.std())
        output = volume - mean if std <= 1e-8 else (volume - mean) / std
        output = np.where(np.isfinite(output), output, 0.0)
        output = np.where(volume == 0, 0.0, output)
        return output.astype(np.float32, copy=False)

    @torch.inference_mode()
    def predict(
        self,
        volume: np.ndarray,
        already_scaled: bool = False,
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

        volume = self._prepare_intensity(
            volume,
            already_scaled=already_scaled,
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
                self.architecture,
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
                self.sw_overlap,
            "validation_dice":
                self.validation_dice,
            "normalize_nonzero":
                getattr(self, "NORMALIZE_NONZERO", False),
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
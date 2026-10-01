from __future__ import annotations

import hashlib
import os
from pathlib import Path

import numpy as np
import SimpleITK as sitk
import torch
from monai.inferers import SlidingWindowInferer
from monai.networks.nets import SegResNet


DEFAULT_MODEL_PATH = Path(__file__).resolve().parent / "models" / "brats_mri" / "model.pt"
MODEL_ENV = "RADASSIST_BRAIN_TUMOR_MODEL_PATH"


class BrainTumorBraTSAdapter:
    """Research adapter for the MONAI BraTS MRI segmentation bundle."""

    ARCHITECTURE = "MONAI SegResNet 3D"
    TASK = "Multimodal brain tumor subregion segmentation"
    MODALITY = "MR"

    OUTPUT_LABELS = {
        0: "background",
        1: "tumor core",
        2: "whole tumor",
        4: "enhancing tumor",
    }

    INPUT_CHANNELS = {
        0: "T1c",
        1: "T1",
        2: "T2",
        3: "FLAIR",
    }

    def __init__(self, checkpoint_path: str | Path | None = None) -> None:
        configured = os.getenv(MODEL_ENV)
        self.checkpoint_path = Path(
            configured or checkpoint_path or DEFAULT_MODEL_PATH
        ).expanduser().resolve()

        if not self.checkpoint_path.is_file():
            raise FileNotFoundError(
                f"Brain tumor checkpoint not found: {self.checkpoint_path}"
            )

        self.device = torch.device(
            "cuda:0" if torch.cuda.is_available() else "cpu"
        )

        self.model = SegResNet(
            spatial_dims=3,
            init_filters=16,
            in_channels=4,
            out_channels=3,
            dropout_prob=0.2,
            blocks_down=(1, 2, 2, 4),
            blocks_up=(1, 1, 1),
        )

        state = torch.load(
            self.checkpoint_path,
            map_location="cpu",
            weights_only=True,
        )
        if isinstance(state, dict) and "state_dict" in state:
            state = state["state_dict"]
        if not isinstance(state, dict):
            raise ValueError("BraTS checkpoint must contain a state_dict mapping.")

        self.model.load_state_dict(state, strict=True)
        self.model.to(self.device)
        self.model.eval()

        inferer_kwargs = {
            "roi_size": (240, 240, 160),
            "sw_batch_size": 1,
            "overlap": 0.5,
        }
        if self.device.type == "cuda":
            inferer_kwargs.update(
                sw_device=self.device,
                device=torch.device("cpu"),
            )
        self.inferer = SlidingWindowInferer(**inferer_kwargs)
        self.checkpoint_sha256 = self._sha256(self.checkpoint_path)

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _normalize_channel(array: np.ndarray) -> np.ndarray:
        array = np.asarray(array, dtype=np.float32)
        finite = np.isfinite(array)
        nonzero = array[finite & (array != 0)]
        if nonzero.size == 0:
            return np.zeros_like(array, dtype=np.float32)
        mean = float(nonzero.mean())
        std = float(nonzero.std())
        if std <= 1e-8:
            return np.where(np.isfinite(array), array - mean, 0.0).astype(np.float32)
        output = (array - mean) / std
        output[~np.isfinite(output)] = 0.0
        return output.astype(np.float32)

    @torch.inference_mode()
    def predict(self, channels: list[sitk.Image]) -> sitk.Image:
        if len(channels) != 4:
            raise ValueError(
                "BraTS brain-tumor inference requires exactly four aligned MRI volumes: "
                "T1c, T1, T2 and FLAIR."
            )

        reference = channels[0]
        if reference.GetDimension() != 3:
            raise ValueError("BraTS MRI inputs must be 3D volumes.")

        reference_size = reference.GetSize()
        reference_spacing = reference.GetSpacing()
        reference_direction = reference.GetDirection()
        reference_origin = reference.GetOrigin()

        arrays = []
        for index, image in enumerate(channels):
            if image.GetDimension() != 3:
                raise ValueError(f"BraTS channel {index} is not a 3D volume.")
            if image.GetSize() != reference_size:
                raise ValueError("All four BraTS MRI channels must have identical dimensions.")
            if not np.allclose(image.GetSpacing(), reference_spacing, atol=1e-5):
                raise ValueError("All four BraTS MRI channels must have identical spacing.")
            if not np.allclose(image.GetDirection(), reference_direction, atol=1e-5):
                raise ValueError("All four BraTS MRI channels must have identical direction.")
            if not np.allclose(image.GetOrigin(), reference_origin, atol=1e-5):
                raise ValueError("All four BraTS MRI channels must have identical origin.")
            arrays.append(
                self._normalize_channel(
                    sitk.GetArrayFromImage(image)
                )
            )

        # SimpleITK arrays are [Z,Y,X]; PyTorch 3D inference expects [B,C,Z,Y,X].
        tensor = torch.from_numpy(np.stack(arrays, axis=0)).unsqueeze(0)
        tensor = tensor.to(self.device, non_blocking=True)

        logits = self.inferer(tensor, self.model)
        probabilities = torch.sigmoid(logits[0]).detach().cpu().numpy()
        binary = probabilities >= 0.5

        # MONAI BraTS bundle output channels:
        # 0 = tumor core, 1 = whole tumor, 2 = enhancing tumor.
        # Bundle label mapping: ET -> 4, TC -> 1, WT -> 2.
        label_array = np.zeros(binary.shape[1:], dtype=np.uint8)
        label_array[binary[1]] = 2
        label_array[binary[0]] = 1
        label_array[binary[2]] = 4

        mask = sitk.GetImageFromArray(label_array)
        mask.CopyInformation(reference)

        if not np.any(label_array):
            raise RuntimeError("BraTS checkpoint produced an empty tumor mask.")

        return mask

    def provenance(self) -> dict:
        return {
            "name": "MONAI BraTS MRI segmentation",
            "architecture": self.ARCHITECTURE,
            "task": self.TASK,
            "modality": self.MODALITY,
            "checkpoint": str(self.checkpoint_path),
            "checkpoint_sha256": self.checkpoint_sha256,
            "device": str(self.device),
            "input_channels": dict(self.INPUT_CHANNELS),
            "roi_size": [240, 240, 160],
            "overlap": 0.5,
            "preprocessing": ["NormalizeIntensityd(nonzero=True, channel_wise=True)"],
            "output_labels": dict(self.OUTPUT_LABELS),
            "intended_use": "Research example; not for diagnostic use",
            "clinical_use": False,
        }

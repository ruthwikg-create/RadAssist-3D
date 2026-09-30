# ============================================================
# RadAssist 3D — MSD Task09 Spleen SegResNet Training
# Designed for Google Colab GPU runtime.
# ============================================================

from __future__ import annotations

# Colab/Linux dependency bootstrap. Disable AUTO_INSTALL_DEPS when the
# environment is already provisioned.
import os
import subprocess
import sys

if os.getenv("RADASSIST_AUTO_INSTALL_DEPS", "1") == "1":
    subprocess.check_call([
        sys.executable, "-m", "pip", "install", "-q",
        "monai==1.6.0",
        "nibabel==5.4.2",
        "SimpleITK==2.5.6",
        "scikit-image>=0.24,<1.0",
    ])

import hashlib
import json
import random
import shutil
import tarfile
import time
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import torch
import monai
from monai.data import CacheDataset, DataLoader, decollate_batch
from monai.inferers import SlidingWindowInferer
from monai.losses import DiceLoss
from monai.metrics import DiceMetric
from monai.networks.nets import SegResNet
from monai.transforms import (
    AsDiscrete,
    Compose,
    EnsureChannelFirstd,
    EnsureTyped,
    LoadImaged,
    NormalizeIntensityd,
    Orientationd,
    RandCropByPosNegLabeld,
    RandFlipd,
    RandRotate90d,
    ScaleIntensityRanged,
    Spacingd,
)
from monai.utils import set_determinism

SEED = 42
set_determinism(seed=SEED)
random.seed(SEED)
np.random.seed(SEED)
torch.manual_seed(SEED)
if torch.cuda.is_available():
    torch.cuda.manual_seed_all(SEED)

ROOT_DIR = Path("/content/radassist3d")
DATASET_ROOT = ROOT_DIR / "MSD"
DATASET_DIR = DATASET_ROOT / "Task09_Spleen"
CHECKPOINT_DIR = ROOT_DIR / "checkpoints"
CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
CHECKPOINT_PATH = CHECKPOINT_DIR / "spleen_segresnet.pth"

DATASET_URL = "https://msd-for-monai.s3-us-west-2.amazonaws.com/Task09_Spleen.tar"
DATASET_MD5 = "410d4a301da4e5b2f6f86ec3ddba524e"
TAR_PATH = DATASET_ROOT / "Task09_Spleen.tar"

HU_MIN = -175.0
HU_MAX = 250.0
TARGET_SPACING = (1.0, 1.0, 1.0)
ROI_SIZE = (96, 96, 96)
MAX_EPOCHS = 100
VAL_INTERVAL = 1
BATCH_SIZE = 1
NUM_SAMPLES = 2
LEARNING_RATE = 2e-4
WEIGHT_DECAY = 1e-5
SW_BATCH_SIZE = 1
SW_OVERLAP = 0.25
CACHE_RATE = 0.25
NUM_WORKERS = 2
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


def md5sum(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


DATASET_ROOT.mkdir(parents=True, exist_ok=True)
if not DATASET_DIR.exists():
    import urllib.request
    print("Downloading MSD Task09 Spleen…")
    urllib.request.urlretrieve(DATASET_URL, TAR_PATH)
    if md5sum(TAR_PATH) != DATASET_MD5:
        raise RuntimeError("Dataset checksum mismatch.")
    with tarfile.open(TAR_PATH, "r") as archive:
        archive.extractall(DATASET_ROOT)

images_dir = DATASET_DIR / "imagesTr"
labels_dir = DATASET_DIR / "labelsTr"
image_files = sorted(images_dir.glob("*.nii.gz"))

data_dicts = []
for image_path in image_files:
    label_path = labels_dir / image_path.name
    if not label_path.exists():
        raise RuntimeError(f"Missing label for {image_path.name}")
    data_dicts.append({"image": str(image_path), "label": str(label_path)})

rng = random.Random(SEED)
indices = list(range(len(data_dicts)))
rng.shuffle(indices)
val_count = max(1, round(len(indices) * 0.20))
val_idx = indices[:val_count]
train_idx = indices[val_count:]
train_files = [data_dicts[i] for i in train_idx]
val_files = [data_dicts[i] for i in val_idx]

train_transforms = Compose([
    LoadImaged(keys=["image", "label"]),
    EnsureChannelFirstd(keys=["image", "label"]),
    Orientationd(keys=["image", "label"], axcodes="RAS"),
    Spacingd(keys=["image", "label"], pixdim=TARGET_SPACING, mode=("bilinear", "nearest")),
    ScaleIntensityRanged(keys=["image"], a_min=HU_MIN, a_max=HU_MAX, b_min=0.0, b_max=1.0, clip=True),
    NormalizeIntensityd(keys=["image"], nonzero=True, channel_wise=True),
    RandCropByPosNegLabeld(keys=["image", "label"], label_key="label", spatial_size=ROI_SIZE, pos=1, neg=1, num_samples=NUM_SAMPLES),
    RandFlipd(keys=["image", "label"], prob=0.5, spatial_axis=0),
    RandFlipd(keys=["image", "label"], prob=0.5, spatial_axis=1),
    RandFlipd(keys=["image", "label"], prob=0.5, spatial_axis=2),
    RandRotate90d(keys=["image", "label"], prob=0.5, max_k=3, spatial_axes=(0, 1)),
    EnsureTyped(keys=["image", "label"]),
])

val_transforms = Compose([
    LoadImaged(keys=["image", "label"]),
    EnsureChannelFirstd(keys=["image", "label"]),
    Orientationd(keys=["image", "label"], axcodes="RAS"),
    Spacingd(keys=["image", "label"], pixdim=TARGET_SPACING, mode=("bilinear", "nearest")),
    ScaleIntensityRanged(keys=["image"], a_min=HU_MIN, a_max=HU_MAX, b_min=0.0, b_max=1.0, clip=True),
    NormalizeIntensityd(keys=["image"], nonzero=True, channel_wise=True),
    EnsureTyped(keys=["image", "label"]),
])

train_ds = CacheDataset(train_files, train_transforms, cache_rate=CACHE_RATE, num_workers=NUM_WORKERS)
val_ds = CacheDataset(val_files, val_transforms, cache_rate=CACHE_RATE, num_workers=NUM_WORKERS)
train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True, num_workers=NUM_WORKERS, pin_memory=torch.cuda.is_available())
val_loader = DataLoader(val_ds, batch_size=1, shuffle=False, num_workers=NUM_WORKERS, pin_memory=torch.cuda.is_available())

model = SegResNet(
    spatial_dims=3,
    init_filters=16,
    in_channels=1,
    out_channels=2,
    dropout_prob=0.0,
    blocks_down=(1, 2, 2, 4),
    blocks_up=(1, 1, 1),
).to(DEVICE)

loss_function = DiceLoss(include_background=False, to_onehot_y=True, softmax=True)
optimizer = torch.optim.AdamW(model.parameters(), lr=LEARNING_RATE, weight_decay=WEIGHT_DECAY)
dice_metric = DiceMetric(include_background=False, reduction="mean")
validation_inferer_kwargs = {
    "roi_size": ROI_SIZE,
    "sw_batch_size": SW_BATCH_SIZE,
    "overlap": SW_OVERLAP,
    "mode": "gaussian",
}
if DEVICE.type == "cuda":
    validation_inferer_kwargs.update(
        sw_device=DEVICE,
        device=torch.device("cpu"),
    )
validation_inferer = SlidingWindowInferer(**validation_inferer_kwargs)
use_amp = DEVICE.type == "cuda"
scaler = torch.amp.GradScaler("cuda", enabled=use_amp) if use_amp else None

best_val_dice = -1.0
best_epoch = -1
loss_history = []
dice_history = []
training_start = time.time()

for epoch in range(1, MAX_EPOCHS + 1):
    model.train()
    epoch_loss = 0.0
    steps = 0

    for batch in train_loader:
        inputs = batch["image"].to(DEVICE, non_blocking=True)
        labels = batch["label"].to(DEVICE, non_blocking=True)
        optimizer.zero_grad(set_to_none=True)

        if use_amp:
            with torch.amp.autocast(device_type="cuda", dtype=torch.float16):
                outputs = model(inputs)
                loss = loss_function(outputs, labels)
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
        else:
            outputs = model(inputs)
            loss = loss_function(outputs, labels)
            loss.backward()
            optimizer.step()

        epoch_loss += float(loss.item())
        steps += 1

    epoch_loss /= max(steps, 1)
    loss_history.append(epoch_loss)

    if epoch % VAL_INTERVAL == 0:
        model.eval()
        dice_metric.reset()

        with torch.no_grad():
            for val_data in val_loader:
                # Keep full validation volumes on CPU; only inference ROIs
                # are transferred to GPU and the stitched logits stay on CPU.
                val_inputs = val_data["image"]
                val_labels = val_data["label"]
                if use_amp:
                    with torch.amp.autocast(device_type="cuda", dtype=torch.float16):
                        val_outputs = validation_inferer(val_inputs, model)
                else:
                    val_outputs = validation_inferer(val_inputs, model)

                preds = decollate_batch(val_outputs)
                labs = decollate_batch(val_labels)
                preds = [AsDiscrete(argmax=True, to_onehot=2)(p) for p in preds]
                labs = [AsDiscrete(to_onehot=2)(l) for l in labs]
                dice_metric(y_pred=preds, y=labs)

        val_dice = float(dice_metric.aggregate().item())
        dice_metric.reset()
        dice_history.append(val_dice)

        print(f"Epoch {epoch:03d} | loss={epoch_loss:.5f} | val_dice={val_dice:.5f}")

        if val_dice > best_val_dice:
            best_val_dice = val_dice
            best_epoch = epoch
            checkpoint = {
                "state_dict": model.state_dict(),
                "best_val_dice": best_val_dice,
                "best_epoch": best_epoch,
                "config": {
                    "architecture": "SegResNet",
                    "spatial_dims": 3,
                    "init_filters": 16,
                    "in_channels": 1,
                    "out_channels": 2,
                    "dropout_prob": 0.0,
                    "blocks_down": [1, 2, 2, 4],
                    "blocks_up": [1, 1, 1],
                    "target_spacing_mm": list(TARGET_SPACING),
                    "roi_size": list(ROI_SIZE),
                    "hu_min": HU_MIN,
                    "hu_max": HU_MAX,
                    "task": "MSD Task09 Spleen",
                    "target": "spleen",
                    "modality": "CT",
                },
            }
            torch.save(checkpoint, CHECKPOINT_PATH)
            print(f"Saved best checkpoint -> {CHECKPOINT_PATH}")

print(f"Best validation Dice: {best_val_dice:.5f} at epoch {best_epoch}")
print(f"Training time (min): {(time.time() - training_start) / 60:.1f}")

model.load_state_dict(torch.load(CHECKPOINT_PATH, map_location=DEVICE, weights_only=True)["state_dict"])
model.eval()

metadata = {
    "project": "RadAssist 3D",
    "task": "MSD Task09 Spleen",
    "best_val_dice": float(best_val_dice),
    "best_epoch": int(best_epoch),
    "preprocessing": {
        "orientation": "RAS",
        "spacing_mm": list(TARGET_SPACING),
        "hu_min": HU_MIN,
        "hu_max": HU_MAX,
        "normalize_nonzero": True,
    },
}
with (CHECKPOINT_DIR / "spleen_segresnet_meta.json").open("w", encoding="utf-8") as handle:
    json.dump(metadata, handle, indent=2)

BACKEND_MODEL_DIR = ROOT_DIR / "backend_models"
BACKEND_MODEL_DIR.mkdir(parents=True, exist_ok=True)
shutil.copy2(CHECKPOINT_PATH, BACKEND_MODEL_DIR / "spleen_segresnet.pth")
shutil.copy2(CHECKPOINT_DIR / "spleen_segresnet_meta.json", BACKEND_MODEL_DIR / "spleen_segresnet_meta.json")

plt.figure(figsize=(8, 4))
plt.plot(loss_history, label="Training Dice Loss")
plt.xlabel("Epoch")
plt.ylabel("Loss")
plt.title("RadAssist 3D — Training curve")
plt.grid(True, alpha=0.2)
plt.legend()
plt.tight_layout()
plt.show()

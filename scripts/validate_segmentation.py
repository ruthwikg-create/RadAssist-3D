#!/usr/bin/env python3
"""Offline Dice/IoU validator for RadAssist segmentation masks."""
from __future__ import annotations
import argparse
from pathlib import Path
import numpy as np
import SimpleITK as sitk

def dice(a: np.ndarray, b: np.ndarray) -> float:
    a = a.astype(bool); b = b.astype(bool)
    denom = int(a.sum() + b.sum())
    return 1.0 if denom == 0 else 2.0 * int(np.logical_and(a, b).sum()) / denom

def iou(a: np.ndarray, b: np.ndarray) -> float:
    a = a.astype(bool); b = b.astype(bool)
    union = int(np.logical_or(a, b).sum())
    return 1.0 if union == 0 else int(np.logical_and(a, b).sum()) / union

def load_reference_like(path: Path, prediction: sitk.Image) -> sitk.Image:
    reference = sitk.ReadImage(str(path))
    same_geometry = (
        reference.GetSize() == prediction.GetSize()
        and reference.GetSpacing() == prediction.GetSpacing()
        and reference.GetOrigin() == prediction.GetOrigin()
        and reference.GetDirection() == prediction.GetDirection()
    )
    if not same_geometry:
        reference = sitk.Resample(
            reference, prediction, sitk.Transform(),
            sitk.sitkNearestNeighbor, 0, reference.GetPixelID()
        )
    return reference

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("prediction", type=Path)
    parser.add_argument("reference", type=Path)
    parser.add_argument("--labels", default="1", help="Comma-separated labels")
    args = parser.parse_args()
    prediction = sitk.ReadImage(str(args.prediction))
    reference = load_reference_like(args.reference, prediction)
    pred = sitk.GetArrayFromImage(prediction)
    ref = sitk.GetArrayFromImage(reference)
    labels = [int(x.strip()) for x in args.labels.split(",") if x.strip()]
    print(f"PREDICTION: {args.prediction}")
    print(f"REFERENCE:  {args.reference}")
    print(f"SIZE:       {prediction.GetSize()}")
    print(f"SPACING:    {prediction.GetSpacing()}")
    for label in labels:
        print(f"LABEL {label}: Dice={dice(pred == label, ref == label):.4f} IoU={iou(pred == label, ref == label):.4f}")
    pred_fg = np.isin(pred, labels); ref_fg = np.isin(ref, labels)
    print(f"FOREGROUND: Dice={dice(pred_fg, ref_fg):.4f} IoU={iou(pred_fg, ref_fg):.4f}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

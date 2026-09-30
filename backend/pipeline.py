

import hashlib
import logging
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

import numpy as np
import SimpleITK as sitk
import torch
try:
    from backend.model_adapter import SpleenUNetAdapter
except ModuleNotFoundError as exc:
    if exc.name != "backend":
        raise
    from model_adapter import SpleenUNetAdapter
from skimage.measure import marching_cubes


logger = logging.getLogger("radassist.pipeline")

MODEL_PATH = Path(
    os.getenv(
        "RADASSIST_MODEL_PATH",
        Path(__file__).resolve().parent / "models" / "spleen_unet_model.pt",
    )
)
TARGET_SPACING_MM = (1.5, 1.5, 2.0)
HU_MIN = -57.0
HU_MAX = 164.0
ROI_SIZE = (
    int(os.getenv("RADASSIST_ROI_X", "96")),
    int(os.getenv("RADASSIST_ROI_Y", "96")),
    int(os.getenv("RADASSIST_ROI_Z", "96")),
)
SW_BATCH_SIZE = int(os.getenv("RADASSIST_SW_BATCH_SIZE", "1"))
SW_OVERLAP = float(os.getenv("RADASSIST_SW_OVERLAP", "0.5"))
SW_CPU_STITCH = os.getenv("RADASSIST_SW_CPU_STITCH", "true").lower() == "true"
MESH_STEP_SIZE = int(os.getenv("RADASSIST_MESH_STEP_SIZE", "2"))
MESH_MAX_VERTICES = int(os.getenv("RADASSIST_MESH_MAX_VERTICES", "250000"))
MAX_UPLOAD_BYTES = int(os.getenv("RADASSIST_MAX_UPLOAD_BYTES", str(512 * 1024 * 1024)))
MAX_EXTRACTED_BYTES = int(os.getenv("RADASSIST_MAX_EXTRACTED_BYTES", str(2 * 1024 * 1024 * 1024)))
MAX_BROWSER_PREVIEW_DIM = int(os.getenv("RADASSIST_MAX_BROWSER_PREVIEW_DIM", "128"))
DEVICE_NAME = os.getenv("RADASSIST_DEVICE", "auto").lower()


def choose_device() -> torch.device:
    if DEVICE_NAME == "cpu":
        return torch.device("cpu")
    if DEVICE_NAME == "cuda":
        if not torch.cuda.is_available():
            raise RuntimeError("RADASSIST_DEVICE=cuda was requested, but CUDA is unavailable.")
        return torch.device("cuda")
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


DEVICE = choose_device()


@dataclass
class VolumeData:
    image: sitk.Image
    source_type: str
    modality: str
    intensity_domain: str = "Source intensity values"
    hu_calibrated: bool = False
    rescale_slope: float | None = None
    rescale_intercept: float | None = None
    input_notes: list[str] | None = None


@dataclass
class MeshData:
    vertices: list[list[float]]
    faces: list[list[int]]
    vertex_count: int
    face_count: int


@dataclass
class SegmentationResult:
    mesh: MeshData
    voxel_count: int
    volume_cm3: float
    mean_hu: float | None
    std_hu: float | None
    min_hu: float | None
    max_hu: float | None
    median_hu: float | None
    p05_hu: float | None
    p95_hu: float | None
    validation_dice: float | None
    validation_dice_threshold: float
    source_type: str
    modality: str
    original_spacing_mm: list[float]
    original_dimensions: list[int]
    processing_seconds: float
    mesh_step_size: int
    measurement_quality: dict[str, Any] | None = None
    model_provenance: dict[str, Any] | None = None
    advanced_metrics: dict[str, Any] | None = None
    input_notes: list[str] | None = None
    target: str = "spleen"
    is_demo: bool = False


class SpleenSegmentationModel:
    """Compatibility wrapper around the verified MONAI spleen UNet adapter.

    The rest of RadAssist continues to consume a SimpleITK segmentation image,
    so downstream metrics, mesh generation, storage, and API behavior remain
    unchanged.
    """

    ARCHITECTURE = "MONAI UNet 3D"
    TASK = "Spleen CT Segmentation"

    def __init__(self, checkpoint_path: Path):
        self.checkpoint_path = Path(checkpoint_path)

        if not self.checkpoint_path.exists():
            raise FileNotFoundError(
                f"Model checkpoint not found: {self.checkpoint_path}"
            )

        self.backend = SpleenUNetAdapter(self.checkpoint_path)

        self.checkpoint_sha256 = self.backend.checkpoint_sha256
        self.validation_dice = self.backend.validation_dice
        self.config: dict[str, Any] = self.backend.metadata()
        self.inference_lock = threading.Lock()

    @torch.inference_mode()
    def predict(self, volume: sitk.Image) -> sitk.Image:
        array = sitk.GetArrayFromImage(volume).astype(
            np.float32,
            copy=False,
        )

        if array.ndim != 3:
            raise ValueError(
                f"Expected a 3D CT volume, received shape {array.shape}"
            )

        # SimpleITK exposes NumPy arrays in [Z, Y, X] order.
        # The verified MONAI NIfTI workflow expects spatial order [X, Y, Z].
        # Convert before inference, then convert the predicted label map back
        # to SimpleITK order before restoring image geometry.
        model_array = np.transpose(array, (2, 1, 0))

        mask_model_array = self.backend.predict(model_array, already_scaled=False)

        if mask_model_array.ndim != 3:
            raise ValueError(
                f"Model returned an invalid mask shape: {mask_model_array.shape}"
            )

        mask_array = np.transpose(mask_model_array, (2, 1, 0))

        mask = sitk.GetImageFromArray(
            np.asarray(mask_array, dtype=np.uint8)
        )
        mask.CopyInformation(volume)
        return mask


def _normalize_modality(value: str | None) -> str:
    return value.strip().upper() if value else "UNKNOWN"


def _safe_extract_zip(zip_path: Path, destination: Path) -> None:
    import zipfile

    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    total = 0

    with zipfile.ZipFile(zip_path, "r") as archive:
        for member in archive.infolist():
            unix_mode = (member.external_attr >> 16) & 0o170000
            if unix_mode == 0o120000:
                raise ValueError("Symbolic links are not allowed in uploaded ZIP files.")

            total += member.file_size
            if total > MAX_EXTRACTED_BYTES:
                raise ValueError("The decompressed DICOM archive exceeds the configured size limit.")

            target = (root / member.filename).resolve()
            try:
                target.relative_to(root)
            except ValueError:
                raise ValueError("Unsafe ZIP path detected.") from None

            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue

            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member, "r") as src, target.open("wb") as dst:
                while True:
                    chunk = src.read(1024 * 1024)
                    if not chunk:
                        break
                    dst.write(chunk)


def _read_dicom_modality(path: Path) -> str:
    try:
        reader = sitk.ImageFileReader()
        reader.SetFileName(str(path))
        reader.LoadPrivateTagsOn()
        reader.ReadImageInformation()
        key = "0008|0060"
        if reader.HasMetaDataKey(key):
            return _normalize_modality(reader.GetMetaData(key))
    except Exception:
        pass
    return "UNKNOWN"


def _read_dicom_intensity_domain(path: Path, modality: str) -> tuple[str, bool, float | None, float | None]:
    if modality != "CT":
        return "DICOM source intensity values", False, None, None
    try:
        reader = sitk.ImageFileReader()
        reader.SetFileName(str(path))
        reader.LoadPrivateTagsOn()
        reader.ReadImageInformation()
        rescale_type = reader.GetMetaData("0028|1054").strip().upper() if reader.HasMetaDataKey("0028|1054") else ""
        slope = float(reader.GetMetaData("0028|1053")) if reader.HasMetaDataKey("0028|1053") else None
        intercept = float(reader.GetMetaData("0028|1052")) if reader.HasMetaDataKey("0028|1052") else None
        finite_transform = slope is not None and intercept is not None and np.isfinite(slope) and np.isfinite(intercept)
        if rescale_type == "HU" and finite_transform:
            return "HU (DICOM CT rescale transform; explicit HU type)", True, slope, intercept
        if finite_transform:
            return "DICOM CT rescaled values (HU type not explicit)", False, slope, intercept
    except Exception:
        pass
    return "DICOM CT intensity values (HU provenance not fully verified)", False, None, None


def _validate_dicom_series_integrity(files: list[str]) -> dict[str, Any]:
    """Check identity-critical DICOM tags across the selected series."""
    keys = {
        "0020|000d": "StudyInstanceUID",
        "0020|000e": "SeriesInstanceUID",
        "0020|0052": "FrameOfReferenceUID",
        "0008|0060": "Modality",
    }
    observed: dict[str, set[str]] = {name: set() for name in keys.values()}
    for filename in files:
        reader = sitk.ImageFileReader()
        reader.SetFileName(str(filename))
        reader.LoadPrivateTagsOn()
        reader.ReadImageInformation()
        for key, name in keys.items():
            if reader.HasMetaDataKey(key):
                observed[name].add(reader.GetMetaData(key).strip())
    errors = [name for name, values in observed.items() if len(values) > 1]
    if errors:
        raise ValueError(
            "DICOM metadata integrity check failed: inconsistent "
            + ", ".join(errors)
            + " across the selected series."
        )
    missing = [name for name, values in observed.items() if not values]
    return {
        "status": "REVIEW" if missing else "PASS",
        "checked_tags": list(keys.values()),
        "missing_tags": missing,
    }

def _read_dicom_series(directory: Path) -> VolumeData:
    # Scan the extraction root and nested folders so common DICOM ZIP layouts
    # (series/IM-0001.dcm, nested vendor folders, etc.) work reliably.
    candidates: dict[str, tuple[Path, list[str]]] = {}
    directories = [directory] + [path for path in directory.rglob("*") if path.is_dir()]

    for candidate_dir in directories:
        try:
            series_ids = sitk.ImageSeriesReader.GetGDCMSeriesIDs(str(candidate_dir)) or []
        except Exception:
            continue
        for series_id in series_ids:
            try:
                files = list(sitk.ImageSeriesReader.GetGDCMSeriesFileNames(str(candidate_dir), series_id) or [])
            except Exception:
                files = []
            if files:
                previous = candidates.get(series_id)
                if previous is None or len(files) > len(previous[1]):
                    candidates[series_id] = (candidate_dir, files)

    if not candidates:
        raise ValueError("No DICOM image series was found.")
    if len(candidates) != 1:
        raise ValueError("The uploaded DICOM set contains multiple series. Upload exactly one CT series.")

    _, files = next(iter(candidates.values()))
    _validate_dicom_series_integrity(files)
    reader = sitk.ImageSeriesReader()
    reader.SetFileNames(files)
    reader.MetaDataDictionaryArrayUpdateOn()
    reader.LoadPrivateTagsOn()
    image = reader.Execute()
    modality = _read_dicom_modality(Path(files[0]))
    intensity_domain, hu_calibrated, rescale_slope, rescale_intercept = _read_dicom_intensity_domain(Path(files[0]), modality)

    return VolumeData(
        image=image,
        source_type="DICOM",
        modality=modality,
        intensity_domain=intensity_domain,
        hu_calibrated=hu_calibrated,
        rescale_slope=rescale_slope,
        rescale_intercept=rescale_intercept,
    )


def load_medical_volume(input_paths: list[Path], extraction_root: Path) -> VolumeData:
    if not input_paths:
        raise ValueError("No input files were supplied.")

    lowered = [p.name.lower() for p in input_paths]
    nii = [p for p in input_paths if p.name.lower().endswith(".nii") or p.name.lower().endswith(".nii.gz")]
    zips = [p for p in input_paths if p.name.lower().endswith(".zip")]

    if len(input_paths) == 1 and nii:
        image = sitk.ReadImage(str(input_paths[0]))
        input_notes: list[str] = []

        if image.GetDimension() == 4:
            # A 4D NIfTI can represent time, echo, phase, or another extra
            # acquisition dimension. The current anatomy models accept one
            # 3D volume, so select a deterministic frame rather than failing
            # with the generic "requires a 3D volume" message.
            frame_index = int(os.getenv("RADASSIST_NIFTI_FRAME_INDEX", "0"))
            size = list(image.GetSize())
            frame_count = int(size[3])
            if frame_count <= 0:
                raise ValueError("The 4D NIfTI contains no usable frames.")
            if frame_index < 0 or frame_index >= frame_count:
                raise ValueError(
                    f"RADASSIST_NIFTI_FRAME_INDEX={frame_index} is outside "
                    f"the available 4D frame range 0..{frame_count - 1}."
                )
            extract_size = [int(v) for v in size]
            extract_size[3] = 0
            extract_index = [0, 0, 0, frame_index]
            image = sitk.Extract(image, extract_size, extract_index)
            input_notes.append(
                f"4D NIfTI reduced to frame {frame_index} of {frame_count}; "
                "the selected frame is not independently verified as the intended acquisition."
            )

        if image.GetDimension() != 3:
            raise ValueError(
                f"Unsupported NIfTI dimensionality: {image.GetDimension()}D. "
                "RadAssist models currently require a 3D spatial volume."
            )

        if image.GetNumberOfComponentsPerPixel() > 1:
            components = image.GetNumberOfComponentsPerPixel()
            image = sitk.VectorIndexSelectionCast(image, 0)
            input_notes.append(
                f"Vector NIfTI reduced to component 0 of {components}; "
                "the selected component is not independently verified as the intended acquisition."
            )

        return VolumeData(
            image=image,
            source_type="NIFTI",
            modality="CT",
            intensity_domain="NIfTI source intensity values (unit semantics not independently verified)",
            hu_calibrated=False,
            rescale_slope=None,
            rescale_intercept=None,
            input_notes=input_notes,
        )

    if len(input_paths) == 1 and zips:
        dicom_dir = extraction_root / "dicom"
        _safe_extract_zip(input_paths[0], dicom_dir)
        return _read_dicom_series(dicom_dir)

    # Multiple files are interpreted as a DICOM folder selection.
    dicom_dir = extraction_root / "dicom_files"
    dicom_dir.mkdir(parents=True, exist_ok=True)
    for path in input_paths:
        target = dicom_dir / path.name
        target.write_bytes(path.read_bytes())
    return _read_dicom_series(dicom_dir)


def canonicalize_ct(image: sitk.Image) -> sitk.Image:
    if image.GetDimension() != 3:
        raise ValueError("Only 3D volumes are supported.")
    try:
        return sitk.DICOMOrient(image, "RAS")
    except Exception:
        return image


def resample_image(
    image: sitk.Image,
    target_spacing: tuple[float, float, float] = TARGET_SPACING_MM,
    interpolator: int = sitk.sitkLinear,
    pixel_id: int | None = sitk.sitkFloat32,
) -> sitk.Image:
    spacing = np.asarray(image.GetSpacing(), dtype=np.float64)
    size = np.asarray(image.GetSize(), dtype=np.int64)
    target_spacing_np = np.asarray(target_spacing, dtype=np.float64)
    target_size = np.maximum(np.ceil(size * spacing / target_spacing_np).astype(np.int64), 1)

    resampler = sitk.ResampleImageFilter()
    resampler.SetOutputSpacing([float(v) for v in target_spacing])
    resampler.SetSize([int(v) for v in target_size])
    resampler.SetOutputDirection(image.GetDirection())
    resampler.SetOutputOrigin(image.GetOrigin())
    resampler.SetTransform(sitk.Transform())
    resampler.SetInterpolator(interpolator)
    resampler.SetDefaultPixelValue(-1024.0 if interpolator == sitk.sitkLinear else 0)
    if pixel_id is not None:
        resampler.SetOutputPixelType(pixel_id)
    return resampler.Execute(image)


def normalize_ct_for_model(image: sitk.Image) -> sitk.Image:
    """Apply the MONAI spleen bundle intensity preprocessing.

    CT values are clipped to [-57, 164] HU and linearly scaled to [0, 1].
    No z-score normalization is applied because the verified MONAI bundle
    uses ScaleIntensityRanged only.
    """
    array = sitk.GetArrayFromImage(image).astype(np.float32, copy=False)
    array = np.clip(array, HU_MIN, HU_MAX)
    array = (array - HU_MIN) / (HU_MAX - HU_MIN)

    output = sitk.GetImageFromArray(array.astype(np.float32, copy=False))
    output.CopyInformation(image)
    return output


def _safe_stat(values: np.ndarray, statistic: str) -> float | None:
    if values.size == 0:
        return None
    values = values[np.isfinite(values)]
    if values.size == 0:
        return None
    if statistic == "mean":
        return float(np.mean(values))
    if statistic == "std":
        return float(np.std(values))
    if statistic == "min":
        return float(np.min(values))
    if statistic == "max":
        return float(np.max(values))
    if statistic == "median":
        return float(np.median(values))
    if statistic == "p05":
        return float(np.percentile(values, 5))
    if statistic == "p95":
        return float(np.percentile(values, 95))
    raise ValueError(statistic)


def calculate_metrics(original_ct: sitk.Image, original_space_mask: sitk.Image, validation_dice: float | None) -> dict[str, Any]:
    ct = sitk.GetArrayFromImage(original_ct).astype(np.float32, copy=False)
    mask = sitk.GetArrayFromImage(original_space_mask) > 0
    voxel_count = int(np.count_nonzero(mask))
    spacing = np.asarray(original_ct.GetSpacing(), dtype=np.float64)
    volume_cm3 = float(voxel_count * float(np.prod(spacing)) / 1000.0)
    hu = ct[mask] if voxel_count else np.empty(0, dtype=np.float32)
    return {
        "voxel_count": voxel_count,
        "volume_cm3": volume_cm3,
        "mean_hu": _safe_stat(hu, "mean"),
        "std_hu": _safe_stat(hu, "std"),
        "min_hu": _safe_stat(hu, "min"),
        "max_hu": _safe_stat(hu, "max"),
        "median_hu": _safe_stat(hu, "median"),
        "p05_hu": _safe_stat(hu, "p05"),
        "p95_hu": _safe_stat(hu, "p95"),
        "validation_dice": validation_dice,
    }


def _physical_mesh_from_mask(mask: sitk.Image, step_size: int) -> MeshData:
    mask_array = sitk.GetArrayFromImage(mask).astype(np.uint8, copy=False)
    if not np.any(mask_array):
        return MeshData([], [], 0, 0)
    if mask_array.min() == mask_array.max():
        return MeshData([], [], 0, 0)

    # March only the target bounding box (plus one voxel of padding). This is
    # materially cheaper than running Marching Cubes over a full 512³-style CT.
    occupied = np.argwhere(mask_array > 0)  # [z, y, x]
    z_min, y_min, x_min = occupied.min(axis=0).tolist()
    z_max, y_max, x_max = occupied.max(axis=0).tolist()
    z0, y0, x0 = max(0, z_min - 1), max(0, y_min - 1), max(0, x_min - 1)
    z1 = min(mask_array.shape[0], z_max + 2)
    y1 = min(mask_array.shape[1], y_max + 2)
    x1 = min(mask_array.shape[2], x_max + 2)
    cropped = mask_array[z0:z1, y0:y1, x0:x1]

    spacing_xyz = np.asarray(mask.GetSpacing(), dtype=np.float64)

    # Request voxel-space coordinates from marching_cubes.  The previous
    # implementation supplied physical spacing here and then multiplied the
    # coordinates by spacing again after adding the crop offset, which applied
    # spacing twice and could make the independent mesh-volume cross-check
    # wildly disagree with the native labelmap volume.
    verts_zyx, faces, _, _ = marching_cubes(
        cropped,
        level=0.5,
        spacing=(1.0, 1.0, 1.0),
        step_size=max(1, int(step_size)),
    )

    # marching_cubes returns [z, y, x] positions relative to the cropped
    # array. Add the crop offset in voxel coordinates, then convert exactly
    # once to physical [x, y, z] millimetres.
    offset_zyx = np.asarray([z0, y0, x0], dtype=np.float64)
    verts_zyx = verts_zyx + offset_zyx
    xyz = np.column_stack(
        [verts_zyx[:, 2], verts_zyx[:, 1], verts_zyx[:, 0]]
    ) * spacing_xyz

    direction = np.asarray(mask.GetDirection(), dtype=np.float64).reshape(3, 3)
    origin = np.asarray(mask.GetOrigin(), dtype=np.float64)
    physical = xyz @ direction.T + origin
    return MeshData(
        vertices=np.round(physical, 4).tolist(),
        faces=faces.astype(np.int32).tolist(),
        vertex_count=int(physical.shape[0]),
        face_count=int(faces.shape[0]),
    )


def create_mesh(mask: sitk.Image) -> tuple[MeshData, int]:
    steps = sorted(set([
        max(1, MESH_STEP_SIZE),
        max(2, MESH_STEP_SIZE + 1),
        max(3, MESH_STEP_SIZE + 2),
        max(4, MESH_STEP_SIZE + 3),
        max(5, MESH_STEP_SIZE + 4),
    ]))
    for step in steps:
        mesh = _physical_mesh_from_mask(mask, step)
        if mesh.vertex_count <= MESH_MAX_VERTICES:
            return mesh, step
    raise RuntimeError("The generated segmentation surface exceeds the configured mesh vertex budget.")


def _make_browser_preview(image: sitk.Image) -> sitk.Image:
    """Create a bounded-memory, anonymized CT preview for browser MPR.

    The source image is never replaced by this preview. We downsample the
    longest dimension to MAX_BROWSER_PREVIEW_DIM and store CT values as Int16,
    which keeps Cornerstone memory use predictable for large studies.
    """
    size = np.asarray(image.GetSize(), dtype=np.int64)
    if size.size != 3:
        raise ValueError("Browser preview requires a 3D image.")

    longest = int(size.max())
    if longest <= MAX_BROWSER_PREVIEW_DIM:
        preview = image
    else:
        scale = MAX_BROWSER_PREVIEW_DIM / float(longest)
        target_size = np.maximum(np.floor(size * scale).astype(np.int64), 1)
        target_spacing = np.asarray(image.GetSpacing(), dtype=np.float64) * size / target_size
        resampler = sitk.ResampleImageFilter()
        resampler.SetSize([int(v) for v in target_size])
        resampler.SetOutputSpacing([float(v) for v in target_spacing])
        resampler.SetOutputDirection(image.GetDirection())
        resampler.SetOutputOrigin(image.GetOrigin())
        resampler.SetTransform(sitk.Transform())
        resampler.SetInterpolator(sitk.sitkLinear)
        resampler.SetDefaultPixelValue(-1024.0)
        preview = resampler.Execute(image)

    clean = sitk.Cast(preview, sitk.sitkInt16)
    for key in clean.GetMetaDataKeys():
        clean.EraseMetaData(key)
    return clean


def write_sanitized_nifti(image: sitk.Image, destination: Path, browser_preview: bool = True) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    clean = _make_browser_preview(image) if browser_preview else sitk.Cast(image, sitk.sitkInt16)
    for key in clean.GetMetaDataKeys():
        clean.EraseMetaData(key)
    sitk.WriteImage(clean, str(destination), useCompression=destination.name.lower().endswith(".gz"))


def write_sanitized_mask(image: sitk.Image, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Segmentation labels remain UInt8 while all source metadata is removed.
    clean = sitk.Cast(image, sitk.sitkUInt8)
    for key in clean.GetMetaDataKeys():
        clean.EraseMetaData(key)
    sitk.WriteImage(clean, str(destination), useCompression=destination.name.lower().endswith(".gz"))


def _mesh_geometry_metrics(mesh: MeshData) -> tuple[float | None, float | None]:
    if mesh.vertex_count == 0 or mesh.face_count == 0:
        return None, None
    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    faces = np.asarray(mesh.faces, dtype=np.int64)
    if vertices.ndim != 2 or vertices.shape[1] != 3 or faces.ndim != 2 or faces.shape[1] != 3:
        return None, None
    triangles = vertices[faces]
    cross = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    area_mm2 = float(0.5 * np.linalg.norm(cross, axis=1).sum())
    signed_volume_mm3 = float(np.einsum("ij,ij->i", triangles[:, 0], np.cross(triangles[:, 1], triangles[:, 2])).sum() / 6.0)
    volume_mm3 = abs(signed_volume_mm3)
    return area_mm2 / 100.0, volume_mm3 / 1000.0


def _centroid_mm(mask: sitk.Image) -> list[float] | None:
    array = sitk.GetArrayFromImage(mask) > 0
    points = np.argwhere(array)
    if points.size == 0:
        return None
    # Array order is [z, y, x]; transform the mean index into physical xyz mm.
    mean_zyx = points.mean(axis=0)
    index_xyz = np.asarray([mean_zyx[2], mean_zyx[1], mean_zyx[0]], dtype=np.float64)
    spacing = np.asarray(mask.GetSpacing(), dtype=np.float64)
    direction = np.asarray(mask.GetDirection(), dtype=np.float64).reshape(3, 3)
    origin = np.asarray(mask.GetOrigin(), dtype=np.float64)
    physical = direction @ (index_xyz * spacing) + origin
    return np.round(physical, 3).tolist()


def _intensity_provenance(source_type: str, modality: str, intensity_domain: str, hu_calibrated: bool) -> tuple[str, bool, list[str]]:
    if hu_calibrated:
        return intensity_domain, True, []
    flags: list[str] = []
    if source_type == "NIFTI" and modality == "CT":
        flags.append("Hounsfield units are not independently verified from NIfTI metadata; use DICOM CT when HU traceability is required.")
    elif source_type == "DICOM" and modality == "CT":
        flags.append("DICOM CT intensity transform could not be fully verified from the available metadata.")
    return intensity_domain, False, flags


def _measurement_quality(
    original_ct: sitk.Image,
    mask: sitk.Image,
    source_type: str,
    modality: str,
    mesh: MeshData,
    intensity_domain: str = "Source intensity values",
    hu_calibrated: bool = False,
    rescale_slope: float | None = None,
    rescale_intercept: float | None = None,
) -> dict[str, Any]:
    mask_array = sitk.GetArrayFromImage(mask) > 0
    voxel_count = int(np.count_nonzero(mask_array))
    total_voxels = int(np.prod(np.asarray(original_ct.GetSize(), dtype=np.int64)))
    spacing = np.asarray(original_ct.GetSpacing(), dtype=np.float64)
    voxel_volume_mm3 = float(np.prod(spacing))
    labelmap_volume_cm3 = float(voxel_count * voxel_volume_mm3 / 1000.0)
    equivalent_diameter_mm = (6.0 * labelmap_volume_cm3 * 1000.0 / np.pi) ** (1.0 / 3.0) if labelmap_volume_cm3 > 0 else None
    mask_fraction_pct = float((voxel_count / total_voxels) * 100.0) if total_voxels else 0.0
    surface_area_cm2, mesh_volume_cm3 = _mesh_geometry_metrics(mesh)
    volume_difference_pct = None
    if mesh_volume_cm3 is not None and labelmap_volume_cm3 > 0:
        volume_difference_pct = abs(mesh_volume_cm3 - labelmap_volume_cm3) / labelmap_volume_cm3 * 100.0

    connected_components = 0
    largest_component_fraction_pct = None
    if voxel_count:
        try:
            cc = sitk.ConnectedComponent(mask)
            stats = sitk.LabelShapeStatisticsImageFilter()
            stats.Execute(cc)
            sizes = [stats.GetNumberOfPixels(label) for label in stats.GetLabels()]
            connected_components = len(sizes)
            if sizes:
                largest_component_fraction_pct = max(sizes) / voxel_count * 100.0
        except Exception:
            connected_components = 0
    touches_boundary = bool(
        voxel_count and (
            mask_array[0].any() or mask_array[-1].any() or
            mask_array[:, 0, :].any() or mask_array[:, -1, :].any() or
            mask_array[:, :, 0].any() or mask_array[:, :, -1].any()
        )
    )

    intensity_domain, hu_calibrated, flags = _intensity_provenance(
        source_type, modality, intensity_domain, hu_calibrated
    )
    status = "PASS"
    if voxel_count == 0:
        status = "FAIL"
        flags.append("Segmentation mask is empty.")
    if not np.all(np.isfinite(spacing)) or np.any(spacing <= 0):
        status = "FAIL"
        flags.append("Source voxel spacing is invalid.")
    elif np.any(spacing > 5.0):
        status = "REVIEW"
        flags.append("Large source slice/pixel spacing detected; review volumetric accuracy.")
    if volume_difference_pct is not None and volume_difference_pct > 5.0:
        status = "REVIEW" if status != "FAIL" else status
        flags.append(f"Mesh/labelmap volume difference is {volume_difference_pct:.1f}%.")
    if mask_fraction_pct > 30.0:
        status = "REVIEW" if status != "FAIL" else status
        flags.append("Segmentation occupies an unusually large fraction of the source volume; review the mask.")
    if connected_components > 1:
        status = "REVIEW" if status != "FAIL" else status
        flags.append(f"Segmentation contains {connected_components} connected components; review for leakage or fragmentation.")
    if touches_boundary:
        status = "REVIEW" if status != "FAIL" else status
        flags.append("Segmentation touches the source-volume boundary; review for truncation or leakage.")

    return {
        "status": status,
        "measurement_method": "Labelmap voxel count × native source voxel volume; mesh volume used as independent cross-check",
        "voxel_volume_mm3": voxel_volume_mm3,
        "labelmap_volume_cm3": labelmap_volume_cm3,
        "equivalent_diameter_mm": equivalent_diameter_mm,
        "mask_fraction_pct": mask_fraction_pct,
        "connected_components": connected_components,
        "largest_component_fraction_pct": largest_component_fraction_pct,
        "touches_volume_boundary": touches_boundary,
        "surface_area_cm2": surface_area_cm2,
        "mesh_volume_cm3": mesh_volume_cm3,
        "volume_difference_pct": volume_difference_pct,
        "centroid_mm": _centroid_mm(mask),
        "intensity_domain": intensity_domain,
        "hu_calibrated": hu_calibrated,
        "rescale_slope": rescale_slope,
        "rescale_intercept": rescale_intercept,
        "flags": flags,
    }


def _checkpoint_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()

def advanced_shape_metrics(
    mask: sitk.Image,
    surface_area_cm2: float | None = None,
    mesh_volume_cm3: float | None = None,
) -> dict[str, Any]:
    """Compute geometry descriptors that are useful for research QA.

    These are descriptive shape metrics, not clinical biomarkers. Principal
    spread is estimated from a bounded sample of foreground voxels to keep
    memory predictable on large volumes.
    """
    array = sitk.GetArrayFromImage(mask)
    foreground = array > 0
    voxel_count = int(np.count_nonzero(foreground))
    if voxel_count == 0:
        return {
            "bounding_box_mm": None,
            "principal_spread_mm": None,
            "sphericity": None,
            "compactness": None,
            "surface_to_volume_cm_inv": None,
            "foreground_voxels": 0,
        }

    coords_zyx = np.argwhere(foreground)
    spacing = np.asarray(mask.GetSpacing(), dtype=np.float64)
    direction = np.asarray(mask.GetDirection(), dtype=np.float64).reshape(3, 3)
    origin = np.asarray(mask.GetOrigin(), dtype=np.float64)

    mins = coords_zyx.min(axis=0).astype(np.float64)
    maxs = coords_zyx.max(axis=0).astype(np.float64)
    # Bounding-box extent is reported in the image's physical axes. Direction
    # does not change the voxel-axis lengths.
    bbox_xyz = (maxs[::-1] - mins[::-1] + 1.0) * spacing

    max_samples = 200_000
    if len(coords_zyx) > max_samples:
        stride = max(1, len(coords_zyx) // max_samples)
        coords_zyx = coords_zyx[::stride][:max_samples]

    xyz_index = coords_zyx[:, ::-1].astype(np.float64)
    physical = xyz_index * spacing
    physical = physical @ direction.T + origin
    centered = physical - physical.mean(axis=0, keepdims=True)
    covariance = np.cov(centered, rowvar=False) if len(physical) > 1 else np.zeros((3, 3))
    eigenvalues = np.maximum(np.linalg.eigvalsh(covariance), 0.0)
    principal_spread = (2.0 * np.sqrt(eigenvalues))[::-1]

    volume = voxel_count * float(np.prod(spacing)) / 1000.0
    sphericity = None
    compactness = None
    surface_to_volume = None
    if surface_area_cm2 is not None and surface_area_cm2 > 0 and volume > 0:
        sphericity = float(
            (np.pi ** (1.0 / 3.0) * (6.0 * volume) ** (2.0 / 3.0))
            / surface_area_cm2
        )
        compactness = float(36.0 * np.pi * volume * volume / (surface_area_cm2 ** 3))
        surface_to_volume = float(surface_area_cm2 / volume)

    return {
        "bounding_box_mm": [round(float(v), 3) for v in bbox_xyz],
        "principal_spread_mm": [round(float(v), 3) for v in principal_spread],
        "sphericity": round(sphericity, 5) if sphericity is not None else None,
        "compactness": round(compactness, 5) if compactness is not None else None,
        "surface_to_volume_cm_inv": round(surface_to_volume, 5) if surface_to_volume is not None else None,
        "foreground_voxels": voxel_count,
        "mesh_volume_cm3": mesh_volume_cm3,
    }


def to_serializable(result: SegmentationResult, case_id: str, preview_url: str, mask_url: str) -> dict[str, Any]:
    return {
        "request_id": case_id,
        "target": result.target,
        "source_type": result.source_type,
        "modality": result.modality,
        "is_demo": result.is_demo,
        "volume_cm3": result.volume_cm3,
        "voxel_count": result.voxel_count,
        "hu_statistics": {
            "mean_hu": result.mean_hu,
            "std_hu": result.std_hu,
            "min_hu": result.min_hu,
            "max_hu": result.max_hu,
            "median_hu": result.median_hu,
            "p05_hu": result.p05_hu,
            "p95_hu": result.p95_hu,
        },
        "validation_benchmark": {
            "validation_dice": result.validation_dice,
            "target_threshold": result.validation_dice_threshold,
        },
        "measurement_quality": result.measurement_quality or {},
        "model_provenance": result.model_provenance or {},
        "advanced_metrics": result.advanced_metrics or {},
        "input_notes": result.input_notes or [],
        "mesh": {
            "vertices": result.mesh.vertices,
            "faces": result.mesh.faces,
            "vertex_count": result.mesh.vertex_count,
            "face_count": result.mesh.face_count,
        },
        "original_spacing_mm": result.original_spacing_mm,
        "original_dimensions": result.original_dimensions,
        "processing_seconds": result.processing_seconds,
        "mesh_step_size": result.mesh_step_size,
        "preview": {
            "volume_url": preview_url,
            "mask_url": mask_url,
        },
        "warnings": (
            [
                "Synthetic demonstration data. No clinical or AI inference result is being represented."
            ] if result.is_demo else [
                "Research-use output: this segmentation pipeline has not been clinically validated by RadAssist 3D.",
                "The displayed Dice value is a held-out model benchmark, not a patient-specific accuracy score.",
            ] + list((result.measurement_quality or {}).get("flags", []))
        ),
    }


class RadAssistInferenceEngine:
    def __init__(self, checkpoint_path: Path = MODEL_PATH):
        self.model = SpleenSegmentationModel(checkpoint_path)

    def segment(self, input_paths: list[Path], extraction_root: Path, case_directory: Path) -> tuple[dict[str, Any], sitk.Image, sitk.Image]:
        start = perf_counter()
        loaded = load_medical_volume(input_paths, extraction_root)
        original_ct = loaded.image

        if original_ct.GetDimension() != 3:
            raise ValueError("The supplied image is not a 3D volume.")
        if loaded.modality not in {"CT", "UNKNOWN"}:
            raise ValueError(f"Unsupported modality '{loaded.modality}'. The current model accepts CT volumes only.")

        original_spacing = [float(v) for v in original_ct.GetSpacing()]
        original_dimensions = [int(v) for v in original_ct.GetSize()]

        canonical = canonicalize_ct(original_ct)
        resampled = resample_image(canonical, target_spacing=TARGET_SPACING_MM, interpolator=sitk.sitkLinear, pixel_id=sitk.sitkFloat32)
        # The checkpoint-aware adapter owns intensity preprocessing so runtime
        # preprocessing cannot silently diverge from the loaded model artifact.
        with self.model.inference_lock:
            predicted_resampled_mask = self.model.predict(resampled)

        mask = sitk.Resample(
            predicted_resampled_mask,
            original_ct,
            sitk.Transform(),
            sitk.sitkNearestNeighbor,
            0,
            sitk.sitkUInt8,
        )

        metrics = calculate_metrics(original_ct, mask, self.model.validation_dice)
        mesh, actual_step = create_mesh(mask)
        measurement_quality = _measurement_quality(
            original_ct,
            mask,
            loaded.source_type,
            loaded.modality,
            mesh,
            loaded.intensity_domain,
            loaded.hu_calibrated,
            loaded.rescale_slope,
            loaded.rescale_intercept,
        )
        advanced_metrics = advanced_shape_metrics(
            mask,
            surface_area_cm2=measurement_quality.get("surface_area_cm2"),
            mesh_volume_cm3=measurement_quality.get("mesh_volume_cm3"),
        )
        elapsed = perf_counter() - start
        result = SegmentationResult(
            mesh=mesh,
            voxel_count=metrics["voxel_count"],
            volume_cm3=metrics["volume_cm3"],
            mean_hu=metrics["mean_hu"],
            std_hu=metrics["std_hu"],
            min_hu=metrics["min_hu"],
            max_hu=metrics["max_hu"],
            median_hu=metrics["median_hu"],
            p05_hu=metrics["p05_hu"],
            p95_hu=metrics["p95_hu"],
            validation_dice=metrics["validation_dice"],
            validation_dice_threshold=0.90,
            source_type=loaded.source_type,
            modality=loaded.modality,
            original_spacing_mm=original_spacing,
            original_dimensions=original_dimensions,
            processing_seconds=round(elapsed, 3),
            mesh_step_size=actual_step,
            measurement_quality=measurement_quality,
            advanced_metrics=advanced_metrics,
            input_notes=loaded.input_notes or [],
            model_provenance={
                "name": "RadAssist Spleen CT Segmentation",
                "architecture": self.model.config.get("architecture", "Unknown"),
                "dataset": "Medical Segmentation Decathlon Task09 Spleen",
                "checkpoint_loaded": True,
                "checkpoint_sha256": self.model.checkpoint_sha256,
                "benchmark_mean_dice": self.model.validation_dice,
                "preprocessing": {
                    "orientation": "RAS",
                    "spacing_mm": list(self.model.config.get("required_spacing_mm", TARGET_SPACING_MM)),
                    "hu_range": self.model.config.get("intensity_range_hu", [HU_MIN, HU_MAX]),
                    "normalization": (
                        "Scale intensity range and nonzero z-score"
                        if self.model.config.get("normalize_nonzero")
                        else "Scale intensity range to [0, 1]"
                    ),
                    "roi_size": self.model.config.get("roi_size", [96, 96, 96]),
                    "sliding_window_overlap": self.model.config.get("overlap", SW_OVERLAP),
                },
                "checkpoint_metadata": self.model.config,
            },
        )
        case_id = case_directory.name
        preview_path = case_directory / "preview.nii"
        mask_path = case_directory / "segmentation_mask.nii.gz"
        # Serve a canonicalized preview volume. The quantitative metrics
        # still use the original source geometry and intensities.
        write_sanitized_nifti(canonical, preview_path)
        write_sanitized_mask(mask, mask_path)
        payload = to_serializable(
            result,
            case_id,
            f"/api/v1/cases/{case_id}/volume",
            f"/api/v1/cases/{case_id}/mask",
        )
        return payload, original_ct, mask


def create_demo_case(case_directory: Path) -> dict[str, Any]:
    start = perf_counter()
    case_id = case_directory.name
    size_x, size_y, size_z = 96, 96, 64
    spacing = (1.5, 1.5, 2.0)

    z, y, x = np.indices((size_z, size_y, size_x), dtype=np.float32)
    cx, cy, cz = 48.0, 47.0, 32.0
    body = (
        ((x - 48.0) / 42.0) ** 2
        + ((y - 47.0) / 39.0) ** 2
        + ((z - 32.0) / 29.0) ** 2
    ) < 1.0

    rng = np.random.default_rng(42)
    noise = rng.normal(0, 12, size=(size_z, size_y, size_x)).astype(np.float32)
    volume = np.full((size_z, size_y, size_x), -1000.0, dtype=np.float32)
    volume[body] = 35.0 + noise[body]

    spleen = (
        ((x - cx) / 14.0) ** 2
        + ((y - cy) / 10.0) ** 2
        + ((z - cz) / 13.0) ** 2
    ) <= 1.0
    volume[spleen] = 72.0 + noise[spleen] * 0.55

    ct = sitk.GetImageFromArray(volume)
    ct.SetSpacing(spacing)

    mask_arr = spleen.astype(np.uint8)
    mask = sitk.GetImageFromArray(mask_arr)
    mask.CopyInformation(ct)

    metrics = calculate_metrics(ct, mask, validation_dice=None)
    mesh, actual_step = create_mesh(mask)
    measurement_quality = _measurement_quality(ct, mask, "SYNTHETIC", "CT", mesh, "Synthetic CT-like intensity values", False, None, None)

    result = SegmentationResult(
        mesh=mesh,
        voxel_count=metrics["voxel_count"],
        volume_cm3=metrics["volume_cm3"],
        mean_hu=metrics["mean_hu"],
        std_hu=metrics["std_hu"],
        min_hu=metrics["min_hu"],
        max_hu=metrics["max_hu"],
        median_hu=metrics["median_hu"],
        p05_hu=metrics["p05_hu"],
        p95_hu=metrics["p95_hu"],
        validation_dice=None,
        validation_dice_threshold=0.90,
        source_type="SYNTHETIC",
        modality="CT",
        original_spacing_mm=list(spacing),
        original_dimensions=[size_x, size_y, size_z],
        processing_seconds=round(perf_counter() - start, 3),
        mesh_step_size=actual_step,
        measurement_quality=measurement_quality,
        model_provenance={
            "name": "Synthetic browser demo geometry",
            "architecture": "Synthetic",
            "dataset": "Synthetic",
            "checkpoint_loaded": False,
            "checkpoint_sha256": None,
            "preprocessing": {
                "orientation": "Synthetic",
                "spacing_mm": list(spacing),
                "hu_range": [HU_MIN, HU_MAX],
                "normalization": "Not applicable",
            },
        },
        is_demo=True,
    )

    write_sanitized_nifti(ct, case_directory / "preview.nii", browser_preview=True)
    write_sanitized_mask(mask, case_directory / "segmentation_mask.nii.gz")

    return to_serializable(
        result,
        case_id,
        f"/api/v1/cases/{case_id}/volume",
        f"/api/v1/cases/{case_id}/mask",
    )

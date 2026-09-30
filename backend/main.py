from __future__ import annotations

import logging
import os
import tempfile
import uuid
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import (
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, ORJSONResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

try:
    from .case_store import (
        case_dir,
        create_case,
        delete_case,
        list_case_summaries,
        load_case_result,
        save_case_result,
    )
    from .pipeline import (
        MAX_UPLOAD_BYTES,
        MODEL_PATH,
        DEVICE,
        RadAssistInferenceEngine,
        create_demo_case,
    )
    from .heart_model_adapter import CardiacVentricularAdapter
    from .prostate_model_adapter import ProstateMRIAdapter
    from .multimodel_engine import MultiModelInferenceEngine
    from .engineering import append_audit_event, build_provenance, validate_input_contract, write_report_bundle
except ImportError:
    from case_store import (
        case_dir,
        create_case,
        delete_case,
        list_case_summaries,
        load_case_result,
        save_case_result,
    )
    from pipeline import (
        MAX_UPLOAD_BYTES,
        MODEL_PATH,
        DEVICE,
        RadAssistInferenceEngine,
        create_demo_case,
    )
    from heart_model_adapter import CardiacVentricularAdapter
    from prostate_model_adapter import ProstateMRIAdapter
    from multimodel_engine import MultiModelInferenceEngine
    from engineering import append_audit_event, build_provenance, validate_input_contract, write_report_bundle


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

logger = logging.getLogger("radassist.api")


# ---------------------------------------------------------------------------
# Model registry metadata
# ---------------------------------------------------------------------------

SUPPORTED_TARGETS = {
    "spleen": {
        "display_name": "Spleen",
        "modality": "CT",
        "description": "Spleen CT segmentation",
        "labels": {
            "0": "background",
            "1": "spleen",
        },
    },
    "heart": {
        "display_name": "Heart",
        "modality": "MR",
        "description": "Cardiac MRI ventricular segmentation",
        "labels": {
            "0": "background",
            "1": "LV blood pool",
            "2": "myocardium",
            "3": "RV blood pool",
        },
    },
    "prostate": {
        "display_name": "Prostate",
        "modality": "MR",
        "description": "Prostate MRI zonal segmentation",
        "labels": {
            "0": "background",
            "1": "central gland",
            "2": "peripheral zone",
        },
    },
}


# ---------------------------------------------------------------------------
# Application lifecycle
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "Starting RadAssist 3D backend on %s",
        DEVICE,
    )

    engines: dict[str, Any] = {}
    errors: dict[str, str | None] = {}

    # -------------------------
    # Spleen
    # -------------------------
    try:
        spleen_engine = RadAssistInferenceEngine(
            MODEL_PATH
        )

        engines["spleen"] = spleen_engine
        errors["spleen"] = None

        logger.info(
            "Spleen model loaded successfully."
        )

    except FileNotFoundError as exc:
        errors["spleen"] = str(exc)

        logger.warning(
            "Spleen model checkpoint unavailable: %s",
            exc,
        )

    except Exception as exc:
        errors["spleen"] = str(exc)

        logger.exception(
            "Spleen model initialization failed."
        )

    # -------------------------
    # Heart + Prostate
    # -------------------------
    heart_model = None
    prostate_model = None

    try:
        heart_model = (
            CardiacVentricularAdapter()
        )

        errors["heart"] = None

        logger.info(
            "Heart model loaded successfully."
        )

    except Exception as exc:
        errors["heart"] = str(exc)

        logger.exception(
            "Heart model initialization failed."
        )

    try:
        prostate_model = (
            ProstateMRIAdapter()
        )

        errors["prostate"] = None

        logger.info(
            "Prostate model loaded successfully."
        )

    except Exception as exc:
        errors["prostate"] = str(exc)

        logger.exception(
            "Prostate model initialization failed."
        )

    # Create MRI dispatcher only when both adapters are available.
    if (
        heart_model is not None
        and prostate_model is not None
    ):
        try:
            app.state.mri_engine = (
                MultiModelInferenceEngine(
                    heart_model,
                    prostate_model,
                )
            )

            engines["heart"] = heart_model
            engines["prostate"] = prostate_model

            logger.info(
                "Heart + Prostate multimodel engine ready."
            )

        except Exception as exc:
            app.state.mri_engine = None

            errors["heart"] = (
                errors.get("heart")
                or str(exc)
            )

            errors["prostate"] = (
                errors.get("prostate")
                or str(exc)
            )

            logger.exception(
                "MRI multimodel dispatcher initialization failed."
            )

    else:
        app.state.mri_engine = None

    # Backward-compatible single spleen reference.
    app.state.engine = engines.get(
        "spleen"
    )

    app.state.engines = engines
    app.state.model_errors = errors

    app.state.model_loaded = bool(
        engines
    )

    combined_errors = [
        f"{name}: {message}"
        for name, message in errors.items()
        if message
    ]

    app.state.model_error = (
        "; ".join(combined_errors)
        if combined_errors
        else None
    )

    logger.info(
        "Loaded RadAssist models: %s",
        ", ".join(sorted(engines))
        if engines
        else "none",
    )

    yield

    logger.info(
        "RadAssist 3D backend stopped."
    )


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="RadAssist 3D API",
    version="1.4.0",
    description=(
        "Research-oriented multimodel medical "
        "image segmentation and visualization backend."
    ),
    default_response_class=ORJSONResponse,
    lifespan=lifespan,
)


cors_origins = [
    origin.strip()
    for origin in os.getenv(
        "RADASSIST_CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    ).split(",")
    if origin.strip()
]


app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=[
        "GET",
        "POST",
        "DELETE",
    ],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    device: str
    model_loaded: bool
    model_error: str | None = None

    models: dict[
        str,
        dict[str, Any],
    ] = Field(
        default_factory=dict
    )


class HUStatistics(BaseModel):
    mean_hu: float | None
    std_hu: float | None
    min_hu: float | None
    max_hu: float | None
    median_hu: float | None
    p05_hu: float | None
    p95_hu: float | None


class ValidationBenchmark(BaseModel):
    validation_dice: float | None = Field(
        description=(
            "Held-out model validation Dice; "
            "not patient-specific accuracy."
        )
    )

    target_threshold: float

    per_class: dict[str, float] = Field(
        default_factory=dict
    )


class LabelMetric(BaseModel):
    label: int
    name: str
    voxel_count: int
    volume_cm3: float
    fraction_pct: float


class MeasurementQuality(BaseModel):
    status: str
    measurement_method: str
    voxel_volume_mm3: float
    labelmap_volume_cm3: float
    equivalent_diameter_mm: float | None = None
    mask_fraction_pct: float
    connected_components: int
    largest_component_fraction_pct: float | None = None
    touches_volume_boundary: bool
    surface_area_cm2: float | None = None
    mesh_volume_cm3: float | None = None
    volume_difference_pct: float | None = None
    centroid_mm: list[float] | None = None
    intensity_domain: str
    hu_calibrated: bool
    rescale_slope: float | None = None
    rescale_intercept: float | None = None
    flags: list[str] = Field(
        default_factory=list
    )


class ModelProvenance(BaseModel):
    name: str
    architecture: str
    dataset: str
    checkpoint_loaded: bool
    checkpoint_sha256: str | None = None
    preprocessing: dict[str, Any]
    labels: dict[str, str] = Field(
        default_factory=dict
    )


class MeshResponse(BaseModel):
    vertices: list[list[float]]
    faces: list[list[int]]
    vertex_count: int
    face_count: int


class PreviewResponse(BaseModel):
    volume_url: str
    mask_url: str


class SegmentResponse(BaseModel):
    request_id: str
    target: str
    source_type: str
    modality: str
    is_demo: bool

    volume_cm3: float
    voxel_count: int

    hu_statistics: HUStatistics

    validation_benchmark: ValidationBenchmark

    measurement_quality: MeasurementQuality | None = None

    model_provenance: ModelProvenance

    label_metrics: list[LabelMetric] = Field(
        default_factory=list
    )

    label_meshes: dict[str, MeshResponse] = Field(
        default_factory=dict
    )

    label_component_qa: dict[str, dict] = Field(
        default_factory=dict
    )

    mesh: MeshResponse

    original_spacing_mm: list[float]
    original_dimensions: list[int]

    processing_seconds: float
    mesh_step_size: int

    preview: PreviewResponse

    warnings: list[str]

    # Phase 3 structured-result architecture.
    provenance_record: dict[str, Any] | None = None
    structured_measurements: dict[str, Any] | None = None
    dicom_seg_result: dict[str, Any] | None = None
    dicom_sr_result: dict[str, Any] | None = None
    uncertainty_status: dict[str, Any] | None = None
    input_validation: dict[str, Any] | None = None


class CaseSummary(BaseModel):
    case_id: str
    target: str
    source_type: str
    modality: str
    volume_cm3: float | None
    stored_at: str | None
    is_demo: bool


# ---------------------------------------------------------------------------
# Upload / filesystem helpers
# ---------------------------------------------------------------------------

def _supported_name(name: str) -> bool:
    lower = name.lower()

    return lower.endswith(
        (
            ".nii",
            ".nii.gz",
            ".dcm",
            ".dicom",
            ".ima",
            ".zip",
        )
    ) or "." not in Path(name).name


async def _save_upload(
    upload: UploadFile,
    destination: Path,
    total_so_far: int,
) -> int:
    current = total_so_far

    with destination.open("wb") as target:
        while True:
            chunk = await upload.read(
                1024 * 1024
            )

            if not chunk:
                break

            current += len(chunk)

            if current > MAX_UPLOAD_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail=(
                        "Combined upload size exceeds "
                        "the configured maximum."
                    ),
                )

            target.write(chunk)

    await upload.close()

    return current


def _absolute_case_file(
    case_id: str,
    filename: str,
) -> Path:
    directory = (
        case_dir(case_id)
        .resolve()
    )

    file_path = (
        directory / filename
    ).resolve()

    file_path.relative_to(
        directory
    )

    return file_path


# ---------------------------------------------------------------------------
# Basic endpoints
# ---------------------------------------------------------------------------

@app.get("/")
async def root() -> dict[str, str]:
    return {
        "service": "RadAssist 3D API",
        "version": "1.4.0",
        "status": "ok",
        "docs": "/docs",
        "health": "/health",
    }


@app.get(
    "/health",
    response_model=HealthResponse,
)
async def health(
    request: Request,
) -> HealthResponse:
    engines = getattr(
        request.app.state,
        "engines",
        {},
    )

    errors = getattr(
        request.app.state,
        "model_errors",
        {},
    )

    models: dict[
        str,
        dict[str, Any],
    ] = {}

    for target in (
        "spleen",
        "heart",
        "prostate",
    ):
        metadata = (
            SUPPORTED_TARGETS[target]
        )

        models[target] = {
            "loaded": target in engines,
            "error": errors.get(target),
            "display_name": metadata[
                "display_name"
            ],
            "modality": metadata[
                "modality"
            ],
        }

    return HealthResponse(
        status=(
            "ok"
            if bool(engines)
            else "degraded"
        ),
        service="radassist-3d-backend",
        version="1.4.0",
        device=str(DEVICE),
        model_loaded=bool(engines),
        model_error=getattr(
            request.app.state,
            "model_error",
            None,
        ),
        models=models,
    )


@app.get(
    "/api/v1/models"
)
async def models(
    request: Request,
) -> dict[str, Any]:
    engines = getattr(
        request.app.state,
        "engines",
        {},
    )

    errors = getattr(
        request.app.state,
        "model_errors",
        {},
    )

    result: dict[
        str,
        dict[str, Any],
    ] = {}

    for target, metadata in (
        SUPPORTED_TARGETS.items()
    ):
        result[target] = {
            **metadata,
            "loaded": target in engines,
            "error": errors.get(target),
        }

    return {
        "models": result
    }


# ---------------------------------------------------------------------------
# Case history
# ---------------------------------------------------------------------------

@app.get(
    "/api/v1/cases",
    response_model=list[CaseSummary],
)
async def cases() -> list[CaseSummary]:
    return [
        CaseSummary(**item)
        for item in list_case_summaries()
    ]


@app.get(
    "/api/v1/cases/{case_id}",
    response_model=SegmentResponse,
)
async def get_case(
    case_id: str,
) -> SegmentResponse:
    try:
        return SegmentResponse(
            **load_case_result(case_id)
        )

    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail="Case not found.",
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc


@app.delete(
    "/api/v1/cases/{case_id}"
)
async def remove_case(
    case_id: str,
) -> dict[str, Any]:
    try:
        case_path = case_dir(
            case_id
        )

        if not case_path.exists():
            raise HTTPException(
                status_code=404,
                detail="Case not found.",
            )

        delete_case(case_id)

        return {
            "deleted": True,
            "case_id": case_id,
        }

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc


# ---------------------------------------------------------------------------
# Case artifacts
# ---------------------------------------------------------------------------

@app.get(
    "/api/v1/cases/{case_id}/volume"
)
async def get_case_volume(
    case_id: str,
) -> FileResponse:
    path = _absolute_case_file(
        case_id,
        "preview.nii",
    )

    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail="Preview volume not found.",
        )

    return FileResponse(
        path,
        media_type="application/octet-stream",
        filename="preview.nii",
        headers={
            "Cache-Control": (
                "private, max-age=3600"
            )
        },
    )


@app.get(
    "/api/v1/cases/{case_id}/mask"
)
async def get_case_mask(
    case_id: str,
) -> FileResponse:
    path = _absolute_case_file(
        case_id,
        "segmentation_mask.nii.gz",
    )

    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=(
                "Segmentation mask not found."
            ),
        )

    return FileResponse(
        path,
        media_type="application/gzip",
        filename="segmentation_mask.nii.gz",
        headers={
            "Cache-Control": (
                "private, max-age=3600"
            )
        },
    )


@app.get(
    "/api/v1/cases/{case_id}/bundle"
)
async def get_case_bundle(
    case_id: str,
) -> FileResponse:
    try:
        directory = case_dir(
            case_id
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    if not directory.exists():
        raise HTTPException(
            status_code=404,
            detail="Case not found.",
        )

    bundle_path = (
        directory
        / "radassist_case_bundle.zip"
    )

    if not bundle_path.exists():
        files_to_include = [
            directory / "result.json",
            directory / "summary.json",
            directory / "preview.nii",
            directory
            / "segmentation_mask.nii.gz",
            directory / "report.json",
            directory / "audit.jsonl",
        ]

        existing = [
            path
            for path in files_to_include
            if path.exists()
        ]

        if not existing:
            raise HTTPException(
                status_code=404,
                detail=(
                    "Case artifacts are unavailable."
                ),
            )

        with zipfile.ZipFile(
            bundle_path,
            "w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=6,
        ) as archive:
            for path in existing:
                archive.write(
                    path,
                    arcname=path.name,
                )

    return FileResponse(
        bundle_path,
        media_type="application/zip",
        filename="radassist_case_bundle.zip",
        headers={
            "Cache-Control": (
                "private, max-age=300"
            )
        },
    )


@app.get("/api/v1/cases/{case_id}/report")
async def get_case_report(case_id: str) -> FileResponse:
    try:
        path = _absolute_case_file(case_id, "report.json")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not path.exists():
        raise HTTPException(status_code=404, detail="Structured report not found.")
    return FileResponse(path, media_type="application/json", filename="radassist_report.json", headers={"Cache-Control": "private, max-age=300"})


# ---------------------------------------------------------------------------
# Segmentation endpoint
# ---------------------------------------------------------------------------

@app.post(
    "/api/v1/segment",
    response_model=SegmentResponse,
)
async def segment(
    request: Request,
    target: str = Form("spleen"),
    files: list[UploadFile] = File(
        ...,
        description=(
            "One NIfTI volume, one DICOM ZIP, "
            "or multiple DICOM files selected "
            "from a folder."
        ),
    ),
) -> SegmentResponse:

    if not files:
        raise HTTPException(
            status_code=400,
            detail="No files were uploaded.",
        )

    target = target.strip().lower()

    if target not in SUPPORTED_TARGETS:
        raise HTTPException(
            status_code=400,
            detail=(
                "Unsupported model target. "
                "Choose spleen, heart, or prostate."
            ),
        )

    # ------------------------------------------------------------
    # File validation
    # ------------------------------------------------------------

    if len(files) == 1:
        upload_name = (
            files[0].filename
            or ""
        )

        if not _supported_name(
            upload_name
        ):
            raise HTTPException(
                status_code=415,
                detail=(
                    "Unsupported file type: "
                    f"{upload_name or '<unnamed>'}"
                ),
            )

    lowered_names = [
        (
            upload.filename
            or ""
        ).lower()
        for upload in files
    ]

    has_nifti = any(
        name.endswith(
            (
                ".nii",
                ".nii.gz",
            )
        )
        for name in lowered_names
    )

    has_zip = any(
        name.endswith(".zip")
        for name in lowered_names
    )

    if len(files) > 1 and (
        has_nifti or has_zip
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "Upload exactly one NIfTI volume "
                "or one DICOM ZIP. Multiple files "
                "are reserved for a DICOM series."
            ),
        )

    if len(files) > 5000:
        raise HTTPException(
            status_code=413,
            detail=(
                "The selected DICOM series contains "
                "too many files. Create a ZIP and "
                "upload the ZIP instead."
            ),
        )

    # ------------------------------------------------------------
    # Select model subsystem
    # ------------------------------------------------------------

    engines = getattr(
        request.app.state,
        "engines",
        {},
    )

    if target == "spleen":
        engine = engines.get(
            "spleen"
        )

        if engine is None:
            raise HTTPException(
                status_code=503,
                detail=(
                    "The Spleen model is unavailable."
                ),
            )

    else:
        engine = getattr(
            request.app.state,
            "mri_engine",
            None,
        )

        if engine is None:
            raise HTTPException(
                status_code=503,
                detail=(
                    "The MRI model subsystem is unavailable."
                ),
            )

        if target not in engines:
            raise HTTPException(
                status_code=503,
                detail=(
                    f"The {target.title()} model is unavailable."
                ),
            )

    # ------------------------------------------------------------
    # Case creation
    # ------------------------------------------------------------

    case_id = uuid.uuid4().hex

    try:
        case_path = create_case(
            case_id
        )

    except FileExistsError as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "Could not create a unique "
                "case directory."
            ),
        ) from exc

    # ------------------------------------------------------------
    # Save uploads + inference
    # ------------------------------------------------------------

    try:
        with tempfile.TemporaryDirectory(
            prefix=f"radassist_{case_id}_"
        ) as tmp_dir:

            tmp = Path(tmp_dir)

            input_paths: list[
                Path
            ] = []

            total = 0

            for index, upload in enumerate(
                files
            ):
                safe_name = Path(
                    upload.filename
                    or f"input_{index}"
                ).name

                destination = (
                    tmp
                    / f"{index:05d}_{safe_name}"
                )

                total = await _save_upload(
                    upload,
                    destination,
                    total,
                )

                input_paths.append(
                    destination
                )

            extraction_root = (
                tmp / "extracted"
            )

            # Existing validated Spleen workflow.
            if target == "spleen":

                result_payload, _, _ = (
                    await run_in_threadpool(
                        engine.segment,
                        input_paths,
                        extraction_root,
                        case_path,
                    )
                )

            # Heart / Prostate multimodel workflow.
            else:

                result_payload, _, _ = (
                    await run_in_threadpool(
                        engine.segment,
                        target,
                        input_paths,
                        extraction_root,
                        case_path,
                    )
                )

            input_validation = validate_input_contract(
                source_type=str(result_payload.get("source_type", "UNKNOWN")),
                modality=str(result_payload.get("modality", "UNKNOWN")),
                dimensions=[int(v) for v in result_payload.get("original_dimensions", [])],
                spacing_mm=[float(v) for v in result_payload.get("original_spacing_mm", [])],
            )
            if input_validation["status"] != "PASS":
                raise ValueError("Input validation failed: " + ", ".join(input_validation["errors"]))

            # Build deterministic structured result metadata before persistence.
            result_payload["input_validation"] = input_validation
            provenance_record = build_provenance(result_payload)
            result_payload["provenance_record"] = provenance_record
            result_payload["structured_measurements"] = provenance_record["structured_measurements"]
            result_payload["dicom_seg_result"] = provenance_record["dicom_seg"]
            result_payload["dicom_sr_result"] = provenance_record["dicom_sr"]
            result_payload["uncertainty_status"] = provenance_record["structured_measurements"]["uncertainty_status"]

            write_report_bundle(case_path, result_payload)
            append_audit_event(
                case_path,
                "SEGMENTATION_COMPLETED",
                request_id=case_id,
                target=target,
                source_type=result_payload.get("source_type"),
                modality=result_payload.get("modality"),
                input_validation=input_validation,
                qa_status=(result_payload.get("measurement_quality") or {}).get("status"),
            )

            save_case_result(
                case_id,
                result_payload,
            )

            return SegmentResponse(
                **result_payload
            )

    except HTTPException:
        delete_case(case_id)
        raise

    except ValueError as exc:
        delete_case(case_id)

        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except RuntimeError as exc:
        delete_case(case_id)

        logger.exception(
            "Runtime inference error for %s",
            case_id,
        )

        raise HTTPException(
            status_code=500,
            detail=(
                "The segmentation pipeline "
                "could not complete the request."
            ),
        ) from exc

    except Exception as exc:
        delete_case(case_id)

        logger.exception(
            "Unexpected inference error for %s",
            case_id,
        )

        raise HTTPException(
            status_code=500,
            detail=(
                "Unexpected server error "
                "during segmentation."
            ),
        ) from exc


# ---------------------------------------------------------------------------
# Synthetic demo
# ---------------------------------------------------------------------------

@app.post(
    "/api/v1/demo",
    response_model=SegmentResponse,
)
async def demo(
    request: Request,
) -> SegmentResponse:

    if (
        os.getenv(
            "RADASSIST_ALLOW_DEMO",
            "true",
        ).lower()
        != "true"
    ):
        raise HTTPException(
            status_code=404,
            detail="Demo mode is disabled.",
        )

    case_id = (
        f"demo-{uuid.uuid4().hex[:16]}"
    )

    try:
        case_path = create_case(
            case_id
        )

        result_payload = (
            await run_in_threadpool(
                create_demo_case,
                case_path,
            )
        )

        save_case_result(
            case_id,
            result_payload,
        )

        return SegmentResponse(
            **result_payload
        )

    except Exception as exc:
        delete_case(case_id)

        logger.exception(
            "Demo generation failed for %s",
            case_id,
        )

        raise HTTPException(
            status_code=500,
            detail=(
                "Could not create "
                "synthetic demo data."
            ),
        ) from exc
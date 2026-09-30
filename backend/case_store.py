from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CASE_ROOT = Path(
    os.getenv(
        "RADASSIST_CASE_ROOT",
        Path(__file__).resolve().parent / "data" / "cases",
    )
)

CASE_ROOT.mkdir(parents=True, exist_ok=True)


def case_dir(case_id: str) -> Path:
    """Return a safe, deterministic directory for a generated case."""
    if not case_id or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for ch in case_id):
        raise ValueError("Invalid case identifier.")
    return CASE_ROOT / case_id


def create_case(case_id: str) -> Path:
    path = case_dir(case_id)
    path.mkdir(parents=True, exist_ok=False)
    return path


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )
    os.replace(tmp, path)


def save_case_result(case_id: str, payload: dict[str, Any]) -> None:
    path = case_dir(case_id)
    path.mkdir(parents=True, exist_ok=True)
    payload = dict(payload)
    payload["stored_at"] = datetime.now(timezone.utc).isoformat()
    write_json_atomic(path / "result.json", payload)
    write_json_atomic(path / "summary.json", {
        "case_id": payload.get("request_id"),
        "target": payload.get("target"),
        "source_type": payload.get("source_type"),
        "modality": payload.get("modality"),
        "volume_cm3": payload.get("volume_cm3"),
        "stored_at": payload.get("stored_at"),
        "is_demo": payload.get("is_demo", False),
    })


def load_case_result(case_id: str) -> dict[str, Any]:
    result_path = case_dir(case_id) / "result.json"
    if not result_path.exists():
        raise FileNotFoundError(case_id)
    return json.loads(result_path.read_text(encoding="utf-8"))


def delete_case(case_id: str) -> None:
    path = case_dir(case_id)
    if path.exists():
        shutil.rmtree(path)


def list_case_summaries(limit: int = 25) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    try:
        case_paths = [p for p in CASE_ROOT.iterdir() if p.is_dir()]
    except OSError:
        return results

    def safe_mtime(path: Path) -> float:
        try:
            return path.stat().st_mtime
        except OSError:
            return 0.0

    for case_path in sorted(
        case_paths,
        key=safe_mtime,
        reverse=True,
    ):
        if not case_path.is_dir():
            continue
        summary_path = case_path / "summary.json"
        result_path = case_path / "result.json"
        if summary_path.exists():
            try:
                results.append(json.loads(summary_path.read_text(encoding="utf-8")))
            except Exception:
                continue
        elif result_path.exists():
            try:
                payload = json.loads(result_path.read_text(encoding="utf-8"))
                results.append({
                    "case_id": payload.get("request_id"),
                    "target": payload.get("target"),
                    "source_type": payload.get("source_type"),
                    "volume_cm3": payload.get("volume_cm3"),
                    "modality": payload.get("modality"),
                    "stored_at": payload.get("stored_at"),
                    "is_demo": payload.get("is_demo", False),
                })
            except Exception:
                continue
        if len(results) >= limit:
            break
    return results

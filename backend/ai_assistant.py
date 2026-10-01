from __future__ import annotations

import os
from typing import Any

import requests


SYSTEM_PROMPT = (
    "You are a research medical-imaging workstation assistant. "
    "Only discuss the supplied structured segmentation result. "
    "Do not diagnose, prognosticate, recommend treatment, or claim patient-specific accuracy. "
    "Explicitly distinguish model benchmarks from patient-specific validation. "
    "If the data does not support an answer, say so."
)


def build_context(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "target": result.get("target"),
        "modality": result.get("modality"),
        "source_type": result.get("source_type"),
        "volume_cm3": result.get("volume_cm3"),
        "label_metrics": result.get("label_metrics", []),
        "measurement_quality": result.get("measurement_quality", {}),
        "validation_benchmark": result.get("validation_benchmark", {}),
        "model_provenance": result.get("model_provenance", {}),
        "uncertainty_status": result.get("uncertainty_status", {}),
        "warnings": result.get("warnings", []),
    }


def deterministic_answer(result: dict[str, Any], question: str) -> str:
    quality = result.get("measurement_quality") or {}
    benchmark = result.get("validation_benchmark") or {}
    flags = quality.get("flags") or []
    if any(word in question.lower() for word in ("quality", "qa", "reliable", "review")):
        return (
            f"Measurement QA is {quality.get('status', 'REVIEW')}. "
            f"There are {len(flags)} review flag(s). "
            "Patient-specific accuracy is not established by this result."
        )
    if any(word in question.lower() for word in ("volume", "size", "measurement")):
        return (
            f"The segmented foreground volume is {result.get('volume_cm3', '—')} cm³. "
            "This is a computed geometric measurement of the segmentation, not a clinical interpretation."
        )
    if "dice" in question.lower() or "iou" in question.lower():
        return (
            f"The runtime result reports validation Dice as {benchmark.get('validation_dice')}. "
            "Use the offline reference-mask validator for patient/reference-specific Dice and IoU."
        )
    return (
        "I can explain the supplied segmentation measurements, QA flags, provenance, and validation status. "
        "I will not infer a diagnosis or treatment recommendation from this result."
    )


def answer(result: dict[str, Any], question: str) -> dict[str, Any]:
    base_url = os.getenv("RADASSIST_AI_BASE_URL", "").rstrip("/")
    api_key = os.getenv("RADASSIST_AI_API_KEY", "")
    model = os.getenv("RADASSIST_AI_MODEL", "")

    if not base_url or not api_key or not model:
        return {
            "provider": "deterministic",
            "configured": False,
            "answer": deterministic_answer(result, question),
        }

    payload = {
        "model": model,
        "temperature": 0.1,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Question:\n"
                    + question
                    + "\n\nStructured result JSON:\n"
                    + str(build_context(result))
                ),
            },
        ],
    }
    response = requests.post(
        f"{base_url}/chat/completions",
        json=payload,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        timeout=45,
    )
    response.raise_for_status()
    body = response.json()
    text = body["choices"][0]["message"]["content"]
    return {"provider": "llm", "configured": True, "answer": str(text)}

from __future__ import annotations

import os
from typing import Any

import requests


class DicomWebClient:
    def __init__(self, base_url: str | None = None, token: str | None = None, timeout: float = 30.0):
        self.base_url = (base_url or os.getenv("RADASSIST_DICOMWEB_URL", "")).rstrip("/")
        self.token = token or os.getenv("RADASSIST_DICOMWEB_TOKEN")
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self.base_url)

    def _headers(self, accept: str = "application/dicom+json") -> dict[str, str]:
        headers = {"Accept": accept}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def qido_studies(self, query: dict[str, str] | None = None) -> Any:
        if not self.configured:
            raise RuntimeError("DICOMweb is not configured. Set RADASSIST_DICOMWEB_URL.")
        response = requests.get(
            f"{self.base_url}/studies",
            params=query or {},
            headers=self._headers(),
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def qido_series(self, study_instance_uid: str) -> Any:
        if not self.configured:
            raise RuntimeError("DICOMweb is not configured. Set RADASSIST_DICOMWEB_URL.")
        response = requests.get(
            f"{self.base_url}/studies/{study_instance_uid}/series",
            headers=self._headers(),
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def stow(self, dicom_bytes: bytes) -> str:
        if not self.configured:
            raise RuntimeError("DICOMweb is not configured. Set RADASSIST_DICOMWEB_URL.")
        headers = self._headers("application/dicom+json")
        headers.update({
            "Content-Type": "application/dicom",
            "Accept": "application/dicom+json",
        })
        response = requests.post(
            f"{self.base_url}/studies",
            data=dicom_bytes,
            headers=headers,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.text

    def wado_instance(self, study_uid: str, series_uid: str, sop_uid: str) -> bytes:
        if not self.configured:
            raise RuntimeError("DICOMweb is not configured. Set RADASSIST_DICOMWEB_URL.")
        response = requests.get(
            f"{self.base_url}/studies/{study_uid}/series/{series_uid}/instances/{sop_uid}",
            headers=self._headers("application/dicom"),
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.content

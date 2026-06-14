"""
FHIR R4 REST client — thin httpx wrapper for GET and bundle search.
"""

import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_TIMEOUT = 20.0


def _headers() -> dict:
    h = {"Accept": "application/fhir+json"}
    if settings.fhir_auth_token:
        h["Authorization"] = f"Bearer {settings.fhir_auth_token}"
    return h


def get_resource(path: str) -> dict[str, Any]:
    """GET a single FHIR resource by path, e.g. 'Patient/123'."""
    url = f"{settings.fhir_base_url.rstrip('/')}/{path}"
    resp = httpx.get(url, headers=_headers(), timeout=_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def search(resource_type: str, params: dict[str, str]) -> dict[str, Any]:
    """Search a FHIR resource type and return the Bundle."""
    url = f"{settings.fhir_base_url.rstrip('/')}/{resource_type}"
    resp = httpx.get(url, headers=_headers(), params=params, timeout=_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def bundle_entries(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract resource entries from a FHIR Bundle."""
    return [e["resource"] for e in bundle.get("entry", []) if "resource" in e]

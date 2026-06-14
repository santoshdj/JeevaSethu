"""
Patient service — fetches cancer-relevant FHIR resources and builds
a structured plain-text profile for the Foundry Agent.
"""

import datetime
import logging
from typing import Any

from app import fhir_client

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_patient(patient_id: str) -> dict[str, Any]:
    """Return a summary dict for a single patient."""
    pt = fhir_client.get_resource(f"Patient/{patient_id}")
    return _summarise_patient(pt)


def search_patients(name: str | None = None, count: int = 50) -> list[dict[str, Any]]:
    """Return a deduplicated list of patient summary dicts, optionally filtered by name."""
    # Fetch more than needed to have enough after deduplication
    params: dict[str, str] = {"_count": str(count * 4), "_sort": "family"}
    if name:
        params["name"] = name
    bundle = fhir_client.search("Patient", params)
    patients = [_summarise_patient(pt) for pt in fhir_client.bundle_entries(bundle)]

    # Deduplicate by (name, dob) — public HAPI sandbox has many duplicate Synthea uploads
    seen: set[tuple[str, str]] = set()
    unique: list[dict[str, Any]] = []
    for pt in patients:
        key = (pt["name"].lower(), pt["dob"])
        if key not in seen:
            seen.add(key)
            unique.append(pt)
        if len(unique) >= count:
            break
    return unique


def build_patient_profile(patient_id: str) -> str:
    """
    Fetch FHIR resources for a patient and return a structured plain-text
    profile suitable for sending to the Foundry Agent as a user message.
    """
    pt = fhir_client.get_resource(f"Patient/{patient_id}")
    conditions = fhir_client.bundle_entries(
        fhir_client.search("Condition", {"patient": patient_id, "clinical-status": "active"})
    )
    medications = fhir_client.bundle_entries(
        fhir_client.search("MedicationRequest", {"patient": patient_id, "status": "active"})
    )
    labs = fhir_client.bundle_entries(
        fhir_client.search(
            "Observation",
            {"patient": patient_id, "category": "laboratory", "_sort": "-date", "_count": "20"},
        )
    )
    procedures = fhir_client.bundle_entries(
        fhir_client.search("Procedure", {"patient": patient_id, "_sort": "-date", "_count": "10"})
    )

    name = _extract_name(pt)
    age = _calculate_age(pt.get("birthDate", ""))
    sex = pt.get("gender", "unknown").capitalize()

    condition_lines = _format_conditions(conditions)
    medication_lines = _format_medications(medications)
    lab_lines = _format_labs(labs)
    procedure_lines = _format_procedures(procedures)

    return f"""PATIENT PROFILE FOR CLINICAL TRIAL MATCHING

Demographics:
- Name: {name}
- Age: {age} years
- Biological Sex: {sex}

Active Diagnoses / Cancer Conditions:
{_bullet_list(condition_lines)}

Current Medications (chemotherapy, targeted therapy, supportive care):
{_bullet_list(medication_lines)}

Recent Laboratory Results (tumor markers, CBC, metabolic panel):
{_bullet_list(lab_lines)}

Prior Procedures and Treatments (surgeries, radiation, prior chemo lines):
{_bullet_list(procedure_lines)}
"""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _summarise_patient(pt: dict[str, Any]) -> dict[str, Any]:
    patient_id = pt.get("id", "")
    name = _extract_name(pt)
    age = _calculate_age(pt.get("birthDate", ""))
    sex = pt.get("gender", "unknown").capitalize()
    dob = pt.get("birthDate", "")
    return {"id": patient_id, "name": name, "age": age, "sex": sex, "dob": dob}


def _extract_name(pt: dict[str, Any]) -> str:
    for name_entry in pt.get("name", []):
        given = " ".join(name_entry.get("given", []))
        family = name_entry.get("family", "")
        if given or family:
            return f"{given} {family}".strip()
    return f"Patient {pt.get('id', '')}"


def _calculate_age(birth_date: str) -> int:
    if not birth_date:
        return 0
    try:
        dob = datetime.date.fromisoformat(birth_date[:10])
        today = datetime.date.today()
        return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    except ValueError:
        return 0


def _code_display(codeable: dict[str, Any]) -> str:
    if text := codeable.get("text"):
        return text
    for coding in codeable.get("coding", []):
        if display := coding.get("display"):
            return display
        if code := coding.get("code"):
            return code
    return ""


def _format_conditions(resources: list[dict]) -> list[str]:
    lines = []
    for r in resources:
        display = _code_display(r.get("code", {}))
        onset = (r.get("onsetDateTime") or r.get("recordedDate") or "")[:10]
        if display:
            lines.append(display + (f" (since {onset})" if onset else ""))
    return lines or ["None documented"]


def _format_medications(resources: list[dict]) -> list[str]:
    lines = []
    for r in resources:
        med = _code_display(
            r.get("medicationCodeableConcept")
            or r.get("medication", {}).get("concept", {})
            or {}
        )
        if med:
            lines.append(med)
    return lines or ["None documented"]


def _format_labs(resources: list[dict]) -> list[str]:
    lines = []
    for r in resources[:15]:
        code = _code_display(r.get("code", {}))
        qty = r.get("valueQuantity", {})
        value_str = (
            f"{qty.get('value', '')} {qty.get('unit', '')}".strip()
            if qty
            else r.get("valueString", "")
        )
        date = (r.get("effectiveDateTime") or "")[:10]
        if code and value_str:
            lines.append(f"{code}: {value_str}" + (f" ({date})" if date else ""))
    return lines or ["None documented"]


def _format_procedures(resources: list[dict]) -> list[str]:
    lines = []
    for r in resources[:10]:
        code = _code_display(r.get("code", {}))
        date = (
            (r.get("performedDateTime") or r.get("performedPeriod", {}).get("start") or "")[:10]
        )
        if code:
            lines.append(code + (f" ({date})" if date else ""))
    return lines or ["None documented"]


def _bullet_list(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items)

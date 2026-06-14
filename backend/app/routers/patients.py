from fastapi import APIRouter, HTTPException, Query

from app.services import patient_service

router = APIRouter(tags=["patients"])


@router.get("/patients")
def list_patients(name: str | None = Query(default=None, description="Search by name")):
    try:
        return patient_service.search_patients(name=name)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"FHIR error: {exc}") from exc


@router.get("/patients/{patient_id}")
def get_patient(patient_id: str):
    try:
        return patient_service.get_patient(patient_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"FHIR error: {exc}") from exc


@router.get("/patients/{patient_id}/profile")
def get_patient_profile(patient_id: str):
    """Return the raw text profile that will be sent to the Foundry Agent."""
    try:
        profile = patient_service.build_patient_profile(patient_id)
        return {"patient_id": patient_id, "profile": profile}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"FHIR error: {exc}") from exc

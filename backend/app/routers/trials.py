from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services import trial_matching_service

router = APIRouter(tags=["trials"])


@router.post("/patients/{patient_id}/match-trials")
def match_trials(patient_id: str):
    """
    Run the Foundry Agent against the patient's FHIR profile.
    Returns eligibility verdicts with citations and the thread_id for follow-up chat.
    """
    try:
        return trial_matching_service.match_trials(patient_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {exc}") from exc


class ChatRequest(BaseModel):
    thread_id: str
    message: str


@router.post("/chat")
def chat(body: ChatRequest):
    """
    Send a follow-up message to an existing Foundry Agent thread.
    The agent retains full context from the initial match and all prior turns.
    """
    try:
        return trial_matching_service.send_chat_message(body.thread_id, body.message)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {exc}") from exc

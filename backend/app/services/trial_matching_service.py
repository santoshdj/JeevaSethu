"""
Trial Matching Service — sends a patient profile to the Foundry Agent Service
(with Foundry IQ knowledge base attached) and returns structured match results.

The Foundry Agent is created once in the Azure AI Foundry portal:
  1. Agents tab → Create agent
  2. Add system prompt (see AGENT_SYSTEM_PROMPT below for reference)
  3. Attach Foundry IQ knowledge base (indexed ClinicalTrials.gov documents)
  4. Copy the agent ID → AZURE_AGENT_ID env var

The agent handles query decomposition, parallel retrieval from Foundry IQ,
reranking, and citation attachment automatically.
"""

import logging

from azure.ai.agents import AgentsClient
from azure.ai.agents.models import (
    AgentThreadCreationOptions,
    MessageRole,
    ThreadMessageOptions,
)
from azure.identity import DefaultAzureCredential

from app.config import settings
from app.services import patient_service

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Reference system prompt — paste this into the Foundry portal when creating
# the agent (Agents tab → Instructions field).
# ---------------------------------------------------------------------------
AGENT_SYSTEM_PROMPT = """
You are a clinical trial matching assistant for oncology. Your job is to match a cancer patient
to recruiting clinical trials from the knowledge base and assess their eligibility.

When given a patient profile, you must:
1. Search the knowledge base for trials relevant to the patient's cancer type, stage, and treatment history.
2. Return the top 5–10 most relevant recruiting trials.
3. For each trial provide:
   - Trial name and NCT ID
   - Eligibility verdict: ELIGIBLE ✅, PARTIAL ⚠️, or INELIGIBLE ❌
   - 2–3 sentences explaining the verdict, citing specific patient data points
   - Key inclusion criteria the patient meets
   - Key exclusion criteria that may disqualify the patient (if any)
   - Trial location(s) and phase

Format each trial as a clearly separated section. Be precise and grounded — only use
information present in the patient profile and the retrieved trial documents.
Always cite the source trial document for each recommendation.
""".strip()

# ---------------------------------------------------------------------------
# User message template
# ---------------------------------------------------------------------------
_USER_TEMPLATE = """{profile}

---
Based on this patient profile, search the clinical trials knowledge base and provide
eligibility assessments for the top matching recruiting oncology trials.
For each trial include: trial name, NCT ID, eligibility verdict (ELIGIBLE/PARTIAL/INELIGIBLE),
reasoning grounded in the patient data, and a citation to the source document.
"""


def match_trials(patient_id: str) -> dict:
    """
    Build a patient profile from FHIR, call the Foundry Agent, and return
    the agent's response with inline citations.

    Returns:
        {
            "patient_id": str,
            "patient_name": str,
            "response": str,          # full agent response text
            "citations": [            # source documents cited by the agent
                {"title": str, "url": str}
            ]
        }
    """
    # 1. Build structured patient profile from FHIR
    profile = patient_service.build_patient_profile(patient_id)
    patient_info = patient_service.get_patient(patient_id)

    # 2. Call Foundry Agent Service
    client = AgentsClient(
        endpoint=settings.azure_project_endpoint,
        credential=DefaultAzureCredential(),
    )

    thread_run = client.create_thread_and_process_run(
        agent_id=settings.azure_agent_id,
        thread=AgentThreadCreationOptions(
            messages=[
                ThreadMessageOptions(
                    role=MessageRole.USER,
                    content=_USER_TEMPLATE.format(profile=profile),
                )
            ]
        ),
    )
    logger.info("Agent run %s on thread %s for patient %s", thread_run.id, thread_run.thread_id, patient_id)

    if thread_run.status == "failed":
        error_detail = getattr(thread_run, "last_error", "unknown error")
        logger.error("Agent run failed for patient %s: %s", patient_id, error_detail)
        raise RuntimeError(f"Agent run failed: {error_detail}")

    # 3. Extract response and citations
    last_msg = client.messages.get_last_message_by_role(
        thread_run.thread_id, MessageRole.AGENT
    )
    response_text = ""
    citations: list[dict] = []

    if last_msg:
        for text_block in last_msg.text_messages:
            response_text = text_block.text.value
            break
        for ann in last_msg.url_citation_annotations:
            citations.append(
                {
                    "title": getattr(ann.url_citation, "title", ""),
                    "url": getattr(ann.url_citation, "url", ""),
                }
            )
        for ann in last_msg.file_citation_annotations:
            citations.append(
                {
                    "title": getattr(ann, "text", "Source document"),
                    "url": "",
                }
            )

    # Deduplicate citations by URL
    seen: set[str] = set()
    unique_citations: list[dict] = []
    for c in citations:
        key = c.get("url") or c.get("title", "")
        if key and key not in seen:
            seen.add(key)
            unique_citations.append(c)

    return {
        "patient_id": patient_id,
        "patient_name": patient_info["name"],
        "thread_id": thread_run.thread_id,
        "response": response_text,
        "citations": unique_citations,
    }


def send_chat_message(thread_id: str, message: str) -> dict:
    """
    Send a follow-up message to an existing Foundry Agent thread.
    The agent retains full context from the initial match and all prior turns.

    Returns:
        { "response": str, "citations": [{"title": str, "url": str}] }
    """
    client = AgentsClient(
        endpoint=settings.azure_project_endpoint,
        credential=DefaultAzureCredential(),
    )

    run = client.runs.create_and_process(
        thread_id=thread_id,
        agent_id=settings.azure_agent_id,
        additional_messages=[
            ThreadMessageOptions(role=MessageRole.USER, content=message)
        ],
    )

    if run.status == "failed":
        error_detail = getattr(run, "last_error", "unknown error")
        logger.error("Follow-up run failed on thread %s: %s", thread_id, error_detail)
        raise RuntimeError(f"Agent run failed: {error_detail}")

    last_msg = client.messages.get_last_message_by_role(
        thread_id, MessageRole.AGENT
    )
    response_text = ""
    citations: list[dict] = []

    if last_msg:
        for text_block in last_msg.text_messages:
            response_text = text_block.text.value
            break
        for ann in last_msg.url_citation_annotations:
            citations.append(
                {
                    "title": getattr(ann.url_citation, "title", ""),
                    "url": getattr(ann.url_citation, "url", ""),
                }
            )
        for ann in last_msg.file_citation_annotations:
            citations.append(
                {
                    "title": getattr(ann, "text", "Source document"),
                    "url": "",
                }
            )

    seen: set[str] = set()
    unique_citations: list[dict] = []
    for c in citations:
        key = c.get("url") or c.get("title", "")
        if key and key not in seen:
            seen.add(key)
            unique_citations.append(c)

    return {"response": response_text, "citations": unique_citations}

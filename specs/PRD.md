# PRD: Clinical Trial Matcher — AI-Assisted Oncology Trial Matching

**Date:** 2026-06-11
**Status:** Accepted
**Author:** Product owner (via design interview, 2026-06-11)

---

## Problem Statement

Oncology clinicians spend significant time manually searching ClinicalTrials.gov to find
recruiting trials that match a specific patient's profile — cancer type, stage, prior
treatments, age, biomarkers, and organ function. This process is slow, error-prone, and
typically not performed during the encounter due to time constraints. As a result, eligible
patients are frequently not offered trials, and clinicians lack a fast way to surface
relevant options from a corpus of tens of thousands of active trials.

---

## Solution

A clinician-facing web application that retrieves a cancer patient's clinical profile from
a FHIR server and runs it through an Azure AI Foundry Agent connected to a Foundry IQ
knowledge base of indexed ClinicalTrials.gov documents. The agent returns eligibility
verdicts (ELIGIBLE / PARTIAL / INELIGIBLE) with per-verdict reasoning and citations to the
source trial documents — in a single button click, during the encounter.

---

## User Stories

### Patients Page

1. As a clinician, I want to see a list of all cancer patients from the FHIR server when I open the app, so that I can quickly find the patient I'm seeing.
2. As a clinician, I want to search patients by name, so that I can find a specific patient without scrolling through a long list.
3. As a clinician, I want to clear my search and return to the full patient list, so that I can switch between patients quickly.
4. As a clinician, I want each patient row to show name, age, sex, and date of birth, so that I can confirm I have the right patient before running a match.
5. As a clinician, I want to click a patient row to navigate to their Trial Match Page, so that the workflow is a single click.
6. As a clinician, I want a visible "Find trials →" affordance on each row, so that the action is discoverable without instructions.
7. As a clinician, I want to see a loading state while the patient list is fetching, so that I know the app is working.
8. As a clinician, I want to see a clear error message if the FHIR server is unavailable, so that I understand why no patients are showing.

### Trial Match Page — Patient Identity

9. As a clinician, I want to see the selected patient's name, age, sex, and DOB at the top of the Trial Match Page, so that I can confirm I'm looking at the right patient.
10. As a clinician, I want a "Back to patients" link, so that I can return to the patient list without using the browser's back button.
11. As a clinician, I want to see the patient's FHIR ID displayed, so that I can cross-reference with external systems if needed.

### Trial Match Page — Running a Match

12. As a clinician, I want a clearly labelled "Find Matching Trials" button, so that the action is unambiguous.
13. As a clinician, I want to see a loading spinner with a descriptive message while the Foundry Agent is running, so that I understand why the page is not responding.
14. As a clinician, I want to know that the match may take 15–30 seconds, so that I don't assume the app has frozen.
15. As a clinician, I want to see an error message if the agent call fails, so that I can retry or escalate.
16. As a clinician, I want to re-run the match after viewing results, so that I can get a fresh response if needed.

### Trial Match Page — Results

17. As a clinician, I want to see the Foundry Agent's full response rendered clearly, so that I can read the eligibility assessments without visual noise.
18. As a clinician, I want eligibility verdicts (ELIGIBLE ✅ / PARTIAL ⚠️ / INELIGIBLE ❌) to be visually distinct, so that I can scan results at a glance.
19. As a clinician, I want each trial result to include the trial name and NCT ID, so that I can look it up on ClinicalTrials.gov.
20. As a clinician, I want each trial result to include 2–3 sentences of reasoning grounded in my patient's specific data, so that I understand why the verdict was reached.
21. As a clinician, I want to see which eligibility criteria the patient meets, so that I can validate the agent's assessment.
22. As a clinician, I want to see any exclusion criteria that may disqualify the patient, so that I can decide whether to pursue the trial.
23. As a clinician, I want to see the trial's phase and location, so that I can assess feasibility for the patient.
24. As a clinician, I want the top 5–10 most relevant trials returned (not all matching trials), so that results are actionable and not overwhelming.

### Citations

25. As a clinician, I want to see a numbered list of source citations below the agent response, so that I can verify the information.
26. As a clinician, I want each citation to link directly to the trial on ClinicalTrials.gov, so that I can review the full protocol.
27. As a clinician, I want citations to be deduplicated, so that the same trial does not appear multiple times.
28. As a clinician, I want to understand that the agent's verdicts are grounded in the indexed trial documents, so that I trust the source of the information.

### Patient Profile (FHIR Extraction)

29. As a clinician, I want the app to automatically extract the patient's active cancer diagnoses from the FHIR server, so that I don't have to enter them manually.
30. As a clinician, I want the app to extract current medications (including chemotherapy and targeted therapy), so that the agent knows what the patient is already receiving.
31. As a clinician, I want recent laboratory results (tumor markers, CBC, metabolic panel) included in the match, so that the agent can assess functional eligibility criteria.
32. As a clinician, I want prior procedures and treatments included, so that the agent can assess prior therapy lines and exclusion criteria based on treatment history.
33. As a clinician, I want patient age and biological sex included, so that age range and sex eligibility criteria are evaluated correctly.

### Trial Seed (Offline / Admin)

34. As a developer, I want a standalone seed script that fetches recruiting oncology trials from ClinicalTrials.gov and uploads them to Azure Blob Storage, so that Foundry IQ has a current corpus to index.
35. As a developer, I want the seed to be capped at 5,000 trials by default, so that seed time and storage costs are bounded.
36. As a developer, I want the seed to filter for recruiting trials only, so that the agent does not suggest closed or completed trials.
37. As a developer, I want each trial document to include the full eligibility criteria text, so that the agent has the raw criteria available for reasoning.
38. As a developer, I want clear next-step instructions printed after seeding, so that I know how to configure Foundry IQ in the portal.
39. As a developer, I want the seed to handle API pagination automatically, so that all matching trials are captured regardless of total count.

---

## Implementation Decisions

### Modules

**`fhir_client`** — Thin httpx wrapper. Exposes `get_resource(path)` and `search(resource_type, params)`. Returns raw FHIR JSON dicts. Stateless, no caching. This is a deep module: a simple interface over network I/O.

**`patient_service`** — FHIR domain logic. Owns `search_patients`, `get_patient`, and `build_patient_profile`. Extracts and formats Conditions, MedicationRequests, Observations (lab category), and Procedures into a plain-text Patient Profile. All FHIR JSON parsing lives here — no FHIR structures leak into routers or the matching service.

**`trial_matching_service`** — Foundry Agent caller. Owns the full lifecycle: create thread → create message → run agent → extract response text → extract and deduplicate citations. Returns a `MatchResult` dict. All `azure-ai-projects` SDK usage lives here — no SDK imports elsewhere.

**`patients` router** — `GET /api/patients`, `GET /api/patients/{id}`, `GET /api/patients/{id}/profile`. Thin delegation to `patient_service`. No business logic.

**`trials` router** — `POST /api/patients/{id}/match-trials`. Thin delegation to `trial_matching_service`. Returns the `MatchResult` dict directly.

**`seed_trials.py`** (offline script) — Standalone; not part of the FastAPI app. Fetches, converts, and uploads. No shared imports with the backend app.

### API Contracts

`POST /api/patients/{patient_id}/match-trials`
- Request: no body
- Response:
  ```
  {
    patient_id: string,
    patient_name: string,
    response: string,        // full agent response text (markdown)
    citations: [
      { title: string, url: string }
    ]
  }
  ```

`GET /api/patients`
- Query params: `name` (optional, partial match)
- Response: `[{ id, name, age, sex, dob }]`

### Foundry Agent Configuration (portal-side, not in code)

- Model: GPT-4o
- Knowledge base: Foundry IQ instance pointed at the Blob Storage container
- System prompt: instructs the agent to return top 5–10 recruiting trials with ELIGIBLE / PARTIAL / INELIGIBLE verdict, 2–3 sentence reasoning, inclusion/exclusion criteria assessment, and citations
- Agent ID captured once → `AZURE_AGENT_ID` env var

### Patient Profile Format

Plain text, structured with labelled sections:
```
PATIENT PROFILE FOR CLINICAL TRIAL MATCHING

Demographics:
- Name, Age, Biological Sex

Active Diagnoses / Cancer Conditions:
- <condition> (since <date>)

Current Medications:
- <medication>

Recent Laboratory Results:
- <code>: <value> <unit> (<date>)

Prior Procedures and Treatments:
- <procedure> (<date>)
```

### Environment Variables

| Variable | Purpose |
|---|---|
| `FHIR_BASE_URL` | FHIR server base URL |
| `FHIR_AUTH_TOKEN` | Optional bearer token for FHIR auth |
| `AZURE_PROJECT_ENDPOINT` | Azure AI Foundry project endpoint |
| `AZURE_API_KEY` | Azure AI Foundry API key |
| `AZURE_AGENT_ID` | Foundry Agent ID (created in portal) |
| `ALLOWED_ORIGINS` | Comma-separated CORS origins |
| `AZURE_STORAGE_CONNECTION_STRING` | Blob Storage (seed script only) |
| `AZURE_BLOB_CONTAINER` | Blob container name (seed script only) |

---

## Testing Decisions

### What makes a good test

Tests should assert on observable output given controlled input — not on internal implementation details (which SDK method was called, how many loops ran, etc.). A good test for `patient_service.build_patient_profile` provides a mock FHIR bundle and asserts on the output string content. A good test for `trial_matching_service.match_trials` mocks the `AIProjectClient` and asserts on the returned `MatchResult` shape.

### Modules to test

| Module | What to test |
|---|---|
| `patient_service` | `build_patient_profile` — given a FHIR Patient + Condition + MedicationRequest + Observation bundle, assert the profile text contains expected name, age, condition names, medication names, lab values, and procedure names. Test edge cases: missing `birthDate`, empty medication list, no labs. |
| `patient_service` | `search_patients` — given a FHIR Bundle with multiple entries, assert the returned list shape (id, name, age, sex, dob). |
| `fhir_client` | `bundle_entries` — given a raw Bundle dict, assert correct entry extraction including missing-entry edge cases. |
| `trial_matching_service` | `match_trials` — mock `AIProjectClient`, assert correct thread creation, message content contains patient profile, response text and citations are extracted and returned correctly. Test the deduplication logic for citations. |
| `patients` router | Integration test via FastAPI `TestClient` — mock `patient_service`, assert correct HTTP status and response shape. |
| `trials` router | Integration test via FastAPI `TestClient` — mock `trial_matching_service`, assert correct HTTP status and `MatchResult` shape. |

### Prior art

The Patient Management App (`backend/tests/`) contains comparable FastAPI `TestClient`-based router tests and service unit tests using `pytest` + `unittest.mock.patch`. The same pattern applies here.

---

## Out of Scope

- **Authentication and access control** — no login, roles, or patient scoping. Demo only. See ADR-0004.
- **Saving or persisting Trial Matches** — results are ephemeral; no FHIR write-back, no local DB
- **Scheduled trial data refresh** — Foundry IQ indexer can be re-run manually; no automated pipeline
- **Patient record editing** — the app is read-only against the FHIR server
- **Sending trial referrals** — no integration with trial coordinator systems or patient communication tools
- **Multi-tenant / multi-clinician scoping** — all patients visible to all users in demo
- **Batch matching** — match runs one patient at a time; no bulk export
- **Mobile layout** — desktop browser only for the demo
- **Audit logging** — no AuditEvent FHIR writes; not required for synthetic data demo

---

## Further Notes

- The Foundry Agent system prompt (in `trial_matching_service.py` as `AGENT_SYSTEM_PROMPT`) must be pasted into the Foundry portal when creating the agent. If the agent is recreated, a new `AZURE_AGENT_ID` must be set in `.env`.
- The seed script can be run multiple times safely — blob uploads use `overwrite=True`. Re-running the seed does not automatically re-index Foundry IQ; the indexer must be triggered manually in the portal after each seed run.
- Foundry IQ agentic retrieval uses an optional LLM for query planning. This is separate from the Foundry Agent model (GPT-4o) and is configured within Foundry IQ's retrieval settings (retrieval reasoning effort: minimal / low / medium).
- The `azure-ai-projects` SDK (version `>=1.0.0b11`) is in preview as of this PRD. Breaking changes in agent thread and message APIs are possible; pin to a specific version when stabilising for production.

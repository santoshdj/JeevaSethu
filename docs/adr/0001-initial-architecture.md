# ADR 0001: Initial Architecture — Clinical Trial Matcher

**Date:** 2026-06-11
**Status:** Accepted
**Deciders:** Product owner (via design interview, 2026-06-11)

---

## Context

The Clinical Trial Matcher is a greenfield application. All foundational architectural decisions
were made during a structured design interview prior to any code being written. This ADR records
the full set of decisions so that future contributors understand the reasoning behind the
initial structure.

---

## Decisions

### 1. Target User: Oncology Clinician

**Decision:** The primary user is an oncology clinician who selects a cancer patient and wants
to see which recruiting clinical trials that patient may be eligible for.

**Rationale:** Clinicians have the clinical context to interpret eligibility verdicts and act
on them (discussing with the patient, referring to a trial coordinator). Patient self-service
matching was considered but deferred — patients without clinical context may misinterpret
partial eligibility signals.

---

### 2. Patient Data Source: FHIR Server

**Decision:** All patient data is sourced from a FHIR R4-compliant server containing synthetic
cancer patient records. The app reads from the FHIR server and never writes to it.

**Rationale:** FHIR R4 is the mandated interoperability standard under the 21st Century Cures
Act. Building against FHIR from the start ensures the integration path to real EHRs (Epic,
Cerner, Athena) is a configuration change, not a rewrite. Synthetic data eliminates PHI
concerns during development.

---

### 3. App Stack: FastAPI (Python) + React (TypeScript)

**Decision:** The backend is FastAPI + Uvicorn. The frontend is React 18 + TypeScript + Vite +
Tailwind CSS + React Query. This mirrors the stack used in the companion Patient Management App.

**Rationale:** Reusing a proven stack reduces bootstrap time and cognitive load. The Python
backend aligns with the `azure-ai-projects` SDK which is Python-first. The FHIR client code
and patterns (httpx, pydantic-settings, bundle entry extraction) are directly reusable.

---

### 4. Single Page per Workflow Step

**Decision:** The app has exactly two pages:
1. **Patients Page** — searchable list of all FHIR patients
2. **Trial Match Page** — patient identity + "Find Matching Trials" button + results

**Rationale:** The matching workflow is linear: pick a patient → run match → review results.
A multi-page or tabbed layout would add navigation overhead without benefit for a linear flow.

---

### 5. Backend as Thin Orchestrator

**Decision:** The FastAPI backend owns two responsibilities only: (1) fetching FHIR data and
assembling the Patient Profile, and (2) calling the Foundry Agent Service and returning the
response. No business logic, no persistence, no trial data storage.

**Rationale:** Clinical trial data lives in Foundry IQ (Azure AI Search). Patient data lives
in the FHIR server. The backend is stateless and horizontally scalable. Keeping it thin reduces
the surface area for bugs and makes each layer independently replaceable.

---

## Consequences

- `backend/` contains FastAPI app with two routers: `patients` and `trials`
- `frontend/` contains React SPA with two pages: `PatientsPage` and `TrialMatchPage`
- No database, no session store, no queue — stateless by design
- Swapping the FHIR server requires only changing `FHIR_BASE_URL` in `.env`
- Swapping the AI provider requires changing the `trial_matching_service` and env vars

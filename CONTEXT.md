# Clinical Trial Matcher — Domain Glossary

**Product focus:** AI-assisted clinical trial matching for oncology patients. A clinician selects a cancer patient, and the app uses Azure AI Foundry (GPT-4o + Foundry IQ) to assess the patient's eligibility against recruiting trials sourced from ClinicalTrials.gov.

This file defines the canonical terms used across the codebase and documentation.
Update here first; code naming follows this glossary.

---

## Patient Profile

A structured plain-text document generated from a patient's FHIR data at match time. Contains demographics (name, age, biological sex), active cancer diagnoses, current medications (including chemotherapy and targeted therapy), recent laboratory results (tumor markers, CBC, metabolic panel), and prior procedures and treatments. The Patient Profile is the sole input sent to the Foundry Agent — no raw FHIR resources are transmitted.

## Clinical Trial

A recruiting oncology study sourced from ClinicalTrials.gov and indexed into the Foundry IQ knowledge base. Each Clinical Trial document contains: NCT ID, title, phase, sponsor, conditions, interventions, age range, sex eligibility, locations, a plain-language summary, and the full eligibility criteria text. Clinical Trials are never stored in the app's own database — they exist only as indexed documents in Foundry IQ.

## NCT ID

The unique identifier assigned by ClinicalTrials.gov to each Clinical Trial (format: `NCT` followed by 8 digits, e.g. `NCT04613505`). Used as the blob file name (`NCT04613505.txt`) and the primary reference in agent responses and citations.

## Trial Match

The result of running the Foundry Agent against a Patient Profile. A Trial Match consists of the agent's full response text and a list of Citations. A Trial Match is ephemeral — it is never saved or persisted; it exists only for the duration of the page session.

## Eligibility Verdict

A per-trial judgement returned by the Foundry Agent within a Trial Match. Three values:
- **ELIGIBLE ✅** — patient meets the key inclusion criteria and no disqualifying exclusion criteria are identified
- **PARTIAL ⚠️** — patient meets some criteria but has one or more factors that may require protocol review
- **INELIGIBLE ❌** — patient is excluded by one or more hard exclusion criteria (e.g. prior treatment type, age, organ function)

The Eligibility Verdict is a clinical decision-support signal, not a medical determination. The clinician is responsible for final eligibility assessment.

## Foundry Agent

The GPT-4o agent deployed in Azure AI Foundry Agent Service with the Foundry IQ knowledge base attached. Receives a Patient Profile as a user message and returns Eligibility Verdicts with Citations. The Foundry Agent is created once in the Azure AI Foundry portal (Agents tab); its agent ID is injected via the `AZURE_AGENT_ID` environment variable.

## Foundry IQ

The managed knowledge base in Azure AI Foundry backed by Azure AI Search. Contains indexed Clinical Trial documents sourced from Azure Blob Storage. Uses agentic retrieval — multi-query decomposition, parallel search, semantic reranking — to return grounded answers with Citations. Multiple agents can share the same Foundry IQ knowledge base.

## Agentic Retrieval

Foundry IQ's internal query pipeline. When the Foundry Agent queries Foundry IQ with a Patient Profile, agentic retrieval decomposes the query into subqueries (by cancer type, age, prior treatments, biomarkers, etc.), executes them in parallel across indexed Clinical Trial documents, semantically reranks results, and returns unified responses with Citations.

## Citation

A source reference attached to a Trial Match response by the Foundry Agent, pointing to the indexed Clinical Trial document that grounded a specific claim. Displayed to the clinician as a numbered footnote list below the agent response. Each Citation has a title and a URL back to the trial on ClinicalTrials.gov.

## Knowledge Source

A connection configured in Foundry IQ pointing to a data store. In this app, the Knowledge Source is the Azure Blob Storage container populated by the Trial Seed script. Foundry IQ indexes all `.txt` files in the container.

## Trial Seed

The one-time offline process that populates Foundry IQ with Clinical Trial data. The seed script (`scripts/seed_trials.py`) fetches recruiting oncology trials from the ClinicalTrials.gov v2 API (capped at 5,000 trials), converts each to a plain-text document, and uploads to Azure Blob Storage. After uploading, the Foundry IQ indexer runs once in the portal to index the documents. The Trial Seed is a prerequisite for the app to function — no trials are matched until it has been run.

## Trial Match Page

The per-patient view reached by clicking a patient on the Patients Page. Shows the patient's identity (name, age, sex), a "Find Matching Trials" button, and — after the Foundry Agent responds — the full Eligibility Verdict response and Citation list. A single page session produces at most one Trial Match; the clinician can trigger a re-run manually.

## Patients Page

The landing page of the app. Displays all cancer patients from the FHIR server in a searchable table. The clinician searches by name and clicks a patient row to navigate to the Trial Match Page.

## Demo Clinician

The fixed identity used in place of authentication for the demo app: **Dr. Sarah Chen**. Displayed in the navigation bar. There is no login flow — all patients from the FHIR server are visible to the Demo Clinician. The Demo Clinician concept will be replaced by real authentication if the app moves beyond demo use.

## FHIR Server

The external FHIR R4-compliant server that stores synthetic cancer patient data. The app reads from it (never writes). The base URL is injected via `FHIR_BASE_URL`. In the demo configuration this is a synthetic sandbox; in production it would be replaced by an institution's EHR FHIR endpoint.

## Trial Chat

A multi-turn conversation between the clinician and the Foundry Agent that begins after the initial Trial Match completes. The agent retains the full patient profile and all prior trial results in its thread context — the clinician does not need to re-state the patient's situation. Each Follow-up Message in a Trial Chat is grounded in the same Foundry IQ knowledge base as the initial match, and the agent returns citations for any new claims it makes. Trial Chat history is session-scoped: it resets when the clinician navigates away or clicks "Run again".

## Follow-up Message

A clinician-authored question or instruction sent to the Foundry Agent after the initial Trial Match, within the same agent thread. Examples: "Which of these trials has the fewest required visits?", "Are there any trials near Boston?", "What would change if the patient stopped current chemotherapy?". Each Follow-up Message adds one user turn and one agent turn to the Trial Chat history. Follow-up Messages are sent to `POST /api/chat` with the `thread_id` from the initial match.

## Referral Packet

A structured plain-text document generated on-demand by the clinician from a single Eligibility Verdict within a Trial Match, intended to be sent to a Trial Coordinator. Scoped to one trial — a separate Referral Packet is generated per trial. Shown only for ELIGIBLE ✅ and PARTIAL ⚠️ verdicts; INELIGIBLE trials do not produce a Referral Packet. Contains: patient demographics (name, age, sex, DOB), primary diagnosis (first 1–3 active conditions from the Patient Profile), key laboratory values (3 most recent labs from the Patient Profile), the NCT ID and trial title, the Eligibility Verdict, and the agent's full per-trial assessment text. Delivery: the clinician copies formatted plain text to clipboard via a "Copy Referral Packet" button and pastes it into their own communication channel. The Referral Packet is never stored server-side; it is assembled entirely in the browser from session data.

## Trial Coordinator

The person at a clinical trial site (or institution) responsible for screening patients and managing trial enrolment. The recipient of a Referral Packet. Not modelled as a user of this app — the app has no coordinator accounts or email infrastructure; the clinician is responsible for obtaining the coordinator's contact details and transmitting the Referral Packet independently.

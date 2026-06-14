# ADR 0003: ClinicalTrials.gov as Trial Data Source (One-Time Seed)

**Date:** 2026-06-11
**Status:** Accepted
**Deciders:** Product owner (via design interview, 2026-06-11)
**Relates to:** ADR-0002 (Foundry IQ)

---

## Context

Foundry IQ needs clinical trial documents to index. This ADR records the source of those
documents and the ingestion approach.

---

## Decisions

### 1. Trial Data Source: ClinicalTrials.gov v2 API

**Decision:** All clinical trial documents are sourced from the ClinicalTrials.gov v2 REST API
(`https://clinicaltrials.gov/api/v2/studies`), filtered to recruiting oncology trials.

**Filter applied:**
- `query.cond`: cancer | oncology | tumor | neoplasm | carcinoma | lymphoma | leukemia | melanoma | sarcoma | glioma
- `filter.overallStatus`: RECRUITING
- Cap: 5,000 trials

**Alternatives rejected:**
- **Custom curated dataset**: Would require ongoing manual curation, has no authoritative
  coverage, and adds maintenance burden with no benefit for a demo.
- **Commercial trial databases (e.g. Citeline, Informa)**: Require licensing, not appropriate
  for an open demo app.

**Rationale:** ClinicalTrials.gov is the authoritative, free, and comprehensive registry of
clinical trials (500k+ total, ~50k active oncology trials). Its v2 API returns structured
JSON with eligibility criteria, age ranges, conditions, interventions, and locations — all
the fields needed for matching.

---

### 2. Ingestion Pattern: One-Time Seed Script (not scheduled pipeline)

**Decision:** Trial documents are ingested by a single Python script (`scripts/seed_trials.py`)
run once manually. No scheduled pipeline, no event-driven refresh.

**Rationale:** Foundry IQ supports native scheduled indexer runs configurable in the portal
without application code changes. Building a scheduling pipeline (GitHub Actions timer, Azure
Functions) before the core matching feature works adds infrastructure risk without
demonstrable value. The scheduled refresh is a one-line portal configuration when needed.

---

### 3. Document Format: Plain Text (not JSON or JSONL)

**Decision:** Each trial is converted to a plain-text `.txt` file before upload to Blob
Storage. The document preserves all matching-relevant fields as human-readable prose.

**Document structure:**
```
Clinical Trial: <title>
NCT ID: <id>
URL: https://clinicaltrials.gov/study/<id>
Phase: <phase>
Conditions: <conditions>
Interventions: <interventions>
Age Range: <min> to <max>
Sex Eligibility: <sex>
Locations: <locations>
Summary: <brief summary>
Eligibility Criteria: <full eligibility text>
```

**Rationale:** Plain text is natively supported by Foundry IQ's chunking and embedding
pipeline without schema configuration. The full eligibility criteria text (typically 500–2000
words) is preserved verbatim — this is what the agent needs to reason against patient data.
JSON would require schema mapping in Foundry IQ and would not improve retrieval quality.

---

### 4. Blob Storage as Intermediary

**Decision:** Converted trial documents are uploaded to Azure Blob Storage, and Foundry IQ is
pointed at that container as its Knowledge Source. The script does not call Foundry IQ APIs
directly.

**Rationale:** Blob Storage is the recommended Knowledge Source type for Foundry IQ with
custom document sets. It decouples the ingestion script from the Foundry IQ configuration —
the container can be re-indexed without re-running the fetch script, and the fetch can be
re-run without reconfiguring Foundry IQ.

---

## Consequences

- `scripts/seed_trials.py` is a standalone script (not part of the FastAPI app)
- Requires `AZURE_STORAGE_CONNECTION_STRING` and `AZURE_BLOB_CONTAINER` env vars at seed time
- After seeding, the Foundry IQ indexer must be run once in the portal
- Trial data freshness is manual — a re-seed + re-index is required to pick up new trials
- The blob container name is the only coupling point between the seed script and Foundry IQ

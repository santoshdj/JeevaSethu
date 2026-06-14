# ADR 0002: Foundry IQ as the Clinical Trial Knowledge Base

**Date:** 2026-06-11
**Status:** Accepted
**Deciders:** Product owner (via design interview, 2026-06-11)
**Relates to:** ADR-0001 (Initial Architecture), ADR-0003 (Data Source)

---

## Context

The matching engine needs a knowledge base of clinical trials to search against. The key
decisions are: what managed service powers the knowledge base, and how the Foundry Agent
queries it.

---

## Decisions

### 1. Knowledge Base: Foundry IQ (not bare Azure AI Search)

**Decision:** Foundry IQ — the managed knowledge layer in Azure AI Foundry backed by Azure AI
Search — is the knowledge base. It is configured in the Foundry portal (Build → Knowledge tab)
and attached directly to the Foundry Agent.

**Alternatives rejected:**
- **Bare Azure AI Search**: Would require building the retrieval orchestration manually
  (chunking, embedding, query decomposition, reranking, citation attachment). Foundry IQ
  provides all of this out of the box.
- **External vector database (Pinecone, Weaviate)**: Introduces a non-Azure dependency with
  no native Foundry integration; requires more infrastructure to manage.

**Rationale:** Foundry IQ's agentic retrieval (multi-query decomposition, parallel search,
semantic reranking, citation attachment) is precisely what clinical trial matching requires.
A patient profile maps to many independent subqueries (cancer type, age, prior treatments,
biomarkers) — agentic retrieval handles this natively without custom orchestration code.

---

### 2. Agent Runtime: Foundry Agent Service (managed)

**Decision:** The Foundry Agent is created and hosted in Foundry Agent Service (Azure AI
Foundry portal → Agents tab). The backend calls it via the `azure-ai-projects` SDK. The
knowledge base attachment, thread management, and retrieval orchestration are managed by
Azure — not by application code.

**Alternatives rejected:**
- **Custom agent (code-first)**: Building the retrieve → augment → generate loop manually
  would replicate functionality that Foundry Agent Service provides natively (thread
  management, tool routing, citation formatting, parallel retrieval). Estimated additional
  complexity: 2–3 weeks.

---

### 3. Agent Model: GPT-4o

**Decision:** The Foundry Agent uses GPT-4o as the underlying model.

**Rationale:** Action Recommendations (the most demanding task) sends a multi-field patient
profile and must assess eligibility against complex clinical criteria with multiple logical
conditions. GPT-4o has the strongest instruction-following and structured reasoning of the
available Foundry catalog models. GPT-4o-mini was considered but rejected for complex
multi-field eligibility assessment.

---

### 4. Citation Output: Required

**Decision:** The Foundry Agent must return citations for every eligibility claim. Citations
are extracted from the agent response annotations and displayed as a numbered source list
below the response.

**Rationale:** Clinicians need to verify AI claims. A verdict of "ELIGIBLE ✅" without a
traceable source to the specific trial document is unacceptable in a clinical context. Foundry
IQ's citation attachment is the primary mechanism for grounding the agent's responses.

---

## Consequences

- One Foundry IQ knowledge base created per Foundry project
- Knowledge base knowledge source: Azure Blob Storage container populated by the Trial Seed script
- Agent ID captured once at agent creation → `AZURE_AGENT_ID` env var
- `trial_matching_service.py` is the sole caller of `azure-ai-projects` SDK; it owns
  thread lifecycle and citation extraction
- If the knowledge base needs refresh, the Foundry IQ indexer is re-run in the portal —
  no application code changes required

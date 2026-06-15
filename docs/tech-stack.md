# Tech Stack

Complete reference of every technology, library, and external service used in the Clinical Trial Matcher.

---

## Backend

| Layer | Technology | Version | Purpose |
|---|---|---|---|
| Runtime | Python | 3.11+ | Application runtime |
| Web framework | FastAPI | ≥ 0.115 | REST API, request validation, OpenAPI docs |
| ASGI server | Uvicorn | ≥ 0.32 | Production-grade async server |
| Config management | pydantic-settings | ≥ 2.0 | Typed settings from `.env` |
| Data validation | Pydantic | ≥ 2.0 | Request/response models |
| FHIR HTTP client | httpx | ≥ 0.27 | Async HTTP client for FHIR R4 REST calls |
| Azure Agents SDK | azure-ai-agents | ≥ 1.0 | Thread-based agent runs (`AgentsClient`) |
| Azure Projects SDK | azure-ai-projects | ≥ 1.0, < 2.0 | Foundry project client; delegates agents to `azure-ai-agents` |
| Azure auth | azure-identity | ≥ 1.16 | `DefaultAzureCredential` — Entra ID token auth for Foundry Agents |
| Environment loading | python-dotenv | ≥ 1.0 | `.env` file loading |

---

## Frontend

| Layer | Technology | Version | Purpose |
|---|---|---|---|
| UI framework | React | 18.3 | Component model |
| Language | TypeScript | 5.5 | Static typing |
| Build tool | Vite | 5.4 | Dev server, HMR, production build |
| Styling | Tailwind CSS | 3.4 | Utility-first CSS |
| CSS processing | PostCSS + Autoprefixer | 8.4 / 10.4 | CSS pipeline |
| Routing | React Router DOM | 6.26 | Client-side routing |
| Server state | TanStack Query (React Query) | 5.56 | Data fetching, caching, loading states |

---

## Azure Services

| Service | Role |
|---|---|
| **Azure AI Foundry** | Project endpoint — hosts the agent, model deployments, and knowledge bases |
| **Azure AI Agents Service** | Runs the GPT-4o agent thread; handles query decomposition, tool calls, and citation attachment |
| **Foundry IQ (Azure AI Search)** | Indexes the ClinicalTrials.gov trial documents; powers retrieval-augmented generation |
| **Azure Blob Storage** | Stores the trial plain-text documents uploaded by `scripts/seed_trials.py` |
| **GPT-4o (Serverless API)** | Foundation model used by the Foundry Agent for reasoning and response generation |
| **Azure Container Apps** | Recommended backend deployment target (see Part 3 of README) |
| **Azure Container Registry** | Docker image registry for the backend container (deployment only) |
| **Azure Static Web Apps** | Recommended frontend deployment target (see Part 3 of README) |

---

## Data Sources

| Source | How it's used |
|---|---|
| **ClinicalTrials.gov v2 API** | `scripts/seed_trials.py` fetches recruiting oncology trials and uploads them as plain-text documents to Blob Storage for Foundry IQ indexing |
| **HAPI FHIR R4** | Patient demographics, active conditions, medications, lab results, and procedures — either the public sandbox (`hapi.fhir.org/baseR4`) or a local Docker instance |
| **Synthea** | Generates synthetic FHIR R4 patient bundles for local development; `scripts/upload_fhir_bundles.py` loads them into HAPI |

---

## Development Tooling

| Tool | Purpose |
|---|---|
| Azure CLI (`az`) | `az login` — required for `DefaultAzureCredential` to resolve locally |
| Docker | Runs a local HAPI FHIR server (`hapiproject/hapi:latest`) |
| Java 11+ | Runs the Synthea JAR to generate synthetic patients |
| Git | Version control |

---

## Key Design Constraints

- **Authentication**: The Foundry Agents endpoint accepts only Entra ID bearer tokens. API keys from the Foundry portal do not grant the `Microsoft.MachineLearningServices/workspaces/agents/action` permission required at runtime. Locally, `az login` resolves credentials via `DefaultAzureCredential`. In production, use a managed identity.
- **FHIR standard**: FHIR R4 (4.0.1) only. The FHIR client uses standard REST search parameters — no SMART-on-FHIR auth is required for the public sandbox.
- **azure-ai-projects pinning**: Pinned to `< 2.0.0` because version 2.x removed the thread-based agents API. The `MessageRole`, `AgentThreadCreationOptions`, and `ThreadMessageOptions` classes live in the separate `azure-ai-agents` package, not in `azure-ai-projects`.

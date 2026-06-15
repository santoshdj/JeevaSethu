# Clinical Trial Matcher

AI-assisted oncology trial matching for clinicians. A clinician selects a cancer patient, and the app pulls their FHIR profile, runs it through a **Foundry Agent (GPT-4o)** backed by a **Foundry IQ** knowledge base of indexed ClinicalTrials.gov trials, and returns eligibility verdicts with citations — in a single button click.

```
Clinician selects patient
        ↓
FastAPI pulls FHIR profile (diagnoses, meds, labs, procedures)
        ↓
Foundry Agent Service (GPT-4o)
        ↓
Foundry IQ (Azure AI Search — indexed CT.gov trial documents)
        ↓
ELIGIBLE ✅ / PARTIAL ⚠️ / INELIGIBLE ❌ per trial + citations
```

---

## Further Reading

| Document | Description |
|---|---|
| [specs/PRD.md](specs/PRD.md) | Product requirements — problem statement, user stories, success metrics |
| [docs/tech-stack.md](docs/tech-stack.md) | Full tech stack — every library, Azure service, data source, and design constraint |
| [docs/adr/0001-initial-architecture.md](docs/adr/0001-initial-architecture.md) | Why FastAPI + React over alternatives |
| [docs/adr/0002-foundry-iq-knowledge-base.md](docs/adr/0002-foundry-iq-knowledge-base.md) | Why Azure AI Foundry IQ for trial document retrieval |
| [docs/adr/0003-clinicaltrials-gov-data-source.md](docs/adr/0003-clinicaltrials-gov-data-source.md) | Why ClinicalTrials.gov v2 API as the trial corpus |
| [docs/adr/0004-no-auth-demo-clinician.md](docs/adr/0004-no-auth-demo-clinician.md) | Why auth is out of scope for the demo build |
| [CONTEXT.md](CONTEXT.md) | Domain glossary — canonical terms used across the codebase |

---

## Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Python | 3.11+ | 3.12+ recommended |
| Node.js | 20+ | LTS release |
| Azure CLI | Latest | **Required** — backend uses `DefaultAzureCredential`; run `az login` before starting |
| Azure subscription | Any tier | AI services quota needed for GPT-4o |
| Docker | 20+ | Optional — only needed for a local FHIR server (recommended) |
| Java | 11+ | Optional — only needed to generate Synthea synthetic patients |

---

## Architecture

```
Jeeva-sethu/
├── backend/                   FastAPI app
│   ├── main.py
│   ├── requirements.txt
│   ├── .env.example
│   └── app/
│       ├── config.py          Settings (FHIR + Foundry env vars)
│       ├── fhir_client.py     FHIR R4 REST client (httpx)
│       ├── routers/
│       │   ├── patients.py    GET /api/patients, /api/patients/:id
│       │   └── trials.py      POST /api/patients/:id/match-trials
│       └── services/
│           ├── patient_service.py          FHIR → Patient Profile text
│           └── trial_matching_service.py   Foundry Agent call + citation parsing
├── frontend/                  React 18 + TypeScript + Vite + Tailwind
│   └── src/
│       ├── pages/
│       │   ├── PatientsPage.tsx     Patient list + name search
│       │   └── TrialMatchPage.tsx   Profile + "Find Trials" + results + citations
│       └── lib/api.ts
├── scripts/
│   └── seed_trials.py         One-time: CT.gov → Azure Blob Storage → Foundry IQ
├── docs/adr/                  Architecture Decision Records
├── specs/PRD.md
└── CONTEXT.md                 Domain glossary
```

---

## Part 0 — FHIR Server & Patient Data

The app reads patient demographics, conditions, medications, lab results, and procedures from any FHIR R4 server. Choose one of the two options below before running locally.

---

### Option A — Public HAPI FHIR Sandbox (zero setup)

The default `.env` already points to the public HAPI FHIR R4 sandbox at `https://hapi.fhir.org/baseR4`. It is pre-populated with Synthea synthetic data and requires no setup.

**Caveats:**
- Shared public server — occasionally slow or briefly unavailable
- Contains many duplicate records (the app deduplicates by name + DOB automatically)
- Patients cover a broad range of conditions; not all have oncology diagnoses — you may need to scroll or search to find cancer patients

No changes needed in `.env`. Skip to [Part 1](#part-1--azure-ai-foundry-setup-do-this-once).

---

### Option B — Local HAPI FHIR Server + Synthetic Cancer Patients (recommended)

A local server gives you a fast, stable, private dataset of cancer patients you control.

#### Step 1 — Start a local HAPI FHIR server

Requires Docker:

```powershell
docker run -d --name hapi-fhir -p 8080:8080 hapiproject/hapi:latest
```

Wait ~30 seconds for startup, then verify:

```powershell
Invoke-RestMethod http://localhost:8080/fhir/metadata | Select-Object -ExpandProperty fhirVersion
# Should print: 4.0.1
```

> To stop/restart later: `docker stop hapi-fhir` / `docker start hapi-fhir`

Update `backend/.env` to point at the local server:

```env
FHIR_BASE_URL=http://localhost:8080/fhir
```

#### Step 2 — Generate synthetic cancer patients with Synthea

Requires Java 11+. Download the Synthea JAR once:

```powershell
# Windows (PowerShell)
curl.exe -L -o synthea.jar https://github.com/synthetichealth/synthea/releases/latest/download/synthea-with-dependencies.jar
```

```bash
# macOS / Linux
curl -L -o synthea.jar https://github.com/synthetichealth/synthea/releases/latest/download/synthea-with-dependencies.jar
```

Generate 100 synthetic patients (outputs FHIR R4 bundles under `output/fhir/`):

```powershell
java -jar synthea.jar -p 100
```

To target specific cancer conditions, use the `-m` module flag:

```powershell
# Each command appends to output/fhir/ — run as many as you like
java -jar synthea.jar -p 50 -m breast_cancer
java -jar synthea.jar -p 50 -m lung_cancer
java -jar synthea.jar -p 50 -m colorectal_cancer
java -jar synthea.jar -p 50 -m prostate_cancer
java -jar synthea.jar -p 30 -m ovarian_cancer
```

> Synthea's built-in cancer modules: `breast_cancer`, `lung_cancer`, `colorectal_cancer`, `prostate_cancer`, `ovarian_cancer`, `bladder_cancer`, `kidney_cancer`, `leukemia`, `multiple_myeloma`.

#### Step 3 — Upload bundles to the local HAPI server

Install the upload script dependency:

```powershell
pip install requests
```

Run the bundled upload helper:

```powershell
python scripts/upload_fhir_bundles.py --fhir-url http://localhost:8080/fhir --dir output/fhir
```

Example output:

```
Uploading 100 bundle(s) to http://localhost:8080/fhir ...

  [  1/100] OK    abc123.json
  [  2/100] OK    def456.json
  ...

✓ Uploaded 100 patient(s) from 100 bundle(s).
```

> **Tip:** Run `python scripts/upload_fhir_bundles.py --help` to see all options.

---

## Part 1 — Azure AI Foundry Setup (do this once)

These steps provision the Azure resources the app depends on. Complete them before running the app locally or deploying to Azure.

### Automated provisioning (recommended)

`scripts/provision.py` automates Steps 1–6 and writes `backend/.env` for you.

**Prerequisites:**
```powershell
az login
pip install azure-ai-projects azure-storage-blob requests python-dotenv azure-identity
```

**Run (PowerShell):**
```powershell
python scripts/provision.py `
  --subscription  <your-subscription-id> `
  --resource-group clinical-trial-matcher-rg `
  --location eastus `
  --project-name clinical-trial-matcher `
  --storage-account <globally-unique-name> `
  --blob-container clinical-trials `
  --max-trials 500
```

**Run (bash / macOS / Linux):**
```bash
python scripts/provision.py \
  --subscription  <your-subscription-id> \
  --resource-group clinical-trial-matcher-rg \
  --location eastus \
  --project-name clinical-trial-matcher \
  --storage-account <globally-unique-name> \
  --blob-container clinical-trials \
  --max-trials 500
```

The script creates the resource group, AI Hub, AI Project, GPT-4o serverless deployment, storage account, seeds trial documents, and creates the Foundry Agent. It then prints the two remaining portal-only actions (Foundry IQ knowledge base indexing and attaching it to the agent).

> Use `--skip-seed` to skip trial seeding on re-runs. Use `--skip-agent` if you want to create the agent manually.

---

### Manual provisioning (step-by-step)

Follow these steps if you prefer to provision resources manually or need to troubleshoot.

### Step 1 — Create an Azure AI Foundry project

1. Go to [ai.azure.com](https://ai.azure.com) and sign in
2. **New project** → give it a name (e.g. `clinical-trial-matcher`)
3. On the project home page, note:
   - **Project endpoint** — e.g. `https://<project>.services.ai.azure.com`
   - **API key** — click the copy icon next to "API key"

### Step 2 — Deploy GPT-4o in the Foundry model catalog

1. Inside your project → **Model catalog** → search `gpt-4o`
2. Click **Deploy** → choose **Serverless API**
3. Name the deployment (e.g. `gpt-4o`) → **Deploy**
4. Wait for status to show **Succeeded**

> The project endpoint + API key are what the app uses. You do **not** need the model-specific endpoint URL separately.

### Step 3 — Create an Azure Storage account and container

1. In the Azure portal → **Storage accounts** → **Create**
2. Choose your subscription and resource group → give it a name → **Review + Create**
3. Once created → **Containers** → **+ Container** → name it `clinical-trials` → **Create**
4. Go to **Access keys** → copy **Connection string** (key1)

### Step 4 — Seed Foundry IQ with ClinicalTrials.gov data

Install seed dependencies and run the seed script:

```powershell
cd scripts
pip install requests azure-storage-blob python-dotenv
```

Create a `.env` at the repo root (or export these directly):

```
AZURE_STORAGE_CONNECTION_STRING=DefaultEndpointsProtocol=https;AccountName=...
AZURE_BLOB_CONTAINER=clinical-trials
MAX_TRIALS=5000
```

Run the seed:

```powershell
python seed_trials.py
```

Output: `✓ Uploaded 5000/5000 documents` — this takes 5–10 minutes.

### Step 5 — Create a Foundry IQ knowledge base

1. Azure AI Foundry portal → your project → **Build** tab → **Knowledge** tab
2. **Create knowledge base** → give it a name (e.g. `trials-kb`)
3. **Add knowledge source** → type: **Azure Blob Storage**
   - Select your storage account and the `clinical-trials` container
4. **Save** → **Run indexer** (wait for indexer to complete — ~5–15 minutes depending on trial count)

### Step 6 — Create the Foundry Agent

1. Azure AI Foundry portal → **Build** tab → **Agents** tab
2. **New agent** → name it (e.g. `trial-matcher-agent`)
3. In **Instructions**, paste this system prompt:

```
You are a clinical trial matching assistant for oncology. Your job is to match a cancer
patient to recruiting clinical trials from the knowledge base and assess their eligibility.

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
```

4. Under **Knowledge** → **Add knowledge base** → select `trials-kb`
5. **Save** the agent
6. Note the **Agent ID** (format: `asst_xxxxxxxxxx`) — you will need this for `.env`

---

## Part 2 — Running Locally

### Step 1 — Authenticate with Azure

The backend uses `DefaultAzureCredential` to call the Foundry Agent Service. API keys do **not** work for this call — Entra ID auth is required.

```powershell
az login
```

Then verify your account has the **Azure AI Developer** role on the Azure Machine Learning workspace that backs your Foundry project:

1. [Azure portal](https://portal.azure.com) → **Resource groups** → your resource group
2. Find the **Machine Learning workspace** resource (type: `Microsoft.MachineLearningServices/workspaces`)
3. **Access control (IAM)** → **Add role assignment** → role: `Azure AI Developer` → assign to your user

> If you see `Identity (object id: ...) does not have permissions for Microsoft.MachineLearningServices/workspaces/agents/action`, this role is missing.

### Step 2 — Configure the backend

```powershell
cd backend
copy .env.example .env
```

Edit `.env`:

```env
# FHIR server — use the public sandbox or http://localhost:8080/fhir for a local Docker server
FHIR_BASE_URL=https://hapi.fhir.org/baseR4
FHIR_AUTH_TOKEN=

# Azure AI Foundry project endpoint (from portal home page)
AZURE_PROJECT_ENDPOINT=https://<your-project>.services.ai.azure.com

# API key — stored for reference; the Agents SDK uses DefaultAzureCredential (az login)
AZURE_API_KEY=<api-key-from-foundry-home-page>

# Agent ID from Foundry portal → Agents tab (format: asst_...)
AZURE_AGENT_ID=asst_<your-agent-id>

ALLOWED_ORIGINS=http://localhost:5173
```

### Step 3 — Install and run the backend

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Verify: open [http://localhost:8000/health](http://localhost:8000/health) — should return `{"status":"ok"}`.

### Step 4 — Configure and run the frontend

```powershell
cd frontend
copy .env.local.example .env.local
npm install
npm run dev
```

`.env.local` should contain:

```env
VITE_API_BASE_URL=http://localhost:8000
```

Open [http://localhost:5173](http://localhost:5173).

### Step 5 — Test the full flow

1. The Patients Page loads cancer patients from your FHIR server
2. Click any patient → Trial Match Page opens
3. Click **Find Matching Trials**
4. Wait 15–30 seconds while the Foundry Agent queries Foundry IQ
5. Eligibility verdicts + citations appear

---

## Part 3 — Deploying to Azure

The recommended deployment is **Azure Container Apps** (backend) + **Azure Static Web Apps** (frontend).

### Backend — Azure Container Apps

#### Build and push the Docker image

Create `backend/Dockerfile`:

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

```powershell
az login
az acr create --name <registry-name> --resource-group <rg> --sku Basic
az acr build --registry <registry-name> --image clinical-trial-matcher-backend:latest ./backend
```

#### Deploy to Container Apps

```powershell
az containerapp env create --name trial-matcher-env --resource-group <rg> --location eastus

az containerapp create `
  --name trial-matcher-backend `
  --resource-group <rg> `
  --environment trial-matcher-env `
  --image <registry-name>.azurecr.io/clinical-trial-matcher-backend:latest `
  --target-port 8000 `
  --ingress external `
  --env-vars `
    FHIR_BASE_URL=https://hapi.fhir.org/baseR4 `
    AZURE_PROJECT_ENDPOINT=https://<your-project>.services.ai.azure.com `
    AZURE_API_KEY=secretref:azure-api-key `
    AZURE_AGENT_ID=asst_<your-agent-id> `
    ALLOWED_ORIGINS=https://<your-static-web-app>.azurestaticapps.net
```

> Store `AZURE_API_KEY` as a Container Apps secret rather than a plain env var:
> ```powershell
> az containerapp secret set --name trial-matcher-backend --resource-group <rg> \
>   --secrets azure-api-key=<your-key>
> ```

Note the **Container App URL** from the output (e.g. `https://trial-matcher-backend.<hash>.eastus.azurecontainerapps.io`).

### Frontend — Azure Static Web Apps

1. Update `frontend/.env.local` (or set in SWA configuration):
   ```env
   VITE_API_BASE_URL=https://trial-matcher-backend.<hash>.eastus.azurecontainerapps.io
   ```

2. Build the frontend:
   ```powershell
   cd frontend
   npm run build
   ```

3. Deploy via Azure CLI:
   ```powershell
   az staticwebapp create --name trial-matcher-frontend --resource-group <rg> --location eastus
   az staticwebapp deploy --name trial-matcher-frontend --resource-group <rg> --source ./frontend/dist
   ```

   Alternatively, connect the GitHub repo to Azure Static Web Apps for automatic deploys on push.

### CORS configuration

Once both are deployed, update `ALLOWED_ORIGINS` in the Container App to the Static Web App URL:

```powershell
az containerapp update --name trial-matcher-backend --resource-group <rg> `
  --set-env-vars ALLOWED_ORIGINS=https://<your-static-web-app>.azurestaticapps.net
```

---

## Environment Variable Reference

| Variable | Required | Where used | Description |
|---|---|---|---|
| `FHIR_BASE_URL` | Yes | Backend | FHIR R4 server base URL |
| `FHIR_AUTH_TOKEN` | No | Backend | Bearer token if FHIR server requires auth |
| `AZURE_PROJECT_ENDPOINT` | Yes | Backend | Foundry project endpoint from portal home page |
| `AZURE_API_KEY` | Yes | Backend | API key from Foundry portal home page |
| `AZURE_AGENT_ID` | Yes | Backend | Agent ID from Foundry Agents tab (format: `asst_...`) |
| `ALLOWED_ORIGINS` | Yes | Backend | Comma-separated CORS origins |
| `VITE_API_BASE_URL` | Yes | Frontend | Backend base URL |
| `AZURE_STORAGE_CONNECTION_STRING` | Seed only | `scripts/seed_trials.py` | Blob Storage connection string |
| `AZURE_BLOB_CONTAINER` | Seed only | `scripts/seed_trials.py` | Container name (default: `clinical-trials`) |
| `MAX_TRIALS` | No | `scripts/seed_trials.py` | Trial fetch cap (default: `5000`) |

---

## Refreshing the Trial Knowledge Base

When you want to update Foundry IQ with newer trials from ClinicalTrials.gov:

1. Re-run the seed script: `python scripts/seed_trials.py`
2. Azure AI Foundry portal → Build → Knowledge → select `trials-kb` → **Run indexer**

No application code changes are required.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Patients page shows no patients | FHIR server unreachable or wrong `FHIR_BASE_URL` | Check `/health` endpoint and verify env var |
| Patients page shows no patients | Local HAPI not running | `docker start hapi-fhir` then wait 30 s |
| No cancer patients in the list | Public HAPI sandbox has mixed data | Search by name or use local Docker server with Synthea cancer modules |
| `DefaultAzureCredential: No credential` | `az login` not done or session expired | Run `az login` then restart the backend |
| `Identity does not have permissions … agents/action` | `Azure AI Developer` RBAC role missing | Assign the role on the ML workspace via Azure portal IAM |
| "Find Matching Trials" returns error | Wrong `AZURE_AGENT_ID` or agent not saved in portal | Re-copy agent ID from Foundry Agents tab |
| Agent response has no citations | Foundry IQ knowledge base not attached to the agent | Agents tab → edit agent → add knowledge base |
| Indexer shows 0 documents | Blob container empty or wrong container name | Re-run seed script, verify `AZURE_BLOB_CONTAINER` |
| CORS error in browser | `ALLOWED_ORIGINS` missing frontend URL | Update env var to include the frontend origin |
| Agent run status `failed` | GPT-4o deployment not ready or quota exceeded | Check deployment status in Foundry model catalog |
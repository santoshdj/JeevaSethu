#!/usr/bin/env python3
"""
provision.py — Automates Part 1 (Azure AI Foundry Setup) for Clinical Trial Matcher.

What this script does
---------------------
  Step 1  Create resource group
  Step 2  Create Azure AI Hub + Project (requires az ml extension)
  Step 3  Deploy GPT-4o via Serverless API
  Step 4  Create Azure Storage account + container
  Step 5  Seed Foundry IQ blob container with ClinicalTrials.gov data
  Step 6  Create the Foundry Agent via SDK
  Step 7  Write a ready-to-use backend/.env file

  ⚠  Foundry IQ knowledge-base creation (attaching Blob Storage as a search
     index and running the indexer) is portal-only at this time. The script
     will print the exact instructions once seeding is complete.

Prerequisites
-------------
  1. Azure CLI  (az)        — https://learn.microsoft.com/cli/azure/install-azure-cli
  2. az ml extension        — run:  az extension add -n ml
  3. Python packages        — pip install azure-ai-projects azure-storage-blob
                                      requests python-dotenv azure-identity

Usage
-----
  python scripts/provision.py \\
      --subscription  <subscription-id>  \\
      --resource-group clinical-trial-matcher-rg  \\
      --location eastus  \\
      --project-name clinical-trial-matcher  \\
      --storage-account <globally-unique-name>  \\
      --blob-container clinical-trials

  All flags have defaults shown by --help.
  On re-run, already-existing resources are skipped (idempotent).
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import textwrap
import time

# ---------------------------------------------------------------------------
# CLI args
# ---------------------------------------------------------------------------

DEFAULTS = {
    "resource_group": "clinical-trial-matcher-rg",
    "location": "eastus",
    "project_name": "clinical-trial-matcher",
    "hub_name": "clinical-trial-hub",
    "storage_account": "",          # must be globally unique — user supplies
    "blob_container": "clinical-trials",
    "max_trials": 500,
    "agent_name": "trial-matcher-agent",
    "model_deployment": "gpt-4o",
}

AGENT_SYSTEM_PROMPT = textwrap.dedent("""\
    You are a clinical trial matching assistant for oncology. Your job is to match a cancer
    patient to recruiting clinical trials from the knowledge base and assess their eligibility.

    When given a patient profile, you must:
    1. Search the knowledge base for trials relevant to the patient's cancer type, stage,
       and treatment history.
    2. Return the top 5-10 most relevant recruiting trials.
    3. For each trial provide:
       - Trial name and NCT ID
       - Eligibility verdict: ELIGIBLE ✅, PARTIAL ⚠️, or INELIGIBLE ❌
       - 2-3 sentences explaining the verdict, citing specific patient data points
       - Key inclusion criteria the patient meets
       - Key exclusion criteria that may disqualify the patient (if any)
       - Trial location(s) and phase

    Format each trial as a clearly separated section. Be precise and grounded — only use
    information present in the patient profile and the retrieved trial documents.
    Always cite the source trial document for each recommendation.
""")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Provision Azure resources for Clinical Trial Matcher (Part 1).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--subscription", required=True, help="Azure subscription ID")
    p.add_argument("--resource-group", default=DEFAULTS["resource_group"])
    p.add_argument("--location", default=DEFAULTS["location"])
    p.add_argument("--project-name", default=DEFAULTS["project_name"])
    p.add_argument("--storage-account", default=DEFAULTS["storage_account"],
                   help="Globally unique storage account name (3-24 lowercase alphanum)")
    p.add_argument("--blob-container", default=DEFAULTS["blob_container"])
    p.add_argument("--max-trials", type=int, default=DEFAULTS["max_trials"],
                   help="Cap on trial docs to seed (default 500 for speed; use 5000 for prod)")
    p.add_argument("--agent-name", default=DEFAULTS["agent_name"])
    p.add_argument("--model-deployment", default=DEFAULTS["model_deployment"],
                   help="Name for the GPT-4o serverless deployment")
    p.add_argument("--skip-seed", action="store_true",
                   help="Skip seeding trials (if blob already populated)")
    p.add_argument("--skip-agent", action="store_true",
                   help="Skip agent creation (Foundry IQ not yet attached)")
    return p.parse_args()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BOLD  = "\033[1m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED   = "\033[91m"
RESET = "\033[0m"


def step(n: int, title: str) -> None:
    print(f"\n{BOLD}{'─'*60}{RESET}")
    print(f"{BOLD}Step {n}: {title}{RESET}")
    print(f"{BOLD}{'─'*60}{RESET}")


def ok(msg: str) -> None:
    print(f"{GREEN}  ✓ {msg}{RESET}")


def warn(msg: str) -> None:
    print(f"{YELLOW}  ⚠  {msg}{RESET}")


def err(msg: str) -> None:
    print(f"{RED}  ✗ {msg}{RESET}", file=sys.stderr)


def _resolve_cmd(cmd: list[str]) -> list[str]:
    """On Windows, resolve the executable via shutil.which so .cmd/.bat files are found."""
    if sys.platform == "win32" and cmd:
        resolved = shutil.which(cmd[0])
        if resolved:
            return [resolved] + cmd[1:]
    return cmd


def run(cmd: list[str], *, check: bool = True, capture: bool = False) -> subprocess.CompletedProcess:
    """Run an az CLI command, streaming output unless capture=True."""
    cmd = _resolve_cmd(cmd)
    print(f"  $ {' '.join(cmd)}")
    result = subprocess.run(
        cmd,
        capture_output=capture,
        text=True,
        check=False,
    )
    if check and result.returncode != 0:
        err(f"Command failed (exit {result.returncode})")
        if capture:
            print(result.stderr, file=sys.stderr)
        sys.exit(1)
    return result


def az_json(cmd: list[str]) -> dict | list | None:
    """Run an az CLI command and parse the JSON output."""
    result = run(cmd + ["--output", "json"], capture=True, check=False)
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def require_cli_tool(tool: str, install_hint: str) -> None:
    if shutil.which(tool) is None:
        err(f"'{tool}' not found. {install_hint}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Step implementations
# ---------------------------------------------------------------------------

def ensure_resource_group(args: argparse.Namespace) -> None:
    step(1, f"Resource group: {args.resource_group}")
    existing = az_json(["az", "group", "show", "--name", args.resource_group])
    if existing:
        ok(f"Resource group already exists — skipping creation")
        return
    run(["az", "group", "create",
         "--name", args.resource_group,
         "--location", args.location])
    ok(f"Created resource group '{args.resource_group}' in {args.location}")


def ensure_foundry_project(args: argparse.Namespace) -> tuple[str, str]:
    """
    Create an Azure AI Services account (new Foundry model — no Hub required).
    Returns (project_endpoint, api_key).
    """
    step(2, f"Azure AI Services account (Foundry project): {args.project_name}")

    existing = az_json([
        "az", "cognitiveservices", "account", "show",
        "--name", args.project_name,
        "--resource-group", args.resource_group,
        "--subscription", args.subscription,
    ])
    if existing:
        ok(f"AI Services account '{args.project_name}' already exists — skipping creation")
    else:
        print(f"  Creating Azure AI Services account '{args.project_name}' ...")
        print("  (This may take 1–3 minutes)")
        run([
            "az", "cognitiveservices", "account", "create",
            "--name", args.project_name,
            "--resource-group", args.resource_group,
            "--location", args.location,
            "--kind", "AIServices",
            "--sku", "S0",
            "--yes",
            "--subscription", args.subscription,
        ])
        ok(f"Created Azure AI Services account '{args.project_name}'")

    # Retrieve endpoint
    account_info = az_json([
        "az", "cognitiveservices", "account", "show",
        "--name", args.project_name,
        "--resource-group", args.resource_group,
        "--subscription", args.subscription,
    ])
    endpoint = (account_info or {}).get("properties", {}).get("endpoint", "")
    if not endpoint:
        endpoint = f"https://{args.project_name}.cognitiveservices.azure.com"
        warn(
            f"Could not auto-detect endpoint. Using inferred value: {endpoint}\n"
            "  → Verify in Foundry portal → project home page and update .env if different."
        )
    else:
        ok(f"Project endpoint: {endpoint}")

    # Retrieve API key
    keys_result = az_json([
        "az", "cognitiveservices", "account", "keys", "list",
        "--name", args.project_name,
        "--resource-group", args.resource_group,
        "--subscription", args.subscription,
    ])
    api_key = (keys_result or {}).get("key1", "")
    if not api_key:
        warn(
            "Could not retrieve API key automatically.\n"
            "  → Copy the API key from Foundry portal → project home page and add it to .env."
        )
    else:
        ok("Retrieved API key")

    return endpoint, api_key


def ensure_gpt4o_deployment(args: argparse.Namespace) -> None:
    step(3, f"Deploy GPT-4o: {args.model_deployment}")

    # Check if deployment already exists
    existing = az_json([
        "az", "cognitiveservices", "account", "deployment", "show",
        "--name", args.project_name,
        "--resource-group", args.resource_group,
        "--deployment-name", args.model_deployment,
        "--subscription", args.subscription,
    ])
    if existing and existing.get("properties", {}).get("provisioningState") == "Succeeded":
        ok(f"GPT-4o deployment '{args.model_deployment}' already exists")
        return

    print(f"  Deploying GPT-4o as '{args.model_deployment}' ...")
    print("  (This may take 2–5 minutes)")
    run([
        "az", "cognitiveservices", "account", "deployment", "create",
        "--name", args.project_name,
        "--resource-group", args.resource_group,
        "--deployment-name", args.model_deployment,
        "--model-name", "gpt-4o",
        "--model-version", "2024-11-20",
        "--model-format", "OpenAI",
        "--sku-name", "Standard",
        "--sku-capacity", "10",
        "--subscription", args.subscription,
    ])
    ok(f"GPT-4o deployment '{args.model_deployment}' created")


def ensure_storage(args: argparse.Namespace) -> str:
    """Create storage account + container. Returns connection string."""
    step(4, f"Storage account: {args.storage_account}")

    if not args.storage_account:
        err(
            "--storage-account is required. "
            "Choose a globally unique name (3-24 lowercase alphanumeric)."
        )
        sys.exit(1)

    # Create storage account
    existing = az_json([
        "az", "storage", "account", "show",
        "--name", args.storage_account,
        "--resource-group", args.resource_group,
        "--subscription", args.subscription,
    ])
    if existing:
        ok(f"Storage account '{args.storage_account}' already exists")
    else:
        run([
            "az", "storage", "account", "create",
            "--name", args.storage_account,
            "--resource-group", args.resource_group,
            "--location", args.location,
            "--sku", "Standard_LRS",
            "--kind", "StorageV2",
            "--subscription", args.subscription,
        ])
        ok(f"Created storage account '{args.storage_account}'")

    # Retrieve connection string
    keys = az_json([
        "az", "storage", "account", "show-connection-string",
        "--name", args.storage_account,
        "--resource-group", args.resource_group,
        "--subscription", args.subscription,
    ])
    conn_str = (keys or {}).get("connectionString", "")
    if not conn_str:
        err("Could not retrieve storage connection string")
        sys.exit(1)
    ok("Retrieved storage connection string")

    # Create blob container
    container_result = run([
        "az", "storage", "container", "create",
        "--name", args.blob_container,
        "--connection-string", conn_str,
    ], check=False, capture=True)
    if container_result.returncode == 0:
        ok(f"Container '{args.blob_container}' ready")
    else:
        warn(f"Container creation returned non-zero — may already exist")

    return conn_str


def seed_trials(conn_str: str, args: argparse.Namespace) -> None:
    step(5, "Seed Foundry IQ blob container with ClinicalTrials.gov data")

    # Import seed logic inline to avoid subprocess overhead
    try:
        import requests as _requests
        from azure.storage.blob import BlobServiceClient
    except ImportError:
        err(
            "Missing packages. Run:\n"
            "  pip install requests azure-storage-blob"
        )
        sys.exit(1)

    CT_API_BASE = "https://clinicaltrials.gov/api/v2/studies"
    CT_PARAMS = {
        "query.cond": (
            "cancer OR oncology OR tumor OR neoplasm OR carcinoma "
            "OR lymphoma OR leukemia OR melanoma OR sarcoma OR glioma "
            "OR breast OR lung OR colorectal OR prostate OR ovarian OR cervical "
            "OR pancreatic OR gastric OR bladder OR thyroid OR endometrial"
        ),
        "filter.overallStatus": "RECRUITING",
        "pageSize": "100",
        "format": "json",
    }

    print(f"  Fetching up to {args.max_trials} recruiting oncology trials from ClinicalTrials.gov ...")
    all_studies: list[dict] = []
    next_token: str | None = None
    page = 1

    while len(all_studies) < args.max_trials:
        params = {**CT_PARAMS}
        if next_token:
            params["pageToken"] = next_token
        try:
            resp = _requests.get(CT_API_BASE, params=params, timeout=30)
            resp.raise_for_status()
        except _requests.RequestException as exc:
            warn(f"Page {page} failed: {exc} — stopping fetch early")
            break
        data = resp.json()
        studies = data.get("studies", [])
        all_studies.extend(studies)
        print(f"    Page {page}: {len(studies)} trials fetched (total: {len(all_studies)})")
        next_token = data.get("nextPageToken")
        if not next_token:
            break
        page += 1
        time.sleep(0.3)

    all_studies = all_studies[:args.max_trials]
    print(f"  Uploading {len(all_studies)} documents to blob container '{args.blob_container}' ...")

    client = BlobServiceClient.from_connection_string(conn_str)
    container_client = client.get_container_client(args.blob_container)

    uploaded = 0
    skipped = 0
    for study in all_studies:
        proto = study.get("protocolSection", {})
        id_mod = proto.get("identificationModule", {})
        nct_id = id_mod.get("nctId", "UNKNOWN")

        # Skip if already uploaded (idempotent)
        blob_client = container_client.get_blob_client(f"{nct_id}.txt")
        try:
            blob_client.get_blob_properties()
            skipped += 1
            continue
        except Exception:
            pass

        doc = _study_to_text(study)
        blob_client.upload_blob(doc, overwrite=True)
        uploaded += 1
        if uploaded % 100 == 0:
            print(f"    Uploaded {uploaded} ...")

    ok(f"Seeding complete — {uploaded} uploaded, {skipped} already existed")


def _study_to_text(study: dict) -> str:
    proto = study.get("protocolSection", {})
    id_mod    = proto.get("identificationModule", {})
    desc_mod  = proto.get("descriptionModule", {})
    elig_mod  = proto.get("eligibilityModule", {})
    cond_mod  = proto.get("conditionsModule", {})
    arms_mod  = proto.get("armsInterventionsModule", {})
    design_mod = proto.get("designModule", {})
    contacts_mod = proto.get("contactsLocationsModule", {})
    sponsor_mod  = proto.get("sponsorCollaboratorsModule", {})

    nct_id   = id_mod.get("nctId", "UNKNOWN")
    title    = id_mod.get("briefTitle") or id_mod.get("officialTitle", "")
    summary  = desc_mod.get("briefSummary", "").strip()
    elig     = elig_mod.get("eligibilityCriteria", "").strip()
    min_age  = elig_mod.get("minimumAge", "Not specified")
    max_age  = elig_mod.get("maximumAge", "Not specified")
    sex      = elig_mod.get("sex", "ALL")
    conds    = ", ".join(cond_mod.get("conditions", []))
    phases   = design_mod.get("phaseList", {}).get("phase", [])
    phase    = ", ".join(phases) if phases else "Not specified"
    interventions = [
        f"{i.get('interventionType','')}: {i.get('interventionName','')}"
        for i in arms_mod.get("interventionList", {}).get("intervention", [])
        if i.get("interventionName")
    ]
    locations = [
        f"{loc.get('locationCity','')}, {loc.get('locationCountry','')}"
        for loc in contacts_mod.get("locationList", {}).get("location", [])[:5]
        if loc.get("locationCity")
    ]
    sponsor = sponsor_mod.get("leadSponsor", {}).get("leadSponsorName", "")

    return (
        f"Clinical Trial: {title}\n"
        f"NCT ID: {nct_id}\n"
        f"URL: https://clinicaltrials.gov/study/{nct_id}\n"
        f"Status: RECRUITING\n"
        f"Phase: {phase}\n"
        f"Sponsor: {sponsor}\n\n"
        f"Conditions: {conds}\n"
        f"Interventions: {'; '.join(interventions) or 'Not specified'}\n\n"
        f"Age Range: {min_age} to {max_age}\n"
        f"Sex Eligibility: {sex}\n"
        f"Locations: {'; '.join(locations) or 'See ClinicalTrials.gov'}\n\n"
        f"Summary:\n{summary}\n\n"
        f"Eligibility Criteria:\n{elig}\n"
    )


def create_agent(project_endpoint: str, api_key: str, args: argparse.Namespace) -> str:
    """Create the Foundry Agent and return its agent_id."""
    step(6, f"Create Foundry Agent: {args.agent_name}")

    if not api_key:
        warn(
            "API key not available — skipping automated agent creation.\n"
            "  → Follow Step 6 in the README to create the agent manually in the portal."
        )
        return ""

    try:
        from azure.ai.projects import AIProjectClient
        from azure.core.credentials import AzureKeyCredential
    except ImportError:
        warn(
            "azure-ai-projects not installed — skipping automated agent creation.\n"
            "  Run: pip install azure-ai-projects\n"
            "  Then re-run this script or create the agent manually."
        )
        return ""

    try:
        client = AIProjectClient(
            endpoint=project_endpoint,
            credential=AzureKeyCredential(api_key),
        )

        # Check for existing agent with the same name
        agents = client.agents.list_agents()
        for agent in (agents.value if hasattr(agents, "value") else []):
            if agent.name == args.agent_name:
                ok(f"Agent '{args.agent_name}' already exists (id: {agent.id})")
                return agent.id

        agent = client.agents.create_agent(
            model=args.model_deployment,
            name=args.agent_name,
            instructions=AGENT_SYSTEM_PROMPT,
        )
        ok(f"Created agent '{args.agent_name}' → id: {agent.id}")
        warn(
            "IMPORTANT: Foundry IQ knowledge base must be attached to the agent in the portal.\n"
            "  → See manual instructions printed at the end of this script."
        )
        return agent.id
    except Exception as exc:
        warn(f"Agent creation failed: {exc}\n  → Create the agent manually in the portal.")
        return ""


def write_env_file(
    project_endpoint: str,
    api_key: str,
    agent_id: str,
    args: argparse.Namespace,
) -> None:
    step(7, "Write backend/.env")

    env_path = os.path.join(
        os.path.dirname(__file__), "..", "backend", ".env"
    )
    env_path = os.path.normpath(env_path)

    if os.path.exists(env_path):
        warn(f".env already exists at {env_path} — writing .env.provisioned instead")
        env_path = env_path.replace(".env", ".env.provisioned")

    content = textwrap.dedent(f"""\
        # Generated by scripts/provision.py
        FHIR_BASE_URL=https://hapi.fhir.org/baseR4
        FHIR_AUTH_TOKEN=

        AZURE_PROJECT_ENDPOINT={project_endpoint}
        AZURE_API_KEY={api_key or "<PASTE_FROM_FOUNDRY_PORTAL>"}
        AZURE_AGENT_ID={agent_id or "<PASTE_AGENT_ID_FROM_FOUNDRY_PORTAL>"}

        ALLOWED_ORIGINS=http://localhost:5173
    """)

    with open(env_path, "w") as f:
        f.write(content)
    ok(f"Written to {env_path}")


def print_manual_steps(args: argparse.Namespace, conn_str: str) -> None:
    step("→", "Manual steps required in the Azure AI Foundry portal")
    print(textwrap.dedent(f"""
  {YELLOW}Foundry IQ knowledge base creation is not yet available via CLI.
  Complete these steps in the portal (takes ~10 minutes):{RESET}

  A) CREATE THE KNOWLEDGE BASE
     1. Go to https://ai.azure.com → your project '{args.project_name}'
     2. Build tab → Knowledge tab
     3. Click "Create knowledge base" → name it 'trials-kb'
     4. Add knowledge source → type: Azure Blob Storage
        Storage account : {args.storage_account}
        Container       : {args.blob_container}
     5. Save → click "Run indexer"
        Wait for "Indexer status: Succeeded" (~5-15 min for 500+ docs)

  B) ATTACH KNOWLEDGE BASE TO AGENT
     1. Build tab → Agents tab → select '{args.agent_name}'
     2. Under "Knowledge" → "Add knowledge base" → select 'trials-kb'
     3. Save the agent

  C) COPY THE AGENT ID
     The agent ID (format: asst_xxxx) is shown in the Agents tab.
     Paste it into backend/.env as AZURE_AGENT_ID.

  {GREEN}Once complete, run the app:{RESET}
     cd backend && uvicorn main:app --reload --port 8000
     cd frontend && npm install && npm run dev
"""))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    args = parse_args()

    print(f"\n{BOLD}Clinical Trial Matcher — Azure Provisioning{RESET}")
    print(f"Subscription : {args.subscription}")
    print(f"Resource group: {args.resource_group}  ({args.location})")
    print(f"Project      : {args.project_name}")

    # Check prerequisites
    require_cli_tool("az", "Install from https://aka.ms/installazurecliwindows")

    # Verify az login
    account = az_json(["az", "account", "show"])
    if not account:
        err("Not logged in to Azure CLI. Run: az login")
        sys.exit(1)
    ok(f"Logged in as: {account.get('user', {}).get('name', '?')}")

    # Set subscription
    run(["az", "account", "set", "--subscription", args.subscription], check=True, capture=True)

    # Run steps
    ensure_resource_group(args)
    project_endpoint, api_key = ensure_foundry_project(args)
    ensure_gpt4o_deployment(args)
    conn_str = ensure_storage(args)

    if not args.skip_seed:
        seed_trials(conn_str, args)
    else:
        warn("Skipping seed step (--skip-seed)")

    agent_id = ""
    if not args.skip_agent:
        agent_id = create_agent(project_endpoint, api_key, args)

    write_env_file(project_endpoint, api_key, agent_id, args)
    print_manual_steps(args, conn_str)

    print(f"\n{GREEN}{BOLD}Provisioning complete.{RESET}")
    print("Complete the portal steps above, then start the app.\n")


if __name__ == "__main__":
    main()

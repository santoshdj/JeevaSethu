"""
Seed script: fetch recruiting oncology trials from ClinicalTrials.gov v2 API,
convert each to a plain-text document, and upload to Azure Blob Storage so
Foundry IQ can index them.

Usage:
    pip install requests azure-storage-blob python-dotenv
    python scripts/seed_trials.py

Required env vars (or set in .env at repo root):
    AZURE_STORAGE_CONNECTION_STRING  — Blob Storage connection string
    AZURE_BLOB_CONTAINER             — container name (e.g. "clinical-trials")

Optional:
    MAX_TRIALS  — cap on number of trials to fetch (default: 5000)

After running:
    1. Go to Azure AI Foundry portal → your project → Build → Knowledge tab
    2. Create a knowledge base, add a knowledge source pointing to the Blob
       Storage container you just populated
    3. Run the indexer
    4. Attach the knowledge base to your agent (Agents tab)
"""

import json
import os
import sys
import time

import requests
from azure.storage.blob import BlobServiceClient
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
CT_API_BASE = "https://clinicaltrials.gov/api/v2/studies"
CONNECTION_STRING = os.environ["AZURE_STORAGE_CONNECTION_STRING"]
CONTAINER_NAME = os.environ.get("AZURE_BLOB_CONTAINER", "clinical-trials")
MAX_TRIALS = int(os.environ.get("MAX_TRIALS", "5000"))

CT_PARAMS = {
    # Broad oncology filter — catches most cancer trial conditions
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


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------
def fetch_trials() -> list[dict]:
    all_studies: list[dict] = []
    next_token: str | None = None
    page = 1

    print(f"Fetching recruiting oncology trials from ClinicalTrials.gov (cap: {MAX_TRIALS})...")

    while len(all_studies) < MAX_TRIALS:
        params = {**CT_PARAMS}
        if next_token:
            params["pageToken"] = next_token

        try:
            resp = requests.get(CT_API_BASE, params=params, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as exc:
            print(f"  ✗ Page {page} failed: {exc}", file=sys.stderr)
            break

        data = resp.json()
        studies = data.get("studies", [])
        all_studies.extend(studies)
        print(f"  Page {page}: fetched {len(studies)} trials (total: {len(all_studies)})")

        next_token = data.get("nextPageToken")
        if not next_token:
            break

        page += 1
        time.sleep(0.3)  # be polite to the API

    return all_studies[:MAX_TRIALS]


# ---------------------------------------------------------------------------
# Convert
# ---------------------------------------------------------------------------
def study_to_text(study: dict) -> tuple[str, str]:
    """
    Convert a ClinicalTrials.gov study JSON to a plain-text document.
    Returns (nct_id, document_text).
    """
    proto = study.get("protocolSection", {})
    id_mod = proto.get("identificationModule", {})
    desc_mod = proto.get("descriptionModule", {})
    elig_mod = proto.get("eligibilityModule", {})
    cond_mod = proto.get("conditionsModule", {})
    arms_mod = proto.get("armsInterventionsModule", {})
    design_mod = proto.get("designModule", {})
    contacts_mod = proto.get("contactsLocationsModule", {})
    sponsor_mod = proto.get("sponsorCollaboratorsModule", {})

    nct_id = id_mod.get("nctId", "UNKNOWN")
    title = id_mod.get("briefTitle") or id_mod.get("officialTitle", "")
    summary = desc_mod.get("briefSummary", "").strip()
    eligibility = elig_mod.get("eligibilityCriteria", "").strip()
    min_age = elig_mod.get("minimumAge", "Not specified")
    max_age = elig_mod.get("maximumAge", "Not specified")
    sex = elig_mod.get("sex", "ALL")
    conditions = ", ".join(cond_mod.get("conditions", []))

    phases = design_mod.get("phaseList", {}).get("phase", [])
    phase = ", ".join(phases) if phases else "Not specified"

    interventions = [
        f"{i.get('interventionType', '')}: {i.get('interventionName', '')}"
        for i in arms_mod.get("interventionList", {}).get("intervention", [])
        if i.get("interventionName")
    ]

    locations = [
        f"{loc.get('locationCity', '')}, {loc.get('locationCountry', '')}"
        for loc in contacts_mod.get("locationList", {}).get("location", [])[:5]
        if loc.get("locationCity")
    ]

    sponsor = sponsor_mod.get("leadSponsor", {}).get("leadSponsorName", "")

    doc = f"""Clinical Trial: {title}
NCT ID: {nct_id}
URL: https://clinicaltrials.gov/study/{nct_id}
Status: RECRUITING
Phase: {phase}
Sponsor: {sponsor}

Conditions: {conditions}
Interventions: {'; '.join(interventions) or 'Not specified'}

Age Range: {min_age} to {max_age}
Sex Eligibility: {sex}
Locations: {'; '.join(locations) or 'See ClinicalTrials.gov'}

Summary:
{summary}

Eligibility Criteria:
{eligibility}
"""
    return nct_id, doc


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------
def upload_to_blob(documents: list[tuple[str, str]]) -> None:
    blob_service = BlobServiceClient.from_connection_string(CONNECTION_STRING)

    # Create container if it doesn't exist
    container_client = blob_service.get_container_client(CONTAINER_NAME)
    try:
        container_client.create_container()
        print(f"Created container: {CONTAINER_NAME}")
    except Exception:
        print(f"Container already exists: {CONTAINER_NAME}")

    print(f"\nUploading {len(documents)} documents to Blob Storage...")
    success = 0
    for nct_id, text in documents:
        blob_name = f"{nct_id}.txt"
        try:
            container_client.upload_blob(
                name=blob_name,
                data=text.encode("utf-8"),
                overwrite=True,
            )
            success += 1
        except Exception as exc:
            print(f"  ✗ Failed to upload {blob_name}: {exc}", file=sys.stderr)

    print(f"  ✓ Uploaded {success}/{len(documents)} documents")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    studies = fetch_trials()
    if not studies:
        print("No studies fetched. Exiting.", file=sys.stderr)
        sys.exit(1)

    print(f"\nConverting {len(studies)} studies to text documents...")
    documents = [study_to_text(s) for s in studies]
    valid = [(nct, text) for nct, text in documents if nct != "UNKNOWN"]
    print(f"  ✓ {len(valid)} valid documents")

    upload_to_blob(valid)

    print(
        f"\nDone. Next steps:"
        f"\n  1. Azure AI Foundry portal → Build → Knowledge tab"
        f"\n  2. Create knowledge base → add knowledge source → Azure Blob Storage"
        f"\n  3. Point to container: {CONTAINER_NAME}"
        f"\n  4. Run the indexer"
        f"\n  5. Attach the knowledge base to your agent (Agents tab)"
    )

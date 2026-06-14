"""
Upload Synthea-generated FHIR R4 patient bundles to a FHIR server.

Usage:
    pip install requests
    python scripts/upload_fhir_bundles.py

Optional arguments:
    --fhir-url   FHIR server base URL  (default: http://localhost:8080/fhir)
    --dir        Directory of Synthea bundle JSON files  (default: output/fhir)
    --pause      Seconds to wait between uploads  (default: 0.1)

Synthea generates three file types in output/fhir/:
  - <uuid>.json           patient bundles  ← uploaded
  - hospitalInformation*.json              ← skipped
  - practitionerInformation*.json          ← skipped
"""

import argparse
import json
import os
import sys
import time

import requests


# ---------------------------------------------------------------------------
# Upload one bundle; returns number of Patient resources in it
# ---------------------------------------------------------------------------
def upload_bundle(fhir_url: str, path: str) -> int:
    with open(path, encoding="utf-8") as f:
        bundle = json.load(f)

    # Skip non-bundle resources (just in case)
    if bundle.get("resourceType") != "Bundle":
        return 0

    resp = requests.post(
        fhir_url,
        json=bundle,
        headers={
            "Content-Type": "application/fhir+json",
            "Accept": "application/fhir+json",
        },
        timeout=60,
    )

    if resp.status_code not in (200, 201):
        print(f"  WARN  {os.path.basename(path)}  HTTP {resp.status_code}: {resp.text[:120]}")
        return 0

    patient_count = sum(
        1
        for entry in bundle.get("entry", [])
        if entry.get("resource", {}).get("resourceType") == "Patient"
    )
    return patient_count


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Upload Synthea FHIR bundles to a local HAPI FHIR server."
    )
    parser.add_argument(
        "--fhir-url",
        default="http://localhost:8080/fhir",
        help="FHIR server base URL (default: http://localhost:8080/fhir)",
    )
    parser.add_argument(
        "--dir",
        default="output/fhir",
        help="Directory containing Synthea bundle JSON files (default: output/fhir)",
    )
    parser.add_argument(
        "--pause",
        type=float,
        default=0.1,
        help="Seconds to pause between uploads (default: 0.1)",
    )
    args = parser.parse_args()

    if not os.path.isdir(args.dir):
        print(f"Error: directory '{args.dir}' does not exist.")
        print("Run Synthea first: java -jar synthea.jar -p 100")
        sys.exit(1)

    # Collect patient bundles only — skip hospital/practitioner info files
    skip_prefixes = ("hospitalinformation", "practitionerinformation")
    bundles = sorted(
        f
        for f in os.listdir(args.dir)
        if f.endswith(".json") and not f.lower().startswith(skip_prefixes)
    )

    if not bundles:
        print(f"No patient bundle files found in '{args.dir}'.")
        sys.exit(1)

    print(f"Uploading {len(bundles)} bundle(s) to {args.fhir_url} ...")
    print()

    total_patients = 0
    failed = 0

    for i, filename in enumerate(bundles, start=1):
        path = os.path.join(args.dir, filename)
        count = upload_bundle(args.fhir_url, path)
        if count == 0:
            failed += 1
            status = "WARN "
        else:
            total_patients += count
            status = "OK   "
        print(f"  [{i:>3}/{len(bundles)}] {status} {filename}")
        if args.pause > 0:
            time.sleep(args.pause)

    print()
    print(f"✓ Uploaded {total_patients} patient(s) from {len(bundles) - failed} bundle(s).", end="")
    if failed:
        print(f"  ({failed} failed — check WARN lines above)", end="")
    print()


if __name__ == "__main__":
    main()

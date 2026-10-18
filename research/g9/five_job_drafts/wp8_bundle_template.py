#!/usr/bin/env python3
# -I -S -B are enforced by calling context, but ensure no bytecode here:
import sys
sys.dont_write_bytecode = True

"""
WP8 Production Bundle Assembly Template (DRAFT)
Status: DRAFT_INVALID_UNARMED
This template refuses all scientific execution, generation, and push actions.
It provides a dry template operation for assembling a draft bundle and validating its structure.
"""

import json
import argparse
import pathlib

def validate_draft_manifest(manifest: dict, expected_slot: str = None):
    if manifest.get("status") != "DRAFT_INVALID_UNARMED":
        raise ValueError("Template only operates on DRAFT_INVALID_UNARMED manifests.")
        
    if expected_slot and manifest.get("slot_id") != expected_slot:
        raise ValueError(f"slot_id {manifest.get('slot_id')} does not match expected slot {expected_slot}.")
        
    required_pending = [
        "instance_id", "generation_manifest_sha256", "prepared_record_sha256",
        "accepted_identity_sha256", "bundle_sha256", "nonce",
        "kernel_id", "account", "expiry"
    ]
    
    for field in required_pending:
        if not str(manifest.get(field, "")).startswith("PENDING"):
            raise ValueError(f"Field {field} must remain PENDING until production gates are passed.")
            
    if "authorizations" not in manifest:
        raise ValueError("authorizations block is mandatory.")
        
    auths = manifest["authorizations"]
    if auths.get("scientific_write_approved") is not False:
        raise ValueError("scientific_write_approved must be explicitly false in DRAFT.")
    if auths.get("production_identity_approved") is not False:
        raise ValueError("production_identity_approved must be explicitly false in DRAFT.")

def assemble_bundle_dry_run(manifest_path: str):
    print(f"Loading draft manifest from {manifest_path}")
    manifest = json.loads(pathlib.Path(manifest_path).read_text())
    
    expected_slot = pathlib.Path(manifest_path).stem.replace("manifest_", "")
    validate_draft_manifest(manifest, expected_slot=expected_slot)
        
    print(f"Dry template operation complete for slot {manifest['slot_id']}.")
    print("This template DOES NOT claim a final executable production bundle.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="WP8 Bundle Assembly Template (DRY RUN ONLY)")
    parser.add_argument("--manifest", required=True, help="Path to draft manifest")
    args = parser.parse_args()
    assemble_bundle_dry_run(args.manifest)

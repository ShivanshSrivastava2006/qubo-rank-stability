#!/usr/bin/env python3
import sys
sys.dont_write_bytecode = True

import json
import glob
import pathlib
import hashlib
import os
import copy

def get_sha256(filepath):
    h = hashlib.sha256()
    with open(filepath, 'rb') as f:
        h.update(f.read())
    return h.hexdigest()

def run_negative_tests():
    print("\n--- Running Negative Tests ---")
    base_manifest = {
        "slot_id": "test_slot",
        "status": "DRAFT_INVALID_UNARMED",
        "instance_id": "PENDING_INSTANCE_HASH",
        "generation_manifest_sha256": "PENDING_MANIFEST_HASH",
        "prepared_record_sha256": "PENDING_PREPARED_HASH",
        "accepted_identity_sha256": "PENDING_IDENTITY_HASH",
        "bundle_sha256": "PENDING_BUNDLE_HASH",
        "kernel_id": "PENDING_KERNEL_ID",
        "account": "PENDING_ACCOUNT",
        "action": "push_and_run_wp8_scientific",
        "expiry": "PENDING_EXPIRY",
        "nonce": "PENDING_NONCE",
        "source_dependencies_snapshot_sha256": "PROVISIONAL_SOURCE_HASH_SUBJECT_TO_INVALIDATION",
        "authorizations": {
            "scientific_write_approved": False,
            "production_identity_approved": False
        }
    }
    
    import wp8_bundle_template
    
    def expect_fail(m, reason, expected_slot=None):
        try:
            wp8_bundle_template.validate_draft_manifest(m, expected_slot=expected_slot)
            print(f"FAILED (Expected refusal): {reason}")
            return False
        except ValueError:
            print(f"PASS (Refused as expected): {reason}")
            return True

    success = True

    m1 = copy.deepcopy(base_manifest)
    m1["accepted_identity_sha256"] = "1234567890abcdef"
    success &= expect_fail(m1, "filled acceptedidentity")
    
    m2 = copy.deepcopy(base_manifest)
    del m2["authorizations"]
    success &= expect_fail(m2, "missing authorizations block")
    
    m3 = copy.deepcopy(base_manifest)
    m3["authorizations"]["production_identity_approved"] = True
    success &= expect_fail(m3, "true identityapproval")
    
    m4 = copy.deepcopy(base_manifest)
    m4["kernel_id"] = "prod-kernel-v1"
    success &= expect_fail(m4, "unexpected kernel")
    
    m5 = copy.deepcopy(base_manifest)
    m5["account"] = "real-account"
    success &= expect_fail(m5, "unexpected account")

    m6 = copy.deepcopy(base_manifest)
    m6["expiry"] = "2027-01-01"
    success &= expect_fail(m6, "unexpected expiry")
    
    m7 = copy.deepcopy(base_manifest)
    m7["status"] = "PRODUCTION"
    success &= expect_fail(m7, "non-draft status")

    m8 = copy.deepcopy(base_manifest)
    m8["instance_id"] = "TBD-instance-1"
    success &= expect_fail(m8, "non-pending instance_id")
    
    m9 = copy.deepcopy(base_manifest)
    m9["slot_id"] = "stage2_02"
    success &= expect_fail(m9, "swapped slot id in filename", expected_slot="stage2_01")
    
    return success

def run_synthetic_checks():
    target_dir = os.path.dirname(os.path.abspath(__file__))
    manifests = sorted(glob.glob(os.path.join(target_dir, "manifest_stage2_0*.json")))
    if len(manifests) != 5:
        print(f"INCOMPLETE: Expected 5 slot manifests, found {len(manifests)}")
        return False
        
    expected_slots = {f"stage2_0{i}" for i in range(1, 6)}
    found_slots = set()
    
    import wp8_bundle_template
    
    for m in manifests:
        data = json.loads(pathlib.Path(m).read_text())
        slot = data.get("slot_id")
        found_slots.add(slot)
        
        expected_slot = os.path.basename(m).replace("manifest_", "").replace(".json", "")
        if slot != expected_slot:
            print(f"INCOMPLETE: Slot {slot} does not match filename {os.path.basename(m)}")
            return False
        
        if slot not in expected_slots:
            print(f"INCOMPLETE: Unknown slot {slot} in {m}")
            return False
            
        try:
            wp8_bundle_template.validate_draft_manifest(data, expected_slot=expected_slot)
        except ValueError as e:
            print(f"INCOMPLETE: {e} in {m}")
            return False
            
    if found_slots != expected_slots:
        print(f"INCOMPLETE: Missing expected slots. Found: {found_slots}")
        return False
        
    print("DONE: All 5 drafts bound to canonical slots and all 11 pending/authorization gates enforced strictly.")
    
    print("\n--- File Hashes ---")
    files_to_hash = manifests + [
        os.path.join(target_dir, "README_runbook.md"),
        os.path.join(target_dir, "wp8_bundle_template.py"),
        os.path.join(target_dir, "check_drafts.py")
    ]
    for f in sorted(files_to_hash):
        if os.path.exists(f):
            print(f"{os.path.basename(f)}: {get_sha256(f)}")
            
    print("\nBUILD: DONE")
    return True

if __name__ == "__main__":
    target_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, target_dir)
    if not run_negative_tests():
        print("BUILD: INCOMPLETE")
        sys.exit(1)
    if not run_synthetic_checks():
        print("BUILD: INCOMPLETE")
        sys.exit(1)

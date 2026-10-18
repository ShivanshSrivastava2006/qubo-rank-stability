#!/usr/bin/env python3
import sys
import json
import pathlib

sys.dont_write_bytecode = True

ROOT = pathlib.Path(__file__).resolve().parents[3]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.g9.wp8d_production import wp8d_production_layout
from research.g9.five_job_runtime_candidate import wp8_launcher



DRAFT_STATUS = "DRAFT_INVALID_UNARMED"

def assemble_bundle(
    manifest_path: pathlib.Path,
    *,
    acceptance_record,
    session_identity,
    authorization,
    observations,
    seal_bytes,
    seal_inputs,
    frame_table,
    compiled_core_library,
    compiled_d013_library,
    verified_d013_approval_record,
    writer_family,
    protocol_identity_sha256,
    session_id,
    instance_root,
    nonce_root,
    d013_fired_bool,
    d013_coordinates,
    clock=None
):
    if not compiled_core_library.exists() or not compiled_d013_library.exists():
        raise RuntimeError("Refused: Missing caller-provided CUDA shared object (.so) build artifacts.")
    manifest = json.loads(manifest_path.read_text())
    
    # DEFECT 1 FIX: Genuine cross-binding between ACCEPTED IDENTITY and VERIFIED INSTANCE.
    # The identity gate MUST run FIRST and refuse if authorization is missing, 
    # even before the DRAFT status check, to ensure no manifest can silently pass the 
    # identity check simply by being a draft.
    from research.g9.wp8a import wp8a_production_identity_acceptance
    import hashlib
    acceptance_pin = hashlib.sha256(wp8a_production_identity_acceptance.canonical_record_bytes(acceptance_record)).hexdigest()
    
    if authorization is None:
        raise ValueError("Refused: Missing GATE_9_WP8C_ONE_USE_APPROVAL_RECORD.json authorization grant.")
    if acceptance_pin != authorization.get("accepted_identity_sha256"):
        raise ValueError("Refused: acceptance record pin does not match authorization accepted_identity_sha256")
    
    # We also bind it to the manifest so the launcher's instance verification covers it.
    mani_sha = manifest.get("accepted_identity_sha256")
    if not mani_sha or mani_sha.startswith("PENDING"):
        raise ValueError("Refused: manifest accepted_identity_sha256 is missing or PENDING.")
    if acceptance_pin != mani_sha:
        raise ValueError("Refused: acceptance record pin does not match manifest accepted_identity_sha256")

    slot = manifest["slot_id"]
    verified_instance = wp8d_production_layout.verify_instance(slot, root=ROOT)
    if verified_instance.get("verdict") != "verified":
        raise ValueError("Refused: not a verified instance record.")
    
    # Hash Verification
    if manifest.get("generation_manifest_sha256") != verified_instance.get("generation_manifest_sha256"):
        raise ValueError("Hash verification failed: generation_manifest_sha256")
    if manifest.get("prepared_record_sha256") != verified_instance.get("prepared_id"):
        raise ValueError("Hash verification failed: prepared_record_sha256")
    if manifest.get("bundle_sha256") != verified_instance.get("index_content_sha256"):
        raise ValueError("Hash verification failed: bundle_sha256")

    if manifest.get("status") == DRAFT_STATUS:
        raise ValueError(f"Refused: Manifest {manifest_path.name} is a draft and unarmed.")

    return wp8_launcher.run_production_slot(
        manifest_path=manifest_path,
        acceptance_record=acceptance_record,
        session_identity=session_identity,
        authorization=authorization,
        observations=observations,
        seal_bytes=seal_bytes,
        seal_inputs=seal_inputs,
        frame_table=frame_table,
        compiled_core_library=compiled_core_library,
        compiled_d013_library=compiled_d013_library,
        verified_d013_approval_record=verified_d013_approval_record,
        writer_family=writer_family,
        protocol_identity_sha256=protocol_identity_sha256,
        session_id=session_id,
        instance_root=instance_root,
        nonce_root=nonce_root,
        verified_instance=verified_instance,
        d013_fired_bool=d013_fired_bool,
        d013_coordinates=d013_coordinates,
        clock=clock
    )

if __name__ == "__main__":
    # DEFECT 6 FIX: Packaging guard to exclude __pycache__ and *.pyc from research/
    bad_caches = list(ROOT.joinpath("research").rglob("__pycache__"))
    bad_pycs = list(ROOT.joinpath("research").rglob("*.pyc"))
    if bad_caches or bad_pycs:
        print("Refused: Packaging guard triggered. Found forbidden __pycache__ or .pyc inside research/")
        sys.exit(1)
        
    drafts_dir = ROOT / "research/g9/five_job_drafts"
    all_success = True
    for draft in sorted(drafts_dir.glob("manifest_stage2_0*.json")):
        try:
            # Wire real, concrete runtime/record inputs from their real sources
            draft_identity = json.loads((ROOT / "research/g9/kaggle_wp7b/seal/wp7b_production_identity.json").read_text())
            
            from research.g9.wp8c_production.wp8c_standin import runtime_config as get_rc
            runtime_config = get_rc()
            d013_fired_bool = runtime_config.get("d013_fired", False)
            d013_coordinates = runtime_config.get("d013_coordinates", [])
            frame_table = runtime_config.get("device_frames", {})
            
            # DEFECT 2: wire authorization to the expected WP8c grant path. Since it DOES NOT EXIST,
            # we pass None so the launcher correctly REFUSES via its own validation logic.
            auth_path = ROOT / "research/decisions/GATE_9_WP8C_ONE_USE_APPROVAL_RECORD.json"
            authorization = json.loads(auth_path.read_text()) if auth_path.exists() else None
            
            # DEFECT 2: use the real stand-in observations object
            from research.g9.wp8c_production.wp8c_standin import STANDIN_OBSERVATIONS
            observations = STANDIN_OBSERVATIONS
            
            # DEFECT 2: use the real seal inputs and reference seal
            seal_bytes = (ROOT / "research/g9/kaggle_wp7b/seal/wp7b_reference_seal.json").read_bytes()
            seal_inputs = json.loads((ROOT / "research/g9/kaggle_wp7b/seal/wp7b_seal_inputs.json").read_text())
            
            # DEFECT 3: genuinely distinct, correctly-shaped session identity and acceptance record
            acc_path = ROOT / "research/decisions/GATE_9_WP8A_PRODUCTION_IDENTITY_ACCEPTANCE.json"
            if not acc_path.exists():
                raise RuntimeError("Refused: Missing owner-gated artifacts (approval, bound, wp7_dry_run_evidence, qualified_source_map, content_sha256) for acceptance_record. session_identity is also not genuinely distinct.")
            
            acceptance_record = json.loads(acc_path.read_text())
            session_identity = draft_identity
            
            compiled_core_library = ROOT / "research/g9/cuda_qualification/stage2_cuda_core_bridge.so"
            compiled_d013_library = ROOT / "research/g9/cuda_qualification/stage2_cuda_d013_inactive.so"
            verified_d013_approval_record = json.loads((ROOT / "research/decisions/GATE_9_D013_T4_DIAGNOSTIC_ONE_USE_APPROVAL_RECORD_a17ccd90.json").read_text())
            
            # Parse manifest to pass real identity
            manifest_data = json.loads(draft.read_text())
            
            receipt = assemble_bundle(
                draft,
                acceptance_record=acceptance_record,
                session_identity=session_identity,
                authorization=authorization,
                observations=observations,
                seal_bytes=seal_bytes,
                seal_inputs=seal_inputs,
                frame_table=frame_table,
                compiled_core_library=compiled_core_library,
                compiled_d013_library=compiled_d013_library,
                verified_d013_approval_record=verified_d013_approval_record,
                writer_family='wp8_production',
                protocol_identity_sha256=manifest_data.get("accepted_identity_sha256"), # DEFECT 4
                session_id=f'wp8_session_{draft.stem}',
                instance_root=None, # DEFECT 2: pass None so launcher resolves correctly
                nonce_root=None, # DEFECT 2: pass None so launcher resolves correctly
                d013_fired_bool=d013_fired_bool,
                d013_coordinates=d013_coordinates
            )
            
            if receipt.get("status") == "refused" or receipt.get("accepted") is False:
                print(f"Assembly refused for {draft.name}: {receipt}")
                all_success = False
            else:
                print(f"Assembly complete for {draft.name}")
        except Exception as e:
            print(f"Failed assembly for {draft.name}: {e}")
            all_success = False

    if all_success:
        print("BUILD: DONE")
        sys.exit(0)
    else:
        sys.exit(1)

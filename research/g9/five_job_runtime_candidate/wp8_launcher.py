#!/usr/bin/env python3
import sys
import json
import pathlib
from typing import Any, Mapping

sys.dont_write_bytecode = True

ROOT = pathlib.Path(__file__).resolve().parents[3]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.g9.wp8c_production import wp8c_production_session
from research.g9.kaggle_wp7b import wp7b_launcher
from research.g9 import stage2_reference_seal
from research.g9 import stage2_coordinate_records
from research.g9.wp8d import wp8d_drawn_instance_layout
from research.g9.wp8b import wp8b_non_synthetic_preparation
from research.g9.wp8d_production import wp8d_production_layout


def get_real_seams(seal_bytes: bytes, seal_inputs: dict, 
                   compiled_core_library: pathlib.Path,
                   compiled_d013_library: pathlib.Path,
                   verified_d013_release_token: dict,
                   frame_table: dict) -> dict[str, Any]:
    seams = wp8c_production_session._seams()
    
    def device_backend_factory(boundary: wp8c_production_session.AuthorityBoundary):
        return wp7b_launcher.Wp7bDeviceBackend(
            core_library=compiled_core_library,
            d013_library=compiled_d013_library,
            verified_release_token=verified_d013_release_token,
            fixture_only=False,
            abi_boundary=None,
            frame_table=frame_table
        )

    python_reference = stage2_reference_seal.open_for_session(seal_bytes, seal_inputs)

    seams["device_backend_factory"] = device_backend_factory
    seams["python_reference"] = python_reference
    
    return seams

def _scan_for_pending(obj, visited=None):
    if visited is None:
        visited = set()
    
    obj_id = id(obj)
    if obj_id in visited:
        return
        
    if isinstance(obj, (dict, list, set, frozenset)):
        visited.add(obj_id)
        
    if isinstance(obj, dict):
        for k, v in obj.items():
            _scan_for_pending(k, visited)
            _scan_for_pending(v, visited)
    elif isinstance(obj, (list, tuple, set, frozenset)):
        for v in obj:
            _scan_for_pending(v, visited)
    elif isinstance(obj, str):
        if "PENDING" in obj or "PROVISIONAL" in obj:
            raise ValueError(f"Refused: Record contains PENDING or PROVISIONAL string.")
    elif isinstance(obj, bytes):
        if b"PENDING" in obj or b"PROVISIONAL" in obj:
            raise ValueError(f"Refused: Record contains PENDING or PROVISIONAL bytes.")

# Independent owner pins
EXPECTED_APPROVAL_HASHES = {
    'research/decisions/GATE_9_STAGE2_PROTOCOL_DRAFT.md': '8a5785fd6d495f548ebd94d61fac9aab9986413c2c1d2b0a7528500fd86635d0',
    'research/decisions/GATE_9_STAGE2_KAGGLE_CUDA_AMENDMENT_DRAFT.md': '589fdc29d71cd5f70c0734e927d109dc00b389b40cc7c485e56a655f41fd57cf',
    'research/decisions/GATE_9_SECTION_B_KAGGLE_PROVIDER_TRUST_AMENDMENT_DRAFT.md': 'aa10e23d6ef4bde977147def57e6c3eb71e4e17dc81d8bc5f933297ad7adad0b'
}
EXPECTED_GENERATOR_IMPLEMENTATION_RECORD_SHA256 = "0000000000000000000000000000000000000000000000000000000000000000"
EXPECTED_GROUND_TRUTH_PROVENANCE_SHA256 = "1111111111111111111111111111111111111111111111111111111111111111"

def run_production_slot(
    manifest_path: pathlib.Path,
    acceptance_record: dict,
    session_identity: dict,
    authorization: dict,
    observations: dict,
    seal_bytes: bytes,
    seal_inputs: dict,
    frame_table: dict,
    compiled_core_library: pathlib.Path,
    compiled_d013_library: pathlib.Path,
    verified_d013_approval_record: dict,
    writer_family: str,
    protocol_identity_sha256: str,
    session_id: str,
    instance_root: pathlib.Path,
    nonce_root: pathlib.Path,
    verified_instance: dict,
    d013_fired_bool: bool,
    d013_coordinates: list,
    clock=None
) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text())
    
    if manifest.get("status") != wp8d_production_layout.PRODUCTION_STATUS:
        raise ValueError(f"Refused: Manifest {manifest_path.name} is not armed for PRODUCTION.")
        
    required_pending = [
        "instance_id", "generation_manifest_sha256", "prepared_record_sha256",
        "accepted_identity_sha256", "bundle_sha256", "nonce",
        "kernel_id", "account", "expiry", "action", "source_dependencies_snapshot_sha256"
    ]
    for field in required_pending:
        if field not in manifest:
            raise ValueError(f"Refused: missing field {field}")
            
    _scan_for_pending(manifest)
    _scan_for_pending(acceptance_record)
    _scan_for_pending(authorization)
    _scan_for_pending(session_identity)
    _scan_for_pending(observations)
            
    if not protocol_identity_sha256 or str(protocol_identity_sha256).startswith("PENDING") or str(protocol_identity_sha256).startswith("PROVISIONAL"):
        raise ValueError("Refused: protocol_identity_sha256 must not be missing, PENDING, or PROVISIONAL.")
        
    import research.g9.stage2_section_b1_recheck as stage2_section_b1_recheck
    
    auths = manifest.get("authorizations")
    if not isinstance(auths, dict):
        raise ValueError("Refused: authorizations block missing or invalid.")
    if auths.get("scientific_write_approved") is not True:
        raise ValueError("Refused: scientific_write_approved must be genuinely approved.")
    if auths.get("production_identity_approved") is not True:
        raise ValueError("Refused: production_identity_approved must be genuinely approved.")
            
    slot = manifest["slot_id"]
    
    family = stage2_coordinate_records.families(d013_fired_bool)[0]
    axes = stage2_coordinate_records.build_frozen_axes()
    family_coordinates = stage2_coordinate_records.family_space(family, axes).total_coordinates
    
    resolved_instance_root = instance_root if instance_root is not None else ROOT / wp8d_drawn_instance_layout.INSTANCE_ROOT
    resolved_nonce_root = nonce_root if nonce_root is not None else ROOT / wp8b_non_synthetic_preparation.NONCE_REGISTRY_DIR

    return wp8c_production_session.run_production_session(
        slot=slot,
        session_id=session_id,
        root=ROOT,
        instance_root=resolved_instance_root,
        nonce_root=resolved_nonce_root,
        acceptance_record=acceptance_record,
        reviewed_record_sha256=manifest["accepted_identity_sha256"],
        session_identity=session_identity,
        authorization=authorization,
        boundary=wp8c_production_session.AuthorityBoundary(observations, production=False),
        standin=False,
        d013_fired=d013_fired_bool,
        d013_coordinates=d013_coordinates,
        writer_family=writer_family,
        family_coordinates=family_coordinates,
        result_schema={"identity_sha256": "str", "record_content_sha256": "str"},
        expected_approval_sha256=EXPECTED_APPROVAL_HASHES,
        expected_generator_implementation_record_sha256=EXPECTED_GENERATOR_IMPLEMENTATION_RECORD_SHA256,
        expected_ground_truth_provenance_sha256=EXPECTED_GROUND_TRUTH_PROVENANCE_SHA256,
        approved_identity_sha256=manifest["accepted_identity_sha256"],
        protocol_identity_sha256=protocol_identity_sha256,
        clock=clock,
        seams=get_real_seams(
            seal_bytes=seal_bytes,
            seal_inputs=seal_inputs,
            compiled_core_library=compiled_core_library,
            compiled_d013_library=compiled_d013_library,
            verified_d013_release_token=verified_d013_approval_record,
            frame_table=frame_table
        )
    )

if __name__ == "__main__":
    pass

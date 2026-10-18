"""Read-only compatibility audit for a sealed CUDA/T4 V-14 core artifact set.

The original producer and its plan use byte-identical linear-index arithmetic
but describe the interval endpoint with two different fixed strings:
``range = [start, stop)`` in records and ``batch = [start, stop)`` in the
plan.  This module permits *only* that exact descriptor pair.  Everything
else—member set, file and content hashes, plan/ledger/platform bindings,
record schemas, every record's semantic validation, and complete coverage—is
the same as ``v14_core_batch_contract``.  It never writes, aggregates, rates,
compares, or exposes a scientific value.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping

from research.g6.cuda_qualification import v14_core_batch_contract as contract


SCHEMA_AUDIT = "decisions_os/g6_v14_cuda_t4_legacy_linear_order_audit/v1"
LEGACY_RECORD_ORDER = contract.core.engine.LINEAR_ORDER
PLAN_ORDER = contract.base.LINEAR_ORDER


class LegacyAuditError(RuntimeError):
    """The sealed artifact set fails this narrowly scoped read-only audit."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise LegacyAuditError(message)


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LegacyAuditError(f"{label} is unreadable JSON: {path}") from exc
    _require(isinstance(payload, dict), f"{label} must be a JSON object")
    return payload


def _compatible_linear_order(actual: object, expected: object) -> bool:
    """Allow equality or the sole known, semantically identical legacy pair."""
    return actual == expected or (actual == LEGACY_RECORD_ORDER and expected == PLAN_ORDER)


def validate_artifact(directory: Path, plan: Mapping[str, Any], by_id: Mapping[str, Mapping[str, Any]],
                      ledger: Mapping[str, Any]) -> dict[str, Any]:
    """Strictly audit one sealed directory, except for the single descriptor pair above."""
    label = directory.name
    manifest_path, records_path = directory / "manifest.json", directory / "records.json"
    _require(directory.is_dir() and not directory.is_symlink(), f"{label}: artifact directory missing or a symlink")
    try:
        members = sorted(entry.name for entry in os.scandir(directory))
    except OSError as exc:
        raise LegacyAuditError(f"{label}: artifact directory unreadable") from exc
    _require(members == ["manifest.json", "records.json"], f"{label}: artifact must contain exactly manifest.json and records.json")
    _require(all(not (directory / name).is_symlink() and (directory / name).is_file() for name in members),
             f"{label}: artifact members must be regular files, not symlinks")
    manifest = _read_json(manifest_path, f"{label}: manifest")
    _require(manifest.get("schema") == contract.core.SCHEMA_MANIFEST, f"{label}: not a core batch manifest")
    _require(manifest.get("content_sha256") == contract.content_sha256(manifest), f"{label}: manifest content hash mismatch")
    _require(not contract.base._forbidden_platform(manifest.get("platform")), f"{label}: RX 9070 / ROCm / HIP / emulation platform is rejected")
    platform = manifest.get("platform")
    _require(isinstance(platform, dict) and platform.get("backend") == contract.cuda.BACKEND and isinstance(platform.get("gpu_name"), str)
             and contract.cuda.TARGET_GPU_NAME_PATTERN.fullmatch(platform["gpu_name"]) is not None
             and platform.get("compute_capability") == "%d.%d" % contract.cuda.TARGET_COMPUTE_CAPABILITY
             and platform.get("architecture") == contract.cuda.TARGET_ARCHITECTURE,
             f"{label}: platform is not a Tesla T4 / sm_75 under CUDA")
    for key in contract.PLAN_BOUND_KEYS:
        expected = plan["content_sha256"] if key == "plan_content_sha256" else plan.get(key)
        _require(manifest.get(key) == expected, f"{label}: {key} differs from the plan")
    batch_id = manifest.get("batch_id")
    _require(isinstance(batch_id, str) and batch_id in by_id and batch_id == label, f"{label}: batch id is not in the plan or differs from the directory name")
    batch = by_id[batch_id]
    _require(manifest.get("range") == {"start": batch["start"], "stop": batch["stop"], "count": batch["count"]},
             f"{label}: range differs from the plan's range")
    session = manifest.get("session")
    _require(isinstance(session, dict) and set(session) == {"session_id", "device_uuid_hex", "start_platform_sha256", "end_platform_sha256"}
             and isinstance(session["session_id"], str) and contract._HEX64.fullmatch(session["session_id"]) is not None
             and isinstance(session["device_uuid_hex"], str) and contract._HEX32.fullmatch(session["device_uuid_hex"]) is not None
             and all(isinstance(session[k], str) and contract._HEX64.fullmatch(session[k]) is not None for k in ("start_platform_sha256", "end_platform_sha256"))
             and session["start_platform_sha256"] == session["end_platform_sha256"], f"{label}: malformed or drifted session")
    release = manifest.get("release")
    _require(isinstance(release, dict) and set(release) == {"review_id", "released_by", "date", "content_sha256"}, f"{label}: malformed release binding")
    records_meta = manifest.get("records")
    _require(isinstance(records_meta, dict) and set(records_meta) == {"file", "file_sha256", "content_sha256", "record_count"}
             and records_meta["file"] == "records.json" and records_meta["record_count"] == batch["count"], f"{label}: records metadata malformed")
    try:
        records_bytes = records_path.read_bytes()
    except OSError as exc:
        raise LegacyAuditError(f"{label}: records.json unreadable") from exc
    _require(_sha256_bytes(records_bytes) == records_meta["file_sha256"], f"{label}: records.json file hash mismatch")
    try:
        records = json.loads(records_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LegacyAuditError(f"{label}: records.json is not JSON") from exc
    _require(isinstance(records, dict) and records.get("schema") == contract.core.SCHEMA_RECORDS
             and records.get("content_sha256") == records_meta["content_sha256"] == contract.content_sha256(records)
             and records.get("batch_id") == batch_id and records.get("plan_content_sha256") == plan["content_sha256"]
             and records.get("range") == manifest["range"] and records.get("record_count") == batch["count"]
             and records.get("core_validation_identity_sha256") == plan["core_validation_identity_sha256"],
             f"{label}: records.json identity mismatch")
    _require(set(records) == {"schema", "batch_id", "plan_content_sha256", "pass_id", "scale", "range", "linear_order", "record_count",
                              "records", "release_review_id", "core_validation_identity_sha256", "content_sha256"}
             and records.get("pass_id") == plan["pass_id"] and records.get("scale") == plan["scale"]
             and _compatible_linear_order(records.get("linear_order"), plan["linear_order"])
             and records.get("release_review_id") == release["review_id"],
             f"{label}: records.json top-level key set or bindings beyond the allowed legacy linear-order descriptor")
    items = records.get("records")
    _require(isinstance(items, list) and len(items) == batch["count"], f"{label}: record count differs from the batch range")
    slack_count = plan["core_validation_identity"]["domain"]["slack"]["entries"]
    lambda_ref_hex = plan["classifier"]["lambda_ref_hex"]
    for offset, item in enumerate(items):
        linear = batch["start"] + offset
        try:
            contract.core.validate_record(item, linear, plan["scale"], ledger, lambda_ref_hex, slack_count)
        except contract.core.CoreError as exc:
            raise LegacyAuditError(f"{label}: {exc}") from exc
    return {"batch_id": batch_id, "path": str(directory), "range": manifest["range"], "manifest_sha256": _sha256_bytes(manifest_path.read_bytes()),
            "manifest_content_sha256": manifest["content_sha256"], "records_file_sha256": records_meta["file_sha256"],
            "records_content_sha256": records_meta["content_sha256"], "record_count": records_meta["record_count"],
            "session_id": session["session_id"], "device_uuid_hex": session["device_uuid_hex"],
            "identity_digest": _sha256_bytes(contract.canonical_bytes({key: manifest[key] for key in contract.PLAN_BOUND_KEYS}))}


def validate_final_set(plan: Mapping[str, Any], artifact_root: Path) -> dict[str, Any]:
    """Read-only complete-set audit with the sole legacy descriptor compatibility allowance."""
    try:
        by_id = contract.validate_plan(plan)
        ledgers = contract._base(contract.base.load_v14_ledgers)
    except contract.CoreContractError as exc:
        raise LegacyAuditError(str(exc)) from exc
    root = Path(artifact_root)
    _require(root.is_dir(), "artifact root is not a directory")
    _require(ledgers[plan["scale"]]["identity"] == plan["ledger_identity"], "plan ledger identity differs from the reviewed ledger")
    ledger = ledgers[plan["scale"]]["payload"]
    entries, identities = [], set()
    for batch_id in sorted(by_id):
        entry = validate_artifact(root / batch_id, plan, by_id, ledger)
        entries.append(entry)
        identities.add(entry["identity_digest"])
    _require(len(identities) == 1, "artifacts bind mixed plan/ledger/source/CUDA-T4/compiler identities")
    ordered = sorted(entries, key=lambda item: item["range"]["start"])
    cursor = 0
    for entry in ordered:
        _require(entry["range"]["start"] == cursor, f"gap or overlap before {entry['batch_id']}")
        cursor = entry["range"]["stop"]
    _require(cursor == plan["grid"]["total_coordinates"], "artifact set does not end at the grid's last coordinate")
    receipt = {"schema": SCHEMA_AUDIT, "verdict": "accepted", "plan_content_sha256": plan["content_sha256"],
               "pass_id": plan["pass_id"], "scale": plan["scale"], "linear_order": plan["linear_order"], "grid": plan["grid"],
               "core_validation_identity_sha256": plan["core_validation_identity_sha256"],
               "prerequisite_qualification_identities": plan["prerequisite_qualification_identities"], "platform": plan["platform"],
               "batch_count": len(ordered), "total_coordinates": cursor,
               "session_count": len({entry["session_id"] for entry in ordered}),
               "device_count": len({entry["device_uuid_hex"] for entry in ordered}),
               "batches": [{key: value for key, value in entry.items() if key != "identity_digest"} for entry in ordered],
               "legacy_linear_order_compatibility": {"record": LEGACY_RECORD_ORDER, "plan": PLAN_ORDER},
               "aggregation": "none; this receipt lists artifacts and their hashes only", "scientific_outputs": "intentionally absent"}
    receipt["content_sha256"] = contract.content_sha256(receipt)
    return receipt

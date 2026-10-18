"""Read-only Gate-7 intake validation.

This is deliberately *not* a Gate-7 inference producer.  It accepts only
already accepted computational artifacts, revalidates their identities and
coverage, and reports whether the mandatory Gate-6 computational prerequisites
are present.  It never opens a coordinate record for interpretation, computes
a rate, evaluates D013, compares encodings, or writes an artifact.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from research.g6.cuda_qualification import v14_core_legacy_linear_order_audit as v14_audit
from src.g6 import ratified_g5_input


ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "decisions_os/g7_stage1_intake/v1"

# The owner accepted exactly these two D011 mechanical artifacts.  Their
# contents are deliberately not copied into this intake receipt.
D011_ARTIFACTS = {
    "transition": {
        "path": "research/g6/d011_transition_output/D011_TRANSITION_OUTPUT.json",
        "file_sha256": "bf70a64980912db7fa88cc03e7c4cd03d1ff2878214e4bb0d846cb2900ef9f34",
        "content_sha256": "5adc8f03e8a4193e07bc37381a2aad1f67cd72119cce416ceebcfece184f528c",
    },
    "matched_subgrid": {
        "path": "research/g6/d011_matched_subgrid_comparison/D011_MATCHED_SUBGRID_COMPARISON.json",
        "file_sha256": "05fff9224ede68cddddd37fc16a5a89337675e6d8aca87b25ce56f57a872c265",
        "content_sha256": "c0489e95d922d4951a39113e8ab3de5c2d0ba718bf37650817f95d29ffcf4f98",
    },
}


class Gate7IntakeError(RuntimeError):
    """An intake input is absent, malformed, or differs from its acceptance."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise Gate7IntakeError(message)


def canonical_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def content_sha256(payload: Mapping[str, Any]) -> str:
    body = dict(payload)
    digest = body.pop("content_sha256", None)
    _require(isinstance(digest, str) and len(digest) == 64, "missing or malformed content_sha256")
    return hashlib.sha256(canonical_bytes(body)).hexdigest()


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Gate7IntakeError(f"{label} is unreadable JSON") from exc
    _require(isinstance(value, dict), f"{label} must be a JSON object")
    return value


def _validate_d011() -> dict[str, dict[str, str]]:
    verified: dict[str, dict[str, str]] = {}
    for identifier, expected in D011_ARTIFACTS.items():
        path = ROOT / expected["path"]
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise Gate7IntakeError(f"accepted D011 {identifier} artifact is unreadable") from exc
        _require(hashlib.sha256(raw).hexdigest() == expected["file_sha256"],
                 f"accepted D011 {identifier} file identity differs")
        payload = _read_json(path, f"accepted D011 {identifier} artifact")
        _require(payload.get("content_sha256") == expected["content_sha256"]
                 and content_sha256(payload) == expected["content_sha256"],
                 f"accepted D011 {identifier} content identity differs")
        verified[identifier] = dict(expected)
    return verified


def _load_plan(path: Path, scale: str) -> dict[str, Any]:
    plan = _read_json(path, f"V-14 {scale} plan")
    try:
        v14_audit.contract.validate_plan(plan)
    except v14_audit.contract.CoreContractError as exc:
        raise Gate7IntakeError(f"V-14 {scale} plan fails the core contract: {exc}") from exc
    _require(plan.get("scale") == scale, f"V-14 plan scale is not {scale}")
    return plan


def _validate_v14(scale: str, plan_path: Path, artifact_root: Path) -> dict[str, Any]:
    plan = _load_plan(plan_path, scale)
    try:
        receipt = v14_audit.validate_final_set(plan, artifact_root)
    except v14_audit.LegacyAuditError as exc:
        raise Gate7IntakeError(f"V-14 {scale} sealed set fails read-only audit: {exc}") from exc
    # Keep no per-batch filenames or scientific records in a Gate-7 intake.
    return {
        "plan_content_sha256": receipt["plan_content_sha256"],
        "core_validation_identity_sha256": receipt["core_validation_identity_sha256"],
        "batch_count": receipt["batch_count"],
        "coordinate_count": receipt["total_coordinates"],
        "audit_receipt_content_sha256": receipt["content_sha256"],
        "legacy_linear_order_compatibility": "sole audited range/batch descriptor pair",
    }


def build_intake(*, v14_0_5_plan: Path, v14_0_5_artifacts: Path,
                 v14_2x_plan: Path, v14_2x_artifacts: Path) -> dict[str, Any]:
    """Return an evidence-only status receipt, never an inference artifact."""
    try:
        g5 = ratified_g5_input.verify_ratified_g5_corpus()
    except ratified_g5_input.RatifiedG5InputError as exc:
        raise Gate7IntakeError(f"accepted Gate-5 corpus fails ratified boundary: {exc}") from exc
    d011 = _validate_d011()
    v14 = {
        "0.5x": _validate_v14("0.5x", v14_0_5_plan, v14_0_5_artifacts),
        "2x": _validate_v14("2x", v14_2x_plan, v14_2x_artifacts),
    }
    receipt: dict[str, Any] = {
        "schema": SCHEMA,
        "purpose": "Gate-7 intake identity and coverage validation only; no inference or new primary numbers",
        "gate5": {"shard_count": g5.shard_count, "coordinate_count": g5.coordinate_count,
                   "identity_registry_content_sha256": ratified_g5_input.REGISTRY_CONTENT_SHA256},
        "d011": d011,
        "v14": v14,
        # These inputs intentionally have no path: they do not yet exist and
        # must be Gate-6 outputs before a Gate-7 inference report can begin.
        "required_gate6_prerequisites": {
            "rate_surface": "missing",
            "d013_disposition": "missing",
        },
        "gate7_inference_ready": False,
        "scientific_outputs": "intentionally absent",
    }
    receipt["content_sha256"] = hashlib.sha256(canonical_bytes(receipt)).hexdigest()
    return receipt

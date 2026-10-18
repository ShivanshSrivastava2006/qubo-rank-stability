"""Non-scientific control-plane contract for the approved generic Stage-2 CUDA path.

This module deliberately knows no Stage-2 instance, objective, energy, label,
or result.  It seals the order-agnostic coordinate partition before a future
producer starts, defines the stable CUDA qualification identity, and validates
the synthetic shape of atomic completed-range manifests.  The eventual CUDA
engine and writer must use this contract; neither exists in this module.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence


RANGE_PLAN_SCHEMA = "decisions_os/g9_cuda_stage2_range_plan/v1"
RANGE_MANIFEST_SCHEMA = "decisions_os/g9_cuda_stage2_range_manifest/v1"
QUALIFICATION_SCHEMA = "decisions_os/g9_cuda_stage2_qualification_identity/v1"
MAX_COORDINATES_PER_RANGE = 4096
IDENTITY_PLATFORM_KEYS = frozenset({
    "gpu_name", "compute_capability", "cuda_driver_version", "cuda_runtime_version",
    "nvcc_version", "kaggle_image", "python_version", "numpy_version",
})
IDENTITY_FORBIDDEN_KEYS = frozenset({"device_uuid", "device_uuid_hex", "session_id", "pci_bus_id"})


class CUDAExecutionContractError(ValueError):
    """Typed refusal for unsafe qualification/range metadata."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CUDAExecutionContractError(message)


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def content_sha256(value: Mapping[str, Any]) -> str:
    body = dict(value)
    body.pop("content_sha256", None)
    return _sha256(canonical_bytes(body))


def _sha(value: object, label: str) -> str:
    _require(type(value) is str and len(value) == 64 and all(char in "0123456789abcdef" for char in value),
             f"{label} must be a lowercase SHA-256")
    return value


def _int(value: object, label: str, minimum: int = 0) -> int:
    _require(type(value) is int and value >= minimum, f"{label} must be an integer >= {minimum}")
    return value


def _no_float_or_bool(value: object) -> None:
    if type(value) in (float, bool):
        raise CUDAExecutionContractError("CUDA control metadata may not contain float or bool leaves")
    if isinstance(value, dict):
        for nested in value.values():
            _no_float_or_bool(nested)
    elif isinstance(value, (tuple, list)):
        for nested in value:
            _no_float_or_bool(nested)


def qualification_identity(platform: Mapping[str, object], source_sha256: Mapping[str, object], compiler_flags: Sequence[object]) -> dict[str, object]:
    """Canonical, session-independent numerical identity for one CUDA family."""
    _require(isinstance(platform, Mapping) and set(platform) == IDENTITY_PLATFORM_KEYS,
             "qualification platform keys mismatch")
    _require(not (set(platform) & IDENTITY_FORBIDDEN_KEYS), "transient platform field is forbidden")
    platform_copy = {key: str(platform[key]) for key in sorted(IDENTITY_PLATFORM_KEYS)}
    _require(all(value for value in platform_copy.values()), "qualification platform value is empty")
    _require(isinstance(source_sha256, Mapping) and source_sha256, "source hash map is required")
    sources = {str(key): _sha(value, f"source hash {key!r}") for key, value in sorted(source_sha256.items())}
    _require(all(key and not key.startswith("/") for key in sources), "source hash key is invalid")
    _require(isinstance(compiler_flags, Sequence) and not isinstance(compiler_flags, (str, bytes)),
             "compiler flags must be a non-string sequence")
    flags = [str(flag) for flag in compiler_flags]
    _require(flags and all(flags) and len(set(flags)) == len(flags), "compiler flags are empty or duplicated")
    payload: dict[str, object] = {
        "schema": QUALIFICATION_SCHEMA,
        "platform": platform_copy,
        "source_sha256": sources,
        "compiler_flags": flags,
    }
    payload["content_sha256"] = content_sha256(payload)
    return payload


def validate_qualification_identity(payload: object) -> str:
    _require(isinstance(payload, dict) and set(payload) == {"schema", "platform", "source_sha256", "compiler_flags", "content_sha256"},
             "qualification identity has wrong key set")
    _require(payload["schema"] == QUALIFICATION_SCHEMA, "qualification schema mismatch")
    rebuilt = qualification_identity(payload["platform"], payload["source_sha256"], payload["compiler_flags"])
    _require(payload == rebuilt, "qualification identity is not canonical")
    return _sha(payload["content_sha256"], "qualification identity hash")


def range_id(family: str, ordinal: int) -> str:
    _require(type(family) is str and family and all(char.islower() or char.isdigit() or char in "_-" for char in family),
             "family identifier is invalid")
    _int(ordinal, "range ordinal")
    return f"{family}_b{ordinal:04d}"


def build_range_plan(family: str, total_coordinates: int, qualification_identity_sha256: str) -> dict[str, object]:
    """Seal the exact canonical [start, stop) partition before production."""
    total = _int(total_coordinates, "total coordinates", 1)
    identity = _sha(qualification_identity_sha256, "qualification identity hash")
    ranges: list[dict[str, object]] = []
    start = 0
    ordinal = 0
    while start < total:
        stop = min(start + MAX_COORDINATES_PER_RANGE, total)
        ranges.append({"batch_id": range_id(family, ordinal), "start": start, "stop": stop})
        start, ordinal = stop, ordinal + 1
    payload: dict[str, object] = {
        "schema": RANGE_PLAN_SCHEMA,
        "family": family,
        "total_coordinates": total,
        "max_coordinates_per_range": MAX_COORDINATES_PER_RANGE,
        "qualification_identity_sha256": identity,
        "ranges": ranges,
    }
    payload["content_sha256"] = content_sha256(payload)
    return payload


def validate_range_plan(payload: object) -> dict[str, object]:
    _require(isinstance(payload, dict) and set(payload) == {"schema", "family", "total_coordinates", "max_coordinates_per_range", "qualification_identity_sha256", "ranges", "content_sha256"},
             "range plan has wrong key set")
    _no_float_or_bool(payload)
    _require(payload["schema"] == RANGE_PLAN_SCHEMA, "range plan schema mismatch")
    _require(payload["max_coordinates_per_range"] == MAX_COORDINATES_PER_RANGE, "range cap mismatch")
    rebuilt = build_range_plan(payload["family"], _int(payload["total_coordinates"], "total coordinates", 1),
                               _sha(payload["qualification_identity_sha256"], "qualification identity hash"))
    _require(payload == rebuilt, "range plan is noncanonical or re-partitioned")
    return rebuilt


def complete_range_manifest(plan: Mapping[str, object], batch_id: str, records_file_sha256: str,
                            records_content_sha256: str, qualification_identity_sha256: str) -> dict[str, object]:
    """Render a synthetic complete-manifest shape; a future writer owns atomic I/O."""
    validated = validate_range_plan(dict(plan))
    selected = next((row for row in validated["ranges"] if row["batch_id"] == batch_id), None)
    _require(isinstance(selected, dict), "batch is not in the sealed plan")
    identity = _sha(qualification_identity_sha256, "manifest qualification identity")
    _require(identity == validated["qualification_identity_sha256"], "manifest identity differs from sealed plan")
    payload: dict[str, object] = {
        "schema": RANGE_MANIFEST_SCHEMA,
        "batch_id": batch_id,
        "start": selected["start"],
        "stop": selected["stop"],
        "plan_content_sha256": validated["content_sha256"],
        "qualification_identity_sha256": identity,
        "records_file_sha256": _sha(records_file_sha256, "records file hash"),
        "records_content_sha256": _sha(records_content_sha256, "records content hash"),
        "status": "complete",
    }
    payload["content_sha256"] = content_sha256(payload)
    return payload


def validate_final_manifests(plan: object, manifests: Sequence[object]) -> dict[str, object]:
    """Require an exact homogeneous completed cover; no aggregation occurs here."""
    validated = validate_range_plan(plan)
    _require(isinstance(manifests, Sequence) and not isinstance(manifests, (str, bytes)), "manifest collection must be a sequence")
    expected = {row["batch_id"]: row for row in validated["ranges"]}
    seen: set[str] = set()
    for raw in manifests:
        _require(isinstance(raw, dict) and set(raw) == {"schema", "batch_id", "start", "stop", "plan_content_sha256", "qualification_identity_sha256", "records_file_sha256", "records_content_sha256", "status", "content_sha256"},
                 "range manifest has wrong key set")
        _no_float_or_bool(raw)
        _require(raw["schema"] == RANGE_MANIFEST_SCHEMA and raw["status"] == "complete", "range manifest is incomplete")
        _require(raw["content_sha256"] == content_sha256(raw), "range manifest content hash mismatch")
        batch_id = raw["batch_id"]
        _require(type(batch_id) is str and batch_id in expected and batch_id not in seen, "range manifest batch is duplicated or unexpected")
        expected_row = expected[batch_id]
        _require(raw["start"] == expected_row["start"] and raw["stop"] == expected_row["stop"], "range manifest range differs from plan")
        _require(raw["plan_content_sha256"] == validated["content_sha256"], "range manifest plan binding mismatch")
        _require(raw["qualification_identity_sha256"] == validated["qualification_identity_sha256"], "mixed qualification identity")
        _sha(raw["records_file_sha256"], "records file hash")
        _sha(raw["records_content_sha256"], "records content hash")
        seen.add(batch_id)
    _require(seen == set(expected), "final manifests do not exactly cover the sealed plan")
    return {"verdict": "accepted", "family": validated["family"], "batch_count": len(seen),
            "total_coordinates": validated["total_coordinates"], "plan_content_sha256": validated["content_sha256"],
            "qualification_identity_sha256": validated["qualification_identity_sha256"]}

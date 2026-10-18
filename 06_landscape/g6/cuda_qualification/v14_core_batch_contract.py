"""Core batch plan contract and merger for the CUDA/T4 V-14 core producer.

Separate from the non-value ``v14_batch_contract`` (whose linear order,
sizing arithmetic, and manifest logic it reuses by import), this contract:

1. plans capped, independent ``[start, stop)`` core batches for a 3.5-hour
   target inside a 4-hour session budget from a **core** ``--measure``
   timing (never the non-value engine's timing), handling the 4,096
   invocation cap and cap-limited calibration;
2. binds the ledger, both qualification identities, the core validation
   identity, compiler/platform identity, and every producer hash;
3. rejects RX/ROCm/HIP/emulation platforms;
4. validates artifact directories (manifest + records.json identities and
   hashes, exact non-overlapping coverage, compatible identities) and emits
   only a merged index manifest.  It never computes an aggregate and never
   copies or rewrites a scientific record.

Importing this module has no side effects and writes nothing.
"""

from __future__ import annotations

from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.g6.cuda_qualification import cuda_energy_crosscheck as cuda  # noqa: E402
from research.g6.cuda_qualification import cuda_v14_core_batch as core  # noqa: E402
from research.g6.cuda_qualification import cuda_v14_engine as engine  # noqa: E402
from research.g6.cuda_qualification import v14_batch_contract as base  # noqa: E402


SCHEMA_PLAN = "decisions_os/g6_v14_cuda_t4_core_batch_plan/v1"
SCHEMA_MERGED_INDEX = "decisions_os/g6_v14_cuda_t4_core_merged_index/v1"
PURPOSE = ("V-14 CUDA/T4 core batch plan: independent capped coordinate ranges and bound identities; "
           "no energy, minimum, tie set, label, rate, transition, comparison, or conclusion")
PLATFORM_KEYS = base.PLATFORM_KEYS
PLAN_BOUND_KEYS = ("pass_id", "scale", "track", "plan_content_sha256", "linear_order", "grid", "ledger_identity",
                   "source_sha256", "core_validation_identity_sha256", "prerequisite_qualification_identities",
                   "slack_domain_logical_sha256", "compile_contract", "platform")
PRODUCER_RELATIVES = (
    "research/g6/cuda_qualification/cuda_energy_crosscheck.py",
    "research/g6/cuda_qualification/cuda_slack_energy_crosscheck.py",
    "research/g6/cuda_qualification/cuda_v14_engine.py",
    "research/g6/cuda_qualification/cuda_v14_prepared_domain_engine.cu",
    "research/g6/cuda_qualification/cuda_v14_core_batch_engine.cu",
    "research/g6/cuda_qualification/cuda_v14_core_batch.py",
    "research/g6/cuda_qualification/v14_batch_contract.py",
    "research/g6/cuda_qualification/v14_core_batch_contract.py",
    "research/g6/run_cuda_v14_core_batches.py",
    "research/g6/plan_v14_cuda_core_batches.py",
    f"{base.LEDGER_DIR_REL}/v14_expansion_0_5x.json",
    f"{base.LEDGER_DIR_REL}/v14_expansion_2x.json",
)
_HEX64 = re.compile(r"[0-9a-f]{64}")
_HEX32 = re.compile(r"[0-9a-f]{32}")


class CoreContractError(RuntimeError):
    """Raised when a core plan, measurement, or artifact set fails closed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CoreContractError(message)


def _base(function, *arguments):
    try:
        return function(*arguments)
    except base.BatchContractError as exc:
        raise CoreContractError(str(exc)) from exc


canonical_bytes = base.canonical_bytes
content_sha256 = base.content_sha256


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def validate_core_validation_record(record: Mapping[str, Any]) -> dict[str, Any]:
    """Accept only a passed core --validate record bound to the current sources and both qualifications."""
    _require(isinstance(record, dict), "core validation record is not a JSON object")
    _require(record.get("schema") == core.SCHEMA_VALIDATE and record.get("mode") == "validate"
             and record.get("track") == "cuda-t4", "record is not a CUDA/T4 core validation run")
    _require(record.get("verdict") == "pass", "core validation did not pass")
    validation = record.get("validation")
    _require(isinstance(validation, dict) and isinstance(validation.get("totals"), dict)
             and all(type(value) is int and value == 0 for value in validation["totals"].values())
             and set(validation["totals"]) == {"h_min_bits_mismatches", "h_min_index_mismatches", "tie_entry_mismatches", "summary_mismatches"}
             and validation.get("device_vs_host_cxx_mismatches") == 0
             and isinstance(validation.get("per_coordinate"), list) and validation["per_coordinate"],
             "core validation counters are not all zero")
    identity = record.get("core_validation_identity")
    _require(isinstance(identity, dict) and record.get("core_validation_identity_sha256") == core.identity_sha256(identity),
             "core validation identity hash mismatch")
    _require(identity.get("backend") == cuda.BACKEND and isinstance(identity.get("gpu_name"), str)
             and cuda.TARGET_GPU_NAME_PATTERN.fullmatch(identity["gpu_name"]) is not None
             and identity.get("compute_capability") == "%d.%d" % cuda.TARGET_COMPUTE_CAPABILITY
             and identity.get("architecture") == cuda.TARGET_ARCHITECTURE and identity.get("role") == "core-batch-producer"
             and identity.get("probe") == core.PROBE, "core identity is not a T4/sm_75 CUDA core-producer identity")
    _require(not base._forbidden_platform({key: identity.get(key) for key in PLATFORM_KEYS}), "core identity names a non-CUDA/T4 platform")
    for key in ("cuda_driver_version", "cuda_runtime_version"):
        _require(isinstance(identity.get(key), int) and identity[key] > 0, f"core identity lacks {key}")
    _require(isinstance(identity.get("nvcc_build"), str) and identity["nvcc_build"] != "0.0.0", "core identity lacks the nvcc version")
    _require(identity.get("compile_flags") == list(core.COMPILE_FLAGS), "core compile flags differ from the current nvcc contract")
    try:
        current = core.verify_pinned_inputs()
    except core.CoreError as exc:
        raise CoreContractError(str(exc)) from exc
    _require(identity.get("pinned_inputs") == current, "core validation was produced against different pinned sources")
    _require(identity.get("core_source_sha256") == identity.get("cuda_source_sha256") == current[core.CUDA_SOURCE_REL]
             and identity.get("engine_source_sha256") == current[engine.CUDA_SOURCE_REL]
             and identity.get("engine_library_sha256") == current[core.ENGINE_LIBRARY_REL], "core identity binds different producer sources")
    domain = identity.get("domain")
    _require(isinstance(domain, dict) and isinstance(domain.get("slack"), dict)
             and domain["slack"].get("logical_sha256") == engine.EXPECTED_SLACK_DOMAIN["logical_sha256"]
             and domain["slack"].get("entries") == engine.EXPECTED_SLACK_DOMAIN["entries"], "core identity binds a different slack domain")
    prerequisites = identity.get("prerequisites")
    _require(isinstance(prerequisites, dict) and set(prerequisites) == {"unbalanced_identity_sha256", "slack_identity_sha256"}
             and all(isinstance(v, str) and _HEX64.fullmatch(v) is not None for v in prerequisites.values())
             and prerequisites["unbalanced_identity_sha256"] != prerequisites["slack_identity_sha256"],
             "core identity lacks both prerequisite qualification identities")
    _require(identity.get("validation_coordinates_sha256") == engine.validation_coordinates_sha256(),
             "core validation covered a different coordinate declaration")
    classifier = identity.get("classifier")
    _require(isinstance(classifier, dict) and classifier.get("ground_truth_sha256") == current[core.GROUND_TRUTH_REL]
             and classifier.get("adnye_001_sha256") == current[core.ADNYE_001_REL]
             and classifier.get("d015_d016_decision_record_sha256") == current[core.DECISIONS_REL],
             "core identity binds different classifier authorities")
    _require(identity.get("d015_pairs") == [list(core.PRIMARY_PAIR)] + [list(p) for p in core.DIAGNOSTIC_PAIRS]
             and identity.get("record_schema") == core.SCHEMA_RECORDS, "core identity D015 configuration drift")
    device = record.get("device")
    _require(isinstance(device, dict) and isinstance(device.get("device_uuid_hex"), str)
             and _HEX32.fullmatch(device["device_uuid_hex"]) is not None, "core validation record lacks a device UUID")
    return identity


def validate_measurement(measurement: Mapping[str, Any], identity_sha256: str) -> dict[str, Any]:
    """Core --measure timing only: same sample rules, cap-limited acceptance, and conservative derivations as the base contract."""
    _require(isinstance(measurement, dict) and measurement.get("schema") == core.SCHEMA_MEASUREMENT,
             "measurement is not a core --measure throughput measurement (non-value engine timing is not accepted)")
    relabelled = dict(measurement)
    relabelled["schema"] = base.SCHEMA_THROUGHPUT
    relabelled.pop("content_sha256", None)
    _require(measurement.get("content_sha256") == content_sha256(measurement), "core measurement content hash mismatch")
    relabelled["content_sha256"] = content_sha256(relabelled)
    measured = _base(base.validate_throughput, relabelled, identity_sha256)
    measured["measurement_content_sha256"] = measurement["content_sha256"]
    measured["measurement_schema"] = core.SCHEMA_MEASUREMENT
    return measured


def build_plan(scale: str, validation_record: Mapping[str, Any], measurement: Mapping[str, Any],
               derate: Fraction = base.DEFAULT_DERATE) -> dict[str, Any]:
    """Validate every input and emit the canonical core plan; nothing is written."""
    _require(scale in base.SCALES, "scale must be '0.5x' or '2x'")
    ledgers = _base(base.load_v14_ledgers)
    identity = validate_core_validation_record(validation_record)
    identity_sha256 = core.identity_sha256(identity)
    measured = validate_measurement(measurement, identity_sha256)
    rate, setup = measured.pop("_rate"), measured.pop("_setup")
    size, uncapped = _base(base.coordinates_per_batch, rate, setup, derate)
    choice = base.SCALES[scale]
    axis_count = choice["axis_count"]
    total = axis_count ** 3
    batches = _base(base.batch_ranges, total, size, choice["tag"] + "_core")
    plan: dict[str, Any] = {
        "schema": SCHEMA_PLAN, "purpose": PURPOSE, "track": "cuda-t4", "scale": scale, "pass_id": choice["pass_id"],
        "linear_order": base.LINEAR_ORDER,
        "grid": {"axis_count": axis_count, "total_coordinates": total, "axis_index_range": [0, axis_count]},
        "ledger_identity": ledgers[scale]["identity"],
        "all_v14_ledgers_validated": {s: ledgers[s]["identity"]["content_sha256"] for s in base.SCALES},
        "source_sha256": cuda.current_hashes(PRODUCER_RELATIVES),
        "core_validation_identity_sha256": identity_sha256, "core_validation_identity": identity,
        "validation_record": {"schema": validation_record["schema"], "verdict": validation_record["verdict"],
                              "validated_coordinates": len(validation_record["validation"]["per_coordinate"])},
        "prerequisite_qualification_identities": dict(identity["prerequisites"]),
        "slack_domain_logical_sha256": identity["domain"]["slack"]["logical_sha256"],
        "compile_contract": {"nvcc_flags": list(core.COMPILE_FLAGS), "cuda_source_sha256": identity["core_source_sha256"],
                             "engine_source_sha256": identity["engine_source_sha256"]},
        "platform": {key: identity[key] for key in PLATFORM_KEYS},
        "classifier": identity["classifier"], "d015_pairs": identity["d015_pairs"], "record_schema": core.SCHEMA_RECORDS,
        "throughput": measured,
        "sizing": {"measurement_acceptance_basis": measured["acceptance_basis"], "target_batch_seconds": base.TARGET_BATCH_SECONDS,
                   "session_budget_seconds": base.SESSION_BUDGET_SECONDS, "derate": base._fraction_text(derate),
                   "conservative_setup_seconds": base._fraction_text(setup),
                   "max_coordinates_per_invocation": core.MAX_COORDINATES_PER_INVOCATION,
                   "rule": "uncapped = floor(conservative_rate * (target_batch_seconds - conservative_setup_seconds) * derate); "
                           "coordinates_per_batch = min(uncapped, max_coordinates_per_invocation)",
                   "coordinates_per_batch_uncapped": uncapped, "coordinates_per_batch": size, "cap_applied": uncapped > size,
                   "estimated_full_batch_seconds": base._fraction_text(setup + Fraction(size) / rate), "batch_count": len(batches)},
        "batches": batches,
        "run_rule": ("one batch per --run-batch invocation, any order, any qualified session; an explicit output directory "
                     "outside the repository; a failed or interrupted batch is rerun as the same range after removing its "
                     "partial pending directory; merge only after every batch is complete"),
        "release_rule": "a release record bound to this plan's content hash is required before any --run-batch",
        "scientific_outputs": "intentionally absent",
    }
    plan["content_sha256"] = content_sha256(plan)
    validate_plan(plan)
    return plan


def validate_plan(plan: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    _require(isinstance(plan, dict) and plan.get("schema") == SCHEMA_PLAN, "not a V-14 CUDA/T4 core batch plan")
    _require(plan.get("content_sha256") == content_sha256(plan), "core plan content hash mismatch")
    _require(plan.get("track") == "cuda-t4" and plan.get("linear_order") == base.LINEAR_ORDER
             and plan.get("scientific_outputs") == "intentionally absent" and plan.get("record_schema") == core.SCHEMA_RECORDS,
             "core plan contract drift")
    scale = plan.get("scale")
    _require(scale in base.SCALES and plan.get("pass_id") == base.SCALES[scale]["pass_id"], "plan scale/pass mismatch")
    axis_count = base.SCALES[scale]["axis_count"]
    _require(plan.get("grid") == {"axis_count": axis_count, "total_coordinates": axis_count ** 3, "axis_index_range": [0, axis_count]},
             "plan grid drift")
    identity = plan.get("core_validation_identity")
    _require(isinstance(identity, dict) and plan.get("core_validation_identity_sha256") == core.identity_sha256(identity)
             and identity.get("role") == "core-batch-producer", "plan core identity hash mismatch")
    _require(plan.get("platform") == {key: identity.get(key) for key in PLATFORM_KEYS} and plan["platform"]["backend"] == cuda.BACKEND
             and not base._forbidden_platform(plan["platform"]), "plan platform is not the validated CUDA/T4 platform")
    _require(plan.get("prerequisite_qualification_identities") == identity.get("prerequisites")
             and set(identity.get("prerequisites", {})) == {"unbalanced_identity_sha256", "slack_identity_sha256"},
             "plan does not bind both prerequisite qualification identities")
    _require(plan.get("compile_contract", {}).get("nvcc_flags") == list(core.COMPILE_FLAGS)
             and plan["compile_contract"].get("cuda_source_sha256") == identity.get("core_source_sha256"),
             "plan compile contract drift")
    _require(set(plan.get("source_sha256", {})) == set(PRODUCER_RELATIVES), "plan does not bind every producer source")
    batches = plan.get("batches")
    size = plan.get("sizing", {}).get("coordinates_per_batch")
    _require(isinstance(batches, list) and batches and isinstance(size, int) and 1 <= size <= core.MAX_COORDINATES_PER_INVOCATION
             and plan["sizing"].get("max_coordinates_per_invocation") == core.MAX_COORDINATES_PER_INVOCATION
             and plan["sizing"].get("batch_count") == len(batches), "plan sizing drift or invocation cap exceeded")
    by_id: dict[str, dict[str, Any]] = {}
    cursor = 0
    for index, batch in enumerate(batches):
        _require(isinstance(batch, dict) and set(batch) == {"batch_id", "index", "start", "stop", "count"}, f"malformed batch {index}")
        _require(batch["index"] == index and batch["start"] == cursor and batch["stop"] > batch["start"]
                 and batch["count"] == batch["stop"] - batch["start"] <= size, f"batch {index} range drift")
        _require(isinstance(batch["batch_id"], str) and batch["batch_id"] not in by_id, f"duplicate batch id at {index}")
        by_id[batch["batch_id"]] = batch
        cursor = batch["stop"]
    _require(cursor == axis_count ** 3, "plan batches do not cover the grid exactly once")
    return by_id


# --------------------------------------------------------------------------
# Artifact validation and merged index
# --------------------------------------------------------------------------

def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CoreContractError(f"{label} is unreadable JSON: {path}") from exc
    _require(isinstance(payload, dict), f"{label} must be a JSON object")
    return payload


def validate_artifact(directory: Path, plan: Mapping[str, Any], by_id: Mapping[str, Mapping[str, Any]],
                      ledger: Mapping[str, Any]) -> dict[str, Any]:
    """Validate one batch directory: exact member set, manifest/records identities, and every record semantically.

    Never rewrites, copies, or aggregates a scientific record.
    """
    label = directory.name
    manifest_path, records_path = directory / "manifest.json", directory / "records.json"
    _require(directory.is_dir() and not directory.is_symlink(), f"{label}: artifact directory missing or a symlink")
    try:
        members = sorted(entry.name for entry in os.scandir(directory))
    except OSError as exc:
        raise CoreContractError(f"{label}: artifact directory unreadable") from exc
    _require(members == ["manifest.json", "records.json"], f"{label}: artifact must contain exactly manifest.json and records.json")
    _require(all(not (directory / name).is_symlink() and (directory / name).is_file() for name in members),
             f"{label}: artifact members must be regular files, not symlinks")
    manifest = _read_json(manifest_path, f"{label}: manifest")
    _require(manifest.get("schema") == core.SCHEMA_MANIFEST, f"{label}: not a core batch manifest")
    _require(manifest.get("content_sha256") == content_sha256(manifest), f"{label}: manifest content hash mismatch")
    _require(not base._forbidden_platform(manifest.get("platform")), f"{label}: RX 9070 / ROCm / HIP / emulation platform is rejected")
    platform = manifest.get("platform")
    _require(isinstance(platform, dict) and platform.get("backend") == cuda.BACKEND and isinstance(platform.get("gpu_name"), str)
             and cuda.TARGET_GPU_NAME_PATTERN.fullmatch(platform["gpu_name"]) is not None
             and platform.get("compute_capability") == "%d.%d" % cuda.TARGET_COMPUTE_CAPABILITY
             and platform.get("architecture") == cuda.TARGET_ARCHITECTURE, f"{label}: platform is not a Tesla T4 / sm_75 under CUDA")
    for key in PLAN_BOUND_KEYS:
        expected = plan["content_sha256"] if key == "plan_content_sha256" else plan.get(key)
        _require(manifest.get(key) == expected, f"{label}: {key} differs from the plan")
    batch_id = manifest.get("batch_id")
    _require(isinstance(batch_id, str) and batch_id in by_id and batch_id == label, f"{label}: batch id is not in the plan or differs from the directory name")
    batch = by_id[batch_id]
    _require(manifest.get("range") == {"start": batch["start"], "stop": batch["stop"], "count": batch["count"]},
             f"{label}: range differs from the plan's range")
    session = manifest.get("session")
    _require(isinstance(session, dict) and set(session) == {"session_id", "device_uuid_hex", "start_platform_sha256", "end_platform_sha256"}
             and isinstance(session["session_id"], str) and _HEX64.fullmatch(session["session_id"]) is not None
             and isinstance(session["device_uuid_hex"], str) and _HEX32.fullmatch(session["device_uuid_hex"]) is not None
             and all(isinstance(session[k], str) and _HEX64.fullmatch(session[k]) is not None for k in ("start_platform_sha256", "end_platform_sha256"))
             and session["start_platform_sha256"] == session["end_platform_sha256"], f"{label}: malformed or drifted session")
    release = manifest.get("release")
    _require(isinstance(release, dict) and set(release) == {"review_id", "released_by", "date", "content_sha256"}, f"{label}: malformed release binding")
    records_meta = manifest.get("records")
    _require(isinstance(records_meta, dict) and set(records_meta) == {"file", "file_sha256", "content_sha256", "record_count"}
             and records_meta["file"] == "records.json" and records_meta["record_count"] == batch["count"], f"{label}: records metadata malformed")
    try:
        records_bytes = records_path.read_bytes()
    except OSError as exc:
        raise CoreContractError(f"{label}: records.json unreadable") from exc
    _require(_sha256_bytes(records_bytes) == records_meta["file_sha256"], f"{label}: records.json file hash mismatch")
    try:
        records = json.loads(records_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CoreContractError(f"{label}: records.json is not JSON") from exc
    _require(isinstance(records, dict) and records.get("schema") == core.SCHEMA_RECORDS
             and records.get("content_sha256") == records_meta["content_sha256"] == content_sha256(records)
             and records.get("batch_id") == batch_id and records.get("plan_content_sha256") == plan["content_sha256"]
             and records.get("range") == manifest["range"] and records.get("record_count") == batch["count"]
             and records.get("core_validation_identity_sha256") == plan["core_validation_identity_sha256"],
             f"{label}: records.json identity mismatch")
    _require(set(records) == {"schema", "batch_id", "plan_content_sha256", "pass_id", "scale", "range", "linear_order", "record_count",
                              "records", "release_review_id", "core_validation_identity_sha256", "content_sha256"}
             and records.get("pass_id") == plan["pass_id"] and records.get("scale") == plan["scale"]
             and records.get("linear_order") == plan["linear_order"] and records.get("release_review_id") == release["review_id"],
             f"{label}: records.json top-level key set or bindings")
    items = records.get("records")
    _require(isinstance(items, list) and len(items) == batch["count"], f"{label}: record count differs from the batch range")
    slack_count = plan["core_validation_identity"]["domain"]["slack"]["entries"]
    lambda_ref_hex = plan["classifier"]["lambda_ref_hex"]
    for offset, item in enumerate(items):
        linear = batch["start"] + offset
        try:
            core.validate_record(item, linear, plan["scale"], ledger, lambda_ref_hex, slack_count)
        except core.CoreError as exc:
            raise CoreContractError(f"{label}: {exc}") from exc
    return {"batch_id": batch_id, "path": str(directory), "range": manifest["range"], "manifest_sha256": _sha256_bytes(manifest_path.read_bytes()),
            "manifest_content_sha256": manifest["content_sha256"], "records_file_sha256": records_meta["file_sha256"],
            "records_content_sha256": records_meta["content_sha256"], "record_count": records_meta["record_count"],
            "session_id": session["session_id"], "device_uuid_hex": session["device_uuid_hex"],
            "identity_digest": _sha256_bytes(canonical_bytes({key: manifest[key] for key in PLAN_BOUND_KEYS}))}


def validate_final_set(plan: Mapping[str, Any], artifact_root: Path) -> dict[str, Any]:
    """Accept only a complete, order-independent, identity-homogeneous artifact set; emit the merged index only."""
    by_id = validate_plan(plan)
    root = Path(artifact_root)
    _require(root.is_dir(), "artifact root is not a directory")
    ledgers = _base(base.load_v14_ledgers)
    _require(ledgers[plan["scale"]]["identity"] == plan["ledger_identity"], "plan ledger identity differs from the reviewed ledger")
    ledger = ledgers[plan["scale"]]["payload"]
    entries = []
    identities: set[str] = set()
    for batch_id in sorted(by_id):
        entries.append(validate_artifact(root / batch_id, plan, by_id, ledger))
        identities.add(entries[-1]["identity_digest"])
    _require(len(identities) == 1, "artifacts bind mixed plan/ledger/source/CUDA-T4/compiler identities")
    ordered = sorted(entries, key=lambda item: item["range"]["start"])
    cursor = 0
    for entry in ordered:
        _require(entry["range"]["start"] == cursor, f"gap or overlap before {entry['batch_id']}")
        cursor = entry["range"]["stop"]
    _require(cursor == plan["grid"]["total_coordinates"], "artifact set does not end at the grid's last coordinate")
    index = {"schema": SCHEMA_MERGED_INDEX, "verdict": "accepted", "plan_content_sha256": plan["content_sha256"],
             "pass_id": plan["pass_id"], "scale": plan["scale"], "linear_order": plan["linear_order"], "grid": plan["grid"],
             "core_validation_identity_sha256": plan["core_validation_identity_sha256"],
             "prerequisite_qualification_identities": plan["prerequisite_qualification_identities"],
             "platform": plan["platform"], "batch_count": len(ordered), "total_coordinates": cursor,
             "session_count": len({entry["session_id"] for entry in ordered}),
             "device_count": len({entry["device_uuid_hex"] for entry in ordered}),
             "batches": [{key: value for key, value in entry.items() if key not in ("identity_digest",)} for entry in ordered],
             "aggregation": "none; this index lists artifacts and their hashes only",
             "scientific_outputs": "intentionally absent"}
    index["content_sha256"] = content_sha256(index)
    return index


def write_merged_index(index: Mapping[str, Any], path: Path) -> Path:
    """Atomic, collision-refusing write of the merged index outside the repository tree."""
    target = Path(path)
    _require(target.is_absolute() and target.parent.is_dir(), "merged index path must be absolute inside an existing directory")
    try:
        core.require_safe_output_dir(target.parent)
    except core.CoreError as exc:
        raise CoreContractError(str(exc)) from exc
    _require(not target.exists() and not target.is_symlink(), f"refusing to overwrite an existing merged index: {target}")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.pending-", dir=target.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(canonical_bytes(index))
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary_name, 0o644)
        os.link(temporary_name, target)
        fd = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError as exc:
        raise CoreContractError(f"merged index write failed: {exc}") from exc
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
    return target

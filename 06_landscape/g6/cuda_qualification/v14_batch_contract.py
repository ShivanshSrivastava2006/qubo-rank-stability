"""Independent, order-agnostic V-14 CUDA/T4 batch planning and merge validation.

This module only plans and validates future V-14 batches.  It computes no
energy, reads no Gate-5 corpus, emits no batch artifact, and defines no
value-producing run.  Its two jobs:

1. **Plan.**  Given one transcript-validated V-14 ledger (0.5x or 2x), one
   passed CUDA/T4 V-14 engine validation record (which binds BOTH the
   unbalanced and slack qualification identities, the canonical slack-domain
   digest, and the engine source), and one validated throughput measurement, derive a conservative integer ``coordinates_per_batch`` for a
   3.5-hour target under a 4-hour session budget and emit a canonical plan
   that covers the grid exactly once in the deterministic linear order

       linear = card * N^2 + sector * N + budget        (N = axis_count)

   as half-open ranges ``[start, stop)``, each no larger than the engine's
   per-invocation cap.  A batch owns no shared state and
   may run in any order, in any Colab session, on any physical T4 that
   presents the identical qualification identity.

2. **Validate a final set.**  Accept a collection of future batch manifests
   (metadata only; no value file is ever opened) only when they are an exact
   non-overlapping cover of the plan and every manifest binds the identical
   plan, ledger, source, CUDA/T4, compiler, and qualification identity.  Any
   RX 9070 / ROCm / HIP / emulation platform, and any batch whose session or
   platform fingerprint drifted within the batch, is rejected.

Importing this module has no side effects and writes nothing.
"""

from __future__ import annotations

from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import re
import sys
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.g6.cuda_qualification import cuda_energy_crosscheck as cuda  # noqa: E402
from research.g6.cuda_qualification import cuda_v14_engine as engine  # noqa: E402
from src.g6.ledgers import validate_preexecution_ledger  # noqa: E402


SCHEMA_PLAN = "decisions_os/g6_v14_cuda_t4_batch_plan/v1"
SCHEMA_MANIFEST = "decisions_os/g6_v14_cuda_t4_batch_manifest/v1"
SCHEMA_THROUGHPUT = "decisions_os/g6_v14_cuda_t4_throughput_measurement/v1"
SCHEMA_FINAL_SET = "decisions_os/g6_v14_cuda_t4_final_set_validation/v1"
PURPOSE = ("V-14 CUDA/T4 batch plan: coordinate ranges and bound identities only; "
           "no energy, minimum, tie set, label, rate, transition, or conclusion")
LINEAR_ORDER = "linear = card * N^2 + sector * N + budget; N = axis_count; batch = [start, stop)"
TARGET_BATCH_SECONDS = 12600   # 3.5 h
SESSION_BUDGET_SECONDS = 14400  # 4 h Colab session budget the target stays below
DEFAULT_DERATE = Fraction(9, 10)
MIN_MEASURED_COORDINATES = 4
MIN_MEASURED_SECONDS = 60

LEDGER_DIR_REL = "research/g6/preexecution_ledgers"
MANIFEST_REL = f"{LEDGER_DIR_REL}/manifest.json"
SCALES = {
    "0.5x": {"file": "v14_expansion_0_5x.json", "pass_id": "v14_expansion_0.5x", "axis_count": 31, "tag": "v14_0_5x"},
    "2x": {"file": "v14_expansion_2x.json", "pass_id": "v14_expansion_2x", "axis_count": 111, "tag": "v14_2x"},
}
# Sources whose live hashes every plan binds beyond the qualification pins.
PLAN_SOURCE_RELATIVES = (
    "research/g6/cuda_qualification/cuda_energy_crosscheck.py",
    "research/g6/cuda_qualification/cuda_slack_energy_crosscheck.py",
    "research/g6/cuda_qualification/cuda_v14_engine.py",
    "research/g6/cuda_qualification/cuda_v14_prepared_domain_engine.cu",
    "research/g6/cuda_qualification/v14_batch_contract.py",
    f"{LEDGER_DIR_REL}/v14_expansion_0_5x.json",
    f"{LEDGER_DIR_REL}/v14_expansion_2x.json",
)
PLATFORM_KEYS = ("backend", "gpu_name", "compute_capability", "architecture",
                 "cuda_driver_version", "cuda_runtime_version", "nvcc_release", "nvcc_build")
# Fields every manifest must carry byte-for-byte from the plan.
PLAN_BOUND_KEYS = ("pass_id", "scale", "track", "plan_content_sha256", "linear_order", "grid",
                   "ledger_identity", "source_sha256", "cuda_qualification_identity_sha256",
                   "prerequisite_qualification_identities", "slack_domain_logical_sha256",
                   "compile_contract", "platform")
FORBIDDEN_MANIFEST_KEYS = ("energy", "energies", "h_e_min", "h_e_min_hex", "minimum", "t_e", "x_e",
                           "label", "labels", "tie", "ties", "rate", "transition")
_HEX64 = re.compile(r"[0-9a-f]{64}")
_HEX32 = re.compile(r"[0-9a-f]{32}")


class BatchContractError(RuntimeError):
    """Raised when a plan, measurement, or manifest set fails closed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise BatchContractError(message)


def canonical_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def content_sha256(payload: Mapping[str, Any]) -> str:
    body = {key: value for key, value in payload.items() if key != "content_sha256"}
    return _sha256_bytes(canonical_bytes(body))


def _validate_content_hash(payload: Mapping[str, Any], label: str) -> None:
    _require(isinstance(payload, dict), f"{label} is not a JSON object")
    digest = payload.get("content_sha256")
    _require(isinstance(digest, str) and digest == content_sha256(payload), f"{label} canonical content hash mismatch")


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BatchContractError(f"{label} is unreadable JSON: {path}") from exc
    _require(isinstance(payload, dict), f"{label} must be a JSON object")
    return payload


def _fraction(value: object, label: str) -> Fraction:
    """Exact rational from an int, a decimal string, or a 'p/q' string; never a float."""
    _require(not isinstance(value, bool), f"{label} must be numeric")
    if isinstance(value, int):
        return Fraction(value)
    if isinstance(value, str):
        try:
            return Fraction(value)
        except (ValueError, ZeroDivisionError) as exc:
            raise BatchContractError(f"{label} is not an exact rational: {value!r}") from exc
    raise BatchContractError(f"{label} must be an integer or an exact decimal/rational string")


def _fraction_text(value: Fraction) -> str:
    return f"{value.numerator}/{value.denominator}"


def _forbidden_platform(value: object) -> bool:
    if isinstance(value, dict):
        return any(_forbidden_platform(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_forbidden_platform(item) for item in value)
    if isinstance(value, str):
        lowered = value.lower()
        return any(token in lowered for token in cuda.FORBIDDEN_PLATFORM_TOKENS)
    return False


# --------------------------------------------------------------------------
# Inputs
# --------------------------------------------------------------------------

def load_v14_ledgers() -> dict[str, dict[str, Any]]:
    """Load both reviewed V-14 ledgers through the manifest and replay validation."""
    manifest = _read_json(ROOT / MANIFEST_REL, "preexecution-ledger manifest")
    _validate_content_hash(manifest, "preexecution-ledger manifest")
    _require(manifest.get("schema") == "decisions_os/g6_preexecution_ledger_manifest/v1",
             "unexpected preexecution-ledger manifest schema")
    listed = manifest.get("ledgers")
    _require(isinstance(listed, dict), "malformed preexecution-ledger manifest")
    manifest_file_sha256 = _sha256_bytes((ROOT / MANIFEST_REL).read_bytes())
    output: dict[str, dict[str, Any]] = {}
    for scale, choice in SCALES.items():
        name = choice["file"]
        entry = listed.get(name)
        _require(isinstance(entry, dict) and set(entry) == {"content_sha256", "file_sha256"},
                 f"manifest entry missing or malformed: {name}")
        path = ROOT / LEDGER_DIR_REL / name
        try:
            file_sha256 = _sha256_bytes(path.read_bytes())
        except OSError as exc:
            raise BatchContractError(f"ledger is unreadable: {name}") from exc
        _require(file_sha256 == entry["file_sha256"], f"ledger file identity mismatch: {name}")
        payload = _read_json(path, name)
        _require(payload.get("content_sha256") == entry["content_sha256"], f"ledger content identity mismatch: {name}")
        try:
            validate_preexecution_ledger(payload)
        except Exception as exc:  # LedgerError or any replay failure is fail-closed
            raise BatchContractError(f"ledger fails transcript replay: {name}") from exc
        _require(payload.get("pass_id") == choice["pass_id"]
                 and payload.get("grid_rule", {}).get("N_axis") == choice["axis_count"]
                 and len(payload.get("coordinates", ())) == choice["axis_count"],
                 f"V-14 {scale} ledger shape drift")
        output[scale] = {
            "payload": payload,
            "identity": {
                "file": f"{LEDGER_DIR_REL}/{name}",
                "file_sha256": file_sha256,
                "content_sha256": payload["content_sha256"],
                "manifest_file": MANIFEST_REL,
                "manifest_file_sha256": manifest_file_sha256,
                "manifest_content_sha256": manifest["content_sha256"],
                "pass_id": choice["pass_id"],
            },
        }
    return output


def validate_qualification_record(record: Mapping[str, Any]) -> dict[str, Any]:
    """Accept only a passed CUDA/T4 V-14 engine validation record bound to the current sources.

    The engine record binds BOTH prerequisite qualification identities
    (unbalanced and slack cross-checks), the canonical slack-domain digest,
    the engine source, and the platform/toolchain observed at validation.
    """
    _require(isinstance(record, dict), "qualification record is not a JSON object")
    _require(record.get("schema") == engine.SCHEMA_VALIDATE and record.get("mode") == "validate"
             and record.get("track") == "cuda-t4", "qualification record is not a CUDA/T4 V-14 engine validation run")
    _require(record.get("verdict") == "pass", "engine validation did not pass")
    validation = record.get("validation")
    _require(isinstance(validation, dict) and isinstance(validation.get("totals"), dict)
             and validation["totals"].get("word_mismatches") == 0 and validation["totals"].get("reduction_mismatches") == 0
             and validation.get("device_vs_host_cxx_mismatches") == 0
             and isinstance(validation.get("per_coordinate"), list) and validation["per_coordinate"],
             "engine validation counters are not all zero")
    identity = record.get("qualification_identity")
    _require(isinstance(identity, dict), "qualification record lacks its identity")
    _require(record.get("qualification_identity_sha256") == engine.identity_sha256(identity),
             "qualification identity hash mismatch")
    _require(identity.get("backend") == cuda.BACKEND
             and isinstance(identity.get("gpu_name"), str)
             and cuda.TARGET_GPU_NAME_PATTERN.fullmatch(identity["gpu_name"]) is not None
             and identity.get("compute_capability") == "%d.%d" % cuda.TARGET_COMPUTE_CAPABILITY
             and identity.get("architecture") == cuda.TARGET_ARCHITECTURE,
             "qualification identity is not an NVIDIA Tesla T4 at compute capability 7.5")
    _require(not _forbidden_platform({key: identity.get(key) for key in PLATFORM_KEYS}),
             "qualification identity names a non-CUDA/T4 platform")
    for key in ("cuda_driver_version", "cuda_runtime_version"):
        _require(isinstance(identity.get(key), int) and identity[key] > 0, f"qualification identity lacks {key}")
    _require(isinstance(identity.get("nvcc_release"), str) and isinstance(identity.get("nvcc_build"), str)
             and identity["nvcc_build"] != "0.0.0", "qualification identity lacks the nvcc version")
    _require(identity.get("compile_flags") == list(engine.COMPILE_FLAGS),
             "qualification compile flags differ from the current nvcc contract")
    current_pins = engine.verify_pinned_inputs()
    _require(identity.get("pinned_inputs") == current_pins,
             "qualification record was produced against different pinned sources, domain code, or ledgers")
    _require(identity.get("cuda_source_sha256") == identity.get("engine_source_sha256") == current_pins[engine.CUDA_SOURCE_REL],
             "qualification record binds a different engine source")
    domain = identity.get("domain")
    _require(isinstance(domain, dict) and isinstance(domain.get("slack"), dict)
             and domain["slack"].get("logical_sha256") == engine.EXPECTED_SLACK_DOMAIN["logical_sha256"]
             and domain["slack"].get("entries") == engine.EXPECTED_SLACK_DOMAIN["entries"],
             "qualification record binds a different canonical slack domain")
    prerequisites = identity.get("prerequisites")
    _require(isinstance(prerequisites, dict) and set(prerequisites) == {"unbalanced_identity_sha256", "slack_identity_sha256"}
             and all(isinstance(value, str) and _HEX64.fullmatch(value) is not None for value in prerequisites.values())
             and prerequisites["unbalanced_identity_sha256"] != prerequisites["slack_identity_sha256"],
             "qualification record lacks both prerequisite qualification identities")
    _require(identity.get("validation_coordinates_sha256") == engine.validation_coordinates_sha256(),
             "qualification record validated a different coordinate declaration")
    device = record.get("device")
    _require(isinstance(device, dict) and isinstance(device.get("device_uuid_hex"), str)
             and _HEX32.fullmatch(device["device_uuid_hex"]) is not None, "qualification record lacks a device UUID")
    return identity


SAMPLE_FIELDS = frozenset({"coordinates", "wall_seconds", "setup_seconds", "coordinate_seconds"})


def validate_throughput(measurement: Mapping[str, Any], identity_sha256: str) -> dict[str, Any]:
    """Validate a measured throughput input; return the conservative rate and setup.

    Every sample must carry exactly ``coordinates``, ``wall_seconds``,
    ``setup_seconds``, and ``coordinate_seconds`` (exact decimal strings) with
    ``wall == setup + coordinate`` reconciling exactly.  The conservative
    coordinate rate is the slowest ``coordinates / coordinate_seconds``; the
    conservative setup is the largest ``setup_seconds``.
    """
    _require(isinstance(measurement, dict), "throughput measurement is not a JSON object")
    _require(measurement.get("schema") == SCHEMA_THROUGHPUT, "unexpected throughput measurement schema")
    _validate_content_hash(measurement, "throughput measurement")
    _require(measurement.get("qualification_identity_sha256") == identity_sha256,
             "throughput measurement is bound to a different CUDA/T4 qualification identity")
    _require(measurement.get("unit") == "coordinates", "throughput measurement unit must be coordinates")
    samples = measurement.get("samples")
    _require(isinstance(samples, list) and samples, "throughput measurement has no samples")
    rates: list[Fraction] = []
    setups: list[Fraction] = []
    total_coordinates = 0
    total_coordinate_seconds = Fraction(0)
    reported = []
    for index, sample in enumerate(samples):
        _require(isinstance(sample, dict) and set(sample) == SAMPLE_FIELDS, f"malformed throughput sample {index}")
        coordinates = sample["coordinates"]
        _require(isinstance(coordinates, int) and not isinstance(coordinates, bool) and coordinates > 0,
                 f"throughput sample {index} coordinates must be a positive integer")
        _require(coordinates <= engine.MAX_COORDINATES_PER_INVOCATION,
                 f"throughput sample {index} exceeds the engine's per-invocation cap")
        wall = _fraction(sample["wall_seconds"], f"throughput sample {index} wall_seconds")
        setup = _fraction(sample["setup_seconds"], f"throughput sample {index} setup_seconds")
        coordinate = _fraction(sample["coordinate_seconds"], f"throughput sample {index} coordinate_seconds")
        _require(coordinate > 0 and setup >= 0 and wall > 0, f"throughput sample {index} times must be positive")
        _require(wall == setup + coordinate, f"throughput sample {index} wall_seconds != setup_seconds + coordinate_seconds")
        rates.append(Fraction(coordinates) / coordinate)
        setups.append(setup)
        total_coordinates += coordinates
        total_coordinate_seconds += coordinate
        reported.append({"coordinates": coordinates, "wall_seconds": str(sample["wall_seconds"]),
                         "setup_seconds": str(sample["setup_seconds"]), "coordinate_seconds": str(sample["coordinate_seconds"])})
    # Ordinary acceptance needs >= 4 coordinates over >= 60 s of coordinate time.  A
    # genuine full-cap sample (coordinates == engine.MAX_COORDINATES_PER_INVOCATION)
    # is the largest measurement one invocation can make; when the T4 finishes it in
    # under 60 s, the duration threshold is unattainable without redundant repeats,
    # so such a sample is accepted and the basis is recorded.
    cap_samples = [sample for sample in reported if sample["coordinates"] == engine.MAX_COORDINATES_PER_INVOCATION]
    _require(total_coordinates >= MIN_MEASURED_COORDINATES,
             f"throughput measurement is too small: need >= {MIN_MEASURED_COORDINATES} coordinates")
    if total_coordinate_seconds >= MIN_MEASURED_SECONDS:
        acceptance = "duration_threshold"
    else:
        _require(cap_samples, f"throughput measurement is too short: need >= {MIN_MEASURED_SECONDS} s of coordinate "
                              f"time unless a sample processes exactly {engine.MAX_COORDINATES_PER_INVOCATION} coordinates")
        acceptance = "invocation_cap_limited"
    setup = max(setups)
    _require(setup < TARGET_BATCH_SECONDS, "measured setup consumes the whole batch target window")
    return {
        "measurement_content_sha256": measurement["content_sha256"],
        "samples": reported,
        "total_coordinates": total_coordinates,
        "total_coordinate_seconds": _fraction_text(total_coordinate_seconds),
        "rule": "conservative rate = slowest sample coordinates / coordinate_seconds; "
                "conservative setup = largest sample setup_seconds",
        "acceptance_basis": acceptance,
        "acceptance_rule": (f"duration_threshold: >= {MIN_MEASURED_COORDINATES} coordinates over >= {MIN_MEASURED_SECONDS} s; "
                            f"invocation_cap_limited: shorter is accepted only when a sample has coordinates == "
                            f"{engine.MAX_COORDINATES_PER_INVOCATION} (the engine's per-invocation cap)"),
        "full_cap_sample_count": len(cap_samples),
        "conservative_rate_coordinates_per_second": _fraction_text(min(rates)),
        "conservative_setup_seconds": _fraction_text(setup),
        "_rate": min(rates),
        "_setup": setup,
    }


# --------------------------------------------------------------------------
# Plan
# --------------------------------------------------------------------------

def linear_index(card: int, sector: int, budget: int, axis_count: int) -> int:
    for label, value in (("card", card), ("sector", sector), ("budget", budget)):
        _require(isinstance(value, int) and 0 <= value < axis_count, f"{label} index outside the axis")
    return card * axis_count * axis_count + sector * axis_count + budget


def coordinate_at(linear: int, axis_count: int) -> tuple[int, int, int]:
    _require(isinstance(linear, int) and 0 <= linear < axis_count ** 3, "linear index outside the grid")
    card, remainder = divmod(linear, axis_count * axis_count)
    sector, budget = divmod(remainder, axis_count)
    return card, sector, budget


def coordinates_per_batch(rate: Fraction, setup: Fraction, derate: Fraction) -> tuple[int, int]:
    """Conservative integer batch size, capped by the engine's per-invocation bound.

    uncapped = floor(rate * (target_batch_seconds - setup) * derate);
    size = min(uncapped, engine.MAX_COORDINATES_PER_INVOCATION).
    Returns (size, uncapped).
    """
    _require(isinstance(rate, Fraction) and rate > 0, "throughput rate must be positive")
    _require(isinstance(setup, Fraction) and 0 <= setup < TARGET_BATCH_SECONDS,
             "setup must be non-negative and below the batch target")
    _require(isinstance(derate, Fraction) and 0 < derate <= 1, "derate must lie in (0, 1]")
    _require(TARGET_BATCH_SECONDS < SESSION_BUDGET_SECONDS, "target must stay below the session budget")
    uncapped = math.floor(rate * (TARGET_BATCH_SECONDS - setup) * derate)
    _require(uncapped >= 1, "measured throughput admits no whole coordinate within the batch target after setup")
    return min(uncapped, engine.MAX_COORDINATES_PER_INVOCATION), uncapped


def batch_ranges(total: int, size: int, tag: str) -> list[dict[str, Any]]:
    _require(isinstance(total, int) and total > 0 and isinstance(size, int) and size > 0, "malformed batch sizing")
    count = -(-total // size)
    width = max(4, len(str(count - 1)))
    batches = []
    for index in range(count):
        start = index * size
        stop = min(start + size, total)
        batches.append({"batch_id": f"{tag}_cuda_t4_b{index:0{width}d}", "index": index,
                        "start": start, "stop": stop, "count": stop - start})
    return batches


def build_plan(scale: str, qualification_record: Mapping[str, Any], throughput: Mapping[str, Any],
               derate: Fraction = DEFAULT_DERATE) -> dict[str, Any]:
    """Validate every input and emit the canonical plan; nothing is written."""
    _require(scale in SCALES, "scale must be '0.5x' or '2x'")
    ledgers = load_v14_ledgers()
    identity = validate_qualification_record(qualification_record)
    identity_sha256 = engine.identity_sha256(identity)
    measured = validate_throughput(throughput, identity_sha256)
    rate = measured.pop("_rate")
    setup = measured.pop("_setup")
    size, uncapped = coordinates_per_batch(rate, setup, derate)
    choice = SCALES[scale]
    axis_count = choice["axis_count"]
    total = axis_count ** 3
    batches = batch_ranges(total, size, choice["tag"])
    source_sha256 = cuda.current_hashes(PLAN_SOURCE_RELATIVES)
    plan: dict[str, Any] = {
        "schema": SCHEMA_PLAN,
        "purpose": PURPOSE,
        "track": "cuda-t4",
        "scale": scale,
        "pass_id": choice["pass_id"],
        "linear_order": LINEAR_ORDER,
        "grid": {"axis_count": axis_count, "total_coordinates": total, "axis_index_range": [0, axis_count]},
        "ledger_identity": ledgers[scale]["identity"],
        "all_v14_ledgers_validated": {s: ledgers[s]["identity"]["content_sha256"] for s in SCALES},
        "source_sha256": source_sha256,
        "cuda_qualification_identity_sha256": identity_sha256,
        "cuda_qualification_identity": identity,
        "qualification_record": {
            "schema": qualification_record["schema"],
            "verdict": qualification_record["verdict"],
            "word_mismatches": 0,
            "reduction_mismatches": 0,
            "device_vs_host_cxx_mismatches": 0,
            "validated_coordinates": len(qualification_record["validation"]["per_coordinate"]),
            "evaluations": qualification_record.get("evaluations"),
        },
        "prerequisite_qualification_identities": dict(identity["prerequisites"]),
        "slack_domain_logical_sha256": identity["domain"]["slack"]["logical_sha256"],
        "compile_contract": {"nvcc_flags": list(engine.COMPILE_FLAGS),
                             "cuda_source_sha256": identity["cuda_source_sha256"]},
        "platform": {key: identity[key] for key in PLATFORM_KEYS},
        "throughput": measured,
        "sizing": {
            "measurement_acceptance_basis": measured["acceptance_basis"],
            "target_batch_seconds": TARGET_BATCH_SECONDS,
            "session_budget_seconds": SESSION_BUDGET_SECONDS,
            "derate": _fraction_text(derate),
            "conservative_setup_seconds": _fraction_text(setup),
            "max_coordinates_per_invocation": engine.MAX_COORDINATES_PER_INVOCATION,
            "rule": "uncapped = floor(conservative_rate * (target_batch_seconds - conservative_setup_seconds) * derate); "
                    "coordinates_per_batch = min(uncapped, max_coordinates_per_invocation)",
            "coordinates_per_batch_uncapped": uncapped,
            "coordinates_per_batch": size,
            "cap_applied": uncapped > size,
            "estimated_full_batch_seconds": _fraction_text(setup + Fraction(size) / rate),
            "batch_count": len(batches),
        },
        "batches": batches,
        "merge_rule": ("all batches complete, exact non-overlapping cover, identical plan/ledger/source/"
                       "CUDA-T4/compiler/qualification identity; no RX 9070/ROCm/HIP batch; "
                       "no intra-batch session or platform drift"),
        "scientific_outputs": "intentionally absent",
    }
    plan["content_sha256"] = content_sha256(plan)
    validate_plan(plan)
    return plan


def validate_plan(plan: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Structural and coverage validation of a plan; returns batches by id."""
    _require(isinstance(plan, dict) and plan.get("schema") == SCHEMA_PLAN, "not a V-14 CUDA/T4 batch plan")
    _validate_content_hash(plan, "batch plan")
    _require(plan.get("track") == "cuda-t4" and plan.get("linear_order") == LINEAR_ORDER
             and plan.get("scientific_outputs") == "intentionally absent", "plan contract drift")
    scale = plan.get("scale")
    _require(scale in SCALES and plan.get("pass_id") == SCALES[scale]["pass_id"], "plan scale/pass mismatch")
    grid = plan.get("grid")
    axis_count = SCALES[scale]["axis_count"]
    _require(grid == {"axis_count": axis_count, "total_coordinates": axis_count ** 3,
                      "axis_index_range": [0, axis_count]}, "plan grid drift")
    identity = plan.get("cuda_qualification_identity")
    _require(isinstance(identity, dict), "plan lacks its CUDA/T4 qualification identity")
    _require(plan.get("platform") == {key: identity.get(key) for key in PLATFORM_KEYS}
             and plan["platform"]["backend"] == cuda.BACKEND and not _forbidden_platform(plan["platform"]),
             "plan platform is not the CUDA/T4 qualification platform")
    _require(plan.get("cuda_qualification_identity_sha256") == engine.identity_sha256(identity),
             "plan qualification identity hash mismatch")
    _require(plan.get("compile_contract", {}).get("nvcc_flags") == list(engine.COMPILE_FLAGS),
             "plan compile contract differs from the current nvcc contract")
    _require(plan.get("prerequisite_qualification_identities") == identity.get("prerequisites")
             and isinstance(identity.get("prerequisites"), dict)
             and set(identity["prerequisites"]) == {"unbalanced_identity_sha256", "slack_identity_sha256"},
             "plan does not bind both prerequisite qualification identities")
    batches = plan.get("batches")
    _require(isinstance(batches, list) and batches, "plan has no batches")
    size = plan.get("sizing", {}).get("coordinates_per_batch")
    _require(isinstance(size, int) and 1 <= size <= engine.MAX_COORDINATES_PER_INVOCATION
             and plan["sizing"].get("max_coordinates_per_invocation") == engine.MAX_COORDINATES_PER_INVOCATION
             and plan["sizing"].get("batch_count") == len(batches), "plan sizing drift or invocation cap exceeded")
    by_id: dict[str, dict[str, Any]] = {}
    cursor = 0
    for index, batch in enumerate(batches):
        _require(isinstance(batch, dict) and set(batch) == {"batch_id", "index", "start", "stop", "count"},
                 f"malformed batch entry {index}")
        _require(batch["index"] == index and batch["start"] == cursor and batch["stop"] > batch["start"]
                 and batch["count"] == batch["stop"] - batch["start"] <= size <= engine.MAX_COORDINATES_PER_INVOCATION,
                 f"batch {index} range drift or invocation cap exceeded")
        _require(isinstance(batch["batch_id"], str) and batch["batch_id"] not in by_id, f"duplicate batch id at {index}")
        by_id[batch["batch_id"]] = batch
        cursor = batch["stop"]
    _require(cursor == axis_count ** 3, "plan batches do not cover the grid exactly once")
    return by_id


# --------------------------------------------------------------------------
# Manifests and final-set validation (metadata only)
# --------------------------------------------------------------------------

def manifest_skeleton(plan: Mapping[str, Any], batch_id: str) -> dict[str, Any]:
    """The plan-bound fields a future batch emitter must carry verbatim.

    The emitter adds ``session`` (session_id, device_uuid_hex, identical
    start/end platform fingerprints), ``records`` (record_count and an opaque
    value-file hash), and ``content_sha256``.  No value ever enters a manifest.
    """
    by_id = validate_plan(plan)
    _require(batch_id in by_id, f"batch id is not in the plan: {batch_id}")
    batch = by_id[batch_id]
    return {
        "schema": SCHEMA_MANIFEST,
        "batch_id": batch_id,
        "range": {"start": batch["start"], "stop": batch["stop"], "count": batch["count"]},
        "pass_id": plan["pass_id"],
        "scale": plan["scale"],
        "track": plan["track"],
        "plan_content_sha256": plan["content_sha256"],
        "linear_order": plan["linear_order"],
        "grid": plan["grid"],
        "ledger_identity": plan["ledger_identity"],
        "source_sha256": plan["source_sha256"],
        "cuda_qualification_identity_sha256": plan["cuda_qualification_identity_sha256"],
        "prerequisite_qualification_identities": plan["prerequisite_qualification_identities"],
        "slack_domain_logical_sha256": plan["slack_domain_logical_sha256"],
        "compile_contract": plan["compile_contract"],
        "platform": plan["platform"],
        "scientific_outputs": "intentionally absent",
    }


def _validate_manifest(manifest: object, plan: Mapping[str, Any], by_id: Mapping[str, Mapping[str, Any]],
                       label: str) -> dict[str, Any]:
    _require(isinstance(manifest, dict), f"{label}: manifest is not a JSON object")
    _require(manifest.get("schema") == SCHEMA_MANIFEST, f"{label}: not a V-14 CUDA/T4 batch manifest")
    _validate_content_hash(manifest, f"{label}: manifest")
    lowered = {str(key).lower() for key in manifest}
    _require(not any(key in lowered for key in FORBIDDEN_MANIFEST_KEYS),
             f"{label}: manifest carries a scientific field")
    _require(manifest.get("scientific_outputs") == "intentionally absent", f"{label}: manifest output boundary")
    _require(not _forbidden_platform(manifest.get("platform")),
             f"{label}: RX 9070 / ROCm / HIP / emulation platform is rejected")
    platform = manifest.get("platform")
    _require(isinstance(platform, dict) and platform.get("backend") == cuda.BACKEND
             and isinstance(platform.get("gpu_name"), str)
             and cuda.TARGET_GPU_NAME_PATTERN.fullmatch(platform["gpu_name"]) is not None
             and platform.get("compute_capability") == "%d.%d" % cuda.TARGET_COMPUTE_CAPABILITY
             and platform.get("architecture") == cuda.TARGET_ARCHITECTURE,
             f"{label}: platform is not an NVIDIA Tesla T4 at compute capability 7.5 under CUDA")
    for key in PLAN_BOUND_KEYS:
        _require(manifest.get(key) == plan.get(key) if key != "plan_content_sha256"
                 else manifest.get(key) == plan["content_sha256"],
                 f"{label}: {key} differs from the plan")
    batch_id = manifest.get("batch_id")
    _require(isinstance(batch_id, str) and batch_id in by_id, f"{label}: batch id is not in the plan")
    batch = by_id[batch_id]
    _require(manifest.get("range") == {"start": batch["start"], "stop": batch["stop"], "count": batch["count"]},
             f"{label}: range differs from the plan's range for {batch_id}")
    session = manifest.get("session")
    _require(isinstance(session, dict) and set(session) == {"session_id", "device_uuid_hex",
                                                            "start_platform_sha256", "end_platform_sha256"},
             f"{label}: malformed session record")
    _require(isinstance(session["session_id"], str) and session["session_id"].strip() != "",
             f"{label}: session id missing")
    _require(isinstance(session["device_uuid_hex"], str) and _HEX32.fullmatch(session["device_uuid_hex"]) is not None,
             f"{label}: device UUID missing")
    _require(all(isinstance(session[key], str) and _HEX64.fullmatch(session[key]) is not None
                 for key in ("start_platform_sha256", "end_platform_sha256")),
             f"{label}: platform fingerprints missing")
    _require(session["start_platform_sha256"] == session["end_platform_sha256"],
             f"{label}: platform fingerprint drifted within the batch (mixed session)")
    records = manifest.get("records")
    _require(isinstance(records, dict) and set(records) == {"record_count", "value_file_sha256"}
             and records["record_count"] == batch["count"]
             and isinstance(records["value_file_sha256"], str)
             and _HEX64.fullmatch(records["value_file_sha256"]) is not None,
             f"{label}: record count or value-file identity malformed")
    return manifest


def validate_final_set(plan: Mapping[str, Any], manifests: Sequence[object]) -> dict[str, Any]:
    """Accept a complete, order-independent, identity-homogeneous batch set; otherwise fail closed."""
    by_id = validate_plan(plan)
    _require(isinstance(manifests, (list, tuple)) and manifests, "no batch manifests supplied")
    seen: dict[str, dict[str, Any]] = {}
    identities: set[str] = set()
    sessions: set[str] = set()
    devices: set[str] = set()
    for position, candidate in enumerate(manifests):
        manifest = _validate_manifest(candidate, plan, by_id, f"manifest {position}")
        batch_id = manifest["batch_id"]
        _require(batch_id not in seen, f"duplicate batch: {batch_id}")
        seen[batch_id] = manifest
        identities.add(_sha256_bytes(canonical_bytes({key: manifest[key] for key in PLAN_BOUND_KEYS})))
        sessions.add(manifest["session"]["session_id"])
        devices.add(manifest["session"]["device_uuid_hex"])
    missing = sorted(set(by_id) - set(seen))
    _require(not missing, "incomplete cover; missing batches: " + ", ".join(missing[:8]))
    _require(len(identities) == 1, "batches bind mixed plan/ledger/source/CUDA-T4/compiler identities")
    ordered = sorted(seen.values(), key=lambda item: item["range"]["start"])
    cursor = 0
    for manifest in ordered:
        _require(manifest["range"]["start"] == cursor, f"gap or overlap before {manifest['batch_id']}")
        cursor = manifest["range"]["stop"]
    _require(cursor == plan["grid"]["total_coordinates"], "final set does not end at the grid's last coordinate")
    return {
        "schema": SCHEMA_FINAL_SET,
        "verdict": "accepted",
        "plan_content_sha256": plan["content_sha256"],
        "pass_id": plan["pass_id"],
        "scale": plan["scale"],
        "batch_count": len(seen),
        "total_coordinates": cursor,
        "cuda_qualification_identity_sha256": plan["cuda_qualification_identity_sha256"],
        "platform": plan["platform"],
        "session_count": len(sessions),
        "device_count": len(devices),
        "order_independent": True,
        "scientific_outputs": "intentionally absent",
    }

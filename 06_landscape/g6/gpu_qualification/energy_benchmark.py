"""Non-production throughput benchmark of the reviewed unbalanced-energy GPU kernel.

This module measures how quickly the already reviewed HIP transcript in
``gpu_unbalanced_energy_crosscheck.hip.cpp`` executes on the discrete
``gfx1201`` device under two compile profiles, on the same fixed inputs the
bit-exact cross-check uses (1710 declared raw 20-bit states x 4 reviewed
coefficient points = 6840 evaluations per launch):

1. ``strict_o0`` -- the existing strict cross-check compile command, unchanged;
2. ``candidate_o3`` -- ``-O3`` with fp contraction off and no fast-math; every
   other flag identical.

For each profile the pinned cross-check program is first compiled with that
profile's flags and executed once; its 6840 device and host-C++ bit patterns
are compared against the canonical Python evaluator with the cross-check's
own comparator.  Any mismatch rejects the profile: no timing is measured or
reported for it.  Only then is the benchmark harness (the same source text,
included verbatim, launched repeatedly) compiled with the same flags and
timed; its last-launch bit patterns are compared again and any mismatch
rejects the measurement.

Emitted: compile commands, mismatch counts, launch counts, and durations.
Never emitted: an energy, minimum, tie set, label, rate, or any other
scientific quantity.  A result is a bounded measurement, not a production
claim or an authorization of any GPU backend.  Importing this module has no
side effects and writes nothing.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
from typing import Any, Callable, Mapping

ROOT = Path(__file__).resolve().parents[3]

SCHEMA_PLAN = "decisions_os/g6_gpu_unbalanced_energy_benchmark_plan/v1"
SCHEMA_RUN = "decisions_os/g6_gpu_unbalanced_energy_benchmark_run/v1"
PURPOSE = (
    "non-production throughput benchmark of the reviewed unbalanced-energy GPU "
    "transcript; timings and counts only; no scientific output; no production claim"
)

CROSSCHECK_MODULE_REL = "research/g6/gpu_qualification/energy_crosscheck.py"
BENCH_SOURCE_REL = "research/g6/gpu_qualification/gpu_unbalanced_energy_benchmark.hip.cpp"
# The staged file names are fixed: the harness includes the cross-check source
# by this exact basename from the same temporary directory.
CROSSCHECK_STAGED_NAME = "gpu_unbalanced_energy_crosscheck.hip.cpp"
BENCH_STAGED_NAME = "gpu_unbalanced_energy_benchmark.hip.cpp"
INCLUDE_DIRECTIVE = f'#include "{CROSSCHECK_STAGED_NAME}"'

# Inputs this benchmark consumes beyond the cross-check's own pins.  The
# cross-check library is a consumed input here (it supplies the binding, the
# encoding, and the comparator) and so can be pinned by this module.
PINNED_INPUTS: dict[str, str] = {
    CROSSCHECK_MODULE_REL: "6ceb20042f184ff1d7652024589490d1ccb339930b0be0ecf6a01b30d275f775",
    BENCH_SOURCE_REL: "8697161953eb519575c648cb6010dcb3557679c62768201a0a6dc59954d24c0c",
}
SELF_RELATIVES = (
    "research/g6/gpu_qualification/energy_benchmark.py",
    "research/g6/run_gpu_energy_benchmark.py",
)

# The two compared profiles.  ``optimization`` is the only flag that differs.
PROFILES: tuple[dict[str, str], ...] = (
    {
        "profile_id": "strict_o0",
        "optimization": "-O0",
        "role": "existing strict cross-check profile (baseline)",
    },
    {
        "profile_id": "candidate_o3",
        "optimization": "-O3",
        "role": "candidate profile: -O3 with fp contraction off and no fast-math",
    },
)
# Required in every compile command, host or device.
COMMON_FLAGS = ("-std=c++17", "-ffp-contract=off", "-fno-fast-math")
# Additionally required in every hipcc (device) compile command.
DEVICE_FLAGS = ("-mno-unsafe-fp-atomics", "--offload-arch=gfx1201", "-lamdhip64")
# Any of these anywhere in a compile command is a contract violation.
FORBIDDEN_FLAG_PREFIXES = (
    "-ffast-math", "-Ofast", "-ffp-contract=fast", "-ffp-contract=on", "-ffp-model=fast",
    "-funsafe-math-optimizations", "-fassociative-math", "-freciprocal-math", "-ffinite-math-only",
    "-fno-honor-nans", "-fno-honor-infinities", "-fno-signed-zeros", "-fgpu-flush-denormals-to-zero",
    "-fcuda-flush-denormals-to-zero", "-munsafe-fp-atomics", "-mfma", "-march=", "-mcpu=",
    "-fdenormal-fp-math", "-cl-", "-fno-rounding-math",
)
COMPILE_TIMEOUT_SECONDS = 900
EXECUTE_TIMEOUT_SECONDS = 900

DEFAULT_WARMUP_LAUNCHES = 10
DEFAULT_TIMED_LAUNCHES = 200
MAX_WARMUP_LAUNCHES = 100
MAX_TIMED_LAUNCHES = 5000

# The harness may print exactly these keys, with these types.  Anything else
# on its stdout rejects the measurement.
HARNESS_KEYS: dict[str, type | tuple[type, ...]] = {
    "architecture": str,
    "batch_launches": int,
    "batch_wall_ms": (int, float),
    "block_count": int,
    "block_size": int,
    "device_index": int,
    "device_name": str,
    "device_vs_host_cxx_mismatches": int,
    "evaluations_per_launch": int,
    "per_launch_ms": list,
    "point_count": int,
    "probe": str,
    "scientific_outputs": str,
    "state_count": int,
    "timed_launches": int,
    "warmup_launches": int,
}
HARNESS_PROBE = "unbalanced_energy_transcript_benchmark"


class BenchmarkError(RuntimeError):
    """Raised when the bounded benchmark contract cannot be established."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise BenchmarkError(message)


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def load_crosscheck():
    """Load the pinned cross-check library by path; it is never modified here."""
    path = ROOT / CROSSCHECK_MODULE_REL
    try:
        digest = _sha256_bytes(path.read_bytes())
    except OSError as exc:
        raise BenchmarkError("cross-check library is unreadable") from exc
    _require(digest == PINNED_INPUTS[CROSSCHECK_MODULE_REL], "cross-check library drifted from its pin")
    specification = importlib.util.spec_from_file_location("g6_gpu_energy_crosscheck_for_benchmark", path)
    _require(specification is not None and specification.loader is not None, "cross-check library unavailable")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def all_pins(crosscheck) -> dict[str, str]:
    combined = dict(crosscheck.PINNED_INPUTS)
    combined.update(PINNED_INPUTS)
    return combined


def verify_all_pins(crosscheck) -> dict[str, str]:
    """Fail closed on drift of any cross-check pin or benchmark pin."""
    try:
        return crosscheck.verify_pinned_inputs(all_pins(crosscheck))
    except crosscheck.CrosscheckError as exc:
        raise BenchmarkError(str(exc)) from exc


def profile_by_id(profile_id: str) -> dict[str, str]:
    for profile in PROFILES:
        if profile["profile_id"] == profile_id:
            return dict(profile)
    raise BenchmarkError(f"unknown profile: {profile_id}")


def check_flags(command: list[str]) -> None:
    joined = " ".join(command)
    for prefix in FORBIDDEN_FLAG_PREFIXES:
        _require(not any(token.startswith(prefix) for token in command),
                 f"forbidden compile flag in command: {prefix}")
    for flag in COMMON_FLAGS:
        _require(flag in command, f"compile command lacks {flag}")
    _require("-fno-fast-math" in joined and "-ffp-contract=off" in joined, "compile command relaxes fp semantics")
    levels = [token for token in command if token.startswith("-O")]
    _require(len(levels) == 1 and levels[0] in {"-O0", "-O3"}, "exactly one declared optimisation level is permitted")


def profile_compile_command(crosscheck, hipcc: str, profile: Mapping[str, str], source: Path, binary: Path) -> list[str]:
    """The cross-check compile command with only the optimisation level substituted."""
    baseline = crosscheck.compile_command(hipcc, source, binary)
    _require(baseline.count("-O0") == 1, "cross-check compile command drifted")
    command = [profile["optimization"] if token == "-O0" else token for token in baseline]
    if profile["optimization"] == "-O0":
        _require(command == baseline, "strict profile must equal the cross-check compile command exactly")
    check_flags(command)
    for flag in DEVICE_FLAGS:
        _require(flag in command, f"device compile command lacks {flag}")
    return command


def validate_launch_counts(warmup: int, timed: int) -> None:
    _require(isinstance(warmup, int) and isinstance(timed, int) and not isinstance(warmup, bool)
             and not isinstance(timed, bool), "launch counts must be integers")
    _require(0 <= warmup <= MAX_WARMUP_LAUNCHES, f"warm-up launches must be in 0..{MAX_WARMUP_LAUNCHES}")
    _require(1 <= timed <= MAX_TIMED_LAUNCHES, f"timed launches must be in 1..{MAX_TIMED_LAUNCHES}")


def validate_harness_report(payload: Any, point_count: int, state_count: int, warmup: int, timed: int) -> dict[str, Any]:
    """Accept only the declared timing/count keys; reject any extra field."""
    _require(isinstance(payload, dict), "harness output is not a JSON object")
    _require(set(payload) == set(HARNESS_KEYS), "harness output keys differ from the declared timing contract")
    for key, kind in HARNESS_KEYS.items():
        value = payload[key]
        _require(isinstance(value, kind) and not isinstance(value, bool), f"harness field has unexpected type: {key}")
    _require(payload["probe"] == HARNESS_PROBE and payload["scientific_outputs"] == "intentionally absent",
             "harness output does not declare itself a benchmark without scientific output")
    _require(payload["point_count"] == point_count and payload["state_count"] == state_count
             and payload["evaluations_per_launch"] == point_count * state_count,
             "harness output counts differ from the declared inputs")
    _require(payload["warmup_launches"] == warmup and payload["timed_launches"] == timed
             and payload["batch_launches"] == timed, "harness launch counts differ from the request")
    per_launch = payload["per_launch_ms"]
    _require(len(per_launch) == timed, "per-launch timing count differs from the timed launch count")
    _require(all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and v >= 0.0
                 for v in per_launch), "per-launch timings must be finite non-negative numbers")
    _require(math.isfinite(payload["batch_wall_ms"]) and payload["batch_wall_ms"] >= 0.0,
             "batch wall time must be finite and non-negative")
    _require(payload["block_size"] > 0 and payload["block_count"] * payload["block_size"] >= payload["evaluations_per_launch"],
             "launch geometry does not cover the evaluations")
    return dict(payload)


def summarise_timings(report: Mapping[str, Any]) -> dict[str, Any]:
    """Durations and throughput counts only."""
    per_launch = [float(v) for v in report["per_launch_ms"]]
    evaluations = int(report["evaluations_per_launch"])
    timed = int(report["timed_launches"])
    median_ms = statistics.median(per_launch)
    batch_ms = float(report["batch_wall_ms"])
    return {
        "evaluations_per_launch": evaluations,
        "warmup_launches": int(report["warmup_launches"]),
        "timed_launches": timed,
        "timed_evaluations_total": evaluations * timed,
        "per_launch_ms": {
            "min": min(per_launch),
            "median": median_ms,
            "mean": statistics.fmean(per_launch),
            "max": max(per_launch),
        },
        "evaluations_per_second_at_median_launch": (evaluations / (median_ms / 1000.0)) if median_ms > 0.0 else None,
        "batch": {
            "launches": int(report["batch_launches"]),
            "wall_ms": batch_ms,
            "mean_launch_ms": batch_ms / timed,
            "evaluations_per_second": (evaluations * timed / (batch_ms / 1000.0)) if batch_ms > 0.0 else None,
        },
        "launch_geometry": {"block_size": int(report["block_size"]), "block_count": int(report["block_count"])},
    }


def _run_subprocess(command: list[str], cwd: Path, timeout: int, label: str) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        return subprocess.run(command, cwd=cwd, env=environment, text=True, capture_output=True,
                              check=False, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise BenchmarkError(f"{label} did not complete: {type(exc).__name__}") from exc


def stage_sources(crosscheck, staging: Path) -> tuple[Path, Path]:
    """Copy both pinned sources into the staging directory and re-verify their hashes."""
    crosscheck_source = staging / CROSSCHECK_STAGED_NAME
    bench_source = staging / BENCH_STAGED_NAME
    crosscheck_source.write_bytes((ROOT / crosscheck.HIP_SOURCE_REL).read_bytes())
    bench_source.write_bytes((ROOT / BENCH_SOURCE_REL).read_bytes())
    _require(_sha256_bytes(crosscheck_source.read_bytes()) == crosscheck.PINNED_INPUTS[crosscheck.HIP_SOURCE_REL],
             "staged cross-check source does not match its pin")
    _require(_sha256_bytes(bench_source.read_bytes()) == PINNED_INPUTS[BENCH_SOURCE_REL],
             "staged benchmark harness does not match its pin")
    _require(INCLUDE_DIRECTIVE in bench_source.read_text(encoding="utf-8"),
             "benchmark harness does not include the pinned cross-check source")
    return crosscheck_source, bench_source


def evaluate_profile(crosscheck, profile: Mapping[str, str], staging: Path,
                     build_command: Callable[[Mapping[str, str], Path, Path], list[str]],
                     architecture_accepts: Callable[[object], bool],
                     encoded: bytes, reference: tuple[int, ...],
                     points: tuple[Mapping[str, Any], ...], states: tuple[int, ...],
                     warmup: int, timed: int) -> dict[str, Any]:
    """Gate one profile on the 6840-evaluation cross-check, then time it.

    ``build_command`` returns the compile command for (profile, source,
    binary); ``architecture_accepts`` decides whether the reported device
    architecture is the intended target.  Both are injected so the
    hardware-free host-emulation verifier can drive exactly this gate.
    """
    validate_launch_counts(warmup, timed)
    profile_dir = staging / profile["profile_id"]
    profile_dir.mkdir()
    crosscheck_source, bench_source = stage_sources(crosscheck, profile_dir)
    input_path = profile_dir / "input.words"
    input_path.write_bytes(encoded)
    result: dict[str, Any] = {
        "profile_id": profile["profile_id"],
        "optimization": profile["optimization"],
        "role": profile["role"],
        "status": "rejected",
        "crosscheck_gate": None,
        "benchmark_gate": None,
    }

    # Gate 1: the pinned cross-check program itself, under this profile's flags.
    crosscheck_binary = profile_dir / "crosscheck"
    crosscheck_command = build_command(profile, crosscheck_source, crosscheck_binary)
    check_flags(crosscheck_command)
    result["crosscheck_compile_command"] = list(crosscheck_command)
    compilation = _run_subprocess(crosscheck_command, profile_dir, COMPILE_TIMEOUT_SECONDS, "cross-check compilation")
    if compilation.returncode != 0:
        result["rejection"] = "cross-check compilation failed under this profile: " + compilation.stderr[-1500:]
        return result
    crosscheck_output = profile_dir / "crosscheck_output.words"
    execution = _run_subprocess([str(crosscheck_binary), str(input_path), str(crosscheck_output)], profile_dir,
                                EXECUTE_TIMEOUT_SECONDS, "cross-check execution")
    if execution.returncode != 0:
        result["rejection"] = "cross-check execution failed under this profile: " + execution.stderr[-1500:]
        return result
    try:
        device_report = json.loads(execution.stdout)
    except json.JSONDecodeError as exc:
        raise BenchmarkError("cross-check emitted malformed JSON") from exc
    _require(isinstance(device_report, dict) and architecture_accepts(device_report.get("architecture")),
             "cross-check ran on an unexpected architecture")
    _require(device_report.get("point_count") == len(points) and device_report.get("state_count") == len(states),
             "cross-check reported unexpected counts")
    try:
        device_index, device_bits, host_bits = crosscheck.decode_output(crosscheck_output.read_bytes(), len(points), len(states))
    except crosscheck.CrosscheckError as exc:
        raise BenchmarkError(str(exc)) from exc
    _require(device_index == device_report.get("device_index"), "cross-check device index disagreement")
    gpu = crosscheck.compare_bits(reference, device_bits, points, states)
    host = crosscheck.compare_bits(reference, host_bits, points, states)
    result["crosscheck_gate"] = {
        "evaluations": gpu["evaluations"],
        "gpu_vs_python_mismatches": gpu["mismatches"],
        "host_cxx_vs_python_mismatches": host["mismatches"],
        "device": {key: device_report.get(key) for key in ("architecture", "device_index", "device_name")},
        "passed": gpu["mismatches"] == 0 and host["mismatches"] == 0,
    }
    if not result["crosscheck_gate"]["passed"]:
        result["rejection"] = "profile is not bit-exact on the 6840-evaluation cross-check; no timing was measured"
        return result

    # Gate 2 + measurement: the harness, same source text, same flags.
    bench_binary = profile_dir / "benchmark"
    bench_command = build_command(profile, bench_source, bench_binary)
    check_flags(bench_command)
    result["benchmark_compile_command"] = list(bench_command)
    compilation = _run_subprocess(bench_command, profile_dir, COMPILE_TIMEOUT_SECONDS, "benchmark compilation")
    if compilation.returncode != 0:
        result["rejection"] = "benchmark harness compilation failed under this profile: " + compilation.stderr[-1500:]
        return result
    bench_output = profile_dir / "benchmark_output.words"
    execution = _run_subprocess([str(bench_binary), str(input_path), str(bench_output), str(warmup), str(timed)],
                                profile_dir, EXECUTE_TIMEOUT_SECONDS, "benchmark execution")
    if execution.returncode != 0:
        result["rejection"] = "benchmark harness execution failed: " + execution.stderr[-1500:]
        return result
    try:
        harness_report = json.loads(execution.stdout)
    except json.JSONDecodeError as exc:
        raise BenchmarkError("benchmark harness emitted malformed JSON") from exc
    harness_report = validate_harness_report(harness_report, len(points), len(states), warmup, timed)
    _require(architecture_accepts(harness_report["architecture"]), "benchmark ran on an unexpected architecture")
    _require(harness_report["device_index"] == device_index, "benchmark and cross-check selected different devices")
    try:
        bench_device_index, bench_device_bits, bench_host_bits = crosscheck.decode_output(
            bench_output.read_bytes(), len(points), len(states))
    except crosscheck.CrosscheckError as exc:
        raise BenchmarkError(str(exc)) from exc
    _require(bench_device_index == device_index, "benchmark output device index disagreement")
    bench_gpu = crosscheck.compare_bits(reference, bench_device_bits, points, states)
    bench_host = crosscheck.compare_bits(reference, bench_host_bits, points, states)
    result["benchmark_gate"] = {
        "evaluations": bench_gpu["evaluations"],
        "last_launch_gpu_vs_python_mismatches": bench_gpu["mismatches"],
        "host_cxx_vs_python_mismatches": bench_host["mismatches"],
        "device_vs_host_cxx_mismatches_reported": harness_report["device_vs_host_cxx_mismatches"],
        "passed": bench_gpu["mismatches"] == 0 and bench_host["mismatches"] == 0
                  and harness_report["device_vs_host_cxx_mismatches"] == 0,
    }
    if not result["benchmark_gate"]["passed"]:
        result["rejection"] = "benchmark harness output is not bit-exact; timings withheld"
        return result
    result["status"] = "accepted"
    result["timings"] = summarise_timings(harness_report)
    return result


def _bind(crosscheck):
    try:
        instance, points, states, families, _pins = crosscheck._bind()
    except crosscheck.CrosscheckError as exc:
        raise BenchmarkError(str(exc)) from exc
    return instance, points, states, families


def build_plan(warmup: int = DEFAULT_WARMUP_LAUNCHES, timed: int = DEFAULT_TIMED_LAUNCHES) -> dict[str, Any]:
    """Validate every binding and describe the benchmark without compiling or timing."""
    validate_launch_counts(warmup, timed)
    crosscheck = load_crosscheck()
    pins = verify_all_pins(crosscheck)
    _instance, points, states, families = _bind(crosscheck)
    templates = []
    for profile in PROFILES:
        templates.append({
            **profile,
            "compile_command_template": profile_compile_command(
                crosscheck, "hipcc", profile, Path("<tmp>/<profile>/source.hip.cpp"), Path("<tmp>/<profile>/binary")),
        })
    return {
        "schema": SCHEMA_PLAN,
        "mode": "plan",
        "purpose": PURPOSE,
        "encoding": crosscheck.ENCODING,
        "reference": crosscheck.REFERENCE,
        "kernel_source": crosscheck.HIP_SOURCE_REL,
        "harness_source": BENCH_SOURCE_REL,
        "harness_mechanism": "textual inclusion of the pinned cross-check source with its main renamed; kernel text unchanged",
        "target_architecture": crosscheck.TARGET_ARCHITECTURE,
        "pinned_inputs": pins,
        "self_sha256": crosscheck.current_hashes(SELF_RELATIVES),
        "coefficient_points": [point["point_id"] for point in points],
        "state_set": {"count": len(states), "families": families,
                      "sha256_le_uint64_sequence": crosscheck.states_digest(states)},
        "evaluations_per_launch": len(points) * len(states),
        "launches": {"warmup": warmup, "timed": timed, "batch": timed,
                     "bounds": {"warmup_max": MAX_WARMUP_LAUNCHES, "timed_max": MAX_TIMED_LAUNCHES}},
        "profiles": templates,
        "gate": "each profile must report 0 GPU-vs-Python and 0 host-C++-vs-Python mismatches over "
                f"{len(points) * len(states)} evaluations before and after timing; otherwise it is rejected and no timing is emitted",
        "hipcc_located": crosscheck._locate_hipcc() is not None,
        "writes": "none",
        "scientific_outputs": "intentionally absent",
        "production_claim": "none",
    }


def run_benchmark(warmup: int = DEFAULT_WARMUP_LAUNCHES, timed: int = DEFAULT_TIMED_LAUNCHES) -> dict[str, Any]:
    """Compile, gate, and time both profiles in a temporary directory; report timings and counts only."""
    _require(os.environ.get("PYTHONDONTWRITEBYTECODE") == "1", "PYTHONDONTWRITEBYTECODE=1 is required")
    validate_launch_counts(warmup, timed)
    crosscheck = load_crosscheck()
    hipcc = crosscheck._locate_hipcc()
    _require(hipcc is not None, "hipcc is unavailable; the benchmark cannot run on this host")
    pins_before = verify_all_pins(crosscheck)
    self_before = crosscheck.current_hashes(SELF_RELATIVES)
    platform_before = crosscheck._platform_fingerprint()
    instance, points, states, families = _bind(crosscheck)
    reference = crosscheck.python_reference_bits(instance, points, states)
    encoded = crosscheck.encode_inputs(instance, points, states)

    def build_command(profile: Mapping[str, str], source: Path, binary: Path) -> list[str]:
        return profile_compile_command(crosscheck, hipcc, profile, source, binary)

    results: list[dict[str, Any]] = []
    temporary_path: Path | None = None
    with tempfile.TemporaryDirectory(prefix="g6-gpu-energy-benchmark-") as temporary:
        temporary_path = Path(temporary)
        for profile in PROFILES:
            results.append(evaluate_profile(crosscheck, profile, temporary_path, build_command,
                                            crosscheck._architecture_is_target, encoded, reference,
                                            points, states, warmup, timed))
    _require(temporary_path is not None and not temporary_path.exists(), "temporary directory was not removed")
    pins_after = verify_all_pins(crosscheck)
    _require(pins_after == pins_before, "pinned input drift during the benchmark")
    _require(crosscheck.current_hashes(SELF_RELATIVES) == self_before, "benchmark source drift during the run")
    _require(crosscheck._platform_fingerprint() == platform_before, "platform fingerprint drift during the run")
    accepted = {result["profile_id"]: result for result in results if result["status"] == "accepted"}
    comparison: dict[str, Any] | None = None
    if set(accepted) == {profile["profile_id"] for profile in PROFILES}:
        strict = accepted["strict_o0"]["timings"]
        candidate = accepted["candidate_o3"]["timings"]
        comparison = {
            "median_launch_ms_ratio_strict_over_candidate":
                strict["per_launch_ms"]["median"] / candidate["per_launch_ms"]["median"]
                if candidate["per_launch_ms"]["median"] > 0.0 else None,
            "batch_wall_ms_ratio_strict_over_candidate":
                strict["batch"]["wall_ms"] / candidate["batch"]["wall_ms"]
                if candidate["batch"]["wall_ms"] > 0.0 else None,
            "meaning": "duration ratio on this fixed 6840-evaluation input only; not a production throughput claim",
        }
    return {
        "schema": SCHEMA_RUN,
        "mode": "run",
        "purpose": PURPOSE,
        "encoding": crosscheck.ENCODING,
        "reference": crosscheck.REFERENCE,
        "target_architecture": crosscheck.TARGET_ARCHITECTURE,
        "platform": platform_before,
        "pinned_inputs": pins_before,
        "pinned_inputs_after_run": pins_after,
        "self_sha256": self_before,
        "coefficient_points": [point["point_id"] for point in points],
        "state_set": {"count": len(states), "families": families,
                      "sha256_le_uint64_sequence": crosscheck.states_digest(states)},
        "evaluations_per_launch": len(points) * len(states),
        "launches": {"warmup": warmup, "timed": timed, "batch": timed},
        "profiles": results,
        "comparison": comparison,
        "temporary_directory_removed": True,
        "verdict": "accepted" if comparison is not None else "rejected",
        "writes": "none",
        "scientific_outputs": "intentionally absent",
        "production_claim": "none",
    }

"""Execution-locked, non-scientific Gate-9 CUDA corruption qualification.

The approved clean dry run proves one unchanged synthetic core ran on a T4.
Amendment A separately requires deliberately corrupted kernels to be rejected
on the GPU before any Stage-2 candidate is generated.  This module prepares
that check without touching canonical inputs or changing the approved core.

``build_plan`` is read-only and never looks up nvcc. ``run_qualification``
refuses before nvcc unless a later owner-approved, hash-exact release exists.
Even a successful GPU execution is only a pending qualification observation:
the Kaggle-selected image digest must be bound by a separate read-only
post-run audit before a production qualification identity can be accepted.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
from typing import NamedTuple

from research.g9.cuda_qualification import stage2_cuda_core_stream_engine as core
from research.g9.cuda_qualification import stage2_cuda_core_qualification as clean
from research.g9.cuda_qualification import stage2_cuda_execution_contract as contract


ROOT = Path(__file__).resolve().parents[3]
CORE_REL = "research/g9/cuda_qualification/stage2_cuda_core_stream_engine.cu"
CORE_RELEASE_REL = "research/decisions/GATE_9_CUDA_CORE_DRY_RUN_RELEASE.json"
CORE_RELEASE_SHA256 = "50f25827ef07b8fcbf3f19223f3982b486f1b11c5d71a7d0c037fd1c6f5328a9"
CLEAN_RECEIPT_REL = "research/g9/kaggle_dry_run/GATE_9_KAGGLE_CORE_V3_VERSION1_RECEIPT.json"
CLEAN_RECEIPT_SHA256 = "41a32675e667ffe8e9fb0e2a5d15b191c242f39a221ce9a3d941152f41530859"
RELEASE_REL = "research/decisions/GATE_9_CUDA_CORE_CORRUPTION_QUALIFICATION_RELEASE.json"
RELEASE_SCHEMA = "decisions_os/g9_cuda_core_corruption_qualification_release/v1"
PLAN_SCHEMA = "decisions_os/g9_cuda_core_corruption_qualification_plan/v1"
RECEIPT_SCHEMA = "decisions_os/g9_cuda_core_corruption_qualification_receipt/v1"
ALLOW_ENV = "G9_ALLOW_NONSCIENTIFIC_CUDA_CORRUPTION_QUALIFICATION"

# The eight previously reviewed numerical sources plus this additive harness,
# its CLI/fixture, and the independently established host mutation authority.
# The approved clean release pins the original eight.
SOURCE_RELS = tuple(sorted((*clean.SOURCE_RELS,
    "research/g9/cuda_qualification/stage2_cuda_core_corruption_qualification.py",
    "research/g9/run_stage2_cuda_core_corruption_qualification.py",
    "research/g9/verify_stage2_cuda_core_corruption_qualification_fixtures.py",
    "research/g9/verify_stage2_cuda_core_stream_engine_host_emulation.py",
)))


class CorruptionQualificationError(RuntimeError):
    """The A-path is unreleased, malformed, or numerically unqualified."""


class Mutation(NamedTuple):
    label: str
    category: str
    old: str
    new: str


# Every mutation has an exact unique anchor in the reviewed .cu.  All are
# expected to compile; a compiler refusal is *not* counted as numerical
# rejection.  The on-GPU report must be well-formed and disagree with the
# independently computed Python reference.  Several also fail device-side.
MUTATIONS = (
    Mutation("canonical_index_reversal", "index_order",
        "return ((index >> (kDecodedWidth - 1u - asset)) & 1u) != 0u;",
        "return ((index >> asset) & 1u) != 0u;"),
    Mutation("energy_reassociation", "accumulation_order",
        "    energies[index] = h + ((-linear) + quadratic);",
        "    energies[index] = (h + (-linear)) + quadratic;"),
    Mutation("slack_register_layout_drift", "slack_register_handling",
        "  return reg < kSectorCount ? (reg * kSectorSlackBits) : (kSectorCount * kSectorSlackBits);",
        "  return reg < kSectorCount ? reg : (kSectorCount * kSectorSlackBits);"),
    Mutation("tied_lift_loss", "slack_register_handling",
        "  values[0] = low; penalties[0] = penalty_low;\n"
        "  values[1] = high; penalties[1] = penalty_high;\n"
        "  return 2u;",
        "  values[0] = low; penalties[0] = penalty_low;\n"
        "  return 1u;"),
    Mutation("first_seen_minimum_weakened", "index_order",
        "    if (!have || value < best) { best = value; best_index = position; have = true; }",
        "    if (!have || value <= best) { best = value; best_index = position; have = true; }"),
    Mutation("d015_scale_omitted", "tie_threshold",
        "  const double scale = lambda_ref + maximum;",
        "  const double scale = lambda_ref;"),
    Mutation("c_h_bit_permutation", "tie_threshold",
        "  if (gap <= (1024.0 * kEpsilon) * scale) flags |= 1u;\n"
        "  if (gap <= (2048.0 * kEpsilon) * scale) flags |= 2u;\n"
        "  if (gap <= (4096.0 * kEpsilon) * scale) flags |= 4u;",
        "  if (gap <= (1024.0 * kEpsilon) * scale) flags |= 4u;\n"
        "  if (gap <= (2048.0 * kEpsilon) * scale) flags |= 2u;\n"
        "  if (gap <= (4096.0 * kEpsilon) * scale) flags |= 1u;"),
    Mutation("nonfinite_energy_injection", "nonfinite_output",
        "    energies[index] = h + ((-linear) + quadratic);\n    return;",
        "    energies[index] = h + ((-linear) + quadratic);\n"
        "    if (index == 654321u) energies[index] = 0.0 / 0.0;\n    return;"),
)
REQUIRED_CATEGORIES = frozenset({
    "accumulation_order", "index_order", "tie_threshold",
    "slack_register_handling", "nonfinite_output",
})


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CorruptionQualificationError(message)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_bound(relative: str) -> bytes:
    _require(relative.startswith("research/") and ".." not in relative.split("/"),
             "bound path is not a plain research path")
    path = ROOT / relative
    _require(path.is_file() and not path.is_symlink(), "bound file is missing: " + relative)
    return path.read_bytes()


def _core_release() -> dict[str, object]:
    raw = _read_bound(CORE_RELEASE_REL)
    _require(_sha(raw) == CORE_RELEASE_SHA256, "approved clean core release hash drift")
    try:
        release = json.loads(raw)
    except ValueError as exc:
        raise CorruptionQualificationError("clean core release is invalid JSON") from exc
    _require(type(release) is dict and raw == contract.canonical_bytes(release) + b"\n" and
             release.get("status") == "approved" and
             release.get("schema") == clean.RELEASE_SCHEMA,
             "clean core release shape drift")
    _require(release.get("source_sha256") == clean._source_hashes() and
             release.get("authorities") == clean._authorities(),
             "clean core source or authority drift")
    return release


def _clean_receipt(release: dict[str, object]) -> dict[str, object]:
    raw = _read_bound(CLEAN_RECEIPT_REL)
    _require(_sha(raw) == CLEAN_RECEIPT_SHA256, "clean T4 dry-run receipt hash drift")
    try:
        receipt = json.loads(raw)
    except ValueError as exc:
        raise CorruptionQualificationError("clean T4 receipt is invalid JSON") from exc
    _require(type(receipt) is dict and type(receipt.get("source_sha256")) is dict and
             type(receipt.get("self_test_report")) is dict,
             "clean T4 receipt has invalid containers")
    _require(type(receipt) is dict and raw == contract.canonical_bytes(receipt) + b"\n" and
             receipt.get("content_sha256") == contract.content_sha256(receipt) and
             receipt.get("execution_release_sha256") == CORE_RELEASE_SHA256 and
             receipt["source_sha256"].items() >= release["source_sha256"].items() and
             receipt.get("authorities") == release["authorities"] and
             receipt.get("mode") == "non_scientific_dry_run" and
             receipt.get("amendment_A_status") == "not_satisfied_corrupted_kernel_tests_pending" and
             receipt.get("scientific_outputs") == "intentionally absent" and
             receipt["self_test_report"].get("verdict") == "pass",
             "clean T4 receipt binding or non-scientific scope drift")
    return receipt


def mutated_sources(source: str) -> tuple[tuple[Mutation, str], ...]:
    _require(type(source) is str and source, "CUDA source is empty")
    _require(len({m.label for m in MUTATIONS}) == len(MUTATIONS) and
             {m.category for m in MUTATIONS} == REQUIRED_CATEGORIES,
             "mutation labels or required A categories drift")
    result = []
    for mutation in MUTATIONS:
        _require(source.count(mutation.old) == 1 and mutation.old != mutation.new,
                 "mutation anchor is missing or ambiguous: " + mutation.label)
        changed = source.replace(mutation.old, mutation.new, 1)
        _require(changed != source and changed.count(mutation.new) == 1,
                 "mutation did not change exactly one anchor: " + mutation.label)
        result.append((mutation, changed))
    _require(len({_sha(text.encode("utf-8")) for _, text in result}) == len(result),
             "two mutations produced the same source")
    return tuple(result)


def source_hashes() -> dict[str, str]:
    return {relative: _sha(_read_bound(relative)) for relative in SOURCE_RELS}


def build_plan() -> dict[str, object]:
    """Read-only source/fixture plan; no nvcc lookup or CUDA operation."""
    release = _core_release()
    _clean_receipt(release)
    source = _read_bound(CORE_REL).decode("utf-8")
    rows = [{"label": mutation.label, "category": mutation.category,
             "source_sha256": _sha(text.encode("utf-8"))}
            for mutation, text in mutated_sources(source)]
    body: dict[str, object] = {
        "schema": PLAN_SCHEMA,
        "mode": "non_scientific_corruption_plan",
        "scientific_outputs": "intentionally absent",
        "stage2_inputs": "intentionally absent",
        "execution_release": "separate_owner_release_required",
        "core_release_sha256": CORE_RELEASE_SHA256,
        "clean_dry_run_receipt_sha256": CLEAN_RECEIPT_SHA256,
        "source_sha256": source_hashes(),
        "compile_flags": list(clean.COMPILE_FLAGS),
        "mutations": rows,
        "image_digest_status": "post_run_metadata_audit_required",
    }
    body["content_sha256"] = contract.content_sha256(body)
    return body


def _released(reviewed: object) -> dict[str, object]:
    """All release checks run before shutil.which, compiler or device access."""
    _require(os.environ.get("PYTHONDONTWRITEBYTECODE") == "1",
             "PYTHONDONTWRITEBYTECODE=1 is required")
    _require(type(reviewed) is str and len(reviewed) == 64 and
             all(c in "0123456789abcdef" for c in reviewed),
             "reviewed A-release SHA-256 is required")
    _require(os.environ.get(ALLOW_ENV) == "1", "separate A-execution permission is required")
    plan = build_plan()
    path = ROOT / RELEASE_REL
    _require(path.is_file() and not path.is_symlink(), "A-execution release is unavailable")
    raw = path.read_bytes()
    _require(_sha(raw) == reviewed, "A-execution release hash differs from reviewed handoff")
    try:
        release = json.loads(raw)
    except ValueError as exc:
        raise CorruptionQualificationError("A-execution release is invalid JSON") from exc
    _require(type(release) is dict and raw == contract.canonical_bytes(release) + b"\n" and
             set(release) == {"schema", "status", "plan_content_sha256", "source_sha256"} and
             release["schema"] == RELEASE_SCHEMA and release["status"] == "approved" and
             release["plan_content_sha256"] == plan["content_sha256"] and
             release["source_sha256"] == plan["source_sha256"],
             "A-execution release does not bind the reviewed plan and source map")
    return plan


def _run(command: list[str], label: str, *, timeout: int) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True,
                                check=False, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CorruptionQualificationError(label + " failed or timed out") from exc
    return result


def _json_stdout(result: subprocess.CompletedProcess[str], label: str) -> dict[str, object]:
    try:
        value = json.loads(result.stdout)
    except ValueError as exc:
        raise CorruptionQualificationError(label + " did not emit one JSON report") from exc
    _require(type(value) is dict, label + " emitted a non-object report")
    return value


def _runtime_build(nvcc: str, dev_dir: Path = Path("/dev")) -> dict[str, object]:
    cuda_home = os.environ.get("CUDA_HOME", "")
    path_entries = [os.path.normpath(part) for part in os.environ.get("PATH", "").split(os.pathsep) if part]
    _require(os.environ.get("COLAB_IMAGE_TYPE") == "gpu", "runtime is not a GPU image")
    _require(cuda_home and os.path.isabs(cuda_home) and
             os.path.normpath(os.path.join(cuda_home, "bin")) in path_entries and
             os.path.normpath(nvcc) == os.path.normpath(os.path.join(cuda_home, "bin", "nvcc")),
             "CUDA_HOME/bin/nvcc is not the selected compiler")
    devices = sorted(p.name for p in dev_dir.glob("nvidia[0-9]*")
                     if p.name[6:].isdigit() and p.is_char_device())
    _require(devices, "no NVIDIA character device is available")
    keys = ("BUILD_DATE", "GIT_COMMIT", "CUDA_VERSION")
    values = {key: os.environ.get(key, "") for key in keys}
    _require(all(0 < len(value) <= 128 and value.isascii() and value.isprintable()
                 for value in values.values()), "runtime image/build fields are missing or invalid")
    try:
        import numpy as np
    except ImportError as exc:
        raise CorruptionQualificationError("NumPy is unavailable for the platform identity") from exc
    language = {"python_version": platform.python_version(),
                "numpy_version": np.__version__}
    _require(all(type(value) is str and 0 < len(value) <= 128 and
                 value.isascii() and value.isprintable() for value in language.values()),
             "Python/NumPy platform fields are missing or invalid")
    return {**values, "COLAB_IMAGE_TYPE": "gpu", "cuda_home": cuda_home,
            "nvcc_path": nvcc, "nvidia_device_count": len(devices), **language}


def run_qualification(reviewed: str) -> dict[str, object]:
    """Future GPU A-check; unreachable until a separate owner release."""
    plan = _released(reviewed)
    before = source_hashes()
    _require(before == plan["source_sha256"], "A source map changed before nvcc lookup")
    nvcc = shutil.which("nvcc")
    _require(nvcc is not None, "nvcc is unavailable")
    runtime = _runtime_build(nvcc)
    version = _run([nvcc, "--version"], "nvcc version", timeout=30)
    _require(version.returncode == 0 and version.stdout.strip(), "nvcc version failed")
    source = _read_bound(CORE_REL).decode("utf-8")
    changes = mutated_sources(source)
    with tempfile.TemporaryDirectory(prefix="g9-core-A-corruptions-") as temporary:
        directory = Path(temporary)
        probe_source = directory / "platform_probe.cu"
        probe_binary = directory / "platform_probe"
        probe_source.write_text(clean.PLATFORM_PROBE, encoding="ascii")
        compiled_probe = _run([nvcc, *clean.COMPILE_FLAGS, str(probe_source), "-o", str(probe_binary)],
                              "platform-probe compilation", timeout=180)
        _require(compiled_probe.returncode == 0, "platform probe did not compile")
        probe_result = _run([str(probe_binary)], "platform probe", timeout=60)
        _require(probe_result.returncode == 0, "platform probe failed")
        probe = _json_stdout(probe_result, "platform probe")
        _require(set(probe) == {"gpu_name", "compute_capability", "cuda_driver_version",
                                "cuda_runtime_version"} and
                 all(type(value) is str and value for value in probe.values()),
                 "platform probe fields are malformed")

        baseline_binary = directory / "baseline"
        baseline_compile = _run([nvcc, *clean.COMPILE_FLAGS, str(ROOT / CORE_REL),
                                 "-o", str(baseline_binary)], "baseline compilation", timeout=300)
        _require(baseline_compile.returncode == 0, "reviewed baseline did not compile")
        baseline_result = _run([str(baseline_binary), "--self-test"], "baseline self-test", timeout=300)
        _require(baseline_result.returncode == 0, "reviewed baseline failed on GPU")
        baseline = _json_stdout(baseline_result, "baseline")
        domain = core.build_domain(core.synthetic_payload())
        scans = {(row, encoding): core.scan(domain, row, encoding)
                 for row in core.ROW_NAMES for encoding in core.ENCODINGS}
        generic = {(row, encoding): core.scan(domain, core.coefficient_row(row), encoding, control={})
                   for row in core.ROW_NAMES for encoding in core.ENCODINGS}
        try:
            core.validate_self_test_report(baseline, scans, domain, generic)
        except core.CoreStreamEngineError as exc:
            raise CorruptionQualificationError("GPU baseline disagrees with Python") from exc
        _require(baseline["device_name"] == probe["gpu_name"] and baseline["device_index"] == 0,
                 "baseline and platform probe selected different GPUs")

        results = []
        for mutation, changed in changes:
            candidate = directory / (mutation.label + ".cu")
            binary = directory / mutation.label
            candidate.write_text(changed, encoding="utf-8")
            mutation_sha = _sha(candidate.read_bytes())
            planned = next(row for row in plan["mutations"] if row["label"] == mutation.label)
            _require(mutation_sha == planned["source_sha256"],
                     "mutated source differs from sealed plan: " + mutation.label)
            compiled = _run([nvcc, *clean.COMPILE_FLAGS, str(candidate), "-o", str(binary)],
                            mutation.label + " compilation", timeout=300)
            _require(compiled.returncode == 0,
                     "corrupted kernel did not compile; numerical rejection unproven: " + mutation.label)
            executed = _run([str(binary), "--self-test"], mutation.label + " self-test", timeout=300)
            _require(executed.returncode in (0, 1),
                     "corrupted kernel crashed or had an unexpected exit: " + mutation.label)
            report = _json_stdout(executed, mutation.label)
            _require(report.get("device_name") == baseline["device_name"] and
                     report.get("device_index") == 0 and
                     report.get("scientific_outputs") == "intentionally absent",
                     "corrupted kernel changed device or output scope: " + mutation.label)
            try:
                core.validate_self_test_report(report, scans, domain, generic)
            except core.CoreStreamEngineError as exc:
                reason = str(exc)[:200]
            else:
                raise CorruptionQualificationError(
                    "corrupted kernel escaped the Python reference: " + mutation.label)
            results.append({"label": mutation.label, "category": mutation.category,
                            "source_sha256": mutation_sha,
                            "device_self_test_rejected": executed.returncode == 1,
                            "python_reference_rejected": True,
                            "rejection_reason": reason})

    _require(source_hashes() == before, "A source map changed during qualification")
    receipt: dict[str, object] = {
        "schema": RECEIPT_SCHEMA,
        "mode": "non_scientific_corruption_qualification",
        "scientific_outputs": "intentionally absent",
        "stage2_inputs": "intentionally absent",
        "verdict": "gpu_corruption_checks_passed_pending_image_metadata_audit",
        "amendment_A_status": "not_satisfied_pending_post_run_audit_and_owner_acceptance",
        "execution_release_sha256": reviewed,
        "plan_content_sha256": plan["content_sha256"],
        "source_sha256": before,
        "core_release_sha256": CORE_RELEASE_SHA256,
        "clean_dry_run_receipt_sha256": CLEAN_RECEIPT_SHA256,
        "baseline_report_sha256": _sha(contract.canonical_bytes(baseline)),
        "platform_probe": probe,
        "runtime_build_observed": runtime,
        "nvcc_version": version.stdout.strip(),
        "compiler_flags": list(clean.COMPILE_FLAGS),
        "image_digest_status": "post_run_metadata_audit_required",
        "mutations": results,
    }
    receipt["content_sha256"] = contract.content_sha256(receipt)
    return receipt

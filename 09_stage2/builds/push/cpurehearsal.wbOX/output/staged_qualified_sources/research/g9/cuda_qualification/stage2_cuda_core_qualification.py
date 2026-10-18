"""Plan and future non-scientific Kaggle qualification of the full-domain core.

The present source is execution-locked: its release record remains pending.
Implementing and fixture-testing this path is authorized; compiling or running
CUDA is not. A later owner-approved final release SHA-256 must be supplied and
must bind the exact reviewed source map before this module can seek nvcc.
No Stage-2 instance input is read.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import struct
import subprocess
import sys
import tempfile

from research.g9.cuda_qualification import stage2_cuda_core_stream_engine as core
from research.g9.cuda_qualification import stage2_cuda_core_bridge as bridge
from research.g9.cuda_qualification import stage2_cuda_execution_contract as contract
from research.g9.cuda_qualification import stage2_cuda_input_frame as input_frame


ROOT = Path(__file__).resolve().parents[3]
AMENDMENT_REL = "research/decisions/GATE_9_STAGE2_KAGGLE_CUDA_AMENDMENT_DRAFT.md"
APPROVAL_REL = "research/decisions/GATE_9_STAGE2_KAGGLE_CUDA_AMENDMENT_APPROVAL.md"
CUDA_SOURCE_REL = "research/g9/cuda_qualification/stage2_cuda_core_stream_engine.cu"
SOURCE_RELS = (
    CUDA_SOURCE_REL,
    "research/g9/cuda_qualification/stage2_cuda_core_stream_engine.py",
    "research/g9/cuda_qualification/stage2_cuda_input_frame.py",
    "research/g9/cuda_qualification/stage2_cuda_core_bridge.cu",
    "research/g9/cuda_qualification/stage2_cuda_core_bridge.py",
    "research/g9/cuda_qualification/stage2_cuda_core_qualification.py",
    "research/g9/cuda_qualification/stage2_cuda_execution_contract.py",
    "research/g9/run_stage2_cuda_core_qualification.py",
)
AMENDMENT_SHA256 = "589fdc29d71cd5f70c0734e927d109dc00b389b40cc7c485e56a655f41fd57cf"
APPROVAL_SHA256 = "a2b0747a5db2721f046420c120848e6bb4ea82505b2f5a16c4f8da64671377d4"
# The named release record is staged as PENDING. The CLI handoff must be the
# exact hash of its eventual owner-approved bytes, including the reviewed
# SOURCE_RELS map. A pending status refuses before nvcc even with env toggles.
EXECUTION_RELEASE_REL: str | None = "research/decisions/GATE_9_CUDA_CORE_DRY_RUN_RELEASE.json"
RELEASE_SCHEMA = "decisions_os/g9_cuda_core_dry_run_release/v1"
PLAN_SCHEMA = "decisions_os/g9_cuda_core_qualification_plan/v1"
RECEIPT_SCHEMA = "decisions_os/g9_cuda_core_dry_run_receipt/v1"
COMPILE_FLAGS = (
    "-std=c++17", "-O0", *core.CUDA_COMPILE_FLAGS,
    "-Xcompiler", "-O0,-ffp-contract=off,-fno-fast-math,-fPIC",
)
ABI_COMPILE_FLAGS = (*COMPILE_FLAGS, "-shared")

PLATFORM_PROBE = r'''#include <cuda_runtime.h>
#include <cstdio>
int main() {
  int count = 0, driver = 0, runtime = 0;
  if (cudaGetDeviceCount(&count) != cudaSuccess || count < 1) return 1;
  cudaDeviceProp p{};
  if (cudaGetDeviceProperties(&p, 0) != cudaSuccess || p.major < 1) return 1;
  if (cudaDriverGetVersion(&driver) != cudaSuccess) return 1;
  if (cudaRuntimeGetVersion(&runtime) != cudaSuccess) return 1;
  std::printf("{\"gpu_name\":\"%s\",\"compute_capability\":\"%d.%d\","
              "\"cuda_driver_version\":\"%d\",\"cuda_runtime_version\":\"%d\"}\n",
              p.name, p.major, p.minor, driver, runtime);
  return 0;
}
'''


class CoreQualificationError(RuntimeError):
    """The qualification path is not released or failed closed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CoreQualificationError(message)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(text: str, label: str) -> dict[str, object]:
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CoreQualificationError(f"{label} emitted invalid JSON") from exc
    _require(type(value) is dict, f"{label} did not emit an object")
    return value


def _authorities() -> dict[str, str]:
    _require(_sha(ROOT / AMENDMENT_REL) == AMENDMENT_SHA256, "CUDA amendment hash drift")
    _require(_sha(ROOT / APPROVAL_REL) == APPROVAL_SHA256, "CUDA approval hash drift")
    return {AMENDMENT_REL: AMENDMENT_SHA256, APPROVAL_REL: APPROVAL_SHA256}


def _source_hashes() -> dict[str, str]:
    return {relative: _sha(ROOT / relative) for relative in SOURCE_RELS}


def build_plan() -> dict[str, object]:
    """Read-only plan; does not query nvcc, a GPU, or any Stage-2 input."""
    body: dict[str, object] = {
        "schema": PLAN_SCHEMA,
        "mode": "plan",
        "scientific_outputs": "intentionally absent",
        "stage2_inputs": "intentionally absent",
        "execution_release": "separate_owner_release_required",
        "authorities": _authorities(),
        "source_sha256": _source_hashes(),
        "platform_probe_sha256": hashlib.sha256(PLATFORM_PROBE.encode("ascii")).hexdigest(),
        "compile_flags": list(COMPILE_FLAGS),
        "abi_compile_flags": list(ABI_COMPILE_FLAGS),
    }
    body["content_sha256"] = contract.content_sha256(body)
    return body


def _released(reviewed: object) -> tuple[str, dict[str, str]]:
    # These checks precede shutil.which, temporary directories, compilation,
    # GPU queries, imports of NumPy, and any scientific code path.
    _require(os.environ.get("PYTHONDONTWRITEBYTECODE") == "1",
             "PYTHONDONTWRITEBYTECODE=1 is required")
    _require(type(reviewed) is str and len(reviewed) == 64 and
             all(character in "0123456789abcdef" for character in reviewed),
             "reviewed handoff must be the approved release SHA-256")
    _require(EXECUTION_RELEASE_REL is not None,
             "separate owner CUDA qualification release is not pinned")
    _require(os.environ.get("G9_ALLOW_NONSCIENTIFIC_CUDA_QUALIFICATION") == "1",
             "separate CUDA qualification permission is required")
    release_path = ROOT / EXECUTION_RELEASE_REL
    try:
        release_bytes = release_path.read_bytes()
    except OSError as exc:
        raise CoreQualificationError("owner CUDA qualification release is unavailable") from exc
    _require(hashlib.sha256(release_bytes).hexdigest() == reviewed,
             "CUDA qualification release hash differs from the owner-approved handoff")
    try:
        release = json.loads(release_bytes)
    except json.JSONDecodeError as exc:
        raise CoreQualificationError("owner CUDA qualification release is not JSON") from exc
    _require(release_bytes == contract.canonical_bytes(release) + b"\n",
             "owner CUDA qualification release is not canonical JSON with one final LF")
    _require(type(release) is dict and set(release) ==
             {"schema", "status", "source_sha256", "authorities"} and
             release["schema"] == RELEASE_SCHEMA and release["status"] == "approved",
             "owner CUDA qualification release has invalid fields")
    live_sources = _source_hashes()
    _require(release["source_sha256"] == live_sources,
             "live CUDA source bytes differ from the reviewed release map")
    _require(release["authorities"] == _authorities(),
             "owner release does not pin the approved CUDA amendment")
    return reviewed, live_sources


def _run(command: list[str], label: str, *, timeout: int) -> subprocess.CompletedProcess[str]:
    try:
        outcome = subprocess.run(command, cwd=ROOT, text=True, capture_output=True,
                                 check=False, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CoreQualificationError(f"{label} failed or timed out") from exc
    _require(outcome.returncode == 0, f"{label} returned nonzero status")
    return outcome


def _require_exact_core_result(actual: dict[str, object], expected: dict[str, object]) -> None:
    _require(set(actual) == set(expected) and actual["lift_total"] == expected["lift_total"] and
             actual["record_count"] == expected["record_count"] and
             set(actual["summaries"]) == set(expected["summaries"]),
             "CUDA ABI result shape differs from Python")
    for key, observed in actual["summaries"].items():
        wanted = expected["summaries"][key]
        _require(set(observed) == set(wanted), "CUDA ABI summary fields differ from Python")
        for field, value in observed.items():
            if field == "minimum":
                _require(struct.pack("<d", value) == struct.pack("<d", wanted[field]),
                         "CUDA ABI minimum word differs from Python")
            else:
                _require(value == wanted[field], f"CUDA ABI {field} differs from Python")


def _bounded_summary_digest(raw: dict[str, object]) -> str:
    """Commit the synthetic compared result without carrying tie indices in the receipt."""
    streams = []
    for slot in range(raw["record_count"]):
        for encoding in core.ENCODINGS:
            summary = raw["summaries"][(slot, encoding)]
            bound = {field + "_hex" if field == "minimum" else field:
                     value.hex() if field == "minimum" else list(value) if type(value) is tuple else value
                     for field, value in summary.items()}
            streams.append({"slot": slot, "encoding": encoding, "summary": bound})
    body = {"schema": "decisions_os/g9_cuda_core_bounded_comparison/v1",
            "lift_total": raw["lift_total"], "record_count": raw["record_count"],
            "streams": streams}
    return hashlib.sha256(contract.canonical_bytes(body)).hexdigest()


def run_qualification(reviewed: str) -> dict[str, object]:
    """Future synthetic GPU self-test; unreachable until a pinned owner release."""
    release_sha, reviewed_sources = _released(reviewed)
    before = _source_hashes()
    _require(before == reviewed_sources, "source changed after release validation")
    nvcc = shutil.which("nvcc")
    _require(nvcc is not None, "nvcc is unavailable")
    image = os.environ.get("G9_KAGGLE_IMAGE_BUILD", "")
    _require(image and not any(char.isspace() for char in image),
             "a nonempty Kaggle image/build identity is required")
    nvcc_version = _run([nvcc, "--version"], "nvcc version", timeout=30).stdout.strip()
    _require(nvcc_version, "nvcc version output is empty")
    with tempfile.TemporaryDirectory(prefix="g9-core-qualification-") as temporary:
        directory = Path(temporary)
        core_binary = directory / "core_self_test"
        abi_binary = directory / "libg9_core_cuda.so"
        probe_source = directory / "platform_probe.cu"
        probe_binary = directory / "platform_probe"
        probe_source.write_text(PLATFORM_PROBE, encoding="ascii")
        _run([nvcc, *COMPILE_FLAGS, str(probe_source), "-o", str(probe_binary)],
             "platform-probe compilation", timeout=180)
        _run([nvcc, *COMPILE_FLAGS, str(ROOT / CUDA_SOURCE_REL), "-o", str(core_binary)],
             "core compilation", timeout=300)
        _run([nvcc, *ABI_COMPILE_FLAGS,
              str(ROOT / "research/g9/cuda_qualification/stage2_cuda_core_bridge.cu"),
              "-o", str(abi_binary)], "core ABI compilation", timeout=300)
        probe = _json(_run([str(probe_binary)], "platform probe", timeout=60).stdout,
                      "platform probe")
        raw = _json(_run([str(core_binary), "--self-test"], "core self-test", timeout=300).stdout,
                    "core self-test")
        _require(sys.byteorder == "little", "slack offsets require a little-endian host")
        first_payload = core.synthetic_payload()
        second_payload = core.synthetic_payload()
        second_payload["sectors"] = core.ALTERNATE_MEMBERSHIP
        second_payload["lambda_ref"] = core.ALTERNATE_LAMBDA_REF
        second_payload["b"] = 45.0
        cases = (
            (first_payload, [core.coefficient_row("row0")]),
            (second_payload, [core.coefficient_row("row1"), core.coefficient_row("row0")]),
        )
        abi_validations = []
        for payload, rows in cases:
            domain = core.build_domain(payload)
            offsets_sha = hashlib.sha256(domain["offsets"].tobytes()).hexdigest()
            frame = input_frame.build_input_frame(payload, rows, offsets_sha)
            try:
                bound = bridge._run_compiled_frame(frame, abi_binary, require_backend=1)
            except bridge.CoreBridgeError as exc:
                raise CoreQualificationError("CUDA ABI input/offset binding failed") from exc
            _require(bound["input_frame_sha256"] == frame["content_sha256"] and
                     bound["offsets_sha256"] == offsets_sha,
                     "CUDA ABI returned an unbound input or offset identity")
            decoded_payload, decoded_rows = input_frame.decoded_inputs(frame)
            _require_exact_core_result(bound["core_result"],
                                       core.run_core(decoded_payload, decoded_rows))
            abi_validations.append({"status": "pass", "input_frame_sha256": frame["content_sha256"],
                                    "offsets_sha256": offsets_sha, "row_count": len(rows),
                                    "bounded_summary_sha256": _bounded_summary_digest(bound["core_result"])})
        _require(abi_validations[0]["offsets_sha256"] != abi_validations[1]["offsets_sha256"],
                 "the alternate payload did not change the computed offset table")
    _require(before == _source_hashes(), "source changed during CUDA qualification")
    _require(set(probe) == {"gpu_name", "compute_capability", "cuda_driver_version",
                            "cuda_runtime_version"} and
             all(type(value) is str and value for value in probe.values()),
             "platform probe fields are malformed")
    _require(probe["gpu_name"] == raw.get("device_name") and raw.get("device_index") == 0,
             "platform probe and core selected different GPUs")
    try:
        verified = core.validate_self_test_report(raw)
    except core.CoreStreamEngineError as exc:
        raise CoreQualificationError("CUDA core disagrees with the Python reference") from exc
    import numpy as np  # Deferred until after the execution-release guard.
    platform_fields = dict(probe)
    platform_fields.update({"nvcc_version": nvcc_version, "kaggle_image": image,
                            "python_version": platform.python_version(),
                            "numpy_version": np.__version__})
    sources = dict(before)
    sources["platform_probe_literal"] = hashlib.sha256(PLATFORM_PROBE.encode("ascii")).hexdigest()
    # Check that the observed fields could form a future qualification
    # identity, but do not emit that identity: amendment A is not satisfied by
    # this dry run and its receipt must not be usable as a production plan pin.
    contract.qualification_identity(platform_fields, sources, ABI_COMPILE_FLAGS)
    receipt: dict[str, object] = {
        "schema": RECEIPT_SCHEMA,
        "mode": "non_scientific_dry_run",
        "amendment_A_status": "not_satisfied_corrupted_kernel_tests_pending",
        "scientific_outputs": "intentionally absent",
        "kaggle_image_origin": "operator_asserted",
        "authorities": _authorities(),
        "execution_release_sha256": release_sha,
        "platform_fingerprint": platform_fields,
        "source_sha256": sources,
        "abi_validations": abi_validations,
        "self_test_compile_flags": list(COMPILE_FLAGS),
        "abi_compile_flags": list(ABI_COMPILE_FLAGS),
        "self_test_report": verified,
    }
    receipt["content_sha256"] = contract.content_sha256(receipt)
    return receipt

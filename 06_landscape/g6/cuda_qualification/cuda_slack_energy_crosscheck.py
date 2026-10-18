"""Bounded CUDA-vs-CPU bit-exact cross-check of the slack energy transcript on an NVIDIA T4.

Second step of the non-production Gate-6 **CUDA/T4** qualification track,
after the unbalanced cross-check.  It reuses, by pinned import:

* the reviewed HIP slack prototype (``slack_energy_crosscheck.py``) for the
  raw 20-bit state set (1710 masks), the four reviewed coefficient points,
  the exact-lift attachment (auxiliary registers come **only** from
  ``src.g4.energy.exact_slack_lift``; raw states without an exact lift are
  excluded and counted by register, never clamped, substituted, searched,
  or optimised), the input/output word encodings, and the comparator;
* the CUDA unbalanced prototype (``cuda_energy_crosscheck.py``) for the nvcc
  compile contract, nvcc/T4 identity capture, device-report validation, and
  the qualification-identity hash.

It evaluates canonical ``src.g4.energy.slack_energy`` on the CPU, the
transcribed CUDA kernel on a Tesla T4 (compute capability 7.5, ``sm_75``),
and reports mismatch counts plus environment identity only.  The lifted and
excluded counts are derived from the canonical lift at run time, never
assumed.

It is not a Gate-6 pass.  It never reads the Gate-5 corpus, never enumerates
a slack domain, never computes a minimum, tie set, X_E, label, rate,
aggregate, transition, D013 trigger, V-14 value, batch, or conclusion, never
writes a result artifact, never installs anything, and never treats GPU
output as a scientific value.  A pass of the earlier unbalanced cross-check
is a prerequisite, not a substitute.

Importing this module has no side effects and writes nothing.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, Callable, Mapping

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.g6.cuda_qualification import cuda_energy_crosscheck as cuda_unbalanced  # noqa: E402
from research.g6.gpu_qualification import energy_crosscheck as hip_unbalanced  # noqa: E402
from research.g6.gpu_qualification import slack_energy_crosscheck as hip_slack  # noqa: E402
from src.g4.instance import Instance, load_instance  # noqa: E402


SCHEMA_PLAN = "decisions_os/g6_cuda_t4_slack_energy_crosscheck_plan/v1"
SCHEMA_RUN = "decisions_os/g6_cuda_t4_slack_energy_crosscheck_run/v1"
PURPOSE = (
    "non-production CUDA-vs-CPU bit-exact cross-check of the slack energy transcript "
    "at the exact-minimizer lift on an NVIDIA T4; GPU output cannot contribute to a Gate-6 artifact"
)
TRACK = "cuda-t4"
ENCODING = hip_slack.ENCODING
REFERENCE = hip_slack.REFERENCE
LIFT_SOURCE = hip_slack.LIFT_SOURCE
PROBE = "slack_energy_transcript_crosscheck_cuda"
BACKEND = cuda_unbalanced.BACKEND
TARGET_GPU_NAME = cuda_unbalanced.TARGET_GPU_NAME
TARGET_COMPUTE_CAPABILITY = cuda_unbalanced.TARGET_COMPUTE_CAPABILITY
TARGET_ARCHITECTURE = cuda_unbalanced.TARGET_ARCHITECTURE
COMPILE_FLAGS = cuda_unbalanced.COMPILE_FLAGS
# Owner-reported identity of the passed unbalanced CUDA/T4 qualification this
# step follows.  Declared prerequisite only; this module cannot verify it and
# it is not part of the slack identity hash.
DECLARED_PREREQUISITE_UNBALANCED_IDENTITY_SHA256 = (
    "5c7841a35fa81621bd5b41619afeb78529df3f8a8f3d27e8acd4cb26b524c224"
)

CUDA_SOURCE_REL = "research/g6/cuda_qualification/cuda_slack_energy_crosscheck.cu"
CUDA_UNBALANCED_LIBRARY_REL = "research/g6/cuda_qualification/cuda_energy_crosscheck.py"
CUDA_UNBALANCED_SOURCE_REL = cuda_unbalanced.CUDA_SOURCE_REL
HIP_UNBALANCED_LIBRARY_REL = hip_slack.UNBALANCED_LIBRARY_REL
HIP_SLACK_LIBRARY_REL = "research/g6/gpu_qualification/slack_energy_crosscheck.py"
INSTANCE_REL = hip_slack.INSTANCE_REL
MANIFEST_REL = hip_slack.MANIFEST_REL
D011_LEDGER_REL = hip_slack.D011_LEDGER_REL
V14_2X_LEDGER_REL = hip_slack.V14_2X_LEDGER_REL

# Exact inputs this prototype consumes.  Shared entries must equal the HIP
# slack and CUDA unbalanced pins (checked by the fixtures).  The qualified
# unbalanced CUDA program is pinned because the slack program's non-transcript
# scaffolding (device selection, launch, I/O, identity report) is taken from it.
PINNED_INPUTS: dict[str, str] = {
    "src/g4/energy.py": "0ba83c0d33e0d2996352370e26bf0e782002ec49cb79e1628b74a2a74dd5fa11",
    "src/g4/instance.py": "645419374fd30891c2f9ff14d030ed65a032d52d8fe88fab068ad23417b58187",
    "src/g4/parameters.py": "cbbdebbe44b9af0d47fa1d5da7e00303e492d70d21abd696e6bdd5a4cd5be97c",
    "src/g6/ledgers.py": "40ff906fdedb526f7063c7d40aeb778335cf49291a47a948d9f5b31620fc0723",
    INSTANCE_REL: "c4615d9b5066597c4754a1e06d2b3a7906c218965a7d6d530cf54f75c4b5f243",
    MANIFEST_REL: "900b639509074114b4be1149dfaef7d14b6e4ba4a7c1fbcf90d719057a0611ca",
    D011_LEDGER_REL: "00091b631dc92f4a923badf4dd2abda0efc9d82a533f8c61926aa88c521fc06e",
    V14_2X_LEDGER_REL: "3bd7341a7dcf8ca5de007cf2d92ab89e64e95b887349df8e7dede0cc5b0ec3ea",
    HIP_UNBALANCED_LIBRARY_REL: "6ceb20042f184ff1d7652024589490d1ccb339930b0be0ecf6a01b30d275f775",
    HIP_SLACK_LIBRARY_REL: "bdc59777e7808ccc9822bf22047514775f3cb1803ce911911e02178322586f1c",
    CUDA_UNBALANCED_LIBRARY_REL: "cf826736cf2c1dafca03b0d2e8c31cf6d9ed5a86eee961bc84345669698dc2f1",
    CUDA_UNBALANCED_SOURCE_REL: "006421acc9bb61b92df3a45189c734977f6459b092909a821e6e52855a357e1c",
    CUDA_SOURCE_REL: "9661374be597dfd17f9eb2a983124c0e9d44ccd70e1ff48a11f3036736a4af54",
}
SELF_RELATIVES = (
    "research/g6/cuda_qualification/cuda_slack_energy_crosscheck.py",
    "research/g6/run_cuda_slack_energy_crosscheck.py",
)
COMPILE_TIMEOUT_SECONDS = cuda_unbalanced.COMPILE_TIMEOUT_SECONDS
EXECUTE_TIMEOUT_SECONDS = cuda_unbalanced.EXECUTE_TIMEOUT_SECONDS


class CrosscheckError(RuntimeError):
    """Raised when the bounded cross-check contract cannot be established."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CrosscheckError(message)


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _shared(function: Callable, *arguments):
    """Call a shared prototype helper, converting either prototype's failure type to ours."""
    try:
        return function(*arguments)
    except (hip_slack.CrosscheckError, hip_unbalanced.CrosscheckError, cuda_unbalanced.CrosscheckError) as exc:
        raise CrosscheckError(str(exc)) from exc


def current_hashes(relatives: tuple[str, ...] | list[str]) -> dict[str, str]:
    return _shared(hip_unbalanced.current_hashes, relatives)


def verify_pinned_inputs(expected: Mapping[str, str] | None = None) -> dict[str, str]:
    """Hash every consumed input and fail closed on any drift from the pins."""
    pins = dict(PINNED_INPUTS if expected is None else expected)
    observed = current_hashes(tuple(pins))
    drifted = sorted(relative for relative in pins if observed[relative] != pins[relative])
    _require(not drifted, "pinned input drift: " + ", ".join(drifted))
    return observed


def load_ledgers() -> dict[str, dict[str, Any]]:
    return _shared(hip_slack.load_ledgers)


def coefficient_points(ledgers: Mapping[str, Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    return _shared(hip_slack.coefficient_points, ledgers)


def declared_states(instance: Instance) -> tuple[tuple[int, ...], dict[str, int]]:
    return _shared(hip_slack.declared_states, instance)


def lift_states(instance: Instance, states: tuple[int, ...]):
    """Attach the canonical exact lift; the lifted/excluded partition is derived here, not assumed."""
    return _shared(hip_slack.lift_states, instance, states)


def encode_inputs(instance: Instance, points, lifted) -> bytes:
    return _shared(hip_slack.encode_inputs, instance, points, lifted)


def decode_output(payload: bytes, point_count: int, state_count: int):
    return _shared(hip_slack.decode_output, payload, point_count, state_count)


def python_reference_bits(instance: Instance, points, lifted) -> tuple[int, ...]:
    return _shared(hip_slack.python_reference_bits, instance, points, lifted)


def compare_bits(reference, candidate, points, lifted, limit: int = 16) -> dict[str, Any]:
    return _shared(hip_slack.compare_bits, reference, candidate, points, lifted, limit)


def compile_command(nvcc: str, source: Path, binary: Path) -> list[str]:
    return _shared(cuda_unbalanced.compile_command, nvcc, source, binary)


def validate_device_report(report: object, point_count: int, state_count: int) -> dict[str, Any]:
    """T4/7.5/CUDA/nvcc validation from the unbalanced prototype plus this probe's name."""
    validated = _shared(cuda_unbalanced.validate_device_report, report, point_count, state_count)
    _require(validated.get("probe") == PROBE, "device report is not from the slack transcript program")
    return validated


def qualification_identity(report, nvcc_info, command, pins, lifted_sha256: str, states_sha256: str,
                           point_ids: list[str], evaluations: int) -> dict[str, Any]:
    """Slack-track identity: the unbalanced identity fields plus the lifted-pair digest."""
    identity = _shared(cuda_unbalanced.qualification_identity, report, nvcc_info, command, pins,
                       states_sha256, point_ids, evaluations)
    identity["encoding"] = ENCODING
    identity["reference"] = REFERENCE
    identity["lift_source"] = LIFT_SOURCE
    identity["lifted_pairs_sha256"] = lifted_sha256
    identity["cuda_source_sha256"] = pins[CUDA_SOURCE_REL]
    identity["probe"] = PROBE
    return identity


def identity_sha256(identity: Mapping[str, Any]) -> str:
    return cuda_unbalanced.identity_sha256(identity)


def _point_report(point: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in point.items() if key != "coefficients"}


def _bind():
    pins = verify_pinned_inputs()
    for other, label in ((hip_slack.PINNED_INPUTS, "HIP slack"), (cuda_unbalanced.PINNED_INPUTS, "CUDA unbalanced")):
        _require(all(other[key] == PINNED_INPUTS[key] for key in other if key in PINNED_INPUTS),
                 f"CUDA slack and {label} prototypes pin different shared inputs")
    ledgers = load_ledgers()
    points = coefficient_points(ledgers)
    instance = load_instance(ROOT / INSTANCE_REL)
    states, families = declared_states(instance)
    lifted, excluded = lift_states(instance, states)
    return instance, points, states, families, lifted, excluded, pins


def _lift_report(states, lifted, excluded) -> dict[str, Any]:
    report = hip_slack._lift_report(states, lifted, excluded)
    report["derived_at"] = "run time from src.g4.energy.exact_slack_lift; no constant is trusted"
    return report


def _state_report(states, families) -> dict[str, Any]:
    return {
        "count": len(states),
        "bit_order": hip_slack.BIT_ORDER,
        "families": families,
        "sha256_le_uint64_sequence": hip_unbalanced.states_digest(states),
        "shared_with": HIP_UNBALANCED_LIBRARY_REL,
    }


def build_plan() -> dict[str, Any]:
    """Validate every binding and describe the run without nvcc, GPU access, or writes."""
    instance, points, states, families, lifted, excluded, pins = _bind()
    return {
        "schema": SCHEMA_PLAN,
        "mode": "plan",
        "purpose": PURPOSE,
        "track": TRACK,
        "encoding": ENCODING,
        "reference": REFERENCE,
        "declared_prerequisite_unbalanced_identity_sha256": DECLARED_PREREQUISITE_UNBALANCED_IDENTITY_SHA256,
        "target": {"backend": BACKEND, "gpu_name": TARGET_GPU_NAME,
                   "compute_capability": "%d.%d" % TARGET_COMPUTE_CAPABILITY,
                   "architecture": TARGET_ARCHITECTURE},
        "device_selection": "explicit compute-capability 7.5 and T4-name match; device 0 is not assumed; "
                            "the runner requires the exact product name Tesla T4",
        "pinned_inputs": pins,
        "self_sha256": current_hashes(SELF_RELATIVES),
        "coefficient_points": [_point_report(point) for point in points],
        "raw_state_set": _state_report(states, families),
        "lift": _lift_report(states, lifted, excluded),
        "planned_evaluations": len(points) * len(lifted),
        "compile_flags": list(COMPILE_FLAGS),
        "compile_command_template": compile_command("nvcc", Path("<tmp>/source.cu"), Path("<tmp>/crosscheck")),
        "nvcc_located": cuda_unbalanced.locate_nvcc() is not None,
        "writes": "none",
        "scientific_outputs": "intentionally absent",
    }


def run_crosscheck(locate: Callable[[], str | None] = cuda_unbalanced.locate_nvcc) -> dict[str, Any]:
    """Compile and execute the CUDA slack cross-check in a temporary directory; counts and identity only.

    ``locate`` is injectable so hardware-free fixtures can prove the no-nvcc
    refusal without touching PATH or a real toolchain.
    """
    _require(os.environ.get("PYTHONDONTWRITEBYTECODE") == "1", "PYTHONDONTWRITEBYTECODE=1 is required")
    nvcc = locate()
    _require(nvcc is not None, "nvcc is unavailable; the CUDA slack cross-check cannot run on this host")
    instance, points, states, families, lifted, excluded, pins_before = _bind()
    self_before = current_hashes(SELF_RELATIVES)
    platform_before = cuda_unbalanced._platform_fingerprint()
    source = ROOT / CUDA_SOURCE_REL
    reference = python_reference_bits(instance, points, lifted)
    encoded = encode_inputs(instance, points, lifted)
    temporary_path: Path | None = None
    with tempfile.TemporaryDirectory(prefix="g6-cuda-t4-slack-energy-crosscheck-") as temporary:
        temporary_path = Path(temporary)
        nvcc_info = _shared(cuda_unbalanced.nvcc_version, nvcc, temporary_path)
        smi = _shared(cuda_unbalanced.nvidia_smi_identity, temporary_path)
        staged_source = temporary_path / "cuda_slack_energy_crosscheck.cu"
        binary = temporary_path / "crosscheck"
        input_path = temporary_path / "input.words"
        output_path = temporary_path / "output.words"
        staged_source.write_bytes(source.read_bytes())
        _require(_sha256_bytes(staged_source.read_bytes()) == PINNED_INPUTS[CUDA_SOURCE_REL],
                 "staged CUDA source does not match the pinned source")
        input_path.write_bytes(encoded)
        command = compile_command(nvcc, staged_source, binary)
        compilation = _shared(cuda_unbalanced._run_subprocess, command, temporary_path,
                              COMPILE_TIMEOUT_SECONDS, "nvcc compilation")
        _require(compilation.returncode == 0,
                 "nvcc compilation failed; do not substitute relaxed floating-point flags: "
                 + compilation.stderr[-2000:])
        execution = _shared(cuda_unbalanced._run_subprocess, [str(binary), str(input_path), str(output_path)],
                            temporary_path, EXECUTE_TIMEOUT_SECONDS, "CUDA execution")
        _require(execution.returncode == 0, "CUDA slack cross-check binary failed: " + execution.stderr[-2000:])
        try:
            device_report = json.loads(execution.stdout)
        except json.JSONDecodeError as exc:
            raise CrosscheckError("CUDA slack cross-check emitted malformed JSON") from exc
        validate_device_report(device_report, len(points), len(lifted))
        try:
            output_bytes = output_path.read_bytes()
        except OSError as exc:
            raise CrosscheckError("CUDA slack cross-check output file is unreadable") from exc
        device_index, device_bits, host_bits = decode_output(output_bytes, len(points), len(lifted))
        _require(device_index == device_report.get("device_index"), "device index disagreement")
    _require(temporary_path is not None and not temporary_path.exists(), "temporary directory was not removed")
    gpu = compare_bits(reference, device_bits, points, lifted)
    host = compare_bits(reference, host_bits, points, lifted)
    pins_after = verify_pinned_inputs()
    _require(pins_after == pins_before, "pinned input drift during the cross-check")
    _require(current_hashes(SELF_RELATIVES) == self_before, "prototype source drift during the cross-check")
    _require(cuda_unbalanced._platform_fingerprint() == platform_before,
             "platform fingerprint drift during the cross-check")
    identity = qualification_identity(device_report, nvcc_info, command, pins_before,
                                      hip_slack.lifted_digest(lifted), hip_unbalanced.states_digest(states),
                                      [point["point_id"] for point in points], len(reference))
    verdict = "pass" if gpu["mismatches"] == 0 and host["mismatches"] == 0 else "fail"
    return {
        "schema": SCHEMA_RUN,
        "mode": "run",
        "purpose": PURPOSE,
        "track": TRACK,
        "encoding": ENCODING,
        "reference": REFERENCE,
        "declared_prerequisite_unbalanced_identity_sha256": DECLARED_PREREQUISITE_UNBALANCED_IDENTITY_SHA256,
        "platform": platform_before,
        "pinned_inputs": pins_before,
        "pinned_inputs_after_run": pins_after,
        "self_sha256": self_before,
        "coefficient_points": [_point_report(point) for point in points],
        "raw_state_set": _state_report(states, families),
        "lift": _lift_report(states, lifted, excluded),
        "compile_command": command,
        "nvcc": nvcc_info,
        "nvidia_smi": smi,
        "device": cuda_unbalanced.device_fingerprint(device_report),
        "device_reported": device_report,
        "qualification_identity": identity,
        "qualification_identity_sha256": identity_sha256(identity),
        "gpu_vs_python": gpu,
        "host_cxx_vs_python": host,
        "temporary_directory_removed": True,
        "verdict": verdict,
        "writes": "none",
        "scientific_outputs": "intentionally absent",
    }

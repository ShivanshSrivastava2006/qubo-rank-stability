"""Bounded CUDA-vs-CPU bit-exact cross-check of the unbalanced energy transcript on an NVIDIA T4.

This module is the non-production Gate-6 **CUDA/T4** qualification prototype.
It is a separate track from the RX 9070 / ROCm (HIP, ``gfx1201``) track and
never mixes with it.  It reuses, by import, the reviewed HIP prototype's
finite raw 20-bit state set, four reviewed coefficient points, input/output
word encodings, and comparator (``energy_crosscheck.py`` is a pinned consumed
input); it evaluates the canonical Python ``src.g4.energy.unbalanced_energy``
on the CPU, evaluates the transcribed CUDA kernel on an NVIDIA T4 (compute
capability 7.5, ``sm_75``), and reports mismatch counts plus environment
identity only.

Environment identity recorded by ``--run``: full nvcc compile command, nvcc
version (from ``nvcc --version`` and from the compiled program's
``__CUDACC_VER_*`` macros, which must agree), CUDA runtime and driver
versions, GPU name, compute capability, and a device fingerprint (UUID, PCI
location, memory, SM count).  Any GPU that is not exactly a ``Tesla T4`` at
capability 7.5 is rejected.

It is not a Gate-6 pass.  It never reads the Gate-5 core-pass output
directory or any Gate-5 shard, never computes a minimum, tie set, X_E, label,
rate, aggregate, transition, D013 trigger, or conclusion, never writes a
Gate-5 or Gate-6 result artifact, never installs anything, and never treats
GPU output as a scientific value.  The ``qualification_identity`` it emits is
the only thing a future V-14 CUDA batch plan may bind.

Importing this module has no side effects and writes nothing.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.g6.gpu_qualification import energy_crosscheck as shared  # noqa: E402
from src.g4.instance import Instance, load_instance  # noqa: E402


SCHEMA_PLAN = "decisions_os/g6_cuda_t4_unbalanced_energy_crosscheck_plan/v1"
SCHEMA_RUN = "decisions_os/g6_cuda_t4_unbalanced_energy_crosscheck_run/v1"
PURPOSE = (
    "non-production CUDA-vs-CPU bit-exact cross-check of the unbalanced energy "
    "transcript on an NVIDIA T4; GPU output cannot contribute to a Gate-6 artifact"
)
BACKEND = "cuda-runtime"
TARGET_GPU_NAME = "Tesla T4"
TARGET_GPU_NAME_PATTERN = re.compile(r"(NVIDIA )?Tesla T4")
TARGET_COMPUTE_CAPABILITY = (7, 5)
TARGET_ARCHITECTURE = "sm_75"
ENCODING = shared.ENCODING
REFERENCE = shared.REFERENCE
# Any of these in a device name or backend string marks the wrong track
# (ROCm/HIP/RX 9070), an emulation stub, or an unknown vendor.
FORBIDDEN_PLATFORM_TOKENS = ("gfx", "rocm", "hip", "radeon", "rx 9070", "amd", "emulation", "stub")

CUDA_SOURCE_REL = "research/g6/cuda_qualification/cuda_unbalanced_energy_crosscheck.cu"
SHARED_LIBRARY_REL = "research/g6/gpu_qualification/energy_crosscheck.py"
INSTANCE_REL = shared.INSTANCE_REL
MANIFEST_REL = shared.MANIFEST_REL
D011_LEDGER_REL = shared.D011_LEDGER_REL
V14_2X_LEDGER_REL = shared.V14_2X_LEDGER_REL

# Exact inputs this prototype consumes.  The shared entries must equal the
# HIP prototype's pins (checked by the fixtures) so both tracks bind the same
# canonical evaluator, instance, ledgers, and state set.
PINNED_INPUTS: dict[str, str] = {
    "src/g4/energy.py": "0ba83c0d33e0d2996352370e26bf0e782002ec49cb79e1628b74a2a74dd5fa11",
    "src/g4/instance.py": "645419374fd30891c2f9ff14d030ed65a032d52d8fe88fab068ad23417b58187",
    "src/g4/parameters.py": "cbbdebbe44b9af0d47fa1d5da7e00303e492d70d21abd696e6bdd5a4cd5be97c",
    "src/g6/ledgers.py": "40ff906fdedb526f7063c7d40aeb778335cf49291a47a948d9f5b31620fc0723",
    INSTANCE_REL: "c4615d9b5066597c4754a1e06d2b3a7906c218965a7d6d530cf54f75c4b5f243",
    MANIFEST_REL: "900b639509074114b4be1149dfaef7d14b6e4ba4a7c1fbcf90d719057a0611ca",
    D011_LEDGER_REL: "00091b631dc92f4a923badf4dd2abda0efc9d82a533f8c61926aa88c521fc06e",
    V14_2X_LEDGER_REL: "3bd7341a7dcf8ca5de007cf2d92ab89e64e95b887349df8e7dede0cc5b0ec3ea",
    SHARED_LIBRARY_REL: "6ceb20042f184ff1d7652024589490d1ccb339930b0be0ecf6a01b30d275f775",
    CUDA_SOURCE_REL: "006421acc9bb61b92df3a45189c734977f6459b092909a821e6e52855a357e1c",
}
# Files whose hashes are recorded and drift-checked within a run, but which
# cannot pin themselves.
SELF_RELATIVES = (
    "research/g6/cuda_qualification/cuda_energy_crosscheck.py",
    "research/g6/run_cuda_energy_crosscheck.py",
)

# nvcc compile contract.  Device code: sm_75 SASS only (no PTX JIT onto
# another capability), no FMA contraction, no flush-to-zero, IEEE division
# and square root, ptxas at -O0.  Host code: -O0, no contraction, no
# fast-math.  The runner refuses to substitute relaxed flags.
COMPILE_FLAGS = (
    "-std=c++17",
    "-O0",
    "-gencode", "arch=compute_75,code=sm_75",
    "--fmad=false",
    "--ftz=false",
    "--prec-div=true",
    "--prec-sqrt=true",
    "-Xptxas", "-O0",
    "-Xcompiler", "-O0",
    "-Xcompiler", "-ffp-contract=off",
    "-Xcompiler", "-fno-fast-math",
)
FORBIDDEN_COMPILE_TOKENS = ("--use_fast_math", "-use_fast_math", "--fmad=true", "-fmad=true",
                            "--ftz=true", "-ftz=true", "--prec-div=false", "--prec-sqrt=false",
                            "-ffast-math", "-Ofast")
COMPILE_TIMEOUT_SECONDS = 900
EXECUTE_TIMEOUT_SECONDS = 600
TOOL_TIMEOUT_SECONDS = 60
NVCC_RELEASE_PATTERN = re.compile(r"release\s+(\d+)\.(\d+),\s*V(\d+)\.(\d+)\.(\d+)")


class CrosscheckError(RuntimeError):
    """Raised when the bounded cross-check contract cannot be established."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CrosscheckError(message)


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _shared(function, *arguments):
    """Call a shared HIP-prototype helper, converting its failure type to ours."""
    try:
        return function(*arguments)
    except shared.CrosscheckError as exc:
        raise CrosscheckError(str(exc)) from exc


def current_hashes(relatives: tuple[str, ...] | list[str]) -> dict[str, str]:
    return _shared(shared.current_hashes, relatives)


def verify_pinned_inputs(expected: Mapping[str, str] | None = None) -> dict[str, str]:
    """Hash every consumed input and fail closed on any drift from the pins."""
    pins = dict(PINNED_INPUTS if expected is None else expected)
    observed = current_hashes(tuple(pins))
    drifted = sorted(relative for relative in pins if observed[relative] != pins[relative])
    _require(not drifted, "pinned input drift: " + ", ".join(drifted))
    return observed


def load_ledgers() -> dict[str, dict[str, Any]]:
    return _shared(shared.load_ledgers)


def coefficient_points(ledgers: Mapping[str, Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    return _shared(shared.coefficient_points, ledgers)


def declared_states(instance: Instance) -> tuple[tuple[int, ...], dict[str, int]]:
    return _shared(shared.declared_states, instance)


def encode_inputs(instance: Instance, points: tuple[Mapping[str, Any], ...], states: tuple[int, ...]) -> bytes:
    return _shared(shared.encode_inputs, instance, points, states)


def decode_output(payload: bytes, point_count: int, state_count: int):
    return _shared(shared.decode_output, payload, point_count, state_count)


def python_reference_bits(instance: Instance, points: tuple[Mapping[str, Any], ...],
                          states: tuple[int, ...]) -> tuple[int, ...]:
    return _shared(shared.python_reference_bits, instance, points, states)


def compare_bits(reference: tuple[int, ...], candidate: tuple[int, ...],
                 points: tuple[Mapping[str, Any], ...], states: tuple[int, ...],
                 limit: int = 16) -> dict[str, Any]:
    return _shared(shared.compare_bits, reference, candidate, points, states, limit)


def locate_nvcc() -> str | None:
    candidate = Path("/usr/local/cuda/bin/nvcc")
    return shutil.which("nvcc") or (str(candidate) if candidate.is_file() else None)


def compile_command(nvcc: str, source: Path, binary: Path) -> list[str]:
    command = [nvcc, *COMPILE_FLAGS, str(source), "-o", str(binary)]
    _require(not any(token in command for token in FORBIDDEN_COMPILE_TOKENS),
             "compile contract contains a forbidden relaxed flag")
    _require(command[1:1 + len(COMPILE_FLAGS)] == list(COMPILE_FLAGS), "compile contract flags are incomplete")
    return command


def _run_subprocess(command: list[str], cwd: Path, timeout: int, label: str) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        return subprocess.run(command, cwd=cwd, env=environment, text=True, capture_output=True,
                              check=False, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CrosscheckError(f"{label} did not complete: {type(exc).__name__}") from exc


def nvcc_version(nvcc: str, cwd: Path) -> dict[str, Any]:
    """Record ``nvcc --version`` and parse its release/build; fail closed if unparsable."""
    result = _run_subprocess([nvcc, "--version"], cwd, TOOL_TIMEOUT_SECONDS, "nvcc --version")
    _require(result.returncode == 0, "nvcc --version failed")
    matched = NVCC_RELEASE_PATTERN.search(result.stdout)
    _require(matched is not None, "nvcc --version output is unrecognised")
    return {
        "path": nvcc,
        "release": f"{matched.group(1)}.{matched.group(2)}",
        "build": f"{matched.group(3)}.{matched.group(4)}.{matched.group(5)}",
        "stdout": result.stdout[:4000],
    }


def nvidia_smi_identity(cwd: Path) -> dict[str, Any]:
    """Optional corroborating evidence; absence is recorded, never fatal."""
    executable = shutil.which("nvidia-smi")
    if executable is None:
        return {"found": False}
    result = _run_subprocess([executable, "--query-gpu=name,driver_version,uuid,pci.bus_id",
                              "--format=csv,noheader"], cwd, TOOL_TIMEOUT_SECONDS, "nvidia-smi")
    return {"found": True, "returncode": result.returncode, "stdout": result.stdout[:4000]}


def _platform_fingerprint() -> dict[str, Any]:
    return {
        "python": sys.version,
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "colab_release_tag": os.environ.get("COLAB_RELEASE_TAG", "<unset>"),
        "python_dont_write_bytecode": os.environ.get("PYTHONDONTWRITEBYTECODE", "<unset>"),
    }


def _forbidden_token(text: object) -> bool:
    lowered = str(text).lower()
    return any(token in lowered for token in FORBIDDEN_PLATFORM_TOKENS)


def validate_device_report(report: object, point_count: int, state_count: int) -> dict[str, Any]:
    """Fail closed unless the program ran on exactly a Tesla T4 at capability 7.5 under nvcc."""
    _require(isinstance(report, dict), "device report is not an object")
    name = report.get("device_name")
    _require(isinstance(name, str) and TARGET_GPU_NAME_PATTERN.fullmatch(name) is not None,
             f"device is not an NVIDIA {TARGET_GPU_NAME}: {name!r}")
    _require(report.get("backend") == BACKEND, "program was not compiled by nvcc against the CUDA runtime")
    _require(not _forbidden_token(name) and not _forbidden_token(report.get("backend")),
             "device report names a non-CUDA/T4 platform")
    _require(report.get("compute_capability") == "%d.%d" % TARGET_COMPUTE_CAPABILITY
             and report.get("architecture") == TARGET_ARCHITECTURE,
             "device is not compute capability 7.5 / sm_75")
    for key in ("cuda_driver_version", "cuda_runtime_version"):
        _require(isinstance(report.get(key), int) and report[key] > 0, f"{key} is missing or zero")
    _require(isinstance(report.get("nvcc_version"), str) and report["nvcc_version"] != "0.0.0",
             "compiled program does not carry an nvcc version")
    uuid = report.get("device_uuid_hex")
    _require(isinstance(uuid, str) and re.fullmatch(r"[0-9a-f]{32}", uuid) is not None
             and uuid != "0" * 32, "device UUID is missing")
    _require(isinstance(report.get("device_index"), int) and report["device_index"] >= 0, "device index missing")
    _require(report.get("point_count") == point_count and report.get("state_count") == state_count
             and report.get("evaluations") == point_count * state_count,
             "program reported unexpected counts")
    _require(report.get("scientific_outputs") == "intentionally absent", "program output boundary violated")
    return report


def device_fingerprint(report: Mapping[str, Any]) -> dict[str, Any]:
    """The physical device and session identity: differs between Colab sessions."""
    return {key: report.get(key) for key in (
        "device_name", "device_uuid_hex", "pci_domain_id", "pci_bus_id", "pci_device_id",
        "multiprocessor_count", "total_global_memory_bytes", "device_index", "device_count")}


def qualification_identity(report: Mapping[str, Any], nvcc_info: Mapping[str, Any],
                           command: list[str], pins: Mapping[str, str],
                           states_sha256: str, point_ids: list[str], evaluations: int) -> dict[str, Any]:
    """The platform/toolchain identity a future V-14 CUDA batch plan binds.

    Deliberately excludes the device UUID, PCI location, and session: every
    ~3.5 h batch runs in its own Colab session, so batches may run on
    different physical T4s but must share this exact identity.
    """
    _require(command[0] == nvcc_info["path"], "compile command does not name the recorded nvcc")
    _require(report["nvcc_version"] == nvcc_info["build"],
             f"nvcc --version build {nvcc_info['build']} differs from the compiled program's "
             f"__CUDACC_VER__ {report['nvcc_version']}")
    identity = {
        "backend": BACKEND,
        "gpu_name": report["device_name"],
        "compute_capability": report["compute_capability"],
        "architecture": report["architecture"],
        "cuda_driver_version": report["cuda_driver_version"],
        "cuda_runtime_version": report["cuda_runtime_version"],
        "nvcc_release": nvcc_info["release"],
        "nvcc_build": nvcc_info["build"],
        "compile_flags": list(COMPILE_FLAGS),
        "cuda_source_sha256": pins[CUDA_SOURCE_REL],
        "pinned_inputs": dict(pins),
        "state_set_sha256": states_sha256,
        "coefficient_point_ids": list(point_ids),
        "evaluations": evaluations,
        "encoding": ENCODING,
        "reference": REFERENCE,
    }
    return identity


def identity_sha256(identity: Mapping[str, Any]) -> str:
    return _sha256_bytes(canonical_bytes(identity))


def _point_report(point: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in point.items() if key != "coefficients"}


def _bind() -> tuple[Instance, tuple[dict[str, Any], ...], tuple[int, ...], dict[str, int], dict[str, str]]:
    pins = verify_pinned_inputs()
    _require(all(shared.PINNED_INPUTS[key] == PINNED_INPUTS[key] for key in shared.PINNED_INPUTS
                 if key in PINNED_INPUTS),
             "CUDA and HIP prototypes pin different shared inputs")
    ledgers = load_ledgers()
    points = coefficient_points(ledgers)
    instance = load_instance(ROOT / INSTANCE_REL)
    states, families = declared_states(instance)
    return instance, points, states, families, pins


def _state_report(states: tuple[int, ...], families: dict[str, int]) -> dict[str, Any]:
    return {
        "count": len(states),
        "bit_order": shared.BIT_ORDER,
        "families": families,
        "sha256_le_uint64_sequence": shared.states_digest(states),
        "shared_with": SHARED_LIBRARY_REL,
    }


def build_plan() -> dict[str, Any]:
    """Validate every binding and describe the run without compiling or evaluating."""
    instance, points, states, families, pins = _bind()
    return {
        "schema": SCHEMA_PLAN,
        "mode": "plan",
        "purpose": PURPOSE,
        "track": "cuda-t4",
        "encoding": ENCODING,
        "reference": REFERENCE,
        "target": {"backend": BACKEND, "gpu_name": TARGET_GPU_NAME,
                   "compute_capability": "%d.%d" % TARGET_COMPUTE_CAPABILITY,
                   "architecture": TARGET_ARCHITECTURE},
        "device_selection": "explicit compute-capability 7.5 and T4-name match; device 0 is not assumed; "
                            "the runner requires the exact product name Tesla T4",
        "pinned_inputs": pins,
        "self_sha256": current_hashes(SELF_RELATIVES),
        "coefficient_points": [_point_report(point) for point in points],
        "state_set": _state_report(states, families),
        "planned_evaluations": len(points) * len(states),
        "compile_flags": list(COMPILE_FLAGS),
        "compile_command_template": compile_command("nvcc", Path("<tmp>/source.cu"), Path("<tmp>/crosscheck")),
        "nvcc_located": locate_nvcc() is not None,
        "writes": "none",
        "scientific_outputs": "intentionally absent",
    }


def run_crosscheck() -> dict[str, Any]:
    """Compile and execute the CUDA cross-check in a temporary directory; report counts and identity only."""
    _require(os.environ.get("PYTHONDONTWRITEBYTECODE") == "1", "PYTHONDONTWRITEBYTECODE=1 is required")
    nvcc = locate_nvcc()
    _require(nvcc is not None, "nvcc is unavailable; the CUDA cross-check cannot run on this host")
    instance, points, states, families, pins_before = _bind()
    self_before = current_hashes(SELF_RELATIVES)
    platform_before = _platform_fingerprint()
    source = ROOT / CUDA_SOURCE_REL
    reference = python_reference_bits(instance, points, states)
    encoded = encode_inputs(instance, points, states)
    temporary_path: Path | None = None
    with tempfile.TemporaryDirectory(prefix="g6-cuda-t4-energy-crosscheck-") as temporary:
        temporary_path = Path(temporary)
        nvcc_info = nvcc_version(nvcc, temporary_path)
        smi = nvidia_smi_identity(temporary_path)
        staged_source = temporary_path / "cuda_unbalanced_energy_crosscheck.cu"
        binary = temporary_path / "crosscheck"
        input_path = temporary_path / "input.words"
        output_path = temporary_path / "output.words"
        staged_source.write_bytes(source.read_bytes())
        _require(_sha256_bytes(staged_source.read_bytes()) == PINNED_INPUTS[CUDA_SOURCE_REL],
                 "staged CUDA source does not match the pinned source")
        input_path.write_bytes(encoded)
        command = compile_command(nvcc, staged_source, binary)
        compilation = _run_subprocess(command, temporary_path, COMPILE_TIMEOUT_SECONDS, "nvcc compilation")
        _require(compilation.returncode == 0,
                 "nvcc compilation failed; do not substitute relaxed floating-point flags: "
                 + compilation.stderr[-2000:])
        execution = _run_subprocess([str(binary), str(input_path), str(output_path)], temporary_path,
                                    EXECUTE_TIMEOUT_SECONDS, "CUDA execution")
        _require(execution.returncode == 0, "CUDA cross-check binary failed: " + execution.stderr[-2000:])
        try:
            device_report = json.loads(execution.stdout)
        except json.JSONDecodeError as exc:
            raise CrosscheckError("CUDA cross-check emitted malformed JSON") from exc
        validate_device_report(device_report, len(points), len(states))
        device_index, device_bits, host_bits = decode_output(output_path.read_bytes(), len(points), len(states))
        _require(device_index == device_report.get("device_index"), "device index disagreement")
    _require(temporary_path is not None and not temporary_path.exists(), "temporary directory was not removed")
    gpu = compare_bits(reference, device_bits, points, states)
    host = compare_bits(reference, host_bits, points, states)
    pins_after = verify_pinned_inputs()
    _require(pins_after == pins_before, "pinned input drift during the cross-check")
    _require(current_hashes(SELF_RELATIVES) == self_before, "prototype source drift during the cross-check")
    _require(_platform_fingerprint() == platform_before, "platform fingerprint drift during the cross-check")
    states_sha256 = shared.states_digest(states)
    identity = qualification_identity(device_report, nvcc_info, command, pins_before, states_sha256,
                                      [point["point_id"] for point in points], len(reference))
    verdict = "pass" if gpu["mismatches"] == 0 and host["mismatches"] == 0 else "fail"
    return {
        "schema": SCHEMA_RUN,
        "mode": "run",
        "purpose": PURPOSE,
        "track": "cuda-t4",
        "encoding": ENCODING,
        "reference": REFERENCE,
        "platform": platform_before,
        "pinned_inputs": pins_before,
        "pinned_inputs_after_run": pins_after,
        "self_sha256": self_before,
        "coefficient_points": [_point_report(point) for point in points],
        "state_set": _state_report(states, families),
        "compile_command": command,
        "nvcc": nvcc_info,
        "nvidia_smi": smi,
        "device": device_fingerprint(device_report),
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

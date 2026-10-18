#!/usr/bin/env python3
"""Hardware-free fixtures for the bounded CUDA/T4 unbalanced-energy cross-check.

These checks need no nvcc, no CUDA runtime, no GPU, and no Gate-5 corpus
access.  They prove the static contract (nvcc flags, pragmas, T4/sm_75
selection, pins, no assert), that the state set and coefficient points are
byte-identical to the reviewed HIP track, the input/output encodings, the
comparator, the device-report validator's rejection of every non-T4 report
(including the RX 9070 / gfx1201 report shape), the qualification-identity
hash, and the fail-closed behaviour of ``--run`` on a host without nvcc.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
MODULE = ROOT / "research/g6/cuda_qualification/cuda_energy_crosscheck.py"
RUNNER = ROOT / "research/g6/run_cuda_energy_crosscheck.py"
CUDA_SOURCE = ROOT / "research/g6/cuda_qualification/cuda_unbalanced_energy_crosscheck.cu"
STUB = ROOT / "research/g6/cuda_qualification/host_emulation_stub/cuda_runtime.h"
BOUNDARY = ROOT / "research/g6/verify_cuda_energy_crosscheck_import_boundary.py"
HOST_EMULATION = ROOT / "research/g6/verify_cuda_energy_crosscheck_host_emulation.py"
NEW_PYTHON = (MODULE, RUNNER, Path(__file__).resolve(), BOUNDARY, HOST_EMULATION)

EXPECTED_POINT_IDS = (
    "d011_primary_ell_30",
    "v14_2x_row_70_embedded_primary",
    "v14_2x_row_0_lower_endpoint",
    "v14_2x_row_110_upper_endpoint",
)
# Same regression pins as the reviewed HIP track: the state set is shared.
EXPECTED_STATE_COUNT = 1710
EXPECTED_STATE_DIGEST = "b38bd5158f397e8f7382a872ccd6794e224f46329fe0374dfbc8ac295344d5be"


class FixtureError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise FixtureError(message)


def load_module():
    specification = importlib.util.spec_from_file_location("g6_cuda_energy_crosscheck_fixture", MODULE)
    require(specification is not None and specification.loader is not None, "module unavailable")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def tree_digest(directory: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(p for p in directory.rglob("*") if p.is_file()):
        digest.update(str(path.relative_to(ROOT)).encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def canonical_report(module, point_count: int = 4, state_count: int = 1710) -> dict:
    """The shape of a genuine T4 report; values are synthetic identity only."""
    return {
        "architecture": "sm_75", "backend": module.BACKEND, "compute_capability": "7.5",
        "cuda_driver_version": 12040, "cuda_runtime_version": 12020, "device_count": 1,
        "device_index": 0, "device_name": "Tesla T4", "device_uuid_hex": "0123456789abcdef0123456789abcdef",
        "device_vs_host_cxx_mismatches": 0, "evaluations": point_count * state_count,
        "multiprocessor_count": 40, "nvcc_version": "12.2.140", "pci_bus_id": 0, "pci_device_id": 4,
        "pci_domain_id": 0, "point_count": point_count, "probe": "unbalanced_energy_transcript_crosscheck_cuda",
        "scientific_outputs": "intentionally absent", "state_count": state_count,
        "total_global_memory_bytes": 15828320256,
    }


def check_static(module) -> None:
    cuda_text = CUDA_SOURCE.read_text(encoding="utf-8")
    code_only = re.sub(r"//[^\n]*", "", cuda_text)
    require("#pragma STDC FP_CONTRACT OFF" in code_only, "CUDA source lacks the FP_CONTRACT OFF declaration")
    require("properties.major == kTargetMajor && properties.minor == kTargetMinor" in code_only
            and 'std::strstr(properties.name, "T4") != nullptr' in code_only
            and "constexpr int kTargetMajor = 7;" in code_only and "constexpr int kTargetMinor = 5;" in code_only
            and "cudaSetDevice(selected_device)" in code_only,
            "CUDA source does not select a T4 / compute capability 7.5 device explicitly")
    require("device zero" in cuda_text, "CUDA source does not document the device-order hazard")
    require("scientific_outputs" in code_only and "intentionally absent" in code_only,
            "CUDA source must declare the absent scientific output")
    # The real launch is the nvcc-only branch; the emulation branch is dead under nvcc.
    require(re.search(r"#if defined\(__CUDACC__\)\s*\n#define G6_LAUNCH_KERNEL\([^\n]*\) kernel<<<grid, block>>>\(__VA_ARGS__\)\s*\n#else",
                      code_only) is not None, "real nvcc launch branch drift")
    require(code_only.count("<<<") == 1 and code_only.count("g6_host_emulation_launch") == 1,
            "launch macro must contain exactly one real and one emulation launch")
    require("__CUDACC_VER_MAJOR__" in code_only and '"cuda-runtime"' in code_only and '"not-nvcc"' in code_only,
            "CUDA source must report the nvcc version and backend")
    forbidden_tokens = ("fma(", "__fma", "pow(", "sqrt(", "exp(", "log(", "-ffast-math", "use_fast_math",
                        "__builtin_fma", "atomicAdd", "__fmul_rn", "__dmul_rn", "__dadd_rn", "__fadd_rn",
                        "_Float", "__half", "half", "__float2", "rsqrt", "__expf")
    for token in forbidden_tokens:
        require(token not in code_only, f"forbidden token in CUDA source: {token!r}")
    require(re.search(r"\bfloat\b", code_only) is None, "CUDA source must not declare fp32 values")
    # The kernel transcript must be byte-identical to the reviewed HIP transcript.
    hip_text = (ROOT / "research/g6/gpu_qualification/gpu_unbalanced_energy_crosscheck.hip.cpp").read_text(encoding="utf-8")
    anchor_start, anchor_end = "__host__ __device__ static double unbalanced_energy_transcript(", "  return h_e;\n}\n"
    hip_body = hip_text[hip_text.index(anchor_start):hip_text.index(anchor_end) + len(anchor_end)]
    cuda_body = cuda_text[cuda_text.index(anchor_start):cuda_text.index(anchor_end) + len(anchor_end)]
    require(hip_body == cuda_body, "CUDA transcript text differs from the reviewed HIP transcript")
    stub_text = STUB.read_text(encoding="utf-8")
    require("THIS IS NOT THE CUDA RUNTIME" in stub_text and "Tesla T4 host-emulation-stub" in stub_text,
            "host-emulation stub must declare itself and name a rejectable device")
    command = module.compile_command("nvcc", Path("a"), Path("b"))
    require(command == ["nvcc", *module.COMPILE_FLAGS, "a", "-o", "b"], "compile command drift")
    for flag in ("--fmad=false", "--ftz=false", "--prec-div=true", "--prec-sqrt=true", "-ffp-contract=off",
                 "-fno-fast-math", "arch=compute_75,code=sm_75", "-O0"):
        require(flag in command, f"compile command lacks {flag}")
    require(not any(token in command for token in module.FORBIDDEN_COMPILE_TOKENS), "relaxed flag present")
    require(module.TARGET_ARCHITECTURE == "sm_75" and module.TARGET_COMPUTE_CAPABILITY == (7, 5)
            and module.TARGET_GPU_NAME == "Tesla T4", "target drift")
    for source in NEW_PYTHON:
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        require(not any(isinstance(node, ast.Assert) for node in ast.walk(tree)),
                f"assert is not permitted: {source.name}")


def check_pins(module) -> None:
    observed = module.verify_pinned_inputs()
    require(observed == module.PINNED_INPUTS, "pinned inputs drifted")
    require(observed[module.CUDA_SOURCE_REL] == hashlib.sha256(CUDA_SOURCE.read_bytes()).hexdigest(),
            "CUDA source pin is stale")
    from research.g6.gpu_qualification import energy_crosscheck as hip
    for key, value in hip.PINNED_INPUTS.items():
        if key in module.PINNED_INPUTS:
            require(module.PINNED_INPUTS[key] == value, f"CUDA pin differs from HIP pin: {key}")
    require(module.PINNED_INPUTS[module.SHARED_LIBRARY_REL]
            == hashlib.sha256((ROOT / module.SHARED_LIBRARY_REL).read_bytes()).hexdigest(),
            "shared HIP library pin is stale")
    tampered = dict(module.PINNED_INPUTS)
    tampered["src/g4/energy.py"] = "0" * 64
    try:
        module.verify_pinned_inputs(tampered)
    except module.CrosscheckError as exc:
        require("src/g4/energy.py" in str(exc), "drift message does not name the drifted file")
    else:
        raise FixtureError("pin verification accepted a drifted input")


def check_points_and_states(module, instance) -> tuple:
    ledgers = module.load_ledgers()
    points = module.coefficient_points(ledgers)
    require(tuple(point["point_id"] for point in points) == EXPECTED_POINT_IDS, "coefficient point drift")
    for point in points:
        require(point["ledger_content_sha256"] == ledgers[point["ledger_file"]]["content_sha256"],
                "point does not cite its ledger content hash")
    states, families = module.declared_states(instance)
    require(len(states) == len(set(states)) == EXPECTED_STATE_COUNT, "declared state count drift")
    from research.g6.gpu_qualification import energy_crosscheck as hip
    require(hip.states_digest(states) == EXPECTED_STATE_DIGEST, "declared state digest drift")
    hip_states, hip_families = hip.declared_states(instance)
    require(hip_states == states and hip_families == families, "CUDA state set differs from HIP state set")
    return points, states


def check_encoding_and_comparator(module, instance, points, states) -> None:
    from research.g6.gpu_qualification import energy_crosscheck as hip
    from src.g4.parameters import Coefficients

    require(module.encode_inputs(instance, points, states) == hip.encode_inputs(instance, points, states),
            "CUDA input encoding differs from HIP input encoding")
    synthetic = Coefficients(1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0)
    synthetic_points = ({"point_id": "synthetic_unit", "coefficients": synthetic},)
    synthetic_states = (0, 1, hip.FULL_MASK, 0x00033)
    reference = module.python_reference_bits(instance, synthetic_points, synthetic_states)
    clean = module.compare_bits(reference, reference, synthetic_points, synthetic_states)
    require(clean["mismatches"] == 0 and clean["evaluations"] == 4, "comparator reports mismatches on identical bits")
    corrupted = list(reference)
    corrupted[2] ^= 1
    flagged = module.compare_bits(reference, tuple(corrupted), synthetic_points, synthetic_states)
    require(flagged["mismatches"] == 1 and flagged["first_mismatches"] == [
        {"point_id": "synthetic_unit", "state_mask_hex": "0xfffff"}], "comparator missed a one-ulp corruption")
    header = [hip.OUTPUT_MAGIC, hip.FORMAT_VERSION, 1, 4, 1]
    stream = b"".join(int(w).to_bytes(8, "little") for w in header + list(reference) + list(reference))
    device_index, device_bits, host_bits = module.decode_output(stream, 1, 4)
    require(device_index == 1 and device_bits == reference and host_bits == reference, "output decoding drift")
    try:
        module.decode_output(stream[:-8], 1, 4)
    except module.CrosscheckError:
        pass
    else:
        raise FixtureError("truncated output was accepted")


def check_device_validation(module) -> None:
    good = canonical_report(module)
    require(module.validate_device_report(good, 4, 1710) is good, "canonical T4 report rejected")
    require(module.validate_device_report({**good, "device_name": "NVIDIA Tesla T4"}, 4, 1710) is not None,
            "NVIDIA-prefixed T4 name rejected")
    rejected = {
        "rx9070_rocm": {"architecture": "gfx1201", "device_index": 1, "device_name": "AMD Radeon RX 9070",
                        "device_vs_host_cxx_mismatches": 0, "evaluations": 6840, "point_count": 4,
                        "probe": "unbalanced_energy_transcript_crosscheck",
                        "scientific_outputs": "intentionally absent", "state_count": 1710},
        "hip_backend": {**good, "backend": "hip-runtime"},
        "a100": {**good, "device_name": "NVIDIA A100-SXM4-40GB", "compute_capability": "8.0", "architecture": "sm_80"},
        "l4": {**good, "device_name": "NVIDIA L4", "compute_capability": "8.9", "architecture": "sm_89"},
        "t4_wrong_capability": {**good, "compute_capability": "8.6", "architecture": "sm_86"},
        "t4_name_wrong_arch": {**good, "architecture": "sm_86"},
        "emulation_stub": {**good, "device_name": "Tesla T4 host-emulation-stub"},
        "not_nvcc": {**good, "backend": "not-nvcc"},
        "no_nvcc_version": {**good, "nvcc_version": "0.0.0"},
        "zero_runtime": {**good, "cuda_runtime_version": 0},
        "zero_driver": {**good, "cuda_driver_version": 0},
        "zero_uuid": {**good, "device_uuid_hex": "0" * 32},
        "count_drift": {**good, "state_count": 1709},
        "evaluations_drift": {**good, "evaluations": 6839},
        "boundary": {**good, "scientific_outputs": "present"},
        "not_object": ["Tesla T4"],
    }
    for label, report in rejected.items():
        try:
            module.validate_device_report(report, 4, 1710)
        except module.CrosscheckError:
            continue
        raise FixtureError(f"device validation accepted a non-T4/CUDA report: {label}")


def check_identity(module) -> None:
    report = canonical_report(module)
    nvcc_info = {"path": "/usr/local/cuda/bin/nvcc", "release": "12.2", "build": "12.2.140", "stdout": ""}
    command = module.compile_command(nvcc_info["path"], Path("x.cu"), Path("x"))
    identity = module.qualification_identity(report, nvcc_info, command, module.PINNED_INPUTS,
                                             EXPECTED_STATE_DIGEST, list(EXPECTED_POINT_IDS), 6840)
    again = module.qualification_identity(report, nvcc_info, command, module.PINNED_INPUTS,
                                          EXPECTED_STATE_DIGEST, list(EXPECTED_POINT_IDS), 6840)
    require(identity == again and module.identity_sha256(identity) == module.identity_sha256(again),
            "qualification identity is not deterministic")
    for key in ("device_uuid_hex", "pci_bus_id", "device_index"):
        require(key not in identity, f"session-specific field leaked into the platform identity: {key}")
    for key in ("gpu_name", "compute_capability", "cuda_driver_version", "cuda_runtime_version", "nvcc_build",
                "compile_flags", "cuda_source_sha256", "pinned_inputs", "state_set_sha256"):
        require(key in identity, f"qualification identity lacks {key}")
    changed = module.qualification_identity({**report, "cuda_driver_version": 12050}, nvcc_info, command,
                                            module.PINNED_INPUTS, EXPECTED_STATE_DIGEST,
                                            list(EXPECTED_POINT_IDS), 6840)
    require(module.identity_sha256(changed) != module.identity_sha256(identity), "driver change not reflected")
    fingerprint = module.device_fingerprint(report)
    require(fingerprint["device_uuid_hex"] == report["device_uuid_hex"], "device fingerprint drift")
    try:
        module.qualification_identity({**report, "nvcc_version": "12.4.131"}, nvcc_info, command,
                                      module.PINNED_INPUTS, EXPECTED_STATE_DIGEST, list(EXPECTED_POINT_IDS), 6840)
    except module.CrosscheckError:
        pass
    else:
        raise FixtureError("nvcc --version / __CUDACC_VER__ disagreement was accepted")
    try:
        module.compile_command("nvcc", Path("--use_fast_math"), Path("x"))
    except module.CrosscheckError:
        pass
    else:
        raise FixtureError("relaxed flag was accepted in the compile command")


def check_cli(module) -> None:
    environment = {"PATH": "", "PYTHONDONTWRITEBYTECODE": "1"}
    before = tree_digest(ROOT / "research/g6")
    plan = subprocess.run([sys.executable, str(RUNNER)], cwd=ROOT, text=True, capture_output=True,
                          check=False, env=environment)
    require(plan.returncode == 0, "default invocation must plan without nvcc: " + plan.stderr[-400:])
    payload = json.loads(plan.stdout)
    require(payload["mode"] == "plan" and payload["writes"] == "none" and payload["track"] == "cuda-t4"
            and payload["scientific_outputs"] == "intentionally absent"
            and isinstance(payload["nvcc_located"], bool)
            and payload["state_set"]["count"] == EXPECTED_STATE_COUNT
            and payload["planned_evaluations"] == 4 * EXPECTED_STATE_COUNT
            and payload["target"] == {"backend": "cuda-runtime", "gpu_name": "Tesla T4",
                                      "compute_capability": "7.5", "architecture": "sm_75"}
            and [p["point_id"] for p in payload["coefficient_points"]] == list(EXPECTED_POINT_IDS),
            "plan payload drift")
    require("verdict" not in payload and "gpu_vs_python" not in payload, "plan must not carry run fields")
    explicit = subprocess.run([sys.executable, str(RUNNER), "--plan"], cwd=ROOT, text=True,
                              capture_output=True, check=False, env=environment)
    require(explicit.returncode == 0 and explicit.stdout == plan.stdout, "--plan differs from default")
    optimized = subprocess.run([sys.executable, "-O", str(RUNNER), "--plan"], cwd=ROOT, text=True,
                               capture_output=True, check=False, env=environment)
    require(optimized.returncode == 0 and optimized.stdout == plan.stdout, "--plan differs under python -O")
    both = subprocess.run([sys.executable, str(RUNNER), "--plan", "--run"], cwd=ROOT, text=True,
                          capture_output=True, check=False, env=environment)
    require(both.returncode == 2, "--plan and --run must be mutually exclusive")
    # Do not invoke the CLI's --run path here.  On Colab, clearing PATH does
    # not hide its intentional /usr/local/cuda/bin/nvcc fallback, and this
    # hardware-free fixture must never compile or launch a real GPU kernel.
    original_locate_nvcc = module.locate_nvcc
    module.locate_nvcc = lambda: None
    try:
        try:
            module.run_crosscheck()
        except module.CrosscheckError as exc:
            require("nvcc is unavailable" in str(exc), "missing-nvcc refusal message drift")
        else:
            raise FixtureError("--run accepted a missing nvcc")
    finally:
        module.locate_nvcc = original_locate_nvcc
    no_env = subprocess.run([sys.executable, str(RUNNER), "--run"], cwd=ROOT, text=True,
                            capture_output=True, check=False, env={"PATH": ""})
    require(no_env.returncode == 1 and "PYTHONDONTWRITEBYTECODE=1 is required" in no_env.stderr,
            "--run without PYTHONDONTWRITEBYTECODE must fail closed")
    require(tree_digest(ROOT / "research/g6") == before, "CLI invocations changed the research/g6 tree")
    leftovers = [p for p in Path(tempfile.gettempdir()).glob("g6-cuda-t4-energy-crosscheck-*")]
    require(not leftovers, "temporary cross-check directories were left behind")


def check_run_guard(module) -> None:
    previous = os.environ.pop("PYTHONDONTWRITEBYTECODE", None)
    try:
        try:
            module.run_crosscheck()
        except module.CrosscheckError as exc:
            require("PYTHONDONTWRITEBYTECODE" in str(exc), "run guard message drift")
        else:
            raise FixtureError("run_crosscheck accepted an unqualified environment")
    finally:
        if previous is not None:
            os.environ["PYTHONDONTWRITEBYTECODE"] = previous


def main() -> int:
    try:
        module = load_module()
        check_static(module)
        check_pins(module)
        from src.g4.instance import load_instance

        instance = load_instance(ROOT / module.INSTANCE_REL)
        points, states = check_points_and_states(module, instance)
        check_encoding_and_comparator(module, instance, points, states)
        check_device_validation(module)
        check_identity(module)
        check_run_guard(module)
        check_cli(module)
        forbidden = [name for name in sys.modules if name.startswith("src.g5") or name in {
            "src.g6.g5_input", "src.g6.ratified_g5_input", "src.g6.g5_digest_registry",
            "src.g6.trial_runner", "src.g6.d011_runner"}]
        require(not forbidden, "fixtures loaded a Gate-5 corpus/runner module: " + ", ".join(forbidden))
        print("PASS CUDA T4 energy cross-check fixtures; no nvcc, GPU, Gate-5 corpus read, or repository write")
        return 0
    except FixtureError as exc:
        print(f"FAIL CUDA T4 energy cross-check fixtures: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

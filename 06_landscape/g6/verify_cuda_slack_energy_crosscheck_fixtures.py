#!/usr/bin/env python3
"""Hardware-free fixtures for the bounded CUDA/T4 slack-energy cross-check.

No nvcc, CUDA runtime, GPU, or Gate-5 corpus is touched, even when nvcc is
installed: the no-nvcc refusal is proven by injecting a locator, never by
editing PATH, and ``--run`` is never invoked with a qualified environment.
Proves the static contract (slack transcript byte-identical to the reviewed
HIP slack kernel, CUDA scaffolding from the qualified unbalanced program,
T4/7.5 selection, flags, no assert), the pins, that the raw state set and
points equal the HIP/CUDA unbalanced tracks, that the lifted/excluded
partition derived from ``exact_slack_lift`` agrees with an independent
integer-residual oracle, the encodings, the comparator, device-report and
identity behaviour, and read-only ``--plan`` under normal and ``-O`` Python.
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

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
MODULE = ROOT / "research/g6/cuda_qualification/cuda_slack_energy_crosscheck.py"
RUNNER = ROOT / "research/g6/run_cuda_slack_energy_crosscheck.py"
CUDA_SOURCE = ROOT / "research/g6/cuda_qualification/cuda_slack_energy_crosscheck.cu"
CUDA_UNBALANCED_SOURCE = ROOT / "research/g6/cuda_qualification/cuda_unbalanced_energy_crosscheck.cu"
HIP_SLACK_SOURCE = ROOT / "research/g6/gpu_qualification/gpu_slack_energy_crosscheck.hip.cpp"
BOUNDARY = ROOT / "research/g6/verify_cuda_slack_energy_crosscheck_import_boundary.py"
HOST_EMULATION = ROOT / "research/g6/verify_cuda_slack_energy_crosscheck_host_emulation.py"
NEW_PYTHON = (MODULE, RUNNER, Path(__file__).resolve(), BOUNDARY, HOST_EMULATION)
EXPECTED_POINT_IDS = ("d011_primary_ell_30", "v14_2x_row_70_embedded_primary",
                      "v14_2x_row_0_lower_endpoint", "v14_2x_row_110_upper_endpoint")
EXPECTED_STATE_DIGEST = "b38bd5158f397e8f7382a872ccd6794e224f46329fe0374dfbc8ac295344d5be"


class FixtureError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise FixtureError(message)


def load_module():
    specification = importlib.util.spec_from_file_location("g6_cuda_slack_energy_crosscheck_fixture", MODULE)
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


def pyc_snapshot() -> set[str]:
    return {str(p) for base in (ROOT / "src", ROOT / "research") for p in base.rglob("*.pyc")}


def transcript(text: str, name: str) -> str:
    start = text.index(f"__host__ __device__ static double {name}(")
    end = text.index("  return h_e;\n}\n", start) + len("  return h_e;\n}\n")
    return text[start:end]


def check_static(module) -> None:
    cuda_text = CUDA_SOURCE.read_text(encoding="utf-8")
    code_only = re.sub(r"//[^\n]*", "", cuda_text)
    require(transcript(cuda_text, "slack_energy_transcript") == transcript(HIP_SLACK_SOURCE.read_text(encoding="utf-8"),
                                                                            "slack_energy_transcript"),
            "CUDA slack transcript text differs from the reviewed HIP slack transcript")
    unbalanced = CUDA_UNBALANCED_SOURCE.read_text(encoding="utf-8")
    for anchor in ("static bool is_target_device(const cudaDeviceProp& properties) {",
                   "properties.major == kTargetMajor && properties.minor == kTargetMinor",
                   'std::strstr(properties.name, "T4") != nullptr', "constexpr int kTargetMajor = 7;",
                   "constexpr int kTargetMinor = 5;", "cudaSetDevice(selected_device)",
                   "#if defined(__CUDACC__)\n#define G6_LAUNCH_KERNEL(kernel, grid, block, ...) kernel<<<grid, block>>>(__VA_ARGS__)\n#else",
                   "#pragma STDC FP_CONTRACT OFF", "__CUDACC_VER_MAJOR__", '"cuda-runtime"', '"not-nvcc"',
                   "cudaDriverGetVersion(&driver_version)", "cudaRuntimeGetVersion(&runtime_version)",
                   "print_uuid_hex(properties);"):
        require(anchor in code_only and anchor in unbalanced, f"CUDA scaffolding anchor missing: {anchor[:50]!r}")
    for anchor in ("constexpr std::uint32_t kCoefficientWords = 3;", "constexpr std::uint32_t kSectorSlackBits = 2;",
                   "constexpr std::uint32_t kBudgetSlackBits = 11;",
                   "constexpr std::uint32_t kAuxiliaryLength = kSectorCount * kSectorSlackBits + kBudgetSlackBits;",
                   "constexpr std::uint64_t kAuxiliaryMask = (1ULL << kAuxiliaryLength) - 1ULL;",
                   '0x3158434B4C533647ULL', '0x3159434B4C533647ULL', "std::uint64_t header[7];",
                   "header[3] != kSectorSlackBits", "header[4] != kBudgetSlackBits",
                   "inputs->auxiliaries[s] > kAuxiliaryMask", "double sector_slack;", "double budget_slack;",
                   "const double weight = static_cast<double>(1ULL << d);",
                   'std::calloc(inputs->state_count, sizeof(std::uint64_t)));\n    ok = inputs->points != nullptr && inputs->states != nullptr && inputs->auxiliaries != nullptr;',
                   '"cudaMalloc(auxiliaries)"', '"cudaMemcpy(auxiliaries)"', "cudaFree(device_auxiliaries)",
                   'slack_energy_transcript_crosscheck_cuda', "device zero"):
        require(anchor in cuda_text, f"CUDA slack anchor missing: {anchor[:50]!r}")
    require(code_only.count("<<<") == 1 and code_only.count("g6_host_emulation_launch") == 1
            and "device_auxiliaries,\n                     device_output" in code_only, "launch drift")
    require("sector_linear" not in code_only and "budget_quadratic" not in code_only, "unbalanced coefficients leaked")
    for token in ("fma(", "__fma", "pow(", "sqrt(", "exp(", "log(", "-ffast-math", "use_fast_math", "__builtin_fma",
                  "atomicAdd", "__fmul_rn", "__dmul_rn", "__dadd_rn", "__fadd_rn", "_Float", "__half", "half",
                  "__float2", "rsqrt", "__expf", "ldexp"):
        require(token not in code_only, f"forbidden token in CUDA source: {token!r}")
    require(re.search(r"\bfloat\b", code_only) is None, "CUDA source must not declare fp32 values")
    require("scientific_outputs" in code_only and "intentionally absent" in code_only, "output boundary missing")
    command = module.compile_command("nvcc", Path("a"), Path("b"))
    require(command == ["nvcc", *module.COMPILE_FLAGS, "a", "-o", "b"]
            and module.COMPILE_FLAGS == module.cuda_unbalanced.COMPILE_FLAGS, "compile contract drift")
    for flag in ("-O0", "arch=compute_75,code=sm_75", "--fmad=false", "--ftz=false", "--prec-div=true",
                 "--prec-sqrt=true", "-Xptxas", "-ffp-contract=off", "-fno-fast-math"):
        require(flag in command, f"compile command lacks {flag}")
    require(module.TARGET_ARCHITECTURE == "sm_75" and module.TARGET_COMPUTE_CAPABILITY == (7, 5)
            and module.TARGET_GPU_NAME == "Tesla T4" and module.PROBE == "slack_energy_transcript_crosscheck_cuda",
            "target drift")
    require(re.fullmatch(r"[0-9a-f]{64}", module.DECLARED_PREREQUISITE_UNBALANCED_IDENTITY_SHA256) is not None,
            "prerequisite identity malformed")
    for source in NEW_PYTHON:
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        require(not any(isinstance(node, ast.Assert) for node in ast.walk(tree)), f"assert is not permitted: {source.name}")


def check_pins(module) -> None:
    observed = module.verify_pinned_inputs()
    require(observed == module.PINNED_INPUTS, "pinned inputs drifted")
    require(observed[module.CUDA_SOURCE_REL] == hashlib.sha256(CUDA_SOURCE.read_bytes()).hexdigest(), "CUDA pin stale")
    for other in (module.hip_slack.PINNED_INPUTS, module.cuda_unbalanced.PINNED_INPUTS):
        for key, value in other.items():
            if key in module.PINNED_INPUTS:
                require(module.PINNED_INPUTS[key] == value, f"pin differs from a sibling prototype: {key}")
    require(module.PINNED_INPUTS[module.CUDA_UNBALANCED_LIBRARY_REL]
            == hashlib.sha256((ROOT / module.CUDA_UNBALANCED_LIBRARY_REL).read_bytes()).hexdigest()
            and module.PINNED_INPUTS[module.HIP_SLACK_LIBRARY_REL]
            == hashlib.sha256((ROOT / module.HIP_SLACK_LIBRARY_REL).read_bytes()).hexdigest(),
            "consumed library pins stale")
    tampered = dict(module.PINNED_INPUTS)
    tampered["src/g4/energy.py"] = "0" * 64
    try:
        module.verify_pinned_inputs(tampered)
    except module.CrosscheckError as exc:
        require("src/g4/energy.py" in str(exc), "drift message does not name the drifted file")
    else:
        raise FixtureError("pin verification accepted a drifted input")


def independent_lift_oracle(instance, mask: int):
    """Integer residual oracle: which register (in exact_slack_lift order) refuses, or the exact word."""
    x = [(mask >> i) & 1 for i in range(20)]
    word = 0
    for j, members in enumerate(instance.sectors):
        residual = instance.C - sum(x[i] for i in members)
        if residual < 0 or residual > 3:
            return f"sector[{j}]", None
        word |= residual << (2 * j)
    spend = +0.0
    for i in range(20):
        spend = spend + instance.prices[i] * float(x[i])
    residual = instance.B - spend
    if residual != int(residual) or residual < 0 or residual >= 2048:
        return "budget", None
    word |= int(residual) << 8
    return None, word


def check_points_states_and_lift(module, instance) -> tuple:
    ledgers = module.load_ledgers()
    points = module.coefficient_points(ledgers)
    require(tuple(point["point_id"] for point in points) == EXPECTED_POINT_IDS, "coefficient point drift")
    require(all(point["consumed_by_slack_transcript"] == ["alpha", "sector_slack", "budget_slack"] for point in points),
            "slack point relabelling drift")
    states, families = module.declared_states(instance)
    require(module.hip_unbalanced.states_digest(states) == EXPECTED_STATE_DIGEST and len(states) == 1710,
            "raw state set drift from the reviewed tracks")
    cuda_states, _ = module.cuda_unbalanced.declared_states(instance)
    require(cuda_states == states, "raw state set differs from the CUDA unbalanced track")
    lifted, excluded = module.lift_states(instance, states)
    require(len(lifted) + sum(excluded.values()) == len(states) and len(lifted) > 0, "lift partition incomplete")
    require(len({mask for mask, _ in lifted}) == len(lifted), "lifted masks not unique")
    oracle_excluded: dict[str, int] = {}
    oracle_words = {}
    for mask in states:
        refusal, word = independent_lift_oracle(instance, mask)
        if refusal is None:
            oracle_words[mask] = word
        else:
            oracle_excluded[refusal] = oracle_excluded.get(refusal, 0) + 1
    require(oracle_excluded == excluded, f"exclusion partition differs from the oracle: {excluded} vs {oracle_excluded}")
    require({mask: word for mask, word in lifted} == oracle_words, "lifted auxiliary words differ from the oracle")
    require([mask for mask, _ in lifted] == [mask for mask in states if mask in oracle_words], "lift order drift")
    for mask, word in lifted[:64]:
        auxiliary = module.hip_slack.word_to_auxiliary(word)
        require(len(auxiliary) == 19 and module.hip_slack.auxiliary_to_word(auxiliary) == word, "auxiliary round trip")
    return points, states, lifted, excluded


def check_encoding_and_comparator(module, instance, points, lifted) -> None:
    payload = module.encode_inputs(instance, points, lifted)
    words = [int.from_bytes(payload[i:i + 8], "little") for i in range(0, len(payload), 8)]
    require(words[:7] == [int.from_bytes(b"G6SLKCX1", "little"), 1, 20, 2, 11, len(points), len(lifted)],
            "slack input header drift")
    require(words[-len(lifted):] == [word for _, word in lifted]
            and words[-2 * len(lifted):-len(lifted)] == [mask for mask, _ in lifted], "state/auxiliary tail drift")
    require(payload == module.hip_slack.encode_inputs(instance, points, lifted), "encoding differs from HIP slack")
    from src.g4.parameters import Coefficients

    synthetic = ({"point_id": "synthetic_unit", "coefficients": Coefficients(1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0)},)
    sample = lifted[:4]
    reference = module.python_reference_bits(instance, synthetic, sample)
    require(len(reference) == 4, "reference length drift")
    clean = module.compare_bits(reference, reference, synthetic, sample)
    require(clean["mismatches"] == 0 and clean["evaluations"] == 4, "comparator reports mismatches on identical bits")
    corrupted = list(reference)
    corrupted[1] ^= 1
    flagged = module.compare_bits(reference, tuple(corrupted), synthetic, sample)
    require(flagged["mismatches"] == 1 and flagged["first_mismatches"][0]["state_mask_hex"] == f"0x{sample[1][0]:05x}",
            "comparator missed a one-ulp corruption")
    header = [int.from_bytes(b"G6SLKCY1", "little"), 1, 1, 4, 1]
    stream = b"".join(int(w).to_bytes(8, "little") for w in header + list(reference) + list(reference))
    index, device_bits, host_bits = module.decode_output(stream, 1, 4)
    require(index == 1 and device_bits == reference and host_bits == reference, "output decoding drift")
    for broken in (stream[:-8], stream + b"\0" * 8, b"\0" * len(stream)):
        try:
            module.decode_output(broken, 1, 4)
        except module.CrosscheckError:
            continue
        raise FixtureError("malformed output was accepted")


def canonical_report(module, state_count: int) -> dict:
    return {
        "architecture": "sm_75", "backend": module.BACKEND, "compute_capability": "7.5",
        "cuda_driver_version": 13000, "cuda_runtime_version": 12080, "device_count": 1, "device_index": 0,
        "device_name": "Tesla T4", "device_uuid_hex": "0123456789abcdef0123456789abcdef",
        "device_vs_host_cxx_mismatches": 0, "evaluations": 4 * state_count, "multiprocessor_count": 40,
        "nvcc_version": "12.8.93", "pci_bus_id": 0, "pci_device_id": 4, "pci_domain_id": 0, "point_count": 4,
        "probe": module.PROBE, "scientific_outputs": "intentionally absent", "state_count": state_count,
        "total_global_memory_bytes": 15828320256,
    }


def check_device_and_identity(module, lifted, states) -> None:
    good = canonical_report(module, len(lifted))
    require(module.validate_device_report(good, 4, len(lifted)) is good, "canonical T4 report rejected")
    for label, report in {
        "unbalanced_probe": {**good, "probe": "unbalanced_energy_transcript_crosscheck_cuda"},
        "rx9070": {**good, "device_name": "AMD Radeon RX 9070", "architecture": "gfx1201"},
        "hip": {**good, "backend": "hip-runtime"}, "a100": {**good, "device_name": "NVIDIA A100-SXM4-40GB"},
        "cc86": {**good, "compute_capability": "8.6", "architecture": "sm_86"},
        "stub": {**good, "device_name": "Tesla T4 host-emulation-stub"}, "not_nvcc": {**good, "backend": "not-nvcc"},
        "count": {**good, "state_count": len(lifted) + 1}, "raw_count": {**good, "state_count": len(states)},
    }.items():
        try:
            module.validate_device_report(report, 4, len(lifted))
        except module.CrosscheckError:
            continue
        raise FixtureError(f"device validation accepted: {label}")
    nvcc_info = {"path": "/usr/local/cuda/bin/nvcc", "release": "12.8", "build": "12.8.93", "stdout": ""}
    command = module.compile_command(nvcc_info["path"], Path("x.cu"), Path("x"))
    lifted_sha = module.hip_slack.lifted_digest(lifted)
    identity = module.qualification_identity(good, nvcc_info, command, module.PINNED_INPUTS, lifted_sha,
                                             EXPECTED_STATE_DIGEST, list(EXPECTED_POINT_IDS), 4 * len(lifted))
    again = module.qualification_identity(good, nvcc_info, command, module.PINNED_INPUTS, lifted_sha,
                                          EXPECTED_STATE_DIGEST, list(EXPECTED_POINT_IDS), 4 * len(lifted))
    require(identity == again, "identity not deterministic")
    require(identity["encoding"] == "slack" and identity["lifted_pairs_sha256"] == lifted_sha
            and identity["cuda_source_sha256"] == module.PINNED_INPUTS[module.CUDA_SOURCE_REL]
            and identity["probe"] == module.PROBE and identity["pinned_inputs"] == module.PINNED_INPUTS
            and identity["compile_flags"] == list(module.COMPILE_FLAGS), "slack identity binding drift")
    unbalanced_identity = module.cuda_unbalanced.qualification_identity(
        {**good, "probe": "unbalanced_energy_transcript_crosscheck_cuda"}, nvcc_info, command,
        module.cuda_unbalanced.PINNED_INPUTS, EXPECTED_STATE_DIGEST, list(EXPECTED_POINT_IDS), 6840)
    require(module.identity_sha256(identity) != module.identity_sha256(unbalanced_identity),
            "slack identity collides with the unbalanced identity")
    try:
        module.qualification_identity({**good, "nvcc_version": "12.2.140"}, nvcc_info, command, module.PINNED_INPUTS,
                                      lifted_sha, EXPECTED_STATE_DIGEST, list(EXPECTED_POINT_IDS), 4 * len(lifted))
    except module.CrosscheckError:
        pass
    else:
        raise FixtureError("nvcc version disagreement accepted")


def check_run_refusals(module) -> None:
    calls = []

    def never_located():
        calls.append(1)
        return None

    def must_not_be_called():
        raise FixtureError("nvcc locator consulted before the environment guard")

    previous = os.environ.pop("PYTHONDONTWRITEBYTECODE", None)
    try:
        try:
            module.run_crosscheck(locate=must_not_be_called)
        except module.CrosscheckError as exc:
            require("PYTHONDONTWRITEBYTECODE" in str(exc), "environment guard message drift")
        else:
            raise FixtureError("run_crosscheck accepted an unqualified environment")
    finally:
        os.environ["PYTHONDONTWRITEBYTECODE"] = "1" if previous is None else previous
    try:
        module.run_crosscheck(locate=never_located)
    except module.CrosscheckError as exc:
        require("nvcc is unavailable" in str(exc) and calls == [1], "no-nvcc refusal drift")
    else:
        raise FixtureError("run_crosscheck proceeded without nvcc")
    require(not list(Path(tempfile.gettempdir()).glob("g6-cuda-t4-slack-energy-crosscheck-*")),
            "refused runs left temporary directories")


def check_cli(lifted_count: int) -> None:
    environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    before = tree_digest(ROOT / "research/g6")
    plan = subprocess.run([sys.executable, str(RUNNER)], cwd=ROOT, text=True, capture_output=True, check=False,
                          env=environment)
    require(plan.returncode == 0, "default invocation must plan read-only: " + plan.stderr[-400:])
    payload = json.loads(plan.stdout)
    require(payload["mode"] == "plan" and payload["writes"] == "none" and payload["track"] == "cuda-t4"
            and payload["encoding"] == "slack" and payload["scientific_outputs"] == "intentionally absent"
            and payload["lift"]["lifted_count"] == lifted_count
            and payload["lift"]["lifted_count"] + payload["lift"]["excluded_count"] == 1710
            and payload["planned_evaluations"] == 4 * lifted_count
            and payload["target"]["gpu_name"] == "Tesla T4" and payload["target"]["compute_capability"] == "7.5"
            and [p["point_id"] for p in payload["coefficient_points"]] == list(EXPECTED_POINT_IDS),
            "plan payload drift")
    require("verdict" not in payload and "gpu_vs_python" not in payload, "plan must not carry run fields")
    for flags in (["--plan"],):
        explicit = subprocess.run([sys.executable, str(RUNNER), *flags], cwd=ROOT, text=True, capture_output=True,
                                  check=False, env=environment)
        require(explicit.returncode == 0 and explicit.stdout == plan.stdout, "--plan differs from default")
    optimized = subprocess.run([sys.executable, "-O", str(RUNNER), "--plan"], cwd=ROOT, text=True,
                               capture_output=True, check=False, env=environment)
    require(optimized.returncode == 0 and optimized.stdout == plan.stdout, "--plan differs under python -O")
    both = subprocess.run([sys.executable, str(RUNNER), "--plan", "--run"], cwd=ROOT, text=True,
                          capture_output=True, check=False, env=environment)
    require(both.returncode == 2 and both.stdout == "", "--plan and --run must be mutually exclusive")
    # --run is exercised only with the environment guard unmet: it refuses before any nvcc lookup.
    no_env = {key: value for key, value in os.environ.items() if key != "PYTHONDONTWRITEBYTECODE"}
    guarded = subprocess.run([sys.executable, "-B", str(RUNNER), "--run"], cwd=ROOT, text=True, capture_output=True,
                             check=False, env=no_env)
    require(guarded.returncode == 1 and guarded.stdout == "" and "PYTHONDONTWRITEBYTECODE=1 is required" in guarded.stderr,
            "--run without PYTHONDONTWRITEBYTECODE must fail closed")
    require(tree_digest(ROOT / "research/g6") == before, "CLI invocations changed the research/g6 tree")
    require(not list(Path(tempfile.gettempdir()).glob("g6-cuda-t4-slack-energy-crosscheck-*")), "temporary leftovers")


def main() -> int:
    pyc_before = pyc_snapshot()
    try:
        require(os.environ.get("PYTHONDONTWRITEBYTECODE") == "1", "run with PYTHONDONTWRITEBYTECODE=1")
        module = load_module()
        check_static(module)
        check_pins(module)
        from src.g4.instance import load_instance

        instance = load_instance(ROOT / module.INSTANCE_REL)
        points, states, lifted, excluded = check_points_states_and_lift(module, instance)
        check_encoding_and_comparator(module, instance, points, lifted)
        check_device_and_identity(module, lifted, states)
        check_run_refusals(module)
        check_cli(len(lifted))
        forbidden = [name for name in sys.modules if name.startswith("src.g5") or name in {
            "src.g6.g5_input", "src.g6.ratified_g5_input", "src.g6.g5_digest_registry",
            "src.g6.trial_runner", "src.g6.d011_runner"}]
        require(not forbidden, "fixtures loaded a Gate-5 corpus/runner module: " + ", ".join(forbidden))
        require(pyc_snapshot() == pyc_before, "verification wrote bytecode")
        print("PASS CUDA T4 slack energy cross-check fixtures; "
              f"lifted={len(lifted)} excluded={sum(excluded.values())} by_register={json.dumps(excluded, sort_keys=True)} "
              f"evaluations={4 * len(lifted)}; no nvcc, GPU, Gate-5 corpus read, bytecode, or repository write")
        return 0
    except FixtureError as exc:
        print(f"FAIL CUDA T4 slack energy cross-check fixtures: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

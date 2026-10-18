#!/usr/bin/env python3
"""Hardware-free fixtures for the non-production unbalanced-energy GPU throughput benchmark.

No HIP compiler, GPU, or Gate-5 corpus access is needed.  These checks prove
the static contract of the harness (kernel text included verbatim, no fp32
arithmetic, no scientific print), the pins, the two compile profiles and
the forbidden-flag guard, the launch-count bounds, the strict harness-report
validator, the timing summary, and the fail-closed behaviour of ``--run`` on
a host without hipcc.  No energy is evaluated here.
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
MODULE = ROOT / "research/g6/gpu_qualification/energy_benchmark.py"
RUNNER = ROOT / "research/g6/run_gpu_energy_benchmark.py"
HARNESS = ROOT / "research/g6/gpu_qualification/gpu_unbalanced_energy_benchmark.hip.cpp"
CROSSCHECK_SOURCE = ROOT / "research/g6/gpu_qualification/gpu_unbalanced_energy_crosscheck.hip.cpp"
BENCH_STUB = ROOT / "research/g6/gpu_qualification/host_emulation_stub_benchmark/hip/hip_runtime.h"
CROSSCHECK_STUB = ROOT / "research/g6/gpu_qualification/host_emulation_stub/hip/hip_runtime.h"
BOUNDARY = ROOT / "research/g6/verify_gpu_energy_benchmark_import_boundary.py"
HOST_EMULATION = ROOT / "research/g6/verify_gpu_energy_benchmark_host_emulation.py"
NEW_PYTHON = (MODULE, RUNNER, Path(__file__).resolve(), BOUNDARY, HOST_EMULATION)

# Regression pins of the already reviewed cross-check pieces this benchmark
# builds on; the benchmark never modifies them.
EXPECTED_CROSSCHECK_SOURCE_SHA256 = "909c1403503098a1b475d207fafa991f8116b5a29055ce3afa30ffdee8842b9b"
EXPECTED_CROSSCHECK_STUB_SHA256 = "fc592117bf19bfe4efd9cbcb0bb5ed8ba7e7feb90c7e56730aa245effdf3f25f"
EXPECTED_PROFILE_IDS = ("strict_o0", "candidate_o3")
EXPECTED_STATE_COUNT = 1710
EXPECTED_STATE_DIGEST = "b38bd5158f397e8f7382a872ccd6794e224f46329fe0374dfbc8ac295344d5be"


class FixtureError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise FixtureError(message)


def load_module():
    specification = importlib.util.spec_from_file_location("g6_gpu_energy_benchmark_fixture", MODULE)
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


def check_static(module) -> None:
    text = HARNESS.read_text(encoding="utf-8")
    code_only = re.sub(r"//[^\n]*", "", text)
    require("#define main crosscheck_program_main" in code_only and module.INCLUDE_DIRECTIVE in code_only
            and "#undef main" in code_only, "harness must include the pinned cross-check source with main renamed")
    require(code_only.index("#define main") < code_only.index(module.INCLUDE_DIRECTIVE) < code_only.index("#undef main"),
            "harness include/rename ordering drift")
    require(code_only.count("#include \"") == 1, "harness may include exactly one project source")
    require("__global__" not in code_only and "unbalanced_energy_transcript(" in code_only
            and re.search(r"double\s+unbalanced_energy_transcript\s*\(", code_only) is None,
            "harness must call, never redefine, the kernel or the transcript")
    require("crosscheck_kernel" in code_only, "harness must launch the cross-check kernel")
    require(re.search(r"#pragma\s+clang\s+fp\s+contract\(off\)", code_only) is not None
            and re.search(r"#pragma\s+clang\s+fp\s+reassociate\(off\)", code_only) is not None,
            "harness lacks the fp pragmas")
    require('"gfx1201", 7) == 0' in code_only and "hipSetDevice(selected_device)" in code_only,
            "harness does not select the gfx1201 device explicitly")
    for token in ("fma(", "__fma", "pow(", "sqrt(", "exp(", "log(", "-ffast-math", "__builtin_fma", "atomicAdd",
                  "__fmul_rn", "__dmul_rn", "__dadd_rn", "_Float", "__fp16", "half", "%a", "%e", "%g"):
        require(token not in code_only, f"forbidden token in harness: {token!r}")
    # The only fp32 object is the HIP event duration; it is a time, not an energy.
    fp32_free = code_only.replace("float elapsed_ms_f32 = 0.0f;", "").replace("hipEventElapsedTime(&elapsed_ms_f32", "")
    require(re.search(r"\bfloat\b", fp32_free) is None, "harness declares an fp32 value other than the event duration")
    require("scientific_outputs" in code_only and "intentionally absent" in code_only,
            "harness must declare the absent scientific output")
    require("kMaxWarmupLaunches = 100" in code_only and "kMaxTimedLaunches = 5000" in code_only,
            "harness launch bounds drift")
    require(module.MAX_WARMUP_LAUNCHES == 100 and module.MAX_TIMED_LAUNCHES == 5000, "library launch bounds drift")
    stub_text = BENCH_STUB.read_text(encoding="utf-8")
    require('#include "../../host_emulation_stub/hip/hip_runtime.h"' in stub_text
            and "NOT THE HIP RUNTIME" in stub_text, "benchmark stub must layer over the cross-check stub")
    require(hashlib.sha256(CROSSCHECK_STUB.read_bytes()).hexdigest() == EXPECTED_CROSSCHECK_STUB_SHA256,
            "the reviewed cross-check stub was modified")
    require(hashlib.sha256(CROSSCHECK_SOURCE.read_bytes()).hexdigest() == EXPECTED_CROSSCHECK_SOURCE_SHA256,
            "the reviewed cross-check source was modified")
    for source in NEW_PYTHON:
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        require(not any(isinstance(node, ast.Assert) for node in ast.walk(tree)),
                f"assert is not permitted: {source.name}")


def check_pins(module, crosscheck) -> None:
    observed = module.verify_all_pins(crosscheck)
    require(observed == module.all_pins(crosscheck), "pinned inputs drifted")
    require(observed[module.BENCH_SOURCE_REL] == hashlib.sha256(HARNESS.read_bytes()).hexdigest(), "harness pin is stale")
    require(observed[module.CROSSCHECK_MODULE_REL] == hashlib.sha256(
        (ROOT / module.CROSSCHECK_MODULE_REL).read_bytes()).hexdigest(), "cross-check library pin is stale")
    require(set(crosscheck.PINNED_INPUTS) < set(observed), "benchmark pins must include every cross-check pin")
    tampered = dict(module.all_pins(crosscheck))
    tampered[module.BENCH_SOURCE_REL] = "0" * 64
    try:
        crosscheck.verify_pinned_inputs(tampered)
    except crosscheck.CrosscheckError as exc:
        require(module.BENCH_SOURCE_REL in str(exc), "drift message does not name the drifted file")
    else:
        raise FixtureError("pin verification accepted a drifted harness")


def check_profiles(module, crosscheck) -> None:
    require(tuple(p["profile_id"] for p in module.PROFILES) == EXPECTED_PROFILE_IDS, "profile drift")
    source, binary = Path("/tmp/x/src.hip.cpp"), Path("/tmp/x/bin")
    strict = module.profile_compile_command(crosscheck, "hipcc", module.profile_by_id("strict_o0"), source, binary)
    require(strict == crosscheck.compile_command("hipcc", source, binary),
            "strict profile is not the existing cross-check compile command")
    candidate = module.profile_compile_command(crosscheck, "hipcc", module.profile_by_id("candidate_o3"), source, binary)
    differences = [(a, b) for a, b in zip(strict, candidate, strict=True) if a != b]
    require(differences == [("-O0", "-O3")], "candidate profile differs from strict by more than the optimisation level")
    for command in (strict, candidate):
        for flag in (*module.COMMON_FLAGS, *module.DEVICE_FLAGS):
            require(flag in command, f"profile command lacks {flag}")
        for flag in crosscheck.REQUIRED_COMPILE_FLAGS:
            require(flag in command or flag == "-O0", f"profile command lacks reviewed flag {flag}")
    for bad in ("-ffast-math", "-Ofast", "-ffp-contract=fast", "-ffp-contract=on", "-funsafe-math-optimizations",
                "-fgpu-flush-denormals-to-zero", "-munsafe-fp-atomics", "-mfma", "-march=native", "-ffp-model=fast"):
        try:
            module.check_flags(candidate + [bad])
        except module.BenchmarkError:
            pass
        else:
            raise FixtureError(f"forbidden flag accepted: {bad}")
    for bad_command in (candidate + ["-O0"], [t if t != "-O3" else "-O2" for t in candidate],
                        [t for t in candidate if t != "-ffp-contract=off"], [t for t in candidate if t != "-fno-fast-math"]):
        try:
            module.check_flags(bad_command)
        except module.BenchmarkError:
            pass
        else:
            raise FixtureError("malformed compile command accepted")
    try:
        module.profile_by_id("candidate_o2")
    except module.BenchmarkError:
        pass
    else:
        raise FixtureError("unknown profile accepted")


def check_launch_bounds(module) -> None:
    module.validate_launch_counts(0, 1)
    module.validate_launch_counts(module.MAX_WARMUP_LAUNCHES, module.MAX_TIMED_LAUNCHES)
    for warmup, timed in ((-1, 1), (101, 1), (0, 0), (0, 5001), (True, 1), (0, 2.0), (0, "3")):
        try:
            module.validate_launch_counts(warmup, timed)
        except module.BenchmarkError:
            pass
        else:
            raise FixtureError(f"launch counts accepted: {warmup}, {timed}")


def synthetic_report(module, timed: int = 4) -> dict:
    return {
        "architecture": "gfx1201", "batch_launches": timed, "batch_wall_ms": 1.25, "block_count": 107, "block_size": 64,
        "device_index": 1, "device_name": "synthetic", "device_vs_host_cxx_mismatches": 0,
        "evaluations_per_launch": 4 * EXPECTED_STATE_COUNT, "per_launch_ms": [0.4, 0.2, 0.3, 0.1],
        "point_count": 4, "probe": module.HARNESS_PROBE, "scientific_outputs": "intentionally absent",
        "state_count": EXPECTED_STATE_COUNT, "timed_launches": timed, "warmup_launches": 2,
    }


def check_report_validation(module) -> None:
    good = synthetic_report(module)
    validated = module.validate_harness_report(dict(good), 4, EXPECTED_STATE_COUNT, 2, 4)
    require(validated == good, "validator altered a good report")
    summary = module.summarise_timings(validated)
    require(summary["per_launch_ms"] == {"min": 0.1, "median": 0.25, "mean": 0.25, "max": 0.4}
            and summary["timed_evaluations_total"] == 4 * 6840
            and abs(summary["evaluations_per_second_at_median_launch"] - 6840 / 0.00025) < 1e-6
            and summary["batch"]["mean_launch_ms"] == 1.25 / 4
            and abs(summary["batch"]["evaluations_per_second"] - 4 * 6840 / 0.00125) < 1e-6,
            "timing summary drift")
    require(set(summary) == {"evaluations_per_launch", "warmup_launches", "timed_launches", "timed_evaluations_total",
                             "per_launch_ms", "evaluations_per_second_at_median_launch", "batch", "launch_geometry"},
            "summary keys drift")
    bad_reports = []
    extra = dict(good); extra["energy_minimum"] = 1.0; bad_reports.append(("extra key", extra))
    missing = dict(good); del missing["per_launch_ms"]; bad_reports.append(("missing key", missing))
    short = dict(good); short["per_launch_ms"] = [0.1, 0.2]; bad_reports.append(("short timings", short))
    nan = dict(good); nan["per_launch_ms"] = [0.1, float("nan"), 0.3, 0.4]; bad_reports.append(("nan timing", nan))
    negative = dict(good); negative["batch_wall_ms"] = -1.0; bad_reports.append(("negative batch", negative))
    counts = dict(good); counts["evaluations_per_launch"] = 6839; bad_reports.append(("count", counts))
    probe = dict(good); probe["probe"] = "unbalanced_energy_transcript_crosscheck"; bad_reports.append(("probe", probe))
    boolean = dict(good); boolean["timed_launches"] = True; bad_reports.append(("bool", boolean))
    geometry = dict(good); geometry["block_count"] = 1; bad_reports.append(("geometry", geometry))
    launches = dict(good); launches["batch_launches"] = 3; bad_reports.append(("batch launches", launches))
    bad_reports.append(("not an object", [good]))
    for label, payload in bad_reports:
        try:
            module.validate_harness_report(payload, 4, EXPECTED_STATE_COUNT, 2, 4)
        except module.BenchmarkError:
            pass
        else:
            raise FixtureError(f"validator accepted a bad report: {label}")
    try:
        module.validate_harness_report(dict(good), 4, EXPECTED_STATE_COUNT, 3, 4)
    except module.BenchmarkError:
        pass
    else:
        raise FixtureError("validator accepted a report whose warm-up count differs from the request")


def check_cli() -> None:
    environment = {"PATH": "", "PYTHONDONTWRITEBYTECODE": "1"}
    before = tree_digest(ROOT / "research/g6")
    plan = subprocess.run([sys.executable, str(RUNNER)], cwd=ROOT, text=True, capture_output=True, check=False, env=environment)
    require(plan.returncode == 0, "default invocation must plan without a HIP compiler: " + plan.stderr[-400:])
    payload = json.loads(plan.stdout)
    require(payload["mode"] == "plan" and payload["writes"] == "none" and payload["production_claim"] == "none"
            and payload["scientific_outputs"] == "intentionally absent" and payload["hipcc_located"] is False
            and payload["state_set"]["count"] == EXPECTED_STATE_COUNT
            and payload["state_set"]["sha256_le_uint64_sequence"] == EXPECTED_STATE_DIGEST
            and payload["evaluations_per_launch"] == 4 * EXPECTED_STATE_COUNT
            and [p["profile_id"] for p in payload["profiles"]] == list(EXPECTED_PROFILE_IDS)
            and payload["launches"] == {"warmup": 10, "timed": 200, "batch": 200, "bounds": {"warmup_max": 100, "timed_max": 5000}},
            "plan payload drift")
    require("verdict" not in payload and "comparison" not in payload
            and all("timings" not in p for p in payload["profiles"]), "plan must not carry run fields")
    explicit = subprocess.run([sys.executable, str(RUNNER), "--plan"], cwd=ROOT, text=True, capture_output=True,
                              check=False, env=environment)
    require(explicit.returncode == 0 and explicit.stdout == plan.stdout, "--plan differs from default")
    custom = subprocess.run([sys.executable, str(RUNNER), "--plan", "--warmup", "3", "--launches", "50"], cwd=ROOT,
                            text=True, capture_output=True, check=False, env=environment)
    require(custom.returncode == 0 and json.loads(custom.stdout)["launches"]["timed"] == 50
            and json.loads(custom.stdout)["launches"]["warmup"] == 3, "plan ignores launch options")
    both = subprocess.run([sys.executable, str(RUNNER), "--plan", "--run"], cwd=ROOT, text=True, capture_output=True,
                          check=False, env=environment)
    require(both.returncode == 2, "--plan and --run must be mutually exclusive")
    for bad in (["--launches", "0"], ["--launches", "5001"], ["--warmup", "101"], ["--warmup", "-1"]):
        out = subprocess.run([sys.executable, str(RUNNER), "--plan", *bad], cwd=ROOT, text=True, capture_output=True,
                             check=False, env=environment)
        require(out.returncode == 1 and out.stdout == "" and "launches must be in" in out.stderr,
                f"out-of-bound launch option accepted: {bad}")
    no_hipcc = subprocess.run([sys.executable, str(RUNNER), "--run"], cwd=ROOT, text=True, capture_output=True,
                              check=False, env=environment)
    require(no_hipcc.returncode == 1 and "hipcc is unavailable" in no_hipcc.stderr and no_hipcc.stdout == "",
            "--run without hipcc must fail closed before any evaluation")
    no_env = subprocess.run([sys.executable, str(RUNNER), "--run"], cwd=ROOT, text=True, capture_output=True,
                            check=False, env={"PATH": ""})
    require(no_env.returncode == 1 and "PYTHONDONTWRITEBYTECODE=1 is required" in no_env.stderr,
            "--run without PYTHONDONTWRITEBYTECODE must fail closed")
    require(tree_digest(ROOT / "research/g6") == before, "CLI invocations changed the research/g6 tree")
    leftovers = list(Path(tempfile.gettempdir()).glob("g6-gpu-energy-benchmark-*"))
    require(not leftovers, "temporary benchmark directories were left behind")


def check_run_guard(module) -> None:
    previous = os.environ.pop("PYTHONDONTWRITEBYTECODE", None)
    try:
        try:
            module.run_benchmark()
        except module.BenchmarkError as exc:
            require("PYTHONDONTWRITEBYTECODE" in str(exc), "run guard message drift")
        else:
            raise FixtureError("run_benchmark accepted an unqualified environment")
    finally:
        if previous is not None:
            os.environ["PYTHONDONTWRITEBYTECODE"] = previous


def main() -> int:
    try:
        module = load_module()
        crosscheck = module.load_crosscheck()
        check_static(module)
        check_pins(module, crosscheck)
        check_profiles(module, crosscheck)
        check_launch_bounds(module)
        check_report_validation(module)
        check_run_guard(module)
        check_cli()
        forbidden = [name for name in sys.modules if name.startswith("src.g5") or name in {
            "src.g6.g5_input", "src.g6.ratified_g5_input", "src.g6.g5_digest_registry",
            "src.g6.trial_runner", "src.g6.d011_runner"}]
        require(not forbidden, "fixtures loaded a Gate-5 corpus/runner module: " + ", ".join(forbidden))
        print("PASS GPU energy benchmark fixtures; no HIP compiler, GPU, Gate-5 corpus read, or repository write")
        return 0
    except (FixtureError, RuntimeError) as exc:
        print(f"FAIL GPU energy benchmark fixtures: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

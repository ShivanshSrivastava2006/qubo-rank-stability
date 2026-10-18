#!/usr/bin/env python3
"""Non-writing plan/refusal fixtures; never calls nvcc or a GPU."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import hashlib
import json

if os.environ.get("PYTHONDONTWRITEBYTECODE") != "1":
    raise SystemExit("PYTHONDONTWRITEBYTECODE=1 is required")
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.g9.cuda_qualification import stage2_cuda_core_qualification as qualifier
from research.g9.cuda_qualification import stage2_cuda_execution_contract as contract


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> None:
    original_which = qualifier.shutil.which
    qualifier.shutil.which = lambda name: (_ for _ in ()).throw(
        RuntimeError("nvcc lookup must not happen before owner release"))
    try:
        plan = qualifier.build_plan()
        require(plan["schema"] == qualifier.PLAN_SCHEMA and
                plan["execution_release"] == "separate_owner_release_required" and
                plan["scientific_outputs"] == "intentionally absent" and
                plan["content_sha256"] == contract.content_sha256(plan),
                "read-only plan drift")
        require(set(plan["source_sha256"]) == set(qualifier.SOURCE_RELS),
                "plan omitted a source")
        require(plan["compile_flags"] == list(qualifier.COMPILE_FLAGS) and
                plan["abi_compile_flags"] == list(qualifier.ABI_COMPILE_FLAGS) and
                tuple(qualifier.core.CUDA_COMPILE_FLAGS) ==
                ("--fmad=false", "--ftz=false", "--prec-div=true", "--prec-sqrt=true"),
                "numerical compile contract drift")
        sample_platform = {key: "host-stub" for key in contract.IDENTITY_PLATFORM_KEYS}
        require(contract.validate_qualification_identity(contract.qualification_identity(
            sample_platform, {"core": "a" * 64}, qualifier.ABI_COMPILE_FLAGS)),
            "ABI compile flags cannot form a qualification identity")
        require(qualifier.EXECUTION_RELEASE_REL ==
                "research/decisions/GATE_9_CUDA_CORE_DRY_RUN_RELEASE.json",
                "dry-run release path drift")
        staged = json.loads((ROOT / qualifier.EXECUTION_RELEASE_REL).read_text(encoding="ascii"))
        require(staged["status"] in ("pending", "approved"), "dry-run release has invalid status")
        for reviewed in (None, "", "a" * 64):
            try:
                qualifier.run_qualification(reviewed)
            except qualifier.CoreQualificationError as exc:
                require("reviewed handoff" in str(exc) or "release hash differs" in str(exc) or
                        "separate CUDA qualification permission" in str(exc),
                        "unexpected refusal reason")
            else:
                raise RuntimeError("unreleased CUDA qualification was accepted")
    finally:
        qualifier.shutil.which = original_which

    # Exercise the future release-map check without making CUDA executable:
    # the real module path is restored before any CLI test.
    with tempfile.TemporaryDirectory(prefix="g9-core-release-fixture-") as temporary:
        release_path = Path(temporary) / "synthetic_release.json"
        release = {"schema": qualifier.RELEASE_SCHEMA, "status": "approved",
                   "source_sha256": qualifier._source_hashes(),
                   "authorities": qualifier._authorities()}
        original_release = qualifier.EXECUTION_RELEASE_REL
        original_permission = os.environ.get("G9_ALLOW_NONSCIENTIFIC_CUDA_QUALIFICATION")
        try:
            qualifier.EXECUTION_RELEASE_REL = str(release_path)
            os.environ["G9_ALLOW_NONSCIENTIFIC_CUDA_QUALIFICATION"] = "1"
            release_path.write_bytes(contract.canonical_bytes(release) + b"\n")
            release_sha = hashlib.sha256(release_path.read_bytes()).hexdigest()
            require(qualifier._released(release_sha)[0] == release_sha,
                    "exact reviewed source map was refused")
            drifted = json.loads(release_path.read_text(encoding="ascii"))
            first = next(iter(drifted["source_sha256"]))
            drifted["source_sha256"][first] = "0" * 64
            release_path.write_bytes(contract.canonical_bytes(drifted) + b"\n")
            wrong_sha = hashlib.sha256(release_path.read_bytes()).hexdigest()
            try:
                qualifier._released(wrong_sha)
            except qualifier.CoreQualificationError as exc:
                require("reviewed release map" in str(exc), "wrong source-map refusal reason")
            else:
                raise RuntimeError("hash-consistent source-map drift was accepted")
        finally:
            qualifier.EXECUTION_RELEASE_REL = original_release
            if original_permission is None:
                os.environ.pop("G9_ALLOW_NONSCIENTIFIC_CUDA_QUALIFICATION", None)
            else:
                os.environ["G9_ALLOW_NONSCIENTIFIC_CUDA_QUALIFICATION"] = original_permission

    command = [sys.executable, str(ROOT / "research/g9/run_stage2_cuda_core_qualification.py")]
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    normal = subprocess.run([*command, "--plan"], cwd=ROOT, env=env,
                            text=True, capture_output=True, check=False, timeout=30)
    require(normal.returncode == 0 and normal.stdout.endswith("\n") and not normal.stderr,
            "CLI plan failed")
    optimized = subprocess.run([sys.executable, "-O", command[1], "--plan"], cwd=ROOT,
                               env=env, text=True, capture_output=True, check=False, timeout=30)
    require(optimized.returncode == 0 and optimized.stdout == normal.stdout,
            "normal/-O plan bytes differ")
    if staged["status"] == "pending":
        env["G9_ALLOW_NONSCIENTIFIC_CUDA_QUALIFICATION"] = "1"
        pending_sha = hashlib.sha256((ROOT / qualifier.EXECUTION_RELEASE_REL).read_bytes()).hexdigest()
        refused = subprocess.run([*command, "--qualify-self-test", "--reviewed", pending_sha],
                                 cwd=ROOT, env=env, text=True, capture_output=True,
                                 check=False, timeout=30)
        require(refused.returncode == 1 and "release has invalid fields" in refused.stderr and
                not refused.stdout, "pending CLI release did not refuse before nvcc")

    import_probe = (
        "import sys; "
        "from research.g9.cuda_qualification import stage2_cuda_core_qualification; "
        "assert not any(name == 'numpy' or name.startswith('numpy.') or "
        "name == 'src' or name.startswith('src.') for name in sys.modules)"
    )
    isolated = subprocess.run([sys.executable, "-c", import_probe], cwd=ROOT, env=env,
                              text=True, capture_output=True, check=False, timeout=30)
    require(isolated.returncode == 0 and not isolated.stderr,
            "qualification import crossed into NumPy or frozen src before release")

    # Host-stub compilation checks the embedded platform probe's C++ syntax;
    # this is not nvcc, CUDA compilation, or a GPU run.
    stub = ROOT / "research/g6/cuda_qualification/host_emulation_stub"
    with tempfile.TemporaryDirectory(prefix="g9-core-probe-host-") as temporary:
        source = Path(temporary) / "probe.cpp"
        binary = Path(temporary) / "probe"
        source.write_text(qualifier.PLATFORM_PROBE, encoding="ascii")
        compiled = subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
                                   "-I", str(stub), str(source), "-o", str(binary)],
                                  cwd=ROOT, text=True, capture_output=True, check=False, timeout=30)
        require(compiled.returncode == 0, "host-stub platform probe did not compile: " + compiled.stderr)
        executed = subprocess.run([str(binary)], cwd=ROOT, text=True,
                                  capture_output=True, check=False, timeout=30)
        require(executed.returncode == 0 and not executed.stderr, "host-stub platform probe failed")
        probe = qualifier._json(executed.stdout, "host-stub platform probe")
        require(set(probe) == {"gpu_name", "compute_capability", "cuda_driver_version",
                               "cuda_runtime_version"}, "host-stub platform probe field drift")
    print("PASS Stage-2 CUDA core qualification plan and execution lock fixtures")


if __name__ == "__main__":
    main()

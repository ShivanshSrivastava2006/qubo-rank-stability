#!/usr/bin/env python3
"""Offline Gate-9 A-path fixtures; g++ host emulation, never nvcc or Kaggle.

The eight GPU mutations are checked independently against the established
host-emulation mutations, compiled with the G6 CUDA stub, and required to
produce well-formed reports that the frozen Python reference rejects.  The
future GPU runner is execution-locked and never invoked by this verifier.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile

if os.environ.get("PYTHONDONTWRITEBYTECODE") != "1":
    raise SystemExit("PYTHONDONTWRITEBYTECODE=1 is required")
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.g9.cuda_qualification import stage2_cuda_core_corruption_qualification as qualifier
from research.g9.cuda_qualification import stage2_cuda_core_stream_engine as core
from research.g9.cuda_qualification import stage2_cuda_core_qualification as clean
from research.g9.cuda_qualification import stage2_cuda_execution_contract as contract
from research.g9 import verify_stage2_cuda_core_stream_engine_host_emulation as host


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def refuses(function, *args, **kwargs) -> bool:
    try:
        function(*args, **kwargs)
    except qualifier.CorruptionQualificationError:
        return True
    return False


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


HOST_LABELS = {
    "canonical_index_reversal": "canonical index reversal",
    "energy_reassociation": "frozen energy accumulation-order drift",
    "slack_register_layout_drift": "slack register layout drift",
    "tied_lift_loss": "tied lift loss (second minimizer dropped)",
    "first_seen_minimum_weakened": "segment strict '<' weakened to '<='",
    "d015_scale_omitted": "omitted D015 max(|y|,|y_min|) scale",
    "c_h_bit_permutation": "c_H bit permutation",
    "nonfinite_energy_injection": "injected NaN energy",
}


def main() -> None:
    source = (ROOT / qualifier.CORE_REL).read_text(encoding="utf-8")
    plan = qualifier.build_plan()
    require(plan["schema"] == qualifier.PLAN_SCHEMA and
            plan["mode"] == "non_scientific_corruption_plan" and
            plan["scientific_outputs"] == "intentionally absent" and
            plan["stage2_inputs"] == "intentionally absent" and
            plan["execution_release"] == "separate_owner_release_required" and
            plan["image_digest_status"] == "post_run_metadata_audit_required" and
            plan["content_sha256"] == contract.content_sha256(plan),
            "read-only A-plan shape or commitment drift")
    require(plan["core_release_sha256"] == qualifier.CORE_RELEASE_SHA256 and
            plan["clean_dry_run_receipt_sha256"] == qualifier.CLEAN_RECEIPT_SHA256 and
            plan["source_sha256"] == qualifier.source_hashes() and
            set(plan["source_sha256"]) == set(qualifier.SOURCE_RELS),
            "A-plan source and authority binding drift")
    require(plan["compile_flags"] == list(clean.COMPILE_FLAGS) and
            tuple(core.CUDA_COMPILE_FLAGS) ==
            ("--fmad=false", "--ftz=false", "--prec-div=true", "--prec-sqrt=true"),
            "GPU numerical flags drifted")
    require(len(plan["mutations"]) == len(qualifier.MUTATIONS) == 8 and
            {row["category"] for row in plan["mutations"]} == qualifier.REQUIRED_CATEGORIES,
            "required A categories or mutation count drift")
    changes = qualifier.mutated_sources(source)
    host_changes = dict(host.mutations(source))
    require(set(HOST_LABELS) == {mutation.label for mutation, _ in changes},
            "reviewed host labels and GPU mutation labels differ")
    for mutation, changed in changes:
        require(changed == host_changes[HOST_LABELS[mutation.label]],
                "GPU mutation differs from reviewed host mutation: " + mutation.label)
        row = next(row for row in plan["mutations"] if row["label"] == mutation.label)
        require(row == {"label": mutation.label, "category": mutation.category,
                        "source_sha256": sha(changed.encode("utf-8"))},
                "mutation plan does not bind exact changed source: " + mutation.label)
    require(refuses(qualifier.mutated_sources, source.replace(qualifier.MUTATIONS[0].old, "", 1)),
            "a missing mutation anchor was accepted")
    require(refuses(qualifier.mutated_sources, source + qualifier.MUTATIONS[0].old),
            "an ambiguous mutation anchor was accepted")

    # The execution gate must refuse before any nvcc lookup.  A temporary
    # approved-looking release exercises the map check without invoking CUDA.
    original_which = qualifier.shutil.which
    qualifier.shutil.which = lambda _name: (_ for _ in ()).throw(
        RuntimeError("nvcc lookup happened before A execution release"))
    try:
        require(qualifier.build_plan() == plan, "read-only plan looked up nvcc or changed")
        for reviewed in (None, "", "0" * 64):
            require(refuses(qualifier.run_qualification, reviewed),
                    "unreleased A qualification reached nvcc")
    finally:
        qualifier.shutil.which = original_which

    with tempfile.TemporaryDirectory(prefix="g9-A-release-fixture-") as temporary:
        release_path = Path(temporary) / "release.json"
        owner_release = {"schema": qualifier.RELEASE_SCHEMA, "status": "approved",
                         "plan_content_sha256": plan["content_sha256"],
                         "source_sha256": plan["source_sha256"]}
        original_rel = qualifier.RELEASE_REL
        original_allow = os.environ.get(qualifier.ALLOW_ENV)
        try:
            qualifier.RELEASE_REL = str(release_path)
            os.environ[qualifier.ALLOW_ENV] = "1"
            release_path.write_bytes(contract.canonical_bytes(owner_release) + b"\n")
            reviewed = sha(release_path.read_bytes())
            require(qualifier._released(reviewed)["content_sha256"] == plan["content_sha256"],
                    "exact A owner release refused")
            drifted = dict(owner_release, plan_content_sha256="0" * 64)
            release_path.write_bytes(contract.canonical_bytes(drifted) + b"\n")
            require(refuses(qualifier._released, sha(release_path.read_bytes())),
                    "hash-consistent A-plan drift was accepted")
            pending = dict(owner_release, status="pending")
            release_path.write_bytes(contract.canonical_bytes(pending) + b"\n")
            require(refuses(qualifier._released, sha(release_path.read_bytes())),
                    "pending A release was accepted")
        finally:
            qualifier.RELEASE_REL = original_rel
            if original_allow is None:
                os.environ.pop(qualifier.ALLOW_ENV, None)
            else:
                os.environ[qualifier.ALLOW_ENV] = original_allow

    with tempfile.TemporaryDirectory(prefix="g9-A-runtime-fixture-") as temporary:
        fake = Path(temporary)
        cuda = fake / "cuda"
        (cuda / "bin").mkdir(parents=True)
        device = fake / "dev"
        device.mkdir()
        (device / "nvidia0").symlink_to("/dev/null")
        original = {key: os.environ.get(key) for key in
                    ("PATH", "CUDA_HOME", "COLAB_IMAGE_TYPE", "BUILD_DATE", "GIT_COMMIT", "CUDA_VERSION")}
        try:
            os.environ.update({"PATH": str(cuda / "bin"), "CUDA_HOME": str(cuda),
                               "COLAB_IMAGE_TYPE": "gpu", "BUILD_DATE": "synthetic-build",
                               "GIT_COMMIT": "a" * 40, "CUDA_VERSION": "12.8.1"})
            observed = qualifier._runtime_build(str(cuda / "bin" / "nvcc"), device)
            import numpy as np
            require(observed["nvidia_device_count"] == 1 and
                    observed["BUILD_DATE"] == "synthetic-build" and
                    observed["COLAB_IMAGE_TYPE"] == "gpu" and
                    observed["python_version"] == platform.python_version() and
                    observed["numpy_version"] == np.__version__,
                    "valid runtime build refused or omitted Python/NumPy identity")
            os.environ.pop("BUILD_DATE")
            require(refuses(qualifier._runtime_build, str(cuda / "bin" / "nvcc"), device),
                    "missing build identity was accepted")
            os.environ["BUILD_DATE"] = "synthetic-build"
            require(refuses(qualifier._runtime_build, str(fake / "other-nvcc"), device),
                    "shadowed compiler was accepted")
            (device / "nvidia0").unlink()
            require(refuses(qualifier._runtime_build, str(cuda / "bin" / "nvcc"), device),
                    "missing NVIDIA device was accepted")
        finally:
            for key, value in original.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    command = [sys.executable, str(ROOT / "research/g9/run_stage2_cuda_core_corruption_qualification.py")]
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    normal = subprocess.run([*command, "--plan"], cwd=ROOT, env=env,
                            text=True, capture_output=True, check=False, timeout=30)
    optimized = subprocess.run([sys.executable, "-O", command[1], "--plan"], cwd=ROOT, env=env,
                               text=True, capture_output=True, check=False, timeout=30)
    require(normal.returncode == optimized.returncode == 0 and
            normal.stdout == optimized.stdout and not normal.stderr and not optimized.stderr,
            "normal/-O plan differs")
    require(json.loads(normal.stdout) == plan, "CLI plan differs from module plan")
    forbidden = subprocess.run([*command, "--qualify-corruptions", "--reviewed", "0" * 64],
                               cwd=ROOT, env=env, text=True, capture_output=True,
                               check=False, timeout=30)
    require(forbidden.returncode == 1 and not forbidden.stdout and
            "A-execution permission" in forbidden.stderr,
            "CLI reached GPU before release")

    # Numerical load-bearing evidence: compilation and self-test with g++ +
    # CUDA stub, never nvcc.  Every selected mutant must compile, emit JSON,
    # and be rejected by the same Python reference the GPU runner will use.
    domain = core.build_domain(core.synthetic_payload())
    scans = {(row, encoding): core.scan(domain, row, encoding)
             for row in core.ROW_NAMES for encoding in core.ENCODINGS}
    generic = {(row, encoding): core.scan(domain, core.coefficient_row(row), encoding, control={})
               for row in core.ROW_NAMES for encoding in core.ENCODINGS}
    baseline_result = host.run(source, warning_free=True)
    require(baseline_result is not None and baseline_result.returncode == 0,
            "host baseline did not compile and pass")
    baseline = core.validate_self_test_report(host.payload(baseline_result), scans, domain, generic)
    for mutation, changed in changes:
        result = host.run(changed, allow_compile_failure=False)
        require(result is not None and result.returncode in (0, 1),
                "host corruption did not produce a controlled report: " + mutation.label)
        report = host.payload(result)
        require(report.get("device_name") == baseline["device_name"] and
                report.get("scientific_outputs") == "intentionally absent",
                "host corruption changed the device or output scope: " + mutation.label)
        if mutation.label == "nonfinite_energy_injection":
            require(result.returncode == 1 and report.get("nonfinite_energies", 0) > 0,
                    "non-finite mutation did not trip the device verdict")
        try:
            core.validate_self_test_report(report, scans, domain, generic)
        except core.CoreStreamEngineError:
            pass
        else:
            raise RuntimeError("host corruption escaped Python reference: " + mutation.label)
        print("  host-detected: " + mutation.label)
    require(qualifier.source_hashes() == plan["source_sha256"],
            "source hashes changed during offline fixtures")
    print(f"PASS Gate-9 CUDA corruption qualification offline fixtures: "
          f"{len(changes)}/{len(changes)} selected mutations compile and are rejected; "
          "no nvcc or GPU used")


if __name__ == "__main__":
    main()

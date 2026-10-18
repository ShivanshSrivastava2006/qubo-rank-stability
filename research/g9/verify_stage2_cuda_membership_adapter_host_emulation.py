#!/usr/bin/env python3
"""Host-emulate the membership-adapter self-test and its corruption mutations.

Compiles the pinned .cu with g++ against the existing CUDA host stub, so no
nvcc, GPU, or Kaggle session is involved.  Every artefact is written inside a
temporary directory that is removed on exit.
"""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from research.g9.cuda_qualification import stage2_cuda_membership_adapter as adapter  # noqa: E402

SOURCE = ROOT / "research/g9/cuda_qualification/stage2_cuda_membership_adapter.cu"
STUB = ROOT / "research/g6/cuda_qualification/host_emulation_stub"


class FixtureError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise FixtureError(message)


def run(source_text: str) -> subprocess.CompletedProcess[str]:
    compiler = shutil.which("g++")
    require(compiler is not None, "g++ is unavailable for host emulation")
    with tempfile.TemporaryDirectory(prefix="g9-membership-adapter-host-") as temporary:
        directory = Path(temporary)
        candidate, executable = directory / "source.cu", directory / "self_test"
        candidate.write_text(source_text, encoding="utf-8")
        compiled = subprocess.run(
            [compiler, "-x", "c++", "-std=c++17", "-O0", "-Wall", "-Wextra", "-Wno-unknown-pragmas",
             "-ffp-contract=off", "-I", str(STUB), str(candidate), "-o", str(executable)],
            cwd=ROOT, text=True, capture_output=True, check=False,
        )
        require(compiled.returncode == 0, "host compilation failed: " + compiled.stderr[-1200:])
        require("warning:" not in compiled.stderr, "host compilation emitted warnings: " + compiled.stderr[-800:])
        return subprocess.run([str(executable), "--self-test"], cwd=ROOT, text=True, capture_output=True, check=False)


def payload(result: subprocess.CompletedProcess[str]) -> dict:
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise FixtureError("invalid JSON from host self-test: " + result.stderr[-500:]) from exc


def main() -> int:
    source = SOURCE.read_text(encoding="utf-8")
    baseline = run(source)
    require(baseline.returncode == 0, "baseline adapter self-test failed: " + baseline.stderr[-500:])
    report = adapter.validate_self_test_report(payload(baseline))
    require(report["device_name"] == "host-emulation-fake-gpu", "unexpected host-emulation device")

    mutations = (
        # Canonical 20-bit decoded ordering.
        ("canonical index order", source.replace("kAssetCount - 1u - asset", "asset", 1), False),
        # Explicit membership replaced by the inherited contiguous assumption.
        ("contiguous membership fallback",
         source.replace("const std::uint32_t asset = instance->membership[sector][member];",
                        "const std::uint32_t asset = sector * kSectorSize + member;", 1), False),
        # A single asset moved between two sectors.
        ("membership content swap",
         source.replace("{0u, 5u, 9u, 14u, 19u}, {1u, 4u, 8u, 12u, 17u}",
                        "{0u, 5u, 9u, 14u, 17u}, {1u, 4u, 8u, 12u, 19u}", 1), False),
        # Objective accumulation order: quadratic phase before the mu phase.
        ("objective accumulation order",
         source.replace("  f_acc = accumulate_mu(instance, x, f_acc);\n  f_acc = accumulate_quadratic(instance, x, f_acc);",
                        "  f_acc = accumulate_quadratic(instance, x, f_acc);\n  f_acc = accumulate_mu(instance, x, f_acc);", 1), False),
        # Sector register bit weight and sector register layout offset.
        ("sector register bit weight",
         source.replace("const double sector_weight = static_cast<double>(1ULL << bit);",
                        "const double sector_weight = static_cast<double>(1ULL << (bit + 1u));", 1), False),
        ("sector register layout offset",
         source.replace("return reg < kSectorCount ? (reg * kSectorSlackBits) : (kSectorCount * kSectorSlackBits);",
                        "return reg < kSectorCount ? reg : (kSectorCount * kSectorSlackBits);", 1), False),
        # Budget register bit weight and budget register width.
        ("budget register bit weight",
         source.replace("const double budget_weight = static_cast<double>(1ULL << bit);",
                        "const double budget_weight = static_cast<double>(1ULL << (bit + 1u));", 1), False),
        ("budget register width",
         source.replace("constexpr std::uint32_t kBudgetSlackBits = 11;",
                        "constexpr std::uint32_t kBudgetSlackBits = 10;", 1), False),
        # Frozen lift policy: drop the tie retention so a tied register yields one lift.
        ("lift tie retention",
         source.replace("if (penalties[index] == best) {", "if (penalties[index] == best && out->count == 0u) {", 1), False),
        # Non-finite injection must both fail the process and be refused.  The
        # mu variant poisons a prepared term; the c_value/b variants poison a
        # residual, i.e. the quantity the lift policy would otherwise floor.
        ("nonfinite injection via mu",
         source.replace("value.mu[asset] = (static_cast<double>(asset) - 9.0) / 1000.0;",
                        "value.mu[asset] = 0.0 / 0.0;", 1), True),
        ("nonfinite sector residual via c_value",
         source.replace("value.c_value = 2.0;", "value.c_value = 0.0 / 0.0;", 1), True),
        ("nonfinite budget residual via b",
         source.replace("value.b = 1100.0;", "value.b = 0.0 / 0.0;", 1), True),
        ("infinite budget residual via b",
         source.replace("value.b = 1100.0;", "value.b = 1.0 / 0.0;", 1), True),
    )
    # A corruption may be caught on either of two independent channels: the
    # self-test's own reconstruction/non-finite check failing the process, or
    # the Python reference refusing the emitted report.  A mutation escapes
    # only if it both exits zero and produces a report the reference accepts.
    detected: dict[str, str] = {}
    for label, mutated, must_fail_process in mutations:
        require(mutated != source, f"mutation anchor missing: {label}")
        result = run(mutated)
        if must_fail_process:
            require(result.returncode != 0, f"{label} mutation was not refused by the self-test")
        channels = []
        if result.returncode != 0:
            channels.append("self-test")
        if result.stdout.strip():
            try:
                adapter.validate_self_test_report(payload(result))
            except adapter.MembershipAdapterError:
                channels.append("python-reference")
            else:
                raise FixtureError(f"mutation escaped the Python reference: {label}")
        require(channels, f"mutation produced neither a failure nor a report: {label}")
        detected[label] = "+".join(channels)
    require(len(detected) == len(mutations), "not every adapter mutation was detected")
    for label, channel in detected.items():
        print(f"  detected via {channel}: {label}")
    print(f"PASS Stage-2 membership adapter host emulation; baseline matches Python and "
          f"{len(detected)}/{len(mutations)} corruptions detected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

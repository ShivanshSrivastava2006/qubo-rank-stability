#!/usr/bin/env python3
"""Host-emulate the 20-bit decoded/slack preparation self-test and mutations."""
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
from research.g9.cuda_qualification import stage2_cuda_preparation as prep  # noqa: E402

SOURCE = ROOT / "research/g9/cuda_qualification/stage2_cuda_preparation_selftest.cu"
STUB = ROOT / "research/g6/cuda_qualification/host_emulation_stub"


class FixtureError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise FixtureError(message)


def run(source_text: str) -> subprocess.CompletedProcess[str]:
    compiler = shutil.which("g++")
    require(compiler is not None, "g++ is unavailable")
    with tempfile.TemporaryDirectory(prefix="g9-cuda-preparation-host-") as temporary:
        directory = Path(temporary)
        candidate, executable = directory / "source.cu", directory / "self_test"
        candidate.write_text(source_text, encoding="utf-8")
        compiled = subprocess.run([compiler, "-x", "c++", "-std=c++17", "-O0", "-Wall", "-Wextra", "-Wno-unknown-pragmas",
                                  "-ffp-contract=off", "-I", str(STUB), str(candidate), "-o", str(executable)],
                                 cwd=ROOT, text=True, capture_output=True, check=False)
        require(compiled.returncode == 0, "host compilation failed: " + compiled.stderr[-1000:])
        return subprocess.run([str(executable), "--self-test"], cwd=ROOT, text=True, capture_output=True, check=False)


def payload(result: subprocess.CompletedProcess[str]) -> dict:
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise FixtureError("invalid JSON from host self-test: " + result.stderr[-500:]) from exc


def main() -> int:
    source = SOURCE.read_text(encoding="utf-8")
    baseline = run(source)
    require(baseline.returncode == 0, "baseline preparation failed")
    prep.validate_self_test_report(payload(baseline))
    mutations = (
        ("canonical index order", source.replace("kAssetCount - 1u - i", "i", 1), False),
        ("objective arithmetic", source.replace("f_acc = f_acc + mu_term;", "f_acc = f_acc - mu_term;", 1), False),
        ("sector register bit weight", source.replace("1ULL << bit", "1ULL << (bit + 1u)", 1), False),
        ("auxiliary layout", source.replace("offset += kSectorBits;", "offset += 1u;", 1), False),
        ("nonfinite preparation", source.replace("value.mu[i] = (static_cast<double>(i) - 9.0) / 1000.0;", "value.mu[i] = 0.0 / 0.0;", 1), True),
    )
    detected = 0
    for label, mutated, process_failure in mutations:
        require(mutated != source, f"mutation anchor missing: {label}")
        result = run(mutated)
        require((result.returncode != 0) if process_failure else (result.returncode == 0), f"unexpected process result: {label}")
        try:
            prep.validate_self_test_report(payload(result))
        except prep.PreparationError:
            detected += 1
        else:
            raise FixtureError(f"mutation escaped Python reference: {label}")
    require(detected == len(mutations), "not every preparation mutation was detected")
    print("PASS Stage-2 CUDA preparation host emulation; baseline matches Python and 5/5 corruptions detected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

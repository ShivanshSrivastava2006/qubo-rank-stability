#!/usr/bin/env python3
"""Host-emulate the tie-compaction self-test and its corruption mutations.

Compiles the pinned .cu with g++ against the existing CUDA host stub, so no
nvcc, GPU, or Kaggle session is involved.  Every artefact lives inside a
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
from research.g9.cuda_qualification import stage2_cuda_tie_transport as tie  # noqa: E402

SOURCE = ROOT / "research/g9/cuda_qualification/stage2_cuda_tie_transport.cu"
STUB = ROOT / "research/g6/cuda_qualification/host_emulation_stub"


class FixtureError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise FixtureError(message)


def run(source_text: str) -> subprocess.CompletedProcess[str]:
    compiler = shutil.which("g++")
    require(compiler is not None, "g++ is unavailable for host emulation")
    with tempfile.TemporaryDirectory(prefix="g9-tie-transport-host-") as temporary:
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
    require(baseline.returncode == 0, "baseline tie-transport self-test failed: " + baseline.stderr[-500:])
    report = tie.validate_self_test_report(payload(baseline))
    require(report["device_name"] == "host-emulation-fake-gpu", "unexpected host-emulation device")
    require(report["verdict"] == "pass" and report["compacted_total"] > 0, "baseline produced no transport")
    # The emitted report must not carry the transported indices themselves.
    require("compacted_indices" not in baseline.stdout and "\"words\"" not in baseline.stdout,
            "self-test leaked the compacted payload")

    mutations = (
        # Stable ordering: local scan direction, chunk prefix direction.
        ("reverse canonical scan within a chunk",
         source.replace("for (std::uint32_t local = 0; local < span; ++local) {",
                        "for (std::uint32_t local = span; local-- > 0;) {", 1)),
        ("reverse chunk-prefix order",
         source.replace("for (std::uint32_t prefix_chunk = 0; prefix_chunk < kChunkCount; ++prefix_chunk) {",
                        "for (std::uint32_t prefix_chunk = kChunkCount; prefix_chunk-- > 0;) {", 1)),
        # Offset arithmetic and per-chunk count.
        ("offset accumulation corruption",
         source.replace("running = running + audits[prefix_chunk].flagged;",
                        "running = running + audits[prefix_chunk].flagged + 1u;", 1)),
        ("chunk count corruption",
         source.replace("if (value != 0u) local.flagged += 1u;", "if (value > 4u) local.flagged += 1u;", 1)),
        # Dropped and duplicated compacted entries.
        ("dropped flagged entry",
         source.replace("if (entry_flags != 0u) {", "if (entry_flags != 0u && local != 0u) {", 1)),
        ("duplicate compacted entry",
         source.replace("const std::uint32_t position = start + local;",
                        "const std::uint32_t position = start + (local == 1u ? 0u : local);", 1)),
        # Flag legality and nesting.
        ("illegal flag value", source.replace("if (position % 11u == 4u) return 4u;",
                                              "if (position % 11u == 4u) return 12u;", 1)),
        ("nested-flag bit corruption", source.replace("if (position % 5u == 2u) return 6u;",
                                                      "if (position % 5u == 2u) return 5u;", 1)),
        # A reported counter that no longer measures what it claims.
        ("per-c_H counter corruption",
         source.replace("if ((value & (1u << bit)) != 0u) local.per_ch[bit] += 1u;",
                        "if ((value & (1u << ((bit + 1u) % kCHCount))) != 0u) local.per_ch[bit] += 1u;", 1)),
        # Compound: weakening the order audit must not let a real defect pass.
        # A lone audit weakening is unobservable on a clean stream — there is
        # nothing to under-report — so it is paired with the duplicate defect
        # it would otherwise conceal.
        ("weakened order audit hiding a duplicate",
         source.replace("const std::uint32_t position = start + local;",
                        "const std::uint32_t position = start + (local == 1u ? 0u : local);", 1)
               .replace("if (index <= previous) local.order_violations += 1u;",
                        "if (index < previous) local.order_violations += 1u;", 1)),
    )
    detected: dict[str, str] = {}
    for label, mutated in mutations:
        require(mutated != source, f"mutation anchor missing: {label}")
        result = run(mutated)
        channels = []
        if result.returncode != 0:
            channels.append("self-test")
        if result.stdout.strip():
            try:
                tie.validate_self_test_report(payload(result))
            except tie.TieTransportError:
                channels.append("python-reference")
            else:
                raise FixtureError(f"mutation escaped the Python reference: {label}")
        require(channels, f"mutation produced neither a failure nor a report: {label}")
        detected[label] = "+".join(channels)
    require(len(detected) == len(mutations), "not every tie-transport mutation was detected")
    for label, channel in detected.items():
        print(f"  detected via {channel}: {label}")
    print(f"PASS Stage-2 tie-transport host emulation; baseline matches Python and "
          f"{len(detected)}/{len(mutations)} corruptions detected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

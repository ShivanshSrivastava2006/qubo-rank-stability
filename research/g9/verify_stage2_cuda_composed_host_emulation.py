#!/usr/bin/env python3
"""Host-emulate the composed self-test and its corruption mutations.

Compiles the pinned .cu with g++ against the existing CUDA host stub, so no
nvcc, GPU, or Kaggle session is involved.  Everything is built inside a
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
from research.g9.cuda_qualification import stage2_cuda_composed as composed  # noqa: E402

SOURCE = ROOT / "research/g9/cuda_qualification/stage2_cuda_composed_selftest.cu"
STUB = ROOT / "research/g6/cuda_qualification/host_emulation_stub"


class FixtureError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise FixtureError(message)


def run(source_text: str, *, warning_free: bool = False) -> subprocess.CompletedProcess[str]:
    """Compile and run one source.  ``warning_free`` is asserted for the pinned
    baseline only: a deliberately corrupted source may legitimately warn (for
    example, removing the D015 scale leaves its inputs unused)."""
    compiler = shutil.which("g++")
    require(compiler is not None, "g++ is unavailable for host emulation")
    with tempfile.TemporaryDirectory(prefix="g9-composed-host-") as temporary:
        directory = Path(temporary)
        candidate, executable = directory / "source.cu", directory / "self_test"
        candidate.write_text(source_text, encoding="utf-8")
        compiled = subprocess.run(
            [compiler, "-x", "c++", "-std=c++17", "-O0", "-Wall", "-Wextra", "-Wno-unknown-pragmas",
             "-ffp-contract=off", "-I", str(STUB), str(candidate), "-o", str(executable)],
            cwd=ROOT, text=True, capture_output=True, check=False,
        )
        require(compiled.returncode == 0, "host compilation failed: " + compiled.stderr[-1500:])
        if warning_free:
            require("warning:" not in compiled.stderr,
                    "baseline compilation emitted warnings: " + compiled.stderr[-800:])
        return subprocess.run([str(executable), "--self-test"], cwd=ROOT, text=True, capture_output=True, check=False)


def payload(result: subprocess.CompletedProcess[str]) -> dict:
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise FixtureError("invalid JSON from host self-test: " + result.stderr[-500:]) from exc


def main() -> int:
    source = SOURCE.read_text(encoding="utf-8")
    baseline = run(source, warning_free=True)
    require(baseline.returncode == 0, "baseline composed self-test failed: " + baseline.stderr[-600:])
    report = composed.validate_self_test_report(payload(baseline))
    require(report["device_name"] == "host-emulation-fake-gpu", "unexpected host-emulation device")
    require(report["compacted_total_unbalanced"] > 0 and report["compacted_total_slack"] > 0,
            "baseline transported nothing")
    require("compacted_indices" not in baseline.stdout and "minimum_index" not in baseline.stdout,
            "self-test leaked an index")

    mutations = (
        ("canonical index reversal", source.replace("kAssetCount - 1u - asset", "asset", 1)),
        ("contiguous-sector fallback",
         source.replace("const std::uint32_t asset = instance->membership[sector][member];",
                        "const std::uint32_t asset = sector * kSectorSize + member;", 1)),
        ("membership swap",
         source.replace("{0u, 6u, 11u, 15u, 19u}, {1u, 5u, 10u, 14u, 18u}",
                        "{0u, 6u, 11u, 15u, 18u}, {1u, 5u, 10u, 14u, 19u}", 1)),
        ("objective accumulation-order drift",
         source.replace("  f_acc = accumulate_mu(instance, x, f_acc);\n  f_acc = accumulate_quadratic(instance, x, f_acc);",
                        "  f_acc = accumulate_quadratic(instance, x, f_acc);\n  f_acc = accumulate_mu(instance, x, f_acc);", 1)),
        ("sector register bit-weight drift",
         source.replace("const double sector_weight = static_cast<double>(1ULL << bit);",
                        "const double sector_weight = static_cast<double>(1ULL << (bit + 1u));", 1)),
        ("budget register bit-weight drift",
         source.replace("const double budget_weight = static_cast<double>(1ULL << bit);",
                        "const double budget_weight = static_cast<double>(1ULL << (bit + 1u));", 1)),
        ("slack register layout drift",
         source.replace("return reg < kSectorCount ? (reg * kSectorSlackBits) : (kSectorCount * kSectorSlackBits);",
                        "return reg < kSectorCount ? reg : (kSectorCount * kSectorSlackBits);", 1)),
        ("slack-minimizer tie retention loss",
         source.replace("if (penalties[index] == best) {", "if (penalties[index] == best && out->count == 0u) {", 1)),
        ("strict minimum '<' -> '<='",
         source.replace("      if (energies[base + position] < best) {\n        best = energies[base + position];\n        best_index = position;",
                        "      if (energies[base + position] <= best) {\n        best = energies[base + position];\n        best_index = position;", 1)),
        ("omitted D015 max scale",
         source.replace("const double maximum = y_magnitude > prime_magnitude ? y_magnitude : prime_magnitude;",
                        "const double maximum = 0.0;", 1)),
        ("c_H bit permutation",
         source.replace("return index == 0u ? 1024.0 : (index == 1u ? 2048.0 : 4096.0);",
                        "return index == 0u ? 4096.0 : (index == 1u ? 2048.0 : 1024.0);", 1)),
        ("local compaction-order reversal",
         source.replace("for (std::uint32_t local = 0; local < span; ++local) {",
                        "for (std::uint32_t local = span; local-- > 0;) {", 1)),
        ("prefix-offset reversal",
         source.replace("for (std::uint32_t prefix_chunk = 0; prefix_chunk < kChunkCount; ++prefix_chunk) {",
                        "for (std::uint32_t prefix_chunk = kChunkCount; prefix_chunk-- > 0;) {", 1)),
        ("prefix-offset corruption",
         source.replace("running = running + counts[encoding * kChunkCount + prefix_chunk];",
                        "running = running + counts[encoding * kChunkCount + prefix_chunk] + 1u;", 1)),
        # Data-independent drop: skip each chunk's first flagged entry, whatever
        # its local index happens to be in this fixed table.
        ("dropped compacted entry",
         source.replace("if (entry_flags != 0u) {",
                        "if (entry_flags != 0u && cursor != offsets[encoding * (kChunkCount + 1u) + chunk]) {", 1)),
        ("duplicated compacted entry",
         source.replace("const std::uint32_t position = start + local;",
                        "const std::uint32_t position = start + (local == 1u ? 0u : local);", 1)),
        # A natural-energy defect confined to one control position: the value
        # is overwritten before the controlled checksum is formed, so only the
        # pre-control natural checksum can detect it.
        ("natural energy defect at a control position",
         source.replace("  energies[position] = unbalanced_energy(local.terms, coefficients);",
                        "  energies[position] = unbalanced_energy(local.terms, coefficients);\n"
                        "  if (position == 40u) energies[position] = energies[position] + 0x1p-20;", 1)),
        ("control offset drift",
         source.replace("const double slack_offsets[kControlCount] = {0x0p+0, 0x0p+0, 0x1p-46, 0x1p-45, 0x1p-44, 0x1p-43};",
                        "const double slack_offsets[kControlCount] = {0x0p+0, 0x0p+0, 0x1p-45, 0x1p-45, 0x1p-44, 0x1p-43};", 1)),
        ("non-finite residual injection", source.replace("value.b = 40.0;", "value.b = 0.0 / 0.0;", 1)),
        ("non-finite energy injection",
         source.replace("value.alpha = 0x1.0000000000000p-3;", "value.alpha = 0.0 / 0.0;", 1)),
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
                composed.validate_self_test_report(payload(result))
            except composed.ComposedSelfTestError:
                channels.append("python-reference")
            else:
                raise FixtureError(f"mutation escaped the Python reference: {label}")
        require(channels, f"mutation produced neither a failure nor a report: {label}")
        detected[label] = "+".join(channels)
    require(len(detected) == len(mutations), "not every composed mutation was detected")
    for label, channel in detected.items():
        print(f"  detected via {channel}: {label}")
    print(f"PASS Stage-2 composed host emulation; baseline matches Python and "
          f"{len(detected)}/{len(mutations)} corruptions detected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Host-emulate the core-stream engine self-test and its corruption mutations.

Compiles the pinned .cu with g++ against the existing CUDA host stub, so no
nvcc, GPU, or Kaggle session is involved.  Each build and run happens inside a
temporary directory that is removed on exit.  Nothing is written to the project
tree and no scientific value is printed.
"""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from research.g9.cuda_qualification import stage2_cuda_core_stream_engine as engine  # noqa: E402

SOURCE = ROOT / "research/g9/cuda_qualification/stage2_cuda_core_stream_engine.cu"
STUB = ROOT / "research/g6/cuda_qualification/host_emulation_stub"


class FixtureError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise FixtureError(message)


def run(source_text: str, *, warning_free: bool = False, allow_compile_failure: bool = False,
        optimization: str = "-O0") -> subprocess.CompletedProcess[str] | None:
    """Compile and run one source; ``None`` means it did not compile.

    ``warning_free`` applies to the pinned baseline only.  A deliberately
    corrupted source may legitimately warn, and refusing to compile is a valid
    way for a corruption to be rejected.
    """
    compiler = shutil.which("g++")
    require(compiler is not None, "g++ is unavailable for host emulation")
    with tempfile.TemporaryDirectory(prefix="g9-core-host-") as temporary:
        directory = Path(temporary)
        candidate, executable = directory / "source.cu", directory / "self_test"
        candidate.write_text(source_text, encoding="utf-8")
        compiled = subprocess.run(
            [compiler, "-x", "c++", "-std=c++17", optimization, "-Wall", "-Wextra",
             "-Wno-unknown-pragmas", *engine.HOST_COMPILE_FLAGS, "-I", str(STUB),
             str(candidate), "-o", str(executable)],
            cwd=ROOT, text=True, capture_output=True, check=False,
        )
        if compiled.returncode != 0:
            if allow_compile_failure:
                return None
            require(False, "host compilation failed: " + compiled.stderr[-1500:])
        if warning_free:
            require("warning:" not in compiled.stderr,
                    "baseline compilation emitted warnings: " + compiled.stderr[-900:])
        return subprocess.run([str(executable), "--self-test"], cwd=ROOT, text=True,
                              capture_output=True, check=False, timeout=900)


def payload(result: subprocess.CompletedProcess[str]) -> dict:
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise FixtureError("invalid JSON from host self-test: " + result.stderr[-500:]) from exc


def mutations(source: str) -> tuple[tuple[str, str], ...]:
    """Each entry must change a value the report can see, or fail to compile."""
    return (
        ("canonical index reversal",
         source.replace("return ((index >> (kDecodedWidth - 1u - asset)) & 1u) != 0u;",
                        "return ((index >> asset) & 1u) != 0u;", 1)),
        ("contiguous-sector fallback",
         source.replace("      const std::uint32_t asset = payload->membership[s][member];",
                        "      const std::uint32_t asset = s * kSectorSize + member;", 1)),
        ("membership content drift",
         source.replace("{0u, 6u, 11u, 15u, 19u}, {1u, 5u, 10u, 14u, 18u}",
                        "{0u, 6u, 11u, 15u, 18u}, {1u, 5u, 10u, 14u, 19u}", 1)),
        # The frozen transcript is h + ((-linear) + quadratic); regrouping it as
        # (h + (-linear)) + quadratic is a genuine binary64 reassociation.
        ("frozen energy accumulation-order drift",
         source.replace("    energies[index] = h + ((-linear) + quadratic);",
                        "    energies[index] = (h + (-linear)) + quadratic;", 1)),
        ("slack register layout drift",
         source.replace("  return reg < kSectorCount ? (reg * kSectorSlackBits) : (kSectorCount * kSectorSlackBits);",
                        "  return reg < kSectorCount ? reg : (kSectorCount * kSectorSlackBits);", 1)),
        # Tied minimizers carry EQUAL penalties by construction, so a tied lift
        # is energy-degenerate: collapsing penalties[lift] onto penalties[0]
        # would be a genuine no-op.  The loss has to be in the multiplicity,
        # which is what the lift cache and its layout digest exist to catch.
        ("tied lift loss (second minimizer dropped)",
         source.replace("  values[0] = low; penalties[0] = penalty_low;\n"
                        "  values[1] = high; penalties[1] = penalty_high;\n"
                        "  return 2u;",
                        "  values[0] = low; penalties[0] = penalty_low;\n"
                        "  return 1u;", 1)),
        # The tied pair is kept but written in the wrong register order, so the
        # frozen product order and the 19-bit layout are both load-bearing.
        ("tied minimizer order inversion",
         source.replace("  values[0] = low; penalties[0] = penalty_low;\n"
                        "  values[1] = high; penalties[1] = penalty_high;\n"
                        "  return 2u;",
                        "  values[0] = high; penalties[0] = penalty_high;\n"
                        "  values[1] = low; penalties[1] = penalty_low;\n"
                        "  return 2u;", 1)),
        # Within a segment the earliest tied position must win.
        ("segment strict '<' weakened to '<='",
         source.replace("    if (!have || value < best) { best = value; best_index = position; have = true; }",
                        "    if (!have || value <= best) { best = value; best_index = position; have = true; }", 1)),
        # Across segments the earliest tied segment must win.
        ("merge strict '<' weakened to '<='",
         source.replace("        if (!merged || host_segment_value[segment] < minimum) {",
                        "        if (!merged || host_segment_value[segment] <= minimum) {", 1)),
        ("merge order drift (descending segments)",
         source.replace("      for (std::uint32_t segment = 0; segment < segment_count; ++segment) {\n"
                        "        nonfinite += host_segment_nonfinite[segment];",
                        "      for (std::uint32_t r = 0; r < segment_count; ++r) {\n"
                        "        const std::uint32_t segment = segment_count - 1u - r;\n"
                        "        nonfinite += host_segment_nonfinite[segment];", 1)),
        # D015 must scale by lambda_ref + max(|y|, |y_min|), not lambda_ref.
        ("omitted D015 max(|y|,|y_min|) scale",
         source.replace("  const double scale = lambda_ref + maximum;",
                        "  const double scale = lambda_ref;", 1)),
        ("c_H bit permutation",
         source.replace("  if (gap <= (1024.0 * kEpsilon) * scale) flags |= 1u;\n"
                        "  if (gap <= (2048.0 * kEpsilon) * scale) flags |= 2u;\n"
                        "  if (gap <= (4096.0 * kEpsilon) * scale) flags |= 4u;",
                        "  if (gap <= (1024.0 * kEpsilon) * scale) flags |= 4u;\n"
                        "  if (gap <= (2048.0 * kEpsilon) * scale) flags |= 2u;\n"
                        "  if (gap <= (4096.0 * kEpsilon) * scale) flags |= 1u;", 1)),
        ("controlled-energy drift",
         source.replace("        if (position < word_count) host_energies[position] = natural_minimum + offsets_row[slot];",
                        "        if (position < word_count) host_energies[position] = natural_minimum + offsets_row[slot] + 1.0;", 1)),
        # A defect exactly under a control position: the controlled pass
        # overwrites it, so only the natural pre-control checksum can see it.
        ("natural-energy defect at a controlled position",
         source.replace("    energies[index] = h + ((-linear) + quadratic);\n    return;",
                        "    energies[index] = h + ((-linear) + quadratic);\n"
                        "    if (index == 40u) energies[index] = energies[index] + 1.0;\n    return;", 1)),
        ("injected NaN energy",
         source.replace("    energies[index] = h + ((-linear) + quadratic);\n    return;",
                        "    energies[index] = h + ((-linear) + quadratic);\n"
                        "    if (index == 654321u) energies[index] = 0.0 / 0.0;\n    return;", 1)),
        # The lift prefix must stay 64-bit; narrowing it is a type error at the
        # kernel boundary, which is a valid way for the corruption to be caught.
        ("uint64 lift-offset prefix downgraded to uint32",
         source.replace("static std::uint64_t g_offsets[kStateCount + 1];",
                        "static std::uint32_t g_offsets[kStateCount + 1];", 1)),
        # --- compaction ------------------------------------------------------
        # Each chunk must write its own slice in ASCENDING canonical order.
        ("compaction write order reversed",
         source.replace("""  std::uint64_t cursor = prefix[chunk];
  for (std::uint64_t position = start; position < stop; ++position) {
    const std::uint64_t flags = flag_bytes[position];""",
                        """  std::uint64_t cursor = prefix[chunk];
  for (std::uint64_t walk = start; walk < stop; ++walk) {
    const std::uint64_t position = stop - 1ULL - (walk - start);
    const std::uint64_t flags = flag_bytes[position];""", 1)),
        # The exclusive prefix must seat each chunk exactly.
        ("compaction prefix drift",
         source.replace("  std::uint64_t cursor = prefix[chunk];",
                        "  std::uint64_t cursor = prefix[chunk] + (chunk == 1u ? 1ULL : 0ULL);", 1)),
        ("compaction drops a flagged entry",
         source.replace("    if (flags == 0ULL) continue;",
                        "    if (flags == 0ULL || position == 100ULL) continue;", 1)),
        ("compaction duplicates a canonical index",
         source.replace("    entries[cursor] = (flags << 32) | position;",
                        "    entries[cursor] = (flags << 32) | ((position == 200ULL) ? 100ULL : position);", 1)),
        ("compacted entry carries an illegal flag word",
         source.replace("    flag_bytes[position] = static_cast<std::uint8_t>(flags);",
                        "    flag_bytes[position] = static_cast<std::uint8_t>(position == 100ULL ? 5u : flags);", 1)),
        # The hard cap must fail closed rather than truncate or overrun.
        ("compaction hard cap exceeded",
         source.replace("constexpr std::uint64_t kMaxCompactedEntries = 1ULL << 14;",
                        "constexpr std::uint64_t kMaxCompactedEntries = 4ULL;", 1)),
        ("compaction chunk size drift",
         source.replace("constexpr std::uint64_t kCompactionChunkSize = 4096;",
                        "constexpr std::uint64_t kCompactionChunkSize = 2048;", 1)),
        # --- coefficients ----------------------------------------------------
        # --- the declared payload contract (B1) ------------------------------
        # A fractional C ties a sector register, which the energy stage never
        # emits; run_core must refuse BEFORE allocating, not half-support it.
        ("payload contract: fractional C",
         source.replace("  value.c_value = 2.0;", "  value.c_value = 2.5;", 1)),
        ("payload contract: unsorted membership",
         source.replace("{0u, 6u, 11u, 15u, 19u}, {1u, 5u, 10u, 14u, 18u}",
                        "{0u, 6u, 15u, 11u, 19u}, {1u, 5u, 10u, 14u, 18u}", 1)),
        # --- the generic path really is control-free (B2/B3) -----------------
        ("generic run reuses the controlled path",
         source.replace("ok = ok && run_core(host_payload, host_rows, kRowCount, nullptr, nullptr, &generic);",
                        "ok = ok && run_core(host_payload, host_rows, kRowCount, "
                        "host_control_positions, host_control_offsets, &generic);", 1)),
        # --- instance-specific lambda_ref ------------------------------------
        # If the comparator ignored the payload field, changing it would be
        # invisible; detection proves lambda_ref reaches every D015 comparison.
        ("payload lambda_ref drift",
         source.replace("  value.lambda_ref = kSyntheticLambdaRef;",
                        "  value.lambda_ref = 0x1p+3;", 1)),
        ("payload lambda_ref non-positive",
         source.replace("  value.lambda_ref = kSyntheticLambdaRef;",
                        "  value.lambda_ref = 0.0;", 1)),
        # --- the returned interface ------------------------------------------
        ("returned minimum withheld",
         source.replace("      result->minimum = minimum;",
                        "      result->minimum = 0.0;", 1)),
        ("returned entries withheld",
         source.replace("""      for (std::uint64_t slot = 0; slot < produced; ++slot) {
        result->entries[slot] = host_entries[slot];
      }""",
                        "      // entries deliberately not returned", 1)),
        ("returned entries truncated",
         source.replace("      for (std::uint64_t slot = 0; slot < produced; ++slot) {\n"
                        "        result->entries[slot] = host_entries[slot];",
                        "      for (std::uint64_t slot = 0; slot + 1ULL < produced; ++slot) {\n"
                        "        result->entries[slot] = host_entries[slot];", 1)),
        ("coefficient field swap",
         source.replace("    value.sector_linear = 0x1.4p-3; value.sector_quadratic = 0x1p-5;",
                        "    value.sector_linear = 0x1p-5; value.sector_quadratic = 0x1.4p-3;", 1)),
        # A one-row call must not silently process or return the second slot.
        ("one-row tail executes an unrequested second row",
         source.replace("  for (std::uint32_t row = 0; ok && row < row_count; ++row) {",
                        "  for (std::uint32_t row = 0; ok && row < kRowCount; ++row) {", 1)),
    )


def check_compile_contract(source: str) -> None:
    """The pre-nvcc numerical contract, enforced statically -- nvcc is not run."""
    require(tuple(engine.CUDA_COMPILE_FLAGS)
            == ("--fmad=false", "--ftz=false", "--prec-div=true", "--prec-sqrt=true"),
            "the declared CUDA numerical flags drifted")
    require(tuple(engine.HOST_COMPILE_FLAGS) == ("-ffp-contract=off", "-fno-fast-math"),
            "the declared host numerical flags drifted")
    for flag in tuple(engine.CUDA_COMPILE_FLAGS) + tuple(engine.HOST_COMPILE_FLAGS):
        require(flag in source, f"the CUDA source does not document {flag}")
    require("NOT a claim of real CUDA numerical qualification" in source,
            "the source must not imply CUDA numerical qualification has been done")


def main() -> int:
    source = SOURCE.read_text(encoding="utf-8")
    check_compile_contract(source)
    domain = engine.build_domain(engine.synthetic_payload())
    scans = {(row, encoding): engine.scan(domain, row, encoding)
             for row in engine.ROW_NAMES for encoding in engine.ENCODINGS}
    # The control-free generic path, computed once and reused for every mutation.
    generic = {(row, encoding): engine.scan(domain, engine.coefficient_row(row), encoding,
                                            control={})
               for row in engine.ROW_NAMES for encoding in engine.ENCODINGS}

    # Optimization must not change a single reported value, and that is proved
    # rather than assumed: the pinned baseline is built at both -O0 and -O2 and
    # the two runs must agree byte for byte.
    started = time.time()
    unoptimized = run(source, warning_free=True, optimization="-O0")
    baseline = run(source, warning_free=True, optimization="-O2")
    baseline_seconds = time.time() - started
    require(unoptimized is not None and baseline is not None, "the baseline failed to compile")
    require(unoptimized.returncode == baseline.returncode and unoptimized.stdout == baseline.stdout,
            "the baseline differs between -O0 and -O2")
    require(baseline.returncode == 0,
            "baseline core-stream engine self-test failed: " + baseline.stderr[-600:])
    report = engine.validate_self_test_report(payload(baseline), scans, domain, generic)
    require(report["device_name"] == "host-emulation-fake-gpu", "unexpected host-emulation device")
    require(report["scientific_outputs"] == "intentionally absent", "scientific outputs appeared")

    # The synthetic control levers must actually be load-bearing, or the
    # mutation sweep below would prove nothing.
    for row in engine.ROW_NAMES:
        for encoding in engine.ENCODINGS:
            data = scans[(row, encoding)]
            key = f"{row}_{encoding}"
            require(data["minimum_index"] != data["natural_index"],
                    f"{key}: the controls do not move the first-seen winner")
            require(report[f"natural_energy_checksum_{key}"]
                    != report[f"controlled_energy_checksum_{key}"],
                    f"{key}: the natural and controlled checksums coincide")
            counts = tuple(report[f"count_c_h_{c_h}_{key}"] for c_h in (1024, 2048, 4096))
            require(counts[0] < counts[1] < counts[2],
                    f"{key}: the c_H ladder is not strictly separating: {counts}")
            require(report["reconstruction_mismatches"] == 0,
                    "the returned minima/entries do not reconstruct their own checksums")
            require(report[f"generic_compacted_count_{key}"] >= 1,
                    f"{key}: the generic path compacted nothing")
            require(report[f"generic_minimum_checksum_{key}"]
                    != report[f"minimum_checksum_{key}"],
                    f"{key}: the generic and controlled minima coincide, so the "
                    "control-free path is not load-bearing")
            require(report[f"compacted_count_{key}"] > 1,
                    f"{key}: compaction retains too little to be load-bearing")
            require(report[f"compacted_count_{key}"] <= engine.MAX_COMPACTED_ENTRIES,
                    f"{key}: compaction exceeded the declared cap")
            entries = list(data["compacted_entries"])
            spread = {int(entry & 0xFFFFFFFF) // engine.COMPACTION_CHUNK_SIZE for entry in entries}
            require(len(spread) >= 3,
                    f"{key}: flagged entries occupy only {len(spread)} compaction chunk(s), "
                    "so the per-chunk prefix is not load-bearing")

    detected: dict[str, str] = {}
    table = mutations(source)
    for label, mutated in table:
        require(mutated != source, f"mutation anchor missing: {label}")
        result = run(mutated, allow_compile_failure=True)
        if result is None:
            detected[label] = "compiler"
            continue
        channels = []
        if result.returncode != 0:
            channels.append("self-test")
        if result.stdout.strip():
            try:
                engine.validate_self_test_report(payload(result), scans, domain, generic)
            except engine.CoreStreamEngineError:
                channels.append("python-reference")
            else:
                raise FixtureError(f"mutation escaped the Python reference: {label}")
        require(channels, f"mutation produced neither a failure nor a report: {label}")
        detected[label] = "+".join(channels)
    require(len(detected) == len(table), "not every core-stream mutation was detected")
    for label, channel in detected.items():
        print(f"  detected via {channel}: {label}")
    print(f"  compile contract enforced: {' '.join(engine.HOST_COMPILE_FLAGS)} "
          f"(host) / {' '.join(engine.CUDA_COMPILE_FLAGS)} (contracted for nvcc, not run)")
    print(f"PASS Stage-2 core-stream engine host emulation; baseline ({baseline_seconds:.1f}s, "
          f"{report['lift_total']} lifts) matches Python at -O0 and -O2 and "
          f"{len(detected)}/{len(table)} corruptions detected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

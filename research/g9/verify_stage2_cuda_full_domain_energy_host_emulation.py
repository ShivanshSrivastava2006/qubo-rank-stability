#!/usr/bin/env python3
"""Host-emulate the full-domain energy self-test and its corruption mutations.

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
from research.g9.cuda_qualification import stage2_cuda_full_domain_energy as energy  # noqa: E402

SOURCE = ROOT / "research/g9/cuda_qualification/stage2_cuda_full_domain_energy.cu"
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
    with tempfile.TemporaryDirectory(prefix="g9-energy-host-") as temporary:
        directory = Path(temporary)
        candidate, executable = directory / "source.cu", directory / "self_test"
        candidate.write_text(source_text, encoding="utf-8")
        compiled = subprocess.run(
            [compiler, "-x", "c++", "-std=c++17", optimization, "-Wall", "-Wextra",
             "-Wno-unknown-pragmas", *energy.HOST_COMPILE_FLAGS, "-I", str(STUB),
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
         source.replace("  const double scale = kLambdaRef + maximum;",
                        "  const double scale = kLambdaRef;", 1)),
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
    )


def check_compile_contract(source: str) -> None:
    """The pre-nvcc numerical contract, enforced statically -- nvcc is not run."""
    require(tuple(energy.CUDA_COMPILE_FLAGS)
            == ("--fmad=false", "--ftz=false", "--prec-div=true", "--prec-sqrt=true"),
            "the declared CUDA numerical flags drifted")
    require(tuple(energy.HOST_COMPILE_FLAGS) == ("-ffp-contract=off", "-fno-fast-math"),
            "the declared host numerical flags drifted")
    for flag in tuple(energy.CUDA_COMPILE_FLAGS) + tuple(energy.HOST_COMPILE_FLAGS):
        require(flag in source, f"the CUDA source does not document {flag}")
    require("NOT a claim of real CUDA numerical qualification" in source,
            "the source must not imply CUDA numerical qualification has been done")


def main() -> int:
    source = SOURCE.read_text(encoding="utf-8")
    check_compile_contract(source)
    domain = energy.build_domain(energy.synthetic_payload())
    scans = {(row, encoding): energy.scan(domain, row, encoding)
             for row in energy.ROW_NAMES for encoding in energy.ENCODINGS}

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
            "baseline full-domain energy self-test failed: " + baseline.stderr[-600:])
    report = energy.validate_self_test_report(payload(baseline), scans, domain)
    require(report["device_name"] == "host-emulation-fake-gpu", "unexpected host-emulation device")
    require(report["scientific_outputs"] == "intentionally absent", "scientific outputs appeared")

    # The synthetic control levers must actually be load-bearing, or the
    # mutation sweep below would prove nothing.
    for row in energy.ROW_NAMES:
        for encoding in energy.ENCODINGS:
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
                energy.validate_self_test_report(payload(result), scans, domain)
            except energy.FullDomainEnergyError:
                channels.append("python-reference")
            else:
                raise FixtureError(f"mutation escaped the Python reference: {label}")
        require(channels, f"mutation produced neither a failure nor a report: {label}")
        detected[label] = "+".join(channels)
    require(len(detected) == len(table), "not every energy mutation was detected")
    for label, channel in detected.items():
        print(f"  detected via {channel}: {label}")
    print(f"  compile contract enforced: {' '.join(energy.HOST_COMPILE_FLAGS)} "
          f"(host) / {' '.join(energy.CUDA_COMPILE_FLAGS)} (contracted for nvcc, not run)")
    print(f"PASS Stage-2 full-domain energy host emulation; baseline ({baseline_seconds:.1f}s, "
          f"{report['lift_total']} lifts) matches Python at -O0 and -O2 and "
          f"{len(detected)}/{len(table)} corruptions detected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Host-emulate the full-domain cache self-test and its corruption mutations.

Compiles the pinned .cu with g++ against the existing CUDA host stub, so no
nvcc, GPU, or Kaggle session is involved.  Each build and run happens inside a
temporary directory that is removed on exit.
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
from research.g9.cuda_qualification import stage2_cuda_full_domain_cache as cache  # noqa: E402

SOURCE = ROOT / "research/g9/cuda_qualification/stage2_cuda_full_domain_cache.cu"
STUB = ROOT / "research/g6/cuda_qualification/host_emulation_stub"


class FixtureError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise FixtureError(message)


def run(source_text: str, *, warning_free: bool = False, allow_compile_failure: bool = False,
        optimization: str = "-O0") -> subprocess.CompletedProcess[str] | None:
    """Compile and run one source; ``None`` means it did not compile.

    ``warning_free`` applies to the pinned baseline only — a deliberately
    corrupted source may legitimately warn.  ``allow_compile_failure`` is used
    for mutations: refusing to compile is a valid way for a corruption to be
    rejected (the 32-bit capacity downgrade, for instance, makes the probe
    table's 64-bit constants a narrowing error).
    """
    compiler = shutil.which("g++")
    require(compiler is not None, "g++ is unavailable for host emulation")
    with tempfile.TemporaryDirectory(prefix="g9-full-domain-host-") as temporary:
        directory = Path(temporary)
        candidate, executable = directory / "source.cu", directory / "self_test"
        candidate.write_text(source_text, encoding="utf-8")
        compiled = subprocess.run(
            [compiler, "-x", "c++", "-std=c++17", optimization, "-Wall", "-Wextra", "-Wno-unknown-pragmas",
             "-ffp-contract=off", "-I", str(STUB), str(candidate), "-o", str(executable)],
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
                              capture_output=True, check=False, timeout=600)


def payload(result: subprocess.CompletedProcess[str]) -> dict:
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise FixtureError("invalid JSON from host self-test: " + result.stderr[-500:]) from exc


def main() -> int:
    source = SOURCE.read_text(encoding="utf-8")
    built = cache.build_cache(cache.synthetic_payload())
    # Mutations are swept at -O0, as in the sibling components.  Optimization
    # must not change a single reported value either, and that is proved rather
    # than assumed: the pinned baseline is built at both -O0 and -O2 and the
    # two runs must agree byte for byte.
    started = time.time()
    unoptimized = run(source, warning_free=True, optimization="-O0")
    baseline = run(source, warning_free=True, optimization="-O2")
    baseline_seconds = time.time() - started
    require(unoptimized is not None and baseline is not None, "the baseline failed to compile")
    require(unoptimized.returncode == baseline.returncode and unoptimized.stdout == baseline.stdout,
            "the baseline differs between -O0 and -O2")
    require(baseline.returncode == 0, "baseline full-domain self-test failed: " + baseline.stderr[-600:])
    report = cache.validate_self_test_report(payload(baseline), built)
    require(report["device_name"] == "host-emulation-fake-gpu", "unexpected host-emulation device")
    require(report["lift_total"] > report["state_count"], "baseline retained no tied lift")
    require("packed_lifts" not in baseline.stdout and "offsets" not in baseline.stdout,
            "self-test leaked a cache entry")

    high_index = cache.STATE_COUNT - 1
    mutations = (
        ("canonical index reversal",
         source.replace("return ((index >> (kDecodedWidth - 1u - asset)) & 1u) ? 1.0 : 0.0;",
                        "return ((index >> asset) & 1u) ? 1.0 : 0.0;", 1)),
        ("contiguous-sector fallback",
         source.replace("const std::uint32_t asset = payload->membership[sector][member];",
                        "const std::uint32_t asset = sector * kSectorSize + member;", 1)),
        ("membership content drift",
         source.replace("{0u, 6u, 11u, 15u, 19u}, {1u, 5u, 10u, 14u, 18u}",
                        "{0u, 6u, 11u, 15u, 18u}, {1u, 5u, 10u, 14u, 19u}", 1)),
        ("sector register layout drift",
         source.replace("return reg < kSectorCount ? (reg * kSectorSlackBits) : (kSectorCount * kSectorSlackBits);",
                        "return reg < kSectorCount ? reg : (kSectorCount * kSectorSlackBits);", 1)),
        ("budget register width drift",
         source.replace("constexpr std::uint32_t kBudgetSlackBits = 11;",
                        "constexpr std::uint32_t kBudgetSlackBits = 10;", 1)),
        ("tied minimizer loss",
         source.replace("  values[0] = low;\n  values[1] = high;\n  return 2u;",
                        "  values[0] = low;\n  return 1u;", 1)),
        ("lift product-order drift",
         source.replace("            masks[cursor] = (values[0][a] << register_offset(0)) | (values[1][b] << register_offset(1)) |",
                        "            masks[cursor] = (values[0][a] << register_offset(1)) | (values[1][b] << register_offset(0)) |", 1)),
        ("duplicate packed lift",
         source.replace("            masks[cursor] = (values[0][a] << register_offset(0))",
                        "            masks[cursor] = (values[4][0] << register_offset(4)) | (values[0][a] << register_offset(0))", 1)),
        # One boundary of the exclusive prefix is shifted, so two adjacent
        # decoded ranges no longer match their multiplicities.
        ("offset-prefix drift",
         source.replace("      g_offsets[index + 1ULL] = lift_total;",
                        "      g_offsets[index + 1ULL] = lift_total + (index == 7ULL ? 1ULL : 0ULL);", 1)),
        ("32-bit capacity downgrade",
         source.replace("using CapacityInt = std::uint64_t;", "using CapacityInt = std::uint32_t;", 1)),
        ("simulated capacity overflow",
         source.replace("constexpr std::uint32_t kMaxLiftsPerState = 1u << kRegisterCount;",
                        "constexpr std::uint32_t kMaxLiftsPerState = 1u;", 1)),
        # A finite but extreme residual: the squared penalty overflows, so the
        # device must fail through the invalid-residual path rather than
        # narrowing 1e200 to long long or reporting a clamped endpoint.
        ("finite extreme budget residual",
         source.replace("  value.b = 40.0;", "  value.b = 1e200;", 1)),
        ("non-finite sector residual",
         source.replace("  value.c_value = 2.0;", "  value.c_value = 0.0 / 0.0;", 1)),
        ("non-finite budget residual",
         source.replace("  value.b = 40.0;", "  value.b = 0.0 / 0.0;", 1)),
        # Only the highest decoded index is touched: detection proves the whole
        # 2^20 domain is genuinely scanned and digested.
        (f"high decoded index {high_index} corruption",
         source.replace("            cursor = cursor + 1u;",
                        f"            if (index == {high_index}u) masks[cursor] ^= 1u;\n"
                        "            cursor = cursor + 1u;", 1)),
    )
    detected: dict[str, str] = {}
    for label, mutated in mutations:
        require(mutated != source, f"mutation anchor missing: {label}")
        result = run(mutated, allow_compile_failure=True)
        if result is None:
            # The corruption is rejected outright by the type system.
            detected[label] = "compiler"
            continue
        channels = []
        if result.returncode != 0:
            channels.append("self-test")
        if result.stdout.strip():
            try:
                cache.validate_self_test_report(payload(result), built)
            except cache.FullDomainCacheError:
                channels.append("python-reference")
            else:
                raise FixtureError(f"mutation escaped the Python reference: {label}")
        require(channels, f"mutation produced neither a failure nor a report: {label}")
        detected[label] = "+".join(channels)
    require(len(detected) == len(mutations), "not every full-domain mutation was detected")
    for label, channel in detected.items():
        print(f"  detected via {channel}: {label}")
    print(f"PASS Stage-2 full-domain cache host emulation; baseline ({baseline_seconds:.1f}s, "
          f"{report['lift_total']} lifts) matches Python and {len(detected)}/{len(mutations)} corruptions detected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

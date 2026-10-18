#!/usr/bin/env python3
"""Compile/run the generic CUDA self-test serially with the reviewed host stub."""
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
from research.g9.cuda_qualification import stage2_cuda_generic_engine as engine  # noqa: E402

SOURCE = ROOT / engine.CUDA_SOURCE_REL
STUB = ROOT / "research/g6/cuda_qualification/host_emulation_stub"


class FixtureError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise FixtureError(message)


def compile_and_run(source_text: str) -> subprocess.CompletedProcess[str]:
    compiler = shutil.which("g++")
    require(compiler is not None, "g++ is unavailable for host emulation")
    with tempfile.TemporaryDirectory(prefix="g9-cuda-generic-host-") as temporary:
        directory = Path(temporary)
        candidate = directory / "source.cu"
        executable = directory / "self_test"
        candidate.write_text(source_text, encoding="utf-8")
        compiled = subprocess.run(
            [compiler, "-x", "c++", "-std=c++17", "-O0", "-Wall", "-Wextra", "-Wno-unknown-pragmas",
             "-ffp-contract=off", "-I", str(STUB), str(candidate), "-o", str(executable)],
            cwd=ROOT, text=True, capture_output=True, check=False,
        )
        require(compiled.returncode == 0, "host-emulation compilation failed: " + compiled.stderr[-1000:])
        return subprocess.run([str(executable), "--self-test"], cwd=ROOT, text=True, capture_output=True, check=False)


def report(result: subprocess.CompletedProcess[str]) -> dict:
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise FixtureError("host-emulation emitted invalid JSON: " + result.stderr[-500:]) from exc


def main() -> int:
    source = SOURCE.read_text(encoding="utf-8")
    baseline = compile_and_run(source)
    require(baseline.returncode == 0, "baseline self-test failed")
    payload = report(baseline)
    engine.validate_self_test_report(payload)
    require(payload["device_name"] == "host-emulation-fake-gpu", "unexpected host-emulation device")
    reordered = source.replace(
        "double h = term->f_value;\n  h = h + card_penalty;\n  for (std::uint32_t sector = 0; sector < 4; ++sector) {",
        "double h = term->f_value;\n  for (std::uint32_t sector = 0; sector < 4; ++sector) {", 1,
    ).replace(
        "  const double budget_linear = coeff->budget_linear * term->h_budget;",
        "  h = h + card_penalty;\n  const double budget_linear = coeff->budget_linear * term->h_budget;", 1,
    )
    mutations = (
        ("accumulation order", reordered, False),
        ("minimum comparator", source.replace("if (candidate < best)", "if (candidate > best)", 1), False),
        ("first-seen equality", source.replace("if (candidate < best)", "if (candidate <= best)", 1), False),
        ("reverse canonical scan", source.replace("for (std::uint32_t state = 1; state < kStates; ++state)", "for (std::uint32_t state = kStates - 1u; state > 0u; --state)", 1), False),
        ("D015 scale", source.replace("const double maximum = y_magnitude > prime_magnitude ? y_magnitude : prime_magnitude;", "const double maximum = 0.0;", 1), False),
        ("D015 c_H order", source.replace("return index == 0 ? 1024.0 : (index == 1 ? 2048.0 : 4096.0);", "return index == 0 ? 4096.0 : (index == 1 ? 2048.0 : 1024.0);", 1), False),
        ("slack coefficient", source.replace("coeff->sector_slack * term->sector_slack_square[sector]", "coeff->sector_linear * term->sector_slack_square[sector]", 1), False),
        ("nonfinite detection", source.replace("out.f_value = static_cast<double>(signed_state) / 251.0;", "out.f_value = 0.0 / 0.0;", 1), True),
    )
    detected = 0
    for label, mutated, expects_process_failure in mutations:
        require(mutated != source, f"mutation anchor missing: {label}")
        result = compile_and_run(mutated)
        if expects_process_failure:
            require(result.returncode != 0, f"{label} mutation was not refused")
        else:
            require(result.returncode == 0, f"{label} mutation failed before comparison")
        try:
            engine.validate_self_test_report(report(result))
        except engine.GenericCUDAEngineError:
            detected += 1
        else:
            raise FixtureError(f"{label} mutation escaped the Python reference")
    require(detected == len(mutations), "not every corruption mutation was detected")
    print("PASS Stage-2 generic CUDA host emulation; baseline matches Python and 8/8 corruptions detected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

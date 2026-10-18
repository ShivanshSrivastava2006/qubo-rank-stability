"""Synthetic-only host harness for the generic Stage-2 CUDA numerical core.

The paired ``.cu`` program has one supported action: a fixed artificial
self-test.  It accepts no Stage-2 input and writes no artifact.  This module
replays the same binary64 operations in Python, verifies the reported
checksums, and defines the strict future invocation boundary.  It is not a
producer and it does not qualify a Stage-2 instance or platform by itself.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[3]
AMENDMENT_REL = "research/decisions/GATE_9_STAGE2_KAGGLE_CUDA_AMENDMENT_DRAFT.md"
APPROVAL_REL = "research/decisions/GATE_9_STAGE2_KAGGLE_CUDA_AMENDMENT_APPROVAL.md"
CUDA_SOURCE_REL = "research/g9/cuda_qualification/stage2_cuda_generic_engine.cu"
SELF_REL = "research/g9/cuda_qualification/stage2_cuda_generic_engine.py"
RUNNER_REL = "research/g9/run_stage2_cuda_generic_engine.py"
AMENDMENT_SHA256 = "589fdc29d71cd5f70c0734e927d109dc00b389b40cc7c485e56a655f41fd57cf"
APPROVAL_SHA256 = "a2b0747a5db2721f046420c120848e6bb4ea82505b2f5a16c4f8da64671377d4"
SCHEMA_PLAN = "decisions_os/g9_cuda_generic_engine_plan/v1"
SCHEMA_SELF_TEST = "decisions_os/g9_cuda_generic_self_test/v1"
STATE_COUNT, POINT_COUNT, ENCODING_COUNT, CH_COUNT = 257, 4, 2, 3
EPSILON, LAMBDA_REF = float.fromhex("0x1p-52"), float.fromhex("0x1p-5")
FNV_OFFSET, FNV_PRIME = 1469598103934665603, 1099511628211
MASK64 = (1 << 64) - 1
COMPILE_FLAGS = (
    "-std=c++17", "-O0", "--fmad=false", "--ftz=false", "--prec-div=true", "--prec-sqrt=true",
    "-Xcompiler", "-O0", "-Xcompiler", "-ffp-contract=off", "-Xcompiler", "-fno-fast-math",
)


class GenericCUDAEngineError(RuntimeError):
    """Typed refusal for an unavailable or malformed generic self-test."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise GenericCUDAEngineError(message)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def content_sha256(value: Mapping[str, Any]) -> str:
    body = dict(value)
    body.pop("content_sha256", None)
    return hashlib.sha256(canonical_bytes(body)).hexdigest()


def require_authorities() -> dict[str, str]:
    observed = {AMENDMENT_REL: _sha(ROOT / AMENDMENT_REL), APPROVAL_REL: _sha(ROOT / APPROVAL_REL)}
    _require(observed[AMENDMENT_REL] == AMENDMENT_SHA256, "approved CUDA amendment drift")
    _require(observed[APPROVAL_REL] == APPROVAL_SHA256, "CUDA amendment approval record drift")
    return observed


def current_source_hashes() -> dict[str, str]:
    return {relative: _sha(ROOT / relative) for relative in (CUDA_SOURCE_REL, SELF_REL, RUNNER_REL)}


def _word(value: float) -> int:
    return struct.unpack("<Q", struct.pack("<d", value))[0]


def _fnv(state: int, word: int) -> int:
    return ((state ^ word) * FNV_PRIME) & MASK64


def _terms(state: int) -> dict[str, object]:
    signed_state = (state * 37) % 257 - 128
    f_value = signed_state / 251.0
    card = float(state % 9) - 4.0
    h_sector, sector_square, sector_slack_square = [], [], []
    for sector in range(4):
        residual = ((state * (sector + 3) + 5) % 17) / 13.0 - 1.0
        h_sector.append(residual)
        sector_square.append(residual * residual)
        slack_delta = residual - float((state + sector) % 3)
        sector_slack_square.append(slack_delta * slack_delta)
    h_budget = ((state * 11 + 7) % 31) / 7.0 - 3.0
    budget_delta = h_budget - float(state % 7)
    return {"f": f_value, "card_square": card * card, "h_sector": h_sector, "sector_square": sector_square,
            "h_budget": h_budget, "budget_square": h_budget * h_budget,
            "sector_slack_square": sector_slack_square, "budget_slack_square": budget_delta * budget_delta}


def _coefficients() -> tuple[tuple[float, ...], ...]:
    return tuple(tuple(float.fromhex(item) for item in row) for row in (
        ("0x1.0000000000000p-3", "0x1.0000000000000p-4", "0x1.8000000000000p-5", "0x1.4000000000000p-3", "0x1.0000000000000p-5", "0x1.0000000000000p-4", "0x1.0000000000000p-6"),
        ("0x1.4000000000000p-3", "0x1.8000000000000p-4", "0x1.0000000000000p-5", "0x1.0000000000000p-3", "0x1.8000000000000p-5", "0x1.4000000000000p-4", "0x1.0000000000000p-7"),
        ("0x1.8000000000000p-3", "0x1.0000000000000p-5", "0x1.4000000000000p-5", "0x1.8000000000000p-3", "0x1.0000000000000p-6", "0x1.8000000000000p-4", "0x1.4000000000000p-7"),
        ("0x1.0000000000000p-2", "0x1.4000000000000p-4", "0x1.8000000000000p-5", "0x1.4000000000000p-3", "0x1.4000000000000p-5", "0x1.0000000000000p-4", "0x1.8000000000000p-7"),
    ))


def _unbalanced(term: Mapping[str, object], coeff: tuple[float, ...]) -> float:
    alpha, _, _, sector_linear, sector_quadratic, budget_linear, budget_quadratic = coeff
    h = float(term["f"])
    h = h + alpha * float(term["card_square"])
    for residual, square in zip(term["h_sector"], term["sector_square"]):
        h = h + ((-(sector_linear * float(residual))) + sector_quadratic * float(square))
    return h + ((-(budget_linear * float(term["h_budget"]))) + budget_quadratic * float(term["budget_square"]))


def _slack(term: Mapping[str, object], coeff: tuple[float, ...]) -> float:
    alpha, sector_slack, budget_slack, _, _, _, _ = coeff
    h = float(term["f"])
    h = h + alpha * float(term["card_square"])
    for square in term["sector_slack_square"]:
        h = h + sector_slack * float(square)
    return h + budget_slack * float(term["budget_slack_square"])


def _frozen_tie(y: float, y_prime: float, c_h: float) -> bool:
    difference = y - y_prime
    gap = abs(difference)
    maximum = max(abs(y), abs(y_prime))
    scale = LAMBDA_REF + maximum
    tolerance = (c_h * EPSILON) * scale
    return gap <= tolerance


def _control_energy(raw: float, state: int, point: int, encoding: int) -> float:
    pair = point * ENCODING_COUNT + encoding
    anchor = 17 + point * 31 + encoding * 7
    base = -256.0 - float(pair) * 16.0
    if state in (anchor, anchor + 1):
        return base
    if state == anchor + 2:
        return base + float.fromhex("0x1p-35")
    if state == anchor + 3:
        return base + float.fromhex("0x1.8p-34")
    if state == anchor + 4:
        return base + float.fromhex("0x1.8p-33")
    return raw


def expected_self_test() -> dict[str, object]:
    energy_words: list[int] = []
    minima: list[tuple[int, int]] = []
    flags: list[int] = []
    tie_counts: list[list[int]] = []
    for point, coeff in enumerate(_coefficients()):
        for encoding, evaluator in enumerate((_unbalanced, _slack)):
            words = [_word(_control_energy(evaluator(_terms(state), coeff), state, point, encoding)) for state in range(STATE_COUNT)]
            energy_words.extend(words)
            minimum_index = 0
            minimum = struct.unpack("<d", struct.pack("<Q", words[0]))[0]
            for state, word in enumerate(words[1:], 1):
                candidate = struct.unpack("<d", struct.pack("<Q", word))[0]
                if candidate < minimum:
                    minimum, minimum_index = candidate, state
            minima.append((_word(minimum), minimum_index))
            for word in words:
                energy = struct.unpack("<d", struct.pack("<Q", word))[0]
                bits = 0
                for index, c_h in enumerate((1024.0, 2048.0, 4096.0)):
                    if _frozen_tie(energy, minimum, c_h):
                        bits |= 1 << index
                flags.append(bits)
            tie_counts.append([sum(1 for bits in flags[-STATE_COUNT:] if bits & (1 << index)) for index in range(CH_COUNT)])
    energy_checksum = FNV_OFFSET
    flags_checksum = FNV_OFFSET
    for word, flag in zip(energy_words, flags):
        energy_checksum = _fnv(energy_checksum, word)
        flags_checksum = _fnv(flags_checksum, flag)
    minimum_checksum = FNV_OFFSET
    for word, index in minima:
        minimum_checksum = _fnv(minimum_checksum, word)
        minimum_checksum = _fnv(minimum_checksum, index)
    return {"schema": SCHEMA_SELF_TEST, "state_count": STATE_COUNT, "point_count": POINT_COUNT,
            "energy_checksum": f"{energy_checksum:016x}", "minimum_checksum": f"{minimum_checksum:016x}",
            "flags_checksum": f"{flags_checksum:016x}", "tie_counts": tie_counts, "nonfinite_energies": 0,
            "scientific_outputs": "intentionally absent", "verdict": "pass"}


def validate_self_test_report(payload: object) -> dict[str, object]:
    _require(isinstance(payload, dict) and set(payload) == {"schema", "device_index", "device_name", "state_count", "point_count", "energy_checksum", "minimum_checksum", "flags_checksum", "tie_counts", "nonfinite_energies", "scientific_outputs", "verdict"},
             "generic CUDA report has wrong key set")
    _require(type(payload["device_index"]) is int and payload["device_index"] >= 0 and type(payload["device_name"]) is str and payload["device_name"],
             "generic CUDA device report malformed")
    _require(type(payload["state_count"]) is int and type(payload["point_count"]) is int
             and type(payload["nonfinite_energies"]) is int,
             "generic CUDA integer field has wrong type")
    expected = expected_self_test()
    for key, value in expected.items():
        _require(payload[key] == value, f"generic CUDA self-test mismatch: {key}")
    return dict(payload)


def build_plan() -> dict[str, object]:
    authorities = require_authorities()
    payload: dict[str, object] = {
        "schema": SCHEMA_PLAN, "mode": "plan", "writes": "none", "scientific_outputs": "intentionally absent",
        "stage2_inputs": "intentionally absent", "amendment_authorities": authorities,
        "cuda_source_sha256": _sha(ROOT / CUDA_SOURCE_REL), "self_sha256": current_source_hashes(),
        "compile_flags": list(COMPILE_FLAGS), "synthetic_self_test": expected_self_test(),
    }
    payload["content_sha256"] = content_sha256(payload)
    return payload


def run_qualified_self_test(reviewed: str) -> dict[str, object]:
    """Future non-scientific invocation; explicit owner/environment boundary required."""
    _require(os.environ.get("PYTHONDONTWRITEBYTECODE") == "1", "PYTHONDONTWRITEBYTECODE=1 is required")
    _require(os.environ.get("G9_ALLOW_NONSCIENTIFIC_CUDA_QUALIFICATION") == "1", "separate CUDA qualification permission is required")
    _require(type(reviewed) is str and reviewed.strip(), "non-empty reviewed handoff is required")
    require_authorities()
    nvcc = shutil.which("nvcc")
    _require(nvcc is not None, "nvcc is unavailable")
    with tempfile.TemporaryDirectory(prefix="g9-cuda-generic-self-test-") as temporary:
        executable = Path(temporary) / "generic_self_test"
        command = [nvcc, *COMPILE_FLAGS, str(ROOT / CUDA_SOURCE_REL), "-o", str(executable)]
        compiled = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False, timeout=180)
        _require(compiled.returncode == 0, "nvcc compilation failed")
        executed = subprocess.run([str(executable), "--self-test"], cwd=ROOT, text=True, capture_output=True, check=False, timeout=120)
        _require(executed.returncode == 0, "generic CUDA self-test failed")
        try:
            payload = json.loads(executed.stdout)
        except json.JSONDecodeError as exc:
            raise GenericCUDAEngineError("generic CUDA self-test emitted invalid JSON") from exc
    verified = validate_self_test_report(payload)
    verified["reviewed_handoff"] = reviewed
    verified["source_sha256"] = current_source_hashes()
    return verified

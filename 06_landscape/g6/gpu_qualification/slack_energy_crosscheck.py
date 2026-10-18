"""Bounded GPU-vs-CPU bit-exact cross-check of the slack energy transcript.

This module is a non-production Gate-6 GPU qualification prototype for the
**slack** encoding.  It reuses, by import, the exact raw 20-bit state set and
the four reviewed coefficient points declared by the unbalanced prototype
``energy_crosscheck.py``; for each raw state it obtains the slack auxiliary
register contents only from the canonical exact-minimizer lift
``src.g4.energy.exact_slack_lift``; it evaluates the canonical Python
``src.g4.energy.slack_energy`` on the CPU, evaluates the transcribed HIP
kernel on the discrete ``gfx1201`` device, and reports mismatch counts only.

Raw states for which ``exact_slack_lift`` reports that a residual is not
exactly representable in the slack register (a negative or out-of-range
sector/budget residual) have no exact lift and are excluded; the exclusion is
counted by reason and reported, never silently dropped or replaced by a
clamped or searched auxiliary.

It is not a Gate-6 pass.  It never reads the Gate-5 core-pass output
directory or any Gate-5 shard, never enumerates a slack domain, never computes
a minimum, tie set, X_E, label, rate, aggregate, transition, D013 trigger, or
conclusion, never writes a Gate-5 or Gate-6 result artifact, and never treats
GPU output as a scientific value.

Importing this module has no side effects and writes nothing.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import struct
import subprocess
import sys
import tempfile
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.g6.gpu_qualification import energy_crosscheck as unbalanced  # noqa: E402
from src.g4.energy import (  # noqa: E402
    BUDGET_SLACK_BITS,
    SECTOR_SLACK_BITS,
    SLACK_AUXILIARY_LENGTH,
    exact_slack_lift,
    slack_energy,
)
from src.g4.instance import Instance, load_instance  # noqa: E402
from src.g4.parameters import Coefficients  # noqa: E402


SCHEMA_PLAN = "decisions_os/g6_gpu_slack_energy_crosscheck_plan/v1"
SCHEMA_RUN = "decisions_os/g6_gpu_slack_energy_crosscheck_run/v1"
PURPOSE = (
    "non-production GPU-vs-CPU bit-exact cross-check of the slack energy "
    "transcript at the exact-minimizer lift; GPU output cannot contribute to a Gate-6 artifact"
)
TARGET_ARCHITECTURE = unbalanced.TARGET_ARCHITECTURE
ENCODING = "slack"
REFERENCE = "src.g4.energy.slack_energy"
LIFT_SOURCE = "src.g4.energy.exact_slack_lift"
ASSET_COUNT = unbalanced.ASSET_COUNT
SECTOR_COUNT = unbalanced.SECTOR_COUNT
FULL_MASK = unbalanced.FULL_MASK
AUXILIARY_MASK = (1 << SLACK_AUXILIARY_LENGTH) - 1
BIT_ORDER = unbalanced.BIT_ORDER
AUXILIARY_BIT_ORDER = (
    "auxiliary[t] = (auxiliary_word >> t) & 1 for t in 0..18; tuple layout is "
    "sector j bits d=0,1 at t=2*j+d, then budget bits d=0..10 at t=8+d"
)

INPUT_MAGIC = int.from_bytes(b"G6SLKCX1", "little")
OUTPUT_MAGIC = int.from_bytes(b"G6SLKCY1", "little")
FORMAT_VERSION = 1
COEFFICIENT_ORDER = ("alpha", "sector_slack", "budget_slack")
UNCONSUMED_COEFFICIENTS = ("sector_linear", "sector_quadratic", "budget_linear", "budget_quadratic")

HIP_SOURCE_REL = "research/g6/gpu_qualification/gpu_slack_energy_crosscheck.hip.cpp"
UNBALANCED_LIBRARY_REL = "research/g6/gpu_qualification/energy_crosscheck.py"
INSTANCE_REL = unbalanced.INSTANCE_REL
MANIFEST_REL = unbalanced.MANIFEST_REL
D011_LEDGER_REL = unbalanced.D011_LEDGER_REL
V14_2X_LEDGER_REL = unbalanced.V14_2X_LEDGER_REL

# Exact inputs this prototype consumes.  The shared entries are required to
# equal the unbalanced prototype's pins (checked by the fixtures), so both
# cross-checks bind the same canonical evaluator, instance, and ledgers.  The
# unbalanced library itself is a consumed input because the state set and
# coefficient points are taken from it.
PINNED_INPUTS: dict[str, str] = {
    "src/g4/energy.py": "0ba83c0d33e0d2996352370e26bf0e782002ec49cb79e1628b74a2a74dd5fa11",
    "src/g4/instance.py": "645419374fd30891c2f9ff14d030ed65a032d52d8fe88fab068ad23417b58187",
    "src/g4/parameters.py": "cbbdebbe44b9af0d47fa1d5da7e00303e492d70d21abd696e6bdd5a4cd5be97c",
    "src/g6/ledgers.py": "40ff906fdedb526f7063c7d40aeb778335cf49291a47a948d9f5b31620fc0723",
    INSTANCE_REL: "c4615d9b5066597c4754a1e06d2b3a7906c218965a7d6d530cf54f75c4b5f243",
    MANIFEST_REL: "900b639509074114b4be1149dfaef7d14b6e4ba4a7c1fbcf90d719057a0611ca",
    D011_LEDGER_REL: "00091b631dc92f4a923badf4dd2abda0efc9d82a533f8c61926aa88c521fc06e",
    V14_2X_LEDGER_REL: "3bd7341a7dcf8ca5de007cf2d92ab89e64e95b887349df8e7dede0cc5b0ec3ea",
    UNBALANCED_LIBRARY_REL: "6ceb20042f184ff1d7652024589490d1ccb339930b0be0ecf6a01b30d275f775",
    HIP_SOURCE_REL: "9b4b4d5f7bd681d5d594f64aed84ecfb3de76f09f40dcda9f0e0ebe39cb3e57b",
}
# Files whose hashes are recorded and drift-checked within a run, but which
# cannot pin themselves.
SELF_RELATIVES = (
    "research/g6/gpu_qualification/slack_energy_crosscheck.py",
    "research/g6/run_gpu_slack_energy_crosscheck.py",
)

REQUIRED_COMPILE_FLAGS = unbalanced.REQUIRED_COMPILE_FLAGS
COMPILE_TIMEOUT_SECONDS = unbalanced.COMPILE_TIMEOUT_SECONDS
EXECUTE_TIMEOUT_SECONDS = unbalanced.EXECUTE_TIMEOUT_SECONDS

# The only exception text from exact_slack_lift that means "no exact lift
# exists for this raw state".  Anything else is an unexpected failure.
_NO_LIFT_PATTERN = re.compile(
    r"^(?P<register>sector\[[0-3]\]|budget) residual (?P<value>\S+) is not exactly "
    r"representable in the slack register$"
)


class CrosscheckError(RuntimeError):
    """Raised when the bounded cross-check contract cannot be established."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CrosscheckError(message)


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def current_hashes(relatives: tuple[str, ...] | list[str]) -> dict[str, str]:
    try:
        return unbalanced.current_hashes(relatives)
    except unbalanced.CrosscheckError as exc:
        raise CrosscheckError(str(exc)) from exc


def verify_pinned_inputs(expected: Mapping[str, str] | None = None) -> dict[str, str]:
    """Hash every consumed input and fail closed on any drift from the pins."""
    pins = dict(PINNED_INPUTS if expected is None else expected)
    observed = current_hashes(tuple(pins))
    drifted = sorted(relative for relative in pins if observed[relative] != pins[relative])
    _require(not drifted, "pinned input drift: " + ", ".join(drifted))
    return observed


def load_ledgers() -> dict[str, dict[str, Any]]:
    """Load the two consumed reviewed ledgers exactly as the unbalanced prototype does."""
    try:
        return unbalanced.load_ledgers()
    except unbalanced.CrosscheckError as exc:
        raise CrosscheckError(str(exc)) from exc


def coefficient_points(ledgers: Mapping[str, Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    """The unbalanced prototype's four points, re-labelled for the slack transcript."""
    try:
        shared = unbalanced.coefficient_points(ledgers)
    except unbalanced.CrosscheckError as exc:
        raise CrosscheckError(str(exc)) from exc
    points = []
    for point in shared:
        relabelled = {key: value for key, value in point.items()
                      if key not in ("consumed_by_unbalanced_transcript", "not_consumed")}
        relabelled["consumed_by_slack_transcript"] = list(COEFFICIENT_ORDER)
        relabelled["not_consumed"] = list(UNCONSUMED_COEFFICIENTS)
        _require(isinstance(relabelled["coefficients"], Coefficients), "point lacks validated Coefficients")
        points.append(relabelled)
    return tuple(points)


def declared_states(instance: Instance) -> tuple[tuple[int, ...], dict[str, int]]:
    """The unbalanced prototype's fixed raw 20-bit state set, unchanged."""
    try:
        return unbalanced.declared_states(instance)
    except unbalanced.CrosscheckError as exc:
        raise CrosscheckError(str(exc)) from exc


def mask_to_x(mask: int) -> tuple[int, ...]:
    try:
        return unbalanced.mask_to_x(mask)
    except unbalanced.CrosscheckError as exc:
        raise CrosscheckError(str(exc)) from exc


def auxiliary_to_word(auxiliary: tuple[int, ...]) -> int:
    _require(len(auxiliary) == SLACK_AUXILIARY_LENGTH and all(bit in (0, 1) for bit in auxiliary),
             "auxiliary is not a 19-bit vector")
    word = 0
    for position, bit in enumerate(auxiliary):
        word |= bit << position
    return word


def word_to_auxiliary(word: int) -> tuple[int, ...]:
    _require(isinstance(word, int) and 0 <= word <= AUXILIARY_MASK, "auxiliary word outside 19 bits")
    return tuple((word >> position) & 1 for position in range(SLACK_AUXILIARY_LENGTH))


def lift_states(instance: Instance, states: tuple[int, ...]) -> tuple[tuple[tuple[int, int], ...], dict[str, int]]:
    """Attach the canonical exact-minimizer lift to every raw state that has one.

    Returns the ordered ``(mask, auxiliary_word)`` pairs for lifted states and
    the count of excluded raw states by the register named in
    ``exact_slack_lift``'s refusal.  Any other failure is fail-closed.
    """
    lifted: list[tuple[int, int]] = []
    excluded: dict[str, int] = {}
    for mask in states:
        x = mask_to_x(mask)
        try:
            auxiliary = exact_slack_lift(instance, x)
        except ValueError as exc:
            matched = _NO_LIFT_PATTERN.fullmatch(str(exc))
            _require(matched is not None, f"exact_slack_lift failed unexpectedly for mask 0x{mask:05x}: {exc}")
            register = matched.group("register")
            excluded[register] = excluded.get(register, 0) + 1
            continue
        _require(len(auxiliary) == SLACK_AUXILIARY_LENGTH, "exact lift has the wrong length")
        lifted.append((mask, auxiliary_to_word(auxiliary)))
    _require(len(lifted) + sum(excluded.values()) == len(states), "lift partition does not cover the state set")
    _require(len(lifted) > 0, "no raw state admits an exact slack lift")
    return tuple(lifted), dict(sorted(excluded.items()))


def lifted_digest(lifted: tuple[tuple[int, int], ...]) -> str:
    return _sha256_bytes(b"".join(struct.pack("<QQ", mask, word) for mask, word in lifted))


def float_bits(value: float) -> int:
    return unbalanced.float_bits(value)


def _words(values: list[int]) -> bytes:
    return b"".join(struct.pack("<Q", value) for value in values)


def encode_inputs(instance: Instance, points: tuple[Mapping[str, Any], ...],
                  lifted: tuple[tuple[int, int], ...]) -> bytes:
    """Little-endian uint64 word stream consumed by the HIP program.

    Layout: magic, version, 20, 2, 11, point_count, state_count; mu[20];
    sigma[400] row-major; prices[20]; kappa_risk; float(K); float(C); B;
    for each of 4 sectors: member_count then sorted member indices; for each
    point: alpha, sector_slack, budget_slack; then the state masks; then the
    auxiliary words in the same order.
    """
    _require(len(instance.tickers) == ASSET_COUNT and len(instance.sectors) == SECTOR_COUNT,
             "instance shape is not 20 assets in 4 sectors")
    _require(0 < len(points) <= 64 and 0 < len(lifted) <= (1 << ASSET_COUNT), "bounded contract violated")
    header = [INPUT_MAGIC, FORMAT_VERSION, ASSET_COUNT, SECTOR_SLACK_BITS, BUDGET_SLACK_BITS,
              len(points), len(lifted)]
    scalars = [float_bits(value) for value in instance.mu]
    for row in instance.sigma:
        _require(len(row) == ASSET_COUNT, "Sigma row length mismatch")
        scalars.extend(float_bits(value) for value in row)
    scalars.extend(float_bits(value) for value in instance.prices)
    scalars.extend([float_bits(instance.kappa_risk), float_bits(float(instance.K)),
                    float_bits(float(instance.C)), float_bits(instance.B)])
    sectors: list[int] = []
    covered: list[int] = []
    for members in instance.sectors:
        ordered = sorted(members)
        _require(0 < len(ordered) <= ASSET_COUNT and len(set(ordered)) == len(ordered),
                 "sector members are not distinct")
        sectors.append(len(ordered))
        sectors.extend(ordered)
        covered.extend(ordered)
    _require(sorted(covered) == list(range(ASSET_COUNT)), "sectors do not partition the assets")
    coefficient_words: list[int] = []
    for point in points:
        values = point["coefficients"]
        _require(isinstance(values, Coefficients), "point lacks validated Coefficients")
        coefficient_words.extend(float_bits(getattr(values, name)) for name in COEFFICIENT_ORDER)
    masks: list[int] = []
    auxiliaries: list[int] = []
    for mask, word in lifted:
        _require(isinstance(mask, int) and 0 <= mask <= FULL_MASK, "state outside 20 bits")
        _require(isinstance(word, int) and 0 <= word <= AUXILIARY_MASK, "auxiliary outside 19 bits")
        masks.append(mask)
        auxiliaries.append(word)
    return (_words(header) + _words(scalars) + _words(sectors) + _words(coefficient_words)
            + _words(masks) + _words(auxiliaries))


def decode_output(payload: bytes, point_count: int, state_count: int) -> tuple[int, tuple[int, ...], tuple[int, ...]]:
    """Parse the HIP program's output words: header, device bits, host C++ bits."""
    total = point_count * state_count
    expected_length = 8 * (5 + 2 * total)
    _require(len(payload) == expected_length, "GPU output has unexpected length")
    words = struct.unpack(f"<{5 + 2 * total}Q", payload)
    _require(words[0] == OUTPUT_MAGIC and words[1] == FORMAT_VERSION, "GPU output header mismatch")
    _require(words[2] == point_count and words[3] == state_count, "GPU output counts mismatch")
    device_index = words[4]
    device_bits = tuple(words[5:5 + total])
    host_bits = tuple(words[5 + total:5 + 2 * total])
    return device_index, device_bits, host_bits


def python_reference_bits(instance: Instance, points: tuple[Mapping[str, Any], ...],
                          lifted: tuple[tuple[int, int], ...]) -> tuple[int, ...]:
    """Canonical CPU reference: slack_energy at the exact lift for every (point, state), point-major."""
    output: list[int] = []
    for point in points:
        coefficients = point["coefficients"]
        for mask, word in lifted:
            value = slack_energy(instance, mask_to_x(mask), word_to_auxiliary(word), coefficients)
            _require(math.isfinite(value), "canonical evaluator produced a nonfinite energy")
            output.append(float_bits(value))
    return tuple(output)


def compare_bits(reference: tuple[int, ...], candidate: tuple[int, ...],
                 points: tuple[Mapping[str, Any], ...], lifted: tuple[tuple[int, int], ...],
                 limit: int = 16) -> dict[str, Any]:
    """Count bit-pattern mismatches; identify at most ``limit`` by point and mask only."""
    masks = tuple(mask for mask, _word in lifted)
    try:
        return unbalanced.compare_bits(reference, candidate, points, masks, limit)
    except unbalanced.CrosscheckError as exc:
        raise CrosscheckError(str(exc)) from exc


def compile_command(hipcc: str, source: Path, binary: Path) -> list[str]:
    try:
        command = unbalanced.compile_command(hipcc, source, binary)
    except unbalanced.CrosscheckError as exc:
        raise CrosscheckError(str(exc)) from exc
    _require(all(flag in command for flag in REQUIRED_COMPILE_FLAGS), "compile contract flags are incomplete")
    return command


def _platform_fingerprint() -> dict[str, Any]:
    return {
        "python": sys.version,
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "python_dont_write_bytecode": os.environ.get("PYTHONDONTWRITEBYTECODE", "<unset>"),
    }


def _point_report(point: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in point.items() if key != "coefficients"}


def _bind() -> tuple[Instance, tuple[dict[str, Any], ...], tuple[int, ...], dict[str, int],
                     tuple[tuple[int, int], ...], dict[str, int], dict[str, str]]:
    pins = verify_pinned_inputs()
    ledgers = load_ledgers()
    points = coefficient_points(ledgers)
    instance = load_instance(ROOT / INSTANCE_REL)
    states, families = declared_states(instance)
    lifted, excluded = lift_states(instance, states)
    return instance, points, states, families, lifted, excluded, pins


def _lift_report(states: tuple[int, ...], lifted: tuple[tuple[int, int], ...],
                 excluded: dict[str, int]) -> dict[str, Any]:
    return {
        "source": LIFT_SOURCE,
        "rule": "each auxiliary register holds the exact residual integer; states whose "
                "residual is not exactly representable in the register have no exact lift",
        "raw_state_count": len(states),
        "lifted_count": len(lifted),
        "excluded_count": sum(excluded.values()),
        "excluded_by_register": excluded,
        "auxiliary_bit_order": AUXILIARY_BIT_ORDER,
        "register_widths": {"sector": SECTOR_SLACK_BITS, "budget": BUDGET_SLACK_BITS,
                            "auxiliary_length": SLACK_AUXILIARY_LENGTH},
        "sha256_le_uint64_pairs": lifted_digest(lifted),
        "first_pairs_hex": [{"mask": f"0x{mask:05x}", "auxiliary": f"0x{word:05x}"} for mask, word in lifted[:4]],
    }


def build_plan() -> dict[str, Any]:
    """Validate every binding and describe the run without compiling or evaluating."""
    instance, points, states, families, lifted, excluded, pins = _bind()
    return {
        "schema": SCHEMA_PLAN,
        "mode": "plan",
        "purpose": PURPOSE,
        "encoding": ENCODING,
        "reference": REFERENCE,
        "target_architecture": TARGET_ARCHITECTURE,
        "device_selection": "explicit gcnArchName gfx1201 match; device 0 is not assumed",
        "pinned_inputs": pins,
        "self_sha256": current_hashes(SELF_RELATIVES),
        "coefficient_points": [_point_report(point) for point in points],
        "raw_state_set": {
            "count": len(states),
            "bit_order": BIT_ORDER,
            "families": families,
            "sha256_le_uint64_sequence": unbalanced.states_digest(states),
            "shared_with": UNBALANCED_LIBRARY_REL,
        },
        "lift": _lift_report(states, lifted, excluded),
        "planned_evaluations": len(points) * len(lifted),
        "compile_command_template": compile_command("hipcc", Path("<tmp>/source.hip.cpp"), Path("<tmp>/crosscheck")),
        "hipcc_located": unbalanced._locate_hipcc() is not None,
        "writes": "none",
        "scientific_outputs": "intentionally absent",
    }


def _run_subprocess(command: list[str], cwd: Path, timeout: int, label: str) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        return subprocess.run(command, cwd=cwd, env=environment, text=True, capture_output=True,
                              check=False, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CrosscheckError(f"{label} did not complete: {type(exc).__name__}") from exc


def _architecture_is_target(architecture: object) -> bool:
    return unbalanced._architecture_is_target(architecture)


def run_crosscheck() -> dict[str, Any]:
    """Compile and execute the HIP cross-check in a temporary directory; report counts only."""
    _require(os.environ.get("PYTHONDONTWRITEBYTECODE") == "1", "PYTHONDONTWRITEBYTECODE=1 is required")
    hipcc = unbalanced._locate_hipcc()
    _require(hipcc is not None, "hipcc is unavailable; the cross-check cannot run on this host")
    instance, points, states, families, lifted, excluded, pins_before = _bind()
    self_before = current_hashes(SELF_RELATIVES)
    platform_before = _platform_fingerprint()
    source = ROOT / HIP_SOURCE_REL
    reference = python_reference_bits(instance, points, lifted)
    encoded = encode_inputs(instance, points, lifted)
    temporary_path: Path | None = None
    with tempfile.TemporaryDirectory(prefix="g6-gpu-slack-energy-crosscheck-") as temporary:
        temporary_path = Path(temporary)
        staged_source = temporary_path / "gpu_slack_energy_crosscheck.hip.cpp"
        binary = temporary_path / "crosscheck"
        input_path = temporary_path / "input.words"
        output_path = temporary_path / "output.words"
        staged_source.write_bytes(source.read_bytes())
        _require(_sha256_bytes(staged_source.read_bytes()) == PINNED_INPUTS[HIP_SOURCE_REL],
                 "staged HIP source does not match the pinned source")
        input_path.write_bytes(encoded)
        command = compile_command(hipcc, staged_source, binary)
        compilation = _run_subprocess(command, temporary_path, COMPILE_TIMEOUT_SECONDS, "HIP compilation")
        _require(compilation.returncode == 0,
                 "HIP compilation failed; do not substitute relaxed floating-point flags: "
                 + compilation.stderr[-2000:])
        execution = _run_subprocess([str(binary), str(input_path), str(output_path)], temporary_path,
                                    EXECUTE_TIMEOUT_SECONDS, "HIP execution")
        _require(execution.returncode == 0, "HIP cross-check binary failed: " + execution.stderr[-2000:])
        try:
            device_report = json.loads(execution.stdout)
        except json.JSONDecodeError as exc:
            raise CrosscheckError("HIP cross-check emitted malformed JSON") from exc
        _require(isinstance(device_report, dict) and _architecture_is_target(device_report.get("architecture")),
                 "HIP cross-check ran on an unexpected GPU architecture")
        _require(device_report.get("point_count") == len(points)
                 and device_report.get("state_count") == len(lifted),
                 "HIP cross-check reported unexpected counts")
        device_index, device_bits, host_bits = decode_output(output_path.read_bytes(), len(points), len(lifted))
        _require(device_index == device_report.get("device_index"), "device index disagreement")
    _require(temporary_path is not None and not temporary_path.exists(), "temporary directory was not removed")
    gpu = compare_bits(reference, device_bits, points, lifted)
    host = compare_bits(reference, host_bits, points, lifted)
    pins_after = verify_pinned_inputs()
    _require(pins_after == pins_before, "pinned input drift during the cross-check")
    _require(current_hashes(SELF_RELATIVES) == self_before, "prototype source drift during the cross-check")
    _require(_platform_fingerprint() == platform_before, "platform fingerprint drift during the cross-check")
    verdict = "pass" if gpu["mismatches"] == 0 and host["mismatches"] == 0 else "fail"
    return {
        "schema": SCHEMA_RUN,
        "mode": "run",
        "purpose": PURPOSE,
        "encoding": ENCODING,
        "reference": REFERENCE,
        "target_architecture": TARGET_ARCHITECTURE,
        "platform": platform_before,
        "pinned_inputs": pins_before,
        "pinned_inputs_after_run": pins_after,
        "self_sha256": self_before,
        "coefficient_points": [_point_report(point) for point in points],
        "raw_state_set": {
            "count": len(states),
            "bit_order": BIT_ORDER,
            "families": families,
            "sha256_le_uint64_sequence": unbalanced.states_digest(states),
            "shared_with": UNBALANCED_LIBRARY_REL,
        },
        "lift": _lift_report(states, lifted, excluded),
        "compile_command": command,
        "device": {key: device_report.get(key) for key in ("architecture", "device_index", "device_name")},
        "device_reported": device_report,
        "gpu_vs_python": gpu,
        "host_cxx_vs_python": host,
        "temporary_directory_removed": True,
        "verdict": verdict,
        "writes": "none",
        "scientific_outputs": "intentionally absent",
    }

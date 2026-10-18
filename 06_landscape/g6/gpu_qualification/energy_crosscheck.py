"""Bounded GPU-vs-CPU bit-exact cross-check of the unbalanced energy transcript.

This module is a non-production Gate-6 GPU qualification prototype.  It binds
one explicitly declared finite set of raw 20-bit states and four reviewed
coefficient points, evaluates the canonical Python
``src.g4.energy.unbalanced_energy`` on the CPU, evaluates the transcribed HIP
kernel on the discrete ``gfx1201`` device, and reports mismatch counts only.

It is not a Gate-6 pass.  It never reads the Gate-5 core-pass output directory
or any Gate-5 shard, never computes a minimum, tie set, X_E, label, rate,
aggregate, transition, D013 trigger, or conclusion, never writes a Gate-5 or
Gate-6 result artifact, and never treats GPU output as a scientific value.

Importing this module has no side effects and writes nothing.
"""

from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.g4.energy import unbalanced_energy  # noqa: E402
from src.g4.instance import Instance, load_instance  # noqa: E402
from src.g4.parameters import Coefficients  # noqa: E402
from src.g6.ledgers import canonical_bytes, validate_preexecution_ledger  # noqa: E402


SCHEMA_PLAN = "decisions_os/g6_gpu_unbalanced_energy_crosscheck_plan/v1"
SCHEMA_RUN = "decisions_os/g6_gpu_unbalanced_energy_crosscheck_run/v1"
PURPOSE = (
    "non-production GPU-vs-CPU bit-exact cross-check of the unbalanced energy "
    "transcript; GPU output cannot contribute to a Gate-6 artifact"
)
TARGET_ARCHITECTURE = "gfx1201"
ENCODING = "unbalanced"
REFERENCE = "src.g4.energy.unbalanced_energy"
ASSET_COUNT = 20
SECTOR_COUNT = 4
FULL_MASK = (1 << ASSET_COUNT) - 1
BIT_ORDER = "x[i] = (mask >> i) & 1 for canonical ticker index i in 0..19"

INPUT_MAGIC = int.from_bytes(b"G6UBNCX1", "little")
OUTPUT_MAGIC = int.from_bytes(b"G6UBNCY1", "little")
FORMAT_VERSION = 1
COEFFICIENT_ORDER = ("alpha", "sector_linear", "sector_quadratic", "budget_linear", "budget_quadratic")
UNCONSUMED_COEFFICIENTS = ("sector_slack", "budget_slack")

HIP_SOURCE_REL = "research/g6/gpu_qualification/gpu_unbalanced_energy_crosscheck.hip.cpp"
INSTANCE_REL = "research/canonical/stage1_instance.json"
LEDGER_DIR_REL = "research/g6/preexecution_ledgers"
MANIFEST_REL = f"{LEDGER_DIR_REL}/manifest.json"
D011_LEDGER_REL = f"{LEDGER_DIR_REL}/d011_curvature_companion.json"
V14_2X_LEDGER_REL = f"{LEDGER_DIR_REL}/v14_expansion_2x.json"

# Exact inputs this prototype consumes.  Any drift fails closed before and
# after a run.  These are the only files whose bytes reach the comparison.
PINNED_INPUTS: dict[str, str] = {
    "src/g4/energy.py": "0ba83c0d33e0d2996352370e26bf0e782002ec49cb79e1628b74a2a74dd5fa11",
    "src/g4/instance.py": "645419374fd30891c2f9ff14d030ed65a032d52d8fe88fab068ad23417b58187",
    "src/g4/parameters.py": "cbbdebbe44b9af0d47fa1d5da7e00303e492d70d21abd696e6bdd5a4cd5be97c",
    "src/g6/ledgers.py": "40ff906fdedb526f7063c7d40aeb778335cf49291a47a948d9f5b31620fc0723",
    INSTANCE_REL: "c4615d9b5066597c4754a1e06d2b3a7906c218965a7d6d530cf54f75c4b5f243",
    MANIFEST_REL: "900b639509074114b4be1149dfaef7d14b6e4ba4a7c1fbcf90d719057a0611ca",
    D011_LEDGER_REL: "00091b631dc92f4a923badf4dd2abda0efc9d82a533f8c61926aa88c521fc06e",
    V14_2X_LEDGER_REL: "3bd7341a7dcf8ca5de007cf2d92ab89e64e95b887349df8e7dede0cc5b0ec3ea",
    HIP_SOURCE_REL: "909c1403503098a1b475d207fafa991f8116b5a29055ce3afa30ffdee8842b9b",
}
# Files whose hashes are recorded and drift-checked within a run, but which
# cannot pin themselves.
SELF_RELATIVES = (
    "research/g6/gpu_qualification/energy_crosscheck.py",
    "research/g6/run_gpu_energy_crosscheck.py",
)

# Compile contract.  The runner refuses to substitute relaxed flags.
REQUIRED_COMPILE_FLAGS = (
    "-O0",
    "-ffp-contract=off",
    "-mno-unsafe-fp-atomics",
    "-fno-fast-math",
    f"--offload-arch={TARGET_ARCHITECTURE}",
    "-lamdhip64",
)
COMPILE_TIMEOUT_SECONDS = 900
EXECUTE_TIMEOUT_SECONDS = 600

# Deterministic PRNG for the declared random-mask family (splitmix64).
SPLITMIX_SEED = 0x67365F756E62616C  # ascii "g6_unbal" as a little-endian word
SPLITMIX_DRAWS = 1024
NAMED_MASKS = (
    0xAAAAA, 0x55555, 0xF0F0F, 0x0F0F0, 0x33333, 0xCCCCC,
    0xFFC00, 0x003FF, 0xF8000, 0x0001F, 0x80001, 0xC0003, 0xE0007, 0x7FFFF, 0xFFFFE,
)
RANGE_LENGTH = 256


class CrosscheckError(RuntimeError):
    """Raised when the bounded cross-check contract cannot be established."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CrosscheckError(message)


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(relative: str) -> str:
    path = ROOT / relative
    try:
        return _sha256_bytes(path.read_bytes())
    except OSError as exc:
        raise CrosscheckError(f"consumed input is unreadable: {relative}") from exc


def current_hashes(relatives: tuple[str, ...] | list[str]) -> dict[str, str]:
    return {relative: _sha256_file(relative) for relative in relatives}


def verify_pinned_inputs(expected: Mapping[str, str] | None = None) -> dict[str, str]:
    """Hash every consumed input and fail closed on any drift from the pins."""
    pins = dict(PINNED_INPUTS if expected is None else expected)
    observed = current_hashes(tuple(pins))
    drifted = sorted(relative for relative in pins if observed[relative] != pins[relative])
    _require(not drifted, "pinned input drift: " + ", ".join(drifted))
    return observed


def _read_json(relative: str) -> dict[str, Any]:
    try:
        payload = json.loads((ROOT / relative).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CrosscheckError(f"unreadable JSON input: {relative}") from exc
    _require(isinstance(payload, dict), f"JSON input must be an object: {relative}")
    return payload


def _validate_content_hash(payload: Mapping[str, Any], label: str) -> None:
    body = dict(payload)
    digest = body.pop("content_sha256", None)
    _require(isinstance(digest, str) and digest == _sha256_bytes(canonical_bytes(body)),
             f"{label} canonical content hash mismatch")


def load_ledgers() -> dict[str, dict[str, Any]]:
    """Load the two consumed reviewed ledgers through the manifest and replay validation."""
    manifest = _read_json(MANIFEST_REL)
    _validate_content_hash(manifest, "preexecution-ledger manifest")
    _require(manifest.get("schema") == "decisions_os/g6_preexecution_ledger_manifest/v1",
             "unexpected preexecution-ledger manifest schema")
    listed = manifest.get("ledgers")
    _require(isinstance(listed, dict), "malformed preexecution-ledger manifest")
    output: dict[str, dict[str, Any]] = {}
    for relative in (D011_LEDGER_REL, V14_2X_LEDGER_REL):
        name = Path(relative).name
        entry = listed.get(name)
        _require(isinstance(entry, dict) and set(entry) == {"content_sha256", "file_sha256"},
                 f"manifest entry missing or malformed: {name}")
        _require(_sha256_file(relative) == entry["file_sha256"] == PINNED_INPUTS[relative],
                 f"ledger file identity mismatch: {name}")
        payload = _read_json(relative)
        _require(payload.get("content_sha256") == entry["content_sha256"],
                 f"ledger content identity mismatch: {name}")
        try:
            validate_preexecution_ledger(payload)
        except Exception as exc:  # LedgerError or any replay failure is fail-closed
            raise CrosscheckError(f"ledger fails transcript replay: {name}") from exc
        output[relative] = payload
    return output


def _coefficients_at(ledger: Mapping[str, Any], index: int) -> Coefficients:
    families = ledger["coefficient_ledger"]
    try:
        card = families["cardinality"][index]
        sector = families["sector"][index]
        budget = families["budget"][index]
        _require(card["index"] == sector["index"] == budget["index"] == index,
                 f"misaligned coefficient row {index}")
        return Coefficients(
            alpha=float.fromhex(card["alpha_hex"]),
            sector_slack=float.fromhex(sector["lambda_slack_hex"]),
            budget_slack=float.fromhex(budget["lambda_slack_hex"]),
            sector_linear=float.fromhex(sector["lambda_1_hex"]),
            sector_quadratic=float.fromhex(sector["lambda_2_hex"]),
            budget_linear=float.fromhex(budget["lambda_1_hex"]),
            budget_quadratic=float.fromhex(budget["lambda_2_hex"]),
        )
    except (IndexError, KeyError, TypeError, ValueError) as exc:
        raise CrosscheckError(f"malformed coefficient row {index}") from exc


def coefficient_points(ledgers: Mapping[str, Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    """Return the four declared coefficient points, loaded rather than re-derived."""
    d011 = ledgers[D011_LEDGER_REL]
    double = ledgers[V14_2X_LEDGER_REL]
    d011_rows = [row for row in d011["coordinates"] if row.get("primary_ell") == 30]
    _require(len(d011_rows) == 1, "D011 ledger must contain exactly one primary_ell=30 row")
    d011_index = d011_rows[0]["index"]
    _require(isinstance(d011_index, int) and d011["coordinates"][d011_index] is d011_rows[0],
             "D011 primary_ell=30 row index is misaligned")
    _require(len(double["coordinates"]) == 111, "V-14 2x ledger must contain 111 coordinate rows")
    _require(double["coordinates"][70]["binary64_hex"] == d011_rows[0]["binary64_hex"],
             "V-14 2x row 70 is not the embedded primary coordinate")
    declared = (
        ("d011_primary_ell_30", D011_LEDGER_REL, d011, d011_index, 30),
        ("v14_2x_row_70_embedded_primary", V14_2X_LEDGER_REL, double, 70, 30),
        ("v14_2x_row_0_lower_endpoint", V14_2X_LEDGER_REL, double, 0, None),
        ("v14_2x_row_110_upper_endpoint", V14_2X_LEDGER_REL, double, 110, None),
    )
    points = []
    for point_id, relative, ledger, index, primary_ell in declared:
        row = ledger["coordinates"][index]
        _require(row.get("index") == index, f"coordinate row misaligned: {point_id}")
        coefficients = _coefficients_at(ledger, index)
        values = asdict(coefficients)
        _require(all(math.isfinite(value) and value > 0.0 for value in values.values()),
                 f"coefficient is not finite and positive: {point_id}")
        points.append({
            "point_id": point_id,
            "pass_id": ledger["pass_id"],
            "ledger_file": relative,
            "ledger_content_sha256": ledger["content_sha256"],
            "ledger_index": {"card": index, "sector": index, "budget": index},
            "primary_ell": primary_ell,
            "coordinate_hex": row["binary64_hex"],
            "coefficients_hex": {name: value.hex() for name, value in values.items()},
            "consumed_by_unbalanced_transcript": list(COEFFICIENT_ORDER),
            "not_consumed": list(UNCONSUMED_COEFFICIENTS),
            "coefficients": coefficients,
        })
    return tuple(points)


def _splitmix64(state: int) -> tuple[int, int]:
    state = (state + 0x9E3779B97F4A7C15) & 0xFFFFFFFFFFFFFFFF
    z = state
    z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & 0xFFFFFFFFFFFFFFFF
    z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & 0xFFFFFFFFFFFFFFFF
    z = z ^ (z >> 31)
    return state, z


def declared_states(instance: Instance) -> tuple[tuple[int, ...], dict[str, int]]:
    """Return the fixed, deduplicated, ordered 20-bit state masks and family counts."""
    ordered: list[int] = []
    seen: set[int] = set()
    families: dict[str, int] = {}

    def add(family: str, mask: int) -> None:
        _require(isinstance(mask, int) and 0 <= mask <= FULL_MASK, "declared mask outside 20 bits")
        if mask not in seen:
            seen.add(mask)
            ordered.append(mask)
            families[family] = families.get(family, 0) + 1

    add("all_zero", 0)
    add("all_one", FULL_MASK)
    for i in range(ASSET_COUNT):
        add("single_bit", 1 << i)
    for i in range(ASSET_COUNT):
        add("all_but_one_bit", FULL_MASK ^ (1 << i))
    for i in range(ASSET_COUNT):
        for k in range(i + 1, ASSET_COUNT):
            add("two_bit", (1 << i) | (1 << k))
    for mask in NAMED_MASKS:
        add("named_high_bit_or_alternating", mask)
    for members in instance.sectors:
        sector_mask = 0
        for index in members:
            sector_mask |= 1 << index
        add("whole_sector", sector_mask)
        add("whole_sector_complement", FULL_MASK ^ sector_mask)
    for value in range(RANGE_LENGTH):
        add("low_range_0_255", value)
    for value in range(RANGE_LENGTH):
        add("high_range_0_255_shifted_12", value << 12)
    state = SPLITMIX_SEED
    for _ in range(SPLITMIX_DRAWS):
        state, output = _splitmix64(state)
        add("splitmix64_seeded", output & FULL_MASK)
    _require(len(ordered) == len(seen), "state deduplication failed")
    return tuple(ordered), families


def mask_to_x(mask: int) -> tuple[int, ...]:
    _require(isinstance(mask, int) and 0 <= mask <= FULL_MASK, "mask outside 20 bits")
    return tuple((mask >> i) & 1 for i in range(ASSET_COUNT))


def x_to_mask(x: tuple[int, ...]) -> int:
    _require(len(x) == ASSET_COUNT and all(bit in (0, 1) for bit in x), "x is not a 20-bit vector")
    mask = 0
    for i, bit in enumerate(x):
        mask |= bit << i
    return mask


def states_digest(states: tuple[int, ...]) -> str:
    return _sha256_bytes(b"".join(struct.pack("<Q", mask) for mask in states))


def float_bits(value: float) -> int:
    return struct.unpack("<Q", struct.pack("<d", value))[0]


def _words(values: list[int]) -> bytes:
    return b"".join(struct.pack("<Q", value) for value in values)


def encode_inputs(instance: Instance, points: tuple[Mapping[str, Any], ...],
                  states: tuple[int, ...]) -> bytes:
    """Little-endian uint64 word stream consumed by the HIP program.

    Layout: magic, version, 20, point_count, state_count; mu[20];
    sigma[400] row-major; prices[20]; kappa_risk; float(K); float(C); B;
    for each of 4 sectors: member_count then sorted member indices; for each
    point: alpha, sector_linear, sector_quadratic, budget_linear,
    budget_quadratic; then the state masks.
    """
    _require(len(instance.tickers) == ASSET_COUNT and len(instance.sectors) == SECTOR_COUNT,
             "instance shape is not 20 assets in 4 sectors")
    _require(0 < len(points) <= 64 and 0 < len(states) <= (1 << ASSET_COUNT), "bounded contract violated")
    header = [INPUT_MAGIC, FORMAT_VERSION, ASSET_COUNT, len(points), len(states)]
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
    for mask in states:
        _require(isinstance(mask, int) and 0 <= mask <= FULL_MASK, "state outside 20 bits")
    return _words(header) + _words(scalars) + _words(sectors) + _words(coefficient_words) + _words(list(states))


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
                          states: tuple[int, ...]) -> tuple[int, ...]:
    """Canonical CPU reference: unbalanced_energy for every (point, state), point-major."""
    output: list[int] = []
    for point in points:
        coefficients = point["coefficients"]
        for mask in states:
            value = unbalanced_energy(instance, mask_to_x(mask), coefficients)
            _require(math.isfinite(value), "canonical evaluator produced a nonfinite energy")
            output.append(float_bits(value))
    return tuple(output)


def compare_bits(reference: tuple[int, ...], candidate: tuple[int, ...],
                 points: tuple[Mapping[str, Any], ...], states: tuple[int, ...],
                 limit: int = 16) -> dict[str, Any]:
    """Count bit-pattern mismatches; identify at most ``limit`` by point and mask only."""
    _require(len(reference) == len(candidate) == len(points) * len(states),
             "comparison arrays have inconsistent lengths")
    mismatches = 0
    located: list[dict[str, Any]] = []
    for index, (expected, observed) in enumerate(zip(reference, candidate, strict=True)):
        if expected != observed:
            mismatches += 1
            if len(located) < limit:
                point_index, state_index = divmod(index, len(states))
                located.append({"point_id": points[point_index]["point_id"],
                                "state_mask_hex": f"0x{states[state_index]:05x}"})
    return {"mismatches": mismatches, "evaluations": len(reference), "first_mismatches": located}


def _locate_hipcc() -> str | None:
    candidate = Path("/opt/rocm/bin/hipcc")
    return shutil.which("hipcc") or (str(candidate) if candidate.is_file() else None)


def compile_command(hipcc: str, source: Path, binary: Path) -> list[str]:
    command = [
        hipcc,
        "-std=c++17",
        "-O0",
        "-ffp-contract=off",
        "-mno-unsafe-fp-atomics",
        "-fno-fast-math",
        f"--offload-arch={TARGET_ARCHITECTURE}",
        str(source),
        # Fedora's HIP package keeps libamdhip64 in the system library path
        # but its hipcc wrapper does not add it at link time.
        "-lamdhip64",
        "-o",
        str(binary),
    ]
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


def _bind() -> tuple[Instance, tuple[dict[str, Any], ...], tuple[int, ...], dict[str, int], dict[str, str]]:
    pins = verify_pinned_inputs()
    ledgers = load_ledgers()
    points = coefficient_points(ledgers)
    instance = load_instance(ROOT / INSTANCE_REL)
    states, families = declared_states(instance)
    return instance, points, states, families, pins


def build_plan() -> dict[str, Any]:
    """Validate every binding and describe the run without compiling or evaluating."""
    instance, points, states, families, pins = _bind()
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
        "state_set": {
            "count": len(states),
            "bit_order": BIT_ORDER,
            "families": families,
            "sha256_le_uint64_sequence": states_digest(states),
            "first_masks_hex": [f"0x{mask:05x}" for mask in states[:8]],
            "last_masks_hex": [f"0x{mask:05x}" for mask in states[-4:]],
            "splitmix64_seed_hex": f"0x{SPLITMIX_SEED:016x}",
            "splitmix64_draws": SPLITMIX_DRAWS,
        },
        "planned_evaluations": len(points) * len(states),
        "compile_command_template": compile_command("hipcc", Path("<tmp>/source.hip.cpp"), Path("<tmp>/crosscheck")),
        "hipcc_located": _locate_hipcc() is not None,
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
    return isinstance(architecture, str) and re.fullmatch(r"gfx1201(:.*)?", architecture) is not None


def run_crosscheck() -> dict[str, Any]:
    """Compile and execute the HIP cross-check in a temporary directory; report counts only."""
    _require(os.environ.get("PYTHONDONTWRITEBYTECODE") == "1", "PYTHONDONTWRITEBYTECODE=1 is required")
    hipcc = _locate_hipcc()
    _require(hipcc is not None, "hipcc is unavailable; the cross-check cannot run on this host")
    instance, points, states, families, pins_before = _bind()
    self_before = current_hashes(SELF_RELATIVES)
    platform_before = _platform_fingerprint()
    source = ROOT / HIP_SOURCE_REL
    reference = python_reference_bits(instance, points, states)
    encoded = encode_inputs(instance, points, states)
    temporary_path: Path | None = None
    with tempfile.TemporaryDirectory(prefix="g6-gpu-energy-crosscheck-") as temporary:
        temporary_path = Path(temporary)
        staged_source = temporary_path / "gpu_unbalanced_energy_crosscheck.hip.cpp"
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
                 and device_report.get("state_count") == len(states),
                 "HIP cross-check reported unexpected counts")
        device_index, device_bits, host_bits = decode_output(output_path.read_bytes(), len(points), len(states))
        _require(device_index == device_report.get("device_index"), "device index disagreement")
    _require(temporary_path is not None and not temporary_path.exists(), "temporary directory was not removed")
    gpu = compare_bits(reference, device_bits, points, states)
    host = compare_bits(reference, host_bits, points, states)
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
        "state_set": {
            "count": len(states),
            "bit_order": BIT_ORDER,
            "families": families,
            "sha256_le_uint64_sequence": states_digest(states),
        },
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

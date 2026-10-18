"""Python reference for the composed synthetic Stage-2 CUDA self-test.

This component joins the already-reviewed concepts into one fixed 257-state
synthetic path: canonical 20-bit decoded order, explicit sorted non-contiguous
sector membership, the frozen decoded preparation transcript, the frozen
per-register slack-minimizer policy (retaining tied minimizers), both frozen
energy transcripts, a strict first-seen minimum scan, the frozen D015 ``tau``
comparator at ``c_H in {1024, 2048, 4096}``, and stable chunked compaction of
``(flags << 32) | canonical_index``.

It is isolated from canonical inputs, ledgers, solvers, the Stage-2 generator
and NumPy, it writes no file, and its report carries checksums, counters and
identity metadata only — never an energy, minimum, tie index, label, rate or
record.

Synthetic control adjustment (narrow, documented, checksum-bound).  The tie
flags must be *derived* from real minima through the frozen comparator, but a
naturally generated near-tie at a fraction of ``tau`` cannot be arranged from
an arbitrary synthetic instance.  Therefore, and only for the six fixed
control positions in ``CONTROL_POSITIONS``, the energy is replaced by
``phase_a_minimum + offset`` with the exact binary64 offsets in
``CONTROL_OFFSETS``.  Everything else is untouched: the remaining 251 energies
per encoding are the unmodified frozen transcript, the phase-A minimum that
anchors the control is itself a natural energy, and the flags of every state —
control or not — are computed by the same frozen ``tau`` comparator.  The
offsets enter ``control_checksum`` and the energy checksums, and the fixtures
assert the exact flag each control position must produce, so a drifting
control is a test failure rather than a silent change.

The tied-minimizer branch is *not* simulated: the synthetic price vector holds
one deliberately non-integer price, so some budget residuals are half-integers
and the frozen rule legitimately retains two minimizers.  Real Stage-1/Stage-2
instances use integer prices and would not exercise that branch.
"""
from __future__ import annotations

import struct
from typing import Iterable, Mapping, Sequence


ASSET_COUNT = 20
SECTOR_COUNT = 4
SECTOR_SIZE = 5
SECTOR_SLACK_BITS = 2
BUDGET_SLACK_BITS = 11
AUXILIARY_BITS = SECTOR_COUNT * SECTOR_SLACK_BITS + BUDGET_SLACK_BITS
REGISTER_COUNT = SECTOR_COUNT + 1
TERM_COUNT = 12
STATE_COUNT = 257
INDEX_STRIDE = 4073
CHUNK_SIZE = 32
CHUNK_COUNT = (STATE_COUNT + CHUNK_SIZE - 1) // CHUNK_SIZE
ENCODINGS = ("unbalanced", "slack")
CH_VALUES = (1024.0, 2048.0, 4096.0)
LEGAL_FLAGS = (0, 4, 6, 7)
EPSILON = float.fromhex("0x1p-52")
LAMBDA_REF = float.fromhex("0x1p-5")
SENTINEL = (1 << 64) - 1
FNV_OFFSET, FNV_PRIME, MASK64 = 1469598103934665603, 1099511628211, (1 << 64) - 1
SCHEMA = "decisions_os/g9_cuda_composed_self_test/v1"

# Fixed synthetic non-contiguous balanced partition: sorted blocks, disjoint,
# covering 0..19, and no block a contiguous five-asset run.
SYNTHETIC_MEMBERSHIP: tuple[tuple[int, ...], ...] = (
    (0, 6, 11, 15, 19),
    (1, 5, 10, 14, 18),
    (2, 7, 9, 13, 17),
    (3, 4, 8, 12, 16),
)
# The single non-integer price that makes the tied-register branch reachable.
FRACTIONAL_PRICE_ASSET = 7
FRACTIONAL_PRICE = 2.5

CONTROL_POSITIONS: tuple[int, ...] = (40, 41, 100, 101, 200, 201)
CONTROL_OFFSETS: dict[str, tuple[str, ...]] = {
    # Offsets are exact binary64 powers of two calibrated per encoding so the
    # frozen comparator yields flags 7, 7, 7, 6, 4 and 0 in this order.
    "unbalanced": ("0x0p+0", "0x0p+0", "0x1p-43", "0x1p-42", "0x1p-41", "0x1p-40"),
    "slack": ("0x0p+0", "0x0p+0", "0x1p-46", "0x1p-45", "0x1p-44", "0x1p-43"),
}
EXPECTED_CONTROL_FLAGS: tuple[int, ...] = (7, 7, 7, 6, 4, 0)


class ComposedSelfTestError(RuntimeError):
    """Typed refusal for malformed synthetic inputs or self-test metadata."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ComposedSelfTestError(message)


def _word(value: float) -> int:
    return struct.unpack("<Q", struct.pack("<d", value))[0]


def _fnv(state: int, word: int) -> int:
    return ((state ^ word) * FNV_PRIME) & MASK64


# --- membership, canonical order -------------------------------------------

def validate_membership(sectors: Iterable[Iterable[object]]) -> tuple[tuple[int, ...], ...]:
    """Four explicit sorted five-asset blocks covering 0..19 exactly once."""
    blocks = tuple(tuple(block) for block in sectors)
    _require(len(blocks) == SECTOR_COUNT, "membership must contain exactly four sectors")
    seen: list[int] = []
    for sector, block in enumerate(blocks):
        _require(len(block) == SECTOR_SIZE, f"sector[{sector}] must contain exactly five assets")
        for member in block:
            _require(type(member) is int and 0 <= member < ASSET_COUNT,
                     f"sector[{sector}] member is not an asset index")
        _require(list(block) == sorted(block), f"sector[{sector}] members are not sorted ascending")
        _require(len(set(block)) == SECTOR_SIZE, f"sector[{sector}] repeats an asset")
        seen.extend(int(member) for member in block)
    _require(sorted(seen) == list(range(ASSET_COUNT)), "membership must cover each asset exactly once")
    return tuple(tuple(int(member) for member in block) for block in blocks)


def is_contiguous_membership(sectors: Iterable[Iterable[object]]) -> bool:
    blocks = validate_membership(sectors)
    return blocks == tuple(tuple(range(s * SECTOR_SIZE, s * SECTOR_SIZE + SECTOR_SIZE))
                           for s in range(SECTOR_COUNT))


def canonical_index(position: int) -> int:
    """Strictly ascending synthetic canonical indices inside the 20-bit space."""
    _require(type(position) is int and 0 <= position < STATE_COUNT, "table position is out of range")
    index = position * INDEX_STRIDE
    _require(index < (1 << ASSET_COUNT), "synthetic index escaped the decoded space")
    return index


def canonical_index_to_mask(index: int) -> int:
    """Canonical 20-bit decoded order, identical to src.g5.domains.BinaryDomain."""
    _require(type(index) is int and 0 <= index < (1 << ASSET_COUNT), "canonical index is out of range")
    mask = 0
    for asset in range(ASSET_COUNT):
        mask |= ((index >> (ASSET_COUNT - 1 - asset)) & 1) << asset
    return mask


# --- synthetic instance and coefficients ------------------------------------

def synthetic_instance() -> dict[str, object]:
    """Fixed artificial instance; not derived from any canonical input."""
    mu = [(float(asset) - 9.0) / 1000.0 for asset in range(ASSET_COUNT)]
    prices = [float(1 + (asset % 5)) for asset in range(ASSET_COUNT)]
    prices[FRACTIONAL_PRICE_ASSET] = FRACTIONAL_PRICE
    sigma = [
        [0.01 + float(row) / 10000.0 if row == column else float((row + column) % 7) / 100000.0
         for column in range(ASSET_COUNT)]
        for row in range(ASSET_COUNT)
    ]
    return {"mu": mu, "prices": prices, "sigma": sigma, "kappa_risk": 1.0,
            "k": 6.0, "c": 2.0, "b": 40.0, "sectors": SYNTHETIC_MEMBERSHIP}


def synthetic_coefficients() -> dict[str, float]:
    """One fixed synthetic coefficient point; no ledger is consulted."""
    return {"alpha": float.fromhex("0x1.0000000000000p-3"),
            "sector_slack": float.fromhex("0x1.0000000000000p-4"),
            "budget_slack": float.fromhex("0x1.8000000000000p-5"),
            "sector_linear": float.fromhex("0x1.4000000000000p-3"),
            "sector_quadratic": float.fromhex("0x1.0000000000000p-5"),
            "budget_linear": float.fromhex("0x1.0000000000000p-4"),
            "budget_quadratic": float.fromhex("0x1.0000000000000p-6")}


# --- frozen preparation transcript ------------------------------------------

def decoded_terms(instance: Mapping[str, object], index: int) -> tuple[float, ...]:
    """Frozen transcript order, with explicit sorted sector membership."""
    sectors = validate_membership(instance["sectors"])
    mask = canonical_index_to_mask(index)
    x = [1.0 if (mask >> asset) & 1 else 0.0 for asset in range(ASSET_COUNT)]
    f_value = +0.0
    for asset in range(ASSET_COUNT):
        f_value = f_value + (-(float(instance["mu"][asset]) * x[asset]))
    for row in range(ASSET_COUNT):
        for column in range(ASSET_COUNT):
            sigma_x = float(instance["sigma"][row][column]) * x[row]
            f_value = f_value + (float(instance["kappa_risk"]) * (sigma_x * x[column]))
    cardinality = +0.0
    for asset in range(ASSET_COUNT):
        cardinality = cardinality + x[asset]
    h_card = cardinality - float(instance["k"])
    h_sector: list[float] = []
    sector_square: list[float] = []
    for block in sectors:
        total = +0.0
        for member in block:
            total = total + x[member]
        residual = float(instance["c"]) - total
        h_sector.append(residual)
        sector_square.append(residual * residual)
    budget = +0.0
    for asset in range(ASSET_COUNT):
        budget = budget + (float(instance["prices"][asset]) * x[asset])
    h_budget = float(instance["b"]) - budget
    return (f_value, h_card * h_card, *h_sector, *sector_square, h_budget, h_budget * h_budget)


# --- frozen per-register slack-minimizer policy -----------------------------

def _require_finite(value: object) -> float:
    _require(type(value) in (int, float), "value must be a real number")
    number = float(value)
    _require(number == number and number not in (float("inf"), float("-inf")), "value must be finite")
    return number


def _floor_double(value: float) -> int:
    _require_finite(value)
    lower = int(value)
    if float(lower) > value:
        lower -= 1
    return lower


def register_maximum(register: int) -> int:
    _require(type(register) is int and 0 <= register < REGISTER_COUNT, "register index is out of range")
    bits = SECTOR_SLACK_BITS if register < SECTOR_COUNT else BUDGET_SLACK_BITS
    return (1 << bits) - 1


def register_offset(register: int) -> int:
    _require(type(register) is int and 0 <= register < REGISTER_COUNT, "register index is out of range")
    return register * SECTOR_SLACK_BITS if register < SECTOR_COUNT else SECTOR_COUNT * SECTOR_SLACK_BITS


def register_minimizers(residual: float, maximum: int) -> tuple[tuple[int, float], ...]:
    """Frozen rule: clamped floor/floor+1 candidates, every tied minimizer kept."""
    residual = _require_finite(residual)
    lower = _floor_double(residual)
    candidates = sorted({min(max(lower, 0), maximum), min(max(lower + 1, 0), maximum)})
    scored = [(value, (residual - float(value)) * (residual - float(value))) for value in candidates]
    best = min(penalty for _, penalty in scored)
    return tuple((value, penalty) for value, penalty in scored if penalty == best)


def register_is_exactly_representable(residual: float, maximum: int) -> bool:
    residual = _require_finite(residual)
    lower = _floor_double(residual)
    return float(lower) == residual and 0 <= lower <= maximum


def unpack_register_value(auxiliary: int, register: int) -> float:
    """Reconstruct one register by explicit ascending bit weights from ``+0.0``."""
    offset = register_offset(register)
    bits = SECTOR_SLACK_BITS if register < SECTOR_COUNT else BUDGET_SLACK_BITS
    accumulator = +0.0
    for bit in range(bits):
        value = 1.0 if (auxiliary >> (offset + bit)) & 1 else 0.0
        accumulator = accumulator + (float(1 << bit) * value)
    return accumulator


def state_registers(terms: Sequence[float]) -> dict[str, object]:
    """Per-register minimizers, packed first lift, and reconstructed penalties."""
    residuals = [terms[2 + sector] for sector in range(SECTOR_COUNT)] + [terms[2 + 2 * SECTOR_COUNT]]
    registers = []
    packed = 0
    multiplicity = 1
    for register, residual in enumerate(residuals):
        maximum = register_maximum(register)
        minimizers = register_minimizers(residual, maximum)
        multiplicity *= len(minimizers)
        packed |= minimizers[0][0] << register_offset(register)
        registers.append({"residual": residual, "minimizers": minimizers,
                          "exactly_representable": register_is_exactly_representable(residual, maximum)})
    slack_squares = []
    for register in range(REGISTER_COUNT):
        value = unpack_register_value(packed, register)
        delta = residuals[register] - value
        slack_squares.append(delta * delta)
    return {"registers": registers, "packed": packed, "multiplicity": multiplicity,
            "slack_squares": tuple(slack_squares)}


# --- frozen energy transcripts ----------------------------------------------

def unbalanced_energy(terms: Sequence[float], coefficients: Mapping[str, float]) -> float:
    h = terms[0]
    h = h + (coefficients["alpha"] * terms[1])
    for sector in range(SECTOR_COUNT):
        linear = coefficients["sector_linear"] * terms[2 + sector]
        quadratic = coefficients["sector_quadratic"] * terms[2 + SECTOR_COUNT + sector]
        h = h + ((-linear) + quadratic)
    linear = coefficients["budget_linear"] * terms[2 + 2 * SECTOR_COUNT]
    quadratic = coefficients["budget_quadratic"] * terms[3 + 2 * SECTOR_COUNT]
    return h + ((-linear) + quadratic)


def slack_energy(terms: Sequence[float], slack_squares: Sequence[float],
                 coefficients: Mapping[str, float]) -> float:
    h = terms[0]
    h = h + (coefficients["alpha"] * terms[1])
    for sector in range(SECTOR_COUNT):
        h = h + (coefficients["sector_slack"] * slack_squares[sector])
    return h + (coefficients["budget_slack"] * slack_squares[SECTOR_COUNT])


# --- frozen D015 comparator --------------------------------------------------

def frozen_tau(y: float, y_prime: float, c_h: float) -> float:
    """FROZEN_MATH_SPEC §5.3 / src.g4.energy.tau, in the same operation order."""
    maximum = max(abs(y), abs(y_prime))
    scale = LAMBDA_REF + maximum
    return (c_h * EPSILON) * scale


def frozen_tie(y: float, y_prime: float, c_h: float) -> bool:
    gap = abs(y - y_prime)
    return gap <= frozen_tau(y, y_prime, c_h)


def tie_flags(energy: float, minimum: float) -> int:
    flags = 0
    for bit, c_h in enumerate(CH_VALUES):
        if frozen_tie(energy, minimum, c_h):
            flags |= 1 << bit
    return flags


def flag_is_legal(flags: int) -> bool:
    return flags in LEGAL_FLAGS


def flag_violates_nesting(flags: int) -> bool:
    return (bool(flags & 1) and not flags & 2) or (bool(flags & 2) and not flags & 4)


# --- stable chunked compaction ----------------------------------------------

def compact_word(index: int, flags: int) -> int:
    _require(0 <= index < (1 << 32) and 0 <= flags < (1 << 32), "word field does not fit")
    return (flags << 32) | index


def chunk_counts(flags: Sequence[int]) -> tuple[int, ...]:
    counts = [0] * CHUNK_COUNT
    for position, value in enumerate(flags):
        if value != 0:
            counts[position // CHUNK_SIZE] += 1
    return tuple(counts)


def exclusive_offsets(counts: Sequence[int]) -> tuple[int, ...]:
    offsets = [0]
    running = 0
    for count in counts:
        running += count
        offsets.append(running)
    return tuple(offsets)


def compact_stream(flags: Sequence[int]) -> tuple[int, ...]:
    counts = chunk_counts(flags)
    offsets = exclusive_offsets(counts)
    stream = [SENTINEL] * offsets[-1]
    for chunk in range(CHUNK_COUNT):
        cursor = offsets[chunk]
        start = chunk * CHUNK_SIZE
        stop = min(start + CHUNK_SIZE, len(flags))
        for position in range(start, stop):
            if flags[position] != 0:
                stream[cursor] = compact_word(canonical_index(position), flags[position])
                cursor += 1
    return tuple(stream)


def audit_stream(stream: Sequence[int]) -> dict[str, int]:
    order_violations = duplicate_entries = unwritten_slots = 0
    previous: int | None = None
    for word in stream:
        if word == SENTINEL:
            unwritten_slots += 1
            continue
        index = word & 0xFFFFFFFF
        if previous is not None:
            if index == previous:
                duplicate_entries += 1
            if index <= previous:
                order_violations += 1
        previous = index
    return {"order_violations": order_violations, "duplicate_entries": duplicate_entries,
            "unwritten_slots": unwritten_slots}


# --- composed pipeline -------------------------------------------------------

def control_offsets(encoding: str) -> tuple[float, ...]:
    _require(encoding in ENCODINGS, "unknown encoding")
    return tuple(float.fromhex(value) for value in CONTROL_OFFSETS[encoding])


def pipeline() -> dict[str, object]:
    """Run the whole fixed synthetic path and retain every intermediate."""
    instance = synthetic_instance()
    coefficients = synthetic_coefficients()
    terms: list[tuple[float, ...]] = []
    registers: list[dict[str, object]] = []
    natural: dict[str, list[float]] = {name: [] for name in ENCODINGS}
    exact = clamped = tied = 0
    multiplicity_total = 0
    nonfinite_terms = 0
    for position in range(STATE_COUNT):
        row = decoded_terms(instance, canonical_index(position))
        terms.append(row)
        state = state_registers(row)
        registers.append(state)
        for entry in state["registers"]:
            minimizers = entry["minimizers"]
            if entry["exactly_representable"]:
                exact += 1
            else:
                clamped += 1
            if len(minimizers) > 1:
                tied += 1
        multiplicity_total += int(state["multiplicity"])
        for value in row:
            if value != value or value in (float("inf"), float("-inf")):
                nonfinite_terms += 1
        natural["unbalanced"].append(unbalanced_energy(row, coefficients))
        natural["slack"].append(slack_energy(row, state["slack_squares"], coefficients))
    result: dict[str, object] = {"instance": instance, "coefficients": coefficients, "terms": terms,
                                 "registers": registers, "exact_registers": exact,
                                 "clamped_registers": clamped, "tied_registers": tied,
                                 "lift_multiplicity_total": multiplicity_total,
                                 "nonfinite_terms": nonfinite_terms, "encodings": {}}
    for encoding in ENCODINGS:
        energies = list(natural[encoding])
        phase_a_minimum = min(energies)
        offsets = control_offsets(encoding)
        for slot, position in enumerate(CONTROL_POSITIONS):
            energies[position] = phase_a_minimum + offsets[slot]
        minimum = energies[0]
        minimum_index = 0
        for position in range(1, STATE_COUNT):
            if energies[position] < minimum:          # strict: first-seen wins
                minimum = energies[position]
                minimum_index = position
        flags = [tie_flags(value, minimum) for value in energies]
        counts = chunk_counts(flags)
        offsets_vector = exclusive_offsets(counts)
        stream = compact_stream(flags)
        audit = audit_stream(stream)
        result["encodings"][encoding] = {
            "phase_a_minimum": phase_a_minimum, "natural_energies": tuple(natural[encoding]),
            "energies": energies, "minimum": minimum,
            "minimum_index": minimum_index, "flags": flags, "chunk_counts": counts,
            "offsets": offsets_vector, "stream": stream, "audit": audit,
            "per_ch": tuple(sum(1 for value in flags if value & (1 << bit)) for bit in range(len(CH_VALUES))),
            "illegal": sum(1 for value in flags if not flag_is_legal(value)),
            "nesting": sum(1 for value in flags if flag_violates_nesting(value)),
        }
    return result


def expected_self_test() -> dict[str, object]:
    """Reproduce every device checksum and counter from the fixed synthetic path."""
    run = pipeline()
    membership_checksum = FNV_OFFSET
    for block in validate_membership(run["instance"]["sectors"]):
        for member in block:
            membership_checksum = _fnv(membership_checksum, member)
    domain_checksum = FNV_OFFSET
    terms_checksum = FNV_OFFSET
    lift_checksum = FNV_OFFSET
    for position in range(STATE_COUNT):
        domain_checksum = _fnv(domain_checksum, canonical_index(position))
        for value in run["terms"][position]:
            terms_checksum = _fnv(terms_checksum, _word(value))
        state = run["registers"][position]
        for entry in state["registers"]:
            lift_checksum = _fnv(lift_checksum, len(entry["minimizers"]))
            lift_checksum = _fnv(lift_checksum, 1 if entry["exactly_representable"] else 0)
            for value, penalty in entry["minimizers"]:
                lift_checksum = _fnv(lift_checksum, value)
                lift_checksum = _fnv(lift_checksum, _word(penalty))
        lift_checksum = _fnv(lift_checksum, state["packed"])
        for value in state["slack_squares"]:
            lift_checksum = _fnv(lift_checksum, _word(value))
    control_checksum = FNV_OFFSET
    for encoding in ENCODINGS:
        for slot, position in enumerate(CONTROL_POSITIONS):
            control_checksum = _fnv(control_checksum, position)
            control_checksum = _fnv(control_checksum, _word(control_offsets(encoding)[slot]))
    report: dict[str, object] = {
        "schema": SCHEMA, "state_count": STATE_COUNT, "chunk_size": CHUNK_SIZE,
        "chunk_count": CHUNK_COUNT, "register_count": REGISTER_COUNT, "auxiliary_bits": AUXILIARY_BITS,
        "membership_checksum": f"{membership_checksum:016x}", "domain_checksum": f"{domain_checksum:016x}",
        "terms_checksum": f"{terms_checksum:016x}", "lift_policy_checksum": f"{lift_checksum:016x}",
        "control_checksum": f"{control_checksum:016x}",
        "exact_registers": run["exact_registers"], "clamped_registers": run["clamped_registers"],
        "tied_registers": run["tied_registers"], "lift_multiplicity_total": run["lift_multiplicity_total"],
        "nonfinite_terms": run["nonfinite_terms"], "nonfinite_energies": 0, "invalid_registers": 0,
        "scientific_outputs": "intentionally absent",
    }
    order = duplicates = unwritten = 0
    illegal = nesting = 0
    for encoding in ENCODINGS:
        data = run["encodings"][encoding]
        # The natural digest is taken over all 257 pre-control words, so a
        # defect confined to a natural energy at a control position cannot be
        # hidden by the overwrite that follows.
        natural_checksum = FNV_OFFSET
        for value in data["natural_energies"]:
            natural_checksum = _fnv(natural_checksum, _word(value))
        energy_checksum = FNV_OFFSET
        for value in data["energies"]:
            energy_checksum = _fnv(energy_checksum, _word(value))
        # The first-seen minimum index is checksum-bound, never reported.
        minimum_checksum = _fnv(_fnv(FNV_OFFSET, _word(data["minimum"])), data["minimum_index"])
        flags_checksum = FNV_OFFSET
        for value in data["flags"]:
            flags_checksum = _fnv(flags_checksum, value)
        offsets_checksum = FNV_OFFSET
        for count in data["chunk_counts"]:
            offsets_checksum = _fnv(offsets_checksum, count)
        for offset in data["offsets"]:
            offsets_checksum = _fnv(offsets_checksum, offset)
        compacted_checksum = FNV_OFFSET
        for word in data["stream"]:
            compacted_checksum = _fnv(compacted_checksum, word)
        report[f"natural_energy_checksum_{encoding}"] = f"{natural_checksum:016x}"
        report[f"controlled_energy_checksum_{encoding}"] = f"{energy_checksum:016x}"
        report[f"minimum_checksum_{encoding}"] = f"{minimum_checksum:016x}"
        report[f"flags_checksum_{encoding}"] = f"{flags_checksum:016x}"
        report[f"offsets_checksum_{encoding}"] = f"{offsets_checksum:016x}"
        report[f"compacted_checksum_{encoding}"] = f"{compacted_checksum:016x}"
        report[f"compacted_total_{encoding}"] = data["offsets"][-1]
        report[f"count_c_h_1024_{encoding}"] = data["per_ch"][0]
        report[f"count_c_h_2048_{encoding}"] = data["per_ch"][1]
        report[f"count_c_h_4096_{encoding}"] = data["per_ch"][2]
        order += data["audit"]["order_violations"]
        duplicates += data["audit"]["duplicate_entries"]
        unwritten += data["audit"]["unwritten_slots"]
        illegal += data["illegal"]
        nesting += data["nesting"]
    report["order_violations"] = order
    report["duplicate_entries"] = duplicates
    report["unwritten_slots"] = unwritten
    report["sentinel_violations"] = 0
    report["illegal_flag_entries"] = illegal
    report["nesting_violations"] = nesting
    report["verdict"] = "pass"
    return report


def validate_self_test_report(payload: object) -> dict[str, object]:
    """Fail closed unless the device reproduces every expected field exactly."""
    expected = expected_self_test()
    required = set(expected) | {"device_index", "device_name"}
    _require(isinstance(payload, dict) and set(payload) == required, "composed report has wrong key set")
    _require(type(payload["device_index"]) is int and payload["device_index"] >= 0
             and type(payload["device_name"]) is str and payload["device_name"],
             "composed device metadata malformed")
    for key, value in expected.items():
        if type(value) is int:
            _require(type(payload[key]) is int, f"composed integer field has wrong type: {key}")
    # Counters, checksums and identity metadata only: a container would be a
    # route for an energy, minimum, tie index, label, rate or record to escape.
    for key, value in payload.items():
        _require(not isinstance(value, (list, tuple, dict)), f"composed report carries a container: {key}")
    for key, value in expected.items():
        _require(payload[key] == value, f"composed self-test mismatch: {key}")
    return dict(payload)

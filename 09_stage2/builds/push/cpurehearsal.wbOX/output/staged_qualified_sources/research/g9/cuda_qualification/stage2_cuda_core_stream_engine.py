"""Python reference for the synthetic Stage-2 CUDA core-stream engine.

This is the first production-shaped numerical core: it composes, in one path,
canonical 20-bit decoded enumeration, arbitrary sorted 4x5 sector membership,
the frozen sequential binary64 objective/residual transcript, the full
active-CSB slack lift rule with every tied minimizer retained in frozen 19-bit
packing and Cartesian order, both energy transcripts for two coefficient rows,
strict first-seen minima through fixed contiguous segments and an ascending
strict-'<' merge, frozen D015 flags at c_H in {1024, 2048, 4096}, and the
deterministic stable compaction of ``(flags << 32) | canonical_index`` entries.

It is synthetic and isolated: no Stage-2 candidate, generated instance, ground
truth, ledger, real file input, record output, manifest output, Kaggle session,
nvcc run or GPU run is involved, and no scientific value is produced.  The
report carries synthetic checksums, integer counters, fixed identity metadata
and a verdict only.

The engine is generic: the payload carries its own membership and the core
makes no contiguous-sector assumption.  ``ALTERNATE_MEMBERSHIP`` exists so the
fixtures can drive the same core with a different sorted partition.

Frozen rules reproduced here, not invented:

* canonical decoded order ``x[i] = (index >> (19 - i)) & 1``
  (``src.g5.domains.BinaryDomain``);
* the residual transcript and the clamped floor/floor+1 minimizer rule with
  **every** tied minimizer retained, the frozen 19-bit register layout and the
  frozen Cartesian-product lift order (sector 0 slowest, budget fastest);
* the prepared-energy transcripts of ``src.g4.energy``, every accumulator
  starting at ``+0.0``;
* D015: ``gap = abs(fl(y - y_min))``, ``scale = fl(lambda_ref + max(abs(y),
  abs(y_min)))``, ``tau = fl((c_H * eps) * scale)``, tie iff ``gap <= tau``.

Compaction is deterministic and stable: a fixed chunk count, then an exclusive
prefix, then each chunk writes its own entries in ascending canonical order.
No atomics, no shared-memory reduction, no sorting, no fp32, no fast math, no
FMA and no nondeterministic minimum selection appear anywhere in this path.

This component is **not** a record, classification or D016 producer, and it is
not a claim of real CUDA qualification or Stage-2 execution readiness.
"""
from __future__ import annotations

from array import array
import itertools
import struct
from typing import Iterable, Mapping, Sequence


ASSET_COUNT = 20
SECTOR_COUNT = 4
SECTOR_SIZE = 5
SECTOR_SLACK_BITS = 2
BUDGET_SLACK_BITS = 11
AUXILIARY_BITS = SECTOR_COUNT * SECTOR_SLACK_BITS + BUDGET_SLACK_BITS
REGISTER_COUNT = SECTOR_COUNT + 1
DECODED_WIDTH = ASSET_COUNT
STATE_COUNT = 1 << DECODED_WIDTH
SEGMENT_SIZE = 1024
SEGMENT_COUNT = STATE_COUNT // SEGMENT_SIZE
MAX_LIFTS_PER_STATE = 1 << REGISTER_COUNT
CACHE_CAPACITY = STATE_COUNT * MAX_LIFTS_PER_STATE
UINT64_MAX = (1 << 64) - 1
ENCODINGS = ("unbalanced", "slack")
CH_VALUES = (1024.0, 2048.0, 4096.0)
LEGAL_FLAGS = (0, 4, 6, 7)
EPSILON = float.fromhex("0x1p-52")
# Lambda_ref is INSTANCE-SPECIFIC: the approved protocol recomputes it per
# instance, so it is a validated payload field, never a module constant baked
# into the comparator.  This is only the value the synthetic payload carries.
SYNTHETIC_LAMBDA_REF = float.fromhex("0x1p-5")
# Far enough from the synthetic value to be observable even when |y_min|
# dominates the D015 scale; the fixtures rely on that separation.
ALTERNATE_LAMBDA_REF = float.fromhex("0x1p+3")
FNV_OFFSET, FNV_PRIME, MASK64 = 1469598103934665603, 1099511628211, (1 << 64) - 1
SCHEMA = "decisions_os/g9_cuda_core_stream_engine_self_test/v1"

# Pre-nvcc numerical compile contract.  These are the flags this component
# REQUIRES of any future integrated CUDA runner; nothing here invokes nvcc, and
# declaring them is not a claim of real CUDA numerical qualification.
CUDA_COMPILE_FLAGS = ("--fmad=false", "--ftz=false", "--prec-div=true", "--prec-sqrt=true")
HOST_COMPILE_FLAGS = ("-ffp-contract=off", "-fno-fast-math")

SYNTHETIC_MEMBERSHIP: tuple[tuple[int, ...], ...] = (
    (0, 6, 11, 15, 19),
    (1, 5, 10, 14, 18),
    (2, 7, 9, 13, 17),
    (3, 4, 8, 12, 16),
)
# Deterministic stable compaction of (flags << 32) | canonical_index.
COMPACTION_CHUNK_SIZE = 4096
MAX_COMPACTED_ENTRIES = 1 << 14
COMPACTED_FLAGS = (4, 6, 7)

# A different sorted 4x5 partition, so the fixtures can prove the core carries
# no contiguous-sector assumption and no dependence on one fixed membership.
ALTERNATE_MEMBERSHIP: tuple[tuple[int, ...], ...] = (
    (2, 3, 8, 12, 17),
    (0, 4, 9, 13, 16),
    (1, 6, 10, 15, 18),
    (5, 7, 11, 14, 19),
)

FRACTIONAL_PRICE_ASSET = 7
FRACTIONAL_PRICE = 2.5

ROW_NAMES = ("row0", "row1")
COEFFICIENT_ROWS: dict[str, tuple[str, ...]] = {
    # alpha, sector_slack, budget_slack, sector_linear, sector_quadratic,
    # budget_linear, budget_quadratic — fixed synthetic words, host-validated.
    "row0": ("0x1p-3", "0x1p-4", "0x1.8p-5", "0x1.4p-3", "0x1p-5", "0x1p-4", "0x1p-6"),
    "row1": ("0x1p-5", "0x1p+2", "0x1p+1", "0x1p-1", "0x1p-2", "0x1.8p-1", "0x1p-3"),
}
COEFFICIENT_FIELDS = ("alpha", "sector_slack", "budget_slack", "sector_linear",
                      "sector_quadratic", "budget_linear", "budget_quadratic")

# Control positions are decoded indices (unbalanced) and lift indices (slack).
# Synthetic control adjustment (declared, checksum-bound, never hidden).  The
# natural landscape has unique minima and no near-ties, so a fixed set of
# control positions takes the value natural_minimum + offset.  Offsets are
# non-negative, so the controlled minimum VALUE is the natural minimum; only
# the first-seen winner and the flag population change.
#
# The positions are chosen so that every downstream rule is load-bearing:
#   * 40 and 41 tie inside segment 0            -> segment-local strict '<';
#   * 1064 and 20000 tie from segments 1 and 19 -> fixed-order ascending merge;
#   * flagged entries land in compaction chunks 0, 1, 2, 4 and 24
#     (chunk size 4096)                         -> per-chunk prefix and order.
CONTROL_POSITIONS: dict[str, tuple[int, ...]] = {
    "unbalanced": (40, 41, 100, 101, 200, 201, 1064, 5000, 9000, 20000, 100000),
    "slack": (40, 41, 100, 101, 200, 201, 1064, 5000, 9000, 20000, 100000),
}
# Offsets calibrated per (row, encoding) so the frozen comparator yields the
# declared ladder; the fixtures assert the exact resulting flags.
CONTROL_OFFSETS: dict[tuple[str, str], tuple[str, ...]] = {
    ("row0", "unbalanced"): ("0x0p+0", "0x0p+0", "0x1p-43", "0x1p-42", "0x1p-41", "0x1p-40",
                             "0x0p+0", "0x1p-43", "0x1p-42", "0x0p+0", "0x1p-41"),
    ("row0", "slack"): ("0x0p+0", "0x0p+0", "0x1p-47", "0x1p-46", "0x1p-45", "0x1p-44",
                        "0x0p+0", "0x1p-47", "0x1p-46", "0x0p+0", "0x1p-45"),
    ("row1", "unbalanced"): ("0x0p+0", "0x0p+0", "0x1p-44", "0x1p-43", "0x1p-42", "0x1p-41",
                             "0x0p+0", "0x1p-44", "0x1p-43", "0x0p+0", "0x1p-42"),
    ("row1", "slack"): ("0x0p+0", "0x0p+0", "0x1p-47", "0x1p-46", "0x1p-45", "0x1p-44",
                        "0x0p+0", "0x1p-47", "0x1p-46", "0x0p+0", "0x1p-45"),
}
EXPECTED_CONTROL_FLAGS = (7, 7, 7, 6, 4, 0, 7, 7, 6, 7, 4)


class CoreStreamEngineError(RuntimeError):
    """Typed refusal: malformed input, cap overflow, or inconsistent reconstruction."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CoreStreamEngineError(message)


def _word(value: float) -> int:
    return struct.unpack("<Q", struct.pack("<d", value))[0]


def _fnv(state: int, word: int) -> int:
    return ((state ^ word) * FNV_PRIME) & MASK64


def _finite(value: object, label: str) -> float:
    _require(type(value) in (int, float), f"{label} must be a real number")
    number = float(value)
    _require(number == number and number not in (float("inf"), float("-inf")), f"{label} must be finite")
    return number


def _is_nonfinite(value: float) -> bool:
    return value != value or value in (float("inf"), float("-inf"))


# --- payload, coefficients ---------------------------------------------------

def validate_membership(sectors: Iterable[Iterable[object]]) -> tuple[tuple[int, ...], ...]:
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
    return validate_membership(sectors) == tuple(
        tuple(range(s * SECTOR_SIZE, s * SECTOR_SIZE + SECTOR_SIZE)) for s in range(SECTOR_COUNT))


def validate_payload(payload: Mapping[str, object]) -> dict[str, object]:
    _require(isinstance(payload, Mapping), "payload must be a mapping")
    _require(set(payload) == {"mu", "sigma", "prices", "kappa_risk", "k", "c", "b", "sectors",
                              "lambda_ref"},
             "payload has wrong key set")
    mu = tuple(_finite(value, "mu") for value in payload["mu"])
    prices = tuple(_finite(value, "price") for value in payload["prices"])
    _require(len(mu) == ASSET_COUNT and len(prices) == ASSET_COUNT, "mu and prices need 20 entries")
    _require(all(value > 0.0 for value in prices), "prices must be strictly positive")
    sigma = tuple(tuple(_finite(value, "sigma") for value in row) for row in payload["sigma"])
    _require(len(sigma) == ASSET_COUNT and all(len(row) == ASSET_COUNT for row in sigma),
             "sigma must be 20 by 20")
    _require(sigma == tuple(tuple(row[column] for row in sigma) for column in range(ASSET_COUNT)),
             "sigma must be exactly symmetric")
    kappa = _finite(payload["kappa_risk"], "kappa_risk")
    lambda_ref = _finite(payload["lambda_ref"], "lambda_ref")
    _require(lambda_ref > 0.0, "lambda_ref must be finite and strictly positive")
    k_value, c_value, b_value = (_finite(payload[name], name) for name in ("k", "c", "b"))
    _require(float(int(k_value)) == k_value and 0 < int(k_value) <= ASSET_COUNT, "K must be an integer in range")
    # DECLARED CONTRACT (B1, resolution B): C must be integral.
    #
    # With integral C and integral per-sector selection counts every sector
    # residual is an integer, so each sector register has exactly ONE
    # minimizer and the slack lift multiplicity is carried entirely by the
    # budget register.  A fractional C would put a sector residual on a
    # half-integer, tie that register, and multiply the lift count -- but the
    # energy stage enumerates only the budget alternatives, which would leave
    # allocated offset ranges unwritten.  Rather than support that partially,
    # the contract is narrowed here and the tie is separately asserted
    # unreachable in build_domain.  This matches the approved Stage-2 C rule.
    _require(float(int(c_value)) == c_value and int(c_value) >= 0,
             "C must be a non-negative integer (fractional C would tie a sector register)")
    return {"mu": mu, "sigma": sigma, "prices": prices, "kappa_risk": kappa,
            "k": k_value, "c": c_value, "b": b_value, "lambda_ref": lambda_ref,
            "sectors": validate_membership(payload["sectors"])}


def synthetic_payload() -> dict[str, object]:
    """Fixed artificial 20-asset payload; not derived from any real input."""
    mu = [(float(asset) - 9.0) / 1000.0 for asset in range(ASSET_COUNT)]
    prices = [float(1 + (asset % 5)) for asset in range(ASSET_COUNT)]
    prices[FRACTIONAL_PRICE_ASSET] = FRACTIONAL_PRICE
    sigma = [
        [0.01 + float(row) / 10000.0 if row == column else float((row + column) % 7) / 100000.0
         for column in range(ASSET_COUNT)]
        for row in range(ASSET_COUNT)
    ]
    return {"mu": mu, "sigma": sigma, "prices": prices, "kappa_risk": 1.0,
            "k": 6.0, "c": 2.0, "b": 40.0, "lambda_ref": SYNTHETIC_LAMBDA_REF,
            "sectors": SYNTHETIC_MEMBERSHIP}


def coefficient_row(name: str) -> dict[str, float]:
    """One fixed synthetic coefficient row; no ledger is consulted."""
    _require(name in COEFFICIENT_ROWS, "unknown coefficient row")
    values = {field: float.fromhex(word) for field, word in zip(COEFFICIENT_FIELDS, COEFFICIENT_ROWS[name])}
    for field, value in values.items():
        _require(value == value and value not in (float("inf"), float("-inf")),
                 f"coefficient {field} must be finite")
    _require(values["sector_slack"] > 0.0 and values["budget_slack"] > 0.0,
             "active-CSB slack coefficients must be strictly positive")
    return values


# --- canonical order, residuals, registers -----------------------------------

def coefficient_record(values: Mapping[str, object]) -> dict[str, float]:
    """Validate an explicit binary64 coefficient record: all seven fields.

    This is the generic entry: a caller supplies its own record and never has
    to go through the synthetic row-name table.
    """
    _require(isinstance(values, Mapping), "coefficient record must be a mapping")
    _require(set(values) == set(COEFFICIENT_FIELDS), "coefficient record has wrong field set")
    record = {field: _finite(values[field], f"coefficient {field}") for field in COEFFICIENT_FIELDS}
    _require(record["sector_slack"] > 0.0 and record["budget_slack"] > 0.0,
             "active-CSB slack coefficients must be strictly positive")
    return record


_DECLARED = object()


def resolve_coefficients(coefficients) -> tuple[dict[str, float], str | None]:
    """Accept a validated record, or a synthetic row name; never a bare tuple."""
    if isinstance(coefficients, str):
        return coefficient_row(coefficients), coefficients
    return coefficient_record(coefficients), None


def declared_control(row: str | None, encoding: str) -> dict[int, float]:
    """The synthetic control table, which exists only for qualification."""
    if row is None:
        return {}
    return dict(zip(CONTROL_POSITIONS[encoding], control_offsets(row, encoding)))


def canonical_bits(index: int) -> tuple[int, ...]:
    _require(type(index) is int and 0 <= index < STATE_COUNT, "decoded index is out of range")
    return tuple((index >> (DECODED_WIDTH - 1 - asset)) & 1 for asset in range(DECODED_WIDTH))


def register_maximum(register: int) -> int:
    _require(type(register) is int and 0 <= register < REGISTER_COUNT, "register index is out of range")
    bits = SECTOR_SLACK_BITS if register < SECTOR_COUNT else BUDGET_SLACK_BITS
    return (1 << bits) - 1


def register_offset(register: int) -> int:
    _require(type(register) is int and 0 <= register < REGISTER_COUNT, "register index is out of range")
    return register * SECTOR_SLACK_BITS if register < SECTOR_COUNT else SECTOR_COUNT * SECTOR_SLACK_BITS


def register_minimizers(residual: float, maximum: int) -> tuple[tuple[int, float], ...]:
    """Frozen rule with both fail-closed guards, as repaired in the cache."""
    residual = _finite(residual, "residual")
    if residual < 0.0:
        candidates = [0]
    elif residual >= float(maximum):
        candidates = [maximum]
    else:
        lower = int(residual)
        if float(lower) > residual:
            lower -= 1
        candidates = sorted({min(max(lower, 0), maximum), min(max(lower + 1, 0), maximum)})
    scored = []
    for value in candidates:
        delta = residual - float(value)
        penalty = delta * delta
        _require(not _is_nonfinite(penalty), "non-finite slack-minimizer penalty")
        scored.append((value, penalty))
    best = min(penalty for _, penalty in scored)
    return tuple((value, penalty) for value, penalty in scored if penalty == best)


def register_values_for_state(sector_residuals: Sequence[float], budget_residual: float,
                              minimizers=None) -> tuple[tuple[int, ...], ...]:
    """Per-register minimizer values in frozen register order, sector 0 first."""
    chooser = register_minimizers if minimizers is None else minimizers
    values = [tuple(value for value, _ in chooser(residual, register_maximum(register)))
              for register, residual in enumerate(sector_residuals)]
    values.append(tuple(value for value, _
                        in chooser(budget_residual, register_maximum(SECTOR_COUNT))))
    return tuple(values)


def packed_lift_masks(register_values: Sequence[Sequence[int]]):
    """Yield the frozen 19-bit packed masks in declared Cartesian-product order.

    Register order is sector 0 slowest ... budget fastest, which is exactly
    ``itertools.product`` over the registers in order.  This is the single
    definition of the cache's lift order: the builder's layout digest and the
    frozen-authority verifier both consume it, so an inverted or dropped tied
    minimizer is observable even though tied minimizers carry equal penalties
    and therefore leave every energy unchanged.
    """
    for combination in itertools.product(*register_values):
        mask = 0
        for register, value in enumerate(combination):
            mask |= value << register_offset(register)
        yield mask


def lift_mask_digest(domain: Mapping[str, object], start: int, stop: int) -> tuple[int, int]:
    """Fold the builder's packed masks over ``[start, stop)``; also count them."""
    _require(type(start) is int and type(stop) is int and 0 <= start <= stop <= STATE_COUNT,
             "lift-mask interval is out of range")
    sector_residual = domain["sector_residual"]
    budget_residual = domain["budget_residual"]
    digest, produced = FNV_OFFSET, 0
    for index in range(start, stop):
        values = register_values_for_state(
            [sector_residual[sector][index] for sector in range(SECTOR_COUNT)],
            budget_residual[index])
        for mask in packed_lift_masks(values):
            digest = _fnv(digest, mask)
            produced += 1
    return digest, produced


def prepared_terms(payload: Mapping[str, object], index: int) -> tuple[float, ...]:
    """Literal frozen transcript for one decoded state; the fixtures' reference."""
    sectors = payload["sectors"]
    x = [float(bit) for bit in canonical_bits(index)]
    f_value = +0.0
    for asset in range(ASSET_COUNT):
        f_value = f_value + (-(float(payload["mu"][asset]) * x[asset]))
    for row in range(ASSET_COUNT):
        for column in range(ASSET_COUNT):
            sigma_x = float(payload["sigma"][row][column]) * x[row]
            f_value = f_value + (float(payload["kappa_risk"]) * (sigma_x * x[column]))
    cardinality = +0.0
    for asset in range(ASSET_COUNT):
        cardinality = cardinality + x[asset]
    h_card = cardinality - float(payload["k"])
    h_sector: list[float] = []
    sector_square: list[float] = []
    for block in sectors:
        total = +0.0
        for member in block:
            total = total + x[member]
        residual = float(payload["c"]) - total
        h_sector.append(residual)
        sector_square.append(residual * residual)
    budget = +0.0
    for asset in range(ASSET_COUNT):
        budget = budget + (float(payload["prices"][asset]) * x[asset])
    h_budget = float(payload["b"]) - budget
    return (f_value, h_card * h_card, *h_sector, *sector_square, h_budget, h_budget * h_budget)


def _fast_objective(payload: Mapping[str, object], selected: Sequence[int]) -> float:
    """Frozen objective with the exactly-equivalent zero-term skip."""
    mu = payload["mu"]
    sigma = payload["sigma"]
    kappa = float(payload["kappa_risk"])
    accumulator = +0.0
    for asset in selected:
        accumulator = accumulator + (-(float(mu[asset]) * 1.0))
    for row in selected:
        sigma_row = sigma[row]
        for column in selected:
            sigma_x = float(sigma_row[column]) * 1.0
            accumulator = accumulator + (kappa * (sigma_x * 1.0))
    return accumulator


# --- energy transcripts ------------------------------------------------------

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


# --- frozen D015 -------------------------------------------------------------

def frozen_tau(y: float, y_min: float, c_h: float, lambda_ref: float) -> float:
    """D015 scale for one pair, with the instance's own lambda_ref."""
    maximum = max(abs(y), abs(y_min))
    scale = lambda_ref + maximum
    return (c_h * EPSILON) * scale


def frozen_tie(y: float, y_min: float, c_h: float, lambda_ref: float) -> bool:
    return abs(y - y_min) <= frozen_tau(y, y_min, c_h, lambda_ref)


def tie_flags(y: float, y_min: float, lambda_ref: float) -> int:
    """Frozen flags, short-circuiting on the exactly monotone loosest threshold.

    ``lambda_ref`` is the instance's own recomputed value and is required: the
    comparator holds no global fallback.
    """
    _require(type(lambda_ref) is float and lambda_ref > 0.0
             and not _is_nonfinite(lambda_ref),
             "lambda_ref must be finite and strictly positive")
    gap = abs(y - y_min)
    maximum = max(abs(y), abs(y_min))
    scale = lambda_ref + maximum
    if gap > (CH_VALUES[2] * EPSILON) * scale:
        return 0
    flags = 0
    for bit, c_h in enumerate(CH_VALUES):
        if gap <= (c_h * EPSILON) * scale:
            flags |= 1 << bit
    return flags


def flag_is_legal(flags: int) -> bool:
    return flags in LEGAL_FLAGS


def flag_violates_nesting(flags: int) -> bool:
    return (bool(flags & 1) and not flags & 2) or (bool(flags & 2) and not flags & 4)


# --- deterministic stable compaction -----------------------------------------

def compaction_chunk_count(word_count: int) -> int:
    _require(type(word_count) is int and word_count >= 0, "word count must be a non-negative int")
    return (word_count + COMPACTION_CHUNK_SIZE - 1) // COMPACTION_CHUNK_SIZE


def compact_flags(flag_bytes: Sequence[int]) -> dict[str, object]:
    """Stable ascending compaction of ``(flags << 32) | position`` entries.

    Deterministic by construction and free of atomics, shared-memory
    reductions and sorting: a fixed chunk count, then an exclusive prefix over
    those counts, then each chunk writes only its own slice, in ascending
    canonical position.  The result is audited against the flagged
    subsequence, so a mis-ordered, dropped or duplicated entry fails closed.
    """
    word_count = len(flag_bytes)
    chunks = compaction_chunk_count(word_count)
    counts = [0] * chunks
    for chunk in range(chunks):
        start = chunk * COMPACTION_CHUNK_SIZE
        stop = min(start + COMPACTION_CHUNK_SIZE, word_count)
        total = 0
        for position in range(start, stop):
            flags = flag_bytes[position]
            if flags:
                _require(flags in COMPACTED_FLAGS,
                         "a compacted entry carries an illegal flag word")
                total += 1
        counts[chunk] = total

    prefix = [0] * (chunks + 1)
    for chunk in range(chunks):
        prefix[chunk + 1] = prefix[chunk] + counts[chunk]
    produced = prefix[chunks]
    _require(produced <= MAX_COMPACTED_ENTRIES,
             "compacted entries exceed the declared hard cap")

    entries = array("Q", bytes(8 * produced))
    for chunk in range(chunks):
        cursor = prefix[chunk]
        start = chunk * COMPACTION_CHUNK_SIZE
        stop = min(start + COMPACTION_CHUNK_SIZE, word_count)
        for position in range(start, stop):
            flags = flag_bytes[position]
            if flags:
                _require(position < (1 << 32), "canonical index does not fit the entry word")
                entries[cursor] = (flags << 32) | position
                cursor += 1
        _require(cursor == prefix[chunk + 1],
                 "a compaction chunk wrote the wrong number of entries")

    # Fail-closed audit: the compacted stream must BE the flagged subsequence.
    expected = [position for position in range(word_count) if flag_bytes[position]]
    _require(len(expected) == produced, "the compacted count differs from the flagged count")
    previous = -1
    for slot, position in enumerate(expected):
        _require(entries[slot] == ((flag_bytes[position] << 32) | position),
                 "the compacted stream differs from the flagged subsequence")
        _require(position > previous, "compacted entries are not strictly ascending")
        previous = position

    checksum = FNV_OFFSET
    for slot in range(produced):
        checksum = _fnv(checksum, entries[slot])
    return {"entries": entries, "counts": tuple(counts), "prefix": tuple(prefix),
            "produced": produced, "checksum": checksum, "chunks": chunks}


# --- the full-domain scan ----------------------------------------------------

def build_domain(payload: Mapping[str, object]) -> dict[str, object]:
    """Prepared terms, the complete slack lift cache, and its capacity proof."""
    payload = validate_payload(payload)
    sectors = payload["sectors"]
    membership = [0] * ASSET_COUNT
    for sector, block in enumerate(sectors):
        for member in block:
            membership[member] = sector
    prices = payload["prices"]
    c_value, b_value, k_value = float(payload["c"]), float(payload["b"]), float(payload["k"])
    sector_max, budget_max = register_maximum(0), register_maximum(SECTOR_COUNT)

    minimizer_memo: dict[tuple[float, int], tuple[tuple[int, float], ...]] = {}

    def memo_minimizers(residual: float, maximum: int):
        key = (residual, maximum)
        found = minimizer_memo.get(key)
        if found is None:
            found = register_minimizers(residual, maximum)
            minimizer_memo[key] = found
        return found

    objective = array("d", bytes(8 * STATE_COUNT))
    card_square = array("d", bytes(8 * STATE_COUNT))
    sector_penalty = [array("d", bytes(8 * STATE_COUNT)) for _ in range(SECTOR_COUNT)]
    sector_residual = [array("d", bytes(8 * STATE_COUNT)) for _ in range(SECTOR_COUNT)]
    sector_square = [array("d", bytes(8 * STATE_COUNT)) for _ in range(SECTOR_COUNT)]
    budget_residual = array("d", bytes(8 * STATE_COUNT))
    budget_square = array("d", bytes(8 * STATE_COUNT))
    lift_counts = array("I", bytes(4 * STATE_COUNT))
    budget_penalties: list[tuple[float, ...]] = []
    packed_first = array("I", bytes(4 * STATE_COUNT))
    exact = clamped = tied = 0

    for index in range(STATE_COUNT):
        selected = [asset for asset in range(ASSET_COUNT) if (index >> (DECODED_WIDTH - 1 - asset)) & 1]
        objective[index] = _fast_objective(payload, selected)
        h_card = float(len(selected)) - k_value
        card_square[index] = h_card * h_card
        counts = [0] * SECTOR_COUNT
        for asset in selected:
            counts[membership[asset]] += 1
        multiplicity = 1
        packed = 0
        for sector in range(SECTOR_COUNT):
            residual = c_value - float(counts[sector])
            sector_residual[sector][index] = residual
            sector_square[sector][index] = residual * residual
            minimizers = memo_minimizers(residual, sector_max)
            # Fail closed: the declared contract forbids a tied sector
            # register, because the energy stage below emits only the budget
            # alternatives.  Never silently miscount the multiplicity.
            _require(len(minimizers) == 1,
                     f"sector[{sector}] register tied at state {index}: the integral-C "
                     "contract is violated and slack lifts would be unwritten")
            sector_penalty[sector][index] = minimizers[0][1]
            packed |= minimizers[0][0] << register_offset(sector)
            multiplicity *= len(minimizers)
            if len(minimizers) > 1:
                tied += 1
            if residual == float(int(residual)) and 0 <= residual <= sector_max:
                exact += 1
            else:
                clamped += 1
        spend = +0.0
        for asset in range(ASSET_COUNT):
            spend = spend + (float(prices[asset]) * (1.0 if (index >> (DECODED_WIDTH - 1 - asset)) & 1 else 0.0))
        residual = b_value - spend
        budget_residual[index] = residual
        budget_square[index] = residual * residual
        minimizers = memo_minimizers(residual, budget_max)
        budget_penalties.append(tuple(penalty for _, penalty in minimizers))
        packed |= minimizers[0][0] << register_offset(SECTOR_COUNT)
        packed_first[index] = packed
        multiplicity *= len(minimizers)
        if len(minimizers) > 1:
            tied += 1
        if residual == float(int(residual)) and 0 <= residual <= budget_max:
            exact += 1
        else:
            clamped += 1
        _require(multiplicity <= MAX_LIFTS_PER_STATE, "a decoded state exceeds the declared lift bound")
        lift_counts[index] = multiplicity

    # Fold every lift's packed word, in frozen cache order, into a layout
    # digest: this keeps the frozen 19-bit register layout load-bearing here
    # even though the energies consume the register penalties directly.
    lift_digest = FNV_OFFSET
    for index in range(STATE_COUNT):
        values = register_values_for_state(
            [sector_residual[sector][index] for sector in range(SECTOR_COUNT)],
            budget_residual[index], memo_minimizers)
        for mask in packed_lift_masks(values):
            lift_digest = _fnv(lift_digest, mask)

    lift_total = 0
    offsets = array("Q", bytes(8 * (STATE_COUNT + 1)))
    for index in range(STATE_COUNT):
        lift_total += lift_counts[index]
        _require(lift_total <= UINT64_MAX, "lift total overflowed")
        offsets[index + 1] = lift_total
    _require(lift_total <= CACHE_CAPACITY, "the lift total exceeds the declared capacity")
    return {"payload": payload, "objective": objective, "card_square": card_square,
            "sector_residual": sector_residual, "sector_square": sector_square,
            "sector_penalty": sector_penalty, "budget_residual": budget_residual,
            "budget_square": budget_square, "budget_penalties": budget_penalties,
            "lift_counts": lift_counts, "offsets": offsets, "lift_total": lift_total,
            "lift_digest": lift_digest,
            "packed_first": packed_first, "exact_registers": exact,
            "clamped_registers": clamped, "tied_registers": tied}


def natural_energies(domain: Mapping[str, object], coefficients, encoding: str):
    """Yield every natural energy word of one (record, encoding) in scan order.

    ``coefficients`` is a validated record mapping, or a synthetic row name.
    """
    coefficients, _name = resolve_coefficients(coefficients)
    objective = domain["objective"]
    card_square = domain["card_square"]
    alpha = coefficients["alpha"]
    if encoding == "unbalanced":
        sr, sq = domain["sector_residual"], domain["sector_square"]
        br, bq = domain["budget_residual"], domain["budget_square"]
        sl, sqc = coefficients["sector_linear"], coefficients["sector_quadratic"]
        bl, bqc = coefficients["budget_linear"], coefficients["budget_quadratic"]
        for index in range(STATE_COUNT):
            h = objective[index]
            h = h + (alpha * card_square[index])
            for sector in range(SECTOR_COUNT):
                h = h + ((-(sl * sr[sector][index])) + sqc * sq[sector][index])
            h = h + ((-(bl * br[index])) + bqc * bq[index])
            yield h
    else:
        penalties = domain["sector_penalty"]
        budget_penalties = domain["budget_penalties"]
        ssl, bsl = coefficients["sector_slack"], coefficients["budget_slack"]
        for index in range(STATE_COUNT):
            base = objective[index]
            base = base + (alpha * card_square[index])
            for sector in range(SECTOR_COUNT):
                base = base + (ssl * penalties[sector][index])
            for penalty in budget_penalties[index]:
                yield base + (bsl * penalty)


def control_offsets(row: str, encoding: str) -> tuple[float, ...]:
    _require((row, encoding) in CONTROL_OFFSETS, "unknown control row/encoding")
    return tuple(float.fromhex(word) for word in CONTROL_OFFSETS[(row, encoding)])


def scan(domain: Mapping[str, object], coefficients, encoding: str,
         control=_DECLARED) -> dict[str, object]:
    """Natural pass, then minima, flags, compaction and counters.

    ``coefficients`` is a validated record or a synthetic row name.  ``control``
    selects the synthetic control adjustment: omitted means "the declared table
    for this row name, or none for an anonymous record", and an explicit
    mapping (``{}`` for none) overrides it.  The generic core runs with no
    controls at all.
    """
    values, name = resolve_coefficients(coefficients)
    _require(encoding in ENCODINGS, "unknown encoding")
    if control is _DECLARED:
        control = declared_control(name, encoding)
    _require(isinstance(control, Mapping), "control must be a mapping of position to offset")
    control = {int(position): _finite(offset, "control offset")
               for position, offset in control.items()}
    _require(all(offset >= 0.0 for offset in control.values()),
             "control offsets must be non-negative")
    coefficients = values
    lambda_ref = domain["payload"]["lambda_ref"]
    natural_checksum = FNV_OFFSET
    natural_minimum = None
    natural_index = -1
    nonfinite = 0
    for position, value in enumerate(natural_energies(domain, coefficients, encoding)):
        natural_checksum = _fnv(natural_checksum, _word(value))
        if _is_nonfinite(value):
            nonfinite += 1
            continue
        if natural_minimum is None or value < natural_minimum:
            natural_minimum = value
            natural_index = position
    _require(natural_minimum is not None, "every natural energy was non-finite")

    controlled_checksum = FNV_OFFSET
    flags_checksum = FNV_OFFSET
    per_ch = [0, 0, 0]
    illegal = nesting = 0
    current_value = None
    current_index = -1
    segment_best: list[tuple[float, int]] = []
    segment_value = None
    segment_index = -1
    word_count = 0
    flag_bytes = array("B")
    # Control offsets are non-negative and anchored to the natural minimum, so
    # the controlled minimum *value* is the natural minimum; only the first-seen
    # winner and the flag population can change.  Flags can therefore be scored
    # in this same pass, and no full-domain energy buffer is retained.
    loosest = (CH_VALUES[2] * EPSILON)
    for position, value in enumerate(natural_energies(domain, coefficients, encoding)):
        if position in control:
            value = natural_minimum + control[position]
        controlled_checksum = _fnv(controlled_checksum, _word(value))
        if _is_nonfinite(value):
            nonfinite += 1
        else:
            if current_value is None or value < current_value:
                current_value = value
                current_index = position
            if segment_value is None or value < segment_value:
                segment_value = value
                segment_index = position
        flags = tie_flags(value, natural_minimum, lambda_ref)
        flags_checksum = _fnv(flags_checksum, flags)
        flag_bytes.append(flags)
        if not flag_is_legal(flags):
            illegal += 1
        if flag_violates_nesting(flags):
            nesting += 1
        for bit in range(len(CH_VALUES)):
            if flags & (1 << bit):
                per_ch[bit] += 1
        word_count += 1
        if word_count % SEGMENT_SIZE == 0:
            segment_best.append((segment_value, segment_index))
            segment_value = None
            segment_index = -1
    if segment_value is not None:
        segment_best.append((segment_value, segment_index))
    _require(nonfinite == 0, "a non-finite energy word was produced")
    _require(loosest > 0.0, "the loosest D015 multiplier must be positive")

    # Fixed-order merge over deterministic contiguous segments: the earliest
    # segment wins an exact tie because the merge uses strict '<'.
    minimum = None
    minimum_index = -1
    for value, index in segment_best:
        if minimum is None or value < minimum:
            minimum = value
            minimum_index = index
    _require(minimum == current_value and minimum_index == current_index,
             "the segmented reduction disagrees with the serial scan")
    _require(minimum == natural_minimum,
             "the controlled minimum moved away from the natural minimum")
    _require(len(flag_bytes) == word_count, "the flag stream and the word stream disagree")
    compaction = compact_flags(flag_bytes)
    return {"compacted_entries": compaction["entries"],
            "compaction_counts": compaction["counts"],
            "compaction_prefix": compaction["prefix"],
            "compacted_count": compaction["produced"],
            "compaction_checksum": compaction["checksum"],
            "compaction_chunks": compaction["chunks"],
            "natural_checksum": natural_checksum, "natural_minimum": natural_minimum,
            "natural_index": natural_index, "controlled_checksum": controlled_checksum,
            "flags_checksum": flags_checksum, "minimum": minimum, "minimum_index": minimum_index,
            "per_ch": tuple(per_ch), "illegal": illegal, "nesting": nesting,
            "word_count": word_count}


def run_core(payload: Mapping[str, object], records: Sequence[Mapping[str, object]],
             *, controls: Mapping[tuple[int, str], Mapping[int, float]] | None = None,
             encodings: Sequence[str] = ENCODINGS) -> dict[str, object]:
    """Generic in-memory core: validated payload + explicit records in.

    No parser, ledger reader, generator, writer, real input or instance is
    involved, and nothing is read from or written to disk.  The caller supplies
    an arbitrary sorted 4x5 membership and its own binary64 coefficient
    records; ``controls`` is the synthetic qualification adjustment and is
    absent (no controls at all) in the generic mode.

    Only BOUNDED summaries come back: per-stream minima, integer counters, and
    the compacted canonical tie entries (at most ``MAX_COMPACTED_ENTRIES``).
    No full energy or flag stream is returned, so a caller can reconstruct only
    from the compact entries.
    """
    payload = validate_payload(payload)
    records = tuple(coefficient_record(record) for record in records)
    _require(len(records) >= 1, "at least one coefficient record is required")
    for encoding in encodings:
        _require(encoding in ENCODINGS, "unknown encoding")
    domain = build_domain(payload)
    summaries: dict[tuple[int, str], dict[str, object]] = {}
    for slot, record in enumerate(records):
        for encoding in encodings:
            control = {} if controls is None else controls.get((slot, encoding), {})
            data = scan(domain, record, encoding, control=control)
            entries = tuple(data["compacted_entries"])
            _require(len(entries) <= MAX_COMPACTED_ENTRIES, "compaction exceeded the declared cap")
            summaries[(slot, encoding)] = {
                "word_count": data["word_count"],
                "minimum": data["minimum"], "minimum_index": data["minimum_index"],
                "per_ch": data["per_ch"], "illegal": data["illegal"], "nesting": data["nesting"],
                "compacted_count": data["compacted_count"],
                "compaction_chunks": data["compaction_chunks"],
                "compaction_checksum": data["compaction_checksum"],
                "compacted_entries": entries,
            }
    return {"lift_total": domain["lift_total"], "record_count": len(records),
            "summaries": summaries}


def expected_self_test(scans: Mapping[tuple[str, str], Mapping[str, object]] | None = None,
                       domain: Mapping[str, object] | None = None,
                       generic: Mapping[tuple[str, str], Mapping[str, object]] | None = None) -> dict[str, object]:
    """Reproduce every device checksum and counter from the full-domain scan."""
    built = build_domain(synthetic_payload()) if domain is None else domain
    if scans is None:
        scans = {(row, encoding): scan(built, row, encoding)
                 for row in ROW_NAMES for encoding in ENCODINGS}
    if generic is None:
        # The same core with NO synthetic controls: this is the generic path,
        # and it is exercised rather than derived from the controlled one.
        generic = {(row, encoding): scan(built, coefficient_row(row), encoding, control={})
                   for row in ROW_NAMES for encoding in ENCODINGS}
    membership_digest = FNV_OFFSET
    for block in built["payload"]["sectors"]:
        for member in block:
            for byte in struct.pack("<I", int(member)):
                membership_digest = _fnv(membership_digest, byte)
    coefficient_digest = FNV_OFFSET
    for row in ROW_NAMES:
        values = coefficient_row(row)
        for field in COEFFICIENT_FIELDS:
            coefficient_digest = _fnv(coefficient_digest, _word(values[field]))
    control_digest = FNV_OFFSET
    for row in ROW_NAMES:
        for encoding in ENCODINGS:
            for position, offset in zip(CONTROL_POSITIONS[encoding], control_offsets(row, encoding)):
                control_digest = _fnv(control_digest, position)
                control_digest = _fnv(control_digest, _word(offset))
    report: dict[str, object] = {
        "schema": SCHEMA, "decoded_width": DECODED_WIDTH, "state_count": STATE_COUNT,
        "segment_size": SEGMENT_SIZE, "segment_count": SEGMENT_COUNT,
        "register_count": REGISTER_COUNT, "auxiliary_bits": AUXILIARY_BITS,
        "row_count": len(ROW_NAMES), "lift_total": built["lift_total"],
        "cache_capacity": CACHE_CAPACITY,
        "membership_digest": f"{membership_digest:016x}",
        "lift_digest": f"{built['lift_digest']:016x}",
        "coefficient_digest": f"{coefficient_digest:016x}",
        "control_digest": f"{control_digest:016x}",
        "exact_registers": built["exact_registers"], "clamped_registers": built["clamped_registers"],
        "tied_registers": built["tied_registers"],
        "compaction_chunk_size": COMPACTION_CHUNK_SIZE,
        "max_compacted_entries": MAX_COMPACTED_ENTRIES,
        "compaction_order_violations": 0, "compaction_mismatches": 0,
        "compaction_overflows": 0, "generic_disagreements": 0,
        "reconstruction_mismatches": 0,
        "lambda_ref_checksum": f"{_fnv(FNV_OFFSET, _word(built['payload']['lambda_ref'])):016x}",
        "nonfinite_energies": 0, "reduction_disagreements": 0,
        "illegal_flag_entries": 0, "nesting_violations": 0,
        "scientific_outputs": "intentionally absent",
    }
    for row in ROW_NAMES:
        for encoding in ENCODINGS:
            data = scans[(row, encoding)]
            key = f"{row}_{encoding}"
            report[f"natural_energy_checksum_{key}"] = f"{data['natural_checksum']:016x}"
            report[f"controlled_energy_checksum_{key}"] = f"{data['controlled_checksum']:016x}"
            report[f"flags_checksum_{key}"] = f"{data['flags_checksum']:016x}"
            report[f"minimum_checksum_{key}"] = f"{_fnv(_fnv(FNV_OFFSET, _word(data['minimum'])), data['minimum_index']):016x}"
            report[f"word_count_{key}"] = data["word_count"]
            report[f"count_c_h_1024_{key}"] = data["per_ch"][0]
            report[f"count_c_h_2048_{key}"] = data["per_ch"][1]
            report[f"count_c_h_4096_{key}"] = data["per_ch"][2]
            report[f"compacted_count_{key}"] = data["compacted_count"]
            report[f"compaction_chunks_{key}"] = data["compaction_chunks"]
            report[f"compaction_checksum_{key}"] = f"{data['compaction_checksum']:016x}"
            plain = generic[(row, encoding)]
            report[f"generic_minimum_checksum_{key}"] = (
                f"{_fnv(_fnv(FNV_OFFSET, _word(plain['minimum'])), plain['minimum_index']):016x}")
            report[f"generic_compacted_count_{key}"] = plain["compacted_count"]
            report[f"generic_compaction_checksum_{key}"] = f"{plain['compaction_checksum']:016x}"
            report["illegal_flag_entries"] += data["illegal"]
            report["nesting_violations"] += data["nesting"]
    report["verdict"] = "pass"
    return report


def validate_self_test_report(payload: object, scans=None, domain=None,
                              generic=None) -> dict[str, object]:
    """Fail closed unless the device reproduces every expected field exactly."""
    expected = expected_self_test(scans, domain, generic)
    required = set(expected) | {"device_index", "device_name"}
    _require(isinstance(payload, dict) and set(payload) == required, "core-stream report has wrong key set")
    _require(type(payload["device_index"]) is int and payload["device_index"] >= 0
             and type(payload["device_name"]) is str and payload["device_name"],
             "core-stream device metadata malformed")
    for key, value in expected.items():
        if type(value) is int:
            _require(type(payload[key]) is int and type(payload[key]) is not bool,
                     f"core-stream integer field has wrong type: {key}")
    for key, value in payload.items():
        _require(not isinstance(value, (list, tuple, dict)), f"core-stream report carries a container: {key}")
        _require(not isinstance(value, bool), f"core-stream report carries a bool: {key}")
        _require(not isinstance(value, float), f"core-stream report carries a float: {key}")
    for key, value in expected.items():
        _require(payload[key] == value, f"core-stream self-test mismatch: {key}")
    return dict(payload)

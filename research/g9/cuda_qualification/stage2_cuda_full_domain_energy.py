"""Python reference for the synthetic full-domain energy / minimum / D015 scan.

This component consumes the reviewed full-domain cache semantics and evaluates,
over the *whole* canonical decoded domain (``2^20`` unbalanced states and the
complete active-CSB slack lift cache), both encodings' energies, deterministic
strict-first-seen minima, and frozen D015 flags at ``c_H in {1024, 2048,
4096}``, for two fixed synthetic coefficient rows.

It is isolated: no filesystem parser, no candidate draw, no real input, no
ledger, no writer, no NumPy.  The report carries synthetic checksums, integer
counters, fixed identity metadata and a verdict only — never an energy, a
minimum, an index, a tie list, a label, a rate or a record.

Frozen rules reproduced here, not invented:

* canonical decoded order ``x[i] = (index >> (19 - i)) & 1``
  (``src.g5.domains.BinaryDomain``);
* the residual transcript and the clamped floor/floor+1 minimizer rule with
  **every** tied minimizer retained, the frozen 19-bit register layout and the
  frozen Cartesian-product lift order (sector 0 slowest, budget fastest), with
  uint64 offsets and a capacity proof;
* the prepared-energy transcripts of ``src.g4.energy``: the objective first,
  then ``alpha * card_square``, then each sector family, then the budget
  family, every accumulator starting at ``+0.0``;
* D015: ``gap = abs(fl(y - y_min))``, ``scale = fl(lambda_ref + max(abs(y),
  abs(y_min)))``, ``tau = fl((c_H * eps) * scale)``, tie iff ``gap <= tau``.

Two optimisations are used, and both are *exact*, not approximations:

1. Objective terms whose ``x`` factor is zero are skipped.  Every such term is
   ``+-0.0`` and the accumulator starts at ``+0.0``, so adding them cannot
   change the value; the fixtures replay the literal 420-term fold to prove it.
2. Flags short-circuit when ``gap > tau(4096)``.  ``c_H`` is a power of two and
   ``eps = 2^-52``, so ``c_H * eps`` is exact and ``tau`` is exactly monotone in
   ``c_H``; failing the loosest threshold therefore fails all of them.

Synthetic control adjustment (declared, checksum-bound, never hidden).  The
natural landscape has unique minima and no near-ties, so for a small fixed set
of control positions per (row, encoding) the energy is replaced by
``natural_minimum + offset`` with exact binary64 offsets.  Offsets are
non-negative, so the controlled minimum *value* is the natural minimum; only
the first-seen winner and the flag population change.  A **natural pre-control
checksum over every full-domain word** is retained alongside the controlled
checksum, so a defect in a natural energy cannot hide behind a control.
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
LAMBDA_REF = float.fromhex("0x1p-5")
FNV_OFFSET, FNV_PRIME, MASK64 = 1469598103934665603, 1099511628211, (1 << 64) - 1
SCHEMA = "decisions_os/g9_cuda_full_domain_energy_self_test/v1"

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
# 40 and 41 tie inside segment 0; 1064 ties from segment 1, so the fixed
# order of the segmented merge, and its strict '<', are both load-bearing.
CONTROL_POSITIONS: dict[str, tuple[int, ...]] = {
    "unbalanced": (40, 41, 1064, 100, 101, 200, 201),
    "slack": (40, 41, 1064, 100, 101, 200, 201),
}
# Offsets calibrated per (row, encoding) so the frozen comparator yields the
# declared ladder; the fixtures assert the exact resulting flags.
CONTROL_OFFSETS: dict[tuple[str, str], tuple[str, ...]] = {
    ("row0", "unbalanced"): ("0x0p+0", "0x0p+0", "0x0p+0", "0x1p-43", "0x1p-42", "0x1p-41", "0x1p-40"),
    ("row0", "slack"): ("0x0p+0", "0x0p+0", "0x0p+0", "0x1p-47", "0x1p-46", "0x1p-45", "0x1p-44"),
    ("row1", "unbalanced"): ("0x0p+0", "0x0p+0", "0x0p+0", "0x1p-44", "0x1p-43", "0x1p-42", "0x1p-41"),
    ("row1", "slack"): ("0x0p+0", "0x0p+0", "0x0p+0", "0x1p-47", "0x1p-46", "0x1p-45", "0x1p-44"),
}
EXPECTED_CONTROL_FLAGS = (7, 7, 7, 7, 6, 4, 0)


class FullDomainEnergyError(RuntimeError):
    """Typed refusal for a malformed payload, coefficient row, or report."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FullDomainEnergyError(message)


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
    _require(set(payload) == {"mu", "sigma", "prices", "kappa_risk", "k", "c", "b", "sectors"},
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
    k_value, c_value, b_value = (_finite(payload[name], name) for name in ("k", "c", "b"))
    _require(float(int(k_value)) == k_value and 0 < int(k_value) <= ASSET_COUNT, "K must be an integer in range")
    _require(float(int(c_value)) == c_value and int(c_value) >= 0, "C must be a non-negative integer")
    return {"mu": mu, "sigma": sigma, "prices": prices, "kappa_risk": kappa,
            "k": k_value, "c": c_value, "b": b_value,
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
            "k": 6.0, "c": 2.0, "b": 40.0, "sectors": SYNTHETIC_MEMBERSHIP}


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

def frozen_tau(y: float, y_min: float, c_h: float) -> float:
    maximum = max(abs(y), abs(y_min))
    scale = LAMBDA_REF + maximum
    return (c_h * EPSILON) * scale


def frozen_tie(y: float, y_min: float, c_h: float) -> bool:
    return abs(y - y_min) <= frozen_tau(y, y_min, c_h)


def tie_flags(y: float, y_min: float) -> int:
    """Frozen flags, short-circuiting on the exactly monotone loosest threshold."""
    gap = abs(y - y_min)
    maximum = max(abs(y), abs(y_min))
    scale = LAMBDA_REF + maximum
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


def natural_energies(domain: Mapping[str, object], row: str, encoding: str):
    """Yield every natural energy word of one (row, encoding) in scan order."""
    coefficients = coefficient_row(row)
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


def scan(domain: Mapping[str, object], row: str, encoding: str) -> dict[str, object]:
    """Natural pass, then the controlled pass with minima, flags and counters."""
    positions = CONTROL_POSITIONS[encoding]
    offsets = control_offsets(row, encoding)
    natural_checksum = FNV_OFFSET
    natural_minimum = None
    natural_index = -1
    nonfinite = 0
    for position, value in enumerate(natural_energies(domain, row, encoding)):
        natural_checksum = _fnv(natural_checksum, _word(value))
        if _is_nonfinite(value):
            nonfinite += 1
            continue
        if natural_minimum is None or value < natural_minimum:
            natural_minimum = value
            natural_index = position
    _require(natural_minimum is not None, "every natural energy was non-finite")

    control = dict(zip(positions, offsets))
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
    # Control offsets are non-negative and anchored to the natural minimum, so
    # the controlled minimum *value* is the natural minimum; only the first-seen
    # winner and the flag population can change.  Flags can therefore be scored
    # in this same pass, and no full-domain energy buffer is retained.
    loosest = (CH_VALUES[2] * EPSILON)
    for position, value in enumerate(natural_energies(domain, row, encoding)):
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
        flags = tie_flags(value, natural_minimum)
        flags_checksum = _fnv(flags_checksum, flags)
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
    return {"natural_checksum": natural_checksum, "natural_minimum": natural_minimum,
            "natural_index": natural_index, "controlled_checksum": controlled_checksum,
            "flags_checksum": flags_checksum, "minimum": minimum, "minimum_index": minimum_index,
            "per_ch": tuple(per_ch), "illegal": illegal, "nesting": nesting,
            "word_count": word_count}


def expected_self_test(scans: Mapping[tuple[str, str], Mapping[str, object]] | None = None,
                       domain: Mapping[str, object] | None = None) -> dict[str, object]:
    """Reproduce every device checksum and counter from the full-domain scan."""
    built = build_domain(synthetic_payload()) if domain is None else domain
    if scans is None:
        scans = {(row, encoding): scan(built, row, encoding)
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
            report["illegal_flag_entries"] += data["illegal"]
            report["nesting_violations"] += data["nesting"]
    report["verdict"] = "pass"
    return report


def validate_self_test_report(payload: object, scans=None, domain=None) -> dict[str, object]:
    """Fail closed unless the device reproduces every expected field exactly."""
    expected = expected_self_test(scans, domain)
    required = set(expected) | {"device_index", "device_name"}
    _require(isinstance(payload, dict) and set(payload) == required, "energy report has wrong key set")
    _require(type(payload["device_index"]) is int and payload["device_index"] >= 0
             and type(payload["device_name"]) is str and payload["device_name"],
             "energy device metadata malformed")
    for key, value in expected.items():
        if type(value) is int:
            _require(type(payload[key]) is int and type(payload[key]) is not bool,
                     f"energy integer field has wrong type: {key}")
    for key, value in payload.items():
        _require(not isinstance(value, (list, tuple, dict)), f"energy report carries a container: {key}")
        _require(not isinstance(value, bool), f"energy report carries a bool: {key}")
        _require(not isinstance(value, float), f"energy report carries a float: {key}")
    for key, value in expected.items():
        _require(payload[key] == value, f"energy self-test mismatch: {key}")
    return dict(payload)

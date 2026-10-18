"""Python reference for the generic capacity-safe full-domain slack cache.

This component builds the complete active-CSB slack-domain cache over the whole
canonical decoded domain (``2^20`` positions) for a generic, validated,
in-memory 20-asset payload with four explicit sorted five-asset membership
lists.  There is no filesystem parser, no candidate draw, no coefficient
ledger, no energy, no minimum, no tie set, no label and no record: the cache
holds packed auxiliary registers and per-state offsets only.

Frozen rules reproduced here, not invented:

* canonical decoded order is ``src.g5.domains.BinaryDomain`` —
  ``x[i] = (index >> (width - 1 - i)) & 1``;
* residuals follow the frozen transcript order of
  ``src.g4.energy._residuals_from_bits``, each accumulator starting at ``+0.0``
  and each sector summed over its own sorted membership;
* a register admits exactly the clamped ``floor(h)`` / ``floor(h) + 1``
  candidates compared by exact binary64 ``(h - S)^2``, retaining *every* tied
  minimizer (``src.g5.domains._register_minimizers``);
* the lifts of one decoded state are the Cartesian product of the per-register
  minimizer sets in register order — sector 0 slowest, the budget register
  fastest — matching ``itertools.product(*sector_choices, budget_choices)`` in
  ``src.g5.domains.build_slack_domain_cache``;
* each lift packs into the frozen 19-bit layout: sector ``j`` occupies two
  little-endian bits at offset ``2j``, then eleven little-endian budget bits at
  offset 8.

Capacity safety.  Offsets and lift totals are 64-bit throughout.  The total is
proved to fit the declared capacity *before* any cache buffer is allocated or
written, multiplication is overflow-checked, and a non-finite residual is
refused before any narrowing conversion.

Performance note.  Residuals are obtained from split-half lookup tables and the
per-register minimizer sets from a memo keyed by the exact residual.  Both are
memoizations of the frozen functions, never substitutes: the fixtures replay
the literal frozen-order accumulation and the direct minimizer rule for every
distinct residual the payload produces, and the frozen-authority verifier
compares the complete cache element-by-element with
``src.g5.domains.build_slack_domain_cache``.
"""
from __future__ import annotations

from array import array
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
HALF_WIDTH = DECODED_WIDTH // 2
# Declared capacity for this component: at most 32 lifts per decoded state,
# i.e. every register tied.  The build refuses anything larger before it
# allocates, so the cache can never exceed this bound.
MAX_LIFTS_PER_STATE = 1 << REGISTER_COUNT
CACHE_CAPACITY = STATE_COUNT * MAX_LIFTS_PER_STATE
UINT64_MAX = (1 << 64) - 1
FNV_OFFSET_A, FNV_OFFSET_B = 1469598103934665603, 1099511628211
FNV_PRIME, MASK64 = 1099511628211, (1 << 64) - 1
DIGEST_TAG = b"G9-FULL-DOMAIN-SLACK-CACHE-V1\0"
SCHEMA = "decisions_os/g9_cuda_full_domain_cache_self_test/v1"

# Fixed synthetic non-contiguous balanced partition.
SYNTHETIC_MEMBERSHIP: tuple[tuple[int, ...], ...] = (
    (0, 6, 11, 15, 19),
    (1, 5, 10, 14, 18),
    (2, 7, 9, 13, 17),
    (3, 4, 8, 12, 16),
)
# One deliberately fractional price makes half-integer budget residuals — and
# therefore naturally tied budget registers — occur across the domain.
FRACTIONAL_PRICE_ASSET = 7
FRACTIONAL_PRICE = 2.5


class FullDomainCacheError(RuntimeError):
    """Typed refusal for a malformed payload, residual, or capacity request."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FullDomainCacheError(message)


# --- payload ----------------------------------------------------------------

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


def _finite(value: object, label: str) -> float:
    _require(type(value) in (int, float), f"{label} must be a real number")
    number = float(value)
    _require(number == number and number not in (float("inf"), float("-inf")), f"{label} must be finite")
    return number


def validate_payload(payload: Mapping[str, object]) -> dict[str, object]:
    """Validate the generic in-memory 20-asset payload; no file is opened."""
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


# --- canonical decoded order -------------------------------------------------

def canonical_bits(index: int) -> tuple[int, ...]:
    """Canonical decoded bits, identical to src.g5.domains.BinaryDomain[index]."""
    _require(type(index) is int and 0 <= index < STATE_COUNT, "decoded index is out of range")
    return tuple((index >> (DECODED_WIDTH - 1 - asset)) & 1 for asset in range(DECODED_WIDTH))


# --- frozen residual transcript ----------------------------------------------

def frozen_residuals(payload: Mapping[str, object], index: int) -> tuple[tuple[float, ...], float]:
    """Literal frozen-order residuals; the reference for the fast tables."""
    sectors = payload["sectors"]
    x = [float(bit) for bit in canonical_bits(index)]
    h_sector: list[float] = []
    for block in sectors:
        total = +0.0
        for member in block:
            total = total + x[member]
        h_sector.append(float(payload["c"]) - total)
    budget = +0.0
    for asset in range(ASSET_COUNT):
        budget = budget + (float(payload["prices"][asset]) * x[asset])
    return tuple(h_sector), float(payload["b"]) - budget


def _half_tables(payload: Mapping[str, object]) -> tuple[list[tuple[int, ...]], list[float],
                                                          list[tuple[int, ...]], list[float]]:
    """Split-half sector counts and *prefix* price sums, in canonical positions.

    Canonical order is ``x[asset] = (index >> (19 - asset)) & 1``, so assets
    0..9 live in the *high* half of the decoded index and assets 10..19 in the
    *low* half.  The first pair returned is therefore indexed by
    ``index >> 10`` and the second by ``index & 1023``; within a half, the
    k-th asset is bit ``9 - k`` of the pattern.

    Sector entries are integer counts of at most five ones, so combining two
    halves is exact and cannot change the frozen transcript.  The price entries
    are **not** interchangeable that way: binary64 addition does not
    reassociate, so the first price table holds the genuine left-to-right
    *prefix* after asset 9 — the exact intermediate the frozen fold reaches —
    and the second price table is retained for diagnostics only.  The
    authoritative budget residual is produced by ``budget_residual``, which
    continues that prefix asset by asset; nothing in the cache path ever adds
    two independently accumulated price sums.
    """
    sectors = payload["sectors"]
    membership = [0] * ASSET_COUNT
    for sector, block in enumerate(sectors):
        for member in block:
            membership[member] = sector
    prices = payload["prices"]
    tables = []
    for half in range(2):
        counts_table: list[tuple[int, ...]] = []
        spend_table: list[float] = []
        for pattern in range(1 << HALF_WIDTH):
            counts = [0] * SECTOR_COUNT
            spend = +0.0
            for bit in range(HALF_WIDTH):
                asset = half * HALF_WIDTH + bit
                if (pattern >> (HALF_WIDTH - 1 - bit)) & 1:
                    counts[membership[asset]] += 1
                # Accumulate in asset order, including the zero terms the
                # frozen fold also visits, so the first half's entry is the
                # exact left-to-right prefix after asset 9.
                spend = spend + (float(prices[asset]) * (1.0 if (pattern >> (HALF_WIDTH - 1 - bit)) & 1 else 0.0))
            counts_table.append(tuple(counts))
            spend_table.append(spend)
        tables.append((counts_table, spend_table))
    return tables[0][0], tables[0][1], tables[1][0], tables[1][1]


def budget_residual(payload: Mapping[str, object], index: int, prefix_table: Sequence[float] | None = None) -> float:
    """Authoritative budget residual: the literal frozen left-to-right fold.

    ``prefix_table`` may supply the exact accumulated value after asset 9 (the
    frozen fold's own intermediate); assets 10..19 are then folded in one at a
    time.  Passing ``None`` recomputes the whole fold from ``+0.0``.  No two
    independently accumulated price sums are ever added.
    """
    prices = payload["prices"]
    if prefix_table is None:
        budget = +0.0
        start = 0
    else:
        budget = prefix_table[index >> HALF_WIDTH]
        start = HALF_WIDTH
    for asset in range(start, ASSET_COUNT):
        bit = 1.0 if (index >> (DECODED_WIDTH - 1 - asset)) & 1 else 0.0
        budget = budget + (float(prices[asset]) * bit)
    return float(payload["b"]) - budget


# --- frozen per-register minimizer rule --------------------------------------

def _floor_double(value: float) -> int:
    _finite(value, "residual")
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


def register_minimizers(residual: float, maximum: int) -> tuple[int, ...]:
    """Frozen rule: clamped floor/floor+1, every tied minimizer retained.

    Two fail-closed guards match ``src.g5.domains._register_minimizers``
    exactly.  A non-finite residual is refused before any conversion, and the
    residual is narrowed only inside ``[0, maximum)``, the one range where the
    floor is needed: below it both candidates clamp to ``0`` and at or above it
    both clamp to ``maximum``, so no cast is required.  The squared penalty is
    then computed for the surviving candidates and a non-finite penalty is
    refused, so an extreme finite residual such as ``1e200`` fails here just as
    it does in the frozen rule instead of silently returning an endpoint.
    """
    residual = _finite(residual, "residual")
    if residual < 0.0:
        candidates = [0]
    elif residual >= float(maximum):
        candidates = [maximum]
    else:
        lower = _floor_double(residual)
        candidates = sorted({min(max(lower, 0), maximum), min(max(lower + 1, 0), maximum)})
    scored = []
    for value in candidates:
        delta = residual - float(value)
        penalty = delta * delta
        _require(penalty == penalty and penalty != float("inf"),
                 "non-finite slack-minimizer penalty")
        scored.append((value, penalty))
    best = min(penalty for _, penalty in scored)
    return tuple(value for value, penalty in scored if penalty == best)


def register_is_exactly_representable(residual: float, maximum: int) -> bool:
    """Exactness, narrowing the residual only where that is safe."""
    residual = _finite(residual, "residual")
    if residual < 0.0 or residual > float(maximum):
        return False
    lower = _floor_double(residual)
    return float(lower) == residual and 0 <= lower <= maximum


def pack_lift(values: Sequence[int]) -> int:
    """Frozen 19-bit layout: sector j at 2j, budget at 8."""
    _require(len(values) == REGISTER_COUNT, "a lift needs one value per register")
    packed = 0
    for register, value in enumerate(values):
        maximum = register_maximum(register)
        _require(type(value) is int and 0 <= value <= maximum, f"register[{register}] value out of range")
        packed |= value << register_offset(register)
    return packed


# --- capacity safety ---------------------------------------------------------

def capacity_total(states: int, per_state: int, capacity: int) -> int | None:
    """64-bit overflow-checked capacity proof; ``None`` means refuse."""
    _require(type(states) is int and states >= 0, "state count must be a non-negative integer")
    _require(type(per_state) is int and per_state >= 0, "per-state multiplicity must be non-negative")
    _require(type(capacity) is int and capacity >= 0, "capacity must be non-negative")
    if per_state != 0 and states > UINT64_MAX // per_state:
        return None
    total = states * per_state
    if total > UINT64_MAX or total > capacity:
        return None
    return total


def capacity_probe_table() -> tuple[tuple[int, int, int], ...]:
    """Fixed probes: accepted, over-capacity, and multiplication-overflow cases."""
    return (
        (STATE_COUNT, 1, CACHE_CAPACITY),
        (STATE_COUNT, MAX_LIFTS_PER_STATE, CACHE_CAPACITY),
        (STATE_COUNT, MAX_LIFTS_PER_STATE + 1, CACHE_CAPACITY),
        (STATE_COUNT, 1 << 44, CACHE_CAPACITY),
        (1 << 62, 1 << 32, CACHE_CAPACITY),
        (UINT64_MAX, 2, CACHE_CAPACITY),
        (0, 5, CACHE_CAPACITY),
    )


# --- the complete cache ------------------------------------------------------

def build_cache(payload: Mapping[str, object]) -> dict[str, object]:
    """Build the complete active-CSB slack cache over all 2^20 decoded states."""
    payload = validate_payload(payload)
    first_counts, first_spend, second_counts, second_spend = _half_tables(payload)
    c_value, b_value = float(payload["c"]), float(payload["b"])
    sector_max, budget_max = register_maximum(0), register_maximum(SECTOR_COUNT)

    sector_memo: dict[float, tuple[int, ...]] = {}
    budget_memo: dict[float, tuple[int, ...]] = {}
    counts = array("I", bytes(4 * STATE_COUNT))
    exact = clamped = tied = 0
    residual_values: set[float] = set()

    # Pass 1: per-state multiplicity, with the capacity proof before allocation.
    for index in range(STATE_COUNT):
        first, second = index >> HALF_WIDTH, index & ((1 << HALF_WIDTH) - 1)
        lc, hc = first_counts[first], second_counts[second]
        multiplicity = 1
        for sector in range(SECTOR_COUNT):
            residual = c_value - float(lc[sector] + hc[sector])
            choices = sector_memo.get(residual)
            if choices is None:
                choices = register_minimizers(residual, sector_max)
                sector_memo[residual] = choices
                residual_values.add(residual)
            multiplicity *= len(choices)
            if register_is_exactly_representable(residual, sector_max):
                exact += 1
            else:
                clamped += 1
            if len(choices) > 1:
                tied += 1
        residual = budget_residual(payload, index, first_spend)
        choices = budget_memo.get(residual)
        if choices is None:
            choices = register_minimizers(residual, budget_max)
            budget_memo[residual] = choices
            residual_values.add(residual)
        multiplicity *= len(choices)
        if register_is_exactly_representable(residual, budget_max):
            exact += 1
        else:
            clamped += 1
        if len(choices) > 1:
            tied += 1
        _require(multiplicity <= MAX_LIFTS_PER_STATE, "a decoded state exceeds the declared lift bound")
        counts[index] = multiplicity

    total = 0
    for index in range(STATE_COUNT):
        total += counts[index]
    _require(capacity_total(1, total, CACHE_CAPACITY) is not None,
             "the cache total exceeds the declared capacity")

    # Pass 2: exclusive 64-bit offsets, then the packed lifts.
    offsets = array("Q", bytes(8 * (STATE_COUNT + 1)))
    running = 0
    for index in range(STATE_COUNT):
        running += counts[index]
        _require(running <= UINT64_MAX, "offset accumulator overflowed")
        offsets[index + 1] = running
    _require(offsets[STATE_COUNT] == total, "prefix total disagrees with the counted total")

    masks = array("I", bytes(4 * total))
    unsorted_ranges = duplicate_lifts = 0
    for index in range(STATE_COUNT):
        first, second = index >> HALF_WIDTH, index & ((1 << HALF_WIDTH) - 1)
        lc, hc = first_counts[first], second_counts[second]
        sector_choices = [sector_memo[c_value - float(lc[sector] + hc[sector])] for sector in range(SECTOR_COUNT)]
        budget_choices = budget_memo[budget_residual(payload, index, first_spend)]
        cursor = offsets[index]
        # Register order: sector 0 slowest, budget fastest — the frozen product.
        for value0 in sector_choices[0]:
            for value1 in sector_choices[1]:
                for value2 in sector_choices[2]:
                    for value3 in sector_choices[3]:
                        for budget in budget_choices:
                            masks[cursor] = (value0 | (value1 << 2) | (value2 << 4)
                                             | (value3 << 6) | (budget << 8))
                            cursor += 1
        _require(cursor == offsets[index + 1], "a decoded state wrote the wrong number of lifts")
        previous = -1
        for slot in range(offsets[index], offsets[index + 1]):
            value = masks[slot]
            if value == previous:
                duplicate_lifts += 1
            if value <= previous:
                unsorted_ranges += 1
            previous = value
    return {"payload": payload, "counts": counts, "offsets": offsets, "masks": masks, "total": total,
            "exact_registers": exact, "clamped_registers": clamped, "tied_registers": tied,
            "unsorted_ranges": unsorted_ranges, "duplicate_lifts": duplicate_lifts,
            "distinct_residuals": residual_values}


def _fnv(state: int, byte: int) -> int:
    return ((state ^ byte) * FNV_PRIME) & MASK64


def cache_digest(offsets: Sequence[int], masks: Sequence[int], total: int) -> str:
    """Deterministic two-lane FNV checksum over explicit little-endian bytes.

    This is a **synthetic corruption checksum only**.  It is not SHA-256, not a
    cryptographic hash, and must never be described or relied upon as a
    provenance or content identity: it exists so this self-test notices a
    changed offset or packed lift.  Endianness-independent by construction —
    every integer is serialised with an explicit ``<`` struct format before it
    enters the checksum.
    """
    low, high = FNV_OFFSET_A, FNV_OFFSET_B
    header = DIGEST_TAG + struct.pack("<IIIIQ", DECODED_WIDTH, SECTOR_COUNT, SECTOR_SLACK_BITS,
                                      BUDGET_SLACK_BITS, total)
    for byte in header:
        low = _fnv(low, byte)
        high = _fnv(high, byte ^ 0xFF)
    for offset in offsets:
        for byte in struct.pack("<Q", int(offset)):
            low = _fnv(low, byte)
            high = _fnv(high, byte ^ 0xFF)
    for mask in masks:
        for byte in struct.pack("<I", int(mask)):
            low = _fnv(low, byte)
            high = _fnv(high, byte ^ 0xFF)
    return f"{low:016x}{high:016x}"


def expected_self_test(cache: Mapping[str, object] | None = None) -> dict[str, object]:
    """Reproduce every device checksum, cardinality and capacity counter.

    The digest spans about 14 MB of logical integers, so the finished report is
    memoised on the cache object it was derived from; repeatedly validating the
    same cache is then free.  A freshly built cache always recomputes it.
    """
    built = build_cache(synthetic_payload()) if cache is None else cache
    memo = built.get("_expected_report") if isinstance(built, dict) else None
    if memo is not None:
        return dict(memo)
    # Byte-wise little-endian, exactly as the device digests each member.
    membership_digest = FNV_OFFSET_A
    for block in built["payload"]["sectors"]:
        for member in block:
            for byte in struct.pack("<I", int(member)):
                membership_digest = _fnv(membership_digest, byte)
    accepts = rejects = 0
    probe_digest = FNV_OFFSET_A
    for states, per_state, capacity in capacity_probe_table():
        total = capacity_total(states, per_state, capacity)
        probe_digest = _fnv(probe_digest, 1 if total is None else 0)
        for byte in struct.pack("<Q", 0 if total is None else total):
            probe_digest = _fnv(probe_digest, byte)
        if total is None:
            rejects += 1
        else:
            accepts += 1
    report: dict[str, object] = {"schema": SCHEMA, "decoded_width": DECODED_WIDTH, "state_count": STATE_COUNT,
            "register_count": REGISTER_COUNT, "auxiliary_bits": AUXILIARY_BITS,
            "max_lifts_per_state": MAX_LIFTS_PER_STATE, "cache_capacity": CACHE_CAPACITY,
            "membership_digest": f"{membership_digest:016x}",
            "cache_digest": cache_digest(built["offsets"], built["masks"], built["total"]),
            "capacity_probe_digest": f"{probe_digest:016x}",
            "lift_total": built["total"], "exact_registers": built["exact_registers"],
            "clamped_registers": built["clamped_registers"], "tied_registers": built["tied_registers"],
            "unsorted_ranges": built["unsorted_ranges"], "duplicate_lifts": built["duplicate_lifts"],
            "capacity_accepts": accepts, "capacity_rejects": rejects,
            "invalid_residuals": 0, "scientific_outputs": "intentionally absent", "verdict": "pass"}
    if isinstance(built, dict):
        built["_expected_report"] = dict(report)
    return dict(report)


def validate_self_test_report(payload: object, cache: Mapping[str, object] | None = None) -> dict[str, object]:
    """Fail closed unless the device reproduces every expected field exactly."""
    expected = expected_self_test(cache)
    required = set(expected) | {"device_index", "device_name"}
    _require(isinstance(payload, dict) and set(payload) == required, "cache report has wrong key set")
    _require(type(payload["device_index"]) is int and payload["device_index"] >= 0
             and type(payload["device_name"]) is str and payload["device_name"],
             "cache device metadata malformed")
    for key, value in expected.items():
        if type(value) is int:
            _require(type(payload[key]) is int, f"cache integer field has wrong type: {key}")
    for key, value in payload.items():
        _require(not isinstance(value, (list, tuple, dict)), f"cache report carries a container: {key}")
    for key, value in expected.items():
        _require(payload[key] == value, f"cache self-test mismatch: {key}")
    return dict(payload)

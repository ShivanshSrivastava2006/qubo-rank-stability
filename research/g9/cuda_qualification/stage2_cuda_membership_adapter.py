"""Python reference for the generic arbitrary-membership prepared-domain adapter.

This module is a *generic* transcript: the four sectors are supplied as four
explicit sorted five-asset membership lists, never as the contiguous
``sector * 5 + offset`` blocks assumed by
``stage2_cuda_preparation.py``.  It is deliberately isolated from canonical
inputs, ledgers, solvers and NumPy, and it operates only on the fixed
synthetic instance and fixed synthetic non-contiguous partition defined below.

Authoritative lift policy (not invented here).  ``FROZEN_MATH_SPEC.md`` §5.1
states that ``C_slack`` contains exactly the slack lifts *whose every
auxiliary register is an exact minimizer for its decoded x*; a numerically
near-minimal lift is excluded.  ``src/g5/domains.py::_register_minimizers``
implements that rule per register: the candidates are ``floor(h)`` and
``floor(h) + 1``, each clamped into ``[0, 2^N - 1]``; their exact binary64
penalties ``(h - S)^2`` are compared; and *every* tied minimizer is retained,
so a register may contribute two lifts.  Two consequences are recorded
explicitly rather than assumed:

* **Exact representability is the special case, not the rule.**  When ``h`` is
  an integer inside the register range, the single minimizer is ``h`` and its
  penalty is exactly ``+0.0``.  ``src/g4/energy.py::exact_slack_lift`` raises
  for any other residual, but that helper reconstructs the unique exact lift
  of one decoded state; it is not the domain-admission rule, and this adapter
  does not copy its refusal.
* **Out-of-range and half-integer residuals are admitted, not rejected.**  A
  negative or over-range residual clamps to the nearest endpoint with a
  non-zero penalty, and a half-integer residual yields two equally minimal
  registers.  No rejection rule is introduced by this module.

The self-test emits checksums and counters only: no energy, minimum, tie set,
label, rate, record, file, or other scientific value exists here.
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
STATE_COUNT = 257
STATE_STRIDE = 4093
PROBE_COUNT = 12
FNV_OFFSET, FNV_PRIME, MASK64 = 1469598103934665603, 1099511628211, (1 << 64) - 1
SCHEMA = "decisions_os/g9_cuda_membership_adapter_self_test/v1"

# Fixed synthetic non-contiguous balanced partition.  Every block is sorted
# ascending, the four blocks are disjoint and cover 0..19 exactly once, and no
# block is a contiguous five-asset run.
SYNTHETIC_MEMBERSHIP: tuple[tuple[int, ...], ...] = (
    (0, 5, 9, 14, 19),
    (1, 4, 8, 12, 17),
    (2, 6, 10, 13, 16),
    (3, 7, 11, 15, 18),
)


class MembershipAdapterError(RuntimeError):
    """Typed refusal for malformed membership, index, or self-test metadata."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise MembershipAdapterError(message)


def _word(value: float) -> int:
    return struct.unpack("<Q", struct.pack("<d", value))[0]


def _fnv(state: int, word: int) -> int:
    return ((state ^ word) * FNV_PRIME) & MASK64


def validate_membership(sectors: Iterable[Iterable[object]]) -> tuple[tuple[int, ...], ...]:
    """Accept four explicit sorted five-asset blocks covering 0..19 exactly once."""
    try:
        blocks = tuple(tuple(block) for block in sectors)
    except TypeError as exc:
        raise MembershipAdapterError("membership must be an iterable of blocks") from exc
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
    """True only for the inherited ``sector * 5 + offset`` block assumption."""
    blocks = validate_membership(sectors)
    return blocks == tuple(
        tuple(range(sector * SECTOR_SIZE, sector * SECTOR_SIZE + SECTOR_SIZE))
        for sector in range(SECTOR_COUNT)
    )


def membership_checksum(sectors: Iterable[Iterable[object]]) -> int:
    """Checksum the explicit membership so a silent block change is visible."""
    blocks = validate_membership(sectors)
    digest = FNV_OFFSET
    for block in blocks:
        for member in block:
            digest = _fnv(digest, member)
    return digest


def canonical_index_to_mask(index: int) -> int:
    """Canonical 20-bit decoded order, identical to src.g5.domains.BinaryDomain."""
    _require(type(index) is int and 0 <= index < (1 << ASSET_COUNT), "canonical index is out of range")
    mask = 0
    for asset in range(ASSET_COUNT):
        mask |= ((index >> (ASSET_COUNT - 1 - asset)) & 1) << asset
    return mask


def synthetic_instance() -> dict[str, object]:
    """Fixed artificial instance; not derived from any canonical Stage-1 input."""
    mu = [(float(asset) - 9.0) / 1000.0 for asset in range(ASSET_COUNT)]
    prices = [float(1 + (asset % 5)) for asset in range(ASSET_COUNT)]
    sigma = [
        [0.01 + float(row) / 10000.0 if row == column else float((row + column) % 7) / 100000.0
         for column in range(ASSET_COUNT)]
        for row in range(ASSET_COUNT)
    ]
    return {"mu": mu, "prices": prices, "sigma": sigma, "kappa_risk": 1.0,
            "k": 6.0, "c": 2.0, "b": 1100.0, "sectors": SYNTHETIC_MEMBERSHIP}


def synthetic_indices() -> tuple[int, ...]:
    """Fixed deterministic decoded indices; no candidate or instance is drawn."""
    return tuple((position * STATE_STRIDE) % (1 << ASSET_COUNT) for position in range(STATE_COUNT))


def decoded_terms(instance: Mapping[str, object], index: int) -> tuple[float, ...]:
    """Frozen preparation transcript with explicit sorted sector membership.

    The binary64 operation order mirrors src/g4/energy.py: every ``mu`` term is
    accumulated into ``f_acc`` first, then every ``kappa * (sigma_ik * x_i) *
    x_k`` term in row-major order; each residual accumulator starts at ``+0.0``.
    """
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


def _require_finite_residual(residual: object) -> float:
    """Fail closed before any narrowing conversion of a residual."""
    _require(type(residual) in (int, float), "residual must be a real number")
    value = float(residual)
    # NaN and both infinities are refused here so that no caller can reach the
    # truncating conversion in _floor_double, which is undefined for them.
    _require(value == value and value not in (float("inf"), float("-inf")),
             "residual must be finite")
    return value


def _floor_double(value: float) -> int:
    """Truncation-based floor; exact for the bounded residuals used here."""
    _require_finite_residual(value)
    lower = int(value)
    if float(lower) > value:
        lower -= 1
    return lower


def register_minimizers(residual: float, maximum: int) -> tuple[tuple[int, float], ...]:
    """Frozen per-register admission rule: clamped floor/floor+1, all ties kept.

    Mirrors src/g5/domains.py::_register_minimizers and returns each retained
    minimizer with its exact binary64 penalty ``(h - S)^2``.  A non-finite
    residual is refused before any conversion rather than admitted.
    """
    residual = _require_finite_residual(residual)
    lower = _floor_double(residual)
    candidates = sorted({min(max(lower, 0), maximum), min(max(lower + 1, 0), maximum)})
    scored = [(value, (residual - float(value)) * (residual - float(value))) for value in candidates]
    best = min(penalty for _, penalty in scored)
    return tuple((value, penalty) for value, penalty in scored if penalty == best)


def register_is_exactly_representable(residual: float, maximum: int) -> bool:
    """Exact representability, kept distinct from the clamped/tied general rule.

    A non-finite residual is refused before any conversion, never reported as
    simply "not exactly representable".
    """
    residual = _require_finite_residual(residual)
    lower = _floor_double(residual)
    return float(lower) == residual and 0 <= lower <= maximum


def register_maximum(register: int) -> int:
    """Register capacity: four two-bit sector registers, then eleven budget bits."""
    _require(type(register) is int and 0 <= register < REGISTER_COUNT, "register index is out of range")
    bits = SECTOR_SLACK_BITS if register < SECTOR_COUNT else BUDGET_SLACK_BITS
    return (1 << bits) - 1


def register_offset(register: int) -> int:
    """Frozen 19-bit layout offsets: sector j at 2j, budget at 8."""
    _require(type(register) is int and 0 <= register < REGISTER_COUNT, "register index is out of range")
    return register * SECTOR_SLACK_BITS if register < SECTOR_COUNT else SECTOR_COUNT * SECTOR_SLACK_BITS


def pack_auxiliary(values: Sequence[int]) -> int:
    """Pack five register values into the frozen little-endian 19-bit word."""
    _require(len(values) == REGISTER_COUNT, "packing needs one value per register")
    packed = 0
    for register, value in enumerate(values):
        maximum = register_maximum(register)
        _require(type(value) is int and 0 <= value <= maximum, f"register[{register}] value is out of range")
        packed |= value << register_offset(register)
    return packed


def unpack_register_value(auxiliary: int, register: int) -> float:
    """Reconstruct one register by explicit ascending bit weights from ``+0.0``."""
    _require(type(auxiliary) is int and 0 <= auxiliary < (1 << AUXILIARY_BITS), "auxiliary word is out of range")
    offset = register_offset(register)
    bits = SECTOR_SLACK_BITS if register < SECTOR_COUNT else BUDGET_SLACK_BITS
    accumulator = +0.0
    for bit in range(bits):
        value = 1.0 if (auxiliary >> (offset + bit)) & 1 else 0.0
        accumulator = accumulator + (float(1 << bit) * value)
    return accumulator


def state_lift_policy(instance: Mapping[str, object], index: int) -> dict[str, object]:
    """Per-state registers, admitted minimizers, packed first lift, and reconstruction."""
    terms = decoded_terms(instance, index)
    residuals = [terms[2 + sector] for sector in range(SECTOR_COUNT)] + [terms[2 + 2 * SECTOR_COUNT]]
    registers: list[dict[str, object]] = []
    lift_count = 1
    first_values: list[int] = []
    for register, residual in enumerate(residuals):
        maximum = register_maximum(register)
        minimizers = register_minimizers(residual, maximum)
        lift_count *= len(minimizers)
        first_values.append(minimizers[0][0])
        registers.append({
            "residual": residual,
            "exactly_representable": register_is_exactly_representable(residual, maximum),
            "minimizers": minimizers,
        })
    packed = pack_auxiliary(first_values)
    reconstructed = []
    for register in range(REGISTER_COUNT):
        value = unpack_register_value(packed, register)
        delta = residuals[register] - value
        reconstructed.append(delta * delta)
    return {"index": index, "terms": terms, "registers": registers, "lift_count": lift_count,
            "packed_first_lift": packed, "reconstructed_slack_squares": tuple(reconstructed)}


def policy_probe_table() -> tuple[tuple[float, int], ...]:
    """Fixed residual probes covering exact, clamped-low/high, and tied registers."""
    return (
        (2.0, 3), (0.0, 3), (3.0, 3), (-1.0, 3), (-2.5, 3), (4.0, 3),
        (0.5, 3), (1.5, 3), (2.5, 3), (1100.0, 2047), (2047.5, 2047), (-0.5, 2047),
    )


def expected_self_test() -> dict[str, object]:
    """Reproduce every device checksum and counter from the fixed synthetic data."""
    instance = synthetic_instance()
    membership = membership_checksum(instance["sectors"])
    domain_checksum = FNV_OFFSET
    terms_checksum = FNV_OFFSET
    policy_checksum = FNV_OFFSET
    packed_checksum = FNV_OFFSET
    exact_registers = clamped_registers = tied_registers = 0
    reconstruction_mismatches = 0
    total_lifts = 0
    for index in synthetic_indices():
        state = state_lift_policy(instance, index)
        domain_checksum = _fnv(domain_checksum, index)
        for value in state["terms"]:
            terms_checksum = _fnv(terms_checksum, _word(value))
        for register in state["registers"]:
            minimizers = register["minimizers"]
            policy_checksum = _fnv(policy_checksum, len(minimizers))
            policy_checksum = _fnv(policy_checksum, 1 if register["exactly_representable"] else 0)
            # A Python residual can never be non-finite here: it would already
            # have been refused.  The device reports the same field, so a
            # device-side invalid register is visible in this stream.
            policy_checksum = _fnv(policy_checksum, 0)
            for value, penalty in minimizers:
                policy_checksum = _fnv(policy_checksum, value)
                policy_checksum = _fnv(policy_checksum, _word(penalty))
            if register["exactly_representable"]:
                exact_registers += 1
            else:
                clamped_registers += 1
            if len(minimizers) > 1:
                tied_registers += 1
        total_lifts += int(state["lift_count"])
        packed_checksum = _fnv(packed_checksum, state["packed_first_lift"])
        for register, value in enumerate(state["reconstructed_slack_squares"]):
            packed_checksum = _fnv(packed_checksum, _word(value))
            if value != state["registers"][register]["minimizers"][0][1]:
                reconstruction_mismatches += 1
    probe_checksum = FNV_OFFSET
    for residual, maximum in policy_probe_table():
        minimizers = register_minimizers(residual, maximum)
        probe_checksum = _fnv(probe_checksum, len(minimizers))
        probe_checksum = _fnv(probe_checksum, 1 if register_is_exactly_representable(residual, maximum) else 0)
        probe_checksum = _fnv(probe_checksum, 0)
        for value, penalty in minimizers:
            probe_checksum = _fnv(probe_checksum, value)
            probe_checksum = _fnv(probe_checksum, _word(penalty))
    return {"schema": SCHEMA, "state_count": STATE_COUNT, "auxiliary_bits": AUXILIARY_BITS,
            "register_count": REGISTER_COUNT, "probe_count": PROBE_COUNT,
            "membership_checksum": f"{membership:016x}", "domain_checksum": f"{domain_checksum:016x}",
            "terms_checksum": f"{terms_checksum:016x}", "lift_policy_checksum": f"{policy_checksum:016x}",
            "packed_lift_checksum": f"{packed_checksum:016x}", "policy_probe_checksum": f"{probe_checksum:016x}",
            "exact_registers": exact_registers, "clamped_registers": clamped_registers,
            "tied_registers": tied_registers, "total_lifts": total_lifts,
            "reconstruction_mismatches": reconstruction_mismatches, "invalid_registers": 0,
            "nonfinite_terms": 0, "scientific_outputs": "intentionally absent", "verdict": "pass"}


def validate_self_test_report(payload: object) -> dict[str, object]:
    """Fail closed unless the device reproduces every expected field exactly."""
    expected = expected_self_test()
    required = set(expected) | {"device_index", "device_name"}
    _require(isinstance(payload, dict) and set(payload) == required, "adapter report has wrong key set")
    _require(type(payload["device_index"]) is int and payload["device_index"] >= 0
             and type(payload["device_name"]) is str and payload["device_name"],
             "adapter device metadata malformed")
    for key in ("state_count", "auxiliary_bits", "register_count", "probe_count", "exact_registers",
                "clamped_registers", "tied_registers", "total_lifts", "reconstruction_mismatches",
                "invalid_registers", "nonfinite_terms"):
        _require(type(payload[key]) is int, f"adapter integer field has wrong type: {key}")
    for key, value in expected.items():
        _require(payload[key] == value, f"adapter self-test mismatch: {key}")
    return dict(payload)

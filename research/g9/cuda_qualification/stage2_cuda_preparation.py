"""Python reference for the synthetic generic 20-bit CUDA preparation self-test.

This module is intentionally isolated from canonical input, ledgers, and
solvers.  It recreates the artificial C++ instance and exact-lift domain only
to compare device preparation checksums during non-scientific qualification.
"""
from __future__ import annotations

import struct
from typing import Any, Mapping


ASSET_COUNT, SECTOR_COUNT, SECTOR_SIZE = 20, 4, 5
SECTOR_BITS, BUDGET_BITS, AUXILIARY_BITS = 2, 11, 19
STATE_COUNT = 257
FNV_OFFSET, FNV_PRIME, MASK64 = 1469598103934665603, 1099511628211, (1 << 64) - 1
SCHEMA = "decisions_os/g9_cuda_preparation_self_test/v1"


class PreparationError(RuntimeError):
    """Typed refusal for a malformed synthetic preparation report."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PreparationError(message)


def _word(value: float) -> int:
    return struct.unpack("<Q", struct.pack("<d", value))[0]


def _fnv(state: int, word: int) -> int:
    return ((state ^ word) * FNV_PRIME) & MASK64


def canonical_index_to_mask(index: int) -> int:
    _require(type(index) is int and 0 <= index < (1 << ASSET_COUNT), "canonical index is out of range")
    mask = 0
    for asset in range(ASSET_COUNT):
        mask |= ((index >> (ASSET_COUNT - 1 - asset)) & 1) << asset
    return mask


def synthetic_instance() -> dict[str, object]:
    mu = [(float(index) - 9.0) / 1000.0 for index in range(ASSET_COUNT)]
    prices = [float(1 + (index % 5)) for index in range(ASSET_COUNT)]
    sigma = [
        [0.01 + float(row) / 10000.0 if row == column else float((row + column) % 7) / 100000.0
         for column in range(ASSET_COUNT)]
        for row in range(ASSET_COUNT)
    ]
    return {"mu": mu, "prices": prices, "sigma": sigma, "kappa_risk": 1.0, "k": 6.0, "c": 2.0, "b": 32.0}


def exact_auxiliary(instance: Mapping[str, object], mask: int) -> int | None:
    auxiliary = 0
    offset = 0
    for sector in range(SECTOR_COUNT):
        count = sum((mask >> (sector * SECTOR_SIZE + member)) & 1 for member in range(SECTOR_SIZE))
        residual = int(instance["c"]) - count
        if residual < 0 or residual >= (1 << SECTOR_BITS):
            return None
        auxiliary |= residual << offset
        offset += SECTOR_BITS
    spend = sum(int(instance["prices"][asset]) for asset in range(ASSET_COUNT) if (mask >> asset) & 1)
    budget_residual = int(instance["b"]) - spend
    if budget_residual < 0 or budget_residual >= (1 << BUDGET_BITS):
        return None
    return auxiliary | (budget_residual << offset)


def synthetic_domain(instance: Mapping[str, object]) -> list[tuple[int, int]]:
    domain: list[tuple[int, int]] = []
    for index in range(1 << ASSET_COUNT):
        auxiliary = exact_auxiliary(instance, canonical_index_to_mask(index))
        if auxiliary is not None:
            domain.append((index, auxiliary))
            if len(domain) == STATE_COUNT:
                return domain
    raise PreparationError("synthetic exact-lift domain is too small")


def prepared_terms(instance: Mapping[str, object], index: int, auxiliary: int) -> tuple[float, ...]:
    mask = canonical_index_to_mask(index)
    x = [1.0 if (mask >> asset) & 1 else 0.0 for asset in range(ASSET_COUNT)]
    f_value = 0.0
    for asset in range(ASSET_COUNT):
        f_value = f_value + (-(float(instance["mu"][asset]) * x[asset]))
    for row in range(ASSET_COUNT):
        for column in range(ASSET_COUNT):
            sigma_x = float(instance["sigma"][row][column]) * x[row]
            f_value = f_value + (float(instance["kappa_risk"]) * (sigma_x * x[column]))
    cardinality = 0.0
    for asset in range(ASSET_COUNT):
        cardinality = cardinality + x[asset]
    h_card = cardinality - float(instance["k"])
    h_sector: list[float] = []
    sector_square: list[float] = []
    for sector in range(SECTOR_COUNT):
        total = 0.0
        for member in range(SECTOR_SIZE):
            total = total + x[sector * SECTOR_SIZE + member]
        residual = float(instance["c"]) - total
        h_sector.append(residual)
        sector_square.append(residual * residual)
    budget = 0.0
    for asset in range(ASSET_COUNT):
        budget = budget + (float(instance["prices"][asset]) * x[asset])
    h_budget = float(instance["b"]) - budget
    offset = 0
    sector_slack_square: list[float] = []
    for sector in range(SECTOR_COUNT):
        register = 0.0
        for bit in range(SECTOR_BITS):
            value = 1.0 if (auxiliary >> (offset + bit)) & 1 else 0.0
            register = register + (float(1 << bit) * value)
        offset += SECTOR_BITS
        delta = h_sector[sector] - register
        sector_slack_square.append(delta * delta)
    budget_register = 0.0
    for bit in range(BUDGET_BITS):
        value = 1.0 if (auxiliary >> (offset + bit)) & 1 else 0.0
        budget_register = budget_register + (float(1 << bit) * value)
    budget_delta = h_budget - budget_register
    return (f_value, h_card * h_card, *h_sector, *sector_square, h_budget, h_budget * h_budget,
            *sector_slack_square, budget_delta * budget_delta)


def expected_self_test() -> dict[str, object]:
    instance = synthetic_instance()
    domain = synthetic_domain(instance)
    domain_checksum, auxiliary_checksum, terms_checksum = FNV_OFFSET, FNV_OFFSET, FNV_OFFSET
    for index, auxiliary in domain:
        domain_checksum = _fnv(domain_checksum, index)
        auxiliary_checksum = _fnv(auxiliary_checksum, auxiliary)
        for value in prepared_terms(instance, index, auxiliary):
            terms_checksum = _fnv(terms_checksum, _word(value))
    return {"schema": SCHEMA, "state_count": STATE_COUNT, "auxiliary_bits": AUXILIARY_BITS,
            "domain_checksum": f"{domain_checksum:016x}", "auxiliary_checksum": f"{auxiliary_checksum:016x}",
            "terms_checksum": f"{terms_checksum:016x}", "nonfinite_terms": 0,
            "scientific_outputs": "intentionally absent", "verdict": "pass"}


def validate_self_test_report(payload: object) -> dict[str, object]:
    _require(isinstance(payload, dict) and set(payload) == {"schema", "device_index", "device_name", "state_count", "auxiliary_bits", "domain_checksum", "auxiliary_checksum", "terms_checksum", "nonfinite_terms", "scientific_outputs", "verdict"},
             "preparation report has wrong key set")
    _require(type(payload["device_index"]) is int and payload["device_index"] >= 0 and type(payload["device_name"]) is str and payload["device_name"],
             "preparation device metadata malformed")
    _require(type(payload["state_count"]) is int and type(payload["auxiliary_bits"]) is int and type(payload["nonfinite_terms"]) is int,
             "preparation integer metadata malformed")
    for key, value in expected_self_test().items():
        _require(payload[key] == value, f"preparation self-test mismatch: {key}")
    return dict(payload)

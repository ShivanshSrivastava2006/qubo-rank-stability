"""Shared residual definitions only; no penalty function belongs here."""

from __future__ import annotations

from .instance import Instance


AffineResidual = tuple[float, tuple[tuple[int, float], ...]]


def cardinality_affine(instance: Instance) -> AffineResidual:
    """Return ``h_card = constant + sum(coefficient_i * x_i)``."""
    return -float(instance.K), tuple((i, 1.0) for i in range(20))


def sector_affines(instance: Instance) -> tuple[AffineResidual, ...]:
    """Return the four shared sector-residual affine definitions."""
    return tuple(
        (float(instance.C), tuple((i, -1.0) for i in members))
        for members in instance.sectors
    )


def budget_affine(instance: Instance) -> AffineResidual:
    """Return the shared budget-residual affine definition."""
    return instance.B, tuple((i, -instance.prices[i]) for i in range(20))


def cardinality(instance: Instance, x: tuple[int, ...]) -> float:
    constant, terms = cardinality_affine(instance)
    return constant + sum(coefficient * float(x[index]) for index, coefficient in terms)


def sector(instance: Instance, x: tuple[int, ...]) -> tuple[float, ...]:
    return tuple(
        constant + sum(coefficient * float(x[index]) for index, coefficient in terms)
        for constant, terms in sector_affines(instance)
    )


def budget(instance: Instance, x: tuple[int, ...]) -> float:
    # Preserve the frozen §5.2 primitive order: sum spending first, then
    # subtract that rounded accumulator from B.  The affine form above is for
    # QUBO expansion only and must not replace this canonical residual ledger.
    total = 0.0
    for index in range(20):
        total = total + (instance.prices[index] * float(x[index]))
    return instance.B - total

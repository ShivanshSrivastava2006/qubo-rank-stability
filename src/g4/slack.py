"""Slack encoding only; it shares residual definitions, never penalty assembly."""

from __future__ import annotations

from . import constraints, objective
from .instance import Instance
from .parameters import Coefficients
from .quadratic import Qubo


SECTOR_BITS = 2
BUDGET_BITS = 11


def variable_count() -> int:
    return 20 + 4 * SECTOR_BITS + BUDGET_BITS


def _add_square(qubo: Qubo, constant: float, terms: list[tuple[int, float]], scale: float) -> None:
    qubo.add_constant(scale * constant * constant)
    for index, coefficient in terms:
        qubo.add_linear(index, scale * (2.0 * constant * coefficient + coefficient * coefficient))
    for left_position, (left, left_coefficient) in enumerate(terms):
        for right, right_coefficient in terms[left_position + 1:]:
            qubo.add_pair(left, right, scale * 2.0 * left_coefficient * right_coefficient)


def formulate(instance: Instance, coefficients: Coefficients) -> Qubo:
    """Construct the explicit 39-variable slack QUBO, retaining constants."""
    qubo = Qubo(variable_count())
    objective.add_qubo_terms(qubo, instance)
    constant, terms = constraints.cardinality_affine(instance)
    _add_square(qubo, constant, list(terms), coefficients.alpha)
    auxiliary = 20
    for constant, residual_terms in constraints.sector_affines(instance):
        terms = list(residual_terms) + [(auxiliary + d, -float(1 << d)) for d in range(SECTOR_BITS)]
        _add_square(qubo, constant, terms, coefficients.sector_slack)
        auxiliary += SECTOR_BITS
    constant, residual_terms = constraints.budget_affine(instance)
    budget_terms = list(residual_terms) + [(auxiliary + d, -float(1 << d)) for d in range(BUDGET_BITS)]
    _add_square(qubo, constant, budget_terms, coefficients.budget_slack)
    return qubo

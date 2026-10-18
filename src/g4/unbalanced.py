"""Unbalanced encoding only; it shares residual definitions, never penalty assembly."""

from __future__ import annotations

from . import constraints, objective
from .instance import Instance
from .parameters import Coefficients
from .quadratic import Qubo


def variable_count() -> int:
    return 20


def _add_zeta(qubo: Qubo, constant: float, terms: list[tuple[int, float]], linear: float,
               quadratic: float) -> None:
    qubo.add_constant((-linear * constant) + (quadratic * constant * constant))
    for index, coefficient in terms:
        qubo.add_linear(index, (-linear * coefficient) + quadratic * (2.0 * constant * coefficient + coefficient * coefficient))
    for left_position, (left, left_coefficient) in enumerate(terms):
        for right, right_coefficient in terms[left_position + 1:]:
            qubo.add_pair(left, right, quadratic * 2.0 * left_coefficient * right_coefficient)


def formulate(instance: Instance, coefficients: Coefficients) -> Qubo:
    """Construct the explicit 20-variable unbalanced QUBO, retaining constants."""
    qubo = Qubo(variable_count())
    objective.add_qubo_terms(qubo, instance)
    card_constant, card_terms_tuple = constraints.cardinality_affine(instance)
    card_terms = list(card_terms_tuple)
    for index, coefficient in card_terms:
        qubo.add_linear(index, coefficients.alpha * (2.0 * card_constant * coefficient + coefficient * coefficient))
    qubo.add_constant(coefficients.alpha * card_constant * card_constant)
    for left_position, (left, left_coefficient) in enumerate(card_terms):
        for right, right_coefficient in card_terms[left_position + 1:]:
            qubo.add_pair(left, right, coefficients.alpha * 2.0 * left_coefficient * right_coefficient)
    for constant, terms in constraints.sector_affines(instance):
        _add_zeta(qubo, constant, list(terms),
                   coefficients.sector_linear, coefficients.sector_quadratic)
    constant, terms = constraints.budget_affine(instance)
    _add_zeta(qubo, constant, list(terms),
               coefficients.budget_linear, coefficients.budget_quadratic)
    return qubo

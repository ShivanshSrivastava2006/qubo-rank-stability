"""Canonical ordered binary64 objective ledger; it knows nothing about encodings."""

from __future__ import annotations

from .instance import Instance
from .quadratic import Qubo


def add_qubo_terms(qubo: Qubo, instance: Instance) -> None:
    """Add the common objective QUBO terms; this is not a penalty helper."""
    if qubo.size < 20:
        raise ValueError("objective requires the 20 original decision variables")
    for i in range(20):
        qubo.add_linear(i, -instance.mu[i] + instance.kappa_risk * instance.sigma[i][i])
        for k in range(i + 1, 20):
            # The accepted canonical covariance is symmetric.  State the sum
            # explicitly so the QUBO follows f=x^T Sigma x rather than assuming
            # a compiler-selected triangular expansion.
            qubo.add_pair(i, k, instance.kappa_risk * (instance.sigma[i][k] + instance.sigma[k][i]))


def value(instance: Instance, x: tuple[int, ...]) -> float:
    if len(x) != len(instance.tickers) or any(bit not in (0, 1) for bit in x):
        raise ValueError("x must be a binary vector in canonical order")
    total = 0.0
    for i in range(20):
        total = total + (-(instance.mu[i] * float(x[i])))
    for i in range(20):
        for k in range(20):
            total = total + (instance.kappa_risk * (instance.sigma[i][k] * float(x[i])) * float(x[k]))
    return total

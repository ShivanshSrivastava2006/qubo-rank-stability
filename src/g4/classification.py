"""Encoding-blind decoded classification required by frozen M5.

This module knows only decoded bit vectors, the frozen original optimum value,
an original-objective callable, and an original-feasibility predicate.  Encoded
energies and encoded state are deliberately outside every public interface.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
import math


Decoded = tuple[int, ...]
Objective = Callable[[Decoded], float]
Feasibility = Callable[[Decoded], bool]

EPSILON = math.ldexp(1.0, -52)
C_F_PRIMARY = 2048.0


def _decoded(value: object) -> Decoded:
    if not isinstance(value, tuple) or not value:
        raise ValueError("decoded x must be a nonempty tuple of bits")
    if any(type(bit) is not int or bit not in (0, 1) for bit in value):
        raise ValueError("decoded x must contain only integer bits")
    return value


def _finite(value: object, label: str) -> float:
    if type(value) not in (int, float):
        raise TypeError(f"{label} must be a real binary64-compatible scalar")
    converted = float(value)
    if not math.isfinite(converted):
        raise ValueError(f"{label} must be finite")
    return converted


@dataclass(frozen=True)
class OriginalObjectiveService:
    """Immutable D015 original-objective comparator configuration."""

    objective: Objective
    lambda_ref: float
    c_f: float = C_F_PRIMARY

    def __post_init__(self) -> None:
        if not callable(self.objective):
            raise TypeError("objective must be callable")
        lambda_ref = _finite(self.lambda_ref, "Lambda_ref")
        c_f = _finite(self.c_f, "c_f")
        if lambda_ref <= 0.0:
            raise ValueError("Lambda_ref must be strictly positive")
        if c_f <= 0.0:
            raise ValueError("c_f must be strictly positive")
        object.__setattr__(self, "lambda_ref", lambda_ref)
        object.__setattr__(self, "c_f", c_f)

    def agrees_with_frozen_optimum(self, x: Decoded, f_star: float) -> bool:
        """Apply only D015's objective-comparison component of ``OPT_f``.

        This public helper is not the complete feasibility-aware ``OPT_f``
        predicate and must not be used as an atomic A-label decision.  Call
        :meth:`DecodedClassifier.label`, which composes the independent
        feasibility predicate with this comparison, for the full classifier
        path.
        """
        decoded = _decoded(x)
        optimum = _finite(f_star, "f_star")
        value = _finite(self.objective(decoded), "f(x)")
        gap = abs(value - optimum)
        magnitude = max(abs(value), abs(optimum))
        scale = _finite(self.lambda_ref + magnitude, "objective comparison scale")
        tolerance = _finite((self.c_f * EPSILON) * scale, "objective tolerance")
        if tolerance <= 0.0:
            raise ValueError("objective tolerance must be strictly positive")
        return gap <= tolerance


@dataclass(frozen=True)
class DecodedClassifier:
    """D016 atomic and decoded-set labels over original objects only."""

    optimum_service: OriginalObjectiveService
    feasible: Feasibility

    def __post_init__(self) -> None:
        if not isinstance(self.optimum_service, OriginalObjectiveService):
            raise TypeError("optimum_service must be an OriginalObjectiveService")
        if not callable(self.feasible):
            raise TypeError("feasible must be callable")

    def label(self, x: Decoded, f_star: float) -> str:
        """Return exactly A=OPT_f, B=feasible and not A, or C=not feasible."""
        decoded = _decoded(x)
        optimum = _finite(f_star, "f_star")
        feasible = self.feasible(decoded)
        if type(feasible) is not bool:
            raise TypeError("feasibility predicate must return bool")
        if not feasible:
            return "C"
        if self.optimum_service.agrees_with_frozen_optimum(decoded, optimum):
            return "A"
        return "B"

    def label_set(self, decoded_states: Iterable[Decoded], f_star: float) -> str:
        """Apply D016's exists-C, else all-A, else-B rule after deduplication."""
        optimum = _finite(f_star, "f_star")
        try:
            states = tuple(dict.fromkeys(_decoded(x) for x in decoded_states))
        except TypeError as error:
            raise TypeError("decoded_states must be an iterable of decoded bit tuples") from error
        if not states:
            raise ValueError("decoded state set must be nonempty")
        labels = tuple(self.label(x, optimum) for x in states)
        if "C" in labels:
            return "C"
        if all(label == "A" for label in labels):
            return "A"
        return "B"

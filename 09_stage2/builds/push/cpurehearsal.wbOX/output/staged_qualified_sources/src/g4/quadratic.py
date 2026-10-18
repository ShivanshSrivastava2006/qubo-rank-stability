"""A transparent upper-triangular QUBO representation with its constant retained."""

from __future__ import annotations

from dataclasses import dataclass, field
import math


@dataclass
class Qubo:
    size: int
    constant: float = 0.0
    diagonal: list[float] = field(init=False)
    upper: dict[tuple[int, int], float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.size, int) or self.size <= 0:
            raise ValueError("QUBO size must be a positive integer")
        if not math.isfinite(self.constant):
            raise ValueError("QUBO constant must be finite")
        self.diagonal = [0.0] * self.size

    def _validate(self, value: float) -> None:
        if not math.isfinite(value):
            raise ValueError("QUBO coefficient must be finite")

    def _validate_index(self, index: int) -> None:
        if not isinstance(index, int) or index < 0 or index >= self.size:
            raise ValueError("QUBO variable index is out of range")

    def add_constant(self, value: float) -> None:
        self._validate(value)
        self.constant = self.constant + value
        self._validate(self.constant)

    def add_linear(self, index: int, value: float) -> None:
        self._validate_index(index)
        self._validate(value)
        self.diagonal[index] = self.diagonal[index] + value
        self._validate(self.diagonal[index])

    def add_pair(self, left: int, right: int, value: float) -> None:
        self._validate_index(left)
        self._validate_index(right)
        self._validate(value)
        if left == right:
            self.add_linear(left, value)
            return
        key = (left, right) if left < right else (right, left)
        self.upper[key] = self.upper.get(key, 0.0) + value
        self._validate(self.upper[key])

    def energy(self, bits: tuple[int, ...]) -> float:
        """Evaluate the expanded matrix for formulation diagnostics only.

        The frozen D015 comparison energy remains the residual-form primitive
        ledger, not this cancellation-prone expanded accumulation.
        """
        if len(bits) != self.size or any(bit not in (0, 1) for bit in bits):
            raise ValueError("QUBO state has the wrong binary shape")
        total = self.constant
        for i, bit in enumerate(bits):
            total = total + (self.diagonal[i] * float(bit))
        for (i, j), coefficient in self.upper.items():
            total = total + (coefficient * float(bits[i]) * float(bits[j]))
        return total

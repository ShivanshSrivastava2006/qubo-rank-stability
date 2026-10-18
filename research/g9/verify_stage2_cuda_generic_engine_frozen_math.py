#!/usr/bin/env python3
"""Anchor synthetic D015 control cases to the frozen authoritative tau function."""
from __future__ import annotations

from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from research.g9.cuda_qualification import stage2_cuda_generic_engine as engine  # noqa: E402
from src.g4.energy import tau  # noqa: E402


class FixtureError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise FixtureError(message)


def main() -> int:
    expected_counts: list[list[int]] = []
    expected_indices: list[int] = []
    for point, coeff in enumerate(engine._coefficients()):
        for encoding, evaluator in enumerate((engine._unbalanced, engine._slack)):
            energies = [engine._control_energy(evaluator(engine._terms(state), coeff), state, point, encoding)
                        for state in range(engine.STATE_COUNT)]
            minimum = min(energies)
            first_index = energies.index(minimum)
            anchor = 17 + point * 31 + encoding * 7
            require(first_index == anchor, "synthetic exact duplicate did not test strict first-seen order")
            expected_indices.append(first_index)
            counts: list[int] = []
            for c_h in (1024.0, 2048.0, 4096.0):
                frozen = [abs(energy - minimum) <= tau(energy, minimum, engine.LAMBDA_REF, c_h) for energy in energies]
                local = [engine._frozen_tie(energy, minimum, c_h) for energy in energies]
                require(local == frozen, "harness tie comparator differs from src.g4.energy.tau")
                counts.append(sum(frozen))
            require(counts == [3, 4, 5], "synthetic D015 nesting is not strictly load-bearing")
            expected_counts.append(counts)
    report = engine.expected_self_test()
    require(report["tie_counts"] == expected_counts and len(expected_indices) == engine.POINT_COUNT * engine.ENCODING_COUNT,
            "self-test report no longer binds frozen D015 cases")
    print("PASS Stage-2 generic CUDA frozen-math anchor; src.g4.energy.tau agrees on all synthetic control energies")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Anchor the composed synthetic path to the frozen authorities.

Imports only the comparison entry points needed: ``src.g4.energy`` for the
prepared decoded/slack transcript, the two energy transcripts and ``tau``;
``src.g5.domains`` for the canonical decoded order and the per-register
admission rule.  Every check runs on this component's own fixed synthetic
instance — no canonical Stage-1 artifact is opened and no scientific value is
produced or printed.
"""
from __future__ import annotations

from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from research.g9.cuda_qualification import stage2_cuda_composed as composed  # noqa: E402
from src.g4.energy import (  # noqa: E402
    BUDGET_SLACK_BITS,
    SECTOR_SLACK_BITS,
    SLACK_AUXILIARY_LENGTH,
    prepare_coefficients,
    prepare_decoded_state,
    prepare_instance,
    prepare_slack_state,
    slack_energy_prepared,
    tau,
    unbalanced_energy_prepared,
)
from src.g4.parameters import Coefficients  # noqa: E402
from src.g5.domains import BinaryDomain, _register_minimizers  # noqa: E402
from src.g4.instance import Instance  # noqa: E402


class AnchorError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AnchorError(message)


def frozen_instance() -> Instance:
    data = composed.synthetic_instance()
    return Instance(
        tickers=tuple(f"SYN{index:02d}" for index in range(composed.ASSET_COUNT)),
        sectors=tuple(tuple(block) for block in data["sectors"]),
        mu=tuple(data["mu"]),
        sigma=tuple(tuple(row) for row in data["sigma"]),
        prices=tuple(data["prices"]),
        kappa_risk=data["kappa_risk"],
        K=int(data["k"]),
        C=int(data["c"]),
        B=float(data["b"]),
    )


def frozen_coefficients() -> Coefficients:
    values = composed.synthetic_coefficients()
    return Coefficients(
        alpha=values["alpha"],
        sector_slack=values["sector_slack"],
        budget_slack=values["budget_slack"],
        sector_linear=values["sector_linear"],
        sector_quadratic=values["sector_quadratic"],
        budget_linear=values["budget_linear"],
        budget_quadratic=values["budget_quadratic"],
    )


def main() -> int:
    run = composed.pipeline()
    require(not composed.is_contiguous_membership(composed.SYNTHETIC_MEMBERSHIP),
            "the anchored partition must be non-contiguous")
    require(composed.SECTOR_SLACK_BITS == SECTOR_SLACK_BITS
            and composed.BUDGET_SLACK_BITS == BUDGET_SLACK_BITS
            and composed.AUXILIARY_BITS == SLACK_AUXILIARY_LENGTH,
            "slack layout constants differ from the frozen ledger")

    prepared = prepare_instance(frozen_instance())
    coefficients = prepare_coefficients(frozen_coefficients())
    domain = BinaryDomain(composed.ASSET_COUNT)
    states = registers = energies = 0
    for position in range(composed.STATE_COUNT):
        index = composed.canonical_index(position)
        bits = tuple((composed.canonical_index_to_mask(index) >> asset) & 1
                     for asset in range(composed.ASSET_COUNT))
        require(bits == domain[index], f"canonical order differs from BinaryDomain at {index}")

        frozen_decoded = prepare_decoded_state(prepared, domain[index])
        mine = run["terms"][position]
        frozen_terms = (frozen_decoded.f_value, frozen_decoded.card_square, *frozen_decoded.h_sector,
                        *frozen_decoded.sector_square, frozen_decoded.h_budget, frozen_decoded.budget_square)
        for slot, (left, right) in enumerate(zip(mine, frozen_terms)):
            require(left == right, f"prepared term {slot} differs from src.g4.energy at position {position}")
        states += 1

        state = run["registers"][position]
        for register, entry in enumerate(state["registers"]):
            frozen_minimizers = _register_minimizers(entry["residual"], composed.register_maximum(register))
            require(tuple(value for value, _ in entry["minimizers"]) == frozen_minimizers,
                    f"register[{register}] minimizers differ from src.g5.domains at position {position}")
            registers += 1

        auxiliary = tuple((state["packed"] >> bit) & 1 for bit in range(composed.AUXILIARY_BITS))
        frozen_slack = prepare_slack_state(frozen_decoded, auxiliary)
        frozen_squares = (*frozen_slack.sector_slack_square, frozen_slack.budget_slack_square)
        for slot, (left, right) in enumerate(zip(state["slack_squares"], frozen_squares)):
            require(left == right, f"slack square {slot} differs from src.g4.energy at position {position}")

        # Every natural word is compared, including the six per encoding that
        # the control later overwrites; no position is skipped.
        frozen_unbalanced = unbalanced_energy_prepared(frozen_decoded, coefficients)
        frozen_slack_energy = slack_energy_prepared(frozen_slack, coefficients)
        require(run["encodings"]["unbalanced"]["natural_energies"][position] == frozen_unbalanced,
                f"natural unbalanced energy differs from src.g4.energy at position {position}")
        require(run["encodings"]["slack"]["natural_energies"][position] == frozen_slack_energy,
                f"natural slack energy differs from src.g4.energy at position {position}")
        energies += 2

    # The controlled words are verified against the declared control protocol,
    # separately from the frozen-transcript comparison above.
    controlled = 0
    for encoding in composed.ENCODINGS:
        data = run["encodings"][encoding]
        offsets = composed.control_offsets(encoding)
        for slot, position in enumerate(composed.CONTROL_POSITIONS):
            require(data["energies"][position] == data["phase_a_minimum"] + offsets[slot],
                    f"{encoding}: control position {position} is not phase_a_minimum + declared offset")
            controlled += 1
        for position in range(composed.STATE_COUNT):
            if position not in composed.CONTROL_POSITIONS:
                require(data["energies"][position] == data["natural_energies"][position],
                        f"{encoding}: control altered non-control position {position}")

    # tau and the derived tie flags, against the authoritative comparator.
    for encoding in composed.ENCODINGS:
        data = run["encodings"][encoding]
        minimum = data["minimum"]
        for position, energy in enumerate(data["energies"]):
            expected = 0
            for bit, c_h in enumerate(composed.CH_VALUES):
                if abs(energy - minimum) <= tau(energy, minimum, composed.LAMBDA_REF, c_h):
                    expected |= 1 << bit
            require(data["flags"][position] == expected,
                    f"{encoding}: flag at position {position} differs from src.g4.energy.tau")
        # First-seen minimum recomputed independently under the strict rule.
        best, best_index = data["energies"][0], 0
        for position in range(1, composed.STATE_COUNT):
            if data["energies"][position] < best:
                best, best_index = data["energies"][position], position
        require(best == minimum and best_index == data["minimum_index"],
                f"{encoding}: first-seen minimum differs from an independent strict scan")

    print(f"PASS Stage-2 composed frozen anchor; {states} states and {registers} registers match "
          f"src.g4.energy / src.g5.domains on a non-contiguous synthetic partition; "
          f"{energies} natural energy words match the frozen authority; "
          f"{controlled} controlled words match the declared control protocol")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

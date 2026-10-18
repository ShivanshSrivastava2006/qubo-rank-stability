#!/usr/bin/env python3
"""Anchor the membership adapter to the frozen authorities.

Imports only the comparison entry points it needs — ``src.g5.domains`` for the
canonical decoded order and the per-register admission rule, ``src.g4.energy``
for the prepared decoded/slack transcript — and checks the adapter reproduces
them bit-for-bit on the fixed synthetic instance with its non-contiguous
partition.  No canonical Stage-1 artifact is opened and no scientific value is
produced: the instance and partition are the adapter's own synthetic data.
"""
from __future__ import annotations

from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from research.g9.cuda_qualification import stage2_cuda_membership_adapter as adapter  # noqa: E402
from src.g4.energy import prepare_decoded_state, prepare_instance, prepare_slack_state  # noqa: E402
from src.g4.instance import Instance  # noqa: E402
from src.g5.domains import BinaryDomain, _register_minimizers  # noqa: E402


class AnchorError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AnchorError(message)


def frozen_instance() -> Instance:
    """The adapter's synthetic data expressed for the frozen ledger."""
    data = adapter.synthetic_instance()
    return Instance(
        tickers=tuple(f"SYN{index:02d}" for index in range(adapter.ASSET_COUNT)),
        sectors=tuple(tuple(block) for block in data["sectors"]),
        mu=tuple(data["mu"]),
        sigma=tuple(tuple(row) for row in data["sigma"]),
        prices=tuple(data["prices"]),
        kappa_risk=data["kappa_risk"],
        K=int(data["k"]),
        C=int(data["c"]),
        B=int(data["b"]),
    )


def check_canonical_order(indices) -> None:
    domain = BinaryDomain(adapter.ASSET_COUNT)
    for index in indices:
        mask = adapter.canonical_index_to_mask(index)
        bits = tuple((mask >> asset) & 1 for asset in range(adapter.ASSET_COUNT))
        require(bits == domain[index], f"canonical order differs from BinaryDomain at {index}")
    for index in (0, 1, 2, 3, 1023, (1 << adapter.ASSET_COUNT) - 1):
        mask = adapter.canonical_index_to_mask(index)
        bits = tuple((mask >> asset) & 1 for asset in range(adapter.ASSET_COUNT))
        require(bits == domain[index], f"canonical order differs from BinaryDomain at {index}")


def check_prepared_transcript(indices) -> int:
    """Compare every decoded and slack term against src.g4.energy, bit-for-bit."""
    instance = adapter.synthetic_instance()
    prepared = prepare_instance(frozen_instance())
    domain = BinaryDomain(adapter.ASSET_COUNT)
    compared = 0
    for index in indices:
        state = adapter.state_lift_policy(instance, index)
        frozen_decoded = prepare_decoded_state(prepared, domain[index])
        mine = state["terms"]
        frozen_terms = (frozen_decoded.f_value, frozen_decoded.card_square, *frozen_decoded.h_sector,
                        *frozen_decoded.sector_square, frozen_decoded.h_budget, frozen_decoded.budget_square)
        require(len(mine) == len(frozen_terms), "prepared term count differs from the frozen transcript")
        for position, (left, right) in enumerate(zip(mine, frozen_terms)):
            require(left == right and left.__class__ is right.__class__,
                    f"prepared term {position} differs from src.g4.energy at index {index}")
        packed = state["packed_first_lift"]
        auxiliary = tuple((packed >> bit) & 1 for bit in range(adapter.AUXILIARY_BITS))
        frozen_slack = prepare_slack_state(frozen_decoded, auxiliary)
        frozen_squares = (*frozen_slack.sector_slack_square, frozen_slack.budget_slack_square)
        for position, (left, right) in enumerate(zip(state["reconstructed_slack_squares"], frozen_squares)):
            require(left == right, f"slack square {position} differs from src.g4.energy at index {index}")
        compared += 1
    return compared


def check_register_policy(indices) -> int:
    """Compare admitted minimizers against src.g5.domains._register_minimizers."""
    instance = adapter.synthetic_instance()
    compared = 0
    for index in indices:
        state = adapter.state_lift_policy(instance, index)
        for register, entry in enumerate(state["registers"]):
            maximum = adapter.register_maximum(register)
            frozen = _register_minimizers(entry["residual"], maximum)
            mine = tuple(value for value, _ in entry["minimizers"])
            require(mine == frozen,
                    f"register[{register}] minimizers differ from the frozen rule at index {index}")
            compared += 1
    for residual, maximum in adapter.policy_probe_table():
        frozen = _register_minimizers(residual, maximum)
        mine = tuple(value for value, _ in adapter.register_minimizers(residual, maximum))
        require(mine == frozen, f"probe residual {residual!r} differs from the frozen rule")
        compared += 1
    return compared


def check_layout_against_frozen() -> None:
    """The 19-bit layout constants must equal the frozen ledger's own constants."""
    from src.g4.energy import BUDGET_SLACK_BITS, SECTOR_SLACK_BITS, SLACK_AUXILIARY_LENGTH

    require(adapter.SECTOR_SLACK_BITS == SECTOR_SLACK_BITS, "sector slack width differs from the frozen ledger")
    require(adapter.BUDGET_SLACK_BITS == BUDGET_SLACK_BITS, "budget slack width differs from the frozen ledger")
    require(adapter.AUXILIARY_BITS == SLACK_AUXILIARY_LENGTH, "auxiliary width differs from the frozen ledger")


def main() -> int:
    indices = adapter.synthetic_indices()
    require(not adapter.is_contiguous_membership(adapter.SYNTHETIC_MEMBERSHIP),
            "the anchored partition must be non-contiguous")
    check_layout_against_frozen()
    check_canonical_order(indices)
    terms = check_prepared_transcript(indices)
    registers = check_register_policy(indices)
    print(f"PASS Stage-2 membership adapter frozen anchor; {terms} states match src.g4.energy and "
          f"{registers} registers match src.g5.domains on a non-contiguous partition")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

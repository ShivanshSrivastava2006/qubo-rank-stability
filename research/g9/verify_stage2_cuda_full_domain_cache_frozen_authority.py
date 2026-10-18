#!/usr/bin/env python3
"""Anchor the full-domain slack cache to the frozen authorities.

Constructs the same synthetic instance in memory only and compares the
complete cache — cardinality, every 64-bit offset and every packed lift — with
``src.g5.domains.build_slack_domain_cache``, plus canonical ordering against
``BinaryDomain`` and representative prepared terms/registers against
``src.g4.energy``.  No canonical artifact is opened and no scientific value is
produced.
"""
from __future__ import annotations

from pathlib import Path
import random
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from research.g9.cuda_qualification import stage2_cuda_full_domain_cache as cache  # noqa: E402
from src.g4.energy import (  # noqa: E402
    BUDGET_SLACK_BITS,
    SECTOR_SLACK_BITS,
    SLACK_AUXILIARY_LENGTH,
    prepare_decoded_state,
    prepare_instance,
    prepare_slack_state,
)
from src.g4.instance import Instance  # noqa: E402
from src.g4.parameters import Coefficients  # noqa: E402
from src.g5.domains import BinaryDomain, _register_minimizers, build_slack_domain_cache  # noqa: E402


class AnchorError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AnchorError(message)


def frozen_instance(payload) -> Instance:
    return Instance(
        tickers=tuple(f"SYN{index:02d}" for index in range(cache.ASSET_COUNT)),
        sectors=tuple(tuple(block) for block in payload["sectors"]),
        mu=tuple(payload["mu"]),
        sigma=tuple(tuple(row) for row in payload["sigma"]),
        prices=tuple(payload["prices"]),
        kappa_risk=float(payload["kappa_risk"]),
        K=int(payload["k"]),
        C=int(payload["c"]),
        B=float(payload["b"]),
    )


def frozen_coefficients() -> Coefficients:
    """Any active slack coefficients: the cache depends on residuals only."""
    return Coefficients(alpha=0.125, sector_slack=0.0625, budget_slack=0.046875,
                        sector_linear=0.15625, sector_quadratic=0.03125,
                        budget_linear=0.0625, budget_quadratic=0.015625)


def main() -> int:
    payload = cache.validate_payload(cache.synthetic_payload())
    require(not cache.is_contiguous_membership(payload["sectors"]),
            "the anchored partition must be non-contiguous")
    require(cache.SECTOR_SLACK_BITS == SECTOR_SLACK_BITS
            and cache.BUDGET_SLACK_BITS == BUDGET_SLACK_BITS
            and cache.AUXILIARY_BITS == SLACK_AUXILIARY_LENGTH,
            "slack layout constants differ from the frozen ledger")

    built = cache.build_cache(cache.synthetic_payload())
    instance = frozen_instance(payload)
    frozen = build_slack_domain_cache(instance, frozen_coefficients())

    # Complete cardinality and offset semantics.
    require(len(frozen) == built["total"],
            f"lift cardinality differs: frozen {len(frozen)} vs built {built['total']}")
    frozen_offsets = memoryview(frozen.offset_bytes).cast("Q")
    frozen_masks = memoryview(frozen.auxiliary_bytes).cast("I")
    require(len(frozen_offsets) == cache.STATE_COUNT + 1, "frozen offsets do not span the whole domain")
    offsets_checked = 0
    for index in range(cache.STATE_COUNT + 1):
        require(int(frozen_offsets[index]) == int(built["offsets"][index]),
                f"offset {index} differs from the frozen cache")
        offsets_checked += 1
    masks_checked = 0
    for slot in range(built["total"]):
        require(int(frozen_masks[slot]) == int(built["masks"][slot]),
                f"packed lift {slot} differs from the frozen cache")
        masks_checked += 1

    # Canonical decoded ordering.
    domain = BinaryDomain(cache.ASSET_COUNT)
    random.seed(4073)
    order_checked = 0
    for index in [0, 1, 2, 3, cache.STATE_COUNT - 1] + [random.randrange(cache.STATE_COUNT) for _ in range(500)]:
        require(cache.canonical_bits(index) == domain[index],
                f"canonical order differs from BinaryDomain at {index}")
        order_checked += 1

    # Representative prepared terms and registers.
    prepared = prepare_instance(instance)
    terms_checked = registers_checked = 0
    probes = [0, 1, cache.STATE_COUNT - 1, cache.STATE_COUNT // 2]
    probes += [random.randrange(cache.STATE_COUNT) for _ in range(200)]
    for index in probes:
        frozen_decoded = prepare_decoded_state(prepared, domain[index])
        mine_sector, mine_budget = cache.frozen_residuals(payload, index)
        for sector in range(cache.SECTOR_COUNT):
            require(mine_sector[sector] == frozen_decoded.h_sector[sector],
                    f"sector residual {sector} differs from src.g4.energy at {index}")
        require(mine_budget == frozen_decoded.h_budget,
                f"budget residual differs from src.g4.energy at {index}")
        terms_checked += 1
        for register in range(cache.REGISTER_COUNT):
            residual = mine_sector[register] if register < cache.SECTOR_COUNT else mine_budget
            require(cache.register_minimizers(residual, cache.register_maximum(register))
                    == _register_minimizers(residual, cache.register_maximum(register)),
                    f"register[{register}] minimizers differ from src.g5.domains at {index}")
            registers_checked += 1
        # The frozen lift of one state must reconstruct through the frozen
        # slack-state preparation without raising.
        first = int(built["masks"][built["offsets"][index]])
        auxiliary = tuple((first >> bit) & 1 for bit in range(cache.AUXILIARY_BITS))
        prepare_slack_state(frozen_decoded, auxiliary)

    print(f"PASS Stage-2 full-domain cache frozen anchor; {offsets_checked} offsets and {masks_checked} "
          f"packed lifts match src.g5.domains.build_slack_domain_cache over the complete {cache.STATE_COUNT}-state "
          f"domain; {order_checked} canonical positions match BinaryDomain; {terms_checked} prepared states and "
          f"{registers_checked} registers match src.g4.energy / src.g5.domains")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

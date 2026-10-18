#!/usr/bin/env python3
"""Synthetic fixtures for the future Stage-2 generation-ledger contract."""
from __future__ import annotations

import copy
import hashlib
import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from research.g9 import stage2_generation_contract as c  # noqa: E402
from research.g9 import stage2_generator as g  # noqa: E402


class FixtureError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise FixtureError(message)


def rejected(fn, label: str) -> None:
    try:
        fn()
    except c.GenerationContractError:
        return
    except Exception as exc:
        raise FixtureError(f"{label}: raw {type(exc).__name__}") from exc
    raise FixtureError(f"{label}: accepted")


INPUTS = c.ScreeningInputs(prices=(1,) * 20, K=6, C=2, B=6,
                           stage1_partition=tuple(tuple(range(n, n + 5)) for n in range(0, 20, 5)))
SOURCE_SHA = hashlib.sha256(b"synthetic-generator-source").hexdigest()


def first_accepted(slot: int, prior) -> list[g.AttemptScreen]:
    rows = []
    for attempt in range(128):
        screen = g.screen_attempt(prices=INPUTS.prices, K=INPUTS.K, C=INPUTS.C, B=INPUTS.B,
                                  stage1_partition=INPUTS.stage1_partition,
                                  earlier_accepted_partitions=prior, slot=slot, attempt=attempt)
        rows.append(screen)
        if screen.accepted:
            return rows
    raise FixtureError("synthetic fixture failed to find an accepted partition")


def valid_payload() -> dict:
    prior, rows = [], []
    for slot in range(1, 6):
        attempted = first_accepted(slot, prior)
        rows.extend(attempted)
        prior.append(attempted[-1].normalized_partition)
    return c.build_synthetic_ledger(rows, SOURCE_SHA)


def reseal(payload: dict) -> None:
    payload["content_sha256"] = c.content_sha256(payload)


def main() -> int:
    require(not (ROOT / "research/g9/stage2_generation").exists(), "fixtures must not create a production output directory")
    payload = valid_payload()
    receipt = c.validate_generation_ledger(payload, INPUTS, SOURCE_SHA)
    require(receipt["verdict"] == "accepted" and receipt["slot_count"] == 5
            and len(receipt["accepted_instances"]) == 5, "valid ledger rejected")
    for label, mutate in (
        ("protocol pin", lambda p: p.__setitem__("protocol_file_sha256", "0" * 64)),
        ("generator pin", lambda p: p.__setitem__("generator_source_sha256", "0" * 64)),
        ("scope statement", lambda p: p.__setitem__("scientific_outputs", "present")),
        ("extra top key", lambda p: p.__setitem__("extra", 1)),
        ("float leaf", lambda p: p["attempts"][0].__setitem__("feasible_count", 1.0)),
        ("bool leaf", lambda p: p["attempts"][0].__setitem__("feasible_count", True)),
        ("seed tamper", lambda p: p["attempts"][0]["returns_seed"].__setitem__("seed_uint128_decimal", "0")),
        ("partition tamper", lambda p: p["attempts"][0].__setitem__("partition_sha256", "0" * 64)),
        ("feasible tamper", lambda p: p["attempts"][0].__setitem__("feasible_count", 0)),
        # The synthetic first attempt is accepted and consequently has the
        # legitimate empty list.  Substitute a valid-but-wrong code so this
        # exercises replay consistency rather than making a no-op edit.
        ("rejection tamper", lambda p: p["attempts"][0].__setitem__("rejection_codes", ["feasible_set_below_100"])),
        ("order tamper", lambda p: p["attempts"][0].__setitem__("attempt", 1)),
        ("trailing row", lambda p: p["attempts"].append(copy.deepcopy(p["attempts"][-1]))),
    ):
        bad = copy.deepcopy(payload)
        mutate(bad)
        reseal(bad)
        rejected(lambda bad=bad: c.validate_generation_ledger(bad, INPUTS, SOURCE_SHA), label)
    unrehashed = copy.deepcopy(payload)
    unrehashed["attempts"][0]["outcome"] = "rejected"
    rejected(lambda: c.validate_generation_ledger(unrehashed, INPUTS, SOURCE_SHA), "content hash tamper")
    print("PASS Stage-2 generation-contract fixtures; synthetic ledger only, no Stage-2 candidate or output")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

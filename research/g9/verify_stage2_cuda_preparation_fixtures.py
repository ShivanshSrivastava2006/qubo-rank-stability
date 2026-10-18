#!/usr/bin/env python3
"""Pure synthetic fixtures for exact 20-bit decoded/slack preparation."""
from __future__ import annotations

import copy
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from research.g9.cuda_qualification import stage2_cuda_preparation as prep  # noqa: E402


class FixtureError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise FixtureError(message)


def rejected(action, label: str) -> None:
    try:
        action()
    except prep.PreparationError:
        return
    except Exception as exc:
        raise FixtureError(f"{label}: raw {type(exc).__name__}") from exc
    raise FixtureError(f"{label}: accepted")


def main() -> int:
    instance = prep.synthetic_instance()
    domain = prep.synthetic_domain(instance)
    require(len(domain) == 257 and len({index for index, _ in domain}) == 257, "synthetic domain coverage drift")
    require(all(prep.exact_auxiliary(instance, prep.canonical_index_to_mask(index)) == auxiliary for index, auxiliary in domain),
            "exact auxiliary replay drift")
    require(all(all(value == 0.0 for value in prep.prepared_terms(instance, index, auxiliary)[12:]) for index, auxiliary in domain),
            "exact lift should yield zero slack squares")
    report = {**prep.expected_self_test(), "device_index": 0, "device_name": "synthetic NVIDIA"}
    require(prep.validate_self_test_report(report)["verdict"] == "pass", "valid preparation report refused")
    for label, mutate in (
        ("domain", lambda p: p.__setitem__("domain_checksum", "0" * 16)),
        ("auxiliary", lambda p: p.__setitem__("auxiliary_bits", 18)),
        ("terms", lambda p: p.__setitem__("terms_checksum", "0" * 16)),
        ("nonfinite", lambda p: p.__setitem__("nonfinite_terms", 1)),
        ("float", lambda p: p.__setitem__("state_count", 257.0)),
    ):
        bad = copy.deepcopy(report)
        mutate(bad)
        rejected(lambda bad=bad: prep.validate_self_test_report(bad), label)
    rejected(lambda: prep.canonical_index_to_mask(-1), "negative index")
    rejected(lambda: prep.canonical_index_to_mask(1 << 20), "large index")
    print("PASS Stage-2 CUDA preparation fixtures; synthetic 20-bit decoded/slack terms only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

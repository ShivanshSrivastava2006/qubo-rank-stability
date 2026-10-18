#!/usr/bin/env python3
"""Synthetic fixtures for the arbitrary-membership prepared-domain adapter.

Nothing here draws, screens, or retains a Stage-2 candidate, opens a canonical
input, writes a file, or produces a scientific value.
"""
from __future__ import annotations

import copy
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from research.g9.cuda_qualification import stage2_cuda_membership_adapter as adapter  # noqa: E402


class FixtureError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise FixtureError(message)


def rejected(action, label: str) -> None:
    try:
        action()
    except adapter.MembershipAdapterError:
        return
    except Exception as exc:
        raise FixtureError(f"{label}: raw {type(exc).__name__}") from exc
    raise FixtureError(f"{label}: accepted")


CONTIGUOUS = tuple(tuple(range(sector * 5, sector * 5 + 5)) for sector in range(4))


def check_membership() -> None:
    blocks = adapter.validate_membership(adapter.SYNTHETIC_MEMBERSHIP)
    require(blocks == adapter.SYNTHETIC_MEMBERSHIP, "validated membership drifted")
    # The synthetic partition must be genuinely non-contiguous: it differs from
    # the inherited sector*5+offset blocks, and no block is a contiguous run.
    require(not adapter.is_contiguous_membership(blocks), "synthetic partition is the contiguous assumption")
    require(blocks != CONTIGUOUS, "synthetic partition equals the contiguous blocks")
    for sector, block in enumerate(blocks):
        require(tuple(range(block[0], block[0] + 5)) != block, f"sector[{sector}] is a contiguous run")
    require(adapter.is_contiguous_membership(CONTIGUOUS), "contiguous detector fails on contiguous blocks")
    # Member order within a block is structurally enforced, not numerically:
    # a sector sum of 0/1 doubles is exact in any order, so an unsorted block
    # must be refused by the validator rather than by a checksum.
    unsorted_block = (adapter.SYNTHETIC_MEMBERSHIP[0][::-1],) + adapter.SYNTHETIC_MEMBERSHIP[1:]
    rejected(lambda: adapter.validate_membership(unsorted_block), "unsorted sector block")
    for label, bad in (
        ("three sectors", adapter.SYNTHETIC_MEMBERSHIP[:3]),
        ("short block", ((0, 5, 9, 14),) + adapter.SYNTHETIC_MEMBERSHIP[1:]),
        ("repeated asset", ((0, 0, 9, 14, 19),) + adapter.SYNTHETIC_MEMBERSHIP[1:]),
        ("out-of-range asset", ((0, 5, 9, 14, 20),) + adapter.SYNTHETIC_MEMBERSHIP[1:]),
        ("incomplete cover", ((0, 5, 9, 14, 18),) + adapter.SYNTHETIC_MEMBERSHIP[1:]),
        ("non-integer member", ((0.0, 5, 9, 14, 19),) + adapter.SYNTHETIC_MEMBERSHIP[1:]),
    ):
        rejected(lambda bad=bad: adapter.validate_membership(bad), label)
    swapped = ((0, 5, 9, 14, 17), (1, 4, 8, 12, 19)) + adapter.SYNTHETIC_MEMBERSHIP[2:]
    require(adapter.membership_checksum(swapped) != adapter.membership_checksum(adapter.SYNTHETIC_MEMBERSHIP),
            "membership checksum ignores a swapped asset")


def check_canonical_order() -> None:
    for index in (0, 1, 2, 3, 1023, 12345, (1 << 20) - 1):
        mask = adapter.canonical_index_to_mask(index)
        expected = 0
        for asset in range(20):
            expected |= ((index >> (19 - asset)) & 1) << asset
        require(mask == expected, f"canonical order drift at {index}")
    rejected(lambda: adapter.canonical_index_to_mask(-1), "negative index")
    rejected(lambda: adapter.canonical_index_to_mask(1 << 20), "oversized index")
    rejected(lambda: adapter.canonical_index_to_mask(1.0), "non-integer index")


def check_membership_is_load_bearing() -> None:
    """Sector residuals must actually depend on the explicit membership."""
    instance = adapter.synthetic_instance()
    contiguous = dict(instance)
    contiguous["sectors"] = CONTIGUOUS
    differing = 0
    for index in adapter.synthetic_indices():
        explicit = adapter.decoded_terms(instance, index)[2:6]
        inherited = adapter.decoded_terms(contiguous, index)[2:6]
        if explicit != inherited:
            differing += 1
    require(differing > 0, "contiguous fallback would be numerically invisible")
    require(differing > adapter.STATE_COUNT // 2, "membership is only marginally load-bearing")


def check_lift_policy() -> None:
    """Frozen rule: clamped floor/floor+1, all ties retained; exactness is separate."""
    require(adapter.register_minimizers(2.0, 3) == ((2, 0.0),), "exact representable case drift")
    require(adapter.register_is_exactly_representable(2.0, 3), "exact flag drift")
    require(adapter.register_minimizers(-1.0, 3) == ((0, 1.0),), "clamped-low case drift")
    require(not adapter.register_is_exactly_representable(-1.0, 3), "negative residual marked exact")
    require(adapter.register_minimizers(9.0, 3) == ((3, 36.0),), "clamped-high case drift")
    tie = adapter.register_minimizers(0.5, 3)
    require(len(tie) == 2 and tie[0][0] == 0 and tie[1][0] == 1 and tie[0][1] == tie[1][1],
            "half-integer tie must retain both minimizers")
    require(not adapter.register_is_exactly_representable(0.5, 3), "half-integer marked exact")
    require(all(value == 0.0 for _, value in
                (adapter.register_minimizers(residual, 3)[0] for residual in (0.0, 1.0, 2.0, 3.0))),
            "exactly representable registers must have zero penalty")
    # A non-finite residual must be refused before any narrowing conversion,
    # by the typed error rather than a raw ValueError/OverflowError.
    for label, residual in (("NaN", float("nan")), ("+inf", float("inf")), ("-inf", float("-inf"))):
        rejected(lambda residual=residual: adapter.register_minimizers(residual, 3), f"{label} residual minimizers")
        rejected(lambda residual=residual: adapter.register_is_exactly_representable(residual, 3),
                 f"{label} residual exactness")
        rejected(lambda residual=residual: adapter._floor_double(residual), f"{label} residual floor")
    rejected(lambda: adapter.register_minimizers("2.0", 3), "non-numeric residual")
    # A non-finite instance quantity must surface as the same typed refusal
    # through the full preparation path, not as a raw conversion error.
    for label, field in (("c", "c"), ("b", "b")):
        poisoned = dict(adapter.synthetic_instance())
        poisoned[field] = float("nan")
        rejected(lambda poisoned=poisoned: adapter.state_lift_policy(poisoned, adapter.synthetic_indices()[0]),
                 f"non-finite instance {label}")
    # The probe table must exercise every branch of the frozen rule.
    branches = {"exact": 0, "clamped": 0, "tied": 0}
    for residual, maximum in adapter.policy_probe_table():
        minimizers = adapter.register_minimizers(residual, maximum)
        if adapter.register_is_exactly_representable(residual, maximum):
            branches["exact"] += 1
        else:
            branches["clamped"] += 1
        if len(minimizers) > 1:
            branches["tied"] += 1
    require(all(count > 0 for count in branches.values()), f"probe table misses a branch: {branches}")


def check_layout() -> None:
    require([adapter.register_offset(reg) for reg in range(5)] == [0, 2, 4, 6, 8], "register offsets drift")
    require([adapter.register_maximum(reg) for reg in range(5)] == [3, 3, 3, 3, 2047], "register maxima drift")
    packed = adapter.pack_auxiliary([1, 2, 3, 0, 1365])
    require(packed == 1 | (2 << 2) | (3 << 4) | (0 << 6) | (1365 << 8), "packing layout drift")
    require(packed < (1 << adapter.AUXILIARY_BITS), "packed word exceeds the 19-bit layout")
    for register, expected in enumerate((1.0, 2.0, 3.0, 0.0, 1365.0)):
        require(adapter.unpack_register_value(packed, register) == expected,
                f"register[{register}] bit weights drift")
    rejected(lambda: adapter.pack_auxiliary([1, 2, 3, 0]), "short packing")
    rejected(lambda: adapter.pack_auxiliary([4, 0, 0, 0, 0]), "sector value above its register")
    rejected(lambda: adapter.pack_auxiliary([0, 0, 0, 0, 2048]), "budget value above its register")
    rejected(lambda: adapter.unpack_register_value(1 << adapter.AUXILIARY_BITS, 0), "oversized auxiliary word")


def check_report() -> None:
    expected = adapter.expected_self_test()
    report = {**expected, "device_index": 0, "device_name": "synthetic NVIDIA"}
    require(adapter.validate_self_test_report(report)["verdict"] == "pass", "valid report refused")
    require(report["exact_registers"] > 0 and report["clamped_registers"] > 0,
            "instance table must exercise exact and clamped registers")
    require(report["exact_registers"] + report["clamped_registers"]
            == adapter.STATE_COUNT * adapter.REGISTER_COUNT, "register census drift")
    require(report["reconstruction_mismatches"] == 0 and report["nonfinite_terms"] == 0,
            "baseline report must be clean")
    for label, mutate in (
        ("membership", lambda p: p.__setitem__("membership_checksum", "0" * 16)),
        ("domain", lambda p: p.__setitem__("domain_checksum", "0" * 16)),
        ("terms", lambda p: p.__setitem__("terms_checksum", "0" * 16)),
        ("policy", lambda p: p.__setitem__("lift_policy_checksum", "0" * 16)),
        ("packed", lambda p: p.__setitem__("packed_lift_checksum", "0" * 16)),
        ("probe", lambda p: p.__setitem__("policy_probe_checksum", "0" * 16)),
        ("auxiliary bits", lambda p: p.__setitem__("auxiliary_bits", 18)),
        ("exact census", lambda p: p.__setitem__("exact_registers", 0)),
        ("mismatch", lambda p: p.__setitem__("reconstruction_mismatches", 1)),
        ("nonfinite", lambda p: p.__setitem__("nonfinite_terms", 1)),
        ("scope", lambda p: p.__setitem__("scientific_outputs", "present")),
        ("float", lambda p: p.__setitem__("state_count", 257.0)),
        ("extra", lambda p: p.__setitem__("extra", 1)),
    ):
        bad = copy.deepcopy(report)
        mutate(bad)
        rejected(lambda bad=bad: adapter.validate_self_test_report(bad), label)


def main() -> int:
    require(not (ROOT / "research/g9/stage2_generation").exists(), "fixtures must not create a Stage-2 output")
    check_membership()
    check_canonical_order()
    check_membership_is_load_bearing()
    check_lift_policy()
    check_layout()
    check_report()
    print("PASS Stage-2 membership adapter fixtures; synthetic non-contiguous partition only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

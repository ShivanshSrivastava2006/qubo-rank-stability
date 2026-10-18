#!/usr/bin/env python3
"""Synthetic fixtures for the generic full-domain slack-cache foundation.

Nothing here opens a real input, draws a candidate, or writes a file, and no
energy, minimum, tie set, label or record is produced.
"""
from __future__ import annotations

import copy
from pathlib import Path
import random
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from research.g9.cuda_qualification import stage2_cuda_full_domain_cache as cache  # noqa: E402


class FixtureError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise FixtureError(message)


def rejected(action, label: str) -> None:
    try:
        action()
    except cache.FullDomainCacheError:
        return
    except Exception as exc:
        raise FixtureError(f"{label}: raw {type(exc).__name__}") from exc
    raise FixtureError(f"{label}: accepted")


CONTIGUOUS = tuple(tuple(range(sector * 5, sector * 5 + 5)) for sector in range(4))
PAYLOAD = cache.validate_payload(cache.synthetic_payload())
BUILT = cache.build_cache(cache.synthetic_payload())


def check_payload() -> None:
    require(not cache.is_contiguous_membership(PAYLOAD["sectors"]), "synthetic partition is contiguous")
    require(cache.is_contiguous_membership(CONTIGUOUS), "contiguous detector is broken")
    rejected(lambda: cache.validate_membership((PAYLOAD["sectors"][0][::-1],) + PAYLOAD["sectors"][1:]),
             "unsorted sector block")
    rejected(lambda: cache.validate_membership(PAYLOAD["sectors"][:3]), "three sectors")
    for label, mutate in (
        ("missing key", lambda p: p.pop("mu")),
        ("short mu", lambda p: p.__setitem__("mu", p["mu"][:-1])),
        ("non-finite price", lambda p: p.__setitem__("prices", (float("nan"),) + tuple(p["prices"][1:]))),
        ("negative price", lambda p: p.__setitem__("prices", (-1.0,) + tuple(p["prices"][1:]))),
        ("asymmetric sigma", lambda p: p.__setitem__(
            "sigma", [list(row[:1]) + [row[1] + 1.0] + list(row[2:]) if index == 0 else list(row)
                      for index, row in enumerate(p["sigma"])])),
        ("non-integer K", lambda p: p.__setitem__("k", 6.5)),
        ("non-finite B", lambda p: p.__setitem__("b", float("inf"))),
    ):
        bad = dict(cache.synthetic_payload())
        mutate(bad)
        rejected(lambda bad=bad: cache.validate_payload(bad), label)


def check_canonical_order() -> None:
    for index in (0, 1, 2, 3, 1023, 12345, cache.STATE_COUNT - 1):
        bits = cache.canonical_bits(index)
        expected = tuple((index >> (19 - asset)) & 1 for asset in range(20))
        require(bits == expected, f"canonical order drift at {index}")
    rejected(lambda: cache.canonical_bits(-1), "negative decoded index")
    rejected(lambda: cache.canonical_bits(cache.STATE_COUNT), "decoded index past the domain")


def check_fast_tables_against_frozen_order() -> None:
    """The split-half tables must reproduce the literal frozen accumulation."""
    first_counts, first_spend, second_counts, second_spend = cache._half_tables(PAYLOAD)
    c_value, b_value = float(PAYLOAD["c"]), float(PAYLOAD["b"])
    random.seed(20260922)
    probes = [0, 1, 2, cache.STATE_COUNT - 1, cache.STATE_COUNT - 2, (1 << 19), (1 << 10) - 1]
    probes += [random.randrange(cache.STATE_COUNT) for _ in range(600)]
    for index in probes:
        first, second = index >> cache.HALF_WIDTH, index & ((1 << cache.HALF_WIDTH) - 1)
        fast_sector = tuple(c_value - float(first_counts[first][sector] + second_counts[second][sector])
                            for sector in range(cache.SECTOR_COUNT))
        fast_budget = b_value - (first_spend[first] + second_spend[second])
        frozen_sector, frozen_budget = cache.frozen_residuals(PAYLOAD, index)
        require(fast_sector == frozen_sector, f"sector residual tables differ from the frozen order at {index}")
        require(fast_budget == frozen_budget, f"budget residual table differs from the frozen order at {index}")


def check_frozen_budget_transcript() -> None:
    """The authoritative budget residual must be the literal frozen fold.

    Binary64 addition does not reassociate, so a split-half price sum can
    differ from the frozen left-to-right accumulation.  This payload is a
    concrete witness: assets 9, 10 and 11 are selected at canonical index
    1792, the frozen fold reaches 1024.0 and a reassociated pair of half sums
    reaches 1022.0, giving different register minimizers.
    """
    prices = [float(1 + (asset % 5)) for asset in range(20)]
    prices[9], prices[10], prices[11] = 1e16, 1.0, 1.0
    payload = dict(cache.synthetic_payload())
    payload["prices"] = prices
    payload["b"] = 1e16 + 1024.0
    payload = cache.validate_payload(payload)
    index = 1792
    require(tuple(asset for asset in range(20) if (index >> (19 - asset)) & 1) == (9, 10, 11),
            "the witness index no longer selects assets 9, 10 and 11")
    frozen = cache.frozen_residuals(payload, index)[1]
    require(frozen == 1024.0, f"frozen budget residual drifted to {frozen!r}")
    # The authoritative path, both with and without the prefix memo.
    _, first_spend, _, second_spend = cache._half_tables(payload)
    with_prefix = cache.budget_residual(payload, index, first_spend)
    without_prefix = cache.budget_residual(payload, index, None)
    require(with_prefix == frozen and without_prefix == frozen,
            f"the cache path gave {with_prefix!r}/{without_prefix!r}, not the frozen {frozen!r}")
    # A return to split-half reassociation would be caught here.
    reassociated = float(payload["b"]) - (first_spend[index >> cache.HALF_WIDTH]
                                          + second_spend[index & ((1 << cache.HALF_WIDTH) - 1)])
    require(reassociated == 1022.0, f"the reassociated witness drifted to {reassociated!r}")
    require(reassociated != frozen, "the witness no longer separates the two orders")
    sector_max, budget_max = cache.register_maximum(0), cache.register_maximum(cache.SECTOR_COUNT)
    require(cache.register_minimizers(frozen, budget_max)
            != cache.register_minimizers(reassociated, budget_max),
            "the witness no longer changes the admitted minimizers")
    require(sector_max == 3, "sector register width drifted")
    # The shipped payload must agree under both call forms as well.
    shipped = cache.validate_payload(cache.synthetic_payload())
    _, shipped_prefix, _, _ = cache._half_tables(shipped)
    for probe in (0, 1, 1792, 999999, cache.STATE_COUNT - 1):
        expected = cache.frozen_residuals(shipped, probe)[1]
        require(cache.budget_residual(shipped, probe, shipped_prefix) == expected
                and cache.budget_residual(shipped, probe, None) == expected,
                f"shipped budget residual differs from the frozen fold at {probe}")


def check_minimizer_memo() -> None:
    """Every distinct residual the payload produces must replay the direct rule."""
    sector_max, budget_max = cache.register_maximum(0), cache.register_maximum(cache.SECTOR_COUNT)
    require(len(BUILT["distinct_residuals"]) > 1, "the payload produced a single residual value")
    for residual in BUILT["distinct_residuals"]:
        for maximum in (sector_max, budget_max):
            direct = cache.register_minimizers(residual, maximum)
            require(len(direct) in (1, 2), f"residual {residual!r} produced {len(direct)} minimizers")
            require(tuple(sorted(direct)) == direct, "minimizers are not ascending")
    require(cache.register_minimizers(2.0, 3) == (2,), "exact case drift")
    require(cache.register_minimizers(-1.0, 3) == (0,), "clamped-low case drift")
    require(cache.register_minimizers(9.0, 3) == (3,), "clamped-high case drift")
    require(cache.register_minimizers(0.5, 3) == (0, 1), "half-integer tie drift")
    require(cache.register_is_exactly_representable(2.0, 3), "exact flag drift")
    require(not cache.register_is_exactly_representable(0.5, 3), "half-integer marked exact")
    for label, residual in (("NaN", float("nan")), ("+inf", float("inf")), ("-inf", float("-inf"))):
        rejected(lambda residual=residual: cache.register_minimizers(residual, 3), f"{label} residual")
        rejected(lambda residual=residual: cache.register_is_exactly_representable(residual, 3),
                 f"{label} exactness")
        rejected(lambda residual=residual: cache._floor_double(residual), f"{label} floor")
    # An extreme *finite* residual squares to infinity; the frozen rule refuses
    # it, so this component must refuse it too rather than returning a clamped
    # endpoint, and it must do so without narrowing the residual.
    for residual in (1e200, -1e200):
        rejected(lambda residual=residual: cache.register_minimizers(residual, 2047),
                 f"extreme finite residual {residual:+.0e}")
        require(cache.register_is_exactly_representable(residual, 2047) is False,
                f"extreme residual {residual:+.0e} reported as exactly representable")
    # A large residual whose penalty is still finite stays admissible.
    require(cache.register_minimizers(1e154, 2047) == (2047,), "finite-penalty extreme drifted")


def check_layout() -> None:
    require([cache.register_offset(reg) for reg in range(5)] == [0, 2, 4, 6, 8], "register offsets drift")
    require([cache.register_maximum(reg) for reg in range(5)] == [3, 3, 3, 3, 2047], "register maxima drift")
    packed = cache.pack_lift([1, 2, 3, 0, 1365])
    require(packed == 1 | (2 << 2) | (3 << 4) | (0 << 6) | (1365 << 8), "packing layout drift")
    require(packed < (1 << cache.AUXILIARY_BITS), "packed word exceeds the 19-bit layout")
    rejected(lambda: cache.pack_lift([4, 0, 0, 0, 0]), "sector value above its register")
    rejected(lambda: cache.pack_lift([0, 0, 0, 0, 2048]), "budget value above its register")
    rejected(lambda: cache.pack_lift([1, 2, 3, 0]), "short lift")


def check_capacity() -> None:
    require(cache.capacity_total(cache.STATE_COUNT, 1, cache.CACHE_CAPACITY) == cache.STATE_COUNT,
            "a one-lift domain must be accepted")
    require(cache.capacity_total(cache.STATE_COUNT, cache.MAX_LIFTS_PER_STATE, cache.CACHE_CAPACITY)
            == cache.CACHE_CAPACITY, "the declared bound must be exactly reachable")
    require(cache.capacity_total(cache.STATE_COUNT, cache.MAX_LIFTS_PER_STATE + 1, cache.CACHE_CAPACITY) is None,
            "one lift above the bound must be refused")
    require(cache.capacity_total(cache.STATE_COUNT, 1 << 44, cache.CACHE_CAPACITY) is None,
            "an over-capacity total must be refused")
    require(cache.capacity_total(1 << 62, 1 << 32, cache.CACHE_CAPACITY) is None,
            "a multiplication overflow must be refused, not wrapped")
    require(cache.capacity_total(cache.UINT64_MAX, 2, cache.CACHE_CAPACITY) is None,
            "a saturating product must be refused")
    require(cache.capacity_total(0, 5, cache.CACHE_CAPACITY) == 0, "an empty domain is a valid total")
    rejected(lambda: cache.capacity_total(-1, 1, 10), "negative state count")
    accepts = sum(1 for probe in cache.capacity_probe_table() if cache.capacity_total(*probe) is not None)
    require(accepts == 3 and len(cache.capacity_probe_table()) - accepts == 4,
            "the probe table must cover both outcomes")


def check_complete_domain() -> None:
    offsets, counts, masks = BUILT["offsets"], BUILT["counts"], BUILT["masks"]
    require(len(offsets) == cache.STATE_COUNT + 1, "offsets must span the whole domain")
    require(offsets[0] == 0, "the exclusive prefix must start at zero")
    require(offsets[cache.STATE_COUNT] == BUILT["total"] == len(masks), "prefix total disagrees with the cache")
    require(all(offsets[index + 1] - offsets[index] == counts[index] for index in range(0, cache.STATE_COUNT, 997)),
            "sampled offsets disagree with the per-state multiplicity")
    require(min(counts) >= 1, "every decoded state must retain at least one lift")
    require(max(counts) <= cache.MAX_LIFTS_PER_STATE, "a state exceeded the declared lift bound")
    require(BUILT["exact_registers"] > 0 and BUILT["clamped_registers"] > 0 and BUILT["tied_registers"] > 0,
            "the payload must exercise exact, clamped and tied registers")
    require(BUILT["exact_registers"] + BUILT["clamped_registers"]
            == cache.STATE_COUNT * cache.REGISTER_COUNT, "register census drift")
    require(BUILT["total"] > cache.STATE_COUNT, "tied minimizers are not retained in the cache")
    require(BUILT["unsorted_ranges"] == 0 and BUILT["duplicate_lifts"] == 0,
            "the clean cache reported an ordering or duplicate defect")
    require(all(value < (1 << cache.AUXILIARY_BITS) for value in masks[:4096]),
            "a packed lift escaped the 19-bit layout")
    # The product order is the frozen one: sector 0 slowest, budget fastest.
    for index in (0, 12345, cache.STATE_COUNT - 1):
        sectors, budget = cache.frozen_residuals(PAYLOAD, index)
        choices = [cache.register_minimizers(sectors[sector], cache.register_maximum(sector))
                   for sector in range(cache.SECTOR_COUNT)]
        choices.append(cache.register_minimizers(budget, cache.register_maximum(cache.SECTOR_COUNT)))
        expected = []
        for v0 in choices[0]:
            for v1 in choices[1]:
                for v2 in choices[2]:
                    for v3 in choices[3]:
                        for v4 in choices[4]:
                            expected.append(cache.pack_lift([v0, v1, v2, v3, v4]))
        observed = list(masks[offsets[index]:offsets[index + 1]])
        require(observed == expected, f"lift product order drift at decoded index {index}")


def check_digest_sensitivity() -> None:
    """The cache digest must react to any offset or packed-lift change."""
    offsets, masks, total = BUILT["offsets"], BUILT["masks"], BUILT["total"]
    baseline = cache.cache_digest(offsets, masks, total)
    require(len(baseline) == 32, "the cache digest must be 128 bits")
    for label, position in (("first", 0), ("middle", total // 2), ("last", total - 1)):
        perturbed = list(masks)
        perturbed[position] ^= 1
        require(cache.cache_digest(offsets, perturbed, total) != baseline,
                f"the digest ignores a {label} packed lift")
    shifted = list(offsets)
    shifted[cache.STATE_COUNT // 2] += 1
    require(cache.cache_digest(shifted, masks, total) != baseline, "the digest ignores an offset change")
    require(cache.cache_digest(offsets, masks, total + 1) != baseline, "the digest ignores the declared total")


def check_report() -> None:
    expected = cache.expected_self_test(BUILT)
    report = {**expected, "device_index": 0, "device_name": "synthetic NVIDIA"}
    require(cache.validate_self_test_report(report, BUILT)["verdict"] == "pass", "valid report refused")
    for key, value in report.items():
        require(not isinstance(value, (list, tuple, dict)), f"report carries a container: {key}")
    for label, mutate in (
        ("membership digest", lambda p: p.__setitem__("membership_digest", "0" * 16)),
        ("cache digest", lambda p: p.__setitem__("cache_digest", "0" * 32)),
        ("probe digest", lambda p: p.__setitem__("capacity_probe_digest", "0" * 16)),
        ("lift total", lambda p: p.__setitem__("lift_total", cache.STATE_COUNT)),
        ("tied registers", lambda p: p.__setitem__("tied_registers", 0)),
        ("exact registers", lambda p: p.__setitem__("exact_registers", 0)),
        ("unsorted", lambda p: p.__setitem__("unsorted_ranges", 1)),
        ("duplicates", lambda p: p.__setitem__("duplicate_lifts", 1)),
        ("invalid residuals", lambda p: p.__setitem__("invalid_residuals", 1)),
        ("capacity accepts", lambda p: p.__setitem__("capacity_accepts", 7)),
        ("capacity rejects", lambda p: p.__setitem__("capacity_rejects", 0)),
        ("capacity bound", lambda p: p.__setitem__("max_lifts_per_state", 16)),
        ("state count", lambda p: p.__setitem__("state_count", 1 << 19)),
        ("scope", lambda p: p.__setitem__("scientific_outputs", "present")),
        ("verdict", lambda p: p.__setitem__("verdict", "fail")),
        ("float counter", lambda p: p.__setitem__("lift_total", float(expected["lift_total"]))),
        ("extra key", lambda p: p.__setitem__("extra", 1)),
        ("leaked masks", lambda p: p.__setitem__("packed_lifts", [1, 2, 3])),
    ):
        bad = copy.deepcopy(report)
        mutate(bad)
        rejected(lambda bad=bad: cache.validate_self_test_report(bad, BUILT), label)
    missing = copy.deepcopy(report)
    del missing["device_name"]
    rejected(lambda: cache.validate_self_test_report(missing, BUILT), "missing device metadata")


def main() -> int:
    require(not (ROOT / "research/g9/stage2_generation").exists(), "fixtures must not create a Stage-2 output")
    check_payload()
    check_canonical_order()
    check_fast_tables_against_frozen_order()
    check_frozen_budget_transcript()
    check_minimizer_memo()
    check_layout()
    check_capacity()
    check_complete_domain()
    check_digest_sensitivity()
    check_report()
    print(f"PASS Stage-2 full-domain cache fixtures; {cache.STATE_COUNT} decoded states, "
          f"{BUILT['total']} lifts, synthetic payload only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

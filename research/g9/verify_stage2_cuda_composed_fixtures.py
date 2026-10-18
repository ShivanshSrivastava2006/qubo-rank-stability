#!/usr/bin/env python3
"""Synthetic fixtures for the composed Stage-2 CUDA self-test.

Nothing here opens a canonical input, draws a Stage-2 candidate, or writes a
file, and no energy, minimum, tie index, label or rate leaves the process.
"""
from __future__ import annotations

import copy
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from research.g9.cuda_qualification import stage2_cuda_composed as composed  # noqa: E402


class FixtureError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise FixtureError(message)


def rejected(action, label: str) -> None:
    try:
        action()
    except composed.ComposedSelfTestError:
        return
    except Exception as exc:
        raise FixtureError(f"{label}: raw {type(exc).__name__}") from exc
    raise FixtureError(f"{label}: accepted")


CONTIGUOUS = tuple(tuple(range(sector * 5, sector * 5 + 5)) for sector in range(4))
RUN = composed.pipeline()


def check_membership_and_order() -> None:
    blocks = composed.validate_membership(composed.SYNTHETIC_MEMBERSHIP)
    require(not composed.is_contiguous_membership(blocks), "synthetic partition is contiguous")
    for sector, block in enumerate(blocks):
        require(tuple(range(block[0], block[0] + 5)) != block, f"sector[{sector}] is a contiguous run")
    require(composed.is_contiguous_membership(CONTIGUOUS), "contiguous detector is broken")
    rejected(lambda: composed.validate_membership((blocks[0][::-1],) + blocks[1:]), "unsorted block")
    rejected(lambda: composed.validate_membership(blocks[:3]), "three sectors")
    indices = [composed.canonical_index(position) for position in range(composed.STATE_COUNT)]
    require(all(left < right for left, right in zip(indices, indices[1:])),
            "canonical indices are not strictly ascending")
    for index in (0, 1, 1023, (1 << 20) - 1):
        mask = composed.canonical_index_to_mask(index)
        expected = 0
        for asset in range(20):
            expected |= ((index >> (19 - asset)) & 1) << asset
        require(mask == expected, f"canonical order drift at {index}")
    rejected(lambda: composed.canonical_index_to_mask(1 << 20), "oversized canonical index")
    # The explicit membership must actually change the prepared residuals.
    contiguous_instance = dict(composed.synthetic_instance())
    contiguous_instance["sectors"] = CONTIGUOUS
    differing = sum(1 for position in range(composed.STATE_COUNT)
                    if composed.decoded_terms(composed.synthetic_instance(), composed.canonical_index(position))[2:6]
                    != composed.decoded_terms(contiguous_instance, composed.canonical_index(position))[2:6])
    require(differing > composed.STATE_COUNT // 2, "contiguous fallback would be nearly invisible")


def check_lift_policy() -> None:
    require(RUN["exact_registers"] > 0 and RUN["clamped_registers"] > 0 and RUN["tied_registers"] > 0,
            "the synthetic instance must exercise exact, clamped and tied registers")
    require(RUN["lift_multiplicity_total"] > composed.STATE_COUNT,
            "tied minimizers are not retained in the lift multiplicity")
    require(RUN["exact_registers"] + RUN["clamped_registers"]
            == composed.STATE_COUNT * composed.REGISTER_COUNT, "register census drift")
    # A tied register's two minimizers must carry the same penalty, so the
    # slack energy is independent of which tied lift is taken.
    tied_seen = 0
    for state in RUN["registers"]:
        for entry in state["registers"]:
            minimizers = entry["minimizers"]
            if len(minimizers) > 1:
                tied_seen += 1
                require(minimizers[0][1] == minimizers[1][1], "tied minimizers carry different penalties")
                require(minimizers[0][0] != minimizers[1][0], "tied minimizers repeat a register value")
    require(tied_seen == RUN["tied_registers"], "tied-register census drift")
    require(composed.register_minimizers(0.5, 3) == ((0, 0.25), (1, 0.25)), "half-integer tie drift")
    require(composed.register_minimizers(2.0, 3) == ((2, 0.0),), "exact case drift")
    require(composed.register_minimizers(-1.0, 3) == ((0, 1.0),), "clamped-low case drift")
    require(composed.register_minimizers(9.0, 3) == ((3, 36.0),), "clamped-high case drift")
    for label, residual in (("NaN", float("nan")), ("+inf", float("inf")), ("-inf", float("-inf"))):
        rejected(lambda residual=residual: composed.register_minimizers(residual, 3), f"{label} residual")
        rejected(lambda residual=residual: composed.register_is_exactly_representable(residual, 3),
                 f"{label} exactness")
    require([composed.register_offset(reg) for reg in range(5)] == [0, 2, 4, 6, 8], "register offsets drift")
    require([composed.register_maximum(reg) for reg in range(5)] == [3, 3, 3, 3, 2047], "register maxima drift")
    packed = 1 | (2 << 2) | (3 << 4) | (0 << 6) | (1365 << 8)
    for register, expected in enumerate((1.0, 2.0, 3.0, 0.0, 1365.0)):
        require(composed.unpack_register_value(packed, register) == expected,
                f"register[{register}] bit weights drift")


def check_minimum_and_flags() -> None:
    for encoding in composed.ENCODINGS:
        data = RUN["encodings"][encoding]
        energies = data["energies"]
        minimum = data["minimum"]
        # Strict first-seen: several positions hold the exact minimum, and the
        # reported index is the earliest of them, so '<' vs '<=' matters.
        holders = [position for position, value in enumerate(energies) if value == minimum]
        require(len(holders) >= 2, f"{encoding}: fewer than two exactly equal minima")
        require(data["minimum_index"] == holders[0], f"{encoding}: minimum index is not first-seen")
        require(holders[-1] != holders[0], f"{encoding}: '<=' would pick the same index")
        require(minimum == data["phase_a_minimum"], f"{encoding}: control moved the minimum")
        # Every legal non-zero flag must occur, derived through frozen tau.
        flags = data["flags"]
        for legal in (4, 6, 7):
            require(flags.count(legal) > 0, f"{encoding}: flag {legal} never occurs")
        require(all(composed.flag_is_legal(value) for value in flags), f"{encoding}: illegal flag produced")
        require(not any(composed.flag_violates_nesting(value) for value in flags),
                f"{encoding}: nesting violated")
        # The control ladder must land exactly on its declared flags.
        observed = tuple(flags[position] for position in composed.CONTROL_POSITIONS)
        require(observed == composed.EXPECTED_CONTROL_FLAGS,
                f"{encoding}: control ladder drifted to {observed}")
        # The control must actually move those energies.
        offsets = composed.control_offsets(encoding)
        for slot, position in enumerate(composed.CONTROL_POSITIONS):
            require(energies[position] == minimum + offsets[slot],
                    f"{encoding}: control position {slot} was not applied")
        require(data["per_ch"][0] < data["per_ch"][1] < data["per_ch"][2],
                f"{encoding}: per-c_H counts are not strictly separated")
        require(data["per_ch"][2] == data["offsets"][-1], f"{encoding}: 4096 census differs from the total")
    require(RUN["encodings"]["unbalanced"]["flags"] != RUN["encodings"]["slack"]["flags"],
            "both encodings produced identical flags, so they are not independent")
    require(RUN["encodings"]["unbalanced"]["energies"] != RUN["encodings"]["slack"]["energies"],
            "both encodings produced identical energies")


def check_tau_boundary() -> None:
    """The comparator must use the frozen scale, not a bare tolerance."""
    y_prime = -0.5
    for c_h in composed.CH_VALUES:
        tau = composed.frozen_tau(y_prime + 0.0, y_prime, c_h)
        require(tau == (c_h * composed.EPSILON) * (composed.LAMBDA_REF + abs(y_prime)), "tau formula drift")
        require(composed.frozen_tie(y_prime + tau, y_prime, c_h), "gap == tau must tie")
        require(not composed.frozen_tie(y_prime + tau * 4.0, y_prime, c_h), "gap >> tau must not tie")
    require(composed.tie_flags(y_prime, y_prime) == 7, "zero gap must tie at every c_H")


def check_compaction() -> None:
    for encoding in composed.ENCODINGS:
        data = RUN["encodings"][encoding]
        flags = data["flags"]
        counts = data["chunk_counts"]
        require(counts.count(0) >= 1, f"{encoding}: no empty chunk")
        require(sum(1 for count in counts if count > 0) >= 2, f"{encoding}: fewer than two non-empty chunks")
        require(max(counts) >= 2, f"{encoding}: no chunk holds two flagged entries")
        stream = data["stream"]
        expected = tuple(composed.compact_word(composed.canonical_index(position), value)
                         for position, value in enumerate(flags) if value != 0)
        require(stream == expected, f"{encoding}: stream is not the flagged subsequence in canonical order")
        indices = [word & 0xFFFFFFFF for word in stream]
        require(all(left < right for left, right in zip(indices, indices[1:])),
                f"{encoding}: stream is not strictly ascending")
        require(len(set(indices)) == len(indices), f"{encoding}: stream repeats an index")
        require(data["audit"] == {"order_violations": 0, "duplicate_entries": 0, "unwritten_slots": 0},
                f"{encoding}: clean stream reported a violation")
        swapped = list(stream)
        swapped[0], swapped[1] = swapped[1], swapped[0]
        require(composed.audit_stream(swapped)["order_violations"] > 0, f"{encoding}: swap escaped the audit")
        duplicated = list(stream)
        duplicated[1] = duplicated[0]
        require(composed.audit_stream(duplicated)["duplicate_entries"] > 0,
                f"{encoding}: duplicate escaped the audit")
        dropped = list(stream)
        dropped[1] = composed.SENTINEL
        require(composed.audit_stream(dropped)["unwritten_slots"] > 0, f"{encoding}: drop escaped the audit")


def check_natural_and_controlled_split() -> None:
    """The natural digest must cover the words the control later overwrites."""
    expected = composed.expected_self_test()
    for encoding in composed.ENCODINGS:
        data = RUN["encodings"][encoding]
        require(f"natural_energy_checksum_{encoding}" in expected
                and f"controlled_energy_checksum_{encoding}" in expected,
                f"{encoding}: both energy checksums must be reported")
        require(expected[f"natural_energy_checksum_{encoding}"]
                != expected[f"controlled_energy_checksum_{encoding}"],
                f"{encoding}: natural and controlled digests coincide, so the split proves nothing")
        require(len(data["natural_energies"]) == composed.STATE_COUNT,
                f"{encoding}: natural energies are not retained for every state")
        differing = [position for position in range(composed.STATE_COUNT)
                     if data["natural_energies"][position] != data["energies"][position]]
        require(tuple(differing) == composed.CONTROL_POSITIONS,
                f"{encoding}: the control changed {differing}, not exactly the declared positions")
        # A perturbation of a natural word at a control position is invisible
        # after the overwrite, so only the natural digest can catch it.
        perturbed = list(data["natural_energies"])
        perturbed[composed.CONTROL_POSITIONS[0]] += float.fromhex("0x1p-20")
        digest = composed.FNV_OFFSET
        for value in perturbed:
            digest = composed._fnv(digest, composed._word(value))
        require(f"{digest:016x}" != expected[f"natural_energy_checksum_{encoding}"],
                f"{encoding}: natural digest is insensitive to a control-position defect")


def check_report() -> None:
    expected = composed.expected_self_test()
    report = {**expected, "device_index": 0, "device_name": "synthetic NVIDIA"}
    require(composed.validate_self_test_report(report)["verdict"] == "pass", "valid report refused")
    for key in report:
        require(not isinstance(report[key], (list, tuple, dict)), f"report carries a container: {key}")
    for label, mutate in (
        ("terms checksum", lambda p: p.__setitem__("terms_checksum", "0" * 16)),
        ("lift checksum", lambda p: p.__setitem__("lift_policy_checksum", "0" * 16)),
        ("control checksum", lambda p: p.__setitem__("control_checksum", "0" * 16)),
        ("natural unbalanced energy", lambda p: p.__setitem__("natural_energy_checksum_unbalanced", "0" * 16)),
        ("natural slack energy", lambda p: p.__setitem__("natural_energy_checksum_slack", "0" * 16)),
        ("controlled unbalanced energy", lambda p: p.__setitem__("controlled_energy_checksum_unbalanced", "0" * 16)),
        ("controlled slack energy", lambda p: p.__setitem__("controlled_energy_checksum_slack", "0" * 16)),
        ("unbalanced minimum", lambda p: p.__setitem__("minimum_checksum_unbalanced", "0" * 16)),
        ("slack minimum", lambda p: p.__setitem__("minimum_checksum_slack", "0" * 16)),
        ("unbalanced flags", lambda p: p.__setitem__("flags_checksum_unbalanced", "0" * 16)),
        ("slack compacted", lambda p: p.__setitem__("compacted_checksum_slack", "0" * 16)),
        ("tied registers", lambda p: p.__setitem__("tied_registers", 0)),
        ("multiplicity", lambda p: p.__setitem__("lift_multiplicity_total", 257)),
        ("c_H count", lambda p: p.__setitem__("count_c_h_2048_slack", 0)),
        ("order violations", lambda p: p.__setitem__("order_violations", 1)),
        ("nonfinite", lambda p: p.__setitem__("nonfinite_terms", 1)),
        ("invalid registers", lambda p: p.__setitem__("invalid_registers", 1)),
        ("scope", lambda p: p.__setitem__("scientific_outputs", "present")),
        ("verdict", lambda p: p.__setitem__("verdict", "fail")),
        ("float counter", lambda p: p.__setitem__("compacted_total_slack", 6.0)),
        ("extra key", lambda p: p.__setitem__("extra", 1)),
        ("leaked stream", lambda p: p.__setitem__("compacted_indices", [1, 2, 3])),
    ):
        bad = copy.deepcopy(report)
        mutate(bad)
        rejected(lambda bad=bad: composed.validate_self_test_report(bad), label)
    bad = copy.deepcopy(report)
    del bad["device_name"]
    rejected(lambda: composed.validate_self_test_report(bad), "missing device metadata")


def main() -> int:
    require(not (ROOT / "research/g9/stage2_generation").exists(), "fixtures must not create a Stage-2 output")
    check_membership_and_order()
    check_lift_policy()
    check_minimum_and_flags()
    check_tau_boundary()
    check_compaction()
    check_natural_and_controlled_split()
    check_report()
    print("PASS Stage-2 composed fixtures; fixed synthetic path only, no scientific value emitted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

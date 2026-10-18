#!/usr/bin/env python3
"""Synthetic fixtures for the CUDA stable tie-compaction transport.

Nothing here computes an energy, minimum or label, opens a canonical input,
draws a Stage-2 candidate, or writes a file.
"""
from __future__ import annotations

import copy
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from research.g9.cuda_qualification import stage2_cuda_tie_transport as tie  # noqa: E402


class FixtureError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise FixtureError(message)


def rejected(action, label: str) -> None:
    try:
        action()
    except tie.TieTransportError:
        return
    except Exception as exc:
        raise FixtureError(f"{label}: raw {type(exc).__name__}") from exc
    raise FixtureError(f"{label}: accepted")


def check_control_table() -> None:
    """The fixed table must make every ordering corruption observable."""
    table = tie.synthetic_table()
    require(len(table) == tie.STATE_COUNT, "control table size drift")
    indices = [index for index, _ in table]
    require(all(left < right for left, right in zip(indices, indices[1:])),
            "control indices are not strictly ascending")
    require(all(index < (1 << 20) for index in indices), "control index escaped the 20-bit space")
    flags = [value for _, value in table]
    require(all(tie.flag_is_legal(value) for value in flags), "control table holds an illegal flag")
    for legal in (4, 6, 7):
        require(flags.count(legal) > 0, f"control table lacks a flag-{legal} entry")
    counts = tie.chunk_counts(table)
    require(len(counts) == tie.CHUNK_COUNT, "chunk count drift")
    require(counts.count(0) >= 1, "control table has no empty chunk")
    require(sum(1 for count in counts if count > 0) >= 2, "flagged entries occupy fewer than two chunks")
    require(sum(1 for count in counts if count >= 2) >= 2,
            "no chunk holds two flagged entries, so local-order corruption would be invisible")
    require(len({count for count in counts if count > 0}) >= 2,
            "all non-empty chunks share one count, so chunk-order corruption could hide")


def check_offsets_and_stream() -> None:
    table = tie.synthetic_table()
    counts = tie.chunk_counts(table)
    offsets = tie.exclusive_offsets(counts)
    require(offsets[0] == 0, "exclusive prefix must start at zero")
    require(all(offsets[chunk + 1] - offsets[chunk] == counts[chunk] for chunk in range(tie.CHUNK_COUNT)),
            "exclusive prefix does not match the chunk counts")
    require(offsets[-1] == sum(counts) == sum(1 for _, value in table if value != 0),
            "prefix total disagrees with the flagged census")
    stream = tie.compact_stream(table)
    require(len(stream) == offsets[-1], "stream length differs from the prefix total")
    # Exact ascending output-order proof, and exact equality with the flagged
    # subsequence of the input in its original order.
    expected = tuple(tie.compact_word(index, value) for index, value in table if value != 0)
    require(stream == expected, "stream is not the flagged subsequence in canonical order")
    indices = [word & 0xFFFFFFFF for word in stream]
    require(all(left < right for left, right in zip(indices, indices[1:])),
            "stream is not strictly ascending by canonical index")
    require(len(set(indices)) == len(indices), "stream repeats a canonical index")
    for word, (index, value) in zip(stream, ((i, f) for i, f in table if f != 0)):
        require(word >> 32 == value and word & 0xFFFFFFFF == index, "word layout drift")
    audit = tie.audit_stream(stream)
    require(audit == {"order_violations": 0, "duplicate_entries": 0, "unwritten_slots": 0},
            "clean stream reported a violation")


def check_audit_detects_corruption() -> None:
    """The stream audit must catch reordering, duplication and dropped writes."""
    stream = list(tie.compact_stream(tie.synthetic_table()))
    swapped = list(stream)
    swapped[0], swapped[1] = swapped[1], swapped[0]
    require(tie.audit_stream(swapped)["order_violations"] > 0, "swap escaped the order audit")
    duplicated = list(stream)
    duplicated[1] = duplicated[0]
    result = tie.audit_stream(duplicated)
    require(result["duplicate_entries"] > 0 and result["order_violations"] > 0,
            "duplicate escaped the audit")
    dropped = list(stream)
    dropped[2] = tie.SENTINEL
    require(tie.audit_stream(dropped)["unwritten_slots"] > 0, "dropped entry escaped the audit")
    reversed_stream = list(reversed(stream))
    require(tie.audit_stream(reversed_stream)["order_violations"] > 0, "reversal escaped the order audit")


def check_flag_rules() -> None:
    for legal in tie.LEGAL_FLAGS:
        require(tie.flag_is_legal(legal), f"legal flag {legal} rejected")
        require(not tie.flag_violates_nesting(legal), f"legal flag {legal} reported as unnested")
    for illegal in (1, 2, 3, 5, 8, 12, 15, 255):
        require(not tie.flag_is_legal(illegal), f"illegal flag {illegal} accepted")
    for unnested in (1, 2, 3, 5):
        require(tie.flag_violates_nesting(unnested), f"unnested flag {unnested} not reported")
    for nested_ok in (0, 4, 6, 7, 12):
        require(not tie.flag_violates_nesting(nested_ok), f"flag {nested_ok} wrongly reported as unnested")
    rejected(lambda: tie.compact_word(1 << 32, 4), "index beyond the word half")
    rejected(lambda: tie.compact_word(0, 1 << 32), "flags beyond the word half")
    rejected(lambda: tie.synthetic_index(-1), "negative table position")
    rejected(lambda: tie.synthetic_flags(tie.STATE_COUNT), "table position past the end")


def check_counts_by_ch() -> None:
    """Exact compacted count for each c_H, with the nesting inequality."""
    report = tie.expected_self_test()
    table = tie.synthetic_table()
    for bit, key in enumerate(("count_c_h_1024", "count_c_h_2048", "count_c_h_4096")):
        expected = sum(1 for _, value in table if value & (1 << bit))
        require(report[key] == expected, f"{key} drift")
    require(report["count_c_h_1024"] <= report["count_c_h_2048"] <= report["count_c_h_4096"],
            "per-c_H counts violate nesting")
    require(report["count_c_h_4096"] == report["compacted_total"] == report["direct_flagged_total"],
            "flagged total disagrees with the 4096 census")
    require(report["count_c_h_1024"] > 0 and report["count_c_h_2048"] > report["count_c_h_1024"]
            and report["count_c_h_4096"] > report["count_c_h_2048"],
            "per-c_H counts are not strictly separated, so a c_H mix-up could hide")


def check_report() -> None:
    expected = tie.expected_self_test()
    report = {**expected, "device_index": 0, "device_name": "synthetic NVIDIA"}
    require(tie.validate_self_test_report(report)["verdict"] == "pass", "valid report refused")
    for label, mutate in (
        ("input checksum", lambda p: p.__setitem__("input_checksum", "0" * 16)),
        ("offsets checksum", lambda p: p.__setitem__("offsets_checksum", "0" * 16)),
        ("compacted checksum", lambda p: p.__setitem__("compacted_checksum", "0" * 16)),
        ("compacted total", lambda p: p.__setitem__("compacted_total", 0)),
        ("direct total", lambda p: p.__setitem__("direct_flagged_total", 0)),
        ("total mismatch", lambda p: p.__setitem__("total_mismatch", 1)),
        ("c_H 1024 count", lambda p: p.__setitem__("count_c_h_1024", 0)),
        ("c_H 2048 count", lambda p: p.__setitem__("count_c_h_2048", 0)),
        ("c_H 4096 count", lambda p: p.__setitem__("count_c_h_4096", 0)),
        ("illegal flags", lambda p: p.__setitem__("illegal_flag_entries", 1)),
        ("nesting violations", lambda p: p.__setitem__("nesting_violations", 1)),
        ("order violations", lambda p: p.__setitem__("order_violations", 1)),
        ("duplicates", lambda p: p.__setitem__("duplicate_entries", 1)),
        ("unwritten slots", lambda p: p.__setitem__("unwritten_slots", 1)),
        ("sentinel violations", lambda p: p.__setitem__("sentinel_violations", 1)),
        ("chunk size", lambda p: p.__setitem__("chunk_size", 16)),
        ("verdict", lambda p: p.__setitem__("verdict", "fail")),
        ("scope", lambda p: p.__setitem__("scientific_outputs", "present")),
        ("float counter", lambda p: p.__setitem__("compacted_total", 84.0)),
        ("extra key", lambda p: p.__setitem__("extra", 1)),
        # The report must carry counters and checksums only: a compacted index
        # list would leak the transported payload itself.
        ("leaked index list", lambda p: p.__setitem__("compacted_indices", [1, 2, 3])),
    ):
        bad = copy.deepcopy(report)
        mutate(bad)
        rejected(lambda bad=bad: tie.validate_self_test_report(bad), label)
    for label, missing in (("missing device", "device_index"), ("missing counter", "order_violations")):
        bad = copy.deepcopy(report)
        del bad[missing]
        rejected(lambda bad=bad: tie.validate_self_test_report(bad), label)


def main() -> int:
    require(not (ROOT / "research/g9/stage2_generation").exists(), "fixtures must not create a Stage-2 output")
    check_control_table()
    check_offsets_and_stream()
    check_audit_detects_corruption()
    check_flag_rules()
    check_counts_by_ch()
    check_report()
    print("PASS Stage-2 tie-transport fixtures; synthetic flag table only, no energy, minimum, or label")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

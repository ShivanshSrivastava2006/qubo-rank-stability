#!/usr/bin/env python3
"""Fixtures for the synthetic full-domain energy / minimum / D015 component.

Every check is synthetic: no real input, candidate, instance, ledger, record or
artifact is read or written.  Refusals are asserted by type, not by message.
"""
from __future__ import annotations

import math
from pathlib import Path
import tempfile
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from research.g9 import verify_stage2_cuda_core_stream_engine_frozen_authority as authority  # noqa: E402
from research.g9 import verify_stage2_cuda_core_stream_engine_import_boundary as boundary  # noqa: E402
from research.g9.cuda_qualification import stage2_cuda_core_stream_engine as engine  # noqa: E402

# A coefficient record that is NOT any synthetic row: distinct in every field,
# so "a second record changes the result" is a real claim.
INDEPENDENT_RECORD = {
    "alpha": float.fromhex("0x1p-2"), "sector_slack": float.fromhex("0x1p-3"),
    "budget_slack": float.fromhex("0x1p-2"), "sector_linear": float.fromhex("0x1p-1"),
    "sector_quadratic": float.fromhex("0x1p-4"), "budget_linear": float.fromhex("0x1p-3"),
    "budget_quadratic": float.fromhex("0x1p-5"),
}

FAILURES: list[str] = []
_DOMAIN: dict | None = None


def check(name: str, condition: bool, detail: str = "") -> None:
    if not condition:
        FAILURES.append(f"{name}{(': ' + detail) if detail else ''}")


def refuses(name: str, call, *args, **kwargs) -> None:
    """The call must fail closed with the component's typed refusal."""
    try:
        call(*args, **kwargs)
    except engine.CoreStreamEngineError:
        return
    except Exception as error:  # noqa: BLE001 - an untyped escape is itself a defect
        FAILURES.append(f"{name}: raised {type(error).__name__}, not CoreStreamEngineError")
        return
    FAILURES.append(f"{name}: accepted a malformed input")


def domain() -> dict:
    global _DOMAIN
    if _DOMAIN is None:
        _DOMAIN = engine.build_domain(engine.synthetic_payload())
    return _DOMAIN


def stub_report_inputs():
    """Real report shape without a full-domain build."""
    # Non-zero stubs, so that "corrupting" a digest to zeros is a real drift.
    stub_domain = {"payload": {"sectors": engine.SYNTHETIC_MEMBERSHIP,
                               "lambda_ref": engine.SYNTHETIC_LAMBDA_REF}, "lift_total": 3,
                   "lift_digest": 0x0123456789abcdef, "exact_registers": 5,
                   "clamped_registers": 7, "tied_registers": 11}
    one = {"natural_checksum": 0, "controlled_checksum": 0, "flags_checksum": 0, "minimum": 0.0,
           "minimum_index": 0, "word_count": 0, "per_ch": (0, 0, 0), "illegal": 0, "nesting": 0,
           "compacted_count": 3, "compaction_chunks": 5, "compaction_checksum": 0x1234}
    scans = {(row, encoding): one for row in engine.ROW_NAMES for encoding in engine.ENCODINGS}
    return scans, stub_domain


# --- 1. malformed payload and coefficient refusals ---------------------------

def fixture_malformed_inputs() -> None:
    good = engine.synthetic_payload()

    def mutated(**changes):
        payload = dict(good)
        payload.update(changes)
        return payload

    refuses("payload/sectors overlap", engine.validate_payload,
            mutated(sectors=((0, 1, 2, 3, 4), (0, 5, 6, 7, 8), (9, 10, 11, 12, 13), (14, 15, 16, 17, 18))))
    refuses("payload/sectors incomplete", engine.validate_payload,
            mutated(sectors=((0, 1, 2, 3, 4), (5, 6, 7, 8, 9), (10, 11, 12, 13, 14), (15, 16, 17, 18))))
    refuses("payload/sector member out of range", engine.validate_payload,
            mutated(sectors=((0, 6, 11, 15, 20), (1, 5, 10, 14, 18), (2, 7, 9, 13, 17), (3, 4, 8, 12, 16))))
    refuses("payload/non-finite price", engine.validate_payload,
            mutated(prices=tuple([float("inf")] + list(good["prices"][1:]))))
    refuses("payload/NaN mu", engine.validate_payload,
            mutated(mu=tuple([float("nan")] + list(good["mu"][1:]))))
    refuses("payload/non-finite budget", engine.validate_payload, mutated(b=float("inf")))
    refuses("payload/bool where a number belongs", engine.validate_payload, mutated(k=True))
    refuses("coefficients/unknown row", engine.coefficient_row, "row2")
    refuses("canonical index below range", engine.canonical_bits, -1)
    refuses("canonical index above range", engine.canonical_bits, engine.STATE_COUNT)
    refuses("register index out of range", engine.register_maximum, engine.REGISTER_COUNT)
    refuses("register offset out of range", engine.register_offset, engine.REGISTER_COUNT)
    refuses("minimizer/non-finite residual", engine.register_minimizers, float("nan"), 2047)
    refuses("minimizer/infinite residual", engine.register_minimizers, float("inf"), 2047)
    refuses("control/unknown row-encoding pair", engine.control_offsets, "row0", "balanced")
    check("payload/the anchored partition is non-contiguous",
          not engine.is_contiguous_membership(engine.validate_payload(good)["sectors"]))
    check("payload/two fixed coefficient rows", len(engine.ROW_NAMES) >= 2)
    check("payload/rows differ",
          engine.COEFFICIENT_ROWS["row0"] != engine.COEFFICIENT_ROWS["row1"])


# --- 2. canonical ordering ---------------------------------------------------

def fixture_canonical_order() -> None:
    check("canonical/index 0 is empty", engine.canonical_bits(0) == (0,) * engine.ASSET_COUNT)
    check("canonical/index -1 is full",
          engine.canonical_bits(engine.STATE_COUNT - 1) == (1,) * engine.ASSET_COUNT)
    # Asset 0 is the HIGH bit of the index, not the low bit.
    high = engine.canonical_bits(1 << (engine.DECODED_WIDTH - 1))
    check("canonical/asset 0 is the high bit", high[0] == 1 and sum(high) == 1)
    low = engine.canonical_bits(1)
    check("canonical/asset 19 is the low bit", low[-1] == 1 and sum(low) == 1)
    for index in (0, 1, 2, 3, 511, 512, 1023, 40, 41, 100, 33333, engine.STATE_COUNT - 1):
        bits = engine.canonical_bits(index)
        rebuilt = 0
        for asset, bit in enumerate(bits):
            rebuilt |= bit << (engine.DECODED_WIDTH - 1 - asset)
        check(f"canonical/round trip {index}", rebuilt == index)


# --- 3. layout and cache capacity -------------------------------------------

def fixture_layout_and_capacity() -> None:
    check("layout/auxiliary width",
          engine.AUXILIARY_BITS == engine.SECTOR_COUNT * engine.SECTOR_SLACK_BITS + engine.BUDGET_SLACK_BITS)
    check("layout/auxiliary is 19 bits", engine.AUXILIARY_BITS == 19)
    for sector in range(engine.SECTOR_COUNT):
        check(f"layout/sector {sector} offset",
              engine.register_offset(sector) == sector * engine.SECTOR_SLACK_BITS)
    check("layout/budget offset",
          engine.register_offset(engine.SECTOR_COUNT) == engine.SECTOR_COUNT * engine.SECTOR_SLACK_BITS)
    check("layout/registers do not overlap",
          engine.register_offset(engine.SECTOR_COUNT) + engine.BUDGET_SLACK_BITS == engine.AUXILIARY_BITS)
    check("layout/sector register maximum", engine.register_maximum(0) == 3)
    check("layout/budget register maximum", engine.register_maximum(engine.SECTOR_COUNT) == 2047)
    built = domain()
    check("capacity/lift total within the declared bound",
          built["lift_total"] <= engine.CACHE_CAPACITY)
    check("capacity/offsets start at zero", built["offsets"][0] == 0)
    check("capacity/offsets end at the lift total",
          built["offsets"][engine.STATE_COUNT] == built["lift_total"])
    monotone = all(built["offsets"][i + 1] - built["offsets"][i] == built["lift_counts"][i]
                   for i in range(0, engine.STATE_COUNT, 997))
    check("capacity/offsets are the exact prefix of the counts", monotone)
    check("capacity/every state has at least one lift", min(built["lift_counts"]) >= 1)
    check("capacity/no state exceeds the lift bound",
          max(built["lift_counts"]) <= engine.MAX_LIFTS_PER_STATE)
    check("capacity/ties actually occur", built["tied_registers"] > 0)


# --- 4. exact D015 boundary cases -------------------------------------------

def fixture_d015_boundaries() -> None:
    lambda_ref = engine.synthetic_payload()["lambda_ref"]
    y_min = 1.0
    for bit, c_h in enumerate(engine.CH_VALUES):
        scale = lambda_ref + 1.0
        threshold = (c_h * engine.EPSILON) * scale
        # Exactly at the threshold: a tie, because the comparator is '<='.
        at = y_min + threshold
        if abs(at - y_min) == threshold:
            check(f"d015/gap == tau({c_h:.0f}) ties",
                  bool(engine.tie_flags(at, y_min, lambda_ref) & (1 << bit)))
        just_over = math.nextafter(at, math.inf)
        while abs(just_over - y_min) <= (c_h * engine.EPSILON) * (lambda_ref + max(abs(just_over), 1.0)):
            just_over = math.nextafter(just_over, math.inf)
        check(f"d015/gap > tau({c_h:.0f}) does not tie",
              not engine.tie_flags(just_over, y_min, lambda_ref) & (1 << bit))
    check("d015/identical energies tie at every threshold", engine.tie_flags(1.0, 1.0, lambda_ref) == 7)
    check("d015/a far energy ties nowhere", engine.tie_flags(2.0, 1.0, lambda_ref) == 0)
    # The ladder is strictly nested: 1024 implies 2048 implies 4096.
    for flags in range(8):
        nested = not engine.flag_violates_nesting(flags)
        check(f"d015/nesting classification {flags}",
              nested == (flags in engine.LEGAL_FLAGS))
    check("d015/legal flag set", set(engine.LEGAL_FLAGS) == {0, 4, 6, 7})
    # tau is exactly monotone in c_H because c_H is a power of two.
    for y in (1.0, -3.5, 1e6, 1e-6):
        taus = [engine.frozen_tau(y, y_min, c_h, lambda_ref) for c_h in engine.CH_VALUES]
        check(f"d015/tau monotone at y={y}", taus[0] <= taus[1] <= taus[2])
    # The scale must use max(|y|, |y_min|), not |y_min| alone.
    big, small = 1e12, 1.0
    check("d015/scale uses the larger magnitude",
          engine.frozen_tau(big, small, 1024.0, lambda_ref)
          > engine.frozen_tau(small, small, 1024.0, lambda_ref))
    # The declared control ladder is exactly what the comparator produces.
    for row in engine.ROW_NAMES:
        for encoding in engine.ENCODINGS:
            data = scans()[(row, encoding)]
            minimum = data["minimum"]
            produced = tuple(engine.tie_flags(minimum + offset, minimum, lambda_ref)
                             for offset in engine.control_offsets(row, encoding))
            check(f"d015/control ladder {row}/{encoding}",
                  produced == engine.EXPECTED_CONTROL_FLAGS,
                  f"{produced} != {engine.EXPECTED_CONTROL_FLAGS}")


_SCANS: dict | None = None


def scans() -> dict:
    global _SCANS
    if _SCANS is None:
        _SCANS = {(row, encoding): engine.scan(domain(), row, encoding)
                  for row in engine.ROW_NAMES for encoding in engine.ENCODINGS}
    return _SCANS


# --- 5/6. report schema: counters and checksums only -------------------------

def fixture_report_schema() -> None:
    stub_scans, stub_domain = stub_report_inputs()
    report = engine.expected_self_test(stub_scans, stub_domain, stub_scans)
    good = dict(report)
    good["device_index"] = 0
    good["device_name"] = "host-emulation-fake-gpu"
    accepted = engine.validate_self_test_report(good, stub_scans, stub_domain, stub_scans)
    check("report/the well-formed report is accepted", accepted["verdict"] == "pass")

    for field, value in report.items():
        check(f"report/{field} is a counter, checksum or fixed string",
              isinstance(value, (int, str)) and not isinstance(value, bool))

    def corrupted(**changes):
        payload = dict(good)
        payload.update(changes)
        return payload

    refuses("report/float field", engine.validate_self_test_report,
            corrupted(lift_total=float(report["lift_total"])), stub_scans, stub_domain, stub_scans)
    refuses("report/bool field", engine.validate_self_test_report,
            corrupted(nonfinite_energies=False), stub_scans, stub_domain, stub_scans)
    refuses("report/list container", engine.validate_self_test_report,
            corrupted(tied_registers=[0]), stub_scans, stub_domain, stub_scans)
    refuses("report/dict container", engine.validate_self_test_report,
            corrupted(exact_registers={"a": 1}), stub_scans, stub_domain, stub_scans)
    refuses("report/tuple container", engine.validate_self_test_report,
            corrupted(clamped_registers=(1, 2)), stub_scans, stub_domain, stub_scans)
    refuses("report/leaked energy value", engine.validate_self_test_report,
            corrupted(leaked_minimum=1.0), stub_scans, stub_domain, stub_scans)
    missing = dict(good)
    missing.pop("verdict")
    refuses("report/missing field", engine.validate_self_test_report, missing, stub_scans, stub_domain, stub_scans)
    refuses("report/negative device index", engine.validate_self_test_report,
            corrupted(device_index=-1), stub_scans, stub_domain, stub_scans)
    refuses("report/empty device name", engine.validate_self_test_report,
            corrupted(device_name=""), stub_scans, stub_domain, stub_scans)
    refuses("report/not a mapping", engine.validate_self_test_report,
            ["schema"], stub_scans, stub_domain, stub_scans)
    for field in ("lift_digest", "membership_digest", "coefficient_digest", "control_digest"):
        refuses(f"report/{field} drift", engine.validate_self_test_report,
                corrupted(**{field: "0000000000000000"}), stub_scans, stub_domain, stub_scans)


# --- 7. controlled versus natural checksum separation ------------------------

def fixture_checksum_separation() -> None:
    row, encoding = "row0", "unbalanced"
    baseline = scans()[(row, encoding)]
    control_position = engine.CONTROL_POSITIONS[encoding][0]
    original = engine.natural_energies

    def perturbed(built, wanted_row, wanted_encoding):
        for position, value in enumerate(original(built, wanted_row, wanted_encoding)):
            # A defect exactly under a control position, which the controlled
            # pass overwrites; only the natural checksum can still see it.
            yield value + 1.0 if position == control_position else value

    engine.natural_energies = perturbed
    try:
        shifted = engine.scan(domain(), row, encoding)
    finally:
        engine.natural_energies = original
    check("checksum/the controlled checksum hides a defect under a control",
          shifted["controlled_checksum"] == baseline["controlled_checksum"])
    check("checksum/the natural checksum still catches it",
          shifted["natural_checksum"] != baseline["natural_checksum"])
    check("checksum/natural and controlled checksums differ",
          baseline["natural_checksum"] != baseline["controlled_checksum"])
    # The declared controls really move the first-seen winner.
    check("checksum/a control wins the minimum",
          baseline["minimum_index"] == control_position)
    check("checksum/the natural argmin is elsewhere",
          baseline["natural_index"] != baseline["minimum_index"])
    check("checksum/the controlled minimum value is the natural minimum",
          baseline["minimum"] == baseline["natural_minimum"])
    # The tie-breaking levers must reach both scopes, or the segment-local
    # strict '<' and the fixed-order merge would be untestable.
    for encoding in engine.ENCODINGS:
        zero_positions = [position for position, offset
                          in zip(engine.CONTROL_POSITIONS[encoding],
                                 engine.control_offsets("row0", encoding))
                          if offset == 0.0]
        segments = {position // engine.SEGMENT_SIZE for position in zero_positions}
        check(f"checksum/{encoding}: an exact tie inside one segment",
              len(zero_positions) - len(segments) >= 1, str(zero_positions))
        check(f"checksum/{encoding}: an exact tie across two segments",
              len(segments) >= 2, str(sorted(segments)))
        check(f"checksum/{encoding}: the earliest tied position is first",
              min(zero_positions) == engine.CONTROL_POSITIONS[encoding][0])


# --- 8. chunk syntax ---------------------------------------------------------

def fixture_chunk_syntax() -> None:
    for argv in (["p"], ["p", "--chunk"], ["p", "--chunk", "8/8"], ["p", "--chunk", "0/4"],
                 ["p", "--chunk", "-1/8"], ["p", "--chunk", "00/8"], ["p", "--chunk", "0/8", "x"],
                 ["p", "--chunks", "0/8"], ["p", "--chunk", "7"], ["p", "--chunk", "7/"],
                 ["p", "--chunk", "/8"], ["p", "--chunk", "0/08"], ["p", "--chunk", " 0/8"]):
        try:
            authority.parse_chunk(argv)
        except authority.AuthorityError:
            continue
        FAILURES.append(f"chunk syntax: accepted {argv[1:]}")
    for chunk in range(authority.CHUNK_COUNT):
        check(f"chunk syntax/{chunk}/8 accepted",
              authority.parse_chunk(["p", "--chunk", f"{chunk}/8"]) == chunk)
    check("chunk syntax/N is frozen at 8", authority.CHUNK_COUNT == 8)


# --- 9. the eight chunks partition the domain exactly ------------------------

def fixture_chunk_partition() -> None:
    bounds = [authority.chunk_bounds(chunk) for chunk in range(authority.CHUNK_COUNT)]
    check("partition/first chunk starts at zero", bounds[0][0] == 0)
    check("partition/last chunk ends at the domain",
          bounds[-1][1] == engine.STATE_COUNT)
    for chunk in range(authority.CHUNK_COUNT - 1):
        check(f"partition/chunk {chunk} meets chunk {chunk + 1} with no gap or overlap",
              bounds[chunk][1] == bounds[chunk + 1][0])
    for chunk, (start, stop) in enumerate(bounds):
        check(f"partition/chunk {chunk} is non-empty", stop > start)
    check("partition/the intervals sum to the whole domain",
          sum(stop - start for start, stop in bounds) == engine.STATE_COUNT)
    refuses_authority("partition/chunk 8 refused", authority.chunk_bounds, 8)
    refuses_authority("partition/chunk -1 refused", authority.chunk_bounds, -1)
    # The same split must partition the slack lift stream exactly once.
    offsets = domain()["offsets"]
    covered = sum(int(offsets[stop]) - int(offsets[start]) for start, stop in bounds)
    check("partition/the lift stream is covered exactly once",
          covered == domain()["lift_total"], f"{covered} != {domain()['lift_total']}")
    for chunk in range(authority.CHUNK_COUNT - 1):
        check(f"partition/lift interval {chunk} meets {chunk + 1}",
              int(offsets[bounds[chunk][1]]) == int(offsets[bounds[chunk + 1][0]]))


def refuses_authority(name: str, call, *args) -> None:
    try:
        call(*args)
    except authority.AuthorityError:
        return
    except Exception as error:  # noqa: BLE001
        FAILURES.append(f"{name}: raised {type(error).__name__}, not AuthorityError")
        return
    FAILURES.append(f"{name}: accepted an out-of-range chunk")


# --- 10. a deliberately corrupted value inside the highest chunk -------------

def fixture_corrupted_highest_chunk() -> None:
    """The chunk-7 run must reject a single wrong component engine."""
    highest = authority.CHUNK_COUNT - 1
    start, _stop = authority.chunk_bounds(highest)
    original = engine.unbalanced_energy
    state = {"calls": 0}

    def corrupt(terms, coefficients):
        value = original(terms, coefficients)
        state["calls"] += 1
        # The first comparison of the highest chunk, i.e. decoded state `start`.
        return math.nextafter(value, math.inf) if state["calls"] == 1 else value

    engine.unbalanced_energy = corrupt
    try:
        authority.main(["p", "--chunk", f"{highest}/8"])
    except authority.AuthorityError as error:
        check("corruption/the highest chunk rejects a one-ulp defect",
              f"at {start}" in str(error), str(error))
        check("corruption/the defect was reached in chunk 7", state["calls"] == 1)
        return
    finally:
        engine.unbalanced_energy = original
    FAILURES.append("corruption/the highest chunk accepted a corrupted energy")


# --- 11. directed B1: a one-word defect in the consumed stream --------------

def fixture_natural_stream_defect_chunk7() -> None:
    """A single perturbed word of natural_energies must be rejected in chunk 7.

    The defect is deliberately benign to every other check: it raises a word
    that is far above the minimum, so it stays above the claimed minimum and
    its D015 flags remain 0.  Only a lockstep comparison of the actual stream
    against the frozen authority can see it.
    """
    highest = authority.CHUNK_COUNT - 1
    start, _stop = authority.chunk_bounds(highest)
    original = engine.natural_energies

    def perturbed(built, row, encoding):
        for position, value in enumerate(original(built, row, encoding)):
            if row == "row0" and encoding == "unbalanced" and position == start:
                yield math.nextafter(value, math.inf)
            else:
                yield value

    engine.natural_energies = perturbed
    try:
        authority.main(["p", "--chunk", f"{highest}/8"])
    except authority.AuthorityError as error:
        check("B1/chunk 7 rejects a one-word natural_energies defect",
              "natural_energies differs" in str(error), str(error))
        return
    finally:
        engine.natural_energies = original
    FAILURES.append("B1/chunk 7 accepted a corrupted natural_energies word")


# --- 12. directed B2: tied packed-mask order and retention ------------------

def fixture_packed_mask_order_chunk7() -> None:
    """Reversing or dropping a tied packed mask must be rejected in chunk 7.

    Tied minimizers carry equal penalties, so neither mutation changes any
    energy word; only the authority-side mask derivation binds the order.
    """
    built = domain()
    budget_max = engine.register_maximum(engine.SECTOR_COUNT)
    tied = next((index for index in range(engine.STATE_COUNT)
                 if built["lift_counts"][index] > 1), None)
    check("B2/the domain contains a tied lift", tied is not None)
    if tied is None:
        return
    minimizers = engine.register_minimizers(built["budget_residual"][tied], budget_max)
    penalties = {penalty for _value, penalty in minimizers}
    check("B2/tied minimizers carry equal penalties, so masks are energy-invisible",
          len(penalties) == 1, str(sorted(penalties)))

    highest = authority.CHUNK_COUNT - 1
    original = engine.packed_lift_masks

    def reversed_masks(register_values):
        return reversed(tuple(original(register_values)))

    def dropped_mask(register_values):
        produced = tuple(original(register_values))
        return iter(produced[:1] if len(produced) > 1 else produced)

    for label, replacement, expected in (
            ("reversed", reversed_masks, "packed lift masks differ"),
            ("dropped", dropped_mask, "multiplicity")):
        engine.packed_lift_masks = replacement
        try:
            authority.main(["p", "--chunk", f"{highest}/8"])
        except authority.AuthorityError as error:
            check(f"B2/chunk 7 rejects a {label} tied packed mask",
                  expected in str(error), str(error))
            continue
        finally:
            engine.packed_lift_masks = original
        FAILURES.append(f"B2/chunk 7 accepted a {label} tied packed mask")


# --- 13. the pre-nvcc numerical compile contract ----------------------------

def fixture_compile_contract() -> None:
    required_cuda = ("--fmad=false", "--ftz=false", "--prec-div=true", "--prec-sqrt=true")
    required_host = ("-ffp-contract=off", "-fno-fast-math")
    check("contract/CUDA flags declared", tuple(engine.CUDA_COMPILE_FLAGS) == required_cuda,
          str(engine.CUDA_COMPILE_FLAGS))
    check("contract/host flags declared", tuple(engine.HOST_COMPILE_FLAGS) == required_host,
          str(engine.HOST_COMPILE_FLAGS))
    source = (ROOT / "research/g9/cuda_qualification/stage2_cuda_core_stream_engine.cu").read_text(
        encoding="utf-8")
    for flag in required_cuda + required_host:
        check(f"contract/{flag} documented in the CUDA source", flag in source)
    check("contract/no CUDA numerical qualification is claimed",
          "NOT a claim of real CUDA numerical qualification" in source)


# --- 14. deterministic stable compaction ------------------------------------

def fixture_compaction() -> None:
    size = engine.COMPACTION_CHUNK_SIZE

    def flags_at(positions, word_count, flags=7):
        stream = bytearray(word_count)
        for position in positions:
            stream[position] = flags
        return stream

    empty = engine.compact_flags(bytearray(0))
    check("compaction/an empty stream yields nothing", empty["produced"] == 0)
    unflagged = engine.compact_flags(bytearray(size * 3))
    check("compaction/an unflagged stream yields nothing", unflagged["produced"] == 0)
    check("compaction/an unflagged stream still has chunks", unflagged["chunks"] == 3)

    # Entries spread across several chunks, including both chunk boundaries.
    positions = [0, 1, size - 1, size, size + 5, 2 * size - 1, 2 * size, 3 * size - 1]
    result = engine.compact_flags(flags_at(positions, 3 * size))
    check("compaction/every flagged position is retained", result["produced"] == len(positions))
    carried = [int(entry & 0xFFFFFFFF) for entry in result["entries"]]
    check("compaction/entries are the flagged subsequence in order", carried == positions)
    check("compaction/entries carry the flag word in the high half",
          all(int(entry >> 32) == 7 for entry in result["entries"]))
    check("compaction/per-chunk counts are exact", result["counts"] == (3, 3, 2))
    check("compaction/the prefix is the exclusive scan of the counts",
          result["prefix"] == (0, 3, 6, 8))
    check("compaction/the prefix ends at the produced count",
          result["prefix"][-1] == result["produced"])

    # Mixed legal flag words survive; an illegal one fails closed.
    mixed = bytearray(size)
    mixed[10], mixed[20], mixed[30] = 4, 6, 7
    blended = engine.compact_flags(mixed)
    check("compaction/mixed legal flags are retained", blended["produced"] == 3)
    check("compaction/flag words are preserved exactly",
          [int(entry >> 32) for entry in blended["entries"]] == [4, 6, 7])
    for illegal in (1, 2, 3, 5):
        bad = bytearray(size)
        bad[7] = illegal
        refuses(f"compaction/illegal flag word {illegal}", engine.compact_flags, bad)

    # The hard cap fails closed rather than truncating.
    over = bytearray(engine.MAX_COMPACTED_ENTRIES + 1)
    for position in range(engine.MAX_COMPACTED_ENTRIES + 1):
        over[position] = 7
    refuses("compaction/the hard cap fails closed", engine.compact_flags, over)
    exact = bytearray(engine.MAX_COMPACTED_ENTRIES)
    for position in range(engine.MAX_COMPACTED_ENTRIES):
        exact[position] = 7
    at_cap = engine.compact_flags(exact)
    check("compaction/exactly at the cap is accepted",
          at_cap["produced"] == engine.MAX_COMPACTED_ENTRIES)
    check("compaction/the compacted flag set is exactly {4, 6, 7}",
          tuple(engine.COMPACTED_FLAGS) == (4, 6, 7))


# --- 15. the core is generic over membership --------------------------------

def fixture_generic_membership() -> None:
    check("generic/the alternate partition is valid",
          engine.validate_membership(engine.ALTERNATE_MEMBERSHIP) == engine.ALTERNATE_MEMBERSHIP)
    check("generic/the alternate partition is non-contiguous",
          not engine.is_contiguous_membership(engine.ALTERNATE_MEMBERSHIP))
    check("generic/the two partitions differ",
          engine.ALTERNATE_MEMBERSHIP != engine.SYNTHETIC_MEMBERSHIP)
    primary = engine.validate_payload(engine.synthetic_payload())
    alternate = dict(engine.synthetic_payload())
    alternate["sectors"] = engine.ALTERNATE_MEMBERSHIP
    alternate = engine.validate_payload(alternate)
    # Membership is load-bearing: the same decoded state must yield different
    # sector residuals under a different partition.
    differing = 0
    for index in (1, 2, 3, 37, 4095, 65535, 1048575):
        left = engine.prepared_terms(primary, index)
        right = engine.prepared_terms(alternate, index)
        if left[2:2 + engine.SECTOR_COUNT] != right[2:2 + engine.SECTOR_COUNT]:
            differing += 1
        # The objective and cardinality do not depend on the partition.
        check(f"generic/objective is partition-independent at {index}", left[0] == right[0])
        check(f"generic/cardinality is partition-independent at {index}", left[1] == right[1])
    check("generic/sector residuals do depend on the partition", differing > 0)
    # A contiguous partition must still be accepted -- genericity, not a ban.
    contiguous = dict(engine.synthetic_payload())
    contiguous["sectors"] = tuple(tuple(range(s * 5, s * 5 + 5)) for s in range(4))
    accepted = engine.validate_payload(contiguous)
    check("generic/a contiguous partition is still accepted",
          engine.is_contiguous_membership(accepted["sectors"]))


# --- 16. coefficient rows are load-bearing ----------------------------------

def fixture_coefficient_rows() -> None:
    payload = engine.validate_payload(engine.synthetic_payload())
    terms = engine.prepared_terms(payload, 12345)
    row0 = engine.coefficient_row("row0")
    swapped = dict(row0)
    swapped["sector_linear"], swapped["sector_quadratic"] = (
        row0["sector_quadratic"], row0["sector_linear"])
    check("coefficients/a field swap changes the unbalanced energy",
          engine.unbalanced_energy(terms, swapped) != engine.unbalanced_energy(terms, row0))
    squares = (0.25, 0.25, 0.25, 0.25, 0.5)
    slack_swapped = dict(row0)
    slack_swapped["sector_slack"], slack_swapped["budget_slack"] = (
        row0["budget_slack"], row0["sector_slack"])
    check("coefficients/a slack field swap changes the slack energy",
          engine.slack_energy(terms, squares, slack_swapped)
          != engine.slack_energy(terms, squares, row0))
    check("coefficients/the two rows differ",
          engine.coefficient_row("row0") != engine.coefficient_row("row1"))


# --- B1. the integral-C contract, fail-closed on both paths ------------------

def fixture_integral_c_contract() -> None:
    for good in (0.0, 1.0, 2.0, 3.0, 20.0):
        payload = dict(engine.synthetic_payload())
        payload["c"] = good
        engine.validate_payload(payload)
    check("contract/integral C values are accepted", True)
    for bad in (2.5, 0.5, -1.0, 1.25, float("nan"), float("inf")):
        payload = dict(engine.synthetic_payload())
        payload["c"] = bad
        refuses(f"contract/invalid C={bad} refused by validate_payload",
                engine.validate_payload, payload)
        refuses(f"contract/run_core refuses C={bad} before construction",
                engine.run_core, payload, [engine.coefficient_row("row0")])

    # A fractional C really would tie a sector register: that is WHY the
    # contract is narrowed, and the tie is proven here rather than assumed.
    tied = engine.register_minimizers(0.5, engine.register_maximum(0))
    check("contract/a half-integer sector residual ties", len(tied) == 2, str(tied))
    check("contract/the tied sector penalties are equal",
          len({penalty for _value, penalty in tied}) == 1)
    check("contract/an integral sector residual is unique",
          len(engine.register_minimizers(2.0, engine.register_maximum(0))) == 1)

    # The build fails closed even if validation were bypassed, rather than
    # silently counting a sector tie the energy stage never emits.
    original = engine.validate_payload

    def passthrough(payload):
        return {"mu": tuple(payload["mu"]), "prices": tuple(payload["prices"]),
                "sigma": tuple(tuple(row) for row in payload["sigma"]),
                "kappa_risk": float(payload["kappa_risk"]), "k": float(payload["k"]),
                "c": float(payload["c"]), "b": float(payload["b"]),
                "sectors": engine.validate_membership(payload["sectors"])}

    engine.validate_payload = passthrough
    try:
        smuggled = dict(engine.synthetic_payload())
        smuggled["c"] = 2.5
        refuses("contract/build_domain fails closed on a smuggled fractional C",
                engine.build_domain, smuggled)
    finally:
        engine.validate_payload = original

    # The CUDA host path enforces the same rule before allocating or launching.
    source = (ROOT / "research/g9/cuda_qualification/stage2_cuda_core_stream_engine.cu").read_text(
        encoding="utf-8")
    check("contract/the CUDA host path validates the payload",
          "static bool validate_payload_contract(const PayloadData& payload)" in source)
    check("contract/the CUDA host path rejects non-integral C",
          "static_cast<double>(static_cast<long long>(payload.c_value)) != payload.c_value" in source)
    check("contract/run_core refuses before doing anything",
          "if (!validate_payload_contract(payload)) return false;" in source)


# --- B2. the generic in-memory core API -------------------------------------

def fixture_generic_core_api() -> None:
    good = engine.coefficient_row("row0")
    check("api/a synthetic row is a valid record", engine.coefficient_record(good) == good)
    refuses("api/record with a missing field", engine.coefficient_record,
            {k: v for k, v in good.items() if k != "alpha"})
    refuses("api/record with an extra field", engine.coefficient_record, {**good, "extra": 1.0})
    refuses("api/record with a non-finite field", engine.coefficient_record,
            {**good, "alpha": float("inf")})
    refuses("api/record with a non-positive sector slack", engine.coefficient_record,
            {**good, "sector_slack": 0.0})
    refuses("api/record that is not a mapping", engine.coefficient_record, [1, 2, 3])
    refuses("api/run_core with no records", engine.run_core, engine.synthetic_payload(), [])

    # An independently supplied record, never routed through the row table.
    record = dict(INDEPENDENT_RECORD)
    engine.coefficient_record(record)
    built = domain()
    plain = engine.scan(built, record, "unbalanced", control={})
    controlled = engine.scan(built, "row0", "unbalanced")
    check("api/the generic mode applies no controls",
          plain["minimum_index"] == plain["natural_index"])
    check("api/the qualification mode does apply them",
          controlled["minimum_index"] != controlled["natural_index"])

    # A SECOND valid payload really travels through run_core and changes the
    # result: a structural membership check alone would not prove this.
    alternate = dict(engine.synthetic_payload())
    alternate["sectors"] = engine.ALTERNATE_MEMBERSHIP
    other = engine.run_core(alternate, [record], encodings=("unbalanced",))
    summary = other["summaries"][(0, "unbalanced")]
    check("api/run_core returns bounded summaries only",
          set(summary) == {"word_count", "minimum", "minimum_index", "per_ch", "illegal",
                           "nesting", "compacted_count", "compaction_chunks",
                           "compaction_checksum", "compacted_entries"},
          str(sorted(summary)))
    check("api/run_core returns no full stream",
          len(summary["compacted_entries"]) <= engine.MAX_COMPACTED_ENTRIES)
    check("api/a second payload changes the minimum through the generic core",
          summary["minimum_index"] != plain["minimum_index"],
          f"{summary['minimum_index']} vs {plain['minimum_index']}")
    check("api/and changes the minimum value too", summary["minimum"] != plain["minimum"])
    check("api/the second payload still compacts", summary["compacted_count"] >= 1)


# --- B3. the generic path performs no full-stream transfer ------------------

def fixture_generic_path_isolation() -> None:
    check("isolation/the real source passes the generic-path check",
          boundary.generic_path_violations() == [],
          str(boundary.generic_path_violations()))
    source = boundary.CUDA_SOURCE.read_text(encoding="utf-8")
    original = boundary.CUDA_SOURCE

    def with_source(text: str) -> list[str]:
        with tempfile.TemporaryDirectory(prefix="g9-core-isolation-") as folder:
            candidate = Path(folder) / "source.cu"
            candidate.write_text(text, encoding="utf-8")
            boundary.CUDA_SOURCE = candidate
            try:
                return boundary.generic_path_violations()
            finally:
                boundary.CUDA_SOURCE = original

    stripped = "\n".join(line for line in source.splitlines()
                          if "QUALIFICATION-ONLY" not in line)
    check("isolation/stripping the markers is detected", with_source(stripped) != [])

    moved = source.replace("      ScanResult* result = &results[row][encoding];",
                           "      ok = ok && cudaMemcpy(host_energies, device_energies, 8,\n"
                           "                            cudaMemcpyDeviceToHost) == cudaSuccess;\n"
                           "      ScanResult* result = &results[row][encoding];", 1)
    if moved != source:
        check("isolation/a full-stream copy outside the region is detected",
              with_source(moved) != [])
    else:
        FAILURES.append("isolation/the moved-copy probe did not apply")


# --- instance-specific lambda_ref -------------------------------------------

def fixture_instance_lambda_ref() -> None:
    payload = engine.synthetic_payload()
    check("lambda/the payload carries lambda_ref", "lambda_ref" in payload)
    check("lambda/validate_payload keeps it",
          engine.validate_payload(payload)["lambda_ref"] == engine.SYNTHETIC_LAMBDA_REF)
    for bad in (0.0, -1.0, float("nan"), float("inf")):
        broken = dict(payload)
        broken["lambda_ref"] = bad
        refuses(f"lambda/payload lambda_ref={bad} refused", engine.validate_payload, broken)
    missing = {key: value for key, value in payload.items() if key != "lambda_ref"}
    refuses("lambda/a payload without lambda_ref is refused", engine.validate_payload, missing)
    for bad in (0.0, -1.0, float("nan"), float("inf")):
        refuses(f"lambda/comparator refuses lambda_ref={bad}", engine.tie_flags, 1.0, 1.0, bad)

    # A SECOND instance value must actually move the D015 boundary.
    small, large = engine.SYNTHETIC_LAMBDA_REF, engine.ALTERNATE_LAMBDA_REF
    check("lambda/the two synthetic values differ", small != large)
    # Probe near zero, so lambda_ref -- not |y_min| -- sets the scale.
    y_min = 0.0
    probe = ((engine.CH_VALUES[0] * engine.EPSILON) * small) * 2.5
    check("lambda/tau grows with lambda_ref",
          engine.frozen_tau(probe, y_min, 1024.0, large)
          > engine.frozen_tau(probe, y_min, 1024.0, small))
    check("lambda/a second lambda_ref changes the flag outcome",
          engine.tie_flags(probe, y_min, small) != engine.tie_flags(probe, y_min, large),
          f"{engine.tie_flags(probe, y_min, small)} vs {engine.tie_flags(probe, y_min, large)}")

    # And it must reach the real pipeline, not just the comparator helpers.
    built = domain()
    other = {**built, "payload": {**built["payload"], "lambda_ref": large}}
    base = engine.scan(built, "row0", "unbalanced")
    shifted = engine.scan(other, "row0", "unbalanced")
    check("lambda/the scan's flag checksum follows lambda_ref",
          base["flags_checksum"] != shifted["flags_checksum"])
    check("lambda/the compacted population follows lambda_ref",
          base["compacted_count"] != shifted["compacted_count"],
          f"{base['compacted_count']} vs {shifted['compacted_count']}")
    check("lambda/the minimum itself does not move with lambda_ref",
          base["minimum"] == shifted["minimum"] and
          base["minimum_index"] == shifted["minimum_index"])


# --- the returned interface is enough to rebuild labels ----------------------

def fixture_returned_interface() -> None:
    record = dict(INDEPENDENT_RECORD)
    built = domain()
    for label, coefficients in (("row0", "row0"), ("record", record)):
        data = engine.scan(built, coefficients, "unbalanced", control={})
        entries = tuple(data["compacted_entries"])
        check(f"interface/{label}: the minimum value is returned",
              isinstance(data["minimum"], float))
        check(f"interface/{label}: the first-seen index is returned",
              isinstance(data["minimum_index"], int) and data["minimum_index"] >= 0)
        check(f"interface/{label}: the compacted entries are returned",
              len(entries) == data["compacted_count"] >= 1)
        # Rebuild the stream's own checksum from the returned entries alone.
        rebuilt = engine.FNV_OFFSET
        previous = -1
        ordered = True
        for entry in entries:
            flags, position = int(entry >> 32), int(entry & 0xFFFFFFFF)
            if flags not in engine.COMPACTED_FLAGS or position <= previous:
                ordered = False
            previous = position
            rebuilt = engine._fnv(rebuilt, entry)
        check(f"interface/{label}: entries are ascending with legal flags", ordered)
        check(f"interface/{label}: entries reproduce the compaction checksum",
              rebuilt == data["compaction_checksum"])
        check(f"interface/{label}: the winner is among the compacted entries",
              any(int(entry & 0xFFFFFFFF) == data["minimum_index"] for entry in entries))

    # A second, independently supplied record changes what comes back.
    first = engine.scan(built, "row0", "unbalanced", control={})
    second = engine.scan(built, record, "unbalanced", control={})
    check("interface/a second record changes the returned minimum",
          first["minimum"] != second["minimum"])


def main() -> int:
    fixture_malformed_inputs()
    fixture_canonical_order()
    fixture_chunk_syntax()
    fixture_layout_and_capacity()
    fixture_chunk_partition()
    fixture_d015_boundaries()
    fixture_report_schema()
    fixture_checksum_separation()
    fixture_compile_contract()
    fixture_integral_c_contract()
    fixture_instance_lambda_ref()
    fixture_returned_interface()
    fixture_generic_core_api()
    fixture_generic_path_isolation()
    fixture_compaction()
    fixture_generic_membership()
    fixture_coefficient_rows()
    fixture_corrupted_highest_chunk()
    fixture_natural_stream_defect_chunk7()
    fixture_packed_mask_order_chunk7()
    if FAILURES:
        print("FAIL Stage-2 core-stream engine fixtures: " + "; ".join(FAILURES), file=sys.stderr)
        return 1
    print("PASS Stage-2 core-stream engine fixtures; malformed inputs, canonical order, layout and "
          "capacity, chunk syntax and partition, D015 boundaries, report schema, checksum "
          "separation, the pre-nvcc compile contract, a corrupted value in the highest chunk, "
          "a one-word natural_energies defect, tied packed-mask order, deterministic "
          "compaction, generic membership, coefficient-row sensitivity, the integral-C "
          "contract, the generic in-memory core API, generic-path isolation, the "
          "instance-specific lambda_ref, and the returned minima/entries interface all handled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

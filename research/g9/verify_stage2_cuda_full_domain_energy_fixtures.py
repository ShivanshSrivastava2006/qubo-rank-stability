#!/usr/bin/env python3
"""Fixtures for the synthetic full-domain energy / minimum / D015 component.

Every check is synthetic: no real input, candidate, instance, ledger, record or
artifact is read or written.  Refusals are asserted by type, not by message.
"""
from __future__ import annotations

import math
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from research.g9 import verify_stage2_cuda_full_domain_energy_frozen_authority as authority  # noqa: E402
from research.g9.cuda_qualification import stage2_cuda_full_domain_energy as energy  # noqa: E402

FAILURES: list[str] = []
_DOMAIN: dict | None = None


def check(name: str, condition: bool, detail: str = "") -> None:
    if not condition:
        FAILURES.append(f"{name}{(': ' + detail) if detail else ''}")


def refuses(name: str, call, *args, **kwargs) -> None:
    """The call must fail closed with the component's typed refusal."""
    try:
        call(*args, **kwargs)
    except energy.FullDomainEnergyError:
        return
    except Exception as error:  # noqa: BLE001 - an untyped escape is itself a defect
        FAILURES.append(f"{name}: raised {type(error).__name__}, not FullDomainEnergyError")
        return
    FAILURES.append(f"{name}: accepted a malformed input")


def domain() -> dict:
    global _DOMAIN
    if _DOMAIN is None:
        _DOMAIN = energy.build_domain(energy.synthetic_payload())
    return _DOMAIN


def stub_report_inputs():
    """Real report shape without a full-domain build."""
    # Non-zero stubs, so that "corrupting" a digest to zeros is a real drift.
    stub_domain = {"payload": {"sectors": energy.SYNTHETIC_MEMBERSHIP}, "lift_total": 3,
                   "lift_digest": 0x0123456789abcdef, "exact_registers": 5,
                   "clamped_registers": 7, "tied_registers": 11}
    one = {"natural_checksum": 0, "controlled_checksum": 0, "flags_checksum": 0, "minimum": 0.0,
           "minimum_index": 0, "word_count": 0, "per_ch": (0, 0, 0), "illegal": 0, "nesting": 0}
    scans = {(row, encoding): one for row in energy.ROW_NAMES for encoding in energy.ENCODINGS}
    return scans, stub_domain


# --- 1. malformed payload and coefficient refusals ---------------------------

def fixture_malformed_inputs() -> None:
    good = energy.synthetic_payload()

    def mutated(**changes):
        payload = dict(good)
        payload.update(changes)
        return payload

    refuses("payload/sectors overlap", energy.validate_payload,
            mutated(sectors=((0, 1, 2, 3, 4), (0, 5, 6, 7, 8), (9, 10, 11, 12, 13), (14, 15, 16, 17, 18))))
    refuses("payload/sectors incomplete", energy.validate_payload,
            mutated(sectors=((0, 1, 2, 3, 4), (5, 6, 7, 8, 9), (10, 11, 12, 13, 14), (15, 16, 17, 18))))
    refuses("payload/sector member out of range", energy.validate_payload,
            mutated(sectors=((0, 6, 11, 15, 20), (1, 5, 10, 14, 18), (2, 7, 9, 13, 17), (3, 4, 8, 12, 16))))
    refuses("payload/non-finite price", energy.validate_payload,
            mutated(prices=tuple([float("inf")] + list(good["prices"][1:]))))
    refuses("payload/NaN mu", energy.validate_payload,
            mutated(mu=tuple([float("nan")] + list(good["mu"][1:]))))
    refuses("payload/non-finite budget", energy.validate_payload, mutated(b=float("inf")))
    refuses("payload/bool where a number belongs", energy.validate_payload, mutated(k=True))
    refuses("coefficients/unknown row", energy.coefficient_row, "row2")
    refuses("canonical index below range", energy.canonical_bits, -1)
    refuses("canonical index above range", energy.canonical_bits, energy.STATE_COUNT)
    refuses("register index out of range", energy.register_maximum, energy.REGISTER_COUNT)
    refuses("register offset out of range", energy.register_offset, energy.REGISTER_COUNT)
    refuses("minimizer/non-finite residual", energy.register_minimizers, float("nan"), 2047)
    refuses("minimizer/infinite residual", energy.register_minimizers, float("inf"), 2047)
    refuses("control/unknown row-encoding pair", energy.control_offsets, "row0", "balanced")
    check("payload/the anchored partition is non-contiguous",
          not energy.is_contiguous_membership(energy.validate_payload(good)["sectors"]))
    check("payload/two fixed coefficient rows", len(energy.ROW_NAMES) >= 2)
    check("payload/rows differ",
          energy.COEFFICIENT_ROWS["row0"] != energy.COEFFICIENT_ROWS["row1"])


# --- 2. canonical ordering ---------------------------------------------------

def fixture_canonical_order() -> None:
    check("canonical/index 0 is empty", energy.canonical_bits(0) == (0,) * energy.ASSET_COUNT)
    check("canonical/index -1 is full",
          energy.canonical_bits(energy.STATE_COUNT - 1) == (1,) * energy.ASSET_COUNT)
    # Asset 0 is the HIGH bit of the index, not the low bit.
    high = energy.canonical_bits(1 << (energy.DECODED_WIDTH - 1))
    check("canonical/asset 0 is the high bit", high[0] == 1 and sum(high) == 1)
    low = energy.canonical_bits(1)
    check("canonical/asset 19 is the low bit", low[-1] == 1 and sum(low) == 1)
    for index in (0, 1, 2, 3, 511, 512, 1023, 40, 41, 100, 33333, energy.STATE_COUNT - 1):
        bits = energy.canonical_bits(index)
        rebuilt = 0
        for asset, bit in enumerate(bits):
            rebuilt |= bit << (energy.DECODED_WIDTH - 1 - asset)
        check(f"canonical/round trip {index}", rebuilt == index)


# --- 3. layout and cache capacity -------------------------------------------

def fixture_layout_and_capacity() -> None:
    check("layout/auxiliary width",
          energy.AUXILIARY_BITS == energy.SECTOR_COUNT * energy.SECTOR_SLACK_BITS + energy.BUDGET_SLACK_BITS)
    check("layout/auxiliary is 19 bits", energy.AUXILIARY_BITS == 19)
    for sector in range(energy.SECTOR_COUNT):
        check(f"layout/sector {sector} offset",
              energy.register_offset(sector) == sector * energy.SECTOR_SLACK_BITS)
    check("layout/budget offset",
          energy.register_offset(energy.SECTOR_COUNT) == energy.SECTOR_COUNT * energy.SECTOR_SLACK_BITS)
    check("layout/registers do not overlap",
          energy.register_offset(energy.SECTOR_COUNT) + energy.BUDGET_SLACK_BITS == energy.AUXILIARY_BITS)
    check("layout/sector register maximum", energy.register_maximum(0) == 3)
    check("layout/budget register maximum", energy.register_maximum(energy.SECTOR_COUNT) == 2047)
    built = domain()
    check("capacity/lift total within the declared bound",
          built["lift_total"] <= energy.CACHE_CAPACITY)
    check("capacity/offsets start at zero", built["offsets"][0] == 0)
    check("capacity/offsets end at the lift total",
          built["offsets"][energy.STATE_COUNT] == built["lift_total"])
    monotone = all(built["offsets"][i + 1] - built["offsets"][i] == built["lift_counts"][i]
                   for i in range(0, energy.STATE_COUNT, 997))
    check("capacity/offsets are the exact prefix of the counts", monotone)
    check("capacity/every state has at least one lift", min(built["lift_counts"]) >= 1)
    check("capacity/no state exceeds the lift bound",
          max(built["lift_counts"]) <= energy.MAX_LIFTS_PER_STATE)
    check("capacity/ties actually occur", built["tied_registers"] > 0)


# --- 4. exact D015 boundary cases -------------------------------------------

def fixture_d015_boundaries() -> None:
    y_min = 1.0
    for bit, c_h in enumerate(energy.CH_VALUES):
        scale = energy.LAMBDA_REF + 1.0
        threshold = (c_h * energy.EPSILON) * scale
        # Exactly at the threshold: a tie, because the comparator is '<='.
        at = y_min + threshold
        if abs(at - y_min) == threshold:
            check(f"d015/gap == tau({c_h:.0f}) ties",
                  bool(energy.tie_flags(at, y_min) & (1 << bit)))
        just_over = math.nextafter(at, math.inf)
        while abs(just_over - y_min) <= (c_h * energy.EPSILON) * (energy.LAMBDA_REF + max(abs(just_over), 1.0)):
            just_over = math.nextafter(just_over, math.inf)
        check(f"d015/gap > tau({c_h:.0f}) does not tie",
              not energy.tie_flags(just_over, y_min) & (1 << bit))
    check("d015/identical energies tie at every threshold", energy.tie_flags(1.0, 1.0) == 7)
    check("d015/a far energy ties nowhere", energy.tie_flags(2.0, 1.0) == 0)
    # The ladder is strictly nested: 1024 implies 2048 implies 4096.
    for flags in range(8):
        nested = not energy.flag_violates_nesting(flags)
        check(f"d015/nesting classification {flags}",
              nested == (flags in energy.LEGAL_FLAGS))
    check("d015/legal flag set", set(energy.LEGAL_FLAGS) == {0, 4, 6, 7})
    # tau is exactly monotone in c_H because c_H is a power of two.
    for y in (1.0, -3.5, 1e6, 1e-6):
        taus = [energy.frozen_tau(y, y_min, c_h) for c_h in energy.CH_VALUES]
        check(f"d015/tau monotone at y={y}", taus[0] <= taus[1] <= taus[2])
    # The scale must use max(|y|, |y_min|), not |y_min| alone.
    big, small = 1e12, 1.0
    check("d015/scale uses the larger magnitude",
          energy.frozen_tau(big, small, 1024.0) > energy.frozen_tau(small, small, 1024.0))
    # The declared control ladder is exactly what the comparator produces.
    for row in energy.ROW_NAMES:
        for encoding in energy.ENCODINGS:
            data = scans()[(row, encoding)]
            minimum = data["minimum"]
            produced = tuple(energy.tie_flags(minimum + offset, minimum)
                             for offset in energy.control_offsets(row, encoding))
            check(f"d015/control ladder {row}/{encoding}",
                  produced == energy.EXPECTED_CONTROL_FLAGS,
                  f"{produced} != {energy.EXPECTED_CONTROL_FLAGS}")


_SCANS: dict | None = None


def scans() -> dict:
    global _SCANS
    if _SCANS is None:
        _SCANS = {(row, encoding): energy.scan(domain(), row, encoding)
                  for row in energy.ROW_NAMES for encoding in energy.ENCODINGS}
    return _SCANS


# --- 5/6. report schema: counters and checksums only -------------------------

def fixture_report_schema() -> None:
    stub_scans, stub_domain = stub_report_inputs()
    report = energy.expected_self_test(stub_scans, stub_domain)
    good = dict(report)
    good["device_index"] = 0
    good["device_name"] = "host-emulation-fake-gpu"
    accepted = energy.validate_self_test_report(good, stub_scans, stub_domain)
    check("report/the well-formed report is accepted", accepted["verdict"] == "pass")

    for field, value in report.items():
        check(f"report/{field} is a counter, checksum or fixed string",
              isinstance(value, (int, str)) and not isinstance(value, bool))

    def corrupted(**changes):
        payload = dict(good)
        payload.update(changes)
        return payload

    refuses("report/float field", energy.validate_self_test_report,
            corrupted(lift_total=float(report["lift_total"])), stub_scans, stub_domain)
    refuses("report/bool field", energy.validate_self_test_report,
            corrupted(nonfinite_energies=False), stub_scans, stub_domain)
    refuses("report/list container", energy.validate_self_test_report,
            corrupted(tied_registers=[0]), stub_scans, stub_domain)
    refuses("report/dict container", energy.validate_self_test_report,
            corrupted(exact_registers={"a": 1}), stub_scans, stub_domain)
    refuses("report/tuple container", energy.validate_self_test_report,
            corrupted(clamped_registers=(1, 2)), stub_scans, stub_domain)
    refuses("report/leaked energy value", energy.validate_self_test_report,
            corrupted(leaked_minimum=1.0), stub_scans, stub_domain)
    missing = dict(good)
    missing.pop("verdict")
    refuses("report/missing field", energy.validate_self_test_report, missing, stub_scans, stub_domain)
    refuses("report/negative device index", energy.validate_self_test_report,
            corrupted(device_index=-1), stub_scans, stub_domain)
    refuses("report/empty device name", energy.validate_self_test_report,
            corrupted(device_name=""), stub_scans, stub_domain)
    refuses("report/not a mapping", energy.validate_self_test_report,
            ["schema"], stub_scans, stub_domain)
    for field in ("lift_digest", "membership_digest", "coefficient_digest", "control_digest"):
        refuses(f"report/{field} drift", energy.validate_self_test_report,
                corrupted(**{field: "0000000000000000"}), stub_scans, stub_domain)


# --- 7. controlled versus natural checksum separation ------------------------

def fixture_checksum_separation() -> None:
    row, encoding = "row0", "unbalanced"
    baseline = scans()[(row, encoding)]
    control_position = energy.CONTROL_POSITIONS[encoding][0]
    original = energy.natural_energies

    def perturbed(built, wanted_row, wanted_encoding):
        for position, value in enumerate(original(built, wanted_row, wanted_encoding)):
            # A defect exactly under a control position, which the controlled
            # pass overwrites; only the natural checksum can still see it.
            yield value + 1.0 if position == control_position else value

    energy.natural_energies = perturbed
    try:
        shifted = energy.scan(domain(), row, encoding)
    finally:
        energy.natural_energies = original
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
    for encoding in energy.ENCODINGS:
        zero_positions = [position for position, offset
                          in zip(energy.CONTROL_POSITIONS[encoding],
                                 energy.control_offsets("row0", encoding))
                          if offset == 0.0]
        segments = {position // energy.SEGMENT_SIZE for position in zero_positions}
        check(f"checksum/{encoding}: an exact tie inside one segment",
              len(zero_positions) - len(segments) >= 1, str(zero_positions))
        check(f"checksum/{encoding}: an exact tie across two segments",
              len(segments) >= 2, str(sorted(segments)))
        check(f"checksum/{encoding}: the earliest tied position is first",
              min(zero_positions) == energy.CONTROL_POSITIONS[encoding][0])


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
          bounds[-1][1] == energy.STATE_COUNT)
    for chunk in range(authority.CHUNK_COUNT - 1):
        check(f"partition/chunk {chunk} meets chunk {chunk + 1} with no gap or overlap",
              bounds[chunk][1] == bounds[chunk + 1][0])
    for chunk, (start, stop) in enumerate(bounds):
        check(f"partition/chunk {chunk} is non-empty", stop > start)
    check("partition/the intervals sum to the whole domain",
          sum(stop - start for start, stop in bounds) == energy.STATE_COUNT)
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
    """The chunk-7 run must reject a single wrong component energy."""
    highest = authority.CHUNK_COUNT - 1
    start, _stop = authority.chunk_bounds(highest)
    original = energy.unbalanced_energy
    state = {"calls": 0}

    def corrupt(terms, coefficients):
        value = original(terms, coefficients)
        state["calls"] += 1
        # The first comparison of the highest chunk, i.e. decoded state `start`.
        return math.nextafter(value, math.inf) if state["calls"] == 1 else value

    energy.unbalanced_energy = corrupt
    try:
        authority.main(["p", "--chunk", f"{highest}/8"])
    except authority.AuthorityError as error:
        check("corruption/the highest chunk rejects a one-ulp defect",
              f"at {start}" in str(error), str(error))
        check("corruption/the defect was reached in chunk 7", state["calls"] == 1)
        return
    finally:
        energy.unbalanced_energy = original
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
    original = energy.natural_energies

    def perturbed(built, row, encoding):
        for position, value in enumerate(original(built, row, encoding)):
            if row == "row0" and encoding == "unbalanced" and position == start:
                yield math.nextafter(value, math.inf)
            else:
                yield value

    energy.natural_energies = perturbed
    try:
        authority.main(["p", "--chunk", f"{highest}/8"])
    except authority.AuthorityError as error:
        check("B1/chunk 7 rejects a one-word natural_energies defect",
              "natural_energies differs" in str(error), str(error))
        return
    finally:
        energy.natural_energies = original
    FAILURES.append("B1/chunk 7 accepted a corrupted natural_energies word")


# --- 12. directed B2: tied packed-mask order and retention ------------------

def fixture_packed_mask_order_chunk7() -> None:
    """Reversing or dropping a tied packed mask must be rejected in chunk 7.

    Tied minimizers carry equal penalties, so neither mutation changes any
    energy word; only the authority-side mask derivation binds the order.
    """
    built = domain()
    budget_max = energy.register_maximum(energy.SECTOR_COUNT)
    tied = next((index for index in range(energy.STATE_COUNT)
                 if built["lift_counts"][index] > 1), None)
    check("B2/the domain contains a tied lift", tied is not None)
    if tied is None:
        return
    minimizers = energy.register_minimizers(built["budget_residual"][tied], budget_max)
    penalties = {penalty for _value, penalty in minimizers}
    check("B2/tied minimizers carry equal penalties, so masks are energy-invisible",
          len(penalties) == 1, str(sorted(penalties)))

    highest = authority.CHUNK_COUNT - 1
    original = energy.packed_lift_masks

    def reversed_masks(register_values):
        return reversed(tuple(original(register_values)))

    def dropped_mask(register_values):
        produced = tuple(original(register_values))
        return iter(produced[:1] if len(produced) > 1 else produced)

    for label, replacement, expected in (
            ("reversed", reversed_masks, "packed lift masks differ"),
            ("dropped", dropped_mask, "multiplicity")):
        energy.packed_lift_masks = replacement
        try:
            authority.main(["p", "--chunk", f"{highest}/8"])
        except authority.AuthorityError as error:
            check(f"B2/chunk 7 rejects a {label} tied packed mask",
                  expected in str(error), str(error))
            continue
        finally:
            energy.packed_lift_masks = original
        FAILURES.append(f"B2/chunk 7 accepted a {label} tied packed mask")


# --- 13. the pre-nvcc numerical compile contract ----------------------------

def fixture_compile_contract() -> None:
    required_cuda = ("--fmad=false", "--ftz=false", "--prec-div=true", "--prec-sqrt=true")
    required_host = ("-ffp-contract=off", "-fno-fast-math")
    check("contract/CUDA flags declared", tuple(energy.CUDA_COMPILE_FLAGS) == required_cuda,
          str(energy.CUDA_COMPILE_FLAGS))
    check("contract/host flags declared", tuple(energy.HOST_COMPILE_FLAGS) == required_host,
          str(energy.HOST_COMPILE_FLAGS))
    source = (ROOT / "research/g9/cuda_qualification/stage2_cuda_full_domain_energy.cu").read_text(
        encoding="utf-8")
    for flag in required_cuda + required_host:
        check(f"contract/{flag} documented in the CUDA source", flag in source)
    check("contract/no CUDA numerical qualification is claimed",
          "NOT a claim of real CUDA numerical qualification" in source)


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
    fixture_corrupted_highest_chunk()
    fixture_natural_stream_defect_chunk7()
    fixture_packed_mask_order_chunk7()
    if FAILURES:
        print("FAIL Stage-2 full-domain energy fixtures: " + "; ".join(FAILURES), file=sys.stderr)
        return 1
    print("PASS Stage-2 full-domain energy fixtures; malformed inputs, canonical order, layout and "
          "capacity, chunk syntax and partition, D015 boundaries, report schema, checksum "
          "separation, the pre-nvcc compile contract, a corrupted value in the highest chunk, "
          "a one-word natural_energies defect, and tied packed-mask order all handled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

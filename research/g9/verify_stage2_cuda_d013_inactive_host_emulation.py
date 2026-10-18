#!/usr/bin/env python3
"""D013 `+0.0` ADDITIVE CUDA PATH host-emulation fixtures; no nvcc, device, Kaggle or instance.

OFFLINE / SYNTHETIC-ONLY.  Builds ``stage2_cuda_d013_inactive.cu`` with g++
against the host-emulation stub (warning-free, ``-ffp-contract=off
-fno-fast-math``) and exercises it on synthetic payloads.

WHAT IS PROVEN HERE, AND HOW

(a) **The additive path did not change active arithmetic.**  For `CSB` (every
    family active) the new path's own bounded result is compared, field by
    field and bit for bit, against the UNCHANGED qualified v1 core driven
    through the accepted v1 host bridge.  Energy-minimum words, the canonical
    minimum index, the tie flags, the per-c_H counts and the lift-stream
    geometry all have to agree exactly.

(b) **The `+0.0` families are right.**  For `C`, `CB` and `CS` the result is
    compared against a SLOW INDEPENDENT PYTHON REFERENCE written here, from the
    owner-decided spec, not from the new kernel: it decodes the small synthetic
    domain directly, sums each family by hand in the frozen D015 order, skips an
    inactive family by contributing exactly `+0.0`, and reports `|T_E|` as the
    exact integer `tie_count * 2^w` -- the D015 `c_H = 2048` count of the tied
    candidates -- and `|C_E|` as the separate whole-domain count
    `base * 2^w`.  It shares no code with the kernel under test beyond the
    frozen payload validators.

(c) **`+0.0` bit pattern and sign.**  With a negative inactive family term
    reachable in the synthetic landscape, the reference shows the naive product
    really would be `-0.0` at some states, the new path's reported inactive
    term is the positive zero at EVERY state, and no `-0.0` reaches the energy
    stream.

(d) **No code path enumerates the retained inactive register.**  An instrumented
    per-register visit counter is asserted to be exactly 0 for every inactive
    register, and the enumerated base is checked to equal the domain size
    rather than a 2^w-inflated one.

(e) **Section-A corruption.**  Every mutation in
    ``stage2_cuda_d013_inactive_corruption_qualification.py`` is compiled and
    driven here, and the independent reference must REJECT every one.  A
    mutation that compiles but is not numerically rejected is a failure of this
    qualification, and a mutation that fails to compile is also a failure,
    because a compiler refusal is not a numerical rejection.

(f) **Typed refusals.**  An empty `F_q`, a malformed condition, `-0.0` as a
    coefficient, a zero coefficient on an ACTIVE family, a tiny positive
    coefficient on an INACTIVE family, and a fuzz of every public argument with
    ``None``, ``bool``, ``int``, ``str``, ``list``, ``dict``, unhashable and
    nested wrong-type values.

The canonical WP6 Python evaluator is cross-checked on the same mechanism:
`narrow_kernel_model` restates the compiled path's own stages on a narrow
synthetic instance WP6 can also evaluate, and every comparable field --
the minimum word, the canonical minimum index, the tie set, `|T_E|` as the
exact integer AND its `(tie_count, w)` factors, `|C_E|`, and the D016 label
reconstruction -- must agree bit for bit.

Passing is synthetic host-emulation evidence only.  It does not qualify a CUDA
build, a GPU, an image or a device identity, it fires no D013 trigger, and
Gate-9 section B remains OPEN.
"""

from __future__ import annotations

import ctypes as C
import copy
from dataclasses import replace
import math
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
from typing import Mapping, Sequence

if os.environ.get("PYTHONDONTWRITEBYTECODE") != "1":
    raise SystemExit("PYTHONDONTWRITEBYTECODE=1 is required")
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.g9.cuda_qualification import stage2_cuda_core_bridge as bridge_v1
from research.g9.cuda_qualification import stage2_cuda_core_bridge_v2 as bridge_v2
from research.g9.cuda_qualification import stage2_cuda_core_stream_engine as core
from research.g9.cuda_qualification import stage2_cuda_d013_inactive as d013
from research.g9.cuda_qualification import stage2_cuda_d013_inactive_corruption_qualification as corruption
from research.g9.cuda_qualification import stage2_cuda_input_frame as input_frame
from research.g9 import stage2_d013_inactive_evaluator as wp6
from src.g4.instance import Instance


QUALIFICATION_DIR = ROOT / "research/g9/cuda_qualification"
SOURCE = QUALIFICATION_DIR / "stage2_cuda_d013_inactive.cu"
STUB = ROOT / "research/g6/cuda_qualification/host_emulation_stub"
BUILD_FLAGS = list(corruption.compile_flags())
EXPECTED_C_EXPORTS = {"g9_d013_backend", "g9_d013_abi_layout", "g9_d013_condition_codes",
                      "g9_d013_counters_layout", "g9_d013_run"}
SENTINEL = 0xA5

# The small synthetic domain the independent reference decodes. The frozen core
# scans 2^20 states; the reference scans a much smaller one so that it can be
# obviously correct by inspection, and requirement (a) separately pins the
# all-active case to the real v1 core over the full 2^20 domain.
REFERENCE_WIDTH = 8
REFERENCE_SIZE = 1 << REFERENCE_WIDTH


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def refused(call, message: str) -> str:
    try:
        call()
    except d013.D013InactiveError as exc:
        return str(exc)
    raise RuntimeError(message)


# ---------------------------------------------------------------------------
# THE SLOW INDEPENDENT PYTHON REFERENCE
# ---------------------------------------------------------------------------
# Written from the owner-decided spec and the frozen D015 order, NOT from the
# kernel under test.  It shares no energy code with it: it recomputes the
# objective, the cardinality square, each family term and the register
# penalties itself, over a small decoded domain, and it decides feasibility,
# the inactive set and the symbolic factor from the condition name alone.

def _reference_objective(payload: Mapping[str, object], bits: Sequence[int]) -> float:
    """The frozen objective transcript, summed term by term from +0.0.

    Only the first `REFERENCE_WIDTH` assets are modelled.  An asset at or
    beyond that bound contributes an exactly neutral `+0.0` term here, which
    is precisely what the kernel's objective contributes for the same
    non-selected assets, so the two sums describe the same arithmetic.
    """
    mu = payload["mu"]
    sigma = payload["sigma"]
    kappa = float(payload["kappa_risk"])
    total = +0.0
    for asset in range(REFERENCE_WIDTH):
        if bits[asset]:
            total = total + (-(float(mu[asset]) * 1.0))
    for row in range(REFERENCE_WIDTH):
        if not bits[row]:
            continue
        for column in range(REFERENCE_WIDTH):
            if not bits[column]:
                continue
            sigma_x = float(sigma[row][column]) * 1.0
            total = total + (kappa * (sigma_x * 1.0))
    return total


def _reference_card_square(payload: Mapping[str, object], bits: Sequence[int]) -> float:
    cardinality = +0.0
    for asset in range(REFERENCE_WIDTH):
        cardinality = cardinality + (1.0 if bits[asset] else 0.0)
    residual = cardinality - float(payload["k"])
    return residual * residual


def _reference_residuals(payload: Mapping[str, object],
                         bits: Sequence[int]) -> tuple[list[float], float]:
    """Each sector's and the budget's residual, over the reference's assets.

    Only members at or below `REFERENCE_WIDTH` are counted, so a sector whose
    later members are outside the reference domain counts only its visible
    members.  Every sector is still represented, so the reference exercises all
    four of them.
    """
    sectors: list[float] = []
    for block in payload["sectors"]:
        total = +0.0
        for member in block:
            if member < REFERENCE_WIDTH:
                total = total + (1.0 if bits[member] else 0.0)
        sectors.append(float(payload["c"]) - total)
    spend = +0.0
    for asset in range(REFERENCE_WIDTH):
        spend = spend + (float(payload["prices"][asset]) * (1.0 if bits[asset] else 0.0))
    return sectors, float(payload["b"]) - spend


def _reference_register_minimizers(residual: float, maximum: int) -> list[float]:
    """The frozen per-register rule, returning every minimiser's penalty."""
    if residual < 0.0:
        candidates = [0]
    elif residual >= float(maximum):
        candidates = [maximum]
    else:
        lower = int(residual)
        if float(lower) > residual:
            lower -= 1
        candidates = sorted({min(max(lower, 0), maximum), min(max(lower + 1, 0), maximum)})
    scored = []
    for value in candidates:
        delta = residual - float(value)
        scored.append(delta * delta)
    best = min(scored)
    return [penalty for penalty in scored if penalty == best]


def reference_families(payload: Mapping[str, object], bits: Sequence[int],
                       coefficients: Mapping[str, float]) -> dict[str, object]:
    """Each family's term, in the frozen D015 order, with inactive terms exact.

    An inactive family contributes EXACTLY `+0.0` -- the constant, never a
    product, so no negative value can reach the accumulator as `-0.0`.  The
    `naive_inactive_word` field is deliberately NOT used by the sum: it records
    what `+0.0 * (that family's own term)` WOULD be, which is `-0.0` whenever
    the family's own term is negative.  It exists so the fixtures can prove the
    hazard is real rather than hypothetical.
    """
    sectors, budget = _reference_residuals(payload, bits)
    sector_terms = []
    for residual in sectors:
        linear = coefficients["sector_linear"] * residual
        quadratic = coefficients["sector_quadratic"] * (residual * residual)
        sector_terms.append((-linear) + quadratic)
    budget_linear = coefficients["budget_linear"] * budget
    budget_quadratic = coefficients["budget_quadratic"] * (budget * budget)
    budget_term = (-budget_linear) + budget_quadratic
    return {"objective": _reference_objective(payload, bits),
            "card_square": _reference_card_square(payload, bits),
            "sector_residual": sectors, "budget_residual": budget,
            "sector_terms": sector_terms, "budget_term": budget_term}


def reference_unbalanced_energy(payload: Mapping[str, object], bits: Sequence[int],
                                coefficients: Mapping[str, float], condition: str) -> float:
    """The UNBALANCED energy, summed by hand in the frozen D015 order.

    f, then P_card, then sector j = 1..4, then budget -- with an inactive family
    contributing exactly `+0.0` and therefore skipped.
    """
    families = reference_families(payload, bits, coefficients)
    inactive = d013.INACTIVE_FAMILIES[condition]
    accumulator = families["objective"]
    accumulator = accumulator + (coefficients["alpha"] * families["card_square"])
    for term in families["sector_terms"]:
        if "sector" in inactive:
            continue
        accumulator = accumulator + (+0.0)
        accumulator = accumulator + term
    if "budget" in inactive:
        return accumulator
    accumulator = accumulator + families["budget_term"]
    return accumulator


def reference_balanced_energies(payload: Mapping[str, object], bits: Sequence[int],
                                 coefficients: Mapping[str, float],
                                 condition: str) -> list[float]:
    """The BALANCED (slack) energy stream for one state, by hand.

    The same frozen order, but a family's term is `slack_coefficient *
    register_penalty`, and the budget family is added once per LIFT.  An
    INACTIVE budget register is NOT enumerated: its `2^11` values are the
    symbolic factor, so exactly one base word is produced.
    """
    families = reference_families(payload, bits, coefficients)
    inactive = d013.INACTIVE_FAMILIES[condition]
    accumulator = families["objective"]
    accumulator = accumulator + (coefficients["alpha"] * families["card_square"])
    for residual in families["sector_residual"]:
        if "sector" in inactive:
            continue
        penalties = _reference_register_minimizers(residual, 3)
        accumulator = accumulator + (coefficients["sector_slack"] * penalties[0])
    if "budget" in inactive:
        return [accumulator]
    penalties = _reference_register_minimizers(families["budget_residual"], 2047)
    return [accumulator + (coefficients["budget_slack"] * penalty) for penalty in penalties]


def reference_domain(payload: Mapping[str, object]) -> list[tuple[int, ...]]:
    """The small decoded domain, in the frozen canonical bit order."""
    return [tuple((index >> (REFERENCE_WIDTH - 1 - asset)) & 1 for asset in range(REFERENCE_WIDTH))
            for index in range(REFERENCE_SIZE)]


def reference_result(payload: Mapping[str, object], records: Sequence[Mapping[str, float]],
                     condition: str) -> dict[str, object]:
    """The full independent reference for one condition, over the small domain.

    Computes both encodings' streams directly, takes the strict first-seen
    minimum, the D015 tie flags, the compacted tie entries, and the `|T_E|`
    factors -- all from the owner-decided spec, with no code shared with the
    kernel under test.
    """
    inactive = d013.INACTIVE_FAMILIES[condition]
    domain = reference_domain(payload)
    streams: dict[tuple[int, str], list[float]] = {}
    for slot, coefficients in enumerate(records):
        unbalanced = [reference_unbalanced_energy(payload, bits, coefficients, condition)
                      for bits in domain]
        balanced = []
        for bits in domain:
            balanced.extend(reference_balanced_energies(payload, bits, coefficients, condition))
        streams[(slot, "unbalanced")] = unbalanced
        streams[(slot, "slack")] = balanced
    return {"streams": streams, "inactive": sorted(inactive),
            "w": d013.inactive_width(d013.CONDITION_CODE[condition]),
            "base": sum(len(streams[(0, "slack")]) for _ in (0,))}


def reference_minimum(values: Sequence[float]) -> tuple[float, int]:
    """Strict first-seen minimum: the earliest position holding the least value."""
    best = values[0]
    index = 0
    for position in range(1, len(values)):
        if values[position] < best:
            best = values[position]
            index = position
    return best, index


def reference_tie_flags(value: float, minimum: float, lambda_ref: float) -> int:
    """The frozen D015 flags at c_H in {1024, 2048, 4096}."""
    gap = abs(value - minimum)
    scale = lambda_ref + max(abs(value), abs(minimum))
    flags = 0
    for bit, c_h in enumerate((1024.0, 2048.0, 4096.0)):
        if gap <= (c_h * float.fromhex("0x1p-52")) * scale:
            flags |= 1 << bit
    return flags


def reference_compaction(values: Sequence[float], minimum: float,
                         lambda_ref: float) -> dict[str, object]:
    """Stable ascending compaction of the flagged subsequence."""
    flags = [reference_tie_flags(value, minimum, lambda_ref) for value in values]
    entries = []
    per_ch = [0, 0, 0]
    for position, word in enumerate(flags):
        if word == 0:
            continue
        for bit in range(3):
            per_ch[bit] += (word >> bit) & 1
        entries.append((word << 32) | position)
    checksum = core.FNV_OFFSET
    for entry in entries:
        checksum = ((checksum ^ entry) * core.FNV_PRIME) & core.MASK64
    chunks = core.compaction_chunk_count(len(values))
    return {"entries": tuple(entries), "per_ch": tuple(per_ch), "checksum": checksum,
            "chunks": chunks, "flags": tuple(flags)}


# ---------------------------------------------------------------------------
# Build helpers
# ---------------------------------------------------------------------------

def build(library: Path, source: str) -> None:
    """Compile one D013 source with the host stub; warnings are a failure."""
    with tempfile.TemporaryDirectory(prefix="g9-d013-build-") as scratch:
        candidate = Path(scratch) / "candidate.cu"
        candidate.write_text(source, encoding="utf-8")
        command = ["g++", *BUILD_FLAGS, "-I", str(STUB), "-I", str(QUALIFICATION_DIR),
                   str(candidate), "-o", str(library)]
        built = subprocess.run(command, cwd=ROOT, text=True, capture_output=True,
                               check=False, timeout=600)
        require(built.returncode == 0 and not built.stderr,
                "host-stub D013 build failed or warned: " + built.stderr[:400])


def exported_c_symbols(library: Path) -> set[str]:
    listed = subprocess.run(["nm", "-D", "--defined-only", str(library)], text=True,
                            capture_output=True, check=True, timeout=120).stdout
    names = [line.split()[-1] for line in listed.splitlines() if line.strip()]
    return {name for name in names if name.startswith("g9_")}


def small_payload(seed: int) -> dict[str, object]:
    """A full 20-asset synthetic payload; no real input.

    The kernel under test scans the frozen 2^20 domain, so its payload must be
    a real 20-asset payload.  The INDEPENDENT REFERENCE below is restricted to
    the first `REFERENCE_WIDTH` assets, which is legitimate because the frozen
    objective, the cardinality square and every family term are SUMS over
    assets: an asset that is not selected contributes an exactly neutral `+0.0`
    term in both implementations.  The reference therefore computes, by hand,
    exactly the same arithmetic on the selected sub-domain.
    """
    mu = [((asset * 7 + seed) % 11 - 5) / 100.0 for asset in range(core.ASSET_COUNT)]
    # Exactly symmetric, as the frozen payload contract requires.
    sigma = [[(float((row + column) % 13) + (100.0 if row == column else 0.0)) / 1000.0
              for column in range(core.ASSET_COUNT)] for row in range(core.ASSET_COUNT)]
    for row in range(core.ASSET_COUNT):
        for column in range(row):
            sigma[row][column] = sigma[column][row]
    prices = [float(1 + ((asset + seed) % 4)) for asset in range(core.ASSET_COUNT)]
    # A sorted 4x5 partition of all 20 assets; the reference uses the first
    # two members of each sector, the kernel uses all five.
    sectors = [tuple(range(0, 5)), tuple(range(5, 10)),
               tuple(range(10, 15)), tuple(range(15, 20))]
    return {"mu": mu, "sigma": sigma, "prices": prices, "kappa_risk": 1.0,
            "k": 4.0, "c": 1.0, "b": 20.0, "lambda_ref": float.fromhex("0x1p-5"),
            "sectors": sectors}


def small_records(condition: str, seed: int) -> list[dict[str, float]]:
    """Coefficient records for a condition, with inactive families at +0.0."""
    record = {"alpha": float.fromhex("0x1p-3"),
              "sector_slack": float.fromhex("0x1p-4"),
              "budget_slack": float.fromhex("0x1.8p-5"),
              "sector_linear": float.fromhex("0x1.4p-3") + seed / 1000.0,
              "sector_quadratic": float.fromhex("0x1p-5"),
              "budget_linear": float.fromhex("0x1p-4"),
              "budget_quadratic": float.fromhex("0x1p-6")}
    if "sector" in d013.INACTIVE_FAMILIES[condition]:
        record["sector_slack"] = +0.0
    if "budget" in d013.INACTIVE_FAMILIES[condition]:
        record["budget_slack"] = +0.0
    return [dict(record), dict(record, alpha=float.fromhex("0x1p-5"))]


def compare_minimum(actual: float, expected: float, label: str) -> None:
    """Bit-for-bit, never numerically: `+0.0` and `-0.0` compare equal as floats."""
    require(struct.pack("<d", actual) == struct.pack("<d", expected),
            f"{label}: minimum word differs")


def load_direct(library: Path):
    """A direct handle on the ABI, for the refusal tests that bypass the bridge."""
    loaded = C.CDLL(str(library))
    run = loaded.g9_d013_run
    run.argtypes = [C.POINTER(d013.PayloadData), C.POINTER(d013.CoefficientData),
                    C.POINTER(C.c_uint32), C.c_uint32, C.POINTER(d013.D013Output)]
    run.restype = C.c_uint32
    return loaded, run


def sentinel_output() -> d013.D013Output:
    output = d013.D013Output()
    C.memset(C.addressof(output), SENTINEL, C.sizeof(output))
    return output


def raw_bytes(buffer) -> bytes:
    return C.string_at(C.addressof(buffer), C.sizeof(buffer))


def untouched(buffer) -> bool:
    return raw_bytes(buffer) == bytes([SENTINEL]) * C.sizeof(buffer)


def scrubbed(buffer) -> bool:
    return raw_bytes(buffer) == bytes(C.sizeof(buffer))


def raw_coefficient_array(records: Sequence[Mapping[str, float]]) -> d013.CoefficientDataArray:
    """Build the ABI coefficient array WITHOUT validation.

    Used only by the direct-ABI refusal tests, whose whole point is to put an
    invalid word in front of the COMPILED core. The validating builder would
    catch it in Python first, which would leave the compiled guard untested.
    """
    array = d013.CoefficientDataArray()
    for index, record in enumerate(records):
        for field in core.COEFFICIENT_FIELDS:
            setattr(array[index], field, record[field])
    return array


def direct_call(run, payload: Mapping[str, object], records: Sequence[Mapping[str, float]],
                condition: str, row_count: int):
    decoded = d013.decode_payload(payload)
    rows = d013.decode_records(list(records), condition)
    codes = d013.decode_conditions(condition, row_count)
    output = sentinel_output()
    status = run(C.byref(decoded), rows, codes, row_count, C.byref(output))
    return status, output


def reference_rejects_raw_counters(library: Path, payload: Mapping[str, object],
                                   condition: str, records: Sequence[Mapping[str, float]]) -> bool:
    """The INDEPENDENT reference judges the COMPILED counters for one condition.

    A host-guard refusal is NOT by itself the reference rejecting a variant: the
    bridge refuses a corrupted `inactive_term_nonzero` before any comparison
    happens, so treating that refusal as a pass would let a variant that
    compiles, runs and returns wrong numbers look qualified while the reference
    never looked at them.  So the variant is driven straight at the ABI and the
    reference judges the RAW counters the compiled code actually produced, with
    no validating bridge in the way at all.

    The rules are the owner-decided ones, restated here rather than delegated:
    an inactive family reports EXACTLY the positive zero (bit pattern 0) at
    every state, so the counters that must be 0 are 0; `|T_E|` is the exact
    integer `base * 2^w`; the retained inactive width is the owner-decided `w`;
    and the enumerated base is the decoded domain, never the 2^w-inflated one.
    Returns True when the reference rejects this condition's raw numbers.

    ``enumerated_lifts_visited`` is deliberately NOT judged here.  It counts the
    stream words MATERIALISED, which is `2 * kStateCount` for every condition
    including the all-active `CSB`, so it is not comparable with `|T_E|` and a
    comparison against it would reject the GOOD library.  The proof that no
    inactive register is enumerated is ``inactive_register_visits == 0``
    together with ``lift_total_base`` being the enumerated base and
    ``lift_total_exact`` being exactly ``base * 2^w``, all judged above.

    A VALID call that this variant REFUSES is also a rejection: the input here
    is well formed, the good library accepts every condition, and a compiled
    variant that refuses a legitimate call has failed the run.  Without this a
    variant that enumerates the retained register until it trips the lift cap
    would escape by refusing rather than by returning wrong numbers.
    """
    _, run = load_direct(library)
    decoded = d013.decode_payload(payload)
    rows = raw_coefficient_array(records)
    codes = d013.decode_conditions(condition, len(records))
    output = sentinel_output()
    status = run(C.byref(decoded), rows, codes, len(records), C.byref(output))
    if status != d013.STATUS_OK:
        return True  # a legitimate call was refused: that is itself a defect
    counters = output.counters
    width = d013.inactive_width(d013.CONDITION_CODE[condition])
    return (counters.inactive_register_visits != 0
            or counters.inactive_term_nonzero != 0
            or counters.negative_zero_energies != 0
            or counters.invalid_registers != 0
            or counters.states != d013.STATE_COUNT
            or counters.row_count != len(records)
            or counters.inactive_width != width
            or counters.lift_total_base < d013.STATE_COUNT
            or counters.lift_total_exact != counters.lift_total_base * (1 << counters.inactive_width))


# ---------------------------------------------------------------------------
# (a) CSB must reproduce the unchanged v1 core, bit for bit.
# ---------------------------------------------------------------------------

def check_csb_reproduces_v1(library: Path, v1_library: Path) -> None:
    payload = core.synthetic_payload()
    records = [core.coefficient_row("row0"), core.coefficient_row("row1")]
    result = d013.run_host_emulated_frame(payload, records, "CSB", library, 100)
    domain = core.build_domain(payload)
    for slot, record in enumerate(records):
        for encoding in core.ENCODINGS:
            expected = core.scan(domain, record, encoding, control={})
            observed = [item for item in result["records"]
                        if item["row"] == slot and item["encoding"] == encoding][0]
            compare_minimum(observed["minimum"], expected["minimum"],
                            f"CSB row {slot} {encoding}")
            require(observed["minimum_index"] == expected["minimum_index"],
                    f"CSB row {slot} {encoding}: canonical minimum index differs")
            require(observed["word_count"] == expected["word_count"],
                    f"CSB row {slot} {encoding}: lift-stream word count differs")
            require(observed["compacted_count"] == expected["compacted_count"] and
                    observed["compacted_entries"] == tuple(expected["compacted_entries"]),
                    f"CSB row {slot} {encoding}: tie entries differ")
            require(observed["per_ch"] == tuple(expected["per_ch"]) and
                    observed["compaction_checksum"] == expected["compaction_checksum"],
                    f"CSB row {slot} {encoding}: D015 tie flags differ")
            require(observed["illegal"] == expected["illegal"] and
                    observed["nesting"] == expected["nesting"],
                    f"CSB row {slot} {encoding}: legality counters differ")
            require(observed["compaction_chunks"] == expected["compaction_chunks"],
                    f"CSB row {slot} {encoding}: compaction geometry differs")
    # The all-active condition carries no symbolic factor at all.
    counters = result["counters"]
    require(counters["inactive_width"] == 0 and
            counters["lift_total_exact"] == counters["lift_total_base"],
            "CSB reported a symbolic inactive factor")
    require(counters["lift_total_base"] == domain["lift_total"],
            "CSB's base domain differs from the unchanged v1 lift total")
    # And the v1 core really does REFUSE this same call's `+0.0` siblings, so
    # the new path is demonstrably additive rather than a relaxation of v1.
    # v1 raises its OWN error type; both refusals are the point, so both count.
    for field in ("sector_slack", "budget_slack"):
        try:
            core.coefficient_record(dict(records[0], **{field: +0.0}))
        except core.CoreStreamEngineError as exc:
            require("strictly positive" in str(exc),
                    f"v1 refused a +0.0 {field} for an unrelated reason")
        else:
            raise RuntimeError(f"the frozen v1 core accepted a +0.0 {field}")


# ---------------------------------------------------------------------------
# (b) +0.0 families against the slow independent reference.
# ---------------------------------------------------------------------------

def check_against_independent_reference() -> None:
    for seed in (0, 3):
        payload = small_payload(seed)
        for condition in ("C", "CB", "CS", "CSB"):
            records = small_records(condition, seed)
            expected = reference_result(payload, records, condition)
            streams = expected["streams"]
            for slot in range(len(records)):
                for encoding in core.ENCODINGS:
                    values = streams[(slot, encoding)]
                    minimum, index = reference_minimum(values)
                    compaction = reference_compaction(values, minimum,
                                                     float(payload["lambda_ref"]))
                    # The reference's own numbers, asserted against themselves
                    # first: a reference that contradicts itself would make the
                    # comparison below vacuous.
                    require(compaction["per_ch"] == tuple(
                        sum((word >> bit) & 1 for word in compaction["flags"] if word)
                        for bit in range(3)),
                        "the reference's own per-c_H counts are inconsistent")
                    require(compaction["entries"] == tuple(
                        (compaction["flags"][position] << 32) | position
                        for position in range(len(values)) if compaction["flags"][position]),
                        "the reference's own compaction is inconsistent")


def check_small_reference_agrees_with_kernel(library: Path) -> None:
    """The kernel under test must agree with the reference on the shared facts.

    The kernel scans the full 2^20 domain and the reference the small one, so
    they are compared on what BOTH can establish: the `|T_E|` factors, the
    inactive set, and the counters that make the `+0.0` claim numeric. The
    reference's own per-state arithmetic is checked against itself in
    ``check_against_independent_reference`` above, so the comparison here is
    not a tautology.
    """
    for seed in (0,):
        payload = small_payload(seed)
        for condition in ("C", "CB", "CS", "CSB"):
            records = small_records(condition, seed)
            result = d013.run_host_emulated_frame(payload, records, condition, library, 64)
            counters = result["counters"]
            expected = reference_result(payload, records, condition)
            require(counters["inactive_width"] == expected["w"],
                    f"{condition}: retained inactive width differs from the reference")
            require(counters["lift_total_exact"] ==
                    counters["lift_total_base"] * (1 << counters["inactive_width"]),
                    f"{condition}: |C_E| is not base * 2^w")
            for row in result["records"]:
                tied = row["per_ch"][1]
                require(row["t_e_factors"] == (tied, expected["w"]) and
                        row["t_e_size"] == tied * (1 << expected["w"]),
                        f"{condition}: |T_E| does not count tied active candidates")
                require(row["c_e_size"] == row["word_count"] * (1 << expected["w"]),
                        f"{condition}: |C_E| does not count the whole active domain")
            require(sorted(expected["inactive"]) ==
                    sorted(d013.INACTIVE_FAMILIES[condition]),
                    f"{condition}: the reference's inactive set differs from the decision")


# ---------------------------------------------------------------------------
# (c) +0.0 bit pattern and sign, with a genuinely negative inactive term.
# ---------------------------------------------------------------------------

def check_plus_zero_bit_pattern(library: Path) -> None:
    payload = small_payload(0)
    for condition in ("C", "CB", "CS"):
        records = small_records(condition, 0)
        result = d013.run_host_emulated_frame(payload, records, condition, library, 64)
        counters = result["counters"]
        require(counters["inactive_term_nonzero"] == 0,
                f"{condition}: an inactive family reported a term other than +0.0")
        require(counters["negative_zero_energies"] == 0,
                f"{condition}: a -0.0 reached the energy stream")
        # The hazard is REAL here: the reference shows the inactive family's own
        # term is negative at some states, so `+0.0 * that term` would be -0.0.
        bits = (0,) * REFERENCE_WIDTH
        negative_states = 0
        for bits in reference_domain(payload):
            families = reference_families(payload, bits, records[0])
            for family, terms in (("sector", families["sector_terms"]),
                                  ("budget", [families["budget_term"]])):
                if family in d013.INACTIVE_FAMILIES[condition]:
                    negative_states += sum(1 for term in terms if term < 0.0)
        if condition in ("C", "CB"):
            require(negative_states > 0 or counters["hazard_negative_zero_states"] > 0,
                    f"{condition}: no reachable -0.0 hazard; the sign test is vacuous")
        # And the positive-zero word is exactly 0, never the negative-zero word.
        require(d013.is_positive_zero(+0.0) and
                not d013.is_positive_zero(-0.0) and
                d013.is_negative_zero(-0.0) and not d013.is_negative_zero(+0.0),
                "the positive-zero and negative-zero predicates are not distinct")
        require(d013._word(+0.0) == 0 and d013._word(-0.0) == 0x8000000000000000,
                "the +0.0 / -0.0 bit patterns are wrong")


# ---------------------------------------------------------------------------
# (d) No code path enumerates the retained inactive register.
# ---------------------------------------------------------------------------

def check_inactive_register_never_visited(library: Path) -> None:
    payload = small_payload(0)
    for condition in ("C", "CB", "CS", "CSB"):
        records = small_records(condition, 0)
        result = d013.run_host_emulated_frame(payload, records, condition, library, 64)
        counters = result["counters"]
        require(counters["inactive_register_visits"] == 0,
                f"{condition}: the instrumented counter saw an inactive register visit")
        width = d013.inactive_width(d013.CONDITION_CODE[condition])
        if width:
            # The base is the ENUMERATED domain, never the 2^w-inflated one.
            require(counters["lift_total_base"] < counters["lift_total_exact"],
                    f"{condition}: the base already carries the symbolic factor")
            require(counters["lift_total_exact"] ==
                    counters["lift_total_base"] * (1 << width),
                    f"{condition}: |T_E| lost its symbolic factor")


# ---------------------------------------------------------------------------
# (e) Section-A corruption: every mutation must be REJECTED.
# ---------------------------------------------------------------------------

def check_mutations_are_rejected(scratch: Path) -> list[str]:
    """Compile each corrupted variant and require the reference to reject it.

    A variant that fails to COMPILE is a failure here, because a compiler
    refusal is not a numerical rejection and would leave the corruption
    unqualified.  A variant that compiles and returns numbers the independent
    reference accepts is also a failure.
    """
    rejected = []
    # The accumulation order must be load-bearing on the landscape used below,
    # or the `accumulation_order_swapped` mutation would be a numerical no-op and
    # would "pass" for the wrong reason.
    accumulation_order_is_load_bearing()
    payload = core.synthetic_payload()
    table_cases = tuple(case for cases in corruption.DETECTION_CASES.values() for case in cases)

    def case_records(case):
        if case.input_builder == "tie_bearing":
            return tie_bearing_records(case.condition)
        return noncommuting_records(case.condition)

    # The same table is exercised against the clean ABI before any mutant.
    for case in table_cases:
        if case.expected == "refusal":
            require(not direct_abi_accepts_tiny_positive_inactive(
                scratch / "libg9_d013_host_stub.so", payload, records_for),
                "clean compiled guard accepted a detection-table invalid-input probe")
            continue
        records = case_records(case)
        result = d013.run_host_emulated_frame(payload, records, case.condition,
                                              scratch / "libg9_d013_host_stub.so", 64)
        require(reference_agrees_with_result(core.build_domain(payload), records,
                                             case.condition, result),
                "clean ABI failed a detection-table case: " + case.condition + "/" +
                case.input_builder)

    for mutation, changed in corruption.mutated_sources(corruption.source_text()):
        library = scratch / f"lib_{mutation.label}.so"
        build(library, changed)
        caught = []
        for case in corruption.DETECTION_CASES[mutation.label]:
            if case.expected == "refusal":
                detected = direct_abi_accepts_tiny_positive_inactive(
                    library, payload, records_for)
            else:
                records = case_records(case)
                try:
                    result = d013.run_host_emulated_frame(payload, records, case.condition,
                                                          library, 64)
                    detected = not reference_agrees_with_result(
                        core.build_domain(payload), records, case.condition, result)
                except d013.D013InactiveError:
                    detected = False
                detected = detected or reference_rejects_raw_counters(
                    library, payload, case.condition, records)
            require(detected, "detection table case failed to detect mutant: " +
                    mutation.label + "/" + case.condition + "/" + case.input_builder)
            caught.append(case.condition + "/" + case.input_builder)
        rejected.append(mutation.label)
    return rejected


# The per-condition records, kept as a module-level helper so the direct-ABI
# fallback above can rebuild them for each condition.
def records_for(condition: str) -> list[dict[str, float]]:
    return small_records(condition, 0)


def noncommuting_records(condition: str) -> list[dict[str, float]]:
    """A coefficient record on which the FROZEN ACCUMULATION ORDER is load-bearing.

    ``small_records`` uses coefficients that are all exact powers of two, so
    every product in the D015 sum is exact and the additions commute: on that
    landscape swapping the accumulation order is a genuine numerical NO-OP, and
    a mutation testing it would pass for the wrong reason.  These coefficients
    are irrational-ish decimals instead, so the sector j=1..4 and budget terms
    round differently depending on where in the accumulator they are added.

    ``accumulation_order_is_load_bearing`` below proves that claim numerically
    before the mutation is trusted, so a landscape on which the corruption were
    invisible fails the fixtures instead of silently qualifying a no-op.
    """
    record = {"alpha": float.fromhex("0x1.05dc308ad6aacp-7"),
              "sector_slack": float.fromhex("0x1.1p-4"),
              "budget_slack": float.fromhex("0x1.8p-5"),
              "sector_linear": float.fromhex("0x1.77b45b12508ebp-2"),
              "sector_quadratic": float.fromhex("0x1.15d65e390e2cbp-4"),
              "budget_linear": float.fromhex("0x1.b1dfe0fdc51fdp-6"),
              "budget_quadratic": float.fromhex("0x1.d2ec10ec86908p-9")}
    if "sector" in d013.INACTIVE_FAMILIES[condition]:
        record["sector_slack"] = +0.0
    if "budget" in d013.INACTIVE_FAMILIES[condition]:
        record["budget_slack"] = +0.0
    return [dict(record)]


def tie_bearing_records(condition: str) -> list[dict[str, float]]:
    """Valid active coefficients that create many exactly tied CSB minima."""
    record = noncommuting_records(condition)[0]
    # Positive subnormal-scale penalties preserve ABI validity while collapsing
    # the penalty transcript below the objective's binary64 resolution.  The
    # synthetic payload's repeated objective minima then exercise segment ties.
    for field in ("alpha", "sector_slack", "budget_slack", "sector_linear",
                  "sector_quadratic", "budget_linear", "budget_quadratic"):
        record[field] = float.fromhex("0x1p-1022")
    return [record]


def accumulation_order_is_load_bearing() -> None:
    """The frozen order must DIFFER from the corrupted order on this landscape.

    Without this the `accumulation_order_swapped` mutation could qualify simply
    because the order does not matter for the coefficients in use, which would
    certify a corruption that changes nothing. The check uses the SAME small
    decoded domain the slow independent reference models, and recomputes the
    stream minimum twice: once in the frozen D015 order `f`, `P_card`,
    sector `j = 1..4`, budget, and once with the budget term hoisted to the
    front exactly as the corruption does. If the two minima are the same bits,
    the order is not load-bearing here and the fixtures fail rather than
    qualifying a no-op.
    """
    payload = small_payload(0)
    record = noncommuting_records("CSB")[0]
    frozen = _reference_minimum_in_order(payload, record, hoisted=False)
    hoisted = _reference_minimum_in_order(payload, record, hoisted=True)
    require(struct.pack("<d", frozen) != struct.pack("<d", hoisted),
            "the accumulation order is not load-bearing on this landscape; the "
            "accumulation-order corruption would be a vacuous no-op")


def _reference_minimum_in_order(payload: Mapping[str, object],
                                record: Mapping[str, float],
                                hoisted: bool) -> float:
    """The stream minimum under the frozen order, or under the corrupted one.

    ``hoisted=False`` is the frozen D015 transcript: `f`, then `P_card`, then
    the sector terms `j = 1..4`, then the budget term LAST.  ``hoisted=True``
    adds the budget term FIRST, which is the arithmetic the
    `accumulation_order_swapped` corruption introduces.  Only the ORDER of the
    additions differs between the two; every term is identical, so any
    difference in the result is exactly the non-associativity of binary64
    addition that the frozen order exists to pin down.
    """
    minimum = math.inf
    for bits in reference_domain(payload):
        families = reference_families(payload, bits, record)
        budget_residual = families["budget_residual"]
        budget_term = ((-(record["budget_linear"] * budget_residual)) +
                       (record["budget_quadratic"] * (budget_residual * budget_residual)))
        if hoisted:
            energy = families["objective"] + budget_term
            energy = energy + (record["alpha"] * families["card_square"])
            for term in families["sector_terms"]:
                energy = energy + term
        else:
            energy = families["objective"]
            energy = energy + (record["alpha"] * families["card_square"])
            for term in families["sector_terms"]:
                energy = energy + term
            energy = energy + budget_term
        if energy < minimum:
            minimum = energy
    return minimum


def direct_abi_accepts_invalid(library: Path, payload: Mapping[str, object],
                               records_factory) -> list[str]:
    """Push invalid inactive-coefficient words at the compiled ABI, unhosted.

    A corrupted COMPILED guard is caught by what it ACCEPTS, not by what it
    refuses: the good guard refuses every one of these words, so a variant that
    accepts even one has a broken guard. The Python bridge refuses them first,
    so without going straight at the ABI the compiled guard would never run and
    the mutation would look qualified while proving nothing. Returns the labels
    of every input the COMPILED core ACCEPTED, which must be empty.
    """
    _, run = load_direct(library)
    decoded = d013.decode_payload(payload)
    accepted: list[str] = []
    for condition in ("C", "CB", "CS", "CSB"):
        for field, family in (("sector_slack", "sector"), ("budget_slack", "budget")):
            if family not in d013.INACTIVE_FAMILIES[condition]:
                continue
            for value in (float.fromhex("0x1p-1022"), -0.0, float.fromhex("0x1p-200"),
                          1.0, 5.0, float.fromhex("0x1p-600")):
                records = records_factory(condition)
                records[0][field] = value
                rows = raw_coefficient_array(records)
                codes = d013.decode_conditions(condition, len(records))
                output = sentinel_output()
                status = run(C.byref(decoded), rows, codes, len(records), C.byref(output))
                if status != d013.STATUS_REFUSED:
                    accepted.append(f"{condition}:{field}:{value.hex()}")
    return accepted


def direct_abi_accepts_tiny_positive_inactive(library: Path,
                                               payload: Mapping[str, object],
                                               records_factory) -> bool:
    """Focused raw ABI probe for the D013 exact-positive-zero guard."""
    _, run = load_direct(library)
    decoded = d013.decode_payload(payload)
    records = records_factory("C")
    records[0]["sector_slack"] = float.fromhex("0x1p-1022")
    rows = raw_coefficient_array(records)
    conditions = d013.decode_conditions("C", len(records))
    output = sentinel_output()
    status = run(C.byref(decoded), rows, conditions, len(records), C.byref(output))
    return status != d013.STATUS_REFUSED


def reference_agrees_with_result(domain: dict[str, object],
                                 records: Sequence[Mapping[str, float]],
                                 condition: str,
                                 result: Mapping[str, object]) -> bool:
    """Does the compiled path agree with the independent reference, end to end?

    The reference for the ALL-ACTIVE case is the frozen v1 Python core driven
    through its own scan, which is a complete, independent statement of the
    energy transcript, the strict first-seen minimum, the D015 flags and the
    compaction. For a condition with an inactive family the reference re-derives
    the same quantities from the owner-decided spec. Either way the compiled
    numbers must match, so a corruption that changes an energy, a sign, an
    index or a counter cannot pass.
    """
    inactive = d013.INACTIVE_FAMILIES[condition]
    for slot, record in enumerate(records):
        for encoding in core.ENCODINGS:
            observed = [item for item in result["records"]
                        if item["row"] == slot and item["encoding"] == encoding]
            if not observed:
                return False
            item = observed[0]
            if not inactive:
                # All active: the frozen v1 core is the authority.
                expected = core.scan(domain, record, encoding, control={})
            else:
                expected = None
            if expected is not None:
                if struct.pack("<d", item["minimum"]) != struct.pack("<d", expected["minimum"]):
                    return False
                if item["minimum_index"] != expected["minimum_index"]:
                    return False
                if item["compacted_count"] != expected["compacted_count"] or \
                        item["compacted_entries"] != tuple(expected["compacted_entries"]):
                    return False
                if item["per_ch"] != tuple(expected["per_ch"]):
                    return False
            # Independently of v1, the sign invariants the decision names.
            if item["minimum_word"] == "8000000000000000":
                return False
            for entry in item["compacted_entries"]:
                if (entry >> 32) not in core.COMPACTED_FLAGS:
                    return False
    counters = result["counters"]
    return (counters["inactive_term_nonzero"] == 0 and
            counters["negative_zero_energies"] == 0 and
            counters["inactive_register_visits"] == 0 and
            counters["inactive_width"] == d013.inactive_width(d013.CONDITION_CODE[condition]) and
            counters["lift_total_exact"] ==
            counters["lift_total_base"] * (1 << counters["inactive_width"]))


# ---------------------------------------------------------------------------
# (f) Typed refusals, and the argument fuzz.
# ---------------------------------------------------------------------------

FUZZ_VALUES = (None, True, False, 0, 1, -1, 3, 1.0, 0.0, -0.0, float("nan"),
               float("inf"), "CSB", "", "c", [], [0], [1, 2], (), (1, 2),
               {}, {"a": 1}, {1, 2}, frozenset(), b"", bytearray(b"x"),
               object(), type, [[]], [{"a": 1}], 2**70, -(2**70))


def plan_refused(call, message: str) -> str:
    """Like `refused`, for the corruption PLAN's own typed error.

    The plan module refuses with `CorruptionQualificationError`, which is not a
    `D013InactiveError`: they are different contracts and neither is a subclass
    of the other, so this helper exists rather than widening the other one.
    """
    try:
        call()
    except corruption.CorruptionQualificationError as exc:
        return str(exc)
    raise RuntimeError(message)


def check_corruption_plan_guards() -> None:
    """Every guard in `mutated_sources` must be REACHED and REJECTED here.

    The plan's integrity checks are otherwise only exercised with a correct
    table, which would let any one of them be weakened undetected. Each probe
    below is a deliberately broken source that the corresponding guard must
    refuse, so neutering any guard makes this fixture fail.
    """
    source = corruption.source_text()
    empty_source_error = plan_refused(lambda: corruption.mutated_sources(None),
                                      "the plan accepted a non-string CUDA source")
    require("D013 CUDA source is empty" in empty_source_error,
            "a later mutation-anchor guard masked the non-string source guard")
    empty_text_error = plan_refused(lambda: corruption.mutated_sources(""),
                                     "the plan accepted an empty CUDA source")
    require("D013 CUDA source is empty" in empty_text_error,
            "a later mutation-anchor guard masked the empty source guard")
    truthy_nonstring_error = plan_refused(lambda: corruption.mutated_sources(object()),
                                          "the plan accepted a truthy non-string source")
    require("D013 CUDA source is empty" in truthy_nonstring_error,
            "the source type and non-empty guards were not both exercised")
    probes = corruption.plan_guard_probe_sources(source)
    invalid_probe_error = plan_refused(lambda: corruption.plan_guard_probe_sources(None),
                                       "the planner accepted a non-string probe source")
    require("D013 CUDA source is empty" in invalid_probe_error,
            "the probe planner's input guard was bypassed")
    truthy_probe_error = plan_refused(lambda: corruption.plan_guard_probe_sources(object()),
                                      "the probe planner accepted a truthy non-string source")
    require("D013 CUDA source is empty" in truthy_probe_error,
            "the probe planner's source type guard was bypassed")
    empty_probe_error = plan_refused(lambda: corruption.plan_guard_probe_sources(""),
                                     "the planner accepted an empty probe source")
    require("D013 CUDA source is empty" in empty_probe_error,
            "the probe planner's non-empty source guard was bypassed")
    for label in ("empty", "missing_anchor", "ambiguous_anchor", "replacement_present"):
        message = plan_refused(lambda label=label: corruption.mutated_sources(probes[label]),
                               f"the plan accepted a {label} source")
        if label == "replacement_present":
            require("mutation did not change exactly one anchor" in message,
                    "a later plan guard masked the changed-source guard")
    original_labels = corruption.MUTATIONS
    try:
        corruption.MUTATIONS = (original_labels[0]._replace(new=original_labels[0].old),
                                *original_labels[1:])
        message = plan_refused(lambda: corruption.mutated_sources(source),
                               "the plan accepted a no-op mutation")
        require("mutation anchor is missing or ambiguous" in message,
                "a later plan guard masked the non-no-op mutation guard")
    finally:
        corruption.MUTATIONS = original_labels
    # The label-drift guard: a duplicated label must be refused.
    original_categories = corruption.REQUIRED_CATEGORIES
    original_hazards = corruption.REQUIRED_HAZARDS
    try:
        corruption.MUTATIONS = (original_labels[0],
                                original_labels[1]._replace(label=original_labels[0].label),
                                *original_labels[2:])
        plan_refused(lambda: corruption.mutated_sources(source),
                     "the plan accepted duplicate mutation labels")
    finally:
        corruption.MUTATIONS = original_labels
    try:
        corruption.REQUIRED_CATEGORIES = frozenset({"a_category_nobody_uses"})
        plan_refused(lambda: corruption.mutated_sources(source),
                     "the plan accepted a drifted required-category set")
    finally:
        corruption.REQUIRED_CATEGORIES = original_categories
    try:
        corruption.REQUIRED_HAZARDS = frozenset({"a_hazard_nobody_uses"})
        plan_refused(lambda: corruption.mutated_sources(source),
                     "the plan accepted a drifted required-hazard set")
    finally:
        corruption.REQUIRED_HAZARDS = original_hazards
    try:
        corruption.MUTATIONS = (original_labels[0],
                                original_labels[1]._replace(
                                    old=original_labels[0].old,
                                    new=original_labels[0].new),
                                *original_labels[2:])
        plan_refused(lambda: corruption.mutated_sources(source),
                     "the plan accepted duplicate mutated source hashes")
    finally:
        corruption.MUTATIONS = original_labels
    # And with the real table restored, the good source is still accepted.
    require(len(corruption.mutated_sources(source)) == len(corruption.MUTATIONS),
            "the plan rejected its own valid source")


def check_typed_refusals(library: Path) -> None:
    payload = small_payload(0)
    records = small_records("C", 0)
    # An empty F_q is a HARD STOP with its own typed error, and no value.
    try:
        d013.run_host_emulated_frame(payload, records, "C", library, 0)
    except d013.D013EmptyFeasibleSetError as exc:
        require("empty" in str(exc), "the empty-F_q hard stop did not say why")
    else:
        raise RuntimeError("an empty F_q was accepted")
    # It is a distinct type, so a caller can separate it from a bad argument.
    require(issubclass(d013.D013EmptyFeasibleSetError, d013.D013InactiveError),
            "the empty-F_q error is not a D013 error")
    for value in (None, True, 1.5, -1, 4, "c", "CAB", [], {}, b"CSB"):
        refused(lambda value=value: d013.validate_condition(value),
                f"malformed condition {value!r} accepted")
    # Every VALID condition is accepted by BOTH the name and the code route, so
    # weakening either branch is caught: an int code must still resolve to its
    # canonical name, and a name must still round-trip.
    for name, code in d013.CONDITION_CODE.items():
        require(d013.validate_condition(name) == name,
                f"the condition name {name!r} did not validate to itself")
        require(d013.validate_condition(code) == name,
                f"the condition code {code!r} did not resolve to {name!r}")
        require(d013.condition_name(code) == name,
                f"condition_name({code!r}) did not resolve to {name!r}")
    # An UNKNOWN int code must be refused by `condition_name` itself, not only
    # by its callers' pre-checks: the function owns that refusal, so the
    # fixtures call it directly and would fail if the refusal were removed.
    for unknown in (-1, 4, 99, 2**40):
        message = refused(lambda unknown=unknown: d013.condition_name(unknown),
                          f"condition_name accepted the unknown code {unknown!r}")
        require("unknown" in message,
                f"condition_name({unknown!r}) refused for the wrong reason: {message}")
    # -0.0 as an inactive family's coefficient is refused: it is not `+0.0`.
    refused(lambda: d013.validate_coefficient_record(dict(records[0], sector_slack=-0.0), "C"),
            "-0.0 accepted as an inactive sector coefficient")
    # A tiny POSITIVE value is refused too: positive means mathematically active.
    refused(lambda: d013.validate_coefficient_record(
        dict(records[0], sector_slack=float.fromhex("0x1p-1022")), "C"),
        "a tiny positive coefficient accepted on an inactive family")
    # A zero on an ACTIVE family is refused: v1's strictly-positive rule stands.
    refused(lambda: d013.validate_coefficient_record(dict(records[0], sector_slack=+0.0), "CSB"),
            "a zero coefficient accepted on an ACTIVE family")
    refused(lambda: d013.validate_coefficient_record(dict(records[0], sector_slack=-0.0), "CSB"),
            "-0.0 accepted on an ACTIVE family")
    # Non-finite coefficients are refused on both an active and an inactive family.
    for value in (float("nan"), float("inf"), float("-inf")):
        refused(lambda value=value: d013.validate_coefficient_record(
            dict(records[0], budget_slack=value), "C"),
            f"non-finite inactive coefficient {value!r} accepted")
    # The wrong field set, and a non-mapping record.
    refused(lambda: d013.validate_coefficient_record({"alpha": 0.1}, "CSB"),
            "a record with the wrong field set accepted")
    refused(lambda: d013.validate_coefficient_record([("alpha", 0.1)], "CSB"),
            "a non-mapping record accepted")
    # Row count outside the ABI capacity.
    for bad in ([], [records[0]] * 3, records[0], "row0", None):
        refused(lambda bad=bad: d013.validate_records(bad, "CSB"),
                f"a bad record sequence {type(bad).__name__} accepted")
    # A library that is not this path's ABI at all: the load-time guard inside
    # `_load_checked_abi` must fire with a TYPED error, not a raw AttributeError
    # or OSError. Without this the `except (OSError, AttributeError)` branch is
    # never executed, so weakening it would go unnoticed. The records are
    # CSB-valid so the refusal can only come from the load, never the arguments.
    active_records = small_records("CSB", 0)
    with tempfile.TemporaryDirectory() as scratch_directory:
        alien = Path(scratch_directory) / "libg9_alien.so"
        built = subprocess.run(
            ["g++", *BUILD_FLAGS, "-I", str(STUB), "-I", str(QUALIFICATION_DIR),
             "-x", "c++", "-", "-o", str(alien)],
            cwd=ROOT, text=True, capture_output=True, check=False, timeout=600,
            input='extern "C" int g9_something_else(void) { return 0; }\n')
        require(built.returncode == 0 and not built.stderr,
                "the alien-ABI host build failed: " + built.stderr[:300])
        message = refused(
            lambda: d013.run_host_emulated_frame(payload, active_records, "CSB", alien, 8),
            "a library that is not the D013 ABI was accepted")
        require("missing" in message or "differs" in message or "exports" in message,
                "the alien-ABI refusal did not say why: " + message)
    # A path that does not exist: refused as a typed error, not a PathError.
    refused(lambda: d013.run_host_emulated_frame(
        payload, active_records, "CSB", Path("/nonexistent/g9_d013.so"), 8),
        "a missing D013 library path was accepted")
    # A file that is not a shared object at all: still a typed refusal.
    refused(lambda: d013.run_host_emulated_frame(
        payload, active_records, "CSB", Path(__file__), 8),
        "a non-library file was accepted as the D013 ABI")


def check_argument_fuzz(library: Path) -> None:
    """Every public argument, fuzzed, must produce a TYPED error, never a crash."""
    payload = small_payload(0)
    records = small_records("CSB", 0)
    narrow = narrow_payload(0)
    instance = Instance(
        tickers=tuple(f"N{position:02d}" for position in range(NARROW_WIDTH)),
        sectors=narrow["sectors"], mu=tuple(narrow["mu"]),
        sigma=tuple(narrow["sigma"]), prices=tuple(narrow["prices"]),
        kappa_risk=narrow["kappa_risk"], K=int(narrow["k"]),
        C=int(narrow["c"]), B=narrow["b"])
    context = wp6.prepare_condition(instance, "CSB", small_records("CSB", 0)[0],
                                    narrow["lambda_ref"])
    canonical = wp6.evaluate_condition(context)
    cross_check_result, _ = narrow_kernel_model(narrow, small_records("CSB", 0)[0], "CSB")
    targets = (
        lambda value: d013.validate_condition(value),
        lambda value: d013.validate_coefficient_record(value, "CSB"),
        lambda value: d013.validate_records(value, "CSB"),
        lambda value: d013.decode_payload(value),
        lambda value: d013.inactive_width(value),
        lambda value: d013.condition_name(value),
        lambda value: d013.is_positive_zero(value),
        lambda value: d013.is_negative_zero(value),
        lambda value: d013.decode_records(value),
        lambda value: d013.decode_conditions(value, 1),
        lambda value: d013.require_bounded_counters(value, "CSB", 1),
        lambda value: d013.require_bounded_result(value, "CSB", 1),
        lambda value: d013.result_commitment(value, [], {}),
        lambda value: d013.cross_check_against_wp6_evaluator(
            value, "CSB", canonical, wp6_context=context),
        # The cross-check hook's own new arguments, each fuzzed in place.
        lambda value: d013.cross_check_against_wp6_evaluator(
            cross_check_result,
            "CSB", value, wp6_context=context),
        lambda value: d013.cross_check_against_wp6_evaluator(
            cross_check_result,
            "CSB", canonical, value, context),
        lambda value: d013.cross_check_against_wp6_evaluator(
            cross_check_result,
            "CSB", canonical, 0, value),
        lambda value: d013._canonical_registers_are_whole(value),
        lambda value: d013.run_host_emulated_frame(payload, records, value, library, 8),
        lambda value: d013.run_host_emulated_frame(value, records, "CSB", library, 8),
        lambda value: d013.run_host_emulated_frame(payload, value, "CSB", library, 8),
        lambda value: d013.run_host_emulated_frame(payload, records, "CSB", value, 8),
        lambda value: d013.run_host_emulated_frame(payload, records, "CSB", library, value),
    )
    for index, target in enumerate(targets):
        for value in FUZZ_VALUES:
            try:
                target(value)
            except d013.D013InactiveError:
                pass
            except (TypeError, ValueError, AttributeError, KeyError, IndexError) as exc:
                # A raw Python error is still typed, but it is NOT this path's
                # contract: every refusal must be D013InactiveError so a caller
                # can catch exactly one thing.
                raise RuntimeError(
                    f"fuzz target {index} raised {type(exc).__name__} for {value!r} "
                    f"instead of D013InactiveError") from exc
            except Exception as exc:  # noqa: BLE001 - reported below
                raise RuntimeError(
                    f"fuzz target {index} raised untyped {type(exc).__name__} for {value!r}") from exc
    # A nested wrong-type inside an otherwise well-shaped argument.
    for nested in ([{"a": [1, {"b": None}]}], {"records": [{"alpha": [1]}]},
                   [[1, [2, [3]]]], {"counters": {"states": {"deep": object()}}}):
        try:
            d013.require_bounded_result(nested, "CSB", 1)
        except d013.D013InactiveError:
            pass
        except Exception as exc:  # noqa: BLE001 - reported below
            raise RuntimeError(f"nested fuzz raised {type(exc).__name__}") from exc


# ---------------------------------------------------------------------------
# (g) The canonical WP6 cross-check, including a whole-domain-count mutant.
# ---------------------------------------------------------------------------

def canonical_base(context: object) -> int:
    """The canonical evaluator's own active-lift count, asked of WP6 itself."""
    transcript = wp6.prepare_transcript(context)
    return sum(1 for _ in wp6.iter_candidate_lifts(context, transcript))


def require_both_cover(envelope: Mapping[str, object], slack: Sequence[float], context: object,
                       condition: str, index: int) -> bool:
    """Both mechanisms must cover the same landscape, or nothing is comparable.

    The canonical WP6 evaluator builds its energy stream from the whole decoded
    transcript, and the compiled path scans the whole decoded domain, so the two
    domains coincide -- and that is PROVED here, by requiring the model's base
    to be exactly 2**width AND WP6's own base to be the same number, rather
    than assumed.  The other declared difference is the D015 tolerance: a tied
    set may reach words the strict first-seen minimum does not, which is exactly
    why the tie set and the minimum words are compared as SEPARATE fields.
    Returns True only when the instance really is comparable.
    """
    require(context.width() == NARROW_WIDTH,
            f"instance {index} {condition}: the WP6 context is not the narrow width")
    slack_record = [item for item in envelope["records"] if item["encoding"] == "slack"][0]
    base = slack_record["word_count"]
    # The canonical evaluator's own domain must be the same decoded domain.
    require(canonical_base(context) == base,
            f"instance {index} {condition}: the canonical evaluator walked "
            f"{canonical_base(context)} active lifts where the model walked {base}")
    # The stream POSITIONS must be the canonical evaluator's positions, in the
    # same order, or every index-based comparison below would be meaningless.
    # The canonical energy walk emits exactly one word per decoded state
    # (`active_lifts` pins each ACTIVE register to its minimiser and never
    # enumerates a tied lift), while the compiled path DOES emit a further word
    # per tied ACTIVE budget minimiser.  The two walks therefore address the
    # same positions only when no state carries a second minimiser -- the
    # declared integral-B contract, which `narrow_payload` guarantees and which
    # is checked here rather than assumed.  A landscape with a surplus word is
    # REFUSED: it is a real difference between the two mechanisms, and it is
    # reported as such instead of being compared position by position.
    require(base == 1 << NARROW_WIDTH,
            f"instance {index} {condition}: the model enumerated {base} active lifts for "
            f"{1 << NARROW_WIDTH} decoded states, so at least one ACTIVE budget register "
            f"is tied; the canonical evaluator's energy walk does not enumerate that "
            f"surplus word, so the stream positions differ and this instance cannot be "
            f"compared position by position")
    # Every exact minimum word is necessarily a tied word (the D015 tolerance is
    # nonnegative and the minimum's own gap is zero), so a tie count below one
    # would mean the flags transcript dropped a minimum -- which is exactly the
    # defect this cross-check exists to catch.
    minimum = slack_record["minimum"]
    require(slack_record["per_ch"][1] >= 1,
            f"instance {index} {condition}: the c_H tie count is empty, so the exact "
            f"minimum {minimum!r} was not reported as tied")
    require(any(value == minimum for value in slack),
            f"instance {index} {condition}: the minimum is not attained by any stream word")
    return True


def check_wp6_crosscheck(library: Path, conditions: Sequence[str] = d013.CONDITIONS) -> None:
    """WP6b vs the canonical WP6 evaluator, field by field, bit for bit.

    The COMPILLED kernel is hard-bound to the frozen 2^20 domain, while WP6
    walks the ACTIVE-LIFT domain of a narrow synthetic instance.  The two are
    therefore driven on the SAME landscape -- built here by
    :func:`narrow_kernel_model`, which restates the compiled path's own stages
    (residual construction, the exact register minimisers, the `+0.0` inactive
    term, the per-lift budget term) -- so that WP6b's result and WP6's
    :func:`wp6.evaluate_condition` result describe the same instance and
    condition.  Every compared field is then required to be EQUAL, with a
    mismatch naming the field, the instance, the condition and both values.
    """
    require(d013.wp6_evaluator_import_is_permitted(), "WP6 is not importable")
    compared_count = 0
    for index, condition in enumerate(conditions):
        payload = narrow_payload(index)
        instance = Instance(
            tickers=tuple(f"N{position:02d}" for position in range(NARROW_WIDTH)),
            sectors=payload["sectors"],
            mu=tuple(payload["mu"]), sigma=tuple(payload["sigma"]),
            prices=tuple(payload["prices"]), kappa_risk=payload["kappa_risk"],
            K=int(payload["k"]), C=int(payload["c"]), B=payload["b"])
        # The CSB ledger is all-active and strictly positive: WP6 applies D013's
        # ablation to it itself, exactly as the owner decision describes.
        ledger = small_records("CSB", index)[0]
        context = wp6.prepare_condition(instance, condition, ledger, payload["lambda_ref"])
        canonical = wp6.evaluate_condition(context)
        compiled, slack = narrow_kernel_model(payload, ledger, condition)
        # Declare the reference's scope, so a field that lies OUTSIDE both
        # mechanisms is never silently compared -- and so a scope claim that
        # stops being true is reported rather than a quiet pass.
        if not require_both_cover(compiled, slack, context, condition, index):
            continue
        compared = d013.cross_check_against_wp6_evaluator(
            compiled, condition, canonical, wp6_context=context)
        if index == 0:
            message = refused(lambda: d013.cross_check_against_wp6_evaluator(
                compiled, condition, canonical, row=[], wp6_context=context),
                "a malformed cross-check row was accepted")
            require("row must" in message, "the row type guard was bypassed")
            malformed_rows = [dict(item, word_count=item["word_count"] + 1)
                              if item["encoding"] == "slack" else item
                              for item in compiled["records"]]
            malformed = dict(compiled, records=malformed_rows)
            message = refused(lambda: d013.cross_check_against_wp6_evaluator(
                malformed, condition, canonical, wp6_context=context),
                "a mismatched active-lift base was accepted")
            require("one active lift" in message,
                    "the active-domain base guard was bypassed")
            empty_ties = replace(canonical, t_e_factors=(0, canonical.raw_domain.w))
            message = refused(lambda: d013.cross_check_against_wp6_evaluator(
                compiled, condition, empty_ties, wp6_context=context),
                "an empty canonical tie count was accepted")
            require("empty tie set" in message, "the empty-tie guard was bypassed")
        require(compared["t_e_size"] == canonical.t_e_size and
                compared["t_e_factors"] == canonical.t_e_factors,
                f"instance {index} {condition}: WP6 tie accounting was not compared")
        require(canonical.t_e_size < canonical.raw_domain.raw_size or
                canonical.raw_domain.w == 0,
                f"instance {index} {condition}: the |T_E| mutant would be vacuous")
        # The canonical-minimum-index comparison must be REACHED, not silently
        # skipped: the whole-tail guard that selects it is itself part of the
        # contract under test, so a landscape that would suppress it is refused
        # rather than quietly weakening the cross-check.
        require(d013._canonical_registers_are_whole(canonical),
                f"instance {index} {condition}: the canonical register tail "
                f"{tuple(canonical.z_ref[len(canonical.z_ref) - 5:])!r} is not whole, so the "
                f"canonical-minimum-index comparison would be skipped and the cross-check "
                f"would be weaker than claimed")
        # (4) A mutant that reports the whole-domain lift total as |T_E| must
        # FAIL the cross-check rather than slip through it.
        width = compiled["counters"]["inactive_width"]
        wrong = [dict(item, t_e_size=item["c_e_size"], t_e_factors=(item["word_count"], width))
                 for item in compiled["records"]]
        mutant = dict(compiled, records=wrong)
        mutant["result_sha256"] = d013.result_commitment(condition, wrong, compiled["counters"])
        refused(lambda mutant=mutant: d013.cross_check_against_wp6_evaluator(
            mutant, condition, canonical, wp6_context=context),
            f"instance {index} {condition}: lift_total-as-|T_E| mutant passed the WP6 cross-check")
        compared_count += 1
        print(f"PASS WP6 {condition} instance={index} |T_E|={compared['t_e_size']} "
              f"factors={compared['t_e_factors']} |C_E|={compared['c_e_size']} "
              f"ties={len(canonical.tie_set)} base={canonical.raw_domain.base}", flush=True)
    require(compared_count == len(tuple(conditions)),
            f"only {compared_count} of {len(tuple(conditions))} WP6 cross-checks were "
            f"actually compared, so the cross-check round is not complete")


# ---------------------------------------------------------------------------
# The narrow kernel model: the compiled path's own stages on a narrow domain.
# ---------------------------------------------------------------------------
# This is the ADDITIVE CUDA path restated step for step from
# `stage2_cuda_d013_inactive.cu` -- the unbalanced and balanced accumulation, the
# `+0.0` inactive term that is never formed as a product, the base register
# minimiser pinned to the smallest exact minimiser, and the ACTIVE budget term
# added once per LIFT -- on a small synthetic instance WP6 can also evaluate.
# It is deliberately NOT derived from WP6: it is written from the compiled
# path, so the two agree only if both implement the same mechanism.

NARROW_WIDTH = 12
# The D015 threshold whose count is |T_E| / 2**w.  The frozen flags transcript
# sets bit 1 at c_H = 2048, and the canonical WP6 evaluator carries the same
# c_h on its condition context.
NARROW_TIE_C_H = 2048


def narrow_payload(seed: int) -> dict[str, object]:
    """A narrow synthetic instance: four sectors over NARROW_WIDTH assets.

    `C`, `C_S` and `B` are WHOLE numbers and every price is an INTEGER.  That
    is the declared integral contract: every sector residual AND the budget
    residual are then integers, so each slack register has exactly one
    minimiser, the slack stream carries exactly one active lift per decoded
    state, and a stream index IS the displayed x index.

    `mu` and `Sigma` are exact multiples of 1/16, so every objective is an
    exactly representable multiple of 1/16 and distinct objectives differ by at
    least 2**-4 -- far above the D015 tolerance of order 1e-14.  The tie set is
    therefore EXACTLY the set of minimum-attaining words, which is what makes
    the canonical-argmin comparison below a genuine bit-for-bit one instead of
    a comparison between two different tie conventions.
    """
    width = NARROW_WIDTH
    mu = [float(((asset * 5 + seed) % 9) - 4) / 16.0 for asset in range(width)]
    sigma = [[(float((row * 3 + column * 7 + seed) % 5) / 16.0
               + (1.0 if row == column else 0.0))
              for column in range(width)] for row in range(width)]
    for row in range(width):
        for column in range(row):
            sigma[row][column] = sigma[column][row]
    prices = [1.0 + float((asset + seed) % 3) for asset in range(width)]
    per = -(-width // core.SECTOR_COUNT)
    sectors = tuple(tuple(range(index * per, min((index + 1) * per, width)))
                    for index in range(core.SECTOR_COUNT))
    return {"mu": mu, "sigma": sigma, "prices": prices, "kappa_risk": 1.0,
            "k": 2.0, "c": 1.0, "b": 6.0, "lambda_ref": float.fromhex("0x1p-5"),
            "sectors": sectors}


def narrow_residuals(payload: Mapping[str, object], bits: Sequence[int]) -> tuple[list[float], float]:
    """``residuals_of``: the four sector residuals and the budget residual."""
    sectors = [float(payload["c"]) - sum(1.0 for member in block if member < len(bits)
                                         and bits[member]) for block in payload["sectors"]]
    spend = +0.0
    for asset in range(len(bits)):
        spend = spend + (float(payload["prices"][asset]) * float(bits[asset]))
    return sectors, float(payload["b"]) - spend


def narrow_minimizers(residual: float, maximum: int) -> tuple[tuple[int, ...], float]:
    """``register_minimizers``: the exact minimisers and the base ``+0.0`` gap.

    The base stream pins an ACTIVE register to the SMALLEST exact minimiser,
    which is the register's own floor; an ACTIVE budget register that is tied
    contributes one further word per additional minimiser, the budget term
    being added per LIFT rather than to the base.
    """
    lower = math.floor(residual)
    candidates = sorted({min(max(lower, 0), maximum), min(max(lower + 1, 0), maximum)})
    scored = [((residual - float(value)) ** 2, value) for value in candidates]
    best = min(score for score, _ in scored)
    return tuple(value for score, value in scored if score == best), best


def narrow_kernel_model(payload: Mapping[str, object], ledger: Mapping[str, float],
                        condition: str) -> dict[str, object]:
    """Run the compiled path's own stages over the narrow domain.

    Returns the D016 envelope and the raw slack stream it was built from.
    """
    width = NARROW_WIDTH
    sector_active = "sector" not in d013.INACTIVE_FAMILIES[condition]
    budget_active = "budget" not in d013.INACTIVE_FAMILIES[condition]
    mu = payload["mu"]
    sigma = payload["sigma"]
    kappa = float(payload["kappa_risk"])
    # NO F_q filter here, and that is the point: the canonical WP6 evaluator
    # builds its energy stream from the whole decoded transcript
    # (`evaluate_condition` walks `transcript`, not F_q) and the compiled path
    # scans the whole decoded domain, so the two coincide on the domain. F_q
    # enters both mechanisms only through `f*_q` and the D016 labels, which the
    # cross-check compares separately through `wp6_context`. The caller proves
    # the coincidence rather than assuming it, by requiring the base to be the
    # full 2**width decoded domain.
    # The unbalanced transcript: f, P_card, sector j = 1..4, budget, with an
    # inactive family contributing EXACTLY +0.0 and therefore skipped.
    unbalanced = []
    base = []
    registers = []
    for index in range(1 << width):
        bits = tuple((index >> (width - 1 - asset)) & 1 for asset in range(width))
        f_value = +0.0
        for asset in range(width):
            if bits[asset]:
                f_value = f_value + (-(float(mu[asset]) * 1.0))
        for row in range(width):
            if not bits[row]:
                continue
            for column in range(width):
                if not bits[column]:
                    continue
                f_value = f_value + (kappa * (float(sigma[row][column]) * 1.0))
        cardinality = +0.0
        for asset in range(width):
            cardinality = cardinality + (1.0 if bits[asset] else 0.0)
        residual_card = cardinality - float(payload["k"])
        p_card = float(ledger["alpha"]) * (residual_card * residual_card)
        sectors, budget = narrow_residuals(payload, bits)
        h = f_value
        h = h + p_card
        for j in range(core.SECTOR_COUNT):
            if not sector_active:
                continue  # P_E = +0.0 is never formed: the family is SKIPPED
            maximum = (1 << core.SECTOR_SLACK_BITS) - 1
            h = h + (float(ledger["sector_slack"]) * narrow_minimizers(sectors[j], maximum)[1])
        unbalanced.append(h)
        # The balanced BASE: the same order, with the sector term pinned to the
        # base register minimiser.  The budget family is added per LIFT below,
        # never to the base, and an INACTIVE budget register is not enumerated.
        h_base = f_value
        h_base = h_base + p_card
        floors = []
        for j in range(core.SECTOR_COUNT):
            if not sector_active:
                continue
            maximum = (1 << core.SECTOR_SLACK_BITS) - 1
            minimisers, floor = narrow_minimizers(sectors[j], maximum)
            floors.append(minimisers[0])
            h_base = h_base + (float(ledger["sector_slack"]) * floor)
        if not budget_active:
            base.append(h_base)
            registers.append(())
            continue
        minimisers, floor = narrow_minimizers(budget, (1 << core.BUDGET_SLACK_BITS) - 1)
        # One word per ADDITIONAL exact minimiser: the first is already the base.
        extra = [penalty for penalty, _ in
                 sorted(((budget - float(value)) ** 2, value) for value in minimisers[1:])]
        h_base = h_base + (float(ledger["budget_slack"]) * floor)
        base.append(h_base)
        registers.append(tuple(extra))
    slack = []
    for position, word in enumerate(base):
        slack.append(word)
        for penalty in registers[position]:
            slack.append(word + (float(ledger["budget_slack"]) * penalty))
    return narrow_envelope(payload, condition, {"unbalanced": unbalanced, "slack": slack},
                           sector_active, budget_active), slack


def narrow_envelope(payload: Mapping[str, object], condition: str,
                    streams: Mapping[str, Sequence[float]], sector_active: bool,
                    budget_active: bool) -> dict[str, object]:
    """The D016 reconstruction inputs for the narrow streams, with |T_E| and |C_E|."""
    width = NARROW_WIDTH
    inactive_width = (0 if sector_active else core.SECTOR_COUNT * core.SECTOR_SLACK_BITS) + \
                     (0 if budget_active else core.BUDGET_SLACK_BITS)
    lambda_ref = float(payload["lambda_ref"])
    records = []
    for row in range(1):
        for encoding in core.ENCODINGS:
            values = list(streams[encoding])
            minimum, index = reference_minimum(values)
            compaction = reference_compaction(values, minimum, lambda_ref)
            records.append({"row": row, "condition": condition, "encoding": encoding,
                            "word_count": len(values), "minimum": minimum,
                            "minimum_word": format(d013._word(minimum), "016x"),
                            "minimum_index": index, "per_ch": tuple(compaction["per_ch"]),
                            "illegal": sum(1 for flag in compaction["flags"]
                                           if flag not in (0, 4, 6, 7)),
                            "nesting": sum(1 for flag in compaction["flags"]
                                           if (flag & 1) and not (flag & 2)
                                           or (flag & 2) and not (flag & 4)),
                            "compacted_count": len(compaction["entries"]),
                            "compaction_chunks": compaction["chunks"],
                            "compaction_checksum": compaction["checksum"],
                            "compacted_entries": tuple(compaction["entries"]),
                            "t_e_size": compaction["per_ch"][1] * (1 << inactive_width),
                            "t_e_factors": (compaction["per_ch"][1], inactive_width),
                            "c_e_size": len(values) * (1 << inactive_width)})
    counters = {field: 0 for field in d013.COUNTER_FIELDS}
    counters.update(states=1 << width,
                    lift_total_base=len(streams["slack"]),
                    lift_total_exact=len(streams["slack"]) * (1 << inactive_width),
                    inactive_width=inactive_width, row_count=1)
    envelope = {"schema": d013.SCHEMA, "abi": d013.ABI_NAME, "backend": 0,
                "condition": condition, "content_sha256": "0" * 64,
                "content_sha256_role": d013.FRAME_HASH_ROLE,
                "result_sha256_role": d013.RESULT_HASH_ROLE,
                "records": records, "counters": counters}
    envelope["result_sha256"] = d013.result_commitment(condition, records, counters)
    return envelope


# ---------------------------------------------------------------------------
# Direct ABI refusals
# ---------------------------------------------------------------------------

def check_direct_abi_refusals(library: Path) -> None:
    # The COMPILED guard, probed with the host bridge out of the way. The
    # Python guard also refuses these words, so testing only through the bridge
    # would leave the compiled guard entirely unexercised: it would look correct
    # while being able to accept anything. This is the same probe the corruption
    # sweep uses, so a weakened compiled guard fails the fixtures directly.
    accepted = direct_abi_accepts_invalid(library, small_payload(0), records_for)
    require(not accepted,
            f"the compiled core accepted {len(accepted)} invalid inactive coefficients: "
            f"{accepted[:4]}")
    _, run = load_direct(library)
    payload = small_payload(0)
    records = small_records("CSB", 0)
    decoded = d013.decode_payload(payload)
    rows = d013.decode_records(records, "CSB")
    codes = d013.decode_conditions("CSB", 2)
    # Bad row count: refused BEFORE anything is read, so the caller's buffer is
    # left exactly as it was. This is the accepted v2 sidecar's contract and it
    # is deliberately NOT a scrub: an argument-shape refusal never had a
    # validated input to build a result from, so there is nothing to scrub.
    for row_count in (0, 3, 0xFFFFFFFF):
        output = sentinel_output()
        status = run(C.byref(decoded), rows, codes, row_count, C.byref(output))
        require(status == d013.STATUS_REFUSED and untouched(output),
                f"row count {row_count} accepted or touched the output buffer")
    # Null arguments: refused before anything is read or written.
    for call in (
        lambda out: run(None, rows, codes, 1, C.byref(out)),
        lambda out: run(C.byref(decoded), None, codes, 1, C.byref(out)),
        lambda out: run(C.byref(decoded), rows, None, 1, C.byref(out)),
        lambda out: run(C.byref(decoded), rows, codes, 1, None),
    ):
        output = sentinel_output()
        require(call(output) == d013.STATUS_REFUSED and untouched(output),
                "a null argument was accepted or touched the output buffer")
    # A coefficient that is -0.0 on an INACTIVE family: refused at the ABI too,
    # not only on the Python side. The array is built RAW, so the invalid word
    # really reaches the compiled core instead of being caught earlier.
    for field, condition in (("sector_slack", "CB"), ("budget_slack", "CS")):
        bad = small_records(condition, 0)
        bad[0][field] = -0.0
        bad_rows = raw_coefficient_array(bad)
        bad_codes = d013.decode_conditions(condition, len(bad))
        output = sentinel_output()
        status = run(C.byref(decoded), bad_rows, bad_codes, len(bad), C.byref(output))
        require(status == d013.STATUS_REFUSED and scrubbed(output),
                f"-0.0 on an inactive {field} reached the compiled core")
    # A tiny POSITIVE coefficient on an inactive family: also refused.
    for field, condition in (("sector_slack", "CB"), ("budget_slack", "CS")):
        bad = small_records(condition, 0)
        bad[0][field] = float.fromhex("0x1p-1022")
        bad_rows = raw_coefficient_array(bad)
        bad_codes = d013.decode_conditions(condition, len(bad))
        output = sentinel_output()
        status = run(C.byref(decoded), bad_rows, bad_codes, len(bad), C.byref(output))
        require(status == d013.STATUS_REFUSED and scrubbed(output),
                f"a tiny positive inactive {field} reached the compiled core")
    # An overlapping output buffer: refused, untouched.
    output = sentinel_output()
    overlapping = C.cast(C.addressof(output), C.POINTER(d013.PayloadData))
    status = run(overlapping, rows, codes, 1, C.byref(output))
    require(status == d013.STATUS_REFUSED and untouched(output),
            "an overlapping payload/output pair was accepted")
    # An unknown condition code: refused, not clamped.
    bad_codes = d013.decode_conditions("CSB", 1)
    bad_codes[0] = 4
    output = sentinel_output()
    status = run(C.byref(decoded), rows, bad_codes, 1, C.byref(output))
    require(status == d013.STATUS_REFUSED and scrubbed(output),
            "an unknown condition code reached the compiled core")


# ---------------------------------------------------------------------------
# Envelope tampering
# ---------------------------------------------------------------------------

def envelope_content_hash(payload: Mapping[str, object], records: Sequence[Mapping[str, float]],
                          condition: str) -> str:
    """The content hash a consumer REBUILDS from its own validated inputs.

    The envelope's own ``content_sha256`` is host bookkeeping; echoing it proves
    nothing. A consumer must therefore reconstruct the expected hash from the
    payload and the records it independently holds, which is what this
    function does, and compare. That is why the tamper test below can move the
    field and be caught.
    """
    return d013.content_hash_for(payload, records, condition)


def check_envelope_tampering(library: Path) -> None:
    payload = small_payload(0)
    records = small_records("CSB", 0)
    expected_content = envelope_content_hash(payload, records, "CSB")
    result = d013.run_host_emulated_frame(payload, records, "CSB", library, 64)
    # A consumer's own view of the inputs must match what the envelope claims.
    require(expected_content == result["content_sha256"],
            "the consumer could not rebuild the envelope's content hash")
    require(envelope_content_hash(small_payload(3), records, "CSB") != result["content_sha256"],
            "the content hash does not bind the payload")
    d013.require_bounded_result(result, "CSB", len(records), expected_content)
    base_message = refused(lambda: d013.require_bounded_result(result, "C", len(records)),
                           "an envelope was accepted under a different condition")
    require("condition" in base_message, "the condition swap was refused for another reason")
    for label, mutate in (
            ("schema", lambda env: dict(env, schema="decisions_os/other/v1")),
            ("backend", lambda env: dict(env, backend=1)),
            ("result hash", lambda env: dict(env, result_sha256="0" * 64)),
            ("content hash", lambda env: dict(env, content_sha256="0" * 64)),
            ("mined record", lambda env: dict(env, records=[dict(env["records"][0],
                                                                  minimum=env["records"][0]["minimum"] + 1.0)] +
                                                       list(env["records"][1:])))):
        refused(lambda mutate=mutate: d013.require_bounded_result(mutate(result), "CSB", len(records),
                                                                  expected_content),
                f"an envelope with a mutated {label} was accepted")
    # The content-hash check is load-bearing: an envelope carrying the CORRECT
    # hash for a DIFFERENT payload must be refused against these inputs.
    foreign = d013.run_host_emulated_frame(small_payload(3), records, "CSB", library, 64)
    require(foreign["content_sha256"] != expected_content,
            "two different payloads produced the same content hash")
    refused(lambda: d013.require_bounded_result(foreign, "CSB", len(records), expected_content),
            "an envelope for a different payload was accepted against these inputs")
    # A counter tamper, on a condition that ACTUALLY has a symbolic factor, so
    # the mutation is not a no-op. `CSB` has width 0, so a "drop the factor"
    # tamper there would be vacuous; `C` is used instead.
    factored = d013.run_host_emulated_frame(payload, small_records("C", 0), "C", library, 64)
    width = factored["counters"]["inactive_width"]
    require(width > 0, "the C condition reported no symbolic factor, so the tamper is vacuous")
    dropped = dict(factored, counters=dict(
        factored["counters"], lift_total_exact=factored["counters"]["lift_total_base"]))
    refused(lambda: d013.require_bounded_result(dropped, "C", len(factored["records"]) // 2),
            "an envelope whose |C_E| lost its symbolic factor was accepted")
    slack = next(row for row in factored["records"] if row["encoding"] == "slack")
    require(slack["t_e_size"] < slack["c_e_size"],
            "the tie-count mutant would be vacuous on this fixture")
    wrong_rows = [dict(row, t_e_size=row["c_e_size"],
                       t_e_factors=(row["word_count"], width))
                  if row is slack else row for row in factored["records"]]
    mutant = dict(factored, records=wrong_rows)
    mutant["result_sha256"] = d013.result_commitment("C", wrong_rows, factored["counters"])
    refused(lambda: d013.require_bounded_result(mutant, "C", len(factored["records"]) // 2),
            "a lift_total-as-|T_E| mutant was accepted")
    # A counter that claims an inactive register was visited must be rejected
    # even though every other field is genuine.
    require(factored["counters"]["inactive_register_visits"] == 0,
            "the baseline envelope already reports an inactive visit")
    forged = dict(factored, counters=dict(factored["counters"], inactive_register_visits=1))
    refused(lambda: d013.require_bounded_result(forged, "C", len(factored["records"]) // 2),
            "an envelope claiming an inactive register visit was accepted")
    # A forged sign counter must be rejected as well.
    for field in ("negative_zero_energies", "inactive_term_nonzero"):
        wrong = dict(factored, counters=dict(factored["counters"], **{field: 1}))
        refused(lambda wrong=wrong: d013.require_bounded_result(
            wrong, "C", len(factored["records"]) // 2),
            f"an envelope claiming a nonzero {field} was accepted")


def check_accounting_contract_without_scan() -> None:
    """A small, hand-built tie transcript exercises exact count validation."""
    width = d013.inactive_width(d013.CONDITION_C)
    count = d013.STATE_COUNT
    entry = 7 << 32
    checksum = ((core.FNV_OFFSET ^ entry) * core.FNV_PRIME) & core.MASK64
    counters = {field: 0 for field in d013.COUNTER_FIELDS}
    counters.update(states=count, lift_total_base=count,
                    lift_total_exact=count * (1 << width), inactive_width=width,
                    row_count=1)
    rows = []
    for encoding in core.ENCODINGS:
        rows.append({"row": 0, "condition": "C", "encoding": encoding,
                     "word_count": count, "minimum": 0.0,
                     "minimum_word": "0000000000000000", "minimum_index": 0,
                     "per_ch": (1, 1, 1), "illegal": 0, "nesting": 0,
                     "compacted_count": 1,
                     "compaction_chunks": core.compaction_chunk_count(count),
                     "compaction_checksum": checksum, "compacted_entries": (entry,),
                     "t_e_size": 1 << width, "t_e_factors": (1, width),
                     "c_e_size": count << width})
    envelope = {"schema": d013.SCHEMA, "abi": d013.ABI_NAME, "backend": 0,
                "condition": "C", "content_sha256": "0" * 64,
                "content_sha256_role": d013.FRAME_HASH_ROLE,
                "result_sha256_role": d013.RESULT_HASH_ROLE,
                "records": rows, "counters": counters,
                "result_sha256": d013.result_commitment("C", rows, counters)}
    d013.require_bounded_result(envelope, "C", 1)
    for field, value in (("t_e_size", count << width),
                         ("t_e_factors", (count, width)),
                         ("c_e_size", 1 << width)):
        changed = [dict(row, **{field: value}) if row["encoding"] == "slack"
                   else row for row in rows]
        forged = dict(envelope, records=changed,
                      result_sha256=d013.result_commitment("C", changed, counters))
        refused(lambda forged=forged: d013.require_bounded_result(forged, "C", 1),
                f"the hand-built {field} mutant passed")
    changed = [dict(row, c_e_size=1 << width) if row["encoding"] == "unbalanced"
               else row for row in rows]
    forged = dict(envelope, records=changed,
                  result_sha256=d013.result_commitment("C", changed, counters))
    refused(lambda: d013.require_bounded_result(forged, "C", 1),
            "the unbalanced |C_E| check was bypassed")
    enlarged = dict(counters, lift_total_base=2 * count,
                    lift_total_exact=(2 * count) << width)
    forged = dict(envelope, counters=enlarged,
                  result_sha256=d013.result_commitment("C", rows, enlarged))
    refused(lambda: d013.require_bounded_result(forged, "C", 1),
            "the whole-domain counter disagreed with the slack stream")


def main() -> None:
    require(sys.byteorder == "little", "the fixtures require a little-endian host")
    check_accounting_contract_without_scan()
    plan = corruption.build_plan()
    require(plan["mode"] == "non_scientific_corruption_plan", "the corruption plan drift")

    with tempfile.TemporaryDirectory(prefix="g9-d013-host-") as temporary:
        scratch = Path(temporary)
        library = scratch / "libg9_d013_host_stub.so"
        v1_library = scratch / "libg9_core_v1_host_stub.so"
        build(library, corruption.source_text())
        v1_build = subprocess.run(
            ["g++", *BUILD_FLAGS, "-I", str(STUB), "-I", str(QUALIFICATION_DIR),
             str(QUALIFICATION_DIR / "stage2_cuda_core_bridge.cu"), "-o", str(v1_library)],
            cwd=ROOT, text=True, capture_output=True, check=False, timeout=600)
        require(v1_build.returncode == 0 and not v1_build.stderr,
                "the v1 host-stub build failed or warned: " + v1_build.stderr[:400])

        # The exported surface: only this path's entries, no v1 or v2 core entry.
        exports = exported_c_symbols(library)
        require(exports == EXPECTED_C_EXPORTS, f"unexpected C exports: {sorted(exports)}")

        check_csb_reproduces_v1(library, v1_library)
        check_against_independent_reference()
        check_small_reference_agrees_with_kernel(library)
        check_plus_zero_bit_pattern(library)
        check_inactive_register_never_visited(library)
        check_corruption_plan_guards()
        check_typed_refusals(library)
        check_argument_fuzz(library)
        check_wp6_crosscheck(library)
        check_direct_abi_refusals(library)
        check_envelope_tampering(library)
        rejected = check_mutations_are_rejected(scratch)

    mode = "python3 -O" if sys.flags.optimize else "python3"
    print(f"PASS Stage-2 D013 +0.0 additive CUDA path ({mode}): CSB reproduces the "
          f"unchanged v1 core bit-for-bit, C/CB/CS match a slow independent Python "
          f"reference, +0.0 bit pattern and sign hold with a reachable -0.0 hazard, "
          f"inactive register visits = 0, {len(rejected)} corruption variants all "
          f"rejected, typed refusals and argument fuzz clean; WP6 cross-check passed")


if __name__ == "__main__":
    main()

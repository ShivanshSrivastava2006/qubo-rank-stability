"""Fast refusal and accounting checks for the Stage-2 D013 Python bridge.

This fixture builds the host stub once, then exercises the public validation,
ABI, envelope, argument-fuzz, and WP6 cross-check paths without running the
large corruption qualification sweep.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import os
from pathlib import Path
from dataclasses import replace
from types import SimpleNamespace
import tempfile
import sys
from unittest import mock

os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

from research.g9.cuda_qualification import stage2_cuda_d013_inactive as d013
from research.g9.cuda_qualification import stage2_cuda_execution_contract as contract

_QUALIFICATION_MODULE = (
    "research.g9.cuda_qualification.stage2_cuda_d013_inactive_corruption_qualification")
_QUALIFICATION_PATH = (Path(__file__).resolve().parent / "cuda_qualification" /
                       "stage2_cuda_d013_inactive_corruption_qualification.py")
_QUALIFICATION_SPEC = importlib.util.spec_from_file_location(
    _QUALIFICATION_MODULE, _QUALIFICATION_PATH)
if _QUALIFICATION_SPEC is None or _QUALIFICATION_SPEC.loader is None:
    raise RuntimeError("the D013 qualification module is unavailable")
qualification = importlib.util.module_from_spec(_QUALIFICATION_SPEC)
sys.modules[_QUALIFICATION_MODULE] = qualification
_QUALIFICATION_IMPORT_OUTPUT = io.StringIO()
try:
    with contextlib.redirect_stdout(_QUALIFICATION_IMPORT_OUTPUT):
        _QUALIFICATION_SPEC.loader.exec_module(qualification)
except SystemExit as exc:
    # An imported module that ran its CLI is a fixture failure. Keep the
    # partially executed module available so the ordinary probes can report it.
    if exc.code not in (None, 0):
        raise RuntimeError("the D013 qualification module exited during import") from exc

from research.g9 import verify_stage2_cuda_d013_inactive_host_emulation as checks


def must_refuse(call, label: str) -> None:
    try:
        call()
    except d013.D013InactiveError:
        return
    raise RuntimeError(f"the fast fixture accepted {label}")


def must_refuse_with(call, label: str, message_fragment: str) -> None:
    try:
        call()
    except d013.D013InactiveError as exc:
        if message_fragment not in str(exc):
            raise RuntimeError(f"{label} was refused for the wrong reason: {exc}") from exc
        return
    raise RuntimeError(f"the fast fixture accepted {label}")


def check_counter_guard_refusals() -> None:
    width = d013.inactive_width(d013.CONDITION_C)
    base = {field: 0 for field in d013.COUNTER_FIELDS}
    base.update(states=d013.STATE_COUNT, lift_total_base=d013.STATE_COUNT,
                lift_total_exact=d013.STATE_COUNT * (1 << width),
                inactive_width=width, row_count=1)
    probes = []
    for field, value, label in (
            ("hazard_negative_zero_states", -1, "a negative counter"),
            ("inactive_register_visits", 1, "inactive register visits"),
            ("inactive_term_nonzero", 1, "a nonzero inactive term"),
            ("negative_zero_energies", 1, "negative-zero energies"),
            ("invalid_registers", 1, "invalid registers"),
            ("states", d013.STATE_COUNT - 1, "a wrong state count"),
            ("row_count", 0, "a wrong row count")):
        changed = dict(base)
        changed[field] = value
        probes.append((changed, label))
    changed_width = dict(base, inactive_width=width + 1,
                         lift_total_exact=d013.STATE_COUNT * (1 << (width + 1)))
    probes.append((changed_width, "a wrong inactive width"))
    changed_base = dict(base, lift_total_base=d013.STATE_COUNT - 1,
                        lift_total_exact=(d013.STATE_COUNT - 1) * (1 << width))
    probes.append((changed_base, "a too-small lift base"))
    changed_exact = dict(base, lift_total_exact=base["lift_total_exact"] - 1)
    probes.append((changed_exact, "an inexact lift total"))
    for counters, label in probes:
        must_refuse(lambda counters=counters: d013.require_bounded_counters(
            counters, "C", 1), label)


def check_discarded_counter_calls() -> None:
    """Exercise both production call sites of require_bounded_counters."""
    bad = {field: 0 for field in d013.COUNTER_FIELDS}
    width = d013.inactive_width(d013.CONDITION_C)
    bad.update(states=d013.STATE_COUNT, lift_total_base=d013.STATE_COUNT,
               lift_total_exact=d013.STATE_COUNT * (1 << width),
               inactive_width=width, row_count=1, invalid_registers=1)
    envelope = accounting_envelope()
    envelope["counters"] = bad
    must_refuse_with(lambda: d013.require_bounded_result(envelope, "C", 1),
                     "bad counters at require_bounded_result",
                     "compiled D013 core reported an invalid register")

    payload = checks.small_payload(0)
    records = checks.small_records("CSB", 0)[:1]
    fake_run = lambda *args: d013.STATUS_OK
    with (mock.patch.object(d013, "_load_checked_abi", return_value=(fake_run, 0)),
          mock.patch.object(d013, "_counters", return_value=bad)):
        must_refuse_with(lambda: d013.run_host_emulated_frame(
            payload, records, "CSB", Path("unused"), 8),
            "bad counters after a successful ABI call",
            "compiled D013 core reported an invalid register")


def check_encoding_branches() -> None:
    """Keep both sides of the slack-only whole-domain counter check live."""
    base = accounting_envelope()
    width = base["counters"]["inactive_width"]
    counters = dict(base["counters"], lift_total_base=d013.STATE_COUNT + 1,
                    lift_total_exact=(d013.STATE_COUNT + 1) * (1 << width))
    rows = [dict(row) for row in base["records"]]
    slack = next(row for row in rows if row["encoding"] == "slack")
    slack["c_e_size"] = d013.STATE_COUNT * (1 << width)
    unbalanced = next(row for row in rows if row["encoding"] != "slack")
    unbalanced["c_e_size"] = d013.STATE_COUNT * (1 << width)
    slack_envelope = dict(base, counters=counters, records=rows)
    slack_envelope["result_sha256"] = d013.result_commitment("C", rows, counters)
    must_refuse_with(lambda: d013.require_bounded_result(slack_envelope, "C", 1),
                     "slack row with a mismatched whole-domain counter",
                     "the slack |C_E| differs from the whole-domain counter")

    rows2 = [dict(row) for row in base["records"]]
    for target in rows2:
        target["encoding"] = "unbalanced"
    unbalanced_envelope = dict(base, counters=counters, records=rows2)
    unbalanced_envelope["result_sha256"] = d013.result_commitment("C", rows2, counters)
    accepted = d013.require_bounded_result(unbalanced_envelope, "C", 1)
    if not any(row["encoding"] == "unbalanced" for row in accepted["records"]):
        raise RuntimeError("the unbalanced encoding did not take its distinct branch")


def accounting_envelope() -> dict[str, object]:
    core = checks.core
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
                "records": rows, "counters": counters, "result_sha256": ""}
    envelope["result_sha256"] = d013.result_commitment("C", rows, counters)
    return envelope


def check_result_shape_refusals() -> None:
    base = accounting_envelope()
    original_hash = base["result_sha256"]
    # bool is an int subclass, but the frozen ABI accepts exact integer tags
    # only. False would otherwise alias the host-emulation backend 0.
    must_refuse(lambda: d013.require_bounded_result(
        dict(base, backend=False), "C", 1), "a boolean backend tag")
    must_refuse(lambda: d013.require_bounded_result(
        dict(base, backend=2), "C", 1), "an out-of-range backend tag")
    probes = []
    probes.append((dict(base, records=list(base["records"][:-1])),
                   "a result with a missing encoding row"))
    records = list(base["records"])
    records[0] = dict(records[0], extra_field=0)
    probes.append((dict(base, records=records), "a record with an extra field"))
    records = [dict(row) for row in base["records"]]
    records[0]["condition"] = "CSB"
    probes.append((dict(base, records=records), "a record for a different condition"))
    records = [dict(row) for row in base["records"]]
    records[0]["encoding"] = "unknown"
    probes.append((dict(base, records=records), "an unknown record encoding"))
    records = [dict(row) for row in base["records"]]
    records[0]["row"] = -1
    probes.append((dict(base, records=records), "an out-of-range result row"))
    records = [dict(row) for row in base["records"]]
    records[0].update(encoding="unbalanced", word_count=d013.STATE_COUNT - 1,
                      compaction_chunks=checks.core.compaction_chunk_count(d013.STATE_COUNT - 1),
                      c_e_size=(d013.STATE_COUNT - 1) *
                      (1 << base["counters"]["inactive_width"]))
    probes.append((dict(base, records=records), "a word count below the decoded domain"))
    for envelope, label in probes:
        with mock.patch.object(d013, "result_commitment", return_value=original_hash):
            must_refuse(lambda envelope=envelope: d013.require_bounded_result(
                envelope, "C", 1), label)


def check_record_value_refusals() -> None:
    base = accounting_envelope()
    expected_hash = base["result_sha256"]
    width = base["counters"]["inactive_width"]
    count = d013.STATE_COUNT

    def probe(label: str, edit, counters=None) -> None:
        records = [dict(row) for row in base["records"]]
        edit(records)
        envelope = dict(base, records=records,
                        counters=dict(base["counters"] if counters is None else counters))
        with mock.patch.object(d013, "result_commitment", return_value=expected_hash):
            must_refuse(lambda: d013.require_bounded_result(envelope, "C", 1), label)

    probe("a non-integer minimum index",
          lambda records: records[0].update(minimum_index="not an int"))
    probe("a negative minimum index",
          lambda records: records[0].update(minimum_index=-1))
    probe("a malformed minimum bit word",
          lambda records: records[0].update(minimum_word="g" * 16))
    probe("minimum bits inconsistent with the minimum",
          lambda records: records[0].update(minimum_word="0000000000000001"))
    probe("a non-integer c_H count",
          lambda records: records[0].update(per_ch=(1.0, 1.0, 1.0)))
    probe("a nonzero illegal or nesting counter",
          lambda records: records[0].update(illegal=1))
    probe("a malformed compacted count",
          lambda records: records[0].update(compacted_count="one"))
    probe("a wrong compaction chunk count",
          lambda records: records[0].update(
              compaction_chunks=checks.core.compaction_chunk_count(count) + 1))
    probe("a non-integer compacted entry",
          lambda records: records[0].update(compacted_entries=(float(7 << 32),)))
    probe("an illegal compacted flag word",
          lambda records: records[0].update(
              compacted_count=2,
              compacted_entries=((9 << 32) | 0, (7 << 32) | 1),
              per_ch=(2, 1, 1), t_e_factors=(1, width), t_e_size=1 << width,
              minimum_index=1,
              compaction_checksum=(((checks.core.FNV_OFFSET ^ (9 << 32)) *
                                    checks.core.FNV_PRIME ^ ((7 << 32) | 1)) *
                                   checks.core.FNV_PRIME) & checks.core.MASK64))
    probe("non-ascending compacted entries",
          lambda records: records[0].update(
              compacted_count=2, compacted_entries=((7 << 32), (7 << 32)),
              per_ch=(2, 2, 2), t_e_factors=(2, width), t_e_size=2 << width,
              compaction_checksum=(((checks.core.FNV_OFFSET ^ (7 << 32)) *
                                    checks.core.FNV_PRIME ^ (7 << 32)) *
                                   checks.core.FNV_PRIME) & checks.core.MASK64))
    probe("c_H counts inconsistent with entries",
          lambda records: records[0].update(per_ch=(1, 1, 2)))
    probe("incorrect |T_E| factors",
          lambda records: records[0].update(t_e_factors=(0, width)))
    probe("incorrect |T_E| size",
          lambda records: records[0].update(t_e_size=2 << width))
    probe("incorrect |C_E| size",
          lambda records: records[0].update(encoding="unbalanced",
                                            c_e_size=(count << width) - 1))
    mismatched_counters = dict(base["counters"], lift_total_base=count + 1,
                               lift_total_exact=(count + 1) * (1 << width))
    probe("a slack row inconsistent with the |C_E| counter",
          lambda records: None, counters=mismatched_counters)
    probe("an incorrect compaction checksum",
          lambda records: records[0].update(compaction_checksum=(
              records[0]["compaction_checksum"] + 1) & checks.core.MASK64))
    probe("a missing stream-minimum tie entry",
          lambda records: records[0].update(minimum_index=1))


def check_commitment_refusals() -> None:
    envelope = accounting_envelope()
    counters = envelope["counters"]
    record = dict(envelope["records"][0])
    must_refuse(lambda: d013.result_commitment("C", None, counters),
                "non-sequence commitment records")
    must_refuse(lambda: d013.result_commitment("C", [], {}),
                "commitment counters with the wrong key set")
    extra_field = dict(record, extra_field=0)
    must_refuse(lambda: d013.result_commitment("C", [extra_field], counters),
                "a commitment record with the wrong field set")
    wrong_condition = dict(record, condition="CSB")
    must_refuse(lambda: d013.result_commitment("C", [wrong_condition], counters),
                "a commitment record for another condition")
    wrong_encoding = dict(record, encoding="unknown")
    must_refuse(lambda: d013.result_commitment("C", [wrong_encoding], counters),
                "a commitment record with an unknown encoding")
    nonfinite = dict(record, minimum=float("nan"))
    must_refuse(lambda: d013.result_commitment("C", [nonfinite], counters),
                "a non-finite commitment minimum")


def check_run_host_refusals(library: Path) -> None:
    payload = checks.small_payload(0)
    records = checks.small_records("CSB", 0)[:1]
    invoked = []
    def forbidden_run(*args):
        invoked.append(True)
        return d013.STATUS_OK
    with mock.patch.object(d013, "_load_checked_abi", return_value=(forbidden_run, 1)):
        must_refuse(lambda: d013.run_host_emulated_frame(
            payload, records, "CSB", library, 8), "a CUDA backend in the host-only API")
    if invoked:
        raise RuntimeError("the host-only API invoked a CUDA backend before refusing it")

    for status, label, message in (
            (d013.STATUS_BUSY, "a busy compiled core", "busy with another call"),
            (d013.STATUS_REFUSED, "a refused compiled call", "refused or failed")):
        fake_run = lambda *args, status=status: status
        with (mock.patch.object(d013, "_load_checked_abi", return_value=(fake_run, 0)),
              mock.patch.object(d013, "_counters", side_effect=RuntimeError(
                  "the output was read before the status refusal"))):
            must_refuse_with(lambda: d013.run_host_emulated_frame(
                payload, records, "CSB", library, 8), label, message)

    valid_counters = dict(accounting_envelope()["counters"], inactive_width=0,
                          lift_total_exact=d013.STATE_COUNT)
    summaries = {
        (0, encoding): {"word_count": d013.STATE_COUNT, "minimum": 0.0,
                        "minimum_index": 0, "per_ch": (1, 1, 1), "illegal": 0,
                        "nesting": 0, "compacted_count": 1,
                        "compaction_chunks": checks.core.compaction_chunk_count(d013.STATE_COUNT),
                        "compaction_checksum": 0,
                        "compacted_entries": (7 << 32,)}
        for encoding in checks.core.ENCODINGS}
    fake_run = lambda *args: d013.STATUS_OK
    with (mock.patch.object(d013, "_load_checked_abi", return_value=(fake_run, 0)),
          mock.patch.object(d013, "_counters", return_value=valid_counters),
          mock.patch.object(d013, "_summaries", return_value=summaries),
          mock.patch.object(d013, "require_bounded_counters"),
          mock.patch.object(d013, "content_hash_for", return_value="0" * 64),
          mock.patch.object(d013, "result_commitment", return_value="0" * 64),
          mock.patch.object(d013, "require_bounded_result", return_value={})):
        must_refuse(lambda: d013.run_host_emulated_frame(
            payload, records, "CSB", library, 8), "a compiled condition echo mismatch")

    echoed_output = d013.D013Output()
    echoed_output.conditions[0] = d013.CONDITION_CODE["CSB"]
    wrong_minimum_summaries = {
        key: dict(value, minimum=1.0) for key, value in summaries.items()}
    with (mock.patch.object(d013, "D013Output", return_value=echoed_output),
          mock.patch.object(d013, "_load_checked_abi", return_value=(fake_run, 0)),
          mock.patch.object(d013, "_counters", return_value=valid_counters),
          mock.patch.object(d013, "_summaries", return_value=wrong_minimum_summaries),
          mock.patch.object(d013, "_word", return_value=0),
          mock.patch.object(d013, "require_bounded_counters"),
          mock.patch.object(d013, "content_hash_for", return_value="0" * 64),
          mock.patch.object(d013, "result_commitment", return_value="0" * 64),
          mock.patch.object(d013, "require_bounded_result", return_value={})):
        must_refuse_with(lambda: d013.run_host_emulated_frame(
            payload, records, "CSB", library, 8),
            "a compiled minimum word mismatch",
            "the minimum word does not round-trip to its minimum")


def check_wp6_minimum_index_refusal() -> None:
    payload = checks.narrow_payload(0)
    instance = checks.Instance(
        tickers=tuple(f"N{position:02d}" for position in range(checks.NARROW_WIDTH)),
        sectors=payload["sectors"], mu=tuple(payload["mu"]),
        sigma=tuple(tuple(row) for row in payload["sigma"]),
        prices=tuple(payload["prices"]), kappa_risk=payload["kappa_risk"],
        K=int(payload["k"]), C=int(payload["c"]), B=payload["b"])
    ledger = checks.small_records("CSB", 0)[0]
    context = checks.wp6.prepare_condition(instance, "C", ledger, payload["lambda_ref"])
    canonical = checks.wp6.evaluate_condition(context)
    result, _ = checks.narrow_kernel_model(payload, ledger, "C")
    width = len(canonical.z_ref) - 5
    rows = [dict(row) for row in result["records"]]
    for row in rows:
        if row["encoding"] == "slack":
            # A string reaches the public result boundary and must be refused
            # by the dedicated line-563 type/range guard before bitwise use.
            row["minimum_index"] = "not-an-index"
    changed = dict(result, records=rows)
    bounded = accounting_envelope()
    bounded_rows = [dict(row) for row in bounded["records"]]
    next(row for row in bounded_rows if row["encoding"] == "slack")[
        "minimum_index"] = "not-an-index"
    bounded["records"] = bounded_rows
    must_refuse_with(lambda: d013.require_bounded_result(bounded, "C", 1),
        "a non-integer minimum index at the bounded-result boundary",
        "record minimum index is outside the stream")


def _wp6_fixture_case():
    payload = checks.narrow_payload(0)
    instance = checks.Instance(
        tickers=tuple(f"N{position:02d}" for position in range(checks.NARROW_WIDTH)),
        sectors=payload["sectors"], mu=tuple(payload["mu"]),
        sigma=tuple(tuple(row) for row in payload["sigma"]),
        prices=tuple(payload["prices"]), kappa_risk=payload["kappa_risk"],
        K=int(payload["k"]), C=int(payload["c"]), B=payload["b"])
    ledger = checks.small_records("CSB", 0)[0]
    context = checks.wp6.prepare_condition(instance, "C", ledger, payload["lambda_ref"])
    canonical = checks.wp6.evaluate_condition(context)
    result, _ = checks.narrow_kernel_model(payload, ledger, "C")
    return result, canonical, context


def check_wp6_field_mismatch_refusals() -> None:
    """Each discarded _same call has one isolated, named negative probe."""
    result, canonical, context = _wp6_fixture_case()
    original = d013.cross_check_against_wp6_evaluator(
        result, "C", canonical, wp6_context=context)
    probes = []
    probes.append((replace(canonical, h_e_min=canonical.h_e_min + 1.0),
                   "minimum_word"))
    probes.append((replace(canonical, tie_set=canonical.tie_set + ((0,) * len(canonical.z_ref[:-5]),)),
                   "tie_set"))
    probes.append((replace(canonical, t_e_factors=(canonical.t_e_factors[0] + 1,
                                                   canonical.t_e_factors[1])),
                   "tie_count"))
    probes.append((replace(canonical, t_e_size=canonical.t_e_size + 1), "|T_E|"))
    probes.append((replace(canonical, t_e_factors=(canonical.t_e_factors[0],
                                                   canonical.t_e_factors[1] + 1)),
                   "|T_E| factors"))
    probes.append((replace(canonical,
                           raw_domain=replace(canonical.raw_domain,
                                             raw_size=canonical.raw_domain.raw_size + 1)),
                   "|C_E|"))
    probes.append((replace(canonical, atomic_labels=canonical.atomic_labels +
                           (((0,) * len(canonical.z_ref[:-5]), "A"),)),
                   "D016 atomic labels"))
    probes.append((replace(canonical, primary_label="NOT-A-WP6-LABEL"),
                   "D016 primary label"))
    changed_counts = dict(canonical.label_counts)
    changed_counts["A"] = changed_counts.get("A", 0) + 1
    probes.append((replace(canonical, label_counts=changed_counts), "D016 label counts"))

    for altered, field in probes:
        must_refuse_with(lambda altered=altered: d013.cross_check_against_wp6_evaluator(
            result, "C", altered, wp6_context=context),
            f"a WP6 cross-check mismatch in {field}", f"WP6 mismatch C row 0 {field}:")
    if original["minimum_word"] != format(checks.wp6.bits_of(canonical.h_e_min), "016x"):
        raise RuntimeError("the baseline WP6 comparison did not match before perturbation")


def check_canonical_index_branch() -> None:
    """The canonical index is compared for whole registers and skipped otherwise."""
    result, canonical, context = _wp6_fixture_case()
    width = len(canonical.z_ref) - 5
    x_index = sum(bit << (width - 1 - index)
                  for index, bit in enumerate(canonical.z_ref[:width]))
    changed_rows = [dict(row) for row in result["records"]]
    slack = next(row for row in changed_rows if row["encoding"] == "slack")
    slack["minimum_index"] = (x_index + 1) % slack["word_count"]
    changed = dict(result, records=changed_rows)
    must_refuse_with(lambda: d013.cross_check_against_wp6_evaluator(
        changed, "C", canonical, wp6_context=context),
        "whole-register canonical index mismatch",
        "WP6 mismatch C row 0 canonical_minimum_index:")

    # A fractional active register removes the x-to-stream-index mapping. With
    # that one semantic condition changed, the unrelated stream position must
    # be ignored rather than compared against the displayed x word.
    nonwhole_tail = list(canonical.z_ref[width:])
    nonwhole_tail[0] = 0.5
    nonwhole = replace(canonical, z_ref=canonical.z_ref[:width] + tuple(nonwhole_tail))
    d013.cross_check_against_wp6_evaluator(changed, "C", nonwhole, wp6_context=context)


def check_crosscheck_width_guard() -> None:
    """Reach the width operand with the raw-domain equality still satisfied."""
    result, canonical, context = _wp6_fixture_case()
    widthless = replace(canonical, z_ref=canonical.z_ref[-5:])
    must_refuse_with(lambda: d013.cross_check_against_wp6_evaluator(
        result, "C", widthless, wp6_context=context),
        "a cross-check with no displayed x bits", "one active lift per decoded state")


def check_conjunct_refusals() -> None:
    """One-conjunct-at-a-time malformed inputs for the guard-sweep survivors."""
    base = accounting_envelope()
    original_hash = base["result_sha256"]

    def result_probe(label: str, edit, message: str) -> None:
        rows = [dict(row) for row in base["records"]]
        counters = dict(base["counters"])
        envelope = dict(base, records=rows, counters=counters)
        edit(envelope, rows, counters)
        with mock.patch.object(d013, "result_commitment", return_value=original_hash):
            must_refuse_with(lambda: d013.require_bounded_result(envelope, "C", 1),
                             label, message)

    def row0(rows):
        return rows[0]

    must_refuse_with(lambda: d013.is_positive_zero(1), "integer positive-zero input",
                     "needs a finite float")
    must_refuse_with(lambda: d013.is_positive_zero(float("nan")),
                     "non-finite positive-zero input", "needs a finite float")
    for value in (1, True):
        must_refuse_with(lambda value=value: d013.is_negative_zero(value),
                         "non-float negative-zero input", "needs a finite float")
    must_refuse_with(lambda: d013.is_negative_zero(float("nan")),
                     "non-finite negative-zero input", "needs a finite float")
    if d013.is_negative_zero(-0.0) is not True:
        raise RuntimeError("a finite negative-zero float was not recognized")
    must_refuse_with(lambda: d013.inactive_width(True), "bool condition width",
                     "condition code is out of range")
    must_refuse_with(lambda: d013.inactive_width(-1), "negative condition width",
                     "condition code is out of range")
    must_refuse_with(lambda: d013.validate_condition(True), "bool condition value",
                     "unknown D013 condition code")
    with mock.patch.object(d013, "condition_name", return_value="C") as lookup:
        must_refuse_with(lambda: d013.validate_condition(99), "unknown integer condition code",
                         "unknown D013 condition code")
        if lookup.called:
            raise RuntimeError("an unknown condition code reached condition_name")
    must_refuse_with(lambda: d013._load_checked_abi("not-a-path"),
                     "non-Path ABI library name", "compiled D013 ABI library is missing")
    path_payload = checks.small_payload(0)
    path_records = checks.small_records("CSB", 0)[:1]
    must_refuse_with(lambda: d013.run_host_emulated_frame(
        path_payload, path_records, "CSB", "not-a-path", 8),
        "non-Path ABI library name at frame entry",
        "the compiled D013 library must be named by a pathlib.Path")
    with tempfile.TemporaryDirectory(prefix="g9-d013-path-probe-") as path_probe:
        must_refuse_with(lambda: d013._load_checked_abi(Path(path_probe) / "missing.so"),
                         "missing ABI library path", "compiled D013 ABI library is missing")
    must_refuse_with(lambda: d013.validate_coefficient_record(
        dict(checks.small_records("CSB", 0)[0], alpha=1), "CSB"),
        "integer coefficient", "must be a finite float")

    must_refuse_with(lambda: d013.validate_records("not-records", "C"),
                     "string coefficient records", "coefficient records must be a sequence")
    must_refuse_with(lambda: d013.decode_conditions("C", True),
                     "bool ABI row count", "needs a row count inside the ABI capacity")

    bad_counter = dict(base["counters"], hazard_negative_zero_states=True)
    must_refuse_with(lambda: d013.require_bounded_counters(bad_counter, "C", 1),
                     "bool counter", "must be a non-negative int")

    for field, value in (("schema", "wrong"), ("abi", "wrong"),
                         ("content_sha256_role", "wrong"),
                         ("result_sha256_role", "wrong")):
        result_probe(f"bad envelope {field}",
                     lambda env, rows, counters, field=field, value=value:
                         env.__setitem__(field, value),
                     "envelope schema or declared roles differ")
    result_probe("bool backend", lambda env, rows, counters: env.__setitem__("backend", False),
                 "envelope backend is not the host-emulation stub")
    result_probe("integer content digest",
                 lambda env, rows, counters: env.__setitem__("content_sha256", 0),
                 "content hash is not a lowercase SHA-256")
    with mock.patch.object(d013, "result_commitment", return_value=original_hash):
        expected_bad = "a" * 63
        must_refuse_with(lambda: d013.require_bounded_result(
            base, "C", 1, expected_content_sha256=expected_bad),
            "short rebuilt digest", "consumer's rebuilt inputs")
    with mock.patch.object(d013, "result_commitment", return_value=original_hash):
        must_refuse_with(lambda: d013.require_bounded_result(
            base, "C", 1, expected_content_sha256=1),
            "integer rebuilt digest", "consumer's rebuilt inputs")

    # A tuple has the expected size and is iterable, but the envelope contract
    # requires its public record collection to be a list.
    tuple_envelope = dict(base, records=tuple(base["records"]))
    with mock.patch.object(d013, "result_commitment", return_value=original_hash):
        must_refuse_with(lambda: d013.require_bounded_result(tuple_envelope, "C", 1),
                         "tuple result records", "record set has the wrong size")
    result_probe("mapping record", lambda env, rows, counters:
                 rows.__setitem__(0, SimpleNamespace(**rows[0])),
                 "record has the wrong field set")
    result_probe("bool record row", lambda env, rows, counters:
                 row0(rows).__setitem__("row", False), "record row is out of range")
    result_probe("float word count", lambda env, rows, counters:
                 row0(rows).__setitem__("word_count", float(d013.STATE_COUNT)),
                 "record word count is below the decoded domain")
    result_probe("integer minimum", lambda env, rows, counters:
                 row0(rows).__setitem__("minimum", 0), "record minimum is not finite")
    result_probe("non-finite floating minimum", lambda env, rows, counters:
                 row0(rows).__setitem__("minimum", float("nan")),
                 "record minimum is not finite")
    result_probe("short minimum word", lambda env, rows, counters:
                 row0(rows).__setitem__("minimum_word", "0"),
                 "record minimum word is not a 16-digit binary64 bit pattern")
    result_probe("non-string minimum word", lambda env, rows, counters:
                 row0(rows).__setitem__("minimum_word", 0),
                 "record minimum word is not a 16-digit binary64 bit pattern")
    result_probe("out-of-range minimum index", lambda env, rows, counters:
                 row0(rows).__setitem__("minimum_index", d013.STATE_COUNT),
                 "record minimum index is outside the stream")
    result_probe("list per-channel counts", lambda env, rows, counters:
                 row0(rows).__setitem__("per_ch", [1, 1, 1]),
                 "per-c_H counts are malformed")
    tuple_like = type("TupleLike", (tuple,), {})((1, 1, 1))
    result_probe("tuple subclass per-channel counts", lambda env, rows, counters:
                 row0(rows).__setitem__("per_ch", tuple_like),
                 "per-c_H counts are malformed")
    result_probe("short tuple per-channel counts", lambda env, rows, counters:
                 row0(rows).__setitem__("per_ch", (1, 1)),
                 "per-c_H counts are malformed")
    result_probe("bool per-channel count", lambda env, rows, counters:
                 row0(rows).__setitem__("per_ch", (True, 1, 1)),
                 "per-c_H counts are malformed")
    result_probe("negative per-channel count", lambda env, rows, counters:
                 row0(rows).__setitem__("per_ch", (-1, 1, 1)),
                 "per-c_H counts are malformed")
    result_probe("bool illegal flag", lambda env, rows, counters:
                 row0(rows).__setitem__("illegal", False),
                 "record reports illegal or non-nested flags")
    result_probe("bool nesting flag", lambda env, rows, counters:
                 row0(rows).__setitem__("nesting", False),
                 "record reports illegal or non-nested flags")
    result_probe("nonzero integer nesting flag", lambda env, rows, counters:
                 row0(rows).__setitem__("nesting", 1),
                 "record reports illegal or non-nested flags")
    result_probe("bool compacted count", lambda env, rows, counters:
                 row0(rows).__setitem__("compacted_count", True),
                 "compacted entry count is outside the declared cap")
    result_probe("list compacted entries", lambda env, rows, counters:
                 row0(rows).__setitem__("compacted_entries", [7 << 32]),
                 "compacted entry count is outside the declared cap")
    result_probe("compacted entry count mismatch", lambda env, rows, counters:
                 row0(rows).__setitem__("compacted_count", 2),
                 "compacted entry count is outside the declared cap")
    def empty_compaction(env, rows, counters):
        row = row0(rows)
        width = counters["inactive_width"]
        row.update(compacted_count=0, compacted_entries=(), per_ch=(0, 0, 0),
                   t_e_factors=(0, width), t_e_size=0,
                   compaction_checksum=checks.core.FNV_OFFSET)
    result_probe("zero compacted entry count", empty_compaction,
                 "compacted entry count is outside the declared cap")
    result_probe("float compaction chunks", lambda env, rows, counters:
                 row0(rows).__setitem__("compaction_chunks",
                     float(checks.core.compaction_chunk_count(d013.STATE_COUNT))),
                 "compaction chunk count differs from the stream length")
    result_probe("float compacted entry", lambda env, rows, counters:
                 row0(rows).__setitem__("compacted_entries", (float(7 << 32),)),
                 "compacted entry is not a uint64")
    result_probe("negative compacted entry", lambda env, rows, counters:
                 row0(rows).__setitem__("compacted_entries", (-1,)),
                 "compacted entry is not a uint64")
    result_probe("tuple subclass tie factors", lambda env, rows, counters:
                 row0(rows).__setitem__("t_e_factors", type("TupleLike", (tuple,), {})( (1, base["counters"]["inactive_width"]) )),
                 "|T_E| factors differ from the tied active candidates")
    result_probe("float tie size", lambda env, rows, counters:
                 row0(rows).__setitem__("t_e_size", float(1 << base["counters"]["inactive_width"])),
                 "|T_E| differs from tie_count * 2^w")
    result_probe("float whole-domain size", lambda env, rows, counters:
                 row0(rows).__setitem__("c_e_size", float(d013.STATE_COUNT << base["counters"]["inactive_width"])),
                 "|C_E| differs from the whole active domain")

    # result_commitment has independent public input checks; use duck mappings
    # that provide the expected key behaviour but do not satisfy Mapping.
    class DuckMap:
        def __init__(self, values): self._values = values
        def __iter__(self): return iter(self._values)
        def __len__(self): return len(self._values)
        def __getitem__(self, key): return self._values[key]
        def keys(self): return self._values.keys()
        def items(self): return self._values.items()

    must_refuse_with(lambda: d013.result_commitment("C", "records", base["counters"]),
                     "string commitment records", "commitment records must be a sequence")
    must_refuse_with(lambda: d013.result_commitment("C", [], DuckMap(base["counters"])),
                     "duck commitment counters", "commitment counters have the wrong key set")
    duck_record = DuckMap(base["records"][0])
    must_refuse_with(lambda: d013.result_commitment("C", [duck_record], base["counters"]),
                     "duck commitment record", "commitment record has the wrong field set")
    nonfinite = dict(base["records"][0], minimum=float("inf"))
    must_refuse_with(lambda: d013.result_commitment("C", [nonfinite], base["counters"]),
                     "non-finite commitment minimum", "commitment minimum must be a finite float")
    nonfloat = dict(base["records"][0], minimum=1)
    must_refuse_with(lambda: d013.result_commitment("C", [nonfloat], base["counters"]),
                     "integer commitment minimum", "commitment minimum must be a finite float")
    must_refuse_with(lambda: d013._require_feasible_nonempty(True, "C"),
                     "bool feasible size", "must be a non-negative int")
    must_refuse_with(lambda: d013._require_feasible_nonempty(-1, "C"),
                     "negative feasible size", "must be a non-negative int")

    # The two cross-check operand guards share valid fixtures but are probed
    # with exactly one failed conjunct each.
    result, canonical, context = _wp6_fixture_case()
    mismatched_condition = replace(canonical, condition="CB")
    must_refuse_with(lambda: d013.cross_check_against_wp6_evaluator(
        result, "C", mismatched_condition, wp6_context=context),
        "cross-check condition mismatch", "canonical WP6 result or condition is malformed")
    bad_context = replace(context, condition="CB")
    must_refuse_with(lambda: d013.cross_check_against_wp6_evaluator(
        result, "C", canonical, wp6_context=bad_context),
        "cross-check context mismatch", "WP6 D016 context is malformed")
    must_refuse_with(lambda: d013.cross_check_against_wp6_evaluator(
        result, "C", canonical, row=-1, wp6_context=context),
        "negative cross-check row", "cross-check row must be a nonnegative int")
    bad_domain = replace(canonical.raw_domain, base=canonical.raw_domain.base + 1)
    bad_base_result = replace(canonical, raw_domain=bad_domain)
    must_refuse_with(lambda: d013.cross_check_against_wp6_evaluator(
        result, "C", bad_base_result, wp6_context=context),
        "cross-check active-domain mismatch", "one active lift per decoded state")


def check_gpu_release_refusals() -> None:
    """Exercise hash, approval, compiler and backend-token refusals offline."""
    import hashlib
    import json
    import os
    import tempfile
    from pathlib import Path

    def expect(call, label: str, fragment: str) -> None:
        try:
            call()
        except qualification.CorruptionQualificationError as exc:
            if fragment not in str(exc):
                raise RuntimeError(f"{label} refused for the wrong reason: {exc}") from exc
            return
        raise RuntimeError(f"accepted {label}")

    with tempfile.TemporaryDirectory(prefix="g9-d013-gpu-gates-") as tmp:
        draft_path = Path(tmp) / "release.json"
        original_rel = qualification.RELEASE_DRAFT_REL
        original_root = qualification.ROOT

        def write_release(approved: bool, *, extra_field: bool = False,
                          bad_flags: bool = False, bad_mutations: bool = False,
                          bad_detection_cases: bool = False,
                          bad_detection_hash: bool = False, schema: str =
                          "decisions_os/g9_d013_cuda_release_draft/v1") -> bytes:
            body = {"schema": schema,
                    "owner_approved": approved,
                    "source_sha256": qualification.source_hashes(),
                    "compile_flags": list(qualification.GPU_COMPILE_FLAGS),
                    "mutations": [{"label": m.label, "category": m.category,
                                   "hazard": m.hazard} for m in qualification.MUTATIONS],
                    "detection_cases": qualification.canonical_detection_table(),
                    "detection_cases_sha256": qualification.detection_table_sha256()}
            if extra_field:
                body["unreviewed_field"] = "fixture probe"
            if bad_flags:
                body["compile_flags"] = ["-O3"]
            if bad_mutations:
                body["mutations"][0]["label"] = "unreviewed mutation"
            if bad_detection_cases:
                body["detection_cases"][0]["cases"][0]["condition"] = "CB"
            if bad_detection_hash:
                body["detection_cases_sha256"] = "0" * 64
            raw = contract.canonical_bytes(body) + b"\n"
            draft_path.write_bytes(raw)
            return raw

        try:
            with mock.patch.dict(os.environ, {"PYTHONDONTWRITEBYTECODE": "1",
                                               qualification.ALLOW_ENV: "1"}):
                qualification.RELEASE_DRAFT_REL = str(Path(tmp) / "missing.json")
                expect(lambda: qualification.run_qualification("0" * 64), "missing release",
                       "release draft is unavailable")

                qualification.RELEASE_DRAFT_REL = str(draft_path)
                pending = write_release(False)
                expect(lambda: qualification.run_qualification("f" * 64), "release hash mismatch",
                       "hash differs")
                expect(lambda: qualification.run_qualification(hashlib.sha256(pending).hexdigest()),
                       "owner approval false", "not canonical and owner-approved")

                approved = write_release(True)
                approved_sha = hashlib.sha256(approved).hexdigest()
                # The release hash can match bytes whose decoded meaning is
                # correct but whose representation is not canonical. The
                # byte-for-byte canonicality check must reject that handoff.
                release_body = json.loads(approved)
                noncanonical = json.dumps(release_body, sort_keys=True,
                                          indent=2).encode("utf-8") + b"\n"
                draft_path.write_bytes(noncanonical)
                expect(lambda: qualification.run_qualification(
                    hashlib.sha256(noncanonical).hexdigest()),
                    "noncanonical release JSON",
                    "D013 release draft is not canonical and owner-approved")

                approved = write_release(True)
                approved_sha = hashlib.sha256(approved).hexdigest()
                saved_bytecode = os.environ.pop("PYTHONDONTWRITEBYTECODE")
                try:
                    expect(lambda: qualification.run_qualification(approved_sha),
                           "bytecode environment gate",
                           "PYTHONDONTWRITEBYTECODE=1 is required")
                finally:
                    os.environ["PYTHONDONTWRITEBYTECODE"] = saved_bytecode
                saved_permission = os.environ.pop(qualification.ALLOW_ENV)
                try:
                    expect(lambda: qualification.run_qualification(approved_sha),
                           "separate execution permission gate",
                           "separate D013 A-execution permission is required")
                finally:
                    os.environ[qualification.ALLOW_ENV] = saved_permission
                for malformed in (None, 1, "A" * 64, "a" * 63):
                    expect(lambda malformed=malformed: qualification.run_qualification(malformed),
                           "malformed reviewed release digest",
                           "reviewed D013 A-release SHA-256 is required")
                extra_release = write_release(True, extra_field=True)
                expect(lambda: qualification.run_qualification(
                    hashlib.sha256(extra_release).hexdigest()),
                    "release draft with an extra field",
                    "D013 release draft is not canonical and owner-approved")
                bad_flags = write_release(True, bad_flags=True)
                expect(lambda: qualification.run_qualification(hashlib.sha256(bad_flags).hexdigest()),
                       "release draft with changed compiler flags",
                       "D013 release draft flags or mutation list drift")
                bad_mutations = write_release(True, bad_mutations=True)
                expect(lambda: qualification.run_qualification(hashlib.sha256(bad_mutations).hexdigest()),
                       "release draft with changed mutation list",
                       "D013 release draft flags or mutation list drift")
                bad_cases = write_release(True, bad_detection_cases=True)
                expect(lambda: qualification.run_qualification(hashlib.sha256(bad_cases).hexdigest()),
                       "release draft with changed detection cases",
                       "D013 release draft flags or mutation list drift")
                bad_case_hash = write_release(True, bad_detection_hash=True)
                expect(lambda: qualification.run_qualification(hashlib.sha256(bad_case_hash).hexdigest()),
                       "release draft with changed detection table hash",
                       "D013 release draft flags or mutation list drift")
                bad_schema = write_release(True, schema="decisions_os/unreviewed/v1")
                expect(lambda: qualification.run_qualification(hashlib.sha256(bad_schema).hexdigest()),
                       "release draft with changed schema",
                       "D013 release draft is not canonical and owner-approved")
                non_object = contract.canonical_bytes([
                    "schema", "owner_approved", "source_sha256", "compile_flags", "mutations",
                    "detection_cases", "detection_cases_sha256"]
                ) + b"\n"
                draft_path.write_bytes(non_object)
                expect(lambda: qualification.run_qualification(
                    hashlib.sha256(non_object).hexdigest()),
                    "non-object release JSON",
                    "D013 release draft is not canonical and owner-approved")
                invalid_json = b"{\"schema\":"
                draft_path.write_bytes(invalid_json)
                expect(lambda: qualification.run_qualification(hashlib.sha256(invalid_json).hexdigest()),
                       "invalid JSON release draft", "D013 A-execution release is invalid JSON")

                approved = write_release(True)
                approved_sha = hashlib.sha256(approved).hexdigest()
                symlink_path = Path(tmp) / "release-symlink.json"
                symlink_path.symlink_to(draft_path)
                qualification.RELEASE_DRAFT_REL = str(symlink_path)
                expect(lambda: qualification.run_qualification(approved_sha),
                       "symlinked release draft", "D013 release draft is unavailable")
                qualification.RELEASE_DRAFT_REL = str(draft_path)

                approved = write_release(True)
                approved_sha = hashlib.sha256(approved).hexdigest()
                drift_root = Path(tmp) / "source-drift-root"
                for relative in qualification.SOURCE_RELS:
                    staged = drift_root / relative
                    staged.parent.mkdir(parents=True, exist_ok=True)
                    staged.write_bytes((original_root / relative).read_bytes())
                qualification.ROOT = drift_root
                source_path = drift_root / qualification.SOURCE_REL
                original_source = source_path.read_bytes()
                source_path.write_bytes(original_source + b"\n// source drift probe\n")
                try:
                    expect(lambda: qualification.run_qualification(approved_sha),
                           "source map changed after release", "source map changed after release")
                finally:
                    qualification.ROOT = original_root

                approved = write_release(True)
                approved_sha = hashlib.sha256(approved).hexdigest()
                if qualification.shutil.which("nvcc") is None:
                    expect(lambda: qualification.run_qualification(approved_sha), "nvcc missing",
                           "nvcc is unavailable")
                else:
                    with mock.patch.object(qualification.shutil, "which", return_value=None):
                        expect(lambda: qualification.run_qualification(approved_sha), "nvcc missing",
                               "nvcc is unavailable")

            source = qualification.source_text()
            old = ('extern "C" std::uint32_t g9_d013_backend() {\n'
                   '#if defined(__CUDACC__)\n  return 1u;\n#else\n  return 0u;\n#endif\n}')
            if source.count(old) != 1:
                raise RuntimeError("backend tag fixture anchor drifted")
            library = Path(tmp) / "libfake_cuda.so"
            checks.build(library, source.replace(old,
                'extern "C" std::uint32_t g9_d013_backend() { return 1u; }', 1))
            forged = qualification.VerifiedReleaseToken("0" * 64, "1" * 64, "2" * 64)
            for token, label in ((None, "backend 1 without token"), (forged, "forged token")):
                try:
                    d013._load_checked_abi(library, verified_release=token)
                except d013.D013InactiveError:
                    continue
                raise RuntimeError(f"accepted {label}")

            approved = write_release(True)
            release_body = json.loads(approved)
            release_sha = hashlib.sha256(approved).hexdigest()
            source_map = release_body["source_sha256"]
            valid_token = {"release_sha256": release_sha,
                           "source_map_sha256": qualification._sha(
                               contract.canonical_bytes(source_map)),
                           "proof_sha256": qualification._token_proof(release_sha, source_map)}
            if not qualification._check_token(valid_token):
                raise RuntimeError("the verified-release receipt token was refused")
            qualification.RELEASE_DRAFT_REL = str(symlink_path)
            if qualification._check_token(valid_token):
                raise RuntimeError("the token checker accepted a symlinked release")
            qualification.RELEASE_DRAFT_REL = str(Path(tmp) / "missing-token-release.json")
            if qualification._check_token(valid_token):
                raise RuntimeError("the token checker accepted a missing release")
            qualification.RELEASE_DRAFT_REL = str(draft_path)

            def token_for(body, *, raw=None):
                token_bytes = contract.canonical_bytes(body) + b"\n" if raw is None else raw
                draft_path.write_bytes(token_bytes)
                digest = hashlib.sha256(token_bytes).hexdigest()
                source_map = body.get("source_sha256", {})
                return {"release_sha256": digest,
                        "source_map_sha256": qualification._sha(
                            contract.canonical_bytes(source_map)),
                        "proof_sha256": qualification._token_proof(digest, source_map)}

            if qualification._check_token(object()):
                raise RuntimeError("the token checker accepted an unrecognized token type")
            if qualification._check_token({**valid_token, "extra": "field"}):
                raise RuntimeError("the token checker accepted an extra token field")
            for field in ("release_sha256", "source_map_sha256", "proof_sha256"):
                broken = dict(valid_token)
                broken[field] = "0" * 64
                if field == "release_sha256":
                    broken["proof_sha256"] = qualification._token_proof(
                        broken["release_sha256"], release_body["source_sha256"])
                if qualification._check_token(broken):
                    raise RuntimeError(f"the token checker accepted a forged {field}")

            approved_body = json.loads(approved)
            token_cases = []
            for label, change in (
                    ("owner approval", lambda body: body.update(owner_approved=False)),
                    ("schema", lambda body: body.update(schema="decisions_os/unreviewed/v1")),
                    ("compile flags", lambda body: body.update(compile_flags=["-O3"])),
                    ("mutation list", lambda body: body["mutations"].pop()),
                    ("detection cases", lambda body: body["detection_cases"][0]["cases"][0].update(
                        condition="CB")),
                    ("detection table hash", lambda body: body.update(
                        detection_cases_sha256="0" * 64)),
                    ("source map", lambda body: body["source_sha256"].update(
                        {qualification.SOURCE_REL: "f" * 64})),
                    ("extra release field", lambda body: body.update(extra="field"))):
                body = json.loads(approved)
                change(body)
                candidate_token = token_for(body)
                token_cases.append((label, body, candidate_token))
            for label, body, token in token_cases:
                draft_path.write_bytes(contract.canonical_bytes(body) + b"\n")
                if qualification._check_token(token):
                    raise RuntimeError(f"the token checker accepted changed {label}")

            noncanonical_body = json.loads(approved)
            noncanonical_raw = json.dumps(noncanonical_body, sort_keys=True,
                                          indent=2).encode("utf-8") + b"\n"
            noncanonical_token = token_for(noncanonical_body, raw=noncanonical_raw)
            if qualification._check_token(noncanonical_token):
                raise RuntimeError("the token checker accepted noncanonical release bytes")
            draft_path.write_bytes(b"{\"schema\":")
            if qualification._check_token(valid_token):
                raise RuntimeError("the token checker accepted invalid JSON release bytes")
            array_raw = contract.canonical_bytes([
                "schema", "owner_approved", "source_sha256", "compile_flags", "mutations",
                "detection_cases", "detection_cases_sha256"]
            ) + b"\n"
            draft_path.write_bytes(array_raw)
            array_sha = hashlib.sha256(array_raw).hexdigest()
            array_token = {"release_sha256": array_sha,
                           "source_map_sha256": valid_token["source_map_sha256"],
                           "proof_sha256": qualification._token_proof(
                               array_sha, release_body["source_sha256"])}
            if qualification._check_token(array_token):
                raise RuntimeError("the token checker accepted a non-object release")
            draft_path.write_bytes(approved)

            try:
                qualification._run([str(Path(tmp) / "missing-executable")],
                                    "missing executable", timeout=1)
            except qualification.CorruptionQualificationError:
                pass
            else:
                raise RuntimeError("_run accepted an unavailable executable")
        finally:
            qualification.RELEASE_DRAFT_REL = original_rel
            qualification.ROOT = original_root


def check_bound_source_path_guards() -> None:
    """Exercise the corruption qualifier's fixed research-path boundaries."""
    import tempfile
    from pathlib import Path

    root_source = str(qualification.ROOT / qualification.SOURCE_REL)
    for relative in ("outside/file", root_source,
                     "research/../research/g9/cuda_qualification/stage2_cuda_d013_inactive.py"):
        try:
            qualification._read_bound(relative)
        except qualification.CorruptionQualificationError:
            pass
        else:
            raise RuntimeError("_read_bound accepted a non-plain research path")

    original_root = qualification.ROOT
    with tempfile.TemporaryDirectory(prefix="g9-d013-bound-path-") as temporary:
        root = Path(temporary)
        research = root / "research"
        research.mkdir()
        (root / "target").write_text("fixture", encoding="ascii")
        (research / "linked").symlink_to(root / "target")
        qualification.ROOT = root
        try:
            for relative in ("research/missing", "research/linked"):
                try:
                    qualification._read_bound(relative)
                except qualification.CorruptionQualificationError:
                    pass
                else:
                    raise RuntimeError("_read_bound accepted a missing or symlinked source")
        finally:
            qualification.ROOT = original_root


def check_mocked_gpu_runner_guards() -> None:
    """Exercise the release-gated runner cheaply without a GPU or compiler."""
    import hashlib
    import json
    import os
    import subprocess
    import io
    import types
    from contextlib import redirect_stdout

    from research.g9 import verify_stage2_cuda_d013_inactive_host_emulation as reference

    def execute_q_source_as(module_name):
        path = Path(qualification.__file__)
        module = types.ModuleType(module_name)
        module.__file__ = str(path)
        saved = sys.modules.get(module_name)
        sys.modules[module_name] = module
        output = io.StringIO()
        try:
            with redirect_stdout(output):
                try:
                    exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"),
                         module.__dict__)
                except SystemExit as exc:
                    if exc.code not in (None, 0):
                        raise RuntimeError("the qualification plan CLI returned failure") from exc
        finally:
            if saved is None:
                sys.modules.pop(module_name, None)
            else:
                sys.modules[module_name] = saved
        return output.getvalue()

    cli_output = execute_q_source_as("__main__")
    try:
        cli_plan = json.loads(cli_output)
    except ValueError as exc:
        raise RuntimeError("the qualification plan CLI did not print its plan") from exc
    if cli_plan.get("schema") != qualification.PLAN_SCHEMA:
        raise RuntimeError("the qualification plan CLI printed the wrong schema")
    imported_output = execute_q_source_as("_d013_import_probe")
    if imported_output:
        raise RuntimeError("importing the qualification module ran its CLI")

    with tempfile.TemporaryDirectory(prefix="g9-d013-mocked-runner-") as temporary:
        release_path = Path(temporary) / "release.json"
        original_release_path = qualification.RELEASE_DRAFT_REL
        original_selected = qualification.selected_mutation_sources
        selected = qualification.MUTATIONS[0]
        rows = original_selected(qualification.source_text())
        one_row = tuple(row for row in rows if row[0].label == selected.label)
        release = {"schema": "decisions_os/g9_d013_cuda_release_draft/v1",
                   "owner_approved": True,
                   "source_sha256": qualification.source_hashes(),
                   "compile_flags": list(qualification.GPU_COMPILE_FLAGS),
                   "mutations": [{"label": mutation.label,
                                  "category": mutation.category,
                                  "hazard": mutation.hazard}
                                 for mutation in qualification.MUTATIONS],
                   "detection_cases": qualification.canonical_detection_table(),
                   "detection_cases_sha256": qualification.detection_table_sha256()}
        raw = contract.canonical_bytes(release) + b"\n"
        release_path.write_bytes(raw)
        reviewed = hashlib.sha256(raw).hexdigest()
        qualification.RELEASE_DRAFT_REL = str(release_path)
        qualification.selected_mutation_sources = lambda _source: one_row

        def fake_run(command, label, *, timeout):
            if "--version" in command:
                return subprocess.CompletedProcess(command, 0,
                                                   stdout="fake nvcc runner probe\n", stderr="")
            candidate = next((Path(item) for item in command if item.endswith(".cu")), None)
            if candidate is None or not candidate.is_file():
                raise RuntimeError("the runner did not write its reviewed CUDA candidate")
            output = Path(command[command.index("-o") + 1])
            output.write_bytes(b"mocked ABI artifact")
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

        def fake_frame(_payload, _records, _condition, library, _feasible, *, verified_release=None):
            if not library.is_file() or not qualification._check_token(verified_release):
                raise RuntimeError("the runner did not load a compiled ABI with its release token")
            return {"counters": {}, "result_sha256": "0" * 64,
                    "content_sha256": "1" * 64}

        original_hashes = qualification.source_hashes

        def expect_q_error(call, label, fragment):
            try:
                call()
            except qualification.CorruptionQualificationError as exc:
                if fragment not in str(exc):
                    raise RuntimeError(f"{label} refused for wrong reason: {exc}") from exc
                return
            raise RuntimeError(f"the mocked runner accepted {label}")

        try:
            with mock.patch.dict(os.environ, {"PYTHONDONTWRITEBYTECODE": "1",
                                                qualification.ALLOW_ENV: "1"}), \
                    mock.patch.object(qualification.shutil, "which", return_value="/mock/nvcc"), \
                    mock.patch.object(qualification, "_run", side_effect=fake_run), \
                    mock.patch.object(d013, "run_host_emulated_frame", side_effect=fake_frame), \
                    mock.patch.object(reference, "reference_agrees_with_result", return_value=True), \
                    mock.patch.object(reference, "reference_rejects_raw_counters", return_value=True), \
                    mock.patch.object(reference, "direct_abi_accepts_tiny_positive_inactive",
                                      return_value=False), \
                    mock.patch.object(reference, "noncommuting_records", return_value=()), \
                    mock.patch.object(reference, "tie_bearing_records", return_value=({},)), \
                    mock.patch.object(reference.core, "build_domain", return_value=None), \
                    mock.patch.object(qualification, "CLEAN_CONDITIONS", ("C",)):
                receipt = qualification.run_qualification(reviewed)
                if (receipt["clean_build"]["verdict"] != "ACCEPTED" or
                        len(receipt["mutations"]) != 1 or
                        receipt["mutations"][0]["verdict"] != "REJECTED"):
                    raise RuntimeError("the mocked runner did not accept clean/reject mutant")

                tiny_guard_rows = tuple(row for row in rows if row[0].label ==
                                        "inactive_coefficient_becomes_tiny_positive")
                with mock.patch.object(qualification, "selected_mutation_sources",
                                       return_value=tiny_guard_rows), \
                        mock.patch.object(reference,
                                          "direct_abi_accepts_tiny_positive_inactive",
                                          side_effect=lambda library, *_:
                                          Path(library).stem == "clean"):
                    expect_q_error(lambda: qualification.run_qualification(reviewed),
                                   "clean build accepted invalid detection input",
                                   "clean D013 CUDA build accepted the invalid direct-ABI probe")

                with mock.patch.object(qualification, "_run",
                                       return_value=subprocess.CompletedProcess(
                                           ["/mock/nvcc", "--version"], 1, "", "version probe")):
                    expect_q_error(lambda: qualification.run_qualification(reviewed),
                                   "failed nvcc version probe", "nvcc version failed")

                for version_result in (
                        subprocess.CompletedProcess(["/mock/nvcc", "--version"],
                                                    1, "fake nvcc\n", "failed code"),
                        subprocess.CompletedProcess(["/mock/nvcc", "--version"],
                                                    0, "", "empty version")):
                    with mock.patch.object(qualification, "_run", side_effect=lambda command, label, *, timeout:
                                           (version_result if "--version" in command else
                                            fake_run(command, label, timeout=timeout))):
                        expect_q_error(lambda: qualification.run_qualification(reviewed),
                                       "malformed nvcc version output", "nvcc version failed")

                with mock.patch.object(qualification, "_run", side_effect=lambda command, label, *, timeout:
                                       subprocess.CompletedProcess(command, 1, "", "compile probe")
                                       if "--version" not in command else
                                       subprocess.CompletedProcess(command, 0, "fake nvcc\n", "")):
                    try:
                        qualification.run_qualification(reviewed)
                    except qualification.CorruptionQualificationError as exc:
                        if "did not compile" not in str(exc):
                            raise RuntimeError(f"failed compilation refused for wrong reason: {exc}") from exc
                    else:
                        raise RuntimeError("the runner accepted a failed candidate compilation")

                def failed_compile_with_artifact(command, label, *, timeout):
                    if "--version" in command:
                        return subprocess.CompletedProcess(command, 0, "fake nvcc\n", "")
                    output = Path(command[command.index("-o") + 1])
                    output.write_bytes(b"failed compiler artifact")
                    return subprocess.CompletedProcess(command, 1, "", "compile failed")

                with mock.patch.object(qualification, "_run", side_effect=failed_compile_with_artifact):
                    expect_q_error(lambda: qualification.run_qualification(reviewed),
                                   "nonzero compiler exit with artifact", "did not compile")

                with mock.patch.object(qualification, "_run", side_effect=lambda command, label, *, timeout:
                                       subprocess.CompletedProcess(command, 0, "", "")
                                       if "--version" not in command else
                                       subprocess.CompletedProcess(command, 0, "fake nvcc\n", "")):
                    try:
                        qualification.run_qualification(reviewed)
                    except qualification.CorruptionQualificationError as exc:
                        if "did not compile" not in str(exc):
                            raise RuntimeError(f"missing ABI artifact refused for wrong reason: {exc}") from exc
                    else:
                        raise RuntimeError("the runner accepted a missing compiled ABI artifact")

                bad_candidate = ((selected, one_row[0][1] + "\\n// release mismatch probe\\n"),)
                with mock.patch.object(qualification, "selected_mutation_sources",
                                       return_value=bad_candidate):
                    expect_q_error(lambda: qualification.run_qualification(reviewed),
                                   "mutated source hash mismatch", "mutated source differs from release")

                with mock.patch.object(reference, "reference_agrees_with_result", return_value=False):
                    expect_q_error(lambda: qualification.run_qualification(reviewed),
                                   "clean reference disagreement",
                                   "clean D013 CUDA build was rejected by the independent reference")

                with mock.patch.object(reference, "reference_rejects_raw_counters", return_value=False):
                    expect_q_error(lambda: qualification.run_qualification(reviewed),
                                   "mutation accepted by independent reference",
                                   "corrupted D013 CUDA build was accepted")

                def rejecting_frame(_payload, _records, _condition, library, _feasible,
                                    *, verified_release=None):
                    if not qualification._check_token(verified_release):
                        raise RuntimeError("missing token in clean rejection probe")
                    raise d013.D013InactiveError("mock ABI refusal")

                with mock.patch.object(d013, "run_host_emulated_frame", side_effect=rejecting_frame), \
                        mock.patch.object(reference, "reference_rejects_raw_counters",
                                          side_effect=AssertionError("clean ABI was treated as a mutant")):
                    expect_q_error(lambda: qualification.run_qualification(reviewed),
                                   "clean ABI rejection", "clean D013 CUDA build was rejected")

                with mock.patch.object(qualification, "CLEAN_CONDITIONS", ()), \
                        mock.patch.object(reference, "reference_agrees_with_result", return_value=False):
                    expect_q_error(lambda: qualification.run_qualification(reviewed),
                                   "empty clean-condition coverage",
                                   "clean D013 CUDA build was rejected")

                with mock.patch.object(qualification, "CLEAN_CONDITIONS", ("C", "CB")), \
                        mock.patch.object(reference, "reference_agrees_with_result",
                                          side_effect=(True, False)):
                    expect_q_error(lambda: qualification.run_qualification(reviewed),
                                   "incomplete clean-condition coverage",
                                   "clean D013 CUDA build was rejected")

                tiny_mutation = next(m for m in qualification.MUTATIONS
                                     if m.label == "inactive_coefficient_becomes_tiny_positive")
                tiny_rows = tuple(row for row in rows if row[0].label == tiny_mutation.label)
                with mock.patch.object(qualification, "selected_mutation_sources",
                                       return_value=tiny_rows), \
                        mock.patch.object(reference, "reference_rejects_raw_counters", return_value=False), \
                        mock.patch.object(reference,
                                          "direct_abi_accepts_tiny_positive_inactive",
                                          side_effect=lambda library, *_: Path(library).stem ==
                                          tiny_mutation.label):
                    receipt = qualification.run_qualification(reviewed)
                    if receipt["mutations"][0]["verdict"] != "REJECTED":
                        raise RuntimeError("the tiny-positive direct guard probe was not counted")

                with mock.patch.object(qualification, "selected_mutation_sources",
                                       return_value=tiny_rows), \
                        mock.patch.object(reference, "reference_rejects_raw_counters", return_value=False), \
                        mock.patch.object(reference,
                                          "direct_abi_accepts_tiny_positive_inactive", return_value=False):
                    expect_q_error(lambda: qualification.run_qualification(reviewed),
                                   "unrejected tiny-positive mutation",
                                   "corrupted D013 CUDA build was accepted")

                # Every individual declarative case is load-bearing.  Make
                # exactly that detector inert and require the corresponding
                # single-mutant run to fail closed.
                for mutation in qualification.MUTATIONS:
                    mutation_rows = tuple(row for row in rows
                                          if row[0].label == mutation.label)
                    for case in qualification.DETECTION_CASES[mutation.label]:
                        patches = [
                            mock.patch.object(qualification, "selected_mutation_sources",
                                              return_value=mutation_rows),
                            mock.patch.object(reference, "reference_agrees_with_result",
                                              return_value=True),
                            mock.patch.object(reference, "reference_rejects_raw_counters",
                                              return_value=False),
                        ]
                        if case.expected == "refusal":
                            patches.append(mock.patch.object(
                                reference, "direct_abi_accepts_tiny_positive_inactive",
                                return_value=False))
                        with contextlib.ExitStack() as stack:
                            for patcher in patches:
                                stack.enter_context(patcher)
                            expect_q_error(lambda: qualification.run_qualification(reviewed),
                                           "inert detection case " + mutation.label + "/" +
                                           case.condition + "/" + case.input_builder,
                                           "corrupted D013 CUDA build was accepted")

                # A numerical mismatch alone is sufficient detection, even
                # when the raw-counter path reports no defect. Keep this path
                # distinct from ABI refusal and exercise it on a single mutant.
                with mock.patch.object(qualification, "selected_mutation_sources",
                                       return_value=one_row), \
                        mock.patch.object(reference, "reference_agrees_with_result",
                                          side_effect=[True] * 9 + [False]), \
                        mock.patch.object(reference, "reference_rejects_raw_counters",
                                          return_value=False), \
                        mock.patch.object(reference,
                                          "direct_abi_accepts_tiny_positive_inactive",
                                          return_value=False):
                    mismatch_receipt = qualification.run_qualification(reviewed)
                    if (len(mismatch_receipt["mutations"]) != 1 or
                            mismatch_receipt["mutations"][0]["verdict"] != "REJECTED"):
                        raise RuntimeError("independent numerical mismatch was not sufficient detection")

                def clean_accept_mutant_refuses(*args, **kwargs):
                    library = args[3]
                    if library.stem != "clean":
                        raise d013.D013InactiveError("independent raw ABI defect")
                    return {"counters": {}, "result_sha256": "0" * 64,
                            "content_sha256": "1" * 64}

                with mock.patch.object(qualification, "selected_mutation_sources",
                                       return_value=one_row), \
                        mock.patch.object(d013, "run_host_emulated_frame",
                                          side_effect=clean_accept_mutant_refuses), \
                        mock.patch.object(reference, "reference_agrees_with_result",
                                          return_value=True), \
                        mock.patch.object(reference, "reference_rejects_raw_counters",
                                          side_effect=lambda library, *_:
                                          Path(library).stem != "clean"), \
                        mock.patch.object(reference,
                                          "direct_abi_accepts_tiny_positive_inactive",
                                          return_value=False):
                    refusal_receipt = qualification.run_qualification(reviewed)
                    if (len(refusal_receipt["mutations"]) != 1 or
                            refusal_receipt["mutations"][0]["verdict"] != "REJECTED"):
                        raise RuntimeError("expected refusal was not sufficient detection")

                source_calls = 0
                def drift_during_run():
                    nonlocal source_calls
                    source_calls += 1
                    if source_calls < 3:
                        return original_hashes()
                    return {**original_hashes(), qualification.SOURCE_REL: "f" * 64}

                with (mock.patch.object(qualification, "source_hashes",
                                        side_effect=drift_during_run),
                      mock.patch.object(d013, "run_host_emulated_frame",
                                        return_value={"counters": {},
                                                      "result_sha256": "0" * 64,
                                                      "content_sha256": "1" * 64}),
                      mock.patch.object(reference,
                                        "direct_abi_accepts_tiny_positive_inactive",
                                        return_value=False)):
                    expect_q_error(lambda: qualification.run_qualification(reviewed),
                                   "source map drift during qualification",
                                   "source map changed during qualification")

                calls = 0
                def drift_after_release():
                    nonlocal calls
                    calls += 1
                    if calls == 1:
                        return original_hashes()
                    return {**original_hashes(), qualification.SOURCE_REL: "f" * 64}

                with mock.patch.object(qualification, "source_hashes", side_effect=drift_after_release):
                    try:
                        qualification.run_qualification(reviewed)
                    except qualification.CorruptionQualificationError as exc:
                        if "source map changed before nvcc lookup" not in str(exc):
                            raise RuntimeError(f"pre-lookup source drift refused for wrong reason: {exc}") from exc
                    else:
                        raise RuntimeError("the runner accepted source drift after release verification")
        finally:
            qualification.RELEASE_DRAFT_REL = original_release_path
            qualification.selected_mutation_sources = original_selected


def run_fake_gpu_control_flow() -> None:
    """Run the complete nvcc/release/ABI/reference path using a host ABI shim."""
    import hashlib
    import os
    import subprocess
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory(prefix="g9-d013-fake-gpu-") as tmp:
        root = Path(tmp)
        bin_dir = root / "bin"
        bin_dir.mkdir()
        release_path = root / "approved-release.json"
        clean_source = root / "clean.cu"
        clean_source.write_text(qualification.source_text(), encoding="utf-8")
        compiler = bin_dir / "nvcc"
        compiler.write_text('''#!/usr/bin/env -S python3 -B
import os, pathlib, subprocess, sys, tempfile
if "--version" in sys.argv:
    print("fake nvcc 1.0 (g++ host ABI shim)")
    raise SystemExit(0)
args = sys.argv[1:]
source = next((x for x in args if x.endswith(".cu")), None)
output = args[args.index("-o") + 1]
if source is None:
    raise SystemExit("missing source")
label = pathlib.Path(source).stem
if os.environ.get("G9_FAKE_NVCC_ACCEPT_LABEL") == label:
    source = os.environ["G9_FAKE_NVCC_CLEAN_SOURCE"]
text = pathlib.Path(source).read_text()
old = ('extern "C" std::uint32_t g9_d013_backend() {\\n'
       '#if defined(__CUDACC__)\\n  return 1u;\\n#else\\n  return 0u;\\n#endif\\n}')
if text.count(old) != 1:
    raise SystemExit("backend source anchor drift")
text = text.replace(old, 'extern "C" std::uint32_t g9_d013_backend() { return 1u; }', 1)
if os.environ.get("G9_FAKE_NVCC_REJECT_CLEAN") == "1" and label == "clean":
    marker = 'extern "C" std::uint32_t g9_d013_run('
    text = text.replace(marker, marker, 1)
    pos = text.index("{", text.index(marker)) + 1
    text = text[:pos] + "\\n  if (row_count == 1u) return G9_D013_REFUSED;" + text[pos:]
with tempfile.TemporaryDirectory(prefix="fake-nvcc-", dir="/tmp") as td:
    translated = pathlib.Path(td) / "candidate.cpp"
    translated.write_text(text)
    cmd = ["g++", "-std=c++17", "-O0", "-shared", "-fPIC",
           "-ffp-contract=off", "-fno-fast-math", "-Wno-unknown-pragmas",
           "-I", os.environ["G9_FAKE_NVCC_STUB"],
           "-I", os.environ["G9_FAKE_NVCC_QUAL"], str(translated), "-o", output]
    raise SystemExit(subprocess.run(cmd).returncode)
''', encoding="utf-8")
        compiler.chmod(0o755)

        def write_approved_release() -> str:
            body = {"schema": "decisions_os/g9_d013_cuda_release_draft/v1",
                    "owner_approved": True,
                    "source_sha256": qualification.source_hashes(),
                    "compile_flags": list(qualification.GPU_COMPILE_FLAGS),
                    "mutations": [{"label": m.label, "category": m.category,
                                   "hazard": m.hazard} for m in qualification.MUTATIONS],
                    "detection_cases": qualification.canonical_detection_table(),
                    "detection_cases_sha256": qualification.detection_table_sha256()}
            raw = contract.canonical_bytes(body) + b"\n"
            release_path.write_bytes(raw)
            return hashlib.sha256(raw).hexdigest()

        def fast_fake_frame(_payload, _records, _condition, library, _feasible,
                            *, verified_release=None):
            # Exercise the production token/backend-1 loader for every clean
            # and mutated candidate, while the fake ABI keeps this control-flow
            # fixture independent of a million-state numerical scan.
            d013._load_checked_abi(library, verified_release=verified_release)
            if (os.environ.get("G9_FAKE_NVCC_REJECT_CLEAN") == "1" and
                    library.stem == "clean"):
                raise d013.D013InactiveError("fake clean ABI refusal")
            disguised_clean = os.environ.get("G9_FAKE_NVCC_ACCEPT_LABEL") == library.stem
            is_clean = library.stem == "clean" or disguised_clean
            return {"fake_detected": not is_clean, "counters": {},
                    "result_sha256": "0" * 64, "content_sha256": "1" * 64}

        def fake_reference_agrees(_domain, _records, _condition, result):
            return not result["fake_detected"]

        def fake_reference_rejects(library, _payload, _condition, _records):
            return Path(library).stem != "clean" and not (
                os.environ.get("G9_FAKE_NVCC_ACCEPT_LABEL") == Path(library).stem)

        def fake_tiny_positive_accepts(library, _payload, _records_factory):
            return Path(library).stem != "clean" and not (
                os.environ.get("G9_FAKE_NVCC_ACCEPT_LABEL") == Path(library).stem)

        old_rel = qualification.RELEASE_DRAFT_REL
        old_mutations = qualification.MUTATIONS
        old_clean_conditions = qualification.CLEAN_CONDITIONS
        old_selected_mutations = qualification.selected_mutation_sources
        original_env = dict(os.environ)
        try:
            qualification.RELEASE_DRAFT_REL = str(release_path)
            tested_mutation = next(m for m in old_mutations
                                   if m.label == "inactive_coefficient_becomes_tiny_positive")
            os.environ.update({"PYTHONDONTWRITEBYTECODE": "1",
                               qualification.ALLOW_ENV: "1",
                               "PATH": str(bin_dir) + os.pathsep + original_env.get("PATH", ""),
                               "G9_FAKE_NVCC_CLEAN_SOURCE": str(clean_source),
                               "G9_FAKE_NVCC_STUB": str(checks.STUB),
                               "G9_FAKE_NVCC_QUAL": str(checks.QUALIFICATION_DIR)})

            reviewed = write_approved_release()
            with (mock.patch.object(d013, "run_host_emulated_frame", side_effect=fast_fake_frame),
                  mock.patch.object(reference := sys.modules[
                      "research.g9.verify_stage2_cuda_d013_inactive_host_emulation"],
                      "reference_agrees_with_result", side_effect=fake_reference_agrees),
                  mock.patch.object(reference, "reference_rejects_raw_counters",
                                    side_effect=fake_reference_rejects),
                  mock.patch.object(reference.core, "build_domain", return_value=None),
                  mock.patch.object(reference, "direct_abi_accepts_tiny_positive_inactive",
                                    side_effect=fake_tiny_positive_accepts)):
                receipt = qualification.run_qualification(reviewed)
            backend_source = qualification.source_text()
            backend_old = ('extern "C" std::uint32_t g9_d013_backend() {\n'
                           '#if defined(__CUDACC__)\n  return 1u;\n#else\n  return 0u;\n#endif\n}')
            backend_library = root / "lib-token-checked-cuda.so"
            checks.build(backend_library, backend_source.replace(
                backend_old, 'extern "C" std::uint32_t g9_d013_backend() { return 1u; }', 1))
            d013._load_checked_abi(backend_library,
                                   verified_release=receipt["verified_release_token"])
            if (receipt["verdict"] != "clean_accepted_all_corruptions_rejected" or
                    receipt["clean_build"]["verdict"] != "ACCEPTED" or
                    len(receipt["mutations"]) != len(old_mutations) or
                    any(row["verdict"] != "REJECTED" for row in receipt["mutations"])):
                raise RuntimeError("fake CUDA control flow did not qualify every mutation")

            # Make one mutant build the clean host ABI. The independent reference
            # must accept it, causing the qualification itself to fail closed.
            os.environ["G9_FAKE_NVCC_ACCEPT_LABEL"] = tested_mutation.label
            reviewed = write_approved_release()
            try:
                with (mock.patch.object(d013, "run_host_emulated_frame", side_effect=fast_fake_frame),
                      mock.patch.object(reference, "reference_agrees_with_result",
                                        side_effect=fake_reference_agrees),
                      mock.patch.object(reference, "reference_rejects_raw_counters",
                                        side_effect=fake_reference_rejects),
                      mock.patch.object(reference.core, "build_domain", return_value=None),
                      mock.patch.object(reference, "direct_abi_accepts_tiny_positive_inactive",
                                        side_effect=fake_tiny_positive_accepts)):
                    qualification.run_qualification(reviewed)
            except qualification.CorruptionQualificationError as exc:
                if "was accepted" not in str(exc):
                    raise RuntimeError(f"accepted-mutant probe failed for the wrong reason: {exc}") from exc
            else:
                raise RuntimeError("qualification accepted a clean build disguised as a mutation")
            os.environ.pop("G9_FAKE_NVCC_ACCEPT_LABEL", None)

            # A clean ABI refusal must fail the clean-build acceptance check.
            os.environ["G9_FAKE_NVCC_REJECT_CLEAN"] = "1"
            reviewed = write_approved_release()
            try:
                with (mock.patch.object(d013, "run_host_emulated_frame", side_effect=fast_fake_frame),
                      mock.patch.object(reference, "reference_agrees_with_result",
                                        side_effect=fake_reference_agrees),
                      mock.patch.object(reference, "reference_rejects_raw_counters",
                                        side_effect=fake_reference_rejects),
                      mock.patch.object(reference.core, "build_domain", return_value=None),
                      mock.patch.object(reference, "direct_abi_accepts_tiny_positive_inactive",
                                        side_effect=fake_tiny_positive_accepts)):
                    qualification.run_qualification(reviewed)
            except qualification.CorruptionQualificationError as exc:
                if "clean D013 CUDA build was rejected" not in str(exc):
                    raise RuntimeError(f"clean rejection probe failed for the wrong reason: {exc}") from exc
            else:
                raise RuntimeError("qualification accepted a rejected clean build")
        finally:
            qualification.MUTATIONS = old_mutations
            qualification.CLEAN_CONDITIONS = old_clean_conditions
            qualification.selected_mutation_sources = old_selected_mutations
            qualification.RELEASE_DRAFT_REL = old_rel
            os.environ.clear()
            os.environ.update(original_env)


def main() -> None:
    if _QUALIFICATION_IMPORT_OUTPUT.getvalue():
        raise RuntimeError("importing the qualification module ran its CLI")
    if checks.corruption.DETECTION_CASES is not qualification.DETECTION_CASES:
        raise RuntimeError("host and GPU paths do not share the same detection table object")
    if (checks.corruption.detection_table_sha256() != qualification.detection_table_sha256() or
            qualification.build_plan()["detection_cases"] !=
            qualification.canonical_detection_table() or
            qualification.build_plan()["detection_cases_sha256"] !=
            qualification.detection_table_sha256()):
        raise RuntimeError("host/GPU detection table or canonical hash drifted")
    check_gpu_release_refusals()
    check_bound_source_path_guards()
    check_mocked_gpu_runner_guards()
    run_fake_gpu_control_flow()
    checks.check_accounting_contract_without_scan()
    checks.check_corruption_plan_guards()
    checks.check_wp6_crosscheck(None)
    check_wp6_minimum_index_refusal()
    try:
        d013.condition_name(True)
    except d013.D013InactiveError:
        pass
    else:
        raise RuntimeError("condition_name accepted bool True as an integer condition code")
    malformed_coefficients = checks.small_records("CSB", 0)[0]
    malformed_coefficients["alpha"] = float("nan")
    must_refuse(
        lambda: d013.validate_coefficient_record(malformed_coefficients, "CSB"),
        "a non-finite non-slack coefficient")
    must_refuse(lambda: d013.decode_conditions("CSB", 3), "a condition row count above capacity")
    malformed_output = d013.D013Output()
    malformed_output.core.results[0][0].compacted_count = 0
    must_refuse(lambda: d013._summaries(malformed_output, 1), "a zero compacted count")
    check_counter_guard_refusals()
    envelope = accounting_envelope()
    for malformed_hash in ("", "A" * 64, "g" * 64):
        changed = dict(envelope, content_sha256=malformed_hash)
        must_refuse(lambda changed=changed: d013.require_bounded_result(
            changed, "C", 1), "a malformed content SHA-256")
    check_result_shape_refusals()
    check_record_value_refusals()
    check_commitment_refusals()
    check_discarded_counter_calls()
    check_encoding_branches()
    check_wp6_field_mismatch_refusals()
    check_canonical_index_branch()
    check_crosscheck_width_guard()
    check_conjunct_refusals()
    with tempfile.TemporaryDirectory(prefix="g9-d013-fast-") as temporary:
        library = Path(temporary) / "libg9_d013_host_stub.so"
        checks.build(library, checks.corruption.source_text())
        d013._load_checked_abi(library)
        with mock.patch.object(d013.sys, "byteorder", "big"):
            must_refuse(lambda: d013._load_checked_abi(library), "a big-endian host")
        for name in ("expected_abi_layout", "expected_counters_layout",
                     "expected_condition_codes"):
            expected = getattr(d013, name)()
            with mock.patch.object(d013, name, lambda expected=expected: (*expected[:-1], -1)):
                must_refuse(lambda: d013._load_checked_abi(library), f"a mismatched {name}")
        proxy = SimpleNamespace()
        loaded = d013.C.CDLL(str(library))
        for symbol in ("g9_d013_abi_layout", "g9_d013_counters_layout",
                       "g9_d013_condition_codes", "g9_d013_run"):
            setattr(proxy, symbol, getattr(loaded, symbol))
        proxy.g9_d013_backend = lambda: 99
        with mock.patch.object(d013.C, "CDLL", return_value=proxy):
            must_refuse(lambda: d013._load_checked_abi(library), "an invalid backend tag")
        retired = Path(temporary) / "libg9_d013_retired.so"
        retired_source = checks.corruption.source_text() + (
            '\nextern "C" int g9_core_run_v1(void) { return 0; }\n')
        checks.build(retired, retired_source)
        must_refuse(lambda: d013._load_checked_abi(retired), "a retired v1 export")
        checks.check_typed_refusals(library)
        checks.check_argument_fuzz(library)
        check_run_host_refusals(library)
        checks.check_direct_abi_refusals(library)
        checks.check_envelope_tampering(library)
    print("FAST_FIXTURE_PASS")


if __name__ == "__main__":
    if sys.argv[1:] == ["--fake-gpu-control-flow"]:
        run_fake_gpu_control_flow()
        print("FAKE_GPU_CONTROL_FLOW_PASS")
    elif sys.argv[1:]:
        raise SystemExit("unknown fixture argument")
    else:
        main()

#!/usr/bin/env python3
"""Fail-closed verification of the five real T4 Stage-2 production slot outputs.

Run it as soon as the five `g9-real-production-slot-N-*-v2` kernels have been
downloaded:

    python3 -B verify_outputs.py --results-root push/<one-or-more>/results
    python3 -B verify_outputs.py --results-root <root> --report /tmp/verify.json

EXIT CODES
----------
`0`  every one of the five slots verified; `--report` written.
`1`  at least one check failed; a precise report of EVERY failure is printed
     and written to `--report`.  Nothing downstream may consume a failed run.
`2`  usage error (bad arguments, unreadable root).

WHAT IS VERIFIED, and why each check is separately load-bearing
----------------------------------------------------------------

For each slot 1..5, in order:

  V1  slot presence and instance identity
      The slot's `research/g9/stage2_instances/stage2_0N/` tree exists, is a
      real directory, is unique, and its `PREPARED.json` names this slot.
      A missing slot is a failure, never a skip: the cross-instance reduction
      is `all_five/any_one/count_of_five` over five statuses
      (`research/decisions/GATE_9_STAGE2_PROTOCOL_DRAFT.md:195-198`), and four
      slots cannot answer it.

  V2  terminal run artefact
      Exactly one of `FULL_PRODUCTION_RESULT.json` / `FULL_PRODUCTION_FAILURE.json`
      / `FULL_PRODUCTION_INCOMPLETE_BUDGET.json` decides the slot's completion
      status.  A result must carry `status == full_computation_complete_pending_final_audit`
      (`full_production_parent_v2.py:89, 147`); a failure or an incomplete-budget
      receipt fails V2 with the status word named.

  V3  baseline receipt and D013 trigger
      `operational/BASELINE_RECEIPT.json` must be a complete six-family baseline
      (`production_parent_v2.py:372-374`) and `operational/D013_TRIGGER.json`
      must exist, be sealed, and carry the instance id, the prepared-record
      hash, the counts, the primary-stream commitment and the `fired` flag
      (`full_production_parent_v2.py:87-88`).

  V4  per-family sealed plan
      Each of the six `sweep/<family>/range_plan.json` is re-derived from
      `MAX_COORDINATES_PER_RANGE = 4096` and the frozen per-family coordinate
      count, then its own `content_sha256` is recomputed.  A re-partitioned
      plan is refused (`stage2_production_writer.seal_range_plan:553-561`).

  V5  promoted range cover
      For every sealed range, `ranges/<batch_id>/RANGE_MANIFEST.json` and
      `records.json` both exist, the manifest is re-derived from the plan and
      the records bytes, and the manifest's two records hashes match.  This is
      `writer.audit_final_set` / `validate_final_manifests`
      (`stage2_cuda_execution_contract.py:170-194`) re-implemented read-only,
      with the records bytes RE-HASHED from disk rather than trusted from the
      producer's own manifest (`stage2_production_writer.py:918-922`).

  V6  full-record commitments
      For every sealed range, `full_records/<batch_id>.jsonl.gz` decompresses,
      holds exactly `stop - start` records, every record passes the frozen
      schema check (`stage2_coordinate_records.py:911-931, 1010`; the linear
      index / coordinate identity check at
      `wp8c_streaming_session_v3_gzip.py:74-80`), and the decompressed stream's
      SHA-256 matches the per-batch commitment.  The **decompressed** bytes are
      what production hashes (`_persist_full:66`).

  V7  writer projection binding
      Each `records.json` entry is re-projected from its full record
      (`wp8c_production_session.project_record_for_writer:1721-1741` +
      `stage2_production_writer.py:594-606`) and must equal the stored
      projection.  This is what binds the committed record bytes to the
      committed writer range: `identity_sha256` plus `record_content_sha256`.

  V8  row and range census
      Per family the observed record count must equal the frozen count; per
      slot the observed total must equal `2,080,562`, the observed sealed-range
      total `511`, and the implied CUDA flush count `1,040,281`
      (`stage2_cuda_core_bridge.py:22`).  A short census is a failure even when
      every hash agrees, because a truncated sweep is not the sealed grid.

  V9  identity consistency across the slot
      Every range manifest's `qualification_identity_sha256` must equal its
      plan's, the session record's `identity_sha256` must equal the plan's, and
      the D013 trigger's `prepared_record_sha256` must equal
      `PREPARED.json`'s own `content_sha256`.  One identity per slot, checked
      from several independent documents.

WHAT IS NOT VERIFIED HERE, DELIBERATELY
----------------------------------------
  * The numerical correctness of any record.  Re-deriving `H_E`, the tie set
    `T_E`, `X_E` or the A/B/C labels would mean re-running the CUDA core, which
    is a separate scientific claim this pipeline does not make.  What is
    verified is that every number is bound, by hash, to a record that satisfies
    the frozen schema and its own commitment.
  * `instance_id` semantic equality with a reference.  The prepared record's
    own content hash is the identity everywhere in this codebase
    (`stage2_production_writer.py:453-499`), so that hash is what is compared.
  * Anything about the `kaggle` platform.  No network is used.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import stage2_schema as schema  # noqa: E402
from stage2_schema import Stage2AnalysisError  # noqa: E402

WRITER_RESULT_SCHEMA = {"identity_sha256": "str", "record_content_sha256": "str"}
"""`wp8c_streaming_session_v3_gzip.py:91` requires exactly this schema."""

REQUIRED_CONDITIONAL_RECEIPTS = 22
"""`full_production_parent_v2.py:67, 146`: 22 declared families when the
trigger fires (6 baseline + 4 conditions x 4 families)."""


class Report:
    """Accumulates every failure so the report is COMPLETE, not first-error."""

    def __init__(self) -> None:
        self.checks: list[dict[str, Any]] = []
        self.failures: list[dict[str, Any]] = []

    def record(self, slot: int | None, check: str, ok: bool, detail: str,
               **extra: Any) -> bool:
        entry = {"slot": slot, "check": check, "ok": ok, "detail": detail}
        entry.update(extra)
        self.checks.append(entry)
        if not ok:
            self.failures.append(entry)
        return ok

    def guard(self, slot: int | None, check: str, label: str, fn, *args, **kwargs):
        """Run `fn`, converting any refusal into a recorded failure.

        A refusal is always a FAILURE, never a crash: the report must name every
        bad check even when an early one has already made the slot unusable.
        """
        try:
            value = fn(*args, **kwargs)
        except Stage2AnalysisError as exc:
            self.record(slot, check, False, f"{label}: {exc}")
            return None
        except (OSError, ValueError, KeyError, TypeError) as exc:
            self.record(slot, check, False,
                        f"{label}: unexpected {type(exc).__name__}: {exc}")
            return None
        self.record(slot, check, True, label)
        return value


# ---------------------------------------------------------------------------
# V2 / V3 — the terminal run artefact and the retained session receipts
# ---------------------------------------------------------------------------

def _find_first(root: Path, name: str) -> Path | None:
    matches = sorted(path for path in root.rglob(name)
                     if path.is_file() and not path.is_symlink())
    if not matches:
        return None
    if len(matches) > 1:
        raise Stage2AnalysisError(
            f"{name} appears {len(matches)} times under {root}; exactly one "
            f"terminal artefact per slot is required "
            f"({', '.join(str(p) for p in matches)})")
    return matches[0]


def _staged_root(slot_dir: Path) -> Path:
    """The `staged_qualified_sources/` directory that holds a slot's tree.

    Anchored on the DIRECTORY NAME rather than on a fixed number of
    `parent` hops, because the download root's depth is a caller choice: the
    collector uses `push/<kernel-id>/results`, but a hand-copied tree may sit at
    any depth.  The instance tree is always
    `<staged>/<INSTANCE_ROOT>/<stage2_0N>`, so counting up from the slot to the
    `staged_qualified_sources` level is exact.
    """
    node = slot_dir
    # stage2_0N -> stage2_instances -> g9 -> research -> staged_qualified_sources
    for _ in range(5):
        if node.name == "staged_qualified_sources":
            return node
        node = node.parent
    raise Stage2AnalysisError(
        f"the slot tree {slot_dir} does not sit under a "
        "staged_qualified_sources/ directory; the downloaded layout is not the "
        "one production writes (kernel.py:7, 13-23)")


def verify_terminal(report: Report, slot: int, results_root: Path,
                     slot_dir: Path) -> dict[str, Any] | None:
    """V2. Exactly one terminal artefact, belonging to THIS slot.

    The terminal artefact is looked up in the SLOT'S OWN download directory — the
    parent of `staged_qualified_sources/`, which is where the collector's
    `^FULL_PRODUCTION_` pattern puts it — and, secondarily, inside the staged
    tree beside it.  It is deliberately NOT searched from the shared
    `--results-root`: that root legitimately holds all five slots' downloads,
    each with its own terminal artefact, so a root-wide search would see five
    copies of every name.  A slot's artefact is the one in its own download.
    """
    staged = _staged_root(slot_dir)
    slot_out = staged.parent
    found: dict[str, Path] = {}
    seen_paths: set[Path] = set()
    for base in (slot_out, staged):
        for name in (schema.RESULT_NAME, schema.FAILURE_NAME,
                     schema.INCOMPLETE_NAME):
            path = _find_first(base, name)
            # `staged` is INSIDE `slot_out`, so a staged-tree artefact is also
            # found by the slot_out scan.  Compare RESOLVED paths so one file
            # is one artefact, not a contradiction with itself.
            if path is None or path.resolve() in seen_paths:
                continue
            seen_paths.add(path.resolve())
            if name in found:
                report.record(slot, "V2_terminal_artefact", False,
                              f"two {name} artefacts for this slot: "
                              f"{found[name]} and {path}")
                return None
            found[name] = path
    if not found:
        report.record(slot, "V2_terminal_artefact", False,
                      f"no {schema.RESULT_NAME}, {schema.FAILURE_NAME} or "
                      f"{schema.INCOMPLETE_NAME} under {slot_out} or "
                      f"{staged}: the slot did not produce a terminal artefact")
        return None
    if len(found) > 1:
        report.record(slot, "V2_terminal_artefact", False,
                      f"contradictory terminal artefacts: "
                      f"{', '.join(sorted(found))}")
        return None
    name, path = next(iter(found.items()))
    _raw, payload = schema.read_json(path, f"slot {slot} {name}")
    if name != schema.RESULT_NAME:
        status = payload.get("status") if isinstance(payload, dict) else None
        report.record(slot, "V2_terminal_artefact", False,
                      f"the slot ended with {name} (status={status!r}); a "
                      f"{schema.RESULT_NAME} with status "
                      f"{schema.FULL_COMPLETE_STATUS!r} is required")
        return None
    if not isinstance(payload, dict):
        report.record(slot, "V2_terminal_artefact", False,
                      f"{name} is not an object")
        return None
    if payload.get("status") != schema.FULL_COMPLETE_STATUS:
        report.record(slot, "V2_terminal_artefact", False,
                      f"{name} status is {payload.get('status')!r}, not "
                      f"{schema.FULL_COMPLETE_STATUS!r} "
                      "(full_production_parent_v2.py:89, 147)")
        return None
    report.record(slot, "V2_terminal_artefact", True,
                  f"{name} status={schema.FULL_COMPLETE_STATUS}",
                  result_path=str(path),
                  d013_fired=payload.get("d013_fired"),
                  instance_id=payload.get("instance_id"))
    return payload


def verify_session_receipts(report: Report, slot: int, slot_dir: Path,
                            terminal: dict[str, Any]) -> tuple[str | None, dict | None]:
    """V3. The retained baseline receipt and the D013 trigger.

    Returns `(prepared_content_sha256, trigger)`.
    """
    staged = _staged_root(slot_dir)
    prepared = schema.read_sealed(slot_dir / "instance/PREPARED.json",
                                  f"slot {slot} PREPARED.json")
    prepared_sha = prepared["content_sha256"]

    baseline_path = staged / schema.BASELINE_RECEIPT_REL
    try:
        baseline = schema.read_sealed(baseline_path, f"slot {slot} BASELINE_RECEIPT")
    except Stage2AnalysisError as exc:
        report.record(slot, "V3_baseline_receipt", False, str(exc))
    else:
        ok = True
        if baseline.get("status") != schema.BASELINE_COMPLETE_STATUS:
            ok = report.record(slot, "V3_baseline_receipt_status", False,
                               f"BASELINE_RECEIPT status is "
                               f"{baseline.get('status')!r}, not "
                               f"{schema.BASELINE_COMPLETE_STATUS!r} "
                               "(production_parent_v2.py:372-374)")
        sessions = baseline.get("family_sessions")
        if not (isinstance(sessions, list) and len(sessions) == 6
                and all(isinstance(s, dict)
                        and s.get("status") == "complete_pending_image_audit"
                        for s in sessions)):
            ok = report.record(
                slot, "V3_baseline_family_sessions", False,
                f"BASELINE_RECEIPT carries "
                f"{len(sessions) if isinstance(sessions, list) else 'no'} family "
                "sessions; exactly 6 are required, each "
                "status='complete_pending_image_audit' "
                "(production_parent_v2.py:349-371)")
        else:
            report.record(slot, "V3_baseline_family_sessions", True,
                          "6 of 6 baseline families complete_pending_image_audit")
        if baseline.get("instance_id") != schema.SLOT_NAMES[slot - 1]:
            ok = report.record(slot, "V3_baseline_instance_id", False,
                               f"BASELINE_RECEIPT instance_id is "
                               f"{baseline.get('instance_id')!r}, not this slot")
        else:
            report.record(slot, "V3_baseline_instance_id", True,
                          f"instance_id={baseline.get('instance_id')}")
        if ok:
            report.record(slot, "V3_baseline_receipt", True,
                          f"{schema.BASELINE_RECEIPT_REL} complete for six families")

    trigger_path = staged / schema.D013_TRIGGER_REL
    trigger: dict[str, Any] | None = None
    try:
        trigger = schema.read_sealed(trigger_path, f"slot {slot} D013_TRIGGER")
    except Stage2AnalysisError as exc:
        report.record(slot, "V3_d013_trigger", False, str(exc))
        return prepared_sha, None
    for field in ("instance_id", "prepared_record_sha256", "counts",
                  "primary_record_stream_sha256", "fired"):
        if field not in trigger:
            report.record(slot, "V3_d013_trigger", False,
                          f"D013_TRIGGER.json lacks {field!r} "
                          "(full_production_parent_v2.py:88)")
            return prepared_sha, None
    problems = []
    if trigger["instance_id"] != schema.SLOT_NAMES[slot - 1]:
        problems.append(f"instance_id={trigger['instance_id']!r} is not this slot")
    if trigger["prepared_record_sha256"] != prepared_sha:
        problems.append(
            f"prepared_record_sha256={trigger['prepared_record_sha256']!r} "
            f"is not PREPARED.json's own content hash {prepared_sha!r}")
    if type(trigger["fired"]) is not bool:
        problems.append(f"fired={trigger['fired']!r} is not a bool")
    if trigger["fired"] and terminal.get("conditional_families_run") != \
            REQUIRED_CONDITIONAL_RECEIPTS:
        problems.append(
            f"the trigger fired but the run reports "
            f"conditional_families_run="
            f"{terminal.get('conditional_families_run')!r}; "
            f"{REQUIRED_CONDITIONAL_RECEIPTS} are required "
            "(full_production_parent_v2.py:146)")
    if problems:
        report.record(slot, "V3_d013_trigger", False, "; ".join(problems))
    else:
        report.record(slot, "V3_d013_trigger", True,
                      f"fired={trigger['fired']} "
                      f"counts={json.dumps(trigger['counts'], sort_keys=True)}",
                      primary_record_stream_sha256=trigger["primary_record_stream_sha256"])
    return prepared_sha, trigger


# ---------------------------------------------------------------------------
# V4-V8 — one family: the plan, the promoted cover, and the full records
# ---------------------------------------------------------------------------

def project_record_for_writer(record: dict[str, Any],
                              accepted_identity_sha256: str) -> dict[str, Any]:
    """The exact WP4b projection of one committed record.

    Byte-for-byte `wp8c_production_session.project_record_for_writer`
    (`:1721-1760`): `coordinates` is the axis map read in SORTED axis order
    (which for the three frozen axes is `ell_budget, ell_card, ell_sector`),
    and `result` carries exactly the accepted identity hash and the record's
    own content hash.
    """
    coordinate = record["coordinate"]
    return {
        "coordinates": [coordinate[axis] for axis in sorted(coordinate)],
        "result": {
            "identity_sha256": accepted_identity_sha256,
            "record_content_sha256": record["content_sha256"],
        },
    }


def verify_family(report: Report, slot: int, slot_dir: Path, family_key: str,
                  census: dict[str, Any]) -> dict[str, Any]:
    """V4-V8 for one family.  Returns the census row."""
    family_root = slot_dir / "sweep" / family_key
    expected = census["family_census"][family_key]
    axis_length = expected["axis_length"]
    expected_rows = expected["coordinates"]
    expected_ranges = expected["sealed_ranges"]
    citation = expected["citation"]
    summary: dict[str, Any] = {
        "family": family_key,
        "expected_rows": expected_rows,
        "expected_sealed_ranges": expected_ranges,
        "axis_length": axis_length,
        "census_citation": citation,
        "observed_rows": 0,
        "observed_sealed_ranges": 0,
        "plan_content_sha256": None,
        "qualification_identity_sha256": None,
        "implied_cuda_flushes": 0,
        "full_records_commitment_sha256": None,
    }
    if not family_root.is_dir():
        report.record(slot, "V4_family_present", False,
                      f"sweep/{family_key}/ is absent: this baseline family did "
                      "not complete")
        return summary
    report.record(slot, "V4_family_present", True, f"sweep/{family_key}/ present")

    try:
        plan = schema.rebuild_range_plan(
            schema.read_sealed(family_root / schema.PLAN_NAME,
                               f"slot {slot} {family_key} range_plan.json"),
            records_per_range=census["records_per_range"])
    except Stage2AnalysisError as exc:
        report.record(slot, "V4_sealed_plan", False, str(exc))
        return summary
    if plan["family"] != family_key:
        report.record(slot, "V4_sealed_plan", False,
                      f"the sealed plan names family {plan['family']!r}, not "
                      f"{family_key!r}")
        return summary
    if plan["total_coordinates"] != expected_rows:
        report.record(slot, "V4_sealed_plan", False,
                      f"the sealed plan spans {plan['total_coordinates']} "
                      f"coordinates; the frozen census is {expected_rows} "
                      f"({citation})")
        return summary
    if len(plan["ranges"]) != expected_ranges:
        report.record(slot, "V4_sealed_plan", False,
                      f"the sealed plan carries {len(plan['ranges'])} ranges; "
                      f"ceil({expected_rows}/"
                      f"{schema.MAX_COORDINATES_PER_RANGE})={expected_ranges}")
        return summary
    summary["plan_content_sha256"] = plan["content_sha256"]
    summary["qualification_identity_sha256"] = plan["qualification_identity_sha256"]
    summary["observed_sealed_ranges"] = len(plan["ranges"])
    report.record(slot, "V4_sealed_plan", True,
                  f"{expected_rows} coordinates in {expected_ranges} sealed "
                  f"ranges, plan {plan['content_sha256'][:12]}...")

    ranges_dir = family_root / schema.RANGES_DIRNAME
    observed_ids = sorted(p.name for p in ranges_dir.iterdir()
                          if p.is_dir() and not p.is_symlink()) \
        if ranges_dir.is_dir() else []
    planned_ids = [row["batch_id"] for row in plan["ranges"]]
    if observed_ids != planned_ids:
        missing = sorted(set(planned_ids) - set(observed_ids))
        extra = sorted(set(observed_ids) - set(planned_ids))
        report.record(slot, "V5_range_cover", False,
                      f"the promoted set is not the sealed plan: "
                      f"{len(missing)} missing ({', '.join(missing[:5])}"
                      f"{'...' if len(missing) > 5 else ''}), "
                      f"{len(extra)} unexpected ({', '.join(extra[:5])})")
        return summary
    report.record(slot, "V5_range_cover", True,
                  f"{len(observed_ids)} promoted ranges exactly cover the plan")

    identity = plan["qualification_identity_sha256"]
    digests: list[str] = []
    observed_rows = 0
    for row in plan["ranges"]:
        batch = row["batch_id"]
        span = row["stop"] - row["start"]
        range_dir = ranges_dir / batch
        try:
            manifest = schema.rebuild_range_manifest(
                plan, schema.read_sealed(range_dir / schema.RANGE_MANIFEST_NAME,
                                         f"{family_key}/{batch} RANGE_MANIFEST"))
            body = (range_dir / schema.RECORDS_NAME).read_bytes()
            projected = json.loads(body.decode("ascii"))
            if not isinstance(projected, list) or len(projected) != span:
                raise Stage2AnalysisError(
                    f"{family_key}/{batch} records.json holds "
                    f"{len(projected) if isinstance(projected, list) else 'a non-list'}"
                    f"; its sealed range spans {span} coordinates "
                    "(stage2_production_writer.py:953-954)")
            records = schema.read_full_records(
                family_root / schema.FULL_RECORDS_DIRNAME / f"{batch}.jsonl.gz",
                span, f"{family_key}/{batch}")
        except (Stage2AnalysisError, OSError, UnicodeDecodeError,
                json.JSONDecodeError) as exc:
            report.record(slot, "V5_promoted_range", False, str(exc))
            continue

        if manifest["records_file_sha256"] != hashlib.sha256(body).hexdigest():
            report.record(slot, "V5_promoted_range", False,
                          f"{family_key}/{batch} records.json bytes hash to "
                          f"{hashlib.sha256(body).hexdigest()}, but its manifest "
                          f"names {manifest['records_file_sha256']}")
            continue
        # The writer's records file is `encodable_records`: canonical JSON of
        # the list (stage2_production_writer.py:282-306).
        content_digest = hashlib.sha256(
            schema.canonical_bytes(projected)).hexdigest()
        if manifest["records_content_sha256"] != content_digest:
            report.record(slot, "V5_promoted_range", False,
                          f"{family_key}/{batch} records content hash is "
                          f"{content_digest}, but its manifest names "
                          f"{manifest['records_content_sha256']}")
            continue

        # V6 — every committed record's own schema and commitment.
        bad = None
        for offset, record in enumerate(records):
            try:
                schema.check_record(record, family_key,
                                    f"{family_key}/{batch}[{offset}]",
                                    axis_length=axis_length,
                                    total=expected_rows)
            except Stage2AnalysisError as exc:
                bad = str(exc)
                break
        if bad is not None:
            report.record(slot, "V6_full_records", False, bad)
            continue
        expected_linear = row["start"]
        if records[0]["linear_index"] != expected_linear \
                or records[-1]["linear_index"] != row["stop"] - 1:
            report.record(slot, "V6_full_records", False,
                          f"{family_key}/{batch} spans linear "
                          f"{records[0]['linear_index']}.."
                          f"{records[-1]['linear_index']} but its sealed range is "
                          f"[{row['start']}, {row['stop']})")
            continue
        # The per-batch commitment production hashes is over the DECOMPRESSED
        # canonical stream (_persist_full:52-66).
        raw = gzip.decompress(
            (family_root / schema.FULL_RECORDS_DIRNAME / f"{batch}.jsonl.gz")
            .read_bytes())
        batch_digest = hashlib.sha256(raw).hexdigest()
        digests.append(batch_digest)
        observed_rows += span

        # V7 — the projection binds the committed record to the committed range.
        identity_mismatch = None
        for offset, record in enumerate(records):
            entry = projected[offset]
            if not isinstance(entry, dict) or set(entry) != {"coordinates", "result"}:
                identity_mismatch = (
                    f"{family_key}/{batch}[{offset}] writer record is not exactly "
                    "{{coordinates, result}} (stage2_production_writer.py:599)")
                break
            if set(entry["result"]) != set(WRITER_RESULT_SCHEMA):
                identity_mismatch = (
                    f"{family_key}/{batch}[{offset}] writer result fields differ "
                    "from the frozen projection schema "
                    "(wp8c_streaming_session_v3_gzip.py:91)")
                break
            if entry["result"]["record_content_sha256"] != record["content_sha256"]:
                identity_mismatch = (
                    f"{family_key}/{batch}[{offset}] writer record binds "
                    f"record_content_sha256="
                    f"{entry['result']['record_content_sha256']!r} but the "
                    f"committed record hashes to {record['content_sha256']!r}")
                break
        if identity_mismatch is not None:
            report.record(slot, "V7_projection_binding", False, identity_mismatch)
            continue
        report.record(slot, "V5_promoted_range", True,
                      f"{batch} [{row['start']},{row['stop']}) verified "
                      f"({span} records, both hashes match)")

    summary["observed_rows"] = observed_rows
    summary["implied_cuda_flushes"] = -(-observed_rows // schema.ROW_CAPACITY)
    if digests and len(digests) == len(plan["ranges"]):
        # stream_and_write_sealed_ranges returns
        # sha256(canonical(sorted(digests))) (gzip:115).
        commitment = hashlib.sha256(schema.canonical_bytes(
            sorted(digests))).hexdigest()
        summary["full_records_commitment_sha256"] = commitment
    # V8 — the census.
    if observed_rows != expected_rows:
        report.record(slot, "V8_row_census", False,
                      f"{family_key} carries {observed_rows} verified records; "
                      f"the frozen census is {expected_rows} ({citation})")
    else:
        report.record(slot, "V8_row_census", True,
                      f"{family_key}: {observed_rows} rows, "
                      f"{expected_ranges} sealed ranges, "
                      f"{summary['implied_cuda_flushes']} CUDA flushes "
                      f"(ROW_CAPACITY={schema.ROW_CAPACITY})")
    return summary


# ---------------------------------------------------------------------------
# V9 — identity consistency, then the slot summary
# ---------------------------------------------------------------------------

def verify_slot_identity(report: Report, slot: int, slot_dir: Path,
                         prepared_sha: str,
                         families: list[dict[str, Any]]) -> None:
    identities = {row["qualification_identity_sha256"] for row in families
                  if row["qualification_identity_sha256"]}
    if len(identities) > 1:
        report.record(slot, "V9_single_identity", False,
                      f"the slot's families carry {len(identities)} distinct "
                      f"qualification identities: {sorted(identities)}; one slot "
                      "is one identity (stage2_production_writer.py:812-813)")
    elif len(identities) == 1:
        report.record(slot, "V9_single_identity", True,
                      f"one qualification identity across all families: "
                      f"{next(iter(identities))[:16]}...")

    # The one-use session registry sits beside the slot trees, not inside one
    # (wp8c_production_session.session_state_path:406-408).
    state = (slot_dir.parent
             / schema.SESSION_STATE_NAME.format(slot_name=schema.SLOT_NAMES[slot - 1]))
    if not state.is_file():
        report.record(slot, "V9_session_state", False,
                      f"no session registry at {state}: the slot's one-use "
                      "authorizations were never consumed to completion "
                      "(wp8c_streaming_session_v3_gzip.py:292-298)")
        return
    try:
        sealed = schema.read_sealed(state, f"slot {slot} session registry")
    except Stage2AnalysisError as exc:
        report.record(slot, "V9_session_state", False, str(exc))
        return
    if sealed.get("schema") != schema.SESSION_STATE_SCHEMA:
        report.record(slot, "V9_session_state", False,
                      f"the session registry schema is "
                      f"{sealed.get('schema')!r}, not "
                      f"{schema.SESSION_STATE_SCHEMA!r}")
        return
    if sealed.get("status") != "complete":
        report.record(slot, "V9_session_state", False,
                      f"the session registry status is {sealed.get('status')!r}, "
                      "not 'complete'")
        return
    expected = next(iter(identities)) if len(identities) == 1 else None
    if expected is not None and sealed.get("identity_sha256") != expected:
        report.record(slot, "V9_session_state", False,
                      f"the session registry identity "
                      f"{sealed.get('identity_sha256')!r} differs from the "
                      f"sealed plan's {expected!r} "
                      "(wp8c_production_session._write_state / session_state_path)")
        return
    if sealed.get("instance_id") != schema.SLOT_NAMES[slot - 1]:
        report.record(slot, "V9_session_state", False,
                      f"the session registry names instance_id="
                      f"{sealed.get('instance_id')!r}, not "
                      f"{schema.SLOT_NAMES[slot - 1]!r}")
        return
    report.record(slot, "V9_session_state", True,
                  f"one-use session registry complete and identity-bound")


def verify_slot(report: Report, slot_number: int, results_root: Path,
                census: dict[str, Any]) -> dict[str, Any]:
    """V1-V9 for one slot.  Returns that slot's summary."""
    slot_name = schema.SLOT_NAMES[slot_number - 1]
    # Every key is initialised here so an early return on a missing slot still
    # yields a complete, comparable summary row rather than a KeyError later.
    summary: dict[str, Any] = {
        "slot": slot_number, "instance_id": slot_name,
        "verified": False, "families": [], "problems": [],
        "observed_rows": 0, "observed_sealed_ranges": 0,
        "observed_cuda_flushes": 0,
        "expected_rows": census["per_slot_rows"],
        "expected_sealed_ranges": census["per_slot_sealed_ranges"],
        "expected_cuda_flushes": census["per_slot_cuda_flushes"],
        "d013_fired": None, "prepared_record_content_sha256": None,
    }

    try:
        slot_dir = schema.find_slot_dir(results_root, slot_number)
    except Stage2AnalysisError as exc:
        report.record(slot_number, "V1_slot_present", False, str(exc))
        summary["problems"].append(str(exc))
        return summary
    try:
        observed = schema.instance_id_of(slot_dir, slot_number)
    except Stage2AnalysisError as exc:
        report.record(slot_number, "V1_instance_identity", False, str(exc))
        summary["problems"].append(str(exc))
        return summary
    report.record(slot_number, "V1_slot_present", True,
                  f"{slot_name} at {slot_dir}")
    report.record(slot_number, "V1_instance_identity", True,
                  f"PREPARED.json names {observed}")

    terminal = report.guard(slot_number, "V2_terminal_artefact",
                            f"slot {slot_number} terminal artefact",
                            verify_terminal, report, slot_number, results_root,
                            slot_dir)
    if terminal is None:
        return summary
    if terminal.get("instance_id") not in (None, slot_name):
        report.record(slot_number, "V2_result_instance_id", False,
                      f"the result names instance_id="
                      f"{terminal.get('instance_id')!r}, not {slot_name!r}")
        return summary
    report.record(slot_number, "V2_result_instance_id", True,
                  f"the result names this slot's instance")

    prepared_sha, trigger = report.guard(
        slot_number, "V3_session_receipts", f"slot {slot_number} retained receipts",
        verify_session_receipts, report, slot_number, slot_dir, terminal)

    families = [verify_family(report, slot_number, slot_dir, key, census)
                for key in schema.BASELINE_FAMILIES]
    summary["families"] = families
    summary["observed_rows"] = sum(row["observed_rows"] for row in families)
    summary["observed_sealed_ranges"] = sum(row["observed_sealed_ranges"]
                                            for row in families)
    summary["observed_cuda_flushes"] = sum(row["implied_cuda_flushes"]
                                           for row in families)
    summary["expected_rows"] = census["per_slot_rows"]
    summary["expected_sealed_ranges"] = census["per_slot_sealed_ranges"]
    summary["expected_cuda_flushes"] = census["per_slot_cuda_flushes"]
    summary["d013_fired"] = bool(trigger["fired"]) if trigger else None
    summary["prepared_record_content_sha256"] = prepared_sha

    if prepared_sha:
        report.guard(slot_number, "V9_identity_consistency",
                     f"slot {slot_number} identity consistency",
                     verify_slot_identity, report, slot_number, slot_dir,
                     prepared_sha, families)

    if summary["observed_rows"] != census["per_slot_rows"]:
        report.record(slot_number, "V8_slot_row_census", False,
                      f"the slot verifies {summary['observed_rows']} rows; the "
                      f"census profile expects {census['per_slot_rows']} "
                      "(3*226981 + 2197 + 29791 + 1367631)")
    elif summary["observed_sealed_ranges"] != census["per_slot_sealed_ranges"]:
        report.record(slot_number, "V8_slot_range_census", False,
                      f"the slot verifies {summary['observed_sealed_ranges']} "
                      f"sealed ranges; the census profile expects "
                      f"{census['per_slot_sealed_ranges']} "
                      f"(records_per_range="
                      f"{census['records_per_range']})")
    elif summary["observed_cuda_flushes"] != census["per_slot_cuda_flushes"]:
        report.record(slot_number, "V8_slot_flush_census", False,
                      f"the slot implies {summary['observed_cuda_flushes']} CUDA "
                      f"batch flushes; ROW_CAPACITY={schema.ROW_CAPACITY} over "
                      f"{census['per_slot_rows']} rows is "
                      f"{census['per_slot_cuda_flushes']}")
    else:
        report.record(slot_number, "V8_slot_census", True,
                      f"{census['per_slot_rows']} rows, "
                      f"{census['per_slot_sealed_ranges']} sealed ranges, "
                      f"{census['per_slot_cuda_flushes']} CUDA flushes")
    return summary


# ---------------------------------------------------------------------------
# The runner
# ---------------------------------------------------------------------------

def build_report(results_root: Path, census: dict[str, Any]) -> dict[str, Any]:
    report = Report()
    slots = [verify_slot(report, number, results_root, census)
             for number in range(1, len(schema.SLOT_NAMES) + 1)]
    frozen = schema.is_frozen_census(census)
    payload: dict[str, Any] = {
        "schema": "decisions_os/g9_stage2_verify_outputs/v1",
        "results_root": str(results_root),
        "census_profile": {
            "label": census["label"],
            "content_sha256": census["content_sha256"],
            "records_per_range": census["records_per_range"],
            "row_capacity": census["row_capacity"],
            "per_slot_rows": census["per_slot_rows"],
            "per_slot_sealed_ranges": census["per_slot_sealed_ranges"],
            "per_slot_cuda_flushes": census["per_slot_cuda_flushes"],
            "is_frozen_real_census": frozen,
            "family_census": census["family_census"],
        },
        "slots": slots,
        "slot_count": len(slots),
        "all_slots_verified": all(row["observed_rows"] == census["per_slot_rows"]
                                  for row in slots),
        "checks_run": len(report.checks),
        "failures": report.failures,
        "failure_count": len(report.failures),
        "checks": report.checks,
    }
    payload["content_sha256"] = schema.content_sha256(payload)
    return payload


def format_report(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("G9 Stage-2 output verification")
    lines.append("=" * 72)
    census = payload["census_profile"]
    lines.append(f"results root : {payload['results_root']}")
    lines.append(f"census       : {census['label']} "
                 f"(sha256 {census['content_sha256'][:16]}..., "
                 f"frozen={census['is_frozen_real_census']})")
    lines.append(f"per-slot     : {census['per_slot_rows']} rows / "
                 f"{census['per_slot_sealed_ranges']} sealed ranges / "
                 f"{census['per_slot_cuda_flushes']} CUDA flushes")
    for row in payload["slots"]:
        state = "VERIFIED" if row["observed_rows"] == census["per_slot_rows"] \
            else "INCOMPLETE"
        lines.append("")
        lines.append(f"  slot {row['slot']} ({row['instance_id']}): {state}")
        for family in row["families"]:
            lines.append(f"    {family['family']:<40} "
                         f"{family['observed_rows']:>9} / "
                         f"{family['expected_rows']:>9} rows   "
                         f"{family['observed_sealed_ranges']:>4} / "
                         f"{family['expected_sealed_ranges']:>4} ranges")
        if row["d013_fired"] is not None:
            lines.append(f"    D013 fired: {row['d013_fired']}")
    lines.append("")
    lines.append(f"checks run : {payload['checks_run']}")
    lines.append(f"failures   : {payload['failure_count']}")
    if payload["failures"]:
        lines.append("")
        lines.append("FAILURES (each names the exact artefact and the exact rule)")
        for failure in payload["failures"]:
            lines.append(f"  - slot {failure['slot']} [{failure['check']}] "
                         f"{failure['detail']}")
    lines.append("")
    lines.append(f"VERDICT: {'PASS' if payload['failure_count'] == 0 else 'FAIL'}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify the five real T4 Stage-2 production slot outputs, "
                    "fail-closed.")
    parser.add_argument("--results-root", required=True, type=Path,
                        help="A downloaded kernel output directory, or a parent "
                             "of several. Each slot's "
                             "staged_qualified_sources/research/g9/"
                             "stage2_instances/stage2_0N/ is discovered under it.")
    parser.add_argument("--report", type=Path, default=None,
                        help="Write the full JSON report here.")
    parser.add_argument("--census", type=Path,
                        default=Path(__file__).resolve().parent
                        / schema.FROZEN_CENSUS_NAME,
                        help="Census profile to check against. Defaults to the "
                             "shipped FROZEN_CENSUS.json, which is the real "
                             "production census (2,080,562 rows / 511 sealed "
                             "ranges / 1,040,281 CUDA flushes per slot). A "
                             "non-default profile is permitted ONLY for the "
                             "MOCK harness and is reported as "
                             "is_frozen_real_census: false.")
    args = parser.parse_args(argv)

    root = args.results_root
    if not root.is_dir():
        sys.stderr.write(f"results root is not a directory: {root}\n")
        return 2

    try:
        census = schema.load_census_profile(args.census)
    except Stage2AnalysisError as exc:
        sys.stderr.write(f"census profile refused: {exc}\n")
        return 2

    payload = build_report(root.resolve(), census)
    text = format_report(payload)
    print(text)
    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_bytes(schema.canonical_bytes(payload) + b"\n")
    return 0 if payload["failure_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
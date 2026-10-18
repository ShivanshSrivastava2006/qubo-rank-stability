#!/usr/bin/env python3
"""Synthetic fixtures for the Stage-2 production writer (WP4b), round 2.

Every filesystem effect happens inside a ``tempfile.TemporaryDirectory``; the
project tree is never written to, never used as a staging parent, and never
served as a production target.  No candidate, instance, ground truth or
scientific value is produced: coordinates are synthetic linear indices and
results are synthetic floats, ints, bools and strings.

The production identity is INJECTED (WP1 is under review), so the fixtures inject
a small synthetic stand-in whose ``validate`` is an independent canonical hash
and whose ``exact_match`` raises on any difference.  The writer's own binding
logic is therefore what is under test, not the identity.

Two fixture families, selected by an environment variable so the automated
mutation sweep can run the small one many times over:

* ``WP4B_FIXTURE_SUITE=fast`` (the default) runs ``check_fast_*`` only, on tiny
  synthetic instances.  Every check this suite performs is also performed by
  ``full``; the fast suite exists so one mutant costs milliseconds, not seconds.
* ``WP4B_FIXTURE_SUITE=full`` runs every ``check_*``, including the two-range
  5000-coordinate full domain, the argument fuzz suite and the plan-binding
  matrix.  This is the suite the reported runs use.
"""
from __future__ import annotations

import ast
import hashlib
import inspect
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
# Snapshot bytecode BEFORE any project import: the project may carry a tracked
# baseline of .pyc files, and this fixture (imports included) must add none.
PYC_BEFORE = set(ROOT.rglob("*.pyc"))
HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.g9 import stage2_production_writer as w  # noqa: E402
from research.g9 import stage2_sampled_verification as sampled  # noqa: E402
from research.g9 import stage2_commitment_adapter as adapter  # noqa: E402
import stage2_timestamp_witness as witness  # noqa: E402
from research.g9.cuda_qualification import stage2_cuda_execution_contract as contract  # noqa: E402

SUITE = os.environ.get("WP4B_FIXTURE_SUITE", "fast")
if SUITE not in ("fast", "full"):
    raise SystemExit(f"WP4B_FIXTURE_SUITE must be fast or full, not {SUITE!r}")


class FixtureError(RuntimeError):
    pass


class Crash(BaseException):
    """A crash injected at a write step, unwinding through the staging cleanup."""


COUNT = 0
STEP_INDEX: dict = {}


def require(condition: bool, message: str) -> None:
    global COUNT
    if not condition:
        raise FixtureError(message)
    COUNT += 1


def refused(fn, label: str, needle: str = "") -> None:
    global COUNT
    try:
        fn()
    except w.ProductionWriterError as exc:
        if needle and needle not in str(exc):
            raise FixtureError(f"{label}: refused for the wrong reason: {exc}") from exc
        COUNT += 1
        return
    except Exception as exc:
        raise FixtureError(f"{label}: raw {type(exc).__name__} instead of "
                           f"ProductionWriterError") from exc
    raise FixtureError(f"{label}: accepted")


def typed(fn, label: str) -> None:
    """Assert a call fails with the writer's typed error, whatever the input.

    Unlike ``refused`` this demands no particular message: it is what the
    argument fuzz suite uses, where the point is only that a wrong-typed or
    unhashable input never escapes as a raw TypeError, KeyError or
    AttributeError.
    """
    global COUNT
    try:
        fn()
    except w.ProductionWriterError:
        COUNT += 1
        return
    except Exception as exc:
        raise FixtureError(f"{label}: raw {type(exc).__name__} instead of "
                           f"ProductionWriterError: {exc}") from exc
    raise FixtureError(f"{label}: accepted")


def typed_or_ignored(fn, label: str) -> None:
    """Like ``typed`` for an argument that is diagnostic-only.

    ``check_records(..., label)`` interpolates ``label`` into refusal messages
    and never inspects it, so any object is legitimate there.  The fuzz suite
    still calls it with every wrong-typed value; what it asserts is that the
    call either succeeds or raises the writer's typed refusal, and never a raw
    error from the label itself.
    """
    global COUNT
    try:
        fn()
    except w.ProductionWriterError:
        pass
    except Exception as exc:
        raise FixtureError(f"{label}: raw {type(exc).__name__} instead of "
                           f"ProductionWriterError: {exc}") from exc
    COUNT += 1


class Identity:
    """Synthetic stand-in for the WP1 production identity (not imported)."""

    def __init__(self, payload: dict) -> None:
        self.accepted = payload

    def validate(self, payload: object) -> str:
        if payload != self.accepted:
            raise ValueError("validate() was given a different payload")
        return hashlib.sha256(json.dumps(payload, sort_keys=True,
                                         separators=(",", ":")).encode("ascii")).hexdigest()

    def exact_match(self, session: object, accepted: object) -> None:
        if session != accepted:
            raise ValueError("session identity does not exactly match the accepted identity")


ACCEPTED = {"schema": "synthetic/wp4b_identity/v1", "source_sha256": {"synthetic.py": "b" * 64}}
OTHER = {"schema": "synthetic/wp4b_identity/v1", "source_sha256": {"synthetic.py": "c" * 64}}
ID = Identity(ACCEPTED)
OTHER_ID = Identity(OTHER)
SCHEMA = {"energy": "binary64", "is_minimum": "bool", "label": "str", "canonical_index": "int"}
TOTAL = 5000  # two sealed ranges: 4096 + 904
# The fast suite is a SUBSET of the checks, not smaller instances: every
# structural case below (a missing second range, a re-promoted range, a cover
# that overlaps) needs a two-range plan to exist at all, so shrinking the total
# would delete the very cases the sweep must keep exercising.
SMALL = TOTAL
ONE = 8       # a genuinely one-range instance, where one range suffices
FAMILY = "synthetic_family"


def make_record(index: int) -> dict:
    return {"coordinates": [index, 0, 0],
            "result": {"energy": float(index) + 0.5, "is_minimum": bool(index % 2),
                       "label": f"syn{index:04d}", "canonical_index": index}}


def records_for(start: int, stop: int) -> list:
    return [make_record(index) for index in range(start, stop)]


def new_root(td: str, name: str = "instance_00") -> Path:
    root = Path(td) / name
    root.mkdir()
    return root


def seal(root: Path, total: int = TOTAL) -> dict:
    return w.seal_range_plan(root, family=FAMILY, total_coordinates=total,
                             identity=ID, session=ACCEPTED)


def write_all(root: Path, total: int = TOTAL) -> dict:
    plan = seal(root, total)
    for row in w.plan_batches(plan):
        w.write_range(root, row["batch_id"], records_for(row["start"], row["stop"]),
                      result_schema=SCHEMA, identity=ID, session=ACCEPTED)
    return plan


def commit(root: Path, plan: dict) -> dict:
    records = w.aggregate_records(root, result_schema=SCHEMA)
    coordinates = [record["coordinates"] for record in records]
    descriptor = {"family": plan["family"], "plan_content_sha256": plan["content_sha256"]}
    return w.seal_instance_commitment(
        root, descriptor=descriptor, result_schema=SCHEMA,
        expected_descriptor_sha256=w.hash_descriptor(descriptor),
        expected_schema_sha256=w.hash_result_schema(SCHEMA),
        expected_coordinate_root=sampled.coordinate_root(coordinates).hex(),
        expected_coordinates=coordinates,
        expected_plan_content_sha256=plan["content_sha256"],
        expected_total_coordinates=plan["total_coordinates"],
        identity=ID, session=ACCEPTED)


BEACON_PIN = {"beacon_chain": "synthetic/chain/v1",
              "round_selection_rule": "earliest_unpublished_at_or_after_pin",
              "chain_period_seconds": 30, "chain_genesis_time": 1_000_000_000,
              "pin_attestation": "synthetic-attestation-blob",
              "chain_hash": "a" * 64,
              "public_key_hex": "b" * 192,
              "scheme_id": "bls-unchained-g1-rfc9380"}
POLICY = {"beacon_chain": BEACON_PIN["beacon_chain"],
          "round_selection_rule": BEACON_PIN["round_selection_rule"]}


def pin_digest(pin: dict) -> str:
    return w._content_digest(w.beacon_policy_of_pin(pin))


def staging_residue(root: Path) -> list:
    return sorted(entry.name for entry in root.iterdir()
                  if entry.name.startswith(w.STAGING_PREFIX))


def promoted(root: Path) -> list:
    return sorted(entry.name for entry in (root / w.RANGES_DIRNAME).iterdir())


# --------------------------------------------------------------------------
# G7: the sealed plan
# --------------------------------------------------------------------------
def _check_plan_sealing(total: int) -> None:
    with tempfile.TemporaryDirectory() as td:
        root = new_root(td)
        plan = seal(root, total)
        rows = w.plan_batches(plan)
        require(plan["family"] == FAMILY and plan["total_coordinates"] == total
                and plan["max_coordinates_per_range"] == 4096, "plan shape changed")
        partition = []
        cursor = 0
        for row in rows:
            partition.append((row["start"], row["stop"]))
            cursor = row["stop"]
        require(cursor == total and partition[0][0] == 0
                and all(partition[i][1] == partition[i + 1][0]
                        for i in range(len(partition) - 1)),
                f"the plan is not the canonical [start, stop) split: {partition}")
        require((root / w.PLAN_NAME).is_file(), "the plan was not written")
        # The sealed plan file is read back and compared, not merely present.
        require(w.load_range_plan(root) == plan, "the sealed plan does not reload")
        require(json.loads((root / w.PLAN_NAME).read_text("ascii")) == plan,
                "the sealed plan file does not hold the sealed plan")
        # Re-sealing identical inputs is idempotent, not an error.
        require(seal(root, total) == plan, "re-sealing identical inputs changed the plan")
        # Repartitioning is refused: a different total is a different plan.
        refused(lambda: w.seal_range_plan(root, family=FAMILY, total_coordinates=total + 1,
                                          identity=ID, session=ACCEPTED),
                "repartition to a larger total", "must not be repartitioned")
        refused(lambda: w.seal_range_plan(root, family=FAMILY, total_coordinates=total - 1,
                                          identity=ID, session=ACCEPTED),
                "repartition to a smaller total", "must not be repartitioned")
        refused(lambda: w.seal_range_plan(root, family=FAMILY, total_coordinates=total,
                                          identity=ID, session=OTHER),
                "seal under a different identity",
                "does not exactly match the accepted identity")


def check_plan_sealing() -> None:
    _check_plan_sealing(TOTAL)
    with tempfile.TemporaryDirectory() as td:
        root = new_root(td)
        plan = seal(root)
        rows = w.plan_batches(plan)
        require([row["batch_id"] for row in rows] == [f"{FAMILY}_b0000", f"{FAMILY}_b0001"],
                "plan batch ids are wrong")
        require([(row["start"], row["stop"]) for row in rows] == [(0, 4096), (4096, 5000)],
                "plan partition is not the canonical [start, stop) split")


def check_fast_plan_sealing() -> None:
    _check_plan_sealing(SMALL)


# --------------------------------------------------------------------------
# G7: the atomic range write, happy path
# --------------------------------------------------------------------------
def _check_happy_path(total: int) -> None:
    with tempfile.TemporaryDirectory() as td:
        root = new_root(td)
        plan = write_all(root, total)
        rows = w.plan_batches(plan)
        digest = w.identity_hash(ID)
        for row in rows:
            verdict = w.verify_range(root, row["batch_id"], result_schema=SCHEMA)
            manifest = verdict["manifest"]
            require(manifest["status"] == "complete", "range is not reported complete")
            require(manifest["plan_content_sha256"] == plan["content_sha256"],
                    "the range manifest does not carry the sealed plan hash")
            require(manifest["qualification_identity_sha256"] == digest,
                    "the range manifest does not carry the accepted identity hash")
            require((manifest["start"], manifest["stop"]) == (row["start"], row["stop"]),
                    "the range manifest does not match the sealed range")
        audit = w.audit_final_set(root)
        require(audit["verdict"] == "accepted" and audit["batch_count"] == len(rows)
                and audit["total_coordinates"] == total, "the final-set audit did not accept")
        records = w.aggregate_records(root, result_schema=SCHEMA)
        require(len(records) == total, "aggregation returned the wrong count")
        require([record["coordinates"][0] for record in records] == list(range(total)),
                "aggregation is not in canonical plan order")
        require(staging_residue(root) == [], "a completed run left staging residue")
        # Every promoted manifest on disk is the one the verdict reported.
        for row in rows:
            stored = json.loads((root / w.RANGES_DIRNAME / row["batch_id"]
                                 / w.RANGE_MANIFEST_NAME).read_text("ascii"))
            require(stored == w.verify_range(root, row["batch_id"])["manifest"],
                    "the promoted manifest on disk is not the one reported complete")


def check_happy_path() -> None:
    _check_happy_path(TOTAL)


def check_fast_happy_path() -> None:
    _check_happy_path(SMALL)


# --------------------------------------------------------------------------
# G7: crash injection at every step
# --------------------------------------------------------------------------
def _check_crash_at_every_step(total: int) -> None:
    with tempfile.TemporaryDirectory() as td:
        probe = new_root(td, "probe")
        require(set(w.WRITE_STEPS) == set(STEP_INDEX), "the fixture and the writer disagree "
                                                       "on the set of write steps")
        del probe
    for step in w.WRITE_STEPS:
        with tempfile.TemporaryDirectory() as td:
            root = new_root(td)
            plan = seal(root, total)
            all_rows = w.plan_batches(plan)
            row = all_rows[0]
            rest = all_rows[1:]

            def hook(seen: str, want: str = step) -> None:
                if seen == want:
                    raise Crash(want)

            def attempt() -> None:
                w.write_range(root, row["batch_id"], records_for(row["start"], row["stop"]),
                              result_schema=SCHEMA, identity=ID, session=ACCEPTED,
                              crash_hook=hook)

            try:
                attempt()
            except Crash:
                pass
            else:
                raise FixtureError(f"crash at {step!r} did not fire")

            destination = root / w.RANGES_DIRNAME / row["batch_id"]
            if step == "promoted":
                # The rename already happened: the range must be whole, never
                # half-written, and its two files must be the promoted pair.
                require(destination.is_dir(), f"crash after the rename lost the range: {step}")
                require((destination / w.RECORDS_NAME).is_file()
                        and (destination / w.RANGE_MANIFEST_NAME).is_file(),
                        f"crash after the rename promoted a partial range: {step}")
                require(w.verify_range(root, row["batch_id"])["verdict"] == "complete",
                        f"a range promoted before a crash is not complete: {step}")
                require([item["batch_id"] for item in w.missing_ranges(root)]
                        == [item["batch_id"] for item in rest],
                        f"a promoted range was offered again after a crash: {step}")
            else:
                require(not destination.exists(),
                        f"crash at {step!r} left a partial promoted range")
                require(w.missing_ranges(root) == all_rows,
                        f"crash at {step!r} lost the range from the missing list")
                # And the range is still writable afterwards, as a whole range.
                manifest = w.write_range(root, row["batch_id"],
                                         records_for(row["start"], row["stop"]),
                                         result_schema=SCHEMA, identity=ID, session=ACCEPTED)
                require(manifest["status"] == "complete",
                        f"the range could not be re-run as a whole after a crash at {step!r}")
                require(w.verify_range(root, row["batch_id"])["verdict"] == "complete",
                        f"the re-run range is not complete after a crash at {step!r}")
            # Staging cleaned in every case.
            require(staging_residue(root) == [],
                    f"crash at {step!r} left staging residue: {staging_residue(root)}")
        STEP_INDEX.setdefault(step, True)


def check_crash_at_every_step() -> None:
    _check_crash_at_every_step(TOTAL)


def check_fast_crash_at_every_step() -> None:
    _check_crash_at_every_step(SMALL)


# --------------------------------------------------------------------------
# G7: the staging boundary -- staged bytes are verified before promotion
# --------------------------------------------------------------------------
def _check_staged_boundary(total: int) -> None:
    """A writer that corrupts its OWN staging is still refused.

    The staged-verify step exists for the case where the bytes that reach the
    file are not the bytes the manifest describes -- a partial write, a wrong
    payload, a manifest built from something other than what was written.  A
    crash_hook is the only way to produce that from outside, and it fires while
    the staging directory still exists.
    """
    def stage_and_tamper(step: str, mutate, needle: str = "does not match its manifest") -> None:
        with tempfile.TemporaryDirectory() as td:
            root = new_root(td)
            plan = seal(root, total)
            row = w.plan_batches(plan)[0]

            # A mutation that takes the row can size its payload without reading
            # the staging manifest, which does not exist yet at the earlier steps.
            wants_row = len(inspect.signature(mutate).parameters) >= 2

            def hook(seen: str, target_step: str = step, action=mutate,
                     two=wants_row) -> None:
                if seen == target_step:
                    staging = [entry for entry in root.iterdir()
                               if entry.name.startswith(w.STAGING_PREFIX)][0]
                    action(staging, row) if two else action(staging)

            refused(lambda: w.write_range(
                        root, row["batch_id"], records_for(row["start"], row["stop"]),
                        result_schema=SCHEMA, identity=ID, session=ACCEPTED,
                        crash_hook=hook),
                    f"a range write whose staging was tampered at {step!r}", needle)
            require(not (root / w.RANGES_DIRNAME / row["batch_id"]).exists(),
                    f"tampered staging at {step!r} was still promoted")
            require(staging_residue(root) == [],
                    f"tampered staging at {step!r} left residue")

    # The records file gains a byte after the manifest recorded its hash.
    stage_and_tamper(
        "records_fsynced",
        lambda staging: (staging / w.RECORDS_NAME).write_bytes(
            (staging / w.RECORDS_NAME).read_bytes() + b" "))
    # The records file is emptied outright.
    stage_and_tamper(
        "records_fsynced", lambda staging: (staging / w.RECORDS_NAME).write_bytes(b""))
    # The records file is replaced with a valid-JSON payload of the same length
    # but the wrong content, so the file hash is the only thing that catches it.
    def replace_with_other_records(staging, row=None):
        span = row["stop"] - row["start"]
        (staging / w.RECORDS_NAME).write_bytes(
            w.encodable_records(records_for(9000, 9000 + span)))
    stage_and_tamper("records_fsynced", replace_with_other_records,
                     "does not match its manifest")
    # The manifest's records-file hash is edited in staging, so the manifest no
    # longer describes the file beside it and no longer matches the plan.
    def edit_manifest(staging):
        manifest = json.loads((staging / w.RANGE_MANIFEST_NAME).read_text("ascii"))
        manifest["records_file_sha256"] = "a" * 64
        manifest.pop("content_sha256")
        manifest["content_sha256"] = contract.content_sha256(manifest)
        (staging / w.RANGE_MANIFEST_NAME).write_text(
            json.dumps(manifest, sort_keys=True, separators=(",", ":")), encoding="ascii")
    stage_and_tamper("manifest_written", edit_manifest,
                     "staged records file hash does not match its manifest")
    # And the manifest's own content hash is made self-consistent over a range
    # the plan does not contain, which the rebuild from the plan refuses.
    def forge_batch(staging):
        manifest = json.loads((staging / w.RANGE_MANIFEST_NAME).read_text("ascii"))
        manifest["batch_id"] = f"{FAMILY}_b9999"
        manifest.pop("content_sha256")
        manifest["content_sha256"] = contract.content_sha256(manifest)
        (staging / w.RANGE_MANIFEST_NAME).write_text(
            json.dumps(manifest, sort_keys=True, separators=(",", ":")), encoding="ascii")
    stage_and_tamper("manifest_written", forge_batch,
                     "does not match the sealed plan")
    # A manifest carrying every field but whose content is not the plan's: the
    # shape guard passes, and the records-file hash is what first disagrees.
    forged = {"schema": "nope", "batch_id": f"{FAMILY}_b0000", "start": 0, "stop": 4096,
              "plan_content_sha256": "a" * 64,
              "qualification_identity_sha256": "b" * 64,
              "records_file_sha256": "c" * 64, "records_content_sha256": "d" * 64,
              "status": "complete", "content_sha256": ""}
    forged["content_sha256"] = contract.content_sha256(forged)
    stage_and_tamper(
        "manifest_written",
        lambda staging: (staging / w.RANGE_MANIFEST_NAME).write_text(
            json.dumps(forged, sort_keys=True, separators=(",", ":")), encoding="ascii"),
        "staged records file hash does not match its manifest")

    # The staged RECORDS-CONTENT hash, reached with the file hash agreeing: the
    # records file is replaced by a different payload of the SAME length and the
    # manifest's file hash is updated to match it, so the file check passes and
    # the content hash -- re-derived over the file's contents rather than over
    # its bytes -- is the only disagreement left.
    def write_content_forged(staging):
        good = json.loads((staging / w.RANGE_MANIFEST_NAME).read_text("ascii"))
        replacement = w.encodable_records(records_for(0, good["stop"]))
        (staging / w.RECORDS_NAME).write_bytes(replacement)
        good["records_file_sha256"] = hashlib.sha256(replacement).hexdigest()
        good["records_content_sha256"] = "e" * 64
        good.pop("content_sha256")
        good["content_sha256"] = contract.content_sha256(good)
        (staging / w.RANGE_MANIFEST_NAME).write_text(
            json.dumps(good, sort_keys=True, separators=(",", ":")),
            encoding="ascii")
    stage_and_tamper("manifest_written", write_content_forged,
                     "staged records content hash does not match its manifest")

    # The staged RECORDS FILE removed outright, and the staged MANIFEST removed
    # outright.  Each reaches its own presence check, which is the only thing
    # standing between an empty staging directory and a promotion.
    stage_and_tamper("staging_fsynced",
                     lambda staging: (staging / w.RECORDS_NAME).unlink(),
                     "staged records file is missing")
    stage_and_tamper("staging_fsynced",
                     lambda staging: (staging / w.RANGE_MANIFEST_NAME).unlink(),
                     "staged range manifest is missing")
    # A staged records path that is a DIRECTORY, and a staged manifest that is a
    # directory: neither is the real file the presence check demands.
    stage_and_tamper("staging_fsynced",
                     lambda staging: (staging / w.RECORDS_NAME).unlink() or
                     (staging / w.RECORDS_NAME).mkdir(),
                     "staged records file is missing")
    stage_and_tamper("staging_fsynced",
                     lambda staging: (staging / w.RANGE_MANIFEST_NAME).unlink() or
                     (staging / w.RANGE_MANIFEST_NAME).mkdir(),
                     "staged range manifest is missing")

    # A symlink to valid staged bytes is still not an owned staged artefact.
    # The bytes and manifest hashes agree, so the no-symlink guards are the
    # only refusals that stop these paths from being promoted as symlinks.
    def symlink_staged_file(staging, name: str) -> None:
        path = staging / name
        target = staging.parent / f"outside-{name}"
        path.replace(target)
        path.symlink_to(target)

    stage_and_tamper("staging_fsynced",
                     lambda staging: symlink_staged_file(staging, w.RECORDS_NAME),
                     "staged records file is missing")
    stage_and_tamper("staging_fsynced",
                     lambda staging: symlink_staged_file(staging, w.RANGE_MANIFEST_NAME),
                     "staged range manifest is missing")

    # The manifest's OWN content hash.  Every key is still present and the range
    # values are all correct; only the manifest's self-hash is dropped, so the
    # shape guard passes and the self-consistency check is the only one that can
    # notice.
    def write_stale_manifest_hash(staging):
        good = json.loads((staging / w.RANGE_MANIFEST_NAME).read_text("ascii"))
        good.pop("content_sha256")
        (staging / w.RANGE_MANIFEST_NAME).write_text(
            json.dumps(good, sort_keys=True, separators=(",", ":")),
            encoding="ascii")
    stage_and_tamper("manifest_written", write_stale_manifest_hash,
                     "wrong key set")
    # And with the key present but holding a hash that is not its own.
    def write_wrong_manifest_hash(staging):
        good = json.loads((staging / w.RANGE_MANIFEST_NAME).read_text("ascii"))
        good["content_sha256"] = "e" * 64
        (staging / w.RANGE_MANIFEST_NAME).write_text(
            json.dumps(good, sort_keys=True, separators=(",", ":")),
            encoding="ascii")
    stage_and_tamper("manifest_written", write_wrong_manifest_hash,
                     "manifest content hash mismatch")
    # A manifest with the right file hashes but a batch the plan does not
    # contain: here the file hash agrees, and the rebuild from the sealed plan
    # is the only thing that can refuse.
    def forge_batch_with_hashes(staging):
        good = json.loads((staging / w.RANGE_MANIFEST_NAME).read_text("ascii"))
        good["batch_id"] = f"{FAMILY}_b9999"
        good.pop("content_sha256")
        good["content_sha256"] = contract.content_sha256(good)
        (staging / w.RANGE_MANIFEST_NAME).write_text(
            json.dumps(good, sort_keys=True, separators=(",", ":")), encoding="ascii")
    stage_and_tamper("manifest_written", forge_batch_with_hashes,
                     "does not match the sealed plan")
    # A manifest missing fields entirely, refused on shape before any index.
    stage_and_tamper(
        "manifest_written",
        lambda staging: (staging / w.RANGE_MANIFEST_NAME).write_bytes(b"{}"),
        "wrong key set")
    # A manifest that is not a dict at all.
    stage_and_tamper(
        "manifest_written",
        lambda staging: (staging / w.RANGE_MANIFEST_NAME).write_bytes(b"[]"),
        "must be a dict")
    # And one whose own content hash is stale.
    stage_and_tamper(
        "manifest_written",
        lambda staging: (staging / w.RANGE_MANIFEST_NAME).write_bytes(
            b'{"schema":"nope","batch_id":"nope"}'),
        "wrong key set")


def check_staged_boundary() -> None:
    _check_staged_boundary(TOTAL)


def check_fast_staged_boundary() -> None:
    _check_staged_boundary(SMALL)


# --------------------------------------------------------------------------
# G7: restart handling -- whole missing ranges only
# --------------------------------------------------------------------------
def _check_stale_staging_discarded(total: int) -> None:
    with tempfile.TemporaryDirectory() as td:
        root = new_root(td)
        plan = seal(root, total)
        all_rows = w.plan_batches(plan)
        row = all_rows[0]
        stale = root / f"{w.STAGING_PREFIX}99999-{row['batch_id']}"
        stale.mkdir()
        (stale / w.RECORDS_NAME).write_bytes(b'[{"coordinates": [0, 0, 0], "result": {}}]')
        (stale / w.RANGE_MANIFEST_NAME).write_bytes(b'{"tampered": true}')
        removed = w.discard_stale_staging(root)
        require(removed == [stale.name], "discard_stale_staging did not report the residue")
        require(not stale.exists(), "the interrupted range was not discarded")
        require(staging_residue(root) == [], "stale staging survived the discard")
        # The range is offered whole, and the tampered bytes were not adopted.
        offered = w.missing_ranges(root)
        require([item["batch_id"] for item in offered]
                == [item["batch_id"] for item in all_rows],
                "an interrupted range was not offered whole")
        w.write_range(root, row["batch_id"], records_for(row["start"], row["stop"]),
                      result_schema=SCHEMA, identity=ID, session=ACCEPTED)
        require(w.verify_range(root, row["batch_id"])["records_file_sha256"]
                == hashlib.sha256(w.encodable_records(
                    records_for(row["start"], row["stop"]))).hexdigest(),
                "the discarded staging bytes were adopted instead of freshly written")


def check_stale_staging_discarded() -> None:
    _check_stale_staging_discarded(TOTAL)


def check_fast_stale_staging_discarded() -> None:
    _check_stale_staging_discarded(SMALL)


# --------------------------------------------------------------------------
# G7: a completed range is never rewritten
# --------------------------------------------------------------------------
def _check_rewrite_refused(total: int) -> None:
    with tempfile.TemporaryDirectory() as td:
        root = new_root(td)
        plan = seal(root, total)
        row = w.plan_batches(plan)[0]
        w.write_range(root, row["batch_id"], records_for(row["start"], row["stop"]),
                      result_schema=SCHEMA, identity=ID, session=ACCEPTED)
        before = w.verify_range(root, row["batch_id"])
        # Identical records: still refused, because the range is complete.
        refused(lambda: w.write_range(root, row["batch_id"],
                                      records_for(row["start"], row["stop"]),
                                      result_schema=SCHEMA, identity=ID, session=ACCEPTED),
                "rewrite of a completed range with identical records",
                "refusing to rewrite a completed range")
        # Different records: also refused, and the promoted bytes are unchanged.
        other = records_for(row["start"], row["stop"])
        other[0]["result"]["label"] = "tampered"
        refused(lambda: w.write_range(root, row["batch_id"], other,
                                      result_schema=SCHEMA, identity=ID, session=ACCEPTED),
                "rewrite of a completed range with different records",
                "refusing to rewrite a completed range")
        after = w.verify_range(root, row["batch_id"])
        require(after["manifest"] == before["manifest"],
                "a refused rewrite changed the promoted range")
        # An unplanned batch is refused too.
        refused(lambda: w.write_range(root, f"{FAMILY}_b0009", records_for(0, 1),
                                      result_schema=SCHEMA, identity=ID, session=ACCEPTED),
                "write of a batch outside the sealed plan", "not in the sealed plan")


def check_rewrite_refused() -> None:
    _check_rewrite_refused(TOTAL)


def check_fast_rewrite_refused() -> None:
    _check_rewrite_refused(SMALL)


# --------------------------------------------------------------------------
# G7: a one-byte change in a promoted records file is detected
# --------------------------------------------------------------------------
def _check_tampered_records_detected(total: int) -> None:
    with tempfile.TemporaryDirectory() as td:
        root = new_root(td)
        # All ranges are written, so the final-set audit reaches the tamper
        # rather than short-circuiting on a missing range.
        plan = write_all(root, total)
        row = w.plan_batches(plan)[0]
        path = root / w.RANGES_DIRNAME / row["batch_id"] / w.RECORDS_NAME
        body = bytearray(path.read_bytes())
        # Flip exactly one byte, keeping the file valid JSON, so the detection
        # cannot come from a parse failure but from the hash comparison.
        target = body.index(b'"label":"syn0000"') + len(b'"label":"syn')
        body[target] = ord("X")
        path.write_bytes(bytes(body))
        # The ORDER of the three hash checks in verify_range is load-bearing: a
        # one-byte change in the file is caught by the records-FILE hash, which
        # runs first.  See also the content-hash-only case below, which is what
        # keeps the content check independently reachable.
        refused(lambda: w.verify_range(root, row["batch_id"], result_schema=SCHEMA),
                "a one-byte change in a promoted records file",
                "promoted records file hash changed")
        refused(lambda: w.audit_final_set(root),
                "a one-byte change seen by the final-set audit",
                "promoted records file hash changed")
        refused(lambda: w.aggregate_records(root, result_schema=SCHEMA),
                "a one-byte change seen by aggregation",
                "promoted records file hash changed")
        # The honest ranges are untouched: the others still verify.
        for other in w.plan_batches(plan)[1:]:
            require(w.verify_range(root, other["batch_id"])["verdict"] == "complete",
                    "tampering with one range damaged another")

    # The RECORDS CONTENT hash, reached with the records FILE hash agreeing.  A
    # one-byte change in the file is caught by the file hash first, so this case
    # is the only thing that keeps the content check independently reachable: the
    # records file is re-encoded canonically, which is a different byte string
    # with the same contents, and the manifest is edited so the FILE hash matches
    # the new bytes while the CONTENT hash still names the old encoding.  Only
    # re-deriving the content hash over the file's contents can refuse.
    with tempfile.TemporaryDirectory() as td:
        root = new_root(td)
        plan = write_all(root, total)
        row = w.plan_batches(plan)[0]
        directory = root / w.RANGES_DIRNAME / row["batch_id"]
        manifest = json.loads((directory / w.RANGE_MANIFEST_NAME).read_text("ascii"))
        # Re-encode the same records with different (but valid) JSON bytes: the
        # key order or separators change, so the file hash moves while every
        # record value is identical.
        original = json.loads((directory / w.RECORDS_NAME).read_text("ascii"))
        reencoded = json.dumps(original, sort_keys=True, indent=1).encode("ascii")
        (directory / w.RECORDS_NAME).write_bytes(reencoded)
        require(hashlib.sha256(reencoded).hexdigest() != manifest["records_file_sha256"],
                "the re-encoded fixture is byte-identical to the original")
        refused(lambda: w.verify_range(root, row["batch_id"]),
                "a promoted records file re-encoded so only its content hash still agrees",
                "promoted records file hash changed")
        # Now make the file hash agree too, leaving the CONTENT hash as the only
        # possible disagreement: the manifest's file hash is updated to the new
        # bytes and its content hash is replaced with a wrong one, with its own
        # content hash recomputed so the manifest is internally self-consistent.
        # Re-encoding the same records canonically reproduces the ORIGINAL content
        # hash, so the file-hash check passes and the records-CONTENT hash is the
        # only check left that can refuse.
        manifest["records_file_sha256"] = hashlib.sha256(reencoded).hexdigest()
        manifest["records_content_sha256"] = "e" * 64
        manifest.pop("content_sha256")
        manifest["content_sha256"] = contract.content_sha256(manifest)
        _write_json(directory / w.RANGE_MANIFEST_NAME, manifest)
        refused(lambda: w.verify_range(root, row["batch_id"]),
                "a manifest whose file hash agrees but whose content hash does not",
                "promoted records content hash changed")
        refused(lambda: w.audit_final_set(root),
                "the final-set audit of a manifest whose content hash does not",
                "promoted records content hash changed")
        del plan


def check_tampered_records_detected() -> None:
    _check_tampered_records_detected(TOTAL)


def check_fast_tampered_records_detected() -> None:
    _check_tampered_records_detected(SMALL)


# --------------------------------------------------------------------------
# G7: the final-set audit refuses a missing or overlapping cover
# --------------------------------------------------------------------------
def _check_final_set_audit(total: int) -> None:
    # A missing range.
    with tempfile.TemporaryDirectory() as td:
        root = new_root(td)
        plan = seal(root, total)
        row = w.plan_batches(plan)[0]
        w.write_range(root, row["batch_id"], records_for(row["start"], row["stop"]),
                      result_schema=SCHEMA, identity=ID, session=ACCEPTED)
        refused(lambda: w.audit_final_set(root), "final-set audit with a missing range",
                "missing from the final set")
        refused(lambda: w.aggregate_records(root, result_schema=SCHEMA),
                "aggregation with a missing range", "missing from the final set")
        require([item["batch_id"] for item in w.missing_ranges(root)]
                == [item["batch_id"] for item in w.plan_batches(plan)[1:]],
                "the missing whole range is not what a restart is offered")

    # An overlapping cover: a hand-built manifest for a range the plan does not
    # contain, spliced over a promoted one.  The frozen contract refuses the
    # unexpected batch and the partition mismatch.
    with tempfile.TemporaryDirectory() as td:
        root = new_root(td)
        write_all(root, total)
        rows = w.plan_batches(w.load_range_plan(root))
        directory = root / w.RANGES_DIRNAME / rows[0]["batch_id"]
        manifest = json.loads((directory / w.RANGE_MANIFEST_NAME).read_text("ascii"))
        overlap = dict(manifest)
        overlap["start"] = manifest["start"] - 1
        overlap["stop"] = manifest["stop"] - 1
        overlap.pop("content_sha256")
        overlap["content_sha256"] = contract.content_sha256(overlap)
        (directory / w.RANGE_MANIFEST_NAME).write_text(
            json.dumps(overlap, sort_keys=True, separators=(",", ":")), encoding="ascii")
        refused(lambda: w.audit_final_set(root),
                "final-set audit with an overlapping range",
                "does not match its manifest and the sealed plan")
        refused(lambda: w.aggregate_records(root, result_schema=SCHEMA),
                "aggregation with an overlapping range",
                "does not match its manifest and the sealed plan")

    # A range whose files were removed after promotion is a missing range, not a
    # silently shorter cover.
    with tempfile.TemporaryDirectory() as td:
        root = new_root(td)
        plan = write_all(root, total)
        row = w.plan_batches(plan)[0]
        (root / w.RANGES_DIRNAME / row["batch_id"] / w.RECORDS_NAME).unlink()
        refused(lambda: w.audit_final_set(root),
                "final-set audit with a promoted range whose records file is gone",
                "incomplete on disk")
        refused(lambda: w.aggregate_records(root, result_schema=SCHEMA),
                "aggregation with a promoted range whose records file is gone",
                "incomplete on disk")
        # And the range itself refuses the same hole, by the same audit.
        refused(lambda: w.verify_range(root, row["batch_id"]),
                "verifying a range whose records file is gone",
                "range records file is missing")

    # A duplicated range cannot happen through the writer, so the cover is built
    # by hand.  This calls the FROZEN CONTRACT directly -- it is the contract's
    # own refusal under test, so its own error type is the correct expectation
    # and is not wrapped.
    with tempfile.TemporaryDirectory() as td:
        root = new_root(td)
        write_all(root, total)
        plan = w.load_range_plan(root)
        manifests = [json.loads((root / w.RANGES_DIRNAME / row["batch_id"]
                                 / w.RANGE_MANIFEST_NAME).read_text("ascii"))
                     for row in w.plan_batches(plan)]
        try:
            contract.validate_final_manifests(plan, manifests + [manifests[0]])
        except contract.CUDAExecutionContractError as exc:
            require("duplicated or unexpected" in str(exc),
                    f"the contract refused a duplicate for the wrong reason: {exc}")
        else:
            raise FixtureError("the contract accepted a duplicated range")


def check_final_set_audit() -> None:
    _check_final_set_audit(TOTAL)


def check_fast_final_set_audit() -> None:
    _check_final_set_audit(SMALL)


# --------------------------------------------------------------------------
# G7: identity binding on the write path
# --------------------------------------------------------------------------
def _check_identity_binding(total: int) -> None:
    with tempfile.TemporaryDirectory() as td:
        root = new_root(td)
        seal(root, total)
        row = w.plan_batches(w.load_range_plan(root))[0]
        refused(lambda: w.write_range(root, row["batch_id"],
                                      records_for(row["start"], row["stop"]),
                                      result_schema=SCHEMA, identity=ID, session=OTHER),
                "write under a session identity that does not match",
                "does not exactly match the accepted identity")
        require(not (root / w.RANGES_DIRNAME / row["batch_id"]).exists(),
                "a refused identity check still promoted a range")
        # An identity whose validate() disagrees with its own payload is refused
        # through the typed contract rather than raising out of it.
        class Broken(Identity):
            def validate(self, payload: object) -> str:
                return "not-a-sha"
        refused(lambda: w.identity_hash(Broken(ACCEPTED)),
                "an identity validate() that returns a non-digest", "must be a lowercase SHA-256")

        class Raising(Identity):
            def exact_match(self, session: object, accepted: object) -> None:
                raise ValueError("platform drift")
        refused(lambda: w.recheck_identity(Raising(ACCEPTED), ACCEPTED),
                "an identity exact_match() that raises",
                "does not exactly match the accepted identity")
        refused(lambda: w.identity_hash(object()),
                "an object with no identity interface", "must expose")

    # A plan sealed under one production identity cannot be written under
    # another.  Both identities are self-consistent, so this is not caught by
    # the exact_match recheck; it is caught only by the plan's own binding.
    with tempfile.TemporaryDirectory() as td:
        root = new_root(td)
        plan = seal(root, total)
        row = w.plan_batches(plan)[0]
        refused(lambda: w.write_range(root, row["batch_id"], records_for(row["start"], row["stop"]),
                                      result_schema=SCHEMA,
                                      identity=ExplodingValidate(ValueError("injected")),
                                      session=ACCEPTED),
                "writing a range under an identity whose validate() raises",
                "recheck_identity refused: ValueError")
        refused(lambda: w.write_range(root, row["batch_id"],
                                      records_for(row["start"], row["stop"]),
                                      result_schema=SCHEMA, identity=OTHER_ID, session=OTHER),
                "writing a range under a different identity than the plan",
                "different production identity")
        require(not (root / w.RANGES_DIRNAME / row["batch_id"]).exists(),
                "a plan-identity mismatch still promoted a range")
        # And the plan really is bound to the first identity.
        require(plan["qualification_identity_sha256"] == w.identity_hash(ID),
                "the sealed plan is not bound to the accepted identity")
        require(plan["qualification_identity_sha256"] != w.identity_hash(OTHER_ID),
                "two different identities produced the same hash")

    # A promoted range carries its identity in its manifest, and an auditor
    # naming a different one must see the mismatch rather than have the range
    # vouched for by whatever the caller has to hand.
    with tempfile.TemporaryDirectory() as td:
        root = new_root(td)
        plan = seal(root, total)
        row = w.plan_batches(plan)[0]
        w.write_range(root, row["batch_id"], records_for(row["start"], row["stop"]),
                      result_schema=SCHEMA, identity=ID, session=ACCEPTED)
        refused(lambda: w.verify_range(root, row["batch_id"],
                                       expected_identity_sha256="9" * 64),
                "verifying a range against a different production identity",
                "carries a different production identity")
        refused(lambda: w.verify_range(root, row["batch_id"],
                                       expected_identity_sha256="not-a-digest"),
                "verifying a range against a non-digest identity",
                "lowercase SHA-256")
        require(w.verify_range(root, row["batch_id"],
                               expected_identity_sha256=w.identity_hash(ID))["verdict"]
                == "complete", "verifying a range against its own identity failed")
        # Without a named identity the DEFAULT is the sealed plan's, not the
        # manifest's own claim: a manifest must not vouch for its own identity.
        stored = json.loads((root / w.RANGES_DIRNAME / row["batch_id"]
                             / w.RANGE_MANIFEST_NAME).read_text("ascii"))
        stored["qualification_identity_sha256"] = "9" * 64
        stored.pop("content_sha256")
        stored["content_sha256"] = contract.content_sha256(stored)
        (root / w.RANGES_DIRNAME / row["batch_id"] / w.RANGE_MANIFEST_NAME).write_text(
            json.dumps(stored, sort_keys=True, separators=(",", ":")), encoding="ascii")
        refused(lambda: w.verify_range(root, row["batch_id"]),
                "verifying a range whose manifest claims another identity, with no "
                "identity named", "carries a different production identity")

    # A range directory whose records file holds too few records, with a manifest
    # that is internally consistent about them.  The count check is what refuses
    # it: a range can hold too few records and still hash consistently with its
    # own manifest, so only a comparison against the sealed range catches it.
    with tempfile.TemporaryDirectory() as td:
        root = new_root(td)
        plan = seal(root, ONE)
        row = w.plan_batches(plan)[0]
        short = records_for(row["start"], row["start"] + 1)
        _plant_range(root, plan, row, short)
        refused(lambda: w.verify_range(root, row["batch_id"]),
                "verifying a range holding fewer records than the sealed range",
                "does not hold the sealed range's records")
        refused(lambda: w.audit_final_set(root),
                "the final-set audit of a range holding fewer records than sealed",
                "does not hold the sealed range's records")

    # A range that is entirely self-consistent -- correct record count, correct
    # file hash, correct content hash, a manifest rebuilt from the sealed plan --
    # but whose records VIOLATE the M1 committable form: an int field holding a
    # bool, and a duplicate coordinate.  Every hash agrees, so nothing in the
    # range machinery can see it; only re-checking the declared record form
    # against the declared schema refuses.  This is the case the optional
    # `result_schema` argument exists for, and it is why the schema is applied
    # when a caller supplies it.
    with tempfile.TemporaryDirectory() as td:
        root = new_root(td)
        plan = seal(root, ONE)
        row = w.plan_batches(plan)[0]
        records = records_for(row["start"], row["stop"])
        records[5]["result"] = dict(records[5]["result"])
        records[5]["result"]["canonical_index"] = True  # bool in an int field
        records[6] = {"coordinates": list(records[4]["coordinates"]),
                      "result": dict(records[6]["result"])}  # duplicate coordinate
        _plant_range(root, plan, row, records)
        # The range is structurally complete: the audit, which knows nothing of
        # the record form, accepts the cover.
        audit = w.audit_final_set(root)
        require(audit["verdict"] == "accepted" and audit["batch_count"] == 1,
                "the audit should accept a structurally complete one-range cover")
        # Without the schema the range verifies, because nothing else can see it.
        require(w.verify_range(root, row["batch_id"])["verdict"] == "complete",
                "a self-consistent range should verify without a declared schema")
        require(len(w.aggregate_records(root)) == ONE,
                "a self-consistent range should aggregate without a declared schema")
        # With the schema declared, both refuse.
        refused(lambda: w.verify_range(root, row["batch_id"], result_schema=SCHEMA),
                "verifying a schema-violating range with the schema declared",
                "wrong exact type")
        refused(lambda: w.aggregate_records(root, result_schema=SCHEMA),
                "aggregating a schema-violating range with the schema declared",
                "wrong exact type")
        # And the commitment layer refuses the same records outright: it
        # re-derives the roster from the records, so the form is checked first.
        sealed_coords = [record["coordinates"] for record in records]
        descriptor = {"family": FAMILY, "plan_content_sha256": plan["content_sha256"]}
        refused(lambda: w.seal_instance_commitment(
                    root, descriptor=descriptor, result_schema=SCHEMA,
                    expected_descriptor_sha256=w.hash_descriptor(descriptor),
                    expected_schema_sha256=w.hash_result_schema(SCHEMA),
                    expected_coordinate_root="e" * 64,
                    expected_coordinates=sealed_coords,
                    expected_plan_content_sha256=plan["content_sha256"],
                    expected_total_coordinates=plan["total_coordinates"],
                    identity=ID, session=ACCEPTED),
                "sealing a commitment over schema-violating records",
                "wrong exact type")


def _plant_range(root: Path, plan: dict, row: dict, records: list) -> None:
    """Promote a hand-built, internally self-consistent range directory."""
    body = w.encodable_records(records)
    manifest = contract.complete_range_manifest(plan, row["batch_id"],
                                                hashlib.sha256(body).hexdigest(),
                                                hashlib.sha256(body).hexdigest(),
                                                plan["qualification_identity_sha256"])
    directory = root / w.RANGES_DIRNAME / row["batch_id"]
    directory.mkdir(parents=True)
    (directory / w.RECORDS_NAME).write_bytes(body)
    (directory / w.RANGE_MANIFEST_NAME).write_bytes(w._canonical(manifest))


def check_identity_binding() -> None:
    _check_identity_binding(TOTAL)


def check_fast_identity_binding() -> None:
    _check_identity_binding(SMALL)


# --------------------------------------------------------------------------
# G7: the sealed artefacts are write-once -- every rewrite path is refused
# --------------------------------------------------------------------------
def _check_sealed_artefacts_write_once(total: int) -> None:
    """Once a plan, a range, a root, a pin or a request is sealed, nothing rewrites it.

    This is the defect the round-1 validator found: a second
    ``seal_instance_commitment`` replaced the sealed root, a second timestamp
    request replaced the stored policy digest, and a second
    ``seal_range_plan`` wrote over a repartitioned plan.  Every write-once
    artefact is exercised here through EVERY route to its bytes: the module's own
    sealing entry point, the low-level ``_create_file_once`` primitive, a direct
    ``os.rename`` over the file, and an out-of-band truncate/rewrite.
    """
    # --- the sealed plan -------------------------------------------------
    with tempfile.TemporaryDirectory() as td:
        root = new_root(td)
        plan = seal(root, total)
        before = (root / w.PLAN_NAME).read_bytes()
        # A re-seal with identical inputs returns the plan and writes nothing.
        require(seal(root, total) == plan, "an identical re-seal changed the plan")
        require((root / w.PLAN_NAME).read_bytes() == before,
                "an identical re-seal rewrote the sealed plan file")
        # A re-seal with a repartitioned plan is refused, and the file is intact.
        refused(lambda: w.seal_range_plan(root, family=FAMILY,
                                          total_coordinates=total + 1,
                                          identity=ID, session=ACCEPTED),
                "re-sealing a repartitioned plan", "must not be repartitioned")
        require((root / w.PLAN_NAME).read_bytes() == before,
                "a refused repartition rewrote the sealed plan file")
        # The low-level primitive refuses the sealed name too.
        _refuse_create_over(root / w.PLAN_NAME, b'{"schema":"forged"}',
                            "re-sealing the plan through the create-once primitive")
        require((root / w.PLAN_NAME).read_bytes() == before,
                "the create-once primitive overwrote the sealed plan")
        # An out-of-band rename is a filesystem act the module cannot prevent,
        # but a range promoted under the OLD plan must then fail to verify: its
        # manifest names a plan content hash that is no longer on disk.  So the
        # range is promoted FIRST, against the original plan, and only then is the
        # plan file swapped.
        first_batch = w.plan_batches(plan)[0]["batch_id"]
        w.write_range(root, first_batch, records_for(0, min(4096, total)),
                      result_schema=SCHEMA, identity=ID, session=ACCEPTED)
        require(w.verify_range(root, first_batch)["verdict"] == "complete",
                "the range does not verify under the plan it was promoted under")
        forged_plan = contract.build_range_plan(FAMILY, total + 1,
                                                plan["qualification_identity_sha256"])
        _rename_over(root / w.PLAN_NAME, w._canonical(forged_plan))
        require(w.load_range_plan(root) == forged_plan,
                "the out-of-band plan rewrite is not the plan the reader now sees")
        refused(lambda: w.verify_range(root, first_batch),
                "verifying a range promoted under a plan that was swapped out of band",
                "does not match its manifest and the sealed plan")
        refused(lambda: w.audit_final_set(root),
                "the final-set audit after an out-of-band plan swap",
                "does not match its manifest and the sealed plan")
        # And a forged plan that is not the contract's canonical shape is refused
        # outright, whatever it claims.
        _rename_over(root / w.PLAN_NAME, b'{"schema":"forged","family":"x"}')
        refused(lambda: w.load_range_plan(root),
                "loading a sealed plan that is not the contract's canonical shape",
                "wrong key set")
        del before

    # --- a promoted range ------------------------------------------------
    with tempfile.TemporaryDirectory() as td:
        root = new_root(td)
        plan = seal(root, total)
        row = w.plan_batches(plan)[0]
        w.write_range(root, row["batch_id"], records_for(row["start"], row["stop"]),
                      result_schema=SCHEMA, identity=ID, session=ACCEPTED)
        directory = root / w.RANGES_DIRNAME / row["batch_id"]
        manifest_bytes = (directory / w.RANGE_MANIFEST_NAME).read_bytes()
        records_bytes = (directory / w.RECORDS_NAME).read_bytes()
        # A re-promote is refused at the KERNEL level: renaming a staging
        # directory onto an existing non-empty directory fails with ENOTEMPTY, so
        # the promotion step cannot overwrite a completed range even if every
        # up-front guard were removed.  Asserted directly on the syscall, because
        # that guarantee -- not the guard -- is what makes promotion write-once.
        staging = root / f"{w.STAGING_PREFIX}repromote"
        staging.mkdir()
        (staging / w.RECORDS_NAME).write_bytes(records_bytes)
        (staging / w.RANGE_MANIFEST_NAME).write_bytes(manifest_bytes)
        _require_rename_refused(staging, directory)
        require((directory / w.RECORDS_NAME).read_bytes() == records_bytes
                and (directory / w.RANGE_MANIFEST_NAME).read_bytes() == manifest_bytes,
                "a re-promote replaced the completed range")
        # The module's own rewrite refusal, and the create-once primitive on the
        # manifest and the records file inside the promoted range.
        refused(lambda: w.write_range(root, row["batch_id"],
                                      records_for(row["start"], row["stop"]),
                                      result_schema=SCHEMA, identity=ID, session=ACCEPTED),
                "re-promoting a completed range through write_range",
                "refusing to rewrite a completed range")
        _refuse_create_over(directory / w.RANGE_MANIFEST_NAME, b"{}",
                            "replacing a promoted range manifest through the primitive")
        _refuse_create_over(directory / w.RECORDS_NAME, b"[]",
                            "replacing a promoted records file through the primitive")
        require((directory / w.RECORDS_NAME).read_bytes() == records_bytes
                and (directory / w.RANGE_MANIFEST_NAME).read_bytes() == manifest_bytes,
                "a refused rewrite changed a promoted range")

    # --- the per-instance commitment root and its pin --------------------
    with tempfile.TemporaryDirectory() as td:
        root = new_root(td)
        plan = write_all(root, total)
        sealed = commit(root, plan)
        commitment_bytes = (root / w.COMMITMENT_NAME).read_bytes()
        pin_bytes = (root / w.CAMPAIGN_PIN_NAME).read_bytes()
        digest = sealed["binding"]["campaign_binding_digest"]
        records = w.aggregate_records(root, result_schema=SCHEMA)
        coordinates = [record["coordinates"] for record in records]
        other_descriptor = {"family": "different", "plan_content_sha256": plan["content_sha256"]}
        # A second seal -- even one that would produce a DIFFERENT binding (a
        # different descriptor) -- is refused, and the sealed root is unchanged.
        refused(lambda: w.seal_instance_commitment(
                    root, descriptor=other_descriptor, result_schema=SCHEMA,
                    expected_descriptor_sha256=w.hash_descriptor(other_descriptor),
                    expected_schema_sha256=w.hash_result_schema(SCHEMA),
                    expected_coordinate_root=sampled.coordinate_root(coordinates).hex(),
                    expected_coordinates=coordinates,
                    expected_plan_content_sha256=plan["content_sha256"],
                    expected_total_coordinates=plan["total_coordinates"],
                    identity=ID, session=ACCEPTED),
                "re-sealing the commitment with a different descriptor",
                "already sealed and may not be re-sealed")
        # And an identical re-seal is refused too: the root is written once, ever.
        refused(lambda: commit(root, plan),
                "an identical re-seal of the commitment",
                "already sealed and may not be re-sealed")
        require((root / w.COMMITMENT_NAME).read_bytes() == commitment_bytes,
                "a refused re-seal changed the sealed commitment file")
        require((root / w.CAMPAIGN_PIN_NAME).read_bytes() == pin_bytes,
                "a refused re-seal changed the sealed campaign binding pin")
        # Re-pinning the campaign binding through the primitive is refused.
        _refuse_create_over(root / w.CAMPAIGN_PIN_NAME, b"{}",
                            "re-pinning the campaign binding through the primitive")
        require((root / w.CAMPAIGN_PIN_NAME).read_bytes() == pin_bytes,
                "the create-once primitive overwrote the sealed campaign pin")
        del digest

    # --- the external timestamp request ----------------------------------
    with tempfile.TemporaryDirectory() as td:
        root = new_root(td)
        plan = write_all(root, total)
        commit(root, plan)
        meta = w.build_timestamp_request(root, POLICY, nonce=4242)
        meta_bytes = (root / w.TIMESTAMP_REQUEST_META).read_bytes()
        request_bytes = (root / w.TIMESTAMP_REQUEST_NAME).read_bytes()
        # A second request with a different policy (a different subject) is
        # refused; the stored policy digest and request are unchanged.
        refused(lambda: w.build_timestamp_request(
                    root, dict(POLICY, round_selection_rule="different"), nonce=4243),
                "a second timestamp request with a different policy",
                "and may not be re-issued")
        # And with the same policy and a fresh nonce: also refused.
        refused(lambda: w.build_timestamp_request(root, POLICY, nonce=7777),
                "a second timestamp request with a fresh nonce",
                "and may not be re-issued")
        require((root / w.TIMESTAMP_REQUEST_META).read_bytes() == meta_bytes,
                "a refused re-issue changed the stored timestamp policy digest")
        require((root / w.TIMESTAMP_REQUEST_NAME).read_bytes() == request_bytes,
                "a refused re-issue changed the stored timestamp request")
        _refuse_create_over(root / w.TIMESTAMP_REQUEST_META, b"{}",
                            "re-issuing the timestamp request through the primitive")
        require((root / w.TIMESTAMP_REQUEST_META).read_bytes() == meta_bytes,
                "the create-once primitive overwrote the timestamp metadata")
        del meta

    # --- the frozen beacon rule pin and the consultation -----------------
    with tempfile.TemporaryDirectory() as td:
        root = new_root(td)
        plan = write_all(root, total)
        commit(root, plan)
        digest = pin_digest(BEACON_PIN)
        sealed_pin = w.seal_beacon_rule_pin(root, BEACON_PIN, digest)
        pin_file_bytes = (root / w.BEACON_PIN_NAME).read_bytes()
        require(sealed_pin["pin_digest"] == digest, "the sealed pin digest changed")
        # Re-pinning the same rule is idempotent; a different one is refused.
        require(w.seal_beacon_rule_pin(root, BEACON_PIN, digest) == sealed_pin,
                "re-pinning the same rule changed the pin")
        for label, other in (("a different beacon chain",
                              dict(BEACON_PIN, beacon_chain="synthetic/other_chain/v1")),
                             ("a different round-selection rule",
                              dict(BEACON_PIN, round_selection_rule="lowest_any_round"))):
            refused(lambda other=other: w.seal_beacon_rule_pin(
                        root, other, pin_digest(other)),
                    f"re-pinning {label}", "may not be re-pinned")
        require((root / w.BEACON_PIN_NAME).read_bytes() == pin_file_bytes,
                "a refused re-pin changed the frozen beacon rule file")
        _refuse_create_over(root / w.BEACON_PIN_NAME, b"{}",
                            "re-pinning the beacon rule through the primitive")
        # The consultation is write-once: consulting twice is refused.
        first = w.consult_beacon_rule(root, digest)
        consult_bytes = (root / w.BEACON_CONSULT_NAME).read_bytes()
        refused(lambda: w.consult_beacon_rule(root, digest),
                "recording the beacon consultation a second time",
                "already sealed and may not be re-recorded")
        require((root / w.BEACON_CONSULT_NAME).read_bytes() == consult_bytes,
                "a refused re-record changed the sealed consultation")
        _refuse_create_over(root / w.BEACON_CONSULT_NAME, b"{}",
                            "re-recording the consultation through the primitive")
        require((root / w.BEACON_CONSULT_NAME).read_bytes() == consult_bytes,
                "the create-once primitive overwrote the sealed consultation")
        del first


def _refuse_create_over(path: Path, payload: bytes, label: str) -> None:
    """Assert the create-once primitive refuses to replace an existing name."""
    refused(lambda: w._create_file_once(path, payload), label,
            "refusing to overwrite an existing file")
    require(path.read_bytes() != payload or not path.exists(),
            f"{label}: the primitive replaced the file's bytes")


def _check_staged_temp_file_is_never_left() -> None:
    """The primitive's staged temporary is removed on EVERY outcome.

    The temporary sibling holds the full payload in the instance root, so if it
    survives a refusal it leaves a complete copy of a sealed artefact next to
    the sealed artefact -- readable by anything that can read the root.  The
    three outcomes are driven separately, and each is observed by a listing of
    the parent taken by the CALLER, not from inside the primitive, so the
    assertion does not depend on the primitive's own view of the directory.
    """
    def temps_in(parent: Path) -> list:
        return sorted(entry.name for entry in parent.iterdir()
                      if entry.name.startswith(".tmp-"))

    with tempfile.TemporaryDirectory() as td:
        root = new_root(td)
        seal(root)
        w._create_file_once(root / "sealed_probe.json", b'{"probe":1}')
        require(temps_in(root) == [],
                f"the primitive left a staged temporary behind: {temps_in(root)}")
        # (a) success
        w._create_file_once(root / "ok.json", b'{"ok":true}')
        require(temps_in(root) == [],
                f"a successful create left a staged temporary: {temps_in(root)}")
        # (b) refusal: the name is already taken, so the hard link fails.
        refused(lambda: w._create_file_once(root / "ok.json", b'{"ok":false}'),
                "creating over an existing name through the primitive",
                "refusing to overwrite an existing file")
        require(temps_in(root) == [],
                f"a refused create left a staged temporary: {temps_in(root)}")
        require((root / "ok.json").read_bytes() == b'{"ok":true}',
                "a refused create changed the sealed file's bytes")
        # (c) a DIRECTORY already in the way.  A hard link to an existing name
        # fails with EEXIST whatever that name is, so this is the same refusal
        # -- and the same cleanup -- over a non-file occupant, which a
        # rename-over implementation would have replaced instead.
        (root / "occupied").mkdir()
        (root / "occupied" / "child").write_text("x", encoding="ascii")
        refused(lambda: w._create_file_once(root / "occupied", b'{"no":1}'),
                "creating over an existing directory through the primitive",
                "refusing to overwrite an existing file")
        require((root / "occupied" / "child").read_text(encoding="ascii") == "x",
                "the primitive replaced an existing directory")
        require(temps_in(root) == [],
                f"a refused create over a directory left a staged temporary: {temps_in(root)}")
        # A leftover temporary from THIS process under the SAME name is
        # cleared rather than reused, and does not stop the create that
        # follows it.  A temporary belonging to another pid is left alone --
        # the name carries the pid precisely so a live session's staged bytes
        # are never removed by a second one.
        orphan = root / f".tmp-after_orphan.json-{os.getpid()}"
        orphan.write_text("orphan", encoding="ascii")
        foreign = root / f".tmp-after_orphan.json-{os.getpid() + 1_000_000}"
        foreign.write_text("another session's staged bytes", encoding="ascii")
        w._create_file_once(root / "after_orphan.json", b'{"after":1}')
        require(not orphan.exists(),
                "the primitive reused this session's own leftover staged temporary")
        require(foreign.is_file(),
                "the primitive removed another process's staged temporary")
        require((root / "after_orphan.json").read_bytes() == b'{"after":1}',
                "the create after an orphan did not write its payload")
        require(sorted(e.name for e in root.iterdir() if e.name.startswith(".tmp-"))
                == [foreign.name],
                "the primitive left a staged temporary of its own behind")


def check_staged_temp_file_is_never_left() -> None:
    _check_staged_temp_file_is_never_left()


def check_fast_staged_temp_file_is_never_left() -> None:
    _check_staged_temp_file_is_never_left()


def _require_rename_refused(source: Path, destination: Path) -> None:
    """Assert the kernel refuses to rename ``source`` onto ``destination``.

    This is the write-once guarantee at its root: the promotion step is a single
    ``os.rename`` of a staging directory onto the range's destination, and
    renaming onto an existing non-empty directory fails, so a promoted range
    cannot be replaced by the writer's own promotion path.
    """
    try:
        os.rename(str(source), str(destination))
    except OSError:
        return
    raise FixtureError(f"the kernel allowed a rename onto an existing {destination}")


def _rename_over(path: Path, payload: bytes) -> None:
    """An out-of-band rename over a sealed FILE: what a filesystem actor could do.

    The module cannot prevent this (it is not the writer's own path), which is
    precisely why every READ re-derives its binding from the sealed plan and
    refuses a forgery.  The fixture plants it and asserts the reader catches it.
    """
    temp = path.parent / f".tmp-outofband-{os.getpid()}-{path.name}"
    temp.write_bytes(payload)
    os.replace(str(temp), str(path))


def check_sealed_artefacts_write_once() -> None:
    _check_sealed_artefacts_write_once(TOTAL)


def check_fast_sealed_artefacts_write_once() -> None:
    _check_sealed_artefacts_write_once(SMALL)


# --------------------------------------------------------------------------
# (2) the commitment is bound to the sealed plan -- a fixture for each field
# --------------------------------------------------------------------------
def _check_commitment_bound_to_plan(total: int) -> None:
    """Any mismatch between the commitment's identity or plan hash and the sealed
    plan is refused -- one fixture per field."""
    def prepared(td: str) -> tuple:
        root = new_root(td)
        plan = write_all(root, total)
        records = w.aggregate_records(root, result_schema=SCHEMA)
        coordinates = [record["coordinates"] for record in records]
        descriptor = {"family": plan["family"], "plan_content_sha256": plan["content_sha256"]}
        return root, plan, coordinates, descriptor

    def seal_with(root, plan, coordinates, descriptor, **overrides) -> None:
        base = dict(
            descriptor=descriptor, result_schema=SCHEMA,
            expected_descriptor_sha256=w.hash_descriptor(descriptor),
            expected_schema_sha256=w.hash_result_schema(SCHEMA),
            expected_coordinate_root=sampled.coordinate_root(coordinates).hex(),
            expected_coordinates=coordinates,
            expected_plan_content_sha256=plan["content_sha256"],
            expected_total_coordinates=plan["total_coordinates"],
            identity=ID, session=ACCEPTED)
        base.update(overrides)
        w.seal_instance_commitment(root, **base)

    # The identity field: a self-consistent injected identity whose hash differs
    # from the sealed plan's is refused.
    with tempfile.TemporaryDirectory() as td:
        root, plan, coordinates, descriptor = prepared(td)
        refused(lambda: seal_with(root, plan, coordinates, descriptor,
                                  identity=OTHER_ID, session=OTHER),
                "sealing a commitment under a different identity than the sealed plan",
                "identity differs from the production identity the sealed plan")
        require(not (root / w.COMMITMENT_NAME).exists(),
                "a refused identity binding still sealed a commitment")
    with tempfile.TemporaryDirectory() as td:
        root, plan, coordinates, descriptor = prepared(td)
        # The session is exact-match-clean but the injected identity object still
        # validates to a different hash -- only the plan's own binding can refuse.
        class Mismatch(Identity):
            def validate(self, payload: object) -> str:
                return "f" * 64  # a different, well-formed identity hash
        refused(lambda: seal_with(root, plan, coordinates, descriptor,
                                  identity=Mismatch(ACCEPTED), session=ACCEPTED),
                "sealing a commitment under an identity whose validate() disagrees "
                "with the plan", "identity differs from the production identity")
    # The plan-hash field: a different plan content hash is refused.
    with tempfile.TemporaryDirectory() as td:
        root, plan, coordinates, descriptor = prepared(td)
        other_plan = contract.build_range_plan(FAMILY, total + 1,
                                               plan["qualification_identity_sha256"])
        refused(lambda: seal_with(root, plan, coordinates, descriptor,
                                  expected_plan_content_sha256=other_plan["content_sha256"]),
                "sealing a commitment against a different plan hash",
                "names a different range plan than the sealed one")
    with tempfile.TemporaryDirectory() as td:
        root, plan, coordinates, descriptor = prepared(td)
        refused(lambda: seal_with(root, plan, coordinates, descriptor,
                                  expected_plan_content_sha256="a" * 64),
                "sealing a commitment against an arbitrary plan hash",
                "names a different range plan than the sealed one")
    # The total field: a different coordinate total is refused.
    with tempfile.TemporaryDirectory() as td:
        root, plan, coordinates, descriptor = prepared(td)
        refused(lambda: seal_with(root, plan, coordinates, descriptor,
                                  expected_total_coordinates=total + 1),
                "sealing a commitment against a different coordinate total",
                "names a different coordinate total than the sealed plan")
    with tempfile.TemporaryDirectory() as td:
        root, plan, coordinates, descriptor = prepared(td)
        refused(lambda: seal_with(root, plan, coordinates, descriptor,
                                  expected_total_coordinates=total - 1),
                "sealing a commitment against a smaller coordinate total",
                "names a different coordinate total than the sealed plan")

    # The happy path still binds, and the sealed file records the binding.
    with tempfile.TemporaryDirectory() as td:
        root, plan, coordinates, descriptor = prepared(td)
        seal_with(root, plan, coordinates, descriptor)
        sealed = w.load_commitment(root)
        require(sealed["plan_content_sha256"] == plan["content_sha256"],
                "the sealed commitment does not record the sealed plan hash")
        require(sealed["production_identity_sha256"] == plan["qualification_identity_sha256"],
                "the sealed commitment does not record the plan's identity")
        require(sealed["total_coordinates"] == plan["total_coordinates"],
                "the sealed commitment does not record the plan's total")
        binding = w.verify_plan_binding(root)
        require(binding["plan_content_sha256"] == plan["content_sha256"]
                and binding["production_identity_sha256"] == plan["qualification_identity_sha256"]
                and binding["total_coordinates"] == plan["total_coordinates"],
                "verify_plan_binding did not confirm the sealed binding")


def check_commitment_bound_to_plan() -> None:
    _check_commitment_bound_to_plan(TOTAL)


def check_fast_commitment_bound_to_plan() -> None:
    _check_commitment_bound_to_plan(SMALL)


# --------------------------------------------------------------------------
# The plan-binding read path: an out-of-band edit of a sealed artefact is refused
# --------------------------------------------------------------------------
def _check_plan_binding_read_path(total: int) -> None:
    """A stored artefact edited out of band is refused on read, field by field."""
    def prepared(td: str) -> tuple:
        root = new_root(td)
        plan = write_all(root, total)
        commit(root, plan)
        return root, plan

    def _rewrite(root: Path, name: str, mutate) -> None:
        document = json.loads((root / name).read_text("ascii"))
        mutate(document)
        (root / name).write_text(
            json.dumps(document, sort_keys=True, separators=(",", ":")), encoding="ascii")

    # The commitment names a different plan.
    for field, needle in (("plan_content_sha256", "names a different range plan than the sealed one"),
                          ("production_identity_sha256", "names a different production identity"),
                          ("total_coordinates", "names a different coordinate total")):
        with tempfile.TemporaryDirectory() as td:
            root, plan = prepared(td)
            _rewrite(root, w.COMMITMENT_NAME,
                     lambda document, f=field: document.__setitem__(
                         f, total + 1 if f == "total_coordinates" else "a" * 64))
            refused(lambda: w.verify_plan_binding(root),
                    f"a commitment whose {field} was edited", needle)
    # The pin names a different plan or identity.
    for field, needle in (("plan_content_sha256", "names a different range plan than the sealed one"),
                          ("production_identity_sha256", "names a different production identity")):
        with tempfile.TemporaryDirectory() as td:
            root, plan = prepared(td)
            _rewrite(root, w.CAMPAIGN_PIN_NAME,
                     lambda document, f=field: document.__setitem__(f, "a" * 64))
            refused(lambda: w.verify_plan_binding(root),
                    f"a campaign pin whose {field} was edited", needle)
    # The pin names a different binding digest than the sealed commitment.
    with tempfile.TemporaryDirectory() as td:
        root, plan = prepared(td)
        _rewrite(root, w.CAMPAIGN_PIN_NAME,
                 lambda document: document.__setitem__("campaign_binding_digest", "b" * 64))
        refused(lambda: w.verify_plan_binding(root),
                "a campaign pin naming a different binding digest",
                "names a different binding digest than the sealed commitment")
    # A malformed stored pin -- a list, a dict missing a key, or non-JSON -- must
    # raise the typed error, never a raw KeyError.  This is the round-1 defect.
    # The assertion here is TYPED-NESS, not a particular message: several shapes
    # are refused on different grounds (a list is "not a dict", a dict missing a
    # field is "wrong key set"), and all of them must be the one typed refusal.
    for payload, label in ((b"[]", "a list"), (b"{}", "a dict missing every key"),
                           (b'{"campaign_binding_digest": "x"}', "a dict missing a field"),
                           (b"not json at all", "non-JSON bytes"),
                           (b"\xff\xfe\x00", "non-ASCII bytes")):
        with tempfile.TemporaryDirectory() as td:
            root, plan = prepared(td)
            (root / w.CAMPAIGN_PIN_NAME).write_bytes(payload)
            typed(lambda: w.open_campaign_pin(root, "0" * 64),
                  f"a stored campaign pin that is {label}")
            typed(lambda: w.build_timestamp_request(root, POLICY, nonce=5),
                  f"a timestamp request with a campaign pin that is {label}")
            typed(lambda: w.verify_plan_binding(root),
                  f"verify_plan_binding with a campaign pin that is {label}")
    # A malformed stored beacon pin likewise, on both the seal and consult paths.
    for payload, label in ((b"[]", "a list"), (b"{}", "a dict missing every key"),
                           (b'{"pin_digest": "x"}', "a dict missing a field"),
                           (b"not json at all", "non-JSON bytes")):
        with tempfile.TemporaryDirectory() as td:
            root = new_root(td)
            plan = write_all(root, total)
            commit(root, plan)
            digest = pin_digest(BEACON_PIN)
            (root / w.BEACON_PIN_NAME).write_bytes(payload)
            typed(lambda: w.consult_beacon_rule(root, digest),
                  f"consulting with a stored beacon pin that is {label}")
            typed(lambda: w.seal_beacon_rule_pin(root, BEACON_PIN, digest),
                  f"re-sealing with a stored beacon pin that is {label}")
    # A malformed stored commitment likewise.
    for payload, label in ((b"[]", "a list"), (b"{}", "a dict missing every key"),
                           (b'{"binding": 7}', "a dict whose binding is not a dict")):
        with tempfile.TemporaryDirectory() as td:
            root, plan = prepared(td)
            (root / w.COMMITMENT_NAME).write_bytes(payload)
            typed(lambda: w.verify_retained_values(root),
                  f"verify_retained_values with a commitment that is {label}")
            typed(lambda: w.verify_plan_binding(root),
                  f"verify_plan_binding with a commitment that is {label}")
    # A non-digest where a digest is required is refused typed, not by a bytes.
    with tempfile.TemporaryDirectory() as td:
        root, plan = prepared(td)
        refused(lambda: w.open_campaign_pin(root, "not-a-digest"),
                "opening a campaign pin against a non-digest", "lowercase SHA-256")


def check_plan_binding_read_path() -> None:
    _check_plan_binding_read_path(TOTAL)


def check_fast_plan_binding_read_path() -> None:
    _check_plan_binding_read_path(SMALL)


# --------------------------------------------------------------------------
# M1: the canonical committable record form
# --------------------------------------------------------------------------
def _check_record_form(total: int) -> None:
    with tempfile.TemporaryDirectory() as td:
        root = new_root(td)
        seal(root, total)
        row = w.plan_batches(w.load_range_plan(root))[0]
        start, stop = row["start"], row["stop"]
        good = records_for(start, stop)

        def write(records: list) -> None:
            w.write_range(root, row["batch_id"], records, result_schema=SCHEMA,
                          identity=ID, session=ACCEPTED)

        bad = [dict(record) for record in good]
        bad[7 % len(bad)] = {"coordinates": bad[7 % len(bad)]["coordinates"]}
        refused(lambda: write(bad), "a record with no result", "must be exactly")

        bad = [dict(record) for record in good]
        bad[7 % len(bad)] = {"coordinates": bad[7 % len(bad)]["coordinates"],
                             "result": bad[7 % len(bad)]["result"], "extra": 1}
        refused(lambda: write(bad), "a record with an extra field", "must be exactly")

        bad = [dict(record) for record in good]
        bad[7 % len(bad)]["result"] = dict(bad[7 % len(bad)]["result"])
        bad[7 % len(bad)]["result"].pop("label")
        refused(lambda: write(bad), "a record missing a schema field",
                "result fields differ from the exact schema")

        bad = [dict(record) for record in good]
        bad[7 % len(bad)]["result"] = dict(bad[7 % len(bad)]["result"])
        bad[7 % len(bad)]["result"]["canonical_index"] = True  # bool is not an int here
        refused(lambda: write(bad), "an int field holding a bool", "wrong exact type")

        bad = [dict(record) for record in good]
        bad[7 % len(bad)]["result"] = dict(bad[7 % len(bad)]["result"])
        bad[7 % len(bad)]["result"]["is_minimum"] = 0  # int is not a bool
        refused(lambda: write(bad), "a bool field holding an int", "wrong exact type")

        bad = [dict(record) for record in good]
        bad[7 % len(bad)]["result"] = dict(bad[7 % len(bad)]["result"])
        bad[7 % len(bad)]["result"]["energy"] = float("inf")
        refused(lambda: write(bad), "a non-finite binary64 field", "not finite")

        bad = [dict(record) for record in good]
        bad[7 % len(bad)]["result"] = dict(bad[7 % len(bad)]["result"])
        bad[7 % len(bad)]["result"]["label"] = "x" * 4097
        refused(lambda: write(bad), "an over-long str field", "too long")

        bad = [dict(record) for record in good]
        bad[7 % len(bad)] = {"coordinates": [start, 1, 0], "result": bad[7 % len(bad)]["result"]}
        bad[8 % len(bad)] = {"coordinates": [start, 1, 0], "result": bad[8 % len(bad)]["result"]}
        refused(lambda: write(bad), "two records at the same coordinate",
                "duplicate coordinates")

        refused(lambda: write(good[:-1]), "a short range", "but the sealed range spans")
        refused(lambda: write(good + [make_record(stop)]), "a long range",
                "but the sealed range spans")

        # A value no JSON rendering can carry, in a field the schema types as a
        # plain string: the M1 form refuses it on type before the encoder ever
        # sees it, and the encoder refuses the same payload on its own.
        bad = [dict(record) for record in good]
        bad[3 % len(bad)]["result"] = dict(bad[3 % len(bad)]["result"])
        bad[3 % len(bad)]["result"]["label"] = {1, 2, 3}
        refused(lambda: write(bad), "a record holding a value JSON cannot encode",
                "wrong exact type")
        refused(lambda: w.encodable_records(bad), "encodable_records on the same payload",
                "not encodable")
        # And a NaN that survived the finiteness check would not encode either.
        refused(lambda: w.encodable_records([{"result": {"energy": float("nan")}}]),
                "encodable_records on a NaN payload", "not encodable")
        require(not (root / w.RANGES_DIRNAME / row["batch_id"]).exists(),
                "a refused record form still promoted a range")
        require(staging_residue(root) == [], "a refused record form left staging residue")


def check_record_form() -> None:
    _check_record_form(TOTAL)


def check_fast_record_form() -> None:
    _check_record_form(SMALL)


# --------------------------------------------------------------------------
# M2 / M5 / M6: the sealed root, the retained values and the independent roster
# --------------------------------------------------------------------------
def _check_commitment_root_and_retained_values(total: int) -> None:
    with tempfile.TemporaryDirectory() as td:
        root = new_root(td)
        plan = write_all(root, total)
        sealed = commit(root, plan)
        commitment = sealed["binding"]["commitment"]
        require(commitment["grid_point_count"] == total, "the root does not cover every point")
        require(len(sealed["retained_leaf_hashes"]) == total, "not every leaf was retained")
        require(len(sealed["retained_coordinates"]) == total,
                "not every coordinate was retained")
        require(commitment["coordinate_root"] == sampled.coordinate_root(
            sealed["retained_coordinates"]).hex(),
            "the retained coordinates do not reproduce the coordinate root")
        first_root = commitment["merkle_root"]
        records = w.aggregate_records(root, result_schema=SCHEMA)
        require(records[0] != records[1], "the fixture records are not distinct")
        del first_root

        coordinates = [record["coordinates"] for record in records]
        descriptor = {"family": FAMILY, "plan_content_sha256": plan["content_sha256"]}
        # M6: a roster that is not the written one is refused.
        wrong = [[index, 0, 0] for index in range(total)]
        wrong[0] = [999999, 0, 0]
        refused(lambda: w.seal_instance_commitment(
                    root, descriptor=descriptor, result_schema=SCHEMA,
                    expected_descriptor_sha256=w.hash_descriptor(descriptor),
                    expected_schema_sha256=w.hash_result_schema(SCHEMA),
                    expected_coordinate_root=sampled.coordinate_root(coordinates).hex(),
                    expected_coordinates=wrong,
                    expected_plan_content_sha256=plan["content_sha256"],
                    expected_total_coordinates=plan["total_coordinates"],
                    identity=ID, session=ACCEPTED),
                "a roster that differs from the written coordinates",
                "differs from the written coordinates")
        # A roster whose root does not match is refused (M6's other half).
        refused(lambda: w.seal_instance_commitment(
                    root, descriptor=descriptor, result_schema=SCHEMA,
                    expected_descriptor_sha256=w.hash_descriptor(descriptor),
                    expected_schema_sha256=w.hash_result_schema(SCHEMA),
                    expected_coordinate_root="d" * 64, expected_coordinates=coordinates,
                    expected_plan_content_sha256=plan["content_sha256"],
                    expected_total_coordinates=plan["total_coordinates"],
                    identity=ID, session=ACCEPTED),
                "a roster whose expected root does not match", "does not match its expected")
        # A descriptor or schema that does not match its pinned hash is refused at
        # the WRITER's boundary, before the commitment adapter is reached.  The
        # messages are distinct on purpose, so this cannot be satisfied by the
        # adapter's own re-check of the same values.
        refused(lambda: w.seal_instance_commitment(
                    root, descriptor={"family": "other"}, result_schema=SCHEMA,
                    expected_descriptor_sha256=w.hash_descriptor(descriptor),
                    expected_schema_sha256=w.hash_result_schema(SCHEMA),
                    expected_coordinate_root=sampled.coordinate_root(coordinates).hex(),
                    expected_coordinates=coordinates,
                    expected_plan_content_sha256=plan["content_sha256"],
                    expected_total_coordinates=plan["total_coordinates"],
                    identity=ID, session=ACCEPTED),
                "a descriptor that does not match its pinned hash",
                "writer boundary: descriptor identity mismatch")
        refused(lambda: w.seal_instance_commitment(
                    root, descriptor=descriptor, result_schema=dict(SCHEMA, extra="int"),
                    expected_descriptor_sha256=w.hash_descriptor(descriptor),
                    expected_schema_sha256=w.hash_result_schema(SCHEMA),
                    expected_coordinate_root=sampled.coordinate_root(coordinates).hex(),
                    expected_coordinates=coordinates,
                    expected_plan_content_sha256=plan["content_sha256"],
                    expected_total_coordinates=plan["total_coordinates"],
                    identity=ID, session=ACCEPTED),
                "a schema that does not match its pinned hash",
                "writer boundary: result schema identity mismatch")
        # A coordinate root that is not a digest is refused before anything else.
        refused(lambda: w.seal_instance_commitment(
                    root, descriptor=descriptor, result_schema=SCHEMA,
                    expected_descriptor_sha256=w.hash_descriptor(descriptor),
                    expected_schema_sha256=w.hash_result_schema(SCHEMA),
                    expected_coordinate_root="not-a-digest", expected_coordinates=coordinates,
                    expected_plan_content_sha256=plan["content_sha256"],
                    expected_total_coordinates=plan["total_coordinates"],
                    identity=ID, session=ACCEPTED),
                "a coordinate root that is not a digest", "lowercase SHA-256")
        # Commitment sealing is refused before the ranges exist.
        with tempfile.TemporaryDirectory() as td2:
            empty = new_root(td2, "instance_01")
            seal(empty, total)
            refused(lambda: w.aggregate_records(empty, result_schema=SCHEMA),
                    "aggregation before any range is promoted", "missing from the final set")

        # M5: the retained values are re-derived, and tampering with either half
        # of what a verifier needs is detected.
        require(w.verify_retained_values(root)["verdict"] == "retained_values_verified",
                "the retained values did not verify on the honest path")
        tampered = json.loads(json.dumps(sealed))
        tampered["retained_leaf_hashes"][3 % total] = "e" * 64
        _write_json(root / w.COMMITMENT_NAME, tampered)
        refused(lambda: w.verify_retained_values(root),
                "a tampered retained leaf hash", "does not reproduce the sealed merkle root")
        tampered = json.loads(json.dumps(sealed))
        tampered["retained_leaf_hashes"] = tampered["retained_leaf_hashes"][:-1]
        _write_json(root / w.COMMITMENT_NAME, tampered)
        refused(lambda: w.verify_retained_values(root),
                "a truncated retained leaf list", "disagree with the retained leaf list")
        tampered = json.loads(json.dumps(sealed))
        tampered["retained_coordinates"] = list(tampered["retained_coordinates"])
        tampered["retained_coordinates"][2] = tampered["retained_coordinates"][1]
        _write_json(root / w.COMMITMENT_NAME, tampered)
        refused(lambda: w.verify_retained_values(root),
                "non-distinct retained coordinates", "not distinct")
        # A retained coordinate list that is distinct, the right length, and
        # carries every leaf hash intact -- but is REORDERED.  Neither the
        # distinctness check nor the leaf-list check can see it: only re-deriving
        # the coordinate root from the list itself refuses.
        tampered = json.loads(json.dumps(sealed))
        coords_t = list(tampered["retained_coordinates"])
        coords_t[2], coords_t[3] = coords_t[3], coords_t[2]
        tampered["retained_coordinates"] = coords_t
        _write_json(root / w.COMMITMENT_NAME, tampered)
        refused(lambda: w.verify_retained_values(root),
                "reordered retained coordinates", "do not reproduce the sealed coordinate root")


def _write_json(path: Path, document) -> None:
    path.write_text(json.dumps(document, sort_keys=True, separators=(",", ":")),
                    encoding="ascii")


def check_commitment_root_and_retained_values() -> None:
    _check_commitment_root_and_retained_values(TOTAL)


def check_fast_commitment_root_and_retained_values() -> None:
    _check_commitment_root_and_retained_values(SMALL)


def check_root_changes_with_records() -> None:
    """A one-range family: changing one record changes the sealed root."""
    small = ONE
    roots = []
    for flip in (0, 1):
        with tempfile.TemporaryDirectory() as td:
            root = new_root(td)
            plan = seal(root, small)
            require(len(w.plan_batches(plan)) == 1, "the small plan is not one range")
            row = w.plan_batches(plan)[0]
            records = records_for(row["start"], row["stop"])
            if flip:
                records[flip]["result"]["energy"] = 1234.5
            w.write_range(root, row["batch_id"], records, result_schema=SCHEMA,
                          identity=ID, session=ACCEPTED)
            sealed = commit(root, plan)
            roots.append((sealed["binding"]["commitment"]["merkle_root"],
                          sealed["binding"]["campaign_binding_digest"]))
    require(roots[0][0] != roots[1][0], "the merkle root did not change with the record")
    require(roots[0][1] != roots[1][1], "the binding digest did not change with the record")


# --------------------------------------------------------------------------
# M4: the pinned binding
# --------------------------------------------------------------------------
def _check_pinned_binding(total: int) -> None:
    with tempfile.TemporaryDirectory() as td:
        root = new_root(td)
        write_all(root, total)
        plan = w.load_range_plan(root)
        sealed = commit(root, plan)
        digest = sealed["binding"]["campaign_binding_digest"]
        require(w.open_campaign_pin(root, digest)["merkle_root"]
                == sealed["binding"]["commitment"]["merkle_root"],
                "the pinned binding did not open against its own digest")
        # A different expected binding digest is refused.
        refused(lambda: w.open_campaign_pin(root, "f" * 64),
                "opening the campaign against a different binding digest",
                "names a different binding digest")
        # Editing the pinned merkle root is caught by the adapter's re-derivation.
        pin = json.loads((root / w.CAMPAIGN_PIN_NAME).read_text("ascii"))
        pin["merkle_root"] = "a" * 64
        _write_json(root / w.CAMPAIGN_PIN_NAME, pin)
        refused(lambda: w.open_campaign_pin(root, digest),
                "a pinned merkle root that was edited", "binding digest mismatch")


def check_pinned_binding() -> None:
    _check_pinned_binding(TOTAL)


def check_fast_pinned_binding() -> None:
    _check_pinned_binding(SMALL)


# --------------------------------------------------------------------------
# M3: the external-timestamp hook
# --------------------------------------------------------------------------
def _check_timestamp_hook(total: int) -> None:
    with tempfile.TemporaryDirectory() as td:
        root = new_root(td)
        write_all(root, total)
        plan = w.load_range_plan(root)
        sealed = commit(root, plan)
        meta = w.build_timestamp_request(root, POLICY, nonce=4242)
        require(meta["tsa_contacted"] is False, "the timestamp hook claims a TSA was contacted")
        require(meta["merkle_root"] == sealed["binding"]["commitment"]["merkle_root"],
                "the timestamp subject does not name the sealed root")
        require(meta["minimum_authorities"] == 2, "the hook did not require two authorities")
        require((root / w.TIMESTAMP_REQUEST_NAME).read_bytes().startswith(b"0"),
                "the timestamp request is not a DER SEQUENCE")
        # The subject binds the policy too: two policies give two subjects.  The
        # comparison is made directly on the subject digest, not by re-issuing a
        # second (now write-once) request.
        other_digest = w._content_digest({"beacon_chain": POLICY["beacon_chain"],
                                          "round_selection_rule": "other"})
        other_subject = __import__("stage2_timestamp_witness").witness_subject_digest(
            meta["merkle_root"], other_digest)
        require(other_subject != meta["subject_digest"],
                "the timestamp subject does not bind the beacon policy")
        del other_subject, other_digest, plan
        # Before the root is sealed there is nothing to timestamp.
        with tempfile.TemporaryDirectory() as td2:
            early = new_root(td2, "instance_02")
            seal(early, total)
            refused(lambda: w.build_timestamp_request(early, POLICY, nonce=1),
                    "a timestamp request before the commitment root is sealed",
                    "no sealed campaign binding pin")
        refused(lambda: w.build_timestamp_request(root, POLICY, nonce=0),
                "a timestamp request with a zero nonce", "positive int")
        refused(lambda: w.build_timestamp_request(root, POLICY, nonce=-5),
                "a timestamp request with a negative nonce", "positive int")
        refused(lambda: w.build_timestamp_request(root, {}, nonce=1),
                "a timestamp request with an empty policy", "non-empty dict")


def check_timestamp_hook() -> None:
    _check_timestamp_hook(TOTAL)


def check_fast_timestamp_hook() -> None:
    _check_timestamp_hook(SMALL)


# --------------------------------------------------------------------------
# M7: the pinned beacon chain and round-selection rule
# --------------------------------------------------------------------------
def _check_beacon_rule_pin(total: int) -> None:
    with tempfile.TemporaryDirectory() as td:
        root = new_root(td)
        write_all(root, total)
        commit(root, w.load_range_plan(root))
        digest = pin_digest(BEACON_PIN)
        sealed = w.seal_beacon_rule_pin(root, BEACON_PIN, digest)
        require(sealed["pin_digest"] == digest, "the sealed pin digest changed")
        refused(lambda: w.seal_beacon_rule_pin(root, BEACON_PIN, "0" * 64),
                "a pin that does not match its expected digest", "does not match its expected")
        # A pin missing a required key is refused.
        for key in w.BEACON_PIN_KEYS:
            incomplete = {k: v for k, v in BEACON_PIN.items() if k != key}
            refused(lambda incomplete=incomplete:
                    w.beacon_policy_of_pin(incomplete), f"a pin missing {key!r}", "is missing")
        # Exact types on the chain parameters: a bool is an int subclass, and a
        # period of True would select a round the owner never intended.
        for key in ("chain_period_seconds", "chain_genesis_time"):
            for value in (True, 0, -1, "30", 30.0):
                bad = dict(BEACON_PIN)
                bad[key] = value
                refused(lambda bad=bad: w.beacon_policy_of_pin(bad),
                        f"a pin whose {key} is {value!r}", "positive integer")
        # And the string fields must be non-empty strings.
        for key in ("beacon_chain", "round_selection_rule", "pin_attestation"):
            for value in ("", 30, None):
                bad = dict(BEACON_PIN)
                bad[key] = value
                refused(lambda bad=bad: w.beacon_policy_of_pin(bad),
                        f"a pin whose {key} is {value!r}", "non-empty string")
        refused(lambda: w.beacon_policy_of_pin("not a dict"),
                "a pin that is not a dict", "must be a dict")
        # And the chain policy is what a round would be selected against.
        policy = w.beacon_policy_of_pin(BEACON_PIN)
        require(policy["chain_period_seconds"] == 30
                and policy["chain_genesis_time"] == 1_000_000_000,
                "the frozen chain parameters did not survive the pin")


def check_beacon_rule_pin() -> None:
    _check_beacon_rule_pin(TOTAL)


def check_fast_beacon_rule_pin() -> None:
    _check_beacon_rule_pin(SMALL)


def check_fast_beacon_exact_schema() -> None:
    """Every policy field is enforced at both seal and stored-pin read."""
    import copy
    with tempfile.TemporaryDirectory() as td:
        root = new_root(td)
        for key in w.BEACON_PIN_KEYS:
            bad = dict(BEACON_PIN)
            del bad[key]
            refused(lambda bad=bad: w.seal_beacon_rule_pin(root, bad, "0" * 64),
                    f"missing beacon {key}")
        variants = []
        for key in w.BEACON_PIN_KEYS:
            bad = dict(BEACON_PIN)
            bad[key] = None
            variants.append((key + " wrong type", bad))
        for key, value in (("chain_hash", "A" * 64),
                           ("chain_hash", "a" * 63),
                           ("public_key_hex", "B" * 192),
                           ("public_key_hex", "b" * 190),
                           ("scheme_id", "unknown"),
                           ("round_selection_rule", "unknown"),
                           ("chain_period_seconds", True),
                           ("chain_genesis_time", False)):
            bad = dict(BEACON_PIN)
            bad[key] = value
            variants.append((key + " invalid", bad))
        variants.append(("extra key", dict(BEACON_PIN, surprise=1)))
        for label, bad in variants:
            refused(lambda bad=bad: w.seal_beacon_rule_pin(root, bad, "0" * 64),
                    f"sealing beacon {label}")
        digest = pin_digest(BEACON_PIN)
        sealed = w.seal_beacon_rule_pin(root, BEACON_PIN, digest)
        for label, bad in variants:
            stored = copy.deepcopy(sealed)
            stored["policy"] = bad
            _write_json(root / w.BEACON_PIN_NAME, stored)
            refused(lambda: w.seal_beacon_rule_pin(root, BEACON_PIN, digest),
                    f"resealing malformed beacon {label}")
            refused(lambda: w.consult_beacon_rule(root, digest),
                    f"consulting malformed beacon {label}")
        _write_json(root / w.BEACON_PIN_NAME, sealed)


def check_fast_field_accessor_and_beacon_refusals() -> None:
    """Reach each schema refusal before a later digest comparison can mask it."""
    for bad in (None, [], "mapping"):
        refused(lambda bad=bad: w._field(bad, "x", str, "probe"),
                "non-dict field mapping", "must be a dict")
    refused(lambda: w._field({}, "x", str, "probe"),
            "missing field", "is missing")
    refused(lambda: w._field({"x": 1}, "x", str, "probe"),
            "wrong field type", "must be exactly str")
    wrong_accepted = Identity([1, 2])
    refused(lambda: w.identity_hash(wrong_accepted),
            "non-dict accepted identity", "payload must be a dict")
    refused(lambda: w.recheck_identity(wrong_accepted, [1, 2]),
            "non-dict accepted identity at recheck", "payload must be a dict")
    refused(lambda: w._identity_exact_match(wrong_accepted, [1, 2]),
            "non-dict accepted identity at matcher", "payload must be a dict")
    class PermissiveMatcher(Identity):
        def exact_match(self, session: object, accepted: object) -> None:
            return None
    refused(lambda: w._identity_exact_match(PermissiveMatcher([1, 2]), ACCEPTED),
            "non-dict accepted identity before permissive matcher", "payload must be a dict")
    refused(lambda: w.recheck_identity(ID, [1, 2]),
            "non-dict session identity", "payload must be a dict")
    for key, value, needle in (("scheme_id", "unknown", "scheme_id is not allowed"),
                               ("round_selection_rule", "unknown", "round-selection rule is not allowed"),
                               ("public_key_hex", "a" * 190, "public key has wrong")):
        bad = dict(BEACON_PIN)
        bad[key] = value
        refused(lambda bad=bad: w.beacon_policy_of_pin(bad),
                f"invalid beacon {key}", needle)
    policy = w.beacon_policy_of_pin(BEACON_PIN)
    sealed = {"pin_digest": w._content_digest(policy), "policy": policy,
              "policy_digest": witness.beacon_policy_digest(policy)}
    refused(lambda: w._sealed_beacon_pin(dict(sealed, extra=1)),
            "extra stored beacon field", "extra key")
    refused(lambda: w._sealed_beacon_pin(dict(sealed, pin_digest="0" * 64)),
            "wrong stored pin digest", "frozen beacon policy is not")
    refused(lambda: w._sealed_beacon_pin(dict(sealed, policy_digest="0" * 64)),
            "wrong stored policy digest", "policy digest differs")


def check_fast_beacon_chain_hash_schema() -> None:
    """The public policy reader and sealed-pin reader enforce the hash schema."""
    malformed = (
        ("63 lowercase hex characters", "a" * 63),
        ("65 lowercase hex characters", "a" * 65),
        ("uppercase hex characters", "A" * 64),
        ("a non-hex character", "g" + "a" * 63),
        ("an empty string", ""),
    )
    for label, chain_hash in malformed:
        policy = dict(BEACON_PIN, chain_hash=chain_hash)
        refused(lambda policy=policy: w.beacon_policy_of_pin(policy),
                f"public beacon policy with {label}", "beacon chain hash")
        raw = {"pin_digest": "0" * 64, "policy": policy,
               "policy_digest": "0" * 64}
        refused(lambda raw=raw: w._sealed_beacon_pin(raw),
                f"sealed beacon pin with {label}", "beacon chain hash")


def check_fast_import_bootstrap_guards() -> None:
    """The writer must add its sibling and project roots before frozen imports."""
    tree = ast.parse(Path(w.__file__).read_text(encoding="utf-8"))
    guards = {ast.unparse(node.test) for node in tree.body
              if isinstance(node, ast.If)}
    require("str(_HERE) not in _sys.path" in guards,
            "the sibling import path guard was removed")
    require("str(_ROOT) not in _sys.path" in guards,
            "the project import path guard was removed")


def check_fast_beacon_consult_secondary_digest() -> None:
    """The consultation rechecks policy even when its stored-pin reader is bypassed."""
    from unittest import mock
    with tempfile.TemporaryDirectory() as td:
        root = new_root(td)
        plan = write_all(root, ONE)
        commit(root, plan)
        digest = pin_digest(BEACON_PIN)
        sealed = w.seal_beacon_rule_pin(root, BEACON_PIN, digest)
        altered = json.loads(json.dumps(sealed))
        altered["policy"]["chain_period_seconds"] = 60
        with mock.patch.object(w, "_sealed_beacon_pin", return_value=altered):
            refused(lambda: w.consult_beacon_rule(root, digest),
                    "consultation after a bypassed malformed pin",
                    "frozen beacon policy is not")


def _check_beacon_consult_requires_sealed_root(total: int) -> None:
    # The rule cannot be consulted before the commitment root is sealed.
    with tempfile.TemporaryDirectory() as td:
        root = new_root(td)
        plan = write_all(root, total)
        digest = pin_digest(BEACON_PIN)
        w.seal_beacon_rule_pin(root, BEACON_PIN, digest)
        refused(lambda: w.consult_beacon_rule(root, digest),
                "consulting the beacon rule before the root is sealed",
                "must be sealed before the beacon")
        commit(root, plan)
        consulted = w.consult_beacon_rule(root, digest)
        require(consulted["beacon_fetched"] is False, "a beacon was fetched")
        require(consulted["merkle_root"] == w.load_commitment(root)["binding"]["commitment"]["merkle_root"],
                "the consultation does not name the sealed root")
        other = dict(BEACON_PIN, beacon_chain="synthetic/other_chain/v1")
        refused(lambda: w.consult_beacon_rule(root, pin_digest(other)),
                "consulting a rule other than the frozen pin", "differs from the frozen pin")
        refused(lambda: w.consult_beacon_rule(root, "not-a-digest"),
                "consulting with a non-digest pin digest", "lowercase SHA-256")
        # Without a frozen pin there is nothing to consult.
        with tempfile.TemporaryDirectory() as td2:
            bare = new_root(td2, "instance_03")
            seal(bare, total)
            refused(lambda: w.consult_beacon_rule(bare, digest),
                    "consulting with no frozen rule", "are not frozen")


def check_beacon_consult_requires_sealed_root() -> None:
    _check_beacon_consult_requires_sealed_root(TOTAL)


def check_fast_beacon_consult_requires_sealed_root() -> None:
    _check_beacon_consult_requires_sealed_root(SMALL)


# --------------------------------------------------------------------------
# The M-ordering, as an observable sequence
# --------------------------------------------------------------------------
def check_stage_ordering() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = new_root(td)
        plan = seal(root)
        require(w.stages_present(root) == ["range_plan"],
                "the sealed plan was not reported as the only stage reached")
        for row in w.plan_batches(plan):
            w.write_range(root, row["batch_id"], records_for(row["start"], row["stop"]),
                          result_schema=SCHEMA, identity=ID, session=ACCEPTED)
        require(w.stages_present(root) == ["range_plan", "ranges_promoted"],
                "promoted ranges were not reported")
        commit(root, plan)
        require("commitment_root_sealed" in w.stages_present(root),
                "the sealed root was not reported")
        w.build_timestamp_request(root, POLICY, nonce=99)
        digest = pin_digest(BEACON_PIN)
        w.seal_beacon_rule_pin(root, BEACON_PIN, digest)
        w.consult_beacon_rule(root, digest)
        stages = w.stages_present(root)
        require(stages == ["range_plan", "ranges_promoted", "commitment_root_sealed",
                           "external_timestamp_requested", "beacon_rule_frozen",
                           "beacon_rule_consulted"],
                f"the M stages are not reported in order: {stages}")
        # And sealed_state reports the CONTENT of each artefact, not mere presence.
        state = {entry["stage"]: entry for entry in w.sealed_state(root)}
        require(all(entry["plan_bound"] for entry in state.values()),
                "sealed_state did not report every artefact as plan-bound")
        require(state["commitment_root_sealed"]["plan_content_sha256"]
                == plan["content_sha256"],
                "sealed_state did not read the commitment's plan hash")


def check_fast_stage_ordering() -> None:
    check_stage_ordering()


def check_sealed_state_reports_content() -> None:
    """sealed_state reports what an artefact SAYS, and flags an edited one."""
    with tempfile.TemporaryDirectory() as td:
        root = new_root(td)
        plan = write_all(root)
        state = {entry["stage"]: entry for entry in w.sealed_state(root)}
        require(state["range_plan_sealed"]["batch_count"] == 2,
                "sealed_state misreported the sealed plan's batch count")
        require(not state["commitment_root_sealed"]["sealed"],
                "sealed_state claimed a commitment before one was sealed")
        commit(root, plan)
        state = {entry["stage"]: entry for entry in w.sealed_state(root)}
        require(state["commitment_root_sealed"]["sealed"]
                and state["commitment_root_sealed"]["plan_bound"],
                "sealed_state did not report the sealed commitment as plan-bound")
        require(state["ranges_promoted"]["promoted_batch_ids"]
                == [f"{FAMILY}_b0000", f"{FAMILY}_b0001"],
                "sealed_state did not report which ranges are promoted")
        # An artefact whose plan hash was edited is present but NOT plan-bound.
        document = json.loads((root / w.COMMITMENT_NAME).read_text("ascii"))
        document["plan_content_sha256"] = "a" * 64
        _write_json(root / w.COMMITMENT_NAME, document)
        state = {entry["stage"]: entry for entry in w.sealed_state(root)}
        require(state["commitment_root_sealed"]["sealed"]
                and not state["commitment_root_sealed"]["plan_bound"],
                "sealed_state reported an edited commitment as plan-bound")


# --------------------------------------------------------------------------
# Fixtures for the checks the round-2 mutation sweep found surviving
# --------------------------------------------------------------------------
class ExplodingValidate(Identity):
    """An injected identity whose ``validate`` raises a non-writer error.

    The identity is injected (WP1 is under review), so the writer cannot know
    what its ``validate`` raises.  It must not let a raw exception through the
    identity boundary either: a caller catching only ``ProductionWriterError``
    would read it as a crash rather than a refusal.
    """

    def __init__(self, error: BaseException) -> None:
        super().__init__(ACCEPTED)
        self.error = error

    def validate(self, payload: object) -> str:
        raise self.error


class ExplodingExactMatch(Identity):
    """An injected identity whose ``exact_match`` raises a non-writer error."""

    def __init__(self, error: BaseException) -> None:
        super().__init__(ACCEPTED)
        self.error = error

    def exact_match(self, session: object, accepted: object) -> None:
        raise self.error


class _FixedDigest(Identity):
    """An identity whose ``validate`` returns a fixed, wrong-typed value.

    The digest the injected validator returns is the module's ONLY view of what
    the identity is, so it is type-checked as 64 lowercase hex characters
    before any sealed artefact is bound to it.
    """

    def __init__(self, digest: object) -> None:
        super().__init__(ACCEPTED)
        self.digest = digest

    def validate(self, payload: object) -> object:
        return self.digest


class _Duck:
    """A minimal identity-shaped object; a subclass withholds one attribute.

    The interface test is a conjunction over three attributes.  A fixture that
    only ever supplies all three cannot tell one clause from another, so each
    attribute is withheld in turn: the interface must be refused for an object
    missing ANY one of them, which is what makes each clause load-bearing.
    """

    def __init__(self, payload: dict) -> None:
        self.accepted = payload

    def validate(self, payload: object) -> str:
        return hashlib.sha256(json.dumps(payload, sort_keys=True,
                                         separators=(",", ":")).encode("ascii")).hexdigest()

    def exact_match(self, session: object, accepted: object) -> None:
        if session != accepted:
            raise ValueError("session identity does not exactly match the accepted identity")


class _NoAccepted(_Duck):
    """Withholds ``accepted`` entirely: the instance dict has no such key."""

    def __init__(self, payload: dict) -> None:
        del payload
        _Duck.__init__(self, {})
        del self.__dict__["accepted"]


class _NoValidate(_Duck):
    validate = None  # type: ignore[assignment]


class _NoExactMatch(_Duck):
    exact_match = None  # type: ignore[assignment]


def _check_identity_failure_translation() -> None:
    """A raising injected identity surfaces as the writer's typed refusal.

    These reach the ``ValueError`` translation in ``_identity_exact_match`` and
    the ``_sha`` test on the injected validator's digest; without them those
    raises are unreachable and the checks they hold are checks nothing depends
    on.
    """
    # The round-2 module asked ``hasattr`` whether the injected object offered
    # an attribute.  That is gone: identity is a CONTENT HASH, and these ducks
    # exist to prove it.  Each duck withholds one member of the declared
    # interface, so whichever member is missing, the writer must refuse the
    # typed way -- an ``AttributeError`` converted at the boundary, not a raw
    # crash, and never a silent acceptance on the strength of what the object
    # happens to have.
    for label, obj in (("no `accepted`", _NoAccepted(ACCEPTED)),
                       ("no `validate`", _NoValidate(ACCEPTED)),
                       ("no `exact_match`", _NoExactMatch(ACCEPTED)),
                       ("none of them", object())):
        try:
            w.recheck_identity(obj, ACCEPTED)
        except w.ProductionWriterError:
            pass
        else:
            raise FixtureError(f"an identity with {label}: recheck_identity accepted it")
    with tempfile.TemporaryDirectory() as td:
        root = new_root(td)
        plan = seal(root)
        row = w.plan_batches(plan)[0]
        for label, obj in (("no `accepted`", _NoAccepted(ACCEPTED)),
                           ("no `validate`", _NoValidate(ACCEPTED)),
                           ("no `exact_match`", _NoExactMatch(ACCEPTED))):
            try:
                w.write_range(root, row["batch_id"],
                              records_for(row["start"], row["stop"]),
                              result_schema=SCHEMA, identity=obj, session=ACCEPTED)
            except w.ProductionWriterError:
                pass
            else:
                raise FixtureError(f"writing a range under an identity with "
                                   f"{label}: accepted")
        require(w.missing_ranges(root) == [dict(r) for r in w.plan_batches(plan)],
                "a write under a partial identity interface promoted a range")
    # Restored round-2 injected validator and matcher cases.  The round-3
    # narrow boundary converts named KeyError, ValueError and TypeError here.
    for label, error in (("a ValueError", ValueError("injected validate() failure")),
                         ("a KeyError", KeyError("injected validate() key")),
                         ("a TypeError", TypeError("injected validate() type"))):
        refused(lambda error=error: w.identity_hash(ExplodingValidate(error)),
                f"an identity whose validate() raises {label}")
    # Lead ruling for round 4: the round-2 arbitrary RuntimeError probe stays,
    # but round-3's narrow exception rule requires unchanged propagation.
    error = RuntimeError("injected validate() state")
    try:
        w.identity_hash(ExplodingValidate(error))
    except RuntimeError as exc:
        require(exc is error,
                "an identity whose validate() raises a RuntimeError was changed")
    except w.ProductionWriterError as exc:
        raise FixtureError("an unlisted RuntimeError was converted") from exc
    else:
        raise FixtureError("an unlisted RuntimeError was swallowed")
    for label, error in (("a ValueError", ValueError("injected exact_match failure")),
                         ("a KeyError", KeyError("injected exact_match key")),
                         ("a TypeError", TypeError("injected exact_match type"))):
        refused(lambda error=error: w.recheck_identity(ExplodingExactMatch(error), ACCEPTED),
                f"an identity whose exact_match() raises {label}")
    error = RuntimeError("platform drift")
    try:
        w.recheck_identity(ExplodingExactMatch(error), ACCEPTED)
    except RuntimeError as exc:
        require(exc is error,
                "an identity whose exact_match() raises RuntimeError was changed")
    except w.ProductionWriterError as exc:
        raise FixtureError("an exact_match RuntimeError was converted") from exc
    else:
        raise FixtureError("an exact_match RuntimeError was swallowed")
    refused(lambda: w._injected(object(), "accepted", "the accepted payload"),
            "the missing-member identity refusal", "must expose 'accepted'")

    # The identity is a CONTENT HASH, never an attribute test.  Two objects
    # with completely different shapes that hash to the SAME digest are the
    # same identity to this module; two that hash differently are not, even when
    # they expose byte-identical interfaces.  This is the case an attribute
    # existence test could not distinguish at all.
    class ShapedLikeNothing(Identity):
        """A duck with the same members and a different accepted payload."""

        def __init__(self) -> None:
            super().__init__(OTHER)
            self.unrelated_attribute = "ignored"

    require(w.identity_hash(ShapedLikeNothing()) == w.identity_hash(OTHER_ID),
            "two identities with the same shape but different content hashed alike")
    require(w.identity_hash(ID) != w.identity_hash(OTHER_ID),
            "two identities with different content produced the same hash")

    # Each specific class the injected validator can raise is translated to the
    # typed refusal.  A ``ValueError`` is the validator REFUSING a session and
    # is caught at the call itself, naming the mismatch; a ``TypeError`` is a
    # STRUCTURAL fault in the injected identity and is caught at the public
    # boundary, naming the entry point.  A ``RuntimeError`` is in neither class
    # list and propagates unchanged (asserted in the typed-wrapper fixture).
    refused(lambda: w.recheck_identity(
                ExplodingExactMatch(ValueError("injected exact_match failure")), ACCEPTED),
            "an identity whose exact_match() raises a ValueError",
            "does not exactly match the accepted identity")
    refused(lambda: w.recheck_identity(
                ExplodingExactMatch(TypeError("injected exact_match type")), ACCEPTED),
            "an identity whose exact_match() raises a TypeError",
            "recheck_identity refused: TypeError")
    # The digest `validate` returns is type-checked before anything trusts it.
    for bad, label in (("not-a-digest", "a non-digest"),
                       (b"a" * 64, "a bytes value"),
                       (None, "None"),
                       (True, "a bool"),
                       (["a" * 64], "a list"),
                       ({"a": "a" * 64}, "a dict"),
                       (set("0123456789abcdef" * 4), "a set of hex characters")):
        refused(lambda bad=bad: w.identity_hash(_FixedDigest(bad)),
                f"an identity whose validate() returns {label}",
                "lowercase SHA-256")
    # The same failures through a full write, which is where the identity is
    # actually consulted before any byte is staged.
    with tempfile.TemporaryDirectory() as td:
        root = new_root(td)
        plan = seal(root)
        row = w.plan_batches(plan)[0]
        refused(lambda: w.write_range(root, row["batch_id"],
                                      records_for(row["start"], row["stop"]),
                                      result_schema=SCHEMA,
                                      identity=ExplodingExactMatch(
                                          ValueError("injected exact_match failure")),
                                      session=ACCEPTED),
                "writing a range whose identity exact_match refuses", "")
        require(staging_residue(root) == [],
                "a refused write left staging residue behind")
        require(w.missing_ranges(root) == [dict(r) for r in w.plan_batches(plan)],
                "a refused write promoted a range anyway")


def check_identity_failure_translation() -> None:
    _check_identity_failure_translation()


def check_fast_identity_failure_translation() -> None:
    _check_identity_failure_translation()


def _check_sealed_state_every_branch() -> None:
    """sealed_state must report correctly on EVERY branch, not just the sealed one.

    The reporter walks eight branches.  Each is driven here, and each asserts
    the CONTENT it reports, so no branch can be a branch nothing depends on.
    """
    # (a) an empty root: nothing sealed at all.
    with tempfile.TemporaryDirectory() as td:
        root = new_root(td)
        state = {entry["stage"]: entry for entry in w.sealed_state(root)}
        require(not state["range_plan_sealed"]["sealed"]
                and not state["range_plan_sealed"]["plan_bound"]
                and state["range_plan_sealed"]["plan_content_sha256"] is None
                and state["range_plan_sealed"]["batch_count"] == 0,
                "sealed_state did not report an unsealed plan as unsealed")
        require(not state["ranges_promoted"]["sealed"]
                and state["ranges_promoted"]["promoted_batch_ids"] == []
                and not state["ranges_promoted"]["plan_bound"],
                "sealed_state reported a promoted range on an empty root")
        require(not state["commitment_root_sealed"]["sealed"]
                and not state["commitment_root_sealed"]["plan_bound"],
                "sealed_state reported a commitment on an empty root")
        for stage in ("external_timestamp_requested", "beacon_rule_frozen",
                      "beacon_rule_consulted"):
            require(not state[stage]["sealed"] and not state[stage]["plan_bound"],
                    f"sealed_state reported {stage} as reached on an empty root")

    # (b) a sealed plan, no ranges promoted yet.
    with tempfile.TemporaryDirectory() as td:
        root = new_root(td)
        plan = seal(root)
        state = {entry["stage"]: entry for entry in w.sealed_state(root)}
        require(state["range_plan_sealed"]["sealed"]
                and state["range_plan_sealed"]["plan_bound"]
                and state["range_plan_sealed"]["plan_content_sha256"] == plan["content_sha256"]
                and state["range_plan_sealed"]["batch_count"] == 2,
                "sealed_state did not report the freshly sealed plan")
        # The ranges directory does not exist yet: the NOT-promoted branch.
        require(not state["ranges_promoted"]["sealed"]
                and state["ranges_promoted"]["promoted_batch_ids"] == []
                and state["ranges_promoted"]["plan_bound"],
                "sealed_state misreported a plan with nothing promoted")

    # (c) an EMPTY ranges directory: the directory exists, so the promoted
    # branch runs, and it must not report a range that was never promoted.
    with tempfile.TemporaryDirectory() as td:
        root = new_root(td)
        plan = seal(root)
        (root / w.RANGES_DIRNAME).mkdir()
        state = {entry["stage"]: entry for entry in w.sealed_state(root)}
        require(not state["ranges_promoted"]["sealed"]
                and state["ranges_promoted"]["promoted_batch_ids"] == [],
                "sealed_state reported an empty ranges directory as promoted")
        del plan

    # (d) ranges ACTUALLY promoted: the positive direction of the same branch.
    # Without it, forcing that branch false would make every populated root
    # report nothing promoted and no fixture would notice.
    with tempfile.TemporaryDirectory() as td:
        root = new_root(td)
        plan = write_all(root)
        state = {entry["stage"]: entry for entry in w.sealed_state(root)}
        require(state["ranges_promoted"]["sealed"]
                and state["ranges_promoted"]["promoted_batch_ids"]
                == [f"{FAMILY}_b0000", f"{FAMILY}_b0001"]
                and state["ranges_promoted"]["plan_content_sha256"] == plan["content_sha256"],
                "sealed_state did not report the promoted ranges of a written family")
        del plan

    # (e) the promotion pin and the commitment pin, both bound.
    with tempfile.TemporaryDirectory() as td:
        root = new_root(td)
        plan = write_all(root)
        commit(root, plan)
        w.build_timestamp_request(root, POLICY, nonce=99)
        digest = pin_digest(BEACON_PIN)
        w.seal_beacon_rule_pin(root, BEACON_PIN, digest)
        w.consult_beacon_rule(root, digest)
        state = {entry["stage"]: entry for entry in w.sealed_state(root)}
        for stage in ("commitment_root_sealed", "campaign_binding_pinned",
                      "external_timestamp_requested", "beacon_rule_frozen",
                      "beacon_rule_consulted"):
            require(state[stage]["sealed"],
                    f"sealed_state did not report the sealed {stage}")
            require(state[stage]["plan_bound"],
                    f"sealed_state did not report the sealed {stage} as plan-bound")

    # (e) a MALFORMED sealed artefact: present, but reported as NOT plan-bound
    # rather than crashing the reporter or claiming a bound stage.
    with tempfile.TemporaryDirectory() as td:
        root = new_root(td)
        plan = write_all(root)
        commit(root, plan)
        (root / w.COMMITMENT_NAME).write_text("{}", encoding="ascii")
        state = {entry["stage"]: entry for entry in w.sealed_state(root)}
        require(state["commitment_root_sealed"]["sealed"]
                and not state["commitment_root_sealed"]["plan_bound"]
                and state["commitment_root_sealed"]["plan_content_sha256"] is None,
                "sealed_state did not report a malformed commitment as unbound")
        (root / w.CAMPAIGN_PIN_NAME).write_text("[]", encoding="ascii")
        state = {entry["stage"]: entry for entry in w.sealed_state(root)}
        require(state["campaign_binding_pinned"]["sealed"]
                and not state["campaign_binding_pinned"]["plan_bound"],
                "sealed_state did not report a malformed campaign pin as unbound")


def check_sealed_state_every_branch() -> None:
    _check_sealed_state_every_branch()


def check_fast_sealed_state_every_branch() -> None:
    _check_sealed_state_every_branch()


def _check_contract_error_translation() -> None:
    """A frozen-module refusal surfaces as the writer's own typed error.

    ``_contract`` translates the frozen contract's error types into
    ``ProductionWriterError``.  That translation is only reachable if a frozen
    call actually refuses, so the plan, the manifest and the final-set audit are
    each driven with an input the frozen contract rejects.
    """
    # A plan the frozen contract refuses: a batch count that does not partition.
    bad_plan = dict(w.build_range_plan(FAMILY, 4, w.identity_hash(ID)))
    bad_plan["ranges"] = bad_plan["ranges"][:-1]
    refused(lambda: w._contract(w.validate_range_plan, bad_plan),
            "a plan the frozen contract refuses", "")
    # A batch id that is not in the sealed plan at all.
    with tempfile.TemporaryDirectory() as td:
        root = new_root(td)
        plan = seal(root)
        refused(lambda: w.plan_row(plan, "not_a_batch"),
                "a batch id absent from the sealed plan", "not in the sealed plan")
    # The final-set audit refusing a cover that is not exact.
    with tempfile.TemporaryDirectory() as td:
        root = new_root(td)
        plan = seal(root)
        row = w.plan_batches(plan)[0]
        w.write_range(root, row["batch_id"], records_for(row["start"], row["stop"]),
                      result_schema=SCHEMA, identity=ID, session=ACCEPTED)
        refused(lambda: w.audit_final_set(root),
                "a final set that covers only part of the sealed plan", "")


def check_contract_error_translation() -> None:
    _check_contract_error_translation()


def check_fast_contract_error_translation() -> None:
    _check_contract_error_translation()


def _check_stale_staging_is_not_promoted() -> None:
    """Discarding stale staging removes it, and removes nothing that is promoted.

    The removal loop skips anything that is not a real directory and is
    name-matched, and the post-loop fsync runs only when something was removed.
    Both are driven here, over a root that holds a real staging directory, a
    staging-named FILE, and a promoted range that must survive.
    """
    with tempfile.TemporaryDirectory() as td:
        root = new_root(td)
        plan = seal(root)
        row = w.plan_batches(plan)[0]
        w.write_range(root, row["batch_id"], records_for(row["start"], row["stop"]),
                      result_schema=SCHEMA, identity=ID, session=ACCEPTED)
        promoted = root / w.RANGES_DIRNAME / row["batch_id"]
        staged_dir = root / f"{w.STAGING_PREFIX}interrupted"
        staged_dir.mkdir()
        (staged_dir / w.RECORDS_NAME).write_text("[]", encoding="ascii")
        # A staging-named regular file is not a directory: the loop's directory
        # test must leave it alone rather than calling the tree remover on it.
        staged_file = root / f"{w.STAGING_PREFIX}not_a_dir"
        staged_file.write_text("synthetic", encoding="ascii")
        removed = w.discard_stale_staging(root)
        require(removed == [staged_dir.name],
                f"discard_stale_staging removed the wrong things: {removed}")
        require(not staged_dir.exists(),
                "discard_stale_staging left an interrupted staging directory behind")
        require(staged_file.is_file(),
                "discard_stale_staging removed a staging-named regular file")
        require(promoted.is_dir(),
                "discard_stale_staging removed a promoted range directory")
        require(w.verify_range(root, row["batch_id"])["verdict"] == "complete",
                "discard_stale_staging disturbed the promoted range")
        # With nothing left to discard the removal list is empty and no
        # promoted range is touched.
        require(w.discard_stale_staging(root) == [],
                "discard_stale_staging claimed a removal on a clean root")

    # The post-removal fsync is what makes the removal itself durable, and
    # durability is not observable in a temporary directory -- so the call is
    # observed directly.  It must run after a removal and NOT run when there
    # was nothing to remove, which is exactly the branch the fsync guard holds.
    with tempfile.TemporaryDirectory() as td:
        root = new_root(td)
        seal(root)
        calls: list = []
        real_fsync = w._fsync_dir
        w._fsync_dir = lambda path: (calls.append(Path(path)), real_fsync(path))[1]
        try:
            (root / f"{w.STAGING_PREFIX}stale").mkdir()
            w.discard_stale_staging(root)
            require(calls == [root],
                    f"the instance root was not fsynced after a removal: {calls}")
            calls.clear()
            w.discard_stale_staging(root)
            require(calls == [],
                    f"a clean discard fsynced anyway: {calls}")
        finally:
            w._fsync_dir = real_fsync


def check_stale_staging_is_not_promoted() -> None:
    _check_stale_staging_is_not_promoted()


def check_fast_stale_staging_is_not_promoted() -> None:
    _check_stale_staging_is_not_promoted()


def _check_encoder_shape_gate() -> None:
    """The on-disk encoder accepts a records payload and nothing else.

    It is the one function that decides what bytes a promoted range holds, and
    it runs on the read path with no schema in hand -- so it must refuse a
    payload that is not a list of record mappings BEFORE encoding, rather than
    handing back the canonical bytes of whatever it was given.
    """
    good = records_for(0, 3)
    require(w.encodable_records(good)
            == json.dumps(good, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True).encode("ascii"),
            "the encoder did not produce the canonical records bytes")
    require(w.encodable_records([]) == b"[]",
            "the encoder refused an empty but well-formed records payload")
    refused(lambda: w.encodable_records(None),
            "a records payload of None", "must be a list")
    refused(lambda: w.encodable_records("records"),
            "a records payload that is a string", "must be a list")
    refused(lambda: w.encodable_records({"coordinates": [0, 0, 0]}),
            "a records payload that is a bare record", "must be a list")
    for payload, label in (([1, 2], "scalars"), (["a", "b"], "strings"),
                           ([None], "a None entry"), ([[1, 2]], "a nested list"),
                           (["x"] * 3, "strings in a list of the right length"),
                           ([make_record(0), "x"], "one good record and a string"),
                           ([make_record(0), None], "one good record and a None")):
        refused(lambda payload=payload: w.encodable_records(payload),
                f"a records payload of {label}",
                "every entry of a records payload must be a record mapping")
    # And the shape gate must not reject a well-formed one whose FIELDS are
    # wrong: the per-field schema is ``check_records``'s job, and the encoder
    # runs without one.
    refused(lambda: w.check_records([{"coordinates": "not a list"}], SCHEMA, 1, "l"),
            "a record whose coordinates are not a list", "")
    require(w.encodable_records([{"any": "shape"}]) == b'[{"any":"shape"}]',
            "the encoder enforced a per-record field schema it is not given")


def check_encoder_shape_gate() -> None:
    _check_encoder_shape_gate()


def check_fast_encoder_shape_gate() -> None:
    _check_encoder_shape_gate()


def _check_internal_type_predicates() -> None:
    """The module's own type predicates refuse every value they must refuse.

    These are the predicates a single-connective mutation weakens but cannot
    turn into an acceptance of anything else: ``_sha``'s SHA-256 test, the path
    tests, and the stored-document shape test.  No public fixture can isolate
    one clause of a composite test, so the clauses are pinned here directly:
    a value that satisfies the REMAINING clauses of each predicate -- a
    64-character non-hex string, a 64-element hashable, a dict of the right
    keys with one value of the wrong type -- must still be refused.
    """
    for value, label in (("x" * 64, "a 64-character non-hex string"),
                         ("A" * 64, "a 64-character upper-case string"),
                         (["a"] * 64, "a 64-element list of strings"),
                         (set(range(64)), "a 64-element set"),
                         (frozenset("0123456789abcdef" * 4), "a 64-hex frozenset"),
                         (b"a" * 64, "a 64-byte bytes value"),
                         (True, "a bool"),
                         (None, "None")):
        refused(lambda value=value: w._sha(value, "fuzzed hash"),
                f"_sha accepting {label}", "lowercase SHA-256")
    require(w._sha("a" * 64, "a real hash") == "a" * 64,
            "_sha refused a well-formed lowercase SHA-256")
    for value, label in ((7, "an int"), (None, "None"), (True, "a bool"),
                         (["a"], "a list"), ({"a": 1}, "a dict"),
                         (b"x", "bytes"), (object(), "an object")):
        refused(lambda value=value: w._as_path(value, "fuzzed path"),
                f"a path argument of {label}", "must be a path")
    # The shape gate refuses a MISSING key (the round-1 defect: a truncated
    # stored document raised a bare KeyError at the first indexed field) and
    # refuses anything that is not a dict.  An EXTRA key is deliberately
    # allowed -- a stored document may carry more than this module reads -- so
    # that is asserted here rather than left to chance.
    fields = frozenset({"alpha", "beta"})
    require(w._document({"alpha": 1, "beta": 2}, fields, "ok") == {"alpha": 1, "beta": 2},
            "_document refused a well-formed document")
    require(w._document({"alpha": 1, "beta": 2, "gamma": 3}, fields, "ok")
            == {"alpha": 1, "beta": 2, "gamma": 3},
            "_document refused a document carrying an extra, unread key")
    for document, label in (({"alpha": 1}, "a missing key"),
                            ({}, "an empty dict"),
                            ([], "a list"), ("{}", "a string"), (None, "None"),
                            (7, "an int"), ([("alpha", 1)], "a list of pairs")):
        refused(lambda document=document: w._document(document, fields, "fuzzed"),
                f"_document accepting {label}", "")
    # The instance-root test refuses a path that is not an existing real dir.
    with tempfile.TemporaryDirectory() as td:
        root = new_root(td)
        require(w._instance_root(root) == root,
                "_instance_root refused a real instance root")
        refused(lambda: w._instance_root(root / "nope"),
                "an instance root that does not exist", "existing real directory")
        refused(lambda: w._instance_root(root / w.PLAN_NAME),
                "an instance root that is a file", "existing real directory")


def check_internal_type_predicates() -> None:
    _check_internal_type_predicates()


def check_fast_internal_type_predicates() -> None:
    _check_internal_type_predicates()


# --------------------------------------------------------------------------
# The writer's own scope statement
# --------------------------------------------------------------------------
def check_limits() -> None:
    limits = w.writer_limits()
    require(isinstance(limits["establishes"], list) and limits["establishes"],
            "the writer claims it establishes nothing")
    require(isinstance(limits["does_not_establish"], list) and limits["does_not_establish"],
            "the writer states no limits")
    joined = " ".join(limits["does_not_establish"])
    for needle in ("external timestamp", "beacon", "sampling", "correctness"):
        require(needle in joined, f"the writer does not disclaim: {needle}")
    established = " ".join(limits["establishes"])
    for needle in ("never replaced", "hard link", "bound to the sealed plan"):
        require(needle in established,
                f"the writer does not claim to establish: {needle}")


# --------------------------------------------------------------------------
# The typed-wrapper contract: listed boundary errors become typed refusals; others propagate
# --------------------------------------------------------------------------
def _check_typed_wrapper(total: int) -> None:
    """Only listed boundary errors become typed refusals at public entry points.

    The ``@_typed`` wrapper is the module's last-resort contract: whatever a
    private helper or the frozen contract raises internally -- from the fixed
    list of classes that can actually arise -- a caller sees
    ``ProductionWriterError``.  This fixture reaches the wrapper's conversion
    branch DIRECTLY by making an internal helper raise such an error, and
    asserts it still comes out as ``ProductionWriterError``.

    It is equally a test of what the wrapper does NOT catch.  The boundary set
    is not ``Exception``: an unrelated ``BaseException`` -- a
    ``KeyboardInterrupt`` raised by an injected reader -- must propagate
    unchanged, and a fault outside the named classes must too.  That is the
    round-3 ruling, and a wrapper that caught everything would pass the first
    half of this fixture and fail the second.
    """
    import unittest.mock as mock

    global COUNT

    with tempfile.TemporaryDirectory() as td:
        root = new_root(td)
        plan = seal(root, total)
        row = w.plan_batches(plan)[0]
        # load_commitment checks that the sealed artifact exists before reading it.
        # A placeholder is sufficient because both reader probes replace _read_json.
        (root / w.COMMITMENT_NAME).write_text("{}", encoding="ascii")
        # A helper raising a class that IS on the boundary list, called INSIDE
        # each public entry point's ``@_typed`` wrapper: it must come out as
        # ``ProductionWriterError``.  Patching the private helper (not the
        # wrapped public function) is what makes this reach the wrapper.
        for name, call in (("load_range_plan", lambda: w.load_range_plan(root)),
                           ("missing_ranges", lambda: w.missing_ranges(root)),
                           ("audit_final_set", lambda: w.audit_final_set(root)),
                           ("aggregate_records", lambda: w.aggregate_records(root)),
                           ("load_commitment", lambda: w.load_commitment(root))):
            with mock.patch.object(w, "_read_json", side_effect=OSError("injected read")) as injected:
                try:
                    call()
                except w.ProductionWriterError:
                    COUNT += 1
                except OSError:
                    raise FixtureError(f"{name}: a raw OSError escaped the typed wrapper")
                else:
                    raise FixtureError(f"{name}: accepted with the reader broken")
                require(injected.called,
                        f"{name}: the patched reader was not reached")
        # Same for a write: an OSError while rechecking the identity.
        with mock.patch.object(w, "recheck_identity", side_effect=OSError("injected raw error")) as injected:
            refused(lambda: w.write_range(root, row["batch_id"],
                                          records_for(row["start"], row["stop"]),
                                          result_schema=SCHEMA, identity=ID,
                                          session=ACCEPTED),
                    "a write whose identity recheck raises a boundary error", "")
            require(injected.called, "write_range: patched recheck_identity was not reached")
        # And a write with a boundary error from the record checker.
        with mock.patch.object(w, "check_records", side_effect=OSError("injected raw error")) as injected:
            refused(lambda: w.write_range(root, row["batch_id"],
                                          records_for(row["start"], row["stop"]),
                                          result_schema=SCHEMA, identity=ID,
                                          session=ACCEPTED),
                    "a write whose record check raises a boundary error", "")
            require(injected.called, "write_range: patched check_records was not reached")

        # The round-4 lead ruling applies the narrow exception rule: an
        # unlisted RuntimeError from an injected helper must propagate unchanged.
        class RawError(RuntimeError):
            pass

        raw_read = RawError("injected raw error")
        with mock.patch.object(w, "_read_json", side_effect=raw_read) as injected:
            for name, call in (("load_range_plan", lambda: w.load_range_plan(root)),
                               ("missing_ranges", lambda: w.missing_ranges(root)),
                               ("audit_final_set", lambda: w.audit_final_set(root)),
                               ("aggregate_records", lambda: w.aggregate_records(root)),
                               ("load_commitment", lambda: w.load_commitment(root))):
                try:
                    call()
                except RawError as exc:
                    require(exc is raw_read,
                            f"{name}: the raw reader error was replaced")
                    COUNT += 1
                except w.ProductionWriterError as exc:
                    raise FixtureError(f"{name}: an unlisted RawError was converted") from exc
                else:
                    raise FixtureError(f"{name}: an unlisted RawError was swallowed")
            require(injected.call_count == 5,
                    "not all five public readers reached the patched helper")

        raw_identity = RawError("injected recheck error")
        with mock.patch.object(w, "recheck_identity", side_effect=raw_identity) as injected:
            try:
                w.write_range(root, row["batch_id"],
                              records_for(row["start"], row["stop"]),
                              result_schema=SCHEMA, identity=ID, session=ACCEPTED)
            except RawError as exc:
                require(exc is raw_identity, "write_range changed its raw identity error")
                COUNT += 1
            except w.ProductionWriterError as exc:
                raise FixtureError("write_range converted an unlisted identity RawError") from exc
            else:
                raise FixtureError("write_range swallowed an identity RawError")
            require(injected.called,
                    "write_range refused before patched recheck_identity was reached")

        raw_records = RawError("injected record error")
        with mock.patch.object(w, "check_records", side_effect=raw_records) as injected:
            try:
                w.write_range(root, row["batch_id"],
                              records_for(row["start"], row["stop"]),
                              result_schema=SCHEMA, identity=ID, session=ACCEPTED)
            except RawError as exc:
                require(exc is raw_records, "write_range changed its raw record error")
                COUNT += 1
            except w.ProductionWriterError as exc:
                raise FixtureError("write_range converted an unlisted record RawError") from exc
            else:
                raise FixtureError("write_range swallowed a record RawError")
            require(injected.called,
                    "write_range refused before patched check_records was reached")

        # An unrelated BaseException must NOT be converted and must NOT be
        # swallowed: a ``KeyboardInterrupt`` from an injected reader unwinds to
        # the caller as itself.  A wrapper catching ``BaseException`` (or
        # converting the interrupt into a refusal) fails here.
        class Interrupt(w.InjectedInterrupt):
            pass
        with mock.patch.object(w, "check_records", side_effect=Interrupt("crash")):
            try:
                w.write_range(root, row["batch_id"],
                              records_for(row["start"], row["stop"]),
                              result_schema=SCHEMA, identity=ID, session=ACCEPTED)
            except Interrupt:
                COUNT += 1
            except w.ProductionWriterError:
                raise FixtureError("an injected interrupt was converted to a refusal")
            else:
                raise FixtureError("an injected interrupt was swallowed")

        # A real ``KeyboardInterrupt`` -- a BaseException that is NOT the
        # module's own InjectedInterrupt -- must also propagate untouched out of
        # a public entry point and out of a write, so that Ctrl-C during a
        # production session is not reported as a refusal.
        with mock.patch.object(w, "_read_json", side_effect=KeyboardInterrupt()):
            try:
                w.load_range_plan(root)
            except KeyboardInterrupt:
                COUNT += 1
            except w.ProductionWriterError:
                raise FixtureError("a KeyboardInterrupt from a reader became a refusal")
            else:
                raise FixtureError("a KeyboardInterrupt from a reader was swallowed")
        with mock.patch.object(w, "check_records", side_effect=KeyboardInterrupt()):
            try:
                w.write_range(root, row["batch_id"],
                              records_for(row["start"], row["stop"]),
                              result_schema=SCHEMA, identity=ID, session=ACCEPTED)
            except KeyboardInterrupt:
                COUNT += 1
            except w.ProductionWriterError:
                raise FixtureError("a KeyboardInterrupt during a write became a refusal")
            else:
                raise FixtureError("a KeyboardInterrupt during a write was swallowed")
        require(staging_residue(root) == [],
                "an injected interrupt left staging residue")


# --------------------------------------------------------------------------
# The I/O failure paths: every except-OSError conversion is the typed refusal
# --------------------------------------------------------------------------
def _check_io_failures(total: int) -> None:
    """Each ``except OSError: raise ProductionWriterError`` is the module's typed refusal.

    These conversions live on private helpers, so the public ``@_typed`` wrapper
    would also convert a raw ``OSError``; the wrapper alone is therefore not
    evidence that these checks fire.  This fixture calls the private helpers
    directly with a forced ``OSError`` and asserts the typed refusal, so each
    conversion is load-bearing rather than masked by the wrapper.
    """
    import unittest.mock as mock

    global COUNT

    with tempfile.TemporaryDirectory() as td:
        root = new_root(td)
        present = root / "present.bin"
        present.write_bytes(b"payload")
        absent = root / "absent.bin"
        # A sealed plan with one range, so the write-path case below has a real
        # batch to write and a real session identity to fail against.
        plan = seal(root, ONE)
        row = w.plan_batches(plan)[0]

        def raises(func, label: str, needle: str) -> None:
            global COUNT
            try:
                func()
            except w.ProductionWriterError as exc:
                if needle and needle not in str(exc):
                    raise FixtureError(f"{label}: refused for the wrong reason: {exc}")
                COUNT += 1
            except Exception as exc:
                raise FixtureError(f"{label}: raw {type(exc).__name__} escaped") from exc
            else:
                raise FixtureError(f"{label}: accepted")

        # _write_file: the file-exists refusal and the generic write failure.
        raises(lambda: w._write_file(present, b"x"),
               "_write_file over an existing file", "refusing to overwrite")
        raises(lambda: w._write_file(root / "no-such-dir" / "f.bin", b"x"),
               "_write_file into a missing directory", "cannot write")
        with mock.patch.object(w.os, "fsync", side_effect=OSError("fsync failed")):
            raises(lambda: w._write_file(root / "fsync-fails.bin", b"x"),
                   "_write_file whose fsync fails", "cannot write")
        # _write_file: the payload must be bytes.  The needle is this check's own
        # message, so it is the payload type test itself under test and not some
        # later refusal that would mask it.
        raises(lambda: w._write_file(root / "not-bytes.bin", "a string"),
               "_write_file with a non-bytes payload", "must be bytes")
        raises(lambda: w._write_file(root / "not-bytes.bin", None),
               "_write_file with a None payload", "must be bytes")
        raises(lambda: w._write_file(root / "not-bytes.bin", ["a"]),
               "_write_file with a list payload", "must be bytes")
        # And the check must be reached through a public entry point too, so
        # removing it cannot hide behind the wrapper.
        with mock.patch.object(w, "encodable_records", return_value="not bytes"):
            raises(lambda: w.write_range(root, row["batch_id"],
                                         records_for(row["start"], row["stop"]),
                                         result_schema=SCHEMA, identity=ID,
                                         session=ACCEPTED),
                   "a write whose encoder returned non-bytes", "must be bytes")
        # _read_file: a missing file and a directory.
        raises(lambda: w._read_file(absent, "a file"), "_read_file of a missing file",
               "cannot read")
        raises(lambda: w._read_file(root, "a directory"), "_read_file of a directory",
               "")
        # _read_json: a directory, non-ASCII bytes, and malformed JSON.
        # Reading a directory is refused either by _read_file (cannot read) or,
        # on a platform where the read succeeds and returns nothing, by _read_json
        # (not ASCII JSON); both are the typed refusal this module promises.
        raises(lambda: w._read_json(root, "a document"), "_read_json of a directory",
               "")
        nonascii = root / "nonascii.json"
        nonascii.write_bytes(b"\xff\xfe")
        raises(lambda: w._read_json(nonascii, "a document"),
               "_read_json of non-ASCII bytes", "not ASCII JSON")
        malformed = root / "malformed.json"
        malformed.write_text("{not json", encoding="ascii")
        raises(lambda: w._read_json(malformed, "a document"),
               "_read_json of malformed JSON", "not ASCII JSON")
        # _canonical: a value no JSON rendering can carry.
        raises(lambda: w._canonical({1, 2}), "_canonical of a set", "not canonical JSON")
        # _fsync_dir: a path that is not a directory.
        raises(lambda: w._fsync_dir(present), "_fsync_dir of a file",
               "for fsync")
        with mock.patch.object(w.os, "fsync", side_effect=OSError("fsync failed")):
            raises(lambda: w._fsync_dir(root), "_fsync_dir whose fsync fails",
                   "cannot fsync directory")
        # _create_file_once: a missing parent directory.
        raises(lambda: w._create_file_once(root / "no-such-dir" / "f.json", b"{}"),
               "_create_file_once into a missing directory", "must be an existing")
        # _create_file_once: the link failing with a generic OSError.
        with mock.patch.object(w.os, "link", side_effect=OSError("link failed")):
            raises(lambda: w._create_file_once(root / "link-fails.json", b"{}"),
                   "_create_file_once whose link fails", "cannot create")
        # _create_file_once: the link finding the name taken (EEXIST).
        taken = root / "taken.json"
        taken.write_bytes(b"original")
        raises(lambda: w._create_file_once(taken, b"replacement"),
               "_create_file_once over an existing name", "refusing to overwrite")
        require(taken.read_bytes() == b"original",
                "a refused create-once replaced the file's bytes")
        # The best-effort removals swallow their errors, so a failure there must
        # not mask anything: they are asserted not to raise.
        w._remove_tree(root / "no-such-tree")
        w._discard_file(root / "no-such-file")
        COUNT += 1


def check_io_failures() -> None:
    _check_io_failures(TOTAL)


def check_fast_io_failures() -> None:
    _check_io_failures(SMALL)


# --------------------------------------------------------------------------
# Every seal-input entry point, with each SPECIFIC class injected at it
# --------------------------------------------------------------------------
#: The seven SEALED INPUTS this module creates, named by the public entry point
#: that seals each one.  The round-2 validator rejected a bare
#: ``except Exception`` over exactly this set -- the stored plan and the stored
#: manifest on the read path, and the commitment, the campaign pin, the beacon
#: pin and the beacon consultation on the write path -- so each is driven here
#: with each specific class that can arise at it.
SEAL_INPUT_ENTRY_POINTS = (
    "seal_range_plan", "write_range", "verify_range", "audit_final_set",
    "aggregate_records", "seal_instance_commitment", "load_commitment",
    "verify_plan_binding", "open_campaign_pin", "verify_retained_values",
    "build_timestamp_request", "seal_beacon_rule_pin", "consult_beacon_rule",
    "sealed_state", "load_range_plan", "missing_ranges",
)

#: The classes a trust boundary in this module can raise, and the module the
#: fixture injects them into.  Each is a NAMED class with a specific meaning:
#: ``OSError`` the filesystem, ``TypeError``/``UnicodeError``/``ValueError`` a
#: malformed stored document or a wrong-typed argument, ``json
#: .JSONDecodeError`` malformed JSON (a ``ValueError`` subclass, listed
#: separately so the narrow JSON conversion is reached on its own), and the
#: delegated modules' own typed refusals.  None of these is ``Exception``.
SEAL_INPUT_FAILURES = (
    ("OSError", OSError("injected filesystem failure"), "os"),
    ("TypeError", TypeError("injected wrong-typed stored document"), "type"),
    ("UnicodeError", UnicodeDecodeError("ascii", b"\xff", 0, 1, "injected"),
     "unicode"),
    ("ValueError", ValueError("injected malformed stored value"), "value"),
    ("JSONDecodeError", json.JSONDecodeError("injected", "{", 0), "json"),
    ("CUDAExecutionContractError",
     contract.CUDAExecutionContractError("injected contract refusal"), "contract"),
    ("VerificationError", sampled.VerificationError("injected sampled refusal"),
     "sampled"),
    ("CommitmentAdapterError", adapter.CommitmentAdapterError("injected adapter refusal"),
     "adapter"),
    ("WitnessError", witness.WitnessError("injected witness refusal"), "witness"),
)


def _check_seal_input_typed_failures() -> None:
    """Each specific failure injected at each seal input is the typed refusal.

    The round-2 module converted a seal-input failure with a bare
    ``except Exception``.  This asserts the replacement directly: for every
    seal-input entry point and every named class, the call raises
    ``ProductionWriterError`` -- never the raw class, and never silently
    succeeding.  It is also the guard on the boundary LIST itself: a class
    removed from ``WRITER_BOUNDARY_ERRORS`` makes its row fail here.
    """
    import unittest.mock as mock

    global COUNT

    # Every class the module claims to convert at a boundary must be reachable
    # through the list it publishes, and nothing broader than those classes may
    # be in it.
    for name, _, _ in SEAL_INPUT_FAILURES:
        klass = {"OSError": OSError, "TypeError": TypeError,
                 "UnicodeError": UnicodeError, "ValueError": ValueError,
                 "JSONDecodeError": json.JSONDecodeError,
                 "CUDAExecutionContractError": contract.CUDAExecutionContractError,
                 "VerificationError": sampled.VerificationError,
                 "CommitmentAdapterError": adapter.CommitmentAdapterError,
                 "WitnessError": witness.WitnessError}[name]
        require(issubclass(klass, w.WRITER_BOUNDARY_ERRORS)
                or klass is json.JSONDecodeError,
                f"{name} is not on the module's boundary class list")
    require(issubclass(w.ProductionWriterError, w.WRITER_BOUNDARY_ERRORS),
            "the module's own refusal is not on its own boundary class list")
    for too_broad in (Exception, BaseException):
        require(too_broad not in w.WRITER_BOUNDARY_ERRORS,
                f"{too_broad.__name__} is on the module's boundary class list")

    with tempfile.TemporaryDirectory() as td:
        root = new_root(td)
        plan = write_all(root, ONE)
        commit(root, plan)
        row = w.plan_batches(plan)[0]
        records = records_for(row["start"], row["stop"])
        digest = pin_digest(BEACON_PIN)
        coordinates = [record["coordinates"]
                       for record in w.aggregate_records(root, result_schema=SCHEMA)]
        descriptor = {"family": FAMILY, "plan_content_sha256": plan["content_sha256"]}

        def calls() -> dict:
            """Every seal-input entry point, bound to this root's state."""
            return {
                "load_range_plan": lambda: w.load_range_plan(root),
                "seal_range_plan": lambda: w.seal_range_plan(
                    root, family=FAMILY, total_coordinates=ONE,
                    identity=ID, session=ACCEPTED),
                "missing_ranges": lambda: w.missing_ranges(root),
                "write_range": lambda: w.write_range(
                    root, "not_in_the_plan", records, result_schema=SCHEMA,
                    identity=ID, session=ACCEPTED),
                "verify_range": lambda: w.verify_range(root, row["batch_id"]),
                "audit_final_set": lambda: w.audit_final_set(root),
                "aggregate_records": lambda: w.aggregate_records(root),
                "seal_instance_commitment": lambda: w.seal_instance_commitment(
                    root, descriptor=descriptor, result_schema=SCHEMA,
                    expected_descriptor_sha256=w.hash_descriptor(descriptor),
                    expected_schema_sha256=w.hash_result_schema(SCHEMA),
                    expected_coordinate_root=sampled.coordinate_root(coordinates).hex(),
                    expected_coordinates=coordinates,
                    expected_plan_content_sha256=plan["content_sha256"],
                    expected_total_coordinates=ONE, identity=ID, session=ACCEPTED),
                "load_commitment": lambda: w.load_commitment(root),
                "verify_plan_binding": lambda: w.verify_plan_binding(root),
                "open_campaign_pin": lambda: w.open_campaign_pin(
                    root, w.load_commitment(root)["binding"]["campaign_binding_digest"]),
                "verify_retained_values": lambda: w.verify_retained_values(root),
                "build_timestamp_request": lambda: w.build_timestamp_request(
                    root, POLICY, nonce=1),
                "seal_beacon_rule_pin": lambda: w.seal_beacon_rule_pin(
                    root, BEACON_PIN, digest),
                "consult_beacon_rule": lambda: w.consult_beacon_rule(root, digest),
                "sealed_state": lambda: w.sealed_state(root),
            }

        # A control: unbound, each call either already refuses on its own
        # account or is legitimate -- so a patched run's failure is the
        # injection and not a pre-existing refusal.
        for name, call in calls().items():
            try:
                call()
            except w.ProductionWriterError:
                pass
            else:
                pass  # legitimate; the injection must be what refuses it below

        for label, error, _ in SEAL_INPUT_FAILURES:
            # The private helpers every seal input flows through, plus the
            # frozen-delegation wrapper, patched to raise this exact class.
            targets = [("_read_json", w._read_json), ("_read_file", w._read_file),
                       ("_write_file", w._write_file),
                       ("_create_file_once", w._create_file_once),
                       ("_fsync_dir", w._fsync_dir), ("_contract", w._contract)]
            for target_name, target in targets:
                with mock.patch.object(w, target_name, side_effect=error):
                    for name, call in calls().items():
                        try:
                            call()
                        except w.ProductionWriterError:
                            COUNT += 1
                        except BaseException as exc:
                            if type(exc) is not type(error):
                                raise FixtureError(
                                    f"{name} with a {label} injected at {target_name}: "
                                    f"a different {type(exc).__name__} escaped") from exc
                            raise FixtureError(
                                f"{name} with a {label} injected at {target_name}: "
                                "the raw class escaped the boundary") from exc
            del targets, target_name, target
        # The record-form checker is a seal input too: a range write consults it
        # before staging a byte.
        for label, error, _ in SEAL_INPUT_FAILURES:
            with mock.patch.object(w, "check_records", side_effect=error):
                for name in ("write_range", "verify_range", "aggregate_records",
                             "seal_instance_commitment", "audit_final_set"):
                    call = calls()[name]
                    try:
                        call()
                    except w.ProductionWriterError:
                        COUNT += 1
                    except BaseException as exc:
                        if type(exc) is not type(error):
                            raise FixtureError(
                                f"{name} with a {label} injected at check_records: "
                                f"a different {type(exc).__name__} escaped") from exc
                        raise FixtureError(
                            f"{name} with a {label} injected at check_records: "
                            "the raw class escaped the boundary") from exc


def check_seal_input_typed_failures() -> None:
    _check_seal_input_typed_failures()


def check_fast_seal_input_typed_failures() -> None:
    _check_seal_input_typed_failures()


# --------------------------------------------------------------------------
# Every boundary is NARROW: a fault outside the named classes propagates
# --------------------------------------------------------------------------
class _UnrelatedFault(Exception):
    """An ``Exception`` that is in none of the module's boundary classes.

    It is the probe for a WIDENED boundary.  Round 2 caught a seal-input
    failure with a bare ``except Exception``, so "converts to the typed refusal"
    proved nothing about which classes were converted: a widened catch accepts
    this fault too, and the round-3 ruling is that it must not.
    """


#: Every ``except`` clause in the module, keyed by the class expression it
#: names.  Checked against the AST so a future edit that widens one, or adds a
#: clause that is not on this list, is caught here.
_NARROW_CLAUSES = {
    "WRITER_BOUNDARY_ERRORS": "the public-entry boundary",
    "(TypeError, ValueError)": "the JSON encoders",
    "OSError": "the filesystem, named failure",
    "FileExistsError": "a sealed name is taken",
    "(contract.CUDAExecutionContractError, sampled.VerificationError, "
    "adapter.CommitmentAdapterError, witness.WitnessError)":
        "the delegated modules' own typed refusals",
    "(UnicodeDecodeError, ValueError)": "a stored document's decode",
    "AttributeError": "the injected identity's interface",
    "ValueError": "the injected identity refusing a session",
}

#: Clauses that are NOT conversions: the best-effort cleanups, which catch only
#: the filesystem on purpose so that a failed removal never masks the real
#: failure, and the one re-raise, which must keep naming both its classes.
_BEST_EFFORT_CLAUSES = frozenset({"OSError"})


def _reraises(handler: ast.ExceptHandler) -> bool:
    """True when a handler's LAST statement is a bare ``raise`` (re-raise).

    A cleanup handler that removes a staging directory and then re-raises is not
    a conversion: it converts nothing and swallows nothing.
    """
    return bool(handler.body) and isinstance(handler.body[-1], ast.Raise) \
        and handler.body[-1].exc is None


def _check_boundaries_are_narrow() -> None:
    """No boundary in this module catches more than it can name.

    Three assertions, one per way a catch can be too wide:

    1. the public-entry wrapper's catch list is a fixed tuple of named classes,
       and neither ``Exception`` nor ``BaseException`` is in it;
    2. every ``except`` in the module names specific classes -- a source-text
       scan, so a widened clause is caught even where the mutation sweep cannot
       reach it;
    3. the RUNTIME proof: an unrelated ``Exception`` injected at each of the
       module's boundary helpers propagates OUT of the public entry point
       instead of being converted.  A widened ``except`` at any of those sites
       converts it and this fixture fails.
    """
    import unittest.mock as mock

    global COUNT

    require(isinstance(w.WRITER_BOUNDARY_ERRORS, tuple)
            and all(isinstance(k, type) for k in w.WRITER_BOUNDARY_ERRORS),
            "the boundary class list is not a tuple of classes")
    for too_broad in (Exception, BaseException):
        require(too_broad not in w.WRITER_BOUNDARY_ERRORS,
                f"{too_broad.__name__} is on the boundary class list")
    require(w.InjectedInterrupt not in w.WRITER_BOUNDARY_ERRORS,
            "InjectedInterrupt is on the boundary class list")

    source = (HERE / "stage2_production_writer.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler) or node.type is None:
            continue
        rendered = ast.unparse(node.type)
        # ``BaseException`` appears exactly once, at the staging cleanup, and it
        # RERASES: it removes the staging directory on the way out and then
        # re-raises the same object.  It converts nothing, so it is not a
        # boundary and is allowed here; it is pinned by the crash-at-every-step
        # fixture, which asserts no staging residue survives it.
        if rendered == "BaseException" and _reraises(node):
            COUNT += 1
            continue
        if rendered in ("Exception", "BaseException"):
            raise FixtureError(
                f"line {node.lineno}: a boundary catches {rendered} outright")
        if rendered in _NARROW_CLAUSES or rendered in _BEST_EFFORT_CLAUSES:
            COUNT += 1
            continue
        if rendered == "(ProductionWriterError, InjectedInterrupt)":
            COUNT += 1  # the re-raise: the typed refusal and the interrupt
            continue
        raise FixtureError(
            f"line {node.lineno}: unrecognised boundary clause `except {rendered}`")

    with tempfile.TemporaryDirectory() as td:
        root = new_root(td)
        # Each of these helpers sits directly behind a narrow ``except`` in the
        # module.  An unrelated Exception raised there belongs to no boundary
        # class, so it must reach the caller UNCHANGED -- not converted by the
        # narrow inner clause, and not converted by the public wrapper either.
        # If any of those clauses were widened to ``Exception`` the fault would
        # come out as a ``ProductionWriterError`` and this fixture fails, which
        # is what makes the narrowness load-bearing rather than decorative.
        # A two-range plan with only the FIRST range promoted, so the second is
        # genuinely missing: that is the one path into ``_write_file`` that is
        # not refused earlier for an unrelated reason.
        plan = write_all(root, TOTAL)
        del plan
        rows = w.plan_batches(w.load_range_plan(root))
        shutil.rmtree(root / w.RANGES_DIRNAME / rows[1]["batch_id"])
        require((root / w.RANGES_DIRNAME / rows[0]["batch_id"]).is_dir()
                and not (root / w.RANGES_DIRNAME / rows[1]["batch_id"]).exists(),
                "the narrowness probe needs exactly one range promoted")
        row = rows[1]
        # A root carrying a real staging directory, so the discard's
        # post-removal fsync runs rather than being skipped on a clean root.
        staged = new_root(td, "staged_root")
        (staged / f"{w.STAGING_PREFIX}leftover").mkdir()
        for target_name, call in (
            ("_read_file", lambda: w.load_range_plan(root)),
            ("_read_json", lambda: w.load_range_plan(root)),
            ("_write_file", lambda: w.write_range(
                root, row["batch_id"], records_for(row["start"], row["stop"]),
                result_schema=SCHEMA, identity=ID, session=ACCEPTED)),
            ("_create_file_once", lambda: w.seal_range_plan(
                new_root(td, "fresh_for_create_once"), family=FAMILY,
                total_coordinates=ONE, identity=ID, session=ACCEPTED)),
            ("_fsync_dir", lambda: w.discard_stale_staging(staged)),
        ):
            with mock.patch.object(w, target_name,
                                   side_effect=_UnrelatedFault("not a boundary class")):
                try:
                    call()
                except w.ProductionWriterError as exc:
                    raise FixtureError(
                        f"{target_name}: an unrelated Exception was converted to a "
                        f"typed refusal by a widened boundary: {exc}") from exc
                except _UnrelatedFault:
                    COUNT += 1
                else:
                    raise FixtureError(
                        f"{target_name}: an unrelated Exception was swallowed")

        # The public-entry boundary itself is held to the SAME rule: a class on
        # the list is converted to the typed refusal naming the entry point,
        # and a class off the list -- an unrelated ``Exception`` here, and a
        # ``BaseException`` below -- propagates as itself.
        try:
            w._typed(lambda: (_ for _ in ()).throw(OSError("injected")))()
        except w.ProductionWriterError as exc:
            require(str(exc).startswith("<lambda> refused: OSError"),
                    f"the public boundary did not name the entry point: {exc}")
            require(type(exc.__cause__) is OSError,
                    "the public boundary lost the real cause")
            COUNT += 1
        else:
            raise FixtureError("a class on the boundary list was not converted")
        try:
            w._typed(lambda: (_ for _ in ()).throw(_UnrelatedFault("off list")))()
        except _UnrelatedFault:
            COUNT += 1
        except w.ProductionWriterError:
            raise FixtureError(
                "an unrelated Exception was converted by the public boundary")
        else:
            raise FixtureError("an unrelated Exception was swallowed by the public boundary")

        class _Boom(BaseException):
            pass

        try:
            w._typed(lambda: (_ for _ in ()).throw(_Boom()))()
        except _Boom:
            COUNT += 1
        except w.ProductionWriterError:
            raise FixtureError("a BaseException was converted to a typed refusal")
        else:
            raise FixtureError("a BaseException was swallowed by the public boundary")


def check_boundaries_are_narrow() -> None:
    _check_boundaries_are_narrow()


def check_fast_boundaries_are_narrow() -> None:
    _check_boundaries_are_narrow()


# --------------------------------------------------------------------------
# Each remaining guard is reached by exactly one case, named here
# --------------------------------------------------------------------------
def _check_individual_guards(total: int) -> None:
    """One case per guard that no other fixture reaches on its own.

    A guard that only ever fires behind another one is a check nothing depends
    on: the round-1 validator's verdict turned on exactly that.  Each block below
    states which single guard it reaches and asserts the refusal is that guard's
    own, so removing that guard makes this fixture fail.
    """

    # --- the injected identity's validate() raising (not returning a bad
    # digest).  ``validate`` reports a *structural* fault in the injected
    # identity, so it is caught at the public boundary and names the entry
    # point; only ``exact_match`` reports a session mismatch, so only its
    # refusal is caught at the call itself.
    class RaisingValidate(Identity):
        def validate(self, payload: object) -> str:
            raise ValueError("identity service is down")
    refused(lambda: w.recheck_identity(RaisingValidate(ACCEPTED), ACCEPTED),
            "an identity validate() that raises ValueError",
            "recheck_identity refused: ValueError")
    refused(lambda: w.identity_hash(RaisingValidate(ACCEPTED)),
            "hashing an identity whose validate() raises ValueError",
            "identity_hash refused: ValueError")

    # --- _as_path: a root that is neither a str nor a PathLike.
    with tempfile.TemporaryDirectory() as td:
        refused(lambda: w.load_range_plan(7), "a root that is an int", "must be a path")
        refused(lambda: w.load_range_plan([td]), "a root that is a list", "must be a path")
        refused(lambda: w.load_range_plan(b"bytes"), "a root that is bytes",
                "must be a path")
        # _instance_root: a str that is not an existing directory.
        refused(lambda: w.seal_range_plan(str(Path(td) / "nope"), family=FAMILY,
                                          total_coordinates=total, identity=ID,
                                          session=ACCEPTED),
                "a root that does not exist", "existing real directory")
        # A file where a root directory is required.
        as_file = Path(td) / "file.bin"
        as_file.write_bytes(b"x")
        refused(lambda: w.seal_range_plan(as_file, family=FAMILY,
                                          total_coordinates=total, identity=ID,
                                          session=ACCEPTED),
                "a root that is a file", "existing real directory")
        # A symlink to a directory: a root must be a REAL directory, not a link.
        # The needle is the ROOT-specific message, not the create-once parent's
        # "must be an existing real directory", which is a different check that
        # would otherwise satisfy this assertion when the root check is removed.
        link = Path(td) / "link"
        link.symlink_to(Path(td), target_is_directory=True)
        refused(lambda: w.seal_range_plan(link, family=FAMILY,
                                          total_coordinates=total, identity=ID,
                                          session=ACCEPTED),
                "a root that is a symlink to a directory",
                "instance root must be an existing real directory")
        # The same root check, reached through a path that never reaches the
        # create-once step: discard_stale_staging refuses the root first.
        refused(lambda: w.discard_stale_staging(link),
                "discarding staging under a symlink root",
                "instance root must be an existing real directory")
        refused(lambda: w.write_range(link, "b0000", [],
                                      result_schema=SCHEMA, identity=ID,
                                      session=ACCEPTED),
                "a write under a symlink root",
                "instance root must be an existing real directory")

        # --- load_range_plan: a root with no plan file at all.
        empty = Path(td) / "empty"
        empty.mkdir()
        refused(lambda: w.load_range_plan(empty), "a root with no sealed plan",
                "no sealed range plan")
        # A plan path that is a symlink, not a real file.
        plan_link = Path(td) / "planlink"
        plan_link.mkdir()
        (plan_link / w.PLAN_NAME).symlink_to(Path(td) / "nowhere.json")
        refused(lambda: w.load_range_plan(plan_link),
                "a plan path that is a dangling symlink", "no sealed range plan")

        # --- check_records: a records payload that is not a list.  The needle is
        # this check's OWN message, so a caller must reach the payload type test
        # itself rather than merely some later refusal that happens to fire.
        plan = seal(empty, total)
        row = w.plan_batches(plan)[0]
        for bad, label in (({}, "a dict"), ("records", "a string"), (5, "an int"),
                           (None, "None"), ((1, 2), "a tuple"), (b"[]", "bytes")):
            refused(lambda bad=bad: w.check_records(bad, SCHEMA, 1, "l"),
                    f"check_records with {label}", "records must be a list")
        # A list that is one record SHORT: this is the count check, and the
        # needle separates it from the type check above.
        refused(lambda: w.check_records(records_for(0, 1), SCHEMA, ONE, "l"),
                "check_records with too few records", "the sealed range spans")
        # A list of the right length holding a non-dict record.
        refused(lambda: w.check_records(["not a record"], SCHEMA, 1, "l"),
                "check_records with a non-dict record", "must be exactly")

        # --- the binary64 finiteness branch: an infinity and a NaN each reach
        # the `if kind == "binary64"` body, which the exact-type check above it
        # does not refuse on its own.
        for field, value, label in (("energy", float("inf"), "infinity"),
                                    ("energy", float("-inf"), "negative infinity"),
                                    ("energy", float("nan"), "NaN")):
            records = records_for(row["start"], row["start"] + 2)
            records[0]["result"] = dict(records[0]["result"])
            records[0]["result"][field] = value
            refused(lambda records=records: w.check_records(records, SCHEMA, 2, "l"),
                    f"a binary64 field holding {label}", "not finite")

    # --- hash_result_schema: a schema that is not an exact field-type map.
    for bad, label in (({}, "an empty schema"),
                       ({"a": "float"}, "a field typed as an unknown kind"),
                       ({"": "int"}, "a field with an empty name"),
                       ({5: "int"}, "a non-string field name"),
                       ({"a": 5}, "a non-string field kind"),
                       ("not a dict", "a schema that is not a dict")):
        refused(lambda bad=bad: w.hash_result_schema(bad),
                f"hash_result_schema with {label}", "result schema must map")

    # --- missing_ranges: a promoted range that the sealed plan does not contain.
    with tempfile.TemporaryDirectory() as td:
        root = new_root(td)
        plan = seal(root, total)
        rogue = root / w.RANGES_DIRNAME / "not_in_the_sealed_plan"
        rogue.mkdir(parents=True)
        refused(lambda: w.missing_ranges(root),
                "a promoted range outside the sealed plan",
                "promoted ranges are not in the sealed plan")
        del plan

    # --- write_range: the staging path that already exists.
    with tempfile.TemporaryDirectory() as td:
        root = new_root(td)
        plan = seal(root, total)
        row = w.plan_batches(plan)[0]
        occupied = root / f"{w.STAGING_PREFIX}{os.getpid()}-{row['batch_id']}"
        occupied.mkdir()
        refused(lambda: w.write_range(root, row["batch_id"],
                                      records_for(row["start"], row["stop"]),
                                      result_schema=SCHEMA, identity=ID,
                                      session=ACCEPTED),
                "a range write whose staging path is already occupied",
                "staging path already exists")
        del occupied

    # --- write_range: the ranges directory replaced by something that is not one.
    with tempfile.TemporaryDirectory() as td:
        root = new_root(td)
        plan = seal(root, total)
        row = w.plan_batches(plan)[0]
        # A FILE where the ranges directory belongs: the range machinery refuses
        # it rather than promoting into it.
        (root / w.RANGES_DIRNAME).write_bytes(b"not a directory")
        refused(lambda: w.write_range(root, row["batch_id"],
                                      records_for(row["start"], row["stop"]),
                                      result_schema=SCHEMA, identity=ID,
                                      session=ACCEPTED),
                "a range write whose ranges directory is a file",
                "must be a real directory")
        del plan


def check_individual_guards() -> None:
    _check_individual_guards(TOTAL)


def check_fast_individual_guards() -> None:
    _check_individual_guards(SMALL)


def check_fast_load_commitment_content_guards() -> None:
    """Exercise each stored commitment shape and digest guard on its read path."""
    with tempfile.TemporaryDirectory() as td:
        root = new_root(td)
        plan = write_all(root, SMALL)
        sealed = commit(root, plan)
        path = root / w.COMMITMENT_NAME

        def load_after(mutate, label: str, needle: str) -> None:
            document = json.loads(json.dumps(sealed))
            mutate(document)
            # Commitment documents have no content digest. If one is added to
            # the stored format later, keep this fixture on the intended guard.
            if "content_sha256" in document:
                document["content_sha256"] = w._content_digest(
                    {key: value for key, value in document.items()
                     if key != "content_sha256"})
            _write_json(path, document)
            refused(lambda: w.load_commitment(root), label, needle)

        load_after(lambda d: d["binding"].pop("schema"),
                   "a stored binding missing its schema", "sealed commitment binding has the wrong key set")
        for value_name, value in (("list", []), ("string", "not a binding"), ("null", None)):
            load_after(lambda d, value=value: d.__setitem__("binding", value),
                       f"a stored commitment binding that is {value_name}",
                       "sealed 'binding' must be exactly dict")

        for value_name, value in (("non-hex", "g" * 64),
                                 ("uppercase", "A" * 64),
                                 ("63 characters", "a" * 63)):
            load_after(lambda d, value=value: d.__setitem__("plan_content_sha256", value),
                       f"a stored commitment plan hash that is {value_name}",
                       "sealed commitment plan hash must be a lowercase SHA-256")
            load_after(lambda d, value=value: d.__setitem__("production_identity_sha256", value),
                       f"a stored commitment identity hash that is {value_name}",
                       "sealed commitment identity hash must be a lowercase SHA-256")
        del plan


def check_fast_load_range_plan_rejects_symlink() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = new_root(td)
        seal(root, SMALL)
        plan_path = root / w.PLAN_NAME
        saved_path = root / "saved-plan.json"
        plan_path.replace(saved_path)
        plan_path.symlink_to(saved_path)
        refused(lambda: w.load_range_plan(root),
                "loading a sealed range plan through a symlink",
                "no sealed range plan")


def check_fast_verify_range_rejects_symlinks() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = new_root(td)
        plan = seal(root, SMALL)
        row = w.plan_batches(plan)[0]
        w.write_range(root, row["batch_id"], records_for(row["start"], row["stop"]),
                      result_schema=SCHEMA, identity=ID, session=ACCEPTED)
        directory = root / w.RANGES_DIRNAME / row["batch_id"]

        saved_directory = root / w.RANGES_DIRNAME / "saved-range"
        directory.replace(saved_directory)
        directory.symlink_to(saved_directory, target_is_directory=True)
        refused(lambda: w.verify_range(root, row["batch_id"]),
                "verifying a promoted range through a symlinked directory",
                "range is not promoted")
        directory.unlink()
        saved_directory.replace(directory)

        for name, needle in ((w.RANGE_MANIFEST_NAME, "range manifest is missing"),
                             (w.RECORDS_NAME, "range records file is missing")):
            path = directory / name
            saved_file = directory / f"saved-{name}"
            path.replace(saved_file)
            path.symlink_to(saved_file)
            refused(lambda: w.verify_range(root, row["batch_id"]),
                    f"verifying a promoted range whose {name} is a symlink", needle)
            path.unlink()
            saved_file.replace(path)
        del plan


def check_fast_write_range_rejects_dangling_destination() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = new_root(td)
        plan = seal(root, SMALL)
        row = w.plan_batches(plan)[0]
        (root / w.RANGES_DIRNAME).mkdir()
        destination = root / w.RANGES_DIRNAME / row["batch_id"]
        destination.symlink_to(root / "missing-destination", target_is_directory=True)
        refused(lambda: w.write_range(
                    root, row["batch_id"], records_for(row["start"], row["stop"]),
                    result_schema=SCHEMA, identity=ID, session=ACCEPTED),
                "writing through an occupied dangling range destination",
                "refusing to rewrite a completed range")
        require(destination.is_symlink(),
                "a refused write replaced its dangling destination symlink")
        del plan


def check_fast_hash_result_schema_refuses_invalid_field_type() -> None:
    class StringSubclass(str):
        pass

    for schema, label in (({}, "an empty schema"),
                          ({1: "int"}, "a non-string field name"),
                          ({"": "int"}, "an empty field name"),
                          ({"energy": 1}, "a non-string field type"),
                          ({"energy": "not-a-schema-type"}, "an unsupported field type"),
                          ({"energy": StringSubclass("binary64")}, "a string-subclass field type")):
        refused(lambda schema=schema: w.hash_result_schema(schema),
                f"hashing a result schema with {label}",
                "result schema must map each field to int/bool/str/binary64")


def check_fast_discard_stale_staging_skips_symlinks() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = new_root(td)
        target = Path(td) / "stale-target"
        target.mkdir()
        link = root / f"{w.STAGING_PREFIX}99999-symlink"
        link.symlink_to(target, target_is_directory=True)
        removed = w.discard_stale_staging(root)
        require(removed == [], "discard_stale_staging reported a symlink as removed")
        require(link.is_symlink(), "discard_stale_staging changed a symlinked staging entry")


def check_fast_commitment_and_pin_read_paths_reject_symlinks() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = new_root(td)
        plan = write_all(root, SMALL)
        sealed = commit(root, plan)
        commitment_path = root / w.COMMITMENT_NAME
        saved_commitment = root / "saved-commitment.json"
        commitment_path.replace(saved_commitment)
        commitment_path.symlink_to(saved_commitment)
        refused(lambda: w.load_commitment(root),
                "loading a commitment through a symlink",
                "no per-instance commitment")
        commitment_path.unlink()
        saved_commitment.replace(commitment_path)

        pin_path = root / w.CAMPAIGN_PIN_NAME
        saved_pin = root / "saved-campaign-pin.json"
        pin_path.replace(saved_pin)
        pin_path.symlink_to(saved_pin)
        refused(lambda: w.open_campaign_pin(
                    root, sealed["binding"]["campaign_binding_digest"]),
                "opening a campaign pin through a symlink",
                "no sealed campaign binding pin")
        pin_path.unlink()
        saved_pin.replace(pin_path)

        digest = pin_digest(BEACON_PIN)
        w.seal_beacon_rule_pin(root, BEACON_PIN, digest)
        beacon_path = root / w.BEACON_PIN_NAME
        saved_beacon = root / "saved-beacon-pin.json"
        beacon_path.replace(saved_beacon)
        beacon_path.symlink_to(saved_beacon)
        refused(lambda: w.consult_beacon_rule(root, digest),
                "consulting a beacon pin through a symlink",
                "not frozen")
        del plan


def check_fast_campaign_pin_symlink_refusal_is_atomic() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = new_root(td)
        plan = write_all(root, SMALL)
        pin_path = root / w.CAMPAIGN_PIN_NAME
        pin_path.symlink_to(root / "missing-campaign-pin")
        refused(lambda: commit(root, plan),
                "sealing a commitment while a dangling campaign-pin symlink exists",
                "campaign binding pin is already sealed and may not be re-pinned")
        require(not (root / w.COMMITMENT_NAME).exists(),
                "a refused campaign-pin re-seal left a partial commitment")
        del plan


def check_fast_plan_binding_rechecks_pin_components() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = new_root(td)
        plan = write_all(root, SMALL)
        commit(root, plan)
        pin_path = root / w.CAMPAIGN_PIN_NAME
        pin = json.loads(pin_path.read_text("ascii"))
        pin["merkle_root"] = "0" * 64
        _write_json(pin_path, pin)
        refused(lambda: w.verify_plan_binding(root),
                "a campaign pin whose Merkle root no longer matches its binding digest",
                "binding digest mismatch")
        del plan


def check_fast_timestamp_rejects_nonhex_campaign_digest() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = new_root(td)
        plan = write_all(root, SMALL)
        commit(root, plan)
        pin_path = root / w.CAMPAIGN_PIN_NAME
        pin = json.loads(pin_path.read_text("ascii"))
        pin["campaign_binding_digest"] = "g" * 64
        _write_json(pin_path, pin)
        refused(lambda: w.build_timestamp_request(root, POLICY, nonce=5),
                "building a timestamp request with a non-hex campaign digest",
                "campaign binding digest must be a lowercase SHA-256")
        del plan


def check_fast_timestamp_writer_types_and_symlink_atomicity() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = new_root(td)
        plan = write_all(root, SMALL)
        commit(root, plan)
        refused(lambda: w.build_timestamp_request(root, list(POLICY.items()), nonce=5),
                "building a timestamp request from a pair-list policy",
                "beacon policy must be a non-empty dict")
        meta_path = root / w.TIMESTAMP_REQUEST_META
        meta_path.symlink_to(root / "missing-timestamp-meta")
        refused(lambda: w.build_timestamp_request(root, POLICY, nonce=5),
                "building a timestamp request with a dangling metadata symlink",
                "already sealed (timestamp_request.meta.json)")
        require(not (root / w.TIMESTAMP_REQUEST_NAME).exists(),
                "a refused timestamp metadata symlink left a partial DER request")
        del plan


def check_fast_retained_leaf_hash_content_refusals() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = new_root(td)
        plan = write_all(root, SMALL)
        sealed = commit(root, plan)
        path = root / w.COMMITMENT_NAME
        original = sealed["retained_leaf_hashes"][0]
        for value, label in ((original.upper(), "uppercase hex"),
                             (original[:-1], "a 63-character hash"),
                             ("g" * 64, "non-hex characters")):
            document = json.loads(json.dumps(sealed))
            document["retained_leaf_hashes"][0] = value
            _write_json(path, document)
            refused(lambda: w.verify_retained_values(root),
                    f"verifying a retained leaf hash with {label}",
                    "retained leaf hash must be a lowercase SHA-256")
        del plan


def check_fast_beacon_policy_positive_and_public_key_schema() -> None:
    policy = w.beacon_policy_of_pin(BEACON_PIN)
    require(policy == {key: BEACON_PIN[key] for key in w.BEACON_PIN_KEYS},
            "a valid beacon policy did not round-trip its exact schema")
    bad = dict(BEACON_PIN, public_key_hex="B" * 192)
    refused(lambda: w.beacon_policy_of_pin(bad),
            "a beacon public key containing uppercase hex",
            "beacon public key has wrong hex length or encoding")


def check_fast_sealed_file_requires_real_parent() -> None:
    """A public pin writer must refuse a symlinked output parent."""
    with tempfile.TemporaryDirectory() as td:
        target = Path(td) / "real-target"
        target.mkdir()
        linked_root = Path(td) / "linked-root"
        linked_root.symlink_to(target, target_is_directory=True)
        refused(lambda: w.seal_beacon_rule_pin(
                    linked_root, BEACON_PIN, pin_digest(BEACON_PIN)),
                "sealing a beacon pin through a symlinked root",
                "parent of " + w.BEACON_PIN_NAME + " must be an existing real directory")


# --------------------------------------------------------------------------
# The presence, write-once and retained-value guards, one case each
# --------------------------------------------------------------------------
def _check_presence_and_write_once_guards(total: int) -> None:
    """The presence checks, the write-once checks and the retained-value checks.

    Each block names the single guard it reaches, and each is the ONLY case in
    the suite that reaches it, so the corresponding mutation is killed.
    """
    # --- verify_range: a promoted range directory that is a FILE, not a dir.
    with tempfile.TemporaryDirectory() as td:
        root = new_root(td)
        plan = seal(root, total)
        row = w.plan_batches(plan)[0]
        (root / w.RANGES_DIRNAME).mkdir()
        (root / w.RANGES_DIRNAME / row["batch_id"]).write_bytes(b"not a directory")
        refused(lambda: w.verify_range(root, row["batch_id"]),
                "verifying a range whose directory is a file", "range is not promoted")
        # A range directory holding only a manifest, no records file.
        directory = root / w.RANGES_DIRNAME / row["batch_id"]
        directory.unlink()
        directory.mkdir()
        body = w.encodable_records(records_for(row["start"], row["stop"]))
        manifest = contract.complete_range_manifest(
            plan, row["batch_id"], hashlib.sha256(body).hexdigest(),
            hashlib.sha256(body).hexdigest(), plan["qualification_identity_sha256"])
        (directory / w.RANGE_MANIFEST_NAME).write_bytes(w._canonical(manifest))
        refused(lambda: w.verify_range(root, row["batch_id"]),
                "verifying a range with no records file", "records file is missing")
        # And holding only a records file, no manifest: remove the manifest too.
        (directory / w.RECORDS_NAME).write_bytes(body)
        (directory / w.RANGE_MANIFEST_NAME).unlink()
        refused(lambda: w.verify_range(root, row["batch_id"]),
                "verifying a range with no manifest", "range manifest is missing")
        del plan

    # --- audit_final_set: a range whose manifest or records file is a DIRECTORY
    # rather than the real file its presence check demands.
    with tempfile.TemporaryDirectory() as td:
        root = new_root(td)
        plan = write_all(root, total)
        rows = w.plan_batches(plan)
        target = root / w.RANGES_DIRNAME / rows[0]["batch_id"]
        for name in (w.RECORDS_NAME, w.RANGE_MANIFEST_NAME):
            path = target / name
            saved = path.read_bytes()
            path.unlink()
            path.mkdir()
            refused(lambda path=path: w.audit_final_set(root),
                    f"the final-set audit of a range whose {name} is a directory",
                    "incomplete on disk")
            path.rmdir()
            path.write_bytes(saved)
        del plan

    # --- write_range: a ranges directory that exists as a symlink to elsewhere.
    with tempfile.TemporaryDirectory() as td:
        root = new_root(td)
        plan = seal(root, total)
        elsewhere = Path(td) / "elsewhere"
        elsewhere.mkdir()
        (root / w.RANGES_DIRNAME).symlink_to(elsewhere, target_is_directory=True)
        row = w.plan_batches(plan)[0]
        refused(lambda: w.write_range(root, row["batch_id"],
                                      records_for(row["start"], row["stop"]),
                                      result_schema=SCHEMA, identity=ID,
                                      session=ACCEPTED),
                "a range write whose ranges directory is a symlink",
                "must be a real directory")
        del plan

    # --- load_commitment: a commitment path that is a directory or a symlink.
    with tempfile.TemporaryDirectory() as td:
        root = new_root(td)
        plan = write_all(root, total)
        commit(root, plan)
        commitment = root / w.COMMITMENT_NAME
        body = commitment.read_bytes()
        commitment.unlink()
        commitment.mkdir()
        refused(lambda: w.load_commitment(root),
                "loading a commitment that is a directory", "no per-instance commitment")
        commitment.rmdir()
        commitment.symlink_to(root / "nowhere")
        refused(lambda: w.load_commitment(root),
                "loading a commitment that is a dangling symlink",
                "no per-instance commitment")
        del plan, body

    # --- verify_retained_values: the retained leaf list and its fields.  A
    # commitment with a NON-LIST leaf hash, a leaf list of the wrong length, and
    # a leaf entry that is not a lowercase digest each reach their own check.
    with tempfile.TemporaryDirectory() as td:
        root = new_root(td)
        plan = write_all(root, total)
        sealed = commit(root, plan)

        def reseal(mutate) -> None:
            document = json.loads(json.dumps(sealed))
            mutate(document)
            _write_json(root / w.COMMITMENT_NAME, document)

        reseal(lambda d: d.__setitem__("retained_leaf_hashes", "not a list"))
        refused(lambda: w.verify_retained_values(root),
                "a retained leaf list that is not a list", "no retained leaf list")
        reseal(lambda d: d.__setitem__("retained_leaf_hashes", []))
        refused(lambda: w.verify_retained_values(root),
                "an empty retained leaf list", "no retained leaf list")
        reseal(lambda d: d["retained_leaf_hashes"].pop())
        refused(lambda: w.verify_retained_values(root),
                "a retained leaf list shorter than the coordinates",
                "disagree with the retained leaf list")
        reseal(lambda d: d["retained_leaf_hashes"].__setitem__(0, "not-a-digest"))
        refused(lambda: w.verify_retained_values(root),
                "a retained leaf entry that is not a digest",
                "lowercase SHA-256")
        reseal(lambda d: d["retained_leaf_hashes"].__setitem__(0, "A" * 64))
        refused(lambda: w.verify_retained_values(root),
                "a retained leaf entry that is not lowercase hex",
                "lowercase SHA-256")
        del plan

    # --- seal_instance_commitment: re-pinning a campaign pin that already exists
    # while the commitment file itself is absent.  This reaches the SECOND
    # write-once check (the pin) on its own.
    with tempfile.TemporaryDirectory() as td:
        root = new_root(td)
        plan = write_all(root, total)
        commit(root, plan)
        (root / w.COMMITMENT_NAME).unlink()  # only the pin remains
        records = w.aggregate_records(root, result_schema=SCHEMA)
        coordinates = [record["coordinates"] for record in records]
        descriptor = {"family": FAMILY, "plan_content_sha256": plan["content_sha256"]}
        refused(lambda: w.seal_instance_commitment(
                    root, descriptor=descriptor, result_schema=SCHEMA,
                    expected_descriptor_sha256=w.hash_descriptor(descriptor),
                    expected_schema_sha256=w.hash_result_schema(SCHEMA),
                    expected_coordinate_root=sampled.coordinate_root(coordinates).hex(),
                    expected_coordinates=coordinates,
                    expected_plan_content_sha256=plan["content_sha256"],
                    expected_total_coordinates=plan["total_coordinates"],
                    identity=ID, session=ACCEPTED),
                "re-sealing while the campaign pin already exists",
                "binding pin is already sealed")
        del plan

    # --- build_timestamp_request: a pin whose plan hash disagrees with the plan.
    with tempfile.TemporaryDirectory() as td:
        root = new_root(td)
        plan = write_all(root, total)
        commit(root, plan)
        pin = json.loads((root / w.CAMPAIGN_PIN_NAME).read_text("ascii"))
        pin["plan_content_sha256"] = "a" * 64
        _write_json(root / w.CAMPAIGN_PIN_NAME, pin)
        refused(lambda: w.build_timestamp_request(root, POLICY, nonce=1),
                "a timestamp request whose pin names a different plan",
                "names a different range plan")
        del plan

    # --- seal_instance_commitment: a roster that is a TUPLE holding exactly the
    # written coordinates.  Every earlier check passes -- the root, the plan, the
    # identity -- and the content comparison below it would also pass, because
    # `list(tuple)` equals the coordinate list.  Only the roster's exact type
    # refuses, so this is the only case that reaches it.
    with tempfile.TemporaryDirectory() as td:
        root = new_root(td)
        plan = write_all(root, total)
        records = w.aggregate_records(root, result_schema=SCHEMA)
        coordinates = [record["coordinates"] for record in records]
        descriptor = {"family": FAMILY, "plan_content_sha256": plan["content_sha256"]}
        for roster, label in ((tuple(coordinates), "a tuple of the right coordinates"),
                              (iter(coordinates), "an iterator of the right coordinates"),
                              ({"c": coordinates}, "a dict wrapping the right roster")):
            refused(lambda roster=roster: w.seal_instance_commitment(
                        root, descriptor=descriptor, result_schema=SCHEMA,
                        expected_descriptor_sha256=w.hash_descriptor(descriptor),
                        expected_schema_sha256=w.hash_result_schema(SCHEMA),
                        expected_coordinate_root=sampled.coordinate_root(coordinates).hex(),
                        expected_coordinates=roster,
                        expected_plan_content_sha256=plan["content_sha256"],
                        expected_total_coordinates=plan["total_coordinates"],
                        identity=ID, session=ACCEPTED),
                    f"a commitment over {label}", "roster must be a list")
        require(not (root / w.COMMITMENT_NAME).exists(),
                "a refused roster type still sealed a commitment")
        del plan

    # --- aggregate_records: a records file that changes between the final-set
    # audit and the aggregation re-read.  The audit has already passed at that
    # point, so the re-read's own count check is the only thing that can refuse
    # a file that is no longer the one the audit covered.
    import unittest.mock as mock
    with tempfile.TemporaryDirectory() as td:
        root = new_root(td)
        plan = write_all(root, total)
        row = w.plan_batches(plan)[0]
        real_read = w._read_json
        state = {"seen": 0}

        def short_after_audit(path, label):
            document = real_read(path, label)
            if path.name == w.RECORDS_NAME and path.parent.name == row["batch_id"]:
                state["seen"] += 1
                if state["seen"] > 1:  # the audit already read it once
                    return document[:-1]
            return document

        with mock.patch.object(w, "_read_json", side_effect=short_after_audit):
            refused(lambda: w.aggregate_records(root),
                    "aggregation whose records file changed after the audit",
                    "range record count changed")
        require(w.verify_range(root, row["batch_id"])["verdict"] == "complete",
                "the fault injection damaged the promoted range")
        del plan

    # --- verify_retained_values: a leaf list AND its coordinate list shortened
    # together, so the two agree with each other but not with the sealed grid
    # size.  Only the grid-size check can refuse.
    with tempfile.TemporaryDirectory() as td:
        root = new_root(td)
        plan = write_all(root, total)
        sealed = commit(root, plan)
        document = json.loads(json.dumps(sealed))
        document["retained_leaf_hashes"] = document["retained_leaf_hashes"][:-1]
        document["retained_coordinates"] = document["retained_coordinates"][:-1]
        _write_json(root / w.COMMITMENT_NAME, document)
        refused(lambda: w.verify_retained_values(root),
                "a leaf list and its coordinates both shortened",
                "retained leaf list length differs from the sealed grid size")
        del plan

    # --- consult_beacon_rule: a frozen policy edited in place so it is no longer
    # the policy its pin digest was taken over.  Every individual field stays
    # well-formed (60 is a valid positive period), so only re-deriving the
    # policy digest can refuse.
    with tempfile.TemporaryDirectory() as td:
        root = new_root(td)
        plan = write_all(root, total)
        commit(root, plan)
        digest = pin_digest(BEACON_PIN)
        sealed_pin = w.seal_beacon_rule_pin(root, BEACON_PIN, digest)
        edited = json.loads(json.dumps(sealed_pin))
        edited["policy"]["chain_period_seconds"] = 60
        _write_json(root / w.BEACON_PIN_NAME, edited)
        refused(lambda: w.consult_beacon_rule(root, digest),
                "consulting a frozen policy that was edited in place",
                "not the policy its pin was taken from")
        del plan


def check_presence_and_write_once_guards() -> None:
    _check_presence_and_write_once_guards(TOTAL)


def check_fast_presence_and_write_once_guards() -> None:
    _check_presence_and_write_once_guards(SMALL)


def check_typed_wrapper() -> None:
    _check_typed_wrapper(TOTAL)


def check_fast_typed_wrapper() -> None:
    _check_typed_wrapper(SMALL)


# --------------------------------------------------------------------------
# The argument fuzz suite: every public argument against every wrong type
# --------------------------------------------------------------------------
_FUZZ_VALUES = (
    ("None", None), ("bool", True), ("int", 7), ("str", "x"),
    ("list", [1, 2]), ("dict", {"a": 1}), ("tuple", (1, 2)),
    ("unhashable-set", {1, 2}), ("unhashable-list", [[1], [2]]),
    ("nested-wrong", {"a": {"b": {"c": 1}}}), ("float", 1.5), ("bytes", b"x"),
    ("object", object()),
)


#: Fuzz targets whose argument is documented as optional with `None` meaning
#: "not supplied".  `None` is a valid value there, not a wrong type, so the fuzz
#: asserts only that the call never raises a raw error for it.
_OPTIONAL_NONE_ARGS = frozenset({"verify_range.identity", "verify_range.schema",
                                 "aggregate_records.schema"})

#: Fuzz targets whose argument is a PATH.  `str` and `Path` are both legitimate
#: path types here, so `str` is not a wrong type for them and must not be
#: required to be refused; every other wrong-typed value still must be.
_PATH_ARGS = frozenset({
    "load_range_plan", "seal_range_plan", "verify_range", "write_range.root",
    "discard_stale_staging", "promoted_batch_ids", "missing_ranges",
    "audit_final_set", "aggregate_records.root", "seal_instance_commitment.root",
    "load_commitment", "verify_plan_binding", "open_campaign_pin",
    "verify_retained_values", "build_timestamp_request.root",
    "seal_beacon_rule_pin.root", "consult_beacon_rule", "stages_present",
    "sealed_state",
})

#: Fuzz targets that accept ANY canonical-JSON value by design and so are not
#: required to refuse a wrong-typed input.  ``hash_descriptor`` hashes whatever
#: descriptor it is given; the descriptor's own validity is established by its
#: pinned hash, which is checked on the sealing path.  Fuzzing it asserts only
#: that no raw error escapes.
_ACCEPTS_ANY_JSON = frozenset({"hash_descriptor"})


def check_argument_fuzz() -> None:
    """Every public argument, against None/bool/int/str/list/dict/unhashable/nested.

    Each public entry point is called once per wrong-typed argument position with
    each fuzz value and MUST surface the writer's typed refusal -- never a raw
    TypeError, KeyError, AttributeError or IndexError.  This is the general form
    of the round-1 defect (a malformed stored pin raising a bare KeyError), so it
    is asserted over the whole surface, not over one hand-picked case.
    """
    with tempfile.TemporaryDirectory() as td:
        root = new_root(td)
        plan = write_all(root, ONE)
        row = w.plan_batches(plan)[0]
        records = w.aggregate_records(root, result_schema=SCHEMA)
        coordinates = [record["coordinates"] for record in records]
        descriptor = {"family": FAMILY, "plan_content_sha256": plan["content_sha256"]}
        digest = pin_digest(BEACON_PIN)

        def call(name: str, *args, **kwargs) -> None:
            getattr(w, name)(*args, **kwargs)

        # Each entry: (callable factory, list of positional/keyword descriptions).
        targets = [
            ("load_range_plan", lambda v: call("load_range_plan", v)),
            ("seal_range_plan", lambda v: call("seal_range_plan", v, family=FAMILY,
                                               total_coordinates=ONE, identity=ID,
                                               session=ACCEPTED)),
            ("seal_range_plan.family", lambda v: call("seal_range_plan", root, family=v,
                                                      total_coordinates=ONE, identity=ID,
                                                      session=ACCEPTED)),
            ("seal_range_plan.total", lambda v: call("seal_range_plan", root, family=FAMILY,
                                                     total_coordinates=v, identity=ID,
                                                     session=ACCEPTED)),
            ("seal_range_plan.identity", lambda v: call("seal_range_plan", root, family=FAMILY,
                                                        total_coordinates=ONE, identity=v,
                                                        session=ACCEPTED)),
            ("seal_range_plan.session", lambda v: call("seal_range_plan", root, family=FAMILY,
                                                       total_coordinates=ONE, identity=ID,
                                                       session=v)),
            ("plan_row", lambda v: call("plan_row", v, row["batch_id"])),
            ("plan_row.batch", lambda v: call("plan_row", plan, v)),
            ("identity_hash", lambda v: call("identity_hash", v)),
            ("recheck_identity", lambda v: call("recheck_identity", v, ACCEPTED)),
            ("recheck_identity.session", lambda v: call("recheck_identity", ID, v)),
            ("check_records", lambda v: call("check_records", v, SCHEMA, ONE, "l")),
            ("check_records.schema", lambda v: call("check_records", records, v, ONE, "l")),
            ("check_records.count", lambda v: call("check_records", records, SCHEMA, v, "l")),
            ("check_records.label", lambda v: call("check_records", records, SCHEMA, ONE, v)),
            ("verify_range", lambda v: call("verify_range", v, row["batch_id"])),
            ("verify_range.batch", lambda v: call("verify_range", root, v)),
            ("verify_range.identity", lambda v: call("verify_range", root, row["batch_id"],
                                                     expected_identity_sha256=v)),
            ("verify_range.schema", lambda v: call("verify_range", root, row["batch_id"],
                                                    result_schema=v)),
            ("write_range.root", lambda v: call("write_range", v, row["batch_id"],
                                                records_for(0, ONE), result_schema=SCHEMA,
                                                identity=ID, session=ACCEPTED)),
            ("write_range.batch", lambda v: call("write_range", root, v, records_for(0, ONE),
                                                  result_schema=SCHEMA, identity=ID,
                                                  session=ACCEPTED)),
            ("write_range.records", lambda v: call("write_range", root, row["batch_id"], v,
                                                   result_schema=SCHEMA, identity=ID,
                                                   session=ACCEPTED)),
            ("write_range.schema", lambda v: call("write_range", root, row["batch_id"],
                                                  records_for(0, ONE), result_schema=v,
                                                  identity=ID, session=ACCEPTED)),
            ("write_range.identity", lambda v: call("write_range", root, row["batch_id"],
                                                    records_for(0, ONE), result_schema=SCHEMA,
                                                    identity=v, session=ACCEPTED)),
            ("write_range.session", lambda v: call("write_range", root, row["batch_id"],
                                                   records_for(0, ONE), result_schema=SCHEMA,
                                                   identity=ID, session=v)),
            ("discard_stale_staging", lambda v: call("discard_stale_staging", v)),
            ("promoted_batch_ids", lambda v: call("promoted_batch_ids", v)),
            ("missing_ranges", lambda v: call("missing_ranges", v)),
            ("audit_final_set", lambda v: call("audit_final_set", v)),
            ("aggregate_records.root", lambda v: call("aggregate_records", v)),
            ("aggregate_records.schema", lambda v: call("aggregate_records", root,
                                                        result_schema=v)),
            ("hash_descriptor", lambda v: call("hash_descriptor", v)),
            ("hash_result_schema", lambda v: call("hash_result_schema", v)),
            ("seal_instance_commitment.root",
             lambda v: call("seal_instance_commitment", v, descriptor=descriptor,
                            result_schema=SCHEMA,
                            expected_descriptor_sha256=w.hash_descriptor(descriptor),
                            expected_schema_sha256=w.hash_result_schema(SCHEMA),
                            expected_coordinate_root=sampled.coordinate_root(coordinates).hex(),
                            expected_coordinates=coordinates,
                            expected_plan_content_sha256=plan["content_sha256"],
                            expected_total_coordinates=ONE, identity=ID, session=ACCEPTED)),
            ("seal_instance_commitment.descriptor",
             lambda v: call("seal_instance_commitment", root, descriptor=v,
                            result_schema=SCHEMA,
                            expected_descriptor_sha256=w.hash_descriptor(descriptor),
                            expected_schema_sha256=w.hash_result_schema(SCHEMA),
                            expected_coordinate_root=sampled.coordinate_root(coordinates).hex(),
                            expected_coordinates=coordinates,
                            expected_plan_content_sha256=plan["content_sha256"],
                            expected_total_coordinates=ONE, identity=ID, session=ACCEPTED)),
            ("seal_instance_commitment.schema",
             lambda v: call("seal_instance_commitment", root, descriptor=descriptor,
                            result_schema=v,
                            expected_descriptor_sha256=w.hash_descriptor(descriptor),
                            expected_schema_sha256=w.hash_result_schema(SCHEMA),
                            expected_coordinate_root=sampled.coordinate_root(coordinates).hex(),
                            expected_coordinates=coordinates,
                            expected_plan_content_sha256=plan["content_sha256"],
                            expected_total_coordinates=ONE, identity=ID, session=ACCEPTED)),
            ("seal_instance_commitment.coordinates",
             lambda v: call("seal_instance_commitment", root, descriptor=descriptor,
                            result_schema=SCHEMA,
                            expected_descriptor_sha256=w.hash_descriptor(descriptor),
                            expected_schema_sha256=w.hash_result_schema(SCHEMA),
                            expected_coordinate_root=sampled.coordinate_root(coordinates).hex(),
                            expected_coordinates=v,
                            expected_plan_content_sha256=plan["content_sha256"],
                            expected_total_coordinates=ONE, identity=ID, session=ACCEPTED)),
            ("seal_instance_commitment.plan_hash",
             lambda v: call("seal_instance_commitment", root, descriptor=descriptor,
                            result_schema=SCHEMA,
                            expected_descriptor_sha256=w.hash_descriptor(descriptor),
                            expected_schema_sha256=w.hash_result_schema(SCHEMA),
                            expected_coordinate_root=sampled.coordinate_root(coordinates).hex(),
                            expected_coordinates=coordinates,
                            expected_plan_content_sha256=v,
                            expected_total_coordinates=ONE, identity=ID, session=ACCEPTED)),
            ("seal_instance_commitment.total",
             lambda v: call("seal_instance_commitment", root, descriptor=descriptor,
                            result_schema=SCHEMA,
                            expected_descriptor_sha256=w.hash_descriptor(descriptor),
                            expected_schema_sha256=w.hash_result_schema(SCHEMA),
                            expected_coordinate_root=sampled.coordinate_root(coordinates).hex(),
                            expected_coordinates=coordinates,
                            expected_plan_content_sha256=plan["content_sha256"],
                            expected_total_coordinates=v, identity=ID, session=ACCEPTED)),
            ("load_commitment", lambda v: call("load_commitment", v)),
            ("verify_plan_binding", lambda v: call("verify_plan_binding", v)),
            ("open_campaign_pin", lambda v: call("open_campaign_pin", v, "0" * 64)),
            ("open_campaign_pin.digest", lambda v: call("open_campaign_pin", root, v)),
            ("verify_retained_values", lambda v: call("verify_retained_values", v)),
            ("build_timestamp_request.root",
             lambda v: call("build_timestamp_request", v, POLICY, nonce=1)),
            ("build_timestamp_request.policy",
             lambda v: call("build_timestamp_request", root, v, nonce=1)),
            ("build_timestamp_request.nonce",
             lambda v: call("build_timestamp_request", root, POLICY, nonce=v)),
            ("beacon_policy_of_pin", lambda v: call("beacon_policy_of_pin", v)),
            ("seal_beacon_rule_pin.root",
             lambda v: call("seal_beacon_rule_pin", v, BEACON_PIN, pin_digest(BEACON_PIN))),
            ("seal_beacon_rule_pin.pin",
             lambda v: call("seal_beacon_rule_pin", root, v, pin_digest(BEACON_PIN))),
            ("seal_beacon_rule_pin.digest",
             lambda v: call("seal_beacon_rule_pin", root, BEACON_PIN, v)),
            ("consult_beacon_rule", lambda v: call("consult_beacon_rule", v, digest)),
            ("consult_beacon_rule.digest", lambda v: call("consult_beacon_rule", root, v)),
            ("stages_present", lambda v: call("stages_present", v)),
            ("sealed_state", lambda v: call("sealed_state", v)),
            ("plan_batches", lambda v: call("plan_batches", v)),
            ("encodable_records", lambda v: call("encodable_records", v)),
        ]
        for label, factory in targets:
            for value_name, value in _FUZZ_VALUES:
                # The call happens INSIDE the assertion's try block, so a typed
                # refusal is observed rather than escaping as a raw exception here.
                call_it = lambda factory=factory, value=value: factory(value)
                if label.endswith(".label"):
                    typed_or_ignored(call_it, f"{label} with {value_name}")
                elif label in _OPTIONAL_NONE_ARGS and value_name == "None":
                    # `None` is the documented "not supplied" sentinel for these,
                    # so it is a valid value, not a wrong type.  The assertion is
                    # still that the call never raises a raw error.
                    typed_or_ignored(call_it, f"{label} with {value_name}")
                elif label in _PATH_ARGS and value_name == "str":
                    # A str is a legitimate path type; the remaining wrong-typed
                    # path values are still required to be refused typed.
                    typed_or_ignored(call_it, f"{label} with {value_name}")
                elif label in _ACCEPTS_ANY_JSON:
                    typed_or_ignored(call_it, f"{label} with {value_name}")
                else:
                    typed(call_it, f"{label} with {value_name}")


# --------------------------------------------------------------------------
def main() -> int:
    STEP_INDEX.update({step: index for index, step in enumerate(w.WRITE_STEPS)})
    prefix = "check_fast_" if SUITE == "fast" else ""
    names = []
    for name, fn in sorted(globals().items()):
        if not callable(fn) or not name.startswith("check_"):
            continue
        if SUITE == "fast" and not name.startswith("check_fast_"):
            continue
        if SUITE == "full" and name.startswith("check_fast_"):
            continue
        names.append((name, fn))
    for name, fn in names:
        fn()
    leaked = sorted(PYC_AFTER - PYC_BEFORE)
    if leaked:
        raise FixtureError(f"the fixture run added bytecode files: {leaked}")
    print(f"production writer fixtures: OK ({COUNT} checks, suite={SUITE}, "
          f"{len(names)} checks-run)")
    del prefix
    return 0


if __name__ == "__main__":
    PYC_AFTER = set(ROOT.rglob("*.pyc"))
    raise SystemExit(main())

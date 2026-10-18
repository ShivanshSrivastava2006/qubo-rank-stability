#!/usr/bin/env python3
"""WP8d-production — the production-capable drawn-instance layout (parallel, v1).

This is a NEW, separately versioned layout module.  It does not modify, patch,
subclass-for-circumvention or re-implement either reviewed package it builds on:

* ``research/g9/wp8d/wp8d_drawn_instance_layout.py`` -- the SYNTHETIC-ONLY
  layout (r3).  Its record builders and record validators are CALLED here (they
  carry no status policy), and its bytes are untouched.
* ``research/g9/wp8b/wp8b_non_synthetic_preparation.py`` -- the reviewed
  non-synthetic preparation path.  Its ``validate_provenance_record`` is the
  ONLY gate through which a prepared record passes here.

Why a parallel module, not an edit
----------------------------------

Owner default 5 ("a reviewed generation-artifact layout, with its
parser/validator bound before the first draw",
``research/decisions/GATE_9_WP7_PINNED_DRAFT_AND_WP7B_OWNER_DECISION.md:146-154``)
is satisfied by the synthetic-only WP8d package, which refuses
``non_synthetic_supported is True`` outright and is deliberately fail-closed.
That fail-closed guarantee is the property the accepted package exists to have,
so widening its accepted status set would destroy it.  This module is therefore
a sibling, not an edit, exactly as WP8d's own notes recommend
(``WP8D_DRAWN_INSTANCE_LAYOUT_NOTES.md:361-392``).

The one thing that changes semantically
======================================

WP8d binds the prepared record to the generation record by its CLAIMED
identity.  That is a hash-and-agreement check between two files.  This module
binds it by CONTENT: the instance envelope itself is a member of the prepared
sidecar, the reader re-parses it from the bound bytes, and the resulting
``SyntheticInstance`` is handed to WP8b, which recomputes the instance digest,
the named identity, the approval's hash binding and every numeric result
through the same frozen WP5b functions the preparation used
(``wp8b_non_synthetic_preparation.py:1330-1467``).

Consequently, on BOTH write and read, a prepared record is accepted only by

    _wp8b.validate_provenance_record(record, instance_from_bound_bytes,
                                     require_production=<path constant>)

with ``require_production`` a constant of the code path, never a caller
argument.  There is no ``production=True`` parameter anywhere in this module's
public interface, no way for a caller to assert validity, and no re-sealing of a
record's own hashes can help: WP8b's anchor recomputes every factual claim from
the instance.

Two layouts, one code path
==========================

``write_instance`` / ``verify_instance``          -> the PRODUCTION path.
``write_standin_instance`` / ``verify_standin_instance`` -> the OFFLINE STAND-IN
path, which validates synthetic fixtures through WP8b with
``require_production=False``.

They are separated here at the SAME two boundaries that separate them in WP8b:

1. a **marker member**.  The production prepared sidecar holds exactly
   ``{PREPARED.json, INSTANCE_ENVELOPE.json, MANIFEST.json}``; the stand-in
   sidecar holds exactly those plus ``STANDIN.json``.  The exact-directory
   check therefore forbids a stand-in marker in a production layout and
   REQUIRES one in a stand-in layout, in both directions.
2. the index's ``layout_kind`` field, cross-bound to the record's own status.

The stand-in path can never be read as production: the reader is selected by a
module constant, a stand-in directory's index says ``non_production_standin``
and its ``STANDIN.json`` says so in a member of its own, and if an attacker
re-seals the index to claim production then WP8b is asked with
``require_production=True`` and refuses the record's own status.

What this module does NOT establish
===================================

* **It is unarmed.**  The production path calls WP8b with
  ``require_production=True``, and WP8b refuses that path while the owner has
  pinned no production release decision record (R6,
  ``wp8b_non_synthetic_preparation.py:894-932``).  So today a production write
  or a production read CANNOT succeed, and the refusal is WP8b's own typed
  ``ProductionReleaseNotPinned``.  Nothing here can be armed until that owner
  gate closes; this module deliberately adds no second, weaker switch.
* **No draw, no seed, no beacon, no scientific step, no network.**  The
  return-matrix bytes and the recorded ``mu_new``/``Sigma_new`` encodings are
  caller inputs (WP8d takes them for the same reason).  The module names,
  binds, rehashes and refuses.  It imports no NumPy.
* **No fabricated approval.**  The adapter never constructs an owner approval
  record and never writes WP8b's production release decision record.  The only
  accepting path exercisable today is WP8b's own non-production fixture branch,
  whose record announces ``prepared_non_production_standin`` in its status.
* **Origin is not in any file.**  A fully re-sealed trio (envelope, record,
  manifests, index) that is self-consistent is still refused by WP8b's approval
  binding, one-use nonce and R6 pin -- none of which live in the layout.  That
  is the honest limit: what binds a layout to a real draw is the approval and
  the pin, not this directory.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
from typing import Any, Mapping, Sequence

from research.g9 import stage2_generation_writer as _writer
from research.g9 import stage2_generator as _generator
from research.g9 import stage2_instance_preparation as _wp5b
from research.g9.wp8b import wp8b_non_synthetic_preparation as _wp8b
from research.g9.wp8d import wp8d_drawn_instance_layout as _layout


ROOT = Path(__file__).resolve().parents[3]

#: Reused unchanged from the reviewed synthetic-only layout.
INSTANCE_ROOT = _layout.INSTANCE_ROOT
SLOT_NAMES = _layout.SLOT_NAMES
SCOPE_STATEMENT = _layout.SCOPE_STATEMENT
MAX_ATTEMPT = _generator.MAX_ATTEMPT
RETURN_MATRIX_BYTES = _layout.RETURN_MATRIX_BYTES
RETURN_MATRIX_NAME = _layout.RETURN_MATRIX_NAME
GENERATION_DIR_NAME = _layout.GENERATION_DIR_NAME
PREPARED_DIR_NAME = _layout.PREPARED_DIR_NAME
META_DIR_NAME = _layout.META_DIR_NAME
INDEX_NAME = "PRODUCTION_INSTANCE.json"
GENERATION_NAME = _layout.GENERATION_NAME
ATTEMPT_NAME = _layout.ATTEMPT_NAME
MANIFEST_NAME = _writer.MANIFEST_NAME
STAGING_PREFIX = _writer.STAGING_PREFIX
PREPARED_NAME = "PREPARED.json"
ENVELOPE_NAME = "INSTANCE_ENVELOPE.json"
STANDIN_MARKER_NAME = "STANDIN.json"

#: The prepared-record status this layout binds in production mode.  Read from
#: WP8b rather than restated, so a WP8b vocabulary change is inherited.
PRODUCTION_STATUS = _wp8b.RECORD_STATUS_PRODUCTION
#: The status WP8b's own fixture branch stamps.  Also read, not restated.
STANDIN_STATUS = _wp8b.RECORD_STATUS_NON_PRODUCTION

#: The two layout kinds.  A production layout is one whose prepared record
#: WP8b validates with ``require_production=True``; a stand-in layout is one
#: validated with ``require_production=False``.  These two constants are the
#: ONLY selectors of that flag in this module.
LAYOUT_KIND_PRODUCTION = "production_instance"
LAYOUT_KIND_STANDIN = "non_production_standin"
LAYOUT_KINDS = (LAYOUT_KIND_PRODUCTION, LAYOUT_KIND_STANDIN)

INDEX_SCHEMA = "decisions_os/g9_wp8d_production_instance_index/v1"
ENVELOPE_SCHEMA = "decisions_os/g9_wp8d_production_instance_envelope/v1"
STANDIN_MARKER_SCHEMA = "decisions_os/g9_wp8d_standin_marker/v1"

ENVELOPE_KEYS = frozenset({"schema", "instance", "content_sha256"})
ENVELOPE_INSTANCE_KEYS = frozenset({
    "instance_id", "synthetic", "canonical_order", "mu", "Sigma", "p",
    "K", "C", "B", "kappa_risk", "sector_of", "sector_labels",
})
STANDIN_MARKER_KEYS = frozenset({
    "schema", "layout_kind", "statement", "content_sha256",
})
STANDIN_MARKER_STATEMENT = (
    "NON-PRODUCTION offline stand-in fixture. Validated through WP8b with "
    "require_production=False. Not a drawn instance, not an accepted instance, "
    "not owner-approved, and refused by the production layout path."
)

PRODUCTION_MEMBERS = (PREPARED_NAME, ENVELOPE_NAME, MANIFEST_NAME)
STANDIN_MEMBERS = (PREPARED_NAME, ENVELOPE_NAME, STANDIN_MARKER_NAME, MANIFEST_NAME)
GENERATION_MEMBERS = _layout.GENERATION_MEMBERS
META_MEMBERS = (INDEX_NAME, MANIFEST_NAME)
SLOT_MEMBERS = (GENERATION_DIR_NAME, META_DIR_NAME, PREPARED_DIR_NAME)

_INDEX_KEYS = frozenset({
    "schema", "layout_kind", "slot", "slot_name", "attempt", "instance_id",
    "generation_id", "prepared_id", "envelope",
    "prepared_record", "generation", "attempt_ledger", "moments",
    "implementation_record", "status", "production", "scope", "content_sha256",
})
_ENVELOPE_REF_KEYS = frozenset({
    "path", "sha256", "content_sha256", "instance_id", "synthetic",
})
_PREPARED_REF_KEYS = frozenset({
    "path", "sha256", "content_sha256", "status", "production",
    "manifest_sha256", "manifest_content_sha256",
})
_GENERATION_REF_KEYS = frozenset({
    "path", "sha256", "content_sha256",
    "manifest_sha256", "manifest_content_sha256",
})
_LEDGER_REF_KEYS = frozenset({
    "path", "sha256", "content_sha256", "attempt", "disposition",
    "rejection_code_count", "rejected_attempt_history_count",
})
_MOMENT_REF_KEYS = frozenset({"mu_new_sha256", "sigma_new_sha256"})


class ProductionLayoutError(ValueError):
    """Typed refusal: unsafe layout, unbound record, or failed promotion."""


def _require(condition: object, message: str) -> None:
    if not condition:
        raise ProductionLayoutError(message)


# ---------------------------------------------------------------------------
# Canonical JSON, hashing, and the on-disk guards
# ---------------------------------------------------------------------------

def _canonical(value: object) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False).encode("ascii")
    except (TypeError, ValueError) as exc:
        raise ProductionLayoutError("record is not canonical JSON") from exc


def _content_sha256(payload: Mapping[str, Any]) -> str:
    """Hash a record with its own content hash removed (WP5's convention)."""
    body = dict(payload)
    body.pop("content_sha256", None)
    return hashlib.sha256(_canonical(body)).hexdigest()


def _sha(value: object, label: str) -> str:
    _require(type(value) is str, f"{label} must be a str")
    _require(len(value) == 64, f"{label} must be exactly 64 characters")
    _require(not set(value) - frozenset("0123456789abcdef"),
             f"{label} must be a lowercase SHA-256")
    return value


def _as_layout(fn, *args, **kwargs):
    """Translate WP5's typed refusal into this module's, keeping the message."""
    try:
        return fn(*args, **kwargs)
    except _writer.GenerationWriterError as exc:
        raise ProductionLayoutError(str(exc)) from exc


def _as_production(fn, *args, **kwargs):
    """Translate the synthetic-only layout's typed refusal into this module's.

    WP8d's record builders and validators raise ``LayoutError``, which is a
    ``ValueError`` but NOT this module's type.  Without this translation a
    caller of :func:`write_instance` or :func:`verify_instance` would have to
    catch two exception types for one class of failure -- an unbound record
    would leave as ``LayoutError`` and an unsafe layout as
    ``ProductionLayoutError`` -- and the fail-closed contract a caller writes
    (``except ProductionLayoutError``) would be silently incomplete.  The
    original message is preserved verbatim and only its type changes.
    """
    try:
        return fn(*args, **kwargs)
    except _layout.LayoutError as exc:
        raise ProductionLayoutError(str(exc)) from exc


def _real_file(path: Path, label: str) -> bytes:
    _require(path.is_file(), f"{label} is missing or not a regular file: {path}")
    _require(not path.is_symlink(), f"{label} is a symlink: {path}")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise ProductionLayoutError(
            f"cannot read {label} {path}: {exc.__class__.__name__}") from exc


def _load_record(path: Path, label: str) -> dict[str, Any]:
    raw = _real_file(path, label)
    try:
        parsed = json.loads(raw.decode("ascii"))
    except UnicodeDecodeError as exc:
        raise ProductionLayoutError(f"{label} is not ASCII") from exc
    except ValueError as exc:
        raise ProductionLayoutError(f"{label} is not JSON") from exc
    _require(type(parsed) is dict, f"{label} must be a JSON object")
    _require(raw == _canonical(parsed), f"{label} is not in canonical form")
    return parsed


def _list_names(directory: Path, label: str) -> list[str]:
    _require(directory.is_dir(), f"{label} is not a directory: {directory}")
    _require(not directory.is_symlink(), f"{label} is a symlink: {directory}")
    try:
        return sorted(os.listdir(directory))
    except OSError as exc:
        raise ProductionLayoutError(f"cannot list {label} {directory}: "
                                    f"{exc.__class__.__name__}") from exc


def _require_exact_names(present: list[str], expected: Sequence[str], label: str) -> None:
    _require(tuple(present) == tuple(sorted(expected)),
             f"{label} contents differ from the canonical layout: "
             f"present={present} expected={sorted(expected)}")


def _require_real_dir(path: Path, label: str) -> None:
    _require(path.is_dir(), f"{label} is not a directory: {path}")
    _require(not path.is_symlink(), f"{label} is a symlink: {path}")


def _require_absent(path: Path, label: str) -> None:
    _require(not path.exists(), f"{label} already exists: {path}")
    _require(not path.is_symlink(), f"{label} is a symlink: {path}")


def _slot_number(slot: object) -> int:
    if type(slot) is str:
        # Wrapped because ``slot_number`` raises ``LayoutError``, and this
        # module's fail-closed contract is that a caller needs exactly ONE
        # exception type.  A traversal or unknown slot name must arrive as a
        # ``ProductionLayoutError`` like every other unsafe-layout refusal.
        return _as_production(_layout.slot_number, slot)
    _require(type(slot) is int, "slot must be an int or a canonical slot name")
    _require(1 <= slot <= len(SLOT_NAMES), "slot must be in 1..5")
    return slot


def _slot_dir(slot: object, root: Path | str) -> Path:
    number = _slot_number(slot)
    return Path(root) / INSTANCE_ROOT / _layout.slot_name(number)


# ---------------------------------------------------------------------------
# The instance envelope: the bytes WP8b re-derives every claim from
# ---------------------------------------------------------------------------

def _is_standin_id(instance_id: object) -> bool:
    return (type(instance_id) is str
            and instance_id.startswith(_wp8b.FIXTURE_INSTANCE_ID_PREFIX)
            and _wp8b.NON_PRODUCTION_LABEL in instance_id)


def build_instance_envelope(instance: object) -> dict[str, Any]:
    """Serialise a WP5b ``SyntheticInstance`` into this layout's envelope.

    The envelope is the bytes the READER hands back to WP8b, so it must carry
    every field of the numeric content digest and nothing else.  ``synthetic``
    is copied verbatim and is required to be exactly ``False`` on the write
    side: WP8b refuses any envelope whose supplied mark is not exactly the bool
    False, and a record prepared from a synthetic envelope would be a
    synthetic-flag confusion.
    """
    _require(isinstance(instance, _wp5b.SyntheticInstance),
             "the instance envelope must be a stage2 SyntheticInstance")
    _require(instance.synthetic is False,
             "the instance envelope must be marked synthetic is False on this path")
    _require(type(instance.instance_id) is str, "instance_id must be a str")
    record: dict[str, Any] = {
        "schema": ENVELOPE_SCHEMA,
        "instance": {
            "instance_id": instance.instance_id,
            "synthetic": False,
            "canonical_order": list(instance.order),
            "mu": list(instance.mu),
            "Sigma": [list(row) for row in instance.Sigma],
            "p": list(instance.p),
            "K": instance.K,
            "C": instance.C,
            "B": instance.B,
            "kappa_risk": instance.kappa,
            "sector_of": dict(instance.sector_of),
            "sector_labels": list(instance.sector_labels),
        },
    }
    record["content_sha256"] = _content_sha256(record)
    return record


def validate_instance_envelope(record: object) -> dict[str, Any]:
    """Validate the envelope's own shape and content hash, and return a copy."""
    _require(type(record) is dict, "instance envelope must be an object")
    _require(set(record) == ENVELOPE_KEYS, "instance envelope has wrong key set")
    _require(record["schema"] == ENVELOPE_SCHEMA, "instance envelope schema mismatch")
    body = record["instance"]
    _require(type(body) is dict, "instance envelope instance must be an object")
    _require(set(body) == ENVELOPE_INSTANCE_KEYS,
             "instance envelope instance has wrong key set")
    _require(record["content_sha256"] == _content_sha256(record),
             "instance envelope content hash mismatch")
    return dict(record)


def _instance_from_envelope(record: Mapping[str, Any]) -> _wp5b.SyntheticInstance:
    """Rebuild the WP5b envelope object from validated envelope bytes.

    Every field is read from the envelope and nothing else, which is what makes
    this the anti-tamper anchor rather than a convenience: the object handed to
    WP8b is a function of the bound bytes, and WP8b recomputes the record's
    digest, identity, approval binding and results from it.
    """
    validated = validate_instance_envelope(record)
    body = validated["instance"]
    return _wp5b.SyntheticInstance(
        instance_id=body["instance_id"],
        synthetic=body["synthetic"],
        order=tuple(body["canonical_order"]),
        mu=tuple(float(value) for value in body["mu"]),
        Sigma=tuple(tuple(float(value) for value in row) for row in body["Sigma"]),
        p=tuple(float(value) for value in body["p"]),
        K=body["K"],
        C=body["C"],
        B=body["B"],
        kappa=body["kappa_risk"],
        sector_of=dict(body["sector_of"]),
        sector_labels=tuple(body["sector_labels"]),
        approval=None,
    )


# ---------------------------------------------------------------------------
# The single gate through which a prepared record passes
# ---------------------------------------------------------------------------

def _validate_prepared(record: object, instance: object, *, require_production: bool
                       ) -> dict[str, Any]:
    """Route a prepared record through WP8b's reviewed validator, and nothing else.

    ``require_production`` here is a parameter of this PRIVATE helper only, and
    its two call sites are the two public code paths, each of which passes a
    module constant.  It is deliberately not threaded through from any public
    signature, so a caller cannot weaken the production path by passing False.
    """
    _require(type(record) is dict, "prepared record must be an object")
    _require(bool(record), "prepared record must be a non-empty object")
    _require(isinstance(instance, _wp5b.SyntheticInstance),
             "the instance supplied to the prepared-record validator must be a "
             "stage2 SyntheticInstance")
    try:
        return _wp8b.validate_provenance_record(
            record, instance, require_production=require_production)
    except _wp8b.NonSyntheticPreparationError as exc:
        raise ProductionLayoutError(
            "prepared record is refused by the reviewed WP8b provenance "
            f"validator (require_production={require_production}): {exc}") from exc


def _require_kind_matches_record(kind: str, validated: Mapping[str, Any]) -> None:
    """Bind the layout kind to the record's OWN status and production flag.

    Two statements, both load-bearing.  On the stand-in path a record claiming
    ``production is True`` is refused even though WP8b's ``require_production=
    False`` would accept it, because a production record must never be filed
    under a non-production marker; on the production path the symmetric check
    is WP8b's own ``require_production=True``, so this pair only adds the
    stand-in half and keeps the two paths from drifting apart.
    """
    production = validated.get("production")
    _require(type(production) is bool,
             "prepared record production flag must be a bool")
    if kind == LAYOUT_KIND_STANDIN:
        _require(production is False,
                 "a stand-in layout must not carry a record claiming production")
    _require(validated.get("status") in _wp8b.RECORD_STATUSES,
             "prepared record status is not a WP8b status")


# ---------------------------------------------------------------------------
# The index
# ---------------------------------------------------------------------------

def build_instance_index(*, layout_kind: str, slot: int, attempt: int, instance_id: str,
                         generation_id: str, prepared_id: str,
                         envelope_sha256: str, envelope_content_sha256: str,
                         prepared_record_sha256: str, prepared_record_status: str,
                         prepared_production: bool,
                         prepared_manifest_sha256: str,
                         prepared_manifest_content_sha256: str,
                         generation_manifest_sha256: str,
                         generation_manifest_content_sha256: str,
                         generation_sha256: str,
                         attempt_record_sha256: str, attempt_record_content_sha256: str,
                         attempt_disposition: str, rejection_code_count: int,
                         rejected_attempt_history_count: int,
                         mu_new_sha256: str, sigma_new_sha256: str,
                         implementation_record_content_sha256: str) -> dict[str, Any]:
    """Render the per-instance index that makes a directory an INSTANCE.

    Beyond the commitments the synthetic-only index carries, this one carries
    ``generation_id`` (the generation record's own content hash), ``prepared_id``
    (the WP8b record's own content hash) and the envelope's bytes hash and
    content hash.  Those three are what bind the three records to ONE instance:
    the reader compares each against the file it actually read, so an index that
    has been re-sealed to point elsewhere is refused by the file, not by the
    index's own arithmetic.
    """
    _require(layout_kind in LAYOUT_KINDS, "layout kind is not a declared layout kind")
    # No standalone slot guard: ``_layout.slot_name(slot)`` on the next line is the
    # reviewed module's own ``_slot_int`` guard and refuses an out-of-range or
    # non-int slot with this module's typed error, so a second copy here would be
    # an unobservable duplicate of one boundary rather than a second boundary.
    _require(0 <= attempt <= MAX_ATTEMPT, "attempt must be in 0..127")
    _require(type(instance_id) is str, "instance_id must be a str")
    _sha(generation_id, "generation id")
    _sha(prepared_id, "prepared id")
    _sha(envelope_sha256, "envelope sha256")
    _sha(envelope_content_sha256, "envelope content sha256")
    _sha(prepared_record_sha256, "prepared record sha256")
    _require(prepared_record_status in _wp8b.RECORD_STATUSES,
             "prepared record status is not a WP8b status")
    _require(type(prepared_production) is bool,
             "prepared production flag must be a bool")
    _sha(prepared_manifest_sha256, "prepared manifest sha256")
    _sha(prepared_manifest_content_sha256, "prepared manifest content sha256")
    _sha(generation_manifest_sha256, "generation manifest sha256")
    _sha(generation_manifest_content_sha256, "generation manifest content sha256")
    _sha(generation_sha256, "generation record sha256")
    _sha(attempt_record_sha256, "attempt record sha256")
    _sha(attempt_record_content_sha256, "attempt record content sha256")
    _require(attempt_disposition == _layout.DISPOSITION_ACCEPTED,
             "the index describes an accepted instance, so its retained-attempt "
             "ledger must claim the accepted disposition")
    _require(type(rejection_code_count) is int, "rejection code count must be an int")
    _require(rejection_code_count >= 0, "rejection code count must be non-negative")
    _require(type(rejected_attempt_history_count) is int,
             "rejected attempt history count must be an int")
    _require(rejected_attempt_history_count >= 0,
             "rejected attempt history count must be non-negative")
    _require(rejected_attempt_history_count <= attempt,
             "more rejected attempts are retained than precede the accepted attempt")
    _sha(mu_new_sha256, "mu_new sha256")
    _sha(sigma_new_sha256, "sigma_new sha256")
    _sha(implementation_record_content_sha256, "implementation record content sha256")
    record: dict[str, Any] = {
        "schema": INDEX_SCHEMA,
        "layout_kind": layout_kind,
        "slot": slot,
        "slot_name": _layout.slot_name(slot),
        "attempt": attempt,
        "instance_id": instance_id,
        "generation_id": generation_id,
        "prepared_id": prepared_id,
        "envelope": {
            "path": f"{PREPARED_DIR_NAME}/{ENVELOPE_NAME}",
            "sha256": envelope_sha256,
            "content_sha256": envelope_content_sha256,
            "instance_id": instance_id,
            "synthetic": False,
        },
        "prepared_record": {
            "path": f"{PREPARED_DIR_NAME}/{PREPARED_NAME}",
            "sha256": prepared_record_sha256,
            "content_sha256": prepared_id,
            "status": prepared_record_status,
            "production": prepared_production,
            "manifest_sha256": prepared_manifest_sha256,
            "manifest_content_sha256": prepared_manifest_content_sha256,
        },
        "generation": {
            "path": GENERATION_DIR_NAME,
            "sha256": generation_sha256,
            "content_sha256": generation_id,
            "manifest_sha256": generation_manifest_sha256,
            "manifest_content_sha256": generation_manifest_content_sha256,
        },
        "attempt_ledger": {
            "path": f"{GENERATION_DIR_NAME}/{ATTEMPT_NAME}",
            "sha256": attempt_record_sha256,
            "content_sha256": attempt_record_content_sha256,
            "attempt": attempt,
            "disposition": attempt_disposition,
            "rejection_code_count": rejection_code_count,
            "rejected_attempt_history_count": rejected_attempt_history_count,
        },
        "moments": {"mu_new_sha256": mu_new_sha256, "sigma_new_sha256": sigma_new_sha256},
        "implementation_record": implementation_record_content_sha256,
        "status": prepared_record_status,
        "production": prepared_production,
        "scope": SCOPE_STATEMENT,
    }
    record["content_sha256"] = _content_sha256(record)
    return record


def validate_instance_index(record: object) -> dict[str, Any]:
    """Validate an index on its own terms and return a copy of it."""
    _require(type(record) is dict, "instance index must be an object")
    _require(set(record) == _INDEX_KEYS, "instance index has wrong key set")
    _require(record["schema"] == INDEX_SCHEMA, "instance index schema mismatch")
    _require(record["layout_kind"] in LAYOUT_KINDS,
             "instance index layout kind is not a declared layout kind")
    _require(record["scope"] == SCOPE_STATEMENT, "instance index scope statement mismatch")
    _require(record["slot_name"] == _layout.slot_name(record["slot"]),
             "instance index slot_name is not the canonical name of its slot")
    _require(0 <= record["attempt"] <= MAX_ATTEMPT,
             "instance index attempt must be in 0..127")
    _require(type(record["instance_id"]) is str, "instance index instance_id must be a str")
    _sha(record["generation_id"], "generation id")
    _sha(record["prepared_id"], "prepared id")
    envelope = record["envelope"]
    _require(type(envelope) is dict, "envelope reference must be an object")
    _require(set(envelope) == _ENVELOPE_REF_KEYS, "envelope reference has wrong key set")
    _require(envelope["path"] == f"{PREPARED_DIR_NAME}/{ENVELOPE_NAME}",
             "envelope reference path mismatch")
    _sha(envelope["sha256"], "envelope sha256")
    _sha(envelope["content_sha256"], "envelope content sha256")
    _require(envelope["instance_id"] == record["instance_id"],
             "envelope reference names a different instance than the index")
    _require(envelope["synthetic"] is False,
             "envelope reference must record the non-synthetic mark False")
    prepared = record["prepared_record"]
    _require(type(prepared) is dict, "prepared_record must be an object")
    _require(set(prepared) == _PREPARED_REF_KEYS, "prepared_record has wrong key set")
    _require(prepared["path"] == f"{PREPARED_DIR_NAME}/{PREPARED_NAME}",
             "prepared_record path mismatch")
    _sha(prepared["sha256"], "prepared record sha256")
    _sha(prepared["content_sha256"], "prepared record content sha256")
    _require(prepared["content_sha256"] == record["prepared_id"],
             "prepared_record content hash disagrees with the index prepared_id")
    _require(prepared["status"] in _wp8b.RECORD_STATUSES,
             "prepared_record status is not a WP8b status")
    _require(type(prepared["production"]) is bool,
             "prepared_record production flag must be a bool")
    _sha(prepared["manifest_sha256"], "prepared manifest sha256")
    _sha(prepared["manifest_content_sha256"], "prepared manifest content sha256")
    generation = record["generation"]
    _require(type(generation) is dict, "generation reference must be an object")
    _require(set(generation) == _GENERATION_REF_KEYS,
             "generation reference has wrong key set")
    _require(generation["path"] == GENERATION_DIR_NAME, "generation reference path mismatch")
    _sha(generation["sha256"], "generation record sha256")
    _sha(generation["content_sha256"], "generation record content sha256")
    _require(generation["content_sha256"] == record["generation_id"],
             "generation content hash disagrees with the index generation_id")
    _sha(generation["manifest_sha256"], "generation manifest sha256")
    _sha(generation["manifest_content_sha256"], "generation manifest content sha256")
    ledger = record["attempt_ledger"]
    _require(type(ledger) is dict, "attempt_ledger must be an object")
    _require(set(ledger) == _LEDGER_REF_KEYS, "attempt_ledger has wrong key set")
    _require(ledger["path"] == f"{GENERATION_DIR_NAME}/{ATTEMPT_NAME}",
             "attempt_ledger path mismatch")
    _sha(ledger["sha256"], "attempt record sha256")
    _sha(ledger["content_sha256"], "attempt record content sha256")
    _require(ledger["attempt"] == record["attempt"],
             "attempt_ledger attempt disagrees with the index attempt")
    _require(ledger["disposition"] == _layout.DISPOSITION_ACCEPTED,
             "the index describes an accepted instance, so its retained-attempt "
             "ledger must claim the accepted disposition")
    _require(type(ledger["rejection_code_count"]) is int,
             "attempt_ledger rejection code count must be an int")
    _require(ledger["rejection_code_count"] == 0,
             "an accepted instance's ledger carries no rejection codes")
    _require(type(ledger["rejected_attempt_history_count"]) is int,
             "attempt_ledger history count must be an int")
    _require(ledger["rejected_attempt_history_count"] <= record["attempt"],
             "more rejected attempts are retained than precede the accepted attempt")
    moments = record["moments"]
    _require(type(moments) is dict, "moments must be an object")
    _require(set(moments) == _MOMENT_REF_KEYS, "moments has wrong key set")
    _sha(moments["mu_new_sha256"], "mu_new sha256")
    _sha(moments["sigma_new_sha256"], "sigma_new sha256")
    _sha(record["implementation_record"], "implementation record content sha256")
    # One status/flag comparison, not two.  The nested ``prepared_record.status``
    # is never compared to the top-level status here: WP8b's record carries a
    # single status, and this index records it in both places from that one
    # source, so the two copies are equal by construction of the builder and a
    # comparison would have no falsifiable input.  The read side DOES compare
    # the nested copy against the prepared FILE, which is a genuinely different
    # object an attacker can rewrite and re-seal -- that comparison is the one
    # that carries weight, and it lives in ``_verify_instance``.
    _require(record["status"] in _wp8b.RECORD_STATUSES,
             "instance index status is not a WP8b status")
    _require(type(record["production"]) is bool,
             "instance index production flag must be a bool")
    _require(record["production"] == prepared["production"],
             "instance index production flag disagrees with its prepared_record "
             "reference")
    _require(record["content_sha256"] == _content_sha256(record),
             "instance index content hash mismatch")
    return dict(record)


def _require_kind_matches_index(kind: str, index: Mapping[str, Any]) -> None:
    """Refuse a layout whose own index says it is the other kind.

    This is the guard that makes an interrupted or re-sealed promotion visible:
    the index is written LAST, and a directory whose index claims a kind other
    than the one the reader opened it as is refused rather than reinterpreted.
    """
    _require(index["layout_kind"] == kind,
             f"instance index declares layout kind {index['layout_kind']!r} but it "
             f"was opened as {kind!r}")


# ---------------------------------------------------------------------------
# Durability and promotion
# ---------------------------------------------------------------------------

def _fsync_dir(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        fd = os.open(str(path), flags)
    except OSError as exc:
        raise ProductionLayoutError(f"cannot open directory {path} for fsync: "
                                    f"{exc.__class__.__name__}") from exc
    try:
        os.fsync(fd)
    except OSError as exc:
        raise ProductionLayoutError(f"cannot fsync directory {path}: "
                                    f"{exc.__class__.__name__}") from exc
    finally:
        os.close(fd)


def _promote(staging: Path, destination: Path) -> None:
    if destination.exists():
        raise ProductionLayoutError(
            f"refusing to overwrite an existing instance directory: {destination}")
    if destination.is_symlink():
        raise ProductionLayoutError(f"refusing to overwrite a symlink target: {destination}")
    try:
        os.rename(str(staging), str(destination))
    except OSError as exc:
        raise ProductionLayoutError(f"cannot promote {staging} to {destination}: "
                                    f"{exc.__class__.__name__}") from exc


# ---------------------------------------------------------------------------
# The write path (one implementation, two kinds)
# ---------------------------------------------------------------------------

def _write_instance(*, layout_kind: str, require_production: bool,
                    slot: int, attempt: int, instance_id: str,
                    sector_partition_sha256: str, feasible_count: int,
                    return_matrix: bytes, prepared_record: Mapping[str, Any],
                    instance: object, implementation_record_content_sha256: str,
                    mu_new: Sequence[str], sigma_new: Sequence[Sequence[str]],
                    rejected_attempt_history: Sequence[Mapping[str, Any]] | None = None,
                    root: Path | str = ROOT) -> dict[str, Any]:
    """Write one instance in this layout, atomically, after WP8b has agreed.

    Order matters and is asserted by the fixtures: the prepared record is
    validated through WP8b BEFORE any directory exists, so an unarmed or
    unauthorised write leaves the tree untouched.

    ``rejected_attempt_history`` defaults to ``None`` and is normalised to an
    empty list here.  WP8d's builder requires an exact ``list``, and its default
    of ``()`` is a tuple that its own history check refuses, so a caller who
    omitted the argument would get a refusal about a default rather than about
    their input.  Normalising in this adapter keeps the reviewed module's bytes
    untouched and the argument genuinely optional.
    """
    _require(layout_kind in LAYOUT_KINDS, "layout kind is not a declared layout kind")
    if rejected_attempt_history is None:
        rejected_attempt_history = []
    envelope_record = build_instance_envelope(instance)
    envelope_instance = _instance_from_envelope(envelope_record)
    validated = _validate_prepared(prepared_record, envelope_instance,
                                   require_production=require_production)
    _require_kind_matches_record(layout_kind, validated)
    identity = envelope_record["instance"]["instance_id"]
    _require(identity == instance_id,
             "the instance envelope names a different instance than the one being written")
    if layout_kind == LAYOUT_KIND_PRODUCTION:
        _require(not _is_standin_id(identity),
                 "the production layout refuses a conspicuously non-production "
                 "stand-in instance id")
    else:
        _require(_is_standin_id(identity),
                 "the stand-in layout prepares only a conspicuously non-production "
                 "stand-in instance id")
    _require(type(return_matrix) is bytes, "return matrix payload must be bytes")
    _require(len(return_matrix) == RETURN_MATRIX_BYTES,
             f"return matrix payload must be exactly {RETURN_MATRIX_BYTES} bytes")
    ledger = _as_production(_layout.build_attempt_record,
                            slot=slot, attempt=attempt,
                            sector_partition_sha256=sector_partition_sha256,
                            feasible_count=feasible_count,
                            rejected_attempt_history=rejected_attempt_history)
    ledger_bytes = _canonical(ledger)
    generation_record = _as_production(_layout.build_generation_record,
                                      slot=slot, attempt=attempt, instance_id=identity,
                                      return_matrix_sha256=hashlib.sha256(
                                          return_matrix).hexdigest(),
                                      implementation_record_content_sha256=(
                                          implementation_record_content_sha256),
                                      mu_new=mu_new, sigma_new=sigma_new)
    generation_bytes = _canonical(generation_record)
    envelope_bytes = _canonical(envelope_record)
    prepared_bytes = _canonical(validated)
    moments = generation_record["moment_summary"]

    parent = Path(root) / INSTANCE_ROOT
    _require_real_dir(parent, "instance root")
    destination = _slot_dir(slot, root)
    _require_absent(destination, "instance directory")
    staging = parent / f"{STAGING_PREFIX}{os.getpid()}-{_layout.slot_name(slot)}"
    _require_absent(staging, "staging path")

    prepared_files: dict[str, bytes] = {
        PREPARED_NAME: prepared_bytes,
        ENVELOPE_NAME: envelope_bytes,
    }
    if layout_kind == LAYOUT_KIND_STANDIN:
        marker: dict[str, Any] = {
            "schema": STANDIN_MARKER_SCHEMA,
            "layout_kind": LAYOUT_KIND_STANDIN,
            "statement": STANDIN_MARKER_STATEMENT,
        }
        marker["content_sha256"] = _content_sha256(marker)
        prepared_files[STANDIN_MARKER_NAME] = _canonical(marker)

    try:
        staging.mkdir()
    except OSError as exc:
        raise ProductionLayoutError(
            f"cannot create staging directory: {exc.__class__.__name__}") from exc
    try:
        generation = _as_layout(_writer.write_generation,
                                target=staging / GENERATION_DIR_NAME,
                                files={ATTEMPT_NAME: ledger_bytes,
                                       GENERATION_NAME: generation_bytes,
                                       RETURN_MATRIX_NAME: return_matrix},
                                implementation_record_content_sha256=(
                                    implementation_record_content_sha256))
        sidecar = _as_layout(_writer.write_generation,
                             target=staging / PREPARED_DIR_NAME,
                             files=prepared_files,
                             implementation_record_content_sha256=(
                                 implementation_record_content_sha256))
        index = build_instance_index(
            layout_kind=layout_kind, slot=slot, attempt=attempt, instance_id=identity,
            generation_id=generation_record["content_sha256"],
            prepared_id=validated["content_sha256"],
            envelope_sha256=hashlib.sha256(envelope_bytes).hexdigest(),
            envelope_content_sha256=envelope_record["content_sha256"],
            prepared_record_sha256=hashlib.sha256(prepared_bytes).hexdigest(),
            prepared_record_status=validated["status"],
            prepared_production=validated["production"],
            prepared_manifest_sha256=_sha_file(
                staging / PREPARED_DIR_NAME / MANIFEST_NAME, "prepared manifest"),
            prepared_manifest_content_sha256=sidecar["manifest_content_sha256"],
            generation_manifest_sha256=_sha_file(
                staging / GENERATION_DIR_NAME / MANIFEST_NAME, "generation manifest"),
            generation_manifest_content_sha256=generation["manifest_content_sha256"],
            generation_sha256=hashlib.sha256(generation_bytes).hexdigest(),
            attempt_record_sha256=hashlib.sha256(ledger_bytes).hexdigest(),
            attempt_record_content_sha256=ledger["content_sha256"],
            attempt_disposition=ledger["disposition"],
            rejection_code_count=len(ledger["rejection_codes"]),
            rejected_attempt_history_count=len(ledger["rejected_attempt_history"]),
            mu_new_sha256=moments["mu_new"]["sha256"],
            sigma_new_sha256=moments["sigma_new"]["sha256"],
            implementation_record_content_sha256=(
                implementation_record_content_sha256))
        meta = _as_layout(_writer.write_generation, target=staging / META_DIR_NAME,
                          files={INDEX_NAME: _canonical(index)},
                          implementation_record_content_sha256=(
                              implementation_record_content_sha256))
        _promote(staging, destination)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    try:
        _fsync_dir(destination)
        _fsync_dir(parent)
    except BaseException as exc:
        try:
            os.rename(str(destination), str(staging))
        except OSError as rollback_exc:
            raise ProductionLayoutError(
                "durability failed after promotion and the rollback to staging also "
                f"failed; {destination} is present and must be inspected by hand: "
                f"{rollback_exc.__class__.__name__}") from exc
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return {
        "target": str(destination),
        "verdict": "written",
        "layout_kind": layout_kind,
        "slot": slot,
        "slot_name": _layout.slot_name(slot),
        "attempt": attempt,
        "instance_id": identity,
        "index": index,
        "index_content_sha256": index["content_sha256"],
        "generation_id": generation_record["content_sha256"],
        "prepared_id": validated["content_sha256"],
        "envelope_sha256": index["envelope"]["sha256"],
        "envelope_content_sha256": envelope_record["content_sha256"],
        "prepared_record_sha256": index["prepared_record"]["sha256"],
        "prepared_record_status": validated["status"],
        "prepared_record_production": validated["production"],
        "generation_manifest_sha256": index["generation"]["manifest_sha256"],
        "generation_manifest_content_sha256": generation["manifest_content_sha256"],
        "prepared_manifest_sha256": index["prepared_record"]["manifest_sha256"],
        "prepared_manifest_content_sha256": sidecar["manifest_content_sha256"],
        "meta_manifest_sha256": _sha_file(destination / META_DIR_NAME / MANIFEST_NAME,
                                          "meta manifest"),
        "meta_manifest_content_sha256": meta["manifest_content_sha256"],
        "return_matrix_sha256": generation_record["return_matrix_sha256"],
        "attempt_record_sha256": hashlib.sha256(ledger_bytes).hexdigest(),
        "attempt_disposition": ledger["disposition"],
        "rejected_attempt_history_count": len(ledger["rejected_attempt_history"]),
        "mu_new_sha256": moments["mu_new"]["sha256"],
        "sigma_new_sha256": moments["sigma_new"]["sha256"],
        "implementation_record_content_sha256": implementation_record_content_sha256,
        "armed": False,
    }


def _sha_file(path: Path, label: str) -> str:
    digest = hashlib.sha256()
    try:
        _require(not path.is_symlink(), f"{label} is a symlink: {path}")
        _require(path.is_file(), f"{label} is missing or not a regular file: {path}")
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
    except OSError as exc:
        raise ProductionLayoutError(f"cannot read {label} {path}: "
                                    f"{exc.__class__.__name__}") from exc
    return digest.hexdigest()


def write_instance(*, slot: int, attempt: int, instance_id: str,
                   sector_partition_sha256: str, feasible_count: int,
                   return_matrix: bytes, prepared_record: Mapping[str, Any],
                   instance: object, implementation_record_content_sha256: str,
                   mu_new: Sequence[str], sigma_new: Sequence[Sequence[str]],
                   rejected_attempt_history: Sequence[Mapping[str, Any]] | None = None,
                   root: Path | str = ROOT) -> dict[str, Any]:
    """Write one PRODUCTION instance.  No production flag is accepted here.

    The prepared record is validated by WP8b with ``require_production=True``.
    While the owner has pinned no production release decision record that call
    refuses (R6), so this function cannot succeed today and never by argument.
    """
    return _write_instance(
        layout_kind=LAYOUT_KIND_PRODUCTION, require_production=True, slot=slot,
        attempt=attempt, instance_id=instance_id,
        sector_partition_sha256=sector_partition_sha256,
        feasible_count=feasible_count, return_matrix=return_matrix,
        prepared_record=prepared_record, instance=instance,
        implementation_record_content_sha256=implementation_record_content_sha256,
        mu_new=mu_new, sigma_new=sigma_new,
        rejected_attempt_history=rejected_attempt_history, root=root)


def write_standin_instance(*, slot: int, attempt: int, instance_id: str,
                           sector_partition_sha256: str, feasible_count: int,
                           return_matrix: bytes, prepared_record: Mapping[str, Any],
                           instance: object, implementation_record_content_sha256: str,
                           mu_new: Sequence[str], sigma_new: Sequence[Sequence[str]],
                           rejected_attempt_history: Sequence[Mapping[str, Any]] | None = None,
                           root: Path | str = ROOT) -> dict[str, Any]:
    """Write one OFFLINE STAND-IN instance for rehearsal only.

    WP8b is asked with ``require_production=False``, so a WP8b fixture-branch
    record is accepted here -- and ONLY here.  The directory is marked in three
    independent places (the ``STANDIN.json`` member, the index ``layout_kind``,
    and the record's own WP8b status), and the production reader refuses it.
    """
    return _write_instance(
        layout_kind=LAYOUT_KIND_STANDIN, require_production=False, slot=slot,
        attempt=attempt, instance_id=instance_id,
        sector_partition_sha256=sector_partition_sha256,
        feasible_count=feasible_count, return_matrix=return_matrix,
        prepared_record=prepared_record, instance=instance,
        implementation_record_content_sha256=implementation_record_content_sha256,
        mu_new=mu_new, sigma_new=sigma_new,
        rejected_attempt_history=rejected_attempt_history, root=root)


# ---------------------------------------------------------------------------
# The read path (one implementation, two kinds)
# ---------------------------------------------------------------------------

def _validated_sidecar(directory: Path, members: Sequence[str], label: str
                       ) -> tuple[dict[str, Any], bytes, dict[str, Any]]:
    present = _list_names(directory, label)
    for name in present:
        _require(not (directory / name).is_dir(),
                 f"{label} contains a subdirectory, which this layout forbids: {name}")
    _require_exact_names(present, members, label)
    _as_layout(_writer.verify_written_generation, directory)
    manifest_bytes = _real_file(directory / MANIFEST_NAME, f"{label} manifest")
    manifest = _as_layout(_writer.validate_manifest,
                          json.loads(manifest_bytes.decode("ascii")))
    _require(manifest_bytes == _canonical(manifest),
             f"{label} manifest is not the canonical encoding of its own content")
    return manifest, manifest_bytes, {"present": present}


def _validate_generation_directory(directory: Path) -> dict[str, Any]:
    manifest, manifest_bytes, extra = _validated_sidecar(
        directory, GENERATION_MEMBERS, "generation directory")
    ledger = _as_production(_layout.validate_attempt_record,
                             _load_record(directory / ATTEMPT_NAME, "attempt record"))
    generation = _as_production(_layout.validate_generation_record,
                               _load_record(directory / GENERATION_NAME,
                                            "generation record"))
    _require(generation["slot"] == ledger["slot"],
             "generation record slot disagrees with the attempt record")
    _require(generation["attempt"] == ledger["attempt"],
             "generation record attempt disagrees with the attempt record")
    _require(manifest["implementation_record_content_sha256"]
             == generation["implementation_record"],
             "the manifest and the generation record name different implementation records")
    matrix_bytes = _real_file(directory / RETURN_MATRIX_NAME, "return matrix")
    _require(len(matrix_bytes) == RETURN_MATRIX_BYTES,
             f"return matrix is not {RETURN_MATRIX_BYTES} bytes: {len(matrix_bytes)}")
    _require(hashlib.sha256(matrix_bytes).hexdigest()
             == generation["return_matrix_sha256"],
             "return matrix content hash does not match the generation record")
    summary = dict(generation["moment_summary"])
    return {
        "slot": generation["slot"],
        "attempt": generation["attempt"],
        "instance_id": generation["instance_id"],
        "content_sha256": generation["content_sha256"],
        "sha256": hashlib.sha256(
            _canonical(generation)).hexdigest(),
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "manifest_content_sha256": manifest["content_sha256"],
        "implementation_record_content_sha256": manifest[
            "implementation_record_content_sha256"],
        "return_matrix_sha256": generation["return_matrix_sha256"],
        "attempt_record_sha256": hashlib.sha256(
            _canonical(ledger)).hexdigest(),
        "attempt_record_content_sha256": ledger["content_sha256"],
        "attempt_disposition": ledger["disposition"],
        "rejection_codes": list(ledger["rejection_codes"]),
        "rejected_attempt_history_count": len(ledger["rejected_attempt_history"]),
        "mu_new_sha256": summary["mu_new"]["sha256"],
        "sigma_new_sha256": summary["sigma_new"]["sha256"],
        "members": extra["present"],
    }


def _validate_prepared_directory(directory: Path, layout_kind: str,
                                 require_production: bool) -> dict[str, Any]:
    members = (STANDIN_MEMBERS if layout_kind == LAYOUT_KIND_STANDIN
               else PRODUCTION_MEMBERS)
    manifest, manifest_bytes, _ = _validated_sidecar(directory, members,
                                                     "prepared sidecar")
    # The envelope is read and re-parsed FIRST, and the object WP8b validates the
    # record against is built from those bytes alone.  That ordering is the whole
    # point of this module: the anchor is content, not a claim.
    envelope_record = _load_record(directory / ENVELOPE_NAME, "instance envelope")
    envelope_instance = _instance_from_envelope(envelope_record)
    prepared_bytes = _real_file(directory / PREPARED_NAME, "prepared record")
    prepared = _load_record(directory / PREPARED_NAME, "prepared record")
    validated = _validate_prepared(prepared, envelope_instance,
                                   require_production=require_production)
    _require_kind_matches_record(layout_kind, validated)
    if layout_kind == LAYOUT_KIND_STANDIN:
        marker = _load_record(directory / STANDIN_MARKER_NAME, "stand-in marker")
        _require(set(marker) == STANDIN_MARKER_KEYS,
                 "stand-in marker has wrong key set")
        _require(marker["schema"] == STANDIN_MARKER_SCHEMA,
                 "stand-in marker schema mismatch")
        _require(marker["layout_kind"] == LAYOUT_KIND_STANDIN,
                 "stand-in marker does not declare the stand-in layout kind")
        _require(marker["statement"] == STANDIN_MARKER_STATEMENT,
                 "stand-in marker statement mismatch")
        _require(marker["content_sha256"] == _content_sha256(marker),
                 "stand-in marker content hash mismatch")
    return {
        "status": validated["status"],
        "production": validated["production"],
        "instance_id": validated["instance"]["instance_id"],
        "content_sha256": validated["content_sha256"],
        "sha256": hashlib.sha256(prepared_bytes).hexdigest(),
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "manifest_content_sha256": manifest["content_sha256"],
        "implementation_record_content_sha256": manifest[
            "implementation_record_content_sha256"],
        "envelope_sha256": hashlib.sha256(_canonical(envelope_record)).hexdigest(),
        "envelope_content_sha256": envelope_record["content_sha256"],
        "envelope_instance_id": envelope_record["instance"]["instance_id"],
        "instance": envelope_instance,
    }


def _validate_meta_directory(directory: Path) -> dict[str, Any]:
    manifest, manifest_bytes, _ = _validated_sidecar(directory, META_MEMBERS,
                                                     "meta sidecar")
    index = validate_instance_index(_load_record(directory / INDEX_NAME,
                                                 "instance index"))
    return {
        "index": index,
        "index_sha256": hashlib.sha256(_canonical(index)).hexdigest(),
        "index_content_sha256": index["content_sha256"],
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "manifest_content_sha256": manifest["content_sha256"],
        "implementation_record_content_sha256": manifest[
            "implementation_record_content_sha256"],
    }


def _verify_instance(*, layout_kind: str, require_production: bool, slot: object,
                     root: Path | str) -> dict[str, Any]:
    """Verify one promoted instance end to end, as one of the two kinds."""
    _require(layout_kind in LAYOUT_KINDS, "layout kind is not a declared layout kind")
    number = _slot_number(slot)
    base = _slot_dir(number, root)
    _require_exact_names(_list_names(base, "instance directory"), SLOT_MEMBERS,
                         "instance directory")
    generation = _validate_generation_directory(base / GENERATION_DIR_NAME)
    prepared = _validate_prepared_directory(base / PREPARED_DIR_NAME, layout_kind,
                                            require_production)
    meta = _validate_meta_directory(base / META_DIR_NAME)
    index = meta["index"]
    _require_kind_matches_index(layout_kind, index)
    # The records must agree with the REQUESTED slot, not merely with each other.
    _require(generation["slot"] == number,
             "the generation record names a different slot than the instance directory")
    _require(index["slot"] == number,
             "instance index slot disagrees with the instance directory")
    _require(generation["attempt"] == index["attempt"],
             "the generation record attempt disagrees with the index")
    for label, left, right in (
        ("prepared sidecar", prepared["implementation_record_content_sha256"],
         generation["implementation_record_content_sha256"]),
        ("meta sidecar", meta["implementation_record_content_sha256"],
         generation["implementation_record_content_sha256"]),
        ("index", index["implementation_record"],
         generation["implementation_record_content_sha256"]),
    ):
        _require(left == right,
                 f"the {label} and the generation name different implementation records")
    # The identity chain: four records must name ONE instance.
    _require(prepared["instance_id"] == generation["instance_id"],
             "the prepared record names a different instance than the generation")
    _require(prepared["envelope_instance_id"] == generation["instance_id"],
             "the instance envelope names a different instance than the generation")
    _require(index["instance_id"] == generation["instance_id"],
             "the instance index names a different instance than the generation")
    # The content chain: three ids, each compared against the file it names.
    _require(index["generation_id"] == generation["content_sha256"],
             "the instance index does not name this generation record's content hash")
    _require(index["generation"]["sha256"] == generation["sha256"],
             "the instance index does not name this generation record's bytes")
    _require(index["prepared_id"] == prepared["content_sha256"],
             "the instance index does not name this prepared record's content hash")
    _require(index["prepared_record"]["sha256"] == prepared["sha256"],
             "the instance index does not name this prepared record's bytes")
    _require(index["envelope"]["sha256"] == prepared["envelope_sha256"],
             "the instance index does not name this instance envelope's bytes")
    _require(index["envelope"]["content_sha256"] == prepared["envelope_content_sha256"],
             "the instance index does not name this instance envelope's content hash")
    _require(index["prepared_record"]["status"] == prepared["status"],
             "the instance index prepared_record status disagrees with the prepared record")
    _require(index["status"] == prepared["status"],
             "the instance index status disagrees with the prepared record")
    _require(index["prepared_record"]["production"] == prepared["production"],
             "the instance index production flag disagrees with the prepared record")
    _require(index["production"] == prepared["production"],
             "the instance index production flag disagrees with the prepared record")
    if layout_kind == LAYOUT_KIND_PRODUCTION:
        _require(prepared["status"] == PRODUCTION_STATUS,
                 "a production layout must carry a production prepared record")
        _require(prepared["production"] is True,
                 "a production layout must carry a production prepared record")
    else:
        _require(prepared["status"] == STANDIN_STATUS,
                 "a stand-in layout must carry a non-production stand-in record")
        _require(prepared["production"] is False,
                 "a stand-in layout must not carry a production record")
    # The manifest bytes and content hashes, both directions, from outside.
    _require(index["generation"]["manifest_sha256"] == generation["manifest_sha256"],
             "the instance index does not name this generation manifest's bytes")
    _require(index["generation"]["manifest_content_sha256"]
             == generation["manifest_content_sha256"],
             "the instance index does not name this generation manifest's content hash")
    _require(index["prepared_record"]["manifest_sha256"] == prepared["manifest_sha256"],
             "the instance index does not name this prepared manifest's bytes")
    _require(index["prepared_record"]["manifest_content_sha256"]
             == prepared["manifest_content_sha256"],
             "the instance index does not name this prepared manifest's content hash")
    ledger = index["attempt_ledger"]
    _require(ledger["sha256"] == generation["attempt_record_sha256"],
             "the instance index does not name this retained-attempt ledger's bytes")
    _require(ledger["content_sha256"] == generation["attempt_record_content_sha256"],
             "the instance index does not name this retained-attempt ledger's content hash")
    _require(ledger["attempt"] == generation["attempt"],
             "the instance index attempt_ledger attempt disagrees with the ledger")
    _require(ledger["disposition"] == generation["attempt_disposition"],
             "the instance index attempt_ledger disposition disagrees with the ledger")
    _require(ledger["rejection_code_count"] == len(generation["rejection_codes"]),
             "the instance index rejection code count disagrees with the ledger")
    _require(ledger["rejected_attempt_history_count"]
             == generation["rejected_attempt_history_count"],
             "the instance index history count disagrees with the ledger")
    _require(index["moments"]["mu_new_sha256"] == generation["mu_new_sha256"],
             "the instance index does not name this generation's mu_new digest")
    _require(index["moments"]["sigma_new_sha256"] == generation["sigma_new_sha256"],
             "the instance index does not name this generation's Sigma_new digest")
    return {
        "verdict": "verified",
        "target": str(base),
        "layout_kind": layout_kind,
        "slot": generation["slot"],
        "slot_name": _layout.slot_name(generation["slot"]),
        "attempt": generation["attempt"],
        "instance_id": generation["instance_id"],
        "index_content_sha256": index["content_sha256"],
        "index_sha256": meta["index_sha256"],
        "generation_id": generation["content_sha256"],
        "prepared_id": prepared["content_sha256"],
        "prepared_record_status": prepared["status"],
        "prepared_record_production": prepared["production"],
        "envelope_sha256": prepared["envelope_sha256"],
        "envelope_content_sha256": prepared["envelope_content_sha256"],
        "generation_manifest_sha256": generation["manifest_sha256"],
        "generation_manifest_content_sha256": generation["manifest_content_sha256"],
        "prepared_manifest_sha256": prepared["manifest_sha256"],
        "prepared_manifest_content_sha256": prepared["manifest_content_sha256"],
        "meta_manifest_sha256": meta["manifest_sha256"],
        "meta_manifest_content_sha256": meta["manifest_content_sha256"],
        "implementation_record_content_sha256": generation[
            "implementation_record_content_sha256"],
        "return_matrix_sha256": generation["return_matrix_sha256"],
        "attempt_record_sha256": generation["attempt_record_sha256"],
        "attempt_disposition": generation["attempt_disposition"],
        "rejected_attempt_history_count": generation["rejected_attempt_history_count"],
        "mu_new_sha256": generation["mu_new_sha256"],
        "sigma_new_sha256": generation["sigma_new_sha256"],
        "armed": False,
    }


def verify_instance(slot: object, *, root: Path | str = ROOT) -> dict[str, Any]:
    """Verify one PRODUCTION instance, through WP8b with require_production=True."""
    return _verify_instance(layout_kind=LAYOUT_KIND_PRODUCTION,
                            require_production=True, slot=slot, root=root)


def verify_standin_instance(slot: object, *, root: Path | str = ROOT) -> dict[str, Any]:
    """Verify one OFFLINE STAND-IN instance, through WP8b with require_production=False."""
    return _verify_instance(layout_kind=LAYOUT_KIND_STANDIN,
                            require_production=False, slot=slot, root=root)


# ---------------------------------------------------------------------------
# Resume, and the whole-tree sweep
# ---------------------------------------------------------------------------

def _instance_root(root: Path | str) -> Path:
    return Path(root) / INSTANCE_ROOT


def _root_entries(root: Path | str) -> list[str]:
    directory = _instance_root(root)
    _require_real_dir(directory, "instance root")
    try:
        return sorted(os.listdir(directory))
    except OSError as exc:
        raise ProductionLayoutError(f"cannot list the instance root {directory}: "
                                    f"{exc.__class__.__name__}") from exc


def resume_standin(*, slot: object, root: Path | str = ROOT,
                   reverify: bool = True) -> dict[str, Any]:
    """Resume a rehearsal: report an already-promoted stand-in slot, or its absence.

    This is the RESUME rehearsal's whole semantics.  An interrupted or already
    written slot is NOT rewritten: the writer refuses to merge into an existing
    directory, so resuming means verifying what is there and reporting the exact
    commitments, or reporting that the slot is free to write.  A staging
    directory left behind by an interrupted promotion is refused by name here,
    because it is not a slot and must not be mistaken for one.
    """
    number = _slot_number(slot)
    entries = _root_entries(root)
    for name in entries:
        _require(not name.startswith(STAGING_PREFIX),
                 f"the instance root holds an interrupted staging directory: {name}")
        _slot_number(name)
    name = _layout.slot_name(number)
    base = _slot_dir(number, root)
    if not base.exists():
        return {
            "verdict": "absent",
            "layout_kind": LAYOUT_KIND_STANDIN,
            "slot": number,
            "slot_name": name,
            "writable": True,
            "resumed": False,
        }
    if not reverify:
        return {
            "verdict": "present",
            "layout_kind": LAYOUT_KIND_STANDIN,
            "slot": number,
            "slot_name": name,
            "writable": False,
            "resumed": True,
        }
    summary = verify_standin_instance(number, root=root)
    summary["writable"] = False
    summary["resumed"] = True
    return summary


def verify_all_standin_slots(*, root: Path | str = ROOT,
                             present: Sequence[int] = ()) -> dict[str, Any]:
    """Verify every stand-in slot that exists under ``root``, refusing a stray one."""
    found = _root_entries(root)
    for name in found:
        _slot_number(name)
    if present:
        expected = sorted(_layout.slot_name(slot) for slot in present)
        _require(found == expected,
                 f"instance root holds {found}, expected exactly {expected}")
    summaries = [verify_standin_instance(name, root=root) for name in found]
    _require(len({summary["instance_id"] for summary in summaries}) == len(summaries),
             "two slots name the same instance_id")
    return {
        "verdict": "verified",
        "layout_kind": LAYOUT_KIND_STANDIN,
        "root": str(_instance_root(root)),
        "slots": [summary["slot_name"] for summary in summaries],
        "count": len(summaries),
        "instances": summaries,
    }
"""UNAPPROVED Stage-2 generator production path: implementation record, approval
check and guarded draw wrapper (WP5, items 1-3 of the pre-run source review).

This module closes the three integration gaps the pre-run review named, and it
closes them so that closing them is worth nothing on its own:

* ``build_candidate_implementation_record`` renders a record that pins the
  generator, the generation-contract validator, the planner and the guard
  sources **and** the complete CPython/NumPy/backend runtime fingerprint, using
  the guard's own capture functions rather than re-implementing them.  Every
  record it renders says ``unapproved_candidate`` / ``owner_approval: absent``;
  there is no argument, and no code path here, that renders anything else.
* ``check_against_record`` refuses unless the caller supplies an approval that
  names the record's exact content sha256 and is not synthetic.  An approval
  that says ``synthetic`` is refused unless the caller additionally passes the
  module's exported ``FIXTURE_CONTEXT_TOKEN`` through the explicit, named
  ``fixture_context`` argument.
* ``draw_screened_attempt`` wraps the frozen pure draw API with a before-draw
  capture, a start/end drift check against the approved record, the draw
  itself, and an after-draw capture.

THE REAL STAGE-2 SEED IS NOT USABLE HERE.  The preregistered master seed lives
in the frozen generator as ``stage2_generator.MASTER_SEED`` and reaches every
stream through ``PROTOCOL_PREFIX``.  That master seed and that prefix are the
unpublished material: a draw with them is a real candidate draw.  The wrapper
rejects any material carrying them, and a rejection is **terminal** - it does
not merely skip the record, it stops the attempt - so a permitted material
cannot be reached by a later retry inside the same call.  No code in this
repository, and no fixture in this repository, produces an approval that passes
``check_against_record`` on a non-synthetic path, so the only seed material
any fixture can draw with is synthetic.

Authority direction: this module *consumes* owner approval.  It never produces
it.  A green fixture run is not a draw permission, and no record, snapshot or
approval object it accepts is read as authorization - it is read as a claim to
be checked against a pin the caller supplied independently.

KNOWN LIMITS (candidate design, not approved policy):
- The independent pin relies on the caller pinning the record hash outside this
  module; the guard's own circular-pin limit applies to the embedded record.
- The wrapper's two captures bracket the draw, so a change made and reverted
  between them is not observed.
- ``check_against_record`` and the guard's ``verify_start_end`` re-validate the
  record but do not re-capture; drift is detected by the wrapper's captures.
- Source hashes reflect the files on disk, not the exact bytes in memory.
- The synthetic-fixture code path is a real branch in this module.  It exists
  only because the fixtures must exercise the refusal and the wrapper without
  a real draw; it is the one path on which a synthetic approval is honoured,
  and it announces itself in the returned evidence.
- A rejected material is a data-dependent branch, so a mutant that special-cases
  it would only be reached by a fixture that supplies that exact material.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

from research.g9 import stage2_generation_contract as contract
from research.g9 import stage2_generator as generator
from research.g9 import stage2_generator_guard as guard


ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "decisions_os/g9_stage2_generation_implementation_record/candidate-v1"
RECORD_STATUS = "unapproved_candidate"
OWNER_APPROVAL = "absent"
APPROVAL_STATEMENT = (
    "Unapproved candidate record. Exact equality with it is evidence that the "
    "pinned sources and the full CPython/NumPy/backend runtime fingerprint are "
    "the ones recorded; it is not owner approval and does not authorize any "
    "draw or write."
)
DRAW_APPROVAL_STATEMENT = (
    "Owner draw approval asserted for the named implementation record. It "
    "confirms only that the sources and runtime at draw time are the approved "
    "ones."
)
SYNTHETIC_APPROVAL_LABEL = "synthetic"
SYNTHETIC_DRAW_AUTHORITY = "synthetic_fixture_only"
DRAW_EVIDENCE_STATEMENT = (
    "Draw performed only after the observed start and end captures both "
    "matched the approved record exactly and the seed material passed the "
    "material gate."
)
MATERIAL_EVIDENCE_STATEMENT = (
    "No owner draw approval exists in this repository, so the real "
    "preregistered Stage-2 seed material is refused here."
)
APPROVAL_KEYS = {
    "schema",
    "status",
    "approves_record_content_sha256",
    "statement",
    "label",
    "scope",
}
APPROVAL_SCHEMA = "decisions_os/g9_stage2_generation_approval/v1"
APPROVAL_STATUS = "owner_approved"
OWNER_APPROVAL_SCOPE = "stage2_generator_draw"
FIXTURE_APPROVAL_SCOPE = "synthetic_fixture_draw"
# The exported token for the fixture-only path.  It is not a secret and is not
# authority: it exists so that the synthetic branch is reachable only by a
# caller that names it explicitly, and the returned evidence says so.
FIXTURE_CONTEXT_TOKEN = "stage2_generation_release.fixtures"
FIXTURE_SCOPE_REQUIRES_SYNTHETIC_LABEL = True
# Sources the record pins beyond the guard's own three.  Content hashes come
# from the guard's _file_sha256, which turns an unreadable file into a typed
# refusal; only this module's sys.path bootstrap is re-implemented, because it
# is the one thing the guard (deliberately) does not do.
EXTRA_SOURCE_PATHS = {
    "planner": "research/g9/plan_stage2_generator.py",
    "contract": "research/g9/stage2_generation_contract.py",
}
RELEASE_MODULE_PATH = "research/g9/stage2_generation_release.py"
# Seed material that reaches a real stream.  Taken from the frozen generator's
# protocol constants; the generator's preregistration of the numbers does not
# publish the stream material they derive.
REAL_MATERIAL_MARKERS = (
    str(generator.MASTER_SEED),
    generator.MASTER_SEED_HEX,
    generator.PROTOCOL_PREFIX,
)
# The number of draws this build has performed.  It exists so that a mutant
# that drops the before-draw or after-draw check still performs a real call
# into the frozen pure API; without it, mutating the guard calls could not be
# distinguished from neutering them.
DRAW_CALL_COUNT = 0


class GenerationReleaseError(ValueError):
    """Typed refusal: malformed input, unapproved release, or refused material."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise GenerationReleaseError(message)


def _sha(value: object, label: str) -> str:
    if type(value) is not str or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise GenerationReleaseError(f"{label} must be a lowercase SHA-256")
    return value


def _canonical(value: object) -> bytes:
    try:
        return guard.canonical_bytes(value)
    except guard.GeneratorGuardError as exc:
        raise GenerationReleaseError("value is not canonical JSON") from exc


def _content_sha256(record: Mapping[str, Any]) -> str:
    body = dict(record)
    body.pop("content_sha256", None)
    return hashlib.sha256(_canonical(body)).hexdigest()


# --------------------------------------------------------------------------
# 1. The implementation record
# --------------------------------------------------------------------------
def _bootstrap_path() -> None:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))


def _extra_source_hashes() -> dict[str, dict[str, str]]:
    hashes: dict[str, dict[str, str]] = {}
    for label, rel in EXTRA_SOURCE_PATHS.items():
        hashes[label] = {"path": rel, "sha256": guard._file_sha256(ROOT / rel)}
    return hashes


def build_candidate_implementation_record() -> dict[str, object]:
    """Capture this process and render it as an UNAPPROVED candidate record.

    The capture is the guard's own ``capture_snapshot`` (which in turn uses
    ``capture_sources``/``capture_runtime``); the four-source map and the
    backend fingerprint are added here because the preregistered pre-run
    review requires the planner and the complete backend identity to be pinned
    as well.  Status is a module constant: there is no argument that can make
    this function emit an approved record.
    """
    _bootstrap_path()
    try:
        snapshot = guard.capture_snapshot()
    except guard.GeneratorGuardError as exc:
        raise GenerationReleaseError(f"implementation capture failed: {exc}") from exc
    record: dict[str, object] = {
        "schema": SCHEMA,
        "status": RECORD_STATUS,
        "owner_approval": OWNER_APPROVAL,
        "approval_statement": APPROVAL_STATEMENT,
        "sources": {
            "guard": snapshot["sources"]["guard"],
            "generator": snapshot["sources"]["generator"],
            "validator": snapshot["sources"]["validator"],
            "planner": _extra_source_hashes()["planner"],
            "contract": _extra_source_hashes()["contract"],
            "release": {
                "path": RELEASE_MODULE_PATH,
                "sha256": guard._file_sha256(ROOT / RELEASE_MODULE_PATH),
            },
        },
        "runtime": snapshot["runtime"],
        "backend_fingerprint": generator.runtime_fingerprint(),
    }
    record["content_sha256"] = _content_sha256(record)
    return record


def validate_candidate_implementation_record(
    record: object, expected_content_sha256: str
) -> dict[str, object]:
    """Accept only an intact, self-consistent unapproved candidate record."""
    if type(record) is not dict:
        raise GenerationReleaseError("implementation record must be an object")
    expected_keys = {
        "schema",
        "status",
        "owner_approval",
        "approval_statement",
        "sources",
        "runtime",
        "backend_fingerprint",
        "content_sha256",
    }
    _require(set(record) == expected_keys, "implementation record has wrong key set")
    _require(record["schema"] == SCHEMA, "implementation record schema mismatch")
    _require(record["status"] == RECORD_STATUS,
             "record status must be unapproved_candidate; this module never renders an approved record")
    _require(record["owner_approval"] == OWNER_APPROVAL,
             "record owner_approval must be absent; this module never renders an approved record")
    _require(record["approval_statement"] == APPROVAL_STATEMENT, "record approval statement mismatch")
    required_sources = {"guard", "generator", "validator", "planner", "contract", "release"}
    _require(type(record["sources"]) is dict and set(record["sources"]) == required_sources,
             "record must pin the generator, validator, contract, planner, guard and release sources")
    for label, entry in record["sources"].items():
        if type(entry) is not dict or set(entry) != {"path", "sha256"}:
            raise GenerationReleaseError(f"record source {label} has wrong key set")
        _require(type(entry["path"]) is str and entry["path"], f"record source {label} path malformed")
        _sha(entry["sha256"], f"record source {label} sha256")
    _require(record["sources"]["generator"]["path"] == "research/g9/stage2_generator.py",
             "record must pin the generator at its declared path")
    _require(record["sources"]["validator"]["path"] == "research/g9/stage2_generation_contract.py",
             "record must pin the generation-contract validator at its declared path")
    _require(record["sources"]["planner"]["path"] == "research/g9/plan_stage2_generator.py",
             "record must pin the planner at its declared path")
    _require(record["sources"]["contract"]["path"] == "research/g9/stage2_generation_contract.py",
             "record must pin the generation contract at its declared path")
    _require(record["sources"]["release"]["path"] == RELEASE_MODULE_PATH,
             "record must pin this release module at its declared path")
    try:
        # The guard's snapshot schema admits exactly its own three sources, so
        # it validates the runtime and those three; the extra pinned sources
        # are validated above against their declared paths.
        guard.validate_snapshot({
            "sources": {label: record["sources"][label] for label in guard.SOURCE_PATHS},
            "runtime": record["runtime"],
        })
    except guard.GeneratorGuardError as exc:
        raise GenerationReleaseError(f"implementation record snapshot invalid: {exc}") from exc
    _validate_backend_fingerprint(record["backend_fingerprint"])
    # No shape check on record["content_sha256"] here: _content_sha256 always
    # returns 64 lowercase hex, so equality with it already implies that shape.
    # A separate _sha call was an unobservable duplicate -- the mutation table
    # showed that deleting it left every fixture passing, because the
    # re-derivation below refuses every malformed value first.
    _require(record["content_sha256"] == _content_sha256(record), "record content hash mismatch")
    _require(expected_content_sha256 is not None, "expected record SHA-256 is required")
    _require(_sha(expected_content_sha256, "expected record SHA-256") == record["content_sha256"],
             "record is not the independently pinned record")
    return dict(record)


def _validate_backend_fingerprint(fingerprint: object) -> None:
    _require(type(fingerprint) is dict, "backend fingerprint must be an object")
    _require(set(fingerprint) == set(generator.runtime_fingerprint()),
             "backend fingerprint has wrong key set")


# --------------------------------------------------------------------------
# 2. The approval check
# --------------------------------------------------------------------------
def _validate_approval(approval: object) -> dict[str, object]:
    if type(approval) is not dict:
        raise GenerationReleaseError("approval must be an object")
    _require(set(approval) == APPROVAL_KEYS, "approval has wrong key set")
    _require(approval["schema"] == APPROVAL_SCHEMA, "approval schema mismatch")
    _require(approval["status"] == APPROVAL_STATUS,
             "approval status must be owner_approved; no other status is accepted")
    _require(type(approval["statement"]) is str and approval["statement"] == DRAW_APPROVAL_STATEMENT,
             "approval statement mismatch")
    _require(type(approval["label"]) is str and approval["label"],
             "approval label must be a non-empty string")
    _sha(approval["approves_record_content_sha256"], "approves_record_content_sha256")
    _require(type(approval["scope"]) is str and approval["scope"],
             "approval scope must be a non-empty string")
    return dict(approval)


def check_against_record(
    record: object,
    approval: object,
    expected_content_sha256: str,
    *,
    fixture_context: object = None,
) -> tuple[dict[str, object], dict[str, object]]:
    """Accept only an owner approval that names this record's exact content hash.

    Returns ``(evidence, validated_record)``.  A synthetic approval is refused
    on every path except the explicit fixture-only branch, which is reachable
    only when the caller passes the module's ``FIXTURE_CONTEXT_TOKEN`` as
    ``fixture_context``; the evidence there says ``owner_approved: absent``
    regardless of the label the approval carries.
    """
    body = validate_candidate_implementation_record(record, expected_content_sha256)
    approval_body = _validate_approval(approval)
    if approval_body["approves_record_content_sha256"] != body["content_sha256"]:
        raise GenerationReleaseError(
            "approval does not name this record's exact content SHA-256"
        )
    synthetic = approval_body["label"] == SYNTHETIC_APPROVAL_LABEL
    if synthetic:
        # The ONE fixture-only branch.  Reaching it requires naming the token.
        _require(fixture_context == FIXTURE_CONTEXT_TOKEN,
                 "approval is labelled synthetic; a synthetic approval is accepted only on the "
                 "explicit fixture-only path, and grants no authority anywhere else")
        _require(approval_body["scope"] == FIXTURE_APPROVAL_SCOPE,
                 "synthetic approval must carry the synthetic fixture scope")
        return {
            "checked": "synthetic_fixture_path",
            "record_content_sha256": body["content_sha256"],
            "record_status": body["status"],
            "synthetic": True,
            "owner_approved": "absent",
            "draw_authority": SYNTHETIC_DRAW_AUTHORITY,
            "statement": MATERIAL_EVIDENCE_STATEMENT,
        }, body
    _require(approval_body["scope"] == OWNER_APPROVAL_SCOPE,
             "owner approval scope mismatch")
    return {
        "checked": "owner_approval",
        "record_content_sha256": body["content_sha256"],
        "record_status": body["status"],
        "synthetic": False,
        "owner_approved": "present",
        "draw_authority": "asserted_by_approval",
        "statement": DRAW_APPROVAL_STATEMENT,
    }, body


# --------------------------------------------------------------------------
# 3. The guarded draw wrapper
# --------------------------------------------------------------------------
def seed_is_permitted_material(material_ascii: object) -> bool:
    """REFUSE the real preregistered Stage-2 seed material.

    The master seed and the protocol prefix are the unpublished stream
    material; a draw that carries either is a real candidate draw.  The
    comparison is exact, so any material this build can construct is refused
    unless it differs from the real one.
    """
    if type(material_ascii) is not str or not material_ascii:
        return False
    return not any(marker in material_ascii for marker in REAL_MATERIAL_MARKERS)


def _require_permitted_material(
    seed: generator.StreamSeed, *, real_material_authorized: bool
) -> None:
    """Refuse the real seed material unless a real owner approval says otherwise.

    ``real_material_authorized`` is True only for a non-synthetic owner draw
    approval issued outside the fixture path; nothing in this repository
    produces one, so in this build the real material is always refused.
    """
    if real_material_authorized or seed_is_permitted_material(seed.material_ascii):
        return
    raise GenerationReleaseError(
        "refusing to draw the real preregistered Stage-2 seed material "
        f"(slot={seed.slot} attempt={seed.attempt} purpose={seed.purpose}); "
        "it needs a non-synthetic owner draw approval, and no code or fixture "
        "in this repository produces one"
    )


def _approval_permits_real_material(approval: object, fixture_context: object) -> bool:
    """Whether the approval is a non-synthetic owner approval for a real draw.

    Kept separate from ``check_against_record`` so the wrapper is explicit
    about which check gates which action.  No approval produced anywhere in this
    repository returns True from here.
    """
    if approval is None:
        return False
    if fixture_context == FIXTURE_CONTEXT_TOKEN:
        return False
    body = _validate_approval(approval)
    if body["label"] == SYNTHETIC_APPROVAL_LABEL:
        return False
    return body["status"] == APPROVAL_STATUS and body["scope"] == OWNER_APPROVAL_SCOPE


def _pinned_view(record: Mapping[str, Any]) -> dict[str, object]:
    """The snapshot-shaped view of an already validated record."""
    return {
        "sources": {label: record["sources"][label] for label in guard.SOURCE_PATHS},
        "runtime": record["runtime"],
    }


def _require_no_drift(expected: object, observed: object, message: str) -> None:
    """Refuse unless an observed capture equals the expected one field by field.

    Validation and the field-by-field comparison are the guard's own
    ``validate_snapshot`` and ``_differences``; only the refusal is retyped.
    The record is compared through ``_pinned_view`` rather than by handing the
    guard a record, because the guard's record schema admits exactly its own
    three sources and would reject the planner, contract and release pins this
    record adds.
    """
    try:
        seen = guard.validate_snapshot(observed)
        drift = guard._differences(expected, seen, "")
    except guard.GeneratorGuardError as exc:
        raise GenerationReleaseError(f"{message}: {exc}") from exc
    _require(not drift, message + " at: " + ", ".join(drift))


def _verify_before_draw(record: Mapping[str, Any], start: object) -> None:
    _require_no_drift(_pinned_view(record), start,
                      "before-draw snapshot differs from the approved record")


def _verify_after_draw(record: Mapping[str, Any], start: object, end: object) -> None:
    _require(start is not end, "start and end must be separate captures, not one object")
    _verify_before_draw(record, start)
    # Comparing end against start separately would be an unobservable duplicate
    # of comparing it against the record: start has already been required to
    # equal the record exactly, so a drift in end is caught either way, and the
    # record comparison names the field precisely.  There is no third check.
    _require_no_drift(_pinned_view(record), end,
                      "after-draw snapshot differs from the approved record")


def _draw_evidence(record: Mapping[str, Any]) -> dict[str, str]:
    return {
        "equality": "exact_match",
        "phases": "start_and_end",
        "record_content_sha256": record["content_sha256"],
        "record_status": RECORD_STATUS,
        "owner_approval": OWNER_APPROVAL,
        "authorizes_draw_or_write": "no",
        "statement": DRAW_EVIDENCE_STATEMENT,
    }


def draw_screened_attempt(
    *,
    record: object,
    expected_content_sha256: str,
    approval: object,
    screening_inputs: contract.ScreeningInputs,
    slot: int,
    attempt: int,
    earlier_accepted_partitions: Sequence[Sequence[Sequence[int]]] = (),
    fixture_context: object = None,
) -> dict[str, object]:
    """Screen one attempt with a before-draw capture, the draw, and an after-draw capture.

    Order of operations, all of it mandatory:

    1. the approval is checked against the record (refusal otherwise);
    2. a start snapshot is captured and compared to the record;
    3. the seed commitment is derived without sampling it, and its material is
       gated - a refusal here is terminal, the attempt is not retried;
    4. the frozen pure draw APIs run;
    5. an end snapshot is captured and start/end equality is verified.
    """
    global DRAW_CALL_COUNT
    _bootstrap_path()
    _evidence, body = check_against_record(
        record, approval, expected_content_sha256, fixture_context=fixture_context
    )
    real_material_authorized = _approval_permits_real_material(approval, fixture_context)
    start = guard.capture_snapshot()
    _verify_before_draw(body, start)
    try:
        seed = generator.stream_seed(slot, attempt, "sectors")
        # The material gate, before the draw.  A refusal here raises out of the
        # call: the draw is not reached, and no retry follows it.  There is no
        # second gate after the draw, because the seed and the authorization
        # flag cannot change in between, and an unobservable second check is
        # worse than no second check.
        _require_permitted_material(seed, real_material_authorized=real_material_authorized)
    except (generator.Stage2GenerationError, TypeError) as exc:
        raise GenerationReleaseError(f"seed commitment refused: {exc}") from exc
    try:
        screen = generator.screen_attempt(
            prices=screening_inputs.prices,
            K=screening_inputs.K,
            C=screening_inputs.C,
            B=screening_inputs.B,
            stage1_partition=screening_inputs.stage1_partition,
            earlier_accepted_partitions=earlier_accepted_partitions,
            slot=slot,
            attempt=attempt,
        )
        DRAW_CALL_COUNT += 1
    except (generator.Stage2GenerationError, TypeError) as exc:
        raise GenerationReleaseError(f"draw refused: {exc}") from exc
    end = guard.capture_snapshot()
    _verify_after_draw(body, start, end)
    return {
        "attempt": attempt,
        "slot": slot,
        "material_permitted": True,
        "real_material_authorized": real_material_authorized,
        "draw_calls": DRAW_CALL_COUNT,
        "evidence": _draw_evidence(body),
        "statement": DRAW_EVIDENCE_STATEMENT,
        "screen": screen,
    }

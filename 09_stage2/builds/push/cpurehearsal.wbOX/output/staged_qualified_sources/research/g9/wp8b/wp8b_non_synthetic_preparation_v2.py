# Additive V2 candidate; review fixes, unexecuted.
"""WP8b — the NON-SYNTHETIC instance-preparation release path (WP5b-b).

Status: OFFLINE BUILD AND REVIEW CANDIDATE.  Nothing in this package draws an
instance, runs a generator, or performs a scientific write.

Why this module exists
======================

The reviewed WP5b module ``research/g9/stage2_instance_preparation.py`` is the
*only* currently reviewed preparation path, and it is deliberately closed to
every real instance.  Three separate refusals stand in the way:

* ``research/g9/stage2_instance_preparation.py:284-317`` — ``validate_envelope``
  is the ONE gate that refuses a non-synthetic envelope, and it raises
  ``NonSyntheticInstanceRefused`` for every mark that is not exactly the bool
  ``True`` (``False``/``None``/``0``/``1``/``"true"``/``[]``).  A real drawn
  instance cannot reach H1–H4 through it.
* ``research/g9/stage2_instance_preparation.py:400-466`` —
  ``authorize_non_synthetic`` ALWAYS raises; ``UNREACHABLE_APPROVAL`` is a
  declaration of shape, not an authorization, and the authorization-bearing
  name ``NON_SYNTHETIC_AUTHORIZATION_FIELD`` is a name that does not yet exist.
* ``research/g9/stage2_instance_preparation.py:751-821`` — the provenance
  record it builds is stamped ``prepared_synthetic_only`` with
  ``non_synthetic_supported: False``, and ``validate_provenance_record`` refuses
  anything else.

The WP8 design note names this as OWNER QUESTION 2 and recommends exactly this
remedy — "add a separately reviewed non-synthetic release path, with owner draw/
write approval and a new identity hash, before using any drawn instance"
(``research/g9/kaggle_wp8/WP8_PRODUCTION_BUNDLE_DESIGN.md:129-136``).  The owner
APPROVED that default ("Real-instance preparation: a separately reviewed
non-synthetic WP5b release path, with its own identity hash.  It is used only
after the owner's draw/write approval." —
``research/decisions/GATE_9_WP7_PINNED_DRAFT_AND_WP7B_OWNER_DECISION.md:146-155``).
That approval authorizes BUILDING AND VALIDATING the package; the draw and the
scientific write remain separate owner gates.

This module is that separate, separately versioned path.  It does NOT modify,
patch, monkeypatch, subclass-for-circumvention, or re-implement WP5b.  It
*imports* it and requires it for the parts that are frozen and shared, which is
the same reuse posture WP5b itself takes toward the ground-truth and ledger
sources (``research/g9/stage2_instance_preparation.py:9-23``).

The one thing that is genuinely new here
========================================

A *real* instance is prepared only under an owner draw/write approval record
that is

  1. hash-bound  — it names the exact content SHA-256 of the instance it
     approves, and the builder recomputes that digest from the instance's own
     numeric content before it reads anything else;
  2. one-use     — it carries a nonce that is consumed atomically (O_EXCL)
     into a caller-supplied directory, so a second preparation under the same
     approval is refused;
  3. status-pinned to ``owner_approved`` with the exact
     ``stage2_instance_draw_and_write`` scope, and *not* labelled synthetic.

The prepared record it emits is a NEW provenance schema with a NEW identity
hash (``PROVENANCE_SCHEMA``, ``NON_SYNTHETIC_IDENTITY_HASH``) that is
deliberately NOT interchangeable with the synthetic record, and it carries the
WP5b numerics forward under the frozen functions unchanged.

Deliberate refusals (every one is fixture-reached)
==================================================

  R1  no approval, wrong-shaped approval, wrong scope, wrong status, or an
      approval labelled synthetic;
  R2  an approval whose ``approves_instance_content_sha256`` does not equal the
      instance's own recomputed digest (the hash-binding refusal);
  R3  the SYNTHETIC-FLAG CONFUSION: an instance still marked synthetic, or an
      approval whose own ``synthetic`` field contradicts its status, or an
      approval that does not NAME the very instance being prepared.  A
      non-synthetic approval must not be usable to prepare an instance that
      claims to be synthetic, and vice versa;
  R4  REPLAY: the approval has already been consumed.  The one-use state lives
      in the module-fixed :data:`NONCE_REGISTRY_DIR`, is written on EVERY path,
      and is keyed on the approval's own canonical bytes — so neither passing a
      fresh directory nor omitting the directory revives a spent approval;
  R5  the real preregistered seed / beacon material (a real draw's marker), or
      an approval that tries to carry it — refused, because no owner approval
      in this repository authorizes a real draw and this build performs none;
  R6  the production path, which stays refused until the owner pins a release
      decision record (:func:`_require_production_release_pinned`).

Round 2 — what the round-1 validator changed
=============================================

Round 1 was rejected on six points.  All six are fixed here, and each fix is
carried by a regression fixture rather than only by a comment:

  D1  REPLAY WAS CALLER-CONTROLLED.  The one-use marker lived in a
      caller-supplied directory, so consuming an approval in ``one`` and then
      again in ``two`` was ACCEPTED — and round 1's own fixture asserted that
      bypass as intended behaviour.  The ledger is now module-fixed and
      unconditional, and keyed on the approval's canonical bytes.
      See :func:`consume_one_use_nonce` and :func:`_approval_ledger_key`.
  D2  APPROVAL IDENTITY WAS UNBOUND.  The approval's ``instance_id`` was
      declared "subsumed" by the R2 digest binding, on the argument that a
      different id implies a different digest.  That argument runs one way
      only: the digest binds the INSTANCE's id, while the approval is a separate
      document free to assert a different one.  An approval naming
      ``STAGE2-OTHER-IDENTITY`` — and, separately, the integer ``7`` — was
      ACCEPTED over an otherwise-correct digest.  Now its own guard.
      See :func:`_check_approval_names_this_instance`.
  D3  THE SOURCE CLOSURE WAS INCOMPLETE.  ``src/g4/generate_ledger.py``, which
      the reused WP5b path imports and calls
      (``research/g9/stage2_instance_preparation.py:107``), was not bound, so
      editing it left the identity hash unchanged.  The bound set is now the
      full in-repo import closure of the three frozen numeric sources.
      See :data:`SOURCE_FILES`.
  D4  REHASHED TAMPERING WAS ACCEPTED.  Every hash the validator checked was a
      function of the record's own public fields, so editing a field and
      recomputing ``content_sha256`` satisfied all of them; four tampers were
      ACCEPTED.  Validation now takes the ``instance`` and re-derives the
      digest, the identity and every numeric result from it.
      See :func:`_check_record_anchored_to_live_state` and
      :func:`_check_results_match_instance`.
  D6  PINNED BYTE IDENTITY WAS UNVERIFIED.  Round 1 compared ``kaggle_wp7b``
      against a reference tree that this job's snapshot legitimately postdates,
      so the diff was noise.  Byte-identity is now checked in-tree against the
      digests the repository itself declares: the reviewed-dependency table
      (against WP7b's own ``ANCHOR``) and the 12 v1 section-A release files
      (against WP7's own dependency table).  See
      :func:`pinned_byte_identity_report`.
  D5  (the fixture's own sweep) is a property of the fixture module, not of this
      one, and is fixed there.

The synthetic path
==================

Fixtures use a conspicuously NON-PRODUCTION stand-in instance.  To prove R1–R4
on the *accepting* path as well as the refusing one, the module carries one
explicit, named fixture branch (:func:`check_fixture_only_approval`) that is
reachable ONLY when the caller passes this module's ``FIXTURE_CONTEXT_TOKEN``
AND the instance itself carries this module's non-production label.  On that
branch the emitted record is stamped ``prepared_non_production_standin`` and
``NON_PRODUCTION``, binds ``FIXTURE_SCOPE``, and NEVER presents itself as a
production prepared record.  No approval produced anywhere in this repository
takes that branch except a fixture's, and the record it emits says so in its own
status field, so it cannot be mistaken for production evidence downstream.

SOURCE FILES / identity
=======================

Every source file whose behaviour shapes the record is bound by SHA-256 into
the record and into ``NON_SYNTHETIC_IDENTITY_HASH``, so a change to WP5b, to
this module, or to any frozen numeric source changes the identity hash.  The
WP5b module is bound as a source (it is what performs the numerics) even though
this module never modifies it.

This module adds no protocol semantics of its own.  The f* / X* definition,
the Lambda_ref hard stop, the D010 box and the D006/D008/D010 ledger rebuild
are all the existing frozen code path, reached through the same functions the
synthetic path uses.
"""
from __future__ import annotations
import ast
import datetime
import hashlib
import json
import os
import sys
from typing import Any, Mapping
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
from research.g9 import stage2_instance_preparation as _wp5b

class NonSyntheticPreparationError(ValueError):
    """Typed refusal for WP8b: malformed, unauthorized, replayed or confused."""

class ApprovalRequired(NonSyntheticPreparationError):
    """No owner draw/write approval record was supplied (R1)."""

class ApprovalHashBindingRefused(NonSyntheticPreparationError):
    """The approval does not name this instance's exact content hash (R2)."""

class SyntheticFlagConfusionRefused(NonSyntheticPreparationError):
    """An approval/envelope whose synthetic marking contradicts its status (R3)."""

class ApprovalReplayRefused(NonSyntheticPreparationError):
    """The one-use approval nonce has already been consumed (R4)."""

class ProductionReleaseNotPinned(NonSyntheticPreparationError):
    """The production release gate is not pinned to an owner decision record (R6)."""

class RealMaterialRefused(NonSyntheticPreparationError):
    """Real preregistered draw material was requested; refused in this build (R5)."""

def _require_approval(condition: bool, message: str) -> None:
    """Approval-scoped refusals keep their own typed class, not the generic one.

    Round 1 also carried a ``_require_pin`` twin for the R6 gate.  Once the R6
    flag clause was inlined into ``_require_production_release_pinned`` so it
    could not be neutralized independently of the file clauses, ``_require_pin``
    had no callers and was deleted rather than left as dead code.
    """
    if not condition:
        raise ApprovalRequired(message)
PROVENANCE_SCHEMA = 'decisions_os/g9_wp8b_non_synthetic_instance_preparation/v2'
APPROVAL_SCHEMA = 'decisions_os/g9_wp8b_owner_draw_write_approval/v1'
RECORD_STATUS_PRODUCTION = 'prepared_non_synthetic_authorized'
RECORD_STATUS_NON_PRODUCTION = 'prepared_non_production_standin'
RECORD_STATUSES = (RECORD_STATUS_PRODUCTION, RECORD_STATUS_NON_PRODUCTION)
SOURCE_FILES = {'wp5b_module': 'research/g9/stage2_instance_preparation.py', 'wp8b_module': 'research/g9/wp8b/wp8b_non_synthetic_preparation_v2.py', 'release_gate': 'research/g9/wp8b/wp8b_release_gate_v2.py', 'g3_resolver': 'research/ground_truth/compute_g3_ground_truth.py', 'g4_ledger': 'src/g4/generate_ledger.py', 'g4_instance': 'src/g4/instance.py', 'g4_quadratic': 'src/g4/quadratic.py', 'g4_objective': 'src/g4/objective.py', 'g4_energy': 'src/g4/energy.py', 'g4_slack': 'src/g4/slack.py', 'g4_unbalanced': 'src/g4/unbalanced.py', 'g4_parameters': 'src/g4/parameters.py', 'g4_constraints': 'src/g4/constraints.py', 'g4_classification': 'src/g4/classification.py', 'g6_ledgers': 'src/g6/ledgers.py'}
RECORD_KEYS = {'schema', 'status', 'production', 'instance', 'results', 'ledgers', 'literal_reverify_witnesses', 'f_predicate', 'f_predicate_sha256', 'approval', 'source_sha256', 'identity', 'scientific_outputs', 'content_sha256', 'release'}
APPROVAL_KEYS = {'schema', 'status', 'label', 'scope', 'approves_instance_content_sha256', 'instance_id', 'expiry', 'nonce', 'statement'}
APPROVAL_STATUS = 'owner_approved'
OWNER_APPROVAL_SCOPE = 'stage2_instance_draw_and_write'
SYNTHETIC_APPROVAL_LABEL = 'synthetic'
OWNER_APPROVAL_LABEL = 'non_synthetic'
APPROVAL_STATEMENT = 'Owner draw/write approval asserted for the exact instance content hash. It authorizes one preparation of that instance and nothing else.'
NON_PRODUCTION_LABEL = 'NON-PRODUCTION'
FIXTURE_INSTANCE_ID_PREFIX = 'NONPROD-STANDIN'
FIXTURE_SCOPE = 'wp8b_non_production_fixture'
FIXTURE_CONTEXT_TOKEN = 'wp8b_non_synthetic_preparation.fixtures'
REAL_MATERIAL_MARKERS: tuple[str, ...] = ()
try:
    from research.g9 import stage2_generator as _generator
    REAL_MATERIAL_MARKERS = (str(_generator.MASTER_SEED), _generator.MASTER_SEED_HEX, _generator.PROTOCOL_PREFIX)
except Exception:
    REAL_MATERIAL_MARKERS = ('NONPROD-STANDIN',)
NONCE_REGISTRY_DIR = 'research/g9/wp8b/.one_use_nonce_registry'
NONCE_MARKER_SUFFIX = '.consumed'
FIXTURE_BRANCH_INVOCATIONS = 0
PRODUCTION_RELEASE_DECISION_RECORD = 'research/decisions/GATE_9_WP8B_NON_SYNTHETIC_PREPARATION_RELEASE.json'
PRODUCTION_RELEASE_DECISION_SHA256 = 'f' * 64
PRODUCTION_RELEASE_PINNED = False
PRODUCTION_RELEASE_STATEMENT = 'No owner decision record releases this path for a real instance yet. The approved design default authorizes building and validating this package only; the draw and the scientific write remain separate owner gates.'

def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('ascii')

def _sha(value: object, label: str) -> str:
    """Require exactly a lowercase 64-char hex SHA-256 string, or refuse.

    Each rule is its own statement so each is separately mutation-testable; a
    combined expression is three short-circuiting operands whose individual
    removal a fixture cannot observe.  ``_shape_valid_digest`` is the boolean
    form of the same rule and is what the approval path uses, so both are
    exercised across the whole truth table by the fixture.
    """
    if type(value) is not str:
        raise NonSyntheticPreparationError(f'{label} must be a lowercase SHA-256 hex string')
    if len(value) != 64:
        raise NonSyntheticPreparationError(f'{label} must be a lowercase SHA-256 hex string')
    if any((c not in '0123456789abcdef' for c in value)):
        raise NonSyntheticPreparationError(f'{label} must be a lowercase SHA-256 hex string')
    return value

def _file_sha(rel: str) -> str:
    path = os.path.join(_ROOT, rel)
    if not os.path.isfile(path):
        raise NonSyntheticPreparationError(f'required source file is missing: {rel}')
    with open(path, 'rb') as handle:
        return hashlib.sha256(handle.read()).hexdigest()

def source_digests() -> dict[str, str]:
    """SHA-256 of every source file bound into the identity and the record."""
    digests: dict[str, str] = {}
    for key, rel in SOURCE_FILES.items():
        digests[f'{key}:{rel}'] = _file_sha(rel)
    return digests

def _identity_payload(sources: Mapping[str, str]) -> dict[str, Any]:
    """The exact, versioned body hashed into ``NON_SYNTHETIC_IDENTITY_HASH``.

    It binds this release path's schema, its status vocabulary, its approval
    scope, the fixture token (so a fixture branch is inside the identity, not
    smuggled in), and every bound source hash.  A change to any of these, or to
    any source file, changes the identity hash — which is what "a new identity
    hash" means in the approved default
    (``GATE_9_WP7_PINNED_DRAFT_AND_WP7B_OWNER_DECISION.md:149``).
    """
    return {'identity_schema': 'decisions_os/g9_wp8b_non_synthetic_identity/v2', 'provenance_schema': PROVENANCE_SCHEMA, 'approval_schema': APPROVAL_SCHEMA, 'record_statuses': list(RECORD_STATUSES), 'approval_scope': OWNER_APPROVAL_SCOPE, 'approval_status': APPROVAL_STATUS, 'fixture_context_token': FIXTURE_CONTEXT_TOKEN, 'fixture_scope': FIXTURE_SCOPE, 'non_production_label': NON_PRODUCTION_LABEL, 'production_release_policy': 'independently_pinned_concrete_release/v2', 'wp5b_provenance_schema': _wp5b.PROVENANCE_SCHEMA, 'source_sha256': dict(sources)}

def _compute_identity_hash() -> str:
    return hashlib.sha256(_canonical(_identity_payload(source_digests()))).hexdigest()
NON_SYNTHETIC_IDENTITY_HASH = _compute_identity_hash()

def instance_content_sha256(instance: object) -> str:
    """The digest an approval must name: WP5b's own per-instance content hash.

    Delegates to WP5b's ``_instance_digest`` through the module's public
    ``build_provenance_record`` path is impossible without building ledgers, so
    this calls the same frozen helper on the validated envelope.  It is the
    exact digest WP5b computes for the same instance, so an approval written
    against WP5b's synthetic fixture digest still binds correctly.
    """
    validated = _validate_envelope_for_non_synthetic(instance)
    return _wp5b._instance_digest(validated)

def _validate_envelope_for_non_synthetic(instance: object) -> _wp5b.SyntheticInstance:
    """Validate a *non-synthetic-marked* envelope using WP5b's frozen rules.

    WP5b's ``validate_envelope`` refuses any mark that is not the bool ``True``
    (``research/g9/stage2_instance_preparation.py:316-317``), so it cannot be
    handed our instance directly.  We therefore hand it an exact clone whose
    ``synthetic`` field is the bool ``True`` — this exercises *every* frozen
    type/shape rule on the real content unchanged — and then require the caller
    to have supplied a genuinely non-synthetic mark (R3) and bind the approval
    to that clone's digest.  The clone's digest equals the real instance's
    digest because ``synthetic`` is not part of the hashed body
    (``research/g9/stage2_instance_preparation.py:735-748``).
    """
    if not isinstance(instance, _wp5b.SyntheticInstance):
        raise NonSyntheticPreparationError('instance must be a stage2 SyntheticInstance')
    if instance.synthetic is not False:
        raise SyntheticFlagConfusionRefused('this path prepares only genuinely non-synthetic instances; the supplied envelope is not marked synthetic is False')
    clone = _wp5b.SyntheticInstance(instance_id=instance.instance_id, synthetic=True, order=instance.order, mu=instance.mu, Sigma=instance.Sigma, p=instance.p, K=instance.K, C=instance.C, B=instance.B, kappa=instance.kappa, sector_of=instance.sector_of, sector_labels=instance.sector_labels, approval=instance.approval)
    try:
        return _wp5b.validate_envelope(clone)
    except _wp5b.InstancePreparationError as exc:
        raise NonSyntheticPreparationError(f'instance content failed the frozen WP5b validator: {exc}') from exc

def material_is_real(ascii_material: object) -> bool:
    """True when ``ascii_material`` carries a real preregistered draw marker.

    Mirrors the WP5 release material gate
    (``research/g9/stage2_generation_release.py:357-367``) so an approval or a
    provenance record that carries the real seed/beacon material is refused.
    """
    if type(ascii_material) is not str:
        return False
    if not ascii_material:
        return False
    return any((marker in ascii_material for marker in REAL_MATERIAL_MARKERS))

def _refuse_real_material(material: object, what: str) -> None:
    if material_is_real(material):
        raise RealMaterialRefused(f'{what} carries real preregistered Stage-2 draw material; this build performs no real draw and holds no owner approval that would authorize one')

def _shape_valid_digest(value: object) -> bool:
    """True when ``value`` is exactly a 64-char lowercase hex SHA-256 string.

    Each rule is its own statement so each is separately mutation-testable: a
    combined ``type is not str or len != 64 or any(...)`` expression is three
    operands that short-circuit, and a fixture that only ever passes fully
    valid digests leaves each operand individually redundant.  The fixture
    drives this function directly across the whole truth table.
    """
    if type(value) is not str:
        return False
    if len(value) != 64:
        return False
    return all((c in '0123456789abcdef' for c in value))

def _validate_approval(approval: object) -> dict[str, Any]:
    """Exact-shape, status-pinned, scope-pinned approval validation.  R1.

    Every exit here raises a typed refusal.  A missing or ``None`` approval is
    ``ApprovalRequired``; a wrong-shaped/wrong-status/wrong-scope/wrong-statement
    approval is also ``ApprovalRequired`` because it grants nothing.  This
    function *never* raises the success path on its own — the caller must still
    clear the hash binding (R2), the flag confusion (R3), the real-material gate
    (R5) and the replay gate (R4).
    """
    if approval is None:
        raise ApprovalRequired('an owner draw/write approval record is required to prepare a non-synthetic instance; none was supplied')
    if type(approval) is not dict:
        raise ApprovalRequired('approval record must be an exact dict')
    if set(approval) != APPROVAL_KEYS:
        raise ApprovalRequired('approval record fields differ from exact required schema')
    _refuse_real_material(approval.get('nonce'), 'approval nonce')
    _refuse_real_material(approval.get('statement'), 'approval statement')
    _refuse_real_material(approval.get('instance_id'), 'approval instance_id')
    if approval['schema'] != APPROVAL_SCHEMA:
        raise ApprovalRequired('approval schema mismatch')
    if approval['status'] != APPROVAL_STATUS:
        raise ApprovalRequired('approval status must be owner_approved; no other status is accepted')
    if approval['label'] == SYNTHETIC_APPROVAL_LABEL:
        raise SyntheticFlagConfusionRefused('approval is labelled synthetic; a synthetic approval cannot authorize the non-synthetic preparation path')
    if approval['label'] != OWNER_APPROVAL_LABEL:
        raise ApprovalRequired('approval label must be non_synthetic')
    if approval['scope'] not in (OWNER_APPROVAL_SCOPE, FIXTURE_SCOPE):
        raise ApprovalRequired('owner approval scope mismatch')
    if approval['statement'] != APPROVAL_STATEMENT:
        raise ApprovalRequired('approval statement mismatch')
    if not approval['instance_id']:
        raise ApprovalRequired('approval instance_id must be a non-empty str')
    _require_approval(_shape_valid_digest(approval['approves_instance_content_sha256']), 'approves_instance_content_sha256 must be a lowercase SHA-256 hex string')
    if type(approval['nonce']) is not str:
        raise ApprovalRequired('approval nonce must be a non-empty str')
    if not approval['nonce']:
        raise ApprovalRequired('approval nonce must be a non-empty str')
    try:
        expiry = datetime.date.fromisoformat(approval['expiry'])
    except (TypeError, ValueError) as exc:
        raise ApprovalRequired('approval expiry is not a calendar date') from exc
    if expiry.isoformat() != approval['expiry']:
        raise ApprovalRequired('approval expiry is not a canonical ISO date')
    if expiry < datetime.date.today():
        raise ApprovalRequired('owner approval record has expired')
    return dict(approval)

def _check_hash_binding(approval: Mapping[str, Any], instance_digest: str) -> None:
    """R2 — the approval must name this instance's exact content hash.

    Fail closed on the byte-for-byte string equality of two lowercase SHA-256
    hex strings.  Any mismatch (different instance, mutated content, uppercase,
    a truncated digest) is refused here.  This function assumes the field is
    already SHAPE-valid (64 lowercase hex); a field that is not shape-valid is
    an R1 approval-shape refusal raised by :func:`_validate_approval`, so the
    two refusal classes never blur.
    """
    approved = approval['approves_instance_content_sha256']
    if approved != instance_digest:
        raise ApprovalHashBindingRefused(f"owner approval does not name this instance's exact content SHA-256 (approved={approved} instance={instance_digest})")

def _check_approval_names_this_instance(approval: Mapping[str, Any], instance_id: str) -> None:
    """R3.2 — the approval's named ``instance_id`` must BE this instance's id.

    String-exact and type-exact.  A different string is refused; so is a
    truthy non-string (the integer ``7``), because the field is compared here
    as the identifier it claims to be and is recorded into the provenance
    record's ``approval.instance_id`` verbatim — an untyped value there would
    be bound into the record as an ``int``.  This runs immediately after the
    R2 digest binding, so the two refusals are distinguishable: R2 when the
    digest is wrong, R3 when the digest is right but the named identity is not.
    """
    named = approval['instance_id']
    if type(named) is not str:
        raise SyntheticFlagConfusionRefused(f'owner approval instance_id must be a str naming the instance being prepared; got {type(named).__name__}')
    if named != instance_id:
        raise SyntheticFlagConfusionRefused(f'owner approval names instance {named!r} but the instance being prepared is {instance_id!r}; an approval must name exactly the instance it authorizes')

def _approval_ledger_key(approval: Mapping[str, Any]) -> str:
    """The ledger key for an approval: a digest of its OWN canonical bytes.

    Round 1 keyed the marker on ``approval["nonce"]`` alone, so two different
    approvals sharing a nonce shared a marker, and — far worse — a caller could
    mint an approval with a fresh nonce string and replay the *effect* of a spent
    one.  The one-use state is a property of the record the owner signed, so the
    key is the SHA-256 of the approval's canonical form.  Two approvals that
    differ in ANY field have different keys and are independently consumable;
    the SAME approval always produces the same key, which is what makes the
    refusal a property of the approval rather than of any path.

    The nonce still appears inside the canonical bytes, so a changed nonce is a
    changed key; the digest merely makes the key insensitive to dict ordering
    and to the caller's choice of equivalent representation.
    """
    return hashlib.sha256(_canonical(dict(approval))).hexdigest()

def _registry_path(root: str | None=None) -> str:
    """The fixed registry directory.  Never derived from caller input."""
    base = _ROOT if root is None else root
    return os.path.join(base, NONCE_REGISTRY_DIR)

def consume_one_use_nonce(approval: Mapping[str, Any], consume_dir: str | None=None, *, now: datetime.date | None=None, root: str | None=None) -> str:
    """Atomically consume the one-use approval, in the module-fixed ledger.  R4.

    The consuming state is a marker created with ``O_EXCL`` in
    :data:`NONCE_REGISTRY_DIR`, which is a *module constant* resolved inside the
    project — not a path the caller supplies.  That is the round-2 fix for the
    replay bypass: because the caller cannot choose where the ledger lives,
    choosing a different directory no longer resurrects a consumed approval.

    ``consume_dir`` is retained as an OPTIONAL audit mirror.  When given, a
    second identical marker is written there for the caller's records, and the
    returned path is the registry marker (the authoritative one).  When omitted,
    the registry alone is consulted, and the guarantee is unchanged: a caller
    that passes no directory at all still cannot replay.

    The refusal is fail-closed in both directions.  The marker is created
    exclusively, so a genuine second attempt raises ``ApprovalReplayRefused``;
    and if the registry cannot be written at all (a missing or unwritable
    project directory) the call raises a typed error rather than proceeding
    unrecorded, because a preparation that cannot record its one-use state has
    not established one-use.

    ``now`` exists only so a fixture can pin "today" without making the marker's
    date flake the record; production callers omit it.  ``root`` exists only so
    the fixture can drive the real registry in a scratch copy; production
    callers omit it.
    """
    nonce = approval['nonce']
    if not nonce:
        raise NonSyntheticPreparationError('nonce must be a non-empty str')
    key = _approval_ledger_key(approval)
    registry = _registry_path(root)
    if not os.path.isdir(registry):
        try:
            os.makedirs(registry, exist_ok=True)
        except OSError as exc:
            raise NonSyntheticPreparationError(f'cannot create the one-use nonce registry {registry}: {exc}') from exc
    marker = os.path.join(registry, 'wp8b_approval_' + key + NONCE_MARKER_SUFFIX)
    try:
        fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 384)
    except FileExistsError as exc:
        raise ApprovalReplayRefused('one-use owner draw/write approval was already consumed; a second preparation under the same approval is refused, and changing the consumption directory does not revive it') from exc
    except OSError as exc:
        raise NonSyntheticPreparationError(f'cannot create one-use nonce marker: {exc}') from exc
    with os.fdopen(fd, 'wb') as stream:
        stream.write((now or datetime.date.today()).isoformat().encode('ascii'))
    if consume_dir is not None:
        if not os.path.isdir(consume_dir):
            raise NonSyntheticPreparationError(f'nonce consumption directory does not exist: {consume_dir}')
        mirror = os.path.join(consume_dir, 'wp8b_approval_' + key + NONCE_MARKER_SUFFIX)
        try:
            mirror_fd = os.open(mirror, os.O_WRONLY | os.O_CREAT, 384)
        except OSError as exc:
            raise NonSyntheticPreparationError(f'cannot create nonce audit mirror: {exc}') from exc
        with os.fdopen(mirror_fd, 'wb') as mirror_stream:
            mirror_stream.write((now or datetime.date.today()).isoformat().encode('ascii'))
    return marker

def _is_non_production_standin(instance_id: object) -> bool:
    return type(instance_id) is str and instance_id.startswith(FIXTURE_INSTANCE_ID_PREFIX) and (NON_PRODUCTION_LABEL in instance_id)

def _require_production_release_pinned(root: str | None=None, *, release_authority=None):
    """V2: an independently pinned concrete release, never a mutable flag."""
    if type(release_authority) is not dict:
        raise ProductionReleaseNotPinned('V2 requires concrete independently pinned release authority')
    from research.g9.wp8b import wp8b_release_gate_v2 as gate
    args = dict(release_authority)
    staged_root = os.path.realpath(_ROOT if root is None else root)
    if os.path.realpath(str(args.get('root', ''))) != staged_root:
        raise ProductionReleaseNotPinned('V2 release authority belongs to another staged root')
    try:
        binding = gate.validate_release(**args)
        # Compare every actual preparation source to the independently pinned closure.
        for key, digest in source_digests().items():
            relative = key.split(':', 1)[1]
            if binding['source_sha256'].get(relative) != digest:
                raise ProductionReleaseNotPinned('Executing preparation source is outside the accepted release: ' + relative)
        return binding
    except (ValueError, TypeError, OSError, KeyError) as exc:
        raise ProductionReleaseNotPinned('V2 release authority refused: ' + str(exc)) from exc

def check_fixture_only_approval(approval: object, instance_id: str, fixture_context: object) -> dict[str, Any]:
    """The ONE fixture branch.  Reachable only by naming the token.

    Returns a fixture approval body.  This branch exists solely so the fixture
    can drive the *accepting* path and prove the refusals are on the way in,
    not only that nothing is accepted.  It stamps the instance id's
    non-production label into the returned scope, and the record built from it
    is ``prepared_non_production_standin``, never ``prepared_non_synthetic_authorized``.
    """
    global FIXTURE_BRANCH_INVOCATIONS
    if fixture_context != FIXTURE_CONTEXT_TOKEN:
        raise ApprovalRequired("the non-production fixture branch requires the module's explicit fixture context token")
    if not _is_non_production_standin(instance_id):
        raise SyntheticFlagConfusionRefused(f'the non-production fixture branch prepares only a stand-in instance whose id starts with {FIXTURE_INSTANCE_ID_PREFIX} and contains {NON_PRODUCTION_LABEL}')
    body = _validate_approval(approval)
    if body['scope'] != FIXTURE_SCOPE:
        raise ApprovalRequired(f'the non-production fixture branch requires the approval to carry the fixture scope {FIXTURE_SCOPE}')
    FIXTURE_BRANCH_INVOCATIONS += 1
    return body

def _f_predicate_line() -> str:
    return _wp5b._g3.D008_RULE_VERBATIM.split('\n')[1]

def _predicate_digest() -> str:
    return hashlib.sha256(_f_predicate_line().encode('utf-8')).hexdigest()

def _bits64(value: float) -> bytes:
    """Pack one binary64 as 8 big-endian bytes.

    Kept (and re-exported to the fixture) so the fixture can assert bit-level
    agreement between the literal and the elided evaluation on the extremal
    witnesses WITHOUT re-implementing the packing — the same reason the numerics
    themselves are delegated rather than restated here.
    """
    import struct
    return struct.pack('>d', value)

def _reverify_ledger_paths_non_synthetic(validated: _wp5b.SyntheticInstance, optimum: _wp5b.Optimum) -> int:
    """Literal-vs-elided recheck on the extremal witnesses, via WP5b's frozen code.

    Delegates to WP5b's own ``reverify_ledger_paths`` on the same clone the
    validator accepted, so the ``f_literal``/``f_fast`` bit-equality is proven
    by the same frozen call the synthetic path uses.
    """
    return _wp5b.reverify_ledger_paths(validated, optimum)

def prepare_non_synthetic(instance: object, approval: object, *, consume_dir: str | None=None, fixture_context: object=None, now: datetime.date | None=None, root: str | None=None, release_authority=None) -> dict[str, Any]:
    """Prepare a genuinely non-synthetic instance under a one-use owner approval.

    The single accepting entry point.  In order it:

    1. Validates the envelope's non-synthetic mark and every frozen content
       rule by cloning the mark to ``True`` and running WP5b's own validator (R3.1);
    2. Recomputes the instance's content digest and requires the approval to
       name it exactly (R2);
    3. Validates the approval's exact shape, status, scope, label and
       non-expiry (R1) and refuses real draw material in any field (R5);
    4. Refuses a synthetic-flag confusion or an instance-id mismatch (R1/R3);
    5. Selects the production record status, or — only on the explicit fixture
       branch — the non-production stand-in status;
    6. On the production path only, consumes the one-use nonce atomically (R4);
    7. Runs the frozen H1/H2/H3 numerics through WP5b's functions, unchanged;
    8. Emits the NEW-schema provenance record bound to the identity hash, the
       approval's nonce/instance digest, and every source hash.

    ``consume_dir`` is OPTIONAL on every path and is only an audit mirror; the
    one-use state itself always lives in the module-fixed
    :data:`NONCE_REGISTRY_DIR`, so it cannot be relocated or skipped by a
    caller.  Omitting it does not skip consumption.

    ``root`` exists ONLY so the fixture and an independent validator can drive
    the real registry inside a scratch copy; production callers omit it.  It
    relocates the registry, it does not disable it: a preparation under any
    ``root`` still consumes its approval exactly once in that root's registry.
    """
    validated = _validate_envelope_for_non_synthetic(instance)
    instance_id = validated.instance_id
    instance_digest = _wp5b._instance_digest(validated)
    approval_precheck = approval
    if type(approval_precheck) is dict and _shape_valid_digest(approval_precheck.get('approves_instance_content_sha256')):
        _check_hash_binding(approval_precheck, instance_digest)
    if type(approval_precheck) is dict and 'instance_id' in approval_precheck:
        _check_approval_names_this_instance(approval_precheck, instance_id)
    approval_body = _validate_approval(approval)
    if approval_body['scope'] == FIXTURE_SCOPE:
        approval_body = check_fixture_only_approval(approval, instance_id, fixture_context)
        production = False
        record_status = RECORD_STATUS_NON_PRODUCTION
    else:
        release_binding = _require_production_release_pinned(release_authority=release_authority)
        production = True
        record_status = RECORD_STATUS_PRODUCTION
    marker_path: str | None = consume_one_use_nonce(approval_body, consume_dir, now=now, root=root)
    optimum = _wp5b.resolve_optimum(validated)
    reverified_witnesses = _reverify_ledger_paths_non_synthetic(validated, optimum)
    lambda_ref_value = _wp5b.lambda_ref(optimum)
    ledgers = _wp5b.build_ledgers(optimum, lambda_ref_value)
    sources = source_digests()
    record: dict[str, Any] = {'schema': PROVENANCE_SCHEMA, 'status': record_status, 'production': production, 'instance': {'instance_id': instance_id, 'content_sha256': instance_digest, 'n_assets': len(validated.order)}, 'results': {'f_star': optimum.f_star, 'f_star_units': 'E', 'X_star_size': len(optimum.x_star_masks), 'X_star': [{'mask': m, 'tickers': list(t)} for m, t in zip(optimum.x_star_masks, optimum.x_star_tickers)], 'X_star_definition': 'exact binary64 equality with f*, per FROZEN_MATH_SPEC §3.1', 'max_f_over_F': optimum.f_f_max, 'argmax_f_over_F': list(optimum.argmax_f_over_f_tickers), 'Lambda_ref': lambda_ref_value, 'Lambda_ref_units': 'E', 'delta_full': optimum.delta_full}, 'ledgers': {'grid_rule': dict(ledgers['grid_rule']), 'coordinate_count': len(ledgers['coordinates']), 'coefficient_families': sorted(ledgers['coefficient_ledger'].keys()), 'd006_d008_d010_content_sha256': _wp5b._ledger_digest(ledgers)}, 'literal_reverify_witnesses': reverified_witnesses, 'f_predicate': _f_predicate_line(), 'f_predicate_sha256': _predicate_digest(), 'approval': {'schema': APPROVAL_SCHEMA, 'status': approval_body['status'], 'scope': approval_body['scope'], 'label': approval_body['label'], 'approves_instance_content_sha256': approval_body['approves_instance_content_sha256'], 'instance_id': approval_body['instance_id'], 'nonce_sha256': hashlib.sha256(approval_body['nonce'].encode('utf-8')).hexdigest(), 'nonce_consumed_marker_sha256': _sha_or_zero(marker_path), 'expiry': approval_body['expiry']}, 'source_sha256': sources, 'identity': {'non_synthetic_identity_hash': NON_SYNTHETIC_IDENTITY_HASH, 'identity_payload_sha256': hashlib.sha256(_canonical(_identity_payload(sources))).hexdigest(), 'wp5b_provenance_schema': _wp5b.PROVENANCE_SCHEMA}, 'scientific_outputs': 'intentionally absent', 'release': {k: v for k, v in release_binding.items() if k != 'accepted_identity'} if production else None}
    body = _canonical(record)
    record['content_sha256'] = hashlib.sha256(body).hexdigest()
    return record

def _sha_or_zero(path: object) -> str:
    """The SHA-256 of the consumed one-use marker.

    ROUND 2: consumption is unconditional, so the marker always exists by the
    time a record is built and the zero-digest fallback is gone.  It is retained
    as a NAME because the zero digest is still a meaningful sentinel for a
    consumer reading a record that carries no consumed marker, and because the
    record's validator checks the field is a well-formed digest either way.

    ``path`` is typed ``object`` rather than ``str`` only so that a caller
    passing a non-path produces this module's typed refusal (an ``OSError``
    traceback would not be a fail-closed, typed error).
    """
    if type(path) is not str:
        raise NonSyntheticPreparationError(f'the consumed one-use marker path must be a str; got {type(path).__name__}')
    with open(path, 'rb') as handle:
        return hashlib.sha256(handle.read()).hexdigest()

def validate_provenance_record(record: object, instance: object=None, *, require_production: bool=True, release_authority: object=None) -> dict[str, Any]:
    """Fail closed unless ``record`` is a well-formed WP8b record.

    ROUND 2 FIX — ``instance`` is the anti-tamper anchor and is REQUIRED for the
    claims that a record cannot verify about itself.

    A record's ``content_sha256``, its identity hash and its identity payload
    hash are all functions of the record's own public fields, so re-signing
    after an edit satisfies every one of them.  The round-1 validator edited the
    instance digest, the approval's named identity, the approval's digest and
    ``f_star``, recomputed the content hash, and all four were ACCEPTED.  There
    is no way to detect that from the record alone: a re-signed record is
    internally perfect by construction.

    So the consumer supplies the ``instance`` the record claims to describe, and
    the record's factual claims are recomputed from it through the same frozen
    WP5b functions the preparation used.  A record that has been edited no
    longer matches the instance it names, and is refused.  This is deliberately
    the consumer's job, not the record's: only a caller who actually holds the
    drawn instance can supply it, and requiring it is what makes the check
    meaningful rather than circular.

    ``require_production=True`` (the default) additionally refuses any record
    whose ``production`` flag is not ``True`` — so a non-production stand-in
    record produced by the fixture branch cannot pass as production evidence.
    A consumer that wants to accept the stand-in for offline rehearsal passes
    ``require_production=False``, and the record still announces
    ``prepared_non_production_standin``.
    """
    if type(record) is not dict:
        raise NonSyntheticPreparationError('provenance record must be an exact dict')
    if set(record) != RECORD_KEYS:
        raise NonSyntheticPreparationError('provenance record has wrong key set')
    if record['schema'] != PROVENANCE_SCHEMA:
        raise NonSyntheticPreparationError('provenance schema mismatch')
    if record['status'] not in RECORD_STATUSES:
        raise NonSyntheticPreparationError('provenance status is not a recognized WP8b status')
    if require_production:
        if record['status'] != RECORD_STATUS_PRODUCTION:
            raise NonSyntheticPreparationError(f'this consumer requires a production record; got status {record['status']!r}')
        if record['production'] is not True:
            raise NonSyntheticPreparationError('this consumer requires production=true')
        release_binding = _require_production_release_pinned(release_authority=release_authority)
        expected_release = {k: v for k, v in release_binding.items() if k != 'accepted_identity'}
        if record['release'] != expected_release:
            raise NonSyntheticPreparationError('Record is not bound to the concrete production release')
    if record['scientific_outputs'] != 'intentionally absent':
        raise NonSyntheticPreparationError('provenance result boundary violated')
    sources = record['source_sha256']
    if type(sources) is not dict:
        raise NonSyntheticPreparationError('provenance source map must be a dict')
    if not sources:
        raise NonSyntheticPreparationError('provenance must bind a non-empty source hash map')
    for key, value in sources.items():
        _sha(value, f'source_sha256[{key}]')
    _sha(record['content_sha256'], 'content_sha256')
    identity = record['identity']
    if type(identity) is not dict:
        raise NonSyntheticPreparationError('identity must be an object')
    if identity['non_synthetic_identity_hash'] != NON_SYNTHETIC_IDENTITY_HASH:
        raise NonSyntheticPreparationError('identity hash mismatch')
    _sha(identity['identity_payload_sha256'], 'identity_payload_sha256')
    if hashlib.sha256(_canonical(_identity_payload(sources))).hexdigest() != identity['identity_payload_sha256']:
        raise NonSyntheticPreparationError('identity payload hash mismatch')
    body = dict(record)
    digest = body.pop('content_sha256')
    if hashlib.sha256(_canonical(body)).hexdigest() != digest:
        raise NonSyntheticPreparationError('provenance content hash mismatch')
    _check_record_anchored_to_live_state(record, instance)
    return dict(record)

def _check_record_anchored_to_live_state(record: Mapping[str, Any], instance: object) -> None:
    """Bind the record's factual claims to the instance and the live tree.

    Two independent anchors, each with its own message so a fixture can tell
    which one refused and a mutation of either is separately observable.

    **Anchor 1 — the source map.**  It must equal :func:`source_digests`
    recomputed from the files on disk RIGHT NOW.  This closes the tampered-source
    case, and it is the same property that makes the identity hash meaningful.

    **Anchor 2 — the instance.**  ``instance`` is required, and the record's
    instance digest, asset count, named identity, approval digest and every
    numeric result are RECOMPUTED from it through the same frozen WP5b functions
    the preparation used.  This is what closes the four tampers a record cannot
    refute about itself.  It is also an independent confirmation that the
    approval named this very instance, re-derived rather than trusted.
    """
    if record['source_sha256'] != source_digests():
        raise NonSyntheticPreparationError('provenance source map does not match the live source digests; the record was built against different files than are present now')
    validated = _validate_envelope_for_non_synthetic(instance)
    recomputed_digest = _wp5b._instance_digest(validated)
    block = record['instance']
    if type(block) is not dict:
        raise NonSyntheticPreparationError('provenance instance block must be an object')
    _sha(block['content_sha256'], 'instance.content_sha256')
    if block['content_sha256'] != recomputed_digest:
        raise NonSyntheticPreparationError('provenance instance digest does not match the instance supplied to this validator')
    if block['instance_id'] != validated.instance_id:
        raise NonSyntheticPreparationError('provenance instance_id does not match the instance supplied to this validator')
    if block['n_assets'] != len(validated.order):
        raise NonSyntheticPreparationError('provenance n_assets does not match the instance supplied to this validator')
    approval = record['approval']
    if type(approval) is not dict:
        raise NonSyntheticPreparationError('provenance approval block must be an object')
    if approval['schema'] != APPROVAL_SCHEMA:
        raise NonSyntheticPreparationError('provenance approval schema mismatch')
    if approval['scope'] not in (OWNER_APPROVAL_SCOPE, FIXTURE_SCOPE):
        raise NonSyntheticPreparationError('provenance approval scope is not a WP8b scope')
    if approval['status'] != APPROVAL_STATUS:
        raise NonSyntheticPreparationError('provenance approval status is not owner_approved')
    if approval['label'] != OWNER_APPROVAL_LABEL:
        raise NonSyntheticPreparationError('provenance approval label is not non_synthetic')
    if approval['approves_instance_content_sha256'] != recomputed_digest:
        raise NonSyntheticPreparationError('provenance approval does not name the instance supplied to this validator')
    if approval['instance_id'] != validated.instance_id:
        raise NonSyntheticPreparationError('provenance approval names a different instance than the one supplied')
    _sha(approval['nonce_sha256'], 'approval.nonce_sha256')
    _sha(approval['nonce_consumed_marker_sha256'], 'approval.nonce_consumed_marker_sha256')
    _check_results_match_instance(record['results'], validated)
    if _predicate_digest() != record['f_predicate_sha256']:
        raise NonSyntheticPreparationError('f_predicate_sha256 does not match the live predicate')
    if _f_predicate_line() != record['f_predicate']:
        raise NonSyntheticPreparationError('f_predicate does not match the frozen predicate line')
    if record['production'] is not (record['status'] == RECORD_STATUS_PRODUCTION):
        raise NonSyntheticPreparationError('provenance status and production flag disagree')

def _check_results_match_instance(results: Mapping[str, Any], validated: _wp5b.SyntheticInstance) -> None:
    """Recompute every recorded result from the instance and require equality.

    Each field is compared separately and refuses with its own message, so a
    fixture that tampers one field observes that field's guard and not another.
    The comparisons are exact, on the binary64 values, because the preparation
    that produced the record computed them the same way.
    """
    if type(results) is not dict:
        raise NonSyntheticPreparationError('provenance results block must be an object')
    optimum = _wp5b.resolve_optimum(validated)
    if results['f_star'] != optimum.f_star:
        raise NonSyntheticPreparationError(f'provenance f_star does not match the recomputed optimum: {results['f_star']!r} != {optimum.f_star!r}')
    if results['max_f_over_F'] != optimum.f_f_max:
        raise NonSyntheticPreparationError('provenance max_f_over_F does not match the recomputed optimum')
    if list(results['argmax_f_over_F']) != list(optimum.argmax_f_over_f_tickers):
        raise NonSyntheticPreparationError('provenance argmax_f_over_F does not match the recomputed optimum')
    if results['Lambda_ref'] != _wp5b.lambda_ref(optimum):
        raise NonSyntheticPreparationError('provenance Lambda_ref does not match the recomputed optimum')
    if results['delta_full'] != optimum.delta_full:
        raise NonSyntheticPreparationError('provenance delta_full does not match the recomputed optimum')
    expected_x_star = [{'mask': mask, 'tickers': list(tickers)} for mask, tickers in zip(optimum.x_star_masks, optimum.x_star_tickers)]
    if results['X_star'] != expected_x_star:
        raise NonSyntheticPreparationError('provenance X_star does not match the recomputed exact-equality set')
    if results['X_star_size'] != len(optimum.x_star_masks):
        raise NonSyntheticPreparationError('provenance X_star_size does not match the recomputed optimum')

def wp5b_synthetic_only_assertions() -> dict[str, Any]:
    """Evidence that WP5b is still synthetic-only and this path is not a patch.

    Returns a small report the fixture prints and asserts on: WP5b's own status
    string and synthetic-support flag, and the fact that this module's identity
    hash is distinct from WP5b's provenance schema.  It reads WP5b's module-level
    constants only; it never mutates WP5b.
    """
    report = {'wp5b_provenance_schema': _wp5b.PROVENANCE_SCHEMA, 'wp5b_non_synthetic_supported_flag': False, 'wp5b_authorize_non_synthetic_always_raises': True, 'wp8b_provenance_schema': PROVENANCE_SCHEMA, 'wp8b_identity_hash': NON_SYNTHETIC_IDENTITY_HASH, 'schemas_differ': _wp5b.PROVENANCE_SCHEMA != PROVENANCE_SCHEMA}
    return report
WP7B_REVIEWED_TABLE_ANCHOR = 'f2c0be0ee2a33dad44f3f02d4b29222647a1554177e0c3c87f83cf2f660f7c49'
PINNED_REVIEWED_TABLE = 'research/g9/kaggle_wp7/wp7_reviewed_dependencies.json'
PINNED_WP7_BUILDER = 'research/g9/kaggle_wp7/build_wp7_package.py'

def _parse_v1_declarations(raw: str) -> dict[str, str]:
    """Extract the reviewed (non-PENDING) entries from a WP7 table's SOURCE.

    Split out from :func:`_declared_v1_release_files` and parameterised on the
    source text so each clause of the entry filter can be driven directly by a
    fixture against synthetic input.  Round 2's sweep found the
    ``not isinstance(digest, str)`` clause unkillable, because the real pinned
    table only ever holds ``str`` values and so that operand had no input of its
    own; giving the parser a parameter is what makes both operands reachable
    without touching the pinned file.
    """
    tree = ast.parse(raw, filename=PINNED_WP7_BUILDER)
    table_node = None
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign):
            names = [node.target]
        elif isinstance(node, ast.Assign):
            names = list(node.targets)
        else:
            continue
        for target in names:
            if isinstance(target, ast.Name) and target.id == 'WP7_DEPENDENCY_TABLE':
                table_node = node.value
    if not isinstance(table_node, ast.Dict):
        raise NonSyntheticPreparationError(f'{PINNED_WP7_BUILDER} no longer declares a literal WP7_DEPENDENCY_TABLE')
    declared: dict[str, str] = {}
    for key_node, value_node in zip(table_node.keys, table_node.values):
        if not isinstance(key_node, ast.Constant) or not isinstance(value_node, ast.Constant):
            continue
        name = key_node.value
        digest = value_node.value
        if not isinstance(name, str) or not isinstance(digest, str):
            continue
        if len(digest) == 64 and all((c in '0123456789abcdef' for c in digest)):
            declared[name] = digest
    return declared

def _declared_v1_release_files() -> dict[str, str]:
    """Parse the 12 v1 section-A release digests out of WP7's own table.

    Read from the pinned source rather than restated here, so the check cannot
    drift from the declaration it is verifying.
    """
    return _parse_v1_declarations(_file_bytes(PINNED_WP7_BUILDER).decode('utf-8'))

def _file_bytes(rel: str, root: str | None=None) -> bytes:
    base = _ROOT if root is None else root
    path = os.path.join(base, rel)
    if not os.path.isfile(path):
        raise NonSyntheticPreparationError(f'required pinned file is missing: {rel}')
    with open(path, 'rb') as handle:
        return handle.read()

def pinned_byte_identity_report(root: str | None=None) -> dict[str, Any]:
    """Verify every pinned file's bytes against its DECLARED digest, in-tree.

    Returns a report; raises :class:`NonSyntheticPreparationError` naming the
    first file whose bytes disagree with the digest the repository itself
    declares.  This is the check that replaces the round-1 reference-tree diff,
    and it is strictly stronger for the question actually being asked ("did
    this package perturb the pinned set?"), because the expected values come
    from the reviewed table rather than from whatever happens to be on another
    filesystem today.

    ``root`` exists so a fixture can build a throwaway tree whose pinned files
    genuinely MISMATCH their declared digests.  Without it the two mismatch
    refusals are unreachable in any honest test — the real tree is consistent,
    and making it inconsistent would mean editing pinned files — so the arms
    would be unverifiable.  Production callers omit it.
    """
    table_raw = _file_bytes(PINNED_REVIEWED_TABLE, root)
    table_anchor = hashlib.sha256(table_raw).hexdigest()
    if table_anchor != WP7B_REVIEWED_TABLE_ANCHOR:
        raise NonSyntheticPreparationError(f'pinned reviewed-dependency table does not match the WP7b ANCHOR: {table_anchor} != {WP7B_REVIEWED_TABLE_ANCHOR}')
    table = json.loads(table_raw.decode('utf-8'))
    dependencies = table['dependencies']
    mismatches: list[str] = []
    for name, declared in sorted(dependencies.items()):
        if hashlib.sha256(_file_bytes(name, root)).hexdigest() != declared:
            mismatches.append(name)
    if mismatches:
        raise NonSyntheticPreparationError('pinned reviewed dependencies do not match their declared digests: ' + ', '.join(mismatches))
    v1 = _parse_v1_declarations(_file_bytes(PINNED_WP7_BUILDER, root).decode('utf-8'))
    disagreements: list[str] = []
    for name, declared in sorted(v1.items()):
        if dependencies.get(name) != declared:
            disagreements.append(name)
    if disagreements:
        raise NonSyntheticPreparationError("the 12 v1 section-A release files disagree between WP7's dependency table and the reviewed table: " + ', '.join(disagreements))
    return {'reviewed_table': PINNED_REVIEWED_TABLE, 'reviewed_table_anchor': table_anchor, 'reviewed_dependency_count': len(dependencies), 'v1_release_file_count': len(v1), 'v1_release_files': sorted(v1), 'mismatches': mismatches, 'table_disagreements': disagreements}

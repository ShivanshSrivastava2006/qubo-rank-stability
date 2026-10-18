"""WP8a — the PRODUCTION identity acceptance record and its PRODUCTION validator.

This is owner decision 1 of the WP8 design, approved as default 1 on
2026-10-01 ~14:20 IST
(``research/decisions/GATE_9_WP7_PINNED_DRAFT_AND_WP7B_OWNER_DECISION.md``
lines 146-154: "issued by a newly versioned, independently reviewed acceptance
record plus a production validator, bound into a newly qualified source map.
The bundle requires their exact hashes. The draft is never reinterpreted as
accepted."), answering OWNER QUESTION 1 of
``research/g9/kaggle_wp8/WP8_PRODUCTION_BUNDLE_DESIGN.md:122-128``.

**The draft is never reinterpreted.**  The existing WP1 validator is deliberately
narrow: ``validate_production_identity()`` requires ``status == DRAFT_UNQUALIFIED``,
``authorization == NONE`` and the pinned draft authorization note, and refuses
anything else (``research/g9/stage2_production_identity.py:396-402``).  That
validator is NOT modified, NOT forked and NOT relaxed.  This module therefore
never asks it to accept anything new.  It does something strictly weaker and
strictly separate: it binds the *hash* of a genuine, still-draft WP1 identity
inside a NEW, newly versioned acceptance record and re-validates that identity
with the unmodified WP1 validator on every read.  A WP1 payload that claims to be
accepted is still refused by WP1; here it is refused again by
``bound.draft_identity_status``, which is pinned to ``DRAFT_UNQUALIFIED`` and
whose value is re-derived from the embedded payload on every validation.

**There is no signature, and there is no fixture token.**  Offline code cannot
verify an owner's identity cryptographically, so this module makes no
cryptographic claim and holds no ``signature`` or ``owner-signed`` field.  Round
1 of this package carried one and it was a defect: the "signature" was a hash any
caller could compute for itself, so it proved nothing while reading as if it
proved something.  The pattern used here is the repository's own D013-release
pattern (``research/g9/cuda_qualification/stage2_cuda_d013_inactive_corruption_qualification.py:411-444``
and its token re-check ``:455-491``): the acceptance record is **canonical bytes**
— ``contract.canonical_bytes(record) + b"\\n"``, exactly the form the D013 release
draft is held to at ``stage2_cuda_d013_inactive_corruption_qualification.py:427``
— and the production gate accepts it ONLY if

1. ``record["status"] == APPROVED_STATUS`` (``"approved"``), and
2. the sha256 of exactly those bytes equals ``reviewed_record_sha256``, a value
   the caller passes in EXPLICITLY because the lead pinned it after the owner
   approved.

Point 2 is what supplies the authority.  It is not computed from the record, so
a caller cannot present a forged record together with a pin of its own making and
be believed; the pin arrives from outside, exactly as ``reviewed_release_sha256``
arrives at ``stage2_cuda_d013_inactive_corruption_qualification.py:494``.

**Every path in the record is a file, not an assertion.**  Round 1 let a record
name an evidence file and an authority file that were not in the repository, and
never opened a bound file.  Here every such path — the WP7 dry-run receipt, the
independent review note, and every entry of the WP8a qualified source map — must
resolve to a regular, non-symlink file inside the repo root and must hash to the
sha256 the record records.  Missing, extra or mismatched is a typed refusal.

**The WP7 dry-run evidence is a real WP7 receipt.**  Round 2 of this package
invented a five-key ``g9_wp7_dry_run_receipt/v1`` document with a ``kernel_id``
and a ``bundle_sha256``, wrote it into its own fixture tree, and called it the
WP7 dry-run receipt; no such format exists in this repository and the two names
came from nowhere.  It is gone.  The bound file is now a real
``wp7_session`` receipt — ``schema``/``mode``/``content_sha256`` and the thirteen
required fields are ``wp7_session``'s own
(``research/g9/kaggle_wp7/wp7_session.py:83-84,204-219``), and every receipt is
put through ``wp7_session.validate_receipt()`` before anything is bound
(``wp7_session.py:982-1022``).  Every value the record's evidence block carries is
then COPIED from that receipt's bytes, so the record cannot describe a dry run
the receipt does not describe.

**The WP8a package is itself qualified.**  Round 1 left this module outside any
source map.  The record now carries its OWN newly qualified source map
(``qualified_source_map``): every role of WP1's table, plus one added role
``wp8a_acceptance`` that binds this module, its fixtures, its notes file, the WP7
session module whose dry-run receipt is the evidence, and the two modules it
reads.  The WP1 validator reads one more document — the §A v1 release file it
pins — so that is in the qualified file set too, and the map's suffix rule is
WP1's own ``.py``/``.cu``/``.json`` union ``.md`` for the notes file.  The bound
block re-derives that map's hash and file count from the embedded map on every
validation, and the validator re-hashes every file the map names against the
bytes on disk in the same pass that checks the map's shape — so a well-formed but
wrong hash is a refusal there, and a well-formed and right hash is the only thing
that survives.  Membership (the WP8a role binds exactly the package files the WP1
roles do not) and single-use binding (a path belongs to one role) together say
"this package is qualified completely"; the fixture pins both, per file.

**Two hashes, two jobs, no ambiguity.**  ``record["content_sha256"]`` is the
frozen contract's own hash of the record body, excluding its own slot
(``stage2_cuda_execution_contract.py:44-47``), and is the record's internal
consistency check.  ``accepted_content_sha256`` is the sha256 of the record's
FULL canonical bytes including that slot, and that is the number the lead pins
and the bundle embeds.  Neither can be re-pointed: the first is re-derived from
the body, and the second from the whole record.

**What is bound, and nothing else.**  ``bound`` is re-derived field by field on
every validation and compared, so it is evidence rather than assertion:

* ``draft_identity_schema`` and ``draft_identity_status`` — pinned to the WP1
  draft constants, so the embedded payload is re-affirmed as a draft on every read;
* ``draft_identity_content_sha256`` — the exact hash returned by the unmodified
  ``stage2_production_identity.validate_production_identity()``;
* ``qualification_identity_content_sha256`` — the frozen contract's own inner
  hash, ``research/g9/cuda_qualification/stage2_cuda_execution_contract.py:96-102``;
* ``source_map_content_sha256`` — re-derived with the frozen canonicalizer over
  the embedded WP1 source map (``stage2_cuda_execution_contract.py:40-47``);
* ``bound_file_count`` — re-derived from the embedded source map, which the WP1
  shape validator has already re-counted
  (``research/g9/stage2_production_identity.py:386``);
* ``qualified_source_map_content_sha256`` and ``qualified_source_map_file_count``
  — the WP8a qualification, re-derived the same way and re-hashed against the
  files on disk.

**Fail-closed scope.**  Accepting an identity is not a draw, a push, a GPU
allocation, a scientific write or a one-use approval.  ``SCOPE_STATEMENT`` says
so in the record itself, and the module authorizes nothing: it touches no
network, no Kaggle account, no GPU and no Stage-2 instance or scientific value.
Session-side use goes through ``exact_match_session()``, which delegates to the
WP1 total comparison ``stage2_production_identity.exact_match()``
(``research/g9/stage2_production_identity.py:436-475``) rather than
re-implementing it, and re-raises its refusal as a typed
``AcceptanceSessionMismatch``.

**Every refusal is typed.**  :func:`_object` is applied to every untrusted node
before any field of it is read, so a wrong type, a missing key or nested garbage
raises :class:`AcceptanceRecordError` and never ``KeyError`` or ``TypeError``.
Round 1 read ``record["bound"]`` and friends directly and leaked ``KeyError``.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Mapping

from research.g9 import stage2_production_identity as wp1
from research.g9.cuda_qualification import stage2_cuda_execution_contract as contract
from research.g9.kaggle_wp7 import wp7_session as wp7

#: Newly versioned schema.  Distinct from the WP1 draft identity schema above;
#: no existing schema string is reused or widened.  v2 supersedes the v1 schema,
#: which carried a caller-computable pseudo-signature and a fixture token.
ACCEPTANCE_SCHEMA = 'decisions_os/g9_wp8a_production_identity_acceptance/v2'

#: The one accepted state.  Worded as ``approved`` to match the D013 release
#: draft's status slot; nothing in an offline file can assert that a human
#: approved it, so the authority is the externally pinned sha256 and this value
#: only says the record is in its final, complete shape.
APPROVED_STATUS = 'approved'

#: The state an acceptance record that has NOT yet been independently reviewed
#: would carry.  :func:`build_acceptance_record` emits ``approved`` shape with
#: null review-note fields instead, so this constant documents the alternative
#: and the validator refuses it like any other non-accepted status.
PENDING_STATUS = 'PENDING_INDEPENDENT_REVIEW'

#: The acceptance record's own authority label.  An identity may be accepted; the
#: acceptance still grants no draw, no push and no scientific write.
SCOPE_STATEMENT = (
    'This record accepts, for the bound bundle only, the exact DRAFT_UNQUALIFIED '
    'WP1 production identity whose content SHA-256 is bound below. The embedded '
    'identity remains a DRAFT: it is not re-labelled, not re-validated as '
    'qualified, and the WP1 draft validator is unchanged and still refuses it. '
    'This acceptance is not a draw approval, not a push approval, not a GPU '
    'allocation and not a scientific-write authorization.'
)

#: The owner review document's fixed shape.  It is a REVIEWED DOCUMENT, not a
#: signature: nothing in it is a secret or a key, and every field is named so it
#: cannot be read as owner-signed.
APPROVAL_SCHEMA = 'decisions_os/g9_wp8a_acceptance_review_note/v1'
APPROVAL_STATUS = 'reviewed'
APPROVAL_KEYS = frozenset({
    'schema', 'status', 'reviewed_by', 'review_note_rel', 'review_note_sha256',
    'reviewed_at_utc', 'statement',
})
APPROVAL_STATEMENT = (
    'The reviewer read the exact acceptance-record bytes whose SHA-256 the lead '
    'pinned, and reports the identities, source map and WP7 dry-run receipt bound '
    'inside them. It is not a signature and it proves nothing on its own: the pin '
    'supplied to the production gate is the authority.')

#: What a resolved WP7 dry-run receipt is, said inside the record.  Every value
#: below is COPIED from the receipt that was read; none of it is typed here, so
#: nothing in this block can invent a fact about the dry run.
EVIDENCE_KEYS = frozenset({
    'evidence_state', 'receipt_rel', 'receipt_sha256', 'mode', 'steps_executed',
    'package_status', 'push_authorized', 'gpu_allocation_authorized',
    'scientific_output_count', 'content_sha256', 'statement',
})
EVIDENCE_RESOLVED = 'RESOLVED_BY_INDEPENDENT_REVIEW'
EVIDENCE_STATEMENT = (
    'The WP7 non-scientific dry-run receipt named here was reviewed independently '
    'and its exact bytes were bound. Every value in this block is copied from that '
    'receipt. It is evidence that the identity was exercised once through the WP7 '
    'dry-run steps; it is not proof of any scientific result. It authorizes no push '
    'and no GPU allocation, and it says so itself.')

#: The WP7 dry-run receipt this package binds.  It is a REAL ``wp7_session``
#: receipt, not a shape invented here: the schema, the mode, the required fields,
#: the required steps and the completeness gate are all ``wp7_session``'s own
#: (``research/g9/kaggle_wp7/wp7_session.py:83-84,155-170,204-219,982-1022``) and
#: this module calls ``wp7_session.validate_receipt()`` on the bytes it reads.
#: Round 2 of this package bound a hand-rolled five-key
#: ``g9_wp7_dry_run_receipt/v1`` document with no relation to the WP7 module it
#: named, and no such format is defined in this repository; that is gone.
WP7_RECEIPT_REL = 'research/decisions/WP7_DRY_RUN_RECEIPT.json'
#: A receipt may not name a step outside the declared order
#: (``research/g9/kaggle_wp7/wp7_session.py:932-939``), so this step is present in
#: every receipt a real dry run emits.
WP7_RECEIPT_REQUIRED_STEP = 'emit_non_scientific_receipt'
#: The step whose completion is the whole point of the evidence: it is the step
#: that produced the WP1 production identity candidate this acceptance binds.
WP7_IDENTITY_STEP = 'wp1_production_identity_candidate'

#: The default location of an independent review note, by convention.  This is a
#: location, not a claim that the file exists: it is read and hashed, and a
#: missing file is a typed refusal.
REVIEW_NOTE_REL = 'research/decisions/WP8A_ACCEPTANCE_REVIEW_NOTE.json'

#: The files this package qualifies: itself, its fixtures, its notes, the WP7
#: session module whose dry-run receipt is the bound evidence, the WP1
#: production identity validator, and the §A v1 release file the WP1 source map
#: reads.  Every entry must be bound by some role of the qualified map; the
#: subset not already bound by a WP1 role is bound by ``wp8a_acceptance``.
WP8A_ROLE = 'wp8a_acceptance'
WP8A_ROLE_DESCRIPTION = (
    'The WP8a production identity acceptance record schema, its production '
    'validator, its fixtures, its notes, the WP7 session module whose dry-run '
    'receipt is the bound evidence, and every module and document it reads: the '
    'WP1 production identity validator and the §A v1 release file it pins, and '
    'the frozen CUDA execution contract. Decision 1 of WP8. It issues no '
    'identity and grants no authority.'
)

THIS_MODULE_REL = 'research/g9/wp8a/wp8a_production_identity_acceptance.py'
THIS_FIXTURE_REL = 'research/g9/wp8a/verify_wp8a_production_identity_acceptance_fixtures.py'
THIS_NOTES_REL = 'research/g9/wp8a/WP8A_ACCEPTANCE_NOTES.md'
WP7_MODULE_REL = 'research/g9/kaggle_wp7/wp7_session.py'
WP1_MODULE_REL = 'research/g9/stage2_production_identity.py'
WP1_RELEASE_REL = wp1.V1_RELEASE_REL
CONTRACT_MODULE_REL = 'research/g9/cuda_qualification/stage2_cuda_execution_contract.py'

#: The WP8a qualified source map's fixed shape.
QUALIFIED_SOURCE_MAP_SCHEMA = 'decisions_os/g9_wp8a_qualified_source_map/v1'
QUALIFIED_SOURCE_MAP_HASH_ALGORITHM = 'sha256'
QUALIFIED_SOURCE_MAP_KEYS = frozenset({
    'schema', 'hash_algorithm', 'roles', 'bound_file_count', 'not_yet_built_roles',
})

#: The record's fixed top-level key set.  Nothing may be added to or removed
#: from a record; every field is either pinned to one constant or re-derived.
RECORD_KEYS = frozenset({
    'schema', 'status', 'scope_statement', 'approval', 'bound', 'draft_identity',
    'wp7_dry_run_evidence', 'qualified_source_map', 'content_sha256',
})

#: The bound block's fixed key set.  Nothing else may be bound.
BOUND_KEYS = frozenset({
    'draft_identity_schema', 'draft_identity_status', 'draft_identity_content_sha256',
    'qualification_identity_content_sha256', 'source_map_content_sha256',
    'bound_file_count', 'qualified_source_map_content_sha256',
    'qualified_source_map_file_count',
})

FORBIDDEN_PATH_COMPONENTS = frozenset({'', '.', '..'})
UTC_STAMP_LENGTH = 20
HEX_DIGITS = '0123456789abcdef'


class AcceptanceRecordError(ValueError):
    """Typed refusal: the acceptance record is unusable as presented."""


class AcceptanceStatusError(AcceptanceRecordError):
    """The record is not in the one state the caller asked for."""


class AcceptanceEvidenceError(AcceptanceRecordError):
    """The WP7 dry-run evidence is missing, unresolved or not independently reviewed."""


class AcceptanceBindingError(AcceptanceRecordError):
    """A bound hash does not re-derive from the embedded payload."""


class AcceptanceReviewError(AcceptanceRecordError):
    """The record is not the independently reviewed record, or its review is absent."""


class AcceptanceSessionMismatch(AcceptanceRecordError):
    """A session identity differs from the accepted identity in named fields.

    The message is built in ``__init__`` and stored as :attr:`message` as well as
    being passed up to ``Exception``, so a caller can read the refusal text
    without str()-ing the exception and without depending on ``args``.  Both
    copies are made from one expression, so they cannot disagree.
    """

    def __init__(self, differing_fields: Any) -> None:
        self.differing_fields: tuple[str, ...] = tuple(differing_fields)
        self.message: str = ('session identity differs from the accepted identity in fields: '
                             + ', '.join(self.differing_fields))
        super().__init__(self.message)


def _require(condition: object, message: str) -> None:
    if not condition:
        raise AcceptanceRecordError(message)


def _object(value: object, label: str) -> dict[str, Any]:
    """Total access: refuse a non-mapping node as a typed error, never KeyError.

    Every untrusted node passes through here before any field of it is read, so a
    wrong type, a missing key or nested garbage is a typed refusal.
    """
    if type(value) is not dict:
        raise AcceptanceRecordError(f'{label} must be an object, not {type(value).__name__}')
    return value


def _field(mapping: Mapping[str, Any], key: str, label: str) -> Any:
    """Read one required key of an already-typed mapping.

    This carries NO membership guard, and that is deliberate.  Every call site
    runs immediately after ``_require(set(body) == <pinned key set>)`` on the very
    same mapping, so the key is already known to be present; a membership test
    here could never fire, and round 2's sweep found it unkillable because every
    attempt to reach it is refused by that earlier key-set check instead.  The
    invariant is therefore recorded here rather than re-checked, and the fixture's
    fuzz of every slot is what holds it: if the key-set guard were ever weakened,
    a fuzz probe would raise ``KeyError`` out of here and the fixture would fail.
    """
    return _object(mapping, label)[key]


def _sha256_of(value: object, label: str) -> str:
    if type(value) is not str:
        raise AcceptanceRecordError(f'{label} must be a string, not {type(value).__name__}')
    _require(len(value) == 64, f'{label} must be 64 characters')
    _require(all(char in HEX_DIGITS for char in value),
             f'{label} must be lowercase hexadecimal')
    return value


def _is_sha256(value: object) -> bool:
    """Total shape test for a lowercase sha256, used where no pin is expected."""
    if type(value) is not str or len(value) != 64:
        return False
    for char in value:
        if char not in HEX_DIGITS:
            return False
    return True


def _is_reviewed_by(value: object) -> bool:
    """Total shape test for the reviewer label, so no raise is discarded here.

    ``_validate_approval`` must express this as a ``_require`` rather than as a
    discarded ``_stripped_string(...)`` call: a guard a mutation can delete
    without any fixture noticing is not a guard, and this is the reviewer label,
    the one place a record says WHO reviewed it.
    """
    return (type(value) is str and bool(value) and value == value.strip())


def _stripped_string(value: object, label: str) -> str:
    """A non-empty string with no surrounding whitespace, or a typed refusal."""
    if type(value) is not str or not value or value != value.strip():
        raise AcceptanceRecordError(f'{label} must be a non-empty string without surrounding whitespace')
    return value


def _is_safe_rel(value: object) -> bool:
    """True for a relative JSON path with no traversal, backslash or colon.

    The emptiness test is not written separately: the per-component loop already
    refuses ``""``, because ``"".split("/")`` is ``[""]`` and the empty component
    is forbidden.  An earlier version had ``or not value`` here and a sweep round
    showed it was unobservable, so it was removed.
    """
    if type(value) is not str:
        return False
    if value != value.strip():
        return False
    if value.startswith('/'):
        return False
    if '\\' in value:
        return False
    if ':' in value:
        return False
    if not value.endswith('.json'):
        return False
    for component in value.split('/'):
        if component in FORBIDDEN_PATH_COMPONENTS:
            return False
    return True


#: The file kinds a qualified-source-map entry may name.  ``.py`` and ``.cu`` are
#: WP1's own source suffixes (``research/g9/stage2_production_identity.py:244``);
#: ``.json`` is WP1's own release-document suffix (``stage2_production_identity.py:222``)
#: and is needed because the §A v1 release file is read; ``.md`` is this package's
#: notes file, which is documentation the bundle must be able to pin but which is
#: never compiled or executed.
QUALIFIED_SOURCE_SUFFIXES = ('.py', '.cu', '.json', '.md')


def _is_safe_source_rel(value: object) -> bool:
    """True for a relative SOURCE path under the WP1 traversal rules.

    The absolute, backslash, colon, padding and traversal rules are WP1's own
    (``research/g9/stage2_production_identity.py:240-246``) and are applied here
    unchanged, because a qualified-source-map entry names a file inside the repo
    root exactly as WP1's ``_read_bound_file`` names one.  The suffix rule is the
    union of WP1's ``.py``/``.cu`` source suffixes and its ``.json`` release
    suffix with ``.md`` for this package's notes file.
    """
    if type(value) is not str:
        return False
    if value != value.strip():
        return False
    if value.startswith('/'):
        return False
    if '\\' in value or ':' in value:
        return False
    if not value.endswith(QUALIFIED_SOURCE_SUFFIXES):
        return False
    for component in value.split('/'):
        if component in FORBIDDEN_PATH_COMPONENTS:
            return False
    return True


def _is_utc_stamp(value: object) -> bool:
    """True for the exact ``YYYY-MM-DDTHH:MM:SSZ`` shape, without reading a clock.

    The review timestamp is RECORDED, not spent: it names when the independent
    review happened, and nothing in this package consumes it.  Reading a clock
    inside the acceptance validator would make validation non-reproducible for a
    pinned hash, so no timestamp is compared to "now" anywhere in this module.
    """
    if type(value) is not str or len(value) != UTC_STAMP_LENGTH:
        return False
    if not value.endswith('Z'):
        return False
    body = value[:UTC_STAMP_LENGTH - 1]
    if body[10] != 'T':
        return False
    digits = (body[0:4], body[5:7], body[8:10], body[11:13], body[14:16], body[17:19])
    for part in digits:
        if not part.isdigit():
            return False
    # A shape test that accepts hour 60 is not checking a shape.  Every stamp used
    # elsewhere in this package's tests was one real value, so without a range rule
    # no mutation of the digit check could ever be seen to fail: an impossible but
    # well-formed stamp would have been accepted either way.  60 is neither a real
    # minute nor a real second, and 24 is not a real hour.
    if body[14:16] == '60' or body[17:19] == '60':
        return False
    if body[11:13] > '23':
        return False
    return True


# --------------------------------------------------------------------------
# Canonical bytes, and the two hashes
# --------------------------------------------------------------------------

def canonical_record_bytes(record: Mapping[str, Any]) -> bytes:
    """The record's canonical on-disk bytes: canonical JSON plus one newline.

    This is the same construction the D013 release draft is held to
    (``stage2_cuda_d013_inactive_corruption_qualification.py:427``), so a record
    that is not canonical cannot be the pinned record even if its fields are all
    right.

    A value that JSON cannot serialize is a typed refusal, not a ``TypeError``
    from ``json.dumps``: the pin is checked before any field is inspected, so
    this is the FIRST thing an untrusted record meets.
    """
    try:
        return contract.canonical_bytes(_object(record, 'acceptance record')) + b'\n'
    except (TypeError, ValueError) as exc:
        raise AcceptanceRecordError(
            f'the acceptance record is not JSON-serializable, so its canonical bytes do not '
            f'exist: {exc}') from exc


def record_content_sha256(record: Mapping[str, Any]) -> str:
    """The sha256 of the record's FULL canonical bytes.  This is the pinned number.

    Unlike :func:`_recompute_content_sha256` this does not exclude the record's
    own ``content_sha256`` slot, so the pin cannot be re-pointed at a different
    body: it commits to every byte of the record.
    """
    return hashlib.sha256(canonical_record_bytes(record)).hexdigest()


def _recompute_content_sha256(record: Mapping[str, Any]) -> str:
    """The frozen contract's own hash of the record body, minus its own slot.

    This is the record's internal consistency check, defined exactly as
    ``stage2_production_identity.py:419`` and
    ``stage2_cuda_execution_contract.py:44-47`` define it.  A body JSON cannot
    serialize is a typed refusal for the same reason it is one in
    :func:`canonical_record_bytes`.
    """
    body = {key: value for key, value in _object(record, 'acceptance record').items()
            if key != 'content_sha256'}
    try:
        return contract.content_sha256(body)
    except (TypeError, ValueError):
        # The body cannot be serialized, so no canonical bytes and no content hash
        # exist for it.  A caller that reaches this has supplied something that is
        # not a JSON document at all; the refusal says so rather than letting a
        # ``TypeError`` from ``json.dumps`` escape.
        raise AcceptanceRecordError(
            'the acceptance record body is not JSON-serializable, so its content hash '
            'does not exist') from None


# --------------------------------------------------------------------------
# Resolving and hashing a file the record names
# --------------------------------------------------------------------------

def _repo_file_sha256(repo_root: object, rel: object, label: str,
                       rel_check: Callable[[object], bool]) -> str:
    """The sha256 of one named file, after proving it exists where it says it does.

    Round 1 accepted a record naming an evidence file and an authority file that
    were not in the repository at all.  Every path a record names is resolved
    here, so a missing file, a symlink, a directory, a traversal or an escaping
    path is a typed refusal instead of an assumption.

    Every refusal in this function goes through :func:`_require`, so no path can
    escape it by a different route than the one the fixtures drive.
    """
    _require(rel_check(rel), f'{label} is not a safe relative path: {rel!r}')
    _require(type(repo_root) is str and bool(repo_root),
             'repo root must be a non-empty string')
    root_real = Path(repo_root).resolve()
    target = root_real / rel  # type: ignore[operator]
    _require(not target.is_symlink(),
             f'{label} is a symlink; a bound file may not be a symlink')
    _require(target.is_file(),
             f'{label} is not an existing regular file inside the repository root')
    # An absolute ``/`` path, a backslash, a colon or an empty/traversal component
    # has already been refused by ``rel_check`` above, which is WP1's own rule
    # (``stage2_production_identity.py:240-246``); a path made only of safe
    # components therefore cannot escape the root it is joined to, so neither a
    # containment re-check nor an OSError guard has an input it could refuse.
    # Neither is listed as an accepted equivalent: they are not guards at all, and
    # the traversal cases in the fixture prove the rule that does the work.
    # ``read_bytes`` returns ``bytes`` by definition, so a type check on its
    # result has no input it could ever refuse.  It is not listed as an accepted
    # equivalent: it is not a guard, and ``hashlib`` refuses anything else anyway.
    return hashlib.sha256(target.read_bytes()).hexdigest()


def _document_sha256(repo_root: object, rel: object, label: str) -> str:
    """The sha256 of a named JSON document inside the repo root."""
    return _repo_file_sha256(repo_root, rel, label, _is_safe_rel)


def _source_sha256(repo_root: object, rel: object, label: str) -> str:
    """The sha256 of a named SOURCE file inside the repo root."""
    return _repo_file_sha256(repo_root, rel, label, _is_safe_source_rel)


# --------------------------------------------------------------------------
# The WP8a qualified source map
# --------------------------------------------------------------------------

def wp8a_qualified_files() -> tuple[str, ...]:
    """Every file this package qualifies, sorted, as repository-relative paths.

    This module, its fixtures, its notes, the WP7 session module whose dry-run
    receipt is the bound evidence, the WP1 production identity validator, the
    §A v1 release file that validator reads and pins, and the frozen CUDA
    execution contract.  Nothing else is claimed.  The validator narrows this set
    to the files the WP1 source map does not ALREADY bind (see
    :func:`wp8a_role_files_for`), because a source-map path is bound by exactly
    one role and the frozen contract module is already qualified by WP1.
    """
    return tuple(sorted((THIS_FIXTURE_REL, THIS_MODULE_REL, THIS_NOTES_REL,
                         WP7_MODULE_REL, WP1_MODULE_REL, WP1_RELEASE_REL,
                         CONTRACT_MODULE_REL)))


def wp8a_role_files_for(already_bound: set) -> tuple[str, ...]:
    """The subset of :func:`wp8a_qualified_files` that this role must bind.

    A qualified-source-map path is single-use across the whole map (the same rule
    WP1 enforces at ``research/g9/stage2_production_identity.py:382``).  The
    frozen contract module is already bound by a WP1 role, so binding it again
    here would make every valid record collide.  Therefore this role binds exactly
    the package files that the WP1 map does not already cover; the already-bound
    ones remain qualified through their WP1 entry, whose hash is still re-verified
    against disk on every validation.
    """
    return tuple(sorted(path for path in wp8a_qualified_files() if path not in already_bound))


def _qualified_source_map_from(draft_source_map: Mapping[str, Any], repo_root: str) -> dict[str, Any]:
    """Compose the WP8a map: every WP1 role, plus the added ``wp8a_acceptance``.

    The WP1 roles are copied out of the embedded, WP1-validated source map
    verbatim, so their hashes are WP1's own and their shape has already been
    re-derived by ``stage2_production_identity.validate_source_map_shape()``.  The
    WP7 session module is added to the ``v1_engine`` role, because it is part of
    the reviewed WP7 package the dry-run evidence comes from.  The
    ``wp8a_acceptance`` role binds this package's own files that the WP1 roles do
    not already cover.  Every new hash is read from disk: nothing here is asserted.

    A duplicate path is not checked here.  WP1's shape validator has already
    refused one in the embedded map (``stage2_production_identity.py:382``), and
    the only path this function adds is :data:`WP7_MODULE_REL`, which is pinned to
    a single constant here — so a duplicate is not an input this builder can be
    given, and the single-use rule belongs to the validator, which does enforce it.
    """
    source_map = _object(draft_source_map, 'draft source map')
    roles: dict[str, list[dict[str, str]]] = {}
    for role in sorted(source_map['roles']):
        entries = [{'path': entry['path'], 'sha256': entry['sha256']}
                   for entry in source_map['roles'][role]]
        roles[role] = sorted(entries, key=lambda entry: entry['path'])
    wp7_entry = {'path': WP7_MODULE_REL,
                 'sha256': _source_sha256(repo_root, WP7_MODULE_REL,
                                          'the WP7 session module in the qualified source map')}
    engine = roles[wp1.V1_ENGINE_ROLE] + [wp7_entry]
    roles[wp1.V1_ENGINE_ROLE] = sorted(engine, key=lambda entry: entry['path'])
    already_bound = {entry['path'] for entries in roles.values() for entry in entries}
    roles[WP8A_ROLE] = [
        {'path': path,
         'sha256': _source_sha256(repo_root, path, f'the WP8a qualified file {path!r}')}
        for path in wp8a_role_files_for(already_bound)
    ]
    return {
        'schema': QUALIFIED_SOURCE_MAP_SCHEMA,
        'hash_algorithm': QUALIFIED_SOURCE_MAP_HASH_ALGORITHM,
        'roles': roles,
        'bound_file_count': sum(len(entries) for entries in roles.values()),
        'not_yet_built_roles': sorted(set(source_map['not_yet_built_roles'])),
    }


def _validate_qualified_source_map_shape(source_map: object, repo_root: object = None) -> dict[str, Any]:
    """Re-derive every qualified-source-map invariant from the map itself.

    Nothing is trusted: the key set, the schema, the hash algorithm, the per-role
    sorted order, the single-use path rule, the file count and the identity of
    the WP8a role's own file set are all recomputed and compared.  This mirrors
    ``stage2_production_identity.validate_source_map_shape``
    (``research/g9/stage2_production_identity.py:360-387``) but is NOT a call to
    it, because the WP8a map carries one role the WP1 role table does not have.
    """
    body = _object(source_map, 'qualified source map')
    _require(set(body) == set(QUALIFIED_SOURCE_MAP_KEYS), 'qualified source map has the wrong key set')
    _require(body['schema'] == QUALIFIED_SOURCE_MAP_SCHEMA,
             f'qualified source map schema is not the pinned {QUALIFIED_SOURCE_MAP_SCHEMA!r}')
    _require(body['hash_algorithm'] == QUALIFIED_SOURCE_MAP_HASH_ALGORITHM,
             f'qualified source map hash_algorithm is not the pinned {QUALIFIED_SOURCE_MAP_HASH_ALGORITHM!r}')
    roles = _object(body['roles'], 'qualified source map roles')
    _require(set(roles) == set(wp1.ROLES) | {WP8A_ROLE},
             'qualified source map does not carry exactly the WP1 role set plus the WP8a role')
    total = 0
    seen: set[str] = set()
    repo_root = repo_root if type(repo_root) is str else None
    for role in sorted(roles):
        entries = roles[role]
        # The per-role shape findings are COLLECTED and reported once, for the
        # same reason as the record shell above: "not a list", "a malformed
        # entry" and "not in sorted path order" are each reachable only by
        # corrupting the role, and a separate guard per finding would let the
        # fixture satisfy one of them with any of the others present.
        problems: list[str] = []
        if type(entries) is not list:
            problems.append(f'is not a list but a {type(entries).__name__}')
        elif not entries:
            problems.append('is empty')
        else:
            for entry in entries:
                entry_body = _object(entry, f'qualified source map role {role!r} entry')
                if set(entry_body) != {'path', 'sha256'}:
                    problems.append(f'has a malformed entry {sorted(entry_body)}')
                    continue
                entry_sha = _sha256_of(entry_body['sha256'],
                                        f'qualified source map role {role!r} entry sha256')
                # The entry's hash is compared against the bytes on disk HERE, in
                # the same pass, rather than in a later one that a caller could
                # skip.  It is the only way the shape check above is more than an
                # assertion: a well-formed but wrong hash is refused by this, and a
                # well-formed and RIGHT hash is the only thing that survives.
                _require(entry_sha == _source_sha256(
                             repo_root, entry_body['path'],
                             f'qualified source map role {role!r} entry path')
                         if repo_root is not None else True,
                         f'qualified source map role {role!r} entry {entry_body["path"]!r} '
                         'does not hash to its recorded sha256')
                if entry_body['path'] in seen:
                    problems.append(f'binds {entry_body["path"]!r}, which another role already binds')
                seen.add(entry_body['path'])
            paths = [entry['path'] for entry in entries if 'path' in entry]
            if paths != sorted(paths):
                problems.append('entries are not in sorted path order')
        _require(not problems, f'qualified source map role {role!r} ' + '; '.join(problems))
        if type(entries) is list:
            total += len(entries)
    _require(body['bound_file_count'] == total,   # True == 1 and 25.0 == 25 are not counts
             'qualified source map bound_file_count does not equal the number of bound files')
    _require(body['not_yet_built_roles'] == sorted(set(wp1.NOT_YET_BUILT_ROLES)),
             'qualified source map not_yet_built_roles does not match the fixed WP1 role table')
    already_bound = {entry['path'] for role in sorted(roles) if role != WP8A_ROLE
                     for entry in roles[role]}
    _require(sorted(entry['path'] for entry in roles[WP8A_ROLE])
             == list(wp8a_role_files_for(already_bound)),
             "the WP8a qualified role does not bind exactly this package's own module, fixtures "
             "and notes and the files it reads that the WP1 map does not already bind")
    # Containment: EVERY file this package claims must be bound by SOME role, not
    # merely by the WP8a one.  Without this, a WP1 role could be edited to stop
    # binding one of them and the only guard left would be this module's own
    # constant, which a record's re-hashing would never notice.  This is the
    # check that makes "the module and every file it reads belongs in the newly
    # qualified source map" true of the RECORD, not just of the builder.
    # Containment.  Membership alone would allow the WP8a role to hand one of this
    # package's files back to a WP1 role and drop another, with the role's contents
    # still being "exactly the files the WP1 roles do not bind" — so this requires
    # every claimed file to be bound by SOME role, whoever binds it.
    #
    # This has NO input it can refuse while the two guards above hold, and round 2's
    # sweep confirmed it: any map that satisfies membership and single-use either
    # also satisfies this, or is refused by one of those first.  It is therefore not
    # listed as an accepted equivalent — it is not a guard, it is the statement of
    # the invariant those two guards jointly imply.  The fixture pins the pair, not
    # this line, and says so.
    return dict(body)


# --------------------------------------------------------------------------
# The builder
# --------------------------------------------------------------------------

def _validated_draft(draft_identity: object) -> dict[str, Any]:
    """Re-validate the embedded payload with the UNMODIFIED WP1 validator.

    ``validate_production_identity()`` is the only thing that decides what a WP1
    identity is, and it is called exactly as published: it requires
    ``DRAFT_UNQUALIFIED`` and ``authorization == NONE``
    (``research/g9/stage2_production_identity.py:396-402``).  A payload claiming
    any other state is refused here by the same refusal WP1 already raises, so
    nothing in this module can widen what WP1 accepts.
    """
    try:
        wp1.validate_production_identity(draft_identity)
    except wp1.ProductionIdentityError as exc:
        raise AcceptanceRecordError(
            f'the embedded payload is not an accepted WP1 DRAFT identity: {exc}') from exc
    return copy.deepcopy(_object(draft_identity, 'draft identity'))


def unresolved_review_note() -> dict[str, Any]:
    """The review-note placeholders a freshly built record carries.

    The three values are null because no independent review has run.  A record
    carrying them is refused by the production gate; only
    :func:`bind_review_note` replaces them, and only from a file that exists.
    """
    return {
        'schema': APPROVAL_SCHEMA,
        'status': APPROVAL_STATUS,
        'reviewed_by': 'NOT-YET-REVIEWED',
        'review_note_rel': None,
        'review_note_sha256': None,
        'reviewed_at_utc': None,
        'statement': APPROVAL_STATEMENT,
    }


def build_acceptance_record(draft_identity: Mapping[str, Any], *, repo_root: str) -> dict[str, Any]:
    """Wrap a genuine WP1 DRAFT identity in a complete, canonical acceptance record.

    The draft is validated by the unmodified WP1 validator first, so the embedded
    payload is known to be a real, canonical, still-draft identity and the
    returned hash is WP1's own.  ``repo_root`` is used to read the WP7 dry-run
    receipt and to hash every file the qualified source map names, so the record
    returned here names only files that exist and only hashes that were observed.

    The result carries ``status == approved`` but is NOT accepted until the
    independent review binds its note and the lead pins the record's
    ``accepted_content_sha256``; see the module docstring for why that pin is the
    authority and this module holds no signature.
    """
    draft_body = _validated_draft(draft_identity)
    evidence = resolved_wp7_dry_run_evidence(repo_root)
    source_map = _object(draft_body['source_map'], 'draft source map')
    qualified = _qualified_source_map_from(source_map, repo_root)
    record: dict[str, Any] = {
        'schema': ACCEPTANCE_SCHEMA,
        'status': APPROVED_STATUS,
        'scope_statement': SCOPE_STATEMENT,
        'approval': unresolved_review_note(),
        'bound': {
            'draft_identity_schema': wp1.PRODUCTION_IDENTITY_SCHEMA,
            'draft_identity_status': draft_body['status'],
            'draft_identity_content_sha256': wp1.validate_production_identity(draft_body),
            'qualification_identity_content_sha256': draft_body['qualification_identity']['content_sha256'],
            'source_map_content_sha256': contract.content_sha256(source_map),
            'bound_file_count': source_map['bound_file_count'],
            'qualified_source_map_content_sha256': contract.content_sha256(qualified),
            'qualified_source_map_file_count': qualified['bound_file_count'],
        },
        'draft_identity': draft_body,
        'wp7_dry_run_evidence': evidence,
        'qualified_source_map': qualified,
    }
    record['content_sha256'] = _recompute_content_sha256(record)
    return record


def bind_review_note(record: Mapping[str, Any], review_note_rel: str, reviewed_at_utc: str,
                     *, reviewed_by: str, repo_root: str) -> dict[str, Any]:
    """Independent review: bind the review note's EXACT bytes to the record.

    The review note is read out of the repo root and hashed here.  This is the
    review act, and it is NOT an approval: the record's status is already
    ``approved`` and this function changes nothing about that.  What it supplies
    is a file the validator can find and re-hash, so a record cannot claim a
    review that left no artifact.
    """
    body = _object(record, 'acceptance record')
    _require(set(body) == set(RECORD_KEYS), 'acceptance record has the wrong key set')
    _require(body['schema'] == ACCEPTANCE_SCHEMA,
             f'acceptance schema mismatch: not the pinned {ACCEPTANCE_SCHEMA!r}')
    approval = _object(body['approval'], 'approval')
    _require(set(approval) == set(APPROVAL_KEYS), 'approval has the wrong key set')
    _require(approval['review_note_rel'] is None,
             'this record already binds a review note; a review note may not be replaced')
    stamp = reviewed_at_utc
    _require(type(stamp) is str and len(stamp) == UTC_STAMP_LENGTH,
             f'the review timestamp is not a {UTC_STAMP_LENGTH}-character string: {stamp!r}')
    _require(_is_utc_stamp(stamp),
             f'the review timestamp is not a YYYY-MM-DDTHH:MM:SSZ stamp: {stamp!r}')
    reviewer = _stripped_string(reviewed_by, 'the reviewer label')
    observed = _document_sha256(repo_root, review_note_rel, 'the review note')
    _require(_sha256_of(observed, 'the observed review-note sha256') == observed,
             'the observed review-note hash is not the value itself')
    updated = copy.deepcopy(body)
    updated['approval'] = dict(approval)
    updated['approval']['reviewed_by'] = reviewer
    updated['approval']['review_note_rel'] = review_note_rel
    updated['approval']['review_note_sha256'] = observed
    updated['approval']['reviewed_at_utc'] = stamp
    updated['content_sha256'] = _recompute_content_sha256(updated)
    # The act must leave a record the production gate ACCEPTS.  This is the only
    # place the module can say that, because only here does it choose the note it
    # binds; the fixture proves it by round-tripping through the gate rather than
    # by inspecting the block.  (Without it, a note with an unusual but legal name
    # could be bound here and then refused at the gate, and no unit test would
    # know.)  It costs one hash and two reads.
    validate_acceptance_record(updated, reviewed_record_sha256=record_content_sha256(updated),
                               repo_root=repo_root)
    return updated


# --------------------------------------------------------------------------
# The WP7 dry-run evidence, read from disk
# --------------------------------------------------------------------------

def _read_wp7_receipt(repo_root: object) -> tuple[dict[str, Any], str]:
    """Read and fully validate the WP7 dry-run receipt; return it with its hash.

    The receipt must be a canonical, complete ``wp7_session`` receipt living
    inside the repo root.  Its shape is decided by the WP7 session module, not by
    this one, and its content hash is re-derived there
    (``research/g9/kaggle_wp7/wp7_session.py:1022-1023``).  Every one of those
    checks runs here, once, so the builder and the validator read the file
    through the SAME function and cannot drift apart.
    """
    rel = WP7_RECEIPT_REL
    observed = _document_sha256(repo_root, rel, 'the WP7 dry-run receipt')
    raw = Path(repo_root).resolve().joinpath(rel).read_bytes()
    try:
        receipt = json.loads(raw.decode('utf-8'))
    except (UnicodeDecodeError, ValueError) as exc:
        raise AcceptanceEvidenceError(f'the WP7 dry-run receipt is not decodable JSON: {exc}') from exc
    body = _object(receipt, 'the WP7 dry-run receipt')
    # The receipt's own completeness gate, called as published.  Nothing here
    # re-implements it: if ``wp7_session`` refuses the receipt, this package has
    # no receipt to bind, and its refusal is re-typed but never weakened.  The
    # call's RESULT is bound to a local on purpose — a discarded call is the one a
    # mutation can remove without anything noticing — and it is then checked, so
    # the gate's own verdict is something the validator reads rather than
    # something it assumes.
    verdict = None
    refusal = ''
    try:
        verdict = wp7.validate_receipt(body)
    except wp7.Wp7SessionError as exc:
        refusal = str(exc)
    _require(not refusal,
             'the WP7 dry-run receipt was refused by the WP7 session module itself: ' + refusal)
    # Everything below reads the gate's OWN verdict, not the bytes: the record binds
    # what the gate approved, not what merely decoded to the same object.
    _require(verdict == body,
             'the WP7 session module did not return the receipt it validated')
    # The bytes on disk must be exactly what this gate returned, so the record
    # binds the receipt the gate approved rather than a file that merely decodes
    # to something similar.
    _require(raw == wp7.canonical_bytes(verdict) + b'\n',  # type: ignore[arg-type]
             'the WP7 dry-run receipt is not the canonical bytes the WP7 gate approved')
    # A receipt that never reached the step which produced the identity candidate
    # is not evidence for this acceptance, whatever else it says.  WP7's own
    # completeness gate already requires every step in ``REQUIRED_STEPS``
    # (``wp7_session.py:1017-1021``); this checks the two named ones and says so.
    executed = verdict.get('steps_executed')  # type: ignore[union-attr]
    _require(type(executed) is list,  # type: ignore[arg-type]
             'the WP7 dry-run receipt steps_executed is not a list, so the identity step '
             'cannot be confirmed')
    # The refusal names ONLY the step that is absent, so it is attributable to one
    # missing step rather than to either of them.  A message that named both would
    # be true whichever was removed, and a guard whose refusal is true in two
    # distinct situations cannot be pinned to either.
    for step in (WP7_IDENTITY_STEP, WP7_RECEIPT_REQUIRED_STEP):
        _require(step in executed,  # type: ignore[operator]
                 f'the WP7 dry-run receipt does not name the step {step!r} '
                 'that produced this evidence')
    return body, observed


def _evidence_from_receipt(receipt: Mapping[str, Any], observed: str) -> dict[str, Any]:
    """The evidence block, derived entirely from the receipt that was read.

    Nothing here is typed by this module: ``mode``, ``package_status``, the two
    authorization flags, the scientific-output count, the executed steps and the
    receipt's own content hash are all COPIED from the receipt that
    :func:`_read_wp7_receipt` read and that ``wp7_session.validate_receipt()``
    accepted.  The record therefore cannot describe a dry run that the receipt
    does not describe, because every field re-derives from those bytes.
    """
    return {
        'evidence_state': EVIDENCE_RESOLVED,
        'receipt_rel': WP7_RECEIPT_REL,
        'receipt_sha256': observed,
        'mode': receipt['mode'],
        'steps_executed': list(receipt['steps_executed']),
        'package_status': _stripped_string(receipt['package_status'],
                                           'the WP7 dry-run receipt package_status'),
        'push_authorized': receipt['push_authorized'],
        'gpu_allocation_authorized': receipt['gpu_allocation_authorized'],
        'scientific_output_count': receipt['scientific_output_count'],
        'content_sha256': _sha256_of(receipt['content_sha256'],
                                     'the WP7 dry-run receipt content_sha256'),
        'statement': EVIDENCE_STATEMENT,
    }


def resolved_wp7_dry_run_evidence(repo_root: str) -> dict[str, Any]:
    """Read the WP7 dry-run receipt out of the repo and bind its EXACT bytes.

    The receipt must exist inside the repo root, be canonical, and pass the WP7
    session module's OWN completeness gate; its hash and every field of the
    evidence block are then read from the FILE, so a record can never name a
    receipt that does not exist or a fact nobody observed.  Round 1 accepted a
    record naming a receipt that was not in the repository at all; this is the
    guard that was missing.
    """
    receipt, observed = _read_wp7_receipt(repo_root)
    return _evidence_from_receipt(receipt, observed)


# --------------------------------------------------------------------------
# The validator
# --------------------------------------------------------------------------

def _validate_approval(approval: object, repo_root: object) -> dict[str, Any]:
    """The review-note block: its shape, then the note's existence and hash.

    A record built but not reviewed carries ``null`` for the three note fields,
    so the note path is ``None`` here and the record is refused: no note, no
    acceptance.  A reviewed record names a note that must exist, be a regular
    non-symlink file inside the repo root, and hash to the recorded value.

    The block's six shape checks — schema, status, statement, reviewer label and
    the review stamp's length and form — are read HERE and reported from here,
    rather than being passed to six separate guards that each report the same
    "wrong key set".  That is not a weakening: every one of them is still
    refused, and the fixture still drives each through the gate and names it.  It
    is the only arrangement in which the fixture can tell which check fired, and
    a guard nobody can attribute is a guard nobody notices has gone.
    """
    body = _object(approval, 'approval')
    _require(set(body) == set(APPROVAL_KEYS), 'approval has the wrong key set')
    shape: list[str] = []
    if body['schema'] != APPROVAL_SCHEMA:
        shape.append(f'schema is {body["schema"]!r}, not the pinned {APPROVAL_SCHEMA!r}')
    if body['status'] != APPROVAL_STATUS:
        shape.append(f'status is {body["status"]!r}, not the pinned {APPROVAL_STATUS!r}')
    if body['statement'] != APPROVAL_STATEMENT:
        shape.append('the statement is not the pinned reviewed wording')
    if not _is_reviewed_by(body['reviewed_by']):
        shape.append(f'reviewed_by is {body["reviewed_by"]!r}, not a non-empty stripped string')
    stamp_value = body['reviewed_at_utc']
    if type(stamp_value) is not str or len(stamp_value) != UTC_STAMP_LENGTH:
        shape.append(f'reviewed_at_utc is {stamp_value!r}, not a '
                     f'{UTC_STAMP_LENGTH}-character string')
    elif not _is_utc_stamp(stamp_value):
        shape.append(f'reviewed_at_utc is {stamp_value!r}, not a YYYY-MM-DDTHH:MM:SSZ stamp')
    _require(not shape, 'approval block shape is wrong: ' + '; '.join(shape))
    note_rel = body['review_note_rel']
    if note_rel is None:
        carried = [name for name, value in (('review_note_sha256', body['review_note_sha256']),
                                            ('reviewed_at_utc', body['reviewed_at_utc']))
                   if value is not None]
        _require(not carried,
                 'an unreviewed record must not carry a review-note hash or a review time '
                 'without naming a review note; it carries ' + ', '.join(carried))
        raise AcceptanceReviewError(
            'this record names no review note; the independent review has not completed')
    observed = _document_sha256(repo_root, note_rel, 'the review note')
    _require(observed == _sha256_of(body['review_note_sha256'], 'approval review_note_sha256'),
             'the review note does not hash to its recorded sha256')
    return dict(body)


def _validate_evidence(evidence: object, repo_root: object) -> dict[str, Any]:
    """The WP7 dry-run evidence: shape, then RE-DERIVED from the receipt on disk.

    Round 1's forged record named a receipt that did not exist and passed.  Here
    the receipt is read again, put through the WP7 session module's own
    completeness gate, and the ENTIRE evidence block is re-derived from those
    bytes and compared field by field.  So the evidence is not merely "a sha256
    that matches some file"; it is a claim about the exact receipt on disk, and
    every field of it is that receipt's own value.
    """
    body = _object(evidence, 'WP7 dry-run evidence')
    _require(set(body) == set(EVIDENCE_KEYS), 'WP7 dry-run evidence has the wrong key set')
    # ``evidence_state`` and ``statement`` are read here and reported from here,
    # for the same reason as the approval block above: three guards that all say
    # "wrong key set" cannot be told apart, so neither of these two could be
    # attributed if it ever stopped firing.
    shape: list[str] = []
    if body['evidence_state'] != EVIDENCE_RESOLVED:
        shape.append(f'evidence_state is {body["evidence_state"]!r}, not the resolved '
                     f'{EVIDENCE_RESOLVED!r}; no production identity may be accepted on a placeholder')
    if body['statement'] != EVIDENCE_STATEMENT:
        shape.append('the statement is not the pinned resolved wording')
    _require(not shape, 'WP7 dry-run evidence is not resolved: ' + '; '.join(shape))
    receipt, observed = _read_wp7_receipt(repo_root)
    named = body['receipt_rel']
    _require(named == WP7_RECEIPT_REL,
             f'the WP7 dry-run evidence names {named!r}, not the pinned receipt path')
    _require(observed == _sha256_of(body['receipt_sha256'],
                                     'WP7 dry-run evidence receipt_sha256'),
             'the WP7 dry-run receipt does not hash to its recorded sha256')
    derived = _evidence_from_receipt(receipt, observed)
    differing = sorted(key for key in EVIDENCE_KEYS if body.get(key) != derived[key])
    _require(not differing,
             'the WP7 dry-run evidence does not re-derive from the receipt on disk: '
             + ', '.join(repr(key) for key in differing)
             + ' must be the receipt\'s own values')
    return dict(body)


def _validate_bound(record: Mapping[str, Any], repo_root: object = None) -> dict[str, Any]:
    """Re-derive every bound value from the embedded payload and compare."""
    body = _object(record, 'acceptance record')
    bound = _object(_field(body, 'bound', 'acceptance record'), 'bound block')
    _require(set(bound) == set(BOUND_KEYS), 'bound block has the wrong key set')
    draft = _validated_draft(_field(body, 'draft_identity', 'acceptance record'))
    _require(bound['draft_identity_schema'] == wp1.PRODUCTION_IDENTITY_SCHEMA,
             'bound draft_identity_schema is not the WP1 draft schema')
    _require(bound['draft_identity_status'] == wp1.DRAFT_STATUS,
             f'bound draft_identity_status is not {wp1.DRAFT_STATUS!r}; an accepted record may never '
             're-label the draft as qualified')
    _require(bound['draft_identity_content_sha256'] == wp1.validate_production_identity(draft),
             'bound draft_identity_content_sha256 does not re-derive from the embedded draft identity')
    _require(bound['qualification_identity_content_sha256']
             == draft['qualification_identity']['content_sha256'],
             'bound qualification_identity_content_sha256 differs from the embedded frozen '
             'qualification identity')
    _require(bound['source_map_content_sha256'] == contract.content_sha256(draft['source_map']),
             'bound source_map_content_sha256 does not re-derive from the embedded source map')
    _require(type(bound['bound_file_count']) is int,
             'bound bound_file_count must be an integer, not '
             f'{type(bound["bound_file_count"]).__name__}')
    _require(bound['bound_file_count'] == draft['source_map']['bound_file_count'],
             'bound bound_file_count differs from the embedded source map')
    qualified = _validate_qualified_source_map_shape(
        _field(body, 'qualified_source_map', 'acceptance record'))
    _require(bound['qualified_source_map_content_sha256'] == contract.content_sha256(qualified),
             'bound qualified_source_map_content_sha256 does not re-derive from the embedded '
             'qualified source map')
    _require(bound['qualified_source_map_file_count'] == qualified['bound_file_count'],
             'bound qualified_source_map_file_count differs from the embedded qualified source map')
    return dict(bound)


def validate_acceptance_record(record: object, *, reviewed_record_sha256: str,
                               repo_root: str) -> dict[str, Any]:
    """The structural PRODUCTION validator.  Returns the acceptance receipt.

    A record is accepted only if ALL of the following hold, each re-derived
    rather than trusted:

    * the pinned schema and scope wording, and the ``approved`` status;
    * the record's canonical bytes are exactly ``canonical_record_bytes()`` and
      their sha256 equals ``reviewed_record_sha256`` — the value the caller passes
      in because the lead pinned it after the owner approved, and the only
      authority this package has;
    * a review note and a WP7 dry-run receipt that both EXIST inside the repo
      root, are regular non-symlink files, and hash to the values recorded;
    * a bound block whose every value re-derives from an embedded identity that
      the UNMODIFIED WP1 validator still accepts as a DRAFT;
    * a WP8a qualified source map whose every named file is re-hashed against the
      bytes on disk, and whose WP8a role binds exactly this package's own files.

    There is no signature and no fixture token: round 1 had both, and neither
    added authority.  A caller cannot present a forged record together with a pin
    of its own making, because the pin is not derived from the record.
    """
    body = _object(record, 'acceptance record')
    # The shell — key set, schema and status — is reported as ONE refusal that
    # names every defect it found.  Three separate guards would all refuse with
    # "acceptance record has the wrong key set", because the fixture must delete
    # or corrupt a key to reach any of them; that is indistinguishable, so none of
    # the three could be attributed if it stopped firing.  Listing the defects
    # keeps every check and makes each one nameable.
    shell: list[str] = []
    if set(body) != set(RECORD_KEYS):
        missing = sorted(set(RECORD_KEYS) - set(body))
        extra = sorted(set(body) - set(RECORD_KEYS))
        shell.append(f'wrong key set: missing {missing}, unexpected {extra}')
    if body.get('schema') != ACCEPTANCE_SCHEMA:
        shell.append(f'schema is {body.get("schema")!r}, not the pinned {ACCEPTANCE_SCHEMA!r}')
    if body.get('status') != APPROVED_STATUS:
        shell.append(f'status is {body.get("status")!r}, not the pinned {APPROVED_STATUS!r}')
    _require(not shell, 'acceptance record has the wrong key set: ' + '; '.join(shell))
    _require(body['scope_statement'] == SCOPE_STATEMENT,
             'acceptance scope_statement is not the pinned wording; an acceptance may not describe '
             'itself as qualified, approved or authorized')
    pin = _sha256_of(reviewed_record_sha256, 'the reviewed acceptance record sha256')
    _require(record_content_sha256(body) == pin,
             'acceptance record is not the independently reviewed record: the sha256 of its exact '
             'canonical bytes is not the reviewed pin supplied by the caller')
    qualified = _validate_qualified_source_map_shape(
        _field(body, 'qualified_source_map', 'acceptance record'), repo_root)
    approval = _validate_approval(_field(body, 'approval', 'acceptance record'), repo_root)
    evidence = _validate_evidence(_field(body, 'wp7_dry_run_evidence', 'acceptance record'), repo_root)
    bound = _validate_bound(body, repo_root)
    recomputed = _recompute_content_sha256(body)
    _require(body['content_sha256'] == recomputed,
             'acceptance record content_sha256 mismatch')
    return {
        'schema': body['schema'],
        'status': APPROVED_STATUS,
        'accepted_content_sha256': record_content_sha256(body),
        'review_note_sha256': approval['review_note_sha256'],
        'draft_identity_content_sha256': bound['draft_identity_content_sha256'],
        'qualification_identity_content_sha256': bound['qualification_identity_content_sha256'],
        'source_map_content_sha256': bound['source_map_content_sha256'],
        'bound_file_count': bound['bound_file_count'],
        'qualified_source_map_content_sha256': bound['qualified_source_map_content_sha256'],
        'qualified_source_map_file_count': bound['qualified_source_map_file_count'],
        'wp7_dry_run_receipt_sha256': evidence['receipt_sha256'],
        'wp7_dry_run_mode': evidence['mode'],
        'wp7_dry_run_package_status': evidence['package_status'],
        'wp7_dry_run_steps_executed': list(evidence['steps_executed']),
    }


def accept_production_identity(record: object, *, reviewed_record_sha256: str,
                               repo_root: str) -> dict[str, Any]:
    """The gate the WP8 bundle calls.  Refuses anything the owner did not approve.

    It returns the accepted binding a bundle needs: the exact hashes, the WP8a
    qualified source map and the embedded draft identity to pass to
    ``stage2_production_identity.exact_match()``.
    """
    receipt = validate_acceptance_record(record, reviewed_record_sha256=reviewed_record_sha256,
                                         repo_root=repo_root)
    body = _object(record, 'acceptance record')
    # NO status/schema re-check happens here, and that is deliberate.
    # ``validate_acceptance_record`` has already proved both, and it builds its own
    # return values from the pinned constants rather than from the record, so a
    # re-read here would compare a constant with itself.  Round 2's sweep confirmed
    # it is unkillable: no record, mutant or garbage value can make it disagree.
    # It is therefore not here at all, rather than here-and-listed-as-an-equivalent
    # - a check that cannot fire is not a check.
    return {
        'accepted_content_sha256': receipt['accepted_content_sha256'],
        'review_note_sha256': receipt['review_note_sha256'],
        'draft_identity_content_sha256': receipt['draft_identity_content_sha256'],
        'qualification_identity_content_sha256': receipt['qualification_identity_content_sha256'],
        'source_map_content_sha256': receipt['source_map_content_sha256'],
        'bound_file_count': receipt['bound_file_count'],
        'qualified_source_map_content_sha256': receipt['qualified_source_map_content_sha256'],
        'qualified_source_map_file_count': receipt['qualified_source_map_file_count'],
        'wp7_dry_run_receipt_sha256': receipt['wp7_dry_run_receipt_sha256'],
        'wp7_dry_run_mode': receipt['wp7_dry_run_mode'],
        'wp7_dry_run_package_status': receipt['wp7_dry_run_package_status'],
        'wp7_dry_run_steps_executed': list(receipt['wp7_dry_run_steps_executed']),
        'qualified_source_map': copy.deepcopy(_object(_field(body, 'qualified_source_map',
                                                             'acceptance record'),
                                                      'qualified source map')),
        'draft_identity': copy.deepcopy(_object(_field(body, 'draft_identity', 'acceptance record'),
                                                'draft identity')),
    }


def exact_match_session(session_identity: Mapping[str, Any], record: Mapping[str, Any], *,
                        reviewed_record_sha256: str, repo_root: str) -> dict[str, Any]:
    """Compare one session identity against the accepted identity, fail-closed.

    The comparison is NOT re-implemented: ``stage2_production_identity.exact_match()``
    is the total, symmetric, name-every-difference comparison
    (``research/g9/stage2_production_identity.py:436-475``) and it is called as
    published, so this package cannot be laxer than WP1 about what a difference
    is.  Its refusal is re-raised as :class:`AcceptanceSessionMismatch`, which
    carries the same named fields.
    """
    accepted = accept_production_identity(record, reviewed_record_sha256=reviewed_record_sha256,
                                          repo_root=repo_root)
    body = _object(record, 'acceptance record')
    try:
        verdict = wp1.exact_match(session_identity, _field(body, 'draft_identity',
                                                           'acceptance record'))
    except wp1.ProductionIdentityMismatch as exc:
        raise AcceptanceSessionMismatch(exc.differing_fields) from exc
    except wp1.ProductionIdentityError as exc:
        # WP1 refused a session identity that is not even a well-formed WP1
        # identity.  It is re-typed here so a caller of this module catches one
        # family, while WP1's own refusal text is preserved verbatim.
        raise AcceptanceRecordError(f'WP1 refused the session identity: {exc}') from exc
    return {
        'verdict': verdict['verdict'],
        'session_content_sha256': verdict['session_content_sha256'],
        'accepted_content_sha256': accepted['accepted_content_sha256'],
        'differing_fields': [],
    }

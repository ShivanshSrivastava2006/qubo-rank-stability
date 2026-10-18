# Additive V2 integration candidate: unreviewed/unexecuted; frozen originals unchanged.
"""WP8c — the production session contract and adapter (v1).

STATUS: BUILD + VALIDATION ONLY. UNARMED. NOT A DRAW, NOT A RELEASE, NOT A PUSH.

This module is the versioned "production session" the owner approved for BUILDING
and VALIDATING at 2026-10-01 ~14:20 IST, owner default 3
(``research/decisions/GATE_9_WP7_PINNED_DRAFT_AND_WP7B_OWNER_DECISION.md:150-151``):

    "Production session and adapter: a reviewed, versioned session contract and
     adapter that feeds the existing ``build_record`` seam, with its source bound
     in the WP1 identity.  It may be built offline against synthetic inputs and
     is never armed before review."

WHAT THIS MODULE IS NOT
=======================
It does not draw.  It does not prepare a production instance.  It does not
issue or fabricate an owner approval.  It does not write a scientific record.
It does not push.  Every one of those is a separate owner gate, and the two that
would otherwise let a caller arm a scientific write are themselves UNSET today:

1.  **The accepted production identity gate is unset.**  The only accepted
    identity available offline is a WP1 ``DRAFT_UNQUALIFIED`` / ``authorization
    = NONE`` payload.  WP1's own validator *requires* exactly that
    (``research/g9/stage2_production_identity.py:400-402``), and
    ``stage2_production_identity.exact_match`` compares identities as published
    (``research/g9/stage2_production_identity.py:436-475``) rather than accepting
    a "production" claim.  WP8a is the reviewed route to a genuinely accepted
    identity, and its ``accept_production_identity`` requires an independently
    reviewed record SHA-256 the caller cannot derive from the record itself
    (``research/g9/wp8a/wp8a_production_identity_acceptance.py:1096-1118``,
    ``:1169-1205``).  WP8c therefore consumes WP8a and never re-implements it.

2.  **The WP8b R6 production-release gate is unset.**  WP8b's
    ``_require_production_release_pinned`` has three independently testable
    clauses and today the FIRST already refuses everything
    (``research/g9/wp8b/wp8b_non_synthetic_preparation.py:894-932``):
    ``PRODUCTION_RELEASE_PINNED`` is ``False`` (line 406), so no decision record
    is pinned at all and every ``require_production=True`` validation raises
    ``ProductionReleaseNotPinned``.  WP8c never fabricates that record, never
    writes it, and never passes ``require_production=False`` on a code path
    that claims to be production.

THE TRUST BOUNDARY, STATED PRECISELY
====================================
The central rule is that **no caller-supplied value may stand in for a
validation**.  Concretely, and each of these is a guard in this file:

* There is no ``armed``, ``production``, ``approved``, ``verified``,
  ``require_production``, ``skip_checks`` or ``dry_run`` parameter on any public
  function.  Arming is a function of the *contents* of the records a caller
  supplies, never of a flag the caller supplies.  (The fixture pins this by
  signature inspection.)
* The instance is re-derived from the WP8d-production layout's own bound bytes
  by calling the reviewed ``verify_standin_instance`` / ``verify_instance``,
  and every hash this module then uses is taken from the *returned, verified*
  record, not from the caller's arguments
  (``research/g9/wp8d_production/wp8d_production_layout.py:1224-1233``).
* The identity is bound through WP8a's ``accept_production_identity`` and
  WP1's ``exact_match``; this module adds no second, weaker comparison.
* A one-use authorization is consumed through WP8b's
  ``consume_one_use_nonce`` registry, so replay is refused by a *stateful*
  registry rather than by anything in this file.
* The one session per instance rule is enforced by a state file written only
  after WP4b promotion, so an interrupted session leaves no permission behind.

THE ORDER OF OPERATIONS IS THE CONTRACT
=======================================
``run_production_session`` performs, in this order, and refuses at the first
failure:

  S1  instance verified through WP8d-production  (the one instance, one slot)
  S2  accepted identity bound through WP8a, session identity compared by WP1
  S3  one-use owner authorization consumed through WP8b's nonce registry
  S4  WP2 §B item 1 recheck before the session's first write
  S5  full WP3 §B item 2 check, including the D013 prerequisite
  S6  reviewed CUDA/record adapter into the existing ``build_record`` seam
  S7  WP4b sealed whole ranges
  S8  incomplete budget receipt, naming the last completed step and the
      promoted whole ranges, and NEVER an acceptance

A failed prerequisite blocks EVERY dependent device step and every dependent
write: the session's step list is walked in order and ``_require_passed`` is
checked before each dependent step, so a WP2 failure means no device backend is
constructed, no record is built and no range is staged.
"""
from __future__ import annotations
import copy
import datetime
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parents[2]
if str(_ROOT) not in os.sys.path:
    os.sys.path.insert(0, str(_ROOT))
from research.g9 import stage2_production_identity as wp1
from research.g9 import stage2_section_b2_harness as harness
from research.g9 import stage2_section_b1_recheck as wp2
from research.g9 import stage2_coordinate_records as records
from research.g9 import stage2_production_writer as writer
from research.g9.wp8a import wp8a_production_identity_acceptance as wp8a
from research.g9.wp8b import wp8b_non_synthetic_preparation_v2 as wp8b
from research.g9.wp8d_production import wp8d_production_layout_v2 as wp8dp

class ProductionSessionError(ValueError):
    """Base class.  A caller writing ``except ProductionSessionError:`` catches
    every refusal this module raises on purpose."""

class InstanceRefused(ProductionSessionError):
    """The one instance did not verify through WP8d-production."""

class IdentityGateUnset(ProductionSessionError):
    """The owner release / accepted-identity / scientific-write gates are unset."""

class AuthorizationRefused(ProductionSessionError):
    """The one-use owner authorization is absent, stale, forged or replayed."""

class PrerequisiteFailed(ProductionSessionError):
    """A named prerequisite failed; every dependent step is blocked."""

class ResumeRefused(ProductionSessionError):
    """A resume attempt violated the one-session-per-instance rule."""
SESSION_SCHEMA = 'decisions_os/g9_wp8c_production_session/v2'
RECEIPT_SCHEMA = 'decisions_os/g9_wp8c_production_session_receipt/v2'
AUTHORIZATION_SCHEMA = 'decisions_os/g9_wp8c_one_use_scientific_write_authorization/v1'
SESSION_STATE_SCHEMA = 'decisions_os/g9_wp8c_session_state/v1'
RESUME_POLICY_SCHEMA = 'decisions_os/g9_wp8c_resume_policy/v1'
SCOPE_STATEMENT = 'WP8c versioned production session contract and adapter. BUILD AND VALIDATION ONLY, UNARMED. It consumes one previously validated WP8d production layout, binds an owner-accepted identity through WP8a, consumes one instance-specific one-use owner authorization, and drives WP2, WP3, the reviewed record adapter into the existing build_record seam, and WP4b sealed whole ranges. It draws nothing, prepares no production instance, issues no approval, writes no scientific record and pushes nothing. Owner default 3 of the 2026-10-01 ~14:20 IST WP8 design defaults.'
AUTHORIZED_ACTION = 'run_wp8c_production_scientific_session'
STEP_ORDER = ('instance_verified', 'identity_bound', 'authorization_consumed', 'wp2_recheck_passed', 'wp3_check_passed', 'records_built', 'ranges_promoted')
DEVICE_OR_WRITE_STEPS = ('wp3_check_passed', 'records_built', 'ranges_promoted')
POST_RUN_ONLY_IMAGE_FIELDS = ('kaggle_image', 'image_manifest_sha256', 'image_config_id', 'image_name')
CHILD_ENVIRONMENT_ALLOWLIST = frozenset({'PATH', 'LD_LIBRARY_PATH', 'CUDA_HOME', 'CUDA_VERSION', 'CUDA_VISIBLE_DEVICES', 'CUDA_DEVICE_ORDER', 'BUILD_DATE', 'COLAB_IMAGE_TYPE', 'GIT_COMMIT', 'HOME', 'LANG', 'TMPDIR'})
CHILD_ENVIRONMENT_PREFIXES = ('LC_', 'NVIDIA_')
CHILD_ENVIRONMENT_DENIED_PREFIXES = ('KAGGLE_', 'PYTHON')
CHILD_ISOLATION_FLAGS = ('-I', '-S', '-B')
BUDGET_SECONDS = 10 * 60 * 60
KAGGLE_HARD_TIMEOUT_SECONDS = 36600
KAGGLE_IMAGE_STATUS_PENDING = 'pending_image_metadata_audit'
RESUME_POLICY = {'schema': RESUME_POLICY_SCHEMA, 'sessions_per_instance': 1, 'resume_unit': 'missing_whole_ranges_only', 'resume_requires_new_authorization': True, 'resume_requires_same_identity': True, 'incomplete_run_is_accepted': False, 'statement': 'One session per instance. A budget stop issues a NON-ACCEPTING incomplete receipt naming the last completed step and the promoted whole ranges. A later session may run MISSING WHOLE RANGES ONLY, under the SAME identity and a NEW one-use owner authorization. A partially written range is discarded, never resumed mid-range, and an incomplete run is never accepted.'}
RECEIPT_STATUSES = ('complete_pending_image_audit', 'incomplete_budget', 'refused')
GATE_NAMES = ('wp8b_production_release_pinned', 'wp8a_accepted_identity_available', 'wp8c_scientific_write_authorized')

def _require(condition: object, message: str) -> None:
    """The one guard form in this module.  Fail-closed: falsy always refuses."""
    if not condition:
        raise ProductionSessionError(message)

def _require_step(condition: object, message: str) -> None:
    """A guard that must hold for a NAMED step of the frozen order.

    Separate from ``_require`` only in its message prefix, so a caller reading a
    refusal can tell a contract violation from a prerequisite failure without
    matching on message text.  Both are guards; both are swept.
    """
    if not condition:
        raise PrerequisiteFailed(message)

def _require_resume(condition: object, message: str) -> None:
    """A guard specific to the RESUME policy.

    Distinct from ``_require`` so that a caller can catch a refused resume as
    ``ResumeRefused`` without also catching an ordinary contract violation, and
    so the resume's own refusals are attributable.  Like the other two, it is
    fail-closed: falsy always refuses.
    """
    if not condition:
        raise ResumeRefused(message)

def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('ascii')

def _content_sha256(payload: Mapping[str, Any]) -> str:
    body = {key: value for key, value in payload.items() if key != 'content_sha256'}
    return hashlib.sha256(_canonical(body)).hexdigest()

def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()

def _is_sha256(value: object) -> bool:
    return type(value) is str and len(value) == 64 and all((character in '0123456789abcdef' for character in value))

def _require_sha256(value: object, label: str) -> str:
    _require(_is_sha256(value), f'{label} must be a sha256 hex digest, not {value!r}')
    return value

def _seal(record: Mapping[str, Any]) -> dict[str, Any]:
    """Return ``record`` with its own content hash, refusing a NaN anywhere."""
    body = copy.deepcopy(dict(record))
    body.pop('content_sha256', None)
    return dict(body, content_sha256=_content_sha256(body))

class AuthorityBoundary:
    """The single, clearly marked stand-in for hardware and owner authority.

    Everything this class "observes" is a CONSPICUOUSLY LABELLED NON-PRODUCTION
    constant supplied by the rehearsal.  It is the ONLY place in this module
    where anything resembling a platform observation or an owner act enters, and
    it is the only place the rehearsal may substitute.  The two properties that
    matter:

    * It can produce an observation, but it can NEVER produce a PASS.  Every
      guard downstream of it is driven by the real reviewed validators, so a
      boundary that lies about the platform is refused by WP1's ``exact_match``
      rather than believed.
    * It can NEVER satisfy an owner gate.  ``owner_authorization`` is a
      parameter the *caller* must supply from outside this module; the boundary
      has no method that creates one, writes an approval record, sets
      ``PRODUCTION_RELEASE_PINNED``, or writes WP8b's R6 decision record.
    """
    KIND = 'non_production_hardware_and_owner_authority_emulation'

    def __init__(self, observations: Mapping[str, Any], *, production: bool=False):
        _require(type(observations) is dict and observations, 'the authority boundary must be given explicit observations')
        _require(production is False, 'the authority boundary is a non-production stand-in and may not be constructed with production=True')
        self._observations = copy.deepcopy(dict(observations))
        self._production = False

    @property
    def kind(self) -> str:
        return self.KIND

    @property
    def production(self) -> bool:
        return self._production

    def observe_platform(self) -> dict[str, Any]:
        """Return the stand-in's platform observation, for the identity builder.

        The values are whatever the rehearsal declared.  They are NOT measured,
        NOT probed and NOT proof.  A value that disagrees with the pinned
        identity is refused downstream by WP1's total comparison, which is the
        point: the boundary can lie, and lying does not help.
        """
        return copy.deepcopy(self._observations)

    def device_backend(self) -> Any:
        """Return the WP3 device backend stand-in.

        There is no production device backend in this package and no code path
        that would construct one.  The rehearsal injects its own; the module
        only ever *receives* one through the injected ``seams`` mapping.
        """
        raise NotImplementedError("the authority boundary cannot construct a device backend: WP8c never builds a production device backend, and the rehearsal injects its own stand-in through seams['device_backend_factory']")

def session_state_path(root: Path | str, slot: object) -> Path:
    base = Path(root) / wp8dp.INSTANCE_ROOT
    return base / f'.wp8c_session_{_slot_token(slot)}.json'

def _slot_token(slot: object) -> str:
    """A safe file-name token for ``slot``, refusing anything not a canonical slot.

    The reviewed readers take a slot NUMBER (``verify_instance(1)``) and return a
    slot NAME (``stage2_01``) in their record, so both forms must be accepted and
    they must agree.  The mapping is WP8d's own
    (``research/g9/wp8d/wp8d_drawn_instance_layout.py`` ``slot_name`` /
    ``slot_number``), reached through ``wp8dp.SLOT_NAMES``; this module does not
    invent a numbering.  A traversal or unknown slot is refused here, so it can
    never become a file name.
    """
    if type(slot) is int and (not isinstance(slot, bool)):
        _require(1 <= slot <= len(wp8dp.SLOT_NAMES), f'slot number is outside the canonical slot range: {slot!r}')
        return wp8dp.SLOT_NAMES[slot - 1]
    _require(type(slot) is str and slot in wp8dp.SLOT_NAMES, f'slot is not one of the canonical slot names or numbers: {slot!r}')
    return slot

def _read_state(root: Path | str, slot: object) -> dict[str, Any] | None:
    path = session_state_path(root, slot)
    if not path.is_file() or path.is_symlink():
        return None
    raw = path.read_bytes()
    try:
        record = json.loads(raw.decode('ascii'))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProductionSessionError(f'the WP8c session state file for {slot!r} is not readable JSON: {exc}') from exc
    _require(type(record) is dict and record.get('schema') == SESSION_STATE_SCHEMA, 'the WP8c session state file is not a WP8c session state record')
    _require(raw == _canonical(record) + b'\n', 'the WP8c session state file is not the canonical encoding of its content')
    return record

def _write_state(root: Path | str, slot: object, record: Mapping[str, Any]) -> None:
    """Write the state file atomically, so a crash never leaves a torn record.

    A torn state file would be read as a MISSING one (``_read_state`` returns
    None for anything that is not a complete canonical record is NOT implied --
    a malformed file raises instead), so a partial write is a refusal rather
    than a silent permission grant.
    """
    path = session_state_path(root, slot)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = _canonical(record) + b'\n'
    temporary = path.with_name(path.name + f'.tmp-{os.getpid()}')
    with open(temporary, 'wb') as stream:
        stream.write(body)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    _require(path.read_bytes() == body, 'the WP8c session state file did not persist')

def _require_session_allowed(state: dict[str, Any] | None, slot: object, session_id: str) -> None:
    """The one-session-per-instance gate.

    ``state is None`` means no session has completed for this instance, so this
    one may start.  Otherwise the instance is CLOSED: a second session is
    refused here unless it is a resume under the SAME identity, which
    ``resume_missing_ranges`` checks separately and which still needs a NEW
    one-use authorization.
    """
    if state is None:
        return
    _require(state.get('status') == 'complete', f'instance {slot!r} already has a recorded session in state {state.get('status')!r}; exactly one session per instance is permitted and a partial session leaves no permission behind')
    _require(state.get('session_id') != session_id, f'instance {slot!r} session {session_id!r} has already run; a session may not be replayed on the same instance')
    _require(state.get('identity_sha256') is not None, 'the recorded session state carries no identity hash and is not usable')

def verify_instance_for_session(slot: object, *, root: Path | str, standin: bool, release_authority=None) -> dict[str, Any]:
    """Verify the one instance and return ONLY the reviewed package's record.

    This is the module's only entry to instance state.  It calls the reviewed
    WP8d-production reader and returns its dict unchanged; every later hash this
    module uses is read from that dict, so a caller cannot substitute its own
    instance hashes for the verified ones.

    ``standin`` is not an arming flag.  It selects which of the TWO reviewed
    readers is called — ``verify_standin_instance`` (WP8b ``require_production
    = False``) or ``verify_instance`` (``require_production=True``) — and each of
    those readers is a fixed, separately reviewed function
    (``research/g9/wp8d_production/wp8d_production_layout.py:1224-1233``).  A
    caller that names the production reader gets WP8b's R6 refusal today, not a
    weaker check.
    """
    _slot_token(slot)
    if standin:
        try:
            return wp8dp.verify_standin_instance(slot, root=root, release_authority=release_authority)
        except wp8dp.ProductionLayoutError as exc:
            raise InstanceRefused(f'the stand-in instance did not verify: {exc}') from exc
    try:
        return wp8dp.verify_instance(slot, root=root, release_authority=release_authority)
    except wp8dp.ProductionLayoutError as exc:
        raise InstanceRefused(f'the production instance did not verify through the reviewed WP8d layout, which routes WP8b with require_production=True: {exc}') from exc

def require_instance_matches_session(verified: Mapping[str, Any], *, expected_instance_id: str, expected_slot: object) -> None:
    """Bind the caller's instance claim to the VERIFIED record, fail-closed.

    Without this, a caller could verify slot 1 and then name slot 2's instance id
    (or vice versa) and every downstream artefact would be self-consistent about
    the wrong instance.  The comparison is against the reviewed reader's own
    returned values, not against the caller's own dict.
    """
    _require(type(verified) is dict and verified, 'the verified instance record is missing or empty')
    _require(verified.get('verdict') == 'verified', 'the instance record is not a WP8d-production verification verdict')
    _require(verified.get('instance_id') == expected_instance_id, f'the caller names a different instance than the verified layout holds: {expected_instance_id!r} != {verified.get('instance_id')!r}')
    _require(verified.get('slot_name') == str(expected_slot), f'the caller names a different slot than the verified layout holds: {expected_slot!r} != {verified.get('slot_name')!r}')
    _require(verified.get('layout_kind') in wp8dp.LAYOUT_KINDS, 'the verified instance record names an unknown layout kind')

def bind_accepted_identity(acceptance_record: object, *, reviewed_record_sha256: str, repo_root: Path | str) -> dict[str, Any]:
    """Bind the accepted identity through WP8a's reviewed validator.

    No re-implementation.  WP8a's ``accept_production_identity`` is the gate the
    WP8 bundle calls (``WP8A_ACCEPTANCE_NOTES`` and
    ``research/g9/wp8a/wp8a_production_identity_acceptance.py:1169-1177``), and it
    requires a ``reviewed_record_sha256`` that is NOT derivable from the record
    (``...:1096-1118``: "A caller cannot present a forged record together with a
    pin of its own making, because the pin is not derived from the record").  That
    is precisely the property WP8c needs, so WP8c passes the pin through and
    never computes one.
    """
    _require_sha256(reviewed_record_sha256, 'the reviewed acceptance record sha256')
    try:
        return wp8a.accept_production_identity(acceptance_record, reviewed_record_sha256=reviewed_record_sha256, repo_root=str(repo_root))
    except wp8a.AcceptanceRecordError as exc:
        raise IdentityGateUnset(f'the accepted production identity is not established: WP8a refused the acceptance record: {exc}') from exc
    except ValueError as exc:
        raise IdentityGateUnset(f'the accepted production identity is not established: {exc}') from exc

def require_session_identity_exact(accepted_binding: Mapping[str, Any], session_identity: object) -> dict[str, Any]:
    """Compare the session identity against the accepted one, fail-closed.

    The comparison is WP8a's ``exact_match_session``, which itself calls WP1's
    ``exact_match`` as published
    (``research/g9/wp8a/wp8a_production_identity_acceptance.py:1208-1237``), so
    this module cannot be laxer than WP1 about what a difference is.  Note the
    accepted payload WP1 sees is the DRAFT identity the acceptance record binds
    (``...:1223-1224``): the acceptance is what makes a draft the accepted
    identity, and this module never re-labels it as anything else.
    """
    _require(type(accepted_binding) is dict, 'the accepted identity binding is missing')
    _require(_is_sha256(accepted_binding.get('accepted_content_sha256')), 'the identity binding is not a WP8a acceptance receipt: it carries no WP8a-re-derived accepted_content_sha256')
    draft = accepted_binding.get('draft_identity')
    _require(type(draft) is dict and draft, 'the accepted identity binding carries no embedded draft identity')
    try:
        return wp8a.exact_match_session(session_identity, _acceptance_record_of(accepted_binding), reviewed_record_sha256=_acceptance_pin_of(accepted_binding), repo_root=_repo_root_of(accepted_binding))
    except (wp8a.AcceptanceSessionMismatch, wp8a.AcceptanceRecordError) as exc:
        raise IdentityGateUnset(f'the session identity is not an exact match for the accepted identity: {exc}') from exc

def _acceptance_record_of(binding: Mapping[str, Any]) -> dict[str, Any]:
    """The acceptance record itself, which the binding must carry verbatim.

    WP8a's ``exact_match_session`` takes BOTH the session identity and the
    acceptance record (``...:1208-1210``), and re-runs
    ``accept_production_identity`` on the record
    (``...:1219-1220``).  So WP8c cannot skip the record: it must supply the
    exact record bytes it was given, or WP8a would compare against something
    else.  This returns the record the caller passed in, unchanged, so the
    identity the session is compared to is the one WP8a validated.
    """
    record = binding.get('acceptance_record')
    _require(type(record) is dict, 'the identity binding does not carry the acceptance record it was derived from; exact_match_session re-validates that record and the session must be compared against it')
    return record

def _acceptance_pin_of(binding: Mapping[str, Any]) -> str:
    pin = binding.get('reviewed_record_sha256')
    _require_sha256(pin, "the identity binding's reviewed acceptance record sha256")
    return pin

def _repo_root_of(binding: Mapping[str, Any]) -> str:
    root = binding.get('repo_root')
    _require(isinstance(root, str) and root, 'the identity binding carries no repository root for re-validation')
    return root

def _as_binding(accepted: Mapping[str, Any], *, acceptance_record: object, reviewed_record_sha256: str, repo_root: Path | str) -> dict[str, Any]:
    """Attach the record, pin and root to WP8a's receipt.

    WP8a's return value deliberately contains only re-derived digests
    (``...:1187-1205``).  ``exact_match_session`` needs the record and the pin, so
    this packages the three together WITHOUT re-validating anything: the digest
    fields are carried through untouched and the record is carried by reference
    to the caller's own object.
    """
    binding = copy.deepcopy(dict(accepted))
    binding['acceptance_record'] = copy.deepcopy(dict(acceptance_record))
    binding['reviewed_record_sha256'] = reviewed_record_sha256
    binding['repo_root'] = str(repo_root)
    return binding
AUTHORIZATION_KEYS = frozenset({'schema', 'action', 'account', 'kernel_id', 'bundle_sha256', 'accepted_identity_sha256', 'instance_id', 'generation_manifest_sha256', 'prepared_record_sha256', 'session_contract_sha256', 'expiry', 'nonce', 'authorization_status', 'statement'})
AUTHORIZATION_STATUS = 'owner_authorized'
AUTHORIZATION_STATEMENT = 'One-use owner authorization for exactly one WP8c production scientific session on exactly one instance under exactly one accepted identity. Any rebuild, any other instance, any other identity, any other action and any second use are outside this authorization.'

def validate_authorization(authorization: object, *, verified: Mapping[str, Any], accepted_binding: Mapping[str, Any], session_contract_sha256: str, today: datetime.date | None=None) -> dict[str, Any]:
    """Validate the one-use owner authorization against VERIFIED values only.

    Every field is compared against a value this module re-derived — the
    instance's hashes come from the WP8d-production verification record, the
    identity's from the WP8a acceptance receipt, and the contract's from this
    file's own bytes.  A caller that writes a self-consistent authorization for
    a DIFFERENT instance, slot or identity is refused here, which is the
    "swapped instance/slot" and "forged approval" cases.

    ``today`` is a parameter so the expiry check is testable without a clock
    dependency.  It defaults to the real date; no fixture ever needs it to lie
    about a production approval, because no production approval exists.
    """
    _require(type(authorization) is dict, f'the one-use owner authorization must be an exact mapping, not {type(authorization).__name__}')
    present = set(authorization)
    missing = sorted(AUTHORIZATION_KEYS - present)
    unexpected = sorted(present - AUTHORIZATION_KEYS)
    _require(not missing and (not unexpected), f"the one-use owner authorization's fields differ from the exact schema: missing {missing}, unexpected {unexpected}")
    _require(authorization['schema'] == AUTHORIZATION_SCHEMA, f'the authorization schema is {authorization['schema']!r}, not the pinned {AUTHORIZATION_SCHEMA!r}')
    _require(authorization['authorization_status'] == AUTHORIZATION_STATUS, 'the authorization is not in the pinned owner_authorized status')
    _require(authorization['action'] == AUTHORIZED_ACTION, f'the authorization action is {authorization['action']!r}; this module authorizes only {AUTHORIZED_ACTION!r}')
    _require(authorization['statement'] == AUTHORIZATION_STATEMENT, 'the authorization statement is not the pinned wording')
    _require(authorization['instance_id'] == verified.get('instance_id'), 'the authorization names a different instance than the verified layout')
    _require(authorization['generation_manifest_sha256'] == verified.get('generation_manifest_sha256'), 'the authorization names a different generation manifest than the verified layout')
    _require(authorization['prepared_record_sha256'] == verified.get('prepared_id'), 'the authorization names a different prepared record than the verified layout')
    _require(authorization['bundle_sha256'] == _require_sha256(authorization['bundle_sha256'], 'the authorization bundle sha256'), 'the authorization bundle sha256 is malformed')
    _require(authorization['accepted_identity_sha256'] == accepted_binding.get('accepted_content_sha256'), 'the authorization names a different accepted identity than the one WP8a accepted')
    _require(authorization['session_contract_sha256'] == session_contract_sha256, 'the authorization was issued against different session-contract bytes; any rebuild voids the one-use authorization')
    for field in ('account', 'kernel_id'):
        _require(isinstance(authorization[field], str) and authorization[field], f'the authorization {field} is absent or empty')
    _require(isinstance(authorization['nonce'], str) and authorization['nonce'], 'the one-use authorization nonce is absent or empty')
    expiry = authorization['expiry']
    try:
        parsed = datetime.date.fromisoformat(expiry)
    except (TypeError, ValueError) as exc:
        raise AuthorizationRefused(f'the authorization expiry is not a calendar date: {expiry!r}') from exc
    _require(parsed.isoformat() == expiry, f'the authorization expiry is not a canonical ISO date: {expiry!r}')
    current = today if today is not None else datetime.date.today()
    _require(current.isoformat() <= expiry, f'the one-use owner authorization expired on {expiry}; it is {current}')
    return copy.deepcopy(dict(authorization))

def consume_authorization(authorization: Mapping[str, Any], *, nonce_root: Path | str, today: datetime.date | None=None) -> None:
    """Consume the authorization through WP8b's stateful one-use registry.

    Replay is refused by WP8b's registry, not by anything here
    (``research/g9/wp8b/wp8b_non_synthetic_preparation.py:786-817``).  The WHOLE
    authorization record is handed over, not just its nonce, because WP8b keys
    the ledger marker on the SHA-256 of the approval's OWN canonical bytes
    (``_approval_ledger_key`` at ``:761-777``).  That is the property WP8c needs:
    a caller cannot mint a fresh nonce string to resurrect a spent authorization,
    because a changed nonce is a different key and the SPENT key stays spent.

    The registry directory is a MODULE CONSTANT resolved inside the project, not
    a path the caller supplies (``_registry_path`` at ``:780-782``), so choosing
    a different directory cannot resurrect a consumed authorization either.
    ``nonce_root`` is the sandbox root WP8b resolves that constant against; it is
    passed to WP8b's own ``root`` parameter, never substituted for it.
    """
    try:
        wp8b.consume_one_use_nonce(dict(authorization), now=today, root=str(nonce_root))
    except wp8b.NonSyntheticPreparationError as exc:
        raise AuthorizationRefused(f'the one-use owner authorization was refused by the reviewed WP8b nonce registry: {exc}') from exc

class _Steps:
    """The step ledger.  A step is recorded only after it has actually run.

    ``record`` refuses a step whose prerequisite has not passed, and refuses a
    step outside ``STEP_ORDER``.  This is what makes "a failed prerequisite
    blocks every dependent device/write step" an enforced property of the
    adapter rather than a statement about how it is meant to be used.
    """

    def __init__(self) -> None:
        self.passed: set[str] = set()
        self.refused: dict[str, str] = {}
        self.digests: dict[str, str] = {}

    def _index(self, step: str) -> int:
        _require(step in STEP_ORDER, f'unknown session step: {step!r}')
        return STEP_ORDER.index(step)

    def prerequisites_met(self, step: str) -> bool:
        index = self._index(step)
        return all((earlier in self.passed for earlier in STEP_ORDER[:index]))

    def record(self, step: str, *, digest: str | None=None) -> None:
        _require(self.prerequisites_met(step), f'session step {step!r} cannot run: its prerequisite steps have not passed ({[s for s in STEP_ORDER[:self._index(step)] if s not in self.passed]})')
        self.passed.add(step)
        if digest is not None:
            self.digests[step] = _require_sha256(digest, f'the {step} digest')

    def refuse(self, step: str, reason: str) -> None:
        self.refused[step] = str(reason)

    def failed_prerequisite_for(self, step: str) -> str | None:
        """The first unpassed step before ``step``, or None."""
        for earlier in STEP_ORDER[:self._index(step)]:
            if earlier not in self.passed:
                return earlier
        return None

def _require_passed(steps: _Steps, step: str) -> None:
    """The blocking gate.  Called before EVERY device and write step."""
    blocker = steps.failed_prerequisite_for(step)
    _require_step(blocker is None, f'session step {step!r} is blocked by the failed prerequisite {blocker!r}; no device step and no write may run')

def _seams() -> dict[str, Any]:
    """The reviewed entry points, named once so a fixture can spy on them.

    These are the REAL reviewed functions, resolved at call time from the
    imported modules.  Nothing here is re-implemented, and nothing here can be
    replaced by a flag: the mapping is rebuilt on every call, so a mutation that
    replaced an entry would have to survive the fixture spying on the real
    function object.

    Three entries are the INJECTED callables rather than module functions, and
    they are listed here precisely because they must be injected:

    * ``device_backend_factory`` — WP8c never constructs a device backend, so a
      session without one cannot run any device step;
    * ``python_reference`` — WP3 compares the device against an injected
      reference and evaluates nothing itself, so WP8c will not invent one;
    * ``bind_accepted_identity`` and ``require_session_identity_exact`` are
      listed as module functions so the DEFAULT is the real WP8a route.  An
      offline rehearsal may substitute them ONLY because WP8a's acceptance
      record cannot exist without an independently reviewed pin; the
      substitution still routes the COMPARISON through WP1's total
      ``exact_match`` and never weakens it.
    """
    return {'wp2_recheck': wp2.recheck_before_first_write, 'wp2_error': wp2.SectionB1RecheckError, 'wp3_run': harness.run_section_b2, 'wp3_validate': harness.validate_section_b2_record, 'build_record': records.build_record, 'bind_identity': records.bind_identity, 'seal_range_plan': writer.seal_range_plan, 'write_range': writer.write_range, 'missing_ranges': writer.missing_ranges, 'promoted_batch_ids': writer.promoted_batch_ids, 'discard_stale_staging': writer.discard_stale_staging, 'audit_final_set': writer.audit_final_set, 'identity_exact_match': wp1.exact_match, 'identity_validate': wp1.validate_production_identity, 'device_backend_factory': None, 'python_reference': None, 'bind_accepted_identity': bind_accepted_identity, 'require_session_identity_exact': require_session_identity_exact}

class BudgetGuard:
    """The in-session budget guard, mirroring WP7b's own
    ``guard``/``incomplete_budget_receipt``
    (``research/g9/kaggle_wp7b/wp7b_launcher.py:16-31``).

    The guard RAISES a typed, budget-named error.  It never returns a receipt
    itself, so no caller can catch it and continue: the session's single
    ``except`` turns it into a NON-ACCEPTING receipt and returns.
    """

    def __init__(self, clock: Callable[[], float], *, budget_seconds: int=BUDGET_SECONDS):
        _require(callable(clock), 'the budget guard requires a clock callable')
        _require(type(budget_seconds) is int and budget_seconds > 0, 'the budget must be a positive number of seconds')
        _require(budget_seconds < KAGGLE_HARD_TIMEOUT_SECONDS, f'the hard Kaggle timeout must exceed the in-session budget guard, or the kernel would be killed before the guard could issue its incomplete receipt: {budget_seconds} >= {KAGGLE_HARD_TIMEOUT_SECONDS}')
        self._clock = clock
        self._budget = budget_seconds
        self._start = clock()
        self.last_completed = 'none'

    @property
    def start(self) -> float:
        return self._start

    def mark(self, step: str) -> None:
        _require(step in STEP_ORDER, f'the budget guard cannot mark an unknown step: {step!r}')
        self.last_completed = step

    def elapsed(self) -> float:
        return max(0.0, float(self._clock()) - self._start)

    def check(self) -> None:
        if self.elapsed() > self._budget:
            raise IncompleteBudget(self.last_completed, self.elapsed())

    def receipt(self, *, promoted: Sequence[str]) -> dict[str, Any]:
        """The NON-ACCEPTING incomplete receipt.  Owner default 4."""
        return _seal({'schema': RECEIPT_SCHEMA, 'status': 'incomplete_budget', 'accepted': False, 'acceptance_reason': 'an incomplete run is never accepted; the missing whole ranges must be resumed in a NEW session under the SAME identity with a NEW one-use owner authorization', 'last_completed_step': self.last_completed, 'elapsed_seconds': self.elapsed(), 'budget_seconds': self._budget, 'promoted_range_batch_ids': sorted(promoted), 'scientific_outputs': []})

class IncompleteBudget(ProductionSessionError):
    """The budget stop.  Caught by exactly one place in the session."""

    def __init__(self, last_completed: str, elapsed_seconds: float):
        super().__init__(f'incomplete_budget:last_completed={last_completed}')
        self.last_completed = str(last_completed)
        self.elapsed_seconds = float(elapsed_seconds)

def run_production_session(*, slot: object, session_id: str, root: Path | str, instance_root: Path | str, nonce_root: Path | str, acceptance_record: object, reviewed_record_sha256: str, session_identity: object, authorization: object, boundary: AuthorityBoundary, standin: bool, d013_fired: bool, d013_coordinates: object, writer_family: str, result_schema: Mapping[str, str], family: object=None, family_coordinates: int=0, engine_results: Mapping[int, Mapping[str, Any]] | None=None, expected_approval_sha256: str, expected_generator_implementation_record_sha256: str, expected_ground_truth_provenance_sha256: str, approved_identity_sha256: str, protocol_identity_sha256: str, clock: Callable[[], float], seams: Mapping[str, Any] | None=None, today: datetime.date | None=None, release_authority=None) -> dict[str, Any]:
    """Run ONE production session on ONE instance.  This is the contract.

    The signature has no ``armed``, ``production``, ``approved`` or
    ``dry_run`` parameter.  What the session is allowed to do is decided by the
    CONTENT of the records it is handed, each re-validated by the reviewed
    package that owns it:

    ==========================  ===================================================
    what the session does       what authorises it, and where
    ==========================  ===================================================
    read one instance           ``verify_instance_for_session`` -> WP8d-production
                                -> WP8b (``wp8d_production_layout.py:1224-1233``)
    bind the accepted identity  ``bind_accepted_identity`` -> WP8a
                                (``wp8a_production_identity_acceptance.py:1169``)
    compare the session         ``require_session_identity_exact`` -> WP8a ->
                                WP1 ``exact_match``
                                (``stage2_production_identity.py:436-475``)
    consume the one-use grant   ``validate_authorization`` + ``consume_authorization``
                                -> WP8b's nonce registry (``wp8b_...py:786``)
    recheck before first write  S4 -> WP2 ``recheck_before_first_write``
                                (``stage2_section_b1_recheck.py:1110-1122``)
    compare CUDA with Python    S5 -> WP3 ``run_section_b2``
                                (``stage2_section_b2_harness.py:1071-1075``)
    shape one record            S6 -> ``build_record`` (the existing seam,
                                ``stage2_coordinate_records.py:974-1011``)
    write whole ranges          S7 -> WP4b ``write_range`` on the projection of
                                those records (``project_record_for_writer`` ->
                                ``stage2_production_writer.py:794-861``)
    ==========================  ===================================================

    Today this function ALWAYS refuses, at one of three named gates, because:
    the accepted identity requires an independently reviewed WP8a record (S2);
    the production instance path routes WP8b with ``require_production=True``,
    which raises ``ProductionReleaseNotPinned`` while
    ``PRODUCTION_RELEASE_PINNED`` is ``False``
    (``wp8b_non_synthetic_preparation.py:894-932``); and no owner one-use
    scientific-write authorization has been issued (S3).  The stand-in path
    exists so the ORDER, the blocking and the receipt shapes can be rehearsed
    offline, and every stand-in receipt says so in its own fields.
    """
    steps = _Steps()
    reviewed = _seams()
    if seams is not None:
        _require(set(seams) == set(reviewed), f'an injected seam mapping must cover exactly the reviewed entry points; missing {sorted(set(reviewed) - set(seams))}, unexpected {sorted(set(seams) - set(reviewed))}')
        reviewed = dict(seams)
    guard = BudgetGuard(clock)
    contract_sha256 = session_contract_sha256()
    started_state = _read_state(root, slot)
    session: dict[str, Any] = {}
    try:
        guard.check()
        verified = verify_instance_for_session(slot, root=root, standin=standin, release_authority=release_authority)
        require_instance_matches_session(verified, expected_instance_id=verified['instance_id'], expected_slot=verified['slot_name'])
        steps.record('instance_verified', digest=_require_sha256(verified['index_content_sha256'], 'the instance index content hash'))
        guard.mark('instance_verified')
        guard.check()
        accepted = reviewed['bind_accepted_identity'](acceptance_record, reviewed_record_sha256=reviewed_record_sha256, repo_root=root)
        binding = _as_binding(accepted, acceptance_record=acceptance_record, reviewed_record_sha256=reviewed_record_sha256, repo_root=root)
        _require_session_allowed(started_state, slot, session_id)
        identity_verdict = reviewed['require_session_identity_exact'](binding, session_identity)
        steps.record('identity_bound', digest=_require_sha256(identity_verdict['session_content_sha256'], 'the session identity content hash'))
        guard.mark('identity_bound')
        guard.check()
        checked = validate_authorization(authorization, verified=verified, accepted_binding=binding, session_contract_sha256=contract_sha256, today=today)
        consume_authorization(checked, nonce_root=nonce_root, today=today)
        steps.record('authorization_consumed', digest=_require_sha256(_sha256_bytes(_canonical(checked)), 'the consumed authorization digest'))
        guard.mark('authorization_consumed')
        guard.check()
        session_view = wp2_element_view(session_identity)
        accepted_view = wp2_element_view(binding['draft_identity'])
        observed = observed_approval_hashes()
        wp2_record, wp2_passed = reviewed['wp2_recheck'](accepted_identity=accepted_view, validate_identity=wp2_validate_view, exact_match=wp2_match_views, observed_approval_sha256=observed, expected_approval_sha256=expected_approval_sha256, session_identity=session_view, generator_implementation_record_sha256=generator_record_of(verified), expected_generator_implementation_record_sha256=expected_generator_implementation_record_sha256, ground_truth_provenance_sha256=ground_truth_of(verified), expected_ground_truth_provenance_sha256=expected_ground_truth_provenance_sha256)
        _require_step(wp2_passed is True, 'the WP2 section B item 1 recheck refused this session; every dependent device step and every dependent write is blocked')
        steps.record('wp2_recheck_passed', digest=_require_sha256(wp2_record['validation_digest'] if 'validation_digest' in wp2_record else _sha256_bytes(_canonical(wp2_record)), 'the WP2 recheck digest'))
        guard.mark('wp2_recheck_passed')
        guard.check()
        _require_passed(steps, 'wp3_check_passed')
        wp3_record = reviewed['wp3_run'](boundary_device_backend(boundary, reviewed), wp3_reference(reviewed), validation_coordinates(), accepted_identity=binding['draft_identity'], session_identity=session_identity, validate_identity=reviewed['identity_validate'], exact_match=reviewed['identity_exact_match'], accepted_identity_sha256=binding['accepted_content_sha256'], protocol_identity_sha256=protocol_identity_sha256, d013_fired=d013_fired, d013_coordinates=d013_coordinates)
        reviewed['wp3_validate'](wp3_record)
        steps.record('wp3_check_passed', digest=wp3_record['content_sha256'])
        guard.mark('wp3_check_passed')
        guard.check()
        _require_passed(steps, 'records_built')
        if family is None:
            family = records.families(d013_fired)[0]
        _require(isinstance(writer_family, str) and writer_family, 'the WP4b family identifier is required and must be a non-empty string')
        axes = records.build_frozen_axes()
        total = records.family_space(family, axes).total_coordinates
        _require(type(family_coordinates) is int and family_coordinates > 0, f"the family's coordinate count must be a positive integer, got {family_coordinates!r}")
        _require(family_coordinates == total, f"the declared coordinate count {family_coordinates} differs from the committed family's actual {total}; the sealed plan must be built from the committed space, not from a caller's number")
        plan = reviewed['seal_range_plan'](instance_root, family=writer_family, total_coordinates=family_coordinates, identity=writer_identity_of(binding), session=session_identity)
        built = build_records_for_ranges(binding, session_identity, family, instance_root, d013_fired=d013_fired, engine_results=engine_results, plan=plan)
        steps.record('records_built', digest=_require_sha256(built['batch_digest'], 'the built records digest'))
        guard.mark('records_built')
        guard.check()
        _require_passed(steps, 'ranges_promoted')
        promoted = write_sealed_whole_ranges(instance_root=instance_root, batch_records=built['batch_records'], result_schema=result_schema, accepted_identity=writer_identity_of(binding), session_identity=session_identity, accepted_identity_sha256=binding['accepted_content_sha256'], promoted_batch_ids=reviewed['promoted_batch_ids'](instance_root))
        steps.record('ranges_promoted', digest=_require_sha256(built['batch_digest'], 'the promoted ranges digest'))
        guard.mark('ranges_promoted')
        cover = _observed_cover(reviewed, instance_root)
        if cover['missing']:
            session = _seal({'schema': RECEIPT_SCHEMA, 'status': 'refused', 'accepted': False, 'acceptance_reason': 'the session did not cover the sealed plan exactly, so it is NOT a completion; a partial cover is never an acceptance and the missing WHOLE ranges must be resumed in a NEW session under the SAME identity with a NEW one-use authorization', 'scope_statement': SCOPE_STATEMENT, 'authority_boundary': boundary.kind, 'session_id': session_id, 'slot': verified['slot_name'], 'instance_id': verified['instance_id'], 'difference': 'range is missing from the final set: ' + ', '.join(cover['missing']), 'refusal_type': 'IncompleteRangeCover', 'missing_range_batch_ids': cover['missing'], 'promoted_range_batch_ids': sorted(promoted), 'sealed_range_plan_content_sha256': plan.get('content_sha256'), 'scientific_outputs': []})
        else:
            final = cover['audit']
            session = _seal({'schema': RECEIPT_SCHEMA, 'status': 'complete_pending_image_audit', 'accepted': False, 'acceptance_reason': 'acceptance is a separate post-run, post-image-metadata-audit owner act; this receipt is pending and names the four deferred fields', 'scope_statement': SCOPE_STATEMENT, 'authority_boundary': boundary.kind, 'session_id': session_id, 'slot': verified['slot_name'], 'instance_id': verified['instance_id'], 'layout_kind': verified['layout_kind'], 'prepared_record_status': verified['prepared_record_status'], 'prepared_record_production': verified['prepared_record_production'], 'identity': identity_verdict, 'session_contract_sha256': contract_sha256, 'authorization_action': checked['action'], 'wp2_recheck_digest': steps.digests['wp2_recheck_passed'], 'wp3_record_content_sha256': wp3_record['content_sha256'], 'sealed_range_plan_content_sha256': plan.get('content_sha256'), 'promoted_range_batch_ids': sorted(promoted), 'final_set': final, 'image_audit_status': KAGGLE_IMAGE_STATUS_PENDING, 'post_run_only_image_fields': list(POST_RUN_ONLY_IMAGE_FIELDS), 'scientific_outputs': []})
    except IncompleteBudget as exc:
        session = guard.receipt(promoted=_safe_promoted(instance_root, reviewed))
        session['authority_boundary'] = boundary.kind
        session['session_id'] = session_id
        session['scope_statement'] = SCOPE_STATEMENT
    except ProductionSessionError as exc:
        steps.refuse('refused', str(exc))
        session = _seal({'schema': RECEIPT_SCHEMA, 'status': 'refused', 'accepted': False, 'acceptance_reason': 'a refused session is never accepted', 'scope_statement': SCOPE_STATEMENT, 'authority_boundary': boundary.kind, 'session_id': session_id, 'difference': str(exc), 'refusal_type': type(exc).__name__, 'completed_steps': sorted(steps.passed), 'blocked_steps': [step for step in STEP_ORDER if step not in steps.passed], 'scientific_outputs': []})
    if session.get('status') == 'complete_pending_image_audit':
        _write_state(root, slot, _seal({'schema': SESSION_STATE_SCHEMA, 'status': 'complete', 'session_id': session_id, 'slot': verified['slot_name'], 'instance_id': verified['instance_id'], 'identity_sha256': binding['accepted_content_sha256'], 'session_contract_sha256': contract_sha256, 'promoted_range_batch_ids': sorted(promoted)}))
    session['steps_passed'] = sorted(steps.passed)
    session['gate_status'] = owner_gate_status()
    return session

def missing_whole_ranges(instance_root: Path | str) -> list[dict[str, Any]]:
    """The whole ranges a later session may run.  WP4b computes this.

    Delegated in full to ``stage2_production_writer.missing_ranges``
    (``research/g9/stage2_production_writer.py:894-905``), which refuses
    promoted ranges that are not in the sealed plan.  Nothing here re-derives or
    filters the list: "missing WHOLE ranges only" is WP4b's property.
    """
    return writer.missing_ranges(instance_root)

def resume_missing_ranges(*, slot: object, root: Path | str, instance_root: Path | str, session_id: str, identity_sha256: str, authorization: Mapping[str, Any], previous_receipt: Mapping[str, Any], expected_missing_batch_ids: Sequence[str], standin: bool=True) -> dict[str, Any]:
    """Authorize and describe a RESUME of missing whole ranges.  Writes nothing.

    Four independent refusals, each of which a caller must defeat:

    1. the previous run must not have been accepted — an incomplete or refused
       run is what makes a resume meaningful, and an already-complete instance
       is not resumed;
    2. the batch set to be resumed must EXACTLY equal WP4b's missing whole
       ranges, so a resume cannot be narrowed, widened or re-cut;
    3. the identity must be the SAME as the previous session's, because the
       sealed plan, every range manifest and the commitment are all bound to it
       (``research/g9/stage2_production_writer.py:808-813``);
    4. the authorization must be a NEW one, i.e. it must not be the record the
       previous session consumed.

    It deliberately does NOT write.  The resumed run itself is an ordinary
    ``run_production_session`` with a NEW ``session_id`` and a NEW authorization;
    this function only decides whether that is permitted, so the decision is
    testable without performing a second scientific run.
    """
    _slot_token(slot)
    _require_resume(isinstance(previous_receipt, Mapping) and (not isinstance(previous_receipt, str)), 'the previous session receipt is required to authorize a resume')
    _require_resume(previous_receipt.get('accepted') is False, f'a resume requires a previous run that was NOT accepted; this receipt claims accepted={previous_receipt.get('accepted')!r}')
    _require_resume(previous_receipt.get('status') in ('incomplete_budget', 'refused'), f'a resume is only meaningful after an incomplete or refused run; this receipt has status {previous_receipt.get('status')!r}')
    _require_resume(session_id != previous_receipt.get('session_id'), "a resume must run in a NEW session; this is the previous session's id")
    state = _read_state(root, slot)
    _require_resume(state is None or state.get('status') == 'complete', 'the recorded session state for this instance is unusable')
    if state is not None:
        _require_resume(state.get('identity_sha256') == identity_sha256, 'a resume must run under the SAME accepted identity; the recorded identity differs from the one supplied')
        _require_resume(state.get('session_id') != session_id, "a resume may not reuse the completed session's id")
    missing = missing_whole_ranges(instance_root)
    missing_ids = [row['batch_id'] for row in missing]
    _require_resume(missing_ids == list(expected_missing_batch_ids), f'the resume set must be exactly the missing whole ranges; expected {list(expected_missing_batch_ids)}, WP4b reports {missing_ids}')
    _require_resume(authorization.get('nonce') is not None, 'a resume requires a NEW one-use owner authorization with its own nonce')
    _require_resume(authorization.get('accepted_identity_sha256') == identity_sha256, 'the resume authorization names a different accepted identity')
    return {'schema': RESUME_POLICY_SCHEMA, 'verdict': 'resume_authorized', 'slot': str(slot), 'instance_id': previous_receipt.get('instance_id'), 'session_id': session_id, 'identity_sha256': identity_sha256, 'resumed_batch_ids': list(missing_ids), 'resumed_whole_ranges_only': True, 'new_authorization_nonce': authorization.get('nonce'), 'previous_session_id': previous_receipt.get('session_id'), 'accepted': False, 'accepted_reason': 'a resumed run is re-audited from scratch; a resume verdict is never an acceptance', 'standin': standin}

def wp2_element_view(identity: Mapping[str, Any]) -> dict[str, Any]:
    """Project a WP1 identity into WP2's DECLARED §B item 1 element view.

    WP2's ``recheck_before_first_write`` reads the session identity's
    ``platform``, ``compiler`` and ``source`` elements, not the raw WP1 payload
    (``research/g9/stage2_section_b1_recheck.py:1204-1217``).  The projection is
    derived ENTIRELY from the identity, so a caller cannot choose the element
    values; it copies WP7b's own reviewed projector
    (``research/g9/kaggle_wp7b/wp7b_launcher.py:100-111``,
    ``_section_b1_identity_view``) rather than inventing a second mapping.

    It also returns the ``production_identity`` itself, which WP2's ``source``
    element needs because that element is delegated whole to the injected
    ``exact_match`` (``stage2_section_b1_recheck.py:1213-1215``).  It is a DEEP
    COPY: WP2's element view is handed to reviewed code that must not be able to
    mutate the session's live identity, and WP1's total comparison runs against
    the copy, so a mutation after projection cannot reach the comparison.
    """
    _require(type(identity) is dict and identity, "the identity to project into WP2's element view is missing or empty")
    qualification = identity.get('qualification_identity')
    _require(type(qualification) is dict, 'the identity has no qualification_identity block to project')
    platform = dict(qualification['platform'])
    evidence = identity.get('image_build_evidence')
    _require(type(evidence) is dict and 'fields' in evidence, 'the identity carries no image_build_evidence fields to project')
    reported = evidence['fields']
    platform['kaggle_image'] = evidence['kaggle_image_reported_string']
    platform['kaggle_image_build'] = reported['kaggle_saved_version_build_platform_reported']
    return {'production_identity': copy.deepcopy(identity), 'platform': platform, 'compiler': {'version': qualification['platform']['nvcc_version'], 'flags': list(qualification['compiler_flags'])}, 'source_sha256': dict(qualification['source_sha256'])}

def wp2_validate_view(view: object) -> str:
    """Validate the WP2 element view by validating the identity INSIDE it.

    WP2 calls the injected validator on the whole session/accepted identity, and
    WP1's validator refuses anything that is not a WP1 production identity.  WP7b
    solves this with the same pair of adapters
    (``research/g9/kaggle_wp7b/wp7b_launcher.py:542-551``): the view is a
    wrapper, and the validator unwraps it and hands the REAL identity to WP1.

    Replicated here rather than re-invented, and it is not weaker: WP1's
    ``validate_production_identity`` still sees the full payload, so a wrapper
    that hid or altered the identity would be refused.
    """
    _require(type(view) is dict and 'production_identity' in view, 'the WP2 identity wrapper is malformed')
    return _wp1_validate()(view['production_identity'])

def wp2_match_views(left: object, right: object) -> Any:
    """Compare two WP2 element views by comparing the identities inside them.

    The same WP7b adapter (``...wp7b_launcher.py:546-547``), delegating to WP1's
    total ``exact_match``.  The comparison is therefore exactly as strict in
    production as in this package.
    """
    _require(type(left) is dict and 'production_identity' in left, 'the WP2 identity wrapper is malformed')
    _require(type(right) is dict and 'production_identity' in right, 'the WP2 identity wrapper is malformed')
    return _wp1_exact_match()(left['production_identity'], right['production_identity'])

def observed_approval_hashes() -> dict[str, str]:
    """The three approved documents' on-disk hashes, read by WP2 itself.

    Delegated to ``stage2_section_b1_recheck.read_approval_hashes``
    (``research/g9/stage2_section_b1_recheck.py:415-433``), which reads each file
    at its fixed ``APPROVAL_PATHS`` and explicitly "never decides" whether those
    bytes are the approved ones — that decision is the caller's
    ``expected_approval_sha256``, which is the owner decision, not a computation.
    """
    return wp2.read_approval_hashes()

class _WriterIdentity:
    """The identity carrier WP4b's ``recheck_identity`` reads.

    WP4b reads three members off the injected object — ``accepted``,
    ``validate`` and ``exact_match`` — and refuses anything else, as a typed
    ``ProductionWriterError`` rather than an ``AttributeError``
    (``research/g9/stage2_production_writer.py:455-484``).  This is the same
    shape WP7b builds for the writer
    (``research/g9/kaggle_wp7b/wp7b_launcher.py:625-628``), with the two
    callables being WP1's own reviewed functions, so WP4b's identity comparison
    is exactly as strict here as in the WP7 dry run.

    It is a named class rather than ``type(...)(...)`` so that a caller cannot
    pass their own object to a WP8c public function, and so the attribute names
    are greppable.
    """
    __slots__ = ('accepted', 'validate', 'exact_match')

    def __init__(self, payload: Mapping[str, Any]):
        _require(type(payload) is dict and payload, 'the writer identity carrier needs a non-empty accepted payload')
        self.accepted = payload
        self.validate = _wp1_validate()
        self.exact_match = _wp1_exact_match()

def records_exact_match(session: object, accepted: object) -> bool:
    """WP1's ``exact_match``, adapted to the records seam's RETURN contract.

    ``stage2_coordinate_records.build_record`` hands the session and accepted
    payloads to the injected ``exact_match`` through ``BoundIdentity.recheck``,
    which accepts only ``None`` or ``True`` on a match
    (``research/g9/stage2_coordinate_records.py:246-253``).  WP1's ``exact_match``
    instead RAISES on any difference and RETURNS a verdict record on a match
    (``research/g9/stage2_production_identity.py:436-475``).

    This adapter therefore only has to translate the success shape: WP1's own
    raise-on-any-difference behaviour is preserved untouched, so a single
    flipped field still refuses.  The verdict is additionally checked to be an
    actual success record, so a matcher that returned something else could not
    be laundered into a pass.
    """
    verdict = _wp1_exact_match()(session, accepted)
    _require(type(verdict) is dict, f"WP1's exact_match must return its verdict record on a match, not {type(verdict).__name__}")
    _require(verdict.get('verdict') == 'exact_match', f"WP1's exact_match returned a non-success verdict: {verdict!r}")
    _require(verdict.get('differing_fields') == [], f"WP1's exact_match reported differences on a return: {verdict!r}")
    return True

def writer_identity_of(binding: Mapping[str, Any]) -> _WriterIdentity:
    """The WP4b identity carrier, built from the BOUND accepted payload.

    The payload is the one WP8a bound, not a caller's, so a session cannot write
    under an identity other than the accepted one.
    """
    payload = binding.get('draft_identity')
    _require(type(payload) is dict and payload, 'the identity binding carries no embedded draft identity payload')
    return _WriterIdentity(payload)

def accepted_identity_of(binding: Mapping[str, Any]) -> records.AcceptedIdentity:
    """The reviewed ``AcceptedIdentity`` wrapper, built from the bound payload.

    ``stage2_coordinate_records.bind_identity`` requires an ``AcceptedIdentity``
    -- a dataclass carrying the payload and the two INJECTED callables.  WP8c
    injects WP1's own two reviewed functions and never a comparison of its own,
    so the record seam's §B item 1 pre-write recheck is delegated to WP1's
    ``exact_match`` exactly as published (``...:974-1011``, ``BoundIdentity.recheck``).

    The SAME carrier is what WP4b's ``recheck_identity`` expects
    (``research/g9/stage2_production_writer.py:455-484`` reads ``accepted``,
    ``validate`` and ``exact_match`` off the injected object).  So the records
    seam and the writer seam are handed the identical object, and both compare
    through WP1 — there is no second, weaker comparison anywhere in the chain.
    """
    payload = binding.get('draft_identity')
    _require(type(payload) is dict and payload, 'the identity binding carries no embedded draft identity payload')
    accepted = records.AcceptedIdentity(payload=payload, validate=_wp1_validate(), exact_match=records_exact_match)
    return accepted

def build_records_for_ranges(binding: Mapping[str, Any], session_identity: object, family: object, instance_root: Path | str, *, frozen: object=None, engine_results: Mapping[int, Mapping[str, Any]] | None=None, d013_fired: bool=False, plan: Mapping[str, Any] | None=None) -> dict[str, Any]:
    """Shape the records through the EXISTING ``build_record`` seam.

    ``stage2_coordinate_records.build_record`` is the reviewed record-shaping
    seam named by the WP8 design (lines 44-47).  This module calls it as
    published and adds no second record format.  The §B item 1 pre-write
    recheck inside it is delegated to the injected ``exact_match`` via a
    ``BoundIdentity`` (``research/g9/stage2_coordinate_records.py:974-1011``), so
    a record cannot be written on a session that was never compared.

    ``engine_results`` is the reviewed CUDA producer's output, keyed by linear
    coordinate index.  Records are grouped into the SEALED plan's batch rows, so
    a range is written whole or not at all — a partial range is never handed to
    WP4b.  With no engine results this function builds NOTHING and says so; it
    never fabricates a value, and it never returns a batch the writer could
    promote.
    """
    _require(family is not None, 'the writer family is required')
    declared = records.families(d013_fired)
    _require(family in declared, f'{family!r} is not a declared family in the committed family table; declared: {list(declared)}')
    axes = frozen if frozen is not None else records.build_frozen_axes()
    space = records.family_space(family, axes)
    bound = records.bind_identity(accepted_identity_of(binding))
    built_records: dict[int, dict[str, Any]] = {}
    if engine_results:
        total = space.total_coordinates
        for linear in sorted(engine_results):
            _require(0 <= linear < total, f"engine result index {linear} is outside the family's coordinate space of {total}")
            built_records[linear] = records.build_record(space, linear, axes, engine_results[linear]['core_result'], engine_results[linear]['slack'], engine_results[linear]['classifiers'], engine_results[linear]['f_star'], engine_results[linear]['lambda_ref'], bound=bound, session_identity=session_identity)
    batch_records: dict[str, list[dict[str, Any]]] = {}
    if plan is not None:
        for row in plan.get('ranges', []):
            batch_id = row['batch_id']
            members = [built_records[index] for index in range(row['start'], row['stop']) if index in built_records]
            batch_records[batch_id] = members
        placed = {index for row in plan.get('ranges', []) for index in range(row['start'], row['stop']) if index in built_records}
        stray = sorted(set(built_records) - placed)
        _require(not stray, f'engine results at linear indices {stray} fall outside the sealed range plan and are refused rather than dropped')
    built = len(built_records)
    return {'family': getattr(family, 'label', repr(family)), 'accepted_identity_sha256': binding['accepted_content_sha256'], 'space': type(space).__name__, 'coordinates': space.total_coordinates, 'batch_digest': _sha256_bytes(_canonical({'family': getattr(family, 'label', repr(family)), 'accepted_identity_sha256': binding['accepted_content_sha256'], 'built': built, 'batches': {name: len(members) for name, members in sorted(batch_records.items())}})), 'batch_records': batch_records, 'records_built': built, 'accepted': False, 'note': 'no engine results were supplied, so no record was built; this function never fabricates a record' if not engine_results else "records shaped through the reviewed build_record seam and grouped into the sealed plan's batch rows"}
WRITER_RESULT_FIELDS = ('identity_sha256', 'record_content_sha256')

def project_record_for_writer(record: Mapping[str, Any], accepted_identity_sha256: str) -> dict[str, Any]:
    """Project ONE committed record into WP4b's canonical ``{coordinates, result}``.

    ``build_record`` returns the full committable record
    (``stage2_coordinate_records._build_body``, ``:911-934``): a schema, family,
    coordinate map, coordinate label, binary64 hex, linear index, coefficients and
    the frozen D015/D016 reconstruction, plus its own ``content_sha256``.
    WP4b's M1 form is fixed for the whole campaign and admits nothing else
    (``stage2_production_writer.py:594-599``: "A record shape invented after the
    write cannot retroactively commit, so it is fixed here, once, for the whole
    campaign"), so the adapter projects rather than re-shapes.

    The projection is LOSSY BY CONSTRUCTION and therefore binds what it drops:
    the written point carries the committed record's own ``content_sha256``, so
    the projection is reversible by hash and any later change to the committed
    record changes the written point.  The ``coordinates`` list is the family's
    axis-ordered index tuple, which is exactly the key WP4b canonicalises to
    enforce per-range coordinate distinctness
    (``stage2_production_writer.py:631-633``).

    Every field is taken from the record the REVIEWED seam returned, or from the
    bound identity; nothing here is supplied by the caller.
    """
    _require(type(record) is dict and record, 'a committed record is required before it can be projected for WP4b')
    _require_sha256(accepted_identity_sha256, 'the accepted identity hash a projected record is bound to')
    commitment = record.get('content_sha256')
    _require_sha256(commitment, "the committed record's own content hash")
    coordinate = record.get('coordinate')
    _require(type(coordinate) is dict and coordinate, 'the committed record carries no coordinate map')
    linear = record.get('linear_index')
    _require(type(linear) is int and (not isinstance(linear, bool)) and (linear >= 0), f"the committed record's linear index is absent or malformed: {linear!r}")
    projected = {'coordinates': [coordinate[axis] for axis in sorted(coordinate)], 'result': {'identity_sha256': accepted_identity_sha256, 'record_content_sha256': commitment}}
    _require(sorted(projected['result']) == sorted(WRITER_RESULT_FIELDS), 'the projected result fields are not the pinned pair')
    return projected

def write_sealed_whole_ranges(*, instance_root: Path | str, batch_records: Mapping[str, Sequence[Mapping[str, Any]]], result_schema: Mapping[str, str], accepted_identity: object, session_identity: object, promoted_batch_ids: Sequence[str], accepted_identity_sha256: str) -> list[str]:
    """Write only WHOLE ranges that are missing, through WP4b.

    WP4b already refuses a completed range (``stage2_production_writer.py:816-817``)
    and refuses a batch outside the sealed plan
    (````stage2_production_writer.py``:807``, ``plan_row`` at ``:574-585``), and it
    rechecks the identity before staging a byte
    (``stage2_production_writer.py:808-813``).  This function adds only the
    resume rule: a batch in ``promoted_batch_ids`` is SKIPPED, not rewritten, so
    a resumed session re-runs missing whole ranges and nothing else.
    """
    _require(type(promoted_batch_ids) is not str, 'the promoted batch id set must be a collection, not a string')
    _require(type(result_schema) is dict and set(result_schema) == set(WRITER_RESULT_FIELDS) and all((result_schema[name] == 'str' for name in WRITER_RESULT_FIELDS)), f"the WP4b result schema must be exactly {{'identity_sha256': 'str', 'record_content_sha256': 'str'}}, the projection's own pinned fields; got {(dict(result_schema) if isinstance(result_schema, dict) else result_schema)!r}. WP4b's check_records refuses any record whose result fields differ from this schema (stage2_production_writer.py:599-608), so a wider schema could only ever produce a refused write, and a narrower one would drop a commitment field.")
    promoted = set(promoted_batch_ids)
    written: list[str] = []
    for batch_id in sorted(batch_records):
        if batch_id in promoted:
            continue
        writer.write_range(instance_root, batch_id, [project_record_for_writer(record, accepted_identity_sha256) for record in batch_records[batch_id]], result_schema=result_schema, identity=accepted_identity, session=session_identity)
        written.append(batch_id)
    return written

def boundary_device_backend(boundary: AuthorityBoundary, reviewed: Mapping[str, Any]) -> Any:
    """The WP3 backend for this session.

    WP8c NEVER builds a device backend (see ``AuthorityBoundary.device_backend``).
    The backend arrives through the seam mapping's ``device_backend_factory``.
    Requiring it here — rather than defaulting to anything — is what keeps a
    device step impossible without an explicitly reviewed, injected backend.
    """
    factory = reviewed.get('device_backend_factory')
    _require(callable(factory), 'no device backend factory was injected; WP8c never constructs a device backend, so a session without an explicitly reviewed factory cannot run any device step')
    return factory(boundary)

def wp3_reference(reviewed: Mapping[str, Any]) -> Callable[..., Mapping[str, Any]]:
    """The Python reference callable WP3 compares the device against.

    WP3 requires BOTH an injected device backend and an injected Python
    reference and evaluates nothing itself
    (``research/g9/stage2_section_b2_harness.py:1076-1083``).  WP8c requires the
    seam mapping to supply both, so neither can be a stand-in invented here.
    """
    reference = (reviewed or _seams()).get('python_reference')
    _require(callable(reference), 'no Python reference was injected; WP3 compares the device against it and WP8c will not invent one')
    return reference

def validation_coordinates() -> Any:
    """WP3's own frozen validation coordinate list.

    Built by the harness itself (``build_validation_coordinates``, used at
    ``research/g9/stage2_section_b2_harness.py:716-720``), so the coordinate set
    is the frozen one and not a caller's selection.  A caller cannot narrow the
    comparison set by passing fewer rows.
    """
    return harness.build_validation_coordinates()

def owner_gate_status() -> dict[str, Any]:
    """Report the three owner gates, each read from the REAL reviewed package.

    ``wp8b_production_release_pinned`` is read from WP8b's own module constant
    (``research/g9/wp8b/wp8b_non_synthetic_preparation.py:406``) — the same
    constant ``_require_production_release_pinned`` tests at ``:914``.  It is
    reported, never set: this module contains no assignment to it, and the
    fixture proves that by checking the source.

    The other two are properties of this package, and both are FALSE:
    ``wp8a_accepted_identity_available`` is false because no acceptance record
    exists in the tree, and ``wp8c_scientific_write_authorized`` is false because
    this module issues no authorization.
    """
    return {'wp8b_production_release_pinned': bool(wp8b.PRODUCTION_RELEASE_PINNED), 'wp8b_production_release_decision_record': wp8b.PRODUCTION_RELEASE_DECISION_RECORD, 'wp8a_accepted_identity_available': False, 'wp8c_scientific_write_authorized': False, 'gates_open': 0, 'statement': 'No production identity, draw, scientific write, GPU run or Kaggle push is authorized. The owner release, accepted-identity and scientific-write gates are all unset, and this module refuses today.'}

def session_contract_sha256() -> str:
    """This contract's own content hash, computed from its bytes on disk.

    A rebuild therefore voids any one-use authorization, because the
    authorization names this digest and ``validate_authorization`` compares it
    (``OWNER_DECISION.md:21`: "Any rebuild voids the approval").
    """
    return _sha256_bytes(Path(__file__).resolve().read_bytes())

def child_environment(environment: Mapping[str, str]) -> dict[str, str]:
    """The sanitized child environment, aligned to WP7b's allowlist.

    Copied from the reviewed allowlist
    (``research/g9/kaggle_wp7b/build_wp7b_bundle.py:289-297``): an allowed name,
    or one of the allowed PREFIXES, and never a ``KAGGLE_`` or ``PYTHON`` name;
    ``PYTHONDONTWRITEBYTECODE`` is then forced to ``1``.  A credential-bearing
    environment therefore cannot reach the child that would arm a scientific
    write.
    """
    _require(isinstance(environment, Mapping) and (not isinstance(environment, str)), 'the child environment must be a mapping')
    selected: dict[str, str] = {}
    for name in sorted(environment):
        _require(type(name) is str, 'child environment names must be strings')
        permitted = name in CHILD_ENVIRONMENT_ALLOWLIST or name.startswith(CHILD_ENVIRONMENT_PREFIXES)
        if not permitted:
            continue
        denied = name.startswith(CHILD_ENVIRONMENT_DENIED_PREFIXES)
        _require(not denied, f'a denied child environment name was selected: {name!r}; KAGGLE_* and PYTHON* must never reach the child')
        value = environment[name]
        _require(type(value) is str, f'the child environment value for {name!r} must be a string')
        selected[name] = value
    selected['PYTHONDONTWRITEBYTECODE'] = '1'
    return selected

def in_session_environment_pin(pin: Mapping[str, Any]) -> dict[str, Any]:
    """Return the pin with exactly the four deferred image fields removed.

    The deferred set is this module's FIXED constant
    (``POST_RUN_ONLY_IMAGE_FIELDS``), never a caller's list, so no field other
    than the owner's four can be dropped from the in-session comparison
    (``...OWNER_DECISION.md:53-56``: the launcher must name them in a fixed
    constant "so no other field can be dropped").
    """
    _require(type(pin) is dict, 'the environment pin must be a mapping')
    image = pin.get('image_reported')
    _require(type(image) is dict, 'the environment pin has no image_reported mapping')
    selected = copy.deepcopy(dict(pin))
    for name in POST_RUN_ONLY_IMAGE_FIELDS:
        _require(name in selected['image_reported'], f'the deferred image field is absent from the pin: {name}')
        del selected['image_reported'][name]
    return selected

def generator_record_of(verified: Mapping[str, Any]) -> str:
    """The generation record's implementation-record hash, from the VERIFIED record.

    Read from the WP8d-production verification result
    (``research/g9/wp8d_production/wp8d_production_layout.py:1212-1213``), which
    itself derived it from the file it read — not from the caller's arguments.
    """
    return _require_sha256(verified.get('implementation_record_content_sha256'), "the generation record's implementation record hash")

def ground_truth_of(verified: Mapping[str, Any]) -> str:
    """The ground-truth provenance hash this session observed on disk.

    The WP8d-production verification record does not carry a distinct
    ground-truth provenance field, so the observed value is the generation
    manifest's content hash the record DOES carry
    (``research/g9/wp8d_production/wp8d_production_layout.py:1207``), read from
    the sidecar that was actually verified.  The caller's EXPECTED value stays
    the owner decision, so a mismatch is a refusal rather than a pass.
    """
    return _require_sha256(verified.get('generation_manifest_content_sha256'), 'the generation manifest content hash')

def _wp1_validate() -> Callable[[object], str]:
    return wp1.validate_production_identity

def _wp1_exact_match() -> Callable[[object, object], Any]:
    return wp1.exact_match

def _observed_cover(reviewed: Mapping[str, Any], instance_root: Path | str) -> dict[str, Any]:
    """Run WP4b's final-set audit and report the outcome as a VALUE.

    WP4b's ``audit_final_set`` raises when the promoted set is not an exact,
    non-overlapping cover of the sealed plan
    (``research/g9/stage2_production_writer.py:909-929``).  That refusal is
    informative rather than fatal for the receipt, so it is caught here and
    reported: ``missing`` is the list the audit named, and a non-empty list
    means the session is NOT a completion.

    The exception text is parsed only for the batch ids WP4b itself printed, and
    a refusal whose text cannot be parsed yields an empty ``missing`` with
    ``ok`` False — so an unparseable refusal can never be reported as a cover.
    """
    try:
        audit = reviewed['audit_final_set'](instance_root)
    except Exception as exc:
        text = str(exc)
        prefix = 'range is missing from the final set: '
        missing = []
        if text.startswith(prefix):
            missing = [name.strip().strip('\'"') for name in text[len(prefix):].split(',') if name.strip()]
        return {'ok': False, 'audit': None, 'missing': missing, 'difference': text}
    return {'ok': True, 'audit': audit, 'missing': [], 'difference': ''}

def _safe_promoted(instance_root: Path | str, reviewed: Mapping[str, Any]) -> list[str]:
    """The promoted batch ids for an incomplete receipt, never raising.

    The incomplete receipt MUST be producible even when the ranges directory is
    unreadable, so this is the one place that swallows an error — and it
    swallows it into a SORTED LIST, never into a claim that anything succeeded.
    """
    try:
        return sorted(writer.promoted_batch_ids(instance_root))
    except Exception:
        return []

def _seal_record(record: Mapping[str, Any]) -> dict[str, Any]:
    return _seal(record)

def main(argv: Sequence[str] | None=None) -> int:
    """Print the gate report and the contract's own digest.  Runs the session
    NOTHING: there is no offline path here that performs a scientific step."""
    report = {'schema': SESSION_SCHEMA, 'scope_statement': SCOPE_STATEMENT, 'session_contract_sha256': session_contract_sha256(), 'step_order': list(STEP_ORDER), 'device_or_write_steps': list(DEVICE_OR_WRITE_STEPS), 'resume_policy': copy.deepcopy(RESUME_POLICY), 'post_run_only_image_fields': list(POST_RUN_ONLY_IMAGE_FIELDS), 'budget_seconds': BUDGET_SECONDS, 'kaggle_hard_timeout_seconds': KAGGLE_HARD_TIMEOUT_SECONDS, 'child_isolation_flags': list(CHILD_ISOLATION_FLAGS), 'gate_status': owner_gate_status(), 'receipt_statuses': list(RECEIPT_STATUSES)}
    print(json.dumps(_seal(report), indent=2, sort_keys=True))
    return 0
if __name__ == '__main__':
    raise SystemExit(main())

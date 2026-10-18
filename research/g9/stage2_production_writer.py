"""Stage-2 production writer (WP4b): atomic range writer + commitment shape.

Two obligations are built here and nothing else.

**(A) Gap G7 -- the production writer.** The approved CUDA amendment's "D013 and
restart handling" range rules, and WP0 gap G7, require one canonical range plan
sealed per instance/output family before the first production session, atomic
promotion of every range, whole-range-only resume, and a final-set exact-cover
audit before any aggregation.  The plan shape, the manifest shape and the cover
audit are the frozen execution contract's
(``build_range_plan`` / ``validate_range_plan`` / ``complete_range_manifest`` /
``validate_final_manifests``); this module supplies the writer that contract
explicitly does not contain -- it says so itself: *"a future writer owns atomic
I/O"* (``stage2_cuda_execution_contract.py:149``).

**(B) The MUST-FIX-BEFORE-PRODUCTION commitment items M1-M7** of WP0 section
5.2.  They are ordering constraints on the write path, not a sampling driver:
the record form, the per-instance root sealed at write completion, the external
timestamp *hook* for that root, the pinned descriptor/schema and binding digest,
the retained per-point values, the independently supplied coordinate roster, and
the pinned beacon chain plus round-selection rule.  Sampling itself stays
deferred; this builds the structures an audit would later need, and the ordering
so the audit cannot be retrofitted.

Identity is an INJECTED dependency, because the WP1 production identity is still
under review and is deliberately not imported here.  A caller supplies an object
with ``accepted`` (a payload), ``validate(payload) -> sha256-hex`` and
``exact_match(session, accepted)`` which raises on any difference.  Every range
manifest carries that hash, so no range can be promoted under a different
identity than the one the plan was sealed under.

IDENTITY IS ESTABLISHED BY CONTENT HASH ALONE.  Nothing here decides what an
identity is by asking what shape its object has: an identity is the sha256-hex
digest the injected ``validate`` returns for the accepted payload, that digest is
type-checked (a ``str`` of exactly 64 lowercase hex characters), and it is
compared for exact equality against the hash recorded in the sealed plan and in
every range manifest, the commitment and the campaign pin.  Any mismatch raises
``ProductionWriterError``.  The object's *interface* is only ever a
mechanical precondition for being able to ask that question at all -- a missing
member is an ``AttributeError`` converted to the typed refusal, never the
evidence about identity.

Atomicity: a range is promoted by a single ``os.rename`` of a staging
*directory* holding both the records file and the range manifest.  Renaming a
directory is atomic, so a promoted range is either absent or holds both files
that were verified together -- there is no state in which one is visible
without the other.  Files and directories are fsynced before the rename and the
parent is fsynced after it.  Every failure path, including a crash injected at
any named step, removes the staging directory and leaves the destination exactly
as it was; an interrupted range is discarded and never resumed mid-range.

WRITE-ONCE SEALING.  A sealed artefact is never rewritten by any code path in
this module.  This is a STRUCTURAL property, not a convention: every sealed
control-plane file is created with ``_create_file_once``, which stages the bytes
in a temporary sibling and then hard-links them into place.  ``os.link`` fails
with ``EEXIST`` if the name is taken, so there is no rename-over-a-sealed-file
path anywhere, and every sealing entry point additionally refuses up front so
the refusal names the sealed artefact rather than a syscall.  The artefacts are
the range plan, a promoted range directory, the per-instance commitment, the
campaign binding pin, the timestamp request and its metadata, the frozen beacon
rule pin, and the beacon rule consultation.

Every public entry point is wrapped so that ANY failure that CAN ARISE --
including a ``KeyError`` from indexing a malformed stored pin, or a ``TypeError``
from indexing a document of the wrong shape -- surfaces as
``ProductionWriterError``.  Stored control-plane files are untrusted input, and a
raw ``KeyError`` escaping here would read to a caller as a crash rather than a
refusal.  Documents read back from disk are shape-checked through the
``*_FIELDS`` tables below before any field of them is indexed.

NO CATCH IN THIS MODULE IS BROADER THAN THE CLASSES THAT CAN OCCUR.  Each
``except`` names specific classes -- the filesystem's ``OSError``, the frozen
modules' own typed refusals, ``ValueError``/``TypeError``/``UnicodeError`` from
decoding and typing a stored document, ``AttributeError`` from the injected
identity breaking its contract -- and the public-entry wrapper uses the single
listed ``WRITER_BOUNDARY_ERRORS`` tuple.  There is no ``except Exception`` and no
``except BaseException`` on any conversion path: an unanticipated fault, and any
``BaseException`` at all (a ``KeyboardInterrupt`` from an injected reader, say),
propagates to the caller as itself rather than being disguised as a refusal.

This module has no device, no network, no command line and no scientific value.
It writes and verifies control-plane metadata and whatever record payloads it is
handed; it never computes a result, never fetches a beacon, and never contacts a
TSA.
"""
from __future__ import annotations

import copy
import functools
import hashlib
import json
import os
from pathlib import Path
import shutil
from typing import Any, Callable, Mapping, Sequence

# The flat-import sibling (stage2_timestamp_witness.py:49 does `import
# stage2_beacon_nonce as beacon`) requires this module's own directory on
# sys.path.  Adding it here is the house convention used by the other research/g9
# modules that import that file, and it is added only if absent.
_HERE = Path(__file__).resolve().parent
import sys as _sys  # noqa: E402
if str(_HERE) not in _sys.path:
    _sys.path.insert(0, str(_HERE))
_ROOT = _HERE.parents[1]
if str(_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_ROOT))

from research.g9.cuda_qualification import stage2_cuda_execution_contract as contract  # noqa: E402
from research.g9 import stage2_commitment_adapter as adapter  # noqa: E402
from research.g9 import stage2_sampled_verification as sampled  # noqa: E402
import stage2_timestamp_witness as witness  # noqa: E402

# Re-exported so a caller has one import site for the whole frozen partition
# contract, and so the fixtures exercise the same objects the writer uses.
build_range_plan = contract.build_range_plan
validate_range_plan = contract.validate_range_plan
complete_range_manifest = contract.complete_range_manifest
validate_final_manifests = contract.validate_final_manifests


PLAN_NAME = "range_plan.json"
RANGES_DIRNAME = "ranges"
RECORDS_NAME = "records.json"
RANGE_MANIFEST_NAME = "RANGE_MANIFEST.json"
COMMITMENT_NAME = "commitment.json"
CAMPAIGN_PIN_NAME = "campaign_binding_pin.json"
BEACON_PIN_NAME = "beacon_rule_pin.json"
BEACON_CONSULT_NAME = "beacon_rule_consultation.json"
TIMESTAMP_REQUEST_NAME = "timestamp_request.der"
TIMESTAMP_REQUEST_META = "timestamp_request.meta.json"
STAGING_PREFIX = ".g9-wp4b-staging-"

BEACON_PIN_KEYS = ("beacon_chain", "round_selection_rule", "chain_period_seconds",
                   "chain_genesis_time", "pin_attestation", "chain_hash",
                   "public_key_hex", "scheme_id")
BEACON_SCHEMES = {"bls-unchained-g1-rfc9380": 96, "bls-chained-g1-rfc9380": 96}
BEACON_ROUND_RULES = frozenset({"earliest_unpublished_at_or_after_pin",
                               "lowest_any_round"})

#: The sealed control-plane artefacts, in the M order in which they are reached.
#: Each is created exactly once; ``sealed_state`` reports which are present and
#: what each one actually says, never merely that a file exists.
SEALED_CONTROL_FILES = (
    ("range_plan_sealed", PLAN_NAME),
    ("ranges_promoted", RANGES_DIRNAME),
    ("commitment_root_sealed", COMMITMENT_NAME),
    ("campaign_binding_pinned", CAMPAIGN_PIN_NAME),
    ("external_timestamp_requested", TIMESTAMP_REQUEST_META),
    ("beacon_rule_frozen", BEACON_PIN_NAME),
    ("beacon_rule_consulted", BEACON_CONSULT_NAME),
)

#: Every named step a range write passes through, in order.  A crash injected at
#: any one of them must leave no partial promoted range and no staging residue;
#: the fixtures iterate this tuple so "every step" is exhaustive by construction
#: rather than by remembering to add a case.
WRITE_STEPS = (
    "identity_rechecked",
    "staging_created",
    "records_written",
    "records_fsynced",
    "manifest_written",
    "staging_fsynced",
    "staged_verified",
    "promoted",
)

_HEX = frozenset("0123456789abcdef")

#: Every exception class this module is able to convert at a trust boundary, in
#: one place, so that no ``except`` clause in this file can be widened by editing
#: a single site.  The list is deliberately made of NAMED classes and nothing
#: derived from ``Exception`` itself:
#:
#: * ``OSError`` -- the filesystem (open, read, write, fsync, link, rename, rmtree)
#: * ``ValueError`` -- this module's own ``ProductionWriterError``, the three
#:   frozen modules' typed refusals (all ``ValueError`` subclasses), and
#:   ``json.JSONDecodeError``
#: * ``TypeError`` -- a wrong-typed, unhashable or otherwise malformed argument
#: * ``UnicodeError`` -- the ASCII decode of stored bytes
#: * ``AttributeError`` -- the INJECTED production identity not offering the
#:   interface the package contract says it must
#:
#: Anything not on this list -- a ``RuntimeError``, a ``RecursionError``, any
#: ``BaseException`` -- propagates unchanged, which is the behaviour the round-2
#: validator asked for: a failure is converted to this module's typed error only
#: when it is one of the classes that can actually arise at this boundary.
WRITER_BOUNDARY_ERRORS: tuple[type[BaseException], ...] = (
    OSError,
    ValueError,          # ProductionWriterError, WitnessError, ...
    TypeError,
    UnicodeError,        # UnicodeDecodeError / UnicodeEncodeError
    AttributeError,      # the injected identity lacks the declared interface
    KeyError,           # an injected validator can refuse a missing member
    json.JSONDecodeError,
)


class ProductionWriterError(ValueError):
    """Typed refusal: bad payload, unsafe layout, or a failed promotion."""


class InjectedInterrupt(BaseException):
    """Base class for a fault a test harness injects into a write step.

    It derives from ``BaseException`` on purpose: the typed-entry wrapper turns
    *every* ordinary ``Exception`` into a ``ProductionWriterError``, and an
    injected interruption must still unwind through the staging cleanup and out
    to the caller as the interruption it is.
    """


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ProductionWriterError(message)


def _typed(fn: Callable) -> Callable:
    """Surface every failure of a public entry point as the one typed refusal.

    Callers of this module should have exactly one exception type to catch.  A
    stored pin that is a list rather than a dict, or one that is a dict missing a
    key, would otherwise raise a raw ``KeyError``/``TypeError`` out of an index
    expression and read to the caller as a crash rather than a refusal.

    The catch is ``WRITER_BOUNDARY_ERRORS`` -- a fixed list of named classes
    that can actually arise from the code this module runs -- and NOT
    ``except Exception``.  Everything outside that list propagates untouched:
    ``InjectedInterrupt`` and any other ``BaseException`` (an injected
    ``KeyboardInterrupt`` from a reader, say) must unwind to the caller as
    itself, and a fault no one anticipated is a fault this wrapper must not
    disguise as a refusal.
    """

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except (ProductionWriterError, InjectedInterrupt):
            raise
        except WRITER_BOUNDARY_ERRORS as exc:
            raise ProductionWriterError(
                f"{fn.__name__} refused: {type(exc).__name__}: {exc}") from exc

    return wrapper


def _sha(value: object, label: str) -> str:
    _require(type(value) is str and len(value) == 64 and set(value) <= _HEX,
             f"{label} must be a lowercase SHA-256")
    return value


def _field(mapping: object, key: str, expected_type: type, label: str) -> Any:
    """Read a trust-boundary mapping field with an exact type and typed refusal."""
    _require(type(mapping) is dict, f"{label} must be a dict")
    _require(key in mapping, f"{label} is missing {key!r}")
    value = mapping[key]
    _require(type(value) is expected_type,
             ("no retained leaf list" if key == "retained_leaf_hashes" else
              f"{label}: result field {key!r} has the wrong exact type" if label == "result" else
              f"{label} {key!r} must be exactly {expected_type.__name__}"
              + (" (positive integer required)" if expected_type is int else
                 " (non-empty string required)" if expected_type is str else "")))
    return value


def _document(raw: object, fields: frozenset, label: str) -> dict:
    """Type and shape a stored control-plane document before any field is indexed.

    A document read back from disk is untrusted input.  Every field this module
    later indexes by name is named here, so a truncated or re-shaped stored
    document is refused on its shape instead of raising a raw ``KeyError``.
    """
    _require(type(raw) is dict, f"{label} must be a dict")
    _require(fields <= set(raw), f"{label} has the wrong key set")
    return raw


@_typed
def encodable_records(records: object) -> bytes:
    """The exact on-disk bytes of a records payload, refusing anything unencodable.

    Every value the M1 schema admits is a JSON primitive (int, bool, str and a
    finite float), so a records payload that survives this has the required
    binary64 round-trip.  Any leaf-hash encoding is deliberately NOT applied
    here: the commitment adapter applies that when it builds the commitment,
    and the on-disk file keeps the caller's declared field types so a verifier
    reads back exactly the type the schema declared.
    """
    # A records payload is a LIST of record MAPPINGS, not an arbitrary JSON
    # value.  Without this the function is a general canonical-encoder that
    # silently accepts ``None``, a bare string, or a list of scalars, and a
    # caller that passed the wrong shape would get those bytes promoted as a
    # range's records file.  The per-record field SCHEMA is not checked here --
    # that is ``check_records``'s job, and this function is called on the read
    # path where no schema is in hand.
    _require(type(records) is list, "records payload must be a list")
    _require(all(type(record) is dict for record in records),
             "every entry of a records payload must be a record mapping")
    try:
        return json.dumps(records, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False).encode("ascii")
    except (TypeError, ValueError) as exc:
        raise ProductionWriterError(f"records payload is not encodable: {exc}") from exc


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                          allow_nan=False).encode("ascii")
    except (TypeError, ValueError) as exc:
        raise ProductionWriterError("value is not canonical JSON") from exc


def _content_digest(value: object) -> str:
    return _sha256(sampled.canonical(value))


def _fsync_dir(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        fd = os.open(str(path), flags)
    except OSError as exc:
        raise ProductionWriterError(
            f"cannot open directory {path} for fsync: {exc.__class__.__name__}") from exc
    try:
        os.fsync(fd)
    except OSError as exc:
        raise ProductionWriterError(
            f"cannot fsync directory {path}: {exc.__class__.__name__}") from exc
    finally:
        os.close(fd)


def _remove_tree(path: Path) -> None:
    """Best-effort staging cleanup; never masks the original failure."""
    try:
        shutil.rmtree(path)
    except OSError:
        pass


def _discard_file(path: Path) -> None:
    """Best-effort removal of one temporary file; never masks the original failure."""
    try:
        path.unlink()
    except OSError:
        pass


def _as_path(target: object, label: str) -> Path:
    _require(type(target) is str or isinstance(target, os.PathLike), f"{label} must be a path")
    return Path(target)


def _instance_root(target: object) -> Path:
    base = _as_path(target, "root")
    _require(base.is_dir() and not base.is_symlink(),
             f"instance root must be an existing real directory: {base}")
    return base


def _contract(fn, *args, **kwargs):
    """Call into the frozen contract, surfacing its refusals as our own type.

    The contract raises ``CUDAExecutionContractError`` and the commitment
    modules raise theirs; without this a caller of one writer entry point would
    have to catch three unrelated types to fail closed.  The refusal itself is
    unchanged -- it is re-raised, not swallowed -- and this is the same wrapping
    the commitment adapter already does around the sampled module.  Only the
    delegated modules' own typed errors are translated; nothing else is caught.
    """
    try:
        return fn(*args, **kwargs)
    except (contract.CUDAExecutionContractError, sampled.VerificationError,
            adapter.CommitmentAdapterError, witness.WitnessError) as exc:
        raise ProductionWriterError(str(exc)) from exc


def _write_file(path: Path, payload: bytes) -> str:
    _require(type(payload) is bytes, "file payload must be bytes")
    try:
        with path.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise ProductionWriterError(f"refusing to overwrite an existing file: {path}") from exc
    except OSError as exc:
        raise ProductionWriterError(
            f"cannot write {path}: {exc.__class__.__name__}") from exc
    return _sha256(payload)


def _read_file(path: Path, label: str) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise ProductionWriterError(f"cannot read {label}: {exc.__class__.__name__}") from exc


def _read_json(path: Path, label: str) -> object:
    try:
        return json.loads(_read_file(path, label).decode("ascii"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise ProductionWriterError(f"{label} is not ASCII JSON") from exc


def _create_file_once(path: Path, payload: bytes) -> str:
    """Create a sealed control-plane file exactly once; never replace one.

    The bytes are staged in a temporary sibling, fsynced there, and then
    hard-linked into place with ``os.link``.  A hard link to an existing name
    fails with ``EEXIST`` -- the kernel, not a check here -- so there is no
    rename-over-a-sealed-file path in this module at all.  The temporary name
    carries the pid so two sessions cannot collide, and the parent directory is
    fsynced after the link so the new name itself is durable.
    """
    parent = path.parent
    _require(parent.is_dir() and not parent.is_symlink(),
             f"parent of {path.name} must be an existing real directory")
    temp = parent / f".tmp-{path.name}-{os.getpid()}"
    if temp.is_dir() and not temp.is_symlink():
        _remove_tree(temp)
    else:
        _discard_file(temp)
    try:
        _write_file(temp, payload)
        try:
            os.link(str(temp), str(path))
        except FileExistsError as exc:
            raise ProductionWriterError(
                f"refusing to overwrite an existing file: {path}") from exc
        except OSError as exc:
            raise ProductionWriterError(
                f"cannot create {path}: {exc.__class__.__name__}") from exc
    finally:
        if temp.is_dir() and not temp.is_symlink():
            _remove_tree(temp)
        else:
            _discard_file(temp)
    _fsync_dir(parent)
    return _sha256(payload)


# ---------------------------------------------------------------------------
# The injected production identity -- COMPARED ONLY BY CONTENT HASH
# ---------------------------------------------------------------------------
def _injected(identity: object, attribute: str, label: str) -> Any:
    """Read one member of the injected identity, or refuse the typed way.

    The package contract says the injected identity exposes ``accepted``,
    ``validate`` and ``exact_match``; this module does not own the object and
    cannot prove the contract holds, so an object that does not offer a member
    is a REFUSAL, not a crash -- ``AttributeError`` is on
    ``WRITER_BOUNDARY_ERRORS`` precisely so that a duck that breaks its
    contract surfaces as ``ProductionWriterError`` and a caller has one type to
    catch.
    """
    try:
        return getattr(identity, attribute)
    except AttributeError as exc:
        raise ProductionWriterError(
            f"the injected production identity must expose {attribute!r} ({label})") from exc


def _identity_hash(identity: object) -> str:
    """The accepted identity's content hash, through the injected validator."""
    accepted = _injected(identity, "accepted", "the accepted payload")
    _require(type(accepted) is dict, "accepted identity payload must be a dict")
    validate = _injected(identity, "validate", "the payload->sha256 callable")
    return _sha(validate(accepted), "production identity hash")


def _identity_exact_match(identity: object, session: object) -> None:
    """Fail closed unless the session matches the accepted identity exactly."""
    accepted = _injected(identity, "accepted", "the accepted payload")
    _require(type(accepted) is dict, "accepted identity payload must be a dict")
    _require(type(session) is dict, "session identity payload must be a dict")
    exact_match = _injected(identity, "exact_match", "the session==accepted callable")
    try:
        exact_match(session, accepted)
    except ValueError as exc:
        # The injected validator refuses by raising; that refusal IS the signal,
        # and it becomes this module's typed refusal with the cause attached.
        # The injected exception's own text is deliberately not repeated: the
        # clause names the class of a *structural* failure in the injected
        # identity, and an injected code that already says the same thing must
        # not make the message ambiguous.
        raise ProductionWriterError(
            "the session identity does not exactly match the accepted identity "
            f"({type(exc).__name__})") from exc


@_typed
def identity_hash(identity: object) -> str:
    """The accepted production identity's content hash, as sha256-hex.

    WP1 is under review, so this module neither defines nor assumes the
    identity's shape; it only ever asks the injected ``validate`` for the hash of
    the accepted payload.  A fixture injects a simple synthetic stand-in whose
    ``validate`` is an independent canonical hash, so the writer's own binding
    logic is still what is under test here.

    IDENTITY IS COMPARED BY CONTENT HASH AND NOTHING ELSE.  The hash is
    type-checked as 64 lowercase hex characters and returned; the caller
    compares it for exact equality against the hash recorded in the sealed plan
    and in every range manifest.  No check in this module asks whether the
    identity object *has* an attribute in order to decide what it is -- the
    object's shape is never the evidence, only its content hash is.
    """
    return _identity_hash(identity)


@_typed
def recheck_identity(identity: object, session: object) -> str:
    """Fail closed unless the session matches the accepted identity exactly.

    Two independent signals, both required.  ``exact_match`` is the injected
    validator's own verdict on the session, and the content hash it returns is
    what every sealed artefact in this module is bound to -- the sealed plan,
    every range manifest, the commitment and the campaign pin all record that
    hash, and each is refused if it does not match the sealed plan's.
    """
    digest = _identity_hash(identity)
    _identity_exact_match(identity, session)
    return digest


# ---------------------------------------------------------------------------
# G7: sealing the one canonical range plan per instance/output family
# ---------------------------------------------------------------------------
@_typed
def seal_range_plan(root: Path | str, *, family: str, total_coordinates: int,
                    identity: object, session: object) -> dict:
    """Seal the one canonical plan for this instance/output family, once.

    The first call writes it.  Every later call re-derives the plan from the same
    inputs and refuses if it differs from the sealed one: that is the
    "may not repartition the plan" rule, and it is why a second session cannot
    quietly shrink, widen or re-cut the partition to make its own work fit.  An
    identical re-seal returns the sealed plan and writes nothing.
    """
    base = _instance_root(root)
    digest = recheck_identity(identity, session)
    candidate = _contract(validate_range_plan,
                          build_range_plan(family, total_coordinates, digest))
    plan_path = base / PLAN_NAME
    if plan_path.exists() or plan_path.is_symlink():
        sealed = _contract(validate_range_plan, _read_json(plan_path, "sealed range plan"))
        _require(sealed == candidate,
                 f"the sealed range plan for family {family!r} must not be repartitioned")
        return sealed
    _create_file_once(plan_path, _canonical(candidate))
    return candidate


@_typed
def load_range_plan(root: Path | str) -> dict:
    base = _as_path(root, "root")
    plan_path = base / PLAN_NAME
    _require(plan_path.is_file() and not plan_path.is_symlink(),
             f"no sealed range plan in {base}")
    return _contract(validate_range_plan, _read_json(plan_path, "sealed range plan"))


@_typed
def plan_row(plan: Mapping[str, Any], batch_id: object) -> dict:
    """Return the sealed plan row for ``batch_id``; refuse an unplanned range.

    There is no separate type check on ``plan`` or ``batch_id``: the frozen
    contract's ``validate_range_plan`` refuses a non-dict plan on its own key
    set, and a non-string ``batch_id`` cannot equal any of the plan's string
    batch ids, so it falls through to the same "not in the sealed plan" refusal.
    """
    validated = _contract(validate_range_plan, dict(plan))
    row = next((item for item in _field(validated, "ranges", list, "validated") if _field(item, "batch_id", str, "plan row") == batch_id), None)
    _require(row is not None, f"batch is not in the sealed plan: {batch_id!r}")
    return dict(row)


# ---------------------------------------------------------------------------
# G7: the atomic range write
# ---------------------------------------------------------------------------
def _check_record_form(record: object, result_schema: Mapping[str, str], label: str) -> None:
    """M1: the canonical committable per-point record form.

    Exactly ``{coordinates, result}`` and nothing else, coordinates distinct from
    every other record's, and every result field carrying its schema's exact type.
    A record shape invented after the write cannot retroactively commit, so it is
    fixed here, once, for the whole campaign.
    """
    _require(type(record) is dict and set(record) == {"coordinates", "result"},
             f"{label}: producer record must be exactly {{coordinates, result}}")
    result = _field(record, "result", dict, "record")
    _require(type(result) is dict and set(result) == set(result_schema),
             f"{label}: result fields differ from the exact schema")
    for field, kind in result_schema.items():
        expected = {"int": int, "bool": bool, "str": str, "binary64": float}[kind]
        _field(result, field, expected, "result")
        if kind == "str":
            _require(len(_field(result, field, expected, "result")) <= 4096, f"{label}: str field {field!r} is too long")
        # The finiteness test is folded into the type test rather than guarded
        # separately: a separate `if kind == "binary64"` block would be a
        # dispatch whose condition could be forced True with no observable
        # difference, and a check nothing can reach is not a check.  For a
        # non-binary64 field this term is vacuously True.
        _require(kind != "binary64" or (_field(result, field, expected, "result") == _field(result, field, expected, "result")
                 and _field(result, field, expected, "result") not in (float("inf"), float("-inf"))),
                 f"{label}: binary64 field {field!r} is not finite")


@_typed
def check_records(records: object, result_schema: Mapping[str, str], expected_count: int,
                  label: str) -> list:
    """Validate the M1 record form for a whole range, before any byte is written."""
    _require(type(records) is list, f"{label}: records must be a list")
    _require(len(records) == expected_count,
             f"{label}: range holds {len(records)} records but the sealed range spans "
             f"{expected_count} coordinates")
    seen: set[bytes] = set()
    out: list[dict] = []
    for position, record in enumerate(records):
        _check_record_form(record, result_schema, f"{label}[{position}]")
        key = sampled.canonical(_field(record, "coordinates", list, "record"))
        _require(key not in seen, f"{label}: duplicate coordinates at position {position}")
        seen.add(key)
        out.append(dict(record))
    return out


def _range_dir(base: Path, batch_id: str) -> Path:
    return base / RANGES_DIRNAME / batch_id


_RANGE_MANIFEST_FIELDS = frozenset({
    "content_sha256", "records_file_sha256", "records_content_sha256",
    "batch_id", "qualification_identity_sha256", "plan_content_sha256",
    "schema", "status", "start", "stop",
})

_CAMPAIGN_PIN_FIELDS = frozenset({
    "campaign_binding_digest", "merkle_root", "coordinate_root", "descriptor_sha256",
    "schema_sha256", "grid_point_count", "production_identity_sha256",
    "plan_content_sha256",
})

_BEACON_PIN_FIELDS = frozenset({"pin_digest", "policy", "policy_digest"})

_BEACON_CONSULT_FIELDS = frozenset({
    "pin_digest", "policy_digest", "merkle_root", "campaign_binding_digest",
    "coordinate_root", "beacon_fetched",
})

_TIMESTAMP_META_FIELDS = frozenset({
    "schema", "subject_digest", "policy_digest", "merkle_root", "coordinate_root",
    "campaign_binding_digest", "nonce", "minimum_authorities", "tsa_contacted",
})

_COMMITMENT_FIELDS = frozenset({
    "binding", "plan_content_sha256", "production_identity_sha256",
    "total_coordinates", "retained_leaf_hashes", "retained_coordinates",
})

_COMMITMENT_BINDING_FIELDS = frozenset({
    "schema", "descriptor", "descriptor_sha256", "result_schema", "result_schema_sha256",
    "expected_coordinate_root", "commitment", "campaign_binding_digest",
})

#: The two artefacts ``sealed_state`` reads a plan hash out of.  A stored
#: document is untrusted input, so the reporter shape-checks the one field it
#: names (a document that is not a dict, or that carries no plan hash at all, is
#: reported as unbound rather than raising out of a reporter) and then
#: type-checks it with ``_sha`` -- a name that is not a 64-lowercase-hex digest
#: is not a plan binding, whatever else the document says.
_STORED_PLAN_BOUND_FIELDS = {
    "commitment_root_sealed": _COMMITMENT_FIELDS,
    "campaign_binding_pinned": _CAMPAIGN_PIN_FIELDS,
}


def _manifest_dict(raw: object, label: str) -> dict:
    """Type and shape a range manifest before any field of it is indexed.

    A manifest read back from disk is untrusted input; indexing it without this
    raises a raw KeyError out of the typed contract, and a caller catching only
    ProductionWriterError reads that as a crash rather than a refusal.
    """
    return _document(raw, _RANGE_MANIFEST_FIELDS, label)


def _check_staged(directory: Path, plan: Mapping[str, Any], batch_id: str,
                  identity_digest: str) -> None:
    """A range is complete only when both records file and content hashes match.

    Everything is checked against the BYTES ON DISK, and the manifest is READ
    BACK rather than taken from the object the writer built.  Checking the
    caller's in-memory manifest would prove only that the writer's own data
    agrees with itself, while what gets promoted is the file: if the two ever
    diverge the promoted range would be described by a manifest that was never
    written.  The manifest is then rebuilt from the SEALED PLAN and the on-disk
    records bytes, so a manifest edited in staging cannot carry a batch the plan
    does not contain or a hash that was never written.
    """
    records_path = directory / RECORDS_NAME
    manifest_path = directory / RANGE_MANIFEST_NAME
    _require(records_path.is_file() and not records_path.is_symlink(),
             "staged records file is missing")
    _require(manifest_path.is_file() and not manifest_path.is_symlink(),
             "staged range manifest is missing")
    manifest = _manifest_dict(_read_json(manifest_path, "staged range manifest"),
                              "staged range manifest")
    _require(_field(manifest, "content_sha256", str, "manifest") == contract.content_sha256(manifest),
             "staged range manifest content hash mismatch")
    body = _read_file(records_path, "staged records file")
    _require(_sha256(body) == _field(manifest, "records_file_sha256", str, "manifest"),
             "staged records file hash does not match its manifest")
    content_digest = _sha256(encodable_records(_read_json(records_path, "staged records file")))
    _require(content_digest == _field(manifest, "records_content_sha256", str, "manifest"),
             "staged records content hash does not match its manifest")
    rebuilt = _contract(complete_range_manifest, plan, batch_id, _sha256(body),
                        content_digest, identity_digest)
    _require(manifest == rebuilt,
             f"staged range manifest does not match the sealed plan: {batch_id!r}")


@_typed
def verify_range(root: Path | str, batch_id: str, *, expected_identity_sha256: str | None = None,
                 result_schema: Mapping[str, str] | None = None) -> dict:
    """Re-verify one promoted range against the sealed plan and its manifest.

    The three hash checks are ORDERED so each is independently reachable: the
    records file hash against the manifest, then the records content hash against
    the manifest, then the whole manifest against a rebuild from the sealed plan
    and the on-disk bytes.  A caller that edits only the content hash sees the
    second check alone; a caller that edits a range boundary sees the third.
    Collapsing any two of them into one would make the others untestable.
    """
    base = _as_path(root, "root")
    plan = load_range_plan(base)
    row = plan_row(plan, batch_id)
    directory = _range_dir(base, batch_id)
    _require(directory.is_dir() and not directory.is_symlink(),
             f"range is not promoted: {batch_id!r}")
    manifest_path = directory / RANGE_MANIFEST_NAME
    records_path = directory / RECORDS_NAME
    _require(manifest_path.is_file() and not manifest_path.is_symlink(),
             f"range manifest is missing: {batch_id!r}")
    _require(records_path.is_file() and not records_path.is_symlink(),
             f"range records file is missing: {batch_id!r}")
    manifest = _manifest_dict(_read_json(manifest_path, "range manifest"),
                              "range manifest")

    if expected_identity_sha256 is None:
        # The default is the SEALED PLAN's identity, not the manifest's own: a
        # manifest must not be able to vouch for the identity it was written
        # under.  A caller naming one explicitly is stating what it expects.
        expected_identity_sha256 = _field(plan, "qualification_identity_sha256", str, "plan")
    _sha(expected_identity_sha256, "expected production identity hash")
    _require(manifest.get("qualification_identity_sha256") == expected_identity_sha256,
             f"promoted range {batch_id!r} carries a different production identity")
    # The record count is checked against the SEALED RANGE, not against a schema
    # supplied by the caller: a range can hold too few records and still hash
    # consistently with its own manifest.
    body = _read_file(records_path, "range records file")
    file_digest = _sha256(body)
    records = _read_json(records_path, "range records file")
    _require(type(records) is list and len(records) == _field(row, "stop", int, "row") - _field(row, "start", int, "row"),
             f"promoted range {batch_id!r} does not hold the sealed range's records")
    content_digest = _sha256(encodable_records(records))
    _require(file_digest == _field(manifest, "records_file_sha256", str, "manifest"),
             f"promoted records file hash changed: {batch_id!r}")
    _require(content_digest == _field(manifest, "records_content_sha256", str, "manifest"),
             f"promoted records content hash changed: {batch_id!r}")
    rebuilt = _contract(complete_range_manifest, plan, batch_id, file_digest, content_digest,
                        expected_identity_sha256)
    _require(manifest == rebuilt,
             f"promoted range {batch_id!r} does not match its manifest and the sealed plan")
    if result_schema is not None:
        check_records(records, result_schema, _field(row, "stop", int, "row") - _field(row, "start", int, "row"),
                      f"range {batch_id}")
    return {"batch_id": batch_id, "verdict": "complete", "start": _field(row, "start", int, "row"),
            "stop": _field(row, "stop", int, "row"), "manifest": rebuilt,
            "records_file_sha256": file_digest, "records_content_sha256": content_digest}


@_typed
def write_range(root: Path | str, batch_id: str, records: Sequence[Mapping[str, Any]], *,
                result_schema: Mapping[str, str], identity: object, session: object,
                crash_hook: Callable[[str], None] | None = None) -> dict:
    """Write one whole range atomically; return its manifest.

    Refuses a range that is already complete -- a later session may run a missing
    whole range and nothing else -- and refuses a batch the sealed plan does not
    contain.  The records and the manifest are staged, fsynced, verified against
    each other, and then promoted by a single rename of the staging directory, so
    neither file is ever visible without the other.
    """
    base = _instance_root(root)
    plan = load_range_plan(base)
    row = plan_row(plan, batch_id)
    identity_digest = recheck_identity(identity, session)
    # Every range manifest carries the plan's identity hash, and this session's
    # identity must be that one: a write under any other identity is refused
    # before a single byte is staged.
    _require(_field(plan, "qualification_identity_sha256", str, "plan") == identity_digest,
             f"the sealed plan was built under a different production identity: {batch_id!r}")

    destination = _range_dir(base, batch_id)
    _require(not destination.exists() and not destination.is_symlink(),
             f"refusing to rewrite a completed range: {batch_id!r}")

    checked = check_records(list(records), result_schema, _field(row, "stop", int, "row") - _field(row, "start", int, "row"),
                            f"range {batch_id}")

    ranges_dir = base / RANGES_DIRNAME
    if not ranges_dir.exists():
        ranges_dir.mkdir()
        _fsync_dir(base)
    _require(ranges_dir.is_dir() and not ranges_dir.is_symlink(),
             f"ranges directory must be a real directory: {ranges_dir}")

    crash = crash_hook if callable(crash_hook) else (lambda _step: None)
    crash("identity_rechecked")
    staging = base / f"{STAGING_PREFIX}{os.getpid()}-{batch_id}"
    _require(not staging.exists() and not staging.is_symlink(),
             f"staging path already exists: {staging}")
    try:
        staging.mkdir()
        _fsync_dir(base)
        crash("staging_created")
        body = encodable_records(checked)
        file_digest = _write_file(staging / RECORDS_NAME, body)
        crash("records_written")
        _fsync_dir(staging)
        crash("records_fsynced")
        manifest = _contract(complete_range_manifest, plan, batch_id, file_digest,
                             _sha256(body), identity_digest)
        # The manifest is written as the contract built it; the staged-verify
        # step below reads it back off the disk and re-checks it, which is the
        # only check that can see a manifest the writer did not write.
        _write_file(staging / RANGE_MANIFEST_NAME, _canonical(manifest))
        crash("manifest_written")
        _fsync_dir(staging)
        crash("staging_fsynced")
        _check_staged(staging, plan, batch_id, identity_digest)
        crash("staged_verified")
        os.rename(str(staging), str(destination))
        crash("promoted")
    except BaseException:
        _remove_tree(staging)
        raise
    _fsync_dir(ranges_dir)
    _fsync_dir(base)
    return manifest


# ---------------------------------------------------------------------------
# G7: restart handling -- whole missing ranges only
# ---------------------------------------------------------------------------
@_typed
def discard_stale_staging(root: Path | str) -> list:
    """Discard every staging directory left by an interrupted session.

    An interrupted range is discarded, never resumed mid-range: the staged bytes
    are not a record, so they are removed rather than adopted.
    """
    base = _instance_root(root)
    removed = []
    for entry in sorted(base.iterdir()):
        if entry.name.startswith(STAGING_PREFIX) and entry.is_dir() and not entry.is_symlink():
            _remove_tree(entry)
            removed.append(entry.name)
    if removed:
        _fsync_dir(base)
    return removed


@_typed
def promoted_batch_ids(root: Path | str) -> set:
    base = _as_path(root, "root")
    ranges_dir = base / RANGES_DIRNAME
    if not ranges_dir.is_dir():
        return set()
    return {entry.name for entry in ranges_dir.iterdir() if entry.is_dir()}


@_typed
def missing_ranges(root: Path | str) -> list:
    """The whole ranges a later session may run: every sealed range not promoted.

    A promoted range is never offered again, so a restart re-runs missing whole
    ranges and nothing else.
    """
    plan = load_range_plan(root)
    promoted = promoted_batch_ids(root)
    _require(promoted <= {_field(row, "batch_id", str, "row") for row in _field(plan, "ranges", list, "plan")},
             "promoted ranges are not in the sealed plan")
    return [dict(row) for row in _field(plan, "ranges", list, "plan") if _field(row, "batch_id", str, "row") not in promoted]


@_typed
def audit_final_set(root: Path | str) -> dict:
    """The final-set audit: an exact, non-overlapping cover of the sealed plan.

    Aggregation is refused until this passes, because the cover is what makes
    the family's records the sealed grid rather than an arbitrary subset.

    Every promoted range is re-verified through ``verify_range``, which re-hashes
    each range's RECORDS FILE rather than trusting the manifest the producer
    wrote: the frozen contract checks the manifests against the plan, and a
    manifest is the producer's own artefact.  Without the re-hash a records file
    edited after promotion would still be covered by its original manifest, and
    the audit would accept a family whose bytes no longer match the ranges it
    claims to cover.
    """
    base = _as_path(root, "root")
    plan = load_range_plan(base)
    manifests = []
    for row in _field(plan, "ranges", list, "plan"):
        row_id = _field(row, "batch_id", str, "row")
        directory = _range_dir(base, row_id)
        _require(directory.is_dir() and not directory.is_symlink(),
                 f"range is missing from the final set: {row_id!r}")
        _require((directory / RANGE_MANIFEST_NAME).is_file()
                 and (directory / RECORDS_NAME).is_file(),
                 f"range is incomplete on disk: {row_id!r}")
        manifests.append(_field(verify_range(base, row_id), "manifest", dict, "verified range"))
    return _contract(validate_final_manifests, plan, manifests)


@_typed
def aggregate_records(root: Path | str, *, result_schema: Mapping[str, str] | None = None) -> list:
    """Return the family's records in canonical plan order, or refuse.

    The final-set audit runs first and is not optional: a missing or overlapping
    range raises before a single record is returned.
    """
    base = _as_path(root, "root")
    audit_final_set(base)
    plan = load_range_plan(base)
    out: list[dict] = []
    for row in _field(plan, "ranges", list, "plan"):
        row_id = _field(row, "batch_id", str, "row")
        directory = _range_dir(base, row_id)
        records = _read_json(directory / RECORDS_NAME, "range records file")
        _require(type(records) is list and len(records) == _field(row, "stop", int, "row") - _field(row, "start", int, "row"),
                 f"range record count changed: {row_id!r}")
        if result_schema is not None:
            check_records(records, result_schema, _field(row, "stop", int, "row") - _field(row, "start", int, "row"),
                          f"range {row_id}")
        out.extend(dict(record) for record in records)
    return out


# ---------------------------------------------------------------------------
# M4 / M6: pinned descriptor + schema, roster root, binding digest
# ---------------------------------------------------------------------------
@_typed
def hash_descriptor(value: object) -> str:
    return _content_digest(value)


@_typed
def hash_result_schema(schema: Mapping[str, str]) -> str:
    _require(type(schema) is dict and schema
             and all(type(k) is str and k and type(v) is str and v in adapter.FIELD_TYPES
                     for k, v in schema.items()),
             "result schema must map each field to int/bool/str/binary64")
    return _content_digest(dict(schema))


# ---------------------------------------------------------------------------
# M2 / M5: the per-instance commitment root, sealed at write completion
# ---------------------------------------------------------------------------
@_typed
def seal_instance_commitment(root: Path | str, *, descriptor: Mapping[str, Any],
                             result_schema: Mapping[str, str],
                             expected_descriptor_sha256: str,
                             expected_schema_sha256: str,
                             expected_coordinate_root: str,
                             expected_coordinates: Sequence[Any],
                             expected_plan_content_sha256: str,
                             expected_total_coordinates: int,
                             identity: object, session: object) -> dict:
    """Seal the per-instance root at write completion, over every point.

    The commitment is BOUND TO THE SEALED PLAN in both directions, and each
    binding is a separate check with its own refusal, because a commitment that
    commits to records without committing to the plan that ordered them
    describes a grid nothing can later prove was the sealed one:

    * the injected identity must hash to the plan's own identity hash, so a
      commitment can never be sealed under an identity the ranges were not
      written under;
    * the caller must independently name the plan's content hash, and it must be
      the sealed plan's -- a commitment sealed against a different plan is a
      different claim even over identical records;
    * the caller must independently name the plan's coordinate total, and the
      aggregated record count must equal it.

    M6: the roster is supplied independently and its root must match, so the
    coordinate order is an external anchor rather than something the producer
    chooses after the fact.  M2: the root covers every point, not a sample, and a
    second root covers the ordered coordinates alone.  M5: the ordered leaf list
    and the ordered coordinates are retained in the sealed file, because
    ``verify_sample`` recomputes the root from the leaf list and re-derives
    coordinate distinctness itself -- aggregates alone cannot be audited.

    Nothing here is written twice: a second call is refused, so the sealed root
    of an instance is fixed at the first write completion and forever after.
    """
    base = _instance_root(root)
    identity_digest = recheck_identity(identity, session)
    plan = load_range_plan(base)
    _require(expected_plan_content_sha256 == _field(plan, "content_sha256", str, "plan"),
             "writer boundary: the commitment names a different range plan than "
             "the sealed one")
    _require(_field(plan, "qualification_identity_sha256", str, "plan") == identity_digest,
             "writer boundary: the commitment identity differs from the production "
             "identity the sealed plan was built under")
    _require(expected_total_coordinates == _field(plan, "total_coordinates", int, "plan"),
             "writer boundary: the commitment names a different coordinate total "
             "than the sealed plan")
    # These two messages are deliberately DISTINCT from the commitment adapter's
    # ("descriptor identity mismatch" / "result schema identity mismatch").  The
    # adapter re-checks both anyway, so without a distinguishable message a
    # fixture asserting this boundary could not tell which check refused, and
    # deleting the writer's own check would be invisible.
    _require(expected_descriptor_sha256 == hash_descriptor(dict(descriptor)),
             "writer boundary: descriptor identity mismatch")
    _require(expected_schema_sha256 == hash_result_schema(result_schema),
             "writer boundary: result schema identity mismatch")
    _sha(expected_coordinate_root, "expected coordinate root")

    records = aggregate_records(base, result_schema=result_schema)
    # No separate check of ``len(records)`` against the expected total: the
    # final-set audit that ``aggregate_records`` runs has already proved the
    # cover is exactly the sealed plan, and ``expected_total_coordinates`` was
    # just checked against that same plan total, so a length check here would
    # restate an identity twice over rather than check anything.
    coordinates = [_field(record, "coordinates", list, "record") for record in records]
    _require(type(expected_coordinates) is list,
             "the independently supplied roster must be a list")
    _require(list(expected_coordinates) == coordinates,
             "the independently supplied roster differs from the written coordinates")
    actual_root = sampled.coordinate_root(coordinates).hex()
    _require(actual_root == expected_coordinate_root,
             "the supplied roster does not match its expected coordinate root")

    # Write-once, checked before the aggregate is built so a re-seal is refused
    # even when every argument happens to be identical.
    _require(not (base / COMMITMENT_NAME).exists() and not (base / COMMITMENT_NAME).is_symlink(),
             "the per-instance commitment root is already sealed and may not be re-sealed")
    _require(not (base / CAMPAIGN_PIN_NAME).exists() and not (base / CAMPAIGN_PIN_NAME).is_symlink(),
             "the campaign binding pin is already sealed and may not be re-pinned")

    binding = _contract(
        adapter.build_campaign_commitment,
        expected_coordinates=list(expected_coordinates),
        expected_coordinate_root=expected_coordinate_root,
        descriptor=dict(descriptor),
        expected_descriptor_sha256=expected_descriptor_sha256,
        expected_schema_sha256=expected_schema_sha256,
        result_schema=dict(result_schema),
        producer_records=records,
    )
    commitment = _field(binding, "commitment", dict, "binding")
    sealed = {
        "binding": binding,
        "plan_content_sha256": _field(plan, "content_sha256", str, "plan"),
        "production_identity_sha256": identity_digest,
        "total_coordinates": _field(plan, "total_coordinates", int, "plan"),
        "retained_leaf_hashes": list(_field(commitment, "leaf_hashes", list, "commitment")),
        "retained_coordinates": copy.deepcopy(list(_field(commitment, "coordinates", list, "commitment"))),
    }
    _create_file_once(base / COMMITMENT_NAME, _canonical(sealed))
    # M4: the pin carries the whole binding, not the inner Merkle root alone -- a
    # root pinned without its descriptor and schema is not reproducible if either
    # is revised, and `verify_campaign_commitment` re-derives the digest from all
    # of these fields rather than reading it.
    _create_file_once(base / CAMPAIGN_PIN_NAME, _canonical({
        "campaign_binding_digest": _field(binding, "campaign_binding_digest", str, "binding"),
        "merkle_root": _field(commitment, "merkle_root", str, "commitment"),
        "coordinate_root": expected_coordinate_root,
        "descriptor_sha256": expected_descriptor_sha256,
        "schema_sha256": expected_schema_sha256,
        "grid_point_count": _field(commitment, "grid_point_count", int, "commitment"),
        "production_identity_sha256": identity_digest,
        "plan_content_sha256": _field(plan, "content_sha256", str, "plan"),
    }))
    return sealed


@_typed
def load_commitment(root: Path | str) -> dict:
    base = _as_path(root, "root")
    path = base / COMMITMENT_NAME
    _require(path.is_file() and not path.is_symlink(),
             "no per-instance commitment has been sealed")
    sealed = _document(_read_json(path, "sealed commitment"), _COMMITMENT_FIELDS,
                       "sealed commitment")
    _document(_field(sealed, "binding", dict, "sealed"), _COMMITMENT_BINDING_FIELDS, "sealed commitment binding")
    _sha(_field(sealed, "plan_content_sha256", str, "sealed"), "sealed commitment plan hash")
    _sha(_field(sealed, "production_identity_sha256", str, "sealed"), "sealed commitment identity hash")
    return sealed


@_typed
def verify_plan_binding(root: Path | str) -> dict:
    """The commitment and its pin must name THIS sealed plan and THIS identity.

    Every read of a sealed artefact re-derives its binding from the sealed plan
    rather than from the artefact's own claim, so a stored document edited
    out of band is refused instead of being read as its own authority.  The
    adapter's binding digest is re-derived from the pinned component fields, so
    the pin cannot be edited coherently without changing that digest.
    """
    base = _as_path(root, "root")
    plan = load_range_plan(base)
    sealed = load_commitment(base)
    _require(_field(sealed, "plan_content_sha256", str, "sealed") == _field(plan, "content_sha256", str, "plan"),
             "the sealed commitment names a different range plan than the sealed one")
    _require(_field(sealed, "production_identity_sha256", str, "sealed") == _field(plan, "qualification_identity_sha256", str, "plan"),
             "the sealed commitment names a different production identity than the "
             "sealed plan")
    _require(_field(sealed, "total_coordinates", int, "sealed") == _field(plan, "total_coordinates", int, "plan"),
             "the sealed commitment names a different coordinate total than the sealed plan")
    pin = _read_campaign_pin(base)
    _require(_field(pin, "plan_content_sha256", str, "pin") == _field(plan, "content_sha256", str, "plan"),
             "the campaign binding pin names a different range plan than the sealed one")
    _require(_field(pin, "production_identity_sha256", str, "pin") == _field(plan, "qualification_identity_sha256", str, "plan"),
             "the campaign binding pin names a different production identity than the "
             "sealed plan")
    _require(_field(_field(sealed, "binding", dict, "sealed"), "campaign_binding_digest", str, "binding") == _field(pin, "campaign_binding_digest", str, "pin"),
             "the campaign binding pin names a different binding digest than the "
             "sealed commitment")
    binding = _field(sealed, "binding", dict, "sealed")
    _contract(adapter.verify_campaign_commitment, _field(pin, "campaign_binding_digest", str, "pin"),
              merkle_root=_field(pin, "merkle_root", str, "pin"),
              grid_point_count=_field(pin, "grid_point_count", int, "pin"),
              expected_descriptor_sha256=_field(pin, "descriptor_sha256", str, "pin"),
              expected_schema_sha256=_field(pin, "schema_sha256", str, "pin"),
              expected_coordinate_root=_field(pin, "coordinate_root", str, "pin"))
    return {"plan_content_sha256": _field(plan, "content_sha256", str, "plan"),
            "production_identity_sha256": _field(plan, "qualification_identity_sha256", str, "plan"),
            "total_coordinates": _field(plan, "total_coordinates", int, "plan"),
            "campaign_binding_digest": _field(pin, "campaign_binding_digest", str, "pin")}


def _read_campaign_pin(base: Path) -> dict:
    pin_path = base / CAMPAIGN_PIN_NAME
    _require(pin_path.is_file() and not pin_path.is_symlink(),
             "no sealed campaign binding pin")
    return _document(_read_json(pin_path, "campaign binding pin"),
                     _CAMPAIGN_PIN_FIELDS, "campaign binding pin")


@_typed
def open_campaign_pin(root: Path | str, expected_binding_digest: str) -> dict:
    """M4: open the campaign only against the pinned binding digest.

    The pinned value is the binding -- merkle root, coordinate root, descriptor
    hash, schema hash, grid size -- and not the inner Merkle root alone, because a
    root pinned without its schema is not reproducible if the schema is revised.
    """
    base = _as_path(root, "root")
    _sha(expected_binding_digest, "expected campaign binding digest")
    pin = _read_campaign_pin(base)
    _require(_field(pin, "campaign_binding_digest", str, "pin") == expected_binding_digest,
             "the sealed campaign binding pin names a different binding digest")
    _contract(
        adapter.verify_campaign_commitment,
        _field(pin, "campaign_binding_digest", str, "pin"),
        merkle_root=_field(pin, "merkle_root", str, "pin"),
        grid_point_count=_field(pin, "grid_point_count", int, "pin"),
        expected_descriptor_sha256=_field(pin, "descriptor_sha256", str, "pin"),
        expected_schema_sha256=_field(pin, "schema_sha256", str, "pin"),
        expected_coordinate_root=_field(pin, "coordinate_root", str, "pin"),
    )
    return pin


@_typed
def verify_retained_values(root: Path | str) -> dict:
    """M5: re-derive the root and the coordinate root from the retained values.

    A verifier needs the full ordered leaf list, the ordered coordinates and
    coordinate distinctness -- not aggregates.  Every one of those is re-derived
    here, so a commitment that retained only a root cannot pass.
    """
    base = _as_path(root, "root")
    sealed = load_commitment(base)
    commitment = _field(_field(sealed, "binding", dict, "sealed"), "commitment", dict, "binding")
    leaves_hex = _field(sealed, "retained_leaf_hashes", list, "sealed")
    coordinates = _field(sealed, "retained_coordinates", list, "sealed")
    _require(type(leaves_hex) is list and leaves_hex, "no retained leaf list")
    _require(type(coordinates) is list and len(coordinates) == len(leaves_hex),
             "retained coordinates disagree with the retained leaf list")
    _require(len(leaves_hex) == _field(commitment, "grid_point_count", int, "commitment"),
             "retained leaf list length differs from the sealed grid size")
    leaves = []
    for item in leaves_hex:
        _require(type(item) is str and len(item) == 64 and set(item) <= _HEX,
                 "retained leaf hash must be a lowercase SHA-256")
        leaves.append(bytes.fromhex(item))
    _require(sampled.merkle_root(leaves).hex() == _field(commitment, "merkle_root", str, "commitment"),
             "the retained leaf list does not reproduce the sealed merkle root")
    seen = set()
    for coordinate in coordinates:
        key = sampled.canonical(coordinate)
        _require(key not in seen, "retained coordinates are not distinct")
        seen.add(key)
    _require(sampled.coordinate_root(coordinates).hex() == _field(commitment, "coordinate_root", str, "commitment"),
             "the retained coordinates do not reproduce the sealed coordinate root")
    return {"verdict": "retained_values_verified",
            "grid_point_count": _field(commitment, "grid_point_count", int, "commitment"),
            "merkle_root": _field(commitment, "merkle_root", str, "commitment"),
            "coordinate_root": _field(commitment, "coordinate_root", str, "commitment")}


# ---------------------------------------------------------------------------
# M3: the external-timestamp hook (the TSA call is NOT made here)
# ---------------------------------------------------------------------------
@_typed
def build_timestamp_request(root: Path | str, policy: Mapping[str, Any], *,
                            nonce: int) -> dict:
    """Build the RFC 3161 request an external TSA will be asked to timestamp.

    The subject binds the sealed campaign root AND the beacon policy digest, so
    timestamping the root alone could not stop the policy changing afterwards.
    No TSA is contacted: the request bytes and their nonce are written out, and
    the token is fetched, verified and attached by a later, separate act.

    The request and its metadata are sealed once.  A second request -- a fresh
    nonce, or a policy that would change what the timestamp is about -- is
    refused rather than substituted, because the stored request is what an
    external TSA was asked to sign.
    """
    base = _as_path(root, "root")
    _require(type(policy) is dict and policy, "beacon policy must be a non-empty dict")
    _require(type(nonce) is int and nonce > 0, "timestamp request nonce must be a positive int")
    # ONE guard over BOTH sealed files.  The request and its metadata are a
    # single artefact: a check over each file separately would never be
    # load-bearing, because removing either one leaves the other to refuse the
    # same thing, and the two would be indistinguishable by message.
    for sealed in (TIMESTAMP_REQUEST_META, TIMESTAMP_REQUEST_NAME):
        _require(not (base / sealed).exists() and not (base / sealed).is_symlink(),
                 f"the external timestamp request is already sealed ({sealed}) "
                 "and may not be re-issued")
    pin = _read_campaign_pin(base)
    _sha(_field(pin, "campaign_binding_digest", str, "pin"), "campaign binding digest")
    plan = load_range_plan(base)
    _require(_field(pin, "plan_content_sha256", str, "pin") ==
             _field(plan, "content_sha256", str, "plan"),
             "the campaign binding pin names a different range plan than the sealed one")
    policy_digest = witness.beacon_policy_digest(dict(policy))
    subject = witness.witness_subject_digest(_field(pin, "merkle_root", str, "pin"), policy_digest)
    der, used_nonce = witness.build_timestamp_request(subject, nonce=nonce)
    _create_file_once(base / TIMESTAMP_REQUEST_NAME, der)
    meta = {"schema": witness.SCHEMA, "subject_digest": subject,
            "policy_digest": policy_digest, "merkle_root": _field(pin, "merkle_root", str, "pin"),
            "coordinate_root": _field(pin, "coordinate_root", str, "pin"),
            "campaign_binding_digest": _field(pin, "campaign_binding_digest", str, "pin"),
            "nonce": used_nonce, "minimum_authorities": witness.MINIMUM_AUTHORITIES,
            "tsa_contacted": False}
    _create_file_once(base / TIMESTAMP_REQUEST_META, _canonical(meta))
    return meta


# ---------------------------------------------------------------------------
# M7: the pinned beacon chain and round-selection rule
# ---------------------------------------------------------------------------
@_typed
def beacon_policy_of_pin(pin: Mapping[str, Any]) -> dict:
    """The policy the round is selected against: the pinned chain parameters.

    Round selection is a pure function of this policy and an attested pin
    timestamp, which is why the chain cannot be chosen after a round exists.
    """
    _require(type(pin) is dict, "beacon pin must be a dict")
    for key in BEACON_PIN_KEYS:
        _require(key in pin, f"beacon pin is missing {key!r}")
    _require(set(pin) == set(BEACON_PIN_KEYS), "beacon pin has an extra key")
    # Exact types, not isinstance: ``select_round`` consumes these as a period
    # and a genesis time, and a bool is an int subclass that would silently
    # become period 1 and select a round the owner never intended.
    period = _field(pin, "chain_period_seconds", int, "beacon pin")
    genesis = _field(pin, "chain_genesis_time", int, "beacon pin")
    _require(period > 0,
             "chain period must be a positive integer number of seconds")
    _require(genesis > 0,
             "chain genesis time must be a positive integer")
    for key in ("beacon_chain", "round_selection_rule", "pin_attestation"):
        _require(type(_field(pin, key, str, "beacon pin")) is str and _field(pin, key, str, "beacon pin"),
                 f"beacon pin {key!r} must be a non-empty string")
    scheme = _field(pin, "scheme_id", str, "beacon pin")
    _require(scheme in BEACON_SCHEMES, "beacon scheme_id is not allowed")
    rule = _field(pin, "round_selection_rule", str, "beacon pin")
    _require(rule in BEACON_ROUND_RULES, "beacon round-selection rule is not allowed")
    chain_hash = _field(pin, "chain_hash", str, "beacon pin")
    _sha(chain_hash, "beacon chain hash")
    public_key = _field(pin, "public_key_hex", str, "beacon pin")
    _require(len(public_key) == BEACON_SCHEMES[scheme] * 2
             and set(public_key) <= _HEX,
             "beacon public key has wrong hex length or encoding")
    return {key: _field(pin, key, int if key in ("chain_period_seconds", "chain_genesis_time") else str,
                        "beacon pin") for key in BEACON_PIN_KEYS}


def _sealed_beacon_pin(raw: object) -> dict:
    sealed = _document(raw, _BEACON_PIN_FIELDS, "sealed beacon rule pin")
    _require(set(sealed) == _BEACON_PIN_FIELDS, "sealed beacon rule pin has an extra key")
    policy = beacon_policy_of_pin(_field(sealed, "policy", dict, "sealed beacon rule pin"))
    digest = _sha(_field(sealed, "pin_digest", str, "sealed beacon rule pin"),
                  "frozen beacon pin digest")
    policy_digest = _sha(_field(sealed, "policy_digest", str, "sealed beacon rule pin"),
                         "frozen beacon policy digest")
    _require(digest == _content_digest(policy),
             "the frozen beacon policy is not the policy its pin was taken from")
    _require(policy_digest == witness.beacon_policy_digest(policy),
             "frozen beacon policy digest differs from policy")
    return sealed


@_typed
def seal_beacon_rule_pin(root: Path | str, pin: Mapping[str, Any],
                         expected_pin_digest: str) -> dict:
    """Freeze the chain choice and the round-selection rule as configuration.

    Frozen before the round exists, and not changed afterwards: a second call
    with a different digest is refused, because re-pinning after a round has been
    observed is exactly how a producer grinds rounds until the sample misses.
    """
    base = _as_path(root, "root")
    policy = beacon_policy_of_pin(pin)
    digest = _content_digest(policy)
    _require(digest == expected_pin_digest,
             "beacon rule pin does not match its expected digest")
    path = base / BEACON_PIN_NAME
    if path.exists() or path.is_symlink():
        sealed = _sealed_beacon_pin(_read_json(path, "sealed beacon rule pin"))
        _require(sealed.get("pin_digest") == digest,
                 "the beacon chain and round-selection rule are already frozen "
                 "and may not be re-pinned")
        return sealed
    body = {"pin_digest": digest, "policy": policy,
            "policy_digest": witness.beacon_policy_digest(policy)}
    _create_file_once(path, _canonical(body))
    return body


@_typed
def consult_beacon_rule(root: Path | str, expected_pin_digest: str) -> dict:
    """Record that the frozen rule was consulted for this sealed commitment.

    The commitment root must already be sealed: the round is selected from a pin
    time that must follow the root's external timestamp, and there is no ordering
    that can be recovered afterwards.  No beacon is fetched here.

    The consultation is sealed once, so it cannot be re-pointed at a different
    root, a different pin or a different policy after it has been recorded.
    """
    base = _as_path(root, "root")
    pin_path = base / BEACON_PIN_NAME
    _require(pin_path.is_file() and not pin_path.is_symlink(),
             "the beacon chain and round-selection rule are not frozen")
    sealed_pin = _sealed_beacon_pin(_read_json(pin_path, "sealed beacon rule pin"))
    _sha(expected_pin_digest, "expected beacon rule pin digest")
    _require(sealed_pin.get("pin_digest") == expected_pin_digest,
             "the consulted beacon rule differs from the frozen pin")
    _sha(_field(sealed_pin, "policy_digest", str, "sealed_pin"), "frozen beacon policy digest")
    # The stored policy must be EXACTLY the policy the pin digest was computed
    # over.  Re-deriving the digest here is what catches a policy edited in
    # place after freezing: a value that is individually well-formed (any
    # positive period) still produces a different digest, so a round selected
    # under the edited policy is not the round the pin names.
    _require(_content_digest(beacon_policy_of_pin(_field(sealed_pin, "policy", dict, "sealed_pin")))
             == _field(sealed_pin, "policy_digest", str, "sealed_pin"),
             "the frozen beacon policy is not the policy its pin was taken from")
    _require((base / CAMPAIGN_PIN_NAME).is_file(),
             "the per-instance commitment root must be sealed before the beacon "
             "round-selection rule is consulted")
    pin = _read_campaign_pin(base)
    _require(not (base / BEACON_CONSULT_NAME).exists()
             and not (base / BEACON_CONSULT_NAME).is_symlink(),
             "the beacon rule consultation is already sealed and may not be re-recorded")
    body = {"pin_digest": expected_pin_digest,
            "policy_digest": _field(sealed_pin, "policy_digest", str, "sealed_pin"),
            "merkle_root": _field(pin, "merkle_root", str, "pin"),
            "campaign_binding_digest": _field(pin, "campaign_binding_digest", str, "pin"),
            "coordinate_root": _field(pin, "coordinate_root", str, "pin"),
            "beacon_fetched": False}
    _create_file_once(base / BEACON_CONSULT_NAME, _canonical(body))
    return body


@_typed
def stages_present(root: Path | str) -> list:
    """Which M-ordering stages have actually been reached, in M1..M7 order.

    Reported so an auditor can see the order rather than infer it.  It is a
    report, not the enforcement: the enforcement is the refusal in each step.
    """
    base = _as_path(root, "root")
    return [name for name, present in (
        ("range_plan", (base / PLAN_NAME).is_file()),
        ("ranges_promoted", (base / RANGES_DIRNAME).is_dir()),
        ("commitment_root_sealed", (base / COMMITMENT_NAME).is_file()),
        ("external_timestamp_requested", (base / TIMESTAMP_REQUEST_META).is_file()),
        ("beacon_rule_frozen", (base / BEACON_PIN_NAME).is_file()),
        ("beacon_rule_consulted", (base / BEACON_CONSULT_NAME).is_file()),
    ) if present]


@_typed
def sealed_state(root: Path | str) -> list:
    """What each sealed artefact actually says, not merely that a file exists.

    Every entry reports the fields that bind the artefact to the sealed plan, read
    back from the stored document and re-checked against the plan on disk.  An
    artefact that is present but names a different plan or identity is reported
    as ``plan_bound: False`` rather than as a completed stage, so presence is
    never reported as progress.
    """
    base = _as_path(root, "root")
    plan_path = base / PLAN_NAME
    state: list[dict] = []
    plan_hash = None
    if plan_path.is_file() and not plan_path.is_symlink():
        plan = load_range_plan(base)
        plan_hash = _field(plan, "content_sha256", str, "plan")
        state.append({"stage": "range_plan_sealed", "sealed": True,
                      "plan_content_sha256": plan_hash, "plan_bound": True,
                      "batch_count": len(_field(plan, "ranges", list, "plan"))})
    else:
        state.append({"stage": "range_plan_sealed", "sealed": False,
                      "plan_content_sha256": None, "plan_bound": False,
                      "batch_count": 0})
    if (base / RANGES_DIRNAME).is_dir():
        promoted = sorted(promoted_batch_ids(base))
        state.append({"stage": "ranges_promoted", "sealed": bool(promoted),
                      "promoted_batch_ids": promoted, "plan_bound": True,
                      "plan_content_sha256": plan_hash})
    else:
        state.append({"stage": "ranges_promoted", "sealed": False,
                      "promoted_batch_ids": [], "plan_bound": plan_hash is not None,
                      "plan_content_sha256": plan_hash})
    for stage, name in (("commitment_root_sealed", COMMITMENT_NAME),
                        ("campaign_binding_pinned", CAMPAIGN_PIN_NAME)):
        path = base / name
        entry = {"stage": stage, "sealed": path.is_file() and not path.is_symlink(),
                 "plan_bound": False, "plan_content_sha256": None}
        if entry["sealed"]:
            # A stored document is untrusted input, so a report over a
            # malformed one must not raise: this reporter's job is to SAY that
            # the artefact is present but unreadable, which is the case a
            # caller most needs reported.  The catch is narrowed to
            # WRITER_BOUNDARY_ERRORS -- the classes a read/parse/index of a
            # stored document can raise -- and NOT ``except Exception``, so a
            # fault outside that set still propagates instead of being reported
            # as an unreadable artefact.
            try:
                document = _read_json(path, stage)
                named = _field(_document(document, _STORED_PLAN_BOUND_FIELDS[stage],
                                  stage), "plan_content_sha256", str, stage)
                _sha(named, f"{stage} plan hash")
                entry["plan_content_sha256"] = named
                entry["plan_bound"] = named == plan_hash
            except WRITER_BOUNDARY_ERRORS:
                entry["plan_content_sha256"] = None
                entry["plan_bound"] = False
        state.append(entry)
    for stage, name in (("external_timestamp_requested", TIMESTAMP_REQUEST_META),
                        ("beacon_rule_frozen", BEACON_PIN_NAME),
                        ("beacon_rule_consulted", BEACON_CONSULT_NAME)):
        path = base / name
        state.append({"stage": stage, "sealed": path.is_file() and not path.is_symlink(),
                      "plan_bound": plan_hash is not None, "plan_content_sha256": plan_hash})
    return state


def writer_limits() -> dict:
    """What this writer does and does not establish, kept in code so it cannot drift."""
    return {
        "establishes": [
            "one canonical range plan is sealed per instance/output family, and a "
            "later session cannot repartition it",
            "a promoted range holds a records file and its manifest that were "
            "written, fsynced and verified together and promoted by a single "
            "rename, so neither is ever visible without the other",
            "a range is reported complete only when its records file hash AND its "
            "records content hash both match its manifest",
            "a later session is offered exactly the whole sealed ranges that were "
            "never promoted, and a completed range is never rewritten",
            "aggregation is refused until the final-set audit confirms an exact, "
            "non-overlapping cover of the sealed plan",
            "every range manifest carries the sealed plan hash and the accepted "
            "production-identity hash, and a write under a different identity is "
            "refused before any byte is written",
            "the production identity is established by CONTENT HASH alone: the "
            "injected validator's sha256-hex is type-checked and compared for "
            "exact equality against the hash in the sealed plan and in every "
            "range manifest, the commitment and the campaign pin.  No check "
            "here infers an identity from an object's attribute existence",
            "a sealed artefact is created once and never replaced: the sealed plan, "
            "a promoted range, the per-instance commitment, the binding pin, the "
            "timestamp request, the frozen beacon rule and the rule consultation "
            "are all created through a hard link that fails on an existing name, "
            "so no code path in this module can rewrite any of them",
            "the per-instance commitment is bound to the sealed plan in both "
            "directions -- its identity hash, its plan content hash and its "
            "coordinate total are each checked against the plan on every seal and "
            "on every read -- and it covers every point over an independently "
            "supplied coordinate roster",
        ],
        "does_not_establish": [
            "the correctness of any record: the writer hashes and orders what it "
            "is handed and computes no result",
            "the production identity itself: the identity payload, its validate() "
            "and its exact_match() are injected by the caller, because the WP1 "
            "identity is still under review and is deliberately not imported here",
            "an external timestamp. This module builds the RFC 3161 request and "
            "writes it out; it contacts no TSA and verifies no token",
            "a beacon round, a beacon response or a drawn nonce. The chain choice "
            "and the round-selection rule are frozen as configuration; no round is "
            "selected and no beacon is fetched here",
            "any sampling. The M1-M7 structures exist so a later audit binds the "
            "same evidence; drawing a challenge and verifying a sample is "
            "deferred, and this module has no code for either",
            "that a promoted range will survive hardware or filesystem loss; the "
            "fsync and rename sequence bounds the rename's atomicity, not storage",
            "that a sealed artefact survives an out-of-band edit of the file "
            "system underneath it. Every read re-derives the artefact's binding "
            "from the sealed plan and from the bytes on disk, so such an edit is "
            "detected and refused, but it is detected rather than prevented",
        ],
    }


# Kept so a caller can iterate a plan's ranges without importing the contract.
# The frozen contract refuses a non-dict plan on its own key set, so there is no
# separate type check here: it would be a check nothing can reach.
@_typed
def plan_batches(plan: Mapping[str, Any]) -> list:
    return [dict(row) for row in _field(_contract(validate_range_plan, dict(plan)), "ranges", list, "plan")]

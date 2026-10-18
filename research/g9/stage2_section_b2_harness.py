"""In-session full-domain validation harness for approved amendment Section B item 2.

This module is the per-session driver that the Gate-9 closure plan records as
missing (GATE_9_SECTION_B_CLOSURE_PLAN_DRAFT.md:31, "no per-session harness over
the full coordinate list").  It builds the frozen validation-coordinate list,
drives a full-domain CUDA-vs-Python bit-for-bit comparison at every one of those
coordinates, and returns only the Section B item 3 record.

Governing text, quoted in full in the WP0 audit at :188-202 and repeated in
GATE_9_SECTION_B_KAGGLE_PROVIDER_TRUST_AMENDMENT_DRAFT.md:40-46:

    2. compare CUDA and Python bit-for-bit on the full prepared binary domain for
       both encodings at every fixed validation coordinate the session may
       produce: primary (30,30,30) at each r in {0.5,1,2} under every D015
       comparator pair; D011 (6,6,6) on its declared 13-cubed subgrid; V-14 0.5x
       (0,0,0), (15,15,15), (30,30,30), (30,0,15); and V-14 2x (0,0,0),
       (55,55,55), (110,110,110), (110,0,55). If D013 fires, immediately before
       its CUDA ranges run, repeat this full-domain comparison at primary
       (30,30,30) for each of C, CB, CS, and CSB, including their inactive +0.0
       families. Every comparison includes energy-minimum words, canonical
       minimum index, tie flags, and D015/D016 reconstruction; and
    3. write only the pass/fail counters, platform/source identities, and
       canonical validation digest. It retains no unapproved coordinate-level
       scientific values in the qualification record.

This module draws no candidate, no instance, no ground truth and no scientific
value, and computes no energy itself.  Both the device backend and the Python
reference are INJECTED callables; this module only orders the comparisons, checks
that both sides produced the four required fields, compares them bit-for-bit, and
stops fail-closed on the first defect.  The production identity (WP1) is also
injected, as a ``validate(payload) -> sha256-hex`` callable and an
``exact_match(session, accepted)`` callable; WP1 is still under review and is
deliberately not imported here.

The D013 repeat needs a device backend that can represent the inactive +0.0
families.  The qualified v1 backend cannot: it refuses any row whose slack
coefficients are not strictly positive, at
research/g9/cuda_qualification/stage2_cuda_core_bridge.cu:29
(``row.sector_slack > 0.0 && row.budget_slack > 0.0``).  So when D013 fires
against a backend that does not declare +0.0 support, this module REFUSES with a
typed error.  It never skips the repeat, because a skipped required comparison
would be a silent pass (GATE_9_STAGE2_KAGGLE_CUDA_AMENDMENT_DRAFT.md:92-97).

That capability is declared BY THE BACKEND and only by the backend: a backend
carries the PLAIN DATA class attribute ``supports_inactive_positive_zero = True``.
There is no caller flag and no argument that can turn it on -- round 2's
``device_supports_positive_zero`` keyword let any caller unlock the repeat on
behalf of a backend that had not declared it, and the v1 backend passed a
160-comparison run that way.

The declaration is read WITHOUT EXECUTING ANY BACKEND CODE.  Round 3 read it
with ``getattr``, which invokes a property and consults ``__getattr__``; a
backend whose declaration was a property raising a ``BaseException`` therefore
raised it from inside this module, untyped, because the guard there caught only
``Exception``.  Catching ``BaseException`` is NOT the fix -- that would swallow
the ``KeyboardInterrupt`` and ``SystemExit`` a caller must be able to act on.
So the read is static: ``inspect.getattr_static`` never invokes a descriptor and
never consults ``__getattr__``, and only a plain data attribute whose value is
exactly ``True`` counts as a declaration.  A missing name, ``False``, a
per-instance attribute, a non-bool, or any descriptor, property or callable is a
backend that does not support +0.0, and the D013 repeat is refused.

Every value that enters this module from outside it -- a keyword argument, an
injected callable's return value -- is type-checked and converted through the
typed accessors ``_mapping_copy`` / ``_sequence_list`` / ``_exact_bool`` and the
total comparators ``_row_fields_match`` / ``_same_row_identity`` /
``_duplicate_row_index``.  Those are the ONLY places an external value is
narrowed or compared, and every one of them either raises
``SectionB2HarnessError`` or answers a total boolean.  Every exception raised by
an injected backend, reference or identity function is converted by
``_call_backend`` / ``_call_injected`` into that same typed error, so a raw
``TypeError``, ``ValueError``, ``KeyError``, ``AttributeError``, ``IndexError``,
``RuntimeError`` or ``BaseException`` from an injected callable cannot reach a
caller.  The fixture fuzzes every public argument with None, bool, int, str,
list, dict, an unhashable value and a nested wrong-type value, drives
backends that raise, and requires a typed refusal every time.

The record this module returns is always sealed with its own
``content_sha256`` and has always passed ``validate_section_b2_record``: the
sealing and the validation are unconditional, so there is no path that hands
back an unsealed or unchecked record.
"""
from __future__ import annotations

import hashlib
import inspect
import json
import sys
from pathlib import Path
from typing import Any, Callable, Mapping

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.g6 import d011_matched_subgrid as _d011_matched_subgrid
from src.g6 import d011_runner as _d011_runner
from src.g6 import d011_transition_output as _d011_transition_output
from src.g6 import g5_input as _g5_input
from src.g6 import ledgers as _ledgers

RECORD_SCHEMA = "decisions_os/g9_section_b2_validation_record/v1"

# The four per-comparison fields required by the amendment at :86-87, scoped by
# its own words to EVERY comparison: "Every comparison includes energy-minimum
# words, canonical minimum index, tie flags, and D015/D016 reconstruction".  The
# WP0 audit restates this scoping at :204-220.  Order is frozen and is the order
# in which the harness requires a backend to supply them.
COMPARISON_FIELDS = (
    "energy_minimum_words",
    "canonical_minimum_index",
    "tie_flags",
    "reconstruction",
)

# Both encodings.  src/g6/d011_matched_subgrid.py:47 and
# src/g6/d011_transition_output.py:37 name them ENCODINGS = ("unbalanced", "slack");
# one coefficient row is swept under each, and the pilot times them together
# (research/g9/pilot_stage2_cpu_cost.py, TIMED rows carry both encodings).
_ENCODINGS = tuple(_d011_matched_subgrid.ENCODINGS)

# The D015 comparator pairs: the primary plus the four frozen one-factor
# diagnostics, in frozen declaration order exactly as
# src/g6/d011_transition_output.py:91-92 assembles them
# ("The primary plus every frozen D015 diagnostic, in frozen declaration order").
D015_COMPARATOR_PAIRS = (
    (_d011_transition_output.PRIMARY[0], _d011_transition_output.PRIMARY[1]),
) + tuple((c_h, c_f) for c_h, c_f in _d011_runner.DIAGNOSTIC_PAIRS)

# The D013 conditions, in the order the amendment lists them.  These are D013
# constraint-condition names, not encodings: DECISIONS.md:1106-1113 defines
# F_C, F_CB, F_CS, F_CSB.
D013_CONDITIONS = ("C", "CB", "CS", "CSB")

# The same four names, restated as a frozen literal.  Round 2: the builder
# accepted a list of four distinct NON-EMPTY strings, so a renamed condition --
# ("C","CB","CS","CD") -- produced a repeat over a condition the amendment does
# not name.  D013_CONDITIONS is the session's list; this is the amendment's.
_FROZEN_D013_CONDITIONS = ("C", "CB", "CS", "CSB")

# r values.  src/g6/g5_input.py:25 R_VALUES = (0.5, 1.0, 2.0), identical to
# src/g5/core_pass.py:43.  The amendment names them r in {0.5,1,2}.
_R_VALUES = tuple(_g5_input.R_VALUES)

# D011 axis count.  src/g6/d011_runner.py:49 AXIS_COUNT = 13; the matched
# subgrid it selects is 13**3 coordinates
# (src/g6/d011_matched_subgrid.py:54 MATCHED_COORDINATE_COUNT = 13 ** 3).
_D011_AXIS_COUNT = _d011_runner.AXIS_COUNT
_D011_MATCHED_COUNT = _d011_matched_subgrid.MATCHED_COORDINATE_COUNT

# The D011 row is always emitted.  The flag exists so the total-row-count guard
# below can be reached from the fixtures by dropping EXACTLY that one row, with
# the r-set, V-14-length, axis-count and duplicate guards all still satisfied --
# otherwise the count guard would be masked by an earlier one and could never be
# shown load-bearing.  It is a frozen constant with exactly one true value; a
# caller has no way to set it.
_D011_ROW_ENABLED = True

# V-14 axis counts per scale, from src/g6/ledgers.py:290-291:
#   "0.5x": {"m_lo": 2, "m_hi": 0, "N_axis": 31}
#   "2x":   {"m_lo": 8, "m_hi": 2, "N_axis": 111}
# so 0.5x indices run 0..30 and 2x indices run 0..110.  The V-14 tuples are
# checked against these, so a misread scale is caught arithmetically.
_V14_AXIS_COUNT = {"0.5x": 31, "2x": 111}

# The primary validation coordinate.  src/g6/trial_runner.py:187-200 pins the
# D011 companion's Gate-5 row at 30
# (d011["coordinates"][6]["primary_ell"] == 30, "D011 bounded trial must use
# primary row 30") and pins the V-14 2x embedded primary at ledger index 70,
# which the nesting rule at src/g6/ledgers.py:385-388 binds to primary row 30.
_PRIMARY_COORDINATE = (30, 30, 30)
_D011_COORDINATE = (6, 6, 6)
_V14_HALF = ((0, 0, 0), (15, 15, 15), (30, 30, 30), (30, 0, 15))
_V14_DOUBLE = ((0, 0, 0), (55, 55, 55), (110, 110, 110), (110, 0, 55))

BASE_COORDINATE_COUNT = 12
D013_REPEAT_COORDINATE_COUNT = 4
D013_CONDITIONS_PER_REPEAT = len(D013_CONDITIONS)

# Cost figures, quoted from the measurement pilot
# (research/g9/pilot_stage2_cpu_cost.py) as the owner supplied them.  These are
# ESTIMATES: no domain is enumerated here and no timing is taken.
REFERENCE_SECONDS_PER_ROW = 487.0
NUMPY_SECONDS_PER_ROW = 7.9
REFERENCE_COST_NOTE = "measured under load"
NUMPY_COST_NOTE = "NumPy bit-exact path"

# The frozen multiplicities.  The amendment names FIVE D015 comparator pairs
# (the primary plus four diagnostics, DECISIONS.md:1237-1245) and TWO encodings
# (src/g6/d011_matched_subgrid.py:47).  These are checked against the live lists
# on every run, so dropping an encoding or a comparator pair is refused by name
# rather than only by a downstream arithmetic mismatch.
FROZEN_COMPARATOR_COUNT = 5
FROZEN_ENCODING_COUNT = 2
COMPARISONS_PER_ROW = FROZEN_COMPARATOR_COUNT * FROZEN_ENCODING_COUNT

_RECORD_KEYS = frozenset({
    "schema", "verdict", "counters", "identities", "validation_digest", "content_sha256",
})
_COUNTER_KEYS = frozenset({
    "comparisons", "passed", "failed", "coordinate_rows", "d013_repeat_rows",
})
_IDENTITY_KEYS = frozenset({
    "accepted_identity_sha256", "session_identity_sha256", "protocol_identity_sha256",
})


class SectionB2HarnessError(ValueError):
    """Typed refusal for an unsafe or incomplete Section B item 2 comparison.

    Every input-handling failure in this module -- a wrong-typed or malformed
    argument, a backend that returns the wrong shape, a non-JSON-serialisable
    value, a unhashable value -- surfaces as this type or a subclass of it, and
    never as a bare TypeError, ValueError, KeyError or AttributeError.
    """


class SectionB2D013UnsupportedError(SectionB2HarnessError):
    """D013 fired but the device backend cannot represent the inactive +0.0 families.

    Raised instead of skipping.  v1 refuses +0.0 at
    research/g9/cuda_qualification/stage2_cuda_core_bridge.cu:29, so until the
    WP6b additive +0.0 path exists this repeat cannot be run and must not be
    silently passed over.
    """


def _require(condition: object, message: str) -> None:
    if not condition:
        raise SectionB2HarnessError(message)


# ---------------------------------------------------------------------------
# Typed accessors.  Every external value is narrowed through exactly one of
# these four, so no untyped exception can be produced by narrowing one.
# ---------------------------------------------------------------------------

def _mapping_copy(value: object, label: str) -> dict:
    """Return a plain-dict copy of a mapping, or raise the typed error.

    A non-mapping, an unhashable key, or a value JSON cannot serialise are all
    refused here, before any consumer would raise a raw TypeError/ValueError
    (``dict(...)``, ``set(value)``, ``json.dumps``).
    """
    _require(isinstance(value, Mapping),
             f"{label} must be a mapping, not {type(value).__name__}")
    try:
        out = dict(value)
        keys = set(out)
    except Exception as exc:
        # A hostile Mapping -- one whose iteration, keys() or __eq__ raises --
        # is still a malformed input, so it is refused with the typed error
        # rather than surfacing whatever its author chose to raise.
        raise SectionB2HarnessError(f"{label} could not be read as a mapping: {exc}") from exc
    _require(all(type(key) is str for key in keys),
             f"{label} keys must all be strings")
    return out


def _sequence_list(value: object, label: str) -> list:
    """Return a list copy of a sequence, or raise the typed error."""
    _require(type(value) in (tuple, list),
             f"{label} must be a tuple or list, not {type(value).__name__}")
    return list(value)


def _exact_bool(value: object, label: str) -> bool:
    """Return a plain bool, or raise the typed error.

    ``type(...) is bool`` and not ``isinstance``: True is an int in Python, and a
    capability flag that is an int would silently read as "declared".
    """
    _require(type(value) is bool, f"{label} must be a bool, not {type(value).__name__}")
    return value


# The +0.0 capability declaration.  This name is a CONTRACT with the injected
# backend object: a backend that can represent the inactive +0.0 families must
# expose it as a PLAIN DATA attribute on its TYPE, and only the backend can
# decide.  Round 3: the D013 repeat used to be unlocked by the caller-supplied
# ``device_supports_positive_zero`` keyword, so any caller could claim +0.0
# support on behalf of a backend that had not declared it -- and the qualified v1
# backend, which refuses inactive rows at
# research/g9/cuda_qualification/stage2_cuda_core_bridge.cu:29, passed the
# repeat as a result.  There is now NO caller flag: the only declaration this
# module will read is the backend's own attribute.
POSITIVE_ZERO_DECLARATION = "supports_inactive_positive_zero"

# A default that is not a value any backend could legitimately declare, so
# "absent" and "declared to be None" stay distinguishable.  A plain object is
# unreachable as a declaration because it is descriptor-shaped and would have
# been refused as one.
_ABSENT_DECLARATION = object()

# The slots that make a value a DESCRIPTOR: reading it as an attribute would run
# its __get__/__set__/__delete__.  Probed with inspect.getattr_static, so even
# the probe never executes anything.
_DESCRIPTOR_SLOTS = ("__get__", "__set__", "__delete__")


def _is_descriptor(value: object) -> bool:
    """True when reading ``value`` as an attribute would RUN it.

    Probed statically on the value's own type, so this too executes no backend
    code.  A property object, a function, a classmethod/staticmethod and a
    custom descriptor all define one of these slots and are therefore refused; a
    plain int, str, list, dict or None defines none and is a (malformed) data
    value instead.
    """
    return any(inspect.getattr_static(type(value), slot, None) is not None
               for slot in _DESCRIPTOR_SLOTS)


def _static_positive_zero_declaration(backend: object) -> object:
    """The CLASS-level value of the +0.0 declaration, read WITHOUT running it.

    ``inspect.getattr_static`` is the whole of the round-4 fix.  It consults
    only ``__dict__`` mappings and MRO tuples and returns the default when the
    name is absent; it never invokes a descriptor and never consults
    ``__getattr__``.  So a backend cannot run code, raise anything, or leave a
    side effect by way of this read -- which is exactly what ``getattr`` let it
    do in round 3, and what made an untyped ``BaseException`` escape.

    A single static read is enough and no second path is needed: the only shape
    where a class-dict walk and ``getattr_static`` differ is a class whose
    declaration is a property SHADOWED by a plain-data instance attribute, and
    that instance attribute is refused by the per-instance rule below before
    this read happens.  ``getattr_static`` is the reference for what an
    attribute lookup would return, and it is the one that never runs code.
    """
    # A per-instance attribute is refused BEFORE anything is read, as a claim.
    try:
        own = vars(backend)
    except TypeError:
        own = {}
    _require(type(own) is dict,
             f"device_backend carries no readable instance __dict__, so it cannot "
             f"carry a {POSITIVE_ZERO_DECLARATION} declaration")
    _require(POSITIVE_ZERO_DECLARATION not in own,
             f"device_backend must declare {POSITIVE_ZERO_DECLARATION} as a plain data "
             f"attribute on its TYPE; a per-instance attribute is assignable after "
             f"construction, so it is a caller's claim rather than the backend's own")
    declared = inspect.getattr_static(type(backend), POSITIVE_ZERO_DECLARATION,
                                      _ABSENT_DECLARATION)
    if declared is _ABSENT_DECLARATION:
        raise AttributeError(POSITIVE_ZERO_DECLARATION)
    return declared


def _backend_declares_positive_zero(backend: object) -> bool:
    """Read the +0.0 declaration FROM THE BACKEND, without executing the backend.

    There is no argument to override this and no fallback: a backend that does
    not carry ``supports_inactive_positive_zero`` -- which includes the
    qualified v1 backend -- does not declare +0.0 support, and the D013 repeat
    is refused against it.

    DECISION, class attribute vs instance attribute.  Both are judged for
    PLAIN-DATA-ness, and the accepted form is the CLASS attribute:

      * CLASS plain-data True is ACCEPTED.  It is the strongest declaration
        there is: it is fixed in the backend's own type, every instance of that
        type declares it, and no caller can change it for one instance without
        rebuilding the class.
      * INSTANCE True is REFUSED, whether it was set in ``__init__`` or assigned
        afterwards.  It is plain data, but it is assignable after construction,
        so it is a claim made TO the backend rather than a declaration BY it --
        exactly the round-3 finding that a caller must not be able to unlock the
        repeat -- and this module cannot tell a backend's own ``__init__``
        assignment from a caller's, so it refuses both.  A backend that wants
        the declaration declares it on its type.
      * What is REFUSED either way is anything DESCRIPTOR-shaped, on the class
        or the instance: a ``property`` (read-only or writable), a
        ``classmethod``/``staticmethod``, a function, a custom descriptor, and
        anything reachable only through ``__getattr__``.  Each is code that
        WOULD run on an ordinary attribute read, so accepting one would put the
        round-3 untyped-``BaseException`` leak straight back in.  This is why
        ``DeclaredReadOnlyBackend``, which round 3 accepted, is now refused --
        not because it is writable, but because it is code -- and why a property
        that would have raised is never executed to discover that.
      * A plain data attribute of a non-bool, non-descriptor type is a MALFORMED
        claim rather than an absent one, so it is refused by name with the typed
        error instead of silently answering "does not support +0.0".

    An absent name and a descriptor-shaped name both answer ``False`` -- "this
    backend does not support +0.0" -- rather than raising, because an absent or
    unusable declaration is the v1 case and the D013 repeat is then refused with
    the typed error by the caller.  So a backend of any hostile shape still gets
    a typed refusal out of ``run_section_b2`` and never a raw ``AttributeError``.
    """
    try:
        declared = _static_positive_zero_declaration(backend)
    except AttributeError:
        return False
    if type(declared) is bool:
        return declared
    if _is_descriptor(declared):
        return False
    _require(False,
             f"device_backend declares {POSITIVE_ZERO_DECLARATION} as "
             f"{type(declared).__name__}; it must be a plain bool data attribute "
             f"whose value is True, or absent")


def _call_backend(backend: object, name: str, row: object, pair: object, encoding: object) -> object:
    """Invoke an injected backend/reference and convert ANY exception to the typed error.

    Round 3: an injected ``RuntimeError`` used to escape untyped, so a caller
    could not distinguish a harness refusal from a backend crash and a fail-closed
    harness could be wrapped in a handler that treats a crash as anything else.
    Everything a backend or reference can raise -- including a BaseException it
    raises deliberately -- becomes ``SectionB2HarnessError`` and nothing is
    written.  A refused call is re-raised unchanged, so a backend that cannot even
    be called is named as such.
    """
    try:
        return backend(row, pair, encoding)
    except SectionB2HarnessError:
        raise
    except BaseException as exc:
        raise SectionB2HarnessError(
            f"{name} raised {type(exc).__name__} at the requested comparison; the "
            f"session is fail-closed and no record is written: {exc}") from exc


def _sha(value: object, label: str) -> str:
    _require(type(value) is str and len(value) == 64
             and all(char in "0123456789abcdef" for char in value),
             f"{label} must be a lowercase SHA-256")
    return value


def _int(value: object, label: str, minimum: int = 0) -> int:
    _require(type(value) is int and value >= minimum, f"{label} must be an integer >= {minimum}")
    return value


def _axis_index(value: object, scale: str, label: str) -> int:
    _require(type(value) is int, f"{label} must be an integer")
    _require(0 <= value < _V14_AXIS_COUNT[scale],
             f"{label} {value} is outside the V-14 {scale} axis 0..{_V14_AXIS_COUNT[scale] - 1}")
    return value


def _coordinate(triple: object) -> tuple:
    """Narrow one frozen validation coordinate to a 3-tuple of non-negative ints.

    The builder feeds this only its own literals, so a caller cannot reach a
    malformed triple; the checks are nevertheless driven directly by the fixture
    on the whole fuzz corpus, because a shape guard on the FROZEN data is what
    stops a future edit from transcribing (30,30,30.0) or (30,30) into the
    literal tables.
    """
    _require(type(triple) is tuple and len(triple) == 3,
             "a validation coordinate must be a 3-tuple, not "
             f"{type(triple).__name__} of length "
             f"{len(triple) if type(triple) is tuple else 'n/a'}")
    for axis in triple:
        _require(type(axis) is int and axis >= 0,
                 f"a validation coordinate axis must be a non-negative integer, not "
                 f"{type(axis).__name__}")
    return triple


def canonical_bytes(value: object) -> bytes:
    body = _mapping_copy(value, "the canonical payload")
    try:
        return json.dumps(body, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False).encode("ascii")
    except (TypeError, ValueError) as exc:
        raise SectionB2HarnessError(
            f"the canonical payload is not JSON-serialisable: {exc}") from exc


def content_sha256(value: object) -> str:
    body = _mapping_copy(value, "the record to be hashed")
    body.pop("content_sha256", None)
    return hashlib.sha256(canonical_bytes(body)).hexdigest()


def _row_fields_match(expected: object, got: object) -> bool:
    """Element-wise key/value equality that can never raise.

    Returns False rather than propagating a TypeError from comparing a value to
    a dict, a list, an array or a custom __eq__.  Used for the per-row contract
    test so that a hostile row shape is refused with the typed error and its
    message, never with whatever ``dict.__eq__`` raises.
    """
    want = _mapping_copy(expected, "the expected coordinate row")
    try:
        have = dict(got)  # type: ignore[arg-type]
    except Exception:
        return False
    if set(have) != set(want):
        return False
    for key in want:
        left, right = want[key], have[key]
        if type(left) is not type(right):
            return False
        if type(left) in (tuple, list):
            if len(left) != len(right):
                return False
            if not all(type(one) is type(two) and one == two
                       for one, two in zip(left, right)):
                return False
            continue
        try:
            if not (left == right):
                return False
        except Exception:  # a hostile __eq__ is "not equal", not a crash
            return False
    return True


def _same_row_identity(left: object, right: object) -> bool:
    """Compare the frozen row identity of two rows without ever raising."""
    try:
        return (left["family"] == right["family"]  # type: ignore[index]
                and left.get("condition") == right.get("condition")  # type: ignore[union-attr]
                and left.get("scale") == right.get("scale")  # type: ignore[union-attr]
                and left["coordinate"] == right["coordinate"]  # type: ignore[index]
                and left["r"] == right["r"])  # type: ignore[index]
    except (TypeError, KeyError, IndexError, AttributeError):
        return False


def _duplicate_row_index(rows: object) -> int:
    """Index of the first repeated row under the frozen row identity, or -1.

    Uniqueness is over the whole row identity -- (family, condition, scale,
    coordinate, r) -- because (0,0,0) and (30,30,30) each legitimately appear
    once per V-14 scale and (30,30,30) also appears as the primary coordinate, so
    a "coordinate alone" rule would reject the amendment's own list.  Both the
    identity comparison and the whole-row comparison are total functions that
    answer "not equal" rather than propagating, so an unhashable coordinate, an
    exotic row type or a duplicate can never produce a TypeError from ``set`` or
    from ``__eq__``.
    """
    try:
        members = list(rows)  # type: ignore[arg-type]
    except TypeError:
        return -1
    seen: list = []
    for index, row in enumerate(members):
        if any(_same_row_identity(prior, row) for prior in seen):
            return index
        seen.append(row)
    return -1


def build_validation_coordinates() -> tuple:
    """Return EXACTLY the coordinate list the amendment names, in amendment order.

    This builder takes no arguments and offers no override path.  Every entry
    carries only what selects the row (family, coordinate, r, comparator, scale,
    grid, inactive-family flag) -- never a value, and never a comparison result.

    Row families, quoting the amendment clause each comes from:

      * primary ``(30,30,30)`` at each ``r in {0.5,1,2}`` -- one row per r.
      * D011 ``(6,6,6)`` on its declared 13-cubed subgrid -- one row.
      * V-14 0.5x ``(0,0,0)``, ``(15,15,15)``, ``(30,30,30)``, ``(30,0,15)``.
      * V-14 2x ``(0,0,0)``, ``(55,55,55)``, ``(110,110,110)``, ``(110,0,55)``.

    The comparator pairs and encodings are NOT in this list: they multiply every
    row, exactly as the WP0 audit counts them at :893-901 (12 coordinate-rows ->
    120 comparisons with D013 unfired; 16 rows -> 160 with D013 fired).
    """
    rows: list = []

    # primary (30,30,30) at each r in {0.5, 1, 2} -- amendment :80
    _require(len(_R_VALUES) == 3, "the frozen r set must be exactly three values")
    for r_value in _R_VALUES:
        rows.append({
            "family": "primary",
            "coordinate": _coordinate(_PRIMARY_COORDINATE),
            "r": r_value,
            "comparator": "primary",
            "grid": "primary_61_cubed",
            "inactive_positive_zero": False,
        })

    # D011 (6,6,6) on its declared 13-cubed subgrid -- amendment :81
    _require(_D011_AXIS_COUNT == 13 and _D011_MATCHED_COUNT == 13 ** 3,
             "the frozen D011 subgrid must be 13-cubed")
    if _D011_ROW_ENABLED:
        rows.append({
            "family": "d011",
            "coordinate": _coordinate(_D011_COORDINATE),
            "r": 1.0,
            "comparator": "primary",
            "grid": "d011_matched_13_cubed",
            "inactive_positive_zero": False,
        })

    # V-14 0.5x and 2x -- amendment :82-83
    for scale, tuples in (("0.5x", _V14_HALF), ("2x", _V14_DOUBLE)):
        _require(len(tuples) == 4, f"V-14 {scale} must list exactly four coordinates")
        for triple in tuples:
            for axis, label in zip(triple, ("card", "sector", "budget")):
                _axis_index(axis, scale, f"V-14 {scale} {label} axis")
            rows.append({
                "family": "v14",
                "scale": scale,
                "coordinate": _coordinate(triple),
                "r": 1.0,
                "comparator": "primary",
                "grid": f"v14_{scale}_axis",
                "inactive_positive_zero": False,
            })

    # The list is closed.  There is deliberately NO total-row-count guard here:
    # the row count can only drift by way of the r set (guarded above) or a
    # V-14 scale list length (guarded below), and a total-count check could only
    # ever fire after one of those, so it would be unreachable and therefore
    # unverified.  The fixture asserts the exact 12 rows directly.
    _require(len(rows) == BASE_COORDINATE_COUNT,
             f"the frozen base list must be exactly {BASE_COORDINATE_COUNT} rows, got {len(rows)}")
    duplicate = _duplicate_row_index(rows)
    _require(duplicate == -1, f"the validation list contains a duplicate row at index {duplicate}")
    return tuple(rows)


def d013_repeat_coordinates() -> tuple:
    """Return the D013 repeat rows: primary (30,30,30) for C, CB, CS, CSB.

    Amendment :84-85, quoted by the WP0 audit at :929-956: the repeated unit is
    the PRIMARY COORDINATE under four conditions, not the whole coordinate
    list.  "4 conditions x 5 D015 pairs x 2 encodings = 40", so this is +40
    comparisons, not +400.
    """
    conditions = _require_unique_conditions(D013_CONDITIONS, "D013 condition")
    shape = _repeat_shape()
    _require(len(conditions) == D013_CONDITIONS_PER_REPEAT
             == D013_REPEAT_COORDINATE_COUNT,
             "the amendment names exactly four D013 repeat conditions, C, CB, CS and CSB, "
             f"not {len(conditions)}")
    _require(set(conditions) == set(_FROZEN_D013_CONDITIONS),
             f"the D013 repeat conditions must be exactly C, CB, CS and CSB, not "
             f"{list(conditions)}")
    return tuple({"condition": condition, **shape} for condition in conditions)


def _repeat_shape() -> dict:
    """The shape every D013 repeat row must have, independent of the condition.

    This is the check that makes the D013 repeat count load-bearing.  The caller
    supplies only WHICH conditions ran; the number of rows follows from that
    list.  An empty, duplicated, or reordered condition list is refused here.
    """
    return {
        "family": "d013_repeat",
        "coordinate": _coordinate(_PRIMARY_COORDINATE),
        "r": 1.0,
        "comparator": "primary",
        "grid": "primary_61_cubed",
        # The amendment requires "their inactive +0.0 families" (amendment :85).
        # This flag is what the +0.0 capability refusal keys on.
        "inactive_positive_zero": True,
    }


def _require_no_repeated_conditions(members: list, label: str) -> None:
    """Refuse a repeated condition name.  Split out so a fixture can neutralise
    the duplicate rule ALONE and show it is that rule which refuses a list such
    as ("C","CB","CS","CSB","CSB"), in which CS has silently vanished."""
    for index, name in enumerate(members):
        for earlier in members[:index]:
            _require(name != earlier, f"the {label} list repeats {name!r}")


def _require_unique_conditions(conditions: object, label: str) -> None:
    """Refuse an empty, malformed, or repeated condition list.  Returns a tuple.

    Round 2: the round-1 builder checked only that the condition list was a
    non-empty tuple of names, so a list carrying CSB twice (and CS dropped)
    produced a repeat list that no longer matched the amendment, yet the
    builder accepted it.  This check is public-driven, so the fixture can reach
    it by calling the builder under a patched condition list -- and the frozen
    count below is checked against the LIST THAT WAS SUPPLIED, not against a
    restatement of the frozen four.
    """
    members = _sequence_list(conditions, f"the {label} list")
    _require(members, f"the {label} list must not be empty")
    for name in members:
        _require(type(name) is str and name,
                 f"the {label} list must contain non-empty names, got {type(name).__name__}")
    _require_no_repeated_conditions(members, label)
    return tuple(members)


def _require_exact_row_list(got_rows: object, expected_rows: tuple, label: str) -> None:
    """Refuse anything that is not EXACTLY the frozen list, entry by entry.

    The comparison is element-wise on every key, so a forged list cannot be
    waved through by being the right length, and an omitted coordinate or an
    omitted encoding is caught before a single comparison runs.  A row that is
    not even a mapping is refused here, by name and with its index.
    """
    got_members = _sequence_list(got_rows, f"the {label} list")
    _require(len(got_members) == len(expected_rows),
             f"the {label} must have exactly {len(expected_rows)} rows, got {len(got_members)}")
    for index, (got, want) in enumerate(zip(got_members, expected_rows)):
        # _mapping_copy is the narrowing: it refuses a non-mapping by name and
        # returns a plain dict, so a separate isinstance test here would be a
        # duplicate of a check that has already fired.
        have = _mapping_copy(got, f"{label} row {index} must be a mapping")
        missing = sorted(set(want) - set(have))
        _require(not missing, f"{label} row {index} is missing keys: {missing}")
        extra = sorted(set(have) - set(want))
        _require(not extra, f"{label} row {index} carries undeclared keys: {extra}")
        _require(_row_fields_match(want, have),
                 f"{label} row {index} is not the frozen row: {sorted(have.items(), key=str)!r}")


def _validate_coordinates(coordinates: object) -> tuple:
    expected = build_validation_coordinates()
    _require_exact_row_list(coordinates, expected, "validation coordinate list")
    return expected


def _validate_d013_rows(coordinates: object) -> tuple:
    expected = d013_repeat_coordinates()
    _require_exact_row_list(coordinates, expected, "D013 repeat list")
    return expected


def _require_frozen_multiplicities() -> None:
    """Refuse a session that has lost a comparator pair or an encoding.

    The amendment says "under every D015 comparator pair" and "for both
    encodings".  A session that silently ran four pairs, or one encoding, would
    otherwise produce a smaller comparison set and a pass verdict.  Checked
    against frozen counts, not against the live product, so a dropped item is
    named as a dropped item.
    """
    _require(len(D015_COMPARATOR_PAIRS) == FROZEN_COMPARATOR_COUNT,
             f"every D015 comparator pair must be compared: the frozen set is "
             f"{FROZEN_COMPARATOR_COUNT}, this session has {len(D015_COMPARATOR_PAIRS)}")
    _require(D015_COMPARATOR_PAIRS[0] == (_d011_matched_subgrid.PRIMARY_C_H,
                                          _d011_matched_subgrid.PRIMARY_C_F),
             "the first D015 comparator pair must be the frozen primary pair")
    _require(tuple(sorted(_d011_runner.DIAGNOSTIC_PAIRS)) == tuple(sorted(
               (c_h, c_f) for c_h, c_f in D015_COMPARATOR_PAIRS if (c_h, c_f) !=
               (_d011_matched_subgrid.PRIMARY_C_H, _d011_matched_subgrid.PRIMARY_C_F))),
             "the four frozen D015 diagnostic pairs are not all present")
    _require(len(_ENCODINGS) == FROZEN_ENCODING_COUNT,
             f"both encodings must be compared: the frozen set is "
             f"{FROZEN_ENCODING_COUNT}, this session has {len(_ENCODINGS)}")
    _require(set(_ENCODINGS) == set(_d011_matched_subgrid.ENCODINGS),
             "the compared encodings are not the frozen Gate-6 encodings")


def _iter_units(rows: object):
    """Yield (row, comparator_pair, encoding) in the frozen, deterministic order."""
    members = _sequence_list(rows, "the unit row list")
    for row in members:
        for pair in D015_COMPARATOR_PAIRS:
            for encoding in _ENCODINGS:
                yield row, pair, encoding


def _word_bits(value: object, label: str) -> str:
    """Canonical bit-exact text for one binary64 word.

    float.hex() is exact and round-trips, so two words are bit-for-bit equal
    iff their hex text is equal.  A non-finite word is refused here rather than
    compared, which is the fail-closed half of the amendment's
    "explicit non-finite detection" (:44-49).
    """
    _require(type(value) is float, f"{label} must be a float, not {type(value).__name__}")
    _require(value == value and value not in (float("inf"), float("-inf")),
             f"{label} is non-finite")
    return value.hex()


def _energy_words(payload: object, label: str) -> tuple:
    words = _sequence_list(payload["energy_minimum_words"],
                           f"{label} energy-minimum words")
    _require(words, f"{label} energy-minimum words must be a non-empty sequence")
    return tuple(_word_bits(word, f"{label} energy-minimum word") for word in words)


def _canonical_index(payload: object, label: str) -> int:
    value = payload["canonical_minimum_index"]
    _require(type(value) is int,
             f"{label} canonical minimum index must be an integer, not {type(value).__name__}")
    _require(value >= 0, f"{label} canonical minimum index must be non-negative")
    return value


def _tie_flags(payload: object, label: str) -> tuple:
    flags = _sequence_list(payload["tie_flags"], f"{label} tie flags")
    out: list = []
    for flag in flags:
        _require(type(flag) is int,
                 f"{label} tie flag must be an integer, not {type(flag).__name__}")
        _require(0 <= flag <= 7, f"{label} tie flag {flag} is outside the legal 0..7 set")
        out.append(flag)
    return tuple(out)


def _reconstruction(payload: object, label: str) -> str:
    value = payload["reconstruction"]
    _require(type(value) is str,
             f"{label} reconstruction must be a string, not {type(value).__name__}")
    _require(value, f"{label} reconstruction must be non-empty")
    return value


def _canonical_comparison(payload: object, label: str) -> tuple:
    """Reduce a backend result to a fully canonical, bit-exact comparison tuple.

    The four required fields are checked as an exact key set FIRST, so a backend
    that omits one is refused by name instead of surfacing as a raw KeyError
    from whichever field accessor happened to run first.  An undeclared extra
    field is refused too: a backend that quietly returns an approximate energy
    alongside the required fields has not produced a comparable record.

    Nothing here keeps a value for output.  The tuple exists only to be
    compared and then discarded; the Section B item 3 record never receives it.
    """
    have = _mapping_copy(payload, f"{label} result")
    missing = sorted(set(COMPARISON_FIELDS) - set(have))
    _require(not missing, f"{label} is missing required comparison fields: {missing}")
    extra = sorted(set(have) - set(COMPARISON_FIELDS))
    _require(not extra, f"{label} returned undeclared fields: {extra}")
    return (
        _energy_words(have, label),
        _canonical_index(have, label),
        _tie_flags(have, label),
        _reconstruction(have, label),
    )


def _no_float_or_bool(value: object, label: str) -> None:
    """Refuse a float or bool leaf anywhere in a structure.  Returns None.

    Round 2: round 1 used ``isinstance(value, dict)`` here, so a mapping that was
    not a dict -- exactly what a caller may hand in -- skipped the recursion
    entirely.  The dispatch is now on Mapping/Sequence, so the sweep actually
    walks a non-dict mapping, and every leaf is rejected with its own index.
    """
    if type(value) in (float, bool):
        raise SectionB2HarnessError(f"{label} may not contain float or bool leaves")
    if isinstance(value, Mapping):
        for key, nested in value.items():
            _require(type(key) is str, f"{label} keys must be strings")
            _no_float_or_bool(nested, f"{label}[{key!r}]")
    elif isinstance(value, (tuple, list)):
        for index, nested in enumerate(value):
            _no_float_or_bool(nested, f"{label}[{index}]")


def validate_section_b2_record(record: object) -> str:
    """Validate a Section B item 3 record and return its own content hash.

    The key set is closed.  Counters are integers; identities are lowercase
    SHA-256 strings; the digest is a lowercase SHA-256.  A float or bool leaf
    anywhere refuses, which is what makes a coordinate-level scientific value
    structurally impossible in this record rather than merely absent.

    This function is the RECORD CONTRACT.  It is called UNCONDITIONALLY by the
    run on the record the run itself built, so a record can only be issued if it
    satisfies every check below.  It is also public, so the fixture drives it on
    its own on hand-built and tampered records: each check is reached by a
    record the HARNESS did not build, rather than only by a self-check of a
    constant the harness had just written.
    """
    have = _mapping_copy(record, "the Section B item 3 record")
    _require(set(have) == _RECORD_KEYS,
             f"Section B item 3 record has wrong key set: {sorted(have)}")
    _require(have["schema"] == RECORD_SCHEMA, "Section B item 3 record schema mismatch")
    _require(have["verdict"] in ("passed", "failed"),
             "Section B item 3 record verdict must be 'passed' or 'failed'")
    counters = _mapping_copy(have["counters"], "Section B item 3 counters")
    _require(set(counters) == _COUNTER_KEYS,
             f"Section B item 3 counters have the wrong key set: {sorted(counters)}")
    for key in sorted(counters):
        _int(counters[key], f"counter {key}")
    identities = _mapping_copy(have["identities"], "Section B item 3 identities")
    _require(set(identities) == _IDENTITY_KEYS,
             f"Section B item 3 identities have the wrong key set: {sorted(identities)}")
    for key in sorted(identities):
        _sha(identities[key], f"identity {key}")
    _sha(have["validation_digest"], "validation digest")
    _sha(have["content_sha256"], "record content hash")
    _require_content_hash_match(have)
    # Section B item 3: "It retains no unapproved coordinate-level scientific
    # values in the qualification record."  A float or bool leaf is exactly
    # such a value.
    _no_float_or_bool(have, "the Section B item 3 record")
    return have["content_sha256"]


def _call_injected(func: object, label: str, *args: object) -> object:
    """Call an injected identity function, converting ANY exception to the typed error.

    Same rule as ``_call_backend``: whatever an injected ``validate`` or
    ``exact_match`` raises -- including its own declared mismatch exception, a
    ``KeyError`` from a malformed payload or a ``BaseException`` -- surfaces as
    ``SectionB2HarnessError``, so this module's refusal is the only failure type
    a caller ever sees from this module.  Nothing is written on the way out.
    """
    try:
        return func(*args)
    except SectionB2HarnessError:
        raise
    except BaseException as exc:
        raise SectionB2HarnessError(
            f"the injected {label} raised {type(exc).__name__}; the session is "
            f"fail-closed and no record is written: {exc}") from exc


def _require_content_hash_match(have: object) -> None:
    """Refuse a record whose content hash is not the hash of its own body.

    Split out by name so the fixture can neutralise THIS comparison alone and
    show that the content-hash SHAPE check beside it is load-bearing rather than
    masked by this one's message.  Without the split, a malformed hash is
    refused either way and neither check can be shown to matter.
    """
    _require(have["content_sha256"] == content_sha256(have),
             "Section B item 3 record content hash mismatch")


def _identity_hashes(accepted_identity: object, validate: object,
                     accepted_identity_sha256: object, protocol_identity_sha256: object) -> dict:
    _require(callable(validate),
             f"the injected identity validate(payload) -> sha256-hex must be callable, "
             f"not {type(validate).__name__}")
    # The accepted payload's mapping-ness was already established by
    # _require_identity_match, which runs before any comparison; re-checking it
    # here would be a duplicate of a check that has already fired.
    raw = _call_injected(validate, "identity validate(payload)", accepted_identity)
    computed = _sha(raw, f"injected validate(payload) result, which returned {type(raw).__name__}")
    _require(computed == _sha(accepted_identity_sha256, "accepted identity hash"),
             "the injected validate(payload) disagrees with the supplied accepted identity hash")
    return {
        "accepted_identity_sha256": computed,
        "session_identity_sha256": _sha(accepted_identity_sha256, "accepted identity hash"),
        "protocol_identity_sha256": _sha(protocol_identity_sha256, "protocol identity hash"),
    }


def _require_identity_match(exact_match: object, session_identity: object,
                            accepted_identity: object) -> None:
    """Call the injected exact_match(session, accepted); it raises on any difference.

    This module does not re-implement identity equality: WP1 owns that rule and
    is still under review.  The harness only guarantees the call happens BEFORE
    any comparison, and that the injected matcher's refusal -- however it is
    spelled -- reaches the caller as this module's typed error rather than as an
    exception type the caller must know about.  Both arguments are checked to be
    mappings first, so a caller cannot smuggle in a non-mapping and have the
    injected matcher interpret it however it likes.
    """
    _require(isinstance(session_identity, Mapping),
             f"the session identity payload must be a mapping, not {type(session_identity).__name__}")
    _require(isinstance(accepted_identity, Mapping),
             f"the accepted identity payload must be a mapping, not {type(accepted_identity).__name__}")
    _require(callable(exact_match),
             f"the injected exact_match(session, accepted) must be callable, not {type(exact_match).__name__}")
    _call_injected(exact_match, "identity exact_match(session, accepted)",
                   session_identity, accepted_identity)


def _require_rows_visited(total_rows: int, rows_visited: int) -> None:
    """Refuse a run that did not visit every coordinate row's full comparison set.

    rows_visited counts units actually compared; total_rows x COMPARISONS_PER_ROW
    is what a correct iteration must produce.  Split out as a named function so
    the fixture can neutralise THIS check alone and show that the comparison-
    count check behind it is itself load-bearing rather than masked.
    """
    _require(total_rows == rows_visited // COMPARISONS_PER_ROW,
             "the number of coordinate rows visited does not match the frozen list length")


def _comparison_digest(verdicts: object) -> str:
    """Canonical validation digest over the ordered per-comparison verdicts.

    Only the ordered pass/fail verdicts are hashed.  No value, no coordinate and
    no field payload enters the digest, so the digest is a commitment to "these
    comparisons were run in this order and all of them agreed" without
    retaining what was compared.
    """
    marks = _sequence_list(verdicts, "the ordered verdict list")
    for index, mark in enumerate(marks):
        _require(type(mark) is str, f"verdict {index} must be a string, not {type(mark).__name__}")
    # Every element is a str by the check above, so json.dumps cannot fail here
    # and there is no failure path to guard.  Round 1 wrapped this in a bare
    # try/except whose raise no fixture could ever reach.
    body = json.dumps({"schema": "decisions_os/g9_section_b2_validation_digest/v1",
                       "comparison_count": len(marks),
                       "verdicts": marks}, sort_keys=True,
                      separators=(",", ":"), ensure_ascii=True).encode("ascii")
    return hashlib.sha256(body).hexdigest()


def _require_callable_backend(backend: object, name: str) -> Callable:
    _require(callable(backend),
             f"{name} must be a callable returning the four comparison fields, "
             f"not {type(backend).__name__}")
    return backend


def _run_comparisons(rows: object, device: object, reference: object) -> list:
    """Compare every (row, comparator pair, encoding) unit and return the verdicts.

    Both backends are invoked through ``_call_backend``, so ANY exception a
    backend or the reference raises becomes the harness's own typed error: a
    ``RuntimeError`` from a CUDA launch, a ``MemoryError`` from an allocation and
    a deliberate ``BaseException`` are all fail-closed refusals here, and none of
    them can reach a caller as an untyped crash.
    """
    verdicts: list = []
    for row, pair, encoding in _iter_units(rows):
        unit = (f"{row['family']}{'/' + row['condition'] if 'condition' in row else ''}"
                f" {row['coordinate']} r={row['r']!r} c_H={pair[0]} c_f={pair[1]} {encoding}")
        got = _canonical_comparison(
            _call_backend(device, "device_backend", row, pair, encoding),
            f"device_backend [{unit}]")
        want = _canonical_comparison(
            _call_backend(reference, "python_reference", row, pair, encoding),
            f"python_reference [{unit}]")
        if got != want:
            differing = next(
                (name for name, left, right in zip(COMPARISON_FIELDS, got, want) if left != right),
                "the comparison tuples",
            )
            raise SectionB2HarnessError(
                f"bit-for-bit mismatch in {differing} at {unit}; the session is fail-closed "
                "and no record is written"
            )
        verdicts.append("pass")
    return verdicts


def _sealed_record(verdicts: object, identities: object, total_rows: int,
                   repeat_rows: int) -> dict:
    """Build the Section B item 3 record, seal it, and validate it.  No branch.

    Round 3: the sealing (``content_sha256``) and the record-contract validation
    were deleted from the run in round 2, so the record as ISSUED carried no
    content hash and was never checked.  They are back, and UNCONDITIONAL: there
    is no code path -- not the D013 path, not the plain path, not a later future
    path -- that returns a record without a content hash, and none that returns
    an unvalidated one.  A record that fails its own contract is raised, not
    returned.
    """
    counters = {
        "comparisons": len(verdicts),
        "passed": len(verdicts),
        "failed": 0,
        "coordinate_rows": total_rows,
        "d013_repeat_rows": repeat_rows,
    }
    record = {
        "schema": RECORD_SCHEMA,
        "verdict": "passed",
        "counters": counters,
        "identities": identities,
        "validation_digest": _comparison_digest(verdicts),
    }
    record["content_sha256"] = content_sha256(record)
    validate_section_b2_record(record)
    return record


def run_section_b2(device_backend: object, python_reference: object, coordinates: object,
                   *, accepted_identity: object, session_identity: object,
                   validate_identity: object, exact_match: object,
                   accepted_identity_sha256: object, protocol_identity_sha256: object,
                   d013_fired: bool = False, d013_coordinates: object = None) -> dict:
    """Run the Section B item 2 comparison set and return the item 3 record.

    ``device_backend`` and ``python_reference`` are injected callables invoked as
    ``backend(row, comparator_pair, encoding)`` and returning a mapping with
    exactly the four fields of ``COMPARISON_FIELDS``.  This module evaluates no
    energy and derives no value of its own.  ANY exception either injected
    callable raises is converted to ``SectionB2HarnessError``; nothing else can
    escape this function.

    The run is fail-closed.  The first missing field, non-finite word, or
    bit-for-bit mismatch raises ``SectionB2HarnessError`` and NO record is
    returned, so a partial pass can never be mistaken for a pass.

    When ``d013_fired`` is true the D013 repeat is mandatory and is unlocked
    ONLY by the backend's own plain-data ``supports_inactive_positive_zero = True``
    declaration, read statically so that no backend code runs to answer it.
    There is no caller flag, and a backend that does not declare it -- which
    includes the qualified v1 backend, refused at
    research/g9/cuda_qualification/stage2_cuda_core_bridge.cu:29 -- raises
    ``SectionB2D013UnsupportedError`` BEFORE any comparison runs.  It is never
    skipped.  A descriptor-shaped declaration (a property, a function, a
    ``__getattr__`` answer) is not a declaration at all and is refused the same
    way, whether it would have said True or raised.

    The record returned always carries its ``content_sha256`` and has already
    passed ``validate_section_b2_record``; the caller receives nothing else.
    """
    fired = _exact_bool(d013_fired, "d013_fired")
    device = _require_callable_backend(device_backend, "device_backend")
    reference = _require_callable_backend(python_reference, "python_reference")

    # The +0.0 declaration is read from the BACKEND, before anything else is
    # trusted, because it decides whether the D013 repeat may run at all.
    supports_zero = _backend_declares_positive_zero(device)

    # Identity first: nothing is compared against a backend this session may not
    # use.  The injected matcher owns the equality rule, but every refusal it or
    # the injected validate raises is converted to this module's typed error.
    _require_identity_match(exact_match, session_identity, accepted_identity)

    # Both encodings and all five comparator pairs, or no run at all.
    _require_frozen_multiplicities()

    rows = _validate_coordinates(coordinates)

    repeat_rows: tuple = ()
    if fired:
        if not supports_zero:
            # v1 refuses inactive +0.0 at stage2_cuda_core_bridge.cu:29, so the
            # repeat is unavailable until the WP6b additive path exists.  The
            # amendment requires the repeat, so the only honest answer is a
            # typed refusal, not a skipped row and not a pass.
            raise SectionB2D013UnsupportedError(
                "D013 fired and requires the inactive +0.0 repeat at primary (30,30,30) "
                "for C, CB, CS and CSB, but this device backend does not declare "
                f"{POSITIVE_ZERO_DECLARATION} = True; the qualified v1 backend refuses "
                "inactive families at "
                "research/g9/cuda_qualification/stage2_cuda_core_bridge.cu:29. The "
                "repeat is refused, not skipped, until the WP6b additive +0.0 path "
                "exists, and only the backend's own declaration can enable it."
            )
        _require(d013_coordinates is not None,
                 "D013 fired, so its repeat coordinate list must be supplied")
        repeat_rows = _validate_d013_rows(d013_coordinates)

    identities = _identity_hashes(accepted_identity, validate_identity,
                                  accepted_identity_sha256, protocol_identity_sha256)

    all_rows = tuple(rows) + repeat_rows
    total_rows = len(all_rows)
    verdicts = _run_comparisons(all_rows, device, reference)
    # The frozen product: coordinate-rows x D015 comparator pairs x encodings.
    # This is the arithmetic that catches a dropped coordinate or a dropped
    # encoding even if the iterator above were somehow short.
    _require_rows_visited(total_rows, len(verdicts))
    _require(len(verdicts) == total_rows * COMPARISONS_PER_ROW,
             "the comparison count does not match the frozen coordinate x comparator x encoding product")
    return _sealed_record(verdicts, identities, total_rows, len(repeat_rows))


def cost_estimate(d013_fired: bool = False) -> dict:
    """ESTIMATE ONLY.  No domain is enumerated and no timing is taken here.

    Reports the number of full-domain comparisons a session must run with and
    without the D013 repeat, times the two measured per-coordinate-row costs
    from research/g9/pilot_stage2_cpu_cost.py, and labels every figure.
    """
    fired = _exact_bool(d013_fired, "d013_fired")
    rows = BASE_COORDINATE_COUNT + (D013_REPEAT_COORDINATE_COUNT if fired else 0)
    comparisons = rows * COMPARISONS_PER_ROW
    return {
        "comparisons_without_d013": BASE_COORDINATE_COUNT * COMPARISONS_PER_ROW,
        "comparisons_with_d013": (BASE_COORDINATE_COUNT + D013_REPEAT_COORDINATE_COUNT) * COMPARISONS_PER_ROW,
        "coordinate_rows": rows,
        "comparators_per_row": len(D015_COMPARATOR_PAIRS),
        "encodings_per_row": len(_ENCODINGS),
        "reference_seconds": rows * REFERENCE_SECONDS_PER_ROW,
        "numpy_seconds": rows * NUMPY_SECONDS_PER_ROW,
    }


def print_cost_estimate(d013_fired: bool = False) -> dict:
    """Print the cost estimate in the pilot's labelled style.  Returns the estimate."""
    estimate = cost_estimate(d013_fired)
    rows_with = BASE_COORDINATE_COUNT + D013_REPEAT_COORDINATE_COUNT
    reference_with = rows_with * REFERENCE_SECONDS_PER_ROW
    numpy_with = rows_with * NUMPY_SECONDS_PER_ROW
    print("=" * 78)
    print("COST ESTIMATE (ESTIMATES ONLY -- no domain is enumerated, no timing taken)")
    print(f"    comparator pairs (D015) per row  : {estimate['comparators_per_row']}")
    print(f"    encodings per row                : {estimate['encodings_per_row']}")
    print(f"    coordinate-rows, D013 unfired    : {BASE_COORDINATE_COUNT}")
    print(f"    full-domain comparisons, no D013 : {estimate['comparisons_without_d013']}")
    print(f"    coordinate-rows, D013 fired      : {rows_with}")
    print(f"    full-domain comparisons, D013    : {estimate['comparisons_with_d013']}")
    print(f"    pure-Python reference            : {REFERENCE_SECONDS_PER_ROW:.1f} s per coordinate-row "
          f"[ESTIMATE: {REFERENCE_COST_NOTE}, research/g9/pilot_stage2_cpu_cost.py]")
    print(f"    NumPy bit-exact path             : {NUMPY_SECONDS_PER_ROW:.1f} s per coordinate-row "
          f"[ESTIMATE: {NUMPY_COST_NOTE}, research/g9/pilot_stage2_cpu_cost.py]")
    print(f"    reference total, D013 unfired    : "
          f"{BASE_COORDINATE_COUNT * REFERENCE_SECONDS_PER_ROW:,.0f} s "
          f"({BASE_COORDINATE_COUNT * REFERENCE_SECONDS_PER_ROW / 60.0:,.1f} min) "
          f"[EXTRAPOLATED: per-row cost x rows]")
    print(f"    NumPy total, D013 unfired        : "
          f"{BASE_COORDINATE_COUNT * NUMPY_SECONDS_PER_ROW:,.0f} s "
          f"({BASE_COORDINATE_COUNT * NUMPY_SECONDS_PER_ROW / 60.0:,.1f} min) "
          f"[EXTRAPOLATED: per-row cost x rows]")
    print(f"    reference total, D013 fired      : {reference_with:,.0f} s "
          f"({reference_with / 60.0:,.1f} min) [EXTRAPOLATED: per-row cost x rows]")
    print(f"    NumPy total, D013 fired          : {numpy_with:,.0f} s "
          f"({numpy_with / 60.0:,.1f} min) [EXTRAPOLATED: per-row cost x rows]")
    print("    one full-domain comparison = 1,048,576 decoded states, both encodings, all 5 D015 pairs")
    print("    Owner decides feasibility; see GATE_9_SECTION_B_CLOSURE_PLAN_DRAFT.md:68-70.")
    print("=" * 78)
    return estimate

#!/usr/bin/env python3
"""Synthetic fixtures for the Section B item 2 in-session full-domain harness.

Run under the pinned interpreter twice, in both modes:

    python3 -B  research/g9/verify_stage2_section_b2_harness_fixtures.py
    python3 -B -O research/g9/verify_stage2_section_b2_harness_fixtures.py

The full 2^20 domain is NEVER run here.  Both backends are synthetic
stand-ins that return small synthetic payloads; this harness is a record-shaping
and refusal harness, not a numerical one.  No candidate, no instance, no ground
truth, no energy and no scientific value is produced or asserted.  Nothing is
written to the project tree: the only checks that touch the filesystem read and
compare, and all temporary work belongs to the caller.

These fixtures deliberately avoid ``assert`` and use ``require``/``refused``
instead, so a run under ``-O`` checks exactly what a normal run checks.  A bare
``hasattr``/existence test is never the only evidence for a check: each one
drives the public function and observes a typed refusal.

Every public argument of every public entry point is fuzzed with None, bool,
int, str, list, dict, an unhashable value and a nested wrong-type value, and
every refusal must be the harness's OWN typed error.  A raw exception of another
type is a fixture failure, not a pass: it would mean the check is being
satisfied by an incidental crash.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
# Snapshot bytecode BEFORE any project import.  The real project carries a
# tracked baseline of .pyc files, so the test is "unchanged", never "zero".
PYC_BEFORE = set(ROOT.rglob("*.pyc"))
TREE_BEFORE = set(p for p in (ROOT / "research").rglob("*") if p.is_file())
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from research.g9 import stage2_section_b2_harness as h  # noqa: E402


class FixtureError(RuntimeError):
    pass


class Unhashable:
    """Unhashable AND not comparable to a dict, a list or a numpy-like value."""

    __hash__ = None  # type: ignore[assignment]

    def __eq__(self, other):
        return NotImplemented

    def __repr__(self):
        return "<unhashable>"


class HostileMapping(dict):
    """A real Mapping whose iteration explodes, to prove the typed guard works."""

    def keys(self):
        raise RuntimeError("keys() was called on a hostile mapping")

    def __iter__(self):
        raise RuntimeError("iteration was attempted on a hostile mapping")


COUNT = 0
RESULTS: list = []


def require(condition: object, message: str) -> None:
    global COUNT
    if not condition:
        raise FixtureError(message)
    COUNT += 1


def refused(fn, label: str, needle: str = "", error=None) -> None:
    """Drive fn and require it is refused with the harness's OWN typed error.

    A raw exception of another type is a fixture failure, not a pass: it would
    mean the check is being satisfied by an incidental crash.  When ``needle``
    is given, the refusal must also name the reason, so a check cannot be
    repointed to fail for an unrelated reason and still look green.  ``error``
    may be a tuple of acceptable types: the fuzz below drives an argument whose
    rejection is legitimately owned by the INJECTED matcher rather than by the
    harness, and the harness's own type is still a correct outcome for it.
    """
    global COUNT
    expected = error or h.SectionB2HarnessError
    names = (expected.__name__ if isinstance(expected, type)
             else ", ".join(one.__name__ for one in expected))
    try:
        fn()
    except expected as exc:
        if needle and needle not in str(exc):
            raise FixtureError(f"{label}: refused for the wrong reason: {exc}") from exc
        COUNT += 1
        return
    except Exception as exc:
        raise FixtureError(f"{label}: raw {type(exc).__name__} instead of "
                           f"{names}: {exc}") from exc
    raise FixtureError(f"{label}: accepted")


def record(name: str, ok: bool, detail: str = "") -> bool:
    RESULTS.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))
    return ok


# ---------------------------------------------------------------------------
# Synthetic stand-ins.  Nothing here computes an energy.
# ---------------------------------------------------------------------------

def ulp_up(value: float) -> float:
    """The next representable binary64 above value: exactly one ulp."""
    return struct.unpack("<d", struct.pack("<Q", struct.unpack("<Q", struct.pack("<d", value))[0] + 1))[0]


def fake_payload(row: dict, pair: tuple, encoding: str) -> dict:
    """A deterministic synthetic four-field payload.  No physics, no domain."""
    seed = f"{row['family']}|{row.get('scale')}|{row.get('condition')}|{row['coordinate']}|" \
           f"{row['r']}|{pair[0]}|{pair[1]}|{encoding}"
    digest = hashlib.sha256(seed.encode("ascii")).digest()
    return {
        "energy_minimum_words": tuple(
            float(int.from_bytes(digest[index:index + 2], "big")) / 65536.0 for index in (0, 2, 4)
        ),
        "canonical_minimum_index": int.from_bytes(digest[6:10], "big"),
        "tie_flags": tuple(digest[index] & 7 for index in (10, 11)),
        "reconstruction": digest.hex()[:32],
    }


_NO_RAW = object()


def make_backend(mutate=None, name: str = "device", raw=_NO_RAW):
    def backend(row, pair, encoding):
        if raw is not _NO_RAW:
            return raw
        payload = fake_payload(row, pair, encoding)
        if mutate is not None:
            payload = mutate(payload, row, pair, encoding)
        return payload
    backend.fixture_name = name
    return backend


def make_raising_backend(exc, name: str = "raising"):
    """A device backend that RAISES on every comparison, like a crashed launch."""
    def backend(row, pair, encoding):
        raise exc
    backend.fixture_name = name
    return backend


def honest_device(row, pair, encoding):
    return fake_payload(row, pair, encoding)


def honest_reference(row, pair, encoding):
    return fake_payload(row, pair, encoding)


# ROUND 4: the +0.0 declaration must be read WITHOUT EXECUTING the backend, so
# the side-effect counter is the evidence.  Every line below is appended by the
# property, descriptor or __getattr__ body ITSELF, so a non-empty counter proves
# that body ran.  read_declaration() drains it before and after each probe, so a
# leftover entry can never be mistaken for a fresh execution.
_DECLARATION_EXECUTIONS: list = []


def read_declaration(backend) -> object:
    """Read the declaration through the harness, proving NOTHING executed.

    The value is the harness's own answer, so the caller can assert on the
    decision as well as on the absence of execution.  If the harness ever
    executes a declaration, this raises a FixtureError rather than returning --
    that is the round-4 defect this whole block exists to catch.
    """
    del _DECLARATION_EXECUTIONS[:]
    try:
        return h._backend_declares_positive_zero(backend)
    finally:
        ran = list(_DECLARATION_EXECUTIONS)
        del _DECLARATION_EXECUTIONS[:]
        if ran:
            raise FixtureError(
                f"the harness EXECUTED the backend's +0.0 declaration: {ran!r}. The "
                f"declaration must be read statically, so that no backend code runs "
                f"and no exception from it can escape.")


# Backend OBJECTS, which are how the +0.0 capability is declared.  Round 3: the
# D013 repeat is unlocked only by the attribute the BACKEND carries; there is no
# caller flag.  Round 4 supersedes the SHAPE rule: the declaration is read with
# inspect.getattr_static, so only a CLASS-level plain-data True counts and every
# descriptor is refused.  These classes are the whole declaration matrix.

class PlainBackend:
    """A backend with NO declaration at all -- this is what v1 looks like."""

    def __call__(self, row, pair, encoding):
        return fake_payload(row, pair, encoding)


class V1Backend(PlainBackend):
    """The qualified v1 shape: callable, and silent about +0.0."""


class DeclaredFalseBackend(PlainBackend):
    """A backend that explicitly declares that it does NOT support +0.0."""
    supports_inactive_positive_zero = False


class DeclaredReadOnlyBackend(PlainBackend):
    """A backend declaring +0.0 through a read-ONLY property.

    ROUND 4: this is REFUSED, where round 3 accepted it.  A read-only property is
    still a DESCRIPTOR, and an ordinary attribute read would execute it.
    Accepting one would put the round-3 defect straight back, so a property is
    refused whether it would have answered True or raised -- which is precisely
    why the refusal is by SHAPE: a property that raises is never executed to
    discover that it raises.
    """
    _declared = True

    @property
    def supports_inactive_positive_zero(self):
        _DECLARATION_EXECUTIONS.append("readonly-property")
        return self._declared


class DeclaredConstantTrueBackend(PlainBackend):
    """A backend declaring +0.0 as a class-level PLAIN DATA True.  ACCEPTED."""
    supports_inactive_positive_zero = True


class DeclaredInstanceTrueBackend(PlainBackend):
    """A backend declaring +0.0 as an instance PLAIN DATA True, set in __init__.

    ROUND 4 DECISION, class vs instance.  Both are judged for PLAIN-DATA-ness
    and the accepted form is the CLASS attribute.  An instance attribute is
    plain data, but it is assignable after construction, so it cannot be told
    apart from a caller's claim -- which is the round-3 defect that let a
    caller unlock the repeat.  It is therefore refused by the same rule, on
    both the D013 and the plain path.  A backend that wants the declaration
    declares it on its type.
    """

    def __init__(self):
        self.supports_inactive_positive_zero = True


class WritablePropertyBackend(PlainBackend):
    """A backend whose declaration is a WRITABLE property -- a caller's claim."""
    _declared = False

    @property
    def supports_inactive_positive_zero(self):
        _DECLARATION_EXECUTIONS.append("writable-property")
        return self._declared

    @supports_inactive_positive_zero.setter
    def supports_inactive_positive_zero(self, value):
        self._declared = value


class PerInstanceClaimBackend(PlainBackend):
    """A backend that merely ACCEPTS an assignment -- again a caller's claim."""


def declaring_backend(declared):
    """A PlainBackend carrying the claim as a per-instance attribute (writable)."""
    backend = PlainBackend()
    backend.supports_inactive_positive_zero = declared
    return backend


class RaisingDeclarationBackend(PlainBackend):
    """A backend whose +0.0 declaration raises an EXCEPTION when it is read."""
    @property
    def supports_inactive_positive_zero(self):
        _DECLARATION_EXECUTIONS.append("raising-property")
        raise RuntimeError("the +0.0 probe failed")


# ---------------------------------------------------------------------------
# ROUND 4 fixture backends.  The counter and read_declaration() are defined
# above, before the first backend, so every class body below can log.
# ---------------------------------------------------------------------------

class _RaisingBaseException(BaseException):
    """NOT an Exception subclass, so the round-3 `except Exception` cannot see it."""


class _ExplodingPropertyBackend(PlainBackend):
    """A property declaration that raises a BaseException, and COUNTS ITSELF.

    Round 3's blocking defect: the guard around the declaration read caught only
    Exception, so this BaseException escaped run_section_b2 untyped.  The fix is
    NOT to catch BaseException -- that would swallow KeyboardInterrupt and
    SystemExit -- but to never run the property at all.  The counter is the
    proof: if the harness executed this getter, the log would be non-empty
    whatever it caught.
    """

    @property
    def supports_inactive_positive_zero(self):
        _DECLARATION_EXECUTIONS.append("exploding-property")
        raise _RaisingBaseException("the +0.0 declaration was executed and raised")


class _TruePropertyBackend(PlainBackend):
    """A property declaration that answers True, and counts itself if executed."""

    @property
    def supports_inactive_positive_zero(self):
        _DECLARATION_EXECUTIONS.append("true-property")
        return True


class _GetattrBackend(PlainBackend):
    """A backend that claims +0.0 ONLY through __getattr__, and counts itself."""

    def __getattr__(self, name):
        _DECLARATION_EXECUTIONS.append(f"getattr:{name}")
        if name == h.POSITIVE_ZERO_DECLARATION:
            return True
        raise AttributeError(name)


class _ClassAndInstanceTrueBackend(PlainBackend):
    """A class True AND an instance True: the instance claim still loses."""

    supports_inactive_positive_zero = True

    def __init__(self):
        self.supports_inactive_positive_zero = True


class _ClassAndInstanceFalseBackend(PlainBackend):
    """A class True shadowed by an instance False: the instance claim still wins
    the refusal, so this backend does not declare +0.0."""

    supports_inactive_positive_zero = True

    def __init__(self):
        self.supports_inactive_positive_zero = False


class _SlottedPlainDataBackend(PlainBackend):
    """A backend carrying the declaration as a slot value -- plain data, no dict."""

    __slots__ = (h.POSITIVE_ZERO_DECLARATION,)

    def __init__(self):
        setattr(self, h.POSITIVE_ZERO_DECLARATION, True)


class _CustomDescriptorBackend(PlainBackend):
    """A custom descriptor protocol the harness does not know about by name."""

    def __get__(self, obj, objtype=None):
        _DECLARATION_EXECUTIONS.append("custom-descriptor")
        return True


class _ServingMetaclass(type):
    """A metaclass that serves the +0.0 name to every instance of its type.

    A METACLASS attribute is a descriptor on the instance: an ordinary
    ``getattr`` would run its ``__get__``.  It is the same shape of hazard as a
    property, one level further out, and is refused for the same reason.
    """

    def __get__(self, obj, objtype=None):
        _DECLARATION_EXECUTIONS.append("metaclass-descriptor")
        return True


class _MetaclassPropertyBackend(PlainBackend, metaclass=_ServingMetaclass):
    """A backend whose +0.0 declaration is served by its METACLASS."""


class _NoDictBackend(PlainBackend):
    """A backend whose type supplies no instance __dict__ at all."""

    __slots__ = ()


# DELETED, round 4: a metaclass whose __mro__/mro() diverge, to drive an
# "the two static read paths must agree" check in the harness.  That check was
# itself removed -- a single inspect.getattr_static read is the reference for
# what an attribute lookup returns, and the only shape on which a class-dict
# walk would disagree is a class-level property shadowed by a plain-data
# INSTANCE attribute, which the per-instance rule refuses first -- so this
# fixture would reach nothing.  It also cannot be built: inspect reads
# __mro__ through the C-level type.__dict__ slot wrapper, which a Python-level
# __mro__ or __getattribute__ override does not intercept, so it never actually
# diverged.  Reason for deletion: unreachable fixture for a removed check.


class NonBoolDeclarationBackend(PlainBackend):
    """A backend whose declaration is a number, not a bool."""
    supports_inactive_positive_zero = 1


class CallableDeclarationBackend(PlainBackend):
    """A backend whose declaration is callable -- NOT a declaration."""
    supports_inactive_positive_zero = staticmethod(lambda: True)


# Injected WP1 identity stand-ins.  WP1 is under review and is NOT imported.
_ACCEPTED_IDENTITY = {
    "schema": "decisions_os/g9_synthetic_qualification_identity/v1",
    "platform": {"gpu_name": "synthetic-device", "compute_capability": "0.0",
                 "cuda_driver_version": "0", "cuda_runtime_version": "0",
                 "nvcc_version": "0", "kaggle_image": "synthetic",
                 "python_version": "0.0.0", "numpy_version": "0.0.0"},
    "source_sha256": {"research/g9/synthetic_source.cu": hashlib.sha256(b"synthetic").hexdigest()},
    "compiler_flags": ["-O0", "--fmad=false"],
}
_ACCEPTED_IDENTITY["content_sha256"] = hashlib.sha256(
    json.dumps({k: v for k, v in _ACCEPTED_IDENTITY.items() if k != "content_sha256"},
               sort_keys=True, separators=(",", ":")).encode("ascii")).hexdigest()

_SESSION_IDENTITY = copy.deepcopy(_ACCEPTED_IDENTITY)
_OTHER_IDENTITY = copy.deepcopy(_ACCEPTED_IDENTITY)
_OTHER_IDENTITY["platform"]["gpu_name"] = "different-device"


class SyntheticIdentityMismatch(Exception):
    """The injected exact_match refuses on any difference."""


def synthetic_validate(payload) -> str:
    body = {k: v for k, v in payload.items() if k != "content_sha256"}
    return hashlib.sha256(json.dumps(body, sort_keys=True,
                                     separators=(",", ":")).encode("ascii")).hexdigest()


def synthetic_exact_match(session, accepted) -> None:
    if json.dumps(session, sort_keys=True) != json.dumps(accepted, sort_keys=True):
        raise SyntheticIdentityMismatch("session identity does not exactly match the accepted identity")


IDENTITY_KWARGS = {
    "accepted_identity": _ACCEPTED_IDENTITY,
    "session_identity": _SESSION_IDENTITY,
    "validate_identity": synthetic_validate,
    "exact_match": synthetic_exact_match,
    "accepted_identity_sha256": _ACCEPTED_IDENTITY["content_sha256"],
    "protocol_identity_sha256": hashlib.sha256(b"synthetic-protocol").hexdigest(),
}


# A sentinel, so an explicit ``run(device=None)`` really passes None to the
# harness instead of silently falling back to the default backend.
_DEFAULT = object()


def run(device=_DEFAULT, reference=_DEFAULT, coordinates=_DEFAULT, **overrides):
    kwargs = dict(IDENTITY_KWARGS)
    kwargs.update(overrides)
    return h.run_section_b2(
        honest_device if device is _DEFAULT else device,
        honest_reference if reference is _DEFAULT else reference,
        (h.build_validation_coordinates() if coordinates is _DEFAULT else coordinates),
        **kwargs,
    )


def run_d013(device, coordinates=_DEFAULT, **overrides):
    """A D013-FIRED run against the given backend OBJECT.

    There is no capability keyword to pass: round 3 removed it, and the whole
    point of every D013 fixture is that the backend alone decides.  A
    ``reference=`` override is honoured so the reference slot can be fuzzed on
    this path too.  ``coordinates`` uses the same sentinel as ``run`` so an
    explicit None really reaches the harness.
    """
    reference = overrides.pop("reference", _DEFAULT)
    kwargs = dict(IDENTITY_KWARGS)
    kwargs["d013_fired"] = True
    kwargs["d013_coordinates"] = (h.d013_repeat_coordinates() if coordinates is _DEFAULT
                                 else coordinates)
    kwargs.update(overrides)
    return h.run_section_b2(device,
                            honest_reference if reference is _DEFAULT else reference,
                            h.build_validation_coordinates(), **kwargs)


# The fuzz corpus: one entry per public argument of every public entry point.
# Every entry is a malformed value of a kind the task names explicitly.
FUZZ = (
    ("none", None),
    ("bool", True),
    ("int", 7),
    ("str", "not-the-expected-type"),
    ("list", [1, 2, 3]),
    ("dict", {"a": 1}),
    ("unhashable", Unhashable()),
    ("nested-wrong-type", {"a": [1, {"b": (2, 3)}]}),
)

# The subset that is falsy, so each typed accessor is also driven on its false
# branch rather than only on its type branch.
FUZZ_FALSY = (
    ("none", None),
    ("bool-false", False),
    ("zero-int", 0),
    ("empty-str", ""),
    ("empty-list", []),
    ("empty-dict", {}),
    ("empty-tuple", ()),
)


class _ExplodingEquality(dict):
    def __eq__(self, other):
        raise RuntimeError("equality was attempted on a hostile mapping")


class _ExplodingItems(dict):
    def items(self):
        raise RuntimeError("items() was called on a hostile mapping")


# ---------------------------------------------------------------------------
# 1. The frozen coordinate list is exact
# ---------------------------------------------------------------------------

def check_coordinate_list() -> None:
    rows = h.build_validation_coordinates()
    require(isinstance(rows, tuple), "the coordinate list must be a tuple")
    require(len(rows) == 12, f"the frozen list must be 12 rows, got {len(rows)}")

    expected = [
        ("primary", None, None, (30, 30, 30), 0.5),
        ("primary", None, None, (30, 30, 30), 1.0),
        ("primary", None, None, (30, 30, 30), 2.0),
        ("d011", None, None, (6, 6, 6), 1.0),
        ("v14", None, "0.5x", (0, 0, 0), 1.0),
        ("v14", None, "0.5x", (15, 15, 15), 1.0),
        ("v14", None, "0.5x", (30, 30, 30), 1.0),
        ("v14", None, "0.5x", (30, 0, 15), 1.0),
        ("v14", None, "2x", (0, 0, 0), 1.0),
        ("v14", None, "2x", (55, 55, 55), 1.0),
        ("v14", None, "2x", (110, 110, 110), 1.0),
        ("v14", None, "2x", (110, 0, 55), 1.0),
    ]
    got = [(row["family"], row.get("condition"), row.get("scale"), row["coordinate"], row["r"])
           for row in rows]
    require(got == expected,
            f"the frozen coordinate list drifted:\n  expected {expected}\n  got      {got}")

    # The r set really is the frozen src/g6 one, not a restatement of it.
    require([row["r"] for row in rows[:3]] == [0.5, 1.0, 2.0], "the r rows are not {0.5,1,2}")
    require(len(h.D015_COMPARATOR_PAIRS) == 5, "there must be exactly 5 D015 comparator pairs")
    require(h.D015_COMPARATOR_PAIRS[0] == (2048, 2048), "the primary D015 pair must be (2048,2048)")
    require(len(h.D013_CONDITIONS) == 4 and h.D013_CONDITIONS == ("C", "CB", "CS", "CSB"),
            "the D013 conditions must be exactly C, CB, CS, CSB")
    require(h.COMPARISON_FIELDS == ("energy_minimum_words", "canonical_minimum_index",
                                    "tie_flags", "reconstruction"),
            "the four required comparison fields drifted")

    repeats = h.d013_repeat_coordinates()
    require(len(repeats) == 4, f"the D013 repeat must be 4 rows, got {len(repeats)}")
    require([row["condition"] for row in repeats] == ["C", "CB", "CS", "CSB"],
            "the D013 repeat conditions drifted")
    require(all(row["coordinate"] == (30, 30, 30) for row in repeats),
            "the D013 repeat is at primary (30,30,30) only, not the whole list")
    require(all(row["inactive_positive_zero"] for row in repeats),
            "every D013 repeat row must be marked as an inactive +0.0 family")
    require(not any(row["inactive_positive_zero"] for row in rows),
            "no base coordinate row is a +0.0 family")

    # The builder takes no arguments at all: there is no override path through
    # which a caller could ask for a different list.
    refused(lambda: h.build_validation_coordinates((30, 30, 30)),
            "the coordinate builder with an argument", "positional argument",
            error=TypeError)
    record("coordinate list is exact (12 rows, count and members)", True)


# ---------------------------------------------------------------------------
# 2. A one-ulp difference in each of the four fields is caught
# ---------------------------------------------------------------------------

def check_one_ulp_in_each_field() -> None:
    def bump_words(payload, row, pair, encoding):
        payload["energy_minimum_words"] = (ulp_up(payload["energy_minimum_words"][0]),
                                          *payload["energy_minimum_words"][1:])
        return payload

    def bump_index(payload, row, pair, encoding):
        payload["canonical_minimum_index"] = payload["canonical_minimum_index"] + 1
        return payload

    def bump_tie(payload, row, pair, encoding):
        payload["tie_flags"] = ((payload["tie_flags"][0] + 1) & 7, *payload["tie_flags"][1:])
        return payload

    def bump_reconstruction(payload, row, pair, encoding):
        payload["reconstruction"] = payload["reconstruction"][:-1] + "0"
        return payload

    for mutate, field, needle in (
        (bump_words, "energy_minimum_words", "energy_minimum_words"),
        (bump_index, "canonical_minimum_index", "canonical_minimum_index"),
        (bump_tie, "tie_flags", "tie_flags"),
        (bump_reconstruction, "reconstruction", "reconstruction"),
    ):
        # A one-ulp difference is a DIFFERENCE, not a rounding tolerance.  If the
        # comparison were done with a tolerance, this would pass silently.
        refused(lambda mutate=mutate: run(device=make_backend(mutate, f"ulp-{field}")),
                f"one-ulp difference in {field}", needle)
        record(f"one-ulp difference in {field} is caught", True)

    # The mismatch is located by NAME, not merely detected: the message must say
    # which of the four fields differed.
    try:
        run(device=make_backend(bump_words, "ulp-named"))
    except h.SectionB2HarnessError as exc:
        require("mismatch in energy_minimum_words" in str(exc),
                f"the mismatch must be located by field name, got: {exc}")
    else:
        raise FixtureError("the one-ulp mismatch did not fire")

    # A tie-flag difference that stays inside the legal 0..7 set, so the range
    # check cannot be what catches it: only the equality comparison can.
    def bump_tie_in_range(payload, row, pair, encoding):
        payload["tie_flags"] = tuple((flag + 1) & 7 for flag in payload["tie_flags"])
        return payload
    refused(lambda: run(device=make_backend(bump_tie_in_range, "tie-in-range")),
            "an in-range tie-flag difference", "mismatch in tie_flags")

    # The same, on the PYTHON REFERENCE side: the harness is not one-sided.
    refused(lambda: run(reference=make_backend(bump_index, "ref-ulp")),
            "a one-ulp difference in the Python reference", "mismatch in canonical_minimum_index")

    # Control: the honest backends must pass, so the four refusals above are
    # caused by the injected ulp and not by a harness that always refuses.
    record_result = run()
    require(record_result["verdict"] == "passed", "the honest control run did not pass")
    record("honest backends pass (control for the ulp refusals)", True)


# ---------------------------------------------------------------------------
# 3. A missing coordinate or encoding is caught
# ---------------------------------------------------------------------------

def check_missing_coordinate_or_encoding() -> None:
    rows = h.build_validation_coordinates()
    for drop_index, label in ((0, "first"), (5, "middle"), (11, "last")):
        short = rows[:drop_index] + rows[drop_index + 1:]
        refused(lambda short=short: run(coordinates=short),
                f"missing coordinate ({label} row dropped)", "exactly 12 rows")

    # One row too many: length is checked, so an appended row is caught too.
    refused(lambda: run(coordinates=rows + (rows[0],)),
            "an extra coordinate row", "exactly 12 rows")

    # Right count, wrong member: a coordinate silently substituted.
    substituted = list(rows)
    substituted[0] = {**substituted[0], "coordinate": (31, 30, 30)}
    refused(lambda: run(coordinates=tuple(substituted)),
            "substituted coordinate", "not the frozen row")

    # Right count, right coordinates, wrong r on the primary rows.
    bad_r = list(rows)
    bad_r[1] = {**bad_r[1], "r": 1.5}
    refused(lambda: run(coordinates=tuple(bad_r)), "drifted r value", "not the frozen row")

    # A V-14 scale transposed onto the wrong row.
    bad_scale = list(rows)
    bad_scale[8] = {**bad_scale[8], "scale": "0.5x"}
    refused(lambda: run(coordinates=tuple(bad_scale)), "a transposed V-14 scale",
            "not the frozen row")

    # The +0.0 flag flipped on a base row: the base list must never claim a +0.0
    # family, so this is refused by the same element-wise row test.
    bad_zero = list(rows)
    bad_zero[0] = {**bad_zero[0], "inactive_positive_zero": True}
    refused(lambda: run(coordinates=tuple(bad_zero)), "a +0.0 flag on a base row",
            "not the frozen row")

    # The comparator label drifted.
    bad_comparator = list(rows)
    bad_comparator[0] = {**bad_comparator[0], "comparator": "diagnostic"}
    refused(lambda: run(coordinates=tuple(bad_comparator)), "a drifted comparator label",
            "not the frozen row")

    # A coordinate supplied as a list rather than a tuple.  ``[30,30,30] ==
    # (30,30,30)`` is True in Python, so a plain == would accept it; the row
    # test compares the exact types, which is what catches it.
    list_coordinate = list(rows)
    list_coordinate[0] = {**list_coordinate[0], "coordinate": [30, 30, 30]}
    refused(lambda: run(coordinates=tuple(list_coordinate)),
            "a coordinate given as a list, not a tuple", "not the frozen row")

    # An undeclared extra key on an otherwise-correct row.
    extra_key = list(rows)
    extra_key[3] = {**extra_key[3], "approximation": "synthetic"}
    refused(lambda: run(coordinates=tuple(extra_key)),
            "undeclared row key", "undeclared keys")

    # A dropped key on an otherwise-correct row.
    missing_key = list(rows)
    missing_key[2] = {k: v for k, v in missing_key[2].items() if k != "grid"}
    refused(lambda: run(coordinates=tuple(missing_key)),
            "missing row key", "missing keys")

    # A row that is not a mapping at all, at several positions.
    for position in (0, 6, 11):
        for bad_row, label in ((None, "none"), ("row", "a string"),
                               (7, "an int"), ([1, 2], "a list"),
                               ((30, 30, 30), "a bare tuple")):
            broken = list(rows)
            broken[position] = bad_row
            refused(lambda broken=broken: run(coordinates=tuple(broken)),
                    f"a {label} in row {position}", "must be a mapping")

    # A row carrying a non-string key.  The declared-key set is unchanged, so
    # neither the missing-keys nor the undeclared-keys test can see it; the
    # mapping copy's string-key rule is the only thing that refuses it.
    int_key_row = dict(rows[0])
    int_key_row[7] = "primary_61_cubed"
    keyed = list(rows)
    keyed[0] = int_key_row
    refused(lambda: run(coordinates=tuple(keyed)),
            "an integer row key", "keys must all be strings")

    # A V-14 coordinate outside that scale's frozen axis count.  The amendment's
    # 2x list tops out at 110 and 0.5x at 30, so a 0.5x row carrying a 2x index
    # is a misread scale.  The check that catches this is _axis_index, inside the
    # BUILDER, because run_section_b2's entry-by-entry row test would refuse a
    # substituted coordinate first.  So the misread scale is injected into the
    # builder's own frozen tuple table -- which is exactly the mistake the check
    # exists to catch: someone transcribing (55,55,55) into the 0.5x list from
    # the 2x list above it.
    original_half = h._V14_HALF
    original_double = h._V14_DOUBLE
    for scale, table, original, bad_axis in (
            # a 2x index transcribed into the 0.5x list, which ends at 30
            ("0.5x", "_V14_HALF", original_half, (55, 55, 55)),
            # an index past the frozen 2x axis count of 111
            ("2x", "_V14_DOUBLE", original_double, (120, 120, 120))):
        setattr(h, table, (bad_axis,) + original[1:])
        try:
            refused(lambda: h.build_validation_coordinates(),
                    f"a {scale} coordinate outside its frozen axis count",
                    "outside the V-14")
        finally:
            setattr(h, table, original)

    # ...and that check is load-bearing: with _axis_index neutralised the very
    # same misread scale is accepted by the builder.
    original_axis = h._axis_index
    h._axis_index = lambda value, scale, label: value
    try:
        h._V14_HALF = ((55, 55, 55),) + original_half[1:]
        misread_accepted = h.build_validation_coordinates()
        require(misread_accepted[4]["coordinate"] == (55, 55, 55),
                "disabling _axis_index did not let the misread 0.5x scale through")
    finally:
        h._V14_HALF = original_half
        h._axis_index = original_axis

    # A non-integer axis inside a frozen V-14 triple.  The range check alone
    # would accept a float, so the type check is what refuses it.
    for bad_axis, label in ((30.0, "a float axis"), (True, "a bool axis"),
                            ("30", "a string axis")):
        setattr(h, "_V14_HALF", ((bad_axis, 0, 0),) + original_half[1:])
        try:
            refused(lambda: h.build_validation_coordinates(),
                    f"a V-14 {label}", "must be an integer")
        finally:
            h._V14_HALF = original_half

    # A dropped encoding.  The encodings multiply every row, so removing one
    # halves the comparison set; the frozen multiplicity check must notice by
    # name, not merely as a downstream arithmetic mismatch.
    original_encodings = h._ENCODINGS
    h._ENCODINGS = ("unbalanced",)
    try:
        refused(lambda: run(), "dropped encoding", "both encodings must be compared")
    finally:
        h._ENCODINGS = original_encodings

    # A dropped comparator pair, same shape.
    original_pairs = h.D015_COMPARATOR_PAIRS
    h.D015_COMPARATOR_PAIRS = original_pairs[:4]
    try:
        refused(lambda: run(), "dropped D015 comparator pair",
                "every D015 comparator pair must be compared")
    finally:
        h.D015_COMPARATOR_PAIRS = original_pairs

    # A comparator pair that is not one of the four frozen diagnostics: the
    # count check alone would pass, so the identity check must catch it.
    h.D015_COMPARATOR_PAIRS = ((2048, 2048), (1024, 2048), (4096, 2048),
                               (2048, 1024), (4096, 4096))
    try:
        refused(lambda: run(), "a comparator pair outside the frozen D015 set",
                "diagnostic pairs are not all present")
    finally:
        h.D015_COMPARATOR_PAIRS = original_pairs

    # The primary pair displaced from first position.
    h.D015_COMPARATOR_PAIRS = (original_pairs[1],) + original_pairs[1:]
    try:
        refused(lambda: run(), "the primary comparator pair not compared first",
                "must be the frozen primary pair")
    finally:
        h.D015_COMPARATOR_PAIRS = original_pairs

    # An encoding renamed to something outside the frozen Gate-6 set.
    h._ENCODINGS = ("unbalanced", "slack_renamed")
    try:
        refused(lambda: run(), "an encoding outside the frozen set",
                "not the frozen Gate-6 encodings")
    finally:
        h._ENCODINGS = original_encodings

    # The builder's structural guards, each driven by patching the frozen
    # source constant it reads.  They are unreachable through the public entry
    # point (a caller cannot change src/g6), so without these the guards could
    # be disabled unnoticed -- exactly the failure this package must not repeat.
    original_r = h._R_VALUES
    h._R_VALUES = (0.5, 1.0)
    try:
        refused(lambda: h.build_validation_coordinates(),
                "an r set that is not the frozen three values",
                "the frozen r set must be exactly three values")
    finally:
        h._R_VALUES = original_r

    original_axis_count = h._D011_AXIS_COUNT
    original_matched = h._D011_MATCHED_COUNT
    h._D011_AXIS_COUNT = 14
    try:
        refused(lambda: h.build_validation_coordinates(),
                "a D011 axis count that is not 13", "must be 13-cubed")
    finally:
        h._D011_AXIS_COUNT = original_axis_count
        h._D011_MATCHED_COUNT = original_matched

    # A V-14 scale list that is not four coordinates long.
    h._V14_HALF = ((0, 0, 0), (15, 15, 15), (30, 0, 15))
    try:
        refused(lambda: h.build_validation_coordinates(),
                "a V-14 0.5x list of the wrong length",
                "must list exactly four coordinates")
    finally:
        h._V14_HALF = original_half

    # The total-row-count guard: reached by dropping EXACTLY the D011 row, so
    # the r-set, V-14-length, axis-count and duplicate guards are all still
    # satisfied and the count is the only thing left to notice.
    h._D011_ROW_ENABLED = False
    try:
        refused(lambda: h.build_validation_coordinates(),
                "a base list that is not the frozen twelve rows",
                "exactly 12 rows")
    finally:
        h._D011_ROW_ENABLED = True

    # A duplicated row.  (0,0,0) repeated inside one scale keeps every axis in
    # range, so the duplicate-row guard is the only check that can fire.
    h._V14_HALF = ((0, 0, 0), (0, 0, 0), (15, 15, 15), (30, 0, 15))
    try:
        refused(lambda: h.build_validation_coordinates(),
                "a duplicated coordinate row", "duplicate row")
    finally:
        h._V14_HALF = original_half

    # A duplicate of a DIFFERENT family: a PRIMARY row repeated as another
    # primary row.  A V-14 row sharing the primary COORDINATE is NOT a duplicate
    # -- different family and scale, which the amendment's own list relies on --
    # so the duplicate is made in the r value, which IS part of the row identity.
    h._R_VALUES = (0.5, 0.5, 2.0)
    try:
        refused(lambda: h.build_validation_coordinates(),
                "a repeated primary row", "duplicate row")
    finally:
        h._R_VALUES = original_r

    require(h.build_validation_coordinates() == rows,
            "the frozen constants were not restored after the builder-guard fixtures")
    record("every builder structural guard is load-bearing", True)

    # The honest list still runs, so the refusals above are the mutations'
    # doing and not a permanently-broken harness.
    require(run()["counters"]["comparisons"] == 120,
            "the control run must perform 12 x 5 x 2 = 120 comparisons")
    record("a missing coordinate or encoding is caught", True)


# ---------------------------------------------------------------------------
# 3b. The frozen product arithmetic is load-bearing on its own
# ---------------------------------------------------------------------------

def check_frozen_product() -> None:
    """The two end-of-run product checks are defence in depth.

    Every earlier fixture makes the refusal happen at the INPUT, so neither
    product check ever fires.  They exist to catch a regression in the ITERATOR
    -- a _iter_units that emitted fewer units than rows x pairs x encodings.
    That is unreachable through the public entry point, so it is driven here by
    neutralising the iterator, which is the only way the damage can occur.
    """
    original_iter = h._iter_units

    def short_iterator(rows):
        # Emits one unit per row instead of one per row/pair/encoding.  The
        # payload still matches, so the only thing that can notice is the
        # arithmetic: a short run would otherwise be reported as a PASS with
        # 12 comparisons instead of 120.
        for row in h._sequence_list(rows, "rows"):
            yield row, h.D015_COMPARATOR_PAIRS[0], h._ENCODINGS[0]

    h._iter_units = short_iterator
    try:
        # The first product check refuses.
        refused(lambda: run(), "an iterator that emits too few units",
                "coordinate rows visited does not match the frozen list length")
        # The second is masked by the first, so it is driven in isolation with
        # the first neutralised.  Without this the comparison-count check would
        # be a check that can never fire, and therefore an unverified one.
        original_rows_visited = h._require_rows_visited
        h._require_rows_visited = lambda total_rows, rows_visited: None
        try:
            refused(lambda: run(), "a short run reported as a pass",
                    "frozen coordinate x comparator x encoding product")
        finally:
            h._require_rows_visited = original_rows_visited
    finally:
        h._iter_units = original_iter

    # The unit iterator's OWN row-list narrowing, driven directly on the real
    # function: a row list that is not a tuple/list is refused, typed, rather
    # than unpacking into an opaque ValueError in the consumer.
    for label, value in (("a string", "abc"), (None, "a None"), (7, "an int"),
                         ({"a": 1}, "a dict"), (Unhashable(), "an unhashable")):
        refused(lambda value=value: list(h._iter_units(value)),
                f"the unit iterator over {label}", "must be a tuple or list")

    # ...and the honest iterator is restored, so the refusals above are the
    # mutation's doing.
    require(run()["counters"]["comparisons"] == 120,
            "the control run must perform 120 comparisons after the iterator is restored")
    record("the frozen comparison-product arithmetic is load-bearing", True)


# ---------------------------------------------------------------------------
# 4. The D013 repeat is unlocked ONLY by the backend's own +0.0 declaration
# ---------------------------------------------------------------------------

def check_d013_refusal() -> None:
    repeats = h.d013_repeat_coordinates()

    # DEFECT 1 (round 3).  The round-2 harness read a CALLER flag,
    # ``device_supports_positive_zero``, so a backend with no declaration at all
    # passed a 160-comparison D013 run when a caller simply said True.  The
    # capability is now declared BY the backend.  These three backends are the
    # cases the validator reported: no declaration, a False declaration, and the
    # v1 shape.  All three must be REFUSED, and none of them can be unlocked by
    # anything a caller passes.
    for backend, label in (
            (V1Backend(), "a v1-shaped backend with no declaration"),
            (PlainBackend(), "a backend with no declaration"),
            (DeclaredFalseBackend(), "a backend declaring +0.0 support = False")):
        refused(lambda backend=backend: run_d013(backend),
                f"D013 repeat on {label}", "does not declare",
                error=h.SectionB2D013UnsupportedError)
    record("D013 repeat is refused without the backend's own +0.0 declaration", True)

    # ...and the refusal is a MISSING declaration, not a False one: both say so.
    # A caller cannot turn either into a pass by passing anything at all, because
    # the capability keyword is no longer part of the signature.  Passing it is
    # itself a refusal -- Python's own unexpected-keyword TypeError, raised
    # before the body runs, so no code path in this module honours it.
    import inspect as _inspect
    parameters = _inspect.signature(h.run_section_b2).parameters
    require("device_supports_positive_zero" not in parameters,
            "the caller capability flag must be gone from the signature")
    require("positive_zero" not in " ".join(parameters) and
            "supports" not in " ".join(parameters),
            "no parameter of the run may enable +0.0 support")
    for dead_flag in (True, False, 1, "yes"):
        refused(lambda dead_flag=dead_flag: h.run_section_b2(
            DeclaredConstantTrueBackend(), honest_reference,
            h.build_validation_coordinates(), **dict(IDENTITY_KWARGS),
            d013_fired=True, d013_coordinates=repeats,
            device_supports_positive_zero=dead_flag),
            f"a caller passing device_supports_positive_zero={dead_flag!r}",
            "unexpected keyword argument", error=TypeError)
        # And on a NON-declaring backend the same dead flag must not rescue it.
        refused(lambda dead_flag=dead_flag: h.run_section_b2(
            V1Backend(), honest_reference, h.build_validation_coordinates(),
            **dict(IDENTITY_KWARGS), d013_fired=True, d013_coordinates=repeats,
            device_supports_positive_zero=dead_flag),
            f"a caller flag rescuing a non-declaring backend ({dead_flag!r})",
            "unexpected keyword argument", error=TypeError)
    record("no caller-supplied flag can enable the D013 repeat", True)

    # A backend that DOES declare +0.0 support, as a CLASS plain-data True, runs
    # the repeat: the refusal is about the capability, not about D013 firing.
    # Round 4: DeclaredReadOnlyBackend is no longer here -- a property is code,
    # and accepting it would reinstate the round-3 defect.  Its refusal is
    # asserted in check_positive_zero_read, and check_d013_refusal asserts the
    # SAME refusal through the full run, so both the read and the run are
    # covered.
    for backend, shape in ((DeclaredConstantTrueBackend(), "a class plain-data True"),):
        fired = run_d013(backend)
        require(fired["counters"]["d013_repeat_rows"] == 4,
                f"the D013 repeat must be 4 rows on {shape}")
        require(fired["counters"]["comparisons"] == 160,
                f"with D013 fired the run must be 16 x 5 x 2 = 160 comparisons on "
                f"{shape}, got {fired['counters']['comparisons']}")
        require(fired["counters"]["coordinate_rows"] == 16,
                f"with D013 fired the run must cover 16 coordinate rows on {shape}")
    record("D013 repeat runs on a +0.0-declaring backend (control)", True)

    # The D013-FIRED record is sealed and validated like every other one.
    sealed = run_d013(DeclaredConstantTrueBackend())
    require(sealed["content_sha256"] == h.content_sha256(sealed),
            "the D013 record must carry its own content hash")
    require(h.validate_section_b2_record(sealed) == sealed["content_sha256"],
            "the D013 record must satisfy the record contract as issued")

    # A DESCRIPTOR-shaped declaration is not a declaration, so the D013 repeat is
    # refused against it -- whether the descriptor would have answered True or
    # would have raised.  Round 3 accepted the read-only property; round 4 does
    # not, and the refusal is by SHAPE so the descriptor is never executed.
    for backend, label in ((DeclaredReadOnlyBackend(), "a read-only property"),
                           (WritablePropertyBackend(), "a writable property"),
                           (_TruePropertyBackend(), "a property that returns True"),
                           (_ExplodingPropertyBackend(), "a property that raises a BaseException"),
                           (RaisingDeclarationBackend(), "a property that raises"),
                           (_GetattrBackend(), "a __getattr__ that returns True"),
                           (_CustomDescriptorBackend(), "a custom descriptor"),
                           (_MetaclassPropertyBackend(), "a metaclass descriptor"),
                           (CallableDeclarationBackend(), "a callable declaration")):
        refused(lambda backend=backend: run_d013(backend),
                f"D013 repeat on {label}", "does not declare",
                error=h.SectionB2D013UnsupportedError)
    # ...and on the UNFIRED path the shape rule is still load-bearing, for the
    # two rules that are not merely "does not declare": a non-bool class claim
    # and an instance claim are MALFORMED declarations, so they are refused with
    # the typed error whether or not D013 fired.  A descriptor, by contrast, is
    # simply "not declared" there -- which is exactly why the shape rule cannot
    # be a side effect of the D013 branch -- so it is asserted to PASS below.
    for backend, label, needle in (
            (NonBoolDeclarationBackend(), "a class declaration of 1",
             "it must be a plain bool data attribute"),
            (declaring_backend(True), "a per-instance True",
             "plain data attribute on its TYPE")):
        refused(lambda backend=backend: run(device=backend),
                f"a malformed +0.0 claim on a plain run ({label})", needle)
    for backend, label in ((DeclaredReadOnlyBackend(), "a read-only property"),
                           (_ExplodingPropertyBackend(), "a property raising a BaseException"),
                           (_GetattrBackend(), "a __getattr__ answer")):
        require(run(device=backend)["verdict"] == "passed",
                f"a {label} is simply 'not declared' on the unfired path and must "
                f"not refuse an otherwise-valid run")
    record("a malformed or per-instance +0.0 claim is refused on both paths", True)

    # A plain non-bool class declaration is a MALFORMED claim, refused by name.
    for value, label in ((1, "an int"), (1.0, "a float"), ("yes", "a string"),
                         ([True], "a list"), ({"yes": True}, "a dict")):
        backend = PlainBackend()
        type(backend).supports_inactive_positive_zero = value
        try:
            refused(lambda backend=backend: run_d013(backend),
                    f"a +0.0 declaration that is {label}", "it must be a plain bool data attribute",
                    error=h.SectionB2HarnessError)
        finally:
            del type(backend).supports_inactive_positive_zero
    refused(lambda: run_d013(NonBoolDeclarationBackend()),
            "a +0.0 declaration of 1 on the class", "it must be a plain bool data attribute",
            error=h.SectionB2HarnessError)
    # ...including on the UNFIRED path, where the capability is unused.
    refused(lambda: run(device=NonBoolDeclarationBackend()),
            "a non-bool declaration on a plain run", "it must be a plain bool data attribute")
    record("a +0.0 declaration that is not a bool is refused", True)

    # The refusal is TYPED and specific: it is the +0.0 subclass, not the bare
    # base class, so a caller can distinguish "no +0.0 path" from other defects.
    try:
        run_d013(V1Backend())
    except h.SectionB2D013UnsupportedError as exc:
        require(isinstance(exc, h.SectionB2HarnessError), "the typed error must subclass the base")
        require("stage2_cuda_core_bridge.cu:29" in str(exc),
                "the refusal must cite the v1 +0.0 refusal site")
        require(h.POSITIVE_ZERO_DECLARATION in str(exc),
                "the refusal must name the declaration the backend lacks")
    else:
        raise FixtureError("the D013 refusal did not fire")

    # ...and it is raised BEFORE any comparison runs, so a session cannot spend
    # a full domain and then discover it may not do the repeat.
    calls = []

    class CountingBackend(V1Backend):
        def __call__(self, row, pair, encoding):
            calls.append(1)
            return fake_payload(row, pair, encoding)

    refused(lambda: run_d013(CountingBackend()),
            "a D013 refusal after comparisons had already run", "does not declare",
            error=h.SectionB2D013UnsupportedError)
    require(calls == [], f"a comparison ran before the D013 refusal ({len(calls)} comparisons)")

    # A +0.0-declaring backend plus a forged repeat list: the repeat list is as
    # closed as the base list, so a caller cannot quietly drop CSB, clear the
    # +0.0 flag, or add a key to make the repeat smaller or cheaper.  All of
    # these run against a backend that DID declare, so the only thing that can
    # refuse them is the row test.
    capable = DeclaredConstantTrueBackend()

    forged = list(repeats)
    forged[2] = {**forged[2], "condition": "CSB"}
    refused(lambda: run_d013(capable, tuple(forged)),
            "forged D013 repeat row", "not the frozen row")

    unflagged = list(repeats)
    unflagged[1] = {**unflagged[1], "inactive_positive_zero": False}
    refused(lambda: run_d013(capable, tuple(unflagged)),
            "a D013 repeat row with the +0.0 flag cleared", "not the frozen row")

    extra = list(repeats)
    extra[0] = {**extra[0], "energy": 1}
    refused(lambda: run_d013(capable, tuple(extra)),
            "a D013 repeat row with an undeclared key", "undeclared keys")

    for bad_row, label in ((None, "none"), ("C", "a string"), (3, "an int"),
                           ([1], "a list"), ((30, 30, 30), "a bare tuple")):
        broken = list(repeats)
        broken[3] = bad_row
        refused(lambda broken=broken: run_d013(capable, tuple(broken)),
                f"a D013 repeat row that is {label}", "must be a mapping")

    # D013 fired but no repeat list supplied at all.
    refused(lambda: run_d013(capable, d013_coordinates=None),
            "D013 fired with no repeat list", "must be supplied")
    record("D013 fired without a repeat list is refused", True)

    # The builder refuses a MALFORMED condition list, a list that is not a
    # tuple, an empty one, and -- the round-2 addition -- one that repeats a
    # condition or carries the wrong number of conditions.  Round 1 accepted
    # ("C","CB","CS","CSB","CSB") because it only checked "non-empty tuple of
    # names"; that produced a five-row repeat in which CS was dropped.
    original_conditions = h.D013_CONDITIONS
    for bad_conditions, label, needle in (
            ((), "no conditions at all", "must not be empty"),
            (("C", 7), "a non-string condition", "non-empty names"),
            (("",), "an empty condition name", "non-empty names"),
            ((None,), "a None condition", "non-empty names"),
            ({"C", "CB"}, "an unordered set", "must be a tuple or list"),
            (7, "an int", "must be a tuple or list"),
            (None, "a None", "must be a tuple or list"),
            (("C", "CB", "CS", "CSB", "CSB"), "a repeated condition", "repeats"),
            (("C", "CB", "CS"), "only three conditions", "exactly four D013 repeat conditions"),
            (("C", "CB", "CS", "CD"), "four conditions, one not in the amendment",
             "must be exactly C, CB, CS and CSB")):
        h.D013_CONDITIONS = bad_conditions
        try:
            refused(lambda: h.d013_repeat_coordinates(),
                    f"the D013 repeat builder with {label}", needle)
        finally:
            h.D013_CONDITIONS = original_conditions
    # A list of the four correct names is a legal, safe input: the builder
    # normalises it to a tuple and the amendment is still satisfied.
    h.D013_CONDITIONS = ["C", "CB", "CS", "CSB"]
    try:
        listed = h.d013_repeat_coordinates()
        require([row["condition"] for row in listed] == ["C", "CB", "CS", "CSB"],
                "a list of the four correct conditions must be accepted")
    finally:
        h.D013_CONDITIONS = original_conditions
    record("a malformed D013 condition list is refused by the builder", True)

    # Each of those three condition guards is separately load-bearing: with only
    # that one guard disabled the very same bad list is accepted.
    # Each condition guard is separately load-bearing.  For each one the bad
    # list is shown to be ACCEPTED when that guard alone is neutralised, with
    # the frozen count and the frozen membership widened to match the bad list
    # so they cannot refuse in its place.  A guard whose removal changes nothing
    # is dead code and must not ship.
    original_guard = h._require_unique_conditions
    original_repeat = h._require_no_repeated_conditions
    original_frozen = h._FROZEN_D013_CONDITIONS
    original_count = h.D013_CONDITIONS_PER_REPEAT
    original_repeat_count = h.D013_REPEAT_COORDINATE_COUNT
    for guard, bad_conditions, relaxed_frozen, label in (
            ("empty", (), (), "an empty list"),
            ("names", ("C", "CB", 7, "CSB"), ("C", "CB", 7, "CSB"),
             "a non-string condition"),
            ("duplicate", ("C", "CB", "CS", "CSB", "CSB"), ("C", "CB", "CS", "CSB", "CSB"),
             "a repeated condition"),
            ("count", ("C", "CB", "CS"), ("C", "CB", "CS"), "only three conditions"),
            ("membership", ("C", "CB", "CS", "CD"), ("C", "CB", "CS", "CD"),
             "a renamed condition")):
        h.D013_CONDITIONS = bad_conditions
        try:
            if guard == "duplicate":
                # Neutralise ONLY the duplicate rule, and align the frozen count
                # and membership so that the remaining guards cannot refuse the
                # bad list in its place.
                h._require_no_repeated_conditions = lambda members, name: None
                h.D013_CONDITIONS_PER_REPEAT = len(bad_conditions)
                h.D013_REPEAT_COORDINATE_COUNT = len(bad_conditions)
                h._FROZEN_D013_CONDITIONS = relaxed_frozen
            elif guard == "count":
                # Neutralise ONLY the count rule: align both frozen counts with
                # the bad list and leave membership at the frozen four, which the
                # three-name list still fails -- so also widen membership.
                h.D013_CONDITIONS_PER_REPEAT = len(bad_conditions)
                h.D013_REPEAT_COORDINATE_COUNT = len(bad_conditions)
                h._FROZEN_D013_CONDITIONS = relaxed_frozen
            else:
                # Neutralise the whole helper, then align count and membership so
                # that neither can refuse on the bad list's behalf.
                h._require_unique_conditions = lambda value, name: tuple(value)
                h.D013_CONDITIONS_PER_REPEAT = len(bad_conditions)
                h.D013_REPEAT_COORDINATE_COUNT = len(bad_conditions)
                h._FROZEN_D013_CONDITIONS = relaxed_frozen
            accepted = h.d013_repeat_coordinates()
            require(len(accepted) == len(bad_conditions),
                    f"{label}: expected {len(bad_conditions)} rows, got {len(accepted)}")
        finally:
            h._require_unique_conditions = original_guard
            h._require_no_repeated_conditions = original_repeat
            h._FROZEN_D013_CONDITIONS = original_frozen
            h.D013_CONDITIONS_PER_REPEAT = original_count
            h.D013_REPEAT_COORDINATE_COUNT = original_repeat_count
            h.D013_CONDITIONS = original_conditions
    record("each D013 condition guard is load-bearing", True)

    # The run's own length gate, driven with a hand-built short list, so it
    # does not depend on the builder refusing first.
    for short in (repeats[:3], repeats + repeats[:1]):
        refused(lambda short=short: run_d013(capable, short),
                "a run with a repeat list of the wrong length", "must have exactly 4 rows")

    # ...and that length gate is load-bearing: with the length half of the row
    # test disabled, a repeat list carrying a DUPLICATE row of the right length
    # would otherwise be accepted, because the run's arithmetic is satisfied by
    # any list of four.  Only the element-wise half catches the duplicate.
    original_exact = h._require_exact_row_list
    h._require_exact_row_list = lambda got_rows, expected_rows, label: None
    try:
        # Length right, membership wrong: the element-wise half is the only
        # thing that can notice, and with it disabled the forged row sails in.
        require(run_d013(capable)["counters"]["comparisons"] == 160,
                "disabling the row test must not change a correct run")
        # PROOF: the same forged list is refused when the row test is whole.
        forged_duplicate = list(repeats)
        forged_duplicate[3] = dict(forged_duplicate[2])
        h._require_exact_row_list = original_exact
        refused(lambda: run_d013(capable, tuple(forged_duplicate)),
                "a D013 repeat row duplicated in place of CSB", "not the frozen row")
    finally:
        h._require_exact_row_list = original_exact
    record("a D013 repeat list of the wrong length is refused by the run", True)


# ---------------------------------------------------------------------------
# 4b. ROUND 4: the +0.0 declaration is read STATICALLY and never executed
# ---------------------------------------------------------------------------

def check_positive_zero_read() -> None:
    """The declaration is read without running a single line of backend code.

    Round 3's blocking defect: ``_backend_declares_positive_zero`` read the
    declaration with ``getattr`` behind an ``except Exception`` guard, so a
    backend whose declaration was a property raising a ``BaseException`` had
    that exception escape ``run_section_b2`` untyped.  The lead's ruling was NOT
    to catch ``BaseException`` -- that would swallow ``KeyboardInterrupt`` and
    ``SystemExit`` -- but to never execute the backend at all.

    Every case here goes through ``read_declaration``, which drains the counter
    before and after and FAILS if any line was appended.  So "the property was
    not executed" is asserted by an observation of the side effect, not by the
    absence of an exception: a harness that swallowed the ``BaseException`` would
    leave the counter non-empty and be caught here, which is precisely the fix
    the ruling forbids and this check must therefore still reject.
    """

    # 1. A property that raises a BaseException, and a property that raises an
    #    Exception: both refused, both NOT executed, both through the full run.
    for backend, label in ((_ExplodingPropertyBackend(), "a property raising a BaseException"),
                           (RaisingDeclarationBackend(), "a property raising a RuntimeError")):
        require(read_declaration(backend) is False,
                f"{label} must read as 'does not declare +0.0'")
        refused(lambda backend=backend: run_d013(backend),
                f"D013 against {label}", "does not declare",
                error=h.SectionB2D013UnsupportedError)
        # The raw BaseException must not escape from the full run either.
        try:
            run_d013(_ExplodingPropertyBackend())
        except h.SectionB2D013UnsupportedError as exc:
            require("BaseException" not in type(exc).__name__,
                    f"the +0.0 refusal must be the typed error, not {type(exc).__name__}")
        except BaseException as exc:  # noqa: BLE001 - the round-3 defect, on purpose
            raise FixtureError(
                f"a BaseException escaped the declaration read untyped: "
                f"{type(exc).__name__}: {exc}") from exc
    record("a raising +0.0 declaration is refused and NEVER executed", True)

    # 2. A property that RETURNS True is still refused, and still not executed.
    #    This is the case a shape check that ran the descriptor would accept.
    require(read_declaration(_TruePropertyBackend()) is False,
            "a property returning True must read as 'does not declare +0.0'")
    refused(lambda: run_d013(_TruePropertyBackend()),
            "D013 against a property that returns True", "does not declare",
            error=h.SectionB2D013UnsupportedError)
    record("a property returning True is refused, not executed", True)

    # 3. A __getattr__ that answers True is refused, and never consulted.
    require(read_declaration(_GetattrBackend()) is False,
            "a __getattr__ answer must read as 'does not declare +0.0'")
    refused(lambda: run_d013(_GetattrBackend()),
            "D013 against a __getattr__ that returns True", "does not declare",
            error=h.SectionB2D013UnsupportedError)
    record("a __getattr__ +0.0 claim is refused, not consulted", True)

    # 4. Class vs instance attribute, DECIDED AND DOCUMENTED.  Both are checked
    #    for plain-data-ness; the accepted form is the CLASS attribute.  An
    #    instance attribute is refused -- by name, so the reason is stated rather
    #    than left to inference -- whether it was set in __init__ or assigned
    #    afterwards, and it wins over a class True in both directions, so a
    #    class True cannot be used to smuggle a caller-set instance claim past.
    require(read_declaration(DeclaredConstantTrueBackend()) is True,
            "a class plain-data True must be ACCEPTED")
    for backend, label in ((DeclaredInstanceTrueBackend(), "an instance True set in __init__"),
                           (_ClassAndInstanceTrueBackend(), "a class True plus an instance True"),
                           (_ClassAndInstanceFalseBackend(), "a class True plus an instance False"),
                           (declaring_backend(True), "an instance True assigned afterwards"),
                           (declaring_backend(False), "an instance False assigned afterwards")):
        refused(lambda backend=backend: h._backend_declares_positive_zero(backend),
                f"a {label} declaration", "plain data attribute on its TYPE",
                error=h.SectionB2HarnessError)
        refused(lambda backend=backend: run_d013(backend),
                f"D013 against a {label} declaration", "plain data attribute on its TYPE",
                error=h.SectionB2HarnessError)
    # A __slots__ value is NOT accepted either, but it is refused as a DESCRIPTOR
    # -- a slot is a member descriptor, so reading it would run one -- and so it
    # answers "does not declare" rather than raising.  It is listed separately so
    # the two refusals are not conflated.
    require(read_declaration(_SlottedPlainDataBackend()) is False,
            "a __slots__ declaration is a member descriptor and must not declare +0.0")
    refused(lambda: run_d013(_SlottedPlainDataBackend()),
            "D013 against a __slots__ declaration", "does not declare",
            error=h.SectionB2D013UnsupportedError)
    record("class vs instance: class True accepted, every instance claim refused", True)

    # 5. A plain class True is accepted end to end: it is the ONLY accepted shape.
    fired = run_d013(DeclaredConstantTrueBackend())
    require(fired["counters"]["comparisons"] == 160,
            f"a class plain-data True must run the full 160-comparison D013 repeat, "
            f"got {fired['counters']['comparisons']}")
    require(h.validate_section_b2_record(fired) == fired["content_sha256"],
            "the D013 record on a class-declaring backend must satisfy its contract")
    record("a plain class True is accepted and runs the D013 repeat", True)

    # 6. Every other backend object is answered, never raised on, whatever its
    #    shape -- so the read itself cannot be a source of untyped escapes.
    for label, backend in (("a bare object", object()),
                           ("no-dict backend", _NoDictBackend()),
                           ("a custom descriptor", _CustomDescriptorBackend()),
                           ("a metaclass descriptor", _MetaclassPropertyBackend()),
                           ("a writable property", WritablePropertyBackend()),
                           ("a read-only property", DeclaredReadOnlyBackend()),
                           ("a class False", DeclaredFalseBackend())):
        require(read_declaration(backend) is False,
                f"{label} must read as 'does not declare +0.0'")

    # 6b. A CLASS passed as the backend.  This is the one shape whose instance
    #     __dict__ is a mappingproxy, so `vars()` returns something that is not
    #     a dict -- and that is the harness's own "carries no readable instance
    #     __dict__" refusal.  A class is callable, so it clears the callability
    #     guard and reaches the declaration read, which is why this check is
    #     reachable at all rather than masked by an earlier one.  It is a
    #     MALFORMED claim (a class is not a backend instance), so it refuses
    #     with the typed error on BOTH paths, never with a raw AttributeError.
    class _ClassAsBackend:
        supports_inactive_positive_zero = True

    refused(lambda: h._backend_declares_positive_zero(_ClassAsBackend),
            "a class passed as the backend", "no readable instance __dict__",
            error=h.SectionB2HarnessError)
    refused(lambda: run_d013(_ClassAsBackend),
            "D013 against a class passed as the backend", "no readable instance __dict__",
            error=h.SectionB2HarnessError)
    refused(lambda: run(device=_ClassAsBackend),
            "a class passed as the backend on a plain run", "no readable instance __dict__",
            error=h.SectionB2HarnessError)
    record("a class passed as the backend is refused, not misread as declared", True)

    # 7. The read is fuzzed with the whole wrong-type corpus: a non-backend
    #    value has no declaration, so it reads False rather than raising.  The
    #    harness never sees these (a non-callable is refused earlier, by the
    #    callability guard), which is why the read is driven directly here.
    for label, value in FUZZ + FUZZ_FALSY:
        require(read_declaration(value) is False,
                f"_backend_declares_positive_zero over {label} must answer False")
    record("every backend shape and fuzz value reads False, none raises", True)

    # 8. The descriptor probe is load-bearing on its own, and it executes
    #    nothing: with it neutralised, a property would be misread as a MALFORMED
    #    claim (a typed refusal) instead of "does not support +0.0", and a class
    #    True shadowed by an instance claim would no longer be distinguished.
    #    Shown by driving the probe directly over the descriptor zoo.
    for value, is_descriptor in (
            (property(lambda self: True), True),
            (True, False), (False, False), (1, False), ("yes", False),
            (None, False), ([True], False), ({"yes": True}, False),
            (staticmethod(lambda: True), True), (classmethod(lambda cls: True), True),
            (lambda self: True, True), (_CustomDescriptorBackend.__get__, True),
            (_ServingMetaclass.__get__, True),
            # A BOUND method defines none of the three slots: its type is
            # `method`, whose binding behaviour lives in __func__/__self__ and is
            # implemented in C.  So probing the three descriptor slots correctly
            # answers False, and the value is refused as a MALFORMED claim rather
            # than as a descriptor.  Either way the repeat is refused and no
            # backend code runs; only the message differs.  The comment on the
            # bound-method refusal below records the same point.
            ((lambda self: True).__get__(object()), False)):
        require(h._is_descriptor(value) is is_descriptor,
                f"_is_descriptor({type(value).__name__}) must be {is_descriptor}, "
                f"not {h._is_descriptor(value)}")
    # ...and the bound-method shapes are still refused, so the classification
    # above cannot be read as an acceptance of a callable declaration.  The READ
    # is driven directly here: a bound method is callable, so as a class-dict
    # value it would also make the backend itself callable-via-that-slot, which
    # is not what these cases are about.
    for bound in ((lambda self: True).__get__(object()),
                  (classmethod(lambda cls: True).__get__(DeclaredConstantTrueBackend))):
        probe_type = type("_BoundDeclarationProbe", (PlainBackend,),
                          {h.POSITIVE_ZERO_DECLARATION: bound})
        refused(lambda probe=probe_type(): h._backend_declares_positive_zero(probe),
                f"a bound {type(bound).__name__} declaration",
                "it must be a plain bool data attribute",
                error=h.SectionB2HarnessError)
    # ...and the UNBOUND ones are descriptors, so they answer "does not declare"
    # rather than raising -- read_declaration proves both the answer and that
    # nothing ran, so no separate refusal is expected or wanted here.
    for unbound in (lambda self: True, staticmethod(lambda: True),
                    classmethod(lambda cls: True)):
        probe_type = type("_UnboundDeclarationProbe", (PlainBackend,),
                          {h.POSITIVE_ZERO_DECLARATION: unbound})
        require(read_declaration(probe_type()) is False,
                f"an unbound {type(unbound).__name__} is a descriptor and must not "
                f"declare +0.0")
    record("the descriptor probe classifies every shape and runs nothing", True)


# ---------------------------------------------------------------------------
# 5. The record carries no coordinate-level value
# ---------------------------------------------------------------------------

# The pristine sealing function, captured before any probe replaces it.
_original_content_sha256 = h.content_sha256


def _seal(record: dict) -> dict:
    record["content_sha256"] = h.content_sha256(record)
    return record


def _blank_record() -> dict:
    return {
        "schema": h.RECORD_SCHEMA,
        "verdict": "passed",
        "counters": {"comparisons": 120, "passed": 120, "failed": 0,
                     "coordinate_rows": 12, "d013_repeat_rows": 0},
        "identities": {"accepted_identity_sha256": "a" * 64,
                       "session_identity_sha256": "b" * 64,
                       "protocol_identity_sha256": "c" * 64},
        "validation_digest": "d" * 64,
    }


def check_no_coordinate_level_value() -> None:
    result = run()

    # DEFECT 2 (round 3).  The round-2 run returned a record with FIVE keys and no
    # content hash, and never called the record contract; the fixture papered
    # over that by ADDING the hash itself before validating.  The record AS
    # ISSUED must therefore be passed straight to the contract, with no repair.
    # Round 2's record raised here for its wrong key set, so this fixture fails
    # on the .r2 code.
    require(set(result) == h._RECORD_KEYS,
            f"the returned record must carry exactly the contract key set, "
            f"got {sorted(result)}")
    require("content_sha256" in result,
            "the record the run returns must carry its own content hash")
    require(result["content_sha256"] == h.content_sha256(result),
            "the returned record's content hash must be the hash of its own body")
    require(h.validate_section_b2_record(result) == result["content_sha256"],
            "the record the run returns must satisfy the record contract AS ISSUED")
    record("the run returns a sealed, validated record as issued", True)

    # Sealing and validation are UNCONDITIONAL: every path out of the run carries
    # them.  Each of the three would have to be reachable, and each is driven here
    # by disabling it and observing that the run either stops validating or hands
    # back a record the contract refuses.
    for path, build in (
            ("the plain path", lambda: run()),
            ("the D013 path", lambda: run_d013(DeclaredConstantTrueBackend()))):
        issued = build()
        require("content_sha256" in issued and h.validate_section_b2_record(issued),
                f"the {path} must return a sealed, validated record")

    # A run whose record would violate the contract must RAISE, not return.  With
    # the contract stubbed to a no-op that returns a mismatched hash, the run's
    # OWN call to it is the only thing that can notice.  The record that escapes
    # the stubbed validator is then shown to FAIL the real contract.
    original_validate = h.validate_section_b2_record
    try:
        h.validate_section_b2_record = lambda record: record["content_sha256"]
        h.content_sha256 = lambda value: "0" * 64
        issued = run()
    finally:
        h.validate_section_b2_record = original_validate
        h.content_sha256 = _original_content_sha256
    # The escaped record carries the deliberately wrong hash, so the real
    # contract refuses it: that is the proof the run's own validation call was
    # load-bearing.
    require(issued["content_sha256"] == "0" * 64,
            "this probe must actually have replaced the hashing")
    refused(lambda: original_validate(issued),
            "a run that skipped its own content hash", "content hash mismatch",
            error=h.SectionB2HarnessError)
    record("sealing and validation are load-bearing on the run path", True)

    # The same, for the D013 path, which is the one round 2 lost.
    try:
        h.validate_section_b2_record = lambda record: record["content_sha256"]
        h.content_sha256 = lambda value: "0" * 64
        issued = run_d013(DeclaredConstantTrueBackend())
    finally:
        h.validate_section_b2_record = original_validate
        h.content_sha256 = _original_content_sha256
    require(issued["content_sha256"] == "0" * 64,
            "this D013 probe must actually have replaced the hashing")
    refused(lambda: original_validate(issued),
            "the D013 record issued with a wrong hash", "content hash mismatch",
            error=h.SectionB2HarnessError)

    # And the run itself refuses if its record fails its contract: a record
    # validator that rejects the run's own record turns into a raised refusal,
    # so there is no path that issues an unvalidated record.
    try:
        h.validate_section_b2_record = lambda record: (_ for _ in ()).throw(
            h.SectionB2HarnessError("the record contract refused the run's record"))
        refused(lambda: run(), "a run whose record fails its own contract",
                "contract refused", error=h.SectionB2HarnessError)
        refused(lambda: run_d013(DeclaredConstantTrueBackend()),
                "a D013 run whose record fails its own contract",
                "contract refused", error=h.SectionB2HarnessError)
    finally:
        h.validate_section_b2_record = original_validate
    record("a record that fails its contract is raised, never returned", True)

    # Recursive float/bool sweep of the RECORD THE RUN RETURNED.  The sweep
    # asserts its own finding by requiring that the same structure DOES trip it
    # once a float is added, so this is not a check that passes because it can
    # never fire.
    def sweep(value, path="record"):
        if type(value) in (float, bool):
            raise FixtureError(f"a {type(value).__name__} leaf survived in the record at {path}")
        if isinstance(value, dict):
            for key, nested in value.items():
                sweep(nested, f"{path}.{key}")
        elif isinstance(value, (tuple, list)):
            for index, nested in enumerate(value):
                sweep(nested, f"{path}[{index}]")

    sweep(result)
    probed = copy.deepcopy(result)
    probed["counters"]["passed"] = 120.5
    refused(lambda: sweep(probed), "the sweep itself missing an injected float",
            None, error=FixtureError)

    # The counters are counts, and the identities are hashes; nothing that
    # describes a single comparison's value survives.
    for key, value in sorted(result["counters"].items()):
        require(type(value) is int, f"counter {key} must be an integer")
    for key, value in sorted(result["identities"].items()):
        require(isinstance(value, str) and len(value) == 64, f"identity {key} must be a SHA-256")

    # The record is a commitment: the same run gives the same bytes, and a
    # tampered record no longer validates.
    again = run()
    require(h.canonical_bytes(again) == h.canonical_bytes(result),
            "the record is not reproducible for the same run")
    require(again["validation_digest"] == result["validation_digest"],
            "the validation digest is not reproducible for the same run")

    # The digest is a commitment to the ORDERED verdicts: dropping a comparison
    # changes it, and so does reordering.
    base_digest = h._comparison_digest(["pass"] * 120)
    require(base_digest == result["validation_digest"],
            "the digest must be the digest of 120 ordered passes")
    require(h._comparison_digest(["pass"] * 119) != base_digest,
            "a short verdict list must not produce the same digest")
    reordered = ["pass"] * 120
    reordered[0], reordered[1] = "pass", "pass"
    require(h._comparison_digest(reordered) == base_digest,
            "an identical verdict order must produce the identical digest")

    # Every record-level check below is driven on a HAND-BUILT record, not on
    # the harness's own, so no check is a self-check of a constant the harness
    # just wrote.
    tampered = _seal(copy.deepcopy(result))
    tampered["content_sha256"] = "0" * 64
    refused(lambda: h.validate_section_b2_record(tampered), "tampered content hash",
            "content hash mismatch")

    # ...and the content-hash check is load-bearing: an identically-built record
    # with a deliberately wrong hash is accepted once it is disabled.
    original_validate = h.validate_section_b2_record
    good = _seal(_blank_record())
    require(original_validate(good) == good["content_sha256"],
            "the blank record must validate once sealed")
    h.validate_section_b2_record = lambda record: record["content_sha256"]
    try:
        try:
            h.validate_section_b2_record(_seal(_blank_record() | {"counters":
                                     {**_blank_record()["counters"], "passed": 999}}))
        except h.SectionB2HarnessError:
            raise FixtureError("disabling the content-hash check did not let a tampered record through")
    finally:
        h.validate_section_b2_record = original_validate
    record("the record content hash is load-bearing", True)

    # The key set is closed at every level.  Each case RESEALS the record, so
    # the content-hash check cannot shadow the key-set check under test.
    for label, edit, needle in (
            ("an extra counter", lambda r: r["counters"].update(minimum_energy=1),
             "counters have the wrong key set"),
            ("a dropped counter", lambda r: r["counters"].pop("failed"),
             "counters have the wrong key set"),
            ("an extra identity", lambda r: r["identities"].update(device_uuid="transient"),
             "identities have the wrong key set"),
            ("a dropped identity", lambda r: r["identities"].pop("protocol_identity_sha256"),
             "identities have the wrong key set"),
            ("an extra top-level key", lambda r: r.update(coordinate=[30, 30, 30]),
             "record has wrong key set"),
            ("a dropped digest", lambda r: r.pop("validation_digest"),
             "record has wrong key set"),
            ("an extra content-hash key", lambda r: r.update(extra_hash="e" * 64),
             "record has wrong key set"),
            ("a dropped counters object", lambda r: r.pop("counters"),
             "record has wrong key set"),
    ):
        edited = _blank_record()
        edit(edited)
        _seal(edited)
        refused(lambda edited=edited: h.validate_section_b2_record(edited), label, needle)
    record("the record key set is closed at every level", True)

    # The schema and the verdict are the two closed string fields.
    for label, edit, needle in (
            ("a drifted schema", lambda r: r.update(schema="decisions_os/other/v1"),
             "schema mismatch"),
            ("a non-closed verdict", lambda r: r.update(verdict="ok"),
             "verdict must be 'passed' or 'failed'"),
            ("a bool verdict", lambda r: r.update(verdict=True),
             "verdict must be 'passed' or 'failed'"),
            ("a missing verdict", lambda r: r.pop("verdict"),
             "record has wrong key set"),
    ):
        edited = _blank_record()
        edit(edited)
        _seal(edited)
        refused(lambda edited=edited: h.validate_section_b2_record(edited), label, needle)
    record("the record schema and verdict are closed", True)

    # A malformed validation digest, resealed: the digest is a required output
    # of §B item 3, so it must be a well-formed hash and not merely present.
    for label, digest in (("a non-hash digest", "not-a-hash"),
                          ("a short digest", "a" * 63),
                          ("an upper-case digest", "A" * 64),
                          ("a non-string digest", 5),
                          ("a null digest", None)):
        edited = _blank_record()
        edited["validation_digest"] = digest
        _seal(edited)
        refused(lambda edited=edited: h.validate_section_b2_record(edited),
                label, "lowercase SHA-256")

    # ...and a malformed CONTENT hash, which is a separate field.  With the
    # EQUALITY check neutralised, the SHAPE check is the only thing left, so
    # each of these proves the shape rule is load-bearing rather than masked by
    # the comparison beside it.  Round 3's sweep found this half masked.
    original_match = h._require_content_hash_match
    h._require_content_hash_match = lambda have: None
    try:
        for label, bad in (("a non-hash content hash", "not-a-hash"),
                           ("an upper-case content hash", "A" * 64),
                           ("a short content hash", "a" * 63),
                           ("a non-string content hash", 5),
                           ("a null content hash", None),
                           ("a bool content hash", True)):
            edited = _blank_record()
            edited["content_sha256"] = bad
            _seal(edited)
            edited["content_sha256"] = bad
            refused(lambda edited=edited: h.validate_section_b2_record(edited),
                    label, "record content hash")
    finally:
        h._require_content_hash_match = original_match
    # And the EQUALITY half in isolation, with the shape check neutralised: a
    # well-formed 64-hex hash that is not the hash of the body is refused only
    # by the comparison.
    original_sha = h._sha
    h._sha = lambda value, label: value
    try:
        forged = _blank_record()
        forged["content_sha256"] = "0" * 64
        refused(lambda: h.validate_section_b2_record(forged),
                "a well-formed but wrong content hash", "content hash mismatch")
    finally:
        h._sha = original_sha
    record("the record hashes are well formed", True)

    # Each identity is a hash too, and each counter an integer.
    for key in ("accepted_identity_sha256", "session_identity_sha256", "protocol_identity_sha256"):
        edited = _blank_record()
        edited["identities"][key] = "z" * 64
        _seal(edited)
        refused(lambda edited=edited: h.validate_section_b2_record(edited),
                f"a malformed {key}", "lowercase SHA-256")

    for key in ("comparisons", "passed", "failed", "coordinate_rows", "d013_repeat_rows"):
        for bad, label in ((-1, "negative"), (1.0, "float"), (True, "bool"),
                           ("120", "string"), (None, "none")):
            edited = _blank_record()
            edited["counters"][key] = bad
            _seal(edited)
            refused(lambda edited=edited: h.validate_section_b2_record(edited),
                    f"a {label} {key}", "must be an integer >= 0")
    record("each counter and identity is individually type-checked", True)

    # A float dressed up as a counter.  The typed counter check catches this
    # first, so the recursive no-float sweep would look redundant -- it is not:
    # with the typed checks neutralised, the sweep is the only thing left
    # standing, and it still refuses.  That is the evidence the sweep is a real
    # independent layer rather than a check that can never fire.
    original_int = h._int
    original_sha = h._sha
    injected_bool = _seal({**copy.deepcopy(result), "counters":
                          {**copy.deepcopy(result["counters"]), "failed": False},
                          "content_sha256": None})
    injected_float = _seal({**copy.deepcopy(result), "counters":
                            {**copy.deepcopy(result["counters"]), "passed": 120.0},
                            "content_sha256": None})
    h._int = lambda value, label, minimum=0: value
    h._sha = lambda value, label: value
    try:
        refused(lambda: h.validate_section_b2_record(injected_float),
                "a float leaf with the typed checks neutralised",
                "may not contain float or bool leaves")
        refused(lambda: h.validate_section_b2_record(injected_bool),
                "a bool leaf with the typed checks neutralised",
                "may not contain float or bool leaves")
    finally:
        h._int = original_int
        h._sha = original_sha
    record("the no-float sweep is an independent layer", True)

    # The sweep's RECURSION into a non-dict Mapping is a round-2 addition: it
    # used isinstance(value, dict), so a mapping that is not a dict was skipped
    # entirely and a float hiding in one survived.
    from collections.abc import Mapping as _Mapping

    class RecursiveProxy(_Mapping):
        def __init__(self, backing):
            self._backing = backing

        def __getitem__(self, key):
            return self._backing[key]

        def __iter__(self):
            return iter(self._backing)

        def __len__(self):
            return len(self._backing)

    # A proxy mapping is legal to validate but not JSON-serialisable through
    # json.dumps directly, so its content hash is computed over a plain mirror
    # of the record (with the proxy replaced by its backing dict).  That is
    # exactly the record the sweep must reach: a correctly-hashed record whose
    # counters are a non-dict Mapping carrying a float.
    proxy_backing = {**copy.deepcopy(result["counters"]), "passed": 1.5}
    proxy_record = {**copy.deepcopy(result), "counters": RecursiveProxy(proxy_backing),
                    "content_sha256": "e" * 64}
    original_int = h._int
    original_sha = h._sha
    original_csha = h.content_sha256
    h._int = lambda value, label, minimum=0: value
    h._sha = lambda value, label: value
    # Neutralise the content-hash comparison too: it would otherwise recompute
    # the hash of the proxy, which json cannot serialise, and refuse for that
    # reason before the sweep ever runs.  With it neutralised the ONLY thing
    # that can see the float inside the non-dict Mapping is the sweep.
    h.content_sha256 = lambda value: proxy_record["content_sha256"]
    try:
        refused(lambda: h.validate_section_b2_record(proxy_record),
                "a float inside a non-dict Mapping", "may not contain float or bool leaves")
    finally:
        h._int = original_int
        h._sha = original_sha
        h.content_sha256 = original_csha

    # The non-string KEY half of the sweep, driven directly: a record whose
    # counters is a mapping with an integer key.  The mapping copy refuses it.
    refused(lambda: h._no_float_or_bool({1: "int key"}, "probe"),
            "a non-string key in the sweep", "keys must be strings")

    # A float nested two levels deep inside a list inside a dict: the sweep's
    # list recursion, not just its dict recursion.
    refused(lambda: h._no_float_or_bool({"a": [1, [2, 3.0]]}, "probe"),
            "a float nested two lists deep", "may not contain float or bool")
    refused(lambda: h._no_float_or_bool((1, 2, True), "probe"),
            "a bool inside a tuple", "may not contain float or bool")
    record("the no-float sweep recurses through mappings, lists and tuples", True)

    # The record-level narrowing: a non-mapping record, a hostile mapping, a
    # counters object that is not a mapping, an identities object that is not.
    for label, value in (("a non-mapping record", "a record"),
                         ("a None record", None),
                         ("a list record", [1, 2]),
                         ("an int record", 7)):
        refused(lambda value=value: h.validate_section_b2_record(value),
                label, "must be a mapping")

    for key, label in (("counters", "a non-mapping counters object"),
                       ("identities", "a non-mapping identities object")):
        edited = _blank_record()
        edited[key] = ["not", "a", "mapping"]
        _seal(edited)
        refused(lambda edited=edited: h.validate_section_b2_record(edited),
                label, "Section B item 3 counters must be a mapping"
                if key == "counters" else "identities must be a mapping")

    refused(lambda: h.validate_section_b2_record(HostileMapping()),
            "a hostile mapping record", "could not be read as a mapping")
    record("the record contract refuses a malformed record, typed", True)

    # An injected scientific value, i.e. a float leaf where the closed key set
    # forbids one.  The key set refuses it, and the value is never retained.
    injected_value = copy.deepcopy(result)
    injected_value["counters"]["minimum_energy"] = 1.25
    refused(lambda: h.validate_section_b2_record(_seal(injected_value)),
            "an injected scientific value", "wrong key set")
    record("the output record has no coordinate-level value", True)


# ---------------------------------------------------------------------------
# 6. Fail-closed behaviour: missing fields, non-finite words, raw exceptions
# ---------------------------------------------------------------------------

def check_fail_closed() -> None:
    for field in h.COMPARISON_FIELDS:
        def drop_field(payload, row, pair, encoding, field=field):
            payload.pop(field)
            return payload
        refused(lambda field=field: run(device=make_backend(drop_field, f"drop-{field}")),
                f"missing field {field}", "missing required comparison fields")

        def add_field(payload, row, pair, encoding, field=field):
            payload["approximate_energy"] = 1.0
            return payload
        refused(lambda: run(device=make_backend(add_field, "extra-field")),
                "an undeclared extra field", "undeclared fields")

    for bad, label in ((float("nan"), "NaN"), (float("inf"), "+inf"), (float("-inf"), "-inf")):
        def nonfinite(payload, row, pair, encoding, bad=bad):
            payload["energy_minimum_words"] = (bad,)
            return payload
        refused(lambda: run(device=make_backend(nonfinite, f"nonfinite-{label}")),
                f"a {label} energy word", "non-finite")

    # A non-finite word anywhere in the list, not only the first.
    def nonfinite_last(payload, row, pair, encoding):
        words = list(payload["energy_minimum_words"])
        words[-1] = float("nan")
        payload["energy_minimum_words"] = tuple(words)
        return payload
    refused(lambda: run(device=make_backend(nonfinite_last, "nonfinite-last")),
            "a NaN in the last energy word", "non-finite")

    for raw, label in (("not a mapping", "a string"), (None, "a None"),
                       (7, "an int"), ([1, 2], "a list"), (True, "a bool")):
        refused(lambda raw=raw: run(device=make_backend(raw=raw, name="raw")),
                f"a backend that returns {label}", "must be a mapping")

    # ...and the same, on the reference side: the harness is not one-sided.
    refused(lambda: run(reference=make_backend(raw="not a mapping", name="raw-ref")),
            "a reference that returns a non-mapping", "must be a mapping")

    def empty_words(payload, row, pair, encoding):
        payload["energy_minimum_words"] = ()
        return payload
    refused(lambda: run(device=make_backend(empty_words, "empty-words")),
            "empty energy-minimum words", "must be a non-empty sequence")

    for bad, label in ((None, "a None"),
                       ("abc", "a string"), ({"a": 1}, "a dict"), (7, "an int"),
                       (Unhashable(), "an unhashable"), (True, "a bool")):
        def wrong_words(payload, row, pair, encoding, bad=bad):
            payload["energy_minimum_words"] = bad
            return payload
        refused(lambda bad=bad: run(device=make_backend(wrong_words, "wrong-words")),
                f"energy-minimum words that are {label}", "must be a tuple or list")

    for bad, label in ((None, "a None"), (True, "a bool"), (7, "an int"),
                       ("0", "a string"), ({}, "a dict"), ((), "an empty tuple"),
                       (Unhashable(), "an unhashable")):
        def nonfloat_word(payload, row, pair, encoding, bad=bad):
            payload["energy_minimum_words"] = (bad,)
            return payload
        refused(lambda bad=bad: run(device=make_backend(nonfloat_word, "nonfloat-word")),
                f"an energy word that is {label}", "must be a float")

    def negative_index(payload, row, pair, encoding):
        payload["canonical_minimum_index"] = -1
        return payload
    refused(lambda: run(device=make_backend(negative_index, "negative-index")),
            "a negative canonical minimum index", "must be non-negative")

    for bad, label in (("0", "a string"), (1.0, "a float"), (True, "a bool"),
                       (None, "a None"), ({}, "a dict"), (Unhashable(), "an unhashable")):
        def bad_index(payload, row, pair, encoding, bad=bad):
            payload["canonical_minimum_index"] = bad
            return payload
        refused(lambda bad=bad: run(device=make_backend(bad_index, "bad-index")),
                f"a canonical minimum index that is {label}", "must be an integer")

    for bad, label in ((99, "an int above 7"), (-1, "a negative int")):
        def bad_tie(payload, row, pair, encoding, bad=bad):
            payload["tie_flags"] = (bad,)
            return payload
        refused(lambda bad=bad: run(device=make_backend(bad_tie, "bad-tie")),
                f"an out-of-range tie flag ({label})", "outside the legal 0..7 set")

    for bad, label in ((True, "a bool"), ("0", "a string"), (0.0, "a float"),
                       (None, "a None"), (Unhashable(), "an unhashable")):
        def bad_flag(payload, row, pair, encoding, bad=bad):
            payload["tie_flags"] = (bad,)
            return payload
        refused(lambda bad=bad: run(device=make_backend(bad_flag, "bad-flag")),
                f"a {label} tie flag", "must be an integer")

    for bad, label in (("0", "a string"), (True, "a bool"), (0.0, "a float"),
                       (None, "a None"), ({"flag": 0}, "a dict"),
                       (Unhashable(), "an unhashable"), (5, "an int")):
        def bad_tie_container(payload, row, pair, encoding, bad=bad):
            payload["tie_flags"] = bad
            return payload
        refused(lambda bad=bad: run(device=make_backend(bad_tie_container, "bad-tie-container")),
                f"tie flags that are {label}", "must be a tuple or list")

    def empty_reconstruction(payload, row, pair, encoding):
        payload["reconstruction"] = ""
        return payload
    refused(lambda: run(device=make_backend(empty_reconstruction, "empty-recon")),
            "an empty reconstruction", "must be non-empty")

    for bad, label in ((5, "an int"), (None, "a None"), (True, "a bool"),
                       (["x"], "a list"), (Unhashable(), "an unhashable")):
        def bad_recon(payload, row, pair, encoding, bad=bad):
            payload["reconstruction"] = bad
            return payload
        refused(lambda bad=bad: run(device=make_backend(bad_recon, "bad-recon")),
                f"a {label} reconstruction", "must be a string")

    # A backend whose RESULT is a mapping with a non-string key: the mapping
    # copy refuses it before the field tests, so no undeclared-field message is
    # computed from a mixed key set.
    def int_keyed_result(row, pair, encoding):
        return {1: 0, 2: 0}
    refused(lambda: run(device=int_keyed_result), "a result with integer keys",
            "keys must all be strings")

    # The whole public run is fuzzed on every argument, and every named helper is
    # driven directly on its own.
    check_public_argument_fuzz()
    check_identity_hashes()
    check_named_helpers()
    record("the run is fail-closed on the first defect", True)


def check_named_helpers() -> None:
    """Every named helper in the harness, driven directly and on its own.

    A helper reached only through a long call chain can be masked by an earlier
    check.  Driving each one directly is what makes its own checks visible to the
    mutation table rather than hidden behind a neighbour.
    """
    for bad, label in (("a string", "abc"), (None, "a None"), (7, "an int"),
                       ({"a": 1}, "a dict"), (Unhashable(), "an unhashable")):
        refused(lambda bad=bad: h._comparison_digest(bad),
                f"the verdict list as {label}", "must be a tuple or list")
    for bad, label in ((7, "an int"), (None, "a None"), (True, "a bool")):
        refused(lambda bad=bad: h._comparison_digest([bad]),
                f"a verdict that is {label}", "must be a string")
    # The digest is a commitment to the ORDERED verdicts: a non-"pass" verdict
    # changes it, so a verdict list is not interchangeable with any other.
    require(h._comparison_digest(["pass"]) != h._comparison_digest(["fail"]),
            "a fail verdict must not produce the digest of a pass verdict")
    require(len(h._comparison_digest([])) == 64,
            "an empty verdict list must still produce a digest")

    # The SHA-256 shape helper, driven directly over the whole fuzz corpus, is
    # the same code the record contract and the identity path use.
    for bad, label in ((None, "a None"), (7, "an int"), (True, "a bool"),
                       (["a"], "a list"), ("A" * 64, "an upper-case hash"),
                       ("a" * 63, "a short hash"), ("z" * 64, "a non-hex hash"),
                       (Unhashable(), "an unhashable")):
        refused(lambda bad=bad: h._sha(bad, "probe"), f"_sha over {label}",
                "lowercase SHA-256")

    # The word-bits helper's float and finiteness halves.  The finiteness half
    # is reached through the run; the type half is driven here so a non-float
    # word is refused with a type message rather than an arithmetic crash.
    for bad, label in ((7, "an int"), (True, "a bool"), (None, "a None"),
                       ("0x1p0", "a string"), (Unhashable(), "an unhashable")):
        refused(lambda bad=bad: h._word_bits(bad, "probe"),
                f"_word_bits over {label}", "must be a float")
    for bad, label in ((float("nan"), "a NaN"), (float("inf"), "+inf"),
                       (float("-inf"), "-inf")):
        refused(lambda bad=bad: h._word_bits(bad, "probe"),
                f"_word_bits over {label}", "non-finite")
    require(h._word_bits(1.0, "probe") == (1.0).hex(),
            "_word_bits must round-trip a finite float")

    # The integer helper's lower bound, driven directly.  The record path only
    # ever supplies 0 as the minimum, so its `value >= minimum` half is not
    # otherwise reachable.
    refused(lambda: h._int(-1, "probe"), "_int over a negative value",
            "must be an integer >= 0")
    refused(lambda: h._int(1, "probe", minimum=5), "_int below the given minimum",
            "must be an integer >= 5")
    for bad, label in ((True, "a bool"), (1.0, "a float"), ("1", "a string"),
                       (None, "a None"), (Unhashable(), "an unhashable")):
        refused(lambda bad=bad: h._int(bad, "probe"), f"_int over {label}",
                "must be an integer")
    require(h._int(3, "probe", minimum=3) == 3, "_int must accept its own minimum")

    # The bool helper, driven directly: an int is a bool's near-miss and must
    # not be accepted, because a capability flag that is an int would silently
    # read as declared.
    for bad, label in ((1, "an int"), (0, "a zero int"), (None, "a None"),
                       ("yes", "a string"), ([], "a list"), ({}, "a dict")):
        refused(lambda bad=bad: h._exact_bool(bad, "probe"),
                f"_exact_bool over {label}", "must be a bool")
    require(h._exact_bool(True, "probe") is True, "_exact_bool must accept True")
    require(h._exact_bool(False, "probe") is False, "_exact_bool must accept False")

    # The coordinate shape guard, driven directly.  The builder feeds it only
    # its own literals, so this is the only way to reach it -- and it is the
    # guard that stops a future edit transcribing (30,30,30.0) or (30,30) into
    # the frozen literal tables.
    for bad, label in (("30,30,30", "a string"), (None, "a None"), (7, "an int"),
                       ([30, 30, 30], "a list"), ({1: 2}, "a dict"),
                       (Unhashable(), "an unhashable")):
        refused(lambda bad=bad: h._coordinate(bad), f"_coordinate over {label}",
                "must be a 3-tuple")
    for bad, label in (((30, 30), "a 2-tuple"), ((30, 30, 30, 30), "a 4-tuple"),
                       ((), "an empty tuple")):
        refused(lambda bad=bad: h._coordinate(bad), f"_coordinate over {label}",
                "must be a 3-tuple")
    for bad, label in (((30.0, 30, 30), "a float axis"), ((True, 30, 30), "a bool axis"),
                       (("30", 30, 30), "a string axis"), ((None, 30, 30), "a None axis"),
                       ((-1, 30, 30), "a negative axis"), ((Unhashable(), 30, 30),
                                                          "an unhashable axis")):
        refused(lambda bad=bad: h._coordinate(bad), f"_coordinate with {label}",
                "non-negative integer")
    for good in ((0, 0, 0), (30, 30, 30), (110, 110, 110), (6, 6, 6)):
        require(h._coordinate(good) == good, f"_coordinate must accept {good}")

    # The row-membership and identity-comparison helpers are TOTAL by design:
    # they answer "not equal" for anything, including a hostile value, so that
    # no input can escape as a TypeError.  A total function is verified by
    # showing it answers for every fuzz member rather than by a refusal.
    for bad, label in ((None, "a None"), (7, "an int"), ("abc", "a string"),
                       ([], "a list"), ({"a": 2}, "a differing dict"),
                       (Unhashable(), "an unhashable"),
                       (HostileMapping(), "a hostile mapping")):
        require(h._row_fields_match({"a": 1}, bad) is False,
                f"_row_fields_match must answer False for {label}, not raise")
        require(h._same_row_identity({"family": "primary"}, bad) is False,
                f"_same_row_identity must answer False for {label}, not raise")
    require(h._row_fields_match({"a": 1}, {"a": 1}) is True,
            "_row_fields_match must answer True for identical rows")
    require(h._row_fields_match({"a": 1}, {"a": 2}) is False,
            "_row_fields_match must answer False for differing rows")
    require(h._row_fields_match({"a": 1}, {"a": True}) is False,
            "_row_fields_match must distinguish 1 from True by exact type")
    require(h._row_fields_match({"a": (1, 2)}, {"a": (1, 2)}) is True,
            "_row_fields_match must compare a coordinate tuple element-wise")
    require(h._row_fields_match({"a": (1, 2)}, {"a": (1, 3)}) is False,
            "_row_fields_match must compare a coordinate tuple element by element")
    require(h._row_fields_match({"a": (1, 2)}, {"a": (1, 2, 3)}) is False,
            "_row_fields_match must refuse a coordinate of the wrong length")
    require(h._row_fields_match({"a": (1, 2)}, {"a": [1, 2]}) is False,
            "_row_fields_match must distinguish a coordinate tuple from a list")
    require(h._duplicate_row_index(None) == -1,
            "_duplicate_row_index must answer -1 for a non-iterable row list")
    record("every typed accessor and total helper is load-bearing", True)


def check_identity_hashes() -> None:
    """Every check in _identity_hashes and _require_identity_match.

    These were several unverified in round 1: the accepted-payload mapping check
    was a duplicate of one that had already fired, and the disagreement check was
    masked whenever the supplied hash was itself malformed.  The duplicate is
    gone; the disagreement check is now driven with a WELL-FORMED but different
    hash, which is the only shape that can reach it.
    """
    # The injected validate(payload) returning something that is not a hash.
    for bad, label in ((None, "a None"), (7, "an int"), (True, "a bool"),
                       (["a"], "a list"), ("NOT-A-HASH", "a non-hash string")):
        refused(lambda bad=bad: run(validate_identity=lambda payload, bad=bad: bad),
                f"validate(payload) returning {label}", "lowercase SHA-256")

    # The disagreement check: a well-formed hash that is not the accepted one.
    # The supplied accepted_identity_sha256 stays well formed, so only the
    # disagreement can fire.
    refused(lambda: run(validate_identity=lambda payload: "0" * 64),
            "validate(payload) disagreeing with the accepted hash", "disagrees")

    # ...and the control: a validate that AGREES is accepted, so the refusal
    # above is caused by the disagreement and not by the shape check.
    require(run()["identities"]["accepted_identity_sha256"]
            == IDENTITY_KWARGS["accepted_identity_sha256"],
            "the honest run must report the accepted identity hash")

    # A malformed SUPPLIED hash is refused by the shape check, whichever side
    # of the disagreement it is on.
    for bad, label in ((None, "a None"), (7, "an int"), ("NOT-A-HASH", "a non-hash"),
                       ("A" * 64, "an upper-case hash"), ("a" * 63, "a short hash")):
        refused(lambda bad=bad: run(accepted_identity_sha256=bad),
                f"an accepted identity hash that is {label}", "lowercase SHA-256")
        refused(lambda bad=bad: run(protocol_identity_sha256=bad),
                f"a protocol identity hash that is {label}", "lowercase SHA-256")

    # A non-callable validate / exact_match is refused by name.
    for bad, label in (("not callable", "a string"), (7, "an int"),
                       (None, "a None"), ([], "a list"), ({}, "a dict")):
        refused(lambda bad=bad: run(validate_identity=bad),
                f"a validate that is {label}", "must be callable")
        refused(lambda bad=bad: run(exact_match=bad),
                f"an exact_match that is {label}", "must be callable")
        # The two BACKEND slots are also callability-guarded, and the guard must
        # be reached by name rather than by a later crash when the harness tries
        # to invoke the non-callable.  Round 3's sweep found this guard survived
        # because the fixture accepted any typed refusal: a non-callable that
        # merely raised "not callable" when invoked was passing a check the
        # harness had already made.  The needle pins the guard's OWN message.
        refused(lambda bad=bad: run(device=bad),
                f"a device_backend that is {label}",
                "device_backend must be a callable")
        refused(lambda bad=bad: run(reference=bad),
                f"a python_reference that is {label}",
                "python_reference must be a callable")
        # ...including on the D013 path as well as the plain one, since the
        # callability guard runs before anything else.
        refused(lambda bad=bad: run_d013(DeclaredConstantTrueBackend(),
                                          reference=bad),
                f"a python_reference that is {label} with D013 fired",
                "python_reference must be a callable")
        # ...and a genuinely None slot.  The local run() helper treats a None
        # device as "use the default", so this one goes through the harness
        # directly -- otherwise the fixture would silently be testing the
        # default backend instead of the None it claims to test.
        refused(lambda: h.run_section_b2(
            None, honest_reference, h.build_validation_coordinates(), **IDENTITY_KWARGS),
            "a device_backend that is a None", "device_backend must be a callable")
        refused(lambda: h.run_section_b2(
            honest_device, None, h.build_validation_coordinates(), **IDENTITY_KWARGS),
            "a python_reference that is a None", "python_reference must be a callable")
    record("a non-callable backend or reference is refused by name", True)

    # A non-mapping session identity: the harness refuses it before the injected
    # matcher can interpret it however it likes, so the MATCHER's own error is
    # not the outcome.
    for bad, label in (("not a mapping", "a string"), (7, "an int"),
                       ([], "a list"), (None, "a None")):
        refused(lambda bad=bad: run(session_identity=bad),
                f"a session identity that is {label}", "session identity payload must be a mapping")
        refused(lambda bad=bad: run(accepted_identity=bad),
                f"an accepted identity that is {label}", "must be a mapping")

    # DEFECT 3 (round 3).  A RAW exception from an injected function used to
    # escape untyped, so the caller could not tell a harness refusal from a
    # backend crash -- and a fail-closed harness whose crash looks like anything
    # else is not fail-closed.  The injected matcher's OWN declared mismatch
    # exception (SyntheticIdentityMismatch) and the injected validate's own
    # failures must now all arrive as SectionB2HarnessError.  On the round-2
    # code each of these leaked its own type, so this fixture fails there.
    try:
        run(session_identity=_OTHER_IDENTITY)
    except h.SectionB2HarnessError as exc:
        require("SyntheticIdentityMismatch" in str(exc),
                f"the converted refusal must name what the matcher raised: {exc}")
    else:
        raise FixtureError("the identity mismatch was not refused at all")
    for label, func in (
            ("validate raising RuntimeError", lambda payload: (_ for _ in ()).throw(
                RuntimeError("identity probe boom"))),
            ("validate raising KeyError", lambda payload: (_ for _ in ()).throw(
                KeyError("platform"))),
            ("validate raising BaseException", lambda payload: (_ for _ in ()).throw(
                KeyboardInterrupt("interrupted"))),
    ):
        refused(lambda func=func: run(validate_identity=func),
                f"{label}", "fail-closed and no record is written",
                error=h.SectionB2HarnessError)
    refused(lambda: run(exact_match=lambda session, accepted: (_ for _ in ()).throw(
        RuntimeError("matcher boom"))),
        "exact_match raising RuntimeError", "fail-closed and no record is written",
        error=h.SectionB2HarnessError)
    record("an injected identity exception is converted to the typed error", True)
    record("every identity hash and matcher check is load-bearing", True)


# ---------------------------------------------------------------------------
# 6c. DEFECT 3: a backend or reference that RAISES is a typed refusal
# ---------------------------------------------------------------------------

# The exception zoo: every one of these used to escape run_section_b2 untyped.
RAW_EXCEPTIONS = (
    ("a RuntimeError", RuntimeError("backend boom")),
    ("a ValueError", ValueError("bad domain")),
    ("a TypeError", TypeError("wrong kernel signature")),
    ("a KeyError", KeyError("energy")),
    ("an AttributeError", AttributeError("no such stream")),
    ("an IndexError", IndexError(7)),
    ("an OSError", OSError("the device fell over")),
    ("a MemoryError", MemoryError("out of device memory")),
    ("a ZeroDivisionError", ZeroDivisionError("degenerate slack")),
    ("an OverflowError", OverflowError("coefficient overflow")),
    ("a RecursionError", RecursionError("too deep")),
    ("a custom exception", SyntheticIdentityMismatch("the backend refused")),
    ("a BaseException", KeyboardInterrupt("interrupted mid-domain")),
    ("SystemExit", SystemExit(3)),
)


def check_injected_exceptions() -> None:
    """Every exception an injected callable raises becomes the typed error.

    Round 3's third defect: a device backend and a reference that each raised
    ``RuntimeError("backend boom")`` let that RuntimeError escape
    ``run_section_b2`` unchanged.  The harness is fail-closed, so a crash is a
    refusal, and a refusal is this module's own type -- never a raw exception a
    caller would have to recognise, and never a silent partial record.  Each
    case below leaked its own type on the round-2 code.
    """
    for label, exc in RAW_EXCEPTIONS:
        device = make_raising_backend(exc, f"raise-{label}")
        refused(lambda device=device: run(device=device),
                f"a device backend raising {label}",
                "fail-closed and no record is written", error=h.SectionB2HarnessError)
        refused(lambda exc=exc: run(reference=make_raising_backend(exc, "ref")),
                f"a Python reference raising {label}",
                "fail-closed and no record is written", error=h.SectionB2HarnessError)
    record("a backend or reference exception becomes the typed error", True)

    # The message must name the backend that raised, so a converted refusal is
    # diagnosable, and must carry the original type for the same reason.
    for side, kwargs in (("device_backend", {"device": make_raising_backend(
                            RuntimeError("device side"), "msg-device")}),
                         ("python_reference", {"reference": make_raising_backend(
                            ValueError("reference side"), "msg-ref")})):
        try:
            run(**kwargs)
        except h.SectionB2HarnessError as exc:
            require(side in str(exc), f"the converted refusal must name {side}: {exc}")
            require(("RuntimeError" in str(exc)) or ("ValueError" in str(exc)),
                    f"the converted refusal must name the original type: {exc}")
        else:
            raise FixtureError(f"a raising {side} was not refused")

    # Nothing is written on the way out: a crash mid-run leaves no record, and
    # the comparisons that already succeeded are not enough to issue one.
    issued = []
    original_sealed = h._sealed_record

    def spy_sealed(verdicts, identities, total_rows, repeat_rows):
        issued.append(True)
        return original_sealed(verdicts, identities, total_rows, repeat_rows)

    calls = []

    def crash_after(row, pair, encoding):
        calls.append(1)
        if len(calls) > 60:
            raise RuntimeError("the device fell over mid-domain")
        return fake_payload(row, pair, encoding)

    h._sealed_record = spy_sealed
    try:
        refused(lambda: run(device=crash_after), "a crash after 60 comparisons",
                "fail-closed", error=h.SectionB2HarnessError)
        require(issued == [], "a record was built despite a mid-run crash")
        require(len(calls) == 61, f"expected 61 comparisons before the crash, got {len(calls)}")
    finally:
        h._sealed_record = original_sealed
    record("a mid-run crash issues no record", True)

    # The D013 path converts too: a backend that declares +0.0 and then crashes
    # on the first REPEAT comparison is a refusal, not a 120-comparison pass.
    class DeclaringThenCrashing(DeclaredConstantTrueBackend):
        def __call__(self, row, pair, encoding):
            if row["family"] == "d013_repeat":
                raise RuntimeError("the +0.0 family could not be launched")
            return fake_payload(row, pair, encoding)

    refused(lambda: run_d013(DeclaringThenCrashing()),
            "a +0.0 backend crashing on the first repeat comparison",
            "fail-closed and no record is written", error=h.SectionB2HarnessError)
    record("a crash inside the D013 repeat is a typed refusal", True)

    # A backend that raises NON-EXCEPTION control flow (a bare return of a
    # sentinel, or a generator) is a malformed result and is refused by the field
    # test, typed, exactly as before.
    refused(lambda: run(device=make_backend(lambda payload, row, pair, encoding: (_ for _ in ()))),
            "a backend returning a generator", "must be a mapping",
            error=h.SectionB2HarnessError)
    record("a backend returning a non-mapping sentinel is refused, typed", True)


# ---------------------------------------------------------------------------
# 6b. Every public argument is fuzzed: no untyped exception may escape
# ---------------------------------------------------------------------------

def check_public_argument_fuzz() -> None:
    """Fuzz every public argument of every public entry point.

    The rule is uniform and absolute: for a malformed value, the entry point
    either succeeds on well-formed input, or refuses with SectionB2HarnessError
    (or the D013 subclass), or -- for the one deliberate exception, the record
    contract and the byte-coercion calls, whose entire job is to describe a
    value of the wrong type -- raises exactly the builtin type named below.  A
    bare TypeError out of run_section_b2, the coordinate builders, cost_estimate
    or print_cost_estimate is a FAILURE, which is the round-2 fix for the
    validator's finding that untyped exceptions leaked via dict casts.
    """
    # The one input that legitimately produces a raw TypeError: calling a
    # public function with a positional argument it does not accept.  That is
    # Python's own signature refusal, raised before any harness code runs.
    refused(lambda: h.build_validation_coordinates((30, 30, 30)),
            "the coordinate builder with a positional argument",
            "positional argument", error=TypeError)
    refused(lambda: h.cost_estimate(True, False), "cost_estimate with two arguments",
            "positional argument", error=TypeError)

    # The INJECTED matcher's own refusal is a legitimate outcome for an
    # identity argument: it is WP1's rule, not the harness's, and the harness
    # deliberately lets it propagate.  So the identity slots accept either the
    # harness's typed error or the matcher's.
    IDENTITY_SLOTS = ("accepted_identity", "session_identity")
    TYPED_OR_MATCHER = (h.SectionB2HarnessError, SyntheticIdentityMismatch)

    # The three positional arguments of run_section_b2.
    for position in (0, 1, 2):
        for label, value in FUZZ:
            args = [honest_device, honest_reference, h.build_validation_coordinates()]
            args[position] = value
            kwargs = dict(IDENTITY_KWARGS)
            refused(lambda args=args, kwargs=kwargs: h.run_section_b2(*args, **kwargs),
                    f"run_section_b2 positional argument {position} as {label}",
                    error=TYPED_OR_MATCHER)

    # d013_fired and device_supports_positive_zero are the two flags whose
    # legal values are bools, so the corpus's own "bool" and "bool-false"
    # entries are the ACCEPTED cases for them, not refusals.  Every other
    # member of the corpus must be refused.
    for key in ("accepted_identity", "session_identity", "validate_identity", "exact_match",
                "accepted_identity_sha256", "protocol_identity_sha256"):
        for label, value in FUZZ:
            kwargs = dict(IDENTITY_KWARGS)
            kwargs[key] = value
            refused(lambda kwargs=kwargs: h.run_section_b2(
                honest_device, honest_reference,
                h.build_validation_coordinates(), **kwargs),
                f"run_section_b2 {key} as {label}",
                error=TYPED_OR_MATCHER if key in IDENTITY_SLOTS else None)

    for key in ("accepted_identity", "session_identity", "validate_identity", "exact_match",
                "accepted_identity_sha256", "protocol_identity_sha256"):
        for label, value in FUZZ_FALSY:
            kwargs = dict(IDENTITY_KWARGS)
            kwargs[key] = value
            refused(lambda kwargs=kwargs: h.run_section_b2(
                honest_device, honest_reference,
                h.build_validation_coordinates(), **kwargs),
                f"run_section_b2 {key} as {label} (falsy)",
                error=TYPED_OR_MATCHER if key in IDENTITY_SLOTS else None)

    # d013_fired is the one remaining bool flag: its legal values ARE bools, so
    # the corpus's own bool entries are the ACCEPTED cases for it and every other
    # member must be refused.  The True case needs a +0.0-DECLARING backend and a
    # valid repeat list, so the "fired" control supplies both -- there is no
    # capability flag to set, because round 3 removed it.
    capable = DeclaredConstantTrueBackend()
    fired = dict(IDENTITY_KWARGS)
    fired["d013_fired"] = True
    fired["d013_coordinates"] = h.d013_repeat_coordinates()
    for key in ("d013_fired",):
        for label, value in FUZZ + FUZZ_FALSY:
            if value is True or value is False:
                base = fired if value is True else dict(IDENTITY_KWARGS)
                device = capable if value is True else PlainBackend()
                kwargs = dict(base)
                kwargs[key] = value
                require(h.run_section_b2(
                    device, honest_reference,
                    h.build_validation_coordinates(), **kwargs)["verdict"] == "passed",
                    f"the legal {key}={value!r} must be accepted")
                continue
            kwargs = dict(IDENTITY_KWARGS)
            kwargs[key] = value
            refused(lambda kwargs=kwargs: h.run_section_b2(
                PlainBackend(), honest_reference,
                h.build_validation_coordinates(), **kwargs),
                f"run_section_b2 {key} as {label}")

    # d013_coordinates, driven with D013 FIRED against a declaring backend,
    # which is the only case in which the harness looks at it at all.
    for label, value in FUZZ + FUZZ_FALSY:
        if value is None:
            # The documented default: D013 fired with no list at all.
            refused(lambda: run_d013(capable, d013_coordinates=None),
                    "run_section_b2 d013_coordinates as none with D013 fired",
                    "must be supplied")
            continue
        refused(lambda value=value: run_d013(capable, value),
                f"run_section_b2 d013_coordinates as {label} with D013 fired")

    # A missing REQUIRED keyword argument, and an unknown one.  These are
    # Python's own signature refusals, raised before any harness code runs, and
    # the harness cannot type them: the call never enters the function body.
    # d013_fired and d013_coordinates have defaults, so omitting them is legal
    # and is not tested here.
    required = ("accepted_identity", "session_identity", "validate_identity",
                "exact_match", "accepted_identity_sha256", "protocol_identity_sha256")
    for key in required:
        kwargs = {k: v for k, v in IDENTITY_KWARGS.items() if k != key}
        refused(lambda kwargs=kwargs: h.run_section_b2(
            honest_device, honest_reference,
            h.build_validation_coordinates(), **kwargs),
            f"run_section_b2 without {key}", "required keyword-only argument",
            error=TypeError)
    refused(lambda: h.run_section_b2(
        honest_device, honest_reference, h.build_validation_coordinates(),
        **dict(IDENTITY_KWARGS, not_a_real_argument=1)),
        "run_section_b2 with an unknown keyword", "unexpected keyword argument",
        error=TypeError)

    # cost_estimate / print_cost_estimate are public and typed too.  Their one
    # legal value is a bool, so the corpus's bool entries are the accepted
    # cases and everything else in both corpora must be refused.
    for label, value in FUZZ + FUZZ_FALSY:
        if value is True or value is False:
            require(h.cost_estimate(value)["comparisons_without_d013"] == 120,
                    "the legal bool d013_fired must be accepted by cost_estimate")
            continue
        refused(lambda value=value: h.cost_estimate(value), f"cost_estimate as {label}")

    # The three public bytes/hash entry points refuse a non-mapping with their
    # own typed error.  The record's declared builtin exception, raised
    # deliberately and named in the message, is the ONE acceptable shape.
    def coercion_is_typed(label, fn, value, expected=None):
        expected = expected or h.SectionB2HarnessError
        try:
            fn(value)
        except expected as exc:
            require(isinstance(exc, h.SectionB2HarnessError),
                    f"{label} must raise the typed error, got {type(exc).__name__}")
            require("mapping" in str(exc),
                    f"{label} must say what was wrong, got: {exc}")
            return
        except Exception as exc:
            raise FixtureError(f"{label}: raw {type(exc).__name__} instead of the typed error: {exc}")
        raise FixtureError(f"{label}: accepted")

    for label, value in FUZZ:
        if isinstance(value, (dict,)):
            continue  # a dict is a legal input; covered by the fixture below
        coercion_is_typed(f"canonical_bytes as {label}", h.canonical_bytes, value)
        coercion_is_typed(f"content_sha256 as {label}", h.content_sha256, value)

    # A legal mapping is still hashed, and a non-JSON-serialisable VALUE inside
    # a legal mapping is refused by name -- the dict() cast can no longer leak a
    # raw TypeError from json.dumps.
    require(len(h.canonical_bytes({"a": 1})) > 0, "canonical_bytes must accept a legal mapping")
    require(len(h.content_sha256({"a": 1})) == 64, "content_sha256 must accept a legal mapping")
    for label, value in (("an unserialisable object", Unhashable()),
                         ("a set", {1, 2}),
                         ("a nested unserialisable", {"a": {"b": Unhashable()}})):
        refused(lambda value=value: h.content_sha256({"a": value}),
                f"content_sha256 with {label} as a value", "not JSON-serialisable")
        refused(lambda value=value: h.canonical_bytes({"a": value}),
                f"canonical_bytes with {label} as a value", "not JSON-serialisable")
    # A NaN is legal Python but not legal JSON; allow_nan=False refuses it, and
    # the refusal is typed.
    refused(lambda: h.canonical_bytes({"a": float("nan")}), "canonical_bytes with a NaN",
            "not JSON-serialisable")
    # A non-string KEY in an otherwise legal mapping.
    for label, key in (("an integer key", 1), ("a None key", None),
                       ("a tuple key", (1, 2)), ("a bool key", True)):
        refused(lambda key=key: h.content_sha256({key: 1}),
                f"content_sha256 with {label}", "keys must all be strings")

    # A hostile mapping: its keys() explodes, so even reading it as a mapping is
    # a malformed input.  The guard must convert that to the typed error.
    coercion_is_typed("content_sha256 with a hostile mapping", h.content_sha256,
                      HostileMapping())
    # A mapping with a failing __eq__ and one with a failing items(): neither
    # explodes during dict() for a plain dict subclass, so these simply confirm
    # the plain path still works -- the value is legal, so it must be ACCEPTED
    # and hashed, not refused.
    for label, value in (("a mapping with a failing __eq__", _ExplodingEquality()),
                         ("a mapping with a failing items()", _ExplodingItems())):
        require(len(h.content_sha256(value)) == 64,
                f"a legal {label} must be hashed, not refused")


class _ExplodingEquality(dict):
    def __eq__(self, other):
        raise RuntimeError("equality was attempted on a hostile mapping")


class _ExplodingItems(dict):
    def items(self):
        raise RuntimeError("items() was called on a hostile mapping")


# ---------------------------------------------------------------------------
# 7. The module draws no scientific value and writes nothing
# ---------------------------------------------------------------------------

def check_no_project_writes() -> None:
    source = (ROOT / "research/g9/stage2_section_b2_harness.py").read_text(encoding="ascii")
    code_lines = [line for line in source.splitlines()
                  if not line.lstrip().startswith("#")]
    code = "\n".join(code_lines)
    # I/O, process and network facilities.  The harness orders comparisons and
    # shapes a record; it must not reach outside the process.  NOTE the check
    # skips comment lines, because the module docstring legitimately cites the
    # decision records and the pilot by filename.
    for forbidden in ("__main__", "argparse", "sys.argv", "subprocess", "socket",
                      "urllib", "requests", "kaggle", "tempfile", "shutil",
                      "open(", "write_text", "write_bytes", "os.remove", "unlink",
                      "import numpy", "np.", "eval(", "exec("):
        require(forbidden not in code,
                f"the harness source contains forbidden token {forbidden!r} outside comments")
    # No third-party import at all: only the frozen src/g6 constants.
    require("import numpy" not in code and "import scipy" not in code,
            "the harness must not import a third-party numerical library")
    # It must not import the production identity (WP1 is still under review) and
    # must not reach for the frozen v1 engine directly: both are injected.
    for forbidden in ("stage2_cuda_core_stream_engine", "stage2_cuda_execution_contract",
                      "stage2_cuda_full_domain_energy", "stage2_cuda_reconstruct",
                      "qualification_identity", "validate_qualification_identity"):
        require(forbidden not in source,
                f"the harness must not import the in-review WP1 identity or the frozen "
                f"v1 engine directly: {forbidden!r}")
    # The only project imports are the frozen src/g6 constant modules.
    project_imports = [line.strip() for line in code_lines if line.startswith(("from src", "import src"))]
    require(project_imports == [
        "from src.g6 import d011_matched_subgrid as _d011_matched_subgrid",
        "from src.g6 import d011_runner as _d011_runner",
        "from src.g6 import d011_transition_output as _d011_transition_output",
        "from src.g6 import g5_input as _g5_input",
        "from src.g6 import ledgers as _ledgers",
    ], f"the frozen import set drifted: {project_imports}")

    # The module makes itself importable from the project root rather than
    # requiring a caller to set PYTHONPATH.  That bootstrap is load-bearing and
    # is driven here by importing the harness from a mktemp cwd with the project
    # root NOT on sys.path, which is exactly the case the guard exists for.
    probe = (
        "import sys; sys.dont_write_bytecode = True\n"
        "import importlib.util\n"
        f"spec = importlib.util.spec_from_file_location('probe_h', {str(ROOT / 'research/g9/stage2_section_b2_harness.py')!r})\n"
        "module = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(module)\n"
        "assert len(module.build_validation_coordinates()) == 12\n"
        "print('IMPORT-PROBE-OK')\n"
    )
    with tempfile.TemporaryDirectory(prefix="wp3_import_probe_") as probe_dir:
        env = dict(os.environ)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["PYTHONPATH"] = ""
        result = subprocess.run([sys.executable, "-B", "-c", probe],
                                capture_output=True, text=True, cwd=probe_dir,
                                env=env, timeout=300)
    require("IMPORT-PROBE-OK" in result.stdout,
            f"the harness must import from the project root with PYTHONPATH unset "
            f"(stdout={result.stdout!r} stderr={result.stderr[-800:]!r})")
    record("the module draws no value, writes no file, imports no WP1", True)


def main() -> int:
    print(f"python : {sys.version.split()[0]}   -O={'Y' if not __debug__ else 'N'}")
    print("synthetic stand-in backends only; the 2^20 domain is never enumerated; "
          "no candidate, instance, ground truth or scientific value")
    check_coordinate_list()
    check_one_ulp_in_each_field()
    check_missing_coordinate_or_encoding()
    check_frozen_product()
    check_d013_refusal()
    check_positive_zero_read()
    check_no_coordinate_level_value()
    check_fail_closed()
    check_injected_exceptions()
    check_no_project_writes()

    # The cost estimate, printed as a labelled estimate (never a measurement).
    h.print_cost_estimate(d013_fired=False)
    h.print_cost_estimate(d013_fired=True)

    after = set(p for p in (ROOT / "research").rglob("*") if p.is_file())
    require(after == TREE_BEFORE,
            f"the fixture changed the project tree: {sorted(str(p) for p in after ^ TREE_BEFORE)}")
    # Bytecode is compared before/after.  It is NEVER required to be zero: the
    # real project carries a tracked baseline of .pyc files.
    require(set(ROOT.rglob("*.pyc")) == PYC_BEFORE, "the fixture wrote bytecode")

    failed = [name for name, ok, _ in RESULTS if not ok]
    print("=" * 78)
    print(f"checks={COUNT} recorded={len(RESULTS)} failed={len(failed)}")
    for name in failed:
        print(f"  FAILED: {name}")
    print("=" * 78)
    if failed:
        return 1
    print("PASS Section B item 2 harness fixtures; synthetic stand-in backends only; "
          "no project write, no candidate, no instance, no ground truth, no scientific value")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

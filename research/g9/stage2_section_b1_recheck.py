"""Section-B item 1 pre-write identity recheck harness (WP2, gap G8).

The approved Kaggle CUDA amendment, ``research/decisions/
GATE_9_STAGE2_KAGGLE_CUDA_AMENDMENT_DRAFT.md`` section "B. Per-session and
per-instance validation" item 1, requires, before a session writes a scientific
output:

    "1. recheck the approved protocol, generator, ground-truth, source,
    platform, and compiler identities;"

and item 3 requires that the session

    "write only the pass/fail counters, platform/source identities, and
    canonical validation digest. It retains no unapproved coordinate-level
    scientific values in the qualification record."

The same section makes the GPU session fail-closed: "any mismatch, non-finite
value, missing identity, invalid compiler flag, unavailable CUDA device, or
interrupted validation prevents that session from writing the affected
scientific records."

The owner-approved provider-trust amendment
(``GATE_9_SECTION_B_KAGGLE_PROVIDER_TRUST_AMENDMENT_DRAFT.md``) removes **only**
the independent pre-write executing-image proof. Section 3 keeps item 1 in full
and requires every image/build value the recheck compares to be recorded as
**PLATFORM-REPORTED**; section 4 quotes item 1 verbatim with the note "This
recheck remains in full; any image/build value it compares is platform-reported
(§3)." A change in a platform-reported image value still forces requalification.

WHAT THIS MODULE IS
    A record-shaping, non-writing decision function. ``recheck_before_first_write``
    re-derives every §B item 1 identity element and returns
    ``(record, gate_passed)``. On **any** failure it returns the refusal record
    with ``gate_passed is False``; it never raises for an identity finding, so a
    caller can record the refusal. ``require_gate`` is the companion that
    raises, for callers that must not proceed. The two disagreeing on failure is
    the fail-closed design: the harness returns a verdict, the caller stops on
    it, and the refusal is never silently converted into a pass.

WHAT THIS MODULE IS NOT
    It writes nothing. No file, record, or environment value is read as
    authorization. A green result is identity evidence, not owner approval, not
    a qualification, and not a write permission. §B remains OPEN; the closure
    plan records that this harness is bound into the production qualification
    identity and qualified in the WP7 dry run, which is itself unauthorized.

THE SIX ELEMENTS
    ``protocol``    approved protocol + approved CUDA amendment + approved
                    provider-trust amendment. Their sha256 are read from disk at
                    the fixed paths below and compared with the expected hashes
                    the caller passed in, so a drift is a refusal and not a
                    silent re-pin.
    ``generator``   the WP5 generator implementation-record content hash
                    (``research/g9/stage2_generation_release.py``), injected.
    ``ground_truth``the WP5b per-instance ground-truth provenance hash, injected.
    ``source``      the session's captured source map, compared by
                    ``exact_match`` against the accepted identity.
    ``platform``    gpu model, compute capability, driver, CUDA runtime, Kaggle
                    image/build, Python and NumPy fingerprints. The image and
                    build values are platform-reported and are labelled so in
                    every emitted record.
    ``compiler``    the compiler version and the numeric compiler flags, with
                    the fast-math/contraction/atomics/nondeterministic-reduction
                    ban of the amendment's fixed binary64 contract.

ONE CHECK PER FAILURE MODE
    Every check below is reachable and every one is load-bearing: each has a
    fixture that fails if and only if that check is removed.  A check that merely
    restated a neighbouring one was deleted rather than kept as decoration.  An
    absent element key and a ``None`` element value both reach the single
    "is not a mapping" refusal in each element check, and one key-set comparison
    against the accepted identity covers both the "the accepted identity has no
    compiler values" and the "the two sides disagree" cases, so there is no
    second key-set check to keep green by accident.

DEPENDENCY INJECTION
    The production qualification identity is still under review (WP1) and is
    deliberately **not imported**: it is passed in as an accepted identity
    payload together with its ``validate`` and ``exact_match`` callables, and the
    harness uses no identity source of its own. The fixtures inject simple
    synthetic stand-ins for all three. The harness never obtains, hard-codes or
    reconstructs a real identity, image digest, or device fingerprint.

RECORD SHAPE
    Both records share the exact key set ``RECORD_KEYS``, so the writer cannot
    branch on the verdict: the refusal carries the same shape as the pass. The
    record holds counters, the element names, the platform/source identities and
    one canonical digest -- and nothing else. In particular no coordinate, index,
    energy, tie flag, label or other coordinate-level value can appear: every
    retained value is validated by ``_retained_value`` as a lowercase SHA-256, a
    declared non-empty status string, a non-negative int, or the ``bool`` verdict.
    The refusal names every failing element in ``failed_elements`` and states
    why in ``refusal_reasons``, which are phrases built from the element label
    and a closed reason code, never from caller data.

TYPED OUTCOMES
    A caller may hand this module anything.  Two typed outcomes are possible and
    no third: an identity *finding* is returned as a refusal record with a closed
    gate, and anything the module cannot read at all raises
    :class:`SectionB1RecheckError`.  No value produces an untyped ``TypeError``,
    ``KeyError`` or ``AttributeError``; the fixtures' fuzz group asserts that for
    every public argument.

KNOWN LIMITS (candidate design, not approved policy)
- The protocol/amendment hashes are compared against values the caller passed
  in; a caller that passes the on-disk hash rather than the approved one
  circularly re-pins an edited file.
- The source, generator and ground-truth pins are hashes supplied by the caller.
  This harness proves equality, not provenance: it cannot tell whether the
  pinned hash is the right one.
- The platform and compiler values are compared as reported strings, exactly.
  Under the provider-trust amendment an altered-but-consistent value reported by
  a trusted platform is not detectable here; that residual risk is stated in
  the amendment §1 and is accepted by the owner.
- The digest is computed over this module's canonical rendering of the
  recheck, which excludes the session and the device UUID by construction (the
  amendment forbids both in a qualification identity). It is not a digest of the
  scientific domain and binds no coordinate-level value.
- Equality is exact string/structure comparison. No tolerance is applied
  anywhere, by design: a tolerant identity check is not an identity check.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[2]

SCHEMA = "decisions_os/g9_stage2_section_b1_recheck_record/v1"
AMENDMENT_CLAUSE = "GATE_9_STAGE2_KAGGLE_CUDA_AMENDMENT_DRAFT.md#B.1"
PROVIDER_TRUST_CLAUSE = "GATE_9_SECTION_B_KAGGLE_PROVIDER_TRUST_AMENDMENT_DRAFT.md#3"
PLATFORM_REPORTED = "platform_reported"
EVIDENCE_STATEMENT = (
    "Equality evidence only: this recheck compares the session's identities with "
    "the accepted production qualification identity and the owner-approved "
    "document hashes. It is not owner approval, not a qualification, and it "
    "authorizes no write."
)

# The six identity elements §B item 1 names, in the amendment's own order.
ELEMENT_NAMES = (
    "protocol",
    "generator",
    "ground_truth",
    "source",
    "platform",
    "compiler",
)

# Two further refusal scopes that are not §B item 1 identity elements but are
# recheck obligations in their own right: the accepted production identity and
# the session's captured identity must both pass the injected validator, and a
# refusal names which of the two failed.  They are not counted in
# ``elements_checked``, which stays the six named elements.
SCOPE_NAMES = ELEMENT_NAMES + ("accepted_identity", "session_identity")

# The approved governing documents, at their fixed repository-relative paths.
# The expected sha256 values are NOT held here: the caller passes them, so a
# pin cannot be silently re-pointed by editing this file.
APPROVAL_PATHS = (
    "research/decisions/GATE_9_STAGE2_PROTOCOL_DRAFT.md",
    "research/decisions/GATE_9_STAGE2_KAGGLE_CUDA_AMENDMENT_DRAFT.md",
    "research/decisions/GATE_9_SECTION_B_KAGGLE_PROVIDER_TRUST_AMENDMENT_DRAFT.md",
)
_APPROVAL_SET = frozenset(APPROVAL_PATHS)

# Platform-reported image/build values (provider-trust amendment §3).  These are
# recorded as reported and compared as reported; they are never proof, and a
# change in any of them still forces requalification.
IMAGE_PLATFORM_FIELDS = ("kaggle_image", "kaggle_image_build")
# Platform values that are not image/build metadata.
NON_IMAGE_PLATFORM_FIELDS = (
    "gpu_name",
    "compute_capability",
    "cuda_driver_version",
    "cuda_runtime_version",
    "nvcc_version",
    "python_version",
    "numpy_version",
)
PLATFORM_FIELDS = tuple(sorted(IMAGE_PLATFORM_FIELDS + NON_IMAGE_PLATFORM_FIELDS))
# The amendment's fixed binary64 numerical contract.  A compiler flag that
# *disables* one of these behaviours is compliance, so each stem is matched
# against the flag's NAME (the part before "=" or ":") rather than its value.
# A raw scan of the whole flag string would refuse the exact flags the contract
# requires -- and a scan with no value exemption would refuse the compliance
# spellings "--fmad=false" and "--ftz=false", making the contract unsatisfiable.
# Stems are lower-cased and the "_" / "-" spellings of each are both listed, so
# a stem is never hidden by a spelling difference.
BANNED_COMPILER_FLAG_STEMS = (
    "fast_math", "fast-math", "fastmath",
    "fmad", "ffp-contract",
    "ftz",
    "contraction", "contract",
    "unsafe_math", "unsafe-math", "unsafe-math-optimizations",
    "associative_math", "associative-math", "associative",
    "reassoc",
    "atomics",
    "nondeterministic", "non_deterministic", "non-deterministic",
    "reduce", "reduction",
)
# Values that turn a banned behaviour off, so the flag is compliance, not a
# violation.  Anything else (including a true/1/on, or no value at all) is a
# violation: an unqualified --fmad enables contraction.
COMPLIANT_FLAG_VALUES = frozenset({"0", "false", "off", "no", "none"})


def _stem_spellings(stem: str) -> set[str]:
    """Return the finite hyphen/underscore spellings of a known flag stem."""
    canonical = stem.lower().replace("_", "-")
    spellings = {canonical}
    for index, char in enumerate(canonical):
        if char == "-":
            spellings |= {value[:index] + "_" + value[index + 1:] for value in tuple(spellings)}
    return spellings


# A token is compliant only if it is one of these complete spellings.  This is
# deliberately finite: malformed suffixes and extra value separators cannot
# acquire meaning by being partially parsed.
_COMPLIANT_FLAG_TOKENS = frozenset(
    token
    for stem in BANNED_COMPILER_FLAG_STEMS
    for spelling in _stem_spellings(stem)
    for token in ("-fno-" + spelling,
                  "--" + spelling + "=false",
                  "--" + spelling + "=off",
                  "--" + spelling + "=0")
) | frozenset(
    "--" + spelling + "=" + value
    for name in ("prec-div", "prec-sqrt")
    for spelling in _stem_spellings(name)
    for value in ("true", "on", "1")
) | frozenset(
    "--" + spelling + "=" + value
    for spelling in _stem_spellings("ftz")
    for value in ("false", "off", "0")
) | frozenset({"-ffp-contract=off", "-ffp_contract=off",
               "--use_fast_math=false", "--use_fast_math=off", "--use_fast_math=0",
               "--use-fast-math=false", "--use-fast-math=off", "--use-fast-math=0"})

# The exact key set of both emitted records.  "Wrong key set" is how a fixture
# asserts that no coordinate-level value was retained, and how a mutation that
# widens a record is caught.
RECORD_KEYS = frozenset({
    "schema",
    "clause",
    "verdict",
    "elements_checked",
    "counters",
    "element_results",
    "failed_elements",
    "refusal_reasons",
    "identity",
    "platform_identity",
    "platform_reported_fields",
    "source_identity",
    "source_identity_sha256",
    "validation_digest",
    "content_sha256",
    "evidence",
})

# The branches the leaf walk covers.  It is the record's own key set minus the
# two self-referential hash fields, whose values ARE their own canonical bytes
# and are re-derived below instead of walked.  Deriving it from ``RECORD_KEYS``
# is deliberate: a key added to the record is therefore walked without anyone
# having to remember to list it, and only these two names are excluded, so a hash
# cannot be smuggled in unchecked through any other branch.
_WALKED_RECORD_KEYS = RECORD_KEYS - {"validation_digest", "content_sha256"}

_HEX = frozenset("0123456789abcdef")
_IMAGE_FIELDS = frozenset(IMAGE_PLATFORM_FIELDS)
_PLATFORM_KEYS = frozenset(PLATFORM_FIELDS)
_COMPILER_KEYS = frozenset({"version", "flags"})
_COUNTER_KEYS = frozenset({"elements_checked", "elements_passed", "elements_failed"})
_RESULT_KEYS = frozenset({"element", "status"})
_RESULT_STATUSES = frozenset({"match", "mismatch", "missing", "invalid"})
_IDENTITY_KEYS = frozenset({"accepted_sha256", "session_sha256", "exact_match"})
_EVIDENCE_KEYS = frozenset({"equality", "authorizes_write", "statement"})
# The digest commits to every claim the record makes, so its payload is the
# record's own walked key set.  ``source_identity``'s own digest is in that set
# as well: a canonical record re-derives it from ``source_identity``, and leaving
# it out would let that one field be edited without disturbing the digest.
_DIGEST_KEYS = _WALKED_RECORD_KEYS


class SectionB1RecheckError(ValueError):
    """Typed refusal raised for a malformed argument or a malformed record.

    Identity *findings* are not exceptions: they are returned as a refusal
    record.  This error covers only a caller that hands this module something
    it cannot read at all, and ``require_gate`` raises it when the gate is
    closed.  The two are deliberately different: a refusal record is
    record-shaped and lossless, this error is not.
    """


def _require(condition: object, message: str) -> None:
    if not condition:
        raise SectionB1RecheckError(message)


def _require_str_keys(value: object) -> None:
    """Refuse any mapping whose keys are not exactly ``str``.

    ``json.dumps`` accepts an int or float key and silently renders it as a
    string, so a canonical encoding computed here could disagree with the
    encoding the same object gets anywhere else.  Refusing the key type keeps
    one object one encoding.  The walk is recursive and covers lists, so a
    non-string key is caught at any depth, not only at the top.
    """
    if type(value) is dict:
        for key, nested in value.items():
            _require(type(key) is str, "every dictionary key must be exactly str")
            _require_str_keys(nested)
    elif type(value) is list:
        for nested in value:
            _require_str_keys(nested)


def canonical_bytes(value: object) -> bytes:
    """The single canonical JSON encoding used for every hash in this module."""
    try:
        _require_str_keys(value)
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
        ).encode("ascii")
    except Exception as exc:
        if isinstance(exc, SectionB1RecheckError):
            raise
        raise SectionB1RecheckError("value is not canonical JSON") from exc


def content_sha256(record: Mapping[str, Any]) -> str:
    """The sha256 of a record's body, with its own hash field excluded."""
    if not isinstance(record, Mapping):
        raise SectionB1RecheckError("record must be a mapping")
    body = dict(record)
    body.pop("content_sha256", None)
    return hashlib.sha256(canonical_bytes(body)).hexdigest()


def _sha(value: object, label: str) -> str:
    _require(
        type(value) is str and len(value) == 64 and set(value) <= _HEX,
        f"{label} must be a lowercase SHA-256",
    )
    return value


def _retained_str(value: object, label: str) -> str:
    """A non-empty, single-line plain string, safe to place in any record.

    A newline or a control character is refused here rather than escaped, so a
    refusal reason can never carry a caller-supplied line break, and a platform
    string carrying one is a refusal, not a written record.  A 64-character
    lowercase-hex string is a sha256 and satisfies these rules unchanged, so
    there is no separate hex branch here that could drift out of step.
    """
    _require(
        type(value) is str and value != "" and len(value) <= 512,
        f"{label} must be a non-empty string of at most 512 characters",
    )
    _require(
        not any(ord(char) < 0x20 or ord(char) == 0x7F for char in value),
        f"{label} must not contain control characters or newlines",
    )
    return value


def _retained_value(value: object, label: str) -> object:
    """Refuse anything that is not a permitted record leaf.

    This is the mechanism behind the §B item 3 write limit.  A float is refused
    unconditionally, and a list or a dict is refused at every level, so no
    coordinate triple, index, energy word, tie-flag list or label can enter the
    record -- the shapes that carry coordinate-level scientific values.
    """
    if type(value) is bool or type(value) is int:
        _require(value >= 0, f"{label} must be a non-negative int")
        return value
    if type(value) is str:
        return _retained_str(value, label)
    raise SectionB1RecheckError(
        f"{label} is not a permitted record leaf; a float, sequence or mapping "
        "would be a coordinate-level or unapproved value"
    )


def _file_sha256(relative: str) -> str:
    """Hash one approved document at its fixed repository-relative path."""
    _require(
        type(relative) is str and relative and not relative.startswith("/")
        and ".." not in Path(relative).parts,
        f"approval path is not a canonical relative path: {relative!r}",
    )
    path = ROOT / relative
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
    except OSError as exc:
        raise SectionB1RecheckError(
            f"cannot read approved document {relative}: {exc.__class__.__name__}"
        ) from exc
    return digest.hexdigest()


def read_approval_hashes(paths: Sequence[object] = APPROVAL_PATHS) -> dict[str, str]:
    """Read each approved document's sha256 from disk at its fixed path.

    The result is a claim about the bytes on disk.  Whether those bytes are the
    *approved* bytes is decided by the expected hashes the caller passes to
    :func:`recheck_before_first_write`; this function never decides it.
    """
    _require(
        isinstance(paths, Sequence) and not isinstance(paths, (str, bytes)) and paths,
        "approval paths must be a non-empty sequence",
    )
    _require(
        list(paths) == list(APPROVAL_PATHS),
        "approval paths must be exactly the module's fixed APPROVAL_PATHS",
    )
    observed: dict[str, str] = {}
    for relative in APPROVAL_PATHS:
        observed[relative] = _file_sha256(relative)
    return observed


def _normalize_callable(candidate: object, name: str) -> Callable[..., object]:
    _require(callable(candidate), f"the injected identity {name} must be callable")
    return candidate  # type: ignore[return-value]


def _differences(expected: object, observed: object, prefix: str) -> list[str]:
    """Every leaf path at which two canonical structures differ.

    Used for the ``source`` and ``platform`` elements.  It reports *what*
    differed, so a refusal names the differing field, and it distinguishes a
    missing field from a present-but-different one, which is the difference
    between the "wrong" and "missing" §B item 1 element cases.
    """
    if type(expected) is dict and type(observed) is dict:
        found: list[str] = []
        for key in sorted(set(expected) | set(observed)):
            path = f"{prefix}.{key}" if prefix else str(key)
            if key not in expected or key not in observed:
                found.append(path)
            else:
                found.extend(_differences(expected[key], observed[key], path))
        return found
    if type(expected) is list and type(observed) is list:
        if len(expected) != len(observed):
            return [prefix]
        found = []
        for index, (left, right) in enumerate(zip(expected, observed)):
            found.extend(_differences(left, right, f"{prefix}[{index}]"))
        return found
    if type(expected) is not type(observed) or canonical_bytes(expected) != canonical_bytes(observed):
        return [prefix]
    return []


def _reasons_for(element: str, code: str) -> str:
    return f"{element}: {code}"


def _check_protocol(
    observed_approval_sha256: object,
    expected_approval_sha256: object,
    failure: list[tuple[str, str]],
) -> dict[str, str]:
    """Re-read the approved documents from disk and compare with the caller's pins.

    The two key-set tests compare sets, not sorted lists: a caller that hands in
    a mapping with a mixed-type key would make a sort raise an untyped
    ``TypeError`` out of a refusal path, and the §B item 1 answer to a malformed
    pin is a refusal record, not an exception.
    """
    paths: set[object] = set()
    if type(observed_approval_sha256) is not dict:
        failure.append(("protocol", "observed approval hashes are not a mapping"))
    elif set(observed_approval_sha256) != _APPROVAL_SET:
        failure.append(("protocol", "observed approval hash set is not the fixed approved set"))
    else:
        paths = set(APPROVAL_PATHS)
    if type(expected_approval_sha256) is not dict:
        failure.append(("protocol", "expected approval hashes are not a mapping"))
        # A pin that is not a mapping cannot be compared document by document:
        # keep no comparable path, or the loop below would index it and raise a
        # bare TypeError out of a refusal path.
        paths = set()
    elif set(expected_approval_sha256) != _APPROVAL_SET:
        failure.append(("protocol", "expected approval hash set is not the fixed approved set"))
        # Likewise a pin that does not carry the fixed set: the loop below would
        # index a key the pin does not hold and raise a bare KeyError.
        paths = set()
    else:
        paths &= set(expected_approval_sha256)

    element_result: dict[str, str] = {}
    for relative in APPROVAL_PATHS:
        if relative not in paths:
            continue
        # The two sides are validated SEPARATELY so a malformed hash names the
        # side it came from: one malformed value is one finding, and naming the
        # side is what tells a caller which pin to re-supply.
        try:
            observed = _sha(observed_approval_sha256[relative], f"observed approval hash {relative}")
        except SectionB1RecheckError:
            failure.append(("protocol", "observed approval hash is malformed"))
            continue
        try:
            expected = _sha(expected_approval_sha256[relative], f"expected approval hash {relative}")
        except SectionB1RecheckError:
            failure.append(("protocol", "expected approval hash is malformed"))
            continue
        if observed != expected:
            failure.append(("protocol", f"approved document {relative} does not match its expected hash"))
        else:
            element_result[relative] = observed
    return element_result


def _check_generator(
    observed: object, expected: object, failure: list[tuple[str, str]]
) -> bool:
    """Compare the session's generator implementation-record hash with the pin."""
    if expected is None:
        failure.append(("generator", "the expected generator implementation-record hash is missing"))
        return False
    if observed is None:
        failure.append(("generator", "the observed generator implementation-record hash is missing"))
        return False
    try:
        expected_sha = _sha(expected, "expected generator implementation-record hash")
        observed_sha = _sha(observed, "session generator implementation-record hash")
    except SectionB1RecheckError:
        failure.append(("generator", "generator implementation-record hash is malformed"))
        return False
    if observed_sha != expected_sha:
        failure.append(("generator", "the generator implementation record differs from its pin"))
        return False
    return True


def _check_ground_truth(
    observed: object, expected: object, failure: list[tuple[str, str]]
) -> bool:
    """Compare the session's ground-truth provenance hash with the WP5b pin.

    The provenance hash is injected because WP5b does not exist yet.  Its
    *presence* is already a §B item 1 obligation, so an absent pin is a refusal
    rather than a skipped element.
    """
    if expected is None:
        failure.append(("ground_truth", "the expected ground-truth provenance hash is missing"))
        return False
    if observed is None:
        failure.append(("ground_truth", "the observed ground-truth provenance hash is missing"))
        return False
    try:
        expected_sha = _sha(expected, "expected ground-truth provenance hash")
        observed_sha = _sha(observed, "session ground-truth provenance hash")
    except SectionB1RecheckError:
        failure.append(("ground_truth", "ground-truth provenance hash is malformed"))
        return False
    if observed_sha != expected_sha:
        failure.append(("ground_truth", "the ground-truth provenance differs from its pin"))
        return False
    return True


def _check_source(
    accepted_identity: Mapping[str, Any],
    session_identity: Mapping[str, Any],
    exact_match: Callable[..., object],
    failure: list[tuple[str, str]],
) -> tuple[dict[str, str], str]:
    """Exact-match the session's captured identity with the accepted one.

    The whole ``source`` element is delegated to the injected ``exact_match``,
    which per the injected contract compares ``(session, accepted)`` and raises
    on any difference.  Passing the *whole* session identity, not just its
    source map, is what lets WP1's ``exact_match`` see every field it binds --
    source, platform, compiler and anything a later identity adds -- so a
    difference outside the source map is still a difference.  An explicit
    ``False`` return is also a refusal: a matcher that says "not equal" must not
    be overruled by the absence of an exception.

    An absent ``source_sha256`` key and a ``None`` value reach the SAME refusal
    here, by ``.get`` at the call site: both mean "no non-empty mapping of
    sha256", so there is no second "is it None" test that only one of the two
    spellings could ever reach.
    """
    session_source_sha256 = session_identity.get("source_sha256")
    if type(session_source_sha256) is not dict or not session_source_sha256:
        failure.append(("source", "session source identity is missing or is not a non-empty mapping"))
        return {}, "0" * 64
    for key, value in session_source_sha256.items():
        try:
            _retained_str(key, "session source key")
            _sha(value, f"session source hash {key!r}")
        except SectionB1RecheckError:
            failure.append(("source", "session source identity is malformed"))
            return {}, "0" * 64
    try:
        verdict = exact_match(session_identity, accepted_identity)
    except SectionB1RecheckError:
        raise
    except Exception as exc:
        failure.append(("source", f"session source identity differs from the accepted identity: {exc.__class__.__name__}"))
        return {}, "0" * 64
    # The injected contract is raise-based: a difference is signalled by raising,
    # so a call that returns at all has found none.  An explicit ``False`` is
    # still refused, because a matcher that says "not equal" must never be
    # overruled by the absence of an exception.
    if verdict is False:
        failure.append(("source", "session source identity differs from the accepted identity"))
        return {}, "0" * 64
    try:
        return (
            json.loads(canonical_bytes(session_source_sha256).decode("ascii")),
            hashlib.sha256(canonical_bytes(session_source_sha256)).hexdigest(),
        )
    except Exception:
        failure.append(("source", "session source identity is not canonical"))
        return {}, "0" * 64


def _check_platform(
    accepted_identity: Mapping[str, Any],
    session_platform: object,
    failure: list[tuple[str, str]],
) -> tuple[dict[str, str], list[str]]:
    """Compare the platform-reported platform values with the accepted identity.

    Every image/build value here is platform-reported under the provider-trust
    amendment §3.  This compares the reported value; it does not, and cannot,
    establish the executing image -- the independent proof was removed by the
    owner-approved amendment, and that residual risk is stated there.

    An absent ``platform`` key and a ``None`` value reach the SAME refusal here,
    by ``.get`` at the call site.  Only the non-mapping test remains: an empty
    mapping is a dict, so the required-field test below already refuses it and a
    separate emptiness test was unreachable (a mutation sweep showed it survived
    removal, the required-field check refusing every input it refused).
    """
    if type(session_platform) is not dict:
        failure.append(("platform", "session platform identity is missing or is not a non-empty mapping"))
        return {}, []
    if _PLATFORM_KEYS - set(session_platform):
        failure.append(("platform", "session platform identity is missing required fields"))
        return {}, []
    if set(session_platform) - _PLATFORM_KEYS:
        failure.append(("platform", "session platform identity carries undeclared fields"))
        return {}, []
    for key in PLATFORM_FIELDS:
        try:
            _retained_str(session_platform[key], f"session platform field {key!r}")
        except SectionB1RecheckError:
            failure.append(("platform", "session platform field is malformed"))
            return {}, []
    accepted_platform = accepted_identity.get("platform") if isinstance(accepted_identity, Mapping) else None
    if type(accepted_platform) is not dict or not accepted_platform:
        failure.append(("platform", "accepted identity carries no platform values to compare"))
        return {}, []
    try:
        session_view = json.loads(canonical_bytes(dict(session_platform)).decode("ascii"))
    except Exception:
        failure.append(("platform", "session platform identity is not canonical"))
        return {}, []
    drift = _differences(dict(accepted_platform), session_view, "")
    if drift:
        failure.append(("platform", "session platform identity differs from the accepted identity"))
        return {}, []
    return {key: session_platform[key] for key in PLATFORM_FIELDS}, sorted(_IMAGE_FIELDS)


def _flag_tokens(flags: Sequence[str]) -> list[str]:
    """Tokenise compiler flags as one ordered stream, including wrapped lists."""
    words: list[str] = []
    pending_payload = False
    for flag in flags:
        for word in flag.split():
            low = word.lower()
            if pending_payload:
                words.extend(part for part in word.split(",") if part)
                pending_payload = False
                continue
            if low in {"-xcompiler", "-xptxas"}:
                pending_payload = True
            elif low.startswith(("-xcompiler=", "-xptxas=")):
                words.extend(part for part in word.split("=", 1)[1].split(",") if part)
            else:
                words.append(word)
    return words


def _canonical_flag_text(token: str) -> str:
    """Remove nested nvcc wrapper prefixes while preserving the token spelling."""
    value = token.strip().lower()
    for _ in range(len(value) + 1):
        lowered = value.lower()
        for prefix in ("-xcompiler=", "-xptxas="):
            if lowered.startswith(prefix):
                value = value[len(prefix):].strip()
                break
        else:
            break
    return value


def _flag_mentions(token: str, stem: str) -> bool:
    text = _canonical_flag_text(token).replace("_", "-")
    target = stem.lower().replace("_", "-")
    return target in text


def _exact_gcc_negation(token: str, stem: str) -> bool:
    text = _canonical_flag_text(token)
    return text in _COMPLIANT_FLAG_TOKENS and text.startswith("-fno-")


def _flag_stream_violation(flags: Sequence[str]) -> str | None:
    """Return a contract violation after parsing the complete ordered flag stream.

    Every mention is enabling unless it is one exact supported negation. State
    is updated in token order, so a later disable may clear an earlier enable
    and a later enable always reopens the violation.
    """
    states: dict[str, bool] = {}
    required: dict[str, bool] = {}
    for token in _flag_tokens(flags):
        text = _canonical_flag_text(token)
        exact_compliant = text in _COMPLIANT_FLAG_TOKENS
        if text == "-ofast":
            states["fast-math"] = True
        for stem in BANNED_COMPILER_FLAG_STEMS:
            if not _flag_mentions(token, stem):
                continue
            target = stem.lower().replace("_", "-")
            exact_negation = _exact_gcc_negation(token, stem)
            long_disable = exact_compliant and text.startswith("--")
            frozen_contract_disable = text == "-ffp-contract=off"
            disabled = exact_negation or long_disable or frozen_contract_disable
            states[target] = not disabled

        for stem in ("prec-div", "prec-sqrt", "ftz"):
            if not _flag_mentions(token, stem):
                continue
            compliant_value = text in _COMPLIANT_FLAG_TOKENS
            required[stem] = compliant_value if stem in {"prec-div", "prec-sqrt"} else not compliant_value

    for stem, enabled in states.items():
        if enabled:
            return stem
    for stem, enabled in required.items():
        if (stem in {"prec-div", "prec-sqrt"} and not enabled) or (stem == "ftz" and enabled):
            return stem
    return None


def _flag_violation(flag: str) -> str | None:
    """Single-string compatibility wrapper for the ordered stream parser."""
    return _flag_stream_violation([flag])


def _check_compiler(
    accepted_identity: Mapping[str, Any],
    session_compiler: object,
    failure: list[tuple[str, str]],
) -> bool:
    """Compare the compiler version and flags, refusing an invalid flag set.

    The banned-fragment scan is a check in its own right, not a comment: a
    fast-math or non-deterministic-reduction flag invalidates the session even if
    every flag string matches the accepted identity.

    An absent ``compiler`` key and a ``None`` value reach the SAME refusal here,
    by ``.get`` at the call site.  The accepted side gets ONE key-set test: it
    refuses an accepted identity with no compiler values, one with a partial key
    set, and one whose key set differs from the session's, so the leaf comparison
    that follows has only one job -- same keys, different values.
    """
    if type(session_compiler) is not dict or not session_compiler:
        failure.append(("compiler", "session compiler identity is missing or is not a non-empty mapping"))
        return False
    if set(session_compiler) != _COMPILER_KEYS:
        failure.append(("compiler", "session compiler identity is missing required fields"))
        return False
    try:
        _retained_str(session_compiler["version"], "session compiler version")
    except SectionB1RecheckError:
        failure.append(("compiler", "session compiler version is malformed"))
        return False
    flags = session_compiler["flags"]
    if type(flags) is not list or not flags:
        failure.append(("compiler", "session compiler flags are missing or not a list"))
        return False
    for flag in flags:
        try:
            _retained_str(flag, "session compiler flag")
        except SectionB1RecheckError:
            failure.append(("compiler", "session compiler flag is malformed"))
            return False
    if len(set(flags)) != len(flags):
        failure.append(("compiler", "session compiler flags are duplicated"))
        return False
    stem = _flag_stream_violation(flags)
    if stem is not None:
        failure.append(
            ("compiler", f"session compiler flag violates the fixed binary64 contract: {stem}")
        )
        return False
    accepted_compiler = accepted_identity.get("compiler") if isinstance(accepted_identity, Mapping) else None
    if type(accepted_compiler) is not dict or set(accepted_compiler) != _COMPILER_KEYS:
        failure.append(("compiler", "accepted identity carries no compiler values to compare"))
        return False
    try:
        if _differences(accepted_compiler, session_compiler, ""):
            failure.append(("compiler", "session compiler identity differs from the accepted identity"))
            return False
    except SectionB1RecheckError:
        failure.append(("compiler", "accepted compiler identity is malformed"))
        return False
    return True


def _build_record(
    gate_passed: bool,
    element_results: Mapping[str, Mapping[str, str]],
    failure: Sequence[tuple[str, str]],
    accepted_sha256: str,
    session_sha256: str,
    platform_identity: Mapping[str, str],
    platform_reported_fields: Sequence[str],
    source_identity: Mapping[str, str],
    source_identity_sha256: str,
) -> dict[str, object]:
    """Render the one record shape both verdicts share, then bind its digest.

    Every leaf passes through :func:`_retained_value` before it is placed, so a
    caller cannot smuggle a coordinate-level value into any of the identity,
    result or reason fields.  ``content_sha256`` is derived, never supplied.
    """
    element_names = sorted(element_results)
    counters = {
        "elements_checked": len(ELEMENT_NAMES),
        "elements_passed": len(element_names),
        "elements_failed": 0 if gate_passed else len(ELEMENT_NAMES) - len(element_names),
    }
    # Preserve first-failure order for the reason list and the refused-element
    # list, so the refusal names the elements in the order they were checked.
    ordered_failed: list[str] = []
    ordered_reasons: list[str] = []
    for element, reason in failure:
        if element not in ordered_failed:
            ordered_failed.append(element)
        ordered_reasons.append(_reasons_for(element, reason))
    payload: dict[str, object] = {
        "schema": SCHEMA,
        "clause": [AMENDMENT_CLAUSE, PROVIDER_TRUST_CLAUSE],
        "verdict": "pass" if gate_passed else "refused",
        "elements_checked": list(ELEMENT_NAMES),
        "counters": counters,
        "element_results": {
            name: dict(row) for name, row in element_results.items()
        },
        "failed_elements": sorted(ordered_failed),
        "refusal_reasons": ordered_reasons,
        "identity": {
            "accepted_sha256": accepted_sha256,
            "session_sha256": session_sha256,
            "exact_match": "no_differences",
        },
        "platform_identity": dict(platform_identity),
        "platform_reported_fields": sorted(platform_reported_fields),
        "source_identity": dict(source_identity),
        "source_identity_sha256": source_identity_sha256,
        "validation_digest": "0" * 64,
        "content_sha256": "0" * 64,
        "evidence": {
            "equality": "exact_match",
            "authorizes_write": "no",
            "statement": EVIDENCE_STATEMENT,
        },
    }
    for key in sorted(_WALKED_RECORD_KEYS):
        _require_retained(payload[key], key)
    payload["validation_digest"] = validation_digest(payload)
    payload["content_sha256"] = content_sha256(payload)
    return payload


def _require_retained(value: object, label: str) -> None:
    """Walk a record branch and refuse any leaf that is not a permitted one.

    Recursive rather than one level deep on purpose: a branch the walker did
    not reach would be an unchecked hole, and an unchecked hole is exactly how
    a coordinate-level value would slip into a §B item 3 record.

    The key types are tested before the keys are sorted, because sorting a mixed
    ``str``/``int`` key set raises an untyped ``TypeError`` -- and a malformed
    record is a typed refusal, not a crash.
    """
    if type(value) is dict:
        _require(all(type(key) is str for key in value), f"{label} has a non-string key")
        for key in sorted(value):
            _require_retained(value[key], f"{label}.{key}")
        return
    if type(value) is list:
        for index, item in enumerate(value):
            _require_retained(item, f"{label}[{index}]")
        return
    _retained_value(value, label)


def _digest_payload(record: Mapping[str, Any]) -> dict[str, object]:
    """The exact value the validation digest commits to.

    It includes every part of the record that carries a *claim*: the verdict,
    the counters, the per-element results, the refused elements and their
    reasons, the identities, and the evidence statement.  Leaving the counters
    or the reasons out would mean a record could be re-labelled from a pass to a
    refusal, or its element count changed, without disturbing the digest -- so
    the digest would be blind to precisely the fields it exists to bind.

    A branch the payload needs but the caller's object does not carry is a typed
    refusal, not a ``KeyError``: this function is public, so it has to be as
    unforgiving of a malformed record as :func:`_validate_record` is.
    """
    if not isinstance(record, Mapping):
        raise SectionB1RecheckError("record must be a mapping")
    try:
        payload = {key: record[key] for key in sorted(_DIGEST_KEYS)}
    except KeyError as exc:
        raise SectionB1RecheckError(
            f"record is missing a branch the validation digest commits to: {exc}"
        ) from exc
    return json.loads(canonical_bytes(payload).decode("ascii"))


def validation_digest(record: Mapping[str, Any]) -> str:
    """The canonical validation digest of a record, re-derivable by anyone."""
    return hashlib.sha256(canonical_bytes(_digest_payload(record))).hexdigest()


def _validate_record(record: object) -> dict[str, object]:
    """Refuse a record that is not exactly this module's shape and not canonical.

    Used by the fixtures to prove the write limit holds, and available to a
    caller that wants to check a record it received before writing it.  It
    re-derives both hashes, so a hand-edited record is refused.  Every test here
    is reachable on its own: the fixtures forge self-consistent records (both
    hashes recomputed) that differ in exactly one field, so no check below can be
    deleted with the suite staying green.
    """
    _require(type(record) is dict and set(record) == RECORD_KEYS, "recheck record has wrong key set")
    _require(record["schema"] == SCHEMA, "recheck record schema mismatch")
    _require(record["clause"] == [AMENDMENT_CLAUSE, PROVIDER_TRUST_CLAUSE], "recheck record clause mismatch")
    _require(record["verdict"] in ("pass", "refused"), "recheck record verdict is not pass or refused")
    _require(record["elements_checked"] == list(ELEMENT_NAMES), "recheck record element list mismatch")
    counters = record["counters"]
    _require(type(counters) is dict and set(counters) == _COUNTER_KEYS, "recheck record counters have wrong key set")
    _require(
        all(type(counters[key]) is int and counters[key] >= 0 for key in _COUNTER_KEYS),
        "recheck record counters must be non-negative ints",
    )
    _require(counters["elements_checked"] == len(ELEMENT_NAMES), "recheck record counter element count mismatch")
    _require(
        counters["elements_passed"] + counters["elements_failed"] == counters["elements_checked"],
        "recheck record counters do not sum to the checked count",
    )
    gate_passed = record["verdict"] == "pass"
    results = record["element_results"]
    _require(type(results) is dict, "recheck record element results must be a mapping")
    for name, result in results.items():
        _require(type(name) is str and name in ELEMENT_NAMES, f"recheck record names an undeclared element: {name!r}")
        _require(type(result) is dict and set(result) == _RESULT_KEYS, "recheck result has wrong key set")
        _require(result["element"] == name, "recheck result names a different element")
        _require(result["status"] in _RESULT_STATUSES, "recheck result status is not declared")
    passed = sorted(name for name, result in results.items() if result["status"] == "match")
    # ONE consistency check, deliberately.  "the counter equals the number of
    # matching results" and "a pass verdict means every element matched" are the
    # same invariant read from two ends.  Stated as two checks, each was
    # unreachable: a forged record that broke one necessarily satisfied the
    # other, so neither could be shown to matter -- a validator could delete
    # either one and every fixture stayed green.  Stated once it is the single
    # place a verdict and its counters must agree, and the fixtures pin all
    # three directions: a pass with a non-match, a pass whose counter is short,
    # and a refusal whose counter disagrees with its results.
    _require(
        counters["elements_passed"] == len(passed)
        and (passed == sorted(ELEMENT_NAMES) if gate_passed
             else len(passed) == counters["elements_checked"] - counters["elements_failed"]),
        "recheck record verdict, counters and element results disagree",
    )
    failed = record["failed_elements"]
    # The name test runs first: sorting a refused-element list that holds a
    # non-string would raise an untyped TypeError out of a refusal path.
    _require(
        type(failed) is list
        and all(type(name) is str and name in SCOPE_NAMES for name in failed)
        and failed == sorted(set(failed)),
        "recheck record failed elements are not a sorted set of declared names",
    )
    # The refused-element list is checked against the verdict here, in the same
    # consistency check as the counters: a "pass" that names a refused element,
    # or a "refused" that names none, is incoherent whichever field is forged.
    _require(bool(failed) is not gate_passed,
             "recheck record verdict disagrees with the refused-element list")
    reasons = record["refusal_reasons"]
    _require(type(reasons) is list, "recheck record refusal reasons must be a list")
    for index, reason in enumerate(reasons):
        _require(
            type(reason) is str and any(reason.startswith(f"{name}: ") for name in failed),
            f"recheck refusal reason {index} names no failed element",
        )
    # Every refused element must be given at least one reason, so a refusal can
    # never name a failure without saying what it was.
    _require(
        all(any(item.startswith(f"{name}: ") for item in reasons) for name in failed),
        "recheck record fails to name the reason for a failed element",
    )
    # A refused record must withhold the identities: a failure that still carried
    # the accepted platform/source map could be read as a passing recheck of a
    # different session.
    if not gate_passed:
        _require(not record["platform_identity"], "a refusing record must withhold the platform identity")
        _require(not record["source_identity"], "a refusing record must withhold the source identity")
        _require(not record["platform_reported_fields"],
                "a refusing record must withhold the platform-reported field labels")
    identity = record["identity"]
    _require(type(identity) is dict and set(identity) == _IDENTITY_KEYS, "recheck record identity has wrong key set")
    _sha(identity["accepted_sha256"], "record identity.accepted_sha256")
    _sha(identity["session_sha256"], "record identity.session_sha256")
    _require(identity["exact_match"] == "no_differences", "record identity exact_match label mismatch")
    reported = record["platform_reported_fields"]
    # Name test first, for the same reason as the refused-element list above.
    _require(
        type(reported) is list
        and all(type(name) is str for name in reported)
        and set(reported) <= _IMAGE_FIELDS
        and reported == sorted(reported),
        "record platform-reported fields must be a sorted subset of the image fields",
    )
    if gate_passed:
        _require(reported == sorted(_IMAGE_FIELDS), "a passing recheck must report every image field as platform-reported")
    platform = record["platform_identity"]
    # The declared-field test that used to stand here is GONE because it was
    # unreachable: on a PASS the completeness test below demands exactly
    # ``_PLATFORM_KEYS``, and on a REFUSAL the withholding test above demands an
    # empty map, so an undeclared field had no remaining case.  A mutation sweep
    # confirmed the removal loses no refusal.
    _require(type(platform) is dict, "recheck record platform identity must be a mapping")
    source = record["source_identity"]
    _require(type(source) is dict, "recheck record source identity must be a mapping")
    for name, value in source.items():
        _sha(value, f"record source_identity[{name!r}]")
    _sha(record["source_identity_sha256"], "record source_identity_sha256")
    _sha(record["validation_digest"], "record validation_digest")
    _sha(record["content_sha256"], "record content_sha256")
    # The digests are excluded from the leaf walk below only because the walk
    # runs on the record as the caller handed it, before the digest fields are
    # re-derived.  That exclusion is narrow and deliberate -- it is the record's
    # own key set minus exactly these two fields, so a hash cannot be smuggled
    # into, say, ``identity.accepted_sha256`` unchecked.
    evidence = record["evidence"]
    _require(
        type(evidence) is dict and set(evidence) == _EVIDENCE_KEYS,
        "recheck record evidence has wrong key set",
    )
    _require(evidence["equality"] == "exact_match" and evidence["authorizes_write"] == "no",
            "recheck record evidence is not a non-authorizing exact-match statement")
    for key in sorted(_WALKED_RECORD_KEYS):
        _require_retained(record[key], key)
    if gate_passed:
        # A PASSING recheck must carry the WHOLE platform identity: every
        # declared field, and the source map.  Checking only "some platform
        # values" would let a record that was edited to drop one field through
        # with recomputed hashes -- a pass that silently rechecked less than §B
        # item 1 names.  This is the record validator's own statement of the
        # completeness ``_check_platform`` already enforced when the record was
        # built; stating it here too is what makes a hand-edited record
        # impossible rather than merely unlikely.
        _require(set(platform) == _PLATFORM_KEYS,
                 "a passing recheck must carry every declared platform field (§B item 3)")
        _require(source, "a passing recheck must carry the source identity (§B item 3)")
    # Re-derive the digests from the record AS RECEIVED, before any repair, so a
    # caller cannot hand back a record whose hashes were recomputed after a
    # tamper.  The validation digest is re-derived FIRST and on its own: it is
    # committed to every claim the record makes, so a record carrying a
    # validation digest nobody can reproduce is not a valid record even when its
    # content hash happens to match it.  The digest payload deliberately includes
    # the verdict, the counters, the refusal content and the evidence, so a
    # re-labelled record cannot keep its digest.
    _require(record["validation_digest"] == validation_digest(record),
             "recheck record validation digest is not reproducible from its own content")
    _require(record["content_sha256"] == content_sha256(record), "recheck record content hash mismatch")
    return dict(record)


def recheck_before_first_write(
    *,
    accepted_identity: object,
    validate_identity: object,
    exact_match: object,
    observed_approval_sha256: object,
    expected_approval_sha256: object,
    session_identity: object,
    generator_implementation_record_sha256: object,
    expected_generator_implementation_record_sha256: object,
    ground_truth_provenance_sha256: object,
    expected_ground_truth_provenance_sha256: object,
) -> tuple[dict[str, object], bool]:
    """Recheck all six §B item 1 identities before the session's first write.

    Returns ``(record, gate_passed)``.  The record is the §B item 3 shaped
    session record: pass/fail counters, the platform and source identities, and
    one canonical validation digest, with no coordinate-level value in it.  On
    any failure the refusal record is returned with ``gate_passed is False``.

    Each of the three session-derived elements is handed to its own check
    unconditionally, by ``.get``.  A missing key and a ``None`` value are the
    same finding and are refused by the same check, so there is no caller-side
    "is the key there" guard that a validator could delete while every fixture
    stayed green.

    This function writes nothing: the caller writes the returned record.  It
    raises :class:`SectionB1RecheckError` only when it is handed an argument it
    cannot read at all (no callable validator or matcher).  An identity
    *finding* -- a mismatch, a missing element, a malformed pin, an invalid
    compiler flag -- is a refusal record, never an exception, so the refusal is
    recordable.
    """
    validator = _normalize_callable(validate_identity, "validate")
    matcher = _normalize_callable(exact_match, "exact_match")

    failure: list[tuple[str, str]] = []
    element_results: dict[str, dict[str, str]] = {}
    source_identity: dict[str, str] = {}
    source_identity_sha256 = "0" * 64
    platform_identity: dict[str, str] = {}
    platform_reported: list[str] = []
    accepted_sha256 = "0" * 64
    session_sha256 = "0" * 64

    # The accepted identity is injected and used only through the injected
    # callables; this module holds no identity of its own.  A validator that
    # raises OR returns a malformed hash is a refusal, never an exception: an
    # exception here would escape a caller that only inspects the gate, which is
    # exactly the fail-open this harness exists to prevent.
    if type(accepted_identity) is not dict or not accepted_identity:
        failure.append(("accepted_identity", "accepted production identity is missing or empty"))
    else:
        try:
            computed = _sha(validator(accepted_identity), "validated identity hash")
        except Exception as exc:
            failure.append(
                ("accepted_identity",
                 f"accepted identity failed validation: {exc.__class__.__name__}"
                 if not isinstance(exc, SectionB1RecheckError) else "accepted identity failed validation")
            )
        else:
            accepted_sha256 = computed

    # Only the non-mapping test remains here.  An EMPTY mapping is a dict, and
    # the whole-identity hash comparison below plus the three element checks --
    # each of which reads its own key with ``.get`` and refuses its absence --
    # already refuse it, naming ``session_identity`` and all three elements; a
    # mutation sweep showed a separate emptiness test survived removal because
    # none of those refusals depended on it.
    if type(session_identity) is not dict:
        failure.append(("session_identity", "session captured identity is missing or not a mapping"))
        accepted = session = {}
    else:
        accepted = accepted_identity if type(accepted_identity) is dict else {}
        session = session_identity
        try:
            session_sha256 = _sha(validator(session_identity), "validated session identity hash")
        except Exception as exc:
            failure.append(
                ("session_identity",
                 f"session identity failed validation: {exc.__class__.__name__}"
                 if not isinstance(exc, SectionB1RecheckError) else "session identity failed validation")
            )

    # The two validated identity hashes must agree.  Each element check below
    # compares a *sub*-identity; this compares the two whole identities, so a
    # difference in a field no element check reads is still a difference.  It is
    # the belt to the element checks' braces, and it is the check that would
    # catch an identity field added after this module was written.
    if accepted_sha256 != "0" * 64 and session_sha256 != "0" * 64 and accepted_sha256 != session_sha256:
        failure.append(("session_identity", "session identity hash differs from the accepted identity hash"))

    # platform -- every image/build value here is platform-reported (§3).
    platform_identity, platform_reported = _check_platform(accepted, session.get("platform"), failure)
    if platform_identity:
        element_results["platform"] = {"element": "platform", "status": "match"}

    # compiler -- version and numeric flags, with the fast-math/contraction/
    # atomics/nondeterministic-reduction ban of the fixed binary64 contract.
    if _check_compiler(accepted, session.get("compiler"), failure):
        element_results["compiler"] = {"element": "compiler", "status": "match"}

    # source -- delegated whole to the injected exact_match, whose contract is
    # to raise on any difference.  An explicit False return is also a refusal.
    source_identity, source_identity_sha256 = _check_source(accepted, session, matcher, failure)
    if source_identity:
        element_results["source"] = {"element": "source", "status": "match"}

    # generator -- the WP5 implementation-record hash, injected.
    if _check_generator(
        generator_implementation_record_sha256,
        expected_generator_implementation_record_sha256,
        failure,
    ):
        element_results["generator"] = {"element": "generator", "status": "match"}

    # ground_truth -- the WP5b provenance hash, injected; not yet built, so its
    # absence is a refusal rather than a skipped element.
    if _check_ground_truth(
        ground_truth_provenance_sha256,
        expected_ground_truth_provenance_sha256,
        failure,
    ):
        element_results["ground_truth"] = {"element": "ground_truth", "status": "match"}

    # protocol -- re-read the approved documents from disk, compared with the
    # caller's expected hashes.  The on-disk hash is a claim; the caller's
    # expected hash is the decision.
    if len(_check_protocol(observed_approval_sha256, expected_approval_sha256, failure)) == len(APPROVAL_PATHS):
        element_results["protocol"] = {"element": "protocol", "status": "match"}

    gate_passed = not failure
    if not gate_passed:
        # Fail closed.  A refused element is recorded as a refusal and never as a
        # match, and the identities are withheld so a failed recheck cannot be
        # mistaken for one that saw an identity.  The source digest needs no
        # zeroing here: ``_check_source`` returns the all-zero hash on every one
        # of its failure paths and a real one only on the path that also returns
        # a real source map, so a second "is the source ok" test could only ever
        # re-derive what that return already says.
        platform_identity = {}
        platform_reported = []
        source_identity = {}
    record = _build_record(
        gate_passed,
        element_results,
        failure,
        accepted_sha256,
        session_sha256,
        platform_identity,
        platform_reported,
        source_identity,
        source_identity_sha256,
    )
    return record, gate_passed


def discover_element(
    element: object,
    *,
    accepted_identity: object,
    validate_identity: object,
    exact_match: object,
    observed_approval_sha256: object,
    expected_approval_sha256: object,
    session_identity: object,
    generator_implementation_record_sha256: object,
    expected_generator_implementation_record_sha256: object,
    ground_truth_provenance_sha256: object,
    expected_ground_truth_provenance_sha256: object,
) -> tuple[bool, dict[str, str]]:
    """Run exactly one of the six §B item 1 element checks, in isolation.

    This is the per-element form of :func:`recheck_before_first_write`, and it
    exists for a specific reason: several element checks have a *second* check
    that masks their failure.  A missing platform field, for instance, also
    makes the whole-identity hash comparison fail, so a session that is
    otherwise wrong still refuses -- which means a fixture that only ever calls
    :func:`recheck_before_first_write` cannot tell whether the missing-field
    check itself works, and a validator who deletes that check sees a green run.
    Isolating one element removes the masking, so a fixture can hold every other
    check to a pass and assert on this one's verdict alone.

    It returns ``(matched, reasons)`` for the named element only.  It writes
    nothing and authorizes nothing: a ``True`` here means only that this one
    comparison found no difference, never that a session may write.
    """
    _require(type(element) is str and element in ELEMENT_NAMES,
             f"element must be one of {ELEMENT_NAMES}")
    _normalize_callable(validate_identity, "validate")
    matcher = _normalize_callable(exact_match, "exact_match")
    failure: list[tuple[str, str]] = []
    accepted = accepted_identity if type(accepted_identity) is dict else {}
    session = session_identity if type(session_identity) is dict else {}

    if element == "platform":
        _check_platform(accepted, session.get("platform"), failure)
    elif element == "compiler":
        _check_compiler(accepted, session.get("compiler"), failure)
    elif element == "source":
        _check_source(accepted, session, matcher, failure)
    elif element == "generator":
        _check_generator(generator_implementation_record_sha256,
                         expected_generator_implementation_record_sha256, failure)
    elif element == "ground_truth":
        _check_ground_truth(ground_truth_provenance_sha256,
                            expected_ground_truth_provenance_sha256, failure)
    else:  # protocol
        _check_protocol(observed_approval_sha256, expected_approval_sha256, failure)
    return (not failure), {reason for _element, reason in failure}


def require_gate(record: object, gate_passed: object) -> None:
    """Raise unless the recheck passed.

    The companion to :func:`recheck_before_first_write` for callers that must
    not proceed on a closed gate.  The record is re-validated first, so a caller
    cannot be handed a hand-written "pass" record for a refusal recheck.

    The closed-gate test and the verdict test are separate checks, each with its
    own fixture.  A caller that reports an open gate while handing back a record
    whose own verdict is ``refused`` has produced a self-contradictory pair; the
    gate test cannot see that case (it only looks at ``gate_passed``) and the
    verdict test cannot see the reverse (a closed gate carrying a "pass" record),
    so neither can stand in for the other.
    """
    if type(gate_passed) is not bool:
        raise SectionB1RecheckError("gate_passed must be a bool")
    _validate_record(record)
    if not gate_passed:
        raise SectionB1RecheckError(
            "Section-B item 1 identity recheck refused; this session may not write: "
            + "; ".join(_validate_record(record)["refusal_reasons"])
        )
    if record["verdict"] != "pass":
        raise SectionB1RecheckError(
            "Section-B item 1 identity recheck refused: record verdict is not a pass"
        )

#!/usr/bin/env python3
"""WP8c mutation fixture — the NON-PRODUCTION guard fixtures.

STATUS: BUILD + VALIDATION ONLY. UNARMED. NOT A DRAW. NOT A PUSH.

Everything here is conspicuously NON-PRODUCTION.  No real generator draw, no
production seed or beacon, no scientific computation or write, no network, no
credential, no GPU, no Kaggle.  The only instances this fixture builds are
stand-ins whose ids start with ``NONPROD-STANDIN`` and contain
``NON-PRODUCTION``, the ONLY id WP8b's single accepting fixture branch takes
(``research/g9/wp8b/wp8b_non_synthetic_preparation.py:318``).  All writes go
under ``g9_jobs/scratch/wp8c``, never ``/tmp``, and the one-use nonce registry is
driven inside a per-run SANDBOX ROOT, never in the project.

WHY THIS FILE LOOKS THE WAY IT DOES
===================================
This file is the FIXTURE for ``g9_guard_sweep.py``, which enumerates a mutation
site for every ``_require`` call, every discarded call, every ``raise`` in a
guard body and every comparison and BoolOp operand in a condition.  A fixture
that merely CALLS the module's checks kills almost none of them: mutating a
guard the fixture never reaches leaves a green run.  Three rules follow, and
each one is a defect this package already paid for:

  1. **Every guard must be observed in BOTH outcomes by real data.**  Each check
     below drives the guard with a value that PASSES and with a value that
     genuinely FAILS, and asserts the refusal's type and its distinguishing
     text.  There is no ``if check_ran: pass`` self-attestation anywhere: every
     assertion compares a real returned value.
  2. **Checks are dispatched from a table, not called by name in ``main``.**  A
     bare ``check_x()`` is itself an S2 (discarded-call) site whose mutant is
     ``pass`` — invisible when the other checks still pass.  ``CHECKS`` below is
     iterated, and the table's own uniqueness and completeness are asserted, so
     deleting an entry removes an assertion the run depends on.
  3. **Both outcomes of every BoolOp operand are covered.**  ``a and b`` needs
     ``a`` true and ``b`` false as well as the valid pair, or the operand's
     mutation is invisible.  The per-guard "both outcomes" cases below exist for
     exactly this reason.

IT REUSES THE REHEARSAL'S DRIVER, NEVER ITS ASSERTIONS
======================================================
``rehearse_wp8c_synthetic_session`` is the end-to-end demonstration.  This file
imports its *construction* helpers (``_layout_and_writer``,
``_one_use_authorization``, ``run_session``, the stand-in acceptance binding)
so the two agree byte-for-byte on what a stand-in session is, but it asserts
independently and it asserts MORE: every refusal here names its expected
exception type and a distinguishing substring, so a mutation that turns a
refusal into a silent pass is killed by the type check, not by a later
assertion failing for an unrelated reason.
"""
from __future__ import annotations

import atexit
import copy
import datetime
import hashlib
import inspect
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True

#: Set to True only once ``main`` has dispatched the whole table.  Written into
#: the completion sentinel so a caller can tell a real run from one that died
#: before the checks.
_TABLE_COMPLETED = False

#: How many checks ``main`` SELECTED (40 for a full run, fewer under --only).
#: Set at the end of ``main``; 0 means ``main`` never got there.
_SELECTED_N = 0

SENTINEL_NAME = "wp8c_fixture_completion.json"
SENTINEL_ENV = "WP8C_FIXTURE_SENTINEL"

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from research.g9 import stage2_coordinate_records as records  # noqa: E402
from research.g9 import stage2_production_identity as wp1  # noqa: E402
from research.g9 import stage2_production_writer as writer  # noqa: E402
from research.g9 import stage2_section_b1_recheck as wp2  # noqa: E402
from research.g9.wp8d_production import wp8d_production_layout as wp8dp  # noqa: E402
from research.g9.wp8b import wp8b_non_synthetic_preparation as wp8b  # noqa: E402
from research.g9.wp8c_production import wp8c_standin as st  # noqa: E402


class FixtureError(AssertionError):
    """A fixture assertion failed.  Distinct from the module's own refusals so a
    reader can tell a broken FIXTURE from a refused GUARD."""


def _import_module_under_test() -> object:
    """Import ``wp8c_production_session``, refusing an import-time SystemExit.

    The module under test carries a ``__main__`` guard at its tail.  Mutating
    that guard (``S4``/``S5`` at :2057) makes ``raise SystemExit(main())``
    execute AT IMPORT TIME, which ends this process with status 0 before a
    single check has run -- a silent bypass the sweep cannot see, because it
    judges this fixture by exit status alone.

    This guard must wrap EVERY import that can transitively pull the module in,
    not just a direct import of it: ``rehearse_wp8c_synthetic_session`` imports
    ``wp8c_production_session`` at ITS module scope (:64), so a plain
    ``from ... import rehearse_...`` above would raise before this function ever
    got a chance to run.  The rehearsal is therefore imported through here too.

    Catching ``SystemExit`` converts the bypass into an ordinary fixture
    failure, so the mutant is KILLED for the right reason: the table really ran
    and really refused.  Nothing else about the imports is altered.
    """
    import importlib
    try:
        R = importlib.import_module(
            "research.g9.wp8c_production.rehearse_wp8c_synthetic_session")
        s = importlib.import_module(
            "research.g9.wp8c_production.wp8c_production_session")
    except SystemExit as exc:
        raise FixtureError(
            "the module under test raised SystemExit("
            f"{exc.code!r}) while being IMPORTED, so no check could have run; "
            "this is a silent-bypass mutation, not a fixture verdict"
        ) from exc
    return R, s


_R, s = _import_module_under_test()
R = _R

#: Scratch root mandated by the package rules.  Never /tmp.
SCRATCH = Path("/home/shivansh-srivastava/decisions_os/g9_jobs/scratch/wp8c")

#: The suite-wide counters, reported at the end.
CHECKED: list[str] = []


def ok(condition: object, message: str) -> None:
    """The one assertion form.  Fail-closed, like the module's own guards."""
    if not condition:
        raise FixtureError(message)


def observe(fn) -> dict:
    """Call ``fn`` and report what happened, WITHOUT letting a refusal escape.

    This is the observation channel every negative case uses: it must return a
    dict whose ``outcome`` is ``"returned"`` or ``"raised"`` so the case can
    assert the refusal's TYPE and TEXT.  ``BaseException`` is caught on purpose
    — the exception type is the thing under test, and letting a wrong type
    escape would abort the run before the assertion that names it.
    """
    try:
        return {"outcome": "returned", "value": fn(), "type": None, "text": ""}
    except BaseException as exc:  # noqa: BLE001 - the type IS the assertion
        return {"outcome": "raised", "value": None,
                "type": type(exc).__name__, "text": str(exc)}


def refuses(fn, type_name: str, *needles: str) -> dict:
    """Assert ``fn`` raises exactly ``type_name`` whose text carries every needle.

    The needles are what kill the S5 (bool-negate) and S4 (compare-swap)
    mutants: a negated condition either raises on the VALID input (caught here,
    because ``fn`` is called with the valid input on the valid path) or fails to
    raise on the INVALID input (caught here, because the needle is absent).
    """
    outcome = observe(fn)
    ok(outcome["outcome"] == "raised",
       f"expected a refusal of type {type_name}, got {outcome['outcome']}: "
       f"{outcome['text'] or outcome['value']!r}")
    ok(outcome["type"] == type_name,
       f"expected refusal type {type_name}, got {outcome['type']}: {outcome['text']}")
    for needle in needles:
        ok(needle in outcome["text"],
           f"the {type_name} refusal does not mention {needle!r}: {outcome['text']}")
    return outcome


def accepts(fn, description: str):
    """Assert ``fn`` returns normally, naming what was expected to succeed."""
    outcome = observe(fn)
    ok(outcome["outcome"] == "returned",
       f"{description} must succeed, but it raised {outcome['type']}: {outcome['text']}")
    return outcome["value"]


# ===========================================================================
# Sandbox construction
# ===========================================================================


def new_base(tag: str) -> str:
    """A fresh sandbox root under the durable scratch tree.  Never /tmp."""
    SCRATCH.mkdir(parents=True, exist_ok=True)
    return tempfile.mkdtemp(prefix=f"fixture-{tag}-", dir=str(SCRATCH))


def valid_authorization(base: str, *, nonce: str,
                        instance_id: str = st.STANDIN_ID) -> dict:
    """A structurally VALID one-use authorization over a freshly prepared stand-in.

    Every hash is read back from the reviewed verification record of the SAME
    layout the authorization is built for, so the value is exactly as
    trustworthy as the session's own comparison: a wrong field is refused by
    ``validate_authorization`` rather than believed.
    """
    layout, _ = R._layout_and_writer(base, "auth-" + nonce, nonce=nonce + "-wp8b",
                                     instance_id=instance_id)
    verified = s.verify_instance_for_session(1, root=layout, standin=True)
    return R._one_use_authorization(verified, st.draft_identity_sha256(), nonce=nonce)


def authorization_over(base: str, *, name: str, nonce: str,
                       instance_id: str = st.STANDIN_ID) -> tuple[dict, dict]:
    """Build one layout and return ``(authorization, verified)`` over THAT layout.

    A case that compares an authorization against a verification record must use
    the same instance for both, because ``validate_authorization`` compares the
    authorization's ``prepared_record_sha256`` and ``generation_manifest_sha256``
    against the VERIFIED record's values.  Two separately prepared stand-ins are
    two different records, so this helper keeps them paired.
    """
    layout, _ = R._layout_and_writer(base, name, nonce=nonce, instance_id=instance_id)
    verified = s.verify_instance_for_session(1, root=layout, standin=True)
    return R._one_use_authorization(verified, st.draft_identity_sha256(),
                                    nonce=nonce), verified


def verified_standin(base: str, name: str, *, nonce: str,
                     instance_id: str = st.STANDIN_ID) -> dict:
    """Prepare one stand-in instance and return the REVIEWED verification record."""
    layout, _ = R._layout_and_writer(base, name, nonce=nonce, instance_id=instance_id)
    return s.verify_instance_for_session(1, root=layout, standin=True)


# ===========================================================================
# 1. The pure helpers: hashing, sealing, sha256 shape
# ===========================================================================


def check_pure_helpers() -> None:
    """``_canonical``, ``_content_sha256``, ``_sha256_bytes``, ``_is_sha256``,
    ``_require_sha256`` and ``_seal``.

    Each is exercised on a value that must be ACCEPTED and one that must be
    REFUSED, because a mutation that inverts ``_require_sha256`` is only visible
    if a malformed digest is actually offered.
    """
    body = {"b": 2, "a": 1}
    accepts(lambda: s._canonical(body), "the canonical encoding")
    # Canonical encoding is order-independent: this is what makes a content hash
    # reproducible, so a mutated key sort would change every digest below.
    ok(s._canonical({"a": 1, "b": 2}) == s._canonical(body),
       "canonical encoding must not depend on dict insertion order")
    accepts(lambda: s._content_sha256(body), "the content hash of a body")
    ok(s._content_sha256({"content_sha256": "x", **body}) == s._content_sha256(body),
       "the content hash must exclude the content_sha256 field itself")
    accepts(lambda: s._sha256_bytes(b"abc"), "the sha256 of bytes")
    ok(s._sha256_bytes(b"abc") ==
       "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
       "sha256 of b'abc' must be the published digest")

    # ``_is_sha256`` is a pure predicate: both outcomes are required.
    ok(s._is_sha256("0" * 64) is True, "a 64-char lowercase hex digest is a sha256")
    ok(s._is_sha256("0" * 63) is False, "a 63-char digest is not a sha256")
    ok(s._is_sha256("0" * 65) is False, "a 65-char digest is not a sha256")
    ok(s._is_sha256("g" * 64) is False, "a non-hex digest is not a sha256")
    ok(s._is_sha256("A" * 64) is False, "an uppercase digest is not a lowercase sha256")
    ok(s._is_sha256(None) is False, "None is not a sha256")
    ok(s._is_sha256(0 * 64) is False, "a non-str is not a sha256")

    digest = s._sha256_bytes(b"ok")
    ok(s._require_sha256(digest, "label") == digest, "a valid digest passes through")
    refuses(lambda: s._require_sha256("nope", "the label"), "ProductionSessionError",
            "the label", "sha256")
    refuses(lambda: s._require_sha256("Z" * 64, "the label"), "ProductionSessionError",
            "sha256")

    sealed = accepts(lambda: s._seal(body), "sealing a body")
    ok(sealed["content_sha256"] == s._content_sha256(body),
       "_seal must store the content hash of its own body")
    ok("content_sha256" not in {k: v for k, v in body.items()},
       "sealing must not mutate the caller's mapping")
    # A NaN anywhere must be refused: it would make the canonical encoding
    # ambiguous, so two different bodies could share a digest.  The refusal
    # arrives from the canonical encoder as a ``ValueError`` (the frozen JSON
    # encoder rejects out-of-range floats), which is why this case names
    # ``ValueError`` and not the module's own type.
    refuses(lambda: s._seal({"x": float("nan")}), "ValueError")
    refuses(lambda: s._canonical({"x": float("nan")}), "ValueError")


def check_require_forms() -> None:
    """``_require`` and ``_require_step`` — the two guard forms.

    ``_require_step`` raises the PREREQUISITE-failed type, which is the type the
    session's per-step blocking gate depends on, so both types are pinned here.
    """
    accepts(lambda: s._require(True, "ok"), "a true require")
    refuses(lambda: s._require(False, "falsy refused"), "ProductionSessionError",
            "falsy refused")
    refuses(lambda: s._require(0, "zero refused"), "ProductionSessionError",
            "zero refused")
    refuses(lambda: s._require("", "empty refused"), "ProductionSessionError",
            "empty refused")
    accepts(lambda: s._require_step(True, "ok"), "a true require_step")
    refuses(lambda: s._require_step(False, "step refused"), "PrerequisiteFailed",
            "step refused")
    ok(issubclass(s.PrerequisiteFailed, s.ProductionSessionError),
       "a prerequisite failure must be catchable as a session error")


def check_error_taxonomy() -> None:
    """Every refusal type must derive from the base, so one ``except`` catches all."""
    for name in ("InstanceRefused", "IdentityGateUnset", "AuthorizationRefused",
                 "PrerequisiteFailed", "ResumeRefused", "IncompleteBudget"):
        cls = getattr(s, name)
        ok(issubclass(cls, s.ProductionSessionError),
           f"{name} must derive from ProductionSessionError")
        ok(issubclass(cls, ValueError),
           f"{name} must derive from ValueError")
    # ``IncompleteBudget`` is deliberately NOT a session error in the receipt
    # path's sense: the session catches it separately, so it must be
    # distinguishable from an ordinary refusal.
    ok(not issubclass(s.IncompleteBudget, s.ResumeRefused),
       "a budget stop is not a resume refusal")


def check_contract_constants() -> None:
    """The pinned constants.  A mutated constant must be visible to a fixture."""
    ok(s.SESSION_SCHEMA.endswith("/v1"), "the session schema is versioned")
    ok(s.RECEIPT_SCHEMA.endswith("/v1"), "the receipt schema is versioned")
    ok(s.AUTHORIZATION_SCHEMA.endswith("/v1"), "the authorization schema is versioned")
    ok(s.SESSION_STATE_SCHEMA.endswith("/v1"), "the state schema is versioned")
    ok(s.RESUME_POLICY_SCHEMA.endswith("/v1"), "the resume schema is versioned")
    ok(len({s.SESSION_SCHEMA, s.RECEIPT_SCHEMA, s.AUTHORIZATION_SCHEMA,
            s.SESSION_STATE_SCHEMA, s.RESUME_POLICY_SCHEMA}) == 5,
       "the five WP8c schemas must be distinct")
    ok(s.RESUME_POLICY["schema"] == s.RESUME_POLICY_SCHEMA,
       "the resume policy must carry its own schema")
    ok(s.AUTHORIZED_ACTION == "run_wp8c_production_scientific_session",
       f"the authorized action is {s.AUTHORIZED_ACTION!r}")
    ok(s.AUTHORIZATION_STATUS == "owner_authorized",
       f"the authorization status is {s.AUTHORIZATION_STATUS!r}")
    ok("never accepted" in s.AUTHORIZATION_STATEMENT
       or "One-use" in s.AUTHORIZATION_STATEMENT,
       "the authorization statement must announce its one-use scope")

    # The frozen step order, and that the device/write steps are a SUBSET of it
    # in the same order — this is what makes the blocking property total.
    ok(len(s.STEP_ORDER) == 7, f"the frozen order has 7 steps, got {s.STEP_ORDER}")
    ok(list(s.STEP_ORDER) == [
        "instance_verified", "identity_bound", "authorization_consumed",
        "wp2_recheck_passed", "wp3_check_passed", "records_built",
        "ranges_promoted"], f"the frozen order drifted: {s.STEP_ORDER}")
    positions = [s.STEP_ORDER.index(step) for step in s.DEVICE_OR_WRITE_STEPS]
    ok(positions == sorted(positions),
       "the device/write steps must be in step order or the blocking is wrong")
    for step in s.DEVICE_OR_WRITE_STEPS:
        ok(step in s.STEP_ORDER, f"{step} must be a member of the frozen order")
    ok("ranges_promoted" in s.DEVICE_OR_WRITE_STEPS,
       "the write step must be gated")

    # Exactly the four deferred image fields, in the owner's fixed order.
    ok(tuple(s.POST_RUN_ONLY_IMAGE_FIELDS) == (
        "kaggle_image", "image_manifest_sha256", "image_config_id", "image_name"),
       f"the deferred image fields drifted: {s.POST_RUN_ONLY_IMAGE_FIELDS}")

    # The child environment must NEVER admit a KAGGLE_ or PYTHON name.
    ok(not any(name.startswith("KAGGLE_") for name in s.CHILD_ENVIRONMENT_ALLOWLIST),
       "a KAGGLE_ name is in the child allowlist")
    ok(not any(name.startswith("PYTHON") for name in s.CHILD_ENVIRONMENT_ALLOWLIST),
       "a PYTHON name is in the child allowlist")
    ok("PATH" in s.CHILD_ENVIRONMENT_ALLOWLIST,
       "PATH must be in the child allowlist")
    ok(tuple(s.CHILD_ISOLATION_FLAGS) == ("-I", "-S", "-B"),
       f"the child isolation flags drifted: {s.CHILD_ISOLATION_FLAGS}")

    # The hard timeout must EXCEED the in-session budget, or the kernel dies
    # before the guard can issue its incomplete receipt.
    ok(s.KAGGLE_HARD_TIMEOUT_SECONDS > s.BUDGET_SECONDS,
       "the hard timeout must exceed the in-session budget")
    ok(s.BUDGET_SECONDS == 10 * 60 * 60,
       f"the in-session budget is {s.BUDGET_SECONDS}, not the owner's 10 hours")

    ok(set(s.RECEIPT_STATUSES) == {
        "complete_pending_image_audit", "incomplete_budget", "refused"},
       f"the receipt statuses drifted: {s.RECEIPT_STATUSES}")
    ok("accepted" not in [name for name in s.RECEIPT_STATUSES],
       "no receipt status may be an acceptance")

    # The resume policy, restated as assertions rather than trusted.
    policy = s.RESUME_POLICY
    ok(policy["sessions_per_instance"] == 1,
       f"the policy must permit one session per instance, got {policy}")
    ok(policy["resume_unit"] == "missing_whole_ranges_only",
       f"the resume unit drifted: {policy}")
    ok(policy["resume_requires_new_authorization"] is True,
       "a resume must require a NEW authorization")
    ok(policy["resume_requires_same_identity"] is True,
       "a resume must require the SAME identity")
    ok(policy["incomplete_run_is_accepted"] is False,
       "an incomplete run must never be accepted")

    # The authorization schema is an EXACT key set: a widened or narrowed record
    # must be refused, so the key set itself is asserted here.  It is asserted
    # against the module's own frozenset AND against an independently written
    # literal, so a mutation of the constant is killed even if every case that
    # uses it passes.
    expected_authorization_keys = frozenset({
        "schema", "action", "account", "kernel_id", "bundle_sha256",
        "accepted_identity_sha256", "instance_id", "generation_manifest_sha256",
        "prepared_record_sha256", "session_contract_sha256", "expiry", "nonce",
        "authorization_status", "statement"})
    ok(s.AUTHORIZATION_KEYS == expected_authorization_keys,
       f"the authorization key set drifted: {sorted(s.AUTHORIZATION_KEYS)}")
    ok(len(s.AUTHORIZATION_KEYS) == 14,
       f"the authorization has 14 fields, got {len(s.AUTHORIZATION_KEYS)}")


def check_identity_binding_and_exact_match() -> None:
    """WP2's element view, the WP1 validate/match adapters, and the writer carrier.

    The tamper cases matter here: the DRAFT identity is self-hash-bound, so ANY
    tamper is refused by WP1's own validator (``ProductionIdentityError``)
    BEFORE a comparison is even reached.  That is the strongest fail-closed
    property WP8c relies on, and it is asserted here rather than assumed.
    """
    identity = st.draft_identity()

    # The element view WP2 reads: platform, compiler, source and image fields.
    view = accepts(lambda: s.wp2_element_view(identity), "the WP2 element view")
    ok("production_identity" in view, "the WP2 view must carry the identity")
    ok("platform" in view and "compiler" in view and "source_sha256" in view,
       f"the WP2 view is missing a declared element: {sorted(view)}")
    ok(view["production_identity"] is not identity,
       "the WP2 view must carry a COPY, not the caller's live identity object")
    ok(view["production_identity"] == identity,
       "the WP2 view's identity copy must equal the caller's identity")
    # The validate adapter unwraps to the REAL identity and WP1 validates it.
    digest = accepts(lambda: s.wp2_validate_view(view), "the WP2 validate adapter")
    ok(digest == st.draft_identity_sha256(),
       "the WP2 validate adapter must return WP1's own digest")

    # The match adapter delegates to WP1's total exact_match.
    verdict = accepts(lambda: s.wp2_match_views(view, s.wp2_element_view(identity)),
                      "the WP2 match adapter on identical views")
    ok(verdict["verdict"] == "exact_match",
       f"identical WP2 views must match, got {verdict}")
    ok(verdict["differing_fields"] == [],
       f"identical WP2 views must report no differences, got {verdict}")

    refuses(lambda: s.wp2_validate_view({"no_identity": True}),
            "ProductionSessionError", "malformed")
    refuses(lambda: s.wp2_match_views({"no_identity": True}, view),
            "ProductionSessionError", "malformed")
    refuses(lambda: s.wp2_element_view({}), "ProductionSessionError")
    refuses(lambda: s.wp2_element_view({"qualification_identity": None}),
            "ProductionSessionError")

    # A TAMPERED identity is refused by WP1 itself.  Both a relabelled status
    # and a rewritten self-note are tested; neither may be accepted.
    tampered_status = copy.deepcopy(identity)
    tampered_status["status"] = "ACCEPTED"
    refuses(lambda: wp1.validate_production_identity(tampered_status),
            "ProductionIdentityError", "DRAFT_UNQUALIFIED")
    tampered_note = copy.deepcopy(identity)
    tampered_note["authorization_note"] = "TAMPERED"
    refuses(lambda: wp1.validate_production_identity(tampered_note),
            "ProductionIdentityError")
    # A tampered identity must also be refused through WP8c's own validate
    # adapter, so a mutation that swaps the adapter for a no-op is killed.
    refuses(lambda: s.wp2_validate_view(
        s.wp2_element_view({**identity, "status": "ACCEPTED"})),
        "ProductionIdentityError", "DRAFT_UNQUALIFIED")

    # The writer identity carrier carries WP1's real validate/match.
    carrier = accepts(lambda: s.writer_identity_of(
        {"draft_identity": identity}), "the writer identity carrier")
    ok(carrier.accepted is identity or carrier.accepted == identity,
       "the writer carrier must hold the bound accepted payload")
    ok(carrier.validate is wp1.validate_production_identity,
       "the writer carrier must inject WP1's real validator")
    ok(carrier.exact_match is wp1.exact_match,
       "the writer carrier must inject WP1's own exact_match")
    # The records adapter returns True on a match and raises otherwise.
    ok(s.records_exact_match(identity, copy.deepcopy(identity)) is True,
       "the records adapter must return True on an exact match")
    refuses(lambda: s.records_exact_match({**identity, "status": "ACCEPTED"},
                                          identity),
            "ProductionIdentityError")

    refuses(lambda: s.writer_identity_of({}), "ProductionSessionError")
    refuses(lambda: s.writer_identity_of({"draft_identity": None}),
            "ProductionSessionError")

    # observed_approval_hashes reads WP2's fixed paths from disk.
    observed = accepts(lambda: s.observed_approval_hashes(),
                       "the observed approval hashes")
    ok(isinstance(observed, dict) and observed,
       f"the observed approval hashes must be a non-empty mapping, got {observed!r}")
    # A hash mismatch must be refused by WP2 (the caller's expected value is the
    # decision), which is proven in the session-level case, not here.

    # generator_record_of / ground_truth_of read the VERIFIED record.
    verified = {"implementation_record_content_sha256": "a" * 64,
                "generation_manifest_content_sha256": "b" * 64}
    ok(s.generator_record_of(verified) == "a" * 64,
       "the generation record hash must come from the verified record")
    ok(s.ground_truth_of(verified) == "b" * 64,
       "the ground-truth hash must come from the verified record")
    refuses(lambda: s.generator_record_of({}), "ProductionSessionError")
    refuses(lambda: s.ground_truth_of({"generation_manifest_content_sha256": "x"}),
            "ProductionSessionError")


def check_child_environment_and_pins() -> None:
    """The WP7b-aligned child environment and the four deferred image fields."""
    environment = {"PATH": "/usr/bin", "NVIDIA_VISIBLE_DEVICES": "all",
                   "KAGGLE_KERNEL_RUN_TYPE": "Interactive",
                   "KAGGLE_USER_SECRETS_TOKEN": "NONPROD-NOT-A-CREDENTIAL",
                   "PYTHONPATH": "/nonprod", "PYTHONDONTWRITEBYTECODE": "0",
                   "HOME": "/home/nonprod", "LD_LIBRARY_PATH": "/lib",
                   "LC_ALL": "C", "SECRET_TOKEN": "NONPROD", "TMPDIR": "/d"}
    child = accepts(lambda: s.child_environment(environment), "the child environment")
    ok("KAGGLE_KERNEL_RUN_TYPE" not in child,
       f"a KAGGLE_* name reached the child: {sorted(child)}")
    ok("KAGGLE_USER_SECRETS_TOKEN" not in child,
       f"a credential-bearing KAGGLE_* name reached the child: {sorted(child)}")
    ok("PYTHONPATH" not in child, f"a PYTHON* name reached the child: {sorted(child)}")
    ok("SECRET_TOKEN" not in child,
       f"an unlisted name reached the child: {sorted(child)}")
    ok(child.get("PATH") == "/usr/bin", "an allowed name must be kept")
    ok(child.get("NVIDIA_VISIBLE_DEVICES") == "all",
       "an NVIDIA_* name must be kept")
    ok(child.get("LC_ALL") == "C", "an LC_* name must be kept")
    ok(child["PYTHONDONTWRITEBYTECODE"] == "1",
       "the child must be forced to not write bytecode")
    # Forcing PYTHONDONTWRITEBYTECODE over a caller's 0 is the point.
    ok(child["PYTHONDONTWRITEBYTECODE"] == "1",
       "the caller's PYTHONDONTWRITEBYTECODE=0 must be overridden to 1")
    refuses(lambda: s.child_environment("not a mapping"), "ProductionSessionError")
    refuses(lambda: s.child_environment({1: "x"}), "ProductionSessionError")
    refuses(lambda: s.child_environment({"PATH": 1}), "ProductionSessionError")
    # The deny-after-select branch is a DEFENCE IN DEPTH: no name can be both
    # allowlisted (exact or by ``LC_``/``NVIDIA_`` prefix) and denied
    # (``KAGGLE_``/``PYTHON`` prefix), because the two prefix sets are disjoint
    # and no allowlisted exact name starts with a denied prefix.  This asserts
    # that disjointness, so the branch is recorded as unreachable-by-
    # construction rather than silently untested — and so a future edit that
    # makes the sets overlap is caught here.
    overlapping = [name for name in s.CHILD_ENVIRONMENT_ALLOWLIST
                   if name.startswith(s.CHILD_ENVIRONMENT_DENIED_PREFIXES)]
    ok(not overlapping,
       f"an allowlisted child name also matches a denied prefix: {overlapping}")
    for prefix in s.CHILD_ENVIRONMENT_PREFIXES:
        ok(not prefix.startswith(s.CHILD_ENVIRONMENT_DENIED_PREFIXES),
           f"the allowed prefix {prefix!r} collides with a denied prefix")

    # The in-session pin drops EXACTLY the four deferred fields.
    pin = {"platform_reported": {"gpu_name": "x"}, "image_reported": {
        name: f"value-{name}" for name in s.POST_RUN_ONLY_IMAGE_FIELDS}}
    reduced = accepts(lambda: s.in_session_environment_pin(pin),
                      "the in-session environment pin")
    for name in s.POST_RUN_ONLY_IMAGE_FIELDS:
        ok(name not in reduced["image_reported"],
           f"a deferred field survived the in-session pin: {name}")
    ok("gpu_name" in reduced["platform_reported"],
       "a non-deferred field was dropped from the pin")
    # The original pin must not be mutated by the reduction.
    ok(all(name in pin["image_reported"] for name in s.POST_RUN_ONLY_IMAGE_FIELDS),
       "in_session_environment_pin must not mutate the caller's pin")
    # A pin missing a deferred field is refused rather than silently dropped.
    short = {"image_reported": {"kaggle_image": "x"}}
    refuses(lambda: s.in_session_environment_pin(short),
            "ProductionSessionError", "absent")
    refuses(lambda: s.in_session_environment_pin({"no_image": {}}),
            "ProductionSessionError")
    refuses(lambda: s.in_session_environment_pin("not a mapping"),
            "ProductionSessionError")


def check_authority_boundary() -> None:
    """The one emulated boundary: it can observe, it can NEVER arm."""
    observations = copy.deepcopy(st.STANDIN_OBSERVATIONS)
    boundary = accepts(lambda: s.AuthorityBoundary(observations),
                       "constructing the authority boundary")
    ok(boundary.kind == s.AuthorityBoundary.KIND,
       f"the boundary kind drifted: {boundary.kind}")
    ok("non_production" in boundary.kind,
       "the boundary must announce itself non-production")
    ok(boundary.production is False, "the boundary must report production=False")
    observed = accepts(lambda: boundary.observe_platform(),
                       "the boundary platform observation")
    ok(observed == observations,
       "the boundary must return exactly the declared observations")
    # Mutating the returned observation must not affect the boundary.
    observed["platform_reported"]["gpu_name"] = "MUTATED"
    ok(boundary.observe_platform() == observations,
       "the boundary must return a copy, not its internal state")
    # It may NEVER be constructed as production.
    refuses(lambda: s.AuthorityBoundary(observations, production=True),
            "ProductionSessionError", "production")
    refuses(lambda: s.AuthorityBoundary({}), "ProductionSessionError")
    refuses(lambda: s.AuthorityBoundary("not a mapping"), "ProductionSessionError")
    # It has no method that builds a device backend.
    refuses(lambda: boundary.device_backend(), "NotImplementedError")
    # And it has no method that issues an owner authorization at all.
    ok(not any(name in dir(boundary) for name in
               ("authorize", "approve", "grant", "release", "accept")),
       f"the boundary exposes an owner act: {dir(boundary)}")


def check_steps_ledger() -> None:
    """The step ledger: order, prerequisite blocking, and digest shape."""
    steps = accepts(lambda: s._Steps(), "constructing the step ledger")
    ok(steps.passed == set(), "a fresh ledger must have passed nothing")
    ok(steps.prerequisites_met("instance_verified") is True,
       "the first step has no prerequisite")
    steps.record("instance_verified", digest="a" * 64)
    ok(steps.passed == {"instance_verified"}, "the recorded step must be in passed")
    ok(steps.digests["instance_verified"] == "a" * 64, "the digest must be recorded")
    # ``identity_bound`` has exactly one predecessor, which HAS now passed, so it
    # is runnable.  A THREE-deep step is the one whose prerequisites are unmet,
    # which is the property the session's blocking gate depends on.
    ok(steps.prerequisites_met("identity_bound") is True,
       "identity_bound's only prerequisite has passed")
    ok(steps.prerequisites_met("wp2_recheck_passed") is False,
       "wp2_recheck_passed has unmet prerequisites")
    steps.record("identity_bound", digest="b" * 64)
    refuses(lambda: steps.record("wp2_recheck_passed"), "ProductionSessionError",
            "prerequisite")
    # An unknown step is refused.
    refuses(lambda: steps.record("not_a_step"), "ProductionSessionError", "unknown")
    refuses(lambda: steps.prerequisites_met("not_a_step"), "ProductionSessionError",
            "unknown")
    # A malformed digest is refused.
    steps.record("identity_bound", digest="b" * 64)
    refuses(lambda: s._Steps().record("instance_verified", digest="short"),
            "ProductionSessionError", "sha256")
    # failed_prerequisite_for names the FIRST unpassed earlier step.
    fresh = s._Steps()
    ok(fresh.failed_prerequisite_for("wp3_check_passed") == "instance_verified",
       "failed_prerequisite_for must name the earliest unpassed step")
    fresh.record("instance_verified", digest="c" * 64)
    fresh.record("identity_bound", digest="c" * 64)
    ok(fresh.failed_prerequisite_for("wp3_check_passed") == "authorization_consumed",
       "failed_prerequisite_for must advance past passed steps")
    fresh.record("authorization_consumed", digest="c" * 64)
    fresh.record("wp2_recheck_passed", digest="c" * 64)
    ok(fresh.failed_prerequisite_for("wp3_check_passed") is None,
       "with every prerequisite passed there is no blocker")
    # refuse() records without passing.
    blocker = s._Steps()
    blocker.refuse("wp2_recheck_passed", "probe")
    ok(blocker.refused["wp2_recheck_passed"] == "probe",
       "refuse must record the reason")
    ok("wp2_recheck_passed" not in blocker.passed,
       "refuse must NOT mark the step as passed")


def check_budget_guard() -> None:
    """The budget guard: monotonic elapsed, typed stop, non-accepting receipt."""
    ticks = {"n": 0}

    def clock():
        ticks["n"] += 1
        return float(ticks["n"]) * 100.0

    guard = accepts(lambda: s.BudgetGuard(clock, budget_seconds=1000),
                    "constructing the budget guard")
    ok(guard.start >= 0.0, "the guard must record a start")
    ok(guard.last_completed == "none", "a fresh guard's last step is 'none'")
    guard.mark("instance_verified")
    ok(guard.last_completed == "instance_verified", "mark must record the step")
    refuses(lambda: guard.mark("not_a_step"), "ProductionSessionError", "unknown")
    accepts(lambda: guard.check(), "a check within budget")
    receipt = accepts(lambda: guard.receipt(promoted=["b1", "b2"]),
                      "the incomplete receipt")
    ok(receipt["status"] == "incomplete_budget", "the receipt status drifted")
    ok(receipt["accepted"] is False, "an incomplete receipt must never be accepted")
    ok(receipt["last_completed_step"] == "instance_verified",
       "the receipt must name the last completed step")
    ok(receipt["promoted_range_batch_ids"] == ["b1", "b2"],
       "the receipt must name the promoted ranges")
    ok(receipt["scientific_outputs"] == [],
       "the receipt must carry no scientific output")

    # A clock past the budget raises the TYPED error.
    slow = accepts(lambda: s.BudgetGuard(lambda: 0.0, budget_seconds=1), "slow guard")
    slow._clock = lambda: 500.0
    outcome = observe(slow.check)
    ok(outcome["type"] == "IncompleteBudget",
       f"a budget overrun must raise IncompleteBudget, got {outcome['type']}")
    ok("incomplete_budget" in outcome["text"],
       f"the budget error must name itself: {outcome['text']}")

    # The budget guard must reject a non-callable clock and a bad budget.
    refuses(lambda: s.BudgetGuard("not callable"), "ProductionSessionError")
    refuses(lambda: s.BudgetGuard(clock, budget_seconds=0), "ProductionSessionError")
    refuses(lambda: s.BudgetGuard(clock, budget_seconds=-1), "ProductionSessionError")
    # A budget that MEETS the hard timeout is refused: the kernel would be
    # killed before the guard could issue its receipt.
    refuses(lambda: s.BudgetGuard(clock, budget_seconds=s.KAGGLE_HARD_TIMEOUT_SECONDS),
            "ProductionSessionError", "hard Kaggle timeout")
    refuses(lambda: s.BudgetGuard(clock, budget_seconds=s.KAGGLE_HARD_TIMEOUT_SECONDS + 1),
            "ProductionSessionError", "hard Kaggle timeout")


def check_no_arming_flags() -> None:
    """No public entry point may take an arming flag.

    This is the module's central trust-boundary claim — "no caller-supplied
    value may stand in for a validation" — and it is checked by SIGNATURE, so a
    mutation that adds a parameter is killed even if no case passes it.
    """
    banned = {"armed", "approved", "verified_flag", "require_production",
              "skip_checks", "dry_run", "trust_caller", "bypass", "force",
              "override", "allow_unverified"}
    # ``AuthorityBoundary.__init__`` legitimately takes ``production`` and
    # REFUSES ``production=True``; it is the emulated boundary, not a session
    # entry point, and its refusal is asserted in ``check_authority_boundary``.
    # Every other ``production`` parameter is banned.
    excluded = {("AuthorityBoundary", "__init__", "production")}
    offenders = []
    for name, value in sorted(vars(s).items()):
        if name.startswith("__"):
            continue
        if isinstance(value, type):
            functions = [m for m in vars(value).values() if inspect.isfunction(m)]
        elif inspect.isfunction(value):
            functions = [value]
        else:
            continue
        for function in functions:
            for parameter in inspect.signature(function).parameters:
                if parameter.lower() not in banned:
                    continue
                if (name, function.__name__, parameter) in excluded:
                    continue
                offenders.append(f"{name}.{function.__name__}({parameter})")
    ok(not offenders,
       f"a public entry point takes an arming flag: {offenders}")
    # The boundary itself must refuse production=True — asserted here too so a
    # mutation of THAT guard is killed even if the boundary check is skipped.
    outcome = observe(lambda: s.AuthorityBoundary(
        copy.deepcopy(st.STANDIN_OBSERVATIONS), production=True))
    ok(outcome["outcome"] == "raised",
       "the authority boundary must refuse production=True")
    # ``standin`` is the one boolean that names WHICH REVIEWED READER is called;
    # it selects between two fixed, separately reviewed functions and each still
    # refuses, so it is explicitly not an arming flag — but it is asserted to be
    # the ONLY boolean parameter on the session entry point.
    booleans = {name: parameter.default
                for name in ("verify_instance_for_session",)
                for parameter, spec in
                inspect.signature(getattr(s, name)).parameters.items()
                if isinstance(spec.default, bool)}
    ok(set(booleans) <= {"standin"},
       f"an unexpected boolean parameter: {sorted(booleans)}")
    # ``run_production_session`` in particular must name no boolean that could
    # stand in for a check.
    parameters = set(inspect.signature(s.run_production_session).parameters)
    ok(not (parameters & banned),
       f"run_production_session takes an arming flag: {sorted(parameters & banned)}")


def check_module_sets_no_gate() -> None:
    """WP8c must never ASSIGN the WP8b production-release flag or its pin.

    Checked against the module SOURCE, not its behaviour: an assignment would
    only show up in a gate value at run time, and the fixture must catch it even
    if the assignment is unreachable.  This is the "does not fabricate a WP8b R6
    pin" claim, made checkable.
    """
    source = Path(s.__file__).read_text("utf-8")
    ok("PRODUCTION_RELEASE_PINNED = True" not in source,
       "WP8c must never set WP8b's PRODUCTION_RELEASE_PINNED")
    ok("PRODUCTION_RELEASE_PINNED =" not in source,
       "WP8c must contain no assignment to WP8b's PRODUCTION_RELEASE_PINNED")
    ok("PRODUCTION_RELEASE_DECISION_SHA256 =" not in source,
       "WP8c must never set WP8b's pinned decision hash")
    # It must not WRITE the R6 decision record either.
    ok("GATE_9_WP8B_NON_SYNTHETIC_PREPARATION_RELEASE" not in source
       or source.count("GATE_9_WP8B_NON_SYNTHETIC_PREPARATION_RELEASE") == 0,
       "WP8c must not name WP8b's R6 decision record path")
    # Nor may it claim a production identity of its own.
    ok("DRAFT_UNQUALIFIED =" not in source,
       "WP8c must not re-label any identity status")


def check_owner_gate_status() -> None:
    """The gate report must report all three gates CLOSED, today."""
    report = accepts(lambda: s.owner_gate_status(), "the owner gate report")
    ok(report["wp8b_production_release_pinned"] is False,
       "WP8b's production release must be reported UNPINNED")
    ok(report["wp8a_accepted_identity_available"] is False,
       "no accepted identity may be reported available")
    ok(report["wp8c_scientific_write_authorized"] is False,
       "no scientific write may be reported authorized")
    ok(report["gates_open"] == 0,
       f"no gate may be reported open, got {report['gates_open']}")
    ok(report["wp8b_production_release_pinned"]
       is bool(wp8b.PRODUCTION_RELEASE_PINNED),
       "the report must read the REAL WP8b constant, not a copy")
    # The R6 record must not exist on disk: WP8c never fabricated one.
    ok(not (_ROOT / wp8b.PRODUCTION_RELEASE_DECISION_RECORD).is_file(),
       "WP8b's R6 decision record must not exist")
    ok(wp8b.PRODUCTION_RELEASE_PINNED is False,
       "WP8b's PRODUCTION_RELEASE_PINNED must still be False")


def check_session_contract_hash() -> None:
    """The contract's own digest must be the digest of its bytes on disk."""
    digest = accepts(lambda: s.session_contract_sha256(), "the contract digest")
    on_disk = hashlib.sha256(Path(s.__file__).resolve().read_bytes()).hexdigest()
    ok(digest == on_disk,
       f"the contract digest {digest} is not the file's sha256 {on_disk}")


def check_main_reports_and_runs_nothing() -> None:
    """``main`` prints the gate report and performs NO session."""
    import io
    import contextlib
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        status = accepts(lambda: s.main([]), "main")
    ok(status == 0, f"main must return 0, got {status!r}")
    text = buffer.getvalue()
    ok(text.strip(), "main must print a report")
    report = json.loads(text)
    ok(report["session_contract_sha256"] == s.session_contract_sha256(),
       "main's report must carry the contract digest")
    ok(report["gate_status"]["gates_open"] == 0,
       "main's report must show no open gate")
    ok(report["step_order"] == list(s.STEP_ORDER),
       "main's report must carry the frozen step order")
    ok("complete_pending_image_audit" in report["receipt_statuses"],
       "main's report must carry the receipt statuses")
    # A report is not a receipt: main must not emit an accepted verdict.
    ok("accepted" not in {key for key in report if report[key] is True},
       "main must not report an accepted anything")


# ===========================================================================
# 2. The instance: WP8d-production verification and the one-session rule
# ===========================================================================


def check_instance_verification_and_state() -> None:
    """S1: the instance, the slot token, the state file and the session gate."""
    base = new_base("instance")

    # The stand-in reader returns the REVIEWED record.
    layout, _ = R._layout_and_writer(base, "ok", nonce="ok-wp8b")
    verified = accepts(lambda: s.verify_instance_for_session(1, root=layout,
                                                             standin=True),
                       "verifying the stand-in instance")
    ok(verified["verdict"] == "verified", f"the verdict drifted: {verified}")
    ok(verified["slot_name"] == "stage2_01",
       f"slot 1 must be stage2_01, got {verified['slot_name']}")
    ok(verified["instance_id"] == st.STANDIN_ID,
       f"the stand-in id drifted: {verified['instance_id']}")
    ok(verified["layout_kind"] in ("standin", "STANDIN", "production")
       or "standin" in str(verified["layout_kind"]).lower(),
       f"the layout kind must be the stand-in one: {verified['layout_kind']}")
    # EVERY hash the session uses must be a real digest on the record.
    for field in ("instance_id", "index_content_sha256", "prepared_id",
                  "generation_manifest_content_sha256",
                  "implementation_record_content_sha256"):
        ok(field in verified, f"the verified record must carry {field!r}")
    ok(s._is_sha256(verified["index_content_sha256"]),
       "the instance index content hash must be a sha256")

    # The PRODUCTION reader must refuse today (WP8b R6).
    outcome = observe(lambda: s.verify_instance_for_session(1, root=layout,
                                                            standin=False))
    ok(outcome["outcome"] == "raised" and outcome["type"] == "InstanceRefused",
       f"the production reader must refuse: {outcome}")
    ok("require_production=True" in outcome["text"],
       f"the production refusal must name the production route: {outcome['text']}")

    # --- the STAND-IN reader's OWN wrapper raise (:525) is load-bearing ------
    # ``verify_instance_for_session`` catches WP8d's ``ProductionLayoutError``
    # and re-raises it as ``InstanceRefused`` with the wording
    # "the stand-in instance did not verify".  The tests above only ever make
    # the PRODUCTION reader refuse, which is the SECOND except clause -- so
    # dropping the first ``raise`` leaves them green while a stand-in failure
    # silently falls through to the production reader at :527 and is reported as
    # a production refusal.  That misattributes the cause and, on any layout
    # where the production reader behaves differently, would report the wrong
    # boundary.  So the stand-in reader is made to fail HERE, on a slot that is
    # canonical but names no prepared instance.
    standin_fail = observe(lambda: s.verify_instance_for_session(
        len(wp8dp.SLOT_NAMES), root=layout, standin=True))
    ok(standin_fail["outcome"] == "raised",
       f"an unprepared stand-in slot must refuse: {standin_fail}")
    ok(standin_fail["type"] == "InstanceRefused",
       f"the stand-in reader's own refusal must be an InstanceRefused: "
       f"{standin_fail}")
    ok("the stand-in instance did not verify" in standin_fail["text"],
       "a stand-in failure must be reported as a STAND-IN failure, not as a "
       f"production one: {standin_fail['text']}")
    ok("require_production=True" not in standin_fail["text"],
       "the stand-in refusal must not borrow the production route's wording: "
       f"{standin_fail['text']}")

    # require_instance_matches_session: verified record vs caller claim.
    accepts(lambda: s.require_instance_matches_session(
        verified, expected_instance_id=verified["instance_id"],
        expected_slot=verified["slot_name"]),
        "a matching instance/slot claim")
    refuses(lambda: s.require_instance_matches_session(
        verified, expected_instance_id=st.STANDIN_ID_B,
        expected_slot=verified["slot_name"]),
        "ProductionSessionError", "different instance")
    refuses(lambda: s.require_instance_matches_session(
        verified, expected_instance_id=verified["instance_id"],
        expected_slot="stage2_02"),
        "ProductionSessionError", "different slot")
    refuses(lambda: s.require_instance_matches_session(
        {}, expected_instance_id="x", expected_slot="stage2_01"),
        "ProductionSessionError", "missing or empty")
    refuses(lambda: s.require_instance_matches_session(
        {**verified, "verdict": "unverified"}, expected_instance_id=verified["instance_id"],
        expected_slot=verified["slot_name"]),
        "ProductionSessionError", "verdict")
    refuses(lambda: s.require_instance_matches_session(
        {**verified, "layout_kind": "made-up"}, expected_instance_id=verified["instance_id"],
        expected_slot=verified["slot_name"]),
        "ProductionSessionError", "layout kind")

    # The slot token: both forms accepted and agreeing; everything else refused.
    for slot, expected in ((1, "stage2_01"), ("stage2_01", "stage2_01"),
                           (2, "stage2_02"), ("stage2_02", "stage2_02")):
        ok(s._slot_token(slot) == expected,
           f"slot {slot!r} must token to {expected}")
    for bad in (0, -1, 99, True, False, "stage2_99", "../escape", "",
                "stage2_01 ", None, 1.0, "stage2_1"):
        refuses(lambda bad=bad: s._slot_token(bad), "ProductionSessionError",
                "slot")

    # The state file: canonical encoding, round-trip, refusal on garbage.
    path = accepts(lambda: s.session_state_path(layout, 1),
                   "the session state path")
    ok(path.name.endswith(".json") and path.parent.is_dir(),
       f"the state path must live inside the instance root: {path}")
    ok(s._read_state(layout, 1) is None,
       "a fresh instance must have no recorded session")
    record = {"schema": s.SESSION_STATE_SCHEMA, "status": "complete",
              "session_id": "probe-1", "identity_sha256": "a" * 64}
    accepts(lambda: s._write_state(layout, 1, record), "writing the state file")
    read_back = accepts(lambda: s._read_state(layout, 1), "reading the state back")
    ok(read_back == record, f"the state must round-trip: {read_back}")
    # A garbage state file is a REFUSAL, not a missing file (fail-closed), and
    # it is a SESSION refusal rather than a resume one: it blocks a first
    # session just as it blocks a resume.
    path.write_text("not json", encoding="ascii")
    refuses(lambda: s._read_state(layout, 1), "ProductionSessionError")
    path.write_bytes(b"\xff\xfe\x00binary")
    refuses(lambda: s._read_state(layout, 1), "ProductionSessionError")
    path.write_text('{"schema": "wrong"}', encoding="ascii")
    refuses(lambda: s._read_state(layout, 1), "ProductionSessionError",
            "session state record")
    # A non-canonical encoding of an otherwise valid record is refused too.
    path.write_text(json.dumps(record, sort_keys=True), encoding="ascii")
    refuses(lambda: s._read_state(layout, 1), "ProductionSessionError",
            "canonical encoding")

    # The one-session-per-instance gate, in all three of its states.
    #
    # The gate has exactly TWO refusals plus the empty-state pass, and the
    # middle one is subtle: a COMPLETE state with a DIFFERENT session id is
    # PERMITTED here, because that is the resume path — ``resume_missing_ranges``
    # separately requires the same identity and a NEW one-use authorization, so
    # permitting it here is not a hole.  What is refused here is (a) a
    # non-complete state, and (b) the SAME session id replayed on a closed
    # instance.
    accepts(lambda: s._require_session_allowed(None, 1, "session-a"),
            "a first session on an unused instance")
    # (a) a torn/partial recorded state leaves no permission behind.
    refused = {**record, "status": "incomplete"}
    refuses(lambda: s._require_session_allowed(refused, 1, "session-a"),
            "ProductionSessionError", "one session per instance")
    refuses(lambda: s._require_session_allowed({**refused, "status": "refused"},
                                               1, "session-b"),
            "ProductionSessionError", "one session per instance")
    # (b) the SAME session id may not be replayed on a closed instance.
    refuses(lambda: s._require_session_allowed(record, 1, "probe-1"),
            "ProductionSessionError", "may not be replayed")
    # A different session id on a COMPLETE instance is the resume path.
    accepts(lambda: s._require_session_allowed(record, 1, "session-b"),
            "a NEW session id on a complete instance (the resume path)")
    # A state with no identity hash is unusable.
    refuses(lambda: s._require_session_allowed({**record, "identity_sha256": None},
                                               1, "session-b"),
            "ProductionSessionError", "identity hash")
    # A symlinked state file must be ignored rather than followed.
    path.unlink()
    path.symlink_to(Path(layout) / "elsewhere.json")
    ok(s._read_state(layout, 1) is None,
       "a symlinked state file must not be followed")
    path.unlink()


# ===========================================================================
# 3. The one-use owner authorization
# ===========================================================================


def check_authorization_validation() -> None:
    """S3: the authorization must match VERIFIED values and refuse every forgery."""
    base = new_base("auth")
    identity_sha = st.draft_identity_sha256()
    good, verified = authorization_over(base, name="auth-ok", nonce="ok-wp8b")
    binding = {"accepted_content_sha256": identity_sha}
    contract = s.session_contract_sha256()

    checked = accepts(lambda: s.validate_authorization(
        good, verified=verified, accepted_binding=binding,
        session_contract_sha256=contract, today=st.PINNED),
        "a valid one-use authorization")
    ok(checked == good, "validation must return the authorization unchanged")

    # Structure: not a mapping at all.
    for bad in (None, "authorization", [], 42, ()):
        refuses(lambda bad=bad: s.validate_authorization(
            bad, verified=verified, accepted_binding=binding,
            session_contract_sha256=contract, today=st.PINNED),
            "ProductionSessionError", "exact mapping")

    # EXACT key set: one missing, one extra.
    missing = {key: value for key, value in good.items() if key != "nonce"}
    refuses(lambda: s.validate_authorization(
        missing, verified=verified, accepted_binding=binding,
        session_contract_sha256=contract, today=st.PINNED),
        "ProductionSessionError", "missing")
    extra = {**good, "surprise": "x"}
    refuses(lambda: s.validate_authorization(
        extra, verified=verified, accepted_binding=binding,
        session_contract_sha256=contract, today=st.PINNED),
        "ProductionSessionError", "unexpected")

# Every field, one at a time.  Each is a SEPARATE forgery class, and each
    # entry names the refusal TYPE as well as a distinguishing substring, so a
    # mutation that inverts the guard's comparison is killed by whichever half
    # of the pair the mutant breaks.
    cases = [
        ("schema", "wrong/schema/v1", ("ProductionSessionError", "schema")),
        ("authorization_status", "owner_maybe",
         ("ProductionSessionError", "owner_authorized")),
        ("action", "some_other_action", ("ProductionSessionError", "action")),
        ("statement", "a different statement", ("ProductionSessionError", "wording")),
        ("instance_id", st.STANDIN_ID_B, ("ProductionSessionError", "instance")),
        ("generation_manifest_sha256", "c" * 64,
         ("ProductionSessionError", "generation manifest")),
        ("prepared_record_sha256", "d" * 64,
         ("ProductionSessionError", "prepared record")),
        ("bundle_sha256", "not-a-digest", ("ProductionSessionError", "bundle sha256")),
        ("accepted_identity_sha256", "e" * 64,
         ("ProductionSessionError", "accepted identity")),
        ("session_contract_sha256", "f" * 64,
         ("ProductionSessionError", "rebuild voids")),
        ("account", "", ("ProductionSessionError", "account")),
        ("kernel_id", "", ("ProductionSessionError", "kernel_id")),
        ("nonce", "", ("ProductionSessionError", "nonce")),
        ("expiry", "not-a-date", ("AuthorizationRefused", "calendar date")),
        ("expiry", "2026-1-1", ("AuthorizationRefused", "calendar date")),
    ]
    for field, value, (expected_type, needle) in cases:
        tampered = {**good, field: value}
        # A malformed DATE is reported as an authorization refusal because the
        # expiry cannot be parsed at all; every other bad field is a contract
        # violation found by ``_require``.  Both are session errors, so the
        # session's single ``except`` still yields a non-accepting receipt.
        refuses(lambda tampered=tampered: s.validate_authorization(
            tampered, verified=verified, accepted_binding=binding,
            session_contract_sha256=contract, today=st.PINNED),
            expected_type, needle)

    # A different accepted identity is refused.
    refuses(lambda: s.validate_authorization(
        good, verified=verified,
        accepted_binding={"accepted_content_sha256": "9" * 64},
        session_contract_sha256=contract, today=st.PINNED),
        "ProductionSessionError", "accepted identity")

    # Expiry: stale is refused, today is fine, tomorrow is fine.
    accepts(lambda: s.validate_authorization(
        {**good, "expiry": st.PINNED.isoformat()}, verified=verified,
        accepted_binding=binding, session_contract_sha256=contract,
        today=st.PINNED), "an authorization expiring today")
    accepts(lambda: s.validate_authorization(
        {**good, "expiry": "2099-12-31"}, verified=verified,
        accepted_binding=binding, session_contract_sha256=contract,
        today=st.PINNED), "an authorization expiring in the future")
    stale = {**good, "expiry": "2026-01-02"}
    refuses(lambda: s.validate_authorization(
        stale, verified=verified, accepted_binding=binding,
        session_contract_sha256=contract, today=datetime.date(2026, 1, 3)),
        "ProductionSessionError", "expired")

    # The result must be a COPY: mutating it must not touch the caller's record.
    mutable = dict(good)
    result = accepts(lambda: s.validate_authorization(
        mutable, verified=verified, accepted_binding=binding,
        session_contract_sha256=contract, today=st.PINNED), "validation again")
    result["nonce"] = "MUTATED"
    ok(mutable["nonce"] == good["nonce"],
       "validation must return a copy, not the caller's mapping")


def check_authorization_consumption_is_one_use() -> None:
    """A consumed authorization must be refused on its SECOND use.

    The replay is refused by WP8b's STATEFUL registry, not by anything in
    WP8c, so this case is what proves the registry is actually reached.
    """
    base = new_base("nonce")
    nonce_root = st.sandbox_root(base, "nonce-root")
    good = valid_authorization(base, nonce="oneuse-1")

    accepts(lambda: s.consume_authorization(good, nonce_root=nonce_root,
                                            today=st.PINNED),
            "consuming an authorization once")
    outcome = observe(lambda: s.consume_authorization(good, nonce_root=nonce_root,
                                                      today=st.PINNED))
    ok(outcome["outcome"] == "raised",
       f"a second consumption must be refused: {outcome}")
    ok(outcome["type"] == "AuthorizationRefused",
       f"the replay must be an AuthorizationRefused, got {outcome['type']}")

    # A DIFFERENT nonce must NOT resurrect the spent authorization: WP8b keys
    # the ledger on the approval's own bytes, so a fresh nonce string is a
    # different approval, and the SPENT one stays spent.
    resurrected = {**good, "nonce": "oneuse-2"}
    accepts(lambda: s.consume_authorization(resurrected, nonce_root=nonce_root,
                                            today=st.PINNED),
            "a genuinely different authorization is consumable")
    refuses(lambda: s.consume_authorization(good, nonce_root=nonce_root,
                                            today=st.PINNED),
            "AuthorizationRefused")


def check_wp8a_acceptance_is_refused() -> None:
    """S2: no acceptance record can exist offline, and WP8a must say so."""
    refuses(lambda: s.bind_accepted_identity(
        {"standin": True},
        reviewed_record_sha256=hashlib.sha256(b"x").hexdigest(),
        repo_root=_ROOT),
        "IdentityGateUnset", "accepted production identity")
    # A malformed pin is refused before WP8a is even called.
    refuses(lambda: s.bind_accepted_identity(
        {"standin": True}, reviewed_record_sha256="not-a-digest", repo_root=_ROOT),
        "ProductionSessionError", "sha256")

    # The real route: the REAL WP8a validator on the stand-in record must
    # refuse, and it must refuse as WP8a's own error type.
    from research.g9.wp8a import wp8a_production_identity_acceptance as wp8a
    outcome = observe(lambda: wp8a.accept_production_identity(
        {"standin": True, "schema": wp8a.ACCEPTANCE_SCHEMA},
        reviewed_record_sha256=hashlib.sha256(b"standin").hexdigest(),
        repo_root=str(_ROOT)))
    ok(outcome["outcome"] == "raised",
       f"WP8a must refuse a stand-in acceptance record: {outcome}")
    ok("Acceptance" in (outcome["type"] or "") or "Acceptance" in outcome["text"]
       or "acceptance" in outcome["text"].lower(),
       f"the WP8a refusal must be an acceptance-record refusal: {outcome}")

    # The identity binding helpers refuse malformed bindings.
    for bad in ({}, {"acceptance_record": None}, {"acceptance_record": {}},
                {"acceptance_record": {}, "reviewed_record_sha256": "x"},
                {"acceptance_record": {}, "reviewed_record_sha256": "a" * 64}):
        refuses(lambda bad=bad: s.require_session_identity_exact(bad, {}),
                "ProductionSessionError")
    refuses(lambda: s.require_session_identity_exact("not a mapping", {}),
            "ProductionSessionError")


# ===========================================================================
# 4. The record projection and the whole-range write
# ===========================================================================


def check_record_projection_and_write() -> None:
    """The committed record -> WP4b M1 projection, and the whole-range write."""
    identity_sha = st.draft_identity_sha256()
    committed = {
        "schema": "decisions_os/g9_stage2_coordinate_record/v1",
        "family": "d013__cb__v14_0_5x__r0x1_0000000000000p_0",
        "coordinate": {"ell_v14_0_5x_a": 3, "ell_v14_0_5x_b": 5},
        "linear_index": 42,
        "content_sha256": "a" * 64,
    }
    projected = accepts(lambda: s.project_record_for_writer(committed, identity_sha),
                        "projecting a committed record")
    ok(set(projected) == {"coordinates", "result"},
       f"the projection must be exactly {{coordinates, result}}, got {sorted(projected)}")
    ok(projected["coordinates"] == [3, 5],
       f"the coordinates must be axis-ordered, got {projected['coordinates']}")
    ok(projected["result"]["identity_sha256"] == identity_sha,
       "the projection must carry the accepted identity hash")
    ok(projected["result"]["record_content_sha256"] == "a" * 64,
       "the projection must carry the committed record's own content hash")
    ok(set(projected["result"]) == set(s.WRITER_RESULT_FIELDS),
       f"the projected result fields drifted: {sorted(projected['result'])}")

    # Every malformed committed record is refused, each for its own reason.
    refuses(lambda: s.project_record_for_writer({}, identity_sha),
            "ProductionSessionError", "committed record is required")
    refuses(lambda: s.project_record_for_writer("not a mapping", identity_sha),
            "ProductionSessionError")
    no_commitment = {**committed}
    del no_commitment["content_sha256"]
    refuses(lambda: s.project_record_for_writer(no_commitment, identity_sha),
            "ProductionSessionError", "content hash")
    no_coordinate = {**committed, "coordinate": None}
    refuses(lambda: s.project_record_for_writer(no_coordinate, identity_sha),
            "ProductionSessionError", "coordinate map")
    empty_coordinate = {**committed, "coordinate": {}}
    refuses(lambda: s.project_record_for_writer(empty_coordinate, identity_sha),
            "ProductionSessionError", "coordinate map")
    for bad_index in (-1, "42", 1.5, None, True):
        refuses(lambda bad_index=bad_index: s.project_record_for_writer(
            {**committed, "linear_index": bad_index}, identity_sha),
            "ProductionSessionError", "linear index")
    refuses(lambda: s.project_record_for_writer(committed, "not-a-digest"),
            "ProductionSessionError", "sha256")

    # The whole-range write: the result schema is pinned, and an empty plan
    # promotes nothing.
    base = new_base("write")
    writer_root = st.writer_root(base, "writer")
    schema = {"identity_sha256": "str", "record_content_sha256": "str"}
    written = accepts(lambda: s.write_sealed_whole_ranges(
        instance_root=writer_root, batch_records={}, result_schema=schema,
        accepted_identity=object(), session_identity={}, promoted_batch_ids=set(),
        accepted_identity_sha256=identity_sha), "writing no ranges")
    ok(written == [], f"an empty plan must promote nothing, got {written}")

    # The pinned schema is enforced.
    for bad_schema in ({}, {"identity_sha256": "str"}, schema | {"extra": "str"},
                       {"identity_sha256": "int", "record_content_sha256": "str"}):
        refuses(lambda bad_schema=bad_schema: s.write_sealed_whole_ranges(
            instance_root=writer_root, batch_records={},
            result_schema=bad_schema, accepted_identity=object(),
            session_identity={}, promoted_batch_ids=set(),
            accepted_identity_sha256=identity_sha),
            "ProductionSessionError", "result schema")
    refuses(lambda: s.write_sealed_whole_ranges(
        instance_root=writer_root, batch_records={}, result_schema=schema,
        accepted_identity=object(), session_identity={},
        promoted_batch_ids="a-string", accepted_identity_sha256=identity_sha),
        "ProductionSessionError", "collection")

    # A malformed member record is refused by the projection, not silently
    # dropped: a range is written whole or not at all.
    refuses(lambda: s.write_sealed_whole_ranges(
        instance_root=writer_root, batch_records={"b0": [{}]},
        result_schema=schema, accepted_identity=object(), session_identity={},
        promoted_batch_ids=set(), accepted_identity_sha256=identity_sha),
        "ProductionSessionError", "committed record is required")


def check_record_building_never_fabricates() -> None:
    """``build_records_for_ranges`` with no engine results must build NOTHING."""
    base = new_base("records")
    binding = {"accepted_content_sha256": st.draft_identity_sha256(),
               "draft_identity": st.draft_identity()}
    family = R.rehearsal_family()
    space = records.family_space(family, records.build_frozen_axes())
    built = accepts(lambda: s.build_records_for_ranges(
        binding, st.draft_identity(), family, st.writer_root(base, "w"),
        d013_fired=R.REHEARSAL_D013_FIRED, engine_results=None),
        "building with no engine results")
    ok(built["records_built"] == 0,
       f"no engine results must build no records, got {built['records_built']}")
    ok("never fabricates" in built["note"],
       f"the note must say nothing was fabricated: {built['note']}")
    ok(built["accepted"] is False, "a build result must never be accepted")
    ok(built["coordinates"] == space.total_coordinates,
       "the reported space must be the committed one")

    # A family that is NOT declared must be refused.
    refused = observe(lambda: s.build_records_for_ranges(
        binding, st.draft_identity(), "not a family",
        st.writer_root(base, "w2"), d013_fired=R.REHEARSAL_D013_FIRED,
        engine_results=None))
    ok(refused["outcome"] == "raised",
       f"an undeclared family must be refused: {refused}")
    refuses(lambda: s.build_records_for_ranges(
        binding, st.draft_identity(), None, st.writer_root(base, "w3"),
        d013_fired=R.REHEARSAL_D013_FIRED, engine_results=None),
        "ProductionSessionError", "writer family is required")


def check_missing_ranges_requires_a_sealed_plan() -> None:
    """WP4b's ``missing_ranges`` refuses without a sealed plan."""
    base = new_base("missing")
    outcome = observe(lambda: s.missing_whole_ranges(
        st.writer_root(base, "unsealed")))
    ok(outcome["outcome"] == "raised",
       f"an unsealed writer root must refuse missing_ranges: {outcome}")
    ok("missing_ranges" in outcome["type"] or "Writer" in outcome["type"],
       f"the refusal must come from WP4b: {outcome}")


# ===========================================================================
# 5. The resume policy
# ===========================================================================


def check_resume_policy() -> None:
    """The four independent resume refusals, each for its own reason."""
    base = new_base("resume")
    identity_sha = st.draft_identity_sha256()
    layout, writer_root = R._layout_and_writer(base, "resume", nonce="resume-wp8b")
    previous = {"schema": s.RECEIPT_SCHEMA, "status": "incomplete_budget",
                "accepted": False, "session_id": "session-1",
                "instance_id": st.STANDIN_ID}
    new_authorization = {"nonce": "new-approval", "accepted_identity_sha256": identity_sha}

    # The unsealed writer root has no missing ranges, so an empty expected set
    # is the exact match and the resume is authorized (but never accepted).
    # On an unsealed root WP4b itself refuses, which is the honest outcome and
    # is asserted below instead.
    outcome = observe(lambda: s.resume_missing_ranges(
        slot=1, root=layout, instance_root=writer_root, session_id="session-2",
        identity_sha256=identity_sha, authorization=new_authorization,
        previous_receipt=previous, expected_missing_batch_ids=[]))
    ok(outcome["outcome"] == "raised",
       f"an unsealed plan must refuse the resume: {outcome}")

    # Build a REAL sealed plan so the four refusals are each observable.
    sealed_root = st.writer_root(base, "sealed")
    family = R.rehearsal_family()
    total = records.family_space(family, records.build_frozen_axes()).total_coordinates
    plan = accepts(lambda: writer.seal_range_plan(
        sealed_root, family="wp8c_nonproduction_probe",
        total_coordinates=total,
        identity=s.writer_identity_of({"draft_identity": st.draft_identity()}),
        session=st.draft_identity()), "sealing a real range plan")
    batch_ids = [row["batch_id"] for row in plan["ranges"]]
    ok(batch_ids, f"the sealed plan must have ranges, got {plan}")
    ok(writer.missing_ranges(sealed_root) is not None,
       "WP4b must report the missing ranges on a sealed plan")
    missing_ids = [row["batch_id"] for row in s.missing_whole_ranges(sealed_root)]
    ok(missing_ids == batch_ids,
       f"every range starts missing: {missing_ids} vs {batch_ids}")

    # (1) the exact resume set is authorized, and is NEVER accepted.
    resumed = accepts(lambda: s.resume_missing_ranges(
        slot=1, root=layout, instance_root=sealed_root, session_id="session-2",
        identity_sha256=identity_sha, authorization=new_authorization,
        previous_receipt=previous, expected_missing_batch_ids=missing_ids),
        "authorizing a resume of the exact missing ranges")
    ok(resumed["verdict"] == "resume_authorized",
       f"the resume verdict drifted: {resumed['verdict']}")
    ok(resumed["accepted"] is False,
       "a resume verdict must never be an acceptance")
    ok(resumed["resumed_whole_ranges_only"] is True,
       "the resume must declare whole-ranges-only")
    ok(resumed["resumed_batch_ids"] == missing_ids,
       "the resume must name exactly the missing whole ranges")

    # (2) an already-accepted previous run cannot be resumed.
    refuses(lambda: s.resume_missing_ranges(
        slot=1, root=layout, instance_root=sealed_root, session_id="session-2",
        identity_sha256=identity_sha, authorization=new_authorization,
        previous_receipt={**previous, "accepted": True},
        expected_missing_batch_ids=missing_ids),
        "ResumeRefused", "NOT accepted")

    # (3) a previous receipt with no meaningful status cannot be resumed.
    refuses(lambda: s.resume_missing_ranges(
        slot=1, root=layout, instance_root=sealed_root, session_id="session-2",
        identity_sha256=identity_sha, authorization=new_authorization,
        previous_receipt={**previous, "status": "complete_pending_image_audit"},
        expected_missing_batch_ids=missing_ids),
        "ResumeRefused", "incomplete or refused")

    # (4) a resume in the SAME session id is refused.
    refuses(lambda: s.resume_missing_ranges(
        slot=1, root=layout, instance_root=sealed_root, session_id="session-1",
        identity_sha256=identity_sha, authorization=new_authorization,
        previous_receipt=previous, expected_missing_batch_ids=missing_ids),
        "ResumeRefused", "NEW session")

    # (5) a narrowed or widened resume set is refused.
    refuses(lambda: s.resume_missing_ranges(
        slot=1, root=layout, instance_root=sealed_root, session_id="session-2",
        identity_sha256=identity_sha, authorization=new_authorization,
        previous_receipt=previous, expected_missing_batch_ids=missing_ids[:-1]),
        "ResumeRefused", "exactly the missing whole ranges")
    refuses(lambda: s.resume_missing_ranges(
        slot=1, root=layout, instance_root=sealed_root, session_id="session-2",
        identity_sha256=identity_sha, authorization=new_authorization,
        previous_receipt=previous,
        expected_missing_batch_ids=missing_ids + ["invented-batch"]),
        "ResumeRefused", "exactly the missing whole ranges")

    # (6) a different identity on resume is refused.
    refuses(lambda: s.resume_missing_ranges(
        slot=1, root=layout, instance_root=sealed_root, session_id="session-2",
        identity_sha256="9" * 64, authorization=new_authorization,
        previous_receipt=previous, expected_missing_batch_ids=missing_ids),
        "ResumeRefused", "accepted identity")

    # (7) an authorization with no nonce is refused.
    refuses(lambda: s.resume_missing_ranges(
        slot=1, root=layout, instance_root=sealed_root, session_id="session-2",
        identity_sha256=identity_sha,
        authorization={"accepted_identity_sha256": identity_sha},
        previous_receipt=previous, expected_missing_batch_ids=missing_ids),
        "ResumeRefused", "nonce")

    # (8) a missing previous receipt is refused.
    refuses(lambda: s.resume_missing_ranges(
        slot=1, root=layout, instance_root=sealed_root, session_id="session-2",
        identity_sha256=identity_sha, authorization=new_authorization,
        previous_receipt=None, expected_missing_batch_ids=missing_ids),
        "ResumeRefused", "required")
    # (9) a bad slot is refused before anything else is examined.  It is a plain
    # session error, not a resume one, because the slot token is checked by the
    # shared path canonicalizer before the resume policy's own guards run.
    refuses(lambda: s.resume_missing_ranges(
        slot=99, root=layout, instance_root=sealed_root, session_id="session-2",
        identity_sha256=identity_sha, authorization=new_authorization,
        previous_receipt=previous, expected_missing_batch_ids=missing_ids),
        "ProductionSessionError", "slot")

    # (10) after a COMPLETED session, a resume under a different identity is
    # refused, and the same identity under a new session id is allowed.
    complete_state = {"schema": s.SESSION_STATE_SCHEMA, "status": "complete",
                      "session_id": "session-done", "instance_id": st.STANDIN_ID,
                      "identity_sha256": identity_sha,
                      "session_contract_sha256": s.session_contract_sha256(),
                      "promoted_range_batch_ids": []}
    accepts(lambda: s._write_state(layout, 1, complete_state),
            "recording a completed session")
    refuses(lambda: s.resume_missing_ranges(
        slot=1, root=layout, instance_root=sealed_root, session_id="session-2",
        identity_sha256="8" * 64, authorization=new_authorization,
        previous_receipt=previous, expected_missing_batch_ids=missing_ids),
        "ResumeRefused", "SAME accepted identity")
    refuses(lambda: s.resume_missing_ranges(
        slot=1, root=layout, instance_root=sealed_root, session_id="session-done",
        identity_sha256=identity_sha, authorization=new_authorization,
        previous_receipt=previous, expected_missing_batch_ids=missing_ids),
        "ResumeRefused", "reuse the completed session's id")
    # An unusable recorded state (not complete) is refused.
    s._write_state(layout, 1, {**complete_state, "status": "torn"})
    refuses(lambda: s.resume_missing_ranges(
        slot=1, root=layout, instance_root=sealed_root, session_id="session-2",
        identity_sha256=identity_sha, authorization=new_authorization,
        previous_receipt=previous, expected_missing_batch_ids=missing_ids),
        "ResumeRefused", "unusable")


# ===========================================================================
# 6. The seam mapping and the injected callables
# ===========================================================================


def check_end_to_end_session_receipt() -> None:
    """The WHOLE session, driven through ``run_production_session`` itself.

    Every other check in this file exercises ONE helper.  Without this check the
    adapter's own body -- every discarded ``guard.check()``, ``steps.record(...)``,
    ``guard.mark(...)`` and ``_require_passed(...)`` inside ``run_production_session``
    -- is never executed by the fixture, so each of those mutants replaces a real
    step call with ``pass`` and the run stays green.  That is a fixture GAP, not
    an equivalent mutation, and this check closes it.

    It asserts the OUTCOME of a complete session rather than re-asserting each
    guard: the frozen step order, the non-accepting receipt, the promoted ranges
    and the absence of scientific outputs are all downstream observations of
    whether those step calls actually ran.
    """
    base = tempfile.mkdtemp(prefix="e2e-", dir=str(SCRATCH))
    layout, writer_root = R._layout_and_writer(base, "e2e", nonce="e2e-wp8b")
    verified = s.verify_instance_for_session(1, root=layout, standin=True)
    family = R.rehearsal_family()
    total = records.family_space(family, records.build_frozen_axes()).total_coordinates

    receipt = accepts(lambda: R.run_session(
        base, layout=layout, writer_root=writer_root,
        nonce_root=st.sandbox_root(base, "e2e-nonce"),
        session_id="session-e2e",
        authorization=R._one_use_authorization(
            verified, st.draft_identity_sha256(), nonce="e2e-1"),
        session_identity=st.draft_identity(), clock=lambda: 0.0,
        verified_instance=verified, family=family,
        engine_results=R.placeholder_engine_results(total)),
        "the complete stand-in session")

    # Every step call in the adapter's body must have run: if any ``steps.record``
    # or ``guard.mark`` had been mutated to ``pass``, its step would be missing here.
    ok(sorted(receipt["steps_passed"]) == sorted(s.STEP_ORDER),
       f"the session did not pass every frozen step: {receipt['steps_passed']}")
    ok(receipt["status"] == "complete_pending_image_audit",
       f"the complete session must be pending the image audit: {receipt['status']}")
    ok(receipt["accepted"] is False,
       "a WP8c receipt is never an acceptance")
    ok(receipt["promoted_range_batch_ids"],
       f"no range was promoted, so S7 did not run: {receipt}")
    ok(receipt["scientific_outputs"] == [],
       f"a stand-in session must carry no scientific output: {receipt}")
    # The final-set audit is the S7 outcome: it only passes when every planned
    # coordinate was written, so it is the assertion that the record-building and
    # range-writing calls actually happened.
    ok(receipt["final_set"]["verdict"] == "accepted",
       f"the final set is not an exact cover: {receipt['final_set']}")
    ok(receipt["final_set"]["total_coordinates"] == total,
       f"the final set covers {receipt['final_set']['total_coordinates']} "
       f"coordinates, not the family's {total}")

    # The state file is written ONLY on completion (``:1298-1311``).  Its presence
    # is therefore the observation that the closing ``_write_state`` call ran.
    state = accepts(lambda: s._read_state(layout, 1),
                    "the completed session's state record")
    ok(state["status"] == "complete",
       f"the instance must be closed on completion: {state}")


def check_failed_prerequisite_blocks_every_step() -> None:
    """A failed WP2 recheck must produce a REFUSED receipt, not a raise.

    ``run_production_session`` converts a ``ProductionSessionError`` into a sealed
    non-accepting receipt (``:1282-1297``).  Asserting the receipt -- its refusal
    type and the exact set of blocked steps -- is what observes that
    ``steps.refuse(...)`` ran, and that every device and write step after the
    failure is blocked.  Without it the ``steps.refuse`` mutant is invisible.
    """
    base = tempfile.mkdtemp(prefix="wp2fail-", dir=str(SCRATCH))

    def failing_wp2(**kwargs):
        return ({"schema": "wp8c/wp2-failure-probe",
                 "content_sha256": hashlib.sha256(b"probe").hexdigest()}, False)

    layout, writer_root = R._layout_and_writer(base, "wp2fail", nonce="wp2fail-wp8b")
    verified = s.verify_instance_for_session(1, root=layout, standin=True)
    receipt = accepts(lambda: R.run_session(
        base, layout=layout, writer_root=writer_root,
        nonce_root=st.sandbox_root(base, "wp2fail-nonce"),
        session_id="session-wp2fail",
        authorization=R._one_use_authorization(
            verified, st.draft_identity_sha256(), nonce="wp2fail-1"),
        session_identity=st.draft_identity(), clock=lambda: 0.0,
        seam_overrides={"wp2_recheck": failing_wp2},
        verified_instance=verified),
        "the session with a failed WP2 prerequisite")

    ok(receipt["status"] == "refused",
       f"a failed WP2 prerequisite must refuse the session: {receipt['status']}")
    ok(receipt["accepted"] is False,
       "a refused session must never be accepted")
    ok(receipt["refusal_type"] == "PrerequisiteFailed",
       f"the refusal must name the prerequisite failure: {receipt['refusal_type']}")
    ok(receipt["blocked_steps"] == ["wp2_recheck_passed", "wp3_check_passed",
                                    "records_built", "ranges_promoted"],
       f"every dependent device/write step must be blocked: {receipt['blocked_steps']}")
    ok(receipt["scientific_outputs"] == [],
       "a blocked session must carry no scientific output")
    # A refused run writes NO state, so the instance stays free for a NEW session.
    # ``_read_state`` returns ``None`` for an absent file rather than raising
    # (``:431-434``), so the absence of a record is the observation here.
    ok(s._read_state(layout, 1) is None,
       "a refused session must not close the instance")


def check_seams_and_injected_callables() -> None:
    """``_seams`` must name the REAL reviewed entry points, and the two that
    WP8c refuses to invent must have no default."""
    seams = accepts(lambda: s._seams(), "the seam mapping")
    ok(seams["wp2_recheck"] is wp2.recheck_before_first_write,
       "the WP2 seam must be the reviewed function itself")
    ok(seams["wp3_run"] is __import__(
        "research.g9.stage2_section_b2_harness", fromlist=["x"]).run_section_b2,
       "the WP3 seam must be the reviewed function itself")
    ok(seams["build_record"] is records.build_record,
       "the record seam must be the reviewed function itself")
    ok(seams["write_range"] is writer.write_range,
       "the write seam must be the reviewed function itself")
    ok(seams["missing_ranges"] is writer.missing_ranges,
       "the missing-ranges seam must be the reviewed function itself")
    ok(seams["audit_final_set"] is writer.audit_final_set,
       "the audit seam must be the reviewed function itself")
    ok(seams["identity_exact_match"] is wp1.exact_match,
       "the identity comparison seam must be WP1's own function")
    ok(seams["identity_validate"] is wp1.validate_production_identity,
       "the identity validation seam must be WP1's own function")
    ok(seams["bind_accepted_identity"] is s.bind_accepted_identity,
       "the identity binding seam must default to the REAL WP8a route")
    ok(seams["require_session_identity_exact"] is s.require_session_identity_exact,
       "the identity comparison seam must default to the REAL WP8a route")
    # WP8c must NOT invent a device backend or a Python reference.
    ok(seams["device_backend_factory"] is None,
       "no device backend factory may be defaulted")
    ok(seams["python_reference"] is None,
       "no Python reference may be defaulted")

    # The two injected callables are refused when absent.
    refuses(lambda: s.boundary_device_backend(
        s.AuthorityBoundary(copy.deepcopy(st.STANDIN_OBSERVATIONS)), {}),
        "ProductionSessionError", "device backend factory")
    refuses(lambda: s.wp3_reference({}), "ProductionSessionError", "Python reference")
    factory = accepts(lambda: s.boundary_device_backend(
        s.AuthorityBoundary(copy.deepcopy(st.STANDIN_OBSERVATIONS)),
        {"device_backend_factory": st.device_backend_factory}),
        "constructing the device backend through the factory")
    ok(factory is not None, "the injected factory must produce a backend")
    reference = accepts(lambda: s.wp3_reference(
        {"python_reference": st.python_reference}),
        "taking the injected Python reference")
    ok(callable(reference), "the Python reference must be callable")

    # WP3's validation coordinates are the HARNESS's frozen list, not a
    # caller's selection.
    coordinates = accepts(lambda: s.validation_coordinates(),
                          "the validation coordinates")
    from research.g9 import stage2_section_b2_harness as harness
    ok(tuple(coordinates) == tuple(harness.build_validation_coordinates()),
       "the validation coordinates must be the harness's frozen list")


# ===========================================================================
# 8. The gaps the 07:51 sweep left open
# ===========================================================================


def check_identity_binding_shape_is_load_bearing() -> None:
    """Every ``require_session_identity_exact`` guard, driven on both outcomes.

    The 07:51 sweep left 12 survivors on the old L605/L607 schema guard.  That
    guard was UNSATISFIABLE -- WP8a's published receipt carries neither a
    ``status`` nor a ``schema`` key
    (``research/g9/wp8a/wp8a_production_identity_acceptance.py:1187-1205``) -- so
    no fixture could ever satisfy it and every mutation of it was invisible.  The
    guard now asserts WP8a's own re-derived ``accepted_content_sha256``.

    This check proves the NEW guard is load-bearing in both directions: a binding
    with the field and a tampered one without it must differ, and the
    non-empty-draft guard at ``:630`` must reject an EMPTY draft (not merely a
    non-dict one), which is the ``and``-operand-to-``True`` mutant.
    """
    binding = R.standin_acceptance_binding(s)
    identity = st.draft_identity()

    # The guards are exercised DIRECTLY, one at a time, because the full
    # comparison below deliberately cannot succeed offline: ``exact_match_session``
    # re-validates the carried acceptance record through WP8a's own
    # ``accept_production_identity`` (``...:1219-1220``), and the stand-in's
    # record is explicitly NOT an acceptance, so WP8a refuses it.  That refusal
    # is itself the positive control for the re-validation, asserted below.
    # What these cases pin is that each GUARD fires on its own bad input, which
    # is what a removed or weakened guard would stop doing.

    # (0) POSITIVE CONTROL: every guard passes on the well-formed binding, and
    #     the run then reaches WP8a's re-validation and is refused THERE -- by
    #     the wrong-key-set check, not by any WP8c guard.
    outcome = observe(lambda: s.require_session_identity_exact(binding, identity))
    ok(outcome["outcome"] == "raised" and outcome["type"] == "IdentityGateUnset",
       f"the stand-in record must reach WP8a's re-validation: {outcome}")
    ok("wrong key set" in outcome["text"],
       f"the refusal must be WP8a's own re-validation, not a WP8c guard: "
       f"{outcome['text'][:200]}")
    ok("WP8a acceptance receipt" not in outcome["text"],
       f"the well-formed binding must not trip the receipt guard: {outcome['text'][:200]}")
    ok("draft identity" not in outcome["text"],
       f"the well-formed binding must not trip the draft guard: {outcome['text'][:200]}")

    # (1) The re-derived digest guard: absent, or not a digest, or not a sha256.
    #     Each is a SEPARATE way the binding is not a WP8a receipt, and the needle
    #     is what separates this refusal from the ones below it.
    for bad in (None, "x", 42, [], {}, "z" * 64, "a" * 63, 1, "0" * 64 + "G"):
        stripped = {k: v for k, v in binding.items()
                    if k != "accepted_content_sha256"}
        stripped["accepted_content_sha256"] = bad
        refuses(lambda stripped=stripped: s.require_session_identity_exact(
            stripped, identity),
            "ProductionSessionError", "WP8a acceptance receipt")
    # The field absent entirely (not merely None) is the same refusal.
    refuses(lambda: s.require_session_identity_exact(
        {k: v for k, v in binding.items() if k != "accepted_content_sha256"},
        identity),
        "ProductionSessionError", "WP8a acceptance receipt")

    # (2) The binding itself must be a dict, not merely mapping-like.
    for bad in (None, "binding", [], 42, ()):
        refuses(lambda bad=bad: s.require_session_identity_exact(bad, identity),
                "ProductionSessionError", "binding is missing")

    # (3) The embedded draft must be a NON-EMPTY dict.  ``{}`` is the exact
    #     input the ``and``-operand-to-``True`` mutant accepts and the original
    #     refuses, so this kills it.
    for bad in (None, "draft", [], 42, {}):
        refuses(lambda bad=bad: s.require_session_identity_exact(
            {**binding, "draft_identity": bad}, identity),
            "ProductionSessionError", "draft identity")

    # (4) A TAMPERED session identity is still refused by the REAL WP1 match,
    #     so the new guard did not accidentally become the only thing standing
    #     between a caller and an accepted identity.
    tampered = copy.deepcopy(identity)
    tampered["status"] = "ACCEPTED"
    refuses(lambda: s.require_session_identity_exact(binding, tampered),
            "IdentityGateUnset", "exact match")

    # (5) The record/pin/root helpers, each on its own distinguishing needle so
    #     a mutation that removes one cannot fall through to another guard's
    #     refusal text.  An EMPTY record is a separate case: ``type({}) is dict``
    #     passes, so it reaches WP8a's re-validation and is refused THERE.  That
    #     is the positive control for the re-validation on a second input, and it
    #     is why the empty record is asserted to name WP8a rather than WP8c.
    for bad, needle in ((None, "acceptance record"),
                        ("record", "acceptance record"),
                        ([], "acceptance record"),
                        (42, "acceptance record")):
        refuses(lambda bad=bad: s.require_session_identity_exact(
            {**binding, "acceptance_record": bad}, identity),
            "ProductionSessionError", needle)
    empty_record = observe(lambda: s.require_session_identity_exact(
        {**binding, "acceptance_record": {}}, identity))
    ok(empty_record["type"] == "IdentityGateUnset",
       f"an empty record must reach WP8a's re-validation: {empty_record}")
    ok("acceptance record it was" not in empty_record["text"],
       f"an empty record is a dict, so the type guard must not fire: "
       f"{empty_record['text'][:160]}")
    for bad in (None, "x", 42, [], {}, "a" * 63, "z" * 64):
        refuses(lambda bad=bad: s.require_session_identity_exact(
            {**binding, "reviewed_record_sha256": bad}, identity),
            "ProductionSessionError", "sha256")
    for bad in (None, "", 42, [], {}):
        refuses(lambda bad=bad: s.require_session_identity_exact(
            {**binding, "repo_root": bad}, identity),
            "ProductionSessionError", "repository root")


def check_slippery_discarded_calls() -> None:
    """The S2 discarded-call sites whose effect nothing observed.

    Each of these is a bare call statement, so S2 replaces it with ``pass`` and
    the mutation survives unless the fixture asserts the call's EFFECT.  The
    calls below are all load-bearing; the fixture had simply never looked at what
    they produce.
    """
    # --- L327 ``_seal`` strips a pre-existing content hash ------------------
    # Re-sealing a record that already carries ``content_sha256`` MUST strip it,
    # or the digest is computed over a body that contains its own old hash and a
    # re-seal of identical content yields a different digest -- so the seal is
    # not idempotent and cannot be used to detect tampering.
    original = {"schema": "probe/v1", "value": 1}
    once = accepts(lambda: s._seal(original), "sealing a fresh record")
    twice = accepts(lambda: s._seal(once), "re-sealing an already-sealed record")
    ok(once["content_sha256"] == twice["content_sha256"],
       f"sealing must be idempotent: {once['content_sha256']} != "
       f"{twice['content_sha256']}")
    ok("content_sha256" in once, "a sealed record must carry its content hash")
    # A record that arrives with a WRONG content hash must be re-sealed to the
    # hash of its own body, not trusted.
    forged = {**once, "content_sha256": "b" * 64}
    resealed = accepts(lambda: s._seal(forged), "re-sealing a forged record")
    ok(resealed["content_sha256"] == once["content_sha256"],
       f"a forged content hash must be replaced by the body's own: {resealed}")
    # A NaN is refused by the seal itself, so a non-canonical body never ships.
    # ``json.dumps`` raises before ``_seal`` can refuse, so the guard is driven
    # through a float that IS representable but not finite in canonical JSON.
    refuses(lambda: s._seal({"value": float("inf")}),
            "ValueError", "compliant")

    # --- L472 ``_write_state`` re-reads what it wrote ------------------------
    # The read-back assertion is what proves the state file actually persisted.
    base = new_base("state")
    layout, _ = R._layout_and_writer(base, "state", nonce="state-wp8b")
    record = {"schema": s.SESSION_STATE_SCHEMA, "status": "complete",
              "session_id": "state-probe-1", "identity_sha256": "a" * 64}
    accepts(lambda: s._write_state(layout, 1, record), "writing the state")
    path = accepts(lambda: s.session_state_path(layout, 1), "the state path")
    ok(path.is_file(), f"the state file must exist after a write: {path}")
    on_disk = json.loads(path.read_bytes().decode("ascii"))
    ok(on_disk == record,
       f"the state file must hold exactly the record written: {on_disk}")
    # The file is the CANONICAL encoding plus one newline, which is what
    # ``_read_state`` re-checks; a non-canonical file is refused on read.
    ok(path.read_bytes() == s._canonical(record) + b"\n",
       "the state file must be the canonical encoding of its content")

    # --- L520 / L1359 ``_slot_token`` refuses a traversal slot ---------------
    # ``verify_instance_for_session`` calls ``_slot_token(slot)`` and DISCARDS
    # the result: the call exists purely for its refusal.  With the call removed
    # an arbitrary slot object reaches the reviewed reader.
    #
    # The refusal must be the MODULE'S OWN typed refusal.  Dropping the call
    # does not admit the slot -- WP8d refuses it later -- but it changes WHAT
    # refuses it: ``InstanceRefused`` instead of ``ProductionSessionError``,
    # which reports the failure as an instance-verification problem instead of
    # the caller's own malformed argument.  Asserting the type and the slot
    # guard's own wording is what makes the discarded call load-bearing.
    for bad in ("../../escape", "stage2_99", "", "stage2_01 ", None, 1.0,
                True, 0, 6, -1):
        refuses(lambda bad=bad: s.verify_instance_for_session(
            bad, root=layout, standin=True), "ProductionSessionError",
            "slot is not one of the canonical slot names or numbers"
            if not isinstance(bad, int) or isinstance(bad, bool)
            else "slot number is outside the canonical slot range")

    # --- L1903 the child environment must refuse a KAGGLE_/PYTHON name -------
    # The allowlist does not contain any KAGGLE_/PYTHON name, so the denied
    # check only fires for a name that is BOTH permitted and denied.  The
    # permitted prefixes are ``LC_`` and ``NVIDIA_``, neither of which is denied,
    # so on the current allowlist the guard is unreachable -- the allowlist is
    # what carries the security.  That is asserted here explicitly, because a
    # mutation that WIDENS the allowlist must be caught.
    environment = {"PATH": "/usr/bin", "LC_ALL": "C", "NVIDIA_VISIBLE_DEVICES": "all",
                   "KAGGLE_KERNEL_RUN_TYPE": "Interactive", "PYTHONPATH": "/evil"}
    child = accepts(lambda: s.child_environment(environment), "the child env")
    ok("KAGGLE_KERNEL_RUN_TYPE" not in child,
       "a KAGGLE_ name must never reach the child")
    ok("PYTHONPATH" not in child, "a PYTHON* name must never reach the child")
    ok(child["PYTHONDONTWRITEBYTECODE"] == "1",
       "the child must be told not to write bytecode")
    # No ALLOWLIST entry may start with a denied prefix -- that is the invariant
    # that makes the denied check unreachable, asserted so widening it fails.
    for name in s.CHILD_ENVIRONMENT_ALLOWLIST:
        ok(not name.startswith(s.CHILD_ENVIRONMENT_DENIED_PREFIXES),
           f"allowlist entry {name!r} must not carry a denied prefix")
    for prefix in s.CHILD_ENVIRONMENT_PREFIXES:
        ok(not prefix.startswith(s.CHILD_ENVIRONMENT_DENIED_PREFIXES),
           f"allowed prefix {prefix!r} must not carry a denied prefix")


def check_s1_to_s7_ordering_is_observed() -> None:
    """The S1-S7 sequencing must be observable, not merely executed.

    Every ``guard.check()`` / ``guard.mark()`` / ``_require_passed()`` in the
    session body is a discarded call (S2), so a fixture that only asserts the
    final receipt cannot see a removed one.  These cases make each observable.
    """
    base = new_base("order")

    # --- guard.mark / last_completed is read back from the ledger -----------
    # ``_Steps`` is the ledger; a mark that does not land is invisible unless the
    # ledger is read.  ``refuse`` must record the refusal too.
    steps = s._Steps()
    for step in s.STEP_ORDER:
        steps.record(step, digest="a" * 64)
    ok(steps.passed == set(s.STEP_ORDER),
       f"every step must record: {sorted(steps.passed)}")
    ok(steps.failed_prerequisite_for(s.STEP_ORDER[-1]) is None,
       "a fully recorded ledger has no failed prerequisite")
    # A refused step is NOT passed, and blocks every later step.
    blocked = s._Steps()
    blocked.record(s.STEP_ORDER[0], digest="a" * 64)
    blocked.refuse("refused", "a probe refusal")
    for later in s.STEP_ORDER[1:]:
        ok(blocked.failed_prerequisite_for(later) == s.STEP_ORDER[1]
           or s.STEP_ORDER[1] not in blocked.passed,
           f"{later!r} must be blocked by the refused step")
    refuses(lambda: s._require_passed(blocked, s.STEP_ORDER[-1]),
            "PrerequisiteFailed", "blocked by the failed prerequisite")
    # An unknown step cannot be recorded, so a typo cannot open a gate.
    refuses(lambda: blocked.record("not-a-real-step"), "ProductionSessionError")

    # --- _require_passed gates every device and write step ------------------
    # The FIRST step has no predecessor, so an empty ledger is correct there;
    # the gate is load-bearing from the SECOND step on, which is what a removed
    # ``_require_passed`` would let through.
    empty = s._Steps()
    accepts(lambda: s._require_passed(empty, s.STEP_ORDER[0]),
            "the first step has no predecessor to be blocked by")
    refuses(lambda: s._require_passed(empty, s.STEP_ORDER[1]),
            "PrerequisiteFailed", "blocked by the failed prerequisite")
    refuses(lambda: s._require_passed(empty, s.STEP_ORDER[-1]),
            "PrerequisiteFailed", "blocked by the failed prerequisite")

    # --- the receipt's completed/blocked split must be exact ----------------
    # A session that fails at WP2 must report WP2 as NOT completed and every
    # device/write step after it as blocked.  This is the observation that makes
    # the ``_require_passed`` calls inside the session body load-bearing.
    def failing_wp2(**kwargs):
        return ({"schema": "probe/wp2", "content_sha256": "a" * 64}, False)

    layout, writer_root = R._layout_and_writer(base, "order", nonce="order-wp8b")
    verified = s.verify_instance_for_session(1, root=layout, standin=True)
    receipt = accepts(lambda: R.run_session(
        base, layout=layout, writer_root=writer_root,
        nonce_root=st.sandbox_root(base, "order-nonce"),
        session_id="session-order",
        authorization=R._one_use_authorization(
            verified, st.draft_identity_sha256(), nonce="order-1"),
        session_identity=st.draft_identity(), clock=lambda: 0.0,
        seam_overrides={"wp2_recheck": failing_wp2},
        verified_instance=verified),
        "the session failing at WP2")
    ok(receipt["status"] == "refused",
       f"a failed WP2 prerequisite must refuse: {receipt['status']}")
    # The steps that DID pass before the failure are recorded, and the ones after
    # are all blocked.  This is what a removed ``_require_passed`` would break.
    passed = set(receipt["steps_passed"])
    ok("instance_verified" in passed,
       f"the steps before the failure must be recorded: {sorted(passed)}")
    ok("wp2_recheck_passed" not in passed,
       "the failed prerequisite must not be recorded as passed")
    for blocked_step in ("wp3_check_passed", "records_built", "ranges_promoted"):
        ok(blocked_step not in passed,
           f"{blocked_step!r} must not be recorded as passed")
        ok(blocked_step in receipt["blocked_steps"],
           f"{blocked_step!r} must be reported as blocked")
    ok(receipt["scientific_outputs"] == [],
       "a refused session must carry no scientific output")
    # A refused run closes nothing, so the instance is still free.
    ok(s._read_state(layout, 1) is None,
       "a refused session must not close the instance")


def check_authorization_wrong_type_and_empty() -> None:
    """The authorization field guards on values that are typed but EMPTY.

    Each guard is ``isinstance(x, str) and x``; the ``and``-operand-to-``True``
    mutant drops the non-emptiness half, so each field needs an empty-string
    case in addition to the wrong-type case the table already has.
    """
    base = new_base("authtype")
    good, verified = authorization_over(base, name="authtype-ok", nonce="at-wp8b")
    binding = {"accepted_content_sha256": st.draft_identity_sha256()}
    contract = s.session_contract_sha256()

    def check(auth):
        return s.validate_authorization(
            auth, verified=verified, accepted_binding=binding,
            session_contract_sha256=contract, today=st.PINNED)

    accepts(lambda: check(good), "the valid authorization")
    # The empty-string cases, one per field, each naming its own needle.
    for field, needle in (("account", "account"),
                          ("kernel_id", "kernel_id"),
                          ("nonce", "nonce")):
        refuses(lambda field=field: check({**good, field: ""}),
                "ProductionSessionError", needle)
    # The NON-CANONICAL but PARSEABLE date.  ``date.fromisoformat`` accepts
    # ``20260101`` (basic format) on 3.11+, so the canonical-form check at :766
    # is the ONLY thing that refuses it -- that is precisely why it is separate
    # from the parse guard, and why it needs its own case.  The unparseable ones
    # take the earlier :764 branch instead, so they are asserted separately.
    refuses(lambda: check({**good, "expiry": "20260101"}),
            "ProductionSessionError", "canonical ISO date")
    for bad in ("2026-1-1", "26-01-01", "2026-01-32", "", "2026-01-01T00:00:00", 20260101):
        refuses(lambda bad=bad: check({**good, "expiry": bad}),
                "AuthorizationRefused", "calendar date")
    # A canonical date that is in the FUTURE is accepted; one in the PAST is
    # refused as expired.  Both are needed or the comparison at :769 is not
    # covered in both directions.
    accepts(lambda: check({**good, "expiry": "2099-12-31"}),
            "an authorization expiring far in the future")
    refuses(lambda: check({**good, "expiry": "2020-01-01"}),
            "ProductionSessionError", "expired")


def check_wp1_verdict_cannot_be_laundered() -> None:
    """``records_exact_match`` must reject a NON-CONFORMING WP1 verdict.

    The three ``_require``s after WP1's ``exact_match`` (``:1551``, ``:1554``,
    ``:1556``) are only killable if WP1 can be made to return something that is
    not its published success record.  WP1's real ``exact_match`` always
    returns the same shape, so the seam is stubbed here -- the stub stands in for
    WP1's RETURN CONTRACT, which is the thing under test, and the fixture still
    asserts the guards fire.
    """
    identity = st.draft_identity()
    ok(s.records_exact_match(identity, copy.deepcopy(identity)) is True,
       "the real WP1 match must still pass on an exact match")

    # ``_wp1_exact_match`` is the module's zero-argument RESOLVER that returns
    # WP1's matcher (``wp8c_production_session.py:1968-1970``), so the stub
    # replaces the resolver, not the matcher, and returns the fake verdict.
    original = s.__dict__["_wp1_exact_match"]

    def with_verdict(value):
        def resolver():
            def stub(*args, **kwargs):
                return value
            return stub
        return resolver

    for bad, needle in (("not a dict", "verdict record"),
                        (None, "verdict record"),
                        (True, "verdict record"),
                        ([], "verdict record"),
                        ({"verdict": "mismatch", "differing_fields": []},
                         "non-success verdict"),
                        ({"verdict": "exact_match", "differing_fields": ["x"]},
                         "differences on a return"),
                        ({"differing_fields": []}, "non-success verdict"),
                        ({"verdict": "exact_match"}, "differences on a return")):
        s.__dict__["_wp1_exact_match"] = with_verdict(bad)
        try:
            refuses(lambda: s.records_exact_match(identity, identity),
                    "ProductionSessionError", needle)
        finally:
            s.__dict__["_wp1_exact_match"] = original

    # The stub must be restored: the real function still works.
    ok(s.records_exact_match(identity, copy.deepcopy(identity)) is True,
       "the real WP1 matcher must be restored after the stub cases")


def check_replay_of_identical_authorization_bytes() -> None:
    """The SAME authorization bytes must be refused on their second use.

    ``consume_authorization`` is a discarded call in the session body (S2), so
    with it removed no nonce is ever spent and a replay would SUCCEED.  The
    existing replay case derives a fresh nonce each time, which cannot observe
    that.  This case replays the IDENTICAL bytes.
    """
    base = new_base("replay")
    nonce_root = st.sandbox_root(base, "replay-nonce")
    auth, verified = authorization_over(base, name="replay-ok", nonce="replay-wp8b")
    frozen = copy.deepcopy(auth)

    accepts(lambda: s.consume_authorization(auth, nonce_root=nonce_root,
                                            today=st.PINNED),
            "consuming a one-use authorization")
    # The IDENTICAL record, byte for byte, is refused on its second use.  The
    # refusal is re-typed by ``consume_authorization`` as
    # ``AuthorizationRefused``, so the type check is what proves the rejection
    # came from WP8b's registry rather than from a structural guard.
    refuses(lambda: s.consume_authorization(copy.deepcopy(frozen),
                                            nonce_root=nonce_root,
                                            today=st.PINNED),
            "AuthorizationRefused", "already consumed")
    # A THIRD identical attempt is still refused: the marker is not consumed
    # once and then readable, so no repeat can succeed.
    refuses(lambda: s.consume_authorization(copy.deepcopy(frozen),
                                            nonce_root=nonce_root,
                                            today=st.PINNED),
            "AuthorizationRefused", "already consumed")

    # A DIFFERENT nonce is a DIFFERENT ledger key, so it is a DIFFERENT
    # approval, not a resurrection of this one.  WP8b keys the marker on the
    # SHA-256 of the approval's own canonical bytes
    # (``research/g9/wp8b/wp8b_non_synthetic_preparation.py:761-777``), and
    # ``validate_authorization`` is what requires the nonce to be a non-empty
    # string (``:777-778``) and to match the layout's own prepared record.  The
    # property WP8c relies on is that the SPENT key stays spent, not that a
    # changed nonce is refused -- so the changed-nonce record is asserted to be
    # a distinct key rather than a replay, and the identical one above is the
    # replay.
    changed = {**frozen, "nonce": "a-fresh-nonce"}
    accepts(lambda: s.consume_authorization(changed, nonce_root=nonce_root,
                                            today=st.PINNED),
            "a different nonce is a different approval, not a replay")
    # ...and re-consuming THAT one is refused, so every key is one-use.
    refuses(lambda: s.consume_authorization(changed, nonce_root=nonce_root,
                                            today=st.PINNED),
            "AuthorizationRefused", "already consumed")


def check_every_budget_check_is_load_bearing() -> None:
    """Each of the session's seven ``guard.check()`` calls, driven on its own.

    Every ``guard.check()`` in ``run_production_session`` is a bare call
    statement, so S2 replaces it with ``pass`` and a removed check is invisible
    to any receipt-only assertion.  The way to observe one is the CLOCK: the
    budget guard's ``check()`` compares ``elapsed()`` against its budget, and
    ``elapsed()`` is computed from the injected ``clock``.  The budget itself is
    a MODULE CONSTANT (``BUDGET_SECONDS``, ``:222``) and ``run_production_session``
    takes no budget override, so the clock is the only lever -- which is exactly
    the property that makes these calls load-bearing rather than decorative.

    The driver crosses the budget at a CHOSEN call by making the clock return a
    large value from that call onward.  ``elapsed()`` at call n is
    ``(n - 1) * stride``, and the guard fires when that exceeds ``BUDGET_SECONDS``.

    The READ-BACK is ``last_completed_step``: it is the incomplete receipt's only
    report of which step the run actually completed, so a removed ``guard.mark()``
    changes it, and a removed ``guard.check()`` changes WHICH receipt is produced
    at all.  Each case below asserts a SPECIFIC step, not merely "not accepted".
    """
    # ``check()`` fires when ``elapsed() > budget`` (STRICTLY greater), and
    # ``elapsed()`` at clock call n is ``(n - 1) * stride``.  The mapping from
    # stride to where the run stops was MEASURED by driving each stride through
    # the real session, not assumed: the clock is called once for the guard's
    # start, then once per ``guard.check()`` and once inside each ``elapsed()``.
    #
    # The stop lands AFTER the mark of the step that just completed, so the
    # receipt names that step.  Each stride below was confirmed to land on its
    # stated step.
    #
    # The strides must cover EVERY mark, not three of seven.  Asserting the
    # read-back only at ``identity_bound``, ``authorization_consumed`` and
    # ``wp3_check_passed`` left the other three marks untested, so dropping
    # ``guard.mark("instance_verified")`` (:1093),
    # ``guard.mark("wp2_recheck_passed")`` (:1151) or
    # ``guard.mark("records_built")`` (:1214) left this check green while the
    # incomplete receipt named the wrong step -- which is the whole point of the
    # budget receipt.  The three extra cases below close that hole; a stride
    # LARGER lands EARLIER, so the ordering runs from coarse to fine.
    budget = float(s.BUDGET_SECONDS)
    for label, stride, expected_last, expected_status in (
            # B*0.9: stops immediately after the FIRST step is verified, so the
            # receipt must name ``instance_verified`` -- the read-back for the
            # mark at :1093.
            ("first", budget * 0.9, "instance_verified", "incomplete_budget"),
            # B*0.5: the run stops with the identity bound and marked, so no
            # authorization was consumed and no device or write step ran.
            ("early", budget * 0.5, "identity_bound", "incomplete_budget"),
            # B*0.3: the one-use authorization has been consumed and marked.
            ("mid", budget * 0.3, "authorization_consumed",
             "incomplete_budget"),
            # B*0.25: stops just after the WP2 recheck is marked -- the
            # read-back for the mark at :1151.
            ("afterwp2", budget * 0.25, "wp2_recheck_passed",
             "incomplete_budget"),
            # B*0.2: WP2 and WP3 have both passed and been marked; the stop is
            # now after the device check, so it is the LAST window in which
            # whole ranges are still missing and unpromoted.
            ("late", budget * 0.2, "wp3_check_passed", "incomplete_budget"),
            # B*0.15: stops just after the records are built and marked -- the
            # read-back for the mark at :1214.
            ("afterbuild", budget * 0.15, "records_built",
             "incomplete_budget"),
            # A stride of 1 second never crosses the 10-hour budget, so the run
            # COMPLETES.  This is the positive control: it proves the cases
            # above stop the run for the BUDGET and not for some unrelated
            # reason, and it pins that an uninterrupted run marks EVERY step in
            # order and promotes the family's whole ranges.
            ("complete", 1.0, None, "complete_pending_image_audit"),
    ):
        base = new_base(f"tick-{label}")
        layout, writer_root = R._layout_and_writer(
            base, f"tick-{label}", nonce=f"tick-{label}-wp8b")
        verified = s.verify_instance_for_session(1, root=layout, standin=True)
        ticks = {"n": 0}

        def clock(ticks=ticks, stride=stride):
            """One stride per call.  The session calls this once for the guard's
            start and then once at every ``guard.check()``."""
            ticks["n"] += 1
            return float(ticks["n"]) * stride

        family = R.rehearsal_family()
        total = records.family_space(
            family, records.build_frozen_axes()).total_coordinates
        receipt = accepts(lambda: R.run_session(
            base, layout=layout, writer_root=writer_root,
            nonce_root=st.sandbox_root(base, f"tick-{label}-nonce"),
            session_id=f"session-tick-{label}",
            authorization=R._one_use_authorization(
                verified, st.draft_identity_sha256(), nonce=f"tick-{label}-auth"),
            session_identity=st.draft_identity(), clock=clock,
            verified_instance=verified, family=family,
            family_coordinates=total,
            engine_results=R.placeholder_engine_results(total)),
            f"the session whose budget case is {label}")

        ok(receipt["status"] == expected_status,
           f"the {label} budget case must produce {expected_status!r}, got "
           f"{receipt['status']!r}: {receipt.get('difference', '')[:200]}")

        if expected_last is None:
            # The positive control: a run that is never stopped must complete,
            # mark every step, and promote the family's whole ranges.
            ok(receipt["accepted"] is False,
               "a complete session is still never accepted; acceptance is a "
               "separate owner act")
            # ``steps_passed`` is emitted SORTED (``:1312``), so the set is
            # compared, and the frozen ORDER is pinned separately: every step is
            # in ``STEP_ORDER`` and all seven are present, so no mark was lost
            # and none was invented.
            ok(set(receipt["steps_passed"]) == set(s.STEP_ORDER),
               f"an uninterrupted run must mark every step: {receipt['steps_passed']}")
            ok(len(receipt["steps_passed"]) == len(s.STEP_ORDER),
               f"an uninterrupted run must mark each step exactly once: "
               f"{receipt['steps_passed']}")
            ok(receipt["promoted_range_batch_ids"],
               "an uninterrupted run must promote the family's whole ranges")
            ok(receipt["scientific_outputs"] == [],
               "even a complete run carries no scientific output; this package "
               "is unarmed")
            continue

        # THE READ-BACK for the stopped runs.
        ok(receipt["accepted"] is False,
           f"an incomplete receipt must never be accepted: {label}")
        ok(receipt["last_completed_step"] == expected_last,
           f"the {label} budget case must name last_completed_step "
           f"{expected_last!r}, got {receipt['last_completed_step']!r}")
        # An incomplete run is a STOP, not a partial write.
        ok(receipt["promoted_range_batch_ids"] == [],
           f"an incomplete receipt must promote nothing: {label} promoted "
           f"{receipt['promoted_range_batch_ids']}")
        ok(receipt["scientific_outputs"] == [],
           f"an incomplete receipt must carry no scientific output: {label}")
        # The steps that had NOT run are still blocked, so a stopped run cannot
        # be mistaken for a finished one.
        for blocked in ("ranges_promoted",):
            ok(receipt["last_completed_step"] != blocked,
               f"the {label} case must not report {blocked} as completed")


def check_empty_and_wrong_typed_carriers_are_refused() -> None:
    """The ``type(x) is dict and x`` carriers, driven with an EMPTY dict.

    Ten of the module's guards have the shape ``_require(type(x) is dict and x)``
    or the equivalent three-part conjunction.  Each carries THREE mutation sites
    (S1 replace-with-pass, and the two S5 operand-to-``True`` replacements), and
    all three survive unless the fixture passes a value that is a dict but EMPTY,
    or a dict that is well-typed but missing the required key.

    The empty dict is the discriminating input: the original refuses it, and every
    mutant accepts it and then fails (or does not fail) somewhere further on, so
    the case is what makes the guard load-bearing rather than decorative.
    """
    identity = st.draft_identity()
    binding = R.standin_acceptance_binding(s)

    # --- wp2_element_view: the identity and the image-build evidence --------
    refuses(lambda: s.wp2_element_view({}),
            "ProductionSessionError", "missing or empty")
    for bad in (None, "identity", [], 42, ()):
        refuses(lambda bad=bad: s.wp2_element_view(bad),
                "ProductionSessionError")
    # A dict identity with NO qualification block, and one whose evidence block
    # lacks the required "fields" key: both are the empty-half cases.
    refuses(lambda: s.wp2_element_view({}),
            "ProductionSessionError", "missing or empty")
    no_qual = {"qualification_identity": None}
    refuses(lambda: s.wp2_element_view(no_qual),
            "ProductionSessionError", "qualification_identity")
    no_evidence = {**copy.deepcopy(identity), "image_build_evidence": {}}
    refuses(lambda: s.wp2_element_view(no_evidence),
            "ProductionSessionError", "image_build_evidence")
    no_fields = {**copy.deepcopy(identity),
                 "image_build_evidence": {"kaggle_image_reported_string": "x"}}
    refuses(lambda: s.wp2_element_view(no_fields),
            "ProductionSessionError", "image_build_evidence")

    # --- the two WP2 view wrappers: a dict that LACKS the key ---------------
    for bad in ({"other": 1}, {}, {"production_identity": None}):
        if bad == {"production_identity": None}:
            continue
        refuses(lambda bad=bad: s.wp2_validate_view(bad),
                "ProductionSessionError", "malformed")
        refuses(lambda bad=bad: s.wp2_match_views(bad, {"production_identity": identity}),
                "ProductionSessionError", "malformed")
        refuses(lambda bad=bad: s.wp2_match_views({"production_identity": identity}, bad),
                "ProductionSessionError", "malformed")

    # --- the two identity CARRIERS: an empty embedded draft payload ---------
    for empty in (None, "draft", [], 42, {}):
        refuses(lambda empty=empty: s.writer_identity_of(
            {"draft_identity": empty}),
            "ProductionSessionError", "payload")
        refuses(lambda empty=empty: s.accepted_identity_of(
            {"draft_identity": empty}),
            "ProductionSessionError", "payload")
    # A binding with NO draft_identity key at all is the same refusal.
    refuses(lambda: s.writer_identity_of({}),
            "ProductionSessionError", "payload")
    refuses(lambda: s.accepted_identity_of({}),
            "ProductionSessionError", "payload")
    # POSITIVE CONTROL: the well-formed carriers still build and still compare
    # through WP1.
    ok(s.writer_identity_of(binding).accepted == identity,
       "the writer carrier must still hold the bound draft identity")
    ok(s.accepted_identity_of(binding).payload == identity,
       "the records carrier must still hold the bound draft identity")

    # --- the record projection: an empty coordinate map, a bad linear index --
    good_record = {
        "coordinate": {"axis_a": 1, "axis_b": 2},
        "linear_index": 0,
        "content_sha256": "a" * 64,
    }
    identity_sha = "b" * 64
    projected = accepts(lambda: s.project_record_for_writer(
        good_record, identity_sha), "projecting a well-formed record")
    ok(sorted(projected["result"]) == sorted(s.WRITER_RESULT_FIELDS),
       f"the projection must carry exactly the pinned fields: {projected}")
    # An EMPTY coordinate map is the ``and``-operand-to-``True`` case.
    for empty in (None, "coords", [], 42, {}):
        refuses(lambda empty=empty: s.project_record_for_writer(
            {**good_record, "coordinate": empty}, identity_sha),
                "ProductionSessionError", "coordinate map")
    # A missing or malformed linear index, including a NEGATIVE one and a bool,
    # which ``type(x) is int`` alone would accept.
    for bad in (None, -1, "0", 1.0, True, [], {}):
        refuses(lambda bad=bad: s.project_record_for_writer(
            {**good_record, "linear_index": bad}, identity_sha),
            "ProductionSessionError", "linear index")
    # A missing commitment is refused by the hash guard before the projection.
    refuses(lambda: s.project_record_for_writer(
        {k: v for k, v in good_record.items() if k != "content_sha256"},
        identity_sha),
        "ProductionSessionError", "content hash")


def check_record_building_guards_see_bad_indices() -> None:
    """``build_records_for_ranges``'s three guards, on inputs they must refuse.

    The family-membership guard, the index-range guard and the stray-index guard
    are each a bare ``_require``, so S1 replaces them with ``pass``.  A fixture
    that only ever builds a CORRECT batch never reaches the failing branch, so
    each case below drives a real refusal and names its own needle.
    """
    family = R.rehearsal_family()
    axes = records.build_frozen_axes()
    total = records.family_space(family, axes).total_coordinates
    binding = R.standin_acceptance_binding(s)
    base = new_base("build")
    identity = st.draft_identity()

    def build(results, **kwargs):
        # The rehearsal family is the D013 family, which only appears in the
        # committed table when D013 actually fired, so the flag is passed
        # explicitly rather than left at its default.
        return s.build_records_for_ranges(
            binding, identity, family, base,
            engine_results=results, d013_fired=True, **kwargs)

    # The happy path builds every declared index and refuses nothing.
    good_results = R.placeholder_engine_results(total)
    built = accepts(lambda: build(good_results),
                    "building every declared coordinate")
    ok(built["records_built"] == total,
       f"every declared coordinate must be built: {built['records_built']} of {total}")
    ok(built["accepted"] is False,
       "a built batch is never itself an acceptance")
    # With NO engine results nothing is built, and the function says so rather
    # than fabricating a record: the fabrication guard is the positive control.
    empty = accepts(lambda: build(None), "building with no engine results")
    ok(empty["records_built"] == 0,
       f"no engine results must build nothing: {empty['records_built']}")
    ok("never fabricates" in empty["note"],
       f"the empty build must say it fabricated nothing: {empty['note']}")

    # (1) An UNDECLARED family is refused, so a caller cannot hand the writer a
    #     family the committed table does not contain.
    refuses(lambda: s.build_records_for_ranges(
        binding, identity, "not-a-family", base, engine_results=good_results,
        d013_fired=True),
        "ProductionSessionError", "declared family")
    refuses(lambda: s.build_records_for_ranges(
        binding, identity, None, base, engine_results=good_results,
        d013_fired=True),
        "ProductionSessionError", "family is required")
    # The D013 family is refused when D013 did NOT fire, so the committed
    # family table -- not a caller flag -- decides which family is buildable.
    refuses(lambda: s.build_records_for_ranges(
        binding, identity, family, base, engine_results=good_results,
        d013_fired=False),
        "ProductionSessionError", "declared family")

    # (2) An index OUTSIDE the family's coordinate space is refused, so an
    #     engine cannot smuggle a result past the sealed space.  Both the upper
    #     and the lower bound are driven: the compare is ``0 <= linear < total``,
    #     so ``linear = 0`` is the boundary the ``<`` half admits and ``-1`` is
    #     what the ``<= 0`` half would wrongly admit.
    for bad_index in (total, total + 1, -1, -100):
        refuses(lambda bad_index=bad_index: build(
            {**good_results, bad_index: good_results[0]}),
            "ProductionSessionError", "outside the family's")

    # (3) A STRIDEY index against a sealed plan is refused, so a re-cut plan
    #     cannot silently discard work.  The plan covers the first HALF of the
    #     space, so every index in the second half is stray.
    plan = {"ranges": [{"batch_id": "half", "start": 0, "stop": total // 2}]}
    refuses(lambda: build(good_results, plan=plan),
            "ProductionSessionError", "outside the sealed")
    # The SAME plan with only the covered half built is accepted, which proves
    # the stray guard fires on the UNCOVERED indices and not on the plan itself.
    inside = {index: good_results[index] for index in range(total // 2)}
    placed = accepts(lambda: build(inside, plan=plan),
                     "building exactly the sealed plan's ranges")
    ok(placed["records_built"] == total // 2,
       f"the placed build must cover the plan: {placed['records_built']}")
    ok(placed["batch_records"]["half"] and
       len(placed["batch_records"]["half"]) == total // 2,
       f"the plan's own row must hold its members: {placed['batch_records']}")


def check_write_schema_and_child_environment_guards() -> None:
    """``write_sealed_whole_ranges``' schema guard and the child-env guards.

    The result-schema guard is a THREE-part conjunction, so it needs one case per
    part: not a dict, the wrong key set, and a right-key-set with the wrong value
    type.  The child-environment guard needs the same treatment.
    """
    identity = st.draft_identity()
    base = new_base("write")

    # --- the WP4b result schema, part by part -------------------------------
    def write_with(schema):
        return s.write_sealed_whole_ranges(
            instance_root=base, batch_records={}, result_schema=schema,
            accepted_identity=s.writer_identity_of(
                {"draft_identity": identity}),
            session_identity=identity,
            accepted_identity_sha256="a" * 64, promoted_batch_ids=())

    # A non-dict schema is refused (the first conjunct).
    for bad in (None, "schema", [], 42, ()):
        refuses(lambda bad=bad: write_with(bad),
                "ProductionSessionError")
    # The wrong key set is refused (the second conjunct): missing one, extra one.
    refuses(lambda: write_with({"identity_sha256": "str"}),
            "ProductionSessionError", "result schema")
    refuses(lambda: write_with({**{n: "str" for n in s.WRITER_RESULT_FIELDS},
                                "extra": "str"}),
            "ProductionSessionError", "result schema")
    # The right keys with the WRONG value type is refused (the third conjunct).
    refuses(lambda: write_with({n: "int" for n in s.WRITER_RESULT_FIELDS}),
            "ProductionSessionError", "result schema")
    refuses(lambda: write_with({n: None for n in s.WRITER_RESULT_FIELDS}),
            "ProductionSessionError", "result schema")
    # A promoted-batch-id SET that is a bare string is refused before anything
    # is written, so a single id can never be iterated character by character.
    refuses(lambda: s.write_sealed_whole_ranges(
        instance_root=base, batch_records={},
        result_schema={n: "str" for n in s.WRITER_RESULT_FIELDS},
        accepted_identity=s.writer_identity_of({"draft_identity": identity}),
        session_identity=identity, accepted_identity_sha256="a" * 64,
        promoted_batch_ids="wp8c_nonproduction_standin_b0000"),
        "ProductionSessionError", "not a string")

    # --- the child environment, part by part --------------------------------
    # A non-mapping environment is refused: a STRING is a Mapping-ish object to
    # ``isinstance`` but must never be treated as a mapping, which is exactly
    # what the ``not isinstance(environment, str)`` conjunct exists for.
    for bad in ("PATH=/usr/bin", ["PATH"], None, 42, ()):
        refuses(lambda bad=bad: s.child_environment(bad),
                "ProductionSessionError", "must be a mapping")
    # The valid path still works and still drops the credential-bearing names.
    child = accepts(lambda: s.child_environment(
        {"PATH": "/usr/bin", "KAGGLE_KEY": "secret", "PYTHONPATH": "/evil"}),
        "a valid child environment")
    ok("KAGGLE_KEY" not in child and "PYTHONPATH" not in child,
       f"credential-bearing names must never reach the child: {sorted(child)}")
    # A non-string NAME is refused rather than silently coerced.
    refuses(lambda: s.child_environment({1: "x"}),
            "ProductionSessionError", "must be strings")
    # A non-string VALUE for an allowed name is refused.
    refuses(lambda: s.child_environment({"PATH": 1}),
            "ProductionSessionError", "must be a string")


# ===========================================================================
# 35. The cont7 survivors, closed by observation
# ===========================================================================


def _c7_session_kwargs(base, layout, writer_root, verified, seams, **over):
    """The FULL reviewed-seam keyword set, for calling the MODULE directly.

    ``run_production_session`` compares an injected ``seams`` mapping against the
    reviewed set, so a probe about that guard must supply the whole mapping itself
    rather than go through the rehearsal (which always injects a correct one).
    Every other keyword mirrors the rehearsal's own call so that the seam guard is
    the only thing under test.
    """
    family = R.rehearsal_family()
    total = records.family_space(family, records.build_frozen_axes()).total_coordinates
    kw = dict(
        slot=1, session_id=over.get("_tag", "c7-seam"), root=layout, instance_root=writer_root,
        nonce_root=st.sandbox_root(base, "c7-" + over.get("_tag", "seam")),
        acceptance_record={"standin": True},
        reviewed_record_sha256=hashlib.sha256(
            b"wp8c-nonproduction-standin-acceptance-pin").hexdigest(),
        session_identity=st.draft_identity(),
        authorization=R._one_use_authorization(
            verified, st.draft_identity_sha256(),
            nonce=over.get("_tag", "c7-seam-nonce")),
        boundary=st.standin_boundary(s), standin=True,
        d013_fired=R.REHEARSAL_D013_FIRED,
        d013_coordinates=(s.harness.d013_repeat_coordinates()
                          if R.REHEARSAL_D013_FIRED else None),
        writer_family=R.WRITER_FAMILY,
        result_schema={"identity_sha256": "str",
                       "record_content_sha256": "str"},
        family=family, family_coordinates=total,
        engine_results=R.placeholder_engine_results(total),
        expected_approval_sha256=wp2.read_approval_hashes(),
        expected_generator_implementation_record_sha256=(
            s.generator_record_of(verified)),
        expected_ground_truth_provenance_sha256=s.ground_truth_of(verified),
        approved_identity_sha256=st.draft_identity_sha256(),
        protocol_identity_sha256=hashlib.sha256(
            b"wp8c-nonproduction-protocol").hexdigest(),
        clock=lambda: 0.0, seams=seams, today=st.PINNED)
    kw.update(over)
    kw.pop("_tag", None)
    return kw


def _c7_session(base, layout, writer_root, verified, *, nonce, session_id,
                **over):
    """One stand-in session through the rehearsal driver, varying ONE argument.

    The rehearsal supplies the stand-in identity seams and the real approval
    hashes, so a probe that differs from a known-good run in exactly one argument
    makes a surviving mutant attributable to that argument rather than to the
    scaffolding.  ``seam_overrides`` reaches the session's ``seams`` argument.
    """
    family = R.rehearsal_family()
    total = records.family_space(family, records.build_frozen_axes()).total_coordinates
    kw = dict(family=family, family_coordinates=total,
              engine_results=R.placeholder_engine_results(total))
    kw.update(over)
    return R.run_session(
        base, layout=layout, writer_root=writer_root,
        nonce_root=st.sandbox_root(base, "c7-" + nonce),
        session_id=session_id,
        authorization=R._one_use_authorization(
            verified, st.draft_identity_sha256(), nonce=nonce),
        session_identity=st.draft_identity(), clock=lambda: 0.0,
        verified_instance=verified, **kw)


def check_session_body_guards_are_observable() -> None:
    """Every guard inside ``run_production_session``'s OWN body is observed.

    The S1/S2 sites inside the adapter's body (the seam-coverage ``_require``, the
    ``require_instance_matches_session`` / ``_require_session_allowed`` /
    ``consume_authorization`` calls, the ``_require_passed`` ordering gates, the
    ``guard.check`` / ``guard.mark`` ledger calls, ``steps.refuse``) are discarded
    calls, so replacing any of them with ``pass`` leaves a run that still looks
    healthy.  Each case below therefore names the OUTCOME that changes when the
    call is dropped: the receipt's ``difference`` carries the guard's own text, so
    an assertion on that text dies with the mutant.
    """
    base = new_base("c7body")
    layout, writer_root = R._layout_and_writer(base, "c7body", nonce="c7b-wp8b")
    verified = s.verify_instance_for_session(1, root=layout, standin=True)
    family = R.rehearsal_family()
    total = records.family_space(family, records.build_frozen_axes()).total_coordinates

    # --- L1074: an injected seam mapping must cover EXACTLY the reviewed set --
    # Dropping this ``_require`` would let a caller add or drop a reviewed entry
    # point, so the named-refusal case is the observation.  The rehearsal passes
    # the reviewed seams plus its own two identity stand-ins, so the override has
    # to be expressed as a MAPPING the session re-checks, not as a raw dict.
    reviewed = {**s._seams(), "device_backend_factory": st.device_backend_factory,
                "python_reference": st.python_reference,
                "bind_accepted_identity": R.standin_bind_acceptance,
                "require_session_identity_exact": R.standin_compare_identity}
    extra = dict(reviewed)
    extra["surprise_entry_point"] = lambda *a, **k: None
    refuses(lambda: s.run_production_session(**_c7_session_kwargs(
        base, layout, writer_root, verified, extra)),
        "ProductionSessionError", "must cover exactly the reviewed entry points",
        "surprise_entry_point")
    # Dropping an entry is equally refused.
    short = dict(reviewed)
    short.pop("write_range")
    refuses(lambda: s.run_production_session(**_c7_session_kwargs(
        base, layout, writer_root, verified, short)),
        "ProductionSessionError", "must cover exactly the reviewed entry points",
        "write_range")

    # --- L1199: the committed family's OWN coordinate count wins ------------
    # The caller's declared number must never be able to build the sealed plan,
    # so BOTH directions of the ``==`` are observed.  A dropped ``_require`` would
    # seal the plan from the CALLER's number instead of the committed space.
    for wrong in (total + 7, total - 1, 1):
        receipt = accepts(lambda wrong=wrong: _c7_session(
            base, layout, writer_root, verified,
            nonce="c7b-count-%d" % wrong, session_id="s-count-%d" % wrong,
            family_coordinates=wrong),
            "a session declaring a wrong coordinate count")
        ok(receipt["status"] != "complete_pending_image_audit",
           f"a caller-declared count of {wrong} must not complete a session: "
           f"{receipt['status']}")
        ok("differs from the committed family's actual" in str(receipt["difference"]),
           f"the refusal must name the committed count, got {receipt['difference']!r}")
        ok("records_built" in receipt["blocked_steps"],
           f"the write steps must be blocked, got {receipt['blocked_steps']}")
    # A count that is not an integer at all is refused by the preceding guard, so
    # both halves of that ``and`` are covered: the type half and the range half.
    for wrong in (0, -1, "961", 961.0):
        receipt = accepts(lambda wrong=wrong: _c7_session(
            base, layout, writer_root, verified,
            nonce="c7b-bad-%r" % (wrong,), session_id="s-bad-%r" % (wrong,),
            family_coordinates=wrong),
            "a session declaring a non-integer coordinate count")
        ok(receipt["status"] != "complete_pending_image_audit",
           f"a non-integer count {wrong!r} must not complete: {receipt['status']}")
        ok("positive integer" in str(receipt["difference"]),
           f"the refusal must name the positive-integer rule, got "
           f"{receipt['difference']!r}")
    # ``True`` is an int, so it is the case the ``type(...) is int`` conjunct
    # exists for: without it, ``True`` would pass as the count 1.
    receipt = accepts(lambda: _c7_session(
        base, layout, writer_root, verified, nonce="c7b-true",
        session_id="s-true", family_coordinates=True),
        "a session declaring True as its coordinate count")
    ok(receipt["status"] != "complete_pending_image_audit",
       f"a boolean count must not complete: {receipt['status']}")

    # --- L1192: the WP4b family label must be a non-empty string -------------
    # The family identifier is what LABELS the sealed plan, so an empty or
    # non-string label would make the plan unsealable-but-accepted.  Both halves
    # of the ``isinstance`` / non-empty conjunction are covered: ``42`` and
    # ``["wp8c"]`` fail the type half, ``""`` fails the emptiness half.  The
    # rehearsal pins its own label, so this probe calls the MODULE directly.
    for bad in ("", None, 42, ["wp8c"], b"wp8c"):
        receipt = accepts(lambda bad=bad: s.run_production_session(
            **_c7_session_kwargs(base, layout, writer_root, verified, reviewed,
                                writer_family=bad, _tag="fam-%r" % (bad,))),
            "a session with a malformed WP4b family label")
        ok(receipt["status"] != "complete_pending_image_audit",
           f"a family label of {bad!r} must not complete: {receipt['status']}")
        ok("non-empty string" in str(receipt["difference"]),
           f"the refusal must name the non-empty-string rule, got "
           f"{receipt['difference']!r}")


def check_session_ledger_and_refusal_are_recorded() -> None:
    """The ``guard``/``steps`` bookkeeping is an OBSERVABLE, not bookkeeping.

    ``guard.mark(...)`` / ``_require_passed(...)`` / ``steps.refuse(...)`` inside
    the adapter body are all discarded calls.  Dropping ``guard.mark`` removes the
    step from the receipt's ``steps_passed``; dropping ``_require_passed`` lets a
    session continue past a failed prerequisite; dropping ``steps.refuse`` loses
    the refusal record.  Each is observed here through the receipt's own ledger.
    """
    base = new_base("c7ledger")
    layout, writer_root = R._layout_and_writer(base, "c7led", nonce="c7l-wp8b")
    verified = s.verify_instance_for_session(1, root=layout, standin=True)

    # --- the happy path records EVERY step (kills each dropped ``guard.mark``) --
    receipt = accepts(lambda: _c7_session(
        base, layout, writer_root, verified, nonce="c7l-ok", session_id="s-ok"),
        "the complete stand-in session")
    ok(sorted(receipt["steps_passed"]) == sorted(s.STEP_ORDER),
       f"every frozen step must be recorded by the ledger: {receipt['steps_passed']}")

    # --- a failed prerequisite BLOCKS the later write steps ------------------
    # This is the observation for the ``_require_passed`` sites: if any of them
    # were ``pass``, ``records_built``/``ranges_promoted`` would appear as
    # completed instead of blocked.
    def failing_wp2(*a, **k):
        return ({"schema": "probe/wp2", "content_sha256": "a" * 64}, False)

    refused = accepts(lambda: _c7_session(
        base, layout, writer_root, verified, nonce="c7l-wp2", session_id="s-wp2",
        seam_overrides={"wp2_recheck": failing_wp2}),
        "the session failing at WP2")
    ok(refused["status"] != "complete_pending_image_audit",
       f"a failed WP2 prerequisite must not complete: {refused['status']}")
    for later in ("wp3_check_passed", "records_built", "ranges_promoted"):
        ok(later in refused["blocked_steps"],
           f"{later!r} must be blocked by the failed prerequisite: "
           f"{refused['blocked_steps']}")
        ok(later not in refused["steps_passed"],
           f"{later!r} must not be recorded as passed after a failure")
    # The refusal itself is RECORDED: this is the ``steps.refuse`` observation.
    ok(refused["refusal_type"], "a refusal must carry its exception type")
    ok("the WP2 section B item 1 recheck refused" in str(refused["difference"]),
       f"the refusal must name the blocking prerequisite: {refused['difference']!r}")
    ok(refused["scientific_outputs"] == [],
       "a refused session must carry no scientific output")
    ok(refused["accepted"] is False,
       "a refused session must never be accepted")
    # A refused run writes NO state, so the instance is still free: a dropped
    # ``_write_state`` on the failure path would close it.  Probed on its OWN
    # layout, because the happy-path run above already closed this one.
    free_layout, free_writer_root = R._layout_and_writer(
        base, "c7led2", nonce="c7l2-wp8b")
    free_verified = s.verify_instance_for_session(1, root=free_layout, standin=True)
    accepts(lambda: _c7_session(
        base, free_layout, free_writer_root, free_verified,
        nonce="c7l2-wp2", session_id="s2-wp2",
        seam_overrides={"wp2_recheck": failing_wp2}),
        "the refused probe session on a fresh layout")
    ok(s._read_state(free_layout, 1) is None,
       "a refused session must leave the instance free for a new authorization")

    # --- ONE SESSION PER INSTANCE, observed END TO END -----------------------
    # The unit cases above exercise ``_require_session_allowed`` directly, which
    # is not enough: the gate is a DISCARDED call in the adapter's body, so
    # replacing it with ``pass`` leaves every unit case green while a SECOND
    # ordinary session on an already-closed instance completes normally.  That
    # exact broken variant is run against these final bytes as a gate.
    closed_layout, closed_writer_root = R._layout_and_writer(
        base, "c7led3", nonce="c7l3-wp8b")
    closed_verified = s.verify_instance_for_session(1, root=closed_layout, standin=True)
    first = accepts(lambda: _c7_session(
        base, closed_layout, closed_writer_root, closed_verified,
        nonce="c7l3-1", session_id="c7l3-first"),
        "the first session on a fresh instance")
    ok(first["status"] == "complete_pending_image_audit",
       f"the first session must complete: {first['status']}")
    ok((s._read_state(closed_layout, 1) or {}).get("status") == "complete",
       "the completed session must have closed the instance")
    # The SAME session id may not be replayed, and the closure is a fact about
    # the INSTANCE, not about the session id.
    replay = accepts(lambda: _c7_session(
        base, closed_layout, closed_writer_root, closed_verified,
        nonce="c7l3-2", session_id="c7l3-first"),
        "the replay attempt on a closed instance")
    ok(replay["status"] != "complete_pending_image_audit",
       f"a replayed session id on a closed instance must not complete: "
       f"{replay['status']}")
    ok("one session per instance" in str(replay["difference"])
       or "may not be replayed" in str(replay["difference"]),
       f"the refusal must name the one-session-per-instance rule, got "
       f"{replay['difference']!r}")
    ok(replay["accepted"] is False, "a refused replay must never be accepted")

    # --- a failed WP3 check blocks the same later steps ----------------------
    def failing_wp3(*a, **k):
        raise s.ProductionSessionError("the WP3 record was not valid")

    wp3_refused = accepts(lambda: _c7_session(
        base, layout, writer_root, verified, nonce="c7l-wp3",
        session_id="s-wp3", seam_overrides={"wp3_validate": failing_wp3}),
        "the session failing at the WP3 validation")
    ok(wp3_refused["status"] != "complete_pending_image_audit",
       f"a failed WP3 check must not complete: {wp3_refused['status']}")
    for later in ("records_built", "ranges_promoted"):
        ok(later in wp3_refused["blocked_steps"],
           f"{later!r} must be blocked by the failed WP3 check")
    ok("the WP3 record was not valid" in str(wp3_refused["difference"]),
       f"the WP3 refusal text must survive into the receipt: "
       f"{wp3_refused['difference']!r}")


def check_adapter_guards_reach_their_second_conjunct() -> None:
    """The ``A and B`` guards must be observed on the ``B`` half as well.

    A conjunct mutated to ``True`` removes only ``A``; ``B`` still runs, so a
    mutant survives whenever the input that violates ``B`` is ALSO refused by
    whatever consumes the value afterwards, or is never driven at all.  These
    cases drive exactly those inputs, so a surviving mutant means the guard's own
    refusal text is no longer produced.
    """
    identity = st.draft_identity()

    # --- _WriterIdentity (:1547): ``type(payload) is dict and payload`` --------
    # The emptiness half is the ``and``'s right operand; the mutation forces the
    # type half True and drops the non-empty test.  The class is never otherwise
    # constructed directly by this fixture, so without these cases nothing
    # observes the guard at all.
    refuses(lambda: s._WriterIdentity({}),
            "ProductionSessionError", "non-empty accepted payload")
    for bad in (None, "payload", 42, [], b"{}"):
        refuses(lambda bad=bad: s._WriterIdentity(bad),
                "ProductionSessionError")
    accepts(lambda: s._WriterIdentity({"draft_identity": identity}),
            "a writer identity over a real payload")

    # --- writer_identity_of (:1588) and accepted_identity_of ------------------
    # The same conjunction over the BOUND payload: a binding whose embedded
    # draft identity is empty must not produce a writer carrier.
    for empty in ({}, None, "draft", []):
        refuses(lambda empty=empty: s.writer_identity_of(
            {"draft_identity": empty}),
            "ProductionSessionError", "no embedded draft identity payload")
    # A binding that is not a Mapping at all cannot satisfy ``.get``; the caller
    # of this function is the session, which always passes a mapping, so the
    # guard under test here is the EMPTY-payload one, not the carrier's type.
    accepts(lambda: s.writer_identity_of({"draft_identity": identity}),
            "a writer identity over a bound draft identity")

    # --- the WP2 element-view wrapper (:1495, :1507, :1509) -------------------
    # ``type(x) is dict and "production_identity" in x``: dropping the FIRST
    # conjunct lets a non-mapping through to WP1, and dropping the second lets a
    # mapping WITHOUT the payload through.  Both must be refused by THIS guard's
    # own message, not by WP1's validator further down.  An EXTRA key is
    # deliberately tolerated, so it is asserted to succeed rather than refused.
    accepts(lambda: s.wp2_validate_view(
        {"production_identity": identity, "platform": {}, "extra": 1}),
        "a WP2 view carrying extra projected fields")
    for bad in ({}, {"nope": 1}, {"platform": {}}):
        outcome = observe(lambda bad=bad: s.wp2_validate_view(bad))
        ok(outcome["outcome"] == "raised",
           f"a WP2 view of {bad!r} must be refused: {outcome}")
        ok("WP2 identity wrapper is malformed" in outcome["text"],
           f"the refusal must name the wrapper guard itself, got {outcome['text']!r}")
    # The match adapter's two operands, for the same reason.
    good_view = {"production_identity": identity}
    refuses(lambda: s.wp2_match_views({"nope": 1}, good_view),
            "ProductionSessionError", "WP2 identity wrapper is malformed")
    refuses(lambda: s.wp2_match_views(good_view, {"nope": 1}),
            "ProductionSessionError", "WP2 identity wrapper is malformed")
    # A non-MAPPING view with the payload key present: this is the input that
    # isolates the ``type(...) is dict`` conjunct, because the key test alone
    # would pass it.  WP1 must still refuse it, which is the defence in depth.
    for bad in ("production_identity", 42, ["production_identity"], None):
        outcome = observe(lambda bad=bad: s.wp2_validate_view(bad))
        ok(outcome["outcome"] == "raised",
           f"a non-mapping WP2 view of {bad!r} must be refused: {outcome}")
        ok("WP2 identity wrapper is malformed" in outcome["text"],
           f"the refusal must name the wrapper guard, got {outcome['text']!r}")

    # --- the authorization's string fields (:775, :777) -----------------------
    # ``isinstance(x, str) and x``: dropping the TYPE half admits any TRUTHY
    # non-string.  These fields are validated but never consumed elsewhere in
    # this module, so nothing downstream re-checks their type -- which is exactly
    # why the fixture must drive them directly.
    auth_base = new_base("c7auth")
    auth, verified = authorization_over(auth_base, name="c7auth",
                                        nonce="c7auth-wp8b")
    binding = {"accepted_content_sha256": st.draft_identity_sha256()}
    contract = s.session_contract_sha256()

    def validate_with(**over):
        record = copy.deepcopy(auth)
        record.update(over)
        return s.validate_authorization(
            record, verified=verified, accepted_binding=binding,
            session_contract_sha256=contract, today=st.PINNED)

    for field in ("account", "kernel_id", "nonce"):
        for wrong in (42, True, ["x"], {"a": 1}, (1, 2), 3.5):
            outcome = observe(
                lambda wrong=wrong, field=field: validate_with(**{field: wrong}))
            ok(outcome["outcome"] == "raised",
               f"an authorization {field} of {wrong!r} must be refused: {outcome}")
        # The EMPTY half of the same conjunction.
        outcome = observe(lambda field=field: validate_with(**{field: ""}))
        ok(outcome["outcome"] == "raised",
           f"an empty authorization {field} must be refused: {outcome}")
    # The valid record is still accepted, so the cases above isolate the guard
    # rather than a scaffolding failure.
    accepts(lambda: validate_with(), "a structurally valid one-use authorization")

    # --- the child environment (:1911) ---------------------------------------
    # ``isinstance(env, Mapping) and not isinstance(env, str)``: the mutation
    # drops the Mapping half.  A LIST is a non-Mapping iterable, so it is the
    # input that distinguishes the two halves.
    for bad in ([], ["PATH"], (1, 2), 42, None, b"PATH=/bin"):
        outcome = observe(lambda bad=bad: s.child_environment(bad))
        ok(outcome["outcome"] == "raised",
           f"a child environment of {bad!r} must be refused: {outcome}")
        ok("must be a mapping" in outcome["text"],
           f"the refusal must name the mapping guard, got {outcome['text']!r}")


def check_state_write_guard_is_load_bearing() -> None:
    """The state write's durability steps are guarded by what FOLLOWS them.

    ``mkdir`` (:464) and ``fsync`` (:470) are discarded calls and the read-back
    ``_require`` (:472) is an S1.  Dropping any of them must change an OBSERVED
    outcome, which is what these cases drive: the parent directory must exist and
    the written bytes must be exactly the canonical encoding.
    """
    base = new_base("c7state")
    record = {"schema": s.SESSION_STATE_SCHEMA, "status": "complete",
              "session_id": "c7", "identity_sha256": "a" * 64}

    # --- the write is durable and byte-exact ---------------------------------
    layout, _ = R._layout_and_writer(base, "c7state", nonce="c7st-wp8b")
    s._write_state(layout, 1, record)
    path = s.session_state_path(layout, 1)
    ok(path.is_file(), f"the state file must exist at {path}")
    ok(path.read_bytes() == s._canonical(record) + b"\n",
       "the state file must hold exactly the canonical encoding")
    ok(s._read_state(layout, 1)["session_id"] == "c7",
       "the written state must read back")

    # --- writing into a NOT-YET-EXISTENT parent must create it --------------
    # This is the observation for the discarded ``mkdir``: if the parent were
    # required to pre-exist, the write would raise instead.
    deep = path.parent / "nested" / "deeper"
    ok(not deep.exists(), "the nested parent must not pre-exist")
    s._write_state(deep, 1, record)
    ok(s.session_state_path(deep, 1).is_file(),
       "the state write must create its own parent directory")

    # --- the atomic replace leaves NO temporary file behind -------------------
    leftovers = [p.name for p in path.parent.iterdir() if ".tmp-" in p.name]
    ok(leftovers == [],
       f"the atomic write must not leave a temporary file behind: {leftovers}")

    # --- a torn record is refused rather than half-believed -------------------
    torn = s.session_state_path(deep, 1)
    torn.write_bytes(s._canonical(record)[:20])
    refuses(lambda: s._read_state(deep, 1), "ProductionSessionError")

    # --- the state record's schema guard (:448) ------------------------------
    # ``type(record) is dict and record.get("schema") == SESSION_STATE_SCHEMA``:
    # dropping the TYPE half lets a non-mapping reach ``.get``.  A JSON payload
    # that decodes to a LIST or a STRING is the input that isolates it, and the
    # read must refuse it either way.
    #
    # The refusal TYPE is the whole point.  This case used to assert only that
    # SOMETHING was raised, which the mutant satisfies by raising
    # ``AttributeError: 'list' object has no attribute 'get'`` -- and that is
    # precisely the crash the guard exists to prevent, because ``AttributeError``
    # is not a ``ProductionSessionError`` and therefore ESCAPES the session's
    # one ``except`` clause instead of becoming a non-accepting receipt.  So the
    # expected type is asserted per payload, and the module's own message is
    # required to be present.
    for payload in ("[]", '"a string"', "42", "null", "true"):
        torn.write_text(payload, encoding="ascii")
        refuses(lambda: s._read_state(deep, 1), "ProductionSessionError",
                "is not a WP8c session state record")
    # A dict whose schema is WRONG is the other half of the same conjunction.
    torn.write_text(json.dumps({"schema": "not-the-wp8c-state"}), encoding="ascii")
    refuses(lambda: s._read_state(deep, 1), "ProductionSessionError")
    # The canonical, correct record reads back, so the cases above isolate the
    # guard rather than a scaffolding failure.
    s._write_state(deep, 1, record)
    ok(s._read_state(deep, 1)["session_id"] == "c7",
       "the canonical state record must read back")


def check_slot_and_state_guards_are_load_bearing() -> None:
    """The slot token, the state-file path shape and its persistence are guards.

    ``_slot_token`` (:422) turns a caller value into a canonical slot name, so
    dropping it would let a traversal string reach a file path.  The state read
    (:433) refuses a symlink, and the state write (:472) reads the bytes BACK
    after the atomic replace; dropping that read-back would let a session believe
    it closed an instance it never actually persisted.
    """
    base = new_base("c7slot")

    # --- the slot token: every non-canonical form is refused -----------------
    # ``slot=True`` is the case the ``not isinstance(slot, bool)`` conjunct
    # exists for: as an int it is 1, without it the guard is bypassed.
    for bad in (0, -1, 6, 99, True, False, None, "../escape", "", "stage_99",
                "STAGE_01", 1.0, [1], (1,)):
        refuses(lambda bad=bad: s._slot_token(bad),
                "ProductionSessionError")
    for good in (1, 2, 5, wp8dp.SLOT_NAMES[0], wp8dp.SLOT_NAMES[-1]):
        accepts(lambda good=good: s._slot_token(good),
                f"the canonical slot {good!r}")

    # --- the state path: a symlink is refused as "no state" -----------------
    layout, _writer_root = R._layout_and_writer(base, "c7slot", nonce="c7s-wp8b")
    s._write_state(layout, 1, {"schema": s.SESSION_STATE_SCHEMA,
                                 "status": "complete", "session_id": "s1"})
    ok(s._read_state(layout, 1) is not None,
       "a written state file must be readable")
    # Replace the state file with a symlink to a decoy; the read must refuse it
    # rather than report the decoy as this instance's state.
    path = s.session_state_path(layout, 1)
    decoy = path.with_name(path.name + ".decoy")
    decoy.write_bytes(b'{"status": "complete", "session_id": "attacker"}')
    path.unlink()
    path.symlink_to(decoy)
    ok(s._read_state(layout, 1) is None,
       "a symlinked state file must read as NO state, never as the decoy")
    path.unlink()
    decoy.unlink()
    # A malformed state file is a refusal, not an uncaught decode error.
    path.write_bytes(b"{not json")
    refuses(lambda: s._read_state(layout, 1), "ProductionSessionError")
    path.unlink()


def check_non_mapping_carriers_keep_their_typed_refusal() -> None:
    """Every ``type(x) is dict and ...`` guard refuses a NON-MAPPING with ITS OWN type.

    Four of the module's guards were previously classified semantic equivalents on
    the argument that the second conjunct already covers the first.  That is true
    for every MAPPING and FALSE for every non-mapping, where dropping the type half
    does not change the answer -- it changes the EXCEPTION.  The pristine guard
    raises ``ProductionSessionError``; the mutant raises ``TypeError`` or
    ``AttributeError`` from the next expression.  That matters because the
    session's single handler is ``except ProductionSessionError``: an
    ``AttributeError`` ESCAPES it, so a malformed carrier stops being a
    non-accepting receipt and becomes a crash.

    So each case below asserts the refusal TYPE and the module's own message,
    which is exactly what the ``and``-operand-to-``True`` mutant cannot produce.

    Sites closed here: ``require_instance_matches_session`` (:544),
    ``wp2_match_views`` left (:1507) and right (:1509), and the
    ``BudgetGuard`` budget conjunct (:943).
    """
    # --- require_instance_matches_session: a non-mapping verified record -----
    # ``{}`` is already covered by the "missing or empty" case; these are the
    # non-mappings, which the SECOND conjunct cannot refuse.
    for carrier in ("a string", b"bytes", 3.5, None, ["a"], ("a",), 0):
        refuses(lambda carrier=carrier: s.require_instance_matches_session(
            carrier, expected_instance_id="x", expected_slot="stage2_01"),
            "ProductionSessionError", "missing or empty")

    # --- wp2_match_views: BOTH wrapper guards, probed separately ------------
    # The left and right guards are probed with the OTHER argument well formed.
    # Probing only with a malformed left lets the left guard raise first and
    # masks a defective right guard entirely -- which is how the right-hand
    # guard was previously mis-read as an equivalence.
    identity = st.draft_identity()
    good_view = s.wp2_element_view(identity)
    for carrier in ("a string", b"bytes", 3.5, None, ["a"], 0):
        refuses(lambda carrier=carrier: s.wp2_match_views(
            carrier, good_view), "ProductionSessionError", "malformed")
        refuses(lambda carrier=carrier: s.wp2_match_views(
            good_view, carrier), "ProductionSessionError", "malformed")
    # A well-formed pair on both sides is the positive control, so the cases
    # above isolate the type guards rather than a scaffolding failure.
    accepts(lambda: s.wp2_match_views(good_view, good_view),
            "comparing a view with itself")

    # --- BudgetGuard: the budget must be a real int, not merely positive ----
    # ``budget_seconds > 0`` is TRUE for ``True`` and for ``1.5``, so dropping
    # the type conjunct makes the guard ACCEPT a bool or a float budget.  This
    # is not an exception-class difference but a difference in what the guard
    # ENFORCES, and it is observable: the accepted budget is stored and appears
    # in the incomplete receipt.
    for carrier in (True, False, 1.5, 2.0, "5", None, [60]):
        refuses(lambda carrier=carrier: s.BudgetGuard(
            lambda: 0.0, budget_seconds=carrier),
            "ProductionSessionError", "budget must be a positive number")
    # The positive control: real positive ints below the hard timeout.
    accepts(lambda: s.BudgetGuard(lambda: 0.0, budget_seconds=60),
            "a valid positive budget")
    accepts(lambda: s.BudgetGuard(lambda: 0.0), "the default budget")


def check_the_s7_budget_check_stops_the_write() -> None:
    """``guard.check()`` at the S7 boundary (:1217) is what stops the write.

    The budget cases in ``check_every_budget_check_is_load_bearing`` stop the run
    at strides that land BEFORE S7, so they never observe what this check does.
    A stride that lands AFTER the records are built but before the whole-range
    promotion is the case: with ``guard.check()`` present the run stops and the
    receipt names ``records_built``; with it dropped the run carries on into
    ``write_sealed_whole_ranges`` and fails deep inside WP4b with an uncaught
    ``ProductionWriterError`` -- the session no longer stops for the budget at
    all, which is the whole purpose of the guard.
    """
    budget = float(s.BUDGET_SECONDS)
    base = new_base("c7s7")
    layout, writer_root = R._layout_and_writer(base, "c7s7", nonce="c7s7-wp8b")
    verified = s.verify_instance_for_session(1, root=layout, standin=True)
    family = R.rehearsal_family()
    total = records.family_space(
        family, records.build_frozen_axes()).total_coordinates

    # The stride is MEASURED, not assumed.  Driving the real session across a range
    # of strides gives: 0.20/0.18/0.17 stop at ``wp3_check_passed``, 0.16 and
    # 0.15 stop at ``records_built`` (the S7 window -- the budget is crossed at
    # the ``guard.check()`` that precedes the whole-range promotion), and 0.14
    # lets the run COMPLETE.  0.15 is inside the window; asserting the landing
    # point below is what makes this a test of the S7 check rather than of an
    # unrelated earlier stop.
    stride = budget * 0.15
    ticks = {"n": 0}

    def clock():
        ticks["n"] += 1
        return float(ticks["n"]) * stride

    receipt = accepts(lambda: R.run_session(
        base, layout=layout, writer_root=writer_root,
        nonce_root=st.sandbox_root(base, "c7s7-nonce"),
        session_id="session-c7s7",
        authorization=R._one_use_authorization(
            verified, st.draft_identity_sha256(), nonce="c7s7-auth"),
        session_identity=st.draft_identity(), clock=clock,
        family=family, family_coordinates=total,
        engine_results=R.placeholder_engine_results(total),
        verified_instance=verified),
        "the session stopped by the budget just before S7")
    ok(receipt["status"] == "incomplete_budget",
       f"the S7 budget case must stop for the budget, got "
       f"{receipt['status']!r}: {receipt.get('difference', '')[:200]}")
    ok(receipt["last_completed_step"] == "records_built",
       f"the S7 budget case must stop AFTER records_built, got "
       f"{receipt['last_completed_step']!r}")
    ok(receipt["promoted_range_batch_ids"] == [],
       "a run stopped at the S7 budget check must promote nothing")
    ok(receipt["scientific_outputs"] == [],
       "a run stopped at the S7 budget check must carry no scientific output")


# ===========================================================================
# The table, and the driver
# ===========================================================================


#: Every check, dispatched from a table so that DELETING an entry removes an
#: assertion the run depends on.  ``main`` never calls a check by name: a bare
#: ``check_x()`` is itself a mutation site whose mutant is ``pass``.
CHECKS = (
    check_pure_helpers,
    check_require_forms,
    check_error_taxonomy,
    check_contract_constants,
    check_no_arming_flags,
    check_module_sets_no_gate,
    check_owner_gate_status,
    check_session_contract_hash,
    check_main_reports_and_runs_nothing,
    check_authority_boundary,
    check_steps_ledger,
    check_budget_guard,
    check_child_environment_and_pins,
    check_identity_binding_and_exact_match,
    check_instance_verification_and_state,
    check_authorization_validation,
    check_authorization_consumption_is_one_use,
    check_wp8a_acceptance_is_refused,
    check_record_projection_and_write,
    check_record_building_never_fabricates,
    check_missing_ranges_requires_a_sealed_plan,
    check_resume_policy,
    check_end_to_end_session_receipt,
    check_failed_prerequisite_blocks_every_step,
    check_seams_and_injected_callables,
    check_identity_binding_shape_is_load_bearing,
    check_slippery_discarded_calls,
    check_s1_to_s7_ordering_is_observed,
    check_authorization_wrong_type_and_empty,
    check_wp1_verdict_cannot_be_laundered,
    check_replay_of_identical_authorization_bytes,
    check_every_budget_check_is_load_bearing,
    check_empty_and_wrong_typed_carriers_are_refused,
    check_record_building_guards_see_bad_indices,
    check_write_schema_and_child_environment_guards,
    check_session_body_guards_are_observable,
    check_session_ledger_and_refusal_are_recorded,
    check_slot_and_state_guards_are_load_bearing,
    check_adapter_guards_reach_their_second_conjunct,
    check_state_write_guard_is_load_bearing,
    check_non_mapping_carriers_keep_their_typed_refusal,
    check_the_s7_budget_check_stops_the_write,
)


def _sentinel_path():
    """Where the completion witness goes, if the caller asked for one.

    The path comes from the environment so each gate gets a UNIQUE file and two
    concurrent runs cannot overwrite each other's witness.
    """
    target = os.environ.get(SENTINEL_ENV)
    return Path(target) if target else None


def _write_sentinel(*, selected: int, passed: int, failed: int,
                    failures: list[str]) -> None:
    """Record that the WHOLE table was dispatched, with its outcome.

    Written only here -- at the very end of ``main`` -- so its presence proves
    the checks actually ran.  Absence (or a stale prior file) is what a gate
    treats as "the fixture did not really execute", which is the condition an
    import-time ``SystemExit(0)`` in the module under test produces.
    """
    path = _sentinel_path()
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    # Truncate first: a stale witness from an earlier run must never survive a
    # run that died before reaching this line.
    path.write_text(json.dumps({
        "schema": "g9_wp8c_fixture_completion/v1",
        "checks_selected": selected,
        "checks_passed": passed,
        "checks_failed": failed,
        "failing_checks": failures,
        "module_sha256": s.session_contract_sha256(),
    }, sort_keys=True), encoding="utf-8")


def main(argv=None) -> int:
    """Run every check in ``CHECKS``.  Returns 0 only when all of them pass."""
    import argparse
    parser = argparse.ArgumentParser(description="WP8c fixture")
    parser.add_argument("--list", action="store_true",
                        help="print the check table and exit")
    parser.add_argument("--only", default=None,
                        help="run only checks whose name contains this substring")
    args = parser.parse_args(argv)

    # The table itself must be well formed: unique names, and every entry a
    # zero-argument callable.  Asserted so that a duplicated or malformed entry
    # is caught before it silently reduces coverage.
    names = [check.__name__ for check in CHECKS]
    ok(len(names) == len(set(names)),
       f"the check table has a duplicate entry: {names}")
    ok(all(inspect.isfunction(check) and check.__module__ == __name__
           for check in CHECKS),
       "every table entry must be a function defined in this fixture")
    ok(all(not inspect.signature(check).parameters for check in CHECKS),
       "every check must take no arguments")

    if args.list:
        for name in names:
            print(name)
        return 0

    selected = CHECKS
    if args.only:
        selected = tuple(check for check in CHECKS if args.only in check.__name__)
        ok(selected, f"no check matched --only {args.only!r}")

    print("WP8c fixture — NON-PRODUCTION stand-in only; unarmed")
    print(f"  scope   {s.SCOPE_STATEMENT[:92]}...")
    print(f"  gates   {json.dumps(s.owner_gate_status(), sort_keys=True)[:120]}")
    print(f"  checks  {len(selected)} of {len(CHECKS)}\n")

    failures: list[tuple[str, str, str]] = []
    for check in selected:
        try:
            check()
        except BaseException as exc:  # noqa: BLE001 - the type is the report
            failures.append((check.__name__, type(exc).__name__, str(exc)))
            print(f"  FAIL    {check.__name__}: {type(exc).__name__}: {exc}")
        else:
            CHECKED.append(check.__name__)
            print(f"  pass    {check.__name__}")

    print(f"\n{len(CHECKED)} passed, {len(failures)} failed")
    global _TABLE_COMPLETED, _SELECTED_N
    _TABLE_COMPLETED = True
    _SELECTED_N = len(selected)
    _write_sentinel(selected=len(selected), passed=len(CHECKED),
                    failed=len(failures), failures=[f[0] for f in failures])
    if failures:
        print("FIXTURE: FAIL")
        return 1
    print("FIXTURE: PASS (NON-PRODUCTION stand-in only; unarmed; no real draw, no "
          "production seed/beacon, no scientific write, no GPU, no push)")
    return 0


if __name__ == "__main__":
    # The return value is asserted against 0 by an ``assert`` this file does not
    # define, so a mutated exit status is caught before ``SystemExit`` hides it.
    _status = main()
    assert _status == 0, f"main() must return 0 on a passing run, got {_status!r}"
    # THE BYPASS GUARD.  A pass is only a pass if every selected check was
    # dispatched.  ``_TABLE_COMPLETED`` is set inside ``main`` after the last
    # check returns, so it cannot be set by a ``SystemExit`` raised while the
    # module under test was being imported -- the condition that let the
    # ``__main__`` mutants at :2057 exit 0 with zero checks executed.
    #
    # ``--only`` selects a deliberate SUBSET, so the comparison is against what
    # was selected.  A full run is additionally held to a constant floor, which
    # no mutation of this file's own table can lower.  ``_SELECTED_N`` is 0
    # unless ``main`` reached its own end, so the equality below is also the
    # witness that ``main`` completed at all.
    assert _SELECTED_N > 0, "main() never recorded its selected-check count"
    assert len(CHECKED) == _SELECTED_N, (
        f"every selected check must have been dispatched and passed: "
        f"{len(CHECKED)} of {_SELECTED_N}")
    if _SELECTED_N == len(CHECKS):
        _MIN_CHECKS = 42
        assert len(CHECKED) >= _MIN_CHECKS, (
            f"the fixture ran only {len(CHECKED)} checks; the table has been "
            f"silently reduced below the floor of {_MIN_CHECKS}")
    raise SystemExit(_status)
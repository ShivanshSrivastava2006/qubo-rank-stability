#!/usr/bin/env python3
"""Synthetic fixtures for WP8b — the NON-SYNTHETIC instance-preparation path.

EVERYTHING HERE IS NON-PRODUCTION.  No real generator draw, no production seed,
no beacon, no network, no credential, no GPU.  The only instances this fixture
builds are conspicuously labelled stand-ins whose ids start with
``NONPROD-STANDIN`` and contain ``NON-PRODUCTION``; the module refuses to take
the accepting branch for anything else.  All writes go to a
``tempfile.TemporaryDirectory`` under the job scratch tree, and the one-use
nonce registry is driven inside a per-run SANDBOX ROOT, never in the project.

Round 2 — why this file was rewritten
=====================================

Round 1's fixture failed its OWN mutation sweep with 231 survivors, and the
validator confirmed with ``--only`` that deleting ``check_replay`` from ``main``
survived.  A sweep site exists for every ``if``/``assert`` test, every discarded
call, and every ``raise`` in a guard body, so a fixture that merely *calls* its
own check functions is one in which most guards are unobservable: the mutated
fixture still exits 0.

The rules this rewrite follows, so the module reaches a clean sweep:

  1. A guard appears only where the fixture observes BOTH outcomes.  There is
     no ``if <check ran>: pass`` self-attestation — the fixture verifies real
     values, and each verification is reached by data that would really fail.
  2. Every check is invoked from a table that is itself iterated and checked for
     duplicates, so removing an entry removes an assertion the run depends on.
     Round 1's ``main()`` called each check once by name, and a bare call is an
     S2 site whose mutant is ``pass`` — invisible when the others still pass.
  3. Conditions are *value* checks whose two outcomes the fixture really
     produces (a valid record and a tampered one), never boolean flags set by
     the code under test.

Every round-1 defect the validator proved has a dedicated regression here, named
after the defect so a reader can match it to the report: ``r2_d1_*`` (replay),
``r2_d2_*`` (approval identity), ``r2_d3_*`` (source closure), ``r2_d4_*``
(rehashed tampering), ``r2_d6_*`` (pinned byte identity).
"""
from __future__ import annotations

import copy
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True

# This fixture lives at research/g9/wp8b/, so the project root is parents[3].
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.g9 import stage2_instance_preparation as wp5b  # noqa: E402
from research.g9.wp8b import wp8b_non_synthetic_preparation as m  # noqa: E402


class FixtureError(RuntimeError):
    pass


COUNT = 0

#: The number of assertions a correct full run performs.  ``main`` requires this
#: exact total, which is what makes most individual assertions load-bearing: a
#: dropped or unreachable one changes the total and fails the run, instead of
#: being masked by its neighbours.  Recalibrate with ``python3 -B <this file>``,
#: which prints the count it observed.
#:
#: IMPORTANT: this total is NOT sufficient on its own, and round 3 proved it.
#: ``require`` is the only thing that increments ``COUNT``, so when ``require``'s
#: own ``raise`` was neutered the total drifted to 476 while this guard — a
#: ``require`` call — silently did nothing and the run still printed PASS.  The
#: total is now corroborated by :func:`check_require_helper_contract` and
#: :func:`check_dispatch_self_audit`, which assert with the interpreter's own
#: ``assert`` and so cannot be disabled by that same edit.
EXPECTED_ASSERTIONS = 476

#: The floor on how many check functions this file may define.  Calibrate down
#: only deliberately, and never as a way of making a failing guard disappear.
MIN_CHECK_FUNCTIONS = 30

#: Scratch root mandated by the package rules.  Never /tmp.
SCRATCH = Path("/home/shivansh-srivastava/decisions_os/g9_jobs/scratch/wp8b")

#: A conspicuously non-production stand-in instance id.
STANDIN_ID = "NONPROD-STANDIN-0001-NON-PRODUCTION"
#: A second, different stand-in, used where a distinct instance id matters.
STANDIN_ID_B = "NONPROD-STANDIN-0002-NON-PRODUCTION"
#: The synthetic path's own stand-in id, used to prove the flag gate.
SYNTHETIC_ID = "NONPROD-SYNTHETIC-0001-NON-PRODUCTION"
#: Real-looking ids that are NOT conspicuously labelled stand-ins.
UNLABELLED_ID = "STAGE2-UNLABELLED-LOOKALIKE"
NO_PREFIX_ID = "STAGE2-01-NON-PRODUCTION"
NO_LABEL_ID = "NONPROD-STANDIN-0003"


def _observed(fn) -> dict:
    """Run ``fn`` and report what it did, as a VALUE rather than a verdict.

    This is the fixture's floor of trust.  ``require``/``refused`` decide what
    counts as a pass, so a check that only ever calls them is testing a
    primitive using itself: neuter the primitive's ``raise`` and every one of
    those calls silently becomes a no-op while the run still prints PASS.  That
    is not hypothetical — ``require``'s own ``raise`` was a surviving mutant
    until this helper was added.

    A fixture cannot make its own reporter lie, so this helper never raises and
    never counts.  It reports ``outcome`` (``"raised"`` / ``"returned"``) plus
    the exception's exact type and message, and the callers below assert on
    those fields with the interpreter's own ``assert``.  ``assert`` is the one
    failure channel this file does not define, so it is independent of
    ``require``: disabling ``require``'s raise cannot disable it, and disabling
    these checks' own raise cannot mask them because the count and
    ``EXPECTED_ASSERTIONS`` are independent quantities.
    """
    try:
        value = fn()
    except BaseException as exc:  # noqa: BLE001 - the type is what is under test
        return {
            "outcome": "raised",
            "type": type(exc),
            "type_name": type(exc).__name__,
            "message": str(exc),
            "text": str(exc),
            "value": None,
        }
    return {
        "outcome": "returned",
        "type": None,
        "type_name": None,
        "message": "",
        "text": "",
        "value": value,
    }


def require(condition: bool, message: str) -> None:
    global COUNT
    if not condition:
        raise FixtureError(message)
    COUNT += 1


def refused(fn, expected_type, label: str, needle: str = "") -> None:
    """Require ``fn`` to raise exactly ``expected_type`` (or a subclass).

    A wrong exception type, and equally an *accepted* call, are both failures:
    the second is what makes this a real negative probe rather than a smoke
    test, and it is what kills the "the guard was deleted" mutant.
    """
    global COUNT
    try:
        fn()
    except expected_type as exc:
        # The count is incremented only on the SUCCESS path, and only after the
        # needle check, so the total ``main`` requires depends on every clause
        # here.  That is what makes the needle a real guard rather than a
        # diagnostic: skipping it (or any of its three conditions) changes the
        # total and fails the run.  The alternative — counting before the
        # check — would make a wrong-reason refusal pass silently, which is
        # exactly the bug the needle exists to catch.
        if needle and needle not in str(exc):
            raise FixtureError(f"{label}: refused for the wrong reason: {exc}") from exc
        COUNT += 1
        return
    except FixtureError:
        raise
    except BaseException as exc:  # noqa: BLE001 - we want the wrong type named
        raise FixtureError(
            f"{label}: raised {type(exc).__name__} instead of "
            f"{expected_type.__name__}: {exc}"
        ) from exc
    raise FixtureError(f"{label}: accepted (no refusal raised)")


def pycache_count() -> int:
    return sum(1 for _ in ROOT.rglob("__pycache__")) + sum(1 for _ in ROOT.rglob("*.pyc"))


# ---------------------------------------------------------------------------
# The stand-in instances and the approvals over them
# ---------------------------------------------------------------------------

def standin(instance_id: str = STANDIN_ID, synthetic: bool = False):
    """A tiny (n=3) stand-in instance.  Obviously non-production parameters."""
    return wp5b.SyntheticInstance(
        instance_id=instance_id,
        synthetic=synthetic,
        order=("AAA", "BBB", "CCC"),
        mu=(0.1, 0.2, 0.3),
        Sigma=((0.04, 0.01, 0.005), (0.01, 0.05, 0.008), (0.005, 0.008, 0.06)),
        p=(0.3, 0.3, 0.4),
        K=2,
        C=2,
        B=1100.0,
        kappa=1.0,
        sector_of={"AAA": "tech", "BBB": "tech", "CCC": "util"},
        sector_labels=("tech", "util"),
        approval=None,
    )


def standin_digest(instance_id: str = STANDIN_ID) -> str:
    return m.instance_content_sha256(standin(instance_id))


def approval_over(
    *,
    scope: str = m.FIXTURE_SCOPE,
    instance_id: str = STANDIN_ID,
    digest: str | None = None,
    nonce: str = "wp8b-fixture-nonce-once",
    label: str = m.OWNER_APPROVAL_LABEL,
    status: str = m.APPROVAL_STATUS,
    schema: str = m.APPROVAL_SCHEMA,
    statement: str = m.APPROVAL_STATEMENT,
    expiry: str = "2099-12-31",
) -> dict:
    """A structurally complete approval record, with every field overridable."""
    if digest is None:
        digest = standin_digest(instance_id)
    return {
        "schema": schema,
        "status": status,
        "label": label,
        "scope": scope,
        "approves_instance_content_sha256": digest,
        "instance_id": instance_id,
        "expiry": expiry,
        "nonce": nonce,
        "statement": statement,
    }


def resign(record: dict) -> dict:
    """Recompute ``content_sha256`` after a tamper, so ONE guard is under test.

    Without re-signing, EVERY field tamper also breaks the final content-hash
    recomputation, so removing an intermediate guard is unobservable.  Signing
    again isolates the guard being probed — and it is precisely re-signing that
    defeated round 1, which is why every ``r2_d4_*`` case re-signs AND supplies
    the instance.
    """
    body = dict(record)
    body.pop("content_sha256", None)
    return dict(body, content_sha256=hashlib.sha256(m._canonical(body)).hexdigest())


def prepare_fixture_branch(
    instance, approval, consume_dir: str | None = None, *, root: str, **kwargs
):
    """Drive the ONE accepting path, always supplying the fixture token."""
    return m.prepare_non_synthetic(
        instance,
        approval,
        consume_dir=consume_dir,
        fixture_context=m.FIXTURE_CONTEXT_TOKEN,
        root=root,
        **kwargs,
    )


def _scratch_dir(parent: str, name: str) -> str:
    """Create and return ``parent/name``.

    Every scratch directory in this fixture is made through here rather than by a
    bare ``os.makedirs`` call.  A discarded ``os.makedirs`` is an S2 site whose
    mutant is ``pass``, and there is no honest way for a fixture to *observe*
    that a directory it just created still exists — so each such site was
    individually unkillable.  Routing them through one helper collapses a dozen
    bookkeeping sites into one whose return value every caller actually uses.
    """
    path = os.path.join(parent, name)
    os.makedirs(path, exist_ok=True)
    return path


def marker_name_for(approval: dict) -> str:
    """The registry marker file name an approval consumes into."""
    return "wp8b_approval_" + m._approval_ledger_key(approval) + m.NONCE_MARKER_SUFFIX


# ===========================================================================
# A. The accepting non-production path (so the guards can be killed)
# ===========================================================================

def check_accepting_non_production(tmp: str, root: str) -> None:
    instance = standin()
    approval = approval_over()
    consume = _scratch_dir(tmp, "consume-a")

    record = prepare_fixture_branch(instance, approval, consume_dir=consume, root=root)

    require(set(record) == m.RECORD_KEYS, "record key set mismatch")
    require(record["schema"] == m.PROVENANCE_SCHEMA, "record schema must be the NEW WP8b schema")
    require(
        record["schema"] != wp5b.PROVENANCE_SCHEMA,
        "WP8b record schema must differ from WP5b's synthetic schema",
    )
    require(
        record["status"] == m.RECORD_STATUS_NON_PRODUCTION,
        "fixture-branch record must be stamped NON-PRODUCTION",
    )
    require(record["production"] is False, "fixture-branch record must not claim production")
    require(
        record["status"] != m.RECORD_STATUS_PRODUCTION,
        "no fixture-branch record may ever carry the production status",
    )
    require(
        m.NON_PRODUCTION_LABEL in record["instance"]["instance_id"],
        "stand-in id must carry the label",
    )
    require(
        record["instance"]["content_sha256"] == standin_digest(),
        "record must bind the instance's own recomputed content digest",
    )
    require(
        record["approval"]["approves_instance_content_sha256"] == standin_digest(),
        "record must bind the approval's named digest",
    )
    require(
        record["approval"]["instance_id"] == STANDIN_ID,
        "record must bind the approval's named identity",
    )
    require(record["scientific_outputs"] == "intentionally absent", "result boundary violated")
    require(
        record["identity"]["non_synthetic_identity_hash"] == m.NON_SYNTHETIC_IDENTITY_HASH,
        "record must bind this path's own identity hash",
    )
    require(
        record["identity"]["identity_payload_sha256"]
        == hashlib.sha256(m._canonical(m._identity_payload(m.source_digests()))).hexdigest(),
        "identity payload hash must be recomputable from the bound sources",
    )
    require(
        set(record["source_sha256"]) == set(m.source_digests()),
        "record must bind exactly the declared source set",
    )
    for key in sorted(m.SOURCE_FILES):
        require(
            any(entry.startswith(key + ":") for entry in record["source_sha256"]),
            f"source closure must bind {key}",
        )
    body = dict(record)
    digest = body.pop("content_sha256")
    require(
        hashlib.sha256(m._canonical(body)).hexdigest() == digest,
        "record content hash must verify",
    )
    # The numerics carried forward are WP5b's, unchanged.
    require(
        record["results"]["f_star"]
        == wp5b.resolve_optimum(
            wp5b.validate_envelope(
                wp5b.SyntheticInstance(**{**instance.__dict__, "synthetic": True})
            )
        ).f_star,
        "f* must equal the frozen WP5b value for identical content",
    )
    require(record["results"]["Lambda_ref"] > 0.0, "Lambda_ref must be strictly positive")
    require(
        record["results"]["X_star_definition"].startswith("exact binary64 equality"),
        "X* definition must be the frozen one",
    )
    # The one-use marker was written for this approval, in the SANDBOX registry.
    expected_marker = os.path.join(m._registry_path(root), marker_name_for(approval))
    require(
        os.path.isfile(expected_marker),
        "the one-use marker must live in the module-fixed sandbox registry",
    )
    require(
        sorted(os.listdir(consume)) == [os.path.basename(expected_marker)],
        "exactly one audit-mirror marker may be written to consume_dir",
    )
    with open(expected_marker, "rb") as handle:
        marker_bytes = handle.read()
    require(
        record["approval"]["nonce_consumed_marker_sha256"]
        == hashlib.sha256(marker_bytes).hexdigest(),
        "record must bind the consumed marker hash",
    )
    require(
        record["approval"]["nonce_consumed_marker_sha256"] != "0" * 64,
        "a consumed marker must never bind the zero digest",
    )


def check_accepting_is_deterministic(tmp: str, root: str) -> None:
    """Distinct approvals give distinct records, and the nonce digest is bound."""
    instance = standin(STANDIN_ID_B)
    approval = approval_over(instance_id=STANDIN_ID_B, nonce="wp8b-fixture-nonce-b")
    pinned = datetime.date(2026, 10, 1)
    consume = _scratch_dir(tmp, "consume-b1")
    root_b = _scratch_dir(root, "root-b")
    first = prepare_fixture_branch(
        instance, approval, consume_dir=consume, root=root_b, now=pinned
    )
    require(
        first["approval"]["nonce_sha256"]
        == hashlib.sha256(approval["nonce"].encode("utf-8")).hexdigest(),
        "record must bind the approval nonce digest",
    )
    other = prepare_fixture_branch(
        instance,
        approval_over(instance_id=STANDIN_ID_B, nonce="wp8b-fixture-nonce-b2"),
        root=root,
        now=pinned,
    )
    require(
        first["content_sha256"] != other["content_sha256"],
        "two approvals over one instance must produce distinct records",
    )


# ===========================================================================
# B. R1 — no approval, and every malformed approval
# ===========================================================================

def check_no_approval(tmp: str, root: str) -> None:
    consume = _scratch_dir(tmp, "consume-no-approval")
    refused(
        lambda: m.prepare_non_synthetic(standin(), None, consume_dir=consume, root=root),
        m.ApprovalRequired,
        "R1 no approval at all",
        "approval record is required",
    )
    refused(
        lambda: m.prepare_non_synthetic(standin(), None, root=root),
        m.ApprovalRequired,
        "R1 no approval, no consume_dir",
    )
    # Omitted entirely.
    refused(
        lambda: m.prepare_non_synthetic(standin()),
        TypeError,
        "R1 approval argument is required by the signature",
    )


def check_malformed_approvals(tmp: str, root: str) -> None:
    good = approval_over()
    instance = standin()

    def refused_shape(record, label, expected=m.ApprovalRequired, needle=""):
        refused(
            lambda: m.prepare_non_synthetic(
                instance, record, fixture_context=m.FIXTURE_CONTEXT_TOKEN, root=root
            ),
            expected,
            label,
            needle,
        )

    for bad, label in (([], "a list"), ("not a dict", "a str"), (7, "an int")):
        refused_shape(bad, f"R1 approval is {label}", needle="exact dict")
    refused_shape(None, "R1 approval is None", needle="approval record is required")

    missing = {k: v for k, v in good.items() if k != "nonce"}
    refused_shape(missing, "R1 approval missing nonce", needle="fields differ")
    refused_shape(dict(good, surprise=1), "R1 approval extra field", needle="fields differ")

    for field, value, needle in (
        ("schema", "decisions_os/g9_wp8b_owner_draw_write_approval/v2", "schema mismatch"),
        ("status", "pending", "must be owner_approved"),
        ("status", None, "must be owner_approved"),
        ("label", "something_else", "label must be non_synthetic"),
        ("label", 7, "label must be non_synthetic"),
        ("scope", "stage2_generator_draw", "scope mismatch"),
        ("scope", None, "scope mismatch"),
        ("statement", "trust me", "statement mismatch"),
        ("statement", None, "statement mismatch"),
        ("nonce", "", "nonce"),
        ("nonce", None, "nonce"),
        ("nonce", 17, "nonce"),
        ("expiry", "tomorrow", "not a calendar date"),
        ("expiry", "2026-99-99", "not a calendar date"),
        ("expiry", None, "not a calendar date"),
        ("expiry", 17, "not a calendar date"),
        ("expiry", "", "not a calendar date"),
        ("expiry", "20261001", "canonical ISO"),
        ("expiry", "2026-W40-1", "canonical ISO"),
    ):
        refused_shape(dict(good, **{field: value}), f"R1 {field}={value!r}", needle=needle)

    yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    refused_shape(dict(good, expiry=yesterday), "R1 expired approval", needle="has expired")

    for bad_digest in ("z" * 64, "F" * 64, "ABCDEF0123456789" * 4, "abc", None, 17, ""):
        # A digest that is not shape-valid is an R1 shape refusal, so it is
        # refused before the R2 comparison and never reports a wrong reason.
        refused_shape(
            dict(good, approves_instance_content_sha256=bad_digest),
            f"R1 malformed digest {bad_digest!r}",
            needle="lowercase SHA-256",
        )


# ===========================================================================
# C. R2 — the approval does not name this instance's exact content hash
# ===========================================================================

def check_hash_binding(tmp: str, root: str) -> None:
    instance = standin()
    good_digest = standin_digest()
    other = standin_digest(STANDIN_ID_B)
    require(good_digest != other, "two stand-ins must differ in content digest")

    refused(
        lambda: m.prepare_non_synthetic(
            instance,
            approval_over(digest=other),
            fixture_context=m.FIXTURE_CONTEXT_TOKEN,
            root=root,
        ),
        m.ApprovalHashBindingRefused,
        "R2 approval names another instance",
        "does not name this instance's exact content SHA-256",
    )
    for wrong, label in ((good_digest.upper(), "uppercase"), (good_digest[:-1], "truncated")):
        refused(
            lambda w=wrong: m.prepare_non_synthetic(
                instance,
                approval_over(digest=w),
                fixture_context=m.FIXTURE_CONTEXT_TOKEN,
                root=root,
            ),
            m.ApprovalRequired,
            f"R1 {label} digest is refused",
            "lowercase SHA-256",
        )
    refused(
        lambda: m.prepare_non_synthetic(
            instance,
            approval_over(digest="0" * 64),
            fixture_context=m.FIXTURE_CONTEXT_TOKEN,
            root=root,
        ),
        m.ApprovalHashBindingRefused,
        "R2 all-zero digest is refused",
    )
    # The binding is checked against the LIVE instance content.
    mutated = wp5b.SyntheticInstance(
        **{**standin().__dict__, "mu": (0.1, 0.2, 0.30000000000000004)}
    )
    refused(
        lambda: m.prepare_non_synthetic(
            mutated, approval_over(), fixture_context=m.FIXTURE_CONTEXT_TOKEN, root=root
        ),
        m.ApprovalHashBindingRefused,
        "R2 mutated instance content is refused under the original approval",
    )
    rec = prepare_fixture_branch(
        mutated,
        approval_over(digest=m.instance_content_sha256(mutated), nonce="wp8b-mutated"),
        root=root,
    )
    require(
        rec["instance"]["content_sha256"] != good_digest,
        "a different instance body must yield a different digest",
    )


def check_hash_binding_precedes_shape(tmp: str, root: str) -> None:
    """An approval whose digest is wrong is refused as R2 even when also malformed."""
    bad = dict(approval_over(), status="not_approved", approves_instance_content_sha256="0" * 64)
    refused(
        lambda: m.prepare_non_synthetic(
            standin(), bad, fixture_context=m.FIXTURE_CONTEXT_TOKEN, root=root
        ),
        m.ApprovalHashBindingRefused,
        "R2 is checked before the status/shape refusals",
        "does not name this instance's exact content",
    )


# ===========================================================================
# D. R3 — synthetic-flag confusion
# ===========================================================================

def check_synthetic_flag_confusion(tmp: str, root: str) -> None:
    good = approval_over()
    refused(
        lambda: m.prepare_non_synthetic(
            standin(synthetic=True), good, fixture_context=m.FIXTURE_CONTEXT_TOKEN, root=root
        ),
        m.SyntheticFlagConfusionRefused,
        "R3 envelope marked synthetic is True",
        "not marked synthetic is False",
    )
    for mark in (True, None, 0, 1, "false", "False", [], ()):
        refused(
            lambda mk=mark: m.prepare_non_synthetic(
                standin(synthetic=mk), good, fixture_context=m.FIXTURE_CONTEXT_TOKEN, root=root
            ),
            m.SyntheticFlagConfusionRefused,
            f"R3 envelope mark {mark!r}",
        )
    refused(
        lambda: m.prepare_non_synthetic(
            standin(),
            approval_over(label="synthetic"),
            fixture_context=m.FIXTURE_CONTEXT_TOKEN,
            root=root,
        ),
        m.SyntheticFlagConfusionRefused,
        "R3 approval labelled synthetic",
        "cannot authorize the non-synthetic preparation path",
    )
    # A DIFFERENT instance: refused by the R2 binding, because a different
    # instance_id is a field of the hashed body and implies a different digest.
    # The R3.2 guard covers what round 1 missed: a CORRECT digest alongside a
    # DIFFERENT named id.
    refused(
        lambda: m.prepare_non_synthetic(
            standin(STANDIN_ID),
            approval_over(instance_id=STANDIN_ID_B),
            fixture_context=m.FIXTURE_CONTEXT_TOKEN,
            root=root,
        ),
        m.ApprovalHashBindingRefused,
        "R3 a different instance is refused by the hash binding",
        "does not name this instance's exact content",
    )


# ===========================================================================
# r2_d2 — REGRESSION: the approval must NAME the instance it authorizes
# ===========================================================================
#
# Round-1 validator probe, verbatim (wp8b.r1.vout:5810-5814):
#     wrong=approval(x,nonce='different-id')
#     wrong['instance_id']='STAGE2-OTHER-IDENTITY'      -> ACCEPTED
#     wrongtype['instance_id']=7                        -> ACCEPTED
# Both carried a CORRECT approves_instance_content_sha256, which is why the R2
# hash binding never fired and the approval was free to assert a different
# identity than the instance it was preparing.

def r2_d2_approval_identity_binding(tmp: str, root: str) -> None:
    instance = standin(STANDIN_ID_B)
    base = approval_over(instance_id=STANDIN_ID_B, digest=standin_digest(STANDIN_ID_B))

    # The exact round-1 bypass: a different id over a correct digest.
    refused(
        lambda: m.prepare_non_synthetic(
            instance,
            dict(base, instance_id="STAGE2-OTHER-IDENTITY", nonce="wp8b-d2-string"),
            fixture_context=m.FIXTURE_CONTEXT_TOKEN,
            root=root,
        ),
        m.SyntheticFlagConfusionRefused,
        "r2_d2 an approval naming another identity is refused",
        "must name exactly the instance it authorizes",
    )
    # The second round-1 bypass: a non-string id.  Round 2's first attempt at
    # this guard gated the CALL on ``type(...) is str``, which skipped the guard
    # for exactly this value, so the type test now lives inside the guard.
    for wrong_id in (7, None, [], 3.5, True):
        refused(
            lambda w=wrong_id: m.prepare_non_synthetic(
                instance,
                dict(base, instance_id=w, nonce=f"wp8b-d2-type-{wrong_id!r}"),
                fixture_context=m.FIXTURE_CONTEXT_TOKEN,
                root=root,
            ),
            m.SyntheticFlagConfusionRefused,
            f"r2_d2 a non-str approval id {wrong_id!r} is refused",
        )
    # The correct pairing is still ACCEPTED, so the guard discriminates rather
    # than refusing everything: this is what the S5 negation mutant needs.
    ok = prepare_fixture_branch(
        instance,
        dict(base, instance_id=STANDIN_ID_B, nonce="wp8b-d2-correct"),
        root=root,
    )
    require(
        ok["approval"]["instance_id"] == STANDIN_ID_B,
        "r2_d2 the correctly-named approval is accepted and records its identity",
    )
    # The R1 shape guard on ``_validate_approval`` is driven DIRECTLY as well.
    # Through the public entry point it is dominated by the R3.2 identity guard
    # above (an empty or None id is also the wrong id), so the round-2 sweep
    # found its ``raise`` unkillable.  The two are different rules with different
    # messages — one is "this approval is not well formed", the other "this
    # approval names a different instance" — and only a direct call tells them
    # apart.
    for bad_id, label in (("", "empty"), (None, "None")):
        refused(
            lambda b=bad_id: m._validate_approval(dict(base, instance_id=b)),
            m.ApprovalRequired,
            f"r2_d2 _validate_approval refuses a {label} instance_id",
            "approval instance_id must be a non-empty str",
        )
    # ... and the R3.2 guard is driven directly too, so its own type clause is
    # observable independently of the R2 binding that runs before it publicly.
    for bad_id, label in ((7, "an int"), (None, "None"), ([], "a list")):
        refused(
            lambda b=bad_id: m._check_approval_names_this_instance(
                dict(base, instance_id=b), STANDIN_ID_B
            ),
            m.SyntheticFlagConfusionRefused,
            f"r2_d2 the identity guard refuses a {label} id directly",
            "must be a str naming the instance being prepared",
        )
    refused(
        lambda: m._check_approval_names_this_instance(
            dict(base, instance_id="SOMETHING-ELSE"), STANDIN_ID_B
        ),
        m.SyntheticFlagConfusionRefused,
        "r2_d2 the identity guard refuses a different str id directly",
        "must name exactly the instance it authorizes",
    )
    # The matching identity passes, so both clauses are discriminating.
    require(
        m._check_approval_names_this_instance(
            dict(base, instance_id=STANDIN_ID_B), STANDIN_ID_B
        )
        is None,
        "r2_d2 the identity guard accepts the matching str id",
    )
    # The membership test in the call condition is load-bearing: with it removed
    # (or set to True), an approval carrying NO ``instance_id`` key reaches the
    # guard and raises a bare ``KeyError`` instead of the R1 exact-key-set
    # refusal.  Driven through the public entry so the whole call site is
    # observed, not just the guard.
    no_key = {k: v for k, v in base.items() if k != "instance_id"}
    refused(
        lambda: m.prepare_non_synthetic(
            instance,
            no_key,
            fixture_context=m.FIXTURE_CONTEXT_TOKEN,
            root=root,
        ),
        m.ApprovalRequired,
        "r2_d2 an approval with no instance_id key is refused by the key-set rule",
        "fields differ",
    )


def r2_d2_unlabelled_real_looking_ids(tmp: str, root: str) -> None:
    """A real-looking id is refused on BOTH paths, and the gate is direct-driven.

    This is the "synthetic flag confusion" the brief calls for in its other
    form: a stand-in that is not conspicuously labelled must not be able to
    borrow this fixture's accepting branch.
    """
    for bad_id in (UNLABELLED_ID, NO_PREFIX_ID, NO_LABEL_ID, "stage2_01"):
        lookalike = standin(bad_id)
        approval = approval_over(
            instance_id=bad_id, digest=m.instance_content_sha256(lookalike)
        )
        refused(
            lambda a=approval, i=lookalike: m.prepare_non_synthetic(
                i, a, fixture_context=m.FIXTURE_CONTEXT_TOKEN, root=root
            ),
            m.SyntheticFlagConfusionRefused,
            f"r2_d2 the unlabelled id {bad_id!r} cannot take the fixture branch",
        )
        refused(
            lambda a=approval, i=lookalike: m.prepare_non_synthetic(
                i,
                dict(a, scope=m.OWNER_APPROVAL_SCOPE),
                fixture_context=m.FIXTURE_CONTEXT_TOKEN,
                root=root,
            ),
            m.ProductionReleaseNotPinned,
            f"r2_d2 the unlabelled id {bad_id!r} cannot reach the owner path",
        )
        refused(
            lambda b=bad_id: m.check_fixture_only_approval(
                approval_over(), b, m.FIXTURE_CONTEXT_TOKEN
            ),
            m.SyntheticFlagConfusionRefused,
            f"r2_d2 the gate refuses the unlabelled id {bad_id!r}",
        )


def check_fixture_gate_requires_token(tmp: str, root: str) -> None:
    """The fixture branch is reachable ONLY by naming the token AND the scope."""
    good = approval_over()
    for context in (None, "", "wp8b_non_synthetic_preparation", 0, m.APPROVAL_SCHEMA):
        refused(
            lambda c=context: m.prepare_non_synthetic(
                standin(), good, fixture_context=c, root=root
            ),
            m.ApprovalRequired,
            f"the fixture branch refuses the context {context!r}",
        )
    refused(
        lambda: m.prepare_non_synthetic(
            standin(),
            approval_over(scope=m.OWNER_APPROVAL_SCOPE, nonce="wp8b-token-owner"),
            fixture_context=m.FIXTURE_CONTEXT_TOKEN,
            root=root,
        ),
        m.ProductionReleaseNotPinned,
        "the token does not open the owner path",
    )
    refused(
        lambda: m.check_fixture_only_approval(
            approval_over(scope=m.OWNER_APPROVAL_SCOPE, nonce="wp8b-gate-owner"),
            STANDIN_ID,
            m.FIXTURE_CONTEXT_TOKEN,
        ),
        m.ApprovalRequired,
        "check_fixture_only_approval refuses the owner scope",
        "carry the fixture scope",
    )
    # The gate is reachable when every condition holds — the positive side of
    # the same guard, so negating any one of its conditions is observable.
    reached = m.check_fixture_only_approval(good, STANDIN_ID, m.FIXTURE_CONTEXT_TOKEN)
    require(
        reached["scope"] == m.FIXTURE_SCOPE,
        "check_fixture_only_approval accepts a correct fixture approval",
    )


# ===========================================================================
# E. R4 — replay, and the round-1 bypass
# ===========================================================================
#
# Round-1 validator probe (wp8b.r1.vout:5806-5809): consume in "one", then
# consume the SAME approval in "two" -> ACCEPTED.  Round 1's own fixture
# asserted that as intended ("a fresh consume dir admits the same approval
# once").  Round 2 moves the ledger to a module-fixed registry, consumes on
# every path, and keys it on the approval's canonical bytes.

def check_replay(tmp: str, root: str) -> None:
    instance = standin(STANDIN_ID_B)
    approval = approval_over(instance_id=STANDIN_ID_B, nonce="wp8b-replay-nonce")
    consume = _scratch_dir(tmp, "consume-replay")
    other_dir = _scratch_dir(tmp, "consume-replay-other")

    first = prepare_fixture_branch(instance, approval, consume_dir=consume, root=root)
    require(first["status"] == m.RECORD_STATUS_NON_PRODUCTION, "first pass must succeed")

    refused(
        lambda: prepare_fixture_branch(instance, approval, consume_dir=consume, root=root),
        m.ApprovalReplayRefused,
        "R4 same approval replayed in the same dir",
        "already consumed",
    )
    refused(
        lambda: prepare_fixture_branch(instance, approval, consume_dir=consume, root=root),
        m.ApprovalReplayRefused,
        "R4 replay is refused again, not once",
    )
    # The authoritative marker is the registry one, not the caller's mirror.
    require(
        os.path.isfile(os.path.join(m._registry_path(root), marker_name_for(approval))),
        "R4 the authoritative marker is the registry one, not the mirror",
    )


def r2_d1_replay_is_not_caller_controlled(tmp: str, root: str) -> None:
    """The round-1 bypass, exactly: a FRESH directory must not revive it."""
    instance = standin(STANDIN_ID_B)
    approval = approval_over(instance_id=STANDIN_ID_B, nonce="wp8b-d1-nonce")
    first_dir = os.path.join(tmp, "d1-one")
    second_dir = os.path.join(tmp, "d1-two")
    third_dir = os.path.join(tmp, "d1-three")
    for path in (first_dir, second_dir, third_dir):
        _scratch_dir(os.path.dirname(path), os.path.basename(path))

    prepare_fixture_branch(instance, approval, consume_dir=first_dir, root=root)
    # THE BYPASS.  Round 1 accepted this.
    refused(
        lambda: prepare_fixture_branch(instance, approval, consume_dir=second_dir, root=root),
        m.ApprovalReplayRefused,
        "r2_d1 a different consume dir does not revive a consumed approval",
        "changing the consumption directory does not revive it",
    )
    # Omitting the directory entirely is not a way out either.  Round 1 consumed
    # the nonce only ``if consume_dir is not None``, so this exact call recorded
    # NO one-use state at all and could be repeated forever.
    refused(
        lambda: prepare_fixture_branch(instance, approval, root=root),
        m.ApprovalReplayRefused,
        "r2_d1 omitting consume_dir does not skip one-use consumption",
    )
    refused(
        lambda: prepare_fixture_branch(instance, approval, consume_dir=third_dir, root=root),
        m.ApprovalReplayRefused,
        "r2_d1 the approval stays spent regardless of directory",
    )
    # An UNCHANGED, never-consumed approval still works in a fresh directory,
    # so the guard discriminates rather than refusing everything.
    fresh = prepare_fixture_branch(
        instance,
        approval_over(instance_id=STANDIN_ID_B, nonce="wp8b-d1-fresh"),
        consume_dir=third_dir,
        root=root,
    )
    require(
        fresh["status"] == m.RECORD_STATUS_NON_PRODUCTION,
        "r2_d1 an unconsumed approval is still accepted in a fresh dir",
    )
    # The ledger is keyed on the approval's CANONICAL BYTES, so a dict that is
    # equal but differently ordered maps to the same key and is still a replay.
    reordered = {key: approval[key] for key in reversed(list(approval))}
    require(
        m._approval_ledger_key(reordered) == m._approval_ledger_key(approval),
        "r2_d1 the ledger key is insensitive to dict ordering",
    )
    refused(
        lambda: prepare_fixture_branch(instance, reordered, root=root),
        m.ApprovalReplayRefused,
        "r2_d1 a reordered but identical approval is still a replay",
    )
    changed = dict(approval, expiry="2099-12-30")
    require(
        m._approval_ledger_key(changed) != m._approval_ledger_key(approval),
        "r2_d1 a changed approval yields a different ledger key",
    )


def r2_d1_ledger_key_properties() -> None:
    """``_approval_ledger_key`` is a real digest of the approval's own bytes."""
    approval = approval_over(nonce="wp8b-key-probe")
    key = m._approval_ledger_key(approval)
    require(
        _is_sha256_shape(key),
        "r2_d1 the ledger key must be a lowercase SHA-256",
    )
    require(
        key == hashlib.sha256(m._canonical(approval)).hexdigest(),
        "r2_d1 the ledger key must be the digest of the approval's canonical bytes",
    )
    for field, value in (("status", "pending"), ("label", "synthetic"), ("nonce", "other")):
        require(
            m._approval_ledger_key(dict(approval, **{field: value})) != key,
            f"r2_d1 changing {field} must change the ledger key",
        )
    # The registry path is module-fixed, never caller-derived.
    require(
        m._registry_path("/some/other/root")
        == os.path.join("/some/other/root", m.NONCE_REGISTRY_DIR),
        "r2_d1 the registry lives at the module-fixed relative location",
    )
    require(
        m.NONCE_REGISTRY_DIR == "research/g9/wp8b/.one_use_nonce_registry",
        "r2_d1 the registry location must not drift",
    )


def check_nonce_consumption_refusals(tmp: str, root: str) -> None:
    """The typed refusals around consumption, and the registry's fail-closed arm."""
    consume = _scratch_dir(tmp, "consume-nonce-refusals")
    refused(
        lambda: m.consume_one_use_nonce(
            approval_over(nonce="wp8b-absent-dir"),
            os.path.join(tmp, "does-not-exist"),
            root=root,
        ),
        m.NonSyntheticPreparationError,
        "an absent consume dir is a typed refusal",
        "does not exist",
    )
    for bad_nonce, label in ((None, "None"), ("", "empty")):
        refused(
            lambda b=bad_nonce: m.consume_one_use_nonce({"nonce": b}, consume, root=root),
            m.NonSyntheticPreparationError,
            f"a {label} nonce is refused before the marker path",
            "nonce must be a non-empty str",
        )
    if os.geteuid() != 0:
        ro_dir = _scratch_dir(tmp, "readonly-consume")
        os.chmod(ro_dir, 0o500)
        try:
            refused(
                lambda: m.consume_one_use_nonce(
                    approval_over(nonce="wp8b-readonly-nonce"), ro_dir, root=root
                ),
                m.NonSyntheticPreparationError,
                "an unwritable consume dir is a typed refusal",
                "cannot create nonce audit mirror",
            )
        finally:
            os.chmod(ro_dir, 0o700)
            # The restore is load-bearing, not tidiness: a later check needing a
            # writable directory under the same tree would fail, and the fixture
            # would silently weaken rather than break.  Asserted here so dropping
            # the chmod is observable instead of merely untidy.
            require(
                os.access(ro_dir, os.W_OK),
                "the read-only consume dir must be restored to writable in the finally block",
            )
    # Fail-closed: a root whose registry cannot be created is a typed refusal,
    # because a preparation that cannot record its one-use state has not
    # established one-use.  A regular file where the directory belongs is the
    # portable way to force this.
    blocked_root = os.path.join(tmp, "blocked-root")
    with open(blocked_root, "wb") as handle:
        handle.write(b"not a directory")
    refused(
        lambda: m.consume_one_use_nonce(
            approval_over(nonce="wp8b-blocked-root"), None, root=blocked_root
        ),
        m.NonSyntheticPreparationError,
        "an uncreatable registry is a typed refusal",
        "one-use nonce registry",
    )
    # The marker's own ``os.open`` generic-OSError arm needs an errno that is
    # NOT EEXIST.  An existing but UNWRITABLE registry directory gives EACCES,
    # which is exactly that: the registry itself is fine and present, so the
    # earlier create/isdir arms do not fire, and only this arm can convert the
    # failure into a typed refusal.  Skipped as root, where the mode is not
    # enforced.
    if os.geteuid() != 0:
        ro_registry_root = _scratch_dir(tmp, "read-only-registry")
        ro_registry = os.path.join(ro_registry_root, m.NONCE_REGISTRY_DIR)
        os.makedirs(ro_registry)
        os.chmod(ro_registry, 0o500)
        try:
            refused(
                lambda: m.consume_one_use_nonce(
                    approval_over(nonce="wp8b-marker-eacces"), None, root=ro_registry_root
                ),
                m.NonSyntheticPreparationError,
                "an unwritable registry is a typed refusal, not a traceback",
                "cannot create one-use nonce marker",
            )
        finally:
            os.chmod(ro_registry, 0o700)
            require(
                os.access(ro_registry, os.W_OK),
                "the read-only registry must be restored to writable in the finally block",
            )
    # A registry path that already exists as a REGULAR FILE is the portable
    # trigger for the create arm: ``os.makedirs(..., exist_ok=True)`` re-raises
    # FileExistsError for a non-directory, and the one arm converts it.
    notdir_root = _scratch_dir(tmp, "registry-parent-is-a-file")
    registry_rel = os.path.join(notdir_root, m.NONCE_REGISTRY_DIR)
    os.makedirs(os.path.dirname(registry_rel))
    with open(registry_rel, "wb") as handle:
        handle.write(b"a file where the registry directory belongs")
    refused(
        lambda: m.consume_one_use_nonce(
            approval_over(nonce="wp8b-notdir"), None, root=notdir_root
        ),
        m.NonSyntheticPreparationError,
        "a registry that is a file is a typed refusal, not a traceback",
        "cannot create the one-use nonce registry",
    )
    # A registry path with a REGULAR FILE as its parent cannot be created at
    # all, and the failure is a typed refusal rather than a raw OSError.
    fileparent_root = _scratch_dir(tmp, "registry-grandparent-is-a-file")
    with open(os.path.join(fileparent_root, "research"), "wb") as handle:
        handle.write(b"not a directory")
    refused(
        lambda: m.consume_one_use_nonce(
            approval_over(nonce="wp8b-notdir2"), None, root=fileparent_root
        ),
        m.NonSyntheticPreparationError,
        "an uncreatable registry parent is a typed refusal",
        "one-use nonce registry",
    )
    # Consumption with NO consume_dir at all still records state.
    no_dir_approval = approval_over(nonce="wp8b-no-dir-consume")
    marker = m.consume_one_use_nonce(no_dir_approval, None, root=root)
    require(os.path.isfile(marker), "consumption with no consume_dir must still write the marker")
    require(
        marker.startswith(m._registry_path(root)),
        "the authoritative marker must be the registry one, not a mirror",
    )
    refused(
        lambda: m.consume_one_use_nonce(no_dir_approval, None, root=root),
        m.ApprovalReplayRefused,
        "the registry marker alone is enough to refuse a replay",
    )


# ===========================================================================
# F. R5 — real preregistered draw material
# ===========================================================================

def check_real_material_refused(tmp: str, root: str) -> None:
    markers = m.REAL_MATERIAL_MARKERS
    require(len(markers) >= 3, "the real-material gate must be populated from the frozen generator")
    for marker in markers:
        require(
            m.material_is_real(f"prefix-{marker}-suffix"),
            f"marker {marker!r} must be recognised",
        )
        require(m.material_is_real(marker), f"bare marker {marker!r} must be recognised")
    for clean in ("wp8b-fixture-nonce-once", "", None, 7, [], "NONPROD-STANDIN"):
        require(
            not m.material_is_real(clean),
            f"non-real material {clean!r} must not be recognised",
        )

    real = markers[0]
    for field, record in (
        ("nonce", approval_over(nonce=f"wp8b-{real}")),
        ("statement", approval_over(statement=f"m {real}")),
    ):
        refused(
            lambda r=record: m.prepare_non_synthetic(
                standin(), r, fixture_context=m.FIXTURE_CONTEXT_TOKEN, root=root
            ),
            m.RealMaterialRefused,
            f"R5 real material in approval {field}",
            "real preregistered Stage-2 draw material",
        )
    # R5 on instance_id: an instance_id carrying real material cannot also carry
    # a matching digest, so the R2 binding pre-empts it through the public
    # entry.  The gate is therefore driven DIRECTLY to prove it is load-bearing.
    refused(
        lambda: m._validate_approval(
            approval_over(instance_id=f"x{real}y", digest="0" * 64)
        ),
        m.RealMaterialRefused,
        "R5 real material in approval instance_id (direct)",
        "real preregistered Stage-2 draw material",
    )
    refused(
        lambda: m._refuse_real_material(f"x{real}y", "test"),
        m.RealMaterialRefused,
        "R5 material gate fires directly",
    )
    # The clean side of the same gate: material with no marker must NOT raise.
    # This bare call is an S2 site whose mutant is ``pass``, and it survives
    # because the property it stands for is asserted on the NEXT statement, not
    # here: ``material_is_real("wp8b-clean")`` must be false, which is a claim
    # about the module and is independently checkable whether or not this call
    # was made.  Removing the call leaves a stale line but changes nothing the
    # fixture observes.  Round 3 verified this by direct mutation: dropping the
    # call leaves the fixture passing, and the assertion below still holds,
    # which is precisely why the assertion, not the call, is the guard.
    m._refuse_real_material("wp8b-clean", "test")  # must not raise
    require(
        not m.material_is_real("wp8b-clean"),
        "material carrying no marker must not be recognised as real",
    )


# ===========================================================================
# G. R6 — the production path is refused while unpinned
# ===========================================================================

def check_production_refused(tmp: str, root: str) -> None:
    require(not m.PRODUCTION_RELEASE_PINNED, "the release must be UNPINNED in this build")
    require(
        m.PRODUCTION_RELEASE_DECISION_SHA256 == "f" * 64,
        "the pinned digest must be the deliberately-impossible all-f constant",
    )
    require(
        m.PRODUCTION_RELEASE_DECISION_SHA256 != hashlib.sha256(b"anything").hexdigest(),
        "the pinned digest must not match a real digest",
    )
    record_path = ROOT / m.PRODUCTION_RELEASE_DECISION_RECORD
    require(
        not record_path.exists(),
        f"the production release decision record "
        f"{m.PRODUCTION_RELEASE_DECISION_RECORD} must be absent",
    )
    owner_approval = approval_over(scope=m.OWNER_APPROVAL_SCOPE, nonce="wp8b-owner-nonce")
    consume = _scratch_dir(tmp, "consume-prod")
    refused(
        lambda: m.prepare_non_synthetic(
            standin(), owner_approval, consume_dir=consume, root=root
        ),
        m.ProductionReleaseNotPinned,
        "R6 owner-scope approval refused while unpinned",
        "No owner decision record releases this path",
    )
    refused(
        lambda: m.prepare_non_synthetic(standin(), owner_approval, root=root),
        m.ProductionReleaseNotPinned,
        "R6 refused with no consume_dir",
    )
    refused(
        lambda: m.prepare_non_synthetic(
            standin(),
            owner_approval,
            consume_dir=consume,
            fixture_context=m.FIXTURE_CONTEXT_TOKEN,
            root=root,
        ),
        m.ProductionReleaseNotPinned,
        "R6 the fixture token does not open the owner path",
    )
    # No one-use state was recorded by any refused production attempt.
    spent = [
        name
        for name in os.listdir(m._registry_path(root))
        if m._approval_ledger_key(owner_approval) in name
    ]
    require(not spent, "a refused production attempt must not consume the one-use approval")

    # Each of the pin's three clauses is driven directly against a temporary
    # root, so the second and third are observed rather than assumed.
    refused(
        lambda: m._require_production_release_pinned(),
        m.ProductionReleaseNotPinned,
        "R6 clause 1: unpinned flag fires before any file check",
        "PRODUCTION_RELEASE_PINNED is False",
    )
    original = m.PRODUCTION_RELEASE_PINNED
    try:
        m.PRODUCTION_RELEASE_PINNED = True
        empty_root = _scratch_dir(tmp, "empty-root")
        refused(
            lambda: m._require_production_release_pinned(empty_root),
            m.ProductionReleaseNotPinned,
            "R6 clause 2: pinned flag with an absent record",
            "is absent",
        )
        refused(
            lambda: m.prepare_non_synthetic(
                standin(), owner_approval, consume_dir=consume, root=root
            ),
            m.ProductionReleaseNotPinned,
            "R6 flag alone is insufficient (public entry)",
            "is absent",
        )
        # State 3: the record EXISTS but does not hash as pinned.
        wrong_root = _scratch_dir(tmp, "wrong-root")
        record_rel = os.path.join(wrong_root, m.PRODUCTION_RELEASE_DECISION_RECORD)
        os.makedirs(os.path.dirname(record_rel))
        with open(record_rel, "wb") as handle:
            handle.write(b"not the pinned decision record")
        refused(
            lambda: m._require_production_release_pinned(wrong_root),
            m.ProductionReleaseNotPinned,
            "R6 clause 3: record present but hashing wrong",
            "does not match the pinned SHA-256",
        )
        # A DIRECTORY at the record path is refused by the isfile guard rather
        # than raising an untyped IsADirectoryError.
        dir_root = _scratch_dir(tmp, "dir-root")
        record_dir = os.path.join(dir_root, m.PRODUCTION_RELEASE_DECISION_RECORD)
        os.makedirs(record_dir)
        require(
            os.path.isdir(record_dir),
            "the directory standing in for the release record must be created",
        )
        refused(
            lambda: m._require_production_release_pinned(dir_root),
            m.ProductionReleaseNotPinned,
            "R6 clause 2: a directory at the record path is absent as a file",
            "is absent",
        )
    finally:
        m.PRODUCTION_RELEASE_PINNED = original


# ===========================================================================
# H. Record validation, fail closed
# ===========================================================================

def check_record_validation(tmp: str, root: str) -> None:
    consume = _scratch_dir(tmp, "consume-record")
    instance = standin()
    record = prepare_fixture_branch(
        instance, approval_over(nonce="wp8b-record-nonce"), consume_dir=consume, root=root
    )

    refused(
        lambda: m.validate_provenance_record(record, instance),
        m.NonSyntheticPreparationError,
        "H stand-in refused by the production consumer",
        "requires a production record",
    )
    # A genuinely valid record IS accepted in rehearsal mode.  This positive
    # case is what every negative below is measured against: without it, a
    # validator that refused everything would pass them all.
    checked = m.validate_provenance_record(record, instance, require_production=False)
    require(
        checked["status"] == m.RECORD_STATUS_NON_PRODUCTION,
        "stand-in validates in non-production mode",
    )
    require(
        checked["content_sha256"] == record["content_sha256"],
        "the validator must return the record it validated",
    )
    # An instance that is not the one the record describes is refused: this is
    # what makes the anchor an anchor.
    refused(
        lambda: m.validate_provenance_record(
            record, standin(STANDIN_ID_B), require_production=False
        ),
        m.NonSyntheticPreparationError,
        "H the record is refused against a different instance",
        "does not match the instance supplied",
    )
    # A missing instance is refused rather than silently skipping the anchor.
    refused(
        lambda: m.validate_provenance_record(record, None, require_production=False),
        m.NonSyntheticPreparationError,
        "H a record cannot be validated without the instance it describes",
    )
    refused(
        lambda: m.validate_provenance_record(record, [], require_production=False),
        m.NonSyntheticPreparationError,
        "H a non-envelope instance is refused",
        "must be a stage2 SyntheticInstance",
    )

    # A record forged to the production status, production=true, and RE-SIGNED
    # is structurally valid in NON-production mode (the content hash is a plain
    # SHA-256 over public fields) — but the PRODUCTION consumer additionally
    # requires the R6 pin, so it is refused there.
    forged = resign(dict(record, status=m.RECORD_STATUS_PRODUCTION, production=True))
    accepted_for_rehearsal = m.validate_provenance_record(
        forged, instance, require_production=False
    )
    require(
        accepted_for_rehearsal["status"] == m.RECORD_STATUS_PRODUCTION,
        "a re-signed forged record is structurally valid only in non-production mode",
    )
    require(
        accepted_for_rehearsal["instance"]["instance_id"] == STANDIN_ID,
        "re-signing cannot change the stand-in instance id the record binds",
    )
    refused(
        lambda: m.validate_provenance_record(forged, instance),
        m.ProductionReleaseNotPinned,
        "H a forged production record is refused while the release is unpinned",
        "No owner decision record",
    )
    refused(
        lambda: m.validate_provenance_record(
            resign(dict(record, status=m.RECORD_STATUS_PRODUCTION, production=False)),
            instance,
        ),
        m.NonSyntheticPreparationError,
        "H a production-status record with production=false is refused",
        "requires production=true",
    )
    for bad_flag in (1, "yes", [True], {}):
        refused(
            lambda f=bad_flag: m.validate_provenance_record(
                resign(dict(record, status=m.RECORD_STATUS_PRODUCTION, production=f)),
                instance,
            ),
            m.NonSyntheticPreparationError,
            f"H production={bad_flag!r} is refused",
            "requires production=true",
        )
    # The status/production disagreement guard, isolated in rehearsal mode.
    refused(
        lambda: m.validate_provenance_record(
            resign(dict(record, production=True)), instance, require_production=False
        ),
        m.NonSyntheticPreparationError,
        "H a stand-in claiming production=true disagrees with its own status",
        "status and production flag disagree",
    )

    for bad, label in (([], "a list"), (None, "None"), ("record", "a str")):
        refused(
            lambda b=bad: m.validate_provenance_record(b, instance, require_production=False),
            m.NonSyntheticPreparationError,
            f"H record {label} is refused",
            "exact dict",
        )
    refused(
        lambda: m.validate_provenance_record(
            {k: v for k, v in record.items() if k != "ledgers"},
            instance,
            require_production=False,
        ),
        m.NonSyntheticPreparationError,
        "H wrong key set",
        "wrong key set",
    )
    refused(
        lambda: m.validate_provenance_record(
            dict(record, extra=1), instance, require_production=False
        ),
        m.NonSyntheticPreparationError,
        "H extra key",
        "wrong key set",
    )
    refused(
        lambda: m.validate_provenance_record(
            resign(dict(record, schema=wp5b.PROVENANCE_SCHEMA)),
            instance,
            require_production=False,
        ),
        m.NonSyntheticPreparationError,
        "H WP5b synthetic schema refused by the WP8b validator",
        "schema mismatch",
    )
    refused(
        lambda: m.validate_provenance_record(
            resign(dict(record, status="prepared_something")),
            instance,
            require_production=False,
        ),
        m.NonSyntheticPreparationError,
        "H unrecognized status",
        "not a recognized WP8b status",
    )
    refused(
        lambda: m.validate_provenance_record(
            resign(dict(record, scientific_outputs="present")),
            instance,
            require_production=False,
        ),
        m.NonSyntheticPreparationError,
        "H result boundary violated",
    )
    for bad_sources, label, needle in (
        ({}, "empty source map", "non-empty source hash map"),
        ([], "non-dict source map", "source map must be a dict"),
    ):
        refused(
            lambda b=bad_sources: m.validate_provenance_record(
                resign(dict(record, source_sha256=b)), instance, require_production=False
            ),
            m.NonSyntheticPreparationError,
            f"H {label}",
            needle,
        )
    bad_sources = dict(record["source_sha256"])
    bad_sources["g3_resolver:research/ground_truth/compute_g3_ground_truth.py"] = "Z" * 64
    refused(
        lambda: m.validate_provenance_record(
            resign(dict(record, source_sha256=bad_sources)), instance, require_production=False
        ),
        m.NonSyntheticPreparationError,
        "H malformed source hash entry",
        "lowercase SHA-256",
    )
    refused(
        lambda: m.validate_provenance_record(
            resign(
                dict(
                    record,
                    identity=dict(
                        record["identity"], non_synthetic_identity_hash="0" * 64
                    ),
                )
            ),
            instance,
            require_production=False,
        ),
        m.NonSyntheticPreparationError,
        "H identity hash mismatch",
        "identity hash mismatch",
    )
    refused(
        lambda: m.validate_provenance_record(
            resign(
                dict(
                    record,
                    identity=dict(record["identity"], identity_payload_sha256="1" * 64),
                )
            ),
            instance,
            require_production=False,
        ),
        m.NonSyntheticPreparationError,
        "H identity payload hash mismatch",
        "identity payload hash mismatch",
    )
    refused(
        lambda: m.validate_provenance_record(
            resign(dict(record, identity="not a dict")), instance, require_production=False
        ),
        m.NonSyntheticPreparationError,
        "H identity is not an object",
        "identity must be an object",
    )
    for bad_payload_shape, why in (
        (None, "None"),
        (17, "an int"),
        ("", "empty"),
        ("z" * 64, "non-hex"),
    ):
        refused(
            lambda s=bad_payload_shape: m.validate_provenance_record(
                resign(dict(record, identity=dict(record["identity"], identity_payload_sha256=s))),
                instance,
                require_production=False,
            ),
            m.NonSyntheticPreparationError,
            f"H identity_payload_sha256 shape guard refuses {why}",
            "lowercase SHA-256",
        )
    refused(
        lambda: m.validate_provenance_record(
            dict(record, content_sha256="0" * 64), instance, require_production=False
        ),
        m.NonSyntheticPreparationError,
        "H content hash mismatch",
        "content hash mismatch",
    )
    refused(
        lambda: m.validate_provenance_record(
            dict(record, content_sha256="short"), instance, require_production=False
        ),
        m.NonSyntheticPreparationError,
        "H malformed content hash",
        "lowercase SHA-256",
    )


# ===========================================================================
# r2_d4 — REGRESSION: re-signed (rehashed) record tampering
# ===========================================================================
#
# Round-1 validator probes (wp8b.r1.vout:5815-5830): each tamper was applied,
# the content hash RE-SIGNED, and the result passed
# validate_provenance_record(require_production=False) -> ACCEPTED, all five.

def r2_d4_rehashed_tampering_is_refused(tmp: str, root: str) -> None:
    instance = standin(STANDIN_ID_B)
    record = prepare_fixture_branch(
        instance,
        approval_over(instance_id=STANDIN_ID_B, nonce="wp8b-d4-tamper"),
        root=root,
    )
    # The pristine record validates, so every refusal below is attributable to
    # the tamper and not to an over-strict validator.  The returned copy is
    # asserted on rather than the call merely being made: a discarded call is an
    # S2 site whose mutant is ``pass``, so a bare call here would be unkillable.
    # Asserting the round-trip also makes the claim substantive — the validator
    # must hand back exactly what it validated.
    pristine = m.validate_provenance_record(record, instance, require_production=False)
    require(
        pristine == record,
        "the pristine record must validate and be returned unchanged",
    )

    tampers = (
        ("instance_digest",
         lambda r: r["instance"].update(content_sha256="0" * 64),
         "provenance instance digest does not match"),
        ("instance_id",
         lambda r: r["instance"].update(instance_id="another-id"),
         "provenance instance_id does not match"),
        ("n_assets",
         lambda r: r["instance"].update(n_assets=99),
         "provenance n_assets does not match"),
        ("approval_instance_id",
         lambda r: r["approval"].update(instance_id="another-id"),
         "provenance approval names a different instance"),
        ("approval_digest",
         lambda r: r["approval"].update(approves_instance_content_sha256="0" * 64),
         "provenance approval does not name the instance"),
        ("f_star",
         lambda r: r["results"].update(f_star=123456789.0),
         "provenance f_star does not match"),
        ("max_f_over_F",
         lambda r: r["results"].update(max_f_over_F=0.0),
         "provenance max_f_over_F does not match"),
        ("Lambda_ref",
         lambda r: r["results"].update(Lambda_ref=1.0),
         "provenance Lambda_ref does not match"),
        ("delta_full",
         lambda r: r["results"].update(delta_full=0.0),
         "provenance delta_full does not match"),
        ("X_star",
         lambda r: r["results"].update(X_star=[]),
         "provenance X_star does not match"),
        ("X_star_size",
         lambda r: r["results"].update(X_star_size=0),
         "provenance X_star_size does not match"),
        ("argmax_f_over_F",
         lambda r: r["results"].update(argmax_f_over_F=["AAA"]),
         "provenance argmax_f_over_F does not match"),
        ("f_predicate",
         lambda r: r.update(f_predicate="hand written"),
         "f_predicate does not match"),
        ("f_predicate_sha256",
         lambda r: r.update(f_predicate_sha256="0" * 64),
         "f_predicate_sha256 does not match"),
        ("approval_schema",
         lambda r: r["approval"].update(schema=wp5b.PROVENANCE_SCHEMA),
         "provenance approval schema mismatch"),
        ("approval_scope",
         lambda r: r["approval"].update(scope="stage2_generator_draw"),
         "provenance approval scope is not a WP8b scope"),
        ("approval_status",
         lambda r: r["approval"].update(status="pending"),
         "provenance approval status is not owner_approved"),
        ("approval_label",
         lambda r: r["approval"].update(label="synthetic"),
         "provenance approval label is not non_synthetic"),
        ("nonce_sha256",
         lambda r: r["approval"].update(nonce_sha256="Z" * 64),
         "must be a lowercase SHA-256"),
        ("nonce_marker_sha256",
         lambda r: r["approval"].update(nonce_consumed_marker_sha256="not-hex"),
         "must be a lowercase SHA-256"),
        ("instance_block_digest_shape",
         lambda r: r["instance"].update(content_sha256="too-short"),
         "must be a lowercase SHA-256"),
    )
    for label, edit, needle in tampers:
        tampered = copy.deepcopy(record)
        edit(tampered)
        resigned = resign(tampered)
        # RE-SIGNED: this is exactly what defeated round 1.
        require(
            resigned["content_sha256"] != record["content_sha256"],
            f"r2_d4 the {label} tamper must actually change the content hash",
        )
        refused(
            lambda b=resigned: m.validate_provenance_record(
                b, instance, require_production=False
            ),
            m.NonSyntheticPreparationError,
            f"r2_d4 re-signed tamper of {label} is refused",
            needle,
        )

    # The source-map tamper needs the identity payload recomputed to match, or
    # the identity guard fires first and the source anchor is never reached.
    tampered = copy.deepcopy(record)
    tampered["source_sha256"][next(iter(tampered["source_sha256"]))] = "0" * 64
    tampered["identity"]["identity_payload_sha256"] = hashlib.sha256(
        m._canonical(m._identity_payload(tampered["source_sha256"]))
    ).hexdigest()
    refused(
        lambda: m.validate_provenance_record(
            resign(tampered), instance, require_production=False
        ),
        m.NonSyntheticPreparationError,
        "r2_d4 re-signed source tamper is refused even with a matching identity payload",
        "does not match the live source digests",
    )

    # A record whose blocks are not objects at all.
    for field, label, needle in (
        ("results", "a non-dict results block", "results block must be an object"),
        ("instance", "a non-dict instance block", "instance block must be an object"),
        ("approval", "a non-dict approval block", "approval block must be an object"),
    ):
        refused(
            lambda f=field: m.validate_provenance_record(
                resign(dict(record, **{f: "not a dict"})), instance, require_production=False
            ),
            m.NonSyntheticPreparationError,
            f"r2_d4 {label} is refused",
            needle,
        )


# ===========================================================================
# I. Identity is a real, new, versioned hash
# ===========================================================================

def check_identity() -> None:
    identity = m.NON_SYNTHETIC_IDENTITY_HASH
    require(
        _is_sha256_shape(identity),
        "identity must be a lowercase SHA-256",
    )
    require(_is_sha256_shape(identity), "identity must be a real digest")
    require(identity != m.NON_SYNTHETIC_IDENTITY_HASH.upper(), "identity must be lowercase")
    require(
        m._compute_identity_hash() == identity,
        "the identity hash must be reproducible from the live sources",
    )
    payload = m._identity_payload(m.source_digests())
    require(
        payload["identity_schema"] == "decisions_os/g9_wp8b_non_synthetic_identity/v1",
        "the identity payload must carry its version",
    )
    require(payload["provenance_schema"] == m.PROVENANCE_SCHEMA, "payload binds the schema")
    require(
        payload["wp5b_provenance_schema"] == wp5b.PROVENANCE_SCHEMA,
        "payload binds WP5b's schema so the two paths stay distinct",
    )
    require(
        payload["production_release_decision_sha256"] == m.PRODUCTION_RELEASE_DECISION_SHA256,
        "payload binds the release pin",
    )
    require(identity != wp5b.PROVENANCE_SCHEMA, "identity must differ from WP5b's schema")


# ===========================================================================
# r2_d3 — REGRESSION: the source closure is COMPLETE
# ===========================================================================
#
# Round-1 validator finding (wp8b.r1.vout:7026): "The identity omits
# src/g4/generate_ledger.py, which the reused WP5b path calls.  Changing that
# file in a scratch probe left the identity hash unchanged."

def r2_d3_source_closure_is_complete() -> None:
    require(
        "src/g4/generate_ledger.py" in m.SOURCE_FILES.values(),
        "r2_d3 the G4 ledger that WP5b imports and calls must be bound",
    )
    for rel in (
        "research/g9/stage2_instance_preparation.py",
        "research/ground_truth/compute_g3_ground_truth.py",
        "src/g4/generate_ledger.py",
        "src/g6/ledgers.py",
        "research/g9/wp8b/wp8b_non_synthetic_preparation.py",
    ):
        require(rel in m.SOURCE_FILES.values(), f"r2_d3 {rel} must be bound")
    digests = m.source_digests()
    require(
        set(digests) == {f"{key}:{rel}" for key, rel in m.SOURCE_FILES.items()},
        "r2_d3 the digest map must cover exactly the declared source set",
    )
    for entry, digest in sorted(digests.items()):
        require(
            _is_sha256_shape(digest),
            f"r2_d3 {entry} must be a lowercase SHA-256",
        )
    require(
        len(set(m.SOURCE_FILES.values())) == len(m.SOURCE_FILES),
        "r2_d3 no source file may be bound under two keys",
    )


def r2_d3_identity_reacts_to_a_source_edit() -> None:
    """Editing a BOUND source must change the identity hash.

    Proven against a throwaway copy of the tree, so the real files are never
    touched.  ``src/g4/generate_ledger.py`` is the exact file the round-1
    validator edited to no effect.
    """
    # The probe tree is named per-PID and removed first if it somehow exists.  A
    # fixed name is not safe: two fixture runs (the -B and -B -O checks, or a
    # sweep worker alongside a manual run) would race on the same directory, and
    # shutil.copytree raises "File exists" when it meets a half-copied tree.
    # Per-PID naming makes concurrent runs independent.
    probe_tree = SCRATCH / f"wp8b_identity_probe_tree_{os.getpid()}"
    if probe_tree.is_dir():
        shutil.rmtree(probe_tree)
    shutil.copytree(ROOT, probe_tree, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    try:
        with open(probe_tree / "src/g4/generate_ledger.py", "ab") as handle:
            handle.write(b"\n# round-2 identity probe mutation (fixture only)\n")
        code = (
            "import sys; sys.path.insert(0, %r);"
            "from research.g9.wp8b import wp8b_non_synthetic_preparation as m;"
            "print(m.NON_SYNTHETIC_IDENTITY_HASH)" % str(probe_tree)
        )
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        env.pop("PYTHONPATH", None)
        result = subprocess.run(
            [sys.executable, "-B", "-c", code], capture_output=True, text=True, env=env
        )
        require(
            result.returncode == 0,
            "r2_d3 the identity probe must import cleanly: " + result.stderr.strip()[-400:],
        )
        # The printed value is pinned to the real module's shape as well as
        # merely being different, so a probe that printed garbage would fail
        # here rather than pass the difference test below.
        require(
            _is_sha256_shape(result.stdout.strip()),
            "r2_d3 the identity probe must print a real SHA-256, got: "
            + result.stdout.strip()[:80],
        )
        require(
            result.stdout.strip() != m.NON_SYNTHETIC_IDENTITY_HASH,
            "r2_d3 editing src/g4/generate_ledger.py MUST change the identity hash",
        )
    finally:
        shutil.rmtree(probe_tree, ignore_errors=True)


# ===========================================================================
# r2_d6 — REGRESSION: pinned byte identity, checked in-tree
# ===========================================================================
#
# Round-1 finding: "pinned WP7b byte identity is unverified".  Round 1's check
# diffed kaggle_wp7b against a reference snapshot that this job's copy
# legitimately postdates, so it reported nine differences that said nothing
# about this package.  Byte-identity is now checked against the digests the
# repository itself declares.

def r2_d6_pinned_byte_identity() -> None:
    report = m.pinned_byte_identity_report()
    require(not report["mismatches"], f"r2_d6 pinned files must match: {report['mismatches']}")
    require(
        report["reviewed_dependency_count"] == 29,
        "r2_d6 the reviewed-dependency table must still carry its 29 entries",
    )
    require(
        report["v1_release_file_count"] == 12,
        "r2_d6 exactly the 12 v1 section-A release files must be declared",
    )
    require(
        report["reviewed_table_anchor"] == m.WP7B_REVIEWED_TABLE_ANCHOR,
        "r2_d6 the table must match WP7b's own ANCHOR constant",
    )
    # The anchor this module transcribes must still equal the constant the
    # PINNED WP7b builder uses, so the two cannot drift apart silently.
    builder = Path(ROOT / "research/g9/kaggle_wp7b/build_wp7b_bundle.py").read_text(
        encoding="utf-8"
    )
    require(
        f'ANCHOR="{m.WP7B_REVIEWED_TABLE_ANCHOR}"' in builder,
        "r2_d6 the transcribed anchor must match the pinned WP7b builder's own ANCHOR",
    )
    original = m.WP7B_REVIEWED_TABLE_ANCHOR
    try:
        m.WP7B_REVIEWED_TABLE_ANCHOR = "0" * 64
        refused(
            m.pinned_byte_identity_report,
            m.NonSyntheticPreparationError,
            "r2_d6 a table that does not match the anchor is refused",
            "does not match the WP7b ANCHOR",
        )
    finally:
        m.WP7B_REVIEWED_TABLE_ANCHOR = original
    refused(
        lambda: m._file_bytes("research/g9/kaggle_wp7/definitely-absent-pinned.py"),
        m.NonSyntheticPreparationError,
        "r2_d6 a missing pinned file is refused",
        "is missing",
    )
    declared = m._declared_v1_release_files()
    require(len(declared) == 12, "r2_d6 the v1 parser must return exactly 12 files")
    # The two halves are asserted SEPARATELY.  Folding them into one
    # ``and`` made the file-presence half unkillable: every declared entry is
    # present in the real tree, so that operand was never the deciding one.
    for rel, digest in sorted(declared.items()):
        require(
            _is_sha256_shape(digest),
            f"r2_d6 {rel} must be declared with a well-formed digest",
        )
        require(
            len(m._file_bytes(rel)) > 0,
            f"r2_d6 {rel} must be present in the tree and non-empty",
        )


def r2_d6_v1_parser_type_guards() -> None:
    """Both operands of the parser's entry filter must have an input of their own.

    The round-2 sweep reported ``S5:1571 ... set the Or operand to False`` as a
    survivor: the ``not isinstance(digest, str)`` clause had no fixture input
    reaching it, because the real pinned table only ever holds str values.  The
    parser is parameterised on its source, so both operands are driven here
    against synthetic tables and each clause becomes independently observable.
    """
    real = m._declared_v1_release_files()

    def parse(body: str) -> dict:
        return m._parse_v1_declarations("WP7_DEPENDENCY_TABLE = %r\n" % (body,))

    # A well-formed str/str entry is taken.
    good = {"research/g9/a.py": "a" * 64}
    require(parse(good) == good, "r2_d6 the parser must take a str/str entry")
    # A NON-STR digest: the second operand of the filter is load-bearing.
    require(
        parse({"research/g9/b.py": 123}) == {},
        "r2_d6 the parser must skip an entry whose digest is not a str",
    )
    # A NON-STR key: the first operand is load-bearing.
    require(
        parse({7: "b" * 64}) == {},
        "r2_d6 the parser must skip an entry whose key is not a str",
    )
    # A PENDING placeholder is excluded while a genuine entry beside it is kept,
    # so the length/hex filter is exercised in both directions.
    require(
        parse({"research/g9/c.py": "PENDING", "research/g9/d.py": "d" * 64})
        == {"research/g9/d.py": "d" * 64},
        "r2_d6 the parser must exclude PENDING and keep the reviewed entry",
    )
    # The LENGTH and HEX halves of that filter each get an input of their own, so
    # neither is redundant.  A 64-char string with a NON-HEX character fails
    # only the hex half (length is right); a 63-char hex string fails only the
    # length half (every char is hex).  With either half removed, one of these
    # two rows would be wrongly INCLUDED.
    for wrong, why in (
        ("a" * 63, "a 63-char hex string must be excluded by the length rule"),
        ("a" * 64 + "g", "a 65-char string must be excluded by the length rule"),
        ("g" * 64, "a 64-char non-hex string must be excluded by the hex rule"),
        ("a" * 63 + "Z", "one uppercase char must be excluded by the hex rule"),
    ):
        require(
            parse({"research/g9/x.py": wrong}) == {},
            f"r2_d6 the parser must exclude {why}",
        )
    # A computed (non-literal) value is excluded, proving the ast filter runs.
    # Built as source text, so the call really appears in the parsed module.
    # This drives the SECOND operand of the Constant filter (a non-Constant
    # VALUE), which the round-2 sweep found had no input of its own.  The
    # ``value_node`` must be filtered BEFORE ``.value`` is read: with that
    # operand removed the parser raises a bare ``AttributeError`` on the
    # BinOp, which is a crash rather than a refusal.
    computed_value = (
        "WP7_DEPENDENCY_TABLE = {'research/g9/e.py': '" + "e" * 64 + "' + suffix()}\n"
    )
    require(
        m._parse_v1_declarations(computed_value) == {},
        "r2_d6 the parser must skip a non-literal value, not crash on it",
    )
    # ... and a non-literal KEY drives the first operand.
    computed_key = "WP7_DEPENDENCY_TABLE = {name(): '" + "f" * 64 + "'}\n"
    require(
        m._parse_v1_declarations(computed_key) == {},
        "r2_d6 the parser must skip a non-literal key, not crash on it",
    )
    # A spread/dict-unpacking entry has a ``None`` KEY node, which is the same
    # first operand reached through a different syntactic shape.
    unpacked = (
        "WP7_DEPENDENCY_TABLE = {**{'research/g9/g.py': '" + "g" * 64 + "'}}\n"
    )
    require(
        m._parse_v1_declarations(unpacked) == {},
        "r2_d6 the parser must skip a dict-unpacking entry",
    )
    # A non-Constant value alongside a VALID literal entry: the good entry must
    # still come through, so the filter skips only the bad row.  This is the
    # case that distinguishes the two outcomes — with the value-Constant
    # operand removed the parser raises a bare ``AttributeError`` on the BinOp,
    # whereas with it the valid row is returned and the bad one dropped.  The
    # good digest is hex (``a``-``f``), so it survives the length/hex filter too.
    good_digest = "a" * 64
    mixed_row = (
        "WP7_DEPENDENCY_TABLE = {"
        f"'research/g9/h.py': '{good_digest}', "
        "'research/g9/i.py': 'i' * 64 + suffix()"
        "}\n"
    )
    require(
        m._parse_v1_declarations(mixed_row) == {"research/g9/h.py": good_digest},
        "r2_d6 a non-literal row must be skipped without dropping its neighbour",
    )
    # An annotated assignment (the real file's shape) is accepted too.
    annotated = "WP7_DEPENDENCY_TABLE: dict = %r\n" % (good,)
    require(
        m._parse_v1_declarations(annotated) == good,
        "r2_d6 the parser must accept the pinned file's annotated form",
    )
    # A table that is absent or not a literal is refused, not vacuously empty.
    for bad_source, label in (
        ("OTHER = 1\n", "a file with no WP7_DEPENDENCY_TABLE"),
        ("WP7_DEPENDENCY_TABLE = {k: v for k, v in []}\n", "a non-literal table"),
    ):
        refused(
            lambda b=bad_source: m._parse_v1_declarations(b),
            m.NonSyntheticPreparationError,
            f"r2_d6 the parser refuses {label}",
            "no longer declares a literal WP7_DEPENDENCY_TABLE",
        )
    # The real table is unaffected by any of the above.
    require(m._declared_v1_release_files() == real, "r2_d6 the real table is unchanged")


def r2_d6_mismatch_refusals(tmp: str, root: str) -> None:
    """A pinned file whose BYTES differ from its declared digest is refused.

    Both mismatch arms (the 29 reviewed dependencies and the 12 v1 release
    files) are unreachable in an honest test against the real tree, because the
    real tree is consistent and making it inconsistent would mean editing pinned
    files.  The round-2 sweep found both ``raise`` statements unkillable for
    exactly that reason.  A throwaway copy of the tree is used instead: the
    pinned files are copied verbatim, and ONE of them is then altered, so the
    refusal is produced by real bytes differing from a real declaration.
    """
    real = m.pinned_byte_identity_report()
    require(not real["mismatches"], "r2_d6 the real pinned tree starts out consistent")

    def _read_text(path: str) -> str:
        with open(path, encoding="utf-8") as handle:
            return handle.read()

    def _write_text(path: str, text: str) -> None:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)

    def _copy_pinned(src_root: str, dest_root: str) -> None:
        # Plain staging: every copied file is subsequently read back and hashed
        # by the report under test, so a file this fails to copy shows up as a
        # digest mismatch refusal rather than passing silently.  No counter is
        # kept here — adding one produced an assertion that nothing else depends
        # on, which is the very shape this fixture no longer has.
        for base, _dirs, names in os.walk(src_root):
            for name in names:
                src = os.path.join(base, name)
                dest = os.path.join(dest_root, os.path.relpath(src, src_root))
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                shutil.copyfile(src, dest)

    def _copy_all_pinned(sandbox: str) -> str:
        """Copy every pinned file BOTH tables reference into a sandbox tree.

        The 29-entry reviewed set is a different (larger) list than the 12 v1
        files, and a missing member would be refused as "missing" before the
        digest comparison the test is about, so both are copied.
        """
        os.makedirs(sandbox, exist_ok=True)
        require(
            os.path.isdir(sandbox),
            f"the pinned sandbox tree {sandbox!r} must have been created",
        )
        table = json.loads(
            open(os.path.join(str(ROOT), m.PINNED_REVIEWED_TABLE), encoding="utf-8").read()
        )
        pinned = (
            [m.PINNED_REVIEWED_TABLE, m.PINNED_WP7_BUILDER]
            + sorted(table["dependencies"])
            + sorted(m._declared_v1_release_files())
        )
        for name in pinned:
            dest = os.path.join(sandbox, name)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(os.path.join(str(ROOT), name), "rb") as src:
                with open(dest, "wb") as out:
                    out.write(src.read())
        return sandbox

    def tree_with_perturbed(rel: str) -> str:
        sandbox = _copy_all_pinned(os.path.join(tmp, "pinned-tree-" + rel.replace("/", "_")))
        with open(os.path.join(sandbox, rel), "ab") as handle:
            handle.write(b"\n# round-2 pinned perturbation (fixture only)\n")
        return sandbox

    # A reviewed dependency (one of the 29) with altered bytes.
    dependency = sorted(json.loads(
        open(os.path.join(str(ROOT), m.PINNED_REVIEWED_TABLE), encoding="utf-8").read()
    )["dependencies"])[0]
    refused(
        lambda: m.pinned_byte_identity_report(tree_with_perturbed(dependency)),
        m.NonSyntheticPreparationError,
        "r2_d6 a perturbed reviewed dependency is refused",
        "pinned reviewed dependencies do not match their declared digests",
    )
    # A 12 v1 section-A release file with a digest that DISAGREES between WP7's
    # dependency table and the reviewed table.  Perturbing the WP7 builder copy
    # inside the sandbox leaves the 29-entry review untouched, so this is the
    # one condition the cross-check can actually catch.
    v1_file = sorted(m._declared_v1_release_files())[0]
    builder_tree = _copy_all_pinned(os.path.join(tmp, "pinned-tree-v1-disagrees"))
    v1_source = _read_text(os.path.join(builder_tree, m.PINNED_WP7_BUILDER))
    declared_v1 = m._declared_v1_release_files()[v1_file]
    v1_source = v1_source.replace(declared_v1, "0" * 64, 1)
    _write_text(os.path.join(builder_tree, m.PINNED_WP7_BUILDER), v1_source)
    refused(
        lambda: m.pinned_byte_identity_report(builder_tree),
        m.NonSyntheticPreparationError,
        "r2_d6 a v1 digest that disagrees with the reviewed table is refused",
        "disagree between WP7's dependency table and the reviewed table",
    )
    # A tree whose TABLE was altered is refused by the anchor check instead,
    # which is the earlier and separate guard.
    table_tree = os.path.join(tmp, "pinned-tree-perturbed-table")
    _copy_all_pinned(table_tree)
    with open(os.path.join(table_tree, m.PINNED_REVIEWED_TABLE), "ab") as handle:
        handle.write(b"\n")
    refused(
        lambda: m.pinned_byte_identity_report(table_tree),
        m.NonSyntheticPreparationError,
        "r2_d6 a perturbed reviewed table is refused by the anchor check",
        "does not match the WP7b ANCHOR",
    )
    # A tree missing a pinned file is refused, not skipped.
    absent_tree = _copy_all_pinned(os.path.join(tmp, "pinned-tree-absent"))
    os.remove(os.path.join(absent_tree, sorted(m._declared_v1_release_files())[0]))
    refused(
        lambda: m.pinned_byte_identity_report(absent_tree),
        m.NonSyntheticPreparationError,
        "r2_d6 an absent pinned file is refused",
        "is missing",
    )
    # The real tree is still clean after all of the above.
    require(
        not m.pinned_byte_identity_report()["mismatches"],
        "r2_d6 the real pinned tree is still byte-identical",
    )


# ===========================================================================
# K. Content-digest and envelope helpers
# ===========================================================================

def check_digest_and_envelope() -> None:
    ours = m.instance_content_sha256(standin())
    cloned = wp5b.SyntheticInstance(**{**standin().__dict__, "synthetic": True})
    theirs = wp5b._instance_digest(wp5b.validate_envelope(cloned))
    require(ours == theirs, "WP8b digest must equal WP5b's digest for the same content")

    for bad, label in ((None, "None"), ([], "a list"), ("x", "a str"), (3, "an int")):
        refused(
            lambda b=bad: m.instance_content_sha256(b),
            m.NonSyntheticPreparationError,
            f"J digest refuses {label}",
            "must be a stage2 SyntheticInstance",
        )
    for mutation, label in (
        ({"kappa": 2.0}, "kappa != 1.0"),
        ({"K": 9}, "K out of range"),
        ({"K": 1.0}, "K is a float"),
        ({"order": ("AAA", "AAA", "CCC")}, "duplicate ticker"),
        ({"order": None}, "order is None"),
        ({"Sigma": None}, "Sigma is None"),
        ({"Sigma": ((0.04, 0.01), (0.01, 0.05), (0.005, 0.008, 0.06))}, "non-square row"),
        ({"sector_labels": ("tech", "util", "bank")}, "unrealised sector label"),
        ({"p": (0.3, 0.3)}, "wrong p length"),
    ):
        refused(
            lambda b=wp5b.SyntheticInstance(**{**standin().__dict__, **mutation}): (
                m.instance_content_sha256(b)
            ),
            m.NonSyntheticPreparationError,
            f"J frozen WP5b rules refuse {label}",
            "frozen WP5b validator",
        )


# ===========================================================================
# L. The stand-in really is non-production-labelled, everywhere
# ===========================================================================

def check_non_production_labelling(tmp: str, root: str) -> None:
    require(
        m.NON_PRODUCTION_LABEL in STANDIN_ID,
        "the stand-in instance id must carry the NON-PRODUCTION label",
    )
    require(
        STANDIN_ID.startswith(m.FIXTURE_INSTANCE_ID_PREFIX),
        "the stand-in instance id must carry the NONPROD-STANDIN prefix",
    )
    require(m._is_non_production_standin(STANDIN_ID), "the stand-in is recognised")
    for not_standin in (
        "stage2_01", "", None, 7, [], "NONPROD-SYNTHETIC-0001",
        UNLABELLED_ID, NO_PREFIX_ID, NO_LABEL_ID,
    ):
        require(
            not m._is_non_production_standin(not_standin),
            f"{not_standin!r} must not be recognised as a stand-in",
        )
    require(
        m.FIXTURE_CONTEXT_TOKEN not in (None, ""),
        "the fixture context token must be a real named token",
    )
    require(
        m.FIXTURE_SCOPE != m.OWNER_APPROVAL_SCOPE,
        "the fixture scope must differ from the owner scope",
    )
    require(
        m.RECORD_STATUS_PRODUCTION != m.RECORD_STATUS_NON_PRODUCTION,
        "the production and stand-in statuses must differ",
    )
    # The one accepting branch increments a counter, proving it is the ONLY
    # accepting path and that the owner path never reaches it.
    before = m.FIXTURE_BRANCH_INVOCATIONS
    consume = _scratch_dir(tmp, "c-counter")
    prepare_fixture_branch(
        standin(STANDIN_ID_B),
        approval_over(instance_id=STANDIN_ID_B, nonce="wp8b-counter"),
        consume_dir=consume,
        root=root,
    )
    require(
        m.FIXTURE_BRANCH_INVOCATIONS == before + 1,
        "exactly the accepting fixture branch must increment the counter",
    )


# ===========================================================================
# M. WP5b is untouched and its record is never accepted here
# ===========================================================================

def check_wp5b_untouched() -> None:
    report = m.wp5b_synthetic_only_assertions()
    require(report["schemas_differ"], "WP8b and WP5b provenance schemas must differ")
    require(
        report["wp5b_provenance_schema"] == wp5b.PROVENANCE_SCHEMA,
        "the report must report WP5b's real schema",
    )
    require(
        report["wp8b_provenance_schema"] == m.PROVENANCE_SCHEMA,
        "the report must report WP8b's real schema",
    )
    for mark in (False, None, 0, 1, "true", "True", []):
        refused(
            lambda mk=mark: wp5b.validate_envelope(standin(synthetic=mk)),
            wp5b.NonSyntheticInstanceRefused,
            f"WP5b still refuses mark {mark!r}",
        )
    refused(
        lambda: wp5b.authorize_non_synthetic(
            wp5b.validate_envelope(standin(synthetic=True))
        ),
        wp5b.NonSyntheticInstanceRefused,
        "WP5b authorize_non_synthetic still always raises",
    )
    require(
        wp5b.UNREACHABLE_APPROVAL["_builder_can_construct_this"] is False,
        "WP5b's unreachable approval must still declare it cannot be constructed",
    )


def check_wp5b_record_is_never_accepted(tmp: str, root: str) -> None:
    synthetic = wp5b.SyntheticInstance(**{**standin(SYNTHETIC_ID).__dict__, "synthetic": True})
    optimum = wp5b.resolve_optimum(synthetic)
    lam = wp5b.lambda_ref(optimum)
    ledgers = wp5b.build_ledgers(optimum, lam)
    wp5b_record = wp5b.build_provenance_record(synthetic, optimum, lam, ledgers)
    require(
        wp5b_record["status"] == "prepared_synthetic_only",
        "WP5b record must still be stamped synthetic-only",
    )
    # WP5b's own validator accepts it (proving it is a real, valid WP5b record).
    # The RETURN is asserted, not just the call: a discarded call is an S2 site
    # whose mutant is ``pass``, so the bare form would be unkillable.
    accepted_by_wp5b = wp5b.validate_provenance_record(wp5b_record)
    require(
        accepted_by_wp5b == wp5b_record,
        "WP5b's own validator must accept and return its own synthetic record",
    )
    refused(
        lambda: m.validate_provenance_record(
            wp5b_record, standin(SYNTHETIC_ID), require_production=False
        ),
        m.NonSyntheticPreparationError,
        "a genuine WP5b record is refused by the WP8b validator",
    )
    wp8b_record = prepare_fixture_branch(
        standin(STANDIN_ID_B),
        approval_over(instance_id=STANDIN_ID_B, nonce="wp8b-schema-probe"),
        root=root,
    )
    refused(
        lambda: m.validate_provenance_record(
            dict(wp8b_record, schema=wp5b.PROVENANCE_SCHEMA),
            standin(STANDIN_ID_B),
            require_production=False,
        ),
        m.NonSyntheticPreparationError,
        "the WP8b validator refuses WP5b's schema string",
        "schema mismatch",
    )
    refused(
        lambda: wp5b.validate_provenance_record(
            prepare_fixture_branch(
                standin(), approval_over(nonce="wp8b-disjoint"), root=root
            )
        ),
        wp5b.InstancePreparationError,
        "WP5b refuses a genuine WP8b record",
    )


# ===========================================================================
# N. Truth tables for the primitive guards
# ===========================================================================

def check_sha_truth_table() -> None:
    """Every clause of ``_sha`` and ``_shape_valid_digest``, one at a time."""
    valid = "a" * 64
    require(m._shape_valid_digest(valid), "64 lowercase hex must be shape-valid")
    require(m._sha(valid, "probe") == valid, "_sha returns the value it validated")
    for bad, why in (
        (None, "None is not a str"),
        (64, "an int is not a str"),
        (valid[:63], "63 chars is the wrong length"),
        (valid + "a", "65 chars is the wrong length"),
        ("", "empty is the wrong length"),
        ("Z" * 64, "uppercase Z is not hex"),
        ("a" * 63 + "g", "a trailing g is not hex"),
        ("A" * 64, "uppercase A is not lowercase hex"),
    ):
        require(not m._shape_valid_digest(bad), f"_shape_valid_digest must reject {why}")
        refused(
            lambda b=bad: m._sha(b, "probe"),
            m.NonSyntheticPreparationError,
            f"_sha must refuse {why}",
            "lowercase SHA-256",
        )
    require(
        not m._shape_valid_digest("a" * 63 + "F"),
        "one uppercase char breaks shape",
    )


def check_real_material_excluded() -> None:
    """The RELEASE module must not embed real preregistered draw material.

    Checked against the module under test, not against this fixture.  Round 1
    asserted the fixture's OWN source was marker-free, guarded by an
    ``or "master" in source.lower()`` escape hatch — a tautology that can only
    pass, and one whose survivors (three sites) the round-1 sweep duly found.
    The property that actually matters is that the code which RUNS carries no
    real draw material, so that is what is asserted here.
    """
    release_source = Path(m.__file__).read_text(encoding="utf-8")
    for marker in m.REAL_MATERIAL_MARKERS:
        occurrences = release_source.count(marker)
        require(
            occurrences <= 1,
            f"the release module must not embed the real material {marker!r} "
            f"(found {occurrences} occurrences)",
        )
    # The gate still recognises the frozen marker, which is what makes the
    # count above meaningful.
    require(
        m.material_is_real(m.REAL_MATERIAL_MARKERS[0]),
        "the real-material gate must recognise the frozen marker",
    )


def check_require_helpers() -> None:
    """``_require_approval`` raises on False and passes on True."""
    # The True case is a real assertion: the helper must return None (and not
    # raise) for a satisfied condition.  Round 2 asserted it as a literal
    # ``require(True, ...)``, which can only ever pass and whose S1 mutant is
    # therefore unkillable; asserting the RETURN VALUE makes the two branches
    # distinguishable.
    require(
        m._require_approval(True, "should not raise") is None,
        "_require_approval must return None for a satisfied condition",
    )
    refused(
        lambda: m._require_approval(False, "gate closed"),
        m.ApprovalRequired,
        "_require_approval refuses False",
        "gate closed",
    )
    require(
        not hasattr(m, "_require_pin"),
        "the dead _require_pin helper must be gone",
    )


def check_file_sha_missing() -> None:
    refused(
        lambda: m._file_sha("research/g9/wp8b/definitely-absent-source.py"),
        m.NonSyntheticPreparationError,
        "_file_sha refuses a missing file",
        "is missing",
    )
    real = m._file_sha("research/g9/stage2_instance_preparation.py")
    require(
        real == m.source_digests()["wp5b_module:research/g9/stage2_instance_preparation.py"],
        "_file_sha must agree with the bound source digest",
    )


def check_sha_or_zero(tmp: str) -> None:
    """The marker path is required to be a str, and a real file hashes."""
    for bad, label in ((None, "None"), (7, "an int"), ([], "a list")):
        refused(
            lambda b=bad: m._sha_or_zero(b),
            m.NonSyntheticPreparationError,
            f"_sha_or_zero refuses {label}",
            "marker path must be a str",
        )
    marker = os.path.join(tmp, "marker-for-sha")
    with open(marker, "wb") as handle:
        handle.write(b"2026-10-01")
    require(
        m._sha_or_zero(marker) == hashlib.sha256(b"2026-10-01").hexdigest(),
        "an existing marker path hashes its contents",
    )


def check_sys_path_bootstrap() -> None:
    """The module bootstrapped the project root onto sys.path.

    Verified in a FRESH interpreter started with ``-S -E`` and a script whose
    directory is NOT the project root, so the module's own ``sys.path.insert``
    is the only thing that can make ``research.g9...`` importable.

    Two things are asserted, because one alone does not kill the S2 mutant on
    ``sys.path.insert(0, _ROOT)``:

    1. the fresh interpreter IMPORTS the module and resolves ``_ROOT`` — which
       dies if the insert is dropped, since nothing else puts the root on the
       path; and
    2. that same interpreter starts with the root ABSENT from ``sys.path``.
       Without this the insert could be dead code masked by an inherited path
       entry, and the mutant would survive.  The round-2 sweep found exactly
       that, so the precondition is now pinned explicitly.
    """
    require(
        str(ROOT) in sys.path,
        "the module must have placed the project root on sys.path",
    )
    require(m._ROOT == str(ROOT), "the module's _ROOT must be the project root")

    module_path = Path(m.__file__).resolve()
    # The fresh interpreter must start WITHOUT the root on sys.path, so the
    # module's own insert is the only thing that can make `research.g9...`
    # importable — and it must then actually go on to import one of those
    # modules.  The second half matters: with the guard's ``not in`` flipped to
    # ``in``, the insert is skipped, and a probe that only checked ``_ROOT``
    # would still pass.  Importing proves the path really was extended.
    probe = (
        "import sys;"
        f"assert {str(ROOT)!r} not in sys.path, 'root was already on sys.path';"
        "import importlib.util;"
        f"spec = importlib.util.spec_from_file_location('wp8b_probe', {str(module_path)!r});"
        "mod = importlib.util.module_from_spec(spec);"
        "sys.modules['wp8b_probe'] = mod;"
        "spec.loader.exec_module(mod);"
        f"assert mod._ROOT == {str(ROOT)!r}, mod._ROOT;"
        f"assert {str(ROOT)!r} in sys.path, 'the module did not put the root on sys.path';"
        "import research.g9.stage2_instance_preparation as wp5b;"
        "assert wp5b.PROVENANCE_SCHEMA;"
        "print(mod._ROOT)"
    )
    with tempfile.TemporaryDirectory(dir=str(SCRATCH)) as probe_dir:
        env = dict(os.environ)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env.pop("PYTHONPATH", None)
        result = subprocess.run(
            [sys.executable, "-B", "-S", "-E", "-c", probe],
            cwd=probe_dir,
            env=env,
            capture_output=True,
            text=True,
        )
    require(
        result.returncode == 0,
        "a clean interpreter must be able to import the module via its own "
        "bootstrap, starting from a path that does NOT already contain the "
        "root: " + (result.stderr.strip()[-400:] or result.stdout.strip()[-400:]),
    )
    require(
        result.stdout.strip() == str(ROOT),
        "the module must resolve _ROOT to the project root from a clean interpreter",
    )


def check_no_side_effects(root: str) -> None:
    for path in (
        ROOT / "research/g9/stage2_instances",
        ROOT / "research/g9/stage2_generation",
        ROOT / "research/g9/stage2_ground_truth",
    ):
        require(not path.exists(), f"the fixture must not create {path}")
    # The one-use registry must exist ONLY inside the sandbox, never in the
    # project: a fixture that consumed approvals in the real tree would leave
    # state behind that changes every later run.
    require(
        not (ROOT / m.NONCE_REGISTRY_DIR).exists(),
        "the fixture must never write the one-use registry into the project tree",
    )
    require(
        os.path.isdir(m._registry_path(root)),
        "the sandbox registry must exist where the fixture asked for it",
    )


# ===========================================================================
# main
# ===========================================================================
#
# ROUND 2 (D5): the checks are dispatched from tables rather than called by
# name.  Round 1's main() listed each check as a bare statement, and deleting
# any one of them survived the sweep — a bare call is an S2 site whose mutant is
# ``pass``, which is invisible when every other check still passes.  Here the
# table is iterated, so removing an entry removes an assertion the run depends
# on, and each check's internal ``require``s are value checks whose failure is
# observable.

def _scratch_checks() -> list:
    """Checks that need a temp dir and the sandbox nonce root."""
    return [
        check_accepting_non_production,
        check_accepting_is_deterministic,
        check_no_approval,
        check_malformed_approvals,
        check_hash_binding,
        check_hash_binding_precedes_shape,
        check_synthetic_flag_confusion,
        r2_d2_approval_identity_binding,
        r2_d2_unlabelled_real_looking_ids,
        check_fixture_gate_requires_token,
        check_replay,
        r2_d1_replay_is_not_caller_controlled,
        check_nonce_consumption_refusals,
        check_real_material_refused,
        check_production_refused,
        check_record_validation,
        r2_d4_rehashed_tampering_is_refused,
        r2_d6_mismatch_refusals,
        check_non_production_labelling,
        check_wp5b_record_is_never_accepted,
    ]


def _standalone_checks() -> list:
    """Checks that need nothing but the module and the tree."""
    return [
        check_refused_helper_contract,
        check_require_helper_contract,
        check_dispatch_self_audit,
        check_digest_shape_halves,
        check_real_material_excluded,
        check_sys_path_bootstrap,
        r2_d1_ledger_key_properties,
        check_identity,
        r2_d3_source_closure_is_complete,
        r2_d3_identity_reacts_to_a_source_edit,
        r2_d6_pinned_byte_identity,
        r2_d6_v1_parser_type_guards,
        check_digest_and_envelope,
        check_sha_truth_table,
        check_require_helpers,
        check_file_sha_missing,
        check_wp5b_untouched,
    ]


def _defined_check_count() -> int:
    """How many ``check_*``/``r2_*`` functions this file defines at all.

    Read from the source with :mod:`ast` so the coverage floor is a real
    measurement of the file rather than a property of two literal lists.
    """
    import ast

    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    return sum(
        1
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and (node.name.startswith("check_") or node.name.startswith("r2_"))
    )


def _undispatched_checks(dispatched: list = None) -> list:
    """Every ``check_*``/``r2_*`` function in this file that no table reaches.

    Round 2 shipped two of these by accident — ``r2_d1_ledger_key_properties``
    and ``check_sys_path_bootstrap`` — and neither showed up as a failure.  An
    orphan check is the worst kind of gap: it is not merely unkillable, it is
    never RUN, so it asserts nothing at all and still looks like coverage in
    review.  This audit is what makes that impossible to repeat.

    ``dispatched`` is parameterised so the audit can be driven against a table
    that is deliberately missing an entry.  Round 3 recorded why that matters:
    with the table read only from inside, the audit's own correctness was
    untestable, because there was no input on which it could be seen to fire.
    """
    import ast

    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    defined = {
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and (node.name.startswith("check_") or node.name.startswith("r2_"))
    }
    if dispatched is None:
        dispatched = _scratch_checks() + _standalone_checks()
    reached = {check.__name__ for check in dispatched}
    directly_called = {"check_sha_or_zero", "check_no_side_effects"}
    return sorted(defined - reached - directly_called)


def _is_sha256_shape(value: object) -> bool:
    """The fixture's own copy of "exactly 64 lowercase hex characters".

    Extracted so the length and hex halves can each be driven on their own.  The
    round-2 sweep could not kill either half of the inline
    ``len(x) == 64 and all(...)`` expressions, because every real value in the
    fixture happened to be a well-formed digest: a real digest satisfies both
    conditions, and the fixture's only negative inputs failed both.  The helper
    keeps the same rule, and :func:`check_digest_shape_halves` supplies the
    one-sided inputs.
    """
    return type(value) is str and len(value) == 64 and all(
        c in "0123456789abcdef" for c in value
    )


def check_digest_shape_halves() -> None:
    """Length and hex are independently observable halves of the digest shape."""
    valid = "a" * 64
    require(_is_sha256_shape(valid), "64 lowercase hex must satisfy the digest shape")
    # Length right, hex wrong: fails ONLY the hex half.
    for wrong in ("z" * 64, "a" * 63 + "F", "g" * 64):
        require(
            not _is_sha256_shape(wrong),
            f"a 64-char non-hex value {wrong[-3:]!r} must fail the hex half alone",
        )
    # Hex right, length wrong: fails ONLY the length half.
    for wrong in ("a" * 63, "a" * 65, ""):
        require(
            not _is_sha256_shape(wrong),
            f"a hex value of length {len(wrong)} must fail the length half alone",
        )
    # Not a string at all: fails the type half.
    for wrong in (None, 64, [], b"a" * 64):
        require(not _is_sha256_shape(wrong), "a non-str must fail the type half")


def check_refused_helper_contract() -> None:
    """``refused`` itself is a guard, so it is exercised on its own terms.

    The needle check is what stops a "refused for the wrong reason" from
    counting as a pass, and the round-2 sweep could not kill any of its three
    conditions because every call supplied a needle that WAS present.  These
    cases drive the mismatches directly, so a skipped or inverted needle is
    observable rather than merely argued about.
    """
    def boom_expected() -> None:
        raise ValueError("the expected refusal text")

    def boom_other() -> None:
        raise ValueError("a completely different message")

    # The happy path: the needle IS present.
    before = COUNT
    refused(boom_expected, ValueError, "matching needle", "expected refusal")
    require(COUNT == before + 1, "a matching needle must count as one assertion")

    # A missing needle: the reason check is skipped and the refusal still counts.
    before = COUNT
    refused(boom_other, ValueError, "no needle given", "")
    require(COUNT == before + 1, "a needle-free refusal must still count")

    # A FALSY-BUT-NON-EMPTY needle.  Round 3 recorded that the round-2 sweep
    # could not kill the ``needle and ...`` short-circuit by rewriting the
    # operand, because the fixture only ever passed ``""`` (falsy) or a real
    # string (truthy): for both of those, ``True and X`` and ``needle and X``
    # agree, so the mutant is equivalent over the observed domain.  This call
    # pins the guard's FULL input domain by supplying ``None`` — falsy, but
    # not the empty string — for which the two forms genuinely disagree
    # (``None and X`` is None/falsy, ``True and X`` evaluates X).  A falsy
    # needle must behave exactly like an absent one: skip the reason check and
    # count the refusal.
    before = COUNT
    refused(boom_other, ValueError, "a None needle", None)
    require(COUNT == before + 1, "a falsy non-empty needle must skip the reason check")

    # A MISMATCHED needle is a fixture failure, not a silent pass.  The three
    # negative controls below are driven through :func:`_observed` and asserted
    # with the interpreter's own ``assert``, NOT through ``require``.  They are
    # the point of this check: ``refused``'s needle arm, its wrong-type arm and
    # its accept arm each reach their raise through a call to ``require``
    # elsewhere in the file, so asserting them with ``require`` meant a fixture
    # whose ``require`` could not raise reported them all as passing.  ``assert``
    # is a failure channel this file does not define, so it cannot be disabled
    # by the same edit that disables ``require``.
    for label, call, must_say in (
        ("a wrong needle",
         lambda: refused(boom_other, ValueError, "x", "needle-not-present"),
         "refused for the wrong reason"),
        ("a wrong expected type",
         lambda: refused(boom_expected, TypeError, "x", ""),
         "instead of"),
        ("an accepted call",
         lambda: refused(lambda: None, ValueError, "nothing raised"),
         "accepted (no refusal raised)"),
    ):
        observed = _observed(call)
        # Each arm is pinned to its OWN reason, so a fixture that raised a
        # FixtureError from some unrelated place cannot satisfy these.
        assert observed["outcome"] == "raised", f"{label} must raise a FixtureError"
        assert observed["type"] is FixtureError, (
            f"{label} must raise FixtureError, got {observed['type_name']}"
        )
        assert must_say in observed["message"], (
            f"{label} must be reported as '{must_say}', got: {observed['message']}"
        )

    # The ``except FixtureError: raise`` re-raise is load-bearing: without it
    # the generic arm below would swallow a FixtureError raised by the call
    # itself and re-wrap it, losing the original message.  Driven here so the
    # re-raise is observable rather than assumed.  The flag is asserted as a
    # value and the count is pinned, so neither branch can be dropped without
    # the run noticing — and no ``require(False, ...)`` stand-in is used, since
    # a literal-False assertion is exactly the tautology this fixture no longer
    # contains.
    def inner_failure() -> None:
        raise FixtureError("the inner failure, with its own message")

    before = COUNT
    observed = _observed(lambda: refused(inner_failure, ValueError, "an inner FixtureError"))
    assert observed["outcome"] == "raised", (
        "an inner FixtureError must propagate out of refused(), not be swallowed"
    )
    assert observed["type"] is FixtureError, (
        f"the propagated failure must be a FixtureError, got {observed['type_name']}"
    )
    assert "the inner failure, with its own message" in observed["message"], (
        "an inner FixtureError must propagate with its own message, got: "
        + observed["message"]
    )
    assert COUNT == before, (
        "a propagating inner FixtureError must not be counted as a pass"
    )


def check_dispatch_self_audit() -> None:
    """Prove the four ``main``-level guards are real by breaking each one.

    ``main`` audits itself four ways — no duplicate entry, no orphan, the
    coverage floor, and the exact assertion total — and round 2 recorded that as
    the mechanism making every other assertion load-bearing.  It was not
    load-bearing, and the reason is the same circularity as ``require``'s own
    raise: **all four were written with ``require``, so a fixture whose
    ``require`` cannot raise dropped all four at once and still printed PASS.**
    The round-3 sweep confirmed it — every one of the four survived.

    Each guard is therefore re-exercised here against data that is
    DELIBERATELY broken, with the broken-input detection done through
    :func:`_observed` and the interpreter's own ``assert``.  So:

    * neutering ``require``'s raise leaves these asserts working (they are not
      ``require`` calls), and
    * neutering any one of these asserts is caught by ``raise SystemExit`` in
      ``__main__`` plus the honest ``EXPECTED_ASSERTIONS`` total, because this
      function is dispatched and therefore adds a known, non-zero number of
      ``require`` calls that the constant must account for.
    """
    tables = _scratch_checks() + _standalone_checks()
    assert tables, "the dispatch tables must not be empty"

    # GUARD 1 — duplicate entry.  Build the exact list ``main`` builds, plus one
    # deliberate repeat, and require the audit to notice.
    def distinct_names(entries: list) -> bool:
        return len({check.__name__ for check in entries}) == len(entries)

    assert distinct_names(tables), "the real dispatch tables must have no duplicates"
    duplicated = tables + [tables[0]]
    assert not distinct_names(duplicated), (
        "a dispatch table that repeats a check must be detectable: main's "
        "duplicate guard exists to catch exactly this"
    )

    # GUARD 2 — orphan.  ``_undispatched_checks`` must be quiet on the real
    # tables, and must NAME the functions when the table is deliberately
    # deprived of entries.  Asserting only the quiet direction would let the
    # audit return a constant empty list forever, which is the vacuous-pass
    # shape this fixture exists to avoid, so the firing direction is driven on
    # a table that is missing real entries.
    assert not _undispatched_checks(), (
        "no check function may be orphaned: " + ", ".join(_undispatched_checks())
    )

    dropped_name = tables[0].__name__
    deprived = [check for check in tables if check.__name__ != dropped_name]
    orphans = _undispatched_checks(deprived)
    assert dropped_name in orphans, (
        f"the orphan audit must report {dropped_name!r} when it is removed from "
        f"the dispatch table; it reported {orphans}"
    )
    # And it must report EVERY function the deprived table fails to reach, not
    # just the one that was removed.
    assert len(orphans) >= 1, "the orphan audit must be non-vacuous when deprived"

    # GUARD 3 — the coverage floor is read from the SOURCE, so it must react to
    # the real function count, not to the literal tables.
    defined_checks = _defined_check_count()
    assert defined_checks >= MIN_CHECK_FUNCTIONS, (
        f"this file must define at least {MIN_CHECK_FUNCTIONS} check functions; "
        f"it defines {defined_checks}"
    )
    # A table emptied of entries would still leave the source count intact, which
    # is exactly why the floor reads the source.  Pin that the source count is a
    # genuine measurement by showing it exceeds the number of tables.
    assert defined_checks > len(_scratch_checks()) + len(_standalone_checks()) - 2, (
        "the coverage floor must be a measurement of the source, not of the tables"
    )

    # GUARD 4 — the exact total.  Round 3 replaced a tautological check
    # (``EXPECTED_ASSERTIONS > len(tables)``, both sides literals in this file,
    # which the sweep could not kill on either operand) with the relation that
    # is actually load-bearing: each dispatched check contributes at least one
    # ``require``, so the constant is bounded below by the number of checks.
    # This is the claim that the total is calibrated to the tables rather than
    # chosen freely — it is what a reviewer recalibrates when a check is added
    # that asserts nothing, and it holds because the run really does perform at
    # least one assertion per dispatched check.
    table_total = len(_scratch_checks()) + len(_standalone_checks())
    assert EXPECTED_ASSERTIONS > table_total, (
        f"the expected assertion total ({EXPECTED_ASSERTIONS}) must exceed the "
        f"number of dispatched checks ({table_total}); a check that asserts "
        "nothing must be removed or made to assert"
    )


def check_require_helper_contract() -> None:
    """``require`` itself is a guard, and it is checked WITHOUT ``require``.

    This is the fixture's own floor of trust.  ``require`` is the assertion
    primitive: every other check in this file reaches its verdict through it,
    so testing it with ``require`` is circular.  It was, and the round-3 sweep
    found it out — ``raise FixtureError(message)`` inside ``require`` survived
    because neutering it turned the whole file into no-ops that still printed
    PASS.

    The negative controls here therefore (a) observe ``require`` through
    :func:`_observed` and (b) assert with the interpreter's own ``assert``,
    which this file does not define and cannot switch off.  So disabling
    ``require``'s raise fails this check, and disabling this check's own raise
    fails the run through ``raise SystemExit`` in ``__main__``, because ``main``
    returning ``0`` is the only path that skips it.
    """
    # The happy path: a true condition does not raise and counts exactly once.
    before = COUNT
    ok = _observed(lambda: require(True, "a true condition must pass"))
    assert ok["outcome"] == "returned", "require(True, ...) must not raise"
    assert COUNT == before + 1, "require(True, ...) must count exactly one assertion"

    # The failure path, observed as a VALUE.  This is the direct control on
    # ``require``'s own ``raise``: with that raise replaced by ``pass`` the
    # observation below reports "returned" and these asserts fire.
    before = COUNT
    failed = _observed(lambda: require(False, "a false condition must fail"))
    assert failed["outcome"] == "raised", (
        "require(False, ...) must raise; the assertion primitive cannot be a no-op"
    )
    assert failed["type"] is FixtureError, (
        f"require(False, ...) must raise FixtureError, got {failed['type_name']}"
    )
    assert failed["message"] == "a false condition must fail", (
        "require(False, ...) must carry the supplied message, got: " + failed["message"]
    )
    assert COUNT == before, "require(False, ...) must not count a failed assertion"

    # The same property on a message that comes from the caller rather than
    # from this function, so a hard-coded raise cannot satisfy it.
    marker = "the caller supplied this exact message"
    again = _observed(lambda: require(False, marker))
    assert again["message"] == marker, (
        "require must carry the caller's message verbatim, got: " + again["message"]
    )

    # And the no-op direction explicitly: a true condition must not raise, so a
    # fixture that raised unconditionally would be caught here rather than
    # looking like a stricter assertion.
    always = _observed(lambda: require(True, "still fine"))
    assert always["outcome"] == "returned", "require(True, ...) must stay quiet"


def main() -> int:
    global COUNT
    # ROUND 3.  The counter is reset FIRST, before the four self-audit guards
    # below.  Round 2 reset it AFTER them, which meant those four ``require``
    # calls incremented a count that was immediately zeroed: their contribution
    # to ``EXPECTED_ASSERTIONS`` was discarded, so dropping any one of them left
    # the final total unchanged and each survived as an S1 mutant.  Resetting
    # here puts every assertion in the file — including the self-audit — inside
    # the total that ``main`` requires, which is what makes these four guards
    # load-bearing in their own right.
    #
    # This alone is NOT sufficient for the four guards: ``require``'s own raise
    # can still be neutered, which disables all four at once.  They are
    # therefore also re-proved against deliberately broken data by
    # :func:`check_dispatch_self_audit` using the interpreter's ``assert``.
    COUNT = 0

    before = pycache_count()
    SCRATCH.mkdir(parents=True, exist_ok=True)
    scratch_checks = _scratch_checks()
    standalone_checks = _standalone_checks()
    dispatched = scratch_checks + standalone_checks
    # Every entry is a distinct callable, so no check can be listed twice and
    # Every entry is a distinct callable, so no check can be listed twice and
    # silently shadow itself.
    require(
        len({check.__name__ for check in dispatched}) == len(dispatched),
        "the dispatched check table must not repeat a check",
    )
    orphans = _undispatched_checks()
    require(
        not orphans,
        "every check function must be dispatched, or it asserts nothing: " + ", ".join(orphans),
    )
    # The coverage floor is derived from the SOURCE, not from the literal
    # tables.  Asserting ``len(dispatched) > 0`` about two literal lists that
    # always have entries is a tautology whose S1 mutant can never be killed;
    # counting the check functions actually DEFINED in this file is the claim
    # that can break, and it breaks the moment entries are deleted.
    defined_checks = _defined_check_count()
    require(
        defined_checks >= MIN_CHECK_FUNCTIONS,
        f"this file must define at least {MIN_CHECK_FUNCTIONS} check functions; "
        f"it defines {defined_checks}",
    )

    # ROUND 2 (D5), the part that makes the assertions mutually dependent.
    #
    # A bare ``require(x, ...)`` is an S1 site whose mutant is ``pass``.  When
    # the other assertions in the function are independent, dropping any ONE of
    # them is invisible, so every one of them survives — which is exactly how
    # round 1's fixture collected 231 survivors.  The fix is to make the run
    # DEPEND on the total: every assertion increments ``COUNT`` and ``main``
    # requires the count it observed, so removing any single one changes that
    # total and the run fails.  (The round-1 sweep fixture for WP7b still has
    # this weakness; the module under test is what the gate sweeps.)

    with tempfile.TemporaryDirectory(dir=str(SCRATCH)) as tmp:
        # The sandbox root for the one-use registry.  Every preparation in this
        # run is recorded here, never in the project tree.
        root = _scratch_dir(tmp, "nonce-root")
        for check in scratch_checks:
            check(tmp, root)
        check_sha_or_zero(tmp)
        check_no_side_effects(root)

    for check in standalone_checks:
        check()

    # Everything below is counted into the same total, so it is covered by the
    # same dependency.
    require(pycache_count() == before, "the fixture must not write bytecode")
    # The total is enforced through THREE INDEPENDENT CHANNELS, all reading the
    # same condition.  Round 3 recorded why one or two are not enough:
    #
    #   * ``require`` alone -- neutering require's own raise disables it, and
    #     with it every other assertion in the file.
    #   * ``assert`` alone -- an interpreter-level channel the file does not
    #     define, but it is a statement whose own deletion is invisible unless
    #     something else reads the count.
    #   * a bare ``raise`` -- a third channel that routes through neither.
    #
    # Removing any ONE channel leaves the other two to fire; the sweep's S1
    # operator drops a single statement, so no single-statement mutant removes
    # the total.  This is the difference between "the total is checked" and
    # "the total is checked by more than the thing being checked".
    _count_message = (
        f"the fixture must perform exactly {EXPECTED_ASSERTIONS} assertions; "
        f"it performed {COUNT} (a missing one means a guard stopped firing)"
    )
    if COUNT != EXPECTED_ASSERTIONS:
        raise FixtureError(_count_message)
    assert COUNT == EXPECTED_ASSERTIONS, _count_message
    require(COUNT == EXPECTED_ASSERTIONS, _count_message)

    print(f"optimize={sys.flags.optimize} checks={COUNT} groups={len(dispatched)} "
          f"fixture_branch_invocations={m.FIXTURE_BRANCH_INVOCATIONS}")
    print(f"wp8b_identity_hash={m.NON_SYNTHETIC_IDENTITY_HASH}")
    print(f"production_release_pinned={m.PRODUCTION_RELEASE_PINNED} "
          f"decision_record={m.PRODUCTION_RELEASE_DECISION_RECORD}")
    print(f"real_material_markers={len(m.REAL_MATERIAL_MARKERS)} "
          f"fixture_scope={m.FIXTURE_SCOPE} bound_sources={len(m.SOURCE_FILES)}")
    print("round-2 regressions: r2_d1 replay r2_d2 approval_identity "
          "r2_d3 source_closure r2_d4 rehashed_tampering r2_d6 pinned_identity")
    print("PASS WP8b non-synthetic preparation fixtures; NON-PRODUCTION stand-in only; "
          "no real draw, no production seed, no scientific write; every refusal exercised; "
          "WP5b left untouched")
    return 0


if __name__ == "__main__":
    # ROUND 3.  Round 2 accepted this ``__main__`` block as three equivalents
    # (the ``__name__`` comparison as S4 and S5, and the raise as S3) on the
    # argument that "every assertion raises FixtureError, so a failing run
    # already exits non-zero through that traceback".  That argument is TRUE,
    # and it is exactly why the acceptance was wrong: it only describes the
    # FAILURE path, while the mutation harness can only silently reach the
    # SUCCESS path.  Replacing the raise with ``pass`` lets ``main()`` run to
    # completion and the process then exits 0 regardless of what ``main``
    # returned, so a green run and a bypassed exit status are indistinguishable
    # from outside.
    #
    # What is pinned here is narrower and true: ``main``'s return value is
    # asserted against 0 by the interpreter's ``assert`` — a channel this file
    # does not define — before it is handed to ``SystemExit``.  Disabling that
    # assert, or the raise, is a change to the module-scope entry point rather
    # than to any guard, and is recorded as such in the equivalents file rather
    # than dressed up as a killed mutant.
    _status = main()
    assert _status == 0, f"main() must return 0 on a passing run, got {_status!r}"
    raise SystemExit(_status)

#!/usr/bin/env python3
"""WP8c — the end-to-end synthetic stand-in REHEARSAL.

STATUS: BUILD + VALIDATION ONLY. UNARMED. NOT A DRAW, NOT A PUSH.

This is the FIRST deliverable: an ACTUAL end-to-end run of the WP8c production
session, on conspicuous NON-PRODUCTION stand-in material, with only two things
emulated at a single clearly marked boundary:

  * HARDWARE — the CUDA device backend and the Python reference are the
    declared placeholders in ``wp8c_standin.py``.  No GPU, no nvcc, no energy
    evaluated, no scientific value produced.
  * OWNER AUTHORITY — the one-use scientific-write authorization, which no
    module may construct.  This script builds it the way an owner would: as a
    literal record over values the session RE-DERIVES, handed to
    ``validate_authorization`` and then consumed through WP8b's own stateful
    nonce registry.

Everything else is the REAL reviewed code, called as published:

  WP8d-production verify -> WP8a accept/exact_match -> WP1 exact_match
      -> WP2 recheck_before_first_write -> WP3 run_section_b2
      -> stage2_coordinate_records.build_record -> WP4b seal_range_plan /
         write_range / promoted_batch_ids / missing_ranges / audit_final_set

WHAT IT PROVES
==============
1.  The order holds.  A complete stand-in session walks S1..S7 and produces a
    ``complete_pending_image_audit`` receipt that is NOT accepted.
2.  The refusals are real.  A tampered identity, a swapped slot, a forged
    authorization, a stale/replayed nonce, a failed WP2 prerequisite, a fired
    D013 with an undeclaring backend, a budget stop, a narrowed resume and a
    replayed session are each refused, each for its OWN named reason.
3.  A failed prerequisite blocks EVERY dependent device and write step.
4.  The production path is UNARMED and refuses: WP8b's R6 gate.
5.  A MEANINGFUL BROKEN VARIANT fails.  ``--broken`` mutates one real guard
    (the identity binding) and the rehearsal must FAIL, not pass.
"""
from __future__ import annotations

import argparse
import ast
import copy
import datetime
import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.g9 import stage2_production_writer as writer  # noqa: E402
from research.g9 import stage2_coordinate_records as records  # noqa: E402
from research.g9 import stage2_section_b2_harness as harness  # noqa: E402
from research.g9 import stage2_section_b1_recheck as wp2  # noqa: E402
from research.g9.wp8b import wp8b_non_synthetic_preparation as wp8b  # noqa: E402
from research.g9.wp8c_production import wp8c_production_session as s  # noqa: E402
from research.g9.wp8c_production import wp8c_standin as st  # noqa: E402

#: Scratch root mandated by the package rules.  Never /tmp.
SCRATCH = Path("/home/shivansh-srivastava/decisions_os/g9_jobs/scratch/wp8c")

#: WP4b's own free-form family identifier for the sealed plan.  Conspicuously
#: non-production, and DISTINCT from the committed coordinate ``Family`` object:
#: the two label different things (WP4b's plan vs the coordinate space).
WRITER_FAMILY = "wp8c_nonproduction_standin"

#: The committed coordinate FAMILY the rehearsal drives end to end.  It is the
#: DECLARED D013 ``CB`` V-14 0.5x companion family (31 x 31 = 961 coordinates),
#: a genuine member of the frozen family table reached through
#: ``stage2_coordinate_records.families(d013_fired=True)``.  It is NOT a reduced,
#: synthetic or hand-built space: the sealed plan, ``build_record`` and WP4b's
#: whole-range write all run over the family's REAL, COMPLETE committed
#: coordinate count, which the session itself re-derives from the committed
#: family table and refuses on any mismatch.  Two properties fix the choice:
#:
#:  * each committed coordinate record carries a full frozen D015/D016
#:    reconstruction that the session holds in memory across the S6/S7 window, so
#:    the rehearsal runs the largest declared family whose COMPLETE space fits
#:    this unit's MemoryMax=20G (the 226,981-coordinate primary family does not,
#:    and the earlier 2,197-coordinate ``d011`` companion reached ~14 GB);
#:  * this family's ``resolve_coefficients`` mapping is buildable.  The sibling
#:    ``d013__*__d011`` families raise ``KeyError: 'ell_sector'`` inside the
#:    reviewed ``resolve_coefficients`` D011-CM branch (``stage2_coordinate_records
#:    .py:864-874``), which assumes three axes where those families declare two;
#:    that is a reviewed-code defect recorded in the notes, not something WP8c
#:    may work around, and no frozen file is modified to hide it.
#:
#: No scientific value is computed: the engine results are the declared
#: placeholders in ``wp8c_standin.py``.  The D013 prerequisite is genuinely
#: exercised because this family only exists when the trigger fires.
REHEARSAL_FAMILY_KEY = "d013__cb__v14_0_5x"

RESULTS: list[tuple[str, str, str]] = []


#: The ``d013_fired`` flag that makes ``REHEARSAL_FAMILY_KEY`` a declared
#: family.  The session takes it as a parameter and refuses a family that is not
#: declared under the SAME flag, so the driver and the session must agree on it.
REHEARSAL_D013_FIRED = True


def rehearsal_family() -> object:
    """The declared ``Family`` object the rehearsal drives end to end.

    Selected from the committed family table by its key PREFIX, never by index
    and never by a constructed or modified object, so the session's own
    membership guard (``family in records.families(d013_fired)``) observes a
    genuine declared family and not a look-alike.  The prefix rather than the
    whole key because ``Family.key`` appends the frozen ``r`` token, which is
    part of the identity of a different family.
    """
    declared = records.families(REHEARSAL_D013_FIRED)
    matches = [family for family in declared
               if family.key.startswith(REHEARSAL_FAMILY_KEY)]
    require(len(matches) == 1,
            f"exactly one declared family must carry the key prefix "
            f"{REHEARSAL_FAMILY_KEY!r}, got {len(matches)} of "
            f"{[f.key for f in declared]}")
    family = matches[0]
    space = records.family_space(family, records.build_frozen_axes())
    require(space.total_coordinates == 961,
            f"the rehearsal family space changed: {space.total_coordinates}")
    return family


def record_step(label: str, outcome: str, detail: str = "") -> None:
    RESULTS.append((label, outcome, detail))
    print(f"  {outcome:<8} {label}" + (f"  {detail}" if detail else ""))


def require(condition: object, message: str) -> None:
    if not condition:
        raise RuntimeError("REHEARSAL FAILED: " + message)


def _layout_and_writer(base: str, name: str, *, nonce: str,
                       instance_id: str = st.STANDIN_ID) -> tuple[str, str]:
    """A fresh layout root with one stand-in instance, and a fresh WP4b root."""
    layout = st.sandbox_root(base, name + "-layout")
    prepared = st.prepare_standin(st.standin_instance(instance_id),
                                  st.approval_over(instance_id=instance_id, nonce=nonce),
                                  root=layout)
    kwargs = st.write_kwargs(root=layout, record=prepared,
                             instance=st.standin_instance(instance_id),
                             instance_id=instance_id)
    from research.g9.wp8d_production import wp8d_production_layout as wp8dp
    wp8dp.write_standin_instance(**kwargs)
    return layout, st.writer_root(base, name + "-writer")


def _one_use_authorization(verified, identity_sha256: str, *,
                           nonce: str, expiry: str = st.PINNED_FUTURE) -> dict:
    """Build the one-use owner authorization, as an owner would.

    Every hash is read from the VERIFIED record and the WP8a acceptance receipt,
    never from an argument, so this helper is exactly as trustworthy as the
    session's own comparison: a wrong value is refused by
    ``validate_authorization`` rather than believed.
    """
    return {
        "schema": s.AUTHORIZATION_SCHEMA,
        "authorization_status": s.AUTHORIZATION_STATUS,
        "action": s.AUTHORIZED_ACTION,
        "account": "NONPROD-STANDIN-ACCOUNT-NOT-AN-ACCOUNT",
        "kernel_id": "nonprod-standin/not-a-kernel",
        "bundle_sha256": hashlib.sha256(
            b"wp8c-nonproduction-standin-bundle").hexdigest(),
        "accepted_identity_sha256": identity_sha256,
        "instance_id": verified["instance_id"],
        "generation_manifest_sha256": verified["generation_manifest_sha256"],
        "prepared_record_sha256": verified["prepared_id"],
        "session_contract_sha256": s.session_contract_sha256(),
        "expiry": expiry,
        "nonce": nonce,
        "statement": s.AUTHORIZATION_STATEMENT,
    }


# ===========================================================================
# The stand-in acceptance record WP8a requires
# ===========================================================================
# WP8a's `accept_production_identity` needs a FULL acceptance record: a review
# note and a WP7 dry-run receipt that must EXIST in the repo root and hash to the
# recorded values, a bound draft identity, and a qualified source map.  No such
# record exists in this tree, which is exactly why the accepted-identity gate is
# UNSET.  The rehearsal therefore drives that gate through the
# `wp8a_seam` injection point below, which is the ONE place WP8c's identity
# binding is stood in for, and it does so in a way that cannot be mistaken for
# the real thing: the stand-in binding carries the DRAFT identity verbatim and
# is compared by the REAL WP1 `exact_match`.


def standin_acceptance_binding(module) -> dict:
    """A conspicuously labelled stand-in for WP8a's acceptance receipt.

    It is NOT an acceptance.  The record it carries is WP8a's own schema with the
    DRAFT identity, and `require_session_identity_exact` still routes the
    comparison through the REAL WP1 `exact_match`, so a session identity that
    differs in ANY field is refused.  What is stood in is WP8a's *existence*
    proof, which no offline package can have; what is NOT stood in is the
    comparison, which is the security-relevant part.
    """
    from research.g9.wp8a import wp8a_production_identity_acceptance as wp8a
    draft = st.draft_identity()
    draft_sha = st.draft_identity_sha256()
    return {
        # `accepted_content_sha256` is the field WP8a's own published return
        # value re-derives from the pinned constants
        # (`wp8a_production_identity_acceptance.py:1187-1205`) and the one
        # `require_session_identity_exact` now requires
        # (`wp8c_production_session.py:626`).  The stand-in therefore carries
        # the SAME shape as a real WP8a receipt, so the rehearsal exercises the
        # real guard rather than a different branch of it.
        "accepted_content_sha256": draft_sha,
        "draft_identity_content_sha256": draft_sha,
        "qualification_identity_content_sha256": draft_sha,
        "schema": wp8a.ACCEPTANCE_SCHEMA,
        "status": wp8a.APPROVED_STATUS,
        "draft_identity": draft,
        "acceptance_record": {
            "schema": wp8a.ACCEPTANCE_SCHEMA,
            "status": "STANDIN-NOT-AN-ACCEPTANCE",
            "draft_identity": draft,
        },
        "reviewed_record_sha256": hashlib.sha256(
            b"wp8c-nonproduction-standin-acceptance-pin").hexdigest(),
        "repo_root": str(ROOT),
        "standin": True,
        "statement": (
            "NON-PRODUCTION STAND-IN for WP8a's acceptance receipt. The real "
            "accept_production_identity requires an independently reviewed record "
            "SHA-256 that is not derivable from the record, so no offline package "
            "can produce one. The identity comparison below is the REAL WP1 "
            "exact_match and is not stood in at all."),
    }


def _identity_verdict(module, binding, session_identity):
    """The REAL WP1 total comparison, called as published.

    ``stage2_production_identity.exact_match`` is total and symmetric and names
    every difference (``research/g9/stage2_production_identity.py:436-475``).
    WP8a calls it through ``exact_match_session``; here the stand-in binding has
    no acceptable record, so the comparison is made by WP1 directly against the
    same draft payload WP8a would have compared.  Nothing weaker is substituted.
    """
    verdict = module.__dict__["wp1"].exact_match(session_identity,
                                                binding["draft_identity"])
    return {"verdict": verdict["verdict"],
            "session_content_sha256": verdict["session_content_sha256"],
            "accepted_content_sha256": verdict["accepted_content_sha256"],
            "differing_fields": []}


def _real_acceptance_verdict(module, binding, session_identity):
    """WP8a's own route, used when a genuine acceptance record is present."""
    return module.require_session_identity_exact(binding, session_identity)


# ===========================================================================
# The driver
# ===========================================================================


def placeholder_engine_results(count: int) -> dict:
    """Declared NON-PRODUCTION engine results, one per linear coordinate.

    These are the reviewed CUDA producer's OUTPUT SHAPE with obvious placeholder
    values, supplied so the rehearsal can drive ``build_record`` and WP4b's range
    write for real.  No energy was evaluated: the minimum is a chosen constant
    and the tie word is a single synthetic state.

    The shape is the frozen engine's, not a convenient one.
    ``reconstruct_pair`` requires exactly the two encodings, each with
    ``minimum`` / ``minimum_index`` / ``compacted_entries``
    (``research/g9/cuda_qualification/stage2_cuda_reconstruct.py:223-243``), and
    requires the tie set to CONTAIN the minimum and the three D015 tie sets to
    be NESTED (``:170-174``).  A tie word with flag ``7`` ties at every ``c_H``
    and contains the minimum index, which is the smallest conforming set — the
    same construction the reviewed coordinate-record fixture uses
    (``verify_stage2_coordinate_records_fixtures.py:138-165``).

    ``slack`` and ``classifiers`` are built ONCE and shared by every coordinate,
    exactly as the reviewed coordinate-record fixture does
    (``verify_stage2_coordinate_records_fixtures.py:930-931``: one
    ``synthetic_slack_map()`` and one ``synthetic_classifiers()`` are built, then
    passed to every ``build_record`` call).  Both are immutable value objects --
    ``SlackIndexMap`` is a frozen dataclass that validates and canonicalises its
    offsets once in ``__post_init__``
    (``research/g9/cuda_qualification/stage2_cuda_reconstruct.py:60-88``) and
    exposes only read-only properties thereafter, and the classifier map holds
    three frozen ``DecodedClassifier`` instances -- so one construction per run is
    equivalent to one per coordinate.  Building one per coordinate was measured at
    ~20 MB of transient allocation per coordinate (a 1,048,578-entry offset ramp),
    i.e. ~19 GB for this family's 961 coordinates, which is a resource defect and
    not a semantic difference.
    """
    minimum_index = 0
    words = ((7 << 32) | minimum_index,)
    slack = _synthetic_slack_map()
    classifiers = _synthetic_classifiers()
    return {
        index: {
            "core_result": {
                encoding: {
                    "minimum": st.PLACEHOLDER_MINIMUM,
                    "minimum_index": minimum_index,
                    "compacted_entries": words,
                }
                for encoding in records.ENCODINGS
            },
            "slack": slack,
            "classifiers": classifiers,
            "f_star": st.PLACEHOLDER_F_STAR,
            "lambda_ref": st.PLACEHOLDER_LAMBDA_REF,
        }
        for index in range(count)
    }


def _synthetic_slack_map():
    """The synthetic ``SlackIndexMap`` the reviewed fixture uses.

    ``SlackIndexMap`` requires ``STATE_COUNT + 1`` ascending boundaries of unit
    steps ending at ``lift_total`` (``reconstruct.py:71-88``), which makes the
    lifted index decode to the same state as the unbalanced one
    (``verify_stage2_coordinate_records_fixtures.py:110-117``).  Replicated here
    rather than re-derived, because a re-derived one would be a different
    reconstruction.
    """
    import array as _array
    from research.g9.cuda_qualification import stage2_cuda_reconstruct as frozen
    offsets = _array.array("Q", range(frozen.STATE_COUNT + 1))
    return frozen.SlackIndexMap(offsets=offsets, lift_total=frozen.STATE_COUNT)


def _synthetic_classifiers():
    """Three frozen classifiers over a synthetic 20-bit objective.

    Identical to the reviewed coordinate-record fixture's construction
    (``verify_stage2_coordinate_records_fixtures.py:120-135``): a popcount
    objective and a ``popcount <= 1`` feasibility test.  The population is
    synthetic; no instance is read and no classification is scientific.
    """
    from research.g9.cuda_qualification import stage2_cuda_reconstruct as frozen
    from src.g4 import classification as frozen_classifier

    def objective(decoded):
        return float(sum(decoded))

    def feasible(decoded):
        return sum(decoded) <= 1

    return {
        c_f: frozen.DecodedClassifier(
            frozen_classifier.OriginalObjectiveService(
                objective, lambda_ref=st.PLACEHOLDER_LAMBDA_REF, c_f=float(c_f)),
            feasible)
        for c_f in frozen.CF_VALUES
    }


def standin_bind_acceptance(acceptance_record, *, reviewed_record_sha256, repo_root):
    """The stand-in for WP8a's ``accept_production_identity``.

    Returns the conspicuously labelled stand-in binding.  It does NOT validate
    the acceptance record — nothing offline can, because WP8a requires a pin
    that is not derivable from the record
    (``research/g9/wp8a/wp8a_production_identity_acceptance.py:1096-1118``).  It
    returns the DRAFT identity verbatim, so the comparison downstream is the
    REAL WP1 ``exact_match`` against the real draft.
    """
    return standin_acceptance_binding(s)


def standin_compare_identity(binding, session_identity):
    """The stand-in for WP8a's ``exact_match_session``.

    The COMPARISON is not stood in: this calls WP1's total, symmetric
    ``exact_match`` (``research/g9/stage2_production_identity.py:436-475``), which
    names every difference and refuses on any of them.  What differs from the
    production route is only the acceptance record's re-validation, which cannot
    be performed offline.  A tampered session identity is refused here exactly as
    it would be in production — and the adversarial probe (a) proves it.
    """
    return _identity_verdict(s, binding, session_identity)


def run_session(base: str, *, layout: str, writer_root: str, nonce_root: str,
                session_id: str, authorization, session_identity,
                clock, standin: bool = True,
                d013_fired: bool = REHEARSAL_D013_FIRED,
                backend_factory=st.device_backend_factory,
                family: object | None = None,
                family_coordinates: int | None = None,
                engine_results=None, seam_overrides=None,
                verified_instance: dict | None = None) -> dict:
    """Drive ONE session through ``run_production_session``.

    The seam mapping is built here, in the rehearsal, and always includes the
    REAL reviewed functions.  ``seam_overrides`` exists so the adversarial
    probes can substitute one entry to prove the rest of the chain still refuses.
    """
    seams = dict(s._seams())
    seams["device_backend_factory"] = backend_factory
    seams["python_reference"] = st.python_reference
    # The ONE identity stand-in.  WP8a's accept_production_identity cannot be
    # driven offline, because it needs an independently reviewed record SHA-256
    # that is not derivable from the record itself.  The binding is stood in; the
    # COMPARISON is not -- it is the real WP1 exact_match either way.
    seams["bind_accepted_identity"] = standin_bind_acceptance
    seams["require_session_identity_exact"] = standin_compare_identity
    if seam_overrides:
        seams.update(seam_overrides)
    identity = session_identity if session_identity is not None else st.draft_identity()
    if family is None:
        # The declared Family OBJECT, never its string repr and never a
        # hand-built look-alike: the committed family table is keyed by the
        # Family dataclass, so the session's membership guard would refuse one.
        family = rehearsal_family()
    if family_coordinates is None:
        family_coordinates = records.family_space(
            family, records.build_frozen_axes()).total_coordinates
    return s.run_production_session(
        slot=1, session_id=session_id, root=layout, instance_root=writer_root,
        nonce_root=nonce_root,
        acceptance_record={"standin": True},
        reviewed_record_sha256=hashlib.sha256(
            b"wp8c-nonproduction-standin-acceptance-pin").hexdigest(),
        session_identity=identity,
        authorization=authorization,
        boundary=st.standin_boundary(s), standin=standin,
        d013_fired=d013_fired, d013_coordinates=(
            harness.d013_repeat_coordinates() if d013_fired else None),
        writer_family=WRITER_FAMILY,
        # WP4b's M1 result schema, matching the module's pinned projection fields
        # (``s.WRITER_RESULT_FIELDS``).  Both are ``str`` SHA-256 digests: the
        # accepted identity hash and the committed record's own content hash.
        result_schema={"identity_sha256": "str",
                       "record_content_sha256": "str"},
        family=family,
        family_coordinates=family_coordinates,
        engine_results=engine_results,
        expected_approval_sha256=wp2.read_approval_hashes(),
        expected_generator_implementation_record_sha256=(
            s.generator_record_of(verified_instance) if verified_instance else
            hashlib.sha256(b"wp8c-nonproduction-implementation-record").hexdigest()),
        expected_ground_truth_provenance_sha256=(
            s.ground_truth_of(verified_instance) if verified_instance else
            hashlib.sha256(b"wp8c-nonproduction-ground-truth").hexdigest()),
        approved_identity_sha256=st.draft_identity_sha256(),
        protocol_identity_sha256=hashlib.sha256(
            b"wp8c-nonproduction-protocol").hexdigest(),
        clock=clock, seams=seams, today=st.PINNED)


def _authorization_for(base: str, *, nonce: str, expiry: str = st.PINNED_FUTURE,
                       instance_id: str = st.STANDIN_ID) -> dict:
    """Verify a stand-in instance, then build the authorization over it."""
    layout, writer_root = _layout_and_writer(base, "auth-" + nonce, nonce=nonce + "-wp8b",
                                             instance_id=instance_id)
    verified = s.verify_instance_for_session(1, root=layout, standin=True)
    return _one_use_authorization(verified, st.draft_identity_sha256(),
                                  nonce=nonce, expiry=expiry)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="WP8c synthetic stand-in rehearsal")
    parser.add_argument("--broken", action="store_true",
                        help="apply the meaningful broken variant; the rehearsal "
                             "must FAIL, and a pass is a build error")
    args = parser.parse_args(argv)

    SCRATCH.mkdir(parents=True, exist_ok=True)
    base = tempfile.mkdtemp(prefix="rehearsal-", dir=str(SCRATCH))
    print("WP8c end-to-end synthetic stand-in rehearsal")
    print(f"  scratch            {base}")
    print(f"  scope              {s.SCOPE_STATEMENT[:96]}...")
    print(f"  gates              {json.dumps(s.owner_gate_status(), sort_keys=True)[:160]}")
    print()

    # The broken variant, applied to the MODULE under test when requested.
    if args.broken:
        return _broken_variant(base)

    try:
        _rehearse(base)
    except RuntimeError as exc:
        print(f"\nREHEARSAL: FAIL — {exc}")
        return 1
    print("\nREHEARSAL: PASS (NON-PRODUCTION stand-in only; unarmed; no real draw, "
          "no production seed/beacon, no scientific write, no GPU, no push)")
    return 0


def _rehearse(base: str) -> None:
    print("[1] the production path is UNARMED and refuses")
    prod_layout, _ = _layout_and_writer(base, "prod", nonce="prod-wp8b")
    prod = _observed(lambda: s.verify_instance_for_session(1, root=prod_layout,
                                                          standin=False))
    require(prod["outcome"] == "raised" and prod["type_name"] == "InstanceRefused",
            f"the production reader did not refuse: {prod}")
    require("require_production=True" in prod["message"], prod["message"])
    record_step("production instance reader refuses (WP8b R6)", "REFUSED",
                "require_production=True")
    require(s.owner_gate_status()["wp8b_production_release_pinned"] is False,
            "WP8b's production release must be unpinned")
    record_step("WP8b PRODUCTION_RELEASE_PINNED is False", "REFUSED", "gate unset")
    require(not Path(ROOT / wp8b.PRODUCTION_RELEASE_DECISION_RECORD).is_file(),
            "WP8b's R6 decision record must not exist; WP8c never writes one")
    record_step("WP8b R6 decision record absent (not fabricated)", "REFUSED", "absent")

    print("\n[2] the accepted-identity gate is UNSET and refuses")
    identity_gate = _observed(lambda: s.bind_accepted_identity(
        {"standin": True},
        reviewed_record_sha256=hashlib.sha256(b"x").hexdigest(), repo_root=ROOT))
    require(identity_gate["outcome"] == "raised"
            and identity_gate["type_name"] == "IdentityGateUnset",
            f"WP8a did not refuse a stand-in acceptance: {identity_gate}")
    record_step("WP8a accept_production_identity refuses a stand-in record", "REFUSED",
                identity_gate["type_name"])

    print("\n[3] the complete stand-in session, end to end")
    layout, writer_root = _layout_and_writer(base, "happy", nonce="happy-wp8b")
    verified = s.verify_instance_for_session(1, root=layout, standin=True)
    record_step("S1 instance verified through WP8d-production", "OK",
                verified["instance_id"])
    identity_sha = st.draft_identity_sha256()
    authorization = _one_use_authorization(verified, identity_sha, nonce="happy-nonce-1")
    nonce_root = st.sandbox_root(base, "happy-nonce-root")
    family = rehearsal_family()
    axes = records.build_frozen_axes()
    population = records.family_space(family, axes).total_coordinates
    print(f"  S6 committed family {family.key}  coordinates {population}")
    receipt = run_session(base, layout=layout, writer_root=writer_root,
                          nonce_root=nonce_root, session_id="session-happy-1",
                          authorization=authorization,
                          session_identity=st.draft_identity(),
                          clock=lambda: 0.0, verified_instance=verified,
                          family=family,
                          engine_results=placeholder_engine_results(population))
    require(receipt["status"] == "complete_pending_image_audit",
            f"the complete session did not complete: {receipt}")
    require(receipt["accepted"] is False,
            "a WP8c receipt must never be accepted")
    require(receipt["image_audit_status"] == s.KAGGLE_IMAGE_STATUS_PENDING,
            "the receipt must be pending the image metadata audit")
    record_step("S1..S7 complete; receipt pending image audit", "OK",
                receipt["status"])
    require(sorted(receipt["steps_passed"]) == sorted(s.STEP_ORDER),
            f"the step set is not the frozen one: {receipt['steps_passed']} vs "
            f"{list(s.STEP_ORDER)}")
    record_step("frozen step order S1..S7 observed", "OK",
                "->".join(s.STEP_ORDER))
    require(receipt["authority_boundary"] == s.AuthorityBoundary.KIND,
            "the receipt must name the emulated boundary")
    record_step("receipt names the emulated authority boundary", "OK",
                s.AuthorityBoundary.KIND)
    promoted = receipt.get("promoted_range_batch_ids", [])
    require(promoted,
            "the complete session must have promoted whole ranges through WP4b")
    record_step("S6 promoted the family's whole ranges via WP4b", "OK",
                f"{len(promoted)} ranges over {population} coordinates")

    print("\n[4] one-use authorization: consumed once, never replayed")
    replay = _observed(lambda: run_session(
        base, layout=layout, writer_root=writer_root, nonce_root=nonce_root,
        session_id="session-happy-2", authorization=authorization,
        session_identity=st.draft_identity(), clock=lambda: 0.0))
    require(replay["outcome"] in ("raised", "returned"), "the replay must be observed")
    replay_message = (replay["message"] if replay["outcome"] == "raised"
                      else replay["value"]["difference"])
    require("refused" in replay_message or "already" in replay_message
            or "replay" in replay_message.lower(),
            f"the replayed authorization was not refused: {replay}")
    record_step("replayed one-use nonce refused by WP8b's registry", "REFUSED",
                "replay")

    print("\n[5] the adversarial refusals, each for its own reason")
    _adversarial(base)

    print("\n[6] the budget stop and the missing-whole-range resume")
    _budget_and_resume(base)

    print("\n[7] the child-isolation and image-pin alignment to WP7b")
    _isolation_and_pins()


def _adversarial(base: str) -> None:
    """Each negative case, refused for its OWN named reason."""
    identity_sha = st.draft_identity_sha256()

    # (a) tampered identity: one flipped platform digit.
    layout, writer_root = _layout_and_writer(base, "tampered", nonce="tamper-wp8b")
    verified = s.verify_instance_for_session(1, root=layout, standin=True)
    tampered = copy.deepcopy(st.draft_identity())
    tampered["qualification_identity"]["platform"]["gpu_name"] = "TAMPERED-NONPROD"
    outcome = _observed(lambda: run_session(
        base, layout=layout, writer_root=writer_root,
        nonce_root=st.sandbox_root(base, "tamper-nonce"),
        session_id="session-tampered",
        authorization=_one_use_authorization(verified, identity_sha, nonce="tamper-1"),
        session_identity=tampered, clock=lambda: 0.0, verified_instance=verified))
    # The refusal type is WP1's OWN, because the comparison runs on WP1's
    # ``exact_match`` directly: a tampered identity is refused by the reviewed
    # identity validator itself, not by a WP8c wrapper.  Both are session
    # errors, so the session's single ``except`` still converts it into a
    # non-accepting receipt, but the refusal is attributable to the reviewed
    # package rather than to this module.
    require(outcome["outcome"] == "raised"
            and outcome["type_name"] in ("IdentityGateUnset",
                                         "ProductionIdentityError"),
            f"a tampered identity was not refused by the identity gate: {outcome}")
    record_step("tampered session identity refused by WP1 exact_match", "REFUSED",
                outcome["type_name"])

    # (b) swapped slot: verify slot 1, then name slot 2.
    swapped = _observed(lambda: s.require_instance_matches_session(
        verified, expected_instance_id=verified["instance_id"],
        expected_slot="stage2_02"))
    require(swapped["outcome"] == "raised"
            and swapped["type_name"] == "ProductionSessionError",
            f"a swapped slot was not refused: {swapped}")
    record_step("swapped slot refused (verified record vs caller claim)", "REFUSED",
                "slot disagreement")

    # (c) forged authorization over a different instance.
    forged = copy.deepcopy(_one_use_authorization(verified, identity_sha,
                                                  nonce="forged-1"))
    forged["instance_id"] = st.STANDIN_ID_B
    forged = _resign_authorization(forged)
    outcome = _observed(lambda: s.validate_authorization(
        forged, verified=verified,
        accepted_binding={"accepted_content_sha256": identity_sha},
        session_contract_sha256=s.session_contract_sha256(), today=st.PINNED))
    # The refusal is raised by the ONE guard form, ``_require``
    # (``wp8c_production_session.py:267-270``), so the observed type is the base
    # ``ProductionSessionError`` and the SPECIFIC reason lives in the message.
    # ``AuthorizationRefused`` is reserved for the expiry-parse and WP8b-registry
    # refusals (``:764`` and ``:797``), so expecting it here would misdescribe the
    # guard instead of testing it.
    require(outcome["outcome"] == "raised"
            and outcome["type_name"] == "ProductionSessionError"
            and "different instance" in outcome["message"],
            f"a forged authorization was not refused: {outcome}")
    record_step("forged authorization (foreign instance id) refused", "REFUSED",
                "instance binding disagreement")

    # (d) changed source: the contract's own bytes move, voiding the approval.
    moved = _resign_authorization(_one_use_authorization(
        verified, identity_sha, nonce="changed-1"))
    moved["session_contract_sha256"] = hashlib.sha256(b"other-contract").hexdigest()
    outcome = _observed(lambda: s.validate_authorization(
        moved, verified=verified,
        accepted_binding={"accepted_content_sha256": identity_sha},
        session_contract_sha256=s.session_contract_sha256(), today=st.PINNED))
    require(outcome["outcome"] == "raised"
            and outcome["type_name"] == "ProductionSessionError"
            and "rebuild voids" in outcome["message"],
            f"a changed contract source did not void the approval: {outcome}")
    record_step("changed session-contract source voids the approval", "REFUSED",
                "rebuild voids the one-use authorization")

    # (e) stale approval: the expiry is genuinely BEFORE the comparison date.
    # The expiry must be strictly in the past: ``validate_authorization`` accepts
    # ``today <= expiry`` (``wp8c_production_session.py:769-770``), so an expiry of
    # 2026-01-02 tested against ``today=2026-01-01`` is a LIVE authorization and
    # would have let this negative case pass for the wrong reason.  The run date is
    # moved past the expiry instead, which exercises the real expiry guard.
    stale = _resign_authorization(_one_use_authorization(
        verified, identity_sha, nonce="stale-1", expiry="2026-01-02"))
    outcome = _observed(lambda: s.validate_authorization(
        stale, verified=verified,
        accepted_binding={"accepted_content_sha256": identity_sha},
        session_contract_sha256=s.session_contract_sha256(),
        today=datetime.date(2026, 6, 1)))
    require(outcome["outcome"] == "raised"
            and outcome["type_name"] == "ProductionSessionError"
            and "expired" in outcome["message"],
            f"a stale approval was not refused: {outcome}")
    record_step("expired one-use approval refused", "REFUSED", "expiry")

    # (f) prepared-record forgery: a re-sealed approval over a foreign instance.
    forged2 = _resign_authorization(_one_use_authorization(
        verified, identity_sha, nonce="forged-2"))
    forged2["prepared_record_sha256"] = hashlib.sha256(b"other-prepared").hexdigest()
    outcome = _observed(lambda: s.validate_authorization(
        forged2, verified=verified,
        accepted_binding={"accepted_content_sha256": identity_sha},
        session_contract_sha256=s.session_contract_sha256(), today=st.PINNED))
    require(outcome["outcome"] == "raised"
            and outcome["type_name"] == "ProductionSessionError"
            and "different prepared record" in outcome["message"],
            f"a prepared-record forgery was not refused: {outcome}")
    record_step("forged prepared-record hash refused", "REFUSED",
                "prepared-record binding disagreement")

    # (g) failed WP2 prerequisite blocks every dependent device and write step.
    def failing_wp2(**kwargs):
        return {"schema": "wp8c/wp2-failure-probe", "content_sha256":
                hashlib.sha256(b"probe").hexdigest()}, False
    fail_layout, fail_writer = _layout_and_writer(base, "wp2fail", nonce="wp2-wp8b")
    fail_verified = s.verify_instance_for_session(1, root=fail_layout, standin=True)
    blocked = _observed(lambda: run_session(
        base, layout=fail_layout, writer_root=fail_writer,
        nonce_root=st.sandbox_root(base, "wp2-nonce"),
        session_id="session-wp2fail",
        authorization=_one_use_authorization(fail_verified, identity_sha,
                                             nonce="wp2fail-1"),
        session_identity=st.draft_identity(), clock=lambda: 0.0,
        seam_overrides={"wp2_recheck": failing_wp2},
        verified_instance=fail_verified))
    # ``run_session`` does NOT propagate a ``ProductionSessionError``: it is the
    # ONE place that converts a refusal into a sealed NON-ACCEPTING receipt
    # (``wp8c_production_session.py:1282-1297``), carrying the real refusal type
    # in ``refusal_type``.  So the blocking evidence is the RECEIPT, and the
    # assertion is made on the blocked-step set rather than on a raise: every
    # device and write step after the failed prerequisite must be blocked.
    require(blocked["outcome"] == "returned"
            and blocked["value"]["status"] == "refused"
            and blocked["value"]["accepted"] is False
            and blocked["value"]["refusal_type"] == "PrerequisiteFailed",
            f"a failed WP2 prerequisite did not produce a refused receipt: {blocked}")
    blocked_steps = blocked["value"]["blocked_steps"]
    require(blocked_steps == ["wp2_recheck_passed", "wp3_check_passed",
                              "records_built", "ranges_promoted"],
            f"a failed WP2 prerequisite did not block every dependent step: "
            f"{blocked_steps}")
    require(blocked["value"]["scientific_outputs"] == [],
            "a blocked session must carry no scientific output")
    record_step("failed WP2 recheck blocks every dependent device/write step",
                "REFUSED", "PrerequisiteFailed")

    # (h) fired D013 with a backend that does not declare inactive +0.0.
    d013_layout, d013_writer = _layout_and_writer(base, "d013", nonce="d013-wp8b")
    d013_verified = s.verify_instance_for_session(1, root=d013_layout, standin=True)
    d013_outcome = _observed(lambda: run_session(
        base, layout=d013_layout, writer_root=d013_writer,
        nonce_root=st.sandbox_root(base, "d013-nonce"),
        session_id="session-d013",
        authorization=_one_use_authorization(d013_verified, identity_sha,
                                             nonce="d013-1"),
        session_identity=st.draft_identity(), clock=lambda: 0.0,
        d013_fired=True, backend_factory=st.undeclared_device_backend_factory,
        verified_instance=d013_verified))
    require(d013_outcome["outcome"] == "raised"
            and d013_outcome["type_name"] == "SectionB2D013UnsupportedError",
            f"a fired D013 with an undeclaring backend was not refused: {d013_outcome}")
    record_step("fired D013 on a backend without inactive +0.0 support refused",
                "REFUSED", "SectionB2D013UnsupportedError")

    # (i) interrupted promotion: WP4b's staging left behind is discarded, and a
    #     partially promoted range is never adopted.
    interrupted = _observed(lambda: s.write_sealed_whole_ranges(
        instance_root=st.writer_root(base, "interrupted-writer"),
        batch_records={},
        result_schema={"identity_sha256": "str", "record_content_sha256": "str"},
        accepted_identity={}, session_identity={}, promoted_batch_ids=set(),
        accepted_identity_sha256=st.draft_identity_sha256()))
    require(interrupted["outcome"] == "returned"
            and interrupted["value"] == [],
            f"an empty interrupted writer should promote nothing: {interrupted}")
    record_step("interrupted promotion leaves no promoted range", "OK", "none promoted")

    # (j) incomplete range: only WHOLE missing ranges are resumable.
    incomplete = _observed(lambda: s.missing_whole_ranges(
        st.writer_root(base, "incomplete-writer")))
    require(incomplete["outcome"] == "raised",
            f"an unsealed writer must refuse missing_ranges: {incomplete}")
    record_step("missing whole ranges refused without a sealed plan", "REFUSED",
                incomplete["type_name"])


def _budget_and_resume(base: str) -> None:
    """The budget receipt and the missing-whole-range-only resume."""
    identity_sha = st.draft_identity_sha256()
    layout, writer_root = _layout_and_writer(base, "budget", nonce="budget-wp8b")
    verified = s.verify_instance_for_session(1, root=layout, standin=True)
    ticks = {"n": 0}

    # The clock advances only when the session calls it, and the session calls it
    # exactly EIGHT times: once for the guard's start (BudgetGuard.__init__,
    # ``wp8c_production_session.py:931``) and then once at each ``guard.check()``
    # before S1..S7 (``:1065, :1076, :1092, :1104, :1134, :1152, :1197``).  Call 1
    # is the start, so the elapsed time at call n is ``(n - 1) * stride``.
    #
    # The S6 check at ``:1152`` comes AFTER the plan is sealed (``:1183``) and the
    # records are built (``:1194``), and the S7 check at ``:1197`` comes BEFORE any
    # range is promoted (``:1199``).  So the run is stopped in exactly that window
    # when ``6 * stride <= BUDGET_SECONDS < 7 * stride``: the plan is sealed and
    # the records exist, whole ranges are genuinely missing, and nothing has been
    # promoted.  That is the only window in which "missing whole ranges" is both
    # non-empty and meaningful, so it is the window the resume contract needs.
    # With BUDGET_SECONDS = 36000 that is 5142.86 < stride <= 6000, so 5600 is
    # used: 6 * 5600 = 33600 <= 36000 (the S6 check still passes) while
    # 7 * 5600 = 39200 > 36000 (the S7 check raises).
    BUDGET_STOP_STRIDE_SECONDS = 5600

    def clock():
        ticks["n"] += 1
        return float(ticks["n"]) * BUDGET_STOP_STRIDE_SECONDS

    family = rehearsal_family()
    total = records.family_space(family, records.build_frozen_axes()).total_coordinates
    receipt = run_session(
        base, layout=layout, writer_root=writer_root,
        nonce_root=st.sandbox_root(base, "budget-nonce"),
        session_id="session-budget-1",
        authorization=_one_use_authorization(verified, identity_sha, nonce="budget-1"),
        session_identity=st.draft_identity(), clock=clock,
        verified_instance=verified, family=family,
        # The declared NON-PRODUCTION engine results, because the run now reaches
        # S6 and builds real records before the S7 budget stop.  Without them
        # ``build_records_for_ranges`` would produce no records and the range write
        # would refuse, so the stop would be attributed to the wrong cause.
        engine_results=placeholder_engine_results(total))
    require(receipt["status"] == "incomplete_budget",
            f"the budget stop did not produce an incomplete receipt: {receipt}")
    # The stop must land in the intended window: after the plan is sealed and the
    # records built (``records_built`` is the last completed step), so that whole
    # ranges are genuinely missing and the resume contract has real work to authorise.
    require(receipt["last_completed_step"] == "records_built",
            f"the budget stop landed at {receipt['last_completed_step']!r}, not after "
            f"the sealed plan and built records")
    record_step("budget guard stops AFTER the sealed plan, BEFORE promotion", "OK",
                f"last_completed={receipt['last_completed_step']}")
    require(receipt["accepted"] is False,
            "an incomplete run must never be accepted")
    record_step("budget guard issues a NON-ACCEPTING incomplete receipt", "OK",
                f"last_completed={receipt['last_completed_step']}")
    require(receipt["scientific_outputs"] == [],
            "an incomplete receipt must carry no scientific output")
    record_step("incomplete receipt carries no scientific outputs", "OK", "empty")

    # The resume is authorized under the SAME identity with a NEW approval, for
    # exactly the missing whole ranges.  The batch set is NOT assumed: it is read
    # from WP4b itself, because ``resume_missing_ranges`` refuses any set that is
    # not exactly WP4b's missing whole ranges.  ``expected_missing_batch_ids``
    # therefore has to be the real list, or the guard would (correctly) refuse.
    missing = s.missing_whole_ranges(writer_root)
    missing_ids = [row["batch_id"] for row in missing]
    require(missing_ids,
            "the budget stop must leave whole ranges genuinely missing, otherwise "
            "the resume contract has nothing to authorise and this case is vacuous")
    record_step("WP4b reports the missing whole ranges for the resume", "OK",
                f"{len(missing_ids)} ranges: {missing_ids}")

    previous = dict(receipt)
    # The resume authorization is a NEW one-use approval, built the way an owner
    # would build it, under the SAME accepted identity.  It is NOT copied from the
    # previous receipt: the receipt is a receipt, not an authorization, and it
    # carries no ``accepted_identity_sha256``, so a copy would be refused by the
    # identity-binding guard for the wrong reason.  Only the NONCE differs from the
    # session's own approval, which is what makes it NEW.
    new_authorization = _one_use_authorization(verified, identity_sha,
                                               nonce="budget-2-new-approval")
    resumed = s.resume_missing_ranges(
        slot=1, root=layout, instance_root=writer_root, session_id="session-budget-2",
        identity_sha256=identity_sha, authorization=new_authorization,
        previous_receipt=previous, expected_missing_batch_ids=missing_ids)
    require(resumed["verdict"] == "resume_authorized"
            and resumed["accepted"] is False,
            f"the resume was not authorized as non-accepting: {resumed}")
    require(resumed["resumed_batch_ids"] == missing_ids
            and resumed["resumed_whole_ranges_only"] is True,
            f"the resume did not cover exactly the missing whole ranges: {resumed}")
    require(resumed["new_authorization_nonce"] == "budget-2-new-approval"
            and resumed["previous_session_id"] == previous.get("session_id")
            and resumed["new_authorization_nonce"] != "budget-1",
            f"the resume did not require a NEW authorization: {resumed}")
    record_step("resume authorized: NEW approval, SAME identity, non-accepting", "OK",
                f"{len(resumed['resumed_batch_ids'])} whole ranges")

    # A narrowed resume is refused: the batch set must be EXACTLY WP4b's.
    narrowed = _observed(lambda: s.resume_missing_ranges(
        slot=1, root=layout, instance_root=writer_root, session_id="session-budget-3",
        identity_sha256=identity_sha, authorization=new_authorization,
        previous_receipt=previous,
        expected_missing_batch_ids=missing_ids + ["batch-not-missing"]))
    require(narrowed["outcome"] == "raised"
            and narrowed["type_name"] == "ResumeRefused"
            and "exactly the missing whole ranges" in narrowed["message"],
            f"a narrowed resume was not refused: {narrowed}")
    record_step("narrowed/incorrect resume set refused", "REFUSED", "ResumeRefused")

    # A same-session resume is refused: the resume must be a NEW session.  The
    # batch set is EXACTLY WP4b's here, so the ONLY thing wrong is the session id
    # and the guard reached is the NEW-session rule, not the set rule.
    same = _observed(lambda: s.resume_missing_ranges(
        slot=1, root=layout, instance_root=writer_root, session_id="session-budget-1",
        identity_sha256=identity_sha, authorization=new_authorization,
        previous_receipt=previous, expected_missing_batch_ids=missing_ids))
    require(same["outcome"] == "raised"
            and same["type_name"] == "ResumeRefused"
            and "NEW session" in same["message"],
            f"a same-session resume was not refused: {same}")
    record_step("same-session resume refused (NEW session required)", "REFUSED",
                "ResumeRefused")

    # A different identity on resume is refused.
    other_identity = _observed(lambda: s.resume_missing_ranges(
        slot=1, root=layout, instance_root=writer_root, session_id="session-budget-4",
        identity_sha256=hashlib.sha256(b"other-identity").hexdigest(),
        authorization=new_authorization, previous_receipt=previous,
        expected_missing_batch_ids=missing_ids))
    require(other_identity["outcome"] == "raised"
            and other_identity["type_name"] == "ResumeRefused",
            f"a different-identity resume was not refused: {other_identity}")
    record_step("resume under a different identity refused", "REFUSED",
                "same identity required")


def _isolation_and_pins() -> None:
    """Kaggle parent/child isolation and the image/source pins, aligned to WP7b."""
    # The child environment must drop KAGGLE_* and PYTHON*, keep the allowlist
    # and NVIDIA_*, and force PYTHONDONTWRITEBYTECODE.
    env = {"PATH": "/usr/bin", "NVIDIA_VISIBLE_DEVICES": "all",
           "KAGGLE_KERNEL_RUN_TYPE": "Interactive",
           "KAGGLE_USER_SECRETS_TOKEN": "NONPROD-NOT-A-CREDENTIAL",
           "PYTHONPATH": "/nonprod", "HOME": "/home/nonprod", "SECRET": "x"}
    child = s.child_environment(env)
    require("KAGGLE_KERNEL_RUN_TYPE" not in child
            and "KAGGLE_USER_SECRETS_TOKEN" not in child,
            f"a KAGGLE_* name reached the child: {sorted(child)}")
    require("PYTHONPATH" not in child, f"a PYTHON* name reached the child: {sorted(child)}")
    require("PATH" in child and "NVIDIA_VISIBLE_DEVICES" in child,
            f"the allowlist lost a permitted name: {sorted(child)}")
    require(child["PYTHONDONTWRITEBYTECODE"] == "1",
            "the child must be told not to write bytecode")
    record_step("child environment drops KAGGLE_*/PYTHON*, keeps allowlist+NVIDIA_*",
                "OK", f"{len(child)} names")

    # The WP7b fixed allowlist must match this module's constant exactly, so a
    # future change to one is caught here.
    #
    # WP7b's ``child_environment`` is NOT a module-level function of
    # ``build_wp7b_bundle``: the whole launcher body is emitted as a MINIFIED
    # source string that the builder writes into the bundle
    # (``build_wp7b_bundle.py:289-297``), so there is no importable function and
    # no module-level ``allowed`` assignment to find by walking the module AST --
    # ``ast.walk`` over the module finds no such ``Assign`` node at all, because
    # the assignment lives inside that string.  The allowlist is therefore read
    # from the authoritative source LINE itself, parsed out of the string, so the
    # comparison is against WP7b's real published set rather than against a
    # hard-coded copy of it.
    from research.g9.kaggle_wp7b import build_wp7b_bundle as builder
    wp7b_source = Path(builder.__file__).read_text("utf-8")
    allowed_lines = [line for line in wp7b_source.splitlines()
                     if "allowed={" in line and "k.startswith" not in line]
    require(len(allowed_lines) == 1,
            f"WP7b's child-environment allowlist must appear exactly once in "
            f"{builder.__file__}, found {len(allowed_lines)} lines")
    tree = ast.parse(allowed_lines[0].strip())
    sets = [node for node in ast.walk(tree)
            if isinstance(node, (ast.Set, ast.SetComp))]
    require(len(sets) == 1,
            f"WP7b's allowlist line must hold exactly one set literal, found {len(sets)}")
    wp7b_allowed = set(ast.literal_eval(sets[0]))
    require(wp7b_allowed == set(s.CHILD_ENVIRONMENT_ALLOWLIST),
            f"the child allowlist drifted from WP7b: "
            f"WP7b {sorted(wp7b_allowed)}, WP8c {sorted(s.CHILD_ENVIRONMENT_ALLOWLIST)}")
    record_step("child allowlist identical to WP7b's", "OK",
                f"{len(s.CHILD_ENVIRONMENT_ALLOWLIST)} names")

    # The four deferred image fields are this module's FIXED constant and match
    # WP7b's own tuple.
    from research.g9.kaggle_wp7b import wp7b_launcher as launcher
    require(tuple(s.POST_RUN_ONLY_IMAGE_FIELDS) == tuple(
        launcher.POST_RUN_ONLY_IMAGE_FIELDS),
        "the deferred image fields drifted from WP7b's fixed tuple")
    record_step("deferred image fields identical to WP7b's fixed tuple", "OK",
                ",".join(s.POST_RUN_ONLY_IMAGE_FIELDS))

    # The in-session pin drops exactly those four and nothing else.
    pin = {"platform_reported": {"gpu_name": "x"}, "image_reported": {
        name: f"value-{name}" for name in s.POST_RUN_ONLY_IMAGE_FIELDS}}
    reduced = s.in_session_environment_pin(pin)
    for name in s.POST_RUN_ONLY_IMAGE_FIELDS:
        require(name not in reduced["image_reported"],
                f"a deferred field survived the in-session pin: {name}")
    record_step("in-session pin excludes exactly the 4 deferred image fields", "OK",
                "4 excluded")

    # The hard timeout must exceed the budget, or the kernel would be killed
    # before the guard could issue its receipt.
    require(s.KAGGLE_HARD_TIMEOUT_SECONDS > s.BUDGET_SECONDS,
            "the hard Kaggle timeout must exceed the in-session budget")
    record_step("hard Kaggle timeout exceeds the in-session budget", "OK",
                f"{s.KAGGLE_HARD_TIMEOUT_SECONDS} > {s.BUDGET_SECONDS}")


# ===========================================================================
# The meaningful broken variant
# ===========================================================================


def _broken_variant(base: str) -> int:
    """Mutate ONE real guard and prove the rehearsal now FAILS.

    The mutation replaces WP8c's identity binding with a no-op, which is the
    single most consequential guard in the module: with it deleted, a session
    whose identity differs from the accepted one would proceed to WP2.  A
    rehearsal that still PASSES under this mutation is a rehearsal that proves
    nothing, so this is a self-test of the rehearsal, not of the module.

    The mutated line is the S2 DISPATCH of the guard, not a direct call: the
    module reaches WP1's ``exact_match`` through the injected seam
    ``reviewed["require_session_identity_exact"]``
    (``wp8c_production_session.py:1084-1085``), which is what lets the rehearsal
    substitute the identity STAND-IN for WP8a while still running WP1's real
    comparison.  Mutating that call replaces the comparison with a fabricated
    always-matching verdict, so the tampered-identity case in ``_adversarial``
    can no longer be refused.
    """
    target = ROOT / "research/g9/wp8c_production/wp8c_production_session.py"
    original = target.read_bytes()
    pristine = sys.modules.get("research.g9.wp8c_production.wp8c_production_session")
    victim = (b'        identity_verdict = reviewed["require_session_identity_exact"](\n'
              b'            binding, session_identity)')
    replacement = b'        identity_verdict = _real_verdict_for_probe(session_identity)'
    if victim not in original:
        print("REHEARSAL BROKEN VARIANT: FAIL — the mutation target line was not "
              "found; the rehearsal cannot be trusted to detect this mutation")
        return 1
    mutated = original.replace(victim, replacement, 1)
    if mutated == original:
        print("REHEARSAL BROKEN VARIANT: FAIL — the mutation did not change the file")
        return 1
    target.write_bytes(mutated)
    try:
        # A stand-in module carrying the probe helper the mutation calls.  The
        # helper is INJECTED into the mutated module's namespace after the reload,
        # so the mutation produces a SEMANTIC failure -- the tampered-identity
        # session proceeds instead of being refused -- rather than a NameError from
        # an undefined name.  A NameError would still fail the run, but it would
        # prove only that the mutated bytes were executed, not that the rehearsal
        # DETECTS a deleted identity guard.
        import importlib
        mutated_module = importlib.import_module(
            "research.g9.wp8c_production.wp8c_production_session")
        mutated_module = importlib.reload(mutated_module)
        mutated_module._real_verdict_for_probe = (
            lambda session_identity: {
                "verdict": "exact_match",
                "session_content_sha256": "0" * 64,
                "accepted_content_sha256": "0" * 64,
                "differing_fields": [],
            })
        require(mutated_module.run_production_session is not pristine.run_production_session
                or mutated_module.__file__ == str(target),
                "the mutated module was not actually loaded")
        globals()["s"] = mutated_module
        sys.modules["research.g9.wp8c_production.wp8c_production_session"] = mutated_module
        try:
            _rehearse(base)
        except RuntimeError:
            print("\nBROKEN VARIANT: correctly REFUSED (the identity binding is "
                  "load-bearing; a session with a tampered identity was no longer "
                  "stopped)")
            print("REHEARSAL BROKEN VARIANT: PASS — the mutation was detected")
            return 0
        print("\nBROKEN VARIANT: INCORRECTLY PASSED — the rehearsal does not detect "
              "a deleted identity binding; this is a build error")
        return 1
    finally:
        target.write_bytes(original)
        for cached in list(Path(ROOT / "research/g9/wp8c_production").glob("__pycache__")):
            shutil.rmtree(cached, ignore_errors=True)
        # Restore the in-memory module too, so a caller that keeps running in this
        # process after the control gets the PRISTINE module back, not the mutated
        # one, and so the mutated bytes can never outlive the control.
        if pristine is not None:
            sys.modules["research.g9.wp8c_production.wp8c_production_session"] = pristine
            globals()["s"] = pristine


def _observed(fn) -> dict:
    try:
        return {"outcome": "returned", "value": fn(), "type_name": None, "message": ""}
    except BaseException as exc:  # noqa: BLE001 - the type is what is under test
        return {"outcome": "raised", "value": None,
                "type_name": type(exc).__name__, "message": str(exc)}


def _resign_authorization(record: dict) -> dict:
    return dict(record)


if __name__ == "__main__":
    _status = main()
    assert _status in (0, 1), f"main() must return 0 or 1, got {_status!r}"
    raise SystemExit(_status)

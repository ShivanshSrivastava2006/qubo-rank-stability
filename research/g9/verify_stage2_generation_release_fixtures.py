#!/usr/bin/env python3
"""Synthetic fixtures for the UNAPPROVED Stage-2 generation release path.

Everything here is synthetic and non-scientific.  No canonical input is read,
no real candidate is drawn, no ground truth is produced, nothing is written
outside a ``tempfile.TemporaryDirectory`` and no network is used.  The real
preregistered seed material is reached only to prove that it is REFUSED.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from research.g9 import stage2_generation_contract as contract  # noqa: E402
from research.g9 import stage2_generation_release as r  # noqa: E402
from research.g9 import stage2_generator as generator  # noqa: E402
from research.g9 import stage2_generator_guard as guard  # noqa: E402

import numpy as np  # noqa: E402


class FixtureError(RuntimeError):
    pass


COUNT = 0


def require(condition: bool, message: str) -> None:
    global COUNT
    if not condition:
        raise FixtureError(message)
    COUNT += 1


def refused(fn, label: str, needle: str = "") -> None:
    global COUNT
    try:
        fn()
    except r.GenerationReleaseError as exc:
        if needle and needle not in str(exc):
            raise FixtureError(f"{label}: refused for the wrong reason: {exc}") from exc
        COUNT += 1
        return
    except Exception as exc:
        raise FixtureError(f"{label}: raw {type(exc).__name__} instead of GenerationReleaseError") from exc
    raise FixtureError(f"{label}: accepted")


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("ascii")


def independent_content_sha256(record: dict) -> str:
    body = {key: value for key, value in record.items() if key != "content_sha256"}
    return hashlib.sha256(canonical(body)).hexdigest()


def fake(tag: str) -> str:
    return hashlib.sha256(tag.encode("ascii")).hexdigest()


# --------------------------------------------------------------------------
# Synthetic inputs and approvals
# --------------------------------------------------------------------------
SYNTHETIC_PRICES = (3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22)
SYNTHETIC_STAGE1 = tuple(tuple(range(n, n + 5)) for n in range(0, 20, 5))
INPUTS = contract.ScreeningInputs(prices=SYNTHETIC_PRICES, K=6, C=2, B=60,
                                  stage1_partition=SYNTHETIC_STAGE1)


def synthetic_record() -> dict:
    """A hand-built record with the full key set and the guard's schema."""
    config = {"Build Dependencies": {"blas": {"name": "synthetic-blas", "version": "0.0.1",
                                              "openblas configuration": "SyntheticConfig"},
                                     "lapack": {"name": "synthetic-lapack", "version": "0.0.1",
                                                "openblas configuration": "SyntheticConfig"}}}
    record = {
        "schema": r.SCHEMA,
        "status": r.RECORD_STATUS,
        "owner_approval": r.OWNER_APPROVAL,
        "approval_statement": r.APPROVAL_STATEMENT,
        "sources": {
            "guard": {"path": "research/g9/stage2_generator_guard.py", "sha256": fake("guard")},
            "generator": {"path": "research/g9/stage2_generator.py", "sha256": fake("generator")},
            "validator": {"path": "research/g9/stage2_generation_contract.py", "sha256": fake("validator")},
            "planner": {"path": "research/g9/plan_stage2_generator.py", "sha256": fake("planner")},
            "contract": {"path": "research/g9/stage2_generation_contract.py", "sha256": fake("contract")},
            "release": {"path": r.RELEASE_MODULE_PATH, "sha256": fake("release")},
        },
        "runtime": {
            "python": {"implementation": "cpython", "sys_version": "3.12.3 (synthetic)",
                       "version_info": [3, 12, 3, "final", 0], "hexversion": 0x030C03F0},
            "numpy": {"version": "2.4.4", "config": config,
                      "config_sha256": hashlib.sha256(canonical(config)).hexdigest()},
            "numpy_binaries": {"numpy/_core/_multiarray_umath.synthetic.so": fake("umath"),
                               "numpy.libs/libsynthetic_openblas.so": fake("blas")},
            "thread_and_dispatch_environment": {key: None for key in guard.THREAD_AND_DISPATCH_KEYS},
        },
        "backend_fingerprint": {"implementation": "cpython", "python": "3.12.3 (synthetic)",
                                "python_version": "3.12.3", "numpy_version": "2.4.4",
                                "numpy_linalg_backend_sha256": fake("backend"),
                                "numpy_blas": "synthetic-blas", "numpy_lapack": "synthetic-lapack"},
    }
    record["content_sha256"] = independent_content_sha256(record)
    return record


def reseal(record: dict) -> dict:
    body = copy.deepcopy(record)
    body["content_sha256"] = independent_content_sha256(body)
    return body


def owner_approval(record_hash: str, *, label: str = "synthetic-owner-review",
                   scope: str = r.OWNER_APPROVAL_SCOPE,
                   status: str = r.APPROVAL_STATUS) -> dict:
    return {
        "schema": r.APPROVAL_SCHEMA,
        "status": status,
        "approves_record_content_sha256": record_hash,
        "statement": r.DRAW_APPROVAL_STATEMENT,
        "label": label,
        "scope": scope,
    }


def synthetic_approval(record: dict) -> dict:
    return owner_approval(record["content_sha256"], label="synthetic",
                          scope=r.FIXTURE_APPROVAL_SCOPE)


TOKEN = r.FIXTURE_CONTEXT_TOKEN


# --------------------------------------------------------------------------
# 1. The record
# --------------------------------------------------------------------------
def check_record_shape() -> tuple[dict, str]:
    record = synthetic_record()
    pinned = independent_content_sha256(record)
    body = r.validate_candidate_implementation_record(record, pinned)
    require(body["content_sha256"] == pinned, "record content hash is not independently reproducible")
    require(record["status"] == "unapproved_candidate" and record["owner_approval"] == "absent"
            and "not owner approval" in record["approval_statement"],
            "record does not declare itself unapproved")
    # The statements are this module's own constants, so a record that quotes
    # them differently is refused.  This pins the wording, not just the fields.
    for label, statement in (
        ("empty", ""),
        ("reworded", "Approved by the owner."),
        ("truncated", r.APPROVAL_STATEMENT[:-1]),
        ("doubled", r.APPROVAL_STATEMENT + " "),
    ):
        reworded = copy.deepcopy(record)
        reworded["approval_statement"] = statement
        reworded = reseal(reworded)
        refused(lambda reworded=reworded: r.validate_candidate_implementation_record(
            reworded, reworded["content_sha256"]), f"approval statement: {label}")
    require(set(record["sources"]) == {"guard", "generator", "validator", "planner", "contract", "release"},
            "record must pin generator, validator, contract, planner, guard and release")
    require(record["sources"]["validator"]["path"] == record["sources"]["contract"]["path"],
            "validator and contract must name the generation-contract source")
    for label, sources in record["sources"].items():
        bad_hash = copy.deepcopy(record)
        bad_hash["sources"][label] = {"path": sources["path"], "sha256": "not-a-sha256"}
        bad_hash = reseal(bad_hash)
        refused(lambda bad_hash=bad_hash: r.validate_candidate_implementation_record(
            bad_hash, bad_hash["content_sha256"]), f"malformed source hash: {label}")
        extra_key = copy.deepcopy(record)
        extra_key["sources"][label] = {**sources, "note": "extra"}
        extra_key = reseal(extra_key)
        refused(lambda extra_key=extra_key: r.validate_candidate_implementation_record(
            extra_key, extra_key["content_sha256"]), f"malformed source entry: {label}")
        empty_path = copy.deepcopy(record)
        empty_path["sources"][label] = {"path": "", "sha256": sources["sha256"]}
        empty_path = reseal(empty_path)
        refused(lambda empty_path=empty_path: r.validate_candidate_implementation_record(
            empty_path, empty_path["content_sha256"]), f"empty source path: {label}")
        # A path that is not a string is refused by the type half of the same
        # check; the "" case above only exercises the emptiness half.  A
        # non-string path is ALSO caught by each source's own declared-path
        # check further down, so the guard's snapshot validation is disabled for
        # the duration: otherwise that check would fire first and the shape
        # check would be masked and unobservable.
        original_validate = guard.validate_snapshot
        guard.validate_snapshot = lambda snapshot: json.loads(
            json.dumps(snapshot, sort_keys=True))
        try:
            for bad_path, why in ((7, "not a string"), (None, "None"), ([], "list")):
                typed_path = copy.deepcopy(record)
                typed_path["sources"][label] = {"path": bad_path, "sha256": sources["sha256"]}
                typed_path = reseal(typed_path)
                refused(lambda typed_path=typed_path: r.validate_candidate_implementation_record(
                    typed_path, typed_path["content_sha256"]),
                    f"source path {why} in isolation: {label}")
        finally:
            guard.validate_snapshot = original_validate
    require(set(record["backend_fingerprint"]) == set(generator.runtime_fingerprint()),
            "record backend fingerprint key set drift")
    for label, mutate_fp in (
        ("not an object", "string"),
        ("dropped key", "drop"),
        ("extra key", "extra"),
    ):
        broken = copy.deepcopy(record)
        if mutate_fp == "string":
            broken["backend_fingerprint"] = "not a fingerprint"
        elif mutate_fp == "drop":
            broken["backend_fingerprint"] = {k: v for k, v in record["backend_fingerprint"].items()
                                             if k != "numpy_linalg_backend_sha256"}
        else:
            broken["backend_fingerprint"] = {**record["backend_fingerprint"], "extra": 1}
        broken = reseal(broken)
        refused(lambda broken=broken: r.validate_candidate_implementation_record(
            broken, broken["content_sha256"]), f"backend fingerprint: {label}")
    # A runtime the guard itself refuses must not be accepted as pinned.
    for label, edit in (
        ("numpy version not a string", lambda s: s["runtime"]["numpy"].update(version="")),
        ("binary key outside the install roots", lambda s: s["runtime"]["numpy_binaries"].update(
            {"/usr/lib/libc.so": fake("libc")})),
        ("config hash stale", lambda s: s["runtime"]["numpy"]["config"].update(extra="x")),
    ):
        broken = copy.deepcopy(record)
        edit(broken)
        broken = reseal(broken)
        refused(lambda broken=broken: r.validate_candidate_implementation_record(
            broken, broken["content_sha256"]), f"guard snapshot validation: {label}")
    # No argument can make the builder render an approved record.
    for kwargs in ({"approval": "owner"}, {"status": "owner_approved"}, {"owner_approval": "granted"}):
        try:
            r.build_candidate_implementation_record(**kwargs)  # type: ignore[call-arg]
        except TypeError:
            require(True, "")
        else:
            raise FixtureError("record builder accepted an authority keyword")

    labels = ("status owner_approved", "status approved", "owner_approval granted",
              "schema swapped", "planner dropped", "contract dropped", "validator dropped",
              "release dropped", "backend fingerprint dropped", "extra key")
    edits = {
        "status owner_approved": lambda b: b.update(status="owner_approved"),
        "status approved": lambda b: b.update(status="approved"),
        "owner_approval granted": lambda b: b.update(owner_approval="granted"),
        "schema swapped": lambda b: b.update(schema="decisions_os/g9_stage2_generation_implementation_record/v1"),
        "planner dropped": lambda b: b["sources"].pop("planner"),
        "contract dropped": lambda b: b["sources"].pop("contract"),
        "validator dropped": lambda b: b["sources"].pop("validator"),
        "release dropped": lambda b: b["sources"].pop("release"),
        "backend fingerprint dropped": lambda b: b.pop("backend_fingerprint"),
        "extra key": lambda b: b.update(authority="owner"),
    }
    for label in labels:
        # Edit FIRST, then reseal.  Sealing first leaves a stale content hash,
        # so every case would be caught by the hash check and the check under
        # test would never run.
        forged = copy.deepcopy(record)
        edits[label](forged)
        forged = reseal(forged)
        refused(lambda forged=forged: r.validate_candidate_implementation_record(
            forged, forged["content_sha256"]), f"forged record: {label}")
    tampered = copy.deepcopy(record)
    tampered["runtime"]["numpy"]["version"] = "9.9.9"
    refused(lambda: r.validate_candidate_implementation_record(tampered, pinned),
            "tampered body, stale hash", "record content hash mismatch")
    refused(lambda: r.validate_candidate_implementation_record(record, fake("elsewhere")),
            "wrong pin", "independently pinned")
    refused(lambda: r.validate_candidate_implementation_record(record, pinned.upper()),
            "uppercase pin", "expected record SHA-256")
    refused(lambda: r.validate_candidate_implementation_record(record, None),
            "missing pin", "expected record SHA-256 is required")
    refused(lambda: r.validate_candidate_implementation_record(record, 12345),
            "non-string pin", "lowercase SHA-256")
    # A backend fingerprint that is not an object at all is refused by the type
    # check, not merely by the key set.
    for label, value in (("string", "not a fingerprint"), ("None", None), ("list", []),
                         ("int", 7)):
        broken = copy.deepcopy(record)
        broken["backend_fingerprint"] = value
        broken = reseal(broken)
        refused(lambda broken=broken: r.validate_candidate_implementation_record(
            broken, broken["content_sha256"]), f"backend fingerprint type: {label}")
    # Every pinned source is checked for its declared path, so a moved path
    # must be refused for each of them.  Resealed after the edit, so the
    # content-hash check cannot shadow the path check.
    declared = {
        "generator": "research/g9/stage2_generator.py",
        "validator": "research/g9/stage2_generation_contract.py",
        "contract": "research/g9/stage2_generation_contract.py",
        "planner": "research/g9/plan_stage2_generator.py",
        "guard": "research/g9/stage2_generator_guard.py",
        "release": r.RELEASE_MODULE_PATH,
    }
    require({label: entry["path"] for label, entry in record["sources"].items()} == declared,
            "the declared source paths drift")
    for label, path in declared.items():
        moved = copy.deepcopy(record)
        moved["sources"][label] = {"path": "research/g9/other.py",
                                   "sha256": record["sources"][label]["sha256"]}
        moved = reseal(moved)
        refused(lambda moved=moved: r.validate_candidate_implementation_record(
            moved, moved["content_sha256"]), f"source path moved: {label}")
    # For the two guard-pinned sources (generator, validator) that refusal is
    # normally the guard's own path check firing first.  Disable the guard's
    # snapshot validation for one call so the record's own path check is what
    # refuses; otherwise the record's check would be masked and unobservable.
    # "guard" itself has no record-level path check, only the guard's.
    original_validate = guard.validate_snapshot
    for label in ("generator", "validator"):
        guard.validate_snapshot = lambda snapshot: json.loads(
            json.dumps(snapshot, sort_keys=True))
        try:
            moved = copy.deepcopy(record)
            moved["sources"][label] = {"path": "research/g9/other.py",
                                       "sha256": record["sources"][label]["sha256"]}
            moved = reseal(moved)
            refused(lambda moved=moved: r.validate_candidate_implementation_record(
                moved, moved["content_sha256"]), f"record path check alone: {label}")
        finally:
            guard.validate_snapshot = original_validate
    # With the guard's validation active, the same move is still refused.
    for label in ("generator", "validator"):
        moved = copy.deepcopy(record)
        moved["sources"][label] = {"path": "research/g9/other.py",
                                   "sha256": record["sources"][label]["sha256"]}
        moved = reseal(moved)
        refused(lambda moved=moved: r.validate_candidate_implementation_record(
            moved, moved["content_sha256"]), f"guard path check: {label}")
    # An approval statement that does not match the module's own.
    reworded = copy.deepcopy(record)
    reworded["approval_statement"] = "Approved by the owner."
    reworded = reseal(reworded)
    refused(lambda: r.validate_candidate_implementation_record(
        reworded, reworded["content_sha256"]), "reworded approval statement")
    return record, pinned


def check_actual_record() -> dict:
    """One real capture of this process, checked against independent hashes."""
    record = r.build_candidate_implementation_record()
    pinned = independent_content_sha256(record)
    r.validate_candidate_implementation_record(record, pinned)
    for label, rel in (("generator", "research/g9/stage2_generator.py"),
                       ("validator", "research/g9/stage2_generation_contract.py"),
                       ("planner", "research/g9/plan_stage2_generator.py"),
                       ("guard", "research/g9/stage2_generator_guard.py"),
                       ("release", r.RELEASE_MODULE_PATH)):
        entry = record["sources"][label]
        require(entry["path"] == rel, f"actual {label} path drift")
        require(entry["sha256"] == hashlib.sha256((ROOT / rel).read_bytes()).hexdigest(),
                f"actual {label} hash is not independently reproduced")
    require(record["sources"]["contract"]["sha256"] == record["sources"]["validator"]["sha256"],
            "contract and validator must pin the same source")
    require(record["runtime"]["python"]["sys_version"] == sys.version
            and record["runtime"]["numpy"]["version"] == __import__("numpy").__version__,
            "actual runtime identity drift")
    require(record["backend_fingerprint"] == generator.runtime_fingerprint(),
            "actual backend fingerprint drift")
    require(record["backend_fingerprint"]["numpy_linalg_backend_sha256"] ==
            generator.runtime_fingerprint()["numpy_linalg_backend_sha256"],
            "backend fingerprint is not the generator's own")
    return {"record": record, "pinned": pinned}


# --------------------------------------------------------------------------
# 2. The approval check
# --------------------------------------------------------------------------
def check_approval_check(record: dict, pinned: str) -> None:
    # A synthetic approval is refused on every non-fixture path.
    approval = synthetic_approval(record)
    refused(lambda: r.check_against_record(record, approval, pinned), "synthetic approval off the fixture path",
            "synthetic")
    refused(lambda: r.check_against_record(record, approval, pinned, fixture_context="something else"),
            "synthetic approval with a wrong context", "synthetic")
    refused(lambda: r.check_against_record(record, approval, pinned, fixture_context=None),
            "synthetic approval with no context", "synthetic")
    # It is accepted only on the named fixture path, and grants no authority.
    evidence, _ = r.check_against_record(record, approval, pinned, fixture_context=TOKEN)
    require(evidence["checked"] == "synthetic_fixture_path" and evidence["synthetic"] is True
            and evidence["owner_approved"] == "absent"
            and evidence["draw_authority"] == r.SYNTHETIC_DRAW_AUTHORITY
            and evidence["record_content_sha256"] == pinned,
            "synthetic fixture evidence overstates authority or drifts")
    # A synthetic label with a real scope is still refused off the fixture path.
    mislabelled = owner_approval(record["content_sha256"], label="synthetic",
                                 scope=r.OWNER_APPROVAL_SCOPE)
    refused(lambda: r.check_against_record(record, mislabelled, pinned),
            "synthetic label with owner scope", "synthetic")
    refused(lambda: r.check_against_record(record, mislabelled, pinned, fixture_context=TOKEN),
            "synthetic label with owner scope on the fixture path", "scope")

    # The approval must name THIS record's exact content hash.
    other = reseal({**record, "sources": {**record["sources"],
                                         "planner": {"path": "research/g9/plan_stage2_generator.py",
                                                     "sha256": fake("other-planner")}}})
    refused(lambda: r.check_against_record(record, owner_approval(other["content_sha256"]), pinned),
            "approval names a different record", "exact content SHA-256")
    refused(lambda: r.check_against_record(record, owner_approval("0" * 64), pinned),
            "approval names a wrong hash", "exact content SHA-256")
    refused(lambda: r.check_against_record(record, owner_approval(record["content_sha256"].upper()), pinned),
            "uppercase approval hash", "lowercase SHA-256")

    # Malformed and non-approved approvals are refused even with a real hash.
    base = owner_approval(record["content_sha256"])
    cases = (
        ("not an object", "string", None),
        ("missing key", None, lambda a: a.pop("scope")),
        ("extra key", None, lambda a: a.update(authority="owner")),
        ("wrong schema", None, lambda a: a.update(schema="decisions_os/other/v1")),
        ("status pending", None, lambda a: a.update(status="pending")),
        ("status absent", None, lambda a: a.update(status="absent")),
        ("status synthetic", None, lambda a: a.update(status="synthetic")),
        ("statement reworded", None, lambda a: a.update(statement="Approved.")),
        ("empty label", None, lambda a: a.update(label="")),
        ("empty scope", None, lambda a: a.update(scope="")),
        ("scope not a string", None, lambda a: a.update(scope=7)),
        ("label not a string", None, lambda a: a.update(label=7)),
        ("record hash not a string", None, lambda a: a.update(approves_record_content_sha256=7)),
        ("record hash short", None, lambda a: a.update(approves_record_content_sha256="ab")),
        ("record hash uppercase", None, lambda a: a.update(approves_record_content_sha256="A" * 64)),
        ("fixture scope off the fixture path", None,
         lambda a: a.update(scope=r.FIXTURE_APPROVAL_SCOPE)),
    )
    for label, value, edit in cases:
        if value is None:
            approval = dict(base)
            edit(approval)
        else:
            approval = value
        refused(lambda approval=approval: r.check_against_record(record, approval, pinned, fixture_context=TOKEN),
                f"malformed approval: {label}")
        # A non-string scope is ALSO refused by the synthetic-scope check just
        # below it, so the shape check is masked unless that comparison is
        # neutralised for the call.  Patching the module's scope constant to the
        # malformed value makes the two checks agree, leaving the shape check as
        # the only thing that can refuse.
        for bad_scope, why in ((7, "not a string"), (None, "None"), ([], "list")):
            typed = dict(base)
            typed["scope"] = bad_scope
            original_scope = r.FIXTURE_APPROVAL_SCOPE
            original_owner_scope = r.OWNER_APPROVAL_SCOPE
            r.FIXTURE_APPROVAL_SCOPE = bad_scope
            r.OWNER_APPROVAL_SCOPE = bad_scope
            try:
                refused(lambda typed=typed: r.check_against_record(
                    record, typed, pinned, fixture_context=TOKEN),
                    f"approval scope {why} in isolation")
            finally:
                r.FIXTURE_APPROVAL_SCOPE = original_scope
                r.OWNER_APPROVAL_SCOPE = original_owner_scope
    refused(lambda: r.check_against_record(record, None, pinned, fixture_context=TOKEN),
            "missing approval", "approval must be an object")

    # A well-formed non-synthetic owner approval is accepted on the real path and
    # is the ONLY thing that could ever reach the real seed material.
    real, returned = r.check_against_record(record, base, pinned)
    require(real["checked"] == "owner_approval" and real["synthetic"] is False
            and real["owner_approved"] == "present" and real["draw_authority"] == "asserted_by_approval",
            "owner approval evidence drift")
    require(returned["content_sha256"] == pinned and set(returned["sources"]) == set(record["sources"]),
            "check_against_record did not return the validated record")
    require(r._approval_permits_real_material(approval_with_status(record, r.APPROVAL_STATUS), None) is True,
            "a well-formed owner approval must permit real material off the fixture path")
    # A synthetic label is refused even when everything else is a perfect
    # owner approval: that is the whole point of the label.
    for label, approval in (
        ("synthetic label with owner scope", owner_approval(
            record["content_sha256"], label="synthetic", scope=r.OWNER_APPROVAL_SCOPE)),
        ("synthetic label with fixture scope", synthetic_approval(record)),
    ):
        require(r._approval_permits_real_material(approval, None) is False,
                f"a synthetic approval permitted real material: {label}")
    require(r._approval_permits_real_material(base, TOKEN) is False,
            "an owner approval must not permit real material on the fixture path")
    require(r._approval_permits_real_material(synthetic_approval(record), None) is False,
            "a synthetic approval must never permit real material")
    require(r._approval_permits_real_material(None, None) is False,
            "a missing approval must never permit real material")
    for label, approval in (
        ("non-approved status", approval_with_status(record, "pending")),
        ("reworded statement", {**base, "statement": "Approved by the owner."}),
    ):
        # Fail closed: it refuses rather than answering False.
        refused(lambda approval=approval: r._approval_permits_real_material(approval, None),
                f"real-material permission for an invalid approval: {label}")
    require(r._approval_permits_real_material(
        owner_approval(record["content_sha256"], scope="something_else"), None) is False,
        "an owner approval for another scope must not permit real material")


def approval_with_status(record: dict, status: str) -> dict:
    return owner_approval(record["content_sha256"], status=status)


# --------------------------------------------------------------------------
# 3. The material gate and the guarded draw wrapper
# --------------------------------------------------------------------------
def check_material_gate() -> None:
    real = generator.stream_seed(1, 0, "sectors")
    require(str(generator.MASTER_SEED) in real.material_ascii
            and generator.PROTOCOL_PREFIX in real.material_ascii,
            "the frozen generator's material does not carry the real preregistered markers")
    require(r.seed_is_permitted_material(real.material_ascii) is False,
            "the real preregistered seed material must not be permitted")
    for purpose in generator.PURPOSES:
        for slot in (1, generator.SLOT_COUNT):
            seed = generator.stream_seed(slot, 0, purpose)
            require(r.seed_is_permitted_material(seed.material_ascii) is False,
                    f"real material permitted for slot {slot} {purpose}")
    for material, why in (
        ("", "empty material"),
        (None, "missing material"),
        (123, "non-string material"),
    ):
        require(r.seed_is_permitted_material(material) is False, f"permitted: {why}")
    # The fixture's own synthetic material IS permitted; that is what makes the
    # wrapper's success path reachable at all.  It carries no real marker.
    require(r.seed_is_permitted_material(synthetic_commitment(1, 0, "sectors").material_ascii) is True,
            "the fixture's own synthetic material is not permitted")
    # A material carrying exactly one marker, and nothing else.  Dropping that
    # marker from the gate would make this material look permitted, so this is
    # the fixture each marker removal has to break.
    for marker, why in (
        (str(generator.MASTER_SEED), "master seed only"),
        (generator.MASTER_SEED_HEX, "master seed hex only"),
        (generator.PROTOCOL_PREFIX, "prefix only"),
    ):
        require(marker != "", f"empty real-material marker for {why}")
        require(r.seed_is_permitted_material(marker) is False, f"permitted: {why}")


class RealMaterialGenerator:
    """A stand-in StreamSeed that carries the real preregistered material.

    Nothing is sampled.  The real material string is the one the frozen
    generator builds; this object only carries the fields the gate reads, so
    the refusal is exercised without any real draw.
    """

    def __init__(self, material: str, slot: int = 1, attempt: int = 0, purpose: str = "sectors"):
        self.slot = slot
        self.attempt = attempt
        self.purpose = purpose
        self.material_ascii = material


def synthetic_commitment(slot: int, attempt: int, purpose: str) -> generator.StreamSeed:
    """A StreamSeed whose material is unambiguously synthetic.

    The real material is produced by hashing the preregistered master seed and
    protocol prefix together, so a fixture cannot reach it without a real
    preregistered stream.  This seed is built from a separate, synthetic
    commitment prefix and never mixes the two.
    """
    material = f"synthetic/stage2-fixture/v1|slot={slot:02d}|attempt={attempt}|purpose={purpose}"
    digest = hashlib.sha256(material.encode("ascii")).digest()
    return generator.StreamSeed(
        slot=slot, attempt=attempt, purpose=purpose, material_ascii=material,
        material_sha256=digest.hex(),
        seed_uint128=int.from_bytes(digest[:16], "big", signed=False),
    )


class SyntheticScreen:
    """A screening attempt whose sector blocks come from a synthetic fixture RNG.

    Nothing preregistered is sampled.  The seed for the block draw is the
    fixture's own ``SYNTHETIC_DRAWN_SEED``; the stream name, purpose and
    material are the ones a real attempt would carry, which is what makes the
    material gate meaningful.
    """

    BLOCK_SEED = "0x5A1A7E"  # fixture-only, chosen here, not preregistered


def patched_generator(body, *, material: str | None = None):
    """Run ``body`` with a provably synthetic draw provider in place."""
    original_seed = generator.stream_seed
    original_blocks = generator.sector_blocks
    original_screen = generator.screen_attempt
    blocks_rng = np.random.Generator(np.random.PCG64(int(SyntheticScreen.BLOCK_SEED, 16)))
    permutation = tuple(int(value) for value in blocks_rng.permutation(generator.ASSET_COUNT))

    def fake_stream_seed(slot, attempt, purpose):
        # The frozen stream_seed's own range and purpose checks, so a stand-in
        # draw is refused for exactly the same malformed inputs a real one is.
        generator._int(slot, "slot", 1, generator.SLOT_COUNT)
        generator._int(attempt, "attempt", 0, generator.MAX_ATTEMPT)
        generator._require(type(purpose) is str and purpose in generator.PURPOSES,
                           "unknown stream purpose")
        if material is not None:
            return RealMaterialGenerator(material, slot, attempt, purpose)
        return synthetic_commitment(slot, attempt, purpose)

    def fake_sector_blocks(slot, attempt):
        return tuple(permutation[offset: offset + generator.SECTOR_SIZE]
                     for offset in range(0, generator.ASSET_COUNT, generator.SECTOR_SIZE))

    def fake_screen_attempt(**kwargs):
        if material is not None:
            # The stand-in draw refuses the real material itself, so the
            # wrapper's PRE-draw gate is the only thing that can refuse it:
            # if that gate is removed, this is reached and fails loudly.
            raise FixtureError("the real-material path reached the draw provider")
        blocks = fake_sector_blocks(kwargs["slot"], kwargs["attempt"])
        candidate = generator.normalized_partition(blocks)
        stage1 = generator.normalized_partition(kwargs["stage1_partition"])
        earlier = {generator.normalized_partition(p) for p in kwargs["earlier_accepted_partitions"]}
        feasible = generator.feasibility_count(kwargs["prices"], candidate, kwargs["K"],
                                               kwargs["C"], kwargs["B"])
        rejections = []
        if candidate == stage1:
            rejections.append("partition_matches_stage1")
        if candidate in earlier:
            rejections.append("partition_matches_earlier_accepted")
        if feasible < 100:
            rejections.append("feasible_set_below_100")
        return generator.AttemptScreen(
            slot=kwargs["slot"], attempt=kwargs["attempt"],
            returns_seed=synthetic_commitment(kwargs["slot"], kwargs["attempt"], "returns"),
            sectors_seed=synthetic_commitment(kwargs["slot"], kwargs["attempt"], "sectors"),
            sector_blocks=blocks, normalized_partition=candidate,
            partition_sha256=generator.partition_digest(candidate),
            feasible_count=feasible, rejection_codes=tuple(rejections))

    generator.stream_seed = fake_stream_seed
    generator.sector_blocks = fake_sector_blocks
    generator.screen_attempt = fake_screen_attempt
    try:
        return body()
    finally:
        generator.stream_seed = original_seed
        generator.sector_blocks = original_blocks
        generator.screen_attempt = original_screen


def check_draw_wrapper(actual: dict) -> None:
    """The guarded wrapper end to end, on provably synthetic draw material.

    The wrapper is required to reach the frozen pure draw API; a synthetic
    stand-in supplies a synthetic sector stream, so no preregistered stream is
    ever constructed.  That is the point: the guard calls and the material gate
    are proved by the wrapper actually working, so a mutation that deletes
    either one is observable.
    """
    record, pinned = actual["record"], actual["pinned"]
    approval = synthetic_approval(record)
    approval_kw = {"fixture_context": TOKEN}
    before = r.DRAW_CALL_COUNT

    receipt = patched_generator(lambda: r.draw_screened_attempt(
        record=record, expected_content_sha256=pinned, approval=approval,
        screening_inputs=INPUTS, slot=1, attempt=0, **approval_kw))
    require(receipt["material_permitted"] is True and receipt["real_material_authorized"] is False,
            "synthetic draw receipt overstates the material authority")
    # The receipt must not carry any key that claims the real preregistered seed
    # was drawn.  A key is a claim, so the exact key set is the check.
    require(set(receipt) == {"attempt", "slot", "material_permitted",
                             "real_material_authorized", "draw_calls", "evidence",
                             "statement", "screen"},
            f"synthetic draw receipt has an unexpected key set: {sorted(receipt)}")
    require(receipt["evidence"] == r._draw_evidence(record), "guarded draw evidence drift")
    require(set(receipt["evidence"]) == {"equality", "phases", "record_content_sha256",
                                        "record_status", "owner_approval",
                                        "authorizes_draw_or_write", "statement"},
            f"guarded draw evidence has an unexpected key set: {sorted(receipt['evidence'])}")
    require(receipt["draw_calls"] == before + 1, "the guarded draw did not run exactly one real draw call")
    require(receipt["evidence"] == r._draw_evidence(record), "guarded draw evidence drift")
    require(receipt["evidence"]["phases"] == "start_and_end"
            and receipt["evidence"]["record_content_sha256"] == pinned
            and receipt["evidence"]["authorizes_draw_or_write"] == "no"
            and receipt["evidence"]["owner_approval"] == "absent",
            "guarded draw evidence overstates authority or drifts")
    screen = receipt["screen"]
    require(screen.slot == 1 and screen.attempt == 0
            and screen.partition_sha256 == generator.partition_digest(screen.normalized_partition)
            and screen.sectors_seed.material_ascii == synthetic_commitment(1, 0, "sectors").material_ascii,
            "screened attempt drift")
    # The screen is exactly what the frozen pure API's own logic produces for
    # the same synthetic blocks and inputs.
    direct = patched_generator(lambda: generator.screen_attempt(
        prices=INPUTS.prices, K=INPUTS.K, C=INPUTS.C, B=INPUTS.B,
        stage1_partition=INPUTS.stage1_partition, earlier_accepted_partitions=(),
        slot=1, attempt=0))
    require(screen == direct, "the wrapper's screen differs from the frozen pure API's own logic")

    # The same synthetic approval off the fixture path refuses before the draw.
    refused(lambda: patched_generator(lambda: r.draw_screened_attempt(
        record=record, expected_content_sha256=pinned, approval=approval,
        screening_inputs=INPUTS, slot=1, attempt=0)), "synthetic draw off the fixture path", "synthetic")
    require(r.DRAW_CALL_COUNT == before + 1, "a refused approval still ran a draw")

    # A refused record (drifted pin) stops the draw before it happens.
    refused(lambda: patched_generator(lambda: r.draw_screened_attempt(
        record=reseal({**record, "sources": {**record["sources"],
                                             "planner": {"path": "research/g9/plan_stage2_generator.py",
                                                         "sha256": fake("drifted")}}}),
        expected_content_sha256=fake("drifted"),
        approval=owner_approval(fake("drifted")),
        screening_inputs=INPUTS, slot=1, attempt=0, **approval_kw)),
        "draw against a drifted record")
    require(r.DRAW_CALL_COUNT == before + 1, "a drifted record still ran a draw")

    # A malformed slot/attempt is refused by the generator and retyped.
    for slot, attempt in ((0, 0), (6, 0), (1, 128), ("1", 0), (1, True)):
        refused(lambda slot=slot, attempt=attempt: patched_generator(lambda: r.draw_screened_attempt(
            record=record, expected_content_sha256=pinned, approval=approval,
            screening_inputs=INPUTS, slot=slot, attempt=attempt, **approval_kw)),
            f"malformed slot/attempt ({slot!r}, {attempt!r})")


def check_no_drift_checks_dependency(actual: dict) -> None:
    """The before-draw and after-draw checks must reach a drifted capture.

    ``guard.capture_snapshot`` is replaced by a real capture with one field
    edited, so the fixture does not depend on how the wrapper fetches a
    snapshot, only on that it compares what it fetched.
    """
    record, pinned = actual["record"], actual["pinned"]
    approval = synthetic_approval(record)
    kw = {"fixture_context": TOKEN}

    def refused_capture(replacement, label: str) -> None:
        global COUNT
        original = guard.capture_snapshot
        guard.capture_snapshot = replacement
        try:
            patched_generator(lambda: r.draw_screened_attempt(
                record=record, expected_content_sha256=pinned, approval=approval,
                screening_inputs=INPUTS, slot=1, attempt=0, **kw))
        except r.GenerationReleaseError as exc:
            if label not in str(exc):
                raise FixtureError(f"{label}: refused for the wrong reason: {exc}") from exc
            COUNT += 1
            return
        finally:
            guard.capture_snapshot = original
        raise FixtureError(f"{label}: accepted a drifted capture")

    start = guard.capture_snapshot()
    version_drift = copy.deepcopy(start)
    version_drift["runtime"]["numpy"]["version"] = "0.0.0-drifted"
    # One capture for both phases, so the label is the "before-draw" one.
    refused_capture(lambda: version_drift, "before-draw snapshot differs")
    refused_capture(lambda: version_drift, "before-draw snapshot differs")

    # Now the healthy case with the same provider shape, and a provider whose
    # first capture is clean and whose second is drifted: the after-draw check
    # must be what refuses.
    def clean_then_drift():
        captures = [copy.deepcopy(start), version_drift]
        return lambda: captures.pop(0)

    refused_capture(clean_then_drift(), "after-draw snapshot differs")

    sources = copy.deepcopy(start)
    sources["sources"]["generator"]["sha256"] = fake("drifted-generator")
    refused_capture(lambda: sources, "before-draw snapshot differs")

    original = guard.capture_snapshot
    guard.capture_snapshot = lambda: copy.deepcopy(start)
    try:
        ok = patched_generator(lambda: r.draw_screened_attempt(
            record=record, expected_content_sha256=pinned, approval=approval,
            screening_inputs=INPUTS, slot=1, attempt=0, **kw))
    finally:
        guard.capture_snapshot = original
    require(ok["draw_calls"] > 0, "the healthy capture provider did not reach the draw")

    # A start and end that are the SAME object is refused, not silently passed.
    one = guard.capture_snapshot()
    refused(lambda: r._verify_after_draw(record, one, one),
            "one object as start and end", "separate captures")
    refused(lambda: r._verify_after_draw(record, one, version_drift),
            "after-draw drift against the record", "after-draw snapshot differs")
    refused(lambda: r._verify_before_draw(record, version_drift),
            "before-draw drift against the record", "before-draw snapshot differs")
    refused(lambda: r._verify_after_draw(record, one, "not a snapshot"),
            "malformed end capture", "wrong key set")
    refused(lambda: r._verify_before_draw(record, {"sources": {}}),
            "malformed start capture", "wrong key set")

    # The two drift windows of the wrapper, each reached with a capture
    # provider so the fixture does not depend on how the wrapper fetches a
    # snapshot, only on that it compares what it fetched.  In both cases the
    # record is the real capture, so whichever comparison fires, the refusal is
    # a genuine refusal.  There is no separate start-vs-end case: it would be
    # unreachable, because the after-draw comparison against the record fires
    # first whenever the end has drifted.
    env_drift = copy.deepcopy(start)
    env_drift["runtime"]["thread_and_dispatch_environment"] = dict(
        env_drift["runtime"]["thread_and_dispatch_environment"], OPENBLAS_NUM_THREADS="3")
    require(guard._differences(start, env_drift, "") != [], "the drift is not observable")
    # A provider whose first capture is the record and whose second capture has
    # drifted: the wrapper's after-draw check against the record must refuse.
    def clean_then_drifted():
        captures = [copy.deepcopy(start), env_drift]
        return lambda: captures.pop(0)

    original_capture = guard.capture_snapshot
    guard.capture_snapshot = clean_then_drifted()
    try:
        refused(lambda: patched_generator(lambda: r.draw_screened_attempt(
            record=record, expected_content_sha256=pinned, approval=approval,
            screening_inputs=INPUTS, slot=1, attempt=0, **kw)),
            "after-draw record drift through the wrapper", "after-draw snapshot differs")
    finally:
        guard.capture_snapshot = original_capture

    # A provider whose first capture has drifted and whose second is clean: the
    # before-draw check against the record must refuse.
    def drifted_then_clean():
        captures = [env_drift, copy.deepcopy(start)]
        return lambda: captures.pop(0)

    guard.capture_snapshot = drifted_then_clean()
    try:
        refused(lambda: patched_generator(lambda: r.draw_screened_attempt(
            record=record, expected_content_sha256=pinned, approval=approval,
            screening_inputs=INPUTS, slot=1, attempt=0, **kw)),
            "before-draw record drift through the wrapper", "before-draw snapshot differs")
    finally:
        guard.capture_snapshot = original_capture

    # The after-draw check's success path: two separate captures that both
    # equal the record.  A record pinned to a drifted runtime, with start and
    # end both matching it, exercises the check without the record comparison
    # hiding behind the clean one.
    drifted_record = copy.deepcopy(record)
    drifted_record["runtime"] = env_drift["runtime"]
    drifted_record = reseal(drifted_record)
    r._verify_after_draw(drifted_record, copy.deepcopy(env_drift), copy.deepcopy(env_drift))


def check_real_material_refused(actual: dict) -> None:
    """The real preregistered material is refused, end to end, before the draw.

    The draw provider is the fixture stand-in, with the real material string
    substituted for the synthetic one, so the refusal is exercised without
    constructing any preregistered stream.
    """
    record, pinned = actual["record"], actual["pinned"]
    real = generator.stream_seed(1, 0, "sectors").material_ascii
    stand_in = RealMaterialGenerator(real)
    before = r.DRAW_CALL_COUNT
    for label, approval, kw in (
        ("synthetic approval on the fixture path", synthetic_approval(record), {"fixture_context": TOKEN}),
        ("synthetic approval off the fixture path", synthetic_approval(record), {}),
    ):
        args = dict(record=record, expected_content_sha256=pinned, approval=approval,
                    screening_inputs=INPUTS, slot=1, attempt=0)
        args.update(kw)
        refused(lambda args=args: patched_generator(
            lambda: r.draw_screened_attempt(**args), material=real),
            f"real material with {label}")
    # Without an approval at all it is refused at the approval check, not later.
    refused(lambda: patched_generator(lambda: r.draw_screened_attempt(
        record=record, expected_content_sha256=pinned, approval=None,
        screening_inputs=INPUTS, slot=1, attempt=0, fixture_context=TOKEN), material=real),
        "real material with no approval", "approval must be an object")
    require(r.DRAW_CALL_COUNT == before,
            "the refused real-material path incremented the draw counter")
    # The gate itself, on the real material and its markers.
    refused(lambda: r._require_permitted_material(stand_in, real_material_authorized=False),
            "real material gate", "refusing to draw the real preregistered")
    require(r._require_permitted_material(stand_in, real_material_authorized=True) is None,
            "a real owner approval must be able to authorize the real material")
    for purpose in generator.PURPOSES:
        seed = generator.stream_seed(1, 0, purpose)
        refused(lambda seed=seed: r._require_permitted_material(seed, real_material_authorized=False),
                f"real material gate for {purpose}")


def check_no_write_or_authority_surface() -> None:
    source = (ROOT / r.RELEASE_MODULE_PATH).read_text(encoding="ascii")
    for forbidden in ("__main__", "argparse", "sys.argv", "open(\"w", "write_text", "write_bytes",
                      "os.rename", "os.replace", "shutil", "subprocess", "socket", "urllib", "kaggle",
                      "multivariate_normal", "sample_return_covariance", "json.dump"):
        require(forbidden not in source, f"release source contains forbidden token {forbidden!r}")
    require(not hasattr(r, "main"), "release module exposes a CLI")
    require(source.count("sys.path.insert") == 1,
            "the release module bootstraps sys.path an unexpected number of times")
    # The record must not depend on anything the environment can change, so the
    # module must not import os/environ at all and must not read an env var.
    require("import os" not in source and "os.environ" not in source
            and "getenv" not in source,
            "release module reads the environment")
    # The builder never reads an approval, and the approval check never renders
    # an approval.
    require("approval" not in inspect_signature(r.build_candidate_implementation_record),
            "the record builder takes an approval-like parameter")


def inspect_signature(fn) -> list:
    import inspect
    return list(inspect.signature(fn).parameters)


def pycache_count() -> int:
    return sum(1 for _ in (ROOT / "research").rglob("*.pyc"))


def main() -> int:
    before = pycache_count()
    check_record_shape()
    actual = check_actual_record()
    check_approval_check(actual["record"], actual["pinned"])
    check_material_gate()
    check_draw_wrapper(actual)
    check_no_drift_checks_dependency(actual)
    check_real_material_refused(actual)
    check_no_write_or_authority_surface()
    require(pycache_count() == before, "fixture wrote bytecode")
    require(not (ROOT / "research/g9/stage2_generation").exists(),
            "fixture must not create a generation artifact directory")
    record, pinned = actual["record"], actual["pinned"]
    print(f"optimize={sys.flags.optimize} checks={COUNT} draw_calls={r.DRAW_CALL_COUNT}")
    print(f"actual_record content_sha256={pinned} status={record['status']} "
          f"owner_approval={record['owner_approval']}")
    print(f"real_material_markers_refused={len(r.REAL_MATERIAL_MARKERS)} "
          f"fixture_scope={r.FIXTURE_APPROVAL_SCOPE}")
    print("PASS Stage-2 generation release fixtures; synthetic inputs and synthetic approvals only; "
          "real preregistered seed material refused; no owner draw approval, no real draw, no write")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

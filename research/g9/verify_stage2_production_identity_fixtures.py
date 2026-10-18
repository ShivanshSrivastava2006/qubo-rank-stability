#!/usr/bin/env python3
"""Offline WP1 production-identity fixtures; synthetic, read-only, no Kaggle.

Every synthetic role is built inside a ``tempfile.TemporaryDirectory``.  The one
role that is not synthetic is ``v1_engine``: it reads the 12 real §A files
read-only and hashes them against the accepted release.

There is deliberately NO ``assert`` in this file.  ``python3 -O`` strips
``assert`` statements, so an assert-based fixture would pass vacuously under
``-O``.  Every check raises instead, so the normal and ``-O`` runs are equally
strict.

This verifier builds and compares DRAFT identities.  It issues no identity,
authorizes nothing, and never runs a GPU, a Kaggle push, or any Stage-2
instance or scientific value.
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import sys
import shutil
import tempfile

if os.environ.get("PYTHONDONTWRITEBYTECODE") != "1":
    raise SystemExit("PYTHONDONTWRITEBYTECODE=1 is required")
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.g9 import stage2_production_identity as prod
from research.g9.cuda_qualification import stage2_cuda_execution_contract as contract


PASSED: list[str] = []


def require(condition: object, message: str) -> None:
    """Raising check, never `assert`: it must hold identically under -O."""
    if not condition:
        raise RuntimeError("FIXTURE FAILURE: " + message)


def refuses(function, *args, **kwargs) -> bool:
    """True iff `function` raised the module's typed refusal."""
    try:
        function(*args, **kwargs)
    except prod.ProductionIdentityError:
        return True
    return False


def refuses_with(function, needle, *args, **kwargs) -> bool:
    """True iff `function` refused with a message naming `needle`."""
    try:
        function(*args, **kwargs)
    except prod.ProductionIdentityError as exc:
        return needle in str(exc)
    return False


def _capture(function, *args, **kwargs) -> object:
    """Run `function` and return the typed refusal it raised, for message checks."""
    try:
        function(*args, **kwargs)
    except prod.ProductionIdentityError as exc:
        return exc
    raise RuntimeError("FIXTURE FAILURE: expected a refusal, none was raised")


def ok(label: str) -> None:
    PASSED.append(label)
    print("  ok: " + label)


def sha256_bytes(raw: bytes) -> str:
    import hashlib
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path: str) -> str:
    import hashlib
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def rewrite(tree: str, rel: str, data: bytes) -> None:
    """Overwrite one mirrored file inside the synthetic tree only."""
    with open(os.path.join(tree, rel), "wb") as handle:
        handle.write(data)


# --------------------------------------------------------------------------
# Fixed, synthetic inputs
# --------------------------------------------------------------------------

V1_REPO_ROOT = str(ROOT)

V1_PLATFORM = {
    "gpu_name": "Tesla T4",
    "compute_capability": "7.5",
    "cuda_driver_version": "13000",
    "cuda_runtime_version": "12080",
    "nvcc_version": "nvcc: NVIDIA (R) Cuda compiler driver, release 12.8, V12.8.93",
    "kaggle_image": "synthetic-image-placeholder-not-a-real-image",
    "python_version": "3.12.13",
    "numpy_version": "2.0.2",
}

V1_IMAGE_BUILD = {
    "kaggle_docker_image_platform_reported": "synthetic-image-placeholder [platform_reported]",
    "kaggle_saved_version_build_platform_reported": "synthetic-build-0 [platform_reported]",
    "kaggle_image_manifest_digest_platform_reported": "sha256:" + "0" * 64 + " [platform_reported]",
    "kaggle_image_config_digest_platform_reported": "sha256:" + "1" * 64 + " [platform_reported]",
    "kaggle_kernel_version_platform_reported": "synthetic-kernel-version-0 [platform_reported]",
    "runtime_build_observed_platform_reported": "synthetic-runtime-build-observed [platform_reported]",
    "kaggle_environment_pinning_platform_reported": "pinned [platform_reported]",
}

V1_FLAGS = ["-std=c++17", "-O0", "--fmad=false", "--ftz=false", "--prec-div=true",
            "--prec-sqrt=true", "-Xcompiler", "-O0,-ffp-contract=off,-fno-fast-math,-fPIC"]

#: Synthetic stand-ins for the not-yet-built bound files, one per role.
SYNTHETIC_ROLE_FILES = {
    "d013_plus_zero_cuda_path": ["research/g9/wp6b_synthetic/plus_zero_bridge.cu",
                                "research/g9/wp6b_synthetic/plus_zero_host.py"],
    "coordinate_iterator": ["research/g9/wp4_synthetic/coordinate_iterator.py"],
    "record_writer": ["research/g9/wp4_synthetic/record_writer.py"],
    "d016_reconstruction": ["research/g9/wp4_synthetic/d016_reconstruction.py"],
    "section_b1_recheck": ["research/g9/wp2_synthetic/section_b1_recheck.py"],
    "section_b2_harness": ["research/g9/wp3_synthetic/section_b2_harness.py"],
    "generation_binding": ["research/g9/wp5_synthetic/generation_binding.py"],
    "per_instance_preparation": ["research/g9/wp5b_synthetic/per_instance_preparation.py"],
}


def v1_role_paths() -> list[str]:
    """The real 12 §A paths, read-only, taken from the accepted release file."""
    release = prod.load_v1_release(V1_REPO_ROOT)
    return sorted(release["source_sha256"])


def make_synthetic_tree(directory: str) -> None:
    """Build the synthetic mirror tree.

    Two things live in it: the synthetic stand-ins for every not-yet-built
    role, and byte-identical READ-ONLY COPIES of the 12 real §A files and the
    release file, so the fixtures can alter a bound file without ever writing
    to the real repository.  Every copy is verified byte-equal to the original.
    """
    for paths in SYNTHETIC_ROLE_FILES.values():
        for path in paths:
            full = os.path.join(directory, path)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w", encoding="utf-8") as handle:
                handle.write("# synthetic WP1 fixture stand-in\n" + path + "\n")
    for rel in [prod.V1_RELEASE_REL] + v1_role_paths():
        source = os.path.join(V1_REPO_ROOT, rel)
        target = os.path.join(directory, rel)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(source, "rb") as src, open(target, "wb") as dst:
            raw = src.read()
            dst.write(raw)
        require(sha256_file(target) == sha256_file(source),
                f"the mirrored §A file {rel!r} is not byte-identical to the real one")


def synthetic_role_paths() -> dict[str, list[str]]:
    roles: dict[str, list[str]] = {prod.V1_ENGINE_ROLE: v1_role_paths()}
    roles.update(copy.deepcopy(SYNTHETIC_ROLE_FILES))
    return roles


def full_identity(tree: str, *, role_paths: dict | None = None,
                  platform: dict | None = None, image_build: dict | None = None,
                  flags: list | None = None, repo_root: str | None = None) -> dict:
    return prod.build_production_identity(
        repo_root=repo_root if repo_root is not None else tree,
        role_paths=role_paths if role_paths is not None else synthetic_role_paths(),
        platform=platform if platform is not None else dict(V1_PLATFORM),
        image_build=image_build if image_build is not None else dict(V1_IMAGE_BUILD),
        compiler_flags=flags if flags is not None else list(V1_FLAGS),
    )


# --------------------------------------------------------------------------
# 0. The module's own self-description is not vacuous
# --------------------------------------------------------------------------

def test_role_table_is_the_decided_scope() -> None:
    require(set(prod.ROLE_TABLE) == set(SYNTHETIC_ROLE_FILES) | {prod.V1_ENGINE_ROLE},
            "ROLE_TABLE does not match the owner-decided role set")
    require(len(prod.ROLES) == 9, "expected 9 production roles")
    require(prod.NOT_YET_BUILT_ROLES == set(SYNTHETIC_ROLE_FILES),
            "NOT_YET_BUILT_ROLES does not match the unbuilt roles")
    for role, description in prod.ROLE_TABLE.items():
        require(isinstance(description, str) and description.strip(),
                f"role {role!r} has no description")
    require(set(prod.NUMERICAL_PLATFORM_FIELDS) == set(contract.IDENTITY_PLATFORM_KEYS),
            "numerical platform fields diverge from the frozen contract's keys")
    require("kaggle_environment_pinning_platform_reported" in prod.IMAGE_BUILD_FIELDS,
            "the environment-pin field is missing from the image/build table")
    ok("role table is the owner-decided 9-role scope and matches the frozen contract keys")


def test_pinned_constants_are_fixed_values() -> None:
    """The pinned constants, spelled out INDEPENDENTLY of the module.

    Each of these is used both to BUILD a payload and to VALIDATE one, so
    changing it is invisible to the round-1 fixtures: the builder and the
    validator move together.  These literals are the fixture's own copy of the
    decided values, so a change to the module's constant is caught here.  The
    literal values are themselves asserted: the authorization note must say the
    payload is a draft, is not a qualification, not an approval and not an
    authorization, and is issued only after the WP7 dry run and owner
    acceptance -- a note claiming otherwise is not an acceptable pin.
    """
    require(prod.DRAFT_STATUS == "DRAFT_UNQUALIFIED",
            f"DRAFT_STATUS is {prod.DRAFT_STATUS!r}, not the decided DRAFT_UNQUALIFIED")
    require(prod.NO_AUTHORIZATION == "NONE",
            f"NO_AUTHORIZATION is {prod.NO_AUTHORIZATION!r}, not NONE")
    require(prod.SOURCE_MAP_SCHEMA
            == "decisions_os/g9_stage2_production_source_map/draft_v1",
            f"SOURCE_MAP_SCHEMA is {prod.SOURCE_MAP_SCHEMA!r}, not the decided draft_v1")
    require(prod.PRODUCTION_IDENTITY_SCHEMA
            == "decisions_os/g9_stage2_production_qualification_identity/draft_v1",
            "PRODUCTION_IDENTITY_SCHEMA is not the decided draft_v1")
    require(prod.HASH_ALGORITHM == "sha256",
            f"HASH_ALGORITHM is {prod.HASH_ALGORITHM!r}, not sha256")
    require(prod.PLATFORM_REPORTED_LABEL == "platform_reported",
            "PLATFORM_REPORTED_LABEL is not the decided platform_reported")

    # The authorization note: the CONTENT is the point, so the words are
    # asserted, not just the identity of the string with itself.
    note = prod.AUTHORIZATION_NOTE
    require(isinstance(note, str) and note.strip() == note and note,
            "AUTHORIZATION_NOTE is not a non-empty stripped string")
    for phrase in ("DRAFT schema instance", "not a qualification",
                   "not an approval", "not an authorization",
                   "WP7", "owner acceptance"):
        require(phrase in note,
                f"AUTHORIZATION_NOTE no longer says {phrase!r}: {note!r}")
    for forbidden in ("qualified", "approved", "authorized", "granted"):
        require(f"is {forbidden}" not in note,
                f"AUTHORIZATION_NOTE now claims the payload {forbidden!r}: {note!r}")

    # The platform-reported statement: it must deny measurement and deny proof.
    statement = prod.PLATFORM_REPORTED_STATEMENT
    require(isinstance(statement, str) and statement.strip() == statement and statement,
            "PLATFORM_REPORTED_STATEMENT is not a non-empty stripped string")
    for phrase in ("PLATFORM-REPORTED", "not independently measured",
                   "not proof", "forces requalification"):
        require(phrase in statement,
                f"PLATFORM_REPORTED_STATEMENT no longer says {phrase!r}: {statement!r}")
    for forbidden in ("independently verified", "independently attested", "are proof"):
        require(forbidden not in statement,
                f"PLATFORM_REPORTED_STATEMENT now claims {forbidden!r}: {statement!r}")
    # "not proof of the executing image" is the required denial, so a statement
    # that dropped the negation must be caught: "proof of" may appear only as
    # part of that denial.
    require("not proof of the executing image" in statement,
            "the statement no longer denies proof of the executing image")
    ok("every pinned constant is the decided fixed value, and each says what it must")


def test_mismatch_subclass_carries_named_fields() -> None:
    exc = prod.ProductionIdentityMismatch(("a", "b"))
    require(exc.differing_fields == ("a", "b"), "mismatch lost its differing-field list")
    require("a, b" in str(exc), "mismatch message does not name the differing fields")
    require(isinstance(exc, prod.ProductionIdentityError), "mismatch is not a typed refusal")
    ok("mismatch refusal carries the named differing fields")


# --------------------------------------------------------------------------
# 1. The happy path, and the DRAFT status
# --------------------------------------------------------------------------

def test_full_identity_builds_and_validates() -> None:
    with tempfile.TemporaryDirectory() as tree:
        make_synthetic_tree(tree)
        identity = full_identity(tree)
        require(prod.validate_production_identity(identity) == identity["content_sha256"],
                "the composed identity does not validate against its own content hash")
        require(identity["status"] == "DRAFT_UNQUALIFIED" and identity["authorization"] == "NONE",
                "a draft identity must not claim status or authorization")
        inner = identity["qualification_identity"]
        require(inner["schema"] == contract.QUALIFICATION_SCHEMA,
                "the frozen contract did not compose the numerical payload")
        require(contract.validate_qualification_identity(inner) == inner["content_sha256"],
                "the frozen contract rejects the embedded numerical payload")
        require(set(inner["platform"]) == set(contract.IDENTITY_PLATFORM_KEYS),
                "the numerical platform is not the frozen contract's key set")
        require(inner["source_sha256"] == {
            entry["path"]: entry["sha256"]
            for entries in identity["source_map"]["roles"].values() for entry in entries},
            "the frozen payload's source hashes do not equal the hashed source map")
        require(identity["content_sha256"] == contract.content_sha256({
            k: v for k, v in identity.items() if k != "content_sha256"}),
            "the outer content hash is not the frozen contract's content hash")
        evidence = identity["image_build_evidence"]
        require(evidence["is_proof"] is False and evidence["evidence_kind"] == "platform_reported",
                "image/build evidence is not marked platform-reported and not proof")
        require("PLATFORM-REPORTED" in evidence["statement"] and "not proof" in evidence["statement"],
                "the image/build statement does not say platform-reported and not proof")
        for key, value in evidence["fields"].items():
            require(key.endswith("_platform_reported") and value.endswith(" [platform_reported]"),
                    f"image/build field {key!r} lost its platform-reported label")
        require(identity["source_map"]["not_yet_built_roles"] == sorted(SYNTHETIC_ROLE_FILES),
                "the source map does not record which roles are not yet built")
        ok("a full synthetic role map builds a validating DRAFT identity")

        result = prod.exact_match(copy.deepcopy(identity), copy.deepcopy(identity))
        require(result["verdict"] == "exact_match" and result["differing_fields"] == [],
                "exact_match did not accept an identity against itself")
        ok("exact_match accepts an unchanged session identity")


# --------------------------------------------------------------------------
# 2. Refusals of the role table (item 1 of the brief)
# --------------------------------------------------------------------------

def test_source_map_refusals(tree: str) -> None:
    base = synthetic_role_paths()

    missing_role = copy.deepcopy(base)
    del missing_role["record_writer"]
    require(refuses_with(prod.build_source_map, "missing role", tree, missing_role),
            "a missing role was not refused")
    require(refuses_with(prod.build_source_map, "record_writer", tree, missing_role),
            "the refusal did not name the missing role")
    ok("refuses a missing role and names it")

    unknown = copy.deepcopy(base)
    unknown["not_a_role"] = ["research/g9/wp4_synthetic/coordinate_iterator.py"]
    require(refuses_with(prod.build_source_map, "unknown role", tree, unknown),
            "an unknown role was not refused")
    ok("refuses an unknown role and names it")

    empty = copy.deepcopy(base)
    empty["record_writer"] = []
    require(refuses_with(prod.build_source_map, "empty", tree, empty),
            "an empty role was not refused")
    require(refuses_with(prod.build_source_map, "record_writer", tree, empty),
            "the empty-role refusal did not name the role")
    ok("refuses an empty role and names it")

    not_a_list = copy.deepcopy(base)
    not_a_list["record_writer"] = "research/g9/wp4_synthetic/record_writer.py"
    require(refuses_with(prod.build_source_map, "non-string sequence", tree, not_a_list),
            "a string role value was not refused")
    ok("refuses a role bound to a bare string instead of a sequence")

    duplicated = copy.deepcopy(base)
    duplicated["record_writer"] = duplicated["d016_reconstruction"]
    require(refuses_with(prod.build_source_map, "more than one role", tree, duplicated),
            "a duplicate path across roles was not refused")
    require(refuses_with(prod.build_source_map, "record_writer", tree, duplicated),
            "the duplicate refusal did not name a role")
    ok("refuses a duplicate path bound by two roles")

    within_role = copy.deepcopy(base)
    within_role["record_writer"] = ["research/g9/wp4_synthetic/record_writer.py"] * 2
    require(refuses_with(prod.build_source_map, "repeats a path", tree, within_role),
            "a path repeated inside one role was not refused")
    ok("refuses a path repeated inside a single role")

    for label, bad_path in (
            ("absolute", "/etc/passwd"),
            ("traversing", "research/g9/../research/g9/wp4_synthetic/record_writer.py"),
            ("escaping", "../outside.py"),
            ("escaping", "research/g9/../../outside.py"),
            ("escaping", "research/g9/wp4_synthetic/../../../../outside.py"),
    ):
        escaped = copy.deepcopy(base)
        escaped["record_writer"] = [bad_path]
        require(refuses_with(prod.build_source_map, "role 'record_writer'", tree, escaped),
                f"{label} path {bad_path!r} was not refused for the role")
    ok("refuses absolute, traversing and escaping paths")

    for bad_path in ("research/g9/wp4_synthetic/absent.py",
                     "research/g9/wp4_synthetic/nested/deeper/absent.py"):
        absent = copy.deepcopy(base)
        absent["record_writer"] = [bad_path]
        require(refuses_with(prod.build_source_map, "not an existing regular file", tree, absent),
                f"a missing file {bad_path!r} was not refused as unreadable")
    ok("refuses an unreadable / non-existent file")

    as_dict = copy.deepcopy(base)
    as_dict["record_writer"] = {"path": "research/g9/wp4_synthetic/record_writer.py"}
    require(refuses_with(prod.build_source_map, "non-string sequence", tree, as_dict),
            "a mapping role value was not refused")
    ok("refuses a role bound to a mapping instead of a sequence")

    non_string = copy.deepcopy(base)
    non_string["record_writer"] = [7]
    require(refuses_with(prod.build_source_map, "non-string path entry", tree, non_string),
            "a non-string path entry was not refused")
    ok("refuses a non-string path entry")

    whitespace = copy.deepcopy(base)
    whitespace["record_writer"] = [" research/g9/wp4_synthetic/record_writer.py"]
    require(refuses_with(prod.build_source_map, "surrounding whitespace", tree, whitespace),
            "a whitespace-padded path was not refused")
    ok("refuses a whitespace-padded path")

    backslash = copy.deepcopy(base)
    backslash["record_writer"] = ["research\\g9\\wp4_synthetic\\record_writer.py"]
    require(refuses_with(prod.build_source_map, "backslash", tree, backslash),
            "a backslash path was not refused")
    ok("refuses a non-POSIX backslash path")

    colon = copy.deepcopy(base)
    colon["record_writer"] = ["research/g9/wp4_synthetic/record:writer.py"]
    require(refuses_with(prod.build_source_map, "colon", tree, colon),
            "a colon-bearing path was not refused")
    ok("refuses a colon-bearing path")

    # A path with no traversing component that is a SYMLINK out of the tree:
    # this is the only way to reach the escape check, so it must be reached.
    outside_dir = tempfile.mkdtemp(prefix="wp1-outside-")
    outside_file = os.path.join(outside_dir, "escaped_writer.py")
    with open(outside_file, "w", encoding="utf-8") as handle:
        handle.write("# outside the repository root\n")
    link_rel = "research/g9/wp4_synthetic/linked_writer.py"
    link_full = os.path.join(tree, link_rel)
    os.symlink(outside_file, link_full)
    linked = copy.deepcopy(base)
    linked["record_writer"] = [link_rel]
    require(refuses_with(prod.build_source_map, "escapes the repository root", tree, linked),
            "a symlink out of the repository root was not refused")
    os.remove(link_full)
    os.remove(outside_file)
    os.rmdir(outside_dir)
    ok("refuses a symlink that escapes the repository root")

    not_source = copy.deepcopy(base)
    not_source["record_writer"] = ["research/g9/wp4_synthetic/record_writer.txt"]
    full = os.path.join(tree, not_source["record_writer"][0])
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as handle:
        handle.write("x")
    require(refuses_with(prod.build_source_map, "neither a .py nor a .cu", tree, not_source),
            "a non-source extension was not refused")
    os.remove(full)
    ok("refuses a bound path that is not a .py/.cu source file")

    dotted = copy.deepcopy(base)
    dotted["record_writer"] = ["./research/g9/wp4_synthetic/record_writer.py"]
    require(refuses_with(prod.build_source_map, "traversing component", tree, dotted),
            "a '.'-prefixed path was not refused")
    doubled = copy.deepcopy(base)
    doubled["record_writer"] = ["research/g9//wp4_synthetic/record_writer.py"]
    require(refuses_with(prod.build_source_map, "traversing component", tree, doubled),
            "a doubled-separator path was not refused")
    for bad, needle in (("./research/g9/wp4_synthetic/record_writer.py", "traversing component"),
                        ("research/g9//wp4_synthetic/record_writer.py", "traversing component"),
                        ("research/g9/wp4_synthetic/../wp4_synthetic/record_writer.py", "traversing component"),
                        ("research/g9/wp4_synthetic/record_writer.py/", "neither a .py nor a .cu"),
                        ("//research/g9/wp4_synthetic/record_writer.py", "absolute")):
        candidate = copy.deepcopy(base)
        candidate["record_writer"] = [bad]
        require(refuses_with(prod.build_source_map, needle, tree, candidate),
                f"an unnormalized path {bad!r} was not refused")
    ok("refuses unnormalized, traversing and absolute paths")

    empty_role_map = {}
    require(refuses_with(prod.build_source_map, "non-empty mapping", tree, empty_role_map),
            "an empty role map was not refused")
    empty_root = copy.deepcopy(base)
    require(refuses_with(prod.build_source_map, "non-empty string", "", empty_root),
            "an empty repo_root was not refused")
    ok("refuses an empty role map and an empty repo root")

    # A role that binds more than one distinct file is legitimate: the
    # d013_plus_zero_cuda_path role already binds two, and the build below
    # proves a multi-file role is accepted and hashed.
    extra_file = "research/g9/wp4_synthetic/second_writer.py"
    with open(os.path.join(tree, extra_file), "w", encoding="utf-8") as handle:
        handle.write("# synthetic second writer\n")
    two_files = copy.deepcopy(base)
    two_files["record_writer"] = list(two_files["record_writer"]) + [extra_file]
    source_map = prod.build_source_map(tree, two_files)
    require([entry["path"] for entry in source_map["roles"]["record_writer"]] ==
            sorted(two_files["record_writer"]),
            "a multi-file role was not preserved in sorted order")
    require(all(len(entries) >= 1 for entries in source_map["roles"].values()),
            "a role lost its entries in a multi-file build")
    require(source_map["bound_file_count"] ==
            sum(len(entries) for entries in source_map["roles"].values()),
            "bound_file_count does not count the multi-file role's files")
    require(prod.validate_source_map_shape(source_map) is None,
            "a legitimate multi-file source map failed its own shape validation")
    os.remove(os.path.join(tree, extra_file))
    ok("accepts a role with more than one distinct file and hashes each one")


# --------------------------------------------------------------------------
# 3. Refusals of the v1 role (release pin, file set, tampered hash)
# --------------------------------------------------------------------------

def test_v1_role_refusals() -> None:
    base = synthetic_role_paths()
    release = prod.load_v1_release(V1_REPO_ROOT)

    require(set(prod.ROLES) == set(base), "role set drift inside the v1 fixtures")

    with open(os.path.join(V1_REPO_ROOT, prod.V1_RELEASE_REL), "rb") as handle:
        raw = handle.read()
    require(sha256_bytes(raw) == prod.V1_RELEASE_SHA256, "the v1 release file is not the accepted one")
    require(release["schema"] == "decisions_os/g9_cuda_core_corruption_qualification_release/v1" and
            release["status"] == "approved",
            "the v1 release is not the approved corruption-qualification release")
    require(len(release["source_sha256"]) == prod.V1_ENGINE_FILE_COUNT,
            "the v1 release does not hold 12 entries")
    ok("the accepted §A release file hash and schema are verified read-only")

    # Every case below runs against a synthetic mirror tree, never the real
    # repository.  `build_source_map` needs the whole role map to resolve, so
    # the tree must carry the synthetic roles as well as the 12 §A copies.
    with tempfile.TemporaryDirectory() as tree:
        make_synthetic_tree(tree)

        # A role map whose v1 role is short by one file.
        short = copy.deepcopy(base)
        short[prod.V1_ENGINE_ROLE] = base[prod.V1_ENGINE_ROLE][:-1]
        require(refuses_with(prod.build_source_map, "exactly 12 files", tree, short),
                "a v1 role with 11 files was not refused")
        require(refuses_with(prod.build_source_map, "v1_engine", tree, short),
                "the short v1 role refusal did not name the role")
        ok("refuses a v1 role that is not exactly the 12 accepted files")

        # A 12-file v1 role that drops one accepted file and adds a readable
        # non-v1 source: same count, wrong set.
        replacement = "research/g9/wp4_synthetic/second_writer.py"
        with open(os.path.join(tree, replacement), "w", encoding="utf-8") as handle:
            handle.write("# synthetic substitute for a v1 file\n")
        substitution: dict[str, list[str]] = copy.deepcopy(base)
        dropped = sorted(entry for entry in base[prod.V1_ENGINE_ROLE]
                         if entry != base[prod.V1_ENGINE_ROLE][0])
        substitution[prod.V1_ENGINE_ROLE] = sorted(dropped + [replacement])
        require(len(substitution[prod.V1_ENGINE_ROLE]) == prod.V1_ENGINE_FILE_COUNT,
                "the substitution fixture must keep 12 files in the v1 role")
        require(refuses_with(prod.build_source_map, "does not bind exactly the accepted", tree, substitution),
                "a v1 role with a substituted file was not refused")
        ok("refuses a v1 role whose file set differs from the accepted release")
        os.remove(os.path.join(tree, replacement))

        # The release file itself tampered: the 12 hashes still match, so only
        # the release-file pin can catch this.
        with open(os.path.join(tree, prod.V1_RELEASE_REL), "w", encoding="utf-8") as handle:
            tampered_release = dict(release)
            tampered_release["plan_content_sha256"] = "0" * 64
            json.dump(tampered_release, handle, sort_keys=True, separators=(",", ":"))
        require(refuses_with(prod.build_source_map, "is not the accepted release", tree, base),
                "a tampered v1 release file was not refused")
        require(refuses_with(prod.build_source_map, prod.V1_RELEASE_SHA256, tree, base),
                "the tampered-release refusal did not name the accepted release hash")
        require(refuses_with(prod.load_v1_release, "is not the accepted release", tree),
                "load_v1_release did not refuse the tampered release on its own")
        ok("refuses a tampered §A release file even though all 12 file hashes match")

        # Restore the release, then alter one bound v1 file by one byte: the
        # role's hash no longer matches, while the release file is untouched.
        make_synthetic_tree(tree)
        target = base[prod.V1_ENGINE_ROLE][0]
        with open(os.path.join(V1_REPO_ROOT, target), "rb") as handle:
            original = handle.read()
        rewrite(tree, target, original + b"x")
        require(refuses_with(prod.build_source_map, "hash mismatch against the accepted", tree, base),
                "a v1 file whose bytes differ from the release was not refused")
        require(refuses_with(prod.build_source_map, target, tree, base),
                "the hash-mismatch refusal did not name the altered file")
        ok("refuses a v1 file whose bytes no longer match the accepted release hash")

        # With the file restored, the same role map is accepted, so the refusal
        # above came from the byte and not from the role map.
        make_synthetic_tree(tree)
        require(not refuses(prod.build_source_map, tree, base),
                "the restored synthetic tree was not accepted")
        source_map = prod.build_source_map(tree, base)
        require(source_map["roles"][prod.V1_ENGINE_ROLE] ==
                [{"path": entry, "sha256": release["source_sha256"][entry]}
                 for entry in base[prod.V1_ENGINE_ROLE]],
                "the accepted v1 role does not carry the release's own hashes")
        require(source_map["v1_engine_release_sha256"] == prod.V1_RELEASE_SHA256,
                "the source map lost the accepted release anchor")
        ok("the unaltered v1 role carries exactly the accepted release hashes")

        # The real repository, read-only, must still verify: this is the only
        # place the fixtures touch the real 12 files.  A source map needs every
        # role bound, so the eight unbuilt roles are given eight distinct REAL
        # readable .py files at the real root; only the v1 role's hashes are
        # asserted against the release.
        v1_paths = set(base[prod.V1_ENGINE_ROLE])
        filler = [rel for rel in sorted(
            "research/g9/" + name for name in os.listdir(os.path.join(V1_REPO_ROOT, "research", "g9"))
        ) if rel.endswith(".py") and rel not in v1_paths
           and os.path.isfile(os.path.join(V1_REPO_ROOT, rel))]
        require(len(filler) >= len(prod.NOT_YET_BUILT_ROLES),
                "the real repository does not have enough readable .py files to fill the roles")
        real_roles = {role: [filler[index]] for index, role in enumerate(sorted(prod.NOT_YET_BUILT_ROLES))}
        real_roles[prod.V1_ENGINE_ROLE] = list(base[prod.V1_ENGINE_ROLE])
        real_source_map = prod.build_source_map(V1_REPO_ROOT, real_roles)
        require(real_source_map["roles"][prod.V1_ENGINE_ROLE] ==
                [{"path": entry, "sha256": release["source_sha256"][entry]}
                 for entry in base[prod.V1_ENGINE_ROLE]],
                "the real §A files do not hash to the accepted release values")
        ok("the real 12 §A files still match the accepted release, read-only")

        # A repo root with no release file at all.
        os.remove(os.path.join(tree, prod.V1_RELEASE_REL))
        require(refuses_with(prod.build_source_map, "unreadable", tree, base),
                "a missing §A release file was not refused as unreadable")
    ok("refuses when the §A release file is absent")


# --------------------------------------------------------------------------
# 4. Platform and image/build refusals (item 2 of the brief)
# --------------------------------------------------------------------------

def test_platform_refusals() -> None:
    require(refuses_with(prod.validate_numerical_platform, "keys mismatch",
                         {k: v for k, v in V1_PLATFORM.items() if k != "gpu_name"}),
            "a missing platform field was not refused")
    require(refuses_with(prod.validate_numerical_platform, "keys mismatch",
                         dict(V1_PLATFORM, extra="x")),
            "an extra platform field was not refused")
    for key in sorted(V1_PLATFORM):
        empty = dict(V1_PLATFORM)
        empty[key] = ""
        require(refuses_with(prod.validate_numerical_platform, "non-empty", empty),
                f"an empty platform value for {key!r} was not refused")
        padded = dict(V1_PLATFORM)
        padded[key] = " " + V1_PLATFORM[key]
        require(refuses_with(prod.validate_numerical_platform, "non-empty", empty if key == key else padded),
                f"a whitespace-padded platform value for {key!r} was not refused")
    ok("refuses missing, extra, empty and padded platform fields")

    for forbidden in ("device_uuid", "session_id", "device_uuid_hex", "pci_bus_id", "uuid", "bus_id"):
        require(refuses_with(prod.validate_numerical_platform, "forbidden",
                             dict(V1_PLATFORM, **{forbidden: "transient"})),
                f"platform field {forbidden!r} was not refused")
        require(refuses_with(prod.validate_numerical_platform, forbidden,
                             dict(V1_PLATFORM, **{forbidden: "transient"})),
                f"the refusal for {forbidden!r} did not name the field")
    # Every documented transient name is actually refused, and so is a name that
    # merely CONTAINS one of the needles, which is the case-folded substring
    # rule doing its job.
    for name in sorted(prod.FORBIDDEN_IDENTITY_FIELDS):
        require(refuses_with(prod.validate_numerical_platform, "forbidden",
                             dict(V1_PLATFORM, **{name: "transient"})),
                f"the documented transient field {name!r} is not refused")
    for name in ("DEVICE_UUID", "x_device_uuid_hex", "run_session_id_2",
                 "the_pci_bus_id", "some_bus_id"):
        require(refuses_with(prod.validate_numerical_platform, "forbidden",
                             dict(V1_PLATFORM, **{name: "transient"})),
                f"a key merely containing a transient needle ({name!r}) was not refused")
    ok("refuses device UUID and session ID supplied in the platform map")

    require(refuses_with(prod.validate_numerical_platform, "forbidden",
                         {"gpu_name": "Tesla T4", "device_UUID": "x", "compute_capability": "7.5",
                          "cuda_driver_version": "13000", "cuda_runtime_version": "12080",
                          "nvcc_version": "12.8", "kaggle_image": "img", "python_version": "3.12.13",
                          "numpy_version": "2.0.2"}),
            "a case-shifted device UUID key was not refused")
    ok("refuses a case-shifted device UUID key")

    numeric = dict(V1_PLATFORM)
    numeric["compute_capability"] = 7.5
    require(refuses_with(prod.validate_numerical_platform, "non-string control leaf", numeric),
            "a float platform value was not refused")
    # A bool is an int subclass in Python, so the int branch is what refuses it.
    # `7.5` above cannot be confused with `True`; these two make that explicit.
    for value, label in ((True, "True"), (False, "False")):
        bool_platform = dict(V1_PLATFORM)
        bool_platform["python_version"] = value
        require(refuses_with(prod.validate_numerical_platform, "integer or bool", bool_platform),
                f"a bool platform value ({label}) was not refused")
    int_platform = dict(V1_PLATFORM)
    int_platform["compute_capability"] = 7
    require(refuses_with(prod.validate_numerical_platform, "integer or bool", int_platform),
            "an int platform value was not refused")
    none_platform = dict(V1_PLATFORM)
    none_platform["numpy_version"] = None
    require(refuses_with(prod.validate_numerical_platform, "non-string control leaf", none_platform),
            "a None platform value was not refused")
    # A nested container is recursed into, so a leaf deep inside is refused by
    # the leaf check itself.  The container arrives under an EXTRA key, which
    # the key-set check would refuse on its own, so the leaf message proves the
    # recursion ran first.
    nested = dict(V1_PLATFORM)
    nested["extra"] = {"deeper": [1, 2, 3]}
    require(refuses_with(prod.validate_numerical_platform, "integer or bool", nested),
            "a nested integer leaf was not refused by the recursive leaf check")
    require(refuses_with(prod.validate_numerical_platform, "must be a mapping", "not-a-mapping"),
            "a non-mapping platform was not refused")
    require(refuses_with(prod.validate_numerical_platform, "must be a mapping", ["not", "a", "mapping"]),
            "a sequence platform was not refused")
    require(refuses_with(prod.validate_image_build_fields, "must be a mapping", 7),
            "a non-mapping image/build map was not refused")
    ok("refuses non-string control leaves in the platform map")

    require(refuses_with(prod.validate_image_build_fields, "keys mismatch",
                         {k: v for k, v in V1_IMAGE_BUILD.items() if k != "kaggle_image_manifest_digest_platform_reported"}),
            "a missing image/build field was not refused")
    require(refuses_with(prod.validate_image_build_fields, "keys mismatch",
                         dict(V1_IMAGE_BUILD, extra_platform_reported="x [platform_reported]")),
            "an extra image/build field was not refused")
    ok("refuses missing and extra image/build fields")

    relabelled = dict(V1_IMAGE_BUILD)
    relabelled["kaggle_image_manifest_digest_platform_reported"] = "sha256:" + "0" * 64
    require(refuses_with(prod.validate_image_build_fields, "does not carry", relabelled),
            "an image value without the platform-reported marker was not refused")
    relabelled = dict(V1_IMAGE_BUILD)
    relabelled["kaggle_image_manifest_digest_platform_reported"] = "sha256:" + "0" * 64 + " [verified_proof]"
    require(refuses_with(prod.validate_image_build_fields, "does not carry", relabelled),
            "an image value labelled as proof was not refused")
    ok("refuses an image value that drops or upgrades the platform-reported label")

    for key in sorted(V1_IMAGE_BUILD):
        blank = dict(V1_IMAGE_BUILD)
        blank[key] = ""
        require(refuses_with(prod.validate_image_build_fields, "non-empty", blank),
                f"an empty image/build value for {key!r} was not refused")
    ok("refuses empty image/build values")

    for forbidden in ("device_uuid", "session_id", "device_uuid_hex", "pci_bus_id", "uuid", "bus_id"):
        require(refuses_with(prod.validate_image_build_fields, "forbidden",
                             dict(V1_IMAGE_BUILD, **{forbidden: "transient"})),
                f"a forbidden image/build key {forbidden!r} was not refused")
        require(refuses_with(prod.validate_image_build_fields, forbidden,
                             dict(V1_IMAGE_BUILD, **{forbidden: "transient"})),
                f"the image/build refusal for {forbidden!r} did not name the field")
    require(refuses_with(prod.validate_image_build_fields, "forbidden",
                         dict(V1_IMAGE_BUILD, DEVICE_UUID="transient")),
            "a case-shifted forbidden image/build key was not refused")
    ok("refuses device UUID and session ID supplied in the image/build map")


def test_image_build_evidence_labels(tree: str) -> None:
    evidence = prod.image_and_build_evidence(V1_PLATFORM, V1_IMAGE_BUILD)
    require(evidence["evidence_kind"] == "platform_reported" and evidence["is_proof"] is False,
            "the evidence block is not labelled platform-reported / not-proof")
    require(evidence["kaggle_image_reported_string"] == V1_PLATFORM["kaggle_image"],
            "the evidence block lost the reported kaggle_image")
    require("not proof" in evidence["statement"],
            "the evidence statement does not deny proof")

    # A real identity whose evidence block claims proof must be refused, and so
    # must one whose statement drops the platform-reported wording or whose
    # evidence_kind is relabelled.
    accepted = full_identity(tree)
    for label, mutate, needle in (
            ("is_proof", lambda e: e.__setitem__("is_proof", True), "not be presented as proof"),
            ("evidence_kind", lambda e: e.__setitem__("evidence_kind", "verified_proof"), "not labelled platform-reported"),
            ("statement", lambda e: e.__setitem__("statement", "The image was independently verified."), "is not the pinned platform-reported wording"),
            ("kaggle_image", lambda e: e.__setitem__("kaggle_image_reported_string", "some-other-image"), "differs from the numerical platform slot"),
            ("extra field", lambda e: e.__setitem__("proof_reference", "abc"), "wrong key set"),
    ):
        tampered = copy.deepcopy(accepted)
        mutate(tampered["image_build_evidence"])
        tampered["content_sha256"] = contract.content_sha256(
            {k: v for k, v in tampered.items() if k != "content_sha256"})
        require(refuses_with(prod.validate_production_identity, needle, tampered),
                f"a payload with a tampered evidence block ({label}) was not refused")
    ok("image/build evidence is structurally platform-reported and never proof")


# --------------------------------------------------------------------------
# 5. exact_match must refuse on ANY difference
# --------------------------------------------------------------------------

def test_exact_match_refusals(tree: str) -> None:
    accepted = full_identity(tree)

    # A one-byte change in one bound host file.  The second tree is a separate
    # synthetic mirror, so the change is made there and the real repository is
    # never written to.
    host_rel = SYNTHETIC_ROLE_FILES["record_writer"][0]
    with tempfile.TemporaryDirectory() as other_tree:
        make_synthetic_tree(other_tree)
        with open(os.path.join(tree, host_rel), "rb") as handle:
            original = handle.read()
        rewrite(other_tree, host_rel, original + b"x")
        changed_session = full_identity(other_tree)
    require(changed_session["qualification_identity"]["source_sha256"][host_rel] !=
            accepted["qualification_identity"]["source_sha256"][host_rel],
            "the one-byte bound-file change did not change a source hash")
    try:
        prod.exact_match(changed_session, accepted)
    except prod.ProductionIdentityMismatch as exc:
        require(any(host_rel in field for field in exc.differing_fields),
                "the one-byte bound-file refusal did not name the file: "
                + repr(exc.differing_fields))
        ok("exact_match refuses a one-byte change in a bound host file and names it")
    else:
        raise RuntimeError("FIXTURE FAILURE: exact_match accepted a changed bound host file")
    require(refuses(prod.exact_match, changed_session, accepted),
            "the changed-bound-file case must raise the mismatch type")
    try:
        prod.exact_match(accepted, changed_session)
    except prod.ProductionIdentityMismatch:
        pass
    else:
        raise RuntimeError("FIXTURE FAILURE: exact_match was asymmetric for a bound file")

    # A one-byte change in one bound v1 file refuses the WHOLE identity at
    # build time, because the v1 role is hash-pinned to the accepted release.
    with tempfile.TemporaryDirectory() as other_tree:
        make_synthetic_tree(other_tree)
        v1_rel = sorted(prod.load_v1_release(V1_REPO_ROOT)["source_sha256"])[0]
        with open(os.path.join(V1_REPO_ROOT, v1_rel), "rb") as handle:
            v1_original = handle.read()
        rewrite(other_tree, v1_rel, v1_original + b"x")
        require(refuses_with(prod.build_production_identity, "hash mismatch against the accepted",
                             repo_root=other_tree, role_paths=synthetic_role_paths(),
                             platform=dict(V1_PLATFORM), image_build=dict(V1_IMAGE_BUILD),
                             compiler_flags=list(V1_FLAGS)),
                "a one-byte change in a bound v1 file did not refuse the whole identity")
        require(refuses_with(prod.build_production_identity, v1_rel,
                             repo_root=other_tree, role_paths=synthetic_role_paths(),
                             platform=dict(V1_PLATFORM), image_build=dict(V1_IMAGE_BUILD),
                             compiler_flags=list(V1_FLAGS)),
                "the v1 one-byte refusal did not name the altered file")
        ok("a one-byte change in a bound v1 file refuses the whole identity, by name")

    # An unaltered second tree must produce an identity that matches exactly,
    # so the bound-file difference above came from the byte and not the tree.
    with tempfile.TemporaryDirectory() as other_tree:
        make_synthetic_tree(other_tree)
        unaltered = full_identity(other_tree)
    result = prod.exact_match(unaltered, accepted)
    require(result["verdict"] == "exact_match" and result["differing_fields"] == [],
            "an identical identity built in a second tree did not match")
    ok("two independently built identical identities match exactly")

    # Each numerical platform field, one at a time.
    for key in sorted(V1_PLATFORM):
        changed = dict(V1_PLATFORM)
        changed[key] = changed[key] + "x"
        changed_session = full_identity(tree, platform=changed)
        try:
            prod.exact_match(changed_session, accepted)
        except prod.ProductionIdentityMismatch as exc:
            require(any(f"platform.{key}" in field for field in exc.differing_fields),
                    f"the platform refusal for {key!r} did not name the field: {exc.differing_fields}")
        else:
            raise RuntimeError(f"FIXTURE FAILURE: exact_match accepted a changed platform {key!r}")
    ok("exact_match refuses every single numerical platform field change, by name")

    # Each image/build field, one at a time.  The value is always kept a
    # non-empty string ending in the [platform_reported] marker, so the change
    # is in the reported VALUE, not in its label.
    for key in sorted(V1_IMAGE_BUILD):
        changed = dict(V1_IMAGE_BUILD)
        changed[key] = "mutated-" + V1_IMAGE_BUILD[key]
        require(changed[key] != V1_IMAGE_BUILD[key] and
                changed[key].endswith(" [platform_reported]"),
                f"the image-field mutation for {key!r} was not a real change")
        changed_session = full_identity(tree, image_build=changed)
        try:
            prod.exact_match(changed_session, accepted)
        except prod.ProductionIdentityMismatch as exc:
            require(any(f"image_build_evidence.fields.{key}" in field for field in exc.differing_fields),
                    f"the image refusal for {key!r} did not name the field: {exc.differing_fields}")
        else:
            raise RuntimeError(f"FIXTURE FAILURE: exact_match accepted a changed image field {key!r}")
    ok("exact_match refuses every single image/build label change, by name")

    # The environment pin specifically.
    changed = dict(V1_IMAGE_BUILD)
    changed["kaggle_environment_pinning_platform_reported"] = "unpinned [platform_reported]"
    try:
        prod.exact_match(full_identity(tree, image_build=changed), accepted)
    except prod.ProductionIdentityMismatch as exc:
        require("kaggle_environment_pinning_platform_reported" in " ".join(exc.differing_fields),
                "the environment-pin change was not named")
    else:
        raise RuntimeError("FIXTURE FAILURE: exact_match accepted an unpinned environment")
    ok("exact_match refuses an environment that reports itself unpinned")

    # Compiler flags: any change at all, including order.
    for changed_flags in ([V1_FLAGS[1]] + V1_FLAGS[:1] + V1_FLAGS[2:],
                          list(reversed(V1_FLAGS)),
                          V1_FLAGS + ["-lineinfo"],
                          [f.replace("-O0", "-O2") for f in V1_FLAGS]):
        require(changed_flags != V1_FLAGS,
                f"the flags mutation {changed_flags!r} is not a real change")
        changed_session = full_identity(tree, flags=changed_flags)
        try:
            prod.exact_match(changed_session, accepted)
        except prod.ProductionIdentityMismatch:
            pass
        else:
            raise RuntimeError(f"FIXTURE FAILURE: exact_match accepted changed flags {changed_flags!r}")
    ok("exact_match refuses reordered, replaced, added and swapped compiler flags")

    # A role moved from one file to another: same bytes, different scope.
    moved = synthetic_role_paths()
    moved["record_writer"] = [SYNTHETIC_ROLE_FILES["d016_reconstruction"][0]]
    moved["d016_reconstruction"] = [SYNTHETIC_ROLE_FILES["record_writer"][0]]
    moved_session = full_identity(tree, role_paths=moved)
    require(moved_session["qualification_identity"]["source_sha256"] ==
            accepted["qualification_identity"]["source_sha256"],
            "the role-swap fixture must keep the same file set and bytes")
    try:
        prod.exact_match(moved_session, accepted)
    except prod.ProductionIdentityMismatch as exc:
        require(any("source_map.roles." in field for field in exc.differing_fields),
                "the role-swap refusal did not name the role: " + repr(exc.differing_fields))
    else:
        raise RuntimeError("FIXTURE FAILURE: exact_match accepted a role swap")
    ok("exact_match refuses a role swap that leaves the file bytes identical")

    # A bound file added to a role.
    added = synthetic_role_paths()
    extra = "research/g9/wp4_synthetic/extra_writer.py"
    with open(os.path.join(tree, extra), "w", encoding="utf-8") as handle:
        handle.write("# synthetic extra\n")
    added["record_writer"] = list(added["record_writer"]) + [extra]
    try:
        prod.exact_match(full_identity(tree, role_paths=added), accepted)
    except prod.ProductionIdentityMismatch:
        pass
    else:
        raise RuntimeError("FIXTURE FAILURE: exact_match accepted an added bound file")
    os.remove(os.path.join(tree, extra))
    ok("exact_match refuses an added bound file")

    # A role dropped from the source map.  exact_match validates both payloads
    # first, so this is refused by the shape check before any comparison, and it
    # is refused whichever argument holds the damage.
    dropped = copy.deepcopy(accepted)
    del dropped["source_map"]["roles"]["record_writer"]
    dropped["content_sha256"] = contract.content_sha256({k: v for k, v in dropped.items() if k != "content_sha256"})
    require(refuses_with(prod.exact_match, "does not carry exactly the fixed role set",
                         dropped, accepted),
            "a source map missing a role was not refused")
    require(refuses_with(prod.exact_match, "does not carry exactly the fixed role set",
                         accepted, dropped),
            "a damaged accepted argument was not refused either")
    ok("exact_match refuses a source map missing a role, on either side")

    # Session and accepted swapped: the rule is symmetric.
    flipped = dict(V1_PLATFORM)
    flipped["gpu_name"] = "Tesla P100"
    flipped_session = full_identity(tree, platform=flipped)
    for left, right in ((flipped_session, accepted), (accepted, flipped_session)):
        try:
            prod.exact_match(left, right)
        except prod.ProductionIdentityMismatch as exc:
            require("gpu_name" in " ".join(exc.differing_fields),
                    "the symmetric refusal did not name gpu_name")
        else:
            raise RuntimeError("FIXTURE FAILURE: exact_match accepted a flipped argument order")
    ok("exact_match refuses symmetrically in both argument orders")

    # A tampered non-canonical identity must be refused before comparison.
    tampered = copy.deepcopy(accepted)
    tampered["qualification_identity"]["content_sha256"] = "0" * 64
    require(refuses_with(prod.exact_match, "not canonical", tampered, accepted),
            "a tampered inner identity hash was not refused")
    tampered = copy.deepcopy(accepted)
    tampered["content_sha256"] = "0" * 64
    require(refuses_with(prod.exact_match, "content_sha256 mismatch", tampered, accepted),
            "a tampered outer content hash was not refused")
    tampered = copy.deepcopy(accepted)
    tampered["status"] = "QUALIFIED"
    require(refuses_with(prod.exact_match, "status mismatch", tampered, accepted),
            "a self-declared qualified status was not refused")
    tampered = copy.deepcopy(accepted)
    tampered["authorization"] = "AUTHORIZED"
    require(refuses_with(prod.exact_match, "may not claim authorization", tampered, accepted),
            "a self-declared authorization was not refused")
    # An out-of-map source hash edit: the frozen numerical payload still holds
    # the real hash, so each view is internally consistent on its own and only
    # the cross-view binding catches the split.  The file must be named.
    tampered = copy.deepcopy(accepted)
    tampered["source_map"]["roles"]["record_writer"][0]["sha256"] = "0" * 64
    tampered["content_sha256"] = contract.content_sha256({k: v for k, v in tampered.items() if k != "content_sha256"})
    try:
        prod.exact_match(tampered, accepted)
    except prod.ProductionIdentityMismatch as exc:
        named = " ".join(exc.differing_fields)
        require(SYNTHETIC_ROLE_FILES["record_writer"][0] in named,
                "the out-of-map source hash refusal did not name the file: " + named)
        require("disagree on bound file(s)" in named,
                "the out-of-map source hash refusal lost the cross-view difference: " + named)
        ok("exact_match refuses an out-of-map source hash edit and names the file")
    else:
        raise RuntimeError("FIXTURE FAILURE: exact_match accepted an out-of-map source hash edit")

    # The same split in the ACCEPTED argument must be caught too.
    try:
        prod.exact_match(accepted, tampered)
    except prod.ProductionIdentityMismatch as exc:
        require("accepted source_map and frozen qualification_identity disagree" in
                " ".join(exc.differing_fields),
                "the cross-view check did not run on the accepted argument")
    else:
        raise RuntimeError("FIXTURE FAILURE: the cross-view check skipped the accepted argument")
    ok("the cross-view binding is checked on both arguments")
    tampered = copy.deepcopy(accepted)
    tampered["source_map"]["roles"]["record_writer"][0]["sha256"] = "NOT-A-SHA256"
    require(refuses_with(prod.exact_match, "source map role", tampered, accepted),
            "a non-sha256 out-of-map source hash was not refused")
    tampered = copy.deepcopy(accepted)
    tampered["source_map"]["bound_file_count"] = 1
    require(refuses_with(prod.exact_match, "bound_file_count", tampered, accepted),
            "a miscounted bound_file_count was not refused")
    tampered = copy.deepcopy(accepted)
    del tampered["source_map"]["roles"]["record_writer"][0]["sha256"]
    require(refuses_with(prod.exact_match, "malformed entry", tampered, accepted),
            "a malformed source map entry was not refused")
    tampered = copy.deepcopy(accepted)
    tampered["source_map"]["v1_engine_release_sha256"] = "0" * 64
    tampered["content_sha256"] = contract.content_sha256({k: v for k, v in tampered.items() if k != "content_sha256"})
    try:
        prod.exact_match(tampered, accepted)
    except prod.ProductionIdentityMismatch as exc:
        require("source_map.v1_engine_release_sha256" in " ".join(exc.differing_fields),
                "a repointed v1 release anchor was not named")
    else:
        raise RuntimeError("FIXTURE FAILURE: exact_match accepted a repointed v1 release anchor")
    tampered = copy.deepcopy(accepted)
    tampered["source_map"]["v1_engine_release_sha256"] = "0" * 64
    require(refuses_with(prod.exact_match, "content_sha256 mismatch", tampered, accepted),
            "a repointed v1 release anchor without a recomputed hash was not refused")
    tampered = copy.deepcopy(accepted)
    tampered["source_map"]["v1_engine_release_sha256"] = "not-a-sha256"
    tampered["content_sha256"] = contract.content_sha256({k: v for k, v in tampered.items() if k != "content_sha256"})
    require(refuses_with(prod.exact_match, "v1 release anchor must be a lowercase sha256",
                         tampered, accepted),
            "a malformed v1 release anchor was not refused")
    ok("exact_match refuses a tampered, self-declared or non-canonical identity")

    require(copy.deepcopy(accepted)["content_sha256"] == accepted["content_sha256"],
            "the fixture itself drifted: a deep copy is not an identity")


def test_forbidden_fields_in_source_map(tree: str) -> None:
    accepted = full_identity(tree)
    for forbidden in ("device_uuid", "session_id", "pci_bus_id"):
        tampered = copy.deepcopy(accepted)
        tampered["source_map"][forbidden] = "transient"
        tampered["content_sha256"] = contract.content_sha256(
            {k: v for k, v in tampered.items() if k != "content_sha256"})
        require(refuses_with(prod.validate_production_identity, "forbidden", tampered),
                f"a source map carrying {forbidden!r} was not refused")
    # A forbidden key nested inside the source map one level deeper.
    tampered = copy.deepcopy(accepted)
    tampered["source_map"]["roles"]["record_writer_entry_extra"] = {"device_uuid": "transient"}
    tampered["content_sha256"] = contract.content_sha256(
        {k: v for k, v in tampered.items() if k != "content_sha256"})
    require(refuses_with(prod.validate_production_identity, "forbidden", tampered),
            "a nested source map carrying device_uuid was not refused")
    # A forbidden key inside the image/build evidence.
    tampered = copy.deepcopy(accepted)
    tampered["image_build_evidence"]["session_id"] = "transient"
    tampered["content_sha256"] = contract.content_sha256(
        {k: v for k, v in tampered.items() if k != "content_sha256"})
    require(refuses_with(prod.validate_production_identity, "forbidden", tampered),
            "an evidence block carrying session_id was not refused")
    # A wrong top-level key set, and a non-mapping payload.
    require(refuses_with(prod.validate_production_identity, "must be a mapping", "not-a-mapping"),
            "a non-mapping payload was not refused")
    require(refuses_with(prod.validate_production_identity, "wrong key set", {"schema": "x"}),
            "a truncated payload was not refused")
    # The payload's own schema string.
    for bad_schema in ("decisions_os/g9_stage2_production_qualification_identity/draft_v2",
                       "something/else/v1"):
        wrong = copy.deepcopy(accepted)
        wrong["schema"] = bad_schema
        wrong["content_sha256"] = contract.content_sha256(
            {k: v for k, v in wrong.items() if k != "content_sha256"})
        require(refuses_with(prod.validate_production_identity, "schema mismatch", wrong),
                f"a payload claiming schema {bad_schema!r} was not refused")
    # The evidence block and its fields must both be mappings.
    for label, damage, needle in (
            ("evidence", lambda p: p.__setitem__("image_build_evidence", ["not", "a", "map"]),
             "evidence must be a mapping"),
            ("fields", lambda p: p["image_build_evidence"].__setitem__("fields", ["not", "a", "map"]),
             "fields must be a mapping")):
        wrong = copy.deepcopy(accepted)
        damage(wrong)
        wrong["content_sha256"] = contract.content_sha256(
            {k: v for k, v in wrong.items() if k != "content_sha256"})
        require(refuses_with(prod.validate_production_identity, needle, wrong),
                f"a non-mapping {label} was not refused")
    # The evidence fields are re-validated, not merely present: a field whose
    # value lost its [platform_reported] marker must be refused even though the
    # evidence key set is intact.
    unlabelled = copy.deepcopy(accepted)
    unlabelled["image_build_evidence"]["fields"]["kaggle_kernel_version_platform_reported"] = "v9"
    unlabelled["content_sha256"] = contract.content_sha256(
        {k: v for k, v in unlabelled.items() if k != "content_sha256"})
    require(refuses_with(prod.validate_production_identity, "does not carry the", unlabelled),
            "an unlabelled evidence field survived re-validation")
    ok("the evidence block is re-validated, not just carried")
    require(not refuses(prod.validate_production_identity, accepted),
            "the unaltered identity failed its own validation")
    ok("a payload with a forbidden transient field or a wrong key set is refused")


def test_v1_release_structural_refusals() -> None:
    """Each structural check of the release anchor, reached with its own defect.

    The SHA-256 pin is the last check, so these are reachable: without this
    section every structural check would be masked by the pin.
    """
    with open(os.path.join(V1_REPO_ROOT, prod.V1_RELEASE_REL), "rb") as handle:
        good_raw = handle.read()
    good = json.loads(good_raw.decode("utf-8"))
    cases = (
        ("wrong top-level key set", lambda r: r.pop("status"), "wrong top-level key set"),
        ("extra top-level key", lambda r: r.__setitem__("extra", 1), "wrong top-level key set"),
        ("schema mismatch", lambda r: r.__setitem__("schema", "other/v1"), "schema mismatch"),
        ("status not approved",
         lambda r: r.__setitem__("status", "pending"), "is not approved"),
        ("not exactly 12 entries",
         lambda r: r["source_sha256"].pop(next(iter(r["source_sha256"]))),
         "must hold exactly 12 entries"),
        ("entry is not a sha256",
         lambda r: r["source_sha256"].__setitem__(next(iter(r["source_sha256"])), "nope"),
         "is not a sha256"),
        ("entry is not a source file",
         lambda r: r["source_sha256"].__setitem__("research/g9/not_a_source.txt",
                                                  r["source_sha256"].pop(
                                                      next(iter(r["source_sha256"])))),
         "is not a source file"),
        ("plan_content_sha256 is not a sha256",
         lambda r: r.__setitem__("plan_content_sha256", "nope"),
         "plan_content_sha256 is not a sha256"),
    )
    for label, damage, needle in cases:
        with tempfile.TemporaryDirectory() as tree:
            make_synthetic_tree(tree)
            mutated = copy.deepcopy(good)
            damage(mutated)
            with open(os.path.join(tree, prod.V1_RELEASE_REL), "w", encoding="utf-8") as handle:
                json.dump(mutated, handle, sort_keys=True, separators=(",", ":"))
            require(refuses_with(prod.load_v1_release, needle, tree),
                    f"a release with {label} was not refused with its own message")
    # A structurally valid release that is simply not the accepted one is
    # refused by the pin, and the refusal names the accepted hash.
    with tempfile.TemporaryDirectory() as tree:
        make_synthetic_tree(tree)
        altered = copy.deepcopy(good)
        altered["plan_content_sha256"] = "0" * 64
        with open(os.path.join(tree, prod.V1_RELEASE_REL), "w", encoding="utf-8") as handle:
            json.dump(altered, handle, sort_keys=True, separators=(",", ":"))
        require(refuses_with(prod.load_v1_release, "is not the accepted release", tree),
                "a structurally valid but unaccepted release was not refused by the pin")
        require(refuses_with(prod.load_v1_release, prod.V1_RELEASE_SHA256, tree),
                "the pin refusal did not name the accepted release hash")
    # Undecodable JSON and an empty repo root.
    with tempfile.TemporaryDirectory() as tree:
        make_synthetic_tree(tree)
        with open(os.path.join(tree, prod.V1_RELEASE_REL), "wb") as handle:
            handle.write(b"not json at all")
        require(refuses_with(prod.load_v1_release, "not decodable JSON", tree),
                "an undecodable release file was not refused")
    require(refuses_with(prod.load_v1_release, "non-empty string", ""),
            "an empty repo root was not refused")
    require(not refuses(prod.load_v1_release, V1_REPO_ROOT),
            "the real accepted release failed its own loader")
    ok("every §A release structural check is reachable and names its defect")


def test_source_map_shape_refusals(tree: str) -> None:
    """Each source-map shape check, reached by damaging a real source map."""
    accepted = full_identity(tree)
    base_map = accepted["source_map"]

    def rehash(payload: dict) -> dict:
        payload["content_sha256"] = contract.content_sha256(
            {k: v for k, v in payload.items() if k != "content_sha256"})
        return payload

    cases = (
        ("wrong key set", lambda m: m.pop("hash_algorithm"), "wrong key set"),
        ("schema mismatch", lambda m: m.__setitem__("schema", "other/v1"), "schema mismatch"),
        ("hash algorithm mismatch", lambda m: m.__setitem__("hash_algorithm", "md5"),
         "hash algorithm mismatch"),
        ("v1 anchor not a sha256", lambda m: m.__setitem__("v1_engine_release_sha256", "x"),
         "v1 release anchor must be a lowercase sha256"),
        ("v1 plan hash not a sha256", lambda m: m.__setitem__("v1_engine_plan_content_sha256", "x"),
         "v1 plan content hash must be a lowercase sha256"),
        ("role set changed", lambda m: m["roles"].pop("record_writer"),
         "does not carry exactly the fixed role set"),
        ("extra role", lambda m: m["roles"].__setitem__("extra_role", m["roles"]["record_writer"]),
         "does not carry exactly the fixed role set"),
        ("empty role", lambda m: m["roles"].__setitem__("record_writer", []),
         "is empty or not a list"),
        ("malformed entry", lambda m: m["roles"]["record_writer"][0].pop("sha256"),
         "malformed entry"),
        ("extra entry key", lambda m: m["roles"]["record_writer"][0].__setitem__("note", "x"),
         "malformed entry"),
        ("entry sha not a sha256",
         lambda m: m["roles"]["record_writer"][0].__setitem__("sha256", "x"),
         "is not a sha256"),
        ("not_yet_built_roles changed",
         lambda m: m.__setitem__("not_yet_built_roles", ["record_writer"]),
         "does not match the fixed role table"),
        ("bound_file_count wrong", lambda m: m.__setitem__("bound_file_count", 1),
         "bound_file_count does not equal"),
    )
    for label, damage, needle in cases:
        payload = copy.deepcopy(accepted)
        damage(payload["source_map"])
        require(refuses_with(prod.validate_production_identity, needle, rehash(payload)),
                f"a source map with {label} was not refused with its own message")

    # A path appearing in two roles, and unsorted role entries.
    duplicated = copy.deepcopy(accepted)
    duplicated["source_map"]["roles"]["d016_reconstruction"] = copy.deepcopy(
        duplicated["source_map"]["roles"]["record_writer"])
    duplicated["source_map"]["bound_file_count"] = sum(
        len(entries) for entries in duplicated["source_map"]["roles"].values())
    require(refuses_with(prod.validate_production_identity, "more than one role in the source map",
                         rehash(duplicated)),
            "a path duplicated across roles was not refused")
    unsorted_map = copy.deepcopy(base_map)
    unsorted_map["roles"]["d013_plus_zero_cuda_path"].reverse()
    require(refuses_with(prod.validate_source_map_shape, "not in sorted path order", unsorted_map),
            "unsorted role entries were not refused")
    ok("every source-map shape check is reachable and names its defect")


def test_exact_match_per_field_comparisons(tree: str) -> None:
    """Each comparison in exact_match, reached by a difference it alone catches.

    These cases recompute the outer content hash, so they are internally valid
    payloads: without this section each field comparison is masked by the
    content-hash difference.
    """
    accepted = full_identity(tree)

    def rehash(payload: dict) -> dict:
        payload["content_sha256"] = contract.content_sha256(
            {k: v for k, v in payload.items() if k != "content_sha256"})
        return payload

    def names(needle: str, session: dict) -> list[str]:
        """Return the difference list, or [] when the identities match exactly."""
        try:
            return list(prod.exact_match(session, accepted)["differing_fields"])
        except prod.ProductionIdentityMismatch as exc:
            return list(exc.differing_fields)

    def refuses_match(needle: str, session: dict) -> None:
        require(refuses_with(prod.exact_match, needle, session, accepted),
                f"exact_match did not refuse with {needle!r}")

    # An unchanged identity must report no difference at all, so the cases
    # below are attributable to the field they damage.
    require(not names("unchanged", rehash(copy.deepcopy(accepted))),
            "an unchanged identity was reported as different")

    # bound_file_count is re-derived by the shape validator, so a miscount is
    # refused before the comparison rather than named by it.  That is the
    # stronger behaviour; the comparison's own scalar branch is covered by
    # not_yet_built_roles below, which the shape validator also pins, so the
    # scalar branch is reached only for fields the validator does not own.
    miscounted = copy.deepcopy(accepted)
    miscounted["source_map"]["bound_file_count"] = 999
    refuses_match("bound_file_count does not equal", rehash(miscounted))

    # not_yet_built_roles is likewise pinned by the shape validator.
    retagged = copy.deepcopy(accepted)
    retagged["source_map"]["not_yet_built_roles"] = ["record_writer"]
    refuses_match("does not match the fixed role table", rehash(retagged))

    # The evidence block's scalar fields.  The validator pins evidence_kind,
    # is_proof, statement and the kaggle_image binding, so a scalar change is
    # refused there; the comparison's own scalar branch is therefore reached
    # only when BOTH sides are valid, which is asserted below.
    for field, value, needle in (
            ("is_proof", True, "not be presented as proof"),
            ("evidence_kind", "verified", "not labelled platform-reported"),
            ("statement", "platform reported, verified independently",
             "is not the pinned platform-reported wording")):
        altered = copy.deepcopy(accepted)
        altered["image_build_evidence"][field] = value
        refuses_match(needle, rehash(altered))

    # A compiler-flag difference is already covered above; here the aggregate
    # "bound file(s) differ" summary must also be present, so the two branches
    # are independently observable.
    with tempfile.TemporaryDirectory() as other_tree:
        make_synthetic_tree(other_tree)
        with open(os.path.join(other_tree, SYNTHETIC_ROLE_FILES["record_writer"][0]), "ab") as handle:
            handle.write(b"x")
        changed = full_identity(other_tree)
    refuses_match("bound file", changed)
    found = names("bound file", changed)
    require(any("bound file(s) differ" in item for item in found),
            "the aggregate bound-file difference was not reported")
    require(any("source_map.roles.record_writer" in item for item in found),
            "the per-role difference was not reported")
    require(any("qualification_identity.source_sha256" in item for item in found),
            "the frozen source_sha256 difference was not reported")
    require(any("content_sha256" in item for item in found),
            "the content-hash difference was not reported")
    require(len(found) == len(set(found)),
            "the difference list contains duplicates")
    ok("each exact_match comparison is independently reachable and named")

    # Every field comparison must be reachable as a NAMED difference, not just
    # as a refusal.  These cases damage one field on ONE side of an otherwise
    # valid pair, so the only thing that can name it is that field's own
    # comparison; the content-hash difference can never name a field.
    def one_sided(damage) -> list[str]:
        altered = copy.deepcopy(accepted)
        damage(altered)
        return names("one-sided", rehash(altered))

    def _set(payload: dict, field: str, value: object) -> dict:
        payload[field] = value
        return payload

    # `status` and `authorization` are each pinned to one admissible value by
    # the validator, so they cannot reach the comparison.  The comparison's
    # own top-level branch is therefore unreachable for them and the validator
    # is the stronger guarantee; both are asserted here.
    for field, value, needle in (("status", "QUALIFIED", "status mismatch"),
                                 ("authorization", "AUTHORIZED", "may not claim authorization")):
        damaged = copy.deepcopy(accepted)
        damaged[field] = value
        require(refuses_with(prod.exact_match, needle, rehash(damaged), accepted),
                f"a one-sided {field!r} change was not refused by the validator")
    require(refuses_with(prod.exact_match, "status mismatch", accepted,
                         rehash(_set(copy.deepcopy(accepted), "status", "QUALIFIED"))),
            "the same damage in the accepted argument was not refused either")
    require(accepted["status"] == "DRAFT_UNQUALIFIED",
            "the fixture mutated its own accepted identity")
    # `qualification_identity.schema` is pinned by the frozen contract, so a
    # one-sided change is refused there rather than named by the comparison.
    damaged = copy.deepcopy(accepted)
    damaged["qualification_identity"]["schema"] = "other/qualification_identity/v1"
    require(refuses_with(prod.exact_match, "qualification schema mismatch", rehash(damaged), accepted),
            "a one-sided inner schema change was not refused by the frozen contract")
    # A different-but-valid flag set: built by the module itself, so the
    # frozen payload is canonical and only the flag comparison can see it.
    with tempfile.TemporaryDirectory() as other_tree:
        make_synthetic_tree(other_tree)
        alternative = full_identity(other_tree, flags=list(reversed(V1_FLAGS)))
    found = names("flags", alternative)
    require(any("qualification_identity.compiler_flags" in item for item in found),
            "a different valid flag set was not named by the flag comparison: " + repr(found))
    # A differently-valued but still well-formed source-map anchor is a NAMED
    # difference: the shape validator only pins its form, so the comparison is
    # the only thing that can catch a repointed anchor.
    for field, value in (("v1_engine_plan_content_sha256", "2" * 64),
                         ("v1_engine_release_sha256", "3" * 64)):
        found = one_sided(lambda p, f=field, v=value: p["source_map"].__setitem__(f, v))
        require(any(f"source_map.{field}" in item for item in found),
                f"a one-sided source_map.{field!r} change was not named: " + repr(found))
    # A malformed anchor is refused by the shape validator instead.
    damaged = copy.deepcopy(accepted)
    damaged["source_map"]["schema"] = "other/source_map/v1"
    require(refuses_with(prod.exact_match, "source map schema mismatch", rehash(damaged), accepted),
            "a one-sided source_map.schema change was not refused by the shape validator")
    found = one_sided(lambda p: p["image_build_evidence"]["fields"].__setitem__(
        "kaggle_docker_image_platform_reported", "mutated [platform_reported]"))
    require(any("image_build_evidence.fields.kaggle_docker_image_platform_reported" in item
                for item in found),
            "a one-sided image field difference was not named: " + repr(found))

    # A one difference must be reported once, not once per comparison that
    # notices it: a changed bound file is seen by three comparisons.
    # A single image-field defect is seen by only the fields comparison, so it
    # must appear exactly once in the list.
    require(len([item for item in found if "kaggle_docker_image" in item]) == 1,
            "a single image-field defect was reported more than once")
    # A one-byte bound-file change is seen by FOUR comparisons (the frozen
    # source_sha256 map, the per-role map, the aggregate bound-file summary and
    # the content hash).  All four entries are distinct strings, so all four
    # must survive: this is what makes the de-duplication a presentation guard
    # rather than a silent collapse of real findings.
    with tempfile.TemporaryDirectory() as other_tree:
        make_synthetic_tree(other_tree)
        with open(os.path.join(other_tree, SYNTHETIC_ROLE_FILES["record_writer"][0]), "ab") as handle:
            handle.write(b"x")
        byte_changed = full_identity(other_tree)
    reported = names("bound file", byte_changed)
    require(len(reported) == len(set(reported)),
            "the difference list contains duplicate entries: " + repr(reported))
    require(len(reported) == 4,
            f"a one-byte bound-file change produced {len(reported)} differences, "
            f"expected 4: " + repr(reported))
    for needle in ("qualification_identity.source_sha256.",
                   "bound file(s) differ:",
                   "source_map.roles.record_writer.",
                   "content_sha256"):
        require(sum(1 for item in reported if needle in item) == 1,
                f"the {needle!r} entry was duplicated or lost: " + repr(reported))
    ok("each comparison contributes once, and no difference is duplicated")


# --------------------------------------------------------------------------
# 6. The completeness fixture: EVERY leaf is pinned or compared, and NAMED
#
# This is the round-2 requirement and the direct regression test for the
# round-1 validator failure.  It enumerates every leaf path of a real built
# identity and, for EACH one:
#
#   * mutates that single leaf, keeping the payload otherwise well formed, and
#   * asserts `exact_match` REFUSES, and
#   * asserts the refusal NAMES that leaf -- either in `differing_fields` when
#     the field is COMPARED, or in the refusal message when the field is PINNED
#     and the validator catches it first.
#
# A difference in a COMPARED field must never be reachable only through the
# catch-all `content_sha256` entry, so the test also asserts the specific
# difference is present among the named fields, not merely that some refusal
# occurred.  This is what makes "the difference is NAMED" a checked property.
# --------------------------------------------------------------------------

def _descend(payload: object, components: tuple[str, ...]) -> object:
    """Walk to the container that HOLDS the leaf at `components`.

    A :data:`prod.SEQUENCE_MARK` component selects element 0 of the sequence, for
    the same reason it is a single component in the first place: every element of
    each such list has the same shape, so the first stands in for any one.
    """
    node = payload
    for component in components[:-1]:
        if component == prod.SEQUENCE_MARK:
            node = node[0]
        else:
            node = node[component]
    return node


def _leaf_slot(payload: object, components: tuple[str, ...]) -> tuple[object, object, object]:
    """Return ``(container, key, current)`` for the leaf at `components`.

    A :data:`prod.SEQUENCE_MARK` component selects the FIRST element of the
    sequence, which is sound because the entries of each such list are fixed in
    shape by a key-set or shape validator and every element is a leaf of the same
    type; mutating the first is therefore equivalent to mutating any one.
    """
    container = _descend(payload, components)
    last = components[-1]
    if last == prod.SEQUENCE_MARK:
        return container, 0, container[0]
    return container, last, container[last]


def _mutate_value(current: object) -> object:
    """A value guaranteed to differ from `current` but keep the payload's shape.

    A string becomes a different string, a bool flips, and any other value
    becomes a marker string.  A string that ends in the image-label marker
    ``[platform_reported]`` is mutated BEFORE that marker, so the mutated value
    is still a well-formed platform-reported field: otherwise the change would be
    refused by the label check rather than compared, and the field's own
    comparison would never be exercised.  The mutation must be a real difference,
    and the fixture asserts that, so a no-op mutation can never pass vacuously.
    """
    marker = " [" + prod.PLATFORM_REPORTED_LABEL + "]"
    if isinstance(current, bool):
        return not current
    if type(current) is int:
        return current + 1
    if isinstance(current, str):
        if prod._is_hex_sha256(current):
            # A digest must stay a well-formed lowercase sha256 or the FROZEN
            # contract refuses it on shape before the comparison is reached;
            # flipping the last hex digit keeps the format and changes the value.
            return current[:-1] + ("0" if current[-1] != "0" else "1")
        if current.endswith(marker):
            return current[:-len(marker)] + "-MUTATED" + marker
        return current + "WP1-LEAF-MUTATION"
    return "WP1-LEAF-MUTATION"


def _mutate_leaf(accepted: dict, components: tuple[str, ...]) -> dict:
    """Return a copy of `accepted` with exactly the leaf at `components` changed.

    Two mutation strategies are needed, and choosing the wrong one makes the
    payload non-canonical so an EARLIER check refuses it and the leaf's own
    comparison is never reached:

    * Leaves INSIDE the frozen ``qualification_identity`` sub-payload
      (``platform``, ``source_sha256``, ``compiler_flags``) cannot be edited in
      place: the FROZEN ``validate_qualification_identity`` rebuilds the payload
      and requires it to equal the rebuild, so an in-place edit is refused as
      "not canonical".  These are therefore changed by REBUILDING the whole
      identity through the module from altered inputs, which is also what a real
      differing session would be.  The same applies to any leaf that a second
      ``build_production_identity`` can produce differently.

    * Every other leaf is edited in place and the outer seal is recomputed, so
      the difference is a real in-payload difference rather than a stale hash.
      The recompute is SKIPPED for the outer ``content_sha256`` itself, which is
      the seal: overwriting it would erase the very difference under test.
    """
    # -- frozen-inner leaves: rebuild through the module ---------------------
    if components[:1] == ("qualification_identity",) and len(components) >= 2:
        section = components[1]
        if section == "compiler_flags":
            # A different, still-canonical flag set: built by the module itself.
            return full_identity(V1_TREE_OF[0], flags=list(reversed(V1_FLAGS)))
        if section == "platform":
            key = components[2]
            changed = dict(V1_PLATFORM)
            changed[key] = _mutate_value(changed[key])
            return full_identity(V1_TREE_OF[0], platform=changed)
        if section == "source_sha256":
            # A one-byte change in one bound host file, made in a SECOND tree so
            # the real repository is never written to.  This yields a fully valid
            # second identity, so the frozen-view COMPARISON is reached.
            rel = components[2]
            if rel in v1_role_paths():
                # A v1 file is hash-pinned to the accepted §A release, so a
                # rebuilt identity with changed v1 bytes is refused outright --
                # the correct, stronger behaviour, asserted elsewhere.  To reach
                # the comparison, the digest is changed consistently in BOTH
                # views instead, which is what a real differing session holds.
                return _edit_matching_views(accepted, ("source_map", "roles",
                                                       prod.V1_ENGINE_ROLE,
                                                       prod.SEQUENCE_MARK,
                                                       "sha256"), rel=rel)
            other = tempfile.mkdtemp(prefix="wp1-leaf-")
            _LEAF_TREES.append(other)
            make_synthetic_tree(other)
            with open(os.path.join(other, rel), "ab") as handle:
                handle.write(b"x")
            return full_identity(other)

    # A bound-file digest under the role-tagged source map is the same datum as
    # the frozen view's, so it is edited in BOTH views to keep the identity
    # internally consistent and reach the per-role comparison.
    if components[:2] == ("source_map", "roles") and components[-1] == "sha256":
        return _edit_matching_views(accepted, components,
                                    rel=accepted["source_map"]["roles"][components[2]][0]["path"])

    # -- everything else: in-place leaf edit, then re-seal --------------------
    return _in_place_mutation(accepted, components)


def _edit_matching_views(accepted: dict, components: tuple[str, ...],
                        rel: str | None = None) -> dict:
    """Edit a bound-file datum in BOTH views that carry it, consistently.

    A source hash appears TWICE in the payload: once under the frozen
    ``qualification_identity.source_sha256`` and once in the role-tagged
    ``source_map.roles``.  Editing only one of the two makes the identity
    internally inconsistent, which ``exact_match`` refuses by the cross-view
    binding -- the correct and stronger behaviour, but it means the per-role
    COMPARISON is never reached.  To reach that comparison, the same datum is
    changed in both views, which is exactly the shape a real differing session
    has: a genuinely different bound file, consistently recorded.  ``rel`` names
    the file when the caller already knows which one the leaf under test is.
    """
    session = copy.deepcopy(accepted)
    role = components[2]
    entries = session["source_map"]["roles"][role]
    if rel is None:
        rel = entries[0]["path"]
    if components[-1] == "path":
        # Changing WHICH file the role binds is only expressible by REBUILDING
        # the identity from a different role map: the source map's path list must
        # stay in sorted order and must agree with the frozen flat view, both of
        # which the shape validator and the cross-view binding enforce.  The role
        # is repointed at a DIFFERENT synthetic stand-in of the same shape, so
        # the role keeps its file count and the map stays sorted; this is a
        # genuinely different binding, i.e. a real difference to be named.
        role_paths = synthetic_role_paths()
        original = role_paths[role][0]
        rel = original[:-3] + "_other.py"
        other = tempfile.mkdtemp(prefix="wp1-leaf-")
        _LEAF_TREES.append(other)
        make_synthetic_tree(other)
        target = os.path.join(other, rel)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as handle:
            handle.write("# synthetic WP1 fixture stand-in\n" + rel + "\n")
        role_paths[role] = sorted([rel] + role_paths[role][1:])
        return prod.build_production_identity(
            repo_root=other, role_paths=role_paths,
            platform=dict(V1_PLATFORM), image_build=dict(V1_IMAGE_BUILD),
            compiler_flags=list(V1_FLAGS))
    # A digest change: apply the same new digest to BOTH views.
    session["qualification_identity"]["source_sha256"][rel] = _mutate_value(
        session["qualification_identity"]["source_sha256"][rel])
    session["qualification_identity"]["content_sha256"] = contract.content_sha256(
        {k: v for k, v in session["qualification_identity"].items()
         if k != "content_sha256"})
    for entries_of_role in session["source_map"]["roles"].values():
        for entry in entries_of_role:
            if entry["path"] == rel:
                entry["sha256"] = session["qualification_identity"]["source_sha256"][rel]
    session["content_sha256"] = contract.content_sha256(
        {k: v for k, v in session.items() if k != "content_sha256"})
    return session


def _in_place_mutation(accepted: dict, components: tuple[str, ...]) -> dict:
    """Edit one leaf in a deep copy, re-seal, and return the damaged payload.

    The outer seal is recomputed so the difference is a real in-payload
    difference rather than a stale hash, and the FROZEN inner seal is recomputed
    too when the edit landed inside ``qualification_identity`` -- the FROZEN
    validator rebuilds that sub-payload and requires equality, so leaving its
    digest stale would be refused as "not canonical" before the comparison runs.
    The outer recompute is SKIPPED when the leaf IS the outer ``content_sha256``,
    which is the seal: overwriting it would erase the difference under test.
    """
    session = copy.deepcopy(accepted)
    container, key, current = _leaf_slot(session, components)
    replacement = _mutate_value(current)
    require(replacement != current,
            f"the mutation of {'.'.join(components)!r} was a no-op")
    if key == prod.SEQUENCE_MARK or key == 0:
        container[0] = replacement
    else:
        container[key] = replacement
    if components[:1] == ("qualification_identity",) and len(components) == 2 \
            and components[1] == "content_sha256":
        # The leaf IS the frozen inner seal: re-sealing it here would erase the
        # very damage under test, which is the point -- the frozen contract must
        # refuse a payload whose declared inner digest is not its own rebuild.
        pass
    elif components[:1] == ("qualification_identity",):
        # Re-canonicalize the frozen sub-payload with the FROZEN implementation,
        # never a re-implementation of it.
        session["qualification_identity"]["content_sha256"] = contract.content_sha256(
            {k: v for k, v in session["qualification_identity"].items()
             if k != "content_sha256"})
    if components != ("content_sha256",):
        session["content_sha256"] = contract.content_sha256(
            {k: v for k, v in session.items() if k != "content_sha256"})
    return session


#: Scratch trees created for frozen-inner leaf mutations, removed after the run.
_LEAF_TREES: list[str] = []

#: Holds the synthetic tree the completeness test is running against, so the
#: frozen-inner rebuild path can build alternatives from the same inputs.
V1_TREE_OF: list[str] = []


def test_every_leaf_is_pinned_or_compared_and_named(tree: str) -> None:
    V1_TREE_OF[:] = [tree]
    try:
        _every_leaf_is_pinned_or_compared_and_named(tree)
    finally:
        for scratch in _LEAF_TREES:
            shutil.rmtree(scratch, ignore_errors=True)
        _LEAF_TREES.clear()


def _every_leaf_is_pinned_or_compared_and_named(tree: str) -> None:
    accepted = full_identity(tree)
    leaves = sorted(set(prod._leaf_paths(accepted)))
    require(len(leaves) >= 60,
            f"the walk found only {len(leaves)} leaves; the payload shape changed")

    # The declared table must be internally consistent before it is trusted:
    # every row names exactly one mechanism, and every leaf is covered by at
    # least one row.  `check_field_coverage` enforces the second at runtime;
    # here the first is asserted directly.
    for name, mechanism in prod.FIELD_COVERAGE.items():
        require(mechanism in (prod.PINNED, prod.COMPARED),
                f"coverage row {name!r} names no valid mechanism: {mechanism!r}")
    prod.check_field_coverage(accepted)

    pinned_seen: list[str] = []
    compared_seen: list[str] = []

    for components in leaves:
        path = ".".join(components)
        covering = [name for name, row in ((n, prod._row_components(n))
                                           for n in prod.FIELD_COVERAGE)
                    if prod._row_matches(row, components)]
        require(covering,
                f"leaf {path!r} is covered by no FIELD_COVERAGE row: it is neither "
                f"pinned nor compared")
        mechanisms = {prod.FIELD_COVERAGE[name] for name in covering}
        require(len(mechanisms) == 1,
                f"leaf {path!r} is covered by rows with conflicting mechanisms: "
                f"{[(n, prod.FIELD_COVERAGE[n]) for n in covering]}")
        mechanism = mechanisms.pop()

        # Mutate exactly this one leaf.  A bound-file digest lives in TWO views
        # of the payload, so it is changed in both (see `_mutate_leaf`); every
        # other leaf is changed in place.  Either way the result is a difference
        # the comparison must NAME.
        session = _mutate_leaf(accepted, components)

        # `exact_match` must refuse.  It may do so either as a NAMED difference
        # (a COMPARED field) or as the validator's typed refusal (a PINNED
        # field); both are refusals that name the field, and both are checked.
        refusal: str = ""
        differing: tuple[str, ...] = ()
        try:
            prod.exact_match(session, accepted)
        except prod.ProductionIdentityMismatch as exc:
            differing = tuple(exc.differing_fields)
            refusal = str(exc)
        except prod.ProductionIdentityError as exc:
            refusal = str(exc)
        else:
            raise RuntimeError(
                f"FIXTURE FAILURE: exact_match accepted a payload with a single "
                f"mutation of {path!r}")

        if mechanism == prod.COMPARED:
            # The field is free data, so the difference must surface as a NAMED
            # difference.  Requiring the leaf's own name here is what forbids the
            # round-1 failure mode of relying on the catch-all hash alone.
            needle = _comparison_needle(components)
            require(needle is not None,
                    f"no comparison name is defined for the COMPARED leaf {path!r}")
            if components == ("content_sha256",):
                # The outer digest is the SEAL.  Mutating it alone makes the
                # payload non-canonical, so the validator refuses it by name
                # before any comparison; that named refusal is the correct
                # handling, and the catch-all branch below is exercised
                # separately by a genuine field difference.
                require(_refusal_names(refusal, components),
                        f"a bare mutation of the outer content_sha256 was not "
                        f"refused by name: {refusal!r}")
                require("content_sha256" in refusal,
                        "the outer digest refusal does not name content_sha256")
                compared_seen.append(path)
                continue
            require(any(needle in item for item in differing),
                    f"the difference in the COMPARED leaf {path!r} was not NAMED "
                    f"(expected {needle!r} among {differing!r})")
            # The catch-all must never be the ONLY report of a compared field.
            # A single-leaf defect whose every entry mentions the content hash
            # is the exact round-1 defect, so at least one entry must be a
            # field-specific one.
            hash_only = all(item.startswith("content_sha256") for item in differing)
            require(not hash_only,
                    f"the difference in the COMPARED leaf {path!r} was reported only "
                    f"by the catch-all hash and was not named: {differing!r}")
            compared_seen.append(path)
        else:
            # The field is pinned, so the validator must refuse it BY NAME: the
            # refusal must mention the field, not merely fail.
            require(_refusal_names(refusal, components),
                    f"the PINNED leaf {path!r} was refused without naming the field: "
                    f"{refusal!r}")
            pinned_seen.append(path)

    # The run must have exercised both mechanisms, otherwise the test would
    # pass having proved only half the claim.
    require(pinned_seen, "no PINNED leaf was exercised")
    require(len(compared_seen) >= 40,
            f"only {len(compared_seen)} COMPARED leaves were exercised")
    ok(f"every one of {len(leaves)} leaves is pinned or compared and NAMED "
       f"({len(pinned_seen)} pinned by the validator, "
       f"{len(compared_seen)} compared by exact_match)")


def _comparison_needle(components: tuple[str, ...]) -> str | None:
    """The substring `exact_match` uses to NAME a COMPARED leaf.

    Mirrors the prefixes in `exact_match`.  The compiler-flags row is the one
    COMPARED field compared as a whole list rather than per key, and it is named
    as a list; the image fields and the platform fields are named per key.
    """
    path = ".".join(components)
    if path.startswith("qualification_identity.platform."):
        return "qualification_identity.platform." + components[2]
    if path.startswith("qualification_identity.source_sha256."):
        return "qualification_identity.source_sha256." + components[2]
    if path == "qualification_identity.compiler_flags.[any]":
        return "qualification_identity.compiler_flags"
    if path.startswith("source_map.roles."):
        return "source_map.roles." + components[2]
    if path.startswith("image_build_evidence.fields."):
        return "image_build_evidence.fields." + components[2]
    if path == "content_sha256":
        return "content_sha256"
    return None


def _refusal_names(refusal: str, components: tuple[str, ...]) -> bool:
    """True when a validator refusal message NAMES the pinned leaf.

    A PINNED field is caught before any comparison runs, so "named" for it means
    the refusal identifies WHICH field is wrong.  Every pin's message now repeats
    that field's own key -- round 2 added the key to the pins whose round-1
    message described the field only in domain terms ("hash algorithm mismatch"),
    keeping the old phrase as a substring so no existing assertion was weakened.
    The FROZEN contract's own message is the one exception: it reports a broken
    inner digest as "qualification identity is not canonical", and that message
    belongs to frozen code and is re-raised verbatim rather than reworded.
    """
    leaf = components[-1]
    if leaf in (prod.SEQUENCE_MARK, "[any]"):
        return True
    if leaf in refusal:
        return True
    return components == ("qualification_identity", "content_sha256") and \
        "qualification identity is not canonical" in refusal


# --------------------------------------------------------------------------
# 7. The completeness check itself is load-bearing, in BOTH directions
#
# `check_field_coverage` can refuse for two different reasons, and each needs a
# fixture: a payload carrying a field no row declares (the round-1 defect
# reintroduced), and a row that no longer describes the payload.  Without these
# the coverage check could be deleted and every other fixture would still pass.
# --------------------------------------------------------------------------

def test_field_coverage_is_load_both_ways(tree: str) -> None:
    accepted = full_identity(tree)

    # (a) an UNDECLARED field: a leaf appears that no row covers.  This is the
    # round-1 failure mode -- a field that is neither pinned nor compared.  In a
    # REAL payload every container is additionally guarded by a key-set or shape
    # check, which fires first; so the coverage check is the second line of
    # defence there, and it is exercised here DIRECTLY on the payload shape, to
    # prove the check itself is load-bearing rather than masked by the key sets.
    #
    # A NEW KEY inside a wildcard-covered sub-map is deliberately NOT the case:
    # the wildcard row covers any key at that position by design, and the
    # key-set validators are what bound the key set.  The uncovered case is a
    # leaf at a position no row reaches, which is what a new top-level field or
    # a new nesting level below a fixed key would be.
    new_top_level = copy.deepcopy(accepted)
    new_top_level["uncovered_top_level_field"] = "value"
    require(refuses_with(prod.check_field_coverage,
                         "neither pinned nor compared", new_top_level),
            "a new top-level field was not refused by the coverage check")
    require("uncovered_top_level_field" in str(_capture(prod.check_field_coverage,
                                                        new_top_level)),
            "the undeclared top-level field was not named")
    # A leaf nested one level deeper under a fixed key is equally uncovered.
    nested = copy.deepcopy(accepted)
    nested["source_map"]["roles"]["record_writer"][0]["nested"] = {"inner": "x"}
    require(refuses_with(prod.check_field_coverage,
                         "neither pinned nor compared", nested),
            "a nested undeclared leaf was not refused by the coverage check")
    ok("the coverage check refuses a field that no row declares, by name")

    # (b) an UNEXERCISED row: the table declares a field the payload does not
    # exhibit.  This is the OTHER failure direction, and it is what stops a row
    # from quietly going stale -- a renamed or removed field would otherwise
    # leave a row describing nothing, and the partition would look complete while
    # silently comparing one field less.  A bogus row is added to exercise it.
    original = prod.FIELD_COVERAGE
    prod.FIELD_COVERAGE = dict(original, **{"source_map.no_such_field": prod.PINNED})
    try:
        require(refuses_with(prod.check_field_coverage,
                             "no built payload exhibits", accepted),
                "a coverage row matching no payload field was not refused")
    finally:
        prod.FIELD_COVERAGE = original
    require(prod.check_field_coverage(accepted) is None,
            "the restored coverage table did not accept the real payload again")
    ok("the coverage check refuses a row that no built payload exhibits")

    # A wildcard row that is too NARROW leaves the fields it should cover
    # uncovered, so a wrongly-narrowed row is caught rather than silently
    # shrinking the compared surface.
    narrowed = {k: v for k, v in original.items()
                if k != "image_build_evidence.fields.*"}
    narrowed["image_build_evidence.fields.__no_such_key__"] = original[
        "image_build_evidence.fields.*"]
    prod.FIELD_COVERAGE = narrowed
    try:
        require(refuses_with(prod.check_field_coverage,
                             "neither pinned nor compared", accepted),
                "a coverage row narrowed to the wrong key was not refused")
    finally:
        prod.FIELD_COVERAGE = original
    ok("the coverage check refuses a row narrowed to the wrong key")

    # (c) A row must not cover a path merely by PREFIX.  `zip` stops at the
    # shorter tuple, so without the length test a one-component row such as
    # `schema` would "match" the two-component path `schema.nested` and the
    # nested leaf would silently be reported as covered.  The length test is
    # what prevents that, so it is exercised directly.
    original = prod.FIELD_COVERAGE
    prod.FIELD_COVERAGE = dict(original)
    prod.FIELD_COVERAGE.pop("source_map.v1_engine_release_sha256")
    prod.FIELD_COVERAGE["source_map"] = prod.PINNED   # 1-component prefix row
    try:
        require(refuses_with(prod.check_field_coverage,
                             "neither pinned nor compared", accepted),
                "a prefix-only coverage row covered a deeper field")
    finally:
        prod.FIELD_COVERAGE = original
    ok("a coverage row cannot cover a deeper path by prefix alone")


def rehash(payload: dict) -> dict:
    """Recompute the outer seal so an edit is a real in-payload difference."""
    payload["content_sha256"] = contract.content_sha256(
        {k: v for k, v in payload.items() if k != "content_sha256"})
    return payload


def test_absent_key_is_named_on_both_sides(tree: str) -> None:
    """A key present on one side of a COMPARED map and absent on the other.

    ``_platform_differences`` has two absent-key branches, one per side, and
    each says which side lacked the key.  A role that binds a DIFFERENT file in
    the two identities is the reachable way to hit both: the per-role map
    ``{path: sha256}`` then has one key the session lacks and one the accepted
    identity lacks, in a single comparison.  Every container's KEY SET is pinned
    by a validator, so this is the only way a compared key can be absent on one
    side only, and it is why the two branches are not dead code.
    """
    accepted = full_identity(tree)
    role = "record_writer"
    original_path = accepted["source_map"]["roles"][role][0]["path"]

    # Build a second, fully valid identity in which this role binds a different
    # file: a genuine difference, expressed the way a real session would.
    other = tempfile.mkdtemp(prefix="wp1-absent-")
    try:
        make_synthetic_tree(other)
        relocated = original_path[:-3] + "_other.py"
        target = os.path.join(other, relocated)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as handle:
            handle.write("# synthetic WP1 fixture stand-in\n" + relocated + "\n")
        role_paths = synthetic_role_paths()
        role_paths[role] = sorted([relocated] + role_paths[role][1:])
        session = prod.build_production_identity(
            repo_root=other, role_paths=role_paths,
            platform=dict(V1_PLATFORM), image_build=dict(V1_IMAGE_BUILD),
            compiler_flags=list(V1_FLAGS))
    finally:
        shutil.rmtree(other, ignore_errors=True)

    require(session["source_map"]["roles"][role][0]["path"] != original_path,
            "the relocated role did not actually change the bound path")

    def names(sess: dict, acc: dict) -> str:
        try:
            return " ".join(prod.exact_match(sess, acc)["differing_fields"])
        except prod.ProductionIdentityError as exc:
            return str(exc)

    reported = names(session, accepted)
    require("absent-from-session" in reported,
            "the key absent from the session side was not named: " + repr(reported))
    require("absent-from-accepted" in reported,
            "the key absent from the accepted side was not named: " + repr(reported))
    require(original_path in reported and relocated in reported,
            "neither side's key was named: " + repr(reported))
    # The comparison is symmetric, so reversing the arguments names the same
    # two keys against the same two sides.
    reversed_reported = names(accepted, session)
    require("absent-from-session" in reversed_reported
            and "absent-from-accepted" in reversed_reported,
            "reversing the arguments lost an absent-key name: " + repr(reversed_reported))
    ok("a key absent from either side of a compared map is refused and named")


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def main() -> None:
    test_role_table_is_the_decided_scope()
    test_pinned_constants_are_fixed_values()
    test_mismatch_subclass_carries_named_fields()
    with tempfile.TemporaryDirectory() as tree:
        make_synthetic_tree(tree)
        test_full_identity_builds_and_validates()
        test_source_map_refusals(tree)
        test_exact_match_refusals(tree)
        test_source_map_shape_refusals(tree)
        test_exact_match_per_field_comparisons(tree)
        test_every_leaf_is_pinned_or_compared_and_named(tree)
        test_field_coverage_is_load_both_ways(tree)
        test_absent_key_is_named_on_both_sides(tree)
    test_v1_role_refusals()
    test_v1_release_structural_refusals()
    test_platform_refusals()
    with tempfile.TemporaryDirectory() as tree:
        make_synthetic_tree(tree)
        test_image_build_evidence_labels(tree)
        test_forbidden_fields_in_source_map(tree)
    print(f"PASS WP1 production identity offline fixtures: {len(PASSED)}/{len(PASSED)} checks; "
          f"synthetic roles in a TemporaryDirectory; v1 role read-only; no Kaggle, no GPU, no "
          f"identity issued")


if __name__ == "__main__":
    main()

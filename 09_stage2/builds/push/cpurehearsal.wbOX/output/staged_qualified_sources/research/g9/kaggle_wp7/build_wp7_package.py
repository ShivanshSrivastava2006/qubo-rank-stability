#!/usr/bin/env python3
"""Assemble the WP7 offline DRAFT session package and its push manifest.

This builder never contacts Kaggle, never invokes the kaggle CLI or any
Kaggle API call, never reads a credential file or credential environment
variable, never uses the network, never allocates a GPU and never invokes
nvcc.  It only hashes files and writes JSON.

ROUND 3 trust anchor. The caller supplies the approved SHA-256 of the
separate reviewed table. Build and verify compare that exact byte digest
before using the table, and compare every dependency and package file with
its reviewed value. The manifest carries a copy of those facts but is never
the authority for them. New package entries are refused. A stale dependency
makes the draft invalid; an altered table or package file is refused.

Paths stay repo-relative and inside the root, and wrong argument types produce
typed WP7 refusals. This module only performs local file and JSON operations.

The manifest can never carry an "approved" or "pushed" status: the status
vocabulary is closed and a guard refuses any other value.
"""

from __future__ import annotations

import hashlib
import json
import os
import posixpath
import re
import sys
from pathlib import Path
from stat import S_ISREG
from typing import Any, Mapping, Sequence

MANIFEST_NAME = "wp7_push_manifest.draft.json"
REVIEWED_TABLE_NAME = "wp7_reviewed_dependencies.json"
MANIFEST_SCHEMA = "decisions_os/g9_wp7_push_manifest_draft/v2"
STATUS_INVALID = "draft_invalid"
STATUS_READY = "draft_ready_for_owner_review"
ALLOWED_STATUSES = (STATUS_INVALID, STATUS_READY)
FORBIDDEN_STATUS_FRAGMENTS = ("approved", "pushed", "push_complete", "released", "executed")
PENDING = "PENDING"

SCHEMA_VERSION = "v2"

# Every file of the package itself.  All of them are pinned by the manifest.
#
# This tuple IS the inventory: it names exactly the files the package
# directory holds.  Prior round saves ("*.r1" / "*.r2") are NOT listed, so a
# round-save file left beside the package is an unreviewed entry and
# ``assert_package_inventory`` refuses it rather than silently pinning it.
PACKAGE_FILES = (
    "wp7_session.py",
    "wp7_environment_pin.json",
    "build_wp7_package.py",
    "verify_wp7_package_fixtures.py",
    "GATE_9_WP7_PACKAGE_DRAFT.md",
)

# Every top-level key the manifest schema requires.  A manifest that is
# missing any of them is refused; completeness is verified, not assumed.
REQUIRED_MANIFEST_KEYS = (
    "schema",
    "status",
    "is_draft",
    "push_authorized",
    "gpu_allocation_authorized",
    "run_authorized",
    "can_emit_approved_or_pushed",
    "status_vocabulary",
    "invalidation_rule",
    "pin_closure_rule",
    "path_containment_rule",
    "dependency_table_sha256",
    "reviewed_table_sha256",
    "dependency_count",
    "dependencies_all_matched",
    "invalidating_reasons",
    "dependencies",
    "package_files_sha256",
    "package_file_count",
    "package_files_all_matched",
    "environment_pin",
    "kernel_metadata_draft",
    "kaggle_rewrites_on_pull",
    "authorization",
    "content_sha256",
)

# The states a dependency entry may carry, and the ones that mean the
# dependency is in force.  ``matched`` is the only state a ready manifest may
# contain.
DEPENDENCY_STATES = ("matched", "pending", "bad_recorded_hash", "missing", "hash_mismatch")
MATCHED_STATE = "matched"

_HEX64 = re.compile(r"\A[0-9a-f]{64}\Z")

# The dependency table this package ships with.  Entries are the reviewed
# sha256 for files whose review has PASSED; "PENDING" marks a file whose
# review has not passed.  WP1..WP6b have no review yet, so they are PENDING
# or absent, and that alone keeps the manifest invalid.
WP7_DEPENDENCY_TABLE: dict[str, str] = {
    # -- 12 v1 section-A release files (review passed 2026-09-25) --
    "research/g9/cuda_qualification/stage2_cuda_core_bridge.cu":
        "a94b59f672456de8370d020800bde80f0c892a6a258e2f78b8d59dde5e199846",
    "research/g9/cuda_qualification/stage2_cuda_core_bridge.py":
        "e0d13fbbc693be58c7c062edb546b5412397074de2f39f60f472d7b30aaaa088",
    "research/g9/cuda_qualification/stage2_cuda_core_corruption_qualification.py":
        "65f0f1d67d9df65602df28854b1dcae976a9c0bfe0c25eebb45cd7249527e218",
    "research/g9/cuda_qualification/stage2_cuda_core_qualification.py":
        "8b8cae6d839e581f993c5bf4a52a970036fa110b433481be1b31c7199103871d",
    "research/g9/cuda_qualification/stage2_cuda_core_stream_engine.cu":
        "fce00217f8530a695d676a774e4f741a83dec2aa7066c8f8a85ce136eac37d14",
    "research/g9/cuda_qualification/stage2_cuda_core_stream_engine.py":
        "d377411e6494c19fbc891df52e1ad7226de1df771bc7afdf059cf8a4368a644d",
    "research/g9/cuda_qualification/stage2_cuda_execution_contract.py":
        "f731690ec858bc4abaecd8edd3bd3c285ebae332b2ee1894241e431804d1a0c6",
    "research/g9/cuda_qualification/stage2_cuda_input_frame.py":
        "61186bf383ec25935852c01dd735f1ffd1f278d922baf4de26f6a95b0c13c597",
    "research/g9/run_stage2_cuda_core_corruption_qualification.py":
        "be6c06cf0587a0f4dadb47fb19554c4cbd4f368d9906a37bbc7b714c9c86f8b8",
    "research/g9/run_stage2_cuda_core_qualification.py":
        "b207aa09afc65a12341297dfc20e79bd163083c6f7221c574b96e60f7e6e431e",
    "research/g9/verify_stage2_cuda_core_corruption_qualification_fixtures.py":
        "b8d6ea456475436f1bf63b6dbcb8a01d825de56d3f6f9be5f165368ca8d6386f",
    "research/g9/verify_stage2_cuda_core_stream_engine_host_emulation.py":
        "16867cd54ac113d9ed9e28ef76cf072ce5a6b4663cbcec3638b3a0a3541dd630",
    # -- WP5 generation record-shaping files (in tree, review status recorded) --
    "research/g9/stage2_generation_release.py": PENDING,
    "research/g9/stage2_generation_writer.py": PENDING,
    "research/g9/stage2_generation_contract.py": PENDING,
    "research/g9/stage2_generator_guard.py": PENDING,
    "research/g9/stage2_commitment_adapter.py": PENDING,
    "research/g9/stage2_beacon_bls_verify.py": PENDING,
    "research/g9/stage2_timestamp_witness.py": PENDING,
    # -- WP1..WP6b: under review in other packages, may not exist here --
    "research/g9/stage2_production_identity.py": PENDING,
    "research/g9/stage2_section_b1_recheck.py": PENDING,
    "research/g9/stage2_section_b2_harness.py": PENDING,
    "research/g9/stage2_coordinate_records.py": PENDING,
    "research/g9/stage2_production_writer.py": PENDING,
    "research/g9/stage2_instance_preparation.py": PENDING,
    "research/g9/stage2_d013_inactive_evaluator.py": PENDING,
    "research/g9/cuda_qualification/stage2_cuda_d013_inactive.cu": PENDING,
    "research/g9/cuda_qualification/stage2_cuda_d013_inactive.py": PENDING,
}

# Kernel metadata draft.  Consistent with the submitted/pulled pairs under
# research/g9/kaggle_dry_run/: the submitted form carries only the policy
# fields, and Kaggle rewrites several fields on pull.
KERNEL_METADATA_DRAFT: dict[str, Any] = {
    "id": "OWNER_SLUG/g9-wp7-nonscientific-dry-run-DRAFT",
    "title": "G9 WP7 Nonscientific Dry Run DRAFT",
    "code_file": "g9_wp7_nonscientific_dry_run_draft.py",
    "kernel_type": "script",
    "language": "python",
    "is_private": True,
    "enable_gpu": True,
    "enable_internet": False,
    "enable_tpu": False,
    "machine_shape": "NvidiaTeslaT4",
    "keywords": [],
    "dataset_sources": [],
    "kernel_sources": [],
    "competition_sources": [],
    "model_sources": [],
    "docker_image_pinning_type": "DRAFT_REQUEST_PIN_TO_ACCEPTED_IMAGE_DIGEST",
    "draft": True,
}

# Fields Kaggle observed to rewrite between the submitted and pulled forms of
# the earlier runs.  Recorded so no reviewer mistakes a pulled field for a
# submitted one.
KAGGLE_REWRITES_ON_PULL = {
    "id_no": "added by Kaggle; not present in the submitted form",
    "code_file": "slugified (dashes) by Kaggle; the submitted form used underscores",
    "keywords": "Kaggle added 'gpu' in the accepted v1 pull; submitted value was []",
    "docker_image": "added by Kaggle on pull; never submitted in the accepted v1 run",
    "title": "echoed back; case and spacing preserved in every observed pair",
}

KERNEL_METADATA_REQUIRED_TRUE = ("is_private", "enable_gpu")
KERNEL_METADATA_REQUIRED_FALSE = ("enable_internet", "enable_tpu")
KERNEL_METADATA_REQUIRED_EMPTY_LISTS = (
    "dataset_sources", "kernel_sources", "competition_sources", "model_sources", "keywords",
)
KERNEL_METADATA_REQUIRED_TEXT = (
    "code_file", "id", "title", "kernel_type", "language", "machine_shape",
)

INVALIDATION_RULE = (
    "Any change to any dependency file -- one byte is enough -- changes its "
    "content hash, so this manifest's status returns to draft_invalid and the "
    "package requires revalidation before any owner review. The same is true "
    "of any file of the package itself, and of the dependency set as a whole."
)

PIN_CLOSURE_RULE = (
    "The dependency set is itself pinned: dependency_table_sha256 is the digest "
    "of the reviewed dependency set and dependency_count fixes its size. A "
    "manifest whose entries do not reproduce exactly that set at exactly that "
    "count is refused, so removing, adding or renaming a dependency entry "
    "invalidates the package even when every surviving entry still matches."
)

PATH_CONTAINMENT_RULE = (
    "Every dependency path is repo-relative, normalized, free of '.' and '..' "
    "components, and must resolve to a regular file inside the root. Absolute "
    "paths, parent-relative paths, backslashes, NUL bytes and symlinks that "
    "escape the root are refused before any file is read."
)


class Wp7PackageError(RuntimeError):
    """Typed refusal from the WP7 package builder."""


class Wp7PathError(Wp7PackageError):
    """A path is not a normalized, contained, repo-relative file path."""


class Wp7DependencyError(Wp7PackageError):
    """A dependency is missing, unreviewed, altered, or escapes the root."""


class Wp7CompletenessError(Wp7PackageError):
    """A manifest is incomplete: a required field is absent."""


def _require(condition: object, message: str) -> None:
    if not condition:
        raise Wp7PackageError(message)


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise Wp7PackageError(f"{label} must be a dict")
    for key in value:
        if not isinstance(key, str):
            raise Wp7PackageError(f"{label} keys must be strings")
    return value


def _sequence(value: object, label: str) -> list[Any]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, (list, tuple)):
        raise Wp7PackageError(f"{label} must be a list")
    return list(value)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise Wp7PackageError(f"{label} must be a string")
    return value


def _is_sha256(value: object) -> bool:
    if not isinstance(value, str):
        return False
    return _HEX64.match(value) is not None


def _require_sha256(value: object, label: str) -> str:
    text = _text(value, label)
    if _HEX64.match(text) is None:
        raise Wp7PackageError(f"{label} must be a lowercase sha256 hex digest")
    return text


def canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
        ).encode("ascii")
    except (TypeError, ValueError) as exc:
        raise Wp7PackageError(f"value is not canonicalizable: {exc}") from exc


def content_sha256(value: Any) -> str:
    if not isinstance(value, dict):
        raise Wp7PackageError("content_sha256 input must be a dict")
    for key in value:
        if not isinstance(key, str):
            raise Wp7PackageError(f"content_sha256 input keys must be strings: {key!r}")
    body = dict(value)
    body.pop("content_sha256", None)
    return hashlib.sha256(canonical_bytes(body)).hexdigest()


def sha256_file(path: Path) -> str:
    if not isinstance(path, Path):
        raise Wp7PackageError("sha256_file path must be a Path")
    try:
        data = path.read_bytes()
    except (OSError, ValueError) as exc:
        raise Wp7PackageError(f"cannot read {path}: {exc}") from exc
    return hashlib.sha256(data).hexdigest()


def dependency_table_sha256(table: Mapping[str, Any]) -> str:
    """Digest of the dependency SET: path -> recorded hash, canonicalized.

    Adding, removing or renaming one entry changes this digest, which is what
    makes a forged, trimmed manifest detectable.
    """
    entries = _mapping(table, "dependency table")
    for key in sorted(entries):
        if key == "":
            raise Wp7PathError("dependency table contains an empty path")
        if not isinstance(entries[key], str):
            raise Wp7PackageError(f"recorded hash for {key!r} must be a string")
    return content_sha256({"dependencies": [[key, entries[key]] for key in sorted(entries)]})


def normalize_relative_path(value: object, label: str) -> str:
    """Return the normalized repo-relative form, or refuse.

    Refuses absolute paths, backslashes, NUL bytes, empty or "." paths and
    any ".." component.  This is purely lexical: it is the first of the two
    path guards and runs before the filesystem is consulted.
    """
    if not isinstance(value, str):
        raise Wp7PathError(f"{label} must be a string")
    text = value
    if text == "":
        raise Wp7PathError(f"{label} must not be empty")
    if "\x00" in text:
        raise Wp7PathError(f"{label} must not contain a NUL byte")
    if "\\" in text:
        raise Wp7PathError(f"{label} must use '/' separators: {text!r}")
    if os.path.isabs(text):
        raise Wp7PathError(f"{label} must be repo-relative, not absolute: {text!r}")
    if ":" in text.split("/")[0]:
        raise Wp7PathError(f"{label} must be repo-relative, not drive-qualified: {text!r}")
    parts = text.split("/")
    for part in parts:
        if part == "":
            raise Wp7PathError(f"{label} must be normalized (empty path component): {text!r}")
        if part == ".":
            raise Wp7PathError(f"{label} must be normalized (a '.' component): {text!r}")
        if part == "..":
            raise Wp7PathError(f"{label} must not contain a '..' component: {text!r}")
    return text


def resolve_inside_root(root: Path, relative: object, label: str) -> Path:
    """Resolve a repo-relative path to a real file inside ``root`` or refuse.

    The second of the two path guards.  It refuses a missing file, a
    non-regular file (directory, FIFO, device) and any symlink whose real
    target leaves the root.  The containment decision is made on the fully
    resolved path, so a symlink chain cannot smuggle a read out of the tree.
    """
    if not isinstance(root, Path):
        raise Wp7PackageError("root must be a Path")
    rel = normalize_relative_path(relative, label)
    root_real = Path(os.path.realpath(str(root)))
    candidate = root / rel
    real = Path(os.path.realpath(str(candidate)))
    try:
        real.relative_to(root_real)
    except ValueError as exc:
        raise Wp7PathError(f"{label} resolves outside the root: {rel!r}") from exc
    if not real.exists():
        raise Wp7PathError(f"{label} does not exist in the tree: {rel!r}")
    # BOTH round-3 checks are kept, in their round-3 order.  ``is_file()``
    # follows symlinks; ``S_ISREG`` is the authoritative mode test that
    # refuses a FIFO, socket or device that ``exists()`` alone accepts.  The
    # validated round 3 shipped both, and neither is removed here.
    if not real.is_file():
        raise Wp7PathError(f"{label} is not a regular file: {rel!r}")
    if not S_ISREG(real.stat().st_mode):
        raise Wp7PathError(f"{label} is not a regular file: {rel!r}")
    return real


def validate_status(status: object) -> str:
    """Refuse any status outside the closed draft vocabulary."""
    text = _text(status, "status")
    if text not in ALLOWED_STATUSES:
        raise Wp7PackageError(f"status {text!r} is outside the closed draft vocabulary")
    lowered = text.lower()
    for fragment in FORBIDDEN_STATUS_FRAGMENTS:
        if fragment in lowered:
            raise Wp7PackageError(f"status {text!r} contains the forbidden fragment {fragment!r}")
    return text


def evaluate_dependencies(root: Path, table: Mapping[str, Any]) -> dict[str, Any]:
    """Hash every dependency and report each invalidating reason.

    A path that escapes the root is an invalidating *reason*, not a raise, so
    one bad entry is reported rather than aborting the whole evaluation; the
    entry still can never appear as "matched" in a ready manifest.
    """
    if not isinstance(root, Path):
        raise Wp7PackageError("root must be a Path")
    if not root.is_dir():
        raise Wp7PackageError(f"root is not a directory: {str(root)!r}")
    entries = _mapping(table, "dependency table")
    if len(entries) == 0:
        raise Wp7PackageError("dependency table is empty")
    results: list[dict[str, Any]] = []
    reasons: list[str] = []
    for relative in sorted(entries):
        recorded = entries[relative]
        entry: dict[str, Any] = {
            "path": None,
            "recorded_reviewed_sha256": None,
            "current_sha256": None,
            "state": None,
            "reason": None,
        }
        if not isinstance(relative, str):
            raise Wp7PackageError("dependency path must be a string")
        if relative == "":
            raise Wp7PathError("dependency path must not be empty")
        if not isinstance(recorded, str):
            raise Wp7PackageError(f"recorded hash for {relative!r} must be a string")
        entry["path"] = relative
        entry["recorded_reviewed_sha256"] = recorded
        if recorded == PENDING:
            entry["state"] = "pending"
            entry["reason"] = "review has not PASSED; no reviewed hash is recorded"
            try:
                pending_file = resolve_inside_root(root, relative, f"dependency path {relative!r}")
                entry["current_sha256"] = sha256_file(pending_file)
            except Wp7PathError as pending_exc:
                entry["reason"] += f"; {pending_exc}"
            reasons.append(f"{relative}: review PENDING")
            results.append(entry)
            continue
        if not _is_sha256(recorded):
            entry["state"] = "bad_recorded_hash"
            entry["reason"] = "recorded value is neither PENDING nor a lowercase sha256"
            reasons.append(f"{relative}: bad recorded hash")
            results.append(entry)
            continue
        try:
            real = resolve_inside_root(root, relative, f"dependency path {relative!r}")
        except Wp7PathError as exc:
            if "does not exist in the tree" in str(exc):
                entry["state"] = "missing"
                entry["reason"] = "file is not present in the tree"
            else:
                entry["state"] = "missing"
                entry["reason"] = str(exc)
            reasons.append(f"{relative}: {entry['reason']}")
            results.append(entry)
            continue
        current = sha256_file(real)
        entry["current_sha256"] = current
        if current != recorded:
            entry["state"] = "hash_mismatch"
            entry["reason"] = (
                f"content changed since review: recorded {recorded} current {current}"
            )
            reasons.append(f"{relative}: hash mismatch")
        else:
            entry["state"] = MATCHED_STATE
            entry["reason"] = None
        results.append(entry)
    return {
        "entries": results,
        "reasons": reasons,
        "all_matched": not reasons,
        "dependency_count": len(results),
    }


def evaluate_package_files(package_root: Path) -> dict[str, Any]:
    """Hash every file of the package itself.

    A package file that is absent, non-regular, unreadable or changed is an
    invalidating reason and a null recorded hash; it is never silently
    skipped, so a package can not be declared ready with a hole in it.

    The READ is guarded exactly like the dependency read in
    ``evaluate_dependencies``: ``sha256_file`` raises ``Wp7PackageError`` on an
    unreadable path, and an unreadable package file is an ordinary event (a
    permission change, a race with an editor), not a crash of a public entry
    point.  So the reason is returned, never raised.
    """
    hashes: dict[str, Any] = {}
    reasons: list[str] = []
    if not isinstance(package_root, Path):
        raise Wp7PackageError("package_root must be a Path")
    for name in PACKAGE_FILES:
        try:
            real = resolve_inside_root(package_root, name, f"package file {name!r}")
        except Wp7PackageError as exc:
            hashes[name] = None
            reasons.append(f"package file {name}: {exc}")
            continue
        try:
            hashes[name] = sha256_file(real)
        except Wp7PackageError as read_exc:
            hashes[name] = None
            reasons.append(f"package file {name}: {read_exc}")
    return {
        "hashes": hashes,
        "reasons": reasons,
        "all_matched": not reasons,
        "count": len(hashes),
    }



def load_reviewed_table(package_root: Path, expected_reviewed_table_sha256: str) -> dict[str, Any]:
    """Read the external review record only after checking its caller-supplied digest."""
    expected = _require_sha256(expected_reviewed_table_sha256, "expected reviewed table sha256")
    path = resolve_inside_root(package_root, REVIEWED_TABLE_NAME, "reviewed table")
    if sha256_file(path) != expected:
        raise Wp7DependencyError("reviewed table differs from caller approval")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError) as exc:
        raise Wp7DependencyError(f"cannot parse reviewed table: {exc}") from exc
    record = _mapping(raw, "reviewed table")
    dependencies = _mapping(record.get("dependencies"), "reviewed dependencies")
    package = _mapping(record.get("package_files_sha256"), "reviewed package files")
    if not dependencies:
        raise Wp7DependencyError("reviewed dependencies are empty")
    if set(package) != set(PACKAGE_FILES):
        raise Wp7DependencyError("reviewed table must name every package file")
    for name, recorded in dependencies.items():
        normalize_relative_path(name, "reviewed dependency path")
        if recorded != PENDING:
            _require_sha256(recorded, f"reviewed hash of {name}")
    for name, recorded in package.items():
        _require_sha256(recorded, f"reviewed package hash of {name}")
    return {"dependencies": dict(dependencies), "package_files_sha256": dict(package)}

def assert_package_inventory(root: Path, package_root: Path, dependencies: Mapping[str, Any]) -> None:
    """Refuse any package entry omitted from the reviewed file inventory."""
    if not isinstance(root, Path) or not isinstance(package_root, Path):
        raise Wp7PackageError("package inventory roots must be Paths")
    dependency_map = _mapping(dependencies, "reviewed dependencies")
    for name, recorded in dependency_map.items():
        normalize_relative_path(name, "reviewed dependency path")
        if recorded != PENDING:
            _require_sha256(recorded, f"reviewed hash of {name}")
    allowed = set(PACKAGE_FILES) | {REVIEWED_TABLE_NAME, MANIFEST_NAME}
    if root.resolve() == package_root.resolve():
        allowed.update(name.split("/")[0] for name in dependency_map)
    try:
        actual = {item.name for item in package_root.iterdir()}
    except (OSError, ValueError) as exc:
        raise Wp7PackageError(f"cannot list package files: {exc}") from exc
    unexpected = sorted(actual - allowed)
    if unexpected:
        raise Wp7DependencyError("unreviewed package entries: " + ", ".join(unexpected))


def build_manifest(
    root: Path,
    table: Mapping[str, Any],
    *,
    expected_reviewed_table_sha256: str,
    environment_pin: Mapping[str, Any] | None = None,
    package_root: Path | None = None,
) -> dict[str, Any]:
    """Assemble the draft push manifest.  Status is a pure function of hashes.

    ``table`` is required: there is no implicit default, so a caller can never
    silently build a manifest from a dependency set it did not supply.

    ``package_root`` is where the package's own files live, when that is not
    ``root`` itself (a repo-root build pins the files under the package
    directory).  It defaults to this file's directory, so a manifest always
    pins the real package rather than whatever happens to be beside the
    dependency tree.
    """
    if package_root is not None and not isinstance(package_root, Path):
        raise Wp7PackageError("package_root must be a Path or None")
    home = Path(__file__).resolve().parent if package_root is None else package_root
    reviewed = load_reviewed_table(home, expected_reviewed_table_sha256)
    assert_package_inventory(root, home, reviewed["dependencies"])
    if _mapping(table, "dependency table") != reviewed["dependencies"]:
        raise Wp7DependencyError("caller dependency table differs from independently reviewed table")
    evaluation = evaluate_dependencies(root, reviewed["dependencies"])
    package = evaluate_package_files(home)
    if package["hashes"] != reviewed["package_files_sha256"]:
        raise Wp7DependencyError("package files differ from independently reviewed table")
    status = validate_status(STATUS_READY if (evaluation["all_matched"] and package["all_matched"]) else STATUS_INVALID)
    reasons = list(evaluation["reasons"]) + list(package["reasons"])

    if environment_pin is None:
        pin: Mapping[str, Any] = {}
    elif isinstance(environment_pin, dict):
        pin = environment_pin
    else:
        raise Wp7PackageError("environment pin must be a dict or None")
    _mapping(pin, "environment pin")

    manifest: dict[str, Any] = {
        "schema": MANIFEST_SCHEMA,
        "status": status,
        "is_draft": True,
        "push_authorized": False,
        "gpu_allocation_authorized": False,
        "run_authorized": False,
        "invalidating_reasons": reasons,
        "dependencies": evaluation["entries"],
        "dependency_count": evaluation["dependency_count"],
        "dependencies_all_matched": evaluation["all_matched"],
        "dependency_table_sha256": dependency_table_sha256(reviewed["dependencies"]),
        "reviewed_table_sha256": expected_reviewed_table_sha256,
        "invalidation_rule": INVALIDATION_RULE,
        "pin_closure_rule": PIN_CLOSURE_RULE,
        "path_containment_rule": PATH_CONTAINMENT_RULE,
        "status_vocabulary": list(ALLOWED_STATUSES),
        "can_emit_approved_or_pushed": False,
        "package_files_sha256": dict(package["hashes"]),
        "package_file_count": package["count"],
        "package_files_all_matched": package["all_matched"],
        "environment_pin": {
            "provenance": pin.get("provenance_label", "PLATFORM-REPORTED"),
            "comparison_mode": pin.get("comparison_rule", {}).get("mode", "fail_closed")
            if isinstance(pin.get("comparison_rule"), dict)
            else "fail_closed",
            "platform_reported": pin.get("platform_reported", {}),
            "image_reported": pin.get("image_reported", {}),
            "pinning_request": pin.get("kaggle_environment_pinning_request", {}),
        },
        "kernel_metadata_draft": dict(KERNEL_METADATA_DRAFT),
        "kaggle_rewrites_on_pull": dict(KAGGLE_REWRITES_ON_PULL),
        "authorization": {
            "push_authorized": False,
            "gpu_allocation_authorized": False,
            "run_authorized": False,
            "note": "DRAFT. Nothing in this package may be pushed. The kaggle CLI and "
            "the Kaggle API are never invoked by this package.",
        },
    }
    manifest["content_sha256"] = content_sha256(manifest)
    return manifest


def validate_kernel_metadata_draft(metadata: Mapping[str, Any]) -> Mapping[str, Any]:
    """Check the draft metadata against the policy the earlier pairs show."""
    table = _mapping(metadata, "kernel metadata")
    for key in KERNEL_METADATA_REQUIRED_TRUE:
        if table.get(key) is not True:
            raise Wp7PackageError(f"kernel metadata {key} must be True")
    for key in KERNEL_METADATA_REQUIRED_FALSE:
        if table.get(key) is not False:
            raise Wp7PackageError(f"kernel metadata {key} must be False")
    for key in KERNEL_METADATA_REQUIRED_TEXT:
        text = _text(table.get(key), f"kernel metadata {key}")
        if text.strip() == "":
            raise Wp7PackageError(f"kernel metadata {key} is empty")
    for key in KERNEL_METADATA_REQUIRED_EMPTY_LISTS:
        value = table.get(key)
        if not isinstance(value, list) or len(value) != 0:
            raise Wp7PackageError(f"kernel metadata {key} must be an empty list")
    if table.get("draft") is not True:
        raise Wp7PackageError("kernel metadata draft flag must be True")
    return table


def _manifest_entry_set(manifest: Mapping[str, Any]) -> dict[str, Any]:
    # The mapping is checked HERE, not assumed: this helper is reached with a
    # caller-supplied object, and ``manifest.get`` on a non-mapping would leak
    # a raw AttributeError out of the entry point instead of a typed refusal.
    table = _mapping(manifest, "manifest")
    recorded_entries = table.get("dependencies")
    if not isinstance(recorded_entries, list) or len(recorded_entries) == 0:
        raise Wp7CompletenessError("manifest dependencies must be a non-empty list")
    entries: dict[str, Any] = {}
    for entry in _sequence(recorded_entries, "manifest dependencies"):
        record = _mapping(entry, "manifest dependency entry")
        for key in ("path", "state", "reason", "current_sha256", "recorded_reviewed_sha256"):
            if key not in record:
                raise Wp7CompletenessError(
                    f"manifest dependency entry is missing the required field {key!r}"
                )
        relative = _text(record.get("path"), "dependency entry path")
        if relative in entries:
            raise Wp7PackageError(f"dependency entry repeated in the manifest: {relative}")
        state = _text(record.get("state"), f"state of {relative}")
        if state not in DEPENDENCY_STATES:
            raise Wp7PackageError(f"dependency entry {relative} has unknown state {state!r}")
        entries[relative] = record
    return entries


def _verify_package_files(root: Path, manifest: Mapping[str, Any]) -> list[str]:
    """Re-hash every file of the package; any change makes the manifest stale.

    An unreadable, missing, non-regular or changed package file is a PROBLEM
    this function reports, never an exception it lets escape: ``sha256_file``
    raises ``Wp7PackageError`` on an unreadable path, and a package file that
    cannot be read right now is an ordinary invalidating condition, not a
    crash of a public entry point.  The caller turns the returned problems
    into the ``draft_invalid`` result.
    """
    table = _mapping(manifest, "manifest")
    recorded = _mapping(table.get("package_files_sha256"), "package_files_sha256")
    if len(recorded) != len(PACKAGE_FILES):
        raise Wp7CompletenessError(
            f"package_files_sha256 must pin all {len(PACKAGE_FILES)} package files"
        )
    count = manifest.get("package_file_count")
    if not isinstance(count, int) or isinstance(count, bool) or count != len(PACKAGE_FILES):
        raise Wp7CompletenessError("package_file_count must be the full package file count")
    problems: list[str] = []
    for name in PACKAGE_FILES:
        if name not in recorded:
            problems.append(f"package file {name}: not pinned by the manifest")
            continue
        recorded_hash = recorded[name]
        if not _is_sha256(recorded_hash):
            problems.append(f"package file {name}: manifest records no usable hash")
            continue
        try:
            real = resolve_inside_root(root, name, f"package file {name!r}")
        except Wp7PackageError as exc:
            problems.append(f"package file {name}: {exc}")
            continue
        try:
            actual = sha256_file(real)
        except Wp7PackageError as read_exc:
            problems.append(f"package file {name}: {read_exc}")
            continue
        if actual != recorded_hash:
            problems.append(f"package file {name}: content changed since the manifest was written")
    return problems


def verify_manifest(
    root: Path, manifest: Mapping[str, Any], *, expected_reviewed_table_sha256: str,
    package_root: Path | None = None
) -> dict[str, Any]:
    """Re-hash every dependency AND every package file; refuse a stale or
    incomplete manifest.

    A manifest is refused when it is missing a required field, when its own
    content digest does not match its body, when its dependency set does not
    reproduce the pinned ``dependency_table_sha256`` at the pinned
    ``dependency_count`` (so a removed entry cannot be hidden by recomputing
    the body digest), when any dependency's current hash differs from the
    manifest's recorded current hash, when any package file changed, or when
    any entry is not "matched" while the manifest claims the ready status.

    A package file that is unreadable, missing, non-regular or changed is
    carried in ``invalidating_reasons`` on a ``draft_invalid`` return rather
    than raised; a manifest that CLAIMS the ready status over any such finding
    is a forgery and is still refused loudly.
    """
    home = Path(__file__).resolve().parent if package_root is None else package_root
    reviewed = load_reviewed_table(home, expected_reviewed_table_sha256)
    assert_package_inventory(root, home, reviewed["dependencies"])
    table = _mapping(manifest, "manifest")
    if table.get("reviewed_table_sha256") != expected_reviewed_table_sha256:
        raise Wp7DependencyError("manifest reviewed table anchor differs from caller approval")
    for key in REQUIRED_MANIFEST_KEYS:
        if key not in table:
            raise Wp7CompletenessError(f"manifest is missing the required field {key!r}")
    status = validate_status(table.get("status"))
    if table.get("is_draft") is not True:
        raise Wp7PackageError("manifest is not marked as a draft")
    for key in ("push_authorized", "gpu_allocation_authorized", "run_authorized"):
        if table.get(key) is not False:
            raise Wp7PackageError(f"manifest {key} must be False")
    if table.get("can_emit_approved_or_pushed") is not False:
        raise Wp7PackageError("manifest must declare that it cannot emit approved or pushed")
    recorded_digest = _require_sha256(table.get("content_sha256"), "manifest content_sha256")
    if content_sha256(table) != recorded_digest:
        raise Wp7PackageError("manifest content_sha256 does not match its body; the manifest is stale")

    entries = _manifest_entry_set(table)
    count = table.get("dependency_count")
    if not isinstance(count, int) or isinstance(count, bool) or count != len(entries):
        raise Wp7CompletenessError(
            f"manifest dependency_count {count!r} does not match its {len(entries)} recorded entries"
        )
    observed_set: dict[str, Any] = {}
    for path, record in entries.items():
        observed_set[path] = _text(
            record.get("recorded_reviewed_sha256"), f"recorded reviewed hash of {path}"
        )
    if observed_set != reviewed["dependencies"]:
        raise Wp7DependencyError("manifest dependency entries differ from independently reviewed table")
    if dependency_table_sha256(observed_set) != table.get("dependency_table_sha256"):
        raise Wp7PackageError(
            "manifest dependency set does not match its pinned dependency_table_sha256; "
            "an entry was added, removed or re-recorded"
        )
    if table.get("package_files_all_matched") is not True:
        raise Wp7PackageError("manifest does not declare every package file matched")

    if table.get("package_files_sha256") != reviewed["package_files_sha256"]:
        raise Wp7DependencyError("manifest package hashes differ from independently reviewed table")
    package_problems: list[str] = list(_verify_package_files(
        Path(__file__).resolve().parent if package_root is None else package_root, table
    ))
    # A manifest that CLAIMS the ready status is a claim about the tree, so
    # a stale matched entry under that claim is a forgery and is refused
    # loudly.  Under any other status the same finding is an ordinary
    # invalidation -- which is exactly the owner's condition, "changes to
    # dependencies must invalidate the package and trigger revalidation" --
    # and is returned as ``draft_invalid`` with its reasons, never raised.
    # The non-matched states below stay a refusal either way: a manifest that
    # is not even internally verifiable must not be handed back as a result.
    #
    # A PACKAGE file that is unreadable, missing, non-regular or changed is the
    # SAME kind of finding as a stale dependency -- the tree moved under the
    # manifest -- so it is carried in ``invalidated`` too and is returned in
    # ``invalidating_reasons``, never raised out of this entry point.
    invalidated: list[str] = list(package_problems)
    problems: list[str] = []
    for relative in sorted(entries):
        record = entries[relative]
        state = record["state"]
        if state == MATCHED_STATE:
            recorded_current = record.get("current_sha256")
            if not _is_sha256(recorded_current):
                invalidated.append(f"{relative}: matched entry has no usable current hash")
                continue
            try:
                real = resolve_inside_root(root, relative, f"dependency path {relative!r}")
            except Wp7PackageError as exc:
                invalidated.append(f"{relative}: {exc}")
                continue
            try:
                actual = sha256_file(real)
            except Wp7PackageError as read_exc:
                invalidated.append(f"{relative}: {read_exc}")
                continue
            if recorded_current != reviewed["dependencies"][relative]:
                invalidated.append(f"{relative}: current hash differs from reviewed hash")
            if actual != recorded_current:
                invalidated.append(f"{relative}: stale; content changed since the manifest was written")
        else:
            reason = record.get("reason")
            if not isinstance(reason, str) or reason == "":
                problems.append(f"{relative}: entry is {state!r} and states no reason")
            problems.append(f"{relative}: recorded state is {state!r}, not 'matched'")
    if invalidated and status == STATUS_READY:
        problems.insert(0, "manifest claims the ready status but its dependencies are stale")
        problems.extend(invalidated)
    if invalidated and status != STATUS_READY:
        if problems:
            problems.extend(invalidated)
        return {
            "status": STATUS_INVALID,
            "verified_dependencies": len(entries),
            "verified_package_files": len(PACKAGE_FILES),
            "dependency_table_sha256": table.get("dependency_table_sha256"),
            "invalidating_reasons": invalidated,
        }
    if problems:
        raise Wp7PackageError("manifest is stale: " + "; ".join(problems))
    if status != STATUS_READY:
        raise Wp7PackageError(
            f"manifest status is {status!r}; an invalid manifest is not verifiable as ready"
        )
    return {
        "status": status,
        "verified_dependencies": len(entries),
        "verified_package_files": len(PACKAGE_FILES),
        "dependency_table_sha256": table.get("dependency_table_sha256"),
    }


def assert_safe_cli_path(value: object) -> None:
    if value is None:
        return
    if not isinstance(value, Path):
        raise Wp7PathError("CLI path must be a Path")
    lowered = str(value).lower()
    for fragment in (".kaggle", "kaggle.json", "credential", "secret", "token"):
        if fragment in lowered:
            raise Wp7PathError(f"refusing credential-related CLI path: {fragment}")


def main(argv: Sequence[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Assemble the WP7 draft push manifest offline.")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[3],
                        help="repository root; dependency paths are repo-relative")
    parser.add_argument("--expected-reviewed-table-sha256", required=True)
    parser.add_argument("--dependency-table", type=Path, help="optional JSON dependency table override")
    parser.add_argument("--out", type=Path, help="write the manifest here instead of beside the builder")
    parser.add_argument("--package-root", type=Path,
                        help="directory holding the package files; defaults to the builder's own directory")
    parser.add_argument("--verify", type=Path, help="verify an existing manifest and exit")
    args = parser.parse_args(_sequence(argv, "argv") if argv is not None else None)

    try:
        for candidate in (args.root, args.dependency_table, args.out, args.package_root, args.verify):
            assert_safe_cli_path(candidate)
        if args.verify is not None:
            verify_path = Path(args.verify)
            manifest = json.loads(verify_path.read_text(encoding="utf-8"))
            result = verify_manifest(args.root, manifest, package_root=args.package_root, expected_reviewed_table_sha256=args.expected_reviewed_table_sha256)
            print(json.dumps(result, sort_keys=True, indent=2))
            return 0

        table: Mapping[str, Any] = load_reviewed_table(args.package_root if args.package_root is not None else Path(__file__).resolve().parent, args.expected_reviewed_table_sha256)["dependencies"]
        if args.dependency_table is not None:
            table = json.loads(Path(args.dependency_table).read_text(encoding="utf-8"))
        package_root = args.package_root if args.package_root is not None else Path(__file__).resolve().parent
        pin_path = package_root / "wp7_environment_pin.json"
        pin: Any = json.loads(pin_path.read_text(encoding="utf-8")) if pin_path.is_file() else {}
        manifest = build_manifest(args.root, table, environment_pin=pin, package_root=package_root, expected_reviewed_table_sha256=args.expected_reviewed_table_sha256)
        validate_kernel_metadata_draft(manifest["kernel_metadata_draft"])
        out = args.out if args.out is not None else Path(__file__).resolve().parent / MANIFEST_NAME
        out.write_bytes(
            (json.dumps(manifest, sort_keys=True, indent=2, ensure_ascii=True) + "\n").encode("ascii")
        )
        print(json.dumps({"status": manifest["status"], "written": str(out)}, sort_keys=True, indent=2))
        return 0
    except (Wp7PackageError, OSError, ValueError) as exc:
        print("FAIL: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

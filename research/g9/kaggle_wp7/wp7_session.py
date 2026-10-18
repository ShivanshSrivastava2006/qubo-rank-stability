#!/usr/bin/env python3
"""WP7 non-scientific end-to-end Kaggle session script (DRAFT, NEVER RUN HERE).

This module is the session script that WOULD run on Kaggle for the WP7
non-scientific end-to-end dry run.  It is a DRAFT.  It is never executed
during package construction, fixtures or review; only a host-side dry
parse/import check with stand-ins is permitted.

It performs, strictly in this order:

  0. refuse to start unless every declared dependency is present, is a
     normalized repo-relative path that stays inside the root, and its
     content hash matches the recorded reviewed hash;
  1. capture the platform-reported identity;
  2. compare that identity with the environment pin -- any single field
     difference aborts BEFORE any computation (fail-closed);
  3. refuse unless a synthetic instance is offered and its payload declares
     no real data source;
  4. run the WP6b section-A corruption qualification plan;
  5. build the WP1 production identity and record it as a qualification
     candidate;
  6. run section-B item 1 (WP2), then open the SEALED OPTION A python
     reference, then run section-B item 2 (WP3) against that sealed reference
     on the SYNTHETIC instance only;
  7. run the production writer (WP4b) on synthetic ranges into a local
     output directory;
  8. emit only non-scientific counters, identities and digests per
     section-B item 3, plus a COMPLETE receipt.

SEALED REFERENCE (owner-approved OPTION A).  The session NEVER computes the
pure-Python reference itself.  ``open_sealed_reference`` reads a seal file
shipped with the package, hands it and the session inputs to
``stage2_reference_seal.open_for_session`` -- loaded from the dependency file
the dependency gate already hash-verified -- and receives a callable that
answers only what the seal contains.  The seal module re-verifies the whole
seal, the input hashes, the production identity and the coordinate census on
open, and refuses on any mismatch, so a tampered seal, a seal for another
instance, or a missing seal module is a typed refusal and never a fallback to
an in-session computation.  ``open_sealed_reference`` is a MANDATORY step:
a receipt that does not record it is refused.

ROUND 3 changes, all of them closing ways found by an independent validator
to produce a receipt that claimed nothing had been done:

  * COMPLETE OR NOT EMITTED.  ``RECEIPT_REQUIRED_FIELDS`` is the required
    field set of a receipt.  ``validate_receipt`` refuses a receipt missing
    any of them, and ``run_session`` only returns a receipt that passes it,
    so an incomplete receipt is never emitted.
  * NO STEP MAY BE "NOT RUN".  A receipt is refused unless every
    ``REQUIRED_STEPS`` entry appears in ``steps_executed``.  There is no
    ``*_not_run`` counter left: a session that cannot run a required step
    refuses instead of reporting a pass.
  * THE SYNTHETIC GATE IS A STEP.  It is a real step in the order, is
    mandatory, and its absence is a refusal, not a receipt that says the
    instance gate never ran.
  * ``synthetic: true`` MUST BE CORROBORATED.  The instance record must
    declare ``instance_kind``, ``synthetic`` and ``source``; the source must
    be a synthetic-generator marker.  A record that claims to be synthetic
    while naming a real dataset is refused.
  * PATH CONTAINMENT.  Every dependency path is normalized and confined to
    the root before any file is read; a symlink out of the root is refused.
  * TYPED ERRORS.  Every public entry point raises ``Wp7SessionError`` (or a
    subclass) for every wrong shape, including ``None``; no raw
    ``TypeError``/``AttributeError`` escapes.

Prohibitions enforced in code: no Kaggle CLI or API call, no credential
read, no network, no GPU allocation, no nvcc invocation at import time, and
refusal of any non-synthetic input.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
from pathlib import Path
from stat import S_ISREG
from typing import Any, Callable, Mapping, Sequence

MODULE_NAME = "wp7_session"
SCHEMA = "decisions_os/g9_wp7_session_receipt/v2"
MODE = "non_scientific_wp7_dry_run"

# Every value in this pin group must match the environment pin exactly.
PIN_GROUPS = ("platform_reported", "image_reported")

# These names are refused wherever they appear in a declared argument, so a
# credential path can never be opened and no Kaggle endpoint can be named.
FORBIDDEN_ARGUMENT_FRAGMENTS = (
    ".kaggle",
    "kaggle.json",
    "kaggle_api",
    "kaggleapi",
    "kaggle_cli",
    "kaggle.conf",
    "KAGGLE_KEY",
    "KAGGLE_USERNAME",
    "KAGGLE_SECRET",
    "KAGGLE_CONFIG",
    "access_token",
    "api_token",
    "credentials",
    "private_key",
    "secret",
)

# Real data sources an instance payload may not name while claiming to be
# synthetic.  Checked as lowercase substrings of the ``source`` field.
FORBIDDEN_SOURCE_FRAGMENTS = (
    "/mnt/kaggle",
    "kaggle input",
    "kaggle-input",
    "kaggle datasets",
    "kaggle competitions",
    "parquet",
    "hdf5",
    "h5py",
    "arrow",
    "feather",
    "duckdb",
    "sqlite",
    "postgres",
    "mysql",
    "s3://",
    "gs://",
    "https://",
    "http://",
    "ftp://",
)

# The only synthetic generators an instance payload may name.
ALLOWED_SOURCE_KINDS = ("synthetic_generator", "wp7_synthetic_generator")

# The only instance kinds this session accepts.  Anything else is refused.
SYNTHETIC_INSTANCE_KINDS = ("synthetic", "wp7_synthetic")

# The order the session runs in.  A receipt may not name a step outside it.
STEP_ORDER = (
    "dependency_gate",
    "capture_platform_identity",
    "compare_environment_pin",
    "synthetic_instance_gate",
    "wp6b_section_a_qualification_plan",
    "wp1_production_identity_candidate",
    "section_b_item_1_recheck_synthetic",
    "open_sealed_reference",
    "section_b_item_2_full_domain_synthetic",
    "wp4b_writer_synthetic_ranges",
    "emit_non_scientific_receipt",
)

# The steps that produce the work the receipt reports.  A receipt is refused
# unless every one of them actually executed.  ``open_sealed_reference`` is
# included because the section-B item 2 comparison must run against the sealed
# OPTION A reference, and that reference is opened here, not in-session.
REQUIRED_STEPS = (
    "dependency_gate",
    "capture_platform_identity",
    "compare_environment_pin",
    "synthetic_instance_gate",
    "wp6b_section_a_qualification_plan",
    "wp1_production_identity_candidate",
    "section_b_item_1_recheck_synthetic",
    "open_sealed_reference",
    "section_b_item_2_full_domain_synthetic",
    "wp4b_writer_synthetic_ranges",
)

# The steps a caller must inject.  The first three and the receipt step are
# performed by the session itself and are never injected.
REQUIRED_WP_DEPENDENCIES = (
    "research/g9/stage2_production_identity.py",
    "research/g9/stage2_section_b1_recheck.py",
    "research/g9/stage2_section_b2_harness.py",
    "research/g9/stage2_reference_seal.py",
    "research/g9/stage2_coordinate_records.py",
    "research/g9/stage2_production_writer.py",
    "research/g9/stage2_instance_preparation.py",
    "research/g9/stage2_d013_inactive_evaluator.py",
    "research/g9/cuda_qualification/stage2_cuda_d013_inactive.cu",
    "research/g9/cuda_qualification/stage2_cuda_d013_inactive.py",
)

# The module that owns the sealed OPTION A reference.  The session IMPORTS
# nothing from it by name at import time; it is loaded from the already
# hash-verified dependency file at run time and its absence is a refusal, so
# the session can never fall back to computing a reference in-session.
REFERENCE_SEAL_MODULE = "research/g9/stage2_reference_seal.py"

# The name the session requires the loaded seal module to expose.
REFERENCE_SEAL_OPENER = "open_for_session"

INJECTED_STEPS = (
    "synthetic_instance_gate",
    "wp6b_section_a_qualification_plan",
    "wp1_production_identity_candidate",
    "section_b_item_1_recheck_synthetic",
    "section_b_item_2_full_domain_synthetic",
    "wp4b_writer_synthetic_ranges",
)

# The required field set of a receipt.  A receipt missing any of these is
# refused; there is no partial receipt.
RECEIPT_REQUIRED_FIELDS = (
    "schema",
    "mode",
    "scientific_outputs",
    "scientific_output_count",
    "steps_executed",
    "counters",
    "identities",
    "digests",
    "differences",
    "push_authorized",
    "gpu_allocation_authorized",
    "package_status",
    "content_sha256",
)

# The keys a step's result mapping must carry to contribute a real report.
STEP_RESULT_KEYS = ("counters", "identities", "digests")

# Every top-level key of a step's result mapping must be one of these: a
# result may not smuggle a new top-level field into the receipt.
STEP_RESULT_ALLOWED_KEYS = STEP_RESULT_KEYS + ("status", "output")
KNOWN_EMPTY_OUTPUT_SHA256 = frozenset(hashlib.sha256(v).hexdigest() for v in (b"", b"null", b"\"\"", b"[]", b"{}"))

# A platform-reported value must be a plain JSON scalar; a list/dict here
# would only mean a probe mis-routed, so it is a difference.
MAX_REPORTED_DEPTH = 8

# Modules that must never be imported by, or present in, this process.
FORBIDDEN_IMPORT_ROOTS = ("kaggle", "kagglehub")
FORBIDDEN_IMPORT_MODULES = ("requests", "urllib.request", "http.client", "socket")

FORBIDDEN_ENVIRONMENT_PREFIXES = ("KAGGLE_",)


class Wp7SessionError(RuntimeError):
    """Typed refusal from the WP7 session script."""


class Wp7EnvironmentAbort(Wp7SessionError):
    """Fail-closed abort: the platform-reported identity differs from the pin."""


class Wp7DependencyError(Wp7SessionError):
    """A declared dependency is missing, altered, escaping the root, or unreviewed."""


class Wp7NonSyntheticRefusal(Wp7SessionError):
    """A non-synthetic instance, dataset or path was offered to the session."""


class Wp7ProhibitedOperationError(Wp7SessionError):
    """A prohibited operation (network, credential, CLI, nvcc) was requested."""


class Wp7IncompleteReceiptError(Wp7SessionError):
    """A receipt is missing a required field, so it is refused, not emitted."""


class Wp7StepNotRunError(Wp7SessionError):
    """A required step did not run, so no receipt may be emitted."""


class Wp7StepResultError(Wp7SessionError):
    """A step's result is not shaped the way the receipt requires."""


class Wp7PathError(Wp7SessionError):
    """A path is not a normalized, contained, repo-relative file path."""


def _require(condition: object, message: str) -> None:
    if not condition:
        raise Wp7SessionError(message)


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise Wp7SessionError(f"{label} must be a dict")
    for key in value:
        if not isinstance(key, str):
            raise Wp7SessionError(f"{label} keys must be strings")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise Wp7SessionError(f"{label} must be a string")
    return value


def _sequence(value: object, label: str) -> list[Any]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, (list, tuple)):
        raise Wp7SessionError(f"{label} must be a list")
    return list(value)


def _flat_text(value: object, label: str) -> str:
    text = _text(value, label)
    lowered = text.lower()
    for fragment in FORBIDDEN_ARGUMENT_FRAGMENTS:
        if fragment.lower() in lowered:
            raise Wp7ProhibitedOperationError(
                f"{label} names a credential or prohibited endpoint: {fragment}"
            )
    return text


def canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
        ).encode("ascii")
    except (TypeError, ValueError) as exc:
        raise Wp7SessionError(f"value is not canonicalizable: {exc}") from exc


def content_sha256(value: Any) -> str:
    if not isinstance(value, dict):
        raise Wp7SessionError("content_sha256 input must be a dict")
    for key in value:
        if not isinstance(key, str):
            raise Wp7SessionError(f"content_sha256 input keys must be strings: {key!r}")
    body = dict(value)
    body.pop("content_sha256", None)
    return hashlib.sha256(canonical_bytes(body)).hexdigest()


def sha256_file(path: Path) -> str:
    """Digest of a file, read through the typed trust-boundary helper.

    The round-3 ``isinstance(path, Path)`` guard is KEPT here as well as in
    ``read_bytes_at_boundary``: it is the check the validated round 3 shipped,
    and removing a validated guard is forbidden.  The shared helper still
    refuses a non-Path, so the duplication costs nothing and the round-3
    invariant is restored verbatim.
    """
    if not isinstance(path, Path):
        raise Wp7SessionError("sha256_file path must be a Path")
    return hashlib.sha256(read_bytes_at_boundary(path, "sha256_file input")).hexdigest()


def read_bytes_at_boundary(path: Path, label: str) -> bytes:
    """The ONE helper every trust-boundary file read goes through.

    A path handed in by a caller, a manifest or a dependency table is not
    trustworthy, so the read itself is a trust boundary: it can fail with
    ``OSError`` (missing, unreadable, a directory, a broken or looping
    symlink, an I/O error) and a decode can fail with ``UnicodeError``, while
    a JSON parse fails with ``ValueError``/``json.JSONDecodeError``.  Each of
    those specific classes is converted into this module's typed error with
    ``from`` so the original is preserved as ``__cause__`` and nothing untyped
    escapes a public entry point.

    ``BaseException`` is deliberately NOT caught: ``KeyboardInterrupt``,
    ``SystemExit`` and ``MemoryError`` must still propagate.
    """
    if not isinstance(label, str):
        raise Wp7SessionError("boundary read label must be a string")
    if not isinstance(path, Path):
        raise Wp7SessionError(f"{label} must be a Path")
    try:
        return path.read_bytes()
    except (OSError, UnicodeError, ValueError) as exc:
        raise Wp7SessionError(f"cannot read {label} at {path}: {exc}") from exc


def read_text_at_boundary(path: Path, label: str) -> str:
    """Typed sibling of :func:`read_bytes_at_boundary` for decoded text."""
    raw = read_bytes_at_boundary(path, label)
    try:
        return raw.decode("utf-8")
    except (UnicodeError, ValueError) as exc:
        raise Wp7SessionError(f"cannot decode {label} at {path}: {exc}") from exc


def read_json_at_boundary(path: Path, label: str) -> Any:
    """Typed sibling of :func:`read_text_at_boundary` for JSON documents.

    A ``json.JSONDecodeError`` is a ``ValueError`` subclass, so it is covered
    by the same conversion; it is named here for the reader's benefit.
    """
    import json as _json

    text = read_text_at_boundary(path, label)
    try:
        return _json.loads(text)
    except (_json.JSONDecodeError, ValueError, UnicodeError) as exc:
        raise Wp7SessionError(f"cannot parse {label} at {path}: {exc}") from exc


# --------------------------------------------------------------------------
# 0a. Prohibitions
# --------------------------------------------------------------------------
def assert_no_prohibited_imports() -> None:
    """Refuse if a Kaggle/network module is already imported in this process.

    Only a module whose ROOT is ``kaggle``/``kagglehub``, or a module named
    exactly one of ``FORBIDDEN_IMPORT_MODULES`` while it is NOT this
    interpreter's own bootstrap machinery, is a violation.
    """
    bootstrap = set(getattr(sys, "builtin_module_names", ()))
    for name in list(sys.modules):
        if name is None:
            continue
        root = name.split(".")[0]
        if root in FORBIDDEN_IMPORT_ROOTS or (name in FORBIDDEN_IMPORT_MODULES and name not in bootstrap):
            raise Wp7ProhibitedOperationError(
                f"prohibited module is imported in this process: {name}"
            )


def assert_no_credential_environment() -> None:
    """Refuse if a credential-bearing environment variable is present.

    This reads only the NAMES of variables matching the credential prefixes,
    never their values, and never reads any credential file.
    """
    for key in os.environ:
        for prefix in FORBIDDEN_ENVIRONMENT_PREFIXES:
            if key.startswith(prefix):
                raise Wp7ProhibitedOperationError(
                    "credential-bearing environment variable is present: " + key
                )


# --------------------------------------------------------------------------
# 0b. Path containment
# --------------------------------------------------------------------------
def normalize_relative_path(value: object, label: str) -> str:
    """Return the normalized repo-relative form, or refuse.

    Refuses empty, absolute, drive-qualified, backslash-separated, NUL
    bearing, non-normalized and parent-relative ("..") paths.  Purely
    lexical: nothing is opened here.
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
    if text.startswith("/") or os.path.isabs(text):
        raise Wp7PathError(f"{label} must be repo-relative, not absolute: {text!r}")
    if ":" in text.split("/")[0]:
        raise Wp7PathError(f"{label} must be repo-relative, not drive-qualified: {text!r}")
    for part in text.split("/"):
        if part == "":
            raise Wp7PathError(f"{label} must be normalized (empty path component): {text!r}")
        if part == ".":
            raise Wp7PathError(f"{label} must be normalized (a '.' component): {text!r}")
        if part == "..":
            raise Wp7PathError(f"{label} must not contain a '..' component: {text!r}")
    if text != os.path.normpath(text):
        raise Wp7PathError(f"{label} is not normalized: {text!r}")
    return text


def resolve_inside_root(root: Path, relative: object, label: str) -> Path:
    """Resolve a repo-relative path to a real regular file inside ``root``.

    Refuses a missing file, a directory or any symlink whose real target
    leaves the root.  The containment test is on the fully resolved path, so
    a symlink chain cannot smuggle a read out of the tree.
    """
    if not isinstance(root, Path):
        raise Wp7SessionError("root must be a Path")
    rel = normalize_relative_path(relative, label)
    root_real = Path(os.path.realpath(str(root)))
    real = Path(os.path.realpath(str(root / rel)))
    try:
        real.relative_to(root_real)
    except ValueError as exc:
        raise Wp7PathError(f"{label} resolves outside the root: {rel!r}") from exc
    if real == root_real:
        raise Wp7PathError(f"{label} resolves to the root itself: {rel!r}")
    if not real.exists():
        raise Wp7PathError(f"{label} does not exist in the tree: {rel!r}")
    # BOTH round-3 checks are kept.  ``is_file()`` follows symlinks and so is
    # the weaker of the two; ``S_ISREG`` is the authoritative mode test that
    # also refuses a FIFO, socket or device that ``exists()`` alone accepts.
    # The validated round 3 shipped both and neither is removed here.
    if not real.is_file():
        raise Wp7PathError(f"{label} is not a regular file: {rel!r}")
    if not S_ISREG(real.stat().st_mode):
        raise Wp7PathError(f"{label} is not a regular file: {rel!r}")
    return real


def resolve_dir_inside_root(root: Path, directory: Path) -> Path:
    """Resolve an output directory that must live inside ``root``.

    The containment test is on the fully resolved path, so a symlinked
    output directory cannot be used to write outside the tree.
    """
    if not isinstance(root, Path):
        raise Wp7SessionError("root must be a Path")
    if not isinstance(directory, Path):
        raise Wp7SessionError("output_dir must be a Path or None")
    root_real = Path(os.path.realpath(str(root)))
    real = Path(os.path.realpath(str(directory)))
    try:
        real.relative_to(root_real)
    except ValueError as exc:
        raise Wp7PathError(f"output_dir resolves outside the root: {str(directory)!r}") from exc
    if real == root_real:
        raise Wp7PathError("output_dir resolves to the root itself; give a subdirectory")
    if not real.is_dir():
        raise Wp7PathError(f"output_dir is not a directory: {str(directory)!r}")
    return real


# --------------------------------------------------------------------------
# 0c. Dependency gate
# --------------------------------------------------------------------------
def resolve_dependencies(
    root: Path, table: Mapping[str, Any]
) -> dict[str, str]:
    """Return {relative_path: sha256} for every present, reviewed dependency.

    Refuses when a dependency path is not a normalized repo-relative path
    inside the root, when the dependency is missing, when its recorded
    reviewed hash is "PENDING", or when its current content hash differs from
    the recorded reviewed hash.  The session therefore cannot run against
    unreviewed or changed code, nor read anything outside the tree.
    """
    if not isinstance(root, Path):
        raise Wp7SessionError("root must be a Path")
    if not root.is_dir():
        raise Wp7SessionError(f"root is not a directory: {str(root)!r}")
    dependencies = _mapping(table, "dependency table")
    if len(dependencies) == 0:
        raise Wp7SessionError("dependency table is empty")
    resolved: dict[str, str] = {}
    problems: list[str] = []
    for relative in sorted(dependencies):
        recorded = dependencies[relative]
        try:
            _flat_text(relative, "dependency path")
            _text(recorded, f"recorded hash for {relative!r}")
        except Wp7ProhibitedOperationError:
            # A credential path keeps its own precise type: it is a
            # prohibited operation, not merely a dependency problem.
            raise
        except Wp7SessionError as exc:
            raise Wp7DependencyError(f"{relative!r}: {exc}") from exc
        if recorded == "PENDING":
            problems.append(f"{relative}: review PENDING")
            continue
        if len(recorded) != 64 or any(c not in "0123456789abcdef" for c in recorded):
            problems.append(f"{relative}: recorded hash is not a lowercase sha256")
            continue
        try:
            real = resolve_inside_root(root, relative, f"dependency path {relative!r}")
        except Wp7PathError as exc:
            problems.append(f"{relative}: {exc}")
            continue
        current = sha256_file(real)
        if current != recorded:
            problems.append(
                f"{relative}: hash mismatch recorded={recorded} current={current}"
            )
            continue
        resolved[relative] = current
    if problems:
        raise Wp7DependencyError("; ".join(problems))
    return resolved


# --------------------------------------------------------------------------
# 0d. Sealed OPTION A reference (opened, never computed in-session)
# --------------------------------------------------------------------------
def _load_seal_module(root: Path, resolved: Mapping[str, Any]) -> Any:
    """Load the reviewed seal module from the already hash-verified tree.

    The seal module is loaded by file path with its own isolated name, so the
    session never falls back to a copy that is not the one the dependency
    gate just hashed.  Any failure -- missing entry, unreadable file, a module
    that does not expose the opener -- is a refusal.

    There is deliberately no root-type check of its own: ``resolve_inside_root``
    runs first and refuses a non-Path with the same typed error, and the
    mutation sweep showed a duplicate here is unreachable.
    """
    table = _mapping(resolved, "resolved dependencies")
    if REFERENCE_SEAL_MODULE not in table:
        raise Wp7DependencyError(
            f"the sealed reference module {REFERENCE_SEAL_MODULE} was not resolved by the dependency gate"
        )
    real = resolve_inside_root(root, REFERENCE_SEAL_MODULE, "reference seal module")
    import importlib.util

    spec = importlib.util.spec_from_file_location("wp7_reference_seal", str(real))
    if spec is None or spec.loader is None:
        raise Wp7DependencyError("the reference seal module has no import spec")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        raise Wp7DependencyError(f"the reference seal module did not load: {exc}") from exc
    return module


def open_sealed_reference(
    root: Path,
    resolved: Mapping[str, Any],
    sealed_path: object,
    seal_inputs: Mapping[str, Any],
) -> dict[str, Any]:
    """Open the sealed OPTION A reference and return the callable plus its digest.

    The session NEVER computes the pure-Python reference itself.  It reads a
    seal file that shipped with the package, hands it and the session inputs to
    ``stage2_reference_seal.open_for_session``, and receives a callable that
    answers only what the seal contains.  The seal module itself re-verifies
    the whole seal on open and refuses on any mismatch, so a tampered or
    wrong-instance seal can never yield a reference.

    There is deliberately no root-type check of its own: ``resolve_inside_root``
    runs one line below and refuses a non-Path with the same typed error, and
    the mutation sweep showed a duplicate here is unreachable.
    """
    seal_real = resolve_inside_root(root, sealed_path, "sealed reference")
    sealed_bytes = read_bytes_at_boundary(seal_real, "sealed reference")
    if len(sealed_bytes) == 0:
        raise Wp7DependencyError("the sealed reference file is empty")
    inputs = _mapping(seal_inputs, "seal inputs")
    for field in ("coordinates", "production_identity_hash"):
        if field not in inputs:
            raise Wp7DependencyError(f"seal inputs do not declare {field}")
    module = _load_seal_module(root, resolved)
    opener = getattr(module, REFERENCE_SEAL_OPENER, None)
    if not callable(opener):
        raise Wp7DependencyError(
            f"the reference seal module does not expose a callable {REFERENCE_SEAL_OPENER}"
        )
    try:
        reference = opener(sealed_bytes, inputs)
    except Exception as exc:
        raise Wp7DependencyError(f"the sealed reference did not open: {exc}") from exc
    if not callable(reference):
        raise Wp7DependencyError("the opened sealed reference is not callable")
    return {
        "python_reference": reference,
        "sealed_reference_sha256": hashlib.sha256(sealed_bytes).hexdigest(),
        "sealed_reference_bytes": len(sealed_bytes),
    }


# --------------------------------------------------------------------------
# 1. Platform identity capture (PLATFORM-REPORTED, never proof)
# --------------------------------------------------------------------------
def _probe_callable(probe: object, label: str) -> Mapping[str, Any]:
    if probe is not None and not callable(probe):
        raise Wp7SessionError(f"{label} probe must be callable or None")
    if probe is None:
        return {}
    observed = probe()
    return _mapping(observed, f"{label} probe result")


def _assert_reportable(value: object, label: str, depth: int) -> None:
    """A platform-reported value must be a plain JSON scalar or a shallow map.

    Lists are refused: a list here means a probe mis-routed, and comparing it
    field by field would silently skip its contents.
    """
    if not isinstance(depth, int) or isinstance(depth, bool):
        # A non-integer depth would make the comparison below raise a raw
        # TypeError out of a public entry point instead of a typed refusal.
        raise Wp7EnvironmentAbort(f"{label} nesting depth must be an integer")
    if depth > MAX_REPORTED_DEPTH:
        raise Wp7EnvironmentAbort(f"{label} is nested deeper than the reported identity allows")
    if isinstance(value, dict):
        for key in value:
            if not isinstance(key, str):
                raise Wp7EnvironmentAbort(f"{label} key {key!r} is not a field name")
            _assert_reportable(value[key], f"{label}.{key}", depth + 1)
        return
    if isinstance(value, list):
        raise Wp7EnvironmentAbort(f"{label} is a list; a platform-reported field must be a scalar or a map")
    if not isinstance(value, (str, int, float, bool)) and value is not None:
        raise Wp7EnvironmentAbort(f"{label} is not a JSON scalar")


def capture_platform_identity(probes: Mapping[str, Callable[[], Any]] | None) -> dict[str, Any]:
    """Capture the platform-reported identity as PLATFORM-REPORTED values."""
    if probes is not None and not isinstance(probes, dict):
        raise Wp7SessionError("probes must be a dict or None")
    table = _mapping(probes if probes is not None else {}, "probes")
    identity: dict[str, Any] = {
        "provenance": "PLATFORM-REPORTED",
        "is_proof": False,
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "machine": platform.machine(),
    }
    for name in sorted(table):
        captured = _probe_callable(table[name], name)
        _assert_reportable(captured, f"probe {name}", 0)
        identity[name] = captured
    return identity


# --------------------------------------------------------------------------
# 2. Environment-pin comparison (fail-closed, before any computation)
# --------------------------------------------------------------------------
def _flatten(value: object, prefix: str = "", depth: int = 0) -> dict[str, Any]:
    if depth > MAX_REPORTED_DEPTH:
        raise Wp7EnvironmentAbort("platform-reported identity is nested too deeply to compare")
    flat: dict[str, Any] = {}
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise Wp7EnvironmentAbort("platform-reported keys must be strings")
        for key in sorted(value):
            child = f"{prefix}.{key}" if prefix else key
            flat.update(_flatten(value[key], child, depth + 1))
    else:
        flat[prefix] = value
    return flat


def _pinned_fields(pin: Mapping[str, Any]) -> dict[str, Any]:
    # The membership test below (``group not in pin``) raises a raw TypeError
    # on a non-container, so the mapping is required HERE rather than assumed
    # from the caller.
    pin_map = _mapping(pin, "environment pin")
    pinned: dict[str, Any] = {}
    for group in PIN_GROUPS:
        if group not in pin_map:
            raise Wp7SessionError(f"environment pin is missing the {group} group")
        pinned.update(_flatten(_mapping(pin_map[group], f"pin group {group}"), group))
    if len(pinned) == 0:
        raise Wp7SessionError("environment pin contains no comparable fields")
    return pinned


def compare_environment_pin(observed: Mapping[str, Any], pin: Mapping[str, Any]) -> dict[str, Any]:
    """Compare every pinned field.  ANY difference is a fail-closed abort.

    A missing field, a field of a different type, a value difference, an
    extra reported field, and a reported value that is a list are all
    differences.  An empty comparison is the only pass.
    """
    observed_map = _mapping(observed, "observed identity")
    pin_map = _mapping(pin, "environment pin")
    if len(pin_map) == 0:
        raise Wp7SessionError("environment pin is empty")
    pinned = _pinned_fields(pin_map)
    observed_flat = _flatten(observed_map)

    differences: list[str] = []
    for field in sorted(pinned):
        expected = pinned[field]
        if field not in observed_flat:
            differences.append(f"{field}: ABSENT (pinned {expected!r})")
            continue
        actual = observed_flat[field]
        if isinstance(actual, list):
            differences.append(f"{field}: list-valued, expected {expected!r}")
            continue
        if type(actual) is not type(expected) or actual != expected:
            differences.append(
                f"{field}: expected {expected!r} ({type(expected).__name__}) "
                f"got {actual!r} ({type(actual).__name__})"
            )
    # An extra reported field is a difference only WITHIN a pinned group; the
    # session's own base capture metadata is not part of the platform identity.
    for group in PIN_GROUPS:
        if group not in observed_map:
            continue
        group_map = _mapping(observed_map[group], f"observed {group}")
        for field in sorted(_flatten(group_map, group)):
            if field not in pinned:
                differences.append(f"{field}: EXTRA reported field not present in the pin")

    if differences:
        raise Wp7EnvironmentAbort(
            "platform-reported identity differs from the environment pin (fail-closed): "
            + "; ".join(differences)
        )
    return {
        "comparison": "exact_match",
        "compared_fields": len(pinned),
        "provenance": "PLATFORM-REPORTED",
        "difference_count": 0,
    }


# --------------------------------------------------------------------------
# 3. Synthetic-input gate
# --------------------------------------------------------------------------
def _assert_synthetic_source(source: object) -> str:
    """A synthetic claim must name a permitted generator, and only that.

    The generator is checked first, so a credential path is reported by the
    credential guard rather than being laundered into a source classification.
    """
    text = _text(source, "instance source")
    if text.strip() == "":
        raise Wp7NonSyntheticRefusal("instance record declares an empty source")
    _flat_text(text, "instance source")
    lowered = text.lower()
    for fragment in FORBIDDEN_SOURCE_FRAGMENTS:
        if fragment in lowered:
            raise Wp7NonSyntheticRefusal(
                f"instance claims to be synthetic but its source names a real data source: {fragment}"
            )
    for allowed in ALLOWED_SOURCE_KINDS:
        if allowed in lowered:
            return allowed
    raise Wp7NonSyntheticRefusal(
        f"instance source {text!r} is not one of the permitted synthetic generators {list(ALLOWED_SOURCE_KINDS)}"
    )


def assert_synthetic_instance(instance: Mapping[str, Any]) -> Mapping[str, Any]:
    """Refuse any non-synthetic instance.  A session may run only synthetic.

    The record must declare ``instance_kind`` (a synthetic kind),
    ``synthetic`` (literally True) and ``source`` (a synthetic generator that
    names no real data).  Declaring synthetic while naming a real dataset is
    refused.
    """
    record = _mapping(instance, "instance")
    if len(record) == 0:
        raise Wp7NonSyntheticRefusal("instance record is empty")
    if "instance_kind" not in record:
        raise Wp7NonSyntheticRefusal("instance record does not declare instance_kind")
    kind = _text(record["instance_kind"], "instance_kind")
    if kind not in SYNTHETIC_INSTANCE_KINDS:
        raise Wp7NonSyntheticRefusal(
            f"refusing non-synthetic instance_kind {kind!r}; only {list(SYNTHETIC_INSTANCE_KINDS)} is permitted"
        )
    if record.get("synthetic") is not True:
        raise Wp7NonSyntheticRefusal(
            "instance record does not assert synthetic=true; refusing as non-synthetic"
        )
    if "source" not in record:
        raise Wp7NonSyntheticRefusal(
            "instance record does not declare source; a synthetic claim must be corroborated"
        )
    source_kind = _assert_synthetic_source(record["source"])
    for key in sorted(record):
        _flat_text(str(record[key]), f"instance field {key}")
    result = dict(record)
    result["source_kind"] = source_kind
    return result


# --------------------------------------------------------------------------
# 4. Step results
# --------------------------------------------------------------------------
def _classify_step_result(name: str, result: object) -> dict[str, Any]:
    """A step result must be a mapping of the declared keys to plain maps.

    A result may not be empty, may not carry a key outside the declared set,
    may not claim a non-ok status, and may not nest anything but strings and
    numbers -- so no value can hide a list of "scientific outputs" or a
    credential path inside the receipt.
    """
    table = _mapping(result, f"step result {name}")
    if len(table) == 0:
        raise Wp7StepResultError(f"step {name} returned an empty result")
    for key in table:
        if key not in STEP_RESULT_ALLOWED_KEYS:
            raise Wp7StepResultError(
                f"step {name} returned key {key!r} outside the permitted set {list(STEP_RESULT_ALLOWED_KEYS)}"
            )
    status = table.get("status")
    if status is not None and status != "ok":
        raise Wp7StepResultError(f"step {name} reported status {status!r}, not 'ok'")
    # counters and digests merge straight into the receipt, so every value
    # must be a plain scalar: nothing may hide a list of "scientific outputs"
    # or a credential path inside the receipt.  identities carries nested
    # structures, so only its KEY NAMES are checked here.
    for key in ("counters", "digests"):
        if key in table:
            _require_scalar_map(table[key], f"step {name} {key}")
    if "identities" in table:
        _require_str_keyed_map(table["identities"], f"step {name} identities")
    if "output" not in table:
        raise Wp7StepResultError(f"step {name} produced no output")
    output_bytes = canonical_bytes(table["output"])
    if hashlib.sha256(output_bytes).hexdigest() in KNOWN_EMPTY_OUTPUT_SHA256:
        raise Wp7StepResultError(f"step {name} produced known-empty output")
    return dict(table)


def _require_str_keyed_map(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise Wp7StepResultError(f"{label} must be a dict")
    table: Mapping[str, Any] = value
    for key in table:
        if not isinstance(key, str):
            raise Wp7StepResultError(f"{label} key {key!r} is not a field name")
    return table


def _require_scalar_map(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise Wp7StepResultError(f"{label} must be a dict")
    table: Mapping[str, Any] = value
    for key in table:
        if not isinstance(key, str):
            raise Wp7StepResultError(f"{label} key {key!r} is not a field name")
        if not isinstance(table[key], (str, int, float, bool)) and table[key] is not None:
            raise Wp7StepResultError(f"{label} value for {key!r} must be a string or a number")
    return table


# --------------------------------------------------------------------------
# 5. Receipt: complete, or not emitted
# --------------------------------------------------------------------------
def build_receipt(
    *,
    steps: Sequence[str],
    counters: Mapping[str, Any],
    identities: Mapping[str, Any],
    digests: Mapping[str, Any],
    differences: Sequence[str],
) -> dict[str, Any]:
    """Assemble the section-B item-3 receipt: counters, identities, digests only.

    A receipt is only ever returned when every required step ran and every
    required field is present; ``validate_receipt`` is the gate.
    """
    ran = _text_sequence(steps, "steps")
    if len(ran) == 0:
        raise Wp7SessionError("receipt claims no executed step")
    unknown = [name for name in ran if name not in STEP_ORDER]
    if unknown:
        raise Wp7SessionError(f"receipt names steps outside the WP7 order: {unknown}")
    ordered = [name for name in STEP_ORDER if name in set(ran)]
    if ordered != ran:
        raise Wp7SessionError("receipt steps are not in the declared WP7 order")
    missing = [name for name in REQUIRED_STEPS if name not in set(ordered)]
    if missing:
        raise Wp7StepNotRunError(
            "receipt would be incomplete: these required steps did not run: " + ", ".join(missing)
        )
    counter_map = _require_scalar_map(counters, "counters")
    identity_map = _mapping(identities, "identities")
    digest_map = _require_scalar_map(digests, "digests")
    difference_list = _text_sequence(differences, "differences")
    receipt: dict[str, Any] = {
        "schema": SCHEMA,
        "mode": MODE,
        "scientific_outputs": [],
        "scientific_output_count": 0,
        "steps_executed": ordered,
        "counters": dict(counter_map),
        "identities": dict(identity_map),
        "digests": dict(digest_map),
        "differences": list(difference_list),
        "push_authorized": False,
        "gpu_allocation_authorized": False,
        "package_status": "draft_not_approved_for_push",
    }
    receipt["content_sha256"] = content_sha256(receipt)
    return validate_receipt(receipt)


def _text_sequence(value: object, label: str) -> list[str]:
    if not isinstance(value, (list, tuple)) or isinstance(value, (str, bytes, bytearray)):
        raise Wp7SessionError(f"{label} must be a list")
    out: list[str] = []
    for item in value:
        out.append(_text(item, f"{label} entry"))
    return out


def validate_receipt(receipt: Mapping[str, Any]) -> Mapping[str, Any]:
    """Refuse any receipt that is not complete.

    This is the completeness gate the owner's condition needs: a missing
    required field refuses instead of being emitted with a hole in it.
    """
    table = _mapping(receipt, "receipt")
    missing = [field for field in RECEIPT_REQUIRED_FIELDS if field not in table]
    if missing:
        raise Wp7IncompleteReceiptError(
            "receipt is incomplete; these required fields are absent: " + ", ".join(missing)
        )
    if table.get("schema") != SCHEMA:
        raise Wp7IncompleteReceiptError(f"receipt schema must be {SCHEMA!r}")
    if table.get("mode") != MODE:
        raise Wp7IncompleteReceiptError(f"receipt mode must be {MODE!r}")
    for field in ("scientific_outputs", "steps_executed", "differences"):
        _sequence(table[field], f"receipt {field}")
    if len(table["scientific_outputs"]) != 0:
        raise Wp7IncompleteReceiptError("a non-scientific receipt may carry no scientific outputs")
    if table.get("scientific_output_count") != 0:
        raise Wp7IncompleteReceiptError("scientific_output_count must be 0")
    for field in ("push_authorized", "gpu_allocation_authorized"):
        if table.get(field) is not False:
            raise Wp7IncompleteReceiptError(f"receipt {field} must be False")
    _text(table.get("package_status"), "receipt package_status")
    for field in ("counters", "identities", "digests"):
        if not isinstance(table[field], dict):
            raise Wp7IncompleteReceiptError(f"receipt {field} must be a dict")
    digest_map = _require_scalar_map(table["digests"], "receipt digests")
    for name in REQUIRED_STEPS:
        value = digest_map.get(f"step:{name}")
        if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            raise Wp7IncompleteReceiptError(f"receipt has no output hash for step {name}")
    ran = _text_sequence(table["steps_executed"], "receipt steps_executed")
    absent = [name for name in REQUIRED_STEPS if name not in set(ran)]
    if absent:
        raise Wp7StepNotRunError(
            "receipt is incomplete: these required steps are absent: " + ", ".join(absent)
        )
    if table.get("content_sha256") != content_sha256(table):
        raise Wp7IncompleteReceiptError("receipt content_sha256 does not match its body")
    return table


# --------------------------------------------------------------------------
# 6. The session, in order
# --------------------------------------------------------------------------
def _validate_step_table(steps: object) -> Mapping[str, Any]:
    if steps is None:
        raise Wp7StepNotRunError(
            "steps is None; the synthetic gate and every required step must be supplied, "
            "so the session cannot be complete"
        )
    table = _mapping(steps, "steps")
    for name in table:
        if name not in STEP_ORDER:
            raise Wp7SessionError(f"unknown step supplied: {name}")
    absent = [name for name in INJECTED_STEPS if name not in table]
    if absent:
        raise Wp7StepNotRunError(
            "these required steps were not supplied, so the session cannot be complete: "
            + ", ".join(absent)
        )
    for name in sorted(table):
        if not callable(table[name]):
            raise Wp7SessionError(f"step {name} is not callable")
    return table


def run_session(
    *,
    root: Path,
    dependency_table: Mapping[str, Any],
    environment_pin: Mapping[str, Any],
    probes: Mapping[str, Callable[[], Any]] | None = None,
    instance: Mapping[str, Any] | None = None,
    output_dir: Path | None = None,
    steps: Mapping[str, Callable[[], Mapping[str, Any]]] | None = None,
    sealed_reference_path: object = None,
    seal_inputs: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute the WP7 dry-run session in the declared order, fail-closed.

    Every step callable is injected so the session can be exercised with
    stand-ins offline.  A required step that is absent is a REFUSAL, never a
    "not run" counter, and the receipt is returned only after
    ``validate_receipt`` accepts it, so an incomplete receipt is never
    emitted.

    The section-B item 2 comparison is handed the python reference opened from
    the sealed OPTION A reference file, never an in-session computation.
    """
    if not isinstance(root, Path):
        raise Wp7SessionError("root must be a Path")
    if output_dir is not None and not isinstance(output_dir, Path):
        raise Wp7SessionError("output_dir must be a Path or None")
    checked_instance = assert_synthetic_instance(instance)
    resolve_dir_inside_root(root, output_dir)
    before_files = {str(p.relative_to(output_dir)): sha256_file(p)
                    for p in output_dir.rglob("*") if p.is_file()}
    dependency_map = _mapping(dependency_table, "dependency table")
    missing_wp = [name for name in REQUIRED_WP_DEPENDENCIES if name not in dependency_map]
    if missing_wp:
        raise Wp7DependencyError("required WP modules missing from dependency table: " + ", ".join(missing_wp))
    _mapping(environment_pin, "environment pin")
    table = _validate_step_table(steps)

    # 0. prohibitions and dependency gate, before anything else.
    assert_no_prohibited_imports()
    assert_no_credential_environment()
    resolved = resolve_dependencies(root, dependency_table)

    counters: dict[str, Any] = {}
    identities: dict[str, Any] = {"dependencies": dict(resolved)}
    digests: dict[str, Any] = {"step:dependency_gate": content_sha256({"dependencies": resolved})}
    differences: list[str] = []
    executed: list[str] = ["dependency_gate"]

    # 1. capture the platform-reported identity.
    observed = capture_platform_identity(probes)
    digests["step:capture_platform_identity"] = content_sha256({"observed": observed})
    executed.append("capture_platform_identity")

    # 2. compare with the pin; a difference aborts before any computation.
    pin_result = compare_environment_pin(observed, environment_pin)
    digests["environment_pin_comparison"] = content_sha256(pin_result)
    counters["environment_pin_fields_compared"] = pin_result["compared_fields"]
    digests["step:compare_environment_pin"] = content_sha256({"comparison": pin_result})
    executed.append("compare_environment_pin")

    # 3..8 the injected steps, each recorded as executed only after its own
    # result has been accepted.  Between section-B item 1 and section-B item 2
    # the sealed OPTION A reference is opened, so item 2 can never compare
    # against a reference the session computed for itself.  The branch below
    # both opens the seal and passes the reference, so there is no window in
    # which item 2 can run with ``python_reference`` still None.
    for name in INJECTED_STEPS:
        if name == "section_b_item_2_full_domain_synthetic":
            opened = open_sealed_reference(root, resolved, sealed_reference_path, seal_inputs)
            python_reference = opened["python_reference"]
            digests["sealed_reference_sha256"] = opened["sealed_reference_sha256"]
            counters["sealed_reference_bytes"] = opened["sealed_reference_bytes"]
            digests["step:open_sealed_reference"] = content_sha256(
                {"sealed_reference_sha256": opened["sealed_reference_sha256"]}
            )
            executed.append("open_sealed_reference")
        try:
            if name == "section_b_item_2_full_domain_synthetic":
                raw_result = table[name](python_reference)
            else:
                raw_result = table[name]()
        except Exception as exc:
            raise Wp7StepResultError(f"step {name} failed: {exc}") from exc
        step_result = _classify_step_result(name, raw_result)
        digests[f"step:{name}"] = hashlib.sha256(canonical_bytes(step_result["output"])).hexdigest()
        executed.append(name)
        for key in STEP_RESULT_KEYS:
            if key not in step_result:
                continue
            for field in sorted(step_result[key]):
                if key == "counters":
                    counters[field] = step_result[key][field]
                elif key == "identities":
                    identities[field] = step_result[key][field]
                else:
                    digests[field] = step_result[key][field]
        if name == "synthetic_instance_gate":
            # The gate's own output is the instance record, so a step that
            # returns none of it can never yield a complete receipt.
            if "identities" not in step_result or "instance" not in step_result["identities"]:
                raise Wp7IncompleteReceiptError(
                    "the synthetic instance gate did not report an instance; no receipt can be complete"
                )
            reported_instance = assert_synthetic_instance(step_result["identities"]["instance"])
            if {k: v for k, v in reported_instance.items() if k != "source_kind"} != {k: v for k, v in checked_instance.items() if k != "source_kind"}:
                raise Wp7NonSyntheticRefusal("synthetic gate instance differs from caller instance")
            identities["instance"] = reported_instance
            counters["instance_is_synthetic"] = 1

    # Require a new or changed nonempty file from the writer step.
    actual_files = [p for p in output_dir.rglob("*") if p.is_file() and p.stat().st_size > 0]
    changed_files = {str(p.relative_to(output_dir)): sha256_file(p) for p in actual_files
                     if before_files.get(str(p.relative_to(output_dir))) != sha256_file(p)}
    if not changed_files:
        raise Wp7StepNotRunError("writer produced no new nonempty output file")
    counters["output_dir_written"] = len(changed_files)
    digests["output_files_sha256"] = content_sha256(changed_files)

    receipt = build_receipt(
        steps=executed,
        counters=counters,
        identities=identities,
        digests=digests,
        differences=differences,
    )
    return validate_receipt(receipt)


def parse_args(argv: Sequence[str] | None = None) -> Any:
    """Parse the session's command line.  Exposed for host-side dry checks."""
    import argparse

    parser = argparse.ArgumentParser(description="WP7 draft session (not authorized to run).")
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--dependency-table", required=True, type=Path)
    parser.add_argument("--environment-pin", required=True, type=Path)
    parser.add_argument("--instance", type=Path)
    parser.add_argument("--output-dir", type=Path)
    return parser.parse_args(_sequence(argv, "argv") if argv is not None else None)


def assert_safe_cli_path(value: object) -> None:
    if value is None:
        return
    if not isinstance(value, Path):
        raise Wp7PathError("CLI path must be a Path")
    _flat_text(str(value), "CLI path")


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        for candidate in (args.root, args.dependency_table, args.environment_pin, args.instance, args.output_dir):
            assert_safe_cli_path(candidate)
        environment_pin = json.loads(Path(args.environment_pin).read_text(encoding="utf-8"))
        table = json.loads(Path(args.dependency_table).read_text(encoding="utf-8"))
        _mapping(environment_pin, "environment pin")
        _mapping(table, "dependency table")
    except (Wp7SessionError, OSError, ValueError) as exc:
        print("REFUSED: cannot read pin or dependency table: " + str(exc), file=sys.stderr)
        return 2
    try:
        assert_no_prohibited_imports()
        assert_no_credential_environment()
    except Wp7ProhibitedOperationError as exc:
        print("REFUSED: " + str(exc), file=sys.stderr)
        return 2
    print("DRAFT: this session is not authorized to run. Nothing was executed.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

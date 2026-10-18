"""Offline DRAFT guard for the Stage-2 generator's full-runtime/source record.

UNAPPROVED CANDIDATE.  This module builds a *candidate* implementation record
and checks, exactly, that an observed source/runtime snapshot equals a record
whose content hash the caller pinned independently, at run start and at run
end.  A match is equality evidence only.  It is not owner approval, it does
not authorize a draw or a write, and no field of any record or argument is
ever read as authorization: every record this module accepts must say
``unapproved_candidate`` and ``owner_approval: absent``.

There is deliberately no draw wrapper, no writer and no command line here.
Reads are limited to the fixed source paths below, interpreter/NumPy
attributes already in memory, a fixed allowlist of thread/dispatch
environment variables, and binary files under NumPy's own install
directories (the ``numpy`` package and its wheel-bundled ``numpy.libs``).
The binary-hash and thread/dispatch fields are candidate design, not
approved policy; see ``CANDIDATE_DESIGN_FIELDS``.

KNOWN LIMITS:
- The independent pin relies on the caller not using this module's own builder to circular-pin a hash.
- Validation relies on caller-supplied snapshots rather than capturing state internally during verification.
- Source hashes reflect the disk paths rather than the exact bytes in memory executing.
- Thread and dispatch environment variables are captured at call time, not when numpy initialized them.
- NumPy python-level monkeypatching is uncaptured.
- Floating-point affecting state (full environment, CPU dispatch, openmp config) is uncaptured beyond a fixed allowlist.
- Symlinked binaries within the install root are recorded under their resolved target's relative path, not the symlink name.
- The wheel-bundled ``numpy.libs`` install root is accepted only when it is a real
  directory, or a symlink whose resolved target lies inside the same site-packages
  directory as the ``numpy`` package.  A dangling ``numpy.libs``, or one resolving
  anywhere else, is refused with ``GeneratorGuardError``: without that refusal the
  per-binary containment check would bless binaries from an outside directory as
  NumPy's own.  This is the only symlink this module may follow.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
import threading
from typing import Any, Mapping

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "decisions_os/g9_stage2_generator_implementation_record/candidate-v1"
RECORD_STATUS = "unapproved_candidate"
OWNER_APPROVAL = "absent"
APPROVAL_STATEMENT = (
    "Unapproved candidate record. Exact equality with it is evidence that the "
    "observed sources and runtime are the ones recorded; it is not owner "
    "approval and does not authorize any draw or write."
)
EVIDENCE_STATEMENT = (
    "Equality evidence only: observed snapshot(s) byte-equal the independently "
    "pinned unapproved candidate record. Owner approval is absent."
)
SOURCE_PATHS = {
    "generator": "research/g9/stage2_generator.py",
    "validator": "research/g9/stage2_generation_contract.py",
    "guard": "research/g9/stage2_generator_guard.py",
}
# Variables that change BLAS threading or CPU kernel dispatch.  Read by name
# only; no other environment variable is consulted.
THREAD_AND_DISPATCH_KEYS = (
    "GOTO_NUM_THREADS",
    "MKL_NUM_THREADS",
    "NPY_DISABLE_CPU_FEATURES",
    "NPY_ENABLE_CPU_FEATURES",
    "OMP_NUM_THREADS",
    "OPENBLAS_CORETYPE",
    "OPENBLAS_NUM_THREADS",
)
CANDIDATE_DESIGN_FIELDS = (
    "runtime.numpy_binaries",
    "runtime.thread_and_dispatch_environment",
    "sources.guard",
)
NUMPY_ROOT_LABELS = ("numpy", "numpy.libs")
_HEX = frozenset("0123456789abcdef")
_CAPTURE_LOCK = threading.Lock()


class GeneratorGuardError(ValueError):
    """Typed refusal: malformed record/snapshot, mismatch, or drift."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise GeneratorGuardError(message)


def _require_str_keys(value: object) -> None:
    if type(value) is dict:
        for k, v in value.items():
            _require(type(k) is str, "all dictionary keys must be strings")
            _require_str_keys(v)
    elif type(value) is list:
        for v in value:
            _require_str_keys(v)

def canonical_bytes(value: object) -> bytes:
    try:
        _require_str_keys(value)
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                          allow_nan=False).encode("ascii")
    except Exception as exc:
        if isinstance(exc, GeneratorGuardError):
            raise
        raise GeneratorGuardError("value is not canonical JSON") from exc


def content_sha256(record: Mapping[str, Any]) -> str:
    body = dict(record)
    body.pop("content_sha256", None)
    return hashlib.sha256(canonical_bytes(body)).hexdigest()


def _sha(value: object, label: str) -> str:
    _require(type(value) is str and len(value) == 64 and set(value) <= _HEX, f"{label} must be lowercase SHA-256")
    return value


def _keys(value: object, expected: set[str], label: str) -> dict:
    _require(type(value) is dict and set(value) == expected, f"{label} has wrong key set")
    return value


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    # A file removed or made unreadable between discovery and read must still
    # fail through the typed contract, not as a bare OSError.
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
    except OSError as exc:
        raise GeneratorGuardError(f"cannot read {path}: {exc.__class__.__name__}") from exc
    return digest.hexdigest()


def _loaded_copies(filename: str) -> list[Path]:
    """Every already-imported module whose source file has this name."""
    found = []
    for module in list(sys.modules.values()):
        source = getattr(module, "__file__", None)
        if isinstance(source, str) and Path(source).name == filename:
            found.append(Path(source).resolve())
    return found


def capture_sources() -> dict[str, dict[str, str]]:
    """Hash the fixed generator, validator and guard sources.

    Hashing `ROOT / rel` alone proves what is on disk at that path, not what
    the interpreter imported: with `sys.path` or `PYTHONPATH` pointing
    elsewhere, a different `stage2_generator.py` can be the one actually
    running while the pristine file is the one hashed.  So any already-loaded
    module with the same filename must resolve to the hashed file.  A module
    not yet imported cannot be checked here, which is a limit of a guard that
    runs in-process, and is stated as such.
    """
    captured = {}
    for label, rel in SOURCE_PATHS.items():
        path = ROOT / rel
        expected = path.resolve()
        _require(expected == path, f"symlinks not allowed in source path: {rel}")
        for loaded in _loaded_copies(expected.name):
            _require(loaded == expected,
                     f"{label} is imported from {loaded}, not the hashed file {expected}")
        captured[label] = {"path": rel, "sha256": _file_sha256(ROOT / rel)}
    return captured


def _numpy_install_roots(package_path: Path | None = None) -> list[tuple[str, Path]]:
    """The NumPy install roots this process may hash binaries under.

    The ``package_path`` argument is the path of the ``numpy`` package
    ``__init__`` (a module attribute, so it can be supplied by a caller);
    it defaults to this process's NumPy.  The wheel-bundled ``numpy.libs``
    beside it is accepted only when it is a real directory, or a symlink whose
    resolved target lies inside the same site-packages directory as the
    package.  A dangling ``numpy.libs``, or one resolving anywhere else, is
    refused rather than followed: the per-binary ``is_relative_to(root)``
    check below cannot protect a root that is itself an outside directory.
    """
    package = Path(np.__file__ if package_path is None else package_path).resolve().parent
    site_packages = package.parent
    boundary = site_packages.resolve()
    roots = [("numpy", package)]
    bundled = site_packages / "numpy.libs"
    if bundled.is_symlink():
        # is_symlink() first: a dangling link is False under exists() and
        # would be silently skipped, leaving the refusal below unreachable.
        _require(bundled.exists(), "dangling symlink: numpy.libs")
        target = bundled.resolve()
        _require(target.is_relative_to(boundary),
                 "symlinked numpy.libs resolves outside the site-packages directory: " + target.as_posix())
        bundled = target
    if bundled.is_dir():
        roots.append(("numpy.libs", bundled))
    return roots


def _is_binary(name: str) -> bool:
    return name.endswith(".so") or ".so." in name


def capture_numpy_binaries() -> dict[str, str]:
    """CANDIDATE DESIGN: hash every shared object under NumPy's install roots only."""
    hashes: dict[str, str] = {}
    def _walk_error(exc: OSError) -> None:
        raise GeneratorGuardError(f"walk error: {exc.__class__.__name__}") from exc

    for label, root in _numpy_install_roots():
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False, onerror=_walk_error):
            dirnames.sort()
            for name in sorted(filenames):
                if not _is_binary(name):
                    continue
                path = Path(dirpath) / name
                if path.is_symlink():
                    _require(path.exists(), f"dangling symlink in numpy binaries: {name}")
                resolved = path.resolve()
                _require(resolved.is_relative_to(root) and resolved.is_file(),
                         f"NumPy binary escapes its install root: {label}/{name}")
                # Key by the RESOLVED path.  Keyed by the link name, a symlink
                # inside the root was recorded as if it were a separate binary
                # carrying its target's hash.
                hashes[f"{label}/{resolved.relative_to(root).as_posix()}"] = _file_sha256(resolved)
    _require(any(key.startswith("numpy/") for key in hashes), "no NumPy extension binaries found")
    return hashes


def capture_runtime() -> dict[str, object]:
    """Capture interpreter identity, NumPy version/build config and candidate extras."""
    config = json.loads(canonical_bytes(np.__config__.CONFIG))
    info = sys.version_info
    return {
        "python": {
            "implementation": sys.implementation.name,
            "sys_version": sys.version,
            "version_info": [info.major, info.minor, info.micro, info.releaselevel, info.serial],
            "hexversion": sys.hexversion,
        },
        "numpy": {
            "version": np.__version__,
            "config": config,
            "config_sha256": hashlib.sha256(canonical_bytes(config)).hexdigest(),
        },
        "numpy_binaries": capture_numpy_binaries(),
        "thread_and_dispatch_environment": {key: os.environ.get(key) for key in THREAD_AND_DISPATCH_KEYS},
    }


def capture_snapshot() -> dict[str, object]:
    """Observe the actual sources and runtime of this process."""
    try:
        with _CAPTURE_LOCK:
            sources = capture_sources()
            runtime = capture_runtime()
            snapshot = {"sources": sources, "runtime": runtime}
            return validate_snapshot(snapshot)
    except Exception as exc:
        if isinstance(exc, GeneratorGuardError):
            raise
        raise GeneratorGuardError(f"capture failed: {exc.__class__.__name__}") from exc


def validate_snapshot(snapshot: object) -> dict[str, object]:
    """Fail closed on any snapshot shape other than the candidate schema."""
    body = _keys(snapshot, {"sources", "runtime"}, "snapshot")
    sources = _keys(body["sources"], set(SOURCE_PATHS), "sources")
    for label, rel in SOURCE_PATHS.items():
        entry = _keys(sources[label], {"path", "sha256"}, f"sources.{label}")
        _require(entry["path"] == rel, f"sources.{label} path mismatch")
        _sha(entry["sha256"], f"sources.{label}.sha256")
    runtime = _keys(body["runtime"], {"python", "numpy", "numpy_binaries", "thread_and_dispatch_environment"}, "runtime")
    python = _keys(runtime["python"], {"implementation", "sys_version", "version_info", "hexversion"}, "runtime.python")
    _require(type(python["implementation"]) is str and python["implementation"], "runtime.python.implementation malformed")
    _require(type(python["sys_version"]) is str and python["sys_version"], "runtime.python.sys_version malformed")
    info = python["version_info"]
    _require(type(info) is list and len(info) == 5 and [type(item) for item in info] == [int, int, int, str, int],
             "runtime.python.version_info malformed")
    _require(type(python["hexversion"]) is int, "runtime.python.hexversion malformed")
    numpy_info = _keys(runtime["numpy"], {"version", "config", "config_sha256"}, "runtime.numpy")
    _require(type(numpy_info["version"]) is str and numpy_info["version"], "runtime.numpy.version malformed")
    _require(type(numpy_info["config"]) is dict and numpy_info["config"], "runtime.numpy.config malformed")
    _require(_sha(numpy_info["config_sha256"], "runtime.numpy.config_sha256")
             == hashlib.sha256(canonical_bytes(numpy_info["config"])).hexdigest(),
             "runtime.numpy.config_sha256 does not hash its config")
    binaries = runtime["numpy_binaries"]
    _require(type(binaries) is dict and binaries, "runtime.numpy_binaries malformed")
    for key, value in binaries.items():
        _require(type(key) is str, f"numpy binary key must be exactly str: {key!r}")
        label, _, rel = key.partition("/")
        _require(label in NUMPY_ROOT_LABELS, f"numpy binary key outside install roots: {key!r}")
        _require(all(part not in ("", ".", "..") for part in rel.split("/")),
                 f"numpy binary key is not a canonical relative path: {key!r}")
        _sha(value, f"numpy binary {key}")
    environment = _keys(runtime["thread_and_dispatch_environment"], set(THREAD_AND_DISPATCH_KEYS),
                        "runtime.thread_and_dispatch_environment")
    _require(all(value is None or type(value) is str for value in environment.values()),
             "thread/dispatch environment values must be str or null")
    return json.loads(canonical_bytes(body))


def build_candidate_record(snapshot: object) -> dict[str, object]:
    """Render a snapshot as an UNAPPROVED candidate record; never an approved one."""
    body = validate_snapshot(snapshot)
    record: dict[str, object] = {
        "schema": SCHEMA,
        "status": RECORD_STATUS,
        "owner_approval": OWNER_APPROVAL,
        "approval_statement": APPROVAL_STATEMENT,
        "candidate_design_fields": list(CANDIDATE_DESIGN_FIELDS),
        "sources": body["sources"],
        "runtime": body["runtime"],
    }
    record["content_sha256"] = content_sha256(record)
    return record


def validate_candidate_record(record: object, expected_record_sha256: str) -> dict[str, object]:
    """Accept only an intact unapproved candidate whose hash the caller pinned separately."""
    body = _keys(record, {"schema", "status", "owner_approval", "approval_statement", "candidate_design_fields",
                          "sources", "runtime", "content_sha256"}, "record")
    _require(body["schema"] == SCHEMA, "record schema mismatch")
    _require(body["status"] == RECORD_STATUS, "record status must be unapproved_candidate; approval is not accepted here")
    _require(body["owner_approval"] == OWNER_APPROVAL, "record owner_approval must be absent; approval is not accepted here")
    _require(body["approval_statement"] == APPROVAL_STATEMENT, "record approval statement mismatch")
    _require(body["candidate_design_fields"] == list(CANDIDATE_DESIGN_FIELDS), "record candidate-design field list mismatch")
    _require(_sha(body["content_sha256"], "record content_sha256") == content_sha256(body), "record content hash mismatch")
    _require(_sha(expected_record_sha256, "expected record SHA-256") == body["content_sha256"],
             "record is not the independently pinned record")
    validate_snapshot({"sources": body["sources"], "runtime": body["runtime"]})
    return body


def _differences(expected: object, observed: object, prefix: str) -> list[str]:
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
        for i, (e, o) in enumerate(zip(expected, observed)):
            found.extend(_differences(e, o, f"{prefix}[{i}]"))
        return found
    try:
        if type(expected) is not type(observed) or canonical_bytes(expected) != canonical_bytes(observed):
            return [prefix]
        return []
    except GeneratorGuardError:
        return [prefix]


def _evidence(record: Mapping[str, Any], phases: str) -> dict[str, str]:
    return {
        "equality": "exact_match",
        "phases": phases,
        "record_content_sha256": record["content_sha256"],
        "record_status": RECORD_STATUS,
        "owner_approval": OWNER_APPROVAL,
        "authorizes_draw_or_write": "no",
        "statement": EVIDENCE_STATEMENT,
    }


def match_snapshot(record: object, expected_record_sha256: str, observed: object) -> dict[str, str]:
    """Exact source/runtime equality between one observed snapshot and the pinned record."""
    body = validate_candidate_record(record, expected_record_sha256)
    seen = validate_snapshot(observed)
    drift = _differences({"sources": body["sources"], "runtime": body["runtime"]}, seen, "")
    _require(not drift, "observed snapshot differs from pinned record at: " + ", ".join(drift))
    return _evidence(body, "single")


def verify_start_end(record: object, expected_record_sha256: str, start: object, end: object) -> dict[str, str]:
    """Refuse unless separately captured start and end snapshots both equal the pinned record."""
    _require(start is not end, "start and end must be separate captures, not one object")
    match_snapshot(record, expected_record_sha256, start)
    end_seen = validate_snapshot(end)
    drift = _differences(validate_snapshot(start), end_seen, "")
    _require(not drift, "runtime/source drift between start and end at: " + ", ".join(drift))
    match_snapshot(record, expected_record_sha256, end)
    return _evidence(validate_candidate_record(record, expected_record_sha256), "start_and_end")

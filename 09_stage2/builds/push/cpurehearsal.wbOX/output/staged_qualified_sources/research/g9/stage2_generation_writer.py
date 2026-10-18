"""Atomic Stage-2 generation writer (WP5, pre-run review item 3).

A generation run is written into a private staging directory beside its target,
every file and every directory is fsynced, a manifest is emitted carrying each
file's content sha256 together with the implementation record's content
sha256, and only then is the staging directory atomically renamed into place
with ``os.rename``.  Every failure removes the staging directory; a target that
already exists is never overwritten, never merged and never partially updated.
``verify_written_generation`` re-hashes the promoted directory against its
manifest.

Deliberate properties, all of them load-bearing:

* The target is refused if it exists at all - file, directory or symlink - and
  is checked again immediately before the rename, because ``os.rename`` onto an
  existing non-empty directory succeeds and would merge the two.  That re-check
  shrinks the window; it does not close it.  Closing it needs
  ``renameat2(RENAME_NOREPLACE)`` or a fresh-parent link protocol, neither of
  which is reachable from this build.
* The manifest's own bytes are fixed before the staging directory exists, so
  the manifest hash is a commitment, not a report.
* The writer never decides *what* to write.  It hashes whatever bytes it is
  handed and refuses duplicate names, traversal, absolute paths, symlinks,
  non-regular files and empty names, so a caller cannot smuggle content out of
  its intended layout.  Canonical input binding (which inputs belong to which
  generation) is the caller's duty and is NOT established here; see the
  pre-run review's item 3 and WP4.

This module has no draw, no command line and no import of the generator.  It
is not a draw permission: given a manifest naming a record, it writes that
record's hash and nothing else.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
from typing import Any, Mapping


SCHEMA = "decisions_os/g9_stage2_generation_manifest/v1"
MANIFEST_NAME = "MANIFEST.json"
STAGING_PREFIX = ".g9-stage2-staging-"
NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
MANIFEST_KEYS = {
    "schema",
    "implementation_record_content_sha256",
    "file_count",
    "files",
    "scientific_outputs",
    "content_sha256",
}
ENTRY_KEYS = {"path", "sha256", "size"}
_HEX = frozenset("0123456789abcdef")


class GenerationWriterError(ValueError):
    """Typed refusal: malformed payload, unsafe layout, or failed promotion."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise GenerationWriterError(message)


def _sha(value: object, label: str) -> str:
    _require(type(value) is str and len(value) == 64 and set(value) <= _HEX,
             f"{label} must be a lowercase SHA-256")
    return value


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                          allow_nan=False).encode("ascii")
    except (TypeError, ValueError) as exc:
        raise GenerationWriterError("manifest is not canonical JSON") from exc


def _content_sha256(payload: Mapping[str, Any]) -> str:
    body = dict(payload)
    body.pop("content_sha256", None)
    return hashlib.sha256(_canonical(body)).hexdigest()


def _safe_relative_name(name: object) -> str:
    """Accept only a canonical relative POSIX path with plain components.

    A leading ``/`` produces an empty first component and a NUL is not in the
    component charset, so both are caught by the two checks below; separate
    checks for them would be unobservable, so there are none.
    """
    _require(type(name) is str and name, "file name must be a non-empty string")
    _require("\\" not in name, f"file name must use POSIX separators: {name!r}")
    parts = name.split("/")
    _require(all(part not in ("", ".", "..") for part in parts),
             f"file name is not a canonical relative path: {name!r}")
    for part in parts:
        _require(NAME_RE.fullmatch(part) is not None,
                 f"file name component is not allowed: {part!r}")
    return name


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        _require(not path.is_symlink(), f"refusing to hash a symlink: {path}")
        _require(path.is_file(), f"refusing to hash a non-regular file: {path}")
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
    except OSError as exc:
        raise GenerationWriterError(f"cannot read {path}: {exc.__class__.__name__}") from exc
    return digest.hexdigest()


def _write_file(path: Path, payload: bytes) -> str:
    # A non-bytes payload is refused HERE, at the single place bytes become a
    # file.  Relying on the caller's manifest build instead would leave
    # _write_file reachable with a str, where handle.write raises a raw TypeError
    # that is not a GenerationWriterError.
    _require(type(payload) is bytes, "file payload must be bytes")
    try:
        with path.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise GenerationWriterError(f"refusing to overwrite a staged file: {path}") from exc
    except OSError as exc:
        raise GenerationWriterError(f"cannot write {path}: {exc.__class__.__name__}") from exc
    return hashlib.sha256(payload).hexdigest()


def _fsync_dir(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        fd = os.open(str(path), flags)
    except OSError as exc:
        raise GenerationWriterError(
            f"cannot open directory {path} for fsync: {exc.__class__.__name__}") from exc
    try:
        os.fsync(fd)
    except OSError as exc:
        raise GenerationWriterError(
            f"cannot fsync directory {path}: {exc.__class__.__name__}") from exc
    finally:
        os.close(fd)


def _remove_tree(path: Path) -> None:
    """Best-effort staging cleanup; never masks the original failure."""
    try:
        shutil.rmtree(path)
    except OSError:
        pass


def build_manifest(
    files: Mapping[str, bytes],
    *,
    implementation_record_content_sha256: str,
) -> dict[str, object]:
    """Render the manifest for ``files``; its bytes are fixed before any write.

    The manifest is a commitment to the exact bytes that will be written, so
    building it before the staging directory exists is deliberate.
    """
    _require(type(files) is dict and files, "files must be a non-empty object")
    _sha(implementation_record_content_sha256, "implementation record content sha256")
    # Validate every name before sorting: a non-string key must be refused
    # through the typed contract, not by sorted() raising a raw TypeError.
    for name in files:
        _safe_relative_name(name)
    entries = []
    for name in sorted(files):
        payload = files[name]
        safe = _safe_relative_name(name)
        _require(type(payload) is bytes, f"payload for {safe} must be bytes")
        _require(safe != MANIFEST_NAME, f"{MANIFEST_NAME} is reserved for the manifest itself")
        entries.append({"path": safe, "sha256": hashlib.sha256(payload).hexdigest(),
                        "size": len(payload)})
    names = [entry["path"] for entry in entries]
    # Two different input keys can name the same canonical path, because
    # "a.txt" and "./a.txt" both reduce to one component list.  The name check
    # above already refuses "./a.txt", so this is defence at the boundary: it is
    # the only place that can see the duplication, and it is what stops the same
    # staged path being written twice.
    _require(len(set(names)) == len(names), "duplicate file names in payload")
    manifest: dict[str, object] = {
        "schema": SCHEMA,
        "implementation_record_content_sha256": implementation_record_content_sha256,
        "file_count": len(entries),
        "files": entries,
        "scientific_outputs": "intentionally absent",
    }
    manifest["content_sha256"] = _content_sha256(manifest)
    return manifest


def _manifest_bytes(manifest: Mapping[str, Any]) -> bytes:
    _require(manifest.get("content_sha256") == _content_sha256(manifest),
             "manifest content hash mismatch")
    return _canonical(manifest)


def validate_manifest(manifest: object) -> dict[str, object]:
    if type(manifest) is not dict:
        raise GenerationWriterError("manifest must be an object")
    _require(set(manifest) == MANIFEST_KEYS, "manifest has wrong key set")
    _require(manifest["schema"] == SCHEMA, "manifest schema mismatch")
    _require(manifest["scientific_outputs"] == "intentionally absent",
             "manifest scope statement mismatch")
    _sha(manifest["implementation_record_content_sha256"], "manifest record hash")
    entries = manifest["files"]
    _require(type(entries) is list and entries, "manifest file list must be a non-empty list")
    names = []
    for entry in entries:
        _require(type(entry) is dict and set(entry) == ENTRY_KEYS,
                 "manifest file entry has wrong key set")
        names.append(_safe_relative_name(entry["path"]))
        _sha(entry["sha256"], f"manifest file {entry['path']}")
        _require(type(entry["size"]) is int and entry["size"] >= 0, "manifest size malformed")
    _require(len(set(names)) == len(names), "manifest contains duplicate paths")
    _require(MANIFEST_NAME not in names, f"{MANIFEST_NAME} is reserved")
    _require(type(manifest["file_count"]) is int and manifest["file_count"] == len(entries),
             "manifest file_count mismatch")
    _require(manifest["content_sha256"] == _content_sha256(manifest),
             "manifest content hash mismatch")
    return dict(manifest)


def _promote(staging: Path, destination: Path) -> None:
    """Atomically move the staged directory into place, refusing to merge.

    ``os.rename`` alone is not enough: on POSIX it silently moves each entry
    of ``staging`` into an existing non-empty ``destination``.  The target is
    re-checked here, immediately before the rename, and the rename is only
    issued when the target is still absent, so the window is as small as a
    rename allows.  A production writer would need
    ``renameat2(RENAME_NOREPLACE)`` or a fresh-parent link protocol to close it
    completely; neither is reachable from this build.
    """
    if destination.exists() or destination.is_symlink():
        raise GenerationWriterError(f"refusing to overwrite an existing target: {destination}")
    try:
        os.rename(str(staging), str(destination))
    except OSError as exc:
        # The staging directory is NOT removed here: it is still the only copy
        # of the payload, and the caller decides whether to discard it.  The
        # failure path in write_generation is what removes it.
        raise GenerationWriterError(
            f"cannot promote {staging} to {destination}: {exc.__class__.__name__}"
        ) from exc


def _as_path(target: object, label: str) -> Path:
    """Accept a str or any os.PathLike, and nothing else.

    ``isinstance``, not an exact-type test: a ``PosixPath`` is not itself a
    member of the ``Path`` class, so ``type(x) in (str, Path)`` would refuse
    the ordinary way a caller names a directory.
    """
    _require(type(target) is str or isinstance(target, os.PathLike), f"{label} must be a path")
    return Path(target)


def write_generation(
    *,
    target: Path | str,
    files: Mapping[str, bytes],
    implementation_record_content_sha256: str,
) -> dict[str, object]:
    """Atomically write ``files`` and a manifest to ``target``.

    The target's parent must already exist and be a real directory.  On any
    failure the staging directory is removed and the target is left exactly as
    it was.
    """
    destination = _as_path(target, "target")
    _require(destination.name not in ("", ".", ".."), "target must name a directory")
    manifest = validate_manifest(build_manifest(
        files, implementation_record_content_sha256=implementation_record_content_sha256))
    manifest_body = _manifest_bytes(manifest)
    parent = destination.parent
    _require(parent.is_dir() and not parent.is_symlink(),
             "target parent must be an existing real directory")
    # No pre-check that the target is absent: _promote re-checks it immediately
    # before the rename, which is the only place the check can be correct.  A
    # pre-check here would be an unobservable duplicate of it.
    staging = parent / f"{STAGING_PREFIX}{os.getpid()}-{destination.name}"
    _require(not staging.exists() and not staging.is_symlink(),
             f"staging path already exists: {staging}")
    try:
        staging.mkdir()
    except OSError as exc:
        raise GenerationWriterError(
            f"cannot create staging directory: {exc.__class__.__name__}") from exc
    try:
        for entry in manifest["files"]:
            file_path = staging / entry["path"]
            if not file_path.parent.is_dir():
                file_path.parent.mkdir(parents=True)
                _fsync_dir(file_path.parent)
                _fsync_dir(staging)
            digest = _write_file(file_path, files[entry["path"]])
            _require(digest == entry["sha256"],
                     f"staged file does not match its manifest entry: {entry['path']}")
        _write_file(staging / MANIFEST_NAME, manifest_body)
        _fsync_dir(staging)
        _promote(staging, destination)
    except BaseException:
        _remove_tree(staging)
        raise
    _fsync_dir(destination)
    _fsync_dir(parent)
    return {
        "target": str(destination),
        "manifest": manifest,
        "manifest_content_sha256": manifest["content_sha256"],
        "file_count": manifest["file_count"],
    }


def verify_written_generation(
    target: Path | str,
    *,
    expected_implementation_record_content_sha256: str | None = None,
) -> dict[str, object]:
    """Re-hash a promoted generation directory against its manifest.

    Refuses a missing or non-directory target, a missing or malformed manifest,
    any file whose size or content hash differs, any file present but not in
    the manifest, any manifest entry with no file, and - when the caller
    supplies the expected record hash - a manifest bound to a different record.
    """
    destination = _as_path(target, "target")
    _require(destination.is_dir() and not destination.is_symlink(),
             f"generation target is not a real directory: {destination}")
    manifest_path = destination / MANIFEST_NAME
    _require(manifest_path.is_file() and not manifest_path.is_symlink(),
             f"generation manifest is missing or not a regular file: {manifest_path}")
    try:
        raw = manifest_path.read_text(encoding="ascii")
    except (OSError, UnicodeDecodeError) as exc:
        raise GenerationWriterError(
            f"cannot read manifest: {exc.__class__.__name__}") from exc
    try:
        parsed = json.loads(raw)
    except ValueError as exc:
        raise GenerationWriterError("manifest is not JSON") from exc
    manifest = validate_manifest(parsed)
    if expected_implementation_record_content_sha256 is not None:
        _sha(expected_implementation_record_content_sha256, "expected record content sha256")
        _require(manifest["implementation_record_content_sha256"]
                 == expected_implementation_record_content_sha256,
                 "generation is bound to a different implementation record")
    listed = set()
    for entry in manifest["files"]:
        name = entry["path"]
        listed.add(name)
        path = destination / name
        _require(path.is_file() and not path.is_symlink(), f"manifest file missing: {name}")
        _require(path.stat().st_size == entry["size"], f"manifest size mismatch: {name}")
        _require(_file_sha256(path) == entry["sha256"], f"file content hash mismatch: {name}")
    present = set()
    for dirpath, dirnames, filenames in os.walk(destination, followlinks=False):
        dirnames.sort()
        for filename in sorted(filenames):
            present.add(Path(dirpath, filename).relative_to(destination).as_posix())
    _require(present == listed | {MANIFEST_NAME},
             "generation directory contents differ from the manifest")
    return {
        "target": str(destination),
        "verdict": "verified",
        "file_count": manifest["file_count"],
        "manifest_content_sha256": manifest["content_sha256"],
        "implementation_record_content_sha256": manifest["implementation_record_content_sha256"],
    }

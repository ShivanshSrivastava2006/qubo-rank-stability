#!/usr/bin/env python3
"""Synthetic fixtures for the atomic Stage-2 generation writer.

Every filesystem effect happens inside a ``tempfile.TemporaryDirectory``; the
project tree is never written to, read for a generation target, or used as a
staging parent.  No candidate, instance, ground truth or scientific value is
produced: the payloads are ASCII fixture text.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
# Snapshot bytecode BEFORE any project import: the project may carry a tracked
# baseline of .pyc files, and this fixture (imports included) must add none.
PYC_BEFORE = set(ROOT.rglob("*.pyc"))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from research.g9 import stage2_generation_writer as w  # noqa: E402


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
    except w.GenerationWriterError as exc:
        if needle and needle not in str(exc):
            raise FixtureError(f"{label}: refused for the wrong reason: {exc}") from exc
        COUNT += 1
        return
    except Exception as exc:
        raise FixtureError(f"{label}: raw {type(exc).__name__} instead of GenerationWriterError") from exc
    raise FixtureError(f"{label}: accepted")


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("ascii")


def fake(tag: str) -> str:
    return hashlib.sha256(tag.encode("ascii")).hexdigest()


RECORD_HASH = fake("synthetic-implementation-record")
OTHER_RECORD_HASH = fake("other-implementation-record")
FILES = {
    "instance_00/ledger.json": b'{"slot": 1, "synthetic": true}\n',
    "instance_00/returns.f64": bytes(range(64)),
    "manifest_of_instances.txt": b"two synthetic instances\n",
}


def staging_leftovers(parent: Path) -> list:
    return sorted(p.name for p in parent.iterdir() if p.name.startswith(w.STAGING_PREFIX))


def _cleanup(path: Path) -> None:
    import shutil
    shutil.rmtree(path)


# --------------------------------------------------------------------------
# The manifest
# --------------------------------------------------------------------------
def check_manifest() -> None:
    manifest = w.build_manifest(FILES, implementation_record_content_sha256=RECORD_HASH)
    body = w.validate_manifest(manifest)
    require(body["schema"] == w.SCHEMA and body["file_count"] == 3
            and [entry["path"] for entry in body["files"]] == sorted(FILES),
            "manifest shape drift")
    require(body["implementation_record_content_sha256"] == RECORD_HASH,
            "manifest does not carry the implementation record hash")
    require(body["scientific_outputs"] == "intentionally absent", "manifest scope statement drift")
    independent = {key: value for key, value in manifest.items() if key != "content_sha256"}
    require(manifest["content_sha256"] == hashlib.sha256(canonical(independent)).hexdigest(),
            "manifest content hash is not independently reproducible")
    for name, payload in FILES.items():
        entry = next(e for e in body["files"] if e["path"] == name)
        require(entry["sha256"] == hashlib.sha256(payload).hexdigest() and entry["size"] == len(payload),
                f"manifest entry drift for {name}")
    # The manifest is a commitment, so the same inputs give the same bytes.
    again = w.build_manifest(dict(reversed(list(FILES.items()))),
                             implementation_record_content_sha256=RECORD_HASH)
    require(canonical(again) == canonical(manifest), "manifest is not order-independent")

    refused(lambda: w.build_manifest({}, implementation_record_content_sha256=RECORD_HASH),
            "empty payload", "non-empty object")
    refused(lambda: w.build_manifest(FILES, implementation_record_content_sha256="0" * 63),
            "short record hash", "lowercase SHA-256")
    refused(lambda: w.build_manifest(FILES, implementation_record_content_sha256=RECORD_HASH.upper()),
            "uppercase record hash", "lowercase SHA-256")
    for name, why in (
        ("", "empty name"),
        ("/abs.txt", "absolute path"),
        ("a/../../escape.txt", "parent escape"),
        ("./a.txt", "leading dot"),
        ("a//b.txt", "double slash"),
        ("a/", "trailing slash"),
        ("..", "dot dot"),
        (".", "dot"),
        ("sub\\win.txt", "backslash separator"),
        ("space in name", "with space.txt"),
        ("leading dash", "-leading-dash.txt"),
        ("NUL byte", "nul\x00.txt"),
        ("absolute path with NUL", "/nul\x00.txt"),
        ("NUL in a component", "a/b\x00c.txt"),
        (w.MANIFEST_NAME, "reserved manifest name"),
    ):
        refused(lambda name=name: w.build_manifest({name: b"x"},
                                                   implementation_record_content_sha256=RECORD_HASH),
                f"unsafe file name ({why})")
    refused(lambda: w.build_manifest({"a.txt": "not bytes"},
                                     implementation_record_content_sha256=RECORD_HASH),
            "non-bytes payload", "must be bytes")
    refused(lambda: w.build_manifest([], implementation_record_content_sha256=RECORD_HASH),
            "non-mapping payload", "non-empty object")
    refused(lambda: w.build_manifest({"a.txt": b"x", 1: b"y"},
                                     implementation_record_content_sha256=RECORD_HASH),
            "non-string file name", "non-empty string")

    # A payload mapping whose keys collapse to one canonical name.  A dict
    # normally cannot hold duplicate keys, and _safe_relative_name does not
    # normalise, so the duplication the check exists to catch is produced here by
    # patching the name resolver so two distinct keys yield one name.  Without
    # this the check is unreachable and therefore unverified.
    original_name_check = w._safe_relative_name
    w._safe_relative_name = lambda name: "a.txt" if name in ("a.txt", "b.txt") else name
    try:
        refused(lambda: w.build_manifest({"a.txt": b"x", "b.txt": b"y"},
                                         implementation_record_content_sha256=RECORD_HASH),
                "duplicate canonical names", "duplicate file names")
    finally:
        w._safe_relative_name = original_name_check

    # Malformed manifests are refused by validate_manifest.  Each case is
    # resealed after the edit, so the content-hash check does not shadow the
    # check under test.
    def resealed(edit) -> dict:
        body = json.loads(json.dumps(manifest))
        edit(body)
        body.pop("content_sha256", None)
        body["content_sha256"] = w._content_sha256(body)
        return body

    # A manifest edited WITHOUT resealing: the content hash no longer covers
    # the body, which is exactly what the self-hash check is for.
    stale = json.loads(json.dumps(manifest))
    stale["files"][0]["sha256"] = fake("x")
    refused(lambda: w.validate_manifest(stale), "stale content hash", "content hash mismatch")

    def resealed_raw(edit) -> dict:
        """Edit the manifest, then re-seal it so only the edit can refuse."""
        body = json.loads(json.dumps(manifest))
        edit(body)
        body.pop("content_sha256", None)
        body["content_sha256"] = w._content_sha256(body)
        return body

    bad_entry = resealed_raw(lambda m: m["files"][0].update(sha256="not-a-hash"))
    refused(lambda: w.validate_manifest(bad_entry), "malformed entry hash",
            "must be a lowercase SHA-256")
    stale_removed = json.loads(json.dumps(manifest))
    stale_removed.pop("content_sha256")
    refused(lambda: w.validate_manifest(stale_removed), "content hash absent", "wrong key set")
    for label, value in (("not a sha", "not-a-hash"), ("uppercase", "A" * 64), ("short", "ab")):
        broken = json.loads(json.dumps(manifest))
        broken["content_sha256"] = value
        refused(lambda broken=broken: w.validate_manifest(broken),
                f"content hash malformed: {label}", "content hash mismatch")

    for label, edit, needle in (
        ("extra key", lambda m: m.update(extra=1), "wrong key set"),
        ("missing key", lambda m: m.pop("file_count"), "wrong key set"),
        ("schema drift", lambda m: m.update(schema="other/v1"), "schema mismatch"),
        ("scope drift", lambda m: m.update(scientific_outputs="present"), "scope statement"),
        ("bad record hash", lambda m: m.update(implementation_record_content_sha256="zz"),
         "lowercase SHA-256"),
        ("empty file list", lambda m: m.update(files=[]), "non-empty list"),
        ("file_count drift", lambda m: m.update(file_count=99), "file_count mismatch"),
        ("bool file_count", lambda m: m.update(file_count=True), "file_count mismatch"),
        ("entry extra key", lambda m: m["files"][0].update(extra=1), "wrong key set"),
        ("entry missing key", lambda m: m["files"][0].pop("size"), "wrong key set"),
        ("negative size", lambda m: m["files"][0].update(size=-1), "size malformed"),
        ("bool size", lambda m: m["files"][0].update(size=True), "size malformed"),
        ("unsafe path", lambda m: m["files"][0].update(path="../escape.txt"), "canonical relative path"),
        ("duplicate path", lambda m: m["files"].append(dict(m["files"][0])), "duplicate paths"),
        ("manifest listed as a file", lambda m: m["files"][0].update(path=w.MANIFEST_NAME), "reserved"),
    ):
        refused(lambda edit=edit: w.validate_manifest(resealed(edit)), f"malformed manifest: {label}", needle)
    for label, value in (("not an object", "string"), ("None", None), ("list", [])):
        refused(lambda value=value: w.validate_manifest(value), f"manifest as {label}", "must be an object")


# --------------------------------------------------------------------------
# Write, verify, and the refusals
# --------------------------------------------------------------------------
def check_write_and_verify() -> None:
    with tempfile.TemporaryDirectory(prefix="g9-generation-") as tmp:
        base = Path(os.path.realpath(tmp))
        target = base / "generation-01"
        receipt = w.write_generation(target=target, files=FILES,
                                     implementation_record_content_sha256=RECORD_HASH)
        require(target.is_dir(), "target was not promoted")
        require(staging_leftovers(base) == [], f"staging survived: {staging_leftovers(base)}")
        require(receipt["manifest_content_sha256"] == receipt["manifest"]["content_sha256"]
                and receipt["file_count"] == 3, "write receipt drift")
        # The promoted tree is exactly the payload plus the manifest.
        present = sorted(p.relative_to(target).as_posix() for p in target.rglob("*") if p.is_file())
        require(present == sorted([*FILES, w.MANIFEST_NAME]), f"promoted tree drift: {present}")
        for name, payload in FILES.items():
            require((target / name).read_bytes() == payload, f"promoted content drift: {name}")
        on_disk = json.loads((target / w.MANIFEST_NAME).read_text(encoding="ascii"))
        require(canonical(on_disk) == canonical(receipt["manifest"]), "manifest bytes drift")
        require((target / w.MANIFEST_NAME).read_bytes() == canonical(receipt["manifest"]),
                "manifest on disk is not the canonical commitment")
        # The manifest's own content hash is re-derived from what is on disk,
        # so a manifest edited after the write cannot verify as the receipt's.
        require(on_disk["content_sha256"] == receipt["manifest_content_sha256"],
                "manifest content hash on disk does not match the receipt")
        require(hashlib.sha256(canonical({k: v for k, v in on_disk.items()
                                          if k != "content_sha256"})).hexdigest()
                == receipt["manifest_content_sha256"],
                "manifest content hash is not independently reproducible from disk")

        verdict = w.verify_written_generation(target,
                                              expected_implementation_record_content_sha256=RECORD_HASH)
        require(verdict["verdict"] == "verified" and verdict["file_count"] == 3
                and verdict["manifest_content_sha256"] == receipt["manifest_content_sha256"]
                and verdict["implementation_record_content_sha256"] == RECORD_HASH,
                "verify verdict drift")
        # Verifying without the expected record hash still verifies the bytes.
        require(w.verify_written_generation(target)["verdict"] == "verified",
                "verify without an expected record hash failed")
        refused(lambda: w.verify_written_generation(
            target, expected_implementation_record_content_sha256=OTHER_RECORD_HASH),
            "generation bound to another record", "different implementation record")
        refused(lambda: w.verify_written_generation(
            target, expected_implementation_record_content_sha256=OTHER_RECORD_HASH.upper()),
            "uppercase expected record hash", "lowercase SHA-256")


def check_refusals_and_cleanup() -> None:
    with tempfile.TemporaryDirectory(prefix="g9-generation-") as tmp:
        base = Path(os.path.realpath(tmp))

        # An existing target is never overwritten, of any kind.
        existing = base / "taken"
        existing.mkdir()
        (existing / "keep.txt").write_bytes(b"existing")
        refused(lambda: w.write_generation(target=existing, files=FILES,
                                           implementation_record_content_sha256=RECORD_HASH),
                "existing directory target", "refusing to overwrite")
        require((existing / "keep.txt").read_bytes() == b"existing", "existing target was modified")
        require(sorted(p.name for p in base.iterdir() if p.name != "taken") == [],
                "a refused write left something behind")

        as_file = base / "target-file"
        as_file.write_bytes(b"occupied")
        refused(lambda: w.write_generation(target=as_file, files=FILES,
                                           implementation_record_content_sha256=RECORD_HASH),
                "existing file target", "refusing to overwrite")
        require(as_file.read_bytes() == b"occupied", "existing file target was modified")

        link = base / "target-link"
        outside = base / "outside"
        outside.mkdir()
        (outside / "keep.txt").write_bytes(b"outside")
        link.symlink_to(outside, target_is_directory=True)
        refused(lambda: w.write_generation(target=link, files=FILES,
                                           implementation_record_content_sha256=RECORD_HASH),
                "symlink target", "refusing to overwrite")
        require((outside / "keep.txt").read_bytes() == b"outside", "symlink target was followed and written")

        # A missing parent is refused, and nothing is created.
        refused(lambda: w.write_generation(target=base / "absent" / "gen", files=FILES,
                                           implementation_record_content_sha256=RECORD_HASH),
                "missing parent", "existing real directory")
        require(not (base / "absent").exists(), "a refused write created the missing parent")

        # A symlinked parent is refused.
        parent_link = base / "parent-link"
        parent_link.symlink_to(outside, target_is_directory=True)
        refused(lambda: w.write_generation(target=parent_link / "gen", files=FILES,
                                           implementation_record_content_sha256=RECORD_HASH),
                "symlinked parent", "existing real directory")

        # Bad targets.  An existing target is caught by the overwrite check
        # before the name check, so both are acceptable reasons here; what
        # matters is that the write is refused and nothing is touched.
        for target, why in ((base, "the parent itself"), (base / ".", "dot"), (base / "..", "dot dot")):
            marker = sorted(p.name for p in base.iterdir())
            refused(lambda target=target: w.write_generation(
                target=target, files=FILES, implementation_record_content_sha256=RECORD_HASH),
                f"target is {why}")
            require(sorted(p.name for p in base.iterdir()) == marker,
                    f"a refused write changed the parent for target {why}")
        refused(lambda: w.write_generation(target=123, files=FILES,
                                           implementation_record_content_sha256=RECORD_HASH),
                "non-path target", "must be a path")

        # The degenerate-target-name check is masked by the existing-target and
        # parent checks for a real directory, so it is exercised in isolation
        # against a target whose parent does not exist yet: only the name check
        # can refuse that one, and its message names the reason.  ("a" / "" and
        # "a" / "." are collapsed by pathlib itself, so the reachable degenerate
        # names are ".." and the root.)
        for name, why in (("..", "dot dot"), ("/", "root"), ("a/..", "trailing dot dot")):
            refused(lambda name=name: w.write_generation(
                target=base / "gen-name" / name, files=FILES,
                implementation_record_content_sha256=RECORD_HASH),
                f"degenerate target name ({why})", "must name a directory")
        require(not (base / "gen-name").exists(),
                "a refused degenerate target name created its parent")

        # A nested generation promotes as one atomic unit, so an interrupted
        # write can never leave half a tree visible.  The manifest covers every
        # file, at any depth.
        nested = {"top.txt": b"top-level payload", "sub/inner.txt": b"nested payload",
                  "sub/deep/leaf.txt": b"leaf payload"}
        target = base / "generation-nested"
        receipt = w.write_generation(target=target, files=nested,
                                     implementation_record_content_sha256=RECORD_HASH)
        require(receipt["file_count"] == 3 and target.is_dir(), "nested generation was not promoted")
        require(w.verify_written_generation(target)["verdict"] == "verified",
                "nested generation does not verify")
        require(staging_leftovers(base) == [], f"staging survived: {staging_leftovers(base)}")

        # A failure part-way through removes the staging directory and leaves
        # the target absent.  The promotion is re-entered with a target that
        # appeared in the meantime, which is the realistic race: the target is
        # re-checked immediately before the rename precisely so a late arrival
        # is refused instead of merged.
        raced = base / "generation-raced"
        w.write_generation(target=raced, files={"a.txt": b"raced payload"},
                           implementation_record_content_sha256=RECORD_HASH)
        marker = (raced / "a.txt").read_bytes()
        staging = base / f"{w.STAGING_PREFIX}test-late"
        staging.mkdir()
        (staging / "a.txt").write_bytes(b"staged payload")
        refused(lambda: w._promote(staging, raced), "promotion onto a target that appeared",
                "refusing to overwrite")
        require((raced / "a.txt").read_bytes() == marker and staging.is_dir(),
                "a refused promotion modified the target")

        # The promotion wraps a raw OSError rather than letting it escape, and
        # leaves the staged payload in place for the caller to decide about.
        refused(lambda: w._promote(staging, base / "generation-absent" / "deep"),
                "promotion with a missing parent", "cannot promote")
        require(staging.is_dir() and (staging / "a.txt").read_bytes() == b"staged payload",
                "a failed promotion removed or altered the caller's staging directory")
        _cleanup(staging)

        # A collision with the writer's own staging name is refused outright.
        collide = base / f"{w.STAGING_PREFIX}{os.getpid()}-generation-collide"
        collide.mkdir()
        refused(lambda: w.write_generation(target=base / "generation-collide",
                                           files={"a.txt": b"x"},
                                           implementation_record_content_sha256=RECORD_HASH),
                "staging name collision", "staging path already exists")
        require(collide.is_dir() and not (base / "generation-collide").exists(),
                "a staging collision disturbed the tree")
        _cleanup(collide)

        # A control write must succeed, so the assertions above are about the
        # failing case only.
        control = w.write_generation(target=base / "gen-control", files={"a.txt": b"1"},
                                     implementation_record_content_sha256=RECORD_HASH)
        require(control["file_count"] == 1 and (base / "gen-control" / "a.txt").read_bytes() == b"1",
                "the control write did not behave as expected")

        # The target-existing refusal, isolated from the pre-check: the
        # promotion is the only thing standing between a late target and a
        # merge, so the refusal must come from the promotion alone when the
        # pre-check is neutralised.
        late = base / "generation-late"
        w.write_generation(target=late, files={"a.txt": b"original"},
                           implementation_record_content_sha256=RECORD_HASH)
        late_marker = (late / "a.txt").read_bytes()
        late_staging = base / f"{w.STAGING_PREFIX}{os.getpid()}-generation-late"
        late_staging.mkdir()
        (late_staging / "a.txt").write_bytes(b"replacement")
        refused(lambda: w._promote(late_staging, late), "promotion onto an existing target",
                "refusing to overwrite")
        require((late / "a.txt").read_bytes() == late_marker
                and (late / w.MANIFEST_NAME).is_file(),
                "the refused promotion modified the target")
        _cleanup(late_staging)

        # The staged-write hash check, driven by handing the writer bytes that
        # do not match the manifest entry it computed.  The manifest is built
        # from the same dict, so the only way to desynchronise them is to
        # mutate the manifest the writer will use: replace the entry's hash
        # after build_manifest but before the write loop.
        original_build = w.build_manifest
        def tampered_build(files, *, implementation_record_content_sha256):
            manifest = original_build(files, implementation_record_content_sha256=implementation_record_content_sha256)
            for entry in manifest["files"]:
                if entry["path"] == "a.txt":
                    entry["sha256"] = fake("staged-mismatch")
            manifest["content_sha256"] = w._content_sha256(manifest)
            return manifest

        w.build_manifest = tampered_build
        try:
            before_staging = staging_leftovers(base)
            refused(lambda: w.write_generation(target=base / "gen-mismatch",
                                               files={"a.txt": b"payload"},
                                               implementation_record_content_sha256=RECORD_HASH),
                    "staged file does not match its manifest entry", "manifest entry")
            require(staging_leftovers(base) == before_staging,
                    "the refused staged write left a staging directory")
            require(not (base / "gen-mismatch").exists(), "the refused staged write left a target")
        finally:
            w.build_manifest = original_build

        # The staged-overwrite refusal: writing the same staged path twice must
        # be refused rather than silently replaced.  The non-bytes refusal is
        # checked here too, at the one place bytes become a file, because
        # write_generation never passes a non-bytes payload this far.
        overwrite_staging = base / f"{w.STAGING_PREFIX}{os.getpid()}-overwrite"
        overwrite_staging.mkdir()
        for label, bad in (("str", "not bytes"), ("bytearray", bytearray(b"x")),
                           ("int", 7), ("None", None)):
            refused(lambda bad=bad: w._write_file(overwrite_staging / f"{label}.txt", bad),
                    f"non-bytes staged payload ({label})", "must be bytes")
        require(sorted(p.name for p in overwrite_staging.iterdir()) == [],
                "a refused non-bytes payload still created a file")
        first = w._write_file(overwrite_staging / "a.txt", b"first")
        require(first == hashlib.sha256(b"first").hexdigest(),
                "writing a new staged file did not hash the payload")
        refused(lambda: w._write_file(overwrite_staging / "a.txt", b"second"),
                "overwriting an existing staged file", "refusing to overwrite")
        require((overwrite_staging / "a.txt").read_bytes() == b"first",
                "the refused staged overwrite changed the file")
        _cleanup(overwrite_staging)

        # The symlink refusal in _file_sha256, in isolation.
        hash_dir = base / "hashdir"
        hash_dir.mkdir()
        (hash_dir / "real.txt").write_bytes(b"real payload")
        (hash_dir / "link.txt").symlink_to(hash_dir / "real.txt")
        refused(lambda: w._file_sha256(hash_dir / "link.txt"),
                "hashing a symlink", "refusing to hash a symlink")
        require(w._file_sha256(hash_dir / "real.txt") == hashlib.sha256(b"real payload").hexdigest(),
                "hashing a regular file is refused")
        refused(lambda: w._file_sha256(hash_dir), "hashing a directory", "non-regular file")
        (hash_dir / "loop").symlink_to(hash_dir / "loop")
        refused(lambda: w._file_sha256(hash_dir / "loop"), "hashing a dangling self-link",
                "refusing to hash a symlink")


def check_verify_refusals() -> None:
    with tempfile.TemporaryDirectory(prefix="g9-verify-") as tmp:
        base = Path(os.path.realpath(tmp))

        refused(lambda: w.verify_written_generation(base / "absent"), "missing target",
                "not a real directory")
        refused(lambda: w.verify_written_generation(123), "non-path target", "must be a path")

        empty = base / "empty"
        empty.mkdir()
        refused(lambda: w.verify_written_generation(empty), "no manifest", "manifest is missing")

        # A manifest that is not JSON, and one that is valid JSON but not a
        # manifest, are both refused.
        not_json = base / "not-json"
        not_json.mkdir()
        (not_json / w.MANIFEST_NAME).write_bytes(b"not json at all")
        refused(lambda: w.verify_written_generation(not_json), "manifest is not JSON", "not JSON")

        wrong = base / "wrong"
        wrong.mkdir()
        (wrong / w.MANIFEST_NAME).write_bytes(b'{"schema": "other"}')
        refused(lambda: w.verify_written_generation(wrong), "manifest is not a manifest", "wrong key set")

        # Non-ASCII manifest bytes are refused rather than crashing.
        non_ascii = base / "non-ascii"
        non_ascii.mkdir()
        (non_ascii / w.MANIFEST_NAME).write_bytes(b'{"label": "\xff\xfe"}')
        refused(lambda: w.verify_written_generation(non_ascii), "non-ASCII manifest",
                "cannot read manifest")

        # A size change is caught by the size check.
        target = base / "tampered"
        w.write_generation(target=target, files={"a.txt": b"original"},
                           implementation_record_content_sha256=RECORD_HASH)
        require(w.verify_written_generation(target)["verdict"] == "verified", "control generation")
        (target / "a.txt").write_bytes(b"tampered and longer")
        refused(lambda: w.verify_written_generation(target), "resized payload", "size mismatch")

        # Same length, different bytes: only the content re-hash catches this,
        # so this is the fixture that proves the manifest is re-hashed rather
        # than merely re-read.
        target2 = base / "tampered-same-size"
        w.write_generation(target=target2, files={"a.txt": b"aaaaaaaa"},
                           implementation_record_content_sha256=RECORD_HASH)
        (target2 / "a.txt").write_bytes(b"bbbbbbbb")
        refused(lambda: w.verify_written_generation(target2), "same-size tamper", "content hash mismatch")

        # A missing file, a symlinked file, an extra file, and a missing
        # manifest entry are all refused.
        target3 = base / "extra-file"
        w.write_generation(target=target3, files={"a.txt": b"payload"},
                           implementation_record_content_sha256=RECORD_HASH)
        (target3 / "unlisted.txt").write_bytes(b"not in the manifest")
        refused(lambda: w.verify_written_generation(target3), "unlisted extra file",
                "differ from the manifest")

        target4 = base / "missing-file"
        w.write_generation(target=target4, files={"a.txt": b"payload"},
                           implementation_record_content_sha256=RECORD_HASH)
        (target4 / "a.txt").unlink()
        refused(lambda: w.verify_written_generation(target4), "missing manifest file", "manifest file missing")

        target5 = base / "symlinked-file"
        w.write_generation(target=target5, files={"a.txt": b"payload"},
                           implementation_record_content_sha256=RECORD_HASH)
        (target5 / "a.txt").unlink()
        (base / "real.txt").write_bytes(b"payload")
        (target5 / "a.txt").symlink_to(base / "real.txt")
        refused(lambda: w.verify_written_generation(target5), "symlinked manifest file",
                "manifest file missing")

        # A symlinked manifest is refused.
        target6 = base / "symlink-manifest"
        w.write_generation(target=target6, files={"a.txt": b"payload"},
                           implementation_record_content_sha256=RECORD_HASH)
        real_manifest = (target6 / w.MANIFEST_NAME).read_bytes()
        (target6 / w.MANIFEST_NAME).unlink()
        (base / "real-manifest.json").write_bytes(real_manifest)
        (target6 / w.MANIFEST_NAME).symlink_to(base / "real-manifest.json")
        refused(lambda: w.verify_written_generation(target6), "symlinked manifest",
                "manifest is missing")


def check_no_project_writes() -> None:
    source = (ROOT / "research/g9/stage2_generation_writer.py").read_text(encoding="ascii")
    for forbidden in ("__main__", "argparse", "sys.argv", "subprocess", "socket", "urllib", "kaggle",
                      "research.g9.stage2_generator", "from research.g9", "import research"):
        require(forbidden not in source, f"writer source contains forbidden token {forbidden!r}")
    require("tempfile" not in source,
            "the writer itself creates temporary directories; only fixtures may")
    # Exactly one rename in the module, inside _promote: the promotion is
    # atomic and there is no second, per-file path.
    require(source.count("os.rename(") == 1, "the writer must promote with exactly one rename")
    require(source.count("shutil.rmtree") == 1, "the writer must clean staging in exactly one place")
    # The writer must fsync, and it must do so at exactly two sites: the staged
    # file's descriptor in _write_file, and the directory in _fsync_dir.  A
    # third or a neutered one is an unverified change to the durability path.
    require("fsync" in source, "the writer never fsyncs")
    require(source.count("os.fsync(") == 2
            and source.count("os.fsync(handle.fileno())") == 1
            and source.count("def _fsync_dir(") == 1
            and "return\n    flags" not in source,
            "the writer must fsync the staged file and _fsync_dir, and nowhere else")


def main() -> int:
    before = set(p for p in (ROOT / "research").rglob("*") if p.is_file())
    check_manifest()
    check_write_and_verify()
    check_refusals_and_cleanup()
    check_verify_refusals()
    check_no_project_writes()
    after = set(p for p in (ROOT / "research").rglob("*") if p.is_file())
    require(after == before, f"fixture changed the project tree: {sorted(str(p) for p in after ^ before)}")
    require(set(ROOT.rglob("*.pyc")) == PYC_BEFORE, "fixture wrote bytecode")
    print(f"optimize={sys.flags.optimize} checks={COUNT}")
    print(f"manifest schema={w.SCHEMA} files={len(FILES)} record_hash={RECORD_HASH}")
    print("PASS Stage-2 generation writer fixtures; temporary directories only; "
          "no project write, no candidate, no ground truth, no scientific value")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

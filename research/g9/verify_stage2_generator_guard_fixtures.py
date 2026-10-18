#!/usr/bin/env python3
"""Synthetic fixtures for the UNAPPROVED Stage-2 generator guard draft.

Match and start/end drift logic is exercised with synthetic snapshots.  One
actual capture is compared against expectations computed here independently
(direct file hashes, interpreter and NumPy attributes).  No canonical input
is read, no candidate is drawn, nothing is written, and no network is used.
"""
from __future__ import annotations

import copy
import hashlib
import inspect
import json
import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from research.g9 import stage2_generator_guard as m  # noqa: E402

import numpy as np  # noqa: E402


class FixtureError(RuntimeError):
    pass


COUNT = 0


def require(ok: bool, message: str) -> None:
    global COUNT
    if not ok:
        raise FixtureError(message)
    COUNT += 1


def refused(fn, label: str, needle: str = "") -> None:
    global COUNT
    try:
        fn()
    except m.GeneratorGuardError as exc:
        if needle and needle not in str(exc):
            raise FixtureError(f"{label}: refused for the wrong reason: {exc}") from exc
        COUNT += 1
        return
    except Exception as exc:
        raise FixtureError(f"{label}: raw {type(exc).__name__} instead of GeneratorGuardError") from exc
    raise FixtureError(f"{label}: accepted")


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")


def independent_content_sha256(record: dict) -> str:
    body = {key: value for key, value in record.items() if key != "content_sha256"}
    return hashlib.sha256(canonical(body)).hexdigest()


def fake(tag: str) -> str:
    return hashlib.sha256(tag.encode("ascii")).hexdigest()


def synthetic_snapshot() -> dict:
    config = {"Build Dependencies": {"blas": {"name": "synthetic-blas", "version": "0.0.1"},
                                     "lapack": {"name": "synthetic-lapack", "version": "0.0.1"}}}
    return {
        "sources": {label: {"path": rel, "sha256": fake("src:" + label)} for label, rel in m.SOURCE_PATHS.items()},
        "runtime": {
            "python": {"implementation": "cpython", "sys_version": "3.12.3 (synthetic) [GCC 0.0]",
                       "version_info": [3, 12, 3, "final", 0], "hexversion": 0x030C03F0},
            "numpy": {"version": "2.4.4", "config": config, "config_sha256": hashlib.sha256(canonical(config)).hexdigest()},
            "numpy_binaries": {"numpy/_core/_multiarray_umath.synthetic.so": fake("bin:umath"),
                               "numpy.libs/libsynthetic_openblas.so": fake("bin:blas")},
            "thread_and_dispatch_environment": {key: None for key in m.THREAD_AND_DISPATCH_KEYS},
        },
    }


def mutated(edit) -> dict:
    snap = synthetic_snapshot()
    edit(snap)
    return snap


def reconfig(snap: dict, version: str) -> None:
    config = snap["runtime"]["numpy"]["config"]
    config["Build Dependencies"]["blas"]["version"] = version
    snap["runtime"]["numpy"]["config_sha256"] = hashlib.sha256(canonical(config)).hexdigest()


# (label, edit, dotted path the guard must name)
DRIFTS = (
    ("generator source", lambda s: s["sources"]["generator"].update(sha256=fake("other-gen")), "sources.generator.sha256"),
    ("validator source", lambda s: s["sources"]["validator"].update(sha256=fake("other-val")), "sources.validator.sha256"),
    ("guard source", lambda s: s["sources"]["guard"].update(sha256=fake("other-guard")), "sources.guard.sha256"),
    ("sys.version", lambda s: s["runtime"]["python"].update(sys_version="3.12.3 (other build)"), "runtime.python.sys_version"),
    ("hexversion", lambda s: s["runtime"]["python"].update(hexversion=0x030C04F0), "runtime.python.hexversion"),
    ("numpy version", lambda s: s["runtime"]["numpy"].update(version="2.4.5"), "runtime.numpy.version"),
    ("numpy config", lambda s: reconfig(s, "0.0.2"), "runtime.numpy.config.Build Dependencies.blas.version"),
    ("binary hash", lambda s: s["runtime"]["numpy_binaries"].update({"numpy.libs/libsynthetic_openblas.so": fake("bin:other")}),
     "runtime.numpy_binaries.numpy.libs/libsynthetic_openblas.so"),
    ("binary added", lambda s: s["runtime"]["numpy_binaries"].update({"numpy/extra.so": fake("bin:extra")}),
     "runtime.numpy_binaries.numpy/extra.so"),
    ("binary removed", lambda s: s["runtime"]["numpy_binaries"].pop("numpy.libs/libsynthetic_openblas.so"),
     "runtime.numpy_binaries.numpy.libs/libsynthetic_openblas.so"),
    ("thread env", lambda s: s["runtime"]["thread_and_dispatch_environment"].update(OPENBLAS_NUM_THREADS="4"),
     "runtime.thread_and_dispatch_environment.OPENBLAS_NUM_THREADS"),
    ("dispatch env", lambda s: s["runtime"]["thread_and_dispatch_environment"].update(OPENBLAS_CORETYPE="Haswell"),
     "runtime.thread_and_dispatch_environment.OPENBLAS_CORETYPE"),
)


def check_record_and_match() -> tuple[dict, str]:
    record = m.build_candidate_record(synthetic_snapshot())
    pinned = independent_content_sha256(record)
    require(record["content_sha256"] == pinned, "record content hash is not independently reproducible")
    require(record["status"] == "unapproved_candidate" and record["owner_approval"] == "absent"
            and "not owner approval" in record["approval_statement"], "record does not declare itself unapproved")
    require(record["candidate_design_fields"] == ["runtime.numpy_binaries", "runtime.thread_and_dispatch_environment",
                                                  "sources.guard"], "candidate-design fields drift")
    require(set(record["sources"]) >= {"generator", "validator"}
            and record["sources"]["generator"]["path"] == "research/g9/stage2_generator.py"
            and record["sources"]["validator"]["path"] == "research/g9/stage2_generation_contract.py",
            "record omits generator or validator source")
    evidence = m.match_snapshot(record, pinned, synthetic_snapshot())
    require(evidence == {"equality": "exact_match", "phases": "single", "record_content_sha256": pinned,
                         "record_status": "unapproved_candidate", "owner_approval": "absent",
                         "authorizes_draw_or_write": "no", "statement": m.EVIDENCE_STATEMENT},
            "match evidence shape or approval wording drift")
    require("Owner approval is absent" in evidence["statement"], "evidence does not separate equality from approval")
    for label, edit, path in DRIFTS:
        refused(lambda edit=edit: m.match_snapshot(record, pinned, mutated(edit)), f"match drift: {label}", path)
    return record, pinned


def check_start_end(record: dict, pinned: str) -> None:
    evidence = m.verify_start_end(record, pinned, synthetic_snapshot(), synthetic_snapshot())
    require(evidence["phases"] == "start_and_end" and evidence["owner_approval"] == "absent"
            and evidence["authorizes_draw_or_write"] == "no", "start/end evidence drift")
    same = synthetic_snapshot()
    refused(lambda: m.verify_start_end(record, pinned, same, same), "one object as start and end", "separate captures")
    for label, edit, path in DRIFTS:
        refused(lambda edit=edit: m.verify_start_end(record, pinned, synthetic_snapshot(), mutated(edit)),
                f"end drift: {label}", "between start and end at: " + path)
        refused(lambda edit=edit: m.verify_start_end(record, pinned, mutated(edit), synthetic_snapshot()),
                f"start drift: {label}", path)
        refused(lambda edit=edit: m.verify_start_end(record, pinned, mutated(edit), mutated(edit)),
                f"consistent drift from record: {label}", path)


def rehashed(record: dict, edit) -> dict:
    forged = copy.deepcopy(record)
    edit(forged)
    forged["content_sha256"] = independent_content_sha256(forged)
    return forged


def check_no_caller_authority(record: dict, pinned: str) -> None:
    snap = synthetic_snapshot()
    for label, edit in (
        ("status owner_approved", lambda r: r.update(status="owner_approved")),
        ("status approved", lambda r: r.update(status="approved")),
        ("owner_approval granted", lambda r: r.update(owner_approval="granted")),
        ("authority=owner key", lambda r: r.update(authority="owner")),
        ("approved_by key", lambda r: r.update(approved_by="owner")),
        ("approval statement reworded", lambda r: r.update(approval_statement="Approved by owner.")),
        ("candidate fields dropped", lambda r: r.update(candidate_design_fields=[])),
        ("schema swapped", lambda r: r.update(schema="decisions_os/g9_stage2_generator_implementation_record/v1")),
    ):
        forged = rehashed(record, edit)
        # Pinning the forged record's own hash still must not make it acceptable.
        refused(lambda forged=forged: m.match_snapshot(forged, forged["content_sha256"], snap), f"forged record: {label}")
    for name in ("match_snapshot", "verify_start_end", "validate_candidate_record", "build_candidate_record"):
        params = set(inspect.signature(getattr(m, name)).parameters)
        require(not params & {"authority", "approval", "approved", "owner", "approved_by"},
                f"{name} exposes an authority-like parameter")
    try:
        m.match_snapshot(record, pinned, snap, authority="owner")
    except TypeError:
        require(True, "")
    else:
        raise FixtureError("match_snapshot accepted an authority keyword")
    tampered = copy.deepcopy(record)
    tampered["runtime"]["numpy"]["version"] = "9.9.9"
    refused(lambda: m.match_snapshot(tampered, pinned, snap), "tampered body, stale hash", "content hash mismatch")
    retampered = rehashed(record, lambda r: r["runtime"]["numpy"].update(version="9.9.9"))
    refused(lambda: m.match_snapshot(retampered, pinned, snap), "rehashed body vs independent pin", "independently pinned")
    refused(lambda: m.match_snapshot(record, pinned.upper(), snap), "uppercase pin", "expected record SHA-256")
    refused(lambda: m.match_snapshot(record, None, snap), "missing pin", "expected record SHA-256")
    refused(lambda: m.match_snapshot(record, fake("elsewhere"), snap), "wrong pin", "independently pinned")


def check_malformed_snapshots(record: dict, pinned: str) -> None:
    cases = (
        ("extra top key", lambda s: s.update(extra={})),
        ("missing validator", lambda s: s["sources"].pop("validator")),
        ("missing generator", lambda s: s["sources"].pop("generator")),
        ("validator path moved", lambda s: s["sources"]["validator"].update(path="research/g9/other.py")),
        ("uppercase source hash", lambda s: s["sources"]["generator"].update(sha256=fake("x").upper())),
        ("bool hexversion", lambda s: s["runtime"]["python"].update(hexversion=True)),
        ("tuple version_info", lambda s: s["runtime"]["python"].update(version_info=(3, 12, 3, "final", 0))),
        ("config hash stale", lambda s: s["runtime"]["numpy"]["config"].update(extra="x")),
        ("binary outside roots", lambda s: s["runtime"]["numpy_binaries"].update({"/usr/lib/libc.so": fake("libc")})),
        ("binary parent escape", lambda s: s["runtime"]["numpy_binaries"].update({"numpy/../x.so": fake("x")})),
        ("no binaries", lambda s: s["runtime"].update(numpy_binaries={})),
        ("unlisted env key", lambda s: s["runtime"]["thread_and_dispatch_environment"].update(HOME="/x")),
        ("int env value", lambda s: s["runtime"]["thread_and_dispatch_environment"].update(OMP_NUM_THREADS=4)),
        ("nan leaf", lambda s: s["runtime"]["numpy"]["config"].update(bad=float("nan"))),
    )
    for label, edit in cases:
        refused(lambda edit=edit: m.validate_snapshot(mutated(edit)), f"malformed snapshot: {label}")
        refused(lambda edit=edit: m.match_snapshot(record, pinned, mutated(edit)), f"malformed observed: {label}")


class StrKey(str):
    pass


def check_binary_keys(record: dict, pinned: str) -> None:
    def only(key: object) -> dict:
        return mutated(lambda s: s["runtime"].update(numpy_binaries={key: "a" * 64}))

    def extra(key: object) -> dict:
        return mutated(lambda s: s["runtime"]["numpy_binaries"].update({key: "a" * 64}))

    # (label, key, needle): non-str keys must be refused before any str method is called on them.
    cases = (
        ("int key", 1, "must be exactly str"),
        ("zero key", 0, "must be exactly str"),
        ("float key", 1.5, "must be exactly str"),
        ("bool key", True, "must be exactly str"),
        ("None key", None, "must be exactly str"),
        ("bytes key", b"numpy/x.so", "must be exactly str"),
        ("tuple key", ("numpy", "x.so"), "must be exactly str"),
        ("frozenset key", frozenset({"numpy/x.so"}), "must be exactly str"),
        ("str subclass key", StrKey("numpy/x.so"), "must be exactly str"),
        ("empty key", "", "outside install roots"),
        ("bare slash", "/", "outside install roots"),
        ("absolute path", "/numpy/x.so", "outside install roots"),
        ("unknown root", "scipy/x.so", "outside install roots"),
        ("root prefix lookalike", "numpyx/x.so", "outside install roots"),
        ("root case drift", "NumPy/x.so", "outside install roots"),
        ("root dot", "./x.so", "outside install roots"),
        ("root dot-dot", "../x.so", "outside install roots"),
        ("bare root", "numpy", "not a canonical relative path"),
        ("bare root slash", "numpy/", "not a canonical relative path"),
        ("bare libs root", "numpy.libs/", "not a canonical relative path"),
        ("double slash", "numpy//x.so", "not a canonical relative path"),
        ("inner double slash", "numpy/linalg//x.so", "not a canonical relative path"),
        ("trailing slash", "numpy/linalg/", "not a canonical relative path"),
        ("leading dot", "numpy/./x.so", "not a canonical relative path"),
        ("inner dot", "numpy/linalg/./x.so", "not a canonical relative path"),
        ("trailing dot", "numpy/linalg/.", "not a canonical relative path"),
        ("only dot", "numpy/.", "not a canonical relative path"),
        ("leading dot-dot", "numpy/../x.so", "not a canonical relative path"),
        ("inner dot-dot", "numpy/linalg/../x.so", "not a canonical relative path"),
        ("trailing dot-dot", "numpy/linalg/..", "not a canonical relative path"),
        ("libs escape", "numpy.libs/../numpy/x.so", "not a canonical relative path"),
    )
    for label, key, needle in cases:
        for shape, build in (("sole", only), ("extra", extra)):
            refused(lambda build=build, key=key: m.validate_snapshot(build(key)),
                    f"binary key {shape}: {label}", needle)
            refused(lambda build=build, key=key: m.match_snapshot(record, pinned, build(key)),
                    f"observed binary key {shape}: {label}", needle)
            refused(lambda build=build, key=key: m.build_candidate_record(build(key)),
                    f"record binary key {shape}: {label}", needle)
    # Canonical nested and dotted-name components remain acceptable.
    for key in ("numpy/linalg/_umath_linalg.synthetic.so", "numpy.libs/libsynthetic.so.0",
                "numpy/.hidden.so", "numpy/..x.so", "numpy/x..so"):
        body = m.validate_snapshot(only(key))
        require(body["runtime"]["numpy_binaries"] == {key: "a" * 64}, f"canonical binary key refused: {key!r}")


def check_no_draw_or_cli() -> None:
    source = (ROOT / "research/g9/stage2_generator_guard.py").read_text(encoding="ascii")
    for forbidden in ("__main__", "argparse", "sys.argv", "from research.g9", "import research",
                      "sample_return_covariance", "screen_attempt", "sector_blocks", "multivariate_normal",
                      "write_text", "write_bytes", "mkdir", "unlink", "os.replace", "os.rename", "shutil",
                      "subprocess", "socket", "urllib", "http", "kaggle", "open(\"w", "\"wb\"", "'wb'", "\"w\"", "'w'"):
        require(forbidden not in source, f"guard source contains forbidden token {forbidden!r}")
    require(source.count("os.environ") == 1, "guard reads the environment outside its allowlist expression")
    require(not hasattr(m, "main") and "research.g9.stage2_generator" not in {
        getattr(value, "__name__", "") for value in vars(m).values()}, "guard exposes a CLI or imports the generator")


def independent_binaries() -> dict[str, str]:
    package = Path(np.__file__).resolve().parent
    found: dict[str, str] = {}
    for label, root in (("numpy", package), ("numpy.libs", package.parent / "numpy.libs")):
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if path.is_file() and (path.name.endswith(".so") or ".so." in path.name):
                found[f"{label}/{path.relative_to(root).as_posix()}"] = hashlib.sha256(path.read_bytes()).hexdigest()
    return found


def check_actual_capture() -> dict:
    saved = {key: os.environ.get(key) for key in m.THREAD_AND_DISPATCH_KEYS}
    start = m.capture_snapshot()
    end = m.capture_snapshot()
    for label, rel in m.SOURCE_PATHS.items():
        require(start["sources"][label]["sha256"] == hashlib.sha256((ROOT / rel).read_bytes()).hexdigest(),
                f"actual {label} hash is not independently reproduced")
    python = start["runtime"]["python"]
    require(python["sys_version"] == sys.version and python["implementation"] == sys.implementation.name
            and python["version_info"] == list(sys.version_info) and python["hexversion"] == sys.hexversion,
            "actual interpreter identity drift")
    numpy_info = start["runtime"]["numpy"]
    require(numpy_info["version"] == np.__version__
            and numpy_info["config_sha256"] == hashlib.sha256(canonical(np.__config__.CONFIG)).hexdigest(),
            "actual NumPy version/config drift")
    require(start["runtime"]["numpy_binaries"] == independent_binaries(), "actual NumPy binary hashes not independently reproduced")
    require(start["runtime"]["thread_and_dispatch_environment"] == saved, "actual thread/dispatch environment drift")
    record = m.build_candidate_record(start)
    pinned = independent_content_sha256(record)
    evidence = m.verify_start_end(record, pinned, start, end)
    require(evidence["owner_approval"] == "absent" and evidence["authorizes_draw_or_write"] == "no",
            "actual start/end evidence overstates authority")
    # Real in-process drift: a thread variable changed between start and a fresh end capture.
    key = "OPENBLAS_NUM_THREADS"
    try:
        os.environ[key] = "3" if saved[key] != "3" else "5"
        drifted = m.capture_snapshot()
    finally:
        if saved[key] is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = saved[key]
    refused(lambda: m.verify_start_end(record, pinned, start, drifted), "actual thread-env drift",
            "runtime.thread_and_dispatch_environment." + key)
    return {"record": record, "pinned": pinned}


def check_numpy_libs_install_root() -> None:
    """OWNER POLICY: numpy.libs is a real dir, or a symlink resolving inside site-packages.

    Every case is built in a TemporaryDirectory, so the real NumPy install is
    never touched.  The synthetic site-packages holds numpy/__init__.py, which
    stands in for np.__file__.
    """
    import tempfile

    with tempfile.TemporaryDirectory(prefix="g9-numpylibs-") as d:
        base = Path(d).resolve()
        # A separate tree outside the site-packages, to be the outside target.
        outside = base / "outside"
        (outside / "real").mkdir(parents=True)
        (outside / "real" / "evil.so").write_bytes(b"synthetic-outside-binary")
        (outside / "real" / "not_a_binary.txt").write_bytes(b"synthetic")

        def site(label: str) -> Path:
            sp = base / label
            (sp / "numpy").mkdir(parents=True)
            (sp / "numpy" / "__init__.py").write_bytes(b"# synthetic numpy\n")
            (sp / "numpy" / "_core.so").write_bytes(b"synthetic-core-binary")
            return sp

        # Accepted roots must actually feed the binary capture.  np.__file__ is
        # the only channel _numpy_install_roots reads by default, so pointing it
        # at the synthetic package exercises the real function end to end
        # without touching the real NumPy install.  Always restored.
        def as_package(sp: Path, body):
            saved = np.__file__
            np.__file__ = str(sp / "numpy" / "__init__.py")
            try:
                return body()
            finally:
                np.__file__ = saved

        # 1. A real numpy.libs directory is accepted.
        real = site("sp_real")
        (real / "numpy.libs").mkdir()
        (real / "numpy.libs" / "libreal.so").write_bytes(b"synthetic-bundled-binary")
        roots = m._numpy_install_roots(real / "numpy" / "__init__.py")
        require(roots == [("numpy", (real / "numpy").resolve()),
                          ("numpy.libs", (real / "numpy.libs").resolve())],
                f"real numpy.libs directory not accepted as an install root: {roots}")
        keys = set(as_package(real, m.capture_numpy_binaries))
        require(keys == {"numpy/_core.so", "numpy.libs/libreal.so"},
                f"real numpy.libs binaries not captured: {sorted(keys)}")
        # The default (no argument) must be this process's NumPy, untouched.
        require(m._numpy_install_roots() == m._numpy_install_roots(Path(np.__file__)),
                "_numpy_install_roots default differs from the explicit NumPy path")

        # 2. A symlink whose target stays inside site-packages is accepted and
        #    followed; its binaries are recorded under their resolved path.
        inside = site("sp_inside")
        (inside / "numpy.libs.real").mkdir()
        (inside / "numpy.libs.real" / "libinside.so").write_bytes(b"synthetic-inside-binary")
        (inside / "numpy.libs").symlink_to(inside / "numpy.libs.real", target_is_directory=True)
        roots = m._numpy_install_roots(inside / "numpy" / "__init__.py")
        require(roots == [("numpy", (inside / "numpy").resolve()),
                          ("numpy.libs", (inside / "numpy.libs.real").resolve())],
                f"inside-site-packages symlinked numpy.libs not accepted: {roots}")
        keys = set(as_package(inside, m.capture_numpy_binaries))
        require(keys == {"numpy/_core.so", "numpy.libs/libinside.so"},
                f"inside symlinked numpy.libs binaries not captured: {sorted(keys)}")

        # 3. A symlink resolving OUTSIDE the site-packages is refused, so outside
        #    binaries are never hashed.  A non-directory target is refused too.
        escaped = site("sp_outside")
        (escaped / "numpy.libs").symlink_to(outside / "real", target_is_directory=True)
        refused(lambda: m._numpy_install_roots(escaped / "numpy" / "__init__.py"),
                "numpy.libs symlink resolving outside site-packages",
                "resolves outside the site-packages directory")
        notdir = site("sp_notdir")
        (notdir / "numpy.libs").symlink_to(outside / "real" / "evil.so")
        refused(lambda: m._numpy_install_roots(notdir / "numpy" / "__init__.py"),
                "numpy.libs symlinked to a file", "resolves outside the site-packages directory")

        # 4. A dangling numpy.libs symlink is refused, not silently skipped.
        dangling = site("sp_dangling")
        (dangling / "numpy.libs").symlink_to(dangling / "absent-target", target_is_directory=True)
        refused(lambda: m._numpy_install_roots(dangling / "numpy" / "__init__.py"),
                "dangling numpy.libs symlink", "dangling symlink: numpy.libs")

        # 5. Absent numpy.libs is not a failure: the numpy root alone suffices.
        bare = site("sp_absent")
        require(m._numpy_install_roots(bare / "numpy" / "__init__.py") == [("numpy", (bare / "numpy").resolve())],
                "absent numpy.libs was not simply omitted")

        # 6. A sibling whose name merely PREFIXES the site-packages directory is
        #    outside it; string-prefix containment would wrongly accept it.
        prefix = base / "sp_prefix"
        (prefix / "numpy").mkdir(parents=True)
        (prefix / "numpy" / "__init__.py").write_bytes(b"# synthetic numpy\n")
        lookalike = base / "sp_prefix_outside"
        (lookalike / "real").mkdir(parents=True)
        (lookalike / "real" / "evil.so").write_bytes(b"synthetic-outside-binary")
        (prefix / "numpy.libs").symlink_to(lookalike / "real", target_is_directory=True)
        refused(lambda: m._numpy_install_roots(prefix / "numpy" / "__init__.py"),
                "numpy.libs symlink to a prefix lookalike directory",
                "resolves outside the site-packages directory")

    # 7. A symlinked binary INSIDE an accepted root that points outside it is
    #    refused by the per-binary containment check, whatever the root is.
    with tempfile.TemporaryDirectory(prefix="g9-binescape-") as d:
        base = Path(d).resolve()
        outside = base / "outside"
        outside.mkdir()
        (outside / "evil.so").write_bytes(b"synthetic-outside-binary")
        package = base / "sp" / "numpy"
        package.mkdir(parents=True)
        (package / "__init__.py").write_bytes(b"# synthetic numpy\n")
        (package / "real.so").write_bytes(b"synthetic-core-binary")
        (package / "escape.so").symlink_to(outside / "evil.so")
        saved = np.__file__
        np.__file__ = str(package / "__init__.py")
        try:
            refused(m.capture_numpy_binaries, "binary symlinked outside its install root",
                    "escapes its install root")
        finally:
            np.__file__ = saved


def check_documented_symlink_policy() -> None:
    """The documented symlink policy must state the numpy.libs rule in the module."""
    doc = m.__doc__ or ""
    require("numpy.libs" in doc and "site-packages" in doc and "refused" in doc,
            "guard docstring does not document the numpy.libs symlink policy")
    require(m._numpy_install_roots.__doc__ and "numpy.libs" in m._numpy_install_roots.__doc__
            and "refused" in m._numpy_install_roots.__doc__,
            "_numpy_install_roots does not document the numpy.libs symlink policy")


def check_review_regressions() -> None:
    """Defects found by independent review of the candidate guard."""
    import tempfile, types

    # Unreadable file: typed refusal, not a bare OSError.
    refused(lambda: m._file_sha256(Path("/nonexistent-g9-guard/stage2_generator.py")),
            "missing source file", "cannot read")

    # Path hijack: a module named stage2_generator.py imported from anywhere
    # other than the hashed file must be refused. The fake carries only a
    # __file__; nothing is executed.
    with tempfile.TemporaryDirectory(prefix="g9-hijack-") as d:
        fake = types.ModuleType("_g9_fixture_hijacked_generator")
        fake.__file__ = str(Path(d) / "stage2_generator.py")
        sys.modules["_g9_fixture_hijacked_generator"] = fake
        try:
            refused(m.capture_sources, "hijacked generator import", "is imported from")
        finally:
            del sys.modules["_g9_fixture_hijacked_generator"]
    capture = m.capture_sources()
    require(set(capture) == set(m.SOURCE_PATHS), "clean capture after hijack removed")

    # Symlinked binary: recorded under its RESOLVED name, never as a separate
    # binary carrying its target's hash.
    with tempfile.TemporaryDirectory(prefix="g9-binroot-") as d:
        root = Path(d).resolve()
        (root / "real.so").write_bytes(b"synthetic-binary")
        (root / "link.so").symlink_to(root / "real.so")
        original = m._numpy_install_roots
        m._numpy_install_roots = lambda: [("numpy", root)]
        try:
            keys = set(m.capture_numpy_binaries())
            require(keys == {"numpy/real.so"}, f"symlink recorded under its own name: {sorted(keys)}")
        finally:
            m._numpy_install_roots = original

    # Defect: Untyped exceptions.
    original_np_file = np.__file__
    np.__file__ = None
    try:
        refused(m.capture_snapshot, "untyped exception Path(None)", "capture failed: TypeError")
    finally:
        np.__file__ = original_np_file

    original_config = getattr(np, '__config__', None)
    try:
        del np.__config__
        refused(m.capture_snapshot, "untyped exception no __config__", "capture failed: AttributeError")
    finally:
        if original_config:
            np.__config__ = original_config

    # Defect: canonical_bytes injectivity and strict walk in _differences.
    # A dictionary with an int key vs string key should not match, and canonical_bytes should refuse non-str keys.
    bad_snap = synthetic_snapshot()
    bad_snap["runtime"]["numpy"]["config"]["int_key"] = {1: "x"} # non-str key deep inside
    bad_snap["runtime"]["numpy"]["config_sha256"] = hashlib.sha256(canonical(bad_snap["runtime"]["numpy"]["config"])).hexdigest()
    refused(lambda: m.build_candidate_record(bad_snap), "canonical_bytes non-str key", "all dictionary keys must be strings")
    
    # We also check _differences strict walk.  The list branch is pinned by a
    # change in LENGTH, which the terminal type() comparison cannot see (a
    # tuple is not a list, so the list branch is not what reports it).  The
    # type() half of the terminal comparison is separately pinned, because
    # json.dumps renders a list and a one-element tuple identically.
    diff = m._differences({"a": -0.0}, {"a": 0.0}, "")
    require(diff == ["a"], "strict walk failed to detect -0.0 vs 0.0 difference")
    require(m._differences({"a": [1, 2]}, {"a": [1]}, "") == ["a"],
            "strict walk failed to detect a shortened list")
    require(m._differences({"a": [1]}, {"a": [1, 2]}, "") == ["a"],
            "strict walk failed to detect a lengthened list")
    require(m._differences({"a": [[1, 2], [3]]}, {"a": [[1], [3]]}, "") == ["a[0]"],
            "strict walk failed to descend into lists and report the differing index")
    require(m._differences({"a": [1]}, {"a": (1,)}, "") == ["a"],
            "strict walk failed to detect list vs tuple difference")

    # Defect: non-atomic capture / publish-once
    # Ensure capture_snapshot builds, VALIDATES, and then publishes, never returning a malformed state.
    original_np_version = np.__version__
    np.__version__ = ""
    try:
        refused(m.capture_snapshot, "malformed state leaked by capture_snapshot", "runtime.numpy.version malformed")
    finally:
        np.__version__ = original_np_version

    # Defect: Symlink walk and unreadable directories
    if os.geteuid() == 0:
        print("Note: skipping unreadable numpy root check because uid is 0")
    else:
        with tempfile.TemporaryDirectory(prefix="g9-onerror-") as d:
            root = Path(d).resolve()
            os.chmod(root, 0o000)
            original_roots = m._numpy_install_roots
            m._numpy_install_roots = lambda: [("numpy", root)]
            try:
                refused(m.capture_numpy_binaries, "unreadable numpy root", "walk error: PermissionError")
            finally:
                m._numpy_install_roots = original_roots
                os.chmod(root, 0o755)

    with tempfile.TemporaryDirectory(prefix="g9-symlink-") as d:
        root = Path(d).resolve()
        (root / "dir").mkdir()
        (root / "dir" / "link.so").symlink_to("target-does-not-exist")
        original_roots = m._numpy_install_roots
        m._numpy_install_roots = lambda: [("numpy", root)]
        try:
            refused(m.capture_numpy_binaries, "dangling symlinked binary in walk", "dangling symlink in numpy binaries")
        finally:
            m._numpy_install_roots = original_roots



def pycache_count() -> int:
    return sum(1 for _ in (ROOT / "research").rglob("*.pyc"))


def main() -> int:
    before = pycache_count()
    record, pinned = check_record_and_match()
    check_start_end(record, pinned)
    check_no_caller_authority(record, pinned)
    check_malformed_snapshots(record, pinned)
    check_binary_keys(record, pinned)
    check_numpy_libs_install_root()
    check_documented_symlink_policy()
    check_no_draw_or_cli()
    check_review_regressions()
    actual = check_actual_capture()
    require(pycache_count() == before, "fixture wrote bytecode")
    require(not (ROOT / "research/g9/stage2_generation").exists(), "fixture must not create a generation artifact directory")
    record = actual["record"]
    binaries = record["runtime"]["numpy_binaries"]
    print(f"optimize={sys.flags.optimize} checks={COUNT}")
    for label in m.SOURCE_PATHS:
        print(f"source {record['sources'][label]['path']} sha256={record['sources'][label]['sha256']}")
    print(f"sys.version={record['runtime']['python']['sys_version']!r}")
    print(f"numpy={record['runtime']['numpy']['version']} config_sha256={record['runtime']['numpy']['config_sha256']}")
    print(f"numpy_binaries={len(binaries)} map_sha256={hashlib.sha256(canonical(binaries)).hexdigest()}")
    for key in sorted(binaries):
        if key.startswith("numpy.libs/"):
            print(f"  {key} sha256={binaries[key]}")
    print(f"thread_and_dispatch_environment={json.dumps(record['runtime']['thread_and_dispatch_environment'], sort_keys=True)}")
    print(f"candidate_record content_sha256={actual['pinned']} status={record['status']} owner_approval={record['owner_approval']}")
    print("PASS Stage-2 generator guard fixtures; synthetic snapshots plus one actual capture; "
          "UNAPPROVED CANDIDATE, equality evidence only, no owner approval, no draw or write")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

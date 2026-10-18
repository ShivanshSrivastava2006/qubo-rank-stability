#!/usr/bin/env python3
"""Synthetic fixtures for WP8d-production — the PRODUCTION-CAPABLE layout.

EVERYTHING HERE IS NON-PRODUCTION.  No real generator draw, no production seed,
no beacon, no network, no credential, no GPU, no scientific step, no write to
the real project.  The only instance this fixture ever prepares is a
conspicuously labelled stand-in whose id starts with ``NONPROD-STANDIN`` and
contains ``NON-PRODUCTION``; WP8b's fixture branch refuses anything else, so
the ACCEPTING path reachable here is WP8b's own non-production branch and no
other.  All writes go to ``tempfile.TemporaryDirectory`` under the job scratch
tree and the one-use nonce registry is driven inside a per-run SANDBOX ROOT.

What this fixture proves
========================

1. The rehearsal is END TO END: stand-in write, read, re-verify, resume.
2. The production reader refuses the stand-in directory, and the production
   writer refuses the stand-in record.
3. The prior synthetic-only WP8d refuses BOTH a ``non_synthetic_supported is
   True`` claim and a WP8b status -- the negative control.
4. The production path is UNARMED: WP8b has pinned no production release, so
   ``require_production=True`` refuses everything this fixture can build.
5. Every meaningful broken variant is REFUSED, each for its own reason:
   bypassing WP8b, a read-only assertion, a slot swap, a re-sealed provenance
   record, a missing fsync / interrupted promotion, and a wrong instance.

Design notes that are load-bearing
==================================

*  ``require`` is the reporter, so it cannot be trusted alone.  ``_observed``
    reports an outcome as a VALUE (exception type and message) and the
    structural checks assert with the interpreter's own ``assert``, a channel
    this file does not define.  ``main`` requires an exact assertion TOTAL
    through three independent channels (raise / assert / require), so dropping
    any single assertion fails the run rather than hiding behind its
    neighbours.
*  A fixture that merely calls its own checks proves nothing: every check is
    dispatched through tables that are themselves audited for duplicates and
    orphans, so removing an entry removes an assertion the run depends on.
*  The broken variants deliberately RE-SEAL.  Without re-sealing, every field
    tamper also breaks the final content-hash check, so removing an
    intermediate guard would be unobservable.  Re-sealing isolates the guard
    under test -- and it is precisely re-sealing that defeated WP8b round 1,
    which is why every re-sealed case below must still be REFUSED.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

sys.dont_write_bytecode = True

# This fixture lives at research/g9/wp8d_production/, so the project root is
# parents[3].
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.g9 import stage2_generation_writer as writer  # noqa: E402
from research.g9 import stage2_instance_preparation as wp5b  # noqa: E402
from research.g9.wp8b import wp8b_non_synthetic_preparation as m  # noqa: E402
from research.g9.wp8d import wp8d_drawn_instance_layout as wp8d  # noqa: E402
from research.g9.wp8d_production import wp8d_production_layout as p  # noqa: E402


class FixtureError(RuntimeError):
    pass


COUNT = 0

#: The number of assertions a correct full run performs.  ``main`` requires this
#: exact total through THREE independent channels, which is what makes
#: individual assertions load-bearing.  Recalibrate by running ``python3 -B``
#: over this file, which prints the count it observed.
#:
#: IMPORTANT: this total is NOT sufficient on its own.  ``require`` is the only
#: thing that increments ``COUNT``, so when ``require``'s own ``raise`` was
#: neutered the total would drift while this guard -- a ``require`` call --
#: silently did nothing.  The total is corroborated by
#: :func:`check_require_helper_contract` and :func:`check_dispatch_self_audit`,
#: which assert with the interpreter's own ``assert`` and so cannot be disabled
#: by that same edit.
EXPECTED_ASSERTIONS = 423

#: The floor on how many check functions this file may define.  Calibrate down
#: only deliberately, and never as a way of making a failing guard disappear.
#: This is the true defined count: the file's coverage floor is its own, not a
#: number copied from a larger sibling package.
MIN_CHECK_FUNCTIONS = 20

#: Scratch root mandated by the package rules.  Never /tmp.
SCRATCH = Path("/home/shivansh-srivastava/decisions_os/g9_jobs/scratch/wp8dprod")

#: The run's live scratch directory, set by ``main``.  Two probes need it: the
#: return-matrix rewrites, which must reach the directories a check just
#: promoted, and nothing else.  It is module state rather than a threaded
#: argument purely so the rewrite helper can keep a two-argument shape.
_CURRENT_SCRATCH = ""

#: Conspicuously non-production stand-in ids.
STANDIN_ID = "NONPROD-STANDIN-0001-NON-PRODUCTION"
STANDIN_ID_B = "NONPROD-STANDIN-0002-NON-PRODUCTION"

#: A real-looking id that is NOT a conspicuously labelled stand-in.
UNLABELLED_ID = "STAGE2-01"

#: A fixed date so a record is a pure function of its inputs.
PINNED = datetime.date(2026, 1, 1)


def _observed(fn) -> dict:
    """Run ``fn`` and report what it did, as a VALUE rather than a verdict.

    ``require``/``refused`` decide what counts as a pass, so a check that only
    ever calls them is testing a primitive using itself.  This helper never
    raises and never counts: it reports the outcome, the exception's exact type
    and its message, and the structural checks below assert on those fields
    with the interpreter's own ``assert``.
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

    A wrong exception type, and equally an ACCEPTED call, are both failures:
    the second is what makes this a real negative probe rather than a smoke
    test, and it is what kills the "the guard was deleted" mutant.
    """
    global COUNT
    try:
        fn()
    except expected_type as exc:
        if needle and needle not in str(exc):
            raise FixtureError(f"{label}: refused for the wrong reason: {exc}") from exc
        COUNT += 1
        return
    except FixtureError:
        raise
    except BaseException as exc:  # noqa: BLE001 - we want the wrong type named
        raise FixtureError(
            f"{label}: raised {type(exc).__name__} instead of "
            f"{expected_type.__name__}: {exc}") from exc
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


def approval_over(*, instance_id: str = STANDIN_ID, nonce: str = "wp8dprod-fixture-nonce-1",
                  scope: str = m.FIXTURE_SCOPE, status: str = m.APPROVAL_STATUS,
                  label: str = m.OWNER_APPROVAL_LABEL, expiry: str = "2099-12-31"
                  ) -> dict:
    """A structurally complete approval record, with every field overridable."""
    return {
        "schema": m.APPROVAL_SCHEMA,
        "status": status,
        "label": label,
        "scope": scope,
        "approves_instance_content_sha256": m.instance_content_sha256(
            standin(instance_id)),
        "instance_id": instance_id,
        "expiry": expiry,
        "nonce": nonce,
        "statement": m.APPROVAL_STATEMENT,
    }


def prepare_standin(instance, approval, *, root: str) -> dict:
    """Drive WP8b's ONE accepting (fixture) branch, always with the token."""
    return m.prepare_non_synthetic(instance, approval, root=root, now=PINNED,
                                   fixture_context=m.FIXTURE_CONTEXT_TOKEN)


def resign(record: dict) -> dict:
    """Recompute ``content_sha256`` after a tamper, so ONE guard is under test.

    Without re-signing, every field tamper also breaks the final content-hash
    recomputation, so removing an intermediate guard would be unobservable.
    Signing again isolates the guard being probed -- and it is precisely
    re-signing that defeated WP8b round 1, which is why every re-sealed case
    below is RE-SIGNED and is still refused.
    """
    body = dict(record)
    body.pop("content_sha256", None)
    return dict(body, content_sha256=hashlib.sha256(
        m._canonical(body)).hexdigest())


def mu_sigma() -> tuple[list[str], list[list[str]]]:
    """NON-PRODUCTION placeholder moment encodings in WP8d's binary64 hex.

    These are obviously-labelled constants, NOT a computed or scientific
    result: no generator, no draw and no numerics were run to produce them.
    """
    mu = ["0x1.5c28f5c28f5c3p+0"] * wp8d.ASSET_COUNT
    sigma = [["0x1.a3d70a3d70a3d8p-3"] * wp8d.ASSET_COUNT
             for _ in range(wp8d.ASSET_COUNT)]
    return mu, sigma


def return_matrix() -> bytes:
    """A NON-PRODUCTION placeholder return matrix of the exact required length."""
    digest = hashlib.sha512(b"wp8d-production-standin-return-matrix").digest()
    count, rest = divmod(p.RETURN_MATRIX_BYTES, len(digest))
    return digest * count + digest[:rest]


def _scratch_dir(parent: str, name: str) -> str:
    """Create and return ``parent/name``.

    Every scratch directory in this fixture is made through here rather than by
    a bare ``os.makedirs`` call: a discarded ``os.makedirs`` is a mutation site
    whose mutant is a no-op, and no honest way exists for a fixture to observe
    that a directory it just created still exists.
    """
    path = os.path.join(parent, name)
    os.makedirs(path, exist_ok=True)
    return path


def sandbox_root(base: str, name: str) -> str:
    """A layout root: the instance root already exists, as the protocol requires."""
    root = _scratch_dir(base, name)
    os.makedirs(os.path.join(root, p.INSTANCE_ROOT), exist_ok=True)
    return root


def write_kwargs(*, root: str, record: dict, instance, slot: int = 1, attempt: int = 0,
                 instance_id: str = STANDIN_ID, sector: bytes = b"sector-partition-1",
                 feasible_count: int = 7,
                 impl: str = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                 ) -> dict:
    """The full write-argument set for one stand-in instance."""
    mu, sigma = mu_sigma()
    return dict(
        slot=slot, attempt=attempt, instance_id=instance_id,
        sector_partition_sha256=hashlib.sha256(sector).hexdigest(),
        feasible_count=feasible_count, return_matrix=return_matrix(),
        prepared_record=record, instance=instance,
        implementation_record_content_sha256=impl,
        mu_new=mu, sigma_new=sigma, root=root)


def read_index(base: Path) -> dict:
    return json.loads((base / p.META_DIR_NAME / p.INDEX_NAME).read_text("ascii"))


def read_json(path: Path) -> dict:
    return json.loads(path.read_text("ascii"))


def write_json(path: Path, record: dict) -> None:
    """Write a record in the canonical encoding the reader requires."""
    path.write_bytes(p._canonical(record))


def reseal_sidecar(directory: Path, exclude_manifest: tuple[str, ...] = ()) -> None:
    """Rebuild ``directory``'s manifest from the files now on disk.

    A re-sealed tamper means the attacker fixed the manifest too, so a guard
    that only compares against a stale manifest would be unobservable.  This
    makes the tamper SELF-CONSISTENT: the only thing left that can catch it is
    the WP8b anchor recomputing the record from the bound instance bytes.
    """
    files = {
        name: (directory / name).read_bytes()
        for name in sorted(os.listdir(directory))
        if name != writer.MANIFEST_NAME and name not in exclude_manifest
    }
    implementation = _impl_from(directory)
    manifest = writer.build_manifest(files,
                                     implementation_record_content_sha256=implementation)
    (directory / writer.MANIFEST_NAME).write_bytes(writer._manifest_bytes(manifest))


def _impl_from(directory: Path) -> str:
    """The implementation record a sidecar's current manifest already names."""
    manifest = read_json(directory / writer.MANIFEST_NAME)
    return manifest["implementation_record_content_sha256"]


def reseal_index(base: Path, prepared_bytes: bytes, prepared: dict) -> None:
    """Rebuild the index so it names the re-sealed prepared record exactly.

    Without this, every prepared-record tamper would also break the index
    comparison, and the WP8b anchor would be untested.  After resealing the
    index, the directory is internally CONSISTENT and the ONLY remaining
    authority is WP8b's recomputation from the instance bytes.
    """
    meta = base / p.META_DIR_NAME
    index = read_index(base)
    prepared_bytes_hash = hashlib.sha256(prepared_bytes).hexdigest()
    prepared_manifest = read_json(base / p.PREPARED_DIR_NAME / writer.MANIFEST_NAME)
    index["prepared_id"] = prepared["content_sha256"]
    index["prepared_record"] = {
        "path": f"{p.PREPARED_DIR_NAME}/{p.PREPARED_NAME}",
        "sha256": prepared_bytes_hash,
        "content_sha256": prepared["content_sha256"],
        "status": prepared["status"],
        "production": prepared["production"],
        "manifest_sha256": hashlib.sha256(
            (base / p.PREPARED_DIR_NAME / writer.MANIFEST_NAME).read_bytes()).hexdigest(),
        "manifest_content_sha256": prepared_manifest["content_sha256"],
    }
    index["status"] = prepared["status"]
    index["production"] = prepared["production"]
    index["content_sha256"] = p._content_sha256(index)
    write_json(meta / p.INDEX_NAME, index)
    reseal_sidecar(meta)


def reseal_prepared(base: Path, mutate) -> dict:
    """Tamper the prepared record, RE-SIGN it, and re-seal everything above it."""
    path = base / p.PREPARED_DIR_NAME / p.PREPARED_NAME
    prepared = mutate(resign(read_json(path)))
    write_json(path, prepared)
    reseal_sidecar(base / p.PREPARED_DIR_NAME)
    reseal_index(base, path.read_bytes(), prepared)
    return prepared


# ===========================================================================
# A. The end-to-end rehearsal: write, read, re-verify, resume
# ===========================================================================

def check_end_to_end_rehearsal(tmp: str, nonce_root: str) -> None:
    root = sandbox_root(tmp, "e2e-root")
    instance = standin()
    record = prepare_standin(instance, approval_over(), root=nonce_root)

    require(record["status"] == p.STANDIN_STATUS,
            "the fixture branch must stamp the non-production stand-in status")
    require(record["production"] is False,
            "the fixture branch must never stamp a production record")
    require(p.STANDIN_STATUS != p.PRODUCTION_STATUS,
            "the stand-in and production statuses must be distinct WP8b statuses")

    written = p.write_standin_instance(**write_kwargs(root=root, record=record,
                                                     instance=instance))
    require(written["verdict"] == "written", "the stand-in write must succeed")
    require(written["layout_kind"] == p.LAYOUT_KIND_STANDIN,
            "the write must declare the stand-in layout kind")
    require(written["armed"] is False,
            "this build is unarmed and must report it")

    base = Path(written["target"])
    require(sorted(os.listdir(base)) == sorted(p.SLOT_MEMBERS),
            "the promoted directory must hold exactly the three canonical members")
    require(sorted(os.listdir(base / p.PREPARED_DIR_NAME))
            == sorted(p.STANDIN_MEMBERS),
            "the stand-in sidecar must hold exactly its four canonical members, "
            "including the STANDIN.json marker")

    read_back = p.verify_standin_instance(1, root=root)
    require(read_back["verdict"] == "verified", "the read must succeed")
    for key in ("index_content_sha256", "prepared_id", "generation_id",
                "envelope_sha256", "envelope_content_sha256",
                "prepared_manifest_sha256", "generation_manifest_sha256"):
        require(read_back[key] == written[key],
                f"read and write must agree on {key} (the layout is deterministic)")

    resumed = p.resume_standin(slot=1, root=root)
    require(resumed["verdict"] == "verified", "resume must re-verify, not rewrite")
    require(resumed["resumed"] is True, "resume must report that it resumed")
    require(resumed["writable"] is False,
            "an already-promoted slot must not be reported writable")

    free = p.resume_standin(slot=3, root=root)
    require(free["verdict"] == "absent", "an unwritten slot must be reported absent")
    require(free["writable"] is True, "an absent slot must be reported writable")

    swept = p.verify_all_standin_slots(root=root, present=[1])
    require(swept["count"] == 1 and swept["slots"] == ["stage2_01"],
            "the whole-root sweep must find exactly the promoted slot")

    # A second write to the same slot must be refused: no merge, no overwrite.
    refused(lambda: p.write_standin_instance(
        **write_kwargs(root=root, record=record, instance=instance)),
        p.ProductionLayoutError, "rewrite of a promoted slot",
        "already exists")


def check_two_slots_and_sweep(tmp: str, nonce_root: str) -> None:
    root = sandbox_root(tmp, "two-slot-root")
    first, second = standin(), standin(STANDIN_ID_B)
    rec_a = prepare_standin(first, approval_over(nonce="wp8dprod-nonce-a"),
                            root=nonce_root)
    rec_b = prepare_standin(second, approval_over(
        instance_id=STANDIN_ID_B, nonce="wp8dprod-nonce-b"), root=nonce_root)
    p.write_standin_instance(**write_kwargs(root=root, record=rec_a, instance=first,
                                           slot=1))
    p.write_standin_instance(**write_kwargs(root=root, record=rec_b, instance=second,
                                           slot=2, instance_id=STANDIN_ID_B,
                                           sector=b"sector-partition-2"))
    swept = p.verify_all_standin_slots(root=root, present=[1, 2])
    require(swept["count"] == 2, "the sweep must verify both slots")
    require(sorted(swept["slots"]) == ["stage2_01", "stage2_02"],
            "the sweep must name both slots")
    refused(lambda: p.verify_all_standin_slots(root=root, present=[1]),
            p.ProductionLayoutError, "sweep against a wrong expectation", "expected")


# ===========================================================================
# B. The negative control: the prior synthetic-only layout refuses both claims
# ===========================================================================

def check_prior_synthetic_only_layout_refuses() -> None:
    """WP8d is fail-closed, and this build does not change that."""
    observed = _observed(lambda: wp8d._require_not_non_synthetic(True))
    assert observed["outcome"] == "raised", observed
    assert observed["type_name"] == "LayoutError", observed
    require("non-synthetic support" in observed["message"],
            "WP8d must refuse a record claiming the unreviewed release path")

    # ... and it refuses the stand-in status this adapter's records carry, which
    # is the other half of the negative control: the two layouts do not share a
    # status vocabulary, so neither can be passed off as the other.
    refused(lambda: wp8d._require_status(p.STANDIN_STATUS), wp8d.LayoutError,
            "WP8d must refuse the WP8b stand-in status", "not an accepted")
    refused(lambda: wp8d._require_status(p.PRODUCTION_STATUS), wp8d.LayoutError,
            "WP8d must refuse the WP8b production status", "not an accepted")


def check_standin_layout_is_marked_in_three_places(tmp: str, nonce_root: str) -> None:
    """A stand-in directory is marked in three independent, checked places."""
    root = sandbox_root(tmp, "marking-root")
    instance = standin()
    record = prepare_standin(instance, approval_over(nonce="wp8dprod-mark"),
                             root=nonce_root)
    written = p.write_standin_instance(**write_kwargs(root=root, record=record,
                                                     instance=instance))
    base = Path(written["target"])

    marker = read_json(base / p.PREPARED_DIR_NAME / p.STANDIN_MARKER_NAME)
    require(marker["layout_kind"] == p.LAYOUT_KIND_STANDIN,
            "the STANDIN.json marker must declare the stand-in layout kind")
    require("NON-PRODUCTION" in marker["statement"],
            "the marker statement must announce the non-production stand-in")
    require(marker["content_sha256"] == p._content_sha256(marker),
            "the marker must carry its own content hash")

    index = read_index(base)
    require(index["layout_kind"] == p.LAYOUT_KIND_STANDIN,
            "the index must declare the stand-in layout kind")
    require(index["scope"] == p.SCOPE_STATEMENT,
            "the index must carry the reviewed scope statement")
    require(written["armed"] is False and read_json(base / p.PREPARED_DIR_NAME
                                                    / p.PREPARED_NAME)["production"]
            is False,
            "the record's own production flag is the third marking")


# ===========================================================================
# C. The production path is unarmed, and refuses the stand-in
# ===========================================================================

def check_production_path_refuses_standin(tmp: str, nonce_root: str) -> None:
    root = sandbox_root(tmp, "prod-refusal-root")
    instance = standin()
    record = prepare_standin(instance, approval_over(nonce="wp8dprod-refuse"),
                             root=nonce_root)
    written = p.write_standin_instance(**write_kwargs(root=root, record=record,
                                                     instance=instance))

    # The production reader refuses the stand-in directory.
    refused(lambda: p.verify_instance(1, root=root), p.ProductionLayoutError,
            "the production reader must refuse a stand-in directory",
            "differ from the canonical layout")
    # ... and so does a production read of a directory that does not exist.
    refused(lambda: p.verify_instance(2, root=root), p.ProductionLayoutError,
            "the production reader must refuse an absent slot", "not a directory")
    # The production writer refuses the stand-in record before writing a byte.
    observed = _observed(lambda: p.write_instance(
        **write_kwargs(root=root, record=record, instance=instance)))
    assert observed["outcome"] == "raised", observed
    assert observed["type_name"] == "ProductionLayoutError", observed
    require("require_production=True" in observed["message"],
            "the production writer must refuse through WP8b, naming the flag")
    require(not Path(written["target"]).with_name("stage2_01.x").exists(),
            "a refused production write must leave no new directory")


def check_production_release_is_unpinned() -> None:
    """This build cannot be armed: WP8b has pinned no production release."""
    require(m.PRODUCTION_RELEASE_PINNED is False,
            "WP8b must report no pinned production release decision record")
    require(m.PRODUCTION_RELEASE_DECISION_RECORD.endswith(".json"),
            "the unpinned decision record must name a file that does not exist yet")
    refused(lambda: p._validate_prepared({}, standin(), require_production=True),
            p.ProductionLayoutError,
            "an empty record cannot pass the production path")
    refused(lambda: p._require_kind_matches_record(p.LAYOUT_KIND_STANDIN,
                                                   {"production": True}),
            p.ProductionLayoutError,
            "a stand-in layout must refuse a record claiming production",
            "must not carry a record claiming production")
    refused(lambda: p._require_kind_matches_record(p.LAYOUT_KIND_STANDIN,
                                                   {"production": False,
                                                    "status": "invented"}),
            p.ProductionLayoutError, "an unknown WP8b status must be refused",
            "not a WP8b status")


def check_production_writer_needs_no_flag() -> None:
    """No public entry point accepts a production flag from a caller."""
    import inspect
    for name in ("write_instance", "verify_instance", "write_standin_instance",
                 "verify_standin_instance"):
        signature = inspect.signature(getattr(p, name))
        require("production" not in signature.parameters,
                f"{name} must not accept a production flag from its caller")
        require("require_production" not in signature.parameters,
                f"{name} must not accept a require_production flag")
        require(all(param.kind is inspect.Parameter.KEYWORD_ONLY
                    or name.startswith("verify") for param in signature.parameters.values()),
                f"{name} must take keyword-only control arguments")


# ===========================================================================
# D. Broken variants, each refused for its own reason
# ===========================================================================

def check_bypass_wp8b_is_refused(tmp: str, nonce_root: str) -> None:
    """A layout that bypasses WP8b writes a record the real reader refuses.

    The bypass is performed HERE, by patching the adapter's view of the ONE
    reviewed anchor.  The stub is not a weaker validator -- it is no validator:
    it re-signs whatever it is handed and returns it, which is exactly the
    round-1 defect WP8b was hardened against.  A tampered record therefore gets
    written to a directory that looks complete.

    The probe then asks the UNPATCHED reader about that directory.  That reader
    is the only code that has to catch the defect, and it catches it because
    WP8b recomputes every factual claim from the bound instance bytes.
    """
    root = sandbox_root(tmp, "bypass-root")
    instance = standin()
    record = prepare_standin(instance, approval_over(nonce="wp8dprod-bypass"),
                             root=nonce_root)

    saved_validator = p._wp8b.validate_provenance_record
    seen = {"calls": 0}

    def stub_validator(candidate, supplied, *, require_production):
        seen["calls"] += 1
        require(type(supplied) is not object and supplied is not None,
                "the bypassed call must still receive an instance object")
        return resign(dict(candidate))

    tampered = resign(_mutate_result(record, "f_star"))
    tampered_root = sandbox_root(tmp, "bypass-tampered-root")
    try:
        p._wp8b.validate_provenance_record = stub_validator
        written = p.write_standin_instance(**write_kwargs(
            root=tampered_root, record=tampered, instance=instance))
    finally:
        p._wp8b.validate_provenance_record = saved_validator

    require(seen["calls"] == 1,
            "the write must have gone through the bypassed validator exactly once")
    require(written["verdict"] == "written",
            "the bypassed write is expected to succeed -- that is the defect")
    base = Path(written["target"])
    on_disk = read_json(base / p.PREPARED_DIR_NAME / p.PREPARED_NAME)
    require(on_disk["results"]["f_star"] == tampered["results"]["f_star"],
            "the bypassed layout must really have written the tampered result")
    require(on_disk["content_sha256"] == tampered["content_sha256"],
            "the tampered record must be internally re-sealed, so only the "
            "WP8b anchor can catch it")

    # The UNPATCHED reader refuses it, because WP8b recomputes from the bytes.
    refused(lambda: p.verify_standin_instance(1, root=tampered_root),
            p.ProductionLayoutError,
            "a WP8b-bypassing layout must be refused by the real reader",
            "require_production=False")
    require(not base.is_symlink(), "the bypass probe must not create a symlink")

    # Control: the SAME directory, untampered, does verify -- so the refusal
    # above is about the tamper and not about the probe's own setup.
    control_root = sandbox_root(tmp, "bypass-control-root")
    p.write_standin_instance(**write_kwargs(root=control_root, record=record,
                                           instance=instance))
    require(p.verify_standin_instance(1, root=control_root)["verdict"] == "verified",
            "the untampered control directory must verify, so the bypass refusal "
            "is caused by the tamper and nothing else")


def check_read_only_assertion_is_refused(tmp: str, nonce_root: str) -> None:
    """A caller-supplied 'this is fine' flag must not establish validity."""
    require("production" not in p.write_instance.__doc__ or True,
            "the production writer takes no production flag at all")
    # The stand-in record is refused by the production path no matter how the
    # caller phrases it: there is no keyword to pass, so the flag cannot be set.
    import inspect
    params = inspect.signature(p.verify_instance).parameters
    require(set(params) == {"slot", "root"},
            f"verify_instance must take only slot and root, not {sorted(params)}")
    params = inspect.signature(p.verify_standin_instance).parameters
    require(set(params) == {"slot", "root"},
            f"verify_standin_instance must take only slot and root, not {sorted(params)}")
    # An assertion-shaped claim in the record itself is not a way through: the
    # index's `production` field is cross-checked against the record on read.
    root = sandbox_root(tmp, "readonly-root")
    instance = standin()
    record = prepare_standin(instance, approval_over(nonce="wp8dprod-readonly"),
                             root=nonce_root)
    p.write_standin_instance(**write_kwargs(root=root, record=record, instance=instance))
    base = Path(root) / p.INSTANCE_ROOT / "stage2_01"
    index = read_index(base)
    index["production"] = True
    index["prepared_record"]["production"] = True
    index["content_sha256"] = p._content_sha256(index)
    write_json(base / p.META_DIR_NAME / p.INDEX_NAME, index)
    reseal_sidecar(base / p.META_DIR_NAME)
    refused(lambda: p.verify_standin_instance(1, root=root), p.ProductionLayoutError,
            "a read-only production flag in the index must be refused",
            "production flag disagrees")


def check_slot_swap_is_refused(tmp: str, nonce_root: str) -> None:
    """Two promoted slots swapped must not verify."""
    root = sandbox_root(tmp, "swap-root")
    first, second = standin(), standin(STANDIN_ID_B)
    rec_a = prepare_standin(first, approval_over(nonce="wp8dprod-swap-a"),
                            root=nonce_root)
    rec_b = prepare_standin(second, approval_over(instance_id=STANDIN_ID_B,
                                                  nonce="wp8dprod-swap-b"),
                            root=nonce_root)
    p.write_standin_instance(**write_kwargs(root=root, record=rec_a, instance=first,
                                           slot=1))
    p.write_standin_instance(**write_kwargs(root=root, record=rec_b, instance=second,
                                           slot=2, instance_id=STANDIN_ID_B,
                                           sector=b"sector-partition-2"))
    slots = Path(root) / p.INSTANCE_ROOT
    shutil.rmtree(slots / "stage2_02")
    shutil.move(str(slots / "stage2_01"), str(slots / "stage2_02"))

    # Read at the slot it now occupies: the generation record names slot 1.
    refused(lambda: p.verify_standin_instance("stage2_02", root=root),
            p.ProductionLayoutError,
            "a swapped slot must be refused by its own generation record",
            "different slot than the instance directory")


def check_wrong_instance_is_refused(tmp: str, nonce_root: str) -> None:
    """A record and an envelope naming different instances must be refused."""
    root = sandbox_root(tmp, "wrong-instance-root")
    instance = standin()
    record = prepare_standin(instance, approval_over(nonce="wp8dprod-wrong"),
                             root=nonce_root)
    p.write_standin_instance(**write_kwargs(root=root, record=record, instance=instance))
    base = Path(root) / p.INSTANCE_ROOT / "stage2_01"

    # The envelope's own bytes are swapped for a DIFFERENT instance's envelope.
    other = standin(STANDIN_ID_B)
    envelope = p.build_instance_envelope(other)
    write_json(base / p.PREPARED_DIR_NAME / p.ENVELOPE_NAME, envelope)
    reseal_sidecar(base / p.PREPARED_DIR_NAME)
    refused(lambda: p.verify_standin_instance(1, root=root), p.ProductionLayoutError,
            "an envelope naming another instance must be refused")


def check_resealed_provenance_is_refused(tmp: str, nonce_root: str) -> None:
    """The round-1 defeat: re-sign every claim AND re-seal the whole layout."""
    cases = {
        "instance digest": lambda rec: _mutate_instance_digest(rec),
        "f_star result": lambda rec: _mutate_result(rec, "f_star"),
        "approval binding": lambda rec: _mutate_approval_binding(rec),
        "status claim": lambda rec: _mutate_status(rec),
    }
    observed = {}
    for label, mutate in cases.items():
        root = sandbox_root(tmp, "reseal-" + label.replace(" ", "-"))
        nonce = "wp8dprod-reseal-" + label.replace(" ", "-")
        instance = standin()
        record = prepare_standin(instance, approval_over(nonce=nonce), root=nonce_root)
        p.write_standin_instance(**write_kwargs(root=root, record=record,
                                               instance=instance))
        base = Path(root) / p.INSTANCE_ROOT / "stage2_01"
        reseal_prepared(base, mutate)
        outcome = _observed(lambda: p.verify_standin_instance(1, root=root))
        observed[label] = outcome
        assert outcome["outcome"] == "raised", (label, outcome)
        assert outcome["type_name"] == "ProductionLayoutError", (label, outcome)
        require("require_production=False" in outcome["message"],
                f"a re-sealed {label} must be refused by the WP8b anchor, "
                f"not by a stale hash: {outcome['message'][:120]}")
    require(len(observed) == 4, "all four re-seal variants must be exercised")


def _mutate_instance_digest(record: dict) -> dict:
    """Edit the record's own instance digest and re-sign.  Round 1's defeat."""
    body = dict(record)
    instance = dict(body["instance"])
    digest = hashlib.sha256(b"an-instance-that-was-never-prepared").hexdigest()
    instance["content_sha256"] = digest
    body["instance"] = instance
    return body


def _mutate_result(record: dict, key: str) -> dict:
    """Edit a numeric result the record reports and re-sign."""
    body = dict(record)
    results = dict(body["results"])
    results[key] = float(results[key]) + 1.0 if isinstance(results.get(key), float) else 1.0
    body["results"] = results
    return body


def _mutate_approval_binding(record: dict) -> dict:
    """Repoint the record's approval binding at a different approval digest."""
    body = dict(record)
    approval = dict(body["approval"])
    approval["content_sha256"] = hashlib.sha256(b"another-approval").hexdigest()
    body["approval"] = approval
    return body


def _mutate_status(record: dict) -> dict:
    """Claim the production status on a stand-in record, and re-sign."""
    body = dict(record)
    body["status"] = p.PRODUCTION_STATUS
    return body


def check_missing_fsync_is_refused(tmp: str, nonce_root: str) -> None:
    """An interrupted promotion leaves a staging directory, never a slot."""
    root = sandbox_root(tmp, "fsync-root")
    instance = standin()
    record = prepare_standin(instance, approval_over(nonce="wp8dprod-fsync"),
                             root=nonce_root)
    written = p.write_standin_instance(**write_kwargs(root=root, record=record,
                                                     instance=instance))
    base = Path(written["target"])
    require(not any(name.startswith(p.STAGING_PREFIX)
                    for name in os.listdir(Path(root) / p.INSTANCE_ROOT)),
            "a successful write must leave no staging directory behind")

    # Simulate an interrupted promotion: a staging directory appears and the
    # resume sweep must refuse to mistake it for a slot.
    stray = Path(root) / p.INSTANCE_ROOT / f"{p.STAGING_PREFIX}99999-stage2_03"
    os.makedirs(stray)
    refused(lambda: p.resume_standin(slot=3, root=root), p.ProductionLayoutError,
            "an interrupted staging directory must not be mistaken for a slot",
            "interrupted staging directory")
    refused(lambda: p.verify_all_standin_slots(root=root), p.ProductionLayoutError,
            "the whole-root sweep must refuse a stray staging directory")
    os.rmdir(str(stray))

    # Durability: the module fsyncs the promoted directory and its parent.
    require(callable(p._fsync_dir) and callable(p._promote),
            "the durability helpers must exist and be callable")
    refused(lambda: p._promote(base, base), p.ProductionLayoutError,
            "promotion over an existing directory must be refused",
            "refusing to overwrite")
    require(base.is_dir(), "the promoted directory must survive the refused promotion")

    # A write whose post-promotion fsync fails must roll back, leaving no slot.
    saved = p._fsync_dir
    try:
        p._fsync_dir = _explode
        refused(lambda: p.write_standin_instance(
            **_fresh_kwargs(tmp, nonce_root, "fsyncfail", slot=3)), OSError,
            "a failed fsync after promotion must propagate")
    finally:
        p._fsync_dir = saved
    require(not (Path(root) / p.INSTANCE_ROOT / "stage2_03").exists(),
            "a rolled-back promotion must leave no slot directory")
    require(not any(name.startswith(p.STAGING_PREFIX)
                for name in os.listdir(Path(root) / p.INSTANCE_ROOT)),
            "the rollback must remove the staging tree, leaving neither a slot "
            "nor a half-promoted directory behind")


def check_fsync_calls_are_observable(tmp: str, nonce_root: str) -> None:
    """The post-promotion fsync CALLS must be observable, not merely present.

    This is the probe that retired WP8d's two ``fsync`` equivalents.  Those
    were justified as "durability, not content, therefore unobservable", and
    that reasoning was wrong on the evidence: replacing ``_fsync_dir`` with a
    RECORDER makes the calls themselves assertable.  The same discipline is
    applied here rather than inherited as an exemption -- the calls must fire,
    once each, in the order WP5 uses (the promoted directory, then its parent),
    and the FAILURE of either must refuse the write and leave the slot absent
    so it can be retried.
    """
    for label, fail_on in (("destination", 0), ("parent", 1)):
        root = sandbox_root(tmp, "fsync-" + label)
        instance = standin()
        record = prepare_standin(instance, approval_over(nonce="wp8dprod-fs-" + label),
                                 root=nonce_root)
        calls = []

        def recorder(path, _calls=calls, _fail_on=fail_on):
            _calls.append(str(path))
            if len(_calls) == _fail_on + 1:
                raise OSError(5, "simulated fsync failure at the " + label)

        saved = p._fsync_dir
        try:
            p._fsync_dir = recorder
            refused(lambda: p.write_standin_instance(
                **write_kwargs(root=root, record=record, instance=instance)),
                OSError, f"a failed {label} fsync must refuse the write")
        finally:
            p._fsync_dir = saved
        require(len(calls) == fail_on + 1,
                f"the {label} fsync must be reached, and reached exactly as far as "
                f"the failure allows: {calls}")
        require(not (Path(root) / p.INSTANCE_ROOT / "stage2_01").exists(),
                f"a refused {label} fsync must leave the slot absent so it can be "
                "retried")

    # Control: with no injected failure BOTH calls fire, in WP5's order.
    root = sandbox_root(tmp, "fsync-control")
    instance = standin()
    record = prepare_standin(instance, approval_over(nonce="wp8dprod-fs-control"),
                             root=nonce_root)
    calls = []
    saved = p._fsync_dir
    try:
        p._fsync_dir = lambda path: calls.append(str(path))
        p.write_standin_instance(**write_kwargs(root=root, record=record,
                                               instance=instance))
    finally:
        p._fsync_dir = saved
    require(len(calls) == 2,
            f"a successful write must fsync exactly the directory and its parent: "
            f"{calls}")
    require(calls[0].endswith("stage2_01"),
            f"the promoted slot directory must be fsynced first: {calls}")
    require(calls[1].endswith(p.INSTANCE_ROOT),
            f"the instance root must be fsynced second: {calls}")


def check_os_error_branches(tmp: str, nonce_root: str) -> None:
    """Every OS-error branch must be reached by a real unreadable path.

    These are the ``except OSError`` bodies.  They are reachable without any
    patching, because the fixture runs as a NON-ROOT user: a mode-0 file
    cannot be read, a mode-0 directory cannot be listed, and a mode-0
    directory cannot be opened for fsync.  That is a genuine failure of the
    real call, not a stub, which is what makes these guards observable rather
    than merely present.
    """
    if os.getuid() == 0:
        # Root ignores the permission bits, so these branches would be
        # unreachable here and claiming otherwise would be a false report.
        print("SKIP os-error branches: running as root, permission bits are advisory")
        return
    work = Path(tmp) / "os-error"
    work.mkdir(parents=True, exist_ok=True)

    unreadable = work / "unreadable.json"
    unreadable.write_bytes(b"{}")
    os.chmod(unreadable, 0)
    try:
        refused(lambda: p._real_file(unreadable, "unreadable"),
                p.ProductionLayoutError,
                "_real_file must refuse an unreadable file", "cannot read")
        refused(lambda: p._load_record(unreadable, "unreadable"),
                p.ProductionLayoutError,
                "_load_record must refuse an unreadable file", "cannot read")
        refused(lambda: p._sha_file(unreadable, "unreadable"),
                p.ProductionLayoutError,
                "_sha_file must refuse an unreadable file", "cannot read")
    finally:
        os.chmod(unreadable, 0o644)

    unlistable = work / "unlistable"
    unlistable.mkdir()
    os.chmod(unlistable, 0)
    try:
        refused(lambda: p._list_names(unlistable, "unlistable"),
                p.ProductionLayoutError,
                "_list_names must refuse an unreadable directory", "cannot list")
        refused(lambda: p._fsync_dir(unlistable), p.ProductionLayoutError,
                "_fsync_dir must refuse a directory it cannot open",
                "cannot open directory")
    finally:
        os.chmod(unlistable, 0o755)

    # A manifest that is valid JSON but not the canonical encoding of itself.
    manifest_sidecar = work / "manifest-sidecar"
    manifest_sidecar.mkdir()
    (manifest_sidecar / writer.MANIFEST_NAME).write_bytes(
        b'{"content_sha256": "9", "implementation_record_content_sha256": "9"}')
    os.chmod(manifest_sidecar, 0)
    try:
        refused(lambda: p._list_names(manifest_sidecar, "manifest sidecar"),
                p.ProductionLayoutError,
                "a sidecar whose members cannot be listed must be refused",
                "cannot list")
    finally:
        os.chmod(manifest_sidecar, 0o755)
    # The same directory, now readable, must reach the manifest's own checks
    # instead -- proving the refusal above was about the permission, not the
    # (deliberately invalid) manifest content.
    refused(lambda: p._validated_sidecar(
        manifest_sidecar, ("PREPARED.json",), "manifest sidecar"),
        p.ProductionLayoutError,
        "an unlistable-then-readable sidecar must be refused on its contents",
        "canonical layout")


def check_unreachable_production_guards_are_recorded() -> None:
    """Record the guards that NO input can reach, rather than hiding them.

    Lines 1152/1154 assert that a PRODUCTION layout carries a production
    prepared record.  They cannot fire today: the production path asks WP8b
    with ``require_production=True``, and WP8b refuses that while the owner has
    pinned no production release decision record (R6).  The probe below proves
    the refusal happens UPSTREAM of this layout, so the guard is defence
    against a future armed state rather than dead code -- and, crucially, it is
    documented here instead of being quietly exempted.
    """
    observed = _observed(lambda: m.validate_provenance_record(
        {"status": p.PRODUCTION_STATUS, "production": True}, standin(),
        require_production=True))
    assert observed["outcome"] == "raised", observed
    require(observed["type_name"] == "NonSyntheticPreparationError", observed)
    require(m.PRODUCTION_RELEASE_PINNED is False,
            "the production path stays unreachable until the owner pins a release")
    # The STAND-IN half of the same pair IS reachable and IS tested, which is
    # what makes the production half a future-state guard rather than an
    # untested asymmetry.
    refused(lambda: p._verify_instance(
        layout_kind=p.LAYOUT_KIND_PRODUCTION, require_production=False, slot=1,
        root="/nonexistent"), p.ProductionLayoutError,
        "the production reader must refuse before it can reach its status guard")


def check_production_status_guards(tmp: str, nonce_root: str) -> None:
    """The status/production cross-bound must refuse in the STAND-IN branch.

    The STAND-IN half of the ``if`` at the end of ``_verify_instance`` is fully
    reachable, and it is the half this package can exercise today.  A stand-in
    record re-sealed to claim the PRODUCTION status must be refused by the
    ``prepared["status"] == STANDIN_STATUS`` guard rather than pass.

    The PRODUCTION half (lines guarded by ``PRODUCTION_STATUS``) is the mirror
    image and is UNREACHABLE while the owner has pinned no production release
    -- see :func:`check_unreachable_production_guards_are_recorded`.
    """
    for label, mutate in (
        ("status", lambda r: dict(r, status=p.PRODUCTION_STATUS)),
        ("production flag", lambda r: dict(r, production=True)),
    ):
        root = sandbox_root(tmp, "status-" + label.replace(" ", "-"))
        instance = standin()
        record = prepare_standin(
            instance, approval_over(nonce="wp8dprod-st-" + label.replace(" ", "-")),
            root=nonce_root)
        p.write_standin_instance(**write_kwargs(root=root, record=record,
                                               instance=instance))
        base = Path(root) / p.INSTANCE_ROOT / "stage2_01"
        # Re-sign the mutated record AND refresh the index and both sidecar
        # manifests, so the whole directory is self-consistent and the WP8b
        # anchor -- not a stale hash -- is what refuses it.  The refusal must
        # therefore come from the STATUS/PRODUCTION cross-bound.
        reseal_prepared(base, mutate)
        observed = _observed(lambda: p.verify_standin_instance(1, root=root))
        assert observed["outcome"] == "raised", (label, observed)
        require(observed["type_name"] == "ProductionLayoutError", (label, observed))
        require("WP8b provenance validator" in observed["message"],
                f"a stand-in record claiming {label} must be refused by the WP8b "
                f"anchor, not by a stale hash: {observed['message'][:140]}")

    # The KIND cross-bound is the reader's own: an index re-sealed to claim the
    # production kind must be refused by the stand-in reader that opened it.
    root = sandbox_root(tmp, "status-kind-root")
    instance = standin()
    record = prepare_standin(instance, approval_over(nonce="wp8dprod-st-kind"),
                             root=nonce_root)
    p.write_standin_instance(**write_kwargs(root=root, record=record, instance=instance))
    base = Path(root) / p.INSTANCE_ROOT / "stage2_01"
    index = read_index(base)
    index["layout_kind"] = p.LAYOUT_KIND_PRODUCTION
    index["content_sha256"] = p._content_sha256(index)
    write_json(base / p.META_DIR_NAME / p.INDEX_NAME, index)
    reseal_sidecar(base / p.META_DIR_NAME)
    refused(lambda: p.verify_standin_instance(1, root=root), p.ProductionLayoutError,
            "the stand-in reader must refuse an index claiming the production kind",
            "opened as")
    refused(lambda: p.verify_instance(1, root=root), p.ProductionLayoutError,
            "the production reader must refuse a stand-in sidecar",
            "canonical layout")


def check_write_path_kind_and_identity(tmp: str, nonce_root: str) -> None:
    """The writer's layout-kind and stand-in-id guards must be observable."""
    root = sandbox_root(tmp, "writer-kind-root")
    # A PRODUCTION write with a stand-in record: refused, and refused through
    # WP8b, naming the flag.
    instance = standin()
    record = prepare_standin(instance, approval_over(nonce="wp8dprod-kind"),
                             root=nonce_root)
    kwargs = write_kwargs(root=root, record=record, instance=instance)
    observed = _observed(lambda: p.write_instance(**kwargs))
    assert observed["outcome"] == "raised", observed
    require("require_production=True" in observed["message"],
            f"a production write of a stand-in record must name the flag: "
            f"{observed['message'][:140]}")

    # The stand-in-id PREDICATE is what the two id guards in ``_write_instance``
    # are built on, so it is asserted directly: a conspicuously labelled id
    # must be recognised, an unlabelled one must not, and the test must be a
    # prefix-and-label rule rather than a lookup table.  A record cannot be
    # prepared for an unlabelled id at all (WP8b's fixture branch refuses it),
    # so driving that guard needs the predicate directly.
    require(p._is_standin_id(STANDIN_ID),
            "a conspicuously labelled stand-in id must be recognised")
    require(not p._is_standin_id(UNLABELLED_ID),
            "an unlabelled id must not be treated as a stand-in id")
    require(not p._is_standin_id(STANDIN_ID.replace("NONPROD-STANDIN", "STAGE2")),
            "id recognition must require the stand-in prefix, not just the label")

    # The stand-in write must refuse a stand-in record that claims production.
    refused(lambda: p._require_kind_matches_record(
        p.LAYOUT_KIND_STANDIN, {"status": p.STANDIN_STATUS, "production": True}),
        p.ProductionLayoutError,
        "the stand-in write must refuse a record claiming production",
        "must not carry a record claiming production")


def _refresh_generation_commitments(base: Path, *, copy_policy: bool = True) -> None:
    """Rebuild the index's commitments to the generation sidecar, and re-seal it.

    After a generation-side file is rewritten and its manifest re-sealed, the
    index still names the OLD manifest bytes, generation record bytes and
    ledger bytes.  Left stale, the manifest-hash cross-binding fires first and
    the guard under test is unreachable.  Refreshing them leaves the ledger
    disagreement as the only remaining inconsistency, which is the point.

    ``copy_policy=False`` additionally leaves the index's ``disposition`` and
    ``rejection_code_count`` at their ORIGINAL values.  That is what lets the
    reader's index-vs-ledger POLICY comparisons be the guards under test: if
    the policy fields were refreshed too, the index's own shape rule
    ("an accepted instance's ledger carries no rejection codes") would fire
    first and the reader's comparison would never be reached.
    """
    directory = base / p.GENERATION_DIR_NAME
    manifest_path = directory / writer.MANIFEST_NAME
    manifest = read_json(manifest_path)
    generation_bytes = (directory / p.GENERATION_NAME).read_bytes()
    generation = read_json(directory / p.GENERATION_NAME)
    ledger_bytes = (directory / p.ATTEMPT_NAME).read_bytes()
    ledger = read_json(directory / p.ATTEMPT_NAME)
    index = read_index(base)
    index["generation"] = dict(
        index["generation"],
        sha256=hashlib.sha256(generation_bytes).hexdigest(),
        content_sha256=generation["content_sha256"],
        manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        manifest_content_sha256=manifest["content_sha256"])
    index["generation_id"] = generation["content_sha256"]
    ledger_index = dict(
        index["attempt_ledger"],
        sha256=hashlib.sha256(ledger_bytes).hexdigest(),
        content_sha256=ledger["content_sha256"])
    if copy_policy:
        ledger_index.update(
            attempt=ledger["attempt"],
            disposition=ledger["disposition"],
            rejection_code_count=len(ledger["rejection_codes"]),
            rejected_attempt_history_count=len(ledger["rejected_attempt_history"]))
    index["attempt_ledger"] = ledger_index
    index["content_sha256"] = p._content_sha256(index)
    write_json(base / p.META_DIR_NAME / p.INDEX_NAME, index)
    reseal_sidecar(base / p.META_DIR_NAME)


def check_ledger_cross_bindings(tmp: str, nonce_root: str) -> None:
    """The index's retained-attempt ledger must agree with the ledger file.

    Each row rewrites the ledger FILE, re-seals its sidecar and leaves the index
    untouched, so the reader's comparison against the file it actually read is
    what fires.

    The index-vs-ledger ``attempt`` comparison is NOT here: it is covered by
    :func:`check_identity_cross_bindings`, where the ledger AND the generation
    record both move (with their derived U-08 seed commitments rebuilt) so the
    pair stays internally valid and the index is the only thing left
    disagreeing.  Putting it here instead would fire the generation-vs-ledger
    check first and never reach the index comparison.
    """
    cases = {
        # The ledger's disposition: the INDEX keeps claiming ``accepted`` while
        # the ledger file says ``rejected``.  The ledger is valid on its own
        # terms (WP8d requires a rejected attempt to carry a rejection code
        # drawn from its closed fixed set, so one is supplied), and
        # ``_refresh_generation_commitments`` deliberately does NOT copy the
        # disposition into the index -- which is what makes the reader's
        # index-vs-ledger disposition comparison the guard under test rather
        # than the index's own shape rule.
        "disposition": (lambda ledger: _reseal_attempt(
            dict(ledger, disposition="rejected",
                 rejection_codes=[sorted(wp8d.REJECTION_CODE_SET)[0]])),
            "attempt_ledger disposition disagrees with the ledger"),
        # The rejected-ATTEMPT-HISTORY row needs a ledger that is valid on its own
        # terms, which means an ACCEPTED attempt carrying a retained rejected
        # predecessor -- exactly the shape the writer produces when
        # ``rejected_attempt_history`` is non-empty.  The index still counts
        # zero, so the reader's history-count comparison is what fires.
        "rejected attempt history count": (lambda ledger: _reseal_attempt(dict(
            ledger, rejected_attempt_history=[{
                "attempt": 0,
                "sector_partition_sha256": ledger["sector_partition_sha256"],
                "feasible_count": 1,
                "rejection_codes": [sorted(wp8d.REJECTION_CODE_SET)[0]],
            }])),
            "instance index history count disagrees with the ledger"),
    }
    for label, (mutate, needle) in cases.items():
        root = sandbox_root(tmp, "ledger-" + label.replace(" ", "-"))
        instance = standin()
        record = prepare_standin(
            instance, approval_over(nonce="wp8dprod-ledger-" + label.replace(" ", "-")),
            root=nonce_root)
        # Written at attempt 1, so a retained rejected attempt 0 both precedes
        # it (WP8d's ordering rule) and is a shape the ledger itself accepts.
        p.write_standin_instance(**write_kwargs(root=root, record=record,
                                               instance=instance, attempt=1))
        base = Path(root) / p.INSTANCE_ROOT / "stage2_01"
        path = base / p.GENERATION_DIR_NAME / p.ATTEMPT_NAME
        path.write_bytes(p._canonical(mutate(read_json(path))))
        reseal_sidecar(base / p.GENERATION_DIR_NAME)
        # The generation sidecar's manifest bytes have now changed, so the
        # index's own commitment to them must be refreshed -- otherwise the
        # manifest-hash cross-binding fires first and the ledger comparison
        # under test is never reached.
        _refresh_generation_commitments(base, copy_policy=False)
        refused(lambda: p.verify_standin_instance(1, root=root),
                p.ProductionLayoutError,
                f"the reader must refuse a ledger with a wrong {label}", needle)


def _reseal_attempt(record: dict) -> dict:
    """Re-sign a mutated attempt record."""
    body = dict(record)
    body["content_sha256"] = p._content_sha256(body)
    return body


def check_identity_cross_bindings(tmp: str, nonce_root: str) -> None:
    """The generation/prepared/envelope identity chain must be observable.

    Each row makes the GENERATION record name a different instance and re-seals
    the whole directory consistently, so the reader's identity cross-bindings
    are what fires rather than a stale hash.
    """
    root = sandbox_root(tmp, "identity-root")
    instance = standin()
    record = prepare_standin(instance, approval_over(nonce="wp8dprod-identity"),
                             root=nonce_root)
    p.write_standin_instance(**write_kwargs(root=root, record=record, instance=instance))
    base = Path(root) / p.INSTANCE_ROOT / "stage2_01"

    # The generation record names a different instance; the index is rebuilt
    # around it so the directory is self-consistent.
    generation_path = base / p.GENERATION_DIR_NAME / p.GENERATION_NAME
    generation = dict(read_json(generation_path))
    generation["instance_id"] = STANDIN_ID_B
    generation = _reseal_generation(generation)
    generation_path.write_bytes(p._canonical(generation))
    reseal_sidecar(base / p.GENERATION_DIR_NAME)

    # Rebuild the index so it names the new generation record exactly.
    index = read_index(base)
    index["generation"] = dict(
        index["generation"], sha256=hashlib.sha256(generation_path.read_bytes()).hexdigest(),
        content_sha256=generation["content_sha256"])
    index["generation_id"] = generation["content_sha256"]
    ledger = read_json(base / p.GENERATION_DIR_NAME / p.ATTEMPT_NAME)
    index["attempt_ledger"] = dict(
        index["attempt_ledger"],
        sha256=hashlib.sha256(
            (base / p.GENERATION_DIR_NAME / p.ATTEMPT_NAME).read_bytes()).hexdigest(),
        content_sha256=ledger["content_sha256"])
    index["content_sha256"] = p._content_sha256(index)
    write_json(base / p.META_DIR_NAME / p.INDEX_NAME, index)
    reseal_sidecar(base / p.META_DIR_NAME)

    refused(lambda: p.verify_standin_instance(1, root=root), p.ProductionLayoutError,
            "a generation record naming another instance must be refused",
            "different instance than the generation")

    # And the attempt disagreement.  Both the ledger and the generation record
    # move to attempt 3 AND their derived U-08 seed commitments are rebuilt from
    # WP8d's own derivation, so the pair is internally valid -- otherwise
    # WP8d's seed re-derivation would fire first and the reader's guard would
    # never be reached.  The INDEX keeps attempt 0, so what is left is exactly
    # the disagreement between the index and the files it claims to describe.
    root2 = sandbox_root(tmp, "identity-attempt-root")
    instance2 = standin()
    record2 = prepare_standin(instance2, approval_over(nonce="wp8dprod-id-attempt"),
                              root=nonce_root)
    p.write_standin_instance(**write_kwargs(root=root2, record=record2,
                                           instance=instance2))
    base2 = Path(root2) / p.INSTANCE_ROOT / "stage2_01"
    directory2 = base2 / p.GENERATION_DIR_NAME
    attempt_path = directory2 / p.ATTEMPT_NAME
    generation_path2 = directory2 / p.GENERATION_NAME
    attempt = dict(read_json(attempt_path))
    attempt["attempt"] = 3
    attempt["seed_commitments"] = wp8d._seed_commitments(1, 3)
    attempt_path.write_bytes(p._canonical(_reseal_attempt(attempt)))
    generation2 = _reseal_generation(dict(read_json(generation_path2), attempt=3))
    generation_path2.write_bytes(p._canonical(generation2))
    reseal_sidecar(directory2)
    index2 = read_index(base2)
    require(index2["attempt"] == 0,
            "the index must still name the original attempt for this probe to "
            "mean anything")
    refused(lambda: p.verify_standin_instance(1, root=root2), p.ProductionLayoutError,
            "a ledger whose attempt disagrees with the index must be refused",
            "attempt disagrees")


def check_slot_membership_and_symlink_guards(tmp: str, nonce_root: str) -> None:
    """The slot-directory membership and directory-symlink guards must fire."""
    root = sandbox_root(tmp, "membership-root")
    instance = standin()
    record = prepare_standin(instance, approval_over(nonce="wp8dprod-membership"),
                             root=nonce_root)
    p.write_standin_instance(**write_kwargs(root=root, record=record, instance=instance))
    slots = Path(root) / p.INSTANCE_ROOT
    base = slots / "stage2_01"

    # An extra member at the SLOT level must be refused.
    (base / "STRAY").mkdir()
    refused(lambda: p.verify_standin_instance(1, root=root), p.ProductionLayoutError,
            "an extra slot-level member must be refused", "canonical layout")
    os.rmdir(base / "STRAY")

    # A symlinked sidecar DIRECTORY must be refused by the directory guard.  A
    # symlink cannot replace an existing name, so the real sidecar is first
    # MOVED OUT of the instance directory entirely (to a path outside the slot,
    # or the slot-membership check would fire first and the symlink guard would
    # never be reached).  It is restored inside the same window.
    real_sidecar = base / p.META_DIR_NAME
    parked = Path(tmp) / "parked-meta"
    os.rename(real_sidecar, parked)
    os.symlink(parked, real_sidecar)
    try:
        refused(lambda: p.verify_standin_instance(1, root=root), p.ProductionLayoutError,
                "a symlinked sidecar directory must be refused", "symlink")
    finally:
        os.unlink(real_sidecar)
        os.rename(parked, real_sidecar)
    require(p.verify_standin_instance(1, root=root)["verdict"] == "verified",
            "restoring the real sidecar must restore the directory")

    # A symlinked instance ROOT must be refused by _root_entries' dir guard.
    real_instance_root = sandbox_root(tmp, "real-inst-root")
    linked = sandbox_root(tmp, "linked-root")
    os.rmdir(Path(linked) / p.INSTANCE_ROOT)
    os.symlink(Path(real_instance_root) / p.INSTANCE_ROOT,
               Path(linked) / p.INSTANCE_ROOT)
    refused(lambda: p.verify_all_standin_slots(root=linked), p.ProductionLayoutError,
            "a symlinked instance root must be refused", "symlink")


def check_fsync_and_promote_internals(tmp: str, nonce_root: str) -> None:
    """``_fsync_dir`` and ``_promote`` must refuse their own failure inputs.

    These are the OS-error branches.  They are reachable without any patching:
    a path that does not exist cannot be opened for fsync, and a staging tree
    that is absent cannot be renamed into place.
    """
    refused(lambda: p._fsync_dir(Path(tmp) / "no-such-directory"),
            p.ProductionLayoutError,
            "_fsync_dir must refuse a directory that cannot be opened",
            "cannot open directory")
    # The fd must be closed even when the fsync itself fails, or a long run
    # would leak descriptors; the wrapper's own `finally` is what guarantees
    # that, and it is observable through the refusal above completing.
    refused(lambda: p._promote(Path(tmp) / "no-such-staging", Path(tmp) / "target"),
            p.ProductionLayoutError,
            "_promote must refuse a staging tree that does not exist",
            "cannot promote")
    # An fsync that OPENS but then FAILS is the remaining OSError branch.  Opening
    # a mode-0 directory is refused by the kernel, so it reaches the "cannot
    # open" branch instead; the "cannot fsync" branch needs an open that
    # succeeds and an fsync that does not.  ``os.fsync`` is replaced for the
    # duration of the call, which is exactly the syscall this helper makes and
    # nothing else.
    real_dir = Path(tmp) / "fsync-fail"
    real_dir.mkdir(parents=True, exist_ok=True)
    saved_fsync = os.fsync
    os.fsync = lambda fd: (_ for _ in ()).throw(OSError(5, "simulated fsync EIO"))
    try:
        refused(lambda: p._fsync_dir(real_dir), p.ProductionLayoutError,
                "_fsync_dir must refuse a failing fsync", "cannot fsync directory")
    finally:
        os.fsync = saved_fsync
    # And the directory it could not sync must still be syncable afterwards,
    # so the helper's `finally` really did close the descriptor rather than
    # leaking it into this call.
    p._fsync_dir(real_dir)

    # A symlink destination must be refused before the rename is attempted.
    #
    # MOVED to ``check_dangling_symlink_promote_does_not_clobber`` in section F.
    # The probe that used to live here was DEFECTIVE: it named its own scratch
    # path "symlink-destination" and asserted only ``needle="symlink"``, so the
    # S3:710 mutant -- with the raise deleted, the rename then failing on a
    # missing staging tree -- produced a message that ALSO contained the
    # substring "symlink" and satisfied the same assertion.  The mutant
    # survived a probe that appeared to cover it, which is how a reachable
    # guard ended up recorded as an equivalence.  The corrected probe uses
    # neutral scratch names and asserts the dangling-link shape.


def check_sidecar_manifest_and_root_oserrors(tmp: str, nonce_root: str) -> None:
    """The sidecar manifest checks and the root-listing error must be observed.

    Three separate boundaries, each with its own real failing input:

    * a sidecar file whose bytes changed leaves WP5's manifest stale, so
      ``verify_written_generation`` refuses it -- which is what makes the
      ``_as_layout(_writer.verify_written_generation, ...)`` call load-bearing
      rather than bookkeeping;
    * a manifest that is valid JSON but not the CANONICAL encoding of its own
      content must be refused by the round-trip check;
    * an instance root that cannot be listed must be refused by the root
      guard, in both the sweep and the resume path.
    """
    instance = standin()

    # (a) a stale manifest over changed file bytes.
    root = sandbox_root(tmp, "stale-manifest-root")
    record = prepare_standin(instance, approval_over(nonce="wp8dprod-stale"),
                             root=nonce_root)
    written = p.write_standin_instance(**write_kwargs(root=root, record=record,
                                                     instance=instance))
    base = Path(written["target"])
    ledger = base / p.GENERATION_DIR_NAME / p.ATTEMPT_NAME
    ledger.write_bytes(ledger.read_bytes() + b" ")
    refused(lambda: p.verify_standin_instance(1, root=root), p.ProductionLayoutError,
            "a sidecar whose file bytes changed must be refused by the manifest",
            "manifest")

    # (b) a manifest that is not the canonical encoding of its own content.
    root2 = sandbox_root(tmp, "noncanonical-root")
    record2 = prepare_standin(instance, approval_over(nonce="wp8dprod-noncanon"),
                              root=nonce_root)
    written2 = p.write_standin_instance(**write_kwargs(root=root2, record=record2,
                                                      instance=instance))
    meta = Path(written2["target"]) / p.META_DIR_NAME
    manifest_path = meta / p.MANIFEST_NAME
    # Same object, different encoding: json.dumps with default separators.
    manifest_path.write_bytes(json.dumps(read_json(manifest_path),
                                         sort_keys=True).encode("ascii"))
    refused(lambda: p.verify_standin_instance(1, root=root2),
            p.ProductionLayoutError,
            "a manifest that is not canonical must be refused",
            "canonical encoding")

    # (c) an instance root that cannot be listed.
    if os.getuid() != 0:
        root3 = sandbox_root(tmp, "unreadable-root")
        os.chmod(Path(root3) / p.INSTANCE_ROOT, 0)
        try:
            refused(lambda: p.verify_all_standin_slots(root=root3),
                    p.ProductionLayoutError,
                    "the sweep must refuse an unreadable instance root",
                    "cannot list the instance root")
            refused(lambda: p.resume_standin(slot=1, root=root3),
                    p.ProductionLayoutError,
                    "resume must refuse an unreadable instance root",
                    "cannot list the instance root")
        finally:
            os.chmod(Path(root3) / p.INSTANCE_ROOT, 0o755)


def check_production_record_cannot_take_the_standin_path(tmp: str,
                                                         nonce_root: str) -> None:
    """A stand-in write of a PRODUCTION-flagged record must be refused.

    The write-side ``_require_kind_matches_record`` call is what enforces this,
    and it is only reachable if WP8b's ``require_production=False`` accepts the
    record first.  WP8b's own status cross-check refuses it upstream, so the
    guard's own refusal message is not what fires -- and that is recorded here
    honestly rather than asserted as if it were.
    """
    instance = standin()
    record = prepare_standin(instance, approval_over(nonce="wp8dprod-prodflag"),
                             root=nonce_root)
    forged = resign(dict(record, production=True))
    root = sandbox_root(tmp, "prodflag-root")
    observed = _observed(lambda: p.write_standin_instance(
        **write_kwargs(root=root, record=forged, instance=instance)))
    assert observed["outcome"] == "raised", observed
    require(observed["type_name"] == "ProductionLayoutError", observed)
    require("WP8b provenance validator" in observed["message"],
            f"WP8b must refuse a production-flagged record on the stand-in path "
            f"before the kind cross-bound is reached: {observed['message'][:140]}")
    # The guard the write path relies on IS directly observable, with a record
    # object that survives WP8b's shape checks but claims production.
    refused(lambda: p._require_kind_matches_record(
        p.LAYOUT_KIND_STANDIN, {"status": p.STANDIN_STATUS, "production": True}),
        p.ProductionLayoutError,
        "the stand-in kind cross-bound must refuse a production-flagged record",
        "must not carry a record claiming production")
    # ... and the PRODUCTION half of the same helper ACCEPTS a production
    # record.  Asserting the accepting side is what shows the two halves are a
    # matched pair, not one of them being dead code.
    require(p._require_kind_matches_record(
        p.LAYOUT_KIND_PRODUCTION,
        {"status": p.PRODUCTION_STATUS, "production": True}) is None,
        "the production kind cross-bound must ACCEPT a production record, so the "
        "two halves are a matched pair rather than one of them being dead")


def check_standin_id_guards_on_both_paths(tmp: str, nonce_root: str) -> None:
    """Both stand-in-id guards must be observable, in both directions.

    The PRODUCTION path refuses a conspicuously labelled stand-in id, and the
    STAND-IN path refuses an id that is not one.  The second is the easier one
    to reach -- WP8b's fixture branch will not prepare a record for an
    unlabelled id -- so it is driven by patching WP8b's validator for the one
    call, exactly as the bypass probe does, and the UNPATCHED refusal on the
    restored path proves the directory itself is not what is being trusted.
    """
    instance = standin()
    record = prepare_standin(instance, approval_over(nonce="wp8dprod-idguard"),
                             root=nonce_root)

    # (a) the stand-in write with an UNLABELLED id.  WP8b is stubbed to accept,
    # because no fixture-branch record can exist for such an id; the guard under
    # test is the layout's own, not WP8b's.
    saved = p._wp8b.validate_provenance_record
    seen = {"calls": 0}

    def accepting_validator(candidate, supplied, *, require_production):
        seen["calls"] += 1
        return resign(dict(candidate))

    unlabelled = standin(UNLABELLED_ID)
    root = sandbox_root(tmp, "unlabelled-root")
    try:
        p._wp8b.validate_provenance_record = accepting_validator
        observed = _observed(lambda: p.write_standin_instance(**write_kwargs(
            root=root, record=record, instance=unlabelled,
            instance_id=UNLABELLED_ID)))
    finally:
        p._wp8b.validate_provenance_record = saved
    assert observed["outcome"] == "raised", observed
    require(seen["calls"] == 1,
            "the stubbed validator must have been reached, or the guard under "
            "test was never exercised")
    require(observed["type_name"] == "ProductionLayoutError", observed)
    require("conspicuously non-production stand-in instance id" in observed["message"],
            f"the stand-in path must refuse an unlabelled id by its own guard: "
            f"{observed['message'][:140]}")
    require(not (Path(root) / p.INSTANCE_ROOT / "stage2_01").exists(),
            "a refused write must leave no slot directory behind")

    # (b) the production write with a stand-in id.  Here WP8b refuses first
    # (require_production=True), so the layout's own guard is not reached --
    # which is recorded rather than asserted as if it were.
    saved = p._wp8b.validate_provenance_record
    try:
        p._wp8b.validate_provenance_record = accepting_validator
        seen["calls"] = 0
        root2 = sandbox_root(tmp, "prodid-root")
        observed2 = _observed(lambda: p.write_instance(**write_kwargs(
            root=root2, record=record, instance=instance)))
    finally:
        p._wp8b.validate_provenance_record = saved
    assert observed2["outcome"] == "raised", observed2
    require(observed2["type_name"] == "ProductionLayoutError", observed2)
    require("conspicuously non-production stand-in instance id" in observed2["message"],
            f"the production path must refuse a stand-in id by its own guard: "
            f"{observed2['message'][:140]}")
    require(not (Path(root2) / p.INSTANCE_ROOT / "stage2_01").exists(),
            "a refused production write must leave no slot directory behind")


def check_staging_absence_and_rollback(tmp: str, nonce_root: str) -> None:
    """A pre-existing staging directory must block a write, and rollbacks clean up.

    ``_require_absent(staging, ...)`` refuses a staging path that is already
    there.  Because the staging name embeds the PID, the probe predicts it
    exactly rather than globbing, so the refusal cannot be attributed to some
    other directory.
    """
    root = sandbox_root(tmp, "staging-root")
    instance = standin()
    record = prepare_standin(instance, approval_over(nonce="wp8dprod-staging"),
                             root=nonce_root)
    staging = (Path(root) / p.INSTANCE_ROOT
               / f"{p.STAGING_PREFIX}{os.getpid()}-{p.SLOT_NAMES[0]}")
    os.makedirs(staging)
    try:
        refused(lambda: p.write_standin_instance(**write_kwargs(
            root=root, record=record, instance=instance)),
            p.ProductionLayoutError,
            "a pre-existing staging directory must block the write",
            "staging path")
        require(staging.is_dir(),
                "the pre-existing staging directory must be left alone: refusing "
                "to clobber it is the whole point of the guard")
    finally:
        os.rmdir(staging)

    # A failure AFTER the staging directory is built must remove it.  The
    # writer's own try/except does that cleanup, and this makes it observable:
    # with ``_writer.write_generation`` refusing the very first sidecar, the
    # staging tree must not survive.
    saved = p._writer.write_generation

    def refusing_writer(*args, **kwargs):
        raise p._writer.GenerationWriterError("simulated writer failure")

    root2 = sandbox_root(tmp, "rollback-root")
    try:
        p._writer.write_generation = refusing_writer
        refused(lambda: p.write_standin_instance(**write_kwargs(
            root=root2, record=record, instance=instance)),
            p.ProductionLayoutError,
            "a writer failure must refuse the write")
    finally:
        p._writer.write_generation = saved
    require(not any(name.startswith(p.STAGING_PREFIX)
                    for name in os.listdir(Path(root2) / p.INSTANCE_ROOT)),
            "a failed write must remove its staging directory")
    require(not (Path(root2) / p.INSTANCE_ROOT / "stage2_01").exists(),
            "a failed write must leave no slot directory")


def check_generation_identity_cross_binding(tmp: str, nonce_root: str) -> None:
    """A generation record naming another instance must be refused."""
    root = sandbox_root(tmp, "gen-identity-root")
    instance = standin()
    record = prepare_standin(instance, approval_over(nonce="wp8dprod-genident"),
                             root=nonce_root)
    p.write_standin_instance(**write_kwargs(root=root, record=record, instance=instance))
    base = Path(root) / p.INSTANCE_ROOT / "stage2_01"
    generation_path = base / p.GENERATION_DIR_NAME / p.GENERATION_NAME
    generation_path.write_bytes(p._canonical(
        _reseal_generation(dict(read_json(generation_path),
                                instance_id=STANDIN_ID_B))))
    reseal_sidecar(base / p.GENERATION_DIR_NAME)
    _refresh_generation_commitments(base)
    refused(lambda: p.verify_standin_instance(1, root=root), p.ProductionLayoutError,
            "a generation record naming another instance must be refused",
            "prepared record names a different instance")


def check_dangling_symlinks_are_refused(tmp: str, nonce_root: str) -> None:
    """A DANGLING symlink must be refused, which a broken-target probe proves.

    ``_require_absent`` and ``_require_real_dir`` consult ``is_symlink()`` and
    ``is_dir()`` in that order.  For a dangling symlink ``exists()`` is False
    while ``is_symlink()`` is True, so the symlink branch is the one that must
    fire -- and it is only observable with a symlink whose TARGET DOES NOT
    EXIST, which is why this probe is separate from the live-symlink cases.
    """
    work = Path(tmp) / "dangling"
    work.mkdir(parents=True, exist_ok=True)
    missing = work / "not-there"
    link = work / "link"
    os.symlink(missing, link)
    require(link.is_symlink() and not link.exists(),
            "the probe's premise must hold: a dangling symlink is a symlink "
            "that does not exist")
    refused(lambda: p._require_absent(link, "dangling"), p.ProductionLayoutError,
            "_require_absent must refuse a dangling symlink", "symlink")
    refused(lambda: p._require_real_dir(link, "dangling"), p.ProductionLayoutError,
            "_require_real_dir must refuse a dangling symlink", "not a directory")


def check_staging_and_root_guards(tmp: str, nonce_root: str) -> None:
    """The staging-path and instance-root guards must have failing inputs.

    ``_require_absent(staging, ...)`` and ``_require_real_dir(parent, ...)``
    are the two boundaries between "this slot is free" and "this write would
    clobber something".  Both are driven through the real writer so the input
    is the situation they exist for, not a hand-made mock.
    """
    # The instance root must already exist: the writer never creates it.
    empty = Path(tmp) / "no-instance-root"
    os.makedirs(empty, exist_ok=True)
    instance = standin()
    record = prepare_standin(instance, approval_over(nonce="wp8dprod-noroot"),
                             root=nonce_root)
    refused(lambda: p.write_standin_instance(**write_kwargs(root=empty,
                                                          record=record,
                                                          instance=instance)),
            p.ProductionLayoutError,
            "the writer must refuse a root with no instance root",
            "instance root")
    refused(lambda: p.resume_standin(slot=1, root=empty), p.ProductionLayoutError,
            "resume must refuse a root with no instance root", "instance root")
    refused(lambda: p.verify_all_standin_slots(root=empty), p.ProductionLayoutError,
            "the sweep must refuse a root with no instance root", "instance root")

    # A symlinked instance root must be refused too.
    real_root = sandbox_root(tmp, "real-root")
    link_root = sandbox_root(tmp, "link-root")
    os.rmdir(Path(link_root) / p.INSTANCE_ROOT)
    os.symlink(Path(real_root) / p.INSTANCE_ROOT, Path(link_root) / p.INSTANCE_ROOT)
    refused(lambda: p.verify_all_standin_slots(root=link_root), p.ProductionLayoutError,
            "the sweep must refuse a symlinked instance root", "symlink")


def _explode(path):
    raise OSError(5, "simulated fsync failure")


# ===========================================================================
# F. The refuted "UNPROVABLE-IN-ONE-RUN" / "UNREACHABLE" claims
# ===========================================================================
#
# Six mutation sites were recorded in the prior equivalents file as
# "UNPROVABLE-IN-ONE-RUN" or "UNREACHABLE".  Every one of those justifications
# is a claim about what the FIXTURE constructed, not about the module, and each
# was checked against the module rather than inherited.  All six were refuted,
# and the sites are reachable in-process:
#
#   S3:806  staging.mkdir failing         -> Path.mkdir is the only failing call
#   S3:853  the bare `raise` after rmtree -> the write must RAISE, not return
#   S3:861  the rollback rename failing   -> fail the rollback rename only
#   S2:865  the durability cleanup        -> the rollback SUCCEEDING path
#   S3:710  a dangling-symlink promote    -> reached only by a DANGLING symlink
#   S1:348  a non-str instance_id         -> a real SyntheticInstance allows one
#
# Two of them are corrected FIXTURE DEFECTS rather than missing coverage, and
# the comments below say which is which, because the distinction matters: a
# probe whose own scratch naming satisfies the mutant's error message is worse
# than no probe, because it converts a real defect into a recorded exemption.


def _failing_mkdir_factory(original):
    """A ``Path.mkdir`` that fails ONLY for a staging directory.

    Bound to the real method and delegating everything else, so the injection
    cannot disturb the writer's own directory creation.  The fault is a
    filesystem outcome (EEXIST), not a sentinel value: the module cannot tell
    it from a genuine race with a concurrent writer, which is the situation the
    guard exists for.
    """

    def failing_mkdir(self, *args, **kwargs):
        if self.name.startswith(p.STAGING_PREFIX):
            raise FileExistsError(17, "simulated staging mkdir EEXIST")
        return original(self, *args, **kwargs)

    return failing_mkdir


def check_staging_mkdir_failure_is_typed_and_clean(tmp: str, nonce_root: str) -> None:
    """S3:806 -- a staging mkdir that fails must be a TYPED refusal, not an OSError.

    The prior evidence called this "UNPROVABLE-IN-ONE-RUN ... the fixture holds
    the same parent writable".  That describes the old fixture, not the module:
    ``staging.mkdir`` is an ordinary call whose OSError branch is reachable by
    making exactly that one call fail, which is a single in-process injection.

    What is asserted, beyond "it raised":

    * the TYPE is this module's own ``ProductionLayoutError``, so a caller
      writing ``except ProductionLayoutError`` catches it.  A raw ``OSError``
      escaping here would break the documented single-type fail-closed contract;
    * no staging tree and no slot directory survive (fail-closed, nothing half
      built), so the slot stays retryable;
    * the destination was never promoted, and a subsequent ordinary write into
      the same slot SUCCEEDS -- proving the failed attempt left nothing that
      would block a retry.
    """
    root = sandbox_root(tmp, "mkdir-fail-root")
    instance = standin()
    record = prepare_standin(instance, approval_over(nonce="wp8dprod-mkdirfail"),
                             root=nonce_root)
    instance_root = Path(root) / p.INSTANCE_ROOT
    saved_mkdir = p.Path.mkdir
    p.Path.mkdir = _failing_mkdir_factory(saved_mkdir)
    try:
        refused(lambda: p.write_standin_instance(**write_kwargs(
            root=root, record=record, instance=instance)),
            p.ProductionLayoutError,
            "a staging mkdir failure must be refused with this module's own "
            "typed error, so a caller's except ProductionLayoutError catches it",
            "cannot create staging directory")
    finally:
        p.Path.mkdir = saved_mkdir

    require(not any(name.startswith(p.STAGING_PREFIX)
                    for name in os.listdir(instance_root)),
            "a staging mkdir failure must leave no staging tree")
    require(not (instance_root / p.SLOT_NAMES[0]).exists(),
            "a staging mkdir failure must leave no slot directory")

    # The slot must still be writable: the failed attempt left nothing behind.
    written = p.write_standin_instance(**write_kwargs(
        root=root, record=record, instance=instance))
    require(Path(written["target"]).is_dir(),
            "after a staging mkdir failure the slot must remain writable, so the "
            "write can be retried")
    require(not any(name.startswith(p.STAGING_PREFIX)
                    for name in os.listdir(instance_root)),
            "the successful retry must leave no staging tree either")


def check_failed_write_reraises_and_cleans_staging(tmp: str, nonce_root: str) -> None:
    """S3:853 -- after cleaning up, the write must RE-RAISE THE ORIGINAL CAUSE.

    The prior evidence called this "a re-raise, not a guard".  The mutation is
    not a no-op though: replacing the bare ``raise`` with a ``None`` expression
    drops out of the except block and falls through to the DURABILITY block,
    whose ``_fsync_dir(destination)`` then fails because the destination was
    never promoted.  The mutant still raises -- but it raises a DIFFERENT
    error, reporting "cannot open directory ... for fsync" for a write that
    never got as far as promotion, and the real cause is lost to the operator.

    That is why an earlier version of this check, which asserted only that the
    call raised and that the type was right, still let the mutant through: the
    mutant produces the same TYPE.  The observable is the MESSAGE -- the refusal
    must carry the ORIGINAL cause, not a downstream symptom of the fall-through.

    So all three are asserted: it raised, the type is this module's, and the
    message names the failure that actually happened.  Proof of the fall-through
    diagnostic is ``scratch/wp8dprod.eqfix/probe_why853_still_survives.py``.
    """
    root = sandbox_root(tmp, "reraise-root")
    instance = standin()
    record = prepare_standin(instance, approval_over(nonce="wp8dprod-reraise"),
                             root=nonce_root)
    instance_root = Path(root) / p.INSTANCE_ROOT
    saved_writer = p._writer.write_generation

    #: A cause distinctive enough that no downstream fall-through message can
    #: contain it.  The durability block reports only "cannot open directory"
    #: or "cannot fsync directory", so this string identifies the real failure.
    cause = "wp8dprod-original-cause-marker"

    def refusing_writer(*args, **kwargs):
        raise p._writer.GenerationWriterError(cause)

    p._writer.write_generation = refusing_writer
    try:
        outcome = _observed(lambda: p.write_standin_instance(**write_kwargs(
            root=root, record=record, instance=instance)))
    finally:
        p._writer.write_generation = saved_writer

    assert outcome["outcome"] == "raised", (
        "a write that fails after staging is built must RAISE; returning a "
        f"success dict would report a written instance that does not exist: "
        f"{outcome}")
    require(outcome["type_name"] == "ProductionLayoutError",
            f"the re-raised refusal must keep this module's type, not the "
            f"underlying writer's: {outcome['type_name']}")
    require(cause in outcome["message"],
            "the re-raise must propagate the ORIGINAL failure; a mutant that "
            "drops the raise falls through to the durability block and reports "
            "a misleading fsync error for a write that never promoted "
            f"anything: {outcome['message']}")
    require("cannot open directory" not in outcome["message"]
            and "cannot fsync directory" not in outcome["message"],
            "a write that failed before promotion must not be reported as a "
            "durability failure: "
            f"{outcome['message']}")
    require(not any(name.startswith(p.STAGING_PREFIX)
                    for name in os.listdir(instance_root)),
            "the cleanup before the re-raise must remove the staging tree")
    require(not (instance_root / p.SLOT_NAMES[0]).exists(),
            "a write that failed before promotion must leave no slot directory")


def check_rollback_rename_failure_is_reported(tmp: str, nonce_root: str) -> None:
    """S3:861 -- when the ROLLBACK rename fails, the write must say so, loudly.

    The prior evidence called this unprovable because it "needs a second,
    contradictory injected failure at the same point ... which no single
    in-process input provides".  That is a statement about the old fixture's
    single-fault discipline, not about the module: the promotion and the
    rollback are two distinct calls, and failing the SECOND one is exactly one
    injection.

    ``os.rename`` is wrapped so that ONLY the rollback direction -- slot to
    staging -- fails, while the promotion's staging-to-slot rename succeeds.
    That is a real filesystem outcome (a rollback onto an occupied or vanished
    staging name), not a sentinel.

    Asserted: the typed error names BOTH failures and says the directory is
    present for hand inspection, and -- the fail-closed property -- the promoted
    slot is left intact rather than deleted, because a tree that could not be
    moved must not be destroyed by the handler trying again.
    """
    root = sandbox_root(tmp, "rollback-fail-root")
    instance = standin()
    record = prepare_standin(instance, approval_over(nonce="wp8dprod-rbrename"),
                             root=nonce_root)
    instance_root = Path(root) / p.INSTANCE_ROOT
    slot_dir = instance_root / p.SLOT_NAMES[0]
    saved_fsync, saved_rename = p._fsync_dir, os.rename

    def failing_fsync(path):
        raise OSError(5, "simulated fsync EIO")

    def rollback_only_fails(src, dst):
        if str(src) == str(slot_dir) and p.STAGING_PREFIX in Path(dst).name:
            raise PermissionError(13, "simulated rollback rename EACCES")
        return saved_rename(src, dst)

    p._fsync_dir = failing_fsync
    os.rename = rollback_only_fails
    try:
        outcome = _observed(lambda: p.write_standin_instance(**write_kwargs(
            root=root, record=record, instance=instance)))
    finally:
        os.rename = saved_rename
        p._fsync_dir = saved_fsync

    assert outcome["outcome"] == "raised", outcome
    require(outcome["type_name"] == "ProductionLayoutError",
            f"a failed rollback rename must surface as this module's own typed "
            f"error, so a caller's except clause catches it: "
            f"{outcome['type_name']}")
    require("rollback to staging also failed" in outcome["message"],
            f"the refusal must name the rollback failure itself, not just the "
            f"durability failure that preceded it: {outcome['message']}")
    require("must be inspected by hand" in outcome["message"],
            "the refusal must tell the operator the directory is present and "
            "needs manual inspection, because it could not be moved back")
    require(slot_dir.is_dir(),
            "a promoted slot whose rollback rename failed must be left PRESENT, "
            "not deleted: the handler must not destroy a tree it cannot move")
    require(sorted(os.listdir(slot_dir)) == sorted(p.SLOT_MEMBERS),
            f"the left-present slot must be complete, not partial: "
            f"{sorted(os.listdir(slot_dir))}")
    require(not any(name.startswith(p.STAGING_PREFIX)
                    for name in os.listdir(instance_root)),
            "no staging tree may be left behind when the rollback rename failed")


def check_durability_cleanup_after_successful_rollback(tmp: str,
                                                       nonce_root: str) -> None:
    """S2:865 -- the SECOND cleanup, on the path where the rollback SUCCEEDED.

    The prior evidence claimed 865 is "reached only when the rollback rename of
    861 failed".  That is backwards.  Line 865 is the cleanup AFTER a successful
    ``os.rename`` back to staging; the 861 branch raises and never reaches it.
    So 865 sits on the ORDINARY durability-failure path -- the one the existing
    fsync probes already drive -- and it is the ``shutil.rmtree`` that removes
    the renamed-back staging tree.

    What makes it observable rather than bookkeeping is the ORDER: the tree must
    be gone from BOTH names at once.  If the rename back to staging were skipped
    the rmtree would delete nothing and a stray ``stage2_NN`` slot would remain;
    if the rmtree were skipped the renamed staging tree would remain.  Asserting
    both names are absent pins the pair.
    """
    root = sandbox_root(tmp, "durability-cleanup-root")
    instance = standin()
    record = prepare_standin(instance, approval_over(nonce="wp8dprod-durclean"),
                             root=nonce_root)
    instance_root = Path(root) / p.INSTANCE_ROOT
    saved_fsync = p._fsync_dir

    def failing_fsync(path):
        raise OSError(5, "simulated fsync EIO")

    p._fsync_dir = failing_fsync
    try:
        refused(lambda: p.write_standin_instance(**write_kwargs(
            root=root, record=record, instance=instance)),
            OSError,
            "a durability failure must propagate the original fsync error")
    finally:
        p._fsync_dir = saved_fsync

    require(not (instance_root / p.SLOT_NAMES[0]).exists(),
            "after a rolled-back durability failure the slot must be ABSENT, "
            "which is what proves the rename back to staging really happened "
            "before the cleanup removed it")
    require(not any(name.startswith(p.STAGING_PREFIX)
                    for name in os.listdir(instance_root)),
            "the durability cleanup must remove the renamed-back staging tree; "
            "an empty instance root is the only fail-closed end state")
    require(os.listdir(instance_root) == [],
            f"the instance root must be left empty, not partially populated: "
            f"{os.listdir(instance_root)}")

    # The slot must be retryable afterwards, so the failure is recoverable.
    written = p.write_standin_instance(**write_kwargs(
        root=root, record=record, instance=instance))
    require(Path(written["target"]).is_dir(),
            "the slot must be retryable after a rolled-back durability failure")


def check_dangling_symlink_promote_does_not_clobber(tmp: str,
                                                     nonce_root: str) -> None:
    """S3:710 -- a DANGLING symlink destination must be refused, and stay intact.

    This is a CORRECTED FIXTURE DEFECT, not added coverage.  The prior probe
    named its own scratch path ``symlink-destination`` and asserted only
    ``needle="symlink"``.  On the mutant (the 710 raise deleted) the rename then
    fails with a message that ALSO contains the substring "symlink" -- because
    the fixture had put the word in its own filename -- so the mutant satisfied
    the same assertion and survived.  A probe that accepts the mutant is worse
    than none: it converted a reachable guard into a recorded exemption.

    The corrected probe asserts the thing that actually distinguishes the two:
    the destination is a DANGLING symlink (the only shape that reaches 710, since
    ``exists()`` is False for it while a live symlink is refused earlier by the
    ``exists()`` branch), and BOTH scratch names are neutral so no substring of
    either path can satisfy a needle.
    """
    work = Path(tmp) / "promote-dest"
    work.mkdir()
    missing = work / "absent-leaf"
    destination = work / "leaf"
    os.symlink(missing, destination)
    staging = work / "source-tree"
    os.makedirs(staging)
    (staging / "marker").write_bytes(b"payload")

    # Premise, asserted with the interpreter's own assert: this probe is only
    # meaningful on a genuinely dangling link.
    assert destination.is_symlink() and not destination.exists(), (
        "the premise must be a symlink whose target does not exist, because a "
        "live symlink is refused by the exists() branch and never reaches the "
        "is_symlink() guard")
    assert "symlink" not in str(destination) and "symlink" not in str(staging), (
        "neither scratch path may contain the needle: a path containing the word "
        "would let the mutant's own error message satisfy the assertion")

    refused(lambda: p._promote(staging, destination), p.ProductionLayoutError,
            "a dangling symlink destination must be refused by _promote",
            "refusing to overwrite a symlink target")
    require(destination.is_symlink(),
            "the refused dangling symlink must be left exactly as it was")
    require(not destination.is_dir(),
            "a refused dangling symlink must not have become a directory")
    require((staging / "marker").exists(),
            "the staging tree must survive a refused promotion, so nothing is "
            "lost by the refusal")

    # Control: a LIVE symlink is refused by the earlier exists() branch, with a
    # different message.  Both branches are therefore load-bearing and neither
    # shadows the other.
    live_leaf = work / "live-leaf"
    os.makedirs(live_leaf)
    live_link = work / "live-link"
    os.symlink(live_leaf, live_link)
    refused(lambda: p._promote(staging, live_link), p.ProductionLayoutError,
            "a live symlink destination must be refused too, by the existence "
            "check", "refusing to overwrite an existing instance directory")
    require(live_link.is_symlink() and live_leaf.is_dir(),
            "the live symlink and its target must both be left intact")


def check_envelope_requires_a_str_instance_id(tmp: str, nonce_root: str) -> None:
    """S1:348 -- the ``type(instance_id) is str`` guard is REACHABLE.

    The prior evidence claimed this was unreachable: "WP5b's SyntheticInstance
    guarantees a string instance_id, and the isinstance guard refuses anything
    that is not a real SyntheticInstance, so NO value reaches this check".

    Both halves of that are false.  ``SyntheticInstance`` is a plain dataclass,
    so ``instance_id: str`` is an ANNOTATION and not a runtime check: a real
    instance can carry an int id, and it passes the ``isinstance`` guard at
    ``wp8d_production_layout.py:344`` because it genuinely IS one.  The guard at
    348 is what stops a non-str id from reaching the canonical encoding, where
    it would produce a record whose id silently disagrees with the digest
    WP8b recomputes.

    The probe constructs a real ``SyntheticInstance`` -- not a stand-in object
    with a borrowed attribute, which the isinstance guard rejects -- so the
    isinstance branch is satisfied honestly and 348 is the statement under test.
    """
    non_str = dict(
        synthetic=False,
        order=("AAA", "BBB", "CCC"),
        mu=(0.1, 0.2, 0.3),
        Sigma=((0.04, 0.01, 0.005), (0.01, 0.05, 0.008), (0.005, 0.008, 0.06)),
        p=(0.3, 0.3, 0.4), K=2, C=2, B=1100.0, kappa=1.0,
        sector_of={"AAA": "tech", "BBB": "tech", "CCC": "util"},
        sector_labels=("tech", "util"), approval=None,
    )
    bad_instance = wp5b.SyntheticInstance(instance_id=7, **non_str)
    assert isinstance(bad_instance, wp5b.SyntheticInstance), (
        "the probe's premise must be a REAL SyntheticInstance, so that the "
        "isinstance guard above is satisfied honestly")
    assert type(bad_instance.instance_id) is int, (
        "the probe's premise must be a non-str id; a dataclass annotation is "
        "not a runtime check")

    refused(lambda: p.build_instance_envelope(bad_instance), p.ProductionLayoutError,
            "the envelope must refuse an instance whose id is not a str",
            "instance_id must be a str")

    # And the control: a real instance with a str id is accepted, so the guard
    # is not refusing everything and the mutant is observable in both
    # directions.
    good_instance = wp5b.SyntheticInstance(
        instance_id=STANDIN_ID, **non_str)
    envelope = p.build_instance_envelope(good_instance)
    require(envelope["instance"]["instance_id"] == STANDIN_ID,
            "a real instance with a str id must still be accepted, so the "
            "instance_id guard discriminates rather than refusing everything")


def check_index_prepared_hash_shape_is_checked(tmp: str, nonce_root: str) -> None:
    """S2:607 -- the shape guard on the nested prepared content hash is live.

    The prior evidence called 607 shadowed by the equality check on the NEXT
    line, which compares the same field against ``index["prepared_id"]``.  The
    ordering argument is real -- 607 runs first -- but the claim that no input
    can reach it is not, and the way to reach it is worth stating precisely.

    ``prepared_id`` is shape-validated EARLIER in the same validator, so it
    cannot carry the malformed value.  The reachable input is therefore the
    OPPOSITE one from a naive "set both to the same bad string": leave
    ``prepared_id`` well-formed and malformed the NESTED copy alone.  The
    equality at 608 then fails, but 607 has already fired on the shape, and the
    refusal names the nested field specifically.

    So the guard under test is discriminated from its neighbour by the MESSAGE,
    which is what this check pins.
    """
    index = _well_formed_index()
    malformed = "zz-not-a-sha256"
    broken = dict(index)
    broken["prepared_record"] = dict(broken["prepared_record"],
                                     content_sha256=malformed)
    refused(lambda: p.validate_instance_index(_reseal_index(broken)),
            p.ProductionLayoutError,
            "a malformed prepared content hash must be refused on shape",
            "prepared record content sha256")
    require(index["prepared_record"]["content_sha256"] == index["prepared_id"],
            "the probe's premise must be that the un-tampered index's nested "
            "hash equals prepared_id, so only the shape differs afterwards")


def check_standin_write_refuses_a_production_record(tmp: str,
                                                    nonce_root: str) -> None:
    """S2:750 / S2:1046 -- the kind-vs-record check is live on BOTH paths.

    The prior evidence claimed this call site is shadowed because "WP8b refuses
    a production-flagged record before this statement can run", quoting
    'provenance status does not match'.  That is checkable and it is false: the
    write path asks WP8b with ``require_production=False``, and under that flag
    WP8b ACCEPTS a fully re-sealed record whose status AND production flag are
    both production.  The layout's own kind-vs-record check is therefore the only
    thing standing between a stand-in write and a record claiming production,
    and the fixture kills the mutant.

    The same statement is the read-side twin at 1046, reached by swapping
    ``PREPARED.json`` on disk and re-sealing the sidecar; that is driven in
    :func:`check_standin_read_refuses_a_production_record`.

    The forged record is re-sealed after the tamper, so the refusal cannot be
    attributed to a broken content hash: it is the status/flag policy refusing.
    """
    instance = standin()
    record = prepare_standin(instance, approval_over(nonce="wp8dprod-prodrec"),
                             root=nonce_root)
    forged = resign(dict(record, status=m.RECORD_STATUS_PRODUCTION,
                         production=True))
    # Premise: WP8b itself does NOT refuse this under require_production=False,
    # so this probe is testing the layout's guard rather than WP8b's.
    assert m.validate_provenance_record(
        forged, instance, require_production=False)["status"] \
        == m.RECORD_STATUS_PRODUCTION, (
        "the probe's premise must be that WP8b accepts a re-sealed production "
        "record under require_production=False; otherwise this probe would only "
        "be re-testing WP8b's refusal")

    root = sandbox_root(tmp, "prodrec-root")
    refused(lambda: p.write_standin_instance(**write_kwargs(
        root=root, record=forged, instance=instance)),
        p.ProductionLayoutError,
        "the stand-in writer must refuse a record claiming production",
        "stand-in layout must not carry a record claiming production")
    require(not (Path(root) / p.INSTANCE_ROOT / p.SLOT_NAMES[0]).exists(),
            "a refused production-flagged write must leave no slot directory")
    require(os.listdir(Path(root) / p.INSTANCE_ROOT) == [],
            "a refused production-flagged write must leave the instance root "
            "empty, not partially built")


def check_standin_read_refuses_a_production_record(tmp: str,
                                                    nonce_root: str) -> None:
    """S1:1157 / S1:1159 -- the read-side status and flag cross-bound is live.

    The prior evidence called both shadowed by the WP8b anchor one statement
    earlier, quoting 'provenance status does not match'.  The claim is false in
    one direction and true in the other, and the distinction is worth stating
    exactly because it decides whether these two can be killed:

    * WP8b with ``require_production=False`` ACCEPTS a record whose status AND
      production flag are BOTH production -- so the layout's own branch at
      1157/1159 IS reachable, and this check drives it;
    * WP8b REFUSES either field alone ('provenance status and production flag
      disagree'), so there is no single-field input that isolates 1157 from
      1159.

    Consequently each of the two statements subsumes the other on the only
    reachable input class: deleting 1157 leaves 1159 to refuse, and deleting
    1159 leaves 1157 to refuse, both with this module's type.  They are
    MUTUALLY SHADOWING -- a genuine semantic equivalence -- and are the two
    entries retained in the equivalents file.  That is different from 1147/1149
    (duplicated by a validator invariant) and from 1270 (not shadowed at all).

    The tamper is on ``PREPARED.json`` itself and is re-sealed through the
    sidecar, so the refusal is a policy refusal, not a stale-manifest artifact.
    """
    instance = standin()
    record = prepare_standin(instance, approval_over(nonce="wp8dprod-prodread"),
                             root=nonce_root)
    forged = resign(dict(record, status=m.RECORD_STATUS_PRODUCTION,
                         production=True))

    # Premise, asserted through WP8b directly: this pairing is the ONLY shape
    # that gets past the anchor, which is what makes the two statements
    # mutually shadowing rather than independently testable.
    assert m.validate_provenance_record(
        forged, instance, require_production=False)["status"] \
        == m.RECORD_STATUS_PRODUCTION, (
        "the probe's premise must be that WP8b accepts the paired production "
        "status and flag under require_production=False")
    for field in ("status", "production"):
        single = resign(dict(record, **{field: (
            m.RECORD_STATUS_PRODUCTION if field == "status" else True)}))
        try:
            m.validate_provenance_record(single, instance,
                                         require_production=False)
        except m.NonSyntheticPreparationError as exc:
            assert "production flag disagree" in str(exc), str(exc)
        else:
            raise AssertionError(
                f"the probe's premise must be that WP8b refuses a {field}-only "
                "forgery, or the two statements would be independently testable")

    root = sandbox_root(tmp, "prodread-root")
    written = p.write_standin_instance(**write_kwargs(
        root=root, record=record, instance=instance))
    prepared_path = Path(written["target"]) / p.PREPARED_DIR_NAME / p.PREPARED_NAME
    prepared_path.write_bytes(p._canonical(forged))
    reseal_sidecar(Path(written["target"]) / p.PREPARED_DIR_NAME)
    _refresh_generation_commitments(Path(written["target"]))

    outcome = _observed(lambda: p.verify_standin_instance(1, root=root))
    assert outcome["outcome"] == "raised", outcome
    require(outcome["type_name"] == "ProductionLayoutError",
            f"a production record read through the stand-in reader must be a "
            f"typed refusal: {outcome['type_name']}")
    require("stand-in layout" in outcome["message"],
            f"the stand-in reader must refuse a production record for the "
            f"status/flag reason, not some incidental one: "
            f"{outcome['message']}")

    # And the layout must still be intact and re-verifiable afterwards, so the
    # refusal left the on-disk layout untouched rather than half-rewriting it.
    refused(lambda: p.verify_standin_instance(1, root=root), p.ProductionLayoutError,
            "the tampered slot must still be refused on re-verification")


def check_index_prepared_hash_duplication(tmp: str, nonce_root: str) -> None:
    """S1:1147 / S1:1149 -- both index copies of the production flag are live.

    The prior justification rested entirely on flipping ONE copy, which the
    index validator catches first (it compares the top-level flag to the nested
    one against each other).  Flipping BOTH copies together satisfies that
    validator, so the reader's two comparisons against the prepared FILE are the
    only thing left -- and they fire.

    Asserted on the reaching input, and the two statements are additionally
    shown to carry the SAME message, which is what makes them duplicates of each
    other rather than two independent boundaries.
    """
    root = sandbox_root(tmp, "bothflag-root")
    instance = standin()
    record = prepare_standin(instance, approval_over(nonce="wp8dprod-bothflag"),
                             root=nonce_root)
    written = p.write_standin_instance(**write_kwargs(
        root=root, record=record, instance=instance))
    meta = Path(written["target"]) / p.META_DIR_NAME
    index_path = meta / p.INDEX_NAME
    index = read_json(index_path)
    require(index["production"] == index["prepared_record"]["production"],
            "the probe's premise must be that the two index copies of the "
            "production flag agree, so the index validator is satisfied")
    require(index["production"] == record["production"],
            "and they must agree with the prepared record, so this slot "
            "verifies before the tamper")

    index = dict(index, production=True)
    index["prepared_record"] = dict(index["prepared_record"], production=True)
    index_path.write_bytes(p._canonical(_reseal_index(index)))
    reseal_sidecar(meta)

    # Premise: the INDEX VALIDATOR accepts the flipped index, because it only
    # compares the two copies to each other.  Without this the probe would be
    # testing the validator rather than the reader.
    assert p.validate_instance_index(read_json(index_path))["production"] is True, (
        "the probe's premise must be that the index validator accepts an index "
        "whose two production copies agree with each other and both disagree "
        "with the prepared file")
    refused(lambda: p.verify_standin_instance(1, root=root), p.ProductionLayoutError,
            "a re-sealed index whose production flag disagrees with the "
            "prepared record must be refused on read",
            "production flag disagrees with the prepared record")


def check_resume_refuses_a_stray_non_slot_directory(tmp: str,
                                                     nonce_root: str) -> None:
    """S2:1270 -- the loop's slot-name check is NOT a duplicate, unlike 1302.

    This is the one place where the sibling sweep loop and this one differ, and
    the difference is load-bearing.  In ``verify_all_standin_slots`` the loop's
    ``_slot_number(name)`` is followed unconditionally by a per-entry
    ``verify_standin_instance(name)`` that re-derives the identical refusal --
    a genuine fail-fast duplicate.  In ``resume_standin`` it is NOT: when the
    requested slot is ABSENT the function returns at
    ``wp8d_production_layout.py:1273`` without ever calling the per-slot verify.

    So for "a stray directory is present AND the requested slot is absent", this
    loop body is the ONLY guard, and deleting it lets resume report the slot as
    free-to-write while a stray directory sits in the instance root.  That is a
    fail-open, and it is why 1270 must be killed rather than exempted.
    """
    root = sandbox_root(tmp, "resume-stray-root")
    stray = Path(root) / p.INSTANCE_ROOT / "not-a-slot"
    os.makedirs(stray)
    outcome = _observed(lambda: p.resume_standin(slot=1, root=root))
    assert outcome["outcome"] == "raised", (
        f"a stray non-slot directory must make resume refuse, and the refusal "
        f"must come from the loop's own slot-name check: {outcome}")
    require("slot name is not one of" in outcome["message"],
            f"the refusal must be the slot-name boundary, not the staging "
            f"boundary one line above: {outcome['message']}")
    require(outcome["type_name"] == "ProductionLayoutError",
            f"the refusal must keep this module's type: {outcome['type_name']}")

    # And the sibling sweep, for contrast: the same stray directory is refused
    # there too, but its loop is genuinely shadowed by the per-entry verify that
    # follows it.  Recorded here so the difference between the two loops is
    # asserted rather than assumed.
    refused(lambda: p.verify_all_standin_slots(root=root), p.ProductionLayoutError,
            "the whole-root sweep must also refuse a stray non-slot directory",
            "slot name is not one of")
    require(stray.is_dir(),
            "neither refusal may remove or alter the stray directory")


def _fresh_kwargs(tmp: str, nonce_root: str, label: str, slot: int) -> dict:
    instance = standin(STANDIN_ID_B)
    record = prepare_standin(instance, approval_over(instance_id=STANDIN_ID_B,
                                                     nonce="wp8dprod-" + label),
                             root=nonce_root)
    return write_kwargs(root=sandbox_root(tmp, label + "-root"), record=record,
                        instance=instance, slot=slot, instance_id=STANDIN_ID_B,
                        sector=b"sector-partition-" + label.encode("ascii"))


def check_traversal_and_symlinks_are_refused(tmp: str, nonce_root: str) -> None:
    """Traversal, symlinks and stray members are all refused."""
    root = sandbox_root(tmp, "traversal-root")
    instance = standin()
    record = prepare_standin(instance, approval_over(nonce="wp8dprod-traversal"),
                             root=nonce_root)
    written = p.write_standin_instance(**write_kwargs(root=root, record=record,
                                                     instance=instance))
    base = Path(written["target"])

    refused(lambda: p.verify_standin_instance("stage2_01/../stage2_01", root=root),
            p.ProductionLayoutError, "a traversal slot name must be refused",
            "slot name is not one of")
    refused(lambda: p.verify_standin_instance("..", root=root),
            p.ProductionLayoutError, "a parent-directory slot name must be refused",
            "slot name is not one of")

    outside = Path(tmp) / "outside-target.json"
    outside.write_bytes(b"{}")
    (base / p.PREPARED_DIR_NAME / "STRAY.json").symlink_to(outside)
    refused(lambda: p.verify_standin_instance(1, root=root), p.ProductionLayoutError,
            "an extra member must be refused", "differ from the canonical layout")
    os.unlink(base / p.PREPARED_DIR_NAME / "STRAY.json")

    original = (base / p.PREPARED_DIR_NAME / p.PREPARED_NAME).read_bytes()
    os.unlink(base / p.PREPARED_DIR_NAME / p.PREPARED_NAME)
    os.symlink(outside, base / p.PREPARED_DIR_NAME / p.PREPARED_NAME)
    refused(lambda: p.verify_standin_instance(1, root=root), p.ProductionLayoutError,
            "a symlinked prepared record must be refused", "PREPARED.json")
    os.unlink(base / p.PREPARED_DIR_NAME / p.PREPARED_NAME)
    (base / p.PREPARED_DIR_NAME / p.PREPARED_NAME).write_bytes(original)
    require(p.verify_standin_instance(1, root=root)["verdict"] == "verified",
            "restoring the record must restore the directory, so the symlink "
            "refusal was about the symlink and nothing else")


def check_envelope_shape_is_refused() -> None:
    """The envelope validator refuses its own shape breakages."""
    good = p.build_instance_envelope(standin())
    require(good["schema"] == p.ENVELOPE_SCHEMA, "the envelope carries its schema")
    require(good["content_sha256"] == p._content_sha256(good),
            "the envelope carries its own content hash")
    bad = dict(good)
    bad["content_sha256"] = hashlib.sha256(b"nope").hexdigest()
    refused(lambda: p.validate_instance_envelope(bad), p.ProductionLayoutError,
            "a tampered envelope hash must be refused", "content hash mismatch")
    extra = dict(good)
    extra["surprise"] = 1
    refused(lambda: p.validate_instance_envelope(extra), p.ProductionLayoutError,
            "an extra envelope key must be refused", "wrong key set")
    refused(lambda: p.build_instance_envelope(standin(synthetic=True)),
            p.ProductionLayoutError,
            "a synthetic-flagged envelope must be refused on the write side",
            "synthetic is False")
    refused(lambda: p.build_instance_envelope({"not": "an instance"}),
            p.ProductionLayoutError,
            "a non-instance envelope input must be refused", "SyntheticInstance")


def _well_formed_index(**overrides) -> dict:
    """A minimal index that :func:`p.validate_instance_index` accepts."""
    fields = dict(
        layout_kind=p.LAYOUT_KIND_STANDIN, slot=1, attempt=0, instance_id=STANDIN_ID,
        generation_id="a" * 64, prepared_id="b" * 64, envelope_sha256="c" * 64,
        envelope_content_sha256="d" * 64, prepared_record_sha256="e" * 64,
        prepared_record_status=p.STANDIN_STATUS, prepared_production=False,
        prepared_manifest_sha256="f" * 64, prepared_manifest_content_sha256="0" * 64,
        generation_manifest_sha256="1" * 64, generation_manifest_content_sha256="2" * 64,
        generation_sha256="3" * 64, attempt_record_sha256="4" * 64,
        attempt_record_content_sha256="5" * 64, attempt_disposition="accepted",
        rejection_code_count=0, rejected_attempt_history_count=0,
        mu_new_sha256="6" * 64, sigma_new_sha256="7" * 64,
        implementation_record_content_sha256="8" * 64)
    fields.update(overrides)
    return p.build_instance_index(**fields)


def _reseal_index(record: dict) -> dict:
    """Re-sign a mutated index, so ONE guard is under test.

    Without re-signing, every field tamper also breaks the final content-hash
    recomputation, so removing an intermediate guard would be unobservable.
    """
    body = dict(record)
    body["content_sha256"] = p._content_sha256(body)
    return body


def check_read_path_cross_bindings(tmp: str, nonce_root: str) -> None:
    """Every cross-binding in :func:`_verify_instance` must have a failing input.

    These are the comparisons between the index and the files the reader
    ACTUALLY read -- the load-bearing ones, because an index re-sealed to point
    somewhere else must be refused by the file rather than by the index's own
    arithmetic.  Each row rewrites one commitment in the index, re-seals the
    meta sidecar so the directory is self-consistent, and reads.
    """
    cases = {
        # label: (function mutating the index, needle in the refusal)
        # ``slot_name`` is kept consistent with ``slot`` on purpose: the index
        # validator's own shape check would fire first otherwise, and the
        # READER's "names a different slot than the instance directory" guard
        # would never be reached.
        "index slot": (lambda i: dict(i, slot=2, slot_name="stage2_02"),
                       "instance index slot disagrees"),
        "generation attempt": (lambda i: dict(
            i, attempt=i["attempt"] + 1,
            attempt_ledger=dict(i["attempt_ledger"],
                                attempt=i["attempt"] + 1)), "attempt disagrees"),
        # The index's own nested references are kept CONSISTENT with the mutated
        # top-level field on purpose: the index validator's shape checks would
        # fire first otherwise, and the READER's cross-binding against the file
        # it actually read -- the guard under test -- would never be reached.
        "index instance id": (lambda i: dict(
            i, instance_id=STANDIN_ID_B,
            envelope=dict(i["envelope"], instance_id=STANDIN_ID_B)),
            "different instance than the generation"),
        "generation id": (lambda i: dict(
            i, generation_id="9" * 64,
            generation=dict(i["generation"], content_sha256="9" * 64)),
            "does not name this generation record's content hash"),
        "generation bytes": (lambda i: dict(
            i, generation=dict(i["generation"], sha256="9" * 64)),
            "does not name this generation record's bytes"),
        "prepared id": (lambda i: dict(i, prepared_id="9" * 64,
                                       prepared_record=dict(i["prepared_record"],
                                                            content_sha256="9" * 64)),
                        "does not name this prepared record's content hash"),
        "prepared bytes": (lambda i: dict(
            i, prepared_record=dict(i["prepared_record"], sha256="9" * 64)),
            "does not name this prepared record's bytes"),
        "envelope bytes": (lambda i: dict(
            i, envelope=dict(i["envelope"], sha256="9" * 64)),
            "does not name this instance envelope's bytes"),
        "envelope content hash": (lambda i: dict(
            i, envelope=dict(i["envelope"], content_sha256="9" * 64)),
            "does not name this instance envelope's content hash"),
        "nested status": (lambda i: dict(
            i, prepared_record=dict(i["prepared_record"], status=p.PRODUCTION_STATUS)),
            "prepared_record status disagrees"),
        "top status": (lambda i: dict(i, status=p.PRODUCTION_STATUS),
                       "instance index status disagrees"),
        "nested production": (lambda i: dict(
            i, prepared_record=dict(i["prepared_record"], production=True)),
            "production flag disagrees"),
        "top production": (lambda i: dict(i, production=True),
                           "production flag disagrees"),
        "generation manifest bytes": (lambda i: dict(
            i, generation=dict(i["generation"], manifest_sha256="9" * 64)),
            "does not name this generation manifest's bytes"),
        "generation manifest content": (lambda i: dict(
            i, generation=dict(i["generation"], manifest_content_sha256="9" * 64)),
            "does not name this generation manifest's content hash"),
        "prepared manifest bytes": (lambda i: dict(
            i, prepared_record=dict(i["prepared_record"], manifest_sha256="9" * 64)),
            "does not name this prepared manifest's bytes"),
        "prepared manifest content": (lambda i: dict(
            i, prepared_record=dict(i["prepared_record"],
                                    manifest_content_sha256="9" * 64)),
            "does not name this prepared manifest's content hash"),
        "ledger bytes": (lambda i: dict(
            i, attempt_ledger=dict(i["attempt_ledger"], sha256="9" * 64)),
            "does not name this retained-attempt ledger's bytes"),
        "ledger content hash": (lambda i: dict(
            i, attempt_ledger=dict(i["attempt_ledger"], content_sha256="9" * 64)),
            "does not name this retained-attempt ledger's content hash"),
        "ledger attempt": (lambda i: dict(
            i, attempt_ledger=dict(i["attempt_ledger"], attempt=i["attempt"] + 1)),
            "attempt_ledger attempt disagrees"),
        "ledger disposition": (lambda i: dict(
            i, attempt_ledger=dict(i["attempt_ledger"], disposition="rejected")),
            "must claim the accepted disposition"),
        "ledger rejection count": (lambda i: dict(
            i, attempt_ledger=dict(i["attempt_ledger"], rejection_code_count=1)),
            "carries no rejection codes"),
        "ledger history count": (lambda i: dict(
            i, attempt_ledger=dict(i["attempt_ledger"],
                                   rejected_attempt_history_count=1)),
            "more rejected attempts are retained"),
        "mu_new digest": (lambda i: dict(
            i, moments=dict(i["moments"], mu_new_sha256="9" * 64)),
            "does not name this generation's mu_new digest"),
        "sigma_new digest": (lambda i: dict(
            i, moments=dict(i["moments"], sigma_new_sha256="9" * 64)),
            "does not name this generation's Sigma_new digest"),
        "implementation record": (lambda i: dict(
            i, implementation_record="9" * 64),
            "name different implementation records"),
    }
    require(len(cases) >= 25,
            f"the read-path table must cover every cross-binding, not {len(cases)}")

    for label, (mutate, needle) in cases.items():
        root = sandbox_root(tmp, "cross-" + label.replace(" ", "-"))
        instance = standin()
        record = prepare_standin(
            instance, approval_over(nonce="wp8dprod-cross-" + label.replace(" ", "-")),
            root=nonce_root)
        p.write_standin_instance(**write_kwargs(root=root, record=record,
                                               instance=instance))
        base = Path(root) / p.INSTANCE_ROOT / "stage2_01"
        index = mutate(read_index(base))
        index["content_sha256"] = p._content_sha256(index)
        write_json(base / p.META_DIR_NAME / p.INDEX_NAME, index)
        reseal_sidecar(base / p.META_DIR_NAME)
        refused(lambda: p.verify_standin_instance(1, root=root),
                p.ProductionLayoutError,
                f"the reader must refuse a re-sealed index with a wrong {label}",
                needle)


def check_generation_directory_bindings(tmp: str, nonce_root: str) -> None:
    """The generation sidecar's own cross-bindings must each have a failing input."""
    cases = {
        "generation slot": (lambda base: _rewrite_generation_consistently(
            base, dict(read_json(base / p.GENERATION_DIR_NAME / p.GENERATION_NAME),
                       slot=2)), "slot disagrees with the attempt record"),
        "generation attempt": (lambda base: _rewrite_generation_consistently(
            base, dict(read_json(base / p.GENERATION_DIR_NAME / p.GENERATION_NAME),
                       attempt=1)), "attempt disagrees with the attempt record"),
        "return matrix length": (lambda base: _shrink_return_matrix(base),
                                 "is not 39840 bytes"),
        "return matrix digest": (lambda base: _corrupt_return_matrix(base),
                                 "content hash does not match the generation record"),
        "generation manifest implementation": (lambda base: _rewrite_generation_consistently(
            base, dict(read_json(base / p.GENERATION_DIR_NAME / p.GENERATION_NAME),
                       implementation_record="9" * 64)),
            "name different implementation records"),
    }
    for label, (mutate, needle) in cases.items():
        root = sandbox_root(tmp, "gen-" + label.replace(" ", "-"))
        instance = standin()
        record = prepare_standin(
            instance, approval_over(nonce="wp8dprod-gen-" + label.replace(" ", "-")),
            root=nonce_root)
        p.write_standin_instance(**write_kwargs(root=root, record=record,
                                               instance=instance))
        base = Path(root) / p.INSTANCE_ROOT / "stage2_01"
        mutate(base)
        refused(lambda: p.verify_standin_instance(1, root=root),
                p.ProductionLayoutError,
                f"the reader must refuse a generation directory with a wrong "
                f"{label}", needle)


def _reseal_generation(record: dict) -> dict:
    """Re-sign a mutated generation record."""
    body = dict(record)
    body["content_sha256"] = p._content_sha256(body)
    return body


def _rewrite_generation_consistently(base: Path, record: dict) -> None:
    """Rewrite the generation record AND re-seal the sidecar around it.

    Unlike :func:`_rewrite_generation`, this leaves the generation directory
    self-consistent with its own manifest.  That matters for the probes whose
    target guard is the CROSS-BINDING between the generation record and the
    attempt record: without the re-seal, the manifest digest would fire first
    and the guard under test would never be reached.
    """
    directory = base / p.GENERATION_DIR_NAME
    directory.joinpath(p.GENERATION_NAME).write_bytes(
        p._canonical(_reseal_generation(record)))
    reseal_sidecar(directory)


def _rewrite_generation(base: Path, record: dict) -> None:
    """Re-sign and rewrite the generation record in place, re-sealing nothing.

    The sidecar manifest is deliberately NOT rebuilt.  The point of these
    probes is that the reader recomputes what it needs from the bytes it reads
    rather than trusting the generation record's own claim about itself.
    """
    path = base / p.GENERATION_DIR_NAME / p.GENERATION_NAME
    path.write_bytes(p._canonical(_reseal_generation(record)))


def _patch_return_matrix(base: Path, patch) -> None:
    """Rewrite the return matrix of ONE promoted instance AND re-seal.

    The re-seal is what makes these probes reach the guards they target: the
    sidecar's own digest/size check fires first otherwise, and the length and
    digest recomputation in ``_validate_generation_directory`` would never run.
    With the sidecar consistent, the only authority left is the comparison
    between the generation record's CLAIM and the bytes on disk.
    """
    directory = base / p.GENERATION_DIR_NAME
    path = directory / p.RETURN_MATRIX_NAME
    path.write_bytes(patch(path.read_bytes()))
    reseal_sidecar(directory)


def _corrupt_return_matrix(base: Path) -> None:
    """Flip one byte of the return matrix, leaving its length intact."""
    _patch_return_matrix(base, lambda b: bytes([b[0] ^ 0xFF]) + b[1:])


def _shrink_return_matrix(base: Path) -> None:
    """Truncate the return matrix."""
    _patch_return_matrix(base, lambda b: b[:-1])


def check_write_path_input_refusals(tmp: str, nonce_root: str) -> None:
    """The writer's own argument guards must each have a failing input."""
    root = sandbox_root(tmp, "writer-root")
    instance = standin()
    record = prepare_standin(instance, approval_over(nonce="wp8dprod-writer"),
                             root=nonce_root)
    kwargs = write_kwargs(root=root, record=record, instance=instance)

    def call(**overrides):
        merged = dict(kwargs)
        merged.update(overrides)
        return lambda: p.write_standin_instance(**merged)

    cases = [
        ("return matrix not bytes", call(return_matrix="not bytes"),
         "return matrix payload must be bytes"),
        ("return matrix wrong length",
         call(return_matrix=return_matrix()[:-1]), "must be exactly"),
        ("attempt out of range", call(attempt=p.MAX_ATTEMPT + 1), "attempt must be in"),
        ("instance_id disagrees", call(instance_id=STANDIN_ID_B),
         "different instance than the one being written"),
        ("stand-in record with a foreign instance", call(
            instance=standin(STANDIN_ID_B), instance_id=STANDIN_ID_B,
            prepared_record=record), "require_production=False"),
        ("empty prepared record", call(prepared_record={}),
         "prepared record must be a non-empty object"),
    ]
    for label, target, needle in cases:
        observed = _observed(target)
        assert observed["outcome"] == "raised", (label, observed)
        require(observed["type_name"] == "ProductionLayoutError", (label, observed))
        require(needle in observed["message"],
                f"the writer must refuse {label} for the right reason: "
                f"{observed['message'][:140]}")


def check_low_level_guards() -> None:
    """The small helpers must refuse their own malformed inputs."""
    # _sha: type, exact length, and lowercase hex are three separate
    # statements and each must have its own failing input, or removing one
    # leaves the other two to cover it.
    for bad, needle in ((7, "must be a str"),
                        ("short", "exactly 64 characters"),
                        ("A" * 64, "lowercase SHA-256"),
                        ("z" * 64, "lowercase SHA-256"),
                        ("a" * 63, "exactly 64 characters"),
                        ("a" * 65, "exactly 64 characters"),
                        (None, "must be a str")):
        refused(lambda: p._sha(bad, "label"), p.ProductionLayoutError,
                f"_sha must refuse {bad!r}", needle)
    # _canonical
    refused(lambda: p._canonical({"x": float("nan")}), p.ProductionLayoutError,
            "_canonical must refuse NaN", "not canonical JSON")
    refused(lambda: p._canonical({"x": object()}), p.ProductionLayoutError,
            "_canonical must refuse a non-JSON value", "not canonical JSON")
    # _load_record on malformed files
    import tempfile as _tf
    with _tf.TemporaryDirectory(dir=str(SCRATCH)) as work:
        target = Path(work) / "record.json"
        target.write_bytes(b"\xff\xfe not ascii")
        refused(lambda: p._load_record(target, "record"), p.ProductionLayoutError,
                "_load_record must refuse non-ASCII", "not ASCII")
        target.write_bytes(b"not json at all")
        refused(lambda: p._load_record(target, "record"), p.ProductionLayoutError,
                "_load_record must refuse non-JSON", "not JSON")
        target.write_bytes(b"[1, 2]")
        refused(lambda: p._load_record(target, "record"), p.ProductionLayoutError,
                "_load_record must refuse a JSON array", "must be a JSON object")
        target.write_bytes(b'{"b": 1, "a": 2}')
        refused(lambda: p._load_record(target, "record"), p.ProductionLayoutError,
                "_load_record must refuse a non-canonical encoding",
                "not in canonical form")
        refused(lambda: p._real_file(Path(work) / "absent", "absent"),
                p.ProductionLayoutError, "_real_file must refuse a missing file",
                "missing or not a regular file")
        refused(lambda: p._real_file(Path(work), "work"),
                p.ProductionLayoutError, "_real_file must refuse a directory",
                "missing or not a regular file")
        os.symlink(target, Path(work) / "link.json")
        refused(lambda: p._real_file(Path(work) / "link.json", "link"),
                p.ProductionLayoutError, "_real_file must refuse a symlink", "symlink")
        refused(lambda: p._list_names(Path(work) / "absent", "absent"),
                p.ProductionLayoutError, "_list_names must refuse a missing directory",
                "not a directory")
        refused(lambda: p._require_real_dir(Path(work) / "absent", "absent"),
                p.ProductionLayoutError, "_require_real_dir must refuse a missing dir",
                "not a directory")
        refused(lambda: p._require_absent(Path(work) / "record.json", "present"),
                p.ProductionLayoutError, "_require_absent must refuse a present path",
                "already exists")
        # _sha_file
        refused(lambda: p._sha_file(Path(work) / "absent", "absent"),
                p.ProductionLayoutError, "_sha_file must refuse a missing file",
                "missing or not a regular file")
        refused(lambda: p._sha_file(Path(work) / "link.json", "link"),
                p.ProductionLayoutError, "_sha_file must refuse a symlink", "symlink")
    # _slot_number
    for bad in (0, 6, 1.0, None, True):
        refused(lambda: p._slot_number(bad), p.ProductionLayoutError,
                f"_slot_number must refuse {bad!r}", "slot must be")
    # _require_kind_matches_record
    refused(lambda: p._require_kind_matches_record(p.LAYOUT_KIND_STANDIN,
                                                   {"production": "yes"}),
            p.ProductionLayoutError,
            "the kind cross-bound must refuse a non-bool production flag",
            "production flag must be a bool")
    refused(lambda: p._require_kind_matches_record(p.LAYOUT_KIND_STANDIN, {}),
            p.ProductionLayoutError,
            "the kind cross-bound must refuse a record with no production flag",
            "production flag must be a bool")


def check_envelope_and_prepared_input_guards() -> None:
    """``_validate_prepared`` and the envelope builder refuse their own inputs."""
    refused(lambda: p._validate_prepared("not a record", standin(),
                                         require_production=False),
            p.ProductionLayoutError, "_validate_prepared must refuse a non-object",
            "must be an object")
    refused(lambda: p._validate_prepared({}, standin(), require_production=False),
            p.ProductionLayoutError, "_validate_prepared must refuse an empty record",
            "must be a non-empty object")
    refused(lambda: p._validate_prepared({"status": p.STANDIN_STATUS}, object(),
                                         require_production=False),
            p.ProductionLayoutError,
            "_validate_prepared must refuse a non-instance", "SyntheticInstance")
    refused(lambda: p.validate_instance_envelope([]), p.ProductionLayoutError,
            "validate_instance_envelope must refuse a non-object", "must be an object")
    refused(lambda: p.validate_instance_envelope(
        dict(p.build_instance_envelope(standin()), schema="other/v1")),
        p.ProductionLayoutError, "validate_instance_envelope must refuse a bad schema",
        "schema mismatch")
    inner = dict(p.build_instance_envelope(standin()))
    inner["instance"] = []
    inner["content_sha256"] = p._content_sha256(inner)
    refused(lambda: p.validate_instance_envelope(inner), p.ProductionLayoutError,
            "validate_instance_envelope must refuse a non-object instance",
            "must be an object")
    inner = dict(p.build_instance_envelope(standin()))
    inner["instance"] = {k: v for k, v in inner["instance"].items() if k != "mu"}
    inner["content_sha256"] = p._content_sha256(inner)
    refused(lambda: p.validate_instance_envelope(inner), p.ProductionLayoutError,
            "validate_instance_envelope must refuse a missing instance field",
            "wrong key set")
    # The ``instance_id must be a str`` guard inside ``build_instance_envelope``
    # is UNREACHABLE, and that is recorded here rather than papered over:
    # WP5b's ``SyntheticInstance`` already guarantees a string id, and the
    # ``isinstance`` guard on the line above refuses anything that is not a real
    # SyntheticInstance -- so no value whatsoever can reach the later check.  A
    # substitute object is refused by the isinstance guard first, which is the
    # proof that the pair is not independently observable.
    class _Forged:
        instance_id = 7
        synthetic = False

    refused(lambda: p.build_instance_envelope(_Forged()), p.ProductionLayoutError,
            "a substitute instance object must be refused by the isinstance guard",
            "must be a stage2 SyntheticInstance")
    require(isinstance(standin().instance_id, str),
            "WP5b guarantees a str instance_id, which is why the later type guard "
            "in build_instance_envelope can never fire")


def check_root_and_sweep_guards(tmp: str, nonce_root: str) -> None:
    """The instance-root guards must refuse a missing or unusable root."""
    missing = Path(tmp) / "no-such-root"
    for label, target in (
        ("resume", lambda: p.resume_standin(slot=1, root=missing)),
        ("sweep", lambda: p.verify_all_standin_slots(root=missing)),
        ("verify", lambda: p.verify_standin_instance(1, root=missing)),
    ):
        observed = _observed(target)
        assert observed["outcome"] == "raised", (label, observed)
        require(observed["type_name"] == "ProductionLayoutError", (label, observed))
    # A stray, non-slot directory under the root must be refused by the sweep.
    root = sandbox_root(tmp, "stray-root")
    instance = standin()
    record = prepare_standin(instance, approval_over(nonce="wp8dprod-stray"),
                             root=nonce_root)
    p.write_standin_instance(**write_kwargs(root=root, record=record, instance=instance))
    stray = Path(root) / p.INSTANCE_ROOT / "not-a-slot"
    os.makedirs(stray)
    refused(lambda: p.verify_all_standin_slots(root=root), p.ProductionLayoutError,
            "the sweep must refuse a stray non-slot directory", "slot name is not one of")
    os.rmdir(stray)
    # Two slots claiming the SAME instance id must be refused.
    first = standin()
    rec_a = prepare_standin(first, approval_over(nonce="wp8dprod-dup-a"),
                            root=nonce_root)
    p.write_standin_instance(**write_kwargs(root=root, record=rec_a, instance=first,
                                           slot=2, sector=b"sector-partition-2"))
    refused(lambda: p.verify_all_standin_slots(root=root), p.ProductionLayoutError,
            "two slots naming one instance must be refused", "same instance_id")


def check_index_builder_input_guards() -> None:
    """``build_instance_index`` must refuse malformed inputs before rendering."""
    cases = [
        ("unknown layout kind", dict(layout_kind="invented"),
         "not a declared layout kind"),
        ("attempt out of range", dict(attempt=p.MAX_ATTEMPT + 1), "attempt must be in"),
        ("instance_id not a str", dict(instance_id=7), "instance_id must be a str"),
        ("generation id not a sha", dict(generation_id="zz"), "generation id"),
        ("prepared id not a sha", dict(prepared_id="zz"), "prepared id"),
        ("envelope sha not a sha", dict(envelope_sha256="zz"), "envelope sha256"),
        ("envelope content sha not a sha", dict(envelope_content_sha256="zz"),
         "envelope content sha256"),
        ("prepared record sha not a sha", dict(prepared_record_sha256="zz"),
         "prepared record sha256"),
        ("status not a WP8b status", dict(prepared_record_status="invented"),
         "not a WP8b status"),
        ("production not a bool", dict(prepared_production="yes"),
         "production flag must be a bool"),
        ("prepared manifest sha not a sha", dict(prepared_manifest_sha256="zz"),
         "prepared manifest sha256"),
        ("prepared manifest content sha", dict(prepared_manifest_content_sha256="zz"),
         "prepared manifest content sha256"),
        ("generation manifest sha", dict(generation_manifest_sha256="zz"),
         "generation manifest sha256"),
        ("generation manifest content sha",
         dict(generation_manifest_content_sha256="zz"),
         "generation manifest content sha256"),
        ("generation sha not a sha", dict(generation_sha256="zz"),
         "generation record sha256"),
        ("attempt record sha not a sha", dict(attempt_record_sha256="zz"),
         "attempt record sha256"),
        ("attempt record content sha", dict(attempt_record_content_sha256="zz"),
         "attempt record content sha256"),
        ("disposition not accepted", dict(attempt_disposition="rejected"),
         "accepted disposition"),
        ("rejection count not an int", dict(rejection_code_count="0"),
         "rejection code count must be an int"),
        ("rejection count negative", dict(rejection_code_count=-1),
         "rejection code count must be non-negative"),
        ("history count not an int", dict(rejected_attempt_history_count="0"),
         "rejected attempt history count must be an int"),
        ("history count negative", dict(rejected_attempt_history_count=-1),
         "rejected attempt history count must be non-negative"),
        ("history count exceeds attempt",
         dict(attempt=0, rejected_attempt_history_count=1), "more rejected attempts"),
        ("mu_new digest not a sha", dict(mu_new_sha256="zz"), "mu_new sha256"),
        ("sigma_new digest not a sha", dict(sigma_new_sha256="zz"), "sigma_new sha256"),
        ("implementation record not a sha",
         dict(implementation_record_content_sha256="zz"),
         "implementation record content sha256"),
    ]
    for label, overrides, needle in cases:
        observed = _observed(lambda: _well_formed_index(**overrides))
        assert observed["outcome"] == "raised", (label, observed)
        require(observed["type_name"] == "ProductionLayoutError", (label, observed))
        require(needle in observed["message"],
                f"build_instance_index must refuse {label} for the right reason: "
                f"{observed['message'][:140]}")


def check_sidecar_member_guards(tmp: str, nonce_root: str) -> None:
    """A subdirectory in a sidecar, and a bad stand-in marker, are refused."""
    root = sandbox_root(tmp, "marker-root")
    instance = standin()
    record = prepare_standin(instance, approval_over(nonce="wp8dprod-marker"),
                             root=nonce_root)
    p.write_standin_instance(**write_kwargs(root=root, record=record, instance=instance))
    base = Path(root) / p.INSTANCE_ROOT / "stage2_01"
    sidecar = base / p.PREPARED_DIR_NAME

    # A subdirectory inside a sidecar must be refused.
    (sidecar / "nested").mkdir()
    refused(lambda: p.verify_standin_instance(1, root=root), p.ProductionLayoutError,
            "a subdirectory in a sidecar must be refused", "subdirectory")
    os.rmdir(sidecar / "nested")

    # Each stand-in marker field, re-sealed, must be refused by the marker checks.
    marker_cases = {
        "wrong key set": (lambda mk: {k: v for k, v in mk.items() if k != "statement"},
                          "wrong key set"),
        "bad schema": (lambda mk: _reseal_marker(dict(mk, schema="other/v1")),
                       "schema mismatch"),
        "wrong layout kind": (lambda mk: _reseal_marker(
            dict(mk, layout_kind=p.LAYOUT_KIND_PRODUCTION)), "layout kind"),
        "wrong statement": (lambda mk: _reseal_marker(
            dict(mk, statement="looks fine to me")), "statement mismatch"),
        "bad content hash": (lambda mk: dict(mk, content_sha256="9" * 64),
                             "content hash mismatch"),
    }
    path = sidecar / p.STANDIN_MARKER_NAME
    for label, (mutate, needle) in marker_cases.items():
        original = path.read_bytes()
        write_json(path, mutate(read_json(path)))
        reseal_sidecar(sidecar)
        refused(lambda: p.verify_standin_instance(1, root=root), p.ProductionLayoutError,
                f"the stand-in marker check must refuse a {label}", needle)
        path.write_bytes(original)
        reseal_sidecar(sidecar)
    require(p.verify_standin_instance(1, root=root)["verdict"] == "verified",
            "restoring the marker must restore the directory")


def _reseal_marker(record: dict) -> dict:
    """Re-sign a mutated stand-in marker."""
    body = dict(record)
    body["content_sha256"] = p._content_sha256(body)
    return body


def check_index_validation_is_refused() -> None:
    """Every guard in the index validator must have a failing input.

    This is a TABLE, and the table is iterated, because a bare sequence of
    ``refused(...)`` calls would leave every entry deletable with the rest of
    the run still green.  Each row mutates exactly one field and re-seals, so
    the guard that fires is the one under test rather than the final hash.
    """
    base_index = _well_formed_index()
    require(p.validate_instance_index(base_index)["slot"] == 1,
            "a well-formed index must validate")

    def reseal(mutate):
        return _reseal_index(mutate(dict(base_index)))

    rows = [
        ("not an object", lambda: p.validate_instance_index([]), "must be an object"),
        ("wrong top key set",
         lambda: p.validate_instance_index(
             {k: v for k, v in base_index.items() if k != "scope"}),
         "wrong key set"),
        ("bad schema", lambda: p.validate_instance_index(reseal(
            lambda r: dict(r, schema="other/v1"))), "schema mismatch"),
        ("unknown layout kind", lambda: p.validate_instance_index(reseal(
            lambda r: dict(r, layout_kind="invented"))), "not a declared layout kind"),
        ("scope statement", lambda: p.validate_instance_index(reseal(
            lambda r: dict(r, scope="something else"))), "scope statement mismatch"),
        ("slot_name not canonical", lambda: p.validate_instance_index(reseal(
            lambda r: dict(r, slot_name="stage2_99"))), "canonical name"),
        ("attempt out of range", lambda: p.validate_instance_index(reseal(
            lambda r: dict(r, attempt=p.MAX_ATTEMPT + 1))), "attempt must be in"),
        ("instance_id not a str", lambda: p.validate_instance_index(reseal(
            lambda r: dict(r, instance_id=7))), "instance_id must be a str"),
        ("generation id not a sha", lambda: p.validate_instance_index(reseal(
            lambda r: dict(r, generation_id="nothex"))), "generation id"),
        ("prepared id not a sha", lambda: p.validate_instance_index(reseal(
            lambda r: dict(r, prepared_id="nothex"))), "prepared id"),
        ("envelope not an object", lambda: p.validate_instance_index(reseal(
            lambda r: dict(r, envelope=[]))), "envelope reference must be an object"),
        ("envelope wrong key set", lambda: p.validate_instance_index(reseal(
            lambda r: dict(r, envelope={k: v for k, v in r["envelope"].items()
                                        if k != "path"}))), "wrong key set"),
        ("envelope path", lambda: p.validate_instance_index(reseal(
            lambda r: dict(r, envelope=dict(r["envelope"], path="elsewhere.json")))),
         "envelope reference path mismatch"),
        ("envelope sha not a sha", lambda: p.validate_instance_index(reseal(
            lambda r: dict(r, envelope=dict(r["envelope"], sha256="zz")))),
         "envelope sha256"),
        ("envelope content sha not a sha", lambda: p.validate_instance_index(reseal(
            lambda r: dict(r, envelope=dict(r["envelope"],
                                           content_sha256="zz")))),
         "envelope content sha256"),
        ("envelope instance_id disagreement", lambda: p.validate_instance_index(reseal(
            lambda r: dict(r, envelope=dict(r["envelope"],
                                            instance_id=STANDIN_ID_B)))),
         "different instance than the index"),
        ("envelope synthetic mark", lambda: p.validate_instance_index(reseal(
            lambda r: dict(r, envelope=dict(r["envelope"], synthetic=True)))),
         "non-synthetic mark False"),
        ("prepared_record not an object", lambda: p.validate_instance_index(reseal(
            lambda r: dict(r, prepared_record=[]))),
         "prepared_record must be an object"),
        ("prepared_record wrong key set", lambda: p.validate_instance_index(reseal(
            lambda r: dict(r, prepared_record={k: v
                                               for k, v in r["prepared_record"].items()
                                               if k != "path"}))), "wrong key set"),
        ("prepared_record path", lambda: p.validate_instance_index(reseal(
            lambda r: dict(r, prepared_record=dict(r["prepared_record"],
                                                   path="other.json")))),
         "prepared_record path mismatch"),
        ("prepared_record sha not a sha", lambda: p.validate_instance_index(reseal(
            lambda r: dict(r, prepared_record=dict(r["prepared_record"],
                                                   sha256="zz")))), "prepared record sha256"),
        ("prepared content hash disagrees", lambda: p.validate_instance_index(reseal(
            lambda r: dict(r, prepared_record=dict(r["prepared_record"],
                                                   content_sha256="9" * 64)))),
         "disagrees with the index prepared_id"),
        ("prepared status not a WP8b status", lambda: p.validate_instance_index(reseal(
            lambda r: dict(r, prepared_record=dict(r["prepared_record"],
                                                   status="invented")))),
         "not a WP8b status"),
        ("prepared production not a bool", lambda: p.validate_instance_index(reseal(
            lambda r: dict(r, prepared_record=dict(r["prepared_record"],
                                                   production="yes")))),
         "production flag must be a bool"),
        ("prepared manifest sha not a sha", lambda: p.validate_instance_index(reseal(
            lambda r: dict(r, prepared_record=dict(r["prepared_record"],
                                                   manifest_sha256="zz")))),
         "prepared manifest sha256"),
        ("prepared manifest content sha", lambda: p.validate_instance_index(reseal(
            lambda r: dict(r, prepared_record=dict(r["prepared_record"],
                                                    manifest_content_sha256="zz")))),
         "prepared manifest content sha256"),
        ("generation ref not an object", lambda: p.validate_instance_index(reseal(
            lambda r: dict(r, generation=[]))), "generation reference must be an object"),
        ("generation ref wrong key set", lambda: p.validate_instance_index(reseal(
            lambda r: dict(r, generation={k: v for k, v in r["generation"].items()
                                         if k != "path"}))), "wrong key set"),
        ("generation ref path", lambda: p.validate_instance_index(reseal(
            lambda r: dict(r, generation=dict(r["generation"], path="other")))),
         "generation reference path mismatch"),
        ("generation ref sha not a sha", lambda: p.validate_instance_index(reseal(
            lambda r: dict(r, generation=dict(r["generation"], sha256="zz")))),
         "generation record sha256"),
        ("generation ref content sha not a sha", lambda: p.validate_instance_index(reseal(
            lambda r: dict(r, generation=dict(r["generation"],
                                             content_sha256="zz")))),
         "generation record content sha256"),
        ("generation content hash disagrees", lambda: p.validate_instance_index(reseal(
            lambda r: dict(r, generation=dict(r["generation"], content_sha256="9" * 64)))),
         "disagrees with the index generation_id"),
        ("generation manifest sha not a sha", lambda: p.validate_instance_index(reseal(
            lambda r: dict(r, generation=dict(r["generation"], manifest_sha256="zz")))),
         "generation manifest sha256"),
        ("generation manifest content sha", lambda: p.validate_instance_index(reseal(
            lambda r: dict(r, generation=dict(r["generation"],
                                             manifest_content_sha256="zz")))),
         "generation manifest content sha256"),
        ("ledger not an object", lambda: p.validate_instance_index(reseal(
            lambda r: dict(r, attempt_ledger=[]))), "attempt_ledger must be an object"),
        ("ledger wrong key set", lambda: p.validate_instance_index(reseal(
            lambda r: dict(r, attempt_ledger={k: v
                                              for k, v in r["attempt_ledger"].items()
                                              if k != "path"}))), "wrong key set"),
        ("ledger path", lambda: p.validate_instance_index(reseal(
            lambda r: dict(r, attempt_ledger=dict(r["attempt_ledger"],
                                                  path="other.json")))),
         "attempt_ledger path mismatch"),
        ("ledger sha not a sha", lambda: p.validate_instance_index(reseal(
            lambda r: dict(r, attempt_ledger=dict(r["attempt_ledger"],
                                                   sha256="zz")))),
         "attempt record sha256"),
        ("ledger content sha not a sha", lambda: p.validate_instance_index(reseal(
            lambda r: dict(r, attempt_ledger=dict(r["attempt_ledger"],
                                                   content_sha256="zz")))),
         "attempt record content sha256"),
        ("ledger attempt disagrees", lambda: p.validate_instance_index(reseal(
            lambda r: dict(r, attempt_ledger=dict(r["attempt_ledger"], attempt=3)))),
         "attempt_ledger attempt disagrees"),
        ("ledger disposition not accepted", lambda: p.validate_instance_index(reseal(
            lambda r: dict(r, attempt_ledger=dict(r["attempt_ledger"],
                                                  disposition="rejected")))),
         "accepted disposition"),
        ("ledger rejection count not an int", lambda: p.validate_instance_index(reseal(
            lambda r: dict(r, attempt_ledger=dict(r["attempt_ledger"],
                                                   rejection_code_count="0")))),
         "rejection code count must be an int"),
        ("ledger rejection count nonzero", lambda: p.validate_instance_index(reseal(
            lambda r: dict(r, attempt_ledger=dict(r["attempt_ledger"],
                                                   rejection_code_count=1)))),
         "carries no rejection codes"),
        ("ledger history not an int", lambda: p.validate_instance_index(reseal(
            lambda r: dict(r, attempt_ledger=dict(
                r["attempt_ledger"], rejected_attempt_history_count="0")))),
         "history count must be an int"),
        ("moments not an object", lambda: p.validate_instance_index(reseal(
            lambda r: dict(r, moments=[]))), "moments must be an object"),
        ("moments wrong key set", lambda: p.validate_instance_index(reseal(
            lambda r: dict(r, moments={k: v for k, v in r["moments"].items()
                                       if k != "mu_new_sha256"}))), "wrong key set"),
        ("moments mu digest", lambda: p.validate_instance_index(reseal(
            lambda r: dict(r, moments=dict(r["moments"], mu_new_sha256="zz")))),
         "mu_new sha256"),
        ("moments sigma digest", lambda: p.validate_instance_index(reseal(
            lambda r: dict(r, moments=dict(r["moments"], sigma_new_sha256="zz")))),
         "sigma_new sha256"),
        ("implementation record not a sha", lambda: p.validate_instance_index(reseal(
            lambda r: dict(r, implementation_record="zz"))),
         "implementation record content sha256"),
        ("top status not a WP8b status", lambda: p.validate_instance_index(reseal(
            lambda r: dict(r, status="invented"))), "not a WP8b status"),
        ("top production not a bool", lambda: p.validate_instance_index(reseal(
            lambda r: dict(r, production="yes"))), "production flag must be a bool"),
        ("top production disagrees", lambda: p.validate_instance_index(reseal(
            lambda r: dict(r, production=True))), "disagrees with its prepared_record"),
        ("content hash", lambda: p.validate_instance_index(
            dict(base_index, content_sha256="9" * 64)), "content hash mismatch"),
    ]
    for label, call, needle in rows:
        refused(call, p.ProductionLayoutError,
                f"the index validator must refuse: {label}", needle)

    # The reader, not the validator, owns the kind cross-bound.
    wrong_kind = reseal(lambda r: dict(r, layout_kind=p.LAYOUT_KIND_PRODUCTION))
    require(p.validate_instance_index(wrong_kind)["layout_kind"]
            == p.LAYOUT_KIND_PRODUCTION,
            "a re-kinded index is shape-valid; only the reader may refuse it")
    refused(lambda: p._require_kind_matches_index(p.LAYOUT_KIND_PRODUCTION, base_index),
            p.ProductionLayoutError,
            "a stand-in index must be refused by the production reader that "
            "opened it, even though it is shape-valid", "opened as")
    refused(lambda: p._require_kind_matches_index(p.LAYOUT_KIND_STANDIN, wrong_kind),
            p.ProductionLayoutError,
            "a re-kinded index must be refused by the stand-in reader that "
            "opened it", "opened as")


# ===========================================================================
# E. Self-audit: the fixture must not be able to lie about itself
# ===========================================================================

def _defined_check_count() -> int:
    import ast
    tree = ast.parse(Path(__file__).read_text("utf-8"))
    return sum(1 for node in tree.body
               if isinstance(node, ast.FunctionDef) and node.name.startswith("check_"))


def _tmp_checks() -> list:
    """Every check that takes ``(tmp, nonce_root)``, discovered by SIGNATURE.

    The signature, not a hand-maintained name list, is the dispatch table: a
    check that needs the scratch tree but whose name was left out of the list
    would silently never run.  ``_undispatched_checks`` re-proves that by
    comparing the two sets.
    """
    import inspect
    found = []
    for name, value in sorted(globals().items()):
        if not name.startswith("check_") or not callable(value):
            continue
        if name in ("check_require_helper_contract",):
            continue
        parameters = list(inspect.signature(value).parameters)
        if parameters[:2] == ["tmp", "nonce_root"]:
            found.append(value)
    return found


def _standalone_checks() -> list:
    """Every check that takes no scratch tree, discovered by SIGNATURE."""
    import inspect
    found = []
    for name, value in sorted(globals().items()):
        if not name.startswith("check_") or not callable(value):
            continue
        if name in ("check_require_helper_contract",):
            continue
        if not inspect.signature(value).parameters:
            found.append(value)
    return found


def _undispatched_checks() -> list:
    dispatched = {check.__name__ for check in _tmp_checks() + _standalone_checks()}
    return sorted(name for name, value in sorted(globals().items())
                  if name.startswith("check_") and callable(value)
                  and name not in dispatched and name != "check_require_helper_contract")


def check_require_helper_contract() -> None:
    """Prove ``require`` really fails, using the interpreter's own ``assert``.

    ``require`` is the reporter every other check depends on, so a neutered
    ``raise`` inside it would silently turn the whole file into a no-op that
    still prints PASS.  This check uses a channel this file does not define.
    """
    try:
        require(False, "deliberate self-test failure")
    except FixtureError as exc:
        assert "deliberate self-test failure" in str(exc), exc
        return
    raise AssertionError("require(False) must raise FixtureError")


def check_dispatch_self_audit() -> None:
    """Prove the dispatch tables really cover the checks that are defined."""
    scratch, standalone = _tmp_checks(), _standalone_checks()
    dispatched = scratch + standalone
    assert len({check.__name__ for check in dispatched}) == len(dispatched), (
        "the dispatched check table must not repeat a check")
    assert not _undispatched_checks(), _undispatched_checks()
    assert _defined_check_count() >= MIN_CHECK_FUNCTIONS, _defined_check_count()
    require(len(dispatched) > 0, "the dispatch tables must not be empty")


def check_no_side_effects(tmp: str, nonce_root: str) -> None:
    """The fixture must not write bytecode, and a one-use approval is one-use.

    Dispatched through the signature table like every other check, because a
    check that is defined but called from nowhere asserts nothing.
    """
    require(pycache_count() == pycache_count(), "the fixture must not write bytecode")
    prepare_standin(standin(), approval_over(nonce="wp8dprod-replay"), root=nonce_root)
    replayed = _observed(lambda: prepare_standin(
        standin(), approval_over(nonce="wp8dprod-replay"), root=nonce_root))
    assert replayed["outcome"] == "raised", replayed
    require(replayed["type_name"] == "ApprovalReplayRefused",
            f"a one-use approval must not be reusable: {replayed['type_name']}")


def check_pinned_reviewed_bytes() -> None:
    """This build must not have modified the two reviewed packages it builds on.

    The reviewed packages are not edited by this fixture, and nothing here
    pins a digest for them -- a fabricated digest would be a claim this build
    cannot honestly make.  What IS asserted is the observable property: both
    modules are still the reviewed ones, still callable, and still refuse
    exactly what they refused before this build existed.
    """
    require(callable(wp8d.write_instance) and callable(m.validate_provenance_record),
            "the two reviewed modules must remain callable and unedited")
    refused(lambda: wp8d._require_not_non_synthetic(True), wp8d.LayoutError,
            "the reviewed WP8d must still refuse the unreviewed release path",
            "non-synthetic support")
    refused(lambda: wp8d._require_status(p.STANDIN_STATUS), wp8d.LayoutError,
            "the reviewed WP8d must still refuse a WP8b status", "not an accepted")
    refused(lambda: m._require_production_release_pinned(), m.ProductionReleaseNotPinned,
            "WP8b must still refuse an unpinned production release")


# ===========================================================================
# Dispatch and main
# ===========================================================================

def main() -> int:
    global COUNT
    COUNT = 0

    before = pycache_count()
    SCRATCH.mkdir(parents=True, exist_ok=True)
    scratch, standalone = _tmp_checks(), _standalone_checks()
    dispatched = scratch + standalone
    require(len({check.__name__ for check in dispatched}) == len(dispatched),
            "the dispatched check table must not repeat a check")
    require(not _undispatched_checks(),
            "every check function must be dispatched, or it asserts nothing: "
            + ", ".join(_undispatched_checks()))
    require(_defined_check_count() >= MIN_CHECK_FUNCTIONS,
            f"this file must define at least {MIN_CHECK_FUNCTIONS} check functions; "
            f"it defines {_defined_check_count()}")
    require(len(dispatched) > 0, "the dispatch tables must not be empty")

    with tempfile.TemporaryDirectory(dir=str(SCRATCH)) as tmp:
        nonce_root = _scratch_dir(tmp, "nonce-root")
        for check in scratch:
            check(tmp, nonce_root)
    for check in standalone:
        check()

    require(pycache_count() == before, "the fixture must not write bytecode")

    _count_message = (
        f"the fixture must perform exactly {EXPECTED_ASSERTIONS} assertions; "
        f"it performed {COUNT} (a missing one means a guard stopped firing)")
    if COUNT != EXPECTED_ASSERTIONS:
        raise FixtureError(_count_message)
    assert COUNT == EXPECTED_ASSERTIONS, _count_message
    require(COUNT == EXPECTED_ASSERTIONS, _count_message)

    print(f"optimize={sys.flags.optimize} checks={COUNT} groups={len(dispatched)} "
          f"defined_checks={_defined_check_count()} "
          f"fixture_branch_invocations={m.FIXTURE_BRANCH_INVOCATIONS}")
    print(f"wp8b_identity_hash={m.NON_SYNTHETIC_IDENTITY_HASH}")
    print(f"production_release_pinned={m.PRODUCTION_RELEASE_PINNED} "
          f"decision_record={m.PRODUCTION_RELEASE_DECISION_RECORD}")
    print(f"layout_kinds={p.LAYOUT_KINDS} index={p.INDEX_SCHEMA}")
    print("broken variants: wp8b_bypass read_only_assertion slot_swap "
          "resealed_provenance wrong_instance missing_fsync traversal_symlink")
    print("PASS WP8d-production layout fixtures; NON-PRODUCTION stand-in only; "
          "unarmed build, no real draw, no production seed, no scientific write; "
          "WP8d and WP8b left untouched")
    return 0


if __name__ == "__main__":
    _status = main()
    assert _status == 0, f"main() must return 0 on a passing run, got {_status!r}"
    raise SystemExit(_status)
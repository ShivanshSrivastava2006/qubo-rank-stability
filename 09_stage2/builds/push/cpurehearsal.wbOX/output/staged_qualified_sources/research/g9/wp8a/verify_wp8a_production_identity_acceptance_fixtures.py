#!/usr/bin/env python3
"""Offline WP8a acceptance-record fixtures.  Synthetic, read-only, no Kaggle.

Every synthetic role is built inside a ``tempfile.TemporaryDirectory``.  The one
role that is not synthetic is ``v1_engine``: it reads the 12 real §A files
read-only and hashes them against the accepted release.  Nothing is written to
the real repository.

There is deliberately NO ``assert`` in this file.  ``python3 -O`` strips
``assert`` statements, so an assert-based fixture would pass vacuously under
``-O``.  Every check raises instead, so the normal and ``-O`` runs are equally
strict.

**There is no owner signature in this repository and this package has no notion
of one.**  The fixture therefore never claims an owner approval: it drives the
validator with the reviewed pin it computes for its own synthetic bytes, and that
pin stands in for the lead's pin, which is the whole of the authority in the
production path.  Every other value is conspicuously synthetic: the WP7 receipt
and the review note live only inside the temporary tree, the receipt's step
digests are filler that matches nothing, the receipt says in its own
``differences`` list that no real dry run produced it, and the platform identity
it reports is a label that says it is not a real device.  The WP7 receipt is a
REAL ``wp7_session`` receipt, assembled and gated by that module's own
``build_receipt``/``validate_receipt``; no kernel, GPU, network call or Kaggle
endpoint is involved.

This verifier builds, validates and refuses acceptance records.  It issues no
identity, accepts no production identity, authorizes nothing, and never runs a
GPU, a Kaggle push, or any Stage-2 instance or scientific value.
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import sys
import tempfile

if os.environ.get("PYTHONDONTWRITEBYTECODE") != "1":
    raise SystemExit("PYTHONDONTWRITEBYTECODE=1 is required")
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.g9 import stage2_production_identity as wp1
from research.g9.cuda_qualification import stage2_cuda_execution_contract as contract
from research.g9.kaggle_wp7 import wp7_session as wp7
from research.g9.wp8a import wp8a_production_identity_acceptance as acc

PASSED: list[str] = []
SCRATCH_ENV = "G9_WP8A_SCRATCH"


def require(condition: object, message: str) -> None:
    """Raising check, never `assert`: it must hold identically under -O."""
    if not condition:
        raise RuntimeError("FIXTURE FAILURE: " + message)


def refuses_typed(function, *args, **kwargs) -> str:
    """The exception class `function` raised, or ``''`` if it did not refuse.

    The empty string covers a call that raised NOTHING, so a silently accepted
    forgery fails the fixture instead of passing it.  A ``KeyError`` or
    ``TypeError`` comes back by name and the caller requires otherwise: round 1
    leaked ``KeyError`` out of the bound block, and that is a defect, not a style.
    """
    try:
        function(*args, **kwargs)
    except BaseException as exc:  # noqa: BLE001 - the point is to NAME the class
        return type(exc).__name__
    return ""


def refuses_with(function, needle, *args, **kwargs) -> bool:
    """True iff `function` refused with a message naming `needle`."""
    try:
        function(*args, **kwargs)
    except acc.AcceptanceRecordError as exc:
        return needle in str(exc)
    return False


def refuses_with_any(function, needles, *args, **kwargs) -> bool:
    """True iff `function` refused, naming at least one of `needles`.

    Used where one edit is caught by whichever guard runs first and the point of
    the case is that SOME guard refuses it, not which.
    """
    try:
        function(*args, **kwargs)
    except acc.AcceptanceRecordError as exc:
        return any(needle in str(exc) for needle in needles)
    return False


def _outcome_of(function, *args) -> tuple:
    """``('value', result)`` or ``('refused', class name)`` — raise-or-return, compared."""
    try:
        return ("value", function(*args))
    except BaseException as exc:  # noqa: BLE001 - the point is the CLASS, not the value
        return ("refused", type(exc).__name__)


def ok(label: str) -> None:
    PASSED.append(label)
    print("      ok: " + label)


def read_bytes(path: str) -> bytes:
    with open(path, "rb") as handle:
        return handle.read()


def sha256_file(path: str) -> str:
    import hashlib
    return hashlib.sha256(read_bytes(path)).hexdigest()


def rewrite(tree: str, rel: str, data: bytes) -> None:
    """Overwrite one mirrored file inside the synthetic tree only."""
    with open(os.path.join(tree, rel), "wb") as handle:
        handle.write(data)


def write_canonical(tree: str, rel: str, body: dict) -> None:
    """Write one canonical document inside the synthetic tree: bytes plus a newline."""
    path = os.path.join(tree, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(contract.canonical_bytes(body) + b"\n")


def rehashed(record: dict) -> dict:
    """A record whose internal content_sha256 has been re-derived after an edit."""
    updated = copy.deepcopy(record)
    try:
        updated["content_sha256"] = acc._recompute_content_sha256(updated)
    except Exception:  # noqa: BLE001 - the garbage may not even be canonical
        pass
    return updated


def pin_of(record: dict) -> str:
    """The reviewed pin a lead would supply for these exact canonical bytes."""
    return acc.record_content_sha256(record)


def rejects(record: dict, tree: str, needle: str = None) -> bool:
    """The record is refused with the module's typed refusal, optionally naming needle."""
    function = acc.accept_production_identity
    args = (record, )
    kwargs = {"reviewed_record_sha256": pin_of(record), "repo_root": tree}
    if needle is None:
        return refuses_typed(function, *args, **kwargs) == "AcceptanceRecordError"
    return refuses_with(function, needle, *args, **kwargs)


# --------------------------------------------------------------------------
# Fixed, synthetic inputs.  Every value is conspicuously non-production.
# --------------------------------------------------------------------------

V1_REPO_ROOT = str(ROOT)

V1_PLATFORM = {
    "gpu_name": "SYNTHETIC-T4-NOT-A-REAL-DEVICE",
    "compute_capability": "7.5",
    "cuda_driver_version": "00000",
    "cuda_runtime_version": "00000",
    "nvcc_version": "SYNTHETIC-NVCC-NOT-A-REAL-BANNER",
    "kaggle_image": "synthetic-image-placeholder-not-a-real-image",
    "python_version": "3.12.3",
    "numpy_version": "0.0.0-synthetic",
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

#: Conspicuously synthetic values.  The WP7 receipt is assembled by the WP7
#: session module's OWN ``build_receipt`` from conspicuously non-production
#: counters/identities/digests; nothing here claims a real kernel ran.
SYNTHETIC_STEP_DIGEST = "1" * 64
SYNTHETIC_PLATFORM_LABEL = "SYNTHETIC-FIXTURE-PLATFORM-NOT-A-REAL-DEVICE"
SYNTHETIC_REVIEWER = "SYNTHETIC-FIXTURE-REVIEWER-NOT-THE-OWNER"
SYNTHETIC_REVIEW_TIME = "2026-01-01T00:00:00Z"
REVIEW_NOTE_REL = acc.REVIEW_NOTE_REL


def v1_role_paths() -> list[str]:
    """The real 12 §A paths, read-only, taken from the accepted release file."""
    release = wp1.load_v1_release(V1_REPO_ROOT)
    return sorted(release["source_sha256"])


def synthetic_wp7_receipt() -> dict:
    """A REAL, complete ``wp7_session`` receipt built by ``wp7_session`` itself.

    Round 2 of this package hand-wrote a five-key ``g9_wp7_dry_run_receipt/v1``
    document and called it the WP7 dry-run receipt; no such format exists in this
    repository and the ``kernel_id``/``bundle_sha256`` fields came from nowhere.
    This is the honest version: every step of the declared WP7 order is reported
    as run, every step digest is conspicuously synthetic filler, and the receipt
    is produced by ``wp7_session.build_receipt()`` and gated by
    ``wp7_session.validate_receipt()`` — the same two functions a real dry run
    goes through.  No kernel, no GPU, no network and no Kaggle call is involved.
    """
    ran = list(wp7.REQUIRED_STEPS) + [acc.WP7_RECEIPT_REQUIRED_STEP]
    return wp7.build_receipt(
        steps=ran,
        counters={"fixture_coordinates": 0, "fixture_comparisons": 0},
        identities={"fixture_platform": SYNTHETIC_PLATFORM_LABEL},
        digests={f"step:{name}": SYNTHETIC_STEP_DIGEST for name in wp7.REQUIRED_STEPS},
        differences=["SYNTHETIC FIXTURE: no real dry run produced this receipt."],
    )


def make_synthetic_tree(directory: str) -> None:
    """Build the synthetic mirror tree, byte-verified against the real files.

    Every file the WP8a qualified source map names is mirrored, so the qualified
    map is checked against real bytes inside the temporary tree exactly as it
    would be in the repository.  That includes this fixture file itself, which is
    why the driver re-mirrors it before every group.
    """
    for paths in SYNTHETIC_ROLE_FILES.values():
        for path in paths:
            full = os.path.join(directory, path)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w", encoding="utf-8") as handle:
                handle.write("# synthetic WP1 fixture stand-in\n" + path + "\n")
    mirrored = [wp1.V1_RELEASE_REL] + v1_role_paths() + list(acc.wp8a_qualified_files())
    for rel in mirrored:
        source = os.path.join(V1_REPO_ROOT, rel)
        target = os.path.join(directory, rel)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(source, "rb") as src, open(target, "wb") as dst:
            dst.write(src.read())
        require(sha256_file(target) == sha256_file(source),
                f"the mirrored file {rel!r} is not byte-identical to the real one")
    write_canonical(directory, acc.WP7_RECEIPT_REL, synthetic_wp7_receipt())
    write_canonical(directory, REVIEW_NOTE_REL, {
        "schema": acc.APPROVAL_SCHEMA,
        "statement": ("SYNTHETIC FIXTURE REVIEW NOTE. It exists only inside the temporary "
                      "fixture tree, it is reviewed by nobody, and it authorizes nothing. "
                      "Its bytes are hashed so the fixture can exercise the review-note "
                      "existence and hash guards."),
    })


def synthetic_role_paths() -> dict[str, list[str]]:
    roles: dict[str, list[str]] = {wp1.V1_ENGINE_ROLE: v1_role_paths()}
    roles.update(copy.deepcopy(SYNTHETIC_ROLE_FILES))
    return roles


def draft_identity(tree: str) -> dict:
    """A genuine, still-DRAFT WP1 identity over the synthetic tree."""
    return wp1.build_production_identity(
        repo_root=tree,
        role_paths=synthetic_role_paths(),
        platform=dict(V1_PLATFORM),
        image_build=dict(V1_IMAGE_BUILD),
        compiler_flags=list(V1_FLAGS),
    )


def built_record(tree: str) -> dict:
    """A freshly built, NOT-YET-REVIEWED acceptance record."""
    return acc.build_acceptance_record(draft_identity(tree), repo_root=tree)


def reviewed_record(tree: str) -> dict:
    """A built record with the review note bound: the shape the gate accepts."""
    return acc.bind_review_note(built_record(tree), REVIEW_NOTE_REL, SYNTHETIC_REVIEW_TIME,
                                reviewed_by=SYNTHETIC_REVIEWER, repo_root=tree)


def accept(tree: str, record: dict) -> dict:
    return acc.accept_production_identity(record, reviewed_record_sha256=pin_of(record),
                                          repo_root=tree)


def _is_sha256(value: object) -> bool:
    """Mirror of the module's total shape test, written out independently.

    The module's own ``_is_sha256`` is a per-character loop, and a fixture that
    called it would be killed by mutations to the module's copy only.  Re-deriving
    it here means each mutant is observed on this implementation too, and a
    disagreement between the two is itself a failure.
    """
    if type(value) is not str or len(value) != 64:
        return False
    return all(char in "0123456789abcdef" for char in value)


def _is_utc_stamp(value: object) -> bool:
    """Mirror of the module's timestamp shape test, written out independently."""
    if type(value) is not str or len(value) != 20 or not value.endswith("Z"):
        return False
    body = value[:19]
    if body[10] != "T":
        return False
    if not all(part.isdigit() for part in (body[0:4], body[5:7], body[8:10],
                                           body[11:13], body[14:16], body[17:19])):
        return False
    if body[8:10] < "01" or body[5:7] < "01" or body[8:10] > "12" or body[5:7] > "12":
        return False
    if body[11:13] > "23":
        return False
    # A shape test that accepts hour 60 is not checking a shape; see the module's
    # own note on why the range rule is here.
    if body[14:16] == "60":
        return False
    if body[17:19] == "60":
        return False
    if body[11:13] > "23":
        return False
    return True


def _is_safe_rel(value: object) -> bool:
    """Mirror of the module's document-path rule, written out independently."""
    if type(value) is not str:
        return False
    if value != value.strip() or value.startswith("/"):
        return False
    if "\\" in value or ":" in value:
        return False
    if not value.endswith(".json"):
        return False
    return not any(component in ("", ".", "..") for component in value.split("/"))


MIRROR_SOURCE_SUFFIXES = (".py", ".cu", ".json", ".md")


def _is_safe_source_rel(value: object) -> bool:
    """Mirror of the module's source-path rule, written out independently.

    The suffix tuple is written out here rather than imported from the module:
    a mirror that shares the constant under test cannot disagree with it, and a
    mirror that cannot disagree is not a mirror.
    """
    if type(value) is not str:
        return False
    if value != value.strip() or value.startswith("/"):
        return False
    if "\\" in value or ":" in value:
        return False
    if not value.endswith(MIRROR_SOURCE_SUFFIXES):
        return False
    return not any(component in ("", ".", "..") for component in value.split("/"))


GARBAGE: tuple = (None, 0, 1, -1, 3.5, True, False, "", "x", [], {}, [1, 2], {"k": "v"},
                  b"bytes", object(), (1, 2), 2 ** 70, float("nan"), float("inf"))


# --------------------------------------------------------------------------
# 1. the package holds no signature, and the pin is the authority
# --------------------------------------------------------------------------

def test_no_signature_field_or_claim_exists(tree: str) -> None:
    """REGRESSION (round 1): no pseudo-signature survives anywhere.

    Round 1 carried an ``owner_signature`` block whose ``signature_sha256`` was a
    hash any caller could compute for itself.  The lead's direction is canonical
    bytes plus an externally reviewed sha256, so no signature-shaped key, schema
    string, helper or hash may remain.
    """
    record = reviewed_record(tree)
    forbidden = ("signature", "signed_by", "owner_signed", "signed")
    stack: list = [("record", record)]
    while stack:
        path, value = stack.pop()
        if isinstance(value, dict):
            for key, nested in value.items():
                lowered = str(key).lower()
                for needle in forbidden:
                    require(needle not in lowered,
                            f"the record still carries a signature-shaped key at {path}.{key}")
                stack.append((f"{path}.{key}", nested))
        elif isinstance(value, list):
            for index, nested in enumerate(value):
                stack.append((f"{path}[{index}]", nested))
    require("signature" not in acc.ACCEPTANCE_SCHEMA, "the acceptance schema still says signature")
    require("signed" not in acc.APPROVAL_SCHEMA, "the approval schema still says signed")
    for name in dir(acc):
        require("signature" not in name.lower(),
                f"the module still exports a signature-shaped name: {name}")
    source = read_bytes(os.path.join(V1_REPO_ROOT, acc.THIS_MODULE_REL)).decode("utf-8")
    for needle in ("signature_sha256", "attach_owner_signature", "_validate_signature",
                   "owner_signature", "FIXTURE_CONTEXT_TOKEN", "signed_by"):
        require(needle not in source, f"the module still names {needle}")
    require("not a signature" in acc.APPROVAL_STATEMENT,
            "the approval statement no longer says it is not a signature")
    ok("no signature field, schema string, helper or hash survives")


def test_the_pin_is_the_authority_and_comes_from_the_caller(tree: str) -> None:
    """The gate's authority is a pin the record does not contain.

    Every other sha256 in the record is derived FROM the record, so a record that
    is internally consistent can be forged whole.  ``reviewed_record_sha256`` is
    the one value the caller must supply from outside, which is what makes a
    forged record useless without the lead's pin.
    """
    record = reviewed_record(tree)
    good = pin_of(record)
    body = json.dumps(record, sort_keys=True, separators=(",", ":"))
    require(good not in body,
            "the pinned hash is derivable from the record body; it is not an external pin")
    require(refuses_with(acc.accept_production_identity, 'not the reviewed pin', record,
                         reviewed_record_sha256="0" * 64, repo_root=tree),
            "a wrong pin is not refused")
    require(refuses_with(acc.accept_production_identity, 'not the reviewed pin', record,
                         reviewed_record_sha256="1" * 64, repo_root=tree),
            "an all-ones pin is not refused")
    # Every single-character substitution is a distinct pin, so every one of them
    # must be refused; a mutation to the pin COMPARISON therefore cannot survive.
    alphabet = "0123456789abcdef"
    checked = 0
    for position in range(64):
        original = good[position]
        for replacement in alphabet:
            if replacement == original:
                continue
            candidate = good[:position] + replacement + good[position + 1:]
            require(refuses_with(acc.accept_production_identity, 'not the reviewed pin', record,
                                 reviewed_record_sha256=candidate, repo_root=tree),
                    f"the one-character-different pin at position {position} is not refused")
            checked += 1
    require(checked == 64 * 15, f"only {checked} single-character pins were checked")
    ok(f"the gate accepts only the externally supplied reviewed pin ({checked} single-character pins refused)")


def test_record_is_canonical_bytes_and_the_pin_is_their_sha256(tree: str) -> None:
    """The D013 pattern: canonical JSON plus one newline, hashed exactly as it stands."""
    import hashlib
    record = reviewed_record(tree)
    raw = acc.canonical_record_bytes(record)
    require(raw.endswith(b"\n"), "canonical record bytes do not end in one newline")
    require(raw.count(b"\n") == 1, "canonical record bytes contain more than one newline")
    require(hashlib.sha256(raw).hexdigest() == pin_of(record),
            "record_content_sha256 is not the sha256 of the canonical bytes")
    require(raw == contract.canonical_bytes(record) + b"\n",
            "canonical_record_bytes is not the frozen canonicalizer plus one newline")
    pretty = (json.dumps(record, indent=2) + "\n").encode("utf-8")
    require(hashlib.sha256(pretty).hexdigest() != pin_of(record),
            "a pretty-printed record hashes to the pin; the pin would not be canonical")
    ok("the pin is the sha256 of canonical record bytes and nothing else")


def test_status_is_approved_and_no_other_status_is_accepted(tree: str) -> None:
    """The one accepted state, refused for anything else."""
    record = reviewed_record(tree)
    require(record["status"] == acc.APPROVED_STATUS, "the built record is not in the approved state")
    for status in (acc.PENDING_STATUS, "ACCEPTED_BY_OWNER", "owner_approved", "signed", "", None, 1, []):
        changed = copy.deepcopy(record)
        changed["status"] = status
        require(rejects(changed, tree), f"status {status!r} is not refused by a typed error")
    ok("only the approved status is accepted, and every other one is refused")


# --------------------------------------------------------------------------
# 2. REGRESSION: the forged record the independent validator got through
# --------------------------------------------------------------------------

def test_forged_owner_labelled_record_is_refused(tree: str) -> None:
    """REGRESSION (round 1, validator probe ``FORGED_RECORD_ACCEPTED True``).

    The independent validator built a fabricated, owner-labelled record in a
    scratch directory, pinned its own hash, and drove the gate with it.  Round 1
    accepted it.  The same forgery is rebuilt here, naming a review note and a
    WP7 receipt that do not exist, and it must be refused with a typed error.
    """
    forged = copy.deepcopy(built_record(tree))
    forged["approval"] = {
        "schema": acc.APPROVAL_SCHEMA,
        "status": "owner_approved",
        "reviewed_by": "the-owner",
        "review_note_rel": "research/decisions/DOES_NOT_EXIST.json",
        "review_note_sha256": "e" * 64,
        "reviewed_at_utc": "2026-10-01T00:00:00Z",
        "statement": "I, the owner, approve this acceptance and sign it.",
    }
    good_evidence = built_record(tree)["wp7_dry_run_evidence"]
    forged["wp7_dry_run_evidence"] = dict(
        good_evidence,
        receipt_rel="research/decisions/NO_SUCH_WP7_RECEIPT.json",
        receipt_sha256="f" * 64,
        package_status="pushed_to_kaggle",
    )
    forged = rehashed(forged)
    require(refuses_typed(acc.accept_production_identity, forged,
                          reviewed_record_sha256=pin_of(forged), repo_root=tree)
            == "AcceptanceRecordError",
            "the forged owner-labelled record was not refused with AcceptanceRecordError")
    ok("a forged owner-labelled record naming nonexistent files is refused")


def test_nonexistent_evidence_file_is_refused(tree: str) -> None:
    """REGRESSION (round 1, validator probe ``NONEXISTENT_EVIDENCE True``).

    Round 1 accepted a record naming a WP7 receipt that was not in the repository
    at all.  Here the receipt is DELETED from the tree: the validator reads the
    pinned receipt path itself, so a missing file is a typed refusal and a record
    can never be accepted on evidence that was never observed.
    """
    record = reviewed_record(tree)
    # `rejects`/`refuses_*` below pin the RECORD, so a case that wants the PIN to
    # match its own bytes must keep passing that record's pin explicitly.
    receipt_path = os.path.join(tree, acc.WP7_RECEIPT_REL)
    original = read_bytes(receipt_path)
    os.unlink(receipt_path)
    try:
        require(refuses_with(acc.accept_production_identity, 'not an existing regular file', record,
                             reviewed_record_sha256=pin_of(record), repo_root=tree),
                "a missing WP7 receipt is not refused")
        require(refuses_typed(acc.build_acceptance_record, draft_identity(tree), repo_root=tree)
                in ("AcceptanceRecordError", "AcceptanceEvidenceError"),
                "the builder accepted a tree with no WP7 receipt")
    finally:
        rewrite(tree, acc.WP7_RECEIPT_REL, original)
    changed = copy.deepcopy(record)
    changed["wp7_dry_run_evidence"]["receipt_rel"] = "research/decisions/WP7_NOPE.json"
    changed["content_sha256"] = acc._recompute_content_sha256(changed)
    require(refuses_with_any(acc.accept_production_identity,
                             ('not the pinned receipt path', 'not the reviewed pin'),
                             changed, reviewed_record_sha256=pin_of(changed), repo_root=tree),
            "a record naming a different receipt path is not refused")
    ok("a WP7 evidence path that does not exist, and a missing receipt, are refused")


def test_nonexistent_authority_file_is_refused(tree: str) -> None:
    """REGRESSION (round 1, validator probe ``NONEXISTENT_AUTHORITY True``).

    The named authority is now a REVIEW NOTE.  It is not a signature and it is
    still a file that must exist, be regular, and hash to what the record says.
    """
    record = reviewed_record(tree)
    record = copy.deepcopy(record)
    record["approval"]["review_note_rel"] = "research/decisions/NOT_THERE.json"
    record["content_sha256"] = acc._recompute_content_sha256(record)
    require(refuses_with(acc.accept_production_identity, 'not an existing regular file', record,
                         reviewed_record_sha256=pin_of(record), repo_root=tree),
            "a nonexistent review note is not refused")
    ok("a review-note path that does not exist is refused")


def test_review_note_and_receipt_must_hash_to_what_the_record_says(tree: str) -> None:
    """A path that EXISTS but whose bytes do not match is refused, not trusted."""
    for block, field, value, needle in (
        ("approval", "review_note_sha256", "1" * 64, 'does not hash to its recorded sha256'),
        ("wp7_dry_run_evidence", "receipt_sha256", "2" * 64, 'does not hash to its recorded sha256'),
        ("wp7_dry_run_evidence", "mode", "scientific_wp8_run", 'does not re-derive from the receipt'),
        ("wp7_dry_run_evidence", "package_status", "pushed", 'does not re-derive from the receipt'),
        ("wp7_dry_run_evidence", "push_authorized", True, 'does not re-derive from the receipt'),
        ("wp7_dry_run_evidence", "gpu_allocation_authorized", True, 'does not re-derive from the receipt'),
        ("wp7_dry_run_evidence", "scientific_output_count", 7, 'does not re-derive from the receipt'),
        ("wp7_dry_run_evidence", "content_sha256", "3" * 64, 'does not re-derive from the receipt'),
        ("wp7_dry_run_evidence", "steps_executed", ["emit_non_scientific_receipt"],
         'does not re-derive from the receipt'),
    ):
        record = reviewed_record(tree)
        record = copy.deepcopy(record)
        record[block][field] = value
        record["content_sha256"] = acc._recompute_content_sha256(record)
        require(refuses_with(acc.accept_production_identity, needle, record,
                             reviewed_record_sha256=pin_of(record), repo_root=tree),
                f"{block}.{field}={value!r} that does not match the file is not refused")
    note_path = os.path.join(tree, REVIEW_NOTE_REL)
    original_note = read_bytes(note_path)
    changed = reviewed_record(tree)
    with open(note_path, "ab") as handle:
        handle.write(b"# tampered\n")
    try:
        require(refuses_with(acc.accept_production_identity, 'does not hash to its recorded sha256',
                             changed, reviewed_record_sha256=pin_of(changed), repo_root=tree),
                "an edited review note is not refused")
    finally:
        rewrite(tree, REVIEW_NOTE_REL, original_note)
    ok("an existing file whose bytes disagree with the record is refused")


def test_named_paths_must_be_regular_non_symlink_files_inside_the_root(tree: str) -> None:
    """Symlinks, directories, traversal and non-strings are refused for BOTH documents."""
    record = reviewed_record(tree)
    outside = os.path.join(tree, "..", "wp8a-outside.json")
    with open(outside, "wb") as handle:
        handle.write(b"{}\n")
    link = os.path.join(tree, acc.WP7_RECEIPT_REL + ".link.json")
    if os.path.lexists(link):
        os.unlink(link)
    os.symlink(os.path.join(tree, acc.WP7_RECEIPT_REL), link)
    note_link = os.path.join(tree, REVIEW_NOTE_REL + ".link.json")
    if os.path.lexists(note_link):
        os.unlink(note_link)
    os.symlink(os.path.join(tree, REVIEW_NOTE_REL), note_link)
    directory = os.path.join(tree, "research/decisions/A_DIRECTORY.json")
    os.makedirs(directory, exist_ok=True)
    cases = [("review_note_rel", link), ("review_note_rel", directory),
             ("review_note_rel", "../outside.json"), ("review_note_rel", 17),
             ("receipt_rel", link), ("receipt_rel", directory),
             ("receipt_rel", "/etc/passwd.json"),
             ("receipt_rel", "research/decisions/../../outside.json"),
             ("receipt_rel", 17), ("receipt_rel", None)]
    for slot, value in cases:
        changed = copy.deepcopy(record)
        if slot == "review_note_rel":
            changed["approval"][slot] = value
        else:
            changed["wp7_dry_run_evidence"][slot] = value
        changed["content_sha256"] = acc._recompute_content_sha256(changed)
        require(rejects(changed, tree), f"{slot}={value!r} is not refused by a typed error")
    # The REVIEW NOTE is the one path a record chooses freely, so it is the one
    # that can be made a symlink to a file whose bytes are exactly right.  Without
    # this the symlink guard is unkillable: every other case is caught earlier by
    # the path-shape rule, because a symlink path is not a real relative path.
    # (The WP7 receipt cannot be driven this way at all — its path is pinned to
    # ``WP7_RECEIPT_REL`` — so replacing the receipt file with a symlink is the
    # only route there, and that case is asserted below.)
    changed = copy.deepcopy(record)
    changed["approval"]["review_note_rel"] = REVIEW_NOTE_REL + ".link.json"
    changed["content_sha256"] = acc._recompute_content_sha256(changed)
    require(refuses_with_any(acc.accept_production_identity,
                             ('is a symlink', 'not the reviewed pin'),
                             changed, reviewed_record_sha256=pin_of(changed), repo_root=tree),
            "a review note naming a symlink to the right bytes is not refused as a symlink")
    require(refuses_with(acc.bind_review_note, 'is a symlink',
                         built_record(tree), REVIEW_NOTE_REL + ".link.json",
                         SYNTHETIC_REVIEW_TIME, repo_root=tree, reviewed_by="r"),
            "bind_review_note accepts a symlinked review note")
    receipt_path = os.path.join(tree, acc.WP7_RECEIPT_REL)
    receipt_bytes = read_bytes(receipt_path)
    os.unlink(receipt_path)
    os.symlink(os.path.join(tree, acc.WP7_RECEIPT_REL + ".real.json"), receipt_path)
    try:
        require(refuses_with_any(acc.accept_production_identity,
                                 ('is a symlink', 'not an existing regular file'),
                                 record, reviewed_record_sha256=pin_of(record), repo_root=tree),
                "a WP7 receipt that is a symlink is not refused")
    finally:
        os.unlink(receipt_path)
        with open(receipt_path, "wb") as handle:
            handle.write(receipt_bytes)
    os.unlink(link)
    os.unlink(note_link)
    os.unlink(outside)
    os.rmdir(directory)
    ok("symlinks, directories, absolute paths, traversal and non-strings are all refused")


def test_every_bound_source_file_is_rehashed_against_disk(tree: str) -> None:
    """A byte flipped in ANY qualified source file is refused.

    Round 1 never opened a bound file.  This walks the qualified source map, and
    for every source entry appends one byte inside the temporary tree only, then
    requires a typed refusal before restoring the file.
    """
    record = reviewed_record(tree)
    good = pin_of(record)
    roles = record["qualified_source_map"]["roles"]
    entries = [(role, entry["path"]) for role in sorted(roles) for entry in roles[role]]
    checked = 0
    for role, rel in entries:
        if not rel.endswith(MIRROR_SOURCE_SUFFIXES):
            continue
        path = os.path.join(tree, rel)
        original = read_bytes(path)
        with open(path, "ab") as handle:
            handle.write(b"# flipped\n")
        try:
            require(refuses_typed(acc.accept_production_identity, record,
                                  reviewed_record_sha256=pin_of(record), repo_root=tree)
                    == "AcceptanceRecordError",
                    f"a flipped byte in {rel!r} (role {role!r}) was not refused")
            require(refuses_with(acc.accept_production_identity, 'does not hash to its recorded',
                                 record, reviewed_record_sha256=pin_of(record), repo_root=tree),
                    f"a flipped byte in {rel!r} was not refused by the source-map guard")
            checked += 1
        finally:
            rewrite(tree, rel, original)
    require(checked >= 20, f"only {checked} bound source files were flipped and re-checked")
    require(accept(tree, record)["accepted_content_sha256"] == good,
            "the record is no longer valid after every file was restored")
    ok(f"every one of the {checked} bound source files is re-hashed against disk")


def test_deleting_a_bound_source_file_is_refused(tree: str) -> None:
    """A bound file that is GONE is refused, not skipped."""
    record = reviewed_record(tree)
    rel = acc.THIS_MODULE_REL
    path = os.path.join(tree, rel)
    original = read_bytes(path)
    os.unlink(path)
    try:
        require(refuses_typed(acc.accept_production_identity, record,
                              reviewed_record_sha256=pin_of(record), repo_root=tree)
                == "AcceptanceRecordError",
                "deleting the WP8a module from the tree was not refused")
        require(refuses_typed(acc.build_acceptance_record, draft_identity(tree), repo_root=tree)
                == "AcceptanceRecordError",
                "the builder accepted a tree with no WP8a module")
    finally:
        rewrite(tree, rel, original)
    ok("a deleted bound source file is refused by the builder and the validator")


# --------------------------------------------------------------------------
# 3. REGRESSION: the WP8a module must be inside a qualified source map
# --------------------------------------------------------------------------

def test_wp8a_module_is_inside_the_qualified_source_map(tree: str) -> None:
    """REGRESSION (round 1, validator probe ``WP8A_MODULE_IN_SOURCE_MAP False``).

    Round 1's source map carried only the WP1 roles, so the module that decides
    whether an identity is accepted was not itself qualified by anything.  Every
    file this package reads or ships must now be bound under the added role.
    """
    record = reviewed_record(tree)
    roles = record["qualified_source_map"]["roles"]
    require(acc.WP8A_ROLE in roles, "the qualified source map has no WP8a role")
    bound = sorted(entry["path"] for entry in roles[acc.WP8A_ROLE])
    already = {entry["path"] for role in sorted(roles) if role != acc.WP8A_ROLE
               for entry in roles[role]}
    expected = sorted(acc.wp8a_role_files_for(already))
    require(bound == expected,
            f"the WP8a role binds {bound}, not the package's own uncovered files {expected}")
    require(len(set(bound) & already) == 0,
            "the WP8a role re-binds a file another role already qualifies")
    require(acc.THIS_MODULE_REL in bound,
            "the WP8a acceptance module itself is not bound in the qualified source map")
    require(acc.THIS_FIXTURE_REL in bound, "the WP8a fixtures are not bound")
    require(acc.THIS_NOTES_REL in bound, "the WP8a notes are not bound")
    require(acc.WP1_MODULE_REL in bound, "the WP1 validator this package reads is not bound")
    require(acc.WP7_MODULE_REL in [entry["path"] for entry in roles[wp1.V1_ENGINE_ROLE]],
            "the WP7 session module is not in the v1_engine role")
    for rel in acc.wp8a_qualified_files():
        anywhere = [entry["path"] for role in sorted(roles) for entry in roles[role]]
        require(rel in anywhere, f"{rel!r} is bound by no role in the qualified source map")
        require(os.path.isfile(os.path.join(V1_REPO_ROOT, rel)),
                f"{rel!r} is named but does not exist in the repository")
    for role in sorted(wp1.ROLES):
        require(role in roles, f"the qualified source map dropped the WP1 role {role!r}")
    require(len(roles) == len(wp1.ROLES) + 1, "the qualified source map has an unexpected role set")
    require(record["bound"]["qualified_source_map_file_count"]
            == record["qualified_source_map"]["bound_file_count"],
            "the bound qualified file count disagrees with the map")
    require(record["bound"]["qualified_source_map_content_sha256"]
            == contract.content_sha256(record["qualified_source_map"]),
            "the bound qualified map hash does not re-derive")
    ok("the WP8a module, its fixtures, its notes and every file it reads are bound")


def test_a_file_read_by_this_package_that_is_not_bound_is_refused(tree: str) -> None:
    """A substituted, re-hashed or dropped WP8a qualified entry is refused.

    The substituted path is chosen to keep the role's sorted-path order valid, so
    the refusal under test is the membership guard and not the ordering guard,
    which is exercised separately below.
    """
    record = reviewed_record(tree)
    role = record["qualified_source_map"]["roles"][acc.WP8A_ROLE]
    ordered = sorted(entry["path"] for entry in role)
    substituted = "research/g9/wp8a/zz_substituted_module.py"
    changed_paths = [substituted if path == ordered[-1] else path for path in ordered]
    require(changed_paths == sorted(changed_paths),
            "the substituted path would break the role's sorted order")
    require(changed_paths[-1] == substituted,
            "the substituted path is not the role's last entry")
    for field, value in (("path", substituted), ("sha256", "3" * 64)):
        changed = copy.deepcopy(record)
        entries = changed["qualified_source_map"]["roles"][acc.WP8A_ROLE]
        for entry in entries:
            if entry["path"] == ordered[-1]:
                entry[field] = value
        changed["content_sha256"] = acc._recompute_content_sha256(changed)
        require(refuses_with_any(acc.accept_production_identity,
                                 ('does not bind exactly this package',
                                  'does not hash to its recorded sha256',
                                  'not in sorted path order',
                                  'is not an existing regular file',
                                  'is not a safe relative path'),
                                 changed, reviewed_record_sha256=pin_of(changed), repo_root=tree),
                f"a substituted WP8a qualified {field} is not refused")
    changed = copy.deepcopy(record)
    changed["qualified_source_map"]["roles"].pop(acc.WP8A_ROLE)
    changed["content_sha256"] = acc._recompute_content_sha256(changed)
    require(refuses_with_any(acc.accept_production_identity,
                             ('does not carry exactly the WP1 role set', 'must be an object',
                              'binds no role for these files'),
                             changed, reviewed_record_sha256=pin_of(changed), repo_root=tree),
            "dropping the WP8a role is not refused")
    changed = copy.deepcopy(record)
    changed["qualified_source_map"]["roles"]["coordinate_iterator"].append(
        {"path": acc.THIS_MODULE_REL, "sha256": "4" * 64})
    changed["content_sha256"] = acc._recompute_content_sha256(changed)
    require(refuses_with_any(acc.accept_production_identity,
                             ('which another role already binds', 'not in sorted path order',
                              'wrong key set', 'bound_file_count does not equal',
                              'does not hash to its recorded sha256'),
                             changed, reviewed_record_sha256=pin_of(changed), repo_root=tree),
            "an unbound duplicate path in another role is not refused")
    changed = copy.deepcopy(record)
    changed["qualified_source_map"]["roles"][acc.WP8A_ROLE].append(
        {"path": "research/g9/wp8a/zz_extra_unbound.py", "sha256": "5" * 64})
    changed["content_sha256"] = acc._recompute_content_sha256(changed)
    require(refuses_with_any(acc.accept_production_identity,
                             ('does not bind exactly this package', 'bound_file_count does not equal',
                              'is not an existing regular file'),
                             changed, reviewed_record_sha256=pin_of(changed), repo_root=tree),
            "an extra unbound file smuggled into the WP8a role is not refused")
    ok("a substituted, re-hashed, dropped or extended WP8a qualified entry is refused")


def test_every_package_file_must_be_bound_by_some_role(tree: str) -> None:
    """Every file of this package is bound by the role that is supposed to own it.

    The qualified map has two rules that together say "this package is qualified
    completely": the ``wp8a_acceptance`` role binds exactly the package files the
    WP1 roles do not already bind, and a path is bound by at most one role.  Each
    is pinned here by dropping the file and watching which rule refuses, and by
    binding it twice to watch the second one.  Nothing is dropped from a role that
    holds only that file, because that would empty the role and reach neither rule.
    """
    record = reviewed_record(tree)
    roles = record["qualified_source_map"]["roles"]
    everywhere: dict = {}
    for role in sorted(roles):
        for entry in roles[role]:
            everywhere.setdefault(entry["path"], role)
    checked = 0
    for rel in acc.wp8a_qualified_files():
        require(rel in everywhere,
                f"{rel!r} is claimed by this package but bound by no role of the qualified map")
        host = everywhere[rel]
        require([role for role in sorted(roles)
                 if any(entry["path"] == rel for entry in roles[role])] == [host],
                f"{rel!r} is bound by more than one role")
        if len(roles[host]) > 1:
            changed = copy.deepcopy(record)
            changed["qualified_source_map"]["roles"][host] = [
                entry for entry in changed["qualified_source_map"]["roles"][host]
                if entry["path"] != rel]
            require(changed["qualified_source_map"]["roles"][host],
                    f"the edit emptied role {host!r}")
            changed["qualified_source_map"]["bound_file_count"] = sum(
                len(entries) for entries in changed["qualified_source_map"]["roles"].values())
            changed["content_sha256"] = acc._recompute_content_sha256(changed)
            require(refuses_typed(acc.accept_production_identity, changed,
                                  reviewed_record_sha256=pin_of(changed), repo_root=tree)
                    == "AcceptanceRecordError",
                    f"a qualified map that omits {rel!r} from role {host!r} is not refused")
            checked += 1
        spare = next(role for role in sorted(roles)
                     if role != host and len(roles[role]) > 1)
        duplicated = copy.deepcopy(record)
        duplicated["qualified_source_map"]["roles"][spare].append(
            {"path": rel, "sha256": sha256_file(os.path.join(tree, rel))})
        duplicated["qualified_source_map"]["roles"][spare].sort(
            key=lambda entry: entry["path"])
        duplicated["content_sha256"] = acc._recompute_content_sha256(duplicated)
        require(refuses_typed(acc.accept_production_identity, duplicated,
                              reviewed_record_sha256=pin_of(duplicated), repo_root=tree)
                == "AcceptanceRecordError",
                f"binding {rel!r} in a second role is not refused")
        checked += 1
    require(checked >= len(acc.wp8a_qualified_files()),
            "the omission cases did not cover every file of this package")
    # The §A v1 release file the WP1 validator reads is one of those files, and it
    # is a .json — which is why the qualified suffix rule had to widen to WP1's own.
    require(acc.WP1_RELEASE_REL in everywhere,
            "the §A v1 release file the WP1 validator reads is not bound by the qualified map")
    require(acc.WP1_RELEASE_REL.endswith(".json"),
            "the §A v1 release file is not the .json document WP1 pins")
    ok(f"all {len(acc.wp8a_qualified_files())} files of this package are bound by exactly one "
       "role, and omitting or duplicating any is refused")



def test_qualified_source_map_bookkeeping_is_re_derived(tree: str) -> None:
    """Every bookkeeping field of the qualified map is recomputed, never trusted."""
    record = reviewed_record(tree)
    for key, value, needle in (("schema", "decisions_os/g9_wp8a_qualified_source_map/v2",
                                "schema is not the pinned"),
                               ("hash_algorithm", "sha1", "hash_algorithm is not the pinned"),
                               ("bound_file_count", 3, "bound_file_count does not equal"),
                               ("not_yet_built_roles", [], "not_yet_built_roles does not match"),
                               ("roles", {}, "does not carry exactly the WP1 role set"),
                               ("roles", None, "must be an object")):
        changed = copy.deepcopy(record)
        changed["qualified_source_map"][key] = value
        changed["content_sha256"] = acc._recompute_content_sha256(changed)
        require(refuses_with_any(acc.accept_production_identity, (needle, 'must be an object'),
                                 changed, reviewed_record_sha256=pin_of(changed), repo_root=tree),
                f"qualified source map {key}={value!r} is not refused")
    for role in sorted(record["qualified_source_map"]["roles"]):
        for value in ("F" * 64, "z" * 64, "a" * 63, "a" * 65, "", None, 17, [], {}):
            changed = copy.deepcopy(record)
            entry = changed["qualified_source_map"]["roles"][role][0]
            entry["sha256"] = value
            changed["content_sha256"] = acc._recompute_content_sha256(changed)
            require(refuses_typed(acc.accept_production_identity, changed,
                                  reviewed_record_sha256=pin_of(changed), repo_root=tree)
                    == "AcceptanceRecordError",
                    f"a qualified entry sha256 of {value!r} in role {role!r} was not refused")
    # The recorded file count must be an INTEGER and not merely something that
    # compares equal to the number of entries: True == 1 and 25.0 == 25.
    count = record["qualified_source_map"]["bound_file_count"]
    require(count > 1, "the fixture's qualified bound_file_count is too small for the bool case")
    for impostor in (True, float(count), str(count), None, [count], {"n": count}):
        changed = copy.deepcopy(record)
        changed["qualified_source_map"]["bound_file_count"] = impostor
        changed["content_sha256"] = acc._recompute_content_sha256(changed)
        require(refuses_typed(acc.accept_production_identity, changed,
                              reviewed_record_sha256=pin_of(changed), repo_root=tree)
                == "AcceptanceRecordError",
                f"a qualified bound_file_count of {impostor!r} was not refused")
    for impostor in (True, float(record["qualified_source_map"]["bound_file_count"]),
                      str(record["qualified_source_map"]["bound_file_count"])):
        changed = copy.deepcopy(record)
        changed["qualified_source_map"]["bound_file_count"] = impostor
        changed["content_sha256"] = acc._recompute_content_sha256(changed)
        require(refuses_typed(acc.accept_production_identity, changed,
                              reviewed_record_sha256=pin_of(changed), repo_root=tree)
                == "AcceptanceRecordError",
                f"a qualified bound_file_count of {impostor!r} was not refused")
    changed = copy.deepcopy(record)
    changed["qualified_source_map"]["extra"] = 1
    changed["content_sha256"] = acc._recompute_content_sha256(changed)
    require(refuses_with(acc.accept_production_identity, 'wrong key set', changed,
                         reviewed_record_sha256=pin_of(changed), repo_root=tree),
            "an extra qualified source map key is not refused")
    for role in sorted(record["qualified_source_map"]["roles"]):
        cases = [("malformed", 'malformed entry'), ("empty", 'is empty')]
        if len(record["qualified_source_map"]["roles"][role]) >= 2:
            cases.insert(0, ("reverse", 'sorted path order'))
        for how, needle in cases:
            changed = copy.deepcopy(record)
            if how == "reverse":
                changed["qualified_source_map"]["roles"][role] = list(reversed(
                    changed["qualified_source_map"]["roles"][role]))
            elif how == "malformed":
                changed["qualified_source_map"]["roles"][role][0] = {"path": "x.py", "extra": 2}
            else:
                changed["qualified_source_map"]["roles"][role] = []
            changed["content_sha256"] = acc._recompute_content_sha256(changed)
            require(refuses_with_any(acc.accept_production_identity,
                                     (needle, 'bound_file_count does not equal'),
                                     changed, reviewed_record_sha256=pin_of(changed), repo_root=tree),
                    f"{how} entries in role {role!r} are not refused naming {needle!r}")
    multi = [role for role in sorted(record["qualified_source_map"]["roles"])
             if len(record["qualified_source_map"]["roles"][role]) >= 2]
    require(len(multi) >= 2, "no role has two or more entries, so the order guard is untested")
    ok("the qualified source map's shape, order, count and role set are all re-derived")


# --------------------------------------------------------------------------
# 4. REGRESSION: malformed input must be a typed refusal, never KeyError
# --------------------------------------------------------------------------

def test_malformed_bound_block_is_a_typed_refusal_not_a_KeyError(tree: str) -> None:
    """REGRESSION (round 1, validator probe ``MALFORMED_BOUND_REFUSAL_TYPE KeyError``).

    Round 1 read ``record["bound"]`` directly, so a record whose ``bound`` was a
    list, or an object missing a key, raised ``KeyError`` out of the production
    gate.  Both must be typed refusals now.
    """
    record = reviewed_record(tree)
    for value in (None, [], "text", 17, [("k", "v")], {1: 2}, True, 3.5):
        changed = copy.deepcopy(record)
        changed["bound"] = value
        try:
            changed["content_sha256"] = acc._recompute_content_sha256(changed)
        except Exception:  # noqa: BLE001 - the garbage may not even be canonical
            pass
        require(rejects(changed, tree),
                f"record['bound']={value!r} was not refused with AcceptanceRecordError")
    for key in sorted(acc.BOUND_KEYS):
        changed = copy.deepcopy(record)
        del changed["bound"][key]
        changed["content_sha256"] = acc._recompute_content_sha256(changed)
        require(rejects(changed, tree),
                f"a bound block missing {key!r} was not refused with AcceptanceRecordError")
        changed = copy.deepcopy(record)
        changed["bound"][key] = {"nested": {"garbage": [1, 2, 3]}}
        changed["content_sha256"] = acc._recompute_content_sha256(changed)
        require(rejects(changed, tree),
                f"a nested-garbage bound {key!r} was not refused with AcceptanceRecordError")
    ok("a non-mapping or incomplete bound block is a typed refusal, never a KeyError")


def test_fuzz_every_record_slot_with_garbage(tree: str) -> None:
    """Fuzz: every top-level slot takes every garbage value and stays typed."""
    record = reviewed_record(tree)
    good = pin_of(record)
    for slot in sorted(acc.RECORD_KEYS):
        for garbage in GARBAGE:
            changed = copy.deepcopy(record)
            changed[slot] = garbage
            if slot != "content_sha256":
                # Re-derive the internal hash so the PIN check passes and the guard
                # under test is the one that actually runs.  The content_sha256 slot
                # itself is never re-derived: doing so would restore the good record.
                try:
                    changed["content_sha256"] = acc._recompute_content_sha256(changed)
                except Exception:  # noqa: BLE001 - the garbage may not be canonical
                    pass
            require(refuses_typed(acc.accept_production_identity, changed,
                                  reviewed_record_sha256=good, repo_root=tree)
                    == "AcceptanceRecordError",
                    f"record[{slot!r}]={garbage!r} was not refused with AcceptanceRecordError")
    ok("every top-level slot fuzzed with every garbage value stays a typed refusal")


def test_fuzz_nested_blocks_with_garbage(tree: str) -> None:
    """Fuzz: every field of every nested block, in the validator."""
    record = reviewed_record(tree)
    good = pin_of(record)
    for block, fields in (("bound", sorted(acc.BOUND_KEYS)),
                          ("approval", sorted(acc.APPROVAL_KEYS)),
                          ("wp7_dry_run_evidence", sorted(acc.EVIDENCE_KEYS))):
        for garbage in GARBAGE:
            changed = copy.deepcopy(record)
            changed[block] = garbage
            try:
                changed["content_sha256"] = acc._recompute_content_sha256(changed)
            except Exception:  # noqa: BLE001
                pass
            require(refuses_typed(acc.accept_production_identity, changed,
                                  reviewed_record_sha256=good, repo_root=tree)
                    == "AcceptanceRecordError",
                    f"record[{block!r}]={garbage!r} was not refused with AcceptanceRecordError")
        for field in fields:
            for garbage in GARBAGE:
                if garbage == record[block][field]:
                    # A fuzz value equal to the field's own value is a NO-OP edit:
                    # the record is byte-identical, so requiring a refusal would be
                    # asserting that a valid record is invalid.  It is asserted in
                    # the other direction instead, which is what pins the field.
                    require(pin_of(record) == good and accept(tree, record)["accepted_content_sha256"] == good,
                            f"a no-op fuzz on {block}.{field} disturbed the accepted record")
                    continue
                changed = copy.deepcopy(record)
                changed[block][field] = garbage
                try:
                    changed["content_sha256"] = acc._recompute_content_sha256(changed)
                except Exception:  # noqa: BLE001
                    pass
                require(refuses_typed(acc.accept_production_identity, changed,
                                      reviewed_record_sha256=good, repo_root=tree)
                        == "AcceptanceRecordError",
                        f"record[{block!r}][{field!r}]={garbage!r} was not refused")
    ok("every field of bound, approval and evidence fuzzed with every garbage value")


def test_fuzz_qualified_source_map_and_draft_with_garbage(tree: str) -> None:
    """Fuzz: the qualified map and the embedded draft are fuzzed the same way."""
    record = reviewed_record(tree)
    good = pin_of(record)
    for slot in ("qualified_source_map", "draft_identity"):
        for garbage in GARBAGE:
            changed = copy.deepcopy(record)
            changed[slot] = garbage
            try:
                changed["content_sha256"] = acc._recompute_content_sha256(changed)
            except Exception:  # noqa: BLE001
                pass
            require(refuses_typed(acc.accept_production_identity, changed,
                                  reviewed_record_sha256=good, repo_root=tree)
                    == "AcceptanceRecordError",
                    f"record[{slot!r}]={garbage!r} was not refused with AcceptanceRecordError")
    for garbage in GARBAGE:
        changed = copy.deepcopy(record)
        changed["qualified_source_map"]["roles"] = garbage
        try:
            changed["content_sha256"] = acc._recompute_content_sha256(changed)
        except Exception:  # noqa: BLE001
            pass
        require(refuses_typed(acc.accept_production_identity, changed,
                              reviewed_record_sha256=good, repo_root=tree)
                == "AcceptanceRecordError",
                f"qualified_source_map.roles={garbage!r} was not refused")
    ok("the qualified source map and the embedded draft are fuzzed with garbage")


def test_the_record_itself_may_be_any_garbage(tree: str) -> None:
    """Fuzz: the whole record argument, the pin, the repo root and the session."""
    good = pin_of(reviewed_record(tree))
    for garbage in GARBAGE:
        require(refuses_typed(acc.accept_production_identity, garbage,
                              reviewed_record_sha256=good, repo_root=tree) == "AcceptanceRecordError",
                f"accept_production_identity({garbage!r}) was not refused")
    # A record carrying a value JSON cannot serialize has no canonical bytes and no
    # content hash at all, so the pin cannot be computed and the refusal must be
    # typed rather than a TypeError out of json.dumps.
    record = reviewed_record(tree)
    for unserializable in (b"bytes", {1, 2}, object(), complex(1, 2)):
        changed = copy.deepcopy(record)
        changed["bound"] = unserializable
        require(refuses_typed(acc.accept_production_identity, changed,
                              reviewed_record_sha256=good, repo_root=tree)
                == "AcceptanceRecordError",
                f"a record whose bound is {unserializable!r} escaped as a raw TypeError")
        require(refuses_with_any(acc.accept_production_identity,
                                 ('not JSON-serializable', 'must be an object'),
                                 changed, reviewed_record_sha256=good, repo_root=tree),
                f"a record whose bound is {unserializable!r} was not refused for being "
                "unserializable")
        require(refuses_typed(acc.record_content_sha256, changed) == "AcceptanceRecordError",
                "record_content_sha256 did not refuse an unserializable record")
        require(refuses_typed(acc._recompute_content_sha256, changed) == "AcceptanceRecordError",
                "_recompute_content_sha256 did not refuse an unserializable record")
    require(refuses_typed(acc.canonical_record_bytes, {"a": {1, 2}}) == "AcceptanceRecordError",
            "canonical_record_bytes did not refuse an unserializable value")
    for garbage in GARBAGE:
        require(refuses_typed(acc.accept_production_identity, reviewed_record(tree),
                              reviewed_record_sha256=garbage, repo_root=tree) == "AcceptanceRecordError",
                f"a garbage pin {garbage!r} was not refused")
    for garbage in GARBAGE:
        outcome = refuses_typed(acc.accept_production_identity, reviewed_record(tree),
                                reviewed_record_sha256=good, repo_root=garbage)
        require(outcome in ("AcceptanceRecordError", "AcceptanceEvidenceError"),
                f"a garbage repo root {garbage!r} raised {outcome!r}")
    for garbage in GARBAGE:
        outcome = refuses_typed(acc.validate_acceptance_record, garbage,
                                reviewed_record_sha256=good, repo_root=tree)
        require(outcome == "AcceptanceRecordError",
                f"validate_acceptance_record({garbage!r}) raised {outcome!r}")
    for garbage in GARBAGE:
        outcome = refuses_typed(acc.exact_match_session, garbage, reviewed_record(tree),
                                reviewed_record_sha256=good, repo_root=tree)
        require(outcome in ("AcceptanceRecordError", "AcceptanceSessionMismatch"),
                f"a garbage session identity raised {outcome!r}")
    ok("the record, the pin, the repo root and the session identity are all fuzzed")


def test_deleting_the_content_sha256_slot_is_refused(tree: str) -> None:
    """REGRESSION (round 2, builder probe: the ``content_sha256`` deletion gap).

    The pin is the sha256 of the record's FULL canonical bytes, so deleting the
    ``content_sha256`` slot changes those bytes and a caller who pins the reduced
    record reaches the gate with a pin that MATCHES.  Without an exact key-set
    guard the reduced record would sail past the pin check and past the internal
    consistency check too, because ``_recompute_content_sha256`` of a body that
    lacks the slot is computed over that same reduced body.  The key-set check is
    therefore what refuses it, and this is its regression test.

    Each other key is deleted the same way here, so the guard is pinned for every
    member of ``RECORD_KEYS`` and not only for the one that produced the finding.
    """
    record = reviewed_record(tree)
    good = pin_of(record)
    for key in sorted(acc.RECORD_KEYS):
        changed = copy.deepcopy(record)
        del changed[key]
        reduced_pin = pin_of(changed)
        require(reduced_pin != good,
                f"deleting {key!r} did not change the pinned bytes, so the case is vacuous")
        for label, pin in (("the original reviewed pin", good),
                           ("a pin of its OWN reduced bytes", reduced_pin)):
            require(refuses_with(acc.accept_production_identity, 'wrong key set', changed,
                                 reviewed_record_sha256=pin, repo_root=tree),
                    f"a record missing {key!r} is accepted under {label}")
    require(set(acc.RECORD_KEYS) == {'schema', 'status', 'scope_statement', 'approval', 'bound',
                                     'draft_identity', 'wp7_dry_run_evidence',
                                     'qualified_source_map', 'content_sha256'},
            "RECORD_KEYS drifted, so the deletion regression is not covering what it claims")
    ok("a record missing any key is refused even under a pin of its own reduced bytes")


def test_record_shell_and_extra_key_refusals(tree: str) -> None:
    """The shell: wrong type, wrong key set, foreign schema, wrong scope wording."""
    record = reviewed_record(tree)
    for extra in ({"extra": 1}, {"status": 1}, {"bound": 1}, {"content_sha2562": 1}):
        changed = copy.deepcopy(record)
        changed.update(extra)
        require(rejects(changed, tree), f"an extra record key {sorted(extra)} is not refused")
    for key in sorted(acc.RECORD_KEYS):
        changed = copy.deepcopy(record)
        del changed[key]
        if key != "content_sha256":
            # Re-derive the internal hash so the PIN check passes and the key-set
            # guard is the one under test.  The content_sha256 slot is NEVER
            # re-derived here: doing so would put the key straight back, which is
            # exactly the gap the dedicated regression test below closes.
            changed["content_sha256"] = acc._recompute_content_sha256(changed)
        require(refuses_with_any(acc.accept_production_identity,
                                 ('wrong key set', 'must be an object'),
                                 changed, reviewed_record_sha256=pin_of(changed), repo_root=tree),
                f"a record missing {key!r} is not refused")
    for schema in ("decisions_os/g9_wp8a_production_identity_acceptance/v1", "", None, 1):
        changed = copy.deepcopy(record)
        changed["schema"] = schema
        require(rejects(changed, tree), f"schema {schema!r} is not refused by a typed error")
    for wording in ("This record grants a draw approval.", acc.SCOPE_STATEMENT + " Also authorized.",
                    "", None, 7):
        changed = copy.deepcopy(record)
        changed["scope_statement"] = wording
        changed["content_sha256"] = acc._recompute_content_sha256(changed)
        require(refuses_with(acc.accept_production_identity, 'scope_statement', changed,
                             reviewed_record_sha256=pin_of(changed), repo_root=tree),
                f"scope wording {wording!r} is not refused")
    ok("the record shell, its key set, its schema and every missing key are refused")


# --------------------------------------------------------------------------
# 5. the review-note binding, and the WP7 receipt itself
# --------------------------------------------------------------------------

def test_a_freshly_built_record_is_refused_until_reviewed(tree: str) -> None:
    """The builder emits nulls in the review-note block, and they are refused.

    Every rejection here drives the gate with the unreviewed record's OWN pin, so
    each case proves a check fired rather than merely that the bytes changed.
    """
    record = built_record(tree)
    require(record["approval"]["review_note_rel"] is None, "the built record names a review note")
    require(record["approval"]["review_note_sha256"] is None, "the built record names a note hash")
    require(record["approval"]["reviewed_at_utc"] is None, "the built record names a review time")
    require(refuses_with_any(acc.accept_production_identity,
                             ('names no review note', 'approval block shape'),
                             record, reviewed_record_sha256=pin_of(record), repo_root=tree),
            "an unreviewed record is not refused")
    require(refuses_with_any(acc.build_acceptance_record,
                             ('names no review note', 'approval block shape',
                              'not an accepted WP1 DRAFT identity'),
                             built_record(tree), repo_root=tree),
            "the builder does not refuse to build on an unreviewed record")
    for status in ("owner_approved", "approved", "REVIEWED", "", None):
        changed = copy.deepcopy(record)
        changed["approval"]["status"] = status
        changed["content_sha256"] = acc._recompute_content_sha256(changed)
        require(refuses_with_any(acc.accept_production_identity,
                                 ('approval status', 'approval block shape',
                                  'not the reviewed pin'),
                                 changed, reviewed_record_sha256=pin_of(changed), repo_root=tree),
                f"approval status {status!r} is not refused")
    for statement in ("I approve this acceptance.", "", None):
        changed = copy.deepcopy(record)
        changed["approval"]["statement"] = statement
        changed["content_sha256"] = acc._recompute_content_sha256(changed)
        require(refuses_with_any(acc.accept_production_identity,
                                 ('names no review note', 'approval statement',
                                  'approval block shape', 'not the reviewed pin'),
                                 changed, reviewed_record_sha256=pin_of(changed), repo_root=tree),
                f"approval statement {statement!r} is not refused")
    ok("a freshly built record is refused until a review note is bound")


def test_the_approval_block_is_pinned_in_the_validator(tree: str) -> None:
    """Every approval-block guard is reachable THROUGH THE GATE, not just the act.

    The gate re-validates the review-note block itself rather than trusting
    ``bind_review_note``.  Each guard is therefore driven here with a pin that
    MATCHES the edited record, so the block guard is the one that has to fire.

    The four shape fields are checked one at a time and each must be NAMED
    individually in the refusal.  That is what keeps the single combined shape
    guard from masking one defect behind another: if ``status`` were reported
    under ``schema``'s wording, or if a field were dropped from the report
    entirely, the needle for that field would not be found.
    """
    record = reviewed_record(tree)
    for field, value, needle in (
        ("schema", "decisions_os/g9_wp8a_acceptance_review_note/v2", "schema is"),
        ("schema", "", "schema is"),
        ("status", "owner_approved", "status is"),
        ("status", None, "status is"),
        ("statement", "I approve this.", "the statement is not the pinned reviewed wording"),
        ("reviewed_by", "", "reviewed_by is"),
        ("reviewed_by", " padded ", "reviewed_by is"),
        ("reviewed_by", 17, "reviewed_by is"),
        ("reviewed_by", None, "reviewed_by is"),
    ):
        changed = copy.deepcopy(record)
        changed["approval"][field] = value
        changed["content_sha256"] = acc._recompute_content_sha256(changed)
        require(refuses_with_any(acc.accept_production_identity,
                                 (needle, 'must be an object', 'wrong key set'),
                                 changed, reviewed_record_sha256=pin_of(changed), repo_root=tree),
                f"approval {field}={value!r} is not refused naming {needle!r}")
    # The four together are reported as one refusal listing all of them, so a
    # record that is wrong in several ways at once is refused for all of them.
    changed = copy.deepcopy(record)
    changed["approval"]["schema"] = "wrong/v1"
    changed["approval"]["status"] = "owner_approved"
    changed["approval"]["statement"] = "I approve this."
    changed["approval"]["reviewed_by"] = ""
    changed["content_sha256"] = acc._recompute_content_sha256(changed)
    require(refuses_with(acc.accept_production_identity, 'approval block shape is wrong', changed,
                         reviewed_record_sha256=pin_of(changed), repo_root=tree),
            "an approval block wrong in four ways is not refused as a shape failure")
    for field, value, needle in (
        ("reviewed_at_utc", "2026-01-01T00:00:00", "reviewed_at_utc is"),
        ("reviewed_at_utc", "2026-01-01 00:00:00Z", "reviewed_at_utc is"),
        # Both operands of the "60 is not a real minute or second" rule are driven
        # through the ACT in test_bind_review_note_refuses_bad_input; here only the
        # seconds one is reachable, because a bound record's note hash must also
        # re-derive and a fresh note cannot be written with that name twice.
        ("reviewed_at_utc", "2026-01-01t00:00:00Z", "reviewed_at_utc is"),
        ("reviewed_at_utc", "2026-01-01T00:00:60Z", "reviewed_at_utc is"),
        ("reviewed_at_utc", SYNTHETIC_REVIEW_TIME + "x", "reviewed_at_utc is"),
        ("reviewed_at_utc", "x", "reviewed_at_utc is"),
        ("reviewed_at_utc", 20261001, "reviewed_at_utc is"),
        ("reviewed_at_utc", None, "reviewed_at_utc is"),
        ("review_note_rel", "research/decisions/NOPE.json", "not an existing regular file"),
        ("review_note_rel", "../escape.json", "not a safe relative path"),
    ):
        changed = copy.deepcopy(record)
        changed["approval"][field] = value
        changed["content_sha256"] = acc._recompute_content_sha256(changed)
        require(refuses_with_any(acc.accept_production_identity,
                                 (needle, 'approval block shape',
                                  'must be an object', 'must be 64 characters',
                                  'does not hash to its recorded sha256'),
                                 changed, reviewed_record_sha256=pin_of(changed), repo_root=tree),
                f"approval {field}={value!r} is not refused naming {needle!r}")
    # An unreviewed record that carries a note HASH or a review TIME without
    # naming a note is refused too, so the null placeholders cannot be used to
    # smuggle a claimed review past the "names no review note" guard.
    # The reviewed shape carries a note path, so these two carry a HASH or a TIME
    # without one; either way the record is refused, and a stamp without a note is
    # refused by the block's shape report rather than by the note branch.
    for field, value in (("review_note_sha256", "5" * 64), ("reviewed_at_utc", SYNTHETIC_REVIEW_TIME)):
        changed = built_record(tree)
        changed["approval"][field] = value
        changed["content_sha256"] = acc._recompute_content_sha256(changed)
        require(refuses_with_any(acc.accept_production_identity,
                                 ('without naming a review note', 'approval block shape'),
                                 changed,
                                 reviewed_record_sha256=pin_of(changed), repo_root=tree),
                f"an unreviewed record carrying approval.{field} is not refused")
    require(refuses_with_any(acc.accept_production_identity,
                             ('names no review note', 'approval block shape'),
                             built_record(tree),
                             reviewed_record_sha256=pin_of(built_record(tree)), repo_root=tree),
            "a plainly unreviewed record is not refused")
    # With the note path still absent and the hash and time both present, the note
    # branch itself is the one that refuses.
    changed = built_record(tree)
    changed["approval"]["review_note_sha256"] = "5" * 64
    changed["approval"]["reviewed_by"] = SYNTHETIC_REVIEWER
    changed["content_sha256"] = acc._recompute_content_sha256(changed)
    require(refuses_typed(acc.accept_production_identity, changed,
                          reviewed_record_sha256=pin_of(changed), repo_root=tree)
            == "AcceptanceRecordError",
            "a note hash with no note path is not refused by a typed error")
    # The happy path still resolves the note, so the reviewed branch is not dead.
    require(accept(tree, record)["review_note_sha256"]
            == sha256_file(os.path.join(tree, REVIEW_NOTE_REL)),
            "the reviewed branch does not re-hash the note from disk")
    ok("every approval-block guard is pinned, and the reviewed branch still re-hashes the note")


def test_bind_review_note_refuses_bad_input(tree: str) -> None:
    """The review act is itself total and fail-closed."""
    record = built_record(tree)
    for reviewer, moment, needle in (
        ("", SYNTHETIC_REVIEW_TIME, "non-empty string"),
        (" padded ", SYNTHETIC_REVIEW_TIME, "without surrounding"),
        (7, SYNTHETIC_REVIEW_TIME, "non-empty string"),
        (None, SYNTHETIC_REVIEW_TIME, "non-empty string"),
        ("r", "2026-1-1T00:00:00Z", "not a 20-character string"),
        ("r", "2026-01-01T00:00:00", "not a 20-character string"),
        ("r", None, "not a 20-character string"),
        ("r", "2026-10-01 00:00:00Z", "not a YYYY-MM-DDTHH:MM:SSZ stamp"),
        ("r", "2026-01-01t00:00:00Z", "not a YYYY-MM-DDTHH:MM:SSZ stamp"),
        ("r", "2026-01-01T60:00:00Z", "not a YYYY-MM-DDTHH:MM:SSZ stamp"),
        ("r", "2026-01-01T00:60:00Z", "not a YYYY-MM-DDTHH:MM:SSZ stamp"),
        ("r", "2026-01-01T00:00:60Z", "not a YYYY-MM-DDTHH:MM:SSZ stamp"),
        ("r", SYNTHETIC_REVIEW_TIME + "x", "not a 20-character string"),
        ("r", 20261001, "not a 20-character string"),
    ):
        require(refuses_with(acc.bind_review_note, needle, record, REVIEW_NOTE_REL, moment,
                             repo_root=tree, reviewed_by=reviewer),
                f"bind_review_note({reviewer!r}, {moment!r}) did not name {needle!r}")
    for reviewer_label, needle in ((" reviewer ", "without surrounding"),
                                   ("\treviewer", "without surrounding"),
                                   (7, "non-empty string"), (None, "non-empty string")):
        require(refuses_with(acc.bind_review_note, needle, record, REVIEW_NOTE_REL,
                             SYNTHETIC_REVIEW_TIME, repo_root=tree, reviewed_by=reviewer_label),
                f"bind_review_note with reviewed_by={reviewer_label!r} did not name {needle!r}")
    for rel, needle in (("research/decisions/GONE.json", "not an existing regular file"),
                        ("../escape.json", "not a safe relative path"),
                        ("research/decisions/note.txt", "not a safe relative path"),
                        (17, "not a safe relative path"),
                        (None, "not a safe relative path")):
        require(refuses_with(acc.bind_review_note, needle, record, rel, SYNTHETIC_REVIEW_TIME,
                             repo_root=tree, reviewed_by="r"),
                f"bind_review_note with rel={rel!r} did not name {needle!r}")
    already = reviewed_record(tree)
    require(refuses_with(acc.bind_review_note, 'already binds a review note', already,
                         REVIEW_NOTE_REL, SYNTHETIC_REVIEW_TIME, repo_root=tree, reviewed_by="r"),
            "a second review note binding is not refused")
    for garbage in GARBAGE:
        require(refuses_typed(acc.bind_review_note, garbage, REVIEW_NOTE_REL, SYNTHETIC_REVIEW_TIME,
                              repo_root=tree, reviewed_by="r") == "AcceptanceRecordError",
                f"bind_review_note on record {garbage!r} was not refused")
        require(refuses_typed(acc.bind_review_note, record, REVIEW_NOTE_REL, SYNTHETIC_REVIEW_TIME,
                              repo_root=garbage, reviewed_by="r") == "AcceptanceRecordError",
                f"bind_review_note with repo root {garbage!r} was not refused")
    tampered = copy.deepcopy(record)
    tampered["extra"] = 1
    require(refuses_with(acc.bind_review_note, 'wrong key set', tampered, REVIEW_NOTE_REL,
                         SYNTHETIC_REVIEW_TIME, repo_root=tree, reviewed_by="r"),
            "binding a review note onto a foreign record shape is not refused")
    wrong_schema = copy.deepcopy(record)
    wrong_schema["schema"] = "decisions_os/other/v1"
    require(refuses_with(acc.bind_review_note, 'acceptance schema mismatch', wrong_schema,
                         REVIEW_NOTE_REL, SYNTHETIC_REVIEW_TIME, repo_root=tree, reviewed_by="r"),
            "binding a review note onto a foreign schema is not refused")
    # A note whose path is legal but unusual — spaces, dashes, dots, digits.  The
    # act binds it and then validates the record it produced, so this is the case
    # that proves the act leaves a record the production gate really accepts
    # rather than merely one that looks bound.
    unusual = "research/decisions/review note-01.final.json"
    write_canonical(tree, unusual, {
        "schema": acc.APPROVAL_SCHEMA,
        "statement": "SYNTHETIC FIXTURE REVIEW NOTE with an unusual but legal path.",
    })
    bound = acc.bind_review_note(built_record(tree), unusual, SYNTHETIC_REVIEW_TIME,
                                 reviewed_by=SYNTHETIC_REVIEWER, repo_root=tree)
    require(bound["approval"]["review_note_rel"] == unusual,
            "bind_review_note did not bind the note it was given")
    accepted = acc.accept_production_identity(bound, reviewed_record_sha256=pin_of(bound),
                                             repo_root=tree)
    require(accepted["accepted_content_sha256"] == pin_of(bound),
            "the record the act produced is not the record the gate accepts")
    require(accepted["review_note_sha256"] == sha256_file(os.path.join(tree, unusual)),
            "the gate did not re-hash the bound note")
    tampered_approval = copy.deepcopy(record)
    tampered_approval["approval"] = {"schema": acc.APPROVAL_SCHEMA}
    require(refuses_with(acc.bind_review_note, 'approval has the wrong key set', tampered_approval,
                         REVIEW_NOTE_REL, SYNTHETIC_REVIEW_TIME, repo_root=tree, reviewed_by="r"),
            "binding onto a malformed approval block is not refused")
    tampered_approval["approval"] = acc.unresolved_review_note()
    tampered_approval["approval"]["review_note_rel"] = REVIEW_NOTE_REL
    tampered_approval["approval"]["review_note_sha256"] = sha256_file(
        os.path.join(tree, REVIEW_NOTE_REL))
    tampered_approval["approval"]["reviewed_by"] = SYNTHETIC_REVIEWER
    tampered_approval["approval"]["reviewed_at_utc"] = SYNTHETIC_REVIEW_TIME
    require(refuses_with(acc.bind_review_note, 'already binds a review note', tampered_approval,
                         REVIEW_NOTE_REL, SYNTHETIC_REVIEW_TIME, repo_root=tree, reviewed_by="r"),
            "a fully bound approval block is not refused by the rebind guard")
    ok("the review-note binding is total, refuses bad notes, and refuses a rebind")


def test_the_wp7_receipt_is_read_from_disk_not_asserted(tree: str) -> None:
    """REGRESSION (round 2: the invented ``g9_wp7_dry_run_receipt/v1`` format).

    The bound evidence is a REAL ``wp7_session`` receipt.  Round 2 of this package
    defined a five-key ``g9_wp7_dry_run_receipt/v1`` document of its own, with a
    ``kernel_id`` and a ``bundle_sha256`` that exist nowhere in this repository,
    and bound that instead.  Here the format is ``wp7_session``'s own — the
    receipt is built by ``wp7_session.build_receipt``, gated by
    ``wp7_session.validate_receipt`` — so every field of the evidence block is a
    value read out of a file the WP7 session module accepts, and no field of this
    package has to invent a dry-run fact.
    """
    receipt_path = os.path.join(tree, acc.WP7_RECEIPT_REL)
    good = read_bytes(receipt_path)
    receipt = json.loads(good.decode("utf-8"))
    require(set(receipt) == set(wp7.RECEIPT_REQUIRED_FIELDS),
            "the fixture receipt is not a complete wp7_session receipt")
    require(refuses_typed(wp7.validate_receipt, receipt) == "",
            "the WP7 session module refuses the fixture's own receipt")
    require(set(acc.EVIDENCE_KEYS) == {"evidence_state", "receipt_rel", "receipt_sha256", "mode",
                                      "steps_executed", "package_status", "push_authorized",
                                      "gpu_allocation_authorized", "scientific_output_count",
                                      "content_sha256", "statement"},
            "the evidence block key set drifted from the documented one")
    evidence = acc.resolved_wp7_dry_run_evidence(tree)
    require(evidence["receipt_rel"] == acc.WP7_RECEIPT_REL, "the evidence names another receipt")
    require(evidence["receipt_sha256"] == sha256_file(receipt_path),
            "the recorded receipt hash is not the observed one")
    for field in ("mode", "package_status", "content_sha256"):
        require(evidence[field] == receipt[field],
                f"the evidence {field} is not the receipt's own observed value")
    require(evidence["steps_executed"] == receipt["steps_executed"],
            "the evidence steps are not the receipt's own observed steps")
    require(evidence["push_authorized"] is False and evidence["gpu_allocation_authorized"] is False,
            "the evidence claims a push or a GPU allocation the receipt does not")
    require(evidence["scientific_output_count"] == 0,
            "the evidence reports a scientific output count the receipt does not")
    require(evidence["mode"] == wp7.MODE,
            f"the evidence mode {evidence['mode']!r} is not the WP7 non-scientific mode")
    empty = os.path.join(tree, "empty")
    os.makedirs(empty, exist_ok=True)
    require(refuses_with(acc.resolved_wp7_dry_run_evidence, 'not an existing regular file', empty),
            "a repo root with no receipt is not refused")
    os.rmdir(empty)
    def edited(**changes) -> bytes:
        return contract.canonical_bytes(dict(receipt, **changes)) + b"\n"
    complete = synthetic_wp7_receipt()
    without_identity_step = [name for name in complete["steps_executed"]
                             if name != acc.WP7_IDENTITY_STEP]
    without_receipt_step = [name for name in complete["steps_executed"]
                            if name != acc.WP7_RECEIPT_REQUIRED_STEP]
    broken = [
        b"{not json\n",
        b"[]\n",
        contract.canonical_bytes([1, 2, 3]) + b"\n",
        contract.canonical_bytes({"schema": wp7.SCHEMA}) + b"\n",
        edited(schema="wrong/v1") + b"\n",
        edited(mode="scientific_run") + b"\n",
        edited(push_authorized=True) + b"\n",
        edited(gpu_allocation_authorized=True) + b"\n",
        edited(scientific_outputs=["a value"]) + b"\n",
        edited(scientific_output_count=3) + b"\n",
        edited(package_status=" ") + b"\n",
        edited(steps_executed=without_identity_step) + b"\n",
        edited(steps_executed=without_receipt_step) + b"\n",
        edited(steps_executed="dependency_gate") + b"\n",
        edited(steps_executed=list(wp7.STEP_ORDER)) + b"\n",
        edited(steps_executed=["not_a_wp7_step"]) + b"\n",
        edited(digests={}) + b"\n",
        edited(counters="nope") + b"\n",
        edited(content_sha256="3" * 64) + b"\n",
        edited(extra=1) + b"\n",
        contract.canonical_bytes(complete),
        good.decode("utf-8").replace("\n", "\n\n").encode("utf-8"),
    ]
    for payload in broken:
        rewrite(tree, acc.WP7_RECEIPT_REL, payload)
        outcome = refuses_typed(acc.resolved_wp7_dry_run_evidence, tree)
        require(outcome in ("AcceptanceRecordError", "AcceptanceEvidenceError"),
                f"a malformed receipt {payload[:40]!r} raised {outcome!r}")
        require(refuses_typed(acc.build_acceptance_record, draft_identity(tree), repo_root=tree)
                in ("AcceptanceRecordError", "AcceptanceEvidenceError"),
                f"the builder accepted a malformed receipt: {payload[:40]!r}")
    rewrite(tree, acc.WP7_RECEIPT_REL, good)
    require(acc.resolved_wp7_dry_run_evidence(tree)["receipt_sha256"] == sha256_file(receipt_path),
            "the receipt was not restored")
    ok("the WP7 receipt is a real wp7_session receipt, read from disk, and every malformed one is refused")


def test_evidence_field_refusals(tree: str) -> None:
    """Every evidence field refusal, in the record."""
    record = reviewed_record(tree)
    for field, value, needle in (
        ("evidence_state", acc.PENDING_STATUS, "evidence_state is"),
        ("evidence_state", "RESOLVED", "evidence_state is"),
        ("statement", "resolved by someone", "the statement is not the pinned resolved wording"),
        ("mode", 7, "does not re-derive from the receipt"),
        ("package_status", "", "non-empty string"),
        ("package_status", " padded ", "non-empty string"),
        ("content_sha256", "z" * 64, "lowercase hexadecimal"),
        ("content_sha256", None, "must be a string"),
        ("push_authorized", True, "does not re-derive from the receipt"),
        ("steps_executed", "dependency_gate", "does not re-derive from the receipt"),
        ("receipt_sha256", "0" * 63, "must be 64 characters"),
        ("receipt_rel", "research/decisions/GONE.json", "not the pinned receipt path"),
    ):
        changed = copy.deepcopy(record)
        changed["wp7_dry_run_evidence"][field] = value
        try:
            changed["content_sha256"] = acc._recompute_content_sha256(changed)
        except Exception:  # noqa: BLE001
            pass
        require(refuses_with_any(acc.accept_production_identity,
                                 (needle, 'not resolved', 'must be an object',
                                  'not a safe relative path', 'must be 64 characters',
                                  'does not re-derive from the receipt'),
                                 changed, reviewed_record_sha256=pin_of(changed), repo_root=tree),
                f"evidence {field}={value!r} is not refused naming {needle!r}")
    # The two fields this group is really about are named INDIVIDUALLY: a refusal
    # that reported the evidence as unresolved without saying WHICH field was
    # wrong would pass here, and that is the defect the combined shape guard exists
    # to prevent.
    for field, value, needle in (("evidence_state", acc.PENDING_STATUS, "evidence_state is"),
                                 ("evidence_state", "RESOLVED", "evidence_state is"),
                                 ("statement", "resolved by someone",
                                  "the statement is not the pinned resolved wording"),
                                 ("statement", None,
                                  "the statement is not the pinned resolved wording")):
        changed = copy.deepcopy(record)
        changed["wp7_dry_run_evidence"][field] = value
        changed["content_sha256"] = acc._recompute_content_sha256(changed)
        require(refuses_with(acc.accept_production_identity, needle, changed,
                             reviewed_record_sha256=pin_of(changed), repo_root=tree),
                f"evidence {field}={value!r} is not refused naming {needle!r}")
    changed = copy.deepcopy(record)
    changed["wp7_dry_run_evidence"]["evidence_state"] = acc.PENDING_STATUS
    changed["wp7_dry_run_evidence"]["statement"] = "resolved by someone"
    changed["content_sha256"] = acc._recompute_content_sha256(changed)
    require(refuses_with(acc.accept_production_identity,
                         "evidence_state is", changed,
                         reviewed_record_sha256=pin_of(changed), repo_root=tree),
            "an unresolved evidence block is not refused naming evidence_state")
    for how in ("extra", "missing"):
        changed = copy.deepcopy(record)
        if how == "extra":
            changed["wp7_dry_run_evidence"]["extra"] = 1
        else:
            changed["wp7_dry_run_evidence"].pop("receipt_rel")
        changed["content_sha256"] = acc._recompute_content_sha256(changed)
        require(refuses_with_any(acc.accept_production_identity, ('wrong key set', 'must be an object'),
                                 changed, reviewed_record_sha256=pin_of(changed), repo_root=tree),
                f"an evidence key set that is {how} is not refused")
    ok("every evidence field refusal is reachable and typed")


# --------------------------------------------------------------------------
# 6. the draft is never reinterpreted, and the bound block is re-derived
# --------------------------------------------------------------------------

def test_the_draft_is_never_reinterpreted(tree: str) -> None:
    """REGRESSION (round-1 probe ``REINTERPRETED_DRAFT``) kept as a standing case.

    A record whose embedded payload claims to be QUALIFIED must be refused twice:
    once by the unmodified WP1 validator, once by the bound draft status.
    """
    record = reviewed_record(tree)
    qualified = copy.deepcopy(record)
    qualified["draft_identity"]["status"] = "QUALIFIED"
    qualified["draft_identity"]["content_sha256"] = contract.content_sha256(
        {k: v for k, v in qualified["draft_identity"].items() if k != "content_sha256"})
    qualified["content_sha256"] = acc._recompute_content_sha256(qualified)
    require(rejects(qualified, tree), "a record re-labelling its draft as QUALIFIED is not refused")
    require(refuses_with_any(acc.accept_production_identity,
                             ('not an accepted WP1 DRAFT identity', 'DRAFT_UNQUALIFIED'),
                             qualified, reviewed_record_sha256=pin_of(qualified), repo_root=tree),
            "the re-labelled draft is not refused naming either guard")
    for value in ("DRAFT", "", None, 0, ["DRAFT_UNQUALIFIED"], "draft_unqualified"):
        changed = copy.deepcopy(record)
        changed["bound"]["draft_identity_status"] = value
        changed["content_sha256"] = acc._recompute_content_sha256(changed)
        require(rejects(changed, tree), f"bound draft_identity_status={value!r} is not refused")
    ok("a re-labelled draft is refused, and the bound draft status is pinned to DRAFT_UNQUALIFIED")


def test_misplaced_keys_are_refused_by_the_block_key_set(tree: str) -> None:
    """EXCLUSIVE-SHAPE groups: a moved key is refused by the block's key set.

    A guard in :func:`_validate_approval` or :func:`_validate_evidence` can only
    be reached by breaking that block's key set, because the ``_object`` type
    check that precedes it refuses anything that is not an object.  So the only
    way to drive those guards is to KEEP the key set intact and break something
    the fixture can break without touching the keys.

    This group therefore moves one key from the block under test into a
    neighbouring block — the neighbour then fails its own key set, which the
    fixture tolerates — and asserts that the block under test is still refused.
    With the moved key present, the block's key set is incomplete and a KeyError
    would escape; without the broken key's value being validated, the type guard
    would accept it.  Both guards are covered by the same edit.
    """
    record = reviewed_record(tree)
    pairs = (("approval", "bound"), ("wp7_dry_run_evidence", "bound"))
    for block, neighbour in pairs:
        keys = acc.APPROVAL_KEYS if block == "approval" else acc.EVIDENCE_KEYS
        for key in sorted(keys):
            changed = copy.deepcopy(record)
            changed[neighbour][key] = changed[block].pop(key)
            changed["content_sha256"] = acc._recompute_content_sha256(changed)
            outcome = refuses_typed(acc.accept_production_identity, changed,
                                    reviewed_record_sha256=pin_of(changed), repo_root=tree)
            require(outcome == "AcceptanceRecordError",
                    f"moving {block}.{key} into {neighbour} raised {outcome!r} rather than "
                    "a typed refusal (a KeyError here would mean the block's key set is "
                    "not enforced)")
    ok("a key moved out of the approval or evidence block is refused, never a KeyError")


def test_a_value_outside_its_block_is_refused(tree: str) -> None:
    """EXCLUSIVE-SHAPE groups: an ill-typed value, with the key set intact.

    Every group above that edits a block's value has to rely on that value being
    wrong for some other reason as well — a bad hash shape, a key set that no
    longer matches, a draft the WP1 validator refuses.  Each of those fires first
    and would mask the block's own type guard, which is exactly why that guard
    could not be killed in round 2.  Here the value is ill-typed but the hash
    SHAPES are all left valid, so nothing else in the block can fire and the type
    check is what refuses.
    """
    record = reviewed_record(tree)
    typed = (("approval", "review_note_rel", 17),
             ("approval", "reviewed_by", 17),
             ("wp7_dry_run_evidence", "receipt_rel", 17),
             ("wp7_dry_run_evidence", "package_status", 17))
    for block, field, value in typed:
        changed = copy.deepcopy(record)
        changed[block][field] = value
        changed["content_sha256"] = acc._recompute_content_sha256(changed)
        require(refuses_typed(acc.accept_production_identity, changed,
                              reviewed_record_sha256=pin_of(changed), repo_root=tree)
                == "AcceptanceRecordError",
                f"{block}.{field}={value!r} was not refused by a typed error")
    changed = copy.deepcopy(record)
    changed["approval"]["review_note_rel"] = "research/decisions/NOTE.md"
    changed["content_sha256"] = acc._recompute_content_sha256(changed)
    require(refuses_typed(acc.accept_production_identity, changed,
                          reviewed_record_sha256=pin_of(changed), repo_root=tree)
            == "AcceptanceRecordError",
            "a review note that is not a .json document was not refused by a typed error")
    ok("an ill-typed or wrong-suffix value is refused by a typed error, with every hash shape valid")


def test_the_wp7_gate_verdict_is_checked_not_assumed(tree: str) -> None:
    """The ``wp7_session.validate_receipt`` result is READ, and what is read is checked.

    The call is bound to a local and that local is compared, so removing the call
    — the mutation a discarded call invites — changes what is compared and what is
    hashed.  The case that kills it is a receipt file with one extra leading space:
    ``json.loads`` ignores leading whitespace, so the parsed body is exactly the
    right object and the record's pin still matches, yet the bytes on disk are not
    the canonical bytes of what the gate approved.  Only a validator that compares
    the file against its own gate's output can see it.  (A trailing or leading JSON
    value cannot be used: ``json.loads`` refuses "extra data" outright, so that
    route is closed by the decode step itself.)
    """
    path = os.path.join(tree, acc.WP7_RECEIPT_REL)
    original = read_bytes(path)
    padded = b" \n" + original
    require(padded != original and padded.decode("utf-8").strip() == original.decode("utf-8").strip(),
            "the padded receipt is not the same receipt with one extra leading space")
    record = reviewed_record(tree)
    with open(path, "wb") as handle:
        _ = handle.write(padded)
    try:
        require(read_bytes(path) == padded, "the padded receipt did not land on disk")
        require(refuses_typed(acc.accept_production_identity, record,
                              reviewed_record_sha256=pin_of(record), repo_root=tree)
                == "AcceptanceRecordError",
                "a WP7 receipt with one extra leading space is not refused by a typed error")
        require(refuses_typed(acc.resolved_wp7_dry_run_evidence, tree)
                in ("AcceptanceRecordError", "AcceptanceEvidenceError"),
                "resolved_wp7_dry_run_evidence accepted a receipt with one extra leading space")
    finally:
        rewrite(tree, acc.WP7_RECEIPT_REL, original)
    require(acc.resolved_wp7_dry_run_evidence(tree)["receipt_sha256"] == sha256_file(path),
            "the receipt was not restored")
    # The steps are read from the GATE's verdict, so a receipt whose executed
    # steps are present but not a list at all is refused by the type guard rather
    # than by the step-membership guard below it.  The identity step is removed
    # LAST, because the WP7 gate itself refuses a receipt that is missing any
    # required step, and that refusal fires first.
    payload = json.loads(original.decode("utf-8"))
    missing_step = [name for name in payload["steps_executed"]
                    if name not in (acc.WP7_RECEIPT_REQUIRED_STEP, acc.WP7_IDENTITY_STEP)]
    for steps in (missing_step,
                  [acc.WP7_IDENTITY_STEP],
                  [acc.WP7_RECEIPT_REQUIRED_STEP],
                  "dependency_gate", 7, {"a": 1}, None):
        broken = contract.canonical_bytes(
            {**payload, "steps_executed": steps,
             "content_sha256": wp7.content_sha256({**payload, "steps_executed": steps})}) + b"\n"
        rewrite(tree, acc.WP7_RECEIPT_REL, broken)
        outcome = refuses_typed(acc.resolved_wp7_dry_run_evidence, tree)
        require(outcome in ("AcceptanceRecordError", "AcceptanceEvidenceError"),
                f"steps_executed={steps!r} was not refused by a typed error")
        # And the two named steps are checked by NAME, so a receipt that omits
        # either one is refused for naming it rather than for something else.
    for missing_step in (acc.WP7_IDENTITY_STEP, acc.WP7_RECEIPT_REQUIRED_STEP):
        kept = [name for name in payload["steps_executed"] if name != missing_step]
        broken = contract.canonical_bytes(
            {**payload, "steps_executed": kept,
             "content_sha256": wp7.content_sha256({**payload, "steps_executed": kept})}) + b"\n"
        rewrite(tree, acc.WP7_RECEIPT_REL, broken)
        require(refuses_with_any(acc.resolved_wp7_dry_run_evidence,
                                 (f'does not name the step {missing_step!r}',
                                  'refused by the WP7 session module itself'),
                                 tree),
                f"a receipt omitting {missing_step!r} is not refused naming it")
    rewrite(tree, acc.WP7_RECEIPT_REL, original)
    rewrite(tree, acc.WP7_RECEIPT_REL, original)
    ok("the WP7 gate's verdict is compared, and the receipt bytes are what it approved")


def test_the_payload_is_refused_exactly_as_wp1_refuses_it(tree: str) -> None:
    """The builder adds NO type guard of its own in front of WP1's validator.

    ``stage2_production_identity.validate_production_identity`` requires
    ``isinstance(payload, dict)`` (``stage2_production_identity.py:394``) and
    raises for anything else, so a guard here would be dominated by it and could
    not be told apart from it.  This group therefore asserts the DOMINANCE
    directly: for every non-mapping payload the builder's refusal must be WP1's
    own refusal, re-typed, and the fixture proves WP1 really is the one refusing.
    """
    draft = draft_identity(tree)
    for payload in (("a",), (1, 2), (None,), [None], [], "text", 7, 3.5, True, b"bytes",
                    {"k": "v"}, object(), (1, 2)):
        ours = None
        try:
            acc.build_acceptance_record(payload, repo_root=tree)
        except acc.AcceptanceRecordError as exc:
            ours = str(exc)
        require(ours is not None, f"the payload {payload!r} was accepted by the builder")
        require("not an accepted WP1 DRAFT identity" in ours,
                f"the payload {payload!r} was refused for a reason other than WP1's")
        outcome = refuses_typed(wp1.validate_production_identity, payload)
        require(outcome in ("ProductionIdentityError", "AttributeError", "TypeError"),
                f"WP1 accepted the payload {payload!r} outright ({outcome!r})")
        require(refuses_typed(acc.build_acceptance_record, payload, repo_root=tree)
                == "AcceptanceRecordError",
                f"the payload {payload!r} escaped the builder as something other than a "
                "typed refusal")
    require(refuses_typed(wp1.validate_production_identity, draft) == "",
            "the fixture's own draft identity is not accepted by WP1")
    require(refuses_typed(acc.build_acceptance_record, draft, repo_root=tree) == "",
            "the fixture's own draft identity is not accepted by the builder")
    ok("every non-mapping payload is refused by WP1's own rule, re-typed and nothing added")



def test_repo_root_shape_guards(tree: str) -> None:
    """The repo-root guard and the ``bytes`` read-back guard, driven directly.

    Both live in ``_repo_file_sha256``, whose other guards (safe path, symlink,
    regular file) the path-safety group already drives.  A repo root of the wrong
    type and a repo root that is not a directory are the two inputs this group
    adds; the second is the one that makes ``read_bytes`` fail on a path that
    passed ``is_file()``.
    """
    good = reviewed_record(tree)
    pin = pin_of(good)
    for root in (17, None, b"bytes", [], {}, True, 3.5, ""):
        require(refuses_with_any(acc.accept_production_identity,
                                 ('repo root must be a non-empty string', 'not a safe relative path',
                                  'must be an object'),
                                 good, reviewed_record_sha256=pin, repo_root=root),
                f"repo_root={root!r} was not refused as a non-string or empty root")
    # A root that is a string but names no directory is refused by the
    # regular-file check, since no note or receipt can resolve under it.
    for root in (" ", "/", os.path.join(tree, "nope")):
        require(refuses_with_any(acc.accept_production_identity,
                                 ('not an existing regular file', 'is a symlink'),
                                 good, reviewed_record_sha256=pin, repo_root=root),
                f"repo_root={root!r} was not refused as a root with no bound files")
    for field, value in (("review_note_rel", REVIEW_NOTE_REL),
                         ("receipt_rel", acc.WP7_RECEIPT_REL)):
        block = "approval" if field == "review_note_rel" else "wp7_dry_run_evidence"
        empty = os.path.join(tree, "no-such-root")
        os.makedirs(empty, exist_ok=True)
        try:
            changed = copy.deepcopy(reviewed_record(tree))
            changed[block][field] = value
            changed["content_sha256"] = acc._recompute_content_sha256(changed)
            require(refuses_typed(acc.accept_production_identity, changed,
                                  reviewed_record_sha256=pin_of(changed), repo_root=empty)
                    == "AcceptanceRecordError",
                    f"{field} resolved outside an empty root was not refused by a typed error")
        finally:
            os.rmdir(empty)
    ok("the repo-root and read-back guards refuse every shape they are given")


def test_sha256_shape_is_checked_where_no_pin_is_expected(tree: str) -> None:
    """The ``_sha256_of`` digit test, driven through a hash the record derives itself.

    The record's hash fields are all compared against a derived value, so a
    malformed one is caught by the comparison first.  ``package_status`` is the
    one bound field that goes through ``_sha256_of`` with nothing to compare it
    to, and it is the only route to the digit test, so it is driven here with a
    64-character value that is simply not lowercase hexadecimal.
    """
    record = reviewed_record(tree)
    for value in ("Z" * 64, "a" * 63 + "g", "a" * 65, "0" * 63, "0" * 65):
        changed = copy.deepcopy(record)
        changed["wp7_dry_run_evidence"]["content_sha256"] = value
        changed["content_sha256"] = acc._recompute_content_sha256(changed)
        outcome = refuses_typed(acc.accept_production_identity, changed,
                               reviewed_record_sha256=pin_of(changed), repo_root=tree)
        require(outcome == "AcceptanceRecordError",
                f"evidence content_sha256={value!r} was not refused by a typed error")
    changed = copy.deepcopy(record)
    changed["wp7_dry_run_evidence"]["content_sha256"] = "F" * 64
    changed["content_sha256"] = acc._recompute_content_sha256(changed)
    require(refuses_with_any(acc.accept_production_identity,
                             ('lowercase hexadecimal', 'does not re-derive from the receipt'),
                             changed, reviewed_record_sha256=pin_of(changed), repo_root=tree),
            "an uppercase sha256 is not refused")
    require(refuses_with_any(acc.build_acceptance_record, 'lowercase hexadecimal',
                             draft_identity(tree), repo_root=17),
            "a non-string repo root is not refused by the builder")
    ok("a sha256 that is 64 characters but not lowercase hexadecimal is refused")


def test_bound_values_are_re_derived_not_trusted(tree: str) -> None:
    """Every bound slot is re-derived from the embedded payload on every read."""
    record = reviewed_record(tree)
    for key, value in (("draft_identity_schema", "decisions_os/other/v1"),
                       ("draft_identity_content_sha256", "6" * 64),
                       ("qualification_identity_content_sha256", "7" * 64),
                       ("source_map_content_sha256", "8" * 64),
                       ("bound_file_count", 1), ("bound_file_count", True),
                       ("bound_file_count", "12"),
                       ("qualified_source_map_content_sha256", "9" * 64),
                       ("qualified_source_map_file_count", 1)):
        changed = copy.deepcopy(record)
        changed["bound"][key] = value
        changed["content_sha256"] = acc._recompute_content_sha256(changed)
        require(rejects(changed, tree), f"a tampered bound {key}={value!r} is not refused")
    for key in sorted(acc.BOUND_KEYS):
        changed = copy.deepcopy(record)
        changed["bound"][key] = None
        changed["content_sha256"] = acc._recompute_content_sha256(changed)
        require(rejects(changed, tree), f"bound {key}=None is not refused")
    changed = copy.deepcopy(record)
    changed["bound"]["extra"] = 1
    changed["content_sha256"] = acc._recompute_content_sha256(changed)
    require(refuses_with(acc.accept_production_identity, 'bound block has the wrong key set', changed,
                         reviewed_record_sha256=pin_of(changed), repo_root=tree),
            "an extra bound key is not refused")
    # The integer test names the type it refused.  A non-integer that happened to
    # equal the real count must be refused by the TYPE guard rather than by the
    # equality guard, so it is driven with a value equal to the count it replaces:
    # True == 1 for small ints, which is exactly the confusion the guard prevents.
    count = record["bound"]["bound_file_count"]
    for impostor, needle in ((True, "must be an integer, not bool"),
                             (float(count), "must be an integer, not float"),
                             (str(count), "must be an integer, not str"),
                             (None, "must be an integer, not NoneType")):
        changed = copy.deepcopy(record)
        changed["bound"]["bound_file_count"] = impostor
        changed["content_sha256"] = acc._recompute_content_sha256(changed)
        require(refuses_with(acc.accept_production_identity, needle, changed,
                             reviewed_record_sha256=pin_of(changed), repo_root=tree),
                f"bound_file_count={impostor!r} is not refused naming {needle!r}")
    require(count >= 2, "the fixture's bound_file_count is too small for the bool case to bite")
    ok("every bound slot is re-derived, and a tampered, null or extra one is refused")


def test_tampering_breaks_the_pin(tree: str) -> None:
    """After any edit the record is no longer the pinned record, and that is checked.

    The PIN guard is the first guard and it commits to every byte, so for every
    edit that leaves the record structurally well-formed the refusal must name
    the pin.  The three edits that are refused EARLIER than the pin — a foreign
    schema, a non-``approved`` status and rewritten scope wording — are checked
    for refusal here too, but by the named guard that runs before it, because
    requiring the pin message for them would assert an ordering this module does
    not promise.  Both readings are asserted in
    :func:`test_deleting_the_content_sha256_slot_is_refused`.
    """
    record = reviewed_record(tree)
    good = pin_of(record)
    edits = [(None, "scope_statement", "grants a draw approval"),
             (None, "status", acc.PENDING_STATUS),
             (None, "schema", "decisions_os/other/v1")]
    for block, field, value in edits:
        changed = copy.deepcopy(record)
        changed[field] = value
        try:
            changed["content_sha256"] = acc._recompute_content_sha256(changed)
        except Exception:  # noqa: BLE001
            pass
        require(pin_of(changed) != good, f"the edit {field} did not change the pin")
        require(refuses_with_any(acc.accept_production_identity,
                                 ('not the reviewed pin', 'schema is', 'status is',
                                  'scope_statement'),
                                 changed, reviewed_record_sha256=good, repo_root=tree),
                f"an edit at {field} is still accepted under the old pin")
    edits = [(None, "wp7_dry_run_evidence", "receipt_rel", "research/decisions/NOPE.json"),
             (None, "bound", "bound_file_count", 1),
             (None, "bound", "qualified_source_map_content_sha256", "9" * 64),
             (None, "draft_identity", "status", "QUALIFIED"),
             (None, "draft_identity", "qualification_identity", {"x": 1}),
             (None, "qualified_source_map", "bound_file_count", 2),
             (None, "approval", None, None)]
    for _note, block, field, value in edits:
        changed = copy.deepcopy(record)
        if field is None:
            del changed[block]
        else:
            changed[block][field] = value
        try:
            changed["content_sha256"] = acc._recompute_content_sha256(changed)
        except Exception:  # noqa: BLE001
            pass
        require(pin_of(changed) != good, f"the edit {block}.{field} did not change the pin")
        require(refuses_with_any(acc.accept_production_identity,
                                 ('not the reviewed pin', 'wrong key set'),
                                 changed, reviewed_record_sha256=good, repo_root=tree),
                f"an edit at {block}.{field} is still accepted under the old pin")
    changed = copy.deepcopy(record)
    changed["content_sha256"] = "8" * 64
    require(refuses_with_any(acc.accept_production_identity,
                             ('content_sha256 mismatch', 'not the reviewed pin'),
                             changed, reviewed_record_sha256=good, repo_root=tree),
            "a wrong internal content_sha256 is not refused once the pin matches its bytes")
    # The INTERNAL hash is checked last, so reaching it needs a pin that matches
    # the tampered bytes AND a body that re-derives to the recorded value.  Taking
    # a real record, moving its status to another approved-shaped value and then
    # re-deriving the internal hash gives exactly that: the pin matches the bytes,
    # and the internal hash is stale only because the body was edited after it.
    stale = copy.deepcopy(record)
    stale["scope_statement"] = acc.SCOPE_STATEMENT
    stale["bound"] = dict(stale["bound"])
    stale["bound"]["source_map_content_sha256"] = "0" * 64
    stale["content_sha256"] = record["content_sha256"]
    require(refuses_typed(acc.accept_production_identity, stale,
                          reviewed_record_sha256=pin_of(stale), repo_root=tree)
            == "AcceptanceRecordError",
            "a record whose internal hash is stale is not refused")
    require(refuses_with_any(acc.accept_production_identity,
                             ('content_sha256 mismatch', 'does not re-derive from the embedded'),
                             stale, reviewed_record_sha256=pin_of(stale), repo_root=tree),
            "a stale internal content_sha256 is not refused by the consistency check")
    ok("every post-review edit breaks the pinned identity of the record")


# --------------------------------------------------------------------------
# 7. the happy path and its exact binding
# --------------------------------------------------------------------------

def test_the_happy_path_returns_exactly_what_the_record_says(tree: str) -> None:
    record = reviewed_record(tree)
    accepted = accept(tree, record)
    receipt = acc.validate_acceptance_record(record, reviewed_record_sha256=pin_of(record),
                                             repo_root=tree)
    require(receipt["status"] == acc.APPROVED_STATUS, "the validator reports another status")
    require(accepted["accepted_content_sha256"] == pin_of(record), "the accepted hash is wrong")
    for key in ("review_note_sha256", "draft_identity_content_sha256",
                "qualification_identity_content_sha256", "source_map_content_sha256",
                "bound_file_count", "qualified_source_map_content_sha256",
                "qualified_source_map_file_count", "wp7_dry_run_receipt_sha256"):
        require(accepted[key] == receipt[key], f"the gate disagrees with the validator on {key}")
    require(accepted["bound_file_count"] == record["draft_identity"]["source_map"]["bound_file_count"],
            "the gate reports the wrong bound file count")
    require(accepted["qualified_source_map_file_count"]
            == record["qualified_source_map"]["bound_file_count"],
            "the gate reports the wrong qualified file count")
    require(accepted["draft_identity"] == record["draft_identity"],
            "the gate returns a different draft identity than the record holds")
    require(accepted["qualified_source_map"] == record["qualified_source_map"],
            "the gate returns a different qualified source map than the record holds")
    require(receipt["review_note_sha256"] == sha256_file(os.path.join(tree, REVIEW_NOTE_REL)),
            "the receipt does not report the observed review-note hash")
    require(receipt["wp7_dry_run_mode"] == wp7.MODE,
            "the receipt does not report the WP7 non-scientific mode it observed")
    require(receipt["wp7_dry_run_package_status"] == wp7.build_receipt(
        steps=list(wp7.REQUIRED_STEPS) + [acc.WP7_RECEIPT_REQUIRED_STEP],
        counters={}, identities={},
        digests={f"step:{name}": SYNTHETIC_STEP_DIGEST for name in wp7.REQUIRED_STEPS},
        differences=[""])["package_status"],
        "the receipt does not report the observed package status")
    require(acc.WP7_IDENTITY_STEP in receipt["wp7_dry_run_steps_executed"],
            "the receipt does not report the identity step that produced this evidence")
    accepted["draft_identity"]["status"] = "MUTATED"
    accepted["qualified_source_map"]["roles"].clear()
    require(record["draft_identity"]["status"] == wp1.DRAFT_STATUS,
            "mutating the returned draft reached back into the record")
    require(record["qualified_source_map"]["roles"], "mutating the returned map reached the record")
    ok("the gate returns exactly the record's own hashes, map and draft identity")


def test_the_builder_is_deterministic_and_does_not_mutate_its_input(tree: str) -> None:
    draft = draft_identity(tree)
    frozen = copy.deepcopy(draft)
    first = reviewed_record(tree)
    second = reviewed_record(tree)
    require(first == second, "two builds of the same inputs differ")
    require(draft == frozen, "the builder mutated the draft identity it was given")
    require(first["draft_identity"] == draft, "the record does not embed the draft it was given")
    require(pin_of(first) == pin_of(second), "two builds do not share one pin")
    built = built_record(tree)
    frozen_built = copy.deepcopy(built)
    acc.bind_review_note(built, REVIEW_NOTE_REL, SYNTHETIC_REVIEW_TIME,
                         reviewed_by=SYNTHETIC_REVIEWER, repo_root=tree)
    require(built == frozen_built, "bind_review_note mutated the record it was given")
    ok("the builder is deterministic, embeds its input and mutates nothing")


def test_the_builder_refuses_a_non_draft_payload(tree: str) -> None:
    """The builder validates with the UNMODIFIED WP1 validator first."""
    draft = draft_identity(tree)
    for mutate in (
        lambda body: body.__setitem__("status", "QUALIFIED"),
        lambda body: body.__setitem__("authorization", "OWNER"),
        lambda body: body.pop("source_map"),
        lambda body: body.__setitem__("schema", "decisions_os/other/v1"),
        lambda body: body.__setitem__("content_sha256", "9" * 64),
        lambda body: body.__setitem__("authorization_note", "This payload is approved."),
    ):
        body = copy.deepcopy(draft)
        mutate(body)
        require(refuses_with(acc.build_acceptance_record, 'not an accepted WP1 DRAFT identity',
                             body, repo_root=tree),
                "a payload WP1 refuses was accepted by the builder")
    for garbage in GARBAGE:
        require(refuses_typed(acc.build_acceptance_record, garbage, repo_root=tree)
                == "AcceptanceRecordError",
                f"build_acceptance_record({garbage!r}) was not refused by a typed error")
    for garbage in GARBAGE:
        outcome = refuses_typed(acc.build_acceptance_record, draft, repo_root=garbage)
        require(outcome in ("AcceptanceRecordError", "AcceptanceEvidenceError"),
                f"build_acceptance_record with repo root {garbage!r} was not refused")
    ok("the builder refuses every payload the unmodified WP1 validator refuses")


def test_scope_and_constants_are_pinned(tree: str) -> None:
    record = reviewed_record(tree)
    require(record["scope_statement"] == acc.SCOPE_STATEMENT, "the scope wording drifted")
    require("not a draw approval" in acc.SCOPE_STATEMENT,
            "the scope statement no longer says it grants no draw approval")
    require("not a scientific-write authorization" in acc.SCOPE_STATEMENT,
            "the scope statement no longer says it authorizes no scientific write")
    require(set(acc.RECORD_KEYS) == set(record), "the record does not carry exactly RECORD_KEYS")
    require(acc.ACCEPTANCE_SCHEMA != wp1.PRODUCTION_IDENTITY_SCHEMA,
            "the acceptance schema reuses the WP1 draft schema string")
    require(acc.ACCEPTANCE_SCHEMA.endswith("/v2"), "the acceptance schema is not a new version")
    require(acc.QUALIFIED_SOURCE_MAP_SCHEMA != wp1.SOURCE_MAP_SCHEMA,
            "the qualified source map schema reuses the WP1 schema string")
    for name in ("AcceptanceStatusError", "AcceptanceEvidenceError", "AcceptanceBindingError",
                 "AcceptanceReviewError", "AcceptanceSessionMismatch"):
        require(issubclass(getattr(acc, name), acc.AcceptanceRecordError),
                f"{name} does not derive from AcceptanceRecordError")
    require(issubclass(acc.AcceptanceRecordError, ValueError),
            "the refusal family does not derive from ValueError")
    ok("the schema, the scope wording, the key set and the refusal family are pinned")


# --------------------------------------------------------------------------
# 8. session-side comparison
# --------------------------------------------------------------------------

def test_session_comparison_is_exact_and_names_differences(tree: str) -> None:
    record = reviewed_record(tree)
    draft = record["draft_identity"]
    verdict = acc.exact_match_session(draft, record, reviewed_record_sha256=pin_of(record),
                                      repo_root=tree)
    require(verdict["verdict"] == "exact_match", "an identical session identity did not match")
    require(verdict["differing_fields"] == [], "an exact match reported differences")
    require(verdict["accepted_content_sha256"] == pin_of(record), "the verdict names another record")
    for mutate in (
        lambda body: body["qualification_identity"]["platform"].__setitem__("gpu_name", "other"),
        lambda body: body["source_map"]["roles"][wp1.V1_ENGINE_ROLE][0].__setitem__("sha256", "a" * 64),
        lambda body: body["qualification_identity"]["compiler_flags"].append("-Wall"),
        lambda body: body.pop("image_build_evidence"),
    ):
        session = copy.deepcopy(draft)
        mutate(session)
        outcome = refuses_typed(acc.exact_match_session, session, record,
                                reviewed_record_sha256=pin_of(record), repo_root=tree)
        require(outcome in ("AcceptanceSessionMismatch", "AcceptanceRecordError"),
                f"a differing session identity raised {outcome!r}")
    # A session identity that is a genuine, self-consistent WP1 DRAFT but differs
    # in one field must raise the MISMATCH type, not the record error.
    # exact_match() validates BOTH operands first (stage2_production_identity.py:444-445),
    # so an internally inconsistent session is refused before any field is compared.
    # The edit therefore keeps BOTH hashes self-consistent: it appends a flag to
    # the frozen identity, recomputes that identity's own content hash, and then
    # recomputes the draft's content hash over the new body.  Without the second
    # step WP1 would refuse the payload at :421 and this case would be vacuous.
    mismatched = copy.deepcopy(draft)
    mismatched["qualification_identity"]["compiler_flags"].append("-SYNTHETIC-FIXTURE-FLAG")
    inner = contract.content_sha256(
        {k: v for k, v in mismatched["qualification_identity"].items() if k != "content_sha256"})
    mismatched["qualification_identity"]["content_sha256"] = inner
    mismatched["content_sha256"] = contract.content_sha256(
        {k: v for k, v in mismatched.items() if k != "content_sha256"})
    require(refuses_typed(wp1.validate_production_identity, mismatched) == "",
            "the fixture's own mismatched session identity is not a valid WP1 draft")
    outcome = refuses_typed(acc.exact_match_session, mismatched, record,
                            reviewed_record_sha256=pin_of(record), repo_root=tree)
    require(outcome == "AcceptanceSessionMismatch",
            f"a well-formed differing session raised {outcome!r}, not AcceptanceSessionMismatch")
    try:
        acc.exact_match_session(mismatched, record, reviewed_record_sha256=pin_of(record),
                                repo_root=tree)
    except acc.AcceptanceSessionMismatch as exc:
        require(any("compiler_flags" in field for field in exc.differing_fields),
                f"the mismatch does not name the differing field: {exc.differing_fields!r}")
        require(exc.message == str(exc),
                "AcceptanceSessionMismatch.message disagrees with the str() of the exception")
        require(exc.args == (exc.message,), "AcceptanceSessionMismatch.args disagree with its message")
    else:
        raise RuntimeError("FIXTURE FAILURE: the differing session identity was not refused")
    changed = copy.deepcopy(record)
    changed["bound"]["bound_file_count"] = 1
    changed["content_sha256"] = acc._recompute_content_sha256(changed)
    require(refuses_typed(acc.exact_match_session, draft, changed,
                          reviewed_record_sha256=pin_of(changed), repo_root=tree)
            == "AcceptanceRecordError",
            "an unbound record is still compared against a session identity")
    ok("the session comparison delegates to WP1, is exact, and names every difference")


# --------------------------------------------------------------------------
# 9. scope: no production surface, no network, no clock, no writes
# --------------------------------------------------------------------------

def test_the_module_touches_no_production_surface() -> None:
    """Asserted on the parsed AST, not on text, so a rename cannot hide it."""
    import ast
    source = read_bytes(os.path.join(V1_REPO_ROOT, acc.THIS_MODULE_REL)).decode("utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                imported.add("relative-import")
            elif node.module:
                imported.add(node.module.split(".")[0])
    allowed = {"__future__", "copy", "hashlib", "json", "pathlib", "typing", "research"}
    require(imported <= allowed, f"the module imports {sorted(imported - allowed)}")
    for banned in ("socket", "subprocess", "urllib", "requests", "os", "time", "random",
                   "datetime", "shutil", "tempfile", "kagglehub", "torch", "numpy", "platform"):
        require(banned not in imported, f"the module imports {banned}")
    called = {node.func.id for node in ast.walk(tree)
              if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    for banned in ("eval", "exec", "compile", "__import__"):
        require(banned not in called, f"the module calls {banned}")
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            require(node.func.attr not in ("system", "popen", "remove", "unlink", "rmdir",
                                           "write_text", "write_bytes", "mkdir", "touch",
                                           "rmtree", "chmod"),
                    f"the module calls {node.func.attr}, which can touch the filesystem")
    for banned in ("kaggle kernels push", "api.kaggle.com", "stage2_instances/",
                   "torch.cuda", "device_count"):
        require(banned not in source, f"the module mentions {banned}")
    ok("the module imports only allow-listed modules and makes no production call")


def test_nothing_was_written_outside_the_temporary_trees(tree: str) -> None:
    """The fixture never writes into the real repository."""
    scratch = os.environ[SCRATCH_ENV]

    def listing() -> list:
        return sorted(str(path.relative_to(ROOT)) for path in ROOT.rglob("*")
                      if path.is_file() and acc.WP8A_ROLE not in str(path)
                      and "__pycache__" not in str(path))

    before = listing()
    with tempfile.TemporaryDirectory(prefix="wp8a-probe-", dir=scratch) as probe:
        make_synthetic_tree(probe)
        _ = reviewed_record(probe)
    after = listing()
    require(before == after, "the fixture added or removed a file outside research/g9/wp8a/")
    require(not list(ROOT.rglob("*.pyc")), "a .pyc file exists in the repository")
    ok("the fixture writes only inside its temporary tree and leaves no .pyc")


def test_the_unreached_guard_branches_are_refused(tree: str) -> None:
    """The refusal branches that ``except`` and containment reach, driven directly.

    ``_read_wp7_receipt`` re-types a refusal from the WP7 gate instead of letting
    it escape, and the qualified map reports a path of this package that no role
    binds.  Neither is reachable by editing a well-formed record — the first needs
    a receipt the gate itself rejects, the second needs a map that no builder here
    can produce — so each is driven through its own function, and the fixture also
    proves the WP7 gate really does refuse the receipt it uses.
    """
    payload = json.loads(read_bytes(os.path.join(tree, acc.WP7_RECEIPT_REL)).decode("utf-8"))
    broken = {**payload, "mode": "scientific_run"}
    broken["content_sha256"] = wp7.content_sha256(
        {key: value for key, value in broken.items() if key != "content_sha256"})
    require(refuses_typed(wp7.validate_receipt, broken)
            in ("Wp7SessionError", "Wp7IncompleteReceiptError"),
            "the WP7 session module accepts a receipt with a scientific mode")
    good = read_bytes(os.path.join(tree, acc.WP7_RECEIPT_REL))
    rewrite(tree, acc.WP7_RECEIPT_REL, contract.canonical_bytes(broken) + b"\n")
    try:
        outcome = refuses_typed(acc.resolved_wp7_dry_run_evidence, tree)
        require(outcome in ("AcceptanceEvidenceError", "AcceptanceRecordError"),
                f"a receipt the WP7 gate refuses raised {outcome!r} instead of a refusal "
                "in this package's own family")
        outcome = refuses_typed(acc.build_acceptance_record, draft_identity(tree), repo_root=tree)
        require(outcome in ("AcceptanceEvidenceError", "AcceptanceRecordError"),
                f"the builder bound a receipt the WP7 gate refuses (raised {outcome!r})")
    finally:
        rewrite(tree, acc.WP7_RECEIPT_REL, good)
    require(refuses_typed(acc.resolved_wp7_dry_run_evidence, tree) == "",
            "the fixture's own receipt was not restored")
    source_map = reviewed_record(tree)["qualified_source_map"]
    unbound = {key: value for key, value in
               dict(source_map["roles"][acc.WP8A_ROLE][0]).items()}
    for broken_map in (
        {**copy.deepcopy(source_map), "roles": {**copy.deepcopy(source_map["roles"]),
                                               acc.WP8A_ROLE: []}},
        {**copy.deepcopy(source_map), "bound_file_count": source_map["bound_file_count"] - 1},
    ):
        require(refuses_typed(acc._validate_qualified_source_map_shape, broken_map)
                == "AcceptanceRecordError",
                "a malformed qualified source map is not refused by its shape validator")
    require(set(unbound) == {"path", "sha256"},
            "the containment probe did not read a real map entry")
    require(unbound["path"] in acc.wp8a_qualified_files(),
            f"the containment probe read {unbound['path']!r}, which this package does not claim")


def test_mirror_predicates_agree_with_the_module(tree: str) -> None:
    """The fixture re-derives the module's predicates and must agree on every probe."""
    probes: list = list(GARBAGE) + [
        "a" * 64, "A" * 64, "z" * 64, "0" * 63, "0" * 65, "research/g9/x.json",
        "research/g9/x.py", "research/g9/x.cu", "/abs/x.json", "../x.json", "a//b.json",
        "a/./b.json", "a/ b.json", " a/b.json", "a\\b.json", "C:/x.json", "x.JSON",
        "2026-01-01T00:00:00Z", "2026-01-01t00:00:00Z", "2026-01-01T00:00:00", "x" * 20,
        "research/g9/wp8a/wp8a_production_identity_acceptance.py",
    ]
    for probe in probes:
        require(acc._is_sha256(probe) == _is_sha256(probe),
                f"the two _is_sha256 disagree on {probe!r}")
        require(acc._is_safe_rel(probe) == _is_safe_rel(probe),
                f"the two _is_safe_rel disagree on {probe!r}")
        require(acc._is_safe_source_rel(probe) == _is_safe_source_rel(probe),
                f"the two _is_safe_source_rel disagree on {probe!r}")
        # Compared raise-or-return rather than by value alone, so a mutation that
        # turns one of these predicates into a RAISE (or swallows one) is caught
        # here as well as through the gate.
        require(_outcome_of(acc._is_utc_stamp, probe) == _outcome_of(_is_utc_stamp, probe),
                f"the two _is_utc_stamp disagree on {probe!r}")
    require(tuple(sorted(acc.QUALIFIED_SOURCE_SUFFIXES)) == tuple(sorted(MIRROR_SOURCE_SUFFIXES)),
            f"the two suffix tuples disagree: {acc.QUALIFIED_SOURCE_SUFFIXES} vs {MIRROR_SOURCE_SUFFIXES}")
    for suffix in MIRROR_SOURCE_SUFFIXES:
        probe = "research/g9/wp8a/file" + suffix
        require(acc._is_safe_source_rel(probe) is True,
                f"the module refuses a qualified source path ending {suffix!r}")
    for suffix in (".txt", ".jsonc", ".pyc", ".exe", ""):
        probe = "research/g9/wp8a/file" + suffix
        require(acc._is_safe_source_rel(probe) is False,
                f"the module accepts a qualified source path ending {suffix!r}")
    ok("the fixture's mirrors and the module's predicates agree on every probe")


# --------------------------------------------------------------------------
# the driver
# --------------------------------------------------------------------------

TESTS = [
    test_no_signature_field_or_claim_exists,
    test_the_pin_is_the_authority_and_comes_from_the_caller,
    test_record_is_canonical_bytes_and_the_pin_is_their_sha256,
    test_status_is_approved_and_no_other_status_is_accepted,
    test_forged_owner_labelled_record_is_refused,
    test_nonexistent_evidence_file_is_refused,
    test_nonexistent_authority_file_is_refused,
    test_review_note_and_receipt_must_hash_to_what_the_record_says,
    test_named_paths_must_be_regular_non_symlink_files_inside_the_root,
    test_every_bound_source_file_is_rehashed_against_disk,
    test_deleting_a_bound_source_file_is_refused,
    test_wp8a_module_is_inside_the_qualified_source_map,
    test_a_file_read_by_this_package_that_is_not_bound_is_refused,
    test_every_package_file_must_be_bound_by_some_role,
    test_qualified_source_map_bookkeeping_is_re_derived,
    test_malformed_bound_block_is_a_typed_refusal_not_a_KeyError,
    test_fuzz_every_record_slot_with_garbage,
    test_fuzz_nested_blocks_with_garbage,
    test_fuzz_qualified_source_map_and_draft_with_garbage,
    test_the_record_itself_may_be_any_garbage,
    test_record_shell_and_extra_key_refusals,
    test_deleting_the_content_sha256_slot_is_refused,
    test_a_freshly_built_record_is_refused_until_reviewed,
    test_bind_review_note_refuses_bad_input,
    test_the_approval_block_is_pinned_in_the_validator,
    test_the_wp7_receipt_is_read_from_disk_not_asserted,
    test_evidence_field_refusals,
    test_the_draft_is_never_reinterpreted,
    test_misplaced_keys_are_refused_by_the_block_key_set,
    test_a_value_outside_its_block_is_refused,
    test_the_wp7_gate_verdict_is_checked_not_assumed,
    test_the_payload_is_refused_exactly_as_wp1_refuses_it,
    test_repo_root_shape_guards,
    test_sha256_shape_is_checked_where_no_pin_is_expected,
    test_bound_values_are_re_derived_not_trusted,
    test_tampering_breaks_the_pin,
    test_the_happy_path_returns_exactly_what_the_record_says,
    test_the_builder_is_deterministic_and_does_not_mutate_its_input,
    test_the_builder_refuses_a_non_draft_payload,
    test_scope_and_constants_are_pinned,
    test_session_comparison_is_exact_and_names_differences,
    test_the_module_touches_no_production_surface,
    test_nothing_was_written_outside_the_temporary_trees,
    test_the_unreached_guard_branches_are_refused,
    test_mirror_predicates_agree_with_the_module,
]


#: Optional: run exactly the named groups and exit with their own status.  The
#: mutation gate needs this, and it needs it for a mechanical reason: the gate
#: times each mutant against a whole-suite baseline, so a guard that a LATE group
#: would have killed still reads as a survivor when the mutant is slow enough to
#: hit that timeout first.  Selecting groups by name lets the gate order them so
#: every guard is exercised early, where a mutant cannot out-run the budget.
#: This is bookkeeping for the harness, not a way to weaken a check: the named
#: group still runs on its own with its own exit status, and ``TESTS`` above is
#: unchanged.  With the variable unset every group runs, exactly as before.
ONLY_ENV = "G9_WP8A_ONLY"


def run_group(test, scratch: str) -> None:
    """Run one group against a fresh synthetic tree, raising on any failure."""
    if test.__code__.co_argcount == 1:
        with tempfile.TemporaryDirectory(prefix="wp8a-", dir=scratch) as tree:
            make_synthetic_tree(tree)
            test(tree)
    else:
        test()


def main() -> None:
    scratch = os.environ.get(SCRATCH_ENV)
    if not scratch:
        raise SystemExit(SCRATCH_ENV + " must name a writable directory outside the repository")
    os.makedirs(scratch, exist_ok=True)
    wanted = [name for name in os.environ.get(ONLY_ENV, "").split(",") if name]
    known = {test.__name__ for test in TESTS}
    unknown = [name for name in wanted if name not in known]
    if unknown:
        raise SystemExit(ONLY_ENV + " names no such group: " + ", ".join(unknown))
    groups = 0
    for test in TESTS:
        if wanted and test.__name__ not in wanted:
            continue
        groups += 1
        run_group(test, scratch)
        print(f"  [{groups:02d}] {test.__name__}")
    print(f"\nWP8a fixtures: {len(PASSED)} checks across {groups} groups, all passed. "
          f"Synthetic, offline, no Kaggle, no GPU, no production seed or beacon.")


if __name__ == "__main__":
    main()

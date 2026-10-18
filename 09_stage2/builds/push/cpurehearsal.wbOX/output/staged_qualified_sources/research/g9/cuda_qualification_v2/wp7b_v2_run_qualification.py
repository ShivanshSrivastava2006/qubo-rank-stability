"""WP7b D013 v2 qualification EXECUTOR -- COPY, CANDIDATE, NOT APPROVED.

Why this file exists
--------------------

The reviewed v2 plan
(:mod:`research.g9.cuda_qualification_v2.stage2_cuda_d013_inactive_corruption_qualification`)
has ``build_plan`` but **no** ``run_qualification``. The WP7b launcher calls
``d013_q.run_qualification(...)`` at
:mod:`research.g9.kaggle_wp7b.wp7b_launcher` :490, so a v2-backed WP7b run has
nothing to resolve that call against. Authorising a release alone would leave it
unresolvable.

This module supplies that executor. It is the v1 executor's algorithm
re-derived against the v2 candidate, and it is honest about what it reuses:

  * the nine mutations, their anchors, hazards and the detection table are
    IMPORTED from the frozen v1 plan, not retyped;
  * the reviewed numeric flags (``GPU_COMPILE_FLAGS``, ``CLEAN_CONDITIONS``)
    are IMPORTED from the frozen v1 plan, not retyped;
  * the release gate, the source map, the token proof and ``_check_token`` are
    DELEGATED to the reviewed v2 plan, never restated;
  * the independent Python reference -- the frozen host-emulation fixture, which
    computes the domain, the energies, the minimum and the tie flags in pure
    Python from the payload -- is the ONLY thing that judges a compiled result.

The v1 executor's shape is preserved: compile the clean candidate, compile each
mutation, run exactly the reviewed detection cases, and require the clean build
to agree with the independent reference while every mutation is rejected.

What is NOT weakened
-------------------

  * ``_released(reviewed_release_sha256)`` is called FIRST, before any nvcc
    lookup, any compiler invocation and any device operation. It refuses unless
    the v2 release draft exists, is canonical, carries ``owner_approved is
    True``, matches the reviewed handoff digest, and whose source map still
    matches the v2 files on disk.
  * No token is ever synthesised, defaulted, reused from v1, or fabricated.
    With the shipped draft (``owner_approved: false``) ``_released`` refuses, so
    ``run_qualification`` refuses before nvcc is located. That is the correct
    outcome, and it is a refusal -- not a skip, a warning, or a pass.
  * The source map is re-checked before and after the sweep.
  * Every judgement is made by the independent reference, not by the bridge.

Scope
-----
Non-scientific. It compiles a synthetic fixture and judges it against an
independent Python reference. It reads no external data, performs no scientific
computation, produces no production seed, no drawing, and no beacon.
"""

from __future__ import annotations

import hashlib
import json
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Mapping

# FROZEN reviewed dependencies, imported by absolute path. Not copied, not
# edited. The v1 release, v1 bridge, v1 plan and host-emulation fixture all keep
# validating against their own bytes.
from research.g9.cuda_qualification import (
    stage2_cuda_d013_inactive_corruption_qualification as _v1_plan)
from research.g9.cuda_qualification_v2 import (
    stage2_cuda_d013_inactive_v2_corruption_qualification as _v2_plan)

# The launcher-facing names are delegated to the COPY compatibility adapter, so
# this executor and the launcher exercise the SAME bridge object.
from research.g9.cuda_qualification_v2 import wp7b_v2_bridge_compat as _compat


# --- the v2 bindings. These are the ONLY paths that differ from v1. ---------
ROOT = _v2_plan.ROOT
SOURCE_REL = _v2_plan.SOURCE_REL
RELEASE_DRAFT_REL = _v2_plan.RELEASE_DRAFT_REL
SOURCE_RELS = _v2_plan.SOURCE_RELS

RECEIPT_SCHEMA = _v2_plan.RECEIPT_SCHEMA

# A SEPARATE permission variable. The v1 arming variable never arms this path.
ALLOW_ENV = _v2_plan.ALLOW_ENV

# The reviewed numeric flags and the reviewed corruption tables: imported, not
# copied. The device-pointer repair changes launch plumbing only, never a flag.
GPU_COMPILE_FLAGS = _v2_plan.GPU_COMPILE_FLAGS
CLEAN_CONDITIONS = _v2_plan.CLEAN_CONDITIONS
MUTATIONS = _v2_plan.MUTATIONS
DETECTION_CASES = _v2_plan.DETECTION_CASES

CorruptionQualificationError = _v2_plan.CorruptionQualificationError

# Compiled once in a private temporary directory, inside the bounded dry run.
COMPILE_TIMEOUT_SECONDS = 240
VERSION_TIMEOUT_SECONDS = 30

# The ACTIVATED v2 candidate. Re-derived from the repaired .cu bytes, which bind
# the core stream engine by the relative path the in-place no-`-I` compile can
# resolve. This gate is the SECOND live enforcement point on the candidate bytes
# (the first is the launcher's D013_V2_REPAIRED_SOURCE_SHA256); it is unchanged in
# KIND and still refuses on any mismatch -- only the pinned value moved.
V2_REPAIRED_SOURCE_SHA256 = (
    "74a912f9f145a655a1084fe510516f08fc0121a3c6760f469ce1a90d014f30c4")
# Superseded unrepaired candidate, retained for evidence only. Recorded in the
# reviewed v1 release draft and in the r2 draft, and carried by a previously
# pushed kernel. It must not re-enter any enforcement position.
V2_SUPERSEDED_SOURCE_SHA256 = (
    "953b7f15a14950d75536d72b074a7907dc06df13539b2ce3f4122cc427ab0f61")

# --- the token serialization boundary. --------------------------------------
#
# Why this exists. ``verified_release_token`` returns the FROZEN v1
# ``VerifiedReleaseToken`` dataclass, because that is the type the reviewed v2
# plan mints and the type ``_check_token`` accepts as the real thing. That object
# is NOT JSON serializable, and the reviewed contract digests with a plain
# ``json.dumps``. So hashing a receipt that still holds the live object raises
# ``TypeError: Object of type VerifiedReleaseToken is not JSON serializable``
# -- which is exactly how hosted run 284e713c died, at the launcher's canonical()
# over the qualification report, and would still die one step earlier inside
# this executor's own ``content_sha256`` call.
#
# What this boundary does. It renders the live token into the EXACT three-key
# ABI representation -- {release_sha256, source_map_sha256, proof_sha256} --
# which is the second form ``_check_token`` accepts, byte-for-byte the schema
# the runtime token carries. Every verified field is preserved: nothing is
# dropped, defaulted, repr()-ed, stringified or iterated unordered. The rendered
# value is what the receipt stores, what the digest covers, and what the launcher
# forwards to the ABI gate and WP3, so all four representations agree.
#
# This is a serialization boundary, NOT a weakening. The digest still commits to
# the exact release digest, the exact source-map digest and the exact token
# proof, so a downgraded or tampered token changes the receipt digest. It is
# also not a bypass: the projection only runs AFTER ``_released`` has already
# owner-gated the release, and it refuses rather than degrades if the token does
# not carry all three verified fields as lowercase sha256 digests.

# The complete set of verified identity fields on VerifiedReleaseToken. This is
# the same tuple the launcher binds, and it is exactly the ABI key set.
TOKEN_BINDING_FIELDS = ("release_sha256", "source_map_sha256", "proof_sha256")


def _token_repr(token: object) -> dict[str, str]:
    """Render a live v2 release token into its exact JSON-safe ABI form.

    Refuses -- it never returns a partial projection -- if the token is absent,
    is not the real verified token type the reviewed v2 plan mints, or does not
    carry all three verified fields as lowercase sha256 digests. It is
    reproducible from the token alone and stable across calls.
    """
    if type(token) is not _v1_token_type():
        raise CorruptionQualificationError(
            "receipt serialization refuses a release token that is not the "
            "reviewed VerifiedReleaseToken")
    present = tuple(f for f in TOKEN_BINDING_FIELDS if hasattr(token, f))
    if present != TOKEN_BINDING_FIELDS:
        raise CorruptionQualificationError(
            "release token does not carry the reviewed binding fields")
    # A dataclass token declares its fields; refuse if it declares one this
    # projection does not bind, so the receipt can never cover LESS than the
    # token verifies.
    declared = getattr(token, "__dataclass_fields__", None)
    if declared is not None:
        extra = sorted(f for f in declared if f not in TOKEN_BINDING_FIELDS)
        if extra:
            raise CorruptionQualificationError(
                "release token grew unprojected field(s)")
    projection = {f: getattr(token, f) for f in TOKEN_BINDING_FIELDS}
    for field, value in projection.items():
        if type(value) is not str or len(value) != 64 or any(
                character not in "0123456789abcdef" for character in value):
            raise CorruptionQualificationError(
                "release token field is not a lowercase sha256 digest: " + field)
    return projection


def _v1_token_type():
    """The real frozen VerifiedReleaseToken class, from the frozen v1 plan."""
    return _v1_plan.VerifiedReleaseToken


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CorruptionQualificationError(message)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _run(command, label: str, *, timeout: int) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(command, cwd=ROOT, text=True, capture_output=True,
                              check=False, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CorruptionQualificationError(label + " failed or timed out") from exc


def source_hashes() -> dict[str, str]:
    """The v2 source map, delegated to the reviewed v2 plan."""
    return _v2_plan.source_hashes()


def source_text() -> str:
    """The reviewed v2 candidate source, delegated."""
    return _v2_plan.source_text()


def _released(reviewed_release_sha256: str) -> Mapping[str, object]:
    """The v2 release gate, delegated in full to the reviewed v2 plan.

    Raises ``CorruptionQualificationError`` unless the v2 release draft is
    present, canonical, owner-approved, matches the reviewed handoff digest, and
    still binds the v2 files on disk. This is the first statement of
    ``run_qualification``, so nothing is compiled and no device is touched until
    it has passed.
    """
    return _v2_plan._released(reviewed_release_sha256)


def selected_mutation_sources(source: str):
    """Production selection always means the complete reviewed mutation set."""
    return _v2_plan.mutated_sources(source)


def _clean_baseline_cases():
    """The clean build must also pass the frozen four-condition baseline.

    These are the same ``DetectionCase`` rows v1 adds for the clean build, built
    from the frozen v1 constructor so the row shape cannot drift.
    """
    return tuple(_v1_plan.DetectionCase(condition, "noncommuting", "mismatch")
                 for condition in CLEAN_CONDITIONS)


def run_qualification(reviewed_release_sha256: str) -> dict[str, object]:
    """Compile and independently qualify the clean and mutated D013 v2 ABIs.

    Returns a receipt on success. Raises ``CorruptionQualificationError`` -- it
    never returns a partial or optimistic verdict -- if the release gate refuses,
    if the clean candidate does not compile, if the clean build disagrees with
    the independent reference, or if any mutation goes undetected.
    """
    # (1) Release gate FIRST. Refuses on the shipped unapproved draft.
    plan = _released(reviewed_release_sha256)

    # (2) The plan must describe the reviewed repaired bytes, and they must
    #     still be the bytes on disk.
    before = source_hashes()
    _require(before == plan["source_sha256"],
             "D013 v2 source map changed before nvcc lookup")
    _require(before[SOURCE_REL] == V2_REPAIRED_SOURCE_SHA256,
             "D013 v2 candidate is not the reviewed repaired source")
    anchors = plan.get("anchor_report") or []
    _require(anchors and all(row.get("applicable") is True for row in anchors),
             "not every reviewed mutation anchor is unique in the v2 candidate")

    # (3) Compiler lookup and version, only now that the release has passed.
    nvcc = shutil.which("nvcc")
    _require(nvcc is not None, "nvcc is unavailable")
    version = _run([nvcc, "--version"], "nvcc version",
                   timeout=VERSION_TIMEOUT_SECONDS)
    _require(version.returncode == 0 and version.stdout.strip(),
             "nvcc version failed: " + version.stderr[:240])

    # (4) The INDEPENDENT reference. Frozen, and the only judge below.
    from research.g9 import verify_stage2_cuda_d013_inactive_host_emulation as reference

    payload = reference.core.synthetic_payload()

    results = []
    clean_build = None
    with tempfile.TemporaryDirectory(prefix="g9-d013-v2-gpu-") as temporary:
        directory = Path(temporary)
        source = source_text()
        candidates = [(None, source), *selected_mutation_sources(source)]
        for mutation, candidate_text in candidates:
            label = "clean" if mutation is None else mutation.label
            candidate = directory / (label + ".cu")
            library = directory / (label + ".so")
            candidate.write_text(candidate_text, encoding="utf-8")
            candidate_sha = _sha(candidate.read_bytes())
            if mutation is not None:
                expected = next(row for row in plan["mutations"]
                                if row["label"] == mutation.label)
                _require(candidate_sha == expected["source_sha256"],
                         "mutated source differs from release: " + label)
            compiled = _run([nvcc, *GPU_COMPILE_FLAGS, "-I",
                             str((ROOT / SOURCE_REL).parent),
                             str(candidate), "-o", str(library)],
                            label + " compilation", timeout=COMPILE_TIMEOUT_SECONDS)
            _require(compiled.returncode == 0 and library.is_file(),
                     label + " CUDA ABI did not compile: "
                     + compiled.stderr[-400:])
            table_cases = (tuple(case for cases in DETECTION_CASES.values()
                                 for case in cases)
                           if mutation is None
                           else DETECTION_CASES[mutation.label])
            if mutation is None:
                table_cases += _clean_baseline_cases()
            case_results = []
            observations = []
            for case in table_cases:
                condition = case.condition
                if case.input_builder == "direct_tiny_positive":
                    # Bypasses the Python validator so the COMPILED exact
                    # positive-zero guard is what is actually tested.
                    accepts = reference.direct_abi_accepts_tiny_positive_inactive(
                        library, payload, reference.records_for)
                    detected = accepts
                    if mutation is None and accepts:
                        raise CorruptionQualificationError(
                            "clean D013 v2 CUDA build accepted the invalid "
                            "direct-ABI probe")
                    if mutation is not None and not detected:
                        raise CorruptionQualificationError(
                            "corrupted D013 v2 CUDA build was accepted: " + label)
                    case_results.append({"condition": condition,
                                         "input_builder": case.input_builder,
                                         "detected": detected})
                    continue
                records = (reference.tie_bearing_records(condition)
                           if case.input_builder == "tie_bearing"
                           else reference.noncommuting_records(condition))
                detected = False
                try:
                    observed = _compat.run_host_emulated_frame(
                        payload, records, condition, library, 64,
                        verified_release=_token(reviewed_release_sha256))
                    observations.append({
                        "condition": condition,
                        "input_builder": case.input_builder,
                        "counters": observed["counters"],
                        "result_sha256": observed["result_sha256"],
                        "content_sha256": observed["content_sha256"]})
                    agrees = reference.reference_agrees_with_result(
                        reference.core.build_domain(payload), records, condition,
                        observed)
                    raw_rejected = reference.reference_rejects_raw_counters(
                        library, payload, condition, records)
                    detected = (not agrees) or raw_rejected
                    if mutation is None and not agrees:
                        raise CorruptionQualificationError(
                            "clean D013 v2 CUDA build was rejected by the "
                            "independent reference")
                except _compat.D013InactiveError:
                    if mutation is None:
                        raise CorruptionQualificationError(
                            "clean D013 v2 CUDA build was rejected by the "
                            "independent reference")
                    detected = reference.reference_rejects_raw_counters(
                        library, payload, condition, records)
                case_results.append({"condition": condition,
                                     "input_builder": case.input_builder,
                                     "detected": detected})
                if mutation is not None and not detected:
                    raise CorruptionQualificationError(
                        "corrupted D013 v2 CUDA build was accepted: " + label)
            summary = {"source_sha256": candidate_sha,
                       "verdict": "ACCEPTED" if mutation is None else "REJECTED",
                       "reference_checks": len(table_cases),
                       "rejection_count": sum(bool(row["detected"])
                                              for row in case_results),
                       "detection_cases": case_results,
                       "observations": observations}
            if mutation is None:
                clean_build = summary
            else:
                results.append({"label": label, "category": mutation.category,
                                **summary})

    _require(source_hashes() == before,
             "D013 v2 source map changed during qualification")
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "mode": "non_scientific_d013_cuda_v2_corruption_qualification",
        "scientific_outputs": "intentionally absent",
        "stage2_inputs": "intentionally absent",
        "verdict": "clean_accepted_all_corruptions_rejected",
        "clean_build": clean_build,
        "execution_release_sha256": reviewed_release_sha256,
        "source_sha256": before,
        "compiler_flags": list(GPU_COMPILE_FLAGS),
        "nvcc_version": version.stdout.strip(),
        # THE SERIALIZATION BOUNDARY. The receipt stores the exact three-key ABI
        # representation of the verified token, not the live dataclass, so the
        # reviewed content_sha256 below can digest it and so every downstream
        # consumer (the launcher's digest, the ABI gate, WP3's dict guard) sees
        # the same object the runtime token denotes. _token_repr refuses rather
        # than degrades; it never drops a verified field.
        "verified_release_token": _token_repr(_token(reviewed_release_sha256)),
        "python_version": platform.python_version(),
        "mutations": results,
        "identity": {"backend": 1, "compiler_path": nvcc, "device_index": 0,
                     "python_version": platform.python_version()},
    }
    receipt["content_sha256"] = _v2_plan.contract.content_sha256(receipt)
    return receipt


def _token(reviewed_release_sha256: str):
    """Mint a v2 token through the reviewed v2 plan -- or refuse.

    Delegates to ``_v2_plan.verified_release_token``, which re-runs the whole
    ``_released`` gate first. There is no local construction of a
    ``VerifiedReleaseToken``: if the release is not owner-approved this raises
    before any value exists, so a caller can never receive a token that the
    v2 plan would not itself verify.
    """
    return _v2_plan.verified_release_token(reviewed_release_sha256)


def main() -> int:
    """Read-only: print the derived v2 plan. Compiles nothing, runs nothing."""
    print(json.dumps(_v2_plan.build_plan(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
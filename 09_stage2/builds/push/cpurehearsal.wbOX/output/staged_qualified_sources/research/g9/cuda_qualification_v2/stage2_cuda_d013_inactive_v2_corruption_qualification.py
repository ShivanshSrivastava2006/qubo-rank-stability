"""GATE 9 D013 CUDA v2 corruption plan -- CANDIDATE, NOT APPROVED, NOT ARMED.

This is the v2 counterpart of
``research/g9/cuda_qualification/stage2_cuda_d013_inactive_corruption_qualification.py``.
It exists because the reviewed candidate
``research/g9/cuda_qualification_v2/stage2_cuda_d013_inactive_v2.cu``
(sha256 ``953b7f15a14950d75536d72b074a7907dc06df13539b2ce3f4122cc427ab0f61``)
repairs the device-pointer defect, and the v1 plan hard-codes the v1 source path
at its ``SOURCE_REL``. Re-deriving this plan is required before the candidate
could ever be qualified; nothing here performs that qualification.

What this module does, and does not, do
---------------------------------------

It re-points the plan at the v2 ``.cu`` and re-derives the source map, the
detection table and the release-token proof. The nine mutations, their anchors,
their hazards and the detection cases are **imported from the frozen v1 plan
by absolute import** rather than copied: they target kernel-body properties that
the device-pointer fix does not touch, so re-typing them here would create a
second source of truth for the same reviewed table. Uniqueness of all nine
anchors inside the v2 candidate is re-checked at plan time and is load-bearing.

``owner_approved`` is **False** in the companion release draft
``GATE_9_D013_CUDA_V2_RELEASE_DRAFT.json``, so ``_released`` and
``_check_token`` below both REFUSE, and no token can be minted. The v1 token is
derived from the v1 release and the v1 source map; reusing or re-presenting it
against v2 is refused by construction, because both the release digest and the
source map that feed ``_token_proof`` are v2-specific.

Nothing in this module constructs a CUDA context, looks up ``nvcc``, executes a
kernel, reads production data, or performs scientific computation. It is a
read-only source/plan derivation plus a release gate that is currently closed.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Mapping

# FROZEN reviewed dependencies, imported by absolute path. These are NOT copied
# into this directory and NOT edited: the v1 release, the v1 bridge, the v1 plan
# and the host-emulation fixture all keep validating against their own bytes.
from research.g9.cuda_qualification import stage2_cuda_d013_inactive_corruption_qualification as _frozen_v1
from research.g9.cuda_qualification import stage2_cuda_execution_contract as contract


ROOT = Path(__file__).resolve().parents[3]

# --- the v2 bindings. These are the ONLY paths that differ from v1. ---------
SOURCE_REL = "research/g9/cuda_qualification_v2/stage2_cuda_d013_inactive_v2.cu"
BRIDGE_REL = "research/g9/cuda_qualification_v2/stage2_cuda_d013_inactive_v2_bridge.py"
PLAN_REL = "research/g9/cuda_qualification_v2/stage2_cuda_d013_inactive_v2_corruption_qualification.py"
FIXTURE_REL = "research/g9/verify_stage2_cuda_d013_inactive_host_emulation.py"
RELEASE_DRAFT_REL = "research/g9/cuda_qualification_v2/GATE_9_D013_CUDA_V2_RELEASE_DRAFT.json"

PLAN_SCHEMA = "decisions_os/g9_cuda_d013_inactive_v2_corruption_plan/v1"
RECEIPT_SCHEMA = "decisions_os/g9_cuda_d013_inactive_v2_corruption_receipt/v1"
RELEASE_SCHEMA = "decisions_os/g9_d013_cuda_v2_release_draft/v1"
# A SEPARATE permission variable. The v1 arming variable is deliberately not
# reused, so arming the v1 plan can never arm this one.
ALLOW_ENV = "G9_ALLOW_NONSCIENTIFIC_D013_CUDA_V2_CORRUPTION_QUALIFICATION"

SOURCE_RELS = (SOURCE_REL, BRIDGE_REL, PLAN_REL, FIXTURE_REL)

# The reviewed numerical flags, imported not copied. Identical to v1: the
# device-pointer repair changes launch plumbing only, never a numeric flag.
GPU_COMPILE_FLAGS = _frozen_v1.GPU_COMPILE_FLAGS
CLEAN_CONDITIONS = _frozen_v1.CLEAN_CONDITIONS

# The reviewed corruption tables, imported not copied.
MUTATIONS = _frozen_v1.MUTATIONS
DETECTION_CASES = _frozen_v1.DETECTION_CASES
REQUIRED_CATEGORIES = _frozen_v1.REQUIRED_CATEGORIES
REQUIRED_HAZARDS = _frozen_v1.REQUIRED_HAZARDS


class CorruptionQualificationError(RuntimeError):
    """The D013 v2 section-A path is unreleased, malformed or numerically unqualified."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CorruptionQualificationError(message)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_bound(relative: str) -> bytes:
    _require(relative.startswith("research/") and ".." not in relative.split("/"),
             "bound path is not a plain research path")
    path = ROOT / relative
    _require(path.is_file() and not path.is_symlink(), "bound file is missing: " + relative)
    return path.read_bytes()


# --- the reviewed tables, re-expressed as v2 plan functions ----------------

def canonical_detection_table() -> list[dict[str, object]]:
    """The reviewed detection table. Byte-identical to v1 by construction."""
    return [{"mutation": label,
             "cases": [{"condition": case.condition,
                        "input_builder": case.input_builder,
                        "expected": case.expected} for case in cases]}
            for label, cases in DETECTION_CASES.items()]


def detection_table_sha256() -> str:
    return _sha(json.dumps(canonical_detection_table(), sort_keys=True,
                           separators=(",", ":"), ensure_ascii=False).encode("utf-8"))


def source_text() -> str:
    """The v2 candidate source, read from its v2 path."""
    return _read_bound(SOURCE_REL).decode("utf-8")


def source_hashes() -> dict[str, str]:
    return {relative: _sha(_read_bound(relative)) for relative in SOURCE_RELS}


def compile_flags() -> tuple[str, ...]:
    """The host-emulation flags this v2 path REQUIRES; imported, not copied."""
    return _frozen_v1.compile_flags()


def mutated_sources(source: str) -> tuple[tuple[object, str], ...]:
    """Every mutation, each with an EXACTLY unique anchor in the v2 candidate.

    The guard set is the frozen v1 guard set, reached by construction. The one
    substantive v2 change is the target: anchors are matched against the v2
    candidate rather than the v1 source. All nine anchors are present exactly
    once in the v2 candidate, which is what keeps the reviewed plan applicable
    without re-authoring it. If a future edit to the candidate breaks that, this
    refuses rather than silently skipping a mutation.
    """
    _require(type(source) is str and source, "D013 v2 CUDA source is empty")
    _require(len({mutation.label for mutation in MUTATIONS}) == len(MUTATIONS),
             "mutation labels drift")
    _require({mutation.category for mutation in MUTATIONS} == REQUIRED_CATEGORIES,
             "required corruption categories drift")
    _require({mutation.hazard for mutation in MUTATIONS} == REQUIRED_HAZARDS,
             "required corruption hazards drift")
    result = []
    for mutation in MUTATIONS:
        count = source.count(mutation.old)
        _require(count == 1 and mutation.old != mutation.new,
                 "mutation anchor is missing or ambiguous in the v2 candidate: "
                 + mutation.label + " (occurrences=" + str(count) + ")")
        changed = source.replace(mutation.old, mutation.new, 1)
        _require(changed != source and changed.count(mutation.new) == 1,
                 "mutation did not change exactly one anchor: " + mutation.label)
        result.append((mutation, changed))
    _require(len({_sha(text.encode("utf-8")) for _, text in result}) == len(result),
             "two mutations produced the same source")
    return tuple(result)


def anchor_report(source: str | None = None) -> list[dict[str, object]]:
    """Per-anchor applicability against the v2 candidate, for review.

    Read-only. A non-unique or absent anchor is reported as NOT applicable with
    a reason; it is never reported as tested.
    """
    if source is None:
        source = source_text()
    report: list[dict[str, object]] = []
    for mutation in MUTATIONS:
        count = source.count(mutation.old)
        applicable = bool(mutation.old) and mutation.old != mutation.new and count == 1
        entry: dict[str, object] = {
            "label": mutation.label,
            "category": mutation.category,
            "hazard": mutation.hazard,
            "anchor_occurrences_in_candidate_v2": count,
            "anchor_is_unique": count == 1,
            "anchor_differs_from_replacement": mutation.old != mutation.new,
            "applicable": applicable,
        }
        if not applicable:
            entry["refusal_reason"] = (
                "anchor is empty or equals its replacement" if mutation.old == mutation.new
                else "anchor occurs " + str(count) + " times in the v2 candidate, required exactly 1")
        report.append(entry)
    return report


def build_plan() -> dict[str, object]:
    """Read-only v2 source/fixture plan. No nvcc lookup and no CUDA operation.

    The plan is self-describing about its own status: it is derived, not
    executed, and it does not claim the nine-mutation sweep has been run
    against the v2 candidate. That sweep is a separate owner-authorised step.
    """
    source = source_text()
    rows = [{"label": mutation.label, "category": mutation.category, "hazard": mutation.hazard,
             "source_sha256": _sha(text.encode("utf-8"))}
            for mutation, text in mutated_sources(source)]
    body: dict[str, object] = {
        "schema": PLAN_SCHEMA,
        "mode": "non_scientific_corruption_plan",
        "scientific_outputs": "intentionally absent",
        "stage2_inputs": "intentionally absent",
        "execution_release": "separate_owner_release_required",
        "conditions": list(_frozen_v1.d013.CONDITIONS),
        "inactive_families": {name: sorted(families)
                              for name, families in _frozen_v1.d013.INACTIVE_FAMILIES.items()},
        "retained_inactive_width": (_frozen_v1.d013.SECTOR_REGISTER_WIDTH
                                    + _frozen_v1.d013.BUDGET_REGISTER_WIDTH),
        "source_sha256": source_hashes(),
        "compile_flags": list(compile_flags()),
        "gpu_compile_flags": list(GPU_COMPILE_FLAGS),
        "mutations": rows,
        "detection_cases": canonical_detection_table(),
        "detection_cases_sha256": detection_table_sha256(),
        "anchor_report": anchor_report(source),
        "mutation_sweep_executed_against_v2": False,
        "reference": "frozen_independent_python_reference_in_the_host_emulation_fixture",
        "image_digest_status": "post_run_metadata_audit_required",
        "inherits_from": {
            "plan": "research/g9/cuda_qualification/"
                    "stage2_cuda_d013_inactive_corruption_qualification.py",
            "tables": "mutations, detection_cases, required_categories, required_hazards, "
                      "gpu_compile_flags, host compile_flags",
            "reused_by": "absolute import; not copied",
        },
    }
    body["content_sha256"] = contract.content_sha256(body)
    return body


# --- the release gate. Currently CLOSED, and it cannot be opened locally. ---

def _release_draft_path() -> Path:
    return ROOT / RELEASE_DRAFT_REL


def _load_release_draft(reviewed: str) -> dict[str, object]:
    """Load and fully validate the v2 release draft. Refuses while unapproved.

    Every condition here is a REFUSAL, not a warning. In particular
    ``owner_approved is True`` is required and is currently False, so this
    refuses no matter what the caller passes.
    """
    _require(os.environ.get("PYTHONDONTWRITEBYTECODE") == "1",
             "PYTHONDONTWRITEBYTECODE=1 is required")
    _require(type(reviewed) is str and len(reviewed) == 64 and
             all(character in "0123456789abcdef" for character in reviewed),
             "reviewed D013 v2 A-release SHA-256 is required")
    _require(os.environ.get(ALLOW_ENV) == "1",
             "separate D013 v2 A-execution permission is required; the v1 arming "
             "variable does not arm this path")
    path = _release_draft_path()
    _require(path.is_file() and not path.is_symlink(), "D013 v2 release draft is unavailable")
    raw = path.read_bytes()
    _require(_sha(raw) == reviewed, "D013 v2 release draft hash differs from the reviewed handoff")
    try:
        release = json.loads(raw)
    except ValueError as exc:
        raise CorruptionQualificationError("D013 v2 A-execution release is invalid JSON") from exc
    _require(type(release) is dict and raw == contract.canonical_bytes(release) + b"\n" and
             set(release) == {"schema", "owner_approved", "source_sha256",
                              "compile_flags", "mutations", "detection_cases",
                              "detection_cases_sha256"} and
             release.get("schema") == RELEASE_SCHEMA and
             release.get("owner_approved") is True,
             "D013 v2 release draft is not canonical and owner-approved")
    _require(release.get("compile_flags") == list(GPU_COMPILE_FLAGS) and
             release.get("mutations") == [
                 {"label": item.label, "category": item.category, "hazard": item.hazard}
                 for item in MUTATIONS] and
             release.get("detection_cases") == canonical_detection_table() and
             release.get("detection_cases_sha256") == detection_table_sha256(),
             "D013 v2 release draft flags or mutation list drift")
    plan = build_plan()
    _require(release.get("source_sha256") == plan["source_sha256"],
             "D013 v2 source map changed after release")
    return release


def _released(reviewed: str) -> dict[str, object]:
    """Verify the owner-approved v2 draft before any compiler or device lookup."""
    _load_release_draft(reviewed)
    return build_plan()


# --- the token. New derivation, v1 token structurally unusable here. --------

def _token_proof(release_sha256: str, source_map: Mapping[str, str]) -> str:
    """The v2 token proof.

    Identical in FORM to the frozen v1 proof, but every input is v2-specific:
    the release digest is the v2 release draft's, and ``source_map`` names the
    v2 ``.cu``, the v2 bridge, this v2 plan and the frozen fixture. A v1 token
    therefore cannot satisfy this check for two independent reasons -- its
    ``release_sha256`` names different bytes, and its ``source_map_sha256`` is
    the digest of a different four-entry map.
    """
    body = {"release_sha256": release_sha256, "source_sha256": dict(source_map)}
    return _sha(contract.canonical_bytes(body))


def source_map_sha256(source_map: Mapping[str, str]) -> str:
    return _sha(contract.canonical_bytes(dict(source_map)))


def _check_token(token: object) -> bool:
    """Verify a v2 release token. Returns False unless every check passes.

    Returns False, never raises, so a caller cannot turn a bad token into a
    crash path. Requires a canonical, owner-approved v2 release whose source
    map still matches the v2 files on disk, and whose proof is recomputed here.
    """
    if type(token) is _frozen_v1.VerifiedReleaseToken or (
            type(token) is dict and set(token) == {
                "release_sha256", "source_map_sha256", "proof_sha256"}):
        release_sha = token["release_sha256"] if type(token) is dict else token.release_sha256
        map_sha = token["source_map_sha256"] if type(token) is dict else token.source_map_sha256
        proof_sha = token["proof_sha256"] if type(token) is dict else token.proof_sha256
    else:
        return False
    if not (type(release_sha) is str and type(map_sha) is str and type(proof_sha) is str):
        return False
    path = _release_draft_path()
    if not path.is_file() or path.is_symlink():
        return False
    raw = path.read_bytes()
    try:
        release = json.loads(raw)
    except ValueError:
        return False
    if type(release) is not dict:
        return False
    if (_sha(raw) != release_sha or release.get("owner_approved") is not True or
            raw != contract.canonical_bytes(release) + b"\n" or
            set(release) != {"schema", "owner_approved", "source_sha256",
                             "compile_flags", "mutations", "detection_cases",
                             "detection_cases_sha256"} or
            release.get("schema") != RELEASE_SCHEMA or
            release.get("compile_flags") != list(GPU_COMPILE_FLAGS) or
            release.get("mutations") != [
                {"label": item.label, "category": item.category, "hazard": item.hazard}
                for item in MUTATIONS] or
            release.get("detection_cases") != canonical_detection_table() or
            release.get("detection_cases_sha256") != detection_table_sha256()):
        return False
    try:
        current = source_hashes()
    except CorruptionQualificationError:
        return False
    if release.get("source_sha256") != current:
        return False
    return (map_sha == source_map_sha256(current) and
            proof_sha == _token_proof(release_sha, current))


def verified_release_token(reviewed_release_sha256: str) -> _frozen_v1.VerifiedReleaseToken:
    """Mint a v2 token. Refuses unless the v2 release is owner-approved.

    Not callable in the current state: the companion release draft carries
    ``owner_approved: false``, so ``_load_release_draft`` refuses first.
    """
    _released(reviewed_release_sha256)
    source_map = source_hashes()
    return _frozen_v1.VerifiedReleaseToken(
        reviewed_release_sha256, source_map_sha256(source_map),
        _token_proof(reviewed_release_sha256, source_map))


__all__ = [
    "CorruptionQualificationError", "ALLOW_ENV", "SOURCE_REL", "BRIDGE_REL", "PLAN_REL",
    "FIXTURE_REL", "RELEASE_DRAFT_REL", "PLAN_SCHEMA", "RECEIPT_SCHEMA", "RELEASE_SCHEMA",
    "SOURCE_RELS", "GPU_COMPILE_FLAGS", "CLEAN_CONDITIONS", "MUTATIONS", "DETECTION_CASES",
    "canonical_detection_table", "detection_table_sha256", "source_text", "source_hashes",
    "compile_flags", "mutated_sources", "anchor_report", "build_plan", "_token_proof",
    "source_map_sha256", "_check_token", "verified_release_token",
]

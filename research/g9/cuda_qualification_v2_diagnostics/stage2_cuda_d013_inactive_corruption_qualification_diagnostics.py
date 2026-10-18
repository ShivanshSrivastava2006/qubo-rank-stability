"""D013 corruption-qualification harness with guard-preserving refusal diagnostics.

**DRAFT DIAGNOSTIC CANDIDATE -- UNROUTED. NOT OWNER-APPROVED. NOT T4-QUALIFIED.**

This is a *new versioned module* under
``research/g9/cuda_qualification_v2_diagnostics/``. The frozen D013 v1 plan at
``research/g9/cuda_qualification/stage2_cuda_d013_inactive_corruption_qualification.py``
(sha256 ``ab0c9060...c5c``) is **not edited** and remains the only approved
plan. This module exists to demonstrate, offline and against synthetic inputs,
the exact diagnostic behaviour that a future owner-reviewed release would need,
and to prove the change does not weaken any guard.

What is preserved from v1, verbatim in behaviour:

* the release gate ``_released`` / ``_check_token`` and its token proof;
* the plan, the nine mutations, the detection cases and their ordering;
* the failure order inside ``_run_case`` -- ``run_host_emulated_frame`` first,
  then ``reference_agrees_with_result``, then ``reference_rejects_raw_counters``;
* the fail-closed disposition: any clean-case refusal or disagreement raises a
  typed ``CorruptionQualificationError`` out of the loop;
* the ``direct_tiny_positive`` refusal probe handling;
* the post-run source-map re-check.

What is changed, and only this:

1. The clean-case ``except d013.D013InactiveError`` handler binds ``as exc``
   and routes through :func:`d013_d013_refusal_diagnostics
   .raise_clean_case_refusal`, which re-raises the **same typed refusal**
   (``CorruptionQualificationError``) *chained from* ``exc``. The nested reason,
   exception type, exception chain and case/stage identity are attached as a
   bounded, sanitized ``refusal_diagnostic`` attribute. Nothing is caught and
   continued; nothing is replaced by a success value; no dependent step runs.
2. The two branches no longer share one string. v1 lines 573-574 and 575-578
   both raised the identical "rejected by the independent reference" text, which
   is why the preserved T4 traceback could not distinguish a real numeric
   disagreement from an ordinary D013 refusal. They are now separate constants:
   ``NUMERIC_DISAGREEMENT_MESSAGE`` (the reference ran and disagreed -- truthful,
   v1 wording kept) and ``REFUSAL_MESSAGE`` (the compiled core refused before the
   reference was consulted). Both are asserted distinct at import time.
3. ``_run_case`` is factored out of ``_run_qualification`` verbatim in logic so
   the case-level behaviour is unit-testable with injected fakes, with no nvcc,
   no CUDA and no scientific computation. The real ``run_qualification`` drives
   exactly this function, so the tested path is the shipped path.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from typing import Callable, NamedTuple

from research.g9.cuda_qualification import stage2_cuda_d013_inactive as d013
from research.g9.cuda_qualification import stage2_cuda_core_qualification as core_clean
from research.g9.cuda_qualification import stage2_cuda_execution_contract as contract
from research.g9.cuda_qualification import stage2_cuda_d013_inactive_corruption_qualification as v1
from research.g9.cuda_qualification_v2_diagnostics import d013_refusal_diagnostics as diag


HARNESS_VERSION = "d013-corruption-qualification-diagnostics/v2.1"
DIAGNOSTIC_NOTICE = "UNROUTED_DRAFT_NOT_OWNER_APPROVED_NOT_T4_QUALIFIED"

#: This harness binds the v1 source map on purpose, because a v2 source map
#: would have to come from a new owner-reviewed release that does not exist.
#: The diagnostic behaviour under test is source-map-independent.
SOURCE_REL = v1.SOURCE_REL
BRIDGE_REL = v1.BRIDGE_REL
PLAN_REL = "research/g9/cuda_qualification_v2_diagnostics/stage2_cuda_d013_inactive_corruption_qualification_diagnostics.py"
FIXTURE_REL = v1.FIXTURE_REL
RELEASE_DRAFT_REL = v1.RELEASE_DRAFT_REL
PLAN_SCHEMA = "decisions_os/g9_cuda_d013_inactive_corruption_plan_diagnostics/v1"
RECEIPT_SCHEMA = "decisions_os/g9_cuda_d013_inactive_corruption_receipt_diagnostics/v1"
ALLOW_ENV = v1.ALLOW_ENV

# Inherited unchanged from the reviewed v1 plan. Re-derived rather than copied
# so the two can never silently diverge.
MUTATIONS = v1.MUTATIONS
DETECTION_CASES = v1.DETECTION_CASES
CLEAN_CONDITIONS = v1.CLEAN_CONDITIONS
REQUIRED_CATEGORIES = v1.REQUIRED_CATEGORIES
REQUIRED_HAZARDS = v1.REQUIRED_HAZARDS
GPU_COMPILE_FLAGS = (*core_clean.COMPILE_FLAGS, "-shared")

CorruptionQualificationError = v1.CorruptionQualificationError
NUMERIC_DISAGREEMENT_MESSAGE = diag.NUMERIC_DISAGREEMENT_MESSAGE
REFUSAL_MESSAGE = diag.REFUSAL_MESSAGE

SOURCE_RELS = (SOURCE_REL, BRIDGE_REL, PLAN_REL, FIXTURE_REL)
ROOT = v1.ROOT


class CaseOutcome(NamedTuple):
    """Result of one detection case. Mirrors v1's ``case_results`` row."""

    condition: str
    input_builder: str
    detected: bool
    row: dict[str, object]
    observations: list[dict[str, object]]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CorruptionQualificationError(message)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_bound(relative: str) -> bytes:
    return v1._read_bound(relative)


def source_text() -> str:
    return _read_bound(SOURCE_REL).decode("utf-8")


def source_hashes() -> dict[str, str]:
    return {relative: _sha(_read_bound(relative)) for relative in SOURCE_RELS}


def compile_flags() -> tuple[str, ...]:
    return ("-x", "c++", "-std=c++17", "-O0", "-shared", "-fPIC", "-Wall", "-Wextra",
            "-Wno-unknown-pragmas", "-ffp-contract=off", "-fno-fast-math")


def build_plan() -> dict[str, object]:
    """Read-only plan. Identical content to v1's plan, different schema id."""
    plan = v1.build_plan()
    return {**plan,
            "schema": PLAN_SCHEMA,
            "harness_version": HARNESS_VERSION,
            "routing_status": DIAGNOSTIC_NOTICE,
            "refusal_diagnostics": {
                "nested_reason_retained": True,
                "nested_reason_max_chars": diag.MAX_REASON_CHARS,
                "raw_scan_limit": diag.RAW_SCAN_LIMIT,
                "case_identity_retained": True,
                "exception_chained": True,
                "refusal_type": CorruptionQualificationError.__name__,
                "numeric_disagreement_message": NUMERIC_DISAGREEMENT_MESSAGE,
                "refusal_message": REFUSAL_MESSAGE,
                "messages_distinct": NUMERIC_DISAGREEMENT_MESSAGE != REFUSAL_MESSAGE,
            }}


def _released(reviewed: object) -> dict[str, object]:
    """Same release gate as v1. Reached only with an explicit reviewed digest."""
    return v1._released(reviewed)


def _run(command: list[str], label: str, *, timeout: int) -> subprocess.CompletedProcess[str]:
    return v1._run(command, label, timeout=timeout)


def _check_token(token: object) -> bool:
    return v1._check_token(token)


VerifiedReleaseToken = v1.VerifiedReleaseToken


def run_case(case: object, *, payload: object, library: object, token: object,
             mutation: object, case_index: object, mutate_label: str,
             frame: Callable[..., object],
             direct_probe: Callable[..., bool], reference_agrees: Callable[..., bool],
             raw_counter_probe: Callable[..., bool],
             ) -> CaseOutcome:
    """Run one detection case. The logic is v1's, extracted verbatim.

    Order of operations, unchanged from v1 lines 541-585:

    1. ``direct_tiny_positive`` -> refusal-probe branch, ``continue``;
    2. build records;
    3. ``run_host_emulated_frame`` inside the ``try``;
    4. append ``observations``;
    5. ``reference_agrees_with_result``;
    6. ``reference_rejects_raw_counters``;
    7. ``detected = (not agrees) or raw_rejected``;
    8. clean case: ``not agrees`` -> typed refusal (numeric disagreement);
    9. ``except d013.D013InactiveError`` -> clean: typed refusal chained from
       ``exc`` WITH diagnostics; mutation: re-probe raw counters.

    Steps 3-9 are byte-for-byte the same *decisions* as v1. Only the handler's
    message and its carried evidence changed.

    ``frame`` is injected purely so the case logic can be exercised offline with
    synthetic fakes. :func:`run_qualification` passes the real
    ``d013.run_host_emulated_frame``; nothing else may.
    """
    condition = case.condition
    input_builder = case.input_builder

    if input_builder == "direct_tiny_positive":
        accepts = direct_probe(library, payload)
        detected = accepts
        if mutation is None and accepts:
            raise CorruptionQualificationError(
                "clean D013 CUDA build accepted the invalid direct-ABI probe")
        if mutation is not None and not detected:
            raise CorruptionQualificationError(
                "corrupted D013 CUDA build was accepted: " + mutate_label)
        row = {"condition": condition, "input_builder": input_builder,
               "detected": detected}
        return CaseOutcome(condition, input_builder, detected, row, [])

    records = ("tie_bearing" if input_builder == "tie_bearing" else "noncommuting")
    observations: list[dict[str, object]] = []
    detected = False
    try:
        observed = frame(payload, records, condition, library, 64, verified_release=token)
        observations.append({"condition": condition, "input_builder": input_builder,
                             "counters": observed["counters"],
                             "result_sha256": observed["result_sha256"],
                             "content_sha256": observed["content_sha256"]})
        agrees = reference_agrees(observed)
        raw_rejected = raw_counter_probe(library, payload, condition, records)
        detected = (not agrees) or raw_rejected
        if mutation is None and not agrees:
            # Truthful, distinct, and still a hard refusal. v1 wording preserved.
            raise CorruptionQualificationError(NUMERIC_DISAGREEMENT_MESSAGE)
    except d013.D013InactiveError as exc:
        if mutation is None:
            # THE ONLY BEHAVIOURAL CHANGE. Same typed refusal, still raised, still
            # aborting; but the nested reason survives, bounded and sanitized,
            # and the reference-disagreement claim is no longer made falsely.
            diag.raise_clean_case_refusal(
                exc, case=mutate_label,
                stage="clean_case_run_host_emulated_frame",
                condition=condition, input_builder=input_builder,
                mutation_label=None, case_index=case_index)
        # v1 line 579-580, unchanged: a mutation's refusal is not a refusal, the
        # raw-counter probe decides whether the corruption was detected.
        detected = raw_counter_probe(library, payload, condition, records)
    # v1 lines 583-585, unchanged and load-bearing: an undetected mutation is a
    # refusal, not a detection. This guard fires for the post-catch path too.
    if mutation is not None and not detected:
        raise CorruptionQualificationError(
            "corrupted D013 CUDA build was accepted: " + mutate_label)
    row = {"condition": condition, "input_builder": input_builder, "detected": detected}
    return CaseOutcome(condition, input_builder, detected, row, observations)


def _clean_case_table(mutation: object) -> tuple[object, ...]:
    """The exact v1 table for a candidate: full flattened table for clean, else the
    mutation's own cases, plus the four frozen clean conditions when clean."""
    if mutation is not None:
        return DETECTION_CASES[mutation.label]
    table = tuple(case for cases in DETECTION_CASES.values() for case in cases)
    return table + tuple(v1.DetectionCase(condition, "noncommuting", "mismatch")
                        for condition in CLEAN_CONDITIONS)


def _run_command_reference(reference: object) -> tuple[Callable, Callable, Callable]:
    return (reference.direct_abi_accepts_tiny_positive_inactive,
            reference.reference_agrees_with_result,
            reference.reference_rejects_raw_counters)


def run_qualification(reviewed_release_sha256: str) -> dict[str, object]:
    """Compile and qualify clean and mutated D013 ABIs with diagnostics enabled.

    The gate, compile, mutation-selection and receipt logic is v1's. The case
    loop body is :func:`run_case`.
    """
    plan = _released(reviewed_release_sha256)
    before = source_hashes()
    _require(before == plan["source_sha256"], "D013 source map changed before nvcc lookup")
    nvcc = shutil.which("nvcc")
    _require(nvcc is not None, "nvcc is unavailable")
    version = _run([nvcc, "--version"], "nvcc version", timeout=30)
    _require(version.returncode == 0 and version.stdout.strip(),
             "nvcc version failed: " + version.stderr[:240])
    from research.g9 import verify_stage2_cuda_d013_inactive_host_emulation as reference

    token = VerifiedReleaseToken(reviewed_release_sha256,
                                 _sha(contract.canonical_bytes(before)),
                                 v1._token_proof(reviewed_release_sha256,
                                                 json.loads((ROOT / RELEASE_DRAFT_REL)
                                                            .read_bytes())["source_sha256"]))
    payload = reference.core.synthetic_payload()
    results: list[dict[str, object]] = []
    clean_build: dict[str, object] | None = None
    with tempfile.TemporaryDirectory(prefix="g9-d013-diag-A-") as temporary:
        directory = Path(temporary)
        source = source_text()
        mutation_rows = v1.selected_mutation_sources(source)
        candidates = [(None, source), *mutation_rows]
        for mutation, candidate_text in candidates:
            label = "clean" if mutation is None else mutation.label
            candidate = directory / (label + ".cu")
            library = directory / (label + ".so")
            candidate.write_text(candidate_text, encoding="utf-8")
            candidate_sha = _sha(candidate.read_bytes())
            if mutation is not None:
                expected = next(row for row in plan["mutations"] if row["label"] == mutation.label)
                _require(candidate_sha == expected["source_sha256"],
                         "mutated source differs from release: " + label)
            compiled = _run([nvcc, *GPU_COMPILE_FLAGS, "-I", str((ROOT / SOURCE_REL).parent),
                             str(candidate), "-o", str(library)],
                            label + " compilation", timeout=600)
            _require(compiled.returncode == 0 and library.is_file(),
                     label + " CUDA ABI did not compile")
            table_cases = _clean_case_table(mutation)
            case_results: list[dict[str, object]] = []
            observations: list[dict[str, object]] = []
            direct_probe, reference_agrees, raw_counter_probe = _run_command_reference(reference)
            for case_index, case in enumerate(table_cases):
                outcome = run_case(
                    case, payload=payload, library=library, token=token,
                    mutation=mutation, case_index=case_index, mutate_label=label,
                    frame=d013.run_host_emulated_frame,
                    direct_probe=direct_probe, reference_agrees=reference_agrees,
                    raw_counter_probe=raw_counter_probe)
                case_results.append(outcome.row)
                observations.extend(outcome.observations)
            summary = {"source_sha256": candidate_sha,
                       "verdict": "ACCEPTED" if mutation is None else "REJECTED",
                       "reference_checks": len(table_cases),
                       "rejection_count": sum(bool(row["detected"]) for row in case_results),
                       "detection_cases": case_results,
                       "observations": observations}
            if mutation is None:
                clean_build = summary
            else:
                results.append({"label": label, "category": mutation.category,
                                **summary})
    _require(source_hashes() == before, "D013 source map changed during qualification")
    receipt: dict[str, object] = {
        "schema": RECEIPT_SCHEMA,
        "mode": "non_scientific_d013_cuda_corruption_qualification_diagnostics",
        "harness_version": HARNESS_VERSION,
        "routing_status": DIAGNOSTIC_NOTICE,
        "scientific_outputs": "intentionally absent",
        "stage2_inputs": "intentionally absent",
        "verdict": "clean_accepted_all_corruptions_rejected",
        "clean_build": clean_build,
        "execution_release_sha256": reviewed_release_sha256,
        "source_sha256": before,
        "compiler_flags": list(GPU_COMPILE_FLAGS),
        "nvcc_version": version.stdout.strip(),
        "verified_release_token": {
            "release_sha256": reviewed_release_sha256,
            "source_map_sha256": _sha(contract.canonical_bytes(before)),
            "proof_sha256": v1._token_proof(reviewed_release_sha256, before),
        },
        "python_version": platform.python_version(),
        "mutations": results,
        "identity": {"backend": 1, "compiler_path": nvcc,
                     "device_index": 0,
                     "python_version": platform.python_version()},
    }
    receipt["content_sha256"] = contract.content_sha256(receipt)
    return receipt


def main() -> int:
    plan = build_plan()
    print(json.dumps(plan, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
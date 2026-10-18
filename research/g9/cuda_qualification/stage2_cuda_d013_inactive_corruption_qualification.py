"""Section-A corruption qualification PLAN for the D013 `+0.0` additive CUDA path.

The qualified v1 release (``research/decisions/
GATE_9_CUDA_CORE_CORRUPTION_QUALIFICATION_RELEASE.json``) covers twelve files and
does NOT cover this path.  The owner decision
``GATE_9_WP0_D013_CUDA_PATH_AND_IDENTITY_SCOPE_OWNER_DECISION.md`` decision 1 is
explicit that the `+0.0` capability "needs its own section-A corruption
qualification, including new `+0.0` and slack-register corruption cases", and
that qualification is planned for the WP7 Kaggle session. This module builds
the read-only plan and carries the release-gated GPU execution path. It refuses
before compiler lookup unless an exact owner-approved release exists.

Every mutation below has an exact, unique anchor in
``stage2_cuda_d013_inactive.cu`` and targets one of the two hazards this path
exists to handle, or one of the frozen rules it must preserve:

* ``inactive_term_becomes_negative_zero``  -- the `-0.0` sign hazard, reached by
  forming the inactive family's product instead of skipping it.
* ``inactive_coefficient_becomes_tiny_positive`` -- an inactive family given a
  mathematically active coefficient, which would silently make its register
  non-degenerate.
* ``wrong_family_inactivated`` -- the condition mask applied to the wrong
  family, so a family that should be active is skipped and vice versa.
* ``register_enumerated_instead_of_symbolic`` -- the `+0.0` family's retained
  register ENUMERATED rather than accounted for as the factor 2^w, which is the
  2^19 domain explosion the owner decision forbids.
* ``accumulation_order_swapped`` -- the frozen D015 order f, P_card, sector
  j=1..4, budget rearranged.
* ``inactive_width_dropped`` -- `w` reported as 0, so `|T_E|` loses its factor.
* ``base_total_claimed_as_lift_total`` -- `|T_E|` reported as the base alone,
  dropping the symbolic factor from the reported value.
* ``first_seen_minimum_weakened`` -- the strict first-seen segment merge
  weakened, so a later equal segment overwrites the canonical minimum.
* ``inactive_term_negative_zero_reaches_the_stream`` -- a `-0.0` injected into
  the energy stream, which only the sign counter can detect.

In host emulation the reference that rejects them is the SLOW INDEPENDENT
PYTHON REFERENCE in ``verify_stage2_cuda_d013_inactive_host_emulation.py``,
which recomputes each condition from the owner-decided spec by direct per-family
sums over the small decoded domain. The separately validated WP6 evaluator is
also used by the cross-check fixture.
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
from typing import NamedTuple

from research.g9.cuda_qualification import stage2_cuda_d013_inactive as d013
from research.g9.cuda_qualification import stage2_cuda_core_qualification as core_clean
from research.g9.cuda_qualification import stage2_cuda_execution_contract as contract


ROOT = Path(__file__).resolve().parents[3]
SOURCE_REL = "research/g9/cuda_qualification/stage2_cuda_d013_inactive.cu"
BRIDGE_REL = "research/g9/cuda_qualification/stage2_cuda_d013_inactive.py"
PLAN_REL = "research/g9/cuda_qualification/stage2_cuda_d013_inactive_corruption_qualification.py"
FIXTURE_REL = "research/g9/verify_stage2_cuda_d013_inactive_host_emulation.py"
RELEASE_DRAFT_REL = "research/g9/cuda_qualification/GATE_9_D013_CUDA_RELEASE_DRAFT.json"
PLAN_SCHEMA = "decisions_os/g9_cuda_d013_inactive_corruption_plan/v1"
RECEIPT_SCHEMA = "decisions_os/g9_cuda_d013_inactive_corruption_receipt/v1"
ALLOW_ENV = "G9_ALLOW_NONSCIENTIFIC_D013_CUDA_CORRUPTION_QUALIFICATION"

# The additive path and the host files that exercise it. This map is separate
# from, and does not extend, the qualified v1 release.
SOURCE_RELS = (SOURCE_REL, BRIDGE_REL, PLAN_REL, FIXTURE_REL)
# Keep this identical to the v1 runner's reviewed numerical flags, with only
# the ABI shared-library switch added.
GPU_COMPILE_FLAGS = (*core_clean.COMPILE_FLAGS, "-shared")
CLEAN_CONDITIONS = ("C", "CB", "CS", "CSB")


class CorruptionQualificationError(RuntimeError):
    """The D013 section-A path is unreleased, malformed or numerically unqualified."""


class Mutation(NamedTuple):
    label: str
    category: str
    hazard: str
    old: str
    new: str


class DetectionCase(NamedTuple):
    condition: str
    input_builder: str
    expected: str


# This is the single reviewed detection plan used by the host qualification
# and the release-gated GPU runner.  Builders name functions in the independent
# host reference module; "mismatch" means compare all numerical output against
# its independent reference, while "refusal" means the clean ABI must refuse
# the invalid direct-ABI probe and the mutant is detected if it accepts it.
DETECTION_CASES = {
    "inactive_term_becomes_negative_zero": (DetectionCase("C", "noncommuting", "mismatch"),),
    "inactive_coefficient_becomes_tiny_positive": (
        DetectionCase("C", "direct_tiny_positive", "refusal"),),
    "wrong_family_inactivated": (
        DetectionCase("CB", "noncommuting", "mismatch"),),
    "register_enumerated_instead_of_symbolic": (
        DetectionCase("C", "noncommuting", "mismatch"),),
    "accumulation_order_swapped": (
        DetectionCase("CSB", "noncommuting", "mismatch"),),
    "inactive_width_dropped": (DetectionCase("C", "noncommuting", "mismatch"),),
    "base_total_claimed_as_lift_total": (DetectionCase("C", "noncommuting", "mismatch"),),
    "first_seen_minimum_weakened": (
        DetectionCase("CSB", "tie_bearing", "mismatch"),),
    "inactive_term_negative_zero_reaches_the_stream": (
        DetectionCase("C", "noncommuting", "mismatch"),),
}


def canonical_detection_table() -> list[dict[str, object]]:
    return [{"mutation": label,
             "cases": [{"condition": case.condition,
                        "input_builder": case.input_builder,
                        "expected": case.expected} for case in cases]}
            for label, cases in DETECTION_CASES.items()]


def detection_table_sha256() -> str:
    return _sha(json.dumps(canonical_detection_table(), sort_keys=True,
                           separators=(",", ":"), ensure_ascii=False).encode("utf-8"))


@dataclass(frozen=True)
class VerifiedReleaseToken:
    release_sha256: str
    source_map_sha256: str
    proof_sha256: str


def _token_proof(release_sha256: str, source_map: dict[str, str]) -> str:
    body = {"release_sha256": release_sha256, "source_sha256": source_map}
    return _sha(contract.canonical_bytes(body))


# Each mutation targets a DIFFERENT frozen property, and every one is expected
# to compile: a compiler refusal is not counted as numerical rejection, and the
# host-emulation reference must reject the resulting numbers.
MUTATIONS = (
    Mutation(
        "inactive_term_becomes_negative_zero", "inactive_zero",
        "sign_of_the_inactive_term",
        # An inactive family must report EXACTLY the positive zero, bit pattern
        # 0. This mutation makes the reported term `-0.0` instead, which is the
        # bit pattern D015 section 1.4 forbids. It is applied to the value the
        # path actually SUMS into the accumulator, not only to a probe, so a
        # variant that reports the sign and then sums it is caught too.
        "  if (is_sector ? !sector_active : !budget_active) return +0.0;",
        "  if (is_sector ? !sector_active : !budget_active) return -0.0;"),
    Mutation(
        "inactive_coefficient_becomes_tiny_positive", "inactive_coefficient",
        "coefficient_must_be_exactly_positive_zero",
        # An inactive family's coefficient must be the POSITIVE ZERO, bit
        # pattern 0. This mutation accepts any non-negative value, so a tiny
        # positive coefficient would pass validation.
        "  return double_to_word(value) == 0ULL;",
        "  return !(value < 0.0) && !value_is_nonfinite(value);"),
    Mutation(
        "wrong_family_inactivated", "condition_mapping",
        "active_and_inactive_families_must_not_be_swapped",
        # `C` inactivates sector+budget, `CB` inactivates sector, `CS`
        # inactivates budget. This mutation swaps the activity bits, so a
        # condition's families are exchanged.
        "  const bool sector_active = (condition & G9_D013_ACTIVITY_SECTOR) != 0u;\n"
        "  const bool budget_active = (condition & G9_D013_ACTIVITY_BUDGET) != 0u;",
        "  const bool sector_active = (condition & G9_D013_ACTIVITY_BUDGET) != 0u;\n"
        "  const bool budget_active = (condition & G9_D013_ACTIVITY_SECTOR) != 0u;"),
    Mutation(
        "register_enumerated_instead_of_symbolic", "slack_register_handling",
        "inactive_register_must_not_be_enumerated",
        # The retained INACTIVE register must be SKIPPED: never visited, never
        # enumerated, and its 2^w factor applied once, arithmetically, as the
        # symbolic |T_E| factor. This mutation drops the skip, so the inactive
        # register is ENUMERATED like an active one -- visited, its minimiser
        # count folded into the base multiplicity, and its penalty slot
        # written. That is exactly the 2^19 domain explosion the owner decision
        # forbids, and it moves both the instrumented visit counter and
        # |T_E|'s enumerated base.
        "    if (register_activity[index * kRegisterCount + r] == G9_D013_REGISTER_NONE) {\n"
        "      // INACTIVE: never visited, so never enumerated, never counted, and its\n"
        "      // penalty slot is left untouched rather than being written with a value\n"
        "      // the balanced transcript must not read.\n"
        "      continue;\n"
        "    }",
        "    if (register_activity[index * kRegisterCount + r] == G9_D013_REGISTER_NONE) {\n"
        "      // CORRUPTION: the retained inactive register is ENUMERATED here\n"
        "      // instead of being accounted for symbolically as the factor 2^w.\n"
        "    }"),
    Mutation(
        "accumulation_order_swapped", "accumulation_order",
        "frozen_f015_accumulation_order",
        # The frozen D015 order is f, P_card, sector j=1..4, budget LAST. This
        # mutation hoists the budget family's term to the FRONT of the
        # accumulator, before the sector j=1..4 terms, which is a real
        # non-associativity defect: `+0.0 * P_E_budget` is no longer
        # `(f + P_card + sum_sector) + P_E_budget`. Floating-point addition is
        # not associative, so this changes the per-state energy bits and hence
        # the minimum. It is a genuine corruption, not a re-spelling.
        "  for (std::uint32_t s = 0; s < kSectorCount; ++s) {\n"
        "    if ((condition & G9_D013_ACTIVITY_SECTOR) == 0u) continue;  // P_E_sector[j] = +0.0\n"
        "    const double linear = coefficients.sector_linear * sector_residual[s];\n"
        "    const double quadratic = coefficients.sector_quadratic * (sector_residual[s] * sector_residual[s]);\n"
        "    h_acc = h_acc + ((-linear) + quadratic);\n"
        "  }\n"
        "  if ((condition & G9_D013_ACTIVITY_BUDGET) == 0u) return h_acc;  // P_E_budget = +0.0\n"
        "  const double linear = coefficients.budget_linear * budget_residual;\n"
        "  const double quadratic = coefficients.budget_quadratic * (budget_residual * budget_residual);\n"
        "  return h_acc + ((-linear) + quadratic);",
        "  if ((condition & G9_D013_ACTIVITY_BUDGET) != 0u) {\n"
        "    const double b_linear = coefficients.budget_linear * budget_residual;\n"
        "    const double b_quadratic = coefficients.budget_quadratic * (budget_residual * budget_residual);\n"
        "    h_acc = h_acc + ((-b_linear) + b_quadratic);  // CORRUPTION: budget hoisted to front\n"
        "  }\n"
        "  for (std::uint32_t s = 0; s < kSectorCount; ++s) {\n"
        "    if ((condition & G9_D013_ACTIVITY_SECTOR) == 0u) continue;  // P_E_sector[j] = +0.0\n"
        "    const double linear = coefficients.sector_linear * sector_residual[s];\n"
        "    const double quadratic = coefficients.sector_quadratic * (sector_residual[s] * sector_residual[s]);\n"
        "    h_acc = h_acc + ((-linear) + quadratic);\n"
        "  }\n"
        "  return h_acc;"),
    Mutation(
        "inactive_width_dropped", "symbolic_factor",
        "T_E_must_carry_the_retained_inactive_width",
        # `w` is the total retained inactive register width: 8 for the sector
        # family, 11 for budget. This mutation always reports 0.
        "  if ((condition & G9_D013_ACTIVITY_SECTOR) == 0u) w += kD013InactiveSectorWidth;",
        "  if ((condition & G9_D013_ACTIVITY_SECTOR) == 0u) w += 0u;"),
    Mutation(
        "base_total_claimed_as_lift_total", "symbolic_factor",
        "T_E_exact_must_equal_base_times_two_to_the_w",
        # |T_E| = base * 2^w. This mutation reports the base alone.
        "  out->counters.lift_total_exact = base_total * (1ULL << width);",
        "  out->counters.lift_total_exact = base_total;"),
    Mutation(
        "first_seen_minimum_weakened", "index_order",
        "canonical_strict_first_seen_minimum",
        # The segment merge must report the STRICT minimum, keeping the FIRST
        # segment that attains it. This mutation drops the `!merged` seed and
        # keeps only the non-strict `<=`, so a LATER segment that merely EQUALS
        # the running minimum overwrites the winner. It is a weakening of the
        # strict first-seen rule: a later equal segment is accepted where the
        # frozen rule requires the earlier one to stand.
        "    if (!merged || segment_value[segment] < minimum) {",
        "    if (true || segment_value[segment] <= minimum) {"),
    Mutation(
        "inactive_term_negative_zero_reaches_the_stream", "nonfinite_and_sign_output",
        "a_minus_zero_energy_must_be_counted",
        # A `-0.0` in the energy stream is a hard defect, and the counter that
        # reports it is the ONLY thing that can reveal it: `-0.0` compares equal
        # to `+0.0` as a float, so no minimum or index comparison can see it.
        # On the GOOD kernel the counter is vacuously zero, which would let a
        # corruption here qualify for the wrong reason, so this mutation
        # INJECTS a `-0.0` into the stream and leaves the honest per-word count
        # in place. The reference must then REJECT the run on the non-zero
        # counter alone, which is exactly the property the decision relies on:
        # a sign defect in the stream is reported, never hidden.
        "      for (std::uint64_t index = 0; index < word_count; ++index) {\n"
        "        if (double_to_word(energies[index]) == 0x8000000000000000ULL) {\n"
        "          out->counters.negative_zero_energies += 1ULL;\n"
        "        }\n"
        "      }",
        "      energies[0] = -0.0;  // CORRUPTION: a -0.0 injected into the stream\n"
        "      for (std::uint64_t index = 0; index < word_count; ++index) {\n"
        "        if (double_to_word(energies[index]) == 0x8000000000000000ULL) {\n"
        "          out->counters.negative_zero_energies += 1ULL;\n"
        "        }\n"
        "      }"),
)

REQUIRED_CATEGORIES = frozenset({
    "inactive_zero", "inactive_coefficient", "condition_mapping",
    "slack_register_handling", "accumulation_order", "symbolic_factor",
    "index_order", "nonfinite_and_sign_output",
})
REQUIRED_HAZARDS = frozenset({
    "sign_of_the_inactive_term", "coefficient_must_be_exactly_positive_zero",
    "active_and_inactive_families_must_not_be_swapped",
    "inactive_register_must_not_be_enumerated", "frozen_f015_accumulation_order",
    "T_E_must_carry_the_retained_inactive_width",
    "T_E_exact_must_equal_base_times_two_to_the_w",
    "canonical_strict_first_seen_minimum", "a_minus_zero_energy_must_be_counted",
})


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


def source_text() -> str:
    return _read_bound(SOURCE_REL).decode("utf-8")


def mutated_sources(source: str) -> tuple[tuple[Mutation, str], ...]:
    """Every mutation, each with an exact unique anchor in the reviewed source.

    Each guard here is load-bearing and is REACHED by a fixture that feeds this
    function a deliberately broken source, so none of them can be weakened
    without the fixtures failing. The fixtures in
    ``verify_stage2_cuda_d013_inactive_host_emulation.py`` call
    ``check_corruption_plan_guards`` for exactly that purpose.
    """
    _require(type(source) is str and source, "D013 CUDA source is empty")
    _require(len({mutation.label for mutation in MUTATIONS}) == len(MUTATIONS),
             "mutation labels drift")
    _require({mutation.category for mutation in MUTATIONS} == REQUIRED_CATEGORIES,
             "required corruption categories drift")
    _require({mutation.hazard for mutation in MUTATIONS} == REQUIRED_HAZARDS,
             "required corruption hazards drift")
    result = []
    for mutation in MUTATIONS:
        _require(source.count(mutation.old) == 1 and mutation.old != mutation.new,
                 "mutation anchor is missing or ambiguous: " + mutation.label)
        changed = source.replace(mutation.old, mutation.new, 1)
        _require(changed != source and changed.count(mutation.new) == 1,
                 "mutation did not change exactly one anchor: " + mutation.label)
        result.append((mutation, changed))
    _require(len({_sha(text.encode("utf-8")) for _, text in result}) == len(result),
             "two mutations produced the same source")
    return tuple(result)


def plan_guard_probe_sources(source: str) -> dict[str, str]:
    """Deliberately broken sources, one per ``mutated_sources`` guard.

    Each value is accepted by exactly the labelled guard and refused by the
    others, so a fixture can reach every guard in ``mutated_sources`` without
    editing the MUTATIONS table itself. This exists so the plan's own integrity
    checks are exercised rather than merely present.
    """
    _require(type(source) is str and source, "D013 CUDA source is empty")
    first = MUTATIONS[0]
    probes = {
        # Not a usable source: trips the very first guard.
        "empty": "",
        # Anchor missing: this mutation's `old` is not present at all.
        "missing_anchor": source.replace(first.old, "// removed anchor\n", 1),
        # Anchor AMBIGUOUS: the same anchor appears twice.
        "ambiguous_anchor": source.replace(first.old, first.old + first.old, 1),
        # The replacement text is ALREADY present, so after the substitution it
        # occurs more than once and the "exactly one anchor" guard must refuse.
        "replacement_present": source.replace(first.old, first.old + first.new, 1),
    }
    return probes


def source_hashes() -> dict[str, str]:
    return {relative: _sha(_read_bound(relative)) for relative in SOURCE_RELS}


def compile_flags() -> tuple[str, ...]:
    """The host-emulation flags this path REQUIRES, and its own frozen contract."""
    return ("-x", "c++", "-std=c++17", "-O0", "-shared", "-fPIC", "-Wall", "-Wextra",
            "-Wno-unknown-pragmas", "-ffp-contract=off", "-fno-fast-math")


def build_plan() -> dict[str, object]:
    """Read-only source/fixture plan; no nvcc lookup and no CUDA operation."""
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
        "conditions": list(d013.CONDITIONS),
        "inactive_families": {name: sorted(families)
                              for name, families in d013.INACTIVE_FAMILIES.items()},
        "retained_inactive_width": d013.SECTOR_REGISTER_WIDTH + d013.BUDGET_REGISTER_WIDTH,
        "source_sha256": source_hashes(),
        "compile_flags": list(compile_flags()),
        "mutations": rows,
        "detection_cases": canonical_detection_table(),
        "detection_cases_sha256": detection_table_sha256(),
        "reference": "slow_independent_python_reference_in_the_fixtures",
        "wp6_evaluator": "not_imported_hook_reserved",
        "image_digest_status": "post_run_metadata_audit_required",
    }
    body["content_sha256"] = contract.content_sha256(body)
    return body


def _released(reviewed: object) -> dict[str, object]:
    """Verify the owner-approved draft before any compiler or device lookup."""
    _require(os.environ.get("PYTHONDONTWRITEBYTECODE") == "1",
             "PYTHONDONTWRITEBYTECODE=1 is required")
    _require(type(reviewed) is str and len(reviewed) == 64 and
             all(character in "0123456789abcdef" for character in reviewed),
             "reviewed D013 A-release SHA-256 is required")
    _require(os.environ.get(ALLOW_ENV) == "1", "separate D013 A-execution permission is required")
    path = ROOT / RELEASE_DRAFT_REL
    _require(path.is_file() and not path.is_symlink(), "D013 release draft is unavailable")
    raw = path.read_bytes()
    _require(_sha(raw) == reviewed, "D013 release draft hash differs from reviewed handoff")
    try:
        release = json.loads(raw)
    except ValueError as exc:
        raise CorruptionQualificationError("D013 A-execution release is invalid JSON") from exc
    _require(type(release) is dict and raw == contract.canonical_bytes(release) + b"\n" and
             set(release) == {"schema", "owner_approved", "source_sha256",
                              "compile_flags", "mutations", "detection_cases",
                              "detection_cases_sha256"} and
             release.get("schema") == "decisions_os/g9_d013_cuda_release_draft/v1" and
             release.get("owner_approved") is True,
             "D013 release draft is not canonical and owner-approved")
    _require(release.get("compile_flags") == list(GPU_COMPILE_FLAGS) and
             release.get("mutations") == [
                 {"label": item.label, "category": item.category, "hazard": item.hazard}
                 for item in MUTATIONS] and
             release.get("detection_cases") == canonical_detection_table() and
             release.get("detection_cases_sha256") == detection_table_sha256(),
             "D013 release draft flags or mutation list drift")
    plan = build_plan()
    _require(release.get("source_sha256") == plan["source_sha256"],
             "D013 source map changed after release")
    return plan


def _run(command: list[str], label: str, *, timeout: int) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(command, cwd=ROOT, text=True, capture_output=True,
                              check=False, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CorruptionQualificationError(label + " failed or timed out") from exc


def _check_token(token: object) -> bool:
    if type(token) is VerifiedReleaseToken:
        release_sha, map_sha, proof_sha = (token.release_sha256, token.source_map_sha256,
                                           token.proof_sha256)
    elif (type(token) is dict and set(token) == {
            "release_sha256", "source_map_sha256", "proof_sha256"}):
        release_sha, map_sha, proof_sha = (token["release_sha256"], token["source_map_sha256"],
                                           token["proof_sha256"])
    else:
        return False
    path = ROOT / RELEASE_DRAFT_REL
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
            release.get("schema") != "decisions_os/g9_d013_cuda_release_draft/v1" or
            release.get("compile_flags") != list(GPU_COMPILE_FLAGS) or
            release.get("mutations") != [
                {"label": item.label, "category": item.category, "hazard": item.hazard}
                for item in MUTATIONS] or
            release.get("detection_cases") != canonical_detection_table() or
            release.get("detection_cases_sha256") != detection_table_sha256() or
            release.get("source_sha256") != source_hashes()):
        return False
    source_map = release["source_sha256"]
    return (map_sha == _sha(contract.canonical_bytes(source_map)) and
            proof_sha == _token_proof(release_sha, source_map))


def run_qualification(reviewed_release_sha256: str) -> dict[str, object]:
    """Compile and independently qualify clean and mutated D013 CUDA ABIs."""
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
                                 _token_proof(reviewed_release_sha256,
                                              json.loads((ROOT / RELEASE_DRAFT_REL).read_bytes())["source_sha256"]))
    payload = reference.core.synthetic_payload()
    results = []
    clean_build = None
    with tempfile.TemporaryDirectory(prefix="g9-d013-gpu-A-") as temporary:
        directory = Path(temporary)
        source = source_text()
        mutation_rows = selected_mutation_sources(source)
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
            table_cases = (tuple(case for cases in DETECTION_CASES.values() for case in cases)
                           if mutation is None else DETECTION_CASES[mutation.label])
            # The clean ABI must also pass the frozen four-condition baseline.
            if mutation is None:
                table_cases += tuple(DetectionCase(condition, "noncommuting", "mismatch")
                                     for condition in CLEAN_CONDITIONS)
            case_results = []
            observations = []
            for case in table_cases:
                condition = case.condition
                if case.input_builder == "direct_tiny_positive":
                    accepts = reference.direct_abi_accepts_tiny_positive_inactive(
                        library, payload, reference.records_for)
                    detected = accepts
                    if mutation is None and accepts:
                        raise CorruptionQualificationError(
                            "clean D013 CUDA build accepted the invalid direct-ABI probe")
                    if mutation is not None and not detected:
                        raise CorruptionQualificationError(
                            "corrupted D013 CUDA build was accepted: " + label)
                    case_results.append({"condition": condition, "input_builder": case.input_builder,
                                         "detected": detected})
                    continue
                records = (reference.tie_bearing_records(condition)
                           if case.input_builder == "tie_bearing"
                           else reference.noncommuting_records(condition))
                detected = False
                try:
                    observed = d013.run_host_emulated_frame(payload, records, condition,
                                                            library, 64, verified_release=token)
                    observations.append({"condition": condition, "input_builder": case.input_builder,
                                         "counters": observed["counters"],
                                         "result_sha256": observed["result_sha256"],
                                         "content_sha256": observed["content_sha256"]})
                    agrees = reference.reference_agrees_with_result(
                        reference.core.build_domain(payload), records, condition, observed)
                    raw_rejected = reference.reference_rejects_raw_counters(
                        library, payload, condition, records)
                    detected = (not agrees) or raw_rejected
                    if mutation is None and not agrees:
                        raise CorruptionQualificationError(
                            "clean D013 CUDA build was rejected by the independent reference")
                except d013.D013InactiveError:
                    if mutation is None:
                        raise CorruptionQualificationError(
                            "clean D013 CUDA build was rejected by the independent reference")
                    detected = reference.reference_rejects_raw_counters(
                        library, payload, condition, records)
                case_results.append({"condition": condition, "input_builder": case.input_builder,
                                     "detected": detected})
                if mutation is not None and not detected:
                    raise CorruptionQualificationError(
                        "corrupted D013 CUDA build was accepted: " + label)
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
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "mode": "non_scientific_d013_cuda_corruption_qualification",
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
            "proof_sha256": _token_proof(reviewed_release_sha256, before),
        },
        "python_version": platform.python_version(),
        "mutations": results,
        "identity": {"backend": 1, "compiler_path": nvcc,
                     "device_index": 0,
                     "python_version": platform.python_version()},
    }
    receipt["content_sha256"] = contract.content_sha256(receipt)
    return receipt


def selected_mutation_sources(source: str) -> tuple[tuple[Mutation, str], ...]:
    """Production selection always means the complete reviewed mutation set."""
    return mutated_sources(source)


def main() -> int:
    plan = build_plan()
    print(json.dumps(plan, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())

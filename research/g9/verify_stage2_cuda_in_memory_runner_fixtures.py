#!/usr/bin/env python3
"""Non-writing, synthetic-only checks for the Gate-9 core/reconstruction seam."""

from __future__ import annotations

from array import array
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.g9.cuda_qualification import stage2_cuda_core_stream_engine as core  # noqa: E402
from research.g9.cuda_qualification import stage2_cuda_in_memory_runner as runner  # noqa: E402
from research.g9.cuda_qualification import stage2_cuda_reconstruct as recon  # noqa: E402


class FixtureError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise FixtureError(message)


def refused(operation, *args) -> None:
    try:
        operation(*args)
    except (recon.ReconstructionError, runner.InMemoryRunnerError):
        return
    raise FixtureError("malformed core-to-host handoff was accepted")


def no_float_or_bool(value: object) -> bool:
    if type(value) in (float, bool):
        return False
    if isinstance(value, dict):
        return all(no_float_or_bool(key) and no_float_or_bool(item)
                   for key, item in value.items())
    if isinstance(value, (tuple, list)):
        return all(no_float_or_bool(item) for item in value)
    return True


def main() -> int:
    payload = core.synthetic_payload()
    coefficients = core.coefficient_row("row0")

    def objective(x: tuple[int, ...]) -> float:
        return 0.0 if sum(x) == 0 else 1.0

    def feasible(x: tuple[int, ...]) -> bool:
        return sum(x) <= 1

    prepared = runner.PreparedInMemoryRunner(
        payload, f_star=0.0, objective=objective, feasible=feasible,
    )
    reconstructed = prepared.reconstruct_record(coefficients)
    require(no_float_or_bool(reconstructed), "runner leaked a float or boolean")
    require(set(reconstructed) == {"primary_c_h_2048", "d015_diagnostics"},
            "runner did not return the bounded record-summary body")

    # The public generic core runs without qualification controls. Its raw
    # ten-field summaries must be accepted directly, with no hand projection.
    raw = core.run_core(payload, [coefficients])
    require(raw["lift_total"] == prepared.lift_total and raw["record_count"] == 1,
            "generic core and prepared runner disagree on the domain")
    # Rebuild the offset map independently of the prepared runner and use its
    # digest as the external-domain binding, rather than echoing the runner's.
    independent_domain = core.build_domain(payload)
    independent_slack = recon.SlackIndexMap(
        independent_domain["offsets"], independent_domain["lift_total"],
    )
    require(independent_slack.offsets_sha256 == prepared.offsets_sha256,
            "independent slack-domain identity differs")
    direct = prepared.reconstruct_core_result(
        raw, 0, offsets_sha256=independent_slack.offsets_sha256,
    )
    require(direct == reconstructed, "generic run_core and prepared runner disagree")

    # A different *valid* offset table can have the same lift_total. Shift one
    # boundary unit from a later multi-lift state into state zero: total and
    # per-state bounds remain legal, but the decoded mapping and digest change.
    donor = next(index for index in range(1, recon.STATE_COUNT)
                 if independent_domain["offsets"][index + 1] -
                 independent_domain["offsets"][index] >= 2)
    shifted = array("Q", independent_domain["offsets"])
    for boundary in range(1, donor + 1):
        shifted[boundary] += 1
    mismatched_slack = recon.SlackIndexMap(shifted, independent_slack.lift_total)
    require(mismatched_slack.offsets_sha256 != independent_slack.offsets_sha256,
            "same-size offset swap was invisible to the digest")
    refused(lambda: prepared.reconstruct_core_result(
        raw, 0, offsets_sha256=mismatched_slack.offsets_sha256,
    ))
    first_decode = independent_slack.decoded_index(0)
    independent_domain["offsets"][1] += 1
    require(independent_slack.decoded_index(0) == first_decode and
            independent_slack.offsets_sha256 == prepared.offsets_sha256,
            "validated offset snapshot changed when its source array was mutated")
    for encoding in core.ENCODINGS:
        summary = raw["summaries"][(0, encoding)]
        primary = direct["primary_c_h_2048"][encoding]
        require(summary["compacted_count"] == len(summary["compacted_entries"]) == 1,
                f"{encoding}: control-free path did not produce a singleton compacted set")
        require(summary["per_ch"] == (1, 1, 1) and primary["T_E_size"] == 1
                and primary["X_E_size"] == 1,
                f"{encoding}: control-free D015/D016 reconstruction drifted")
        require(summary["illegal"] == summary["nesting"] == 0,
                f"{encoding}: core returned invalid flags")

    def drifted(field: str, value: object) -> dict[str, object]:
        summaries = dict(raw["summaries"])
        changed = dict(summaries[(0, "slack")])
        changed[field] = value
        summaries[(0, "slack")] = changed
        return {**raw, "summaries": summaries}

    def project(value: dict[str, object], slot: int = 0) -> dict[str, object]:
        return prepared.reconstruct_core_result(
            value, slot, offsets_sha256=independent_slack.offsets_sha256,
        )

    refused(project, {**raw, "lift_total": raw["lift_total"] + 1})
    refused(project, {**raw, "record_count": 2}, 1)
    refused(project, drifted("word_count", 0))
    refused(project, drifted("compacted_count", 2))
    refused(project, drifted("per_ch", (2, 1, 1)))
    refused(project, drifted("illegal", 1))
    refused(project, drifted("nesting", 1))
    refused(project, drifted("compacted_entries", ("bad",)))
    missing = dict(raw["summaries"])
    del missing[(0, "slack")]
    refused(project, {**raw, "summaries": missing})

    print("PASS Stage-2 synthetic in-memory integration: control-free core, retained offsets, direct summaries, D015/D016 and refusals")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

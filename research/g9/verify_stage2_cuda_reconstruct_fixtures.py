#!/usr/bin/env python3
"""Synthetic, non-writing checks for the Gate-9 compact-result reconstruction."""

from __future__ import annotations

from array import array
import hashlib
from pathlib import Path
import struct
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.g9.cuda_qualification import stage2_cuda_core_stream_engine as core  # noqa: E402
from research.g9.cuda_qualification import stage2_cuda_reconstruct as recon  # noqa: E402
from src.g4.classification import DecodedClassifier, OriginalObjectiveService  # noqa: E402
from src.g5.certify import decode_x_e  # noqa: E402
from src.g5.domains import BinaryDomain  # noqa: E402


class FixtureError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise FixtureError(message)


def refused(operation, *args) -> None:
    try:
        operation(*args)
    except recon.ReconstructionError:
        return
    raise FixtureError("malformed compact input was accepted")


def classifiers(lambda_ref: float) -> dict[int, DecodedClassifier]:
    first_nonzero = float.fromhex("0x1p-46")

    def objective(x: tuple[int, ...]) -> float:
        if sum(x) == 0:
            return 0.0
        if sum(x) == 1:
            return first_nonzero
        return 1.0

    def feasible(x: tuple[int, ...]) -> bool:
        return sum(x) <= 1

    return {c_f: DecodedClassifier(
        OriginalObjectiveService(objective, lambda_ref, float(c_f)),
        feasible,
    ) for c_f in recon.CF_VALUES}


def synthetic_offsets() -> recon.SlackIndexMap:
    # Decoded state zero has two lifts, every later state one. The offsets are
    # complete and monotone without materializing any energy or auxiliary data.
    offsets = array("Q", range(recon.STATE_COUNT + 1))
    for position in range(1, len(offsets)):
        offsets[position] += 1
    return recon.SlackIndexMap(offsets, recon.STATE_COUNT + 1)


def manual_checks(slack: recon.SlackIndexMap) -> None:
    lam = core.SYNTHETIC_LAMBDA_REF
    groups = classifiers(lam)
    require(slack.decoded_index(0) == 0 and slack.decoded_index(1) == 0
            and slack.decoded_index(2) == 1 and slack.decoded_index(4) == 3,
            "slack offsets did not preserve first-seen decoded order")

    unbalanced = [(7 << 32) | 0, (6 << 32) | 1, (4 << 32) | 3]
    result = recon.reconstruct_stream("unbalanced", 0.0, 0, unbalanced, slack, groups, 0.0, lam)
    primary = result["primary_c_h_2048"]
    diagnostics = result["d015_diagnostics"]
    require(primary["T_E_size"] == 2 and primary["X_E_size"] == 2
            and primary["set_label"] == "A", "primary D015/D016 reconstruction drifted")
    require(diagnostics["c_H=2048__c_f=1024"]["set_label"] == "B"
            and diagnostics["c_H=2048__c_f=4096"]["set_label"] == "A",
            "changing c_f did not re-label the same decoded X_E")
    require(diagnostics["c_H=1024__c_f=2048"]["T_E_size"] == 1
            and diagnostics["c_H=4096__c_f=2048"]["set_label"] == "C",
            "changing c_H did not select the nested tie sets")
    expected_digest = hashlib.sha256(struct.pack("<QQ", 0, 1)).hexdigest()
    require(primary["commitments"]["T_E_domain_index_stream_sha256"] == expected_digest,
            "tie-index commitment drifted")

    lifted = [(7 << 32) | 0, (6 << 32) | 1, (4 << 32) | 2, (4 << 32) | 4]
    result = recon.reconstruct_stream("slack", 0.0, 0, lifted, slack, groups, 0.0, lam)
    primary = result["primary_c_h_2048"]
    loose = result["d015_diagnostics"]["c_H=4096__c_f=2048"]
    require(primary["T_E_size"] == 2 and primary["X_E_size"] == 1
            and primary["set_label"] == "A", "slack first-seen deduplication drifted")
    require(loose["T_E_size"] == 4 and loose["X_E_size"] == 3
            and loose["set_label"] == "C" and loose["atomic_counts"] == {"A": 2, "B": 0, "C": 1},
            "slack D016 census drifted")

    binary = BinaryDomain(20)
    independent = decode_x_e([0, 1, 2, 4], lambda index: binary[slack.decoded_index(index)])
    require(len(independent) == loose["X_E_size"], "frozen first-seen decoder disagrees")

    def no_float(value: object) -> bool:
        if isinstance(value, dict):
            return all(no_float(key) and no_float(item) for key, item in value.items())
        if isinstance(value, (list, tuple)):
            return all(no_float(item) for item in value)
        return not isinstance(value, (float, bool))

    require(no_float(result), "reconstruction leaked a float or bool into its summary")

    pair = recon.reconstruct_pair({
        "unbalanced": {"minimum": 0.0, "minimum_index": 0,
                       "compacted_entries": unbalanced},
        "slack": {"minimum": 0.0, "minimum_index": 0,
                  "compacted_entries": lifted},
    }, slack, groups, 0.0, lam)
    require(set(pair["primary_c_h_2048"]) == {"unbalanced", "slack"}
            and len(pair["d015_diagnostics"]) == len(recon.DIAGNOSTIC_PAIRS),
            "paired record body is incomplete")
    require(no_float(pair), "paired record body leaked a float or bool")

    args = ("unbalanced", 0.0, 0)
    tail = (slack, groups, 0.0, lam)
    for entries in (
        [(7 << 32) | 0, (7 << 32) | 0],
        [(7 << 32) | 1, (7 << 32) | 0],
        [(5 << 32) | 0],
        [(4 << 32) | 0],
        [(7 << 32) | recon.STATE_COUNT],
        [(7 << 32) | 1],
        [],
    ):
        refused(recon.reconstruct_stream, *args, entries, *tail)
    wrong = classifiers(lam * 2.0)
    refused(recon.reconstruct_stream, *args, unbalanced, slack, wrong, 0.0, lam)
    changed_problem = dict(groups)
    changed_problem[4096] = DecodedClassifier(
        OriginalObjectiveService(lambda x: 0.0, lam, 4096.0),
        groups[4096].feasible,
    )
    refused(recon.reconstruct_stream, *args, unbalanced, slack, changed_problem, 0.0, lam)
    changed_feasibility = dict(groups)
    changed_feasibility[4096] = DecodedClassifier(
        groups[4096].optimum_service, lambda x: True,
    )
    refused(recon.reconstruct_stream, *args, unbalanced, slack, changed_feasibility, 0.0, lam)
    refused(recon.reconstruct_stream, *args, unbalanced, slack, groups, 0.0, 0.0)
    refused(recon.reconstruct_stream, *args, unbalanced, slack, groups, 0.0, lam * 2.0)
    refused(recon.reconstruct_stream, "slack", 0.0, slack.lift_total,
            lifted, slack, groups, 0.0, lam)
    refused(recon.reconstruct_pair, {"unbalanced": {"minimum": 0.0,
            "minimum_index": 0, "compacted_entries": unbalanced}},
            slack, groups, 0.0, lam)


def composed_core_check() -> None:
    # One real scan of the existing fixed synthetic core path. Its compacted
    # output is consumed directly, without re-enumerating energies here.
    domain = core.build_domain(core.synthetic_payload())
    slack = recon.SlackIndexMap(domain["offsets"], domain["lift_total"])
    lam = domain["payload"]["lambda_ref"]
    groups = classifiers(lam)
    for encoding in core.ENCODINGS:
        device_shape = core.scan(domain, "row0", encoding)
        result = recon.reconstruct_stream(
            encoding, device_shape["minimum"], device_shape["minimum_index"],
            device_shape["compacted_entries"], slack, groups, 0.0, lam,
        )
        primary = result["primary_c_h_2048"]
        require(primary["T_E_size"] == device_shape["per_ch"][1],
                f"{encoding}: primary ties disagree with the core's flag census")
        require(primary["H_E_min_domain_index"] == device_shape["minimum_index"],
                f"{encoding}: minimum index was not transported")
        require(primary["X_E_size"] >= 1 and primary["X_E_size"] <= primary["T_E_size"],
                f"{encoding}: decoded census is impossible")


def main() -> int:
    manual_checks(synthetic_offsets())
    composed_core_check()
    print("PASS Stage-2 synthetic compact-result reconstruction: frozen decode, D015/D016, commitments, refusals and composed core output")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

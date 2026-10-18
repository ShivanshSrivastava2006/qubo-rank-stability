#!/usr/bin/env python3
"""Read-only verification of the one-shot Gate-6 bounded CPU trial artifact."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.g4.energy import tau, unbalanced_energy
from src.g4.instance import load_instance
from src.g4.parameters import Coefficients
from src.g6.ledgers import canonical_bytes
from src.g6.ratified_g5_input import (
    RatifiedG5InputError,
    iter_ratified_records,
    verify_ratified_g5_corpus,
)


SCHEMA = "decisions_os/g6_bounded_cpu_trial/v1"
EXPECTED_POINTS = {
    "d011_primary_30": "d011_curvature_companion",
    "v14_2x_embedded_primary_30": "v14_expansion_2x",
    "v14_2x_lower_endpoint": "v14_expansion_2x",
    "v14_2x_upper_endpoint": "v14_expansion_2x",
}
EXPECTED_DIAGNOSTICS = {
    "c_H=1024__c_f=2048",
    "c_H=4096__c_f=2048",
    "c_H=2048__c_f=1024",
    "c_H=2048__c_f=4096",
}
G5_NAMED_KEY = {"r_hex": float(1.0).hex(), "ell_card": 30, "ell_sector": 30, "ell_budget": 30}


class TrialAuditError(RuntimeError):
    """Raised on any trial-artifact identity or contract failure."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise TrialAuditError(message)


def _file_hash(path: Path, label: str) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise TrialAuditError(f"{label} is unreadable") from exc


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TrialAuditError(f"{label} is unreadable JSON") from exc
    _require(isinstance(payload, dict), f"{label} must be a JSON object")
    return payload


def _validate_content(payload: Mapping[str, Any], label: str) -> None:
    body = dict(payload)
    digest = body.pop("content_sha256", None)
    _require(isinstance(digest, str) and digest == hashlib.sha256(canonical_bytes(body)).hexdigest(),
             f"{label} canonical content hash mismatch")


def _label_from_atomic(record: Mapping[str, Any]) -> str:
    decoded = record.get("X_E")
    _require(isinstance(decoded, list) and decoded, "certification has no decoded tie set")
    _require(all(isinstance(item, dict) for item in decoded), "malformed decoded record")
    labels = {item.get("atomic_label") for item in decoded}
    _require(labels <= {"A", "B", "C"}, "invalid atomic label")
    return "C" if "C" in labels else ("A" if labels == {"A"} else "B")


def _validate_rendered_record(record: Mapping[str, Any], expected_c_h: int) -> None:
    _require(isinstance(record, dict) and set(record) == {
        "H_E_min_hex", "T_E_size", "T_E", "X_E_size", "X_E", "set_label", "tie_comparator"
    }, "malformed rendered certification record")
    _require(record.get("T_E_size") == len(record["T_E"]) and record.get("X_E_size") == len(record["X_E"]),
             "rendered certification cardinality mismatch")
    comparator = record["tie_comparator"]
    _require(isinstance(comparator, dict) and comparator.get("c_H") == expected_c_h,
             "rendered certification c_H mismatch")
    _require(record.get("set_label") == _label_from_atomic(record), "D016 set-label mismatch")
    try:
        h_min = float.fromhex(record["H_E_min_hex"])
        epsilon = float.fromhex(comparator["epsilon_hex"])
        minimum_tau = float.fromhex(comparator["minimum_tau_hex"])
    except (KeyError, TypeError, ValueError) as exc:
        raise TrialAuditError("unparseable rendered binary64 field") from exc
    _require(math.isfinite(h_min) and epsilon == math.ldexp(1.0, -52) and math.isfinite(minimum_tau)
             and minimum_tau > 0.0, "invalid rendered tie comparator")


def _ratified_named_record() -> dict[str, Any]:
    found = None
    try:
        for record in iter_ratified_records():
            if record.get("key") == G5_NAMED_KEY:
                _require(found is None, "ratified Gate-5 named record is duplicated")
                found = record
    except RatifiedG5InputError as exc:
        raise TrialAuditError(f"ratified Gate-5 named-record lookup failed: {exc}") from exc
    _require(found is not None, "ratified Gate-5 named record is absent")
    return found


def _coefficients(values: Mapping[str, Any]) -> Coefficients:
    required = {
        "alpha", "sector_slack", "budget_slack", "sector_linear", "sector_quadratic",
        "budget_linear", "budget_quadratic",
    }
    _require(isinstance(values, dict) and set(values) == required, "malformed trial coefficient mapping")
    try:
        return Coefficients(**{name: float.fromhex(values[name]) for name in required})
    except (TypeError, ValueError) as exc:
        raise TrialAuditError("invalid trial coefficient binary64 value") from exc


def _check_d011(point: Mapping[str, Any], reference: Mapping[str, Any], instance, lambda_ref: float) -> None:
    core = point["primary_c_h_2048"]
    _require(core["slack"] == reference["slack"], "D011 slack record differs from ratified Gate-5")
    coefficients = _coefficients(point["coefficients_hex"])
    trial_hex = {name: value.hex() for name, value in asdict(coefficients).items()}
    reference_hex = reference["coefficients_hex"]
    _require(all(trial_hex[field] == reference_hex[field] for field in
                 ("alpha", "sector_slack", "budget_slack")),
             "D011 shared coefficients differ from ratified Gate-5")
    _require(all(trial_hex[field] != reference_hex[field] for field in
                 ("sector_linear", "sector_quadratic", "budget_linear", "budget_quadratic")),
             "D011 unbalanced coefficients unexpectedly equal ratified Gate-5")
    h_min = float.fromhex(core["unbalanced"]["H_E_min_hex"])
    for raw in core["unbalanced"]["T_E"]:
        x = tuple(raw["x_bits"])
        value = unbalanced_energy(instance, x, coefficients)
        _require(abs(value - h_min) <= tau(value, h_min, lambda_ref, 2048.0),
                 "D011 tied state fails independent unbalanced energy check")
    _require(point.get("mechanical_checks") == {
        "slack_matches_ratified_gate5": True,
        "shared_coefficients_match_ratified_gate5": True,
        "unbalanced_coefficients_differ": True,
        "unbalanced_tied_states_independently_checked": True,
    }, "D011 mechanical-check record mismatch")


def _check_v14_overlap(point: Mapping[str, Any], reference: Mapping[str, Any]) -> None:
    _require(point["coefficients_hex"] == reference["coefficients_hex"],
             "V-14 embedded coefficients differ from ratified Gate-5")
    core = point["primary_c_h_2048"]
    _require(core["unbalanced"] == reference["unbalanced"] and core["slack"] == reference["slack"],
             "V-14 embedded encoding record differs from ratified Gate-5")
    _require(point.get("mechanical_checks") == {
        "coefficients_match_ratified_gate5": True,
        "both_encodings_match_ratified_gate5": True,
    }, "V-14 embedded mechanical-check record mismatch")


def verify_trial(output_dir: Path) -> dict[str, str]:
    trial_path, manifest_path = output_dir / "trial.json", output_dir / "manifest.json"
    _require(output_dir.is_dir(), "bounded-trial output directory is absent")
    _require({path.name for path in output_dir.iterdir()} == {"trial.json", "manifest.json"},
             "bounded-trial output directory has unexpected membership")
    trial, manifest = _read_json(trial_path, "trial artifact"), _read_json(manifest_path, "trial manifest")
    _validate_content(trial, "trial artifact")
    _validate_content(manifest, "trial manifest")
    _require(manifest.get("schema") == "decisions_os/g6_bounded_cpu_trial_manifest/v1",
             "unexpected trial manifest schema")
    _require(manifest.get("trial_file_sha256") == _file_hash(trial_path, "trial artifact")
             and manifest.get("trial_content_sha256") == trial.get("content_sha256"),
             "trial manifest identity mismatch")
    _require(trial.get("schema") == SCHEMA and trial.get("scientific_outputs") == "intentionally absent",
             "trial schema or scientific-output boundary mismatch")
    _require(trial.get("ratified_gate5_reference_key") == G5_NAMED_KEY,
             "trial ratified reference key mismatch")
    source_hashes = trial.get("validator_source_sha256")
    _require(isinstance(source_hashes, dict) and source_hashes == manifest.get("validator_source_sha256"),
             "trial/manifest validator-source identity mismatch")
    _require(all(_file_hash(ROOT / relative, relative) == digest for relative, digest in source_hashes.items()),
             "live validator source differs from trial artifact")
    worker = trial.get("worker_self_test")
    _require(isinstance(worker, list) and len(worker) == 2
             and {entry.get("optimized") for entry in worker if isinstance(entry, dict)} == {False, True}
             and all(entry.get("exit_code") == 0 for entry in worker if isinstance(entry, dict)),
             "trial worker self-test attestation mismatch")
    points = trial.get("points")
    _require(isinstance(points, list) and len(points) == 4, "bounded trial point count mismatch")
    by_id = {point.get("trial_id"): point for point in points if isinstance(point, dict)}
    _require(set(by_id) == set(EXPECTED_POINTS) and len(by_id) == len(points), "bounded trial point membership mismatch")
    for trial_id, point in by_id.items():
        _require(point.get("pass_id") == EXPECTED_POINTS[trial_id], f"wrong pass for trial point: {trial_id}")
        core = point.get("primary_c_h_2048")
        _require(isinstance(core, dict) and set(core) == {"unbalanced", "slack"},
                 f"malformed primary certification: {trial_id}")
        for record in core.values():
            _validate_rendered_record(record, 2048)
        diagnostics = point.get("d015_diagnostics")
        _require(isinstance(diagnostics, dict) and set(diagnostics) == EXPECTED_DIAGNOSTICS,
                 f"D015 diagnostic membership mismatch: {trial_id}")
        for identifier, rendering in diagnostics.items():
            c_h = int(identifier.split("__", 1)[0].split("=", 1)[1])
            _require(isinstance(rendering, dict) and set(rendering) == {"unbalanced", "slack"},
                     f"malformed D015 rendering: {trial_id}/{identifier}")
            for record in rendering.values():
                _validate_rendered_record(record, c_h)
    try:
        summary = verify_ratified_g5_corpus()
    except RatifiedG5InputError as exc:
        raise TrialAuditError(f"ratified Gate-5 corpus verification failed: {exc}") from exc
    _require(trial.get("gate5_source_snapshot") == dict(summary.source_snapshot),
             "trial Gate-5 source snapshot differs from ratified corpus")
    reference = _ratified_named_record()
    instance = load_instance(ROOT / "research/canonical/stage1_instance.json")
    ground_truth = _read_json(ROOT / "research/ground_truth/G3_GROUND_TRUTH.json", "Gate-3 ground truth")
    lambda_ref = float(ground_truth["results"]["Lambda_ref"])
    _check_d011(by_id["d011_primary_30"], reference, instance, lambda_ref)
    _check_v14_overlap(by_id["v14_2x_embedded_primary_30"], reference)
    for trial_id in ("v14_2x_lower_endpoint", "v14_2x_upper_endpoint"):
        _require(by_id[trial_id].get("mechanical_checks") == {"finite_positive_coefficients": True},
                 f"endpoint mechanical-check record mismatch: {trial_id}")
        _coefficients(by_id[trial_id]["coefficients_hex"])
    return {"trial_file_sha256": manifest["trial_file_sha256"],
            "trial_content_sha256": trial["content_sha256"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "research/g6/bounded_cpu_trial")
    args = parser.parse_args()
    try:
        result = verify_trial(args.output_dir)
        print("PASS bounded CPU trial artifact verification")
        print(json.dumps(result, sort_keys=True))
        return 0
    except (TrialAuditError, KeyError, TypeError, ValueError) as exc:
        print(f"FAIL bounded CPU trial artifact verification: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

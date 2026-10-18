"""Bounded, CPU-only Gate-6 trial service.

This additive module is deliberately unable to dispatch a grid or resume a
pass.  Its one explicit execution produces four predeclared r=1 points:

* D011 curvature-match at the primary coordinate (30, 30, 30);
* V-14 2x at its embedded primary coordinate (70, 70, 70) = (30, 30, 30);
* V-14 2x at the two all-axis endpoints (0, 0, 0) and (110, 110, 110).

It uses the owner-ratified Gate-5 iterator for both reference comparisons.
No rate, grid aggregation, encoding comparison, or transition statistic is
defined here.
"""

from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
from typing import Any, Mapping

from src.g4.classification import DecodedClassifier, OriginalObjectiveService
from src.g4.energy import (
    objective,
    prepare_coefficients,
    slack_energy_prepared,
    tau,
    unbalanced_energy,
    unbalanced_energy_prepared,
)
from src.g4.instance import load_instance
from src.g4.parameters import Coefficients
from src.g5.certify import certify_prepared_domain
from src.g5.domains import build_slack_domain_cache, prepare_active_domains
from src.g6.ledgers import canonical_bytes, validate_preexecution_ledger
from src.g6.ratified_g5_input import (
    RatifiedG5InputError,
    iter_ratified_records,
    verify_ratified_g5_corpus,
)


ROOT = Path(__file__).resolve().parents[2]
PREEXECUTION_REL = "research/g6/preexecution_ledgers"
INSTANCE_REL = "research/canonical/stage1_instance.json"
GROUND_TRUTH_REL = "research/ground_truth/G3_GROUND_TRUTH.json"
WORKER_SELF_TEST_REL = "research/g5/verify_worker.py"
SCHEMA = "decisions_os/g6_bounded_cpu_trial/v1"
EPSILON = math.ldexp(1.0, -52)
CH_VALUES = (1024, 2048, 4096)
DIAGNOSTIC_PAIRS = ((1024, 2048), (4096, 2048), (2048, 1024), (2048, 4096))


class TrialError(RuntimeError):
    """Raised when the bounded trial contract cannot be established."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise TrialError(message)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path, label: str) -> str:
    try:
        return _sha256_bytes(path.read_bytes())
    except OSError as exc:
        raise TrialError(f"{label} is unreadable") from exc


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TrialError(f"{label} is unreadable JSON") from exc
    _require(isinstance(payload, dict), f"{label} must be a JSON object")
    return payload


def _validate_content_hash(payload: Mapping[str, Any], label: str) -> None:
    body = dict(payload)
    digest = body.pop("content_sha256", None)
    _require(isinstance(digest, str) and digest == _sha256_bytes(canonical_bytes(body)),
             f"{label} canonical content hash mismatch")


def _platform_fingerprint() -> dict[str, Any]:
    flags: list[str] = []
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.is_file():
        for line in cpuinfo.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("flags") and ":" in line:
                flags = sorted(line.split(":", 1)[1].split())
                break
    return {
        "python": sys.version,
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cpu_flags": flags,
        "pythonhashseed": os.environ.get("PYTHONHASHSEED", "<unset>"),
        "python_dont_write_bytecode": os.environ.get("PYTHONDONTWRITEBYTECODE", "<unset>"),
    }


def _worker_gate() -> list[dict[str, Any]]:
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    records: list[dict[str, Any]] = []
    for optimized in (False, True):
        command = [sys.executable] + (["-O"] if optimized else []) + [str(ROOT / WORKER_SELF_TEST_REL)]
        result = subprocess.run(command, cwd=ROOT, env=environment, text=True,
                                capture_output=True, check=False)
        _require(result.returncode == 0 and result.stdout.strip() == "PASS worker self test",
                 "Gate-5 worker self-test failed during bounded-trial qualification")
        records.append({"command": " ".join(command), "optimized": optimized, "exit_code": 0})
    return records


def _current_hashes(relatives: tuple[str, ...]) -> dict[str, str]:
    return {relative: _sha256_file(ROOT / relative, relative) for relative in relatives}


def _load_preexecution_ledgers() -> dict[str, dict[str, Any]]:
    directory = ROOT / PREEXECUTION_REL
    manifest_path = directory / "manifest.json"
    manifest = _read_json(manifest_path, "preexecution-ledger manifest")
    _validate_content_hash(manifest, "preexecution-ledger manifest")
    _require(manifest.get("schema") == "decisions_os/g6_preexecution_ledger_manifest/v1",
             "unexpected preexecution-ledger manifest schema")
    expected_names = {
        "d011_curvature_companion.json",
        "v14_expansion_0_5x.json",
        "v14_expansion_2x.json",
    }
    listed = manifest.get("ledgers")
    _require(isinstance(listed, dict) and set(listed) == expected_names,
             "preexecution-ledger manifest membership mismatch")
    output: dict[str, dict[str, Any]] = {}
    for name in sorted(expected_names):
        entry = listed[name]
        _require(isinstance(entry, dict) and set(entry) == {"content_sha256", "file_sha256"},
                 f"malformed preexecution-ledger manifest entry: {name}")
        path = directory / name
        _require(_sha256_file(path, name) == entry["file_sha256"],
                 f"preexecution-ledger file identity mismatch: {name}")
        payload = _read_json(path, name)
        _require(payload.get("content_sha256") == entry["content_sha256"],
                 f"preexecution-ledger content identity mismatch: {name}")
        try:
            validate_preexecution_ledger(payload)
        except Exception as exc:
            raise TrialError(f"preexecution ledger fails transcript replay: {name}") from exc
        output[name] = payload
    return output


def _coefficient_at(ledger: Mapping[str, Any], index: int) -> Coefficients:
    families = ledger["coefficient_ledger"]
    try:
        card = families["cardinality"][index]
        sector = families["sector"][index]
        budget = families["budget"][index]
        return Coefficients(
            alpha=float.fromhex(card["alpha_hex"]),
            sector_slack=float.fromhex(sector["lambda_slack_hex"]),
            budget_slack=float.fromhex(budget["lambda_slack_hex"]),
            sector_linear=float.fromhex(sector["lambda_1_hex"]),
            sector_quadratic=float.fromhex(sector["lambda_2_hex"]),
            budget_linear=float.fromhex(budget["lambda_1_hex"]),
            budget_quadratic=float.fromhex(budget["lambda_2_hex"]),
        )
    except (IndexError, KeyError, TypeError, ValueError) as exc:
        raise TrialError(f"malformed coefficient row {index}") from exc


def trial_points(ledgers: Mapping[str, Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    """Return the four frozen trial points without evaluating a domain."""
    d011 = ledgers["d011_curvature_companion.json"]
    double = ledgers["v14_expansion_2x.json"]
    _require(d011["coordinates"][6].get("primary_ell") == 30,
             "D011 bounded trial must use primary row 30")
    _require(double["coordinates"][70]["binary64_hex"] == d011["coordinates"][6]["binary64_hex"],
             "V-14 embedded trial coordinate does not equal primary row 30")
    trials = (
        ("d011_primary_30", "d011_curvature_companion", d011, (6, 6, 6), (30, 30, 30)),
        ("v14_2x_embedded_primary_30", "v14_expansion_2x", double, (70, 70, 70), (30, 30, 30)),
        ("v14_2x_lower_endpoint", "v14_expansion_2x", double, (0, 0, 0), None),
        ("v14_2x_upper_endpoint", "v14_expansion_2x", double, (110, 110, 110), None),
    )
    result = []
    for trial_id, pass_id, ledger, indices, primary_ells in trials:
        _require(all(isinstance(index, int) and 0 <= index < len(ledger["coordinates"]) for index in indices),
                 f"trial coordinate index outside ledger: {trial_id}")
        _require(indices[0] == indices[1] == indices[2],
                 f"bounded trial requires one shared all-axis ledger index: {trial_id}")
        coordinate_hex = tuple(ledger["coordinates"][index]["binary64_hex"] for index in indices)
        coefficients = _coefficient_at(ledger, indices[0])
        _require(all(math.isfinite(value) and value > 0.0 for value in asdict(coefficients).values()),
                 f"trial coefficient is not finite and positive: {trial_id}")
        result.append({
            "trial_id": trial_id,
            "pass_id": pass_id,
            "ledger_indices": {"card": indices[0], "sector": indices[1], "budget": indices[2]},
            "coordinate_hex": {"card": coordinate_hex[0], "sector": coordinate_hex[1], "budget": coordinate_hex[2]},
            "primary_ell": (None if primary_ells is None else
                            {"card": primary_ells[0], "sector": primary_ells[1], "budget": primary_ells[2]}),
            "coefficients": coefficients,
        })
    return tuple(result)


def _hard_feasible(instance, x: tuple[int, ...]) -> bool:
    if sum(x) != instance.K:
        return False
    for members in instance.sectors:
        if sum(x[index] for index in members) > instance.C:
            return False
    spend = +0.0
    for index, bit in enumerate(x):
        spend = spend + instance.prices[index] * float(bit)
    return spend <= instance.B


def _decoded_record(x: tuple[int, ...], instance, classifier: DecodedClassifier, f_star: float) -> dict[str, Any]:
    value = objective(instance, x)
    return {
        "x_bits": list(x),
        "selected_tickers": [ticker for ticker, bit in zip(instance.tickers, x, strict=True) if bit],
        "objective_hex": value.hex(),
        "hard_feasible": _hard_feasible(instance, x),
        "atomic_label": classifier.label(x, f_star),
    }


def _raw_record(state: Any, encoding: str, instance) -> dict[str, Any]:
    if encoding == "unbalanced":
        x, output = state, {"x_bits": list(state)}
    else:
        x, auxiliary = state
        output = {"x_bits": list(x), "auxiliary_bits": list(auxiliary)}
    output["selected_tickers"] = [ticker for ticker, bit in zip(instance.tickers, x, strict=True) if bit]
    return output


def _render_certification(result: tuple, encoding: str, instance, classifier: DecodedClassifier,
                          f_star: float, lambda_ref: float, c_h: int) -> dict[str, Any]:
    h_min, tied, decoded, _source_set_label = result
    epsilon = EPSILON
    tau = float((float(c_h) * epsilon) * float(lambda_ref + abs(h_min)))
    atomic = [_decoded_record(x, instance, classifier, f_star) for x in decoded]
    # ``result`` was necessarily tie-extracted with the primary classifier:
    # c_f does not change T_E, but it may legitimately change D016 labels.
    # Reclassify the same decoded set with the requested diagnostic c_f.
    set_label = classifier.label_set(decoded, f_star)
    labels = {item["atomic_label"] for item in atomic}
    expected_set_label = "C" if "C" in labels else ("A" if labels == {"A"} else "B")
    _require(set_label == expected_set_label, "diagnostic decoded set-label drift")
    return {
        "H_E_min_hex": h_min.hex(),
        "T_E_size": len(tied),
        "T_E": [_raw_record(item, encoding, instance) for item in tied],
        "X_E_size": len(decoded),
        "X_E": atomic,
        "set_label": set_label,
        "tie_comparator": {"c_H": c_h, "epsilon_hex": epsilon.hex(), "minimum_tau_hex": tau.hex()},
    }


def _certify_point(domains, coefficients: Coefficients, instance, lambda_ref: float, f_star: float) -> dict[str, Any]:
    prepared_coefficients = prepare_coefficients(coefficients)
    primary_classifier = DecodedClassifier(
        OriginalObjectiveService(lambda x: objective(instance, x), lambda_ref, 2048.0),
        lambda x: _hard_feasible(instance, x),
    )
    results: dict[int, dict[str, tuple]] = {}
    for c_h in CH_VALUES:
        results[c_h] = {
            "unbalanced": certify_prepared_domain(
                domains.unbalanced,
                lambda state, values=prepared_coefficients: unbalanced_energy_prepared(state, values),
                lambda_ref, f_star, lambda x: x, primary_classifier, float(c_h),
            ),
            "slack": certify_prepared_domain(
                domains.slack,
                lambda state, values=prepared_coefficients: slack_energy_prepared(state, values),
                lambda_ref, f_star, lambda state: state[0], primary_classifier, float(c_h),
            ),
        }
    for encoding in ("unbalanced", "slack"):
        state_sets = [set(results[c_h][encoding][1]) for c_h in CH_VALUES]
        _require(state_sets[0] <= state_sets[1] <= state_sets[2],
                 f"D015 tie-set nesting drift: {encoding}")
    core = {
        encoding: _render_certification(results[2048][encoding], encoding, instance,
                                        primary_classifier, f_star, lambda_ref, 2048)
        for encoding in ("unbalanced", "slack")
    }
    diagnostics: dict[str, Any] = {}
    for c_h, c_f in DIAGNOSTIC_PAIRS:
        classifier = DecodedClassifier(
            OriginalObjectiveService(lambda x, base=instance: objective(base, x), lambda_ref, float(c_f)),
            lambda x, base=instance: _hard_feasible(base, x),
        )
        diagnostics[f"c_H={c_h}__c_f={c_f}"] = {
            encoding: _render_certification(results[c_h][encoding], encoding, instance,
                                            classifier, f_star, lambda_ref, c_h)
            for encoding in ("unbalanced", "slack")
        }
    return {"primary_c_h_2048": core, "d015_diagnostics": diagnostics}


def _registered_g5_named_record() -> dict[str, Any]:
    wanted = {"r_hex": float(1.0).hex(), "ell_card": 30, "ell_sector": 30, "ell_budget": 30}
    found = None
    try:
        for record in iter_ratified_records():
            if record.get("key") == wanted:
                _require(found is None, "ratified Gate-5 named record is duplicated")
                found = record
    except RatifiedG5InputError as exc:
        raise TrialError(f"ratified Gate-5 named-record lookup failed: {exc}") from exc
    _require(found is not None, "ratified Gate-5 named record is absent")
    return found


def _check_d011(point: Mapping[str, Any], result: Mapping[str, Any], reference: Mapping[str, Any], instance,
                lambda_ref: float) -> dict[str, bool]:
    core = result["primary_c_h_2048"]
    _require(core["slack"] == reference["slack"],
             "D011 slack trial does not reproduce the ratified Gate-5 record")
    trial_coefficients = {name: value.hex() for name, value in asdict(point["coefficients"]).items()}
    reference_coefficients = reference["coefficients_hex"]
    shared = ("alpha", "sector_slack", "budget_slack")
    _require(all(trial_coefficients[field] == reference_coefficients[field] for field in shared),
             "D011 shared cardinality/slack coefficients drift from primary mapping")
    changed = ("sector_linear", "sector_quadratic", "budget_linear", "budget_quadratic")
    _require(all(trial_coefficients[field] != reference_coefficients[field] for field in changed),
             "D011 unbalanced inequality mapping unexpectedly equals primary mapping")
    h_min = float.fromhex(core["unbalanced"]["H_E_min_hex"])
    for raw in core["unbalanced"]["T_E"]:
        x = tuple(raw["x_bits"])
        independent = unbalanced_energy(instance, x, point["coefficients"])
        _require(abs(independent - h_min) <= tau(independent, h_min, lambda_ref, 2048.0),
                 "D011 unbalanced tied state fails independent §5.2 energy check")
    return {"slack_matches_ratified_gate5": True, "shared_coefficients_match_ratified_gate5": True,
            "unbalanced_coefficients_differ": True,
            "unbalanced_tied_states_independently_checked": True}


def _check_v14_embedded(point: Mapping[str, Any], result: Mapping[str, Any], reference: Mapping[str, Any]) -> dict[str, bool]:
    core = result["primary_c_h_2048"]
    coefficients_hex = {name: value.hex() for name, value in asdict(point["coefficients"]).items()}
    _require(coefficients_hex == reference["coefficients_hex"],
             "V-14 embedded primary coefficients do not reproduce Gate-5")
    _require(core["unbalanced"] == reference["unbalanced"] and core["slack"] == reference["slack"],
             "V-14 embedded primary trial does not reproduce ratified Gate-5 records")
    return {"coefficients_match_ratified_gate5": True, "both_encodings_match_ratified_gate5": True}


def _atomic_write_new(path: Path, payload: Mapping[str, Any]) -> None:
    temporary: Path | None = None
    descriptor: int | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.pending-", dir=path.parent)
        temporary = Path(temporary_name)
        encoded = canonical_bytes(payload)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = None
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o644)
        try:
            os.link(temporary, path)
        except FileExistsError as exc:
            raise TrialError(f"refusing to overwrite trial artifact: {path}") from exc
        directory_descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except OSError as exc:
        raise TrialError(f"atomic trial-artifact publication failed: {path}") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


def fixture_plan() -> dict[str, Any]:
    """Validate all static trial bindings without a Gate-5 read or energy sweep."""
    ledgers = _load_preexecution_ledgers()
    points = trial_points(ledgers)
    return {
        "trial_ids": [point["trial_id"] for point in points],
        "diagnostic_pairs": [list(pair) for pair in DIAGNOSTIC_PAIRS],
        "ledger_ids": {name: ledger["content_sha256"] for name, ledger in ledgers.items()},
        "scientific_outputs": "intentionally absent",
    }


def run_bounded_cpu_trial(output_dir: Path | str) -> Path:
    """Execute exactly the fixed trial points and atomically publish one artifact."""
    _require(os.environ.get("PYTHONDONTWRITEBYTECODE") == "1", "PYTHONDONTWRITEBYTECODE=1 is required")
    destination = Path(output_dir)
    _require(not destination.exists(), "bounded-trial output directory must not already exist")
    ledgers = _load_preexecution_ledgers()
    points = trial_points(ledgers)
    try:
        summary = verify_ratified_g5_corpus()
    except RatifiedG5InputError as exc:
        raise TrialError(f"ratified Gate-5 input verification failed: {exc}") from exc
    current_snapshot = _current_hashes(tuple(summary.source_snapshot))
    _require(current_snapshot == dict(summary.source_snapshot),
             "current Gate-5 source/input snapshot differs from the accepted corpus")
    validator_relatives = (
        "src/g6/g5_digest_registry.py", "src/g6/g5_input.py", "src/g6/ratified_g5_input.py",
        "src/g6/trial_runner.py", "src/g6/ledgers.py", "src/g4/energy.py", "src/g4/classification.py",
        "src/g5/certify.py", "src/g5/domains.py",
    )
    validator_sources_at_start = _current_hashes(validator_relatives)
    reference = _registered_g5_named_record()
    worker_gate = _worker_gate()
    start_platform = _platform_fingerprint()
    instance = load_instance(ROOT / INSTANCE_REL)
    ground_truth = _read_json(ROOT / GROUND_TRUTH_REL, "Gate-3 ground truth")
    try:
        lambda_ref = float(ground_truth["results"]["Lambda_ref"])
        f_star = float(ground_truth["results"]["f_star"])
    except (KeyError, TypeError, ValueError) as exc:
        raise TrialError("Gate-3 ground truth has invalid classifier inputs") from exc
    _require(math.isfinite(lambda_ref) and lambda_ref > 0.0 and math.isfinite(f_star),
             "Gate-3 classifier inputs are nonfinite")
    _require(all(ledger["inputs"]["lambda_ref_binary64_hex"] == lambda_ref.hex()
                 for ledger in ledgers.values()),
             "Gate-3 and preexecution-ledger Lambda_ref authorities differ")
    dummy = Coefficients(1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0)
    domains = prepare_active_domains(instance, build_slack_domain_cache(instance, dummy))
    rendered = []
    for point in points:
        certifications = _certify_point(domains, point["coefficients"], instance, lambda_ref, f_star)
        item = {key: value for key, value in point.items() if key != "coefficients"}
        item["coefficients_hex"] = {name: value.hex() for name, value in asdict(point["coefficients"]).items()}
        item.update(certifications)
        if point["trial_id"] == "d011_primary_30":
            item["mechanical_checks"] = _check_d011(point, certifications, reference, instance, lambda_ref)
        elif point["trial_id"] == "v14_2x_embedded_primary_30":
            item["mechanical_checks"] = _check_v14_embedded(point, certifications, reference)
        else:
            item["mechanical_checks"] = {"finite_positive_coefficients": True}
        rendered.append(item)
    _require(_platform_fingerprint() == start_platform, "platform fingerprint drift during bounded trial")
    _require(_current_hashes(tuple(summary.source_snapshot)) == dict(summary.source_snapshot),
             "Gate-5 source/input snapshot drift during bounded trial")
    source_hashes = _current_hashes(validator_relatives)
    _require(source_hashes == validator_sources_at_start,
             "Gate-6 validator source drift during bounded trial")
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "purpose": "bounded CPU qualification only; no pass, rate, aggregation, or conclusion",
        "platform": start_platform,
        "gate5_source_snapshot": dict(summary.source_snapshot),
        "ratified_gate5_reference_key": reference["key"],
        "worker_self_test": worker_gate,
        "preexecution_ledgers": {name: ledger["content_sha256"] for name, ledger in ledgers.items()},
        "validator_source_sha256": source_hashes,
        "d015_pairs": [{"c_H": c_h, "c_f": c_f} for c_h, c_f in DIAGNOSTIC_PAIRS],
        "points": rendered,
        "scientific_outputs": "intentionally absent",
    }
    payload["content_sha256"] = _sha256_bytes(canonical_bytes(payload))
    try:
        destination.mkdir(parents=True, exist_ok=False)
        os.chmod(destination, 0o755)
    except OSError as exc:
        raise TrialError(f"unable to create bounded-trial output directory: {destination}") from exc
    _atomic_write_new(destination / "trial.json", payload)
    manifest = {
        "schema": "decisions_os/g6_bounded_cpu_trial_manifest/v1",
        "trial_file_sha256": _sha256_file(destination / "trial.json", "bounded trial"),
        "trial_content_sha256": payload["content_sha256"],
        "validator_source_sha256": source_hashes,
        "scientific_outputs": "intentionally absent",
    }
    manifest["content_sha256"] = _sha256_bytes(canonical_bytes(manifest))
    _atomic_write_new(destination / "manifest.json", manifest)
    return destination / "trial.json"

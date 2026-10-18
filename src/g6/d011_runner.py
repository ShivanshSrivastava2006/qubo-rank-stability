"""Restartable CPU-only executor for the non-primary D011 companion pass.

The service has a fixed 13 x 13 x 13 coordinate population.  It emits
per-coordinate certification records only: no rates, aggregation, transition
edges, encoding comparison, or scientific interpretation is implemented here.
It never opens the Gate-5 corpus for writing.
"""

from __future__ import annotations

from array import array
from dataclasses import asdict
import hashlib
import json
import math
import multiprocessing as mp
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any, Callable, Mapping

from src.g4.classification import DecodedClassifier, OriginalObjectiveService
from src.g4.energy import prepare_coefficients, slack_energy_prepared, unbalanced_energy_prepared
from src.g4.instance import load_instance
from src.g4.parameters import Coefficients
from src.g5.certify import decode_x_e
from src.g5.domains import PreparedDomainCache, build_slack_domain_cache, prepare_active_domains
from src.g6.ledgers import canonical_bytes, validate_preexecution_ledger
from src.g6.ratified_g5_input import RatifiedG5InputError, verify_ratified_g5_corpus


ROOT = Path(__file__).resolve().parents[2]
PREEXECUTION_REL = "research/g6/preexecution_ledgers"
INSTANCE_REL = "research/canonical/stage1_instance.json"
GROUND_TRUTH_REL = "research/ground_truth/G3_GROUND_TRUTH.json"
WORKER_SELF_TEST_REL = "research/g5/verify_worker.py"
D011_SELF_TEST_REL = "research/g6/verify_d011_runner.py"
OWNER_DECISIONS_REL = "research/decisions/GATE_6_OWNER_EXECUTION_DECISIONS.md"
REGISTRY_REL = "research/g6/g5_identity_digest_registry_v1/G5_PER_SHARD_DIGEST_REGISTRY.json"
RATIFICATION_REL = "research/decisions/GATE_5_IDENTITY_REGISTRY_RATIFICATION.md"
SCHEMA = "decisions_os/g6_d011_curvature_companion/v1"
MANIFEST_SCHEMA = "decisions_os/g6_d011_curvature_companion/resume-manifest/v1"
COVERAGE_SCHEMA = "decisions_os/g6_d011_curvature_companion/coverage-audit/v1"
AXIS_COUNT = 13
ROW_COUNT = 13
EXPECTED_SHARDS = AXIS_COUNT * AXIS_COUNT
EXPECTED_COORDINATES = AXIS_COUNT * AXIS_COUNT * ROW_COUNT
CH_VALUES = (1024, 2048, 4096)
DIAGNOSTIC_PAIRS = ((1024, 2048), (4096, 2048), (2048, 1024), (2048, 4096))
EPSILON = math.ldexp(1.0, -52)
MIN_FREE_BYTES = 5 * 1024**3
WORKER_START_TIMEOUT_SECONDS = 15.0 * 60.0
_STATE: dict[str, Any] = {}


class D011Error(RuntimeError):
    """Raised whenever the D011 service cannot prove its contract."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise D011Error(message)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path, label: str) -> str:
    try:
        return _sha256_bytes(path.read_bytes())
    except OSError as exc:
        raise D011Error(f"{label} is unreadable") from exc


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise D011Error(f"{label} is unreadable JSON") from exc
    _require(isinstance(value, dict), f"{label} must be a JSON object")
    return value


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


def _d011_shard_id(card: int, sector: int) -> str:
    _require(isinstance(card, int) and isinstance(sector, int) and 0 <= card < AXIS_COUNT and 0 <= sector < AXIS_COUNT,
             "D011 shard indices outside 0..12")
    return f"d011__card={card:02d}__sector={sector:02d}"


def d011_tasks() -> tuple[tuple[int, int], ...]:
    return tuple((card, sector) for card in range(AXIS_COUNT) for sector in range(AXIS_COUNT))


def _load_d011_ledger() -> tuple[dict[str, Any], dict[str, Any]]:
    directory = ROOT / PREEXECUTION_REL
    manifest = _read_json(directory / "manifest.json", "preexecution-ledger manifest")
    _validate_content_hash(manifest, "preexecution-ledger manifest")
    _require(manifest.get("schema") == "decisions_os/g6_preexecution_ledger_manifest/v1",
             "unexpected preexecution-ledger manifest schema")
    entry = manifest.get("ledgers", {}).get("d011_curvature_companion.json")
    _require(isinstance(entry, dict) and set(entry) == {"content_sha256", "file_sha256"},
             "D011 preexecution-ledger manifest entry is malformed")
    path = directory / "d011_curvature_companion.json"
    _require(_sha256_file(path, "D011 preexecution ledger") == entry["file_sha256"],
             "D011 preexecution-ledger file identity mismatch")
    ledger = _read_json(path, "D011 preexecution ledger")
    _require(ledger.get("content_sha256") == entry["content_sha256"],
             "D011 preexecution-ledger content identity mismatch")
    try:
        validate_preexecution_ledger(ledger)
    except Exception as exc:
        raise D011Error("D011 preexecution ledger fails transcript replay") from exc
    _require(ledger.get("pass_id") == "d011_curvature_companion"
             and ledger.get("grid_rule", {}).get("N_axis") == AXIS_COUNT,
             "D011 preexecution-ledger extent mismatch")
    return ledger, manifest


def _coefficient_at(ledger: Mapping[str, Any], card: int, sector: int, budget: int) -> Coefficients:
    rows = ledger.get("coefficient_ledger")
    _require(isinstance(rows, dict), "D011 coefficient ledger is malformed")
    try:
        card_row = rows["cardinality"][card]
        sector_row = rows["sector"][sector]
        budget_row = rows["budget"][budget]
        values = Coefficients(
            alpha=float.fromhex(card_row["alpha_hex"]),
            sector_slack=float.fromhex(sector_row["lambda_slack_hex"]),
            budget_slack=float.fromhex(budget_row["lambda_slack_hex"]),
            sector_linear=float.fromhex(sector_row["lambda_1_hex"]),
            sector_quadratic=float.fromhex(sector_row["lambda_2_hex"]),
            budget_linear=float.fromhex(budget_row["lambda_1_hex"]),
            budget_quadratic=float.fromhex(budget_row["lambda_2_hex"]),
        )
    except (IndexError, KeyError, TypeError, ValueError) as exc:
        raise D011Error("D011 coefficient ledger row is malformed") from exc
    return values


def _coordinate_hex(ledger: Mapping[str, Any], index: int) -> str:
    try:
        row = ledger["coordinates"][index]
        value = row["binary64_hex"]
        _require(row.get("index") == index and isinstance(value, str)
                 and math.isfinite(float.fromhex(value)) and float.fromhex(value) > 0.0,
                 "D011 coordinate row is malformed")
        return value
    except (IndexError, KeyError, TypeError, ValueError) as exc:
        raise D011Error("D011 coordinate row is malformed") from exc


def _key(ledger: Mapping[str, Any], card: int, sector: int, budget: int) -> dict[str, Any]:
    return {
        "ell_card": card,
        "ell_sector": sector,
        "ell_budget": budget,
        "s_card_hex": _coordinate_hex(ledger, card),
        "s_sector_hex": _coordinate_hex(ledger, sector),
        "s_budget_hex": _coordinate_hex(ledger, budget),
    }


def _current_hashes(snapshot: Mapping[str, str]) -> dict[str, str]:
    actual: dict[str, str] = {}
    for relative in snapshot:
        actual[relative] = _sha256_file(ROOT / relative, relative)
    return actual


def _source_snapshot(gate5_snapshot: Mapping[str, str], ledger_manifest: Mapping[str, Any]) -> dict[str, str]:
    snapshot = dict(gate5_snapshot)
    relatives = (
        "src/g6/d011_runner.py", "src/g6/ledgers.py", "src/g6/ratified_g5_input.py",
        "src/g6/g5_digest_registry.py", "src/g6/g5_input.py", D011_SELF_TEST_REL,
        OWNER_DECISIONS_REL, RATIFICATION_REL, REGISTRY_REL,
        f"{PREEXECUTION_REL}/manifest.json", f"{PREEXECUTION_REL}/d011_curvature_companion.json",
    )
    for relative in relatives:
        snapshot[relative] = _sha256_file(ROOT / relative, relative)
    _require(ledger_manifest.get("content_sha256") is not None, "preexecution-ledger manifest lacks identity")
    return snapshot


def _worker_gate() -> list[dict[str, Any]]:
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    records = []
    for relative, expected in ((WORKER_SELF_TEST_REL, "PASS worker self test"),
                               (D011_SELF_TEST_REL, "PASS D011 runner fixtures")):
        for optimized in (False, True):
            command = [sys.executable] + (["-O"] if optimized else []) + [str(ROOT / relative)]
            result = subprocess.run(command, cwd=ROOT, env=environment, text=True, capture_output=True, check=False)
            _require(result.returncode == 0 and result.stdout.strip() == expected,
                     f"worker qualification failed: {relative} optimized={optimized}")
            records.append({"command": " ".join(command), "source": relative,
                            "optimized": optimized, "exit_code": 0})
    return records


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
    from src.g4.energy import objective
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
    h_min, tied, decoded, _ = result
    atomic = [_decoded_record(x, instance, classifier, f_star) for x in decoded]
    labels = {item["atomic_label"] for item in atomic}
    set_label = "C" if "C" in labels else ("A" if labels == {"A"} else "B")
    _require(set_label == classifier.label_set(decoded, f_star), "D016 label reconstruction drift")
    minimum_tau = float((float(c_h) * EPSILON) * float(lambda_ref + abs(h_min)))
    return {
        "H_E_min_hex": h_min.hex(),
        "T_E_size": len(tied),
        "T_E": [_raw_record(item, encoding, instance) for item in tied],
        "X_E_size": len(decoded),
        "X_E": atomic,
        "set_label": set_label,
        "tie_comparator": {"c_H": c_h, "epsilon_hex": EPSILON.hex(), "minimum_tau_hex": minimum_tau.hex()},
    }


def certify_prepared_domain_multi_ch(
    domain: PreparedDomainCache,
    energy_func: Callable,
    lambda_ref: float,
    f_star: float,
    decode_func: Callable,
    classifiers: Mapping[int, DecodedClassifier],
) -> dict[tuple[int, int], tuple]:
    """Extract all fixed D015 c_H/c_f configurations from one energy scan."""
    _require(isinstance(domain, PreparedDomainCache), "domain must be a prepared cache")
    _require(math.isfinite(lambda_ref) and lambda_ref > 0.0, "Lambda_ref must be finite and positive")
    _require(set(classifiers) == {1024, 2048, 4096}, "D015 classifier family mismatch")
    energies = array("d")
    h_min: float | None = None
    for state in domain:
        value = float(energy_func(state))
        _require(math.isfinite(value), "nonfinite prepared energy")
        energies.append(value)
        if h_min is None or value < h_min:
            h_min = value
    _require(h_min is not None, "prepared domain is empty")
    decoded_by_ch: dict[int, tuple[list, list]] = {}
    previous: set[int] = set()
    for c_h in CH_VALUES:
        tied_indices: list[int] = []
        for index, value in enumerate(energies):
            gap = abs(value - h_min)
            scale = lambda_ref + max(abs(value), abs(h_min))
            tie_tau = (float(c_h) * EPSILON) * scale
            _require(math.isfinite(gap) and math.isfinite(scale) and math.isfinite(tie_tau),
                     "nonfinite D015 tie comparator")
            if gap <= tie_tau:
                tied_indices.append(index)
        current = set(tied_indices)
        _require(previous <= current, "D015 tie-set nesting drift")
        previous = current
        tied = [domain.raw_state(index) for index in tied_indices]
        decoded = decode_x_e(tied, decode_func)
        decoded_by_ch[c_h] = (tied, decoded)
    output: dict[tuple[int, int], tuple] = {}
    for c_h, c_f in ((2048, 2048),) + DIAGNOSTIC_PAIRS:
        tied, decoded = decoded_by_ch[c_h]
        classifier = classifiers[c_f]
        output[(c_h, c_f)] = (h_min, tied, decoded, classifier.label_set(decoded, f_star))
    return output


def _certify_point(domains, coefficients: Coefficients, instance, lambda_ref: float, f_star: float) -> dict[str, Any]:
    from src.g4.energy import objective
    prepared = prepare_coefficients(coefficients)
    classifiers = {
        c_f: DecodedClassifier(OriginalObjectiveService(lambda x, base=instance: objective(base, x), lambda_ref, float(c_f)),
                               lambda x, base=instance: _hard_feasible(base, x))
        for c_f in (1024, 2048, 4096)
    }
    unbalanced = certify_prepared_domain_multi_ch(
        domains.unbalanced, lambda state, values=prepared: unbalanced_energy_prepared(state, values),
        lambda_ref, f_star, lambda x: x, classifiers,
    )
    slack = certify_prepared_domain_multi_ch(
        domains.slack, lambda state, values=prepared: slack_energy_prepared(state, values),
        lambda_ref, f_star, lambda state: state[0], classifiers,
    )
    primary = {
        "unbalanced": _render_certification(unbalanced[(2048, 2048)], "unbalanced", instance, classifiers[2048], f_star, lambda_ref, 2048),
        "slack": _render_certification(slack[(2048, 2048)], "slack", instance, classifiers[2048], f_star, lambda_ref, 2048),
    }
    diagnostics: dict[str, Any] = {}
    for c_h, c_f in DIAGNOSTIC_PAIRS:
        diagnostics[f"c_H={c_h}__c_f={c_f}"] = {
            "unbalanced": _render_certification(unbalanced[(c_h, c_f)], "unbalanced", instance, classifiers[c_f], f_star, lambda_ref, c_h),
            "slack": _render_certification(slack[(c_h, c_f)], "slack", instance, classifiers[c_f], f_star, lambda_ref, c_h),
        }
    return {"primary_c_h_2048": primary, "d015_diagnostics": diagnostics}


def _worker_initializer(snapshot: Mapping[str, str], ledger: Mapping[str, Any], run_platform: Mapping[str, Any]) -> None:
    _require(os.environ.get("PYTHONDONTWRITEBYTECODE") == "1", "PYTHONDONTWRITEBYTECODE=1 required")
    _require(_current_hashes(snapshot) == dict(snapshot), "worker source/input snapshot drift")
    _require(_platform_fingerprint() == dict(run_platform), "worker platform differs from run platform")
    worker_gate = _worker_gate()
    instance = load_instance(ROOT / INSTANCE_REL)
    ground_truth = _read_json(ROOT / GROUND_TRUTH_REL, "Gate-3 ground truth")
    try:
        lambda_ref = float(ground_truth["results"]["Lambda_ref"])
        f_star = float(ground_truth["results"]["f_star"])
    except (KeyError, TypeError, ValueError) as exc:
        raise D011Error("Gate-3 ground truth classifier inputs are invalid") from exc
    _require(math.isfinite(lambda_ref) and lambda_ref > 0.0 and math.isfinite(f_star),
             "Gate-3 classifier inputs are nonfinite")
    _require(ledger["inputs"]["lambda_ref_binary64_hex"] == lambda_ref.hex(),
             "D011 ledger and Gate-3 Lambda_ref disagree")
    dummy = Coefficients(1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0)
    domains = prepare_active_domains(instance, build_slack_domain_cache(instance, dummy))
    _require(domains.slack.raw_domain.logical_sha256()
             == "d052e67892d0e39882db26798f881628480d83c0119ee3a1e2ba9b1cdcf03063",
             "D011 slack-domain logical identity drift")
    _STATE.update(snapshot=dict(snapshot), ledger=dict(ledger), platform=dict(run_platform), worker_gate=worker_gate,
                  instance=instance, lambda_ref=lambda_ref, f_star=f_star, domains=domains)


def _compute_shard(task: tuple[int, int]) -> dict[str, Any]:
    _require(_STATE, "D011 worker was not initialized")
    card, sector = task
    ledger = _STATE["ledger"]
    keys, records = [], []
    for budget in range(ROW_COUNT):
        key = _key(ledger, card, sector, budget)
        coefficients = _coefficient_at(ledger, card, sector, budget)
        record = {"key": key, "coefficients_hex": {name: value.hex() for name, value in asdict(coefficients).items()}}
        record.update(_certify_point(_STATE["domains"], coefficients, _STATE["instance"], _STATE["lambda_ref"], _STATE["f_star"]))
        keys.append(key)
        records.append(record)
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "shard_id": _d011_shard_id(card, sector),
        "keys": keys,
        "provenance": {
            "source_snapshot": _STATE["snapshot"],
            "platform": _STATE["platform"],
            "worker_self_test": _STATE["worker_gate"],
            "worker_pid": os.getpid(),
            "ledger_content_sha256": ledger["content_sha256"],
            "domain": {
                "slack_logical_sha256": _STATE["domains"].slack.raw_domain.logical_sha256(),
                "slack_states": len(_STATE["domains"].slack),
                "unbalanced_states": len(_STATE["domains"].unbalanced),
            },
        },
        "records": records,
        "scientific_outputs": "intentionally absent",
    }
    payload["content_sha256"] = _sha256_bytes(canonical_bytes(payload))
    return payload


def _validate_shard(payload: dict[str, Any], ledger: Mapping[str, Any], snapshot: Mapping[str, str],
                    platform_fingerprint: Mapping[str, Any], task: tuple[int, int]) -> None:
    digest = payload.pop("content_sha256", None)
    try:
        _require(isinstance(digest, str) and digest == _sha256_bytes(canonical_bytes(payload)), "D011 shard content hash mismatch")
        card, sector = task
        _require(payload.get("schema") == SCHEMA and payload.get("shard_id") == _d011_shard_id(card, sector),
                 "D011 shard identity mismatch")
        keys = payload.get("keys")
        records = payload.get("records")
        _require(isinstance(keys, list) and isinstance(records, list) and len(keys) == len(records) == ROW_COUNT,
                 "D011 shard row count mismatch")
        expected_keys = [_key(ledger, card, sector, budget) for budget in range(ROW_COUNT)]
        _require(keys == expected_keys and [record.get("key") for record in records] == expected_keys,
                 "D011 shard key/coordinate binding mismatch")
        provenance = payload.get("provenance")
        _require(isinstance(provenance, dict) and provenance.get("source_snapshot") == dict(snapshot)
                 and provenance.get("platform") == dict(platform_fingerprint)
                 and provenance.get("ledger_content_sha256") == ledger["content_sha256"],
                 "D011 shard provenance mismatch")
        _require(payload.get("scientific_outputs") == "intentionally absent", "D011 shard scientific-output boundary violated")
        for record in records:
            coefficient = _coefficient_at(ledger, card, sector, record["key"]["ell_budget"])
            _require(record.get("coefficients_hex") == {name: value.hex() for name, value in asdict(coefficient).items()},
                     "D011 shard coefficient binding mismatch")
            primary = record.get("primary_c_h_2048")
            diagnostics = record.get("d015_diagnostics")
            _require(isinstance(primary, dict) and set(primary) == {"unbalanced", "slack"}
                     and isinstance(diagnostics, dict)
                     and set(diagnostics) == {f"c_H={c_h}__c_f={c_f}" for c_h, c_f in DIAGNOSTIC_PAIRS},
                     "D011 shard D015 configuration mismatch")
    finally:
        if digest is not None:
            payload["content_sha256"] = digest


def _write_manifest(path: Path, payload: Mapping[str, Any]) -> None:
    temporary: Path | None = None
    descriptor: int | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(prefix=".manifest.pending-", dir=path.parent)
        temporary = Path(temporary_name)
        body = dict(payload)
        body["content_sha256"] = _sha256_bytes(canonical_bytes(body))
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = None
            stream.write(canonical_bytes(body))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory_descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except OSError as exc:
        raise D011Error(f"D011 manifest publication failed: {exc}") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


def _promote_payload(output_dir: Path, payload: dict[str, Any], ledger: Mapping[str, Any],
                     snapshot: Mapping[str, str], platform_fingerprint: Mapping[str, Any], task: tuple[int, int]) -> Path:
    _validate_shard(payload, ledger, snapshot, platform_fingerprint, task)
    final = output_dir / f"{payload['shard_id']}.json"
    temporary: Path | None = None
    descriptor: int | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{final.name}.pending-", dir=output_dir)
        temporary = Path(temporary_name)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = None
            stream.write(canonical_bytes(payload))
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o644)
        try:
            os.link(temporary, final)
        except FileExistsError as exc:
            raise D011Error(f"refusing to overwrite existing D011 shard: {final.name}") from exc
        directory_descriptor = os.open(output_dir, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except OSError as exc:
        raise D011Error(f"D011 shard promotion failed: {exc}") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
    return final


class D011Runner:
    """One-pass, resumable D011 controller; it has no other pass mode."""

    def __init__(self, output_dir: Path | str, workers: int = 1, session_hours: float = 2.0,
                 checkpoint_minutes: float = 20.0) -> None:
        _require(isinstance(workers, int) and 1 <= workers <= 8, "D011 workers must be in 1..8")
        _require(session_hours > 0.0 and checkpoint_minutes > 0.0, "D011 time budgets must be positive")
        self.output_dir = Path(output_dir)
        self.workers = workers
        self.session_seconds = session_hours * 3600.0
        self.checkpoint_seconds = checkpoint_minutes * 60.0
        self.tasks = d011_tasks()

    def _require_safe_output_dir(self) -> None:
        """Bind all D011 writes beneath its dedicated Gate-6 artifact root."""
        target = self.output_dir.resolve()
        root = (ROOT / "research/g6").resolve()
        try:
            target.relative_to(root)
        except ValueError as exc:
            raise D011Error("D011 output directory must be inside research/g6") from exc
        _require(target != root, "D011 output directory must be a dedicated research/g6 subdirectory")

    def plan(self) -> dict[str, Any]:
        ledger, manifest = _load_d011_ledger()
        return {
            "pass_id": "d011_curvature_companion",
            "shards": len(self.tasks),
            "coordinates": len(self.tasks) * ROW_COUNT,
            "records_per_coordinate": 2,
            "d015_pairs": [{"c_H": c_h, "c_f": c_f} for c_h, c_f in DIAGNOSTIC_PAIRS],
            "ledger_content_sha256": ledger["content_sha256"],
            "ledger_manifest_content_sha256": manifest["content_sha256"],
            "scientific_outputs": "intentionally absent",
        }

    def _require_disk(self) -> None:
        target = self.output_dir if self.output_dir.exists() else self.output_dir.parent
        try:
            _require(shutil.disk_usage(target).free >= MIN_FREE_BYTES, "available disk space is below 5 GiB")
        except OSError as exc:
            raise D011Error("unable to inspect D011 output disk space") from exc

    def _load_valid(self, ledger: Mapping[str, Any], snapshot: Mapping[str, str], platform_fingerprint: Mapping[str, Any]) -> set[str]:
        completed: set[str] = set()
        task_by_id = {_d011_shard_id(card, sector): (card, sector) for card, sector in self.tasks}
        quarantine = self.output_dir / "quarantine"
        quarantined_this_cycle = 0
        for path in sorted(self.output_dir.glob("d011__card=*_sector=*.json")):
            try:
                payload = _read_json(path, f"D011 shard {path.name}")
                task = task_by_id.get(path.stem)
                _require(task is not None, "unexpected D011 shard filename")
                _validate_shard(payload, ledger, snapshot, platform_fingerprint, task)
                _require(path.stem not in completed, "duplicate D011 shard")
                completed.add(path.stem)
            except Exception as exc:
                quarantine.mkdir(exist_ok=True)
                target = quarantine / f"{path.name}.quarantined"
                _require(not target.exists(), f"D011 quarantine collision: {path.name}")
                os.replace(path, target)
                quarantined_this_cycle += 1
                if quarantined_this_cycle > 3:
                    raise D011Error("more than three D011 shards quarantined in one resume cycle") from exc
        return completed

    def _preflight_existing_output(self, snapshot: Mapping[str, str], ledger: Mapping[str, Any],
                                   platform_fingerprint: Mapping[str, Any]) -> None:
        """Refuse platform/source drift before recovery could quarantine old output."""
        manifest_path = self.output_dir / "resume_manifest.json"
        if manifest_path.is_file():
            manifest = _read_json(manifest_path, "D011 resume manifest")
            _validate_content_hash(manifest, "D011 resume manifest")
            _require(manifest.get("schema") == MANIFEST_SCHEMA
                     and manifest.get("source_snapshot") == dict(snapshot)
                     and manifest.get("ledger_content_sha256") == ledger["content_sha256"]
                     and manifest.get("platform") == dict(platform_fingerprint),
                     "existing D011 resume manifest belongs to a different source/ledger/platform run")
        for path in self.output_dir.glob("d011__card=*_sector=*.json"):
            payload = _read_json(path, f"D011 shard {path.name}")
            provenance = payload.get("provenance")
            _require(isinstance(provenance, dict)
                     and provenance.get("source_snapshot") == dict(snapshot)
                     and provenance.get("platform") == dict(platform_fingerprint)
                     and provenance.get("ledger_content_sha256") == ledger["content_sha256"],
                     "existing D011 shard belongs to a different source/ledger/platform run")

    def _manifest_payload(self, completed: set[str], snapshot: Mapping[str, str], ledger: Mapping[str, Any],
                          platform_fingerprint: Mapping[str, Any], stopped_for_budget: bool,
                          in_progress: bool = False) -> dict[str, Any]:
        return {
            "schema": MANIFEST_SCHEMA,
            "pass_id": "d011_curvature_companion",
            "source_snapshot": dict(snapshot),
            "ledger_content_sha256": ledger["content_sha256"],
            "platform": dict(platform_fingerprint),
            "worker_count": self.workers,
            "completed_shards": sorted(completed),
            "expected_shards": EXPECTED_SHARDS,
            "expected_coordinates": EXPECTED_COORDINATES,
            "stopped_for_budget": stopped_for_budget,
            "in_progress": in_progress,
            "scientific_outputs": "intentionally absent",
        }

    def _coverage_audit(self, completed: set[str], snapshot: Mapping[str, str], ledger: Mapping[str, Any],
                        platform_fingerprint: Mapping[str, Any]) -> dict[str, Any]:
        expected = {_d011_shard_id(card, sector) for card, sector in self.tasks}
        _require(completed == expected, "D011 coverage requires every expected shard")
        payload = {
            "schema": COVERAGE_SCHEMA,
            "pass_id": "d011_curvature_companion",
            "source_snapshot": dict(snapshot),
            "ledger_content_sha256": ledger["content_sha256"],
            "platform": dict(platform_fingerprint),
            "shard_count": EXPECTED_SHARDS,
            "coordinate_count": EXPECTED_COORDINATES,
            "scientific_outputs": "intentionally absent",
        }
        _write_manifest(self.output_dir / "coverage_audit.json", payload)
        return payload

    def run(self) -> dict[str, Any]:
        _require(os.environ.get("PYTHONDONTWRITEBYTECODE") == "1", "PYTHONDONTWRITEBYTECODE=1 required")
        self._require_safe_output_dir()
        self._require_disk()
        ledger, ledger_manifest = _load_d011_ledger()
        try:
            gate5_summary = verify_ratified_g5_corpus()
        except RatifiedG5InputError as exc:
            raise D011Error(f"ratified Gate-5 input verification failed: {exc}") from exc
        snapshot = _source_snapshot(gate5_summary.source_snapshot, ledger_manifest)
        _require(_current_hashes(snapshot) == snapshot, "D011 source/input snapshot drift before run")
        run_platform = _platform_fingerprint()
        _worker_gate()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._preflight_existing_output(snapshot, ledger, run_platform)
        completed = self._load_valid(ledger, snapshot, run_platform)
        pending = [task for task in self.tasks if _d011_shard_id(*task) not in completed]
        if not pending:
            return self._coverage_audit(completed, snapshot, ledger, run_platform)
        deadline = time.monotonic() + self.session_seconds
        dispatch_deadline = max(time.monotonic(), deadline - 600.0)
        checkpoint = time.monotonic()
        last_progress = checkpoint
        next_task = 0
        with mp.get_context("spawn").Pool(self.workers, initializer=_worker_initializer,
                                            initargs=(snapshot, ledger, run_platform)) as pool:
            in_flight = []
            while next_task < len(pending) and len(in_flight) < self.workers and time.monotonic() < dispatch_deadline:
                in_flight.append((pending[next_task], pool.apply_async(_compute_shard, (pending[next_task],))))
                next_task += 1
            while in_flight:
                ready = [(task, job) for task, job in in_flight if job.ready()]
                if not ready:
                    if time.monotonic() - last_progress > WORKER_START_TIMEOUT_SECONDS:
                        raise D011Error("D011 worker initialization or computation made no progress for 15 minutes")
                    time.sleep(0.25)
                    continue
                for task, job in ready:
                    in_flight.remove((task, job))
                    payload = job.get()
                    _require(_current_hashes(snapshot) == snapshot, "D011 source/input snapshot drift during run")
                    _require(payload.get("provenance", {}).get("platform") == run_platform,
                             "D011 worker platform drift")
                    promoted = _promote_payload(self.output_dir, payload, ledger, snapshot, run_platform, task)
                    completed.add(promoted.stem)
                    last_progress = time.monotonic()
                    self._require_disk()
                    if time.monotonic() - checkpoint >= self.checkpoint_seconds:
                        _write_manifest(self.output_dir / "resume_manifest.json",
                                        self._manifest_payload(completed, snapshot, ledger, run_platform, False, True))
                        checkpoint = time.monotonic()
                    if next_task < len(pending) and time.monotonic() < dispatch_deadline:
                        in_flight.append((pending[next_task], pool.apply_async(_compute_shard, (pending[next_task],))))
                        next_task += 1
        stopped = len(completed) != EXPECTED_SHARDS
        _write_manifest(self.output_dir / "resume_manifest.json",
                        self._manifest_payload(completed, snapshot, ledger, run_platform, stopped))
        if not stopped:
            return self._coverage_audit(completed, snapshot, ledger, run_platform)
        return {"completed_shards": len(completed), "remaining_shards": EXPECTED_SHARDS - len(completed),
                "stopped_for_budget": True, "scientific_outputs": "intentionally absent"}

"""Restartable, provenance-bound Gate-5 CSB certification service.

This module produces only per-coordinate certification records. It never
derives rates, compares encodings, or draws a scientific conclusion.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import multiprocessing as mp
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.g4.classification import DecodedClassifier, OriginalObjectiveService
from src.g4.energy import objective
from src.g4.instance import load_instance
from src.g4.parameters import Coefficients
from src.g5.domains import build_slack_domain_cache, prepare_active_domains
from src.g5.runner import certify_prepared_grid

INSTANCE_REL = "research/canonical/stage1_instance.json"
GROUND_TRUTH_REL = "research/ground_truth/G3_GROUND_TRUTH.json"
LEDGER_REL = "research/g4/G4_PRIMARY_LEDGER.json"
WORKER_REL = "research/g5/verify_worker.py"
VECTOR_REL = "research/g5/worker_self_test.json"
DECISIONS_REL = "research/decisions/DECISIONS.md"
SCHEMA = "decisions_os/g5_csb_core_pass/v1"
R_VALUES = (0.5, 1.0, 2.0)
ROW_COUNT = 61
_STATE: dict[str, Any] = {}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _source_snapshot() -> dict[str, str]:
    relatives = (INSTANCE_REL, GROUND_TRUTH_REL, LEDGER_REL, VECTOR_REL, DECISIONS_REL,
                 "research/adnye/ADNYE-001_Lambda_ref.json", "research/adnye/ADNYE-002_s_domain_box.json",
                 "src/g4/instance.py", "src/g4/parameters.py", "src/g4/classification.py", "src/g4/energy.py",
                 "src/g5/domains.py", "src/g5/certify.py", "src/g5/runner.py", "src/g5/core_pass.py", WORKER_REL)
    output: dict[str, str] = {}
    for relative in relatives:
        path = ROOT / relative
        require(path.is_file(), f"required artifact missing: {relative}")
        output[relative] = _sha256(path)
    return output


def _platform_fingerprint() -> dict[str, Any]:
    flags: list[str] = []
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.is_file():
        for line in cpuinfo.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("flags") and ":" in line:
                flags = sorted(line.split(":", 1)[1].split())
                break
    return {"python": sys.version, "implementation": platform.python_implementation(),
            "platform": platform.platform(), "machine": platform.machine(), "cpu_flags": flags,
            "pythonhashseed": os.environ.get("PYTHONHASHSEED", "<unset>"),
            "python_dont_write_bytecode": os.environ.get("PYTHONDONTWRITEBYTECODE", "<unset>")}


def _worker_gate() -> list[dict[str, Any]]:
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    output: list[dict[str, Any]] = []
    for optimized in (False, True):
        command = [sys.executable] + (["-O"] if optimized else []) + [str(ROOT / WORKER_REL)]
        result = subprocess.run(command, cwd=ROOT, env=environment, text=True, capture_output=True, check=False)
        require(result.returncode == 0, f"worker self-test failed: {result.stderr.strip()}")
        require(result.stdout.strip() == "PASS worker self test", "unexpected worker self-test output")
        output.append({"command": " ".join(command), "optimized": optimized, "exit_code": 0})
    return output


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


def _coordinate(ledger: dict[str, Any], ell: int) -> float:
    require(isinstance(ell, int) and 0 <= ell < ROW_COUNT, "ledger index outside 0..60")
    return float.fromhex(ledger["coordinates"][ell]["binary64_hex"])


def _coefficient_family(r: float, s: float, v: float, lambda_ref: float) -> tuple[float, float, float]:
    two_s = float(2.0 * s)
    denominator = float(math.sqrt(float(float(r * r) + two_s)) + r)
    a = float(two_s / denominator)
    v_sq = float(v * v)
    return (float(float(s * lambda_ref) / v_sq), float(float(lambda_ref * a) / v),
            float(float(lambda_ref * float(a * a)) / float(2.0 * v_sq)))


def derive_coefficients(r: float, s_card: float, s_sector: float | None = None, s_budget: float | None = None,
                        lambda_ref: float | None = None) -> Coefficients:
    """Derive a complete D006 coefficient tuple without reparameterization."""
    if lambda_ref is None:  # compatibility: derive_coefficients(r, s, lambda_ref)
        lambda_ref, s_sector, s_budget = s_sector, s_card, s_card
    require(all(isinstance(value, float) and math.isfinite(value) and value > 0.0
                for value in (r, s_card, s_sector, s_budget, lambda_ref)), "invalid coefficient inputs")
    sector_slack, sector_linear, sector_quadratic = _coefficient_family(r, s_sector, 1.0, lambda_ref)
    budget_slack, budget_linear, budget_quadratic = _coefficient_family(r, s_budget, 5.0, lambda_ref)
    return Coefficients(alpha=float(float(s_card * lambda_ref) / 1.0), sector_slack=sector_slack,
                        budget_slack=budget_slack, sector_linear=sector_linear,
                        sector_quadratic=sector_quadratic, budget_linear=budget_linear,
                        budget_quadratic=budget_quadratic)


def _require_r1_ledger_conformance(ledger: dict[str, Any], lambda_ref: float) -> None:
    """Every r=1 axis field must match the frozen ledger bit-for-bit."""
    for card in range(ROW_COUNT):
        value = derive_coefficients(1.0, _coordinate(ledger, card), _coordinate(ledger, 0), _coordinate(ledger, 0), lambda_ref)
        require(value.alpha.hex() == ledger["coefficient_ledger"]["cardinality"][card]["alpha_hex"], "r=1 cardinality ledger mismatch")
    for sector in range(ROW_COUNT):
        value = derive_coefficients(1.0, _coordinate(ledger, 0), _coordinate(ledger, sector), _coordinate(ledger, 0), lambda_ref)
        expected = ledger["coefficient_ledger"]["sector"][sector]
        require(value.sector_slack.hex() == expected["lambda_slack_hex"] and value.sector_linear.hex() == expected["lambda_1_hex"] and value.sector_quadratic.hex() == expected["lambda_2_hex"], "r=1 sector ledger mismatch")
    for budget in range(ROW_COUNT):
        value = derive_coefficients(1.0, _coordinate(ledger, 0), _coordinate(ledger, 0), _coordinate(ledger, budget), lambda_ref)
        expected = ledger["coefficient_ledger"]["budget"][budget]
        require(value.budget_slack.hex() == expected["lambda_slack_hex"] and value.budget_linear.hex() == expected["lambda_1_hex"] and value.budget_quadratic.hex() == expected["lambda_2_hex"], "r=1 budget ledger mismatch")


def _decoded_record(x: tuple[int, ...], instance, classifier, f_star: float) -> dict[str, Any]:
    value = objective(instance, x)
    return {"x_bits": list(x), "selected_tickers": [ticker for ticker, bit in zip(instance.tickers, x, strict=True) if bit],
            "objective_hex": value.hex(), "hard_feasible": _hard_feasible(instance, x), "atomic_label": classifier.label(x, f_star)}


def _raw_record(state: Any, encoding: str, instance) -> dict[str, Any]:
    if encoding == "unbalanced":
        x, output = state, {"x_bits": list(state)}
    else:
        x, auxiliary = state
        output = {"x_bits": list(x), "auxiliary_bits": list(auxiliary)}
    output["selected_tickers"] = [ticker for ticker, bit in zip(instance.tickers, x, strict=True) if bit]
    return output


def _certification_record(result: tuple, encoding: str, instance, classifier, f_star: float, lambda_ref: float) -> dict[str, Any]:
    h_min, tied, decoded, set_label = result
    atomic = [_decoded_record(x, instance, classifier, f_star) for x in decoded]
    require(set_label == classifier.label_set(decoded, f_star), "decoded set label drift")
    epsilon = math.ldexp(1.0, -52)
    tau = float((2048.0 * epsilon) * float(lambda_ref + abs(h_min)))
    return {"H_E_min_hex": h_min.hex(), "T_E_size": len(tied), "T_E": [_raw_record(item, encoding, instance) for item in tied],
            "X_E_size": len(decoded), "X_E": atomic, "set_label": set_label,
            "tie_comparator": {"c_H": 2048, "epsilon_hex": epsilon.hex(), "minimum_tau_hex": tau.hex()}}


def _worker_initializer(snapshot: dict[str, str]) -> None:
    require(os.environ.get("PYTHONDONTWRITEBYTECODE") == "1", "PYTHONDONTWRITEBYTECODE=1 required")
    require(_source_snapshot() == snapshot, "worker source/input snapshot mismatch")
    worker_gate = _worker_gate()
    instance = load_instance(ROOT / INSTANCE_REL)
    ground_truth = json.loads((ROOT / GROUND_TRUTH_REL).read_text(encoding="utf-8"))
    ledger = json.loads((ROOT / LEDGER_REL).read_text(encoding="utf-8"))
    lambda_ref = float(ground_truth["results"]["Lambda_ref"])
    require(lambda_ref.hex() == ledger["inputs"]["lambda_ref_binary64_hex"], "Lambda_ref authority mismatch")
    _require_r1_ledger_conformance(ledger, lambda_ref)
    dummy = Coefficients(alpha=1.0, sector_slack=1.0, budget_slack=1.0, sector_linear=1.0, sector_quadratic=1.0, budget_linear=1.0, budget_quadratic=1.0)
    domains = prepare_active_domains(instance, build_slack_domain_cache(instance, dummy))
    classifier = DecodedClassifier(OriginalObjectiveService(lambda x: objective(instance, x), lambda_ref), lambda x: _hard_feasible(instance, x))
    _STATE.update(instance=instance, ledger=ledger, lambda_ref=lambda_ref, f_star=float(ground_truth["results"]["f_star"]),
                  domains=domains, classifier=classifier, worker_gate=worker_gate, snapshot=snapshot)


def _shard_id(r: float, card: int, sector: int) -> str:
    return f"r={r.hex()}__card={card:02d}__sector={sector:02d}"


def _compute_shard(task: tuple[float, int, int]) -> dict[str, Any]:
    r, card, sector = task
    require(_STATE, "worker was not initialized")
    ledger, instance = _STATE["ledger"], _STATE["instance"]
    points, keys = [], []
    for budget in range(ROW_COUNT):
        points.append(derive_coefficients(r, _coordinate(ledger, card), _coordinate(ledger, sector), _coordinate(ledger, budget), _STATE["lambda_ref"]))
        keys.append({"r_hex": r.hex(), "ell_card": card, "ell_sector": sector, "ell_budget": budget})
    certifications = certify_prepared_grid(_STATE["domains"], points, _STATE["lambda_ref"], _STATE["f_star"], _STATE["classifier"])
    records = []
    for key, certification in zip(keys, certifications, strict=True):
        records.append({"key": key, "coefficients_hex": {name: value.hex() for name, value in asdict(certification.coefficients).items()},
                        "unbalanced": _certification_record(certification.unbalanced, "unbalanced", instance, _STATE["classifier"], _STATE["f_star"], _STATE["lambda_ref"]),
                        "slack": _certification_record(certification.slack, "slack", instance, _STATE["classifier"], _STATE["f_star"], _STATE["lambda_ref"])})
    payload = {"schema": SCHEMA, "shard_id": _shard_id(r, card, sector), "keys": keys,
               "provenance": {"source_snapshot": _STATE["snapshot"], "worker_self_test": _STATE["worker_gate"],
                              "platform": _platform_fingerprint(), "worker_pid": os.getpid(),
                              "domain": {"slack_logical_sha256": _STATE["domains"].slack.raw_domain.logical_sha256(),
                                         "slack_states": len(_STATE["domains"].slack), "unbalanced_states": len(_STATE["domains"].unbalanced)}},
               "records": records}
    payload["content_sha256"] = hashlib.sha256(_canonical_bytes(payload)).hexdigest()
    return payload


def _validate_shard(payload: dict[str, Any], snapshot: dict[str, str]) -> None:
    digest = payload.pop("content_sha256", None)
    require(isinstance(digest, str) and digest == hashlib.sha256(_canonical_bytes(payload)).hexdigest(), "shard digest mismatch")
    require(payload.get("schema") == SCHEMA and len(payload.get("keys", [])) == ROW_COUNT, "malformed shard")
    require(payload["provenance"]["source_snapshot"] == snapshot, "shard snapshot mismatch")
    keys = payload["keys"]
    require(len({(item["r_hex"], item["ell_card"], item["ell_sector"], item["ell_budget"]) for item in keys}) == ROW_COUNT, "duplicate key in shard")
    require([item["ell_budget"] for item in keys] == list(range(ROW_COUNT)), "budget-line coverage malformed")
    require(len(payload.get("records", [])) == ROW_COUNT, "record count mismatch")
    payload["content_sha256"] = digest


def _promote_payload(output_dir: Path, payload: dict[str, Any], snapshot: dict[str, str]) -> Path:
    _validate_shard(payload, snapshot)
    final = output_dir / f"{payload['shard_id']}.json"
    require(not final.exists(), f"refusing to overwrite existing shard: {final.name}")
    descriptor, temporary = tempfile.mkstemp(prefix=".pending-", suffix=".json", dir=output_dir)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
            stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, final)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return final


class CorePassRunner:
    """Persistent-worker, deterministic, restartable G5 core-pass controller."""

    def __init__(self, output_dir: Path | str, workers: int = 8, session_hours: float = 2.0, checkpoint_hours: float = 2.0):
        require(isinstance(workers, int) and 1 <= workers <= 12, "workers must be in 1..12")
        require(session_hours > 0.0 and checkpoint_hours > 0.0, "time budgets must be positive")
        self.output_dir, self.workers = Path(output_dir), workers
        self.session_seconds, self.checkpoint_seconds = session_hours * 3600.0, checkpoint_hours * 3600.0
        self.snapshot = _source_snapshot()
        self.tasks = tuple((r, card, sector) for r in R_VALUES for card in range(ROW_COUNT) for sector in range(ROW_COUNT))

    def dry_run(self) -> int:
        return len(self.tasks)

    def _load_valid(self) -> set[str]:
        complete: set[str] = set(); quarantine = self.output_dir / "quarantine"
        for path in sorted(self.output_dir.glob("r=*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8")); _validate_shard(payload, self.snapshot)
                require(path.stem == payload["shard_id"], "filename/shard id mismatch")
                require(payload["shard_id"] not in complete, "duplicate promoted shard"); complete.add(payload["shard_id"])
            except Exception:
                quarantine.mkdir(exist_ok=True); target = quarantine / f"{path.name}.quarantined"
                require(not target.exists(), f"quarantine collision for {path.name}"); shutil.move(str(path), str(target))
        return complete

    def _write_manifest(self, completed: set[str], stopped_for_budget: bool) -> Path:
        payload = {"schema": SCHEMA + "/resume-manifest", "source_snapshot": self.snapshot, "worker_count": self.workers,
                   "completed_shards": sorted(completed), "expected_shards": len(self.tasks), "stopped_for_budget": stopped_for_budget}
        payload["content_sha256"] = hashlib.sha256(_canonical_bytes(payload)).hexdigest()
        target = self.output_dir / "resume_manifest.json"; temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")), encoding="utf-8"); os.replace(temporary, target)
        return target

    def run(self) -> dict[str, Any]:
        require(os.environ.get("PYTHONDONTWRITEBYTECODE") == "1", "PYTHONDONTWRITEBYTECODE=1 required")
        self.output_dir.mkdir(parents=True, exist_ok=True); completed = self._load_valid()
        pending = [task for task in self.tasks if _shard_id(*task) not in completed]
        if not pending:
            return self.coverage_audit()
        deadline = time.monotonic() + self.session_seconds; dispatch_deadline = max(time.monotonic(), deadline - 600.0)
        dispatched = 0; checkpoint = time.monotonic(); next_task = 0
        with mp.get_context("spawn").Pool(self.workers, initializer=_worker_initializer, initargs=(self.snapshot,)) as pool:
            in_flight = []
            while next_task < len(pending) and len(in_flight) < self.workers and time.monotonic() < dispatch_deadline:
                in_flight.append(pool.apply_async(_compute_shard, (pending[next_task],))); next_task += 1
            while in_flight:
                ready = [job for job in in_flight if job.ready()]
                if not ready:
                    time.sleep(0.25); continue
                for job in ready:
                    in_flight.remove(job)
                    payload = job.get()
                    path = _promote_payload(self.output_dir, payload, self.snapshot); completed.add(path.stem); dispatched += 1
                    if time.monotonic() - checkpoint >= self.checkpoint_seconds:
                        self._write_manifest(completed, True); checkpoint = time.monotonic()
                    if next_task < len(pending) and time.monotonic() < dispatch_deadline:
                        in_flight.append(pool.apply_async(_compute_shard, (pending[next_task],))); next_task += 1
        self._write_manifest(completed, dispatched < len(pending))
        return {"completed": len(completed), "remaining": len(self.tasks) - len(completed), "manifest": str(self.output_dir / "resume_manifest.json")}

    def run_one_shard_trial(self, task: tuple[float, int, int]) -> dict[str, Any]:
        """Execute and promote exactly one explicit shard, then stop.

        This exists solely for the pre-full-pass trial required by the G5
        release decision.  It refuses a pre-existing output and never queues
        another task.
        """
        require(task in self.tasks, "trial task is not a primary CSB shard")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        require(not any(self.output_dir.glob("r=*.json")), "trial directory must be new and empty")
        _worker_initializer(self.snapshot)
        payload = _compute_shard(task)
        path = _promote_payload(self.output_dir, payload, self.snapshot)
        self._write_manifest({path.stem}, True)
        return {"trial_shard": path.name, "content_sha256": payload["content_sha256"], "remaining_shards": len(self.tasks) - 1}

    def coverage_audit(self) -> dict[str, Any]:
        completed = self._load_valid(); expected = {_shard_id(*task) for task in self.tasks}
        require(completed == expected, "coverage audit requires exactly every expected shard")
        payload = {"schema": SCHEMA + "/coverage-audit", "source_snapshot": self.snapshot,
                   "shard_count": len(completed), "coordinate_count": len(completed) * ROW_COUNT,
                   "scientific_outputs": "intentionally absent"}
        payload["content_sha256"] = hashlib.sha256(_canonical_bytes(payload)).hexdigest()
        (self.output_dir / "coverage_audit.json").write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")), encoding="utf-8")
        return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True); parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--session-hours", type=float, default=2.0); parser.add_argument("--checkpoint-hours", type=float, default=2.0)
    mode = parser.add_mutually_exclusive_group(required=True); mode.add_argument("--dry-run", action="store_true"); mode.add_argument("--run", action="store_true"); mode.add_argument("--trial", action="store_true")
    args = parser.parse_args(); runner = CorePassRunner(args.output_dir, args.workers, args.session_hours, args.checkpoint_hours)
    if args.dry_run:
        output = {"deterministic_shards": runner.dry_run(), "coordinates": runner.dry_run() * ROW_COUNT, "snapshot": runner.snapshot}
    elif args.trial:
        output = runner.run_one_shard_trial((1.0, 30, 30))
    else:
        output = runner.run()
    print(json.dumps(output, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

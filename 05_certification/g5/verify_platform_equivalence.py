"""Read-only Gate-5 numerical-equivalence verifier for a platform split.

This is a post-core-pass verifier, not a producer.  It identifies the minority
platform-fingerprint population in a complete G5 corpus, recomputes those exact
shards using the current pinned source snapshot, and compares every output field
other than the non-deterministic worker PID and its dependent content digest.
It never creates, moves, edits, or deletes a file in the core-pass output
directory.

Passing this verifier establishes reproducibility on the current platform.  It
does not override SHARD_PROVENANCE_CONTRACT.md's uniform-platform requirement;
that remains an explicit owner/reviewer decision.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import multiprocessing as mp
import os
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.g5 import core_pass

SCHEMA = "decisions_os/g5_platform_equivalence_audit/v1"
CHECKPOINT_EVERY = 12


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def canonical_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def sha256_payload(payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    os.replace(temporary, path)


def validate_stored_payload(payload: dict[str, Any], snapshot: dict[str, str]) -> None:
    candidate = copy.deepcopy(payload)
    core_pass._validate_shard(candidate, snapshot)


def task_from_payload(payload: dict[str, Any]) -> tuple[float, int, int]:
    keys = payload["keys"]
    require(len(keys) == core_pass.ROW_COUNT, "stored shard has malformed keys")
    first = keys[0]
    r = float.fromhex(first["r_hex"])
    card, sector = first["ell_card"], first["ell_sector"]
    expected = [{"r_hex": r.hex(), "ell_card": card, "ell_sector": sector, "ell_budget": budget}
                for budget in range(core_pass.ROW_COUNT)]
    require(keys == expected, "stored shard keys are not a canonical budget line")
    require(payload["shard_id"] == core_pass._shard_id(r, card, sector), "stored shard id does not match keys")
    return r, card, sector


def comparison_projection(payload: dict[str, Any]) -> dict[str, Any]:
    """Remove exactly the per-process fields that cannot repeat across a run."""
    result = copy.deepcopy(payload)
    result.pop("content_sha256", None)
    provenance = result.get("provenance")
    require(isinstance(provenance, dict), "payload lacks provenance")
    provenance.pop("worker_pid", None)
    return result


def mismatch_sections(stored: dict[str, Any], fresh: dict[str, Any]) -> list[str]:
    labels = ("schema", "shard_id", "keys", "records", "provenance")
    return [label for label in labels if stored.get(label) != fresh.get(label)]


def worker_initializer(snapshot: dict[str, str]) -> None:
    core_pass._worker_initializer(snapshot)


def verify_one(item: tuple[str, str, tuple[float, int, int], dict[str, str]]) -> dict[str, Any]:
    shard_id, path_string, task, snapshot = item
    try:
        stored = json.loads(Path(path_string).read_text(encoding="utf-8"))
        validate_stored_payload(stored, snapshot)
        fresh = core_pass._compute_shard(task)
        core_pass._validate_shard(fresh, snapshot)
        stored_view, fresh_view = comparison_projection(stored), comparison_projection(fresh)
        return {
            "shard_id": shard_id,
            "ok": stored_view == fresh_view,
            "stored_projection_sha256": sha256_payload(stored_view),
            "fresh_projection_sha256": sha256_payload(fresh_view),
            "mismatch_sections": mismatch_sections(stored_view, fresh_view),
        }
    except Exception as error:  # Fail closed and preserve concise diagnostic evidence.
        return {"shard_id": shard_id, "ok": False, "error_type": type(error).__name__, "error": str(error)}


def load_population(output_dir: Path, snapshot: dict[str, str]) -> tuple[list[tuple[str, Path, tuple[float, int, int]]], dict[str, Any], dict[str, Any]]:
    paths = sorted(output_dir.glob("r=*.json"))
    require(len(paths) == 11163, f"expected 11163 promoted shards, found {len(paths)}")
    all_rows: list[tuple[str, Path, tuple[float, int, int], dict[str, Any]]] = []
    platforms: Counter[str] = Counter()
    platform_values: dict[str, dict[str, Any]] = {}
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        validate_stored_payload(payload, snapshot)
        task = task_from_payload(payload)
        key = json.dumps(payload["provenance"]["platform"], sort_keys=True, separators=(",", ":"))
        platforms[key] += 1
        platform_values[key] = payload["provenance"]["platform"]
        all_rows.append((payload["shard_id"], path, task, payload))
    require(len(platforms) == 2, f"expected exactly two platform fingerprints, found {len(platforms)}")
    ordered = platforms.most_common()
    baseline_key, baseline_count = ordered[0]
    divergent_key, divergent_count = ordered[1]
    require(baseline_count > divergent_count, "platform populations do not have a unique majority baseline")
    targets = [(shard_id, path, task) for shard_id, path, task, payload in all_rows
               if payload["provenance"]["platform"] == platform_values[divergent_key]]
    require(len(targets) == divergent_count, "target population selection drift")
    return targets, platform_values[baseline_key], platform_values[divergent_key]


def make_metadata(output_dir: Path, targets: list[tuple[str, Path, tuple[float, int, int]]], snapshot: dict[str, str],
                  baseline: dict[str, Any], divergent: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": SCHEMA + "/checkpoint",
        "output_directory": str(output_dir.resolve()),
        "source_snapshot": snapshot,
        "baseline_platform": baseline,
        "recomputed_platform_expected": divergent,
        "target_shard_ids": [shard_id for shard_id, _, _ in targets],
    }


def load_or_create_checkpoint(path: Path, metadata: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return {**metadata, "completed": {}, "started_unix": time.time()}
    checkpoint = json.loads(path.read_text(encoding="utf-8"))
    for key, value in metadata.items():
        require(checkpoint.get(key) == value, f"checkpoint metadata mismatch: {key}")
    require(isinstance(checkpoint.get("completed"), dict), "checkpoint completed set malformed")
    require(set(checkpoint["completed"]).issubset(set(metadata["target_shard_ids"])), "checkpoint contains foreign shard")
    return checkpoint


def final_report(checkpoint: dict[str, Any], report_path: Path) -> dict[str, Any]:
    completed = checkpoint["completed"]
    target_ids = checkpoint["target_shard_ids"]
    require(set(completed) == set(target_ids), "cannot report before every target is compared")
    failures = {shard_id: result for shard_id, result in completed.items() if not result.get("ok", False)}
    payload = {
        "schema": SCHEMA + "/report",
        "verdict": "PASS" if not failures else "FAIL",
        "target_shard_count": len(target_ids),
        "coordinate_count": len(target_ids) * core_pass.ROW_COUNT,
        "baseline_platform": checkpoint["baseline_platform"],
        "recomputed_platform": checkpoint["recomputed_platform_expected"],
        "source_snapshot": checkpoint["source_snapshot"],
        "exact_projection_matches": len(target_ids) - len(failures),
        "mismatch_count": len(failures),
        "mismatches": failures,
        "scope": "read-only comparison against existing core_pass_output; no core-pass artifact was modified",
        "contract_boundary": "A PASS establishes current-platform reproduction only; it does not override the frozen uniform-platform-fingerprint merge rule.",
        "completed_unix": time.time(),
    }
    payload["content_sha256"] = sha256_payload(payload)
    atomic_json(report_path, payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "research/g5/core_pass_output")
    parser.add_argument("--audit-dir", type=Path, default=ROOT / "research/g5/platform_equivalence_audit_v1")
    parser.add_argument("--workers", type=int, default=12)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--run", action="store_true")
    args = parser.parse_args()
    require(os.environ.get("PYTHONDONTWRITEBYTECODE") == "1", "PYTHONDONTWRITEBYTECODE=1 required")
    require(1 <= args.workers <= 12, "workers must be in 1..12")
    snapshot = core_pass._source_snapshot()
    targets, baseline, divergent = load_population(args.output_dir, snapshot)
    metadata = make_metadata(args.output_dir, targets, snapshot, baseline, divergent)
    if args.dry_run:
        print(json.dumps({"mode": "dry-run", "target_shards": len(targets), "coordinates": len(targets) * core_pass.ROW_COUNT,
                          "baseline_platform": baseline, "target_platform": divergent}, sort_keys=True))
        return 0

    checkpoint_path = args.audit_dir / "checkpoint.json"
    report_path = args.audit_dir / "report.json"
    checkpoint = load_or_create_checkpoint(checkpoint_path, metadata)
    pending = [(shard_id, str(path), task, snapshot) for shard_id, path, task in targets if shard_id not in checkpoint["completed"]]
    if pending:
        with mp.get_context("spawn").Pool(args.workers, initializer=worker_initializer, initargs=(snapshot,)) as pool:
            for index, result in enumerate(pool.imap_unordered(verify_one, pending), start=1):
                checkpoint["completed"][result["shard_id"]] = result
                if index % CHECKPOINT_EVERY == 0:
                    atomic_json(checkpoint_path, checkpoint)
                    print(json.dumps({"completed": len(checkpoint["completed"]), "target": len(targets)}, sort_keys=True), flush=True)
    atomic_json(checkpoint_path, checkpoint)
    report = final_report(checkpoint, report_path)
    print(json.dumps({"verdict": report["verdict"], "target_shards": report["target_shard_count"],
                      "exact_projection_matches": report["exact_projection_matches"], "mismatch_count": report["mismatch_count"],
                      "report": str(report_path)}, sort_keys=True))
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

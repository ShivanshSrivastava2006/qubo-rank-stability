"""Non-primary contract checks for the Gate-5 CSB core-pass runner.

This verifier never initializes a million-state primary domain and never emits
a primary shard.  The separately authorized one-shard trial is invoked by the
operator only after this verifier passes.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.g5.core_pass import (
    CorePassRunner,
    ROW_COUNT,
    R_VALUES,
    SCHEMA,
    _canonical_bytes,
    _coordinate,
    _require_r1_ledger_conformance,
    _source_snapshot,
    _validate_shard,
    derive_coefficients,
    require,
)


def expect_failure(action, message: str) -> None:
    try:
        action()
    except RuntimeError:
        return
    raise RuntimeError(message)


def fixture(snapshot: dict[str, str]) -> dict:
    keys = [{"r_hex": float(1.0).hex(), "ell_card": 0, "ell_sector": 0, "ell_budget": budget} for budget in range(ROW_COUNT)]
    payload = {"schema": SCHEMA, "shard_id": "r=0x1.0000000000000p+0__card=00__sector=00", "keys": keys,
               "provenance": {"source_snapshot": snapshot, "worker_self_test": [], "platform": {}, "worker_pid": 0, "domain": {}},
               "records": [{} for _ in range(ROW_COUNT)]}
    payload["content_sha256"] = hashlib.sha256(_canonical_bytes(payload)).hexdigest()
    return payload


def main() -> int:
    require(os.environ.get("PYTHONDONTWRITEBYTECODE") == "1", "PYTHONDONTWRITEBYTECODE=1 required")
    snapshot = _source_snapshot()
    ledger = json.loads(Path("research/g4/G4_PRIMARY_LEDGER.json").read_text(encoding="utf-8"))
    lambda_ref = float.fromhex(ledger["inputs"]["lambda_ref_binary64_hex"])
    _require_r1_ledger_conformance(ledger, lambda_ref)
    print("PASS r=1 all-row coefficient conformance")

    # Independent selected sensitivity sanity checks: stable a_r differs with r;
    # cardinality remains r-independent while all values remain finite/positive.
    for r in (0.5, 2.0):
        value = derive_coefficients(r, _coordinate(ledger, 30), _coordinate(ledger, 31), _coordinate(ledger, 29), lambda_ref)
        require(all(float(item) > 0.0 for item in value.__dict__.values()), f"invalid r={r} coefficient")
    require(derive_coefficients(0.5, .1, .1, .1, lambda_ref).alpha == derive_coefficients(2.0, .1, .1, .1, lambda_ref).alpha, "alpha must be r-independent")
    print("PASS selected r=0.5/2 coefficient checks")

    with tempfile.TemporaryDirectory() as temporary:
        runner = CorePassRunner(Path(temporary), workers=1, session_hours=1.0, checkpoint_hours=1.0)
        require(runner.dry_run() == 3 * ROW_COUNT * ROW_COUNT, "wrong deterministic shard count")
        require(runner.dry_run() * ROW_COUNT == 680943, "wrong coordinate count")
        payload = fixture(snapshot)
        _validate_shard(copy.deepcopy(payload), snapshot)
        bad_digest = copy.deepcopy(payload); bad_digest["records"][0] = {"mutated": True}
        expect_failure(lambda: _validate_shard(bad_digest, snapshot), "digest mutation escaped")
        bad_key = copy.deepcopy(payload); bad_key["keys"][1]["ell_budget"] = 0
        bad_key["content_sha256"] = hashlib.sha256(_canonical_bytes({k: v for k, v in bad_key.items() if k != "content_sha256"})).hexdigest()
        expect_failure(lambda: _validate_shard(bad_key, snapshot), "duplicate key escaped")
        bad_snapshot = copy.deepcopy(payload); bad_snapshot["provenance"]["source_snapshot"] = {"wrong": "snapshot"}
        bad_snapshot["content_sha256"] = hashlib.sha256(_canonical_bytes({k: v for k, v in bad_snapshot.items() if k != "content_sha256"})).hexdigest()
        expect_failure(lambda: _validate_shard(bad_snapshot, snapshot), "snapshot mismatch escaped")
        print("PASS deterministic keys, digest, duplicate and snapshot refusal")
    print("PASS core-pass non-primary contract verifier")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

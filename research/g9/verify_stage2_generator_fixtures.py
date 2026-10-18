#!/usr/bin/env python3
"""Synthetic, non-writing fixtures for the approved Stage-2 generator implementation.

The fixtures do not load the canonical Stage-1 instance and do not draw any
Stage-2 candidate.  All return/covariance samples use an artificial 20-asset
mean/covariance solely to exercise U-09 mechanics.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from research.g9 import stage2_generator as m  # noqa: E402


class FixtureError(RuntimeError):
    pass


def require(ok: bool, message: str) -> None:
    if not ok:
        raise FixtureError(message)


def rejected(fn, label: str) -> None:
    try:
        fn()
    except m.Stage2GenerationError:
        return
    except Exception as exc:
        raise FixtureError(f"{label}: raw {type(exc).__name__} instead of Stage2GenerationError") from exc
    raise FixtureError(f"{label}: accepted")


def synthetic_partition() -> tuple[tuple[int, ...], ...]:
    return tuple(tuple(range(start, start + 5)) for start in range(0, 20, 5))


def check_seeds() -> None:
    sample = m.stream_seed(1, 0, "returns")
    material = "decisions_os/stage2/v1|master=1592594996|slot=01|attempt=0|purpose=returns"
    digest = hashlib.sha256(material.encode("ascii")).digest()
    require(sample.material_ascii == material and sample.material_sha256 == digest.hex()
            and sample.seed_uint128 == int.from_bytes(digest[:16], "big"), "seed material drift")
    require(m.stream_seed(1, 0, "returns") == sample, "seed determinism")
    require(m.stream_seed(1, 0, "sectors").seed_uint128 != sample.seed_uint128, "purpose streams collide")
    require(m.stream_seed(2, 0, "returns").seed_uint128 != sample.seed_uint128, "slot streams collide")
    require(m.stream_seed(1, 1, "returns").seed_uint128 != sample.seed_uint128, "attempt streams collide")
    for raw in ((0, 0, "returns"), (6, 0, "returns"), (1, -1, "returns"), (1, 128, "returns"),
                (True, 0, "returns"), (1, 0, "other"), (1, 0, True)):
        rejected(lambda raw=raw: m.stream_seed(*raw), f"invalid seed {raw!r}")


def check_partitions_and_screen() -> None:
    first = m.sector_blocks(1, 0)
    require(first == m.sector_blocks(1, 0), "partition sampling is not deterministic")
    normalized = m.normalized_partition(first)
    require(len(normalized) == 4 and all(len(block) == 5 for block in normalized)
            and tuple(sorted(value for block in normalized for value in block)) == tuple(range(20)), "balanced partition drift")
    relabelled = tuple(reversed(first))
    require(m.normalized_partition(first) == m.normalized_partition(relabelled), "partition normalization depends on labels")
    require(m.partition_digest(first) == m.partition_digest(relabelled), "partition digest depends on labels")
    for bad in (
        ((0, 1, 2, 3, 4),) * 4,
        ((0, 1, 2, 3), (4, 5, 6, 7, 8), (9, 10, 11, 12, 13), (14, 15, 16, 17, 18)),
        ((0, 1, 2, 3, 4), (5, 6, 7, 8, 9), (10, 11, 12, 13, 14), (15, 16, 17, 18, 20)),
    ):
        rejected(lambda bad=bad: m.normalized_partition(bad), "malformed partition")
    prices = (1,) * 20
    partition = synthetic_partition()
    expected = sum(
        1 for chosen in __import__("itertools").combinations(range(20), 6)
        if all(sum(index in block for index in chosen) <= 2 for block in partition)
    )
    require(m.feasibility_count(prices, partition, 6, 2, 6) == expected, "feasibility count drift")
    rejected(lambda: m.feasibility_count((1,) * 19, partition, 6, 2, 6), "short prices")
    rejected(lambda: m.feasibility_count((1,) * 19 + (1.5,), partition, 6, 2, 6), "noninteger price")
    rejected(lambda: m.feasibility_count(prices, partition, 6.5, 2, 6), "noninteger K")
    screen = m.screen_attempt(prices=prices, K=6, C=2, B=6, stage1_partition=synthetic_partition(),
                              earlier_accepted_partitions=(), slot=1, attempt=0)
    require(screen.returns_seed.purpose == "returns" and screen.sectors_seed.purpose == "sectors"
            and type(screen.feasible_count) is int and screen.partition_sha256 == m.partition_digest(screen.normalized_partition), "screen shape drift")
    duplicate = m.screen_attempt(prices=prices, K=6, C=2, B=6, stage1_partition=screen.normalized_partition,
                                 earlier_accepted_partitions=(screen.normalized_partition,), slot=1, attempt=0)
    require(duplicate.rejection_codes[:2] == ("partition_matches_stage1", "partition_matches_earlier_accepted"), "duplicate rejection codes drift")
    impossible = m.screen_attempt(prices=prices, K=6, C=0, B=6, stage1_partition=synthetic_partition(),
                                  earlier_accepted_partitions=(), slot=1, attempt=0)
    require("feasible_set_below_100" in impossible.rejection_codes, "feasibility floor drift")


def check_returns() -> None:
    mean = [float(index) / 1000.0 for index in range(20)]
    covariance = [[0.0] * 20 for _ in range(20)]
    for index in range(20):
        covariance[index][index] = 0.01 + index / 10000.0
    first = m.sample_return_covariance(mean, covariance, 1, 0)
    second = m.sample_return_covariance(mean, covariance, 1, 0)
    require(first.return_matrix_sha256_le_f64_row_major == second.return_matrix_sha256_le_f64_row_major
            and first.mu_hex == second.mu_hex and first.sigma_hex == second.sigma_hex, "return draw nondeterminism")
    require(first.returns.shape == (249, 20) and first.mu.shape == (20,) and first.sigma.shape == (20, 20), "return shape drift")
    require(bool((first.sigma == first.sigma.T).all()) and len(first.mu_hex) == 20 and len(first.sigma_hex) == 20, "covariance construction drift")
    # A dense positive-definite covariance forces NumPy's SVD reconstruction
    # path.  This guards against accidentally restoring a zero tolerance,
    # which rejects valid dense binary64 matrices solely from SVD roundoff.
    dense_covariance = [
        [(0.01 if row == column else 0.0) + 0.00001 * ((row + 1) * (column + 1))
         for column in range(20)]
        for row in range(20)
    ]
    dense_first = m.sample_return_covariance(mean, dense_covariance, 1, 0)
    dense_second = m.sample_return_covariance(mean, dense_covariance, 1, 0)
    require(dense_first.return_matrix_sha256_le_f64_row_major == dense_second.return_matrix_sha256_le_f64_row_major,
            "dense PSD draw nondeterminism or SVD tolerance drift")
    nonsymmetric = [row[:] for row in covariance]
    nonsymmetric[0][1] = 0.2
    rejected(lambda: m.sample_return_covariance(mean, nonsymmetric, 1, 0), "nonsymmetric covariance")
    nonfinite = [row[:] for row in covariance]
    nonfinite[0][0] = float("nan")
    rejected(lambda: m.sample_return_covariance(mean, nonfinite, 1, 0), "nonfinite covariance")
    indefinite = [row[:] for row in covariance]
    indefinite[0][0] = -1.0
    rejected(lambda: m.sample_return_covariance(mean, indefinite, 1, 0), "indefinite covariance")
    rejected(lambda: m.sample_return_covariance(mean[:-1], covariance, 1, 0), "short mean")


def check_plan_cli() -> None:
    runner = ROOT / "research/g9/plan_stage2_generator.py"
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    normal = subprocess.run([sys.executable, str(runner), "--plan"], cwd=ROOT, env=env, capture_output=True, text=True, check=True)
    optimized = subprocess.run([sys.executable, "-O", str(runner), "--plan"], cwd=ROOT, env=env, capture_output=True, text=True, check=True)
    require(normal.stdout == optimized.stdout, "plan differs under -O")
    payload = json.loads(normal.stdout)
    require(payload["writes"] == "none" and payload["candidate_draws"] == "intentionally absent"
            and payload["slots"] == [1, 2, 3, 4, 5] and payload["attempt_range"] == [0, 127]
            and len(payload["runtime"]["numpy_linalg_backend_sha256"]) == 64
            and payload["runtime"]["numpy_blas"] and payload["runtime"]["numpy_lapack"]
            and payload["return_draw"] == {"method": "svd", "check_valid": "raise", "svd_tolerance": float(1.0e-8).hex()},
            "plan payload drift")
    bare_env = {key: value for key, value in os.environ.items() if key != "PYTHONDONTWRITEBYTECODE"}
    refused = subprocess.run([sys.executable, "-B", str(runner), "--plan"], cwd=ROOT, env=bare_env, capture_output=True, text=True)
    require(refused.returncode != 0 and "PYTHONDONTWRITEBYTECODE=1" in refused.stderr, "missing-env guard drift")


def main() -> int:
    require(not (ROOT / "research/g9/stage2_generation").exists(), "fixture must not create a generation artifact directory")
    check_seeds()
    check_partitions_and_screen()
    check_returns()
    check_plan_cli()
    print("PASS Stage-2 generator fixtures; synthetic inputs only, no Stage-2 candidate or output")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

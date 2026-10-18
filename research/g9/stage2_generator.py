"""Pure, non-writing implementation of the approved Gate-9 Stage-2 generator.

This module deliberately has no command that draws or writes a Stage-2
candidate.  Its functions are exercised only with synthetic fixture inputs
until the separately reviewed pre-run boundary is authorized.  It fixes the
prospective U-08--U-11 mechanics: stream derivation, balanced partitioning,
feasibility counting, and parametric return/covariance construction.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import itertools
import json
import math
import sys
from typing import Iterable, Sequence

import numpy as np


MASTER_SEED = 1_592_594_996
MASTER_SEED_HEX = "0x5EED2024"
PROTOCOL_PREFIX = "decisions_os/stage2/v1"
SLOT_COUNT = 5
MAX_ATTEMPT = 127
ASSET_COUNT = 20
SECTOR_COUNT = 4
SECTOR_SIZE = 5
RETURN_ROWS = 249
EXPECTED_PYTHON = "3.12.3"
EXPECTED_NUMPY = "2.4.4"
PURPOSES = ("returns", "sectors")
# NumPy's SVD validity check is a tolerance check on its own rounded
# reconstruction.  The independent exact-symmetry and PSD checks below are
# the acceptance boundary for Sigma; this permits only that harmless SVD
# roundoff when drawing a valid dense covariance.
DRAW_METHOD = "svd"
DRAW_CHECK_VALID = "raise"
DRAW_SVD_TOLERANCE = 1.0e-8


class Stage2GenerationError(ValueError):
    """Typed refusal for a malformed prospective generator input."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise Stage2GenerationError(message)


def _int(value: object, name: str, minimum: int | None = None, maximum: int | None = None) -> int:
    _require(type(value) is int, f"{name} must be an int")
    if minimum is not None:
        _require(value >= minimum, f"{name} is below its permitted range")
    if maximum is not None:
        _require(value <= maximum, f"{name} is above its permitted range")
    return value


def runtime_fingerprint() -> dict[str, str]:
    """Return the limited runtime identity the implementation later pins."""
    dependencies = np.__config__.CONFIG.get("Build Dependencies", {})
    backend = {
        name: {
            "name": str(dependencies.get(name, {}).get("name", "")),
            "version": str(dependencies.get(name, {}).get("version", "")),
            "configuration": str(dependencies.get(name, {}).get("openblas configuration", "")),
        }
        for name in ("blas", "lapack")
    }
    backend_sha256 = hashlib.sha256(
        json.dumps(backend, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    ).hexdigest()
    return {
        "implementation": sys.implementation.name,
        "python": sys.version,
        "python_version": ".".join(str(value) for value in sys.version_info[:3]),
        "numpy_version": np.__version__,
        "numpy_linalg_backend_sha256": backend_sha256,
        "numpy_blas": backend["blas"]["name"],
        "numpy_lapack": backend["lapack"]["name"],
    }


def require_approved_runtime() -> dict[str, str]:
    """Refuse a runtime other than the prospective protocol baseline."""
    fingerprint = runtime_fingerprint()
    _require(fingerprint["implementation"] == "cpython", "CPython is required")
    _require(fingerprint["python_version"] == EXPECTED_PYTHON, "unexpected CPython version")
    _require(fingerprint["numpy_version"] == EXPECTED_NUMPY, "unexpected NumPy version")
    return fingerprint


@dataclass(frozen=True)
class StreamSeed:
    """Exact U-08 commitment for one independent random stream."""

    slot: int
    attempt: int
    purpose: str
    material_ascii: str
    material_sha256: str
    seed_uint128: int


def stream_seed(slot: int, attempt: int, purpose: str) -> StreamSeed:
    """Derive one U-08 SHA-256/PCG64 stream commitment without sampling it."""
    _int(slot, "slot", 1, SLOT_COUNT)
    _int(attempt, "attempt", 0, MAX_ATTEMPT)
    _require(type(purpose) is str and purpose in PURPOSES, "unknown stream purpose")
    material = (
        f"{PROTOCOL_PREFIX}|master={MASTER_SEED}|slot={slot:02d}|"
        f"attempt={attempt}|purpose={purpose}"
    )
    digest = hashlib.sha256(material.encode("ascii")).digest()
    return StreamSeed(
        slot=slot,
        attempt=attempt,
        purpose=purpose,
        material_ascii=material,
        material_sha256=digest.hex(),
        seed_uint128=int.from_bytes(digest[:16], "big", signed=False),
    )


def stream_rng(slot: int, attempt: int, purpose: str) -> tuple[np.random.Generator, StreamSeed]:
    """Construct an isolated PCG64 generator for one declared stream."""
    commitment = stream_seed(slot, attempt, purpose)
    return np.random.Generator(np.random.PCG64(commitment.seed_uint128)), commitment


def _integer_prices(prices: Sequence[object]) -> tuple[int, ...]:
    _require(not isinstance(prices, (str, bytes)), "prices must be a sequence")
    _require(len(prices) == ASSET_COUNT, "price vector must have exactly 20 entries")
    values: list[int] = []
    for index, raw in enumerate(prices):
        _require(type(raw) in (int, float), f"price[{index}] has a non-numeric type")
        value = float(raw)
        _require(math.isfinite(value) and value > 0.0 and value.is_integer(), f"price[{index}] must be a positive integer")
        values.append(int(value))
    return tuple(values)


def _integer_scalar(value: object, name: str, minimum: int = 0) -> int:
    _require(type(value) in (int, float), f"{name} has a non-numeric type")
    as_float = float(value)
    _require(math.isfinite(as_float) and as_float.is_integer(), f"{name} must be an integer")
    as_int = int(as_float)
    _require(as_int >= minimum, f"{name} is below its permitted range")
    return as_int


def normalized_partition(sectors: Iterable[Iterable[object]]) -> tuple[tuple[int, ...], ...]:
    """Represent sector blocks label-blindly for U-10 duplicate checks."""
    try:
        blocks = tuple(tuple(block) for block in sectors)
    except TypeError as exc:
        raise Stage2GenerationError("sectors must be an iterable of blocks") from exc
    _require(len(blocks) == SECTOR_COUNT, "partition must contain exactly four sectors")
    normalized: list[tuple[int, ...]] = []
    flattened: list[int] = []
    for sector_index, block in enumerate(blocks):
        _require(len(block) == SECTOR_SIZE, f"sector[{sector_index}] must contain exactly five assets")
        members = tuple(_int(value, f"sector[{sector_index}] member", 0, ASSET_COUNT - 1) for value in block)
        _require(len(set(members)) == SECTOR_SIZE, f"sector[{sector_index}] repeats an asset")
        normalized.append(tuple(sorted(members)))
        flattened.extend(members)
    _require(tuple(sorted(flattened)) == tuple(range(ASSET_COUNT)), "partition must cover each asset exactly once")
    return tuple(sorted(normalized))


def sector_blocks(slot: int, attempt: int) -> tuple[tuple[int, ...], ...]:
    """Draw the labelled four-block partition from the independent sector stream."""
    rng, _ = stream_rng(slot, attempt, "sectors")
    permutation = tuple(int(value) for value in rng.permutation(ASSET_COUNT))
    return tuple(
        permutation[offset: offset + SECTOR_SIZE]
        for offset in range(0, ASSET_COUNT, SECTOR_SIZE)
    )


def feasibility_count(
    prices: Sequence[object],
    sectors: Iterable[Iterable[object]],
    K: object,
    C: object,
    B: object,
) -> int:
    """Exact U-11 screen: count only cardinality/sector/budget-feasible portfolios."""
    p = _integer_prices(prices)
    partition = normalized_partition(sectors)
    k = _integer_scalar(K, "K", 1)
    cap = _integer_scalar(C, "C", 0)
    budget = _integer_scalar(B, "B", 0)
    _require(k <= ASSET_COUNT, "K exceeds asset count")
    membership = [-1] * ASSET_COUNT
    for sector_index, block in enumerate(partition):
        for asset in block:
            membership[asset] = sector_index
    total = 0
    for chosen in itertools.combinations(range(ASSET_COUNT), k):
        if sum(p[index] for index in chosen) > budget:
            continue
        counts = [0] * SECTOR_COUNT
        for index in chosen:
            counts[membership[index]] += 1
        if all(count <= cap for count in counts):
            total += 1
    return total


@dataclass(frozen=True)
class AttemptScreen:
    """Non-scientific U-10/U-11 outcome for one attempt; no objective is used."""

    slot: int
    attempt: int
    returns_seed: StreamSeed
    sectors_seed: StreamSeed
    sector_blocks: tuple[tuple[int, ...], ...]
    normalized_partition: tuple[tuple[int, ...], ...]
    partition_sha256: str
    feasible_count: int
    rejection_codes: tuple[str, ...]

    @property
    def accepted(self) -> bool:
        return not self.rejection_codes


def partition_digest(partition: tuple[tuple[int, ...], ...]) -> str:
    """Hash the label-blind partition in an unambiguous ASCII form."""
    normalized = normalized_partition(partition)
    material = "|".join(
        ",".join(str(member) for member in block) for block in normalized
    )
    return hashlib.sha256(material.encode("ascii")).hexdigest()


def screen_attempt(
    *,
    prices: Sequence[object],
    K: object,
    C: object,
    B: object,
    stage1_partition: Iterable[Iterable[object]],
    earlier_accepted_partitions: Iterable[Iterable[Iterable[object]]],
    slot: int,
    attempt: int,
) -> AttemptScreen:
    """Apply exactly the two prospective candidate-rejection rules."""
    blocks = sector_blocks(slot, attempt)
    candidate = normalized_partition(blocks)
    stage1 = normalized_partition(stage1_partition)
    earlier = {normalized_partition(partition) for partition in earlier_accepted_partitions}
    feasible = feasibility_count(prices, candidate, K, C, B)
    rejections: list[str] = []
    if candidate == stage1:
        rejections.append("partition_matches_stage1")
    if candidate in earlier:
        rejections.append("partition_matches_earlier_accepted")
    if feasible < 100:
        rejections.append("feasible_set_below_100")
    return AttemptScreen(
        slot=_int(slot, "slot", 1, SLOT_COUNT),
        attempt=_int(attempt, "attempt", 0, MAX_ATTEMPT),
        returns_seed=stream_seed(slot, attempt, "returns"),
        sectors_seed=stream_seed(slot, attempt, "sectors"),
        sector_blocks=blocks,
        normalized_partition=candidate,
        partition_sha256=partition_digest(candidate),
        feasible_count=feasible,
        rejection_codes=tuple(rejections),
    )


def _array(vector: object, shape: tuple[int, ...], name: str) -> np.ndarray:
    try:
        result = np.asarray(vector, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise Stage2GenerationError(f"{name} cannot be converted to binary64") from exc
    _require(result.shape == shape, f"{name} has wrong shape")
    _require(bool(np.isfinite(result).all()), f"{name} contains a non-finite value")
    return result


def _validate_covariance(covariance: object) -> np.ndarray:
    sigma = _array(covariance, (ASSET_COUNT, ASSET_COUNT), "Sigma")
    _require(bool(np.array_equal(sigma, sigma.T)), "Sigma must be exactly symmetric")
    try:
        eigenvalues = np.linalg.eigvalsh(sigma)
    except np.linalg.LinAlgError as exc:
        raise Stage2GenerationError("Sigma PSD validation failed") from exc
    _require(bool(np.isfinite(eigenvalues).all()) and float(eigenvalues.min()) >= 0.0, "Sigma is not PSD")
    return sigma


@dataclass(frozen=True)
class ReturnDraw:
    """In-memory U-09 construction; fixture-only until the pre-run boundary."""

    seed: StreamSeed
    returns: np.ndarray
    mu: np.ndarray
    sigma: np.ndarray
    return_matrix_sha256_le_f64_row_major: str
    mu_hex: tuple[str, ...]
    sigma_hex: tuple[tuple[str, ...], ...]


def sample_return_covariance(mu: object, sigma: object, slot: int, attempt: int) -> ReturnDraw:
    """Perform the fixed 249-by-20 parametric U-09 construction in memory."""
    mean = _array(mu, (ASSET_COUNT,), "mu")
    covariance = _validate_covariance(sigma)
    rng, commitment = stream_rng(slot, attempt, "returns")
    try:
        returns = rng.multivariate_normal(
            mean, covariance, size=RETURN_ROWS, method=DRAW_METHOD,
            check_valid=DRAW_CHECK_VALID, tol=DRAW_SVD_TOLERANCE,
        )
    except (ValueError, np.linalg.LinAlgError) as exc:
        raise Stage2GenerationError("parametric return draw failed") from exc
    returns = _array(returns, (RETURN_ROWS, ASSET_COUNT), "drawn returns")
    derived_mu = np.mean(returns, axis=0, dtype=np.float64)
    centered = returns - derived_mu
    derived_sigma = (centered.T @ centered) / np.float64(RETURN_ROWS - 1)
    derived_sigma = (derived_sigma + derived_sigma.T) / np.float64(2.0)
    derived_sigma = _validate_covariance(derived_sigma)
    raw = np.asarray(returns, dtype="<f8", order="C").tobytes(order="C")
    return ReturnDraw(
        seed=commitment,
        returns=returns,
        mu=derived_mu,
        sigma=derived_sigma,
        return_matrix_sha256_le_f64_row_major=hashlib.sha256(raw).hexdigest(),
        mu_hex=tuple(float(value).hex() for value in derived_mu),
        sigma_hex=tuple(tuple(float(value).hex() for value in row) for row in derived_sigma),
    )

"""The only Gate-5 input boundary permitted to a future Gate-6 runner.

It composes the structural accepted-corpus boundary with the owner-ratified
per-shard registry.  The older :mod:`src.g6.g5_input` module remains a
read-only upstream validator, but does not by itself establish the ratified
baseline-shard identity lock.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterator

from src.g6 import g5_digest_registry, g5_input


ROOT = Path(__file__).resolve().parents[2]
REGISTRY_REL = "research/g6/g5_identity_digest_registry_v1/G5_PER_SHARD_DIGEST_REGISTRY.json"
REGISTRY_FILE_SHA256 = "64d0c92b53bd7f4340e3b3837ddaaacb1009a7427dd11d6e38714582b93b66be"
REGISTRY_CONTENT_SHA256 = "ab0c84400ae92fdf5da7c75511ce559679ebdadd003a9007a959585b40e74955"
REGISTRY_PRODUCER_SHA256 = {
    "src/g6/g5_digest_registry.py": "48ee606a8937cf047cc12ca5e46391142d6e47a214acf734b35d36b7f818f989",
    "research/g6/make_g5_digest_registry.py": "fbc8a2cd1de8ce13c900d2ae9713166e85344101d269f12e93a3b0834a913c5b",
}
RATIFICATION_REL = "research/decisions/GATE_5_IDENTITY_REGISTRY_RATIFICATION.md"
RATIFICATION_FILE_SHA256 = "d6e9b01db6198456e9c8a8290741184b7cfebe7add23335e434fc18822934e3f"
EXPECTED_COORDINATE_COUNT = g5_input.EXPECTED_COORDINATE_COUNT


class RatifiedG5InputError(RuntimeError):
    """Raised when the required Gate-5 identity authorities do not validate."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RatifiedG5InputError(message)


def _file_sha256(path: Path, label: str) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise RatifiedG5InputError(f"{label} is unreadable") from exc


def _load_ratified_registry() -> dict:
    ratification = ROOT / RATIFICATION_REL
    _require(_file_sha256(ratification, "Gate-5 registry ratification") == RATIFICATION_FILE_SHA256,
             "Gate-5 registry ratification authority differs from the owner-ratified record")
    registry_path = ROOT / REGISTRY_REL
    _require(_file_sha256(registry_path, "Gate-5 identity registry") == REGISTRY_FILE_SHA256,
             "Gate-5 identity registry file differs from the owner-ratified artifact")
    try:
        registry = g5_digest_registry._read_json(registry_path)
        g5_digest_registry.validate_pending_registry(registry)
    except g5_digest_registry.DigestRegistryError as exc:
        raise RatifiedG5InputError(f"Gate-5 identity registry is invalid: {exc}") from exc
    _require(registry.get("content_sha256") == REGISTRY_CONTENT_SHA256,
             "Gate-5 identity registry canonical identity differs from the owner-ratified artifact")
    _require(registry.get("producer_source_sha256") == REGISTRY_PRODUCER_SHA256,
             "Gate-5 identity registry producer identity differs from the owner-ratified artifact")
    return registry


def verify_ratified_g5_corpus(corpus_dir: Path | str = g5_input.DEFAULT_CORPUS_DIR) -> g5_input.AcceptedG5Summary:
    """Verify the owner record, exact registry, and every Gate-5 shard identity."""
    registry = _load_ratified_registry()
    try:
        return g5_digest_registry.verify_pending_registry_against_corpus(registry, corpus_dir)
    except (g5_digest_registry.DigestRegistryError, g5_input.G5InputError) as exc:
        raise RatifiedG5InputError(f"ratified Gate-5 input validation failed: {exc}") from exc


def _payload_from_registry_bound_bytes(raw: bytes, path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RatifiedG5InputError(f"registry-bound shard is unreadable JSON: {path.name}") from exc
    _require(isinstance(payload, dict), f"registry-bound shard is not a JSON object: {path.name}")
    return payload


def iter_ratified_records(corpus_dir: Path | str = g5_input.DEFAULT_CORPUS_DIR) -> Iterator[dict[str, Any]]:
    """Yield records only from bytes bound to the owner-ratified registry.

    The initial full validation establishes corpus coverage and authorities.
    Each subsequent shard is then read exactly once, hashed before decoding,
    structurally revalidated from that same byte buffer, and only then yielded.
    A later rehashed shard substitution cannot cross this boundary.
    """
    directory = Path(corpus_dir)
    registry = _load_ratified_registry()
    try:
        summary = g5_digest_registry.verify_pending_registry_against_corpus(registry, directory)
    except (g5_digest_registry.DigestRegistryError, g5_input.G5InputError) as exc:
        raise RatifiedG5InputError(f"ratified Gate-5 input validation failed: {exc}") from exc
    for entry in registry["shards"]:
        shard_id = entry["shard_id"]
        path = directory / f"{shard_id}.json"
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise RatifiedG5InputError(f"registry-bound shard is unreadable: {path.name}") from exc
        _require(hashlib.sha256(raw).hexdigest() == entry["file_sha256"],
                 f"registry-bound shard file digest mismatch: {path.name}")
        payload = _payload_from_registry_bound_bytes(raw, path)
        _require(payload.get("content_sha256") == entry["content_sha256"],
                 f"registry-bound shard content digest mismatch: {path.name}")
        try:
            kind, platform = g5_input._validate_shard(
                payload,
                path,
                summary.source_snapshot,
                summary.minority_projection_sha256,
                summary.primary_r1_coefficients,
            )
        except g5_input.G5InputError as exc:
            raise RatifiedG5InputError(f"registry-bound shard structural validation failed: {exc}") from exc
        expected_platform = summary.minority_platform if kind == "minority" else summary.baseline_platform
        _require(platform == expected_platform, f"registry-bound shard platform drift: {path.name}")
        for record in payload["records"]:
            yield record

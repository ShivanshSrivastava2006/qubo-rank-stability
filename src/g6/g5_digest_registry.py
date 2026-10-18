"""Additive identity registry for the immutable accepted Gate-5 corpus.

The registry prevents a later well-formed-and-rehashed shard substitution from
silently becoming a Gate-6 input.  It is not retroactive proof of the corpus:
until independently reviewed and owner-ratified it is explicitly a pending
artifact and must not be consumed by a production runner.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from src.g6 import g5_input


ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "decisions_os/g6_g5_identity_digest_registry/v1"
REGISTRY_FILENAME = "G5_PER_SHARD_DIGEST_REGISTRY.json"
OWNER_DECISION_REL = "research/decisions/GATE_6_OWNER_EXECUTION_DECISIONS.md"
OWNER_DECISION_SHA256 = "0d7d212dd1205a8c1c84d702f0f8b44a444b952d84c29a6a352d9a17b716e4fe"
PENDING_RATIFICATION = "pending-independent-review-and-owner-ratification"


class DigestRegistryError(RuntimeError):
    """Raised when a prospective or emitted registry does not validate."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise DigestRegistryError(message)


def canonical_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def file_sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise DigestRegistryError(f"unreadable file: {path}") from exc


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise DigestRegistryError(f"unreadable JSON: {path}") from exc
    _require(isinstance(payload, dict), f"registry JSON must be an object: {path}")
    return payload


def _validate_content_hash(payload: Mapping[str, Any], label: str) -> None:
    body = dict(payload)
    digest = body.pop("content_sha256", None)
    _require(isinstance(digest, str), f"{label}: missing content_sha256")
    _require(hashlib.sha256(canonical_bytes(body)).hexdigest() == digest,
             f"{label}: canonical content_sha256 mismatch")


def _owner_authorization() -> dict[str, str]:
    path = ROOT / OWNER_DECISION_REL
    digest = file_sha256(path)
    _require(digest == OWNER_DECISION_SHA256,
             "Gate-6 owner execution decision differs from the authorized record")
    return {"path": OWNER_DECISION_REL, "file_sha256": digest}


def build_pending_registry(corpus_dir: Path | str = g5_input.DEFAULT_CORPUS_DIR) -> dict[str, Any]:
    """Build a canonical pending registry after fully validating the corpus."""
    directory = Path(corpus_dir)
    try:
        summary = g5_input.verify_accepted_g5_corpus(directory)
    except g5_input.G5InputError as exc:
        raise DigestRegistryError(f"accepted Gate-5 corpus verification failed: {exc}") from exc

    shards: list[dict[str, str]] = []
    for shard_id in g5_input.EXPECTED_SHARDS:
        path = directory / f"{shard_id}.json"
        payload = _read_json(path)
        _validate_content_hash(payload, path.name)
        _require(payload.get("shard_id") == shard_id, f"registry build shard-id mismatch: {path.name}")
        content_sha256 = payload.get("content_sha256")
        _require(isinstance(content_sha256, str), f"registry build missing content hash: {path.name}")
        shards.append({
            "shard_id": shard_id,
            "file_sha256": file_sha256(path),
            "content_sha256": content_sha256,
        })

    payload = {
        "schema": SCHEMA,
        "purpose": "Additive immutable-identity lock for accepted Gate-5 shards; no scientific outputs.",
        "ratification_status": PENDING_RATIFICATION,
        "owner_authorization": _owner_authorization(),
        "accepted_gate5": {
            "coverage_audit_content_sha256": g5_input.ACCEPTED_COVERAGE_SHA256,
            "resume_manifest_content_sha256": g5_input.ACCEPTED_MANIFEST_SHA256,
            "source_snapshot": dict(summary.source_snapshot),
            "shard_count": summary.shard_count,
            "coordinate_count": summary.coordinate_count,
        },
        "producer_source_sha256": {
            "src/g6/g5_digest_registry.py": file_sha256(Path(__file__).resolve()),
            "research/g6/make_g5_digest_registry.py": file_sha256(ROOT / "research/g6/make_g5_digest_registry.py"),
        },
        "shards": shards,
        "scientific_outputs": "intentionally absent",
    }
    payload["content_sha256"] = hashlib.sha256(canonical_bytes(payload)).hexdigest()
    return payload


def validate_pending_registry(payload: Mapping[str, Any]) -> None:
    """Validate registry structure and immutable authority links, without corpus I/O."""
    _require(payload.get("schema") == SCHEMA, "unexpected registry schema")
    _validate_content_hash(payload, "Gate-5 digest registry")
    _require(payload.get("purpose") == "Additive immutable-identity lock for accepted Gate-5 shards; no scientific outputs.",
             "registry purpose drift")
    _require(payload.get("ratification_status") == PENDING_RATIFICATION,
             "registry must remain pending review and owner ratification")
    _require(payload.get("owner_authorization") == _owner_authorization(), "registry owner authorization drift")
    accepted = payload.get("accepted_gate5")
    _require(isinstance(accepted, dict)
             and accepted.get("coverage_audit_content_sha256") == g5_input.ACCEPTED_COVERAGE_SHA256
             and accepted.get("resume_manifest_content_sha256") == g5_input.ACCEPTED_MANIFEST_SHA256
             and accepted.get("shard_count") == g5_input.EXPECTED_SHARD_COUNT
             and accepted.get("coordinate_count") == g5_input.EXPECTED_COORDINATE_COUNT
             and isinstance(accepted.get("source_snapshot"), dict),
             "registry accepted-Gate-5 identity mismatch")
    producer = payload.get("producer_source_sha256")
    _require(isinstance(producer, dict)
             and set(producer) == {"src/g6/g5_digest_registry.py", "research/g6/make_g5_digest_registry.py"}
             and all(isinstance(digest, str) and len(digest) == 64 for digest in producer.values()),
             "registry producer-source identity mismatch")
    expected_shards = g5_input.EXPECTED_SHARDS
    entries = payload.get("shards")
    _require(isinstance(entries, list) and len(entries) == len(expected_shards), "registry shard count mismatch")
    for shard_id, entry in zip(expected_shards, entries, strict=True):
        _require(isinstance(entry, dict) and set(entry) == {"shard_id", "file_sha256", "content_sha256"}
                 and entry.get("shard_id") == shard_id
                 and all(isinstance(entry.get(field), str) and len(entry[field]) == 64
                         for field in ("file_sha256", "content_sha256")),
                 f"registry malformed shard entry: {shard_id}")
    _require(payload.get("scientific_outputs") == "intentionally absent", "registry scientific-output boundary violated")


def verify_pending_registry_against_corpus(
    payload: Mapping[str, Any], corpus_dir: Path | str = g5_input.DEFAULT_CORPUS_DIR
) -> g5_input.AcceptedG5Summary:
    """Revalidate the corpus and require exact per-file and payload identities."""
    validate_pending_registry(payload)
    directory = Path(corpus_dir)
    try:
        summary = g5_input.verify_accepted_g5_corpus(directory)
    except g5_input.G5InputError as exc:
        raise DigestRegistryError(f"accepted Gate-5 corpus verification failed: {exc}") from exc
    accepted = payload["accepted_gate5"]
    _require(accepted["source_snapshot"] == dict(summary.source_snapshot),
             "registry source snapshot differs from validated corpus")
    for entry in payload["shards"]:
        path = directory / f"{entry['shard_id']}.json"
        _require(file_sha256(path) == entry["file_sha256"], f"registry file digest mismatch: {path.name}")
        shard = _read_json(path)
        _validate_content_hash(shard, path.name)
        _require(shard.get("content_sha256") == entry["content_sha256"],
                 f"registry content digest mismatch: {path.name}")
    return summary

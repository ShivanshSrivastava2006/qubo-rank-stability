"""Offline, non-writing commitment adapter; no scientific schema is chosen here.

The trusted verifier supplies the complete ordered roster, its expected root,
a frozen campaign descriptor and an exact flat result-field schema. These
arguments are NOT self-proven protocol authority. The caller must independently
establish their provenance. The adapter proves completeness against those
inputs, not scientific correctness, GPU origin, timestamping or sample adequacy.
No files, generator, device, network or scientific output are accessed.

Boundaries enforced:
- Descriptor is limited to 65536 bytes when encoded via canonical().
- Str fields in results are limited to 4096 characters.
"""
from __future__ import annotations

import copy
import hashlib
import hmac
import math

from research.g9 import stage2_sampled_verification as sampled

SCHEMA = "decisions_os/g9_commitment_adapter/draft_v1"
FIELD_TYPES = frozenset({"int", "bool", "str", "binary64"})


class CommitmentAdapterError(ValueError):
    """The supplied campaign inputs or producer records disagree."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CommitmentAdapterError(message)


def _bytes(value: object) -> bytes:
    try:
        return sampled.canonical(value)
    except sampled.VerificationError as exc:
        raise CommitmentAdapterError(str(exc)) from exc
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise CommitmentAdapterError(f"unencodable input: {exc!r}") from exc


def _hash(value: object) -> str:
    return hashlib.sha256(_bytes(value)).hexdigest()


def _sha(value: object) -> None:
    _require(type(value) is str and len(value) == 64 and
             all(c in "0123456789abcdef" for c in value), "invalid expected digest")


def build_campaign_commitment(*, expected_coordinates: list,
                              expected_coordinate_root: str,
                              descriptor: dict, expected_descriptor_sha256: str,
                              result_schema: dict, expected_schema_sha256: str,
                              producer_records: list) -> dict:
    """Validate all records before invoking the sampled commitment builder.

    Schema maps each required field to int/bool/str/binary64. Binary64 inputs
    must be exact Python floats and are encoded to preserve signed-zero bits.
    The returned campaign_binding_digest binds descriptor, schema and full commitment;
    future timestamp/beacon integration must pin THIS binding, not just its
    inner Merkle root. This function performs no publication or persistence.
    """
    for digest in (expected_coordinate_root, expected_descriptor_sha256,
                   expected_schema_sha256):
        _sha(digest)

    _require(type(expected_coordinates) is list and
             0 < len(expected_coordinates) <= sampled.MAX_GRID_POINTS,
             "expected roster must be a non-empty bounded list")
    
    _require(type(descriptor) is dict and descriptor, "descriptor must be non-empty dict")
    
    _require(type(result_schema) is dict and result_schema and
             all(type(k) is str and k and type(v) is str and v in FIELD_TYPES
                 for k, v in result_schema.items()), "invalid exact field schema")

    _require(type(producer_records) is list and len(producer_records) == len(expected_coordinates),
             "producer record count differs from trusted roster")

    # Every caller-owned container is snapshotted, and the snapshot is what the
    # returned body is built from.  `schema` is copied deeply for uniformity
    # rather than necessity: the `type(result_schema) is dict` check above
    # already excludes subclasses, so no nested caller-owned object can reach the
    # returned `result_schema`.  The check is kept because it also refuses a
    # self-referential descriptor -- a plain `except Exception: pass` there
    # would let an untyped RuntimeError escape the module's contract.
    try:
        roster = copy.deepcopy(expected_coordinates)
        frozen_descriptor = copy.deepcopy(descriptor)
        frozen_records = copy.deepcopy(producer_records)
        schema = copy.deepcopy(result_schema)
    except Exception as exc:
        raise CommitmentAdapterError(f"snapshot failed: {exc!r}") from exc

    descriptor_bytes = _bytes(frozen_descriptor)
    _require(len(descriptor_bytes) <= 65536, "descriptor too large")
    
    _require(_hash(frozen_descriptor) == expected_descriptor_sha256,
             "descriptor identity mismatch")
             
    _require(_hash(schema) == expected_schema_sha256, "result schema identity mismatch")

    seen = set()
    for coordinate in roster:
        encoded = _bytes(coordinate)
        _require(encoded not in seen, "duplicate coordinate in trusted roster")
        seen.add(encoded)
        
    try:
        actual_root = sampled.coordinate_root(roster).hex()
    except sampled.VerificationError as exc:
        raise CommitmentAdapterError(str(exc)) from exc
    _require(actual_root == expected_coordinate_root,
             "trusted roster differs from its expected root")

    entries = []
    for expected, record in zip(roster, frozen_records):
        _require(type(record) is dict and set(record) == {"coordinates", "result"},
                 "producer record has wrong fields")
        _require(_bytes(record["coordinates"]) == _bytes(expected),
                 "producer coordinates differ from canonical expected order")
                 
        result = record["result"]
        _require(type(result) is dict and set(result) == set(schema),
                 "result fields differ from exact schema")
                 
        encoded_result = {}
        for field, kind in schema.items():
            value = result[field]
            expected_type = {"int": int, "bool": bool, "str": str,
                             "binary64": float}[kind]
            _require(type(value) is expected_type, "result field has wrong exact type")
            
            if kind == "str":
                _require(len(value) <= 4096, "str field too long")
            if kind == "binary64":
                _require(math.isfinite(value), "non-finite float in result")
                encoded_result[field] = sampled.encode_float(value)
            else:
                encoded_result[field] = value

        entries.append((expected, encoded_result))
        
    # Wrapped like every other call into `sampled`: a result field the caller
    # typed as `int` can still be unencodable (an integer with more than 4300
    # decimal digits makes `json.dumps` raise inside `canonical`), which raises
    # VerificationError there.  That must not escape this module's contract of
    # raising only CommitmentAdapterError.
    try:
        commitment = sampled.build_commitment(entries, len(roster))
    except sampled.VerificationError as exc:
        raise CommitmentAdapterError(str(exc)) from exc

    binding_payload = {
        "domain": SCHEMA + "/binding",
        "merkle_root": commitment["merkle_root"],
        "coordinate_root": expected_coordinate_root,
        "descriptor_sha256": expected_descriptor_sha256,
        "schema_sha256": expected_schema_sha256,
        "grid_point_count": len(roster),
        "schema_version": SCHEMA,
    }
    binding_digest = _hash(binding_payload)

    body = {"schema": SCHEMA, "descriptor": frozen_descriptor,
            "descriptor_sha256": expected_descriptor_sha256,
            "result_schema": schema, "result_schema_sha256": expected_schema_sha256,
            "expected_coordinate_root": expected_coordinate_root,
            "commitment": commitment}
    return {**body, "campaign_binding_digest": binding_digest}


def verify_campaign_commitment(binding_digest: str, *, merkle_root: str,
                               grid_point_count: int, expected_descriptor_sha256: str,
                               expected_schema_sha256: str, expected_coordinate_root: str) -> None:
    """Verifies that a published campaign binding digest authentically commits the expected components."""
    for digest in (binding_digest, merkle_root, expected_descriptor_sha256, 
                   expected_schema_sha256, expected_coordinate_root):
        _sha(digest)
    _require(type(grid_point_count) is int and grid_point_count > 0, "invalid grid point count")

    binding_payload = {
        "domain": SCHEMA + "/binding",
        "merkle_root": merkle_root,
        "coordinate_root": expected_coordinate_root,
        "descriptor_sha256": expected_descriptor_sha256,
        "schema_sha256": expected_schema_sha256,
        "grid_point_count": grid_point_count,
        "schema_version": SCHEMA,
    }
    expected_binding = _hash(binding_payload)
    _require(hmac.compare_digest(binding_digest, expected_binding), "binding digest mismatch")

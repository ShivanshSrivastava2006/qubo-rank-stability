"""Offline, canonical transport for the approved Option A Python comparison fields.

The caller supplies the frozen single-process reference as ``inputs['frozen_reference']``;
a reviewed parallel runner may instead be injected. Neither runner is imported here.
Only the four Section B.2 comparison fields cross this boundary.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
import copy
import hashlib
import json
import re


class ReferenceSealError(ValueError):
    """An input, reference result, or sealed session does not match its contract."""


HASH_FIELDS = ("instance_digest", "coefficient_ledger_digest", "protocol_digest",
               "original_objective_digest", "frozen_source_digest", "decision_digest")
FIELDS = ("energy_minimum_words", "canonical_minimum_index", "tie_flags",
          "d015_d016_reconstruction")
ENCODINGS = ("unbalanced", "slack")
FORMAT = "decisions_os/g9_section_b2_python_reference_seal/v1"
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_WORD = re.compile(r"[0-9a-f]{16}\Z")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ReferenceSealError(message)


def _json(value: object) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False).encode("ascii")
    except (TypeError, ValueError, OverflowError) as exc:
        raise ReferenceSealError("noncanonical JSON value") from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_json(value)).hexdigest()


def _hash(value: object, label: str) -> str:
    _require(type(value) is str and _HEX.fullmatch(value) is not None,
             f"{label} must be a lowercase SHA-256")
    return value


def _identities(inputs: object) -> dict[str, str]:
    _require(isinstance(inputs, Mapping), "inputs must be a mapping")
    bound = {field: _hash(inputs.get(field), field) for field in HASH_FIELDS}
    extra = inputs.get("additional_input_hashes", {})
    _require(type(extra) is dict and all(type(k) is str and k and k not in bound for k in extra),
             "invalid additional input hash names")
    bound.update({key: _hash(value, key) for key, value in extra.items()})
    return bound


def _coordinate_value(value: object) -> bool:
    return (type(value) is str and bool(value)) or type(value) is int or (
        type(value) is list and all(_coordinate_value(item) for item in value)) or (
        type(value) is dict and all(type(key) is str and bool(key) and
                                    _coordinate_value(item) for key, item in value.items()))


def _coordinate_rows(coordinates: object) -> list[dict[str, object]]:
    _require(type(coordinates) in (list, tuple) and len(coordinates) > 0,
             "coordinates must be a nonempty list")
    rows = []
    seen = set()
    for item in coordinates:
        _require(type(item) is dict and set(item) == {"coordinate", "encoding"},
                 "coordinate row must contain exactly coordinate and encoding")
        coordinate, encoding = item["coordinate"], item["encoding"]
        _require(type(coordinate) is dict and bool(coordinate), "coordinate must be a nonempty mapping")
        _require(type(encoding) is str and encoding in ENCODINGS, "unknown encoding")
        # Every branch and family identifier, including D013, is part of the exact key.
        _require(all(type(k) is str and k for k in coordinate), "coordinate keys must be strings")
        _require(all(_coordinate_value(v) for v in coordinate.values()),
                 "coordinate values have invalid types")
        key = _json(item)
        _require(key not in seen, "duplicate coordinate and encoding")
        seen.add(key)
        rows.append(copy.deepcopy(item))
    return rows


def _result(value: object) -> dict[str, object]:
    _require(type(value) is dict and set(value) == set(FIELDS),
             "reference must return exactly the four comparison fields")
    words = value["energy_minimum_words"]
    _require(type(words) is list and len(words) == 1 and
             all(type(w) is str and _WORD.fullmatch(w) is not None for w in words),
             "energy words must be binary64 hex words")
    index = value["canonical_minimum_index"]
    _require(type(index) is int and index >= 0, "invalid canonical minimum index")
    flags = value["tie_flags"]
    _require(type(flags) is list and len(flags) > index and
             all(type(f) is int and 0 <= f <= 7 for f in flags) and flags[index] == 7,
             "tie flags must cover the canonical minimum")
    reconstruction = value["d015_d016_reconstruction"]
    _require(type(reconstruction) is dict and bool(reconstruction) and
             _coordinate_value(reconstruction),
             "D015/D016 reconstruction is required")
    _json(reconstruction)
    return copy.deepcopy(value)


def precompute(inputs: object, coordinates: object, runner=None) -> list[dict[str, object]]:
    """Run each requested coordinate/encoding through the frozen reference."""
    _identities(inputs)
    rows = _coordinate_rows(coordinates)
    reference = runner if runner is not None else inputs.get("frozen_reference")
    _require(callable(reference), "a frozen single-process reference is required")
    output = []
    for row in rows:
        result = _result(reference(row["coordinate"], row["encoding"]))
        output.append({"coordinate": row["coordinate"], "encoding": row["encoding"],
                       "result": result})
    return output


def seal(inputs: object, coordinates: object, production_identity_hash: object,
         runner=None) -> bytes:
    """Return canonical JSON bytes with a whole-seal content SHA-256."""
    identities = _identities(inputs)
    identity = _hash(production_identity_hash, "production identity")
    rows = _coordinate_rows(coordinates)
    computed = precompute(inputs, rows, runner)
    results = [{"coordinate": row["coordinate"], "encoding": row["encoding"],
                "result": row["result"], "result_sha256": _digest(row["result"])}
               for row in computed]
    manifest = {"format": FORMAT, "input_hashes": identities,
                "production_identity_hash": identity, "coordinates": rows,
                "result_sha256": [row["result_sha256"] for row in results]}
    body = {"manifest": manifest, "results": results}
    return _json({**body, "content_sha256": _digest(body)})


def open_for_session(sealed: object, session_inputs: object):
    """Verify the entire seal and return a WP3-shaped reference callable."""
    try:
        document = json.loads(sealed)
    except (ValueError, UnicodeError, TypeError) as exc:
        raise ReferenceSealError("seal is not JSON") from exc
    _require(type(document) is dict and set(document) ==
             {"manifest", "results", "content_sha256"}, "invalid seal envelope")
    _require(_json(document) == sealed, "seal bytes are not canonical")
    body = {"manifest": document["manifest"], "results": document["results"]}
    _require(_hash(document["content_sha256"], "content digest") == _digest(body),
             "tampered seal")
    manifest = document["manifest"]
    _require(type(manifest) is dict and set(manifest) ==
             {"format", "input_hashes", "production_identity_hash", "coordinates", "result_sha256"}
             and manifest["format"] == FORMAT, "invalid manifest")
    _require(manifest["input_hashes"] == _identities(session_inputs), "input hash mismatch")
    _require(manifest["production_identity_hash"] ==
             _hash(session_inputs.get("production_identity_hash"), "production identity"),
             "production identity mismatch")
    rows = _coordinate_rows(manifest["coordinates"])
    requested = _coordinate_rows(session_inputs.get("coordinates"))
    _require(rows == requested, "missing or extra coordinate/encoding")
    results = document["results"]
    digests = manifest["result_sha256"]
    _require(type(results) is list and len(results) == len(rows) and
             type(digests) is list and len(digests) == len(rows), "result census mismatch")
    lookup = {}
    for expected, entry, digest in zip(rows, results, digests):
        _require(type(entry) is dict and set(entry) ==
                 {"coordinate", "encoding", "result", "result_sha256"}, "invalid result row")
        _require(entry["coordinate"] == expected["coordinate"] and
                 entry["encoding"] == expected["encoding"], "result row order mismatch")
        result = _result(entry["result"])
        _require(_hash(digest, "result digest") == entry["result_sha256"] == _digest(result),
                 "tampered result")
        lookup[_json(expected)] = result

    def python_reference(coordinate: object, encoding: object) -> dict[str, object]:
        _require(_identities(session_inputs) == manifest["input_hashes"] and
                 session_inputs.get("production_identity_hash") ==
                 manifest["production_identity_hash"] and
                 _coordinate_rows(session_inputs.get("coordinates")) == rows,
                 "session inputs changed after opening the seal")
        key = _json({"coordinate": coordinate, "encoding": encoding})
        _require(key in lookup, "coordinate/encoding not sealed")
        return copy.deepcopy(lookup[key])

    return python_reference

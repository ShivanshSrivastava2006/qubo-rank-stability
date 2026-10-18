"""Read-only provenance and overlap audit for the sealed CUDA/T4 V-14 sets.

This module repairs two provenance debts without creating a scientific result:

* regenerate and retain the complete, hash-bound receipts for the accepted
  0.5x and 2x CUDA/T4 core sets; and
* retain only a bit-identity comparison receipt for the coordinates those
  sets recomputed in common with the accepted Gate-5 r=1 grid.

The comparison deliberately emits counts and a digest of equal common-field
streams only. It does not emit an energy, tie set, decoded portfolio, label,
rate, or other scientific value.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
from typing import Any, Iterator, Mapping


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.g6.cuda_qualification import v14_core_legacy_linear_order_audit as legacy  # noqa: E402
from src.g6 import ratified_g5_input  # noqa: E402


SCHEMA = "decisions_os/g6_v14_cuda_t4_provenance_overlap/v1"
SCHEMA_MANIFEST = "decisions_os/g6_v14_cuda_t4_provenance_overlap_manifest/v1"
RATE_REL = "research/g6/rate_surface_and_d013/RATE_SURFACE_AND_D013.json"
G4_LEDGER_REL = "research/g4/G4_PRIMARY_LEDGER.json"
OWNER_DECISIONS_REL = "research/decisions/GATE_6_OWNER_EXECUTION_DECISIONS.md"
OUTPUT_NAME = "V14_CUDA_T4_PROVENANCE_AND_OVERLAP.json"
MANIFEST_NAME = "manifest.json"
RECEIPT_NAMES = {"0.5x": "V14_0_5X_AUDIT_RECEIPT.json", "2x": "V14_2X_AUDIT_RECEIPT.json"}
ACCEPTED_RATE_FILE_SHA256 = "6f052678ad854f3a8e705c365df4221b70cdaa347007436d3bedbda8e31229ff"
ACCEPTED_RATE_CONTENT_SHA256 = "00636483e62e78f4b865274b6b79b47842072f90312beee3425c7fce5d8597ea"
EXPECTED_PLAN_CONTENT_SHA256 = {
    "0.5x": "e5b44620206e5bbaca3a03e890a4f99b4f29a23b87d3e2d4f8f8be2c3067d71d",
    "2x": "38c01eff5a313273fc106a5f5c39760628e59132b9a7a72e0176b37aa1897748",
}
PRIMARY_R_HEX = float(1.0).hex()
COMMON_ENCODING_FIELDS = ("H_E_min_hex", "T_E_size", "X_E_size", "set_label")
COMMON_TIE_COMPARATOR_FIELDS = ("c_H", "epsilon_hex", "minimum_tau_hex")
PRODUCER_RELATIVES = (
    "research/g6/v14_cuda_t4_provenance_overlap.py",
    "research/g6/run_v14_cuda_t4_provenance_overlap.py",
)


class ProvenanceOverlapError(RuntimeError):
    """A sealed V-14 set or its Gate-5 overlap fails closed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ProvenanceOverlapError(message)


def canonical_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def content_sha256(payload: Mapping[str, Any]) -> str:
    body = dict(payload)
    digest = body.pop("content_sha256", None)
    _require(isinstance(digest, str), "canonical payload lacks content_sha256")
    return hashlib.sha256(canonical_bytes(body)).hexdigest()


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _read_regular_bytes(path: Path, label: str) -> bytes:
    try:
        status = path.lstat()
        _require(stat.S_ISREG(status.st_mode) and not path.is_symlink(), f"{label} is not a regular non-symlink file")
        return path.read_bytes()
    except OSError as exc:
        raise ProvenanceOverlapError(f"{label} is unreadable") from exc


def _read_json(path: Path, label: str) -> tuple[bytes, dict[str, Any]]:
    raw = _read_regular_bytes(path, label)
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProvenanceOverlapError(f"{label} is invalid JSON") from exc
    _require(isinstance(value, dict), f"{label} must be a JSON object")
    return raw, value


def _require_content(payload: Mapping[str, Any], label: str) -> None:
    _require(payload.get("content_sha256") == content_sha256(payload), f"{label} canonical content hash mismatch")


def _source_hashes() -> dict[str, str]:
    return {relative: _sha256(_read_regular_bytes(ROOT / relative, relative)) for relative in PRODUCER_RELATIVES}


def _read_accepted_rate() -> dict[str, Any]:
    raw, rate = _read_json(ROOT / RATE_REL, "accepted rate/D013 artifact")
    _require(_sha256(raw) == ACCEPTED_RATE_FILE_SHA256, "accepted rate/D013 file identity differs")
    _require(rate.get("content_sha256") == ACCEPTED_RATE_CONTENT_SHA256, "accepted rate/D013 content identity differs")
    _require_content(rate, "accepted rate/D013 artifact")
    return rate


def _read_plan(plan_path: Path, scale: str, rate: Mapping[str, Any]) -> tuple[bytes, dict[str, Any]]:
    raw, plan = _read_json(plan_path, f"{scale} V-14 plan")
    _require(plan.get("content_sha256") == EXPECTED_PLAN_CONTENT_SHA256[scale], f"{scale} plan content identity differs")
    _require_content(plan, f"{scale} V-14 plan")
    try:
        bound = rate["input_identities"]["v14"][scale]
    except (KeyError, TypeError) as exc:
        raise ProvenanceOverlapError(f"accepted rate/D013 lacks {scale} V-14 identity") from exc
    _require(isinstance(bound, dict) and bound.get("plan_content_sha256") == plan["content_sha256"]
             and bound.get("plan_file_sha256") == _sha256(raw), f"{scale} plan differs from accepted rate/D013 provenance")
    return raw, plan


def _safe_root(root: Path, scale: str) -> Path:
    try:
        status = root.lstat()
    except OSError as exc:
        raise ProvenanceOverlapError(f"{scale} artifact root is unreadable") from exc
    _require(stat.S_ISDIR(status.st_mode) and not root.is_symlink(), f"{scale} artifact root is not a non-symlink directory")
    return root.resolve(strict=True)


def _axis_index_by_hex() -> dict[str, int]:
    _raw, ledger = _read_json(ROOT / G4_LEDGER_REL, "Gate-4 primary ledger")
    _require_content(ledger, "Gate-4 primary ledger")
    coordinates = ledger.get("coordinates")
    _require(isinstance(coordinates, list) and len(coordinates) == 61, "Gate-4 primary axis is malformed")
    mapping: dict[str, int] = {}
    for expected, entry in enumerate(coordinates):
        _require(isinstance(entry, dict) and entry.get("index") == expected and isinstance(entry.get("binary64_hex"), str),
                 "Gate-4 primary axis row is malformed")
        coordinate = entry["binary64_hex"]
        _require(coordinate not in mapping, "Gate-4 primary axis has duplicate binary64 coordinate")
        mapping[coordinate] = expected
    return mapping


def _iter_receipt_records(receipt: Mapping[str, Any]) -> Iterator[dict[str, Any]]:
    batches = receipt.get("batches")
    _require(isinstance(batches, list), "V-14 receipt has no batches")
    for entry in sorted(batches, key=lambda item: item["range"]["start"]):
        _require(isinstance(entry, dict) and isinstance(entry.get("path"), str), "V-14 receipt batch path is malformed")
        directory = Path(entry["path"])
        records_path = directory / "records.json"
        raw, records = _read_json(records_path, f"V-14 batch {entry.get('batch_id')}")
        _require(_sha256(raw) == entry.get("records_file_sha256"), "V-14 records changed after its receipt")
        _require(records.get("content_sha256") == entry.get("records_content_sha256"), "V-14 records content changed after its receipt")
        _require_content(records, "V-14 records")
        items = records.get("records")
        _require(isinstance(items, list) and len(items) == entry.get("record_count"), "V-14 receipt record count drift")
        for record in items:
            _require(isinstance(record, dict), "V-14 record is not an object")
            yield record


def _primary_key(v14_key: object, axis: Mapping[str, int]) -> dict[str, Any] | None:
    _require(isinstance(v14_key, dict) and set(v14_key) == {
        "ell_budget", "ell_card", "ell_sector", "s_budget_hex", "s_card_hex", "s_sector_hex"
    }, "V-14 coordinate key is malformed")
    try:
        card, sector, budget = (axis[v14_key["s_card_hex"]], axis[v14_key["s_sector_hex"]], axis[v14_key["s_budget_hex"]])
    except KeyError:
        return None
    return {"r_hex": PRIMARY_R_HEX, "ell_card": card, "ell_sector": sector, "ell_budget": budget}


def _v14_projection(record: Mapping[str, Any], encoding: str) -> dict[str, Any]:
    _require(isinstance(record.get("coefficients_hex"), dict), "V-14 record coefficients are malformed")
    primary = record.get("primary_c_h_2048")
    _require(isinstance(primary, dict) and set(primary) == {"unbalanced", "slack"}, "V-14 record primary condition is malformed")
    value = primary.get(encoding)
    _require(isinstance(value, dict) and set(COMMON_ENCODING_FIELDS) <= set(value)
             and isinstance(value.get("tie_comparator"), dict)
             and set(COMMON_TIE_COMPARATOR_FIELDS) <= set(value["tie_comparator"]), "V-14 primary record is malformed")
    return {
        "coefficients_hex": record["coefficients_hex"],
        "encoding": {field: value[field] for field in COMMON_ENCODING_FIELDS},
        "tie_comparator": {field: value["tie_comparator"][field] for field in COMMON_TIE_COMPARATOR_FIELDS},
    }


def _g5_projection(record: Mapping[str, Any], encoding: str) -> dict[str, Any]:
    _require(isinstance(record.get("coefficients_hex"), dict), "Gate-5 record coefficients are malformed")
    value = record.get(encoding)
    _require(isinstance(value, dict) and set(COMMON_ENCODING_FIELDS) <= set(value)
             and isinstance(value.get("tie_comparator"), dict)
             and set(COMMON_TIE_COMPARATOR_FIELDS) <= set(value["tie_comparator"]), "Gate-5 primary record is malformed")
    return {
        "coefficients_hex": record["coefficients_hex"],
        "encoding": {field: value[field] for field in COMMON_ENCODING_FIELDS},
        "tie_comparator": {field: value["tie_comparator"][field] for field in COMMON_TIE_COMPARATOR_FIELDS},
    }


def _iter_selected_v14(receipt: Mapping[str, Any], axis: Mapping[str, int]) -> Iterator[tuple[dict[str, Any], dict[str, Any]]]:
    """Yield only the overlap rows, retaining the core producer's linear order."""
    previous: tuple[int, int, int] | None = None
    for record in _iter_receipt_records(receipt):
        key = _primary_key(record.get("key"), axis)
        if key is None:
            continue
        order = (key["ell_card"], key["ell_sector"], key["ell_budget"])
        _require(previous is None or order > previous, "V-14 overlap rows are not strictly primary-grid ordered")
        previous = order
        yield key, record


def _overlaps(receipts: Mapping[str, Mapping[str, Any]], axis: Mapping[str, int]) -> dict[str, dict[str, Any]]:
    """Perform both ordered joins during one ratified Gate-5 corpus traversal."""
    selected = {scale: _iter_selected_v14(receipt, axis) for scale, receipt in receipts.items()}
    next_v14: dict[str, tuple[dict[str, Any], dict[str, Any]] | None] = {}
    for scale, iterator in selected.items():
        try:
            next_v14[scale] = next(iterator)
        except StopIteration as exc:
            raise ProvenanceOverlapError(f"{scale} V-14 set has no embedded primary overlap") from exc
    counts = {scale: 0 for scale in receipts}
    streams = {scale: hashlib.sha256() for scale in receipts}
    for g5_record in ratified_g5_input.iter_ratified_records():
        key = g5_record.get("key")
        if not isinstance(key, dict) or key.get("r_hex") != PRIMARY_R_HEX:
            continue
        for scale, iterator in selected.items():
            current = next_v14[scale]
            if current is None or current[0] != key:
                continue
            _expected_key, v14_record = current
            for encoding in ("unbalanced", "slack"):
                v14_value = _v14_projection(v14_record, encoding)
                g5_value = _g5_projection(g5_record, encoding)
                _require(v14_value == g5_value, f"{scale} CUDA/Python common primary fields differ")
                streams[scale].update(canonical_bytes({"key": key, "encoding": encoding, "common_fields": v14_value}))
            counts[scale] += 1
            try:
                next_v14[scale] = next(iterator)
            except StopIteration:
                next_v14[scale] = None
    result: dict[str, dict[str, Any]] = {}
    for scale, pending in next_v14.items():
        _require(pending is None, f"{scale} V-14 set has a primary overlap key absent from Gate-5")
        expected_count = (31 if scale == "0.5x" else 61) ** 3
        _require(counts[scale] == expected_count, f"{scale} overlap cardinality is not the declared embedded primary grid")
        result[scale] = {
            "r_hex": PRIMARY_R_HEX,
            "coordinate_count": counts[scale],
            "encoding_comparisons": 2 * counts[scale],
            "common_fields": ["coefficients_hex", *COMMON_ENCODING_FIELDS, "tie_comparator.{c_H,epsilon_hex,minimum_tau_hex}"],
            "mismatch_count": 0,
            "matching_stream_sha256": streams[scale].hexdigest(),
            "retained_values": "none; only a digest of equal common-field streams is retained",
        }
    return result


def build(*, zero_five_plan: Path, zero_five_root: Path, two_x_plan: Path, two_x_root: Path,
          reviewed_handoff: str) -> dict[str, Any]:
    """Build a provenance-only canonical body. This function writes nothing."""
    _require(isinstance(reviewed_handoff, str) and reviewed_handoff.strip(), "reviewed handoff is required")
    rate = _read_accepted_rate()
    axis = _axis_index_by_hex()
    supplied = {
        "0.5x": (Path(zero_five_plan), _safe_root(Path(zero_five_root), "0.5x")),
        "2x": (Path(two_x_plan), _safe_root(Path(two_x_root), "2x")),
    }
    v14: dict[str, Any] = {}
    receipts: dict[str, dict[str, Any]] = {}
    for scale, (plan_path, root) in supplied.items():
        plan_raw, plan = _read_plan(plan_path, scale, rate)
        try:
            receipt = legacy.validate_final_set(plan, root)
        except legacy.LegacyAuditError as exc:
            raise ProvenanceOverlapError(f"{scale} sealed V-14 audit fails: {exc}") from exc
        expected_receipt = rate["input_identities"]["v14"][scale].get("audit_receipt_content_sha256")
        _require(receipt.get("content_sha256") == expected_receipt,
                 f"{scale} regenerated receipt differs from the accepted Gate-6 binding")
        receipts[scale] = receipt
        v14[scale] = {
            "artifact_root": str(root),
            "plan_file_sha256": _sha256(plan_raw),
            "plan_content_sha256": plan["content_sha256"],
            "audit_receipt": receipt,
        }
    overlaps = _overlaps(receipts, axis)
    authority_hashes = {
        OWNER_DECISIONS_REL: _sha256(_read_regular_bytes(ROOT / OWNER_DECISIONS_REL, "Gate-6 owner decisions")),
        RATE_REL: ACCEPTED_RATE_FILE_SHA256,
        G4_LEDGER_REL: _sha256(_read_regular_bytes(ROOT / G4_LEDGER_REL, "Gate-4 primary ledger")),
    }
    body = {
        "schema": SCHEMA,
        "purpose": "durable non-scientific CUDA/T4 V-14 provenance and Gate-5 overlap identity audit",
        "reviewed_handoff": reviewed_handoff,
        "accepted_rate_surface": {"file_sha256": ACCEPTED_RATE_FILE_SHA256, "content_sha256": ACCEPTED_RATE_CONTENT_SHA256},
        "authority_file_sha256": authority_hashes,
        "gate5_registry_content_sha256": ratified_g5_input.REGISTRY_CONTENT_SHA256,
        "v14": v14,
        "overlap": overlaps,
        "producer_source_sha256": _source_hashes(),
        "scientific_outputs": "intentionally absent",
    }
    body["content_sha256"] = hashlib.sha256(canonical_bytes(body)).hexdigest()
    return body


def _safe_output(target: Path) -> None:
    _require(target.is_absolute(), "output directory must be absolute")
    try:
        target.relative_to(ROOT / "research" / "g6")
    except ValueError as exc:
        raise ProvenanceOverlapError("output directory must be under research/g6") from exc
    _require(not target.exists() and not target.is_symlink(), "output directory already exists")
    _require(target.parent.is_dir() and not target.parent.is_symlink(), "output parent is not a regular directory")


def write_new(output_dir: Path, payload: Mapping[str, Any]) -> None:
    """Atomically publish the summary, both durable receipts, and manifest."""
    target = Path(output_dir)
    _safe_output(target)
    v14 = payload.get("v14")
    _require(isinstance(v14, dict) and set(v14) == set(RECEIPT_NAMES), "payload lacks both V-14 receipts")
    receipts: dict[str, Mapping[str, Any]] = {}
    receipt_bindings: dict[str, dict[str, str]] = {}
    for scale, filename in RECEIPT_NAMES.items():
        entry = v14.get(scale)
        _require(isinstance(entry, dict) and isinstance(entry.get("audit_receipt"), dict),
                 f"payload lacks {scale} receipt")
        receipt = entry["audit_receipt"]
        _require_content(receipt, f"{scale} receipt")
        receipts[scale] = receipt
        receipt_bindings[scale] = {
            "file": filename,
            "file_sha256": hashlib.sha256(canonical_bytes(receipt)).hexdigest(),
            "content_sha256": receipt["content_sha256"],
        }
    manifest = {
        "schema": SCHEMA_MANIFEST,
        "artifact_file": OUTPUT_NAME,
        "artifact_file_sha256": hashlib.sha256(canonical_bytes(payload)).hexdigest(),
        "artifact_content_sha256": payload.get("content_sha256"),
        "audit_receipts": receipt_bindings,
        "reviewed_handoff": payload.get("reviewed_handoff"),
        "producer_source_sha256": payload.get("producer_source_sha256"),
    }
    manifest["content_sha256"] = hashlib.sha256(canonical_bytes(manifest)).hexdigest()
    staging = Path(tempfile.mkdtemp(prefix=f".{target.name}.pending-", dir=target.parent))
    try:
        output_files: list[tuple[str, Mapping[str, Any]]] = [(OUTPUT_NAME, payload)]
        output_files.extend((RECEIPT_NAMES[scale], receipts[scale]) for scale in ("0.5x", "2x"))
        output_files.append((MANIFEST_NAME, manifest))
        for name, value in output_files:
            path = staging / name
            with path.open("wb") as stream:
                stream.write(canonical_bytes(value))
                stream.flush()
                os.fsync(stream.fileno())
        os.replace(staging, target)
        directory = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except OSError as exc:
        raise ProvenanceOverlapError(f"artifact promotion failed: {exc}") from exc
    finally:
        if staging.exists():
            for item in staging.iterdir():
                item.unlink()
            staging.rmdir()


def validate_published(output_dir: Path, *, zero_five_plan: Path, zero_five_root: Path,
                       two_x_plan: Path, two_x_root: Path, reviewed_handoff: str) -> dict[str, str]:
    directory = Path(output_dir)
    _require(directory.is_dir() and not directory.is_symlink(), "published output directory is absent or symlinked")
    _require(sorted(item.name for item in directory.iterdir()) == sorted([MANIFEST_NAME, OUTPUT_NAME, *RECEIPT_NAMES.values()]),
             "published output membership differs")
    raw, payload = _read_json(directory / OUTPUT_NAME, "published provenance artifact")
    manifest_raw, manifest = _read_json(directory / MANIFEST_NAME, "published provenance manifest")
    _require_content(payload, "published provenance artifact")
    _require_content(manifest, "published provenance manifest")
    _require(manifest.get("schema") == SCHEMA_MANIFEST and manifest.get("artifact_file_sha256") == _sha256(raw)
             and manifest.get("artifact_content_sha256") == payload.get("content_sha256"), "published manifest binding differs")
    v14 = payload.get("v14")
    bindings = manifest.get("audit_receipts")
    _require(isinstance(v14, dict) and isinstance(bindings, dict) and set(bindings) == set(RECEIPT_NAMES),
             "published receipt bindings are malformed")
    for scale, filename in RECEIPT_NAMES.items():
        receipt_raw, receipt = _read_json(directory / filename, f"published {scale} receipt")
        _require_content(receipt, f"published {scale} receipt")
        binding = bindings[scale]
        _require(isinstance(binding, dict) and binding == {
            "file": filename,
            "file_sha256": _sha256(receipt_raw),
            "content_sha256": receipt.get("content_sha256"),
        }, f"published {scale} receipt manifest binding differs")
        _require(isinstance(v14.get(scale), dict) and receipt == v14[scale].get("audit_receipt"),
                 f"published {scale} receipt differs from the provenance summary")
    rebuilt = build(zero_five_plan=zero_five_plan, zero_five_root=zero_five_root,
                    two_x_plan=two_x_plan, two_x_root=two_x_root, reviewed_handoff=reviewed_handoff)
    _require(canonical_bytes(payload) == canonical_bytes(rebuilt), "published provenance artifact differs from current read-only replay")
    return {"file_sha256": _sha256(raw), "content_sha256": payload["content_sha256"], "manifest_file_sha256": _sha256(manifest_raw)}

"""Bounded mechanical D011-versus-primary matched-subgrid comparison.

This module reads the owner-accepted D011 transition artifact and the
owner-ratified Gate-5 boundary.  It selects *only* the Gate-5 ``r=1`` records
whose three primary-grid indices are ``0, 5, ..., 60``.  Those are the exact
2,197 coordinates of D011's declared 13-by-13-by-13 coarse grid.

It emits global A/B/C counts and ``rho_E^exact = A_count / 2197`` as exact
integer fractions for the primary condition of each encoding, together with
the exact D011-minus-Gate-5 numerator.  It never evaluates energy, builds a
domain, creates a tie set, runs a sensitivity, fits, ranks, or interprets.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Iterable, Mapping

import src.g6.d011_transition_output as transition
import src.g6.ratified_g5_input as ratified_g5_input
from src.g6.ledgers import canonical_bytes


ROOT = Path(__file__).resolve().parents[2]
AUTHORIZATION_REL = "research/decisions/GATE_6_D011_MATCHED_SUBGRID_AUTHORIZATION.md"
AUTHORIZATION_SHA256 = "f9f5a097359c00d874f07e0ad68bade548c2eb07e0f02ed415c5ed27d1c763aa"

TRANSITION_REL = "research/g6/d011_transition_output"
TRANSITION_OUTPUT_FILENAME = "D011_TRANSITION_OUTPUT.json"
TRANSITION_MANIFEST_FILENAME = "manifest.json"
TRANSITION_OUTPUT_SHA256 = "bf70a64980912db7fa88cc03e7c4cd03d1ff2878214e4bb0d846cb2900ef9f34"
TRANSITION_CONTENT_SHA256 = "5adc8f03e8a4193e07bc37381a2aad1f67cd72119cce416ceebcfece184f528c"
TRANSITION_REVIEWED_HANDOFF = "claude-d011-transition-output-delta-2026-09-20"

DEFAULT_OUTPUT_REL = "research/g6/d011_matched_subgrid_comparison"
OUTPUT_FILENAME = "D011_MATCHED_SUBGRID_COMPARISON.json"
MANIFEST_FILENAME = "manifest.json"
SCHEMA = "decisions_os/g6_d011_matched_subgrid_comparison/v1"
MANIFEST_SCHEMA = "decisions_os/g6_d011_matched_subgrid_comparison_manifest/v1"

AXES = ("ell_card", "ell_sector", "ell_budget")
ENCODINGS = ("unbalanced", "slack")
LABELS = ("A", "B", "C")
PRIMARY_R_HEX = "0x1.0000000000000p+0"
PRIMARY_C_H = 2048
PRIMARY_C_F = 2048
COARSE_INDICES = tuple(range(13))
PRIMARY_INDICES = tuple(index * 5 for index in COARSE_INDICES)
MATCHED_COORDINATE_COUNT = 13 ** 3

PURPOSE = "Mechanical D011-to-Gate-5 matched-subgrid rho comparison only."
OUTPUT_SCOPE = (
    "exact matched-grid A/B/C counts and rho_E^exact integer fractions for the "
    "primary condition only; no inference, fitting, V-14, D013, GPU output, or label lattice"
)
SCIENTIFIC_OUTPUTS = "mechanical matched-subgrid rho comparison only"


class D011MatchedSubgridError(RuntimeError):
    """Raised when the bounded matched-subgrid contract cannot be established."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise D011MatchedSubgridError(message)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path, label: str) -> str:
    try:
        return _sha256_bytes(path.read_bytes())
    except OSError as exc:
        raise D011MatchedSubgridError(f"{label} is unreadable") from exc


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise D011MatchedSubgridError(f"{label} is unreadable JSON") from exc
    _require(isinstance(value, dict), f"{label} must be a JSON object")
    return value


def _validate_content_hash(payload: Mapping[str, Any], label: str) -> None:
    body = dict(payload)
    digest = body.pop("content_sha256", None)
    _require(isinstance(digest, str) and digest == _sha256_bytes(canonical_bytes(body)),
             f"{label} canonical content hash mismatch")


def _owner_authorization() -> dict[str, str]:
    path = ROOT / AUTHORIZATION_REL
    observed = _sha256_file(path, "D011 matched-subgrid owner authorization")
    _require(observed == AUTHORIZATION_SHA256,
             "D011 matched-subgrid owner authorization differs from the approved record")
    return {"path": AUTHORIZATION_REL, "file_sha256": observed}


def _transition_dir() -> Path:
    directory = ROOT / TRANSITION_REL
    _require(directory.is_dir() and not directory.is_symlink(),
             "accepted D011 transition artifact directory is unavailable")
    _require({path.name for path in directory.iterdir()} == {
        TRANSITION_OUTPUT_FILENAME, TRANSITION_MANIFEST_FILENAME
    }, "accepted D011 transition artifact membership mismatch")
    return directory


def _transition_primary_labels() -> tuple[dict[str, dict[tuple[int, int, int], str]], dict[str, Any]]:
    """Validate and extract only the accepted primary-condition D011 lattice."""
    directory = _transition_dir()
    output_path = directory / TRANSITION_OUTPUT_FILENAME
    _require(_sha256_file(output_path, "accepted D011 transition output") == TRANSITION_OUTPUT_SHA256,
             "accepted D011 transition output file identity differs from the owner-accepted artifact")
    try:
        transition.validate_published_transition_output(
            directory, expected_reviewed_handoff=TRANSITION_REVIEWED_HANDOFF
        )
    except transition.TransitionOutputError as exc:
        raise D011MatchedSubgridError(f"accepted D011 transition artifact is invalid: {exc}") from exc
    payload = _read_json(output_path, "accepted D011 transition output")
    _validate_content_hash(payload, "accepted D011 transition output")
    _require(payload.get("content_sha256") == TRANSITION_CONTENT_SHA256,
             "accepted D011 transition output canonical identity differs from the owner-accepted artifact")
    configurations = payload.get("configurations")
    _require(isinstance(configurations, list) and len(configurations) == 10,
             "accepted D011 transition configuration population is malformed")
    expected_coordinates = {
        (card, sector, budget)
        for card in COARSE_INDICES
        for sector in COARSE_INDICES
        for budget in COARSE_INDICES
    }
    labels: dict[str, dict[tuple[int, int, int], str]] = {}
    for configuration in configurations:
        _require(isinstance(configuration, dict), "accepted D011 transition configuration is malformed")
        condition = configuration.get("condition")
        encoding = configuration.get("encoding")
        if not (isinstance(condition, dict)
                and condition.get("c_H") == PRIMARY_C_H
                and condition.get("c_f") == PRIMARY_C_F
                and condition.get("role") == "primary"):
            continue
        _require(encoding in ENCODINGS and encoding not in labels,
                 "accepted D011 primary configuration is malformed or duplicated")
        lattice = configuration.get("label_lattice")
        _require(isinstance(lattice, list) and len(lattice) == MATCHED_COORDINATE_COUNT,
                 "accepted D011 primary label lattice size is invalid")
        extracted: dict[tuple[int, int, int], str] = {}
        for entry in lattice:
            _require(isinstance(entry, dict) and set(entry) == {*AXES, "set_label"},
                     "accepted D011 primary lattice entry is malformed")
            coordinate = tuple(entry[axis] for axis in AXES)
            label = entry.get("set_label")
            _require(all(isinstance(value, int) and value in COARSE_INDICES for value in coordinate)
                     and label in LABELS,
                     "accepted D011 primary lattice coordinate or label is invalid")
            _require(coordinate not in extracted, "accepted D011 primary label lattice has a duplicate coordinate")
            extracted[coordinate] = label
        _require(set(extracted) == expected_coordinates,
                 "accepted D011 primary label lattice is incomplete or has a foreign coordinate")
        labels[encoding] = extracted
    _require(set(labels) == set(ENCODINGS),
             "accepted D011 transition artifact lacks one primary encoding")
    return labels, payload


@dataclass(frozen=True)
class VerifiedInputs:
    d011_labels: dict[str, dict[tuple[int, int, int], str]]
    gate5_labels: dict[str, dict[tuple[int, int, int], str]]
    transition_payload: dict[str, Any]
    gate5_reference: dict[str, Any]


def _gate5_matched_primary_labels(records: Iterable[Mapping[str, Any]]) -> dict[str, dict[tuple[int, int, int], str]]:
    """Select the exact 13-cubed `r=1` primary lattice from verified G5 records."""
    labels = {encoding: {} for encoding in ENCODINGS}
    for record in records:
        key = record.get("key")
        _require(isinstance(key, dict) and set(key) == {*AXES, "r_hex"},
                 "ratified Gate-5 record has a malformed key")
        if key.get("r_hex") != PRIMARY_R_HEX:
            continue
        coordinate = tuple(key[axis] for axis in AXES)
        _require(all(isinstance(value, int) and 0 <= value <= 60 for value in coordinate),
                 "ratified Gate-5 r=1 coordinate is malformed")
        if not all(value in PRIMARY_INDICES for value in coordinate):
            continue
        coarse_coordinate = tuple(value // 5 for value in coordinate)
        for encoding in ENCODINGS:
            certification = record.get(encoding)
            _require(isinstance(certification, dict)
                     and certification.get("set_label") in LABELS
                     and isinstance(certification.get("tie_comparator"), dict)
                     and certification["tie_comparator"].get("c_H") == PRIMARY_C_H,
                     f"ratified Gate-5 primary {encoding} certification is malformed")
            label = certification["set_label"]
            _require(coarse_coordinate not in labels[encoding],
                     "ratified Gate-5 matched subgrid has a duplicate coordinate")
            labels[encoding][coarse_coordinate] = label
    expected_coordinates = {
        (card, sector, budget)
        for card in COARSE_INDICES
        for sector in COARSE_INDICES
        for budget in COARSE_INDICES
    }
    for encoding in ENCODINGS:
        _require(set(labels[encoding]) == expected_coordinates,
                 f"ratified Gate-5 matched subgrid is incomplete for {encoding}")
    return labels


def _load_verified_inputs() -> VerifiedInputs:
    d011_labels, transition_payload = _transition_primary_labels()
    try:
        registry = ratified_g5_input._load_ratified_registry()
        gate5_labels = _gate5_matched_primary_labels(ratified_g5_input.iter_ratified_records())
    except ratified_g5_input.RatifiedG5InputError as exc:
        raise D011MatchedSubgridError(f"ratified Gate-5 input validation failed: {exc}") from exc
    accepted = registry.get("accepted_gate5")
    _require(isinstance(accepted, dict)
             and accepted.get("shard_count") == 11163
             and accepted.get("coordinate_count") == 680943
             and isinstance(accepted.get("source_snapshot"), dict),
             "ratified Gate-5 accepted identity is malformed")
    return VerifiedInputs(
        d011_labels=d011_labels,
        gate5_labels=gate5_labels,
        transition_payload=transition_payload,
        gate5_reference={
            "ratification": {
                "path": ratified_g5_input.RATIFICATION_REL,
                "file_sha256": ratified_g5_input.RATIFICATION_FILE_SHA256,
            },
            "identity_registry": {
                "path": ratified_g5_input.REGISTRY_REL,
                "file_sha256": ratified_g5_input.REGISTRY_FILE_SHA256,
                "content_sha256": ratified_g5_input.REGISTRY_CONTENT_SHA256,
            },
            "accepted_gate5": {
                "coverage_audit_content_sha256": accepted["coverage_audit_content_sha256"],
                "resume_manifest_content_sha256": accepted["resume_manifest_content_sha256"],
                "source_snapshot": dict(accepted["source_snapshot"]),
                "shard_count": accepted["shard_count"],
                "coordinate_count": accepted["coordinate_count"],
            },
            "selection": {
                "r_hex": PRIMARY_R_HEX,
                "axis_indices": list(PRIMARY_INDICES),
                "coordinate_count": MATCHED_COORDINATE_COUNT,
                "mapping": "Gate-5 primary coordinate (5*i,5*j,5*k) maps to D011 coordinate (i,j,k)",
            },
        },
    )


def _counts(labels: Mapping[tuple[int, int, int], str]) -> dict[str, int]:
    counts = {label: 0 for label in LABELS}
    for label in labels.values():
        _require(label in counts, "matched subgrid has an invalid label")
        counts[label] += 1
    _require(sum(counts.values()) == MATCHED_COORDINATE_COUNT,
             "matched subgrid count does not cover exactly 2,197 coordinates")
    return counts


def _fraction(numerator: int) -> dict[str, int]:
    _require(type(numerator) is int, "rho numerator must be an exact integer")
    return {"numerator": numerator, "denominator": MATCHED_COORDINATE_COUNT}


def _comparison(encoding: str, gate5_labels: Mapping[tuple[int, int, int], str],
                d011_labels: Mapping[tuple[int, int, int], str]) -> dict[str, Any]:
    gate5_counts = _counts(gate5_labels)
    d011_counts = _counts(d011_labels)
    return {
        "encoding": encoding,
        "metric": "rho_E^exact = A_count / matched_grid_coordinate_count",
        "matched_grid_coordinate_count": MATCHED_COORDINATE_COUNT,
        "accepted_gate5_r1": {
            "exact_integer_count_by_label": gate5_counts,
            "rho_E_exact": _fraction(gate5_counts["A"]),
        },
        "d011_companion_primary": {
            "exact_integer_count_by_label": d011_counts,
            "rho_E_exact": _fraction(d011_counts["A"]),
        },
        "d011_minus_gate5_rho_E_exact": _fraction(d011_counts["A"] - gate5_counts["A"]),
    }


def _producer_source_hashes() -> dict[str, str]:
    return {
        "src/g6/d011_matched_subgrid.py": _sha256_file(Path(__file__).resolve(), "matched-subgrid source"),
        "research/g6/make_d011_matched_subgrid_comparison.py": _sha256_file(
            ROOT / "research/g6/make_d011_matched_subgrid_comparison.py", "matched-subgrid command"
        ),
    }


def build_comparison(reviewed_handoff: str) -> dict[str, Any]:
    """Build the bounded comparison in memory after complete input validation."""
    _require(isinstance(reviewed_handoff, str) and reviewed_handoff.strip(),
             "a non-empty independent-review handoff identifier is required")
    inputs = _load_verified_inputs()
    payload = {
        "schema": SCHEMA,
        "purpose": PURPOSE,
        "approved_output_scope": OUTPUT_SCOPE,
        "owner_authorization": _owner_authorization(),
        "reviewed_handoff": reviewed_handoff,
        "transition_artifact": {
            "path": TRANSITION_REL,
            "output": {
                "path": TRANSITION_OUTPUT_FILENAME,
                "file_sha256": TRANSITION_OUTPUT_SHA256,
                "content_sha256": TRANSITION_CONTENT_SHA256,
            },
            "reviewed_handoff": TRANSITION_REVIEWED_HANDOFF,
        },
        "gate5_reference": inputs.gate5_reference,
        "primary_condition": {"c_H": PRIMARY_C_H, "c_f": PRIMARY_C_F},
        "comparisons": [
            _comparison(encoding, inputs.gate5_labels[encoding], inputs.d011_labels[encoding])
            for encoding in ENCODINGS
        ],
        "producer_source_sha256": _producer_source_hashes(),
        "scientific_outputs": SCIENTIFIC_OUTPUTS,
    }
    payload["content_sha256"] = _sha256_bytes(canonical_bytes(payload))
    return payload


def validate_comparison(payload: Mapping[str, Any], expected_reviewed_handoff: str | None = None) -> None:
    """Replay the complete bounded construction and reject every output drift."""
    _validate_content_hash(payload, "D011 matched-subgrid comparison")
    _require(payload.get("schema") == SCHEMA
             and payload.get("purpose") == PURPOSE
             and payload.get("approved_output_scope") == OUTPUT_SCOPE
             and payload.get("owner_authorization") == _owner_authorization()
             and payload.get("primary_condition") == {"c_H": PRIMARY_C_H, "c_f": PRIMARY_C_F}
             and payload.get("scientific_outputs") == SCIENTIFIC_OUTPUTS,
             "D011 matched-subgrid comparison contract mismatch")
    reviewed = payload.get("reviewed_handoff")
    _require(isinstance(reviewed, str) and reviewed.strip(),
             "D011 matched-subgrid comparison lacks a review handoff")
    if expected_reviewed_handoff is not None:
        _require(isinstance(expected_reviewed_handoff, str) and expected_reviewed_handoff.strip(),
                 "expected review handoff must be a non-empty string")
        _require(reviewed == expected_reviewed_handoff,
                 "D011 matched-subgrid review handoff differs from the expected identifier")
    _require(payload.get("producer_source_sha256") == _producer_source_hashes(),
             "D011 matched-subgrid producer source differs from the emitted producer hashes")
    expected = build_comparison(reviewed)
    _require(canonical_bytes(dict(payload)) == canonical_bytes(expected),
             "D011 matched-subgrid comparison differs from its validated input replay")


def build_plan() -> dict[str, Any]:
    """Validate both input boundaries and describe one no-write bounded output."""
    _load_verified_inputs()
    return {
        "schema": "decisions_os/g6_d011_matched_subgrid_comparison_plan/v1",
        "gate5_r_hex": PRIMARY_R_HEX,
        "gate5_axis_indices": list(PRIMARY_INDICES),
        "matched_coordinates": MATCHED_COORDINATE_COUNT,
        "encodings": list(ENCODINGS),
        "primary_condition": {"c_H": PRIMARY_C_H, "c_f": PRIMARY_C_F},
        "approved_output_scope": OUTPUT_SCOPE,
        "writes": "none",
        "scientific_outputs": SCIENTIFIC_OUTPUTS,
    }


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_new(path: Path, payload: Mapping[str, Any]) -> None:
    descriptor: int | None = None
    temporary: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.pending-", dir=path.parent)
        temporary = Path(temporary_name)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = None
            stream.write(canonical_bytes(payload))
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o644)
        try:
            os.link(temporary, path)
        except FileExistsError as exc:
            raise D011MatchedSubgridError(f"refusing to overwrite existing matched-subgrid output: {path}") from exc
        _fsync_directory(path.parent)
    except OSError as exc:
        raise D011MatchedSubgridError(f"matched-subgrid publication failed for {path}: {exc}") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary is not None:
            try:
                temporary.unlink()
            except OSError:
                pass


def _require_safe_output_dir(output_dir: Path | str) -> Path:
    target = Path(output_dir)
    root = (ROOT / "research/g6").resolve()
    resolved = target.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise D011MatchedSubgridError("matched-subgrid output directory must be under research/g6") from exc
    _require(resolved.parent == root,
             "matched-subgrid output directory must be a dedicated direct child of research/g6")
    _require(resolved != (ROOT / TRANSITION_REL).resolve(),
             "matched-subgrid output may not share the immutable transition input directory")
    _require(not target.exists(), f"refusing to write into existing output directory: {target}")
    return target


def write_comparison(output_dir: Path | str, reviewed_handoff: str) -> dict[str, Any]:
    """Publish one reviewed comparison in a new direct child of ``research/g6``."""
    _require(os.environ.get("PYTHONDONTWRITEBYTECODE") == "1", "PYTHONDONTWRITEBYTECODE=1 is required")
    target = _require_safe_output_dir(output_dir)
    payload = build_comparison(reviewed_handoff)
    validate_comparison(payload, reviewed_handoff)
    try:
        target.mkdir(parents=True, exist_ok=False)
        os.chmod(target, 0o755)
    except OSError as exc:
        raise D011MatchedSubgridError(f"unable to create matched-subgrid output directory: {target}: {exc}") from exc
    try:
        output_path = target / OUTPUT_FILENAME
        _write_new(output_path, payload)
        manifest = {
            "schema": MANIFEST_SCHEMA,
            "reviewed_handoff": reviewed_handoff,
            "owner_authorization": _owner_authorization(),
            "producer_source_sha256": payload["producer_source_sha256"],
            "transition_artifact": payload["transition_artifact"],
            "gate5_reference": payload["gate5_reference"],
            "output": {
                "path": OUTPUT_FILENAME,
                "file_sha256": _sha256_file(output_path, "D011 matched-subgrid comparison"),
                "content_sha256": payload["content_sha256"],
            },
            "scientific_outputs": SCIENTIFIC_OUTPUTS,
        }
        manifest["content_sha256"] = _sha256_bytes(canonical_bytes(manifest))
        _write_new(target / MANIFEST_FILENAME, manifest)
        return {
            "output_dir": str(target),
            "output_file": str(output_path),
            "output_content_sha256": payload["content_sha256"],
            "scientific_outputs": SCIENTIFIC_OUTPUTS,
        }
    except Exception:
        for name in (MANIFEST_FILENAME, OUTPUT_FILENAME):
            try:
                (target / name).unlink()
            except OSError:
                pass
        try:
            target.rmdir()
            _fsync_directory(target.parent)
        except OSError:
            pass
        raise


def validate_published_comparison(output_dir: Path | str,
                                  expected_reviewed_handoff: str | None = None) -> None:
    """Read-only validation of one published bounded comparison."""
    directory = Path(output_dir)
    _require(directory.is_dir() and not directory.is_symlink(),
             "matched-subgrid output directory is unavailable or a symlink")
    _require({path.name for path in directory.iterdir()} == {OUTPUT_FILENAME, MANIFEST_FILENAME},
             "matched-subgrid output directory membership mismatch")
    output = _read_json(directory / OUTPUT_FILENAME, "D011 matched-subgrid output")
    manifest = _read_json(directory / MANIFEST_FILENAME, "D011 matched-subgrid manifest")
    _validate_content_hash(manifest, "D011 matched-subgrid manifest")
    _require(manifest.get("schema") == MANIFEST_SCHEMA
             and manifest.get("owner_authorization") == _owner_authorization()
             and manifest.get("producer_source_sha256") == output.get("producer_source_sha256")
             and manifest.get("transition_artifact") == output.get("transition_artifact")
             and manifest.get("gate5_reference") == output.get("gate5_reference")
             and manifest.get("scientific_outputs") == SCIENTIFIC_OUTPUTS,
             "D011 matched-subgrid manifest contract mismatch")
    entry = manifest.get("output")
    _require(isinstance(entry, dict) and entry.get("path") == OUTPUT_FILENAME
             and entry.get("file_sha256") == _sha256_file(directory / OUTPUT_FILENAME,
                                                           "D011 matched-subgrid output")
             and entry.get("content_sha256") == output.get("content_sha256"),
             "D011 matched-subgrid manifest output identity mismatch")
    reviewed = manifest.get("reviewed_handoff")
    _require(isinstance(reviewed, str) and reviewed.strip(),
             "D011 matched-subgrid manifest lacks a review handoff")
    if expected_reviewed_handoff is not None:
        _require(reviewed == expected_reviewed_handoff,
                 "D011 matched-subgrid manifest review handoff differs from the expected identifier")
    _require(output.get("reviewed_handoff") == reviewed,
             "D011 matched-subgrid output and manifest review handoffs differ")
    validate_comparison(output, expected_reviewed_handoff)

"""Mechanical transition output for the completed Gate-6 D011 companion pass.

This module consumes only the completed, CPU-produced D011 artifact.  It
validates the artifact's full identity/provenance boundary and emits exactly
the transition representation approved in
``GATE_6_OWNER_EXECUTION_DECISIONS.md``: every label lattice, exact integer
count tables, and every face-adjacent unequal-label edge.  It does not
evaluate an energy, build a domain, derive a tie set, fit, smooth, rank,
trigger, or interpret anything.  It never reads or writes the Gate-5 corpus.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping

from src.g6 import d011_runner as d011
from src.g6.ledgers import canonical_bytes


ROOT = Path(__file__).resolve().parents[2]
INPUT_REL = "research/g6/d011_curvature_companion"
DEFAULT_OUTPUT_REL = "research/g6/d011_transition_output"
OWNER_DECISION_REL = "research/decisions/GATE_6_OWNER_EXECUTION_DECISIONS.md"
OWNER_DECISION_SHA256 = "0d7d212dd1205a8c1c84d702f0f8b44a444b952d84c29a6a352d9a17b716e4fe"

SCHEMA = "decisions_os/g6_d011_transition_output/v1"
MANIFEST_SCHEMA = "decisions_os/g6_d011_transition_output_manifest/v1"
OUTPUT_FILENAME = "D011_TRANSITION_OUTPUT.json"
MANIFEST_FILENAME = "manifest.json"
AXES = ("ell_card", "ell_sector", "ell_budget")
LABELS = ("A", "B", "C")
ENCODINGS = ("unbalanced", "slack")
PRIMARY = (2048, 2048, "primary")
OUTPUT_SCOPE = (
    "full label lattice, exact integer count tables, and complete face-adjacent "
    "unequal-label edges only; no fitting, smoothing, ranking, or interpretation"
)


class TransitionOutputError(RuntimeError):
    """Raised when the approved D011 transition-output contract is not established."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise TransitionOutputError(message)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path, label: str) -> str:
    try:
        return _sha256_bytes(path.read_bytes())
    except OSError as exc:
        raise TransitionOutputError(f"{label} is unreadable") from exc


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TransitionOutputError(f"{label} is unreadable JSON") from exc
    _require(isinstance(value, dict), f"{label} must be a JSON object")
    return value


def _validate_content_hash(payload: Mapping[str, Any], label: str) -> None:
    body = dict(payload)
    digest = body.pop("content_sha256", None)
    _require(isinstance(digest, str) and digest == _sha256_bytes(canonical_bytes(body)),
             f"{label} canonical content hash mismatch")


def _owner_authorization() -> dict[str, str]:
    path = ROOT / OWNER_DECISION_REL
    observed = _sha256_file(path, "Gate-6 owner execution decision")
    _require(observed == OWNER_DECISION_SHA256,
             "Gate-6 owner execution decision differs from the approved record")
    return {"path": OWNER_DECISION_REL, "file_sha256": observed}


def _condition_descriptors() -> tuple[tuple[int, int, str], ...]:
    """The primary plus every frozen D015 diagnostic, in frozen declaration order."""
    return (PRIMARY,) + tuple((c_h, c_f, "diagnostic") for c_h, c_f in d011.DIAGNOSTIC_PAIRS)


def _condition_id(c_h: int, c_f: int) -> str:
    return f"c_H={c_h}__c_f={c_f}"


def _certification(record: Mapping[str, Any], c_h: int, c_f: int, encoding: str) -> Mapping[str, Any]:
    if (c_h, c_f) == PRIMARY[:2]:
        family = record.get("primary_c_h_2048")
    else:
        diagnostics = record.get("d015_diagnostics")
        family = diagnostics.get(_condition_id(c_h, c_f)) if isinstance(diagnostics, dict) else None
    _require(isinstance(family, dict), f"missing D015 condition {_condition_id(c_h, c_f)}")
    value = family.get(encoding)
    _require(isinstance(value, dict), f"missing {encoding} certification for {_condition_id(c_h, c_f)}")
    return value


def _validate_label(certification: Mapping[str, Any], label: str, c_h: int) -> None:
    _require(label in LABELS, "certification has an invalid D016 set label")
    raw = certification.get("set_label")
    _require(raw == label, "certification label extraction drift")
    tied = certification.get("X_E")
    _require(isinstance(tied, list) and len(tied) == certification.get("X_E_size") and tied
             and all(isinstance(entry, dict) for entry in tied),
             "certification has an invalid decoded tie set")
    comparator = certification.get("tie_comparator")
    _require(isinstance(comparator, dict) and comparator.get("c_H") == c_h,
             "certification tie comparator is not bound to its D015 c_H")
    atomic = {entry.get("atomic_label") for entry in tied}
    _require(len(atomic) > 0 and atomic <= set(LABELS), "certification has invalid atomic labels")
    expected = "C" if "C" in atomic else ("A" if atomic == {"A"} else "B")
    _require(label == expected, "certification fails the frozen D016 set-label rule")


def _coordinate_from_key(key: Mapping[str, Any]) -> tuple[int, int, int]:
    try:
        coordinate = tuple(key[axis] for axis in AXES)
    except KeyError as exc:
        raise TransitionOutputError("D011 key lacks a lattice axis") from exc
    _require(all(isinstance(value, int) and 0 <= value < d011.AXIS_COUNT for value in coordinate),
             "D011 lattice coordinate is outside 0..12")
    return coordinate  # type: ignore[return-value]


@dataclass(frozen=True)
class VerifiedD011Input:
    input_dir: Path
    coverage: dict[str, Any]
    resume: dict[str, Any]
    ledger: dict[str, Any]
    ledger_manifest: dict[str, Any]
    source_snapshot: dict[str, str]
    platform: dict[str, Any]
    shard_digests: tuple[dict[str, str], ...]
    labels: dict[tuple[int, int, str], dict[str, dict[tuple[int, int, int], str]]]


def load_verified_d011_input(input_dir: Path | str = ROOT / INPUT_REL) -> VerifiedD011Input:
    """Read and fail-closed validate the finished D011 artifact before aggregation."""
    directory = Path(input_dir)
    expected_directory = (ROOT / INPUT_REL).resolve()
    _require(directory.resolve() == expected_directory,
             "transition input must be the completed D011 artifact under research/g6")
    _require(directory.is_dir() and not directory.is_symlink(), "D011 input directory is unavailable or a symlink")
    ledger, ledger_manifest = d011._load_d011_ledger()
    expected_tasks = d011.d011_tasks()
    expected_ids = {d011._d011_shard_id(card, sector) for card, sector in expected_tasks}
    expected_names = {f"{shard_id}.json" for shard_id in expected_ids} | {
        "coverage_audit.json", "resume_manifest.json"
    }
    actual_names = {path.name for path in directory.iterdir()}
    _require(actual_names == expected_names, "D011 input directory membership differs from the completed artifact")
    for name in actual_names:
        _require(not (directory / name).is_symlink(), f"D011 input member is a symlink: {name}")

    coverage = _read_json(directory / "coverage_audit.json", "D011 coverage audit")
    resume = _read_json(directory / "resume_manifest.json", "D011 resume manifest")
    _validate_content_hash(coverage, "D011 coverage audit")
    _validate_content_hash(resume, "D011 resume manifest")
    _require(coverage.get("schema") == d011.COVERAGE_SCHEMA
             and resume.get("schema") == d011.MANIFEST_SCHEMA,
             "D011 final manifest schema mismatch")
    snapshot = coverage.get("source_snapshot")
    platform = coverage.get("platform")
    _require(isinstance(snapshot, dict) and all(isinstance(k, str) and isinstance(v, str)
                                                 for k, v in snapshot.items()),
             "D011 coverage source snapshot is malformed")
    _require(isinstance(platform, dict), "D011 coverage platform fingerprint is malformed")
    _require(coverage.get("pass_id") == "d011_curvature_companion"
             and coverage.get("ledger_content_sha256") == ledger.get("content_sha256")
             and coverage.get("shard_count") == d011.EXPECTED_SHARDS
             and coverage.get("coordinate_count") == d011.EXPECTED_COORDINATES
             and coverage.get("scientific_outputs") == "intentionally absent",
             "D011 coverage audit binding mismatch")
    _require(resume.get("pass_id") == "d011_curvature_companion"
             and resume.get("source_snapshot") == snapshot
             and resume.get("platform") == platform
             and resume.get("ledger_content_sha256") == ledger.get("content_sha256")
             and resume.get("expected_shards") == d011.EXPECTED_SHARDS
             and resume.get("expected_coordinates") == d011.EXPECTED_COORDINATES
             and resume.get("completed_shards") == sorted(expected_ids)
             and resume.get("in_progress") is False
             and resume.get("stopped_for_budget") is False
             and resume.get("scientific_outputs") == "intentionally absent",
             "D011 resume manifest does not describe one complete final artifact")
    try:
        current = d011._current_hashes(snapshot)
    except d011.D011Error as exc:
        raise TransitionOutputError(str(exc)) from exc
    _require(current == snapshot, "D011 source/input snapshot drift after the pass")
    _require(snapshot.get(OWNER_DECISION_REL) == OWNER_DECISION_SHA256,
             "D011 input is not bound to the approved transition authority")
    _require(_owner_authorization()["file_sha256"] == snapshot[OWNER_DECISION_REL],
             "transition authority drift after D011 pass")

    labels: dict[tuple[int, int, str], dict[str, dict[tuple[int, int, int], str]]] = {
        descriptor: {encoding: {} for encoding in ENCODINGS} for descriptor in _condition_descriptors()
    }
    shard_digests: list[dict[str, str]] = []
    for task in expected_tasks:
        shard_id = d011._d011_shard_id(*task)
        path = directory / f"{shard_id}.json"
        payload = _read_json(path, f"D011 shard {shard_id}")
        try:
            d011._validate_shard(payload, ledger, snapshot, platform, task)
        except d011.D011Error as exc:
            raise TransitionOutputError(f"D011 input validation failed for {shard_id}: {exc}") from exc
        shard_digests.append({
            "shard_id": shard_id,
            "file_sha256": _sha256_file(path, f"D011 shard {shard_id}"),
            "content_sha256": payload["content_sha256"],
        })
        records = payload["records"]
        for record in records:
            _require(isinstance(record, dict), "D011 shard record is not an object")
            coordinate = _coordinate_from_key(record["key"])
            for descriptor in _condition_descriptors():
                c_h, c_f, _role = descriptor
                for encoding in ENCODINGS:
                    certification = _certification(record, c_h, c_f, encoding)
                    label = certification.get("set_label")
                    _require(isinstance(label, str), "certification set label is not a string")
                    _validate_label(certification, label, c_h)
                    previous = labels[descriptor][encoding].setdefault(coordinate, label)
                    _require(previous == label, "duplicate D011 coordinate has inconsistent labels")
    expected_coordinates = {(card, sector, budget)
                            for card in range(d011.AXIS_COUNT)
                            for sector in range(d011.AXIS_COUNT)
                            for budget in range(d011.ROW_COUNT)}
    for descriptor in _condition_descriptors():
        for encoding in ENCODINGS:
            _require(set(labels[descriptor][encoding]) == expected_coordinates,
                     "D011 label lattice is incomplete or has foreign coordinates")
    return VerifiedD011Input(directory, coverage, resume, ledger, ledger_manifest,
                             dict(snapshot), dict(platform), tuple(shard_digests), labels)


def _coordinate_object(coordinate: tuple[int, int, int], label: str | None = None) -> dict[str, Any]:
    output: dict[str, Any] = dict(zip(AXES, coordinate, strict=True))
    if label is not None:
        output["set_label"] = label
    return output


def _count_tables(labels: Mapping[tuple[int, int, int], str]) -> dict[str, Any]:
    global_counts = {label: 0 for label in LABELS}
    axis_tables: dict[str, list[dict[str, int]]] = {}
    for label in labels.values():
        global_counts[label] += 1
    for position, axis in enumerate(AXES):
        rows: list[dict[str, int]] = []
        for index in range(d011.AXIS_COUNT):
            row = {"index": index, **{label: 0 for label in LABELS}}
            for coordinate, label in labels.items():
                if coordinate[position] == index:
                    row[label] += 1
            _require(sum(row[label] for label in LABELS) == d011.AXIS_COUNT * d011.AXIS_COUNT,
                     f"count table does not cover a full {axis} slice")
            rows.append(row)
        axis_tables[axis] = rows
    _require(sum(global_counts.values()) == d011.EXPECTED_COORDINATES,
             "global count table does not cover the full lattice")
    return {"global_by_label": global_counts, "by_axis": axis_tables}


def _unequal_face_edges(labels: Mapping[tuple[int, int, int], str]) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    for card in range(d011.AXIS_COUNT):
        for sector in range(d011.AXIS_COUNT):
            for budget in range(d011.ROW_COUNT):
                source = (card, sector, budget)
                for position, axis in enumerate(AXES):
                    if source[position] + 1 >= d011.AXIS_COUNT:
                        continue
                    target = list(source)
                    target[position] += 1
                    neighbour = tuple(target)
                    _require(neighbour in labels, "face neighbour is absent from the label lattice")
                    if labels[source] != labels[neighbour]:
                        edges.append({
                            "axis": axis,
                            "from": _coordinate_object(source, labels[source]),
                            "to": _coordinate_object(neighbour, labels[neighbour]),
                        })
    return edges


def _configuration_output(descriptor: tuple[int, int, str], encoding: str,
                          labels: Mapping[tuple[int, int, int], str]) -> dict[str, Any]:
    c_h, c_f, role = descriptor
    lattice = [_coordinate_object((card, sector, budget), labels[(card, sector, budget)])
               for card in range(d011.AXIS_COUNT)
               for sector in range(d011.AXIS_COUNT)
               for budget in range(d011.ROW_COUNT)]
    return {
        "condition": {"condition_id": _condition_id(c_h, c_f), "c_H": c_h, "c_f": c_f, "role": role},
        "encoding": encoding,
        "label_lattice": lattice,
        "exact_integer_count_tables": _count_tables(labels),
        "face_adjacent_unequal_label_edges": _unequal_face_edges(labels),
    }


def _producer_source_hashes() -> dict[str, str]:
    return {
        "src/g6/d011_transition_output.py": _sha256_file(Path(__file__).resolve(), "transition output source"),
        "research/g6/make_d011_transition_output.py": _sha256_file(
            ROOT / "research/g6/make_d011_transition_output.py", "transition output command"),
    }


def build_transition_output(reviewed_handoff: str,
                            input_dir: Path | str = ROOT / INPUT_REL) -> dict[str, Any]:
    """Build the complete approved representation in memory after input validation."""
    _require(isinstance(reviewed_handoff, str) and reviewed_handoff.strip(),
             "a non-empty independent-review handoff identifier is required")
    verified = load_verified_d011_input(input_dir)
    configurations = [
        _configuration_output(descriptor, encoding, verified.labels[descriptor][encoding])
        for descriptor in _condition_descriptors()
        for encoding in ENCODINGS
    ]
    payload = {
        "schema": SCHEMA,
        "purpose": "Mechanical D011 transition representation only.",
        "approved_output_scope": OUTPUT_SCOPE,
        "owner_authorization": _owner_authorization(),
        "reviewed_handoff": reviewed_handoff,
        "input_artifact": {
            "path": str(verified.input_dir.relative_to(ROOT)),
            "coverage_audit": {
                "file_sha256": _sha256_file(verified.input_dir / "coverage_audit.json", "D011 coverage audit"),
                "content_sha256": verified.coverage["content_sha256"],
            },
            "resume_manifest": {
                "file_sha256": _sha256_file(verified.input_dir / "resume_manifest.json", "D011 resume manifest"),
                "content_sha256": verified.resume["content_sha256"],
            },
            "source_snapshot": verified.source_snapshot,
            "platform": verified.platform,
            "ledger": {
                "file_sha256": _sha256_file(ROOT / d011.PREEXECUTION_REL / "d011_curvature_companion.json",
                                               "D011 preexecution ledger"),
                "content_sha256": verified.ledger["content_sha256"],
            },
            "shard_digest_registry": {
                "algorithm": "sha256",
                "entries": list(verified.shard_digests),
            },
            "shard_count": d011.EXPECTED_SHARDS,
            "coordinate_count": d011.EXPECTED_COORDINATES,
        },
        "grid": {
            "axes": list(AXES),
            "axis_count": d011.AXIS_COUNT,
            "coordinate_count": d011.EXPECTED_COORDINATES,
            "adjacency": "positive unit step along exactly one lattice axis",
        },
        "configurations": configurations,
        "producer_source_sha256": _producer_source_hashes(),
        "scientific_outputs": "mechanical transition representation only",
    }
    payload["content_sha256"] = _sha256_bytes(canonical_bytes(payload))
    return payload


def validate_transition_output(payload: Mapping[str, Any],
                               input_dir: Path | str = ROOT / INPUT_REL,
                               expected_reviewed_handoff: str | None = None) -> None:
    """Replay the complete bounded construction and reject any output drift."""
    _validate_content_hash(payload, "D011 transition output")
    _require(payload.get("schema") == SCHEMA
             and payload.get("purpose") == "Mechanical D011 transition representation only."
             and payload.get("approved_output_scope") == OUTPUT_SCOPE
             and payload.get("owner_authorization") == _owner_authorization()
             and payload.get("scientific_outputs") == "mechanical transition representation only",
             "D011 transition output contract mismatch")
    reviewed = payload.get("reviewed_handoff")
    _require(isinstance(reviewed, str) and reviewed.strip(), "D011 transition output lacks a review handoff")
    if expected_reviewed_handoff is not None:
        _require(isinstance(expected_reviewed_handoff, str) and expected_reviewed_handoff.strip(),
                 "expected review handoff must be a non-empty string")
        _require(reviewed == expected_reviewed_handoff,
                 "D011 transition output review handoff differs from the expected identifier")
    _require(payload.get("producer_source_sha256") == _producer_source_hashes(),
             "D011 transition producer source differs from the emitted producer hashes")
    expected = build_transition_output(reviewed, input_dir)
    _require(canonical_bytes(dict(payload)) == canonical_bytes(expected),
             "D011 transition output differs from its validated input replay")


def build_plan(input_dir: Path | str = ROOT / INPUT_REL) -> dict[str, Any]:
    """Validate the finished D011 input and describe emission without aggregation or writes."""
    verified = load_verified_d011_input(input_dir)
    return {
        "schema": "decisions_os/g6_d011_transition_output_plan/v1",
        "input_artifact": str(verified.input_dir.relative_to(ROOT)),
        "shards": d011.EXPECTED_SHARDS,
        "coordinates": d011.EXPECTED_COORDINATES,
        "configurations": [
            {"condition_id": _condition_id(c_h, c_f), "c_H": c_h, "c_f": c_f, "role": role,
             "encodings": list(ENCODINGS)}
            for c_h, c_f, role in _condition_descriptors()
        ],
        "approved_output_scope": OUTPUT_SCOPE,
        "writes": "none",
        "scientific_outputs": "mechanical transition representation only",
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
            raise TransitionOutputError(f"refusing to overwrite existing transition output: {path}") from exc
        _fsync_directory(path.parent)
    except OSError as exc:
        raise TransitionOutputError(f"transition output publication failed for {path}: {exc}") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


def write_transition_output(output_dir: Path | str, reviewed_handoff: str,
                            input_dir: Path | str = ROOT / INPUT_REL) -> dict[str, Any]:
    """Publish one reviewed transition artifact in a new, dedicated directory."""
    _require(os.environ.get("PYTHONDONTWRITEBYTECODE") == "1", "PYTHONDONTWRITEBYTECODE=1 is required")
    target = Path(output_dir)
    root = (ROOT / "research/g6").resolve()
    resolved = target.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise TransitionOutputError("transition output directory must be under research/g6") from exc
    _require(resolved.parent == root, "transition output directory must be a dedicated direct child of research/g6")
    input_resolved = (ROOT / INPUT_REL).resolve()
    _require(resolved != input_resolved, "transition output may not share the immutable D011 input directory")
    _require(not target.exists(), f"refusing to write into existing output directory: {target}")
    payload = build_transition_output(reviewed_handoff, input_dir)
    validate_transition_output(payload, input_dir, reviewed_handoff)
    created = False
    try:
        target.mkdir(parents=True, exist_ok=False)
        os.chmod(target, 0o755)
        created = True
    except OSError as exc:
        raise TransitionOutputError(f"unable to create transition output directory: {target}: {exc}") from exc
    try:
        output_path = target / OUTPUT_FILENAME
        _write_new(output_path, payload)
        manifest = {
            "schema": MANIFEST_SCHEMA,
            "reviewed_handoff": reviewed_handoff,
            "owner_authorization": _owner_authorization(),
            "producer_source_sha256": payload["producer_source_sha256"],
            "input_artifact": payload["input_artifact"],
            "output": {
                "path": OUTPUT_FILENAME,
                "file_sha256": _sha256_file(output_path, "D011 transition output"),
                "content_sha256": payload["content_sha256"],
            },
            "scientific_outputs": "mechanical transition representation only",
        }
        manifest["content_sha256"] = _sha256_bytes(canonical_bytes(manifest))
        _write_new(target / MANIFEST_FILENAME, manifest)
        return {"output_dir": str(target), "output_file": str(output_path),
                "output_content_sha256": payload["content_sha256"],
                "scientific_outputs": "mechanical transition representation only"}
    except Exception:
        # The directory was created by this call and may only hold our two
        # fixed names.  Clean them individually so a failed second publish
        # does not leave an apparently valid-but-incomplete artifact behind.
        if created:
            for name in (MANIFEST_FILENAME, OUTPUT_FILENAME):
                try:
                    (target / name).unlink()
                except FileNotFoundError:
                    pass
            try:
                target.rmdir()
                _fsync_directory(target.parent)
            except OSError:
                pass
        raise


def validate_published_transition_output(output_dir: Path | str,
                                         input_dir: Path | str = ROOT / INPUT_REL,
                                         expected_reviewed_handoff: str | None = None) -> None:
    """Validate one published output and replay it against the immutable D011 input."""
    directory = Path(output_dir)
    _require(directory.is_dir() and not directory.is_symlink(), "transition output directory is unavailable or a symlink")
    _require({path.name for path in directory.iterdir()} == {OUTPUT_FILENAME, MANIFEST_FILENAME},
             "transition output directory membership mismatch")
    output = _read_json(directory / OUTPUT_FILENAME, "D011 transition output")
    manifest = _read_json(directory / MANIFEST_FILENAME, "D011 transition manifest")
    _validate_content_hash(manifest, "D011 transition manifest")
    _require(manifest.get("schema") == MANIFEST_SCHEMA
             and manifest.get("owner_authorization") == _owner_authorization()
             and manifest.get("producer_source_sha256") == output.get("producer_source_sha256")
             and manifest.get("input_artifact") == output.get("input_artifact")
             and manifest.get("scientific_outputs") == "mechanical transition representation only",
             "D011 transition manifest contract mismatch")
    entry = manifest.get("output")
    _require(isinstance(entry, dict) and entry.get("path") == OUTPUT_FILENAME
             and entry.get("file_sha256") == _sha256_file(directory / OUTPUT_FILENAME, "D011 transition output")
             and entry.get("content_sha256") == output.get("content_sha256"),
             "D011 transition manifest output identity mismatch")
    manifest_reviewed = manifest.get("reviewed_handoff")
    _require(isinstance(manifest_reviewed, str) and manifest_reviewed.strip(),
             "D011 transition manifest lacks a review handoff")
    if expected_reviewed_handoff is not None:
        _require(manifest_reviewed == expected_reviewed_handoff,
                 "D011 transition manifest review handoff differs from the expected identifier")
    _require(output.get("reviewed_handoff") == manifest_reviewed,
             "D011 transition output and manifest review handoffs differ")
    validate_transition_output(output, input_dir, expected_reviewed_handoff)

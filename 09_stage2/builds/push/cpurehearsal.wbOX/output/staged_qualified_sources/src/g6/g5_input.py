"""Strict read-only validation of the accepted Gate-5 corpus.

This module deliberately does not import ``src.g5.core_pass``.  Its runner has
resume and quarantine behaviour that is appropriate for producing Gate-5
output but must never be reachable from a Gate-6 input path.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
from types import MappingProxyType
from typing import Any, Iterator, Mapping


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CORPUS_DIR = ROOT / "research/g5/core_pass_output"

G5_SCHEMA = "decisions_os/g5_csb_core_pass/v1"
ROW_COUNT = 61
R_VALUES = (0.5, 1.0, 2.0)
EXPECTED_SHARD_COUNT = 11_163
EXPECTED_COORDINATE_COUNT = 680_943

# These are the immutable, accepted G5 artifact identities rather than values
# recomputed from the present working tree.  G5's source files were snapshot
# pinned at production time and must not be treated as mutable G6 inputs.
ACCEPTED_COVERAGE_SHA256 = "fdef0caf588a575eb7c53b6bb72c6f42eac4c8e90915f4489af1f73c0a941194"
ACCEPTED_MANIFEST_SHA256 = "14b658451f4e144e79819393dec5ca9db6479013dfd93d0a0b58c0efe9cacecc"
ACCEPTED_DECISIONS_SHA256 = "274c6cd92d4958957d125efc7ae2ddb6f40629eb78b7c2e2be99224e038ce849"
ACCEPTED_LAMBDA_REF_HEX = "0x1.2b93cd4cbc969p-7"
PLATFORM_EQUIVALENCE_REPORT_REL = "research/g5/platform_equivalence_audit_v1/report.json"
PLATFORM_EQUIVALENCE_REPORT_SHA256 = "958fa5eb87df2f04d6da1f63735a623201c94a1900b12d8f39af6d27ed5f7bca"
PLATFORM_EQUIVALENCE_CONTENT_SHA256 = "4039b69e179dd72d393886e779e770b9a9fb7ca5cd2183b9978654bc57105603"
G4_PRIMARY_LEDGER_REL = "research/g4/G4_PRIMARY_LEDGER.json"
GATE_5_OWNER_RECORD_REL = "research/decisions/GATE_5_OWNER_EXCEPTION_AND_EXIT.md"
GATE_5_OWNER_RECORD_SHA256 = "061004477a1e71e76664878fc5b46eb281f7e55fea470fbf4828a477efb23d9c"

BASELINE_PYTHON = "3.12.3 (main, Jun 19 2026, 12:46:00) [GCC 13.3.0]"
MINORITY_PYTHON = "3.12.3 (main, Jul 15 2026, 23:46:41) [GCC 13.3.0]"
EXPECTED_BASELINE_SHARDS = 10_420
EXPECTED_MINORITY_SHARDS = 743
EXPECTED_DOMAIN = {
    "slack_logical_sha256": "d052e67892d0e39882db26798f881628480d83c0119ee3a1e2ba9b1cdcf03063",
    "slack_states": 1_048_576,
    "unbalanced_states": 1_048_576,
}
COEFFICIENT_FIELDS = frozenset({
    "alpha", "sector_slack", "budget_slack", "sector_linear", "sector_quadratic", "budget_linear",
    "budget_quadratic",
})
EPSILON_HEX = math.ldexp(1.0, -52).hex()


class G5InputError(RuntimeError):
    """Raised when the accepted Gate-5 input boundary does not validate."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise G5InputError(message)


def canonical_bytes(payload: Mapping[str, Any]) -> bytes:
    """Return the canonical byte representation used by the G5 artifacts."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _validate_content_hash(payload: Mapping[str, Any], artifact: str) -> None:
    body = dict(payload)
    digest = body.pop("content_sha256", None)
    _require(isinstance(digest, str), f"{artifact}: missing content_sha256")
    actual = hashlib.sha256(canonical_bytes(body)).hexdigest()
    _require(actual == digest, f"{artifact}: canonical content_sha256 mismatch")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise G5InputError(f"{path.name}: unreadable JSON") from exc
    _require(isinstance(payload, dict), f"{path.name}: top-level JSON must be an object")
    return payload


def _shard_id(r: float, card: int, sector: int) -> str:
    return f"r={r.hex()}__card={card:02d}__sector={sector:02d}"


def _expected_shards() -> tuple[str, ...]:
    return tuple(
        _shard_id(r, card, sector)
        for r in R_VALUES
        for card in range(ROW_COUNT)
        for sector in range(ROW_COUNT)
    )


EXPECTED_SHARDS = _expected_shards()
EXPECTED_SHARD_SET = frozenset(EXPECTED_SHARDS)


def _is_minority_shard(shard_id: str) -> bool:
    """Return whether a task belongs to the narrowly accepted 743-shard split."""
    prefix = "r=0x1.0000000000000p+1__card="
    if not shard_id.startswith(prefix):
        return False
    try:
        card_text, sector_text = shard_id.removeprefix(prefix).split("__sector=", 1)
        card, sector = int(card_text), int(sector_text)
    except ValueError as exc:
        raise G5InputError(f"malformed expected shard id: {shard_id}") from exc
    return card > 48 or (card == 48 and sector >= 50)


EXPECTED_MINORITY_SHARD_SET = frozenset(shard for shard in EXPECTED_SHARDS if _is_minority_shard(shard))
_require(len(EXPECTED_MINORITY_SHARD_SET) == EXPECTED_MINORITY_SHARDS, "internal minority-scope count error")


@dataclass(frozen=True)
class AcceptedG5Summary:
    """Verified structural facts about the immutable accepted corpus."""

    corpus_dir: Path
    source_snapshot: Mapping[str, str]
    baseline_platform: Mapping[str, Any]
    minority_platform: Mapping[str, Any]
    minority_projection_sha256: Mapping[str, str]
    primary_r1_coefficients: "PrimaryR1Coefficients"
    platform_counts: Mapping[str, int]
    shard_count: int
    coordinate_count: int


def _finite_hex(value: Any, label: str, *, positive: bool = False) -> float:
    _require(isinstance(value, str), f"{label}: missing hexadecimal binary64 value")
    try:
        parsed = float.fromhex(value)
    except ValueError as exc:
        raise G5InputError(f"{label}: invalid hexadecimal binary64 value") from exc
    _require(math.isfinite(parsed) and (not positive or parsed > 0.0),
             f"{label}: nonfinite or nonpositive binary64 value")
    return parsed


def _bits(value: Any, label: str, width: int) -> tuple[int, ...]:
    _require(isinstance(value, list) and len(value) == width
             and all(type(bit) is int and bit in (0, 1) for bit in value),
             f"{label}: expected {width} binary integer bits")
    return tuple(value)


def _ticker_list(value: Any, label: str) -> None:
    _require(isinstance(value, list) and all(isinstance(ticker, str) for ticker in value),
             f"{label}: malformed selected-ticker list")


def _d016_set_label(atomic_labels: set[str]) -> str:
    _require(atomic_labels and atomic_labels <= {"A", "B", "C"}, "invalid decoded atomic-label set")
    if "C" in atomic_labels:
        return "C"
    if atomic_labels == {"A"}:
        return "A"
    return "B"


@dataclass(frozen=True)
class PrimaryR1Coefficients:
    """The accepted G4 r=1 coefficient ledger, indexed by its three axes."""

    cardinality: tuple[Mapping[str, str | int], ...]
    sector: tuple[Mapping[str, str | int], ...]
    budget: tuple[Mapping[str, str | int], ...]


def _validate_g4_coefficient_rows(value: Any, family: str, fields: set[str]) -> tuple[Mapping[str, str | int], ...]:
    _require(isinstance(value, list) and len(value) == ROW_COUNT,
             f"G4 ledger: malformed {family} coefficient family")
    rows: list[Mapping[str, str | int]] = []
    for index, row in enumerate(value):
        _require(isinstance(row, dict) and set(row) == fields and row.get("index") == index,
                 f"G4 ledger: malformed {family} coefficient row {index}")
        for key, item in row.items():
            if key != "index":
                _finite_hex(item, f"G4 ledger: {family}.{key} at row {index}", positive=True)
        rows.append(MappingProxyType(dict(row)))
    return tuple(rows)


def _load_primary_r1_coefficients(snapshot: Mapping[str, str]) -> PrimaryR1Coefficients:
    """Load the snapshot-pinned G4 r=1 coefficient ledger for a cheap replay."""
    expected_file_hash = snapshot.get(G4_PRIMARY_LEDGER_REL)
    _require(isinstance(expected_file_hash, str), "accepted source snapshot lacks the G4 primary ledger")
    path = ROOT / G4_PRIMARY_LEDGER_REL
    try:
        actual_file_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise G5InputError("G4 primary ledger is unreadable") from exc
    _require(actual_file_hash == expected_file_hash, "G4 primary ledger differs from the accepted source snapshot")
    ledger = _read_json(path)
    _validate_content_hash(ledger, "G4 primary ledger")
    _require(ledger.get("schema") == "g4-primary-coordinate-coefficient-ledger/v1"
             and ledger.get("grid_rule") == {"q_min": -4, "q_max": 2, "P": 10, "N_axis": 61},
             "G4 primary ledger schema or grid rule mismatch")
    coefficients = ledger.get("coefficient_ledger")
    _require(isinstance(coefficients, dict) and set(coefficients) == {"cardinality", "sector", "budget"},
             "G4 primary ledger coefficient map mismatch")
    return PrimaryR1Coefficients(
        cardinality=_validate_g4_coefficient_rows(coefficients["cardinality"], "cardinality", {"index", "alpha_hex"}),
        sector=_validate_g4_coefficient_rows(
            coefficients["sector"], "sector", {"index", "a_r_hex", "lambda_slack_hex", "lambda_1_hex", "lambda_2_hex"}
        ),
        budget=_validate_g4_coefficient_rows(
            coefficients["budget"], "budget", {"index", "a_r_hex", "lambda_slack_hex", "lambda_1_hex", "lambda_2_hex"}
        ),
    )


def _validate_primary_r1_coefficients(record: Mapping[str, Any], key: Mapping[str, Any], shard_name: str,
                                      index: int, primary: PrimaryR1Coefficients) -> None:
    """Replay the G5 r=1 coefficient interface against the accepted G4 ledger."""
    if key["r_hex"] != float(1.0).hex():
        return
    card, sector, budget = key["ell_card"], key["ell_sector"], key["ell_budget"]
    _require(all(type(value) is int and 0 <= value < ROW_COUNT for value in (card, sector, budget)),
             f"{shard_name}: r=1 key axes are malformed at budget {index}")
    expected = {
        "alpha": primary.cardinality[card]["alpha_hex"],
        "sector_slack": primary.sector[sector]["lambda_slack_hex"],
        "sector_linear": primary.sector[sector]["lambda_1_hex"],
        "sector_quadratic": primary.sector[sector]["lambda_2_hex"],
        "budget_slack": primary.budget[budget]["lambda_slack_hex"],
        "budget_linear": primary.budget[budget]["lambda_1_hex"],
        "budget_quadratic": primary.budget[budget]["lambda_2_hex"],
    }
    _require(record.get("coefficients_hex") == expected,
             f"{shard_name}: r=1 coefficients differ from the accepted G4 ledger at budget {index}")


def _validate_tie_lists(certification: Mapping[str, Any], encoding: str, shard_name: str, index: int) -> None:
    raw_ties, decoded = certification.get("T_E"), certification.get("X_E")
    _require(isinstance(raw_ties, list) and isinstance(decoded, list),
             f"{shard_name}: malformed {encoding} tie lists at budget {index}")
    _require(certification.get("T_E_size") == len(raw_ties) and certification.get("X_E_size") == len(decoded)
             and raw_ties and decoded, f"{shard_name}: inconsistent {encoding} tie cardinalities at budget {index}")

    raw_decoded: set[tuple[int, ...]] = set()
    raw_states: set[tuple[tuple[int, ...], tuple[int, ...] | None]] = set()
    for raw_index, raw in enumerate(raw_ties):
        _require(isinstance(raw, dict), f"{shard_name}: malformed {encoding} raw tie {raw_index}")
        _ticker_list(raw.get("selected_tickers"), f"{shard_name}: {encoding} raw tie {raw_index}")
        raw_bits = _bits(raw.get("x_bits"), f"{shard_name}: {encoding} raw tie {raw_index}", 20)
        raw_decoded.add(raw_bits)
        if encoding == "slack":
            auxiliary_bits: tuple[int, ...] | None = _bits(
                raw.get("auxiliary_bits"), f"{shard_name}: slack raw tie {raw_index}", 19
            )
        else:
            _require("auxiliary_bits" not in raw, f"{shard_name}: unbalanced raw tie has auxiliary bits")
            auxiliary_bits = None
        raw_state = (raw_bits, auxiliary_bits)
        _require(raw_state not in raw_states, f"{shard_name}: duplicate {encoding} raw tie")
        raw_states.add(raw_state)

    decoded_bits: set[tuple[int, ...]] = set()
    atomic_labels: set[str] = set()
    for decoded_index, item in enumerate(decoded):
        _require(isinstance(item, dict), f"{shard_name}: malformed {encoding} decoded tie {decoded_index}")
        bits = _bits(item.get("x_bits"), f"{shard_name}: {encoding} decoded tie {decoded_index}", 20)
        _require(bits not in decoded_bits, f"{shard_name}: duplicate {encoding} decoded tie")
        decoded_bits.add(bits)
        _ticker_list(item.get("selected_tickers"), f"{shard_name}: {encoding} decoded tie {decoded_index}")
        _finite_hex(item.get("objective_hex"), f"{shard_name}: {encoding} decoded objective {decoded_index}")
        _require(type(item.get("hard_feasible")) is bool, f"{shard_name}: non-boolean hard-feasibility")
        atomic = item.get("atomic_label")
        _require(atomic in {"A", "B", "C"}, f"{shard_name}: invalid decoded atomic label")
        _require(item["hard_feasible"] == (atomic != "C"),
                 f"{shard_name}: decoded hard-feasibility/atomic-label inconsistency")
        atomic_labels.add(atomic)

    _require(raw_decoded == decoded_bits, f"{shard_name}: {encoding} raw/decode tie mismatch")
    _require(certification.get("set_label") == _d016_set_label(atomic_labels),
             f"{shard_name}: {encoding} stored D016 set-label drift")


def _validate_record(record: Any, expected_key: dict[str, Any], shard_name: str, index: int,
                     primary_r1: PrimaryR1Coefficients) -> None:
    _require(isinstance(record, dict), f"{shard_name}: record {index} must be an object")
    _require(record.get("key") == expected_key, f"{shard_name}: record/key alignment mismatch at budget {index}")
    coefficients = record.get("coefficients_hex")
    _require(isinstance(coefficients, dict) and set(coefficients) == COEFFICIENT_FIELDS,
             f"{shard_name}: malformed coefficient hex map at budget {index}")
    for name, value in coefficients.items():
        _finite_hex(value, f"{shard_name}: coefficient {name} at budget {index}", positive=True)
    _validate_primary_r1_coefficients(record, expected_key, shard_name, index, primary_r1)

    for encoding in ("unbalanced", "slack"):
        certification = record.get(encoding)
        _require(isinstance(certification, dict), f"{shard_name}: missing {encoding} record at budget {index}")
        _require(certification.get("set_label") in {"A", "B", "C"},
                 f"{shard_name}: invalid {encoding} set label at budget {index}")
        h_min = _finite_hex(certification.get("H_E_min_hex"),
                            f"{shard_name}: {encoding} minimum energy at budget {index}")
        _validate_tie_lists(certification, encoding, shard_name, index)
        comparator = certification.get("tie_comparator")
        _require(isinstance(comparator, dict) and set(comparator) == {"c_H", "epsilon_hex", "minimum_tau_hex"}
                 and comparator.get("c_H") == 2048 and comparator.get("epsilon_hex") == EPSILON_HEX,
                 f"{shard_name}: non-primary tie comparator at budget {index}")
        lambda_ref = float.fromhex(ACCEPTED_LAMBDA_REF_HEX)
        expected_tau = float((2048.0 * math.ldexp(1.0, -52)) * float(lambda_ref + abs(h_min)))
        _require(comparator.get("minimum_tau_hex") == expected_tau.hex(),
                 f"{shard_name}: {encoding} minimum tie tolerance drift at budget {index}")


def _validate_platform(platform: Any, shard_id: str) -> str:
    _require(isinstance(platform, dict), f"{shard_id}: missing platform fingerprint")
    python_build = platform.get("python")
    expected_build = MINORITY_PYTHON if shard_id in EXPECTED_MINORITY_SHARD_SET else BASELINE_PYTHON
    _require(python_build == expected_build, f"{shard_id}: platform is outside the accepted exception scope")
    return "minority" if python_build == MINORITY_PYTHON else "baseline"


def _stored_projection_sha256(payload: Mapping[str, Any]) -> str:
    """Reproduce Phase-B's stored projection without importing its writer."""
    projection = dict(payload)
    projection.pop("content_sha256", None)
    provenance = projection.get("provenance")
    _require(isinstance(provenance, dict), "shard lacks provenance for Phase-B projection")
    projection["provenance"] = {key: value for key, value in provenance.items() if key != "worker_pid"}
    return hashlib.sha256(canonical_bytes(projection)).hexdigest()


def _validate_platform_equivalence_evidence() -> Mapping[str, str]:
    """Anchor the exact owner-exception shard set to the Phase-B evidence."""
    path = ROOT / PLATFORM_EQUIVALENCE_REPORT_REL
    _require(path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == PLATFORM_EQUIVALENCE_REPORT_SHA256,
             "platform-equivalence evidence file hash mismatch")
    report = _read_json(path)
    _validate_content_hash(report, "platform-equivalence report")
    _require(report.get("content_sha256") == PLATFORM_EQUIVALENCE_CONTENT_SHA256
             and report.get("schema") == "decisions_os/g5_platform_equivalence_audit/v1/report"
             and report.get("target_shard_count") == EXPECTED_MINORITY_SHARDS
             and report.get("coordinate_count") == EXPECTED_MINORITY_SHARDS * ROW_COUNT,
             "platform-equivalence evidence scope mismatch")
    mismatches = report.get("mismatches")
    _require(isinstance(mismatches, dict) and set(mismatches) == EXPECTED_MINORITY_SHARD_SET,
             "platform-equivalence evidence shard set mismatch")
    stored_projections: dict[str, str] = {}
    for shard_id, detail in mismatches.items():
        _require(isinstance(detail, dict) and detail.get("shard_id") == shard_id
                 and detail.get("ok") is False and detail.get("mismatch_sections") == ["provenance"]
                 and isinstance(detail.get("stored_projection_sha256"), str)
                 and isinstance(detail.get("fresh_projection_sha256"), str),
                 "platform-equivalence evidence mismatch boundary violated")
        stored_projections[shard_id] = detail["stored_projection_sha256"]
    return MappingProxyType(stored_projections)


def _validate_shard(payload: Mapping[str, Any], path: Path, snapshot: Mapping[str, str],
                    minority_projection_sha256: Mapping[str, str],
                    primary_r1: PrimaryR1Coefficients) -> tuple[str, dict[str, Any]]:
    _validate_content_hash(payload, path.name)
    shard_id = payload.get("shard_id")
    _require(isinstance(shard_id, str) and path.stem == shard_id and shard_id in EXPECTED_SHARD_SET,
             f"{path.name}: filename/shard-id mismatch")
    _require(payload.get("schema") == G5_SCHEMA, f"{path.name}: unexpected shard schema")
    provenance = payload.get("provenance")
    _require(isinstance(provenance, dict) and provenance.get("source_snapshot") == snapshot,
             f"{path.name}: source snapshot mismatch")
    _require(provenance.get("domain") == EXPECTED_DOMAIN, f"{path.name}: domain provenance mismatch")
    worker_gate = provenance.get("worker_self_test")
    _require(isinstance(worker_gate, list) and len(worker_gate) == 2
             and [item.get("optimized") for item in worker_gate if isinstance(item, dict)] == [False, True]
             and all(isinstance(item, dict) and item.get("exit_code") == 0 for item in worker_gate),
             f"{path.name}: worker self-test attestation mismatch")
    kind = _validate_platform(provenance.get("platform"), shard_id)
    if kind == "minority":
        _require(_stored_projection_sha256(payload) == minority_projection_sha256.get(shard_id),
                 f"{path.name}: Phase-B stored-projection mismatch")
    platform = dict(provenance["platform"])

    keys, records = payload.get("keys"), payload.get("records")
    _require(isinstance(keys, list) and isinstance(records, list)
             and len(keys) == ROW_COUNT and len(records) == ROW_COUNT,
             f"{path.name}: malformed budget-line length")
    head = shard_id.split("__")
    r_hex, card, sector = head[0].removeprefix("r="), int(head[1].removeprefix("card=")), int(head[2].removeprefix("sector="))
    for budget, (key, record) in enumerate(zip(keys, records, strict=True)):
        expected_key = {"r_hex": r_hex, "ell_card": card, "ell_sector": sector, "ell_budget": budget}
        _require(key == expected_key, f"{path.name}: malformed budget-line key {budget}")
        _validate_record(record, expected_key, path.name, budget, primary_r1)
    return kind, platform


def verify_accepted_g5_corpus(corpus_dir: Path | str = DEFAULT_CORPUS_DIR) -> AcceptedG5Summary:
    """Validate the full accepted corpus without modifying it or aggregating labels.

    The accepted G5 platform exception is checked against its exact 743-shard
    scope.  No current-source hash is recomputed: artifact validation uses the
    accepted coverage audit as the immutable source-snapshot anchor.
    """
    directory = Path(corpus_dir)
    _require(directory.is_dir(), f"missing G5 corpus directory: {directory}")
    owner_record = ROOT / GATE_5_OWNER_RECORD_REL
    try:
        owner_record_hash = hashlib.sha256(owner_record.read_bytes()).hexdigest()
    except OSError as exc:
        raise G5InputError("Gate-5 owner exit record is unreadable") from exc
    _require(owner_record_hash == GATE_5_OWNER_RECORD_SHA256,
             "Gate-5 owner exit record differs from the accepted exception authority")
    minority_projection_sha256 = _validate_platform_equivalence_evidence()

    coverage = _read_json(directory / "coverage_audit.json")
    _validate_content_hash(coverage, "coverage_audit.json")
    _require(coverage.get("content_sha256") == ACCEPTED_COVERAGE_SHA256,
             "coverage_audit.json is not the accepted Gate-5 audit")
    _require(coverage.get("schema") == G5_SCHEMA + "/coverage-audit", "unexpected coverage-audit schema")
    _require(coverage.get("shard_count") == EXPECTED_SHARD_COUNT
             and coverage.get("coordinate_count") == EXPECTED_COORDINATE_COUNT,
             "coverage-audit population mismatch")
    _require(coverage.get("scientific_outputs") == "intentionally absent",
             "coverage-audit scientific-output boundary violated")
    snapshot = coverage.get("source_snapshot")
    _require(isinstance(snapshot, dict) and snapshot.get("research/decisions/DECISIONS.md") == ACCEPTED_DECISIONS_SHA256,
             "coverage-audit source snapshot is not accepted")
    primary_r1 = _load_primary_r1_coefficients(snapshot)

    manifest = _read_json(directory / "resume_manifest.json")
    _validate_content_hash(manifest, "resume_manifest.json")
    _require(manifest.get("content_sha256") == ACCEPTED_MANIFEST_SHA256,
             "resume_manifest.json is not the accepted Gate-5 manifest")
    _require(manifest.get("schema") == G5_SCHEMA + "/resume-manifest", "unexpected resume-manifest schema")
    _require(manifest.get("source_snapshot") == snapshot, "resume-manifest source snapshot mismatch")
    _require(manifest.get("expected_shards") == EXPECTED_SHARD_COUNT and manifest.get("stopped_for_budget") is False,
             "resume-manifest completion state mismatch")
    completed = manifest.get("completed_shards")
    _require(isinstance(completed, list) and len(completed) == EXPECTED_SHARD_COUNT
             and len(set(completed)) == EXPECTED_SHARD_COUNT and set(completed) == EXPECTED_SHARD_SET,
             "resume-manifest completed-shard coverage mismatch")

    expected_names = {f"{shard_id}.json" for shard_id in EXPECTED_SHARDS}
    _require(set(os.listdir(directory)) == expected_names | {"coverage_audit.json", "resume_manifest.json"},
             "G5 corpus directory contains unexpected or missing entries")
    paths = tuple(sorted(directory.glob("r=*.json")))
    _require(len(paths) == EXPECTED_SHARD_COUNT and {path.stem for path in paths} == EXPECTED_SHARD_SET,
             "G5 shard filesystem coverage mismatch")

    platform_by_kind: dict[str, dict[str, Any]] = {}
    platform_counts = {"baseline": 0, "minority": 0}
    for path in paths:
        payload = _read_json(path)
        kind, platform = _validate_shard(payload, path, snapshot, minority_projection_sha256, primary_r1)
        previous = platform_by_kind.setdefault(kind, platform)
        _require(previous == platform, f"{path.name}: inconsistent {kind} platform fingerprint")
        platform_counts[kind] += 1

    _require(platform_counts == {"baseline": EXPECTED_BASELINE_SHARDS, "minority": EXPECTED_MINORITY_SHARDS},
             "accepted platform-split population mismatch")
    _require(set(platform_by_kind) == {"baseline", "minority"}, "accepted platform variants missing")
    baseline_other = {key: value for key, value in platform_by_kind["baseline"].items() if key != "python"}
    minority_other = {key: value for key, value in platform_by_kind["minority"].items() if key != "python"}
    _require(baseline_other == minority_other, "owner-exception platforms differ outside the Python-build field")
    return AcceptedG5Summary(
        corpus_dir=directory,
        source_snapshot=MappingProxyType(dict(snapshot)),
        baseline_platform=MappingProxyType(platform_by_kind["baseline"]),
        minority_platform=MappingProxyType(platform_by_kind["minority"]),
        minority_projection_sha256=minority_projection_sha256,
        primary_r1_coefficients=primary_r1,
        platform_counts=MappingProxyType(dict(platform_counts)),
        shard_count=EXPECTED_SHARD_COUNT,
        coordinate_count=EXPECTED_COORDINATE_COUNT,
    )


def iter_validated_records(corpus_dir: Path | str = DEFAULT_CORPUS_DIR) -> Iterator[dict[str, Any]]:
    """Yield records only after a full structural validation has succeeded.

    This intentionally performs a second read.  Consumers cannot obtain a
    partially trusted stream while a malformed corpus remains undetected.
    """
    directory = Path(corpus_dir)
    summary = verify_accepted_g5_corpus(directory)
    for shard_id in EXPECTED_SHARDS:
        path = directory / f"{shard_id}.json"
        payload = _read_json(path)
        kind, platform = _validate_shard(
            payload, path, summary.source_snapshot, summary.minority_projection_sha256, summary.primary_r1_coefficients
        )
        expected_platform = summary.minority_platform if kind == "minority" else summary.baseline_platform
        _require(platform == expected_platform, f"{path.name}: platform changed after initial validation")
        for record in payload["records"]:
            yield record

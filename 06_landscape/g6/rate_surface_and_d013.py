"""Streaming Gate-6 exact aggregate producer and mechanical D013 disposition; no inference logic.

Inputs and bindings:
* Gate-5: only the owner-ratified boundary ``src.g6.ratified_g5_input.iter_ratified_records`` (registry
  digests, hash-before-decode, structural validation); every record's primary ``(c_H, c_f) = (2048, 2048)``
  set label and decoded census are re-derived here; exact key-set coverage with duplicate rejection.
* V-14: the two accepted core plans are pinned by content SHA-256 (0.5x and 2x, never swapped or reused);
  the sealed artifact set is audited by the reviewed legacy-descriptor audit, the artifact root must contain
  exactly the plan's batch directories (no extra, missing, symlinked, or mixed members), and every consumed
  ``records.json`` byte stream is hash-bound to the audit receipt and semantically re-validated record by
  record from those same bytes before aggregation (no unchecked second read).
* Authorities: ``DECISIONS.md`` and ``FROZEN_MATH_SPEC.md`` are pinned by SHA-256 and fail closed on drift.

Arithmetic is exact (integers and ``fractions.Fraction``); no float or bool appears in any output.  D013
consumes exactly the six Gate-5 primary cells ``r in {0.5, 1, 2} x {unbalanced, slack}``; V-14 series,
D015 diagnostics, atomic fractions, D011, and GPU timing never enter the disposition.  This module writes
nothing; the caller decides whether a reviewed artifact may be written.
"""
from __future__ import annotations

from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any, Callable, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.g6.cuda_qualification import cuda_v14_core_batch as core  # noqa: E402
from research.g6.cuda_qualification import v14_core_batch_contract as contract  # noqa: E402
from research.g6.cuda_qualification import v14_core_legacy_linear_order_audit as v14_audit  # noqa: E402
from src.g6 import ratified_g5_input  # noqa: E402

SCHEMA = "decisions_os/g6_rate_surface_and_d013/v1"
ENCODINGS = ("unbalanced", "slack")
R_HEX = tuple(value.hex() for value in (0.5, 1.0, 2.0))
PRIMARY_PAIR = (2048, 2048)
CONDITIONS = (PRIMARY_PAIR, (1024, 2048), (4096, 2048), (2048, 1024), (2048, 4096))
GATE5_SOURCE = "gate5_csb_primary"
GATE5_AXIS = 61
GATE5_SLICE = GATE5_AXIS ** 3
D013_CELLS = frozenset((r, e) for r in R_HEX for e in ENCODINGS)
# Accepted V-14 core plans (content SHA-256), one per scale; nothing else is aggregated.
ACCEPTED_V14_PLANS = {
    "0.5x": "e5b44620206e5bbaca3a03e890a4f99b4f29a23b87d3e2d4f8f8be2c3067d71d",
    "2x": "38c01eff5a313273fc106a5f5c39760628e59132b9a7a72e0176b37aa1897748",
}
# Governing authorities, pinned; any drift fails closed before any aggregation.
AUTHORITIES = {
    "research/decisions/DECISIONS.md": "274c6cd92d4958957d125efc7ae2ddb6f40629eb78b7c2e2be99224e038ce849",
    "research/00_specifications/FROZEN_MATH_SPEC.md": "e963a7e10ba797a373ef50d585bec1056ee82f7274d762b7c8bab9a817062900",
}
SERIES_KEYS = frozenset({"source", "r_hex", "encoding", "coordinate_count", "set_label_counts", "rho_E_exact",
                         "I_C_exist_count", "I_C_univ_count", "mean_p"})


class RateSurfaceError(RuntimeError):
    """Raised whenever an input, binding, or aggregate fails closed."""


def _require(ok: bool, msg: str) -> None:
    if not ok:
        raise RateSurfaceError(msg)


def _int(v: object) -> bool:
    return type(v) is int


def canonical_bytes(v: Mapping[str, Any]) -> bytes:
    return json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _fraction(v: Fraction) -> dict[str, int]:
    return {"numerator": v.numerator, "denominator": v.denominator}


def _sha(relative: str) -> str:
    try:
        return _sha256((ROOT / relative).read_bytes())
    except OSError as exc:
        raise RateSurfaceError(f"required provenance input unreadable: {relative}") from exc


def bind_authorities() -> dict[str, str]:
    """Fail closed unless the governing decision and specification records are byte-identical to the pins."""
    observed = {relative: _sha(relative) for relative in AUTHORITIES}
    drifted = sorted(relative for relative, digest in observed.items() if digest != AUTHORITIES[relative])
    _require(not drifted, "authority drift: " + ", ".join(drifted))
    return observed


# --------------------------------------------------------------------------
# Exact per-cell accumulation
# --------------------------------------------------------------------------

def _new() -> dict[str, Any]:
    return {"coordinates": 0, "labels": {x: 0 for x in "ABC"}, "i_c_exist": 0, "i_c_univ": 0,
            "p": {x: Fraction(0) for x in "ABC"}}


def _add(bucket: dict[str, Any], summary: Mapping[str, Any]) -> None:
    label = summary.get("set_label")
    _require(label in ("A", "B", "C"), "invalid D016 set label")
    counts, n = summary.get("atomic_counts"), summary.get("X_E_size")
    _require(isinstance(counts, dict) and _int(n) and n > 0 and set(counts) == set("ABC"), "invalid D016 summary")
    _require(all(_int(counts[x]) and counts[x] >= 0 for x in "ABC") and sum(counts.values()) == n, "atomic census drift")
    _require(label == ("C" if counts["C"] else ("A" if counts["A"] == n else "B")), "D016 label/census drift")
    bucket["coordinates"] += 1
    bucket["labels"][label] += 1
    bucket["i_c_exist"] += int(counts["C"] > 0)
    bucket["i_c_univ"] += int(counts["C"] == n)
    for x in "ABC":
        bucket["p"][x] += Fraction(counts[x], n)


def _render(bucket: Mapping[str, Any]) -> dict[str, Any]:
    n, labels = bucket["coordinates"], bucket["labels"]
    _require(_int(n) and n > 0 and sum(labels.values()) == n, "aggregate label census drift")
    return {"coordinate_count": n, "set_label_counts": dict(labels),
            "rho_E_exact": {"numerator": labels["A"], "denominator": n},
            "I_C_exist_count": bucket["i_c_exist"], "I_C_univ_count": bucket["i_c_univ"],
            "mean_p": {x: _fraction(bucket["p"][x] / n) for x in "ABC"}}


# --------------------------------------------------------------------------
# Gate-5 primary series
# --------------------------------------------------------------------------

def _gate5_summary(cert: object) -> dict[str, Any]:
    comparator = cert.get("tie_comparator") if isinstance(cert, dict) else None
    _require(isinstance(cert, dict) and isinstance(comparator, dict) and comparator.get("c_H") == 2048,
             "Gate-5 primary comparator is absent or non-primary")
    xs = cert.get("X_E")
    _require(isinstance(xs, list) and xs and cert.get("X_E_size") == len(xs), "invalid Gate-5 decoded set")
    labels = []
    for item in xs:
        _require(isinstance(item, dict) and item.get("atomic_label") in ("A", "B", "C"), "invalid Gate-5 decoded atomic label")
        labels.append(item["atomic_label"])
    counts = {x: labels.count(x) for x in "ABC"}
    expected = "C" if counts["C"] else ("A" if counts["A"] == len(xs) else "B")
    _require(cert.get("set_label") == expected, "Gate-5 D016 label/census drift")
    return {"set_label": expected, "atomic_counts": counts, "X_E_size": len(xs)}


def aggregate_gate5(records: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Exact per-(r, encoding) primary series over the full 3 x 61^3 Gate-5 key set, duplicates refused."""
    buckets = {(r, e): _new() for r in R_HEX for e in ENCODINGS}
    expected = {(card, sector, budget) for card in range(GATE5_AXIS) for sector in range(GATE5_AXIS) for budget in range(GATE5_AXIS)}
    seen: dict[str, set] = {r: set() for r in R_HEX}
    for record in records:
        _require(isinstance(record, dict), "Gate-5 record is not an object")
        key = record.get("key")
        _require(isinstance(key, dict) and key.get("r_hex") in R_HEX, "Gate-5 record outside frozen r population")
        r = key["r_hex"]
        coordinate = tuple(key.get(name) for name in ("ell_card", "ell_sector", "ell_budget"))
        _require(all(_int(v) for v in coordinate) and coordinate in expected, "Gate-5 coordinate outside expected grid")
        _require(coordinate not in seen[r], "duplicate Gate-5 coordinate")
        seen[r].add(coordinate)
        for e in ENCODINGS:
            _add(buckets[(r, e)], _gate5_summary(record.get(e)))
    result = []
    for r in R_HEX:
        _require(seen[r] == expected, "Gate-5 slice coverage drift")
        for e in ENCODINGS:
            item = _render(buckets[(r, e)])
            _require(item["coordinate_count"] == GATE5_SLICE, "Gate-5 slice count drift")
            result.append({"source": GATE5_SOURCE, "r_hex": r, "encoding": e, **item})
    return result


def aggregate_ratified_gate5() -> list[dict[str, Any]]:
    """The sole production entry point for the D013-eligible Gate-5 input."""
    try:
        return aggregate_gate5(ratified_g5_input.iter_ratified_records())
    except ratified_g5_input.RatifiedG5InputError as exc:
        raise RateSurfaceError(f"ratified Gate-5 boundary rejected input: {exc}") from exc


# --------------------------------------------------------------------------
# D013 mechanical disposition (six Gate-5 primary cells only)
# --------------------------------------------------------------------------

def _rational(value: object, label: str) -> tuple[int, int]:
    _require(isinstance(value, dict) and set(value) == {"numerator", "denominator"}, f"{label}: malformed rational")
    numerator, denominator = value["numerator"], value["denominator"]
    _require(_int(numerator) and _int(denominator) and denominator > 0 and 0 <= numerator <= denominator, f"{label}: rational out of range")
    return numerator, denominator


def d013_disposition(g5_series: object) -> dict[str, Any]:
    """D013 exact-sign rule over exactly the six unique Gate-5 primary cells; anything else is refused."""
    _require(isinstance(g5_series, (list, tuple)) and len(g5_series) == 6, "D013 requires exactly six Gate-5 primary series")
    by: dict[tuple[str, str], Mapping[str, Any]] = {}
    for entry in g5_series:
        _require(isinstance(entry, dict) and set(entry) == SERIES_KEYS, "D013 input series has a malformed key set")
        _require(entry["source"] == GATE5_SOURCE, "D013 input is not a Gate-5 CSB primary series")
        _require("condition" not in entry, "D013 input carries a D015 condition; only the primary series is eligible")
        cell = (entry["r_hex"], entry["encoding"])
        _require(cell in D013_CELLS, "D013 input cell outside r in {0.5, 1, 2} x {unbalanced, slack}")
        _require(cell not in by, "duplicate D013 input cell")
        _require(_int(entry["coordinate_count"]) and entry["coordinate_count"] == GATE5_SLICE, "D013 input series count drift")
        by[cell] = entry
    _require(set(by) == D013_CELLS, "D013 input is missing a cell")
    differences = []
    denominators = set()
    for r in R_HEX:
        s_n, s_d = _rational(by[(r, "slack")]["rho_E_exact"], f"slack r={r}")
        u_n, u_d = _rational(by[(r, "unbalanced")]["rho_E_exact"], f"unbalanced r={r}")
        _require(s_d == u_d == GATE5_SLICE, "D013 denominator mismatch")
        denominators.add(s_d)
        differences.append({"r_hex": r, "numerator": s_n - u_n, "denominator": s_d})
    _require(len(denominators) == 1, "D013 denominators differ across r")
    nums = [d["numerator"] for d in differences]
    fires = any(x == 0 for x in nums) or not (all(x > 0 for x in nums) or all(x < 0 for x in nums))
    return {"rule": "D013: Delta(r) = rho_slack - rho_unbalanced, exact; fires iff any Delta is zero or the three Deltas "
                    "do not share one strict sign; inputs are the six Gate-5 primary (2048, 2048) cells only",
            "differences": differences,
            "disposition": "fires" if fires else "does_not_fire",
            "required_conditions": ["C", "CB", "CS", "CSB"] if fires else [],
            "ablation_status": "not_run_requires_separate_authorization" if fires else "not_applicable"}


# --------------------------------------------------------------------------
# V-14 sealed core artifact sets (separate, non-pooled series)
# --------------------------------------------------------------------------

def _v14_summary(record: Mapping[str, Any], c_h: int, c_f: int, encoding: str) -> Mapping[str, Any]:
    if (c_h, c_f) == PRIMARY_PAIR:
        group = record.get("primary_c_h_2048")
    else:
        diagnostics = record.get("d015_diagnostics")
        group = diagnostics.get(f"c_H={c_h}__c_f={c_f}") if isinstance(diagnostics, dict) else None
    _require(isinstance(group, dict) and isinstance(group.get(encoding), dict), "missing V-14 D015 summary")
    return group[encoding]


def require_root_membership(root: Path, batch_ids: Iterable[str]) -> None:
    """The artifact root must contain exactly the plan's batch directories, none symlinked."""
    expected = set(batch_ids)
    _require(root.is_dir() and not root.is_symlink(), "V-14 artifact root is not a plain directory")
    try:
        members = sorted(entry.name for entry in os.scandir(root))
    except OSError as exc:
        raise RateSurfaceError("V-14 artifact root unreadable") from exc
    _require(set(members) == expected, "V-14 artifact root membership differs from the plan's batch ids "
                                       f"(extra: {sorted(set(members) - expected)[:4]}, missing: {sorted(expected - set(members))[:4]})")
    for name in members:
        member = root / name
        _require(not member.is_symlink() and member.is_dir(), f"V-14 batch directory is a symlink or not a directory: {name}")


def aggregate_v14(plan_path: Path, artifact_root: Path, expected_scale: str, *,
                  accepted_plans: Mapping[str, str] = ACCEPTED_V14_PLANS,
                  audit: Callable[[Mapping[str, Any], Path], Mapping[str, Any]] = v14_audit.validate_final_set,
                  record_validator: Callable[..., None] = core.validate_record) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Audit a sealed V-14 set, then aggregate only from hash-bound, re-validated records.json bytes.

    ``accepted_plans``/``audit``/``record_validator`` are injection seams for hardware-free fixtures; the
    production CLI never overrides them.
    """
    _require(expected_scale in ACCEPTED_V14_PLANS and expected_scale in accepted_plans, "unknown V-14 scale")
    try:
        plan_bytes = Path(plan_path).read_bytes()
        plan = json.loads(plan_bytes)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RateSurfaceError(f"V-14 plan unreadable: {exc}") from exc
    _require(isinstance(plan, dict) and plan.get("scale") == expected_scale, f"V-14 plan is not the {expected_scale} plan")
    _require(plan.get("content_sha256") == accepted_plans[expected_scale] == contract.content_sha256(plan),
             f"V-14 {expected_scale} plan is not the accepted plan (content SHA-256 pin)")
    try:
        receipt = audit(plan, Path(artifact_root))
    except (v14_audit.LegacyAuditError, contract.CoreContractError, core.CoreError) as exc:
        raise RateSurfaceError(f"V-14 sealed-set audit failed: {exc}") from exc
    _require(isinstance(receipt, dict) and receipt.get("verdict") == "accepted"
             and receipt.get("plan_content_sha256") == plan["content_sha256"], "V-14 audit receipt is not an acceptance of this plan")
    batches = receipt.get("batches")
    _require(isinstance(batches, list) and batches, "V-14 audit receipt lists no batches")
    plan_batches = plan.get("batches")
    _require(isinstance(plan_batches, list) and {b.get("batch_id") for b in plan_batches} == {b.get("batch_id") for b in batches},
             "V-14 audit receipt batches differ from the plan")
    require_root_membership(Path(artifact_root), [b["batch_id"] for b in plan_batches])
    total = plan.get("grid", {}).get("total_coordinates")
    _require(_int(total) and total > 0, "V-14 plan grid total is malformed")
    try:
        ledger = contract._base(contract.base.load_v14_ledgers)[expected_scale]["payload"]
    except contract.CoreContractError as exc:
        raise RateSurfaceError(str(exc)) from exc
    lambda_ref_hex = plan.get("classifier", {}).get("lambda_ref_hex")
    slack_count = plan.get("core_validation_identity", {}).get("domain", {}).get("slack", {}).get("entries")
    _require(isinstance(lambda_ref_hex, str) and _int(slack_count) and slack_count > 0, "V-14 plan lacks classifier/domain bindings")
    buckets = {(pair, encoding): _new() for pair in CONDITIONS for encoding in ENCODINGS}
    covered: set[int] = set()
    consumed = []
    for entry in sorted(batches, key=lambda item: item["range"]["start"]):
        directory = Path(entry["path"])
        _require(directory.parent == Path(artifact_root).resolve() or directory.parent == Path(artifact_root),
                 "V-14 audit receipt points outside the artifact root")
        try:
            raw = (directory / "records.json").read_bytes()
        except OSError as exc:
            raise RateSurfaceError("validated V-14 records became unreadable") from exc
        # TOCTOU binding: the bytes consumed here must be the bytes the audit hashed.
        _require(_sha256(raw) == entry["records_file_sha256"], f"V-14 records.json changed after the audit: {entry['batch_id']}")
        try:
            records = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RateSurfaceError("V-14 records.json is not JSON") from exc
        _require(isinstance(records, dict) and records.get("content_sha256") == entry["records_content_sha256"] == contract.content_sha256(records)
                 and records.get("batch_id") == entry["batch_id"] and records.get("plan_content_sha256") == plan["content_sha256"]
                 and records.get("range") == entry["range"] and records.get("record_count") == entry["range"]["count"],
                 f"V-14 records.json identity mismatch: {entry['batch_id']}")
        items = records.get("records")
        _require(isinstance(items, list) and len(items) == entry["range"]["count"], f"V-14 record count drift: {entry['batch_id']}")
        for offset, record in enumerate(items):
            linear = entry["range"]["start"] + offset
            try:
                record_validator(record, linear, expected_scale, ledger, lambda_ref_hex, slack_count)
            except core.CoreError as exc:
                raise RateSurfaceError(f"V-14 record failed semantic validation: {entry['batch_id']}: {exc}") from exc
            _require(linear not in covered, "duplicate V-14 coordinate")
            covered.add(linear)
            for pair in CONDITIONS:
                for encoding in ENCODINGS:
                    _add(buckets[(pair, encoding)], _v14_summary(record, *pair, encoding))
        consumed.append({"batch_id": entry["batch_id"], "records_file_sha256": entry["records_file_sha256"],
                         "records_content_sha256": entry["records_content_sha256"], "record_count": entry["range"]["count"]})
    _require(covered == set(range(total)), "V-14 coverage drift")
    series = []
    for c_h, c_f in CONDITIONS:
        for encoding in ENCODINGS:
            item = _render(buckets[((c_h, c_f), encoding)])
            _require(item["coordinate_count"] == total, "V-14 coverage drift")
            series.append({"source": "v14", "scale": expected_scale,
                           "condition": {"c_H": c_h, "c_f": c_f, "role": "primary" if (c_h, c_f) == PRIMARY_PAIR else "diagnostic"},
                           "encoding": encoding, **item})
    evidence = {"plan_file_sha256": _sha256(plan_bytes), "plan_content_sha256": plan["content_sha256"],
                "audit_receipt_content_sha256": receipt.get("content_sha256"), "batch_count": len(consumed),
                "coordinate_count": total, "consumed_records": consumed,
                "binding": "records.json bytes hash-bound to the audit receipt and re-validated record by record before aggregation",
                "compatibility": "only the audited range/batch descriptor pair"}
    return series, evidence


# --------------------------------------------------------------------------
# Whole artifact (in memory only)
# --------------------------------------------------------------------------

def _no_float_or_bool(value: object, label: str = "output") -> None:
    if isinstance(value, (float, bool)):
        raise RateSurfaceError(f"{label} contains float or bool")
    if isinstance(value, dict):
        for key, item in value.items():
            _no_float_or_bool(item, f"{label}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _no_float_or_bool(item, f"{label}[{index}]")


def build_rate_surface(*, v14_0_5_plan: Path, v14_0_5_artifacts: Path,
                       v14_2x_plan: Path, v14_2x_artifacts: Path, reviewed_handoff: str,
                       gate5_loader: Callable[[], list[dict[str, Any]]] = aggregate_ratified_gate5,
                       v14_aggregator: Callable[..., tuple[list[dict[str, Any]], dict[str, Any]]] = aggregate_v14) -> dict[str, Any]:
    """Build in memory only; the caller decides whether a reviewed artifact may be written.

    ``gate5_loader``/``v14_aggregator`` are injection seams for hardware-free fixtures; the production CLI
    never overrides them, so production always goes through the ratified boundary and pinned plans.
    """
    _require(isinstance(reviewed_handoff, str) and reviewed_handoff.strip() != "", "reviewed handoff is required")
    authorities = bind_authorities()
    gate5 = gate5_loader()
    _require(isinstance(gate5, list) and len(gate5) == 6, "Gate-5 loader did not return six primary series")
    v05, v05_evidence = v14_aggregator(v14_0_5_plan, v14_0_5_artifacts, "0.5x")
    v2, v2_evidence = v14_aggregator(v14_2x_plan, v14_2x_artifacts, "2x")
    _require(v05_evidence["plan_content_sha256"] != v2_evidence["plan_content_sha256"], "V-14 plans must be distinct")
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "purpose": "Gate-6 exact aggregate rate surfaces and mechanical D013 disposition only; no inference or conclusion",
        "input_identities": {
            "gate5_registry_file_sha256": ratified_g5_input.REGISTRY_FILE_SHA256,
            "gate5_registry_content_sha256": ratified_g5_input.REGISTRY_CONTENT_SHA256,
            "gate5_ratification_file_sha256": ratified_g5_input.RATIFICATION_FILE_SHA256,
            "d015_d016_decisions_file_sha256": authorities["research/decisions/DECISIONS.md"],
            "frozen_math_file_sha256": authorities["research/00_specifications/FROZEN_MATH_SPEC.md"],
            "accepted_v14_plans": dict(ACCEPTED_V14_PLANS),
            "v14": {"0.5x": v05_evidence, "2x": v2_evidence},
        },
        "series": gate5 + v05 + v2,
        "d013_disposition": d013_disposition(gate5),
        "producer_source_sha256": {"research/g6/rate_surface_and_d013.py": _sha("research/g6/rate_surface_and_d013.py")},
        "reviewed_handoff": reviewed_handoff,
        "scientific_outputs": "exact aggregates and mechanical D013 disposition only",
    }
    _no_float_or_bool(payload)
    payload["content_sha256"] = _sha256(canonical_bytes(payload))
    return payload

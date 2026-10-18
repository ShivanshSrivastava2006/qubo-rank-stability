"""Gate-7 Stage-1 inference over accepted, immutable Gate-5/Gate-6 evidence.

This module never evaluates an energy, minimum, tie set, classifier, or new
penalty coordinate.  It streams already certified Gate-5 primary labels only
to derive literal spatial predicates required by the pre-registered H0/H1/H3
wording, and checks their aggregate against the accepted Gate-6 rate artifact.
"""

from __future__ import annotations

from collections import Counter, deque
from fractions import Fraction
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from src.g6 import ratified_g5_input


ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "decisions_os/g7_stage1_inference/v1"
RATE_REL = "research/g6/rate_surface_and_d013/RATE_SURFACE_AND_D013.json"
RATE_FILE_SHA256 = "6f052678ad854f3a8e705c365df4221b70cdaa347007436d3bedbda8e31229ff"
RATE_CONTENT_SHA256 = "00636483e62e78f4b865274b6b79b47842072f90312beee3425c7fce5d8597ea"
RATE_SCHEMA = "decisions_os/g6_rate_surface_and_d013/v1"
ACCEPTED_V14_PLANS = {
    "0.5x": "e5b44620206e5bbaca3a03e890a4f99b4f29a23b87d3e2d4f8f8be2c3067d71d",
    "2x": "38c01eff5a313273fc106a5f5c39760628e59132b9a7a72e0176b37aa1897748",
}
INFERENCE_AUTHORITIES = {
    "RESEARCH_SCOPING_AND_SCOPE_LOCK.md": "86fe02434d31180db8780c8545f151c460cee1b41b86236401173165bd28f6bc",
    "research/00_specifications/IMPLEMENTATION_SPEC.md": "6aad8221e45fd34d707e0e33e289aab2f9e099dc51590c4793da2679d4c78dae",
    "research/decisions/DECISIONS.md": "274c6cd92d4958957d125efc7ae2ddb6f40629eb78b7c2e2be99224e038ce849",
}
R_HEX = tuple(value.hex() for value in (0.5, 1.0, 2.0))
ENCODINGS = ("unbalanced", "slack")
AXIS = 61
CELL_COUNT = AXIS ** 3
D011 = {
    "transition": ("research/g6/d011_transition_output/D011_TRANSITION_OUTPUT.json",
                   "bf70a64980912db7fa88cc03e7c4cd03d1ff2878214e4bb0d846cb2900ef9f34",
                   "5adc8f03e8a4193e07bc37381a2aad1f67cd72119cce416ceebcfece184f528c"),
    "matched_subgrid": ("research/g6/d011_matched_subgrid_comparison/D011_MATCHED_SUBGRID_COMPARISON.json",
                        "05fff9224ede68cddddd37fc16a5a89337675e6d8aca87b25ce56f57a872c265",
                        "c0489e95d922d4951a39113e8ab3de5c2d0ba718bf37650817f95d29ffcf4f98"),
}


class Gate7InferenceError(RuntimeError):
    """An accepted evidence item is missing, altered, or semantically inconsistent."""


def _require(ok: bool, message: str) -> None:
    if not ok:
        raise Gate7InferenceError(message)


def canonical_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _content_sha(payload: Mapping[str, Any], label: str) -> str:
    body = dict(payload)
    claimed = body.pop("content_sha256", None)
    _require(isinstance(claimed, str) and len(claimed) == 64, f"{label} content hash is malformed")
    _require(_sha_bytes(canonical_bytes(body)) == claimed, f"{label} content hash differs")
    return claimed


def _read_json(path: Path, label: str) -> tuple[bytes, dict[str, Any]]:
    try:
        raw = path.read_bytes()
        payload = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Gate7InferenceError(f"{label} is unreadable JSON") from exc
    _require(isinstance(payload, dict), f"{label} is not an object")
    return raw, payload


def _validate_inference_authorities() -> dict[str, str]:
    for relative, expected in INFERENCE_AUTHORITIES.items():
        try:
            actual = _sha_bytes((ROOT / relative).read_bytes())
        except OSError as exc:
            raise Gate7InferenceError(f"Gate-7 authority is unreadable: {relative}") from exc
        _require(actual == expected, f"Gate-7 authority differs: {relative}")
    return dict(INFERENCE_AUTHORITIES)


def _strict_int(value: object, label: str, *, lower: int = 0) -> int:
    _require(type(value) is int and value >= lower, f"{label} is not an integer in range")
    return value


def _rational(value: object, label: str) -> Fraction:
    _require(isinstance(value, dict) and set(value) == {"numerator", "denominator"}, f"{label} malformed")
    numerator = _strict_int(value["numerator"], f"{label}.numerator")
    denominator = _strict_int(value["denominator"], f"{label}.denominator", lower=1)
    _require(numerator <= denominator, f"{label} is outside [0,1]")
    return Fraction(numerator, denominator)


def _load_accepted_rate(path: Path, *, expected_file_sha256: str = RATE_FILE_SHA256,
                        expected_content_sha256: str = RATE_CONTENT_SHA256) -> dict[str, Any]:
    raw, payload = _read_json(path, "accepted Gate-6 rate artifact")
    _require(raw == canonical_bytes(payload), "accepted Gate-6 rate artifact is not canonical bytes")
    _require(_sha_bytes(raw) == expected_file_sha256, "accepted Gate-6 rate artifact file identity differs")
    _require(payload.get("schema") == RATE_SCHEMA, "accepted Gate-6 rate artifact schema differs")
    _require(_content_sha(payload, "accepted Gate-6 rate artifact") == expected_content_sha256,
             "accepted Gate-6 rate artifact content identity differs")
    _require(payload.get("d013_disposition", {}).get("disposition") == "does_not_fire"
             and payload["d013_disposition"].get("ablation_status") == "not_applicable",
             "accepted Gate-6 D013 disposition is not the accepted no-ablation branch")
    return payload


def _validate_d011() -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for key, (relative, file_hash, content_hash) in D011.items():
        raw, payload = _read_json(ROOT / relative, f"accepted D011 {key} artifact")
        _require(_sha_bytes(raw) == file_hash, f"accepted D011 {key} file identity differs")
        _require(_content_sha(payload, f"accepted D011 {key} artifact") == content_hash,
                 f"accepted D011 {key} content identity differs")
        result[key] = {"file_sha256": file_hash, "content_sha256": content_hash}
    return result


def _series_index(rate: Mapping[str, Any]) -> dict[tuple[str, str], Mapping[str, Any]]:
    raw = rate.get("series")
    _require(isinstance(raw, list), "rate artifact series is malformed")
    result: dict[tuple[str, str], Mapping[str, Any]] = {}
    for item in raw:
        if not isinstance(item, dict) or item.get("source") != "gate5_csb_primary":
            continue
        r, encoding = item.get("r_hex"), item.get("encoding")
        _require(r in R_HEX and encoding in ENCODINGS, "rate artifact has a malformed Gate-5 series cell")
        cell = (r, encoding)
        _require(cell not in result, "rate artifact duplicates a Gate-5 series cell")
        _require(item.get("coordinate_count") == CELL_COUNT, "rate artifact Gate-5 series count differs")
        labels = item.get("set_label_counts")
        _require(isinstance(labels, dict) and set(labels) == {"A", "B", "C"}
                 and all(type(v) is int and v >= 0 for v in labels.values())
                 and sum(labels.values()) == CELL_COUNT, "rate artifact Gate-5 label census differs")
        _require(_rational(item.get("rho_E_exact"), "rate artifact rho") == Fraction(labels["A"], CELL_COUNT),
                 "rate artifact rho differs from the A census")
        result[cell] = item
    _require(set(result) == {(r, encoding) for r in R_HEX for encoding in ENCODINGS},
             "rate artifact lacks exactly the six Gate-5 primary series")
    return result


def _linear(card: int, sector: int, budget: int) -> int:
    return (card * AXIS + sector) * AXIS + budget


def _unlinear(value: int) -> tuple[int, int, int]:
    card, remainder = divmod(value, AXIS * AXIS)
    sector, budget = divmod(remainder, AXIS)
    return card, sector, budget


def _neighbors(value: int) -> tuple[int, ...]:
    card, sector, budget = _unlinear(value)
    result: list[int] = []
    for axis, coordinate in enumerate((card, sector, budget)):
        for delta in (-1, 1):
            changed = coordinate + delta
            if not 0 <= changed < AXIS:
                continue
            fields = [card, sector, budget]
            fields[axis] = changed
            result.append(_linear(*fields))
    return tuple(result)


def _components(points: set[int]) -> dict[str, int]:
    remaining = set(points)
    component_count = 0
    largest = 0
    while remaining:
        component_count += 1
        queue = deque([remaining.pop()])
        size = 0
        while queue:
            current = queue.popleft()
            size += 1
            for neighbor in _neighbors(current):
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    queue.append(neighbor)
        largest = max(largest, size)
    return {"component_count": component_count, "largest_component_size": largest}


def _region_shape(points: set[int]) -> dict[str, Any]:
    if not points:
        return {"A_point_count": 0, "cartesian_product": "empty", "axis_aligned_box": "empty"}
    projections = [set() for _ in range(3)]
    for value in points:
        for axis, coordinate in enumerate(_unlinear(value)):
            projections[axis].add(coordinate)
    product_size = len(projections[0]) * len(projections[1]) * len(projections[2])
    cartesian = len(points) == product_size
    contiguous = all(max(axis) - min(axis) + 1 == len(axis) for axis in projections)
    return {
        "A_point_count": len(points),
        "cartesian_product": "yes" if cartesian else "no",
        "axis_aligned_box": "yes" if cartesian and contiguous else "no",
        "axis_projection_sizes": [len(axis) for axis in projections],
    }


def scan_primary_lattice(records: Iterable[Mapping[str, Any]], rate: Mapping[str, Any]) -> dict[str, Any]:
    """Stream ratified primary labels and derive no energies or new grid values."""
    expected = set(range(CELL_COUNT))
    seen = {r: set() for r in R_HEX}
    labels = {(r, encoding): Counter({"A": 0, "B": 0, "C": 0}) for r in R_HEX for encoding in ENCODINGS}
    a_regions = {(r, encoding): set() for r in R_HEX for encoding in ENCODINGS}
    advantage = {(r, direction): set() for r in R_HEX for direction in ("slack_A_advantage", "unbalanced_A_advantage")}
    for record in records:
        _require(isinstance(record, Mapping), "ratified Gate-5 record is not an object")
        key = record.get("key")
        _require(isinstance(key, Mapping) and key.get("r_hex") in R_HEX, "ratified Gate-5 record r is invalid")
        r = key["r_hex"]
        try:
            card, sector, budget = (key[name] for name in ("ell_card", "ell_sector", "ell_budget"))
        except KeyError as exc:
            raise Gate7InferenceError("ratified Gate-5 record lacks a coordinate axis") from exc
        _require(all(type(v) is int and 0 <= v < AXIS for v in (card, sector, budget)),
                 "ratified Gate-5 record coordinate is invalid")
        linear = _linear(card, sector, budget)
        _require(linear not in seen[r], "ratified Gate-5 record duplicates a coordinate")
        seen[r].add(linear)
        point_labels: dict[str, str] = {}
        for encoding in ENCODINGS:
            certification = record.get(encoding)
            label = certification.get("set_label") if isinstance(certification, Mapping) else None
            _require(label in {"A", "B", "C"}, "ratified Gate-5 primary set label is invalid")
            point_labels[encoding] = label
            labels[(r, encoding)][label] += 1
            if label == "A":
                a_regions[(r, encoding)].add(linear)
        if point_labels["slack"] == "A" and point_labels["unbalanced"] != "A":
            advantage[(r, "slack_A_advantage")].add(linear)
        elif point_labels["unbalanced"] == "A" and point_labels["slack"] != "A":
            advantage[(r, "unbalanced_A_advantage")].add(linear)
    index = _series_index(rate)
    per_r: dict[str, Any] = {}
    for r in R_HEX:
        _require(seen[r] == expected, "ratified Gate-5 primary lattice coverage differs")
        for encoding in ENCODINGS:
            _require(dict(labels[(r, encoding)]) == index[(r, encoding)]["set_label_counts"],
                     "accepted aggregate differs from the streamed accepted primary labels")
        wins = {direction: advantage[(r, direction)] for direction in ("slack_A_advantage", "unbalanced_A_advantage")}
        per_r[r] = {
            "slack_A_advantage": {"point_count": len(wins["slack_A_advantage"]),
                                    **_components(wins["slack_A_advantage"])},
            "unbalanced_A_advantage": {"point_count": len(wins["unbalanced_A_advantage"]),
                                         **_components(wins["unbalanced_A_advantage"])},
            "both_directional_A_advantages": "yes" if all(wins[direction] for direction in wins) else "no",
            "A_region_shape": {encoding: _region_shape(a_regions[(r, encoding)]) for encoding in ENCODINGS},
        }
    return per_r


def _sign(value: int) -> str:
    return "positive" if value > 0 else "negative" if value < 0 else "zero"


def _v14_primary(rate: Mapping[str, Any]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for scale, expected_count in (("0.5x", 29_791), ("2x", 1_367_631)):
        cells = [x for x in rate["series"] if isinstance(x, dict) and x.get("source") == "v14"
                 and x.get("scale") == scale and x.get("condition") == {"c_H": 2048, "c_f": 2048, "role": "primary"}]
        _require(len(cells) == 2 and {x.get("encoding") for x in cells} == set(ENCODINGS),
                 f"accepted V-14 {scale} primary series is malformed")
        by = {x["encoding"]: x for x in cells}
        _require(all(x.get("coordinate_count") == expected_count for x in cells), f"accepted V-14 {scale} count differs")
        delta = _rational(by["slack"].get("rho_E_exact"), f"V-14 {scale} slack") - _rational(by["unbalanced"].get("rho_E_exact"), f"V-14 {scale} unbalanced")
        output[scale] = {"slack_minus_unbalanced_rho": {"numerator": delta.numerator, "denominator": delta.denominator},
                         "sign": _sign(delta.numerator), "coordinate_count": expected_count}
    return output


def build_inference(*, rate_path: Path = ROOT / RATE_REL, reviewed_handoff: str,
                    records: Iterable[Mapping[str, Any]] | None = None,
                    expected_rate_file_sha256: str = RATE_FILE_SHA256,
                    expected_rate_content_sha256: str = RATE_CONTENT_SHA256) -> dict[str, Any]:
    """Build a canonical inference artifact from accepted evidence only."""
    _require(isinstance(reviewed_handoff, str) and reviewed_handoff.strip(), "reviewed handoff is required")
    rate = _load_accepted_rate(rate_path, expected_file_sha256=expected_rate_file_sha256,
                               expected_content_sha256=expected_rate_content_sha256)
    authorities = _validate_inference_authorities()
    identities = rate.get("input_identities")
    _require(isinstance(identities, Mapping)
             and identities.get("gate5_registry_content_sha256") == ratified_g5_input.REGISTRY_CONTENT_SHA256,
             "accepted rate artifact Gate-5 registry binding differs")
    _require(identities.get("accepted_v14_plans") == ACCEPTED_V14_PLANS,
             "accepted rate artifact V-14 plan bindings differ")
    source = ratified_g5_input.iter_ratified_records() if records is None else records
    lattice = scan_primary_lattice(source, rate)
    series = _series_index(rate)
    deltas = []
    c_deltas = []
    for r in R_HEX:
        slack, unbalanced = series[(r, "slack")], series[(r, "unbalanced")]
        rho_delta = _rational(slack["rho_E_exact"], "slack rho") - _rational(unbalanced["rho_E_exact"], "unbalanced rho")
        deltas.append({"r_hex": r, "numerator": rho_delta.numerator, "denominator": rho_delta.denominator,
                       "sign": _sign(rho_delta.numerator)})
        c_delta = unbalanced["set_label_counts"]["C"] - slack["set_label_counts"]["C"]
        c_deltas.append({"r_hex": r, "numerator": c_delta, "denominator": CELL_COUNT, "sign": _sign(c_delta)})
    h1_observed = any(item["both_directional_A_advantages"] == "yes" for item in lattice.values())
    h3_nonbox = any(shape["axis_aligned_box"] == "no"
                    for item in lattice.values() for shape in item["A_region_shape"].values())
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "purpose": "Gate-7 Stage-1 inference from accepted artifacts only; no new energy, tie, label, rate, fit, or experiment",
        "accepted_evidence": {
            "rate_surface_file_sha256": expected_rate_file_sha256,
            "rate_surface_content_sha256": expected_rate_content_sha256,
            "inference_authorities": authorities,
            "gate5_registry_content_sha256": identities["gate5_registry_content_sha256"],
            "d011": _validate_d011(),
            "v14": {scale: {key: identities["v14"][scale][key]
                              for key in ("plan_content_sha256", "audit_receipt_content_sha256", "batch_count", "coordinate_count")}
                    for scale in ("0.5x", "2x")},
        },
        "primary_reported_rates": [series[(r, encoding)] for r in R_HEX for encoding in ENCODINGS],
        "primary_rate_differences": deltas,
        "primary_C_rate_differences_unbalanced_minus_slack": c_deltas,
        "spatial_A_predicates": lattice,
        "v14_primary_condition_comparison": _v14_primary(rate),
        "hypothesis_evaluation": {
            "H0_rank_stability": {
                "rate_component": "indeterminate_no_preregistered_comparability_threshold",
                "pointwise_A_advantage_flip": "observed" if h1_observed else "not_observed",
                "overall": "falsified_by_observed_pointwise_A_advantage_flip" if h1_observed
                else "not_falsified_by_the_exact_rank_flip_predicate",
            },
            "H1_rank_instability": {
                "literal_A_advantage_crossover": "observed" if h1_observed else "not_observed",
                "status": "not_falsified_crossover_not_adjudicated_no_preregistered_subregion_criterion" if h1_observed
                else "falsified_by_weak_dominance_of_A_advantage",
            },
            "H2_infeasibility_asymmetry": {
                "exact_direction": [item["sign"] for item in c_deltas],
                "status": "indeterminate_no_preregistered_measurability_threshold",
            },
            "H3_constraint_heterogeneity": {
                "within_sweep_nonbox_A_region": "observed" if h3_nonbox else "not_observed",
                "active_set_ablation": "not_run_D013_did_not_fire",
                "status": "indeterminate_for_active_set_claim_without_the_conditional_ablation",
            },
        },
        "mandatory_conditioning": [
            "All unbalanced comparisons are conditional on D005/D006's non-neutral mapping; its local D<0 gap for w>1 confounds attribution and is not a neutrality baseline.",
            "All Stage-1 conclusions are conditional on the fixed kappa_risk convention and D010's m_hi=1 derived / m_lo=4 judgement box rule.",
            "V-14 is report-only at r=1; its 0.5x m_hi floor-to-zero defect is a recorded judgement and both V-14 scales remain separate from the primary grid.",
            "D011 is non-primary, matched-subgrid only, and carries its known positive local curvature-match bias; it is not a D013 input or rank-stability evidence.",
            "No Stage-2 generalization is claimed.",
        ],
        "reviewed_handoff": reviewed_handoff,
    }
    payload["content_sha256"] = _sha_bytes(canonical_bytes(payload))
    return payload

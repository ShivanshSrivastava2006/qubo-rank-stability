"""
production_cuda_runner.py

Implements the per-instance axes/payload builder and range-streaming CUDA
all-coordinate producer. Consumes genuinely verified instance components
without fabricating authority or substituting Python run_core.
"""

from collections.abc import Iterator, Mapping, Sequence
import hashlib
import math
from pathlib import Path
from typing import Any
from dataclasses import dataclass
from types import MappingProxyType
from src.g4.classification import OriginalObjectiveService, DecodedClassifier
from research.g9.wp8b import wp8b_non_synthetic_preparation_v2 as preparation

from research.g9 import stage2_coordinate_records as records
from research.g9 import stage2_instance_preparation as instance_prep
from research.g9.cuda_qualification import stage2_cuda_input_frame as input_frame
from research.g9.cuda_qualification import stage2_cuda_core_bridge as bridge
from research.g9.cuda_qualification import stage2_cuda_reconstruct as reconstruct
from research.g9.cuda_qualification import stage2_cuda_core_stream_engine as core


def validate_release_authority(instance, prepared_record, release_authority, library_path, expected_library_sha256):
    preparation.validate_provenance_record(prepared_record, instance, require_production=True,
                                          release_authority=release_authority)
    if (not isinstance(expected_library_sha256, str) or len(expected_library_sha256) != 64
            or any(c not in "0123456789abcdef" for c in expected_library_sha256)):
        raise RuntimeError("An independently qualified library SHA256 is required")
    library_path = Path(library_path)
    if library_path.is_symlink() or not library_path.is_file():
        raise RuntimeError("Library must be a regular qualified file")
    if hashlib.sha256(library_path.read_bytes()).hexdigest() != expected_library_sha256:
        raise RuntimeError("Qualified library SHA256 mismatch")


def build_per_instance_axes(delta_full: float, lambda_ref_val: float) -> records.FrozenAxes:
    """
    Derive the per-instance frozen axes dynamically from the actual problem
    using frozen build_ledgers and g6 primitives.
    """
    # 1. Primary grid
    rule = instance_prep._box_rule(delta_full, lambda_ref_val)
    primary_rows = instance_prep._coordinates(rule["q_min"], rule["q_max"])
    primary = tuple(float.fromhex(str(row["binary64_hex"])) for row in primary_rows)
    
    # 2. D011 (every fifth PRIMARY coordinate)
    if len(primary) != 61:
        raise RuntimeError("Frozen D011 selection requires 61 primary points; refuse unsupported grid")
    d011 = tuple(primary[i] for i in range(0, 61, 5))
    
    # 3. V14 coordinates based on own rho_box and scaling
    rule = instance_prep._box_rule(delta_full, lambda_ref_val)
    rho_box = rule["rho_box"]
    
    base_q_min = rule["q_min"] + 4
    base_q_max = rule["q_max"] - 1
    
    # V14 0.5x: m_lo=2, m_hi=0
    v14_05_q_min = base_q_min - 2
    v14_05_q_max = base_q_max + 0
    v14_05_rows = instance_prep._coordinates(v14_05_q_min, v14_05_q_max)
    v14_0_5x = tuple(float.fromhex(str(row["binary64_hex"])) for row in v14_05_rows)
    
    # V14 2x: m_lo=8, m_hi=2
    v14_2_q_min = base_q_min - 8
    v14_2_q_max = base_q_max + 2
    v14_2_rows = instance_prep._coordinates(v14_2_q_min, v14_2_q_max)
    v14_2x = tuple(float.fromhex(str(row["binary64_hex"])) for row in v14_2_rows)
    
    return records.FrozenAxes(
        lambda_ref=lambda_ref_val,
        primary=primary,
        d011=d011,
        v14_0_5x=v14_0_5x,
        v14_2x=v14_2x
    )


def build_production_payload(instance: instance_prep.SyntheticInstance, lambda_ref_val: float) -> dict[str, Any]:
    """
    Binds the genuinely verified instance to the exact CUDA core PayloadData schema.
    """
    sector_to_assets = {label: [] for label in instance.sector_labels}
    for asset_idx, ticker in enumerate(instance.order):
        sector_label = instance.sector_of[ticker]
        sector_to_assets[sector_label].append(asset_idx)
    sectors = [sector_to_assets[label] for label in instance.sector_labels]

    return {
        "mu": list(instance.mu),
        "sigma": [list(row) for row in instance.Sigma],
        "prices": list(instance.p),
        "kappa_risk": float(instance.kappa),
        "k": float(instance.K),
        "c": float(instance.C),
        "b": float(instance.B),
        "lambda_ref": float(lambda_ref_val),
        "sectors": sectors,
    }


def initialize_instance_slack_map(payload: dict[str, Any]) -> reconstruct.SlackIndexMap:
    """Build per-instance domain/slack offsets ONCE via the actual core."""
    domain = core.build_domain(payload)
    return reconstruct.SlackIndexMap(offsets=domain["offsets"], lift_total=domain["lift_total"])


def extract_seven_coefficients(resolved: dict[str, Any]) -> dict[str, float]:
    """
    Convert resolve_coefficients entries to the exact seven coefficient fields
    required by the core ABI. Inactive penalty families are correctly carried
    as exact positive zeros via float.fromhex.
    """
    alpha = float.fromhex(resolved[records.CARDINALITY]["alpha_hex"])
    
    sector_entry = resolved[records.SECTOR]
    budget_entry = resolved[records.BUDGET]
    
    return {
        "alpha": alpha,
        "sector_slack": float.fromhex(sector_entry["lambda_slack_hex"]),
        "sector_linear": float.fromhex(sector_entry["lambda_1_hex"]),
        "sector_quadratic": float.fromhex(sector_entry["lambda_2_hex"]),
        "budget_slack": float.fromhex(budget_entry["lambda_slack_hex"]),
        "budget_linear": float.fromhex(budget_entry["lambda_1_hex"]),
        "budget_quadratic": float.fromhex(budget_entry["lambda_2_hex"]),
    }


def _flush_cuda_batch(
    linears: list[int],
    coefficient_records: list[dict[str, float]],
    payload: dict[str, Any],
    offsets_sha256: str,
    slack_map: reconstruct.SlackIndexMap,
    classifiers: dict[int, DecodedClassifier],
    f_star: float,
    lambda_ref_val: float,
    library_path: Path
) -> Iterator[tuple[int, dict[str, Any]]]:
    """Execute one chunk on the production backend and project summaries."""
    frame = input_frame.build_input_frame(payload, coefficient_records, offsets_sha256)
    
    # Require backend=1 for production hardware bridge
    result = bridge._run_compiled_frame(frame, library_path, require_backend=1)
    
    core_result = result["core_result"]
    summaries = core_result["summaries"]
    
    for slot, linear in enumerate(linears):
        sliced_core_result = {
            encoding: summaries[(slot, encoding)]
            for encoding in core.ENCODINGS
        }
        
        engine_item = {
            "core_result": sliced_core_result,
            "slack": slack_map,
            "classifiers": classifiers,
            "f_star": f_star,
            "lambda_ref": lambda_ref_val,
        }
        yield linear, engine_item


@dataclass(frozen=True)
class VerifiedContext:
    instance_id: str
    prepared_record_sha256: str
    frozen: records.FrozenAxes
    payload: dict[str, Any]
    slack_map: reconstruct.SlackIndexMap
    classifiers: dict[int, DecodedClassifier]
    f_star: float
    lambda_ref: float
    library_path: Path
    library_sha256: str
    offsets_sha256: str


def create_verified_context(instance, prepared_record, release_authority, library_path, expected_library_sha256):
    # All source, approval and factual provenance checks precede domain building.
    validate_release_authority(instance, prepared_record, release_authority, library_path, expected_library_sha256)
    checked = preparation._validate_envelope_for_non_synthetic(instance)
    result = prepared_record["results"]
    lambda_ref_val = result["Lambda_ref"]
    frozen = build_per_instance_axes(result["delta_full"], lambda_ref_val)
    payload = build_production_payload(checked, lambda_ref_val)
    sectors = tuple(tuple(group) for group in payload["sectors"])
    def objective(x):
        indices = [i for i, bit in enumerate(x) if bit]
        return instance_prep._g3.f_fast(indices, checked.mu, checked.Sigma, checked.kappa)
    def feasible(x):
        indices = [i for i, bit in enumerate(x) if bit]
        card, sector, budget = instance_prep._g3.residuals(
            indices, checked.p, sectors, checked.K, checked.C, checked.B)
        return card == 0.0 and all(v >= 0.0 for v in sector) and budget >= 0.0
    classifiers = {c: DecodedClassifier(OriginalObjectiveService(objective, lambda_ref_val, float(c)), feasible)
                   for c in reconstruct.CF_VALUES}
    reconstruct._classifiers(classifiers, lambda_ref_val)
    slack_map = initialize_instance_slack_map(payload)
    immutable_payload = MappingProxyType({k: (tuple(tuple(x) for x in v) if k in ("sigma", "sectors") else tuple(v) if k in ("mu", "prices") else v) for k,v in payload.items()})
    return VerifiedContext(checked.instance_id, prepared_record["content_sha256"], frozen, immutable_payload, slack_map, MappingProxyType(classifiers), result["f_star"], lambda_ref_val,
                           Path(library_path), expected_library_sha256, slack_map.offsets_sha256)


def cuda_range_producer(space, context: VerifiedContext, start=0, stop=None):
    if type(context) is not VerifiedContext:
        raise TypeError("An actual verified production context is required")
    if space.family.condition is not None:
        raise ValueError("Baseline driver refuses D013; use the separately qualified inactive engine")
    # Recheck the independently pinned compiled artifact for every submitted range.
    if hashlib.sha256(context.library_path.read_bytes()).hexdigest() != context.library_sha256:
        raise RuntimeError("Compiled library drift before CUDA range")
    frozen, payload = context.frozen, context.payload
    offsets_sha256, slack_map = context.offsets_sha256, context.slack_map
    classifiers, f_star = context.classifiers, context.f_star
    lambda_ref_val, library_path = context.lambda_ref, context.library_path
    iterator = records.iter_coordinates(space, frozen, start=start, stop=stop, with_coefficients=True)

    batch_linears: list[int] = []
    batch_records: list[dict[str, float]] = []

    for linear, _coordinate, coefficients in iterator:
        batch_linears.append(linear)
        batch_records.append(extract_seven_coefficients(coefficients))

        if len(batch_records) == bridge.ROW_CAPACITY:
            yield from _flush_cuda_batch(
                batch_linears, batch_records, payload, offsets_sha256,
                slack_map, classifiers, f_star, lambda_ref_val, library_path
            )
            batch_linears.clear()
            batch_records.clear()

    if batch_records:
        yield from _flush_cuda_batch(
            batch_linears, batch_records, payload, offsets_sha256,
            slack_map, classifiers, f_star, lambda_ref_val, library_path
        )

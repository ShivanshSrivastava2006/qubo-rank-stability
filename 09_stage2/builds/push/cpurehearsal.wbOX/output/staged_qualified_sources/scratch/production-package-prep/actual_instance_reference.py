"""Additive, unreviewed baseline WP3 CPU seal and matching device inputs.

Numerical work is intended exclusively for the authorized Kaggle CPU job.
No synthetic reference, D013 execution, CUDA invocation or approval fabrication.
The caller must independently pin this module, its imports and helper source.
"""
from __future__ import annotations

import ast
from array import array
import hashlib
import json
import lzma
import math
from pathlib import Path
import struct
from typing import Any, Mapping

from src.g4.instance import Instance
from src.g4.classification import DecodedClassifier, OriginalObjectiveService
from src.g4.energy import tau
from research.g9 import stage2_d013_inactive_evaluator as ev
from research.g9 import stage2_coordinate_records as records
from research.g9 import stage2_reference_seal as seal_api
from research.g9 import stage2_section_b2_harness as harness
from research.g9.cuda_qualification import stage2_cuda_input_frame as frame_api


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def checked_hash(value):
    if type(value) is not str or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("An independently supplied SHA256 is required")
    return value


def load_frozen_helpers(path, expected_sha256):
    """Load unchanged function ASTs without the old synthetic pin-loader.

    The entire original builder file must match an independently supplied pin.
    No old top-level executable statements or synthetic constants are loaded.
    """
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("Frozen helper source must be a regular file")
    source = path.read_bytes()
    if hashlib.sha256(source).hexdigest() != checked_hash(expected_sha256):
        raise ValueError("Frozen helper source hash mismatch")
    names = {"_unbalanced_stream", "_slack_stream", "energy_stream", "tie_flags", "d015_reconstruction"}
    tree = ast.parse(source, filename=str(path))
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    if {n.name for n in functions} != names or len(functions) != len(names):
        raise ValueError("Frozen helper definition census mismatch")
    def require(condition, message):
        if not condition:
            raise ValueError(message)
    namespace = {"__builtins__": __builtins__, "ev": ev, "array": array,
                 "math": math, "tau": tau, "DecodedClassifier": DecodedClassifier,
                 "OriginalObjectiveService": OriginalObjectiveService,
                 "_require": require, "CH_VALUES": (1024.0, 2048.0, 4096.0),
                 "ENCODINGS": ("unbalanced", "slack"), "Any": Any}
    module = ast.Module(body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0), *functions], type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, str(path), "exec"), namespace)
    return namespace


def row_key(row):
    return json.dumps([row.get("family"), row.get("condition"), row.get("coordinate"),
                       row.get("r"), row.get("grid"), row.get("comparator")],
                      sort_keys=True, separators=(",", ":"), default=str)


def sealed_coordinate(row, pair):
    return {"family": row["family"], "point": list(row["coordinate"]),
            "r_hex": float(row["r"]).hex(), "comparator": row["comparator"],
            "grid": row["grid"], "inactive_positive_zero": "no",
            **({"scale": row["scale"]} if "scale" in row else {}),
            "c_h": pair[0], "c_f": pair[1]}


def select_family(row):
    companion = "v14_" + row["scale"] if row["family"] == "v14" else row["family"]
    matches = [f for f in records.families(False) if f.group == row["family"]
               and f.companion == companion and f.r.hex() == float(row["r"]).hex()]
    if len(matches) != 1:
        raise ValueError("Baseline coordinate has no unique frozen family")
    return matches[0]


class ActualReference:
    """One actual transcript; at most one row/encoding energy stream cached."""
    def __init__(self, g4_instance, context, rows, coefficients, helpers):
        self.context, self.helpers = context, helpers
        self.rows, self.coefficients = rows, coefficients
        self.g4_instance = g4_instance
        first = ev.prepare_condition(g4_instance, "CSB", coefficients[0], context.lambda_ref)
        self.transcript = ev.prepare_transcript(first)
        if len(self.transcript) != 1 << len(g4_instance.tickers):
            raise ValueError("Actual reference decoded domain is incomplete")
        # Independently reduce the same frozen Python objective and feasibility.
        best = None
        feasible = 0
        for mask in range(len(self.transcript)):
            if ev.feasible_q(first, ev.mask_to_bits(mask, first.width())):
                feasible += 1
                value = self.transcript.f[mask]
                if best is None or value < best:
                    best = value
        if best is None or struct.pack(">d", best) != struct.pack(">d", context.f_star):
            raise ValueError("Actual reference optimum differs from verified preparation")
        self.feasible_count = feasible
        self._cached_key = None
        self._cached = None
        self.lookup = {}
        for i, row in enumerate(rows):
            for pair in harness.D015_COMPARATOR_PAIRS:
                coordinate = sealed_coordinate(row, pair)
                self.lookup[canonical(coordinate)] = i

    def __call__(self, coordinate, encoding):
        index = self.lookup.get(canonical(coordinate))
        if index is None or encoding not in ("unbalanced", "slack"):
            raise ValueError("Unrequested baseline reference coordinate")
        coefficients = self.coefficients[index]
        key = (canonical(coefficients), encoding)
        if key != self._cached_key:
            # Drop previous stream before materialising its replacement.
            self._cached = None
            condition = ev.prepare_condition(self.g4_instance, "CSB", coefficients, self.context.lambda_ref)
            values, owners, inactive = self.helpers["energy_stream"](condition, self.transcript, encoding)
            if inactive != 0 or not values:
                raise ValueError("Baseline stream must be nonempty and all-active")
            minimum = min(values)
            first = values.index(minimum)
            flags = self.helpers["tie_flags"](values, minimum, self.context.lambda_ref, first + 1)
            self._cached = (condition, values, owners, minimum, first, flags)
            self._cached_key = key
        condition, values, owners, minimum, first, flags = self._cached
        reconstruction = self.helpers["d015_reconstruction"](
            condition, owners, values, minimum, self.context.lambda_ref, self.context.f_star,
            (coordinate["c_h"], coordinate["c_f"]))
        return {"energy_minimum_words": [struct.pack(">d", minimum).hex()],
                "canonical_minimum_index": first, "tie_flags": flags,
                "d015_d016_reconstruction": reconstruction}


def build_actual_reference(*, instance, prepared_record, release_authority,
                           producer, library_path, expected_library_sha256,
                           helper_source_path, expected_helper_source_sha256,
                           independent_input_hashes, production_identity_hash):
    """Return xz seal bytes, exact open inputs, 12 device frames and evidence.

    producer is the independently pinned V6 module, already loaded by the parent.
    independent_input_hashes has exactly stage2_reference_seal.HASH_FIELDS.
    It must bind genuine instance content, prepared ledger and provenance, plus
    independently approved protocol/source/decision digests. No default pins.
    """
    if type(independent_input_hashes) is not dict or set(independent_input_hashes) != set(seal_api.HASH_FIELDS):
        raise ValueError("Exactly six independent seal input hashes required")
    inputs = {k: checked_hash(v) for k, v in independent_input_hashes.items()}
    identity = checked_hash(production_identity_hash)
    expected = {"instance_digest": prepared_record["instance"]["content_sha256"],
                "coefficient_ledger_digest": prepared_record["ledgers"]["d006_d008_d010_content_sha256"],
                "original_objective_digest": prepared_record["content_sha256"]}
    if any(inputs[k] != v for k, v in expected.items()):
        raise ValueError("Independent seal hashes do not bind actual preparation")
    helpers = load_frozen_helpers(helper_source_path, expected_helper_source_sha256)
    # V6 validates genuine preparation/release and qualified library BEFORE domain work.
    context = producer.create_verified_context(instance, prepared_record, release_authority,
                                              library_path, expected_library_sha256)
    payload = context.payload
    g4_instance = Instance(tuple(instance.order), tuple(tuple(v) for v in payload["sectors"]),
                           tuple(instance.mu), tuple(tuple(v) for v in instance.Sigma),
                           tuple(instance.p), float(instance.kappa), int(instance.K),
                           int(instance.C), float(instance.B))
    rows = [dict(row) for row in harness.build_validation_coordinates()]
    if len(rows) != 12 or any(row.get("condition") is not None for row in rows):
        raise ValueError("Expected exactly twelve unfired baseline rows")
    coefficients = [producer.extract_seven_coefficients(records.resolve_coefficients(
        select_family(row), tuple(row["coordinate"]), context.frozen)) for row in rows]
    reference = ActualReference(g4_instance, context, rows, coefficients, helpers)
    # Group by encoding within each row so each full stream serves all five pairs.
    coordinates = [{"coordinate": sealed_coordinate(row, pair), "encoding": encoding}
                   for row in rows for encoding in ("unbalanced", "slack")
                   for pair in harness.D015_COMPARATOR_PAIRS]
    seal_bytes = seal_api.seal(inputs, coordinates, identity, runner=reference)
    open_inputs = {**inputs, "production_identity_hash": identity, "coordinates": coordinates}
    g4 = {"tickers": list(g4_instance.tickers), "sectors": [list(v) for v in g4_instance.sectors],
          "mu": list(g4_instance.mu), "sigma": [list(v) for v in g4_instance.sigma],
          "prices": list(g4_instance.prices), "kappa_risk": g4_instance.kappa_risk,
          "K": g4_instance.K, "C": g4_instance.C, "B": g4_instance.B}
    frames = {}
    for row, coefficients_for_row in zip(rows, coefficients, strict=True):
        frame_row = {**row, "condition": None}
        frames[row_key(frame_row)] = {"row": frame_row, "payload": dict(payload),
            "records": [coefficients_for_row], "condition": "CSB", "instance": g4,
            "lambda_ref": context.lambda_ref, "f_star": context.f_star,
            "feasible_count": reference.feasible_count,
            "input_frame": frame_api.build_input_frame(payload, [coefficients_for_row], context.offsets_sha256)}
    return {"reference_bytes_xz": lzma.compress(seal_bytes), "seal_inputs": open_inputs,
            "frame_table": frames,
            "metadata": {"instance_id": context.instance_id,
                "prepared_record_sha256": context.prepared_record_sha256,
                "production_identity_hash": identity, "baseline_rows": len(rows),
                "comparison_count": len(coordinates), "d013_fired": False,
                "offsets_sha256": context.offsets_sha256,
                "reference_bytes_sha256": hashlib.sha256(seal_bytes).hexdigest(),
                "status": "candidate_requires_independent_review_and_actual_T4_crosscheck"}}


def open_compressed_reference(reference_bytes_xz, seal_inputs):
    """Exact existing v1 seal reader after standard lossless decompression."""
    return seal_api.open_for_session(lzma.decompress(reference_bytes_xz), seal_inputs)

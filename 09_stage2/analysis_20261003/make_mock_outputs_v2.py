#!/usr/bin/env python3
"""Synthesize a schema-valid MOCK Stage-2 output tree for five slots.

    python3 -B make_mock_outputs_v2.py --out <dir>

Every byte this writes is FABRICATED.  It exists so the pipeline can be run
end to end before the five real T4 kernels finish, and so that the negative
tests have something to tamper with.

WHAT IT WRITES, PER SLOT
------------------------
Under `<out>/slot<N>/`:

  `FULL_PRODUCTION_RESULT.json`  a complete-looking terminal artefact with the
        real `full_computation_complete_pending_final_audit` status word;
  `staged_qualified_sources/operational/BASELINE_RECEIPT.json`
  `staged_qualified_sources/operational/D013_TRIGGER.json`
  `staged_qualified_sources/research/g9/stage2_instances/.wp8c_session_stage2_0N.json`
  `staged_qualified_sources/research/g9/stage2_instances/stage2_0N/instance/PREPARED.json`
  `staged_qualified_sources/research/g9/stage2_instances/stage2_0N/sweep/<family>/`
      `range_plan.json`               the real canonical 4096-coord partition
      `ranges/<batch>/records.json`   the real WP4b projection
      `ranges/<batch>/RANGE_MANIFEST.json`
      `full_records/<batch>.jsonl.gz` real gzip framing, compresslevel=1, mtime=0
  `STAGE2_MOCK.json`                the marker the renderer and the analyzer
                                    read to label everything MOCK

The RECORDS are synthetic but STRUCTURALLY EXACT: they carry the real
`decisions_os/g9_stage2_coordinate_record/v1` key set
(`stage2_coordinate_records.py:911-931`), a real self-consistent
`content_sha256`, a real reconstruction of the frozen shape
(`stage2_cuda_reconstruct.py:196-214`), correct `r_hex`/mapping/group, and
coordinates that match their own linear index in the canonical last-axis-fastest
order.  Everything an integrity check can see is therefore genuinely satisfied.

WHAT IS FABRICATED
------------------
The A/B/C LABELS, the `Delta(r)` signs, the spatial predicates and therefore
every rate.  They are produced by a deterministic hash-based pseudo-label
function over `(slot, family, linear index)` — deliberately shaped so the mock
exercises BOTH branches of the D013 trigger (slots 1–3 all-positive, slots 4–5
firing), and so SLOT-2 sees both a box-shaped and a non-box A-region.

THE LABELS ARE NOT, AND CANNOT BE, A PREDICTION OF ANY REAL RESULT.  They carry
no information about the Stage-2 instance family.  They exist to prove the
plumbing, and every artefact downstream carries the literal `MOCK` token.

SIZE
----
The real census is 2,080,562 records per slot, which would take hours to
fabricate.  The mock uses a `--scale` divisor so the default tree is a few
thousand records per slot.  The mock's OWN plan is built with a matching
`max_coordinates_per_range` per batch, so its sealed ranges are internally
consistent; `verify_outputs_v2.py` then refuses it at the V4 census check, which
is CORRECT behaviour and is exercised by the negative tests.  To get a mock all
the way through the pipeline, pass `--scale 1`, which builds the full 2,080,562
records per slot.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import shutil
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import stage2_schema_v2 as schema  # noqa: E402

MOCK_MARKER_NAME = "STAGE2_MOCK.json"
MOCK_MARKER_SCHEMA = "decisions_os/g9_stage2_mock_marker/v1"

#: Records per sealed range in the MOCK tree.  The real value is
#: `MAX_COORDINATES_PER_RANGE = 4096`.  A smaller value keeps the fabricated
#: tree small while leaving the range-plan SHAPE (contiguous `[start, stop)`
#: from zero, 512-aligned) intact.
MOCK_RECORDS_PER_RANGE = schema.MOCK_RECORDS_PER_RANGE

#: The fabricated `Lambda_ref`.  Rescaled by the primary `c_H` so the D015
#: cells' `tau` follows the frozen formula's `c_H` dependence exactly.
MOCK_LAMBDA_REF = 0.125

#: A precomputed pool of well-formed lowercase SHA-256 strings for the mock
#: `commitments` fields.  Hashing ten small payloads per record over 2,080,562
#: records is pure overhead: the values are FABRICATED either way, and the
#: analyzer never re-derives them.  They are still correctly SHAPED, so a
#: structural check that inspects them still behaves as it would on real data.
_DIGEST_POOL: tuple[str, ...] = tuple(
    hashlib.sha256(f"MOCK_COMMITMENT_{index}".encode("ascii")).hexdigest()
    for index in range(256))


def _pair_of(key: str) -> tuple[int, int]:
    """Parse a frozen `c_H=<n>__c_f=<n>` diagnostic key (stage2_cuda_reconstruct.py:962-972)."""
    head, _, tail = key.partition("__c_f=")
    return int(head[len("c_H="):]), int(tail)


def _hex(value: int) -> str:
    return f"0x{(value & ((1 << 64) - 1)):#018x}"


def _digest(payload: Any) -> str:
    return hashlib.sha256(schema.canonical_bytes(payload)).hexdigest()


def sealed(payload: dict[str, Any]) -> dict[str, Any]:
    body = dict(payload)
    body["content_sha256"] = schema.content_sha256(body)
    return body


def _r_ordinal(family_key: str) -> int:
    """0, 1 or 2 for the primary `r = 0.5, 1.0, 2.0`; 1 for every r=1 companion."""
    r_hex = schema.FAMILY_R_HEX[family_key]
    return {schema.PRIMARY_R_HEX[0]: 0,
            schema.PRIMARY_R_HEX[1]: 1,
            schema.PRIMARY_R_HEX[2]: 2}[r_hex]


def _fake_label(slot: int, family_key: str, linear: int, encoding: str) -> str:
    """A deterministic, fabricated A/B/C label.  NOT A PREDICTION OF ANYTHING.

    The shape is chosen to exercise the pipeline, not to resemble a result:
    slack recovers more often than unbalanced (so `Delta > 0`), and the last
    slot's families are forced to a mixed sign so the D013 trigger FIRES there.
    """
    seed = (slot * 1_000_003 + hash_family(family_key) * 7_919
            + linear * 131 + (0 if encoding == "slack" else 1))
    value = seed % 1000
    if encoding == "slack":
        if value < 320:
            return "A"
        return "C"
    if slot >= 4:
        # Force a mixed sign across r so the exact-sign trigger fires.
        return "A" if (linear + _r_ordinal(family_key)) % 97 == 0 else "B"
    if value < 90:
        return "A"
    if value < 320:
        return "B"
    return "C"


def hash_family(family_key: str) -> int:
    return int(hashlib.sha256(family_key.encode("ascii")).hexdigest()[:8], 16)


def _cell_summary(slot: int, family_key: str, linear: int, encoding: str,
                  c_h: int, c_f: int) -> dict[str, Any]:
    """A summary of the frozen shape (`stage2_cuda_reconstruct.py:196-214`).

    Every value is internally consistent with the label the point actually
    receives, so the analyzer's consistency checks (`atomic counts sum to
    X_E_size`, `set_label` derivation, `p_*` numerators, `I_C_*` indicators)
    all pass on genuine structure rather than on a bypass.
    """
    label = _fake_label(slot, family_key, linear, encoding)
    x_size = 1 + (linear % 3)
    counts = {"A": 0, "B": 0, "C": 0}
    counts[label] = x_size
    t_size = x_size + (linear % 2)
    minimum = -(1.0 + (linear % 7) * 0.5)
    tau = ((c_h * (2.0 ** -52)) * (0.125 + abs(minimum)))
    return {
        "c_H": c_h, "c_f": c_f,
        "H_E_min_hex": float(minimum).hex(),
        "H_E_min_domain_index": linear % 1048576,
        "tie_comparator": {"c_H": c_h, "epsilon_hex": float(2.0 ** -52).hex(),
                           "minimum_tau_hex": float(tau).hex(),
                           "lambda_ref_hex": float(MOCK_LAMBDA_REF).hex()},
        "T_E_size": t_size, "X_E_size": x_size,
        "commitments": {
            "T_E_domain_index_stream_sha256": _DIGEST_POOL[linear & 255],
            "X_E_decoded_index_stream_sha256": _DIGEST_POOL[(linear + 97) & 255],
            "T_E_first_index": linear, "T_E_last_index": linear + t_size - 1,
        },
        "set_label": label,
        "atomic_counts": counts,
        "atomic_label_set": sorted(counts),
        "I_C_exist": int(counts["C"] > 0),
        "I_C_univ": int(counts["C"] == x_size),
        "p_A": [counts["A"], x_size],
        "p_B": [counts["B"], x_size],
        "p_C": [counts["C"], x_size],
    }


def build_record(slot: int, family_key: str, linear: int,
                 coordinate: dict[str, int]) -> dict[str, Any]:
    """One committed record of the exact frozen schema.

    The four D015 diagnostic cells are DERIVED from the primary cell by
    re-reading the label through the diagnostic `c_H`, so they carry the same
    label the point actually has.  That keeps the fabricated tree cheap (the
    cell-shape work is done once per point, not five times) while every cell
    remains internally consistent under its own comparator.
    """
    group = schema.FAMILY_GROUP[family_key]
    primary = {encoding: _cell_summary(slot, family_key, linear, encoding,
                                       schema.PRIMARY_C_H, schema.PRIMARY_C_F)
               for encoding in schema.ENCODINGS}
    diagnostics = {}
    for key in schema.D015_DIAGNOSTIC_KEYS:
        c_h, c_f = _pair_of(key)
        diagnostics[key] = {
            encoding: _diagnostic_cell(primary[encoding], c_h, c_f)
            for encoding in schema.ENCODINGS}
    body = {
        "schema": schema.RECORD_SCHEMA,
        "family": family_key,
        "group": group,
        "companion": ("primary" if group == "primary"
                      else "d011" if group == "d011" else "v14"),
        "condition": None,
        "r_hex": schema.FAMILY_R_HEX[family_key],
        "mapping": "d011_cm" if group == "d011" else "d006_r1",
        "coordinate": dict(coordinate),
        "coordinate_label": "|".join(f"{axis}={coordinate[axis]}"
                                     for axis in sorted(coordinate)),
        "coordinate_binary64_hex": {
            axis: _hex(0x3FF0000000000000 + value) for axis, value in coordinate.items()
        },
        "linear_index": linear,
        "coefficients": {
            "cardinality": {"active": True, "alpha_hex": float(0.5).hex()},
            "sector": {"active": True, "a_hex": float(0.25).hex(),
                       "lambda_slack_hex": float(0.5).hex(),
                       "lambda_1_hex": float(0.25).hex(),
                       "lambda_2_hex": float(0.03125).hex()},
            "budget": {"active": True, "a_hex": float(0.25).hex(),
                       "lambda_slack_hex": float(12.5).hex(),
                       "lambda_1_hex": float(2.5).hex(),
                       "lambda_2_hex": float(0.3125).hex()},
        },
        "reconstruction": {
            schema.PRIMARY_SUMMARY_KEY: primary,
            "d015_diagnostics": diagnostics,
        },
    }
    record = dict(body)
    record["content_sha256"] = _digest(body)
    return record


def _diagnostic_cell(primary: dict[str, Any], c_h: int, c_f: int) -> dict[str, Any]:
    """Re-read the primary cell's label under a different `(c_H, c_f)` pair.

    The label is carried over unchanged; only the comparator identity and the
    tie tolerance, which the frozen formula makes a function of `c_H` alone
    (`stage2_cuda_reconstruct.py:192-193`), are recomputed.  The structural
    checks the analyzer applies therefore all hold.
    """
    cell = dict(primary)
    cell["c_H"] = c_h
    cell["c_f"] = c_f
    comparator = dict(cell["tie_comparator"])
    tau = ((c_h * (2.0 ** -52)) * abs(float.fromhex(comparator["minimum_tau_hex"]))
           / ((schema.PRIMARY_C_H * (2.0 ** -52)) * MOCK_LAMBDA_REF))
    comparator["c_H"] = c_h
    comparator["minimum_tau_hex"] = float(tau).hex()
    cell["tie_comparator"] = comparator
    return cell


def _coordinate(linear: int, axis_length: int) -> dict[str, int]:
    card, remainder = divmod(linear, axis_length * axis_length)
    sector, budget = divmod(remainder, axis_length)
    return {"ell_card": card, "ell_sector": sector, "ell_budget": budget}


def build_mock_plan(family_key: str, total: int, identity: str,
                    records_per_range: int) -> dict[str, Any]:
    """The canonical partition, exactly as the frozen contract builds it."""
    ranges = []
    start = 0
    ordinal = 0
    while start < total:
        stop = min(start + records_per_range, total)
        ranges.append({"batch_id": f"{family_key}_b{ordinal:04d}",
                       "start": start, "stop": stop})
        start, ordinal = stop, ordinal + 1
    return sealed({
        "schema": schema.RANGE_PLAN_SCHEMA,
        "family": family_key,
        "total_coordinates": total,
        "max_coordinates_per_range": records_per_range,
        "qualification_identity_sha256": identity,
        "ranges": ranges,
    })


def build_manifest(plan: dict[str, Any], batch_id: str,
                   records_file_sha256: str,
                   records_content_sha256: str) -> dict[str, Any]:
    row = next(r for r in plan["ranges"] if r["batch_id"] == batch_id)
    return sealed({
        "schema": schema.RANGE_MANIFEST_SCHEMA,
        "batch_id": batch_id,
        "start": row["start"], "stop": row["stop"],
        "plan_content_sha256": plan["content_sha256"],
        "qualification_identity_sha256": plan["qualification_identity_sha256"],
        "records_file_sha256": records_file_sha256,
        "records_content_sha256": records_content_sha256,
        "status": "complete",
    })


def project(record: dict[str, Any], identity: str) -> dict[str, Any]:
    """The WP4b projection, byte-identical to `project_record_for_writer`."""
    coordinate = record["coordinate"]
    return {
        "coordinates": [coordinate[axis] for axis in sorted(coordinate)],
        "result": {"identity_sha256": identity,
                   "record_content_sha256": record["content_sha256"]},
    }


def _axis_for(coordcount: int) -> int:
    """The integer cube root, by integer arithmetic only.

    Under the unscaled census the count is exactly `axis**3` and this returns
    the real axis, so the mock's lattice is the real one.  The census profile
    derives its coordinate counts the same way (`stage2_schema_v2.
    build_census_profile`), so the mock and the verifier always agree.
    """
    if coordcount < 1:
        return 1
    low, high = 1, 1
    while high ** 3 <= coordcount:
        high *= 2
    while low + 1 < high:
        middle = (low + high) // 2
        if middle ** 3 <= coordcount:
            low = middle
        else:
            high = middle
    return low


def write_family(family_root: Path, slot: int, family_key: str,
                 identity: str, records_per_range: int,
                 coordinate_count: int) -> int:
    axis_length = _axis_for(coordinate_count)
    total = axis_length ** 3
    family_root.mkdir(parents=True, exist_ok=True)
    plan = build_mock_plan(family_key, total, identity, records_per_range)
    (family_root / schema.PLAN_NAME).write_bytes(schema.canonical_bytes(plan))

    ranges_dir = family_root / schema.RANGES_DIRNAME
    full_dir = family_root / schema.FULL_RECORDS_DIRNAME
    ranges_dir.mkdir(exist_ok=True)
    full_dir.mkdir(exist_ok=True)

    for row in plan["ranges"]:
        batch = row["batch_id"]
        records = [build_record(slot, family_key, linear,
                                _coordinate(linear, axis_length))
                   for linear in range(row["start"], row["stop"])]
        raw = b"".join(schema.canonical_bytes(rec) + b"\n" for rec in records)
        # The exact framing production writes (wp8c_streaming_session_v3_gzip.py:53).
        (full_dir / f"{batch}.jsonl.gz").write_bytes(
            gzip.compress(raw, compresslevel=1, mtime=0))
        projected = [project(rec, identity) for rec in records]
        body = schema.canonical_bytes(projected)
        batch_dir = ranges_dir / batch
        batch_dir.mkdir(exist_ok=True)
        (batch_dir / schema.RECORDS_NAME).write_bytes(body)
        manifest = build_manifest(plan, batch, _digest_of(body),
                                  _digest_of(projected))
        (batch_dir / schema.RANGE_MANIFEST_NAME).write_bytes(
            schema.canonical_bytes(manifest))
    return total


def _digest_of(value: Any) -> str:
    raw = value if isinstance(value, bytes) else schema.canonical_bytes(value)
    return hashlib.sha256(raw).hexdigest()


def write_slot(out_dir: Path, slot: int, records_per_range: int,
               scale: int) -> dict[str, Any]:
    """One complete mock slot tree."""
    profile = schema.build_census_profile(records_per_range, schema.FAMILY_CENSUS,
                                          "MOCK_SYNTHETIC_NOT_A_RESULT",
                                          scale=scale)
    counts = {key: entry["coordinates"]
              for key, entry in profile["family_census"].items()}
    name = schema.SLOT_NAMES[slot - 1]
    # One downloaded kernel output = ONE slot.  Each slot therefore gets its own
    # `slotN/` directory, exactly as `push/<kernel-id>/results/` does in
    # production; sharing one staged tree across slots would put five instance
    # directories in one download and `find_slot_dir` correctly refuses that.
    slot_out = out_dir / f"slot{slot}"
    staged = slot_out / "staged_qualified_sources"
    instances = staged / schema.INSTANCE_ROOT
    slot_dir = instances / name
    slot_dir.mkdir(parents=True, exist_ok=True)

    identity = _digest({"mock_slot": slot, "accepted_identity": name})

    (slot_dir / "instance").mkdir(parents=True, exist_ok=True)
    prepared = sealed({"instance_id": name, "slot": slot,
                       "layout_kind": "MOCK_drawn_production_layout",
                       "prepared_record_status": "MOCK",
                       "coordinate_count": 61})
    (slot_dir / "instance/PREPARED.json").write_bytes(
        schema.canonical_bytes(prepared))
    # The D013 trigger must name PREPARED.json's OWN content hash
    # (full_production_parent_v2.py:88), so it is read back from the file that
    # was just written rather than recomputed from the same inputs.
    prepared_sha = schema.read_sealed(
        slot_dir / "instance/PREPARED.json", "mock PREPARED")["content_sha256"]

    families: dict[str, int] = {}
    for family_key in schema.BASELINE_FAMILIES:
        families[family_key] = write_family(
            slot_dir / "sweep" / family_key, slot, family_key, identity,
            records_per_range, counts[family_key])

    (instances / schema.SESSION_STATE_NAME.format(slot_name=name)).write_bytes(
        schema.canonical_bytes(sealed({
            "schema": schema.SESSION_STATE_SCHEMA, "status": "complete",
            "session_id": f"MOCK_{name}", "slot": name, "instance_id": name,
            "identity_sha256": identity,
            "session_contract_sha256": _digest({"mock_contract": name}),
            "promoted_range_batch_ids": [],
        })) + b"\n")

    operational = staged / "operational"
    operational.mkdir(parents=True, exist_ok=True)
    sessions = []
    for family_key in schema.BASELINE_FAMILIES:
        sessions.append(sealed({
            "family": family_key, "status": "complete_pending_image_audit",
            "slot": name, "instance_id": name,
            "sealed_range_plan_content_sha256": _digest({"plan": family_key}),
        }))
    (operational / "BASELINE_RECEIPT.json").write_bytes(
        schema.canonical_bytes(sealed({
            "status": schema.BASELINE_COMPLETE_STATUS,
            "full_package_complete": False, "instance_id": name,
            "wp3_record_content_sha256": _digest({"wp3": name}),
            "family_sessions": sessions,
        })))

    # Slots 1-3 keep all-positive Delta signs; slots 4-5 fire the trigger, so
    # the mock tree exercises BOTH branches of the exact-sign rule.
    fired = slot >= 4
    (operational / "D013_TRIGGER.json").write_bytes(
        schema.canonical_bytes(sealed({
            "instance_id": name, "prepared_record_sha256": prepared_sha,
            "counts": {"primary_streams": 3, "coordinates": schema.PER_SLOT_ROWS},
            "primary_record_stream_sha256": _digest({"stream": name}),
            "fired": fired,
        })))

    # The kernel writes its terminal artefact into /kaggle/working, i.e. the
    # slot's OWN output directory, which is the PARENT of staged_qualified_sources
    # (kernel.py:56).  It is therefore placed at <staged>/ so that
    # verify_outputs_v2.py finds it exactly where a real download would put it.
    (staged / schema.RESULT_NAME).write_bytes(json.dumps({
        "status": schema.FULL_COMPLETE_STATUS, "accepted": False,
        "instance_id": name, "d013_fired": fired,
        "conditional_families_run": 22 if fired else 0,
        "trigger_sha256": _digest({"trigger": name}),
        "wall_seconds": 0,
        "MOCK": True,
    }, indent=2).encode("ascii") + b"\n")

    return {"slot": slot, "instance_id": name, "identity": identity,
            "prepared_record_sha256": prepared_sha, "d013_fired": fired,
            "rows": sum(families.values()), "families": families}


def write_marker(out_dir: Path, slots: list[dict[str, Any]],
                 records_per_range: int, scale: int) -> None:
    profile = schema.build_census_profile(
        records_per_range, schema.FAMILY_CENSUS,
        "MOCK_SYNTHETIC_NOT_A_RESULT", scale=scale)
    payload = sealed({
        "schema": MOCK_MARKER_SCHEMA,
        "MOCK": True,
        "label": schema.MOCK_LABEL,
        "statement": "EVERY NUMBER IN THIS TREE IS FABRICATED. It is produced "
                     "by make_mock_outputs_v2.py to exercise the analysis pipeline "
                     "before the five real T4 production slots finish. No value "
                     "here is a scientific result, a prediction, or an estimate "
                     "of any real Stage-2 quantity.",
        "differences_from_the_real_census": [
            f"every family's coordinate count is divided by scale={scale}, so "
            f"this tree carries {profile['per_slot_rows']:,} records per slot "
            f"instead of the real {schema.PER_SLOT_ROWS:,}",
            f"the sealed partition width is {records_per_range} records per "
            f"range instead of the real {schema.MAX_COORDINATES_PER_RANGE}",
            "every A/B/C label, Delta sign and spatial predicate is fabricated "
            "by a hash function over (slot, family, linear index) and carries "
            "no information about any real Stage-2 quantity",
        ],
        "census_profile": profile,
        "slots": slots,
    })
    for slot in slots:
        slot_dir = out_dir / f"slot{slot['slot']}"
        slot_dir.mkdir(parents=True, exist_ok=True)
        (slot_dir / MOCK_MARKER_NAME).write_bytes(
            schema.canonical_bytes(payload) + b"\n")
    (out_dir / MOCK_MARKER_NAME).write_bytes(
        schema.canonical_bytes(payload) + b"\n")


def build(out_dir: Path, slots: list[int], records_per_range: int,
          scale: int) -> dict[str, Any]:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    summaries = [write_slot(out_dir, slot, records_per_range, scale)
                 for slot in slots]
    write_marker(out_dir, summaries, records_per_range, scale)
    return {"out": str(out_dir), "slots": summaries,
            "records_per_range": records_per_range, "scale": scale}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Synthesize a schema-valid MOCK five-slot output tree.")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--slots", default="1,2,3,4,5",
                        help="Which slots to synthesize (default all five).")
    parser.add_argument("--records-per-range", type=int,
                        default=schema.MOCK_RECORDS_PER_RANGE,
                        help="Sealed partition width. The REAL width is "
                             f"{schema.MAX_COORDINATES_PER_RANGE}.")
    parser.add_argument("--scale", type=int, default=1,
                        help="Divide every family's coordinate count by this. "
                             "1 is the REAL census: 2,080,562 records per slot, "
                             "about 1.4 GB and 15 minutes per slot of "
                             "generation. Anything above 1 produces a SMALLER, "
                             "explicitly non-frozen census that is recorded as "
                             "such in every artefact it produces.")
    args = parser.parse_args(argv)
    if args.scale < 1:
        sys.stderr.write("--scale must be >= 1\n")
        return 2
    slots = [int(value) for value in args.slots.split(",") if value.strip()]
    summary = build(args.out, slots, args.records_per_range, args.scale)
    print(f"wrote MOCK tree at {summary['out']} "
          f"(records_per_range={summary['records_per_range']}, "
          f"scale={summary['scale']})")
    for slot in summary["slots"]:
        print(f"  slot {slot['slot']} ({slot['instance_id']}): "
              f"{slot['rows']:,} records, D013 fired={slot['d013_fired']}")
    print(f"real per-slot census for comparison: {schema.PER_SLOT_ROWS:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
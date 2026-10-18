#!/usr/bin/env python3
"""Hardware-free, corpus-free fixtures for the Gate-6 rate-surface/D013 aggregate producer.

Never reads accepted Gate-5 or V-14 data: the ratified Gate-5 loader is stubbed to raise for the whole
run, V-14 inputs are synthetic sealed sets in a temporary directory, and no artifact is written.  Covers
the D013 truth table and strict six-cell input, authority and plan pinning, V-14 root membership,
TOCTOU/rehash tampering of consumed records.json bytes, semantic record rejection, exact/no-float
output, and read-only plan mode under normal and -O Python.
"""
from __future__ import annotations

import copy
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from research.g6 import rate_surface_and_d013 as m  # noqa: E402

RUNNER = ROOT / "research/g6/run_rate_surface_and_d013.py"
SLACK_ENTRIES = 1048576


class FixtureError(RuntimeError):
    pass


def require(ok: bool, msg: str) -> None:
    if not ok:
        raise FixtureError(msg)


def rejected(fn, name: str) -> None:
    try:
        fn()
    except m.RateSurfaceError:
        return
    except Exception as exc:  # any raw exception is itself a failure of fail-closed typing
        raise FixtureError(f"{name} raised a raw {type(exc).__name__} instead of RateSurfaceError") from exc
    raise FixtureError(f"{name} was accepted")


def production_guard_calls() -> list:
    return PRODUCTION_CALLS


PRODUCTION_CALLS: list[str] = []


def _forbidden(*_args, **_kwargs):
    PRODUCTION_CALLS.append("called")
    raise FixtureError("production Gate-5 loader invoked during fixtures")


def rows(signs) -> list[dict]:
    out = []
    for r, d in zip(m.R_HEX, signs, strict=True):
        for encoding, offset in (("unbalanced", 0), ("slack", d)):
            out.append({"source": m.GATE5_SOURCE, "r_hex": r, "encoding": encoding, "coordinate_count": m.GATE5_SLICE,
                        "set_label_counts": {"A": 10 + offset, "B": m.GATE5_SLICE - 10 - offset, "C": 0},
                        "rho_E_exact": {"numerator": 10 + offset, "denominator": m.GATE5_SLICE},
                        "I_C_exist_count": 0, "I_C_univ_count": 0,
                        "mean_p": {x: {"numerator": 0, "denominator": 1} for x in "ABC"}})
    return out


def check_d013() -> None:
    require(m.d013_disposition(rows([1, 2, 3]))["disposition"] == "does_not_fire", "positive D013 truth table")
    require(m.d013_disposition(rows([-1, -2, -3]))["disposition"] == "does_not_fire", "negative D013 truth table")
    require(m.d013_disposition(rows([1, -2, 3]))["disposition"] == "fires", "mixed D013 truth table")
    require(m.d013_disposition(rows([1, 0, 3]))["disposition"] == "fires", "zero D013 truth table")
    require(m.d013_disposition(rows([0, 0, 0]))["disposition"] == "fires", "all-zero D013 truth table")
    require(m.d013_disposition(rows([1, 2, 3]))["required_conditions"] == [] and m.d013_disposition(rows([1, 0, 3]))["required_conditions"] == ["C", "CB", "CS", "CSB"],
            "D013 condition package drift")
    require([d["numerator"] for d in m.d013_disposition(rows([1, -2, 3]))["differences"]] == [1, -2, 3], "D013 differences drift")
    good = rows([1, 2, 3])
    rejected(lambda: m.d013_disposition(good[:-1]), "five series")
    rejected(lambda: m.d013_disposition(good + [good[0]]), "seven series")
    rejected(lambda: m.d013_disposition(good[:-1] + [good[0]]), "duplicate cell with a missing cell")
    rejected(lambda: m.d013_disposition(tuple(good)[:5] + ({**good[5], "encoding": "unbalanced"},)), "duplicate cell")
    rejected(lambda: m.d013_disposition([{**e, "source": "v14"} for e in good]), "wrong source")
    rejected(lambda: m.d013_disposition([{**e, "condition": {"c_H": 2048, "c_f": 2048}} for e in good]), "condition present")
    rejected(lambda: m.d013_disposition([{**e, "r_hex": (4.0).hex()} if i == 0 else e for i, e in enumerate(good)]), "r outside the family")
    rejected(lambda: m.d013_disposition([{**e, "encoding": "hybrid"} if i == 0 else e for i, e in enumerate(good)]), "unknown encoding")
    for label, rational in (("bool denominator", {"numerator": 1, "denominator": True}), ("float numerator", {"numerator": 1.0, "denominator": 3}),
                            ("negative numerator", {"numerator": -1, "denominator": 3}), ("numerator above denominator", {"numerator": 4, "denominator": 3}),
                            ("zero denominator", {"numerator": 0, "denominator": 0}), ("extra key", {"numerator": 1, "denominator": 3, "value": 0}),
                            ("missing key", {"numerator": 1}), ("string rational", "1/3"), ("list rational", [1, 3]), ("none rational", None)):
        bad = copy.deepcopy(good)
        bad[0]["rho_E_exact"] = rational
        rejected(lambda: m.d013_disposition(bad), label)
    bad = copy.deepcopy(good); bad[1]["rho_E_exact"]["denominator"] = m.GATE5_SLICE - 1
    rejected(lambda: m.d013_disposition(bad), "denominator mismatch")
    bad = copy.deepcopy(good); bad[2]["coordinate_count"] = m.GATE5_SLICE + 1
    rejected(lambda: m.d013_disposition(bad), "coordinate count drift")
    bad = copy.deepcopy(good); bad[3]["extra"] = 1
    rejected(lambda: m.d013_disposition(bad), "extra series key")
    bad = copy.deepcopy(good); del bad[3]["mean_p"]
    rejected(lambda: m.d013_disposition(bad), "missing series key")
    for raw in (None, "series", 6, {"a": 1}, [None] * 6, ["x"] * 6, [1, 2, 3, 4, 5, 6]):
        rejected(lambda r=raw: m.d013_disposition(r), f"raw input {type(raw).__name__}")


def check_aggregation_and_output() -> None:
    cert = {"tie_comparator": {"c_H": 2048}, "X_E_size": 2, "X_E": [{"atomic_label": "A"}, {"atomic_label": "B"}], "set_label": "B"}
    require(m._gate5_summary(cert)["atomic_counts"] == {"A": 1, "B": 1, "C": 0}, "D016 census")
    rejected(lambda: m._gate5_summary({**cert, "set_label": "A"}), "D016 label drift")
    rejected(lambda: m._gate5_summary({**cert, "tie_comparator": {"c_H": 1024}}), "non-primary comparator")
    rejected(lambda: m._gate5_summary({**cert, "X_E_size": 3}), "X_E size drift")
    rejected(lambda: m._gate5_summary({**cert, "X_E": [{"atomic_label": "A"}, {"label": "B"}]}), "unlabeled decoded member")
    bucket = m._new()
    m._add(bucket, {"set_label": "B", "atomic_counts": {"A": 1, "B": 2, "C": 0}, "X_E_size": 3})
    m._add(bucket, {"set_label": "A", "atomic_counts": {"A": 2, "B": 0, "C": 0}, "X_E_size": 2})
    rendered = m._render(bucket)
    require(rendered["rho_E_exact"] == {"numerator": 1, "denominator": 2} and rendered["mean_p"]["A"] == {"numerator": 2, "denominator": 3}
            and rendered["set_label_counts"] == {"A": 1, "B": 1, "C": 0}, "exact aggregation drift")
    rejected(lambda: m._add(m._new(), {"set_label": "A", "atomic_counts": {"A": 1, "B": 1, "C": 0}, "X_E_size": 2}), "label/census drift")
    rejected(lambda: m._add(m._new(), {"set_label": "AB", "atomic_counts": {"A": 1, "B": 1, "C": 0}, "X_E_size": 2}), "substring label")
    rejected(lambda: m._add(m._new(), {"set_label": "B", "atomic_counts": {"A": 1.0, "B": 1, "C": 0}, "X_E_size": 2}), "float count")
    rejected(lambda: m._add(m._new(), {"set_label": "B", "atomic_counts": {"A": True, "B": 1, "C": 0}, "X_E_size": 2}), "bool count")
    rejected(lambda: m._no_float_or_bool({"x": 1.0}), "float output")
    rejected(lambda: m._no_float_or_bool({"x": [False]}), "bool output")
    # Gate-5 coverage: full synthetic key set is heavy; prove duplicate and out-of-grid refusal, then exact coverage with a tiny axis stub.
    record = {"key": {"r_hex": m.R_HEX[0], "ell_card": 0, "ell_sector": 0, "ell_budget": 0},
              "unbalanced": cert, "slack": cert}
    rejected(lambda: m.aggregate_gate5([record, record]), "duplicate Gate-5 coordinate")
    rejected(lambda: m.aggregate_gate5([{**record, "key": {**record["key"], "ell_card": 61}}]), "coordinate outside the grid")
    rejected(lambda: m.aggregate_gate5([{**record, "key": {**record["key"], "ell_card": 1.0}}]), "float coordinate")
    rejected(lambda: m.aggregate_gate5([{**record, "key": {**record["key"], "r_hex": (4.0).hex()}}]), "r outside the population")
    rejected(lambda: m.aggregate_gate5([record]), "incomplete Gate-5 coverage")
    rejected(lambda: m.aggregate_gate5(["not a record"]), "non-object record")


def check_authorities() -> None:
    require(m.bind_authorities() == m.AUTHORITIES, "authority binding drift")
    original = dict(m.AUTHORITIES)
    try:
        m.AUTHORITIES["research/decisions/DECISIONS.md"] = "0" * 64
        rejected(m.bind_authorities, "drifted DECISIONS.md pin")
        m.AUTHORITIES.update(original)
        m.AUTHORITIES["research/00_specifications/FROZEN_MATH_SPEC.md"] = "0" * 64
        rejected(m.bind_authorities, "drifted FROZEN_MATH_SPEC.md pin")
    finally:
        m.AUTHORITIES.clear()
        m.AUTHORITIES.update(original)
    require(m.AUTHORITIES["research/decisions/DECISIONS.md"] == "274c6cd92d4958957d125efc7ae2ddb6f40629eb78b7c2e2be99224e038ce849"
            and m.AUTHORITIES["research/00_specifications/FROZEN_MATH_SPEC.md"] == "e963a7e10ba797a373ef50d585bec1056ee82f7274d762b7c8bab9a817062900"
            and m.ACCEPTED_V14_PLANS == {"0.5x": "e5b44620206e5bbaca3a03e890a4f99b4f29a23b87d3e2d4f8f8be2c3067d71d",
                                         "2x": "38c01eff5a313273fc106a5f5c39760628e59132b9a7a72e0176b37aa1897748"}, "pin constants drift")


class FakeCache:
    """Entry e <-> decoded index e with a fixed lift, mirroring the accepted one-lift-per-mask cache shape."""

    def __init__(self):
        from src.g5.domains import BinaryDomain
        self.domain = BinaryDomain(20)

    def __getitem__(self, entry):
        return self.domain[entry], (0,) * 19

    def __len__(self):
        return SLACK_ENTRIES


def synthetic_v14_set(directory: Path, scale: str, total: int, batch_sizes: list[int], plan_sha: str, ledgers, inputs) -> tuple[Path, Path, dict]:
    """A synthetic sealed set: plan + batch dirs with semantically valid records; returns (plan_path, root, plan)."""
    core = m.core
    ledger = ledgers[scale]
    classifiers = core.build_classifiers(core.engine.load_instance(ROOT / core.engine.INSTANCE_REL), inputs["lambda_ref"])
    cache = FakeCache()
    point = core.engine.validation_points(ledgers)[0 if scale == "0.5x" else 4]
    device = {"unbalanced": {"h_min_bits": core.engine.float_bits(-1.5), "h_min_index": 77, "entries": [(5, 7), (77, 7), (4096, 7)]},
              "slack": {"h_min_bits": core.engine.float_bits(-2.25), "h_min_index": 3, "entries": [(3, 7), (77, 7)]}}
    template = core.coordinate_record(point, ledger, device, cache, classifiers, inputs["f_star"], inputs["lambda_ref"])
    axis = core.engine.SCALES[scale]["axis_count"]
    batches, start = [], 0
    for index, size in enumerate(batch_sizes):
        batches.append({"batch_id": f"synthetic_{scale}_b{index:04d}", "index": index, "start": start, "stop": start + size, "count": size})
        start += size
    require(start == total, "synthetic batch sizes must tile the total")
    plan = {"schema": m.contract.SCHEMA_PLAN, "scale": scale, "pass_id": core.engine.SCALES[scale]["pass_id"],
            "grid": {"axis_count": axis, "total_coordinates": total, "axis_index_range": [0, axis]},
            "classifier": {"lambda_ref_hex": inputs["lambda_ref_hex"]},
            "core_validation_identity": {"domain": {"slack": {"entries": SLACK_ENTRIES}}}, "batches": batches}
    plan["content_sha256"] = m.contract.content_sha256(plan)
    require(plan["content_sha256"] == plan_sha or plan_sha == "", "synthetic plan hash drift")
    plan_path = directory / f"plan_{scale}.json"
    plan_path.write_bytes(m.canonical_bytes(plan))
    root = directory / f"artifacts_{scale}"
    root.mkdir()
    for batch in batches:
        records = []
        for linear in range(batch["start"], batch["stop"]):
            card, sector, budget = core.engine.coordinate_at(linear, axis)
            coefficients = core.engine.coefficients_at(ledger, card, sector, budget)
            records.append({"key": {"ell_card": card, "ell_sector": sector, "ell_budget": budget,
                                    "s_card_hex": ledger["coordinates"][card]["binary64_hex"],
                                    "s_sector_hex": ledger["coordinates"][sector]["binary64_hex"],
                                    "s_budget_hex": ledger["coordinates"][budget]["binary64_hex"]},
                            "linear": linear, "scale": scale, "pass_id": plan["pass_id"],
                            "coefficients_hex": {name: value.hex() for name, value in asdict(coefficients).items()},
                            "commitment_descriptors": template["commitment_descriptors"],
                            "primary_c_h_2048": template["primary_c_h_2048"], "d015_diagnostics": template["d015_diagnostics"]})
        payload = {"schema": core.SCHEMA_RECORDS, "batch_id": batch["batch_id"], "plan_content_sha256": plan["content_sha256"],
                   "pass_id": plan["pass_id"], "scale": scale, "range": {"start": batch["start"], "stop": batch["stop"], "count": batch["count"]},
                   "linear_order": core.engine.LINEAR_ORDER, "record_count": len(records), "records": records, "release_review_id": "review-x",
                   "core_validation_identity_sha256": "f" * 64}
        payload["content_sha256"] = core.content_sha256(payload)
        (root / batch["batch_id"]).mkdir()
        (root / batch["batch_id"] / "records.json").write_bytes(core.canonical_bytes(payload))
        (root / batch["batch_id"] / "manifest.json").write_bytes(b"{}")
    return plan_path, root, plan


def fake_audit_from_disk(plan: dict, root: Path) -> dict:
    """Mimic the reviewed audit's receipt shape from the current on-disk bytes (the audit's own read)."""
    batches = []
    for batch in plan["batches"]:
        raw = (root / batch["batch_id"] / "records.json").read_bytes()
        content = json.loads(raw)
        batches.append({"batch_id": batch["batch_id"], "path": str(root / batch["batch_id"]),
                        "range": {"start": batch["start"], "stop": batch["stop"], "count": batch["count"]},
                        "records_file_sha256": hashlib.sha256(raw).hexdigest(), "records_content_sha256": content["content_sha256"],
                        "record_count": batch["count"]})
    receipt = {"schema": "synthetic-audit", "verdict": "accepted", "plan_content_sha256": plan["content_sha256"], "batches": batches}
    receipt["content_sha256"] = m.contract.content_sha256(receipt)
    return receipt


def reseal_records(path: Path, mutate) -> None:
    """Tamper a record and rehash records.json consistently (the TOCTOU/rehash adversary)."""
    records = json.loads(path.read_bytes())
    mutate(records)
    records["content_sha256"] = m.core.content_sha256(records)
    path.write_bytes(m.core.canonical_bytes(records))


def check_v14(ledgers, inputs) -> None:
    with tempfile.TemporaryDirectory(prefix="g6-rate-surface-fixture-") as temporary:
        directory = Path(temporary).resolve()
        plan_path, root, plan = synthetic_v14_set(directory, "0.5x", 6, [4, 2], "", ledgers, inputs)
        accepted = {"0.5x": plan["content_sha256"], "2x": "1" * 64}
        series, evidence = m.aggregate_v14(plan_path, root, "0.5x", accepted_plans=accepted, audit=fake_audit_from_disk)
        require(len(series) == 10 and all(s["coordinate_count"] == 6 and s["source"] == "v14" and s["scale"] == "0.5x" for s in series)
                and sum(1 for s in series if s["condition"]["role"] == "primary") == 2 and evidence["batch_count"] == 2
                and evidence["consumed_records"][0]["records_file_sha256"] == hashlib.sha256((root / plan["batches"][0]["batch_id"] / "records.json").read_bytes()).hexdigest()
                and "hash-bound" in evidence["binding"], "V-14 synthetic aggregation drift")
        m._no_float_or_bool(series)
        # Plan pinning: unpinned hash, swapped scale, tampered plan bytes.
        rejected(lambda: m.aggregate_v14(plan_path, root, "0.5x", audit=fake_audit_from_disk), "plan not matching the production pin")
        rejected(lambda: m.aggregate_v14(plan_path, root, "2x", accepted_plans={"0.5x": "1" * 64, "2x": plan["content_sha256"]}, audit=fake_audit_from_disk),
                 "0.5x plan supplied as the 2x plan")
        rejected(lambda: m.aggregate_v14(plan_path, root, "1x", accepted_plans=accepted, audit=fake_audit_from_disk), "unknown scale")
        tampered_plan = directory / "plan_tampered.json"
        tampered_plan.write_bytes(plan_path.read_bytes().replace(b'"scale":"0.5x"', b'"scale":"0.5x","x":1'))
        rejected(lambda: m.aggregate_v14(tampered_plan, root, "0.5x", accepted_plans=accepted, audit=fake_audit_from_disk), "plan bytes not matching its content hash")
        # Audit receipt integrity.
        rejected(lambda: m.aggregate_v14(plan_path, root, "0.5x", accepted_plans=accepted, audit=lambda p, r: {**fake_audit_from_disk(p, r), "verdict": "rejected"}),
                 "non-accepting receipt")
        rejected(lambda: m.aggregate_v14(plan_path, root, "0.5x", accepted_plans=accepted, audit=lambda p, r: {**fake_audit_from_disk(p, r), "plan_content_sha256": "2" * 64}),
                 "receipt for another plan")

        def outside(p, r):
            receipt = fake_audit_from_disk(p, r)
            receipt["batches"][0]["path"] = str(directory / "elsewhere")
            return receipt
        rejected(lambda: m.aggregate_v14(plan_path, root, "0.5x", accepted_plans=accepted, audit=outside), "receipt path outside the root")

        def raising(p, r):
            raise m.v14_audit.LegacyAuditError("audit refused")
        rejected(lambda: m.aggregate_v14(plan_path, root, "0.5x", accepted_plans=accepted, audit=raising), "audit refusal propagates as a typed error")
        # TOCTOU: the audit hashed the original bytes; the file is then rehashed consistently before consumption.
        b0 = root / plan["batches"][0]["batch_id"] / "records.json"
        original = b0.read_bytes()
        receipt_before = fake_audit_from_disk(plan, root)

        def flip(records):
            summary = records["records"][1]["primary_c_h_2048"]["unbalanced"]
            summary["T_E_size"] = summary["T_E_size"] + 1  # guaranteed byte change; the byte binding must trip first
        reseal_records(b0, flip)
        rejected(lambda: m.aggregate_v14(plan_path, root, "0.5x", accepted_plans=accepted, audit=lambda p, r: receipt_before),
                 "records.json rehashed after the audit (TOCTOU)")
        # Same tampering but the (fake) audit is fooled into re-reading: the semantic validator must still reject an inconsistent record.
        def corrupt(records):
            records["records"][1]["primary_c_h_2048"]["unbalanced"]["p_A"] = [9, 3]
        b0.write_bytes(original)
        reseal_records(b0, corrupt)
        rejected(lambda: m.aggregate_v14(plan_path, root, "0.5x", accepted_plans=accepted, audit=fake_audit_from_disk),
                 "rehashed but semantically corrupted record")
        b0.write_bytes(original)
        # A consistent, semantically valid re-labelling that the audit did not see must still be refused (byte binding).
        b0.write_bytes(original + b"\n")
        rejected(lambda: m.aggregate_v14(plan_path, root, "0.5x", accepted_plans=accepted, audit=lambda p, r: receipt_before),
                 "records.json bytes changed after the audit")
        b0.write_bytes(original)
        # Root membership.
        (root / "extra_dir").mkdir()
        rejected(lambda: m.aggregate_v14(plan_path, root, "0.5x", accepted_plans=accepted, audit=fake_audit_from_disk), "extra batch directory")
        (root / "extra_dir").rmdir()
        (root / "stray.json").write_bytes(b"{}")
        rejected(lambda: m.aggregate_v14(plan_path, root, "0.5x", accepted_plans=accepted, audit=fake_audit_from_disk), "extra file in the root")
        (root / "stray.json").unlink()
        b1 = root / plan["batches"][1]["batch_id"]
        b1.rename(directory / "moved")
        rejected(lambda: m.aggregate_v14(plan_path, root, "0.5x", accepted_plans=accepted, audit=lambda p, r: receipt_before), "missing batch directory")
        b1.symlink_to(directory / "moved")
        rejected(lambda: m.aggregate_v14(plan_path, root, "0.5x", accepted_plans=accepted, audit=lambda p, r: receipt_before), "symlinked batch directory")
        b1.unlink()
        (directory / "moved").rename(b1)
        # Mixed set: a second synthetic plan's batch directory present in the root.
        _plan2_path, root2, plan2 = synthetic_v14_set(directory, "2x", 3, [3], "", ledgers, inputs)
        foreign = root2 / plan2["batches"][0]["batch_id"]
        foreign.rename(root / foreign.name)
        rejected(lambda: m.aggregate_v14(plan_path, root, "0.5x", accepted_plans=accepted, audit=fake_audit_from_disk), "mixed batch directories")
        (root / foreign.name).rename(foreign)
        # Coverage: receipt/plan batch mismatch and duplicate coordinates.
        def duplicate_range(p, r):
            receipt = fake_audit_from_disk(p, r)
            receipt["batches"][1]["range"] = dict(receipt["batches"][0]["range"])
            return receipt
        rejected(lambda: m.aggregate_v14(plan_path, root, "0.5x", accepted_plans=accepted, audit=duplicate_range), "duplicate coordinate coverage")
        require(m.aggregate_v14(plan_path, root, "0.5x", accepted_plans=accepted, audit=fake_audit_from_disk)[0] == series, "V-14 set not restored")
        # Whole payload through the injection seams: synthetic Gate-5 series, both V-14 sets, distinct plans required.
        plan2_path = directory / "plan_2x.json"
        accepted_both = {"0.5x": plan["content_sha256"], "2x": plan2["content_sha256"]}

        def aggregator(plan_file, artifact_root, scale):
            return m.aggregate_v14(plan_file, artifact_root, scale, accepted_plans=accepted_both, audit=fake_audit_from_disk)
        payload = m.build_rate_surface(v14_0_5_plan=plan_path, v14_0_5_artifacts=root, v14_2x_plan=plan2_path, v14_2x_artifacts=root2,
                                       reviewed_handoff="fixture-handoff", gate5_loader=lambda: rows([1, 2, 3]), v14_aggregator=aggregator)
        require(payload["schema"] == m.SCHEMA and payload["d013_disposition"]["disposition"] == "does_not_fire"
                and len(payload["series"]) == 6 + 10 + 10 and payload["content_sha256"] == hashlib.sha256(m.canonical_bytes(
                    {k: v for k, v in payload.items() if k != "content_sha256"})).hexdigest()
                and payload["input_identities"]["accepted_v14_plans"] == m.ACCEPTED_V14_PLANS
                and payload["input_identities"]["d015_d016_decisions_file_sha256"] == m.AUTHORITIES["research/decisions/DECISIONS.md"]
                and all("records" not in key for key in payload) and "X_E" not in json.dumps(payload) and "H_E_min_hex" not in json.dumps(payload),
                "aggregate payload drift")
        m._no_float_or_bool(payload)
        rejected(lambda: m.build_rate_surface(v14_0_5_plan=plan_path, v14_0_5_artifacts=root, v14_2x_plan=plan_path, v14_2x_artifacts=root,
                                              reviewed_handoff="fixture-handoff", gate5_loader=lambda: rows([1, 2, 3]),
                                              v14_aggregator=lambda pf, ar, sc: aggregator(pf, ar, "0.5x")), "the same plan used for both scales")
        rejected(lambda: m.build_rate_surface(v14_0_5_plan=plan_path, v14_0_5_artifacts=root, v14_2x_plan=plan2_path, v14_2x_artifacts=root2,
                                              reviewed_handoff="fixture-handoff", gate5_loader=lambda: rows([1, 2, 3])[:5], v14_aggregator=aggregator),
                 "Gate-5 loader returning five series")
        rejected(lambda: m.build_rate_surface(v14_0_5_plan=plan_path, v14_0_5_artifacts=root, v14_2x_plan=plan2_path, v14_2x_artifacts=root2,
                                              reviewed_handoff="", gate5_loader=lambda: rows([1, 2, 3]), v14_aggregator=aggregator), "empty reviewed handoff")


def check_cli() -> None:
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    run = [sys.executable, str(RUNNER)]
    a = subprocess.run(run, cwd=ROOT, env=env, text=True, capture_output=True, check=False)
    b = subprocess.run([sys.executable, "-O", str(RUNNER)], cwd=ROOT, env=env, text=True, capture_output=True, check=False)
    require(a.returncode == 0 and a.stdout == b.stdout and '"mode":"plan"' in a.stdout and '"writes":"none"' in a.stdout
            and m.ACCEPTED_V14_PLANS["2x"] in a.stdout, "plan mode drift")
    failed = subprocess.run([*run, "--run"], cwd=ROOT, env=env, text=True, capture_output=True, check=False)
    require(failed.returncode == 1 and "requires" in failed.stderr and failed.stdout == "", "run input guard")
    no_env = {k: v for k, v in os.environ.items() if k != "PYTHONDONTWRITEBYTECODE"}
    guarded = subprocess.run([sys.executable, "-B", str(RUNNER)], cwd=ROOT, env=no_env, text=True, capture_output=True, check=False)
    require(guarded.returncode == 1 and "PYTHONDONTWRITEBYTECODE" in guarded.stderr, "bytecode guard")


def main() -> int:
    original_loader, original_iter = m.aggregate_ratified_gate5, m.ratified_g5_input.iter_ratified_records
    m.aggregate_ratified_gate5 = _forbidden
    m.ratified_g5_input.iter_ratified_records = _forbidden
    try:
        require(os.environ.get("PYTHONDONTWRITEBYTECODE") == "1", "run with PYTHONDONTWRITEBYTECODE=1")
        check_d013()
        check_aggregation_and_output()
        check_authorities()
        ledgers = m.core.engine.load_ledgers()
        inputs = m.core.classifier_inputs(ledgers)
        check_v14(ledgers, inputs)
        check_cli()
        require(not PRODUCTION_CALLS, "a production Gate-5 read was attempted during fixtures")
        require(not [p for p in (ROOT / "research").rglob("*.pyc") if p.stat().st_mtime > (ROOT / "research/g6/rate_surface_and_d013.py").stat().st_mtime],
                "bytecode written")
        print("PASS Gate-6 rate/D013 fixtures; no Gate-5/V-14 corpus read, no artifact written")
        return 0
    except FixtureError as exc:
        print(f"FAIL Gate-6 rate/D013 fixtures: {exc}", file=sys.stderr)
        return 1
    finally:
        m.aggregate_ratified_gate5, m.ratified_g5_input.iter_ratified_records = original_loader, original_iter


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Hardware-free fixtures for the V-14 CUDA/T4 batch plan and final-set validator.

Uses a synthetic (structurally genuine) CUDA/T4 qualification record and a
synthetic throughput measurement in an automatically removed temporary
directory.  Proves: linear-order bijection; conservative sizing; exact
single cover with no overlap; deterministic canonical plans (normal and
``python -O`` byte-identical through the CLI); order-independent acceptance;
rejection of gaps, overlaps, duplicates, changed CUDA fingerprints, changed
ledgers, RX 9070/ROCm/HIP platforms, intra-batch session drift, mixed
identities, scientific fields, and unqualified inputs.  No energy is
computed, no Gate-5 path is read, and no project file is written.
"""

from __future__ import annotations

import ast
import copy
from decimal import Decimal
from fractions import Fraction
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
MODULE = ROOT / "research/g6/cuda_qualification/v14_batch_contract.py"
CLI = ROOT / "research/g6/plan_v14_cuda_batches.py"
NEW_PYTHON = (MODULE, CLI, Path(__file__).resolve())


class FixtureError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise FixtureError(message)


def load_module():
    specification = importlib.util.spec_from_file_location("g6_v14_batch_contract_fixture", MODULE)
    require(specification is not None and specification.loader is not None, "module unavailable")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def tree_digest(directory: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(p for p in directory.rglob("*") if p.is_file()):
        digest.update(str(path.relative_to(ROOT)).encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def rejects(module, function, *arguments, reason: str) -> None:
    try:
        function(*arguments)
    except module.BatchContractError:
        return
    raise FixtureError(f"accepted: {reason}")


def synthetic_qualification(module) -> dict:
    """A structurally genuine passed engine validation record; identity values are synthetic, never measured."""
    engine = module.engine
    pins = engine.verify_pinned_inputs()
    per = engine.DECODED_COUNT + engine.EXPECTED_SLACK_DOMAIN["entries"]
    report = {
        "architecture": "sm_75", "backend": engine.BACKEND, "compute_capability": "7.5", "coordinate_count": 8,
        "cuda_driver_version": 13000, "cuda_runtime_version": 12080, "decoded_state_count": engine.DECODED_COUNT,
        "device_count": 1, "device_index": 0, "device_name": "Tesla T4", "device_uuid_hex": "0123456789abcdef0123456789abcdef",
        "device_vs_host_cxx_mismatches": 0, "elapsed_ns_coordinates": 8000000000, "elapsed_ns_prepare": 50000000,
        "evaluations": 8 * per, "host_reference_evaluated": True, "mode": "validate", "multiprocessor_count": 40,
        "nonfinite_energies": 0, "nvcc_version": "12.8.93", "pci_bus_id": 0, "pci_device_id": 4, "pci_domain_id": 0,
        "point_count": 8, "probe": engine.PROBE, "scientific_outputs": "intentionally absent",
        "slack_state_count": engine.EXPECTED_SLACK_DOMAIN["entries"], "state_count": per, "tie_nesting_violations": 0,
        "total_global_memory_bytes": 15828320256,
    }
    nvcc_info = {"path": "/usr/local/cuda/bin/nvcc", "release": "12.8", "build": "12.8.93", "stdout": ""}
    command = module.cuda.compile_command(nvcc_info["path"], Path("e.cu"), Path("e"))
    domain = {"unbalanced": {"order": engine.DECODED_ORDER, "width": 20, "count": engine.DECODED_COUNT},
              "slack": {"source": "src.g5.domains.build_slack_domain_cache (active-CSB, bounded register minimizers)",
                        "order": "SlackDomainCache.iter_auxiliary_indexed: decoded index major, cached lift order",
                        "entries": engine.EXPECTED_SLACK_DOMAIN["entries"],
                        "logical_sha256": engine.EXPECTED_SLACK_DOMAIN["logical_sha256"],
                        "instance_sha256": "e" * 64, "register_widths": {"sector": 2, "budget": 11}}}
    prerequisites = {"unbalanced_identity_sha256": "a" * 64, "slack_identity_sha256": "b" * 64}
    identity = engine.engine_identity(report, nvcc_info, command, pins, domain, prerequisites)
    per_coordinate = [{"scale": scale, "coordinate": {"card": c, "sector": s, "budget": b},
                       "unbalanced": {"gpu_vs_python_word_mismatches": 0, "evaluations": engine.DECODED_COUNT,
                                      "h_min_bits_mismatch": 0, "h_min_index_mismatch": 0, "tie_flag_mismatches": 0},
                       "slack": {"gpu_vs_python_word_mismatches": 0, "evaluations": engine.EXPECTED_SLACK_DOMAIN["entries"],
                                 "h_min_bits_mismatch": 0, "h_min_index_mismatch": 0, "tie_flag_mismatches": 0}}
                      for scale, (c, s, b) in engine.VALIDATION_COORDINATES]
    return {
        "schema": engine.SCHEMA_VALIDATE, "mode": "validate", "track": "cuda-t4", "verdict": "pass",
        "validation": {"per_coordinate": per_coordinate, "totals": {"word_mismatches": 0, "reduction_mismatches": 0},
                       "device_vs_host_cxx_mismatches": 0},
        "evaluations": 8 * per,
        "qualification_identity": identity,
        "qualification_identity_sha256": engine.identity_sha256(identity),
        "device": module.cuda.device_fingerprint(report),
        "scientific_outputs": "intentionally absent",
    }


def synthetic_throughput(module, identity_sha256: str, samples) -> dict:
    """samples: (coordinates, coordinate_seconds, setup_seconds[, wall_seconds]); wall defaults to the exact sum."""
    rendered = []
    for sample in samples:
        coordinates, coordinate, setup = sample[0], sample[1], sample[2]
        wall = sample[3] if len(sample) > 3 else str(Decimal(str(setup)) + Decimal(str(coordinate)))
        rendered.append({"coordinates": coordinates, "wall_seconds": wall, "setup_seconds": setup,
                         "coordinate_seconds": coordinate})
    payload = {"schema": module.SCHEMA_THROUGHPUT, "unit": "coordinates",
               "qualification_identity_sha256": identity_sha256, "samples": rendered,
               "measured_by": "synthetic fixture; not a measurement"}
    payload["content_sha256"] = module.content_sha256(payload)
    return payload


def synthetic_manifest(module, plan: dict, batch_id: str, session_id: str, uuid: str) -> dict:
    manifest = module.manifest_skeleton(plan, batch_id)
    fingerprint = hashlib.sha256(session_id.encode()).hexdigest()
    manifest["session"] = {"session_id": session_id, "device_uuid_hex": uuid,
                           "start_platform_sha256": fingerprint, "end_platform_sha256": fingerprint}
    manifest["records"] = {"record_count": manifest["range"]["count"],
                           "value_file_sha256": hashlib.sha256(batch_id.encode()).hexdigest()}
    manifest["content_sha256"] = module.content_sha256(manifest)
    return manifest


def resealed(module, manifest: dict, **changes) -> dict:
    copied = copy.deepcopy(manifest)
    for key, value in changes.items():
        copied[key] = value
    copied["content_sha256"] = module.content_sha256(copied)
    return copied


def check_static() -> None:
    for source in NEW_PYTHON:
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        require(not any(isinstance(node, ast.Assert) for node in ast.walk(tree)),
                f"assert is not permitted: {source.name}")
    for source in (MODULE, CLI):
        text = source.read_text(encoding="utf-8")
        require("src.g5" not in text and "core_pass_output" not in text and "research/g5" not in text,
                f"{source.name} names a Gate-5 corpus or module path")


def check_linear_order(module) -> None:
    for axis_count in (31, 111):
        seen = set()
        for card in (0, 1, axis_count - 1):
            for sector in (0, 2, axis_count - 1):
                for budget in range(axis_count):
                    linear = module.linear_index(card, sector, budget, axis_count)
                    require(module.coordinate_at(linear, axis_count) == (card, sector, budget), "linear order bijection")
                    seen.add(linear)
        require(len(seen) == 9 * axis_count, "linear order collision")
        require(module.linear_index(axis_count - 1, axis_count - 1, axis_count - 1, axis_count) == axis_count ** 3 - 1,
                "last linear index drift")
    require(module.linear_index(1, 0, 0, 31) == 961 and module.linear_index(0, 1, 0, 31) == 31, "linear formula drift")
    rejects(module, module.linear_index, 31, 0, 0, 31, reason="axis overflow")


def check_sizing(module) -> None:
    require(module.TARGET_BATCH_SECONDS == 12600 and module.SESSION_BUDGET_SECONDS == 14400, "budget drift")
    cap = module.engine.MAX_COORDINATES_PER_INVOCATION
    require(cap == 4096, "engine invocation cap drift")
    # 1 coordinate / 10 s, setup 600 s, derate 9/10: floor(0.1 * (12600 - 600) * 0.9) = 1080.
    require(module.coordinates_per_batch(Fraction(1, 10), Fraction(600), Fraction(9, 10)) == (1080, 1080), "sizing formula drift")
    require(module.coordinates_per_batch(Fraction(1, 10), Fraction(0), Fraction(9, 10)) == (1134, 1134), "zero-setup sizing drift")
    require(module.coordinates_per_batch(Fraction(1, 12600), Fraction(0), Fraction(1)) == (1, 1), "single-coordinate boundary")
    # High throughput: 100 coordinates/s would give 1,260,000; the engine cap applies.
    require(module.coordinates_per_batch(Fraction(100), Fraction(0), Fraction(1)) == (cap, 1260000), "invocation cap not applied")
    require(module.coordinates_per_batch(Fraction(4097, 12600), Fraction(0), Fraction(1)) == (cap, 4097), "cap boundary drift")
    require(module.coordinates_per_batch(Fraction(4096, 12600), Fraction(0), Fraction(1)) == (cap, 4096), "cap boundary drift")
    rejects(module, module.coordinates_per_batch, Fraction(1, 12001), Fraction(600), Fraction(1), reason="sub-coordinate after setup")
    rejects(module, module.coordinates_per_batch, Fraction(1), Fraction(12600), Fraction(1), reason="setup consuming the window")
    rejects(module, module.coordinates_per_batch, Fraction(1), Fraction(-1), Fraction(1), reason="negative setup")
    rejects(module, module.coordinates_per_batch, Fraction(1), Fraction(0), Fraction(0), reason="zero derate")
    rejects(module, module.coordinates_per_batch, Fraction(1), Fraction(0), Fraction(11, 10), reason="derate above one")
    batches = module.batch_ranges(29791, 1134, "t")
    require(batches[0]["start"] == 0 and batches[-1]["stop"] == 29791 and len(batches) == 27
            and all(b["stop"] - b["start"] == b["count"] for b in batches)
            and all(batches[i]["stop"] == batches[i + 1]["start"] for i in range(len(batches) - 1)),
            "batch ranges do not tile the grid")
    require(len({b["batch_id"] for b in batches}) == 27, "batch ids collide")


def check_inputs(module, record: dict) -> None:
    cuda = module.cuda
    identity = module.validate_qualification_record(record)
    sha = module.engine.identity_sha256(identity)
    rejects(module, module.validate_qualification_record, {**record, "verdict": "fail"}, reason="failed record")
    mismatching = copy.deepcopy(record)
    mismatching["validation"]["totals"]["word_mismatches"] = 1
    rejects(module, module.validate_qualification_record, mismatching, reason="mismatching record")
    mismatching = copy.deepcopy(record)
    mismatching["validation"]["totals"]["reduction_mismatches"] = 1
    rejects(module, module.validate_qualification_record, mismatching, reason="reduction-mismatching record")
    rejects(module, module.validate_qualification_record, {**record, "track": "rocm-rx9070"}, reason="ROCm track")
    rejects(module, module.validate_qualification_record, {**record, "schema": cuda.SCHEMA_RUN, "mode": "run"},
            reason="bare unbalanced qualifier record instead of the engine record")
    missing_prerequisite = copy.deepcopy(record)
    del missing_prerequisite["qualification_identity"]["prerequisites"]["slack_identity_sha256"]
    missing_prerequisite["qualification_identity_sha256"] = module.engine.identity_sha256(missing_prerequisite["qualification_identity"])
    rejects(module, module.validate_qualification_record, missing_prerequisite, reason="record lacking the slack prerequisite")
    wrong_domain = copy.deepcopy(record)
    wrong_domain["qualification_identity"]["domain"]["slack"]["logical_sha256"] = "d" * 64
    wrong_domain["qualification_identity_sha256"] = module.engine.identity_sha256(wrong_domain["qualification_identity"])
    rejects(module, module.validate_qualification_record, wrong_domain, reason="record bound to a different slack domain")
    rejects(module, module.validate_qualification_record,
            {**record, "qualification_identity_sha256": "0" * 64}, reason="identity hash mismatch")
    for key, value in (("gpu_name", "AMD Radeon RX 9070"), ("gpu_name", "NVIDIA A100-SXM4-40GB"),
                       ("backend", "hip-runtime"), ("compute_capability", "8.6"), ("architecture", "gfx1201"),
                       ("compile_flags", [flag for flag in cuda.COMPILE_FLAGS if flag != "--fmad=false"]),
                       ("nvcc_build", "0.0.0"), ("cuda_driver_version", 0)):
        changed = copy.deepcopy(record)
        changed["qualification_identity"][key] = value
        changed["qualification_identity_sha256"] = module.engine.identity_sha256(changed["qualification_identity"])
        rejects(module, module.validate_qualification_record, changed, reason=f"identity {key}={value!r}")
    # Changed ledger: a record produced against a different V-14 2x ledger is rejected.
    changed = copy.deepcopy(record)
    changed["qualification_identity"]["pinned_inputs"][cuda.V14_2X_LEDGER_REL] = "1" * 64
    changed["qualification_identity_sha256"] = module.engine.identity_sha256(changed["qualification_identity"])
    rejects(module, module.validate_qualification_record, changed, reason="record bound to a changed ledger")
    changed = copy.deepcopy(record)
    changed["qualification_identity"]["pinned_inputs"]["src/g4/energy.py"] = "2" * 64
    changed["qualification_identity_sha256"] = module.engine.identity_sha256(changed["qualification_identity"])
    rejects(module, module.validate_qualification_record, changed, reason="record bound to a changed evaluator")

    good = synthetic_throughput(module, sha, [(12, "120.5", "40.000000001"), (10, "90", "55.25")])
    measured = module.validate_throughput(good, sha)
    require(measured["conservative_rate_coordinates_per_second"] == "24/241" and measured["conservative_setup_seconds"] == "221/4"
            and measured["samples"][0]["wall_seconds"] == "160.500000001"
            and measured["acceptance_basis"] == "duration_threshold" and measured["full_cap_sample_count"] == 0,
            "slowest rate / largest setup not chosen")
    # A genuine full-cap (4096-coordinate) sample under 60 s is accepted as invocation-cap-limited;
    # the same duration without a full-cap sample is rejected.
    capped = module.validate_throughput(synthetic_throughput(module, sha, [(4096, "41.271828182", "93.5")]), sha)
    require(capped["acceptance_basis"] == "invocation_cap_limited" and capped["full_cap_sample_count"] == 1
            and capped["conservative_rate_coordinates_per_second"] == str(Fraction(4096) / Fraction("41.271828182"))
            and capped["conservative_setup_seconds"] == "187/2", "cap-limited acceptance drift")
    rejects(module, module.validate_throughput, synthetic_throughput(module, sha, [(4095, "41.271828182", "93.5")]), sha,
            reason="4095-coordinate sample under 60 s")
    rejects(module, module.validate_throughput, synthetic_throughput(module, sha, [(2048, "20", "5"), (2048, "20", "5")]), sha,
            reason="two half-cap samples under 60 s in total")
    mixed = module.validate_throughput(synthetic_throughput(module, sha, [(4096, "40", "90"), (10, "5", "90.25")]), sha)
    require(mixed["acceptance_basis"] == "invocation_cap_limited" and mixed["conservative_rate_coordinates_per_second"] == "2/1"
            and mixed["conservative_setup_seconds"] == "361/4", "mixed cap-limited measurement drift")
    long_cap = module.validate_throughput(synthetic_throughput(module, sha, [(4096, "61", "90")]), sha)
    require(long_cap["acceptance_basis"] == "duration_threshold" and long_cap["full_cap_sample_count"] == 1,
            "a full-cap sample over 60 s must remain an ordinary acceptance")
    rejects(module, module.validate_throughput, good, "0" * 64, reason="throughput bound to another identity")
    rejects(module, module.validate_throughput, {**good, "content_sha256": "0" * 64}, sha, reason="throughput hash")
    rejects(module, module.validate_throughput, synthetic_throughput(module, sha, []), sha, reason="no samples")
    rejects(module, module.validate_throughput, synthetic_throughput(module, sha, [(10, "0", "5")]), sha, reason="zero coordinate time")
    rejects(module, module.validate_throughput, synthetic_throughput(module, sha, [(0, "100", "5")]), sha, reason="zero coords")
    rejects(module, module.validate_throughput, synthetic_throughput(module, sha, [(3, "100", "5")]), sha, reason="too few coords")
    rejects(module, module.validate_throughput, synthetic_throughput(module, sha, [(10, "30", "5")]), sha, reason="too short")
    rejects(module, module.validate_throughput, synthetic_throughput(module, sha, [(4097, "30", "5")]), sha,
            reason="above-cap sample cannot unlock cap-limited acceptance")
    rejects(module, module.validate_throughput, synthetic_throughput(module, sha, [(10, 1.5, "5")]), sha, reason="float seconds")
    rejects(module, module.validate_throughput, synthetic_throughput(module, sha, [(10, "100", "-1")]), sha, reason="negative setup")
    rejects(module, module.validate_throughput, synthetic_throughput(module, sha, [(10, "100", "5", "105.000000001")]), sha,
            reason="wall not reconciling at nanosecond precision")
    rejects(module, module.validate_throughput, synthetic_throughput(module, sha, [(10, "100", "5", "104.999999999")]), sha,
            reason="wall short by one nanosecond")
    rejects(module, module.validate_throughput, synthetic_throughput(module, sha, [(10, "100", "12600")]), sha,
            reason="setup consuming the target window")
    rejects(module, module.validate_throughput, synthetic_throughput(module, sha, [(4097, "100", "5")]), sha,
            reason="sample above the invocation cap")
    legacy = copy.deepcopy(good)
    for sample in legacy["samples"]:
        del sample["setup_seconds"]
    legacy["content_sha256"] = module.content_sha256(legacy)
    rejects(module, module.validate_throughput, legacy, sha, reason="legacy two-field sample")
    extra = copy.deepcopy(good)
    extra["samples"][0]["rate"] = "1"
    extra["content_sha256"] = module.content_sha256(extra)
    rejects(module, module.validate_throughput, extra, sha, reason="sample with an extra field")


def check_plan(module, record: dict) -> tuple[dict, dict]:
    sha = record["qualification_identity_sha256"]
    throughput = synthetic_throughput(module, sha, [(40, "400", "600")])  # 0.1 coordinates/s, 600 s setup
    plan = module.build_plan("0.5x", record, throughput)
    again = module.build_plan("0.5x", record, throughput)
    require(module.canonical_bytes(plan) == module.canonical_bytes(again), "plan is not deterministic")
    require(plan["sizing"]["coordinates_per_batch"] == 1080 and plan["sizing"]["coordinates_per_batch_uncapped"] == 1080
            and plan["sizing"]["cap_applied"] is False and plan["sizing"]["batch_count"] == 28
            and plan["sizing"]["max_coordinates_per_invocation"] == 4096 and plan["sizing"]["conservative_setup_seconds"] == "600/1"
            and plan["grid"]["total_coordinates"] == 29791 and plan["sizing"]["estimated_full_batch_seconds"] == "11400/1"
            and "min(uncapped, max_coordinates_per_invocation)" in plan["sizing"]["rule"]
            and plan["sizing"]["measurement_acceptance_basis"] == "duration_threshold"
            and plan["throughput"]["acceptance_basis"] == "duration_threshold",
            "0.5x plan sizing drift")
    # A cap-limited measurement (one 4096-coordinate sample under 60 s) plans a capped batch and records the basis.
    limited = module.build_plan("2x", record, synthetic_throughput(module, sha, [(4096, "41.271828182", "93.5")]))
    require(limited["sizing"]["measurement_acceptance_basis"] == "invocation_cap_limited"
            and limited["throughput"]["acceptance_basis"] == "invocation_cap_limited"
            and limited["throughput"]["full_cap_sample_count"] == 1
            and limited["sizing"]["coordinates_per_batch"] == 4096 and limited["sizing"]["cap_applied"] is True
            and all(b["count"] <= 4096 for b in limited["batches"]) and limited["batches"][-1]["stop"] == 1367631
            and limited["sizing"]["batch_count"] == -(-1367631 // 4096), "cap-limited plan drift")
    module.validate_plan(limited)
    # High synthetic throughput (200/3 coordinates/s) would size 752,640 per batch; the cap must hold.
    fast = module.build_plan("0.5x", record, synthetic_throughput(module, sha, [(4000, "60", "56")]))
    require(fast["sizing"]["coordinates_per_batch"] == 4096 and fast["sizing"]["cap_applied"] is True
            and fast["sizing"]["coordinates_per_batch_uncapped"] == 752640 and fast["sizing"]["batch_count"] == 8
            and all(b["count"] <= 4096 for b in fast["batches"]) and fast["batches"][-1]["stop"] == 29791, "cap not applied in plan")
    module.validate_plan(fast)
    over = copy.deepcopy(fast)
    over["sizing"]["coordinates_per_batch"] = 4097
    over["batches"] = module.batch_ranges(29791, 4097, "v14_0_5x")
    over["sizing"]["batch_count"] = len(over["batches"])
    over["content_sha256"] = module.content_sha256(over)
    rejects(module, module.validate_plan, over, reason="plan with a batch above the invocation cap")
    require(Fraction(plan["sizing"]["estimated_full_batch_seconds"]) <= module.TARGET_BATCH_SECONDS
            < module.SESSION_BUDGET_SECONDS, "batch estimate exceeds the target")
    require(plan["ledger_identity"]["pass_id"] == "v14_expansion_0.5x"
            and plan["ledger_identity"]["content_sha256"] == "031752dba1d7386c1dec8d0bcd23eb29e68d091b33f346e237bcc2528ec53654",
            "0.5x ledger identity drift")
    require(plan["all_v14_ledgers_validated"]["2x"] == "f3f99ba08395115a6ab0c70f9d657ec96354ef06e182d1d907fcdd9c9e696251",
            "2x ledger not validated alongside")
    require(plan["cuda_qualification_identity_sha256"] == sha and plan["platform"]["gpu_name"] == "Tesla T4"
            and plan["compile_contract"]["nvcc_flags"] == list(module.cuda.COMPILE_FLAGS)
            and plan["prerequisite_qualification_identities"] == {"unbalanced_identity_sha256": "a" * 64, "slack_identity_sha256": "b" * 64}
            and plan["slack_domain_logical_sha256"] == module.engine.EXPECTED_SLACK_DOMAIN["logical_sha256"]
            and plan["compile_contract"]["cuda_source_sha256"] == module.engine.PINNED_INPUTS[module.engine.CUDA_SOURCE_REL],
            "plan binding drift")
    tampered_prerequisites = copy.deepcopy(plan)
    tampered_prerequisites["prerequisite_qualification_identities"]["slack_identity_sha256"] = "9" * 64
    tampered_prerequisites["content_sha256"] = module.content_sha256(tampered_prerequisites)
    rejects(module, module.validate_plan, tampered_prerequisites, reason="plan whose prerequisites differ from its identity")
    require(set(plan["source_sha256"]) == set(module.PLAN_SOURCE_RELATIVES)
            and plan["source_sha256"][MODULE.relative_to(ROOT).as_posix()]
            == hashlib.sha256(MODULE.read_bytes()).hexdigest(), "plan does not bind its own source")
    require(plan["content_sha256"] == module.content_sha256(plan), "plan content hash drift")
    for key in ("energies", "H_E_min_hex", "labels"):
        require(key not in json.dumps(plan), "plan carries a scientific field")
    double = module.build_plan("2x", record, throughput, Fraction(1))
    require(double["grid"]["total_coordinates"] == 1367631 and double["sizing"]["coordinates_per_batch"] == 1200
            and double["sizing"]["batch_count"] == 1140 and double["batches"][-1]["stop"] == 1367631,
            "2x plan sizing drift")
    module.validate_plan(double)
    tampered = copy.deepcopy(plan)
    tampered["batches"][3]["start"] += 1
    tampered["content_sha256"] = module.content_sha256(tampered)
    rejects(module, module.validate_plan, tampered, reason="plan with a gap")
    tampered = copy.deepcopy(plan)
    tampered["ledger_identity"]["content_sha256"] = "3" * 64
    rejects(module, module.validate_plan, tampered, reason="plan with an unsealed ledger change")
    rejects(module, module.build_plan, "0.5x", record, synthetic_throughput(module, "0" * 64, [(40, "400", "600")]),
            reason="plan from a foreign throughput measurement")
    rejects(module, module.build_plan, "0.5x", record, synthetic_throughput(module, sha, [(40, "400", "12599")]),
            reason="plan whose setup leaves no whole coordinate")
    rejects(module, module.build_plan, "1x", record, throughput, reason="unknown scale")
    return plan, throughput


def check_final_set(module, plan: dict) -> None:
    ids = [batch["batch_id"] for batch in plan["batches"]]
    manifests = [synthetic_manifest(module, plan, batch_id, f"colab-session-{index:03d}", f"{index:032x}")
                 for index, batch_id in enumerate(ids)]
    summary = module.validate_final_set(plan, manifests)
    require(summary["verdict"] == "accepted" and summary["batch_count"] == 28 and summary["session_count"] == 28
            and summary["device_count"] == 28 and summary["total_coordinates"] == 29791, "final set summary drift")
    shuffled = list(manifests)
    random.Random(20260920).shuffle(shuffled)
    require(shuffled != manifests and module.validate_final_set(plan, shuffled) == summary, "order dependence")
    require(module.validate_final_set(plan, list(reversed(manifests))) == summary, "reverse-order dependence")
    # Batches from one session on one device are also acceptable (identity is platform, not UUID).
    same = [synthetic_manifest(module, plan, batch_id, "one-session", "a" * 32) for batch_id in ids]
    require(module.validate_final_set(plan, same)["device_count"] == 1, "single-device set rejected")

    rejects(module, module.validate_final_set, plan, manifests[:-1], reason="gap: missing last batch")
    rejects(module, module.validate_final_set, plan, manifests[:5] + manifests[6:], reason="gap: missing middle batch")
    rejects(module, module.validate_final_set, plan, manifests + [manifests[4]], reason="duplicate batch")
    rejects(module, module.validate_final_set, plan, manifests[:4] + [manifests[3]] + manifests[5:],
            reason="duplicate replacing a batch")
    overlap = resealed(module, manifests[7], range={"start": manifests[7]["range"]["start"] - 5,
                                                    "stop": manifests[7]["range"]["stop"],
                                                    "count": manifests[7]["range"]["count"] + 5})
    rejects(module, module.validate_final_set, plan, manifests[:7] + [overlap] + manifests[8:], reason="overlap")
    rejects(module, module.validate_final_set, plan, [], reason="empty set")

    changed_fingerprint = resealed(module, manifests[2], cuda_qualification_identity_sha256="4" * 64)
    rejects(module, module.validate_final_set, plan, manifests[:2] + [changed_fingerprint] + manifests[3:],
            reason="changed CUDA qualification fingerprint")
    platform = dict(manifests[2]["platform"]); platform["cuda_driver_version"] += 1
    rejects(module, module.validate_final_set, plan, manifests[:2] + [resealed(module, manifests[2], platform=platform)]
            + manifests[3:], reason="changed driver version")
    platform = dict(manifests[2]["platform"]); platform["nvcc_build"] = "12.4.131"
    rejects(module, module.validate_final_set, plan, manifests[:2] + [resealed(module, manifests[2], platform=platform)]
            + manifests[3:], reason="changed nvcc build")
    contract = copy.deepcopy(manifests[2]["compile_contract"]); contract["nvcc_flags"].remove("--fmad=false")
    rejects(module, module.validate_final_set, plan, manifests[:2] + [resealed(module, manifests[2], compile_contract=contract)]
            + manifests[3:], reason="changed compile contract")
    ledger = dict(manifests[2]["ledger_identity"]); ledger["content_sha256"] = "5" * 64
    rejects(module, module.validate_final_set, plan, manifests[:2] + [resealed(module, manifests[2], ledger_identity=ledger)]
            + manifests[3:], reason="changed ledger")
    sources = dict(manifests[2]["source_sha256"]); sources["research/g6/cuda_qualification/cuda_energy_crosscheck.py"] = "6" * 64
    rejects(module, module.validate_final_set, plan, manifests[:2] + [resealed(module, manifests[2], source_sha256=sources)]
            + manifests[3:], reason="changed source hash")
    rejects(module, module.validate_final_set, plan, manifests[:2] + [resealed(module, manifests[2], plan_content_sha256="7" * 64)]
            + manifests[3:], reason="manifest bound to another plan")
    other = {"unbalanced_identity_sha256": "a" * 64, "slack_identity_sha256": "c" * 64}
    rejects(module, module.validate_final_set, plan, manifests[:2]
            + [resealed(module, manifests[2], prerequisite_qualification_identities=other)] + manifests[3:],
            reason="manifest with a different slack qualification identity")
    rejects(module, module.validate_final_set, plan, manifests[:2]
            + [resealed(module, manifests[2], slack_domain_logical_sha256="d" * 64)] + manifests[3:],
            reason="manifest with a different slack domain digest")
    for platform in (
        {**manifests[2]["platform"], "backend": "hip-runtime", "gpu_name": "AMD Radeon RX 9070", "architecture": "gfx1201"},
        {**manifests[2]["platform"], "gpu_name": "AMD Radeon RX 9070"},
        {**manifests[2]["platform"], "architecture": "gfx1201"},
        {**manifests[2]["platform"], "gpu_name": "NVIDIA A100-SXM4-40GB", "compute_capability": "8.0", "architecture": "sm_80"},
        {**manifests[2]["platform"], "gpu_name": "Tesla T4 host-emulation-stub"},
    ):
        rejects(module, module.validate_final_set, plan, manifests[:2] + [resealed(module, manifests[2], platform=platform)]
                + manifests[3:], reason=f"platform {platform['gpu_name']} / {platform['architecture']}")
    session = dict(manifests[2]["session"]); session["end_platform_sha256"] = "8" * 64
    rejects(module, module.validate_final_set, plan, manifests[:2] + [resealed(module, manifests[2], session=session)]
            + manifests[3:], reason="intra-batch platform drift (mixed session)")
    session = dict(manifests[2]["session"]); session["device_uuid_hex"] = "gfx1201-rocm"
    rejects(module, module.validate_final_set, plan, manifests[:2] + [resealed(module, manifests[2], session=session)]
            + manifests[3:], reason="non-hex device UUID in session")
    records = dict(manifests[2]["records"]); records["record_count"] -= 1
    rejects(module, module.validate_final_set, plan, manifests[:2] + [resealed(module, manifests[2], records=records)]
            + manifests[3:], reason="record count differs from the range")
    rejects(module, module.validate_final_set, plan, manifests[:2] + [resealed(module, manifests[2], H_E_min_hex="0x0p+0")]
            + manifests[3:], reason="scientific field in manifest")
    unsealed = copy.deepcopy(manifests[2]); unsealed["range"]["count"] += 0; unsealed["content_sha256"] = "9" * 64
    rejects(module, module.validate_final_set, plan, manifests[:2] + [unsealed] + manifests[3:], reason="unsealed manifest")
    rejects(module, module.validate_final_set, plan, manifests[:2] + ["not a manifest"] + manifests[3:], reason="non-object")
    rejects(module, module.manifest_skeleton, plan, "absent-batch", reason="skeleton for an unknown batch")


def check_cli(module, record: dict, throughput: dict, plan: dict) -> None:
    environment = {"PATH": "", "PYTHONDONTWRITEBYTECODE": "1"}
    before = tree_digest(ROOT / "research/g6")
    with tempfile.TemporaryDirectory(prefix="g6-v14-cuda-batch-fixture-") as temporary:
        directory = Path(temporary)
        (directory / "qualification.json").write_bytes(module.canonical_bytes(record))
        (directory / "throughput.json").write_bytes(module.canonical_bytes(throughput))
        base = [str(CLI), "plan", "--scale", "0.5x", "--qualification", str(directory / "qualification.json"),
                "--throughput", str(directory / "throughput.json")]
        normal = subprocess.run([sys.executable, *base], cwd=ROOT, text=True, capture_output=True, check=False,
                                env=environment)
        require(normal.returncode == 0, "CLI plan failed: " + normal.stderr[-400:])
        optimized = subprocess.run([sys.executable, "-O", *base], cwd=ROOT, text=True, capture_output=True,
                                   check=False, env=environment)
        require(optimized.returncode == 0 and optimized.stdout == normal.stdout, "python -O plan differs")
        emitted = json.loads(normal.stdout)
        require(emitted["content_sha256"] == plan["content_sha256"], "CLI plan differs from in-process plan")
        require(normal.stdout == json.dumps(emitted, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n",
                "CLI plan is not canonical JSON")
        (directory / "plan.json").write_text(normal.stdout, encoding="utf-8")
        paths = []
        for index, batch in enumerate(plan["batches"]):
            manifest = synthetic_manifest(module, plan, batch["batch_id"], f"s{index}", f"{index:032x}")
            path = directory / f"{batch['batch_id']}.json"
            path.write_bytes(module.canonical_bytes(manifest))
            paths.append(str(path))
        accept = subprocess.run([sys.executable, str(CLI), "validate-final-set", "--plan", str(directory / "plan.json"),
                                 *reversed(paths)], cwd=ROOT, text=True, capture_output=True, check=False, env=environment)
        require(accept.returncode == 0 and json.loads(accept.stdout)["verdict"] == "accepted",
                "CLI final-set validation failed: " + accept.stderr[-400:])
        reject = subprocess.run([sys.executable, str(CLI), "validate-final-set", "--plan", str(directory / "plan.json"),
                                 *paths[1:]], cwd=ROOT, text=True, capture_output=True, check=False, env=environment)
        require(reject.returncode == 1 and reject.stdout == "" and "missing batches" in reject.stderr,
                "CLI accepted an incomplete cover")
        skeleton = subprocess.run([sys.executable, str(CLI), "manifest-skeleton", "--plan", str(directory / "plan.json"),
                                   "--batch-id", plan["batches"][0]["batch_id"]], cwd=ROOT, text=True,
                                  capture_output=True, check=False, env=environment)
        require(skeleton.returncode == 0 and json.loads(skeleton.stdout)["range"]["start"] == 0, "skeleton CLI drift")
        bad_derate = subprocess.run([sys.executable, *base, "--derate", "3/2"], cwd=ROOT, text=True,
                                    capture_output=True, check=False, env=environment)
        require(bad_derate.returncode == 1 and bad_derate.stdout == "", "derate above one accepted")
        no_env = subprocess.run([sys.executable, *base], cwd=ROOT, text=True, capture_output=True, check=False,
                                env={"PATH": ""})
        require(no_env.returncode == 1 and "PYTHONDONTWRITEBYTECODE=1 is required" in no_env.stderr,
                "CLI without PYTHONDONTWRITEBYTECODE must fail closed")
    require(tree_digest(ROOT / "research/g6") == before, "CLI invocations changed the research/g6 tree")


def main() -> int:
    try:
        check_static()
        module = load_module()
        check_linear_order(module)
        check_sizing(module)
        record = synthetic_qualification(module)
        check_inputs(module, record)
        plan, throughput = check_plan(module, record)
        check_final_set(module, plan)
        check_cli(module, record, throughput, plan)
        # The engine legitimately imports the canonical prepared-domain material
        # (src.g5.domains) and pins src.g5.certify; every other Gate-5 module,
        # input boundary, runner, and result path stays forbidden.
        forbidden = [name for name in sys.modules if name in {
            "src.g5.runner", "src.g5.core_pass", "src.g5.make_self_test",
            "src.g6.g5_input", "src.g6.ratified_g5_input", "src.g6.g5_digest_registry",
            "src.g6.trial_runner", "src.g6.d011_runner"}]
        require(not forbidden, "fixtures loaded a Gate-5 corpus/runner module: " + ", ".join(forbidden))
        print("PASS V-14 CUDA/T4 batch contract fixtures; no energy computed, no GPU, no Gate-5 read, no repository write")
        return 0
    except FixtureError as exc:
        print(f"FAIL V-14 CUDA/T4 batch contract fixtures: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

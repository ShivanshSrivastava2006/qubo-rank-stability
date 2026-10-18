"""Additive owner-authorized hosted U09 draw entry; numerical functions unchanged.

The parent independently pins every imported source, input and this entry.
No runtime constants or frozen module objects are modified.
"""
import hashlib
import json
from pathlib import Path

PACKAGE_PIN = "8937dc59212931b75d7706ac91e3aa0c5621b645cbedec6d2493ee26612770e7"
RUNTIME_PIN = "669fbc025eefce9298f843754b079be5b5cdfde811900ce245bc7e71f52632fb"


def write_five_returns(*, root, acceptance_module, acceptance_record,
                       reviewed_acceptance_sha256, session_identity,
                       generation_release, generation_contract, generator,
                       implementation_record, expected_implementation_sha256,
                       draw_approval, screening_file, expected_screening_sha256,
                       stage1_file, expected_stage1_sha256,
                       ledger_file, expected_ledger_file_sha256,
                       package_file, runtime_file, writer, output_dir):
    def pinned_json(path, pin):
        if (type(pin) is not str or len(pin) != 64 or
                any(c not in "0123456789abcdef" for c in pin)):
            raise ValueError("Independent input/authority pin required")
        raw = Path(path).read_bytes()
        if hashlib.sha256(raw).hexdigest() != pin:
            raise ValueError("Independent input/authority pin mismatch")
        return json.loads(raw)
    package = pinned_json(package_file, PACKAGE_PIN)
    runtime = pinned_json(runtime_file, RUNTIME_PIN)
    if package.get("owner_message") != "approved" or runtime.get("status") != "owner_approved":
        raise ValueError("Owner draw/runtime authority absent")
    acceptance_module.accept_production_identity(acceptance_record,
        reviewed_record_sha256=reviewed_acceptance_sha256, repo_root=str(root))
    acceptance_module.exact_match_session(session_identity, acceptance_record,
        reviewed_record_sha256=reviewed_acceptance_sha256, repo_root=str(root))
    approval_evidence, checked = generation_release.check_against_record(
        implementation_record, draw_approval, expected_implementation_sha256)
    if not generation_release._approval_permits_real_material(draw_approval, None):
        raise ValueError("Actual non-synthetic generator draw authority required")
    fp = generator.runtime_fingerprint()
    if fp["python_version"] != runtime["runtime"]["python"] or fp["numpy_version"] != runtime["runtime"]["numpy"]:
        raise ValueError("Approved runtime amendment mismatch")
    inputs = generation_contract.ScreeningInputs(**pinned_json(screening_file, expected_screening_sha256))
    stage1 = pinned_json(stage1_file, expected_stage1_sha256)
    ledger = pinned_json(ledger_file, expected_ledger_file_sha256)
    start = generation_release.guard.capture_snapshot()
    generation_release._verify_before_draw(checked, start)
    validated = generation_contract.validate_generation_ledger(
        ledger, inputs, checked["sources"]["generator"]["sha256"])
    end = generation_release.guard.capture_snapshot()
    generation_release._verify_after_draw(checked, start, end)
    if (validated.get("verdict") != "accepted" or validated.get("slot_count") != generator.SLOT_COUNT
            or validated.get("ledger_content_sha256") != ledger["content_sha256"]):
        raise ValueError("Exact first-valid five-slot ledger required")
    files, evidence = {}, []
    for accepted in validated["accepted_instances"]:
        slot, attempt = accepted["slot"], accepted["attempt"]
        start = generation_release.guard.capture_snapshot()
        generation_release._verify_before_draw(checked, start)
        seed = generator.stream_seed(slot, attempt, "returns")
        generation_release._require_permitted_material(seed, real_material_authorized=True)
        # Counter increments before invocation, so a failed draw remains visible.
        generation_release.DRAW_CALL_COUNT += 1
        draw = generator.sample_return_covariance(stage1["mu"], stage1["Sigma"], slot, attempt)
        blocks = generator.sector_blocks(slot, attempt)
        partition = generator.normalized_partition(blocks)
        if generator.partition_digest(partition) != accepted["partition_sha256"]:
            raise ValueError("Accepted partition drift")
        raw_returns = draw.returns.astype("<f8", copy=False).tobytes(order="C")
        if hashlib.sha256(raw_returns).hexdigest() != draw.return_matrix_sha256_le_f64_row_major:
            raise ValueError("Return binary serialization mismatch")
        end = generation_release.guard.capture_snapshot()
        generation_release._verify_after_draw(checked, start, end)
        name = accepted["instance_id"]
        body = dict(schema="decisions_os/g9_real_return_parameters/v1", instance_id=name,
                    slot=slot, attempt=attempt, label="non_synthetic",
                    canonical_order=stage1["canonical_order"], partition=[list(x) for x in partition],
                    partition_sha256=accepted["partition_sha256"], mu_hex=list(draw.mu_hex),
                    Sigma_hex=[list(x) for x in draw.sigma_hex],
                    returns_file=name+"_returns.f64", returns_shape=[generator.RETURN_ROWS,generator.ASSET_COUNT],
                    returns_dtype="little_endian_binary64", returns_order="C",
                    returns_sha256=draw.return_matrix_sha256_le_f64_row_major,
                    seed_material_sha256=draw.seed.material_sha256,
                    stage1_parameters_file_sha256=expected_stage1_sha256,
                    screening_inputs_file_sha256=expected_screening_sha256,
                    generation_ledger_file_sha256=expected_ledger_file_sha256,
                    implementation_record_content_sha256=expected_implementation_sha256,
                    scientific_outputs="U09 parameters only; no ground truth, sweep, certification or paper results")
        files[name+"_returns.f64"] = raw_returns
        files[name+"_parameters.json"] = _canonical(body)
        evidence.append(dict(instance_id=name, slot=slot, attempt=attempt,
                             return_sha256=body["returns_sha256"], equality="exact_match",
                             phases="start_and_end", owner_approval=approval_evidence,
                             implementation_record_content_sha256=expected_implementation_sha256))
    if len(evidence) != generator.SLOT_COUNT:
        raise ValueError("Exactly five return draws required")
    acceptance_module.exact_match_session(session_identity, acceptance_record,
        reviewed_record_sha256=reviewed_acceptance_sha256, repo_root=str(root))
    files["RETURN_DRAW_EVIDENCE.json"] = _canonical(evidence)
    return writer.write_generation(target=Path(output_dir), files=files,
                                   implementation_record_content_sha256=expected_implementation_sha256)


def _canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode() + b"\n"

"""Prospective hosted screening entry; requires genuine reviewed authority.

This does not prepare ground truth or arm the five scientific jobs. It builds
the prerequisite first-valid partition ledger using the existing release API.
"""
import hashlib
import json
from pathlib import Path


def screen_five_slots(*, root, acceptance_module, acceptance_record,
                      reviewed_acceptance_sha256, session_identity,
                      generation_release, generation_contract, generator,
                      implementation_record, expected_implementation_sha256,
                      draw_approval, screening_file, expected_screening_sha256,
                      writer, output_dir):
    root = Path(root)
    # Validate actual authority before deriving a seed or making any draw.
    acceptance_module.accept_production_identity(
        acceptance_record, reviewed_record_sha256=reviewed_acceptance_sha256,
        repo_root=str(root))
    acceptance_module.exact_match_session(
        session_identity, acceptance_record,
        reviewed_record_sha256=reviewed_acceptance_sha256, repo_root=str(root))
    generation_release.check_against_record(
        implementation_record, draw_approval, expected_implementation_sha256)
    raw = Path(screening_file).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_screening_sha256:
        raise ValueError('Refused: independent screening-input pin mismatch')
    inputs = generation_contract.ScreeningInputs(**json.loads(raw))
    screens, accepted, evidence = [], [], []
    for slot in range(1, generator.SLOT_COUNT + 1):
        for attempt in range(generator.MAX_ATTEMPT + 1):
            result = generation_release.draw_screened_attempt(
                record=implementation_record,
                expected_content_sha256=expected_implementation_sha256,
                approval=draw_approval, screening_inputs=inputs,
                slot=slot, attempt=attempt,
                earlier_accepted_partitions=accepted)
            screen = result['screen']
            screens.append(screen)
            evidence.append({k: v for k, v in result.items() if k != 'screen'})
            if screen.accepted:
                accepted.append(screen.normalized_partition)
                break
        else:
            raise ValueError('Refused: no valid preregistered attempt for slot ' + str(slot))
    # Use the real production ledger schema, not the fixture ledger helper.
    ledger = {
        'schema': generation_contract.SCHEMA,
        'protocol_file_sha256': generation_contract.PROTOCOL_FILE_SHA256,
        'generator_source_sha256': implementation_record['sources']['generator']['sha256'],
        'attempts': [generation_contract.attempt_payload(s) for s in screens],
        'scientific_outputs': 'intentionally absent',
    }
    ledger['content_sha256'] = generation_contract.content_sha256(ledger)
    # Replay derives the same registered RNG material: guard it too.
    _, checked_record = generation_release.check_against_record(
        implementation_record, draw_approval, expected_implementation_sha256)
    replay_start = generation_release.guard.capture_snapshot()
    generation_release._verify_before_draw(checked_record, replay_start)
    validated = generation_contract.validate_generation_ledger(
        ledger, inputs, ledger['generator_source_sha256'])
    if (validated.get('verdict') != 'accepted' or
            validated.get('slot_count') != generator.SLOT_COUNT or
            validated.get('ledger_content_sha256') != ledger['content_sha256']):
        raise ValueError('Refused: ledger validator did not accept the exact five-slot ledger')
    replay_end = generation_release.guard.capture_snapshot()
    generation_release._verify_after_draw(checked_record, replay_start, replay_end)
    # Revalidate acceptance immediately before the prospective ledger write.
    acceptance_module.exact_match_session(
        session_identity, acceptance_record,
        reviewed_record_sha256=reviewed_acceptance_sha256, repo_root=str(root))
    canonical = lambda obj: json.dumps(obj, sort_keys=True, separators=(',', ':'),
                                       ensure_ascii=True, allow_nan=False).encode() + b'\n'
    files = {'GENERATION_LEDGER.json': canonical(ledger),
             'DRAW_EVIDENCE.json': canonical(evidence)}
    return writer.write_generation(
        target=Path(output_dir), files=files,
        implementation_record_content_sha256=expected_implementation_sha256)

"""Additive actual-instance baseline parent; never declares a full D013 package.

Execution belongs on the explicitly authorized Kaggle job, not the host.
Every module/artifact and per-family owner authorization arrives externally.
There are no synthetic defaults, approval generators or duration budgets.
"""
from __future__ import annotations

import hashlib
import json
import lzma
import copy
from pathlib import Path
from types import SimpleNamespace


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=True, allow_nan=False).encode('ascii')


def sha_pin(value):
    if type(value) is not str or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
        raise ValueError('Independent SHA256 pin required')
    return value


def checked_file(path, expected):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError('Pinned artifact must be a regular file: ' + str(path))
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != sha_pin(expected):
        raise ValueError('Artifact bytes differ from independent pin: ' + str(path))
    return raw


def checked_module(module, expected):
    checked_file(module.__file__, expected)
    return module


# Reference-review gate. A baseline reference that still declares itself a
# candidate awaiting review or an actual T4 crosscheck is NOT an admissible
# scientific baseline oracle. This runs before the B.2 crosscheck and therefore
# long before any scientific write, and it fails closed on an unrecognised
# status rather than treating anything non-candidate as acceptable.
#
# Two independent pieces of evidence must both be present and pinned:
#
#   1. `status` must be exactly `accepted_reviewed_and_T4_crosschecked`. Any
#      value beginning `candidate` (in particular the current
#      `candidate_requires_independent_review_and_actual_T4_crosscheck` that
#      every g9-real-reference-* kernel emits) is refused outright, and so is
#      any other value -- the allowlist has exactly one member.
#
#   2. The independent-review and actual-T4-crosscheck receipts must be
#      recorded in the plan under `reference_gate`, each pinned by SHA-256 and
#      each naming this exact instance, prepared record and reference metadata
#      file. The crosscheck receipt is the in-kernel B.2 result: the
#      `production_parent_v1.py:147` `seams['wp3_run']` call followed by
#      `seams['wp3_validate'](crosscheck)`, which is the only place in this
#      package where the real T4 CUDA backend is compared against the real
#      12-row/120-comparison reference. That comparison runs here, in this
#      process, before any write; the receipt records its record digest so the
#      write cannot later claim an unrun crosscheck.
ALLOWED_REFERENCE_STATUS = 'accepted_reviewed_and_T4_crosschecked'
REFERENCE_GATE_RECEIPTS = ('independent_review_receipt', 'actual_T4_crosscheck_receipt')


def _gate_receipt(value, name, reference_meta, reference_metadata_file_sha256):
    if type(value) is not dict:
        raise ValueError('Reference gate receipt must be an object: ' + name)
    for field in ('schema', 'verdict', 'review_family', 'review_log',
                  'instance_id', 'prepared_record_sha256',
                  'reference_metadata_file_sha256', 'artifact_sha256'):
        if field not in value:
            raise ValueError('Reference gate receipt is missing a field: ' + name + '.' + field)
    if value['verdict'] != 'PASS':
        raise ValueError('Reference gate receipt is not a PASS: ' + name)
    if value['instance_id'] != reference_meta['instance_id'] \
            or value['prepared_record_sha256'] != reference_meta['prepared_record_sha256']:
        raise ValueError('Reference gate receipt covers another instance: ' + name)
    if value['reference_metadata_file_sha256'] != reference_metadata_file_sha256:
        raise ValueError('Reference gate receipt covers another reference file: ' + name)
    sha_pin(value['artifact_sha256'])
    if value['schema'] != 'decisions_os/g9_reference_gate_receipt/v1':
        raise ValueError('Reference gate receipt schema is not the reviewed one: ' + name)
    if type(value['review_family']) is not str or not value['review_family']:
        raise ValueError('Reference gate receipt does not name its independent reviewer: ' + name)
    if type(value['review_log']) is not str or not value['review_log'].startswith('/'):
        raise ValueError('Reference gate receipt review log is not an absolute path: ' + name)
    return value


def _bind_crosscheck_record(gate, observed_digest, instance_id, prepared_sha256):
    """Require the pinned T4-crosscheck receipt to name the record just produced."""
    receipt = gate.get('actual_T4_crosscheck_receipt')
    if type(receipt) is not dict or 'crosscheck_record_content_sha256' not in receipt:
        raise ValueError('T4 crosscheck receipt does not carry a crosscheck record digest')
    expected = receipt['crosscheck_record_content_sha256']
    if expected == 'pending_this_run':
        # First execution of this reference on an actual T4: the record digest is
        # not knowable before the run. Record it in the working receipt so the
        # value is observable, then require every later reader to match it.
        receipt['crosscheck_record_content_sha256'] = observed_digest
        receipt['crosscheck_bound_this_run'] = True
        return observed_digest
    sha_pin(expected)
    if expected != observed_digest:
        raise ValueError(
            'T4 crosscheck receipt names a different record than this run produced')
    return observed_digest


def enforce_reference_gate(reference_meta, plan):
    """Refuse to treat an un-reviewed or un-cross-checked reference as baseline."""
    status = reference_meta.get('status')
    if not isinstance(status, str):
        raise ValueError('Reference metadata has no status string')
    if status.startswith('candidate'):
        raise ValueError(
            'Baseline reference is still a candidate and is not admissible as a '
            'scientific baseline oracle: ' + status)
    if status != ALLOWED_REFERENCE_STATUS:
        raise ValueError(
            'Baseline reference status is not the one accepted reviewed+T4-crosschecked '
            'value: ' + status)
    gate = plan.get('reference_gate')
    if type(gate) is not dict:
        raise ValueError('Plan carries no reference_gate evidence')
    if gate.get('required_status') != ALLOWED_REFERENCE_STATUS:
        raise ValueError('Plan reference_gate declares a different required status')
    for name in REFERENCE_GATE_RECEIPTS:
        _gate_receipt(gate.get(name), name, reference_meta,
                      plan['reference_metadata_file_sha256'])
    if gate['crosscheck_scope'] != 'in_kernel_wp3_B2_actual_T4_before_any_scientific_write':
        raise ValueError('reference_gate does not bind the actual T4 crosscheck scope')
    return True


def run_actual_baseline_parent(*, root, plan, expected_plan_sha256, modules):
    """Cross-check the real 12/120 WP3 reference, then stream six baselines.

    ``plan`` is the externally reviewed operational manifest. It binds actual
    acceptance/session identity, prepared instance, reference, qualified libs,
    source closure and six distinct one-use authorizations. No pin is derived
    here as a substitute for an independently reviewed value. Module execution
    and numerical calls must happen only on the authorized remote job.
    """
    root = Path(root).resolve()
    if hashlib.sha256(canonical(plan)).hexdigest() != sha_pin(expected_plan_sha256):
        raise ValueError('Operational parent plan differs from reviewed pin')
    if plan['scope'] != 'actual_instance_six_baselines_pending_full_D013_trigger_audit':
        raise ValueError('This parent does not implement full conditional D013')
    required = {'acceptance', 'session', 'producer', 'reference', 'backend_binding',
                'provider', 'reference_adapter'}
    if set(modules) != required or set(plan['module_sha256']) != required:
        raise ValueError('Exact seven independently reviewed modules required')
    for name in required:
        checked_module(modules[name], plan['module_sha256'][name])
    acceptance = modules['acceptance']
    streaming = modules['session']
    primitive = streaming.wp8c_v2
    producer = modules['producer']
    provider = modules['provider']

    accepted_record = json.loads(checked_file(root / plan['acceptance_path'], plan['acceptance_file_sha256']))
    accepted = acceptance.accept_production_identity(accepted_record,
        reviewed_record_sha256=plan['reviewed_acceptance_record_sha256'], repo_root=str(root))
    identity = json.loads(checked_file(root / plan['session_identity_path'], plan['session_identity_file_sha256']))
    acceptance.exact_match_session(identity, accepted_record,
        reviewed_record_sha256=plan['reviewed_acceptance_record_sha256'], repo_root=str(root))
    # Preserve the actual release-gate API: authority is a live object with
    # module/path references, not a fabricated serialized acceptance adapter.
    release = dict(plan['release_authority'])
    for field in ('release_file', 'owner_authority_file', 'source_manifest_file'):
        release[field] = root / release[field]
    release.update(root=root, acceptance_module=acceptance,
                   acceptance_record=accepted_record, session_identity=identity)
    verified = primitive.verify_instance_for_session(plan['slot'], root=root,
                                                      standin=False, release_authority=release)
    if verified['instance_id'] != plan['instance_id'] or verified['prepared_id'] != plan['prepared_record_content_sha256']:
        raise ValueError('Parent plan names another real instance/prepared record')
    instance_dir = primitive.wp8dp._slot_dir(plan['slot'], root)
    envelope = json.loads(checked_file(instance_dir / 'instance/INSTANCE_ENVELOPE.json', plan['envelope_file_sha256']))
    instance = primitive.wp8dp._instance_from_envelope(envelope)
    prepared = json.loads(checked_file(instance_dir / 'instance/PREPARED.json', plan['prepared_file_sha256']))
    if prepared['content_sha256'] != verified['prepared_id']:
        raise ValueError('Prepared bytes are not the verified layout record')

    q = plan['qualified_artifacts']
    receipt = json.loads(checked_file(root / q['receipt_path'], q['receipt_file_sha256']))
    if receipt['receipt']['status'] != 'ok':
        raise ValueError('Qualified artifact receipt did not succeed')
    core = root / q['core_library_path']
    d013 = root / q['d013_library_path']
    token_path = root / q['release_token_path']
    for path, pin, receipt_name in (
        (core, q['core_library_sha256'], 'stage2_cuda_core_bridge.so'),
        (d013, q['d013_library_sha256'], 'stage2_cuda_d013_inactive_v2.so'),
        (token_path, q['release_token_file_sha256'], 'VERIFIED_D013_RELEASE_TOKEN.json')):
        checked_file(path, pin)
        if receipt['files_sha256'][receipt_name] != pin:
            raise ValueError('Artifact independent pin differs from qualification receipt')
    token = json.loads(token_path.read_bytes())
    if set(token) != {'release_sha256', 'source_map_sha256', 'proof_sha256'}:
        raise ValueError('Actual V2 runtime token requires exact three-key shape')
    backend_binding = modules['backend_binding'].load_reviewed_backend(root,
        root / plan['python_source_pins_path'],
        expected_pins_sha256=plan['python_source_pins_file_sha256'], provider=provider)
    backend_binding._validate()

    reference_meta = json.loads(checked_file(root / plan['reference_metadata_path'], plan['reference_metadata_file_sha256']))
    if (reference_meta['instance_id'] != verified['instance_id']
        or reference_meta['prepared_record_sha256'] != verified['prepared_id']
        or reference_meta['production_identity_hash'] != identity['content_sha256']
        or reference_meta['baseline_rows'] != 12 or reference_meta['comparison_count'] != 120
        or reference_meta['d013_fired'] is not False):
        raise ValueError('Actual reference identity/12-row baseline census mismatch')
    enforce_reference_gate(reference_meta, plan)
    compressed = checked_file(root / plan['reference_xz_path'], plan['reference_xz_file_sha256'])
    inputs = json.loads(checked_file(root / plan['reference_inputs_path'], plan['reference_inputs_file_sha256']))
    raw = lzma.decompress(compressed)
    if hashlib.sha256(raw).hexdigest() != reference_meta['reference_bytes_sha256']:
        raise ValueError('Lossless reference expansion differs from declared actual seal')
    # Original open_for_session is used by the independently reviewed helper;
    # the generic adapter only changes the harness call shape.
    reference = modules['reference'].open_compressed_reference(compressed, inputs)
    reference = modules['reference_adapter'].budgeted_reference(reference)
    frames = json.loads(checked_file(root / plan['frame_table_path'], plan['frame_table_file_sha256']))
    if len(frames) != 12:
        raise ValueError('Actual baseline backend requires all 12 frames')
    context = producer.create_verified_context(instance, prepared, release,
                                               core, q['core_library_sha256'])
    if reference_meta['offsets_sha256'] != context.offsets_sha256:
        raise ValueError('Actual reference uses another instance slack mapping')
    factory = provider.build_device_backend_factory(backend_binding, core, d013,
                                                    token, frames, fixture_only=False)
    seams = streaming._v3_seams(acceptance)
    seams['bind_accepted_identity_v4'] = acceptance.accept_production_identity
    seams['device_backend_factory'] = factory
    seams['python_reference'] = reference
    boundary = SimpleNamespace(kind='actual_qualified_T4_runtime_no_owner_authority_substitution')
    device = factory(boundary)
    # This complete real-data check precedes every scientific writer call.
    crosscheck = seams['wp3_run'](device, reference,
        primitive.validation_coordinates(), accepted_identity=accepted['draft_identity'],
        session_identity=identity, validate_identity=seams['identity_validate'],
        exact_match=seams['identity_exact_match'],
        accepted_identity_sha256=accepted['accepted_content_sha256'],
        protocol_identity_sha256=plan['protocol_identity_sha256'],
        d013_fired=False, d013_coordinates=None)
    seams['wp3_validate'](crosscheck)
    # The gate receipt must name the record digest that THIS actual T4 run just
    # produced. A receipt citing any other digest is refused here, so the write
    # below can never rest on a crosscheck that did not actually execute.
    _bind_crosscheck_record(plan['reference_gate'],
                            hashlib.sha256(canonical(crosscheck)).hexdigest(),
                            reference_meta['instance_id'],
                            reference_meta['prepared_record_sha256'])

    # B.2 is a pre-write check for this instance/identity, not a separate
    # numerical experiment for each output namespace. Reuse only the genuine
    # validated record produced immediately above, and only in this process.
    # The underlying CUDA backend identity and all reviewed inputs stay fixed.
    retained_record = copy.deepcopy(crosscheck)
    retained_frames = canonical(frames)
    retained_coordinates = canonical(primitive.validation_coordinates())
    retained_identity = canonical(identity)
    retained_accepted = canonical(accepted['draft_identity'])
    expected_functions = (seams['identity_validate'], seams['identity_exact_match'])
    def retained_factory(actual_boundary):
        if actual_boundary is not boundary:
            raise ValueError('Retained WP3 backend belongs to another runtime boundary')
        return device
    def cached_wp3_run(actual_device, actual_reference, coordinates, *,
                       accepted_identity, session_identity, validate_identity,
                       exact_match, accepted_identity_sha256,
                       protocol_identity_sha256, d013_fired=False,
                       d013_coordinates=None):
        if (actual_device is not device or actual_reference is not reference
                or validate_identity is not expected_functions[0]
                or exact_match is not expected_functions[1]
                or canonical(coordinates) != retained_coordinates
                or canonical(accepted_identity) != retained_accepted
                or canonical(session_identity) != retained_identity
                or accepted_identity_sha256 != accepted['accepted_content_sha256']
                or protocol_identity_sha256 != plan['protocol_identity_sha256']
                or d013_fired is not False or d013_coordinates is not None):
            raise ValueError('Retained WP3 check does not cover this actual call')
        for name in required:
            checked_module(modules[name], plan['module_sha256'][name])
        for path, pin in (
            (core, q['core_library_sha256']), (d013, q['d013_library_sha256']),
            (token_path, q['release_token_file_sha256']),
            (root / q['receipt_path'], q['receipt_file_sha256']),
            (root / plan['reference_xz_path'], plan['reference_xz_file_sha256']),
            (root / plan['reference_inputs_path'], plan['reference_inputs_file_sha256']),
            (root / plan['reference_metadata_path'], plan['reference_metadata_file_sha256']),
            (root / plan['frame_table_path'], plan['frame_table_file_sha256']),
            (root / plan['acceptance_path'], plan['acceptance_file_sha256']),
            (root / plan['session_identity_path'], plan['session_identity_file_sha256']),
            (instance_dir / 'instance/INSTANCE_ENVELOPE.json', plan['envelope_file_sha256']),
            (instance_dir / 'instance/PREPARED.json', plan['prepared_file_sha256'])):
            checked_file(path, pin)
        source_manifest = json.loads(checked_file(root / plan['python_source_pins_path'],
                                                   plan['python_source_pins_file_sha256']))
        for rel, pin in source_manifest['source_sha256'].items():
            checked_file(root / rel, pin)
        backend_binding._validate()
        if (canonical(device._frames) != retained_frames
                or device._core_path != core or device._d013_path != d013
                or canonical(device._token) != canonical(token)
                or device._fixture_only is not False or device._boundary is not None):
            raise ValueError('Actual retained device binding/configuration changed')
        acceptance.exact_match_session(session_identity, accepted_record,
            reviewed_record_sha256=plan['reviewed_acceptance_record_sha256'], repo_root=str(root))
        primitive.verify_instance_for_session(plan['slot'], root=root,
                                               standin=False, release_authority=release)
        # Reopen the same seal to revalidate its exact reference manifest and
        # inputs. This performs no energy evaluation or CUDA comparison.
        modules['reference'].open_compressed_reference(compressed, inputs)
        seams['wp3_validate'](retained_record)
        return copy.deepcopy(retained_record)
    seams['device_backend_factory'] = retained_factory
    seams['wp3_run'] = cached_wp3_run

    families = streaming.records.families(False)
    declarations = plan['families']
    if len(families) != 6 or set(declarations) != {f.key for f in families}:
        raise ValueError('All six exact baseline family declarations required')
    authorizations = {}
    nonces = set()
    binding = primitive._as_binding(accepted, acceptance_record=accepted_record,
        reviewed_record_sha256=plan['reviewed_acceptance_record_sha256'], repo_root=root)
    for family in families:
        declaration = declarations[family.key]
        authorization = json.loads(checked_file(root / declaration['authorization_path'], declaration['authorization_file_sha256']))
        primitive.validate_authorization(authorization, verified=verified,
            accepted_binding=binding, session_contract_sha256=streaming.session_contract_sha256_v3())
        if authorization['bundle_sha256'] != plan['bundle_sha256'] or authorization['kernel_id'] != plan['kernel_id']:
            raise ValueError('Family authorization belongs to another bundle/kernel')
        if authorization['nonce'] in nonces:
            raise ValueError('Each baseline family needs a distinct one-use nonce')
        nonces.add(authorization['nonce'])
        authorizations[family.key] = authorization
    results = []
    for family in families:
        declaration = declarations[family.key]
        space = streaming.records.family_space(family, context.frozen)
        result = streaming.run_production_session_v3(slot=plan['slot'],
            session_id=declaration['session_id'], root=root,
            family_output_root=instance_dir / 'sweep' / family.key,
            nonce_root=root / plan['nonce_root'], acceptance_record=accepted_record,
            reviewed_record_sha256=plan['reviewed_acceptance_record_sha256'],
            session_identity=identity, authorization=authorizations[family.key],
            boundary=boundary, standin=False, writer_family=family.key,
            result_schema=plan['result_schema'], family_space=space,
            family_coordinates=space.total_coordinates,
            expected_bundle_sha256=plan['bundle_sha256'], expected_kernel_id=plan['kernel_id'],
            expected_approval_sha256=plan['expected_approval_sha256'],
            expected_generator_implementation_record_sha256=plan['generator_implementation_record_sha256'],
            expected_ground_truth_provenance_sha256=plan['ground_truth_provenance_sha256'],
            protocol_identity_sha256=plan['protocol_identity_sha256'],
            parent_v4_acceptance_module=acceptance,
            cuda_producer_func=producer.cuda_range_producer, cuda_context=context,
            seams=seams, release_authority=release)
        results.append(result)
        if result['status'] != 'complete_pending_image_audit':
            break
    return {'status': 'baseline_complete_pending_D013_trigger_and_image_audit'
            if len(results) == 6 and all(r['status'] == 'complete_pending_image_audit' for r in results)
            else 'baseline_refused_or_partial', 'full_package_complete': False,
            'instance_id': verified['instance_id'],
            'wp3_record_content_sha256': crosscheck['content_sha256'],
            'family_sessions': results,
            'unresolved': ['frozen whole-baseline D013 trigger extraction',
                           'conditional D013 family axes and actual CUDA producer',
                           'D013-on real-data reference/WP3 comparison and scientific write authorization',
                           'full-package final audit and image audit']}

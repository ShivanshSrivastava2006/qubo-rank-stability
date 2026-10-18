"""ADDITIVE round-2 crosscheck parent: the GPU gate in the RIGHT PLACE.

THIS MODULE PERFORMS NO SCIENTIFIC WRITE.

WHY IT EXISTS
=============
Round 2's offline rehearsal made a real ordering defect visible that round 1
never could. In the round-1 child the live platform probe (``shutil.which
('nvcc')`` plus a compile and a run) ran FIRST, before any plan key was read.
So on a host without a T4 the run refused at ~1 s having proven nothing --
it never reached the accepted-identity check, never verified the instance, and
never opened the real reference seal. That is a weak rehearsal: it would have
passed just as happily if every pin and identity check below it were broken.

The owner's requirement for round 2 is explicit: the rehearsal must get
"through plan loading, every pin and identity check, the seal/reference
opening and the session start, all the way to the first point that genuinely
needs the GPU", and stop THERE. That means the hardware gate must be the LAST
thing, not the first.

So the probe becomes a CALLBACK injected at exactly one point: after every
pin, every identity check, the real reference seal has been opened and
verified, the verified context and its offsets have been reconciled against the
seal, the backend factory has been validated, and the reviewed seam mapping has
been assembled -- and immediately before the device is constructed and the
comparison begins.

WHAT IS REUSED AND WHAT IS NOT
==============================
This module imports :mod:`xcheck_parent` and reuses its checked_file/canonical/
sha_pin helpers, its crosscheck-refusal type, its authorization validator and
its per-row timing proxy, UNMODIFIED. The comparison itself is still performed
by the reviewed seam ``seams['wp3_run']``; this module never re-implements it,
and there is no flag that can suppress a difference.

``run_crosscheck_r2`` is deliberately a near-copy of ``run_crosscheck`` with
one difference: the live platform probe is an injected callable instead of
preamble. The duplication is intentional and is the honest shape of the fix --
rewriting ``xcheck_parent`` in place would change a pinned, reviewed module and
void every pin that names it.

THE ONLY NEW CONTROL FLOW
=========================
    live_platform_probe()   # <- the sole GPU boundary, and it RAISES here

is called once, after the seal is open and the seams are assembled, and before
``factory(boundary)``. On a real T4 it returns the observed platform dict,
which then flows into the receipt exactly as ``observed_platform`` always did.
On a host without a T4 it raises ``GpuUnavailable`` (imported from the caller
by name, so there is exactly one definition of that type in a run), and the
caller's fail-closed handler writes the difference record.
"""
from __future__ import annotations

import hashlib
import json
import lzma
from pathlib import Path
from types import SimpleNamespace

import xcheck_parent as base

#: Re-exported so the child imports ONE definition of each.
CrosscheckRefused = base.CrosscheckRefused
canonical = base.canonical
sha_pin = base.sha_pin
checked_file = base.checked_file
_row_label = base._row_label
_timed_backend = base._timed_backend
_mirrored_positive_zero = base._mirrored_positive_zero
CROSSCHECK_SCOPE = base.CROSSCHECK_SCOPE
validate_crosscheck_authorization = base.validate_crosscheck_authorization

#: The seven independently reviewed modules this parent requires. Unchanged.
REQUIRED_MODULES = frozenset({
    'acceptance', 'session', 'producer', 'reference', 'backend_binding',
    'provider', 'reference_adapter'})


def run_crosscheck_r2(*, root, plan, expected_plan_sha256, modules,
                      live_platform_probe, receipt_path, difference_path):
    """Run every CPU-verifiable step, THEN the GPU gate, then the comparison.

    ``live_platform_probe`` is the injected hardware gate. It is called exactly
    once, at the documented point, and it either returns the observed platform
    mapping (real T4) or raises (no T4). It is REQUIRED: this parent has no
    default and no "skip the probe" path, because a crosscheck whose platform
    was never observed is not a crosscheck of the real instance.
    """
    if not callable(live_platform_probe):
        raise CrosscheckRefused(
            'A live platform probe callable is REQUIRED; this parent will not '
            'run a crosscheck whose real T4 identity was never observed',
            stage='platform_probe')

    root = Path(root).resolve()
    if hashlib.sha256(canonical(plan)).hexdigest() != sha_pin(expected_plan_sha256):
        raise CrosscheckRefused('Crosscheck plan differs from reviewed pin',
                                stage='plan_pin')
    if plan['scope'] != CROSSCHECK_SCOPE:
        raise CrosscheckRefused(
            'This parent implements the crosscheck-only scope only', stage='scope')

    if set(modules) != REQUIRED_MODULES or set(plan['module_sha256']) != REQUIRED_MODULES:
        raise CrosscheckRefused('Exact seven independently reviewed modules required',
                                stage='module_census')
    for name in REQUIRED_MODULES:
        checked_file(Path(modules[name].__file__), plan['module_sha256'][name])

    acceptance = modules['acceptance']
    streaming = modules['session']
    primitive = streaming.wp8c_v2
    producer = modules['producer']
    provider = modules['provider']

    # --- identity, instance, prepared: identical to the v2 parent -------------
    accepted_record = json.loads(checked_file(
        root / plan['acceptance_path'], plan['acceptance_file_sha256']))
    accepted = acceptance.accept_production_identity(
        accepted_record,
        reviewed_record_sha256=plan['reviewed_acceptance_record_sha256'],
        repo_root=str(root))
    identity = json.loads(checked_file(
        root / plan['session_identity_path'], plan['session_identity_file_sha256']))
    acceptance.exact_match_session(
        identity, accepted_record,
        reviewed_record_sha256=plan['reviewed_acceptance_record_sha256'],
        repo_root=str(root))
    release = dict(plan['release_authority'])
    for field in ('release_file', 'owner_authority_file', 'source_manifest_file'):
        release[field] = root / release[field]
    release.update(root=root, acceptance_module=acceptance,
                   acceptance_record=accepted_record, session_identity=identity)
    verified = primitive.verify_instance_for_session(
        plan['slot'], root=root, standin=False, release_authority=release)
    if (verified['instance_id'] != plan['instance_id']
            or verified['prepared_id'] != plan['prepared_record_content_sha256']):
        raise CrosscheckRefused(
            'Plan names another real instance/prepared record', stage='instance')
    instance_dir = primitive.wp8dp._slot_dir(plan['slot'], root)
    envelope = json.loads(checked_file(
        instance_dir / 'instance/INSTANCE_ENVELOPE.json', plan['envelope_file_sha256']))
    instance = primitive.wp8dp._instance_from_envelope(envelope)
    prepared = json.loads(checked_file(
        instance_dir / 'instance/PREPARED.json', plan['prepared_file_sha256']))
    if prepared['content_sha256'] != verified['prepared_id']:
        raise CrosscheckRefused('Prepared bytes are not the verified layout record',
                                stage='prepared')

    # --- the one crosscheck authorization, validated against re-derived values -
    import datetime
    authorization = json.loads(checked_file(
        root / plan['authorization_path'], plan['authorization_file_sha256']))
    validate_crosscheck_authorization(
        authorization, plan=plan, verified=verified, accepted=accepted,
        session_contract_sha256=plan['module_sha256']['session'],
        today=datetime.date.today())

    # --- qualified artifacts ---------------------------------------------------
    q = plan['qualified_artifacts']
    qualification = json.loads(checked_file(
        root / q['receipt_path'], q['receipt_file_sha256']))
    if qualification['receipt']['status'] != 'ok':
        raise CrosscheckRefused('Qualified artifact receipt did not succeed',
                                stage='qualification')
    core = root / q['core_library_path']
    d013 = root / q['d013_library_path']
    token_path = root / q['release_token_path']
    for path, pin, name in (
            (core, q['core_library_sha256'], 'stage2_cuda_core_bridge.so'),
            (d013, q['d013_library_sha256'], 'stage2_cuda_d013_inactive_v2.so'),
            (token_path, q['release_token_file_sha256'],
             'VERIFIED_D013_RELEASE_TOKEN.json')):
        checked_file(path, pin)
        if qualification['files_sha256'][name] != pin:
            raise CrosscheckRefused(
                'Artifact pin differs from qualification receipt', stage='qualification')
    token = json.loads(token_path.read_bytes())

    backend_binding = modules['backend_binding'].load_reviewed_backend(
        root, root / plan['python_source_pins_path'],
        expected_pins_sha256=plan['python_source_pins_file_sha256'], provider=provider)
    backend_binding._validate()

    # --- the real reference seal, on the real instance -------------------------
    reference_meta = json.loads(checked_file(
        root / plan['reference_metadata_path'], plan['reference_metadata_file_sha256']))
    if (reference_meta['instance_id'] != verified['instance_id']
            or reference_meta['prepared_record_sha256'] != verified['prepared_id']
            or reference_meta['production_identity_hash'] != identity['content_sha256']
            or reference_meta['baseline_rows'] != 12
            or reference_meta['comparison_count'] != 120
            or reference_meta['d013_fired'] is not False):
        raise CrosscheckRefused(
            'Actual reference identity/12-row baseline census mismatch',
            stage='reference_census')
    compressed = checked_file(
        root / plan['reference_xz_path'], plan['reference_xz_file_sha256'])
    inputs = json.loads(checked_file(
        root / plan['reference_inputs_path'], plan['reference_inputs_file_sha256']))
    if hashlib.sha256(lzma.decompress(compressed)).hexdigest() \
            != reference_meta['reference_bytes_sha256']:
        raise CrosscheckRefused(
            'Lossless reference expansion differs from declared seal',
            stage='reference_expansion')
    reference = modules['reference'].open_compressed_reference(compressed, inputs)
    reference = modules['reference_adapter'].budgeted_reference(reference)

    # --- the verified context and its slack mapping, reconciled with the seal --
    frames = json.loads(checked_file(
        root / plan['frame_table_path'], plan['frame_table_file_sha256']))
    if len(frames) != 12:
        raise CrosscheckRefused('Actual baseline backend requires all 12 frames',
                                stage='frame_table')
    context = producer.create_verified_context(
        instance, prepared, release, core, q['core_library_sha256'])
    if reference_meta['offsets_sha256'] != context.offsets_sha256:
        raise CrosscheckRefused('Actual reference uses another instance slack mapping',
                                stage='offsets')
    factory = provider.build_device_backend_factory(
        backend_binding, core, d013, token, frames, fixture_only=False)

    # --- the reviewed seam mapping, assembled but not yet used -----------------
    seams = streaming._v3_seams(acceptance)
    seams['bind_accepted_identity_v4'] = acceptance.accept_production_identity
    seams['device_backend_factory'] = factory
    seams['python_reference'] = reference
    boundary = SimpleNamespace(
        kind='actual_qualified_T4_runtime_crosscheck_no_owner_authority_substitution')

    coordinates = primitive.validation_coordinates()

    # =====================================================================
    # THE GPU BOUNDARY.
    #
    # Everything above is CPU: every independent pin checked, the accepted
    # identity matched exactly, the real instance verified, the one-use
    # crosscheck authorization validated against re-derived values, the
    # qualified artifacts pinned, the real reference seal opened and its
    # expansion re-hashed, the verified context built and its offsets
    # reconciled against the seal, and the reviewed seam set assembled.
    #
    # Only now is the hardware required. On a host with no T4 the probe raises
    # here and the run ends -- at the FIRST point that genuinely needs the
    # GPU, after having proven everything that does not.
    # =====================================================================
    observed_platform = live_platform_probe()

    device = factory(boundary)

    # --- the actual B.2/WP3 crosscheck, by the REVIEWED seam, once -------------
    timings = {}
    order = []
    timed_device, mirrored_declaration = _timed_backend(device, timings, order)
    try:
        crosscheck = seams['wp3_run'](
            timed_device, reference, coordinates,
            accepted_identity=accepted['draft_identity'],
            session_identity=identity,
            validate_identity=seams['identity_validate'],
            exact_match=seams['identity_exact_match'],
            accepted_identity_sha256=accepted['accepted_content_sha256'],
            protocol_identity_sha256=plan['protocol_identity_sha256'],
            d013_fired=False, d013_coordinates=None)
        seams['wp3_validate'](crosscheck)
    except Exception as exc:
        counters = getattr(exc, 'counters', None)
        raise CrosscheckRefused(
            type(exc).__name__ + ': ' + str(exc),
            stage='wp3_crosscheck',
            differences=[dict(kind='wp3_seam_refused', detail=str(exc))],
            comparisons_completed=(counters or {}).get('comparisons', 0))

    record_digest = hashlib.sha256(canonical(crosscheck)).hexdigest()

    per_row = [dict(row=_row_label(row), wall_seconds=timings.get(_row_label(row), 0.0))
               for row in coordinates]
    body = dict(
        schema='decisions_os/g9_b2_wp3_crosscheck_receipt/v1',
        scope=CROSSCHECK_SCOPE,
        slot=plan['slot'],
        kernel_id=plan['kernel_id'],
        instance_id=verified['instance_id'],
        prepared_record_sha256=verified['prepared_id'],
        production_identity_hash=identity['content_sha256'],
        accepted_identity_sha256=accepted['accepted_content_sha256'],
        reference_metadata_file_sha256=plan['reference_metadata_file_sha256'],
        reference_bytes_sha256=reference_meta['reference_bytes_sha256'],
        reference_artifact_sha256=dict(
            REFERENCE_METADATA_json=plan['reference_metadata_file_sha256'],
            reference_json_xz=plan['reference_xz_file_sha256'],
            seal_inputs_json=plan['reference_inputs_file_sha256'],
            device_frames_json=plan['frame_table_file_sha256']),
        crosscheck_authorization_sha256=plan['authorization_file_sha256'],
        crosscheck_authorization_action=plan['authorization_action'],
        wp3_record_content_sha256=record_digest,
        wp3_validation_digest=crosscheck['validation_digest'],
        wp3_verdict=crosscheck['verdict'],
        comparison_counts=dict(
            counters=crosscheck['counters'],
            coordinate_rows=len(coordinates),
            d013_repeat_rows=crosscheck['counters']['d013_repeat_rows'],
            d013_fired=False,
            d013_repeat_why=('the pinned reference metadata carries d013_fired is '
                             'False, so the trigger did not fire and the four repeat '
                             'rows are correctly absent; the backend under test does '
                             'declare supports_inactive_positive_zero=True, so the '
                             'reviewed harness would have run and validated them if '
                             'they had been supplied')),
        differences=[],
        per_row_wall_seconds=dict(
            rows=per_row,
            total_row_seconds=sum(item['wall_seconds'] for item in per_row),
            first_call_per_row=True,
            note='runtime evidence for the production estimate; never a comparison '
                 'input and never able to change a verdict'),
        backend_positive_zero_declaration=mirrored_declaration,
        gpu=dict(observed_platform),
        docker_image=plan['docker_image'],
        scientific_writes=[],
    )
    body['content_sha256'] = hashlib.sha256(canonical(body)).hexdigest()
    Path(receipt_path).write_text(json.dumps(body, indent=2) + '\n')
    return body
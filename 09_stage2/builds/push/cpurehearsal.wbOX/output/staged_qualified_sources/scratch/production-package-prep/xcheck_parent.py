"""Additive B.2/WP3 crosscheck parent for one real slot on an actual T4.

THIS MODULE PERFORMS NO SCIENTIFIC WRITE.

It runs the reviewed, pinned, in-kernel B.2/WP3 baseline crosscheck -- the actual
Python reference seal against the real CUDA backend on the real instance, over
every required comparison (all five D015 comparator pairs, both encodings) -- and
then STOPS. It writes no WP4b production range, no family sweep, no full-record
stream and consumes no nonce. It calls
``production_parent_v2``'s helpers only; it does not import
``run_actual_baseline_parent`` and therefore cannot reach a writer.

What it emits is exactly one artifact: CROSSCHECK_RECEIPT.json, a pure
description of THIS run -- instance/prepared/reference hashes, the four reference
artifact hashes, the WP3 record content digest, the comparison counts, any
differences (always empty, because the run is fail-closed), the per-row wall time
for every WP3 row with the T4 GPU name, the image, and a SHA-256 of its own
canonical body.

THE RUN IS FAIL-CLOSED AND USES THE REVIEWED COMPARISON, NOT A REPLICA.
The comparison itself is performed by the reviewed seam
``seams['wp3_run']`` -> ``stage2_section_b2_harness.run_section_b2``, which
refuses on the FIRST bit-for-bit difference and returns no record. This module
therefore never re-implements the comparison: it calls the reviewed seam once and
converts any refusal into a difference record plus a non-zero exit. There is no
flag that suppresses a difference.

WHY THE D013 REPEAT ROWS ARE ZERO IN THIS KERNEL
The pinned reference metadata is required, and required to carry
``d013_fired is False`` (the same census check ``production_parent_v2`` makes at
its own reference check). The D013 repeat rows exist only when the trigger fires,
so they cannot fire in a kernel whose reference is pinned unfired. The backend
under test (``Wp7bDeviceBackend``) does declare
``supports_inactive_positive_zero = True``, so the reviewed harness would run and
validate the four repeat rows if they were ever supplied; this kernel supplies
none because its own pinned evidence says the trigger did not fire. The receipt
states this explicitly rather than leaving the zero ambiguous.

TIMING IS EVIDENCE, NEVER A COMPARISON INPUT
The device backend is called through a proxy whose only added behaviour is to
record, per WP3 row, the wall time of that row's FIRST ``(row, pair, encoding)``
call -- the reviewed backend caches per row, so that first call is where the
row's CUDA work happens. The proxy mirrors the real backend's
``supports_inactive_positive_zero`` class declaration, read STATICALLY with
``inspect.getattr_static`` so no backend code runs to answer it, and records the
mirrored value in the receipt. Both the timings and the declaration are recorded
as runtime evidence; neither is compared, and neither can change a verdict.
"""
from __future__ import annotations

import hashlib
import inspect
import json
import lzma
import time
from pathlib import Path
from types import SimpleNamespace

#: The +0.0 capability declaration name, quoted from the reviewed harness
#: (``stage2_section_b2_harness.POSITIVE_ZERO_DECLARATION``) and read statically.
POSITIVE_ZERO_DECLARATION = 'supports_inactive_positive_zero'

CROSSCHECK_SCOPE = 'actual_instance_b2_wp3_crosscheck_only_no_scientific_write'


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=True, allow_nan=False).encode('ascii')


def sha_pin(value):
    if type(value) is not str or len(value) != 64 or any(
            c not in '0123456789abcdef' for c in value):
        raise ValueError('Independent SHA256 pin required')
    return value


def checked_file(path, expected):
    """Byte-identical to production_parent_v2.checked_file, so is the pin discipline."""
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError('Pinned artifact must be a regular file: ' + str(path))
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != sha_pin(expected):
        raise ValueError('Artifact bytes differ from independent pin: ' + str(path))
    return raw


class CrosscheckRefused(ValueError):
    """Any refusal or difference. Carries the fail-closed difference record."""

    def __init__(self, message, *, stage, differences=None, comparisons_completed=0):
        super().__init__(message)
        self.stage = stage
        self.differences = differences or []
        self.comparisons_completed = comparisons_completed


#: The exact key set of the crosscheck authorization. Closed, like the frozen
#: scientific schema's AUTHORIZATION_KEYS, so a missing or extra field refuses.
CROSSCHECK_AUTHORIZATION_KEYS = frozenset({
    'schema', 'action', 'account', 'kernel_id', 'bundle_sha256',
    'accepted_identity_sha256', 'instance_id', 'generation_manifest_sha256',
    'prepared_record_sha256', 'session_contract_sha256', 'expiry', 'nonce',
    'authorization_status', 'statement', 'write_scope',
})
CROSSCHECK_AUTHORIZATION_SCHEMA = 'decisions_os/g9_wp8c_one_use_scientific_write_authorization/v1'
CROSSCHECK_AUTHORIZATION_STATUS = 'owner_authorized'
CROSSCHECK_AUTHORIZATION_WRITE_SCOPE = 'crosscheck_only_no_scientific_write'


def validate_crosscheck_authorization(authorization, *, plan, verified, accepted, session_contract_sha256, today):
    """Validate the ONE crosscheck authorization against re-derived values only.

    WHY THIS IS NOT ``primitive.validate_authorization``: that reviewed function
    is deliberately bound to the SCIENTIFIC action -- it requires
    ``authorization['action'] == 'run_wp8c_production_scientific_session'`` and
    its statement names "one WP8c production scientific session". This kernel
    performs no such session, and the owner's decision authorizes a different
    action, ``run_wp7b_real_crosscheck``. Reusing the scientific validator would
    either force a false statement into the bytes or be edited to fit, and the
    second is exactly the fail-open this repository exists to prevent. So the
    crosscheck authorization has its own closed-schema validator, and it checks
    the SAME values the scientific one does: the instance, prepared record,
    generation manifest and accepted identity are all compared against values
    this run re-derived from the pinned bytes, and the session-contract hash
    binds the exact reviewed session module.

    The nonce is required to be a non-empty string but is NEVER CONSUMED:
    ``primitive.consume_authorization`` writes to the WP8b one-use registry,
    which registers a session that does not exist here.
    """
    import datetime

    if type(authorization) is not dict:
        raise CrosscheckRefused('The crosscheck authorization must be a mapping',
                                stage='authorization')
    present = set(authorization)
    missing = sorted(CROSSCHECK_AUTHORIZATION_KEYS - present)
    unexpected = sorted(present - CROSSCHECK_AUTHORIZATION_KEYS)
    if missing or unexpected:
        raise CrosscheckRefused(
            'Crosscheck authorization fields differ from the exact schema: '
            f'missing {missing}, unexpected {unexpected}', stage='authorization')
    if authorization['schema'] != CROSSCHECK_AUTHORIZATION_SCHEMA:
        raise CrosscheckRefused(
            f"Crosscheck authorization schema is {authorization['schema']!r}",
            stage='authorization')
    if authorization['action'] != plan['authorization_action']:
        raise CrosscheckRefused(
            f"Crosscheck authorization action is {authorization['action']!r}, not "
            f"{plan['authorization_action']!r}", stage='authorization')
    if authorization['authorization_status'] != CROSSCHECK_AUTHORIZATION_STATUS:
        raise CrosscheckRefused('Crosscheck authorization is not owner_authorized',
                                stage='authorization')
    if authorization['write_scope'] != CROSSCHECK_AUTHORIZATION_WRITE_SCOPE:
        raise CrosscheckRefused(
            'Crosscheck authorization claims a write scope other than '
            'crosscheck-only', stage='authorization')
    if authorization['kernel_id'] != plan['kernel_id']:
        raise CrosscheckRefused('Crosscheck authorization names another kernel',
                                stage='authorization')
    if authorization['bundle_sha256'] != plan['bundle_sha256']:
        raise CrosscheckRefused('Crosscheck authorization names another bundle',
                                stage='authorization')
    if authorization['instance_id'] != verified['instance_id']:
        raise CrosscheckRefused(
            'Crosscheck authorization names another instance than the verified layout',
            stage='authorization')
    if authorization['prepared_record_sha256'] != verified['prepared_id']:
        raise CrosscheckRefused(
            'Crosscheck authorization names another prepared record', stage='authorization')
    if authorization['generation_manifest_sha256'] != verified['generation_manifest_sha256']:
        raise CrosscheckRefused(
            'Crosscheck authorization names another generation manifest',
            stage='authorization')
    if authorization['accepted_identity_sha256'] != accepted['accepted_content_sha256']:
        raise CrosscheckRefused(
            'Crosscheck authorization names another accepted identity', stage='authorization')
    if authorization['session_contract_sha256'] != session_contract_sha256:
        raise CrosscheckRefused(
            'Crosscheck authorization was issued against different session-contract '
            'bytes; any rebuild voids the one-use authorization', stage='authorization')
    for field in ('account', 'nonce', 'statement'):
        if type(authorization[field]) is not str or not authorization[field]:
            raise CrosscheckRefused(
                f'Crosscheck authorization {field} is absent or empty',
                stage='authorization')
    expiry = authorization['expiry']
    try:
        parsed = datetime.date.fromisoformat(expiry)
    except (TypeError, ValueError) as exc:
        raise CrosscheckRefused(
            f'The crosscheck authorization expiry is not a calendar date: {expiry!r}',
            stage='authorization') from exc
    if parsed.isoformat() != expiry:
        raise CrosscheckRefused(
            f'The crosscheck authorization expiry is not canonical ISO: {expiry!r}',
            stage='authorization')
    if today.isoformat() > expiry:
        raise CrosscheckRefused(
            f'The crosscheck authorization expired on {expiry}; it is {today}',
            stage='authorization')
    return dict(authorization)


def _row_label(row):
    return '%s%s %s r=%r %s' % (
        row['family'],
        '/' + row['condition'] if 'condition' in row else '',
        row['coordinate'],
        row['r'],
        row['grid'],
    )


def _mirrored_positive_zero(device):
    """Read the backend's +0.0 declaration STATICALLY. Runs no backend code.

    ``inspect.getattr_static`` consults only ``__dict__`` mappings and MRO tuples.
    An absent name reports ``None`` rather than raising, so this cannot execute a
    descriptor or a ``__getattr__`` on the backend. The result is echoed into the
    receipt so a reviewer can confirm the proxy declared exactly what the real
    backend declares.
    """
    return inspect.getattr_static(type(device), POSITIVE_ZERO_DECLARATION, None)


def _timed_backend(device, timings, order):
    """Return a proxy that times each row's first call and forwards everything else.

    ``type(proxy).__dict__[POSITIVE_ZERO_DECLARATION]`` is set to the real
    backend's statically-read value, so the reviewed harness's
    ``_backend_declares_positive_zero`` reads the same answer it would have read
    from the real backend type. No other attribute is added, and the proxy
    declares nothing on the INSTANCE, which is what the harness requires.
    """
    declared = _mirrored_positive_zero(device)

    class _TimedDevice:
        def __init__(self, inner):
            self._inner = inner

        def __call__(self, row, pair, encoding):
            label = _row_label(row)
            first = label not in timings
            start = time.monotonic()
            try:
                return self._inner(row, pair, encoding)
            finally:
                if first:
                    timings[label] = time.monotonic() - start
                    order.append(label)

    if declared is not None:
        setattr(_TimedDevice, POSITIVE_ZERO_DECLARATION, declared)
    return _TimedDevice(device), declared


def run_crosscheck(*, root, plan, expected_plan_sha256, modules, observed_platform,
                   receipt_path, difference_path):
    """Run everything up to and including the B.2/WP3 crosscheck, then STOP."""
    root = Path(root).resolve()
    if hashlib.sha256(canonical(plan)).hexdigest() != sha_pin(expected_plan_sha256):
        raise CrosscheckRefused('Crosscheck plan differs from reviewed pin',
                                stage='plan_pin')
    if plan['scope'] != CROSSCHECK_SCOPE:
        raise CrosscheckRefused(
            'This parent implements the crosscheck-only scope only', stage='scope')

    required = {'acceptance', 'session', 'producer', 'reference', 'backend_binding',
                'provider', 'reference_adapter'}
    if set(modules) != required or set(plan['module_sha256']) != required:
        raise CrosscheckRefused('Exact seven independently reviewed modules required',
                                stage='module_census')
    for name in required:
        checked_file(Path(modules[name].__file__), plan['module_sha256'][name])

    acceptance = modules['acceptance']
    streaming = modules['session']
    primitive = streaming.wp8c_v2
    producer = modules['producer']
    provider = modules['provider']

    # --- identity, instance, prepared: identical to the v2 parent ---
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

    # --- the one crosscheck authorization, validated against re-derived values ---
    import datetime
    authorization = json.loads(checked_file(
        root / plan['authorization_path'], plan['authorization_file_sha256']))
    validate_crosscheck_authorization(
        authorization, plan=plan, verified=verified, accepted=accepted,
        session_contract_sha256=plan['module_sha256']['session'],
        today=datetime.date.today())

    # --- qualified artifacts ---
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

    # --- the real reference seal, on the real instance ---
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

    # --- the real device backend ---
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

    seams = streaming._v3_seams(acceptance)
    seams['bind_accepted_identity_v4'] = acceptance.accept_production_identity
    seams['device_backend_factory'] = factory
    seams['python_reference'] = reference
    boundary = SimpleNamespace(
        kind='actual_qualified_T4_runtime_crosscheck_no_owner_authority_substitution')
    device = factory(boundary)

    coordinates = primitive.validation_coordinates()

    # --- the actual B.2/WP3 crosscheck, by the REVIEWED seam, once ---
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
        # The reviewed harness refuses on the first difference and returns no
        # record. Convert that refusal into a fail-closed difference record.
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


def write_difference_record(path, *, plan, refusal, observed_platform, plan_sha256):
    """The fail-closed difference record. NO receipt accompanies this file."""
    body = dict(
        schema='decisions_os/g9_b2_wp3_crosscheck_difference/v1',
        status='REFUSED_CROSSCHECK_DIFFERENCE_OR_REFUSAL',
        scope=CROSSCHECK_SCOPE,
        slot=plan['slot'],
        kernel_id=plan['kernel_id'],
        instance_id=plan['instance_id'],
        prepared_record_sha256=plan['prepared_record_content_sha256'],
        plan_sha256=plan_sha256,
        stage=refusal.stage,
        detail=str(refusal),
        differences=refusal.differences,
        comparisons_completed=refusal.comparisons_completed,
        gpu=dict(observed_platform),
        receipt_written=False,
        scientific_writes=[],
    )
    body['content_sha256'] = hashlib.sha256(canonical(body)).hexdigest()
    Path(path).write_text(json.dumps(body, indent=2) + '\n')
    return body
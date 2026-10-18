"""
g9_wp8c_production_session_v3.py

Additive streaming production-session V3 with lossless range compression.
- No budget guard (scientific execution runs to completion).
- Streaming range generation: holds one sealed range in memory.
- Stores full committed records as gzip JSONL before writer projection; hashes still cover canonical uncompressed values.
- Consumes independent WP8a V4 acceptance.
- Separate family output root.
- Unchanged frozen primitives for WP2/WP3/instance verification.
"""
from __future__ import annotations

import datetime
import gzip
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

# Inherits unmodified frozen primitives from V2
from research.g9.wp8c_production import wp8c_production_session_v2 as wp8c_v2
from research.g9 import stage2_coordinate_records as records
from research.g9 import stage2_production_writer as writer
import uuid

def session_contract_sha256_v3() -> str:
    """The V3 contract's own content hash."""
    return hashlib.sha256(Path(__file__).resolve().read_bytes()).hexdigest()

def _v3_seams(parent_v4_acceptance_module):
    seams = wp8c_v2._seams()
    seams['bind_accepted_identity_v4'] = parent_v4_acceptance_module.accept_production_identity
    def exact(binding, session):
        return parent_v4_acceptance_module.exact_match_session(
            session, binding['acceptance_record'],
            reviewed_record_sha256=binding['reviewed_record_sha256'], repo_root=binding['repo_root'])
    seams['require_session_identity_exact'] = exact
    return seams


def _canonical(obj):
    return json.dumps(obj,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()


def _persist_full(root, batch_id, full_records):
    directory = root / 'full_records'
    directory.mkdir(exist_ok=True)
    if directory.is_symlink():raise ValueError('Full record directory must be real')
    target = directory / (batch_id + '.jsonl.gz')
    raw = b''.join(_canonical(rec)+b'\n' for rec in full_records)
    stored = gzip.compress(raw,compresslevel=1,mtime=0)
    if target.exists():
        if target.is_symlink() or gzip.decompress(target.read_bytes()) != raw:
            raise ValueError('Full record replay differs from retained range; refusing overwrite')
    else:
        staged = directory / ('.staging-' + uuid.uuid4().hex)
        with staged.open('xb') as f:
            f.write(stored);f.flush();os.fsync(f.fileno())
        # Link provides atomic no-clobber creation; keep staging evidence for later cleanup.
        os.link(staged,target)
        fd=os.open(directory,os.O_RDONLY)
        try:os.fsync(fd)
        finally:os.close(fd)
    return hashlib.sha256(raw).hexdigest()


def _verify_full_records(root,row,space,context,binding,session_identity):
    target = root / 'full_records' / (row['batch_id']+'.jsonl.gz')
    if target.is_symlink() or not target.is_file():raise ValueError('Retained full range missing')
    raw=gzip.decompress(target.read_bytes());full=[json.loads(line) for line in raw.splitlines()]
    if len(full)!=row['stop']-row['start']:raise ValueError('Retained range coverage changed')
    for linear,record in zip(range(row['start'],row['stop']),full,strict=True):
        body=dict(record);pin=body.pop('content_sha256')
        coordinate=space.coordinate(linear)
        if (hashlib.sha256(_canonical(body)).hexdigest()!=pin or record['linear_index']!=linear
                or record['family']!=space.family.key
                or record['coordinate']!={axis:index for axis,index in zip(space.family.axes,coordinate,strict=True)}):
            raise ValueError('Retained full record commitment/coordinate changed')
    writer.verify_range(root,row['batch_id'],result_schema={'identity_sha256':'str','record_content_sha256':'str'})
    projection=json.loads((root/writer.RANGES_DIRNAME/row['batch_id']/writer.RECORDS_NAME).read_bytes())
    expected=[wp8c_v2.project_record_for_writer(rec,binding['accepted_content_sha256']) for rec in full]
    if projection!=expected:raise ValueError('Full retained values no longer match promoted commitments')
    return hashlib.sha256(raw).hexdigest()


def stream_and_write_sealed_ranges(*,family_output_root,plan,cuda_producer_func,cuda_context,
                                   space,binding,session_identity,result_schema,steps):
    root=Path(family_output_root)
    if type(result_schema) is not dict or result_schema!={'identity_sha256':'str','record_content_sha256':'str'}:
        raise ValueError('Exact writer commitment schema required')
    promoted=writer.promoted_batch_ids(root)
    if not promoted<={row['batch_id'] for row in plan['ranges']}:
        raise ValueError('Unexpected promoted range outside sealed plan')
    bound=records.bind_identity(wp8c_v2.accepted_identity_of(binding))
    digests=[]
    for row in plan['ranges']:
        if row['batch_id'] in promoted:
            digests.append(_verify_full_records(root,row,space,cuda_context,binding,session_identity))
            continue
        full=[];expected=row['start']
        for linear,item in cuda_producer_func(space,cuda_context,start=row['start'],stop=row['stop']):
            if type(linear) is not int or linear!=expected:raise ValueError('Exact ordered range coverage required')
            full.append(records.build_record(space,linear,cuda_context.frozen,item['core_result'],item['slack'],
                item['classifiers'],item['f_star'],item['lambda_ref'],bound=bound,session_identity=session_identity))
            expected+=1
        if expected!=row['stop']:raise ValueError('Incomplete whole range refuses promotion')
        digest=_persist_full(root,row['batch_id'],full);digests.append(digest)
        if 'records_built' not in steps.passed:steps.record('records_built',digest=digest)
        projected=[wp8c_v2.project_record_for_writer(rec,binding['accepted_content_sha256']) for rec in full]
        writer.write_range(root,row['batch_id'],projected,result_schema=result_schema,
                           identity=wp8c_v2.writer_identity_of(binding),session=session_identity)
        promoted.add(row['batch_id'])
    commitment=hashlib.sha256(_canonical(digests)).hexdigest()
    if 'records_built' not in steps.passed:steps.record('records_built',digest=commitment)
    steps.record('ranges_promoted',digest=commitment)
    return sorted(promoted),commitment


def run_production_session_v3(
    *,
    slot: object,
    session_id: str,
    root: Path | str,
    family_output_root: Path | str,
    nonce_root: Path | str,
    acceptance_record: object,
    reviewed_record_sha256: str,
    session_identity: object,
    authorization: object,
    boundary: Any,
    standin: bool,
    writer_family: str,
    result_schema: Mapping[str, str],
    family_space: object,
    family_coordinates: int,
    expected_bundle_sha256: str,
    expected_kernel_id: str,
    expected_approval_sha256: str,
    expected_generator_implementation_record_sha256: str,
    expected_ground_truth_provenance_sha256: str,
    protocol_identity_sha256: str,
    parent_v4_acceptance_module: Any,
    cuda_producer_func: Callable,
    cuda_context: Any,
    seams: Mapping[str, Any] | None = None,
    today: datetime.date | None = None,
    release_authority=None
) -> dict[str, Any]:
    """
    V3 Additive Streaming Production Session.
    Bypasses BudgetGuard.
    """
    steps = wp8c_v2._Steps()
    reviewed = seams if seams is not None else _v3_seams(parent_v4_acceptance_module)
    contract_sha256 = session_contract_sha256_v3()
    
    session: dict[str, Any] = {}
    try:
        # 1. Instance Verify (Unchanged S1 primitive)
        verified = wp8c_v2.verify_instance_for_session(slot, root=root, standin=standin, release_authority=release_authority)
        wp8c_v2.require_instance_matches_session(verified, expected_instance_id=verified['instance_id'], expected_slot=verified['slot_name'])
        steps.record('instance_verified', digest=wp8c_v2._require_sha256(verified['index_content_sha256'], 'the instance index content hash'))
        if cuda_context.instance_id!=verified['instance_id'] or cuda_context.prepared_record_sha256!=verified['prepared_id']:
            raise ValueError('CUDA context belongs to another verified real instance/prepared record')
        
        # 2. Identity Bind (Consumes parent's V4 actual passed/pinned module)
        accepted = reviewed['bind_accepted_identity_v4'](acceptance_record, reviewed_record_sha256=reviewed_record_sha256, repo_root=str(root))
        binding = wp8c_v2._as_binding(accepted, acceptance_record=acceptance_record, reviewed_record_sha256=reviewed_record_sha256, repo_root=root)
        
        state_root = Path(family_output_root) / "session_state"
        started_state = wp8c_v2._read_state(state_root, slot)
        wp8c_v2._require_session_allowed(started_state, slot, session_id)
        
        identity_verdict = reviewed['require_session_identity_exact'](binding, session_identity)
        steps.record('identity_bound', digest=wp8c_v2._require_sha256(identity_verdict['session_content_sha256'], 'the session identity content hash'))
        
        # 3. Authorization Consume (Per-family independent reviewed logic)
        checked = wp8c_v2.validate_authorization(authorization, verified=verified, accepted_binding=binding, session_contract_sha256=contract_sha256, today=today)
        if checked['bundle_sha256'] != expected_bundle_sha256 or checked['kernel_id'] != expected_kernel_id or checked['account'] != 'shivanshsrivastava06':
            raise ValueError('Authorization belongs to another source bundle/kernel/account')
        wp8c_v2.consume_authorization(checked, nonce_root=nonce_root, today=today)
        steps.record('authorization_consumed', digest=wp8c_v2._require_sha256(wp8c_v2._sha256_bytes(wp8c_v2._canonical(checked)), 'the consumed authorization digest'))
        
        # 4. WP2 Recheck
        session_view = wp8c_v2.wp2_element_view(session_identity)
        accepted_view = wp8c_v2.wp2_element_view(binding['draft_identity'])
        observed = wp8c_v2.observed_approval_hashes()
        
        wp2_record, wp2_passed = reviewed['wp2_recheck'](
            accepted_identity=accepted_view, 
            validate_identity=wp8c_v2.wp2_validate_view, 
            exact_match=wp8c_v2.wp2_match_views, 
            observed_approval_sha256=observed, 
            expected_approval_sha256=expected_approval_sha256, 
            session_identity=session_view, 
            generator_implementation_record_sha256=wp8c_v2.generator_record_of(verified), 
            expected_generator_implementation_record_sha256=expected_generator_implementation_record_sha256, 
            ground_truth_provenance_sha256=wp8c_v2.ground_truth_of(verified), 
            expected_ground_truth_provenance_sha256=expected_ground_truth_provenance_sha256
        )
        wp8c_v2._require_step(wp2_passed is True, 'the WP2 section B item 1 recheck refused this session')
        steps.record('wp2_recheck_passed', digest=wp8c_v2._require_sha256(wp2_record.get('validation_digest', wp8c_v2._sha256_bytes(wp8c_v2._canonical(wp2_record))), 'the WP2 recheck digest'))
        
        # 5. WP3 Check
        wp8c_v2._require_step(steps.failed_prerequisite_for('wp3_check_passed') is None, 'wp3_check_passed blocked')
        wp3_record = reviewed['wp3_run'](
            wp8c_v2.boundary_device_backend(boundary, reviewed), 
            wp8c_v2.wp3_reference(reviewed), 
            wp8c_v2.validation_coordinates(), 
            accepted_identity=binding['draft_identity'], 
            session_identity=session_identity, 
            validate_identity=reviewed['identity_validate'], 
            exact_match=reviewed['identity_exact_match'], 
            accepted_identity_sha256=binding['accepted_content_sha256'], 
            protocol_identity_sha256=protocol_identity_sha256, 
            d013_fired=False, # Refuses D013 natively; conditional D013 engine reserved for later module
            d013_coordinates=None
        )
        reviewed['wp3_validate'](wp3_record)
        steps.record('wp3_check_passed', digest=wp3_record['content_sha256'])
        
        # 6. Stream and Write Ranges
        wp8c_v2._require_step(steps.failed_prerequisite_for('records_built') is None, 'records_built blocked')
        wp8c_v2._require(isinstance(writer_family, str) and writer_family, 'writer_family is required')
        
        if family_space.family not in records.families(False) or family_space != records.family_space(family_space.family,cuda_context.frozen):
            raise ValueError('Exact declared baseline family/per-instance space required')
        if family_coordinates!=family_space.total_coordinates or writer_family!=family_space.family.key:
            raise ValueError('Plan must match actual family identity/count')
        expected_output = wp8c_v2.wp8dp._slot_dir(slot,root) / 'sweep' / family_space.family.key
        if Path(family_output_root).resolve()!=expected_output.resolve():
            raise ValueError('Scientific output must use the verified instance/family namespace')
        Path(family_output_root).mkdir(parents=True,exist_ok=True)
        # Create plan in distinct family output root (<instance>/sweep/<family.key>)
        plan = reviewed['seal_range_plan'](
            family_output_root, 
            family=writer_family, 
            total_coordinates=family_coordinates, 
            identity=wp8c_v2.writer_identity_of(binding), 
            session=session_identity
        )
        
        promoted,full_commitment=stream_and_write_sealed_ranges(
            family_output_root=family_output_root,plan=plan,cuda_producer_func=cuda_producer_func,
            cuda_context=cuda_context,space=family_space,binding=binding,
            session_identity=session_identity,result_schema=result_schema,steps=steps)

        # 7. Final Audit on unique family_output_root
        cover = wp8c_v2._observed_cover(reviewed, family_output_root)
        if not cover['ok']:
            session = wp8c_v2._seal({
                'schema': 'decisions_os/g9_streaming_production_session/v3', 'status': 'refused', 'accepted': False, 
                'acceptance_reason': 'partial cover is never an acceptance',
                'scope_statement': wp8c_v2.SCOPE_STATEMENT, 'authority_boundary': boundary.kind, 
                'session_id': session_id, 'slot': verified['slot_name'], 'instance_id': verified['instance_id'], 
                'difference': cover['difference'], 
                'refusal_type': 'IncompleteRangeCover', 'missing_range_batch_ids': cover['missing'], 
                'promoted_range_batch_ids': sorted(promoted), 'sealed_range_plan_content_sha256': plan.get('content_sha256'), 
                'scientific_outputs': []
            })
        else:
            session = wp8c_v2._seal({
                'schema': 'decisions_os/g9_streaming_production_session/v3', 'status': 'complete_pending_image_audit', 'accepted': False, 
                'acceptance_reason': 'acceptance is a separate post-run',
                'scope_statement': wp8c_v2.SCOPE_STATEMENT, 'authority_boundary': boundary.kind, 
                'session_id': session_id, 'slot': verified['slot_name'], 'instance_id': verified['instance_id'], 
                'layout_kind': verified['layout_kind'], 'prepared_record_status': verified['prepared_record_status'], 
                'prepared_record_production': verified['prepared_record_production'], 
                'identity': identity_verdict, 'session_contract_sha256': contract_sha256, 
                'authorization_action': checked['action'], 'wp2_recheck_digest': steps.digests['wp2_recheck_passed'], 
                'wp3_record_content_sha256': wp3_record['content_sha256'], 
                'sealed_range_plan_content_sha256': plan.get('content_sha256'), 
                'promoted_range_batch_ids': sorted(promoted), 'final_set': cover['audit'], 'full_records_commitment_sha256': full_commitment, 
                'image_audit_status': wp8c_v2.KAGGLE_IMAGE_STATUS_PENDING, 
                'post_run_only_image_fields': list(wp8c_v2.POST_RUN_ONLY_IMAGE_FIELDS), 
                'scientific_outputs': []
            })
            
    except Exception as exc:
        steps.refuse('refused', str(exc))
        session = wp8c_v2._seal({
            'schema': 'decisions_os/g9_streaming_production_session/v3', 'status': 'refused', 'accepted': False, 
            'acceptance_reason': 'a refused session is never accepted', 
            'scope_statement': wp8c_v2.SCOPE_STATEMENT, 'authority_boundary': boundary.kind, 
            'session_id': session_id, 'difference': str(exc), 'refusal_type': type(exc).__name__, 
            'completed_steps': sorted(steps.passed), 'blocked_steps': [step for step in wp8c_v2.STEP_ORDER if step not in steps.passed], 
            'scientific_outputs': []
        })
        
    if session.get('status') == 'complete_pending_image_audit':
        wp8c_v2._write_state(state_root, slot, wp8c_v2._seal({
            'schema': wp8c_v2.SESSION_STATE_SCHEMA, 'status': 'complete', 'session_id': session_id, 
            'slot': verified['slot_name'], 'instance_id': verified['instance_id'], 
            'identity_sha256': binding['accepted_content_sha256'], 'session_contract_sha256': contract_sha256, 
            'promoted_range_batch_ids': sorted(promoted) if 'promoted' in locals() else []
        }))
        
    session['steps_passed'] = sorted(steps.passed)
    session['gate_status'] = wp8c_v2.owner_gate_status()
    return session

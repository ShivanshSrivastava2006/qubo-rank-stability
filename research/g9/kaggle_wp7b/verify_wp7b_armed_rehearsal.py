"""Offline Kaggle-kernel process-isolation rehearsal of generated armed bundles.

Both source exec and script execution start under a socket-importing parent
with fake Kaggle environment names and sitecustomize. Only the CUDA boundary
and platform observations are emulated; the complete armed chain, payload,
approval, session and receipt checks run unchanged. Negative paths cover
probe mismatch, staged tampering, child environment, timeout and site paths.
"""
from __future__ import annotations
import ast, contextlib, datetime, hashlib, io, json, os, pathlib, runpy, shutil, subprocess, sys
from types import SimpleNamespace

ROOT=pathlib.Path(__file__).resolve().parents[3]
SCRATCH=pathlib.Path('/home/shivansh-srivastava/decisions_os/g9_jobs/scratch/wp7biso/rehearsal')
USER='shivanshsrivastava06'

def sha(data): return hashlib.sha256(data).hexdigest()
def check(value,message):
    if not value: raise RuntimeError(message)

def normalize_approval_regions(source):
    allowed={'APPROVAL_FIELDS','APPROVAL_SHA','ARCHIVE_CHUNKS','ARCHIVE_SHA',
             'EXPECTED_INDEX','SELF_SHA','STAGE_INDEX_SHA'}
    tree=ast.parse(source)
    offsets=[0]
    for line in source.splitlines(keepends=True): offsets.append(offsets[-1]+len(line))
    edits=[]
    for node in tree.body:
        if not isinstance(node,ast.Assign): continue
        names={target.id for target in node.targets if isinstance(target,ast.Name)}
        if not names & allowed: continue
        start=offsets[node.value.lineno-1]+node.value.col_offset
        end=offsets[node.value.end_lineno-1]+node.value.end_col_offset
        edits.append((start,end,'<APPROVAL_REGION>'))
    for start,end,value in reversed(edits): source=source[:start]+value+source[end:]
    return source

def install_nvcc_host_boundary():
    fakebin=SCRATCH/'fakebin'; fakebin.mkdir(parents=True,exist_ok=True)
    nvcc=fakebin/'nvcc'
    rows=[
      '#!/bin/sh',
      'if [ "$1" = "--version" ]; then printf "%s\\n" "Cuda compilation tools, release 12.8, V12.8.61"; exit 0; fi',
      'shared=0; source_file=; output_file=; include_args=',
      'while [ "$#" -gt 0 ]; do case "$1" in',
      '  -shared) shared=1; shift ;;',
      '  -o) output_file=$2; shift 2 ;;',
      '  -I) include_args="$include_args -I $2"; shift 2 ;;',
      '  -Xcompiler) shift 2 ;;',
      '  *.cu) source_file=$1; shift ;;',
      '  *) shift ;;',
      'esac; done',
      '[ -n "$source_file" ] && [ -n "$output_file" ] || exit 2',
      'compiler="g++ -std=c++17 -O0 -ffp-contract=off -fno-fast-math -fPIC -x c++ -I /home/shivansh-srivastava/decisions_os/g9_jobs/copies/wp7bint.Xu2e/project/research/g6/cuda_qualification/host_emulation_stub $include_args"',
      'if [ "$shared" = 1 ]; then compiler="$compiler -shared"; fi',
      'eval "$compiler \\\"$source_file\\\" -o \\\"$output_file\\\""',
    ]
    nvcc.write_text('\n'.join(rows)+'\n',encoding='ascii'); nvcc.chmod(0o755)
    return fakebin

def main():
    import sys as _sys
    if str(ROOT) not in _sys.path: _sys.path.insert(0,str(ROOT))
    from research.g9.kaggle_wp7b import build_wp7b_bundle as builder
    from research.g9.kaggle_wp7b import wp7b_launcher as adapter
    from research.g9.kaggle_wp7b import wp7b_identity_binding as binding
    for name in ('draft','armed','approval','output','armed-positive','positive-output','positive-approval'):
        path=SCRATCH/name
        if path.is_dir(): shutil.rmtree(path)
        elif path.exists(): path.unlink()
    fakebin=install_nvcc_host_boundary()
    paths={
        'instance':ROOT/'research/g9/kaggle_wp7b/seal/wp7b_instance.json',
        'prepared':ROOT/'research/g9/kaggle_wp7b/seal/wp7b_prepared_record.json',
        'seal':ROOT/'research/g9/kaggle_wp7b/seal/wp7b_reference_seal.json',
        'inputs':ROOT/'research/g9/kaggle_wp7b/seal/wp7b_seal_inputs.json',
        'config':ROOT/'research/g9/kaggle_wp7b/runtime_config.json',
    }
    hashes={k:sha(v.read_bytes()) for k,v in paths.items()}
    common=['--kaggle-user',USER,'--instance',str(paths['instance']),'--instance-sha256',hashes['instance'],
      '--prepared-record',str(paths['prepared']),'--prepared-record-sha256',hashes['prepared'],
      '--seal',str(paths['seal']),'--seal-sha256',hashes['seal'],
      '--seal-inputs',str(paths['inputs']),'--seal-inputs-sha256',hashes['inputs'],
      '--runtime-config',str(paths['config']),'--runtime-config-sha256',hashes['config']]
    draft_args=['--output-dir',str(SCRATCH/'draft'),*common,'--draft']
    with contextlib.redirect_stdout(io.StringIO()):
        check(builder.main(draft_args)==0,'draft bundle build failed')
    manifest=json.loads((SCRATCH/'draft/wp7b_bundle_manifest.json').read_bytes())
    record={'bundle_sha256':manifest['bundle_sha256'],
      'reviewed_table_anchor':manifest['reviewed_table_anchor'],'seal_sha256':manifest['seal_sha256'],
      'kernel_id':manifest['kernel_id'],'account':USER,'action':'push_and_run_wp7_dry_run',
      'expiry':(datetime.date.today()+datetime.timedelta(days=1)).isoformat(),
      'nonce':'fixture-negative-driver-mismatch'}
    raw=json.dumps(record,sort_keys=True,indent=2).encode('ascii')+b'\n'
    approval=SCRATCH/'approval'; approval.write_bytes(raw)
    armed_args=['--output-dir',str(SCRATCH/'armed'),*common,
      '--owner-approval-record',str(approval),'--owner-approval-record-sha256',sha(raw)]
    with contextlib.redirect_stdout(io.StringIO()):
        check(builder.main(armed_args)==0,'test-approved armed bundle build failed')
    bundle=json.loads((SCRATCH/'armed/wp7b_bundle_manifest.json').read_bytes())
    check(bundle['bundle_sha256']==manifest['bundle_sha256'],'armed payload differs from draft payload')
    script=SCRATCH/'armed'/('g9_wp7_nonscientific_dry_run_'+bundle['bundle_sha256'][:8]+'.py')
    check('FIXTURE_MODE=False' in script.read_text(encoding='utf-8'),
          'ordinary armed bundle unexpectedly enables fixture-only limits')
    alternate_record=dict(record,nonce='fixture-negative-driver-mismatch-alternate')
    alternate_raw=json.dumps(alternate_record,sort_keys=True,indent=2).encode('ascii')+b'\n'
    alternate_approval=SCRATCH/'alternate-approval'; alternate_approval.write_bytes(alternate_raw)
    alternate_args=['--output-dir',str(SCRATCH/'armed-alternate'),*common,
      '--owner-approval-record',str(alternate_approval),'--owner-approval-record-sha256',sha(alternate_raw)]
    with contextlib.redirect_stdout(io.StringIO()):
        check(builder.main(alternate_args)==0,'second ordinary armed bundle build failed')
    alternate_manifest=json.loads((SCRATCH/'armed-alternate/wp7b_bundle_manifest.json').read_bytes())
    alternate_script=SCRATCH/'armed-alternate'/('g9_wp7_nonscientific_dry_run_'+bundle['bundle_sha256'][:8]+'.py')
    check(alternate_manifest['bundle_sha256']==bundle['bundle_sha256'],
          'approval nonce changed the reviewed payload bundle hash')
    check(normalize_approval_regions(script.read_text(encoding='utf-8')) ==
          normalize_approval_regions(alternate_script.read_text(encoding='utf-8')),
          'armed test-record diff escaped approval-specific script regions')

    positive_record=dict(record,nonce='fixture-positive-host-emulation')
    positive_raw=json.dumps(positive_record,sort_keys=True,indent=2).encode('ascii')+b'\n'
    positive_approval=SCRATCH/'positive-approval'; positive_approval.write_bytes(positive_raw)
    positive_args=['--output-dir',str(SCRATCH/'armed-positive'),*common,
      '--owner-approval-record',str(positive_approval),'--owner-approval-record-sha256',sha(positive_raw),
      '--fixture-mode']
    with contextlib.redirect_stdout(io.StringIO()):
        check(builder.main(positive_args)==0,'fixture-mode armed bundle build failed')
    positive_script=SCRATCH/'armed-positive'/('g9_wp7_nonscientific_dry_run_'+bundle['bundle_sha256'][:8]+'.py')
    check('FIXTURE_MODE=True' in positive_script.read_text(encoding='utf-8'),
          'fixture-mode armed bundle did not declare its test-only mode')

    pin=binding.load_pin(str(ROOT/binding.PIN_PATH))
    image_observed={k:v for k,v in pin['image_reported'].items()
                    if k not in adapter.POST_RUN_ONLY_IMAGE_FIELDS}
    platform_observed=pin['platform_reported']
    fake_sites=SCRATCH/'parent-site-packages'
    fake_sites.mkdir(parents=True,exist_ok=True)
    hook_marker=SCRATCH/'parent-sitecustomize.loaded'
    (fake_sites/'sitecustomize.py').write_text(
      'import socket, os, pathlib\npathlib.Path('+repr(str(hook_marker))+').write_text(str(os.getpid()))\n',encoding='ascii')
    probe_json=json.dumps({'platform_reported':platform_observed,'image_reported':image_observed},
                          sort_keys=True,separators=(',',':'))
    env_before=dict(os.environ)
    positive_env={
      'PATH':str(fakebin)+os.pathsep+os.environ.get('PATH',''),
      'PYTHONDONTWRITEBYTECODE':'1', 'PYTHONPATH':str(fake_sites),
      'CUDA_HOME':image_observed['cuda_home'],
      **image_observed['build_env'],
      'KAGGLE_USER_SECRETS_TOKEN':'fixture-token-never-real',
      'KAGGLE_KERNEL_RUN_TYPE':'Interactive',
      'KAGGLE_DOCKER_IMAGE':'fixture-image',
      'WP7B_TEST_PROBES_JSON':probe_json,
    }
    bootstrap=SCRATCH/'exec_notebook_kernel.py'
    bootstrap.write_text(
      'import socket, pathlib\n'
      'source=pathlib.Path('+repr(str(positive_script))+').read_text(encoding="utf-8")\n'
      'exec(compile(source,'+repr(str(positive_script))+',"exec"),{"__name__":"__main__","__file__":'+repr(str(positive_script))+'})\n',
      encoding='ascii')
    def invoke(label, *, mode='exec', extra=None):
        output=SCRATCH/label
        if output.exists(): shutil.rmtree(output)
        env=os.environ.copy(); env.update(positive_env); env.update(extra or {})
        env['KAGGLE_WORKING_DIR']=str(output)
        if hook_marker.exists(): hook_marker.unlink()
        command=([sys.executable,'-B']+(['-O'] if sys.flags.optimize else [])+
                 ([str(bootstrap)] if mode=='exec' else [str(positive_script)]))
        process=subprocess.Popen(command,cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        stdout,stderr=process.communicate(timeout=1800)
        completed=SimpleNamespace(returncode=process.returncode,stdout=stdout,stderr=stderr,pid=process.pid)
        check(hook_marker.is_file() and hook_marker.read_text()==str(completed.pid),
              label+' parent sitecustomize ran in the parent or was re-run in the child')
        return completed,output
    def check_outer(label, output):
        receipt_path=output/'wp7b_receipt.json'
        check(receipt_path.is_file(),label+' did not write outer receipt')
        check(not (output/'wp7b_difference.json').exists(),label+' wrote difference record')
        outer=json.loads(receipt_path.read_bytes())
        check(outer.get('status')=='pending_image_metadata_audit',label+' missed pending metadata receipt')
        session=outer.get('session_receipt',{})
        check(session.get('package_status')=='draft_not_approved_for_push' and session.get('differences')==[],
              label+' WP7 session receipt did not validate cleanly')
        accepted=json.loads(paths['config'].read_bytes())['accepted_identity']
        check(session.get('identities',{}).get('production_identity_sha256')==accepted['content_sha256'],
              label+' WP1 identity hash differs from accepted identity')
        check(session.get('counters',{}).get('wp3_rows',0)==16 and
              session.get('counters',{}).get('wp3_d013_repeat_rows',0)==4,
              label+' omitted primary or D013 repeat rows')
        check(session.get('counters',{}).get('synthetic_ranges_written',0)>0,
              label+' did not write the identity-only synthetic range')
    # Notebook-style exec and ordinary script execution both start with socket and fake Kaggle variables.
    for label,mode in [('positive-exec','exec'),('positive-script','script')]:
        completed,output=invoke(label,mode=mode)
        if completed.returncode:
            raise RuntimeError(label+' refused: '+(output/'wp7b_difference.json').read_text()
                if (output/'wp7b_difference.json').exists() else completed.stderr[-2000:])
        check_outer(label,output)

    # A mismatch remains a typed, pre-write WP7 refusal in the isolated child.
    bad_platform=dict(platform_observed); bad_platform['cuda_driver_version']='12999'
    bad_probe=json.dumps({'platform_reported':bad_platform,'image_reported':image_observed},
                         sort_keys=True,separators=(',',':'))
    completed,output=invoke('negative-probe',extra={'WP7B_TEST_PROBES_JSON':bad_probe})
    difference=json.loads((output/'wp7b_difference.json').read_bytes())
    check(completed.returncode==2 and difference.get('status')=='refused' and
          difference.get('error_type')=='Wp7EnvironmentAbort' and
          'cuda_driver_version' in difference.get('difference',''),
          'mismatching child probe did not produce typed difference receipt')
    check(not (output/'wp7b_receipt.json').exists() and
          not list((output/'wp7b-output').glob('*')),
          'mismatching probe wrote a receipt or scientific output')

    # Child re-hash catches mutation after the outer verification pass.
    completed,output=invoke('negative-tamper',extra={'WP7B_TEST_TAMPER_STAGED':'research/g9/kaggle_wp7b/runtime_config.json'})
    difference=json.loads((output/'wp7b_difference.json').read_bytes())
    check(completed.returncode==2 and difference.get('error_type')=='ChildRefusal' and
          'staged file sha256 mismatch' in difference.get('difference',''),
          'child accepted a staged file modified after outer verification')
    check(not (output/'wp7b_receipt.json').exists(),'tampered child path wrote receipt')

    # Test-only env injection verifies the child rejects Kaggle credentials before imports.
    injected=json.dumps({'KAGGLE_USER_SECRETS_TOKEN':'fixture-child-token'},separators=(',',':'))
    completed,output=invoke('negative-child-kaggle-env',extra={'WP7B_TEST_CHILD_ENV_JSON':injected})
    difference=json.loads((output/'wp7b_difference.json').read_bytes())
    check(completed.returncode==2 and difference.get('error_type')=='ChildRefusal' and
          'KAGGLE_ environment variable is present' in difference.get('difference',''),
          'child accepted injected Kaggle environment')
    check(not (output/'wp7b_receipt.json').exists(),'credential refusal wrote receipt')

    # The outer's bounded wait kills this exact timed-out child and records a difference, never a receipt.
    started_marker=SCRATCH/'negative-killed-child'/'child-started.marker'
    completed,output=invoke('negative-killed-child',extra={
      'WP7B_TEST_CHILD_SLEEP':'30','WP7B_TEST_CHILD_TIMEOUT':'3',
      'WP7B_TEST_CHILD_STARTED_FILE':str(started_marker)})
    difference=json.loads((output/'wp7b_difference.json').read_bytes())
    check(completed.returncode==124 and difference.get('error_type')=='ChildTimeoutError' and
          'child_timeout' in difference.get('difference',''),
          'killed child did not produce typed timeout difference')
    check(started_marker.is_file(),'child timeout happened before fixture child entered its run path')
    check(not (output/'wp7b_receipt.json').exists(),'killed child was given a fabricated receipt')

    # A nonexistent system package path is refused with a typed difference.
    completed,output=invoke('negative-missing-site',extra={
      'WP7B_TEST_SITE_DIRS_JSON':'["/definitely/missing/wp7b-site-packages"]'})
    difference=json.loads((output/'wp7b_difference.json').read_bytes())
    check(completed.returncode==2 and difference.get('error_type')=='ChildRefusal' and
          'site-packages path is missing or invalid' in difference.get('difference',''),
          'missing site-packages path did not fail with typed refusal')
    check(not (output/'wp7b_receipt.json').exists(),'missing site path wrote receipt')

    # Exercise the same injected-clock budget guard used inside WP3.
    adapter.START=0
    try: adapter.guard(lambda:adapter.START+adapter.BUDGET_SECONDS+1,'armed-fixture-budget-step')
    except RuntimeError as exc:
        check('incomplete_budget:last_completed=armed-fixture-budget-step' in str(exc),
              'budget guard emitted the wrong typed refusal')
    else: raise RuntimeError('injected-clock budget guard did not fire')
    os.environ.clear(); os.environ.update(env_before)
    print('WP7b Kaggle-realistic process-isolation rehearsal: PASS (exec + script, re-hash, env, timeout, site-path refusals)')

if __name__=='__main__': main()

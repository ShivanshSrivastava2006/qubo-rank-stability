"""CPU-only checks of isolated child entry and generated supervisor branches."""
from __future__ import annotations
import contextlib, io, json, os, pathlib, subprocess, sys, tempfile, time, site
from types import SimpleNamespace
import wp7b_child_entry as child

SCRATCH="/home/shivansh-srivastava/decisions_os/g9_jobs/scratch/wp7biso"

def check(condition, message):
    if not condition:
        raise AssertionError(message)


def run():
    with tempfile.TemporaryDirectory(dir=SCRATCH,prefix="child-guards-") as tmp:
        root=pathlib.Path(tmp); leaf=root/'leaf'; leaf.write_bytes(b'fixture')
        index=root/'.index'
        digest=child.sha(leaf.read_bytes())
        cases=[({},'index is malformed'),([None],'row is malformed'),([['leaf']],'row is malformed'),
               ([[7,digest]],'entry is invalid'),([['leaf',7]],'entry is invalid'),
               ([['leaf','short']],'entry is invalid'),([['/absolute',digest]],'entry is invalid'),
               ([['../leaf',digest]],'entry is invalid'),
               ([['leaf',digest],['leaf',digest]],'entry is invalid')]
        for rows,message in cases:
            index.write_bytes(child.canonical(rows))
            try: child.verify_stage(root,index,child.sha(index.read_bytes()))
            except child.ChildRefusal as exc: check(message in str(exc),'wrong staging refusal: '+str(exc))
            else: raise AssertionError('invalid staged index accepted')
        index.write_bytes(child.canonical([['leaf',digest]]))
        for bad_root,bad_index in [(pathlib.Path('relative'),index),(root,pathlib.Path('relative'))]:
            try: child.verify_stage(bad_root,bad_index,child.sha(index.read_bytes()))
            except child.ChildRefusal as exc: check('must be absolute' in str(exc),'wrong relative path refusal')
            else: raise AssertionError('relative staging path accepted')
        linked=root/'linked-root'; linked.symlink_to(root,target_is_directory=True)
        try: child.verify_stage(linked,linked/'.index',child.sha(index.read_bytes()))
        except child.ChildRefusal as exc: check('linked or escaping' in str(exc),'wrong root link refusal')
        else: raise AssertionError('linked stage accepted')
        check(child.validate_site_dirs([str(root),str(root)])==[str(root)],'site paths not deduplicated')
        for sites in (None,{},[7]):
            try: child.validate_site_dirs(sites)
            except child.ChildRefusal: pass
            else: raise AssertionError('invalid site directory types accepted')
        for module in child.FORBIDDEN+child.FORBIDDEN_ROOTS:
            try: child.assert_clean_process(modules=[module],environment={})
            except child.ChildRefusal: pass
            else: raise AssertionError('forbidden module accepted: '+module)
        target=root/'nested'/'atomic.json'
        original_fsync=child.os.fsync; calls=[]
        def synced(fd):
            calls.append(fd)
            return original_fsync(fd)
        child.os.fsync=synced
        try:
            child.atomic_write(target,b'first')
            check(len(calls)==1,'atomic output was not synced')
        finally: child.os.fsync=original_fsync
        child.atomic_write(target,b'second')
        check(target.read_bytes()==b'second','atomic output was not replaced')
        original_replace=child.os.replace
        def failed_replace(*args): raise OSError('fixture replace failure')
        child.os.replace=failed_replace
        try:
            try: child.atomic_write(target,b'third')
            except OSError: pass
            else: raise AssertionError('atomic failure suppressed')
        finally: child.os.replace=original_replace
        check(list(target.parent.iterdir())==[target],'atomic failure leaked scratch file')
    with tempfile.TemporaryDirectory(dir=SCRATCH,prefix="child-fixture-") as tmp:
        base=pathlib.Path(tmp)
        root=base/"stage"; root.mkdir()
        adapter_source = """import os,time
START=time.monotonic()
POST_RUN_ONLY_IMAGE_FIELDS=('image',)
def environment_comparison_pin(pin): return pin
def build_probes(pin): return {'platform_reported':lambda:{},'image_reported':lambda:{}}
def run_adapters(root,instance,prepared,seal_inputs,cfg,fixture_only=False):
    if instance.get('fail'): raise ValueError('adapter refused fixture')
    return [],root,{'fixture':1}
def post_run_image_expectations(pin): return {'image':'fixture'}
def budget_receipt_for_error(exc,elapsed):
    if 'incomplete_budget' not in str(exc): return None
    return {'status':'incomplete_budget','scientific_outputs':[],'last_completed_step':str(exc).split('last_completed=')[1]}
"""
        session_source = """import os, fixture_site_module
def require(value):
    if not value: raise RuntimeError("fixture session invariant failed")
def run_session(**kwargs):
    if kwargs['instance'].get('armed'):
        require(os.environ.get('G9_ALLOW_NONSCIENTIFIC_D013_CUDA_CORRUPTION_QUALIFICATION')=='1')
        require(os.environ.get('G9_ALLOW_NONSCIENTIFIC_CUDA_CORRUPTION_QUALIFICATION')=='1')
    else:
        require('G9_ALLOW_NONSCIENTIFIC_D013_CUDA_CORRUPTION_QUALIFICATION' not in os.environ)
    require(os.environ.get('PYTHONDONTWRITEBYTECODE')=='1')
    require(kwargs['probes']['platform_reported']()=={'fixture':True})
    return {'status':'fixture'}
def validate_receipt(row): return row
"""
        cfg={'instance_path':'instance.json','prepared_record_path':'prepared.json','seal_inputs_path':'inputs.json','seal_path':'seal.json'}
        data={
            'research/__init__.py':b'', 'research/g9/__init__.py':b'',
            'research/g9/kaggle_wp7/__init__.py':b'', 'research/g9/kaggle_wp7b/__init__.py':b'',
            'research/g9/kaggle_wp7/wp7_session.py':session_source.encode(),
            'research/g9/kaggle_wp7b/wp7b_launcher.py':adapter_source.encode(),
            'research/g9/kaggle_wp7/wp7_environment_pin.json':b'{}',
            'research/g9/kaggle_wp7/wp7_reviewed_dependencies.json':b'{"dependencies":[]}',
            'research/g9/kaggle_wp7b/runtime_config.json':json.dumps(cfg).encode(),
            'instance.json':b'{}','prepared.json':b'{}','seal.json':b'{}',
            'inputs.json':b'{"input_hashes":{},"production_identity_hash":"fixture","coordinates":[]}',
        }
        for name,raw in data.items():
            target=root/name; target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(raw)
        index=root/'.index'
        entry=pathlib.Path(child.__file__).resolve()
        site=base/'site-packages'; site.mkdir()
        # Importable hooks must never execute under -S.
        (site/'sitecustomize.py').write_text('raise RuntimeError("site hook executed")')
        (site/'fixture.pth').write_text('import socket\n')
        (site/'fixture_site_module.py').write_text('VALUE = 1\n')
        env={k:v for k,v in os.environ.items() if k in ('PATH','HOME','LANG','TMPDIR')}
        env.update(PYTHONDONTWRITEBYTECODE='1',WP7B_TEST_PROBES_JSON=json.dumps({'platform_reported':{'fixture':True},'image_reported':{}}))
        def invoke(label, extra=None, sites=None, fixture=True, site_argument=None, tamper=False):
            rows=[[name,child.sha((root/name).read_bytes())] for name in sorted(data)]
            index.write_bytes(child.canonical(rows))
            if tamper: (root/'prepared.json').write_bytes(b'{\"tampered\":true}')
            out=base/label
            args=[sys.executable,'-I','-S','-B',str(entry),str(root),str(index),child.sha(index.read_bytes()),str(out),site_argument if site_argument is not None else json.dumps(sites if sites is not None else [str(site)]),'bundle','approval','1' if fixture else '0']
            result=subprocess.run(args,env={**env,**(extra or {})},capture_output=True,text=True,timeout=10)
            receipt=out/'wp7b_receipt.json'; difference=out/'wp7b_difference.json'
            return result,json.loads(receipt.read_text()) if receipt.exists() else None,json.loads(difference.read_text()) if difference.exists() else None
        result,receipt,diff=invoke('valid')
        check(result.returncode==0 and receipt['status']=='pending_image_metadata_audit' and diff is None,result.stderr)
        expected=dict(receipt); digest=expected.pop('content_sha256')
        check(child.sha(child.canonical(expected))==digest,'child receipt digest incorrect')
        check(receipt['bundle_sha256']=='bundle' and receipt['approval_record_sha256']=='approval','receipt binding lost')
        result,receipt,diff=invoke('tampered-main',tamper=True)
        check(result.returncode==2 and receipt is None and diff['error_type']=='ChildRefusal' and 'staged file sha256 mismatch' in diff['difference'],'child main omitted staged verification')
        (root/'prepared.json').write_bytes(b'{}')
        result,receipt,diff=invoke('budget',{'WP7B_TEST_FORCE_BUDGET':'fixture-step'})
        check(result.returncode==0 and receipt['status']=='incomplete_budget' and receipt['last_completed_step']=='fixture-step' and diff is None,'child budget receipt failed')
        (root/'instance.json').write_text('{"fail":true}')
        result,receipt,diff=invoke('adapter-fail')
        check(result.returncode==2 and receipt is None and diff['error_type']=='ValueError' and diff['scientific_outputs']==[],'child adapter refusal failed')
        (root/'instance.json').write_text('{}')
        for label,extra,sites,message in (
            ('env',{'KAGGLE_FAKE':'test'},None,'KAGGLE_'),
            ('injected',{'WP7B_TEST_CHILD_ENV_JSON':'{"KAGGLE_FAKE":"test"}'},None,'KAGGLE_'),
            ('bad-injection',{'WP7B_TEST_CHILD_ENV_JSON':'[]'},None,'injection is malformed'),
            ('bad-injection-value',{'WP7B_TEST_CHILD_ENV_JSON':'{\"fixture\":7}'},None,'injection is malformed'),
            ('empty-sites',{},[],'paths are missing'),
            ('relative-site',{},['relative'],'missing or invalid'),
            ('missing-site',{},[str(base/'absent')],'missing or invalid')):
            result,receipt,diff=invoke(label,extra,sites)
            check(result.returncode==2 and receipt is None and diff['error_type']=='ChildRefusal' and message in diff['difference'],label+' refusal failed')
        result,receipt,diff=invoke('malformed-site-json',site_argument='{')
        check(result.returncode==2 and receipt is None and diff['error_type']=='ChildRefusal' and 'list is malformed' in diff['difference'],'malformed site list was not typed')
        target=root/'research/g9/kaggle_wp7b/wp7b_launcher.py'
        target.write_text(adapter_source.replace("    if 'incomplete_budget' not in str(exc): return None", "    return None"))
        result,receipt,diff=invoke('budget-unrecognized',{'WP7B_TEST_FORCE_BUDGET':'unknown-step'})
        check(result.returncode==2 and receipt is None and diff['last_completed_step']=='unknown-step','unrecognized budget fabricated receipt')
        target.write_text(adapter_source)
        marker=base/'started'
        for label,extra in [('delay-marker',{'WP7B_TEST_CHILD_SLEEP':'0.1','WP7B_TEST_CHILD_STARTED_FILE':str(marker)}),('delay-no-marker',{'WP7B_TEST_CHILD_SLEEP':'0.1'})]:
            start=time.monotonic()
            result,receipt,diff=invoke(label,extra)
            check(result.returncode==0 and receipt is not None and time.monotonic()-start>=0.1,'fixture delay bypassed')
        check(marker.read_text()=='child-entered-fixture-run\n','fixture child entry marker absent')
        # Armed mode ignores all fixture controls and sets permissions after checks.
        (root/'instance.json').write_text('{"armed":true}')
        # Use a platform probe compatible with the non-fixture session assertion.
        target=root/'research/g9/kaggle_wp7b/wp7b_launcher.py'
        target.write_text(adapter_source.replace("lambda:{}","lambda:{'fixture':True}",1))
        result,receipt,diff=invoke('armed',{'WP7B_TEST_CHILD_ENV_JSON':'{"KAGGLE_FAKE":"test"}','WP7B_TEST_FORCE_BUDGET':'bad','WP7B_TEST_CHILD_SLEEP':'999'},fixture=False)
        check(result.returncode==0 and receipt['status']=='pending_image_metadata_audit' and diff is None,'armed fixture seams reachable: '+result.stderr)


def supervisor(runtime, decoded, base):
    """Run the generated outer control flow with a deterministic child boundary."""
    state=dict(runtime)
    main=runtime['main']; scope=main.__globals__
    saved_scope=dict(scope); saved_env=dict(os.environ)
    original_run=subprocess.run
    original_sites=site.getsitepackages
    valid_site=base/'supervisor-site-packages'; valid_site.mkdir()
    site.getsitepackages=lambda:[str(valid_site),str(valid_site),'relative/site-packages',str(base/'missing-site-packages'),None]
    permissions=(child.ALLOW_D013,child.ALLOW_CORE)
    before_permissions={name:os.environ.get(name) for name in permissions}
    try:
        scope['verify_launcher_bytes']=lambda raw:True
        scope['verify_payload']=lambda:decoded
        scope['validate_approval']=lambda raw:{'nonce':'supervisor-fixture'}
        scope['DRAFT']=False; scope['FIXTURE_MODE']=False
        os.environ.update(WP7B_TEST_CHILD_TIMEOUT='0.01',WP7B_TEST_SITE_DIRS_JSON='["/missing"]',WP7B_TEST_TAMPER_STAGED='absent',WP7B_TEST_CHILD_ENV_JSON='{"KAGGLE_FAKE":"test"}')
        for label,code,expected in [('signal',-9,'ChildSignalError'),('exit',7,'ChildProcessError'),('missing',0,'MissingChildReceiptError'),('timeout',124,'ChildTimeoutError')]:
            out=base/('supervisor-'+label); os.environ['KAGGLE_WORKING_DIR']=str(out)
            out.mkdir()
            for filename in ('wp7b_receipt.json','wp7b_difference.json'): (out/filename).write_text('{\"stale\":true}')
            def boundary(command,**kwargs):
                check(command[1:4]==['-I','-S','-B'],'isolation flags changed')
                check(kwargs['timeout']==36300,'child timeout changed')
                sites=json.loads(command[9])
                check(sites.count(str(valid_site))==1 and all(pathlib.Path(value).is_absolute() and pathlib.Path(value).is_dir() for value in sites),'outer site path filtering failed')
                check(command[0]==sys.executable and command[-1]=='0' and pathlib.Path(command[4]).relative_to(pathlib.Path(command[5])).as_posix()=='research/g9/kaggle_wp7b/wp7b_child_entry.py','outer child entry/armed arguments changed')
                check(command[7]==child.sha(pathlib.Path(command[6]).read_bytes()),'outer index digest argument incorrect')
                check(kwargs['cwd']==str(out) and kwargs['env']['PYTHONDONTWRITEBYTECODE']=='1','outer child cwd/bytecode environment changed')
                check(not any(key.startswith('WP7B_TEST_') for key in kwargs['env']),'armed outer forwarded fixture controls')
                check(not (out/'wp7b_receipt.json').exists() and not (out/'wp7b_difference.json').exists(),'outer retained stale child evidence')
                check(not any(k.startswith('KAGGLE_') for k in kwargs['env']),'outer leaked Kaggle environment')
                if label=='timeout': raise subprocess.TimeoutExpired(command,kwargs['timeout'])
                return SimpleNamespace(returncode=code)
            subprocess.run=boundary
            returned=main()
            diff=json.loads((out/'wp7b_difference.json').read_text())
            check(returned==(2 if code==0 else code),'outer failed to relay child exit')
            check(diff['error_type']==expected and diff['last_completed_step']=='isolated_child' and diff['scientific_outputs']==[] and not (out/'wp7b_receipt.json').exists(),'outer fabricated receipt or wrong failure type')
            check(not list(out.glob('wp7b-stage-*')),'outer left private stage behind')
        for label,code,filename in [('receipt',0,'wp7b_receipt.json'),('receipt-with-error',7,'wp7b_receipt.json'),('difference',2,'wp7b_difference.json')]:
            out=base/('supervisor-'+label); os.environ['KAGGLE_WORKING_DIR']=str(out)
            def boundary(command,**kwargs):
                (out/filename).write_text('{"child":"original"}')
                return SimpleNamespace(returncode=code)
            subprocess.run=boundary
            check(main()==code,'outer changed completed child status')
            check((out/filename).read_text()=='{"child":"original"}','outer replaced child evidence')
        check({name:os.environ.get(name) for name in permissions}==before_permissions,'outer armed permission variables')
    finally:
        subprocess.run=original_run
        site.getsitepackages=original_sites
        scope.clear(); scope.update(saved_scope)
        os.environ.clear(); os.environ.update(saved_env)

if __name__=='__main__':
    run()
    print('WP7b child fixtures: PASS')

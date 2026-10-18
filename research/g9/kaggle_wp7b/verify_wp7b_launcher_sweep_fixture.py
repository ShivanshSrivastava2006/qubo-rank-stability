"""Fast direct guard fixture for the WP7b adapter mutation sweep."""
from __future__ import annotations
import contextlib, ctypes, datetime, hashlib, importlib.util, io, json, os, shutil, subprocess, sys, tempfile, types
from array import array
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'research/g9/kaggle_wp7b'))
import wp7b_launcher as launcher
from research.g9 import stage2_section_b2_harness as harness

def require(condition, message):
    if not condition:
        raise RuntimeError(message)

def refuse(call, error_type, label, fragment=None):
    try:
        call()
    except error_type as exc:
        if fragment is not None and fragment not in str(exc):
            raise RuntimeError(label + ' refusal message changed')
        return
    raise RuntimeError(label + ' unexpectedly passed')

def run():
    require(len(launcher.sha(b'x')) == 64, 'sha output malformed')
    require(launcher.canonical({'b': 2, 'a': 1}) == b'{"a":1,"b":2}', 'canonical JSON mismatch')
    require(launcher.result(status='ok')['output'] == {'status': 'ok'}, 'default result output mismatch')
    old_start = launcher.START if hasattr(launcher, 'START') else None
    launcher.START = 1.0
    try:
        launcher.guard(lambda: 1.0, 'step')
        refuse(lambda: launcher.guard(lambda: launcher.BUDGET_SECONDS + 2.0, 'step'), RuntimeError, 'budget guard', 'incomplete_budget:last_completed=step')
        require(launcher.budget_receipt_for_error(RuntimeError('ordinary failure'), 5) is None, 'ordinary exception became a budget receipt')
        budget = launcher.budget_receipt_for_error(RuntimeError('incomplete_budget:last_completed=step'), 5)
        require(budget['status'] == 'incomplete_budget' and budget['last_completed_step'] == 'step', 'budget receipt incomplete')
        calls=[]
        sealed={'energy_minimum_words':['3ff8000000000000'],'canonical_minimum_index':0,
            'tie_flags':[7],'d015_d016_reconstruction':{'c_h':2048,'c_f':2048,
                'set_label':'L','tie_count':1,'x_e_size':1}}
        checked=launcher.budgeted_reference(lambda row,enc:calls.append((row,enc)) or sealed,lambda:1.0,lambda:'wp3')
        row={'family':'primary','coordinate':(30,30,30),'r':1.0,'comparator':'primary',
             'grid':'primary_61_cubed','inactive_positive_zero':False}
        projected=checked(row,(2048,2048),'slack')
        require(calls==[({'family':'primary','point':[30,30,30],'r_hex':'0x1.0000000000000p+0',
            'comparator':'primary','grid':'primary_61_cubed','inactive_positive_zero':'no',
            'c_h':2048,'c_f':2048},'slack')] and projected['energy_minimum_words']==[1.5]
            and projected['canonical_minimum_index']==0 and projected['tie_flags']==[7]
            and projected['reconstruction']=='{"c_f":2048,"c_h":2048,"set_label":"L","tie_count":1,"x_e_size":1}',
            'budgeted reference seal projection failed')
        budgeted=launcher.budgeted_reference(lambda *args:args,lambda:launcher.BUDGET_SECONDS+3.0,lambda:'wp3')
        refuse(lambda:budgeted({'coordinate':{}},('a','b'),'slack'),RuntimeError,'budgeted reference timeout','incomplete_budget')
        checked3=launcher.budgeted_reference(lambda *args:args,lambda:1.0,lambda:'wp3')
        require(checked3(('coordinate',),('a','b'),'slack')==(('coordinate',),('a','b'),'slack'),'non-dict row was not forwarded')
        require(checked3({},('a','b'),'slack')==({},('a','b'),'slack'),'missing coordinate key was not forwarded')
        fallback_reference=launcher.budgeted_reference(lambda *args:args,lambda:1.0,lambda:'wp3')
        require(fallback_reference({'coordinate':{}},'slack')==({'coordinate':{}},'slack'),'budgeted reference fallback changed')
        require(launcher.incomplete_budget_receipt('x',-1)['elapsed_seconds']==0.0,'negative budget time was retained')
    finally:
        if old_start is None: del launcher.START
        else: launcher.START=old_start

    refuse(lambda: launcher.require_wp2_passed(False), RuntimeError, 'WP2 failed gate')
    launcher.require_wp2_passed(True)
    identity={'qualification_identity':{'platform':{'nvcc_version':'fixture'},'source_sha256':{'x':'y'},'compiler_flags':['-O0']},'image_build_evidence':{'fields':{'kaggle_saved_version_build_platform_reported':'build'},'kaggle_image_reported_string':'image'}}
    view=launcher._section_b1_identity_view(identity)
    require(view['platform']['kaggle_image']=='image' and view['compiler']['version']=='fixture' and view['source_sha256']=={'x':'y'},'WP2 identity projection malformed')
    instance={'instance_kind':'synthetic','synthetic':True,'source':'synthetic_generator:tiny-fixture'}

    with tempfile.TemporaryDirectory(dir='/home/shivansh-srivastava/decisions_os/g9_jobs/scratch/wp7biso',prefix='wp7b-launcher-sweep-') as td:
        temp=Path(td)
        module_path=temp/'fixture_module.py'; module_path.write_text('VALUE = 7\n')
        loaded=launcher._load(module_path,'wp7b_launcher_sweep_import')
        require(loaded.VALUE==7,'module loader failed')

        pin={'platform_reported':{'python_version':'x'},'image_reported':{name:'value' for name in launcher.POST_RUN_ONLY_IMAGE_FIELDS}|{'cuda_home':'x'}}
        selected=launcher.environment_comparison_pin(pin)
        require(not any(name in selected['image_reported'] for name in launcher.POST_RUN_ONLY_IMAGE_FIELDS),'post-run fields were kept in comparison pin')
        refuse(lambda:launcher.environment_comparison_pin({'image_reported':{}}),RuntimeError,'incomplete pin')
        refuse(lambda:launcher.environment_comparison_pin([]),RuntimeError,'non-mapping environment pin')
        refuse(lambda:launcher.environment_comparison_pin({'image_reported':None}),RuntimeError,'non-mapping image pin')
        require(launcher.post_run_image_expectations(pin)=={name:'value' for name in launcher.POST_RUN_ONLY_IMAGE_FIELDS},'post-run image fields changed')
        refuse(lambda:launcher.post_run_image_expectations({'image_reported':{}}),RuntimeError,'incomplete post-run metadata')
        refuse(lambda:launcher.post_run_image_expectations({'image_reported':None}),RuntimeError,'non-mapping post-run metadata')

        original_which=launcher.shutil.which
        original_run=launcher.subprocess.run
        try:
            launcher.shutil.which=lambda name:None
            probes=launcher.build_probes(pin)
            require(probes['platform_reported']()['gpu_name'] is None and probes['image_reported']()['nvcc_path'] is None,'CPU probe did not report missing GPU')
            launcher.shutil.which=lambda name:'/fixture/nvcc'
            candidate={'gpu_name':'fixture GPU','compute_capability':'8.0','cuda_driver_version':'12000','cuda_runtime_version':'12010'}
            seen=[]
            def success_run(command,**kwargs):
                seen.append(list(command))
                if '--version' in command:
                    return subprocess.CompletedProcess(command,0,'Cuda compilation tools, release 12.1, V12.1.55','')
                if '-o' in command:
                    source=Path(command[command.index('-o')-1])
                    require(source.is_file() and source.read_text().startswith('#include <cuda_runtime.h>'),'CUDA probe source was not written')
                    return subprocess.CompletedProcess(command,0,'','')
                return subprocess.CompletedProcess(command,0,json.dumps(candidate),'')
            launcher.subprocess.run=success_run
            valid_probes=launcher.build_probes(pin)
            require(valid_probes['platform_reported']()['gpu_name']==candidate['gpu_name'],'valid CUDA probe result was lost')
            require(valid_probes['platform_reported']()['nvcc_version_release']=='12.1, V12.1.55','nvcc release was not parsed')
            require(len(seen)==3,'CUDA probe did not run version, compile, and query')
            bad_candidate=dict(candidate); bad_candidate['unexpected']='x'
            launcher.subprocess.run=lambda command,**kwargs: (subprocess.CompletedProcess(command,0,'release 12.1, V12.1.55','') if '--version' in command else subprocess.CompletedProcess(command,0,'','') if '-o' in command else subprocess.CompletedProcess(command,0,json.dumps(bad_candidate),''))
            bad_probes=launcher.build_probes(pin)
            require(bad_probes['platform_reported']()['gpu_name'] is None,'malformed CUDA probe result was accepted')
            for bad_value in (3, ''):
                value_candidate=dict(candidate); value_candidate['gpu_name']=bad_value
                launcher.subprocess.run=lambda command,**kwargs: (subprocess.CompletedProcess(command,0,'release 12.1, V12.1.55','') if '--version' in command else subprocess.CompletedProcess(command,0,'','') if '-o' in command else subprocess.CompletedProcess(command,0,json.dumps(value_candidate),''))
                invalid_value=launcher.build_probes(pin)
                require(invalid_value['platform_reported']()['gpu_name'] is None,'malformed CUDA field value was accepted')
            def compile_failure(command,**kwargs):
                if '--version' in command: return subprocess.CompletedProcess(command,0,'release 12.1, V12.1.55','')
                return subprocess.CompletedProcess(command,1,'','compile failed')
            launcher.subprocess.run=compile_failure
            with contextlib.redirect_stderr(io.StringIO()) as compile_stderr:
                compile_fail_probes=launcher.build_probes(pin)
            compile_diagnostic=compile_stderr.getvalue()
            require('platform probe compile failed' in compile_diagnostic and 'rc=1' in compile_diagnostic
                and 'compile failed' in compile_diagnostic,'failed probe compile printed no diagnostic')
            require(compile_fail_probes['platform_reported']()['gpu_name'] is None,'failed CUDA probe compile produced a GPU')
            def version_failure(command,**kwargs):
                if '--version' in command: return subprocess.CompletedProcess(command,1,'','version failed')
                if '-o' in command: return subprocess.CompletedProcess(command,0,'','')
                return subprocess.CompletedProcess(command,1,'','query failed')
            launcher.subprocess.run=version_failure
            with contextlib.redirect_stderr(io.StringIO()) as run_stderr:
                run_fail_probes=launcher.build_probes(pin)
            run_diagnostic=run_stderr.getvalue()
            require('platform probe run failed' in run_diagnostic and 'rc=1' in run_diagnostic
                and 'query failed' in run_diagnostic,'failed probe run printed no diagnostic')
            require(run_fail_probes['platform_reported']()['gpu_name'] is None,'failed CUDA probe run produced a GPU')
            launcher.subprocess.run=version_failure
            failed_version=launcher.build_probes(pin)
            require(failed_version['platform_reported']()['nvcc_version_release'] is None,'failed nvcc --version was accepted')
            launcher.subprocess.run=lambda command,**kwargs: (subprocess.CompletedProcess(command,0,'unrecognized version text','') if '--version' in command else subprocess.CompletedProcess(command,0,'','') if '-o' in command else subprocess.CompletedProcess(command,0,json.dumps(candidate),''))
            unrecognized_version=launcher.build_probes(pin)
            require(unrecognized_version['platform_reported']()['nvcc_version_release'] is None,'unrecognized nvcc version text was parsed')
        finally:
            launcher.shutil.which=original_which
            launcher.subprocess.run=original_run

        core=__import__('research.g9.cuda_qualification.stage2_cuda_core_bridge',fromlist=['_load_checked_abi'])
        d013=__import__('research.g9.cuda_qualification.stage2_cuda_d013_inactive',fromlist=['_load_checked_abi'])
        orig_core,orig_d013=core._load_checked_abi,d013._load_checked_abi
        core_path=temp/'core.so'; d013_path=temp/'d013.so'; core_path.write_bytes(b'core'); d013_path.write_bytes(b'd013')
        try:
            core._load_checked_abi=lambda path:None
            d013._load_checked_abi=lambda path,verified_release=None:None
            refuse(lambda:launcher.Wp7bDeviceBackend(core_path,d013_path,{},abi_boundary={},fixture_only=False),RuntimeError,'unapproved ABI injection','fixture-only')
            backend=launcher.Wp7bDeviceBackend(core_path,d013_path,{'approved':True},abi_boundary={'core':lambda *a:None,'d013':lambda *a:None},fixture_only=True,frame_table={})
            require(backend.supports_inactive_positive_zero is True,'inactive-positive-zero declaration missing')
            refuse(lambda:backend({'condition':'CS'},('c','f'),'slack'),RuntimeError,'missing device frame','absent')
            backend._frames={'[]':{}}
            require(backend._key({},('c','f'),'slack')=='[{},["c","f"],"slack"]','device frame key is unstable')
            refuse(lambda:launcher.Wp7bDeviceBackend('core',d013_path,{}),RuntimeError,'non-Path core library')
            refuse(lambda:launcher.Wp7bDeviceBackend(core_path,'d013',{}),RuntimeError,'non-Path D013 library')
            refuse(lambda:launcher.Wp7bDeviceBackend(core_path,temp/'missing.so',{}),RuntimeError,'missing D013 library')
            refuse(lambda:launcher.Wp7bDeviceBackend(temp/'missing-core.so',d013_path,{}),RuntimeError,'missing core library')
            core._load_checked_abi=lambda path:(_ for _ in ()).throw(RuntimeError('core ABI loader fixture refusal'))
            refuse(lambda:launcher.Wp7bDeviceBackend(core_path,d013_path,{}),RuntimeError,'core ABI loader call','core ABI loader fixture refusal')
            core._load_checked_abi=lambda path:None
            d013._load_checked_abi=lambda path,verified_release=None:(_ for _ in ()).throw(RuntimeError('D013 ABI loader fixture refusal'))
            refuse(lambda:launcher.Wp7bDeviceBackend(core_path,d013_path,{}),RuntimeError,'D013 ABI loader call','D013 ABI loader fixture refusal')
            d013._load_checked_abi=lambda path,verified_release=None:None

            from research.g9.cuda_qualification import stage2_cuda_reconstruct as recon
            n=recon.STATE_COUNT; offsets=array('Q',range(n+1))
            offset_sha=hashlib.sha256(offsets.tobytes()).hexdigest()
            g4={'tickers':[f'F{i}' for i in range(20)],'sectors':[[0,1,2,3,4],[5,6,7,8,9],[10,11,12,13,14],[15,16,17,18,19]],
                'mu':[0.0]*20,'sigma':[[0.0]*20 for _ in range(20)],'prices':[0.0]*20,
                'kappa_risk':1.0,'K':0,'C':5,'B':0.0}
            def fake_reconstruction(_result,_slack,_classifiers,_fstar,_lam):
                def summary(ch,cf): return {'c_H':ch,'c_f':cf,'set_label':'A','T_E_size':1,'X_E_size':1}
                return {'primary_c_h_2048':{enc:summary(2048,2048) for enc in ('unbalanced','slack')},
                    'd015_diagnostics':{f'c_H={ch}__c_f={cf}':{enc:summary(ch,cf) for enc in ('unbalanced','slack')}
                        for ch,cf in recon.DIAGNOSTIC_PAIRS}}
            original_reconstruct=recon.reconstruct_pair
            recon.reconstruct_pair=fake_reconstruction
            try:
                crow={'family':'primary','coordinate':(30,30,30),'r':1.0,'grid':'primary','comparator':'primary'}
                drow={'family':'d013_repeat','condition':'C','coordinate':(30,30,30),'r':1.0,'grid':'primary','comparator':'primary'}
                def make_frame(row,condition):
                    return {'row':row,'payload':{},'records':[],'condition':condition,'feasible_count':1,
                        'instance':g4,'lambda_ref':1.0,'f_star':0.0,'input_frame':{},'slot':0}
                cframe=make_frame(crow,'CSB'); dframe=make_frame(drow,'C')
                routed=[]
                def summary(enc): return {'word_count':n,'minimum':1.0,'minimum_index':0,
                    'per_ch':(1,1,1),'compacted_count':1,'compacted_entries':((7<<32)|0,),
                    'illegal':0,'nesting':0,'compaction_chunks':0,'compaction_checksum':0}
                core_raw={'backend':0,'offsets_sha256':offset_sha,'captured_offsets':offsets,
                    'core_result':{'lift_total':n,'summaries':{(0,enc):summary(enc) for enc in ('unbalanced','slack')}}}
                d_raw={'backend':0,'counters':{'lift_total_base':n},'records':[
                    {'encoding':enc,'word_count':n,'minimum':1.0,'minimum_index':0,
                     'per_ch':(1,1,1),'compacted_count':1,'compacted_entries':((7<<32)|0,),
                     'illegal':0,'nesting':0} for enc in ('unbalanced','slack')]}
                backend._frames={launcher.Wp7bDeviceBackend._row_key(crow):cframe,
                    launcher.Wp7bDeviceBackend._row_key(drow):dframe}
                backend._row_cache={}; backend._active_offsets={}
                backend._boundary={'core':lambda *a:(routed.append('core') or core_raw),
                    'd013':lambda *a:(routed.append('d013') or d_raw)}
                backend._offsets_for_frame=lambda *a:(offsets,n,offset_sha)
                for unit_row in (crow,drow):
                    for enc in ('unbalanced','slack'):
                        for pair in harness.D015_COMPARATOR_PAIRS:
                            result=backend(unit_row,pair,enc)
                            require(result['canonical_minimum_index']==0 and result['tie_flags']==[7],
                                'device result omitted the canonical flag prefix')
                            projected=json.loads(result['reconstruction'])
                            require(set(projected)=={'c_h','c_f','set_label','tie_count','x_e_size'} and
                                projected['c_h']==pair[0] and projected['c_f']==pair[1],
                                'seal reconstruction projection drifted')
                require(routed==['core','d013'],'each row must make one call to its routed ABI')
                require(backend.supports_inactive_positive_zero is True,'D013 route declaration changed')
                # The frozen reconstructor still refuses a malformed compacted minimum.
                recon.reconstruct_pair=original_reconstruct
                bad=launcher.Wp7bDeviceBackend(core_path,d013_path,{'approved':True},fixture_only=True,
                    abi_boundary={'core':lambda *a:None,'d013':lambda *a:None},frame_table={})
                bad._frames={launcher.Wp7bDeviceBackend._row_key(drow):dframe}
                bad._offsets_for_frame=lambda *a:(offsets,n,offset_sha)
                malformed=dict(d_raw); malformed['records']=[dict(item,compacted_entries=((4<<32)|0,),per_ch=(0,0,1)) for item in d_raw['records']]
                bad._boundary={'d013':lambda *a:malformed,'core':lambda *a:None}
                refuse(lambda:bad(drow,(2048,2048),'slack'),RuntimeError,'corrupted tie flags','minimum state is not tied')

                # Exercise the structural offset rules with a one-state test
                # domain. Production still walks the frozen 2^20 BinaryDomain.
                from src.g4 import energy as energy_module
                import src.g5.domains as domains_module
                original_prepare=energy_module.prepare_instance
                original_residuals=energy_module._residuals_from_bits
                original_domain=domains_module.BinaryDomain
                original_register=domains_module._register_minimizers
                try:
                    energy_module.prepare_instance=lambda instance:types.SimpleNamespace(instance=instance)
                    energy_module._residuals_from_bits=lambda instance,bits:(0,(1,1,1,1),1)
                    domains_module.BinaryDomain=lambda width:iter(((0,)*20,))
                    domains_module._register_minimizers=lambda residual,bound:list(range(2 if bound==3 else 3))
                    structural_frame={'instance':g4,'payload':{}}
                    for condition,expected in (('C',1),('CS',16),('CB',3),('CSB',48)):
                        got,total,digest=launcher.Wp7bDeviceBackend._offsets_for_frame(structural_frame,condition)
                        require(total==expected and got==(0,expected) and len(digest)==64,
                            'structural D013 offset condition rule drifted: '+condition+' '+repr((got,total)))
                    refuse(lambda:launcher.Wp7bDeviceBackend._offsets_for_frame({'instance':None,'payload':{}},'CSB'),RuntimeError,
                        'structural offsets require instance','frozen G4 instance')
                finally:
                    energy_module.prepare_instance=original_prepare
                    energy_module._residuals_from_bits=original_residuals
                    domains_module.BinaryDomain=original_domain
                    domains_module._register_minimizers=original_register

                # Classifier guards cover cardinality plus each active G4
                # feasibility condition for the frozen three c_f classifiers.
                from src.g4 import constraints as constraints_module
                original_sector,original_budget=constraints_module.sector,constraints_module.budget
                try:
                    constraints_module.sector=lambda instance,x:([-1.0,0.0,0.0,0.0] if x[1] else [1.0]*4)
                    constraints_module.budget=lambda instance,x:(-1.0 if x[2] else 1.0)
                    instance_one=dict(g4,K=1,prices=[1.0]*20,C=100,B=100.0)
                    class_frame={'instance':instance_one,'lambda_ref':1.0,'f_star':0.0,
                        'row':{'family':'classifier_probe','coordinate':(30,30,30),'r':1.0,'grid':'primary','comparator':'primary'}}
                    bad_card=[0]*20
                    groups,fs,lam=backend._construct_classifiers(class_frame,'CSB')
                    require(set(groups)=={1024,2048,4096} and not groups[2048].feasible(bad_card),
                        'decoded classifier cardinality guard drifted '+repr((set(groups),groups[2048].feasible(bad_card))))
                    good=[1]+[0]*19; bad_sector=[0,1]+[0]*18; bad_budget=[0,0,1]+[0]*17
                    require(groups[2048].feasible(good) and not groups[2048].feasible(bad_sector)
                        and not groups[2048].feasible(bad_budget),'decoded classifier CSB constraints drifted')
                    groups_cs,_,_=backend._construct_classifiers(class_frame,'CS')
                    require(not groups_cs[2048].feasible(bad_sector),'decoded classifier sector condition drifted')
                    groups_cb,_,_=backend._construct_classifiers(class_frame,'CB')
                    require(not groups_cb[2048].feasible(bad_budget),'decoded classifier budget condition drifted')
                    groups_c,_,_=backend._construct_classifiers(class_frame,'C')
                    require(groups_c[2048].feasible(good) and groups_c[2048].feasible(bad_sector)
                        and groups_c[2048].feasible(bad_budget),
                        'unconstrained decoded classifier applied sector/budget filters')
                    refuse(lambda:backend._construct_classifiers({'instance':None},'CSB'),RuntimeError,
                        'frozen classifier requires instance','validated G4 instance')
                finally:
                    constraints_module.sector=original_sector; constraints_module.budget=original_budget

                # The checked core bridge must capture offsets inside the same
                # ABI call and fail closed when copy_offsets does not succeed.
                original_checked=backend._core_bridge._load_checked_abi
                original_compiled=backend._core_bridge._run_compiled_frame
                def fake_checked(path):
                    def copy(dst,count):
                        for ix in range(count): dst[ix]=offsets[ix]
                        return 1
                    return (lambda *args:1),copy,0
                def fake_compiled(frame,path,*,require_backend):
                    _,copy,tag=backend._core_bridge._load_checked_abi(path)
                    dst=(ctypes.c_uint64*(n+1))(); copy(dst,n+1)
                    return {'offsets_sha256':hashlib.sha256(ctypes.string_at(ctypes.addressof(dst),ctypes.sizeof(dst))).hexdigest(),
                        'core_result':{'lift_total':n},'backend':tag}
                try:
                    backend._core_bridge._load_checked_abi=fake_checked
                    backend._core_bridge._run_compiled_frame=fake_compiled
                    captured,copied=backend._run_core_with_offsets(cframe)
                    require(copied==tuple(offsets) and captured['backend']==0,'validated core offsets were not captured')
                    backend._core_bridge._load_checked_abi=lambda path:(lambda *args:1,lambda dst,count:0,0)
                    refuse(lambda:backend._run_core_with_offsets(cframe),RuntimeError,
                        'core offset copy failure','did not expose copied offsets')
                finally:
                    backend._core_bridge._load_checked_abi=original_checked
                    backend._core_bridge._run_compiled_frame=original_compiled

                # Armed/fixture backend tags, D013 lift census, and the
                # all-active repeated CSB structural offset check are live
                # guards, so drive them through the exact backend class.
                dcsbrow={'family':'d013_repeat','condition':'CSB','coordinate':(30,30,30),
                    'r':1.0,'grid':'primary','comparator':'primary'}
                dcsbframe=make_frame(dcsbrow,'CSB')
                backend._frames[launcher.Wp7bDeviceBackend._row_key(dcsbrow)]=dcsbframe
                backend._row_cache={}; backend._active_offsets={}
                wrong_core=dict(core_raw,backend=1)
                backend._boundary={'core':lambda *a:wrong_core,'d013':lambda *a:d_raw}
                refuse(lambda:backend(crow,(2048,2048),'slack'),RuntimeError,
                    'fixture core backend tag mismatch','backend differs')
                backend._fixture_only=False
                backend._boundary={'core':lambda *a:core_raw,'d013':lambda *a:d_raw}
                backend._row_cache={}
                refuse(lambda:backend(crow,(2048,2048),'slack'),RuntimeError,
                    'armed core backend tag mismatch','backend differs')
                backend._fixture_only=True
                bad_core_type=dict(core_raw,backend=0.0)
                backend._boundary={'core':lambda *a:bad_core_type,'d013':lambda *a:d_raw}
                backend._row_cache={}
                refuse(lambda:backend(crow,(2048,2048),'slack'),RuntimeError,
                    'non-integer core backend tag','backend differs')
                wrong_d013=dict(d_raw,backend=1)
                backend._boundary={'core':lambda *a:core_raw,'d013':lambda *a:wrong_d013}
                backend._row_cache={}
                refuse(lambda:backend(drow,(2048,2048),'slack'),RuntimeError,
                    'fixture D013 backend tag mismatch','backend differs')
                backend._fixture_only=False
                backend._boundary={'core':lambda *a:core_raw,'d013':lambda *a:d_raw}
                backend._row_cache={}
                refuse(lambda:backend(drow,(2048,2048),'slack'),RuntimeError,
                    'armed D013 backend tag mismatch','backend differs')
                backend._fixture_only=True
                bad_d013_type=dict(d_raw,backend=0.0)
                backend._boundary={'core':lambda *a:core_raw,'d013':lambda *a:bad_d013_type}
                backend._row_cache={}
                refuse(lambda:backend(drow,(2048,2048),'slack'),RuntimeError,
                    'non-integer D013 backend tag','backend differs')
                wrong_count=dict(d_raw,counters={'lift_total_base':n+1})
                backend._boundary={'core':lambda *a:core_raw,'d013':lambda *a:wrong_count}
                backend._row_cache={}
                refuse(lambda:backend(drow,(2048,2048),'slack'),RuntimeError,
                    'D013 lift census mismatch','lift_total_base')
                missing_offsets=dict(core_raw,captured_offsets=None)
                backend._boundary={'core':lambda *a:missing_offsets,'d013':lambda *a:d_raw}
                backend._row_cache={}
                refuse(lambda:backend(crow,(2048,2048),'slack'),RuntimeError,
                    'fixture core omitted copied offsets','omitted captured ABI offsets')

                # First active core result establishes the same-instance
                # offsets. The D013-repeat CSB row then uses core and checks
                # host-derived structure against both device copies.
                backend._boundary={'core':lambda *a:core_raw,'d013':lambda *a:d_raw}
                backend._offsets_for_frame=lambda *a:(offsets,n,offset_sha)
                backend._row_cache={}; backend._active_offsets={}
                backend(crow,(2048,2048),'slack')
                backend._row_cache.pop(launcher.Wp7bDeviceBackend._row_key(dcsbrow),None)
                require(backend(dcsbrow,(2048,2048),'slack')['tie_flags']==[7],
                    'active CSB repeated row did not use validated core offsets')

                # Each side of the repeat-CSB route predicate is live. These
                # neighboring row shapes must not enter the repeat-CSB route.
                for family,condition in (('d013_repeat','OTHER'),('other_family','CSB')):
                    probe_row={'family':family,'condition':condition,'coordinate':(29,29,29),
                        'r':1.0,'grid':'primary','comparator':'primary'}
                    backend._frames[launcher.Wp7bDeviceBackend._row_key(probe_row)]=make_frame(probe_row,condition)
                    backend._row_cache={}; backend._active_offsets={}
                    backend._offsets_for_frame=lambda *a:(bad_offsets,n,offset_sha)
                    require(backend(probe_row,(2048,2048),'slack')['tie_flags']==[7],
                        'non-repeat-CSB row entered the repeat-CSB offset route')

                bad_offsets=list(offsets); bad_offsets[2]+=1; bad_offsets=tuple(bad_offsets)
                instance_key=hashlib.sha256(json.dumps(dcsbframe['payload'],sort_keys=True,
                    separators=(',',':'),default=str).encode()).hexdigest()
                for host_offsets,host_total,host_digest,label in (
                    (offsets,n+1,offset_sha,'lift total'),
                    (offsets,n,'0'*64,'offset digest'),
                    (bad_offsets,n,offset_sha,'offset bytes')):
                    backend._offsets_for_frame=lambda *a,values=(host_offsets,host_total,host_digest):values
                    backend._row_cache={}; backend._active_offsets={instance_key:(host_offsets,host_digest)}
                    refuse(lambda:backend(dcsbrow,(2048,2048),'slack'),RuntimeError,
                        'D013 CSB '+label+' mismatch','host CSB structural offsets differ')
                backend._offsets_for_frame=lambda *a:(offsets,n,offset_sha)
                # Check the active-offset presence guard, then each component
                # independently while the current host/device check matches.
                backend._row_cache={}; backend._active_offsets={}
                refuse(lambda:backend(dcsbrow,(2048,2048),'slack'),RuntimeError,
                    'D013 CSB missing active offsets','active core offsets')
                for prior,label in (((bad_offsets,offset_sha),'prior offset bytes'),
                                    ((offsets,'0'*64),'prior offset digest')):
                    backend._row_cache={}; backend._active_offsets={instance_key:prior}
                    refuse(lambda:backend(dcsbrow,(2048,2048),'slack'),RuntimeError,
                        'D013 CSB '+label,'host CSB structural offsets differ from active core offsets')

                # The final canonical-flag check is independent of the frozen
                # reconstructor; stub only that pure function to reach it.
                original_stream=recon.reconstruct_stream
                def fake_stream(encoding,*args):
                    stream=fake_reconstruction(None,None,None,None,None)
                    return {'primary_c_h_2048':stream['primary_c_h_2048'][encoding],
                        'd015_diagnostics':{key:value[encoding] for key,value in stream['d015_diagnostics'].items()}}
                try:
                    recon.reconstruct_stream=fake_stream
                    bad_flag={**d_raw,'records':[dict(item,compacted_entries=((4<<32)|0,)) for item in d_raw['records']]}
                    backend._boundary={'core':lambda *a:core_raw,'d013':lambda *a:bad_flag}
                    backend._row_cache={}
                    refuse(lambda:backend(drow,(2048,2048),'slack'),RuntimeError,
                        'backend canonical device flag guard','canonical minimum flags')
                finally:
                    recon.reconstruct_stream=original_stream
            finally:
                recon.reconstruct_pair=original_reconstruct
        finally:
            core._load_checked_abi=orig_core; d013._load_checked_abi=orig_d013

        original_which=launcher.shutil.which; original_run=launcher.subprocess.run; original_load=launcher._load
        compile_commands=[]; abi_loads=[]
        def fake_loader(path,name):
            if name=='wp7b_core_abi':
                return types.SimpleNamespace(_load_checked_abi=lambda lib:abi_loads.append(('core',str(lib))))
            if name=='wp7b_d013_abi':
                return types.SimpleNamespace(_load_checked_abi=lambda lib:abi_loads.append(('d013',str(lib))))
            if name in ('wp7b_core_corruption_qualification','wp7b_d013_corruption_qualification'):
                return types.SimpleNamespace(build_plan=lambda:{'mutations':[1]})
            return types.SimpleNamespace(run_qualification=lambda release:{'mutations':[1],'verified_release_token':{'approved':True}})
        launcher._load=fake_loader
        launcher.shutil.which=lambda name:'/fixture/nvcc'
        def compile_ok(command,**kwargs):
            compile_commands.append(list(command))
            if '--self-test' in command:
                return subprocess.CompletedProcess(command,0,'','')
            output=Path(command[command.index('-o')+1]); output.write_bytes(b'compiled fixture library')
            source=Path(command[command.index('-o')-1])
            has_shared='-shared' in command
            require(has_shared == (source.name!='stage2_cuda_core_stream_engine.cu'),'CUDA compile link mode changed')
            return subprocess.CompletedProcess(command,0,'','')
        launcher.subprocess.run=compile_ok
        try:
            qualification_steps,_,_=launcher.run_adapters(temp,instance,{}, {},{'corruption_release_sha256':'a'*64,'d013_corruption_release_sha256':'b'*64},fixture_only=True)
            qualification=qualification_steps['wp6b_section_a_qualification_plan']()
            require(qualification['status']=='ok' and len(compile_commands)==4,'CUDA qualification compile sequence incomplete')
            require({row[0] for row in abi_loads}=={'core','d013'},'compiled ABI validators were skipped')

            # The armed path must carry the real D013 qualification token into
            # the runtime config; only the fixture path may use the plan marker.
            qualification_config={'corruption_release_sha256':'a'*64,
                'd013_corruption_release_sha256':'b'*64}
            verified_token={'approved':'sentinel'}
            qualification_loader=launcher._load
            def armed_qualification_loader(path,name):
                if name=='wp7b_core_corruption_qualification':
                    return types.SimpleNamespace(run_qualification=lambda release:{'mutations':[1]})
                if name=='wp7b_d013_corruption_qualification':
                    return types.SimpleNamespace(run_qualification=lambda release:{
                        'mutations':[1],'verified_release_token':verified_token})
                return qualification_loader(path,name)
            launcher._load=armed_qualification_loader
            try:
                armed_qualification_steps,_,_=launcher.run_adapters(temp,instance,{}, {},
                    qualification_config,fixture_only=False)
                armed_qualification_steps['wp6b_section_a_qualification_plan']()
            finally:
                launcher._load=qualification_loader
            require(qualification_config['verified_d013_release_token'] is verified_token,
                    'armed qualification replaced the verified D013 release token')
            plan_config={'corruption_release_sha256':'a'*64,
                'd013_corruption_release_sha256':'b'*64}
            plan_steps,_,_=launcher.run_adapters(temp,instance,{}, {},plan_config,fixture_only=True)
            plan_steps['wp6b_section_a_qualification_plan']()
            require(plan_config['verified_d013_release_token']=={'host_emulation_plan_only':True},
                    'fixture qualification omitted its plan-only D013 marker')

            def compile_error(command,**kwargs):
                if '--self-test' in command: return subprocess.CompletedProcess(command,0,'','')
                return subprocess.CompletedProcess(command,1,'','fixture compile failure')
            launcher.subprocess.run=compile_error
            failed_compile_steps,_,_=launcher.run_adapters(temp,instance,{}, {},{'corruption_release_sha256':'a'*64,'d013_corruption_release_sha256':'b'*64},fixture_only=True)
            refuse(lambda:failed_compile_steps['wp6b_section_a_qualification_plan'](),RuntimeError,'nvcc compile failure','nvcc compile failed')

            def self_test_error(command,**kwargs):
                if '--self-test' in command: return subprocess.CompletedProcess(command,1,'','self-test fixture failure')
                Path(command[command.index('-o')+1]).write_bytes(b'compiled fixture library')
                return subprocess.CompletedProcess(command,0,'','')
            launcher.subprocess.run=self_test_error
            failed_selftest_steps,_,_=launcher.run_adapters(temp,instance,{}, {},{'corruption_release_sha256':'a'*64,'d013_corruption_release_sha256':'b'*64},fixture_only=True)
            refuse(lambda:failed_selftest_steps['wp6b_section_a_qualification_plan'](),RuntimeError,'core self-test failure','self-test failed')
        finally:
            launcher.shutil.which=original_which; launcher.subprocess.run=original_run; launcher._load=original_load

        accepted_identity={'fixture':'identity'}
        hook_calls=[]
        hooks={
            'wp6b':lambda *a:(hook_calls.append('wp6b') or {'status':'ok'}),
            'wp1':lambda *a:(hook_calls.append('wp1') or accepted_identity),
            'wp2':lambda *a:(hook_calls.append('wp2') or {'gate_passed':True,'checks_passed':3}),
            'wp3':lambda *a:(hook_calls.append('wp3') or {'rows_visited':4}),
            'wp4b':lambda *a:(hook_calls.append('wp4b') or {'ranges_written':1}),
        }
        refuse(lambda:launcher.run_adapters(temp,instance,{}, {}, {},emulation_hooks={'wp1':lambda *a:None}),RuntimeError,'non-fixture hook','fixture-only')
        no_hook_steps,_,_=launcher.run_adapters(temp,instance,{}, {},{},fixture_only=False)
        require('wp1_production_identity_candidate' in no_hook_steps,'adapter setup without fixture hooks refused')
        steps,out,_=launcher.run_adapters(temp,instance,{}, {}, {},emulation_hooks=hooks,fixture_only=True)
        require(steps['synthetic_instance_gate']()['status']=='ok','synthetic instance gate failed')
        require(steps['wp6b_section_a_qualification_plan']()['status']=='ok','fixture qualification failed')
        require(steps['wp1_production_identity_candidate']()['status']=='ok','fixture WP1 failed')
        require(steps['section_b_item_1_recheck_synthetic']()['status']=='ok','fixture WP2 failed')
        require(steps['section_b_item_2_full_domain_synthetic'](lambda *a:True)['status']=='ok','fixture WP3 failed')
        require(steps['wp4b_writer_synthetic_ranges']()['status']=='ok','fixture WP4 failed')
        require(set(hook_calls)=={'wp6b','wp1','wp2','wp3','wp4b'} and out.is_dir(),'adapter hook sequence incomplete')

        real_steps,_,_=launcher.run_adapters(temp,instance,{}, {}, {},fixture_only=True)
        refuse(lambda:real_steps['wp6b_section_a_qualification_plan'](),launcher.NvccUnavailableError,'missing nvcc','nvcc unavailable')
        harness_path=temp/'research/g9/stage2_section_b2_harness.py'; harness_path.parent.mkdir(parents=True,exist_ok=True); harness_path.write_text('# fixture harness stub\n')
        no_lib_steps,_,_=launcher.run_adapters(temp,instance,{}, {}, {'production_identity':{}},fixture_only=True)
        refuse(lambda:no_lib_steps['section_b_item_2_full_domain_synthetic'](lambda *a:True),RuntimeError,'WP3 missing libraries','no compiled core/D013')
        for partial in ({'compiled_d013_library':str(d013_path)},{'compiled_core_library':str(core_path)}):
            partial_steps,_,_=launcher.run_adapters(temp,instance,{}, {},partial,fixture_only=True)
            refuse(lambda partial_steps=partial_steps:partial_steps['section_b_item_2_full_domain_synthetic'](lambda *a:True),RuntimeError,'WP3 partial libraries','no compiled core/D013')
        runtime_config={'compiled_core_library':str(core_path),'compiled_d013_library':str(d013_path),'verified_d013_release_token':None}
        injected_steps,_,_=launcher.run_adapters(temp,instance,{}, {},runtime_config,fixture_only=True)
        refuse(lambda:injected_steps['section_b_item_2_full_domain_synthetic'](lambda *a:True),RuntimeError,'missing D013 release token','approved D013 VerifiedReleaseToken')
        runtime_config['verified_d013_release_token']={}
        runtime_config['device_backend']=lambda:None
        injected_steps,_,_=launcher.run_adapters(temp,instance,{}, {},runtime_config,fixture_only=True)
        refuse(lambda:injected_steps['section_b_item_2_full_domain_synthetic'](lambda *a:True),RuntimeError,'JSON callable backend','fixture-only')
        runtime_config['device_backend']=None; runtime_config['device_backend_factory']=lambda:None
        factory_steps,_,_=launcher.run_adapters(temp,instance,{}, {},runtime_config,fixture_only=True)
        refuse(lambda:factory_steps['section_b_item_2_full_domain_synthetic'](lambda *a:True),RuntimeError,'JSON callable backend factory','fixture-only')
        invalid_wp4_steps,_,_=launcher.run_adapters(temp,instance,{}, {},{'batch_ids':None},fixture_only=True)
        refuse(lambda:invalid_wp4_steps['wp4b_writer_synthetic_ranges'](),RuntimeError,'invalid WP4 batch list','must be a list')
        empty_wp4_steps,_,_=launcher.run_adapters(temp,instance,{}, {},{'batch_ids':[]},fixture_only=True)
        refuse(lambda:empty_wp4_steps['wp4b_writer_synthetic_ranges'](),RuntimeError,'empty WP4 batch list','absent')
        failed_wp2_hooks=dict(hooks); failed_wp2_hooks['wp2']=lambda *a:{'gate_passed':False}
        failed_wp2_steps,_,_=launcher.run_adapters(temp,instance,{}, {},{'production_identity':accepted_identity},emulation_hooks=failed_wp2_hooks,fixture_only=True)
        refuse(lambda:failed_wp2_steps['section_b_item_1_recheck_synthetic'](),RuntimeError,'fixture WP2 gate refusal','recheck refused')
        production_identity_path=temp/'research/g9/stage2_production_identity.py'
        production_identity_path.write_text('def validate_production_identity(value): return "valid"\ndef exact_match(left,right): return True\n')
        recheck_path=temp/'research/g9/stage2_section_b1_recheck.py'
        recheck_path.write_text('def recheck_before_first_write(**kwargs):\n kwargs["validate_identity"](None)\n return ({},False)\n')
        wp2_config={'accepted_identity':identity,'production_identity':identity,'observed_approval_sha256':'a','expected_approval_sha256':'a','generator_implementation_record_sha256':'b','expected_generator_implementation_record_sha256':'b','ground_truth_provenance_sha256':'c','expected_ground_truth_provenance_sha256':'c'}
        malformed_wp2_steps,_,_=launcher.run_adapters(temp,instance,{}, {},wp2_config,fixture_only=True)
        refuse(lambda:malformed_wp2_steps['section_b_item_1_recheck_synthetic'](),RuntimeError,'malformed WP2 wrapper','identity wrapper is malformed')
        recheck_path.write_text('def recheck_before_first_write(**kwargs):\n kwargs["validate_identity"]({"wrong":{}})\n return ({},False)\n')
        malformed_key_steps,_,_=launcher.run_adapters(temp,instance,{}, {},wp2_config,fixture_only=True)
        refuse(lambda:malformed_key_steps['section_b_item_1_recheck_synthetic'](),RuntimeError,
            'malformed WP2 wrapper key','identity wrapper is malformed')
        recheck_path.write_text('def recheck_before_first_write(**kwargs):\n kwargs["validate_identity"]({"production_identity":{}})\n return ({},False)\n')
        false_wp2_steps,_,_=launcher.run_adapters(temp,instance,{}, {},wp2_config,fixture_only=True)
        refuse(lambda:false_wp2_steps['section_b_item_1_recheck_synthetic'](),RuntimeError,'actual WP2 false result','identity recheck refused')

        # WP1 uses the same checked pin mapping as seal construction. Runtime
        # observations, not config values, supply the 13 in-session fields.
        from research.g9.kaggle_wp7b import wp7b_identity_binding as binding
        pin_path=temp/'research/g9/kaggle_wp7/wp7_environment_pin.json'
        pin_path.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/'research/g9/kaggle_wp7/wp7_environment_pin.json',pin_path)
        binding_path=temp/'research/g9/kaggle_wp7b/wp7b_identity_binding.py'
        binding_path.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/'research/g9/kaggle_wp7b/wp7b_identity_binding.py',binding_path)
        pin=binding.load_pin(str(pin_path)); expected=binding.expected_observations(pin)
        expected_platform={k:expected[k] for k in ('gpu_name','compute_capability','cuda_driver_version','cuda_runtime_version','nvcc_version_release','python_version','numpy_version')}
        expected_image={'build_env':{k:expected[k] for k in ('BUILD_DATE','COLAB_IMAGE_TYPE','CUDA_VERSION','GIT_COMMIT')},'cuda_home':expected['CUDA_HOME'],'nvcc_path':expected['nvcc_path']}
        production_identity_path.write_text(
            'def build_production_identity(**kwargs): return {"fixture": kwargs}\n'
            'def validate_production_identity(value): return "fixture-identity-sha256"\n'
        )
        probe_functions={'platform_reported':lambda:dict(expected_platform),
                         'image_reported':lambda:dict(expected_image)}
        expected_identity=binding.build_identity_mapping(pin,expected)
        wp1_base={'runtime_probes':probe_functions,
            'role_paths':{'fixture':'role.py'},'image_build':expected_identity[1],
            'compiler_flags':['-O0']}
        def wp1_call(config):
            wp1_steps,_,_=launcher.run_adapters(temp,instance,{}, {},config,fixture_only=True)
            return wp1_steps['wp1_production_identity_candidate']()
        valid_wp1=wp1_call(dict(wp1_base))
        require(valid_wp1['status']=='ok' and
                valid_wp1['identities']['production_identity_sha256']=='fixture-identity-sha256',
                'valid pin-backed WP1 observations failed')
        for bad_probes in (None,{}, {'platform_reported':probe_functions['platform_reported']},
                           ['platform_reported','image_reported']):
            bad=dict(wp1_base); bad['runtime_probes']=bad_probes
            refuse(lambda bad=bad:wp1_call(bad),RuntimeError,'malformed WP1 runtime probes',
                   'WP1 runtime platform probes are absent')
        bad=dict(wp1_base); bad['runtime_probes']={'unexpected':lambda:{}}
        refuse(lambda:wp1_call(bad),RuntimeError,'WP1 runtime probe key set',
               'WP1 runtime platform probes are absent')
        for bad_platform in ({},expected_platform|{'extra':'value'},
                             expected_platform|{'cuda_driver_version':7},
                             expected_platform|{'cuda_driver_version':''}):
            bad=dict(wp1_base)
            bad['runtime_probes']={'platform_reported':lambda bad_platform=bad_platform:bad_platform,
                                   'image_reported':lambda:dict(expected_image)}
            refuse(lambda bad=bad:wp1_call(bad),ValueError,'malformed observed WP1 fields',
                   'WP7 identity observation')
        for field, bad_value in (('platform_reported',None),('image_reported',None)):
            bad=dict(wp1_base)
            bad['runtime_probes']={
                'platform_reported':(lambda:bad_value) if field=='platform_reported' else probe_functions['platform_reported'],
                'image_reported':(lambda:bad_value) if field=='image_reported' else probe_functions['image_reported']}
            refuse(lambda bad=bad:wp1_call(bad),RuntimeError,'non-mapping WP1 observations',
                   'WP1 runtime observations are malformed')
        bad_image=dict(expected_image); bad_image['build_env']=None
        bad=dict(wp1_base); bad['runtime_probes']={
            'platform_reported':probe_functions['platform_reported'],
            'image_reported':lambda:dict(bad_image)}
        refuse(lambda:wp1_call(bad),RuntimeError,'missing WP1 image build observations',
               'WP1 image build environment observations are absent')
        bad=dict(wp1_base); bad['image_build']={'wrong':'config'}
        refuse(lambda:wp1_call(bad),RuntimeError,'config cannot supply identity evidence',
               'WP1 generated image/build mapping differs')
        different_observation=dict(expected_platform); different_observation['cuda_driver_version']='different driver'
        nonmatching=dict(wp1_base); nonmatching['image_build']={'wrong':'config'}
        nonmatching['runtime_probes']={'platform_reported':lambda:dict(different_observation),
                                      'image_reported':probe_functions['image_reported']}
        require(wp1_call(nonmatching)['status']=='ok',
                'config declaration guard rejected non-pin runtime observations')

        # An armed WP3 must instantiate the device backend and call the real
        # harness adapter. It must never start the isolated host worker.
        original_load=launcher._load; original_backend=launcher.Wp7bDeviceBackend
        original_subprocess_run=launcher.subprocess.run
        backend_events=[]; worker_commands=[]
        class DeviceBackendSpy:
            def __init__(self,*args,**kwargs):
                backend_events.append(('construct',kwargs.get('fixture_only')))
            def __call__(self,*args):
                backend_events.append(('device_call',None)); return {'device':'used'}
        fake_harness=types.SimpleNamespace(run_section_b2=lambda backend,*args,**kwargs:
            (backend({'row':1},(1,1),'slack') or {'counters':{'coordinate_rows':1,'d013_repeat_rows':1}}))
        # Return a well-formed harness record after proving the backend call.
        fake_harness.run_section_b2=lambda backend,*args,**kwargs: (
            backend({'row':1},(1,1),'slack') and {'counters':{'coordinate_rows':1,'d013_repeat_rows':1}})
        def armed_loader(path,name):
            if name=='wp7b_wp3': return fake_harness
            if name=='wp7b_wp1_matchers': return types.SimpleNamespace(
                validate_production_identity=lambda value:'valid',exact_match=lambda left,right:True)
            return original_load(path,name)
        def track_worker(command,*args,**kwargs):
            worker_commands.append(list(command))
            return original_subprocess_run(command,*args,**kwargs)
        launcher._load=armed_loader; launcher.Wp7bDeviceBackend=DeviceBackendSpy
        launcher.subprocess.run=track_worker
        try:
            armed_wp3_config={'compiled_core_library':str(core_path),
                'compiled_d013_library':str(d013_path),'verified_d013_release_token':{'approved':True},
                'coordinates':[{'coordinate':[1,2,3]}], 'd013_coordinates':[{'coordinate':[1,2,3]}],
                'accepted_identity':{},'production_identity':{},'accepted_identity_sha256':'a',
                'protocol_identity_sha256':'b','d013_fired':True}
            armed_wp3_steps,_,_=launcher.run_adapters(temp,instance,{}, {},armed_wp3_config,
                                                       fixture_only=False)
            wp3_record=armed_wp3_steps['section_b_item_2_full_domain_synthetic'](lambda *a:None)
            require(wp3_record['status']=='ok' and backend_events==[('construct',False),('device_call',None)]
                    and not worker_commands,
                    'armed WP3 did not stay on the device backend')
        finally:
            launcher._load=original_load; launcher.Wp7bDeviceBackend=original_backend
            launcher.subprocess.run=original_subprocess_run

        # The fixture-only host worker has a separate fail-closed boundary.
        worker_steps,_,_=launcher.run_adapters(temp,instance,{}, {},{
            'compiled_core_library':str(core_path),'compiled_d013_library':str(d013_path),
            'verified_d013_release_token':{'approved':True},'coordinates':[], 'd013_coordinates':[]},
            fixture_only=True)
        refusal_run=launcher.subprocess.run
        launcher.subprocess.run=lambda *args,**kwargs:subprocess.CompletedProcess(
            args[0],1,'','fixture worker refused')
        try:
            refuse(lambda:worker_steps['section_b_item_2_full_domain_synthetic'](lambda *a:None),
                   RuntimeError,'isolated host worker refusal','isolated host WP3 worker refused')
        finally:
            launcher.subprocess.run=refusal_run

        # A nonempty sealed batch list must match the writer's generated plan.
        mismatch_writer=types.SimpleNamespace(seal_range_plan=lambda *args,**kwargs:
            {'ranges':[{'batch_id':'sealed-id'}]})
        writer_load=launcher._load
        launcher._load=lambda path,name: (mismatch_writer if name=='wp7b_wp4' else
            types.SimpleNamespace(validate_production_identity=lambda value:'valid',
                                  exact_match=lambda left,right:True) if name=='wp7b_wp4_identity' else writer_load(path,name))
        try:
            mismatch_steps,_,_=launcher.run_adapters(temp,instance,{}, {},{
                'batch_ids':['different-id'],'production_identity':{},'accepted_identity':{},
                'writer_family':'fixture','writer_total_coordinates':1},fixture_only=True)
            refuse(lambda:mismatch_steps['wp4b_writer_synthetic_ranges'](),RuntimeError,
                   'WP4b sealed plan batch mismatch','generated batch list differs from the sealed plan')
        finally:
            launcher._load=writer_load

        writer_path=temp/'research/g9/stage2_production_writer.py'; writer_path.write_text('def write_range(*args, **kwargs): return {}\n')
        budget_clock_values=iter([0.0,0.0,0.0,launcher.BUDGET_SECONDS+1.0,launcher.BUDGET_SECONDS+1.0])
        budget_clock=lambda:next(budget_clock_values)
        budget_config={'production_identity':accepted_identity,'batch_ids':['one'],'writer_root':'out','records_by_batch':{'one':[]},'result_schema':{},'writer_session':{}}
        budget_steps,_,_=launcher.run_adapters(temp,instance,{}, {},budget_config,clock=budget_clock,fixture_only=True)
        refuse(lambda:budget_steps['wp4b_writer_synthetic_ranges'](),RuntimeError,'WP4 budget guard','incomplete_budget')

        direct=launcher.subprocess.run([sys.executable,'-B',str(Path(launcher.__file__))],
            cwd=ROOT,capture_output=True,text=True,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
        require(direct.returncode!=0 and 'adapter module is not directly runnable' in direct.stderr,
            'launcher direct-entrypoint refusal guard drifted')

    print('WP7B launcher sweep fixture: PASS')

if __name__=='__main__':
    run()

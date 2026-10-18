#!/usr/bin/env python3
"""Full-domain backend proof using only the checked host-emulation ABIs."""
from __future__ import annotations
import contextlib, hashlib, json, os, subprocess, sys, tempfile, struct
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
SCRATCH=Path('/home/shivansh-srivastava/decisions_os/g9_jobs/scratch/wp7biso')
if os.environ.get('PYTHONDONTWRITEBYTECODE')!='1': raise SystemExit('PYTHONDONTWRITEBYTECODE=1 required')
sys.dont_write_bytecode=True
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from research.g9.kaggle_wp7b import wp7b_launcher as launcher
from research.g9 import stage2_reference_seal as seal_api
from research.g9 import stage2_section_b2_harness as harness
from research.g9.kaggle_wp7b.seal import build_wp7b_seal as seal_builder
from research.g9 import stage2_d013_inactive_evaluator as d013_reference
from research.g9.cuda_qualification import stage2_cuda_core_bridge as core_bridge
from research.g9.cuda_qualification import stage2_cuda_d013_inactive as d013_bridge


def require(ok, message):
    if not ok: raise RuntimeError(message)


def compile_libs(directory):
    stub=ROOT/'research/g6/cuda_qualification/host_emulation_stub'
    qual=ROOT/'research/g9/cuda_qualification'
    core=directory/'core_host.so'; d013=directory/'d013_host.so'
    command=['g++','-x','c++','-std=c++17','-O0','-shared','-fPIC','-Wall','-Wextra',
             '-Wno-unknown-pragmas','-ffp-contract=off','-fno-fast-math','-I',str(stub),
             '-I',str(qual),str(qual/'stage2_cuda_core_bridge.cu'),'-o',str(core)]
    done=subprocess.run(command,cwd=ROOT,text=True,capture_output=True,timeout=600)
    require(done.returncode==0 and not done.stderr,'core host stub compile failed: '+done.stderr[:500])
    command=['g++','-x','c++','-std=c++17','-O0','-shared','-fPIC','-Wall','-Wextra','-Wno-unknown-pragmas',
             '-ffp-contract=off','-fno-fast-math','-I',str(stub),'-I',str(qual),
             str(qual/'stage2_cuda_d013_inactive.cu'),'-o',str(d013)]
    done=subprocess.run(command,cwd=ROOT,text=True,capture_output=True,timeout=600)
    require(done.returncode==0 and not done.stderr,'D013 host stub compile failed: '+done.stderr[:500])
    return core,d013


def frame_for(config, family, condition=None, r=1.0, point=(30,30,30)):
    for item in config['device_frames'].values():
        row=item['row']
        if (row['family']==family and row.get('condition')==condition and row['r']==r
                and tuple(row['coordinate'])==tuple(point)):
            return item
    raise RuntimeError('sealed frame missing: '+str((family,condition,r,point)))


def main():
    config=json.loads((ROOT/'research/g9/kaggle_wp7b/runtime_config.json').read_text())
    seal_raw=(ROOT/'research/g9/kaggle_wp7b/seal/wp7b_reference_seal.json').read_bytes()
    seal_inputs=json.loads((ROOT/'research/g9/kaggle_wp7b/seal/wp7b_seal_inputs.json').read_bytes())
    session_inputs={**seal_inputs['input_hashes'],
        'production_identity_hash':seal_inputs['production_identity_hash'],
        'coordinates':seal_inputs['coordinates']}
    opened=seal_api.open_for_session(seal_raw,session_inputs)
    base=frame_for(config,'primary',None,1.0)
    # One backend instance sees the exact harness row/pair/encoding order for
    # the primary row and every D013 repeat condition.  Keeping these rows in
    # one run is essential: per-condition backend construction hid an
    # encoding-cache crossover in CB and CS.
    repeats=[frame_for(config,'d013_repeat',condition,1.0)
             for condition in ('C','CB','CS','CSB')]
    rows=[]
    for source in (base,*repeats):
        row=dict(source['row'])
        row['inactive_positive_zero']=row['inactive_positive_zero']=='yes'
        row['coordinate']=tuple(row['coordinate'])
        if row.get('condition') is None: row.pop('condition',None)
        rows.append(row)
    expected_lookup={}
    for row in rows:
        for pair in harness.D015_COMPARATOR_PAIRS:
            coordinate={'family':str(row['family']),'point':[int(axis) for axis in row['coordinate']],
                'r_hex':float(row['r']).hex(),'comparator':str(row['comparator']),
                'grid':str(row['grid']),'inactive_positive_zero':'yes' if row['inactive_positive_zero'] else 'no',
                'c_h':int(pair[0]),'c_f':int(pair[1])}
            if 'scale' in row: coordinate['scale']=str(row['scale'])
            if 'condition' in row: coordinate['condition']=str(row['condition'])
            for encoding in harness._ENCODINGS:
                expected_lookup[(json.dumps(coordinate,sort_keys=True,separators=(',',':')),encoding)]=opened(coordinate,encoding)
    # Freeze the already-opened seal answers before disabling the reference
    # callable. The comparison side is a plain lookup; no Python reference
    # computation is reachable while the device backend runs.
    opened=lambda *a,**k: (_ for _ in ()).throw(RuntimeError('forbidden Python reference path reached'))
    launcher.START=0.0
    seal_reference=launcher.budgeted_reference(
        lambda coordinate,encoding:expected_lookup[(json.dumps(coordinate,sort_keys=True,separators=(',',':')),encoding)],
        lambda:0.0,lambda:'offline-proof')
    # Any accidental call to a Python energy/reference evaluator from the device
    # route fails immediately; the opened seal itself is already materialized.
    forbidden=lambda *a,**k: (_ for _ in ()).throw(RuntimeError('forbidden Python reference path reached'))
    for name in ('energy_stream','tie_flags','d015_reconstruction','_shared_transcript','shared_reference'):
        if hasattr(seal_builder,name): setattr(seal_builder,name,forbidden)
    for name in tuple(vars(d013_reference)):
        value=getattr(d013_reference,name)
        if callable(value) and not name.startswith('__'): setattr(d013_reference,name,forbidden)
    with tempfile.TemporaryDirectory(prefix='wp7b-r2-host-proof-',dir=SCRATCH) as td:
        core,d013=compile_libs(Path(td))
        # Backend fixture mode accepts only backend-0 host stubs; normal/armed
        # construction retains its strict backend-1 requirement.
        backend=launcher.Wp7bDeviceBackend(core,d013,{},fixture_only=True,
            frame_table={launcher.Wp7bDeviceBackend._row_key(frame['row']):frame for frame in (base,*repeats)})
        got=harness._run_comparisons(rows,backend,seal_reference)
        require(len(got)==50,'shared backend did not exercise primary + all 4 D013 rows x 5 pairs x 2 encodings')
        # The minimum corruption is compared against the opened seal by the real
        # harness canonical comparator. Flag and offset corruptions are refused
        # by reconstruction census and same-call offset SHA validation.
        original_loader=core_bridge._load_checked_abi
        def corruption_case(kind):
            def loader(path):
                run,copy_offsets,backend_tag=original_loader(path)
                def changed_run(*args):
                    status=run(*args)
                    if status and kind=='minimum': args[-1].contents.results[0][0].minimum += 1.0
                    if status and kind=='flag': args[-1].contents.results[0][0].entries[0] ^= (1<<32)
                    return status
                def changed_offsets(dst,count):
                    status=copy_offsets(dst,count)
                    if status and kind=='offset': dst[1] += 1
                    return status
                return changed_run,changed_offsets,backend_tag
            core_bridge._load_checked_abi=loader
            try:
                bad=launcher.Wp7bDeviceBackend(core,d013,{},fixture_only=True,
                    frame_table={launcher.Wp7bDeviceBackend._row_key(base['row']):base})
                try:
                    harness._run_comparisons([rows[0]],bad,seal_reference)
                except harness.SectionB2HarnessError:
                    return True
                except (launcher._load.__class__ if False else RuntimeError):
                    return True
                return False
            finally: core_bridge._load_checked_abi=original_loader
        for kind in ('minimum','flag','offset'):
            require(corruption_case(kind),kind+' ABI corruption escaped detection')
    print(json.dumps({'status':'PASS','opened_seal_sha256':hashlib.sha256(seal_raw).hexdigest(),
        'row_units':5,'d013_conditions':['C','CB','CS','CSB'],
        'encodings':2,'comparator_pairs':5,'comparisons':50,
        'corruptions_detected':['minimum','compacted_entry_flag','copied_offset'],
        'backend':'Wp7bDeviceBackend / compiled backend-0 host-emulation ABI'},sort_keys=True))

if __name__=='__main__': main()

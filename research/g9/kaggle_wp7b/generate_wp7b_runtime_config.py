#!/usr/bin/env python3
"""Generate the hash-bound WP7b runtime config from sealed artifacts and pins."""
from __future__ import annotations
import argparse, ast, hashlib, json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
SEAL=ROOT/'research/g9/kaggle_wp7b/seal'
PIN=ROOT/'research/g9/kaggle_wp7/wp7_environment_pin.json'
EXPECTED_APPROVAL_SHA256={
 'research/decisions/GATE_9_STAGE2_PROTOCOL_DRAFT.md':'8a5785fd6d495f548ebd94d61fac9aab9986413c2c1d2b0a7528500fd86635d0',
 'research/decisions/GATE_9_STAGE2_KAGGLE_CUDA_AMENDMENT_DRAFT.md':'589fdc29d71cd5f70c0734e927d109dc00b389b40cc7c485e56a655f41fd57cf',
 'research/decisions/GATE_9_SECTION_B_KAGGLE_PROVIDER_TRUST_AMENDMENT_DRAFT.md':'aa10e23d6ef4bde977147def57e6c3eb71e4e17dc81d8bc5f933297ad7adad0b',
}

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def canonical(value: object) -> bytes:
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')

def _frame_key(coordinate):
    row={'family':coordinate['family'],'condition':coordinate.get('condition'),
         'coordinate':coordinate['point'],'r':float.fromhex(coordinate['r_hex']),
         'grid':coordinate['grid'],'comparator':coordinate['comparator']}
    return json.dumps([row.get('family'),row.get('condition'),row.get('coordinate'),row.get('r'),
                       row.get('grid'),row.get('comparator')],sort_keys=True,separators=(',',':'))

def _device_frames(instance_doc, prepared, seal_inputs, coordinates):
    """Derive immutable CUDA frames from the sealed coordinate and G4 sources."""
    import sys
    if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
    from src.g4.instance import Instance
    from src.g4.energy import prepare_instance
    from src.g4 import constraints
    from src.g5.domains import BinaryDomain
    from research.g9.cuda_qualification import stage2_cuda_core_stream_engine as core
    from research.g9.cuda_qualification import stage2_cuda_input_frame as frame_api
    from research.g9.stage2_coordinate_records import families
    tickers=tuple(instance_doc['canonical_order'])
    sectors=tuple(tuple(i for i,t in enumerate(tickers) if instance_doc['sector_of_ticker'][t]==label)
                  for label in instance_doc['sector_labels'])
    instance=Instance(tickers,sectors,tuple(instance_doc['mu']),
        tuple(tuple(row) for row in instance_doc['Sigma']),tuple(instance_doc['p']),
        float(instance_doc['kappa']),int(instance_doc['K']),int(instance_doc['C']),float(instance_doc['B']))
    g4={'tickers':list(instance.tickers),'sectors':[list(v) for v in instance.sectors],
        'mu':list(instance.mu),'sigma':[list(v) for v in instance.sigma],
        'prices':list(instance.prices),'kappa_risk':instance.kappa_risk,
        'K':instance.K,'C':instance.C,'B':instance.B}
    payload={'mu':list(instance.mu),'sigma':[list(v) for v in instance.sigma],
        'prices':list(instance.prices),'kappa_risk':instance.kappa_risk,'k':float(instance.K),
        'c':float(instance.C),'b':instance.B,'lambda_ref':float(prepared['lambda_ref']),
        'sectors':[list(v) for v in instance.sectors]}
    host_domain=core.build_domain(payload)
    offsets_sha=__import__('hashlib').sha256(host_domain['offsets'].tobytes()).hexdigest()
    family_rows=families(bool(seal_inputs.get('d013_fired')))
    family_map={}
    for family in family_rows:
        key=(family.group,family.condition,float(family.r).hex(),family.companion)
        family_map[key]=family
    frames={}; feasible_counts={}
    seen=set()
    coordinate_rows=coordinates['base_rows']+coordinates['d013_repeat_rows']
    for coord in coordinate_rows:
        marker=_frame_key(coord)
        if marker in seen: continue
        seen.add(marker)
        cond=coord.get('condition')
        if coord['family']=='primary': family=family_map[('primary',None,coord['r_hex'],'primary')]
        elif coord['family']=='d011': family=family_map[('d011',None,coord['r_hex'],'d011')]
        elif coord['family']=='v14': family=family_map[('v14',None,coord['r_hex'],'v14_'+coord['scale'])]
        elif coord['family']=='d013_repeat': family=family_map[('d013',cond,coord['r_hex'],'active')]
        else: raise ValueError('unknown sealed coordinate family')
        # The 2^20 WP7b seal binds this prepared active coefficient ledger to
        # every coordinate result; runtime frames must use that exact ledger.
        ledger=prepared['active_ledger']
        records={name:float(ledger[name]) for name in
            ('alpha','sector_slack','budget_slack','sector_linear','sector_quadratic',
             'budget_linear','budget_quadratic')}
        condition=cond or 'CSB'
        row={'family':coord['family'],'condition':cond,'coordinate':coord['point'],
             'r':float.fromhex(coord['r_hex']),'grid':coord['grid'],'comparator':coord['comparator'],
             'inactive_positive_zero':coord['inactive_positive_zero']}
        row_records=dict(records)
        if family.group=='d013':
            # Inactive values are exact positive zero in the D013 ABI's record.
            if condition not in ('CS','CSB'):
                for field in ('sector_slack','sector_linear','sector_quadratic'): row_records[field]=0.0
            if condition not in ('CB','CSB'):
                for field in ('budget_slack','budget_linear','budget_quadratic'): row_records[field]=0.0
        input_frame=(frame_api.build_input_frame(payload,[records],offsets_sha)
                     if family.group!='d013' or condition=='CSB' else None)
        if condition not in feasible_counts:
            feasible=0
            active_sector=condition in ('CS','CSB'); active_budget=condition in ('CB','CSB')
            for bits in BinaryDomain(20):
                if sum(bits)!=instance.K: continue
                if active_sector and any(value<0.0 for value in constraints.sector(instance,bits)): continue
                if active_budget and constraints.budget(instance,bits)<0.0: continue
                feasible+=1
            feasible_counts[condition]=feasible
        frame={'row':row,'payload':payload,'records':[row_records],'condition':condition,
            'input_frame':input_frame,'feasible_count':feasible_counts[condition],'instance':g4,
            'lambda_ref':float(prepared['lambda_ref']),
            'f_star':float(seal_inputs.get('d013_conditions',{}).get(condition,{}).get('f_star',prepared['f_star']))}
        frames[marker]=frame
    return frames

def _seal_constants():
    """Read the builder's identity mapping, which itself checks the pin hash."""
    import sys
    if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
    from research.g9.kaggle_wp7b.seal import build_wp7b_seal as builder
    from research.g9.kaggle_wp7b.wp7b_identity_binding import expected_observations, build_identity_mapping
    platform, image_build, provenance = build_identity_mapping(
        builder._IDENTITY_PIN, expected_observations(builder._IDENTITY_PIN))
    return {'ROLE_FILES':builder.ROLE_FILES,'PLATFORM':platform,'IMAGE_BUILD':image_build,
            'COMPILER_FLAGS':builder.COMPILER_FLAGS,'IDENTITY_FIELD_PROVENANCE':provenance}

def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    files={name:(SEAL/name).read_bytes() for name in ('wp7b_instance.json','wp7b_prepared_record.json','wp7b_reference_seal.json','wp7b_seal_inputs.json','wp7b_coordinates.json')}
    pin=PIN.read_bytes()
    seal_inputs=json.loads(files['wp7b_seal_inputs.json'])
    coordinates=json.loads(files['wp7b_coordinates.json'])
    accepted_identity=json.loads((SEAL/'wp7b_production_identity.json').read_bytes())
    pin_value=json.loads(pin)
    if seal_inputs.get('scientific_outputs') != 'intentionally absent' or coordinates.get('coordinate_count') != seal_inputs.get('coordinate_count'):
        raise SystemExit('seal artifact census mismatch')
    import sys
    if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
    from research.g9 import stage2_section_b2_harness as harness
    seal_constants=_seal_constants()
    from research.g9 import stage2_production_identity as production_identity
    from research.g9 import stage2_section_b1_recheck as wp2_module
    from research.g9 import stage2_production_writer as writer
    release=production_identity.load_v1_release(str(ROOT))
    role_paths={production_identity.V1_ENGINE_ROLE:sorted(release['source_sha256'])}
    role_paths.update({role:list(paths) for role,paths in seal_constants['ROLE_FILES'].items()})
    accepted_roles={role:sorted(entry['path'] for entry in entries)
                    for role,entries in accepted_identity['source_map']['roles'].items()}
    if {role:sorted(paths) for role,paths in role_paths.items()} != accepted_roles:
        raise SystemExit('seal role map differs from accepted production identity')
    if accepted_identity['content_sha256'] != seal_inputs['production_identity_hash']:
        raise SystemExit('accepted production identity hash differs from seal input')
    approval_hashes=wp2_module.read_approval_hashes()
    ground_truth_hash=json.loads(files['wp7b_prepared_record.json'])['provenance_record']['content_sha256']
    generator_record_hash=sha((ROOT/'research/g9/stage2_generation_release.py').read_bytes())
    writer_plan=writer.build_range_plan('wp7b_synthetic',coordinates['coordinate_count'],accepted_identity['content_sha256'])
    batch_ids=[row['batch_id'] for row in writer_plan['ranges']]
    records_by_batch={row['batch_id']:[
      {'coordinates':[index], 'result':{'identity_sha256':accepted_identity['content_sha256']}}
      for index in range(row['start'],row['stop'])] for row in writer_plan['ranges']}
    image_build=dict(seal_constants['IMAGE_BUILD'])
    accepted_build=accepted_identity['image_build_evidence']['fields']
    if image_build != accepted_build:
        raise SystemExit('seal IMAGE_BUILD differs from accepted production identity')
    accepted_platform=accepted_identity['qualification_identity']['platform']
    if seal_constants['PLATFORM']['kaggle_image'] != accepted_platform['kaggle_image']:
        raise SystemExit('seal PLATFORM kaggle_image differs from accepted production identity')
    # Probe names are only selectors. The shared mapping in wp7b_identity_binding
    # takes all thirteen runtime observations and constructs SESSION identity.
    platform_identity={
      'gpu_name':{'probe':'gpu_name'},
      'compute_capability':{'probe':'compute_capability'},
      'cuda_driver_version':{'probe':'cuda_driver_version'},
      'cuda_runtime_version':{'probe':'cuda_runtime_version'},
      'nvcc_version':{'probe':'nvcc_version_release'},
      'python_version':{'probe':'python_version'},
      'numpy_version':{'probe':'numpy_version'},
      'kaggle_image':{'fixed_by_seal':seal_constants['PLATFORM']['kaggle_image']},
    }
    base_rows=list(harness.build_validation_coordinates())
    repeat_rows=list(harness.d013_repeat_coordinates()) if seal_inputs.get('d013_fired') else []
    body={
      'schema':'decisions_os/wp7b_runtime_config/v1',
      'instance_path':'research/g9/kaggle_wp7b/instance.json',
      'prepared_record_path':'research/g9/kaggle_wp7b/prepared_record.json',
      'seal_path':'research/g9/kaggle_wp7b/seal.json',
      'seal_inputs_path':'research/g9/kaggle_wp7b/seal_inputs.json',
      'coordinates_path':'research/g9/kaggle_wp7b/coordinates.json',
      'coordinate_count':coordinates['coordinate_count'],
      'coordinates':base_rows,
      'd013_coordinates':repeat_rows,
      'd013_fired':bool(seal_inputs.get('d013_fired')),
      'corruption_release_sha256':'585da5d87908738e34c9b9858a0ef6d1c5e5cf4311dd1f6e3ba00a9d0ce6bfb9',
      'd013_corruption_release_sha256':'e73a4ff4a38cb6b0cfbc35713b7ce727c6cb8b94b2c38310277a1dac372b0721',
      'role_paths':role_paths,
      'platform_identity':platform_identity,
      'image_build':image_build,
      'compiler_flags':list(seal_constants['COMPILER_FLAGS']),
      'accepted_identity':accepted_identity,
      'accepted_identity_sha256':accepted_identity['content_sha256'],
      'observed_approval_sha256':approval_hashes,
      'expected_approval_sha256':EXPECTED_APPROVAL_SHA256,
      'generator_implementation_record_sha256':generator_record_hash,
      'expected_generator_implementation_record_sha256':generator_record_hash,
      'ground_truth_provenance_sha256':ground_truth_hash,
      'expected_ground_truth_provenance_sha256':ground_truth_hash,
      'protocol_identity_sha256':seal_inputs['input_hashes']['protocol_digest'],
      'batch_ids':batch_ids,
      'records_by_batch':records_by_batch,
      'result_schema':{'identity_sha256':'str'},
      'writer_family':'wp7b_synthetic',
      'writer_total_coordinates':coordinates['coordinate_count'],
      'writer_root':'wp7b-output',
      'identity_field_provenance':{
        'role_paths':'build_wp7b_seal.ROLE_FILES + the accepted v1 release source map; fixed by seal',
        'platform_identity.gpu_name/compute_capability/cuda_driver_version/cuda_runtime_version/nvcc_version/python_version/numpy_version':'observed at runtime by build_probes; never taken from config values',
        'platform_identity.kaggle_image':'build_wp7b_seal.PLATFORM; post-run-only field fixed by the seal and cross-checked against accepted identity',
        **seal_constants['IDENTITY_FIELD_PROVENANCE'],
        'compiler_flags':'build_wp7b_seal.COMPILER_FLAGS; fixed by seal',
        'accepted_identity':'wp7b_production_identity.json; fixed and hash-bound by seal',
        'WP2 observed approval hashes':'approved-path documents read at runtime',
        'WP2 expected approval hashes':'fixed sha256 constants for the three approved governing documents',
      },
      'image_pin_sha256':sha(pin),
      'artifact_sha256':{name:sha(data) for name,data in sorted(files.items())},
      'pin_fields':sorted(pin_value),
      'device_frames':_device_frames(json.loads(files['wp7b_instance.json']),
          json.loads(files['wp7b_prepared_record.json']),seal_inputs,coordinates),
      'scientific_outputs':'intentionally absent'
    }
    body['content_sha256']=hashlib.sha256(canonical(body)).hexdigest()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_bytes(json.dumps(body,sort_keys=True,indent=2).encode('ascii')+b'\n')
    print(json.dumps({'output':str(args.output),'sha256':sha(args.output.read_bytes()),'content_sha256':body['content_sha256']},sort_keys=True))
    return 0
if __name__=='__main__': raise SystemExit(main())

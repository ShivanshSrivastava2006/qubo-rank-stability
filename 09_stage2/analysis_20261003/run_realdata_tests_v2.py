"""Format-only regression tests using unchanged real production artifacts."""
import argparse
import copy
import gzip
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import real_layout_v2 as layout
import stage2_schema_v2 as schema
import verify_outputs_v2 as verifier


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    args = parser.parse_args()
    jobs = Path(__file__).resolve().parents[2]
    scratch = jobs / 'scratch/analysisfix'
    scratch.mkdir(parents=True, exist_ok=True)
    work = Path(subprocess.check_output(
        ['mktemp', '-d', str(scratch / 'format_tests.XXXXXX')], text=True).strip())
    source = args.source.resolve()
    census = schema.load_census_profile(Path(__file__).with_name('FROZEN_CENSUS_v2.json'))
    slot = schema.find_slot_dir(source, 1)
    family = schema.BASELINE_FAMILIES[0]
    base = layout.family_root(slot, family)
    plan = schema.read_sealed(base / schema.PLAN_NAME, 'source range plan')
    assert len(plan['ranges']) == 56
    passed = 0

    def check(ok):
        nonlocal passed
        assert ok
        passed += 1

    def refused(fn):
        try:
            fn()
        except schema.Stage2AnalysisError:
            check(True)
            return
        raise AssertionError('invalid format was admitted')

    with gzip.open(next((base / 'full_records').glob('*.jsonl.gz')), 'rt') as stream:
        record = json.loads(next(stream))
    schema.check_record(record, family, 'real first record')
    check(True)
    bad = copy.deepcopy(record)
    bad['family'] = 'unknown_family'
    refused(lambda: schema.check_record(bad, 'unknown_family', 'unknown family'))
    bad = copy.deepcopy(record)
    bad['r_hex'] = 0.5
    refused(lambda: schema.check_record(bad, family, 'float record'))
    prepared = schema.read_prepared_metadata(slot / 'instance/PREPARED.json', 'production metadata')
    check(prepared['instance']['instance_id'] == 'stage2_01')
    bad = copy.deepcopy(prepared)
    bad['status'] = 'tampered'
    path = work / 'tampered_prepared.json'
    path.write_text(json.dumps(bad))
    refused(lambda: schema.read_prepared_metadata(path, 'tampered metadata'))

    # Assemble three source pieces into the exact merged slot layout. All bytes
    # are real; this fixture invents no records, manifests, or completion receipts.
    for modern in (False, True):
        root = work / ('modern' if modern else 'legacy') / 'piece_merge_slot1'
        staged = root / 'staged_qualified_sources'
        dest_slot = staged / schema.INSTANCE_ROOT / 'stage2_01'
        shutil.copytree(slot / 'instance', dest_slot / 'instance')
        dest = (staged / 'scratch/v4_sweep/stage2_01' / family if modern
                else dest_slot / 'sweep' / family)
        dest.mkdir(parents=True)
        shutil.copyfile(base / schema.PLAN_NAME, dest / schema.PLAN_NAME)
        for piece in range(3):
            piece_dir = work / ('modern_sources' if modern else 'legacy_sources') / f'p{piece + 1}'
            for row in plan['ranges'][piece::3]:
                batch = row['batch_id']
                for rel in (Path('ranges') / batch / 'records.json',
                            Path('ranges') / batch / 'RANGE_MANIFEST.json',
                            Path('full_records') / (batch + '.jsonl.gz')):
                    source_copy = piece_dir / rel
                    source_copy.parent.mkdir(parents=True, exist_ok=True)
                    os.link(base / rel, source_copy)
                    target = dest / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    os.link(source_copy, target)
        check(layout.family_root(dest_slot, family) == dest)
        for prefix in (f'scratch/v4_sweep/stage2_01/{family}/',
                       f'{schema.INSTANCE_ROOT}/stage2_01/sweep/{family}/'):
            check(layout.merged_evidence_path(dest_slot, prefix + schema.PLAN_NAME)
                  == dest / schema.PLAN_NAME)
        problems = layout.inventory(root, census)
        check(len(problems) == 9)
        check(sum('missing family' in x for x in problems) == 5)
        check(sum('missing slot' in x for x in problems) == 4)
        report = verifier.build_report(root, census)
        check(not report['all_slots_verified'] and report['failure_count'] > 0)
        # Removing a scratch link leaves the real source bytes untouched.
        missing = dest / 'full_records' / (plan['ranges'][0]['batch_id'] + '.jsonl.gz')
        missing.unlink()
        problems = layout.inventory(root, census)
        check(f'incomplete: missing {missing}' in problems)
        other = (dest_slot / 'sweep' / family if modern else
                 staged / 'scratch/v4_sweep/stage2_01' / family)
        other.mkdir(parents=True)
        refused(lambda: layout.family_root(dest_slot, family))

    result = {'passed': passed, 'failed': 0, 'work': str(work),
              'scope': 'format only; three piece sources per layout; no inference'}
    (work / 'format_test_results.json').write_text(json.dumps(result))
    print(json.dumps(result))
    return 0


if __name__ == '__main__':
    sys.exit(main())

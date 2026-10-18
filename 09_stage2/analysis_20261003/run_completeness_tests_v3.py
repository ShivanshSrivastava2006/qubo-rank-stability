"""Count-only mock pipeline, real FORMAT and accepted Stage-1 equality tests."""
import argparse
import contextlib
import gzip
import io
import json
from pathlib import Path
import sys
import completeness_core_v3 as core
import stage2_schema_v2 as schema
from export_certificates_v3 import export, scratch_only

HERE = Path(__file__).resolve().parent
JOBS = HERE.parents[1]
PROJECT = JOBS.parent / 'project'

def unit():
    b = core.new_bucket()
    for counts in [dict(A=1, B=1, C=0), dict(A=0, B=0, C=3)]:
        core.add_summary(b, dict(atomic_counts=counts, X_E_size=sum(counts.values()),
                                 set_label='C' if counts['C'] else 'B'))
    assert core.render_series(b, 'fixture', 'r', 'e')['mean_p'] == {
        'A': dict(numerator=1, denominator=4), 'B': dict(numerator=1, denominator=4),
        'C': dict(numerator=1, denominator=2)}
    failures = 0
    for summary in [dict(atomic_counts=dict(A=0, B=0, C=0), X_E_size=0, set_label='A'),
                    dict(atomic_counts=dict(A=1, B=0, C=1), X_E_size=2, set_label='A'),
                    dict(atomic_counts=dict(A=1, B=0, C=0), X_E_size=2, set_label='A')]:
        try:
            core.add_summary(core.new_bucket(), summary)
        except ValueError:
            failures += 1
    assert failures == 3
    print('unit_positive=1 unit_negative=3')

def mock_pipeline(work):
    import make_mock_outputs_v3 as mock
    import analyze_stage2_v3 as analyzer
    import render_paper_slots_v2 as renderer
    from verify_outputs_v2 import build_report
    sys.path.insert(0, str(HERE.parent / 'paper_insert_20261004'))
    import render_insertion_cells as cells
    import insert_results as insertion
    profile = schema.build_census_profile(16, schema.FAMILY_CENSUS,
                                          'MOCK_SYNTHETIC_NOT_A_RESULT', scale=2000)
    census_path = work / 'MOCK_CENSUS_v3.json'
    census_path.write_bytes(schema.canonical_bytes(profile))
    root, out = work / 'mock', work / 'analysis/output'
    out.mkdir(parents=True)
    mock.build(root, [1, 2, 3, 4, 5], profile['records_per_range'], profile['scale'])
    report = build_report(root, profile)
    assert report['failure_count'] == 0
    with contextlib.redirect_stdout(io.StringIO()):
        assert analyzer.main(['--results-root', str(root), '--out', str(work / 'cli_output'),
                              '--census', str(census_path)]) == 0
    assert len(schema.read_sealed(work / 'cli_output/STAGE2_INFERENCE.json',
                                  'CLI regression')['slots']) == 5
    payload = analyzer.build_inference(root, profile)
    payload['content_sha256'] = schema.content_sha256(payload)
    inference = out / 'STAGE2_INFERENCE.json'
    inference.write_bytes(schema.canonical_bytes(payload) + b'\n')
    series_count = 0
    mixed = 0
    for slot in payload['slots']:
        for family in slot['families'].values():
            for series in family['series']:
                assert set(series) == core.SERIES_KEYS
                series_count += 1
                from fractions import Fraction
                assert sum(Fraction(v['numerator'], v['denominator'])
                           for v in series['mean_p'].values()) == 1
            for row in family['reported_cells']:
                for cell in row['encodings'].values():
                    assert cell['mean_p'] == cell['series']['mean_p']
                    mixed += int(cell['mean_p']['A']['numerator'] > 0 and cell['mean_p']['C']['numerator'] > 0)
    assert mixed > 0
    export(root, root, out / 'certificates', mock=True)
    with contextlib.redirect_stdout(io.StringIO()):
        renderer.render(inference, out)
        cells.build(out)
    manifest = json.loads((out / 'INSERTION_CELLS.json').read_text())
    assert manifest['certificate_values_available'] is True
    assert manifest['tie_fractions_available'] is True
    # Exercise the unchanged insertion engine in a minimal labelled MOCK fixture.
    # Its default scratch/paperinsert location conflicts with this task's scratch
    # rule; override only its in-memory test root, never its source file.
    insertion.SCRATCH = work.resolve()
    paper = work / 'mock_paper_fixture'
    sections = paper / 'manuscript/sections'
    sections.mkdir(parents=True)
    target = sections / 'results.tex'
    target.write_text('\n'.join('\\stagetwopending[' + label + ']{}' for label in insertion.MAPPING))
    with contextlib.redirect_stdout(io.StringIO()):
        insertion.insert(out, paper, 'mock')
    inserted = json.loads((paper / 'INSERTION_MANIFEST.json').read_text())
    assert len(inserted['insertions']) == 29 and '\\stagetwopending' not in target.read_text()
    # A mismatched pre-production optimum must not become a certificate.
    negative = work / 'bad_reference'
    for source in root.glob('slot*/actual_reference'):
        target_ref = negative / source.parent.name / 'actual_reference'
        target_ref.mkdir(parents=True)
        for q in source.glob('*.json'):
            data = json.loads(q.read_text())
            if q.name == 'device_frames.json':
                data['mock']['f_star'] = -3
            (target_ref / q.name).write_text(json.dumps(data))
    try:
        export(root, negative, work / 'bad_certificates', mock=True)
    except ValueError as exc:
        assert str(exc) == 'pre-production frame/certificate drift'
    else:
        raise AssertionError('mismatched optimum accepted')
    assert not list((work / 'bad_certificates').glob('*.tex'))
    print(f'mock_slots=5 verified_failures=0 series={series_count} inserted_cells=29 certificate_negative=1')

def real_format():
    legacy = JOBS / 'scratch/v4j_p1_out_shivanshsrivastava06'
    files = sorted(legacy.glob('**/primary__primary__r0x1_0000000000000p-1/full_records/*.gz'))
    pieces = sorted((JOBS / 'push/collected_v4k').glob('s*p*/**/full_records/*.gz'))
    assert files and pieces
    for tag, paths in [('legacy_slot1_primary_half', files), ('collected_piece', [pieces[0]])]:
        buckets = {}
        rows = 0
        for p in paths:
            with gzip.open(p, 'rt') as stream:
                for line in stream:
                    record = json.loads(line)
                    schema.check_record(record, record['family'], 'FORMAT record')
                    for encoding, summary in record['reconstruction'][schema.PRIMARY_SUMMARY_KEY].items():
                        core.add_summary(buckets.setdefault((record['r_hex'], encoding), core.new_bucket()), summary)
                    rows += 1
        for (r, e), bucket in buckets.items():
            assert set(core.render_series(bucket, tag, r, e)) == core.SERIES_KEYS
        print(f'FORMAT {tag} files={len(paths)} records={rows} series={len(buckets)} keys=9')

def stage1():
    sys.path.insert(0, str(PROJECT))
    from src.g6.ratified_g5_input import iter_ratified_records
    accepted = json.loads((PROJECT / 'research/g7/stage1_inference/STAGE1_INFERENCE.json').read_text())
    expected = {(s['r_hex'], s['encoding']): s for s in accepted['primary_reported_rates']}
    buckets = {}
    rows = 0
    for record in iter_ratified_records():
        r = record['key']['r_hex']
        for e in ('slack', 'unbalanced'):
            cert = record[e]
            assert cert['tie_comparator']['c_H'] == 2048
            xs = cert['X_E']
            assert cert['X_E_size'] == len(xs)
            counts = {x: sum(item['atomic_label'] == x for item in xs) for x in 'ABC'}
            core.add_summary(buckets.setdefault((r, e), core.new_bucket()),
                             dict(atomic_counts=counts, X_E_size=len(xs), set_label=cert['set_label']))
        rows += 1
    assert set(buckets) == set(expected)
    for key, bucket in buckets.items():
        s = expected[key]
        actual = core.render_series(bucket, s['source'], *key)
        assert actual == s, 'accepted Stage-1 SERIES_KEYS drift'
        assert schema.canonical_bytes(actual['mean_p']) == schema.canonical_bytes(s['mean_p'])
    print(f'Stage1_records={rows} series_bit_exact={len(buckets)} mean_p_fractions_bit_exact={len(buckets)*3}')

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--work', required=True, type=Path)
    p.add_argument('--suite', choices=['mock', 'real', 'stage1', 'all'], default='all')
    a = p.parse_args()
    scratch_only(a.work)
    unit()
    if a.suite in ('mock', 'all'):
        mock_pipeline(a.work)
    if a.suite in ('real', 'all'):
        real_format()
        export(JOBS / 'push/collected_v4k', JOBS / 'push',
               a.work / 'real/analysis/output/certificates')
        print('FORMAT certificate_fragments=5 source_bindings_verified=5')
    if a.suite in ('stage1', 'all'):
        stage1()

if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('FIRST_ERROR ' + type(exc).__name__ + ': ' + (str(exc).splitlines() or ['unspecified assertion'])[0][:400], file=sys.stderr)
        raise SystemExit(1)

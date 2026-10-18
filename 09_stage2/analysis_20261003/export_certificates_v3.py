"""Machine-only pre-production certificate cells; real runs are FORMAT tests.

Spec: FROZEN_MATH_SPEC.md:114-129 (F and optimum set/value), :148-150
(Lambda_ref normalization). No sweep-derived facts enter these cells.
"""
import argparse
import hashlib
import json
from pathlib import Path
import stage2_schema_v2 as schema

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def scratch_only(out):
    base = Path(__file__).resolve().parents[2] / 'scratch/analysiscomplete'
    if not out.resolve().is_relative_to(base.resolve()):
        raise ValueError('real FORMAT output must be under scratch/analysiscomplete')

def export(staged_root, reference_root, out, mock=False):
    if not mock:
        scratch_only(out)
    refs = {}
    for meta in reference_root.rglob('REFERENCE_METADATA.json'):
        if not mock and not (meta.parent.parent / 'REAL_REFERENCE_RESULT.json').is_file():
            continue
        d = json.loads(meta.read_text())
        if d['instance_id'] in refs:
            raise ValueError('duplicate reference instance')
        refs[d['instance_id']] = (meta, d)
    if set(refs) != {f'stage2_0{i}' for i in range(1, 6)}:
        raise ValueError('reference coverage must contain five instances')
    out.mkdir(parents=True, exist_ok=True)
    for name, (meta, md) in sorted(refs.items()):
        matches = []
        for p in staged_root.rglob('PREPARED.json'):
            if p.parent.parent.name != name:
                continue
            d = schema.read_prepared_metadata(p, 'prepared certificate')
            if d['content_sha256'] == md['prepared_record_sha256']:
                matches.append((p, d))
        if not matches:
            raise ValueError('no digest-bound prepared record')
        p, prepared = sorted(matches, key=lambda item: str(item[0]))[0]
        if any(d != prepared for _, d in matches):
            raise ValueError('prepared duplicates disagree')
        if not mock and (prepared['instance']['instance_id'] != name or
                         prepared['production'] is not True):
            raise ValueError('certificate requires production prepared identity')
        frames_path = meta.parent / 'device_frames.json'
        frames = list(json.loads(frames_path.read_text()).values())
        sources = [p, meta, frames_path]
        if not mock:
            receipt = meta.parent.parent / 'REAL_REFERENCE_RESULT.json'
            rd = json.loads(receipt.read_text())
            if (rd['instance_id'] != name or rd['prepared_record_content_sha256'] != prepared['content_sha256'] or
                any(rd['files_sha256'][q.name] != sha(q) for q in [meta, frames_path])):
                raise ValueError('reference receipt binding drift')
            sources.append(receipt)
        r = prepared['results']
        if not frames or any(type(f['feasible_count']) is not int or f['feasible_count'] <= 0 or
                             f['feasible_count'] != frames[0]['feasible_count'] or
                             float(f['f_star']).hex() != float(r['f_star']).hex() or
                             float(f['lambda_ref']).hex() != float(r['Lambda_ref']).hex()
                             for f in frames):
            raise ValueError('pre-production frame/certificate drift')
        masks = [x['mask'] for x in r['X_star']]
        if not masks or len(set(masks)) != r['X_star_size'] or len(masks) != r['X_star_size']:
            raise ValueError('optimum set size drift')
        comments = ''.join(f'% source: {q.resolve()} sha256: {sha(q)}\n' for q in sources)
        # Hex serializations preserve the certified binary64 facts exactly.
        values = [('Original feasible-set size', str(frames[0]['feasible_count'])),
                  ('Optimum value (E, binary64 hex)', float(r['f_star']).hex()),
                  ('Optimum set size', str(r['X_star_size'])),
                  ('Optimum set (decoded masks)', ', '.join(hex(m) for m in masks)),
                  ('Normalization (E, binary64 hex)', float(r['Lambda_ref']).hex())]
        text = comments + ('% MOCK SYNTHETIC NOT A RESULT\n' if mock else '% REAL FORMAT TEST ONLY\n')
        text += '\\begin{tabular}{ll}\n'
        if mock:
            text += 'MOCK & SYNTHETIC NOT A RESULT\\\\\n'
        text += ''.join(label + ' & \\texttt{' + value + '}\\\\\n' for label, value in values)
        text += '\\end{tabular}\n'
        target = out / (name + '_certificate.tex')
        if target.exists():
            raise ValueError('refusing overwrite of certificate')
        target.write_text(text)
    return len(refs)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--staged-root', type=Path, required=True)
    parser.add_argument('--reference-root', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--mock', action='store_true')
    a = parser.parse_args()
    print('certificate_fragments=' + str(export(a.staged_root, a.reference_root, a.out, a.mock)))

if __name__ == '__main__':
    main()

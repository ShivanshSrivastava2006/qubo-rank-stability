"""Stage-2 A-region figure panels (owner approval 2026-10-15: PAPER_READER_DRAFT_OWNER_DECISIONS_20261015.md item 2).

Rendering only: each primary-comparator (2048, 2048) set_label is read from the
production records and drawn as one pixel block. Nothing is fitted, smoothed,
interpolated or recomputed.

Slice rule, fixed before any data were viewed: r = 1 primary family;
cardinality-axis indices ell_card in {0, 20, 40, 60} (every 20th); each panel is the full
ell_sector (vertical, increasing upward) by ell_budget (horizontal) plane.

Colours (Okabe-Ito): A for both encodings, A for slack only, A for unbalanced only, A for neither.

Before drawing anything, the script checks that full-lattice A/B/C counts per encoding
equal the sealed STAGE2_INFERENCE.json r=1 set_label_counts, and that each record's
coordinate equals the decoded linear index (last axis fastest). Any mismatch aborts.

Writes into this folder: data/stage2_0N_r1_labels.bin (one byte per point,
3*code(unbalanced) + code(slack), A=0 B=1 C=2), panels/*.png, VERIFY_AREGION.json.
Usage: python3 -B make_aregion_figures.py [--workers N]
"""
import gzip
import hashlib
import json
import struct
import sys
import zlib
from multiprocessing import Pool
from pathlib import Path

HERE = Path(__file__).resolve().parent
G9 = Path('/home/shivansh-srivastava/decisions_os/g9_jobs')
sys.path.insert(0, str(G9 / 'scratch/recert.Huef'))
import recert_common as rc  # noqa: E402  (record locations; read-only)

SEALED = G9 / 'scratch/analysiscomplete/real_inference.Aqlp/analysis/output/STAGE2_INFERENCE.json'
FAMILY = 'primary__primary__r0x1_0000000000000p_0'
R_HEX = '0x1.0000000000000p+0'
N = 61
CARD_SLICES = (0, 20, 40, 60)
SCALE = 6
CODE = {'A': 0, 'B': 1, 'C': 2}
COLOURS = {'both': (0, 158, 115), 'slack': (230, 159, 0), 'unbalanced': (0, 114, 178), 'neither': (238, 238, 238)}


def read_batch(args):
    path, batch = args
    out = bytearray()
    with gzip.open(path, 'rt', encoding='ascii') as handle:
        for position, line in enumerate(handle):
            rec = json.loads(line)
            linear = batch * rc.BATCH_ROWS + position
            c = rec['coordinate']
            if rec['linear_index'] != linear or rec['family'] != FAMILY:
                raise ValueError(f'layout mismatch {path}:{position}')
            if (c['ell_card'] * N + c['ell_sector']) * N + c['ell_budget'] != linear:
                raise ValueError(f'coordinate order mismatch {path}:{position}')
            p = rec['reconstruction']['primary_c_h_2048']
            u, s = p['unbalanced'], p['slack']
            if (u['c_H'], u['c_f'], s['c_H'], s['c_f']) != (2048, 2048, 2048, 2048):
                raise ValueError('primary comparator is not (2048, 2048)')
            out.append(CODE[u['set_label']] * 3 + CODE[s['set_label']])
    return batch, bytes(out)


def png(path, rows):
    h, w = len(rows), len(rows[0]) // 3
    raw = b''.join(b'\x00' + bytes(r) for r in rows)
    def chunk(t, d):
        return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    path.write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0))
                     + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b''))


def main():
    workers = int(sys.argv[sys.argv.index('--workers') + 1]) if '--workers' in sys.argv else 6
    sealed = json.loads(SEALED.read_text())
    (HERE / 'data').mkdir(exist_ok=True)
    (HERE / 'panels').mkdir(exist_ok=True)
    report = {'sealed_sha256': hashlib.sha256(SEALED.read_bytes()).hexdigest(), 'family': FAMILY,
              'card_slices': CARD_SLICES, 'instances': {}}
    with Pool(workers) as pool:
        for i, slot in enumerate(sealed['slots'], 1):
            inst = f'stage2_0{i}'
            base = rc.family_dir(inst, FAMILY)
            files = sorted(base.glob(f'{FAMILY}_b*.jsonl.gz'))
            tasks = [(str(f), int(f.name.removesuffix('.jsonl.gz').rsplit('_b', 1)[1])) for f in files]
            parts = dict(pool.map(read_batch, tasks))
            labels = b''.join(parts[b] for b in range(len(parts)))
            if len(labels) != N ** 3:
                raise SystemExit(f'{inst}: {len(labels)} labels')
            counts = {'slack': {'A': 0, 'B': 0, 'C': 0}, 'unbalanced': {'A': 0, 'B': 0, 'C': 0}}
            inv = {v: k for k, v in CODE.items()}
            for b in labels:
                counts['unbalanced'][inv[b // 3]] += 1
                counts['slack'][inv[b % 3]] += 1
            want = {s['encoding']: s['set_label_counts'] for s in slot['families'][FAMILY]['series']
                    if s['r_hex'] == R_HEX}
            match = counts == want
            slack_only = sum(1 for b in labels if b % 3 == 0 and b // 3 != 0)
            unb_only = sum(1 for b in labels if b // 3 == 0 and b % 3 != 0)
            sealed_bd = slot['families'][FAMILY]['spatial_A_predicates'][R_HEX]['both_directional_A_advantages']
            bd_match = (slack_only > 0 and unb_only > 0) == (sealed_bd == 'yes')
            (HERE / 'data' / f'{inst}_r1_labels.bin').write_bytes(labels)
            report['instances'][inst] = {'counts': counts, 'sealed_counts': want, 'counts_match': match,
                                         'slack_only_A': slack_only, 'unbalanced_only_A': unb_only,
                                         'both_directional_sealed': sealed_bd, 'both_directional_match': bd_match,
                                         'labels_sha256': hashlib.sha256(labels).hexdigest(),
                                         'record_dir': str(base)}
            print(inst, 'counts_match', match, 'both_directional_match', bd_match, flush=True)
            if not (match and bd_match):
                (HERE / 'VERIFY_AREGION.json').write_text(json.dumps(report, indent=1))
                raise SystemExit(f'{inst}: verification failed; no panels drawn')
    for i in range(1, 6):
        inst = f'stage2_0{i}'
        labels = (HERE / 'data' / f'{inst}_r1_labels.bin').read_bytes()
        for card in CARD_SLICES:
            rows = []
            for sector in reversed(range(N)):  # sector increases upward
                row = bytearray()
                for budget in range(N):
                    b = labels[(card * N + sector) * N + budget]
                    us, ss = b // 3 == 0, b % 3 == 0
                    key = 'both' if us and ss else 'slack' if ss else 'unbalanced' if us else 'neither'
                    row += bytes(COLOURS[key]) * SCALE
                rows.extend([row] * SCALE)
            png(HERE / 'panels' / f'{inst}_card{card:02d}.png', rows)
    report['panels'] = sorted(p.name for p in (HERE / 'panels').glob('*.png'))
    (HERE / 'VERIFY_AREGION.json').write_text(json.dumps(report, indent=1))
    print('panels', len(report['panels']))


if __name__ == '__main__':
    main()

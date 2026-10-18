"""Exact decoded fractions; no thresholds or winner rule.

Authority paths are relative to project/:
research/00_specifications/FROZEN_MATH_SPEC.md:85 (decoded deduplication),
:452-465 (atomic and set labels), :468-471 (decoded denominator and mean),
:473 (primary A-rate). Producer: research/g6/rate_surface_and_d013.py:105-131.
"""
from fractions import Fraction

SERIES_KEYS = frozenset(('source', 'r_hex', 'encoding', 'coordinate_count',
                        'set_label_counts', 'rho_E_exact', 'I_C_exist_count',
                        'I_C_univ_count', 'mean_p'))

def new_bucket():
    return dict(n=0, labels=dict.fromkeys('ABC', 0),
                p={x: Fraction(0) for x in 'ABC'}, exist=0, univ=0)

def add_summary(bucket, summary):
    # Spec :85,:468-470: Stage-2 reconstruction already deduplicated X_E;
    # atomic_counts counts decoded portfolios, never raw encoded multiplicity.
    counts, n = summary['atomic_counts'], summary['X_E_size']
    if (type(n) is not int or n <= 0 or set(counts) != set('ABC') or
        any(type(c) is not int or c < 0 for c in counts.values()) or
        sum(counts.values()) != n):
        raise ValueError('invalid decoded atomic census')
    # Spec :452-465: C existential, A universal, otherwise B.
    label = 'C' if counts['C'] else ('A' if counts['A'] == n else 'B')
    if summary['set_label'] != label:
        raise ValueError('decoded label/census drift')
    exist, univ = int(counts['C'] > 0), int(counts['C'] == n)
    for key, expected in [('I_C_exist', exist), ('I_C_univ', univ)]:
        if key in summary and summary[key] != expected:
            raise ValueError('decoded indicator drift')
    for x in 'ABC':
        if 'p_' + x in summary and summary['p_' + x] != [counts[x], n]:
            raise ValueError('decoded fraction drift')
        bucket['p'][x] += Fraction(counts[x], n)  # Spec :470.
    bucket['n'] += 1
    bucket['labels'][label] += 1
    bucket['exist'] += exist
    bucket['univ'] += univ

def rational(v):
    return dict(numerator=v.numerator, denominator=v.denominator)

def render_series(bucket, source, r_hex, encoding):
    n = bucket['n']
    if n <= 0:
        raise ValueError('empty coordinate population')
    result = dict(source=source, r_hex=r_hex, encoding=encoding,
                  coordinate_count=n, set_label_counts=dict(bucket['labels']),
                  # Gate-6 :129 preserves the unreduced A-count/population pair.
                  rho_E_exact=dict(numerator=bucket['labels']['A'], denominator=n),
                  I_C_exist_count=bucket['exist'], I_C_univ_count=bucket['univ'],
                  # Spec :470-471: arithmetic mean of coordinate fractions.
                  mean_p={x: rational(bucket['p'][x] / n) for x in 'ABC'})
    assert set(result) == SERIES_KEYS
    return result

# Gate-6 D011 Matched-Subgrid Authorization

Status: **OWNER APPROVED — BOUNDED MECHANICAL COMPARISON ONLY**

Date: 2026-09-20 (Asia/Kolkata)

## Owner authorization text

> I authorize one bounded D011 matched-subgrid comparison using only the
> accepted Gate-5 r=1 records restricted to the same declared 2,197 D011
> coordinates and the accepted D011 transition artifact. It may emit exact
> matched-grid counts and mechanically defined rho values/comparisons only. It
> may not infer, interpret, fit, start V-14, run D013, or use GPU output.

## Bound

The comparator consumes only the `c_H=2048`, `c_f=2048` primary condition for
the `unbalanced` and `slack` encodings.  It reports `rho_E^exact` solely as
the exact rational `A_count / 2197`, alongside its exact numerator difference
between D011 and the matching accepted Gate-5 subset.  It does not emit a
float approximation, any full-grid primary rate, a D015 diagnostic result, a
label lattice, an edge list, or an inference.

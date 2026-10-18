# Frozen Gate-1 Mathematical Specification

**Status:** **FROZEN — AUTHORITATIVE CONSOLIDATION UNDER W0b**  
**Gate:** G1 — mathematical specification only  
**Consolidated:** 2026-08-25  
**Authority:** This document consolidates the Scope Lock as amended by
`research/decisions/SCOPE_AMENDMENT_001.md`, and human-approved decisions D001,
D002, D004–D016 in `research/decisions/DECISIONS.md`. W0b additionally
authorizes the W2 operational determinization in §4.3 so the approved rules
have one reproducible binary64 transcription. That determinization is not text
from a scientific decision record, adds no scientific decision, and cannot
amend the frozen charter.

## 1. Authority, boundary, and notation

Authority resolves in this order: the Scope Lock as expressly amended by
`SCOPE_AMENDMENT_001.md` / D002; the later, scoped human decisions D004–D016;
the frozen Gate-1 charter; then this consolidation. A later item controls only
within its stated scope. Historical drafts and prototype outputs do not control
this specification.

This document authorizes neither canonical-data assembly (G2), numeric ADNYE
execution (G3), QUBO implementation (G4), certification (G5), experiments
(G6+), conclusions, nor Gate-1 exit. Numeric values produced by the approved
later deterministic rules are not present here.

`E` is the objective/return unit, realized by D007 as decimal simple **daily**
return. `R` is a residual/violation unit. `fl(q)` means one IEEE-754 binary64
round-to-nearest, ties-to-even operation. All interval endpoints and grid
coordinates mentioned below are prospective inputs until their approved
execution point.

## 2. Complete symbol, domain, unit, source, and status table

| Symbol | Domain / meaning | Unit | Source | Status |
|---|---|---:|---|---|
| `n` | number of original binary assets, `20` | 1 | Scope §12 | fixed |
| `x` | portfolio in `{0,1}^20` | 1 | Scope §12 | fixed |
| `K` | cardinality target, `6` | assets | Scope §12 | fixed |
| `mathcal S_j` | member-index set of sector `j`, `j=1..4` | set | Scope §12 | canonical instance input at G2 |
| `n_j(x)` | `sum_{i in mathcal S_j} x_i` | assets | Scope §12 | defined |
| `C` | sector cap, `2` | assets | Scope §12 | fixed |
| `p` | asset-price vector | currency | Scope §12, D005 | canonical instance input at G2 |
| `B` | budget, `1100` | currency | Scope §12 | fixed |
| `mu` | mean daily simple decimal-return vector | `E` | D007 | canonical data input at G2 |
| `Sigma` | daily simple decimal-return covariance matrix | `E^2` | D007 | canonical data input at G2 |
| `kappa_risk` | risk-aversion coefficient, exactly `1.0` | `E^-1` | D007 | fixed |
| `f(x)` | original objective | `E` | Scope §12, D007 | defined |
| `F` | original feasible-set predicate | set | Scope §12, D008 | defined |
| `X*`, `f*` | set of original minimizers / minimum value over `F` | set / `E` | D007, D015 | G3 output |
| `Lambda_ref` | range of `f` over `F` | `E` | D008, D014 | ADNYE-001; admitted, not executed |
| `Delta_full` | range of `f` over `{0,1}^20` | `E` | D010, D014 | ADNYE-001 field; admitted, not executed |
| `rho_box` | `Delta_full / Lambda_ref` | 1 | D010 | prospective deterministic input |
| `v_card` | smallest positive cardinality violation | `R` | D005 | exactly `1` from integrality |
| `v_sector` | smallest positive native sector violation, exactly `1` | `R` | D005, D009 | fixed by integer counts/pigeonhole |
| `v_budget` | smallest positive native budget violation | `R` | D005, D009 | evaluate on canonical instance at G2 |
| `v_j` | `v_sector` for sector family `j`, `v_budget` for budget | `R` | D005, D009 | defined abbreviation |
| `s_card,s_sector,s_budget` | nonnegative dimensionless grid coordinates | 1 | D001, D002, D010, D012 | prospective coordinates |
| `s_j` | `s_sector` for sector family `j`; `s_budget` for budget | 1 | D002, D006 | defined abbreviation |
| `ell` | zero-based primary-grid interval index | 1 | D012 | `0..P*D_dec` |
| `q_min` | integer `floor(log10(rho_box))-4` | 1 | D010 | derived after ADNYE resolution |
| `q_max` | integer `ceil(log10(rho_box))+1` | 1 | D010 | derived after ADNYE resolution |
| `N_axis` | `P*D_dec+1`, including endpoints | points | D012 | derived after ADNYE resolution |
| `alpha` | cardinality penalty coefficient | `E/R^2` | D002, D009 | defined across grid |
| `a_r(s)` | D006 unbalanced shape, `r>0` | 1 | D006 | defined across grid |
| `lambda_S,j` | slack inequality coefficient | `E/R^2` | D005, D006 | defined across grid |
| `lambda_1,j` | unbalanced linear coefficient | `E/R` | D004–D006 | defined across grid |
| `lambda_2,j` | unbalanced quadratic coefficient | `E/R^2` | D004–D006 | defined across grid |
| `h_card,h_sector,j,h_budget` | cardinality / sector / budget residuals | `R` | Scope §12 | defined |
| `q_j` | nonnegative binary-register value for inequality `j` | `R` | Scope §12, D005 | raw-QUBO state component |
| `y[d]` | binary bit `d` of a slack register | 1 | Scope §12, D015 | raw-QUBO state component |
| `z` | raw encoded state: `x` plus slack bits where applicable | 1 | Scope §12, D015 | defined |
| `E` | encoding label in `{slack,unbalanced}` | 1 | Scope §12, D015 | fixed vocabulary |
| `lambda` | tuple of coefficient inputs at one grid point | typed tuple | D006, D009 | defined from maps |
| `i,k` | original-asset indices in `1..20` | 1 | Scope §12 | fixed index domain |
| `j` | inequality-family index: sector `1..4` or budget | 1 | Scope §12 | fixed index domain |
| `d` | increasing slack-register bit index | 1 | Scope §12, D015 | fixed index domain |
| `w` | normalized violation magnitude `|h|/v_j` | 1 | D006 | defined |
| `gamma` | positive objective-rescaling scalar | 1 | D001, V-15 | analytic proof variable |
| `P` | primary log intervals per decade, exactly `10` | 1 | D012 | fixed |
| `D_dec` | whole-decade span of an axis | decades | D012 | derived after box resolution |
| `C_E` | certified raw candidate domain for encoding `E` | set | D015 | defined |
| `H_E(z;lambda)` | canonical unshifted encoded energy | `E` | D015 | defined |
| `T_E` | raw encoded-energy tie set | set | D015 | defined after G3/G4 inputs exist |
| `X_E` | decoded, deduplicated set `{decode(z):z in T_E}` | set | D016 | defined |
| `epsilon` | binary64 machine epsilon, `2^-52` | 1 | D015 | fixed |
| `c_H,c_f` | primary energy/objective tolerance multipliers, each `2048` | 1 | D015 | fixed |
| `tau_c` | scale-aware comparison tolerance | `E` | D015 | defined |
| `t0`–`t4`, `v2`, `v_card2` | named binary64 coefficient-transcript intermediates | varies | §4.3 / D006, D009 | defined, fail-closed |
| `sqrt_RN_even` | correctly rounded binary64 square-root primitive | typed operation | IEEE-754 / D015 path | fixed operation |
| `OPT_f(x)` | separate encoding-blind original-optimal predicate | Boolean | D015 | defined |
| `A_x,B_x,C_x` | atomic decoded labels | Boolean | D016 | defined |
| `rho_E^exact` | exact primary A-rate for encoding `E` | 1 | D010, D016 | prospective result metric |

No bare `rho` is valid in current specification text: `rho_box` and
`rho_E^exact` have different meanings (D011 clarification).

## 3. Original problem and exact objects

### 3.1 Objective and feasibility

For every `x in {0,1}^20`, minimize

```
f(x) = -mu^T x + kappa_risk * x^T Sigma x.                 [E]
```

`kappa_risk = (1.0, (decimal simple daily return)^-1, daily)` is one
indivisible D007 choice. The return series must use its native daily period:
no annualization or other horizon conversion is allowed absent a separately
approved aggregation model. Under a representation rescaling `R' = c R`,
ordering-equivalent risk aversion is `kappa_risk' = kappa_risk/c`.

Use the predicate-defined feasible set

```
F = {x in {0,1}^20 :
       sum_i x_i = K,
       n_j(x) <= C for j=1..4,
       p^T x <= B }.
```

The optimum is a set and a value, never presumed unique:

```
f* = min_{x in F} f(x),
X* = {x in F : f(x) = f*}.
```

The residual conventions are fixed:

```
h_card(x)     = sum_i x_i - K,
h_sector,j(x) = C - n_j(x),
h_budget(x)   = B - p^T x.
```

Thus cardinality is feasible exactly at `h_card=0`, while each inequality is
feasible exactly when its residual is nonnegative. These residual definitions
are shared by slack and unbalanced encodings; they share **no** penalty helper
(M4 declaration, enforced at G4 through V-18).

### 3.2 Deferred deterministic values and their limits

The only admitted prospective records are unexecuted D014 records:

```
Lambda_ref = max_{x in F} f(x) - min_{x in F} f(x),
Delta_full = max_{x in {0,1}^20} f(x) - min_{x in {0,1}^20} f(x).
```

`Lambda_ref = 0` is a G3 stop condition: no coefficient or box may be
substituted or patched. ADNYE-001 executes at `G3.compute_Lambda_ref` and
contains `Lambda_ref` and the single serialized `Delta_full`; ADNYE-002
executes at `G3.exit.resolve_box` after sidecar-verifying ADNYE-001. The D014
whitelist, closed schemas, exact UTF-8 digest preimages, decision snapshots,
rule strings, two digests, and conservative chronology rule are binding by
reference to D014 / `ADNYE_OUTPUT_CONTRACT_MEMO.md` revision 6. No record,
directory, validator, or output is created at G1.

All five D008 candidate normalizers are reported at G3 for transparency only:
the approved range over `F`; population standard deviations over `F` and the
cardinality-feasible population (with stated `ddof`); the cardinality-feasible
range; and the full-space range. They never permit re-selection of
`Lambda_ref` (R-U03-2).

## 4. Penalty coordinates, coefficient maps, and domain

### 4.1 Primary maps

D002 fixes the joint three-axis coordinate vector
`(s_card,s_sector,s_budget)`. The four sector inequalities share
`s_sector`. All coordinate values are dimensionless.

For cardinality, D002 / D009 fixes

```
alpha(s_card) = s_card * Lambda_ref / v_card^2,
P_card(x) = alpha(s_card) * h_card(x)^2.
```

This is an equality penalty; it has neither `r` nor an unbalanced coefficient
pair. D009 asserts no cardinality-enforcement threshold. V-17 obligation 1 is
unconditional; obligation 2 remains binding for any future threshold claim.

For each active inequality family `j` (sector and budget), D006 primary uses
`r=1`, `Lambda_pen,j=Lambda_ref`, and the numerical evaluation

```
a_r(s) = 2s / (sqrt(r^2 + 2s) + r).
```

The algebraically equivalent `-r + sqrt(r^2+2s)` names the mathematical
function but is prohibited as its small-positive-`s` numerical evaluation.
This rule also binds the non-primary D006 sensitivity values `r in {0.5,2}`.
At `r=1`, `a(s)=2s/(sqrt(1+2s)+1)` and

```
lambda_S,j = s_j * Lambda_ref / v_j^2,
lambda_1,j = Lambda_ref * a_r(s_j) / v_j,
lambda_2,j = Lambda_ref * a_r(s_j)^2 / (2v_j^2).
```

The two encoding-specific inequality penalties are

```
P_slack,j(h,q_j) = lambda_S,j * (h-q_j)^2,
zeta_j(h)      = -lambda_1,j*h + lambda_2,j*h^2.
```

For the primary `r=1`, the local gap at `h=-w v_j` is
`D(w)=a(s_j)w(1-w)`. It is negative for every `w>1`; this is a
hypothesis-aligned confound, not an A/B/C prediction. The old support counts
are pre-canonical expectations only.

D011 additionally requires a non-primary coarse curvature-match companion for
each inequality family:

```
lambda_S,j^CM = s_j*Lambda_ref/v_j^2,
lambda_1,j^CM = s_j*Lambda_ref/v_j,
lambda_2,j^CM = s_j*Lambda_ref/v_j^2,
```

equivalently `a=2`, `Lambda_pen,j=s_j*Lambda_ref/2`. Its known local gap is
`D_CM(w)=s_j w>0`; it is conditioning only. Its coarse-subgrid extent must be
predeclared before execution, not selected after any result. It is not a
primary mapping and does not alter D006 `r={0.5,2}` sensitivities.

### 4.2 Box and grid rules

D010 fixes a common cube on all three axes:

```
rho_box = Delta_full / Lambda_ref,
s_max = 10^(ceil(log10(rho_box)) + 1),
s_min = 10^(floor(log10(rho_box)) - 4),
[s_min,s_max]^3 on (s_card,s_sector,s_budget).
```

`m_hi=1` is derived; `m_lo=4` is a recorded judgement, not a theorem. The
box is conditioning for every later conclusion; it neither certifies
enforcement nor makes the A-rate box-independent. D012 fixes base-10 density
at `P=10` log **intervals** per decade, including endpoints. Over `D_dec` whole
decades, `N_axis=P*D_dec+1`. A refinement must be separately declared and
additionally reported, never substituted for the primary grid (R-U05-1).

V-14's precise 0.5x/2x expansion execution reading and D011's coarse extent
are pre-execution commitments required before the relevant core pass. They are
execution planning details, not mathematical choices left for a result.

### 4.3 Coordinate and coefficient binary64 pre-ledger path

**W2 operational determinization under W0b — not a decision-record rule.**
This section is the W0b-authorized representation convention required to make
the already approved D006/D009/D010/D012/D015 rules reproducible in binary64.
It does not choose a new scientific mapping, grid extent, grid density,
normalizer, data value, or outcome criterion. A change to this transcription
after results would require a dated human approval under the charter's frozen
change rule.

It fixes the primary path once the D014 sidecar-verified values and the typed
G2 input interface exist. It creates no coordinate or coefficient at G1. D010
makes `q_min=floor(log10(rho_box))-4` an integer and
`q_max=ceil(log10(rho_box))+1` an integer, so
`D_dec=q_max-q_min` is an integer number of decades. For each axis and each
`ell in {0,...,P*D_dec}`, its mathematical coordinate is

```
s(ell) = 10^(q_min + ell/P).
```

The primary binary64 coordinate is the correctly rounded, round-to-nearest
ties-to-even binary64 representation of that real value. The same ordered list
is used on every primary axis. `ell=0` and `ell=P*D_dec` are the D010 endpoints;
no endpoint is discarded or reconstructed from a neighbouring rounded point.
Thus the coordinate list is determined by the approved D010/D012 rules rather
than by a library's `logspace` defaults.

The D014 ADNYE-001 JSON decimal `Lambda_ref` is converted once by correctly
rounded RN-even binary64 conversion, exactly as D015 requires. Each resolved
native violation and every canonical `mu`, `Sigma`, `p`, sector-membership,
and scalar input is supplied by the typed G2 interface as a finite binary64
value with its unit and provenance; this specification forbids a hidden
recomputation or a compiler-selected conversion. Given those bit patterns, the
primary coefficient transcript is, for each active inequality family:

```
t0       = fl(2.0*s_j)
t1       = fl(r*r)
t2       = fl(t1+t0)
t3       = sqrt_RN_even(t2)
t4       = fl(t3+r)
a_r      = fl(t0/t4)
v2       = fl(v_j*v_j)
lambda_S = fl(fl(s_j*Lambda_ref)/v2)
lambda_1 = fl(fl(Lambda_ref*a_r)/v_j)
lambda_2 = fl(fl(Lambda_ref*fl(a_r*a_r))/fl(2.0*v2))
```

`sqrt_RN_even` is IEEE-754 correctly rounded square root in the active
rounding mode. Cardinality uses

```
v_card2 = fl(v_card*v_card)
alpha   = fl(fl(s_card*Lambda_ref)/v_card2).
```

The D011 curvature-match transcript substitutes its three approved formulas
with the same primitive multiplication/division convention. The `r` values
`0.5`, `1.0`, and `2.0` and integer/two literals above are exactly
representable. Any nonfinite intermediate or nonpositive active coefficient
fails closed. This coefficient transcript supplies the binary64 inputs to the
canonical D015 evaluator in §5; it does not change D006's mathematical maps or
make a G4 QUBO.

### 4.4 Rescaling proof and witness boundary

For every `gamma>0`, transform `f -> gamma*f`,
`Lambda_ref -> gamma*Lambda_ref`, and retain `s` and residual scales. Then
`alpha`, `lambda_S`, `lambda_1`, and `lambda_2` each scale by `gamma`, so
every energy term and `H_E` scales by `gamma`; exact minimizers and normalized
coordinates are preserved. This is M3a's analytic term-by-term proof. V-15's
finite cross-decades check is M3b only: a regression witness, never proof of
M3a. D010 normalizer changes are a different transformation and are not
claimed reparameterizable for unbalanced penalties.

## 5. Encoded energies, binary64 ledger, and comparisons

### 5.1 Encodings and raw-state domains

For active constraint families,

```
H_slack      = f + P_card + sum_j P_slack,j,
H_unbalanced = f + P_card + sum_j zeta_j.
```

All state-independent constants implied by those formulas belong to the
canonical unshifted ledger. A solver may drop constants while searching but
must restore this canonical energy before a tie comparison.

`C_unbalanced` contains all raw `x in {0,1}^20`. `C_slack` contains exactly
the slack lifts whose every auxiliary register is an exact minimizer for its
decoded `x`; a numerically near-minimal lift is excluded. The Scope-locked raw
layout has 39 variables: 20 original bits, two sector slack bits for each of
four sectors, and 11 budget slack bits. For D013 inactive inequalities, the
coefficient is exactly `+0.0` but the raw register stays; its multiplicity is
symbolic and never triggers a `2^39` enumeration.

### 5.2 Canonical primitive binary64 ledger

Every primitive below is finite binary64. Unary sign changes and bit-to-binary64
conversion are exact; each written `fl` is one rounded operation. There is no
FMA, contraction, reassociation, library dot product, `pow`, or compiler-chosen
QUBO expansion. Indices increase, accumulators begin at `+0.0`, and any
nonfinite input/intermediate, nonpositive `Lambda_ref`, nonpositive tolerance,
or invalid comparison fails closed.

```
for i=1..20: mu_term[i] = -fl(mu[i]*x[i])
for i=1..20:
  for k=1..20:
    sigma_xi[i,k] = fl(Sigma[i,k]*x[i])
    quad_term[i,k] = fl(kappa_risk*fl(sigma_xi[i,k]*x[k]))
f_acc=+0.0; for i=1..20: f_acc=fl(f_acc+mu_term[i])
for i=1..20: for k=1..20: f_acc=fl(f_acc+quad_term[i,k])
f=f_acc

card_sum=+0.0; for i=1..20: card_sum=fl(card_sum+x[i])
h_card=fl(card_sum-K)
for j=1..4:
  sector_sum[j]=+0.0
  for i in increasing members(mathcal S_j): sector_sum[j]=fl(sector_sum[j]+x[i])
  h_sector[j]=fl(C-sector_sum[j])
budget_sum=+0.0
for i=1..20: budget_sum=fl(budget_sum+fl(p[i]*x[i]))
h_budget=fl(B-budget_sum)

card_square=fl(h_card*h_card); P_card=fl(alpha*card_square)
slack: S_acc=+0.0; in increasing bit order d:
       S_acc=fl(S_acc+fl(2^d*y[d]))
       slack_delta=fl(h-S_acc); slack_square=fl(slack_delta*slack_delta)
       P_E_ineq=fl(lambda_S*slack_square)
unbalanced: linear_product=fl(lambda_1*h)
            quadratic_square=fl(h*h)
            quadratic_product=fl(lambda_2*quadratic_square)
            P_E_ineq=fl((-linear_product)+quadratic_product)
inactive inequality: P_E_ineq=+0.0 exactly

H_acc=f; H_acc=fl(H_acc+P_card)
for j=1..4: H_acc=fl(H_acc+P_E_sector[j])
H_E=fl(H_acc+P_E_budget)
```

The D015 canonical transcript for `f` is `mu_term[1..20]` then
`quad_term[1,1]..quad_term[20,20]`; for `H_E` it is that transcript then the
already rounded `P_card`, four sector penalties in ascending `j`, and budget
penalty. Grid-coordinate and coefficient **bit patterns** must be bound before
implementation; this document fixes evaluation once those inputs exist.

### 5.3 Tie and optimum comparators

Set `epsilon=2^-52`, `c_H=c_f=2048`. These are frozen judgements, not universal
forward-error bounds. For finite energy-valued `y,y'`, use exactly

```
gap   = abs(fl(y-y'))
m     = max(abs(y),abs(y'))
scale = fl(Lambda_ref+m)
tau   = fl((c*epsilon)*scale).
```

The primary encoded tie set is

```
H_E,min = min_{z in C_E} H_E(z;lambda),
T_E = {z in C_E : gap(H_E(z;lambda),H_E,min) <= tau_c_H(H_E(z;lambda),H_E,min)}.
X_E = {decode(z) : z in T_E}.
```

The separate original-objective service has immutable configuration comprising
the `f` ledger, `Lambda_ref`, `epsilon`, and `c_f`; its only runtime inputs are
decoded `x`, `f*`, and the independent feasibility predicate. It receives no
energy and no encoding identity. It defines

```
OPT_f(x) iff x in F and gap(f(x),f*) <= tau_c_f(f(x),f*).
```

`T_E` never decides `OPT_f`, and `OPT_f` never decides encoded energy.
`Lambda_ref` must be parsed by correct RN-even binary64 conversion from the
sidecar-verified D014 ADNYE-001 value. Each dependent result retains the
ADNYE-001 digest and separate D015/D016 approved-decision hashes under V-13/M10.

The one-factor non-primary diagnostic pairs are exactly
`(1024,2048)`, `(4096,2048)`, `(2048,1024)`, and `(2048,4096)` for
`(c_H,c_f)`; they are additionally reported and cannot select a primary result.

For a baseline borderline candidate with `gap in [fl(0.5*tau),fl(2*tau)]`, the
oracle exactly rationally sums its ordered D015 transcript and the stored
baseline reference transcript, then compares its difference with the stored
baseline binary64 `tau`. It neither searches a new minimum nor recomputes a
tolerance, and it cannot replace the classifier. A replay departure from this
ledger is an implementation defect; a conforming-ledger/oracle disagreement is
a numerical-rule conflict that stops acceptance pending dated human resolution.
Neither branch permits multiplier or rule selection after results (R-U14-1).

## 6. Decoded classification, reporting, and ablation

For each distinct decoded portfolio `x in X_E`, assign exactly one label:

```
A_x = OPT_f(x)
B_x = feasible(x) and not A_x
C_x = not feasible(x).
```

For every nonempty finite `X_E`, the primary label is

```
if exists x in X_E with C_x: C
else if all x in X_E have A_x: A
else: B.
```

The cases are mutually exclusive and exhaustive and preserve the Scope's
universal-A rule. Report raw `|T_E|` separately (symbolically where allowed),
decoded `|X_E|`, atomic-label census, `I_C^exist`, `I_C^univ`, per-grid
`p_A,p_B,p_C` with denominator `|X_E|`, and arithmetic-mean aggregate
fractions. Fractional values never supply partial credit to the primary A-rate.

`rho_E^exact` is the exact finite-grid primary A-rate. D013 fires only after
the CSB core pass iff the three D006 differences
`Delta_i(r)=rho_slack,i,r^exact-rho_unbalanced,i,r^exact` for
`r in {0.5,1,2}` include zero or fail to share one strict sign. If fired, run
exactly `C`, `CB`, `CS`, and `CSB`, with inactive penalties zero and omitted
from the active-axis grid. D015 diagnostics, D011 companion, D006 sensitivities
and the predeclared V-14 package are report-only companions; the trigger uses
primary classification only. R-U12-1 and R-U17-1 prohibit post-result semantic,
coordinate, denominator, or reporting re-selection.

## 7. Requirement and validation map

| Requirement | Frozen declaration / check boundary | Validation |
|---|---|---|
| M1 | §2 table gives domain, unit, source, status; all formulas cite decisions | W3 bounded check |
| M2 | §3–§5 state the additive terms and their unit algebra | analytic reading; W3 checks declared unit-row presence only |
| M3a | §4.4 analytic all-`gamma>0` homogeneity proof | V-15 proof review |
| M3b | finite cross-decades regression is witness only | V-15 |
| M4 | common residuals, separate penalty modules, no shared helper | declaration at G1; V-18/G4 enforces |
| M5 | decoded-only classifier interface and separate service | declaration at G1; V-4/V-8/G4 enforce |
| M6 | §6 gives the arbitrary-size A/B/C proof/partition | analytic reading and V-16; W3 checks branch-declaration presence only |
| M7 | §5.1 39-variable and symbolic-multiplicity rule | V-1–V-4 |
| M8 | exact slack-minimizer conditions, including inactive `+0.0` | V-2, V-3, V-11 |
| M9 | decision IDs and conditioning are carried here | W3 bounded check |
| M10 | D014 record digest plus separate governing decision hashes | V-13; procedural residual remains |

Class A is M1, M2, M6, M7, M8, M9, and ADNYE dependency/execution-point declarations.
Class B is only M4 and M5: G1 declares their interfaces; G4 must enforce them.

## 8. Handoff constraints and later-stage work

G2 must supply typed, unit-specified canonical `mu`, `Sigma`, `p`, and sector
membership without presupposing prototype ticker order; it must verify D007's
daily simple decimal-return convention and pin its source dates. G3 alone
executes the D008/D010 records, validates D014 outputs, enumerates `F` and
full space, and computes `f*`. G4 must bind coordinate/coefficient bit patterns
and implement the declared separated modules. G5+ must apply the frozen
comparator, provenance, and reporting rules.

The following are deliberately not generated at G1: canonical data, `v_j`
numeric values, `Lambda_ref`, `Delta_full`, box bounds, grid coordinates,
ADNYE JSON/sidecars, QUBOs, ground states, A/B/C rates, ablation outcomes,
D011 coarse extent, and V-14 execution reading. Their absence is a gate
boundary, not license for downstream discretion: every corresponding rule,
dependency, execution point, and pre-execution commitment above is fixed.

# PROTOTYPE AUDIT — `previous_work/QDTRINITY_sTAGE_2`

**Date:** 2026-08-22
**Auditor:** the lead (primary research engineer) — **not** an independent audit; independent audit still owed.
**Method:** static reading of the notebook (87 cells) and data files. **The prototype was not executed** —
it requires `pandas`/`scipy`, absent from this environment. All statements about its *runtime outputs* are
therefore `CANNOT VERIFY`.
**Reproducible checks:** `research/audit/verify_gate0_facts.py` (standard library only).

**Governing instruction** `[handoff §2, §E]`: the previous implementation is **not** authoritative. Where it
conflicts with the Scope Lock, the discrepancy is documented, not silently preserved — and the prototype is
**not** rewritten for cleanliness, to preserve provenance.

---

## 1. What the prototype is

A soft-penalty, QUBO-*inspired* portfolio model for the QD Trinity Challenge 2026 (Stage 2), developed in
three versions (V1 cardinality, V2 +sector, V3 +budget). Energy `[PROTOTYPE README, cells 19-22]`:

```
E(x) = -mu'x + lambda x'Sigma x + alpha(|x|_1 - K)^2
       + beta * sum_j max(0, n_j - C)^2
       + gamma * max(0, p'x - B)^2
```

Solved by exhaustive enumeration over `C(20,6) = 38,760` cardinality-restricted portfolios
`[PROTOTYPE cell 25]`, swept over `lambda x beta x gamma`.

**Inventory.** `Jupyter_Notebook_For_Submission.ipynb` (87 cells); `datasets/mu.csv`, `datasets/Sigma.csv`;
`datasets/QD_Trinity_Data_Pipeline_Setup (2).ipynb`; `technical_Report/*.pdf`; `README.md`; an **empty**
`git/` directory (0 bytes — no VCS history, so provenance beyond the files is `UNKNOWN`).

---

## 2. Findings

### F-1 — CRITICAL: asset ordering defect (18 of 20 positions mis-joined)

**Evidence.**
- `datasets/mu.csv` index order: `AAPL, ABBV, AMZN, BAC, CAT, CVX, GE, GOOGL, GS, HON, JNJ, JPM, LLY, MA,
  MRK, MSFT, NVDA, PFE, V, XOM` — **alphabetical** `[EXPERIMENTAL]`.
- `Sigma.csv` index == columns == `mu` index `[EXPERIMENTAL]`.
- `[PROTOTYPE cell 12]` defines the universe **sector-grouped**:
  `AAPL, MSFT, NVDA, GOOGL, AMZN | JPM, V, MA, GS, BAC | LLY, JNJ, MRK, PFE, ABBV | XOM, CVX, GE, CAT, HON`,
  with `sector_map` assigning **positions** 0-4, 5-9, 10-14, 15-19.
- `[PROTOTYPE cell 17]` defines `prices` as a positional 20-vector in that same sector-grouped order.
- `[PROTOTYPE cell 19]` converts to positional arrays: `mu = np.array(mu)`, `Sigma = np.array(Sigma)`.
- **No `reindex`, `.loc[stocks]`, or equivalent appears anywhere in the notebook** — verified by exhaustive
  regex search over all code cells.
- **Root cause confirmed** in `datasets/QD_Trinity_Data_Pipeline_Setup (2).ipynb`: the pipeline calls
  `yf.download(stocks, ...)`, and yfinance returns columns **sorted alphabetically**, not in the order the
  ticker list was supplied. That frame flows through `returns_df.pct_change()` -> `returns_df.mean()` ->
  `mu.to_csv('mu.csv')` and `returns_df.cov()` -> `Sigma.to_csv('Sigma.csv')` with **no reindex anywhere in
  the pipeline either** (`reindex`, `loc[stocks]`, `sort_index`, `sort_values` all absent). So the
  alphabetical ordering of `mu.csv`/`Sigma.csv` is a direct, explainable consequence of the download step,
  and the submission notebook then silently assumes positional correspondence with its sector-grouped
  `stocks` list.

**Consequence.** Position `i` carries `mu`/`Sigma` for the *i*-th **alphabetical** ticker but the price and
sector of the *i*-th **sector-grouped** ticker. Only positions 0 (AAPL) and 8 (GS) coincide.

| pos | code assumes | actual `mu` ticker | actual sector of that ticker |
|---|---|---|---|
| 0 | AAPL / Technology | AAPL | Technology (OK) |
| 1 | MSFT / Technology | ABBV | Healthcare |
| 2 | NVDA / Technology | AMZN | Technology |
| 3 | GOOGL / Technology | BAC | Finance |
| 4 | AMZN / Technology | CAT | Industrial_Energy |
| 8 | GS / Finance | GS | Finance (OK) |
| 15 | XOM / Industrial | MSFT | Technology |
| 16 | CVX / Industrial | NVDA | Technology |

**Severity.** CRITICAL for data provenance. **Not** fatal to the mathematical structure: the prototype still
minimized a well-defined objective over a well-defined constraint set — but one whose asset labels do not
correspond to reality.

**What this invalidates.** Every V2/V3 numeric portfolio output; the README's "~95-98% of unconstrained
return" claim; the Markowitz comparison; any sector-diversification interpretation. These must not be
quoted as financial statements.

**What it does not invalidate.** The enumeration machinery, the constraint arithmetic, and the parameter
values `K, C, B, alpha, prices` themselves.

**Action.** See `UNRESOLVED_DECISIONS.md` U-07. The loader must join by ticker and assert the join.

### F-2 — HIGH: prototype implements neither encoding under study

`[PROTOTYPE cells 21, 22]` The sector and budget terms are ordinary **hinge-squared soft penalties**
(`max(0, violation)^2`). They are:
- **not** slack-variable encoding — no auxiliary register exists anywhere in the notebook;
- **not** unbalanced penalization — no linear reward term `-lambda_1 h(x)` exists.

This corroborates `[SCOPE §3]` and the prototype's own technical report, which lists "explicit QUBO
compilation with slack bits" as **deferred future work**.

**Consequence.** There is **no inherited implementation** of either encoding. Both must be built from
scratch. There is correspondingly **no cross-validation baseline** available from the prototype for the
encoding logic — a real loss for validation strength, and the reason `VALIDATION_SPEC.md` leans entirely on
brute-force oracles rather than legacy cross-checks.

**Note on the marginalized form.** `[SCOPE §11, DERIVED]` shows that a *sufficiently wide* slack register
marginalizes to exactly the hinge-squared form the prototype uses. So the prototype's penalty coincides with
the **limiting behaviour** of slack — but only in the limit, and only after marginalization. It is not an
implementation of the encoding, and using it as one would silently discard the register-width question
(U-06) that this project must study.

### F-3 — MEDIUM: cardinality penalty never exercised

`[PROTOTYPE cell 25]` enumerates only `itertools.combinations(range(n), K)`, i.e. only `|x| = K`. The
cardinality term `alpha(|x| - K)^2` is therefore **identically zero over the entire enumerated set**.

**Consequences.**
1. `alpha = 20` was never actually tested; `[PROTOTYPE cell 15]`'s justification ("selected empirically to
   ensure the cardinality penalty strongly dominates") carries **no validation weight**. See U-13.
2. This project's QUBO ground state is over all `2^20` states, where the term **is** load-bearing. The
   prototype's enumeration strategy must **not** be inherited.

### F-4 — MEDIUM: price vector is an inline literal, and a decoy exists

`[PROTOTYPE cell 17]` `prices` is a hard-coded `np.array` inside the notebook. There is **no price CSV**,
contradicting the README's claim that "Stock prices extracted and frozen for reproducibility".

`[PROTOTYPE cell 32]` defines a **second** price vector `prices_stress = [500, 600, 700, 150, 120, 100]`
with `budget_stress = 1200`, `K_stress = 3`, `sector_cap_stress = 1`, for a 6-asset budget stress test. The
notebook annotates it as test-only.

**Risk.** Any automated extraction that greps for `prices` could pick up the wrong vector. Extraction must
target cell 17 and assert length 20 and integrality.

**Separate provenance finding.** The data pipeline *does* write a `prices.csv` — but that is the historical
**price time series** used to compute returns, a different object from the per-share cost vector `p` used in
the budget constraint. That series is **not present** in `datasets/` (only `mu.csv` and `Sigma.csv` survive).
The budget price vector in cell 17 is a set of hand-chosen round numbers (`210, 420, 1200, 180, ...`) with
**no documented derivation from market data**. It is therefore a **synthetic parameter**, not an empirical
one. This does not harm the study — the research question is about encodings, and a fixed synthetic price
vector is a perfectly valid instance parameter — but it must not be described in any write-up as
market-derived. Recorded here because `[SCOPE §26]`'s handoff item "Pull per-stock prices `p_i`" implies a
data file that does not exist.

### F-5 — LOW: stress test carries the ordering defect but is not invalidated by it

`[PROTOTYPE cell 32]` `stress_test_indices = [0,1,2,5,10,15]` is commented "AAPL, MSFT, NVDA, JPM, LLY, XOM"
but `mu.iloc` at those positions actually yields `AAPL, ABBV, AMZN, CVX, JNJ, MSFT`. The code then
**relabels** via `mu_stress.index = stress_test_stocks`, silently applying wrong labels.

**However:** every `mu_stress` value is subsequently overwritten with hand-set constants, so the test's
*budget mechanics* are unaffected. `Sigma_stress` remains mis-joined, but `lambda_stress = 0.01` makes the
risk term nearly irrelevant. The test's conclusion (budget penalty enforces the budget) is
`INFERENCE: probably sound`, but its labels are wrong.

### F-6 — INFORMATIONAL: environment

`[EXPERIMENTAL]` Python 3.12.3; `numpy` present; `pandas`, `scipy`, `matplotlib`, `pytest` **absent**. The
prototype cannot be run as-is. `research/audit/verify_gate0_facts.py` therefore uses only the standard
library.

---

## 3. Verified-good elements

`[EXPERIMENTAL]` These passed independent checks and are safe to reuse **as data**:

- `mu.csv`: 20 assets, no missing values, well-formed.
- `Sigma.csv`: 20x20, index == columns == `mu` index, well-formed.
- Constraint geometry is coherent and non-degenerate: `|F| = 976` fully feasible portfolios out of 38,760
  cardinality-feasible (2.5%), with cost range `[600, 4000]` against `B = 1100`. The budget and sector
  constraints genuinely bind — a precondition for the experiment being informative.
- All prices and `B` are integers, so all three residuals are integer-valued. This is what justifies
  `v_ref = 1` `[SCOPE §14]` and makes the closed-form minimizer exact without rounding ties.

---

## 4. Reuse verdict

| Component | Verdict | Reason |
|---|---|---|
| `mu.csv`, `Sigma.csv` contents | **REUSE** | verified well-formed; **join by ticker, never positionally** |
| `prices`, `sector_map`, `K/C/B` | **REUSE AS PARAMETERS** | extract to a versioned file; record cell-17 provenance |
| `alpha = 20` | **DO NOT INHERIT** | never exercised (F-3); re-derive (U-13) |
| `energy()`, `sector_penalty()`, `budget_penalty()` | **DO NOT REUSE** | hinge-squared soft penalty; neither encoding under study (F-2) |
| enumeration loop | **DO NOT REUSE** | restricted to `|x| = K`; this project needs all `2^20` (F-3) |
| Markowitz baseline, plots, V1/V2/V3 sweeps | **OUT OF SCOPE** | not part of the frozen question |
| all numeric results / README claims | **DO NOT TRUST** | invalidated as financial statements by F-1 |

---

## 5. Discrepancies against the Scope Lock

| # | Scope Lock says | Prototype / data says | Resolution |
|---|---|---|---|
| D1 | `kappa_risk` is a fixed scalar whose value "lives in the prototype's data files" `[§12]` | It is **not** in any data file; the notebook **sweeps** it over 6 values `[cell 14]` | **U-02** — must be fixed by decision |
| D2 | Budget register = 11 bits, 19 aux, 39 QUBO vars `[§13]` | Computable two ways from actual prices: 11 bits (domain = all `x`) or 9 bits (domain = `|x| = K`) | **U-06** — recommend keeping 39 |
| D3 | Prices "referenced in prototype, not yet extracted" `[§26]` | Found: inline literal, cell 17. Plus a decoy in cell 32 | Resolved; extraction task specified (F-4) |
| D4 | `Lambda_ref` = "range (**or std**)" over "the feasible set" `[§14]` | `|F| = 976` vs. 38,760 cardinality-feasible — four candidate values | **U-03** |
| D5 | A single scalar `s` `[§14]` vs. a "joint grid" and "three coefficients" `[§18, §22]` | — | **U-01**, the most consequential ambiguity |
| D6 | Data provenance assumed sound | 18/20 mis-join (F-1) | **U-07** |

---

## 6. What this audit does NOT establish

- It is **not independent**. The reviewer's audit is still owed and is the one that counts `[reviewer brief §11]`.
- The prototype was **not executed**; all claims about its runtime outputs are `CANNOT VERIFY`.
- The technical report PDF was **not parsed**; claims attributed to it come from `[SCOPE §3]` and the README.
- The data-pipeline notebook **was** subsequently parsed (see F-1 root cause), closing what had been the
  most likely route to F-1 being wrong. F-1 is now supported by both the absence of a reindex *and* a
  positive mechanism explaining the ordering.
- No claim is made that this list of defects is complete.

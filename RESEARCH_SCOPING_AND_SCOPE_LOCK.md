# QUBO Portfolio Optimization — Research Scoping, Literature Audit, and Scope-Lock Record

**Document created:** 2026-08-17
**Project status:** SCOPE LOCKED / IMPLEMENTATION STARTING
**Final research question:** Does the relative performance of slack-variable and unbalanced-penalization QUBO encodings remain stable across a principled, jointly-swept, dimension-matched penalty landscape, when evaluated against the certified exact ground state of the encoded QUBO (not the original problem's optimum alone), under multiple simultaneous heterogeneous constraints (cardinality, sector cap, budget) in portfolio optimization — or is the reported superiority of one encoding an artifact of the specific, single, separately-tuned penalty values at which prior comparisons were made?

**Executive summary:** This project began as a broad claim ("no prior work compares slack-variable and unbalanced-penalization QUBO encodings for constrained portfolio optimization while sweeping penalty parameters against certified exact ground truth"). An adversarial literature audit found that every individual ingredient of that claim already has precedent somewhere in the literature — encoding comparisons exist outside portfolio, certified ground truth exists in portfolio without an encoding comparison, multi-coefficient sweeps exist in portfolio without certified ground truth — so the original combination-only framing was rejected as inflated novelty. A narrower, better-evidenced question survived: every encoding comparison found in the literature calibrates each encoding to a single tuned operating point and never tests whether the resulting ranking is stable across a swept penalty landscape. That gap, not the original combination claim, is what this project now studies. A companion algebraic analysis established that a late-stage candidate threat (Awai et al.'s augmented Lagrangian formulation) is not equivalent to unbalanced penalization, and a final methodological decision resolved how to make the two encodings' penalty parameters comparable without introducing a provable bias. This document is the permanent provenance record of that process.

---

## 2. Executive Research Summary

**Problem domain.** Constrained portfolio optimization formulated as a Quadratic Unconstrained Binary Optimization (QUBO) problem, targeting eventual quantum/quantum-inspired solvers (QAOA, quantum annealing) but studied here entirely classically via exact enumeration.

**Constraints.**
- Cardinality (equality): exactly K of 20 assets selected.
- Sector-cap (inequality, ×4 sectors): no more than C assets per sector.
- Budget (inequality): total cost within a fixed limit.

**Encodings compared.**
- Slack-variable encoding: converts each inequality to an equality via an auxiliary binary register, penalized quadratically.
- Unbalanced penalization: a slack-free, auxiliary-variable-free quadratic-plus-linear penalty directly on the inequality residual (Montañez-Barrera et al. 2024).

**Core scientific question.** Whether the relative ranking of these two encodings — as reported in prior work only at single, separately-calibrated penalty points — is stable across a jointly-swept penalty landscape, or is an artifact of the calibration point chosen.

**Ground truth.** Two distinct exact objects are tracked throughout: the original constrained portfolio problem's exact optimum (via exhaustive enumeration of 38,760 cardinality-feasible portfolios), and the encoded QUBO's own exact ground state (a separate object per encoding and per penalty vector, certified via a closed-form computational method derived during scoping, not brute force).

**Core experimental approach.** A joint, objective-normalized penalty-space sweep over both encodings, exact enumeration-based ground-state certification, an A/B/C success taxonomy (exact / feasible-suboptimal / infeasible), robustness-region analysis, and a small Stage-2 instance family to guard against single-instance overclaiming.

This summary is faithful to, and derived from, the frozen Scope Lock document (an HTML artifact produced during this process, referenced throughout this record as "the Scope Lock document").

---

## 3. Starting Point — What the Project Originally Was

The project's earliest concrete form, as stated in the adversarial audit prompt supplied at the start of this scoping process, was:

> "A controlled comparison of slack-variable QUBO encoding versus unbalanced penalization, studied as a function of penalty parameters, for constrained portfolio optimization, with validation against certified exact optima."

The stated setup involved cardinality, sector-cap, and budget constraints simultaneously, with multiple penalty coefficients, and a prototype already validated by exhaustive enumeration on a 20-asset, K=6 instance (C(20,6) = 38,760 feasible portfolios).

**What we originally thought was novel** (as six explicit candidate claims, tested one by one during the audit):
1. No prior work compares slack-variable and unbalanced encodings.
2. No prior work compares these encodings while varying penalty parameters across a range.
3. No prior work performs such a comparison against certified exact optima.
4. No prior work jointly varies three or more independent penalty coefficients against certified exact optima.
5. No prior work studies this interaction in constrained portfolio optimization.
6. No prior work characterizes the robustness regions of different constraint encodings in multidimensional penalty space.

**What the initial testbed actually was.** Not a from-scratch design — it was the existing prototype from a prior competition submission ("QD Trinity Challenge 2026, Stage 2," a `Submission_2_Team_50.zip` archive found in the working directory during initial file discovery). That prototype implements a **soft-penalty QUBO** with a single combined objective:

$$E(x) = -\mu^Tx + \lambda x^T\Sigma x + \alpha(\|x\|_1-K)^2 + \beta\sum_{j=1}^4\max(0,n_j-C)^2 + \gamma\max(0,p^Tx-B)^2$$

with $\lambda$ risk-aversion, $\alpha=20$ (cardinality weight, fixed), $\beta\in[0,10]$ (sector), $\gamma\in[0,1]$ (budget), on 20 blue-chip stocks across 4 sectors (Technology, Finance, Healthcare, Industrial/Energy), K=6, C=2, B=$1100.

**Important honesty check, preserved from the original read of that prototype:** this existing code does **not** implement unbalanced penalization at all. Its own technical report explicitly lists "explicit QUBO compilation with slack bits" as **deferred future work**. The slack-vs-unbalanced comparison that is the entire point of this project had not been built when scoping began — the prototype only validates a single soft-penalty formulation via exhaustive enumeration, and its "sector"/"budget" penalty terms are ordinary hinge-squared soft penalties, not literally either of the two encodings under study.

**Initial assumptions made (later tested, not simply accepted):** that the 3-month project could proceed straight to implementation; that the combination of ingredients (slack vs. unbalanced, swept, certified, portfolio, multi-constraint) was self-evidently novel because no single paper matching every ingredient had been located casually. The adversarial audit was explicitly commissioned to attack this assumption rather than confirm it.

---

## 4. Evolution of the Research Question

### 4.1 Initial formulation
The broad claim above (six candidates) was the starting point for the adversarial audit. No claim had yet been tested against primary literature; all six were, at this stage, unverified researcher assertions.

**What changed and why:** Nothing yet — this is the baseline against which everything else in this section is measured.

### 4.2 First novelty challenge
Four parallel research passes were run: (1) verification of three specifically named papers plus a fresh recent-literature sweep, (2) a cross-domain search for encoding-comparison prior art, (3) a cross-domain search for penalty-sweep and exact-ground-truth prior art, (4) a deep portfolio-specific prior-art search testing all four claim pillars simultaneously.

The first pass found, and verified via direct primary-text fetch, that **Montañez-Barrera et al. (arXiv:2211.13914, published *Quantum Sci. Technol.* 9:025022, 2024)** already performs a direct, numeric, head-to-head slack-vs-unbalanced comparison — just on TSP, bin-packing, and knapsack, not portfolio. A separate, unresolved-provenance GitHub repository (`alejomonbar/clever-portfolio-optimization-encoding`) was found doing the same comparison specifically on a portfolio QUBO, though with only two constraints (budget + minimum-return, not cardinality+sector+budget) and no confirmed peer-reviewed publication.

**What changed and why:** Candidate 1 ("no prior work compares slack and unbalanced") was **CONTRADICTED** in its general (domain-agnostic) form, and weakly contradicted even within portfolio specifically. The claim as originally stated could not be used.

### 4.3 First narrowing
Because the *existence* of a slack-vs-unbalanced comparison was no longer defensible as a novelty claim, the framing shifted toward *how* that comparison had been performed in the literature that did exist. Every comparison paper found (Montañez-Barrera 2211.13914, its 2023 D-Wave follow-up arXiv:2305.18757, and the portfolio GitHub repo) calibrates each encoding to a **single tuned operating point** (via Nelder-Mead or COBYLA, or unspecified manual tuning) and reports a winner at that one point — none sweeps a range. This observation became the seed of the eventual final research question, though it was not yet the primary framing at this stage; at this stage it was simply the reason Candidate 2 ("no prior work sweeps a range while comparing") still looked survivable.

**What changed and why:** The project's working hypothesis moved from "does a comparison exist" (settled: yes) to "does a *swept* comparison exist" (still open at this point).

### 4.4 Adversarial literature search
A second, more targeted round (the "kill-shot" search, §4.5 below) was commissioned specifically to attack the surviving narrower claim: *"Has anyone studied whether the relative performance/ranking of two different QUBO constraint encodings remains stable across a range/joint grid of penalty parameters, rather than at a single tuned point?"* This search was explicitly domain-agnostic (TSP, knapsack, scheduling, Max-Cut, rostering, generic constrained binary optimization all counted), and explicitly excluded three patterns from counting as a threat: (a) penalty sensitivity studied for one encoding only, (b) two encodings compared at one tuned point each, (c) two encodings independently calibrated and then compared once.

### 4.5 Discovery of methodological precedents
The kill-shot search found two papers of note:

- **Kikuchi, Takahashi & Tanaka (arXiv:2410.11198, 2024)** — a genuine, verified DIRECT THREAT under the literal three-part test: domain-wall encoding vs. one-hot encoding for a knapsack capacity variable, with penalty coefficient λ explicitly swept (0.1–0.9, then a finer 0.01–0.99 pass), and both encodings' feasibility rate and approximation ratio plotted against each other across that same range (Fig. 2, Table I). This proved the *experimental design pattern itself* — "plot two encodings against a swept penalty" — was not unprecedented in QUBO literature generally.
- **Awai et al. (arXiv:2606.24241, 2026)** — flagged initially as a PARTIAL THREAT, "right encoding family, unconfirmed cross-variation comparison," because its abstract described comparing an augmented Lagrangian formulation against a plain penalty formulation while sweeping two hyperparameters (μ, λ) against known-optimal quadratic-knapsack benchmarks. At this stage its relationship to unbalanced penalization specifically was **unresolved** — the kill-shot fork could not extract its figures to confirm cross-variation comparison, and guessed (incorrectly, as §4.6 later established) that it might belong to the "Lagrangian vs. penalty" family relevant to unbalanced.

**What changed and why:** Kikuchi et al. demonstrated the experimental *pattern* has prior art (though in a different encoding family — integer-variable binarization, not constraint encoding), which meant the project could no longer claim "no one has ever compared two encodings across a penalty sweep" as a domain-agnostic methodological novelty. It could still claim no one had done so for the *specific* encoding family (slack vs. unbalanced/Lagrangian) — but Awai et al. now needed to be resolved to know whether that narrower claim survived too.

### 4.6 Algebraic distinction between ALF and unbalanced penalization
Both source PDFs (Montañez-Barrera et al. 2024, full 17 pages; Awai et al. 2606.24241, full 11 pages) were read directly and in full from a local `papers/` folder supplied mid-session. A term-by-term algebraic derivation was performed (documented in full in §11 below) establishing that:

- Awai et al.'s baseline "Penalty Function" (PF) and their augmented Lagrangian function (ALF) **both retain the auxiliary slack register** used by ordinary slack-variable encoding — they are two different *weightings* of the same slack-based residual, not a slack-free method.
- Unbalanced penalization has **no auxiliary variables at all** and is a direct function of the original inequality residual.
- After marginalizing the auxiliary register, ALF is **flat across the entire feasible region** (like plain slack) and coincides with unbalanced penalization's functional form **only on the infeasible branch**, and only under an idealized "saturated" auxiliary-bit assignment — not a general equivalence.

**What changed and why:** Awai et al. was reclassified from "PARTIAL THREAT, right encoding family, unresolved" to **NOT A THREAT** to the slack-vs-unbalanced claim specifically — it compares two members of the slack-based family, not slack vs. unbalanced. This was a downgrade of a previously-flagged risk, arrived at by direct derivation rather than further searching, and is recorded here exactly as it happened so a future reader does not need to re-derive it or mistakenly re-flag Awai et al. as a threat.

### 4.7 Final rank-stability framing
With Awai et al. cleared and no other located paper combining an encoding comparison with a genuine swept range in the slack/unbalanced family, the surviving research question crystallized into its final form: not "does an encoding comparison exist" (no), not "does a penalty sweep exist" (no, in this specific family), but **"is the ranking reported by prior single-point-tuned comparisons stable across a swept penalty landscape, or an artifact of the calibration point."** This is the question stated in the document header and locked in the Scope Lock document.

**What changed and why:** This is the final narrowing. It is deliberately narrower than the original six-candidate combination claim, and deliberately more specific than "no methodological precedent for sweeping two encodings exists" (which Kikuchi et al. already disproved in a different family). It survives specifically because the *calibration-artifact* question — whether a reported comparison generalizes beyond its one tuned point — was not found tested anywhere in the searched literature, in any domain, for any encoding pair.

---

## 5. Literature Search Methodology

**Tools and approach.** All literature search was performed via general web search and direct arXiv/publisher access (WebSearch/WebFetch-equivalent tooling inside parallel research subagents), plus direct reading of two full-text PDFs supplied locally (Montañez-Barrera et al. 2024; Awai et al. 2606.24241) from a `papers/` folder.

**Search structure.** Five separate passes were run across this project's lifetime:
1. Named-paper verification + fresh recent-literature sweep (Chang et al. 2000, Stopfer & Wagner 2025, "Montañez-Barrera 2025").
2. Cross-domain encoding-comparison threat search (Threat A).
3. Cross-domain penalty-sweep / exact-ground-truth threat search (Threats B, C, D).
4. Deep portfolio-specific prior-art search against all four claim pillars simultaneously (Threat E).
5. A narrow, final "kill-shot" search targeting exactly the surviving rank-stability conjunction, explicitly excluding single-point-comparison and independently-tuned-comparison patterns from counting as threats.

**Terminology-drift searching.** Each pass deliberately searched conceptual equivalents, not just literal phrase matches (full vocabulary recorded in §6), and was explicitly instructed to search outside portfolio optimization (TSP, knapsack, bin-packing, job-shop scheduling, maximum independent set, generic constrained binary optimization) on the premise that a methodological precedent in another domain could still kill the claim.

**Primary-source standard applied throughout.** Every pass was instructed to prefer primary PDFs/arXiv full text over abstracts, blog posts, or secondary summaries, and to explicitly report `CANNOT VERIFY` rather than infer methodology from an abstract. This standard was mostly honored — several items remain explicitly `CANNOT VERIFY` rather than silently cleared (see §10).

**Coverage — what was actually searched well vs. poorly (do not treat this list as exhaustive coverage claims):**
- **Strong coverage:** arXiv (quant-ph, math.OC), general web/Google search. Roughly 15–20 papers were read from primary PDF text rather than abstracts across all passes combined.
- **Weak/blocked coverage:** ACM Digital Library (one directly-relevant paper permanently paywalled across two separate search passes — see §10), IEEE Xplore direct access, Semantic Scholar's own API (only reached via general web search snippets, not queried directly), Springer, ScienceDirect (403 on the one paper attempted — Chang et al. 2000), bioRxiv (blocked).
- **Domains named in the original audit brief but not actually searched:** job-shop scheduling, rostering. This is an explicit, acknowledged gap, not an oversight to be silently ignored.
- **A caught self-correction, worth preserving as a methodology note:** one search pass returned a description of a portfolio QUBO example with "K=10 assets, sector cap ≤3" nearly matching this project's own penalty terms, but no specific paper title could be traced to it despite repeated follow-up queries, and it had the signature of a search tool paraphrasing generic tutorial content rather than quoting a real citation. It was explicitly excluded from the evidence base rather than reported as a finding — recorded here as an example of the search process working as intended (not finding a paper ≠ concluding no paper exists), not as a literature threat.

**Explicit non-exhaustiveness statement.** At no point should this record be read as "the literature was exhaustively searched." Multiple items remain unresolved (§10). The standard applied throughout was: *"no directly matching paper was identified in the literature searched,"* never *"no such paper exists."*

---

## 6. Search Terminology Used

### Encoding terminology
slack variable · slack-free · unbalanced penalization · unbalanced penalty · Lagrangian formulation · inequality encoding · equality encoding · constraint encoding · quadratic penalty · penalty reformulation · QUBO reformulation · binary reformulation · encoding overhead · auxiliary variables · ancilla variables · quadratization · domain-wall encoding · one-hot encoding

### Penalty terminology
penalty coefficient · penalty parameter · Lagrange multiplier · penalty weight · constraint weight · penalty scaling · penalty calibration · penalty tuning · penalty sensitivity · parameter sensitivity · hyperparameter sensitivity · coefficient robustness · robustness to penalty selection · constraint weighting · energy scale · energy separation · feasibility threshold · optimality threshold · parameter regime · phase diagram · regime boundary

### Comparison terminology
encoding comparison · formulation comparison · alternative QUBO formulations · versus / vs · robustness region · regime map · sensitivity analysis · parameter sweep · parameter scan · grid search · coefficient sweep · phase transition · solution regime · feasible/infeasible ordering · ground-state structure · energy landscape · optimality landscape · constraint-violation landscape

### Domain terminology
QUBO · quadratic unconstrained binary optimization · Ising · quantum annealing · QAOA · quantum optimization · combinatorial optimization · constrained binary optimization · portfolio · cardinality-constrained portfolio · budget-constrained portfolio · sector-constrained portfolio · quantum portfolio optimization · knapsack · multidimensional knapsack · multiple knapsack · bin packing · TSP · job-shop scheduling (searched for, not actually covered) · rostering (searched for, not actually covered) · maximum independent set · Max-Cut · railway timetabling · molecular docking

### Kill-shot-specific boolean forms used in the final targeted pass
`("slack" OR "slack-free" OR "unbalanced" OR "Lagrangian") AND ("QUBO" OR "quadratic unconstrained binary optimization") AND ("sensitivity" OR "robustness" OR "parameter sweep" OR "penalty weights" OR "penalty parameters") AND ("comparison" OR "versus" OR "vs")` plus a broader non-lexical pass for formulation comparisons evaluated across varying penalty weights without requiring slack/unbalanced vocabulary at all, plus a dedicated January 2025–August 2026 recency pass.

---

## 7. Paper-by-Paper Literature Record

> Note on citation completeness: metadata below is exactly what was captured during the actual search passes. Where an item (DOI, page number, exact section) was not confirmed, it is marked `CANNOT VERIFY` rather than filled in. No page numbers, DOIs, or figure numbers below are invented.

### Unbalanced penalization: a new approach to encode inequality constraints of combinatorial problems for quantum optimization algorithms

**Authors:** J A Montañez-Barrera, Dennis Willsch, A Maldonado-Romo, Kristel Michielsen
**Year:** 2024 (submitted 2023)
**Venue:** *Quantum Science and Technology* 9, 025022
**DOI / arXiv:** arXiv:2211.13914; DOI 10.1088/2058-9565/ad35e4
**Role in our scoping process:** Foundational source paper — supplies the unbalanced-penalization formulation this entire project studies (eq. 25–27), and is the paper whose reported comparison (single-point-tuned, TSP/BPP/KP) motivates the final rank-stability question.
**Threat classification:** DIRECT THREAT (to Candidate 1, general domain-agnostic form) / METHODOLOGICAL THREAT (established the core method exists, just not swept, not portfolio) — later became primary related work and the source of the frozen mathematical formulation.

**What the paper actually does.** Compares slack-variable and unbalanced-penalization QUBO encodings on TSP, bin-packing (BPP), and knapsack (KP), up to 43 qubits, via OpenQAOA simulation and D-Wave Advantage/Hybrid hardware. Reports the unbalanced approach achieves feasible solutions for BPP up to 29 items vs. 11 for slack (D-Wave Hybrid solver, §4.2, Figs. 11–12). Tunes 3 coefficients ($\lambda_0,\lambda_1,\lambda_2$) via Nelder-Mead to one point per problem (Table 1, §3). Explicitly documents (§4.1, Figs. 5–6) that the unbalanced ground state is **not guaranteed** to be the true optimum — in one worked example, two infeasible eigenstates have lower energy than the optimal (feasible) solution.

**What it does NOT do.** Never sweeps $\lambda_0,\lambda_1,\lambda_2$ over a range — reports one calibrated point per problem instance. No portfolio application anywhere in the paper (confirmed by direct text read — portfolio is not mentioned). No certified/exhaustive ground truth for the encoding comparison itself; reference points are annealer/QAOA-reported low-energy states, not a proven optimum for most cases (though for small TSP/BPP/KP cases the paper does compare against the *known* combinatorial optimum via eigenvalue-position analysis, §4.1).

**What claim it killed or weakened.** Killed Candidate 1 ("no prior work compares slack and unbalanced") in its general form outright.

**What it contributed to our final framing.** Supplied: the exact mathematical formulation of unbalanced penalization used throughout this project (§13); the Taylor-expansion motivation ($e^{-h(x)}\approx 1-h(x)+\tfrac12h(x)^2$, their eq. 24) that became the basis of the frozen κ-parameterization (§14); the single-point-calibration pattern whose generalizability is the entire research question; and the explicit feasible/infeasible energy-ordering caveat (their own Figs. 5–6) that motivates Hypothesis H2 (§20).

**Evidence.** eq. 5–9 (general QUBO/penalty setup), eq. 23–27 (unbalanced penalty derivation), Table 1 (tuned $\lambda_{0,1,2}$ values, one point each for TSP/BPP/KP), §4.1 and Figs. 5–6 (eigenvalue-position / non-guaranteed ordering), §4.2 and Figs. 9–12 (D-Wave results). Full text read directly.

---

### Improving Performance in Combinatorial Optimization Problems with Inequality Constraints: An Evaluation of the Unbalanced Penalization Method on D-Wave Advantage

**Authors:** Montañez-Barrera et al. (same group)
**Year:** 2023
**Venue:** arXiv preprint (referenced as [53] in the 2024 QST paper's own bibliography)
**DOI / arXiv:** arXiv:2305.18757
**Role in our scoping process:** Follow-up encoding-comparison paper found during the encoding-comparison threat search and re-confirmed during the kill-shot pass.
**Threat classification:** DIRECT THREAT (to Candidate 1, general form) / NOT A THREAT (to the swept-comparison / rank-stability claim, per the kill-shot pass's explicit exclusion criteria).

**What the paper actually does.** Slack-vs-unbalanced comparison on TSP, against CPLEX branch-and-bound as reference for smaller instances.

**What it does NOT do.** Sweeps nothing — single-point calibration via COBYLA ($\lambda_{0,1,2}=\{0.88,0.46,0.54\}$ unbalanced; $\lambda_{0,1}=\{0.88,0.88\}$ slack, per the kill-shot fork's direct text read). CPLEX exactness explicitly degrades at larger instance sizes per the paper's own text — not a scale-general certified benchmark. No portfolio.

**What claim it killed or weakened.** Reinforces the Candidate 1 kill; does not touch the surviving rank-stability question.

**What it contributed to our final framing.** Confirmatory evidence that single-point calibration is the consistent pattern across this research group's own papers, strengthening the case that the rank-stability question is genuinely untested by its own authors.

**Evidence.** Coefficient values and CPLEX degradation statement confirmed via direct text fetch during the kill-shot pass; exact section/table numbers were not separately recorded in that pass's notes — `CANNOT VERIFY` exact table number.

---

### Enhancing portfolio optimization solutions: wisely encoding constrained combinatorial optimization problems on quantum devices

**Authors:** Attributed to the Montañez-Barrera research group (GitHub handle `alejomonbar`)
**Year:** Not confirmed — `CANNOT VERIFY`
**Venue:** GitHub repository, not a confirmed peer-reviewed publication
**DOI / arXiv:** None located
**URL:** `github.com/alejomonbar/clever-portfolio-optimization-encoding` (repository name as found; not independently re-verified as still live)
**Role in our scoping process:** The single most dangerous unresolved item identified during the encoding-comparison threat search — a portfolio-specific slack-vs-unbalanced comparison.
**Threat classification:** PARTIAL THREAT, publication status unresolved.

**What it appears to do.** Slack-vs-unbalanced comparison specifically on a portfolio QUBO (budget + minimum-return constraints only — not cardinality or sector cap), reporting roughly a 1400× improvement in optimal-solution probability for the unbalanced encoding, using docplex for ground truth.

**What it does NOT do (or what remains unconfirmed).** No confirmed systematic penalty sweep — README-level description only mentions coefficients "must be tuned." No cardinality or sector-cap constraints (2 of the 3 constraint types this project studies). Whether docplex was run to certified optimality or terminated early is unconfirmed.

**What claim it killed or weakened.** Weakens the portfolio-specific form of Candidate 1 (an encoding comparison in portfolio does appear to exist, informally) but does not close the full-constraint-set, swept-comparison version of the question.

**What it contributed to our final framing.** A standing risk flagged for resolution before scope lock; not fully resolved by the end of this process (see §10 — its associated publication, if any, was never located).

**Evidence.** README-text level only — no equations, figures, or page numbers available to cite. `CANNOT VERIFY` beyond README claims.

---

### Quantum Portfolio Optimization: An Extensive Benchmark

**Authors:** Stopfer, Wagner
**Year:** 2025
**Venue:** arXiv preprint
**DOI / arXiv:** arXiv:2509.17876
**Role in our scoping process:** Named directly in the original audit brief as an unresolved claim requiring verification; read in full text.
**Threat classification:** PARTIAL THREAT.

**What the paper actually does.** Portfolio QUBO with budget, upper-bound, return, and volatility constraints (no cardinality, no sector cap) — the paper's own text (§7) describes it as "the most simple formulation." 250 instances up to 1000 assets; ground truth via Gurobi MIP proven optimal at 0% gap (§5, eq. 24); quantum methods tested only up to 25 assets. Penalty coefficients $\phi=\psi=1000$ fixed by magnitude-matching (§4/§6, eq. 18) — never swept.

**What it does NOT do.** No cardinality or sector constraints. No penalty sweep. No slack-vs-unbalanced comparison — only one formulation is used throughout.

**What claim it killed or weakened.** Weakens (does not fully kill) the "certified exact ground truth in portfolio QUBO" novelty axis on its own — this precedent exists, at real scale, just without an encoding comparison or sweep. Also weakens Candidate 3 partially, since it establishes MIP-proven-optimal as an accepted, precedented ground-truth method in this exact subfield (useful precedent for our own methodology, not a threat to the specific combined claim).

**What it contributed to our final framing.** Established MIP-certified ground truth as a legitimate, precedented alternative to exhaustive enumeration for scaling beyond the current 20-asset instance (relevant to future work / Stage 2+ discussions, though the frozen Stage 1/2 design in this project uses exhaustive enumeration specifically, §15).

**Evidence.** §2 (eq. 6–15, constraint definitions), §4 (eq. 18, fixed penalty form), §5–6 (Gurobi ground truth methodology), §7 ("most simple formulation" self-description). Full text fetched and quoted directly; high confidence.

---

### Diversifying Investments and Maximizing Sharpe Ratio: A Novel QUBO Formulation

**Authors:** Mattesi et al.
**Year:** 2024
**Venue:** *MDPI Quantum Reports*
**DOI / arXiv:** arXiv:2302.12291
**Role in our scoping process:** Closest near-miss on Candidate 4 (multi-coefficient sweep in portfolio) found during the portfolio-specific prior-art search.
**Threat classification:** PARTIAL THREAT.

**What the paper actually does.** Sweeps 3 independent penalty coefficients ($\lambda_0,\lambda_1,\lambda_2$) in a portfolio QUBO (§5.4, Fig. 2) — the only paper found anywhere in this search doing a genuine multi-coefficient sweep in the portfolio domain.

**What it does NOT do.** Its "diversification" term is a soft entropy-type penalty, not a hard sector cap. Ground truth is **PyPortfolioOpt, a heuristic classical solver** — not certified/exact. No slack-vs-unbalanced encoding comparison anywhere.

**What claim it killed or weakened.** Falsifies the bare, unqualified form of Candidate 4 ("no prior work sweeps 3+ coefficients in portfolio QUBO") — but not the conjunction with certified ground truth, which this paper lacks entirely.

**What it contributed to our final framing.** Directly informed the narrowing of Candidate 4 to require certified (not heuristic) ground truth as an explicit, load-bearing conjunct, since dropping that requirement would concede the claim to this paper.

**Evidence.** §5.4 and Fig. 2 (the 3-coefficient sweep); ground-truth method (PyPortfolioOpt) confirmed via direct text fetch.

---

### QUBO Formulations and Characterization of Penalty Parameters for the Multi-Knapsack Problem

**Authors:** Güney, Ehrenthal, Hanne
**Year:** 2025
**Venue:** *IEEE Access*, vol. 13
**DOI / arXiv:** DOI 10.1109/ACCESS.2025.3550788
**Role in our scoping process:** Found during the penalty-sweep/exact-ground-truth threat search.
**Threat classification:** METHODOLOGICAL THREAT.

**What the paper actually does.** 1-D sweep of a single, shared penalty multiplier $\lambda$ (0.5–1.5× a theoretical bound) across 120 multidimensional-knapsack instances, against Gurobi-proven-optimal ground truth within a 600s time limit ("EFFECTS OF PENALTY PARAMETER" section, Figs. 4–5).

**What it does NOT do.** Despite the multidimensional knapsack problem having multiple simultaneous capacity constraints, only **one shared** $\lambda$ is used and swept — not independent per-constraint coefficients. Slack-encoding only; no unbalanced-penalization comparison anywhere. Not portfolio.

**What claim it killed or weakened.** Establishes that "sweep + near-certified ground truth" exists as a combination — just not with an encoding comparison, not portfolio, and only 1-dimensional.

**What it contributed to our final framing.** Directly informed Hypothesis H3 (constraint heterogeneity) framing and confirmed that multidimensional (not just 1-D) sweeps remain genuinely unprecedented in this literature.

**Evidence.** "EFFECTS OF PENALTY PARAMETER" section (exact page/section number not separately recorded — `CANNOT VERIFY` precise locator beyond section title), Fig. 4, Fig. 5. Full text fetched directly.

---

### Performance of Domain-Wall Encoding in Digital Ising Machine

**Authors:** Kikuchi, Takahashi, Tanaka
**Year:** 2024
**Venue:** arXiv preprint
**DOI / arXiv:** arXiv:2410.11198
**Role in our scoping process:** The one confirmed DIRECT THREAT found by the kill-shot search under its literal three-part test.
**Threat classification:** DIRECT THREAT (to the literal, domain-agnostic "has anyone ever compared two encodings across a swept penalty" pattern) / not a threat to the specific slack-vs-unbalanced family.

**What the paper actually does.** Compares domain-wall encoding vs. one-hot encoding for representing an integer weight/capacity variable in a quadratic knapsack QUBO. Penalty coefficient $\lambda$ explicitly swept (0.1–0.9 in 0.1 steps, then a finer 0.01–0.99 pass). Both encodings' feasibility rate and approximation ratio plotted against each other across that same range (Fig. 2, "λ-dependencies of one-hot encoding and domain-wall encoding"; Table I, peak performance and $\lambda^*$ per encoding, two knapsack instances).

**What it does NOT do.** Domain-wall vs. one-hot is a choice about how to binarize an *integer variable*, not a choice about how to encode an *inequality constraint* (slack vs. unbalanced vs. Lagrangian) — a structurally different kind of "encoding" from the one this project studies. Single coefficient (1-D sweep), single domain (quadratic knapsack). Ground-truth certification method not stated beyond "optimal solutions... known" from a prior instance dataset — `CANNOT VERIFY` whether that dataset's optima are exhaustively certified or best-known.

**What claim it killed or weakened.** Kills the *fully general* claim "no QUBO encoding pair has ever been compared across a penalty sweep, in any sense of 'encoding.'" Does not kill the claim as scoped to the slack/unbalanced constraint-encoding family specifically.

**What it contributed to our final framing.** Forced explicit precision in how the final research question describes "encoding" — the locked question is now careful to specify *constraint*-encoding families (slack, unbalanced, Lagrangian-type), not encoding in the fully general sense, precisely because this paper exists.

**Evidence.** Fig. 2, Table I. Confirmed via two independent direct fetches of the paper's HTML full text (consistent detail both times).

---

### Evaluating the solution performance of the augmented Lagrangian function on Ising machines

**Authors:** Shunsuke Awai, Takuro Itoh, Keita Takahashi, Kotaro Tanahashi, Shu Tanaka
**Year:** 2026 (submitted 23 Jun 2026)
**Venue:** arXiv preprint / *Journal of the Physical Society of Japan* (Full Papers)
**DOI / arXiv:** arXiv:2606.24241v1
**Role in our scoping process:** Initially flagged as an unresolved PARTIAL THREAT by the kill-shot search; fully resolved via direct algebraic derivation later in this session (§11).
**Threat classification:** Initially PARTIAL THREAT / unresolved → **finally NOT A THREAT** to the slack-vs-unbalanced claim, after derivation.

**What the paper actually does.** Compares the "Penalty Function" (PF, standard slack-based quadratic penalty, their eq. 17) against the "Augmented Lagrangian Function" (ALF, their eq. 18, which adds a linear Lagrange-multiplier correction term on top of the same slack-based residual) on the quadratic knapsack problem, sweeping $(\mu,\lambda)$ jointly on a 2D grid ($\mu$: 0–100 step 5; $\lambda$: −500–500 step 50 — their Table I) against known-optimal QKP benchmark instances (Table II).

**What it does NOT do.** Does not compare against unbalanced penalization at all — the paper never mentions unbalanced penalization or Montañez-Barrera's method. Both of its own compared formulations (PF and ALF) retain the auxiliary slack register described in their §3.1.2 ("a slack variable... is introduced to convert the inequality constraint into an equality constraint") — this is standard slack-variable encoding, not a slack-free method. Not portfolio.

**What claim it killed or weakened.** Initially thought to be a possible threat to the "no prior work sweeps a slack-vs-unbalanced-family comparison" claim; the derivation in §11 shows it does not touch that claim, because it never uses unbalanced penalization or a slack-free method at all.

**What it contributed to our final framing.** A rigorous, project-derived (not paper-stated) partial algebraic connection between ALF and unbalanced penalization on the infeasible branch only (§11) — useful as a related-work theoretical framing point, explicitly labeled throughout as our own derivation, not a finding of this paper.

**Evidence.** eq. 16–18 (Hamiltonian construction), §3.1.1–3.1.4 (PF and ALF definitions), §6.1 (their own square-completion showing ALF shifts the energy minimum to $H_\text{const}=\lambda/\mu$ — directly used in our derivation), Table I (grid specification), Table II (QKP benchmark instances). Full 11-page text read directly from local PDF.

---

### Chang, Meade, Beasley, Sharaiha — cardinality-constrained efficient frontier heuristics

**Authors:** T.-J. Chang, N. Meade, J.E. Beasley, Y.M. Sharaiha
**Year:** 2000
**Venue:** *Computers & Operations Research* 27, 1271–1302
**DOI / arXiv:** Not confirmed — `CANNOT VERIFY` (paywalled; DOI not independently confirmed)
**Role in our scoping process:** Named directly in the original audit brief as requiring verification of whether it used certified exact ground truth.
**Threat classification:** RELATED, NOT THREATENING.

**What the paper appears to do.** Genetic algorithm, tabu search, and simulated annealing heuristics for the cardinality-constrained efficient frontier, tested up to 225 assets. Pre-QUBO, classical, not a quantum-adjacent paper.

**What it does NOT do (per available evidence).** Does not appear to use certified/exact ground truth — heuristics are compared against each other / best-found solutions, not a proven optimum. No encoding comparison (not applicable — different problem formalism entirely). No penalty sweep in the sense this project studies.

**Confidence level.** **Medium, not primary-text confirmed.** Direct access was blocked (ScienceDirect 403, academia.edu blocked). The conclusion above rests on convergent secondary-source characterization (multiple independent summaries agreeing on the heuristic-vs-heuristic comparison method, and the existence of a later paper explicitly framed as filling this gap — see below), not on reading the primary text.

**What claim it killed or weakened.** None — if anything, this paper's apparent lack of certified ground truth is reassuring for our own certified-ground-truth framing, but this reassurance is only medium-confidence and should not be over-relied upon.

**Related unresolved item.** A separate paper, referenced as *"An exact algorithm for small-cardinality constrained portfolio optimisation,"* was found cited but never independently verified (author, exact year, and venue all `CANNOT VERIFY`). This paper could be **more dangerous** to the certified-ground-truth novelty axis than Chang et al. itself, since its title suggests it may already provide exact benchmarking for exactly this problem class. **This remains unresolved at the time of scope lock** — see §10.

**Evidence.** No primary-text section/figure/page citations available — access was blocked throughout. All statements above are `CANNOT VERIFY` at the primary-source level and explicitly flagged as inference.

---

### Cutting Slack: Quantum Optimization with Slack-Free Methods for Combinatorial Benchmarks

**Authors:** Not separately recorded in search notes — `CANNOT VERIFY`
**Year:** 2025
**Venue:** arXiv preprint
**DOI / arXiv:** arXiv:2507.12159
**Role in our scoping process:** Found during the encoding-comparison threat search.
**Threat classification:** METHODOLOGICAL THREAT (unverified depth).

**What the paper appears to do.** Slack vs. slack-free comparison on TSP, multidimensional knapsack, and maximum independent set (Tables 3–8, Fig. 1, per search-summary level evidence).

**What it does NOT do / what remains unconfirmed.** Portfolio is not covered (not found in accessible content). Multipliers appear to be updated adaptively via augmented Lagrangian rather than grid-swept — unconfirmed by direct figure read. Ground-truth method mixed/unconfirmed (best-known for MDKP, claimed-exact for MIS, source of that exactness claim not independently verified).

**Confidence level.** Figures were referenced via search-summary text, **not** independently confirmed by a direct PDF section read — should be treated as lower-confidence than the papers read in full above.

**Evidence.** `CANNOT VERIFY` beyond search-summary description; no independently-confirmed page/figure citation.

---

### Implementing Slack-Free Custom Penalty Function for QUBO on Gate-Based Quantum Computers

**Year:** 2025 · **DOI/arXiv:** arXiv:2504.12611
**Threat classification:** NOT A THREAT (confirmed).
**What it does.** Sweeps its own custom slack-free penalty method's parameters (Table II / Fig. 2 per kill-shot fork's direct text confirmation), on multiple knapsack.
**What it does not do.** Unbalanced penalization is shown at **one tuned point only, not swept** — explicitly fails the cross-variation-comparison requirement. Confirmed directly from text, not inferred from title.

---

### Slack-Free Deep-Unfolded Combinatorial Optimization Solver (UPOM)

**Year:** 2026 · **DOI/arXiv:** arXiv:2607.20042
**Threat classification:** NOT A THREAT (confirmed).
**What it does.** Compares its own TAWP variants and unbalanced penalization on MIS/MDKP.
**What it does not do.** Explicitly states it does **not** compare against slack-based encoding, citing the comparison as "already... in [21]" (i.e., deferring to Montañez-Barrera 2211.13914). Penalties tuned once per fixed problem size, not swept. Uses CPLEX as reference, not certified exact.

---

### Thermodynamic QUBO encoding significance paper

**Year:** 2026 · **DOI/arXiv:** arXiv:2601.04402
**Threat classification:** NOT A THREAT (confirmed).
**What it does.** Sweeps a two-parameter penalty family.
**What it does not do.** Confirmed to be **one encoding scheme** parameterized two ways, not two distinct encodings compared against each other — fails the "two encodings" requirement at the definitional level.

---

### Constrained Markowitz portfolio via slack-ancilla QAOA vs. uniform-penalty QAOA

**Year:** 2025 · **DOI/arXiv:** arXiv:2601.03278 (also associated with a Springer *Quantum Machine Intelligence* venue per search notes — venue not independently confirmed, `CANNOT VERIFY`)
**Threat classification:** PARTIAL THREAT.
**What it does.** Slack-ancilla QAOA vs. uniform-penalty QAOA on a portfolio instance, $n=3, K=1$ (toy scale), validated by exhaustive enumeration — the only portfolio-specific paper found combining an encoding comparison with certified exact ground truth.
**What it does not do.** Single constraint, single coefficient (adaptively increased during the run, not swept over a fixed range), one comparison, trivial instance scale.
**Confidence.** Found via search-result synthesis; not independently confirmed against the full primary PDF — `CANNOT VERIFY` beyond the summary-level description.

---

### Evaluation of Sensitivity Analysis of Penalty Weights in QUBO

**Author (as recorded in our search notes):** Jiajie Liu
**Year:** 2025
**Venue:** ACM (conference/proceedings not separately recorded)
**DOI / arXiv:** DOI 10.1145/3712255.3734285
**Role in our scoping process:** The single highest-priority unresolved item across the entire scoping process.
**Threat classification:** **UNRESOLVED — CANNOT VERIFY.**

**Status.** This paper's title is a near-exact match to the surviving research question (penalty-weight sensitivity). It was flagged as paywalled and inaccessible in **two separate search passes** (the original four-fork audit and the dedicated kill-shot search), and was never read at any level beyond its title and DOI. It remains completely unresolved.

**Important discrepancy to flag explicitly:** the instruction that requested this document referenced this item as **"Liu & Moraglio 2025"** and a separate **"Liu & Moraglio 2026 penalty-sensitivity work."** Our actual search records contain only the single item above, attributed to a single author ("Jiajie Liu"), with no second author and no second, separately-dated paper. This record preserves what was **actually found and verified** during this project's search passes, per this document's own anti-fabrication instructions (§27–28) — it does not add an author or a second paper that our search process did not independently confirm. If a "Liu & Moraglio" paper exists and is different from, or additional to, the item above, it was not part of this project's literature search and should be added as new evidence, not retroactively merged into this record.

**Evidence.** None beyond title and DOI — access blocked (403) on every attempt.

---

### Systematic Data-Driven Penalty Calibration for Constrained Quantum Optimization with Application to Molecular Docking

**Year:** 2026 · **Venue:** bioRxiv preprint
**Threat classification:** UNRESOLVED — CANNOT VERIFY.
**Status.** Title suggests systematic multi-constraint calibration in a molecular-docking domain. Blocked (403) on the one access attempt; not independently curled or re-attempted. Domain is far enough from this project's own that even if resolved, it is expected to be low-priority — but this expectation is itself unverified.

---

### Quadratic versus Polynomial Unconstrained Binary Models (railway timetabling)

**Year:** Not confirmed · **DOI/arXiv:** arXiv:2411.10062
**Threat classification:** UNRESOLVED — CANNOT VERIFY.
**Status.** Title directly suggests a two-formulation comparison. PDF extraction failed entirely during the kill-shot pass — no content beyond the title was obtained. Explicitly flagged, not dismissed, in the kill-shot report.

---

### Structure-Aware Penalty Weights Scaling for QUBO

**Year:** 2026 · **Venue:** Springer book chapter (title-level only)
**Threat classification:** UNRESOLVED — CANNOT VERIFY.
**Status.** Automatic per-constraint penalty scaling from structural features is described at the search-snippet level only; never independently fetched. Not confirmed to involve any comparison across a swept range — status is genuinely unknown, not merely unread in depth.

---

### Feasibility-driven QAOA with penalty scheduling (Λ-lr-QAOA)

**Year:** 2026 · **DOI/arXiv:** arXiv:2606.25117
**Threat classification:** METHODOLOGICAL THREAT (motivational, not empirical).
**What it does.** Introduces an independent per-constraint penalty schedule $\Lambda_k$, jointly optimized as trained variational parameters rather than external hyperparameters. Confirmed via direct text fetch.
**What it does not do.** Does not grid-sweep or map a robustness region — it learns one good configuration via gradient-based training. No exhaustive/exact ground truth found. No portfolio.
**What it contributed to our final framing.** Raised, and forced an explicit answer to, the reviewer objection "doesn't automated penalty optimization make manual robustness mapping obsolete?" (§22).

---

### Evaluating the solution performance of the augmented Lagrangian function — companion note on the sparsest k-subgraph paper

**Year:** 2025 · **DOI/arXiv:** arXiv:2509.08544
**Threat classification:** PARTIAL THREAT, unresolved depth.
**What it does.** Introduces quadratic penalty, Lagrangian relaxation, and augmented Lagrangian relaxation together for a sparsest-k-subgraph problem, with theoretical (not necessarily empirical) parameter-sensitivity characterization.
**What it does not do / what's unconfirmed.** Abstract-level evidence only — an empirical cross-method sweep comparison was not confirmed.

---

### Screened but not threatening

The following were checked at least at search-summary level and judged not to bear materially on the final scope, without a full dedicated entry above: "Approaching Collateral Optimization for NISQ and Quantum-Inspired Computing" (arXiv:2305.16395 — finance-adjacent but not portfolio, not independently verified in depth); three additional recent portfolio-QUBO preprints flagged for triage but never read even at abstract level due to time constraints — arXiv:2508.13557 ("sampling-based variational quantum scheme" for portfolio), arXiv:2511.21305 ("Pauli Correlation Encoding" for large-scale portfolio), arXiv:2503.13544 ("robust portfolio optimization framework," likely classical, not quantum). All three remain genuinely untriaged, not "screened and cleared" — recorded here as unresolved, not as evidence of absence.

---

## 8. Papers That Killed Our Original Novelty Claims

### "No prior work compares slack and unbalanced" → FALSE
**What we thought:** This was the starting-point framing implicit in the original audit brief.
**What we found:** Montañez-Barrera et al. 2024 (arXiv:2211.13914) does exactly this on TSP/BPP/KP, verified via direct primary-text read (Table 1). Montañez-Barrera et al. 2023 (arXiv:2305.18757) does the same on TSP against CPLEX. An unresolved-provenance GitHub repository does the same specifically on a 2-constraint portfolio QUBO.
**Why the claim was abandoned:** Directly, primarily-verified contradicting evidence in the paper's own author's prior work. This was not a marginal or ambiguous case.

### "No prior work sweeps multiple penalty coefficients" → FALSE, but narrowly
**What we thought:** Candidate 4, that no prior work jointly varies 3+ independent coefficients against certified ground truth.
**What we found:** Mattesi et al. sweeps exactly 3 independent coefficients in a portfolio QUBO (§5.4, Fig. 2) — but against a **heuristic** solver (PyPortfolioOpt), not certified ground truth.
**Why the claim was narrowed, not fully abandoned:** The bare claim ("3+ coefficients swept in portfolio") is false; the conjunction with certified ground truth survives, because Mattesi et al. explicitly lacks that ingredient. This is the reason "against certified exact optima" became a load-bearing, non-droppable conjunct in the final claim rather than a nice-to-have.

### "No prior work uses certified exact ground truth in this general class" → TOO BROAD
**What we thought:** An implicit assumption that exact/certified ground truth itself was a scarce, novel ingredient in portfolio QUBO work.
**What we found:** Stopfer & Wagner (arXiv:2509.17876) use Gurobi-proven-optimal (0% gap) ground truth at real scale (up to 1000 assets, classically) — verified via direct text fetch of their §5, eq. 24.
**Why the claim was abandoned:** Certified ground truth in portfolio QUBO is not itself scarce or novel; what remains scarce is certified ground truth *combined with* an encoding comparison and a swept range, which Stopfer & Wagner do not supply (they use one fixed penalty pair and no encoding comparison at all).

### "No prior work compares encodings across penalty space" → UNSAFE AFTER KIKUCHI ET AL.
**What we thought:** After the first three corrections above, the working claim narrowed to "no prior work has ever compared two QUBO encodings while sweeping a penalty range," treated as a domain-agnostic methodological novelty.
**What we found:** Kikuchi, Takahashi & Tanaka (arXiv:2410.11198) do exactly this — domain-wall vs. one-hot encoding, plotted against a swept $\lambda$, Fig. 2 and Table I, verified via two independent direct text fetches.
**Why the claim was narrowed, not fully abandoned:** Kikuchi et al.'s "two encodings" are a variable-binarization choice (domain-wall vs. one-hot), not a constraint-encoding choice (slack vs. unbalanced/Lagrangian). The claim survives only when explicitly restricted to the constraint-encoding family this project actually studies — this restriction is not a rhetorical trick, it reflects a real structural difference between the two kinds of "encoding," and this document's final research question (§25) states that restriction explicitly rather than leaving it implicit.

**Standing instruction for future work on this project:** none of the four claims above may be used in their original, broad form in any future paper draft. Each has a documented, verified counterexample. See §23 for the exact forbidden-claims list.

---

## 9. The Most Important Prior-Art Papers — Comparison Table

| Paper | Encoding comparison | Penalty sweep | Joint multi-parameter sweep | Exact/certified ground truth | Portfolio | Heterogeneous constraints | What remains missing |
|---|---|---|---|---|---|---|---|
| Montañez-Barrera et al. 2024 (2211.13914) | Yes (slack vs. unbalanced) | No (single point) | No | No (annealer/QAOA output, not certified) | No | No | Sweep, portfolio, certified truth |
| Montañez-Barrera et al. 2023 (2305.18757) | Yes (slack vs. unbalanced) | No (single point) | No | Partial (CPLEX, size-limited) | No | No | Sweep, portfolio, scale-general certified truth |
| `alejomonbar` portfolio repo | Yes (slack vs. unbalanced) | Unconfirmed | Unconfirmed | Unconfirmed (docplex, unverified) | Yes (2 constraints) | Partial (2 of 3) | Confirmed publication, sweep, full constraint set |
| Stopfer & Wagner 2025 (2509.17876) | No | No (fixed) | No | Yes (Gurobi, proven optimal) | Yes | No (no cardinality/sector) | Encoding comparison, sweep, full constraint set |
| Mattesi et al. (2302.12291) | No | Yes (3 coefficients) | Yes | No (PyPortfolioOpt, heuristic) | Yes | Partial (soft diversification, no hard sector cap) | Encoding comparison, certified truth |
| Güney, Ehrenthal & Hanne 2025 | No (slack only) | Yes (1-D, shared coefficient) | No | Near-certified (Gurobi, time-limited) | No | Partial (multiple constraints, one shared coefficient) | Encoding comparison, independent multi-coefficient sweep, portfolio |
| Awai et al. 2026 (2606.24241) | No (PF vs. ALF, both slack-based) | Yes (2-D, $\mu,\lambda$) | Yes | Yes (known-optimal QKP benchmarks) | No | No | Not the studied encoding pair at all — see §11 |
| Kikuchi et al. 2024 (2410.11198) | Yes (domain-wall vs. one-hot) | Yes (1-D) | No | Unconfirmed | No | No | Right pattern, wrong encoding family, wrong domain |
| Jiajie Liu, ACM (2025) | Unknown | Unknown | Unknown | Unknown | Unknown | Unknown | Entirely unresolved — paywalled throughout |
| Markowitz-slack QAOA (2601.03278) | Yes | No (adaptive, not ranged) | No | Yes (exhaustive, toy scale) | Yes | No (single constraint) | Scale, sweep, full constraint set |
| Chang et al. 2000 | N/A (pre-QUBO) | N/A | N/A | No (heuristic-vs-heuristic, medium confidence) | Yes | Partial (cardinality only) | Not QUBO-relevant; low threat |
| "Exact algorithm, small-cardinality portfolio" | Unknown | Unknown | Unknown | Possibly yes | Yes | Unknown | **Entirely unresolved — never located** |
| "Structure-Aware Penalty Weights Scaling" (Springer 2026) | Unknown | Unknown | Unknown | Unknown | Unknown | Unknown | Entirely unresolved |

No row in this table has more than three of the seven columns filled affirmatively. No row combines an encoding comparison, a genuine multidimensional sweep, and certified ground truth, in portfolio, with heterogeneous constraints. This table is the empirical basis for the final novelty claim in §23.

---

## 10. Unresolved / Failed Search Paths

### Jiajie Liu, "Evaluation of Sensitivity Analysis of Penalty Weights in QUBO" (ACM)
**Why did it look dangerous?** Title is a near-exact match to the surviving research question.
**What did we eventually determine?** Nothing — paywalled and inaccessible across two independent search passes.
**Confidence remaining:** Zero information beyond title and DOI. **This is the single highest-priority item to resolve before any paper draft is written**, not before implementation (implementation does not depend on this paper's contents, but the final novelty claim's safety does).

### "An exact algorithm for small-cardinality constrained portfolio optimisation"
**Why did it look dangerous?** Could supply exactly the certified-ground-truth-in-cardinality-constrained-portfolio precedent this project relies on being scarce.
**What did we eventually determine?** Author, year, and venue were never confirmed; the paper itself was never located or read.
**Confidence remaining:** Zero. Flagged as potentially more dangerous than Chang et al. itself.

### bioRxiv molecular-docking penalty-calibration paper
**Why did it look dangerous?** Title suggests systematic multi-constraint penalty calibration.
**What did we eventually determine?** Blocked on the one access attempt; domain (molecular docking) makes it lower expected priority, but this is an untested expectation, not a finding.
**Confidence remaining:** Zero beyond title.

### arXiv:2411.10062, railway timetabling formulation comparison
**Why did it look dangerous?** Title directly suggests a two-formulation comparison in a non-portfolio domain — exactly the kill-shot search's target pattern.
**What did we eventually determine?** PDF extraction failed entirely during the kill-shot pass; no content beyond the title was obtained.
**Confidence remaining:** Zero beyond title.

### "Structure-Aware Penalty Weights Scaling for QUBO" (Springer, 2026)
**Why did it look dangerous?** Automatic per-constraint scaling sounds adjacent to multidimensional penalty characterization.
**What did we eventually determine?** Search-snippet level only, never fetched.
**Confidence remaining:** Zero beyond title; genuinely unknown whether it involves any comparison at all.

### The "K=10 assets, sector cap ≤3" search result
**Why did it look dangerous?** Nearly matched this project's own penalty-term structure, described in language suggesting a specific published example.
**What did we eventually determine?** No specific paper title could be traced to it despite repeated follow-up queries; one ScienceDirect fetch involved 403'd. Judged to be search-tool paraphrase of generic tutorial content, not a real, distinct citation.
**Confidence remaining:** Explicitly excluded from the evidence base — recorded here specifically so a future reader does not mistake its absence from §7/§9 for an oversight. It was investigated and deliberately not counted.

### Domains never actually searched
Job-shop scheduling and rostering were named as target domains in the original audit brief's own instructions but were not, in fact, searched in any pass. This is an acknowledged gap, not a "screened, found nothing" result — the correct language for these domains is "not searched," never "no threat found."

### Awai et al. (2606.24241) — a cleared, not merely unresolved, initial threat
Included here for completeness even though it was ultimately resolved (§4.6, §11), because the process of clearing it illustrates the document's own methodology: it was *not* cleared by further searching, but by direct algebraic derivation from the primary text. A future reader should not re-flag this paper as a threat without re-reading §11 first.

---

## 11. The ALF vs. Unbalanced Algebraic Analysis

This section is a self-contained technical record of a derivation performed directly against the primary texts (both PDFs read in full). Statements are explicitly separated into **[PAPER STATES]** (taken directly from the source text) and **[DERIVED]** (worked out in this project from the papers' own equations, not stated by either paper).

### Common notation
Let the inequality constraint be $\sum_i w_i x_i \le W$, and define the signed residual $h(x) = W - \sum_i w_i x_i$ ($\ge 0 \iff$ feasible). This notation is consistent across both source papers' underlying meaning, though each paper uses different symbols.

### Slack (baseline shared by both source papers)
Both papers build their baseline on the same mechanism: auxiliary binary bits encoding a register $S=\sum_d 2^d y_d \in [0,2^D-1]$, $D=\lceil\log_2(W+1)\rceil$, penalizing the equality residual:

$$\lambda_S(h(x)-S)^2 \quad \textbf{[PAPER STATES — Montañez-Barrera eq. 8]}$$

Awai et al.'s $H_\text{const}$ (their eq. 16) is confirmed **[DERIVED]** to be an affine reparametrization ($S' = (2^D-1)-S$) of the same slack register, i.e. their "Penalty Function" baseline (their eq. 17, $H_P=H_\text{obj}+\tfrac{\mu}{2}H_\text{const}^2$) is the same slack-variable family Montañez-Barrera compares unbalanced penalization against — **[PAPER STATES]** their own §3.1.2 explicitly describes this as "a slack variable... is introduced to convert the inequality constraint into an equality constraint," confirming this is standard slack encoding, not a new mechanism.

**[DERIVED]** Marginalizing $S$ over its full range for fixed $x$: for feasible $x$ there always exists $S=h(x)$ giving penalty exactly 0; for infeasible $x$ the best reachable is $S=0$, giving $\lambda_S h(x)^2$. So after optimizing out the auxiliary bits, slack's effective penalty is the piecewise (hinge-squared) function:
$$\text{Penalty}_\text{slack}(x) = 0 \text{ if } h(x)\ge0,\ \lambda_S h(x)^2 \text{ if } h(x)<0$$

### Unbalanced penalization
$$\zeta(x) = -\lambda_1 h(x) + \lambda_2 h(x)^2 \quad \textbf{[PAPER STATES — Montañez-Barrera eq. 25–26]}$$
No auxiliary variables at all. **[DERIVED]** A smooth parabola in $h(x)$, vertex at $h^*=\lambda_1/2\lambda_2$, minimum value $-\lambda_1^2/4\lambda_2$.

**[DERIVED]** A smooth quadratic can never equal a piecewise hinge-squared function (no polynomial reproduces a kink) — so unbalanced penalization is not a special case, generalization, or algebraic rearrangement of the slack penalty for any choice of $(\lambda_1,\lambda_2)$ vs. $\lambda_S$. This structural non-equivalence is a project-derived conclusion, not stated by either source paper.

### Awai et al.'s ALF
$$H_\text{AL} = H_\text{obj} + \tfrac{\mu}{2}H_\text{const}^2 - \lambda H_\text{const} \quad \textbf{[PAPER STATES — their eq. 18]}$$
Still contains $H_\text{const}=S-(2^D-1)+h(x)$ — the auxiliary slack register is retained. **[PAPER STATES]** their own §6.1 completes the square: $H_\text{AL}=H_\text{obj}+\tfrac{\mu}{2}(H_\text{const}-\lambda/\mu)^2-\lambda^2/2\mu$, i.e. the energy minimum shifts from $H_\text{const}=0$ to $H_\text{const}=\lambda/\mu$.

**[DERIVED]**, independently, and cross-checked against their own §6.1 discussion of "saturation": marginalizing $S$,
- **Feasible $x$:** $S$ has enough range to hit $H_\text{const}=\lambda/\mu$ exactly (when representable), giving a **constant** penalty $-\lambda^2/2\mu$ for every feasible $x$ — flat/agnostic across the whole feasible region, exactly like plain slack, just shifted.
- **Infeasible $x$:** the maximum reachable $H_\text{const}$ is $h(x)$ itself, at $S$ saturated to its maximum (**[PAPER STATES]** their own §6.1 discusses this saturation explicitly: "the auxiliary variables are driven to the saturated assignment $y_d=1$ for all $d$"). At that point the effective penalty collapses to $\tfrac{\mu}{2}h(x)^2-\lambda h(x)$ — **[DERIVED]** algebraically identical in form to unbalanced penalization with $\lambda_2\leftrightarrow\mu/2$, $\lambda_1\leftrightarrow\lambda$.

### Why ALF is not simply unbalanced penalization
**[DERIVED — this is the project's own conclusion, not stated by either paper]:**
1. **Auxiliary-variable structure:** ALF (like plain slack) requires $D=\lceil\log_2(W+1)\rceil$ auxiliary qubits per inequality; unbalanced requires zero.
2. **Feasible-region behavior:** ALF (converged) is flat/constant across all feasible states; unbalanced actively discriminates among feasible states based on distance from $h^*$.
3. **Infeasible-region behavior:** the two coincide in functional form **only** on this branch, and only under the idealized assumption that the solver has found the energy-minimizing auxiliary-bit assignment — an assumption ALF's own paper does not claim holds in practice for imperfect Ising-machine sampling (their entire paper is about measuring TT$\varepsilon$ under realistic, imperfect search dynamics).
4. **Variable-space differences:** ALF's Hamiltonian is defined jointly over $(x,y)$; unbalanced's is defined over $x$ alone.

**Why this distinction matters for the novelty claim:** without this derivation, a reviewer could plausibly (and incorrectly) claim "your unbalanced formulation is merely ALF under another name," which would threaten the entire encoding-distinctness premise of the project. This derivation exists specifically to preempt that objection with an explicit, checkable algebraic argument rather than an assertion.

### A secondary derived insight (explicitly a project contribution, not sourced from either paper)
A substantive modeling implication follows from combining this derivation with Montañez-Barrera's own Fig. 6 (feasible/infeasible energy-ordering not guaranteed for unbalanced): because unbalanced penalization does not guarantee feasible-beats-infeasible ordering, the certified-ground-truth check in this project's experimental design must explicitly verify the *feasibility* of the returned ground state under the unbalanced encoding, not merely compare objective values — slack does not need this extra check (guaranteed by construction), unbalanced does. This is incorporated into the frozen success-category definitions in §16.

---

## 12. Final Mathematical Problem

Source: taken directly from the existing prototype (`QDTRINITY_sTAGE_2` README/technical report, referenced in §3), not invented for scoping. Risk-aversion is renamed $\kappa_\text{risk}$ here for clarity relative to the encoding-parameterization $\kappa$ introduced in §14 — **note:** the Scope Lock document itself uses the plain symbol $\kappa$ for both the risk-aversion coefficient (§B of that document) and the unbalanced-penalization decay-rate parameter (§H); this record disambiguates them explicitly as $\kappa_\text{risk}$ and $\kappa_\text{penalty}$ respectively to avoid the exact collision that was flagged as a real risk during scoping.

$$x \in \{0,1\}^{20} \text{ (one bit per asset)}$$
$$f(x) = -\mu^Tx + \kappa_\text{risk}\cdot x^T\Sigma x \quad \text{(minimize)}$$
$$\text{cardinality (equality):} \sum_i x_i = K,\ K=6$$
$$\text{sector caps (4 inequalities):} n_j(x)=\sum_{i\in\text{sector }j}x_i \le C,\ C=2,\ j=1..4$$
$$\text{budget (inequality):} p^Tx \le B,\ B=1100$$
$$F = \{x\in\{0,1\}^{20} : \text{all three constraint families hold}\}$$
$$x^* = \arg\min_{x\in F} f(x) \text{ — certified by exhaustive enumeration over } C(20,6)=38{,}760 \text{ cardinality-feasible portfolios}$$

**Missing item, explicitly not assumed:** individual per-stock prices $p_i$ and the exact numeric values of $\mu, \Sigma, \kappa_\text{risk}$ live in the prototype's data files (`mu.csv`, `Sigma.csv`) but were not reproduced or re-derived during scoping. **NOT YET FIXED** — pulling these is an implementation-phase task (§26).

**The two distinct exact objects, kept separate throughout:**
$$x^* = \arg\min_{x\in F} f(x) \quad \text{(original-problem optimum)}$$
$$z^*_E(\lambda) = \arg\min_z Q_E(z;\lambda) \quad \text{(encoded-QUBO ground state, per encoding } E \text{ and per penalty vector } \lambda\text{)}$$

The scientific question throughout is whether decoding $z^*_E(\lambda)$ recovers $x^*$ — checked, never assumed, at every grid point and every encoding independently.

---

## 13. Exact Encodings

### Slack encoding
Cardinality (equality) uses the ordinary quadratic penalty $\alpha(\sum x_i - K)^2$ in **both** encodings — no auxiliary variables are ever used for equality constraints in either formulation (this follows from Montañez-Barrera's own eq. 5/9, not a choice available to us).

Per inequality constraint with residual $h(x)$: auxiliary register $S=\sum_d 2^d y_d$, $N=\lceil\log_2(\max_x h(x))+1\rceil$ bits (per Montañez-Barrera's own eq. 7):
$$\lambda_S(h(x)-S)^2$$

**Auxiliary-bit count, computed from the prototype's own bound values (§12), not invented:**
- Sector cap: $N=\lfloor\log_2(2)+1\rfloor=2$ bits per sector × 4 sectors = **8 bits**.
- Budget: $N=\lfloor\log_2(1100)+1\rfloor=11$ bits (using $B=1100$ from the prototype; this bound calculation does not require individual $p_i$ values).
- **Total: 19 auxiliary bits.** Total slack QUBO variables: 20 (x) + 19 (auxiliary) = **39**.

### Unbalanced encoding
Per inequality: $\zeta(x)=-\lambda_1 h(x)+\lambda_2 h(x)^2$, no auxiliary variables. Cardinality uses the same equality penalty as slack. Total unbalanced QUBO variables: **20** (equal to the original problem's variable count — no auxiliary overhead at all).

---

## 14. Penalty Parameterization Decision

### Original problem
Slack needs exactly one free scalar per inequality ($\lambda_S$); unbalanced naturally needs two ($\lambda_1,\lambda_2$) per inequality. A literal shared 3-vector $\lambda=(\alpha,\beta,\gamma)$ applied identically to both encodings is not achievable without a reduction rule.

### Initial proposal
$$\lambda_1=\kappa,\quad \lambda_2=\kappa^2/2$$
motivated by Montañez-Barrera's own Taylor expansion of $e^{-\kappa h(x)}$ (their eq. 24).

### Why this family was retained
It is the construction actually used in the source method (Montañez-Barrera et al. 2024) — a reviewer will recognize it as "actually unbalanced penalization," not a bespoke invented variant. Two alternatives were explicitly considered and rejected as the primary family: a fixed-curvature family ($\lambda_2=c\kappa$, giving a κ-independent reward location but departing from the paper's own derivation) and treating $(\lambda_1,\lambda_2)$ fully independently (rejected as Design 3, §6 of the κ-decision session — roughly doubles unbalanced's grid dimensionality without actually avoiding the matching problem, only deferring it to analysis time).

### Why naive value equality was rejected
Completing the square, $P_\kappa(h)=\tfrac{\kappa^2}{2}(h-1/\kappa)^2-\tfrac12$: the reward minimum sits at $h^*=1/\kappa$ with **constant depth $-1/2$ regardless of $\kappa$** — so $\kappa$ is a decay-rate/length-scale parameter, not a pure strength multiplier the way $\lambda_S$ is. Under the naive curvature-matching rule ($\lambda_S=\kappa^2/2$):
$$P_\kappa(-v) - P_\text{slack}(-v) = \kappa v + \tfrac{\kappa^2}2 v^2 - \tfrac{\kappa^2}2 v^2 = \kappa v > 0 \quad \text{for all } \kappa,v>0$$
Unbalanced is **always** penalized more heavily than slack at every matched violation point, purely as an artifact of discarding the linear term — a provable, directional bias that would make unbalanced look artificially more resistant to infeasible ground states (Category C, §16) than a fairer comparison would show. Six candidate matching rules total were checked (curvature match, point match at a reference violation, worst-case match, boundary-slope match, objective-scale match); boundary-slope matching is provably impossible (slack's slope at $h=0$ is always exactly 0; unbalanced's is always $-\kappa\ne0$), confirming no single rule preserves every feature of both shapes simultaneously.

### Final normalization (frozen)
$$v_\text{ref}=1 \text{ (smallest nonzero integer violation — all three constraint residuals in this problem are integer-valued)}$$
$$\Lambda_\text{ref} = \text{range (or std) of } f(x) \text{ over the 38,760-portfolio feasible set (computable now, no new data needed)}$$
$$\lambda_S(s) = s\cdot\Lambda_\text{ref}/v_\text{ref}^2, \qquad \kappa(s) = s\cdot\Lambda_\text{ref}/v_\text{ref}$$

$s$ — not $\lambda_S$ or $\kappa$ directly — is the swept quantity, log-spaced. Bounds on $s$: **NOT YET FIXED numerically** — the *principle* (comfortably-non-enforcing to comfortably-enforcing, relative to $\Lambda_\text{ref}$) is frozen; the numeric bounds are an implementation-time task. A domain-expansion robustness check (0.5×/2× the chosen box) is required once the box is fixed. A **bounded sensitivity check** using the rejected curvature-match rule ($\lambda_S=\kappa^2/2$, on a coarse subgrid, not the full grid) is a required companion to the primary sweep, to confirm the qualitative rank-stability conclusion does not flip under the alternate, known-biased anchor.

**There is no unique canonical mapping between the two encodings' penalty parameter spaces.** This is stated explicitly, not glossed over: every claim from this experiment is therefore conditional on the chosen dimension-matched, objective-normalized parameterization above, and must be phrased as such in any future write-up (see the forbidden/required phrasing in §23).

---

## 15. Exact Ground-State Certification

**Why naive slack enumeration is $2^{39}$:** 20 original asset bits + 19 auxiliary slack bits (§13) = 39 total binary variables, giving a naive search space of $2^{39}\approx5.5\times10^{11}$ states — not tractable to brute-force across a multi-point penalty grid.

**Why fixing $x$ makes each slack register independently convex:** for fixed $x$, every slack penalty term $\lambda_S(h(x)-S)^2$ is a convex quadratic in its own independent auxiliary register, with **no cross-terms** between different constraints' registers (cardinality has no auxiliary register at all; sector and budget each have their own, separate, non-interacting register).

**Closed-form auxiliary minimization:** because $S$ is restricted to non-negative integers representable in $N$ bits, the energy-minimizing setting for fixed $x$ is $S^*=\text{clamp}(\text{round}(h(x)), 0, 2^N-1)$ — an $O(1)$ computation (a handful of arithmetic operations, negligible against $N$ bit-conversion cost) per constraint, not a search.

**Why exact certification reduces to $2^{20}$ configurations:** because the total slack energy for fixed $x$ decomposes additively across independent constraint terms (cardinality: $x$ only; each sector: own $S_j$; budget: own $S$), the joint minimization over all auxiliary bits decomposes into independent per-constraint $O(1)$ minimizations. Total work: enumerate the $2^{20}\approx1{,}048{,}576$ possible $x$-configurations (identical in cost to the *unbalanced* encoding's full search space, since unbalanced has no auxiliary variables at all), and at each, close-form-minimize the auxiliary registers.

**Why this applies to every penalty-grid point:** the closed-form minimization is a function only of $h(x)$ and the bit-count bound $N$ (fixed by the problem, not by the penalty coefficients) — it does not need to be re-derived per grid point, only re-evaluated, so the $O(2^{20})$ cost is paid once per $(x,\text{encoding})$ combination and the penalty-coefficient dependence enters only in the final energy sum, not in the search structure.

**Complexity summary:** both encodings' exact ground states are certifiable at identical computational order ($O(2^{20})$), fully tractable on commodity hardware — this is a project-derived computational method, not something either source paper describes, and directly resolves the practicality concern about whether the 20-asset instance remains computationally viable for exact QUBO-level (not just original-problem-level) certification.

---

## 16. Success Categories and Tie Rule

**A — exact:** decoded portfolio $\in F$ and $f(\text{decoded}) = f(x^*)$.
**B — feasible, suboptimal:** decoded portfolio $\in F$, objective $\ne f(x^*)$.
**C — infeasible ground state:** decoded portfolio violates a constraint.

**Why B and C must never be merged:** collapsing them into a single "objective gap" metric would hide exactly the asymmetry established in §11 (Montañez-Barrera's own Fig. 6: unbalanced does not guarantee feasible-beats-infeasible energy ordering; slack does, by construction). Only unbalanced can produce Category C at all by construction under sufficiently large penalty coefficients — a reviewer must be able to see whether a failure was "wrong answer, still a portfolio" (B) or "not a portfolio at all" (C), since these have entirely different causes and different implications for practical deployment.

**Degeneracy rule:** ties in the auxiliary register (multiple slack-bit patterns achieving the same minimal penalty for the same $x$) are not decision-relevant — decoding only reads the $x$-bits, so they collapse to a single decoded portfolio automatically and require no special handling. Genuine ties are only possible at the $x$-level (two distinct portfolios tied for the global QUBO minimum) — expected to be rare with continuous-valued $\mu,\Sigma$ but must be checked computationally at every grid point, at zero extra cost (a byproduct of the $O(2^{20})$ pass in §15), not assumed away.

**Frozen rule:** a grid point is classified A only if **every** tied global ground state decodes to a feasible-optimal portfolio, not merely at least one. The tie fraction is reported as a diagnostic, never as partial credit toward A. This is the scientifically conservative choice, deliberately avoiding overclaiming success when an encoding merely "sometimes" finds the right answer among tied ground states.

---

## 17. Metrics

**Primary:** exact-optimum recovery rate, $\rho_E^\text{exact} = |\{\text{grid points classified A}\}|/|\Lambda|$. Chosen because it is the metric most directly tied to the locked research question (rank stability of exact-recovery, not of some looser notion of "quality").

**Secondary, and why each exists:**
- Feasibility rate (A∪B) — separates "does the encoding stay inside the feasible region at all" from "does it find the optimum within that region."
- Feasible-but-suboptimal rate (B alone) — isolates a distinct failure mode from infeasibility (§16).
- Infeasible-ground-state rate (C alone) — the metric directly motivated by the asymmetry derived in §11; central to Hypothesis H2 (§20).
- Robustness-region geometry (shape, not just size) — the scope-lock document explicitly rejects stopping at a scalar fraction; shape and relative location of regions is the primary object of interest, not merely an average score.
- Connectedness — distinguishes a single contiguous "good" region from a fragmented/scattered one, which would itself be a notable structural finding.
- Qubit/variable overhead (20 for unbalanced vs. 39 for slack, §13) — the standard motivation cited for unbalanced penalization in the literature (qubit savings); reporting it alongside robustness lets the paper address whether that savings comes with a robustness cost.
- Tie fraction — diagnostic for the degeneracy rule (§16), not a scored outcome.
- Parameter-sensitivity diagnostics — supports the bounded sensitivity check required in §14.

---

## 18. Experimental Design

**Stage 1 (required):** the existing canonical 20-asset/K=6 instance — already built, exact, fully enumerable.

**Stage 2 (required before claiming "robustness" rather than "one instance's behavior"):** 4–6 additional instances varying the return/covariance draw and sector assignment, holding 20 assets/K=6 fixed so the exact-enumeration budget (§15) does not change.

**Precommitted, fixed-before-results choices:**
- Joint grid over the shared dimensionless $s$ (§14), not one-parameter-at-a-time sweeps.
- Log spacing (linear spacing over-samples the "too strong" region and under-samples the interesting feasibility-transition region).
- The 0.5×/2× domain-expansion check.
- The bounded curvature-match sensitivity pass (§14).
- The strict all-ties-must-be-A degeneracy rule (§16).
- The A/B/C classification scheme, kept separate throughout (§16).

**Constraint ablations (from the original specification-lock session, §14 of that document — carried forward here unmodified):** cardinality-only, cardinality+budget, cardinality+sector, cardinality+sector+budget, to test Hypothesis H3. **The exact minimum useful subset of these ablations was not finally pinned down during scoping** — this remains an implementation-phase judgment call, to be made only if Stage 1/2 results are ambiguous, per the original scope-lock design principle of not inflating the study preemptively.

---

## 19. Stage-2 Instance Generation Protocol

**Random seed policy:** **NOT YET FIXED.** The scope-lock document requires this be fixed "before running anything, so it isn't chosen post hoc to favor a result" (its own §J/§R), but no specific seed value or seeding library/method was chosen during scoping.

**How $\mu$ and $\Sigma$ are generated/resampled:** **NOT YET FIXED** in exact algorithmic detail. The principle established is "resample with a fixed random seed protocol," varying the return/covariance draw — the exact resampling distribution or method (e.g., bootstrap from historical data vs. parametric resampling) was not specified.

**How sector assignments are generated:** **NOT YET FIXED.** The principle is "vary sector assignment" as part of the Stage 2 family; the exact reassignment algorithm (e.g., random permutation vs. structured reshuffling) was not specified.

**Which quantities remain fixed:** 20 assets, K=6 — explicitly fixed across all Stage 2 instances so the exact-enumeration computational budget from §15 does not change.

**How feasibility is ensured:** **NOT YET FIXED** — no explicit rejection-sampling or repair procedure for ensuring each generated Stage 2 instance has a non-degenerate, well-posed feasible region was specified during scoping.

**How many instances:** 4–6, per the original scope-lock proposal (§J of that document) — described as "the minimum needed to distinguish 'a property of the encodings' from 'a property of one hand-picked instance,' without inflating scope."

**Whether the random generation was specified before seeing results:** Yes in principle (this is a stated design requirement, §R item 5 of the scope-lock document: "so it isn't chosen post hoc to favor a result") but **the protocol itself is not yet concretely specified**, so this requirement is currently a commitment, not yet an executed fact. This must be resolved and written down *before* Stage 2 instances are generated, not after.

---

## 20. Hypotheses

**H0 (null, rank stability):** $\rho_\text{unbalanced}^\text{exact}(\Lambda) \approx \rho_\text{slack}^\text{exact}(\Lambda)$ and the pointwise A/B/C classification never flips ranking across $\Lambda$.
*Rationale:* the natural null against which any claimed instability must be measured.
*Supported by:* comparable recovery rates and no rank flip anywhere in the sampled grid.
*Falsified by:* a systematic, direction-consistent gap, or a rank flip anywhere in $\Lambda$.

**H1 (rank instability):** there exist sub-regions of $\Lambda$ where slack achieves A more often than unbalanced, and other sub-regions where the reverse holds.
*Rationale:* directly motivated by the observation (§4.3, §8) that every prior comparison uses single-point calibration and never checks this.
*Supported by:* a confirmed, characterizable crossover in the grid.
*Falsified by:* one encoding weakly dominating across the entire sampled $\Lambda$.

**H2 (infeasibility asymmetry, mechanistic):** Category C occurs measurably more often for unbalanced than slack across $\Lambda$.
*Rationale:* directly motivated by the algebraic derivation in §11 and Montañez-Barrera's own Fig. 6 (non-guaranteed feasible/infeasible energy ordering for unbalanced; guaranteed for slack).
*Supported by:* a statistically/practically significant, direction-consistent gap in C-rate favoring slack.
*Falsified by:* statistically indistinguishable C-rates, or slack showing higher C-rates than unbalanced.

**H3 (constraint heterogeneity):** the shape of the robustness region $R_E$ depends on which constraint types are active (cardinality-only vs. +sector vs. +budget vs. all three).
*Rationale:* directly motivated by Güney et al.'s finding that even multiple simultaneous constraints were treated with one shared coefficient in prior work — never tested for independent, heterogeneous constraint types.
*Supported by:* region geometry that meaningfully reshapes (not merely rescales) as constraints are added.
*Falsified by:* region geometry that only rescales, never reshapes.

---

## 21. What Counts as a Useful Result

These are **predefined interpretation classes, fixed before any experiment is run** — not post-hoc characterizations of whatever the data happens to show.

**Weak:** one encoding wins on the single Stage 1 instance at one chosen penalty point. Explicitly insufficient — this is exactly the pattern already published (Montañez-Barrera, the portfolio repo) and does not advance the locked research question.

**Interesting negative:** both encodings are essentially equivalent in exact-recovery rate despite the qubit-count difference (20 vs. 39, §13) — a genuine, citable finding given the field's stated motivation for unbalanced penalization is qubit savings, not robustness; this result would show that savings comes at no measured robustness cost, or conversely.

**Interesting positive:** one encoding has a substantially and consistently larger $R_E^\text{exact}$ across both Stage 1 and Stage 2.

**Interesting structural result:** H1 is confirmed — the winner changes across identifiable sub-regions of $\Lambda$, and the boundary is characterizable (ties directly to H3).

---

## 22. Reviewer Objections

| Objection | Answer |
|---|---|
| Isn't this just Montañez-Barrera + portfolio? | No — their method tunes each encoding to one calibrated point (verified, their Table 1) and never portfolio; this tests whether that single-point comparison generalizes, which their methodology cannot answer by construction. |
| Isn't unbalanced just ALF? | No — §11, algebraically resolved: different variable spaces, different feasible-region behavior (flat vs. non-flat), coincide only in an idealized infeasible-branch limit under saturated auxiliaries. |
| Why does a sweep constitute research? | The sweep is the instrument, not the result; the result is whether a previously single-point comparison's conclusion is calibration-dependent, motivated directly by Montañez-Barrera's own Fig. 6. |
| Why care about one 20-asset instance? | It's the largest instance where both encodings' actual QUBO ground states (not just the original optimum) are exactly certifiable at tractable cost (§15) — larger instances force solver-gap-bounded truth (as in Stopfer & Wagner), reintroducing exactly the ambiguity this design avoids. Generalization is addressed, not assumed, via Stage 2 (§19) — **though the Stage 2 protocol itself is not yet fully specified**, which is itself a live scope risk (§19). |
| Why three coefficients? | They correspond to three structurally different constraint types (one equality, two inequalities of different tightness) — testing whether robustness is uniform across constraint types (H3), not a count-padding exercise. |
| Why does the chosen range matter? | Addressed by the κ-normalized, log-spaced, objective-scale-derived domain (§14) plus a fixed domain-expansion robustness check — not an arbitrary box. Numeric bounds are still **NOT YET FIXED**, which weakens this answer until they are. |
| Doesn't auto-tuning make this obsolete? | Auto-tuners (ALM, Λ-lr-QAOA — arXiv:2606.25117) converge to one good configuration per encoding; they don't test whether the ranking between two encoding families is stable to that choice — this study audits exactly that implicit assumption. |
| Does it generalize beyond the instance? | Not claimed beyond the Stage 1/2 family — explicitly flagged as the weakest point in the design, only partially mitigated by Stage 2, whose exact protocol remains unfixed (§19). |
| What about infeasible unbalanced ground states? | Tracked as Category C, kept separate from B (§16) — this is H2, not hidden in an aggregate metric. |
| What's actually new vs. known ingredients? | No source in §9's table supplies more than three of the seven relevant columns — the combination answers a previously untested question (rank stability under a swept, dimension-matched landscape), which is the honest basis of the claim, not novelty-by-combination for its own sake. |

---

## 23. Final Novelty Claim

### Conservative wording (chosen in the Scope Lock document, §N Version A)
An exact, enumeration-certified comparison of feasible-optimal recovery rates for slack and unbalanced QUBO encodings across a joint, dimension-matched penalty grid, on an instance with three heterogeneous simultaneous constraints — a combination not found in the searched literature. Does not claim: first comparison, first sweep, first certified benchmark, first portfolio QUBO.

### Normal paper wording (current research-question framing, Scope Lock §N Version B)
Whether the reported superiority of unbalanced penalization over slack — established only at single, separately-tuned points in prior work — is an artifact of that calibration or a property that holds across a principled penalty landscape, under certified (not solver-approximate) ground truth and multiple heterogeneous constraints.

### Conditional stronger wording (Scope Lock §N Version C — ONLY valid if confirmed by results)
A structural characterization of penalty-robustness regions for two structurally distinct encoding families, showing a confirmed rank-flip (H1) or a confirmed constraint-type dependence (H3). **This wording may not be used in any abstract, introduction, or summary before the corresponding hypothesis is actually confirmed by experimental results.**

### Forbidden claims (disproven during scoping — do not resurrect these in any future draft)
- "First comparison of slack-variable and unbalanced-penalization QUBO encodings" — **FALSE**, contradicted by Montañez-Barrera et al. 2024/2023 (§7, §8).
- "First penalty sweep comparing two QUBO encodings" — **FALSE** in the fully general sense, contradicted by Kikuchi et al. 2024 (§7, §8); survives only when explicitly restricted to the slack/unbalanced constraint-encoding family.
- "First certified/exact-ground-truth QUBO benchmark" — **FALSE**, contradicted by Stopfer & Wagner 2025 (§7, §8).
- "First portfolio QUBO" — **FALSE**; extensive portfolio-QUBO literature exists (§7, §9).
- "First penalty-sensitivity study" — **FALSE**, contradicted by Güney, Ehrenthal & Hanne 2025, and the still-unresolved Jiajie Liu ACM paper whose title suggests the same (§7, §10) — this one remains a live risk specifically because it was never actually read.

---

## 24. Why We Stopped Scoping

The literature-search phase was stopped, not because exhaustive coverage was achieved (§5 explicitly disclaims this), but because:

1. The broad, combination-based novelty claims (the original six candidates, §3) were tested individually and each was found to be either contradicted or in need of narrowing (§8).
2. A narrower, better-evidenced question (rank stability under a swept landscape) was identified and survived a dedicated, narrowly-targeted kill-shot search designed specifically to attack it (§4.4–4.7).
3. The one specific, apparently dangerous candidate remaining after the kill-shot search (Awai et al.'s ALF) was investigated to a definitive conclusion via direct algebraic derivation, not further searching (§4.6, §11) — this is the kind of resolution that ends an open question rather than perpetuating it.
4. The one remaining open item after that — how to make the two encodings' penalty parameters comparable (the κ-parameterization question) — was judged to be a **methodological design decision**, not a literature-coverage gap, and was resolved as such (§14), through analysis rather than search.
5. Several items remain genuinely unresolved (§10) — but these are documented, bounded, and judged not to require reopening the broad search, because each is either low-priority-by-domain (bioRxiv docking) or would, if resolved unfavorably, narrow rather than eliminate the surviving question (the ACM paper, the exact-cardinality-portfolio paper, the railway-timetabling paper) — none is expected to resurrect one of the six forbidden broad claims in §23.

**Purpose of this section, stated explicitly:** to prevent a future revisit of this project from repeatedly reopening the same scoping question without new cause. New cause would be: actually reading one of the unresolved items in §10 and finding it changes the picture — not a vague sense that "we should double check the literature again."

---

## 25. Final Scope Lock

**Research question.** Does the relative performance of slack-variable and unbalanced-penalization QUBO encodings remain stable across a principled, jointly-swept, dimension-matched penalty landscape, when evaluated against the certified exact ground state of the encoded QUBO, under multiple simultaneous heterogeneous constraints (cardinality, sector cap, budget) in portfolio optimization — or is the reported superiority of one encoding an artifact of the specific, single, separately-tuned penalty values at which prior comparisons were made?

**Encodings.** Slack: $\lambda_S(h(x)-S)^2$, auxiliary register $S$, 19 auxiliary bits total (§13). Unbalanced: $-\lambda_1h(x)+\lambda_2h(x)^2$, no auxiliary variables (§13).

**Parameterization.** $\lambda_1=\kappa,\ \lambda_2=\kappa^2/2$ (Taylor family, retained); $\lambda_S(s)=s\Lambda_\text{ref}/v_\text{ref}^2$, $\kappa(s)=s\Lambda_\text{ref}/v_\text{ref}$, $v_\text{ref}=1$, $\Lambda_\text{ref}$ = objective range over the feasible set, $s$ log-spaced (§14). Numeric bounds on $s$: NOT YET FIXED.

**Ground truth.** Original-problem optimum via exhaustive enumeration (38,760 portfolios); encoded-QUBO ground state via the $O(2^{20})$ closed-form auxiliary-minimization method (§15), never brute force.

**Primary metric.** Exact-optimum recovery rate $\rho_E^\text{exact}$ under the strict all-ties-must-be-A rule (§16, §17).

**Instances.** Stage 1: the existing canonical 20-asset/K=6 instance. Stage 2: 4–6 additional instances (protocol NOT YET FIXED — §19).

**Sensitivity checks required.** 0.5×/2× domain expansion on $s$; bounded curvature-match ($\lambda_S=\kappa^2/2$) alternate-anchor check on a coarse subgrid (§14).

**Main hypotheses.** H0 (rank stability, null), H1 (rank instability), H2 (infeasibility asymmetry), H3 (constraint heterogeneity) — §20.

**Scope exclusions — deliberately NOT being studied:**
- The full, independent $(\lambda_1,\lambda_2)$ unbalanced parameter space (Design 3, rejected §14) — only the Taylor one-parameter sub-family is characterized.
- Hardware execution (QAOA/annealing) — this project is entirely classical exact enumeration; hardware noise/sampling effects are out of scope.
- Any encoding family beyond slack and unbalanced (e.g., domain-wall/one-hot variable-binarization encodings, as studied by Kikuchi et al.) — explicitly a different kind of "encoding" than this project addresses.
- Asset-count or K variation beyond the fixed 20/K=6 (Stage 2 varies return/covariance/sector data only, not problem size) — reserved as future work if Stage 1/2 prove ambiguous.
- The full constraint-ablation matrix (cardinality-only through all-three) as a mandatory primary experiment — reserved as a follow-up only if needed to interpret H3, not committed as core scope.

**Main limitation.** Generalization beyond the Stage 1/2 instance family is explicitly not claimed — flagged in the reviewer-objections analysis (§22) as the weakest point in the design, only partially mitigated, and further weakened by the fact that the Stage 2 protocol itself remains unfixed (§19).

---

## 26. Implementation Handoff

### Data
- [ ] Pull actual $\mu$ from `mu.csv` (existing prototype data file)
- [ ] Pull actual $\Sigma$ from `Sigma.csv` (existing prototype data file)
- [ ] Pull per-stock prices $p_i$ (referenced in prototype, not yet extracted during scoping)
- [ ] Pull sector assignments (20 assets across 4 sectors, per prototype README)

### Mathematical implementation
- [ ] Implement canonical original objective $f(x)=-\mu^Tx+\kappa_\text{risk}x^T\Sigma x$ (§12)
- [ ] Implement exact slack QUBO (§13) with 19 auxiliary bits (8 sector + 11 budget)
- [ ] Implement exact unbalanced QUBO (§13), Taylor-family parameterized (§14)
- [ ] Implement objective-normalized parameter mapping $\lambda_S(s), \kappa(s)$ (§14)
- [ ] Implement ground-state evaluator using the $O(2^{20})$ closed-form-auxiliary method (§15) — **never** the naive $2^{39}$ brute force
- [ ] Implement A/B/C classification (§16), keeping B and C separate throughout every downstream metric
- [ ] Implement tie detection at the $x$-level and the strict all-ties-must-be-A rule (§16)

### Experimental protocol
- [ ] Freeze the Stage-2 RNG/resampling/sector-reassignment protocol (§19 — **currently NOT YET FIXED**, must be resolved and written down before any Stage 2 instance is generated)
- [ ] Freeze parameter-grid resolution (log-spacing base, number of grid points per axis)
- [ ] Compute $\Lambda_\text{ref}$ (objective range/std over the 38,760-portfolio feasible set)
- [ ] Freeze the numeric $s$-domain bounds using the comfortably-non-enforcing/comfortably-enforcing principle (§14 — currently a principle only, not numbers)
- [ ] Implement the 0.5×/2× domain-expansion check
- [ ] Implement the curvature-match ($\lambda_S=\kappa^2/2$) bounded sensitivity check on a coarse subgrid

### Reproducibility
- [ ] Record all random seeds used (once the Stage-2 protocol above is fixed)
- [ ] Version all input data files (`mu.csv`, `Sigma.csv`, price/sector data)
- [ ] Save every grid result (not just summary statistics) — needed for the region-shape/connectedness analysis in §17
- [ ] Save exact configurations (grid definitions, $s$-domain bounds, sensitivity-check parameters) alongside results
- [ ] Record software/library versions used for enumeration and any solver dependencies

---

## 27. Citation Policy for This Document

Every paper-derived claim in §7–11 includes, where available: authors, title/subject, venue, year, and DOI or arXiv identifier. Where a detail (exact page, exact table number, exact author list) could not be independently confirmed during the actual search process, it is marked `CANNOT VERIFY` rather than filled in — no page numbers, DOIs, or figure numbers in this document were invented after the fact. Claims derived by this project's own algebraic work (principally §11, and the derivation in §14/§15) are explicitly labeled **[DERIVED]** or "project-derived" and are not attributed to the source papers' authors. Where this document's requested outline referenced a citation ("Liu & Moraglio") that does not match what was actually found and verified during scoping, that discrepancy is preserved and flagged explicitly (§7) rather than silently resolved in either direction.

---

## 28. Source-of-Truth Rule

Where an earlier claim in this project's history was later contradicted by evidence, the corrected conclusion is what appears in the frozen scope (§25) — but the earlier claim and the evidence that contradicted it are preserved in the relevant chronology section (principally §4, §8, and the individual paper entries in §7), not erased. Examples already recorded in this document under this rule: the original six broad novelty candidates (§3) → contradicted or narrowed by specific papers (§8); Awai et al. initially flagged as a partial threat → definitively cleared by direct derivation (§4.6, §7, §11); the naive κ-value-equality proposal → analyzed and rejected in favor of the objective-normalized mapping (§14). This document's own existence is the mechanism by which this rule is honored — nothing above has been rewritten to make an earlier stage of the process look more competent than it was.

---

## 29. Closing Note

This record was written to be read cold, six months or a year from now, without needing to reconstruct the reasoning from scratch. Where something remains unresolved (§10, §19, the numeric $s$-domain bounds in §14), it is marked as such rather than smoothed over. Where an early idea was wrong, it is recorded as wrong, along with exactly which paper or derivation established that. The failed paths and corrected assumptions in this document are as much a part of the project's provenance as the frozen final specification, and should not be deleted or summarized away in any future revision of this file — if this document is ever updated, extend it, don't overwrite its history.

---

**End of record.**

# Adversarial Literature Novelty Audit — QUBO Portfolio Optimization

## Purpose

You are acting as a **hostile literature reviewer and research-scoping analyst**, not as a writing assistant.

I am considering spending approximately **3 months part-time** on a research project around QUBO formulations for constrained portfolio optimization.

Your job is **not to validate my idea**.

Your job is to try as hard as possible to **destroy the novelty claim**. If the idea survives, identify the **narrowest, strongest, evidence-backed novelty claim** that remains defensible.

A false positive ("this is novel!") is much more damaging than a false negative ("we need more evidence").

Do not optimize for encouragement. Optimize for correctness.

---

# 1. Materials you have been given

You should receive some or all of the following:

1. **Current research problem statement / proposal**
2. **Existing literature-review audit**
3. **Current QUBO formulation or code**, if available
4. **Bibliography / papers already identified**
5. Any previous research notes

Treat these as researcher-provided material, not automatically correct facts.

The existing audit may contain:
- verified claims,
- provisional claims,
- mistakes,
- false starts,
- unsupported claims,
- claims that were later retracted.

You MUST distinguish these.

In particular, do not inherit a novelty claim merely because it appears in the audit.

---

# 2. The current research direction

The current direction is broadly:

> A controlled comparison of **slack-variable QUBO encoding versus unbalanced penalization**, studied **as a function of penalty parameters**, for **constrained portfolio optimization**, with validation against **certified exact optima**.

The current setup involves multiple simultaneous constraints, including:

- cardinality,
- sector caps,
- budget,

with multiple penalty coefficients.

A current prototype has been validated by exhaustive enumeration on a 20-asset, K=6 instance, where:

C(20, 6) = 38,760

feasible portfolios can be enumerated and the exact constrained optimum is therefore known.

Do NOT assume that this setup itself is novel.

---

# 3. Core question

Determine whether there is a **real research gap** at the intersection of:

- QUBO / quantum optimization,
- constrained portfolio optimization,
- constraint encoding,
- slack-variable formulations,
- unbalanced penalization / slack-free formulations,
- penalty coefficient selection,
- penalty sensitivity / robustness,
- multidimensional penalty sweeps,
- exact or certified ground truth,
- and multiple simultaneous heterogeneous constraints.

The key question is NOT:

> "Has anyone done exactly this exact experiment?"

The key question is:

> **Has the scientific question already been answered elsewhere, perhaps under different terminology, on a different optimization problem, or using a different experimental formulation?**

If yes, explain why.

If no, explain precisely what remains unanswered.

---

# 4. Your operating principle

## Assume the claim is false until proven otherwise.

For every potentially relevant paper:

1. Locate the actual paper.
2. Prefer the primary paper/PDF over:
   - blog posts,
   - review articles,
   - snippets,
   - citation databases,
   - secondary summaries.
3. Read the relevant sections of the actual paper.
4. Search the full text for relevant concepts.
5. Record exactly what the paper does.
6. Record exactly what it does NOT do.
7. Give the page/section/figure/table supporting each important conclusion.

If you cannot verify something:

> **CANNOT VERIFY**

Do not infer it.

Do not fill gaps from memory.

Do not convert an abstract-level statement into a full-paper claim.

Do not fabricate page numbers, figures, parameter values, instance sizes, citations, or experimental details.

---

# 5. Search broadly, not lexically

Do NOT search only for phrases like:

- "penalty landscape"
- "slack versus unbalanced"
- "QUBO penalty sweep"

A relevant paper may use completely different terminology.

Search conceptual equivalents such as:

### Penalty terminology
- penalty coefficient
- penalty parameter
- Lagrange multiplier
- penalty weight
- constraint weight
- penalty scaling
- penalty calibration
- penalty tuning
- penalty sensitivity
- parameter sensitivity
- hyperparameter sensitivity
- coefficient robustness
- robustness to penalty selection
- constraint weighting
- energy scale
- energy separation
- feasibility threshold
- optimality threshold
- parameter regime
- phase diagram
- regime boundary

### Encoding terminology
- slack variable
- slack-free
- unbalanced penalization
- unbalanced penalty
- Lagrangian formulation
- inequality encoding
- equality encoding
- constraint encoding
- quadratic penalty
- penalty reformulation
- QUBO reformulation
- binary reformulation
- encoding overhead
- auxiliary variables
- ancilla variables
- quadratization

### Optimization terminology
- QUBO
- quadratic unconstrained binary optimization
- Ising
- quantum annealing
- QAOA
- quantum optimization
- combinatorial optimization
- constrained binary optimization

### Robustness / landscape terminology
- sensitivity analysis
- parameter sweep
- parameter scan
- grid search
- coefficient sweep
- phase transition
- solution regime
- feasible/infeasible ordering
- ground-state structure
- energy landscape
- optimality landscape
- constraint violation landscape

Search outside portfolio optimization too.

A method established on:
- knapsack,
- TSP,
- job-shop scheduling,
- maximum independent set,
- bin packing,
- rostering,
- multidimensional knapsack,
- generic constrained binary optimization,

may destroy a supposed methodological novelty even if no portfolio paper uses it.

---

# 6. Search in five threat categories

## Threat A — Encoding comparison

Find work comparing:

- slack-variable QUBO
- unbalanced penalization
- slack-free formulations
- Lagrangian/slack-free formulations
- alternative inequality encodings

Determine whether the comparison is:
- theoretical,
- numerical,
- hardware,
- QAOA,
- annealing,
- classical simulation,
- or some combination.

---

## Threat B — Penalty-parameter dependence

Find work that varies penalty coefficients over a range rather than selecting one value.

Look for:
- 1D sweeps,
- 2D sweeps,
- 3D or higher-dimensional sweeps,
- sensitivity analysis,
- phase diagrams,
- regime maps,
- robustness regions.

Determine whether the study measures:
- feasibility,
- objective quality,
- probability of optimal solution,
- ground-state identity,
- approximation ratio,
- constraint violation,
- energy gap,
- or another metric.

---

## Threat C — Exact ground truth

Determine how papers establish the reference optimum.

Classify ground truth as:

- exhaustive enumeration,
- exact dynamic programming,
- exact ILP/MIP,
- proven optimal solver output,
- known benchmark optimum,
- best-known solution,
- heuristic reference,
- approximate classical solver,
- unknown.

Do NOT treat "optimal" and "best found" as equivalent.

This distinction is crucial.

---

## Threat D — Multiple simultaneous penalty coefficients

Look for papers with:

- 2 coefficients,
- 3 coefficients,
- 4+ coefficients,

where coefficients correspond to genuinely different constraints.

Determine whether they are:

- independently varied,
- jointly varied,
- analytically related,
- fixed after one calibration,
- tuned separately,
- or tuned using another optimizer.

A paper that merely contains three symbols λ1, λ2, λ3 but never studies their independent variation does NOT count as a multidimensional parameter-sweep study.

---

## Threat E — Portfolio-specific prior art

Search deeply for:

- QUBO portfolio optimization,
- cardinality-constrained portfolio,
- budget-constrained portfolio,
- sector-constrained portfolio,
- quantum portfolio optimization,
- unbalanced portfolio QUBO,
- slack portfolio QUBO,
- penalty tuning in portfolio QUBO,
- exact portfolio QUBO validation,
- penalty sensitivity in portfolio optimization.

Do not assume that "portfolio" appearing in an introduction means portfolio experiments were performed.

---

# 7. Search for terminology drift

This is extremely important.

A researcher may describe something as:

> "unbalanced penalization"

while another paper describes essentially the same mechanism as:

> "Lagrangian relaxation"

or:

> "slack-free inequality encoding"

or:

> "weighted constraint penalty."

You must determine whether these are genuinely different methods or merely different terminology.

Likewise:

> "parameter robustness"

may be the same scientific question as:

> "penalty sensitivity."

Do not artificially manufacture novelty through vocabulary.

---

# 8. Build an evidence matrix

Create a comprehensive table for every serious threat paper.

Use columns like:

| Paper | Year | Domain | Portfolio experiment? | QUBO? | Slack encoding? | Unbalanced/slack-free? | Encoding comparison? | Penalties varied? | # independent coefficients | Joint sweep? | Exact ground truth? | Ground-truth method | Metrics | Hardware/QAOA/classical | Relevant section/figure | Threat level |
|---|---:|---|---|---|---|---|---|---:|---:|---|---|---|---|---|---|---|

Do not fill cells with guesses.

Use:
- YES
- NO
- PARTIAL
- CANNOT VERIFY

where appropriate.

---

# 9. Classify threats

For every paper, assign:

### DIRECT THREAT
The paper already answers essentially the same scientific question.

### PARTIAL THREAT
The paper establishes an important component of the proposed contribution but leaves a meaningful dimension unanswered.

### METHODOLOGICAL THREAT
The exact domain differs, but the proposed methodological contribution has effectively already been established elsewhere.

### DOMAIN-SPECIFIC PRIOR ART
The scientific method is established, but the portfolio domain has not been studied.

### RELATED BUT NOT THREATENING
Relevant context, but does not actually answer the research question.

Explain the classification.

---

# 10. Specifically attack the current novelty claim

Test these candidate claims independently.

## Candidate 1

> No prior work compares slack-variable and unbalanced encodings.

Try to disprove it.

## Candidate 2

> No prior work compares these encodings while varying penalty parameters across a range.

Try to disprove it.

## Candidate 3

> No prior work performs such a comparison against certified exact optima.

Try to disprove it.

## Candidate 4

> No prior work jointly varies three or more independent penalty coefficients against certified exact optima.

Try to disprove it.

## Candidate 5

> No prior work studies this interaction in constrained portfolio optimization.

Try to disprove it.

## Candidate 6

> No prior work characterizes the robustness regions of different constraint encodings in multidimensional penalty space.

Try to disprove it.

For every candidate:

**CONFIRMED / CONTRADICTED / PARTIALLY CORRECT / CANNOT VERIFY**

Then provide the evidence.

---

# 11. Do not confuse "not found" with "does not exist"

This rule is mandatory.

There is a huge difference between:

> "I searched and did not find a paper."

and:

> "No prior work exists."

Unless the search is sufficiently comprehensive to justify the latter, say:

> "No directly matching paper was identified in the searched literature."

Use calibrated language.

---

# 12. Search for the most dangerous papers first

Prioritize papers that could destroy the project.

Especially search for papers containing combinations of:

1. encoding comparison + parameter sweep
2. encoding comparison + exact optimum
3. parameter sweep + exact optimum
4. 3+ independent penalty coefficients
5. portfolio + unbalanced penalization
6. portfolio + slack encoding
7. portfolio + penalty sensitivity
8. constrained binary optimization + penalty landscape
9. QUBO encoding + robustness
10. papers published very recently

Also search references/citations from the closest papers.

A paper's related-work section can reveal an older paper that uses different terminology.

---

# 13. Resolve the existing audit's unresolved claims

The current audit contains unresolved literature threats.

At minimum, independently verify:

### Chang et al. (2000)
Determine whether certified exact solutions were used for the cardinality-constrained portfolio frontier.

This matters because if they already did certified-optimum benchmarking of the relevant constrained portfolio problem, part of the proposed benchmark novelty weakens.

### Stopfer & Wagner (2025)
Verify the actual methodology from the paper, especially:
- exact ground truth,
- portfolio formulation,
- penalty treatment,
- scale of instances,
- and whether penalty values were actually fixed/swept.

Do not rely on secondary claims.

### Montañez-Barrera et al. (2025)
Verify the portfolio application of unbalanced penalization.

### Any papers after the date of the existing audit
Search them explicitly.

The literature is moving quickly, so recent papers are high priority.

---

# 14. Look for papers published after the existing audit

Do a fresh search for the newest literature.

The existing audit was itself concerned about rapidly appearing 2026 work.

Do not treat its literature set as complete.

Search current:
- arXiv
- Google Scholar / scholarly search
- Semantic Scholar or equivalent
- IEEE
- ACM
- Springer
- APS
- IOP
- Nature family journals
- Quantum journals/conferences
- relevant optimization journals

Use primary papers wherever possible.

---

# 15. Distinguish novelty types

Do not reduce novelty to "first paper ever."

Evaluate:

### Methodological novelty
A genuinely new method.

### Empirical novelty
A new systematic experimental characterization.

### Benchmark novelty
A new reproducible benchmark with certified ground truth.

### Structural novelty
A new relationship between variables/phenomena.

### Domain novelty
Known method applied rigorously to an important previously unstudied domain.

### Negative/deflationary novelty
A rigorous result showing that an expected advantage does not materialize under controlled conditions.

A project does NOT need methodological novelty to be a worthwhile paper.

But if the only contribution is trivial domain transplantation, say so.

---

# 16. Evaluate the "so what?" problem

Even if the literature gap is real, ask:

> Why should anyone care?

Evaluate whether the proposed result could answer something scientifically meaningful such as:

- Which encoding is more robust to penalty misspecification?
- Are conclusions about encoding quality stable across penalty regimes?
- Do different encodings have qualitatively different feasible/optimal ground-state regions?
- How does constraint tightness affect robustness?
- Does reducing auxiliary variables introduce sensitivity to penalty selection?
- Can penalty robustness be predicted from problem structure?
- Are commonly reported comparisons representative or artifacts of a particular tuned penalty point?

These are examples, not predetermined hypotheses.

Do not force the data toward them.

---

# 17. Identify the minimum publishable contribution

At the end, determine:

> What is the weakest result that would still constitute a meaningful contribution?

For example:

### Weak result
"Encoding A gives lower qubit count."

Probably insufficient by itself.

### Better
"Encoding A and B exhibit different penalty sensitivity."

Potentially meaningful.

### Stronger
"Encoding A has a consistently larger region of parameter space yielding the exact optimum."

Better.

### Strong
"The shape/size of this robustness region changes systematically with constraint structure."

Very interesting.

### Very strong
"An empirical or analytical relationship explains/predicts the observed regime structure."

Potentially substantial.

Again: these are evaluation criteria, not conclusions.

---

# 18. Design a novelty-risk map

Produce a final matrix:

| Potential contribution | Existing prior art | Remaining gap | Novelty confidence | Publication risk |
|---|---|---|---|---|
| Encoding comparison | ... | ... | High/Medium/Low | ... |
| Penalty sensitivity | ... | ... | ... | ... |
| Multidimensional sweep | ... | ... | ... | ... |
| Exact ground truth | ... | ... | ... | ... |
| Portfolio application | ... | ... | ... | ... |
| Encoding × penalty interaction | ... | ... | ... | ... |
| Structural explanation | ... | ... | ... | ... |

---

# 19. Give me three possible outcomes

At the end, classify the project into one of these:

## GREEN — LOCK AND BUILD

The core research question appears sufficiently underexplored and the contribution is defensible.

Give:
- exact surviving novelty claim,
- evidence supporting it,
- key papers that establish the gap,
- remaining caveats,
- experiments required.

## YELLOW — REFRAME BEFORE BUILDING

The core idea is promising but an important component already exists.

Give:
- what was already done,
- what remains unanswered,
- the smallest change needed,
- the strongest revised research question.

Do NOT redesign the entire project unnecessarily.

## RED — ABANDON/REPLACE

The central research question is already substantially answered.

Give:
- the paper(s) that kill it,
- exactly what they already establish,
- why merely changing the dataset/domain is insufficient,
- what nearby research direction appears more defensible.

---

# 20. Critical rule: do not manufacture a better novelty just to save the project

If the current idea is weak, say so.

If it is strong, say so.

If it is uncertain, say:

> CANNOT VERIFY

Do not invent an artificial novelty claim such as:
- "first to use X on dataset Y,"
- "first to combine A and B,"
- "first comprehensive study"

unless the evidence genuinely supports it.

---

# 21. Final deliverable

Return a report with this structure:

# Executive Verdict

One of:
- GREEN — lock and build
- YELLOW — reframe
- RED — replace

Then give a short explanation.

# 1. Current Research Question

Restate what you believe the actual research question is.

# 2. Current Novelty Claims

List each candidate claim and mark:

- CONFIRMED
- CONTRADICTED
- PARTIALLY CORRECT
- CANNOT VERIFY

# 3. Closest Prior Art

For each paper:
- full citation
- what it actually does
- what it does not do
- exact evidence location
- threat classification

# 4. Evidence Matrix

Provide the complete structured table.

# 5. Adversarial Search Results

Explain what you searched and which conceptual variants you used.

# 6. What Would Kill This Project?

List the strongest remaining threats.

# 7. Surviving Research Gap

State the narrowest defensible gap in precise scientific language.

# 8. Recommended Scope

If GREEN/YELLOW, recommend the smallest defensible scope.

Do not inflate it.

# 9. Minimum Experiments Needed

Describe the experiments necessary to substantiate the contribution.

# 10. Publication Risk

Rate:
- novelty risk
- methodological risk
- experimental risk
- scalability risk
- reviewer-objection risk

# 11. Final Recommendation

Tell me whether I should:

- lock the scope,
- do one more targeted search,
- reframe,
- or abandon it.

---

# 22. Standard of evidence

For every major novelty claim, I want:

> **Claim → Paper → Exact evidence → Interpretation → Confidence**

Example:

> Claim: Prior work does not jointly vary three independent penalty coefficients.

> Evidence: Paper X varies two coefficients in Figure Y and fixes all others.

> Interpretation: This paper does not threaten the three-coefficient claim.

> Confidence: HIGH, because the full paper was inspected.

Do this systematically.

---

# 23. Absolutely prohibited

Do NOT:

- hallucinate papers,
- invent citations,
- invent DOI numbers,
- invent page numbers,
- infer full methodology from abstracts,
- treat search snippets as proof,
- treat "best known" as "certified optimal",
- treat "optimal" as exact without checking,
- assume terminology means methodology,
- claim absence from literature based on one search query,
- cite secondary sources as if they were primary evidence,
- tell me the idea is novel merely because you cannot find a paper,
- soften a contradiction because the project is interesting.

If evidence is insufficient:

> CANNOT VERIFY

That is a successful answer.

---

# 24. Researcher's explicit instruction

**Break this project if you can.**

I would rather discover in the literature-review phase that the idea is not novel than discover it after spending three months implementing it.

The desired outcome is not encouragement.

The desired outcome is:

> **a defensible research question whose novelty claim survives serious adversarial scrutiny.**

If the current scope survives, say so confidently and explain exactly why.

If it does not, identify the smallest change that makes the research scientifically worthwhile.


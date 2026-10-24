# qubo-rank-stability

Code, frozen specifications and sealed results for the study
**"Rank Stability of Slack-Variable and Unbalanced-Penalization QUBO Encodings across a
Matched Penalty Landscape in a 20-Asset Portfolio Problem"** (Shivansh Srivastava,
IIT Roorkee). The manuscript is under final internal audit and is not yet public; it will
be linked here when it is posted.

**What the study does, in short.** Two common ways of turning an inequality constraint into
a QUBO (quadratic unconstrained binary optimisation problem) are compared: slack-variable
encoding and unbalanced penalization. Five 20-asset portfolio instances (choose K = 6 assets)
are each certified exactly, by exhaustive enumeration, at every point of a predeclared
61 × 61 × 61 grid of penalty coefficients (226,981 points per matching parameter). Each point
is labelled by whether each encoding's ground state decodes to the true optimum. The results are reported
per instance; no claim is made beyond these five instances.

## How the project was run

The work went through gates 0–10. Each gate has a folder, and each gate's rules were frozen
before its numbers were computed. For example, the penalty range was fixed as a rule at
Gate 1 and only computed at Gate 3.

| Folder | Gate | Contents |
|---|---|---|
| `00_scope/` | 0 | Scoping history and gate logs. The scope lock is `RESEARCH_SCOPING_AND_SCOPE_LOCK.md` at the root. |
| `01_specification/` | 1 | Frozen mathematical, implementation and validation specifications; Gate-1 charter |
| `02_data/` | 2 | The canonical Stage-1 instance (`canonical/stage1_instance.json`) and how it was built |
| `03_ground_truth/` | 3 | Exact ground truth by enumeration of all 2^20 portfolios; the two pre-committed numbers (`adnye/`: the normaliser Λ_ref and the penalty box) |
| `04_encodings/` | 4 | Encoding-correctness checks |
| `05_certification/` | 5 | Exact certification machinery for the full grid (raw output not included, see below) |
| `06_landscape/` | 6 | Penalty-landscape analysis and companion checks; GPU (CUDA, Tesla T4) measurements |
| `07_stage1_inference/` | 7 | Stage-1 inference |
| `08_audit/` | 8 | Independent verifiers and audit material |
| `09_stage2/` | 9 | Five-instance Stage 2: build rehearsals (`builds/`), the analysis pipeline (`analysis_20261003/`) and the sealed result (`sealed_results/STAGE2_INFERENCE.json`) |
| `10_release/paper/reader/figures/` | 10 | Figure 1 (optimal-label regions): script, label data, panels and the verification report |
| `decisions/` | all | Only the approval records and the `DECISIONS.md` register that the code reads; the rest of the decision log is not included |
| `src/` | 4–6 | The frozen Python package (`src.g4`, `src.g5`, `src.g6`) |
| `research/g9/` | 9 | Stage-2 generator and protocol code (`09_stage2/g9` is a shortcut to it; the frozen generator guard refuses paths through shortcuts) |
| `research/` (rest) | — | Shortcuts: older code refers to `research/<x>`, and these links keep it working |
| `ops/scripts/` | — | Test and verifier runners |

## Running the checks

Requirements: Python 3.12 or newer. Most code uses only the standard library; the Stage-2
generator also uses NumPy. The specification names CPython 3.12.3 and NumPy 2.4.4; the Stage-2
draws ran on Kaggle CPython 3.12.13 with NumPy 2.0.2 under a recorded runtime-only amendment.
Run everything from the repository root:

```
bash ops/scripts/run_all_verifiers.sh     # Gate 1–4 verifiers and digest checks
bash ops/scripts/run_tests.sh             # Gate 5 machinery tests
bash ops/scripts/run_stage2_fixtures.sh stage2.tsv  # all 32 Stage-2 fixture suites (slow: ~30 min)
```

**Clean-folder test (2026-10-24).** Every check in the two runners plus all 32 Stage-2 fixture
suites (66 commands) was run on a fresh clone of this repository, with the original project
hidden from the process, under CPython 3.12.3 with NumPy 2.4.4 and `py_ecc` 8.0.0, and with
`TMPDIR` on the same disk as the repository. **60 pass.** The 6 that do not:

| Check | Why it fails |
|---|---|
| `research/audit/verify_g2_canonical.py`, `research/audit/verify_gate0_facts.py`, `02_data/canonical/audit_g2_batch3_delta.py` | Need the original source data, which is not included |
| Gate-2 and Gate-3 checksum checks (`DIGESTS.txt` in `02_data/canonical/` and `03_ground_truth/ground_truth/`) | Three provenance notes they list are not included; every other listed file matches |
| `verify_stage2_section_b1_recheck_fixtures.py` | Contains an absolute path to the original machine |

In the original project, all 32 Stage-2 fixture suites pass under the same environment.

Notes:
- `verify_stage2_beacon_bls_verify_fixtures.py` needs the third-party `py_ecc` package (randomness beacon; the beacon was deferred and not used).
- `verify_stage2_reference_seal_fixtures.py` copies the repository into the temporary folder with hard links, so `TMPDIR` must be on the same filesystem as the repository.
- Under Python 3.14, the Stage-2 generator and section-B2 harness suites also fail: the study specifies CPython 3.12.
- `verify_stage2_cuda_core_corruption_qualification_fixtures.py` failed once on 2026-10-18 ("normal/-O plan differs") and has passed on every later run; treat it as intermittent.
- `verify_stage2_d013_inactive_evaluator_fixtures.py` needs more than 5 minutes; the runner allows 15.

## Licence

Code: MIT (`LICENSE`). Documentation, specifications, records and data: CC BY 4.0 (`LICENSE-docs`).
`research/g9/GATE_9_DRAND_SCHEMES_SOURCE.go.txt` is third-party code from drand (MIT; see the `.LICENSE` file beside it).

## Contact

Shivansh Srivastava, Department of Computer Science and Engineering, IIT Roorkee,
shivansh_s@cs.iitr.ac.in

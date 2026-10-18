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

**Clean-folder test (2026-10-18).** Every check in the two runners plus all 32 Stage-2 fixture
suites (66 commands) was run on a fresh copy of this repository, with the original project
hidden from the process, under Python 3.14.4. **56 pass.** The 10 that do not:

| Check | Why it fails |
|---|---|
| `research/audit/verify_g2_canonical.py`, `research/audit/verify_gate0_facts.py`, `02_data/canonical/audit_g2_batch3_delta.py` | Need the original source data, which is not included |
| Gate-2 and Gate-3 checksum checks (`DIGESTS.txt` in `02_data/canonical/` and `03_ground_truth/ground_truth/`) | Three provenance notes they list are not included; every other listed file matches |
| `verify_stage2_generator_fixtures.py` | The Stage-2 generator deliberately refuses to run on any CPython other than 3.12 |
| `verify_stage2_section_b1_recheck_fixtures.py` | Contains an absolute path to the original machine |
| `verify_stage2_beacon_bls_verify_fixtures.py` | Needs the third-party `py_ecc` package (randomness beacon; the beacon was deferred and not used) |
| `verify_stage2_reference_seal_fixtures.py` | Copies the repository into the temporary folder with hard links, which fails when `/tmp` is on a different filesystem. Passes with `TMPDIR` set to a folder on the same disk as the repository |
| `verify_stage2_section_b2_harness_fixtures.py` | Fails in the original project too on this Python version; the study specifies Python 3.12, not re-checked here |

Notes: `verify_stage2_cuda_core_corruption_qualification_fixtures.py` failed once ("normal/-O plan differs") and passed on the two later runs, so treat it as intermittent. `verify_stage2_d013_inactive_evaluator_fixtures.py` needs more than 5 minutes; the runner allows 15.

## What is not included, and why

- **Raw result records** (about 22 GB: Stage-2 production records 9.9 GB, Gate-5 certification
  output 1.1 GB, Stage-1 GPU runs 11 GB) are too large for git. A data deposit (Zenodo) is
  planned with the arXiv version. The sealed summary that the paper's numbers come from is
  included (`09_stage2/sealed_results/STAGE2_INFERENCE.json`).
- **The Stage-2 reference seal** (`wp7b_reference_seal.json`, 302 MB) exceeds GitHub's file-size
  limit; `research/g9/stage2_reference_seal.py` regenerates it.
- **The GPU production runs** were executed on Kaggle Tesla T4 workers; the job harness is not
  included because it is tied to that environment and to machine-specific paths.
- **Working notes, most decision records and the Stage-1 GPU run bundles** are not included.
  Some frozen documents still refer to them, or to files by their original names.
- **The original source data** that the Stage-1 instance was built from is not included; the built,
  hash-checked instance is (`02_data/canonical/`).
- **Absolute paths.** Some frozen scripts and records contain the original machine paths
  (`/home/shivansh-srivastava/decisions_os/...`). They are left unchanged because frozen files
  are hash-pinned. Scripts that read those paths will not run elsewhere without the raw records.

## Public-copy adjustments

- Four independent review scripts are placed in the gate folder they check:
  `04_encodings/g4/review_g4_energy_conformance.py`, `02_data/canonical/audit_g2_batch3_delta.py`,
  and `05_certification/g5/review_g5_amortisation_v2.py` and `review_g5_domain_cache_corrective.py`.
  Their root-folder line was changed for the new location; `04_encodings/g4/verify_g4_energy.py`
  pins the new value of its probe.
- Five files were renamed: `08_audit/audit/verify_gate0_review_findings.py`,
  `08_audit/audit/GATE_0_INDEPENDENT_AUDIT.md`, `08_audit/audit/G3_ADNYE_00{1,2}_INDEPENDENT_REPLAY.json`
  and `research/g9/GATE_9_TIMESTAMP_WITNESS_INDEPENDENT_REVIEW.md`.
- Wording in some unpinned documents and code comments was edited for the public copy.
  No hash-pinned file was edited except the four review scripts above.
- Edited files' sha256 values therefore differ from any recorded for them in the project
  records. `ops/scripts/run_all_verifiers.sh` and `run_tests.sh` call the current paths.

## Licence

Code: MIT (`LICENSE`). Documentation, specifications, records and data: CC BY 4.0 (`LICENSE-docs`).
`research/g9/GATE_9_DRAND_SCHEMES_SOURCE.go.txt` is third-party code from drand (MIT; see the `.LICENSE` file beside it).

## Contact

Shivansh Srivastava, Department of Computer Science and Engineering, IIT Roorkee,
shivansh_s@cs.iitr.ac.in

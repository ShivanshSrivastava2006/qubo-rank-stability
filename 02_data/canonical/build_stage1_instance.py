#!/usr/bin/env python3
"""
G2 / U-07 — build the canonical Stage-1 instance artifact.

Authority: Shivansh's direct approval of the seven-item G2/U-07 canonical-input package
(2026-08-25; reported in codex_messages/to_claude.md [2026-08-25 18:28:56 IST]; the package
text is progress.md [2026-08-25 18:26:12 IST]).

Reads ONLY read-only prototype evidence under previous_work/ and writes exactly one artifact,
research/canonical/stage1_instance.json. It performs the IMPLEMENTATION_SPEC D.3 assertions:
ticker-keyed read, named canonical order, asserted reindex, attached p/sectors, symmetry+PSD
after reindex, and a single hash-stamped emission.

This script does NOT compute v_ref, Lambda_ref, Delta_full, f*, X*, the domain box, or any
QUBO/G3+ object. `(1,1,5)` is NOT assumed.
"""
import csv, hashlib, json, os, sys
from datetime import date, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PROTO = os.path.join(ROOT, "previous_work", "QDTRINITY_sTAGE_2")
MU_CSV = os.path.join(PROTO, "datasets", "mu.csv")
SIGMA_CSV = os.path.join(PROTO, "datasets", "Sigma.csv")
OUT = os.path.join(ROOT, "research", "canonical", "stage1_instance.json")

# Approved digests of the adopted source artifacts (package item 1).
EXPECTED = {
    "mu.csv": "a20f7b0abd5795e058929e3705d277837d37f10aa9787d044a297f78ed2018b9",
    "Sigma.csv": "ebcdfb342bc30367aa2baa00c9190d86256f2b8dbedd6d07c23fc680ed346e8b",
}

# Canonical universe order, defined ONCE as a named constant (D.3 item 2).
# Source: submission notebook cell 12 (sector-grouped).
CANONICAL_ORDER = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN",
    "JPM", "V", "MA", "GS", "BAC",
    "LLY", "JNJ", "MRK", "PFE", "ABBV",
    "XOM", "CVX", "GE", "CAT", "HON",
]
# Approved label set (package item 5), carried as ticker -> label. Positional ranges are
# DERIVED VIEWS ONLY and are never the source of truth.
SECTOR_OF = {t: lab for lab, ts in {
    "Technology":        ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN"],
    "Finance":           ["JPM", "V", "MA", "GS", "BAC"],
    "Healthcare":        ["LLY", "JNJ", "MRK", "PFE", "ABBV"],
    "Industrial_Energy": ["XOM", "CVX", "GE", "CAT", "HON"],
}.items() for t in ts}

# Approved price vector (package item 4): submission cell 17, paired with B = 1100.
# Selected on evidence (B-coherence, execution provenance, Gate-1 continuity) — NOT Scope-entailed.
PRICES_CELL17 = [210, 420, 1200, 180, 220, 250, 320, 520, 610, 45,
                 780, 155, 110, 30, 205, 115, 145, 200, 390, 470]
K, C, B = 6, 2, 1100

# ---------------------------------------------------------------------------
# Evidence anchors. Every notebook this record adopts or cites is pinned by
# whole-file digest AND by the digest of each cited cell's source, so a silent
# edit to a cited cell fails the build even if other cells absorb the change.
# Cell-source digest convention: sha256(''.join(cell["source"]).encode("utf-8")).
# ---------------------------------------------------------------------------
SUBMISSION_NB = os.path.join(PROTO, "Jupyter_Notebook_For_Submission.ipynb")
PIPELINE_NB = os.path.join(PROTO, "datasets", "QD_Trinity_Data_Pipeline_Setup (2).ipynb")

EVIDENCE_ANCHORS = {
    "submission_notebook": {
        "path": "previous_work/QDTRINITY_sTAGE_2/Jupyter_Notebook_For_Submission.ipynb",
        "whole_file_sha256":
            "0a5a8522a9efab432cdbacea4c2dd3de8a3bdce156808585dd78a347b4374788",
        "cited_cells": {
            "12": {"role": "canonical universe order and sector membership",
                   "source_sha256":
                       "ca5ec2e98c61395fc562fa7c2197e6c952e0eb4b69d4d498736a5beb6c83b8ec"},
            "17": {"role": "ADOPTED price vector and B = 1100",
                   "source_sha256":
                       "1ede5b728df9c82336ef11136875996f10363978cb135d89aef2ee34e73d6ff8"},
            "80": {"role": "REJECTED competing length-20 price vector, budget 1050",
                   "source_sha256":
                       "449cb02ae612ae224ea071fa8228d618fb233aca924177c2a14c82df1eb67e25"},
        },
    },
    "pipeline_notebook": {
        "path": "previous_work/QDTRINITY_sTAGE_2/datasets/"
                "QD_Trinity_Data_Pipeline_Setup (2).ipynb",
        "whole_file_sha256":
            "d488551ff5923a7cc97c27d06930ef7b1e0b14d37006cfd4b2595be5a028b996",
        "cited_cells": {
            "11": {"role": "download window, 250 sessions, first session, auto_adjust defect",
                   "source_sha256":
                       "7c69857a12ce7091ea59e31af2be2db67f36928c1223bc0c319d435a1d6a4b26"},
            "14": {"role": "pct_change() -> 249 daily simple decimal returns",
                   "source_sha256":
                       "479bb4047b5b05592801d21f553a47d316c391cf2724d35e03608fd45cc3aa89"},
            "17": {"role": "mu = returns.mean()",
                   "source_sha256":
                       "a28acaee78957e712252080c36d8f6151442c7d974a11054a8aaa2c46896eebf"},
            "20": {"role": "Sigma = returns.cov()",
                   "source_sha256":
                       "8c8f128ea67cedb78c8fc0706e08b73f455812df3a8ce436a64a94b0b57055a4"},
        },
    },
}

# ---------------------------------------------------------------------------
# Calendar derivation of the realized session window. Fully specified so it is
# reproducible without appeal to "the standard NYSE calendar": the method is
# weekdays in the half-open request interval minus the listed closures.
# The result is calendar-DERIVED and corroborated; it is NOT an observed date.
# ---------------------------------------------------------------------------
REQUEST_START_INCLUSIVE = "2025-05-31"
REQUEST_END_EXCLUSIVE = "2026-05-31"
EXCHANGE_CLOSURES = [
    "2025-06-19",  # Juneteenth
    "2025-07-04",  # Independence Day
    "2025-09-01",  # Labor Day
    "2025-11-27",  # Thanksgiving
    "2025-12-25",  # Christmas
    "2026-01-01",  # New Year's Day
    "2026-01-19",  # Martin Luther King Jr. Day
    "2026-02-16",  # Washington's Birthday
    "2026-04-03",  # Good Friday
    "2026-05-25",  # Memorial Day
]


def derive_sessions(start_inclusive, end_exclusive, closures):
    """Weekdays in [start, end) minus listed closures. Stdlib only."""
    d0 = date.fromisoformat(start_inclusive)
    d1 = date.fromisoformat(end_exclusive)
    shut = {date.fromisoformat(c) for c in closures}
    out, d = [], d0
    while d < d1:
        if d.weekday() < 5 and d not in shut:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def cell_source_sha256(nb_path, index):
    nb = json.load(open(nb_path))
    return hashlib.sha256(
        "".join(nb["cells"][index]["source"]).encode("utf-8")).hexdigest()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def die(msg):
    print(f"ASSERTION FAILED: {msg}", file=sys.stderr)
    sys.exit(1)


def main():
    # --- source integrity -------------------------------------------------
    for name, path in (("mu.csv", MU_CSV), ("Sigma.csv", SIGMA_CSV)):
        got = sha256_file(path)
        if got != EXPECTED[name]:
            die(f"{name} digest {got} != approved {EXPECTED[name]}")

    # --- evidence anchors: fail the build if any cited evidence moved -------
    for nb_key, nb_path in (("submission_notebook", SUBMISSION_NB),
                            ("pipeline_notebook", PIPELINE_NB)):
        spec = EVIDENCE_ANCHORS[nb_key]
        got = sha256_file(nb_path)
        if got != spec["whole_file_sha256"]:
            die(f"{nb_key} whole-file digest {got} != pinned {spec['whole_file_sha256']}")
        for idx, cell in spec["cited_cells"].items():
            ch = cell_source_sha256(nb_path, int(idx))
            if ch != cell["source_sha256"]:
                die(f"{nb_key} cell {idx} source digest {ch} != pinned "
                    f"{cell['source_sha256']}")

    # --- calendar derivation of the realized session window ----------------
    sessions = derive_sessions(REQUEST_START_INCLUSIVE, REQUEST_END_EXCLUSIVE,
                               EXCHANGE_CLOSURES)
    if len(sessions) != 250:
        die(f"calendar derivation gives {len(sessions)} sessions, expected 250")
    if sessions[0] != "2025-06-02":
        die(f"calendar derivation gives first session {sessions[0]}, expected 2025-06-02")
    if sessions[-1] != "2026-05-29":
        die(f"calendar derivation gives last session {sessions[-1]}, expected 2026-05-29")

    # --- D.3 item 1: read keyed by ticker, never positionally --------------
    mu_rows = list(csv.reader(open(MU_CSV)))
    if mu_rows[0] != ["Ticker", "expected_return"]:
        die(f"unexpected mu.csv header {mu_rows[0]}")
    mu_by_ticker = {r[0]: float(r[1]) for r in mu_rows[1:]}
    mu_literal = {r[0]: r[1] for r in mu_rows[1:]}          # exact source decimal text

    s_rows = list(csv.reader(open(SIGMA_CSV)))
    s_cols = s_rows[0][1:]
    sigma_by_ticker = {}
    sigma_literal = {}
    for r in s_rows[1:]:
        for j, v in enumerate(r[1:]):
            sigma_by_ticker[(r[0], s_cols[j])] = float(v)
            sigma_literal[(r[0], s_cols[j])] = v
    s_index = [r[0] for r in s_rows[1:]]
    if s_index != s_cols:
        die("Sigma.csv index != columns")

    # --- D.3 item 3: assert the reindex is a total bijection --------------
    if set(mu_by_ticker) != set(CANONICAL_ORDER):
        die("mu ticker set != canonical universe set")
    if set(s_index) != set(CANONICAL_ORDER):
        die("Sigma ticker set != canonical universe set")
    if len(CANONICAL_ORDER) != len(set(CANONICAL_ORDER)):
        die("canonical universe contains duplicates")
    if len(mu_by_ticker) != 20 or len(s_index) != 20:
        die("expected exactly 20 assets")

    mu_vec = [mu_by_ticker[t] for t in CANONICAL_ORDER]
    sigma_mat = [[sigma_by_ticker[(a, b)] for b in CANONICAL_ORDER] for a in CANONICAL_ORDER]
    # post-reindex order is the canonical order, by construction of the comprehension
    reindex_perm = [ [r[0] for r in mu_rows[1:]].index(t) for t in CANONICAL_ORDER ]

    # --- D.3 item 5: symmetry and PSD after reindexing ---------------------
    asym = max(abs(sigma_mat[i][j] - sigma_mat[j][i]) for i in range(20) for j in range(20))
    if asym != 0.0:
        die(f"Sigma not exactly symmetric after reindex (max asym {asym})")
    try:
        import numpy as np
        eig = np.linalg.eigvalsh(np.array(sigma_mat, dtype=float))
        min_eig, max_eig = float(eig.min()), float(eig.max())
    except ImportError:
        die("numpy required for the PSD assertion")
    if min_eig <= 0.0:
        die(f"Sigma not positive definite after reindex (min eigenvalue {min_eig})")

    # --- D.3 item 4: attach p and sectors to the same canonical order ------
    if len(PRICES_CELL17) != 20 or not all(isinstance(p, int) for p in PRICES_CELL17):
        die("price vector must be 20 integers")
    p_by_ticker = dict(zip(CANONICAL_ORDER, PRICES_CELL17))
    if set(SECTOR_OF) != set(CANONICAL_ORDER):
        die("sector map does not cover the canonical universe exactly")

    # --- assemble ----------------------------------------------------------
    inst = {
        "schema": "decisions_os/stage1_canonical_instance",
        "schema_version": "1.0.0",
        "gate": "G2",
        "unresolved_item": "U-07",
        "status": "CANONICAL — assembled under approved G2/U-07 canonical-input package",

        "authority": {
            "approval": "Shivansh, direct human approval, 2026-08-25, of the seven-item "
                        "G2/U-07 canonical-input package",
            "package_text": "progress.md [2026-08-25 18:26:12 IST] (author: Claude)",
            "approval_relay": "codex_messages/to_claude.md [2026-08-25 18:28:56 IST]",
            "decision_register_entry":
                "research/decisions/DECISIONS.md — "
                "'## Process Approval — G2 / U-07 Canonical-Input Package' "
                "(Status: APPROVED; Shivansh, 2026-08-25; direct human approval quoted in "
                "the record). Recorded by Codex at [2026-08-25 18:28:56 IST].",
            "decision_register_history":
                "At initial assembly [2026-08-25 18:39:45 IST] this register entry was NOT "
                "yet present, and the artifact then recorded it as PENDING. Codex has since "
                "recorded the authoritative entry; this field was updated in Batch 3 "
                "[2026-08-25]. The historical absence is preserved here deliberately and "
                "must not be erased.",
            "does_not_authorize": [
                "U-07 closure", "assuming v_ref = (1,1,5)", "ADNYE execution",
                "G3 ground truth (f*, X*, Lambda_ref, Delta_full)", "the D010 domain box",
                "QUBO construction", "certification", "experiments", "conclusions",
            ],
        },

        "units": {
            "mu": "E",
            "Sigma": "E^2",
            "p": "currency (per-share cost; synthetic — see provenance.price_vector)",
            "B": "currency",
            "K": "dimensionless count",
            "C": "dimensionless count",
            "kappa_risk": "E^-1",
            "note": "E is the objective unit, realized under D007 as decimal simple daily return.",
        },
        "types": {
            "mu_by_ticker": "map<ticker, IEEE-754 binary64>",
            "Sigma_by_ticker_pair": "map<ticker, map<ticker, IEEE-754 binary64>>",
            "p_by_ticker": "map<ticker, int>",
            "sector_of_ticker": "map<ticker, label>",
            "canonical_order": "list<ticker>, length 20, the ONLY positional convention",
            "K": "int", "C": "int", "B": "int",
        },

        "universe": {
            "n_assets": 20,
            "canonical_order": CANONICAL_ORDER,
            "canonical_order_source": "submission notebook cell 12 (sector-grouped)",
            "sector_of_ticker": {t: SECTOR_OF[t] for t in CANONICAL_ORDER},
            "sector_labels": ["Technology", "Finance", "Healthcare", "Industrial_Energy"],
            "positional_sector_ranges_DERIVED_VIEW_ONLY": {
                lab: [i for i, t in enumerate(CANONICAL_ORDER) if SECTOR_OF[t] == lab]
                for lab in ["Technology", "Finance", "Healthcare", "Industrial_Energy"]
            },
        },

        "mu_by_ticker": {t: mu_by_ticker[t] for t in CANONICAL_ORDER},
        "Sigma_by_ticker": {a: {b: sigma_by_ticker[(a, b)] for b in CANONICAL_ORDER}
                            for a in CANONICAL_ORDER},
        "p_by_ticker": {t: p_by_ticker[t] for t in CANONICAL_ORDER},
        "K": K, "C": C, "B": B,

        "kappa_risk": {
            "value": 1.0,
            "unit": "E^-1",
            "unit_as_return_representation": "(decimal simple daily return)^-1",
            "period": "daily",
            "authority": "D007 — indivisible (value, unit, period) triple",
            "d007_conformance": {
                "conforms": True,
                "value": "1.0 as approved; carried unchanged",
                "unit": "mu is a mean of decimal simple returns and Sigma their covariance, "
                        "so [mu]=E, [Sigma]=E^2 and [kappa_risk]=E^-1",
                "period": "daily — returns are pct_change() on consecutive daily adjusted "
                          "closes; NO annualization or other horizon conversion was applied "
                          "at source or here",
                "evidence": "pipeline notebook cells 11/14/17/20 retained outputs; see "
                            "provenance.window and provenance.derivation",
                "statement": "This instance conforms to D007's approved triple in VALUE, UNIT "
                             "AND PERIOD. D007 requires this record to state that explicitly.",
            },
        },

        "reindex": {
            "defect_corrected": "PROTOTYPE_AUDIT.md F-1 — prototype joined mu/Sigma "
                                "positionally to a sector-grouped universe; 18 of 20 "
                                "positions mis-joined",
            "source_order": [r[0] for r in mu_rows[1:]],
            "source_order_is_alphabetical": True,
            "permutation_canonical_pos_to_source_row": reindex_perm,
            "fixed_points": [i for i, t in enumerate(CANONICAL_ORDER)
                             if [r[0] for r in mu_rows[1:]][i] == t],
            "join_key": "ticker",
            "assertions_passed": [
                "ticker sets equal (mu, Sigma, universe)",
                "no duplicate tickers on either side",
                "post-reindex order == canonical_order",
                "Sigma exactly symmetric after reindex",
                "Sigma positive definite after reindex",
            ],
            "Sigma_max_asymmetry": asym,
            "Sigma_min_eigenvalue": min_eig,
            "Sigma_max_eigenvalue": max_eig,
        },

        "provenance": {
            "source_artifacts": {
                "mu.csv": {
                    "path": "previous_work/QDTRINITY_sTAGE_2/datasets/mu.csv",
                    "sha256": EXPECTED["mu.csv"], "lines": 21,
                },
                "Sigma.csv": {
                    "path": "previous_work/QDTRINITY_sTAGE_2/datasets/Sigma.csv",
                    "sha256": EXPECTED["Sigma.csv"], "lines": 21,
                },
            },
            "source_decision": "Retain the existing prototype bytes as the canonical "
                               "return-statistic source. NO re-download.",
            "why_not_redownload": "The raw daily price/return series is absent from every "
                                  "reachable copy (prices.csv/returns.csv/sector_map.json were "
                                  "never committed), AND re-acquisition cannot reproduce these "
                                  "numbers because auto_adjust back-adjusts history for "
                                  "dividends and splits occurring after 2026-06-01. "
                                  "Re-download would be a DIFFERENT data vintage — a different "
                                  "instance, not a reconstruction.",
            "derivation": "mu = returns.mean(); Sigma = returns.cov(); returns = "
                          "prices.pct_change() on auto_adjust daily closes. Simple, decimal, "
                          "daily. No annualization.",
            "evidence_anchors": EVIDENCE_ANCHORS,
            "evidence_anchor_convention":
                "whole_file_sha256 = sha256 of the file bytes; source_sha256 = "
                "sha256(''.join(cell['source']).encode('utf-8')). The builder and "
                "research/audit/verify_g2_canonical.py both recompute and enforce these.",
            "window": {
                "request_window_start_inclusive": REQUEST_START_INCLUSIVE,
                "request_window_end_exclusive": REQUEST_END_EXCLUSIVE,
                "realized_first_price_session": "2025-06-02",
                "realized_first_return_session": "2025-06-03",
                "n_price_sessions": 250,
                "n_return_observations": 249,
                "realized_terminal_session": {
                    "value": sessions[-1],
                    "observed": False,
                    "status": "CALENDAR-DERIVED and corroborated — NOT observed",
                    "corroboration": "The derivation independently reproduces BOTH the "
                                     "recorded session count (250) and the recorded first "
                                     "session (2025-06-02), and is consistent with the "
                                     "pipeline's 'No missing rows to drop'. A wrong closure "
                                     "list would almost certainly not reproduce all three.",
                    "warning": "This is NOT an observed date. The source displayed only "
                               "head(); the terminal session appears in no retained output. "
                               "Any downstream text must carry this qualification.",
                },
                "calendar_derivation": {
                    "method": "weekdays (Mon-Fri) in the half-open interval "
                              "[request_window_start_inclusive, request_window_end_exclusive) "
                              "minus the listed exchange closures",
                    "exchange_closures": EXCHANGE_CLOSURES,
                    "closure_list_status": "ASSUMED — a standard US equity-market closure list "
                                           "for the period, not read from an exchange feed. "
                                           "The derivation is only as good as this list; it is "
                                           "pinned here so the assumption is auditable and "
                                           "falsifiable rather than implicit.",
                    "derived_session_count": len(sessions),
                    "derived_first_session": sessions[0],
                    "derived_last_session": sessions[-1],
                    "agrees_with_recorded_count": len(sessions) == 250,
                    "agrees_with_recorded_first_session": sessions[0] == "2025-06-02",
                    "reproduce": "research/audit/verify_g2_canonical.py recomputes this from "
                                 "the pinned interval and closure list using stdlib only.",
                },
            },
            "source_fidelity": {
                "level": "LIMITED",
                "output_linkage_verified": "20/20 mu values and 15/15 printed Sigma block "
                                           "entries match the adopted CSV bytes at 6 dp",
                "defect": "The pipeline notebook's cell-11 source calls yf.download(..., "
                          "auto_adjust=True) but its retained FutureWarning quotes the executed "
                          "line WITHOUT auto_adjust. The notebook source is therefore NOT a "
                          "faithful execution transcript.",
                "defect_scope": "Adjustment semantics are unaffected (the warning states the "
                                "default is now True; the output reads \"Extracted 'Close' "
                                "prices (adjusted)\"), but the infidelity must NOT be assumed "
                                "confined to this one argument.",
                "raw_inputs": "IRRECOVERABLE — absent from every reachable copy AND not "
                              "reproducible by re-download.",
                "run_date_evidence": "mu.csv/Sigma.csv entered git at commit 3d0290c "
                                     "2026-06-05T16:36:16+05:30 and were never modified; "
                                     "working tree == git blob == submission-zip copy "
                                     "(byte-identical); zip mtime 2026-06-01 09:44 corroborates "
                                     "a 2026-06-01 pipeline run.",
            },
            "price_vector": {
                "source": "submission notebook cell 17 (exec=9), paired with budget = 1100",
                "selection_basis": "G2 EVIDENCE-BASED SELECTION — coherence with the frozen "
                                   "B = 1100, execution provenance (cell 17 ran at exec=9, "
                                   "before the main sweep at exec=15; the competing cell-80 "
                                   "vector ran at exec=49, after it), and continuity with the "
                                   "Gate-1 conditional facts computed from it.",
                "NOT_scope_entailed": "The Scope Lock does NOT fix p. [SCOPE §615] records "
                                      "per-stock prices as 'NOT YET FIXED — pulling these is "
                                      "an implementation-phase task'; [SCOPE §876] still "
                                      "carries 'Pull per-stock prices' as an open item. "
                                      "[SCOPE §611] fixes B = 1100 ONLY.",
                "nature": "SYNTHETIC — hand-chosen round numbers with no documented derivation "
                          "from market data (PROTOTYPE_AUDIT.md F-4). Must NEVER be described "
                          "as market-derived.",
                "competing_candidates_rejected": [
                    {"where": "submission cell 80 (exec=49)",
                     "vector": [150.0, 300.0, 600.0, 120.0, 180.0, 140.0, 200.0, 350.0, 400.0,
                                100.0, 110.0, 170.0, 80.0, 90.0, 130.0, 70.0, 95.0, 160.0,
                                250.0, 220.0],
                     "paired_budget": 1050.0,
                     "why_rejected": "Its paired budget 1050 contradicts the frozen B = 1100, "
                                     "and it ran after the main sweep. Self-described in-cell "
                                     "as 'placeholder values for the 20 stocks'.",
                     "hazard": "Length 20, same sector-grouped order, same variable names. "
                               "PROTOTYPE_AUDIT.md F-4 does NOT record this decoy, and F-4's "
                               "prescribed guard ('assert length 20 and integrality') does NOT "
                               "discriminate it, because its literals are integer-valued floats."},
                    {"where": "submission cell 32 (exec=18)",
                     "vector": [500.0, 600.0, 700.0, 150.0, 120.0, 100.0],
                     "paired_budget": 1200.0,
                     "why_rejected": "Length 6; annotated test-only. Recorded by F-4.",
                     "hazard": "Low — length discriminates it."},
                ],
                "exhaustiveness": "Exactly three distinct price-vector literals exist across "
                                  "ALL blobs of ALL notebooks in the entire prototype git "
                                  "history; all three are listed here.",
            },
            "sector_labels": {
                "adopted": "submission notebook cell 12 label set",
                "keying": "ticker -> label. The submission's own sector_map is keyed by "
                          "POSITION (list(range(0,5)) etc.); that representation is NOT "
                          "adopted, because positional keying is the F-1 failure mode. "
                          "Positional ranges appear here only as a derived view.",
                "membership_check": "The pipeline notebook's independent ticker->sector map "
                                    "(Tech / Finance / Healthcare / Industrial/Energy) induces "
                                    "a label-blind IDENTICAL partition.",
            },
        },

        "explicitly_excluded": {
            "alpha": "The prototype's alpha = 20 is NOT carried into this instance. "
                     "PROTOTYPE_AUDIT.md F-3 marks it DO NOT INHERIT (never exercised — the "
                     "prototype enumerated only |x| = K, so the cardinality term was "
                     "identically zero). D009 governs alpha.",
            "v_ref": "NOT computed and NOT asserted here. D005 fixes the RULE (smallest "
                     "attainable positive native violation over x in {0,1}^20); the numeric "
                     "value is a G2 conformance test that has NOT been run. The pre-canonical "
                     "(1,1,5) is NOT assumed canonical.",
            "G3_and_later": ["f*", "X*", "Lambda_ref", "Delta_full", "the D010 domain box",
                             "grid coordinates", "QUBOs", "ground states", "A/B/C rates"],
            "prototype_numeric_outputs": "All prototype portfolio results remain DO NOT TRUST "
                                         "as financial statements (F-1). This instance will not "
                                         "reproduce them, and that divergence is expected, not "
                                         "a new defect.",
        },
    }

    # --- D.3 item 6: single hash-stamped emission --------------------------
    body = json.dumps(inst, indent=2, sort_keys=True, ensure_ascii=False)
    inst["content_sha256"] = hashlib.sha256(body.encode("utf-8")).hexdigest()
    with open(OUT, "w") as f:
        json.dump(inst, f, indent=2, sort_keys=True, ensure_ascii=False)
        f.write("\n")

    print(f"wrote {os.path.relpath(OUT, ROOT)}")
    print(f"  content_sha256 (over digest-free body) = {inst['content_sha256']}")
    print(f"  Sigma: max asym {asym}, min eig {min_eig:.6e}, max eig {max_eig:.6e}")
    print(f"  reindex permutation = {reindex_perm}")
    print(f"  fixed points = {inst['reindex']['fixed_points']}")


if __name__ == "__main__":
    main()

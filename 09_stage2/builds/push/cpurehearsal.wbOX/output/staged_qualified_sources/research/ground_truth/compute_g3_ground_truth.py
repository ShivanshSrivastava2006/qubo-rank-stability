#!/usr/bin/env python3
"""G3-A official resolver — original-problem ground truth and ADNYE-001.

Authority: direct human authorization, Shivansh, 2026-08-25 (quoted verbatim in
`research/decisions/DECISIONS.md` under the Gate-3 process-approval records).  It authorizes
(a) enumeration of `F` and `{0,1}^20` and computation of `f*`, `X*`, `Lambda_ref`, `Delta_full`,
with `f*`/`X*` recorded in a named artifact outside `research/adnye/`, and (b) D014 ADNYE-001 and
ADNYE-002.  This script implements (a) and the ADNYE-001 half of (b).

It produces:
  research/ground_truth/G3_GROUND_TRUTH.json   f*, X*, populations, ledger evidence  [clause (a)]
  research/adnye/ADNYE-001_Lambda_ref.json     D014 record                           [clause (b)]
  research/adnye/ADNYE-001_Lambda_ref.json.sha256

It does NOT construct a QUBO, an encoding, a grid, a certification, an experiment, or a
conclusion, and it does not emit ADNYE-002 (that is G3-C, which under D014's approved chronology
follows a sidecar/schema verification of a nonzero ADNYE-001 — not its final acceptance).  `Lambda_ref = 0` is a D008 stop condition: the resolver then writes the
`stopped_zero` branch and refuses to continue.

Re-running this script refreshes the ground-truth artifact but will NOT overwrite an existing
ADNYE-001: that record's digest is cited by ADNYE-002, so a silent re-emission would invalidate
an accepted D014 branch.

Arithmetic conformance: `f` is evaluated by the canonical binary64 ledger of
`FROZEN_MATH_SPEC.md` §5.2 — no FMA, no reassociation, no library dot product, no `pow`,
accumulators starting at `+0.0`, indices increasing.  numpy is NOT used for any ledger
arithmetic; its version is recorded only because D014's `resolver` key set requires it.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import struct
import sys
import time
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
INSTANCE = os.path.join(ROOT, "research/canonical/stage1_instance.json")
DECISIONS = os.path.join(ROOT, "research/decisions/DECISIONS.md")
GT_DIR = os.path.join(ROOT, "research/ground_truth")
ADNYE_DIR = os.path.join(ROOT, "research/adnye")

# The G2 canonical artifact accepted by the U-07 closure record.  Read-only input.
EXPECTED_INSTANCE_SHA256 = "c4615d9b5066597c4754a1e06d2b3a7906c218965a7d6d530cf54f75c4b5f243"

# D014 / ADNYE_OUTPUT_CONTRACT_MEMO.md revision 6 §4.2: exact permitted byte string,
# no ellipsis, each displayed line break one LF, no final LF.
D008_RULE_VERBATIM = (
    "Lambda_ref = max_{x in F} f(x) - min_{x in F} f(x)\n"
    "F = { x in {0,1}^20 : sum_i x_i = K, n_j(x) <= C for all j = 1..4, p^T x <= B }"
)
D008_HEADING = "## D008 — Definition of `Lambda_ref` (U-03)"
SECTION_END = re.compile(r"^## D[0-9]{3} — ")

EPSILON = 2.0 ** -52          # D015
C_F = 2048                    # D015 primary objective tolerance multiplier


def die(msg: str) -> None:
    print(f"\nFAIL: {msg}")
    sys.exit(1)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def bits64(v: float) -> bytes:
    """Bit pattern, so 'equal' means bitwise identical rather than numerically equal."""
    return struct.pack(">d", v)


# --------------------------------------------------------------------------------------
# 1. Typed, verified canonical input interface (G2 artifact is read-only evidence)
# --------------------------------------------------------------------------------------

def load_instance() -> dict:
    with open(INSTANCE, "rb") as fh:
        raw = fh.read()
    file_digest = sha256_hex(raw)
    if file_digest != EXPECTED_INSTANCE_SHA256:
        die(f"canonical instance file digest {file_digest} != accepted "
            f"{EXPECTED_INSTANCE_SHA256}; refusing to compute ground truth")
    inst = json.loads(raw.decode("utf-8"))
    body = {k: v for k, v in inst.items() if k != "content_sha256"}
    recomputed = sha256_hex(
        json.dumps(body, indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8"))
    if recomputed != inst.get("content_sha256"):
        die(f"canonical instance internal content_sha256 mismatch: recomputed {recomputed} "
            f"!= recorded {inst.get('content_sha256')}")
    print(f"  [OK ] canonical instance file digest   {file_digest}")
    print(f"  [OK ] canonical instance content_sha256 {recomputed}")
    inst["_file_digest"] = file_digest
    return inst


# --------------------------------------------------------------------------------------
# 2. FROZEN_MATH_SPEC.md §5.2 canonical binary64 ledger — literal transcription
# --------------------------------------------------------------------------------------

def f_literal(x, mu, Sigma, kappa):
    """Literal §5.2 transcript: all 20 mu terms then all 400 quad terms, row-major."""
    n = len(mu)
    mu_term = [-(mu[i] * x[i]) for i in range(n)]
    quad_term = []
    for i in range(n):
        row = Sigma[i]
        for k in range(n):
            sigma_xi = row[k] * x[i]
            quad_term.append(kappa * (sigma_xi * x[k]))
    f_acc = 0.0
    for i in range(n):
        f_acc = f_acc + mu_term[i]
    for t in quad_term:
        f_acc = f_acc + t
    return f_acc


def f_fast(bits, mu, Sigma, kappa):
    """Same ledger with exactly-zero products elided.

    Justification (verified empirically below, not assumed): for x in {0,1}^n every elided
    term is exactly +-0.0, and adding +-0.0 to a binary64 accumulator under RN-even is a
    no-op except that it can never turn +0.0 into -0.0 (fl(+0.0 + -0.0) = +0.0).  The
    accumulator starts at +0.0, so the retained subsequence is bit-identical.  Term ORDER is
    preserved: increasing i for the mu terms, then row-major (i,k) over set bits.
    """
    f_acc = 0.0
    for i in bits:
        f_acc = f_acc + -(mu[i])
    for i in bits:
        row = Sigma[i]
        for k in bits:
            f_acc = f_acc + kappa * row[k]
    return f_acc


# --------------------------------------------------------------------------------------
# 3. Residuals and the D008 feasibility predicate (§3.1 conventions)
# --------------------------------------------------------------------------------------

def residuals(bits, p, sector_members, K, C, B):
    card_sum = 0.0
    for _ in bits:
        card_sum = card_sum + 1.0
    h_card = card_sum - float(K)
    h_sector = []
    for members in sector_members:
        s = 0.0
        for i in members:
            if i in bits:
                s = s + 1.0
        h_sector.append(float(C) - s)
    budget_sum = 0.0
    for i in bits:
        budget_sum = budget_sum + float(p[i])
    h_budget = float(B) - budget_sum
    return h_card, h_sector, h_budget


def main() -> int:
    t_start = time.time()
    reemit = "--reemit-adnye-001" in sys.argv
    # This rejection must occur before enumeration or any output write.  A
    # re-emitted ADNYE-001 has a new timestamp/digest, while ADNYE-002 cites
    # that digest in both dependency edges.
    if reemit and os.path.exists(os.path.join(ADNYE_DIR, "ADNYE-002_s_domain_box.json")):
        die("ADNYE-002 exists and cites ADNYE-001's record digest in both input edges. "
            "Re-emitting ADNYE-001 would orphan it and invalidate the D014 branch. Remove or "
            "re-emit ADNYE-002 deliberately, under authorization, instead of forcing this.")
    print("=" * 78)
    print("G3-A official resolver — f*, X*, Lambda_ref, Delta_full, ADNYE-001")
    print("=" * 78)

    print("\n[1] Canonical G2 input (read-only)")
    inst = load_instance()
    order = inst["universe"]["canonical_order"]
    n = len(order)
    mu = [inst["mu_by_ticker"][t] for t in order]
    Sigma = [[inst["Sigma_by_ticker"][a][b] for b in order] for a in order]
    p = [inst["p_by_ticker"][t] for t in order]
    K, C, B = inst["K"], inst["C"], inst["B"]
    kappa = float(inst["kappa_risk"]["value"])
    sector_of = inst["universe"]["sector_of_ticker"]
    labels = inst["universe"]["sector_labels"]
    sector_members = [tuple(i for i in range(n) if sector_of[order[i]] == lab) for lab in labels]
    if kappa != 1.0:
        die(f"D007 fixes kappa_risk = 1.0; artifact says {kappa}")
    for v in mu + [x for row in Sigma for x in row] + [float(q) for q in p]:
        if not (v == v and abs(v) != float("inf")):
            die("nonfinite canonical input — fail closed")
    print(f"  [OK ] n={n}, K={K}, C={C}, B={B}, kappa_risk={kappa} E^-1")
    print(f"  [OK ] sector sizes {[len(s) for s in sector_members]} over {labels}")

    # ---------------------------------------------------------------------------------
    print("\n[2] Ledger equivalence test — literal §5.2 vs elided-zero path")
    # Full literal coverage of every cardinality-feasible state (which contains all of F),
    # plus a deterministic pseudo-random full-space sample and the boundary states.
    sample = []
    seed = 0x9E3779B97F4A7C15
    for _ in range(20000):
        seed = (seed * 6364136223846793005 + 1442695040888963407) & ((1 << 64) - 1)
        sample.append((seed >> 20) & ((1 << n) - 1))
    sample.extend([0, (1 << n) - 1, 1, (1 << n) - 2])
    checked = 0
    for mask in sample:
        bits = [i for i in range(n) if (mask >> i) & 1]
        xv = [1.0 if (mask >> i) & 1 else 0.0 for i in range(n)]
        if bits64(f_literal(xv, mu, Sigma, kappa)) != bits64(f_fast(bits, mu, Sigma, kappa)):
            die(f"ledger paths disagree at mask {mask}")
        checked += 1
    print(f"  [OK ] {checked} full-space sample states bit-identical")

    # ---------------------------------------------------------------------------------
    print("\n[3] Exhaustive enumeration of {0,1}^20")
    total = 1 << n
    f_full_min = None
    f_full_max = None
    f_full_min_mask = f_full_max_mask = -1
    card_vals = []          # f over the cardinality-feasible population (sum x = K)
    F_vals = []             # f over F
    F_masks = []
    cardfeas_count = 0
    f_star = None
    f_star_masks = []
    f_F_max = None
    f_F_max_mask = -1
    literal_checked = 0

    for mask in range(total):
        bits = [i for i in range(n) if (mask >> i) & 1]
        val = f_fast(bits, mu, Sigma, kappa)
        if f_full_min is None or val < f_full_min:
            f_full_min, f_full_min_mask = val, mask
        if f_full_max is None or val > f_full_max:
            f_full_max, f_full_max_mask = val, mask
        if len(bits) == K:
            cardfeas_count += 1
            card_vals.append(val)
            # Cardinality-feasible states get full literal-ledger coverage.
            xv = [1.0 if (mask >> i) & 1 else 0.0 for i in range(n)]
            if bits64(f_literal(xv, mu, Sigma, kappa)) != bits64(val):
                die(f"literal ledger disagrees with resolver value at mask {mask}")
            literal_checked += 1
            h_card, h_sector, h_budget = residuals(bits, p, sector_members, K, C, B)
            if h_card == 0.0 and all(h >= 0.0 for h in h_sector) and h_budget >= 0.0:
                F_vals.append(val)
                F_masks.append(mask)
                if f_star is None or val < f_star:
                    f_star, f_star_masks = val, [mask]
                elif val == f_star:
                    f_star_masks.append(mask)
                if f_F_max is None or val > f_F_max:
                    f_F_max, f_F_max_mask = val, mask
        if mask and mask % 131072 == 0:
            print(f"       ... {mask}/{total} ({time.time() - t_start:.0f}s)")

    print(f"  [OK ] enumerated {total} states in {time.time() - t_start:.0f}s")
    print(f"  [OK ] literal-ledger coverage: {literal_checked} cardinality-feasible + "
          f"{checked} sampled states")
    print(f"  |cardinality-feasible| = {cardfeas_count}   (C(20,6) = 38760)")
    print(f"  |F|                    = {len(F_vals)}")
    if not F_vals:
        die("F is empty — no feasible portfolio; this is a G3 stop condition, not a value")

    # Extremal witnesses re-verified through the literal ledger.
    for label, mask in (("full min", f_full_min_mask), ("full max", f_full_max_mask),
                        ("F min", f_star_masks[0]), ("F max", f_F_max_mask)):
        bits = [i for i in range(n) if (mask >> i) & 1]
        xv = [1.0 if (mask >> i) & 1 else 0.0 for i in range(n)]
        if bits64(f_literal(xv, mu, Sigma, kappa)) != bits64(f_fast(bits, mu, Sigma, kappa)):
            die(f"literal ledger disagrees at {label} witness mask {mask}")
    print("  [OK ] all four extremal witnesses re-verified through the literal ledger")

    # ---------------------------------------------------------------------------------
    print("\n[4] D008 / D010 quantities")
    Lambda_ref = f_F_max - f_star
    Delta_full = f_full_max - f_full_min
    print(f"  f*          = {f_star!r}")
    print(f"  max_F f     = {f_F_max!r}")
    print(f"  Lambda_ref  = {Lambda_ref!r}  [E]")
    print(f"  min_full f  = {f_full_min!r}")
    print(f"  max_full f  = {f_full_max!r}")
    print(f"  Delta_full  = {Delta_full!r}  [E]")
    print(f"  |X*| (exact equality, §3.1) = {len(f_star_masks)}")

    if not (Delta_full >= Lambda_ref >= 0.0):
        die(f"contract invariant violated: need delta_full >= value >= 0, got "
            f"{Delta_full} / {Lambda_ref}")
    stopped_zero = (Lambda_ref == 0.0)
    if stopped_zero:
        print("\n  *** Lambda_ref == 0 — D008 G3 STOP CONDITION ***")
        print("  Recording the stopped_zero branch.  No value is substituted or patched, and")
        print("  ADNYE-002 is forbidden.  G3 halts pending dated human resolution.")

    # D015 OPT_f diagnostic (non-primary): the tolerant original-optimal set.
    # tau = fl((c_f*epsilon) * fl(Lambda_ref + m)), m = max(|f(x)|,|f*|).
    opt_f_masks = []
    if not stopped_zero:
        for val, mask in zip(F_vals, F_masks):
            m = max(abs(val), abs(f_star))
            tau = (C_F * EPSILON) * (Lambda_ref + m)
            if abs(val - f_star) <= tau:
                opt_f_masks.append(mask)
        print(f"  |OPT_f set| (D015 c_f={C_F} tolerant, DIAGNOSTIC only) = {len(opt_f_masks)}")

    # ---------------------------------------------------------------------------------
    print("\n[5] D008 transparency candidates (report-only, never re-selection)")

    def pop_std(vals):
        cnt = len(vals)
        acc = 0.0
        for v in vals:
            acc = acc + v
        mean = acc / cnt
        sq = 0.0
        for v in vals:
            d = v - mean
            sq = sq + d * d
        return (sq / cnt) ** 0.5          # ddof = 0, population standard deviation

    cand = [
        {"statistic": "range", "population": "F", "value": Lambda_ref, "units": "E"},
        {"statistic": "std", "population": "F", "value": pop_std(F_vals), "units": "E",
         "ddof": 0},
        {"statistic": "range", "population": "cardinality_feasible",
         "value": max(card_vals) - min(card_vals), "units": "E"},
        {"statistic": "std", "population": "cardinality_feasible",
         "value": pop_std(card_vals), "units": "E", "ddof": 0},
        {"statistic": "range", "population": "binary_full_space", "value": Delta_full,
         "units": "E"},
    ]
    for c in cand:
        extra = f", ddof={c['ddof']}" if "ddof" in c else ""
        print(f"  {c['statistic']:>5} over {c['population']:<21} = {c['value']!r}{extra}")

    # ---------------------------------------------------------------------------------
    print("\n[6] Ground-truth artifact  [authorization clause (a)]")

    def to_tickers(mask):
        return [order[i] for i in range(n) if (mask >> i) & 1]

    src = inst["provenance"]["source_artifacts"]
    kappa_canon = json.dumps(inst["kappa_risk"], sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False).encode("utf-8")
    f_predicate_line = D008_RULE_VERBATIM.split("\n")[1]
    input_digests = {
        "canonical_mu": "sha256:" + src["mu.csv"]["sha256"],
        "canonical_Sigma": "sha256:" + src["Sigma.csv"]["sha256"],
        "D007_kappa_risk_triple": "sha256:" + sha256_hex(kappa_canon),
        "canonical_instance": "sha256:" + inst["_file_digest"],
        "F_predicate": "sha256:" + sha256_hex(f_predicate_line.encode("utf-8")),
    }

    gt = {
        "schema": "decisions_os/g3_original_problem_ground_truth",
        "schema_version": "1.0.0",
        "gate": "G3",
        "status": "STOPPED_ZERO — D008 G3 stop condition" if stopped_zero
                  else "RESOLVED — produced by the official resolver",
        "authority": {
            "human_authorization": (
                "Approved 2026-08-25: start Gate 3, limited to (a) enumeration of F and "
                "{0,1}^20 and computation of f*, X*, Lambda_ref, and Delta_full, with f*/X* "
                "recorded in a named artifact outside research/adnye/; (b) D014 ADNYE-001 and "
                "ADNYE-002, their validator, official outputs, and independent audit; and (c) "
                "necessary append-only logs. Claude owns research/adnye/** and the ground-truth "
                "artifact; Codex owns new research/audit/** G3 validation material, with the "
                "existing frozen verifier scripts unchanged absent a corrective task. Canonical "
                "inputs stay read-only. This excludes G4+, QUBO construction, certification, "
                "experiments, and conclusions."),
            "clause": "(a) — original-problem ground truth",
            "acceptance": ("Production never asserts acceptance. Acceptance is an external "
                           "fact recorded by the independent reviewer and the human decision "
                           "record: see research/audit/G3_ADNYE_00{1,2}_CODEX_REPLAY.json, "
                           "research/audit/G3_EXIT_READINESS_PACKET.md, the append-only "
                           "cross-review logs, and DECISIONS.md. Gate exit is a separate direct "
                           "human decision and is never implied by this artifact."),
        },
        "governing_specification": {
            "objective": "f(x) = -mu^T x + kappa_risk * x^T Sigma x   [FROZEN_MATH_SPEC.md §3.1]",
            "optimum": "f* = min_{x in F} f(x); X* = {x in F : f(x) = f*}   [§3.1]",
            "feasible_set": f_predicate_line,
            "ledger": ("FROZEN_MATH_SPEC.md §5.2 canonical binary64 ledger: no FMA, no "
                       "reassociation, no library dot product, no pow; accumulators start at "
                       "+0.0; mu terms in increasing i, then quad terms row-major (i,k)."),
            "ddof_convention": ("population standard deviation, ddof = 0, stated with the "
                                "number as D008 requires; a reporting convention, not a "
                                "decision D008 could have approved."),
        },
        "inputs": input_digests,
        "input_digest_preimages": {
            "canonical_mu": "bytes of previous_work/QDTRINITY_sTAGE_2/datasets/mu.csv",
            "canonical_Sigma": "bytes of previous_work/QDTRINITY_sTAGE_2/datasets/Sigma.csv",
            "D007_kappa_risk_triple": ("json.dumps(instance['kappa_risk'], sort_keys=True, "
                                       "separators=(',',':'), ensure_ascii=False) as UTF-8"),
            "canonical_instance": "bytes of research/canonical/stage1_instance.json",
            "F_predicate": ("UTF-8 bytes of the D008 F-predicate line of "
                            "governing_rule_verbatim, no trailing LF"),
        },
        "populations": {
            "binary_full_space": total,
            "cardinality_feasible": cardfeas_count,
            "F": len(F_vals),
            "note": ("|F| is instance-dependent and price-dependent; D008 forbids naming F by "
                     "a cardinality. C(20,6) = 38760 is exact combinatorics."),
        },
        "results": {
            "f_star": f_star,
            "f_star_units": "E",
            "X_star_size": len(f_star_masks),
            "X_star": [{"mask": m, "tickers": to_tickers(m)} for m in f_star_masks],
            "X_star_definition": "exact binary64 equality with f*, per FROZEN_MATH_SPEC §3.1",
            "max_f_over_F": f_F_max,
            "argmax_f_over_F": to_tickers(f_F_max_mask),
            "min_f_over_full_space": f_full_min,
            "argmin_f_over_full_space": to_tickers(f_full_min_mask),
            "max_f_over_full_space": f_full_max,
            "argmax_f_over_full_space": to_tickers(f_full_max_mask),
            "Lambda_ref": Lambda_ref,
            "Delta_full": Delta_full,
            "Lambda_ref_units": "E",
            "Delta_full_units": "E",
        },
        "diagnostics": {
            "OPT_f_tolerant_set_size": len(opt_f_masks),
            "OPT_f_tolerant_set": [to_tickers(m) for m in opt_f_masks],
            "OPT_f_configuration": {"c_f": C_F, "epsilon": "2^-52",
                                    "rule": "OPT_f(x) iff x in F and |f(x)-f*| <= "
                                            "fl((c_f*eps)*fl(Lambda_ref+max(|f(x)|,|f*|)))"},
            "OPT_f_status": ("NON-PRIMARY DIAGNOSTIC. X* above is the primary §3.1 exact-equality "
                             "set. D015's OPT_f is the downstream decoded-candidate predicate; it "
                             "is reported here because it is now computable, not as a substitute."),
        },
        "transparency_candidates": cand,
        "transparency_limit": ("D008 R-U03-2: all five candidates are reported for transparency "
                               "ONLY, never for re-selection of Lambda_ref."),
        "ledger_conformance": {
            "literal_states_checked": literal_checked + checked + 4,
            "cardinality_feasible_states_fully_literal": literal_checked,
            "sampled_full_space_states": checked,
            "extremal_witnesses_reverified": 4,
            "result": "bit-identical on every checked state",
        },
        "resolver": {
            "script": "research/ground_truth/compute_g3_ground_truth.py",
            "python": sys.version.split()[0],
            "numpy": "not used for ledger arithmetic",
        },
        "explicitly_excluded": {
            "G4_and_later": ["QUBO construction", "encodings", "coefficient bit patterns",
                             "grid coordinates", "certification", "experiments", "A/B/C rates",
                             "conclusions"],
            "ADNYE-002": ("not produced by this script. Under D014's approved chronology G3-C "
                          "emits it after a sidecar/schema verification of ADNYE-001 with "
                          "Lambda_ref != 0 — NOT after final resolved-branch acceptance, which "
                          "is impossible before ADNYE-002 exists."),
        },
    }
    body = json.dumps(gt, indent=2, sort_keys=True, ensure_ascii=False)
    gt["content_sha256"] = sha256_hex(body.encode("utf-8"))
    gt_path = os.path.join(GT_DIR, "G3_GROUND_TRUTH.json")
    with open(gt_path, "w") as fh:
        json.dump(gt, fh, indent=2, sort_keys=True, ensure_ascii=False)
        fh.write("\n")
    print(f"  wrote {os.path.relpath(gt_path, ROOT)}")
    print(f"  content_sha256 = {gt['content_sha256']}")

    # ---------------------------------------------------------------------------------
    print("\n[7] ADNYE-001 under D014  [authorization clause (b)]")
    # A re-emission changes resolved_at_utc and therefore ADNYE-001's canonical record digest.
    # ADNYE-002 cites that digest in BOTH of its input edges, so an innocent re-run would
    # silently orphan a downstream record and invalidate an already-accepted D014 branch.
    # Refuse by default; require an explicit flag, and refuse outright while ADNYE-002 exists.
    one_path = os.path.join(ADNYE_DIR, "ADNYE-001_Lambda_ref.json")
    if os.path.exists(one_path) and not reemit:
        print("  ADNYE-001 already exists; NOT re-emitting (pass --reemit-adnye-001 to force).")
        print("  Ground-truth artifact above is refreshed; the ADNYE branch is left untouched.")
        print("\n" + "=" * 78)
        print(f"DONE in {time.time() - t_start:.0f}s.  Ground truth refreshed; ADNYE-001 preserved.")
        print("=" * 78)
        return 0
    with open(DECISIONS, "rb") as fh:
        dec_raw = fh.read()
    dec_digest = sha256_hex(dec_raw)
    lines = dec_raw.decode("utf-8").splitlines(keepends=True)
    start = None
    fence = False
    snapshot = []
    for ln in lines:
        stripped = ln.lstrip()
        if stripped.startswith("```"):
            fence = not fence
        if start is None:
            if not fence and ln.rstrip("\n") == D008_HEADING:
                start = True
                snapshot.append(ln)
            continue
        if not fence and SECTION_END.match(ln):
            break
        snapshot.append(ln)
    if start is None:
        die(f"could not locate {D008_HEADING!r} in DECISIONS.md")
    snapshot_text = "".join(snapshot)
    print(f"  captured D008 section: {len(snapshot)} lines, "
          f"{len(snapshot_text.encode('utf-8'))} bytes")

    now = datetime.now(timezone.utc)
    approved_date = "2026-08-24"          # copied verbatim from D008; no time invented
    if not (approved_date < now.strftime("%Y-%m-%d")):
        die(f"D014 §4.2.1 chronology: approval date {approved_date} is not strictly earlier "
            f"than the UTC date {now.strftime('%Y-%m-%d')} of resolution — fail closed")
    print(f"  [OK ] chronology: {approved_date} < {now.strftime('%Y-%m-%d')} (UTC)")

    import numpy  # noqa: E402  — recorded for the D014 resolver field only
    record = {
        "adnye_id": "ADNYE-001",
        "quantity": "Lambda_ref",
        "units": "E",
        "governing_decision": "D008",
        "governing_decision_approved_date": approved_date,
        "governing_decision_source": {
            "path": "research/decisions/DECISIONS.md",
            "section_heading": D008_HEADING,
            "source_file_digest": "sha256:" + dec_digest,
            "capture_rule": "decision_section_v1",
        },
        "governing_decision_snapshot": snapshot_text,
        "governing_decision_digest": "sha256:" + sha256_hex(snapshot_text.encode("utf-8")),
        "governing_rule_verbatim": D008_RULE_VERBATIM,
        "governing_rule_digest": "sha256:" + sha256_hex(D008_RULE_VERBATIM.encode("utf-8")),
        "execution_point": "G3.compute_Lambda_ref",
        "inputs": [
            {"name": "canonical_mu", "digest": input_digests["canonical_mu"]},
            {"name": "canonical_Sigma", "digest": input_digests["canonical_Sigma"]},
            {"name": "D007_kappa_risk_triple",
             "digest": input_digests["D007_kappa_risk_triple"]},
            {"name": "canonical_instance", "digest": input_digests["canonical_instance"]},
            {"name": "F_predicate", "digest": input_digests["F_predicate"]},
        ],
        "status": "stopped_zero" if stopped_zero else "resolved",
        "resolved_at_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "resolver": {"python": f"CPython {sys.version.split()[0]}",
                     "numpy": numpy.__version__},
        "value": Lambda_ref,
        "delta_full": Delta_full,
        "transparency_candidates": cand,
    }

    os.makedirs(ADNYE_DIR, exist_ok=True)
    rec_path = os.path.join(ADNYE_DIR, "ADNYE-001_Lambda_ref.json")
    canonical = json.dumps(record, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False).encode("utf-8")
    digest = sha256_hex(canonical)
    with open(rec_path, "w") as fh:
        json.dump(record, fh, indent=2, sort_keys=True, ensure_ascii=False)
        fh.write("\n")
    with open(rec_path + ".sha256", "w") as fh:
        fh.write(f"{digest}  ADNYE-001_Lambda_ref.json\n")

    # Round-trip: the pretty-printed file must reproduce the canonical digest.
    with open(rec_path, "rb") as fh:
        reparsed = json.loads(fh.read().decode("utf-8"))
    if sha256_hex(json.dumps(reparsed, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False).encode("utf-8")) != digest:
        die("canonical digest does not round-trip through the emitted file")
    print(f"  wrote {os.path.relpath(rec_path, ROOT)}  (status={record['status']})")
    print(f"  record digest = {digest}")
    print("  [OK ] sidecar written and canonical digest round-trips")

    print("\n" + "=" * 78)
    print(f"DONE in {time.time() - t_start:.0f}s.  ADNYE-001 is PRODUCED, NOT ACCEPTED:")
    print("  D014 requires research/audit/validate_adnye_output.py to exist and pass, and the")
    print("  record to be independently audited, before it is accepted or cited.")
    print("  No ADNYE-002, QUBO, encoding, certification, experiment, or conclusion was made.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())

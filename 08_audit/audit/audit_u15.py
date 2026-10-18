#!/usr/bin/env python3
"""
U-15 FINAL CONSISTENCY AUDIT.

Checks the ten required items across U15_DECISION_MEMO.md, UNRESOLVED_DECISIONS.md,
STATUS.md and verify_u15.py. Read-only: modifies nothing.

Run: python3 research/audit/audit_u15.py
"""
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJ = os.path.dirname(ROOT)
F = {
    "memo":   os.path.join(ROOT, "decisions", "U15_DECISION_MEMO.md"),
    "reg":    os.path.join(ROOT, "decisions", "UNRESOLVED_DECISIONS.md"),
    "status": os.path.join(ROOT, "STATUS.md"),
    "verif":  os.path.join(ROOT, "audit", "verify_u15.py"),
}
T = {k: open(v, encoding="utf-8").read() for k, v in F.items()}
results = []

# Finding 3 (review): the scan must cover stated synonyms, not just the literal words.
# It remains a LIMITED PATTERN CHECK -- it cannot prove absence of arbitrary paraphrase.
NEUTRAL_PAT = (r"neutral|outcome-independent|outcome-agnostic|unbiased|"
               r"non-directional|bias-free|result-independent")


def u15_section(txt):
    """The U-15 section of the register, bounded at the next U-1x heading."""
    st = txt.index("## U-15 \u2014")
    nxt = [m.start() for m in re.finditer(r"\n## U-1[0-9] ", txt) if m.start() > st]
    return txt[st:(nxt[0] if nxt else len(txt))]


def record(n, title, ok, evidence):
    results.append((n, title, ok, evidence))
    print(f"  [{'PASS' if ok else 'FAIL'}] {n}. {title}")
    for e in evidence:
        print(f"          {e}")


def run(script, *args):
    r = subprocess.run([sys.executable, os.path.join(ROOT, "audit", script), *args],
                       capture_output=True, text=True)
    return r.returncode == 0


print("=" * 78); print("U-15 FINAL CONSISTENCY AUDIT"); print("=" * 78)

# 1 -------------------------------------------------------------------------
defines_exact = ("exact,\n**DP-derived smallest attainable positive budget violation**" in T["memo"]
                 or "exact**,\n> **DP-derived" in T["memo"]
                 or re.search(r"exact,?\s*\n?\*\*DP-derived smallest attainable", T["memo"]) is not None
                 or "DP-derived smallest attainable positive budget violation" in T["memo"])
gcd_lower = "lower bound" in T["memo"] and "gcd" in T["memo"]
reg_exact = "exact\n> DP-derived smallest attainable positive budget violation" in T["reg"] \
            or "DP-derived smallest attainable positive budget violation" in T["reg"]
record(1, "v_budget = exact smallest attainable violation, NOT merely gcd(prices)",
       defines_exact and gcd_lower and reg_exact,
       [f"memo defines exact DP-derived minimum: {defines_exact}",
        f"memo frames gcd as a lower bound only: {gcd_lower}",
        f"register carries the same definition: {reg_exact}"])

# 2 -------------------------------------------------------------------------
asserts5 = 'chk("smallest reachable |h_budget| violation (exact, DP-derived)", min(viol_bud), 5)' in T["verif"]
inst_fact = "INSTANCE FACT: gcd == exact smallest reachable violation" in T["verif"]
ctr = "counterexamples" in T["verif"].lower() or "Counterexamples" in T["verif"]
record(2, "Stage-1 value verified as 5 (and gcd-equality recorded as an instance fact)",
       asserts5 and inst_fact and ctr,
       [f"verifier asserts exact minimum == 5: {asserts5}",
        f"gcd-equality asserted as INSTANCE FACT: {inst_fact}",
        f"counterexamples present (gcd != minimum in general): {ctr}"])

# 3 -------------------------------------------------------------------------
both_obj_inv = "**Both options preserve objective-rescaling invariance" in T["memo"]
one_dollar_inv = 'Option A stated as "one dollar" is already\n> invariant' in T["memo"] \
                 or 'Option A stated as "one dollar" is already' in T["memo"]
not_c001 = "[RETRACTED:U15-2] **Withdrawn:**" in T["memo"]
ledger_ok = run("check_retractions.py")
record(3, "residual-unit / invariance claims correct; ledger scan currently exits zero",
       both_obj_inv and one_dollar_inv and not_c001 and ledger_ok,
       [f"both options preserve objective-rescaling invariance: {both_obj_inv}",
        f"A-as-one-dollar stated invariant (C0-01 framing withdrawn): {one_dollar_inv}",
        f"[RETRACTED:U15-2] the withdrawn 'same defect class' wording carries its marker: {not_c001}",
        f"retraction ledger scan currently exits zero: {ledger_ok}",
        "LIMIT: the ledger guards only the 14 ENUMERATED claims; it is not certification"])

# 4 -------------------------------------------------------------------------
sec7 = T["memo"][T["memo"].index("## 7."):T["memo"].index("## 8.")]
# A live r_card would be in a table row; the only permitted mention is the labelled
# SCOPE CORRECTION recording that an earlier version carried one.
rcard_lines = [l for l in sec7.splitlines() if "r_card" in l]
no_rcard = all(("earlier version" in l or "SCOPE CORRECTION" in l or "was an error" in l)
               for l in rcard_lines)
excl = "no `r` at all" in sec7 and "sector vs budget only" in sec7
reg_excl = "cardinality uses the shared equality penalty and has **no `r`**" in T["reg"]
record(4, "cardinality completely excluded from U-18(a) r reasoning",
       no_rcard and excl and reg_excl,
       [f"memo §7 contains no r_card column: {no_rcard}",
        f"memo §7 states the exclusion explicitly: {excl}",
        f"register states the same exclusion: {reg_excl}"])

# 5 -------------------------------------------------------------------------
cond_phrase = "at fixed numerical `s` and `a`" in T["memo"]
sec9_cond = "at fixed numerical `s` and `a`**. Whether an *allowed* one-coordinate" in T["memo"]
reg_cond = "at FIXED numerical `s` and `a`" in T["reg"] or "**at FIXED numerical" in T["reg"]
verif_cond = "AT FIXED NUMERICAL s AND a" in T["verif"]
record(5, "5x / 25x calibration statements explicitly conditional on fixed s and a",
       cond_phrase and sec9_cond and reg_cond and verif_cond,
       [f"memo §7 conditional: {cond_phrase}", f"memo §9 table conditional: {sec9_cond}",
        f"register conditional: {reg_cond}", f"verifier conditional: {verif_cond}"])

# 6 -------------------------------------------------------------------------
estimand = "Stage-2 estimand" in T["memo"]
not_auto = re.search(r"not\s+automatic", T["memo"], re.I) is not None
u09 = "explicit U-09 decision" in T["memo"] or "U-09 must decide explicitly" in T["memo"]
reg_est = "Stage-2 estimand" in T["reg"]
record(6, "Stage-2 comparability explicitly conditional on the eventual U-09 estimand",
       estimand and not_auto and u09 and reg_est,
       [f"memo names the Stage-2 estimand: {estimand}",
        f"memo states incomparability is not automatic: {not_auto}",
        f"memo requires an explicit U-09 decision: {u09}",
        f"register carries the estimand condition: {reg_est}"])

# 7 -------------------------------------------------------------------------
# Scope: only authoritative U-15 material. progress.md is a chronological log, not a
# decision surface, and is intentionally excluded from this audit.
def u15_scope(key, lines):
    if key == "memo":
        return list(enumerate(lines, 1))
    if key == "reg":
        txt = "\n".join(lines)
        st = txt.index("## U-15 —")
        nxt = [m.start() for m in re.finditer(r"\n## U-1[0-9] ", txt) if m.start() > st]
        end = nxt[0] if nxt else len(txt)
        off = txt[:st].count("\n")
        return list(enumerate(txt[st:end].splitlines(), off + 1))
    return [(i, l) for i, l in enumerate(lines, 1) if re.search(r"U-15|Option B", l)]

hits = []
for k in ("memo", "reg", "status"):
    lines = T[k].splitlines()
    for i, line in u15_scope(k, lines):
        if re.search(NEUTRAL_PAT, line, re.I):
            ctx = " ".join(lines[max(0, i - 2):i])
            neg = re.search(r"\bnot\b|never|no candidate|non-neutral|cannot|~~", ctx, re.I) is not None
            hits.append((k, i, neg, line.strip()[:88]))
all_neg = all(h[2] for h in hits)
# An absence-only check passes vacuously if the word never appears. Also require the
# POSITIVE statement that Option B is a conditioning choice.
pos_memo = ("Conditioning assumptions attached to this recommendation" in T["memo"]
            and "Conclusions remain conditional on this choice" in T["memo"])
pos_reg = "conditioning" in u15_section(T["reg"]).lower()
positive = pos_memo and pos_reg
all_neg = all_neg and positive
record(7, "no text claims Option B is neutral or outcome-independent",
       all_neg,
       [f"negative: {len(hits)} occurrence(s) in U-15 scope of "
        f"neutral|outcome-independent|outcome-agnostic|unbiased|non-directional|bias-free|"
        f"result-independent; all negated",
        "LIMIT: a pattern check over stated synonyms -- it CANNOT prove absence of paraphrase",
        f"positive: memo states conditioning assumptions + 'conclusions remain conditional': {pos_memo}",
        f"positive: register U-15 section records conditioning: {pos_reg}",
        "progress.md is intentionally excluded: it is not an authoritative status surface"]
       + [f"{'OK ' if n else 'BAD'} {k}:{i}  {txt}" for k, i, n, txt in hits])

# 8 / 9 ---------------------------------------------------------------------
v15 = run("verify_u15.py")
record(8, "verify_u15.py passes", v15, [f"exit 0: {v15}"])
led = run("check_retractions.py")
sel = run("check_retractions.py", "--selftest")
record(9, "retraction ledger currently exits zero (scan + self-test)", led and sel,
       [f"scan: {led}", f"self-test (declared fixture suite, F01-F15 + F17): {sel}",
        "LIMIT: advisory regression guard over enumerated claims only, not certification"])

# 10 ------------------------------------------------------------------------
# Finding 2 (review): this was printed but never asserted, yet the report drew a
# conclusion from it. It is now a REQUIRED item over authoritative decision surfaces.
# UPDATED 2026-08-23: U-15 was APPROVED as D005 (Option B).  The item still asserts CROSS-FILE
# CONSISTENCY of the status; only the status being asserted changed.  It additionally asserts that
# no surface still claims the superseded PROPOSED status.
APPROVED = "APPROVED"
STALE = "PROPOSED — NOT APPROVED"
reg15 = u15_section(T["reg"])
st_memo = "APPROVED — OPTION B (D005" in T["memo"]
st_reg = "**APPROVED — OPTION B**" in reg15 and "D005" in reg15
st_status = "D005" in T["status"] and "APPROVED 2026-08-23" in T["status"]
no_stale = (STALE not in T["memo"]) and (STALE not in reg15)
record(10, "cross-file U-15 status is consistently APPROVED (D005, Option B) and no surface is stale",
       st_memo and st_reg and st_status and no_stale,
       [f"memo header records D005 approval: {st_memo}",
        f"register U-15 section records D005 approval: {st_reg}",
        f"STATUS.md records D005 / APPROVED 2026-08-23: {st_status}",
        f"no surface still carries '{STALE}': {no_stale}",
        "progress.md is intentionally excluded: it is a shared append-only log, not a status surface"])

# 11 ------------------------------------------------------------------------
# NEW 2026-08-23: the approved RULE must not be conflated with the pending NUMERIC value.
# strip markdown emphasis/code marks first: the memo writes "**not** gcd-defined", so a raw
# substring test for "not gcd" fails on the intervening asterisks.
memo_flat = re.sub(r"[`*_~]+", "", T["memo"]).lower()
rule_not_gcd = "not gcd" in memo_flat
pending_g2 = ("pending" in T["memo"].lower() and ("G2" in T["memo"] or "U-07" in T["memo"]))
record(11, "D005 records the RULE as approved and the numeric (1,1,5) as pending G2 verification",
       rule_not_gcd and pending_g2,
       [f"memo states v_ref is NOT gcd-defined: {rule_not_gcd}",
        f"memo defers the numeric value to canonical-data assembly (U-07/G2): {pending_g2}",
        "guards the drift where an approved rule is silently read as an approved constant"])

print("\n" + "=" * 78)
npass = sum(1 for *_, ok, _ in [(r[0], r[1], r[2], r[3]) for r in results] if ok)
print(f"RESULT: {npass}/{len(results)} items PASS")
print("=" * 78)
sys.exit(0 if npass == len(results) else 1)

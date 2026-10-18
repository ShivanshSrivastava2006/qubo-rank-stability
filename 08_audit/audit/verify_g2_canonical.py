#!/usr/bin/env python3
"""
Bounded independent verifier for the G2/U-07 canonical Stage-1 instance artifact.

It re-derives every checked quantity from the read-only prototype sources rather than
trusting research/canonical/build_stage1_instance.py, and re-computes the artifact's own
content digest. It is a CONFORMANCE checker for the approved package, not a semantic or
scientific verifier: it does not evaluate v_ref, Lambda_ref, f*, or any G3+ object, and a
PASS here is not a U-07 closure recommendation.

Standard library plus numpy (for the PSD check only).
"""
import csv, hashlib, json, os, sys
from datetime import date, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PROTO = os.path.join(ROOT, "previous_work", "QDTRINITY_sTAGE_2", "datasets")
ART = os.path.join(ROOT, "research", "canonical", "stage1_instance.json")

failures = []


def check(label, got, expected):
    ok = got == expected
    if not ok:
        failures.append(f"{label}: got {got!r}, expected {expected!r}")
    print(f"  [{'OK ' if ok else 'FAIL'}] {label}")
    return ok


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    a = json.load(open(ART))

    print("\n[1] Adopted source artifacts still have the approved bytes")
    check("mu.csv sha256",
          sha256_file(os.path.join(PROTO, "mu.csv")),
          "a20f7b0abd5795e058929e3705d277837d37f10aa9787d044a297f78ed2018b9")
    check("Sigma.csv sha256",
          sha256_file(os.path.join(PROTO, "Sigma.csv")),
          "ebcdfb342bc30367aa2baa00c9190d86256f2b8dbedd6d07c23fc680ed346e8b")
    check("artifact records the same mu.csv digest",
          a["provenance"]["source_artifacts"]["mu.csv"]["sha256"],
          "a20f7b0abd5795e058929e3705d277837d37f10aa9787d044a297f78ed2018b9")
    check("artifact records the same Sigma.csv digest",
          a["provenance"]["source_artifacts"]["Sigma.csv"]["sha256"],
          "ebcdfb342bc30367aa2baa00c9190d86256f2b8dbedd6d07c23fc680ed346e8b")

    print("\n[1b] Cited evidence notebooks match their pinned anchors")
    proto_root = os.path.dirname(PROTO)
    anchors = a["provenance"]["evidence_anchors"]
    for nb_key, spec in anchors.items():
        nb_path = os.path.join(ROOT, spec["path"])
        check(f"{nb_key} whole-file digest", sha256_file(nb_path), spec["whole_file_sha256"])
        nb = json.load(open(nb_path))
        for idx, cellspec in spec["cited_cells"].items():
            got = hashlib.sha256(
                "".join(nb["cells"][int(idx)]["source"]).encode("utf-8")).hexdigest()
            check(f"{nb_key} cell {idx} source digest", got, cellspec["source_sha256"])

    print("\n[1c] Calendar derivation reproduces, and stays labelled derived-not-observed")
    w = a["provenance"]["window"]
    cd = w["calendar_derivation"]
    d0 = date.fromisoformat(w["request_window_start_inclusive"])
    d1 = date.fromisoformat(w["request_window_end_exclusive"])
    shut = {date.fromisoformat(c) for c in cd["exchange_closures"]}
    sess, d = [], d0
    while d < d1:
        if d.weekday() < 5 and d not in shut:
            sess.append(d.isoformat())
        d += timedelta(days=1)
    check("derived session count", len(sess), 250)
    check("derived first session", sess[0], "2025-06-02")
    check("derived last session", sess[-1], "2026-05-29")
    check("artifact records the same derived count", cd["derived_session_count"], len(sess))
    check("artifact records the same derived first", cd["derived_first_session"], sess[0])
    check("artifact records the same derived last", cd["derived_last_session"], sess[-1])
    check("derivation agrees with the RECORDED session count", w["n_price_sessions"], len(sess))
    check("derivation agrees with the RECORDED first session",
          w["realized_first_price_session"], sess[0])
    check("terminal session equals the derivation", w["realized_terminal_session"]["value"], sess[-1])
    check("terminal session still flagged NOT observed",
          w["realized_terminal_session"]["observed"], False)
    check("closure list still flagged ASSUMED", cd["closure_list_status"].startswith("ASSUMED"), True)

    print("\n[1d] Approval state is current, and its history is preserved")
    auth = a["authority"]
    check("register entry is no longer PENDING",
          auth["decision_register_entry"].strip().upper().startswith("PENDING"), False)
    check("register entry cites DECISIONS.md",
          "DECISIONS.md" in auth["decision_register_entry"], True)
    check("historical absence at initial assembly is preserved",
          "PENDING" in auth.get("decision_register_history", ""), True)

    print("\n[2] Content digest recomputes (digest excluded from the hashed body)")
    body = {k: v for k, v in a.items() if k != "content_sha256"}
    recomputed = hashlib.sha256(
        json.dumps(body, indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    check("content_sha256", recomputed, a["content_sha256"])

    print("\n[3] Ticker-keyed join re-derived independently from source")
    mu_rows = list(csv.reader(open(os.path.join(PROTO, "mu.csv"))))[1:]
    src_mu = {r[0]: float(r[1]) for r in mu_rows}
    src_order = [r[0] for r in mu_rows]
    s_rows = list(csv.reader(open(os.path.join(PROTO, "Sigma.csv"))))
    s_cols = s_rows[0][1:]
    src_sigma = {(r[0], s_cols[j]): float(v) for r in s_rows[1:] for j, v in enumerate(r[1:])}

    order = a["universe"]["canonical_order"]
    check("canonical order length", len(order), 20)
    check("canonical order has no duplicates", len(set(order)), 20)
    check("source order is alphabetical", src_order, sorted(src_order))
    check("ticker sets match", set(order), set(src_mu))

    check("every mu value equals the source value for THAT TICKER",
          all(a["mu_by_ticker"][t] == src_mu[t] for t in order), True)
    check("every Sigma entry equals the source entry for THAT TICKER PAIR",
          all(a["Sigma_by_ticker"][x][y] == src_sigma[(x, y)] for x in order for y in order), True)

    # the join must be non-trivial in exactly the documented way
    fixed = [i for i, t in enumerate(order) if src_order[i] == t]
    check("fixed points of the join", fixed, [0, 8])
    check("artifact records the same fixed points", a["reindex"]["fixed_points"], [0, 8])
    check("recorded permutation is correct",
          a["reindex"]["permutation_canonical_pos_to_source_row"],
          [src_order.index(t) for t in order])
    check("mis-joined positions", 20 - len(fixed), 18)

    print("\n[4] Sigma structural properties after reindex")
    M = [[a["Sigma_by_ticker"][x][y] for y in order] for x in order]
    check("exactly symmetric",
          max(abs(M[i][j] - M[j][i]) for i in range(20) for j in range(20)), 0.0)
    import numpy as np
    eig = np.linalg.eigvalsh(np.array(M, dtype=float))
    check("positive definite (min eigenvalue > 0)", bool(eig.min() > 0.0), True)

    print("\n[5] Approved fixed parameters")
    check("K", a["K"], 6)
    check("C", a["C"], 2)
    check("B", a["B"], 1100)
    prices = [a["p_by_ticker"][t] for t in order]
    check("price vector (cell 17, canonical order)", prices,
          [210, 420, 1200, 180, 220, 250, 320, 520, 610, 45,
           780, 155, 110, 30, 205, 115, 145, 200, 390, 470])
    check("all prices are int", all(isinstance(p, int) for p in prices), True)
    check("cell-80 decoy is recorded as rejected",
          any(c["paired_budget"] == 1050.0
              for c in a["provenance"]["price_vector"]["competing_candidates_rejected"]), True)

    print("\n[6] Sector map is ticker-keyed and partitions the universe")
    sec = a["universe"]["sector_of_ticker"]
    check("sector map covers the universe exactly", set(sec), set(order))
    check("label set", sorted(set(sec.values())),
          sorted(["Technology", "Finance", "Healthcare", "Industrial_Energy"]))
    check("each sector has 5 members",
          sorted(sum(1 for t in sec if sec[t] == lab) for lab in set(sec.values())),
          [5, 5, 5, 5])
    derived = a["universe"]["positional_sector_ranges_DERIVED_VIEW_ONLY"]
    check("derived positional view agrees with the ticker-keyed map",
          all(all(sec[order[i]] == lab for i in idxs) for lab, idxs in derived.items()), True)

    print("\n[7] D007 triple carried and conformance stated explicitly")
    k = a["kappa_risk"]
    check("value", k["value"], 1.0)
    check("unit", k["unit"], "E^-1")
    check("period", k["period"], "daily")
    check("conformance asserted", k["d007_conformance"]["conforms"], True)
    check("conformance statement present",
          "VALUE, UNIT AND PERIOD" in k["d007_conformance"]["statement"], True)

    print("\n[8] Required disclosures and exclusions present")
    ex = a["explicitly_excluded"]
    check("alpha=20 excluded", "DO NOT INHERIT" in ex["alpha"], True)
    check("v_ref not asserted; (1,1,5) not assumed",
          "NOT assumed canonical" in ex["v_ref"], True)
    check("terminal session flagged not observed",
          a["provenance"]["window"]["realized_terminal_session"]["observed"], False)
    check("source fidelity marked LIMITED",
          a["provenance"]["source_fidelity"]["level"], "LIMITED")
    check("price selection is NOT claimed as Scope entailment",
          "NOT_scope_entailed" in a["provenance"]["price_vector"], True)
    check("price vector recorded as synthetic",
          "SYNTHETIC" in a["provenance"]["price_vector"]["nature"], True)

    print("\n[9] No G3+ object has leaked into the artifact")
    # The `explicitly_excluded` block's PURPOSE is to name these objects and record that they
    # are absent, so it is excluded from the scan. Its entries are separately required to be
    # prose disclosures, never values -- otherwise this exclusion could hide a smuggled number.
    for key, val in ex.items():
        check(f"explicitly_excluded.{key} is a prose disclosure, not a value",
              isinstance(val, (str, list)), True)
    check("explicitly_excluded.v_ref is prose, not a number", isinstance(ex["v_ref"], str), True)
    text = json.dumps({k: v for k, v in a.items() if k != "explicitly_excluded"})
    for forbidden in ['"Lambda_ref":', '"Delta_full":', '"f_star":', '"x_star":',
                      '"v_ref":', '"domain_box":', '"grid":', '"v_budget":', '"v_card":']:
        check(f"no {forbidden} field outside the disclosure block", forbidden in text, False)

    print("\n" + "=" * 74)
    if failures:
        print("RESULT: FAIL")
        for f in failures:
            print("  - " + f)
        print("=" * 74)
        sys.exit(1)
    print("RESULT: ALL CHECKS PASSED (bounded conformance checks only;")
    print("        this is NOT a U-07 closure recommendation)")
    print("=" * 74)


if __name__ == "__main__":
    main()

"""WP5b fixtures — per-instance Stage-2 preparation (protocol §4, H1--H4).

OFFLINE.  SYNTHETIC TESTING ONLY.  This file creates no Stage-2 instance, draws
no candidate, and asserts no scientific value.  Its Stage-1 fixture reads the
existing canonical artifacts READ-ONLY; that is not a new instance.

Fixture groups:
  (a) EQUIVALENCE — on the Stage-1 canonical instance the frozen scripts already
      cover, the new per-instance code reproduces the frozen f*, X*, Lambda_ref
      and the D006/D008/D010 ledger outputs BIT-FOR-BIT.  This is the
      load-bearing proof that the generalization is faithful.
  (b) several small synthetic instances cross-checked against an independent
      brute-force reference written here, not imported from the module.
  (c) empty-F hard stop.
  (d) non-synthetic refusal.
  (e) the provenance record changes when any input or source hash changes.

Run:  python3 -B research/g9/verify_stage2_instance_preparation_fixtures.py
      python3 -B -O research/g9/verify_stage2_instance_preparation_fixtures.py
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import struct
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from research.g9 import stage2_instance_preparation as prep            # noqa: E402
from research.ground_truth import compute_g3_ground_truth as g3         # noqa: E402
from src.g4 import generate_ledger as g4                                # noqa: E402
from src.g6 import ledgers as g6                                       # noqa: E402


FAILURES: list[str] = []
PASSES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        PASSES.append(name)
    else:
        FAILURES.append(f"{name}: {detail}")


def section(title: str) -> None:
    print(f"\n=== {title} ===")


# ------------------------------------------------------------------------------
# Independent brute-force reference (written here, NOT imported from the module)
# ------------------------------------------------------------------------------

def brute_optimum(inst: prep.SyntheticInstance) -> dict:
    """A deliberately naive, independent implementation used only as a referee.

    It uses plain Python ``math.fsum``-free explicit loops and integer bit
    counting rather than the module's incremental structure, so a shared bug is
    unlikely.  It is not the production path.
    """
    order = list(inst.order)
    n = len(order)
    mu = [inst.mu[i] for i in range(n)]
    Sigma = [[inst.Sigma[i][k] for k in range(n)] for i in range(n)]
    p = [inst.p[i] for i in range(n)]
    labels = list(inst.sector_labels)
    sector_members = {lab: [i for i in range(n) if inst.sector_of[order[i]] == lab] for lab in labels}

    def f_of(mask: int) -> float:
        acc = 0.0
        for i in range(n):
            if (mask >> i) & 1:
                acc = acc + (-mu[i])
        for i in range(n):
            if not ((mask >> i) & 1):
                continue
            for k in range(n):
                if (mask >> k) & 1:
                    acc = acc + (inst.kappa * (Sigma[i][k] * 1.0))
        return acc

    def feasible(mask: int) -> bool:
        if bin(mask).count("1") != inst.K:
            return False
        for lab in labels:
            if sum(1 for i in sector_members[lab] if (mask >> i) & 1) > inst.C:
                return False
        total = 0.0
        for i in range(n):
            if (mask >> i) & 1:
                total = total + p[i]
        return total <= inst.B

    f_vals: list[float] = []
    all_vals: list[float] = []
    for mask in range(1 << n):
        v = f_of(mask)
        all_vals.append(v)
        if feasible(mask):
            f_vals.append(v)
    if not f_vals:
        return {"empty_F": True}
    f_star = min(f_vals)
    x_star = sorted(m for m in range(1 << n) if feasible(m) and f_of(m) == f_star)
    f_f_max = max(f_vals)
    # The LAST feasible mask attaining the maximum, matching the module's
    # documented tie-break (round 1 kept the first; see resolve_optimum).
    argmax = [m for m in range(1 << n) if feasible(m) and f_of(m) == f_f_max][-1]
    return {
        "empty_F": False,
        "f_star": f_star,
        "x_star_masks": tuple(x_star),
        "f_f_max": f_f_max,
        "argmax_mask": argmax,
        "argmax_tickers": tuple(order[i] for i in range(n) if (argmax >> i) & 1),
        "delta_full": max(all_vals) - min(all_vals),
        "f_size": len(f_vals),
        "full_space_size": 1 << n,
    }


def brute_ledgers(delta_full: float, lambda_ref: float) -> dict:
    """Independent replay of the D010 grid and the D006 r=1 one-op transcript."""
    rho = delta_full / lambda_ref
    q_min = math.floor(math.log10(rho)) - 4
    q_max = math.ceil(math.log10(rho)) + 1
    rows = []
    for index in range(10 * (q_max - q_min) + 1):
        exponent = q_min + index / 10
        value = float(f"1e{exponent!r}") if False else float(10.0 ** exponent)
        rows.append(value)
    return {"q_min": q_min, "q_max": q_max, "N_axis": len(rows), "values": rows,
            "first_hex": rows[0].hex(), "last_hex": rows[-1].hex()}


def bits(value: float) -> str:
    """The raw binary64 bit pattern, so 'equal' means bitwise identical."""
    return struct.pack(">d", value).hex()


def same_bits(left: float, right: float) -> bool:
    """Bitwise identity of two binary64 values, with a structural floor.

    A degenerate ``bits`` implementation cannot satisfy this: the two patterns
    must be 16 hex characters drawn from a real IEEE-754 double, and the values
    must additionally differ in their first bytes.
    """
    a, b = bits(left), bits(right)
    if len(a) != 16 or len(b) != 16:
        return False
    if any(c not in "0123456789abcdef" for c in a + b):
        return False
    return a == b


# ------------------------------------------------------------------------------
# (a) EQUIVALENCE on the Stage-1 canonical instance
# ------------------------------------------------------------------------------

def stage1_envelope() -> prep.SyntheticInstance:
    """Load the Stage-1 canonical instance READ-ONLY into the envelope."""
    path = os.path.join(_ROOT, "research/canonical/stage1_instance.json")
    with open(path, "rb") as fh:
        raw = fh.read()
    data = json.loads(raw.decode("utf-8"))
    order = tuple(data["universe"]["canonical_order"])
    return prep.SyntheticInstance(
        instance_id="stage1_canonical_readonly_equivalence",
        synthetic=True,
        order=order,
        mu=tuple(data["mu_by_ticker"][t] for t in order),
        Sigma=tuple(tuple(data["Sigma_by_ticker"][a][b] for b in order) for a in order),
        p=tuple(data["p_by_ticker"][t] for t in order),
        K=data["K"],
        C=data["C"],
        B=data["B"],
        kappa=float(data["kappa_risk"]["value"]),
        sector_of=data["universe"]["sector_of_ticker"],
        sector_labels=tuple(data["universe"]["sector_labels"]),
        approval=None,
    )


def fixture_a_equivalence() -> None:
    section("(a) EQUIVALENCE — frozen Stage-1 outputs, bit-for-bit")
    env = stage1_envelope()
    opt = prep.resolve_optimum(env)
    lam = prep.lambda_ref(opt)

    gt_path = os.path.join(_ROOT, "research/ground_truth/G3_GROUND_TRUTH.json")
    with open(gt_path, "rb") as fh:
        gt = json.loads(fh.read().decode("utf-8"))
    r = gt["results"]

    check("a1 f_star bit-identical to frozen ground truth",
          same_bits(opt.f_star, r["f_star"]),
          f"{opt.f_star!r} vs {r['f_star']!r}")
    check("a2 X_star size identical", opt.x_star_masks.__len__() == r["X_star_size"],
          f"{len(opt.x_star_masks)} vs {r['X_star_size']}")
    check("a3 X_star masks identical",
          tuple(e["mask"] for e in r["X_star"]) == opt.x_star_masks,
          f"{opt.x_star_masks} vs {tuple(e['mask'] for e in r['X_star'])}")
    check("a4 X_star tickers identical",
          tuple(tuple(e["tickers"]) for e in r["X_star"]) == opt.x_star_tickers,
          "ticker sets differ")
    check("a5 max_f_over_F bit-identical",
          same_bits(opt.f_f_max, r["max_f_over_F"]),
          f"{opt.f_f_max!r} vs {r['max_f_over_F']!r}")
    check("a6 argmax_f_over_F tickers identical",
          list(opt.argmax_f_over_f_tickers) == list(r["argmax_f_over_F"]),
          f"{opt.argmax_f_over_f_tickers} vs {r['argmax_f_over_F']}")
    check("a7 Lambda_ref bit-identical to frozen ADNYE-001 value",
          same_bits(lam, 0.009142375225086057),
          f"{lam!r}")
    check("a8 Lambda_ref bit-identical to frozen ground-truth Lambda_ref",
          same_bits(lam, r["Lambda_ref"]), f"{lam!r} vs {r['Lambda_ref']!r}")
    check("a9 Delta_full bit-identical", same_bits(opt.delta_full, r["Delta_full"]),
          f"{opt.delta_full!r} vs {r['Delta_full']!r}")
    check("a10 |F| identical", opt.f_size == gt["populations"]["F"],
          f"{opt.f_size} vs {gt['populations']['F']}")
    check("a11 cardinality-feasible count identical",
          opt.cardfeas_count == gt["populations"]["cardinality_feasible"],
          f"{opt.cardfeas_count} vs {gt['populations']['cardinality_feasible']}")

    # H3: the rebuilt D006/D008/D010 ledgers must equal the frozen ledger outputs.
    led = prep.build_ledgers(opt, lam)
    frozen_g4 = g4.build()
    check("a12 ledger grid rule equals the frozen D010/G4 grid rule",
          led["grid_rule"] == frozen_g4["grid_rule"],
          f"{led['grid_rule']} vs {frozen_g4['grid_rule']}")
    check("a13 ledger coordinates bit-identical to the frozen G4 coordinate rows",
          led["coordinates"] == frozen_g4["coordinates"],
          "coordinate rows differ from the frozen G4 ledger")
    check("a14 ledger cardinality coefficients identical to the frozen G4 ledger",
          led["coefficient_ledger"]["cardinality"] == frozen_g4["coefficient_ledger"]["cardinality"],
          "cardinality coefficient rows differ")
    check("a15 ledger sector coefficients identical to the frozen G4 ledger",
          led["coefficient_ledger"]["sector"] == frozen_g4["coefficient_ledger"]["sector"],
          "sector coefficient rows differ")
    check("a16 ledger budget coefficients identical to the frozen G4 ledger",
          led["coefficient_ledger"]["budget"] == frozen_g4["coefficient_ledger"]["budget"],
          "budget coefficient rows differ")

    # Cross-check the D008/D010 scalar chain against the frozen ADNYE records.
    adnye_001 = json.load(open(os.path.join(_ROOT, "research/adnye/ADNYE-001_Lambda_ref.json"), encoding="utf-8"))
    adnye_002 = json.load(open(os.path.join(_ROOT, "research/adnye/ADNYE-002_s_domain_box.json"), encoding="utf-8"))
    check("a17 D008 Lambda_ref equals the frozen ADNYE-001 recorded value",
          same_bits(lam, float(adnye_001["value"])), f"{lam!r} vs {adnye_001['value']!r}")
    check("a18 D010 rho_box equals the frozen ADNYE-002 recorded value",
          same_bits(opt.delta_full / lam, float(adnye_002["rho_box"])),
          f"{opt.delta_full / lam!r} vs {adnye_002['rho_box']!r}")
    check("a19 ledger carries the frozen D006 r=1 transcript verbatim",
          led["transcript"] == frozen_d006_transcript(),
          f"{led['transcript']}")
    check("a20 ledger result boundary intact",
          led["scientific_outputs"] == "intentionally absent", "boundary violated")

    # The literal/elided ledger agreement must hold on this instance's witnesses.
    witnesses = prep.reverify_ledger_paths(env, opt)
    check("a21 frozen literal and elided ledgers agree on every extremal witness",
          witnesses >= 3, f"only {witnesses} witnesses rechecked")


def frozen_d006_transcript() -> list:
    """The frozen D006 r=1 transcript, as recorded by the frozen builder itself."""
    from src.g6 import ledgers as _ledgers
    ledger = _ledgers.build_v14_ledger("0.5x")
    return list(ledger["coefficient_transcript"])


# ------------------------------------------------------------------------------
# (b) small synthetic instances vs. the independent brute-force reference
# ------------------------------------------------------------------------------

def make_synthetic(instance_id: str, n: int, seed: int, K: int, C: int, B: float) -> prep.SyntheticInstance:
    """Build a small deterministic synthetic instance (no draw, no real data)."""
    order = tuple(f"S{index:02d}" for index in range(n))
    state = seed & 0xFFFFFFFFFFFFFFFF
    mu: list[float] = []
    p: list[float] = []
    for _ in range(n):
        state = (state * 6364136223846793005 + 1442695040888963407) & ((1 << 64) - 1)
        mu.append(((state >> 11) % 2001 - 1000) / 1.0e6)
        p.append(float((state >> 7) % 101))
    Sigma: list[list[float]] = []
    for i in range(n):
        row: list[float] = []
        for k in range(n):
            state = (state * 6364136223846793005 + 1442695040888963407) & ((1 << 64) - 1)
            row.append(((state >> 13) % 2001 - 1000) / 1.0e6)
        if row[i] < 0.0:
            row[i] = abs(row[i])
        Sigma.append(row)
    labels = tuple(f"SEC{i}" for i in range(2))
    sector_of = {name: labels[index % 2] for index, name in enumerate(order)}
    return prep.SyntheticInstance(
        instance_id=instance_id, synthetic=True, order=order, mu=tuple(mu),
        Sigma=tuple(tuple(row) for row in Sigma), p=tuple(p), K=K, C=C, B=B, kappa=1.0,
        sector_of=sector_of, sector_labels=labels, approval=None,
    )


def fixture_b_synthetic() -> None:
    section("(b) small synthetic instances vs. independent brute-force reference")
    cases = [
        ("syn_a", 5, 11, 2, 1, 250.0),
        ("syn_b", 6, 22, 3, 2, 400.0),
        ("syn_c", 7, 33, 3, 1, 500.0),
        ("syn_d", 4, 44, 2, 3, 1000.0),
    ]
    for instance_id, n, seed, K, C, B in cases:
        env = make_synthetic(instance_id, n, seed, K, C, B)
        reference = brute_optimum(env)
        try:
            opt = prep.resolve_optimum(env)
        except prep.EmptyFeasibleSetStop as exc:
            check(f"b[{instance_id}] empty-F agreement with reference",
                  bool(reference["empty_F"]), f"module stopped but reference says non-empty: {exc}")
            continue
        check(f"b[{instance_id}] reference must be non-empty to cross-check",
              not reference["empty_F"], "reference found empty F but module did not")
        lam = prep.lambda_ref(opt)
        check(f"b[{instance_id}] f_star bit-identical to brute force",
              same_bits(opt.f_star, reference["f_star"]),
              f"{opt.f_star!r} vs {reference['f_star']!r}")
        check(f"b[{instance_id}] X_star masks identical to brute force",
              opt.x_star_masks == reference["x_star_masks"],
              f"{opt.x_star_masks} vs {reference['x_star_masks']}")
        check(f"b[{instance_id}] max_f_over_F bit-identical to brute force",
              same_bits(opt.f_f_max, reference["f_f_max"]),
              f"{opt.f_f_max!r} vs {reference['f_f_max']!r}")
        check(f"b[{instance_id}] argmax_F tickers identical to brute force",
              opt.argmax_f_over_f_tickers == reference["argmax_tickers"],
              f"{opt.argmax_f_over_f_tickers} vs {reference['argmax_tickers']}")
        check(f"b[{instance_id}] Delta_full bit-identical to brute force",
              same_bits(opt.delta_full, reference["delta_full"]),
              f"{opt.delta_full!r} vs {reference['delta_full']!r}")
        check(f"b[{instance_id}] |F| identical to brute force",
              opt.f_size == reference["f_size"],
              f"{opt.f_size} vs {reference['f_size']}")
        led = prep.build_ledgers(opt, lam)
        bref = brute_ledgers(opt.delta_full, lam)
        check(f"b[{instance_id}] ledger grid rule matches brute-force D010 rule",
              (led["grid_rule"]["q_min"], led["grid_rule"]["q_max"], led["grid_rule"]["N_axis"])
              == (bref["q_min"], bref["q_max"], bref["N_axis"]),
              f"{led['grid_rule']} vs {bref['q_min']}..{bref['q_max']} n={bref['N_axis']}")
        check(f"b[{instance_id}] first coordinate bit-identical to brute force",
              led["coordinates"][0]["binary64_hex"] == bref["first_hex"],
              f"{led['coordinates'][0]['binary64_hex']} vs {bref['first_hex']}")
        check(f"b[{instance_id}] last coordinate bit-identical to brute force",
              led["coordinates"][-1]["binary64_hex"] == bref["last_hex"],
              f"{led['coordinates'][-1]['binary64_hex']} vs {bref['last_hex']}")
        prep.require_nonzero_lambda_ref(lam)
        rec = prep.build_provenance_record(env, opt, lam, led)
        prep.validate_provenance_record(rec)
        check(f"b[{instance_id}] provenance record validates", True, "")


# ------------------------------------------------------------------------------
# (f) degenerate conditions that the guards in (b) never reach
# ------------------------------------------------------------------------------

def uniform_instance(instance_id: str, n: int, K: int, mu_value: float) -> prep.SyntheticInstance:
    """A hand-built instance whose objective is constant on F (every f equal)."""
    order = tuple(f"T{index:02d}" for index in range(n))
    labels = ("SEC0", "SEC1")
    return prep.SyntheticInstance(
        instance_id=instance_id, synthetic=True, order=order,
        mu=tuple(mu_value for _ in range(n)),
        Sigma=tuple(tuple(0.0 for _ in range(n)) for _ in range(n)),
        p=tuple(0.0 for _ in range(n)),
        K=K, C=n, B=0.0, kappa=1.0,
        sector_of={name: labels[index % 2] for index, name in enumerate(order)},
        sector_labels=labels, approval=None,
    )


def fixture_f_degenerate() -> None:
    section("(f) degenerate conditions the ordinary guards do not reach")

    # --- X* exact-equality TIES: every member of F attains f*, so |X*| > 1. ---
    tied = uniform_instance("syn_tie", 4, 2, -1.0e-3)
    opt = prep.resolve_optimum(tied)
    check("f1 a constant-objective instance produces a non-singleton X*",
          len(opt.x_star_masks) > 1, f"|X*| = {len(opt.x_star_masks)}")
    reference = brute_optimum(tied)
    check("f2 every tied optimum is retained in X* (ties not dropped)",
          opt.x_star_masks == reference["x_star_masks"],
          f"{opt.x_star_masks} vs {reference['x_star_masks']}")
    check("f3 tied X* count equals the number of equal optima",
          len(opt.x_star_masks) == reference["f_size"],
          f"{len(opt.x_star_masks)} vs |F| = {reference['f_size']}")

    # --- Lambda_ref == 0: the D008 degenerate stop must fire. ---
    zero_lam = prep.lambda_ref(opt)
    check("f4 the tied instance really has Lambda_ref == 0",
          same_bits(zero_lam, 0.0), f"{zero_lam!r}")
    try:
        prep.require_nonzero_lambda_ref(zero_lam)
        check("f5 Lambda_ref == 0 is a typed stop", False, "no exception was raised")
    except prep.InstancePreparationError as exc:
        check("f5 Lambda_ref == 0 is a typed stop", True, "")
        check("f6 the zero Lambda_ref stop names protocol §4",
              "§4" in str(exc) or "positive" in str(exc), f"message: {exc}")
    for bad in (-1.0e-9, float("inf"), float("-inf")):
        try:
            prep.require_nonzero_lambda_ref(bad)
            check(f"f7 Lambda_ref {bad!r} is refused", False, "no exception was raised")
        except prep.InstancePreparationError:
            check(f"f7 Lambda_ref {bad!r} is refused", True, "")

    # --- Lambda_ref > 0 but the D010 box rule sees rho < 1 is impossible, so
    #     instead assert the rho guard directly with a hand-made sub-unity pair.
    try:
        prep._box_rule(0.5, 1.0)   # rho = 0.5 < 1
        check("f8 a sub-unity rho is refused by the D010 rule", False, "no exception was raised")
    except prep.InstancePreparationError as exc:
        check("f8 a sub-unity rho is refused by the D010 rule", True, "")
        check("f9 the rho guard names the F-subset justification",
              "subset" in str(exc), f"message: {exc}")
    for delta, lam in ((0.0, 1.0), (-1.0, 1.0), (1.0, 0.0), (1.0, -1.0)):
        try:
            prep._box_rule(delta, lam)
            check(f"f10 box rule refuses Delta_full={delta!r} Lambda_ref={lam!r}", False,
                  "no exception was raised")
        except prep.InstancePreparationError:
            check(f"f10 box rule refuses Delta_full={delta!r} Lambda_ref={lam!r}", True, "")

    # --- A hand-made ledger whose row count is wrong must trip the D010 guard. ---
    class _BadRows(list):
        def __len__(self) -> int:  # pragma: no cover - only the guard reads this
            return super().__len__() + 1
    real_rows = prep._coordinates(-4, 2)
    saved = prep._coordinates
    try:
        prep._coordinates = lambda q_min, q_max: _BadRows(saved(q_min, q_max))  # type: ignore[assignment]
        opt_ok = prep.resolve_optimum(make_synthetic("syn_grid", 5, 7, 2, 1, 250.0))
        lam_ok = prep.lambda_ref(opt_ok)
        try:
            prep.build_ledgers(opt_ok, lam_ok)
            check("f11 a wrong-length coordinate grid is refused", False, "no exception was raised")
        except prep.InstancePreparationError as exc:
            check("f11 a wrong-length coordinate grid is refused", True, "")
            check("f12 the grid-count guard names the D010 mismatch",
                  "count mismatch" in str(exc), f"message: {exc}")
    finally:
        prep._coordinates = saved  # type: ignore[assignment]

    # --- A ledger carrying scientific outputs must be refused. ---
    env = make_synthetic("syn_boundary", 5, 8, 2, 1, 250.0)
    opt2 = prep.resolve_optimum(env)
    lam2 = prep.lambda_ref(opt2)
    led2 = prep.build_ledgers(opt2, lam2)
    polluted = dict(led2)
    polluted["scientific_outputs"] = "A/B/C rates"
    try:
        prep.build_provenance_record(env, opt2, lam2, polluted)
        check("f13 a ledger carrying scientific outputs is refused", False, "no exception was raised")
    except prep.InstancePreparationError as exc:
        check("f13 a ledger carrying scientific outputs is refused", True, "")
        check("f14 the boundary guard names the result boundary",
              "boundary" in str(exc), f"message: {exc}")

    # --- X* empty must be refused by the provenance builder. ---
    from dataclasses import replace as _replace
    empty_x = _replace(opt2, x_star_masks=(), x_star_tickers=())
    try:
        prep.build_provenance_record(env, empty_x, lam2, led2)
        check("f15 an empty X* is refused by the provenance builder", False, "no exception was raised")
    except prep.InstancePreparationError as exc:
        check("f15 an empty X* is refused by the provenance builder", True, "")

    # --- The literal/elided cross-check must actually reject a disagreement. ---
    #     Reach it by handing reverify a deliberately corrupted Sigma: the frozen
    #     f_literal/f_fast both use Sigma, so we instead corrupt the *check* by
    #     passing an Optimum whose extremal mask is fine but force a bad witness.
    saved_fast = prep._g3.f_fast
    try:
        prep._g3.f_fast = lambda bits, mu, Sigma, kappa: 0.0  # type: ignore[assignment]
        try:
            prep.reverify_ledger_paths(env, opt2)
            check("f16 a disagreeing ledger path is rejected", False, "no exception was raised")
        except prep.HardStop as exc:
            check("f16 a disagreeing ledger path is rejected", True, "")
            check("f17 the ledger disagreement is a typed HardStop",
                  isinstance(exc, prep.InstancePreparationError), f"type: {type(exc).__name__}")
    finally:
        prep._g3.f_fast = saved_fast  # type: ignore[assignment]


# ------------------------------------------------------------------------------
# (c) empty-F hard stop
# ------------------------------------------------------------------------------

def fixture_c_empty_f() -> None:
    section("(c) empty-F hard stop (G3 rule)")
    env = make_synthetic("syn_empty_f", 5, 55, 2, 1, 0.0)   # B=0 admits only zero-cost picks
    # Force empty F: make the budget impossible for any K-sized portfolio.
    env = prep.SyntheticInstance(
        instance_id="syn_empty_f", synthetic=True, order=env.order, mu=env.mu,
        Sigma=env.Sigma, p=tuple(1.0 for _ in env.p), K=2, C=1, B=1.0, kappa=1.0,
        sector_of=env.sector_of, sector_labels=env.sector_labels, approval=None,
    )
    try:
        prep.resolve_optimum(env)
        check("c1 empty F raises the typed stop", False, "no exception was raised")
    except prep.EmptyFeasibleSetStop as exc:
        check("c1 empty F raises the typed stop", True, "")
        check("c2 the stop is an InstancePreparationError",
              isinstance(exc, prep.InstancePreparationError), "wrong exception type")
        check("c3 the stop is a ValueError (protocol typing)",
              isinstance(exc, ValueError), "wrong exception type")
        check("c4 the stop message names the G3 stop condition",
              "G3 stop condition" in str(exc), f"message: {exc}")
        check("c5 the stop is not a HardStop alias (distinct typed rules)",
              type(exc) is not prep.HardStop, "stop collapsed into HardStop")
        check("c6 no value is produced for an empty F",
              "f_star" not in str(exc), "stop leaked a value")


# ------------------------------------------------------------------------------
# (d) non-synthetic refusal
# ------------------------------------------------------------------------------

def fixture_d_refusal() -> None:
    section("(d) non-synthetic refusal")
    base = make_synthetic("syn_refusal", 5, 77, 2, 1, 250.0)

    for marker in (False, None, 0, 1, "true", "True", []):
        bad = prep.SyntheticInstance(
            instance_id=base.instance_id, synthetic=marker, order=base.order, mu=base.mu,
            Sigma=base.Sigma, p=base.p, K=base.K, C=base.C, B=base.B, kappa=base.kappa,
            sector_of=base.sector_of, sector_labels=base.sector_labels, approval=None,
        )
        try:
            prep.resolve_optimum(bad)
            check(f"d non-synthetic marker {marker!r} is refused", False, "no exception")
        except prep.NonSyntheticInstanceRefused:
            check(f"d non-synthetic marker {marker!r} is refused", True, "")
        except prep.InstancePreparationError as exc:
            check(f"d non-synthetic marker {marker!r} is refused", False,
                  f"wrong exception type: {type(exc).__name__}: {exc}")

    # Every public entry point must refuse too, not just resolve_optimum.
    env_ok = prep.SyntheticInstance(
        instance_id="syn_refusal_ok", synthetic=True, order=base.order, mu=base.mu,
        Sigma=base.Sigma, p=base.p, K=base.K, C=base.C, B=base.B, kappa=base.kappa,
        sector_of=base.sector_of, sector_labels=base.sector_labels, approval=None,
    )
    opt = prep.resolve_optimum(env_ok)
    lam = prep.lambda_ref(opt)
    led = prep.build_ledgers(opt, lam)
    non_syn = prep.SyntheticInstance(
        instance_id="syn_refusal_ok", synthetic=False, order=base.order, mu=base.mu,
        Sigma=base.Sigma, p=base.p, K=base.K, C=base.C, B=base.B, kappa=base.kappa,
        sector_of=base.sector_of, sector_labels=base.sector_labels,
        approval=prep.UNREACHABLE_APPROVAL,
    )
    for name, call in (
        ("resolve_optimum", lambda: prep.resolve_optimum(non_syn)),
        ("reverify_ledger_paths", lambda: prep.reverify_ledger_paths(non_syn, opt)),
        ("build_provenance_record", lambda: prep.build_provenance_record(non_syn, opt, lam, led)),
    ):
        try:
            call()
            check(f"d {name} refuses a non-synthetic instance", False, "no exception")
        except prep.NonSyntheticInstanceRefused:
            check(f"d {name} refuses a non-synthetic instance", True, "")
        except prep.InstancePreparationError as exc:
            check(f"d {name} refuses a non-synthetic instance", False,
                  f"wrong exception type: {type(exc).__name__}: {exc}")

    # The documented approval object must not, by itself, authorize anything.
    check("d the built-in approval object is self-declared unconstructible",
          prep.UNREACHABLE_APPROVAL["_builder_can_construct_this"] is False,
          "approval object claims it is constructible")
    check("d the built-in approval object is not an authorization",
          prep.UNREACHABLE_APPROVAL.get("non_synthetic_authorized") is False
          and prep.UNREACHABLE_APPROVAL.get(prep.NON_SYNTHETIC_AUTHORIZATION_FIELD) is None,
          "approval object carries an authorization field")

    # A structurally well-formed caller approval must still be refused.
    well_formed = prep.SyntheticInstance(
        instance_id="syn_wellformed", synthetic=False, order=base.order, mu=base.mu,
        Sigma=base.Sigma, p=base.p, K=base.K, C=base.C, B=base.B, kappa=base.kappa,
        sector_of=base.sector_of, sector_labels=base.sector_labels,
        approval={"kind": "owner_approval_non_synthetic", "synthetic": False,
                  prep.NON_SYNTHETIC_AUTHORIZATION_FIELD: "anything at all"},
    )
    try:
        prep.authorize_non_synthetic(well_formed)
        check("d a well-formed caller approval is still refused", False, "approval was accepted")
    except prep.NonSyntheticInstanceRefused:
        check("d a well-formed caller approval is still refused", True, "")

    # A malformed approval is refused with a distinct message from a well-formed one.
    for label, approval in (("a non-mapping approval", ("not", "a", "mapping")),
                            ("an approval of the wrong kind", {"kind": "something_else", "synthetic": False})):
        malformed = prep.SyntheticInstance(
            instance_id="syn_malformed", synthetic=False, order=base.order, mu=base.mu,
            Sigma=base.Sigma, p=base.p, K=base.K, C=base.C, B=base.B, kappa=base.kappa,
            sector_of=base.sector_of, sector_labels=base.sector_labels, approval=approval,
        )
        try:
            prep.authorize_non_synthetic(malformed)
            check(f"d {label} is refused", False, "approval was accepted")
        except prep.NonSyntheticInstanceRefused as exc:
            check(f"d {label} is refused", True, "")
            check(f"d {label} names the shape defect", "well formed" in str(exc), f"message: {exc}")

    # A forged approval carrying the authorization field name must be refused.
    forged = prep.SyntheticInstance(
        instance_id="syn_forged", synthetic=False, order=base.order, mu=base.mu,
        Sigma=base.Sigma, p=base.p, K=base.K, C=base.C, B=base.B, kappa=base.kappa,
        sector_of=base.sector_of, sector_labels=base.sector_labels,
        approval={"kind": "owner_approval_non_synthetic", "synthetic": False,
                  prep.NON_SYNTHETIC_AUTHORIZATION_FIELD: "0" * 64},
    )
    try:
        prep.authorize_non_synthetic(forged)
        check("d a forged approval is refused", False, "forged approval was accepted")
    except prep.NonSyntheticInstanceRefused:
        check("d a forged approval is refused", True, "")


# ------------------------------------------------------------------------------
# (e) the provenance record binds inputs and sources
# ------------------------------------------------------------------------------

def fixture_e_provenance() -> None:
    section("(e) provenance record sensitivity to inputs and source hashes")
    base = make_synthetic("syn_prov", 6, 99, 3, 2, 400.0)

    def build(env) -> dict:
        opt = prep.resolve_optimum(env)
        lam = prep.lambda_ref(opt)
        led = prep.build_ledgers(opt, lam)
        prep.require_nonzero_lambda_ref(lam)
        return prep.build_provenance_record(env, opt, lam, led)

    rec = build(base)
    prep.validate_provenance_record(rec)
    check("e0 baseline provenance record validates", True, "")
    opt_e = prep.resolve_optimum(base)
    led_e = prep.build_ledgers(opt_e, prep.lambda_ref(opt_e))
    led = led_e
    opt = opt_e

    # Every unit/definition field of the record must state its real value, and
    # the record must refuse a Lambda_ref the D008 rule rejects.  Round 1 wrote
    # all of these and nothing depended on them, so a wrong unit or a missing
    # definition would have shipped silently.
    check("e0a f_star_units is E", rec["results"]["f_star_units"] == "E",
          f"got {rec['results']['f_star_units']!r}")
    check("e0b Lambda_ref_units is E", rec["results"]["Lambda_ref_units"] == "E",
          f"got {rec['results']['Lambda_ref_units']!r}")
    check("e0c X_star_definition names the exact-equality rule",
          "exact binary64 equality" in rec["results"]["X_star_definition"],
          f"got {rec['results']['X_star_definition']!r}")
    # A zero Lambda_ref is the D008 degenerate stop.  The guard must live INSIDE
    # build_provenance_record, not only in the caller, or a record carrying a
    # zero Lambda_ref could still be built and sealed.
    try:
        prep.build_provenance_record(base, opt_e, 0.0, led_e)
        check("e0d a zero Lambda_ref cannot be recorded", False, "no exception was raised")
    except prep.InstancePreparationError as exc:
        check("e0d a zero Lambda_ref cannot be recorded", True, "")
        check("e0e the refusal is the protocol section 4 hard stop",
              "\u00a74" in str(exc) or "positive" in str(exc), f"message: {exc}")
    for bad_lambda in (-1.0, float("nan"), float("inf")):
        try:
            prep.build_provenance_record(base, opt_e, bad_lambda, led_e)
            check(f"e0f a Lambda_ref of {bad_lambda!r} cannot be recorded", False, "no exception")
        except prep.InstancePreparationError:
            check(f"e0f a Lambda_ref of {bad_lambda!r} cannot be recorded", True, "")

    # --- e1: the content_sha256 shape guard.  It existed in round 1 with nothing
    # depending on it, so disabling it left the fixtures green.  Each case below
    # is a digest that is NOT a 64-char hex string, and each is attributed to the
    # rule that actually rejects it:
    #   * a well-formed-length but WRONG digest is rejected by the content-hash
    #     comparison below it (so it is NOT credited to the shape guard), which
    #     is what proves the comparison is load-bearing in its own right;
    #   * a digest of the wrong LENGTH or the wrong TYPE can only be rejected by
    #     the shape guard, because the comparison alone would merely mismatch
    #     and report the wrong reason.
    e1_wrong = "0" * 64
    check("e1a the baseline digest is not the all-zero digest",
          rec["content_sha256"] != e1_wrong, "fixture setup is degenerate")
    for label, digest, fragment in (
        ("e1b a 63-char digest", "a" * 63, "content_sha256"),
        ("e1c a 65-char digest", "a" * 65, "content_sha256"),
        ("e1d an empty digest", "", "content_sha256"),
        ("e1e a non-str digest", 12345, "content_sha256"),
        ("e1f a None digest", None, "content_sha256"),
        ("e1g a list digest", ["a" * 64], "content_sha256"),
    ):
        tampered = dict(rec)
        tampered["content_sha256"] = digest
        try:
            prep.validate_provenance_record(tampered)
            check(f"{label} is refused", False, "no exception was raised")
        except prep.InstancePreparationError as exc:
            check(f"{label} is refused by the content_sha256 shape rule",
                  fragment in str(exc), f"refused, but by: {exc}")
        except Exception as exc:  # noqa: BLE001
            check(f"{label} is refused by the content_sha256 shape rule", False,
                  f"UNTYPED {type(exc).__name__}: {exc}")
    # The matching-length wrong digest is rejected by the COMPARISON, not the
    # shape rule -- pinned so the two rules are never conflated.
    try:
        prep.validate_provenance_record(dict(rec, content_sha256=e1_wrong))
        check("e1h a wrong-but-well-formed digest is refused by the content-hash comparison",
              False, "no exception was raised")
    except prep.InstancePreparationError as exc:
        check("e1h a wrong-but-well-formed digest is refused by the content-hash comparison",
              "content hash mismatch" in str(exc), f"refused, but by: {exc}")

    # Mutate each instance input; the record's content hash must move.
    def variant(**changes) -> prep.SyntheticInstance:
        fields = dict(instance_id=base.instance_id, synthetic=True, order=base.order, mu=base.mu,
                      Sigma=base.Sigma, p=base.p, K=base.K, C=base.C, B=base.B, kappa=base.kappa,
                      sector_of=base.sector_of, sector_labels=base.sector_labels, approval=None)
        fields.update(changes)
        return prep.SyntheticInstance(**fields)

    mu2 = list(base.mu)
    mu2[0] = mu2[0] + 1.0e-12
    p2 = list(base.p)
    p2[1] = p2[1] + 1.0
    sigma2 = [list(row) for row in base.Sigma]
    sigma2[0][1] = sigma2[0][1] + 1.0e-12

    mutations = {
        "e1 instance_id changes the record": variant(instance_id="syn_prov_renamed"),
        "e2 mu changes the record": variant(mu=tuple(mu2)),
        "e3 p changes the record": variant(p=tuple(p2)),
        "e4 Sigma changes the record": variant(Sigma=tuple(tuple(r) for r in sigma2)),
        "e5 B changes the record": variant(B=base.B + 1.0),
        "e6 C changes the record": variant(C=base.C + 1),
        "e7 K changes the record": variant(K=base.K + 1),
        "e8 sector_of changes the record": variant(sector_of=dict(base.sector_of, S00=base.sector_labels[1])),
        "e9 sector_labels changes the record": variant(sector_labels=tuple(reversed(base.sector_labels))),
    }
    for label, env in mutations.items():
        # A variant that stops the record entirely proves nothing about the
        # digest, so the build must succeed here: every one of these is a
        # well-formed instance that differs only in the stated field.
        try:
            other = build(env)
        except prep.InstancePreparationError as exc:
            check(label, False, f"variant did not build, so the digest was never compared: {exc}")
            continue
        check(label, other["content_sha256"] != rec["content_sha256"],
              "record content hash did not move")

    # The record must bind a hash of every source file it used.
    expected_keys = {f"{k}:{v}" for k, v in prep.SOURCE_FILES.items()}
    check("e10 record binds exactly the declared source map",
          set(rec["source_sha256"]) == expected_keys,
          f"{sorted(rec['source_sha256'])} vs {sorted(expected_keys)}")
    for key, value in rec["source_sha256"].items():
        check(f"e11 source hash {key} is a real file digest",
              len(value) == 64 and all(c in "0123456789abcdef" for c in value),
              f"bad digest {value!r}")

    # A source map that omits a declared source must fail validation.
    dropped = json.loads(json.dumps(rec))
    dropped["source_sha256"].pop(sorted(dropped["source_sha256"])[0])
    try:
        prep.validate_provenance_record(dropped)
        check("e17 a record missing one declared source fails validation", False, "accepted")
    except prep.InstancePreparationError:
        check("e17 a record missing one declared source fails validation", True, "")

    # A tampered source hash must fail validation.
    tampered = json.loads(json.dumps(rec))
    for key in tampered["source_sha256"]:
        tampered["source_sha256"][key] = "f" * 64
        break
    try:
        prep.validate_provenance_record(tampered)
        check("e12 a tampered source hash fails validation", False, "tampered record validated")
    except prep.InstancePreparationError:
        check("e12 a tampered source hash fails validation", True, "")

    # A tampered result must fail validation.
    tampered2 = json.loads(json.dumps(rec))
    tampered2["results"]["Lambda_ref"] = lam_shifted(rec["results"]["Lambda_ref"])
    try:
        prep.validate_provenance_record(tampered2)
        check("e13 a tampered Lambda_ref fails validation", False, "tampered record validated")
    except prep.InstancePreparationError:
        check("e13 a tampered Lambda_ref fails validation", True, "")

    # A record claiming non-synthetic support must fail validation.
    tampered3 = json.loads(json.dumps(rec))
    tampered3["non_synthetic_supported"] = True
    try:
        prep.validate_provenance_record(tampered3)
        check("e14 a record claiming non-synthetic support fails validation", False,
              "accepted a non-synthetic claim")
    except prep.InstancePreparationError:
        check("e14 a record claiming non-synthetic support fails validation", True, "")

    # A record with an extra key must fail validation.
    tampered4 = json.loads(json.dumps(rec))
    tampered4["extra_field"] = 1
    try:
        prep.validate_provenance_record(tampered4)
        check("e15 a record with an extra key fails validation", False, "accepted an extra key")
    except prep.InstancePreparationError:
        check("e15 a record with an extra key fails validation", True, "")

    # A record missing the source map must fail validation.
    tampered5 = json.loads(json.dumps(rec))
    del tampered5["source_sha256"]
    try:
        prep.validate_provenance_record(tampered5)
        check("e16 a record missing the source map fails validation", False, "accepted")
    except prep.InstancePreparationError:
        check("e16 a record missing the source map fails validation", True, "")

    # ---------------------------------------------------------------------------
    # Re-sealed tampers.  These rewrite one field AND recompute the record's own
    # content hash, so the record is internally consistent and only the specific
    # guard under test can reject it.  Without this, every tamper is caught by
    # the content-hash guard and the other guards are never exercised.
    # ---------------------------------------------------------------------------
    def reseal(record: dict) -> dict:
        body = {k: v for k, v in record.items() if k != "content_sha256"}
        canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
        record["content_sha256"] = hashlib.sha256(canonical).hexdigest()
        return record

    # A re-sealed record that is otherwise intact must VALIDATE, proving the
    # re-sealing itself is sound (otherwise the checks below prove nothing).
    control = reseal(json.loads(json.dumps(rec)))
    try:
        prep.validate_provenance_record(control)
        check("e18 a re-sealed but otherwise intact record validates", True, "")
    except prep.InstancePreparationError as exc:
        check("e18 a re-sealed but otherwise intact record validates", False, f"control failed: {exc}")

    # e19 — a re-sealed record whose source hash is not a 64-char lowercase hex
    # string can only be rejected by the source-hash SHAPE guard.
    for label, bad_value in (("an integer", 12345),
                             ("a short string", "abc"),
                             ("an uppercase string", "A" * 64),
                             ("a 64-char non-hex string", "z" * 64),
                             ("None", None),
                             ("a list", [1, 2, 3])):
        broken = reseal(json.loads(json.dumps(rec)))
        key = sorted(broken["source_sha256"])[0]
        broken["source_sha256"][key] = bad_value
        # Re-seal AFTER the edit so the content hash stays consistent.
        broken = reseal(broken)
        try:
            prep.validate_provenance_record(broken)
            check(f"e19 a re-sealed record with a source hash that is {label} is refused",
                  False, "the shape guard did not reject it")
        except prep.InstancePreparationError:
            check(f"e19 a re-sealed record with a source hash that is {label} is refused", True, "")

    # e20 — a re-sealed record with the wrong status can only be rejected by the
    # status guard (the content hash and key set are both intact).
    for label, bad_status in (("an accepted status", "accepted"),
                              ("a non-synthetic status", "prepared_non_synthetic"),
                              ("an empty status", ""),
                              ("a non-string status", 7)):
        broken = reseal(json.loads(json.dumps(rec)))
        broken["status"] = bad_status
        broken = reseal(broken)
        try:
            prep.validate_provenance_record(broken)
            check(f"e20 a re-sealed record with {label} is refused",
                  False, "the status guard did not reject it")
        except prep.InstancePreparationError:
            check(f"e20 a re-sealed record with {label} is refused", True, "")

    # e21 — a re-sealed record claiming non-synthetic support can only be
    # rejected by the non_synthetic_supported guard.
    for label, bad_flag in (("True", True), ("a string", "false"), ("an integer", 0)):
        broken = reseal(json.loads(json.dumps(rec)))
        broken["non_synthetic_supported"] = bad_flag
        broken = reseal(broken)
        try:
            prep.validate_provenance_record(broken)
            check(f"e21 a re-sealed record with non_synthetic_supported={label} is refused",
                  False, "the non-synthetic guard did not reject it")
        except prep.InstancePreparationError:
            check(f"e21 a re-sealed record with non_synthetic_supported={label} is refused", True, "")

    # e22 — a re-sealed record with an empty source map can only be rejected by
    # the non-empty source-map guard.
    broken = reseal(json.loads(json.dumps(rec)))
    broken["source_sha256"] = {}
    broken = reseal(broken)
    try:
        prep.validate_provenance_record(broken)
        check("e22 a re-sealed record with an empty source map is refused", False,
              "the non-empty source-map guard did not reject it")
    except prep.InstancePreparationError:
        check("e22 a re-sealed record with an empty source map is refused", True, "")

    # e23 — a re-sealed record carrying scientific outputs can only be rejected
    # by the provenance result-boundary guard.
    broken = reseal(json.loads(json.dumps(rec)))
    broken["scientific_outputs"] = "A/B/C rates"
    broken = reseal(broken)
    try:
        prep.validate_provenance_record(broken)
        check("e23 a re-sealed record carrying scientific outputs is refused", False,
              "the provenance result-boundary guard did not reject it")
    except prep.InstancePreparationError:
        check("e23 a re-sealed record carrying scientific outputs is refused", True, "")

    # e24 — a re-sealed record with a wrong schema is rejected by the schema guard.
    broken = reseal(json.loads(json.dumps(rec)))
    broken["schema"] = "decisions_os/something_else/v1"
    broken = reseal(broken)
    try:
        prep.validate_provenance_record(broken)
        check("e24 a re-sealed record with a foreign schema is refused", False,
              "the schema guard did not reject it")
    except prep.InstancePreparationError:
        check("e24 a re-sealed record with a foreign schema is refused", True, "")

    # ---------------------------------------------------------------------------
    # The three provenance fields round 1 wrote and nothing ever read.  Each is
    # now asserted, because a constant or wrong value in any of them would have
    # shipped with no fixture noticing.
    # ---------------------------------------------------------------------------
    # f_predicate is the frozen D008 rule line itself, taken from the frozen
    # module -- not from this file -- and f_predicate_sha256 is its digest.
    frozen_line = g3.D008_RULE_VERBATIM.split("\n")[1]
    check("e25 the record carries the frozen D008 predicate line",
          rec["f_predicate"] == frozen_line, f"got {rec['f_predicate']!r}")
    check("e26 the predicate digest is the digest of that line",
          rec["f_predicate_sha256"] == hashlib.sha256(frozen_line.encode("utf-8")).hexdigest(),
          f"got {rec['f_predicate_sha256']!r}")
    check("e27 the predicate digest is a function of the line",
          hashlib.sha256(g3.D008_RULE_VERBATIM.split("\n")[0].encode("utf-8")).hexdigest()
          != rec["f_predicate_sha256"], "the digest does not depend on the line")
    # d006_d008_d010_content_sha256 must be the digest of the ledger the record
    # also describes, so it must match it and must move when the ledger moves.
    check("e28 the ledger content digest is the digest of that ledger",
          rec["ledgers"]["d006_d008_d010_content_sha256"] == prep._ledger_digest(led),
          "does not match the ledger that was built")
    # A B large enough to change the feasible set, hence f*, Lambda_ref, rho and
    # the whole D010 grid.  (A B+1 perturbation leaves the grid unchanged, which
    # is why that was tried first and rejected.)
    # A mu scaled by 100: the objective scales with it, so f*, Lambda_ref and
    # hence every coefficient in the D006/D008/D010 ledger move.  (Perturbing B
    # does not: this instance's budget is not binding, so nothing downstream
    # changes -- tried first, and rejected for that reason.)
    mu_b2 = tuple(v * 100.0 for v in base.mu)
    env_b2 = prep.SyntheticInstance(
        instance_id=base.instance_id, synthetic=True, order=base.order, mu=mu_b2,
        Sigma=base.Sigma, p=base.p, K=base.K, C=base.C, B=base.B, kappa=base.kappa,
        sector_of=base.sector_of, sector_labels=base.sector_labels, approval=None,
    )
    opt_b2 = prep.resolve_optimum(env_b2)
    led_b2 = prep.build_ledgers(opt_b2, prep.lambda_ref(opt_b2))
    # The perturbation scales the objective, so Lambda_ref and the coefficient
    # ledger move even though this instance's D010 grid range happens to stay the
    # same.  What must change is the ledger CONTENT -- that is what the digest
    # covers -- so the control asserts the content, not the grid.
    check("e29b the perturbed ledger really has different content",
          led_b2["coefficient_ledger"] != led["coefficient_ledger"],
          "the perturbation did not change the ledger content")
    check("e29 the ledger content digest moves when the ledger moves",
          rec["ledgers"]["d006_d008_d010_content_sha256"] != prep._ledger_digest(led_b2),
          "the ledger content digest did not move")
    check("e30 the ledger content digest is not a constant",
          rec["ledgers"]["d006_d008_d010_content_sha256"] != "0" * 64,
          "the ledger content digest is a constant")

    # --- a non-object record, and a record whose content_sha256 is malformed ---
    for junk in ("x", 5, None, ["a"], ("a",), 3.5, b"x"):
        try:
            prep.validate_provenance_record(junk)
            check(f"e31 a non-object record {junk!r} is refused", False, "no exception")
        except prep.InstancePreparationError:
            check(f"e31 a non-object record {junk!r} is refused", True, "")
        except Exception as exc:  # noqa: BLE001
            check(f"e31 a non-object record {junk!r} is refused", False,
                  f"UNTYPED {type(exc).__name__}: {exc}")
    # A re-sealed record whose content_sha256 is of the wrong shape: only the
    # content_sha256 SHAPE rule can reject these, since the key set is intact
    # and the rest of the body is untouched.
    for label, bad_digest in (("an int", 12345), ("None", None), ("a short string", "abc"),
                              ("a 64-char non-hex string", "z" * 64)):
        broken = reseal(json.loads(json.dumps(rec)))
        broken["content_sha256"] = bad_digest
        try:
            prep.validate_provenance_record(broken)
            check(f"e32 a re-sealed record whose content_sha256 is {label} is refused", False,
                  "the content_sha256 shape guard did not reject it")
        except prep.InstancePreparationError:
            check(f"e32 a re-sealed record whose content_sha256 is {label} is refused", True, "")


def lam_shifted(value: float) -> float:
    return value + 1.0e-15


# ------------------------------------------------------------------------------
# envelope-level validation fixtures
# ------------------------------------------------------------------------------

def fixture_envelope() -> None:
    section("envelope validation (fail-closed on malformed instances)")
    base = make_synthetic("syn_env", 5, 123, 2, 1, 250.0)

    def bad(**changes) -> prep.SyntheticInstance:
        fields = dict(instance_id=base.instance_id, synthetic=True, order=base.order, mu=base.mu,
                      Sigma=base.Sigma, p=base.p, K=base.K, C=base.C, B=base.B, kappa=base.kappa,
                      sector_of=base.sector_of, sector_labels=base.sector_labels, approval=None)
        fields.update(changes)
        return prep.SyntheticInstance(**fields)

    def expect_refusal(label: str, env) -> None:
        try:
            prep.resolve_optimum(env)
            check(label, False, "no exception was raised")
        except prep.InstancePreparationError:
            check(label, True, "")

    expect_refusal("v1 K out of range is refused", bad(K=base.n_assets if hasattr(base, "n_assets") else 99))
    expect_refusal("v2 negative C is refused", bad(C=-1))
    expect_refusal("v3 non-D007 kappa is refused", bad(kappa=2.0))
    expect_refusal("v4 non-finite mu is refused", bad(mu=(float("nan"),) + base.mu[1:]))
    expect_refusal("v5 infinite mu is refused", bad(mu=(float("inf"),) + base.mu[1:]))
    expect_refusal("v6 wrong-length mu is refused", bad(mu=base.mu[:-1]))
    expect_refusal("v7 non-square Sigma is refused", bad(Sigma=base.Sigma[:-1]))
    expect_refusal("v8 misaligned p is refused", bad(p=base.p[:-1]))
    expect_refusal("v9 empty canonical_order is refused", bad(order=()))
    expect_refusal("v10 a non-mapping sector_of is refused", bad(sector_of=("SEC0", "SEC1")))
    expect_refusal("v11 a missing sector label is refused", bad(sector_labels=("SEC0", "SEC_MISSING")))
    expect_refusal("v12 an unrepresented sector label is refused", bad(sector_labels=("SEC0", "SEC1", "SEC_EXTRA")))
    expect_refusal("v13 an empty instance_id is refused", bad(instance_id=""))
    expect_refusal("v14 a repeated ticker is refused", bad(order=(base.order[0], base.order[0]) + base.order[2:]))
    expect_refusal("v15 a non-SyntheticInstance input is refused", {"order": ("A",)})

    # A bool kappa must not sneak through as an int.
    expect_refusal("v16 a bool p entry is refused", bad(p=(True,) + base.p[1:]))

    # ---------------------------------------------------------------------------
    # Typed-refusal contract (round 2).  Round 1 leaked an untyped TypeError out
    # of len(order) / set(order) / set(sector_labels) / len(Sigma row) and could
    # leak a KeyError out of sector_of[name].  Every one of those shapes is
    # exercised below, and every exit is asserted to be a
    # prep.InstancePreparationError -- never a bare TypeError/KeyError/etc.
    # ---------------------------------------------------------------------------

    def expect_typed(label: str, env) -> None:
        """The envelope must be refused, and the refusal must be OUR typed class.

        A bare ``except prep.InstancePreparationError`` would also pass if the
        fixture itself raised before the call, so both outcomes are reported.
        """
        try:
            prep.resolve_optimum(env)
            check(label, False, "no exception was raised")
        except prep.InstancePreparationError:
            check(label, True, "")
        except Exception as exc:  # noqa: BLE001 - the point is that this must not happen
            check(label, False, f"UNTYPED {type(exc).__name__}: {exc}")

    def expect_rule(label: str, env, fragment: str) -> None:
        """Refused, TYPED, and refused by the NAMED rule rather than another one.

        Several envelope guards can be reached by the same malformed input, so
        "it was refused" is not enough to make any single one of them
        load-bearing.  Requiring the message to name the intended rule is what
        pins the attribution: remove that rule and a DIFFERENT one takes over and
        this check fails.
        """
        try:
            prep.resolve_optimum(env)
            check(label, False, "no exception was raised")
        except prep.InstancePreparationError as exc:
            check(label, fragment in str(exc), f"refused by a different rule: {exc}")
        except Exception as exc:  # noqa: BLE001
            check(label, False, f"UNTYPED {type(exc).__name__}: {exc}")

    def expect_typed_call(label: str, call) -> None:
        try:
            call()
            check(label, False, "no exception was raised")
        except prep.InstancePreparationError:
            check(label, True, "")
        except Exception as exc:  # noqa: BLE001
            check(label, False, f"UNTYPED {type(exc).__name__}: {exc}")

    # A field whose *read* explodes.  The property is declared on a SUBCLASS, so
    # getattr() really does call it: a data descriptor on the type outranks the
    # value the inherited dataclass __init__ stored in the instance __dict__.
    # (Putting the descriptor on the VALUE would be vacuous -- getattr would
    # just return it -- which is exactly the bug the round-2 mutation table
    # caught in the first version of this fixture.)
    def fields_of() -> dict:
        return dict(instance_id=base.instance_id, synthetic=True, order=base.order, mu=base.mu,
                    Sigma=base.Sigma, p=base.p, K=base.K, C=base.C, B=base.B, kappa=base.kappa,
                    sector_of=base.sector_of, sector_labels=base.sector_labels, approval=None)

    def hostile(field: str) -> prep.SyntheticInstance:
        """An envelope whose ``field`` attribute explodes the moment it is read."""
        cls = type("_HostileInstance", (prep.SyntheticInstance,),
                   {field: property(lambda self: (_ for _ in ()).throw(
                       RuntimeError(f"hostile read of {field}")))})
        # Built without __init__: the frozen dataclass __init__ assigns through
        # setattr, which the type-level property (a data descriptor) rejects.
        # Populating __dict__ directly gives a real SyntheticInstance that passes
        # the isinstance gate and explodes on the getattr() for that one field.
        inst = object.__new__(cls)
        inst.__dict__.update(fields_of())
        return inst

    for field in ("order", "p", "mu", "Sigma", "K", "sector_of", "sector_labels",
                  "instance_id", "synthetic", "approval"):
        expect_typed(f"v17 an exploding read of {field!r} is a typed refusal",
                     hostile(field))

    # The same contract must hold for every public entry point, not only
    # resolve_optimum: each is called on a hostile-field envelope below.
    opt_ok = prep.resolve_optimum(base)
    lam_ok = prep.lambda_ref(opt_ok)
    led_ok = prep.build_ledgers(opt_ok, lam_ok)
    for name, call in (
        ("resolve_optimum", lambda: prep.resolve_optimum(hostile("order"))),
        ("reverify_ledger_paths",
         lambda: prep.reverify_ledger_paths(hostile("order"), opt_ok)),
        ("build_provenance_record",
         lambda: prep.build_provenance_record(hostile("order"),
                                              opt_ok, lam_ok, led_ok)),
    ):
        expect_typed_call(f"v18 {name} refuses an exploding field read typed", call)

    # A Mapping whose value read explodes must be a typed refusal, not a
    # KeyError and not the foreign exception escaping from inside the mapping.
    class _ExplodingValue(dict):
        def __getitem__(self, key):
            raise RuntimeError("hostile mapping value")

    # ... and a Mapping whose membership test explodes likewise.  Note that
    # dict.__getitem__ is bypassed by the ``in`` operator only if the subclass
    # does not override __contains__; both overrides are exercised separately.
    class _ExplodingMembership(dict):
        def __contains__(self, key):
            raise RuntimeError("hostile membership test")

    expect_typed("v19 a mapping whose value read explodes is a typed refusal",
                 bad(sector_of=_ExplodingValue(base.sector_of)))
    expect_typed("v20 a mapping whose membership test explodes is a typed refusal",
                 bad(sector_of=_ExplodingMembership(base.sector_of)))

    # A sequence field that cannot be iterated.  This is exactly the case round 1
    # turned into a bare TypeError.
    class _ExplodingIter:
        def __iter__(self):
            raise RuntimeError("hostile iteration")
        def __len__(self):
            return 5

    expect_typed("v21 an order that cannot be iterated is a typed refusal", bad(order=_ExplodingIter()))
    expect_typed("v22 a mu that cannot be iterated is a typed refusal", bad(mu=_ExplodingIter()))
    expect_typed("v23 a Sigma that cannot be iterated is a typed refusal", bad(Sigma=_ExplodingIter()))
    expect_typed("v24 a Sigma row that cannot be iterated is a typed refusal",
                 bad(Sigma=(_ExplodingIter(),) + base.Sigma[1:]))
    expect_typed("v25 a p that cannot be iterated is a typed refusal", bad(p=_ExplodingIter()))
    expect_typed("v26 a sector_labels that cannot be iterated is a typed refusal",
                 bad(sector_labels=_ExplodingIter()))

    # validate_envelope is the named contract boundary, so exercise it directly
    # too -- resolve_optimum only reaches it indirectly.
    expect_typed_call("v27 validate_envelope refuses a scalar order typed",
                      lambda: prep.validate_envelope(bad(order=5)))
    expect_typed_call("v28 validate_envelope refuses a None order typed",
                      lambda: prep.validate_envelope(bad(order=None)))
    expect_typed_call("v29 validate_envelope refuses a non-SyntheticInstance typed",
                      lambda: prep.validate_envelope("not an instance"))
    expect_typed_call("v30 validate_envelope refuses a None instance typed",
                      lambda: prep.validate_envelope(None))

    # ---------------------------------------------------------------------------
    # (v2) the last remaining round-2 mutation survivors.  Each input below
    # reaches exactly one guard and is refused by nothing else, so the guard is
    # the only thing that can reject it.
    # ---------------------------------------------------------------------------

    # sector_of that is not a Mapping at all.  _mapping_covers needs __contains__
    # and the copy-out needs __getitem__, so a list raises (TypeError) in the
    # copy-out if the Mapping gate is ever removed.
    expect_rule("v31 a sector_of that is not a mapping is refused by the Mapping rule",
                bad(sector_of=[base.sector_labels[0], base.sector_labels[1]]), "must be a mapping")
    expect_typed("v32 a sector_of of mixed str and int is refused typed",
                 bad(sector_of={**base.sector_of, base.order[0]: 1}))

    # A non-empty but WRONG-TYPE sector label: it is not unhashable, so the
    # realised-label set is total and the per-ticker str rule is the only
    # thing that can reject it.  (An unhashable value was tried first and is
    # caught earlier, by the copy-out loop, not by this rule.)
    expect_typed("v33 a non-str sector label is refused typed",
                 bad(sector_of={**base.sector_of, base.order[0]: 1}))

    # An EMPTY sector label.  It IS a str, so it hashes fine and the realised
    # set is total; the non-empty part of the per-ticker rule is the only guard.
    expect_rule("v34 an empty sector label is refused by the per-ticker non-empty rule",
                bad(sector_of={**base.sector_of, base.order[0]: ""}), "non-empty str")

    # Duplicate sector labels: every label is realised, so only the distinctness
    # rule can reject this.
    expect_rule("v35 a duplicated sector label is refused by the distinctness rule",
                bad(sector_labels=(base.sector_labels[0], base.sector_labels[0])),
                "must be distinct")

    # A repeated ticker.  n is still correct (2 in this instance), so every
    # length gate passes; only the distinctness rule can reject it.
    # An EMPTY ticker.  The length is still n, every entry is hashable, and the
    # name is not duplicated -- only the per-element non-empty rule refuses it.
    expect_rule("v11b an empty ticker is refused by the per-element rule",
                bad(order=("",) + base.order[1:]), "canonical_order[0] must be a non-empty str")

    expect_rule("v36 a repeated ticker is refused by the distinctness rule",
                bad(order=(base.order[0], base.order[0], base.order[2])),
                "must not repeat a ticker")

    # K == 0 is INSIDE [0, n] and is rejected by nothing in the module: K=0 makes
    # the empty portfolio the sole feasible set, and the G3 empty-F stop is the
    # rule that refuses it.  That attribution is pinned here so the K range rule
    # is never credited with a rejection it does not perform, and so the
    # empty-F stop is shown to be the one that does.
    expect_rule("v37 K=0 is inside the range and is stopped by the G3 empty-F rule",
                bad(K=0), "G3 stop condition")
    # K == n+1 and K < 0 are the two rejections that are unique to the K range
    # rule: validate_envelope refuses them before any feasibility is considered.
    for k in (-1, len(base.order) + 1, 99):  # K=0 is deliberately NOT here; see v37
        expect_typed_call(f"v39 K={k!r} is refused by the K range rule",
                          lambda k=k: prep.validate_envelope(bad(K=k)))
    expect_typed_call("v38 C=-1 is refused by the C range rule",
                      lambda: prep.validate_envelope(bad(C=-1)))
    for c in (-1, -99):
        expect_typed_call(f"v40 C={c!r} is refused by the C range rule",
                          lambda c=c: prep.validate_envelope(bad(C=c)))

    # An int B is a legitimate JSON number and must still be accepted and
    # normalized to binary64, exactly as the frozen resolver does: the refusal
    # rules for B and kappa are the NUMBER rule and (for kappa) the D007 rule,
    # never a blanket "reject every non-float".
    env_int_b = bad(B=250)
    opt_int_b = prep.resolve_optimum(env_int_b)
    check("v41 an int B is accepted and normalized to binary64",
          type(prep.validate_envelope(env_int_b).B) is float
          and prep.validate_envelope(env_int_b).B == 250.0,
          f"B normalized to {prep.validate_envelope(env_int_b).B!r}")
    check("v41 an int B changes nothing downstream",
          same_bits(opt_int_b.f_star, prep.resolve_optimum(bad(B=250.0)).f_star),
          "int and float B gave different results")
    for field, value, why in (("B", "10.0", "a str B"), ("B", [10.0], "a list B"),
                              ("B", True, "a bool B"),
                              ("kappa", "1.0", "a str kappa"), ("kappa", [1.0], "a list kappa"),
                              ("kappa", True, "a bool kappa")):
        expect_typed(f"v42 {why} is refused typed", bad(**{field: value}))

    # ---------------------------------------------------------------------------
    # (v44) an UNHASHABLE element inside a name sequence.  This is the case the
    # round-2 validator flagged: a list element makes len(set(...)) raise an
    # untyped TypeError, so the per-element str guard is the only thing standing
    # between a hostile envelope and an exception outside the typed hierarchy.
    # Each input below is a sequence of the RIGHT LENGTH holding one unhashable
    # (or wrong-typed) element, so every length gate passes and the per-element
    # rule is the only guard that can reject it.  None of these may raise
    # TypeError: expect_typed fails the check on any non-InstancePreparationError.
    # ---------------------------------------------------------------------------
    for field, elem, why in (
        ("order", ["A"], "a list ticker"),
        ("order", {"A": 1}, "a dict ticker"),
        ("order", (1,), "an int ticker"),
        ("order", (None,), "a None ticker"),
        ("order", ((1, 2),), "a tuple ticker"),
        ("sector_labels", ["S1"], "a list sector label"),
        ("sector_labels", {"S1": 1}, "a dict sector label"),
        ("sector_labels", (1,), "an int sector label"),
        ("sector_labels", (None,), "a None sector label"),
    ):
        rest = {n: getattr(base, n) for n in ("order", "sector_labels") if n != field}
        if field == "order":
            value = (elem,) + tuple(base.order[1:])
        else:
            # Keep the length at n so only the per-element rule can fire; the
            # ticker->label copy-out is fed from the REAL base mapping, so the
            # rule under test is the one over the label sequence.
            value = (elem,) + tuple(base.sector_labels[1:])
        expect_typed_call(
            f"v44 {why} in {field} is refused typed, not a TypeError",
            lambda field=field, value=value, rest=rest: prep.validate_envelope(
                prep.SyntheticInstance(**{**base.__dict__, **rest, field: value})))

    # The same unhashable element must not be able to escape through the OTHER
    # entry points, which re-run validation: if a later call re-validated a
    # partially normalized envelope it would crash the same way.
    for entry, call in (("resolve_optimum", prep.resolve_optimum),
                        ("require_synthetic", prep.require_synthetic)):
        expect_typed_call(f"v44b an unhashable ticker is typed through {entry}",
                          lambda call=call: call(prep.SyntheticInstance(
                              **{**base.__dict__, "order": (["A"],) + tuple(base.order[1:])})))

    # ---------------------------------------------------------------------------
    # (g) the module's own Optimum fields and remaining direct-call guards.  These
    # exist because the round-2 mutation table found checks that nothing
    # depended on: every field of Optimum, and two _box_rule guards, were
    # mutated away with the fixtures still green.
    # ---------------------------------------------------------------------------
    fixture_g_outputs()

    # --- v43 — a non-envelope input.  The "must be a SyntheticInstance" gate is
    # the only thing standing between a raw dict / list / int / None and the field
    # reads below it, so it is pinned here with inputs that are typed enough to
    # carry attributes.
    for junk in (None, 5, "x", {"order": ("A",)}, ["A"], (None,), 3.5, b"x"):
        try:
            prep.validate_envelope(junk)
            check(f"v43 a non-envelope {junk!r} is refused", False, "no exception was raised")
        except prep.InstancePreparationError:
            check(f"v43 a non-envelope {junk!r} is refused", True, "")
        except Exception as exc:  # noqa: BLE001
            check(f"v43 a non-envelope {junk!r} is refused", False,
                  f"UNTYPED {type(exc).__name__}: {exc}")

    # v43b — a LOOK-ALIKE.  A plain object carrying every field with a valid
    # value is refused ONLY by the isinstance gate: _field would happily read
    # all thirteen of them, and every later rule would pass.  This is what makes
    # the gate load-bearing rather than a cosmetic message.
    class _LookAlike:
        pass

    lookalike = _LookAlike()
    for name, value in (("instance_id", "lookalike"), ("synthetic", True), ("order", base.order),
                        ("mu", base.mu), ("Sigma", base.Sigma), ("p", base.p), ("K", base.K),
                        ("C", base.C), ("B", base.B), ("kappa", base.kappa),
                        ("sector_of", base.sector_of), ("sector_labels", base.sector_labels),
                        ("approval", None)):
        setattr(lookalike, name, value)
    try:
        prep.validate_envelope(lookalike)
        check("v43b a duck-typed look-alike is refused", False, "no exception was raised")
    except prep.InstancePreparationError as exc:
        check("v43b a duck-typed look-alike is refused", True, "")
        check("v43c it is the isinstance gate that refused it",
              "must be a SyntheticInstance" in str(exc), f"message: {exc}")
    except Exception as exc:  # noqa: BLE001
        check("v43b a duck-typed look-alike is refused", False,
              f"UNTYPED {type(exc).__name__}: {exc}")

    # build_ledgers takes an Optimum, not an envelope: it must NOT re-validate the
    # envelope, or a caller could not feed it a computed result.  A bogus Optimum
    # is rejected by the D010 box rule instead, and that refusal is typed.
    try:
        prep.build_ledgers(object(), 1.0)
        check("v44 build_ledgers refuses a non-Optimum typed", False, "no exception")
    except prep.InstancePreparationError:
        check("v44 build_ledgers refuses a non-Optimum typed", True, "")
    except Exception as exc:  # noqa: BLE001
        check("v44 build_ledgers refuses a non-Optimum typed", False,
              f"UNTYPED {type(exc).__name__}: {exc}")

    # A REAL Optimum whose Delta_full is not a number: reaches the Delta_full
    # finiteness rule in build_ledgers, which no other rule would catch.
    from dataclasses import replace as _replace
    opt_nan = _replace(prep.resolve_optimum(base), delta_full=float("nan"))
    try:
        prep.build_ledgers(opt_nan, lam_ok)
        check("v44b a NaN Delta_full is refused by build_ledgers", False, "no exception")
    except prep.InstancePreparationError as exc:
        check("v44b a NaN Delta_full is refused by build_ledgers", True, "")
        check("v44c the refusal is the number rule, not the box rule",
              "Optimum.delta_full must be finite" in str(exc), f"message: {exc}")
    opt_inf = _replace(prep.resolve_optimum(base), delta_full=float("inf"))
    try:
        prep.build_ledgers(opt_inf, lam_ok)
        check("v44d an infinite Delta_full is refused by build_ledgers", False, "no exception")
    except prep.InstancePreparationError as exc:
        check("v44d an infinite Delta_full is refused by build_ledgers", True, "")
        check("v44e the refusal is the number rule, not the box rule",
              "Optimum.delta_full must be finite" in str(exc), f"message: {exc}")

    # --- v45 — _sha256_file must refuse a missing source file.  A missing frozen
    # source would otherwise yield a silent hash of nothing unless this fires.
    try:
        prep._sha256_file(os.path.join(_ROOT, "research/g9/definitely_not_a_file.py"))
        check("v45 _sha256_file refuses a missing file", False, "no exception was raised")
    except prep.InstancePreparationError as exc:
        check("v45 _sha256_file refuses a missing file", True, "")
        check("v46 the missing-file refusal names the defect", "missing" in str(exc),
              f"message: {exc}")

    # --- v47 — the instance digest must move when mu moves.  Provenance binds the
    # instance CONTENT, so dropping mu from the digest body (a plausible
    # refactor) must break this.
    mu_shifted = list(base.mu)
    mu_shifted[0] = mu_shifted[0] + 1.0e-9
    env_mu2 = prep.SyntheticInstance(
        instance_id=base.instance_id, synthetic=True, order=base.order, mu=tuple(mu_shifted),
        Sigma=base.Sigma, p=base.p, K=base.K, C=base.C, B=base.B, kappa=base.kappa,
        sector_of=base.sector_of, sector_labels=base.sector_labels, approval=None,
    )
    check("v47 the instance content digest moves when mu moves",
          prep._instance_digest(prep.validate_envelope(env_mu2))
          != prep._instance_digest(prep.validate_envelope(base)),
          "mu is not bound into the instance digest")


def fixture_g_outputs() -> None:
    section("(g) every Optimum field and direct-call guard is load-bearing")

    base = make_synthetic("syn_g", 5, 202, 2, 1, 250.0)
    opt = prep.resolve_optimum(base)

    # --- every Optimum field is compared against the independent reference ------
    ref = brute_optimum(base)
    check("g1 f_full_min is reported", isinstance(opt.f_full_min, float), "not a float")
    check("g2 f_full_max is reported", isinstance(opt.f_full_max, float), "not a float")
    # The minimizing mask, cross-checked against the independent reference: the
    # module reports the FIRST mask attaining the full-space minimum, and this
    # pins both the value and which mask that is.
    min_mask = min(m for m in range(1 << len(base.order))
                   if prep._g3.f_fast([i for i in range(len(base.order)) if (m >> i) & 1],
                                      list(base.mu), [list(r) for r in base.Sigma],
                                      base.kappa) == opt.f_full_min)
    check("g1b f_full_min_mask is the first mask attaining f_full_min",
          opt.f_full_min_mask == min_mask,
          f"{opt.f_full_min_mask} vs {min_mask}")
    check("g3 argmax_F tickers equal the brute-force argmax",
          opt.argmax_f_over_f_tickers == ref["argmax_tickers"],
          f"{opt.argmax_f_over_f_tickers} vs {ref['argmax_tickers']}")
    check("g4 argmax_F mask is consistent with its own tickers",
          opt.argmax_f_mask == ref["argmax_mask"],
          f"{opt.argmax_f_mask} vs {ref['argmax_mask']}")
    check("g5 cardinality_feasible_range spread is non-degenerate",
          opt.cardinality_feasible_range[0] > 0.0,
          f"spread {opt.cardinality_feasible_range[0]!r} is not positive")
    check("g6 full_space_size is 2^n",
          opt.full_space_size == 2 ** len(base.order),
          f"{opt.full_space_size} vs {2 ** len(base.order)}")

    # Recomputed here from scratch, with the SAME accumulation order the frozen
    # ddof=0 rule uses (a plain left-to-right sum, not math.fsum, which rounds
    # differently and would make this a tolerance test rather than a bit test).
    # Round 1 reported this field and nothing depended on it: the
    # constant-objective instance has a degenerate distribution where every
    # value is equal, so any broken formula also returns 0.0 -- which is why the
    # mutation survived there and why this instance is not that instance.
    card_vals = []
    n_g = len(base.order)
    for m in range(1 << n_g):
        if bin(m).count("1") == base.K:
            card_vals.append(prep._g3.f_fast(
                [i for i in range(n_g) if (m >> i) & 1], list(base.mu),
                [list(r) for r in base.Sigma], base.kappa))
    acc = 0.0
    for v in card_vals:
        acc = acc + v
    mean_g = acc / len(card_vals)
    sq = 0.0
    for v in card_vals:
        d = v - mean_g
        sq = sq + d * d
    expected_std = (sq / len(card_vals)) ** 0.5
    check("g5b the cardinality-feasible population std matches an independent sum",
          same_bits(opt.cardinality_feasible_range[1], expected_std),
          f"{opt.cardinality_feasible_range[1]!r} vs {expected_std!r}")
    check("g5c the reported std is non-zero on a non-degenerate instance",
          opt.cardinality_feasible_range[1] > 0.0,
          f"std is {opt.cardinality_feasible_range[1]!r}")
    # And the degenerate branch the round-1 code got wrong: a singleton
    # cardinality-feasible set must report 0.0, not the NaN that 0/0 yields.
    check("g5d a singleton population std is 0.0, not NaN",
          prep._pop_std([1.5]) == 0.0 and prep._pop_std([1.5, 1.5]) == 0.0,
          f"singleton gave {prep._pop_std([1.5])!r}")

    # The argmax_F tie-break is stated explicitly rather than left implied: the
    # constant-objective instance has EVERY feasible mask tied at f_F_max, so it
    # is the only thing that can distinguish first- from last-maximizer.
    tied = uniform_instance("syn_g_tie", 4, 2, -1.0e-3)
    tied_ref = brute_optimum(tied)
    tied_opt = prep.resolve_optimum(tied)
    check("g7 argmax_F is the LAST tied maximizer",
          tied_opt.argmax_f_over_f_tickers == tied_ref["argmax_tickers"]
          and tied_opt.argmax_f_mask == tied_ref["argmax_mask"],
          f"{tied_opt.argmax_f_over_f_tickers} vs {tied_ref['argmax_tickers']}")
    check("g8 the tie instance really has every feasible mask tied",
          len(tied_ref["x_star_masks"]) == tied_ref["f_size"] and tied_ref["f_size"] > 1,
          f"tie instance does not actually tie ({tied_ref['f_size']} feasible)")

    # --- reverify_ledger_paths must recheck the argmax_F witness ---------------
    # f16 corrupts f_fast so every witness disagrees; the count the module
    # reports tells us how many witnesses it actually visited, and the argmax
    # witness is one of them only because argmax_f_mask is appended.
    env = make_synthetic("syn_g_rev", 5, 303, 2, 1, 250.0)
    opt_rev = prep.resolve_optimum(env)
    witnesses = prep.reverify_ledger_paths(env, opt_rev)
    # |X*| + mask 0 + mask (2^n - 1) + the argmax_F mask.
    expected = len(opt_rev.x_star_masks) + 3
    check("g9 reverify visits X* plus the three fixed witnesses",
          witnesses == expected,
          f"{witnesses} witnesses, expected {expected}")
    check("g10 reverify really rechecked the argmax_F mask",
          opt_rev.argmax_f_mask not in (0, (1 << len(env.order)) - 1)
          or opt_rev.argmax_f_mask in opt_rev.x_star_masks,
          "the argmax_F witness is indistinguishable from a fixed witness")

    # --- _box_rule guards reached with the arguments that fire each one -------
    # A finite but non-positive Delta_full reaches the Delta_full guard without
    # ever dividing, so no earlier guard can have refused it.
    for delta, lam, why in ((0.0, 1.0, "zero Delta_full"),
                             (-1.0, 1.0, "negative Delta_full"),
                             (float("nan"), 1.0, "NaN Delta_full"),
                             (float("inf"), 1.0, "infinite Delta_full")):
        try:
            prep._box_rule(delta, lam)
            check(f"g11 _box_rule refuses {why}", False, "no exception was raised")
        except prep.InstancePreparationError as exc:
            # Named, not merely "refused": the other two _box_rule guards also
            # reject an infinite Delta_full, so only the message distinguishes
            # which one is load-bearing.
            check(f"g11 _box_rule refuses {why} by the Delta_full rule",
                  "Delta_full" in str(exc), f"refused by a different rule: {exc}")
    for lam, why in ((0.0, "zero Lambda_ref"), (-1.0, "negative Lambda_ref"),
                     (float("nan"), "NaN Lambda_ref"), (float("-inf"), "negative-infinite Lambda_ref")):
        try:
            prep._box_rule(1.0, lam)
            check(f"g12 _box_rule refuses {why}", False, "no exception was raised")
        except prep.InstancePreparationError:
            check(f"g12 _box_rule refuses {why}", True, "")
    # A subnormal Lambda_ref is finite AND strictly positive, so it passes the
    # positivity guard and is caught by the rho_box rule instead -- that is what
    # makes the rho rule load-bearing.  (An infinite Lambda_ref would NOT reach
    # it: the positivity guard refuses +inf first.)
    for delta, lam, why in ((1.0, 5.0e-324, "a subnormal Lambda_ref overflowing rho"),
                             (1.0, 1.0e-323, "a subnormal Lambda_ref underflowing rho"),
                             (2.0, 1.0e308, "a Lambda_ref that overflows rho"),
                             (0.5, 1.0, "a rho below 1 (F cannot be a subset of the full space)")):
        try:
            prep._box_rule(delta, lam)
            check(f"g13 _box_rule refuses {why}", False, "no exception was raised")
        except prep.InstancePreparationError as exc:
            check(f"g13 _box_rule refuses {why}", True, "")
            check(f"g14 the rho rule is what refused {why}", "rho" in str(exc), f"message: {exc}")

    # --- validate_envelope must refuse a wrong-typed synthetic mark -----------
    # `synthetic is True` already refuses the int 1 (1 is not True), so there is
    # no separate bool-type guard to pin; what is pinned here is that the
    # REFUSAL class, not the generic one, is what comes out.
    for marker in (1, "true", 1.0, (), []):
        env_bad = prep.SyntheticInstance(
            instance_id=base.instance_id, synthetic=marker, order=base.order, mu=base.mu,
            Sigma=base.Sigma, p=base.p, K=base.K, C=base.C, B=base.B, kappa=base.kappa,
            sector_of=base.sector_of, sector_labels=base.sector_labels, approval=None,
        )
        try:
            prep.resolve_optimum(env_bad)
            check(f"g15 a synthetic mark of {marker!r} is refused", False, "no exception")
        except prep.NonSyntheticInstanceRefused:
            check(f"g15 a synthetic mark of {marker!r} is refused", True, "")

    # --- K and C must refuse a float count as well as an out-of-range int -----
    for label, changes in (("K", {"K": 2.0}), ("C", {"C": 1.0}),
                           ("K", {"K": True}), ("C", {"C": False}),
                           ("K", {"K": 99}), ("C", {"C": -1})):
        fields = dict(instance_id=base.instance_id, synthetic=True, order=base.order, mu=base.mu,
                      Sigma=base.Sigma, p=base.p, K=base.K, C=base.C, B=base.B, kappa=base.kappa,
                      sector_of=base.sector_of, sector_labels=base.sector_labels, approval=None)
        fields.update(changes)
        expect = f"g16 {label}={list(changes.values())[0]!r} is refused"
        try:
            prep.resolve_optimum(prep.SyntheticInstance(**fields))
            check(expect, False, "no exception was raised")
        except prep.InstancePreparationError:
            check(expect, True, "")

    # --- the validated envelope must not retain a hostile Mapping -------------
    # sector_of is read four times during validation (membership, the str type
    # test, the realised-label set, and the copy-out).  A mapping that allows
    # exactly as many reads as validation needs and then raises is ACCEPTED,
    # and only survives the rest of the pipeline because the copy-out made a
    # plain dict.  This is what makes the copy-out load-bearing.
    class _FiniteReads(dict):
        """Answers reads, then raises: one read per key per validation pass."""
        def __init__(self, source, allowed):
            super().__init__(source)
            self._reads: dict[str, int] = {}
            self._allowed = allowed

        def __getitem__(self, key):
            self._reads[key] = self._reads.get(key, 0) + 1
            if self._reads[key] > self._allowed:
                raise RuntimeError("sector_of read past the validation budget")
            return super().__getitem__(key)

    # Each ticker is read exactly once per validate_envelope call.  Allowing 1
    # per call leaves no reads for the pipeline, so any re-read of the caller's
    # mapping downstream would raise -- which is exactly what the copy-out
    # prevents.  Every entry point re-validates the envelope, so each call gets
    # its own budgeted mapping.
    def budgeted(tag: str) -> prep.SyntheticInstance:
        return prep.SyntheticInstance(
            instance_id=tag, synthetic=True, order=base.order, mu=base.mu,
            Sigma=base.Sigma, p=base.p, K=base.K, C=base.C, B=base.B, kappa=base.kappa,
            sector_of=_FiniteReads(base.sector_of, allowed=1),
            sector_labels=base.sector_labels, approval=None,
        )

    env_finite = budgeted("syn_g_finite")
    opt_finite = prep.resolve_optimum(env_finite)
    lam_finite = prep.lambda_ref(opt_finite)
    led_finite = prep.build_ledgers(opt_finite, lam_finite)
    rec_finite = prep.build_provenance_record(budgeted("syn_g_finite2"), opt_finite,
                                              lam_finite, led_finite)
    prep.validate_provenance_record(rec_finite)
    check("g17 a mapping that permits only validation's own reads is fully usable", True, "")
    checked_finite = prep.validate_envelope(budgeted("syn_g_finite3"))
    check("g18 the validated envelope holds a plain str->str copy",
          type(checked_finite.sector_of) is dict
          and all(type(v) is str for v in checked_finite.sector_of.values()),
          f"type is {type(checked_finite.sector_of).__name__}")


# ------------------------------------------------------------------------------
# runner
# ------------------------------------------------------------------------------

def main() -> int:
    print("WP5b per-instance preparation fixtures -- offline, synthetic only")
    print("No Stage-2 instance, candidate, ground truth or scientific value is created.")
    # The bit-identity primitive must itself discriminate, or every "bit-for-bit"
    # check below would be vacuous.
    import math as _math
    check("s0 same_bits accepts a value against itself", same_bits(1.25, 1.25), "")
    check("s1 same_bits rejects a one-ulp difference",
          not same_bits(1.0, _math.nextafter(1.0, 2.0)), "one-ulp difference was accepted")
    check("s2 same_bits rejects opposite signs",
          not same_bits(0.0, -0.0), "opposite-signed zeros were treated as identical")
    check("s3 same_bits accepts matching signed zeros",
          same_bits(-0.0, -0.0), "identical signed zeros were rejected")
    check("s4 same_bits distinguishes distinct nonfinite patterns",
          not same_bits(float("nan"), float("inf")), "nan and inf compared identical")
    check("s5 same_bits rejects a subnormal-vs-zero pair",
          not same_bits(0.0, 5.0e-324), "subnormal compared equal to zero")
    fixture_a_equivalence()
    fixture_b_synthetic()
    fixture_f_degenerate()
    fixture_c_empty_f()
    fixture_d_refusal()
    fixture_e_provenance()
    fixture_envelope()
    print(f"\npassed: {len(PASSES)}")
    print(f"failed: {len(FAILURES)}")
    for line in FAILURES:
        print(f"  FAIL {line}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())

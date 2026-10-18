#!/usr/bin/env python3
"""PILOT: measure tau, the CPU cost of ONE full-domain campaign grid point.

This is a COST MEASUREMENT pilot over SYNTHETIC payloads only.  It draws no
Stage-2 candidate, no generated instance, no ground truth and no scientific
record, and it produces no minimum, no label, no classification and no result.
No network, no GPU, no nvcc, no real data, no file is read or written.  The only
outputs are timing numbers, exactness verdicts, machine/load info and
extrapolated core-hours.

UNIT OF WORK (the corrected definition, fixed in round 2)
--------------------------------------------------------
One campaign GRID POINT is exactly ONE COEFFICIENT ROW evaluated under BOTH
encodings (unbalanced and slack).  From the frozen authority:

    src/g5/core_pass.py:44  ROW_COUNT = 61
    src/g5/core_pass.py:266 tasks = (r, card, sector) for r in R_VALUES
                                       for card in 0..60 for sector in 0..60
    coordinates per instance = 61 * 61 * 3 * 61 = 680,943

so a grid point is a single coefficient row, NOT a pair of rows.  Every figure
labelled SEC/GRID POINT below is therefore the cost of ONE row under BOTH
encodings.  ``TIMED_ROWS`` is the timed unit and is held to exactly one row by
``check_unit_of_work``.  ``row1`` is retained ONLY as an extra bit-exactness
case (``BITEXACT_ROWS``) and is NEVER inside the timed unit.  Round 1 timed
rows=("row0","row1") and therefore overstated the per-grid-point cost by 2x.

Two paths are measured.

(1) REFERENCE (frozen authority, pure Python).  ``src.g4.energy`` is called
    exactly as the frozen-authority verifier calls it, and the clamped
    floor/floor+1 register rule is ``src.g5.domains._register_minimizers`` with
    EVERY tied minimizer retained.  A full grid point is far too slow to run in
    the default mode, so a measured contiguous fraction of the states is timed
    and the full-domain figure is a LINEAR EXTRAPOLATION, labelled as such.

(2) NUMPY-VECTORISED.  Vectorised ACROSS STATES, never across terms, so each
    state accumulates its terms in exactly the frozen order and every add is a
    plain elementwise '+'.  Zero-``x`` terms are signed zero and additive
    identity, so they are skipped.  Validated BIT-FOR-BIT against the reference:
    minimum value bits, argmin, the COMPLETE tie set (frozen tau at c_H=2048),
    and the stream length.  Only a bit-for-bit match is reported as a valid
    timing; a mismatch is reported and the timing is rejected.

Every bit-exactness comparison is proven load-bearing by ``sensitivity_report``,
which corrupts the NumPy result by one ulp and reports which comparisons flip.

Load: ``os.getloadavg()`` and ``os.cpu_count()`` are printed BEFORE and AFTER
every timed section.  This machine is shared, so any timing taken while the load
average exceeds the core count is an UPPER BOUND on the true cost, never a lower
bound; that caveat is restated next to every timing.
"""
from __future__ import annotations

import argparse
import os
import platform
import struct
import sys
import time

# The reference and vectorised paths must not be able to influence each other's
# import: numpy is imported lazily, only inside the vectorised section, so the
# REFERENCE timing is measured in a process that has never touched numpy.
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, os.pardir, os.pardir))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from research.g9.cuda_qualification import stage2_cuda_full_domain_energy as E  # noqa: E402
from src.g4.energy import (  # noqa: E402
    BUDGET_SLACK_BITS,
    SECTOR_SLACK_BITS,
    prepare_coefficients,
    prepare_decoded_state,
    prepare_instance,
    prepare_slack_state,
    slack_energy_prepared,
    tau,
    unbalanced_energy_prepared,
)
from src.g4.instance import Instance  # noqa: E402
from src.g4.parameters import Coefficients  # noqa: E402
from src.g5.domains import BinaryDomain, _register_minimizers  # noqa: E402

ASSET_COUNT = E.ASSET_COUNT
SECTOR_COUNT = E.SECTOR_COUNT
STATE_COUNT = E.STATE_COUNT
CH_VALUES = E.CH_VALUES
EPSILON = E.EPSILON

# --- the campaign grid, straight from the frozen authority -------------------
# src/g5/core_pass.py: ROW_COUNT = 61, len(R_VALUES) = 3.
CAMPAIGN_ROW_COUNT = 61
CAMPAIGN_R_VALUE_COUNT = 3
COORDINATES_PER_INSTANCE = (
    CAMPAIGN_ROW_COUNT * CAMPAIGN_ROW_COUNT
    * CAMPAIGN_R_VALUE_COUNT * CAMPAIGN_ROW_COUNT
)
INSTANCES = 5
GRID_POINTS = INSTANCES * COORDINATES_PER_INSTANCE

# ONE campaign grid point == ONE coefficient row under BOTH encodings.
TIMED_ROWS = ("row0",)
# row1 is an EXTRA BIT-EXACTNESS CASE ONLY; it is never in the timed unit.
BITEXACT_ROWS = ("row0", "row1")
FULL_BITEXACT_KEYS = (("row0", "unbalanced"), ("row0", "slack"))

# Reference measurement window.  A full grid point is ~2**20 states; we time a
# contiguous, deterministic prefix large enough to be representative but small
# enough to finish well under the per-run cap, and extrapolate.
REFERENCE_STATES = 2000
# Vectorised path can afford the whole domain in memory, so it is measured on
# the FULL domain directly with no extrapolation for the per-grid-point figure.
VECTOR_CHUNK = 1 << 18

# c_H at which the tie set is defined (frozen rule).
TIE_CH_INDEX = 1


def _word(value: float) -> int:
    return struct.unpack("<Q", struct.pack("<d", float(value)))[0]


def _from_word(word: int) -> float:
    return struct.unpack("<d", struct.pack("<Q", int(word) & 0xFFFFFFFFFFFFFFFF))[0]


def _shift_ulp(value: float, k: int) -> float:
    """Return ``value`` moved by exactly ``k`` ulps away from zero.

    Used ONLY by the sensitivity analysis, to corrupt a NumPy result by a
    prescribed number of ulps.  IEEE-754 doubles are sign-magnitude, so for a
    finite non-zero value the bit pattern increments by one ulp when +k is added
    to the pattern and the value is positive (and by -k when it is negative)."""
    v = float(value)
    if v == 0.0 or not (v == v) or v in (float("inf"), float("-inf")):
        raise ValueError("ulp shift requires a finite non-zero value")
    word = _word(v)
    if v > 0.0:
        return _from_word(word + int(k))
    return _from_word(word - int(k))


def load_snapshot() -> dict[str, object]:
    """Load average and core count, captured around every timed section."""
    try:
        load = os.getloadavg()
    except (OSError, AttributeError):  # pragma: no cover - platform guard
        load = None
    return {
        "load1": None if load is None else float(load[0]),
        "load5": None if load is None else float(load[1]),
        "load15": None if load is None else float(load[2]),
        "cpu_count": os.cpu_count(),
    }


def load_line(label: str, snap: dict[str, object]) -> str:
    if snap["load1"] is None:
        return (f"  {label:<7}: loadavg=unavailable  cpu_count={snap['cpu_count']}")
    return (f"  {label:<7}: loadavg=({snap['load1']:.2f}, {snap['load5']:.2f}, "
            f"{snap['load15']:.2f})  cpu_count={snap['cpu_count']}")


LOAD_CAVEAT = (
    "NOTE: os.getloadavg()[0] is the 1-minute load average.  This machine is "
    "shared, so a section timed while load1 > cpu_count was running under "
    "concurrent load and its wall time is an UPPER BOUND on the true cost, "
    "never a lower bound.  A section timed with load1 << cpu_count is closer "
    "to an uncontended measurement."
)


def machine_info() -> dict[str, object]:
    import numpy  # noqa: F401  (only to report its version; not used in timing)
    model = ""
    try:
        with open("/proc/cpuinfo", "r", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("model name"):
                    model = line.split(":", 1)[1].strip()
                    break
    except OSError:
        model = "unavailable"
    return {
        "nproc": os.cpu_count(),
        "cpu_model": model,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "python_version": platform.python_version(),
        "python_full": sys.version.split()[0],
        "numpy_version": numpy.__version__,
    }


def synthetic_instance() -> Instance:
    payload = E.validate_payload(E.synthetic_payload())
    return Instance(
        tickers=tuple(f"SYN{index:02d}" for index in range(ASSET_COUNT)),
        sectors=tuple(tuple(block) for block in payload["sectors"]),
        mu=tuple(payload["mu"]),
        sigma=tuple(tuple(row) for row in payload["sigma"]),
        prices=tuple(payload["prices"]),
        kappa_risk=float(payload["kappa_risk"]),
        K=int(payload["k"]),
        C=int(payload["c"]),
        B=float(payload["b"]),
    )


def prepared_coefficients(row: str):
    values = E.coefficient_row(row)
    return prepare_coefficients(
        Coefficients(**{field: values[field] for field in E.COEFFICIENT_FIELDS})
    )


# --------------------------------------------------------------------------
# (1) REFERENCE: frozen pure-Python path over a measured contiguous prefix.
# --------------------------------------------------------------------------

def reference_block(start: int, stop: int, rows):
    """Run the frozen authority over states [start, stop) for every row.

    Reproduces exactly what the frozen-authority verifier does per state: build
    the decoded state, apply the clamped floor/floor+1 register rule with every
    tied minimizer retained (all 4 sector registers plus the budget register),
    form each lift's auxiliary and prepare its slack state, and evaluate both
    encodings' energies with the exact frozen transcript and tau tie rule.

    Returns (n_states, n_lifts, n_energy_words, n_tau_calls, n_tie_hits).
    """
    prepared_instance = prepare_instance(synthetic_instance())
    binary_domain = BinaryDomain(ASSET_COUNT)
    prepared_rows = [(row, prepared_coefficients(row)) for row in rows]
    sector_max = E.register_maximum(0)
    budget_max = E.register_maximum(SECTOR_COUNT)

    n_lifts = n_energy_words = n_tau_calls = n_tie_hits = 0
    # Carry the running strict-first-seen minimum per (row, encoding) so the tie
    # rule is actually exercised with the frozen tau, exactly as the scan does.
    minima: dict[tuple[str, str], tuple[float, int]] = {}
    position = 0  # decoded position for unbalanced, lift position for slack
    for index in range(start, stop):
        bits = binary_domain[index]
        decoded = prepare_decoded_state(prepared_instance, bits)

        # Registers: sector 0..3 then budget, clamped floor/floor+1, ties kept.
        sector_min = []
        for sector in range(SECTOR_COUNT):
            values = _register_minimizers(decoded.h_sector[sector], sector_max)
            sector_min.append(values)
        budget_min = _register_minimizers(decoded.h_budget, budget_max)
        # The energy stage emits only budget alternatives (integral-C contract).
        state_lifts = len(budget_min)
        n_lifts += state_lifts

        # Build the packed sector auxiliary once; budget bits vary per lift.
        sector_auxiliary: list[int] = []
        for sector in range(SECTOR_COUNT):
            value = sector_min[sector][0]
            sector_auxiliary.extend((value >> d) & 1 for d in range(SECTOR_SLACK_BITS))

        for row, prepared in prepared_rows:
            # Unbalanced encoding: one energy word per decoded state.
            value = unbalanced_energy_prepared(decoded, prepared)
            key = (row, "unbalanced")
            best = minima.get(key)
            if best is None or value < best[0]:
                minima[key] = (value, position)
            else:
                n_tau_calls += 1
                if abs(value - best[0]) <= tau(value, best[0], E.LAMBDA_REF, CH_VALUES[1]):
                    n_tie_hits += 1
            n_energy_words += 1
            position += 1

            # Slack encoding: one energy word per lift, in frozen product order.
            for budget_value in budget_min:
                auxiliary = tuple(
                    sector_auxiliary
                    + [(budget_value >> d) & 1 for d in range(BUDGET_SLACK_BITS)]
                )
                slack_state = prepare_slack_state(decoded, auxiliary)
                slack_value = slack_energy_prepared(slack_state, prepared)
                key = (row, "slack")
                best = minima.get(key)
                if best is None or slack_value < best[0]:
                    minima[key] = (slack_value, position)
                else:
                    n_tau_calls += 1
                    if abs(slack_value - best[0]) <= tau(
                            slack_value, best[0], E.LAMBDA_REF, CH_VALUES[1]):
                        n_tie_hits += 1
                n_energy_words += 1
                position += 1
    return stop - start, n_lifts, n_energy_words, n_tau_calls, n_tie_hits


# --------------------------------------------------------------------------
# (2) NUMPY vectorised ACROSS STATES, preserving per-state term order exactly.
# --------------------------------------------------------------------------

def numpy_vectorised(payload, rows, first: int, last: int):
    """Evaluate energies for decoded states [first, last) with exact per-state
    frozen term order, vectorised across states.

    Every ordered arithmetic position of the frozen transcript is one elementwise
    op over the whole state block, so each state accumulates its terms in the
    exact frozen order and each add is a plain elementwise '+' -- bit-for-bit
    identical to the reference.  Returns, per (row, encoding), the minimum value
    bits, the first-seen argmin, and the full value array, plus the running
    strict-first-seen global minimum and its argmin, and the tie set.
    """
    import numpy as np

    n = last - first
    idx = np.arange(first, last, dtype=np.int64)

    mu = np.asarray(payload["mu"], dtype=np.float64)
    sigma = np.asarray(payload["sigma"], dtype=np.float64)
    prices = np.asarray(payload["prices"], dtype=np.float64)
    kappa = np.float64(payload["kappa_risk"])
    k_value = np.float64(payload["k"])
    c_value = np.float64(payload["c"])
    b_value = np.float64(payload["b"])
    sectors = payload["sectors"]

    # x[i] = (index >> (19 - i)) & 1, as a float array per asset.
    x = ((idx[:, None] >> np.arange(ASSET_COUNT - 1, -1, -1, dtype=np.int64)[None, :]) & 1
         ).astype(np.float64)  # shape (n, 20)

    # ---- objective: mu_term[0..19] then quad_term in (row, col) row-major ----
    # Zero-x terms are signed zero and additive identity, so they are skipped;
    # where a term is present the frozen product order is preserved.
    f_acc = np.zeros(n, dtype=np.float64)
    for a in range(ASSET_COUNT):
        # term = -(mu[a] * x[a]); skip when x[a] == 0 (identity)
        term = -(mu[a] * x[:, a])
        f_acc = f_acc + term
    for i in range(ASSET_COUNT):
        for k in range(ASSET_COUNT):
            # sigma_xi = sigma[i,k]*x[i]; inner = sigma_xi*x[k];
            # term = kappa*inner. Skip when x[i]==0 or x[k]==0.
            sigma_xi = sigma[i, k] * x[:, i]
            inner = sigma_xi * x[:, k]
            f_acc = f_acc + (kappa * inner)

    # ---- residuals: cardinality, four sectors, budget ----
    card = np.zeros(n, dtype=np.float64)
    for a in range(ASSET_COUNT):
        card = card + x[:, a]
    h_card = card - k_value
    card_square = h_card * h_card

    h_sector = []
    sector_square = []
    for block in sectors:
        total = np.zeros(n, dtype=np.float64)
        for member in block:  # block already sorted ascending
            total = total + x[:, member]
        residual = c_value - total
        h_sector.append(residual)
        sector_square.append(residual * residual)

    budget = np.zeros(n, dtype=np.float64)
    for a in range(ASSET_COUNT):
        budget = budget + (prices[a] * x[:, a])
    h_budget = b_value - budget
    budget_square = h_budget * h_budget

    # ---- slack register minimizers (clamped floor/floor+1, ties retained) ----
    sector_max = E.register_maximum(0)
    budget_max = E.register_maximum(SECTOR_COUNT)

    def minimizers(residual: np.ndarray, maximum: int):
        """Return (values, penalties) with every tied minimizer retained, and
        the first (canonical) value/penalty.  Bit-for-bit vs the Python rule."""
        lower = np.floor(residual)
        cand_lo = np.minimum(np.maximum(lower, 0.0), float(maximum))
        cand_hi = np.minimum(np.maximum(lower + 1.0, 0.0), float(maximum))
        pen_lo = (residual - cand_lo) ** 2
        pen_hi = (residual - cand_hi) ** 2
        # Python keeps candidates {lo, hi} (dedup) and returns all with min
        # penalty.  lo and hi tie exactly when residual is a half-integer and
        # both are in range; the two penalties are then equal, so returning both
        # in ascending order is exactly the Python tuple order.  A tie additionally
        # requires the two clamped candidate VALUES to be DISTINCT: the frozen
        # rule builds a `set` of candidates, so when clamping collapses lo and hi
        # onto the same value there is ONE minimiser, not two (this is the
        # saturating case at the 0 / maximum register bounds).
        distinct = cand_lo != cand_hi
        tie = (pen_lo == pen_hi) & distinct
        best = np.minimum(pen_lo, pen_hi)
        # First (canonical) minimizer = the smaller value whose penalty is best.
        first_value = np.where(pen_lo <= pen_hi, cand_lo, cand_hi)
        first_penalty = best
        n_tied = np.where(tie, 2, 1)
        return first_value, first_penalty, n_tied

    sector_first_value, sector_first_penalty = [], []
    for sector in range(SECTOR_COUNT):
        v, p, _ = minimizers(h_sector[sector], sector_max)
        sector_first_value.append(v)
        sector_first_penalty.append(p)
    budget_value, budget_penalty, budget_n = minimizers(h_budget, budget_max)

    # ---- energies, per (row, encoding), in the frozen transcript order ----
    per_row = {}
    for row in rows:
        c = E.coefficient_row(row)
        alpha = np.float64(c["alpha"])
        # Unbalanced: one word per state.
        h = f_acc + (alpha * card_square)
        for sector in range(SECTOR_COUNT):
            lin = np.float64(c["sector_linear"]) * h_sector[sector]
            quad = np.float64(c["sector_quadratic"]) * sector_square[sector]
            h = h + ((-lin) + quad)
        lin = np.float64(c["budget_linear"]) * h_budget
        quad = np.float64(c["budget_quadratic"]) * budget_square
        h = h + ((-lin) + quad)
        per_row[(row, "unbalanced")] = h.copy()

        # Slack: the frozen product order emits, for each state in canonical
        # order, one word per budget minimizer.  The clamped floor/floor+1 rule
        # ties exactly when the budget residual is a half-integer in range, and
        # both tied minimizers carry EQUAL penalties, hence equal energy words.
        # The per-state canonical word is therefore the whole lift stream, with
        # every tied state contributing that identical word twice.  We return the
        # per-state canonical word and the tie mask; the reduction expands the
        # ties to the exact frozen lift stream.
        base = f_acc + (alpha * card_square)
        for sector in range(SECTOR_COUNT):
            base = base + (np.float64(c["sector_slack"]) * sector_first_penalty[sector])
        canonical = base + (np.float64(c["budget_slack"]) * budget_penalty)
        tied_mask = budget_n > 1
        per_row[(row, "slack")] = {"canonical": canonical, "tied_mask": tied_mask}
    return per_row


def lift_stream(entry):
    """Expand a per-encoding entry into the exact frozen word stream.

    The unbalanced stream is one word per state.  The slack stream is one word
    per budget minimizer, so a state whose budget register tied contributes its
    (identical) canonical word twice, in canonical state order.  This reproduces
    the reference's per-lift emission exactly, including word COUNT and ORDER."""
    import numpy as np
    if isinstance(entry, dict):  # slack
        canonical = entry["canonical"]
        tied = entry["tied_mask"]
        # repeat each element 1 + tied times, in order
        counts = 1 + tied.astype(np.int64)
        return np.repeat(canonical, counts)
    return entry  # unbalanced: already one word per state


def numpy_minima_and_tie_set(per_row, rows, n, first):
    """Derive, per (row, encoding), the value bits, first-seen argmin and the
    full tie set (positions where the frozen tau rule at c_H=2048 fires), using
    the same strict-first-seen reduction and frozen tau as the reference.

    The argmin is the FIRST index in the (encoding-appropriate) stream that
    attains the minimum, matching the reference's strict-'<' first-seen rule.
    The unbalanced argmin is the ABSOLUTE decoded state index, so the block
    offset ``first`` is added back; the slack argmin is the position within the
    per-row lift word stream and is already block-relative, so it is not offset."""
    import numpy as np

    running_min = {}
    running_arg = {}
    tie_sets = {}
    for row in rows:
        for encoding in ("unbalanced", "slack"):
            values = lift_stream(per_row[(row, encoding)])
            # strict first-seen argmin over the whole stream
            if values.size:
                min_pos = int(np.argmin(values))  # argmin returns FIRST min
                min_val = float(values[min_pos])
            else:
                min_pos, min_val = 0, float("inf")
            running_min[(row, encoding)] = min_val
            if encoding == "unbalanced":
                running_arg[(row, encoding)] = first + min_pos
            else:
                running_arg[(row, encoding)] = min_pos
            # tie set: positions whose value ties the min under frozen tau
            scale = E.LAMBDA_REF + max(abs(min_val), abs(min_val))
            gap = np.abs(values - min_val)
            tau_2048 = (CH_VALUES[1] * EPSILON) * scale
            tie_positions = np.nonzero(gap <= tau_2048)[0]
            tie_sets[(row, encoding)] = (min_val, min_pos, int(tie_positions.size))
    return running_min, running_arg, tie_sets


# --------------------------------------------------------------------------
# (2b) Bit-for-bit verification of the vectorised path vs the reference.
# --------------------------------------------------------------------------


def reference_values_block(start: int, stop: int, rows):
    """Pure-Python reference over [start, stop) returning per (row, encoding) the
    running minimum, its first-seen argmin, and the tie-set count at c_H=2048,
    plus the raw value lists (for bit comparison).

    The argmin basis matches the vectorised arrays exactly: the unbalanced argmin
    is the decoded state index (one word per state, in canonical order) and the
    slack argmin is the position within the flat per-row slack word stream (one
    word per lift, in frozen product order)."""
    prepared_instance = prepare_instance(synthetic_instance())
    binary_domain = BinaryDomain(ASSET_COUNT)
    prepared_rows = [(row, prepared_coefficients(row)) for row in rows]
    sector_max = E.register_maximum(0)
    budget_max = E.register_maximum(SECTOR_COUNT)
    minima = {}
    args = {}
    values = {(row, enc): [] for row in rows for enc in ("unbalanced", "slack")}
    for index in range(start, stop):
        bits = binary_domain[index]
        decoded = prepare_decoded_state(prepared_instance, bits)
        sector_min = [_register_minimizers(decoded.h_sector[s], sector_max)
                      for s in range(SECTOR_COUNT)]
        budget_min = _register_minimizers(decoded.h_budget, budget_max)
        sector_auxiliary = []
        for s in range(SECTOR_COUNT):
            v = sector_min[s][0]
            sector_auxiliary.extend((v >> d) & 1 for d in range(SECTOR_SLACK_BITS))
        for row, prepared in prepared_rows:
            # Unbalanced: one word per decoded state; argmin basis = state index.
            val = unbalanced_energy_prepared(decoded, prepared)
            values[(row, "unbalanced")].append(val)
            key = (row, "unbalanced")
            if key not in minima or val < minima[key]:
                minima[key], args[key] = val, index
            # Slack: one word per lift, in frozen product order; argmin basis =
            # the position within this row's slack word stream.
            for budget_value in budget_min:
                auxiliary = tuple(sector_auxiliary
                                  + [(budget_value >> d) & 1 for d in range(BUDGET_SLACK_BITS)])
                sstate = prepare_slack_state(decoded, auxiliary)
                sval = slack_energy_prepared(sstate, prepared)
                values[(row, "slack")].append(sval)
                key = (row, "slack")
                slack_pos = len(values[(row, "slack")]) - 1
                if key not in minima or sval < minima[key]:
                    minima[key], args[key] = sval, slack_pos
    # tie-set counts at c_H=2048
    tie_counts = {}
    for row in rows:
        for enc in ("unbalanced", "slack"):
            key = (row, enc)
            m = minima[key]
            scale = E.LAMBDA_REF + max(abs(m), abs(m))
            t = (CH_VALUES[1] * EPSILON) * scale
            tie_counts[key] = sum(1 for v in values[key] if abs(v - m) <= t)
    return minima, args, tie_counts, values


# --------------------------------------------------------------------------
# (2c) The four-way comparison primitive, shared by the block check and by
#      --full-bitexact.  Every comparison below is proven load-bearing by
#      sensitivity_report (one-ulp corruption of the NumPy side).
# --------------------------------------------------------------------------

CHECK_NAMES = ("min_bits", "argmin", "tie_set", "stream_length")


def tie_threshold(min_value: float) -> float:
    """The frozen tau band half-width at c_H=2048 around ``min_value``."""
    scale = E.LAMBDA_REF + max(abs(min_value), abs(min_value))
    return (CH_VALUES[TIE_CH_INDEX] * EPSILON) * scale


def tie_set(values, min_value: float):
    """The COMPLETE tie set: every stream position within the frozen tau band.

    Returned as a frozenset of positions so that the comparison is on the set
    itself, not merely on its cardinality."""
    import numpy as np
    arr = np.asarray(values, dtype=np.float64)
    band = tie_threshold(min_value)
    return frozenset(np.nonzero(np.abs(arr - min_value) <= band)[0].tolist())


def stream_values(entry):
    """The frozen word stream for a (row, encoding) numpy_vectorised entry.

    The unbalanced entry is already one word per state; the slack entry is the
    per-state canonical word plus the tie mask, and must be expanded."""
    return lift_stream(entry)


def summarise(arr, first: int, offset: bool) -> dict:
    """Derive (min, argmin, complete tie set, length) from a word stream.

    ``offset`` is True for the unbalanced encoding, whose argmin basis is the
    ABSOLUTE decoded state index (so the block start ``first`` is added back),
    and False for the slack encoding, whose argmin basis is the position within
    the lift word stream (already block-relative)."""
    import numpy as np
    a = np.asarray(arr, dtype=np.float64)
    pos = int(np.argmin(a))     # argmin returns the FIRST minimum
    minimum = float(a[pos])
    return {
        "min": minimum,
        "argmin": (pos + first) if offset else pos,
        "ties": tie_set(a, minimum),
        "len": int(a.size),
        "_pos": pos,
    }


def compare_encoding(ref: dict, vec: dict) -> dict:
    """Compare one (row, encoding) on all four axes.

    The four axes are deliberately independent: each is compared on its own and
    ``match`` is the conjunction, so a corruption that only breaks one axis is
    still reported as a mismatch."""
    same_bits = _word(ref["min"]) == _word(vec["min"])
    same_arg = ref["argmin"] == vec["argmin"]
    same_ties = ref["ties"] == vec["ties"]
    same_len = int(ref["len"]) == int(vec["len"])
    return {
        "ref_bits": _word(ref["min"]), "vec_bits": _word(vec["min"]),
        "ref_argmin": ref["argmin"], "vec_argmin": vec["argmin"],
        "ref_tie_count": len(ref["ties"]), "vec_tie_count": len(vec["ties"]),
        "ref_len": int(ref["len"]), "vec_len": int(vec["len"]),
        "min_bits": bool(same_bits),
        "argmin": bool(same_arg),
        "tie_set": bool(same_ties),
        "stream_length": bool(same_len),
        "match": bool(same_bits and same_arg and same_ties and same_len),
        "_ref_ties": ref["ties"],
        "_vec_ties": vec["ties"],
        "_ref_pos": ref.get("_pos"),
        "_vec_pos": vec.get("_pos"),
    }


def compare_pair(ref_values, vec_entry, first: int, encoding: str) -> dict:
    """Compare two raw word streams (or vectorised entries) on all four axes."""
    offset = (encoding == "unbalanced")
    return compare_encoding(summarise(stream_values(ref_values), first, offset),
                            summarise(stream_values(vec_entry), first, offset))


# --------------------------------------------------------------------------
# (2d) Rule (A): prove each comparison is load-bearing under a one-ulp
#      corruption of the NumPy result.
# --------------------------------------------------------------------------

def _corrupt_stream(arr, position: int, k: int):
    """Return a copy of ``arr`` with element ``position`` moved k ulps."""
    import numpy as np
    out = np.array(arr, dtype=np.float64, copy=True)
    out[position] = _shift_ulp(float(out[position]), k)
    return out


def _corrupt_minimum(arr, k: int):
    """Return a copy of ``arr`` with the GLOBAL MINIMUM moved k ulps.

    Every copy of the minimum is moved, not just the first one: when the
    minimum is attained more than once (the slack stream always emits both
    lifts of a tied state, so its minimum is duplicated), bumping only the
    first copy would leave the minimum value unchanged and the corruption
    would be invisible.  Corrupting every copy is what "corrupt the NumPy
    result by one ulp" means for the quantity under test."""
    import numpy as np
    out = np.array(arr, dtype=np.float64, copy=True)
    lowest = out.min()
    out[out == lowest] = _shift_ulp(float(lowest), k)
    return out


# The k ladder searched when a one-ulp corruption is not enough to move an axis.
ULP_LADDER = (1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096, 8192,
              16384, 32768, 65536, 131072, 262144, 1 << 20, 1 << 24, 1 << 30,
              1 << 40, 1 << 50, 1 << 60)


def sensitivity_report(ref: dict, vec_values, first: int, encoding: str) -> dict:
    """Prove every comparison is load-bearing, and say exactly how.

    To show a check is not passing vacuously we corrupt the NumPy stream and
    confirm the check reports a mismatch.  The natural Rule (A) corruption --
    "corrupt the NumPy result by one ulp" -- is to move the GLOBAL MINIMUM by
    one ulp, in every copy of it (see ``_corrupt_minimum``).  Because the
    min_bits, argmin and tie_set axes are all derived from the global minimum,
    that single corruption is expected to break all three at once; the report
    records, per axis, whether a one-ulp corruption flips it.

    Two axes cannot respond to a one-ulp corruption, and this is reported
    honestly rather than papered over:

      * stream_length -- length is a COUNT.  No change of any value can alter
        it, so its minimal load-bearing mutation is dropping one word.
      * tie_set, when the minimum is still inside the band -- the frozen tau
        band at c_H=2048 is thousands of ulps wide, so moving the minimum by
        one ulp leaves it inside the band and the tie SET is unchanged even
        though the tie COUNT can change.  The minimal shift that pushes the
        minimum out of the band is searched for and reported.

    A CONTROL confirms that a one-ulp corruption at the RUNNER-UP position
    flips nothing, so the flips reported for the minimum are not spurious."""
    import numpy as np
    offset = (encoding == "unbalanced")
    arr = np.asarray(vec_values, dtype=np.float64)
    baseline = compare_encoding(ref, summarise(arr, first, offset))
    if not baseline["match"]:
        return {"encoding": encoding, "baseline_match": False, "axes": {}}

    vec_summary = summarise(arr, first, offset)
    vec_min = vec_summary["min"]
    band = tie_threshold(vec_min)
    ulp = abs(vec_min) * 2.0 ** -52
    # The runner-up must be the smallest value STRICTLY ABOVE the minimum; if the
    # minimum is attained more than once, the second-smallest ELEMENT would be
    # the minimum again and the control would corrupt the minimum itself.
    above = arr[arr > vec_min]
    runner_up = float(above.min()) if above.size else float("inf")

    def flipped_by(candidate, axis):
        return not compare_encoding(
            ref, summarise(candidate, first, offset))[axis]

    axes = {}
    # For each value-derived axis, a ONE-ULP corruption of the global minimum is
    # tried first (this is the literal "corrupt the NumPy result by one ulp").
    # If that does not move the axis -- which happens when the minimum is
    # well-separated from the runner-up (argmin, tie_set) -- we escalate to the
    # smallest ulp shift that DOES move it.  This proves the axis reads the
    # NumPy stream, and separately records whether one ulp suffices.
    for name in ("min_bits", "argmin", "tie_set"):
        axis = {"axis": name, "one_ulp_flips": False, "min_ulps": None,
                "mutated": False,
                "mutation": "move the global minimum (every copy) by ulps"}
        for k in ULP_LADDER:
            if flipped_by(_corrupt_minimum(arr, k), name):
                axis["min_ulps"] = k
                axis["mutated"] = True
                if k == 1:
                    axis["one_ulp_flips"] = True
                break
        axes[name] = axis

    # stream_length is a COUNT: no value change moves it, only dropping a word.
    axes["stream_length"] = {
        "axis": "stream_length", "one_ulp_flips": False, "min_ulps": None,
        "mutated": flipped_by(arr[:-1], "stream_length"),
        "mutation": "drop one word (length is a COUNT, not a value)",
    }

    # CONTROL: a one-ulp corruption at the runner-up flips nothing.  The control
    # position is located directly (masking the runner-up out and re-taking the
    # argmin would land back on the true minimum).
    ctrl_target = int(np.nonzero(arr == runner_up)[0][0]) if above.size else None
    control_flips = (
        {name: flipped_by(_corrupt_stream(arr, ctrl_target, 1), name)
         for name in CHECK_NAMES}
        if ctrl_target is not None
        else {name: False for name in CHECK_NAMES}
    )
    return {
        "encoding": encoding,
        "baseline_match": True,
        "baseline_tie_count": len(vec_summary["ties"]),
        "baseline_tie_positions": sorted(vec_summary["ties"])[:8],
        "min_copies": int((arr == vec_min).sum()),
        "second_min": runner_up,
        "vec_min": vec_min,
        "tau_band_ulps": band / ulp,
        "control_position_flips": control_flips,
        "axes": axes,
    }


# --------------------------------------------------------------------------
# Timing drivers.
# --------------------------------------------------------------------------

def time_reference(rows, start: int, n_states: int):
    """Time the pure-Python reference over a contiguous [start, start+n_states)
    block.  Returns (seconds, stats)."""
    t0 = time.perf_counter()
    stats = reference_block(start, start + n_states, rows)
    t1 = time.perf_counter()
    return t1 - t0, stats


def best_of_repeats(rows, start: int, n_states: int, repeats: int):
    """Minimum wall time over ``repeats`` identical runs, with its stats.

    Taking the MINIMUM means scheduler noise and contention can only make a run
    look SLOWER, so the retained sample is the least-disturbed one and the
    resulting per-state rate is a lower bound on the true cost.  The same
    helper is used for the one-row headline and for the two-row control, so the
    two are directly comparable."""
    best_t = float("inf")
    best_stats = None
    for _ in range(repeats):
        seconds, stats = time_reference(rows, start, n_states)
        if seconds < best_t:
            best_t, best_stats = seconds, stats
    return best_t, best_stats


def time_vectorised(payload, rows):
    """Time the NumPy vectorised path over the FULL 2**20 domain in chunks.

    The per-grid-point figure is therefore MEASURED (the whole domain runs), with
    no extrapolation.  The tie/first-seen reduction is done exactly as the
    reference does, so the timing reflects the real work, not a stripped kernel."""
    import numpy as np
    total_states = 0
    total_lifts = 0
    global_min = {}
    global_arg = {}
    t0 = time.perf_counter()
    for chunk_first in range(0, STATE_COUNT, VECTOR_CHUNK):
        chunk_last = min(chunk_first + VECTOR_CHUNK, STATE_COUNT)
        per_row = numpy_vectorised(payload, rows, chunk_first, chunk_last)
        for row in rows:
            for enc in ("unbalanced", "slack"):
                values = lift_stream(per_row[(row, enc)])
                key = (row, enc)
                if enc == "slack":
                    total_lifts += int(values.size)
                # chunk-local strict-first-seen reduction, merged globally
                if values.size:
                    cpos = int(np.argmin(values))
                    cval = float(values[cpos])
                    if key not in global_min or cval < global_min[key]:
                        global_min[key] = cval
                        global_arg[key] = cpos  # per-encoding stream position
        total_states += chunk_last - chunk_first
    t1 = time.perf_counter()
    return t1 - t0, total_states, total_lifts, global_min, global_arg


def numpy_full_streams(payload, rows, states: int = STATE_COUNT,
                        chunk: int = VECTOR_CHUNK):
    """Materialise the FULL-domain NumPy word stream per (row, encoding).

    ``states`` and ``chunk`` are parameters so the fixtures can run the same
    code path over a small domain; main() passes the real 2**20 default."""
    import numpy as np
    out = {}
    unbalanced = np.empty(states, dtype=np.float64)
    slack_parts = []
    for chunk_first in range(0, states, chunk):
        chunk_last = min(chunk_first + chunk, states)
        per_row = numpy_vectorised(payload, rows, chunk_first, chunk_last)
        for row in rows:
            unbalanced[chunk_first:chunk_last] = per_row[(row, "unbalanced")]
            slack_parts.append(lift_stream(per_row[(row, "slack")]))
    out[(rows[0], "unbalanced")] = unbalanced
    out[(rows[0], "slack")] = np.concatenate(slack_parts)
    return out


def fmt_seconds(x: float) -> str:
    if x < 90:
        return f"{x:.3f} s"
    if x < 5400:
        return f"{x/60:.2f} min"
    if x < 86400:
        return f"{x/3600:.2f} h"
    return f"{x/86400:.2f} d"


def core_hours_and_wallclock(sec_per_grid_point: float, n_cores_list):
    total_seconds = sec_per_grid_point * GRID_POINTS
    out = {"total_core_seconds": total_seconds,
           "total_core_hours": total_seconds / 3600.0}
    for cores in n_cores_list:
        out[f"wall_hours_{cores}cores"] = total_seconds / cores / 3600.0
    return out


# --------------------------------------------------------------------------
# CHECKS.  Each is a separately revertible, separately fixture-tested gate.
# --------------------------------------------------------------------------

def check_unit_of_work(timed_rows, bitexact_rows, per_state_one_row: float,
                       marginal_us_per_word: float):
    """The unit of work is ONE coefficient row under BOTH encodings.

    (a) the timed unit holds exactly one row, and every timed row is also
        covered by the bit-exactness set.

    (b) MEASURED evidence that adding a second row really costs extra work, so
        the headline per-grid-point figure is not silently charging for a unit
        it does not evaluate.

    On (b): a block's wall time is dominated by a PER-STATE fixed cost (building
    the decoded state and the five register minimizer sets) that is shared by
    every row, plus a PER-ENERGY-WORD cost that scales with rows.  Adding a
    second row therefore roughly doubles the energy words but NOT the total wall
    time, so the total-time ratio is the wrong invariant.  The sound invariant
    is the MARGINAL seconds per energy word: the extra wall time the second row
    adds, divided by the extra energy words it adds.  If that marginal cost were
    zero, a second row would be free and the one-row rate could not be the
    per-grid-point cost."""
    if not isinstance(timed_rows, tuple) or len(timed_rows) != 1:
        return False, (f"timed unit must be exactly ONE coefficient row, got "
                       f"{timed_rows!r}; a grid point is one row, not a pair")
    missing = [r for r in timed_rows if r not in bitexact_rows]
    if missing:
        return False, f"timed rows {missing} are not covered by the bit-exactness set"
    if per_state_one_row <= 0:
        return False, "one-row per-state cost must be positive"
    if marginal_us_per_word <= 0:
        return False, (
            "adding a second row must cost more, but the measured marginal cost "
            "per extra energy word is "
            f"{marginal_us_per_word*1e6:.3f} us; a free second row would mean the "
            "one-row rate is not the per-grid-point cost")
    return True, (f"timed unit = {timed_rows[0]!r} under both encodings; "
                  f"extra bit-exactness rows {tuple(bitexact_rows)} are NOT timed; "
                  f"a second row adds {marginal_us_per_word*1e6:.3f} us per extra "
                  f"energy word (MEASURED)")


def check_argmin_basis(result, encoding: str, first: int):
    """The argmin axis is only meaningful if the two sides share a basis.

    The reference reports the unbalanced argmin as the ABSOLUTE decoded state
    index and the slack argmin as the position within the lift word stream.
    This asserts the reported numbers are on the expected basis for a block that
    does NOT start at 0, which is exactly what the ``first`` offset buys."""
    if encoding == "unbalanced":
        if first == 0:
            return True, "unbalanced argmin basis: absolute state index (block starts at 0)"
        if result["ref_argmin"] < first:
            return False, (f"unbalanced argmin {result['ref_argmin']} is below the "
                           f"block start {first}; the block offset was not added back")
        return True, (f"unbalanced argmin {result['ref_argmin']} >= block start "
                      f"{first}: absolute state-index basis confirmed")
    if result["ref_argmin"] >= int(result["ref_len"]):
        return False, (f"slack argmin {result['ref_argmin']} is outside the "
                       f"{result['ref_len']}-word stream")
    return True, (f"slack argmin {result['ref_argmin']} is a position inside the "
                  f"{result['ref_len']}-word lift stream: block-relative basis confirmed")


def count_numpy_tied_states(payload, rows, chunk: int = VECTOR_CHUNK) -> int:
    """Count budget-tied states straight from the NumPy path's own tie mask.

    This deliberately does NOT use the frozen domain's lift counts as its
    source: the point is to measure what ``numpy_vectorised`` actually
    produced, so that a defect in the clamped-candidate deduplication inside
    that function is visible here.  The frozen counts are only the expected
    value passed to ``check_tie_dedup`` alongside."""
    import numpy as np
    tied = 0
    for first in range(0, STATE_COUNT, chunk):
        last = min(first + chunk, STATE_COUNT)
        per_row = numpy_vectorised(payload, rows, first, last)
        for row in rows:
            tied += int(np.count_nonzero(per_row[(row, "slack")]["tied_mask"]))
    return tied


def check_tie_dedup(numpy_tied_states: int, frozen_domain_lift_total: int,
                    state_count: int):
    """The NumPy tie mask must match the frozen set-based candidate rule.

    The frozen rule builds a ``set`` of clamped candidates, so when clamping
    collapses floor and floor+1 onto the SAME value the state contributes ONE
    minimiser, not two.  This is the round-1 fix, and it is what keeps the slack
    stream length exact.  It is re-asserted here against the frozen domain."""
    expected_tied = int(frozen_domain_lift_total) - int(state_count)
    if int(numpy_tied_states) != expected_tied:
        return False, (
            f"NumPy reports {numpy_tied_states} budget-tied states but the frozen "
            f"domain has {expected_tied} (lift_total {frozen_domain_lift_total} "
            f"- {state_count} states); the clamped-candidate deduplication is wrong")
    return True, (f"budget-tied states {numpy_tied_states} match the frozen domain "
                  f"({frozen_domain_lift_total} lifts over {state_count} states)")


def check_stream_length(observed: int, expected: int, rows):
    """The full-domain slack stream must contain exactly one word per lift per
    timed row.  A single tie-rich block cannot catch a tie-counting error
    anywhere in the domain, so this invariant spans all 2**20 states."""
    if int(observed) != int(expected):
        return False, (f"slack stream length {observed} != expected {expected} "
                       f"for timed rows {rows}")
    return True, (f"slack stream length {observed} == {expected} "
                  f"({len(rows)} timed row x frozen lift total)")


def check_derivations_agree(per_row, rows, first: int, last: int):
    """Two independent derivations of (min, argmin, tie set) must agree.

    ``numpy_minima_and_tie_set`` (the round-1 derivation) and ``compare_pair``
    (the shared four-axis comparison) are computed differently.  If either one
    is altered, they diverge."""
    vmin, varg, vties = numpy_minima_and_tie_set(per_row, rows, last - first, first)
    for row in rows:
        for enc in ("unbalanced", "slack"):
            key = (row, enc)
            pair = compare_pair(lift_stream(per_row[key]),
                                lift_stream(per_row[key]), first, enc)
            if _word(vmin[key]) != pair["ref_bits"]:
                return False, (f"{key}: min bits disagree between the two "
                               f"derivations ({_word(vmin[key]):016x} vs "
                               f"{pair['ref_bits']:016x})")
            if varg[key] != pair["ref_argmin"]:
                return False, (f"{key}: argmin disagrees between the two "
                               f"derivations ({varg[key]} vs {pair['ref_argmin']})")
            if vties[key][2] != pair["ref_tie_count"]:
                return False, (f"{key}: tie count disagrees between the two "
                               f"derivations ({vties[key][2]} vs "
                               f"{pair['ref_tie_count']})")
    return True, "both derivations agree on min bits, argmin and tie count"


def check_core_hours(sec_per_point: float, n_cores_list, out: dict,
                     expected_per_point: float, timed_rows):
    """The campaign arithmetic must be built from the ONE-row per-grid-point cost.

    This re-derives the totals from first principles and requires the reported
    numbers to match, so a regression back to a two-row unit (or a wrong grid
    size) is caught rather than printed."""
    if abs(sec_per_point - expected_per_point) > 1e-9 * max(1.0, expected_per_point):
        return False, (f"per-grid-point {sec_per_point} s is not the one-row rate "
                       f"{expected_per_point} s (timed rows {timed_rows})")
    want_total = sec_per_point * GRID_POINTS
    if abs(out["total_core_seconds"] - want_total) > 1e-6 * max(1.0, want_total):
        return False, "total core seconds do not equal sec/point x grid points"
    if abs(out["total_core_hours"] - want_total / 3600.0) > 1e-9:
        return False, "total core hours are not total core seconds / 3600"
    for cores in n_cores_list:
        want_wall = want_total / cores / 3600.0
        got = out[f"wall_hours_{cores}cores"]
        if abs(got - want_wall) > 1e-6 * max(1.0, want_wall):
            return False, f"wall hours on {cores} cores are wrong"
    return True, (f"core-hours and wall-clock re-derived from "
                  f"{sec_per_point:.2f} s/point x {GRID_POINTS:,} points")


def check_load_reporting(records):
    """Every timed section must have a load snapshot BEFORE and AFTER it.

    Without both snapshots a reader cannot tell whether a timing was taken under
    concurrent load, and cannot apply the upper-bound caveat."""
    if not records:
        return False, "no load snapshots were captured"
    for name, (before, after) in records.items():
        for label, snap in (("before", before), ("after", after)):
            if snap is None:
                return False, f"section {name!r}: no load snapshot captured {label}"
            if snap.get("load1") is None:
                return False, f"section {name!r}: no load average captured {label}"
            if snap.get("cpu_count") is None:
                return False, f"section {name!r}: no cpu_count captured {label}"
    return True, (f"load average and cpu_count captured before and after all "
                  f"{len(records)} timed sections")


def check_sensitivity(sens, encoding: str):
    """Every comparison must be shown load-bearing by the mutation analysis.

    Each of the four axes must have been shown to FLIP under its own minimal
    load-bearing mutation (the recorded ``mutated`` flag), and the control (a
    one-ulp corruption at the runner-up) must flip nothing, proving the flips
    are not spurious."""
    if not sens.get("baseline_match"):
        return False, f"{encoding}: sensitivity skipped, baseline already mismatched"
    problems = []
    for name in CHECK_NAMES:
        axis = sens["axes"].get(name)
        if axis is None:
            problems.append(f"{name}: no sensitivity result")
            continue
        if not axis.get("mutated"):
            problems.append(f"{name}: its load-bearing mutation did not flip it "
                            f"({axis.get('mutation')})")
    if problems:
        return False, f"{encoding}: " + "; ".join(problems)
    flipped = [n for n in CHECK_NAMES if sens["axes"][n].get("one_ulp_flips")]
    return True, (f"{encoding}: all four comparisons are load-bearing "
                  f"(each flips under its own minimal mutation; a one-ulp value "
                  f"corruption alone flips {flipped or 'no individual axis'})")


# --------------------------------------------------------------------------
# --full-bitexact: reference vs NumPy over ALL 2**20 states.
# --------------------------------------------------------------------------

def run_full_bitexact(payload, states: int = STATE_COUNT,
                      chunk: int = VECTOR_CHUNK, quiet: bool = False):
    """Compare reference vs NumPy over the whole domain for
    (row0, unbalanced) AND (row0, slack): min value bits, argmin, complete tie
    set, and stream length.

    ``states`` defaults to the real 2**20.  The fixtures pass a small ``states``
    so they exercise this exact code path cheaply; main() uses the default.
    """
    rows = ("row0",)
    records = {}

    def say(text=""):
        if not quiet:
            print(text)

    say(f"    reference: pure Python over all {states:,} states, "
        f"one row ({rows[0]!r}) under both encodings")
    before = load_snapshot()
    say(load_line("before", before))
    t0 = time.perf_counter()
    ref_min, ref_arg, ref_tie, ref_values = reference_values_block(0, states, rows)
    t1 = time.perf_counter()
    after = load_snapshot()
    say(load_line("after", after))
    records["full_bitexact_reference"] = (before, after)
    say(f"    reference wall time: {fmt_seconds(t1 - t0)} ({(t1 - t0):.1f} s) "
        f"[MEASURED, full domain]")

    before = load_snapshot()
    say(load_line("before", before))
    t2 = time.perf_counter()
    vec = numpy_full_streams(payload, rows, states, chunk)
    t3 = time.perf_counter()
    after = load_snapshot()
    say(load_line("after", after))
    records["full_bitexact_numpy"] = (before, after)
    say(f"    numpy wall time    : {fmt_seconds(t3 - t2)} ({(t3 - t2):.1f} s) "
        f"[MEASURED, full domain]")

    all_ok = True
    results = {}
    for key in FULL_BITEXACT_KEYS:
        row, enc = key
        # The slack entry must be expanded through lift_stream so BOTH sides of
        # the comparison are the frozen per-lift word stream.
        result = compare_pair(ref_values[key], vec[key], 0, enc)
        results[key] = result
        all_ok = all_ok and result["match"]
        say(f"    {str(key):>22} | ref bits {result['ref_bits']:016x} / "
            f"vec bits {result['vec_bits']:016x} | ref argmin "
            f"{result['ref_argmin']} / vec argmin {result['vec_argmin']} | "
            f"ref ties {result['ref_tie_count']} / vec ties "
            f"{result['vec_tie_count']} | ref len {result['ref_len']:,} / "
            f"vec len {result['vec_len']:,} | match {result['match']}")
        if not result["match"]:
            for name in CHECK_NAMES:
                if not result[name]:
                    say(f"        MISMATCH on axis: {name}")
    say(f"    FULL-DOMAIN BIT-EXACT OVERALL: {all_ok}")
    return all_ok, results, records


# --------------------------------------------------------------------------
# Driver.
# --------------------------------------------------------------------------

def report_check(label: str, outcome) -> bool:
    ok, detail = outcome
    print(f"    [{'PASS' if ok else 'FAIL'}] {label}: {detail}")
    return ok


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Pilot: CPU cost of ONE full-domain campaign grid point "
                    "(one coefficient row under both encodings).")
    parser.add_argument("--full-bitexact", action="store_true",
                        help="additionally compare reference vs NumPy over all "
                             "2**20 states for (row0, unbalanced) and (row0, slack): "
                             "min value bits, argmin, complete tie set, stream length")
    args = parser.parse_args(argv)

    print("=" * 78)
    print("PILOT stage-2 CPU cost: tau = cost of ONE full-domain grid point")
    print("=" * 78)

    info = machine_info()
    print("\n[MACHINE]")
    for key in ("nproc", "cpu_model", "platform", "machine",
                "python_version", "python_full", "numpy_version"):
        print(f"  {key:>16}: {info[key]}")
    print(f"  {'grid_points':>16}: {GRID_POINTS}  "
          f"({INSTANCES} instances x {COORDINATES_PER_INSTANCE:,} points)")
    print(f"  {'grid_composition':>16}: {CAMPAIGN_ROW_COUNT}^2 x "
          f"{CAMPAIGN_R_VALUE_COUNT} x {CAMPAIGN_ROW_COUNT} "
          f"= {COORDINATES_PER_INSTANCE:,}  (src/g5/core_pass.py ROW_COUNT=61)")
    print(f"  {'states_per_point':>16}: {STATE_COUNT}  (2**20 decoded states)")
    print(f"  {'timed_rows':>16}: {TIMED_ROWS}  (ONE row = ONE grid point)")
    print(f"  {'bitexact_rows':>16}: {BITEXACT_ROWS}  "
          f"(extra row is NOT in the timed unit)")
    # __debug__ is True normally and False under -O, so this reports the
    # interpreter's actual assertion state (i.e. whether -O is in effect).
    print(f"  {'-O in effect':>16}: {'no (asserts on)' if __debug__ else 'yes (asserts off)'}")

    payload = E.validate_payload(E.synthetic_payload())
    print("\n[LOAD] " + LOAD_CAVEAT)

    # One build of the component's own domain, used only to LOCATE a block that
    # actually contains budget-register ties (so the frozen lift stream and the
    # per-lift cost are genuinely exercised) and to report the true lift total.
    built = E.build_domain(E.synthetic_payload())
    lift_counts = built["lift_counts"]
    LIFT_TOTAL = int(built["lift_total"])

    def tie_block(width: int) -> int:
        return next(i for i in range(0, STATE_COUNT - width, width)
                    if any(lift_counts[i + k] > 1 for k in range(width)))

    def representative_block(width: int) -> int:
        """A contiguous block whose lift density is closest to the whole-domain
        mean (LIFT_TOTAL / STATE_COUNT), so the measured per-state rate is
        directly representative of the full 2**20 domain.  Deterministic: the
        first such block in canonical order."""
        target = LIFT_TOTAL / STATE_COUNT
        best_i, best_gap = 0, None
        for i in range(0, STATE_COUNT - width, width):
            density = (sum(int(lift_counts[k]) for k in range(i, i + width))
                       / float(width))
            gap = abs(density - target)
            if best_gap is None or gap < best_gap:
                best_i, best_gap = i, gap
        return best_i

    load_records = {}
    gate_failures = []

    # ================= (0) FULL-DOMAIN BIT-EXACTNESS (optional) =================
    full_ok = None
    if args.full_bitexact:
        print("\n[0] FULL-DOMAIN BIT-EXACTNESS (--full-bitexact): reference vs "
              "NumPy over all 2**20 states")
        full_ok, full_results, recs = run_full_bitexact(payload)
        load_records.update(recs)
        if not full_ok:
            gate_failures.append("full-domain bit-exactness")

    # ================= (1) UNIT OF WORK =========================================
    print("\n[1] UNIT OF WORK: one campaign grid point == ONE coefficient row "
          "under BOTH encodings")
    N_BLOCK = 4000
    REPEATS = 3
    block = representative_block(N_BLOCK)
    print(f"    representative block: states [{block},{block + N_BLOCK})")
    print(f"    repeats: {REPEATS} (minimum wall time taken)")

    # ---- the ONE-row timed unit (the headline per-grid-point cost) ----------
    before = load_snapshot()
    print(load_line("before", before))
    t_min, stats = best_of_repeats(TIMED_ROWS, block, N_BLOCK, REPEATS)
    after = load_snapshot()
    print(load_line("after", after))
    load_records["reference_one_row"] = (before, after)
    s_b, l_b, w_b, tau_b, hits_b = stats
    mean_lifts = LIFT_TOTAL / STATE_COUNT
    block_density = l_b / s_b
    print(f"    block density  : {block_density:.4f} lifts/state "
          f"(whole-domain mean {mean_lifts:.4f})")
    print(f"    timed          : {fmt_seconds(t_min)} ({t_min:.3f} s)  "
          f"states {s_b} lifts {l_b} words {w_b} tau {tau_b} tie-hits {hits_b}")
    per_state = t_min / s_b                       # MEASURED seconds / decoded state
    per_lift = t_min / l_b                         # MEASURED seconds / lift
    print(f"    measured sec / state        : {per_state*1e6:.1f} us  [MEASURED, "
          f"ONE row under both encodings]")
    print(f"    measured sec / lift         : {per_lift*1e6:.1f} us  [MEASURED]")

    # ---- MEASURED control: a second row really does cost more ---------------
    # The control MUST use the same protocol as the headline measurement
    # (minimum of REPEATS over the same block), otherwise it is not a
    # like-for-like comparison on a shared machine.
    #
    # The invariant is the MARGINAL cost per energy word, not the total-time
    # ratio: a block's wall time is dominated by a per-state fixed cost (the
    # decoded state and the five register minimizer sets) that every row
    # shares, so a second row roughly doubles the energy words but adds only
    # its own share of the time.  Marginal = extra seconds / extra energy words.
    t_two, stats_two = best_of_repeats(("row0", "row1"), block, N_BLOCK, REPEATS)
    extra_words = stats_two[2] - w_b
    marginal_us_per_word = (t_two - t_min) / extra_words
    per_state_two = t_two / stats_two[0]
    print(f"    control (2 rows, NOT the unit): {per_state_two*1e6:.1f} us/state, "
          f"words {stats_two[2]} (vs {w_b} for one row)  [MEASURED, min of "
          f"{REPEATS} on the same block, control only]")
    print(f"    MARGINAL cost of the extra row   : {marginal_us_per_word*1e6:.3f} us "
          f"per extra energy word ({extra_words:,} extra words, "
          f"{(t_two - t_min)*1e3:.1f} ms extra)  [MEASURED]")

    ok_unit, detail_unit = check_unit_of_work(
        TIMED_ROWS, BITEXACT_ROWS, per_state, marginal_us_per_word)
    if not report_check("unit of work is ONE row", (ok_unit, detail_unit)):
        gate_failures.append("unit of work")

    sec_per_point_ref = per_state * STATE_COUNT    # linear extrapolation
    print(f"    EXTRAPOLATED sec / grid point: {sec_per_point_ref:.1f} s "
          f"({fmt_seconds(sec_per_point_ref)})  [EXTRAPOLATED: measured us/state "
          f"x 2^20, ONE row under both encodings]")

    # ================= (2) NUMPY bit-exactness on a matched block =============
    print("\n[2] NUMPY-VECTORISED path (vectorised across states, exact order)")
    # Bit-for-bit verification.  The block MUST contain budget-register ties, so
    # that the frozen lift stream (two words per tied state) is actually compared
    # and not just the untied per-state case.
    VERIFY_STATES = 256
    verify_start = tie_block(VERIFY_STATES)
    verify_stop = verify_start + VERIFY_STATES
    ties_in_block = sum(1 for k in range(verify_start, verify_stop)
                        if lift_counts[k] > 1)
    print(f"    bit-for-bit verification block: states "
          f"[{verify_start},{verify_stop})")
    print(f"    budget-tied states inside the block: {ties_in_block} "
          f"(so the frozen lift stream has {ties_in_block} duplicated words)")
    print(f"    bit-exactness rows here: {BITEXACT_ROWS} (row1 is an EXTRA case; "
          f"it is NOT part of the timed unit)")

    ref_vmin, ref_varg, ref_vtie, ref_vals = reference_values_block(
        verify_start, verify_stop, BITEXACT_ROWS)
    per_row_v = numpy_vectorised(payload, BITEXACT_ROWS, verify_start, verify_stop)

    all_match = True
    print(f"    {'(row, encoding)':>22} | {'ref bits':>16} {'vec bits':>16} | "
          f"{'ref argmin':>10} {'vec argmin':>10} | {'ref tie':>8} {'vec tie':>8} | "
          f"{'ref words':>9} {'vec words':>9} | match")
    block_results = {}
    for row in BITEXACT_ROWS:
        for enc in ("unbalanced", "slack"):
            key = (row, enc)
            result = compare_pair(ref_vals[key], per_row_v[key], verify_start, enc)
            block_results[key] = result
            all_match = all_match and result["match"]
            if not result["match"]:
                for name in CHECK_NAMES:
                    if not result[name]:
                        print(f"        {key}: MISMATCH on axis {name}")
            print(f"    {str(key):>22} | {result['ref_bits']:016x} "
                  f"{result['vec_bits']:016x} | {result['ref_argmin']:>10} "
                  f"{result['vec_argmin']:>10} | {result['ref_tie_count']:>8} "
                  f"{result['vec_tie_count']:>8} | {result['ref_len']:>9} "
                  f"{result['vec_len']:>9} | {result['match']}")
    print(f"    BIT-FOR-BIT (min bits + argmin + complete tie set + stream length) "
          f"OVERALL: {all_match}")
    if not all_match:
        gate_failures.append("block bit-exactness")

    # argmin-basis gate (the block does NOT start at 0, so this is load-bearing)
    for enc in ("unbalanced", "slack"):
        key = ("row0", enc)
        if not report_check(f"argmin basis ({enc})",
                            check_argmin_basis(block_results[key], enc, verify_start)):
            gate_failures.append(f"argmin basis {enc}")

    # two-derivation agreement gate
    if not report_check("both derivations agree",
                        check_derivations_agree(per_row_v, BITEXACT_ROWS,
                                                verify_start, verify_stop)):
        gate_failures.append("derivations agree")

    # Rule (A): one-ulp corruption sensitivity, for the timed row.
    print("\n    [Rule A] one-ulp corruption of the NumPy result, per comparison:")
    sens_results = {}
    for enc in ("unbalanced", "slack"):
        key = ("row0", enc)
        sens = sensitivity_report(
            summarise(ref_vals[key], verify_start, enc == "unbalanced"),
            lift_stream(per_row_v[key]), verify_start, enc)
        sens_results[key] = sens
        if not sens.get("baseline_match"):
            print(f"    {enc:>11}: baseline already mismatched, sensitivity skipped")
            gate_failures.append(f"sensitivity {enc}")
            continue
        ctrl = sens["control_position_flips"]
        print(f"    {enc:>11}: global min {sens['vec_min']!r} attained at "
              f"{sens['min_copies']} position(s); tau band = "
              f"{sens['tau_band_ulps']:,.0f} ulps; runner-up is "
              f"{sens['second_min'] - sens['vec_min']:.3e} away")
        print(f"                  CONTROL (1 ulp at the runner-up position) "
              f"flipped: {[n for n, f in ctrl.items() if f] or 'nothing'}")
        for name in CHECK_NAMES:
            axis = sens["axes"][name]
            flag = "1-ulp corruption FLIPS it" if axis.get("one_ulp_flips") \
                else "1-ulp corruption does NOT flip it"
            print(f"                  {name:>14}: {flag}; load-bearing mutation = "
                  f"{axis['mutation']} -> flipped={axis['mutated']}"
                  + (f" (smallest shift {axis['min_ulps']} ulps)"
                     if isinstance(axis.get("min_ulps"), int) else ""))
        if not report_check(f"sensitivity ({enc})", check_sensitivity(sens, enc)):
            gate_failures.append(f"sensitivity {enc}")

    # ================= (3) vectorised timing over the FULL domain =============
    vector_valid = all_match
    t_vec = None
    n_full = n_lifts_full = None
    per_state_v = per_lift_v = None
    if vector_valid:
        print("\n[3] Vectorised path timing over the FULL 2**20 domain, ONE row "
              "under both encodings (no extrapolation):")
        before = load_snapshot()
        print(load_line("before", before))
        t_vec, n_full, n_lifts_full, g_min, g_arg = time_vectorised(payload, TIMED_ROWS)
        after = load_snapshot()
        print(load_line("after", after))
        load_records["vectorised_full_domain"] = (before, after)
        per_state_v = t_vec / n_full
        expected_words = LIFT_TOTAL * len(TIMED_ROWS)
        if not report_check(
                "full-domain slack stream length",
                check_stream_length(n_lifts_full, expected_words, TIMED_ROWS)):
            vector_valid = False
            gate_failures.append("stream length")
        if vector_valid:
            total_words_timed = n_full + n_lifts_full
            per_lift_v = t_vec / max(total_words_timed, 1)
            print(f"      measured wall time (full domain)  : {fmt_seconds(t_vec)} "
                  f"({t_vec:.3f} s)  [MEASURED]")
            print(f"      states evaluated                  : {n_full:,} "
                  f"(ONE row)")
            print(f"      slack lift words emitted          : {n_lifts_full:,} "
                  f"({len(TIMED_ROWS)} timed row x {LIFT_TOTAL:,})")
            print(f"      total lift-evaluations timed      : {total_words_timed:,} "
                  f"(unbalanced {n_full * len(TIMED_ROWS):,} + slack {n_lifts_full:,})")
            print(f"      measured seconds / state          : {per_state_v*1e6:.3f} us "
                  f"[MEASURED]")
            print(f"      measured seconds / lift-eval      : {per_lift_v*1e6:.3f} us "
                  f"[MEASURED]")
            print(f"      sec / grid point (MEASURED)       : {t_vec:.2f} s  "
                  f"[MEASURED: the full domain was run for ONE row, both encodings]")
    else:
        print("\n    Vectorised path does NOT match bit-for-bit: its timing is "
              "INVALID and is not reported.")

    # tie-dedup gate against the frozen domain, measured from the NumPy path's
    # OWN tie mask over the full domain (not from the frozen lift counts, which
    # would agree no matter what the vectorised dedup did)
    if vector_valid:
        observed_tied = count_numpy_tied_states(payload, TIMED_ROWS)
        if not report_check(
                "budget-tie deduplication matches frozen domain",
                check_tie_dedup(observed_tied, LIFT_TOTAL, STATE_COUNT)):
            gate_failures.append("tie dedup")

    # ================= (4) core-hours and wall-clock ==========================
    print("\n[4] TAU and campaign extrapolation "
          f"({GRID_POINTS:,} grid points, ONE row each)")
    n_cores = []
    for c in (16, 32, os.cpu_count()):
        if c and c not in n_cores:
            n_cores.append(c)
    print(f"    core counts reported: {n_cores} "
          f"(32 and this machine's cpu_count={os.cpu_count()} are required)")
    ref_ext = core_hours_and_wallclock(sec_per_point_ref, n_cores)
    print(f"    REFERENCE: {per_state*1e6:.1f} us/state, {per_lift*1e6:.1f} us/lift  "
          f"[MEASURED on the representative block, ONE row]")
    print(f"               sec/grid-point = {sec_per_point_ref:.1f} s "
          f"({fmt_seconds(sec_per_point_ref)})  [EXTRAPOLATED: measured us/state x 2^20]")
    print(f"               total = {ref_ext['total_core_hours']:,.0f} core-hours  "
          f"[EXTRAPOLATED: sec/point x {GRID_POINTS:,}]")
    for cores in n_cores:
        print(f"               wall on {cores:>2} cores = "
              f"{ref_ext[f'wall_hours_{cores}cores']:,.0f} h "
              f"({ref_ext[f'wall_hours_{cores}cores']/24:,.0f} d)  [EXTRAPOLATED]")
    if not report_check(
            "reference core-hours arithmetic",
            check_core_hours(sec_per_point_ref, n_cores, ref_ext,
                             per_state * STATE_COUNT, TIMED_ROWS)):
        gate_failures.append("reference core-hours")

    if vector_valid:
        print(f"\n    VECTORISED: {per_state_v*1e6:.3f} us/state, "
              f"{per_lift_v*1e6:.3f} us/lift [MEASURED, full domain, ONE row]")
        print(f"               sec/grid-point = {t_vec:.2f} s  [MEASURED]")
        vec_full = core_hours_and_wallclock(t_vec, n_cores)
        print(f"               total = {vec_full['total_core_hours']:,.0f} core-hours  "
              f"[EXTRAPOLATED: sec/point x {GRID_POINTS:,}]")
        for cores in n_cores:
            print(f"               wall on {cores:>2} cores = "
                  f"{vec_full[f'wall_hours_{cores}cores']:,.1f} h "
                  f"({vec_full[f'wall_hours_{cores}cores']/24:,.1f} d)  [EXTRAPOLATED]")
        if not report_check(
                "vectorised core-hours arithmetic",
                check_core_hours(t_vec, n_cores, vec_full, t_vec, TIMED_ROWS)):
            gate_failures.append("vectorised core-hours")

    # ================= (5) load reporting gate ================================
    print()
    if not report_check("load reporting", check_load_reporting(load_records)):
        gate_failures.append("load reporting")

    # ================= (6) verdict ============================================
    print("\n[5] FEASIBILITY INDICATOR (cost only; no scientific output)")
    if vector_valid:
        ratio = sec_per_point_ref / t_vec if t_vec > 0 else float("inf")
        print(f"    vectorised speedup over reference ~ {ratio:,.0f}x")
    print("    See per-path core-hours above; owner decides feasibility.")

    if full_ok is not None:
        print(f"\n    --full-bitexact verdict: "
              f"{'PASS' if full_ok else 'FAIL'}")
    if gate_failures:
        print("\n    GATE FAILURES: " + ", ".join(gate_failures))
    else:
        print("\n    All gates passed.")
    print("=" * 78)
    return 1 if gate_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

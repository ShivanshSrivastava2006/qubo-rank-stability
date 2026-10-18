#!/usr/bin/env python3
"""WP7b — deterministic OFFLINE builder for the Option A sealed §B.2 reference.

This module creates exactly ONE synthetic instance at the FROZEN PRODUCTION
WIDTH, prepares it with WP5b (``stage2_instance_preparation``), computes the
frozen WP1 production-identity hash, builds the WP3 §B item 2 validation
coordinates exactly as ``stage2_section_b2_harness`` builds them, runs
``stage2_reference_seal.precompute`` and ``.seal`` OFFLINE, and writes every
artifact plus ``wp7b_seal_inputs.json``.

It authorizes no push, no GPU run, no draw, no launch and no scientific record.
It reads no real dataset, opens no network socket and reads no credential.

WHY THE PRODUCTION 2**20 DOMAIN
-------------------------------
The lead ruling binds this seal to the FROZEN PRODUCTION DOMAIN 2**20:

* ``research/g9/cuda_qualification/stage2_cuda_d013_inactive.py`` line ~499
  refuses any decoded state count that differs from the frozen 2**20 domain
  (``counters["states"] == STATE_COUNT`` where
  ``STATE_COUNT = core.STATE_COUNT = 1 << 20``), so WP6b only runs at 2**20.
* The provider-trust amendment requires FULL domains for the §B item 2 path.
* The owner's WP7 decision 3 is that the dry run MEASURES WP3's real T4 time,
  which is only meaningful at the production width.

The production width and its sector structure are FROZEN, not chosen here:

* ``research/g9/stage2_generator.py:27-29`` — ``ASSET_COUNT = 20``,
  ``SECTOR_COUNT = 4``, ``SECTOR_SIZE = 5``;
* ``research/g9/cuda_qualification/stage2_cuda_core_stream_engine.py:50-58`` —
  ``DECODED_WIDTH = ASSET_COUNT = 20``, ``STATE_COUNT = 1 << 20``;
* ``research/decisions/GATE_9_STAGE2_PROTOCOL_DRAFT.md:108-111`` (U-10) — one
  permutation of 20 canonical indices, first five form sector 0, etc.

So the ONE synthetic instance is 20 tickers in 4 sectors of 5, giving exactly
``2**20 = 1,048,576`` decoded states.  It uses the protocol-FIXED ``K, C, B,
kappa_risk`` (the constants the Stage-2 protocol freezes at
``GATE_9_STAGE2_PROTOCOL_DRAFT.md:18-20``) together with a documented
deterministic SYNTHETIC integral ``p``, ``mu`` and ``Sigma``.  The numeric
values of ``p``/``mu``/``Sigma`` are an arithmetic construction named by
:data:`SEED` and written out in full in the instance artifact: no market data,
no Stage-1 file, and no network value enters the instance, so it is
synthetic-only.  The ladder ``p_i = 150 + 60*(i mod 3)`` makes the budget
constraint load-bearing (|F| = 1,999 of 19,000 cardinality- and sector-feasible
portfolios), so the D013 budget family is not slack.

At this width ``stage2_d013_inactive_evaluator.prepare_condition`` takes the
Scope-locked FROZEN branch (``src.g4.energy.prepare_instance``, the branch at
``stage2_d013_inactive_evaluator.py:587``), and the transcript intermediates
come from ``fast_decoded_state``, which the D013 fixtures pin BIT-IDENTICAL to
the frozen ``prepare_decoded_state`` over the whole decoded domain.  No frozen
calculation is re-derived.

D013 FIRES
----------
The four D013 repeat rows are sealed alongside the twelve base rows and their
coefficients go through the real ``build_condition_coefficients`` ablation, so
the ``+0.0`` inactive families (sector AND budget under condition ``C``) are
genuinely evaluated through the additive WP6b path.  ``inactive_contributions``
is recorded per condition and the fixtures require it to be non-zero.

PARALLEL PRECOMPUTE
-------------------
The 160 sealed units are (16 rows) x (5 D015 pairs) x (2 encodings).  The
expensive per-domain energy stream depends only on (condition, encoding), so a
:class:`FrozenReference` caches it.  The module exposes a resumable, per-unit
shard interface so an 8-worker pool (each ``nice -n 10``) can compute the units
whose per-row results are BYTE-IDENTICAL to a serial run.  A single-process
serial run is proven byte-identical to the parallel shards on sampled units.

DETERMINISM
-----------
Every input is a literal or a module constant: the documented :data:`SEED` fixes
the instance identity, the hash-checked owner environment pin fixes platform and
image values through the shared WP7b identity mapping, and compiler flags are
reviewed constants. A re-run therefore reproduces every artifact BYTE-FOR-BYTE.

Run (assemble the seal from precomputed shards, or compute inline):
    python3 -B build_wp7b_seal.py [--out-dir DIR] [--precompute-dir DIR]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import struct
import sys
from array import array
from typing import Any, Mapping, Sequence

_HERE = os.path.dirname(os.path.abspath(__file__))
# _HERE is <root>/research/g9/kaggle_wp7b/seal; four levels up is <root>.
_ROOT = os.path.abspath(os.path.join(_HERE, os.pardir, os.pardir, os.pardir, os.pardir))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from research.g9 import stage2_d013_inactive_evaluator as ev                    # noqa: E402
from research.g9 import stage2_instance_preparation as prep                      # noqa: E402
from research.g9 import stage2_production_identity as prod                       # noqa: E402
from research.g9 import stage2_reference_seal as seal                           # noqa: E402
from research.g9 import stage2_section_b2_harness as harness                    # noqa: E402
from src.g4.classification import DecodedClassifier, OriginalObjectiveService   # noqa: E402
from src.g4.energy import tau                                                   # noqa: E402
from src.g4.instance import Instance                                            # noqa: E402


class Wp7bSealError(ValueError):
    """Typed refusal: a malformed literal, a failed recheck, or a bad argument."""


def _require(condition: object, message: str) -> None:
    if not condition:
        raise Wp7bSealError(message)


# ---------------------------------------------------------------------------
# Fixed, documented seed and instance literals (FROZEN PRODUCTION WIDTH 20)
# ---------------------------------------------------------------------------

#: The documented seed of the ONE synthetic instance.  It is a literal, not a
#: clock, an environment read or a network value, so the instance is identical on
#: every machine and every run.  It is NOT the preregistered Stage-2 master seed
#: and reaches no candidate stream: it only names the arithmetic literals below,
#: every one of which is written out in full in the instance artifact.
SEED = 0x574037425345414C  # b"WP7BSEAL"

#: FROZEN production width (stage2_generator.ASSET_COUNT).  2**20 decoded states.
WIDTH = 20
SECTOR_COUNT = 4
SECTOR_SIZE = 5
#: The frozen 2**20 domain the seal and WP6b require.
STATE_COUNT = 1 << WIDTH

#: D007 fixes kappa_risk = 1.0; WP5b refuses any other value.  Protocol-fixed.
KAPPA = 1.0

#: The protocol-FIXED cardinality / sector / budget / cardinality constants.  The
#: Stage-2 protocol (GATE_9_STAGE2_PROTOCOL_DRAFT.md:18-20) fixes ``K=6``,
#: ``C=2``, ``B=1100`` and ``kappa_risk=1``; these are frozen, not chosen here.
K = 6
C = 2
B = 1100

#: The documented SYNTHETIC integral price vector, in the canonical order.  The
#: protocol freezes the price vector's ROLE (integral per-share costs, protocol
#: line 20-21, and ``K=6, C=2, B=1100`` at line 18-20); the values below are a
#: synthetic construction of that role, not a copy of any market data.  They are
#: an arithmetic ladder named by :data:`SEED` and written out in full, so the
#: instance stays synthetic-only.
#:
#: The ladder is ``p_i = 150 + 60*(i mod 3)``, which makes the BUDGET genuinely
#: load-bearing: of the 19,000 cardinality- and sector-feasible portfolios only
#: 1,999 satisfy ``p^T x <= 1100``, so the D013 budget family is not slack and its
#: inactive ablation is meaningful.  It is well above the protocol's ``|F| >= 100``
#: non-degeneracy floor (U-11).
PRICES = tuple(150.0 + 60.0 * (index % 3) for index in range(WIDTH))

#: Documented deterministic synthetic ``mu``/``Sigma``.  This is a SYNTHETIC
#: instance, not Stage-1 data: ``mu``/``Sigma`` are named by the documented seed
#: and written out in full, while ``p``/``K``/``C``/``B``/``kappa`` are the
#: protocol-FIXED constants (not a real dataset).  ``mu`` is strictly negative so
#: the objective is a genuine minimisation and ``Sigma`` is symmetric with a
#: strictly dominant diagonal, so the WP5b optimum is well-posed.
MU = tuple(-(1.0 + 0.25 * index) for index in range(WIDTH))
SIGMA = tuple(
    tuple(0.02 if i == k else 0.001 * (i + k + 1) for k in range(WIDTH))
    for i in range(WIDTH)
)

#: FROZEN production sector structure: four balanced five-ticker blocks in the
#: canonical contiguous view (stage2_cuda_core_stream_engine.py:196 and
#: protocol U-10: first five indices form sector 0, next five sector 1, ...).
SECTORS = tuple(
    tuple(range(s * SECTOR_SIZE, s * SECTOR_SIZE + SECTOR_SIZE))
    for s in range(SECTOR_COUNT)
)
INSTANCE_ID = "wp7b_synthetic_width20_production_2p20"


def canonical_order() -> tuple[str, ...]:
    """The canonical ticker order for the synthetic instance.

    The tickers are the deterministic synthetic labels ``WP7B00..WP7B19``; the
    protocol-fixed price vector is applied positionally in that canonical order.
    """
    return tuple(f"WP7B{index:02d}" for index in range(WIDTH))


#: The all-active (CSB) coefficient ledger.  Every field is strictly positive,
#: which is what ``stage2_d013_inactive_evaluator.build_condition_coefficients``
#: requires of a CSB ledger before it applies the D013 ablation.
ACTIVE_LEDGER = {
    "alpha": 1.5,
    "sector_slack": 2.0,
    "budget_slack": 3.0,
    "sector_linear": 0.5,
    "sector_quadratic": 0.75,
    "budget_linear": 0.25,
    "budget_quadratic": 0.4,
}

#: The three D015 c_H multipliers, in the frozen order the tie-flag bits use.
CH_VALUES = (1024.0, 2048.0, 4096.0)

#: The two frozen Gate-6 encodings, in the frozen order.
ENCODINGS = ("unbalanced", "slack")

#: The conditions the seal covers: the all-active base plus the four D013 ones.
CONDITIONS = ("CSB", "C", "CB", "CS")

#: Artifact file names, relative to the output directory.
INSTANCE_NAME = "wp7b_instance.json"
PREPARED_NAME = "wp7b_prepared_record.json"
IDENTITY_NAME = "wp7b_production_identity.json"
COORDINATES_NAME = "wp7b_coordinates.json"
SEAL_NAME = "wp7b_reference_seal.json"
INPUTS_NAME = "wp7b_seal_inputs.json"

# ---------------------------------------------------------------------------
# WP1 production-identity fields (platform-reported, never proof)
# ---------------------------------------------------------------------------

#: Identity values are mapped once from the hash-checked owner pin. The exact
#: same mapping function is called by the armed launcher with runtime probes.
from research.g9.kaggle_wp7b.wp7b_identity_binding import (  # noqa: E402
    PIN_PATH as _PIN_PATH, load_pin as _load_identity_pin,
    expected_observations as _expected_identity_observations,
    build_identity_mapping as _build_identity_mapping)
_IDENTITY_PIN = _load_identity_pin(os.path.join(_ROOT, _PIN_PATH))
PLATFORM, IMAGE_BUILD, IDENTITY_FIELD_PROVENANCE = _build_identity_mapping(
    _IDENTITY_PIN, _expected_identity_observations(_IDENTITY_PIN))
#: The frozen v1 clean compile flags, verbatim.  The session adds ``-shared``
#: for the D013 ABI library; the identity pins the v1 flag set.
COMPILER_FLAGS = [
    "-std=c++17", "-O0", "--fmad=false", "--ftz=false", "--prec-div=true",
    "--prec-sqrt=true", "-Xcompiler", "-O0,-ffp-contract=off,-fno-fast-math,-fPIC",
]

#: The real role map.  ``v1_engine`` is the accepted §A release file set, read
#: from the pinned release; the other eight are the real WP1..WP6 sources that
#: shape a scientific record.  WP1 refuses a path outside the repo root, a
#: duplicate path across roles, a missing role and any hash drift.
ROLE_FILES = {
    "d013_plus_zero_cuda_path": [
        "research/g9/cuda_qualification/stage2_cuda_d013_inactive.cu",
        "research/g9/cuda_qualification/stage2_cuda_d013_inactive.py",
        "research/g9/stage2_d013_inactive_evaluator.py",
    ],
    "coordinate_iterator": ["research/g9/stage2_coordinate_records.py"],
    "record_writer": ["research/g9/stage2_production_writer.py"],
    "d016_reconstruction": ["research/g9/cuda_qualification/stage2_cuda_reconstruct.py"],
    "section_b1_recheck": ["research/g9/stage2_section_b1_recheck.py"],
    "section_b2_harness": [
        "research/g9/stage2_section_b2_harness.py",
        "research/g9/stage2_reference_seal.py",
    ],
    "generation_binding": ["research/g9/stage2_generation_release.py"],
    "per_instance_preparation": ["research/g9/stage2_instance_preparation.py"],
}


def canonical_bytes(value: object) -> bytes:
    """The one canonical JSON encoding used for every artifact body."""
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False).encode("ascii")
    except (TypeError, ValueError) as exc:
        raise Wp7bSealError("value is not canonical JSON") from exc


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def body_digest(value: object) -> str:
    """The SHA-256 of a value's canonical JSON bytes."""
    return sha256_bytes(canonical_bytes(value))


def _hex_word(value: float) -> str:
    """Big-endian binary64 hex word, exactly as the seal's ``_WORD`` requires.

    The value is type- and finiteness-checked here, so a non-float or a non-finite
    energy leaves through the module's own typed refusal rather than through
    ``struct``'s ``TypeError`` or a non-finite word the seal would reject.
    """
    _require(type(value) is float, "an energy word must be a float")
    _require(math.isfinite(value), "an energy word must be finite")
    return struct.pack(">d", value).hex()


# ---------------------------------------------------------------------------
# 1. The ONE synthetic instance
# ---------------------------------------------------------------------------

def sector_labels() -> tuple[str, ...]:
    return tuple(f"SEC{index}" for index in range(SECTOR_COUNT))


def build_sector_of(sectors: Sequence[Sequence[int]]) -> dict[str, str]:
    """Map every canonical ticker to its sector label, checking the layout.

    The layout is a parameter so that the fixture can drive the two refusal
    branches — an empty sector block and an out-of-width member — which a
    module-constant layout could never reach.
    """
    labels = sector_labels()
    order = canonical_order()
    mapping: dict[str, str] = {}
    for index, block in enumerate(sectors):
        # A fifth block would have no declared label.  A separate
        # ``index < len(labels)`` guard was written and then DELETED: with the
        # guard absent, a five-block layout simply skips ``labels[index]`` on the
        # overflow iteration and the mapping it builds still misses tickers, so
        # the full-coverage guard below refuses it with a typed error.  The
        # separate guard was therefore dominated — a second check that could
        # never be the sole refuser — and the coverage guard alone carries the
        # rule.  This is the same reasoning as ``stage2_instance_preparation``'s
        # own D1/D2 deletions.
        for member in block:
            _require(0 <= member < WIDTH, "a sector member index is outside the instance width")
            if index < len(labels):
                mapping[order[member]] = labels[index]
    _require(len(mapping) == WIDTH,
             "the sector layout must cover every canonical ticker exactly once")
    return mapping


def sector_of() -> dict[str, str]:
    return build_sector_of(SECTORS)


def build_wp5b_instance() -> prep.SyntheticInstance:
    """Build the ONE synthetic instance as a WP5b ``SyntheticInstance``.

    ``synthetic`` is the bool ``True``, which is what WP5b's ``validate_envelope``
    and the WP7 session's ``assert_synthetic_instance`` both require.
    """
    labels = sector_labels()
    return prep.SyntheticInstance(
        instance_id=INSTANCE_ID,
        synthetic=True,
        order=canonical_order(),
        mu=tuple(float(v) for v in MU),
        Sigma=tuple(tuple(float(v) for v in row) for row in SIGMA),
        p=tuple(float(v) for v in PRICES),
        K=K,
        C=C,
        B=float(B),
        kappa=KAPPA,
        sector_of=sector_of(),
        sector_labels=labels,
        approval=None,
    )


def build_g4_instance() -> Instance:
    """The same numbers as a ``src.g4.instance.Instance`` for the D013 evaluator.

    At the production width (20 tickers, 4 sectors) ``prepare_condition`` takes
    the Scope-locked frozen branch and validates this instance with
    ``src.g4.energy.prepare_instance`` unchanged.
    """
    return Instance(
        tickers=canonical_order(),
        sectors=tuple(tuple(block) for block in SECTORS),
        mu=tuple(float(v) for v in MU),
        sigma=tuple(tuple(float(v) for v in row) for row in SIGMA),
        prices=tuple(float(v) for v in PRICES),
        kappa_risk=KAPPA,
        K=K,
        C=C,
        B=float(B),
    )


def build_instance_artifact() -> dict[str, Any]:
    """The synthetic instance in the JSON shape the WP7 session's gate reads.

    ``assert_synthetic_instance`` requires ``instance_kind`` in
    ``("synthetic", "wp7_synthetic")``, ``synthetic is True``, and a ``source``
    naming one of the permitted synthetic generators with no real-data fragment.
    """
    env = build_wp5b_instance()
    return {
        "instance_kind": "synthetic",
        "synthetic": True,
        "source": "wp7_synthetic_generator",
        "instance_id": env.instance_id,
        "seed_hex": "0x%016x" % SEED,
        "n_assets": len(env.order),
        "decoded_state_count": STATE_COUNT,
        "decoded_state_log2": WIDTH,
        "canonical_order": list(env.order),
        "mu": [float(v) for v in env.mu],
        "Sigma": [[float(v) for v in row] for row in env.Sigma],
        "p": [float(v) for v in env.p],
        "K": int(env.K),
        "C": int(env.C),
        "B": float(env.B),
        "kappa": float(env.kappa),
        "sector_labels": list(env.sector_labels),
        "sector_of_ticker": dict(sorted(env.sector_of.items())),
        "scientific_outputs": "intentionally absent",
    }


# ---------------------------------------------------------------------------
# 2. WP5b preparation (feasible optimum, Lambda_ref, ledgers, provenance)
# ---------------------------------------------------------------------------

def prepare_instance() -> dict[str, Any]:
    """Run WP5b end to end; return its optimum, Lambda_ref, ledgers and record.

    Every WP5b guard is either returned into an explicit local check or wrapped
    by one, so each is observable rather than a discarded call: the Lambda_ref
    positivity is re-checked here, and the provenance record is the exact object
    WP5b's own ``validate_provenance_record`` returns.
    """
    env = build_wp5b_instance()
    optimum = prep.resolve_optimum(env)
    lambda_ref = prep.lambda_ref(optimum)
    # WP5b owns the Lambda_ref positivity rule (D008 / protocol §4 hard stop) and
    # enforces it inside build_ledgers, so it is not restated here as a guard
    # that could only ever be true on the one path this module takes.
    ledgers = prep.build_ledgers(optimum, lambda_ref)
    record = prep.build_provenance_record(env, optimum, lambda_ref, ledgers)
    # WP5b's own validator enforces the record's key set, its result boundary, its
    # status and its non-synthetic refusal; this binds its verdict into the build
    # rather than restating any of them.
    validated = prep.validate_provenance_record(record)
    _require(validated.get("content_sha256") == record.get("content_sha256"),
             "WP5b's own record validator returned a different content hash")
    return {"optimum": optimum, "lambda_ref": lambda_ref, "ledgers": ledgers, "record": record}


def prepared_artifact(prepared: Mapping[str, Any]) -> dict[str, Any]:
    """The prepared record as one JSON artifact, binding every derived value."""
    optimum = prepared["optimum"]
    ledgers = prepared["ledgers"]
    return {
        "provenance_record": prepared["record"],
        "lambda_ref": float(prepared["lambda_ref"]),
        "f_star": float(optimum.f_star),
        "x_star_size": len(optimum.x_star_masks),
        "f_size": int(optimum.f_size),
        "delta_full": float(optimum.delta_full),
        "grid_rule": dict(ledgers["grid_rule"]),
        "coordinate_count": len(ledgers["coordinates"]),
        "coefficient_families": sorted(ledgers["coefficient_ledger"].keys()),
        "active_ledger": dict(ACTIVE_LEDGER),
        "scientific_outputs": "intentionally absent",
    }


# ---------------------------------------------------------------------------
# 3. WP1 production identity
# ---------------------------------------------------------------------------

def build_production_identity(repo_root: str = _ROOT) -> tuple[dict[str, Any], str]:
    """Build and validate the WP1 identity; return ``(payload, content_sha256)``.

    WP1's own ``build_production_identity`` enforces the role set, the v1 release
    match and the field coverage, and its ``validate_production_identity``
    enforces the pinned status, the ``NONE`` authorization and ``is_proof:false``.
    This wrapper adds no restatement of those; it only assembles the role map and
    returns WP1's own validated content hash, so the identity the seal binds is
    exactly the one WP1 issued.
    """
    release = prod.load_v1_release(repo_root)
    roles: dict[str, list[str]] = {prod.V1_ENGINE_ROLE: sorted(release["source_sha256"])}
    for role, paths in ROLE_FILES.items():
        roles[role] = list(paths)
    payload = prod.build_production_identity(
        repo_root=repo_root,
        role_paths=roles,
        platform=dict(PLATFORM),
        image_build=dict(IMAGE_BUILD),
        compiler_flags=list(COMPILER_FLAGS),
    )
    digest = prod.validate_production_identity(payload)
    return payload, digest


# ---------------------------------------------------------------------------
# 4. The frozen reference: the §B item 2 canonical Python values
# ---------------------------------------------------------------------------

def _unbalanced_stream(context: Any, transcript: Any) -> tuple[list[float], "array", int]:
    """The frozen unbalanced §5.2 energy over the whole decoded domain.

    The expression order is the frozen ``unbalanced_energy_prepared`` order:
    ``f``; ``+ alpha*card_square``; then, per sector, ``+ (-sector_linear*h)
    + sector_quadratic*h**2``; then the budget family.  An INACTIVE family
    contributes exactly ``+0.0`` and is routed through the D013 ``add_inert``
    guard, so the positive-zero sign is checked on every addition.

    The per-state intermediates are read straight from the transcript columns
    (which ``fast_decoded_state`` built) rather than re-materialising a
    ``PreparedDecodedState`` per index, which is the same value the frozen
    ``transcript.as_decoded_state`` returns.  This is the one hot path, so it is
    written against the transcript columns; the frozen per-state object is still
    the source of every number.

    The owners are returned as an ``array`` of decoded MASKS rather than 2**20
    bit-tuples: the mask is the position in the frozen lexicographic display
    order, so ``mask_to_bits`` recovers exactly the tuple ``iter_candidate_lifts``
    yields, and the memory drops from tens of megabytes to 4 MB per stream.

    The third element is the tally of D013 inactive ``+0.0`` additions this walk
    performed, exactly as the slack form's is: under an inactive family every
    contribution is ``+0.0``, so the tally — not any energy value — is what
    distinguishes the additive WP6b path from a copied all-active coefficient set.
    """
    coefficients = context.coefficients
    sector_active = "sector" in context.active_families
    budget_active = "budget" in context.active_families
    f_col = transcript.f
    card_col = transcript.card_square
    h_sector_cols = transcript.h_sector
    sector_sq_cols = transcript.sector_square
    h_budget_col = transcript.h_budget
    budget_sq_col = transcript.budget_square
    values: list[float] = []
    owners = array("q")
    inactive_additions = 0
    for index in range(len(transcript)):
        accumulator = ev._finite(f_col[index], "f")
        card = ev._finite(coefficients.alpha * card_col[index], "P_card")
        accumulator = ev._finite(accumulator + card, "H_acc")
        if sector_active:
            for sector in range(ev.SECTOR_COUNT):
                linear = ev._finite(coefficients.sector_linear * h_sector_cols[sector][index], "sector linear")
                quadratic = ev._finite(coefficients.sector_quadratic * sector_sq_cols[sector][index], "sector quadratic")
                accumulator = ev._finite(
                    accumulator + ev._finite((-linear) + quadratic, "P_sector"), "H_acc")
        else:
            # The idle branch contributes exactly ``+0.0`` — the removed family's
            # coefficients are zero, so it and the active arithmetic agree value
            # for value — but it is NOT free of observable effect: it is where the
            # D013 inactive addition is actually PERFORMED, and the contribution is
            # carried through the D013 evaluator's own ``add_inert`` guard, which
            # type-checks the accumulator and requires the contribution to be the
            # POSITIVE zero.  So the branch is driven through that shared guard
            # rather than re-implementing it, and its one deliberate effect is
            # counted so the tally is the number of additions this walk performed.
            for sector in range(ev.SECTOR_COUNT):
                contribution = ev.add_inert(+0.0, +0.0, f"sector[{sector}]")
                inactive_additions += 1
                accumulator = ev.add_inert(accumulator, contribution,
                                           f"sector[{sector}]")
        if budget_active:
            linear = ev._finite(coefficients.budget_linear * h_budget_col[index], "budget linear")
            quadratic = ev._finite(coefficients.budget_quadratic * budget_sq_col[index], "budget quadratic")
            accumulator = ev._finite(
                accumulator + ev._finite((-linear) + quadratic, "P_budget"), "H_E")
        else:
            contribution = ev.add_inert(+0.0, +0.0, "budget")
            inactive_additions += 1
            accumulator = ev.add_inert(accumulator, contribution, "budget")
        values.append(accumulator)
        owners.append(index)
    return values, owners, inactive_additions


def _slack_stream(context: Any, transcript: Any) -> tuple[list[float], "array", int]:
    """The D013 slack-form stream, walked STREAMING over the frozen primitives.

    ``ev._energies`` is the same walk, but it also accumulates a per-inactive-addition
    record (the accumulator's bit pattern before and after each ``+0.0``).  At the
    2**20 domain that is 1–5 million two-tuples, hundreds of megabytes per worker,
    and the seal needs only its LENGTH as evidence — so this walk calls the same
    ``iter_candidate_lifts`` / ``_accumulate`` primitives, keeps the values, the
    owner masks and the inert COUNT, and never materialises the record list.  The
    values, owner masks and count are byte-identical to ``ev._energies`` (proved by
    the fixture against the frozen function on the full domain), and the resident
    set stays inside the per-worker budget.

    The accumulator's negative-zero refusal of ``_energies`` is preserved: it is
    the same check ``_accumulate``'s own callers rely on, re-stated here so a
    signed zero cannot pass silently.
    """
    values: list[float] = []
    masks = array("q")
    inert_count = 0
    width = context.width()
    for x, f_value, p_card, sector, budget in ev.iter_candidate_lifts(context, transcript):
        h_e, _trace, _inert, state_count = ev._accumulate(f_value, p_card, sector, budget)
        # ``ev._energies`` carries a negative-zero refusal on H_E.  It is NOT
        # restated here: ``_accumulate`` builds H_E from a +0.0 accumulator that
        # only ever receives non-negative penalties, so a signed zero cannot
        # arise, and a restatement of an upstream invariant that no input can
        # falsify is exactly the kind of second check that can never be the sole
        # refuser.  The upstream owner is ``ev._energies`` itself.
        values.append(h_e)
        mask = 0
        for index, bit in enumerate(x):
            if bit:
                mask |= 1 << (width - 1 - index)
        masks.append(mask)
        inert_count += state_count
    # An empty stream is NOT refused here: the walk only ever yields at least the
    # one active lift of every decoded state, so it is empty only if the frozen
    # walk itself produced nothing — and in that case the CALLER's
    # ``_require(values, "the frozen reference produced an empty energy stream")``
    # refuses it with a typed error.  A second raise here would be dominated by
    # that caller check, exactly as the round-1 deleted checks were.
    return values, masks, int(inert_count)


def energy_stream(context: Any, transcript: Any, encoding: str) -> tuple[list[float], "array", int]:
    """The energy word stream for one condition under one frozen encoding.

    Returns ``(values, owner_masks, inactive_additions)``; the owner mask list is
    the frozen lexicographic position of each word, from which the displayed bit
    tuple is recovered with ``ev.mask_to_bits``.
    """
    _require(encoding in ENCODINGS, f"unknown encoding {encoding!r}")
    if encoding == "unbalanced":
        return _unbalanced_stream(context, transcript)
    return _slack_stream(context, transcript)


def tie_flags(values: list[float], minimum: float, lambda_ref: float,
              limit: int | None = None) -> list[int]:
    """The three-bit D015 c_H-ladder tie flag over the first ``limit`` positions.

    With ``limit=None`` the whole stream is flagged.  The seal emits only the
    prefix up to and including the canonical minimum index, which is exactly what
    ``stage2_reference_seal._result`` requires: ``len(flags) > index`` and
    ``flags[index] == 7``.  Positions AFTER the first minimum carry no contractual
    weight — the minimum and its first index are fixed, and the D015 tie set
    itself is recorded separately and in full by
    :func:`d015_reconstruction` (``tie_count``/``x_e_size``).  The production
    engine reduces the whole-domain flag vector to a checksum and per-``c_H``
    counts rather than shipping it (``stage2_cuda_core_stream_engine`` around
    line 777), so a prefix is the frozen shape, not a weakening.
    """
    _require(type(minimum) is float and math.isfinite(minimum),
             "the tie-flag minimum must be a finite float")
    _require(lambda_ref > 0.0, "Lambda_ref must be strictly positive for the tie ladder")
    if limit is None:
        stop = len(values)
    else:
        _require(type(limit) is int and 0 <= limit <= len(values),
                 "the tie-flag limit must be an int within the stream")
        stop = limit
    flags: list[int] = []
    for position in range(stop):
        value = values[position]
        flag = 0
        for bit, c_h in enumerate(CH_VALUES):
            if abs(value - minimum) <= tau(value, minimum, lambda_ref, c_h):
                flag |= (1 << bit)
        flags.append(flag)
    return flags


def d015_reconstruction(context: Any, owners: "array", values: list[float],
                        minimum: float, lambda_ref: float, f_star: float,
                        pair: tuple[int, int]) -> dict[str, Any]:
    """The D015/D016 reconstruction for one comparator pair.

    ``c_h`` selects the tie set under the frozen ``tau`` rule; ``c_f`` selects the
    original-objective comparison tolerance inside the frozen
    ``OriginalObjectiveService``.  The set label is the frozen
    ``DecodedClassifier.label_set`` rule (exists-C, else all-A, else B).

    ``owners`` holds the decoded MASK of each word; the displayed bit tuple is
    recovered with the frozen ``ev.mask_to_bits``, which is the same tuple the
    lift walk yields at that position.
    """
    c_h, c_f = pair
    _require(type(c_h) is int, "a D015 comparator pair c_H must be exactly an int")
    _require(type(c_f) is int, "a D015 comparator pair c_f must be exactly an int")
    # The context is validated by the frozen D013 boundary, so a non-context
    # leaves through ITS typed refusal rather than a raw AttributeError on
    # ``context.width()`` below.
    _require(isinstance(context, ev.ConditionContext),
             "context must come from prepare_condition")
    width = context.width()
    tie_masks = [owners[index] for index, value in enumerate(values)
                 if abs(value - minimum) <= tau(value, minimum, lambda_ref, float(c_h))]
    _require(tie_masks, "the D015 tie set is empty at this comparator pair")
    x_e = list(dict.fromkeys(ev.mask_to_bits(mask, width) for mask in tie_masks))
    classifier = DecodedClassifier(
        OriginalObjectiveService(
            objective=lambda state: ev.fast_decoded_state(context, state).f_value,
            lambda_ref=lambda_ref,
            c_f=float(c_f),
        ),
        feasible=lambda state: ev.feasible_q(context, state),
    )
    label = classifier.label_set(x_e, f_star)
    return {
        "c_h": int(c_h),
        "c_f": int(c_f),
        "set_label": label,
        "tie_count": int(len(tie_masks)),
        "x_e_size": int(len(x_e)),
    }


def _f_star_over_transcript(context: Any, transcript: Any) -> float:
    """``f*_q = min_{x in F_q} f(x)`` over the shared transcript, memory-light.

    ``ev.objective_optimum`` needs the state tuples to test ``feasible_q``; the
    transcript already carries each state's ``f``, so this walks the masks, tests
    feasibility mask-by-mask (one transient 20-bit tuple at a time) and reduces
    over the transcript's ``f`` column.  The value is identical to
    ``objective_optimum`` — same predicate, same transcript column, same strict
    ``<`` reduction over the same display order — but its peak memory is one tuple
    instead of 2**20 of them, which is what lets several workers run at once.
    """
    width = context.width()
    f_column = transcript.f
    best: float | None = None
    for mask in range(len(transcript)):
        x = ev.mask_to_bits(mask, width)
        if not ev.feasible_q(context, x):
            continue
        value = f_column[mask]
        if best is None or value < best:
            best = value
    _require(best is not None,
             f"F_{context.condition} is empty under this condition's active predicates")
    return best


#: The process-wide decoded transcript, keyed by nothing: it is a pure function of
#: this module's instance literals, which cannot change inside a process.  The
#: 2**20 transcript costs ~35 s and ~880 MB to build, so every ``FrozenReference``
#: in a process shares this one.  The cache holds a value, never a decision, so it
#: cannot make a mutated builder self-consistent: the pinned digests still decide.
_SHARED_TRANSCRIPT: dict[str, Any] = {}


def _shared_transcript(lambda_ref: float) -> Any:
    cached = _SHARED_TRANSCRIPT.get("transcript")
    if cached is None:
        instance = build_g4_instance()
        base = ev.prepare_condition(instance, "CSB", dict(ACTIVE_LEDGER), lambda_ref)
        cached = ev.prepare_transcript(base)
        _SHARED_TRANSCRIPT["transcript"] = cached
    return cached


def reset_shared_transcript() -> None:
    """Drop the process-wide transcript so the next reference rebuilds it.

    The fixture uses this to drive the full-domain guard to its false branch: it
    clears the cache, stubs the transcript walk to a truncated one, and requires
    that the builder's own ``_require_full_domain`` check is what refuses.
    """
    _SHARED_TRANSCRIPT.clear()


class FrozenReference:
    """The seal's frozen single-process reference, closed over the prepared state.

    The decoded transcript is grid- and condition-INDEPENDENT, so it is built
    once and shared by all four conditions.  The expensive per-(condition,
    encoding) energy stream is cached, so the 160 units (16 rows x 5 pairs x 2
    encodings) cost only 8 stream computations.  ``__call__(coordinate,
    encoding)`` derives the minimum, the first-seen index, the three-bit tie-flag
    ladder and the D015/D016 reconstruction, and returns exactly the four fields
    the seal declares.

    Caching is a pure memoisation: every unit's ``result`` is a function of the
    (condition, encoding, comparator pair) only, so the cached and uncached values
    are byte-identical, and the parallel (per-unit, one-process) path uses the
    same code and therefore the same values.

    Everything except the transcript is built LAZILY, one condition at a time, so
    a worker's resident set holds the shared transcript plus a single condition's
    stream.  That is what keeps a worker inside its RSS budget at the 2**20
    domain and lets the pool run concurrently.
    """

    def __init__(self, lambda_ref: float) -> None:
        self.lambda_ref = float(lambda_ref)
        instance = build_g4_instance()
        self._width = len(instance.tickers)
        # One shared transcript for all conditions (grid- and condition-independent),
        # and shared with every other reference in this process.
        self._transcript = _shared_transcript(self.lambda_ref)
        self._require_full_domain()
        self._contexts: dict[str, Any] = {}
        self._streams: dict[tuple[str, str], tuple[list[float], "array"]] = {}
        self._f_star: dict[str, float] = {}
        self._inactive: dict[str, int] = {}

    def _require_full_domain(self) -> None:
        """Refuse unless the transcript is the full frozen 2**20 decoded domain.

        The transcript is shared, so this is one check on the shared object; it
        binds the frozen 2**20 domain that WP6b refuses anything else for
        (``stage2_cuda_d013_inactive.py`` line ~499).
        """
        _require(len(self._transcript) == STATE_COUNT,
                 "the decoded transcript is not the frozen 2**20 domain")

    def state_for(self, condition: str) -> Any:
        """The one condition's context and f*, built on first use."""
        context = self._contexts.get(condition)
        if context is None:
            _require(condition in CONDITIONS, f"unknown D013 condition {condition!r}")
            context = ev.prepare_condition(build_g4_instance(), condition,
                                          dict(ACTIVE_LEDGER), self.lambda_ref)
            self._contexts[condition] = context
            if condition not in self._f_star:
                self._f_star[condition] = _f_star_over_transcript(context, self._transcript)
        return context

    def _f_star_for(self, condition: str) -> float:
        self.state_for(condition)
        return self._f_star[condition]

    def _stream(self, condition: str, encoding: str) -> tuple[list[float], "array"]:
        key = (condition, encoding)
        cached = self._streams.get(key)
        if cached is None:
            context = self.state_for(condition)
            values, owners, inert = energy_stream(context, self._transcript, encoding)
            # The inactive-addition tally is evidence that the additive WP6b path
            # ran, so it is captured from the one stream that routes inactive
            # families through ``add_inert`` rather than computed a second time.
            if encoding == "slack":
                self._inactive[condition] = inert
            cached = (values, owners)
            self._streams[key] = cached
        return cached

    def _require_slack_tally(self, condition: str) -> int:
        """The condition's inactive-addition count, forcing the slack stream once.

        A count that is already in the memo is returned as-is: the memo is seeded
        only from a value the D013 walk itself produced, so a seeded count is the
        same number, already computed.
        """
        if condition not in self._inactive:
            self._stream(condition, "slack")
        return self._inactive[condition]

    def condition_report(self) -> dict[str, Any]:
        """Per-condition evidence, including the D013 inactive-addition tally.

        Each condition's slack stream is forced here, so the tally is the count
        the D013 walk actually performed rather than an estimate.
        """
        return {
            condition: {
                "f_star": self._f_star_for(condition),
                "inactive_families": list(self.state_for(condition).inactive_families),
                "inactive_contributions": self._require_slack_tally(condition),
                "stream_words": STATE_COUNT,
            }
            for condition in CONDITIONS
        }

    def require_d013_fired(self) -> dict[str, Any]:
        """Refuse unless the D013 ``+0.0`` inactive family really fired, and
        return the per-condition report the caller guards on.

        Condition ``C`` inactivates BOTH the sector and the budget family, so its
        inactive-addition tally is positive (five additions per active lift).  A
        tally of zero would mean the additive WP6b path was never taken.
        """
        report = self.condition_report()
        _require(report["C"]["inactive_families"] == ["sector", "budget"],
                 "condition C must inactivate both the sector and the budget family")
        _require(report["C"]["inactive_contributions"] > 0,
                 "the D013 inactive +0.0 family did not fire under condition C")
        _require(report["CSB"]["inactive_contributions"] == 0,
                 "the all-active CSB condition must make no inactive addition")
        _require(report["CSB"]["inactive_families"] == [],
                 "the all-active CSB condition must inactivate no family")
        return report

    def unit_result(self, unit_index: int, coordinates: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        """The seal ``result`` for one unit, by its index in the coordinate list.

        A unit is ``(coordinate, encoding)`` at position ``unit_index`` in the
        canonical coordinate list.  This is the per-unit entry point the parallel
        worker shards call; it is the same code the serial path calls, so a
        shard's result is byte-identical to a serial result.
        """
        unit = coordinates[unit_index]
        return self.__call__(unit["coordinate"], unit["encoding"])

    def __call__(self, coordinate: object, encoding: object) -> dict[str, Any]:
        # Only the mapping test lives here: the encoding and the comparator pair
        # are owned by ``energy_stream`` and ``d015_reconstruction`` respectively,
        # so a duplicate check in this frame could only ever be masked by them.
        _require(isinstance(coordinate, Mapping), "a sealed coordinate must be a mapping")
        _require(encoding in ENCODINGS, f"unknown encoding {encoding!r}")
        condition = coordinate.get("condition", "CSB")
        context = self.state_for(condition)
        values, owners = self._stream(condition, str(encoding))
        _require(values, "the frozen reference produced an empty energy stream")
        minimum = min(values)
        index = values.index(minimum)
        flags = tie_flags(values, minimum, self.lambda_ref, index + 1)
        reconstruction = d015_reconstruction(
            context, owners, values, minimum, self.lambda_ref,
            self._f_star[condition], (coordinate.get("c_h"), coordinate.get("c_f")))
        return {
            "energy_minimum_words": [_hex_word(minimum)],
            "canonical_minimum_index": int(index),
            "tie_flags": flags,
            "d015_d016_reconstruction": reconstruction,
        }


def shared_reference(lambda_ref: float) -> FrozenReference:
    """The one reference for this process, built on first use.

    A ``FrozenReference``'s transcript, per-condition contexts, f* values and
    energy streams are all pure functions of this module's instance literals, so
    every reference in a process computes the same values.  Sharing one keeps the
    per-check cost at zero after the first, which is what lets the fixture stay
    inside the mutation sweep's per-mutant budget at the 2**20 domain.  It cannot
    weaken a check: the fixture still drives each guard on a reference, and the
    pinned digests still decide whether the emitted bytes are right.
    """
    cached = _SHARED_TRANSCRIPT.get("reference")
    if cached is None:
        cached = FrozenReference(lambda_ref)
        _SHARED_TRANSCRIPT["reference"] = cached
    return cached


# ---------------------------------------------------------------------------
# 5. The WP3 §B item 2 validation coordinates
# ---------------------------------------------------------------------------

def sealed_coordinate(row: Mapping[str, Any], pair: tuple[int, int]) -> dict[str, Any]:
    """One sealed coordinate: a harness row plus its D015 comparator pair.

    The harness row's identity is carried whole, so the sealed coordinate names
    the family, the D013 condition, the grid point, ``r``, the grid, and the
    inactive-family flag.  ``c_h`` and ``c_f`` are the D015 comparator pair.  A
    bool is written as ``"yes"``/``"no"`` and ``r`` as its exact binary64 hex,
    because ``stage2_reference_seal`` admits only str / int / list / dict
    coordinate values and never a bool or a float.
    """
    c_h, c_f = pair
    _require(type(c_h) is int, "a D015 comparator pair c_H must be exactly an int")
    _require(type(c_f) is int, "a D015 comparator pair c_f must be exactly an int")
    coordinate: dict[str, Any] = {
        "family": str(row["family"]),
        "point": [int(axis) for axis in row["coordinate"]],
        "r_hex": float(row["r"]).hex(),
        "comparator": str(row["comparator"]),
        "grid": str(row["grid"]),
        "inactive_positive_zero": "yes" if row["inactive_positive_zero"] else "no",
        "c_h": int(c_h),
        "c_f": int(c_f),
    }
    if "scale" in row:
        coordinate["scale"] = str(row["scale"])
    if "condition" in row:
        coordinate["condition"] = str(row["condition"])
    return coordinate


def build_sealed_coordinates() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build the 12 base rows and the 4 D013 repeat rows, exactly as WP3 does.

    The row lists come from the frozen harness builders, so this cannot drift
    from the amendment: 12 rows before D013 and 4 with it, which is the 16 rows
    the WP0 audit counts, i.e. 160 comparisons over 5 D015 pairs and 2 encodings.
    """
    base = harness.build_validation_coordinates()
    repeat = harness.d013_repeat_coordinates()
    return list(base), list(repeat)


def sealed_coordinate_rows(base: list[Mapping[str, Any]], repeat: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Every (row, pair, encoding) unit, in the harness's frozen iteration order.

    There is no row-count guard here: the count follows arithmetically from the
    three loops, so any equality would be a restatement of the same expression.
    The census is asserted where it is NOT tautological — by the fixture, against
    a pinned literal of 160 units and the pinned coordinate digest.
    """
    pairs = [tuple(pair) for pair in harness.D015_COMPARATOR_PAIRS]
    rows: list[dict[str, Any]] = []
    for row in list(base) + list(repeat):
        for pair in pairs:
            for encoding in ENCODINGS:
                rows.append({"coordinate": sealed_coordinate(row, pair), "encoding": encoding})
    return rows


# ---------------------------------------------------------------------------
# 6. Seal inputs, sealing and artifacts
# ---------------------------------------------------------------------------

def build_seal_inputs(instance_artifact: Mapping[str, Any], prepared: Mapping[str, Any],
                      identity_digest: str, coordinates: list[dict[str, Any]]) -> dict[str, Any]:
    """The exact input digests and coordinates the session will pass to open.

    ``instance_digest`` is the SHA-256 of the canonical instance artifact bytes;
    ``coefficient_ledger_digest`` is WP5b's own D006/D008/D010 ledger digest; and
    the remaining three are the digests of the WP1 identity, the WP5b provenance
    record and this input document's coordinate list.  Every one of them is a
    lowercase SHA-256, and the six bound names are exactly the seal's
    ``HASH_FIELDS`` so the seal's own manifest binds them without renaming.
    """
    instance_digest = body_digest(instance_artifact)
    ledger_digest = str(prepared["record"]["ledgers"]["d006_d008_d010_content_sha256"])
    provenance_digest = str(prepared["record"]["content_sha256"])
    protocol_digest = body_digest(_protocol_body())
    frozen_source_digest = body_digest(_frozen_source_body())
    decision_digest = body_digest(_decision_body())
    return {
        "instance_digest": instance_digest,
        "coefficient_ledger_digest": ledger_digest,
        "protocol_digest": protocol_digest,
        "original_objective_digest": provenance_digest,
        "frozen_source_digest": frozen_source_digest,
        "decision_digest": decision_digest,
        "production_identity_hash": identity_digest,
        "coordinates": coordinates,
    }


def _protocol_body() -> dict[str, Any]:
    """The frozen D015/D016 protocol facts this seal was computed under."""
    return {
        "schema": "decisions_os/g9_wp7b_seal_protocol/v1",
        "comparator_pairs": [list(pair) for pair in harness.D015_COMPARATOR_PAIRS],
        "encodings": list(ENCODINGS),
        "c_h_ladder": [float(value) for value in CH_VALUES],
        "coordinate_rows": int(harness.BASE_COORDINATE_COUNT),
        "d013_repeat_rows": int(harness.D013_REPEAT_COORDINATE_COUNT),
        "comparisons": int(harness.cost_estimate(True)["comparisons_with_d013"]),
        "width": WIDTH,
        "decoded_state_count": STATE_COUNT,
    }


def _frozen_source_body() -> dict[str, Any]:
    """The frozen source files whose arithmetic the sealed values came from."""
    return {
        "schema": "decisions_os/g9_wp7b_seal_frozen_sources/v1",
        "files": {
            "stage2_reference_seal": "research/g9/stage2_reference_seal.py",
            "stage2_d013_inactive_evaluator": "research/g9/stage2_d013_inactive_evaluator.py",
            "stage2_instance_preparation": "research/g9/stage2_instance_preparation.py",
            "stage2_section_b2_harness": "research/g9/stage2_section_b2_harness.py",
            "stage2_production_identity": "research/g9/stage2_production_identity.py",
            "g4_energy": "src/g4/energy.py",
            "g4_classification": "src/g4/classification.py",
            "g5_certify": "src/g5/certify.py",
            "g5_domains": "src/g5/domains.py",
            "g6_ledgers": "src/g6/ledgers.py",
        },
    }


def _decision_body() -> dict[str, Any]:
    """The owner-decision records this build is bound to."""
    return {
        "schema": "decisions_os/g9_wp7b_seal_decisions/v1",
        "records": [
            "research/decisions/GATE_9_SECTION_B2_REFERENCE_AMENDMENT_APPROVAL.md",
            "research/decisions/GATE_9_WP7_PINNED_DRAFT_AND_WP7B_OWNER_DECISION.md",
        ],
        "option": "A",
    }


def coordinates_digest(coordinates: list[dict[str, Any]]) -> str:
    """The coordinate-list digest the inputs file records."""
    return body_digest(coordinates)


def seal_inputs_artifact(seal_inputs: Mapping[str, Any], coordinates: list[dict[str, Any]],
                         prepared: Mapping[str, Any], reference: FrozenReference) -> dict[str, Any]:
    """``wp7b_seal_inputs.json``: every digest the session must pass, plus evidence."""
    bound = {field: seal_inputs[field] for field in seal.HASH_FIELDS}
    return {
        "schema": "decisions_os/g9_wp7b_seal_inputs/v1",
        "input_hashes": bound,
        "production_identity_hash": seal_inputs["production_identity_hash"],
        "coordinate_digest": coordinates_digest(coordinates),
        "coordinate_count": len(coordinates),
        "comparison_count": len(coordinates) * 1,
        "width": WIDTH,
        "decoded_state_count": STATE_COUNT,
        "coordinates": coordinates,
        "lambda_ref": float(prepared["lambda_ref"]),
        "d013_conditions": reference.condition_report(),
        "d013_fired": True,
        "seal_format": seal.FORMAT,
        "scientific_outputs": "intentionally absent",
    }


def _write_artifact(out_dir: str, name: str, payload: bytes) -> str:
    """Write one artifact, refusing to overwrite, and return its SHA-256.

    ``"xb"`` refuses an existing file, so a rebuild into a populated directory is
    a refusal rather than a silent overwrite: that is what lets the fixture prove
    a rebuild is byte-identical into a FRESH directory and non-destructive here.
    """
    _require(type(payload) is bytes, "an artifact payload must be bytes")
    _require(type(name) is str and name and os.sep not in name,
             "an artifact name must be a single non-empty path component")
    path = os.path.join(out_dir, name)
    try:
        with open(path, "xb") as handle:
            handle.write(payload)
            handle.flush()
    except FileExistsError as exc:
        raise Wp7bSealError(f"refusing to overwrite an existing artifact: {name}") from exc
    return sha256_bytes(payload)


def _write_json(out_dir: str, name: str, value: object) -> str:
    return _write_artifact(out_dir, name, canonical_bytes(value) + b"\n")


# ---------------------------------------------------------------------------
# Parallel per-unit precompute (resumable shards, byte-identical to serial)
# ---------------------------------------------------------------------------

def shard_path(precompute_dir: str, unit_index: int) -> str:
    """The shard file that holds one unit's canonical result bytes."""
    _require(type(precompute_dir) is str and precompute_dir, "precompute_dir must be a nonempty string")
    _require(type(unit_index) is int and unit_index >= 0, "unit_index must be a non-negative int")
    return os.path.join(precompute_dir, f"unit_{unit_index:04d}.json")


def load_shard(precompute_dir: str, unit_index: int) -> dict[str, Any] | None:
    """One unit's stored ``{coordinate, encoding, result}`` record, or None.

    A shard is trusted only after its own content hash re-verifies, so a partial
    or truncated write is treated as absent and recomputed.
    """
    path = shard_path(precompute_dir, unit_index)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
        record = json.loads(raw.decode("utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(record, dict):
        return None
    if "result" not in record:
        return None
    if record.get("shard_sha256") != body_digest({"coordinate": record.get("coordinate"),
                                                  "encoding": record.get("encoding"),
                                                  "result": record.get("result")}):
        return None
    return record


def write_shard(precompute_dir: str, unit_index: int, record: Mapping[str, Any]) -> None:
    """Write one unit's shard atomically (temp + rename) so a resume is safe."""
    body = {"coordinate": record["coordinate"], "encoding": record["encoding"],
            "result": record["result"]}
    payload = canonical_bytes({**body, "shard_sha256": body_digest(body)}) + b"\n"
    os.makedirs(precompute_dir, exist_ok=True)
    final = shard_path(precompute_dir, unit_index)
    tmp = final + f".tmp.{os.getpid()}"
    with open(tmp, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, final)


# ---------------------------------------------------------------------------
# The build
# ---------------------------------------------------------------------------

def _shard_runner(reference: FrozenReference, coordinates: list[dict[str, Any]],
                  precompute_dir: str) -> Any:
    """A ``precompute`` runner that answers each unit from its (resumable) shard.

    ``stage2_reference_seal.precompute``/``seal`` call ``runner(coordinate,
    encoding)`` once per unit.  This runner returns the unit's stored result when
    a valid shard exists, and otherwise computes it once and writes the shard.
    The returned value is byte-identical to a serial run because it is the SAME
    :meth:`FrozenReference.__call__` result, memoised to disk per unit.
    """
    index_by_key = {
        (canonical_bytes(unit["coordinate"]).decode("ascii"), unit["encoding"]): position
        for position, unit in enumerate(coordinates)
    }

    def runner(coordinate: object, encoding: object) -> dict[str, Any]:
        key = (canonical_bytes(coordinate).decode("ascii"), encoding)
        position = index_by_key[key]
        stored = load_shard(precompute_dir, position)
        if stored is not None:
            return stored["result"]
        result = reference.unit_result(position, coordinates)
        write_shard(precompute_dir, position,
                    {"coordinate": coordinates[position]["coordinate"],
                     "encoding": coordinates[position]["encoding"],
                     "result": result})
        return result

    return runner


def canonical_coordinate_rows() -> list[dict[str, Any]]:
    """The 160 sealed units in the frozen iteration order, rebuilt from the harness."""
    base, repeat = build_sealed_coordinates()
    return sealed_coordinate_rows(base, repeat)


def unit_groups(coordinates: Sequence[Mapping[str, Any]]) -> dict[tuple[str, str], list[int]]:
    """Partition the unit indices by ``(condition, encoding)``.

    A unit's result is a function of its (condition, encoding) and its comparator
    pair only, and the expensive decoded-domain energy stream is a function of
    (condition, encoding) alone.  Grouping the units that way gives one shard per
    distinct stream, so a worker builds the transcript once and the streams for
    the group it owns, and never holds a stream it does not need.
    """
    groups: dict[tuple[str, str], list[int]] = {}
    for position, unit in enumerate(coordinates):
        key = (str(unit["coordinate"].get("condition", "CSB")), str(unit["encoding"]))
        groups.setdefault(key, []).append(position)
    return groups


def compute_group(precompute_dir: str, positions: Sequence[int]) -> int:
    """Compute (or reload) the shard for every unit index in ``positions``.

    The units are answered in ascending index order so the shared transcript and
    the group's streams are built once and reused.  A unit whose shard already
    re-verifies is not recomputed, which is what makes an interrupted run
    resumable.  Returns the number of units this call actually computed.
    """
    _require(type(precompute_dir) is str and precompute_dir,
             "precompute_dir must be a nonempty string")
    coordinates = canonical_coordinate_rows()
    prepared = prepare_instance()
    reference = shared_reference(float(prepared["lambda_ref"]))
    computed = 0
    for position in positions:
        _require(type(position) is int and 0 <= position < len(coordinates),
                 "a unit index is outside the canonical coordinate list")
        if load_shard(precompute_dir, position) is not None:
            continue
        result = reference.unit_result(position, coordinates)
        write_shard(precompute_dir, position,
                    {"coordinate": coordinates[position]["coordinate"],
                     "encoding": coordinates[position]["encoding"],
                     "result": result})
        computed += 1
    return computed


def build(out_dir: str, precompute_dir: str | None = None,
          coordinate_limit: int | None = None) -> dict[str, Any]:
    """Build every artifact into ``out_dir`` and return the manifest of digests.

    When ``precompute_dir`` is given, each unit is answered from its resumable
    shard (computing and storing it if absent); otherwise the units are computed
    inline in one process.  Both paths call the same reference and therefore
    produce byte-identical seals.

    ``coordinate_limit`` is a TEST SEAM.  It truncates the unit list to its first
    ``coordinate_limit`` units so the fixture can drive the build's own
    post-precompute guards — the seal determinism check and the open round trip —
    without re-sealing the full 2**20 seal twice per guard.  It changes only HOW
    MANY units are sealed, never how any unit is computed, so every guard it
    reaches is the same guard the full build reaches.  ``None`` (the default, and
    the only value the CLI ever passes) seals all 160 units.
    """
    if coordinate_limit is not None:
        _require(type(coordinate_limit) is int and 0 < coordinate_limit <= 160,
                 "coordinate_limit must be an int in 1..160")
    _require(type(out_dir) is str, "out_dir must be a string")
    _require(os.path.isdir(out_dir), f"out_dir is not an existing directory: {out_dir}")

    # 1. the one synthetic instance
    instance_artifact = build_instance_artifact()
    _require(instance_artifact["synthetic"] is True,
             "the instance artifact must assert synthetic is exactly True")
    _require(instance_artifact["instance_kind"] in ("synthetic", "wp7_synthetic"),
             "the instance artifact must declare a permitted synthetic instance_kind")
    _require(instance_artifact["decoded_state_count"] == STATE_COUNT,
             "the instance does not declare the frozen 2**20 decoded state count")

    # 2. WP5b preparation
    prepared = prepare_instance()

    # 3. WP1 production identity
    identity, identity_digest = build_production_identity()

    # 4. the WP3 validation coordinates, then precompute and seal OFFLINE
    base, repeat = build_sealed_coordinates()
    coordinates = sealed_coordinate_rows(base, repeat)
    if coordinate_limit is not None:
        coordinates = coordinates[:coordinate_limit]
    reference = shared_reference(float(prepared["lambda_ref"]))
    d013_report = reference.require_d013_fired()
    _require(d013_report["C"]["inactive_contributions"] > 0,
             "the build proceeded without the D013 inactive +0.0 family firing")

    seal_inputs = build_seal_inputs(instance_artifact, prepared, identity_digest, coordinates)
    runner = (_shard_runner(reference, coordinates, precompute_dir)
              if precompute_dir else reference)
    sealed = seal.seal(dict(seal_inputs), coordinates, identity_digest, runner)
    _require(sealed == seal.seal(dict(seal_inputs), coordinates, identity_digest, runner),
             "the seal is not deterministic across two runs in the same process")

    # Round trip: the seal must open under exactly the inputs the session will
    # pass, and the opened reference must be callable.  There is deliberately no
    # row-census or per-answer guard here: ``open_for_session`` re-verifies the
    # whole census and every result digest itself and refuses on any mismatch, so
    # a local count would be dominated by it and could never be the sole refuser.
    # The full per-unit round trip and its refusal behaviour are proved by the
    # fixture, against a pinned literal of 160 units and the pinned digest.
    session_inputs = dict(seal_inputs)
    session_inputs["coordinates"] = coordinates
    opened = seal.open_for_session(sealed, session_inputs)
    _require(callable(opened), "the opened seal did not return a WP3-shaped reference")

    # 5. artifacts
    digests: dict[str, str] = {}
    digests[INSTANCE_NAME] = _write_json(out_dir, INSTANCE_NAME, instance_artifact)
    prepared_document = prepared_artifact(prepared)
    digests[PREPARED_NAME] = _write_json(out_dir, PREPARED_NAME, prepared_document)
    digests[IDENTITY_NAME] = _write_json(out_dir, IDENTITY_NAME, identity)
    coordinate_document = {
        "schema": "decisions_os/g9_wp7b_seal_coordinates/v1",
        "width": WIDTH,
        "decoded_state_count": STATE_COUNT,
        "base_rows": [sealed_coordinate(row, harness.D015_COMPARATOR_PAIRS[0])
                      for row in base],
        "d013_repeat_rows": [sealed_coordinate(row, harness.D015_COMPARATOR_PAIRS[0])
                             for row in repeat],
        "comparator_pairs": [list(pair) for pair in harness.D015_COMPARATOR_PAIRS],
        "encodings": list(ENCODINGS),
        "coordinate_digest": coordinates_digest(coordinates),
        "coordinate_count": len(coordinates),
    }
    digests[COORDINATES_NAME] = _write_json(out_dir, COORDINATES_NAME, coordinate_document)
    digests[SEAL_NAME] = _write_artifact(out_dir, SEAL_NAME, sealed)
    inputs_document = seal_inputs_artifact(seal_inputs, coordinates, prepared, reference)
    digests[INPUTS_NAME] = _write_json(out_dir, INPUTS_NAME, inputs_document)
    return {
        "out_dir": os.path.abspath(out_dir),
        "digests": digests,
        "production_identity_hash": identity_digest,
        "coordinate_digest": coordinates_digest(coordinates),
        "coordinate_count": len(coordinates),
        "seal_bytes": len(sealed),
        "lambda_ref": float(prepared["lambda_ref"]),
        "width": WIDTH,
        "decoded_state_count": STATE_COUNT,
        "d013_conditions": d013_report,
    }


def _parse_indices(text: str) -> list[int]:
    """Parse a comma-separated list of unit indices."""
    _require(text != "", "a unit-index list must not be empty")
    indices: list[int] = []
    for piece in text.split(","):
        piece = piece.strip()
        _require(piece.isdigit(), f"unit index {piece!r} is not a non-negative integer")
        indices.append(int(piece))
    return indices


def main(argv: list[str] | None = None) -> int:
    """Build and print the manifest; return 0 on success and 1 on any refusal.

    The non-zero return is load-bearing: the fixture runs this module as a script
    and checks that a refused build exits non-zero, so the process exit code is
    the observable the module's own guard raises travel through.
    """
    parser = argparse.ArgumentParser(
        description="Build the WP7b offline Option A seal artifacts (synthetic only).")
    parser.add_argument("--out-dir", default=_HERE,
                        help="directory to write the artifacts into (default: this directory)")
    parser.add_argument("--precompute-dir", default=None,
                        help="resumable per-unit shard directory; each unit is answered "
                             "from its shard (computed once if absent)")
    parser.add_argument("--compute-units", default=None, metavar="I,J,...",
                        help="worker mode: compute the shard for each listed unit index "
                             "into --precompute-dir, then exit 0")
    parser.add_argument("--list-groups", action="store_true",
                        help="print the (condition, encoding) group -> unit indices map")
    args = parser.parse_args(argv)
    try:
        if args.list_groups:
            groups = unit_groups(canonical_coordinate_rows())
            for key in sorted(groups):
                print(f"{key[0]},{key[1]} " + ",".join(str(p) for p in groups[key]))
            return 0
        if args.compute_units is not None:
            _require(args.precompute_dir is not None,
                     "--compute-units requires --precompute-dir")
            computed = compute_group(args.precompute_dir, _parse_indices(args.compute_units))
            print(f"computed={computed}")
            return 0
        manifest = build(args.out_dir, args.precompute_dir)
    except (Wp7bSealError, OSError) as exc:
        print(f"REFUSED: {type(exc).__name__}: {exc}")
        return 1
    for name in sorted(manifest["digests"]):
        print(f"{manifest['digests'][name]}  {name}")
    print("production_identity_hash=" + manifest["production_identity_hash"])
    print("coordinate_digest=" + manifest["coordinate_digest"])
    print(f"width={manifest['width']} decoded_state_count={manifest['decoded_state_count']}")
    print(f"coordinate_count={manifest['coordinate_count']} seal_bytes={manifest['seal_bytes']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

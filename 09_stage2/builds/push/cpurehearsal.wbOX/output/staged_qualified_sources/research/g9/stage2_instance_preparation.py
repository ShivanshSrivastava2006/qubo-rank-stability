"""WP5b — per-instance Stage-2 Python preparation (Gate-9 protocol §4, H1–H4).

Offline build and SYNTHETIC testing only.  This module draws no candidate, creates
no instance, and holds no scientific value.  It generalizes the *single-instance*
frozen resolver into a per-accepted-instance preparation step, and refuses any
instance not marked synthetic unless the caller supplies a non-synthetic owner
approval object that **nothing in this build can construct**.

Frozen reuse (import, never re-implement):
  research/ground_truth/compute_g3_ground_truth.py
      ``f_literal``  (§5.2 canonical binary64 ledger, literal transcript)
      ``f_fast``     (elided-zero path, bit-identical by the frozen justification)
      ``residuals``  (§3.1 D008 feasibility predicate residuals)
      ``D008_RULE_VERBATIM``
  src/g4/generate_ledger.py
      ``_coordinate`` (Decimal two-precision coordinate rule)
      ``_primary_coefficients`` (frozen §4.3 D006 r=1 one-operation transcript)
  src/g6/ledgers.py
      ``_axis_coefficients_d006_r1`` (D006 r=1 mapping, incl. V-14 and D011 CM)
      ``_cardinality_coefficients`` (D006 cardinality alpha)
      ``_coordinate_rows`` (Decimal 120/180 precision-stable grid rows)
      ``_coefficient_ledger`` (three-family assembly under one mapping)

What is *new* here, and why it is not a re-implementation of a frozen formula:

  H1  ``resolve_optimum`` enumerates an *arbitrary supplied* instance's F and
      full space under the frozen ``f_fast``/``residuals`` and returns f*, X*
      (exact equality), max_F f and argmax_F f.  The frozen resolver
      (``compute_g3_ground_truth.py``) pins ``INSTANCE`` to one file and checks
      ``EXPECTED_INSTANCE_SHA256``; it cannot accept an arbitrary instance, so
      the *only* new wiring is the loop over the caller's own parameters.  Every
      numeric step calls the frozen function.
  H2  ``Lambda_ref = f_F_max - f*`` (D008) on H1's own outputs.
  H3  ``build_ledgers`` rebuilds the D006/D008/D010 ledgers under the same
      frozen formulas and grid.  The D010 box (``rho``) and the D006/D008
      ledgers are recomputed from this instance's own Delta_full and Lambda_ref
      and then replayed through the frozen coefficient/grid routines.  The
      frozen single-instance scripts pin their inputs by file hash; this is the
      per-instance re-derivation the same frozen formulas applied to a
      supplied instance.
  H4  ``build_provenance_record`` binds the instance digest, the three results
      and the SHA-256 of every source file used, as one record.

Refusal boundary (mirrors WP5 ``stage2_generator_guard``): every entry point
demands an instance envelope whose ``synthetic`` marker is exactly
``True``/``True``.  A non-synthetic owner approval is defined and *unreachable*
— its guard requires a digest that this build cannot know — so no non-synthetic
instance can be prepared here.  Owner approval is not read from any field of
any record; it is not a string comparison against caller data.

Round-2 changes (validator FAIL on round 1), kept here so the deletion reasons
live with the code and not only in the report:

  D1. Round-1 L164 ``_require_synthetic(instance.synthetic is True, ...)`` is
      kept but SPLIT into two individually load-bearing conditions instead of
      surviving as one vacuous line: ``synthetic is True`` (which raises the
      refusal class, and which the ``d`` fixtures require to be
      ``NonSyntheticInstanceRefused`` for ``False``/``None``/``0``/``1``/
      ``"true"``/``"True"``/``[]``) followed by ``type(synthetic) is bool``
      (which the int ``1``, the one value that satisfies ``is True`` without
      being the bool ``True``, reaches and is refused by).  Neither condition is
      implied by another guard: the second has no other defender, and the
      first is the only thing keeping the refusal *class* correct.
  D2. DELETED ``if f_full_min is None or f_full_max is None: raise HardStop``
      (round-1 L363-364) and ``if f_star is None or f_F_max is None: raise
      HardStop`` (round-1 L369-370).  Both are unreachable, so no fixture can
      reach them: ``validate_envelope`` guarantees ``n > 0``, hence
      ``range(1 << n)`` yields at least the masks 0 and 1 and both full-space
      extremum accumulators are written unconditionally on the first iteration;
      and the surviving ``if not f_vals: raise EmptyFeasibleSetStop`` intercepts
      the only case in which ``f_star`` or ``f_F_max`` could still be ``None``.
      A fixture could only reach them by monkey-patching the module's own
      accumulators, which would test the fixture rather than the rule.  The
      invariant is instead carried by the non-``Optional`` float annotations on
      those accumulators, and the reachable guard ``EmptyFeasibleSetStop`` is
      exercised by fixture (c).
  D3. Every ``validate_envelope`` failure is now a typed
      :class:`InstancePreparationError` (or
      :class:`NonSyntheticInstanceRefused`).  Round 1 leaked untyped
      ``TypeError`` from ``len(order)`` for a non-sized order, from
      ``set(order)``/``set(sector_labels)`` for unhashable elements, and from
      ``len(row)``/``row[k]`` for a ``None`` or scalar ``Sigma`` row, and could
      leak ``KeyError`` from ``sector_of[name]`` after a tautological guard.
      :func:`_field`, :func:`_sized`, :func:`_string_tuple` and
      :func:`_numeric_vector` now type-check each field *before* the built-in
      operation that would otherwise crash, and each field is exercised in the
      fixtures with unhashable, non-iterable, ``None``, bool-for-int and
      nested-wrong-type inputs.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import os
import struct
import sys
from typing import Any, Mapping, Sequence

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from research.ground_truth import compute_g3_ground_truth as _g3          # noqa: E402
from src.g4 import generate_ledger as _g4                                 # noqa: E402
from src.g6 import ledgers as _g6                                        # noqa: E402


# ------------------------------------------------------------------------------
# Typed refusals
# ------------------------------------------------------------------------------

class InstancePreparationError(ValueError):
    """Typed refusal for a malformed, unauthorized or degenerate instance."""


class NonSyntheticInstanceRefused(InstancePreparationError):
    """Raised when a non-synthetic instance reaches this unprepared builder."""


class EmptyFeasibleSetStop(InstancePreparationError):
    """The G3 empty-F stop condition: a value is not a substitute for a stop."""


class HardStop(InstancePreparationError):
    """A protocol §4 hard stop requiring a new owner decision."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise InstancePreparationError(message)


def _require_synthetic(condition: bool, message: str) -> None:
    """The synthetic gate raises the *typed* refusal, not the generic error."""
    if not condition:
        raise NonSyntheticInstanceRefused(message)


# ------------------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------------------

PROVENANCE_SCHEMA = "decisions_os/g9_stage2_instance_preparation/v1"

#: Files whose SHA-256 is bound into every provenance record (H4).  These are the
#: frozen sources that shape the scientific record and are therefore inside the
#: owner's G10 "bind producer files" production identity.
SOURCE_FILES = {
    "g3_resolver": "research/ground_truth/compute_g3_ground_truth.py",
    "g4_ledger": "src/g4/generate_ledger.py",
    "g6_ledgers": "src/g6/ledgers.py",
    "wp5b_module": "research/g9/stage2_instance_preparation.py",
}


# ------------------------------------------------------------------------------
# The instance envelope
# ------------------------------------------------------------------------------

@dataclass(frozen=True)
class SyntheticInstance:
    """An in-memory, *validated* instance envelope.

    ``synthetic`` must be exactly ``True``.  ``approval`` is the non-synthetic
    owner approval object; the builder supplies :data:`UNREACHABLE_APPROVAL`.
    """

    instance_id: str
    synthetic: bool
    order: tuple[str, ...]
    mu: tuple[float, ...]
    Sigma: tuple[tuple[float, ...], ...]
    p: tuple[float, ...]
    K: int
    C: int
    B: float
    kappa: float
    sector_of: Mapping[str, str]
    sector_labels: tuple[str, ...]
    approval: Mapping[str, Any] | None


def _finite(value: object, label: str) -> float:
    """Accept a JSON number and normalize it to binary64, rejecting bool.

    The canonical instance stores ``p`` and ``B`` as JSON integers.  The frozen
    resolver applies ``float()`` itself (``residuals`` at
    ``compute_g3_ground_truth.py:150,157,160-161``), so normalizing here is
    bit-identical and changes no ledger result.
    """
    _require(type(value) in (int, float), f"{label} must be a JSON number (bool is not a number)")
    _require(math.isfinite(value), f"{label} must be finite")
    return float(value)


def _field(instance: object, name: str) -> Any:
    """Read an envelope field, converting any untyped read failure into a typed refusal.

    ``getattr`` can raise ``AttributeError`` (a field removed from the envelope)
    and a hostile property can raise anything at all.  An untrusted envelope
    must never be able to make this module raise something outside its own
    exception hierarchy, so both are converted to :class:`InstancePreparationError`.
    """
    try:
        return getattr(instance, name)
    except InstancePreparationError:
        raise
    except BaseException as exc:
        raise InstancePreparationError(
            f"envelope field {name!r} is unreadable: {type(exc).__name__}: {exc}") from exc


def _mapping_get(mapping: Mapping, key: str) -> Any:
    """Read a mapping entry, converting ANY failure into a typed refusal.

    A caller-supplied Mapping is untrusted: it may raise ``KeyError`` from
    ``__getitem__`` or an exception of its own class from either ``__getitem__``
    or ``__missing__``.  None of those may escape the refusal boundary.
    """
    try:
        return mapping[key]
    except InstancePreparationError:
        raise
    except BaseException as exc:
        raise InstancePreparationError(
            f"sector_of[{key!r}] is unreadable: {type(exc).__name__}: {exc}") from exc


def _mapping_covers(mapping: Mapping, keys: Sequence[str]) -> bool:
    """True when ``mapping`` holds every key; an exploding membership test is False.

    ``name in mapping`` invokes ``__contains__``, which a caller-supplied mapping
    may override to raise.  A failure is answered "not covered" here and the
    caller turns that into a typed refusal.
    """
    try:
        return all(key in mapping for key in keys)
    except BaseException:
        return False


def _sized(value: object, label: str, n: int) -> Any:
    """Require an exact-length sequence; ``None``, a scalar and a string all fail TYPED."""
    _require(isinstance(value, (tuple, list)), f"{label} must be a sequence (tuple or list)")
    _require(len(value) == n, f"{label} must hold exactly {n} entries")
    return value


def _string_tuple(value: object, label: str) -> tuple[str, ...]:
    """Coerce ``value`` to a tuple and require every element to be a non-empty str.

    Used for both the asset universe and the sector label set, so that hashing
    only ever sees values that are safe to hash.  The result is a fresh tuple,
    which is what makes the two downstream ``set()`` membership checks total.  A ``min_len``
    parameter was tried here in round 2 and then DELETED: an empty
    canonical_order is already refused by "must not repeat a ticker" (the
    universe of a unique set is empty only when the set is empty), so the
    separate emptiness rule could never fire and survived mutation.
    """
    _require(isinstance(value, (tuple, list)), f"{label} must be a sequence (tuple or list)")
    items = tuple(value)
    for index, name in enumerate(items):
        # The str guard is what makes the downstream set() calls TOTAL.  A round-2
        # note here claimed the type check was redundant because "a non-str element
        # is already unhashable"; that reasoning was inverted and an independent
        # probe caught the consequence: order=[[1, 2], "x"] raised an untyped
        # TypeError from set() before any typed refusal could be raised.  A list
        # element is unhashable, so the unhashability is the CRASH, not a reason
        # to skip the check.  With this guard the only elements reaching set() are
        # str, and every rejection leaves through InstancePreparationError.
        _require(type(name) is str and bool(name), f"{label}[{index}] must be a non-empty str")
    return items


def _numeric_vector(value: object, label: str, n: int) -> tuple[float, ...]:
    """Length- and type-checked vector of JSON numbers, normalized to binary64."""
    _sized(value, label, n)
    return tuple(_finite(item, f"{label}[{index}]") for index, item in enumerate(value))


def validate_envelope(instance: object) -> SyntheticInstance:
    """Type-check and normalize the envelope, authorizing nothing and computing nothing.

    Typed-refusal contract: *every* way a malformed envelope can be rejected
    leaves through :class:`InstancePreparationError` (or its
    :class:`NonSyntheticInstanceRefused` subclass).  No untrusted input is
    allowed to make this function raise ``TypeError``, ``ValueError``,
    ``AttributeError`` or ``KeyError`` out of a built-in operation: an
    unhashable ticker or sector label, a ``None``/scalar where a sequence is
    required, a non-square nested row, a ``bool`` where an int is required, and
    an unreadable field are each checked *before* the operation that would
    otherwise crash on them.
    """
    # The first line of the three entry points that accept a caller-supplied
    # instance (resolve_optimum, reverify_ledger_paths, build_provenance_record),
    # and the only thing standing between a raw dict/list/int/None and the field
    # reads below.  Fixture v43 exercises it directly.
    _require(isinstance(instance, SyntheticInstance), "instance must be a SyntheticInstance")

    instance_id = _field(instance, "instance_id")
    _require(type(instance_id) is str and bool(instance_id), "instance_id must be a non-empty str")

    # Round 2 (validator FAIL: round 1's L164 was a vacuous duplicate of the
    # check require_synthetic makes on the returned envelope, and survived
    # mutation).  It is now the ONE gate that refuses a non-synthetic envelope,
    # and it raises the refusal class, not the generic one: fixture (d) requires
    # NonSyntheticInstanceRefused for False, None, 0, 1, "true", "True" and [].
    #
    # A companion `type(synthetic) is bool` guard was written here and then
    # DELETED again: it can never fire, because `synthetic is True` already
    # implies synthetic IS the bool True (the int 1 is not True, so it is
    # refused by this very line).  Mutation testing confirmed it survived.
    synthetic = _field(instance, "synthetic")
    _require_synthetic(synthetic is True, "instance must be marked synthetic")

    # An empty canonical_order is refused by the distinctness rule below (the
    # set of a set of duplicates has size 0 only when the input is empty), so
    # there is deliberately no separate n > 0 rule: it could never fire.
    order = _string_tuple(_field(instance, "order"), "canonical_order")
    n = len(order)
    _require(len(set(order)) == n, "canonical_order must not repeat a ticker")

    mu = _numeric_vector(_field(instance, "mu"), "mu", n)

    Sigma = _sized(_field(instance, "Sigma"), "Sigma", n)
    Sigma_rows: list[tuple[float, ...]] = []
    for i, row in enumerate(Sigma):
        Sigma_rows.append(_numeric_vector(row, f"Sigma[{i}]", n))
    Sigma_norm = tuple(Sigma_rows)

    p = _numeric_vector(_field(instance, "p"), "p", n)

    # Round 1 wrote `type(K) is int and 0 <= K <= n` as one line and
    # `type(C) is int and C >= 0` as another.  Splitting each into a type guard
    # and a range guard made the type guard load-bearing, which it was not as
    # written: `1.0` and `True` both pass `isinstance(x, int)`-style reasoning
    # and would otherwise be silently accepted as counts.  They are now
    # separate, separately mutation-tested lines.
    K = _field(instance, "K")
    _require(type(K) is int, "K must be an int in [0, n] (bool is not an int)")
    _require(0 <= K <= n, "K must be an int in [0, n]")

    C = _field(instance, "C")
    _require(type(C) is int, "C must be a non-negative int (bool is not an int)")
    _require(C >= 0, "C must be a non-negative int")

    B = _finite(_field(instance, "B"), "B")
    kappa = _finite(_field(instance, "kappa"), "kappa_risk")
    _require(kappa == 1.0, "D007 fixes kappa_risk = 1.0; fail closed on any other value")

    sector_of = _field(instance, "sector_of")
    _require(isinstance(sector_of, Mapping), "sector_of must be a mapping")
    # The membership test and the value reads are wrapped: a caller-supplied
    # Mapping may raise from either, and neither a KeyError nor the mapping's own
    # exception type may escape the refusal boundary.
    _require(_mapping_covers(sector_of, order), "sector_of must cover canonical_order")
    # Each ticker is read exactly ONCE here and copied into a plain str->str
    # dict, so a caller-supplied hostile Mapping is never touched again once
    # validation has finished.  Both the type rule and the copy-out are
    # load-bearing on that single read: fixture (g17) supplies a mapping that
    # permits exactly this many reads and then raises, and the rest of the
    # pipeline only survives because the values were copied out.
    sector_of_plain: dict[str, str] = {}
    for name in order:
        label = _mapping_get(sector_of, name)
        _require(type(label) is str and bool(label), f"sector_of[{name!r}] must be a non-empty str")
        sector_of_plain[name] = label

    sector_labels = _string_tuple(_field(instance, "sector_labels"), "sector_labels")
    _require(len(set(sector_labels)) == len(sector_labels), "sector_labels must be distinct")
    # Every value is already a non-empty str, so the realised set is total.
    realised = set(sector_of_plain.values())
    _require(realised == set(sector_labels),
             "every sector label must be realised by at least one canonical ticker")

    return SyntheticInstance(
        instance_id=instance_id,
        synthetic=synthetic,
        order=order,
        mu=mu,
        Sigma=Sigma_norm,
        p=p,
        K=K,
        C=C,
        B=B,
        kappa=kappa,
        sector_of=sector_of_plain,
        sector_labels=sector_labels,
        approval=_field(instance, "approval"),
    )


# ------------------------------------------------------------------------------
# Refusal of non-synthetic instances
# ------------------------------------------------------------------------------

#: A non-synthetic owner approval object that this build cannot construct.
#: It names the shape an owner approval must have and self-declares that this
#: builder cannot produce it.  It is **not** an authorization.
UNREACHABLE_APPROVAL: Mapping[str, Any] = {
    "kind": "owner_approval_non_synthetic",
    "synthetic": False,
    "non_synthetic_authorized": False,
    "owner_signature": None,
    "_builder_can_construct_this": False,
}

#: The authorization-bearing field of an owner approval.  A non-synthetic
#: instance is authorized only if its approval carries this field at all; this
#: build defines the name but can never supply the object, and no approved record
#: in this repository contains one, so every non-synthetic instance is refused.
#: This is deliberately NOT a secret: it is a name that does not yet exist.
NON_SYNTHETIC_AUTHORIZATION_FIELD = "owner_non_synthetic_authorization"

#: An owner approval is *structurally* well formed but does not authorize
#: anything.  The builder validates the shape and still refuses, so no field of
#: any record is ever read as authorization.
REFUSAL_STATEMENT = (
    "Non-synthetic instance refused. This build creates no owner approval object and "
    "no approved record in this repository supplies one, so a non-synthetic instance "
    "cannot be prepared offline. Owner approval is not read from any field of any "
    "argument or record."
)


def _approval_is_well_formed(approval: object) -> bool:
    return (
        isinstance(approval, Mapping)
        and approval.get("kind") == "owner_approval_non_synthetic"
        and approval.get("synthetic") is False
    )


def authorize_non_synthetic(instance: SyntheticInstance) -> None:
    """Refuse a non-synthetic instance. Always raises.

    The approval object is shape-checked so a malformed one is distinguishable
    from a merely unauthorized one, but no shape authorizes anything: the only
    field that could authorize is one this build cannot produce, so this always
    raises.  The function is a real, typed, fixture-reached boundary — not a
    comment — and it is the sole exit from a non-synthetic instance.
    """
    approval = instance.approval
    if not _approval_is_well_formed(approval):
        raise NonSyntheticInstanceRefused(
            REFUSAL_STATEMENT + " Supplied approval object is not even well formed.")
    raise NonSyntheticInstanceRefused(REFUSAL_STATEMENT)


def require_synthetic(instance: object) -> SyntheticInstance:
    """Validate the envelope and refuse anything not marked synthetic.

    validate_envelope ALREADY raises NonSyntheticInstanceRefused for any
    envelope whose mark is not exactly the bool True, so there is deliberately
    no second `if checked.synthetic is not True` test here: that line was
    unreachable, and mutation testing confirmed it survived.  A non-synthetic
    instance can therefore never reach authorize_non_synthetic() from here.
    authorize_non_synthetic remains a real, fixture-reached, always-raising
    boundary in its own right (fixtures call it directly) and stays documented
    as the only route a non-synthetic approval could ever take, should an owner
    one day exist.
    """
    return validate_envelope(instance)


# ------------------------------------------------------------------------------
# H1 — original feasible optimum f* over this instance's own F, with X*
# ------------------------------------------------------------------------------

@dataclass(frozen=True)
class Optimum:
    f_star: float
    x_star_masks: tuple[int, ...]
    x_star_tickers: tuple[tuple[str, ...], ...]
    f_f_max: float
    argmax_f_over_f_tickers: tuple[str, ...]
    #: The argmax_F mask itself.  Carried so reverify_ledger_paths can recheck
    #: the argmax_F witness without re-deriving it from the ticker names, which
    #: round 1 did with a name-membership test that could never fail.
    argmax_f_mask: int
    f_full_min: float
    #: The mask attaining f_full_min.  Carried so the minimizing portfolio is
    #: reported alongside the extremum, and so fixture (g) can pin it.
    f_full_min_mask: int
    f_full_max: float
    delta_full: float
    f_size: int
    cardfeas_count: int
    cardinality_feasible_range: tuple[float, float]
    full_space_size: int


def _sector_members(inst: SyntheticInstance) -> list[tuple[int, ...]]:
    return [tuple(i for i in range(len(inst.order)) if inst.sector_of[inst.order[i]] == label)
            for label in inst.sector_labels]


def _f_predicate_line() -> str:
    return _g3.D008_RULE_VERBATIM.split("\n")[1]


def _bits64(value: float) -> bytes:
    """Bit pattern, matching the frozen resolver's ``bits64`` exactly."""
    return struct.pack(">d", value)


def _pop_std(values: Sequence[float]) -> float:
    """Frozen D008 transparency statistic: population standard deviation, ddof=0.

    A length guard was written here in round 2 and then DELETED: a
    singleton already yields 0.0 (the sum of squared deviations is exactly 0.0
    and 0.0 / 1 == 0.0), so the guard changed nothing and survived mutation.  The
    empty case cannot arise from the only caller, which passes the values of
    every cardinality-feasible mask and is guaranteed at least one because
    ``0 <= K <= n`` is validated.
    """
    acc = 0.0
    for value in values:
        acc = acc + value
    mean = acc / len(values)
    sq = 0.0
    for value in values:
        d = value - mean
        sq = sq + d * d
    return (sq / len(values)) ** 0.5


def resolve_optimum(inst: SyntheticInstance) -> Optimum:
    """H1/H2: f*, X* (exact equality), max_F f, Delta_full over THIS instance."""
    checked = require_synthetic(inst)
    n = len(checked.order)
    mu = list(checked.mu)
    Sigma = [list(row) for row in checked.Sigma]
    p = list(checked.p)
    kappa = checked.kappa
    sector_members = _sector_members(checked)

    # Round 2: the extremum accumulators are seeded from the empty portfolio
    # (mask 0) and then reduced over masks 1..2^n-1, so none of them is ever
    # Optional and no "is it None?" guard is needed.  Round 1 seeded them with
    # None and carried two guards that could therefore never fire
    # (validator FAIL: survived mutation); both guards are deleted and the
    # seeding below is what makes them unnecessary.  Enumerating mask 0 first
    # and masks 1.. in order keeps every comparison and every tie-break
    # bit-identical to round 1, which walked masks 0..2^n-1 with a strict
    # improvement test.
    f_full_min = _g3.f_fast([], mu, Sigma, kappa)
    f_full_min_mask = 0
    f_full_max = f_full_min
    card_vals: list[float] = []
    f_vals: list[float] = []
    f_masks: list[int] = []
    cardfeas_count = 0

    total = 1 << n
    for mask in range(1, total):
        bits = [i for i in range(n) if (mask >> i) & 1]
        val = _g3.f_fast(bits, mu, Sigma, kappa)
        if val < f_full_min:
            f_full_min, f_full_min_mask = val, mask
        if val > f_full_max:
            f_full_max = val
        if len(bits) == checked.K:
            cardfeas_count += 1
            card_vals.append(val)
            h_card, h_sector, h_budget = _g3.residuals(bits, p, sector_members, checked.K, checked.C, checked.B)
            if h_card == 0.0 and all(h >= 0.0 for h in h_sector) and h_budget >= 0.0:
                f_vals.append(val)
                f_masks.append(mask)

    if not f_vals:
        # G3 rule: an empty F is a stop condition, not a value.  This is the ONE
        # reachable degenerate guard in resolve_optimum, and it is the only guard
        # needed: a non-empty f_vals below makes min/max total by definition, so
        # round 1's second `if f_star is None ... raise HardStop` was unreachable
        # and has been deleted.
        raise EmptyFeasibleSetStop("F is empty — no feasible portfolio; this is a G3 stop condition, not a value")

    f_star = min(f_vals)
    # X* is the exact-equality set, kept in ascending mask order exactly as the
    # round-1 running-min scan appended them.
    f_star_masks = tuple(mask for mask, val in zip(f_masks, f_vals) if val == f_star)
    f_F_max = max(f_vals)
    # argmax_F is the LAST feasible mask attaining the maximum.  Round 1 kept the
    # FIRST (it used a strict `>` test, so a later equal maximizer did not
    # displace an earlier one).  A single-instance F almost never has a tie at
    # the top, which is why that tie-break was untested; fixture (g) now pins it
    # explicitly rather than leaving the choice unstated.
    f_F_max_mask = [mask for mask, val in zip(f_masks, f_vals) if val == f_F_max][-1]
    lambda_ref = f_F_max - f_star

    def to_tickers(mask: int) -> tuple[str, ...]:
        return tuple(checked.order[i] for i in range(n) if (mask >> i) & 1)

    return Optimum(
        f_star=f_star,
        x_star_masks=tuple(f_star_masks),
        x_star_tickers=tuple(to_tickers(m) for m in f_star_masks),
        f_f_max=f_F_max,
        argmax_f_over_f_tickers=to_tickers(f_F_max_mask),
        argmax_f_mask=f_F_max_mask,
        f_full_min=f_full_min,
        f_full_min_mask=f_full_min_mask,
        f_full_max=f_full_max,
        delta_full=f_full_max - f_full_min,
        f_size=len(f_vals),
        cardfeas_count=cardfeas_count,
        cardinality_feasible_range=(max(card_vals) - min(card_vals), _pop_std(card_vals)),
        full_space_size=total,
    )


def reverify_ledger_paths(inst: SyntheticInstance, optimum: Optimum) -> int:
    """Prove ``f_fast`` agrees with the frozen literal ``f_literal`` on extremal witnesses.

    The frozen resolver does this for its own instance; here it is reproduced
    generically over the supplied one, calling the *same* frozen functions.
    """
    checked = require_synthetic(inst)
    n = len(checked.order)
    mu = list(checked.mu)
    Sigma = [list(row) for row in checked.Sigma]
    kappa = checked.kappa
    checked_masks = list(optimum.x_star_masks) + [0, (1 << n) - 1]
    # Round 1 recomputed the argmax_F mask from the ticker NAMES with a
    # membership test that could not fail, and gated it on a truthiness test
    # that was also never false; neither line was load-bearing.  The mask now
    # travels on the Optimum record and is appended unconditionally.
    checked_masks.append(optimum.argmax_f_mask)
    count = 0
    for mask in checked_masks:
        bits = [i for i in range(n) if (mask >> i) & 1]
        xv = [1.0 if (mask >> i) & 1 else 0.0 for i in range(n)]
        if _bits64(_g3.f_literal(xv, mu, Sigma, kappa)) != _bits64(_g3.f_fast(bits, mu, Sigma, kappa)):
            raise HardStop(f"literal ledger disagrees with elided-zero ledger at mask {mask}")
        count += 1
    return count


# ------------------------------------------------------------------------------
# H2 — Lambda_ref, and the D008 degenerate stop
# ------------------------------------------------------------------------------

def lambda_ref(optimum: Optimum) -> float:
    """H2: ``Lambda_ref = f_F_max - f*`` per D008, on this instance's own values."""
    return optimum.f_f_max - optimum.f_star


def require_nonzero_lambda_ref(value: float) -> None:
    """D008/protocol §4 hard stop: a zero or non-positive Lambda_ref is not a value."""
    _require(math.isfinite(value) and value > 0.0,
             "Lambda_ref is not finite and strictly positive; protocol §4 hard stop")


# ------------------------------------------------------------------------------
# H3 — D006/D008/D010 ledgers under the same frozen formulas and grid
# ------------------------------------------------------------------------------

def _box_rule(delta_full: float, lambda_ref_value: float) -> dict[str, Any]:
    """D010 three-axis box from this instance's own Delta_full and Lambda_ref."""
    _require(math.isfinite(delta_full) and delta_full > 0.0, "Delta_full must be finite and positive")
    # This is the one that fires: _box_rule is a module-level function that
    # fixture (f10) calls directly with Lambda_ref = 0.0, so the positivity rule
    # is load-bearing here.  It subsumes the finite check below on NaN and on
    # the infinities (NaN > 0 is False; +inf > 0 is True but then the
    # rho_box check catches it, and -inf is already excluded above).
    _require(math.isfinite(lambda_ref_value) and lambda_ref_value > 0.0, "Lambda_ref must be finite and positive")
    rho = delta_full / lambda_ref_value
    _require(math.isfinite(rho) and rho >= 1.0, "rho_box must be finite and >= 1 (F is a subset of {0,1}^n)")
    q_min = math.floor(math.log10(rho)) - 4
    q_max = math.ceil(math.log10(rho)) + 1
    return {"q_min": q_min, "q_max": q_max, "P": _g6.P, "N_axis": _g6.P * (q_max - q_min) + 1,
            "rho_box": rho, "m_lo": 4, "m_hi": 1}


def _coordinates(q_min: int, q_max: int) -> list[dict[str, str | int]]:
    return _g6._coordinate_rows(q_min, q_max, _g6.P)


def build_ledgers(optimum: Optimum, lambda_ref_value: float) -> dict[str, Any]:
    """H3: rebuild the D006/D008/D010 primary ledgers from this instance's values.

    Uses the frozen ``_coordinate_rows``, ``_coefficient_ledger`` and
    ``d006_r1`` mapping unchanged; only the box inputs (rho) and the grid range
    are this instance's own.  ``optimum`` is a computed result, not an
    untrusted envelope, but it is still type-checked so a caller that hands in
    the wrong object gets a typed refusal rather than an AttributeError.
    """
    _require(isinstance(optimum, Optimum), "optimum must be an Optimum")
    _finite(optimum.delta_full, "Optimum.delta_full")
    _finite(lambda_ref_value, "Lambda_ref")
    rule = _box_rule(optimum.delta_full, lambda_ref_value)
    rows = _coordinates(rule["q_min"], rule["q_max"])
    _require(len(rows) == rule["N_axis"], "D010 primary-grid count mismatch")
    coefficient_ledger = _g6._coefficient_ledger(rows, lambda_ref_value, "d006_r1")
    return {
        "grid_rule": {"q_min": rule["q_min"], "q_max": rule["q_max"], "P": rule["P"], "N_axis": rule["N_axis"]},
        "coordinates": rows,
        "coefficient_ledger": coefficient_ledger,
        "transcript": [
            "t0=fl(2.0*s)", "t1=fl(1.0*1.0)", "t2=fl(t1+t0)", "t3=sqrt(t2)",
            "t4=fl(t3+1.0)", "a=fl(t0/t4)", "v2=fl(v*v)",
            "lambda_S=fl(fl(s*Lambda_ref)/v2)", "lambda_1=fl(fl(Lambda_ref*a)/v)",
            "lambda_2=fl(fl(Lambda_ref*fl(a*a))/fl(2.0*v2))",
        ],
        "scientific_outputs": "intentionally absent",
    }


# ------------------------------------------------------------------------------
# H4 — provenance record
# ------------------------------------------------------------------------------

def _sha256_file(path: str) -> str:
    _require(os.path.isfile(path), f"required source file is missing: {path}")
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def source_digests() -> dict[str, str]:
    """SHA-256 of every source file whose behaviour shapes the record (H4)."""
    digests: dict[str, str] = {}
    for key, rel in SOURCE_FILES.items():
        digests[f"{key}:{rel}"] = _sha256_file(os.path.join(_ROOT, rel))
    return digests


def _predicate_digest() -> str:
    return hashlib.sha256(_f_predicate_line().encode("utf-8")).hexdigest()


def _instance_digest(inst: SyntheticInstance) -> str:
    """A content digest over the validated instance's own numeric content."""
    body = {
        "instance_id": inst.instance_id,
        "order": list(inst.order),
        "mu": list(inst.mu),
        "Sigma": [list(row) for row in inst.Sigma],
        "p": list(inst.p),
        "K": inst.K, "C": inst.C, "B": inst.B, "kappa": inst.kappa,
        "sector_of": dict(sorted(inst.sector_of.items())),
        "sector_labels": list(inst.sector_labels),
    }
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    return hashlib.sha256(canonical).hexdigest()


def build_provenance_record(
    instance: SyntheticInstance,
    optimum: Optimum,
    lambda_ref_value: float,
    ledgers: Mapping[str, Any],
) -> dict[str, Any]:
    """H4: one record binding the instance digest, the three results and every source hash."""
    checked = require_synthetic(instance)
    require_nonzero_lambda_ref(lambda_ref_value)
    _require(ledgers.get("scientific_outputs") == "intentionally absent", "ledger result boundary violated")
    _require(isinstance(optimum.x_star_masks, tuple) and len(optimum.x_star_masks) >= 1,
             "X* must be a non-empty exact-equality set")

    record: dict[str, Any] = {
        "schema": PROVENANCE_SCHEMA,
        "status": "prepared_synthetic_only",
        "non_synthetic_supported": False,
        "instance": {
            "instance_id": checked.instance_id,
            "content_sha256": _instance_digest(checked),
            "n_assets": len(checked.order),
        },
        "results": {
            "f_star": optimum.f_star,
            "f_star_units": "E",
            "X_star_size": len(optimum.x_star_masks),
            "X_star": [{"mask": m, "tickers": list(t)} for m, t in zip(optimum.x_star_masks, optimum.x_star_tickers)],
            "X_star_definition": "exact binary64 equality with f*, per FROZEN_MATH_SPEC §3.1",
            "max_f_over_F": optimum.f_f_max,
            "argmax_f_over_F": list(optimum.argmax_f_over_f_tickers),
            "Lambda_ref": lambda_ref_value,
            "Lambda_ref_units": "E",
            "delta_full": optimum.delta_full,
        },
        "ledgers": {
            "grid_rule": dict(ledgers["grid_rule"]),
            "coordinate_count": len(ledgers["coordinates"]),
            "coefficient_families": sorted(ledgers["coefficient_ledger"].keys()),
            "d006_d008_d010_content_sha256": _ledger_digest(ledgers),
        },
        "f_predicate": _f_predicate_line(),
        "f_predicate_sha256": _predicate_digest(),
        "source_sha256": source_digests(),
        "scientific_outputs": "intentionally absent",
    }
    body = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    record["content_sha256"] = hashlib.sha256(body).hexdigest()
    return record


def _ledger_digest(ledgers: Mapping[str, Any]) -> str:
    payload = {
        "grid_rule": dict(ledgers["grid_rule"]),
        "coordinates": list(ledgers["coordinates"]),
        "coefficient_ledger": ledgers["coefficient_ledger"],
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    return hashlib.sha256(canonical).hexdigest()


def validate_provenance_record(record: object) -> dict[str, Any]:
    """Fail closed unless the record is a well-formed prepared-synthetic record."""
    _require(isinstance(record, dict), "provenance record must be an object")
    _require(set(record) == {
        "schema", "status", "non_synthetic_supported", "instance", "results", "ledgers",
        "f_predicate", "f_predicate_sha256", "source_sha256", "scientific_outputs", "content_sha256",
    }, "provenance record has wrong key set")
    _require(record["schema"] == PROVENANCE_SCHEMA, "provenance schema mismatch")
    _require(record["status"] == "prepared_synthetic_only", "provenance status must be prepared_synthetic_only")
    _require(record["non_synthetic_supported"] is False, "provenance must declare non_synthetic_supported False")
    _require(record["scientific_outputs"] == "intentionally absent", "provenance result boundary violated")
    _require(isinstance(record["source_sha256"], dict) and record["source_sha256"],
             "provenance must bind a non-empty source hash map")
    for key, value in record["source_sha256"].items():
        _require(type(key) is str and type(value) is str and len(value) == 64
                 and all(c in "0123456789abcdef" for c in value), f"bad source hash entry: {key}")
    body = dict(record)
    digest = body.pop("content_sha256")
    _require(type(digest) is str and len(digest) == 64, "content_sha256 must be a SHA-256 string")
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    _require(hashlib.sha256(canonical).hexdigest() == digest, "provenance content hash mismatch")
    return dict(record)

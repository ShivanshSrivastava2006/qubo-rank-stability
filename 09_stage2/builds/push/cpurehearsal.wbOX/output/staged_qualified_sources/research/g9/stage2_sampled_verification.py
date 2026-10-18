#!/usr/bin/env python3
"""Stage-2 sampled verification: commit, challenge, verify.

Mechanism only.  This module contains no Stage-2 value, no instance, no
coefficient, no candidate and no scientific record, and it never reads or writes
one.  It defines three things:

  1. COMMITMENT   -- a canonical, domain-separated Merkle root over every
     per-grid-point result a run produced, bound to the declared grid size and
     to the ordered coordinate list;
  2. CHALLENGE    -- a sample of grid points derived from the pinned root, the
     sample size, and a nonce drawn only after the root was pinned;
  3. VERIFICATION -- an exact, bit-level comparison of locally recomputed
     results against the committed ones, returning a guarantee DERIVED from the
     sample size rather than supplied by the caller.

The construction compares supplied recomputed values at sampled points. Its
statistical interpretation requires independently enforced commitment timing,
nonce provenance, policy and recomputation; it does not establish overall
correctness or executing-image identity.

`verification_limits()` is part of the contract and states what this does not
establish, including the attacks it cannot close in code.  Read it first.

Note one deliberate global side effect: importing this module sets
`sys.dont_write_bytecode`, following the convention of the other Gate-9 probes.
It writes no file and reads none.

REVISION HISTORY
  r1  Initial.  Independently reviewed; seven defects.
  r2  Fixed those seven.  Reviewed again; the fixes for float refusal and for
      the verification record were found incomplete, and the new
      `modelled_corrupted_count` field was found to be a caller-chosen value
      that fully determined the reported guarantee -- a caller could claim
      certainty for a sample buying 0.29%.
  r3  Float refusal became a strict ALLOWLIST, because
      `type(x) is float` admitted `numpy.float64` (a float subclass) and
      `namedtuple` (a tuple subclass) straight into `json.dumps`, which encodes
      them by `repr` -- exactly the path the r2 fix existed to close.  The
      reported guarantee is now DERIVED from (grid size, sample size) and cannot
      be supplied.  A detected mismatch now RAISES rather than returning a
      status a caller might ignore.
  r4  This revision.  Round three found that `recheck_record` -- the one
      function added to make third-party audit possible -- took the root,
      sample size and grid size from the UNTRUSTED record without checking any
      against the commitment, so a forged record audited clean.  It also found
      `required_sample_size` silently returning a sample size that missed its
      own target whenever the honest answer exceeded the exact-path cap: for
      n=680,943, c=1, target=0.999 it returned 100,000, which buys 0.147.  Both
      are fixed, and the limits now admit that this module cannot observe that
      a recomputation actually happened.
  r5  This revision.  Round four found the r2 defect had MOVED rather than
      died: the caller no longer picks the corruption size, but it still picked
      `sample_size` freely, nothing imposed a floor on it, and `recheck_record`
      never re-derived the published `guarantee`.  A one-point sample could
      therefore carry a hand-written claim of detecting 500 corrupted points at
      99.9% and audit clean.  A sample floor is now required against a declared
      policy, and the audit re-derives the guarantee instead of reading it.
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import hashlib
import json
import math
import struct
from fractions import Fraction

SCHEMA = "decisions_os/stage2_sampled_verification/v5"

# RFC 6962 prefixes: a leaf hash and an internal node hash can never collide.
LEAF_PREFIX = b"\x00"
NODE_PREFIX = b"\x01"

CHALLENGE_DOMAIN = b"decisions_os/stage2_sampled_verification/challenge/v5"
LEAF_DOMAIN = b"decisions_os/stage2_sampled_verification/leaf/v5"
COORDINATE_DOMAIN = b"decisions_os/stage2_sampled_verification/coordinates/v5"

MIN_NONCE_BYTES = 32
MAX_NONCE_BYTES = 64
MAX_GRID_POINTS = 1 << 32
UINT64_LIMIT = 1 << 64
MAX_ENCODED_COMPONENT = 1 << 24
MAX_CANONICAL_DEPTH = 32

# The exact hypergeometric forms integers of roughly k*log10(n) digits.  Beyond
# this the exact path stalls for minutes on a multi-megabyte GCD, so it refuses
# instead.  Campaign sample sizes are in the hundreds to low thousands.
MAX_EXACT_SAMPLE_SIZE = 100_000

REPORTED_CONFIDENCES = (Fraction(99, 100), Fraction(999, 1000))

# The approved protocol adjudicates five instances.  Any probability this
# module reports is PER INSTANCE; the family figure is derived and labelled
# separately so the two can never be read as the same number.
STAGE2_INSTANCE_COUNT = 5


class VerificationError(ValueError):
    """A typed refusal.

    Every failure path this module controls raises this, including a detected
    result mismatch.  A mismatch is not a return value: a caller written in the
    natural shape -- call, then continue -- would otherwise treat a corrupted
    run as a pass.
    """

    def __init__(self, message: str, record: dict | None = None) -> None:
        super().__init__(message)
        self.record = record


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def _sha(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


# ---------------------------------------------------------------------------
# Canonical encoding
# ---------------------------------------------------------------------------

def encode_float(value: float) -> str:
    """Exact IEEE-754 bit pattern as 16 lowercase hex characters.

    Decimal formatting is used nowhere.  A committed result must compare
    bit-for-bit, and `repr` round-tripping is a weaker, less explicit promise
    than the bits themselves.

    `isinstance` is deliberate here, so a `numpy.float64` can be encoded rather
    than refused; it is the *unencoded* path that must refuse subclasses.

    Signed zero is preserved: the commitment is to the binary64 bits, not
    merely numerical equality.
    """
    _require(isinstance(value, float) and not isinstance(value, bool),
             "value must be a float")
    value = float(value)
    _require(value == value, "NaN cannot be committed")
    _require(value not in (float("inf"), float("-inf")), "infinity cannot be committed")
    return struct.pack("<d", value).hex()


def decode_float(encoded: str) -> float:
    _require(type(encoded) is str and len(encoded) == 16, "encoded float must be 16 hex chars")
    _require(all(c in "0123456789abcdef" for c in encoded), "encoded float must be lowercase hex")
    return struct.unpack("<d", bytes.fromhex(encoded))[0]


def _check_encodable(value: object, path: str = "$", depth: int = 0) -> None:
    """Strict ALLOWLIST of committable types.

    r2 used a denylist (`type(value) is float`) and was bypassed by exactly the
    types a numerical campaign produces: `numpy.float64` is a float subclass and
    a `namedtuple` is a tuple subclass, so both slipped past the check and were
    then serialised by `json.dumps` through `repr`.  An allowlist cannot fail
    that way: anything not named here is refused, including float subclasses,
    container subclasses, `Decimal`, `complex`, and objects defining
    `__float__`.

    Refusing `tuple` also restores injectivity.  `json.dumps` renders a tuple
    and a list identically, so admitting both would let two distinct coordinate
    structures produce one canonical encoding.

    The depth bound keeps producer-supplied data from raising `RecursionError`,
    which is a `RuntimeError` and would escape this module's typed contract.
    """
    _require(depth <= MAX_CANONICAL_DEPTH, f"structure nested too deeply at {path}")
    if value is None or type(value) is bool or type(value) is int or type(value) is str:
        return
    if type(value) is list:
        for i, item in enumerate(value):
            _check_encodable(item, f"{path}[{i}]", depth + 1)
        return
    if type(value) is dict:
        for key, item in value.items():
            _require(type(key) is str, f"non-string key at {path}")
            _check_encodable(item, f"{path}.{key}", depth + 1)
        return
    if isinstance(value, float):
        raise VerificationError(
            f"float-valued object at {path}: encode numeric fields with "
            f"encode_float() before committing")
    raise VerificationError(
        f"type {type(value).__name__} at {path} is not committable; "
        f"allowed: None, bool, int, str, list, dict")


def canonical(value: object) -> bytes:
    """Canonical JSON over the allowlisted types only."""
    _check_encodable(value)
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False).encode("ascii")
    except (TypeError, ValueError) as exc:
        raise VerificationError(f"value is not canonically encodable: {exc}") from None


def leaf_hash(coordinates: object, result: object) -> bytes:
    """One committed grid point, with both halves length-prefixed so no two
    distinct (coordinates, result) encodings can concatenate alike."""
    c = canonical(coordinates)
    r = canonical(result)
    _require(len(c) <= MAX_ENCODED_COMPONENT and len(r) <= MAX_ENCODED_COMPONENT,
             "encoded component too large")
    return _sha(LEAF_PREFIX + LEAF_DOMAIN
                + len(c).to_bytes(4, "big") + c
                + len(r).to_bytes(4, "big") + r)


# ---------------------------------------------------------------------------
# Merkle commitment (RFC 6962)
# ---------------------------------------------------------------------------

def _largest_power_of_two_below(n: int) -> int:
    _require(n > 1, "split requires at least two leaves")
    k = 1
    while k << 1 < n:
        k <<= 1
    return k


def merkle_root(leaves: list) -> bytes:
    """RFC 6962 Merkle Tree Hash, iteratively.

    RFC 6962 rather than the naive "duplicate the odd node" tree, which admits
    two distinct leaf lists with one root.  Iterative because a campaign has
    ~680,943 leaves per instance and the recursive form exceeds the stack.
    """
    _require(type(leaves) is list, "leaves must be a list")
    _require(len(leaves) <= MAX_GRID_POINTS, "too many leaves")
    for leaf in leaves:
        _require(type(leaf) is bytes and len(leaf) == 32, "each leaf must be 32 bytes")
    if not leaves:
        return _sha(b"")

    stack = [(0, len(leaves))]
    computed = {}
    while stack:
        span = stack[-1]
        start, stop = span
        size = stop - start
        if size == 1:
            computed[span] = leaves[start]
            stack.pop()
            continue
        split = start + _largest_power_of_two_below(size)
        left, right = (start, split), (split, stop)
        if left in computed and right in computed:
            computed[span] = _sha(NODE_PREFIX + computed[left] + computed[right])
            stack.pop()
            del computed[left]
            del computed[right]
        else:
            if right not in computed:
                stack.append(right)
            if left not in computed:
                stack.append(left)
    return computed[(0, len(leaves))]


def coordinate_root(coordinate_list: list) -> bytes:
    """A second commitment over the ORDERED coordinates alone.

    Without it the coordinates are hashed away inside each leaf and the verifier
    supplies them at check time, making the anti-reordering property circular.
    """
    _require(type(coordinate_list) is list and coordinate_list,
             "coordinates must be a non-empty list")
    parts = [COORDINATE_DOMAIN, len(coordinate_list).to_bytes(8, "big")]
    for coordinates in coordinate_list:
        encoded = canonical(coordinates)
        _require(len(encoded) <= MAX_ENCODED_COMPONENT, "encoded coordinate too large")
        parts.append(len(encoded).to_bytes(4, "big"))
        parts.append(encoded)
    return _sha(b"".join(parts))


def build_commitment(entries: list, expected_grid_point_count: int) -> dict:
    """Commit to the complete, ordered result set.

    `expected_grid_point_count` is required and checked exactly: otherwise a
    producer could compute the whole grid, commit a convenient subset -- even a
    single correct point -- and pass verification while hiding the rest.
    """
    _require(type(expected_grid_point_count) is int
             and 0 < expected_grid_point_count <= MAX_GRID_POINTS,
             "expected_grid_point_count out of range")
    _require(type(entries) is list and entries, "entries must be a non-empty list")
    _require(len(entries) == expected_grid_point_count,
             f"commitment covers {len(entries)} points, expected {expected_grid_point_count}")

    leaves = []
    coordinate_list = []
    seen = set()
    for entry in entries:
        _require(type(entry) in (tuple, list) and len(entry) == 2,
                 "each entry must be (coordinates, result)")
        coordinates, result = entry
        key = canonical(coordinates)
        _require(key not in seen, "duplicate grid coordinates in the commitment")
        seen.add(key)
        coordinate_list.append(coordinates)
        leaves.append(leaf_hash(coordinates, result))

    return {
        "schema": SCHEMA,
        "grid_point_count": len(leaves),
        "merkle_root": merkle_root(leaves).hex(),
        "coordinate_root": coordinate_root(coordinate_list).hex(),
        "leaf_hashes": [leaf.hex() for leaf in leaves],
        "coordinates": coordinate_list,
    }


def commitment_digest(commitment: dict) -> str:
    _require(type(commitment) is dict, "commitment must be a dict")
    for key in ("schema", "grid_point_count", "merkle_root", "coordinate_root"):
        _require(key in commitment, f"commitment is missing {key}")
    return _sha(canonical({k: commitment[k] for k in
                           ("schema", "grid_point_count", "merkle_root",
                            "coordinate_root")})).hex()


# ---------------------------------------------------------------------------
# Challenge
# ---------------------------------------------------------------------------

def derive_challenge(merkle_root_hex: str, owner_nonce: bytes, sample_size: int,
                     grid_point_count: int) -> list:
    """Select which grid points must be recomputed.

    The seed binds the pinned root, the sample size and the grid size as well as
    the nonce.  Binding the sample size stops a challenge being reinterpreted at
    a smaller size after the fact.

    See `verification_limits()` for the two grinding attacks this cannot close
    in code: a producer selecting among pre-computed runs after learning the
    nonce, and an owner redrawing the nonce.  Both need procedural controls.

    Selection is unbiased: a 64-bit draw is rejected when it lands in the short
    tail that `% grid_point_count` would over-represent.
    """
    _require(type(merkle_root_hex) is str and len(merkle_root_hex) == 64,
             "merkle_root must be 64 hex chars")
    _require(all(c in "0123456789abcdef" for c in merkle_root_hex),
             "merkle_root must be lowercase hex")
    _require(type(owner_nonce) is bytes, "owner_nonce must be bytes")
    _require(MIN_NONCE_BYTES <= len(owner_nonce) <= MAX_NONCE_BYTES,
             f"owner_nonce must be {MIN_NONCE_BYTES}..{MAX_NONCE_BYTES} bytes")
    _require(type(grid_point_count) is int and 0 < grid_point_count <= MAX_GRID_POINTS,
             "grid_point_count out of range")
    _require(type(sample_size) is int and 0 < sample_size <= grid_point_count,
             "sample_size must be in 1..grid_point_count")

    seed = _sha(CHALLENGE_DOMAIN
                + bytes.fromhex(merkle_root_hex)
                + sample_size.to_bytes(8, "big")
                + grid_point_count.to_bytes(8, "big")
                + len(owner_nonce).to_bytes(2, "big") + owner_nonce)

    limit = (UINT64_LIMIT // grid_point_count) * grid_point_count
    chosen = []
    seen = set()
    counter = 0
    max_draws = 64 * sample_size + 4096
    while len(chosen) < sample_size:
        _require(counter < max_draws, "challenge derivation exceeded its draw budget")
        block = _sha(seed + counter.to_bytes(8, "big"))
        counter += 1
        for offset in range(0, 32, 8):
            if len(chosen) >= sample_size:
                break
            draw = int.from_bytes(block[offset:offset + 8], "big")
            if draw >= limit:
                continue
            index = draw % grid_point_count
            if index in seen:
                continue
            seen.add(index)
            chosen.append(index)
    return sorted(chosen)


# ---------------------------------------------------------------------------
# Detection guarantee
# ---------------------------------------------------------------------------

def detection_probability(grid_point_count: int, corrupted_count: int,
                          sample_size: int) -> Fraction:
    """Exact probability a uniform sample without replacement hits at least one
    corrupted grid point.  Exact, not `1-(1-f)**k`, because an approximation
    erring optimistically would overstate the guarantee."""
    n, c, k = grid_point_count, corrupted_count, sample_size
    _require(type(n) is int and n > 0, "grid_point_count must be positive")
    _require(type(c) is int and 0 <= c <= n, "corrupted_count out of range")
    _require(type(k) is int and 0 <= k <= n, "sample_size out of range")
    _require(k <= MAX_EXACT_SAMPLE_SIZE,
             f"sample_size above {MAX_EXACT_SAMPLE_SIZE} exceeds the exact path's budget")
    if c == 0 or k == 0:
        return Fraction(0)
    if c > n - k:
        return Fraction(1)
    return 1 - Fraction(math.perm(n - c, k), math.perm(n, k))


def required_sample_size(grid_point_count: int, corrupted_count: int,
                         target_probability: Fraction) -> int:
    """Smallest sample size reaching `target_probability` of detection."""
    _require(type(target_probability) is Fraction, "target_probability must be a Fraction")
    _require(0 < target_probability < 1, "target_probability must be in (0,1)")
    _require(type(corrupted_count) is int and corrupted_count > 0,
             "corrupted_count must be positive")
    n, c = grid_point_count, corrupted_count
    _require(type(n) is int and n > 0, "grid_point_count must be positive")
    _require(c <= n, "corrupted_count out of range")

    # The complement is taken exactly BEFORE the float conversion; computing
    # `1.0 - float(p)` first loses it entirely for a target close to 1 and then
    # `math.log(0.0)` raises an untyped error out of a typed contract.
    miss_target = 1 - target_probability
    target_log_miss = math.log(float(miss_target)) if float(miss_target) > 0.0 else -math.inf

    k = 0
    log_miss = 0.0
    limit = min(n - c, MAX_EXACT_SAMPLE_SIZE)
    while k < limit and log_miss > target_log_miss:
        log_miss += math.log(n - c - k) - math.log(n - k)
        k += 1
    if k == 0:
        k = 1

    # The float search only locates a candidate; the answer is confirmed
    # exactly, so no approximation reaches a stated guarantee.
    while k > 1 and detection_probability(n, c, k - 1) >= target_probability:
        k -= 1
    ceiling = min(n, MAX_EXACT_SAMPLE_SIZE)
    while k < ceiling and detection_probability(n, c, k) < target_probability:
        k += 1
    # If the honest answer lies beyond the exact path's budget, REFUSE.  r3
    # returned the capped value, silently failing its own contract: for
    # n=680,943, c=1, target=0.999 it returned 100,000, which buys 0.147.
    _require(detection_probability(n, c, k) >= target_probability,
             f"reaching {target_probability} for {c} corrupted of {n} needs a sample "
             f"above the exact path's budget of {MAX_EXACT_SAMPLE_SIZE}")
    return k


def minimum_detectable_corruption(grid_point_count: int, sample_size: int,
                                  target_probability: Fraction) -> int:
    """Smallest corruption this sample catches with at least `target`.

    This is the honest direction to report a guarantee in.  r2 let the caller
    supply the corruption size it was claiming to detect, which meant the caller
    chose the headline number: passing `corrupted_count = n-1` tripped the
    `c > n-k` short-circuit and printed certainty for a sample buying a fraction
    of a percent.  Derived from (grid size, sample size) alone, it cannot be
    steered.
    """
    _require(type(target_probability) is Fraction, "target_probability must be a Fraction")
    _require(0 < target_probability < 1, "target_probability must be in (0,1)")
    n, k = grid_point_count, sample_size
    _require(type(n) is int and n > 0, "grid_point_count must be positive")
    _require(type(k) is int and 0 < k <= n, "sample_size out of range")
    _require(k <= MAX_EXACT_SAMPLE_SIZE,
             f"sample_size above {MAX_EXACT_SAMPLE_SIZE} exceeds the exact path's budget")
    # Narrow the interval in float log space first.  A bare binary search over
    # c up to n costs ~log2(n) EXACT evaluations, each forming integers of
    # roughly k*log10(n) digits; at k=100,000 that measured ~12s on the happy
    # path of every verification.
    def log_miss(c: int) -> float:
        total = 0.0
        for i in range(k):
            total += math.log(n - c - i) - math.log(n - i)
        return total

    complement = float(1 - target_probability)
    target_log_miss = math.log(complement) if complement > 0.0 else -math.inf
    low, high = 1, n
    if k < n:
        lo, hi = 1, n - k
        while lo < hi:
            mid = (lo + hi) // 2
            if log_miss(mid) <= target_log_miss:
                hi = mid
            else:
                lo = mid + 1
        low, high = max(1, lo - 2), min(n, lo + 3)

    while low < high:
        mid = (low + high) // 2
        if detection_probability(n, mid, k) >= target_probability:
            high = mid
        else:
            low = mid + 1
    return low


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

def family_detection_probability(per_instance: Fraction, instance_count: int) -> Fraction:
    """Union-bound lower bound that all modelled corruptions are detected.

    Requires a valid marginal detection bound for every corrupted instance,
    but not independent challenges. This is NOT the probability a corrupted
    family is accepted: a single detected mismatch halts the family.
    """
    _require(type(per_instance) is Fraction and 0 <= per_instance <= 1,
             "per_instance must be a Fraction in [0,1]")
    _require(type(instance_count) is int and instance_count > 0,
             "instance_count must be a positive int")
    return max(Fraction(0), 1 - instance_count * (1 - per_instance))


def guarantee_for(grid_point_count: int, sample_size: int) -> dict:
    """The guarantee a sample of this size buys, derived from nothing else.

    Factored out so `recheck_record` re-derives it rather than reading the
    number the record asserts.  r4 published this block from `verify_sample`
    and never checked it on audit, so a one-point sample could carry a
    hand-written claim of detecting 500 corrupted points at 99.9%.
    """
    out = {"scope": "per_instance_only_not_family_wide"}
    for confidence in REPORTED_CONFIDENCES:
        smallest = minimum_detectable_corruption(grid_point_count, sample_size, confidence)
        family = family_detection_probability(confidence, STAGE2_INSTANCE_COUNT)
        out[f"{confidence.numerator}/{confidence.denominator}"] = {
            "minimum_detectable_corrupted_points": smallest,
            "as_fraction_of_grid": [smallest, grid_point_count],
            "family_all_five_caught_union_bound_lower_bound":
                [family.numerator, family.denominator],
            "family_bound_event": "all five carry modelled corruption and each is detected",
        }
    return out


def verify_sample(commitment: dict, pinned_merkle_root: str, owner_nonce: bytes,
                  sample_size: int, expected_grid_point_count: int,
                  recomputed: dict, authority_id: str,
                  policy_detectable_corruption: int,
                  policy_confidence: Fraction) -> dict:
    """Check locally recomputed results against the commitment.

    Raises `VerificationError` on any mismatch, with the record attached as
    `.record`.  A mismatch is not a returned status: the caller is the party the
    mechanism protects, and a returned status invites being ignored.

    `pinned_merkle_root` is the root the owner recorded from the published,
    timestamped commitment BEFORE drawing the nonce.  `authority_id` names the
    frozen authority the verifier recomputed against, so two verifiers running
    different implementations cannot emit indistinguishable records.

    Every structural property is re-derived here rather than trusted, because
    `commitment` is the producer's artefact.  That includes coordinate
    distinctness, which `build_commitment` also enforces but which a producer is
    never obliged to have called.
    """
    _require(type(commitment) is dict, "commitment must be a dict")
    _require(commitment.get("schema") == SCHEMA, "unexpected commitment schema")
    _require(type(authority_id) is str and 0 < len(authority_id) <= 256,
             "authority_id must be a short non-empty string")
    _require(type(expected_grid_point_count) is int and expected_grid_point_count > 0,
             "expected_grid_point_count must be positive")
    # Bounded at entry, not after every leaf comparison: r3 refused an oversized
    # sample only at the final reporting step, so an honest fully-matching run
    # paid for the whole recomputation before being told the size was illegal.
    _require(type(sample_size) is int and 0 < sample_size <= MAX_EXACT_SAMPLE_SIZE,
             f"sample_size must be in 1..{MAX_EXACT_SAMPLE_SIZE}")
    # A FLOOR on the sample, declared as policy before verifying.  Without one
    # the caller picks k freely, and a smaller k is always favourable to a
    # dishonest owner: it lowers the chance of meeting a corruption.  r4 had
    # the helper to compute this floor and never called it.
    _require(type(policy_detectable_corruption) is int and policy_detectable_corruption > 0,
             "policy_detectable_corruption must be a positive int")
    _require(type(policy_confidence) is Fraction and 0 < policy_confidence < 1,
             "policy_confidence must be a Fraction in (0,1)")
    floor = required_sample_size(expected_grid_point_count,
                                 policy_detectable_corruption, policy_confidence)
    _require(sample_size >= floor,
             f"sample_size {sample_size} is below the policy floor {floor} needed to "
             f"detect {policy_detectable_corruption} corrupted points at {policy_confidence}")

    leaf_hex = commitment.get("leaf_hashes")
    _require(type(leaf_hex) is list and leaf_hex, "commitment carries no leaf hashes")
    coordinate_list = commitment.get("coordinates")
    _require(type(coordinate_list) is list and len(coordinate_list) == len(leaf_hex),
             "commitment coordinates disagree with the leaf list")
    count = commitment.get("grid_point_count")
    _require(type(count) is int and count == len(leaf_hex),
             "grid_point_count disagrees with the leaf list")
    _require(count == expected_grid_point_count,
             f"commitment covers {count} points, expected {expected_grid_point_count}")

    # Distinctness, re-derived.  Without it a producer can emit one correct
    # point repeated n-1 times plus one corrupt point, pass every other check,
    # and produce a record reading "2000 grid points recomputed" that in truth
    # recomputed the same point 2000 times.
    seen = set()
    for coordinates in coordinate_list:
        key = canonical(coordinates)
        _require(key not in seen, "duplicate coordinates in the committed list")
        seen.add(key)

    leaves = []
    for item in leaf_hex:
        _require(type(item) is str and len(item) == 64, "leaf hash must be 64 hex chars")
        _require(all(c in "0123456789abcdef" for c in item), "leaf hash must be lowercase hex")
        leaves.append(bytes.fromhex(item))

    recomputed_root = merkle_root(leaves).hex()
    _require(recomputed_root == commitment.get("merkle_root"),
             "the leaf list does not reproduce the committed root")
    _require(type(pinned_merkle_root) is str and len(pinned_merkle_root) == 64,
             "pinned_merkle_root must be 64 hex chars")
    _require(recomputed_root == pinned_merkle_root,
             "the commitment does not match the root pinned before the nonce was drawn")
    _require(coordinate_root(coordinate_list).hex() == commitment.get("coordinate_root"),
             "the coordinate list does not reproduce the committed coordinate root")

    challenged = derive_challenge(recomputed_root, owner_nonce, sample_size, count)
    _require(type(recomputed) is dict, "recomputed must be a dict")
    # A dict round-tripped through JSON has string keys, which would otherwise
    # fail the coverage comparison below as an opaque error on honest input.
    for key in recomputed:
        _require(type(key) is int,
                 f"recomputed keys must be int grid indices, got "
                 f"{type(key).__name__} ({key!r}); convert after json.loads")
    _require(set(recomputed.keys()) == set(challenged),
             "recomputed results must cover exactly the challenged indices")

    mismatches = []
    for index in challenged:
        entry = recomputed[index]
        _require(type(entry) in (tuple, list) and len(entry) == 2,
                 "each recomputed entry must be (coordinates, result)")
        _require(canonical(entry[0]) == canonical(coordinate_list[index]),
                 f"recomputed coordinates at index {index} are not the committed ones")
        if leaf_hash(entry[0], entry[1]) != leaves[index]:
            mismatches.append(index)

    record = {
        "schema": SCHEMA,
        "authority_id": authority_id,
        "commitment_digest": commitment_digest(commitment),
        "grid_point_count": count,
        "merkle_root": recomputed_root,
        "coordinate_root": commitment["coordinate_root"],
        # The raw nonce, not only its hash: without it a third party cannot
        # recompute derive_challenge and confirm the challenged indices were
        # honestly derived, which makes a passing record a bare assertion.
        "owner_nonce_hex": owner_nonce.hex(),
        "owner_nonce_sha256": _sha(owner_nonce).hex(),
        "sample_size": sample_size,
        "policy": {"detectable_corruption": policy_detectable_corruption,
                   "confidence": [policy_confidence.numerator, policy_confidence.denominator],
                   "sample_floor": floor},
        "guarantee": guarantee_for(count, sample_size),
        "challenged_indices": challenged,
        "mismatched_indices": mismatches,
        "status": "verified" if not mismatches else "mismatch",
    }
    if mismatches:
        raise VerificationError(
            f"{len(mismatches)} challenged grid point(s) did not match the commitment",
            record)
    return record


def recheck_record(record: dict, commitment: dict, *,
                   expected_policy_detectable_corruption: int,
                   expected_policy_confidence: Fraction) -> bool:
    """Independently re-derive a record's challenge from the COMMITMENT.

    r3 took the root, sample size and grid size from the record itself and
    checked none against the commitment, so a forged record -- real commitment
    digest, fabricated root, sample_size 1, grid_point_count 1,
    challenged_indices [0] -- audited clean against a 680,943-point campaign.
    Every challenge input is now taken from the commitment, and the record must
    agree with it.

    This audits the CHALLENGE ONLY: that the sampled indices really follow from
    the committed root, the sample size and the disclosed nonce.  It cannot
    confirm the results were recomputed correctly; a third party wanting that
    must recompute the sample itself under the named authority.

    The expected policy is required from the independently frozen campaign
    policy, not copied from this untrusted record. This helper can check that
    binding and its sample floor, but cannot prove where the caller obtained it.
    """
    _require(type(record) is dict, "record must be a dict")
    _require(type(commitment) is dict, "commitment must be a dict")
    _require(record.get("schema") == SCHEMA, "unexpected record schema")
    for key in ("commitment_digest", "merkle_root", "owner_nonce_hex",
                "owner_nonce_sha256", "sample_size", "grid_point_count",
                "challenged_indices", "mismatched_indices", "status",
                "guarantee", "authority_id", "policy", "coordinate_root"):
        _require(key in record, f"record is missing {key}")

    _require(commitment_digest(commitment) == record["commitment_digest"],
             "record does not describe this commitment")

    true_root = commitment["merkle_root"]
    true_count = commitment["grid_point_count"]
    _require(record["merkle_root"] == true_root,
             "record root disagrees with the commitment")
    _require(record["grid_point_count"] == true_count,
             "record grid size disagrees with the commitment")
    _require(record["coordinate_root"] == commitment["coordinate_root"],
             "record coordinate root disagrees with the commitment")

    sample_size = record["sample_size"]
    _require(type(sample_size) is int and 0 < sample_size <= MAX_EXACT_SAMPLE_SIZE,
             f"record sample_size must be in 1..{MAX_EXACT_SAMPLE_SIZE}")
    floor = required_sample_size(true_count, expected_policy_detectable_corruption,
                                 expected_policy_confidence)
    expected_policy = {
        "detectable_corruption": expected_policy_detectable_corruption,
        "confidence": [expected_policy_confidence.numerator,
                       expected_policy_confidence.denominator],
        "sample_floor": floor,
    }
    _require(type(record["policy"]) is dict
             and canonical(record["policy"]) == canonical(expected_policy),
             "record policy disagrees with the externally frozen policy")
    _require(sample_size >= floor, "record sample size is below the frozen policy floor")

    nonce_hex = record["owner_nonce_hex"]
    _require(type(nonce_hex) is str and len(nonce_hex) % 2 == 0
             and all(c in "0123456789abcdef" for c in nonce_hex),
             "record owner_nonce_hex must be lowercase hex of even length")
    nonce = bytes.fromhex(nonce_hex)
    _require(_sha(nonce).hex() == record["owner_nonce_sha256"],
             "record nonce disagrees with its own hash")

    mismatched = record["mismatched_indices"]
    _require(type(mismatched) is list, "mismatched_indices must be a list")
    # `list()` is lenient: a dict would silently become its key list.  Guard
    # the type explicitly rather than relying on the cast.
    challenged_claim = record["challenged_indices"]
    _require(type(challenged_claim) is list, "challenged_indices must be a list")
    _require(type(record["authority_id"]) is str and record["authority_id"],
             "authority_id must be a non-empty string")
    _require(set(mismatched) <= set(challenged_claim),
             "mismatched_indices must be a subset of challenged_indices")
    # Re-derive the published guarantee rather than reading it.
    _require(record["guarantee"] == guarantee_for(true_count, sample_size),
             "record guarantee does not follow from its grid size and sample size")
    # A record cannot both claim success and carry mismatches.  r3 never
    # looked, so a hand-edited status audited clean.
    _require(record["status"] == ("verified" if not mismatched else "mismatch"),
             "record status disagrees with its own mismatch list")

    expected = derive_challenge(true_root, nonce, sample_size, true_count)
    return expected == challenged_claim


def verification_limits() -> dict:
    """What a passing verification does and does not establish.

    Kept in code so it cannot drift from the mechanism.  The adversarial entries
    come from two rounds of independent review and are why this list is longer
    than the establishes list.
    """
    return {
        "establishes": [
            "the results SUPPLIED as recomputed for every challenged grid "
            "point matched the committed result bit-for-bit",
            "the committed leaf list reproduces both the committed root and the "
            "root the owner pinned before drawing the nonce",
            "the commitment covers exactly the expected number of grid points, "
            "the committed coordinates are distinct, and each challenged index "
            "names a specific committed coordinate",
            "the reported guarantee follows from the grid size and sample size "
            "alone and was not supplied by the caller",
            "the reported guarantee is PER INSTANCE, and the family-wide "
            "figure across all five instances is stated separately",
        ],
        "does_not_establish": [
            "the identity of the image, host or hardware that produced the run "
            "-- this mechanism deliberately replaces that question rather than "
            "answering it",
            "that the committed root was fixed before the nonce was drawn. No "
            "code can show this. A producer may compute many campaigns "
            "speculatively and, on learning the nonce, present whichever "
            "pre-computed commitment the sample misses. Only timestamped "
            "publication pinned before the nonce exists rules this out, and "
            "that is a procedural control",
            "anything against an owner who draws the nonce dishonestly. An "
            "owner wanting to pass a run they know to be corrupt can redraw "
            "nonces until the sample misses it; for one bad point in 680,943 "
            "with a sample of 2000, a few hundred draws suffice. Only a "
            "randomness source the owner also cannot steer removes this",
            "the stated probability if a failed campaign is retried; repeated "
            "attempts are a multiple-testing problem",
            "that the committed coordinates are THE campaign's grid. The "
            "coordinate list comes from the producer; only the expected count "
            "and the pinned root are external anchors",
            "correctness of any unchallenged grid point, beyond the "
            "probabilistic bound, or of a corruption smaller than the sample "
            "can detect",
            "that leaf i corresponds to coordinate i at UNCHALLENGED i; the two "
            "roots are coupled only where sampled",
            "that the frozen authority named by authority_id is itself a "
            "correct implementation of the intended science",
            "anything at all if the verifier's own hardware is compromised",
            "that any recomputation actually happened. This module compares "
            "the values it is handed; it cannot observe where they came from. "
            "A caller passing the producer's own results back in gets a clean "
            "record having computed nothing, and authority_id is a free-form "
            "label with no registry behind it. Independent recomputation is a "
            "procedural obligation on the verifier",
            "that a record's results are correct. recheck_record audits the "
            "challenge and re-derives the published guarantee, but it cannot "
            "check the results. A third party wanting assurance about those "
            "must recompute the sample itself",
            "ANY exact predicate. The protocol adjudicates exact predicates "
            "per instance and then all_five / any_one / count_of_five across "
            "five. A SINGLE erroneous grid point can flip an existential or "
            "universal predicate, and for one corrupted point in 680,943 a "
            "sample of 2,000 detects it with probability 0.294%; reaching 99% "
            "would need 674,134 points, which is effectively exhaustive. "
            "Sampled verification is a check against WIDESPREAD numerical "
            "corruption at a declared statistical scale and is not evidence "
            "for any exact conclusion",
            "the authorship of a record. A verification record is a bearer "
            "document its own issuer can mint from scratch: an owner may pick "
            "a nonce, derive the indices, and emit a complete verified record "
            "without doing any work. Nothing binds a record to an author, and "
            "this module ships no function that would detect it",
        ],
        "assumes": [
            "the commitment was published and timestamped, and its root pinned, "
            "before the nonce was drawn",
            "the nonce is unpredictable to the producer AND not freely "
            "re-drawable by the owner",
            "recomputation is bit-reproducible: the same frozen authority, the "
            "same float contraction settings, the same reduction order",
        ],
    }

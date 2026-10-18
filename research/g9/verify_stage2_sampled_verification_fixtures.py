#!/usr/bin/env python3
"""Adversarial fixtures for the Stage-2 sampled verification mechanism (v3).

Synthetic only: every coordinate and result here is invented.  No Stage-2
value, instance, coefficient, candidate or scientific record is read or
written.

Tests named `test_r1_*` and `test_r2_*` pin defects found by independent review
of revisions 1 and 2, so a regression re-opens a known hole rather than merely
failing an abstract assertion.
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import hashlib
import os
import struct
import unittest
from collections import OrderedDict, namedtuple
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stage2_sampled_verification as sv

try:
    import numpy as _np
except Exception:
    _np = None

NONCE_A = bytes(range(32))
NONCE_B = bytes(range(1, 33))
AUTHORITY = "src/g4/energy.py@frozen"
# A policy loose enough that the small synthetic grids here clear the floor.
POLICY_C, POLICY_CONF = 400, Fraction(1, 2)


def synthetic_entries(count: int, seed: int = 0) -> list:
    entries = []
    for i in range(count):
        digest = hashlib.sha256(f"{seed}:{i}".encode("ascii")).digest()
        energy = struct.unpack("<d", digest[:8])[0]
        if energy != energy or energy in (float("inf"), float("-inf")):
            energy = float(i)
        entries.append((
            {"i": i % 61, "j": (i // 61) % 61, "k": (i // 3721) % 61, "r": "1"},
            {"min_energy": sv.encode_float(energy), "argmin": i, "ties": i % 3},
        ))
    return entries


class TestEncoding(unittest.TestCase):

    def test_float_roundtrip_is_exact(self):
        for value in (0.0, 1.0, -1.5, 2.0 ** -1074, 1.7976931348623157e308, -3.25):
            self.assertEqual(sv.decode_float(sv.encode_float(value)), value)

    def test_negative_zero_bits_preserved(self):
        self.assertNotEqual(sv.encode_float(-0.0), sv.encode_float(0.0))
        self.assertEqual(sv.encode_float(-0.0), struct.pack("<d", -0.0).hex())
        self.assertNotEqual(sv.leaf_hash([0], sv.encode_float(-0.0)),
                            sv.leaf_hash([0], sv.encode_float(0.0)))

    def test_nonfinite_and_nonfloat_refused(self):
        for bad in (float("nan"), float("inf"), float("-inf"), 1, "1.0", None, True):
            with self.assertRaises(sv.VerificationError):
                sv.encode_float(bad)

    def test_decode_rejects_malformed(self):
        for bad in ("", "xx", "0" * 63, "0" * 65, "A" * 16, 0):
            with self.assertRaises(sv.VerificationError):
                sv.decode_float(bad)

    # -- r1 defect: encode_float was never reached on the commitment path.
    def test_r1_raw_float_is_structurally_refused(self):
        for payload in (1.5, {"v": 1.5}, {"a": {"b": [1, 2, 3.5]}}, [0.0],
                        {"nested": [{"deep": -0.0}]}):
            with self.assertRaises(sv.VerificationError) as caught:
                sv.canonical(payload)
            self.assertIn("encode_float", str(caught.exception))

    # -- r2 defect: the denylist `type(x) is float` admitted float SUBCLASSES,
    # which json.dumps then encodes by repr -- the exact bypassed path.
    @unittest.skipIf(_np is None, "numpy not available")
    def test_r2_numpy_float_subclass_refused(self):
        self.assertTrue(isinstance(_np.float64(1.5), float))
        self.assertIsNot(type(_np.float64(1.5)), float)
        for payload in (_np.float64(1.5), {"v": _np.float64(1.5)},
                        {"a": [_np.float64(2.5)]}):
            with self.assertRaises(sv.VerificationError):
                sv.canonical(payload)

    @unittest.skipIf(_np is None, "numpy not available")
    def test_r2_numpy_float_can_still_be_encoded_deliberately(self):
        # Refusing it unencoded must not make it impossible to commit.
        self.assertEqual(sv.encode_float(_np.float64(1.5)), sv.encode_float(1.5))

    # -- r2 defect: container subclasses (namedtuple) slipped the denylist.
    def test_r2_container_subclasses_refused(self):
        Point = namedtuple("Point", "a b")
        for payload in (Point(1, 2), {"p": Point(1, 2)}, OrderedDict(a=1)):
            with self.assertRaises(sv.VerificationError):
                sv.canonical(payload)

    def test_r2_tuple_refused_restoring_injectivity(self):
        # json renders a tuple and a list identically; admitting both would let
        # two distinct structures share one canonical encoding.
        with self.assertRaises(sv.VerificationError):
            sv.canonical((1, 2))
        self.assertTrue(sv.canonical([1, 2]))

    def test_r2_exotic_numeric_types_refused(self):
        class HasFloat:
            def __float__(self):
                return 1.5
        for payload in (Decimal("1.5"), complex(1, 2), Fraction(1, 2), HasFloat(), b"x"):
            with self.assertRaises(sv.VerificationError):
                sv.canonical(payload)

    # -- r2 defect: unbounded recursion raised RecursionError, a RuntimeError,
    # escaping the module's typed contract on attacker-supplied data.
    def test_r2_deep_nesting_refused_typed(self):
        deep = payload = []
        for _ in range(400):
            nxt = []
            payload.append(nxt)
            payload = nxt
        with self.assertRaises(sv.VerificationError) as caught:
            sv.canonical(deep)
        self.assertIn("deeply", str(caught.exception))

    def test_allowlisted_types_accepted(self):
        self.assertTrue(sv.canonical({"flag": True, "n": 3, "s": "x",
                                      "none": None, "l": [1, {"z": 2}]}))

    def test_leaf_hash_refuses_raw_floats_both_sides(self):
        with self.assertRaises(sv.VerificationError):
            sv.leaf_hash({"i": 0}, {"energy": 1.5})
        with self.assertRaises(sv.VerificationError):
            sv.leaf_hash({"i": 1.5}, {"energy": sv.encode_float(1.5)})


class TestLeafAndTree(unittest.TestCase):

    def test_length_prefixing_prevents_concatenation_collision(self):
        self.assertNotEqual(sv.leaf_hash({"a": "xy"}, {"b": "z"}),
                            sv.leaf_hash({"a": "x"}, {"b": "yz"}))

    def test_leaf_and_node_domains_separated(self):
        leaf = sv.leaf_hash({"i": 0}, {"v": 1})
        self.assertNotEqual(leaf, hashlib.sha256(sv.NODE_PREFIX + leaf + leaf).digest())

    def test_rfc6962_resists_duplicate_last_leaf_attack(self):
        leaves3 = [sv.leaf_hash({"i": i}, {"v": i}) for i in range(3)]
        self.assertNotEqual(sv.merkle_root(leaves3), sv.merkle_root(leaves3 + [leaves3[-1]]))

    def test_root_is_order_sensitive(self):
        leaves = [sv.leaf_hash({"i": i}, {"v": i}) for i in range(8)]
        swapped = leaves[:]
        swapped[0], swapped[1] = swapped[1], swapped[0]
        self.assertNotEqual(sv.merkle_root(leaves), sv.merkle_root(swapped))

    def test_single_leaf_root_is_the_leaf(self):
        leaf = sv.leaf_hash({"i": 0}, {"v": 0})
        self.assertEqual(sv.merkle_root([leaf]), leaf)

    def test_iterative_tree_handles_campaign_scale(self):
        leaves = [bytes([i % 256]) * 32 for i in range(200000)]
        self.assertEqual(len(sv.merkle_root(leaves)), 32)

    def test_iterative_matches_reference_recursive_tree(self):
        def reference(items):
            if not items:
                return hashlib.sha256(b"").digest()
            if len(items) == 1:
                return items[0]
            k = 1
            while k << 1 < len(items):
                k <<= 1
            return hashlib.sha256(sv.NODE_PREFIX + reference(items[:k])
                                  + reference(items[k:])).digest()
        for n in (1, 2, 3, 4, 5, 7, 8, 9, 13, 16, 17, 31, 64, 100, 129):
            leaves = [sv.leaf_hash({"i": i}, {"v": i}) for i in range(n)]
            self.assertEqual(sv.merkle_root(leaves), reference(leaves), f"n={n}")

    def test_malformed_leaves_refused(self):
        for bad in ([b"short"], [b"x" * 33], ["not bytes"]):
            with self.assertRaises(sv.VerificationError):
                sv.merkle_root(bad)


class TestCommitmentCompleteness(unittest.TestCase):

    # -- r1 defect: a producer could commit a convenient subset.
    def test_r1_subset_commitment_refused(self):
        entries = synthetic_entries(100)
        with self.assertRaises(sv.VerificationError) as caught:
            sv.build_commitment(entries[:1], 100)
        self.assertIn("expected 100", str(caught.exception))

    def test_expected_count_validated(self):
        entries = synthetic_entries(10)
        for bad in (0, -1, "10", None):
            with self.assertRaises(sv.VerificationError):
                sv.build_commitment(entries, bad)

    def test_duplicate_coordinates_refused(self):
        with self.assertRaises(sv.VerificationError):
            sv.build_commitment([({"i": 1}, {"v": 1}), ({"i": 1}, {"v": 2})], 2)

    def test_commitment_deterministic_and_shaped(self):
        entries = synthetic_entries(37)
        a = sv.build_commitment(entries, 37)
        self.assertEqual(a, sv.build_commitment(entries, 37))
        self.assertEqual(len(a["merkle_root"]), 64)
        self.assertEqual(len(a["coordinate_root"]), 64)

    def test_any_single_result_change_moves_the_root(self):
        entries = synthetic_entries(64)
        base = sv.build_commitment(entries, 64)["merkle_root"]
        for victim in (0, 17, 63):
            mutated = list(entries)
            coords, result = mutated[victim]
            altered = dict(result)
            altered["argmin"] += 1
            mutated[victim] = (coords, altered)
            self.assertNotEqual(sv.build_commitment(mutated, 64)["merkle_root"], base)

    # -- r1 defect: coordinates were hashed away, making anti-reordering circular.
    def test_r1_coordinate_root_binds_order(self):
        entries = synthetic_entries(32)
        base = sv.build_commitment(entries, 32)
        swapped = list(entries)
        swapped[0], swapped[1] = swapped[1], swapped[0]
        self.assertNotEqual(sv.build_commitment(swapped, 32)["coordinate_root"],
                            base["coordinate_root"])


class TestChallenge(unittest.TestCase):

    def setUp(self):
        self.commitment = sv.build_commitment(synthetic_entries(5000), 5000)
        self.root = self.commitment["merkle_root"]

    def test_deterministic(self):
        self.assertEqual(sv.derive_challenge(self.root, NONCE_A, 50, 5000),
                         sv.derive_challenge(self.root, NONCE_A, 50, 5000))

    def test_distinct_in_range_sorted(self):
        sample = sv.derive_challenge(self.root, NONCE_A, 200, 5000)
        self.assertEqual(len(set(sample)), 200)
        self.assertEqual(sample, sorted(sample))
        self.assertTrue(all(0 <= i < 5000 for i in sample))

    def test_nonce_and_root_both_change_the_sample(self):
        other = sv.build_commitment(synthetic_entries(5000, seed=1), 5000)["merkle_root"]
        base = sv.derive_challenge(self.root, NONCE_A, 100, 5000)
        self.assertNotEqual(base, sv.derive_challenge(self.root, NONCE_B, 100, 5000))
        self.assertNotEqual(base, sv.derive_challenge(other, NONCE_A, 100, 5000))

    # -- r1 defect: unbound sample size let a challenge be reinterpreted smaller.
    def test_r1_sample_size_bound_into_seed(self):
        small = sv.derive_challenge(self.root, NONCE_A, 20, 5000)
        large = sv.derive_challenge(self.root, NONCE_A, 40, 5000)
        self.assertNotEqual(large[:20], small)

    def test_bad_arguments_refused(self):
        for args in ((self.root, b"short", 10, 5000), (self.root, NONCE_A, 5001, 5000),
                     (self.root, NONCE_A, 0, 5000), ("zz" * 32, NONCE_A, 10, 5000),
                     (self.root[:63], NONCE_A, 10, 5000), (self.root, bytes(65), 10, 5000)):
            with self.assertRaises(sv.VerificationError):
                sv.derive_challenge(*args)

    def test_selection_not_obviously_biased(self):
        first, total = 0, 0
        for t in range(60):
            nonce = hashlib.sha256(str(t).encode()).digest()
            for index in sv.derive_challenge(self.root, nonce, 40, 5000):
                total += 1
                first += index < 2500
        self.assertTrue(0.42 < first / total < 0.58, f"ratio {first/total}")


class TestDetectionMath(unittest.TestCase):

    def test_known_small_cases_exact(self):
        self.assertEqual(sv.detection_probability(10, 1, 1), Fraction(1, 10))
        self.assertEqual(sv.detection_probability(4, 2, 2), Fraction(5, 6))

    def test_monotonic_in_sample_size(self):
        previous = Fraction(0)
        for k in range(0, 40):
            current = sv.detection_probability(1000, 10, k)
            self.assertGreaterEqual(current, previous)
            previous = current

    def test_required_sample_size_is_minimal(self):
        n, c, target = 680943, 6809, Fraction(99, 100)
        k = sv.required_sample_size(n, c, target)
        self.assertGreaterEqual(sv.detection_probability(n, c, k), target)
        self.assertLess(sv.detection_probability(n, c, k - 1), target)

    def test_not_the_common_approximation(self):
        self.assertNotEqual(sv.detection_probability(1000, 100, 50),
                            Fraction(1) - Fraction(9, 10) ** 50)

    # -- r1 defect: a target near 1 lost its complement and crashed untyped.
    def test_r1_extreme_target_does_not_crash_untyped(self):
        for target in (Fraction(2 ** 54 - 1, 2 ** 54), Fraction(2 ** 64 - 1, 2 ** 64)):
            k = sv.required_sample_size(1000, 500, target)
            self.assertIsInstance(k, int)

    # -- r2 defect: exact perms stalled for minutes at huge sample sizes.
    def test_r2_oversized_sample_refused_not_stalled(self):
        with self.assertRaises(sv.VerificationError) as caught:
            sv.detection_probability(680943, 1, 680941)
        self.assertIn("exact path", str(caught.exception))

    # -- r2 defect: the caller supplied the corruption size and so chose the
    # headline number.  The guarantee must be DERIVED instead.
    def test_r2_minimum_detectable_corruption_is_derived_and_monotone(self):
        n = 680943
        previous = None
        for k in (100, 500, 1000, 2000):
            c = sv.minimum_detectable_corruption(n, k, Fraction(99, 100))
            self.assertGreaterEqual(sv.detection_probability(n, c, k), Fraction(99, 100))
            self.assertLess(sv.detection_probability(n, c - 1, k), Fraction(99, 100))
            if previous is not None:
                self.assertLess(c, previous)   # bigger sample detects smaller corruption
            previous = c

    def test_r2_degenerate_certainty_cannot_be_claimed(self):
        # The old free parameter let c=n-1 trip the short circuit and print 1/1.
        n, k = 680943, 2000
        c = sv.minimum_detectable_corruption(n, k, Fraction(99, 100))
        self.assertLess(c, n // 100, "derived corruption should be a small fraction")

    def test_bad_arguments_refused(self):
        with self.assertRaises(sv.VerificationError):
            sv.detection_probability(10, 11, 1)
        with self.assertRaises(sv.VerificationError):
            sv.required_sample_size(100, 1, Fraction(1))
        with self.assertRaises(sv.VerificationError):
            sv.minimum_detectable_corruption(100, 0, Fraction(1, 2))


class TestVerification(unittest.TestCase):

    N = 1000

    def setUp(self):
        self.entries = synthetic_entries(self.N)
        self.commitment = sv.build_commitment(self.entries, self.N)
        self.root = self.commitment["merkle_root"]
        self.k = 40
        self.challenged = sv.derive_challenge(self.root, NONCE_A, self.k, self.N)

    def honest(self):
        return {i: self.entries[i] for i in self.challenged}

    def call(self, **over):
        kwargs = dict(commitment=self.commitment, pinned_merkle_root=self.root,
                      owner_nonce=NONCE_A, sample_size=self.k,
                      expected_grid_point_count=self.N, recomputed=self.honest(),
                      authority_id=AUTHORITY,
                      policy_detectable_corruption=POLICY_C,
                      policy_confidence=POLICY_CONF)
        kwargs.update(over)
        return sv.verify_sample(**kwargs)

    def test_honest_run_verifies(self):
        out = self.call()
        self.assertEqual(out["status"], "verified")
        self.assertEqual(out["mismatched_indices"], [])

    # -- r2 defect: a mismatch was RETURNED, so a natural caller ignored it.
    def test_r2_mismatch_raises_rather_than_returning(self):
        recomputed = self.honest()
        victim = self.challenged[0]
        coords, result = recomputed[victim]
        altered = dict(result)
        altered["argmin"] += 1
        recomputed[victim] = (coords, altered)
        with self.assertRaises(sv.VerificationError) as caught:
            self.call(recomputed=recomputed)
        self.assertEqual(caught.exception.record["status"], "mismatch")
        self.assertEqual(caught.exception.record["mismatched_indices"], [victim])

    def test_one_ulp_energy_difference_caught(self):
        recomputed = self.honest()
        victim = self.challenged[1]
        bits = struct.unpack("<Q", bytes.fromhex(recomputed[victim][1]["min_energy"]))[0] ^ 1
        nudged = struct.unpack("<d", struct.pack("<Q", bits))[0]
        if nudged != nudged or nudged in (float("inf"), float("-inf")):
            nudged = sv.decode_float(recomputed[victim][1]["min_energy"]) + 1.0
        coords, result = recomputed[victim]
        altered = dict(result)
        altered["min_energy"] = sv.encode_float(nudged)
        recomputed[victim] = (coords, altered)
        with self.assertRaises(sv.VerificationError):
            self.call(recomputed=recomputed)

    # -- r2 defect: verify_sample trusted build_commitment's distinctness check,
    # but a producer need never have called build_commitment.
    def test_r2_duplicate_committed_coordinates_refused_at_verification(self):
        one = synthetic_entries(1)[0]
        forged_entries = [(one[0], one[1])] * self.N
        leaves = [sv.leaf_hash(one[0], one[1]) for _ in range(self.N)]
        coords = [one[0] for _ in range(self.N)]
        forged = {
            "schema": sv.SCHEMA,
            "grid_point_count": self.N,
            "merkle_root": sv.merkle_root(leaves).hex(),
            "coordinate_root": sv.coordinate_root(coords).hex(),
            "leaf_hashes": [leaf.hex() for leaf in leaves],
            "coordinates": coords,
        }
        with self.assertRaises(sv.VerificationError) as caught:
            sv.verify_sample(commitment=forged, pinned_merkle_root=forged["merkle_root"],
                             owner_nonce=NONCE_A, sample_size=self.k,
                             expected_grid_point_count=self.N, recomputed={},
                             authority_id=AUTHORITY,
                             policy_detectable_corruption=POLICY_C,
                             policy_confidence=POLICY_CONF)
        self.assertIn("duplicate", str(caught.exception).lower())

    # -- r2 defect: the record must let a third party re-derive the challenge.
    def test_r2_record_carries_nonce_and_rechecks(self):
        out = self.call()
        self.assertIn("owner_nonce_hex", out)
        self.assertEqual(bytes.fromhex(out["owner_nonce_hex"]), NONCE_A)
        self.assertTrue(sv.recheck_record(out, self.commitment, expected_policy_detectable_corruption=POLICY_C, expected_policy_confidence=POLICY_CONF))

    def test_r2_recheck_detects_a_doctored_index_list(self):
        out = dict(self.call())
        out["challenged_indices"] = list(out["challenged_indices"])[:-1]
        self.assertFalse(sv.recheck_record(out, self.commitment, expected_policy_detectable_corruption=POLICY_C, expected_policy_confidence=POLICY_CONF))

    # -- r2 defect: the record named no authority, so two verifiers running
    # different implementations emitted indistinguishable records.
    def test_r2_record_names_the_authority(self):
        self.assertEqual(self.call()["authority_id"], AUTHORITY)
        for bad in ("", None, 5, "x" * 300):
            with self.assertRaises(sv.VerificationError):
                self.call(authority_id=bad)

    def test_r2_guarantee_is_derived_from_sample_size(self):
        out = self.call()
        self.assertEqual(out["guarantee"]["scope"],
                         "per_instance_only_not_family_wide")
        for key, entry in out["guarantee"].items():
            if key == "scope":
                continue
            smallest = entry["minimum_detectable_corrupted_points"]
            self.assertEqual(entry["as_fraction_of_grid"], [smallest, self.N])
            num, den = (int(x) for x in key.split("/"))
            self.assertGreaterEqual(
                sv.detection_probability(self.N, smallest, self.k), Fraction(num, den))

    def test_r1_truncated_commitment_refused_at_verification(self):
        small_entries = synthetic_entries(1)
        small = sv.build_commitment(small_entries, 1)
        with self.assertRaises(sv.VerificationError):
            sv.verify_sample(commitment=small, pinned_merkle_root=small["merkle_root"],
                             owner_nonce=NONCE_A, sample_size=1,
                             expected_grid_point_count=self.N,
                             recomputed={0: small_entries[0]}, authority_id=AUTHORITY,
                             policy_detectable_corruption=POLICY_C,
                             policy_confidence=POLICY_CONF)

    def test_pinned_root_mismatch_refused(self):
        with self.assertRaises(sv.VerificationError):
            self.call(pinned_merkle_root="0" * 64)

    def test_tampered_or_reordered_leaf_list_refused(self):
        for mutate in (lambda L: L.__setitem__(5, "0" * 64),
                       lambda L: L.__setitem__(slice(0, 2), [L[1], L[0]])):
            broken = dict(self.commitment)
            leaves = list(broken["leaf_hashes"])
            mutate(leaves)
            broken["leaf_hashes"] = leaves
            with self.assertRaises(sv.VerificationError):
                self.call(commitment=broken)

    def test_r1_reordered_or_wrong_coordinates_refused(self):
        broken = dict(self.commitment)
        coords = list(broken["coordinates"])
        coords[0], coords[1] = coords[1], coords[0]
        broken["coordinates"] = coords
        with self.assertRaises(sv.VerificationError):
            self.call(commitment=broken)

        recomputed = self.honest()
        victim = self.challenged[0]
        recomputed[victim] = ({"i": 999, "j": 999, "k": 999, "r": "9"}, recomputed[victim][1])
        with self.assertRaises(sv.VerificationError) as caught:
            self.call(recomputed=recomputed)
        self.assertIn("coordinates", str(caught.exception))

    def test_missing_or_extra_index_refused(self):
        short = self.honest()
        short.pop(self.challenged[0])
        with self.assertRaises(sv.VerificationError):
            self.call(recomputed=short)
        extra = self.honest()
        spare = next(i for i in range(self.N) if i not in self.challenged)
        extra[spare] = self.entries[spare]
        with self.assertRaises(sv.VerificationError):
            self.call(recomputed=extra)

    def test_wrong_nonce_changes_challenge_so_coverage_fails(self):
        with self.assertRaises(sv.VerificationError):
            self.call(owner_nonce=NONCE_B)


class TestR3Defects(unittest.TestCase):
    """Round-three findings: the audit function was itself forgeable, and the
    sample-size helper silently missed its own target."""

    N = 1000

    def setUp(self):
        self.entries = synthetic_entries(self.N)
        self.commitment = sv.build_commitment(self.entries, self.N)
        self.root = self.commitment["merkle_root"]
        self.k = 40
        self.challenged = sv.derive_challenge(self.root, NONCE_A, self.k, self.N)
        self.record = sv.verify_sample(
            commitment=self.commitment, pinned_merkle_root=self.root,
            owner_nonce=NONCE_A, sample_size=self.k,
            expected_grid_point_count=self.N,
            recomputed={i: self.entries[i] for i in self.challenged},
            authority_id=AUTHORITY, policy_detectable_corruption=POLICY_C,
            policy_confidence=POLICY_CONF)

    # r3: recheck_record took root/sample_size/grid_point_count from the
    # UNTRUSTED record. A forged record with the real commitment digest but a
    # fabricated root and a 1-point sample audited clean.
    def test_r3_forged_record_with_fake_root_refused(self):
        forged = dict(self.record)
        forged["merkle_root"] = "a" * 64
        with self.assertRaises(sv.VerificationError) as caught:
            sv.recheck_record(forged, self.commitment, expected_policy_detectable_corruption=POLICY_C, expected_policy_confidence=POLICY_CONF)
        self.assertIn("root", str(caught.exception))

    def test_r3_forged_record_shrinking_the_sample_refused(self):
        forged = dict(self.record)
        forged["sample_size"] = 1
        forged["grid_point_count"] = 1
        forged["challenged_indices"] = [0]
        with self.assertRaises(sv.VerificationError) as caught:
            sv.recheck_record(forged, self.commitment, expected_policy_detectable_corruption=POLICY_C, expected_policy_confidence=POLICY_CONF)
        self.assertIn("grid size", str(caught.exception))

    # r3: recheck_record never looked at status or mismatched_indices, so a
    # hand-edited "verified" on a corrupted run audited clean.
    def test_r3_hand_edited_status_refused(self):
        forged = dict(self.record)
        forged["mismatched_indices"] = [self.challenged[0]]
        forged["status"] = "verified"
        with self.assertRaises(sv.VerificationError) as caught:
            sv.recheck_record(forged, self.commitment, expected_policy_detectable_corruption=POLICY_C, expected_policy_confidence=POLICY_CONF)
        self.assertIn("status", str(caught.exception))

    def test_r3_record_missing_fields_stays_typed(self):
        for key in ("commitment_digest", "owner_nonce_sha256", "status",
                    "mismatched_indices"):
            forged = dict(self.record)
            forged.pop(key)
            with self.assertRaises(sv.VerificationError):
                sv.recheck_record(forged, self.commitment, expected_policy_detectable_corruption=POLICY_C, expected_policy_confidence=POLICY_CONF)

    def test_r3_malformed_nonce_hex_stays_typed(self):
        for bad in ("zz" * 32, "abc", 5, None):
            forged = dict(self.record)
            forged["owner_nonce_hex"] = bad
            with self.assertRaises(sv.VerificationError):
                sv.recheck_record(forged, self.commitment, expected_policy_detectable_corruption=POLICY_C, expected_policy_confidence=POLICY_CONF)

    def test_r3_record_for_another_commitment_refused(self):
        other = sv.build_commitment(synthetic_entries(self.N, seed=7), self.N)
        with self.assertRaises(sv.VerificationError):
            sv.recheck_record(self.record, other, expected_policy_detectable_corruption=POLICY_C, expected_policy_confidence=POLICY_CONF)

    def test_honest_record_still_rechecks(self):
        self.assertTrue(sv.recheck_record(self.record, self.commitment, expected_policy_detectable_corruption=POLICY_C, expected_policy_confidence=POLICY_CONF))

    # r3: required_sample_size returned the capped value when the honest answer
    # exceeded it, silently failing its own contract.
    def test_r3_unreachable_target_refused_not_under_reported(self):
        with self.assertRaises(sv.VerificationError) as caught:
            sv.required_sample_size(680943, 1, Fraction(999, 1000))
        self.assertIn("budget", str(caught.exception))

    def test_r3_reachable_target_still_exact(self):
        n, c, t = 680943, 6809, Fraction(99, 100)
        k = sv.required_sample_size(n, c, t)
        self.assertGreaterEqual(sv.detection_probability(n, c, k), t)
        self.assertLess(sv.detection_probability(n, c, k - 1), t)

    # r3: the oversized-sample refusal arrived only at the reporting step.
    def test_r3_oversized_sample_refused_at_entry(self):
        with self.assertRaises(sv.VerificationError) as caught:
            sv.verify_sample(commitment=self.commitment, pinned_merkle_root=self.root,
                             owner_nonce=NONCE_A, sample_size=sv.MAX_EXACT_SAMPLE_SIZE + 1,
                             expected_grid_point_count=self.N, recomputed={},
                             authority_id=AUTHORITY,
                             policy_detectable_corruption=POLICY_C,
                             policy_confidence=POLICY_CONF)
        self.assertIn("sample_size must be in", str(caught.exception))

    # r3: json.loads gives string keys, which failed as an opaque coverage error.
    def test_r3_string_keys_get_an_actionable_message(self):
        stringly = {str(i): self.entries[i] for i in self.challenged}
        with self.assertRaises(sv.VerificationError) as caught:
            sv.verify_sample(commitment=self.commitment, pinned_merkle_root=self.root,
                             owner_nonce=NONCE_A, sample_size=self.k,
                             expected_grid_point_count=self.N, recomputed=stringly,
                             authority_id=AUTHORITY,
                             policy_detectable_corruption=POLICY_C,
                             policy_confidence=POLICY_CONF)
        self.assertIn("json.loads", str(caught.exception))

    def test_r3_minimum_detectable_corruption_exact_after_float_screen(self):
        n, t = 680943, Fraction(99, 100)
        for k in (100, 2000, 20000):
            c = sv.minimum_detectable_corruption(n, k, t)
            self.assertGreaterEqual(sv.detection_probability(n, c, k), t)
            self.assertLess(sv.detection_probability(n, c - 1, k), t)


class TestFamilyScope(unittest.TestCase):
    """A per-instance guarantee is not a family guarantee. The protocol
    adjudicates five instances, so reporting one as the other overstates."""

    def test_family_probability_is_strictly_below_per_instance(self):
        per = Fraction(99, 100)
        fam = sv.family_detection_probability(per, 5)
        self.assertEqual(fam, Fraction(95, 100))
        self.assertLess(fam, per)
        self.assertAlmostEqual(float(fam), 0.95, places=9)

    def test_guarantee_labels_its_scope_and_reports_family(self):
        g = sv.guarantee_for(680943, 2000)
        self.assertEqual(g["scope"], "per_instance_only_not_family_wide")
        num, den = g["99/100"]["family_all_five_caught_union_bound_lower_bound"]
        self.assertEqual(Fraction(num, den), Fraction(95, 100))

    def test_instance_count_matches_the_protocol(self):
        self.assertEqual(sv.STAGE2_INSTANCE_COUNT, 5)

    def test_bad_arguments_refused(self):
        for args in ((Fraction(3, 2), 5), (Fraction(1, 2), 0), (0.99, 5)):
            with self.assertRaises(sv.VerificationError):
                sv.family_detection_probability(*args)

    # The reviewer's point 2: a single bad point is undetectable at any affordable
    # sample size. Pin the arithmetic so the claim cannot silently drift.
    def test_single_point_corruption_is_effectively_undetectable(self):
        n = 680943
        self.assertAlmostEqual(
            float(sv.detection_probability(n, 1, 2000)) * 100, 0.2937, places=3)
        # For c=1 the exact detection collapses to k/n, so the 99% threshold
        # can be pinned in closed form past the exact path's sample-size cap.
        self.assertEqual(sv.detection_probability(n, 1, 1000), Fraction(1000, n))
        self.assertGreaterEqual(Fraction(674134, n), Fraction(99, 100))
        self.assertLess(Fraction(674133, n), Fraction(99, 100))


class TestR4Defects(unittest.TestCase):
    """Round-four finding: the r2 defect had MOVED, not died. The caller no
    longer picks the corruption size, but it picked the sample size freely and
    the audit never re-derived the published guarantee."""

    N = 1000

    def setUp(self):
        self.entries = synthetic_entries(self.N)
        self.commitment = sv.build_commitment(self.entries, self.N)
        self.root = self.commitment["merkle_root"]
        self.k = 40
        self.challenged = sv.derive_challenge(self.root, NONCE_A, self.k, self.N)
        self.record = sv.verify_sample(
            commitment=self.commitment, pinned_merkle_root=self.root,
            owner_nonce=NONCE_A, sample_size=self.k,
            expected_grid_point_count=self.N,
            recomputed={i: self.entries[i] for i in self.challenged},
            authority_id=AUTHORITY, policy_detectable_corruption=POLICY_C,
            policy_confidence=POLICY_CONF)

    def test_forged_policy_and_coordinate_root_refused(self):
        for key, value in (("policy", {"detectable_corruption": 1,
                                      "confidence": [99, 100], "sample_floor": 990}),
                           ("coordinate_root", "0" * 64)):
            forged = dict(self.record)
            forged[key] = value
            with self.assertRaises(sv.VerificationError):
                sv.recheck_record(forged, self.commitment,
                                  expected_policy_detectable_corruption=POLICY_C,
                                  expected_policy_confidence=POLICY_CONF)

    def test_external_policy_not_record_selected(self):
        with self.assertRaises(sv.VerificationError):
            sv.recheck_record(self.record, self.commitment,
                              expected_policy_detectable_corruption=1,
                              expected_policy_confidence=Fraction(99, 100))

    def test_missing_coordinate_root_refused(self):
        forged = dict(self.record)
        del forged["coordinate_root"]
        with self.assertRaises(sv.VerificationError):
            sv.recheck_record(forged, self.commitment,
                              expected_policy_detectable_corruption=POLICY_C,
                              expected_policy_confidence=POLICY_CONF)

    # r4: a forged guarantee block audited clean.
    def test_r4_forged_guarantee_refused(self):
        forged = dict(self.record)
        forged["guarantee"] = {"999/1000": {
            "minimum_detectable_corrupted_points": 1,
            "as_fraction_of_grid": [1, self.N]}}
        with self.assertRaises(sv.VerificationError) as caught:
            sv.recheck_record(forged, self.commitment, expected_policy_detectable_corruption=POLICY_C, expected_policy_confidence=POLICY_CONF)
        self.assertIn("guarantee", str(caught.exception))

    def test_r4_guarantee_is_rederived_not_read(self):
        self.assertEqual(self.record["guarantee"],
                         sv.guarantee_for(self.N, self.k))
        self.assertTrue(sv.recheck_record(self.record, self.commitment, expected_policy_detectable_corruption=POLICY_C, expected_policy_confidence=POLICY_CONF))

    # r4: nothing imposed a floor on the sample size.
    def test_r4_sample_below_policy_floor_refused(self):
        floor = sv.required_sample_size(self.N, 200, Fraction(99, 100))
        self.assertGreater(floor, 1)
        with self.assertRaises(sv.VerificationError) as caught:
            sv.verify_sample(commitment=self.commitment, pinned_merkle_root=self.root,
                             owner_nonce=NONCE_A, sample_size=1,
                             expected_grid_point_count=self.N, recomputed={},
                             authority_id=AUTHORITY,
                             policy_detectable_corruption=200,
                             policy_confidence=Fraction(99, 100))
        self.assertIn("policy floor", str(caught.exception))

    def test_r4_record_carries_the_policy_it_was_held_to(self):
        self.assertEqual(self.record["policy"]["detectable_corruption"], POLICY_C)
        self.assertIn("sample_floor", self.record["policy"])

    # r4: list() is lenient, so a dict became its key list and audited clean.
    def test_r4_challenged_indices_type_guarded(self):
        for bad in (5, None, {0: "x"}, "abc"):
            forged = dict(self.record)
            forged["challenged_indices"] = bad
            with self.assertRaises(sv.VerificationError):
                sv.recheck_record(forged, self.commitment, expected_policy_detectable_corruption=POLICY_C, expected_policy_confidence=POLICY_CONF)

    # r4: mismatched_indices was never required to be a subset.
    def test_r4_mismatch_outside_the_sample_refused(self):
        forged = dict(self.record)
        forged["mismatched_indices"] = [999999]
        forged["status"] = "mismatch"
        with self.assertRaises(sv.VerificationError) as caught:
            sv.recheck_record(forged, self.commitment, expected_policy_detectable_corruption=POLICY_C, expected_policy_confidence=POLICY_CONF)
        self.assertIn("subset", str(caught.exception))

    def test_r4_authority_required_in_audit(self):
        forged = dict(self.record)
        forged["authority_id"] = ""
        with self.assertRaises(sv.VerificationError):
            sv.recheck_record(forged, self.commitment, expected_policy_detectable_corruption=POLICY_C, expected_policy_confidence=POLICY_CONF)


class TestLimitsAreStated(unittest.TestCase):

    def test_limits_admit_every_reviewed_attack(self):
        limits = sv.verification_limits()
        for key in ("establishes", "does_not_establish", "assumes"):
            self.assertIn(key, limits)
            self.assertTrue(limits[key])
        text = " ".join(limits["does_not_establish"]).lower()
        for phrase in ("identity", "before the nonce", "redraw", "retried",
                       "frozen authority", "verifier's own hardware",
                       "the campaign's grid", "unchallenged",
                       "recomputation actually happened",
                       "recheck_record audits the",
                       "bearer document", "exact predicate",
                       "widespread numerical"):
            self.assertIn(phrase, text, f"limits no longer admit: {phrase}")

    def test_assumes_covers_nonce_sourcing(self):
        text = " ".join(sv.verification_limits()["assumes"]).lower()
        self.assertIn("nonce", text)
        self.assertNotIn("normalises away", text)


if __name__ == "__main__":
    if os.environ.get("PYTHONDONTWRITEBYTECODE") != "1":
        os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    unittest.main(verbosity=1)

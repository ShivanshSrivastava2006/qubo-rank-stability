#!/usr/bin/env python3
"""Adversarial fixtures for the drand beacon nonce binding (v2).

Synthetic only: every chain hash, signature and randomness here is invented.
No network call is made and no Stage-2 value is read or written.

Tests named `test_r1_*` pin defects found by four independent reviews of
revision 1.  Tests named `test_known_hole_*` DEMONSTRATE limits the module
cannot close, so that they stay visible instead of being quietly forgotten.
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import hashlib
import os
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stage2_beacon_nonce as bn

GENESIS = 1_600_000_000
PERIOD = 30

POLICY = {
    "chain_hash": "aa" * 32,
    "public_key": "bb" * 96,
    "genesis_time": GENESIS,
    "period_seconds": PERIOD,
    "min_delay_seconds": 300,
    "scheme_id": "bls-unchained-g1-rfc9380",
    "signature_bytes": 48,
    "public_key_bytes": 96,
}

PIN_TIME = GENESIS + 10_000
COMMITMENT_DIGEST = "cd" * 32


def pin(timestamp: int = PIN_TIME) -> dict:
    return {"timestamp": timestamp, "issuer": "kaggle saved-version time",
            "subject_commitment_digest": COMMITMENT_DIGEST}


def beacon(round_number: int, seed: bytes = b"s") -> dict:
    signature = hashlib.sha512(seed + round_number.to_bytes(8, "big")).digest()[:48]
    return {"round": round_number, "signature": signature.hex(),
            "randomness": hashlib.sha256(signature).hexdigest()}


def attest(chain_hash: str = POLICY["chain_hash"]) -> dict:
    return {"verified": True, "verifier_tool": "drand-client verify",
            "verified_at": "2026-09-26T05:00:00Z", "chain_hash": chain_hash}


def bind(**over):
    kwargs = dict(policy=POLICY, pin_attestation=pin(),
                  response=beacon(bn.select_round(POLICY, PIN_TIME)),
                  signature_attestation=attest())
    kwargs.update(over)
    return bn.bind_beacon(**kwargs)


class TestPolicy(unittest.TestCase):

    def test_valid_policy_accepted(self):
        bn.validate_policy(POLICY)

    def test_missing_fields_refused(self):
        for key in bn.POLICY_FIELDS:
            broken = dict(POLICY)
            broken.pop(key)
            with self.assertRaises(bn.BeaconError):
                bn.validate_policy(broken)

    # r2: sizes were merely DECLARED. Declaring a cryptographic parameter is
    # not verifying it; they are now checked against measured chain values.
    def test_r2_declared_sizes_must_match_the_measured_chain(self):
        for key, bad in (("signature_bytes", 96), ("public_key_bytes", 48)):
            with self.assertRaises(bn.BeaconError) as caught:
                bn.validate_policy(dict(POLICY, **{key: bad}))
            self.assertIn("measures", str(caught.exception))

    def test_r2_unverified_scheme_refused_not_guessed(self):
        # evmnet is real and published, but it is BN254 with a 128-byte key,
        # so the BLS12-381 model does not describe it.
        for bad in ("bls-bn254-unchained-on-g1", "made-up-scheme", ""):
            with self.assertRaises(bn.BeaconError) as caught:
                bn.validate_policy(dict(POLICY, scheme_id=bad))
            self.assertIn("verified table", str(caught.exception))

    def test_verified_table_matches_measured_chain_facts(self):
        # Pins the primary-source observations so a silent edit fails here.
        d = bn.VERIFIED_SCHEMES["pedersen-bls-chained"]
        self.assertEqual((d["public_key_bytes"], d["signature_bytes"], d["chained"]),
                         (48, 96, True))
        q = bn.VERIFIED_SCHEMES["bls-unchained-g1-rfc9380"]
        self.assertEqual((q["public_key_bytes"], q["signature_bytes"], q["chained"]),
                         (96, 48, False))
        for scheme in bn.VERIFIED_SCHEMES.values():
            self.assertNotEqual(scheme["public_key_bytes"], scheme["signature_bytes"])

    def test_public_key_length_must_match_the_scheme(self):
        with self.assertRaises(bn.BeaconError):
            bn.validate_policy(dict(POLICY, public_key="bb" * 48))

    def test_delay_shorter_than_a_period_refused(self):
        with self.assertRaises(bn.BeaconError) as caught:
            bn.validate_policy(dict(POLICY, min_delay_seconds=PERIOD - 1))
        self.assertIn("one full period", str(caught.exception))

    def test_nonint_and_nonpositive_refused(self):
        for key, bad in (("period_seconds", 0), ("period_seconds", "30"),
                         ("genesis_time", -1), ("min_delay_seconds", 30.0)):
            with self.assertRaises(bn.BeaconError):
                bn.validate_policy(dict(POLICY, **{key: bad}))


class TestPinAttestation(unittest.TestCase):

    # r1: the pin was a bare int, so a backdated value silently selected an
    # already-published round. It now arrives with an issuer and a subject.
    def test_r1_bare_int_pin_no_longer_accepted(self):
        for bad in (PIN_TIME, "pin", None, [PIN_TIME]):
            with self.assertRaises(bn.BeaconError):
                bn.validate_pin_attestation(POLICY, bad)

    def test_missing_fields_refused(self):
        for key in ("timestamp", "issuer", "subject_commitment_digest"):
            broken = pin()
            broken.pop(key)
            with self.assertRaises(bn.BeaconError):
                bn.validate_pin_attestation(POLICY, broken)

    def test_unnamed_issuer_refused(self):
        with self.assertRaises(bn.BeaconError):
            bn.validate_pin_attestation(POLICY, dict(pin(), issuer=""))

    def test_subject_digest_must_be_64_hex(self):
        for bad in ("", "zz" * 32, "cd" * 31, 5):
            with self.assertRaises(bn.BeaconError):
                bn.validate_pin_attestation(
                    POLICY, dict(pin(), subject_commitment_digest=bad))

    def test_pin_before_genesis_refused(self):
        with self.assertRaises(bn.BeaconError):
            bn.validate_pin_attestation(POLICY, pin(GENESIS - 1))


class TestRoundSelection(unittest.TestCase):

    def test_deterministic_and_monotone(self):
        previous = 0
        for offset in range(0, 3000, 7):
            r = bn.select_round(POLICY, GENESIS + offset)
            self.assertEqual(r, bn.select_round(POLICY, GENESIS + offset))
            self.assertGreaterEqual(r, previous)
            previous = r

    def test_selected_round_is_after_the_required_delay(self):
        for offset in (0, 1, 29, 30, 31, 12_345, 987_654):
            t = GENESIS + offset
            r = bn.select_round(POLICY, t)
            self.assertGreaterEqual(bn.publication_time(POLICY, r),
                                    t + POLICY["min_delay_seconds"])

    def test_publication_formula_is_the_measured_one(self):
        # Settled against the live API on both BLS12-381 chains: round r is
        # published at genesis + (r-1)*period, so round 1 is at genesis. The
        # competing genesis + r*period is excluded.
        for r in (1, 2, 17, 1000):
            self.assertEqual(bn.publication_time(POLICY, r),
                             GENESIS + (r - 1) * PERIOD)
            self.assertNotEqual(bn.publication_time(POLICY, r),
                                GENESIS + r * PERIOD)


class TestBinding(unittest.TestCase):

    def test_valid_binding_accepted(self):
        record = bind()
        self.assertEqual(record["round"], bn.select_round(POLICY, PIN_TIME))
        self.assertEqual(record["outage_policy"], bn.OUTAGE_POLICY)

    # r1: expected_round was a free argument, so any round could be paired
    # with a genuine response for it. It can no longer be supplied at all.
    def test_r1_round_cannot_be_supplied_by_the_caller(self):
        import inspect
        params = inspect.signature(bn.bind_beacon).parameters
        self.assertNotIn("expected_round", params)
        self.assertIn("pin_attestation", params)

    def test_substituted_round_refused(self):
        correct = bn.select_round(POLICY, PIN_TIME)
        for other in (correct - 1, correct + 1, 1):
            with self.assertRaises(bn.BeaconError) as caught:
                bind(response=beacon(other))
            self.assertIn("no other round may be used", str(caught.exception))

    def test_randomness_not_hash_of_signature_refused(self):
        r = bn.select_round(POLICY, PIN_TIME)
        broken = dict(beacon(r), randomness="cc" * 32)
        with self.assertRaises(bn.BeaconError) as caught:
            bind(response=broken)
        self.assertIn("SHA-256 of the signature", str(caught.exception))

    def test_signature_length_must_match_the_declared_policy(self):
        r = bn.select_round(POLICY, PIN_TIME)
        sig = bytes(96)
        broken = {"round": r, "signature": sig.hex(),
                  "randomness": hashlib.sha256(sig).hexdigest()}
        with self.assertRaises(bn.BeaconError):
            bind(response=broken)

    def test_attestation_required_and_checked(self):
        r = bn.select_round(POLICY, PIN_TIME)
        with self.assertRaises(bn.BeaconError) as caught:
            bind(signature_attestation=dict(attest(), verified=False))
        self.assertIn("cannot verify BLS", str(caught.exception))
        with self.assertRaises(bn.BeaconError):
            bind(signature_attestation=dict(attest(), verifier_tool=""))
        with self.assertRaises(bn.BeaconError) as caught:
            bind(signature_attestation=attest(chain_hash="cc" * 32))
        self.assertIn("different chain", str(caught.exception))

    # r1: the record omitted the policy, so an auditor could not re-derive the
    # round, and public_key was validated once and never used again.
    def test_r1_record_carries_the_whole_policy(self):
        record = bind()
        for key in bn.POLICY_FIELDS:
            self.assertIn(key, record["policy"])
        self.assertEqual(record["policy"]["public_key"], POLICY["public_key"])
        self.assertIn("pin_attestation", record)


class TestChainedSchemes(unittest.TestCase):
    """A chained scheme signs (round || previous_signature), so the response
    must carry it or the named verifier cannot rebuild the signed message."""

    CHAINED = dict(POLICY, scheme_id="pedersen-bls-chained",
                   signature_bytes=96, public_key_bytes=48,
                   public_key="bb" * 48)

    @staticmethod
    def _bytes(tag: bytes, r: int, n: int) -> bytes:
        out = b""
        i = 0
        while len(out) < n:
            out += hashlib.sha512(tag + r.to_bytes(8, "big") + bytes([i])).digest()
            i += 1
        return out[:n]

    def chained_beacon(self, r):
        sig = self._bytes(b"c", r, 96)
        prev = self._bytes(b"p", r, 96)
        return {"round": r, "signature": sig.hex(),
                "randomness": hashlib.sha256(sig).hexdigest(),
                "previous_signature": prev.hex()}

    def test_chained_requires_previous_signature(self):
        r = bn.select_round(self.CHAINED, PIN_TIME)
        response = self.chained_beacon(r)
        record = bn.bind_beacon(self.CHAINED, pin(), response, attest())
        self.assertEqual(record["previous_signature"], response["previous_signature"])
        response.pop("previous_signature")
        with self.assertRaises(bn.BeaconError) as caught:
            bn.bind_beacon(self.CHAINED, pin(), response, attest())
        self.assertIn("chained", str(caught.exception))

    def test_unchained_does_not_require_it(self):
        self.assertIsNone(bind()["previous_signature"])

    def test_previous_signature_length_checked(self):
        r = bn.select_round(self.CHAINED, PIN_TIME)
        response = dict(self.chained_beacon(r), previous_signature="ab" * 48)
        with self.assertRaises(bn.BeaconError):
            bn.bind_beacon(self.CHAINED, pin(), response, attest())


class TestRecheckAndNonce(unittest.TestCase):

    def setUp(self):
        self.record = bind()

    def test_recheck_re_derives_the_round(self):
        self.assertTrue(bn.recheck_beacon_record(self.record))

    def test_recheck_catches_a_substituted_round(self):
        forged = dict(self.record, round=self.record["round"] + 5)
        self.assertFalse(bn.recheck_beacon_record(forged))

    def test_recheck_catches_a_mismatched_randomness(self):
        forged = dict(self.record, randomness="dd" * 32)
        with self.assertRaises(bn.BeaconError):
            bn.recheck_beacon_record(forged)

    def test_nonce_shape_and_determinism(self):
        a = bn.nonce_from_beacon(self.record)
        self.assertEqual(len(a), 32)
        self.assertEqual(a, bn.nonce_from_beacon(self.record))

    def test_nonce_is_in_the_range_the_verifier_accepts(self):
        import stage2_sampled_verification as sv
        n = bn.nonce_from_beacon(self.record)
        self.assertTrue(sv.MIN_NONCE_BYTES <= len(n) <= sv.MAX_NONCE_BYTES)

    def test_chain_and_round_are_bound_into_the_nonce(self):
        base = bn.nonce_from_beacon(self.record)
        self.assertNotEqual(bn.nonce_from_beacon(
            dict(self.record, round=self.record["round"] + 1)), base)
        other = dict(self.record)
        other["policy"] = dict(POLICY, chain_hash="cc" * 32)
        self.assertNotEqual(bn.nonce_from_beacon(other), base)

    def test_evidence_digest_covers_policy_and_pin(self):
        base = bn.beacon_evidence_digest(self.record)
        moved = dict(self.record)
        moved["policy"] = dict(POLICY, min_delay_seconds=600)
        self.assertNotEqual(bn.beacon_evidence_digest(moved), base)
        repinned = dict(self.record)
        repinned["pin_attestation"] = pin(PIN_TIME + 1)
        self.assertNotEqual(bn.beacon_evidence_digest(repinned), base)


class TestKnownHoles(unittest.TestCase):
    """Limits the module cannot close. These tests assert the hole is OPEN, so
    that it stays visible and any future claim to have closed it must update
    them deliberately."""

    # A wholly invented beacon passes every in-module check, because the
    # signature is never verified. Only an independent fetch detects it.
    def test_known_hole_forged_beacon_passes(self):
        r = bn.select_round(POLICY, PIN_TIME)
        fake_sig = bytes(range(48))
        forged = {"round": r, "signature": fake_sig.hex(),
                  "randomness": hashlib.sha256(fake_sig).hexdigest()}
        record = bind(response=forged)
        self.assertEqual(record["round"], r)
        self.assertTrue(bn.recheck_beacon_record(record))
        self.assertIn("independently", bn.required_external_checks()[0].lower())

    # A backdated pin is internally consistent and selects an earlier round.
    # The module records the claim; it cannot check it.
    def test_known_hole_backdated_pin_is_internally_consistent(self):
        back = PIN_TIME - 100 * PERIOD
        earlier = bn.select_round(POLICY, back)
        self.assertLess(earlier, bn.select_round(POLICY, PIN_TIME))
        record = bn.bind_beacon(POLICY, pin(back), beacon(earlier), attest())
        self.assertTrue(bn.recheck_beacon_record(record))
        text = " ".join(bn.beacon_limits()["does_not_establish"]).lower()
        self.assertIn("backdated pin", text)

    # HALT is a policy, not enforced state; nothing prevents a second call.
    def test_known_hole_halt_is_not_enforced(self):
        first = bind()
        second = bind()
        self.assertEqual(first["round"], second["round"])
        text = " ".join(bn.beacon_limits()["does_not_establish"]).lower()
        self.assertIn("halt is a policy, not an enforced state", text)


class TestLimits(unittest.TestCase):

    def test_limits_lead_with_the_caller_problem(self):
        first = bn.beacon_limits()["does_not_establish"][0].lower()
        self.assertIn("the party that calls it", first)

    def test_limits_admit_every_reviewed_hole(self):
        text = " ".join(bn.beacon_limits()["does_not_establish"]).lower()
        for phrase in ("invent a signature", "bls on bls12-381",
                       "pairing implementation", "backdated pin",
                       "single execution", "drand chain itself"):
            self.assertIn(phrase, text, f"limits no longer admit: {phrase}")

    def test_external_checks_are_named(self):
        checks = bn.required_external_checks()
        self.assertGreaterEqual(len(checks), 4)
        joined = " ".join(checks).lower()
        for phrase in ("independently", "pairings", "witness", "single execution"):
            self.assertIn(phrase, joined)

    def test_outage_policy_is_halt_not_fallback(self):
        for token in ("halt", "no_fallback_round", "no_redraw"):
            self.assertIn(token, bn.OUTAGE_POLICY)


if __name__ == "__main__":
    if os.environ.get("PYTHONDONTWRITEBYTECODE") != "1":
        os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    unittest.main(verbosity=1)

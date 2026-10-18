#!/usr/bin/env python3
"""Fixtures for the RFC 3161 timestamp witness.

These are end-to-end and offline: a real Timestamp Authority is created locally
with openssl, issues real signed tokens, and those tokens are verified through
the same path production would use.  No network call is made and no Stage-2
value is read or written.
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import hashlib
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stage2_beacon_nonce as bn
import stage2_timestamp_witness as tw

OPENSSL = shutil.which("openssl")

TSA_CONFIG = """
[ req ]
distinguished_name = dn
prompt = no
[ dn ]
CN = {cn}
[ tsa ]
default_tsa = tsa_config
[ tsa_config ]
serial = {serial}
crypto_device = builtin
signer_cert = {crt}
certs = {ca}
signer_key = {key}
signer_digest = sha256
default_policy = {policy}
digests = sha256, sha512
{accuracy}ordering = {ordering}
tsa_name = yes
ess_cert_id_chain = no
ess_cert_id_alg = sha256
[ tsa_ext ]
extendedKeyUsage = critical,timeStamping
basicConstraints = critical,CA:false
keyUsage = critical,digitalSignature
"""


class LocalTSA:
    """A throwaway Timestamp Authority, so the tests exercise real crypto."""

    def __init__(self, directory: str, name: str, accuracy: bool = True,
                 policy: str = "1.2.3.4.1", ordering: str = "yes"):
        self.accuracy = accuracy
        self.dir = directory
        self.name = name
        self.policy = policy
        self.ordering = ordering
        self.ca = os.path.join(directory, "ca.crt")
        self.ca_key = os.path.join(directory, "ca.key")
        self.crt = os.path.join(directory, "tsa.crt")
        self.key = os.path.join(directory, "tsa.key")
        self.cnf = os.path.join(directory, "tsa.cnf")
        self.serial = os.path.join(directory, "serial.txt")
        self._build()

    def _run(self, *args, **kwargs):
        return subprocess.run(args, capture_output=True, timeout=180, **kwargs)

    def _build(self):
        with open(self.cnf, "w") as handle:
            handle.write(TSA_CONFIG.format(
                cn=self.name, serial=self.serial, crt=self.crt, ca=self.ca,
                key=self.key, accuracy="accuracy = secs:1\n" if self.accuracy else "",
                policy=self.policy, ordering=self.ordering))
        self._run(OPENSSL, "req", "-x509", "-newkey", "rsa:2048", "-keyout",
                  self.ca_key, "-out", self.ca, "-days", "2", "-nodes",
                  "-subj", f"/CN={self.name} CA")
        csr = os.path.join(self.dir, "tsa.csr")
        self._run(OPENSSL, "req", "-newkey", "rsa:2048", "-keyout", self.key,
                  "-out", csr, "-nodes", "-config", self.cnf)
        self._run(OPENSSL, "x509", "-req", "-in", csr, "-CA", self.ca, "-CAkey",
                  self.ca_key, "-set_serial", "1", "-days", "2", "-extfile",
                  self.cnf, "-extensions", "tsa_ext", "-out", self.crt)
        with open(self.serial, "w") as handle:
            handle.write("01\n")

    def stamp(self, request_der: bytes) -> bytes:
        query = os.path.join(self.dir, "in.tsq")
        reply = os.path.join(self.dir, "out.tsr")
        with open(query, "wb") as handle:
            handle.write(request_der)
        done = self._run(OPENSSL, "ts", "-reply", "-config", self.cnf,
                         "-queryfile", query, "-out", reply, cwd=self.dir)
        if not os.path.exists(reply):
            raise AssertionError((done.stdout + done.stderr).decode("utf-8", "replace"))
        with open(reply, "rb") as handle:
            return handle.read()


ROOT = "ab" * 32
POLICY_DIGEST = "cd" * 32

# ---------------------------------------------------------------------------
# A synthetic bound beacon record, built exactly as
# verify_stage2_beacon_nonce_fixtures.py builds one.  Every chain hash,
# signature and randomness here is invented; nothing is fetched.
# ---------------------------------------------------------------------------

BEACON_GENESIS = 1_600_000_000
# A one-second period, so the round's publication time is exactly controllable
# and a test can assert an exact margin.  With period P and min_delay M,
# select_round always yields publication_time == pin + M, so pinning M=1 makes
# the published second a free parameter.  The real drand parameters are not
# what these fixtures exercise -- the beacon module has its own.
BEACON_PERIOD = 1
BEACON_MIN_DELAY = 1

BEACON_POLICY = {
    "chain_hash": "aa" * 32,
    "public_key": "bb" * 96,
    "genesis_time": BEACON_GENESIS,
    "period_seconds": BEACON_PERIOD,
    "min_delay_seconds": BEACON_MIN_DELAY,
    "scheme_id": "bls-unchained-g1-rfc9380",
    "signature_bytes": 48,
    "public_key_bytes": 96,
}


def beacon_pin(timestamp: int) -> dict:
    return {"timestamp": timestamp, "issuer": "kaggle saved-version time",
            "subject_commitment_digest": "cd" * 32}


def _beacon_response(round_number: int) -> dict:
    signature = hashlib.sha512(b"s" + round_number.to_bytes(8, "big")).digest()[:48]
    return {"round": round_number, "signature": signature.hex(),
            "randomness": hashlib.sha256(signature).hexdigest()}


def _attest() -> dict:
    return {"verified": True, "verifier_tool": "drand-client verify",
            "verified_at": "2026-09-26T05:00:00Z",
            "chain_hash": BEACON_POLICY["chain_hash"]}


def record_published_at(second: int) -> dict:
    """A genuine `bind_beacon` record whose round publishes at exactly `second`."""
    pin_time = second - BEACON_MIN_DELAY
    chosen = bn.select_round(BEACON_POLICY, pin_time)
    record = bn.bind_beacon(BEACON_POLICY, beacon_pin(pin_time),
                            _beacon_response(chosen), _attest())
    if record["publication_time"] != second or bn.recheck_beacon_record(record) is not True:
        raise AssertionError("fixture policy does not publish at the requested second")
    return record


def build_beacon_record() -> dict:
    """A valid record publishing well after any token these tests will issue."""
    return record_published_at(int(time.time()) + 3600)


def beacon_subject() -> str:
    """The subject the module derives: root + digest of the bound policy."""
    return tw.witness_subject_digest(ROOT, tw.beacon_policy_digest(BEACON_POLICY))


def forge_round(record: dict, offset: int = 1_000_000) -> dict:
    """A record whose round does NOT re-derive from its own policy and pin.

    `recheck_beacon_record` returns False for exactly this shape, and the
    publication time derived from the inflated round is correspondingly
    inflated, so accepting it inflates the reported margin.
    """
    return dict(record, round=record["round"] + offset)


@unittest.skipIf(OPENSSL is None, "openssl not available")
class TestEndToEnd(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="g9-witness-tests-")
        cls.a = LocalTSA(os.path.join(cls.tmp.name, "a"), "Authority A") \
            if os.makedirs(os.path.join(cls.tmp.name, "a"), exist_ok=True) is None else None
        os.makedirs(os.path.join(cls.tmp.name, "b"), exist_ok=True)
        cls.b = LocalTSA(os.path.join(cls.tmp.name, "b"), "Authority B")
        os.makedirs(os.path.join(cls.tmp.name, "n"), exist_ok=True)
        cls.noacc = LocalTSA(os.path.join(cls.tmp.name, "n"), "No Accuracy TSA",
                             accuracy=False)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.record = build_beacon_record()

    def issue(self, tsa, subject=None):
        subject = subject or beacon_subject()
        request, nonce = tw.build_timestamp_request(subject)
        return subject, request, nonce, tsa.stamp(request)

    def raw(self, tsa, label, subject=None):
        """Raw material, exactly what the public API now requires.

        Note there is no `expected_subject_digest`: the subject is derived
        inside the module from the campaign root and the beacon policy.
        """
        subject, request, nonce, token = self.issue(tsa, subject)
        return {"authority": label, "request_der": request, "response_der": token,
                "expected_nonce": nonce, "ca_file": tsa.ca,
                "untrusted_file": tsa.crt}

    def decide(self, raws, record=None, **kwargs):
        """Call the public API the way production now must."""
        return tw.require_round_after_witnesses(ROOT, record or self.record,
                                                raws, **kwargs)

    @staticmethod
    def verify(raw):
        return tw.verify_token(raw["request_der"], raw["response_der"], raw["ca_file"],
                               raw["untrusted_file"],
                               expected_subject_digest=beacon_subject(),
                               expected_nonce=raw["expected_nonce"])

    def latest_of(self, raws):
        return max(self.verify(r)["timestamp_latest"] for r in raws)

    def test_real_token_verifies_and_yields_a_time(self):
        subject = beacon_subject()
        request, nonce = tw.build_timestamp_request(subject)
        token = self.a.stamp(request)
        out = tw.verify_token(request, token, self.a.ca, self.a.crt,
                              expected_subject_digest=subject, expected_nonce=nonce)
        self.assertIn(out["status"], tw.ACCEPTABLE_STATUSES)
        self.assertIsInstance(out["timestamp"], int)
        self.assertGreater(out["timestamp"], 1_700_000_000)
        # token_sha256 names the SIGNED token; the full response, whose
        # unsigned wrapper is mutable, is recorded separately.
        self.assertEqual(out["response_sha256"], hashlib.sha256(token).hexdigest())
        self.assertNotEqual(out["token_sha256"], out["response_sha256"])

    def test_tampered_token_is_refused(self):
        subject = beacon_subject()
        request, nonce = tw.build_timestamp_request(subject)
        token = bytearray(self.a.stamp(request))
        token[len(token) // 2] ^= 0x01
        with self.assertRaises(tw.WitnessError):
            tw.verify_token(request, bytes(token), self.a.ca, self.a.crt,
                            expected_subject_digest=subject, expected_nonce=nonce)

    def test_unsigned_status_string_cannot_backdate_signed_token(self):
        subject = beacon_subject()
        request, nonce = tw.build_timestamp_request(subject)
        response = self.a.stamp(request)
        bind = dict(expected_subject_digest=subject, expected_nonce=nonce)
        actual = tw.verify_token(request, response, self.a.ca, self.a.crt, **bind)
        _, start, end = tw._walk(response, 0)
        _, _, status_end = tw._walk(response, start)
        message = b"Time stamp: Jan 01 00:00:00 2020 GMT\n20200101000000Z"
        status = tw._der(0x30, tw._der_int(0) +
                         tw._der(0x30, tw._der(0x0c, message)))
        wrapped = tw._der(0x30, status + response[status_end:end])
        # The signature remains genuine. The unsigned wrapper may change,
        # but the attested time must still be read from signed TSTInfo.
        checked = tw.verify_token(request, wrapped, self.a.ca, self.a.crt, **bind)
        self.assertEqual(checked["timestamp"], actual["timestamp"])
        self.assertGreater(checked["timestamp"], 1577836800)

    def test_token_from_another_authority_fails_against_the_wrong_ca(self):
        subject = beacon_subject()
        request, nonce = tw.build_timestamp_request(subject)
        token = self.b.stamp(request)
        with self.assertRaises(tw.WitnessError) as caught:
            tw.verify_token(request, token, self.a.ca, self.a.crt,
                            expected_subject_digest=subject, expected_nonce=nonce)
        self.assertIn("openssl refused", str(caught.exception))

    def test_token_for_a_different_subject_is_refused(self):
        subject_a = beacon_subject()
        request_a, nonce_a = tw.build_timestamp_request(subject_a)
        request_b, _ = tw.build_timestamp_request("11" * 32)
        token_b = self.a.stamp(request_b)
        # A token for a different digest must not satisfy our request.
        with self.assertRaises(tw.WitnessError):
            tw.verify_token(request_a, token_b, self.a.ca, self.a.crt,
                            expected_subject_digest=subject_a, expected_nonce=nonce_a)

    def test_two_authorities_produce_independent_witnesses(self):
        raws = [self.raw(self.a, "Authority A"), self.raw(self.b, "Authority B")]
        # Publish the round an exact 30 s after the latest witness, so the
        # margin is asserted EXACTLY rather than as a lower bound.
        record = record_published_at(self.latest_of(raws) + 30)
        summary = self.decide(raws, record)
        self.assertEqual(summary["authority_count"], 2)
        self.assertEqual(len(set(summary["signing_keys"])), 2)
        self.assertEqual(summary["margin_seconds"], 30)
        self.assertEqual(summary["round_publication_time"], record["publication_time"])
        # The subject and the root are recorded, both derived here.
        self.assertEqual(summary["subject_digest"], beacon_subject())
        self.assertEqual(summary["campaign_root"], ROOT)
        self.assertEqual(summary["beacon_policy_digest"],
                         tw.beacon_policy_digest(BEACON_POLICY))

    # The label bypass: ONE TSA, two tokens, labelled as two authorities.
    # Revision 1 keyed independence on the caller's label and accepted this.
    def test_one_tsa_cannot_pose_as_two_by_relabelling(self):
        raws = [self.raw(self.a, "Independent Authority A"),
                self.raw(self.a, "Independent Authority B")]
        with self.assertRaises(tw.WitnessError) as caught:
            self.decide(raws)
        self.assertIn("one authority, not two", str(caught.exception))

    # r2 accepted caller-written dicts: fabricated integers, no token, zero
    # cryptography, and it passed. The public API now takes raw material only.
    def test_fabricated_witness_dicts_are_refused(self):
        forged = [{"authority": "A", "timestamp_latest": 0,
                   "signer_spki_sha256": "aa" * 32, "token_sha256": "bb" * 32},
                  {"authority": "B", "timestamp_latest": 0,
                   "signer_spki_sha256": "cc" * 32, "token_sha256": "dd" * 32}]
        with self.assertRaises(tw.WitnessError) as caught:
            self.decide(forged)
        self.assertIn("request_der", str(caught.exception))

    # Two authorities each witnessing something different are not two
    # witnesses of one thing.  The subject is derived inside the module, so
    # this is reached by one token attesting a different digest.
    def test_witnesses_for_different_subjects_refused(self):
        raws = [self.raw(self.a, "Authority A"),
                self.raw(self.b, "Authority B", subject="11" * 32)]
        with self.assertRaises(tw.WitnessError) as caught:
            self.decide(raws)
        self.assertIn("different digest", str(caught.exception))

    def test_a_tampered_raw_witness_fails_inside_the_ordering_call(self):
        good = self.raw(self.a, "Authority A")
        bad = self.raw(self.b, "Authority B")
        broken = bytearray(bad["response_der"])
        broken[len(broken) // 2] ^= 0x01
        bad["response_der"] = bytes(broken)
        with self.assertRaises(tw.WitnessError) as caught:
            self.decide([good, bad])
        # It must fail on the TAMPERED TOKEN, not incidentally on timing: the
        # message comes from the verification of `bad`, not from the ordering.
        message = str(caught.exception)
        self.assertNotIn("backdating", message)
        self.assertIn("could not extract the signed timestamp token", message)

    def test_verified_output_carries_signer_and_accuracy(self):
        subject, request, nonce, token = self.issue(self.a)
        out = tw.verify_token(request, token, self.a.ca, self.a.crt,
                              expected_subject_digest=subject, expected_nonce=nonce)
        self.assertEqual(len(out["signer_spki_sha256"]), 64)
        self.assertIn("Authority A", out["signer_subject"])
        self.assertEqual(out["accuracy_seconds"], 1)
        # Ordering must use the latest possible true time, never the midpoint.
        self.assertEqual(out["timestamp_latest"], out["timestamp"] + 1)
        self.assertEqual(out["subject_digest"], subject)
        self.assertEqual(out["nonce"], nonce)

    # The policy OID and the ordering flag were read for tag only in r3/r4 and
    # never surfaced, so a record could not show WHAT the TSA attested under or
    # whether it claimed ordering.  Both are read from the DER here.
    def test_verified_output_records_policy_oid_and_ordering_claim(self):
        out = self.verify(self.raw(self.a, "Authority A"))
        # TSA_CONFIG pins default_policy = 1.2.3.4.1 and ordering = yes.
        self.assertEqual(out["policy_oid"], "1.2.3.4.1")
        self.assertIs(out["tsa_ordering_claim"], True)

    def test_summary_records_policy_oids_and_minimum_applied(self):
        raws = [self.raw(self.a, "Authority A"), self.raw(self.b, "Authority B")]
        out = self.decide(raws)
        self.assertEqual(out["policy_oids"],
                         {"Authority A": "1.2.3.4.1", "Authority B": "1.2.3.4.1"})
        self.assertEqual(out["minimum_authorities_applied"], tw.MINIMUM_AUTHORITIES)
        self.assertIsNone(out["pinned_policy_oids"])

    # minimum_authorities is a caller parameter and may be relaxed below the
    # default.  The value ACTUALLY applied must be in the record, or a consumer
    # cannot tell a one-authority result from a two-authority one.
    def test_relaxed_minimum_authorities_is_recorded(self):
        one = self.raw(self.a, "Authority A")
        out = self.decide([one], minimum_authorities=1)
        self.assertEqual(out["authority_count"], 1)
        self.assertEqual(out["minimum_authorities_applied"], 1)
        self.assertNotEqual(out["minimum_authorities_applied"], tw.MINIMUM_AUTHORITIES)

    def test_wrong_expected_subject_refused(self):
        subject, request, nonce, token = self.issue(self.a)
        with self.assertRaises(tw.WitnessError) as caught:
            tw.verify_token(request, token, self.a.ca, self.a.crt,
                            expected_subject_digest="11" * 32, expected_nonce=nonce)
        self.assertIn("different digest", str(caught.exception))

    # A token whose nonce is not the one sent may be a replay of an earlier
    # issuance for the same digest, and would attest the wrong instant.
    def test_wrong_expected_nonce_refused_as_possible_replay(self):
        subject, request, nonce, token = self.issue(self.a)
        with self.assertRaises(tw.WitnessError) as caught:
            tw.verify_token(request, token, self.a.ca, self.a.crt,
                            expected_subject_digest=subject, expected_nonce=nonce + 1)
        self.assertIn("replay", str(caught.exception))

    def test_bindings_are_mandatory(self):
        subject, request, nonce, token = self.issue(self.a)
        with self.assertRaises(TypeError):
            tw.verify_token(request, token, self.a.ca, self.a.crt)
        for bad_nonce in (0, -1, "5"):
            with self.assertRaises(tw.WitnessError):
                tw.verify_token(request, token, self.a.ca, self.a.crt,
                                expected_subject_digest=subject, expected_nonce=bad_nonce)

    # Every raw field is type-checked, including this one.  r4 appended it to
    # the subprocess argv unguarded, so an int raised a bare TypeError from the
    # standard library instead of a typed WitnessError.
    def test_untrusted_file_must_be_a_string_or_none(self):
        raw = self.raw(self.a, "Authority A")
        for bad in (123, True, ["x"], 1.5):
            broken = dict(raw, untrusted_file=bad)
            with self.assertRaises(tw.WitnessError) as caught:
                self.decide([broken])
            self.assertIn("untrusted_file must be a string", str(caught.exception))
        # None and the empty string keep their FALSY meaning: no -untrusted.
        self.assertEqual(self.verify(dict(raw, untrusted_file=None))["nonce"],
                         raw["expected_nonce"])
        self.assertEqual(self.verify(dict(raw, untrusted_file=""))["nonce"],
                         raw["expected_nonce"])

    # No declared accuracy means no error bound, so ordering cannot be made
    # conservative. Refused rather than silently assumed exact.
    def test_token_without_accuracy_refused(self):
        subject, request, nonce, token = self.issue(self.noacc)
        with self.assertRaises(tw.WitnessError) as caught:
            tw.verify_token(request, token, self.noacc.ca, self.noacc.crt,
                            expected_subject_digest=subject, expected_nonce=nonce)
        self.assertIn("accuracy", str(caught.exception))

    def key_of(self, raw):
        return self.verify(raw)["signer_spki_sha256"]

    def test_pinned_registry_accepts_the_right_keys(self):
        a, b = self.raw(self.a, "Authority A"), self.raw(self.b, "Authority B")
        pins = {"Authority A": self.key_of(a), "Authority B": self.key_of(b)}
        out = self.decide([a, b], pinned_authorities=pins)
        self.assertTrue(out["pinned"])

    # With pinning, a label is a checked binding rather than a claim.
    def test_pinned_label_on_the_wrong_key_refused(self):
        a = self.raw(self.a, "Authority A")
        b = self.raw(self.b, "Authority A")   # B's token claiming A's label
        with self.assertRaises(tw.WitnessError) as caught:
            self.decide([a, b], pinned_authorities={"Authority A": self.key_of(a)})
        self.assertIn("different signing key", str(caught.exception))

    def test_unpinned_label_refused_when_registry_given(self):
        a, b = self.raw(self.a, "Authority A"), self.raw(self.b, "Unlisted")
        with self.assertRaises(tw.WitnessError) as caught:
            self.decide([a, b], pinned_authorities={"Authority A": self.key_of(a)})
        self.assertIn("not in the pinned set", str(caught.exception))

    # A key pinned for one policy must not be accepted asserting time under
    # another: RFC 3161 s2.4.1 makes the policy the identifier of WHAT was
    # attested.  pinning the right key is not pinning the right policy.
    def test_pinned_policy_oids_accepts_the_right_policy(self):
        raws = [self.raw(self.a, "Authority A"), self.raw(self.b, "Authority B")]
        out = self.decide(raws, pinned_policy_oids={"1.2.3.4.1"})
        self.assertEqual(out["pinned_policy_oids"], ["1.2.3.4.1"])
        self.assertEqual(out["policy_oids"], {"Authority A": "1.2.3.4.1",
                                              "Authority B": "1.2.3.4.1"})

    def test_policy_oid_outside_the_pin_is_refused(self):
        raws = [self.raw(self.a, "Authority A"), self.raw(self.b, "Authority B")]
        with self.assertRaises(tw.WitnessError) as caught:
            self.decide(raws, pinned_policy_oids={"1.2.3.4.99"})
        self.assertIn("not in the pinned set", str(caught.exception))

    def test_malformed_pinned_policy_oid_refused(self):
        raws = [self.raw(self.a, "Authority A"), self.raw(self.b, "Authority B")]
        for bad in ({"3.4.1.1"}, {"1.2.3.4.01"}, {"1"}, {""}, {"1.2.x"}):
            with self.assertRaises(tw.WitnessError) as caught:
                self.decide(raws, pinned_policy_oids=bad)
            self.assertIn("dotted OID", str(caught.exception))
        for bad in ([], (), "1.2.3.4.1", {"1.2.3.4.1": True}):
            with self.assertRaises(tw.WitnessError):
                self.decide(raws, pinned_policy_oids=bad)


class _SharedTSAs:
    """A second pair of local TSAs, so the pure-logic class needs no fixtures
    of its own beyond the certificates it must verify."""

    def __init__(self):
        self.tmp = None

    def build(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="g9-witness-derived-")
        for name in ("a", "b"):
            os.makedirs(os.path.join(self.tmp.name, name), exist_ok=True)
        self.a = LocalTSA(os.path.join(self.tmp.name, "a"), "Authority A")
        self.b = LocalTSA(os.path.join(self.tmp.name, "b"), "Authority B")
        return self

    @staticmethod
    def issue(tsa, subject=None):
        subject = subject or beacon_subject()
        request, nonce = tw.build_timestamp_request(subject)
        return subject, request, nonce, tsa.stamp(request)

    @classmethod
    def raw(cls, tsa, label, subject=None):
        _, request, nonce, token = cls.issue(tsa, subject)
        return {"authority": label, "request_der": request, "response_der": token,
                "expected_nonce": nonce, "ca_file": tsa.ca, "untrusted_file": tsa.crt}

    @staticmethod
    def verify(raw):
        return tw.verify_token(raw["request_der"], raw["response_der"], raw["ca_file"],
                               raw["untrusted_file"],
                               expected_subject_digest=beacon_subject(),
                               expected_nonce=raw["expected_nonce"])


class TestDerivedInputs(unittest.TestCase):
    """The subject and the round time are DERIVED, not supplied (r4 findings)."""

    @unittest.skipIf(OPENSSL is None, "openssl not available")
    def setUp(self):
        self.holder = _SharedTSAs().build()
        self.addCleanup(self.holder.tmp.cleanup)

    def raws(self):
        return [self.holder.raw(self.holder.a, "Authority A"),
                self.holder.raw(self.holder.b, "Authority B")]

    # A witness dict carrying its own expected_subject_digest is the r4
    # fail-open: the submitter chose what was being witnessed.  It is refused
    # outright rather than silently overridden.
    def test_witness_carrying_its_own_expected_subject_is_refused(self):
        raws = self.raws()
        poisoned = dict(raws[0], expected_subject_digest="11" * 32)
        with self.assertRaises(tw.WitnessError) as caught:
            tw.require_round_after_witnesses(ROOT, build_beacon_record(), [poisoned, raws[1]])
        self.assertIn("must not carry expected_subject_digest", str(caught.exception))

    # Even an AGREEING one is refused: the subject is this module's to derive,
    # and a caller that sets it has not read the result.
    def test_witness_carrying_the_agreeing_subject_is_still_refused(self):
        raws = self.raws()
        poisoned = dict(raws[0], expected_subject_digest=beacon_subject())
        with self.assertRaises(tw.WitnessError) as caught:
            tw.require_round_after_witnesses(ROOT, build_beacon_record(), [poisoned, raws[1]])
        self.assertIn("must not carry expected_subject_digest", str(caught.exception))

    # A token for a DIFFERENT subject must not satisfy the derived one, even
    # though the submitter's own request was perfectly consistent.
    def test_token_for_another_subject_is_refused_by_the_derived_one(self):
        subject, request, nonce, token = self.holder.issue(
            self.holder.a, subject="11" * 32)
        forged = {"authority": "Authority A", "request_der": request,
                  "response_der": token, "expected_nonce": nonce,
                  "ca_file": self.holder.a.ca, "untrusted_file": self.holder.a.crt}
        other = self.raws()[1]
        with self.assertRaises(tw.WitnessError) as caught:
            tw.require_round_after_witnesses(ROOT, build_beacon_record(), [forged, other])
        self.assertIn("different digest", str(caught.exception))

    # THE r4 fail-open the validator measured: recheck_beacon_record returns
    # False for exactly a record whose round does not re-derive, r4 discarded
    # the return value, and the forged round inflated the margin.
    def test_forged_round_is_refused_even_though_recheck_returns_false(self):
        record = build_beacon_record()
        forged = forge_round(record)
        self.assertIs(bn.recheck_beacon_record(forged), False)
        # And the forged round really would have inflated the margin.
        honest = record["publication_time"]
        inflated = bn.publication_time(forged["policy"], forged["round"])
        self.assertEqual(inflated - honest, 1_000_000 * BEACON_PERIOD)
        with self.assertRaises(tw.WitnessError) as caught:
            tw.require_round_after_witnesses(ROOT, forged, self.raws())
        self.assertIn("recheck_beacon_record did not confirm", str(caught.exception))

    def test_a_round_that_does_not_publish_after_the_witnesses_is_refused(self):
        raws = self.raws()
        latest = max(self.holder.verify(r)["timestamp_latest"] for r in raws)
        record = record_published_at(latest)      # published AT the witness bound
        with self.assertRaises(tw.WitnessError) as caught:
            tw.require_round_after_witnesses(ROOT, record, raws)
        self.assertIn("backdating is not excluded", str(caught.exception))

    def test_a_malformed_beacon_record_is_refused(self):
        for bad in ({}, {"schema": bn.SCHEMA}, "not a record", [],
                    dict(build_beacon_record(), randomness="dd" * 32)):
            with self.assertRaises(tw.WitnessError):
                tw.require_round_after_witnesses(ROOT, bad, self.raws())

    def test_subject_is_derived_from_the_root_and_the_record_policy(self):
        record = build_beacon_record()
        raws = self.raws()
        out = tw.require_round_after_witnesses(ROOT, record, raws)
        self.assertEqual(out["subject_digest"],
                         tw.witness_subject_digest(ROOT,
                                                   tw.beacon_policy_digest(record["policy"])))
        # A different campaign root must not verify against these tokens.
        with self.assertRaises(tw.WitnessError) as caught:
            tw.require_round_after_witnesses("cc" * 32, record, raws)
        self.assertIn("different digest", str(caught.exception))

    def test_policy_digest_is_canonical_and_differently_sensitive(self):
        base = tw.beacon_policy_digest(BEACON_POLICY)
        self.assertEqual(base, tw.beacon_policy_digest(dict(reversed(list(BEACON_POLICY.items())))))
        changed = dict(BEACON_POLICY, chain_hash="cc" * 32)
        self.assertNotEqual(tw.beacon_policy_digest(changed), base)
        self.assertEqual(len(base), 64)
        for bad in ({}, [], "policy", None, 5):
            with self.assertRaises(tw.WitnessError):
                tw.beacon_policy_digest(bad)

    # The subject the module checks is DERIVED.  A caller-chosen digest must
    # not be honoured even when one is supplied: these two witnesses attest the
    # derived subject, and a variant of this call that read the caller's choice
    # instead would check a different digest and report a different summary.
    def test_the_checked_subject_is_the_derived_one_not_a_supplied_one(self):
        record = build_beacon_record()
        raws = self.raws()
        derived = beacon_subject()
        other = tw.witness_subject_digest("11" * 32,
                                          tw.beacon_policy_digest(record["policy"]))
        self.assertNotEqual(derived, other)
        out = tw.require_round_after_witnesses(ROOT, record, raws)
        self.assertEqual(out["subject_digest"], derived)
        # If the module were to verify against `other` instead, the imprint
        # check inside verify_token would refuse; it does not, which is what
        # makes this assertion evidence that `derived` is what was used.
        for r in raws:
            self.assertEqual(self.holder.verify(r)["subject_digest"], derived)
            with self.assertRaises(tw.WitnessError):
                tw.verify_token(r["request_der"], r["response_der"], r["ca_file"],
                                r["untrusted_file"],
                                expected_subject_digest=other,
                                expected_nonce=r["expected_nonce"])


class TestTsaPolicyAndOrderingInTheToken(unittest.TestCase):
    """A TSA that asserts a DIFFERENT policy, and one that asserts no ordering.

    Every other fixture's TSA is configured identically, so these two are what
    make the recorded values demonstrably READ rather than assumed.
    """

    @unittest.skipIf(OPENSSL is None, "openssl not available")
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="g9-witness-policy-")
        for name in ("p", "n", "p2"):
            os.makedirs(os.path.join(cls.tmp.name, name), exist_ok=True)
        # default_policy = 1.2.3.4.99 -- deliberately NOT the usual value.
        cls.policy_tsa = LocalTSA(os.path.join(cls.tmp.name, "p"), "Policy TSA",
                                 policy="1.2.3.4.99")
        # ordering = no: the TSA explicitly declines to assert ordering.
        cls.noorder_tsa = LocalTSA(os.path.join(cls.tmp.name, "n"), "No Ordering TSA",
                                   ordering="no")
        cls.policy_tsa2 = LocalTSA(os.path.join(cls.tmp.name, "p2"), "Policy TSA 2",
                                   policy="1.2.3.4.99")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    @staticmethod
    def issue(tsa):
        subject = beacon_subject()
        request, nonce = tw.build_timestamp_request(subject)
        return request, nonce, tsa.stamp(request)

    def verify(self, tsa, request, nonce, token):
        return tw.verify_token(request, token, tsa.ca, tsa.crt,
                               expected_subject_digest=beacon_subject(),
                               expected_nonce=nonce)

    def test_policy_oid_reflects_the_tsa_not_a_constant(self):
        request, nonce, token = self.issue(self.policy_tsa)
        out = self.verify(self.policy_tsa, request, nonce, token)
        self.assertEqual(out["policy_oid"], "1.2.3.4.99")
        self.assertNotEqual(out["policy_oid"], "1.2.3.4.1")

    # `ordering = no` makes openssl OMIT the field rather than encode FALSE,
    # so the derived value is None -- the record distinguishes "asserted true",
    # "asserted false" and "not asserted" rather than collapsing them.
    def test_ordering_not_asserted_is_recorded_as_none_not_as_true(self):
        request, nonce, token = self.issue(self.noorder_tsa)
        out = self.verify(self.noorder_tsa, request, nonce, token)
        self.assertIsNone(out["tsa_ordering_claim"])
        # And a TSA that DOES assert ordering still reports True.
        request, nonce, token = self.issue(self.policy_tsa)
        self.assertIs(self.verify(self.policy_tsa, request, nonce,
                                  token)["tsa_ordering_claim"], True)

    def test_summary_reports_each_tsa_its_own_policy(self):
        raws = []
        for label, tsa in (("Policy TSA", self.policy_tsa),
                           ("Policy TSA 2", self.policy_tsa2)):
            request, nonce, token = self.issue(tsa)
            raws.append({"authority": label, "request_der": request,
                         "response_der": token, "expected_nonce": nonce,
                         "ca_file": tsa.ca, "untrusted_file": tsa.crt})
        out = tw.require_round_after_witnesses(ROOT, build_beacon_record(), raws)
        self.assertEqual(out["policy_oids"], {"Policy TSA": "1.2.3.4.99",
                                              "Policy TSA 2": "1.2.3.4.99"})

    def test_a_pin_that_excludes_the_real_policy_is_refused(self):
        raws = []
        for label, tsa in (("Policy TSA", self.policy_tsa),
                           ("Policy TSA 2", self.policy_tsa2)):
            request, nonce, token = self.issue(tsa)
            raws.append({"authority": label, "request_der": request,
                         "response_der": token, "expected_nonce": nonce,
                         "ca_file": tsa.ca, "untrusted_file": tsa.crt})
        with self.assertRaises(tw.WitnessError) as caught:
            tw.require_round_after_witnesses(ROOT, build_beacon_record(), raws,
                                            pinned_policy_oids={"1.2.3.4.1"})
        self.assertIn("1.2.3.4.99", str(caught.exception))


class _Done:
    """A stand-in for subprocess.CompletedProcess with the three attributes
    the module reads."""

    def __init__(self, returncode, stdout, stderr):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class TestEkuGateReachedThroughVerifyToken(unittest.TestCase):
    """The DER EKU gate and the openssl text gate, as `verify_token` runs them.

    openssl refuses to ISSUE with a non-conforming EKU, so a bad-EKU token
    cannot be minted through its own path.  The DER read is therefore the only
    place a bad certificate can be introduced, and it is stubbed at exactly the
    boundary production uses: the certificate bytes the gate reads.  The text
    gate is stubbed the same way, in the opposite direction, to show that it
    refuses rather than admits.
    """

    @unittest.skipIf(OPENSSL is None, "openssl not available")
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="g9-witness-eku-")
        self.addCleanup(self.tmp.cleanup)
        self.tsa = LocalTSA(self.tmp.name, "Authority A")
        self.subject = beacon_subject()
        self.request, self.nonce = tw.build_timestamp_request(self.subject)
        self.token = self.tsa.stamp(self.request)
        self._real_cert_der = tw._cert_eku_extension_der

    def verify(self):
        return tw.verify_token(self.request, self.token, self.tsa.ca, self.tsa.crt,
                               expected_subject_digest=self.subject,
                               expected_nonce=self.nonce)

    def test_the_honest_token_verifies_and_the_gate_ran(self):
        out = self.verify()
        self.assertIn("Authority A", out["signer_subject"])
        # The real signer certificate really does satisfy the DER gate.
        tw._require_timestamping_eku_der(
            self._real_cert_der(os.path.join(self.tmp.name, "tsa.crt"), "openssl"))

    def test_a_non_critical_signer_eku_is_refused_through_verify_token(self):
        bad = _cert([_eku_extension([tw.TIME_STAMPING_EKU_OID], critical=False)])
        tw._cert_eku_extension_der = lambda pem, openssl: bad
        self.addCleanup(setattr, tw, "_cert_eku_extension_der",
                        self._real_cert_der)
        with self.assertRaises(tw.WitnessError) as caught:
            self.verify()
        self.assertIn("not marked critical", str(caught.exception))

    def test_an_over_broad_signer_eku_is_refused_through_verify_token(self):
        bad = _cert([_eku_extension([tw.TIME_STAMPING_EKU_OID,
                                     "1.3.6.1.5.5.7.3.2"])])
        tw._cert_eku_extension_der = lambda pem, openssl: bad
        self.addCleanup(setattr, tw, "_cert_eku_extension_der",
                        self._real_cert_der)
        with self.assertRaises(tw.WitnessError) as caught:
            self.verify()
        self.assertIn("must be limited to", str(caught.exception))

    def test_a_missing_signer_eku_is_refused_through_verify_token(self):
        other = tw._der(0x30, tw._der(0x06, _oid_body("2.5.29.19"))
                        + tw._der(0x04, b"\x05\x00"))
        tw._cert_eku_extension_der = lambda pem, openssl: _cert([other])
        self.addCleanup(setattr, tw, "_cert_eku_extension_der",
                        self._real_cert_der)
        with self.assertRaises(tw.WitnessError) as caught:
            self.verify()
        self.assertIn("no extended key usage", str(caught.exception))

    # The openssl text check is REFUSE-ONLY: it can never make a token
    # acceptable, but a rendering that does not advertise a critical Time
    # Stamping usage must still refuse.  Stubbing the subprocess proves the
    # refusal is the text check's own, because the DER gate is happy with the
    # real certificate throughout.
    def test_openssl_text_check_refuses_a_rendering_without_time_stamping(self):
        real = subprocess.run

        def fake_run(argv, *args, **kwargs):
            if isinstance(argv, list) and "-ext" in argv:
                return _Done(0, b"X509v3 Extended Key Usage: \n"
                                 b"    TLS Web Server Authentication\n", b"")
            return real(argv, *args, **kwargs)

        tw.subprocess.run = fake_run
        try:
            with self.assertRaises(tw.WitnessError) as caught:
                self.verify()
        finally:
            tw.subprocess.run = real
        self.assertIn("does not report a critical Time Stamping", str(caught.exception))

    def test_openssl_text_check_refuses_when_the_command_fails(self):
        real = subprocess.run

        def fake_run(argv, *args, **kwargs):
            if isinstance(argv, list) and "-ext" in argv:
                return _Done(1, b"", b"unable to load")
            return real(argv, *args, **kwargs)

        tw.subprocess.run = fake_run
        try:
            with self.assertRaises(tw.WitnessError) as caught:
                self.verify()
        finally:
            tw.subprocess.run = real
        self.assertIn("does not report a critical Time Stamping", str(caught.exception))


class TestSubjectAndRequest(unittest.TestCase):

    def test_subject_binds_both_inputs(self):
        base = tw.witness_subject_digest(ROOT, POLICY_DIGEST)
        self.assertEqual(base, tw.witness_subject_digest(ROOT, POLICY_DIGEST))
        self.assertNotEqual(base, tw.witness_subject_digest("11" * 32, POLICY_DIGEST))
        # The policy must be bound too: timestamping the root alone would leave
        # the policy free to change afterwards, and the policy makes the round.
        self.assertNotEqual(base, tw.witness_subject_digest(ROOT, "11" * 32))

    def test_subject_rejects_malformed_input(self):
        for bad in ("", "ab" * 31, "zz" * 32, "AB" * 32, 5, None):
            with self.assertRaises(tw.WitnessError):
                tw.witness_subject_digest(bad, POLICY_DIGEST)
            with self.assertRaises(tw.WitnessError):
                tw.witness_subject_digest(ROOT, bad)

    def test_request_is_well_formed_der(self):
        subject = tw.witness_subject_digest(ROOT, POLICY_DIGEST)
        request, nonce = tw.build_timestamp_request(subject)
        self.assertEqual(request[0], 0x30)
        self.assertIn(bytes.fromhex(subject), request)
        self.assertIn(tw.SHA256_OID_DER, request)
        self.assertGreater(nonce, 0)

    @unittest.skipIf(OPENSSL is None, "openssl not available")
    def test_openssl_parses_our_request(self):
        subject = tw.witness_subject_digest(ROOT, POLICY_DIGEST)
        request, nonce = tw.build_timestamp_request(subject)
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "req.tsq")
            with open(path, "wb") as handle:
                handle.write(request)
            shown = subprocess.run([OPENSSL, "ts", "-query", "-in", path, "-text"],
                                   capture_output=True, timeout=60)
            text = (shown.stdout + shown.stderr).decode("utf-8", "replace")
        # openssl prints the imprint as an offset-prefixed hex dump with an
        # ASCII gutter, e.g. "    0000 - 40 20 2C ... 12   @ ,...". Parse the
        # data column rather than scraping hex characters out of the whole
        # block, which would also pick up the offsets and the gutter.
        import re as _re
        dumped = ""
        for line in text.splitlines():
            m = _re.match(r"\s*[0-9a-fA-F]{4} - ([0-9a-fA-F \-]+?)(?:   |$)", line)
            if m:
                dumped += m.group(1).replace(" ", "").replace("-", "")
        self.assertIn("sha256", text.lower())
        self.assertIn(subject.upper(), dumped.upper())
        self.assertIn("Version: 1", text)
        self.assertIn(f"{nonce:X}".upper(), text.upper())

    def test_nonce_is_fresh_by_default(self):
        subject = tw.witness_subject_digest(ROOT, POLICY_DIGEST)
        seen = {tw.build_timestamp_request(subject)[1] for _ in range(8)}
        self.assertEqual(len(seen), 8, "nonces must not repeat")

    def test_explicit_nonce_is_honoured_and_validated(self):
        subject = tw.witness_subject_digest(ROOT, POLICY_DIGEST)
        _, nonce = tw.build_timestamp_request(subject, nonce=12345)
        self.assertEqual(nonce, 12345)
        for bad in (0, -1, "5", None if False else 1.5):
            with self.assertRaises(tw.WitnessError):
                tw.build_timestamp_request(subject, nonce=bad)


class TestResponseStatus(unittest.TestCase):

    @staticmethod
    def response_with_status(status: int) -> bytes:
        inner = tw._der(0x30, tw._der_int(status))
        return tw._der(0x30, inner)

    def test_granted_statuses_parse(self):
        for status in tw.ACCEPTABLE_STATUSES:
            self.assertEqual(
                tw.parse_response_status(self.response_with_status(status)), status)

    # A rejection is a well-formed response. A caller checking only the
    # signature would otherwise treat a refusal as evidence.
    def test_rejection_refused_before_any_crypto(self):
        for status in (2, 3, 4, 5):
            with self.assertRaises(tw.WitnessError) as caught:
                tw.verify_token(b"\x30\x00", self.response_with_status(status),
                                "/nonexistent-ca.pem",
                                expected_subject_digest="ab" * 32, expected_nonce=1)
            self.assertIn("did not grant", str(caught.exception))

    def test_malformed_der_refused(self):
        for bad in (b"", b"\x30", b"\x02\x01\x00", b"\x30\x84\xff\xff\xff\xff",
                    b"\x30\x03\x02\x01"):
            with self.assertRaises(tw.WitnessError):
                tw.parse_response_status(bad)

    def test_non_bytes_refused(self):
        for bad in ("abc", None, 5, []):
            with self.assertRaises(tw.WitnessError):
                tw.parse_response_status(bad)


class TestOrderingLogic(unittest.TestCase):
    """Pure ordering logic, tested through the private function the public
    entry point calls after verifying every token itself."""

    SUBJECT = "ab" * 32
    POLICY = "1.2.3.4.1"

    def rec(self, name, timestamp, key=None, subject=None, policy=None, ordering=True):
        key = key or hashlib.sha256(b"key:" + name.encode()).hexdigest()
        return (name, {"timestamp_latest": timestamp, "signer_spki_sha256": key,
                       "subject_digest": subject or self.SUBJECT,
                       "policy_oid": policy or self.POLICY,
                       "tsa_ordering_claim": ordering})

    def order(self, round_time, recs, minimum=2, pins=None, policy_pins=None):
        return tw._order_verified(round_time, recs, minimum, pins, policy_pins)

    def test_round_after_all_witnesses_accepted(self):
        out = self.order(1000, [self.rec("A", 900), self.rec("B", 950)])
        self.assertEqual(out["latest_witness_timestamp"], 950)
        self.assertEqual(out["margin_seconds"], 50)

    # The property the whole module exists for.
    def test_round_not_strictly_after_a_witness_is_refused(self):
        for round_time in (949, 950, 100):
            with self.assertRaises(tw.WitnessError) as caught:
                self.order(round_time, [self.rec("A", 900), self.rec("B", 950)])
            self.assertIn("backdating is not excluded", str(caught.exception))

    def test_single_key_refused_by_default(self):
        with self.assertRaises(tw.WitnessError) as caught:
            self.order(1000, [self.rec("A", 900)])
        self.assertIn("required", str(caught.exception))

    def test_same_key_under_two_labels_refused(self):
        shared = "ee" * 32
        with self.assertRaises(tw.WitnessError) as caught:
            self.order(1000, [self.rec("A", 900, shared), self.rec("B", 910, shared)])
        self.assertIn("one authority, not two", str(caught.exception))

    def test_different_subjects_refused(self):
        with self.assertRaises(tw.WitnessError) as caught:
            self.order(1000, [self.rec("A", 900), self.rec("B", 910, subject="cd" * 32)])
        self.assertIn("different subjects", str(caught.exception))

    def test_pinned_registry_rejects_two_labels_on_one_key(self):
        shared = "ee" * 32
        with self.assertRaises(tw.WitnessError) as caught:
            self.order(1000, [self.rec("A", 900)], pins={"A": shared, "B": shared})
        self.assertIn("share one signing key", str(caught.exception))

    def test_malformed_records_refused(self):
        good = self.rec("A", 900)
        for bad in (("B", {}), ("", self.rec("B", 1)[1]),
                    ("B", dict(self.rec("B", 1)[1], timestamp_latest="900")),
                    ("B", dict(self.rec("B", 1)[1], signer_spki_sha256="zz"))):
            with self.assertRaises(tw.WitnessError):
                self.order(1000, [good, bad])
        with self.assertRaises(tw.WitnessError):
            self.order(1000, [])

    # A record missing the newly-required fields is refused, so a caller
    # cannot present a record that predates them.
    def test_record_missing_policy_oid_or_ordering_refused(self):
        good = self.rec("A", 900)
        for drop in ("policy_oid", "tsa_ordering_claim"):
            bad = ("B", {k: v for k, v in self.rec("B", 900)[1].items() if k != drop})
            with self.assertRaises(tw.WitnessError) as caught:
                self.order(1000, [good, bad])
            self.assertIn(f"missing {drop}", str(caught.exception))

    def test_ordering_claim_must_be_a_bool_or_none(self):
        good = self.rec("A", 900)
        for bad_value in ("yes", 1, [], 0.0):
            bad = ("B", dict(self.rec("B", 900)[1], tsa_ordering_claim=bad_value))
            with self.assertRaises(tw.WitnessError) as caught:
                self.order(1000, [good, bad])
            self.assertIn("tsa_ordering_claim", str(caught.exception))
        # A token whose ordering field was absent yields None and is accepted.
        out = self.order(1000, [good, ("B", dict(self.rec("B", 900)[1],
                                                 tsa_ordering_claim=None))])
        self.assertEqual(out["authority_count"], 2)

    def test_policy_pin_enforced_in_the_pure_logic_too(self):
        recs = [self.rec("A", 900), self.rec("B", 910)]
        out = self.order(1000, recs, policy_pins={"1.2.3.4.1"})
        self.assertEqual(out["policy_oids"], {"A": "1.2.3.4.1", "B": "1.2.3.4.1"})
        self.assertEqual(out["pinned_policy_oids"], ["1.2.3.4.1"])
        outside = [self.rec("A", 900), self.rec("B", 910, policy="9.9.9")]
        with self.assertRaises(tw.WitnessError) as caught:
            self.order(1000, outside, policy_pins={"1.2.3.4.1"})
        self.assertIn("not in the pinned set", str(caught.exception))

    def test_summary_records_minimum_applied_and_policy_oids(self):
        out = self.order(1000, [self.rec("A", 900)], minimum=1)
        self.assertEqual(out["minimum_authorities_applied"], 1)
        self.assertEqual(out["policy_oids"], {"A": "1.2.3.4.1"})
        self.assertIsNone(out["pinned_policy_oids"])


def _tstinfo(accuracy="five", nonce=12345, extensions=None,
             gen_time=b"20260926170920Z", imprint=bytes(32), alg=None,
             nonce_before_accuracy=False, policy=bytes.fromhex("2a030401"),
             ordering=b"\xff"):
    """Hand-built TSTInfo DER, so the parser is tested field by field."""
    alg = alg if alg is not None else tw._der(0x30, tw.SHA256_OID_DER + tw._der(0x05, b""))
    fields = [tw._der_int(1), tw._der(0x06, policy),
              tw._der(0x30, alg + tw._der(0x04, imprint)), tw._der_int(5),
              tw._der(0x18, gen_time)]
    acc = tw._der(0x30, tw._der_int(5)) if accuracy == "five" else accuracy
    nonce_field = tw._der_int(nonce) if nonce is not None else None
    tail = []
    if nonce_before_accuracy and nonce_field:
        tail.append(nonce_field)
    if acc is not None:
        tail.append(acc)
    if ordering is not None:
        tail.append(tw._der(0x01, ordering))
    if not nonce_before_accuracy and nonce_field:
        tail.append(nonce_field)
    if extensions is not None:
        tail.append(tw._der(0xA1, extensions))
    return tw._der(0x30, b"".join(fields + tail))


def _signed(tst, signers=1):
    """A structurally valid SignedData around a TSTInfo (not signed; the
    parser checks structure, openssl checks signatures)."""
    eci = tw._der(0x30, tw.TSTINFO_OID_DER + tw._der(0xA0, tw._der(0x04, tst)))
    infos = tw._der(0x31, b"".join(tw._der(0x30, tw._der_int(1)) for _ in range(signers)))
    sd = tw._der(0x30, tw._der_int(3) + tw._der(0x31, b"") + eci + infos)
    return tw._der(0x30, tw.SIGNED_DATA_OID_DER + tw._der(0xA0, sd))


class TestSignedTokenParser(unittest.TestCase):
    """r2 read these fields from openssl text and was forgeable. r3 walks the DER."""

    def test_parses_imprint_nonce_accuracy_and_time(self):
        out = tw.parse_signed_token(_signed(_tstinfo(imprint=b"\x11" * 32)))
        self.assertEqual(out["imprint"], "11" * 32)
        self.assertEqual(out["nonce"], 12345)
        self.assertEqual(out["accuracy_micros"], 5_000_000)
        self.assertEqual(out["gen_time_micros"] % 1_000_000, 0)

    # THE attack both reviewers found: a newline-bearing "Accuracy:" line placed
    # in a signed field that openssl prints verbatim. r2's first-match regex
    # took it. The DER parser reads accuracy by position and cannot be moved.
    def test_forged_accuracy_text_in_signed_extensions_is_ignored(self):
        payload = b"\nAccuracy: 0 seconds, 0 millis, 0 micros\nNonce: 0x01\n"
        ext = tw._der(0x30, tw._der(0x30, tw._der(0x06, bytes.fromhex("2a030405"))
                                    + tw._der(0x04, payload)))
        out = tw.parse_signed_token(_signed(_tstinfo(extensions=ext)))
        self.assertEqual(out["accuracy_micros"], 5_000_000)
        self.assertEqual(out["nonce"], 12345)

    # r2 fell open to ZERO when its regex matched no number.
    def test_empty_accuracy_refused_not_read_as_zero(self):
        with self.assertRaises(tw.WitnessError) as caught:
            tw.parse_signed_token(_signed(_tstinfo(accuracy=tw._der(0x30, b""))))
        self.assertIn("present but empty", str(caught.exception))

    def test_absent_accuracy_refused(self):
        with self.assertRaises(tw.WitnessError) as caught:
            tw.parse_signed_token(_signed(_tstinfo(accuracy=None)))
        self.assertIn("declares no accuracy", str(caught.exception))

    def test_accuracy_subunits_bounded_1_to_999(self):
        for bad in (0, 1000):
            body = bad.to_bytes(max(1, (bad.bit_length() + 8) // 8), "big")   # minimal DER
            acc = tw._der(0x30, tw._der_int(1) + tw._der(0x80, body))
            with self.assertRaises(tw.WitnessError) as caught:
                tw.parse_signed_token(_signed(_tstinfo(accuracy=acc)))
            self.assertIn("1..999", str(caught.exception))

    def test_non_minimal_integer_encoding_refused(self):
        acc = tw._der(0x30, tw._der_int(1) + tw._der(0x80, b"\x00\x05"))
        with self.assertRaises(tw.WitnessError) as caught:
            tw.parse_signed_token(_signed(_tstinfo(accuracy=acc)))
        self.assertIn("minimally encoded", str(caught.exception))

    def test_accuracy_sums_all_components(self):
        acc = tw._der(0x30, tw._der_int(2) + tw._der(0x80, b"\x07") + tw._der(0x81, b"\x09"))
        out = tw.parse_signed_token(_signed(_tstinfo(accuracy=acc)))
        self.assertEqual(out["accuracy_micros"], 2_007_009)

    def test_absent_nonce_refused(self):
        with self.assertRaises(tw.WitnessError) as caught:
            tw.parse_signed_token(_signed(_tstinfo(nonce=None)))
        self.assertIn("no nonce", str(caught.exception))

    def test_optional_fields_out_of_order_refused(self):
        with self.assertRaises(tw.WitnessError) as caught:
            tw.parse_signed_token(_signed(_tstinfo(nonce_before_accuracy=True)))
        self.assertIn("out of order", str(caught.exception))

    def test_non_sha256_imprint_refused(self):
        sha1 = tw._der(0x30, bytes.fromhex("06052b0e03021a") + tw._der(0x05, b""))
        with self.assertRaises(tw.WitnessError) as caught:
            tw.parse_signed_token(_signed(_tstinfo(alg=sha1)))
        self.assertIn("not SHA-256", str(caught.exception))

    def test_more_than_one_signerinfo_refused(self):
        with self.assertRaises(tw.WitnessError) as caught:
            tw.parse_signed_token(_signed(_tstinfo(), signers=2))
        self.assertIn("exactly one is required", str(caught.exception))

    def test_fractional_gentime_rounds_up_and_is_strict(self):
        out = tw.parse_signed_token(_signed(_tstinfo(gen_time=b"20260926170920.5Z")))
        self.assertEqual(out["gen_time_micros"] % 1_000_000, 500_000)
        tiny = tw.parse_signed_token(_signed(_tstinfo(gen_time=b"20260926170920.0000001Z")))
        self.assertEqual(tiny["gen_time_micros"] % 1_000_000, 1)   # rounded UP
        for bad in (b"20260926170920.50Z", b"20260926170920+0000", b"2026092617092Z",
                    b"20261326170920Z"):
            with self.assertRaises(tw.WitnessError):
                tw.parse_signed_token(_signed(_tstinfo(gen_time=bad)))

    def test_malformed_structures_refused(self):
        for bad in (b"", b"\x30\x00", _signed(_tstinfo())[:-3],
                    _signed(_tstinfo()) + b"\x00", tw._der(0x30, b"\x02\x01\x01")):
            with self.assertRaises(tw.WitnessError):
                tw.parse_signed_token(bad)

    def test_old_text_parsers_are_gone(self):
        self.assertFalse(hasattr(tw, "_signed_token_facts"))
        self.assertFalse(hasattr(tw, "_scan_generalized_times"))


class TestOidDecoder(unittest.TestCase):
    """X.690 8.19.  The policy OID is compared against a pin, so a misdecoded
    OID would either never match or match the wrong thing."""

    def test_decodes_the_three_first_arc_regimes(self):
        cases = {"2a8648": "1.2.840", "2b0601": "1.3.6.1", "550d": "2.5.13",
                 "2a": "1.2", "2b": "1.3", "42": "1.26"}
        for raw, want in cases.items():
            self.assertEqual(tw._decode_oid(bytes.fromhex(raw), "oid"), want, raw)

    def test_illegal_first_arc_refused(self):
        # 0xff = 255 -> 255//40 = 6, not a legal first arc.  0x81 = 129 -> 3.
        for raw in ("ff01", "8100", "a801"):
            with self.assertRaises(tw.WitnessError) as caught:
                tw._decode_oid(bytes.fromhex(raw), "policy")
            self.assertIn("illegal first arc", str(caught.exception))

    def test_arc_two_absorbs_values_at_or_above_eighty(self):
        # X.690 8.19.2: the first subidentifier is 40*arc1 + arc2, so a single
        # octet reaches 2.39 (119 = 0x77).  Values at or above 80 are reached
        # by the LATER arcs, which are plain base-128 and absorb them: the
        # 840 in 1.2.840 encodes as 0x86 0x48.
        self.assertEqual(tw._decode_oid(bytes.fromhex("2a8648"), "oid"), "1.2.840")
        # 1.3.6.1.5.5.7.3.8 -- every arc under 128 is one octet.
        self.assertEqual(tw._decode_oid(bytes.fromhex("2b06010505070308"), "oid"),
                         "1.3.6.1.5.5.7.3.8")
        # A later arc above 127 needs two octets: 1.2.200 = 0x81 0x48.
        self.assertEqual(tw._decode_oid(bytes.fromhex("2a8148"), "oid"), "1.2.200")
        # 2.5.29.37 -- the EKU extension's own OID.
        self.assertEqual(tw._decode_oid(bytes.fromhex("551d25"), "oid"), "2.5.29.37")

    def test_truncated_subidentifier_refused(self):
        # The final octet still has the 0x80 continuation bit set, so the
        # encoding runs off the end without ever terminating a subidentifier.
        for raw in ("2a8a", "2a86488a", "2a8648 8a 80".replace(" ", "")):
            with self.assertRaises(tw.WitnessError) as caught:
                tw._decode_oid(bytes.fromhex(raw), "policy")
            self.assertIn("truncated subidentifier", str(caught.exception))

    def test_non_minimal_subidentifier_refused(self):
        # A leading 0x80 octet is a padded, non-DER encoding of zero.
        for raw in ("802a", "8006", "2b80 06".replace(" ", "")):
            with self.assertRaises(tw.WitnessError) as caught:
                tw._decode_oid(bytes.fromhex(raw), "policy")
            self.assertIn("non-minimal subidentifier", str(caught.exception))

    def test_empty_oid_refused(self):
        with self.assertRaises(tw.WitnessError):
            tw._decode_oid(b"", "policy")

    def test_the_modules_own_oids_round_trip(self):
        self.assertEqual(tw._decode_oid(tw.SHA256_OID_DER[2:], "s"),
                         "2.16.840.1.101.3.4.2.1")
        self.assertEqual(tw._decode_oid(tw.TSTINFO_OID_DER[2:], "t"),
                         "1.2.840.113549.1.9.16.1.4")
        self.assertEqual(tw._decode_oid(tw.SIGNED_DATA_OID_DER[2:], "d"),
                         "1.2.840.113549.1.7.2")

    def test_dotted_oid_validator_agrees_with_the_decoder(self):
        for oid in ("1.2.3.4.1", "2.5.29.37", "1.3.6.1.5.5.7.3.8", "2.16.840"):
            self.assertTrue(tw._oid_is_dotted(oid), oid)
        for bad in ("3.4.1", "1", "1.2.3.04", "1.2.x", "", "1.2.3.4.", "01.2"):
            self.assertFalse(tw._oid_is_dotted(bad), bad)
        self.assertFalse(tw._oid_is_dotted(None))
        self.assertFalse(tw._oid_is_dotted(5))

    def test_malformed_policy_oid_in_a_token_is_refused(self):
        # The decoder is on the path, so a broken OID fails the parse.
        for raw in ("ff01", "802a", "2a86488680"):
            with self.assertRaises(tw.WitnessError):
                tw.parse_signed_token(_signed(_tstinfo(policy=bytes.fromhex(raw))))


class TestOrderingAndPolicyFields(unittest.TestCase):
    """D5/D6: the ordering BOOLEAN and the policy OID were accepted by tag and
    their values never read."""

    def test_policy_oid_is_read_from_the_der(self):
        out = tw.parse_signed_token(_signed(_tstinfo()))
        self.assertEqual(out["policy_oid"], "1.2.3.4.1")
        moved = tw.parse_signed_token(_signed(_tstinfo(policy=bytes.fromhex("2a8648"))))
        self.assertEqual(moved["policy_oid"], "1.2.840")

    def test_ordering_true_and_false_are_both_read(self):
        self.assertIs(tw.parse_signed_token(
            _signed(_tstinfo(ordering=b"\xff")))["tsa_ordering_claim"], True)
        self.assertIs(tw.parse_signed_token(
            _signed(_tstinfo(ordering=b"\x00")))["tsa_ordering_claim"], False)
        self.assertIsNone(tw.parse_signed_token(
            _signed(_tstinfo(ordering=None)))["tsa_ordering_claim"])

    # 01 01 01 is a non-canonical BOOLEAN, forbidden by DER.  r3 accepted it
    # because only the tag was examined.
    def test_non_der_boolean_ordering_refused(self):
        for bad in (b"\x01", b"\x7f", b"\x80", b"\x00\x00"):
            with self.assertRaises(tw.WitnessError) as caught:
                tw.parse_signed_token(_signed(_tstinfo(ordering=bad)))
            self.assertIn("not a DER BOOLEAN", str(caught.exception))


def _oid_body(dotted: str) -> bytes:
    arcs = [int(a) for a in dotted.split(".")]
    body = bytes([40 * arcs[0] + arcs[1]])
    for arc in arcs[2:]:
        chunk = [arc & 0x7F]
        arc >>= 7
        while arc:
            chunk.append(0x80 | (arc & 0x7F))
            arc >>= 7
        body += bytes(reversed(chunk))
    return body


def _eku_extension(usages, critical=True, critical_value=b"\xff"):
    """One X.509 ExtendedKeyUsage extension, as an Extension SEQUENCE."""
    value = tw._der(0x30, b"".join(tw._der(0x06, _oid_body(u)) for u in usages))
    ext = tw._der(0x06, _oid_body(tw.EXT_KEY_USAGE_OID))
    if critical:
        ext += tw._der(0x01, critical_value)
    return tw._der(0x30, ext + tw._der(0x04, value))


def _cert(extensions, with_extensions=True):
    """A structurally valid certificate around `extensions`.

    The signature bytes are filler: `_eku_from_cert_der` reads the TBS, and the
    extension walk never looks at them.
    """
    name = tw._der(0x30, bytes.fromhex("3113321106052a03040504"))
    tbs_body = b"".join([
        tw._der(0xA0, tw._der_int(2)),                 # [0] version
        tw._der_int(1),                                # serialNumber
        tw._der(0x30, tw._der(0x06, _oid_body("1.2.840.113549.1.1.11"))
                 + tw._der(0x05, b"")),               # signature
        name,                                          # issuer
        tw._der(0x30, b"2100"),                        # validity
        name,                                          # subject
        tw._der(0x30, name),                           # subjectPublicKeyInfo
    ])
    if with_extensions:
        tbs_body += tw._der(0xA3, tw._der(0x30, b"".join(extensions)))
    tbs = tw._der(0x30, tbs_body)
    return tw._der(0x30, tbs + tw._der(0x30, b"3006020101020102")
                   + tw._der(0x03, b"\x00" * 4))


class TestSignerEkuDer(unittest.TestCase):
    """D1: the EKU gate was text over TSA-chosen bytes, and POSITIVE.

    The DER check and the openssl text check are exercised INDEPENDENTLY here.
    openssl's own issuing path refuses to sign with a non-conforming EKU, so a
    forged token cannot be minted through it; the DER gate is therefore driven
    here against certificates built byte for byte, and the honest end-to-end
    token in TestEndToEnd is what proves it does not reject a genuine signer.
    """

    def test_honest_certificate_accepted(self):
        parsed = tw._require_timestamping_eku_der(
            _cert([_eku_extension([tw.TIME_STAMPING_EKU_OID])]))
        self.assertIs(parsed["critical"], True)
        self.assertEqual(parsed["usages"], [tw.TIME_STAMPING_EKU_OID])

    # A certificate that is timeStamping AND something else passes any check
    # that merely looks for the string "Time Stamping", and openssl renders
    # this one as "critical / Time Stamping, TLS Web Client Authentication".
    # The DER gate refuses it, on the DER alone.
    def test_extra_usage_refused_even_though_the_text_check_would_pass(self):
        der = _cert([_eku_extension([tw.TIME_STAMPING_EKU_OID,
                                     "1.3.6.1.5.5.7.3.2"])])
        parsed = tw._eku_from_cert_der(der)
        self.assertIs(parsed["critical"], True)
        self.assertIn(tw.TIME_STAMPING_EKU_OID, parsed["usages"])
        with self.assertRaises(tw.WitnessError) as caught:
            tw._require_timestamping_eku_der(der)
        self.assertIn("must be limited to", str(caught.exception))
        self.assertIn("1.3.6.1.5.5.7.3.2", str(caught.exception))

    def test_two_usages_neither_of_which_is_timestamping_refused(self):
        der = _cert([_eku_extension(["1.3.6.1.5.5.7.3.2", "1.3.6.1.5.5.7.3.17"])])
        with self.assertRaises(tw.WitnessError) as caught:
            tw._require_timestamping_eku_der(der)
        self.assertIn("must be limited to", str(caught.exception))
    def test_non_critical_eku_refused(self):
        der = _cert([_eku_extension([tw.TIME_STAMPING_EKU_OID], critical=False)])
        parsed = tw._eku_from_cert_der(der)
        self.assertIs(parsed["critical"], False)
        self.assertEqual(parsed["usages"], [tw.TIME_STAMPING_EKU_OID])
        with self.assertRaises(tw.WitnessError) as caught:
            tw._require_timestamping_eku_der(der)
        self.assertIn("not marked critical", str(caught.exception))

    # A critical flag explicitly encoded FALSE is not a DER TRUE, so the
    # extension is malformed rather than "present but not critical".
    def test_der_boolean_false_is_not_a_der_true(self):
        der = _cert([_eku_extension([tw.TIME_STAMPING_EKU_OID],
                                    critical=True, critical_value=b"\x00")])
        with self.assertRaises(tw.WitnessError) as caught:
            tw._eku_from_cert_der(der)
        self.assertIn("not a DER TRUE", str(caught.exception))

    def test_certificate_without_the_extension_fails_the_gate(self):
        other = tw._der(0x30, tw._der(0x06, _oid_body("2.5.29.19"))
                        + tw._der(0x04, b"\x05\x00"))
        der = _cert([other])
        self.assertEqual(tw._eku_from_cert_der(der)["usages"], [])
        with self.assertRaises(tw.WitnessError) as caught:
            tw._require_timestamping_eku_der(der)
        self.assertIn("no extended key usage", str(caught.exception))

    def test_certificate_with_no_extensions_at_all_refused(self):
        der = _cert([], with_extensions=False)
        with self.assertRaises(tw.WitnessError) as caught:
            tw._eku_from_cert_der(der)
        self.assertIn("no extensions", str(caught.exception))

    def test_malformed_certificates_refused(self):
        for bad in (b"", b"\x30\x00", b"\x30\x03\x02\x01\x01", "not bytes", None, 5):
            with self.assertRaises(tw.WitnessError):
                tw._eku_from_cert_der(bad)

    def test_eku_list_with_a_non_oid_refused(self):
        value = tw._der(0x30, tw._der(0x04, b"\x01\x02\x03"))
        ext = (tw._der(0x30, tw._der(0x06, _oid_body(tw.EXT_KEY_USAGE_OID))
                       + tw._der(0x01, b"\xff") + tw._der(0x04, value)))
        with self.assertRaises(tw.WitnessError) as caught:
            tw._eku_from_cert_der(_cert([ext]))
        self.assertIn("non-OID element", str(caught.exception))

    def test_repeated_eku_extension_refused(self):
        der = _cert([_eku_extension([tw.TIME_STAMPING_EKU_OID]),
                     _eku_extension([tw.TIME_STAMPING_EKU_OID])])
        with self.assertRaises(tw.WitnessError) as caught:
            tw._eku_from_cert_der(der)
        self.assertIn("repeats", str(caught.exception))

    def test_gate_refuses_both_bad_shapes_and_admits_the_good_one(self):
        good = _cert([_eku_extension([tw.TIME_STAMPING_EKU_OID])])
        over = _cert([_eku_extension([tw.TIME_STAMPING_EKU_OID, "1.3.6.1.5.5.7.3.2"])])
        noncrit = _cert([_eku_extension([tw.TIME_STAMPING_EKU_OID], critical=False)])
        tw._require_timestamping_eku_der(good)
        for bad in (over, noncrit):
            with self.assertRaises(tw.WitnessError):
                tw._require_timestamping_eku_der(bad)

    # The two checks are independent: the DER gate is the one that refuses an
    # over-broad EKU, and it does so without consulting any text.  openssl's
    # own rendering of this certificate advertises a critical Time Stamping
    # usage, which is precisely what a substring test would accept.
    def test_der_gate_is_the_one_that_refuses_an_over_broad_eku(self):
        over = _cert([_eku_extension([tw.TIME_STAMPING_EKU_OID,
                                      "1.3.6.1.5.5.7.3.2"])])
        with self.assertRaises(tw.WitnessError):
            tw._require_timestamping_eku_der(over)
        with self.assertRaises(tw.WitnessError):
            tw._require_timestamping_eku_der(
                _cert([_eku_extension([tw.TIME_STAMPING_EKU_OID], critical=False)]))
        # The honest one still passes, so the gate is a gate and not a wall.
        tw._require_timestamping_eku_der(_cert([_eku_extension([tw.TIME_STAMPING_EKU_OID])]))


class TestSignerSubjectAndIdentityFields(unittest.TestCase):

    @unittest.skipIf(OPENSSL is None, "openssl not available")
    def test_signer_subject_and_issuer_are_still_recorded(self):
        with tempfile.TemporaryDirectory() as d:
            tsa = LocalTSA(d, "Authority A")
            subject = beacon_subject()
            request, nonce = tw.build_timestamp_request(subject)
            token = tsa.stamp(request)
            out = tw.verify_token(request, token, tsa.ca, tsa.crt,
                                  expected_subject_digest=subject,
                                  expected_nonce=nonce)
        self.assertIn("Authority A", out["signer_subject"])
        self.assertIn("Authority A", out["signer_issuer"])


class TestLimits(unittest.TestCase):

    def test_limits_admit_collusion_and_review(self):
        text = " ".join(tw.witness_limits()["does_not_establish"]).lower()
        for phrase in ("collude", "correctness of any result",
                       "independent review", "openssl",
                       "independent organisations", "declares no accuracy",
                       "never from openssl's text"):
            self.assertIn(phrase, text, f"limits no longer admit: {phrase}")

    def test_assumes_covers_independence_and_freshness(self):
        text = " ".join(tw.witness_limits()["assumes"]).lower()
        self.assertIn("independent", text)
        self.assertIn("nonce", text)

    def test_minimum_authorities_is_at_least_two(self):
        self.assertGreaterEqual(tw.MINIMUM_AUTHORITIES, 2)

    # Spec item 5: the nonce cannot prove freshness offline, and the minimum
    # may be relaxed by the caller.
    def test_limits_state_the_nonce_and_minimum_authorities_caveats(self):
        text = " ".join(tw.witness_limits()["does_not_establish"]).lower()
        self.assertIn("nonce proves a token is fresh offline", text)
        self.assertIn("owner to record each nonce", text)
        self.assertIn("minimum_authorities is a caller-supplied parameter", text)
        self.assertIn("minimum_authorities_applied", text)

    def test_establishes_mentions_derivation(self):
        text = " ".join(tw.witness_limits()["establishes"]).lower()
        self.assertIn("derived", text)



if __name__ == "__main__":
    if os.environ.get("PYTHONDONTWRITEBYTECODE") != "1":
        os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    unittest.main(verbosity=1)

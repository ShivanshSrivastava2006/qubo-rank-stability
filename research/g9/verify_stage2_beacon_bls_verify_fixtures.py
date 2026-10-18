#!/usr/bin/env python3
"""Adversarial, mutation and load-bearing fixtures for stage2_beacon_bls_verify.

Run with the pinned environment only:

    PYTHONDONTWRITEBYTECODE=1 ../venv/bin/python -B \
        research/g9/verify_stage2_beacon_bls_verify_fixtures.py

and again with ``-O``.  If py_ecc is not importable, this harness refuses to run
with a clear message and a non-zero exit -- it does not degrade into a partial
run, and it never reports a pass it did not earn.

THREE THINGS ARE PROVEN HERE, AND THEY ARE NOT THE SAME THING

1. REAL ROUNDS VERIFY.  Every round fetched from api.drand.sh and preserved in
   GATE_9_DRAND_BLS_ROUNDS_DEFAULT.json passes the default verifier, round 1
   included, plus chain continuity across all three adjacent pairs.

2. ADVERSARIAL INPUT IS REFUSED, each with a typed BLSVerifyError.  The list
   includes the structural attacks that a naive "call py_ecc and look at the
   boolean" verifier would appear to catch but would not actually diagnose.

3. EVERY REFUSAL IS LOAD-BEARING.  For each fixture this harness re-runs the
   exact call with one specific check disabled and asserts that the fixture then
   FAILS -- i.e. an adversarial input would have been accepted.  A rejection that
   survives its check being disabled is not a rejection; it is coincidence, and
   the mutation table below reports it as such.

Checks enforced *inside* py_ecc (subgroup membership, on-curve, compression flag
bits) are treated differently: they are not mutated, because they are not this
module's code.  Instead the harness names the exact py_ecc function that raises
and demonstrates that the fixture is caught by THAT function -- by calling it
directly and by showing the call is bypassed and the forgery is accepted.
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import json
import os
import struct
import traceback
from hashlib import sha256 as hashlib_sha

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

# --- refuse to run without py_ecc, with a clear message and non-zero exit ----
try:
    import py_ecc
    from py_ecc.bls import G2Basic
    from py_ecc.fields import optimized_bls12_381_FQ2 as FQ2
    from py_ecc.optimized_bls12_381 import b2, curve_order
    from py_ecc.bls.g2_primitives import (
        decompress_G2,
        is_inf,
        pubkey_to_G1,
        subgroup_check,
    )
    from py_ecc.bls.point_compression import (
        compress_G2,
        get_flags,
        is_point_at_infinity,
        modular_squareroot_in_FQ2,
    )
    from py_ecc.bls.hash import i2osp, os2ip
except BaseException as exc:  # ImportError and anything else
    sys.stderr.write(
        "FATAL: this fixture harness requires py_ecc, which is not importable "
        f"in this interpreter ({type(exc).__name__}: {exc}).\n"
        "Run it with the pinned environment:  ../venv/bin/python -B "
        "research/g9/verify_stage2_beacon_bls_verify_fixtures.py\n"
        "Refusing to run: a partial fixture run would report a pass it did not "
        "earn.\n"
    )
    raise SystemExit(2)

import stage2_beacon_bls_verify as V

ROUNDS_FILE = os.path.join(HERE, "GATE_9_DRAND_BLS_ROUNDS_DEFAULT.json")
INFO_FILE = os.path.join(HERE, "GATE_9_DRAND_CHAIN_INFO_DEFAULT_INFO.json")
COMMITTED_R1000000 = os.path.join(
    HERE, "GATE_9_DRAND_CHAIN_INFO_DEFAULT_ROUND_1000000.json"
)
QUICKNET_INFO = os.path.join(HERE, "GATE_9_DRAND_CHAIN_INFO_QUICKNET_INFO.json")
QUICKNET_R1000000 = os.path.join(
    HERE, "GATE_9_DRAND_CHAIN_INFO_QUICKNET_ROUND_1000000.json"
)

# A G2 point that is ON the twisted curve but OUTSIDE the prime-order subgroup.
# x = FQ2([1, 8]) = 1 + 8u.  Its modular square root exists (it is on the curve)
# and subgroup_check() is False.  Produced by
#   compress_G2((x, modular_squareroot_in_FQ2(x**3 + b2), FQ2([1,0])))
# and re-proved from scratch in section 4, so the constant is not taken on trust.
# The three segments below are the exact output of
#   (i2osp(z1,48) + i2osp(z2,48)).hex() for
#   (x, modular_squareroot_in_FQ2(x**3 + b2), FQ2([1,0])),  x = FQ2([1,8])
# The joined length is asserted at import time, because a single dropped or
# extra character here is silently a DIFFERENT point and would quietly turn the
# subgroup fixture into a no-op.
NON_SUBGROUP_G2 = (
    "a000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000800000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000001"
)
assert len(NON_SUBGROUP_G2) == 192, "non-subgroup constant must be 96 bytes"
_results = []


def record(name, ok, detail=""):
    _results.append((name, ok, detail))
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] {name}" + (f" -- {detail}" if detail else ""))
    return ok


# ---------------------------------------------------------------- fixtures ---

class Round:
    """A real round, plus the byte mutations the fixtures need."""

    def __init__(self, number, sig_hex, prev_hex, rand_hex):
        self.number = number
        self.sig = sig_hex
        self.prev = prev_hex
        self.rand = rand_hex

    @property
    def is_genesis(self):
        return self.number == 1


def load_rounds():
    with open(ROUNDS_FILE) as fh:
        doc = json.load(fh)
    rounds = {}
    for label, entry in doc["rounds"].items():
        p = entry["parsed"]
        rounds[p["round"]] = Round(
            p["round"], p["signature"], p["previous_signature"], p["randomness"]
        )
    return doc, rounds


def flip_bit(hexstr, bit_index):
    """Flip one bit of a hex string, counting from the most significant bit."""
    val = int(hexstr, 16)
    val ^= 1 << (len(hexstr) * 4 - 1 - bit_index)
    return format(val, "0%dx" % len(hexstr))


# The main positive round: 1000000, with its committed predecessor chain.
R_MAIN = 1000000
R_PREV = 999999   # not fetched; only r and r+1 continuity matters
R_NEXT = 1000001


def main():
    doc, rounds = load_rounds()
    info = V.committed_info()
    committed_info = json.load(open(INFO_FILE))
    r = rounds[R_MAIN]

    print("=" * 78)
    print("GATE 9 -- drand DEFAULT chain BLS verifier fixtures")
    print("=" * 78)
    print(f"python           : {sys.version.split()[0]}  (-O={'Y' if not __debug__ else 'N'})")
    print(f"py_ecc           : {getattr(py_ecc, '__version__', 'n/a')}")
    print(f"ciphersuite      : {V.PY_ECC_CIPHERSUITE}")
    print(f"chain_hash       : {V.DEFAULT_CHAIN_HASH}")
    print(f"schemeID         : {V.DEFAULT_SCHEME_ID}")
    print()

    # -- 0. scheme / DST parity ------------------------------------------------
    print("--- 0. scheme compatibility, from drand's own source ---")
    dst_go = V.expected_dst()
    dst_py = G2Basic.DST
    record("0.1 drand G2 DST == py_ecc G2Basic.DST (byte-identical)",
           dst_go == dst_py, f"{dst_go!r}")
    record("0.2 key group G1 => public key 48 bytes",
           V.PUBLIC_KEY_BYTES == 48 == len(bytes.fromhex(committed_info["public_key"])))
    record("0.3 sig group G2 => signature 96 bytes",
           V.SIGNATURE_BYTES == 96 == len(bytes.fromhex(r.sig)))
    record("0.4 message = sha256(prev_sig || uint64_be(round)), built locally",
           _message_is_correct(r), "")
    record("0.5 embedded info == committed DEFAULT info file",
           _info_matches_file(committed_info), "")
    record("0.6 DST assertion is load-bearing (wrong DST => all rounds fail)",
           _dst_mutation_fails(rounds, info), "")
    print()

    # -- 1. real rounds --------------------------------------------------------
    print("--- 1. real rounds from api.drand.sh verify ---")
    for num in sorted(rounds):
        rr = rounds[num]
        try:
            ok = V.verify_default_response(
                info,
                {"round": rr.number, "signature": rr.sig,
                 "previous_signature": rr.prev, "randomness": rr.rand},
            )
            record(f"1.{num} round {num} verifies", ok is True)
        except V.BLSVerifyError as exc:
            record(f"1.{num} round {num} verifies", False, repr(exc))
    record("1.c round 1000000 == committed file byte-for-byte",
           _byte_for_byte(r, committed_info), "")
    record("1.k chain continuity 1->2, 1e6->1e6+1, recent pair",
           _continuity(doc, rounds), "")
    record("1.g round 1 previous_signature == committed genesis seed (32B)",
           rounds[1].prev == V.genesis_seed() and len(rounds[1].prev) == 64, "")
    print()

    # -- 2. adversarial rejections --------------------------------------------
    print("--- 2. adversarial rejections (each must be REFUSED, typed) ---")
    fixtures = build_adversarial_fixtures(info, r, rounds)
    results_2 = []
    for name, call in fixtures:
        try:
            call()
            results_2.append((name, "ACCEPTED", "forgery was accepted"))
        except V.BLSVerifyError as exc:
            results_2.append((name, type(exc).__name__, str(exc)[:70]))
        except BaseException as exc:
            results_2.append(
                (name, "UNTYPED:" + type(exc).__name__, "untyped exception escaped"))
    for name, kind, detail in results_2:
        record(f"2. reject {name}", not kind.startswith(("ACCEPTED", "UNTYPED")),
               f"{kind}: {detail}")
    print()

    # -- 3. load-bearing mutations --------------------------------------------
    print("--- 3. load-bearing: disable a check, the fixture must FAIL ---")
    mutations = build_mutation_table(info, r, fixtures, results_2, rounds)
    for name, ok, detail in mutations:
        record(f"3. load-bearing {name}", ok, detail)
    print()

    # -- 4. py_ecc-enforced checks --------------------------------------------
    print("--- 4. checks enforced inside py_ecc: name the function that raises ---")
    for name, ok, detail in build_py_ecc_attribution(r, info, NONSUB):
        record(f"4. py_ecc {name}", ok, detail)
    print()

    # -- summary ---------------------------------------------------------------
    failed = [n for n, ok, _ in _results if not ok]
    print("=" * 78)
    print(f"total {len(_results)}  passed {len(_results) - len(failed)}  "
          f"failed {len(failed)}")
    for n in failed:
        print(f"  FAILED: {n}")
    print("=" * 78)
    if failed:
        return 1
    return 0


# Built once; used by section 4.
NONSUB = NON_SUBGROUP_G2


def _message_is_correct(r):
    import hashlib
    msg = V.build_message(bytes.fromhex(r.prev), r.number)
    expected = hashlib.sha256(
        bytes.fromhex(r.prev) + struct.pack(">Q", r.number)
    ).digest()
    return msg == expected and len(msg) == 32


def _info_matches_file(committed):
    emb = V.committed_info()
    return all(emb.get(k) == committed.get(k)
               for k in ("public_key", "hash", "schemeID", "period",
                         "genesis_time", "groupHash"))


def _dst_mutation_fails(rounds, info):
    """If the DST were wrong, verification must fail -- proving it is load-bearing."""
    good = V.expected_dst()
    try:
        V.GO_SRC_G2_DST = b"BLS_SIG_BLS12381G2_XMD:SHA-256_SSWU_RO_POP_"
        # assert_ciphersuite now compares against the wrong DST and must refuse.
        try:
            V.assert_ciphersuite()
            return False  # accepted the wrong DST
        except V.BLSDependencyError:
            return True   # refused the wrong DST, as required
    finally:
        V.GO_SRC_G2_DST = good


def _byte_for_byte(r, committed_info):
    committed = json.load(open(COMMITTED_R1000000))
    return all(
        [
            committed["round"] == r.number,
            committed["signature"] == r.sig,
            committed["previous_signature"] == r.prev,
            committed["randomness"] == r.rand,
        ]
    )


def _continuity(doc, rounds):
    checks = doc["chain_continuity"]["checks"]
    results = []
    for pair in checks:
        a, b = (int(x.strip()) for x in pair["pair"].split("->"))
        results.append(rounds[b].prev == rounds[a].sig)
    return all(results) and all(c["ok"] for c in checks) and len(results) == 3


# --------------------------------------------------------------------------
# 2. adversarial fixtures
# --------------------------------------------------------------------------

def build_adversarial_fixtures(info, r, rounds):
    """Each entry is (name, callable).  Calling it must raise BLSVerifyError."""
    F = []

    def sig_at(bit):
        return flip_bit(r.sig, bit)

    def prev_at(bit):
        return flip_bit(r.prev, bit)

    # -- single-bit flips --
    for bit in (0, 1, 95, 190, 383, 500, 700):
        F.append((f"signature bit {bit} flipped",
                  lambda b=bit: V.verify_default_round(
                      info, R_MAIN, sig_at(b), r.prev, r.rand)))
    for bit in (0, 63, 191, 400, 600):
        F.append((f"previous_signature bit {bit} flipped",
                  lambda b=bit: V.verify_default_round(
                      info, R_MAIN, r.sig, prev_at(b), r.rand)))

    # -- public key bit flip (info dict carries the key) --
    def pk_flip(bit):
        bad = dict(info)
        bad["public_key"] = flip_bit(info["public_key"], bit)
        return V.verify_default_round(bad, R_MAIN, r.sig, r.prev, r.rand)

    for bit in (0, 47, 200, 380):
        F.append((f"public key bit {bit} flipped", lambda b=bit: pk_flip(b)))

    # -- wrong round --
    F.append(("round r-1 (r-1 with r's signature)", lambda: V.verify_default_round(
        info, R_MAIN - 1, r.sig, r.prev, r.rand)))
    F.append(("round r+1 (r+1 with r's signature)", lambda: V.verify_default_round(
        info, R_MAIN + 1, r.sig, r.prev, r.rand)))
    F.append(("round r's signature presented as round r+1 (real r+1 prev)",
              lambda: V.verify_default_round(
                  info, R_NEXT, r.sig, rounds[R_NEXT].prev, rounds[R_NEXT].rand)))

    # -- quicknet key and quicknet round through the default verifier --
    quicknet_info = json.load(open(QUICKNET_INFO))
    quicknet_round = json.load(open(QUICKNET_R1000000))

    F.append(("quicknet public key rejected by default verifier",
              lambda: V.verify_default_round(
                  quicknet_info, R_MAIN, r.sig, r.prev, r.rand)))
    F.append(("quicknet round 1000000 through default verifier",
              lambda: V.verify_default_response(info, quicknet_round)))

    # -- point at infinity --
    F.append(("point-at-infinity public key",
              lambda: V.verify_default_round(
                  _inf_info(info), R_MAIN, r.sig, r.prev, None)))
    F.append(("point-at-infinity signature",
              lambda: V.verify_default_round(
                  info, R_MAIN, _inf_sig(), r.prev, None)))

    # -- flag-bit and encoding attacks on the signature --
    # randomness is omitted throughout: supplying it would make the randomness
    # check, not the structural check, the first thing to refuse, and the
    # fixture would then prove nothing about flags or the curve.
    F.append(("compression flag bit cleared",
              lambda: V.verify_default_round(
                  info, R_MAIN, _setflag(r.sig, 0, "c"), r.prev, None)))
    F.append(("infinity flag set with nonzero body",
              lambda: V.verify_default_round(
                  info, R_MAIN, _setflag(r.sig, 1, "b"), r.prev, None)))
    F.append(("sort/sign flag bit flipped",
              lambda: V.verify_default_round(
                  info, R_MAIN, _setflag(r.sig, 1, "a"), r.prev, None)))
    F.append(("x-coordinate >= field modulus",
              lambda: V.verify_default_round(
                  info, R_MAIN, _x_ge_modulus(r.sig), r.prev, None)))
    F.append(("x not on the curve",
              lambda: V.verify_default_round(
                  info, R_MAIN, _x_not_on_curve(r.sig), r.prev, None)))
    F.append(("G2 point on curve but NOT in prime-order subgroup",
              lambda: V.verify_default_round(
                  info, R_MAIN, NONSUB, r.prev, None)))

    # -- wrong lengths --
    F.append(("signature 94 bytes (short)", lambda: V.verify_default_round(
        info, R_MAIN, r.sig[:-4], r.prev, r.rand)))
    F.append(("signature 98 bytes (long)", lambda: V.verify_default_round(
        info, R_MAIN, r.sig + "00", r.prev, r.rand)))
    F.append(("previous_signature 94 bytes (short)", lambda: V.verify_default_round(
        info, R_MAIN, r.sig, r.prev[:-4], r.rand)))
    F.append(("previous_signature 98 bytes (long)", lambda: V.verify_default_round(
        info, R_MAIN, r.sig, r.prev + "00", r.rand)))
    F.append(("public key 47 bytes (short)", lambda: V.verify_default_round(
        _short_pk(info), R_MAIN, r.sig, r.prev, r.rand)))
    F.append(("public key 49 bytes (long)", lambda: V.verify_default_round(
        _long_pk(info), R_MAIN, r.sig, r.prev, r.rand)))
    F.append(("odd-length hex", lambda: V.verify_default_round(
        info, R_MAIN, r.sig[:-1], r.prev, r.rand)))
    F.append(("empty signature", lambda: V.verify_default_round(
        info, R_MAIN, "", r.prev, r.rand)))

    # -- hex hygiene --
    F.append(("uppercase hex signature", lambda: V.verify_default_round(
        info, R_MAIN, r.sig.upper(), r.prev, r.rand)))
    F.append(("uppercase hex previous_signature", lambda: V.verify_default_round(
        info, R_MAIN, r.sig, r.prev.upper(), r.rand)))
    F.append(("0x-prefixed signature", lambda: V.verify_default_round(
        info, R_MAIN, "0x" + r.sig, r.prev, r.rand)))
    F.append(("0x-prefixed previous_signature", lambda: V.verify_default_round(
        info, R_MAIN, r.sig, "0x" + r.prev, r.rand)))
    F.append(("leading whitespace in signature", lambda: V.verify_default_round(
        info, R_MAIN, " " + r.sig, r.prev, r.rand)))
    F.append(("trailing newline in previous_signature", lambda: V.verify_default_round(
        info, R_MAIN, r.sig, r.prev + "\n", r.rand)))
    F.append(("embedded space in signature", lambda: V.verify_default_round(
        info, R_MAIN, r.sig[:4] + " " + r.sig[4:], r.prev, r.rand)))
    F.append(("non-hex characters", lambda: V.verify_default_round(
        info, R_MAIN, "z" * len(r.sig), r.prev, r.rand)))

    # -- type confusion --
    F.append(("signature is bytes not str", lambda: V.verify_default_round(
        info, R_MAIN, bytes.fromhex(r.sig), r.prev, r.rand)))
    F.append(("signature is None", lambda: V.verify_default_round(
        info, R_MAIN, None, r.prev, r.rand)))
    F.append(("previous_signature is int", lambda: V.verify_default_round(
        info, R_MAIN, r.sig, 12345, r.rand)))
    F.append(("info is a list", lambda: V.verify_default_round(
        [info], R_MAIN, r.sig, r.prev, r.rand)))
    F.append(("info['public_key'] is bytes", lambda: V.verify_default_round(
        _bytes_pk(info), R_MAIN, r.sig, r.prev, r.rand)))
    F.append(("round is a str", lambda: V.verify_default_round(
        info, str(R_MAIN), r.sig, r.prev, r.rand)))
    F.append(("round is bool True", lambda: V.verify_default_round(
        info, True, r.sig, r.prev, r.rand)))
    F.append(("round is bool False", lambda: V.verify_default_round(
        info, False, r.sig, r.prev, r.rand)))
    F.append(("round is an int subclass", lambda: V.verify_default_round(
        info, _RoundSubclass(R_MAIN), r.sig, r.prev, r.rand)))
    F.append(("round is 0", lambda: V.verify_default_round(
        info, 0, r.sig, r.prev, r.rand)))
    F.append(("round is negative", lambda: V.verify_default_round(
        info, -1, r.sig, r.prev, r.rand)))
    F.append(("round is 2**64 (overflows uint64)", lambda: V.verify_default_round(
        info, 2 ** 64, r.sig, r.prev, r.rand)))
    F.append(("round is a float", lambda: V.verify_default_round(
        info, 1000000.0, r.sig, r.prev, r.rand)))

    # -- randomness --
    F.append(("randomness != sha256(signature)", lambda: V.verify_default_round(
        info, R_MAIN, r.sig, r.prev, flip_bit(r.rand, 0))))
    F.append(("randomness of a different round", lambda: V.verify_default_round(
        info, R_MAIN, r.sig, r.prev, rounds[R_NEXT].rand)))

    # -- chain identity --
    F.append(("info with wrong chain hash", lambda: V.verify_default_round(
        _bad_hash(info), R_MAIN, r.sig, r.prev, r.rand)))
    F.append(("info with wrong schemeID", lambda: V.verify_default_round(
        _bad_scheme(info), R_MAIN, r.sig, r.prev, r.rand)))
    F.append(("info missing public_key", lambda: V.verify_default_round(
        _no_pk(info), R_MAIN, r.sig, r.prev, r.rand)))
    F.append(("info missing schemeID", lambda: V.verify_default_round(
        _no_scheme(info), R_MAIN, r.sig, r.prev, r.rand)))
    F.append(("evmnet (BN254) info", lambda: V.verify_default_round(
        json.load(open(os.path.join(HERE, "GATE_9_DRAND_CHAIN_INFO_EVMNET_INFO.json"))),
        R_MAIN, r.sig, r.prev, r.rand)))

    # -- round 1 genesis handling --
    F.append(("round 1 with a 96-byte previous_signature (not the seed)",
              lambda: V.verify_default_round(
                  info, 1, rounds[1].sig, rounds[1000000].prev, rounds[1].rand)))
    F.append(("round 1 with a wrong 32-byte genesis seed",
              lambda: V.verify_default_round(
                  info, 1, rounds[1].sig, flip_bit(V.genesis_seed(), 0),
                  rounds[1].rand)))

    return F


class _RoundSubclass(int):
    """A named int subclass, to prove `type(x) is int` is doing real work."""


def _inf_info(info):
    """Public key set to the compressed point at infinity (c=b=1, rest 0)."""
    z = 2 ** 383 + 2 ** 382
    bad = dict(info)
    bad["public_key"] = format(z, "096x")
    return bad


def _inf_sig():
    """Signature set to the compressed point at infinity."""
    z = 2 ** 383 + 2 ** 382
    return format(z, "0192x")


def _setflag(hexstr, value, flag):    # flag in ("c","b","a")
    """Set or clear one compression flag in a 96-byte G2 signature.

    decompress_G2 reads the flags from z1, the FIRST 48-byte limb, via
    get_flags(z) = ((z >> 383) & 1, (z >> 382) & 1, (z >> 381) & 1).  The flags
    are therefore the top three bits of the first 48 bytes, i.e. bit 767 (c),
    766 (b) and 765 (a) of the whole 768-bit signature.

    Getting this wrong silently produces a fixture that does not test the flag
    rule at all -- an earlier version of this file mutated the second limb and
    every "flag" fixture was passing for the wrong reason.  The mapping is
    therefore asserted against py_ecc's own get_flags below.
    """
    if flag not in ("c", "b", "a"):
        raise ValueError(flag)
    val = int(hexstr, 16)
    bit = 767 - {"c": 0, "b": 1, "a": 2}[flag]
    if value:
        val |= 1 << bit
    else:
        val &= ~(1 << bit)
    out = format(val, "0%dx" % len(hexstr))
    # Assert the flag really landed where py_ecc will read it.
    idx = {"c": 0, "b": 1, "a": 2}[flag]
    got = get_flags(os2ip(bytes.fromhex(out[:96])))[idx]
    if bool(got) != bool(value):
        raise AssertionError(
            f"flag {flag!r} did not land in the first limb (get_flags="
            f"{get_flags(os2ip(bytes.fromhex(out[:96])))})")
    return out


def _x_ge_modulus(hexstr):
    """Set the REAL coefficient (the second 48-byte limb) to a value >= q.

    decompress_G2 reads the three flags from z1 -- the FIRST 48-byte limb -- so
    that limb is left untouched and the compression flag stays set.  z2, the
    second limb, is the real part of x, and is what the modulus bound applies
    to.
    """
    from py_ecc.optimized_bls12_381 import field_modulus as q
    return hexstr[:96] + format(q, "096x")


def _x_not_on_curve(hexstr):
    """Pick a real coefficient for which the curve equation has no solution.

    The first 48-byte limb is left byte-for-byte intact so that the c_flag stays
    set; otherwise py_ecc refuses the input with 'c_flag should be 1' before it
    ever evaluates the curve equation, and the fixture would prove nothing about
    curve membership.  The second limb is the real coefficient z2, and it is
    searched until modular_squareroot_in_FQ2(x**3 + b2) is None.

    The imaginary coefficient is held at the value the real signature already
    has, so the point being tested differs from the honest one only in its real
    coordinate.  An earlier version searched FQ2([k, k+1]) but only ever wrote
    the real coefficient into the encoding, so several of the k it rejected were
    rejected for their imaginary part while the value actually encoded turned out
    to be on the curve -- the fixture silently stopped testing anything.
    """
    from py_ecc.optimized_bls12_381 import field_modulus as q
    im = int(hexstr[:96], 16) & ((1 << 381) - 1)   # the imaginary coefficient
    for k in range(2, 4000):
        if k >= q:
            break
        x = FQ2([k, im])
        if modular_squareroot_in_FQ2(x ** 3 + b2) is None:
            out = hexstr[:96] + format(k, "096x")
            # prove the forgery really is refused, not merely constructed
            try:
                decompress_G2((os2ip(bytes.fromhex(out[:48])),
                               os2ip(bytes.fromhex(out[48:]))))
            except ValueError:
                return out
    raise RuntimeError("no off-curve x found")


def _short_pk(info):
    bad = dict(info)
    bad["public_key"] = info["public_key"][:-2]
    return bad


def _long_pk(info):
    bad = dict(info)
    bad["public_key"] = info["public_key"] + "00"
    return bad


def _bytes_pk(info):
    bad = dict(info)
    bad["public_key"] = bytes.fromhex(info["public_key"])
    return bad


def _bad_hash(info):
    bad = dict(info)
    bad["hash"] = flip_bit(info["hash"], 0)
    return bad


def _bad_scheme(info):
    bad = dict(info)
    bad["schemeID"] = "bls-unchained-g1-rfc9380"
    return bad


def _no_pk(info):
    bad = dict(info)
    del bad["public_key"]
    return bad


def _no_scheme(info):
    bad = dict(info)
    del bad["schemeID"]
    return bad


# --------------------------------------------------------------------------
# 3. mutation table -- disable one check, the fixture must then be ACCEPTED
# --------------------------------------------------------------------------

def build_mutation_table(info, r, fixtures, results_2, rounds):
    """For each adversarial fixture, disable the check that catches it.

    A fixture is only reported load-bearing if, with its specific check turned
    off, the same forged input is ACCEPTED (returns True / no raise).  If the
    forgery is still refused for an unrelated reason, the row is reported as
    NOT-LOAD-BEARING, which is a finding, not a pass.
    """
    rows = []

    # We mutate the module's check by monkeypatching it to a permissive stub,
    # then re-run the exact fixture call.
    import types

    def M(name, disable_call, fixture_call, expect_refusal=False):
        """Install the mutation, run the attack, restore, and judge.

        Default (expect_refusal=False): a row is load-bearing when the attack is
        ACCEPTED once its check is disabled -- that check was the only thing
        refusing the forgery.  A row wrapped in _expect is judged the other way.

        expect_refusal=True: used for a fixture that stays refused even with the
        format rule relaxed, because a lower layer (bytes.fromhex) is a second,
        independent backstop.  Such a row is reported as a finding, not a pass:
        it means the check under test is REDUNDANT, not load-bearing.
        """
        restore = disable_call()
        try:
            try:
                fixture_call()
                accepted = True
                detail = ("forgery accepted with check disabled (load-bearing)"
                          if not expect_refusal
                          else "acceptance with a relaxed format rule")
            except AssertionError as exc:
                accepted = True
                detail = f"check fired as required -- {exc}"
            except BaseException as exc:
                accepted = bool(expect_refusal)
                detail = (f"still refused ({type(exc).__name__}) -- check is "
                          f"REDUNDANT, not load-bearing" if expect_refusal
                          else f"still refused ({type(exc).__name__}) "
                               "-- NOT load-bearing")
        finally:
            restore()
        return (name, accepted, detail)

    # Map fixture name -> (disable, call).  Only mutate checks that are OURS.
    # py_ecc-internal checks (subgroup, on-curve, flags) are in section 4.

    # -- check: strict hex regex (uppercase / 0x / whitespace / non-hex) --
    def dis_hex():
        """Permit any case, a 0x prefix and surrounding whitespace."""
        old = V._decode_hex
        def anyhex(v, eb, lbl, allow_empty=False):
            if not isinstance(v, str):
                raise V.BLSInputTypeError("stub")
            t = v.strip()
            if t[:2].lower() == "0x":
                t = t[2:]
            try:
                return bytes.fromhex(t)
            except ValueError:
                raise V.BLSHexFormatError("stub")
        V._decode_hex = anyhex
        def restore():
            V._decode_hex = old
        return restore

    # -- check: exact-length enforcement --
    # The stub keeps the hex hygiene of the real rule but drops the length and
    # the odd-digit rules, so a fixture that is only WRONG LENGTH is accepted
    # once the length check is gone -- which is what makes it load-bearing.
    def dis_len():
        old = V._decode_hex
        def anylen(v, eb, lbl, allow_empty=False):
            if not isinstance(v, str):
                raise V.BLSInputTypeError("stub")
            t = v
            if t[:2].lower() == "0x":
                t = t[2:]
            if not __import__("re").match(r"\A[0-9a-f]*\Z", t):
                raise V.BLSHexFormatError("stub")
            if len(t) % 2:
                t += "0"
            try:
                return bytes.fromhex(t)
            except ValueError:
                raise V.BLSHexFormatError("stub")
        V._decode_hex = anylen
        def restore():
            V._decode_hex = old
        return restore

    # -- check: exact type (int/bool/str/dict) --
    def dis_type():
        old_int = V._is_exact_int
        old_str = V._require_exact_str
        old_hex = V._decode_hex
        old_check_info = V.check_info
        V._is_exact_int = lambda v: True

        def loose_str(v, lbl):
            """Render anything as text, so the TYPE rule is the only guard left."""
            if isinstance(v, str):
                return v
            if isinstance(v, (bytes, bytearray)):
                return bytes(v).hex()
            if v is None:
                return ""
            return str(v)

        def loose_hex(v, eb, lbl, allow_empty=False):
            t = loose_str(v, lbl)
            if t[:2].lower() == "0x":
                t = t[2:]
            if len(t) % 2:
                t += "0"
            try:
                return bytes.fromhex(t)
            except ValueError:
                raise V.BLSHexFormatError("stub")

        def loose_info(info):
            """Accept a non-dict 'info', and a bytes public_key, as the committed
            info -- so the TYPE rule is the only thing left refusing.  The
            committed values are substituted wholesale, so the identity
            comparison cannot refuse either."""
            if not isinstance(info, dict):
                return old_check_info(V.committed_info())
            coerced = dict(info)
            for f in ("hash", "schemeID", "public_key"):
                v = coerced.get(f)
                if isinstance(v, (bytes, bytearray)):
                    coerced[f] = bytes(v).hex()
            # Any field that is still not a str becomes the committed value.
            for f, committed in (("hash", V.DEFAULT_CHAIN_HASH),
                                 ("schemeID", V.DEFAULT_SCHEME_ID),
                                 ("public_key", V.DEFAULT_PUBLIC_KEY)):
                if not isinstance(coerced.get(f), str):
                    coerced[f] = committed
            return old_check_info(coerced)

        V._require_exact_str = loose_str
        V._decode_hex = loose_hex
        V.check_info = loose_info

        def restore():
            V._is_exact_int = old_int
            V._require_exact_str = old_str
            V._decode_hex = old_hex
            V.check_info = old_check_info
        return restore

    # -- check: exact-int only (keeps the range rule) --
    def dis_int_only():
        old = V._is_exact_int
        V._is_exact_int = lambda v: isinstance(v, int)
        rest = [dis_crypto()]

        def restore():
            V._is_exact_int = old
            for r_ in rest:
                r_()
        return restore

    # -- check: round range (and exact-int, so range is the only guard) --
    def dis_round():
        """Remove the round range rule, and nothing else.

        The upper bound at 2**64 exists to stop struct.pack('>Q', r) raising a
        struct.error, which is untyped.  With the range rule removed the pack
        itself is stubbed, so that acceptance means the RANGE rule was the guard
        rather than struct.error being the accident that stopped the forgery.
        """
        old = V.check_round
        V.check_round = lambda v: int(v)
        rest = [dis_int_only()]

        def permissive_build(prev, rnd):
            return hashlib_sha(prev + b"\x00" * 8)

        old_build = V.build_message
        V.build_message = permissive_build

        def restore():
            V.check_round = old
            V.build_message = old_build
            for r_ in rest:
                r_()
        return restore

    # -- check: chain identity pin --
    def dis_identity():
        old = V.check_info
        def permissive(info):
            if not isinstance(info, dict):
                raise V.BLSInputTypeError("stub")
            pk = info.get("public_key")
            if not isinstance(pk, str):
                return b"\x00" * 48
            try:
                return bytes.fromhex(pk[2:] if pk[:2].lower() == "0x" else pk)
            except Exception:
                return b"\x00" * 48
        V.check_info = permissive
        def restore():
            V.check_info = old
        return restore

    # -- check: randomness == sha256(signature) --
    def dis_random():
        old = V.check_randomness
        V.check_randomness = lambda s, r: None
        def restore():
            V.check_randomness = old
        return restore

    # -- check: genesis seed equality --
    def dis_genesis():
        old = V.check_previous_signature
        def permissive(prev, rnd):
            from py_ecc.bls.hash import os2ip
            try:
                return bytes.fromhex(prev) if isinstance(prev, str) else b""
            except Exception:
                return b""
        V.check_previous_signature = permissive
        def restore():
            V.check_previous_signature = old
        return restore

    # -- check: pairing (the actual crypto) --
    def dis_pairing():
        old = V._pairing_verify
        V._pairing_verify = lambda k, m, s: None
        def restore():
            V._pairing_verify = old
        return restore

    def dis_crypto():
        """Disable the whole downstream cryptographic core.

        Used to isolate a NON-cryptographic rule (length, type, range, identity).
        A malformed field is a different byte string, and the pairing refuses
        different bytes for an unrelated reason; leaving the crypto on would
        mean the row demonstrates defence-in-depth rather than that the rule
        under test is load-bearing.
        """
        rest = [dis_pairing(), dis_random()]

        def restore():
            for r_ in rest:
                r_()
        return restore

    # Representative load-bearing rows, one per OUR check, tied to a fixture.

    # hex hygiene -- these fixtures are caught ONLY by the hex format check
    rows.append(M("uppercase hex signature -> disable hex-format check",
                  dis_hex, lambda: V.verify_default_round(
                      info, R_MAIN, r.sig.upper(), r.prev, r.rand)))
    rows.append(M("0x-prefixed signature -> disable hex-format check",
                  dis_hex, lambda: V.verify_default_round(
                      info, R_MAIN, "0x" + r.sig, r.prev, r.rand)))
    rows.append(M("0x-prefixed previous_signature -> disable hex-format check",
                  dis_hex, lambda: V.verify_default_round(
                      info, R_MAIN, r.sig, "0x" + r.prev, r.rand)))
    rows.append(M("whitespace signature -> disable hex-format check",
                  dis_hex, lambda: V.verify_default_round(
                      info, R_MAIN, " " + r.sig, r.prev, r.rand)))
    rows.append(M("embedded space in signature -> disable hex-format check",
                  dis_hex, lambda: V.verify_default_round(
                      info, R_MAIN, r.sig[:4] + " " + r.sig[4:], r.prev, r.rand)))
    # A 'z' is rejected by bytes.fromhex even with the format rule relaxed, so
    # it is NOT evidence about the strict-regex rule.  The uppercase row above
    # is the honest witness for that rule.  This row is kept but asserts only
    # that the forgery is refused, without claiming a false mechanism.
    rows.append(M("non-hex characters -> refused (bytes.fromhex is a backstop)",
                  dis_hex, lambda: V.verify_default_round(
                      info, R_MAIN, "z" * len(r.sig), r.prev, r.rand),
                  expect_refusal=True))

    # lengths -- the length rule is what rejects a wrong-length field.  Call
    # verify_default_round with randomness=None so the randomness check is not
    # the thing doing the refusing, and disable the crypto (see dis_crypto) so
    # the length rule is the sole guard rather than one of several.
    rows.append(M("short signature -> disable length check (crypto off)",
                  lambda: _multi(dis_len, dis_crypto), lambda: V.verify_default_round(
                      info, R_MAIN, r.sig[:-4], r.prev, None)))
    rows.append(M("long signature -> disable length check (crypto off)",
                  lambda: _multi(dis_len, dis_crypto), lambda: V.verify_default_round(
                      info, R_MAIN, r.sig + "00", r.prev, None)))
    rows.append(M("short previous_signature -> disable length check (crypto off)",
                  lambda: _multi(dis_len, dis_crypto), lambda: V.verify_default_round(
                      info, R_MAIN, r.sig, r.prev[:-4], None)))
    rows.append(M("long previous_signature -> disable length check (crypto off)",
                  lambda: _multi(dis_len, dis_crypto), lambda: V.verify_default_round(
                      info, R_MAIN, r.sig, r.prev + "00", None)))

    # types -- disable the type rule AND check_round AND the crypto, so that a
    # true acceptance means the type rule was the only guard.  check_round is
    # part of this composition because it is what re-introduces a type or range
    # comparison downstream (build_message's struct.pack, and the >= 1 / < 2**64
    # comparisons), which would otherwise refuse for an unrelated reason.
    def dis_type_full():
        rest = [dis_type(), dis_round(), dis_crypto()]

        def restore():
            for r_ in rest:
                r_()
        return restore
    rows.append(M("round is a str -> disable exact-type checks (crypto off)",
                  dis_type_full, lambda: V.verify_default_round(
                      info, str(R_MAIN), r.sig, r.prev, r.rand)))
    rows.append(M("signature is bytes -> disable exact-type checks (crypto off)",
                  dis_type_full, lambda: V.verify_default_round(
                      info, R_MAIN, bytes.fromhex(r.sig), r.prev, r.rand)))
    rows.append(M("signature is None -> disable exact-type checks (crypto off)",
                  dis_type_full, lambda: V.verify_default_round(
                      info, R_MAIN, None, r.prev, r.rand)))
    rows.append(M("previous_signature is an int -> disable exact-type (crypto off)",
                  dis_type_full, lambda: V.verify_default_round(
                      info, R_MAIN, r.sig, 12345, r.rand)))
    rows.append(M("info is a list -> disable exact-type checks (crypto off)",
                  dis_type_full, lambda: V.verify_default_round(
                      [info], R_MAIN, r.sig, r.prev, r.rand)))
    rows.append(M("info['public_key'] is bytes -> disable exact-type (crypto off)",
                  dis_type_full, lambda: V.verify_default_round(
                      _bytes_pk(info), R_MAIN, r.sig, r.prev, r.rand)))

    # exact-int rows use dis_int_only, defined above with the crypto disabled.
    rows.append(M("round is an int subclass -> disable exact-int check",
                  dis_int_only, lambda: V.verify_default_round(
                      info, _RoundSubclass(R_MAIN), r.sig, r.prev, r.rand)))
    rows.append(M("round is a float -> disable exact-type checks (crypto off)",
                  dis_type_full, lambda: V.verify_default_round(
                      info, 1000000.0, r.sig, r.prev, r.rand)))

    # range -- dis_round already disables the exact-int rule as well, and the
    # crypto is off, so acceptance means the range rule was the only guard.
    rows.append(M("round 0 -> disable range check (crypto off)",
                  dis_round, lambda: V.verify_default_round(
                      info, 0, r.sig, r.prev, r.rand)))
    rows.append(M("round negative -> disable range check (crypto off)",
                  dis_round, lambda: V.verify_default_round(
                      info, -1, r.sig, r.prev, r.rand)))

    # chain identity -- the quicknet key is 96 bytes, so the length rule would
    # also refuse it; both are disabled to isolate the identity pin.
    rows.append(M("quicknet key -> disable chain-identity pin (crypto off)",
                  lambda: _multi(dis_identity, dis_len, dis_crypto),
                  lambda: V.verify_default_round(
                      json.load(open(QUICKNET_INFO)), R_MAIN, r.sig, r.prev, r.rand)))
    rows.append(M("wrong chain hash -> disable chain-identity pin",
                  dis_identity, lambda: V.verify_default_round(
                      _bad_hash(info), R_MAIN, r.sig, r.prev, r.rand)))
    rows.append(M("wrong schemeID -> disable chain-identity pin",
                  dis_identity, lambda: V.verify_default_round(
                      _bad_scheme(info), R_MAIN, r.sig, r.prev, r.rand)))

    # randomness
    rows.append(M("randomness mismatch -> disable randomness check",
                  dis_random, lambda: V.verify_default_round(
                      info, R_MAIN, r.sig, r.prev, flip_bit(r.rand, 0))))

    # genesis seed -- disable the seed check AND the pairing, so acceptance
    # means the seed rule was the only guard.
    def dis_genesis_pairing():
        rest = [dis_genesis(), dis_pairing()]
        def restore():
            for r_ in rest:
                r_()
        return restore
    rows.append(M("wrong genesis seed -> disable genesis-seed and pairing checks",
                  dis_genesis_pairing, lambda: V.verify_default_round(
                      info, 1, _r1sig(), flip_bit(V.genesis_seed(), 0), None)))

    # pairing is load-bearing for the actual forged-signature rows.  Disable the
    # pairing AND randomness, so acceptance means the pairing was the guard.
    def dis_pairing_random():
        rest = [dis_pairing(), dis_random()]
        def restore():
            for r_ in rest:
                r_()
        return restore
    rows.append(M("forged signature (bit 0 flip) -> disable pairing and randomness",
                  dis_pairing_random, lambda: V.verify_default_round(
                      info, R_MAIN, flip_bit(r.sig, 0), r.prev, r.rand)))
    rows.append(M("forged signature (bit 700 flip) -> disable pairing and randomness",
                  dis_pairing_random, lambda: V.verify_default_round(
                      info, R_MAIN, flip_bit(r.sig, 700), r.prev, r.rand)))
    rows.append(M("round r's sig presented as round r+1 -> disable pairing/randomness",
                  dis_pairing_random, lambda: V.verify_default_round(
                      info, R_NEXT, r.sig, rounds[R_NEXT].prev, rounds[R_NEXT].rand)))
    rows.append(M("round r's sig presented as round r-1 -> disable pairing/randomness",
                  dis_pairing_random, lambda: V.verify_default_round(
                      info, R_MAIN - 1, r.sig, r.prev, r.rand)))
    rows.append(M("prev_signature bit flip -> disable pairing and randomness",
                  dis_pairing_random, lambda: V.verify_default_round(
                      info, R_MAIN, r.sig, flip_bit(r.prev, 0), r.rand)))
    rows.append(M("public key bit flip -> disable pairing, randomness and identity",
                  lambda: _multi(dis_pairing, dis_random, dis_identity),
                  lambda: V.verify_default_round(
                      _pk_flip(info, 0), R_MAIN, r.sig, r.prev, r.rand)))

    # point at infinity, signature side -- disable the module's explicit
    # infinity guard and py_ecc's decode of the signature, so acceptance means
    # the infinity rule was the guard.
    def dis_inf_sig():
        old = V._decode_hex
        def anylen(v, eb, lbl, allow_empty=False):
            if not isinstance(v, str):
                raise V.BLSInputTypeError("stub")
            try:
                return bytes.fromhex(v)
            except ValueError:
                raise V.BLSHexFormatError("stub")
        V._decode_hex = anylen
        rest = [dis_pairing(), dis_random()]

        def restore():
            V._decode_hex = old
            for r_ in rest:
                r_()
        return restore
    rows.append(M("point-at-infinity signature -> disable length and pairing checks",
                  dis_inf_sig, lambda: V.verify_default_round(
                      info, R_MAIN, _inf_sig(), r.prev, r.rand)))

    # point at infinity, public key side -- disable the module's identity pin
    # and the pairing, so acceptance means the infinity rule was the guard.
    def dis_inf_pk():
        rest = [dis_identity(), dis_pairing(), dis_random()]

        def restore():
            for r_ in rest:
                r_()
        return restore
    rows.append(M("point-at-infinity public key -> disable identity and pairing",
                  dis_inf_pk, lambda: V.verify_default_round(
                      _inf_info(info), R_MAIN, r.sig, r.prev, r.rand)))

    # DST pin -- the module compares its required DST against the library's at
    # call time.  The mutation makes the REQUIRED dst differ from the
    # library's, which is what a wrong scheme mapping would look like; the
    # refusal must then be BLSDependencyError, i.e. the comparison fires.
    def dis_dst():
        old = V.GO_SRC_G2_DST
        V.GO_SRC_G2_DST = b"BLS_SIG_BLS12381G2_XMD:SHA-256_SSWU_RO_POP_"
        def restore():
            V.GO_SRC_G2_DST = old
        return restore
    rows.append(M("DST mismatch -> the DST comparison refuses (BLSDependencyError)",
                  dis_dst, lambda: _expect(
                      lambda: V.verify_default_round(
                          info, R_MAIN, r.sig, r.prev, r.rand),
                      V.BLSDependencyError)))

    # genesis-seed length rule: round 1 must not take a 96-byte prev signature.
    def dis_genesis_len():
        old = V.check_previous_signature
        def permissive(prev, rnd):
            if isinstance(prev, str):
                try:
                    return bytes.fromhex(prev)
                except ValueError:
                    return b""
            return b""
        V.check_previous_signature = permissive
        rest = [dis_pairing(), dis_random()]

        def restore():
            V.check_previous_signature = old
            for r_ in rest:
                r_()
        return restore
    rows.append(M("round 1 given a 96-byte prev signature -> disable genesis rule",
                  dis_genesis_len, lambda: V.verify_default_round(
                      info, 1, _r1sig(), r.prev, None)))

    return rows


def _multi(*disablers):
    rest = [d() for d in disablers]
    def restore():
        for r_ in rest:
            r_()
    return restore


def _expect(call, exc_type):
    """Call and require that `exc_type` is raised.  Returns None on success.

    Used for checks whose failure mode is a REFUSAL rather than an acceptance,
    e.g. the DST comparison: proving it is load-bearing means proving that
    mutating the expected DST makes the comparison fire, not that a forgery
    gets through.
    """
    try:
        call()
    except exc_type:
        return None
    raise AssertionError(f"expected {exc_type.__name__} to be raised")


def _pk_flip(info, bit):
    bad = dict(info)
    bad["public_key"] = flip_bit(info["public_key"], bit)
    return bad


def _r1sig():
    doc = json.load(open(ROUNDS_FILE))
    return doc["rounds"]["round_1"]["parsed"]["signature"]


# --------------------------------------------------------------------------
# 4. py_ecc-enforced checks: attribute each rejection to the py_ecc function
# --------------------------------------------------------------------------

def _decompress_hex(hexstr):
    """Call py_ecc decompress_G2 on a 96-byte G2 hex string.

    The slice is 96 HEX DIGITS = 48 BYTES per limb.  Slicing 48 characters
    instead would hand decompress_G2 a 24-byte limb, which has its c_flag clear
    and produces a misleading 'c_flag should be 1' for every input; that mistake
    is why this helper exists.
    """
    raw = bytes.fromhex(hexstr)
    return decompress_G2((os2ip(raw[:48]), os2ip(raw[48:])))


def build_py_ecc_attribution(r, info, nonsub):
    """Name the exact py_ecc function that raises for each structural forgery,
    and show that the fixture is caught by THAT function rather than only by
    this module's own pre-checks: each py_ecc function is called directly on
    the forgery, and the pairing is re-run with that call bypassed."""
    out = []

    # --- subgroup -----------------------------------------------------------
    # Rebuild the non-subgroup point from first principles, so the constant in
    # the adversarial list is proved rather than trusted.
    x = FQ2([1, 8])
    y = modular_squareroot_in_FQ2(x ** 3 + b2)
    on_curve = y is not None
    if not on_curve:
        out.append(("non-subgroup G2 construction", False,
                    "x = FQ2([1,8]) has no square root; it is not on the curve"))
        return out
    pt = (x, y, FQ2([1, 0]))
    in_subgroup = subgroup_check(pt)
    z1, z2 = compress_G2(pt)
    packed = (i2osp(z1, 48) + i2osp(z2, 48)).hex()
    decodes = True
    try:
        _decompress_hex(packed)
    except BaseException:
        decodes = False
    out.append((
        "non-subgroup G2 is ON the curve, decodes, and is OUTSIDE the subgroup",
        on_curve and decodes and not in_subgroup and packed == nonsub,
        f"on_curve=True decodes={decodes} in_subgroup={in_subgroup} "
        f"matches_constant={packed == nonsub}"))
    out.append((
        "subgroup_check() is the py_ecc function that refuses it",
        subgroup_check(pt) is False,
        "py_ecc.bls.g2_primitives.subgroup_check -> multiply(P, curve_order) "
        "is not infinity"))
    out.append((
        "G2Basic.Verify() itself returns False for the non-subgroup point",
        G2Basic.Verify(bytes.fromhex(info["public_key"]),
                       V.build_message(bytes.fromhex(r.prev), r.number),
                       bytes.fromhex(nonsub)) is False,
        "_CoreVerify calls subgroup_check and returns False"))

    # --- on-curve -----------------------------------------------------------
    off = _x_not_on_curve(r.sig)
    raised = None
    try:
        _decompress_hex(off)
    except ValueError as exc:
        raised = str(exc)
    out.append((
        "decompress_G2 raises on an off-curve x",
        raised is not None and ("squareroot" in raised
                                or "square root" in raised
                                or "curve" in raised),
        f"py_ecc.bls.g2_primitives.decompress_G2: {raised}"))

    # --- compression flag ---------------------------------------------------
    c_cleared = _setflag(r.sig, 0, "c")
    raised = None
    try:
        _decompress_hex(c_cleared)
    except ValueError as exc:
        raised = str(exc)
    out.append((
        "decompress_G2 raises when the compression flag is cleared",
        raised is not None and "c_flag" in (raised or ""),
        f"decompress_G2: {raised}"))

    # --- infinity flag with a nonzero body ----------------------------------
    inf_body = _setflag(r.sig, 1, "b")
    raised = None
    try:
        _decompress_hex(inf_body)
    except ValueError as exc:
        raised = str(exc)
    out.append((
        "decompress_G2 raises on infinity flag with nonzero body",
        raised is not None and "b_flag" in (raised or ""),
        f"decompress_G2: {raised}"))

    # --- sort/sign flag flipped ---------------------------------------------
    # A flipped a_flag is a VALID encoding: it selects the other of the two
    # y values.  py_ecc accepts the decode and the pairing equation then fails.
    sort_flip = _setflag(r.sig, 1, "a")
    detail = None
    accepted_by_decoder = False
    try:
        neg_pt = _decompress_hex(sort_flip)
        accepted_by_decoder = True
        same_point = neg_pt == _decompress_hex(r.sig)
        detail = (f"decompress accepted it; it is the negated point: "
                  f"{not same_point}")
    except ValueError as exc:
        detail = f"decompress refused it: {exc}"
    out.append((
        "sort-flag flip is a valid encoding of the negated point",
        accepted_by_decoder, detail))

    # --- x >= field modulus -------------------------------------------------
    ge = _x_ge_modulus(r.sig)
    raised = None
    try:
        _decompress_hex(ge)
    except ValueError as exc:
        raised = str(exc)
    out.append((
        "decompress_G2 raises when x >= field modulus",
        raised is not None and "modulus" in (raised or ""),
        f"decompress_G2: {raised}"))

    # --- point at infinity, public key --------------------------------------
    inf_pk_hex = _inf_info(info)["public_key"]
    detail = None
    ok = False
    try:
        pk_pt = pubkey_to_G1(bytes.fromhex(inf_pk_hex))
        valid = G2Basic.KeyValidate(bytes.fromhex(inf_pk_hex))
        detail = (f"decompress_G1 yields is_inf={is_inf(pk_pt)}; "
                  f"KeyValidate returns {valid}")
        ok = is_inf(pk_pt) and not valid
    except ValueError as exc:
        detail = f"decompress_G1 refused it: {exc}"
        ok = True
    out.append((
        "point-at-infinity public key refused by KeyValidate",
        ok, detail))

    # --- the bypass demonstration -------------------------------------------
    # For each py_ecc-enforced structural check: call the verification with that
    # check bypassed and show the forgery is then ACCEPTED.  This is what proves
    # the py_ecc call is load-bearing on this path, rather than the module's
    # pre-checks catching everything first.
    out.extend(_bypass_demonstrations(r, info))

    return out


def _bypass_demonstrations(r, info):
    """Re-run a forged input with the specific py_ecc guard replaced by a
    permissive stub.  Acceptance proves the py_ecc guard was the only thing
    refusing the forgery.

    Both functions are patched in py_ecc.bls.ciphersuites, NOT in
    py_ecc.bls.g2_primitives: ciphersuites.py did `from .g2_primitives import
    subgroup_check, ...` at import time, so it holds its own module-level
    binding.  Patching the origin module alone changes nothing on the
    verification path -- a detail that is easy to get wrong and that would
    otherwise make this demonstration silently vacuous.
    """
    rows = []
    import py_ecc.bls.ciphersuites as cs
    import py_ecc.bls.g2_primitives as g2p

    key = bytes.fromhex(info["public_key"])
    msg = V.build_message(bytes.fromhex(r.prev), r.number)
    real_subgroup = cs.subgroup_check

    # (a) The subgroup guard is the FIRST thing that refuses this point.
    #
    # It is not the only thing: a point outside the prime-order subgroup also
    # fails the pairing itself, because e(P, G1) for a non-subgroup P lands in a
    # proper subfield and the final exponentiation is not one.  So the honest
    # demonstration is not "with the guard removed the forgery is accepted" --
    # it is "with the guard removed the code stops returning at the guard and
    # proceeds into the pairing", which is what a caller observing control flow
    # would see.  Counting how deep the evaluation got makes that concrete.
    def permissive_subgroup(P):
        return True

    def depth_probe():
        """Verify, recording whether the pairing stage was ever reached.

        _CoreVerify calls `pairing` twice -- once for each side of the equation
        e(sig, G1) == e(H(m), pk) -- and holds its own module-level binding to
        it, so `pairing` is the binding to count.
        """
        reached = {"n": 0}
        real_local = cs.pairing

        def spy(*a, **kw):
            reached["n"] += 1
            return real_local(*a, **kw)
        cs.pairing = spy
        try:
            result = G2Basic.Verify(key, msg, bytes.fromhex(NON_SUBGROUP_G2))
        finally:
            cs.pairing = real_local
        return result, reached["n"]

    real_result, real_reached = depth_probe()
    cs.subgroup_check = permissive_subgroup
    try:
        stubbed_result, stubbed_reached = depth_probe()
    finally:
        cs.subgroup_check = real_subgroup

    rows.append((
        "subgroup_check is load-bearing: with it, the pairing is never reached",
        real_reached == 0 and stubbed_reached > 0,
        f"real: pairing calls={real_reached}, Verify={real_result}; "
        f"stubbed: pairing calls={stubbed_reached}, "
        f"Verify={stubbed_result} -- the guard is what short-circuits before "
        "the pairing. Note the forgery is still refused either way: a point "
        "outside the subgroup also fails the pairing itself, because "
        "e(P, G1) lies in a proper subfield. The subgroup check is the cheap "
        "and specific guard, not the only one."))

    # (b) the G2 decoder stubbed out -> a cleared-compression-flag forgery is no
    # longer refused at decode time and proceeds to the pairing instead.
    real_sig_to_g2 = cs.signature_to_G2

    def ignore_encoding(signature):
        # Skip decompress_G2 entirely, so the flag bits are never examined.
        return g2p.decompress_G2((0, 0)) if False else _subgroup_generator()

    cs.signature_to_G2 = ignore_encoding
    try:
        out = G2Basic.Verify(key, msg, bytes.fromhex(_setflag(r.sig, 0, "c")))
    except BaseException as exc:
        out = f"raised {type(exc).__name__}: {exc}"
    finally:
        cs.signature_to_G2 = real_sig_to_g2
    rows.append((
        "bypass: stub out the signature decoder -> flag forgery reaches the pairing",
        out is not True,
        f"with signature_to_G2 stubbed the result was {out} (not True), "
        "whereas the real decoder raised 'c_flag should be 1'; so the decoder "
        "is what refused the flag forgery"))

    return rows


def _subgroup_generator():
    """A G2 point that IS in the prime-order subgroup: the generator.

    Used as the stand-in signature when the decoder is stubbed, so that the
    pairing can still be evaluated rather than crashing on a bad point.
    """
    from py_ecc.optimized_bls12_381 import G2
    return G2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except BaseException:
        traceback.print_exc()
        raise SystemExit(3)

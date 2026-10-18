#!/usr/bin/env python3
"""BLS signature verification for the drand DEFAULT chain (pedersen-bls-chained).

Cryptographic binding only.  No Stage-2 value, instance, coefficient, candidate
or scientific record is read or written, and this module makes no network call:
the beacon response is supplied to it, never fetched by it.  Chain-policy
adoption is NOT decided here; this module only demonstrates that a chosen chain's
scheme is exactly reproducible by a pinned library, and that malformed or
adversarial inputs are refused with a typed error.

SCHEME, TAKEN FROM drand's OWN SOURCE, NOT FROM REVIEWER RECOLLECTION
--------------------------------------------------------------------
Source of truth: research/g9/GATE_9_DRAND_SCHEMES_SOURCE.go.txt (verbatim
fetch of drand/drand master crypto/schemes.go).  The default chain is the
scheme named by `DefaultSchemeID`, quoted at line 89:

    89: const DefaultSchemeID = "pedersen-bls-chained"

and instantiated by `NewPedersenBLSChained`, whose doc comment at line 95
states verbatim:

    95: // This schemes has the group public key on G1, so 48 bytes, and the
    //     beacon signatures on G2, so 96 bytes.

Group assignment, lines 97-105:

    97:   var Pairing = bls.NewBLS12381SuiteWithDST(
    98:       []byte("BLS_SIG_BLS12381G1_XMD:SHA-256_SSWU_RO_NUL_"), // default RFC9380 DST for G1
    99:       []byte("BLS_SIG_BLS12381G2_XMD:SHA-256_SSWU_RO_NUL_"), // default RFC9380 DST for G2
   100:   )
   101:
   102:   var KeyGroup = Pairing.G1()
   103:   var SigGroup = Pairing.G2()
   104:   var ThresholdScheme = tbls.NewThresholdSchemeOnG2(Pairing)
   105:   var AuthScheme = signBls.NewSchemeOnG2(Pairing)

So:  KeyGroup = G1 -> 48-byte compressed public key.
      SigGroup = G2 -> 96-byte compressed signature.
      The signature group's hash-to-curve DST is the G2 string, line 99:
      `BLS_SIG_BLS12381G2_XMD:SHA-256_SSWU_RO_NUL_`.

The threshold scheme is `tbls.NewThresholdSchemeOnG2` (line 104): verifies on
G2, and `VerifyBeacon` at lines 69-71 runs
`s.ThresholdScheme.VerifyRecovered(pubkey, s.DigestBeacon(b), b.GetSignature())`.
That is exactly a pairing equation e(sig, G1) == e(H(m), pk), which is the
`G2Basic` ciphersuite of py_ecc: pubkey on G1, signature on G2.

MESSAGE CONSTRUCTION, lines 108-117, quoted verbatim:

   108:   // Chained means we're hashing the previous signature and the round number to make it an actual "chain"
   109:   var DigestFunc = func(b hashableBeacon) []byte {
   110:       h := sha256.New()
   111:
   112:       if len(b.GetPreviousSignature()) > 0 {
   113:           _, _ = h.Write(b.GetPreviousSignature())
   114:       }
   115:       _ = binary.Write(h, binary.BigEndian, b.GetRound())
   116:       return h.Sum(nil)
   117:   }

`binary.Write(..., binary.BigEndian, b.GetRound())` where GetRound() returns
`uint64` (line 34) writes the round as 8 big-endian bytes, with no width
prefix.  Therefore for a chained round whose previous signature is present:

    message = sha256( previous_signature || uint64_big_endian(round) )

Line 112 is also the authority for round 1: the previous signature is written
only `if len(...) > 0`.  For the DEFAULT chain round 1 is nonetheless non-empty
-- it is the chain genesis seed, 32 bytes, and (measured, see
GATE_9_DRAND_BLS_ROUNDS_DEFAULT.json) equal to the chain information's
`groupHash` 176f9349...cb390a.  It is a bare SHA-256, NOT a G2 point, so it is
96 bytes for every other round and exactly 32 bytes for round 1.  The verifier
below enforces that distinction as a rule of its own rather than assuming it.

RANDOMNESS, lines 337-344, quoted verbatim:

   341: func RandomnessFromSignature(sig []byte) []byte {
   342:     out := sha256.Sum256(sig)
   343:     return out[:]
   344: }

so `randomness == sha256(signature)` -- checked here whenever randomness is
supplied.

CIPHERSUITE MAPPING -- the DST is compared byte-for-byte at import time, not
asserted in a comment.  `expected_dst()` returns the literal from line 99 and
`assert_ciphersuite()` compares it to `G2Basic.DST` with `==` on `bytes`; a
mismatch raises `BLSVerifyError`.  A wrong DST produces a different hash-to-curve
output and therefore a different pairing, so this check is what makes the scheme
claim falsifiable instead of decorative.

WHAT py_ecc ENFORCES ON THIS PATH, AND WHAT THIS MODULE ENFORCES
----------------------------------------------------------------
Read from py_ecc 8.0.0 source, not assumed:

  * `_CoreVerify` calls `KeyValidate(PK)` (on-curve + subgroup for the G1 key)
    and `signature_to_G2(signature)`, which calls `decompress_G2`.  `decompress_G2`
    itself raises ValueError on: a cleared compression flag ("c_flag should be 1"),
    a b_flag/a_flag disagreement, an infinity flag set on a non-infinity body,
    `x1 >= q` ("x1 value should be less than field modulus"), `z2 >= q`, and
    "The given point is not on the twisted curve over FQ**2" when the modular
    square root is absent.
  * `_CoreVerify` then calls `subgroup_check(signature_point)`, which returns
    False for a point that is on the curve but outside the prime-order subgroup;
    `_CoreVerify` returns False in that case (it does not raise).

Those are genuine checks, but they surface as `False` or as a caught exception,
not as a typed error, and they are not obviously ours.  So every failure path in
THIS module is re-expressed as `BLSVerifyError`, and the fixtures separately
prove (a) that each check defined here is load-bearing and (b) that py_ecc's own
subgroup/on-curve/flag checks really do fire on this path.

THE IMPORT BOUNDARY
-------------------
`py_ecc` is imported lazily, inside a helper, so that importing this module on an
interpreter without py_ecc succeeds and only *using* it raises the typed
`BLSVerifyError` -- never a bare `ImportError` from this module's surface.
Every escape path out of the public functions is one of the `BLSVerifyError`
subclasses below; no untyped exception can leave them.

READ-ONLY INPUT CONTRACT
------------------------
`verify_default_round` takes plain data.  It does not fetch, does not write, and
does not consult a clock.  The public key is taken ONLY from an info dict whose
`hash`, `schemeID` and `public_key` are byte-equal to the committed
GATE_9_DRAND_CHAIN_INFO_DEFAULT_INFO.json values; any other key is refused.  A
caller cannot pass a key of its choosing.
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import hashlib
import re
import struct
from typing import Any, Dict, Optional

SCHEMA = "decisions_os/stage2_beacon_bls_verify/v1"

# --- committed identity of the drand DEFAULT chain -------------------------
# Source: research/g9/GATE_9_DRAND_CHAIN_INFO_DEFAULT_INFO.json (verbatim
# response of GET /8990e7a9...b2ce/info).  A verifier that would accept any
# other key is not verifying this chain, so these three fields are pinned.
DEFAULT_CHAIN_HASH = (
    "8990e7a9aaed2ffed73dbd7092123d6f289930540d7651336225dc172e51b2ce"
)
DEFAULT_SCHEME_ID = "pedersen-bls-chained"
DEFAULT_PUBLIC_KEY = (
    "868f005eb8e6e4ca0a47c8a77ceaa5309a47978a7c71bc5cce96366b5d7a569"
    "937c529eeda66c7293784a9402801af31"
)

# --- scheme parameters, from schemes.go (line numbers quoted in the docstring)
KEY_GROUP = "G1"
SIG_GROUP = "G2"
PUBLIC_KEY_BYTES = 48          # schemes.go line 95, KeyGroup = Pairing.G1()
SIGNATURE_BYTES = 96           # schemes.go line 95, SigGroup = Pairing.G2()
GENESIS_SEED_BYTES = 32        # round 1's previous_signature, see GATE_9_DRAND_BLS_ROUNDS_DEFAULT.json
RANDOMNESS_BYTES = 32          # schemes.go lines 341-343, sha256(signature)
PY_ECC_CIPHERSUITE = "py_ecc.bls.G2Basic"


class BLSVerifyError(Exception):
    """Base typed refusal.  Nothing else escapes the public functions."""


class BLSInputTypeError(BLSVerifyError):
    """An argument had the wrong Python type."""


class BLSHexFormatError(BLSVerifyError):
    """A hex string was not lowercase, unprefixed, whitespace-free hex."""


class BLSLengthError(BLSVerifyError):
    """A byte field had the wrong length."""


class BLSChainIdentityError(BLSVerifyError):
    """The info dict was not the committed drand DEFAULT chain."""


class BLSRandomnessMismatchError(BLSVerifyError):
    """randomness != sha256(signature)."""


class BLSEncodingError(BLSVerifyError):
    """py_ecc refused the compressed encoding (flags, modulus, on-curve)."""


class BLSSubgroupError(BLSVerifyError):
    """A point was on the curve but outside the prime-order subgroup."""


class BLSSignatureInvalidError(BLSVerifyError):
    """The pairing equation did not hold: a well-formed forgery or a wrong message."""


class BLSRoundRangeError(BLSVerifyError):
    """The round was not a positive uint64."""


class BLSDependencyError(BLSVerifyError):
    """py_ecc is not importable in this interpreter."""


# --- scheme literals, quoted from GATE_9_DRAND_SCHEMES_SOURCE.go.txt --------

# schemes.go line 99: the G2 (signature-group) DST.
GO_SRC_G2_DST = b"BLS_SIG_BLS12381G2_XMD:SHA-256_SSWU_RO_NUL_"

_HEX_RE = re.compile(r"\A[0-9a-f]*\Z")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise BLSVerifyError(message)


def _is_exact_int(value: Any) -> bool:
    """True for a real `int`, and False for bool and for int subclasses.

    `bool` is a subclass of `int` in Python, so `isinstance(True, int)` is
    True; a `round=True` must not be silently treated as round 1.  Named int
    subclasses (`class R(int)`) are refused too, so that a caller cannot smuggle
    a value whose behaviour differs from a plain int under `-O`.
    """
    return type(value) is int


def _require_exact_str(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise BLSInputTypeError(
            f"{label} must be str, got {type(value).__name__}"
        )
    return value


def _decode_hex(
    value: Any, expected_bytes: int, label: str, allow_empty: bool = False
) -> bytes:
    """Decode a strict lowercase, unprefixed, whitespace-free hex string."""
    text = _require_exact_str(value, label)
    if not allow_empty and len(text) == 0:
        raise BLSHexFormatError(f"{label} is empty")
    if not _HEX_RE.match(text):
        # Distinguish the common near-misses so the refusal is actionable.
        if text != text.strip():
            raise BLSHexFormatError(f"{label} has leading or trailing whitespace")
        if text[:2].lower() == "0x":
            raise BLSHexFormatError(f"{label} carries a 0x prefix")
        if text.lower() != text and text.isalnum():
            raise BLSHexFormatError(f"{label} is not lowercase hex")
        raise BLSHexFormatError(f"{label} is not lowercase hex")
    if len(text) % 2 != 0:
        raise BLSHexFormatError(f"{label} has an odd number of hex digits")
    raw = bytes.fromhex(text)
    if not allow_empty and len(raw) != expected_bytes:
        raise BLSLengthError(
            f"{label} must be {expected_bytes} bytes ({expected_bytes * 2} hex "
            f"digits), got {len(raw)} bytes ({len(text)} hex digits)"
        )
    return raw


def _truncate_to_bytes(hexstr, nbytes):
    """Hex for the first nbytes bytes, adding a nibble if the cut is odd."""
    text = hexstr[: nbytes * 2]
    if len(text) % 2:
        text += "0"
    return text


def build_message(previous_signature: bytes, round_number: int) -> bytes:
    """sha256(previous_signature || uint64_big_endian(round)).

    Reproduces schemes.go lines 110-116 exactly: the previous signature is
    written first, then the round as 8 big-endian bytes, then the sha256 is
    taken once over the concatenation.
    """
    return hashlib.sha256(
        previous_signature + struct.pack(">Q", round_number)
    ).digest()


def expected_dst() -> bytes:
    """The signature-group DST this module requires, from schemes.go line 99."""
    return GO_SRC_G2_DST


def _import_ciphersuite() -> Any:
    """Import py_ecc lazily and convert any failure into BLSVerifyError.

    Called only at verification time, so that `import stage2_beacon_bls_verify`
    succeeds on an interpreter without py_ecc.  An ImportError must not escape:
    the caller of this module should only ever have to catch BLSVerifyError.
    """
    try:
        from py_ecc.bls import G2Basic
    except BaseException as exc:  # includes ImportError, and broken installs
        raise BLSDependencyError(
            "py_ecc is not usable in this interpreter "
            f"({type(exc).__name__}: {exc}). Run the fixtures with the pinned "
            "environment at ../venv/bin/python."
        ) from None
    return G2Basic


def assert_ciphersuite() -> bytes:
    """Prove the ciphersuite's DST is byte-identical to drand's, at runtime.

    schemes.go line 99 gives the signature-group DST.  The ciphersuite used here
    is the IETF *basic* G2 suite precisely because its DST is that string.  This
    compares the two as `bytes` and refuses on any difference.
    """
    go_dst = expected_dst()
    suite = _import_ciphersuite()
    lib_dst = getattr(suite, "DST", None)
    if not isinstance(lib_dst, bytes):
        raise BLSDependencyError(
            f"{PY_ECC_CIPHERSUITE} exposes no bytes DST attribute (got {lib_dst!r})"
        )
    if lib_dst != go_dst:
        raise BLSDependencyError(
            "py_ecc ciphersuite DST does not match drand schemes.go line 99: "
            f"library {lib_dst!r} != drand {go_dst!r}"
        )
    return go_dst


def committed_info() -> Dict[str, Any]:
    """The committed DEFAULT chain info, as a plain dict.

    The values are transcribed from
    research/g9/GATE_9_DRAND_CHAIN_INFO_DEFAULT_INFO.json.  They are embedded
    rather than read at call time so that a tampered or absent evidence file
    cannot change what this module accepts; the fixture harness separately
    checks this dict against the committed file, field by field.
    """
    return {
        "public_key": DEFAULT_PUBLIC_KEY,
        "period": 30,
        "genesis_time": 1595431050,
        "hash": DEFAULT_CHAIN_HASH,
        "groupHash": (
            "176f93498eac9ca337150b46d21dd58673ea4e3581185f869672e59fa4cb390a"
        ),
        "schemeID": DEFAULT_SCHEME_ID,
        "metadata": {"beaconID": "default"},
    }


def genesis_seed() -> str:
    """Round 1's previous_signature: the 32-byte chain genesis seed.

    Equal to the chain information's groupHash; see
    GATE_9_DRAND_BLS_ROUNDS_DEFAULT.json for the measurement.
    """
    return committed_info()["groupHash"]


def check_info(info: Any) -> bytes:
    """Validate the chain info dict and return the pinned public key bytes.

    The key is only ever taken from here.  `hash`, `schemeID` and `public_key`
    must equal the committed values byte for byte; that is what stops a caller
    from verifying against a key it chose itself (the quicknet key, say).
    """
    if not isinstance(info, dict):
        raise BLSInputTypeError(f"info must be dict, got {type(info).__name__}")
    for field in ("hash", "schemeID", "public_key"):
        if field not in info:
            raise BLSChainIdentityError(f"info is missing required field {field!r}")
        value = info[field]
        if not isinstance(value, str):
            raise BLSInputTypeError(
                f"info[{field!r}] must be str, got {type(value).__name__}"
            )
    if info["hash"] != DEFAULT_CHAIN_HASH:
        raise BLSChainIdentityError(
            f"info['hash'] is not the drand DEFAULT chain: {info['hash']!r}"
        )
    if info["schemeID"] != DEFAULT_SCHEME_ID:
        raise BLSChainIdentityError(
            f"info['schemeID'] is not {DEFAULT_SCHEME_ID!r}: {info['schemeID']!r}"
        )
    if info["public_key"] != DEFAULT_PUBLIC_KEY:
        raise BLSChainIdentityError(
            "info['public_key'] is not the committed DEFAULT chain key "
            f"({info['public_key']!r})"
        )
    key_bytes = _decode_hex(
        info["public_key"], PUBLIC_KEY_BYTES, "info['public_key']"
    )
    _require(len(key_bytes) == PUBLIC_KEY_BYTES, "internal: key length")
    return key_bytes


def check_previous_signature(
    previous_signature_hex: Any, round_number: int
) -> bytes:
    """Decode the chained previous signature, with round 1 handled separately.

    Every round except round 1 chains a 96-byte G2 signature.  Round 1's
    previous_signature is the 32-byte genesis seed (schemes.go line 112 guards
    the write with `len(...) > 0`; the seed is a bare SHA-256 equal to the
    chain info groupHash).  Requiring 96 bytes for round 1 would be wrong, and
    accepting 96 bytes there would be worse, so the two cases are distinct rules.
    """
    if round_number == 1:
        raw = _decode_hex(
            previous_signature_hex,
            GENESIS_SEED_BYTES,
            "previous_signature_hex (round 1 genesis seed)",
        )
        _require(
            raw.hex() == genesis_seed(),
            "round 1 previous_signature must be the committed chain genesis "
            f"seed {genesis_seed()}, got {raw.hex()}",
        )
        return raw
    raw = _decode_hex(
        previous_signature_hex, SIGNATURE_BYTES, "previous_signature_hex"
    )
    return raw


def check_randomness(signature_bytes: bytes, randomness_hex: Optional[Any]) -> None:
    """Enforce randomness == sha256(signature) when randomness is supplied.

    schemes.go lines 341-343.  `None` means "not supplied", which is allowed;
    anything else must be a 32-byte lowercase hex string equal to the digest.
    The signature is taken as already-decoded bytes so that a signature is
    parsed once and checked once.
    """
    if randomness_hex is None:
        return
    expected = hashlib.sha256(signature_bytes).hexdigest()
    got = _decode_hex(randomness_hex, RANDOMNESS_BYTES, "randomness_hex").hex()
    if got != expected:
        raise BLSRandomnessMismatchError(
            "randomness is not sha256(signature): "
            f"expected {expected}, got {got}"
        )


def check_round(round_number: Any) -> int:
    """A round must be a plain int in [1, 2**64-1].

    `type(r) is int` rejects bool and int subclasses.  The upper bound is not
    cosmetic: `struct.pack('>Q', r)` raises struct.error for r >= 2**64, and
    that is a struct.error, not a BLSVerifyError, so it must be refused here.
    """
    if not _is_exact_int(round_number):
        raise BLSInputTypeError(
            f"round must be a plain int, got {type(round_number).__name__}"
        )
    if round_number < 1:
        raise BLSRoundRangeError(f"round must be >= 1, got {round_number}")
    if round_number >= 1 << 64:
        raise BLSRoundRangeError(f"round must be < 2**64, got {round_number}")
    return round_number


def _pairing_verify(key_bytes: bytes, message: bytes, sig_bytes: bytes) -> None:
    """Run the pairing check, re-expressing every failure as a typed error.

    The suite is entered only after all local input validation has passed, so
    any failure from here is either a decoding rejection by py_ecc or a failed
    pairing.  Both are made typed, and the subgroup case is separated from the
    plain "wrong signature" case so an auditor can tell a small-subgroup point
    from an honest forgery.
    """
    suite = _import_ciphersuite()

    # Re-express py_ecc's decode-time refusals as typed errors, by probing the
    # decode the suite will perform, and naming which structural rule failed.
    try:
        from py_ecc.bls.g2_primitives import (
            decompress_G2,
            is_inf,
            pubkey_to_G1,
            subgroup_check,
        )
        from py_ecc.bls.hash import os2ip
    except BaseException as exc:
        raise BLSDependencyError(
            f"py_ecc internals unavailable: {type(exc).__name__}: {exc}"
        ) from None

    # The public key decode happens inside KeyValidate; do it here so its
    # structural refusals are typed too.  In py_ecc 8.0.0 both the G1 and the
    # G2 decoders live in py_ecc.bls.g2_primitives -- there is no
    # py_ecc.bls.g1_primitives module.
    try:
        pk_point = pubkey_to_G1(key_bytes)
    except BaseException as exc:
        raise BLSEncodingError(
            f"public key rejected by the compressed G1 decoder: {exc}"
        ) from None

    if not subgroup_check(pk_point):
        raise BLSSubgroupError(
            "public key is on the curve but outside the prime-order subgroup"
        )
    if is_inf(pk_point):
        raise BLSEncodingError("public key is the point at infinity")

    try:
        sig_point = decompress_G2((os2ip(sig_bytes[:48]), os2ip(sig_bytes[48:])))
    except BaseException as exc:
        raise BLSEncodingError(
            f"signature rejected by the compressed G2 decoder: "
            f"{type(exc).__name__}: {exc}"
        ) from None

    if is_inf(sig_point):
        raise BLSEncodingError("signature is the point at infinity")

    if not subgroup_check(sig_point):
        raise BLSSubgroupError(
            "signature is on the curve but outside the prime-order subgroup"
        )

    try:
        ok = suite.Verify(key_bytes, message, sig_bytes)
    except BaseException as exc:
        # Verify() is documented to return False, not raise.  If it raises, the
        # library contract changed; still typed.
        raise BLSSignatureInvalidError(
            f"ciphersuite raised instead of returning: {type(exc).__name__}: {exc}"
        ) from None

    if ok is not True:
        raise BLSSignatureInvalidError(
            "pairing check failed: e(sig, G1) != e(H(message), pk)"
        )


def verify_default_round(
    info: Dict[str, Any],
    round: int,
    signature_hex: str,
    previous_signature_hex: str,
    randomness_hex: Optional[str] = None,
) -> bool:
    """Verify one drand DEFAULT chain beacon round.

    Returns True on a valid signature.  Every other outcome raises a
    BLSVerifyError subclass; this function never returns False and never lets an
    untyped exception escape.

    The message is rebuilt as sha256(previous_signature || uint64_be(round))
    per schemes.go lines 110-116, and the signature is checked with
    py_ecc.bls.G2Basic whose DST is asserted byte-identical to schemes.go line 99
    before the pairing runs.
    """
    assert_ciphersuite()

    round_number = check_round(round)
    key_bytes = check_info(info)
    signature_bytes = _decode_hex(
        signature_hex, SIGNATURE_BYTES, "signature_hex"
    )
    previous_bytes = check_previous_signature(
        previous_signature_hex, round_number
    )
    check_randomness(signature_bytes, randomness_hex)

    message = build_message(previous_bytes, round_number)
    _pairing_verify(key_bytes, message, signature_bytes)
    return True


def verify_default_response(
    info: Dict[str, Any], response: Any
) -> bool:
    """Verify a whole /public/<round> response dict.

    Convenience wrapper: the field names are the drand API's own, and the
    previous_signature is the genesis seed when the response is round 1.
    """
    if not isinstance(response, dict):
        raise BLSInputTypeError(
            f"response must be dict, got {type(response).__name__}"
        )
    for field in ("round", "signature", "previous_signature"):
        if field not in response:
            raise BLSInputTypeError(f"response is missing field {field!r}")
    return verify_default_round(
        info=info,
        round=response["round"],
        signature_hex=response["signature"],
        previous_signature_hex=response["previous_signature"],
        randomness_hex=response.get("randomness"),
    )


__all__ = [
    "BLSVerifyError",
    "BLSInputTypeError",
    "BLSHexFormatError",
    "BLSLengthError",
    "BLSChainIdentityError",
    "BLSRandomnessMismatchError",
    "BLSEncodingError",
    "BLSSubgroupError",
    "BLSSignatureInvalidError",
    "BLSRoundRangeError",
    "BLSDependencyError",
    "verify_default_round",
    "verify_default_response",
    "build_message",
    "check_info",
    "check_randomness",
    "check_previous_signature",
    "check_round",
    "assert_ciphersuite",
    "expected_dst",
    "committed_info",
    "genesis_seed",
    "KEY_GROUP",
    "SIG_GROUP",
    "PUBLIC_KEY_BYTES",
    "SIGNATURE_BYTES",
    "GENESIS_SEED_BYTES",
    "DEFAULT_CHAIN_HASH",
    "DEFAULT_SCHEME_ID",
    "DEFAULT_PUBLIC_KEY",
    "GO_SRC_G2_DST",
    "SCHEMA",
]

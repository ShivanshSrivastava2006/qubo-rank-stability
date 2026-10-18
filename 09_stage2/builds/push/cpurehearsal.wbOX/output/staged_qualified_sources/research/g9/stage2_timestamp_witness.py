#!/usr/bin/env python3
"""RFC 3161 timestamp witness for the Stage-2 verification commitment.

Mechanism only.  No Stage-2 value, instance, coefficient, candidate or
scientific record is read or written.

WHAT THIS IS FOR.  The beacon binding is defeated by a backdated pin: claim an
earlier pin time, select an already-published drand round, and the nonce is
known before the results are designed.  Closing that needs proof that the
campaign root existed BEFORE the chosen round was published, from a party
neither the producer nor the owner controls.

An independent human publishing "I saw root X at time T" is one way to get
that, and it is the weakest one: it is an assertion, with no cryptographic
binding, resting on that person's own platform's clock anyway.  An RFC 3161
Timestamp Authority returns a **signed token** binding a hash to a time, which
any third party can verify years later with no coordination.  Two roles were
bundled in the original requirement -- independent WITNESS and independent
REVIEWER.  This module replaces the witness role only.  **It does not replace
independent review, which is a judgement function and still needs a person.**

WHERE THIS RUNS.  On the owner's own machine, as part of verification -- never
inside a Kaggle session.  It therefore uses `subprocess` to drive `openssl`,
which the in-session probes are forbidden from doing.  That is a deliberate
difference in trust context, not an oversight.

TRUST.  A TSA can in principle backdate for you, so `require_round_after_witnesses`
demands tokens from at least two INDEPENDENT authorities by default.  Collusion
between unrelated commercial TSAs with no stake in this project is a far weaker
assumption than trusting the party being audited.  For a trust-free anchor
instead of a trust-reduced one, a proof-of-work timestamp such as
OpenTimestamps removes the trusted party entirely at the cost of hours of
latency; this module does not implement it.
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import hashlib
import json
import re
import secrets
import subprocess
from datetime import datetime, timezone

import stage2_beacon_nonce as beacon

SCHEMA = "decisions_os/stage2_timestamp_witness/v3"
SUBJECT_DOMAIN = b"decisions_os/stage2_timestamp_witness/subject/v1"

SHA256_OID_DER = bytes.fromhex("06096086480165030402 01".replace(" ", ""))
NONCE_BITS = 64
MINIMUM_AUTHORITIES = 2

# X.509 id-ce-extKeyUsage (2.5.29.37) and the only usage RFC 3161 s2.3 permits.
EXT_KEY_USAGE_OID = "2.5.29.37"
TIME_STAMPING_EKU_OID = "1.3.6.1.5.5.7.3.8"

PKI_STATUS_GRANTED = 0
PKI_STATUS_GRANTED_WITH_MODS = 1
ACCEPTABLE_STATUSES = (PKI_STATUS_GRANTED, PKI_STATUS_GRANTED_WITH_MODS)


class WitnessError(ValueError):
    """A typed refusal.  Every failure path in this module raises this."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise WitnessError(message)


def _hex32(value: object, label: str) -> bytes:
    _require(type(value) is str and len(value) == 64, f"{label} must be 64 hex chars")
    _require(all(c in "0123456789abcdef" for c in value), f"{label} must be lowercase hex")
    return bytes.fromhex(value)


# ---------------------------------------------------------------------------
# What gets timestamped
# ---------------------------------------------------------------------------

def witness_subject_digest(campaign_root_hex: str, policy_digest_hex: str) -> str:
    """The single digest a TSA is asked to timestamp.

    Binds the campaign root AND the beacon policy together: timestamping the
    root alone would leave the policy free to change afterwards, and the policy
    is what turns a pin time into a round.  Both are length-free fixed-width
    inputs under a domain separator, so no pair of distinct inputs collides.
    """
    root = _hex32(campaign_root_hex, "campaign_root")
    policy = _hex32(policy_digest_hex, "policy_digest")
    return hashlib.sha256(SUBJECT_DOMAIN + root + policy).hexdigest()


def beacon_policy_digest(policy: dict) -> str:
    """The digest that binds a beacon policy into the timestamped subject.

    Public because the owner needs the SAME value when requesting timestamps,
    before any token exists.  Canonical JSON -- sorted keys, no spaces, ASCII,
    NaN refused -- so the binding depends on neither side's dict ordering nor
    on a non-JSON float spelling the same policy two ways.
    """
    _require(type(policy) is dict and policy, "policy must be a non-empty dict")
    payload = json.dumps(policy, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


# ---------------------------------------------------------------------------
# DER, enough of it to build a TimeStampReq without a dependency
# ---------------------------------------------------------------------------

def _der_len(n: int) -> bytes:
    if n < 0x80:
        return bytes([n])
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(raw)]) + raw


def _der(tag: int, body: bytes) -> bytes:
    return bytes([tag]) + _der_len(len(body)) + body


def _der_int(value: int) -> bytes:
    _require(value >= 0, "only non-negative integers are encoded here")
    raw = value.to_bytes(max(1, (value.bit_length() + 8) // 8), "big")
    return _der(0x02, raw)


def build_timestamp_request(subject_digest_hex: str, nonce: int | None = None,
                            cert_req: bool = True) -> tuple:
    """Build a DER TimeStampReq for the subject digest.

    Returns `(der_bytes, nonce)`.  The nonce is mandatory in practice even
    though RFC 3161 makes it optional: without it a TSA, or anyone replaying
    its traffic, could return a previously issued token for the same digest,
    and a stale token proves the wrong instant.  `cert_req` asks the TSA to
    include its certificate so the token can be verified later without
    separately obtaining it.
    """
    digest = _hex32(subject_digest_hex, "subject_digest")
    if nonce is None:
        nonce = secrets.randbits(NONCE_BITS)
    _require(type(nonce) is int and nonce > 0, "nonce must be a positive int")
    _require(type(cert_req) is bool, "cert_req must be a bool")

    algorithm = _der(0x30, SHA256_OID_DER + _der(0x05, b""))     # sha256, NULL params
    imprint = _der(0x30, algorithm + _der(0x04, digest))
    body = _der_int(1) + imprint + _der_int(nonce)
    if cert_req:
        body += _der(0x01, b"\xff")
    return _der(0x30, body), nonce


# ---------------------------------------------------------------------------
# Response handling
# ---------------------------------------------------------------------------

def _walk(der: bytes, offset: int) -> tuple:
    """Return (tag, body_start, body_end) for the element at `offset`."""
    _require(offset + 2 <= len(der), "truncated DER element")
    tag = der[offset]
    length_byte = der[offset + 1]
    if length_byte < 0x80:
        return tag, offset + 2, offset + 2 + length_byte
    count = length_byte & 0x7F
    _require(count and offset + 2 + count <= len(der), "malformed DER length")
    length = int.from_bytes(der[offset + 2:offset + 2 + count], "big")
    start = offset + 2 + count
    _require(start + length <= len(der), "DER length overruns the buffer")
    return tag, start, start + length


def parse_response_status(response_der: bytes) -> int:
    """Extract the PKIStatus without trusting any external parser.

    A rejected response still parses as a well-formed TimeStampResp, so a
    caller that only checked the signature would treat a refusal as evidence.
    """
    _require(type(response_der) is bytes and response_der, "response must be non-empty bytes")
    tag, start, end = _walk(response_der, 0)
    _require(tag == 0x30, "TimeStampResp must be a SEQUENCE")
    tag, s2, e2 = _walk(response_der, start)              # PKIStatusInfo
    _require(tag == 0x30, "PKIStatusInfo must be a SEQUENCE")
    tag, s3, e3 = _walk(response_der, s2)                 # status INTEGER
    _require(tag == 0x02, "PKIStatus must be an INTEGER")
    return int.from_bytes(response_der[s3:e3], "big")


# ---------------------------------------------------------------------------
# The signed TSTInfo, read by POSITION from its DER encoding
# ---------------------------------------------------------------------------
#
# Revision history of this section, because it is the part that went wrong:
#
#   r1  Read the attested time from `openssl ts -reply -text` of the WHOLE
#       response.  Another reviewer showed the unsigned PKIStatusInfo can carry
#       an injected "Time stamp:" line while the CMS signature still verifies,
#       and a genuine token was read as five years older.  Repaired by parsing
#       only the extracted signed token.
#   r2  Added signer identity, subject/nonce binding and accuracy -- and read
#       the new fields with regexes over `-token_in -text`.  That was the SAME
#       pattern on signed data.  Two independent reviews showed a malicious TSA
#       can place newline-bearing text in signed fields that openssl prints
#       verbatim, forging an "Accuracy:" line the first-match regex takes, and
#       that when no number matched the accuracy silently became ZERO.
#   r3  This revision.  Nothing load-bearing is read from text.  The TSTInfo is
#       walked field by field in its fixed RFC 3161 order.  openssl's text is
#       kept only as a cross-check, where disagreement REFUSES; injected text
#       can therefore cause a false refusal but never a false acceptance.

SIGNED_DATA_OID_DER = bytes.fromhex("06092a864886f70d010702")
TSTINFO_OID_DER = bytes.fromhex("060b2a864886f70d0109100104")
ACCURACY_SUBUNIT_RANGE = range(1, 1000)       # RFC 3161: millis, micros in 1..999


def _children(der: bytes, start: int, end: int) -> list:
    """Direct children of a constructed element as (tag, body_start, body_end, tlv_start)."""
    out = []
    offset = start
    while offset < end:
        tag, s, e = _walk(der, offset)
        _require(e <= end, "a child element overruns its parent")
        out.append((tag, s, e, offset))
        offset = e
    _require(offset == end, "trailing bytes inside a constructed element")
    return out


def _uint(der: bytes, s: int, e: int, label: str) -> int:
    body = der[s:e]
    _require(len(body) >= 1, f"{label} is an empty INTEGER")
    _require(body[0] < 0x80, f"{label} is negative")
    _require(not (len(body) > 1 and body[0] == 0 and body[1] < 0x80),
             f"{label} is not minimally encoded")
    return int.from_bytes(body, "big")


def _decode_oid(body: bytes, label: str) -> str:
    """Decode the CONTENT of an OBJECT IDENTIFIER to dotted form.

    X.690 8.19: the first subidentifier is `40*arc1 + arc2`, so the first
    subidentifier is split back into two arcs with arc1 in {0,1,2} and arc2
    absorbing any value >= 80 when arc1 is 2.  A subidentifier whose final
    octet still has the 0x80 continuation bit set is truncated, and a leading
    0x80 octet is a non-minimal (padded) encoding; both are refused rather
    than decoded, so an OID can never be misread into a different value.
    """
    _require(len(body) > 0, f"{label} is an empty OBJECT IDENTIFIER")
    subs: list[int] = []
    value = 0
    fresh = True
    for octet in body:
        if fresh and octet == 0x80:
            raise WitnessError(f"{label} has a non-minimal subidentifier")
        fresh = False
        value = (value << 7) | (octet & 0x7F)
        if not octet & 0x80:
            subs.append(value)
            value = 0
            fresh = True
    _require(fresh, f"{label} has a truncated subidentifier")
    first = subs[0]
    arc1 = first // 40
    _require(arc1 in (0, 1, 2), f"{label} has an illegal first arc")
    arc2 = first - 40 * arc1
    return ".".join(str(a) for a in (arc1, arc2, *subs[1:]))


def _oid_is_dotted(oid: str) -> bool:
    """Whether `oid` is a dotted OID this module's own decoder would produce.

    A pin is compared against a value read out of the DER, so a pin written any
    other way could never match and would silently never bind.  Requiring the
    canonical spelling means a typo is refused at the call site instead.
    """
    if type(oid) is not str or not oid:
        return False
    parts = oid.split(".")
    if len(parts) < 2 or not all(p.isdigit() and (p == "0" or not p.startswith("0"))
                                for p in parts):
        return False
    return parts[0] in ("0", "1", "2")


def _generalized_time_micros(raw: bytes) -> int:
    """GeneralizedTime to epoch MICROseconds, strictly as RFC 3161 requires.

    Any fractional part beyond microseconds is rounded UP, so the instant is
    never reported as earlier than the TSA signed.
    """
    _require(all(0x20 <= b < 0x7F for b in raw), "genTime is not printable ASCII")
    m = re.fullmatch(r"(\d{14})(?:\.(\d+))?Z", raw.decode("ascii"))
    _require(m is not None, "genTime is not a UTC GeneralizedTime")
    try:
        base = datetime.strptime(m.group(1), "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError:
        raise WitnessError("genTime is not a valid calendar instant") from None
    fraction = m.group(2) or ""
    _require(not fraction.endswith("0"), "genTime fraction has trailing zeros (not DER)")
    micros = int((fraction + "000000")[:6]) if fraction else 0
    if len(fraction) > 6 and int(fraction[6:]) > 0:
        micros += 1
    return int(base.timestamp()) * 1_000_000 + micros


def _parse_accuracy(der: bytes, s: int, e: int) -> int:
    """Accuracy ::= SEQUENCE { seconds INTEGER OPT, millis [0] OPT, micros [1] OPT }.

    Returns the bound in microseconds.  An accuracy SEQUENCE with no component
    at all is refused: that is the degenerate case in which r2's text parser
    silently reported zero.
    """
    kids = _children(der, s, e)
    _require(kids, "accuracy is present but empty; it states no bound at all")
    order = {0x02: 0, 0x80: 1, 0x81: 2}
    last = -1
    seconds = millis = micros = 0
    for tag, ks, ke, _ in kids:
        _require(tag in order, f"unexpected tag {tag:#x} inside accuracy")
        _require(order[tag] > last, "accuracy components out of order or repeated")
        last = order[tag]
        value = _uint(der, ks, ke, "accuracy component")
        if tag == 0x02:
            seconds = value
        elif tag == 0x80:
            _require(value in ACCURACY_SUBUNIT_RANGE, "accuracy millis outside 1..999")
            millis = value
        else:
            _require(value in ACCURACY_SUBUNIT_RANGE, "accuracy micros outside 1..999")
            micros = value
    return seconds * 1_000_000 + millis * 1_000 + micros


def _parse_tstinfo_body(tst: bytes) -> dict:
    """TSTInfo, field by field in its fixed order.  Any deviation refuses."""
    tag, s, e = _walk(tst, 0)
    _require(tag == 0x30 and e == len(tst), "TSTInfo is not a single SEQUENCE")
    f = _children(tst, s, e)
    _require(len(f) >= 5, "TSTInfo is missing mandatory fields")

    _require(f[0][0] == 0x02 and _uint(tst, f[0][1], f[0][2], "version") == 1,
             "TSTInfo version is not 1")
    _require(f[1][0] == 0x06, "TSTInfo policy is not an OBJECT IDENTIFIER")
    policy_oid = _decode_oid(tst[f[1][1]:f[1][2]], "TSTInfo policy")

    _require(f[2][0] == 0x30, "messageImprint is not a SEQUENCE")
    mi = _children(tst, f[2][1], f[2][2])
    _require(len(mi) == 2 and mi[0][0] == 0x30 and mi[1][0] == 0x04,
             "messageImprint is malformed")
    alg = _children(tst, mi[0][1], mi[0][2])
    _require(alg and tst[alg[0][3]:alg[0][2]] == SHA256_OID_DER,
             "messageImprint hash algorithm is not SHA-256")
    _require(len(alg) == 1 or (len(alg) == 2 and alg[1][0] == 0x05 and alg[1][1] == alg[1][2]),
             "messageImprint algorithm parameters are not absent or NULL")
    imprint = tst[mi[1][1]:mi[1][2]]
    _require(len(imprint) == 32, "messageImprint is not 32 bytes")

    _require(f[3][0] == 0x02, "serialNumber is not an INTEGER")
    _uint(tst, f[3][1], f[3][2], "serialNumber")
    _require(f[4][0] == 0x18, "genTime is not a GeneralizedTime")
    gen_micros = _generalized_time_micros(tst[f[4][1]:f[4][2]])

    # Optional fields in their fixed order: accuracy, ordering, nonce, tsa, extensions.
    order = {0x30: 0, 0x01: 1, 0x02: 2, 0xA0: 3, 0xA1: 4}
    last = -1
    accuracy_micros = None
    ordering = None
    nonce = None
    for tag, fs, fe, _ in f[5:]:
        _require(tag in order, f"unexpected TSTInfo field tag {tag:#x}")
        _require(order[tag] > last, "TSTInfo optional fields out of order or repeated")
        last = order[tag]
        if tag == 0x30:
            accuracy_micros = _parse_accuracy(tst, fs, fe)
        elif tag == 0x01:
            # The BOOLEAN is DER: 0x00 or 0xFF only.  Its VALUE was accepted by
            # tag and never read in r3, so the record could not show whether the
            # TSA asserted ordering.
            _require(tst[fs:fe] in (b"\x00", b"\xff"),
                     "ordering is not a DER BOOLEAN")
            ordering = tst[fs:fe] == b"\xff"
        elif tag == 0x02:
            nonce = _uint(tst, fs, fe, "nonce")

    _require(nonce is not None,
             "the signed token carries no nonce; without one it could be a replay "
             "of an earlier issuance for the same digest")
    _require(accuracy_micros is not None,
             "the signed token declares no accuracy; without a stated error bound "
             "the ordering cannot be made conservative. A TSA like this needs an "
             "explicit policy decision about the bound to assume")
    return {"imprint": imprint.hex(), "nonce": nonce,
            "accuracy_micros": accuracy_micros, "gen_time_micros": gen_micros,
            "policy_oid": policy_oid, "tsa_ordering_claim": ordering}


def parse_signed_token(signed_token: bytes) -> dict:
    """Extract and parse the TSTInfo carried as eContent of the SignedData.

    Also requires exactly one SignerInfo: RFC 5652 permits several, and with
    more than one the signer that verification checked need not be the signer
    whose identity is recorded.
    """
    _require(type(signed_token) is bytes and signed_token, "signed token must be non-empty bytes")
    tag, s, e = _walk(signed_token, 0)
    _require(tag == 0x30 and e == len(signed_token), "token is not a single ContentInfo")
    ci = _children(signed_token, s, e)
    _require(len(ci) == 2, "ContentInfo is malformed")
    _require(signed_token[ci[0][3]:ci[0][2]] == SIGNED_DATA_OID_DER,
             "token content type is not SignedData")
    _require(ci[1][0] == 0xA0, "SignedData wrapper is malformed")
    sd_outer = _children(signed_token, ci[1][1], ci[1][2])
    _require(len(sd_outer) == 1 and sd_outer[0][0] == 0x30, "SignedData is malformed")
    sd = _children(signed_token, sd_outer[0][1], sd_outer[0][2])
    _require(len(sd) >= 4 and sd[0][0] == 0x02 and sd[1][0] == 0x31 and sd[2][0] == 0x30,
             "SignedData fields are malformed")
    _require(sd[-1][0] == 0x31, "SignedData has no signerInfos SET")
    signers = _children(signed_token, sd[-1][1], sd[-1][2])
    _require(len(signers) == 1,
             f"token carries {len(signers)} SignerInfos; exactly one is required")

    eci = _children(signed_token, sd[2][1], sd[2][2])
    _require(len(eci) == 2, "encapContentInfo is malformed")
    _require(signed_token[eci[0][3]:eci[0][2]] == TSTINFO_OID_DER,
             "eContent type is not id-ct-TSTInfo")
    _require(eci[1][0] == 0xA0, "eContent wrapper is malformed")
    octet = _children(signed_token, eci[1][1], eci[1][2])
    _require(len(octet) == 1 and octet[0][0] == 0x04, "eContent is not an OCTET STRING")
    return _parse_tstinfo_body(signed_token[octet[0][1]:octet[0][2]])


def _cert_eku_extension_der(signer_pem: str, openssl: str) -> bytes:
    """The signer's certificate as DER, with openssl's own PEM/DER decoding."""
    done = subprocess.run([openssl, "x509", "-in", signer_pem, "-outform", "DER"],
                          capture_output=True, timeout=120)
    _require(done.returncode == 0 and done.stdout, "could not read the signer certificate")
    return done.stdout


def _eku_from_cert_der(cert_der: bytes) -> dict:
    """Read the ExtendedKeyUsage extension out of a certificate's DER.

    RFC 3161 s2.3 constrains the SIGNER, not just the token: the EKU must be
    present, critical, and limited to id-kp-timeStamping.  r4 tested that with
    substring and regex checks over `openssl x509 -ext extendedKeyUsage`, i.e.
    over openssl's human RENDERING of bytes the TSA chose -- the r2 pattern
    transplanted into a check that this time was POSITIVE, so injected text
    could make it accept.  This reads the certificate's own bytes instead.

    Returns `{"critical": bool, "usages": [dotted, ...]}`.  Absent extension
    yields an empty list; a missing `critical` is a value error, not a crash.
    """
    _require(type(cert_der) is bytes and cert_der, "certificate must be non-empty bytes")
    tag, s, e = _walk(cert_der, 0)
    _require(tag == 0x30 and e == len(cert_der), "certificate is not a single SEQUENCE")
    top = _children(cert_der, s, e)
    _require(len(top) == 3 and top[0][0] == 0x30 and top[2][0] == 0x03,
             "certificate is malformed")
    tbs = _children(cert_der, top[0][1], top[0][2])
    explicit = [k for k in tbs if k[0] == 0xA3]
    _require(len(explicit) == 1, "certificate carries no extensions [3]")
    wrapper = _children(cert_der, explicit[0][1], explicit[0][2])
    _require(len(wrapper) == 1 and wrapper[0][0] == 0x30,
             "certificate extensions wrapper is malformed")
    found = None
    for ext_tag, ext_s, ext_e, _ in _children(cert_der, wrapper[0][1], wrapper[0][2]):
        _require(ext_tag == 0x30, "certificate extension is not a SEQUENCE")
        parts = _children(cert_der, ext_s, ext_e)
        _require(parts and parts[0][0] == 0x06, "extension has no extnID")
        extn_id = _decode_oid(cert_der[parts[0][1]:parts[0][2]], "extnID")
        if extn_id != EXT_KEY_USAGE_OID:
            # A real certificate carries basicConstraints, keyUsage, SKI, AKI
            # and more.  Only the EKU is constrained, so the rest are walked
            # past rather than refused.
            continue
        _require(found is None, "certificate repeats the extended key usage extension")
        critical = False
        octet = None
        for ptag, ps, pe, _ in parts[1:]:
            if ptag == 0x01:
                _require(octet is None, "extended key usage extension is malformed")
                _require(cert_der[ps:pe] == b"\xff",
                         "extended key usage critical flag is not a DER TRUE")
                critical = True
            elif ptag == 0x04:
                _require(octet is None, "extended key usage extension is malformed")
                octet = cert_der[ps:pe]
            else:
                raise WitnessError("unexpected field inside the extended key usage extension")
        _require(octet is not None, "extended key usage extension has no extnValue")
        found = (critical, octet)
    if found is None:
        return {"critical": False, "usages": []}
    critical, octet = found
    utag, us, ue = _walk(octet, 0)
    _require(utag == 0x30 and ue == len(octet),
             "extKeyUsage is not a single SEQUENCE")
    usages = []
    for ktag, ks, ke, _ in _children(octet, us, ue):
        _require(ktag == 0x06, "extKeyUsage contains a non-OID element")
        usages.append(_decode_oid(octet[ks:ke], "extKeyUsage usage"))
    return {"critical": critical, "usages": usages}


def _require_timestamping_eku_der(cert_der: bytes) -> dict:
    """The DER EKU gate: critical, and LIMITED to id-kp-timeStamping.

    The limitation is the point.  A certificate that is timeStamping *and*
    clientAuth passes any check that merely looks for the string "Time
    Stamping", and RFC 3161 requires the limitation precisely to stop the key
    being usable elsewhere.  So the DER list must be exactly one element.
    """
    parsed = _eku_from_cert_der(cert_der)
    _require(parsed["usages"], "signer certificate has no extended key usage extension")
    _require(parsed["critical"],
             "the extended key usage extension is not marked critical")
    _require(parsed["usages"] == [TIME_STAMPING_EKU_OID],
             f"the extended key usage must be limited to {TIME_STAMPING_EKU_OID}, "
             f"but the certificate asserts {parsed['usages']}")
    return parsed


def _signer_identity(openssl: str, signed_path: str, ca_file: str,
                     untrusted_file: str | None, directory: str) -> dict:
    """The certificate that actually signed the token, with its EKU checked.

    Independence between witnesses must be keyed on the signer's KEY, not on a
    label the caller writes: keyed on the label, one TSA issuing two tokens
    labelled "A" and "B" counted as two authorities.  `-purpose timestampsign`
    replaces r2's `-purpose any`, and the EKU is then checked again from the
    certificate's own DER bytes, so the identity used for the independence
    decision is resolved under the same rules RFC 3161 imposes, not weaker
    ones.
    """
    import os
    signer_pem = os.path.join(directory, "signer.pem")
    command = [openssl, "cms", "-verify", "-inform", "DER", "-in", signed_path,
               "-CAfile", ca_file, "-signer", signer_pem, "-out", os.devnull,
               "-binary", "-purpose", "timestampsign"]
    if untrusted_file:
        command += ["-certfile", untrusted_file]
    done = subprocess.run(command, capture_output=True, timeout=120)
    _require(done.returncode == 0 and os.path.exists(signer_pem),
             "could not resolve a timestamp-signing certificate from the token")
    with open(signer_pem, "rb") as handle:
        pem = handle.read()
    _require(pem.count(b"BEGIN CERTIFICATE") == 1, "expected exactly one signer certificate")

    # The DER gate is the real one.  openssl's text is kept only as a
    # REFUSE-ONLY cross-check: if the rendering does not also advertise a
    # critical Time Stamping usage, the token is refused.  Injected text can
    # therefore cause a false refusal, never a false acceptance.
    _require_timestamping_eku_der(_cert_eku_extension_der(signer_pem, openssl))

    eku = subprocess.run([openssl, "x509", "-in", signer_pem, "-noout", "-ext",
                          "extendedKeyUsage"], capture_output=True, timeout=120)
    eku_text = eku.stdout.decode("utf-8", "replace")
    _require(eku.returncode == 0 and re.search(r"Extended Key Usage:\s*critical", eku_text)
             and "Time Stamping" in eku_text,
             "openssl does not report a critical Time Stamping extended key usage "
             "for the signer certificate")

    pub = subprocess.run([openssl, "x509", "-in", signer_pem, "-noout", "-pubkey"],
                         capture_output=True, timeout=120)
    spki = subprocess.run([openssl, "pkey", "-pubin", "-outform", "DER"],
                          input=pub.stdout, capture_output=True, timeout=120)
    _require(pub.returncode == 0 and spki.returncode == 0 and spki.stdout,
             "could not read the signer's public key")
    names = subprocess.run([openssl, "x509", "-in", signer_pem, "-noout",
                            "-subject", "-issuer", "-nameopt", "RFC2253"],
                           capture_output=True, timeout=120)
    text = names.stdout.decode("utf-8", "replace")
    subject = re.search(r"^subject=(.*)$", text, re.MULTILINE)
    issuer = re.search(r"^issuer=(.*)$", text, re.MULTILINE)
    return {"signer_spki_sha256": hashlib.sha256(spki.stdout).hexdigest(),
            "signer_subject": subject.group(1).strip() if subject else "",
            "signer_issuer": issuer.group(1).strip() if issuer else ""}


def verify_token(request_der: bytes, response_der: bytes, ca_file: str,
                 untrusted_file: str | None = None,
                 openssl: str = "openssl", *,
                 expected_subject_digest: str,
                 expected_nonce: int) -> dict:
    """Verify one token and return the facts read from its SIGNED TSTInfo.

    openssl does signature and chain verification; this module does not
    reimplement CMS.  Every value returned -- imprint, nonce, accuracy, time --
    is read from the DER of the exact bytes openssl verified.
    """
    _require(type(request_der) is bytes and request_der, "request must be non-empty bytes")
    _require(type(response_der) is bytes and response_der, "response must be non-empty bytes")
    _require(type(ca_file) is str and ca_file, "ca_file must be a path")
    # r4 type-checked every raw field except this one, and appended it to the
    # subprocess argv unguarded, so `"untrusted_file": 123` in a witness payload
    # raised a bare TypeError from the standard library instead of a
    # WitnessError.  Falsy semantics are unchanged: "" still means "no file".
    _require(untrusted_file is None or type(untrusted_file) is str,
             "untrusted_file must be a string or None")
    # Bound to what the CALLER intended, not merely to whatever query was handed
    # in: openssl checks token-against-query, and a mismatched but
    # self-consistent query/response pair would otherwise pass.
    expected = _hex32(expected_subject_digest, "expected_subject_digest").hex()
    _require(type(expected_nonce) is int and expected_nonce > 0,
             "expected_nonce must be the positive int returned with the request")

    status = parse_response_status(response_der)
    _require(status in ACCEPTABLE_STATUSES,
             f"TSA did not grant the request: PKIStatus {status}")

    import tempfile, os
    with tempfile.TemporaryDirectory(prefix="g9-tsa-") as directory:
        query = os.path.join(directory, "req.tsq")
        reply = os.path.join(directory, "resp.tsr")
        with open(query, "wb") as handle:
            handle.write(request_der)
        with open(reply, "wb") as handle:
            handle.write(response_der)

        # PKIStatusInfo (including statusString) is outside the signed token.
        # Only the extracted token is ever parsed.
        extracted = subprocess.run([openssl, "ts", "-reply", "-in", reply,
                                    "-token_out"], capture_output=True, timeout=120)
        _require(extracted.returncode == 0 and extracted.stdout,
                 "could not extract the signed timestamp token")
        signed_token = extracted.stdout
        signed_path = os.path.join(directory, "signed.tst")
        with open(signed_path, "wb") as handle:
            handle.write(signed_token)

        # Verify EXACTLY the bytes that are then parsed and signer-resolved, so
        # the three steps cannot be looking at different tokens.
        command = [openssl, "ts", "-verify", "-in", signed_path, "-token_in",
                   "-queryfile", query, "-CAfile", ca_file]
        if untrusted_file:
            command += ["-untrusted", untrusted_file]
        completed = subprocess.run(command, capture_output=True, timeout=120)
        combined = (completed.stdout + completed.stderr).decode("utf-8", "replace")
        _require(completed.returncode == 0 and "Verification: OK" in combined,
                 f"openssl refused the token: {combined.strip()[:300]}")

        facts = parse_signed_token(signed_token)
        identity = _signer_identity(openssl, signed_path, ca_file,
                                    untrusted_file, directory)
        shown = subprocess.run([openssl, "ts", "-reply", "-in", signed_path,
                                "-token_in", "-text"], capture_output=True, timeout=120)
        text = (shown.stdout + shown.stderr).decode("utf-8", "replace")

    _require(facts["imprint"] == expected,
             "the signed token timestamps a different digest than the one intended")
    _require(facts["nonce"] == expected_nonce,
             "the signed token's nonce is not the one sent; it may be a replay")

    # Cross-check only.  The DER value is authoritative; openssl's reading must
    # agree with it or the token is refused.  Injected text can therefore make
    # this REFUSE a genuine token, but can never make it accept a false time.
    epoch = facts["gen_time_micros"] // 1_000_000
    match = re.search(r"^Time stamp:[ \t]*(.+)$", text, re.MULTILINE)
    _require(match is not None, "openssl did not report a time stamp to cross-check")
    stamp = match.group(1).strip()
    shown_epoch = None
    for fmt in ("%b %d %H:%M:%S %Y %Z", "%b %d %H:%M:%S.%f %Y %Z"):
        try:
            shown_epoch = int(datetime.strptime(stamp, fmt)
                              .replace(tzinfo=timezone.utc).timestamp())
            break
        except ValueError:
            continue
    _require(shown_epoch is not None and abs(shown_epoch - epoch) <= 1,
             f"openssl reports {stamp!r} but the signed DER says {epoch}; refusing")

    latest_micros = facts["gen_time_micros"] + facts["accuracy_micros"]
    return {"schema": SCHEMA, "status": status, "timestamp": epoch,
            "timestamp_text": stamp,
            "accuracy_micros": facts["accuracy_micros"],
            "accuracy_seconds": -(-facts["accuracy_micros"] // 1_000_000),
            # The latest instant the true time could be, rounded UP to a whole
            # second.  Ordering is checked against this, never the midpoint.
            "timestamp_latest": -(-latest_micros // 1_000_000),
            "subject_digest": expected,
            "nonce": expected_nonce,
            # Read from the DER, not from openssl's rendering: RFC 3161 s2.4.1
            # makes the policy the identifier of WHAT the TSA attested under,
            # and r4 checked it for tag only and then discarded it.
            "policy_oid": facts["policy_oid"],
            # r4 accepted the ordering BOOLEAN by tag and never read its value,
            # so the record could not show whether the TSA asserted ordering.
            "tsa_ordering_claim": facts["tsa_ordering_claim"],
            "signer_spki_sha256": identity["signer_spki_sha256"],
            "signer_subject": identity["signer_subject"],
            "signer_issuer": identity["signer_issuer"],
            "token_sha256": hashlib.sha256(signed_token).hexdigest(),
            "response_sha256": hashlib.sha256(response_der).hexdigest(),
            "request_sha256": hashlib.sha256(request_der).hexdigest()}


# ---------------------------------------------------------------------------
# The ordering check this all exists for
# ---------------------------------------------------------------------------

def _order_verified(round_publication_time: int, verified: list,
                    minimum_authorities: int, pinned_authorities: dict | None,
                    pinned_policy_oids: set | None = None) -> dict:
    """Pure ordering logic over records that `verify_token` produced.

    Private on purpose.  Revision 2 exposed this logic directly over
    caller-written dicts, so it could be called with fabricated integers and no
    token at all -- zero cryptography -- and pass.  The public entry point below
    produces these records itself.
    """
    _require(type(round_publication_time) is int, "round_publication_time must be an int")
    _require(type(verified) is list and verified, "no verified witnesses")
    _require(type(minimum_authorities) is int and minimum_authorities >= 1,
             "minimum_authorities must be a positive int")
    if pinned_policy_oids is not None:
        _require(type(pinned_policy_oids) in (set, frozenset) and pinned_policy_oids,
                 "pinned_policy_oids must be a non-empty set of dotted OIDs")
        for oid in pinned_policy_oids:
            _require(type(oid) is str and _oid_is_dotted(oid),
                     f"pinned policy OID {oid!r} is not a well-formed dotted OID")
    if pinned_authorities is not None:
        _require(type(pinned_authorities) is dict and pinned_authorities,
                 "pinned_authorities must be a non-empty dict")
        for label, fingerprint in pinned_authorities.items():
            _require(type(label) is str and label, "pinned labels must be non-empty strings")
            _hex32(fingerprint, f"pinned fingerprint for {label!r}")
        _require(len(set(pinned_authorities.values())) == len(pinned_authorities),
                 "two pinned labels share one signing key; they are one authority")

    subjects = set()
    by_key = {}
    policy_oids = {}
    for label, record in verified:
        _require(type(label) is str and label, "witness authority must be named")
        _require(type(record) is dict, "verified record must be a dict")
        for key in ("timestamp_latest", "signer_spki_sha256", "subject_digest",
                    "policy_oid", "tsa_ordering_claim"):
            _require(key in record, f"verified record is missing {key}")
        _require(type(record["timestamp_latest"]) is int, "timestamp_latest must be an int")
        _require(type(record["tsa_ordering_claim"]) in (bool, type(None)),
                 "tsa_ordering_claim must be a bool or None")
        fingerprint = _hex32(record["signer_spki_sha256"], "signer_spki_sha256").hex()
        subjects.add(record["subject_digest"])
        # RFC 3161 s2.4.1: the policy names WHAT the TSA attested under.  A key
        # pinned for one policy must not be accepted asserting time under
        # another, so the pin is on the policy as well as the key.
        if pinned_policy_oids is not None:
            _require(record["policy_oid"] in pinned_policy_oids,
                     f"authority {label!r} asserted time under policy "
                     f"{record['policy_oid']!r}, which is not in the pinned set "
                     f"{sorted(pinned_policy_oids)}")
        policy_oids[label] = record["policy_oid"]
        if pinned_authorities is not None:
            _require(label in pinned_authorities, f"authority {label!r} is not in the pinned set")
            _require(pinned_authorities[label] == fingerprint,
                     f"authority {label!r} is pinned to a different signing key "
                     f"than the one that signed this token")
        _require(fingerprint not in by_key,
                 f"two tokens were signed by the same key ({fingerprint[:16]}...), "
                 f"labelled {by_key.get(fingerprint, ('?',))[0]!r} and {label!r}; "
                 f"that is one authority, not two")
        by_key[fingerprint] = (label, record["timestamp_latest"])

    # Mixing a token for subject X with one for subject Y would let two
    # authorities each witness something different and still count as two.
    _require(len(subjects) == 1, "the witnesses timestamp different subjects")
    _require(len(by_key) >= minimum_authorities,
             f"{len(by_key)} distinct signing key(s) supplied, {minimum_authorities} required")

    latest = max(t for _, t in by_key.values())
    _require(round_publication_time > latest,
             f"the round is published at {round_publication_time}, not strictly "
             f"after the latest witness bound {latest}; backdating is not excluded")
    return {
        "schema": SCHEMA,
        "subject_digest": next(iter(subjects)),
        "authorities": sorted(label for label, _ in by_key.values()),
        "signing_keys": sorted(by_key),
        "authority_count": len(by_key),
        # The threshold ACTUALLY applied.  r4 recorded neither this nor the
        # policy each key asserted under, so a caller that relaxed
        # minimum_authorities to 1 left no trace in the result dict.
        "minimum_authorities_applied": minimum_authorities,
        "policy_oids": {label: policy_oids[label]
                        for label, _ in by_key.values()},
        "latest_witness_timestamp": latest,
        "round_publication_time": round_publication_time,
        "margin_seconds": round_publication_time - latest,
        "pinned": pinned_authorities is not None,
        "pinned_policy_oids": (sorted(pinned_policy_oids)
                               if pinned_policy_oids is not None else None),
    }


RAW_WITNESS_FIELDS = ("authority", "request_der", "response_der",
                      "expected_nonce", "ca_file")


def require_round_after_witnesses(campaign_root_hex: str, beacon_record: dict,
                                  witnesses: list, *,
                                  minimum_authorities: int = MINIMUM_AUTHORITIES,
                                  pinned_authorities: dict | None = None,
                                  pinned_policy_oids: set | None = None,
                                  openssl: str = "openssl") -> dict:
    """The beacon round must be published strictly AFTER every witness.

    Both halves of the decision are DERIVED here, not supplied.  In r4 the
    subject and the round's publication time were both read from the caller --
    and the subject from the UNTRUSTED witness array at that, so a submitter
    could timestamp any digest of their choosing and the call would return a
    success dict.  Now the caller passes only bytes whose meaning it cannot
    choose: the campaign root, and a beacon record already bound by
    `stage2_beacon_nonce.bind_beacon`.

      * `policy_digest` is SHA-256 of the record's canonical-JSON policy, and
        `expected_subject` is derived from it with the campaign root.  Every
        token is verified against THAT subject, and a witness dict that
        carries its own `expected_subject_digest` is refused outright.
      * `round_publication_time` comes from the record's own policy and round
        via `publication_time`, and `recheck_beacon_record` must return exactly
        True -- it returns False for precisely a record whose round does not
        re-derive, which r4 discarded, accepting a forged round and inflating
        the margin.

    Independence is keyed on each token's verified signing key; ordering uses
    the latest possible true time given the declared accuracy; every witness
    must attest the same subject; `pinned_authorities`, if given, maps each
    permitted label to the SPKI fingerprint it must carry; `pinned_policy_oids`,
    if given, restricts the TSA policies those keys may assert under.
    """
    _require(type(witnesses) is list and witnesses, "witnesses must be a non-empty list")
    _require(type(beacon_record) is dict, "beacon_record must be a bound beacon record")
    # The subject and the round's time are both recomputed from the record.
    # recheck_beacon_record raises BeaconError on a malformed record and
    # returns False when the recorded round does not re-derive from its own
    # policy and pin; the False case is the forged-round attack, so it must
    # be refused rather than merely noted.
    try:
        recheck = beacon.recheck_beacon_record(beacon_record)
    except beacon.BeaconError as exc:
        raise WitnessError(f"the bound beacon record is not self-consistent: {exc}") from None
    _require(recheck is True,
             "recheck_beacon_record did not confirm the recorded round; the "
             "beacon record's round does not re-derive from its own policy and "
             "pin attestation, so its publication time is not trustworthy")
    policy_digest = beacon_policy_digest(beacon_record["policy"])
    expected_subject = witness_subject_digest(campaign_root_hex, policy_digest)
    round_publication_time = beacon.publication_time(
        beacon_record["policy"], beacon_record["round"])

    verified = []
    for witness in witnesses:
        _require(type(witness) is dict, "each witness must be a dict of raw material")
        # r4 let each witness declare its own expected subject, which is what
        # let a submitter choose what was being witnessed.  A witness carrying
        # one is refused rather than ignored, so a caller cannot believe it
        # was pinned.
        _require("expected_subject_digest" not in witness,
                 "a witness must not carry expected_subject_digest; the subject "
                 "is derived from the campaign root and the beacon policy")
        for key in RAW_WITNESS_FIELDS:
            _require(key in witness, f"witness is missing {key}")
        record = verify_token(witness["request_der"], witness["response_der"],
                              witness["ca_file"], witness.get("untrusted_file"),
                              openssl,
                              expected_subject_digest=expected_subject,
                              expected_nonce=witness["expected_nonce"])
        verified.append((witness["authority"], record))
    summary = _order_verified(round_publication_time, verified,
                              minimum_authorities, pinned_authorities,
                              pinned_policy_oids)
    # Named so an auditor can see the subject was derived, and from what.
    summary["beacon_policy_digest"] = policy_digest
    summary["campaign_root"] = _hex32(campaign_root_hex, "campaign_root").hex()
    return summary


def witness_limits() -> dict:
    """What a timestamp witness does and does not establish."""
    return {
        "establishes": [
            "at least the required number of independent authorities each "
            "signed a token binding the campaign root and beacon policy to a "
            "time, and every token verified cryptographically",
            "the selected beacon round is published strictly after the latest "
            "of those times, so its randomness was not available when the "
            "commitment was made",
            "the attested instant agrees between openssl and an independent "
            "scan of the token bytes",
            "the subject every token was checked against is DERIVED from the "
            "campaign root and the beacon record's own policy, and the round's "
            "publication time is re-derived from that same record, so neither "
            "can be chosen by whoever supplies the tokens",
        ],
        "does_not_establish": [
            "that a nonce proves a token is fresh OFFLINE. The nonce is "
            "supplied by the same party who submits the token, so checking it "
            "proves only that the token matches the request that party also "
            "holds; anyone replaying an earlier issuance replays its nonce "
            "with it. Replay protection requires the OWNER to record each nonce "
            "at request time and compare against that record",
            "that the beacon round is really the one the chain published. The "
            "record is rechecked for internal consistency only; confirming the "
            "round against the live drand endpoint and verifying the BLS "
            "signature are external checks named by the beacon module",
            "that two DISTINCT signing keys belong to two independent "
            "ORGANISATIONS. Distinctness is checked on the verified signing key, "
            "which defeats one TSA posing as two; it cannot tell that one "
            "operator runs two keys. Only pinning a set of authorities chosen "
            "in advance, from organisations known to be unrelated, addresses "
            "that",
            "that the minimum number of authorities was met at the module's "
            "default. minimum_authorities is a caller-supplied parameter and "
            "may be relaxed below MINIMUM_AUTHORITIES, which weakens the trust "
            "model without forging anything. It is therefore recorded in the "
            "summary as minimum_authorities_applied, and a consumer that does "
            "not read that field cannot tell a one-authority result from a "
            "two-authority one",
            "anything for a TSA whose token declares no accuracy. Such a token "
            "is refused, because without a stated error bound the ordering "
            "cannot be made conservative; accepting one needs an explicit "
            "policy decision about the bound to assume",
            "anything if every supplied authority colludes or backdates. Using "
            "distinct authorities reduces this; it does not remove it. A "
            "proof-of-work anchor such as OpenTimestamps removes the trusted "
            "party entirely and is not implemented here",
            "that the campaign root is the root of the run being audited. This "
            "module timestamps a digest handed to it and cannot see where it "
            "came from",
            "correctness of any result. A timestamp orders events; it says "
            "nothing about whether the computation is right",
            "independent REVIEW. This replaces the witness role only. Judging "
            "whether the science and the implementation are sound remains a "
            "human function and is not automatable by a timestamp",
            "anything openssl gets wrong about signature or chain validity. "
            "Those are delegated to it; this module does not reimplement CMS. "
            "Every attested VALUE, by contrast, is read from the signed DER by "
            "this module and never from openssl's text",
        ],
        "assumes": [
            "the authorities are genuinely independent of each other, of the "
            "owner and of the producer",
            "each token was obtained with a fresh nonce, so a replayed or "
            "cached token cannot stand in for a current one",
            "the CA material used for verification was obtained out of band "
            "and not from the same response being verified",
            "the bound beacon record passed in was produced by "
            "stage2_beacon_nonce.bind_beacon and its pin attestation is honest. "
            "This module re-derives the round from the record and refuses a "
            "record that does not re-derive, but it cannot see the chain",
        ],
    }

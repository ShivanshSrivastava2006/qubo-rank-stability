#!/usr/bin/env python3
"""Drand beacon binding for the Stage-2 sampled-verification nonce.

Mechanism only.  No Stage-2 value, instance, coefficient, candidate or
scientific record is read or written, and this module makes no network call:
the beacon response is supplied to it, never fetched by it.

READ THIS FIRST -- WHAT THIS MODULE CANNOT DO.

The adversary this binding exists to constrain is the party running the
verification, and that party writes the harness that calls this module.  Every
argument crosses that boundary.  **A local, stateless module cannot police its
own caller**, and nothing below should be read as if it could.  Independent
review of revision 1 put it plainly: the module constrains accidental deviation
by an honest harness author; it does not constrain a dishonest one.

What this module therefore is: a structure that makes the honest procedure the
easy one, records enough evidence for somebody else to check the dishonest
cases, and refuses the shapes that would otherwise let a mistake pass silently.
The properties that actually carry the anti-steering guarantee are **outside**
this module and are named in `required_external_checks()`:

  * the pin timestamp must come from a witness neither party controls;
  * the beacon must be independently fetched for the recorded round from a
    public drand endpoint and compared;
  * the BLS signature must be verified by a tool that can do pairings.

WHY DRAND RATHER THAN A SELF-CHOSEN NONCE.  An owner who wants to pass a run
they know to be corrupt can redraw a self-chosen nonce until the audit misses
the bad points -- for one bad point in 680,943 with a sample of 2,000, a few
hundred draws suffice.  A public beacon removes the choice, PROVIDED the round
is fixed by something neither party picks.

SCHEME PARAMETERS ARE VERIFIED, NOT DECLARED.  Two independent reviewers gave
contradictory accounts of which BLS12-381 group carries drand signatures and
which carries public keys, and one account was internally inconsistent.
Revision 2 turned that disagreement into a policy parameter, which made the
value explicit but not correct -- as the next review pointed out, declaring a
cryptographic parameter is not verifying it.  Revision 3 resolves it from
primary source: the chain information was fetched from the public drand API and
the observations are preserved in
`GATE_9_DRAND_CHAIN_INFO_OBSERVATIONS.md` beside this file.  A policy must now
name a scheme from `VERIFIED_SCHEMES`, and its declared lengths are checked
against the measured ones.

REVISION HISTORY
  r1  Initial.  Four independent reviews found: a backdated pin timestamp
      selects an already-published round and hands BOTH parties a pre-known
      nonce; `expected_round` was a free argument so any round could be
      substituted; the signature/public-key size sets were unioned and the
      accompanying comment inverted G1 and G2; the evidence record omitted the
      policy, so an auditor could not check the round was policy-derived; and
      `public_key` was validated once and never used again.
  r2  One entry point computes the round internally from the policy and an
      attested pin; the selected round must be provably unpublished at pin
      time; sizes were policy-declared and exact; the evidence record carries
      the whole policy; the limits lead with the fact that this module cannot
      constrain its caller.
  r3  This revision.  Chain facts resolved against the live drand API instead
      of reviewer recollection.  Confirmed: `default` carries a 48-byte public
      key with 96-byte signatures and IS chained; `quicknet` carries a 96-byte
      public key with 48-byte signatures and is unchained; the two lengths
      always differ; `randomness == SHA-256(signature)` holds on both; and
      round r is published at `genesis + (r-1)*period` on both, which excludes
      the competing convention and retires r2's "take the earlier of two
      formulas" hedge.  A third published chain, `evmnet`, is on BN254 with a
      128-byte key, so a 48/96 model does not describe it and it is refused.
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import hashlib
import json

SCHEMA = "decisions_os/stage2_beacon_nonce/v3"
NONCE_DOMAIN = b"decisions_os/stage2_beacon_nonce/v3"

RANDOMNESS_BYTES = 32
CHAIN_HASH_BYTES = 32

# Measured from the live drand API on 2026-09-26; raw responses and the method
# are preserved in GATE_9_DRAND_CHAIN_INFO_OBSERVATIONS.md beside this file.
# A scheme absent from this table is refused rather than guessed at: the
# published `evmnet` chain is on BN254 with a 128-byte key, so the BLS12-381
# 48/96 model does not describe it.
VERIFIED_SCHEMES = {
    "pedersen-bls-chained": {
        "public_key_bytes": 48,      # G1
        "signature_bytes": 96,       # G2
        "chained": True,
    },
    "bls-unchained-g1-rfc9380": {
        "public_key_bytes": 96,      # G2
        "signature_bytes": 48,       # G1
        "chained": False,
    },
}
CHAIN_INFO_EVIDENCE = "GATE_9_DRAND_CHAIN_INFO_OBSERVATIONS.md"

OUTAGE_POLICY = "halt_and_require_owner_decision_no_fallback_round_no_redraw"

POLICY_FIELDS = ("chain_hash", "public_key", "genesis_time", "period_seconds",
                 "min_delay_seconds", "scheme_id", "signature_bytes",
                 "public_key_bytes")


class BeaconError(ValueError):
    """A typed refusal.  Every failure path in this module raises this."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise BeaconError(message)


def _hex(value: object, expected_bytes: int, label: str) -> bytes:
    _require(type(value) is str, f"{label} must be a hex string")
    _require(len(value) % 2 == 0, f"{label} must have even length")
    _require(all(c in "0123456789abcdef" for c in value),
             f"{label} must be lowercase hex")
    raw = bytes.fromhex(value)
    _require(len(raw) == expected_bytes,
             f"{label} must be {expected_bytes} bytes, got {len(raw)}")
    return raw


def validate_policy(policy: dict) -> None:
    """A beacon policy frozen BEFORE execution, in the owner decision record.

    `signature_bytes` and `public_key_bytes` are declared here rather than
    inferred.  They must differ: a drand chain's signature and public key live
    in different BLS12-381 groups, so a policy claiming the same length for
    both describes no real chain.
    """
    _require(type(policy) is dict, "policy must be a dict")
    for key in POLICY_FIELDS:
        _require(key in policy, f"policy is missing {key}")
    for key in ("genesis_time", "period_seconds", "min_delay_seconds",
                "signature_bytes", "public_key_bytes"):
        _require(type(policy[key]) is int, f"{key} must be an int")
    _require(policy["period_seconds"] > 0, "period_seconds must be positive")
    _require(policy["genesis_time"] > 0, "genesis_time must be positive")

    scheme_id = policy["scheme_id"]
    _require(type(scheme_id) is str, "scheme_id must be a string")
    _require(scheme_id in VERIFIED_SCHEMES,
             f"scheme {scheme_id!r} is not in the verified table "
             f"{tuple(VERIFIED_SCHEMES)}; see {CHAIN_INFO_EVIDENCE}. Declaring "
             f"parameters for an unverified scheme is not verifying them")
    verified = VERIFIED_SCHEMES[scheme_id]
    # Checked against measured values, not merely declared exactly.
    for key in ("signature_bytes", "public_key_bytes"):
        _require(policy[key] == verified[key],
                 f"{key} is {policy[key]} but {scheme_id} measures "
                 f"{verified[key]} (see {CHAIN_INFO_EVIDENCE})")
    _hex(policy["chain_hash"], CHAIN_HASH_BYTES, "chain_hash")
    _hex(policy["public_key"], policy["public_key_bytes"], "public_key")
    # A delay under one period could name a round already published at pin
    # time, which is exactly the predictability the beacon removes.
    _require(policy["min_delay_seconds"] >= policy["period_seconds"],
             "min_delay_seconds must be at least one full period")


def validate_pin_attestation(policy: dict, pin: dict) -> int:
    """The pin timestamp must be a witnessed claim, not a bare integer.

    Revision 1 took a raw int.  A backdated value selects an ALREADY-PUBLISHED
    round whose randomness has been public for years, so the producer can
    compute the nonce before designing the result set and the owner can pick
    the round -- both audits become theatre at once, and the resulting evidence
    looks flawless.  That was the most serious finding against r1 and it is why
    the timestamp now arrives with an issuer and a bound subject.
    """
    validate_policy(policy)
    _require(type(pin) is dict, "pin attestation must be a dict")
    for key in ("timestamp", "issuer", "subject_commitment_digest"):
        _require(key in pin, f"pin attestation is missing {key}")
    _require(type(pin["timestamp"]) is int, "pin timestamp must be an int")
    _require(type(pin["issuer"]) is str and pin["issuer"],
             "pin attestation must name the issuing witness")
    _require(type(pin["subject_commitment_digest"]) is str
             and len(pin["subject_commitment_digest"]) == 64
             and all(c in "0123456789abcdef" for c in pin["subject_commitment_digest"]),
             "pin attestation must bind a 64-hex commitment digest")
    _require(pin["timestamp"] >= policy["genesis_time"],
             "pin timestamp precedes the beacon genesis")
    return pin["timestamp"]


def publication_time(policy: dict, round_number: int) -> int:
    """When round `r` is published: `genesis + (r-1)*period`.

    Measured, not assumed.  Revision 2 hedged by taking the earlier of two
    candidate conventions, which supported a conservative check but left the
    protocol semantics unresolved.  Both published BLS12-381 chains were then
    sampled with the request latency bounded and both put the latest round's
    age inside `[0, period)` under this formula and in the future under
    `genesis + r*period`, which excludes it.  See CHAIN_INFO_EVIDENCE.
    """
    validate_policy(policy)
    _require(type(round_number) is int and round_number > 0,
             "round_number must be a positive int")
    return policy["genesis_time"] + (round_number - 1) * policy["period_seconds"]


def select_round(policy: dict, pin_timestamp: int) -> int:
    """The one round this protocol may use, given the policy and the pin.

    Deterministic and total.  Callers should prefer `bind_beacon`, which
    computes this internally; exposing it separately is for auditors
    re-deriving a recorded round.
    """
    validate_policy(policy)
    _require(type(pin_timestamp) is int, "pin_timestamp must be an int")
    _require(pin_timestamp >= policy["genesis_time"],
             "pin_timestamp precedes the beacon genesis")
    target = pin_timestamp + policy["min_delay_seconds"]
    elapsed = target - policy["genesis_time"]
    round_number = elapsed // policy["period_seconds"] + 1
    if publication_time(policy, round_number) < target:
        round_number += 1
    return round_number


def bind_beacon(policy: dict, pin_attestation: dict, response: dict,
                signature_attestation: dict) -> dict:
    """The single entry point: select the round and validate the response.

    Revision 1 split this so that `expected_round` was a free argument, which
    meant a caller could pass any round together with a genuine response for
    it and bypass round selection entirely.  The round is now computed here
    from the policy and the attested pin, and cannot be supplied.
    """
    pin_timestamp = validate_pin_attestation(policy, pin_attestation)
    expected_round = select_round(policy, pin_timestamp)

    # The property that actually matters, checked rather than assumed: the
    # selected round must not already have been publishable when the
    # commitment was pinned.  This holds under either publication convention
    # because the earlier one is used.
    _require(publication_time(policy, expected_round) > pin_timestamp,
             "the selected round could already have been published at pin time")

    _require(type(response) is dict, "beacon response must be a dict")
    for key in ("round", "randomness", "signature"):
        _require(key in response, f"beacon response is missing {key}")
    _require(type(response["round"]) is int, "beacon round must be an int")
    _require(response["round"] == expected_round,
             f"beacon response is round {response['round']}, the policy and "
             f"attested pin name {expected_round}; no other round may be used")

    randomness = _hex(response["randomness"], RANDOMNESS_BYTES, "randomness")
    signature = _hex(response["signature"], policy["signature_bytes"], "signature")

    # A chained scheme signs (round || previous_signature), so an external
    # verifier cannot rebuild the signed message without it.  Omitting it would
    # make the signature unverifiable by the very tool the attestation names.
    if VERIFIED_SCHEMES[policy["scheme_id"]]["chained"]:
        _require("previous_signature" in response,
                 f"{policy['scheme_id']} is chained; the response must carry "
                 f"previous_signature or the signature cannot be verified")
        _hex(response["previous_signature"], policy["signature_bytes"],
             "previous_signature")

    # Checkable without pairing arithmetic, and it catches a transcription
    # error or a mismatched pair.  It is NOT signature verification: anyone
    # inventing a signature can trivially compute its hash, which is exactly
    # how a forged beacon would pass this module.
    _require(hashlib.sha256(signature).digest() == randomness,
             "randomness is not the SHA-256 of the signature")

    _require(type(signature_attestation) is dict, "signature_attestation must be a dict")
    for key in ("verified", "verifier_tool", "verified_at", "chain_hash"):
        _require(key in signature_attestation, f"signature_attestation is missing {key}")
    _require(signature_attestation["verified"] is True,
             "the beacon signature is not attested as verified; this module "
             "cannot verify BLS itself and will not proceed without it")
    _require(type(signature_attestation["verifier_tool"]) is str
             and signature_attestation["verifier_tool"],
             "signature_attestation.verifier_tool must name the tool that verified")
    _require(signature_attestation["chain_hash"] == policy["chain_hash"],
             "signature_attestation is for a different chain")

    # The whole policy goes into the record.  r1 omitted it, so an auditor
    # could not re-derive the round and `public_key` -- the one field needed to
    # re-verify the signature -- was validated once and then never used again.
    return {
        "schema": SCHEMA,
        "policy": {key: policy[key] for key in POLICY_FIELDS},
        "pin_attestation": dict(pin_attestation),
        "round": expected_round,
        "publication_time": publication_time(policy, expected_round),
        "randomness": response["randomness"],
        "signature": response["signature"],
        "previous_signature": response.get("previous_signature"),
        "signature_attestation": dict(signature_attestation),
        "outage_policy": OUTAGE_POLICY,
    }


def nonce_from_beacon(record: dict) -> bytes:
    """Derive the 32-byte verification nonce from a bound beacon record."""
    _require(type(record) is dict and record.get("schema") == SCHEMA,
             "expected a bound beacon record")
    policy = record.get("policy")
    _require(type(policy) is dict and "chain_hash" in policy,
             "record carries no policy")
    chain = _hex(policy["chain_hash"], CHAIN_HASH_BYTES, "chain_hash")
    randomness = _hex(record["randomness"], RANDOMNESS_BYTES, "randomness")
    _require(type(record["round"]) is int and record["round"] > 0,
             "round must be a positive int")
    return hashlib.sha256(
        NONCE_DOMAIN + chain + record["round"].to_bytes(8, "big") + randomness
    ).digest()


def recheck_beacon_record(record: dict) -> bool:
    """Re-derive a recorded round from the record's own policy and pin.

    This is the check an auditor can perform offline.  It confirms internal
    consistency only; `required_external_checks()` lists what it cannot do.
    """
    _require(type(record) is dict and record.get("schema") == SCHEMA,
             "expected a bound beacon record")
    for key in ("policy", "pin_attestation", "round", "randomness", "signature"):
        _require(key in record, f"record is missing {key}")
    policy = record["policy"]
    pin_timestamp = validate_pin_attestation(policy, record["pin_attestation"])
    expected = select_round(policy, pin_timestamp)
    _require(type(record["round"]) is int, "round must be an int")
    signature = _hex(record["signature"], policy["signature_bytes"], "signature")
    randomness = _hex(record["randomness"], RANDOMNESS_BYTES, "randomness")
    _require(hashlib.sha256(signature).digest() == randomness,
             "randomness is not the SHA-256 of the signature")
    _require(publication_time(policy, expected) > pin_timestamp,
             "the recorded round could already have been published at pin time")
    return record["round"] == expected


def beacon_evidence_digest(record: dict) -> str:
    """One digest naming the preserved beacon evidence, policy included."""
    _require(type(record) is dict and record.get("schema") == SCHEMA,
             "expected a bound beacon record")
    payload = json.dumps(record, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def required_external_checks() -> tuple:
    """The checks that actually carry the guarantee, none of them in this code."""
    return (
        "Fetch the beacon for the recorded round independently from a public "
        "drand endpoint and confirm the randomness and signature match the "
        "record byte for byte. Without this a wholly invented signature, with "
        "its own SHA-256 as the randomness, passes every check in this module.",
        "Verify the BLS signature against the chain's public key with a tool "
        "that implements BLS12-381 pairings. This module cannot, and treats "
        "the attestation as trusted input.",
        "Establish the pin timestamp from a witness neither party controls -- "
        "for a Kaggle run, the server-side saved-version time -- and confirm "
        "the attestation's subject digest is the commitment actually pinned.",
        "Enforce single execution. The outage policy is HALT, but this module "
        "is stateless and cannot prevent a second attempt; only the procedure "
        "around it can.",
    )


def beacon_limits() -> dict:
    """What this binding does and does not establish."""
    return {
        "establishes": [
            "the round is a deterministic function of a frozen policy and an "
            "attested pin timestamp, and cannot be supplied by the caller",
            "the selected round was not publishable at the attested pin time, "
            "under either drand publication convention",
            "the supplied randomness is the SHA-256 of the supplied signature, "
            "a relation confirmed against both live BLS12-381 chains",
            "the scheme's key and signature lengths match values measured from "
            "the live chain, rather than values the policy merely declared",
            "the evidence record carries the whole policy, so the round can be "
            "re-derived offline by a third party",
        ],
        "does_not_establish": [
            "anything against the party that calls it. This module is local "
            "and stateless, and every argument it receives is supplied by the "
            "party whose steering it exists to prevent. It constrains an "
            "honest harness, not a dishonest one",
            "that the beacon is real. A caller may invent a signature, publish "
            "its SHA-256 as the randomness, and attest it verified; every "
            "check here passes. Only an independent fetch detects this",
            "that the beacon signature is valid. BLS on BLS12-381 needs a "
            "pairing implementation the standard library does not have and "
            "which is not available in this environment",
            "that the pin timestamp is honest. A backdated pin selects an "
            "already-published round whose randomness has been public for "
            "years, letting the producer pre-compute the nonce AND the owner "
            "choose it. The attestation records a claim; it does not verify it",
            "single execution. HALT is a policy, not an enforced state",
            "that the drand chain itself is honest or live",
        ],
        "assumes": [
            "every policy field is frozen in the owner decision record before "
            "execution, including the declared signature and public-key byte "
            "lengths taken from the chain's published info",
            "the full beacon response is preserved so a third party can fetch "
            "the round independently and re-verify the signature",
        ],
    }

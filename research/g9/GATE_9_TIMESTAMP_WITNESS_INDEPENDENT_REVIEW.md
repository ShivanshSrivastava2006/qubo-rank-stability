# Gate-9 timestamp witness — preliminary independent source review

Status: NOT READY for production acceptance. This is a read-only source review,
not amendment approval, witness-policy selection, or authorization for network,
dependency installation, instance generation, CUDA, or scientific writes.

Reviewed `stage2_timestamp_witness.py` at SHA-256
`cd2ea02e420f5c6030efe57e0216008bf0a60a22ee46248e77f8adfa0dc8025b`.
Existing fixtures passed 23/23 under normal Python and `-O`, both with
`PYTHONDONTWRITEBYTECODE=1` and `-B`. No dependencies were installed.

## Architecture

An independently trusted RFC 3161 TSA can supply the timestamp-witness role;
no human witness is inherently required. It does not replace independent review
or prove computation correctness. Its evidence depends on the TSA's signing
identity, trustworthy clock, certificate status, policy, and retained evidence.
Calling this universally stronger than a human witness or trust-free is not
justified. RFC 3161 expressly requires a trustworthy source of time and client
policy/certificate checks: <https://www.rfc-editor.org/rfc/rfc3161.html>.

## Blocking integration findings

1. **Caller labels are not independent authority identities.**
   `require_round_after_witnesses` accepts dictionaries without verifying their
   tokens and deduplicates only their caller-supplied `authority` strings.
   Reproducible: two records named `A` and `B`, both with `timestamp=100` and
   `token_sha256="same-token"`, are accepted for round publication time 101.
   The function does not even validate the token hash spelling. `verify_token`
   returns no signer certificate identity. Thus the claim that repeated tokens
   from one authority are refused is true only for repeated *names*.
   A campaign verifier must reverify retained request/response bytes against
   independently frozen trust configuration, derive signer identity from the
   authenticated certificate, and bind that identity to a pre-reviewed provider
   registry. Distinct keys or CA files alone do not prove organizational
   independence. It must also compare the request imprint to the independently
   expected campaign-root/policy subject, not trust an arbitrary supplied query.

2. **The ordering test omits timestamp uncertainty.** The implementation truncates
   fractional seconds and only requires `round_time > int(genTime)`. It neither
   parses token accuracy nor applies an externally frozen policy accuracy bound.
   RFC 3161 section 2.4.2 defines the token creation-time upper bound as
   `genTime + accuracy`; absent accuracy is not automatically zero and may be
   specified by the TSA policy. Compare the round's publication time against a
   conservative upper bound and the declared safety delay, retaining fractional
   precision. A token with genTime 100 and accuracy 2 seconds cannot establish
   pre-publication ordering for round time 101.

3. **Existence is not unique pre-challenge campaign designation.** A private TSA
   token proves that one commitment existed at an attested time. An adversarial
   owner can obtain tokens for many roots before the beacon, then select the
   convenient root afterwards. Timestamping root plus policy does not itself
   establish that exactly one root was irreversibly designated for the named
   campaign before randomness. The external publication/pinning rule must remain:
   a fixed campaign identifier, one accepted root/policy/round, a verifiable
   pre-round record, and a deterministic first-root/no-reselection rule.

## Other limits requiring review

The generic byte scan is not an independent ASN.1 TSTInfo parser; dates elsewhere
in the CMS object can satisfy it. Long-term verification requires an evidence
retention and certificate-status policy; signature validation today is not an
unconditional promise of validation years later. A fresh request nonce provides
response freshness, not independence or immutable public campaign selection.
The OpenTimestamps alternative retains its own consensus and timing assumptions;
it must not be described as assumption-free and is not reviewed here.

These findings do not reject RFC 3161 as the witness mechanism. They reject
claiming that the present helper and its passing fixtures have already closed
the campaign's backdating/selection boundary.

## Confirmed unsigned-wrapper backdating defect and narrow repair

The lead's independent review identified that the first `Time stamp:` match in
OpenSSL's whole-response text can come from unsigned `PKIStatusInfo.statusString`.
The reviewer reproduced this with a genuine locally signed token: the real signed time
was 1790441065, but adding an unsigned status string caused the old verifier to
accept 1577836800 (2020-01-01). The generic byte scan also accepted the injected
date. The signed CMS token and signature were unchanged.

The repaired parser first extracts the signature-verified token using
`openssl ts -reply -token_out`, renders only that token with `-token_in`, anchors
the timestamp line, and scans only the extracted bytes. A regression preserves
the genuine attested time when the unsigned wrapper injects the earlier date.
Final normal and optimized fixtures pass 24/24 each. An initial repair attempted
stdin input without an explicit OpenSSL input path and failed three baseline
tests; that was corrected to a temporary signed-token file before the final runs.

Final repair hashes:
- module: `2aa68d8f5084943a5e2ea4c3db3f55b813aafc7238b7b49dccc8db347f941c6b`
- fixtures: `b4be6c0ed0bc0d6d172671212b41fffe443026b918b9b9fec8e32d1afdbbf42a`

This fixes the reproduced unsigned-wrapper exploit only. The signer/trust-root,
subject binding, accuracy, immutable campaign designation and archival-policy
findings above remain open. The generic scan is still not a full TSTInfo parser.

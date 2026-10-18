# drand chain information — primary-source observations

Fetched 2026-09-26 from `https://api.drand.sh` by read-only HTTPS GET. No
credentials, no writes, no Kaggle involvement. Raw responses preserved beside
this file. These observations replace two contradictory reviewer accounts.

## Chains published by the endpoint

| beaconID | chain hash | schemeID | period | genesis |
| --- | --- | --- | --- | --- |
| default | `8990e7a9…b2ce` | `pedersen-bls-chained` | 30 | 1595431050 |
| quicknet | `52db9ba7…e971` | `bls-unchained-g1-rfc9380` | 3 | 1692803367 |
| evmnet | `04f1e906…c8c3` | `bls-bn254-unchained-on-g1` | 3 | 1727521075 |

## Measured key and signature lengths

| chain | public key | signature | chained |
| --- | --- | --- | --- |
| default | **48 bytes** (G1) | **96 bytes** (G2) | yes — response carries `previous_signature` |
| quicknet | **96 bytes** (G2) | **48 bytes** (G1) | no — no `previous_signature` field |
| evmnet | **128 bytes** (BN254) | not fetched | unchained per schemeID |

The two BLS12-381 chains carry the public key and the signature in **opposite**
groups, and the two lengths always **differ**. A policy giving both the same
length describes no real chain. evmnet is on **BN254, a different curve
entirely**, so a 48/96 model does not describe it at all.

## `randomness == SHA-256(signature)`

Confirmed on both BLS12-381 chains against live responses. True for chained and
unchained alike.

## Round publication time — RESOLVED

Round `r` is published at **`genesis_time + (r - 1) * period`**, so round 1 is
published at genesis.

Measured with the request latency bounded, on both chains:

- default, period 30: round 6500250, `genesis + (r-1)*period` was 26.0s before
  the request began — inside `[0, 30)`. The alternative `genesis + r*period`
  gave −4.0s, i.e. the future.
- quicknet, period 3: round 32545061, `genesis + (r-1)*period` was 0.3s before
  the request began — inside `[0, 3)`. The alternative gave −2.7s.

The competing convention `genesis + r * period` is **excluded** on both chains.

## Consequence for this project

The earlier "take the earlier of two formulas" hedge is no longer needed and
should be removed: the semantics are settled, not ambiguous. Scheme parameters
must be **checked against this table**, not merely declared.

---

## Scheme definitions from drand's own source (added 2026-09-26)

Fetched read-only from `raw.githubusercontent.com/drand/drand/master/crypto/schemes.go`
and preserved as `GATE_9_DRAND_SCHEMES_SOURCE.go.txt`. This is the official
implementation the reviewer asked the scheme to be verified against.

### `bls-unchained-g1-rfc9380` (quicknet)

Source comment, verbatim: *"This schemes has the group public key on G2, so 96
bytes, and the beacon signatures on G1, so 48 bytes."* **This matches the
measured values exactly.**

- KeyGroup = **G2** (96-byte public key); SigGroup = **G1** (48-byte signature)
- Signed message: `sha256( uint64_big_endian(round) )` — the round only
- Signature-group DST: `BLS_SIG_BLS12381G1_XMD:SHA-256_SSWU_RO_NUL_`
- Unchained, and tlock-compatible

### `pedersen-bls-chained` (default)

Source comment, verbatim: *"This schemes has the group public key on G1, so 48
bytes, and the beacon signatures on G2, so 96 bytes."* Also matches measurement.

- KeyGroup = **G1** (48-byte public key); SigGroup = **G2** (96-byte signature)
- Signed message: `sha256( previous_signature || uint64_big_endian(round) )`
- Signature-group DST: `BLS_SIG_BLS12381G2_XMD:SHA-256_SSWU_RO_NUL_`
- Chained, so `previous_signature` is required to rebuild the signed message

## A verifiability finding that cuts against the provisional chain choice

quicknet is the simpler **protocol** — unchained, no `previous_signature` — and
was the provisional recommendation on that basis. But it is likely the **harder
one to verify with available Python tooling**, and the reason is exactly the
one reviewer warned about: general BLS12-381 support is not sufficient.

Common Python BLS libraries, `py_ecc` among them, implement the **Ethereum/IETF**
orientation: public keys on **G1**, signatures on **G2**. That is the
orientation of drand's **default** chain, not quicknet's. quicknet inverts it.

- **default chain** — orientation (pk G1 / sig G2) matches the Ethereum scheme,
  and its DST `BLS_SIG_BLS12381G2_XMD:SHA-256_SSWU_RO_NUL_` is the IETF *basic*
  (NUL) ciphersuite, which is a standard library offering. Plausibly verifiable
  with an existing high-level API.
- **quicknet** — signatures on G1 require hashing to G1 with
  `BLS_SIG_BLS12381G1_XMD:SHA-256_SSWU_RO_NUL_` and pairing with a G2 key.
  Typically **not** exposed by a high-level Ethereum-flavoured API, so it would
  mean working against low-level pairing primitives.

**This is reasoning from the published schemes and the known IETF orientation,
not a demonstrated result.** No library was installed and nothing was verified
here. It is recorded so the chain choice is made with the verification cost
visible, and it strengthens rather than weakens the reviewer's condition: demonstrate
support for the chosen scheme **before** freezing the policy.

The trade-off to decide is therefore protocol simplicity (quicknet, unchained)
against verifiability with available tooling (default, but chained and needing
`previous_signature`, which the module already handles).

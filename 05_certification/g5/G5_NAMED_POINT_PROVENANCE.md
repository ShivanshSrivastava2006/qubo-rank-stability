# Gate-5 single named-point provenance

**Status:** produced by the reviewer; pending fresh controlling the second reviewer review. Gate 5 remains open.  
**Point:** primary `r=1`, ledger indices `(30,30,30)`, coordinates `(0.1,0.1,0.1)`, both encodings.  
**Authority:** `research/decisions/DECISIONS.md`, *Process Approval — Gate-5 clause-(b)
infrastructure acceptance and single named point*, SHA-256
`d746f2711993406963af049faf65f340adb95daaea3eea699c5cc13cbddf9984`.

## Producer boundary

The reviewer was the sole producer. The accepted clause-(b) sources were not modified. The only execution
harness and fast result verifier are additive files:

| Artifact | SHA-256 |
|---|---|
| `research/g5/run_named_point.py` | `85b4ae2c68411d6d71c806b9fcb653d655b3f65fc940bde8dcd0eb9c5b6dd24e` |
| `research/g5/verify_named_point_result.py` | `5794a2b4a6bc58fb7aebada24bb89b13dc2a58acad70a61263b2fee0e5a20c9d` |
| `research/g5/G5_NAMED_POINT_RESULT.json` | `07a209507afcb44d60a931df91b431d45425c8fd6623389c936d9506c5982f64` |
| `research/g5/G5_NAMED_POINT_RESULT.json.sha256` | `1a080d86cf4dc5a5fc647cf2d798e02aca13aecddd31f6fad00729b72ada4143` |

The result binds the accepted infrastructure and input hashes internally, including the canonical
instance, G3 ground truth, both ADNYE records, G4 ledger and evaluator/classifier, clause-(b) domain,
certifier and runner, worker vector/verifier, and the governing decision ledger.

## Pre-execution gate and command

The harness ran `research/g5/verify_worker.py` before primary-domain construction under both normal
Python and `python3 -O`. Both returned exit 0 with exactly `PASS worker self test`.

The sole production command was:

```text
PYTHONDONTWRITEBYTECODE=1 /usr/bin/time -v python3 research/g5/run_named_point.py
```

It exited 0. The harness is deliberately non-parameterized, refuses an existing output, and can execute
only the owner-declared center point for both encodings.

## Produced facts — no interpretation

| Encoding | `H_E_min` binary64 hex | `|T_E|` | `|X_E|` | D016 set label |
|---|---:|---:|---:|---:|
| slack | `-0x1.6f484ef393955p-7` | 1 | 1 | A |
| unbalanced | `-0x1.1c68452f3dcaap-6` | 1 | 1 | B |

The full encoded states, decoded states, atomic labels, selected tickers, coefficient hex values, input
values, platform fingerprint and bound hashes are in the result JSON. These are one-point certification
outputs, not a comparison, inference, trend, rate, or scientific conclusion.

## Domain and resource evidence

- unbalanced domain: `1,048,576` states;
- slack domain: `1,048,576` states;
- slack logical digest: `d052e67892d0e39882db26798f881628480d83c0119ee3a1e2ba9b1cdcf03063`;
- packed slack bytes: `12,582,920`;
- cache construction: `36.01929983700393` s;
- shared domain preparation: `493.11830889599514` s;
- certification of both encodings: `6.045925683982205` s;
- harness total: `535.8438778679993` s;
- external wall time: `8:56.80`;
- peak RSS: `1,125,268` KiB (`1098.89453125` MiB);
- swaps: `0`.

## Producer verification

The fast verifier ran successfully under both normal Python and `python3 -O`:

```text
PYTHONDONTWRITEBYTECODE=1 python3 research/g5/verify_named_point_result.py
PYTHONDONTWRITEBYTECODE=1 python3 -O research/g5/verify_named_point_result.py
```

It independently checks the file and content digests, declared point, bound artifact hashes, every
reported tied-state energy through the non-prepared canonical evaluator, `T_E -> X_E` decoding, original
hard feasibility, objective values, atomic labels and set labels. Both runs exited 0.

This fast check does **not** independently prove full-domain `T_E` completeness. The fresh controlling
The second reviewer review must rebuild and rescan both complete domains with an independently written minimum/tolerance
loop before recommending acceptance.

## Explicit stop boundary

No additional point, sweep, full core pass, Rust-produced primary value, Gate-6 work, interpretation,
conclusion, Gate-5 acceptance, or Gate-5 exit occurred. Production is stopped pending controlling review.

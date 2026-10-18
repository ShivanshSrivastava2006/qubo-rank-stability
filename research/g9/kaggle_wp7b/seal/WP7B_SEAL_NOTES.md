# WP7b — offline synthetic instance and Option A sealed reference

## Round 4 — owner-approved environment-pin identity re-bind

The round-3 identity's offline-host values were a builder error. The owner
directed this copy to re-bind WP1 to the hash-checked
`research/g9/kaggle_wp7/wp7_environment_pin.json` (SHA-256
`c0c57c774380ed025cf00925512ff57c6185ff0b4955669d5282bd1bdda0cadc`). The
single mapping function is `wp7b_identity_binding.build_identity_mapping`;
this builder supplies the checked pin's expected observations, and the armed
launcher supplies values returned by its probes to that same function.

| artifact | old round-3 SHA-256 | re-bound SHA-256 |
|---|---|---|
| production identity | `33a76780e54e240d47ac59814d0bacf4c71bfeb72c38f4213c447c5e1a45698c` | `fe8b814d03a8bafe9ce787303dcd5bb0bc75502e5af1d12e0e5c4c174797a7c2` |
| identity content hash | `a1aa3e788e7bdcd5577cf3fe6fca7d9e4db9728d99dec663c0a1d82371b49e87` | `bba613a2754fdd929bb659d381730e897a012f962a94c0d889fb6fd3f5bc2077` |
| seal inputs | `fdc7049d0a9cd5ec2b2950690b863e17edcc8f3482101ae09f9c532945d267ac` | `40be683c6d052aee1bef6f9b447a82425e6444742c60e320008413bb0becc573` |
| raw reference seal | `e4cd3daf633b7c894e3a1720236c516fb69eda0ba009d89a5ad517afc89e6099` | `220eae886fec6fecb594c7c9dcf7df2b6458b7846b90f6ce298c959f0cb69a5b` |

The raw seal is 301,745,088 bytes; zlib-9 is SHA-256
`dd02b10a2445a2d4080fede49829d72cfd886d2ef05d389906ae520f643b2307`, 351,155
bytes. The scientific content did not change: the instance, prepared record and
coordinates retain SHA-256 `19e5ab97…e557`, `6c0f49b1…0b38`, and
`371dcbce…d8d1`; all 160 per-unit result digests matched the previous seal and
their pre-existing shard records.

Identity mapping rationale follows the owner-approved post-run-audit choice and
`GATE_9_SECTION_B_IMAGE_IDENTITY_DECISION_DRAFT.md` §1 and §3. Runtime platform
and build-environment observations are platform assertions, not proof of the
executing OCI manifest (§1); they are compared to the owner pin before work.
The four `image_reported` values (`kaggle_image`, manifest digest, config id,
image name) and the saved-version build/kernel version values have no trusted
pre-run observation, so the first four use pin constants and the latter two use
declared fixed `[platform_reported]` strings. All are listed for post-run
metadata audit; a mismatch voids the run. No claim of cryptographic image
self-proof is made.

The owner-approved T4 smoke receipt dated 2026-09-29 22:05 reports successful
compilation/self-test and all 13 in-session observations equal to the pin. This
supports using the pin values as the expected session values; runtime identity
still comes from fresh probes.

**Status:** BUILD COMPLETE (offline packaging only). This record authorizes no
Kaggle push, no GPU allocation, no run, no draw, no launch and no scientific
record. §B remains **OPEN**.

**Built:** 2026-09-29. **Builder:** `build_wp7b_seal.py` (deterministic,
sha256 `4627386eb2c0c9106c6b1b76233e44310fe116cf436fd0ae38548a0b5037ed0b`).
**Fixture:** `verify_wp7b_seal_fixtures.py` (sha256
`3c6b24c7c76ecf40d925aa5253f97585d5e33eb73ba74cc2c635afa20bf31359`).
**Gate:** shared tool `jobs/tools/g9_guard_sweep.py`, table in
`logs/seal.sweep.txt`.

## 0. Which run this record is

This is the **ROUND-3 REGENERATE + RE-BIND** run. The round-2 artifacts were
lost (a `/tmp` reboot) and the recovered builder was rebuilt against **this**
project copy, which already carries the applied WP2 fix and the WP6b-GPU change.
That re-binding is not cosmetic: the WP1 production identity is a hash of 23
bound source files, two of which are exactly those files, so the identity hash
and the three artifacts that bind it (the seal, the inputs file and the identity
artifact itself) necessarily changed:

| artifact | round-2 sha256 | round-3 (this run) sha256 |
|---|---|---|
| `wp7b_production_identity.json` | `9213bf79…c12e` | `33a76780…4698c` |
| `wp7b_reference_seal.json` | `6b36d01a…887b` | `e4cd3daf…6099` |
| `wp7b_seal_inputs.json` | `4cc8eadf…61d1` | `fdc7049d…7ac` |
| production identity hash | `a97af2c4…a3c7` | `a1aa3e78…9e87` |

The other three artifacts (`wp7b_instance.json`, `wp7b_prepared_record.json`,
`wp7b_coordinates.json`) are **unchanged** at `19e5ab97…e557`, `6c0f49b1…0b38`
and `371dcbce…8d1`: they bind only the instance literals, the WP5b arithmetic and
the harness rows, none of which the WP2/WP6b edits touch. That is the correct
outcome and a useful cross-check — if the instance or the coordinates had moved,
something other than the identity binding had drifted.

## 1. The one synthetic instance

| field | value |
|---|---|
| seed | `0x574037425345414C` (the ASCII literal `WP7BSEAL`) |
| instance id | `wp7b_synthetic_width20_production_2p20` |
| width | 20 tickers (`WP7B00` … `WP7B19`) — **frozen production** |
| sectors | 4 sectors of 5: `{0..4} {5..9} {10..14} {15..19}`, labels `SEC0…SEC3` |
| domain | `2**20 = 1,048,576` decoded states |
| `kappa_risk` | `1.0` (D007 fixes it; WP5b refuses any other value) |
| `K`, `C`, `B` | `6`, `2`, `1100` (protocol-frozen, §18-20 of the protocol draft) |
| `p` | `p_i = 150 + 60*(i mod 3)` — the documented synthetic ladder |
| `mu` | `mu_i = -(1 + 0.25 i)` |
| `Sigma` | diagonal `0.02`, off-diagonal `0.001*(i+k+1)` (symmetric) |
| declared | `instance_kind="synthetic"`, `synthetic=true`, `source="wp7_synthetic_generator"` |

The seed is a **documented literal**, not a clock, an environment read or a
network value. It is not the preregistered Stage-2 master seed and reaches no
candidate stream: it names the arithmetic literals above, all of which are
written out in full in `wp7b_instance.json`.

The ladder is chosen so the budget is genuinely **load-bearing**: of the 19,000
cardinality- and sector-feasible portfolios only 1,999 satisfy `p^T x <= 1100`.
A slack budget would make the D013 budget family vacuous.

### Why the production width is not a choice here

* `research/g9/cuda_qualification/stage2_cuda_d013_inactive.py:499` refuses any
  decoded state count that differs from the frozen 2**20 domain
  (`counters["states"] == STATE_COUNT`, `1 << 20`), so WP6b only runs at 2**20;
* the provider-trust amendment requires FULL domains for the §B item 2 path;
* the owner's WP7 decision 3 measures WP3's real T4 time, which is only
  meaningful at the production width.

## 2. WP5b preparation

`resolve_optimum` → `lambda_ref` → `build_ledgers` → `build_provenance_record`,
all from `stage2_instance_preparation.py`, on this instance only.

| result | value |
|---|---|
| `f_star` | `15.509999999999991` |
| `Lambda_ref` | `10.920000000000002` (D008, strictly positive) |
| `\|F\|` | 1,999 feasible portfolios |
| `delta_full` | `75.5000000000002` |
| D010 grid rule | `q_min=-4`, `q_max=2`, `P=10`, `N_axis=61` |
| provenance | `prepared_synthetic_only`, `non_synthetic_supported=false` |

## 3. WP1 production identity

`stage2_production_identity.build_production_identity` over the real role map:
the accepted §A `v1_engine` 12-file release plus the eleven real WP1..WP6 source
files. 23 bound files. The payload is `DRAFT_UNQUALIFIED` / `authorization NONE`
and its image/build block is `is_proof: false`.

**production identity hash (this copy)**

```
a1aa3e788e7bdcd5577cf3fe6fca7d9e4db9728d99dec663c0a1d82371b49e87
```

## 4. The §B item 2 validation coordinates and the OFFLINE seal

Rows come from the frozen harness builders, so they cannot drift from the
amendment: 12 base rows (`build_validation_coordinates`) plus 4 D013 repeat rows
(`d013_repeat_coordinates`) = 16 rows, each × 5 frozen D015 comparator pairs × 2
frozen encodings = **160 sealed units**.

**coordinate digest** (width-independent, and unchanged from round 2)

```
9dcd1549ace7c6fb5f8144cbc42a8e0516db7bbd5ecdccf179bd12ab03a204e6
```

## 5. D013 fired

The four D013 repeat rows go through the real `build_condition_coefficients`
ablation, so the additive WP6b `+0.0` inactive families are genuinely evaluated.
The tallies are the count the D013 walk actually performed, not an estimate.

| condition | inactive families | `+0.0` additions | `f*` | stream words |
|---|---|---|---|---|
| `C` | sector, budget | 5,242,880 | `10.049999999999997` | 1,048,576 |
| `CB` | sector | 4,194,304 | `11.609999999999992` | 1,048,576 |
| `CS` | budget | 1,048,576 | `14.729999999999997` | 1,048,576 |
| `CSB` | none (all active) | 0 | `15.509999999999991` | 1,048,576 |

This is exactly D013's active/inactive map, and the non-zero tallies are what
prove the WP6b path was used rather than a copied all-active coefficient set.
`C` inactivates both families, so its slack stream makes five `+0.0` additions
per active lift — hence the exact power-of-two tallies.

## 6. Parallel precompute

The 160 units partition into eight `(condition, encoding)` groups
(65+65 for CSB, 5 each for the other three conditions × 2 encodings), because
the expensive 2**20 energy stream depends only on `(condition, encoding)`.

* 8 worker processes, each `nice -n 10`, one group per worker;
* **resumable per row**: every unit index is checked for an existing shard whose
  own `shard_sha256` re-verifies, and only missing ones are computed; a shard is
  written temp-then-`os.replace`, so an interrupted write is never read back;
* shard directory `jobs/scratch/seal/shards` (never `/tmp`), logs
  `jobs/scratch/seal/precompute.w{0..7}.log`;
* every worker ran under `python3 -B` with `PYTHONDONTWRITEBYTECODE=1`.

| measurement | value |
|---|---|
| per-worker peak RSS (`/usr/bin/time -v`) | **930,660 KB ≈ 909 MB** (budget 1.2 GB) |
| transcript build | 20.5 s, 884 MB |
| unbalanced stream | 2.9 s, 1,048,576 words |
| slack stream | 46.0 s, 1,048,576 words |
| one CSB unit (tie flags to index 934,400) | 4.7 s |
| shard-to-seal assembly | ~9 min (dominated by the ~75 s seal open × 2 for determinism) |

### Parallel ≡ serial, byte for byte

Two rows — unit 0 (CSB / unbalanced) and unit 121 (C / slack) — were recomputed
**inline in a single fresh process**, with no shard consulted, and compared with
the bytes the 8-worker pool had written:

```
serial  unit=0   digest=0c02c8ea9100774597d7836f8d38153ec5636a30ef0a075f135126b51cbbf8ca
parallel unit=0  digest=0c02c8ea9100774597d7836f8d38153ec5636a30ef0a075f135126b51cbbf8ca  identical=YES
serial  unit=121 digest=c4e200a324faee724552396d455c47d07790aa211d514dffbd50ab2a7df3d2ec
parallel unit=121 digest=c4e200a324faee724552396d455c47d07790aa211d514dffbd50ab2a7df3d2ec identical=YES
PARALLEL_SERIAL_BYTE_IDENTICAL=YES
```

This is not a coincidence of two similar code paths: the shard runner returns the
**same** `FrozenReference.unit_result` result, memoised to disk per unit.

## 7. Round trip

`open_for_session(seal, inputs)` **ACCEPTS** with the exact inputs the session
will pass, and returns a callable WP3-shaped reference. It **REFUSES** every
single-field tamper; all twelve were exercised against the committed 288 MB seal:

| tamper | outcome |
|---|---|
| each of the six `HASH_FIELDS` input digests | REFUSED — `input hash mismatch` |
| the production-identity hash | REFUSED — `production identity mismatch` |
| one coordinate's `point` | REFUSED — `missing or extra coordinate/encoding` |
| a dropped coordinate | REFUSED — `missing or extra coordinate/encoding` |
| one seal byte, offset 0 / 150,872,544 / 301,745,087 | REFUSED — `seal is not JSON` |

Four units (0, 1, 120, 121 — both encodings, both the all-active CSB condition
and the fully-inactive C condition) were opened **and** recomputed from the
frozen reference, and all three views agree on the pinned per-unit digest.

## 8. Mutation gate

Shared tool `jobs/tools/g9_guard_sweep.py` against `build_wp7b_seal.py` with the
fixture below. Table in `logs/seal.sweep.txt`.

The fixture command is the **small-domain** mode (§9), because the full 2**20
fixture costs ~15 minutes and the sweep runs 100+ mutants × 8 workers. That is
the whole point of the mode: the builder's own logic is width-parametric, so the
mutation gate exercises the same code paths on a width-8 instance at 118 s.

## 9. The affordable mutation gate: the SMALL-DOMAIN fixture mode

`WP7B_SEAL_FIXTURE=small python3 -B verify_wp7b_seal_fixtures.py`

| | full mode (default) | small mode (`=small`) |
|---|---|---|
| exercise width | 20 (`2**20`) | 8 (`2**8`) |
| committed artifacts | opened, sampled, digest-pinned | **digest-pinned only** (no seal parse) |
| wall | ~15 min | **118 s** |
| checks | 502 | 160 |

**The shipped artifacts stay at 2**20 in both modes.** Nothing in the small mode
changes a committed byte; it only narrows the fixture's own exercise of the
builder's logic. Both modes pin the same six artifact digests, the same identity
hash and the same coordinate digest.

The small mode re-binds every width-derived builder literal
(`WIDTH`, `SECTOR_SIZE`, `SECTORS`, `STATE_COUNT`, `PRICES`, `MU`, `SIGMA` — plus
the budget scalar `B`), restores them in `finally`, and then runs:

1. a fast SHA-256 check of the committed 2**20 artifacts against their recorded
   pins, cross-checked against the committed inputs file;
2. the typed-refusal, energy-word, sector-layout, shard and tie-flag groups;
3. instance + WP5b preparation + WP1 identity at width 8;
4. all four conditions × both encodings, the D013 ablation, both energy forms
   agreeing value-for-value under `C` (where both families are inactive), the
   tie ladder, the D015/D016 reconstruction, and a **full `build()`** that writes
   all six artifacts and opens the resulting seal;
5. the shard interface (compute, reload, refuse) and a width-8 seal round trip
   with all twelve tamper refusals;
6. the CLI: `--list-groups`, `--compute-units` with a resume that recomputes
   nothing, and the three refusals.

Two deliberate, documented narrowings, both recorded at the call site:

* **`B = 1275` at width 8** (production keeps the protocol-frozen 1100). At width
  8 the price ladder spans 150…270, so `B = 1100` admits only the cheapest pair:
  `|F| = 1`, `f_F_max == f*`, `Lambda_ref == 0.0`, and WP5b correctly refuses at
  `stage2_instance_preparation.py:670`. `B = 1275` gives `|F| = 25`,
  `Lambda_ref = 3.12`, `Delta_full = 15.608` — so the tiny fixture exercises the
  same ledgers, box rule, grid rule and provenance path rather than dying on
  `_finite`.
* **the coordinate digest is width-independent** and must still equal the pinned
  production value, which the small mode asserts — the harness rows do not depend
  on the instance width.

## 10. Artifact digests and sizes

| file | sha256 | bytes |
|---|---|---|
| `wp7b_instance.json` | `19e5ab972c74d1ea21f060c832d25f0b921451dbf31eb12eadd500647dc1e557` | 4,376 |
| `wp7b_prepared_record.json` | `6c0f49b1866fa6ca32b994be82655180bbcb741755cb39b02b6aad1943b50b38` | 2,244 |
| `wp7b_production_identity.json` | `33a76780e54e240d47ac59814d0bacf4c71bfeb72c38f4213c447c5e1a45698c` | 9,022 |
| `wp7b_coordinates.json` | `371dcbce68d20caeec6edbcae63c6d51929c5fc0a006141e1240b452a836d8d1` | 3,239 |
| `wp7b_seal_inputs.json` | `fdc7049d0a9cd5ec2b2950690b863e17edcc8f3482101ae09f9c532945d267ac` | 36,220 |
| `wp7b_reference_seal.json` (raw) | `e4cd3daf633b7c894e3a1720236c516fb69eda0ba009d89a5ad517afc89e6099` | **301,745,088** |

### The seal, raw and zlib-9

| form | sha256 | bytes |
|---|---|---|
| raw | `e4cd3daf633b7c894e3a1720236c516fb69eda0ba009d89a5ad517afc89e6099` | 301,745,088 |
| **zlib level 9** | `3840a644739aba3638188effbb319ce81b4561269f80f37e2a2d4b29ded6e393` | **351,156** |

The seal is 301,745,088 raw bytes because it stores one three-bit tie flag per
domain position up to the canonical minimum; zlib-9 compresses it by 859×, which
is what makes a production-width seal shippable at all. The raw digest is the
committed artifact and the digest the fixture pins.

## 11. Regeneration

`build_wp7b_seal.py` refuses to overwrite (`"xb"`), so a rebuild into a populated
directory is a clean refusal with exit code 1. Into a **fresh** directory it
reproduces every artifact **byte-for-byte**.

This run assembled the artifacts **twice**, into two fresh directories from the
same shard set. The two SHA-256 listings, in order, and their diff:

```
=== SHA256 LISTING (run 1) ===
371dcbce68d20caeec6edbcae63c6d51929c5fc0a006141e1240b452a836d8d1  wp7b_coordinates.json
19e5ab972c74d1ea21f060c832d25f0b921451dbf31eb12eadd500647dc1e557  wp7b_instance.json
6c0f49b1866fa6ca32b994be82655180bbcb741755cb39b02b6aad1943b50b38  wp7b_prepared_record.json
33a76780e54e240d47ac59814d0bacf4c71bfeb72c38f4213c447c5e1a45698c  wp7b_production_identity.json
e4cd3daf633b7c894e3a1720236c516fb69eda0ba009d89a5ad517afc89e6099  wp7b_reference_seal.json
fdc7049d0a9cd5ec2b2950690b863e17edcc8f3482101ae09f9c532945d267ac  wp7b_seal_inputs.json

=== SHA256 LISTING (run 2) ===
371dcbce68d20caeec6edbcae63c6d51929c5fc0a006141e1240b452a836d8d1  wp7b_coordinates.json
19e5ab972c74d1ea21f060c832d25f0b921451dbf31eb12eadd500647dc1e557  wp7b_instance.json
6c0f49b1866fa6ca32b994be82655180bbcb741755cb39b02b6aad1943b50b38  wp7b_prepared_record.json
33a76780e54e240d47ac59814d0bacf4c71bfeb72c38f4213c447c5e1a45698c  wp7b_production_identity.json
e4cd3daf633b7c894e3a1720236c516fb69eda0ba009d89a5ad517afc89e6099  wp7b_reference_seal.json
fdc7049d0a9cd5ec2b2950690b863e17edcc8f3482101ae09f9c532945d267ac  wp7b_seal_inputs.json

BYTE-IDENTICAL ACROSS BOTH REBUILDS
```

The committed copies in `research/g9/kaggle_wp7b/seal/` carry exactly these
digests, and the fixture pins them as literals.

## 12. Scope

Synthetic only. No real dataset, no network, no Kaggle CLI or API, no credential
read, no device, no GPU. All scratch and precompute output lives under
`/home/shivansh-srivastava/decisions_os/g9_jobs/scratch/seal`, never `/tmp`.
Every process ran `python3 -B` with `PYTHONDONTWRITEBYTECODE=1`; there are zero
`.pyc` files under the copy.

## 13. Round 3 — test-gap closure and final mutation gate

The six production artifacts stayed byte-identical. `load_shard` now returns
`None` immediately for a non-dict JSON record before checking for a `result` key;
this closes the raw-`AttributeError` case for a string record containing the
word `result`. This invalid-record handling does not affect valid shards, and a
fresh production-width build from the existing shards reproduced all six
artifacts byte-for-byte.

### Classification of the round-2 equivalents snapshot

Each snapshot site below was reclassified against reachable function and CLI
inputs. Every (b) site is a test gap; all are now killed by the fixture. The
only (a) site is the empty-stream check at line 917, which no public input can
reach with an empty stream after the full-domain and encoding checks.

| Snapshot site | Classification | Test or precise semantic reason |
|---|---|---|
| `S5:740:12:6b8af437` | (b) TEST GAP — closed | `check_f_star_reduction_matches_frozen` supplies an interior minimum to the small-mode reducer. |
| `S5:740:14:6b8af437` | (b) TEST GAP — closed | Same interior-minimum probe; both BoolOp operands now change the observed minimum when mutated. |
| `S1:824:12:7ddcfb58` | (b) TEST GAP — closed | `check_small_domain_d013_fired` calls `state_for` with unknown conditions and requires refusal. |
| `S1:913:8:0a0c733d` | (b) TEST GAP — closed | `check_small_domain_typed_refusals` combines an invalid encoding with an invalid condition and checks encoding-refusal precedence. |
| `S1:917:8:d75eb902` | (a) SEMANTIC | `__call__` reaches this check only after the full-domain gate at `build_wp7b_seal.py:817`; `_unbalanced_stream` walks `range(len(transcript))` at `:544` and `_slack_stream` walks candidate lifts at `:604`. Every reachable accepted call has a nonempty stream. |
| `S1:1149:4:5e1a2c42` | (b) TEST GAP — closed | `check_small_domain_shard_path_refusals` calls `shard_path` with `None`, `''`, and `7`. |
| `S1:1150:4:1bebc3fe` | (b) TEST GAP — closed | The direct shard-path probe supplies `-1`, `'0'`, and `True`, and also checks a valid index. |
| `S5:1149:14:5e1a2c42` | (b) TEST GAP — closed | A truthy non-string directory (`7`) isolates the exact-type operand. |
| `S5:1149:16:5e1a2c42` | (b) TEST GAP — closed | An empty-string directory isolates the truthiness operand. |
| `S5:1150:14:1bebc3fe` | (b) TEST GAP — closed | Negative index and valid-index probes cover both outcomes of the lower-bound operand. |
| `S5:1150:16:1bebc3fe` | (b) TEST GAP — closed | The same direct bad-index and valid-index probes cover the second operand mutation. |
| `S5:1169:9:074cbba6` | (b) TEST GAP — closed | `check_small_domain_shard_runner` tests non-dict JSON, including a string containing `result`; `load_shard` now rejects non-dicts before membership access. |
| `S5:1169:11:074cbba6` | (b) TEST GAP — closed | A result-less record with a hash matching the reconstructed `result=None` body is refused and recomputed. |
| `S2:1183:4:fa0ee79e` | (b) TEST GAP — closed | `compute_group`/`write_shard` writes into a directory that does not yet exist and the test verifies the shard lands. |
| `S1:1258:4:c52ee23d` | (b) TEST GAP — closed | `compute_group` is called directly with an invalid directory and bad position; the test checks the directory guard's message. |
| `S5:1258:14:c52ee23d` | (b) TEST GAP — closed | Bad directory values paired with an invalid position isolate the type operand. |
| `S5:1258:16:c52ee23d` | (b) TEST GAP — closed | Bad directory values paired with an invalid position isolate the truthiness operand. |
| `S2:1189:8:a9cc41fa` | (b) TEST GAP — closed | `check_small_domain_shard_runner` injects an `os.fsync` failure and verifies `write_shard` propagates it. |
| `S5:1265:18:7520e0db` | (b) TEST GAP — closed | Direct `compute_group` probes cover out-of-range, negative, Boolean, and non-integer positions with the exact refusal. |
| `S1:1296:8:cff99138` | (b) TEST GAP — closed | `check_small_domain_build_argument_guards` calls `build` with `0`, `-1`, `161`, `True`, `2.0`, and `'3'`. |
| `S4:1296:17:cff99138` | (b) TEST GAP — closed | Those bad limits plus valid `coordinate_limit=1` distinguish the comparison from its valid path. |
| `S5:1296:17:cff99138` | (b) TEST GAP — closed | Bad and valid coordinate limits cover the first range operand. |
| `S5:1296:18:cff99138` | (b) TEST GAP — closed | Bad and valid coordinate limits cover the second range operand. |
| `S5:1296:19:cff99138` | (b) TEST GAP — closed | The same direct build probes cover this BoolOp operand. |
| `S5:1296:20:cff99138` | (b) TEST GAP — closed | The same direct build probes cover this BoolOp operand. |
| `S5:1296:21:cff99138` | (b) TEST GAP — closed | The same direct build probes cover this BoolOp operand. |
| `S4:1296:51:cff99138` | (b) TEST GAP — closed | Valid `1` and out-of-range `161` distinguish the first comparison operator. |
| `S4:1296:52:cff99138` | (b) TEST GAP — closed | Valid `1` and out-of-range `161` distinguish the second comparison operator. |
| `S1:1298:4:1abd6036` | (b) TEST GAP — closed | `build(Path(existing_directory))` checks the string-type guard independently from `os.path.isdir`. |

The snapshot's `load_shard`, `write_shard`, `compute_group`, and `build` site
line numbers after `load_shard` shifted when the structural check was split.
Their classifications above refer to the snapshot mutations; the final sweep
ran against the current source and reported no stale equivalents.

### New probes

* The width-8 f* probe assigns a unique synthetic minimum strictly between the
  first and last feasible masks, so `best is None` and `value < best` are both
  observable in the small fixture.
* Direct bad-input probes cover `shard_path`, `load_shard`, `compute_group`,
  `_parse_indices`, `build(coordinate_limit=...)`, string and non-string
  `out_dir`, and the CLI's `--out-dir` and missing `--precompute-dir` paths.
* A non-dict shard, a result-less shard with a self-consistent hash, a fresh
  shard directory, and an injected fsync error cover the shard refusal and
  write paths.
* A controlled second `seal.seal` result proves the build's determinism guard
  is observable and emits its own typed refusal.

### Final v1.1 mutation sweep

The final run resumed only prior killed/time-out results whose site IDs still
matched the current module; prior equivalence acceptances were discarded and
retested. The final table at the end of
`/home/shivansh-srivastava/decisions_os/g9_jobs/logs/seal.r3.sweep.txt` is:

| shape | sites | killed | timeout | survived | error | equivalent accepted | stale |
|---|---:|---:|---:|---:|---:|---:|---:|
| S1 | 43 | 37 | 0 | 0 | 0 | 6 | 0 |
| S2 | 14 | 14 | 0 | 0 | 0 | 0 | 0 |
| S3 | 4 | 4 | 0 | 0 | 0 | 0 | 0 |
| S4 | 68 | 66 | 2 | 0 | 0 | 0 | 0 |
| S5 | 112 | 110 | 2 | 0 | 0 | 0 | 0 |
| S6 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| **ALL** | **241** | **231** | **4** | **0** | **0** | **6** | **0** |

`SWEEP: PASS`. The four timeout outcomes count as killed under tool v1.1; there
were no survivors, errors, or stale equivalents. The six accepted equivalents
are the current-source invariant guards in
`/home/shivansh-srivastava/decisions_os/g9_jobs/logs/seal.r3.equivalents.json`:
the empty-stream check, the two fixed synthetic instance literals, the instance
state-count self-comparison, the D013 positive-tally duplicate already checked
by `require_d013_fired`, and the callable result guaranteed by
`open_for_session`.

### Round-3 finish checks

* Full fixture: `-B` passed with `checks=328`; `-B -O` passed with
  `checks=328`.
* All 160 shards in `scratch/seal/shards` re-verified their stored
  `shard_sha256`, coordinate, and encoding.
* `nice -n 10 python3 -B build_wp7b_seal.py --out-dir
  scratch/seal/r3_fresh_artifacts --precompute-dir scratch/seal/shards`
  rebuilt the production seal; each of the six outputs was byte-compared to its
  frozen copy and all six were identical. The two SHA-256 listings are in
  §10 and were repeated in the round-3 build log.
* The original project baseline has an existing difference outside this
  round's worktree changes: its
  `research/decisions/GATE_9_WP7_PINNED_DRAFT_AND_WP7B_OWNER_DECISION.md`
  has sha256 `7f6490867aa9723eb2faca07a9e8c24ded96f586dd2f89280fe532d14adf1d27`,
  while the copy's file has sha256
  `9f7f6f1917f2030400ee3c81d60bed2d3d69e5747cf6802e4bb7c917b93fd286` and an
  earlier timestamp (2026-09-29 14:45 versus 22:03 in the baseline). This file
  was not changed in round 3; changing it would alter the pre-existing pinned
  draft context. All files edited in this round are under
  `research/g9/kaggle_wp7b/seal/`.

# GATE 9 D013 CLEAN-CASE REFUSAL DIAGNOSTICS — UNROUTED NOTE

**Status: UNROUTED DRAFT. NOT OWNER-APPROVED. NOT A RELEASE ARTIFACT. NOT
T4-QUALIFIED. NO SUBMISSION IS AUTHORIZED BY THIS DOCUMENT.**

Date: 2026-10-02. Author: Space Bunny Alpha/high (builder), offline only.
Host: Linux, Python 3.12.3, **no `nvcc`, no CUDA device, no `/dev/nvidia*`**.

---

## 1. What this is

A new, versioned **diagnostic** qualification harness under
`research/g9/cuda_qualification_v2_diagnostics/`, addressing one measured defect
in the frozen D013 v1 plan.

**Nothing in the accepted project was edited.** The frozen v1 plan
(`ab0c9060…c5c`), the v1 `.cu` (`2d7bc8f5…023f`), the v1 bridge, the v1 release
draft (`e73a4ff4…0721`), all applied WP7b bytes, the applied v2 candidate and the
launcher, bundle, source map and seal are all byte-identical to before. Every
file here is new.

| File | Role |
|---|---|
| `d013_refusal_diagnostics.py` | the diagnostic helper: bounded/sanitized rendering + typed refusal |
| `stage2_cuda_d013_inactive_corruption_qualification_diagnostics.py` | the versioned harness (`d013-corruption-qualification-diagnostics/v2.1`) |
| `verify_d013_refusal_diagnostics.py` | synthetic-only offline checks |
| `v1_to_diagnostics_v2_1.patch` | the exact minimal delta against the frozen v1 bytes |

---

## 2. The measured defect this addresses

From the consumed T4 discovery push (`logs/discovery.d013.diagnose.bout`):
the clean case reached v1's `except d013.D013InactiveError` handler at lines
575–578, which raised `CorruptionQualificationError("clean D013 CUDA build was
rejected by the independent reference")`.

Three facts follow, all measured rather than assumed:

1. **The message was false.** v1 raises that *identical* string from two
   different branches — the numeric-disagreement raise at line 574 and the
   refusal handler at line 577. The reference never ran; nothing disagreed
   numerically. The receipt attributed a core refusal to the numerical oracle.
2. **The nested reason was discarded.** The handler was a bare `except:` with no
   `as` binding and no `from`. `str(exc)` was never captured into any record.
3. **The shipping channel could not have carried it anyway.** The preserved
   traceback keeps only the tail of the chained chain, truncated to 800 chars.
   Python prints the chained section *first* and the final exception line *last*,
   so a tail cut drops the nested reason entirely. This is measured, not
   theoretical — see checks N1d–N1h. Even in-process, v1 exposes the reason only
   through the implicit `__context__`, never through a deliberate `__cause__`.

So this is an **insufficient-diagnostics / harness-defect** condition, on a
non-drifted, correctly-compiled image, where fail-closed was nevertheless the
correct disposition and must stand.

---

## 3. What the new harness does, and what it deliberately does not

The harness clones the v1 case logic. Every decision is preserved:

* the release gate `_released` / `_check_token` and the token proof;
* the plan, the nine mutations, the detection cases and their order
  (`N9c–N9f` assert table and mutation identity against v1 at runtime);
* the failure order inside the case loop;
* the `direct_tiny_positive` refusal probe;
* the post-run source-map re-check;
* the `if mutation is not None and not detected` refusal (v1:583–585).

One behavioural change, in the clean-case catch only:

* it binds `as exc` and routes to
  `d013_refusal_diagnostics.raise_clean_case_refusal`, which raises the **same**
  `CorruptionQualificationError` type, still raised, still aborting the loop —
  now **chained from `exc`**, carrying a bounded, sanitized
  `refusal_diagnostic` record: nested exception type, nested reason (bounded),
  exception chain, and case/stage identity.

And one truthfulness change: the numeric-disagreement branch keeps v1's exact
wording but is now a **distinct** named constant, so the two branches can no
longer collide. `REFUSAL_MESSAGE` states the compiled core refused *before* the
reference was consulted; `NUMERIC_DISAGREEMENT_MESSAGE` keeps v1's
"rejected by the independent reference". Distinctness is asserted at import.

**Explicitly not done:** no guard added, removed or weakened; no catch-and-continue;
no success value substituted for a refusal; no release token minted; no owner
approval; no CUDA call; no scientific computation; no production input, seed,
beacon or draw; no write step; no launcher, bundle, source map or release touched.

### Bounded-rendering contract (why a hostile reason cannot flood or leak)

A refusal reason is untrusted text from a compiled-library boundary. Rendering is
bounded three independent ways: a raw scan limit, a hard render bound
(`MAX_REASON_CHARS`, matching the core harness's `str(exc)[:200]` convention),
and escaping of every character outside printable ASCII — so ESC/CSI/ANSI, CR/LF
and bidi/zero-width characters cannot survive into a log. Truncation is flagged,
never silent. A non-`str` reason is reported as a type name and never coerced
(`__str__` is not called). Checks N7a–N7z cover all of this, including a 50 MB
reason and a full-width hostile payload.

---

## 4. Offline test results

`PYTHONDONTWRITEBYTECODE=1 python3 -B research/g9/cuda_qualification_v2_diagnostics/verify_d013_refusal_diagnostics.py`

**98/98 passed, exit 0.** Synthetic only; no GPU, no nvcc, no network, no
credentials, no production input.

Coverage against the brief:

| Requirement | Checks |
|---|---|
| old catch loses the nested reason (negative control) | N1a–N1h |
| new path retains it, bounded + sanitized + typed refusal | N2a–N2o, N3a–N3d, N7 |
| no downstream execution after refusal | N4a–N4g |
| independent-reference mismatch stays distinguishable | N5a–N5h, N8a–N8b |
| malformed/long reason cannot flood or leak controls | N7a–N7z |

### Mutation test of the suite (proof it is not vacuous)

Six deliberate breakages were injected; every one was killed by the check that
owns the property:

| Mutant | Killed by |
|---|---|
| sanitization disabled | N7r (×4) |
| render bound removed | N7d, N7v |
| exception chaining removed | N2g, N2l, N2m |
| refusal swallowed, downstream continues | N2a, N4f, N4g, N5g, N5h |
| the two branch messages made identical | import-time `RuntimeError` |
| **undetected-mutation guard removed** | N6d |

The last one is notable: that guard is a real one that was momentarily dropped
during the build and reintroduced; the suite now pins it.

---

## 5. UNROUTED — why this cannot run on T4 as it stands

This harness is **UNROUTED / not runnable on T4**, pending a new owner-reviewed
release. Specifically:

* It is not referenced by the accepted launcher, the runtime config, the source
  map, the bundle or the seal (check N10a–N10b confirm none mention it).
* It carries **no** `owner_approved` release token and mints none. Its
  `run_qualification` still defers to the frozen release gate and would refuse
  before any compiler lookup, exactly as v1 does.
* It binds the **v1** source map. A v2 source map would require a new
  owner-reviewed release that does not exist; faking one is forbidden and not
  attempted.
* `owner_approved` is not asserted anywhere (check N10j).

### How it would later bind to a new release

1. Owner issues a **new** release document with a new schema id, a `source_sha256`
   map naming whichever `.cu` is authorized, a fresh `content_sha256`, and a fresh
   `owner_approved` decision. The old v1 release keeps validating against v1.
2. The launcher is re-pointed at the new release, source and bridge; the runtime
   config is regenerated; a new bundle, seal and approval record are produced.
   None of these are transferable from the existing v1 approval.
3. A new `VerifiedReleaseToken` is minted from the **new** release + source map.
   The existing token is not reusable.
4. `SOURCE_REL` / `SOURCE_RELS` in the harness are re-derived to the new `.cu`,
   and the full mutation sweep is re-run against it.
5. Only then, and only with a fresh owner authorisation and a new one-use
   discovery nonce (the 2026-10-01 push is consumed), could a T4 diagnostic run
   be scheduled. This document authorizes none of it.

---

## 6. What T4 evidence is still missing

Nothing here is evidence about real CUDA hardware. The specific gaps:

1. **The cause of the measured `G9_D013_REFUSED` is still unproven on hardware.**
   "Missing device-pointer staging" is a static/host-stub inference. The v2
   candidate that fixes it is under separate different-family review and is not
   qualified. A T4 run capturing the first non-success `cudaGetLastError()` /
   `cudaDeviceSynchronize()` status and the stage id is what would convert the
   inference into evidence.
2. **This diagnostic harness has never executed its `run_qualification` path.**
   Only `run_case` is covered offline, with fakes. A real nvcc compile, the nine
   mutation builds and the full case table are untested on this harness.
3. **The bounded-rendering contract has been tested only against synthetic
   exceptions.** Real reasons from a real compiled-library boundary may carry
   shapes not yet seen.
4. **No receipt has been produced by this harness**, so its receipt schema
   (`…corruption_receipt_diagnostics/v1`) is unproven against any owner review.
5. Scientific correctness is out of scope entirely and is not addressed by any
   check here. Host emulation cannot establish it.

All of §4 is failure-diagnostic evidence only. It is never WP7 acceptance and
never a production identity.

---

## 7. Hash manifest

### 7.1 New files (all under `research/g9/cuda_qualification_v2_diagnostics/`)

| File | SHA-256 |
|---|---|
| `d013_refusal_diagnostics.py` | `60af0b9fced996ea23b44fd4a195681f93e43deb38715ed96559fc37d1862ea8` |
| `stage2_cuda_d013_inactive_corruption_qualification_diagnostics.py` | `92eb09316190db6588ca7916c47708f1f7c4567ee0c9492889a8d7b4c608ed35` |
| `verify_d013_refusal_diagnostics.py` | `d61c57ced0721056806e352adffdc6efa0f7fe899a1c111b7ed0f07f78e051b9` |
| `v1_to_diagnostics_v2_1.patch` | `78eaedf69a17868c4617ec7536c65fc6bb6f5d2eea28d629f4519ccb1580aaf7` |
| `GATE_9_D013_REFUSAL_DIAGNOSTICS_NOTE.md` | this file (self-referential; verify by re-hash) |

### 7.2 Source inputs — read-only, verified unchanged

Identical to the hashes in `logs/discovery.d013.rootcause.vout`, so this build
acted on the same bytes that were diagnosed.

| File | SHA-256 |
|---|---|
| `research/g9/cuda_qualification/stage2_cuda_d013_inactive_corruption_qualification.py` | `ab0c906017fa7555ee5a00f8ba02cc15e8a467f046008d427be018c318382c5c` |
| `research/g9/cuda_qualification/stage2_cuda_d013_inactive.cu` | `2d7bc8f559ced574283b8b4430ab6326058ae351dc5dde89386934910a3d023f` |
| `research/g9/cuda_qualification/stage2_cuda_d013_inactive.py` | `06b02b2ba800f0c888eb1eb9d9d9a727c0f72d6a11871deeece6e0cf342f74c4` |
| `research/g9/cuda_qualification/GATE_9_D013_CUDA_RELEASE_DRAFT.json` | `e73a4ff4a38cb6b0cfbc35713b7ce727c6cb8b94b2c38310277a1dac372b0721` |
| `research/g9/verify_stage2_cuda_d013_inactive_host_emulation.py` | `b223206b9490fb7fe8ac12b829291a73d7ffbb1663b5cdab939bf9db4da98f4a` |

### 7.3 Scope

- All **61** protected baseline paths: **61/61 unchanged**, 0 changed, 0 missing.
- Files created in this copy: **5**, all new, all under
  `research/g9/cuda_qualification_v2_diagnostics/`. **No existing file edited.**
- The applied D013 v2 candidate under `research/g9/cuda_qualification_v2/` is
  unmodified.
- **`.pyc` files in the copy: 0. `__pycache__` directories: 0.** Every Python
  invocation used `PYTHONDONTWRITEBYTECODE=1 python3 -B`.
- No file was deleted. Temporary build artifacts confined to
  `g9_jobs/scratch/`.
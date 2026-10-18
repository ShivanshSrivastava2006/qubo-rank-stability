# Owner Decision Record — Gate-5 Platform Exception, Exit, and Gate-6 Entry

**Status:** APPROVED  
**Owner:** Shivansh  
**Approved:** 2026-09-16 03:56:04 IST  
**Authority:** Direct owner approval in the project-control conversation.

## Owner decision (verbatim)

> I approve the narrowly scoped Gate-5 platform exception for the Jun-19 to
> Jul-15 CPython 3.12.3 build timestamp split affecting exactly the 743 identified
> minority shards. I accept Gate 5’s completed 11,163-shard / 680,943-coordinate
> primary Python corpus and approve Gate-5 exit.
>
> I authorize entry to Gate 6 only within its already frozen Stage-1 computational
> scope. Gate 7 interpretation, conclusions, post-hoc sensitivity selection, and
> Rust primary values remain unauthorized.

## Evidence accepted for this narrow exception

- The primary corpus contains exactly 11,163 promoted budget-line shards and
  680,943 coordinates. Its source/input snapshot remains intact.
- `resume_manifest.json` internal content SHA-256
  `14b658451f4e144e79819393dec5ca9db6479013dfd93d0a0b58c0efe9cacecc`
  is valid; it records all 11,163 expected shards and `stopped_for_budget=false`.
- `coverage_audit.json` internal content SHA-256
  `fdef0caf588a575eb7c53b6bb72c6f42eac4c8e90915f4489af1f73c0a941194`
  is valid; it records 11,163 shards / 680,943 coordinates and intentionally
  contains no scientific outputs.
- The independent Phase-B report
  `research/g5/platform_equivalence_audit_v1/report.json` has file SHA-256
  `958fa5eb87df2f04d6da1f63735a623201c94a1900b12d8f39af6d27ed5f7bca`
  and valid internal canonical content hash. It recomputed every one of the 743
  Jul-15 minority shards (45,323 coordinates) with zero worker errors. All 743
  saved `schema`, `shard_id`, `keys`, and complete mathematical `records` fields
  reproduced bit-for-bit; every reported difference was provenance only.
- The fresh controlling adjudication independently confirmed corpus integrity,
  the two original production platform populations, and the limited scope of the
  evidence, then conditionally recommended this owner exception and Gate-5
  acceptance.

## Scope and limitation

The exception applies **only** to the original completed production corpus's
CPython 3.12.3 build-timestamp transition:

- 10,420 shards: `Jun 19 2026, 12:46:00`;
- 743 identified minority shards: `Jul 15 2026, 23:46:41`.

It does not establish a general permission to merge heterogeneous platform
fingerprints. The later Aug-31/kernel-31 environment was used only as audit
evidence; it contributes no production shard. The Phase-B run directly
reproduces the stored Jul-15 shards on that later audit environment. It strongly
supports, but does not directly execute, the same coordinates on the historic
Jun-19 build. This stated limitation is accepted as the basis for the narrow
owner exception.

## Gate effects

1. **Gate 5 is accepted and exited.** The declared Python CSB core-pass corpus
   is accepted as the authoritative Gate-5 mechanical certification corpus.
2. **Gate 6 entry is authorized only within its predeclared Stage-1
   computational scope:** D011 coarse curvature companion, V-14 expansion,
   D015 diagnostics, D013 conditional ablation if triggered, and rate-surface
   derivation. This record starts no computation by itself.
3. **Not authorized:** Gate-7 interpretation or conclusions, post-hoc
   sensitivity selection, Rust-produced primary values, changes to accepted
   Gates 0–5, or any expansion beyond the already frozen Gate-6 scope.

## Provenance preservation

`research/decisions/DECISIONS.md` is intentionally unchanged because its SHA-256
is embedded in every primary shard snapshot. This additive record is therefore
the owner decision record for this exceptional case; it does not retroactively
alter the production source snapshot.

The prior reviewer-created file is preserved unchanged as
`research/decisions/GATE_5_ACCEPTANCE_RECORD_UNRATIFIED_REVIEWER_DRAFT.md`
(SHA-256 `a4b8247800bd4c12fdb614561e64368ac03a49ae578769d9076829545fb3bed1`).
It is evidence of the prior reviewer scope breach, not owner authority and not
part of this decision.

# Gate-9 generator pre-run source review — integration still pending

Status: pure generator mechanics reviewed; NOT a production generation release.
No canonical instance was read, no real candidate drawn, and no science written.

The generator, generation-ledger and import-boundary synthetic verifiers all
passed normal Python and `-O`, with `PYTHONDONTWRITEBYTECODE=1` and `-B` (six runs).
The fixture's read-only planner path contains no draw.

Inspected seed material, SHA-256/PCG64 stream derivation, slot/attempt/purpose
separation, sector permutation/label-blind duplicate normalization, integer
feasibility screen, 249-by-20 MVN draw, covariance arithmetic, finite/symmetry/PSD
refusal, binary64 encodings, structural rejection codes and first-valid ledger
replay agree with the declared pure-function contract. No algorithmic blocker
was found for the canonical small-integer input domain.

Before a production draw:
1. Review and approve a separate implementation record pinning generator AND
   validator source hashes plus the complete CPython/NumPy/backend fingerprint.
   The current planner is not that approved record and omits the generation
   contract validator hash.
2. Integrate before-draw source/runtime checks against that record and start/end
   drift checks. The pure draw API does not invoke the planner's runtime guard;
   its limited version checks do not compare an approved full build fingerprint.
3. Implement/review the atomic generation writer, canonical input binding,
   manifests and failure cleanup. These are absent from the pure APIs.
4. Obtain separate owner draw/write permission. Fixture passes and approval of
   a sampled-verification mechanism do not grant it.

This review does not certify alternate library/backend builds, issue a pinned
production runtime, approve instance generation, or satisfy CUDA section B.

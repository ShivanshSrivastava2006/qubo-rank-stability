# ADNYE Output Contract — charter §5 field 5 (output location and content-hash scheme)

**Status:** **APPROVED — D014, 2026-08-25.** The supporting recommendation and revision history below are
retained for provenance; `DECISIONS.md` D014 is authoritative.
**Author:** the lead. **Created:** 2026-08-24. **REVISION 6 — 2026-08-25**, the reviewer corrective pass under
Shivansh's explicit handoff; §8 records the prior and current corrections. **REVISION 5 — 2026-08-25**,
limited the reviewer corrective pass after Shivansh's continuation instruction; §8 records C-ADNYE-1..8. **REVISION 4 — 2026-08-24**, after the reviewer's review
[20:13:56]. **REVISION 3 — 2026-08-24**, after the reviewer's final contract
review. **REVISION 2 — 2026-08-24**, after the reviewer's review
(the review log [2026-08-24 17:44:29]). **All five points accepted.** §8 records what changed.
**Gate:** G1 — specification only. **Raised by:** the reviewer [15:12:23]. **Reviewer:** the reviewer, out of band.

This memo originally **recommended**. Shivansh approved its revision-6 contract as D014 on 2026-08-25. If
this memo and `DECISIONS.md` disagree, **D014 wins.** The approval defines provenance requirements only;
it does not create a validator or output record, execute ADNYE, freeze W0b, or authorize G2+ work.

### Approval status — D014, 2026-08-25

The branch-conditional whitelist, single-source `Delta_full`, closed schemas, source-attested snapshots,
exact governing-rule strings, two-digest scheme, and conservative date rule are approved for D008/D010's
field-5 contract. The earlier proposed approval was retracted; D014 is the controlling approval.

## 1. The gap, stated precisely

`GATE_1_CHARTER.md` §5 requires every admitted prospective ADNYE record to state six fields. Field 5 is
**"standalone output location and content-hash scheme"**.

Both admitted records — `Lambda_ref` (D008) and the three-axis box (D010) — discharge field 5 with the
phrase *"immutable hashed output location"*. **That names no location and defines no scheme.** No
authoritative file supplies either; I searched `IMPLEMENTATION_SPEC.md`, `VALIDATION_SPEC.md`,
`GATE_1_CHARTER.md` and `DECISIONS.md`. The nearest existing material is `IMPLEMENTATION_SPEC.md` §F.5
(result storage) and §F.1's `instance.py` "content hash" — **both concern different objects**, and §F.5 is
about *results*, which ADNYE closures are forbidden to contain.

**Consequence, and its limit.** This does **not** undo D008 or D010. It means **the six-field closure
cannot be claimed complete at W0b**. Dated clarifications recording this are already in both records.

## 2. What field 5 must satisfy

M10 and `VALIDATION_SPEC.md` **V-13** require that every result artifact record "*the governing approved-
decision hash*", with V-13 falsified if "*any result file references a decision hash that postdates it*".
A resolved ADNYE value must therefore be:

1. **Standalone** — resolvable and hashable independently of anything downstream, so its closure provably
   contains no encoded-QUBO or result artifact; and
2. **Content-addressed** — so a downstream artifact can cite the exact value consumed and a later reader
   can verify the citation.

Any scheme meeting both is admissible. §4 is one such scheme, not the only one.

## 3. The living-file problem — and the error revision 1 made solving it

**`DECISIONS.md` is a living file by design.** D008 has been annotated three times since approval: the
transparency clarification, D010's supersession pointer, and the field-5 note. **A digest of D008's section
taken at G3 will not match one taken later, though the decision never changed.**

> **REVISION 1'S FIX WAS WRONG AND IS WITHDRAWN.** It proposed embedding the rule verbatim and hashing
> **that instead**. **A rule hash is not a decision hash.** M10 and V-13 require the *approved-decision*
> hash, so revision 1 would have silently dropped a required field while appearing to strengthen the
> scheme. **The reviewer is right: do not call a rule hash a decision hash.**

**The reframe that actually resolves it.** V-13's criterion is **temporal** — the decision must *predate*
the artifact — **not** that a digest stay invariant forever. So a decision digest is a **point-in-time
attestation of what the governing record said when it was consumed**, which is exactly what M10 wants.
Later annotation changing that digest is **detectable history, not a falsification**.

**So the record carries BOTH**, and neither substitutes for the other:

- `governing_decision_digest` + `governing_decision_approved_date` — satisfies M10/V-13. The **approval
  date is stable** even as annotations accumulate, and it is what V-13's ordering test compares against.
  **Recorded at the granularity the register actually supplies — see §4.2.1.**
- `governing_rule_verbatim` + `governing_rule_digest` — gives self-containment, so the record remains
  interpretable without resolving a reference into a file that has since moved on.

**This contract does not propose narrowing M10 or V-13.** A rule digest never substitutes for the required
approved-decision digest. Any future narrowing would have to amend **both** M10 and V-13 explicitly and is
outside this recommendation.

## 4. Recommended scheme

### 4.1 Location, exact whitelist, and validator interface

    resolved branch:     ADNYE-001_Lambda_ref.json          + ADNYE-001_Lambda_ref.json.sha256
                         ADNYE-002_s_domain_box.json        + ADNYE-002_s_domain_box.json.sha256
    stopped_zero branch: ADNYE-001_Lambda_ref.json          + ADNYE-001_Lambda_ref.json.sha256

A **dedicated location, `research/adnye/`**, so records never sit inside `03_result/` — the tree M10 polices. The complete
whitelist is **branch-conditional**: exactly four files in the resolved branch and exactly the ADNYE-001
pair in the `stopped_zero` branch. No other name, extension, subdirectory, or file is permitted there.

> **CORRECTED in revision 2.** Revision 1 argued the directory makes "standalone" **structural rather than
> promised**, because a stray file would be caught by a directory scan. **That was an overclaim.** the reviewer
> checked `research/audit/SCAN_SCOPE_POLICY.md`: the retraction ledger's manifest covers **`.md` and `.py`
> only**, so `.json` and `.sha256` are **outside it**, and a directory scan alone **does not prove** "no
> result artifact". There is no conflict with the scan policy — but there is no free coverage either.

**The property must therefore be enforced, not inherited.** The contract should require:

1. the exact branch-conditional whitelist above; and
2. `research/audit/validate_adnye_output.py`, invoked as
   `python3 research/audit/validate_adnye_output.py --root research/adnye/`, before any record is accepted
   or cited. It must reject (nonzero exit) a whitelist, schema, type, canonical-digest, sidecar, dependency,
   chronology, capture, or stopped-branch violation. The validator need not exist until the approved contract
   is implemented before the first G3 record; this memo creates neither code nor an ADNYE output.

The sidecar grammar is exactly `<64 lowercase SHA-256 hex><two spaces><JSON basename><LF>`. The validator
must reject any other byte, filename, extra line, or digest representation.

### 4.2 Common record fields and exact digest preimages

Every JSON record is a **closed schema**: its top-level key set, nested-object key sets, field types, and
allowed values are stated in §4.3; unknown fields, missing fields, duplicate JSON object keys, arrays where
an object is required, and objects where an array is required are rejected. A JSON number is valid only when
it is finite (not `NaN`, `Infinity`, or `-Infinity`) and is not a Boolean. `sha256:<64 lowercase hex>` means
the literal lowercase prefix followed by exactly 64 lowercase hexadecimal characters.

Every record has these common fields, with the values and exact top-level additions fixed by §4.3:

```json
{
  "adnye_id": "ADNYE-001 or ADNYE-002",
  "quantity": "per-record constant",
  "units": "per-record constant",
  "governing_decision": "D008 or D010",
  "governing_decision_approved_date": "YYYY-MM-DD",
  "governing_decision_source": {
    "path": "research/decisions/DECISIONS.md",
    "section_heading": "exact per-record heading",
    "source_file_digest": "sha256:<64 lowercase hex>",
    "capture_rule": "decision_section_v1"
  },
  "governing_decision_snapshot": "exact complete governing record",
  "governing_decision_digest": "sha256:<64 lowercase hex>",
  "governing_rule_verbatim": "exact complete frozen rule",
  "governing_rule_digest": "sha256:<64 lowercase hex>",
  "execution_point": "per-record constant",
  "inputs": [],
  "status": "resolved or stopped_zero",
  "resolved_at_utc": "YYYY-MM-DDTHH:MM:SSZ",
  "resolver": {"python": "implementation and version", "numpy": "version"}
}
```

Every shown scalar field is a JSON string except numeric outputs declared in §4.3; `inputs`,
`transparency_candidates`, and their permitted nested objects are the only arrays/objects beyond the two
closed common nested objects. Dates must be valid Gregorian `YYYY-MM-DD` dates, and UTC instants valid
`YYYY-MM-DDTHH:MM:SSZ` instants; lexical resemblance alone is insufficient. The validator rejects a
timezone-less, impossible, or leap-second instant. The `resolver` key set is exactly `{"python", "numpy"}`, with
both nonempty strings.

> **Digest preimages are fixed.** For either embedded text field, its digest preimage is exactly
> `field_value.encode("utf-8")`, with no Unicode normalization, trimming, newline insertion, or JSON
> escaping. The `sha256:` prefix is outside the 64-hex digest. A record must not contain its own record
> digest.
>
> **`governing_rule_verbatim` MUST be an exact permitted byte string with NO ellipsis.** Revision 1's
> example wrote `"F = {...}"`. **An ellipsis in a schema example invites a truncated record**, which would
> defeat self-containment. More importantly, a digest over an otherwise unconstrained string only proves
> that an arbitrary transcription was copied consistently; it does not prove that the approved rule was
> copied. The validator must require byte equality to the following respective strings. Each displayed line
> break is one LF (`\\n`); there is no final LF.

**For ADNYE-001 / D008:**

```text
Lambda_ref = max_{x in F} f(x) - min_{x in F} f(x)
F = { x in {0,1}^20 : sum_i x_i = K, n_j(x) <= C for all j = 1..4, p^T x <= B }
```

**For ADNYE-002 / D010:**

```text
Delta_full = max_{x in {0,1}^20} f(x) - min_{x in {0,1}^20} f(x)
rho_box = Delta_full / Lambda_ref
s_max = 10^(ceil(log10(rho_box)) + 1)
s_min = 10^(floor(log10(rho_box)) - 4)
COMMON CUBE [s_min, s_max] on ALL THREE axes: s_card, s_sector, s_budget
m_hi = 1
m_lo = 4
```

`rho_box` is the mandatory current spelling for D010's historical bare `rho`, under its dated notation
clarification. This is a symbol transcription, not a changed formula. No label, paraphrase, omitted margin,
or other text is valid in either field.

### 4.2.1 Conservative chronology for date-only approvals

> **CORRECTED in revision 4 (review).** Revision 3's schema wrote
> `"governing_decision_approved_utc": "2026-08-24T00:00:00Z"`. **That time is invented.** D008 and D010
> record only `**Approved:** Shivansh, 2026-08-24` — **a date, with no time and no zone.** Worse, the
> project works in **IST**: midnight IST on 2026-08-24 is `2026-08-23T18:30Z`, so the fabricated value is
> not even a defensible rounding of the real instant. **Do not fabricate provenance**, least of all in the
> field whose entire purpose is to attest provenance.

**Two distinct times, neither standing in for the other:**

| Field | Source | Granularity |
|---|---|---|
| `governing_decision_approved_date` | copied verbatim from the decision record | **date** — no time is invented |
| `resolved_at_utc` | the resolver's own clock when it emits the record | **instant**, UTC |

> **Required validator behavior:** when only an approval date exists, accept only if that date is strictly
> earlier than the UTC calendar date of `resolved_at_utc`; reject equal, later, malformed, or missing dates.
> This is deliberately conservative: same-day ordering is unprovable and therefore fails closed. A future
> sourced approval instant may replace this comparison, but no timestamp is fabricated here.

**`governing_decision_digest` is taken over an EMBEDDED SNAPSHOT, with a source attestation captured at
resolution.** This is not an arbitrary string. At intake, the validator must:

1. read `research/decisions/DECISIONS.md` as UTF-8 bytes and require its full-file SHA-256 to equal
   `governing_decision_source.source_file_digest`;
2. map `D008` and `D010` to their exact canonical headings, respectively
   `## D008 — Definition of \`Lambda_ref\` (U-03)` and
   `## D010 — Three-axis \`s\`-domain box (U-04)`, and require the corresponding
   `section_heading` value; and
3. extract the complete top-level Markdown decision section beginning at that heading and ending immediately
   before the next top-level heading matching `^## D[0-9]{3} —`, while ignoring heading-like text inside
   fenced code blocks. The extracted UTF-8 text must equal `governing_decision_snapshot` byte-for-byte.

`capture_rule` is exactly `decision_section_v1`; any other value fails. The validator then hashes that
embedded snapshot under §4.2 and requires `governing_decision_digest` to match. `governing_decision`
remains the stable register locator.

After a record is accepted, later edits to the deliberately living register do **not** invalidate the record:
they simply no longer match its captured full-file digest. A later audit validates the embedded snapshot and
its digest; it may compare the snapshot to current register text as a provenance diagnostic, but does not
silently rewrite it or demand equality to the mutable file.

> **REVISION 3 REPLACES A FRAGILE RULE.** Revision 2 defined the digest over a byte range of
> `DECISIONS.md` without binding the extraction to an identified source file or safe Markdown parsing.
> The present capture procedure is performed only at intake and records the full-file digest and canonical
> section heading alongside the self-contained snapshot. Thus later editorial change cannot redefine an
> already accepted decision snapshot.
>
> **This does not weaken M10/V-13.** V-13 requires "*the hash of the frozen decision record*"; a digest
> over the intake-verified exact embedded copy of that record **is** such a hash. **Both digests are still
> carried** — the decision snapshot's and the rule's — and neither substitutes for the other.

### 4.3 Per-record schemas, dependencies, and the five D008 candidates

**ADNYE-001 (`Lambda_ref`, D008):** its exact top-level key set is the common fields in §4.2 plus
`{"value", "delta_full", "transparency_candidates"}`. The constants are
`adnye_id="ADNYE-001"`, `quantity="Lambda_ref"`, `units="E"`, `governing_decision="D008"`, and
`execution_point="G3.compute_Lambda_ref"`. Its `inputs` array has exactly five ordered objects, each with
the closed key set `{"name", "digest"}`, in this order:
`canonical_mu`, `canonical_Sigma`, `D007_kappa_risk_triple`, `canonical_instance`, `F_predicate`.
Each digest has the §4.2 grammar.

`value` and `delta_full` are finite JSON numbers in units `E`, with `value >= 0` and
`delta_full >= value`. `transparency_candidates` is exactly the following ordered five-element array:

| Position | `statistic` | `population` | Required candidate keys |
|---|---|---|---|
| 1 | `range` | `F` | `statistic`, `population`, `value`, `units` |
| 2 | `std` | `F` | `statistic`, `population`, `value`, `units`, `ddof` |
| 3 | `range` | `cardinality_feasible` | `statistic`, `population`, `value`, `units` |
| 4 | `std` | `cardinality_feasible` | `statistic`, `population`, `value`, `units`, `ddof` |
| 5 | `range` | `binary_full_space` | `statistic`, `population`, `value`, `units` |

Every candidate `value` is a finite JSON number, `units` is exactly `E`, and each `ddof` is a nonnegative
JSON integer (not Boolean). The validator rejects missing, reordered, duplicated, extra, or incomplete
candidates. Reporting remains transparency-only, never re-selection.

If ADNYE-001 has `value = 0`, its status must be `stopped_zero`; it is D008's G3 stop condition, not a
substitutable result. The stopped branch permits exactly the ADNYE-001 pair and no ADNYE-002. Otherwise its
status must be `resolved`, which requires the resolved-branch whitelist.

**ADNYE-002 (three-axis box, D010):** its exact top-level key set is the common fields in §4.2 plus
`{"rho_box", "s_min", "s_max"}` — **not `Delta_full`**. The constants are
`adnye_id="ADNYE-002"`, `quantity="s_domain_box"`, `units="dimensionless"`,
`governing_decision="D010"`, and `execution_point="G3.exit.resolve_box"`. Its `inputs` array has exactly
two ordered objects, each with the closed key set `{"name", "adnye_id", "field", "digest"}`:
`{"name":"Lambda_ref", "adnye_id":"ADNYE-001", "field":"value", ...}` and
`{"name":"Delta_full", "adnye_id":"ADNYE-001", "field":"delta_full", ...}`. Both digests must
equal ADNYE-001's sidecar-verified record digest.

`rho_box`, `s_min`, and `s_max` are finite JSON numbers, with `rho_box >= 1`, `0 < s_min <= s_max`; the
validator reconstructs D010's approved formulas using ADNYE-001's referenced `value` and `delta_full` and
rejects any mismatch. Its status must be `resolved`. The validator rejects ADNYE-002 unless ADNYE-001 is
`resolved`, both references match its sidecar-verified digest, and the dependency graph is acyclic.

### 4.4 `Delta_full` is stored ONCE

`Delta_full` is required by D008 as a transparency candidate **and** by D010 as the box rule's second
input. **It is serialized exactly once**, in `ADNYE-001`'s `delta_full` field. `ADNYE-002` cites **that
field plus `ADNYE-001`'s record digest** as its `Delta_full` input:

```json
"inputs": [
  {"name": "Lambda_ref",  "adnye_id": "ADNYE-001", "field": "value",      "digest": "sha256:..."},
  {"name": "Delta_full",  "adnye_id": "ADNYE-001", "field": "delta_full", "digest": "sha256:..."}
]
```

**D010's two named inputs are preserved** — they are two named inputs, both resolved through one record.

> **REVISION 1'S APPROACH WITHDRAWN.** It serialized `Delta_full` twice and proposed making disagreement a
> **G3 stop condition**. **The reviewer's design is strictly better: remove the failure mode rather than detect
> it.** Two copies that must be equal is a defect waiting to happen; one copy cannot disagree with itself.
> It also **avoids creating a new obligation**, which §7 had to flag as a question. That question is now
> **withdrawn** — there is nothing to decide.

### 4.5 Canonical whole-record hash

    canonical bytes = json.dumps(record, sort_keys=True, separators=(",", ":"),
                                 ensure_ascii=False).encode("utf-8")
    digest          = sha256(canonical bytes)             -> sidecar, lowercase hex

**The record must NOT contain its own digest** — hence the sidecar. Source whitespace is not semantic: the
validator parses JSON and hashes the displayed canonical bytes, so a pretty-printed source has the same
valid canonical digest if and only if it represents the same object.

## 5. Verification boundary

The declared location, schema, and validator interface are an **M10 audit mechanism**. The charter's Class-A
list is closed and does not include M10; this memo neither labels it Class A nor amends that list. At G1,
review can establish only that the proposed declaration is complete. Before any G3 record is accepted, the
prescribed validator must check actual conformance.

## 6. What this memo does NOT recommend

- **No change to D008 or D010's approved content**, and **no change to M10 or V-13.**
- **No creation of `research/adnye/`**, no record files, no G2+ work. Specifying a location is G1;
  creating it is G3.
- **No claim that this scheme is uniquely correct.** Any scheme meeting §2's two properties is admissible.
- **No claim that approving this completes W0b.** It closes one field requirement of one charter section.

## 7. Questions for Shivansh

1. **Approve this scheme, or ask for a different one?** §2's two properties are the requirement; §4 is one
   way to meet them.
2. **Approve both digests and the conservative date rule?** This keeps M10/V-13 unchanged and rejects
   unprovable same-day provenance rather than inventing it.
3. **Nothing further.** A future sourced approval instant may permit same-day ordering, but this contract
   needs no new approval-recording obligation.

## 8. Revision record

### Revision 6 — the reviewer corrective self-audit under Shivansh's explicit handoff, 2026-08-25

Revision 5's proposed contract still had four live defects, all corrected here without approving the
contract or creating any G3 artifact. First, its "exactly two pairs" location rule contradicted D008's
`Lambda_ref=0` stop condition; §4.1 is now explicitly branch-conditional: the resolved branch permits both
pairs and `stopped_zero` permits only the ADNYE-001 pair. Second, it placed `Delta_full` in ADNYE-002 while
§4.4 required one serialization; ADNYE-002 now references only ADNYE-001's `delta_full` field and verified
record digest. Third, its purported schema left nested shapes and several type rules implicit; §4.2–§4.3
now declare closed top-level/nested sets, finite-number and valid-calendar rules, exact candidate/input
shapes, and unknown-key rejection. Fourth, an embedded decision snapshot was not tied to a deterministic
source; §4.2.1 now source-attests the full `DECISIONS.md` bytes, maps each decision to its canonical heading,
and specifies a fence-aware top-level-section capture rule. This pass also states the exact `research/adnye/`
location and the full D010 governing rule, so neither is left as an implementer inference. A final
self-adversarial read found that a "verbatim" field with no permitted byte value still admitted an arbitrary
but consistently hashed transcription; §4.2 now pins both exact strings and includes D010's `m_hi` and
`m_lo`, which were previously omitted from the prose transcription.

These corrections repair the DRAFT recommendation only. They do not repair D008/D010 field 5 by fiat, amend
M10/V-13, approve a contract, create a validator or output directory, freeze W0b, or authorize G2+ work.

### Revision 5 — limited the reviewer corrective pass, 2026-08-25

Shivansh's continuation instruction was treated as a limited handoff for C-ADNYE-1..8 only. The draft
remains non-authoritative and approves nothing. The schema now fixes inner UTF-8 digest preimages;
per-record D008/D010 inputs and dependencies; all five D008 candidates with stated `ddof` for std; an
equal-date fail-closed chronology rule; validator command, sidecar grammar, and reject conditions; M10's
correct classification boundary; no M10/V-13 narrowing; and the `Lambda_ref=0` stopped branch that forbids
ADNYE-002. No directory, JSON record, sidecar, validator code, decision, W0b freeze, or G2+ output was
created.

### Revision 4 — after the reviewer's review [20:13:56]. Accepted.

**Removed a fabricated timestamp.** `governing_decision_approved_utc: "2026-08-24T00:00:00Z"` invented a
precise UTC instant that no source supplies; D008/D010 give a **date only**, and under IST that fabrication
is not even a correct rounding. Replaced with `governing_decision_approved_date` at the granularity the
register actually provides, plus the separately-defined `resolved_at_utc` emission instant. **The reviewer
confirmed the snapshot digest correctly serves as the M10/V-13 decision-hash field**, which is unchanged.

**Worth naming: this was invented inside the provenance field itself.** The whole point of
`governing_decision_approved_*` is to attest what was approved and when. **A plausible-looking value with
no source is worse there than an admitted gap**, because it reads as evidence.

### Revision 3 — after the reviewer's final contract review. Accepted.

**Replaced the fragile decision-digest rule with an embedded `governing_decision_snapshot` plus its
digest**, keeping **both** the decision-snapshot digest and the rule digest, and retaining
`governing_decision` as a stable register locator. See the boxed note in §4.2.

**This closes the one weakness I had flagged for attack.** In revision 2 I wrote to the reviewer that the byte
range was "*the one place a purely editorial change to `DECISIONS.md` could break verification*" and asked
it to try to break it. It did, and the fix removes the dependency on the register's current bytes entirely
rather than patching the range definition. **Asking for the attack was worth more than the rule I was
defending.**

### Revision 2 — after the reviewer [17:44:29]. All five points accepted.

| # | Point | Disposition |
|---|---|---|
| 1 | `governing_rule_verbatim` may not use `F = {...}` | **Accepted** — §4.2 now requires exact text with no ellipsis and spells out D008's in full. |
| 2 | A rule hash does **not** satisfy M10/V-13's approved-decision hash | **Accepted; revision 1's §3 fix WITHDRAWN.** Record now carries **both** digests plus the approval timestamp. Verified against V-13's text. **This was the serious one** — revision 1 dropped a required field while appearing to strengthen the scheme. |
| 3 | Store `Delta_full` once and cite it, rather than duplicate + stop condition | **Accepted; strictly better design.** §4.4 stores it once in `ADNYE-001`. **The §7 question about a new stop condition is withdrawn — there is nothing left to decide.** |
| 4 | Declaration checks are **Class A**, not Class B | **Accepted.** §7 of the charter says Class B "**is specifically M4 and M5**" — a closed list my classification contradicted. |
| 5 | `.json`/`.sha256` are outside the ledger's `.md`/`.py` manifest | **Accepted.** §4.1's "structural rather than promised" claim **corrected**: the directory buys convenience, and a **filename whitelist plus a dedicated validator** is what actually makes the closure checkable. |

**On point 2 — the failure mode is one I should name.** I identified a real problem (living file vs stable
digest) and fixed it by **removing a requirement** rather than satisfying it, then presented the result as
a strengthening. That is worse than the overreach pattern already on my record, because **it degrades a
validation item while reading as an improvement**. The resolution turned out to need no trade at all: V-13
tests **temporal ordering**, not digest invariance, so both digests can coexist.

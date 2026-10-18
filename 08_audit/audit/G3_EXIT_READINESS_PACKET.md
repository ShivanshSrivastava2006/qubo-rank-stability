# Gate 3 exit-readiness packet — the reviewer

**Prepared:** 2026-08-25.  
**Status:** **GATE 3 EXIT APPROVED 2026-08-25.**  
**Scope:** This packet records the accepted exit-readiness basis. The later
direct human exit decision is recorded in `DECISIONS.md`; neither document
authorizes G4 or later work.

## Authority

Direct human authorization, 2026-08-25:

> Approved 2026-08-25: prepare and independently review the Gate 3 exit
> packet only, including required closure checks and append-only logs. Do not
> start G4 or construct grids, coefficients, QUBOs, certifications,
> experiments, or conclusions.

The completed G3 work is bounded by the controlling 2026-08-25 authorization
in `research/decisions/DECISIONS.md`: enumerate `F` and `{0,1}^20`, compute
`f*`, `X*`, `Lambda_ref`, and `Delta_full`; execute D014 ADNYE-001/002;
validate and independently audit them.  It is not blanket later-gate
authority.

## Exit-readiness checklist

| Required G3 obligation | Evidence and independent check | Result |
|---|---|---|
| Enumerate the original feasible population `F` | `G3_GROUND_TRUTH.json`: `|F|=976`; scalar FROZEN §5.2 replay reproduced the population and its range. | PASS |
| Enumerate all `{0,1}^20` states | `G3_GROUND_TRUTH.json`: population `1,048,576`; independent replay reproduced full-space range. | PASS |
| Compute original optimum | `f*=-0.011208571005366133 E`; `X*={GOOGL, BAC, JNJ, MRK, XOM, CAT}`, exact-set size 1. | PASS |
| Resolve D008 / ADNYE-001 | `Lambda_ref=0.009142375225086057 E`, nonzero; `Delta_full=0.018407980994804198 E`; five D008 transparency candidates recorded. | PASS |
| Execute D010 / ADNYE-002 after the nonzero predecessor | `rho_box=2.013479051296642`, `q_min=-4`, `q_max=2`, common cube `[0.0001,100.0]`. | PASS |
| Enforce the D008 stop branch | The result is nonzero, so the stopped-zero branch did not apply; no substitute was used. | PASS |
| D014 closed schemas, canonical sidecars, chronology, dependency edges, and source intake | `validate_adnye_output.py --root research/adnye --intake` passed before this packet, on the exact four-file resolved whitelist. | PASS |
| Independent replay of ADNYE-001 | `audit_adnye_001.py` enumerated independently and agreed within 32 ULPs. | PASS |
| Independent replay of ADNYE-002 | `audit_adnye_002.py` checked canonical sidecars, raw-decimal inputs, the two dependency edges, binary64 ratio, and exact integer-power endpoints. | PASS |
| Canonical and frozen input integrity | All 12 frozen Gate-1 verifiers, G2 delta harness, canonical manifest (6/6), and G3 manifest (8/8) passed. | PASS |
| Preserve G4 boundary | Producer-owned G3 paths contain no grid, coefficient, QUBO, certification, experiment, or conclusion artifact; occurrences are scope prohibitions only. | PASS |

The D010 box is conditional on `m_hi=1` (derived) and `m_lo=4` (recorded
judgement); its six-decade span is a design box, not an enforcement
certificate.  No later-gate inference follows from this result.

## Pinned evidence

| Artifact | SHA-256 |
|---|---|
| `research/ground_truth/G3_GROUND_TRUTH.json` | `13229ad17e0a109731c0682c1ce22a820ea3ca412364fd882a897d036fc475db` |
| `research/ground_truth/compute_g3_ground_truth.py` | `bb7f1f9dd708fc51c053fe9a31932c794cd3c98628bb4c8f8a80c777123076c2` |
| `research/ground_truth/G3_PROVENANCE.md` | `fe55fd83bf241c6793504aae19b7aa38ca2e824875f2bba0e1e00de379df4fe2` |
| `research/adnye/ADNYE-001_Lambda_ref.json` | `9473c205a002697492c75af9ab694920b6bf822b38b5bd5c58f8f240ca66116a` |
| `research/adnye/ADNYE-002_s_domain_box.json` | `9d634366be5c737dbefd1ade5be5f76ceb960c9af4fa4b3d4cbc5ab3b35a2992` |
| `research/audit/G3_ADNYE_001_INDEPENDENT_REPLAY.json` | `2cf3cefa0d882e3596c6ef76c3aecf323bf0a2e4cf616dd185953896f291f310` |
| `research/audit/G3_ADNYE_002_INDEPENDENT_REPLAY.json` | `bb43d8b60033e60ec8eb6db4d28739a09819dd773b847580bf7118b6bed2e9a7` |

## Acceptance-state propagation and re-emission safety — complete

The producer-owned ground-truth JSON, resolver, and provenance now accurately
separate production from external acceptance: the producer does not assert its
own acceptance, while the accepted branch is recorded by the independent
audits, this packet, the cross-review logs, and the shared status page. The
pre-clarification ADNYE-002 wording was corrected to require a sidecar/schema
verification of a nonzero ADNYE-001; final resolved-branch acceptance follows
ADNYE-002 and full audit.

The resolver also now rejects `--reemit-adnye-001` **before enumeration or any
output write** when ADNYE-002 exists. The negative test exited `1` with the
dependency explanation and left the ground-truth, provenance, and both ADNYE
records/sidecars byte-identical. This prevents accidental replacement of the
ADNYE-001 digest cited by ADNYE-002. The updated G3 manifest passes 8/8; no
numeric value, D014 record, decision snapshot, or G4 boundary changed.

## Gate 3 exit outcome

The direct human decision of 2026-08-25 approved Gate 3 exit based on this
accepted packet. See `research/decisions/DECISIONS.md` — *Process Approval —
Gate 3 exit*. Gate 4 and later work remain unauthorized and unstarted.

# Gate-9 conclusion-to-decisive-error mapping — offline draft

Status: independent source-based mapping only; no sample floor or new scientific
threshold selected. No instance or scientific value was generated or evaluated.

The protocol's worst-case decisive error size is one paired grid-point record.
No accepted positive robustness margin establishes that conclusion-changing
errors must affect 1,564 points or another convenient fraction of the grid.
Realized margins, if used, need independently verified evidence and a reviewed
certificate; the GPU's unverified reported margin cannot certify itself.

| Output or predicate | Worst-case decisive error | Required exact evidence |
| --- | --- | --- |
| A/B/C counts and exact rates | One label record | Independently established full census or a reviewed exact certificate |
| A/C rate-difference sign | One paired record at a boundary | Exact count differences or rigorous sign-preserving error bounds |
| D013 fires/no-fire | One paired record | Exact three A-count differences or a certificate preserving strict signs/zero |
| Literal bidirectional A advantage | One record can add/remove the only opposite-direction witness | Independently recomputed opposite-direction witnesses prove presence; absence needs complete checking/certificate |
| Non-box A region | One added/removed point | A sufficient verified non-box certificate can prove presence; box/absence needs complete membership evidence |
| Region size, component count, largest component | One bridge/hole/label | Independently established membership/topology or exact certificate |
| `all_five`, `any_one`, `count_of_five` | One decisive point in one instance | Establish each underlying instance predicate; reduction is mechanical |
| D015/D011/V-14 exact diagnostic rates | One label | Same exact-count requirement; diagnostics remain separate |
| H0 comparability, H1 sub-region, H2 measurability | No accepted adjudication threshold | Preserve existing nonadjudication; sampling cannot invent a threshold |

Evidence: Stage-2 protocol sections 3 and 5; D013 executable rule in
`research/g6/rate_surface_and_d013.py:199`; directional and box definitions in
`research/g7/stage1_inference.py:200`, `:218`, and `:339`; accepted conditioning
in `research/decisions/GATE_7_STAGE1_CONCLUSION_AND_EXIT.md`.

For 680,943 records, 2,000 uniformly sampled distinct records catch one bad
record with probability exactly 2000/680943, about 0.29371%. A 99% guarantee
against one bad record requires 674,134 samples. Therefore modest sampling is
a supplemental widespread-corruption diagnostic, not protection for all exact
conclusions. A positive existential witness is not a certificate of absence.

This draft specifies neither an owner confidence target nor a corruption floor.
Those must be explicitly approved for the supplemental diagnostic purpose and
must not be represented as changing the exact scientific rules.

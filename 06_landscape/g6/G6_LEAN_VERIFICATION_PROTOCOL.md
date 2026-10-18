# Gate-6 Lean Verification Protocol

Status: **shared operating thumb rule**  
Date: 2026-09-20 (Asia/Kolkata)

This is a workflow rule for the reviewer and the lead.  It reduces duplicate human
review and repeated no-change checks.  It does not amend a frozen decision,
weaken a runner's built-in validation, or replace an owner authorization.

## The rule

**Verify a changed boundary once, reuse the resulting evidence until that
boundary changes.**

A boundary changes only when one of these changes:

1. code that computes, validates, or publishes the relevant artifact;
2. a frozen input, input-identity registry, ledger, source snapshot, or owner
   authority bound by that artifact;
3. platform fingerprint, compiler/toolchain/flags, or numerical backend;
4. declared run scope, output schema, or scientific contract.

An unrelated file change, a discussion, or a repeated request to inspect an
unchanged artifact is not a changed boundary.

## Minimum evidence by phase

| Phase | Required evidence | Avoid duplicating |
|---|---|---|
| New or changed runner | Fixtures under normal Python and `python -O`; one independent pre-run review | Re-running the same fixtures or plans after no boundary change |
| Long computation | The runner's built-in input/platform checks; checkpoint monitoring | Separate manual copies of the same full input walk while the run is healthy |
| Published artifact | Its built-in read-only verifier and one independent post-run audit | Multiple tools repeating the same exhaustive audit without a new finding |
| GPU / compiled backend | Qualification again for every relevant backend, compiler, flag, or device change | Treating a prior CPU or different-toolchain result as transferable evidence |

## Reporting rule

For a healthy unchanged boundary, report only:

1. what ran or was inspected;
2. `PASS` / `FAIL`;
3. the artifact identity hash, if an artifact was created; and
4. the next owner decision or execution step.

Do not paste long command logs unless there is a failure, a material new
finding, or the owner asks for the detail.

## Non-negotiable limits

- Do not bypass a validation that the reviewed runner itself requires.
- Do not skip the single independent pre-run review for a new multi-hour or
  multi-day runner, nor the single post-run audit for its first artifact.
- Requalification is required whenever a boundary changes, even if that makes
  the work less convenient.
- This protocol does not authorize a Gate-6 pass, GPU-produced scientific
  value, D013, V-14, rates, interpretation, or any later gate.

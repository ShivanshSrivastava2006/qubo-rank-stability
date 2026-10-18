# Gate-9 core result/offset binding — offline design draft

**Status:** Draft for review, not an execution release. The owner retained the
strict pre-write executing-image requirement (Choice A). This design cannot
establish that identity or satisfy amendment §B.1–§B.3. Changing the reviewed
CUDA or bridge sources would change the accepted §A version-1 source identity
and require a new, separately approved qualification before use.

## Existing seam and precise gap

`stage2_cuda_input_frame.py` canonically commits the exact binary64 payload,
ordered coefficient rows and expected full slack-offset SHA-256. The Python
bridge decodes that validated frame into the C ABI, invokes `g9_core_run_v1`,
then calls `g9_core_copy_offsets_v1`; it checks the returned offset bytes against
the frame before returning bounded summaries. Qualification also compares the
bounded results exactly to the Python reference for two synthetic payloads.

That is meaningful serial host-stub and CUDA qualification evidence, not proof
that a hostile host or an unverified binary executed the frame. The returned
`input_frame_sha256` is attached by the host; it is not a device attestation.
More immediately, `run_core` stores the computed offsets and intermediate
arrays in process-global storage, and the offset copy is a **separate ABI
call**. The C wrapper's `g9_last_core_success` is also process-global. Neither
the Python bridge nor the C wrapper enforces the documented non-reentrancy.
`ctypes` can release the GIL during a foreign call. Concurrent invocations in
one process could therefore pair one call's result with another call's offsets
or corrupt shared intermediate arrays. A nonce echoed in `CoreOutput` would
not repair that race or prove that a GPU produced the numbers.

## Minimal implementation sequence

1. **Serialize the existing ABI transaction.** Hold one process-wide Python
   lock across ABI loading/use, `g9_core_run_v1`, `g9_core_copy_offsets_v1` and
   the checks that follow. Add a C-side non-reentrancy guard that refuses a
   second entry to `g9_core_run_v1` while a first call is active, including
   callers that bypass Python. Define when the guard is released and how a
   failed call invalidates offset copying. This is an interim safety measure;
   separate direct C callers can still misuse the v1 two-call protocol unless
   the C export itself enforces a transaction.

2. **Prefer a v2 single-call ABI for durable binding.** Pass caller-owned
   storage for all `STATE_COUNT + 1` offsets into `g9_core_run_v2` alongside
   the bounded `CoreOutput`. Under the same non-reentrant transaction, fill the
   offset storage from the offsets just computed for that invocation and
   return success only after both the bounded output and offsets are ready.
   Do not claim multi-word atomic CUDA writes: the core executes multiple
   kernels/copies and assembles `CoreOutput` on the host. On failure, callers
   discard both output buffers; tests should confirm the existing v1 output
   struct is published only on success. Retire the separate copy export from
   the reviewed consumer path once v2 is qualified. A versioned generation
   token on both v1 calls is an alternative, but must reject intervening runs
   and still enforce non-reentrancy for shared arrays.

3. **Validate a versioned consumer envelope.** The trusted host constructs
   one envelope from the validated input frame, the single-call v2 outputs,
   and the independently calculated offset-table SHA-256. It compares the
   latter with the frame's expected digest, requires exact schema/row count,
   bounded entries, legal flags, minima inclusion, and all zero failure
   counters, and passes only that verified result to D015/D016 reconstruction.
   A consumer also compares the envelope's frame hash against its own
   separately validated expected payload and ordered coefficient rows; it
   must not merely echo the runner's `offsets_sha256`. The envelope may carry
   an operational call ID for logging, but a host-generated ID proves no
   device origin. A result commitment can detect accidental storage or
   transport corruption; it does not replace direct field checks or the
   existing frozen-authority comparisons.

4. **Keep qualification provenance external.** Source, binary, numerical
   compiler flags, GPU/platform and executing-image identity are distinct
   release conditions. Embedding a flags string or hashing bytes from within
   the session cannot prove which flags compiled the running binary or which
   image executes it. This design supplies none of the independent pre-write
   image evidence required by owner Choice A. No change here authorizes a
   Kaggle run or a scientific write.

## Canonical encoding if an envelope digest is added

Reuse the input frame's canonical JSON and SHA-256 rather than hashing C
struct storage. If a binary result commitment is introduced, version and
domain-separate it; serialize each integer as fixed-width little-endian with
an explicitly stated width and each finite binary64 by its exact IEEE-754
word, preserving `+0.0` versus `-0.0`; define field order, lengths and the
number/order of coefficient rows. Never hash padding, change ABI packing, or
describe FNV as a cryptographic substitute for SHA-256. No device-side hash
is needed to fix the present two-call race.

## Offline fail-closed tests before any new qualification

- Two distinct frames with different offset tables, rows and minima: serial
  calls must bind each result to its own offsets. A deterministic injected
  interleaving or second direct C entry must be refused; do not run unsafe
  simultaneous calls against v1 process-global arrays as a test.
- A failed ABI call, including a failure after intermediate arrays were built,
  must not publish an accepted result or allow stale offset copying. A
  result/offset swap between the two valid frames must be rejected by the
  consumer, including when lift totals happen to match.
- Mutate one payload binary64 word, one ordered coefficient word, one offset
  boundary and one compacted entry separately; each must fail the appropriate
  frame/offset/result check. Test `+0.0` versus `-0.0` as bit-distinct words,
  not merely mathematically equal inputs. Check output capacity and malformed
  schema/row-count refusal in normal and `python3 -O` modes.
- Re-run the existing host-emulation and frozen-authority regressions after
  any source edit. These are synthetic evidence only. A new CUDA source/ABI
  release requires fresh independent §A qualification and owner acceptance.

## Limits

This prevents accidental result/offset misassociation under a trusted,
serialized orchestrator. It cannot stop a hostile host from fabricating the
envelope, cannot prove what the GPU executed, and cannot establish an OCI
manifest identity. It makes no privacy claim about arbitrary caller payloads.
The offset table has `2^20 + 1` words; copying/validating it is a full-domain
host operation, not a bounded-size result. The *scientific* returned summaries
remain capped, and the offset table is not a scientific tie or energy stream.

# Gate-9 CUDA image-channel discovery probe — outcome

## One authorized submission
The USER approved exactly one push and one run. One `kernels push` was made,
returned 0, and created **version 1**. No retry occurred and none is authorized.

    /home/shivansh-srivastava/venv/bin/kaggle kernels push \
      -p /tmp/g9-image-channel-probe.bdO3di -t 600 --accelerator NvidiaTeslaT4

Kaggle assigned the slug from the **title**, not from the submitted `id`. The
submitted id `shivanshsrivastava06/g9-cuda-image-channel-probe` is not a valid
ref and returns permission-denied on `kernels status`. The authoritative ref is
`shivanshsrivastava06/g9-cuda-image-channel-discovery-probe`, saved-version
`id_no` 135860813. Status after the run: `KernelWorkerStatus.COMPLETE`. The
probe's stdout event is timestamped t=1.51 s; the kernel finished in about 7 s,
far inside the 600 s cap.

## Result: a candidate channel exists
Verdict `expected_digest_candidate_observed`. Of 95 environment variable names
seen, 8 were excluded as sensitive by name before any value was read, and 3 were
selected:

| Name | Classification |
| --- | --- |
| `KAGGLE_DOCKER_IMAGE` | `expected_manifest_digest` |
| `KAGGLE_CONTAINER_NAME` | `no_digest_shaped_value` |
| `COLAB_IMAGE_TYPE` | `no_digest_shaped_value` |

`KAGGLE_DOCKER_IMAGE` carried a value matching the section-A version-1 **manifest
digest** `sha256:37c64f7d...`. Two GPU device nodes were present.

## Second, independent channel agrees
The kernel was submitted **unpinned** — the submitted metadata contains no
`docker_image` key. The metadata pulled back after the run contains:

    "docker_image": "gcr.io/kaggle-private-byod/python@sha256:37c64f7dd9c54116ecd1bcc88817c5469b88387388fade02bfa8bf3fc647d461"

This is the same digest the in-session environment variable reported, recorded
server-side and bound to the saved version. So the digest is observable both
**in-session before a write** and **post-run against the saved version**, and
the two agreed on this run.

## Negative results, which also matter
- `expected_config_id` count is **0**. The image **config blob id** was not
  observed anywhere — in-session only the manifest digest is available.
- Both procfs hints were read successfully and **neither** `/proc/self/cgroup`
  nor `/proc/self/mountinfo` contained the expected manifest or config hex. The
  environment variable is the only in-session carrier found.

## Preserved evidence (SHA-256)

| File suffix after `GATE_9_CUDA_IMAGE_CHANNEL_PROBE_` | SHA-256 |
| --- | --- |
| `SUBMITTED_METADATA.json` | `5a2e57e37518839a64d17cae711c4855f7dba2a15db54269aa698a057f80ef86` |
| `SUBMITTED_SCRIPT.py.txt` | `e1e1a354b529cfb70e42ed97aa86675f9bc8578037a560f75d10ef2851682d04` |
| `PULLED_SCRIPT.py.txt` | `e1e1a354b529cfb70e42ed97aa86675f9bc8578037a560f75d10ef2851682d04` |
| `PULLED_METADATA.json` | `9cece6ac91d094aedf7f14f1955f01171dee12b0ccded9adef01a68fe74d22e8` |
| `RECEIPT.json` | `4ce4abdf572ca94cea5d383640552d6498e04eb19d7a74f9ae27556e4426a410` |
| `FULL_KERNEL_LOG.json` | `f1311be2e46b5b2b8739fb2ba25acac19a6b62ccde8fe8ef49d36844aae68735` |
| `PUSH_RECEIPT.txt` | `a7321f0d48856bcbca71b809de495aee7d6d7c84caff61ad0a67f5e4c97ac5e9` |

The submitted and pulled script are **byte-identical**, confirming the API round
trip preserves source exactly. The pulled metadata differs from the submitted
metadata only in the fields Kaggle rewrites: `code_file`, `id`, `id_no` and the
added `docker_image`. The receipt's own `content_sha256` seal was recomputed and
**verifies**, and the stdout copy in the full kernel log carries the same seal.

## Limit: §B is NOT established
This is a discovery result, not an identity proof, and it does not move §B.

- **An environment variable is a platform assertion, not a measurement.** The
  probe reads a string the platform placed into the container. Nothing here
  shows that string is derived from the image actually executing, as opposed to
  the image the platform intended or recorded.
- **The two agreeing channels are not independent in the way that matters.** The
  in-session variable and the saved-version metadata may both derive from one
  upstream allocation record. Agreement is consistent with a correct report and
  equally consistent with one common source.
- **No changed-image observation exists.** A single run cannot distinguish a
  channel that tracks the executing image from one that reports a constant. The
  digest observed here happens to equal the section-A version-1 digest, so this
  run contains no instance of the value changing.

## What would be NECESSARY next, which is not the same as sufficient
1. A **changed-image observation**: a later run allocated a different image, in
   which both the in-session variable and the saved-version `docker_image` must
   move to the new digest together. This requires separate owner approval.
2. A **pre-write ordering demonstration**: the digest must be readable and
   checked before the session's first scientific write, which this probe's
   ordering already models but does not bind to any scientific artifact.
3. Resolution of whether the **config blob id** is obtainable in-session at all;
   it was not observed here.

**None of these three would be sufficient on their own, and (1) in particular
must not be mistaken for a proof.** Observing that the platform updates a string
when it allocates a different image demonstrates *consistency*; it does not turn
an assertion into a measurement. A channel that reports what the platform
believes it ran can track perfectly and still be wrong in exactly the case §B
exists to catch.

Closing §B therefore needs something this probe does not contain: an identity
the session **measures from the environment it is actually running in**, rather
than reads from a string handed to it. That reframing, and the experiment that
would test it, are set out in
`GATE_9_CUDA_IMAGE_TRACKING_EXPERIMENT_DESIGN_DRAFT.md`.

Until then, no Stage-2 scientific write may rely on this channel for identity,
and no qualification claim follows from this run.

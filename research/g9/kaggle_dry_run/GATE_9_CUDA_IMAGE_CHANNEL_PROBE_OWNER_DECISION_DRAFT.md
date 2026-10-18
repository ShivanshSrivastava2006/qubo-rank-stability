# Gate-9 CUDA Image Channel Discovery Probe: Owner Decision Draft

## Proposed Action
**Exact proposed one-shot action:**
Push the generated Gate-9 image-channel discovery bundle to Kaggle over the
network as a single unpinned private kernel (`g9-cuda-image-channel-probe`) on
the `shivanshsrivastava06` account, and run it exactly once.

Two things are deliberately separated here:

- **Offline, already done, no approval needed.** The release generator
  (`stage2_cuda_image_channel_probe_release.py`) is read-only and pure. It
  contacts nothing, writes nothing, and emits only a plan document whose
  `status` is `UNAPPROVED_NOT_EXECUTABLE`. It contains no Kaggle, network or
  subprocess call and therefore cannot itself push.
- **Networked, not done, approval required.** The push and the single run are
  the action described by this draft. They are outward-facing and cannot be
  undone once the kernel exists on Kaggle.

One attempt, no retry, no science. The owner is the USER, not the reviewer and not
The lead.

## Evidence Returned
The live probe counts NVIDIA device nodes and classifies selected non-sensitive
environment values, with optional boolean procfs hints. No scientific
artifacts, instance data or model weights are generated or returned.

## Exact Read Whitelist
This is the complete set of things the probe reads in the session. Every read
goes through an injectable reader; there is no directory walk, no subprocess,
no network call, no PID-1 environment file and no credential access.

**Environment variable names** — all of them, via `os.environ.keys()`, capped at
4096 names. Names alone; no value is touched at this stage.

**Environment variable values** — read only for a name that, upper-cased,
contains one of `IMAGE`, `DIGEST`, `CONTAINER` *and* none of `TOKEN`, `SECRET`,
`KEY`, `PASSWORD`, `PASSWD`, `AUTH`, `PROXY`, `CREDENTIAL`, `COOKIE`. The
sensitive-name exclusion is applied to the name **before** any value is read,
and no value reader is reachable from the name-selection function. At most 16
names qualify; each value must be printable ASCII of at most 512 bytes.

**GPU device nodes** — `os.stat()` on the 16 fixed paths `/dev/nvidia0` through
`/dev/nvidia15`, reduced to a count of character devices. No device is opened.

**Procfs hints** — at most `cap + 1` bytes of exactly two fixed files:
`/proc/self/cgroup` (cap 16384) and `/proc/self/mountinfo` (cap 262144). Any
other path raises. Contents are reduced in place to match-only booleans and are
labelled `untrusted_hint_not_proof`.

## Exactly What Leaves the Session
The report is capped at 8192 bytes. Its complete field set is:

- `environment` — the **names** of the selected variables (at most 16) verbatim;
  for each, one enum from a fixed four-value set, **never the value itself**;
  plus `classification_counts`, `names_seen_count`,
  `excluded_sensitive_name_count`, `selected_name_count`;
- `gpu_device_node_count` — an integer;
- `hints` — four booleans over the two hint files (expected manifest/config hex
  present), plus a per-file status, marked `untrusted_hint_not_proof`;
- `expected_image` — the two **already-public** section-A version-1 digests the
  probe compares against, and their source label;
- `internet` — the declared flag and the in-session observation, which is
  `not_observed`, with an explicit basis string saying so;
- `metadata_policy_sha256` — a digest of the fixed expected policy;
- `verdict`, `refusal_reason`, `refused_selected_names`;
- fixed constants: `schema`, `mode`, `probe_version`, `candidate_status`,
  `cross_version_tracking`, `section_B_prewrite_identity`, and
  `scientific_outputs` / `stage2_inputs`, both the literal
  `intentionally absent`;
- `content_sha256` — a seal over the rest of the body.

No raw environment value, URL, hostname or unrecognised hash can appear.

**Two egress channels, not one.** The same report bytes are also written to
**stdout**, so the full report is captured in the Kaggle session log as well as
in the receipt file. The log is readable wherever the session is. This is
acceptable only because the report is scrubbed by construction — but an owner
approving this is approving both channels.

## Execution Bound and Timeout
**No wall-clock timeout is enforced.** The generated launcher runs the probe via
`subprocess.run([...])` with no `timeout=` argument.

The work is instead bounded structurally, and finitely: at most 4096 name reads,
at most 16 value reads of at most 512 bytes each, exactly 16 `stat()` calls, and
two file reads capped at 16 KiB and 256 KiB. There is no unbounded loop, no
retry and no network wait, so the probe is expected to finish in well under a
second. In practice the only ceiling is Kaggle's own session limit, not the
probe's own logic.

**Residual, deferred:** if the owner wants an enforced ceiling rather than a
structural one, adding `timeout=` to the launcher's `subprocess.run` would
change `build_g9_cuda_image_channel_probe_bundle.py` and therefore require
re-pinning its SHA-256 in the release generator's `EXPECTED_PROBE_FILES`. That
is not done here.

## Session Writes
**Under `/kaggle/working`: exactly one new file** — the receipt, or on refusal
the failure log. The probe refuses and writes nothing if either name already
exists, or if the working directory is a symlink or absent. The file is opened
`xb`, so it can never overwrite.

**Written by the platform, not by us:** Kaggle places its own files in the
session, including the executed script and the rendered `__results__.html` that
`nbconvert` produces at the end of every run — the version-1 kernel log records
it writing 300418 bytes. The "exactly one new file" claim above is scoped to
files the **probe** writes; it is not a claim that the working directory is
otherwise empty, and the owner should not read it as one.

**Elsewhere in the session:** the generated launcher decodes its embedded probe
payload and writes it into a `tempfile.TemporaryDirectory`, runs it from there,
and the directory is removed on exit. That temporary copy is a byte-for-byte
copy of the reviewed, hash-pinned probe — the launcher refuses with
`REFUSED: embedded payload hash mismatch` if it is not — but it is a real file
write, and is disclosed here for completeness.

**On the local machine, before any push:** the bundle builder
(`build_g9_cuda_image_channel_probe_bundle.py`) writes `kernel-metadata.json`
and the launcher into an explicitly supplied, existing, empty, absolute
`--output-dir`. This is a local build step with no network access. It is the
release *generator* — a separate file — that writes nothing at all and only
emits the plan.

## Privacy Limits
- **Metadata**: requests private / T4 / internet-off / no input sources /
  unpinned. The release plan reports this posture by **reading it out of the
  validated bundle metadata**, not by restating literals.
- **Network**: internet access is explicitly disabled in the request.
- **Data**: no dataset, competition, kernel or model sources are requested.
- **Hardware**: `NvidiaTeslaT4` allocation is requested.
- **Visibility**: the kernel remains private.
- **Image pinning**: unpinned; whatever image Kaggle allocates at run time is
  the one observed — which is the point of the probe.

Note the limit of the metadata guarantee: these are properties of the **request**
that is pushed. A declared `enable_internet: false` is not an in-session
observation, and the probe states this in its own report as
`declared_by_reviewed_metadata_policy_not_observed_in_session`.

## Limitations and §B Non-Proof
- **Not §B proof.** A digest match is a hypothesis about a candidate channel,
  nothing more. §B requires a session to prove its own executing-image digest
  **before** its first scientific write; this probe does not establish that and
  cannot substitute for it.
- **Not testable in one run.** A single run cannot show that a candidate channel
  tracks the actual image across versions. Post-run saved-version
  execution-image binding and a separate changed-image observation are both
  still needed.
- **No science.** Strictly infrastructure discovery. No instance, candidate,
  ground truth, coefficient ledger or scientific record is read or written.

## Approval Requirement
A distinct owner decision from the USER is **required** before the generated
bundle can be pushed or run on Kaggle. The release mechanism enforces an
explicit `UNAPPROVED_NOT_EXECUTABLE` status and cannot perform the push itself.
Approving this draft authorises exactly one push and one run — no retry, no
science, and no Stage-2 qualification claim.

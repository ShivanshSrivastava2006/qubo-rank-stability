# Gate-9 image-tracking discrimination experiment — design draft

OFFLINE DESIGN ONLY. Nothing here is approved, built, or pushed. No owner
decision is requested by this document; it exists to be reviewed first.

## The problem this has to solve

Version 1 of the image-channel probe observed `KAGGLE_DOCKER_IMAGE` carrying the
section-A version-1 manifest digest, corroborated by the saved version's
`docker_image`. That single observation is consistent with **three** mutually
exclusive hypotheses, and distinguishing them is the whole task:

- **H0 CONSTANT** — the variable reports a fixed string regardless of which image
  actually runs.
- **H1 ECHO** — it reports the image the *submission requested*, regardless of
  what actually runs.
- **H2 TRACKING** — it reports the digest of the image actually executing.

Only H2 is of any use to §B. Run 1 cannot separate them: it was unpinned, and
the allocated image happened to equal the expected digest, so nothing moved and
nothing was requested.

## Why the obvious experiment is not enough

The obvious next move is to pin a different image digest and see whether the
variable follows. It does not settle the question. When a pin is honoured, "the
image we asked for" and "the image that ran" are the same string, so H1 and H2
predict **identical** observations. A pinned run can kill H0. It cannot kill H1.

The asymmetry that matters: **an unpinned submission contains nothing to echo.**
If the digest changes across two unpinned runs, no request could have produced
that change. That makes the unpinned arm the only one capable of killing H1 —
and it depends on Kaggle rolling its default image, which is not under our
control and may take weeks.

## The missing measurement

Version 1 has a deeper gap than the hypothesis ambiguity: it never measured the
environment itself. It compared one platform-supplied string against another
platform-supplied string. Both could be wrong together.

The experiment therefore needs an **intrinsic image fingerprint**: a value the
session computes by reading the filesystem it is actually running on, with no
platform assertion involved. Proposed construction, standard library only,
bounded, no directory walk:

- `sys.version`, and the `ID` / `VERSION_ID` fields of `/etc/os-release`;
- a content hash of `/etc/os-release` and `/etc/debian_version`;
- over a **fixed whitelist** of about sixteen paths under `/usr` and `/etc`, the
  canonical tuple `(path, st_size, st_mtime_ns, st_mode)`;
- `importlib.metadata.version` for a fixed list of distribution names;
- all of it canonicalised and reduced to one SHA-256.

Deliberately excluded, because they are host state or session state rather than
image content: `/proc`, `/sys`, `/dev`, `/kaggle`, `/tmp`, `/var/run`, and
anything writable by the running session.

## Three arms, in dependency order

**Arm 0 — fingerprint stability. Prerequisite; nothing else is interpretable
without it.** Two unpinned runs, back to back, expected to land on the same
image. The fingerprints **must be identical**. If they are not — because of
overlay writes, mtime drift, or a bind-mounted path that slipped into the
whitelist — the fingerprint is not an identity and the design fails here and
must be revised rather than continued. Two pushes.

**Arm 1 — pinned change.** Pin a digest deliberately different from D0. Kills H0
if the digest and the fingerprint both move together. Does **not** kill H1. One
push.

**Arm 2 — natural rollover.** Unpinned, run after Kaggle's default image
changes. If the digest and the fingerprint move together with nothing requested,
H1 is dead and H2 is supported. This is the arm that actually settles it, and it
requires waiting. One push.

Four pushes total. Each needs its own owner decision; none is being requested
now.

## The reframing this suggests for §B

The fingerprint was introduced above as a control. It may be the better §B
primitive outright.

§B asks a session to prove its own executing image before its first scientific
write. A digest string handed to the session by the platform is an **assertion**:
believing it means trusting the platform's report about itself. A fingerprint the
session computes from the filesystem it is running on is **evidence about the
thing itself**, and depends on nothing but the session's own reads.

That gives three possible §B checks, in increasing strength:

1. `KAGGLE_DOCKER_IMAGE == accepted digest` — trusts the platform entirely.
2. `measured_fingerprint == owner-accepted fingerprint` — trusts only the
   session's own reads.
3. Both, and they must agree — catches the case where the platform's label and
   the delivered filesystem disagree.

Under this framing the digest becomes a convenient **label**, and the
fingerprint becomes the **identity**. If Arm 0 shows the fingerprint is stable,
option 2 is available for §B **without** waiting for Arm 2, because it does not
depend on the digest tracking anything at all.

## What this design still cannot do

It cannot detect a platform that reports a correct digest and a correct
fingerprint while executing different code — a fingerprint covers the paths in
its whitelist and nothing else. It cannot establish that the accepted reference
fingerprint corresponds to the intended public image, which is a separate
owner-side provenance question. And it says nothing about the binding between a
verified identity and a particular scientific write; that remains the open
integration requirement identified in the reconstruct review, where the offset
digest binds the offset table only.

## Next action

Review this design before anything is built. The specific claim to attack is the
Arm 0 / Arm 2 dependency argument: if a cheaper experiment can kill H1, this
design is more expensive than it needs to be.

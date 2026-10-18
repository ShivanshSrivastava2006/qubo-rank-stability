# Push-review summary — <PACKAGE NAME> (template)

*One page for the person who will type the push command. Fill every field; leave nothing implied.*

| Field | Value |
|---|---|
| Package | `<name, e.g. WP7 non-scientific dry run / Stage-2 instance stage2_0N>` |
| Kind | **SYNTHETIC / non-scientific** or **SCIENTIFIC (writes Stage-2 records)** |
| Owner approval | `<approval record path>` at SHA-256 `<…>`, dated `<…>` |
| Package manifest | `<path>` SHA-256 `<…>` (verify with the command below before pushing) |
| Reviewed-dependencies anchor | SHA-256 `<…>` (from the owner's approval, never from the package) |
| Account | `<kaggle username of the person pushing>` |
| Expected GPU / image | T4, CC 7.5, pinned environment `<…>` — a different reported environment stops the session before any write |
| Expected GPU time | `<hours>` of the account's weekly quota |
| What it computes | `<2–4 plain sentences>` |
| What it writes | `<exact outputs; for synthetic runs: counters, identities and digests only>` |
| What it must NOT do | no other files, no network beyond Kaggle's own, no credential use |

## Before pushing (the account owner runs these)

1. Verify the manifest: `<exact verify command>` → must print `draft_ready_for_owner_review` (or the approved final status) and the SHA-256 above.
2. Create a temporary Kaggle config directory for this shell only, log in there, and confirm `KAGGLE_CONFIG_DIR` points to it.
3. Push: `<exact push command>`.
4. Delete the temporary config directory. Tell the owner the kernel slug and version number.

## After the run (The lead does this)

- Pull the executed version; verify its script byte-for-byte against the manifest.
- Check the receipt: complete, identity matched the pin, no refusal.
- Record the account, kernel version and receipt hash as provenance.

*A mismatch at any step voids the session's records; nothing is repaired after the fact.*

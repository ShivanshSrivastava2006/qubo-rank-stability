# Gate-9 §A version-1 execution-image attestation (read-only observation)

Observed: 2026-09-25 IST, in an owner-authenticated browser session on the
private saved notebook's Logs page. This is a **sanitized transcription** of
Kaggle's HTTPS JSON responses, not a cryptographic signature by Kaggle. The
two raw response bodies were preserved separately in an owner-only directory
(mode 700, files mode 600), rather than placed in this project: they contain
worker addresses, download URLs, and incidental page/account fields. No
request headers, cookies, or authentication tokens were inspected or
retained. Only the version/run/image/output fields were examined. No
notebook was edited, pushed, saved, or executed during this observation.

Notebook:
`https://www.kaggle.com/code/shivanshsrivastava06/g9-cuda-core-a-corruption-qualification-585da5d8/log`

Private raw evidence (not to publish):
`/home/shivansh-srivastava/.local/share/decisions_os/g9_kaggle_version1_attestation/`

| Raw response body | Bytes | SHA-256 |
| --- | ---: | --- |
| `ListKernelVersions.raw.json` | 4,225 | `121d2d927f51e49cd74d7f4dce5eb29b7f2fc964605b86963120e557c1aa71b9` |
| `GetKernelViewModel.raw.json` | 7,499 | `b0489f93edddf3aaecda366461a57a8c855d845bbd9159ff7afa5d5763bda7e3` |

Both requests returned HTTP 200. `ListKernelVersions` was requested with
`kernelId=135769337`; `GetKernelViewModel` was requested for this notebook's
Logs tab with `kernelVersionId=0`. These request parameters and HTTP status
were observed in the browser; only the response bodies, not request metadata
or headers, are byte-preserved. An independent read-only reviewer parsed the
raw bodies and recomputed their hashes and the public image hashes.

## Explicit version-to-run-to-image record

Kaggle's `KernelsService/ListKernelVersions` response has only the top-level
key `items` (no pagination token) and returned exactly one version item:

| Response path | Observed value |
| --- | --- |
| `items[0].version.versionNumber` | `1` |
| `items[0].version.id` | `213905783` |
| `items[0].run.kernelId` | `135769337` |
| `items[0].run.id` | `352588357` |
| `items[0].run.status` | `COMPLETE` |
| `items[0].run.runInfo.succeeded` | `true` |
| `items[0].run.dateEvaluated` | `2026-09-25T05:24:58.817Z` |
| `items[0].run.runInfo.dockerImageDigest` | `37c64f7dd9c54116ecd1bcc88817c5469b88387388fade02bfa8bf3fc647d461` |
| `items[0].run.runInfo.dockerImageId` | `sha256:c72831376c5485ec652a6f4a771bf091ae0726310e1b9db3db064387e173e941` |
| `items[0].run.runInfo.dockerImageName` | `gcr.io/kaggle-gpu-images/python` |

An independent `LegacyKernelsService/GetKernelViewModel` browser response
(HTTP 200) for the same notebook's Logs tab reported
`currentVersionNumber=1`, `totalVersionCount=1`,
`kernelRun.kernelVersionNumber=1`,
`kernelRun.kernelId=135769337`, `kernelRun.id=352588357`,
`kernelRun.status=COMPLETE`, the same image digest, image ID, image name,
success value, and evaluation timestamp. Its output listing associated
`g9_cuda_core_a_corruption_qualification_receipt.json` with
`kernelSessionId=352588357` and `contentLength=5734`. The requested
`kernelVersionId=0` means this
second endpoint addressed the current version; the explicit version-1 item
from `ListKernelVersions` is the primary version-bound evidence.

## Local content-addressed cross-check

The preserved `GATE_9_KAGGLE_CORE_A_VERSION1_PUBLIC_IMAGE_MANIFEST.json`
hashes to
`37c64f7dd9c54116ecd1bcc88817c5469b88387388fade02bfa8bf3fc647d461`,
identical to `items[0].run.runInfo.dockerImageDigest`.
The preserved `GATE_9_KAGGLE_CORE_A_VERSION1_PUBLIC_IMAGE_CONFIG.json`
hashes to
`c72831376c5485ec652a6f4a771bf091ae0726310e1b9db3db064387e173e941`,
identical to the digest component of `items[0].run.runInfo.dockerImageId`.
The preserved version-numbered output receipt hashes to
`e6f18e4a9b198b1e8dfd61a09e79588f1ca0c7e425cd62ee7388500731ee0217`.

Unlike the generic "Latest Container Image" link, the first Kaggle response
places the digest **inside saved version 1's completed run record**. This
closes the predeclared image-to-executed-version evidence gap under its
"otherwise version-bound source of truth" clause, subject to the owner's
explicit acceptance. The platform record is Kaggle's unsigned assertion,
not an in-run digest measurement. Its `dockerImageName` says
`kaggle-gpu-images/python`, while the pulled metadata and the worker result
also name `kaggle-private-byod/python`; their manifest digest and image ID
match, so the binding uses content identities rather than repository names.
The receipt itself continues to say
`not_satisfied_pending_post_run_audit_and_owner_acceptance`; this document
does not alter those historical bytes, declare a qualification identity, or
authorize another GPU run or scientific work.

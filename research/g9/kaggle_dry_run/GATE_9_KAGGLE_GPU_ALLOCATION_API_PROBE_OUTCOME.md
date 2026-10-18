# Gate-9 non-scientific Kaggle GPU-allocation API probe — outcome

Date: 2026-09-24 IST. Release: `GATE_9_KAGGLE_GPU_ALLOCATION_API_PROBE_DRAFT.md`
SHA-256 `c29f1781d23c35faa3377cb500931198d14f40e0271ad64f749fc26b4fedb930`.
The owner explicitly approved replacing the unused owner-run UI probe with exactly
one automated API push. This record concerns that one diagnostic version only.

## Attempt and status

- Pre-push gate passed: all five pinned hashes, exactly two staged files, approved
  metadata without `docker_image`, CLI flags, authenticated own-kernel inventory,
  and absence of the new slug.
- The lead invoked once, with no retry:
  `/home/shivansh-srivastava/venv/bin/kaggle kernels push -p /tmp/g9-api-probe.VB4IDV --accelerator NvidiaTeslaT4 -t 600`
- Push return code: `0`; stderr: empty. Exact stdout:
  `Kernel version 1 successfully pushed.  Please check progress at https://www.kaggle.com/code/shivanshsrivastava06/g9-gpu-allocation-api-probe-v1`
- Read-only status: `KernelWorkerStatus.COMPLETE`, return code `0`.
- Versioned read-only output retrieval using suffix `/1` succeeded; its raw log
  contains `probe_conditions_met: true` and no `GATE9_PROBE_NOT_CLEAN` raise.
- Versioned read-only source pull using suffix `/1` returned HTTP 403. The lead then
  pulled the same slug without a version suffix (read-only), which succeeded. The
  reason for the 403 is unknown. The pulled source is therefore the current kernel
  source, not a version-1-specific API source response; the output is versioned.

## Source and runtime evidence

The pulled current source is a script `.py` whose **raw bytes** hash to the pinned
script SHA-256 `b0aa74f3ff1710e9eecae40cc077c031ea39689da433672ede4fc22c29841bff`.
This is approved source-identity shape (a), with no marker removal or newline
normalization. Pulled metadata identifies
`shivanshsrivastava06/g9-gpu-allocation-api-probe-v1`, `kernel_type=script`,
`is_private=true`, `enable_gpu=true`, `enable_tpu=false`,
`enable_internet=false`, `machine_shape=NvidiaTeslaT4`, and empty source arrays.
Kaggle's pulled metadata contains `docker_image` of
`gcr.io/kaggle-private-byod/python@sha256:37c64f7dd9c54116ecd1bcc88817c5469b88387388fade02bfa8bf3fc647d461`.
Submitted metadata omitted this key; the pulled value is an after-the-fact
observation, not evidence of a chosen environment-pinning setting.

The version-1 log's typed JSON reports `gpu_allocation=PASS`, two Tesla T4 devices,
two NVIDIA device nodes, `nvidia_smi` return code 0, `cuda_compiler=PRESENT`,
`cuda_compiler_usable=USABLE`, and `launcher_guard_cuda_home=SATISFIED`.
`CUDA_HOME=/usr/local/cuda`, and `/usr/local/cuda/bin/nvcc --version` returned 0,
reporting CUDA compilation tools 12.8, V12.8.93. It explicitly reports
`compilation_performed=false` and `authorizes="nothing"`. Only Kaggle-side
`mistune`/`nbconvert` warnings follow on stderr; none changes the typed result.

## Preserved evidence (SHA-256)

| File suffix after `GATE_9_KAGGLE_GPU_ALLOCATION_API_PROBE_` | SHA-256 |
| --- | --- |
| `SUBMITTED_SCRIPT.py.txt` | `b0aa74f3ff1710e9eecae40cc077c031ea39689da433672ede4fc22c29841bff` |
| `SUBMITTED_METADATA.json` | `18185f633e3072488d5d69739cbc783ddfb86eab39740d702f65a040ab084844` |
| `PULLED_SCRIPT.py.txt` | `b0aa74f3ff1710e9eecae40cc077c031ea39689da433672ede4fc22c29841bff` |
| `PULLED_METADATA.json` | `6b4824ead7b49e42f26260c84a1527c7980c82bcd0ac61f467d57bcfd7dae9a4` |
| `FULL_KERNEL_LOG.json` | `5de6f686b87d7888ae33f227e2baf9e54e395fa0627ff048b90c7a0a614ab984` |
| `PRINTED_JSON.json` | `a515af2b4da3b06b825f33aff11aba73b6ff582aa00f6387f1186d81ab6faef3` |
| `PUSH_RECEIPT.txt` | `cd3e18d609ce021692c241b6987e6673afa487292ae0e55510606f5174ed1a55` |

The standalone printed JSON was checked for semantic equality against the stdout
events in the full kernel log. The full log preserves Kaggle's event stream verbatim.
No failure log was produced because this diagnostic completed cleanly.

## Limit

This proves GPU visibility and `nvcc --version` usability in this one private,
non-scientific Kaggle run. It neither compiles the CUDA engine nor establishes
numerical correctness or §A qualification. The API path did not expose the UI's
"Always use latest environment" pre-commit control. The one push is spent;
no retry, §A, Stage-2 work, scientific computation, or Gate-10 is authorized by
this outcome. Any next run requires a separately reviewed plan and owner release.

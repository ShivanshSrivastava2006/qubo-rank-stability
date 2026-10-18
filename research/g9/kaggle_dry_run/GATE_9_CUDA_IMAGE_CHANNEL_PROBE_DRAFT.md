# Gate-9 non-scientific image-channel discovery probe draft

This is only a non-scientific discovery design. It is not §B proof or approval to push or run a Kaggle notebook. A separately reviewed, one-attempt owner approval is required before any Kaggle push or GPU run. Offline building and testing do not spend that attempt.

The offline builder produces an exact bundle consisting of two files:
- `kernel-metadata.json`: Contains the exact policy, including `is_private: true`, `enable_internet: false`, T4 GPU, no input sources and no image pin.
- `g9_cuda_image_channel_probe_kaggle.py`: The generated launcher script that embeds the base64-encoded probe payload and hash-checks it before execution.

Receipt semantics:
If separately approved and executed in a Kaggle session, the probe writes one file under `/kaggle/working`: `g9_cuda_image_channel_probe_receipt.json` on a non-refusal verdict, or `g9_cuda_image_channel_probe_failure.log` on a detected refusal. The receipt contains only selected variable names, bounded counts, digest classifications and fixed metadata; sensitive variable names are excluded *before* their values are read. No raw variable value, unfamiliar digest, URL, hostname, Stage-2 input or scientific output belongs in either artifact. A receipt is not a successful image-identity qualification.

Any candidate match must be compared after the run with the saved version's execution-image manifest/config identities. A second, separately approved run on a demonstrably different image would be needed to test whether that channel tracks the executing image, rather than merely echoing a static value. Even those observations would need independent review before revisiting the pre-write rule. A single match cannot confirm §B or authorize scientific writes.

Static expected metadata is offline builder-validated, not observed at runtime.
Internet-off is a metadata declaration, not an in-session measurement.
The fixtures do not run the generated launcher against `/kaggle/working`; they exercise its payload-hash refusal guard and the probe's injected-reader path in a temporary directory. No Kaggle API, GPU or CUDA execution is claimed.

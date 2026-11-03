# Models

The acoustic model is not stored in this repository: GitHub rejects files larger
than 100 MB, and the released one is 274 MiB. Two different files are involved, and
they are easy to confuse, so both are listed here with their hashes.

## The model the release ships

- file: `models/t-one/model.onnx`
- size: 287 475 849 bytes (274 MiB)
- SHA-256: `4a3827b04ef683fe0cffbb47161dd146aa19f8db503902e0ba2de5529d82249e`
- origin: the sherpa-onnx ONNX export of the official T-one weights
  (`csukuangfj/sherpa-onnx-streaming-t-one-russian-2025-09-08`, 3028 nodes, 549
  initializers, 379 of them stored as FP16), widened to FP32 by this project, so the
  bundled file is modified. Weights: `t-tech/T-one` on Hugging Face, Apache 2.0,
  Copyright 2025 T-Software DC. The chain is written out in `THIRD-PARTY-NOTICES.md`,
  and `tools/verify_model_origin.py` reproduces the comparison

This is the file `tools/build.py` copies into the application. It is chosen over the
mixed-precision upstream file because the measurements on three real recordings showed the
same text as fp16 with a lower memory peak (463 MB against 560 MB), a faster load
(2.0 s against 2.8 s) and a slightly lower time per 300 ms chunk (19.9 ms against
20.2 ms). int8 was rejected: 8 % word divergence on a support call, 31 % on a long
call, about 1.5x slower, and words were lost.

Verify it after a copy:

```powershell
certutil -hashfile models\t-one\model.onnx SHA256
```

## The upstream reference model

`python tools/fetch_model.py` downloads the file published by the sherpa-onnx
project (`csukuangfj/sherpa-onnx-streaming-t-one-russian-2025-09-08` on Hugging
Face):

- size: 144 193 702 bytes
- SHA-256: `5ded080e2a6c86ecc11bcb0902d77524eb3e8b0844cb0c0754347f5aafb4dabc`

The download is verified against that hash. This file is smaller and useful for
tests and for a quick look at the model, but it is a different, mixed-precision file (379 of its
549 initializers are FP16, the release one is FP32 throughout): it is not what the
release archive contains and it does not produce byte-identical output.

## tokens.txt

Both variants share the same vocabulary: 202 bytes, SHA-256
`27f7b3ba2096c572375fba1a6b29af1f80d86e08a329940612908112695f97e0`.

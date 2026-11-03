# Third-party notices

Live Captions RU is distributed under the Apache License 2.0 (see `LICENSE`).
It bundles or depends on the components below. Every license text named here is in
`licenses/`, so nothing is promised that is not on disk.

The versions are the ones the 1.0.0 installers were built with.

| Component | Version | License | Copyright | Text |
|---|---|---|---|---|
| Python runtime | 3.12.9 | PSF License 2.0 | Python Software Foundation | `licenses/Python-LICENSE.txt` |
| PySide6 / shiboken6 / Qt | 6.12.0 | LGPL 3.0 | The Qt Company | `licenses/LGPL-3.0.txt` |
| ONNX Runtime | 1.31.0 | MIT | Microsoft Corporation | `licenses/ONNXRuntime-LICENSE.txt`, third-party notices in `licenses/ONNXRuntime-ThirdPartyNotices.txt` |
| NumPy | 2.5.4 | BSD 3-Clause | NumPy developers | `licenses/NumPy-LICENSE.txt` |
| SoundCard | 0.4.6 | BSD 3-Clause | SoundCard developers | `licenses/SoundCard-LICENSE.txt` |
| tqdm | 4.70.1 | MPL 2.0 AND MIT | tqdm developers | `licenses/tqdm-LICENSE.txt` |
| OpenSSL (`libcrypto-3.dll`, `libssl-3.dll`) | 3.x | Apache 2.0 | The OpenSSL Project | `licenses/OpenSSL-LICENSE.txt` |
| libffi (`libffi-8.dll`) | 3.4+ | MIT | Anthony Green, Red Hat and others | `licenses/libffi-LICENSE.txt` |
| Microsoft Visual C++ runtime (`msvcp140*.dll`, `vcruntime140*.dll`) | 14.x | Microsoft Visual Studio redistributable terms | Microsoft Corporation | not reproduced: the runtime is redistributed unmodified under the terms that ship with Visual Studio |
| Roboto (bundled fonts) | Regular, Medium, Bold | Apache 2.0 | Google LLC | `licenses/Roboto-LICENSE.txt` |
| T-one acoustic model (bundled) | 2025-09-08 export, fp32 variant | Apache 2.0 | T-Bank / T-Software DC | `licenses/T-one-LICENSE` |
| PyInstaller (build only) | 6.22.3 | GPL 2.0 with bootloader exception | PyInstaller developers | not redistributed: it only produces the build |

The license texts were taken from the upstream projects and from the installed
packages of the build environment, so they match the code that is actually shipped.

## What this means for the app

**Qt / PySide6 (LGPL 3.0).** Qt is used as a shared library and is not modified.
The application ships as a normal folder with the Qt DLLs next to the executable, so
anyone can replace those DLLs with their own build of the same version; this satisfies
the LGPL relinking requirement. The full LGPL text is in `licenses/LGPL-3.0.txt`, and
the Qt sources are available from https://download.qt.io/official_releases/qt/ under
the same version. Qt itself bundles further third-party components whose notices ship
with the Qt source tree.

**Third-party code inside Qt (BSD, MIT, zlib, IJG, FTL).** The Qt DLLs are not only Qt:
Qt statically links several third-party libraries, and the software OpenGL fallback
(`opengl32sw.dll`, Mesa llvmpipe) ships next to them. Their notices are reproduced in
`licenses/qt-thirdparty/`: zlib, libpng, PCRE2, double-conversion, TinyCBOR, md4c,
HarfBuzz, FreeType, libjpeg-turbo and Mesa.

**tqdm (MPL 2.0).** tqdm ships in compiled form inside the bundle and is not modified.
Its source code is at https://github.com/tqdm/tqdm, which is the Source Code Form the
MPL 2.0 asks to point to.

**T-one model (Apache 2.0).** The bundled file is a modified copy, not the upstream
artifact. The chain, each step checkable:

1. Weights: `voicekit-team/T-one`, published on Hugging Face as `t-tech/T-one` under
   Apache 2.0, Copyright 2025 T-Software DC.
2. ONNX export: `csukuangfj/sherpa-onnx-streaming-t-one-russian-2025-09-08` on Hugging
   Face, whose `model.onnx` is 144 193 702 bytes with 3028 nodes and 549 initializers,
   of which 379 are stored as FP16. The repository describes itself as the scripts
   that export `voicekit-team/T-one` to sherpa-onnx and carries the same Apache 2.0
   license.
3. Our change: those 379 FP16 initializers were widened to FP32. Node order, tensor
   names and the graph are identical; only the stored precision differs. The result
   is 287 475 849 bytes.

The FP32 variant is what ships, because measurements on three real recordings gave the
same text as FP16 with a lower memory peak. To reproduce the comparison, run
`tools/verify_model_origin.py` over a copy of both files; sizes and SHA-256 are in
`models/README.md`.

**Roboto (Apache 2.0).** Font files are bundled unchanged. License text in
`licenses/Roboto-LICENSE.txt`.

**Trademarks.** T-Bank, T-one, Qt, Microsoft and Windows are trademarks of their
respective owners. They are named here only to describe origin and compatibility.
This project is not affiliated with or endorsed by any of them.

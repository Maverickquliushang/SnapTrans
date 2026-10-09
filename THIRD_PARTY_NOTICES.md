# Third-party components

SnapTrans application code is MIT licensed. Dependencies and model assets retain their own licenses. Full available license texts and package metadata are collected in `licenses/`; model provenance and hashes are in `assets/ocr/manifest.json` (under `_internal` in the portable package).

| Component | License / source |
| --- | --- |
| Python | PSF license; https://www.python.org/downloads/source/ |
| PySide6, Shiboken6, Qt Widgets/Core/Gui | LGPLv3/GPL/commercial alternatives; this distribution uses the community libraries dynamically; https://code.qt.io/cgit/pyside/pyside-setup.git/ and https://code.qt.io/cgit/qt/ |
| RapidOCR | Apache-2.0; https://github.com/RapidAI/RapidOCR |
| PaddleOCR-derived ONNX models | Apache-2.0 model distribution; https://huggingface.co/RapidAI/RapidOCR and https://github.com/PaddlePaddle/PaddleOCR |
| ONNX Runtime | MIT; https://github.com/microsoft/onnxruntime |
| OpenCV | Apache-2.0 plus bundled notices; https://github.com/opencv/opencv-python |
| NumPy | BSD-3-Clause plus bundled notices; https://github.com/numpy/numpy |
| Pillow | HPND and bundled component licenses; https://github.com/python-pillow/Pillow |
| httpx, httpcore, anyio | Their upstream licenses, included in collected metadata |
| pywin32 | PSF-derived license; https://github.com/mhammond/pywin32 |
| OmegaConf, ANTLR runtime, shapely, pyclipper | Upstream notices included in licenses |
| PyInstaller | GPL with application-distribution exception; https://pyinstaller.org/ |
| NSIS installer | zlib/libpng with compression-module notices; exact COPYING in licenses/NSIS-COPYING.txt; https://nsis.sourceforge.io/Docs/ |
| Qt WebEngine / Chromium | Qt WebEngine community dynamic libraries and Chromium third-party notices; https://doc.qt.io/qt-6/qtwebengine-licensing.html; matching PySide6 / Qt versions in build-info.json |
| Lobe Icons brand artwork | MIT; https://github.com/lobehub/lobe-icons; pinned source revision, individual URLs and hashes in assets/providers/sources.json; license text alongside SVGs |
| Brand-owned website icons | MyMemory, Youdao, LibreTranslate and Tencent public website favicons; source URLs / hashes in assets/providers/sources.json. Brand names and marks belong to their respective owners; identification does not imply endorsement. |

The dynamic Qt libraries in `_internal/PySide6` are not modified by SnapTrans. The application source and build scripts are supplied alongside this project so users can rebuild with compatible replacement libraries. Qt module selection and binary redistribution must retain the applicable notices. This document does not relicense dependencies under MIT.

The locally built ANTLR wheel is unmodified upstream source; its build provenance is documented in `vendor/README.md`. Runtime dependencies and exact versions are recorded in `requirements.lock` and release `build-info.json`.

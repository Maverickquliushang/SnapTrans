# Vendor dependency

`wheels/antlr4_python3_runtime-4.9.3-py3-none-any.whl` is built without source changes from the official PyPI 4.9.3 source archive by `scripts/prepare_legacy_dep.py` (the archive SHA-256 is verified against PyPI metadata). It avoids legacy setuptools build failures under deeply nested Windows paths. The wheel is a pure Python dependency of OmegaConf, not SnapTrans application logic.

Source: https://pypi.org/project/antlr4-python3-runtime/4.9.3/

Rebuild under the project environment with `python scripts/prepare_legacy_dep.py`. The lock files record the shipped wheel hash. A rebuild can change ZIP timestamps; explicitly regenerate locks when replacing this vendor file. See third-party notices for upstream licensing.

from pathlib import Path
import os
import sys
import tempfile


def resource_root() -> Path:
    return Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))


def app_root() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def storage_root() -> Path:
    """All application-owned state follows the executable, in either distribution."""
    return app_root() / 'data'


def initialize_storage() -> Path:
    root = storage_root()
    for directory in (root, root / 'logs', root / 'tmp'):
        directory.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryFile(dir=root) as probe:
        probe.write(b'write-check')
    for key in ('TEMP', 'TMP', 'TMPDIR'):
        os.environ[key] = str(root / 'tmp')
    tempfile.tempdir = str(root / 'tmp')
    os.environ['MPLCONFIGDIR'] = str(root / 'tmp' / 'matplotlib')
    os.environ['XDG_CACHE_HOME'] = str(root / 'cache')
    return root

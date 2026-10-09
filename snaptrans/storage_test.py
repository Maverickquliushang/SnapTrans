"""Check the real EXE's data routing using synthetic files only."""
import json
import os
from pathlib import Path
import tempfile

from .paths import app_root, initialize_storage


def run(report_path=None):
    try:
        root = initialize_storage()
        assert root == app_root() / 'data'
        with tempfile.TemporaryFile() as probe:
            probe.write(b'SnapTrans local storage test')
        for key in ('TEMP', 'TMP', 'TMPDIR', 'MPLCONFIGDIR', 'XDG_CACHE_HOME'):
            assert Path(os.environ[key]).is_relative_to(root)
        result = {'ok': True, 'data': str(root), 'temporary_files_follow_executable': True,
                  'installed_marker': (app_root() / 'install-mode.ini').is_file()}
    except Exception as error:
        result = {'ok': False, 'error': type(error).__name__}
    if report_path:
        Path(report_path).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if result['ok'] else 1

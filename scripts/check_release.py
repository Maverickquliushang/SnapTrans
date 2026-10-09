import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from snaptrans.core.ocr_adapter import verify_models


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory')
    args = parser.parse_args()
    root = Path(args.directory)
    required = ['SnapTrans.exe', 'README.md', 'LICENSE', 'THIRD_PARTY_NOTICES.md', 'build-info.json',
                'licenses/third-party-licenses.zip', 'docs/release-validation.md',
                '_internal/assets/icon.ico', '_internal/PySide6/plugins/platforms/qwindows.dll',
                '_internal/assets/providers/sources.json',
                '_internal/PySide6/QtWebEngineProcess.exe',
                '_internal/assets/ocr/licenses/PaddleOCR-LICENSE',
                '_internal/assets/ocr/licenses/RapidOCR-LICENSE']
    missing = [name for name in required if not (root / name).is_file()]
    if missing:
        raise RuntimeError('Missing release files: ' + ', '.join(missing))
    verify_models(root / '_internal' / 'assets' / 'ocr')
    for path in root.rglob('*'):
        relative = path.relative_to(root)
        # App state lives only at the release root. Libraries such as OpenCV
        # legitimately ship their own _internal/<package>/data resources.
        if (relative.parts[0] == 'data'
                or any(part in ('.venv', '.tmp', '.cache', '__pycache__') for part in relative.parts)):
            raise RuntimeError(f'Forbidden release content: {relative}')
        if path.name in ('credentials.json', 'app.log'):
            raise RuntimeError(f'Private runtime file in package: {relative}')
    print(json.dumps({'release_check': 'passed', 'files': sum(p.is_file() for p in root.rglob('*'))}))


if __name__ == '__main__':
    main()

import hashlib
import argparse
import importlib.metadata as metadata
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from snaptrans import __version__
STAGING = ROOT / 'output' / f'v{__version__}' / 'SnapTrans'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--stage-only', action='store_true')
    args = parser.parse_args()
    for name in ('README.md', 'LICENSE', 'THIRD_PARTY_NOTICES.md'):
        shutil.copyfile(ROOT / name, STAGING / name)
    from public_files import documentation
    for path in documentation(ROOT):
        destination = STAGING / path.relative_to(ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, destination)
    (STAGING / 'licenses').mkdir(exist_ok=True)
    shutil.copyfile(ROOT / '.tmp' / 'third-party-licenses.zip', STAGING / 'licenses' / 'third-party-licenses.zip')
    nsis_notice = ROOT / 'licenses' / 'NSIS-COPYING.txt'
    if nsis_notice.exists():
        shutil.copyfile(nsis_notice, STAGING / 'licenses' / nsis_notice.name)
    info = {'version': __version__, 'built_at_utc': datetime.now(timezone.utc).isoformat(),
            'python': platform.python_version(), 'windows': platform.platform(),
            'packages': {d.metadata['Name']: d.version for d in metadata.distributions()},
            'requirements_sha256': hashlib.sha256((ROOT / 'requirements.lock').read_bytes()).hexdigest(),
            'models': json.loads((ROOT / 'assets' / 'ocr' / 'manifest.json').read_text())}
    (STAGING / 'build-info.json').write_text(json.dumps(info, indent=2), encoding='utf-8')
    subprocess.run([sys.executable, str(ROOT / 'scripts' / 'check_release.py'), str(STAGING)], check=True)
    if args.stage_only:
        return
    destination = ROOT / 'output' / f'SnapTrans-{__version__}-win-x64'
    if Path(str(destination) + '.zip').exists():
        raise RuntimeError('Release ZIP already exists; preserve it or choose a new version before rebuilding.')
    archive = Path(shutil.make_archive(str(destination), 'zip', STAGING.parent, STAGING.name))
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix('.zip.sha256').write_text(f'{digest}  {archive.name}\n', encoding='ascii')
    print(f'Portable ZIP: {archive.name} ({archive.stat().st_size / 1048576:.1f} MiB)')


if __name__ == '__main__':
    main()

"""Verify the independent source export without installing global tools."""
import base64
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from snaptrans import __version__


def ps_literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def main():
    archive = ROOT / 'output' / f'SnapTrans-{__version__}-source.zip'
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    assert digest == archive.with_suffix('.zip.sha256').read_text().split()[0]
    directory = ROOT / '.tmp' / ('源码 验证-' + uuid.uuid4().hex[:8])
    directory.mkdir(parents=True)
    forbidden = {'.venv', '.cache', '.tmp', '__pycache__', '.git', 'data', 'output', 'build'}
    with zipfile.ZipFile(archive) as source:
        for item in source.infolist():
            name = PurePosixPath(item.filename)
            if (name.is_absolute() or '..' in name.parts or ':' in item.filename
                    or '\\' in item.filename or name.parts[0] != 'SnapTrans'
                    or forbidden.intersection(name.parts)):
                raise RuntimeError('Invalid or private source path: ' + item.filename)
        assert source.testzip() is None
        count = len(source.infolist())
        source.extractall(directory)
    checkout = directory / 'SnapTrans'
    test_temp = ROOT / '.tmp' / ('source-tests-' + uuid.uuid4().hex[:8])
    # Validate the detached environment with no parent project-env.ps1 nearby.
    command = '\n'.join([
        "$ErrorActionPreference = 'Stop'",
        '. ' + ps_literal(ROOT / 'project-env.ps1'),
        'Set-Location -LiteralPath ' + ps_literal(checkout),
        '. ./project-env.ps1', '. ./scripts/env.ps1',
        "if ($nestedProject) { throw 'Unexpected dependency on a parent project' }",
        "foreach ($name in @('TEMP','TMP','TMPDIR','PIP_CACHE_DIR','PYTHONPYCACHEPREFIX','PYINSTALLER_CONFIG_DIR')) {",
        "  $value = [Environment]::GetEnvironmentVariable($name, 'Process')",
        "  if (-not $value.StartsWith($snapRoot + [IO.Path]::DirectorySeparatorChar)) { throw ('External cache: ' + $name) }",
        '}',
        '& ' + ps_literal(sys.executable) + ' -m pytest -q --basetemp ' + ps_literal(test_temp)
        + ' *> .tmp/source-tests.log',
        'exit $LASTEXITCODE',
    ])
    env = dict(os.environ)
    env.pop('PYTHONPATH', None)
    encoded = base64.b64encode(command.encode('utf-16-le')).decode('ascii')
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive',
                            '-ExecutionPolicy', 'Bypass', '-EncodedCommand', encoded],
                            env=env, cwd=checkout, timeout=360, capture_output=True,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    (directory / 'environment-process.log').write_bytes(result.stdout + result.stderr)
    report = {'ok': result.returncode == 0, 'source_sha256': digest, 'files': count,
              'crc': 'passed', 'private_directories_excluded': True,
              'standalone_environment_and_tests': result.returncode == 0,
              'dependency_environment': 'existing locked Python environment; no fresh dependency download',
              'test_log': str((checkout / '.tmp/source-tests.log').relative_to(ROOT))}
    (ROOT / 'output' / f'source-verification-{__version__}.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))
    if result.returncode:
        raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()

"""Verify the delivered ZIP, then run its extracted EXE without a Python PATH."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import uuid
import zipfile
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from snaptrans import __version__


def main():
    archive = ROOT / 'output' / f'SnapTrans-{__version__}-win-x64.zip'
    expected = archive.with_suffix('.zip.sha256').read_text().split()[0]
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    if digest != expected:
        raise RuntimeError('ZIP SHA256 mismatch')
    destination = ROOT / '.tmp' / ('解压 验证-' + uuid.uuid4().hex[:8])
    destination.mkdir()
    with zipfile.ZipFile(archive) as source:
        for item in source.infolist():
            path = PurePosixPath(item.filename)
            if path.is_absolute() or '..' in path.parts or path.parts[0] != 'SnapTrans':
                raise RuntimeError('Unexpected archive path')
        bad_file = source.testzip()
        if bad_file:
            raise RuntimeError('ZIP CRC mismatch: ' + bad_file)
        source.extractall(destination)
    exe = destination / 'SnapTrans' / 'SnapTrans.exe'
    environment = dict(os.environ)
    windows = Path(os.environ['SystemRoot'])
    environment['PATH'] = str(windows / 'System32') + os.pathsep + str(windows)
    for name in ('PYTHONPATH', 'PYTHONHOME', 'VIRTUAL_ENV'):
        environment.pop(name, None)
    report = ROOT / '.tmp' / 'archive-ocr-test.json'
    subprocess.run([str(exe), '--self-test', '--report', str(report)],
                   cwd=ROOT, env=environment, check=True, timeout=60,
                   creationflags=subprocess.CREATE_NO_WINDOW)
    ocr = json.loads(report.read_text(encoding='utf-8'))
    if not ocr['ok']:
        raise RuntimeError('Extracted OCR self-test failed')
    storage_report = destination / 'storage-check.json'
    subprocess.run([str(exe), '--self-test-storage', '--report', str(storage_report)],
                   cwd=ROOT, env=environment, check=True, timeout=30,
                   creationflags=subprocess.CREATE_NO_WINDOW)
    storage = json.loads(storage_report.read_text(encoding='utf-8'))
    assert storage['ok'] and Path(storage['data']) == exe.parent / 'data'
    result = {'ok': True, 'sha256': digest, 'zip_bytes': archive.stat().st_size,
              'extracted_bytes': sum(p.stat().st_size for p in destination.rglob('*') if p.is_file()),
              'crc': 'passed', 'chinese_space_path': True, 'clean_python_environment': True,
              'ocr': ocr, 'data_stays_beside_executable': storage['temporary_files_follow_executable']}
    (ROOT / 'output' / f'delivery-verification-{__version__}.json').write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()

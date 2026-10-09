"""Check release material for NVIDIA key-shaped literals without printing secrets."""
from pathlib import Path
import re
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PATTERN = re.compile(rb'nvapi-[A-Za-z0-9_-]{20,}')


def contains_key(stream):
    tail = b''
    while chunk := stream.read(1024 * 1024):
        data = tail + chunk
        if PATTERN.search(data):
            return True
        tail = data[-256:]
    return False


def main():
    failures = []
    count = 0
    for directory in ('snaptrans', 'scripts', 'docs'):
        for path in (ROOT / directory).rglob('*'):
            if path.is_file() and '__pycache__' not in path.parts:
                with path.open('rb') as stream:
                    if contains_key(stream):
                        failures.append(str(path.relative_to(ROOT)))
                count += 1
    if len(sys.argv) > 1:
        with zipfile.ZipFile(sys.argv[1]) as archive:
            for item in archive.infolist():
                if not item.is_dir():
                    with archive.open(item) as stream:
                        if contains_key(stream):
                            failures.append(item.filename)
                    count += 1
    if failures:
        raise SystemExit('Key-shaped literal found in: ' + ', '.join(failures))
    print(f'NVIDIA key-pattern audit passed; checked {count} source / evidence / archive files.')


if __name__ == '__main__':
    main()

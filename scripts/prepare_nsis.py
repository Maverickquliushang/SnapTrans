"""Fetch a pinned portable compiler into this checkout, without installing tools."""
import hashlib
from pathlib import Path, PurePosixPath
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = '3.11'
SHA256 = 'c7d27f780ddb6cffb4730138cd1591e841f4b7edb155856901cdf5f214394fa1'
URL = 'https://github.com/tauri-apps/binary-releases/releases/download/nsis-3.11/nsis-3.11.zip'


def prepare():
    archive = ROOT / '.cache' / f'nsis-{VERSION}.zip'
    archive.parent.mkdir(parents=True, exist_ok=True)
    if not archive.exists() or hashlib.sha256(archive.read_bytes()).hexdigest() != SHA256:
        with urllib.request.urlopen(URL, timeout=60) as source:
            data = source.read()
        if hashlib.sha256(data).hexdigest() != SHA256:
            raise RuntimeError('NSIS compiler checksum mismatch')
        archive.write_bytes(data)
    destination = ROOT / '.cache' / 'nsis'
    with zipfile.ZipFile(archive) as source:
        for item in source.namelist():
            path = PurePosixPath(item)
            if path.is_absolute() or '..' in path.parts or path.parts[0] != f'nsis-{VERSION}':
                raise RuntimeError('Unexpected compiler archive path')
        source.extractall(destination)
    return destination / f'nsis-{VERSION}' / 'makensis.exe'


if __name__ == '__main__':
    print(prepare())

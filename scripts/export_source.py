"""Export a standalone GitHub-ready tree using an explicit allowlist."""
import hashlib
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from snaptrans import __version__

DIRECTORIES = ('snaptrans', 'scripts', 'tests', 'assets', 'licenses', 'vendor', 'installer', '.github')
FILES = ('README.md', 'LICENSE', 'THIRD_PARTY_NOTICES.md', 'CONTRIBUTING.md', 'SECURITY.md',
         '.gitignore', '.gitattributes', 'project-env.ps1', 'pyproject.toml', 'main.py', 'SnapTrans.spec',
         'requirements.in', 'requirements-dev.in', 'requirements.lock', 'requirements-dev.lock')
EXCLUDED = {'__pycache__', '.pytest_cache', '.tmp', '.cache', 'data', '.venv', 'output', 'build'}


def main():
    archive = ROOT / 'output' / f'SnapTrans-{__version__}-source.zip'
    if archive.exists():
        raise RuntimeError('Source ZIP already exists')
    paths = [ROOT / name for name in FILES]
    for directory in DIRECTORIES:
        paths.extend(p for p in (ROOT / directory).rglob('*') if p.is_file()
                     and not EXCLUDED.intersection(p.relative_to(ROOT).parts)
                     and p.suffix not in ('.pyc', '.log'))
    from public_files import documentation
    paths.extend(documentation(ROOT))
    if any(not p.is_file() for p in paths):
        raise RuntimeError('Required source files missing')
    # Refuse known credential-shaped literals; no secret values are printed.
    from audit_release_secrets import contains_key
    for path in paths:
        with path.open('rb') as source:
            if contains_key(source):
                raise RuntimeError('Credential-shaped literal in export: ' + str(path.relative_to(ROOT)))
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED) as target:
        for path in sorted(set(paths)):
            target.write(path, 'SnapTrans/' + path.relative_to(ROOT).as_posix())
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix('.zip.sha256').write_text(f'{digest}  {archive.name}\n', encoding='ascii')
    print(f'Clean source: {len(set(paths))} files; {archive.stat().st_size / 1048576:.1f} MiB')


if __name__ == '__main__':
    main()

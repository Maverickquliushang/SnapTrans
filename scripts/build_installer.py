"""Compile a per-user installer from the checked release tree."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from prepare_nsis import prepare, VERSION as NSIS_VERSION, SHA256 as NSIS_SHA256, URL as NSIS_URL

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from snaptrans import __version__


def quoted(value):
    value = str(value).replace('$', '$$').replace('"', '$\\"')
    if '\n' in value or '\r' in value:
        raise ValueError('Invalid installer path')
    return '"' + value + '"'


def main():
    from installer_artwork import generate
    generate()
    stage = ROOT / 'output' / f'v{__version__}' / 'SnapTrans'
    output = ROOT / 'output' / f'SnapTrans-{__version__}-Setup-x64.exe'
    if output.exists():
        raise RuntimeError('Installer already exists; preserve it and choose a new version.')
    subprocess.run([sys.executable, str(ROOT / 'scripts/package_release.py'), '--stage-only'], check=True)
    compiler = prepare()
    generated = ROOT / 'build' / 'installer'
    generated.mkdir(parents=True, exist_ok=True)
    files = sorted(p.relative_to(stage) for p in stage.rglob('*') if p.is_file())
    install, uninstall = [], []
    directory = None
    for path in files:
        if path.parent != directory:
            directory = path.parent
            suffix = '' if directory == Path('.') else '\\' + str(directory)
            install.append('SetOutPath "$INSTDIR' + suffix + '"')
        install.append('File ' + quoted(stage / path))
        uninstall.append('Delete "$INSTDIR\\' + str(path).replace('$', '$$') + '"')
    directories = {parent for path in files for parent in path.parents if parent != Path('.')}
    uninstall.extend('RMDir "$INSTDIR\\' + str(path).replace('$', '$$') + '"'
                     for path in sorted(directories, key=lambda p: (-len(p.parts), str(p))))
    install.append('SetOutPath "$INSTDIR"')
    install_path, uninstall_path = generated / 'install-files.nsh', generated / 'uninstall-files.nsh'
    install_path.write_text('\n'.join(install), encoding='utf-8-sig')
    uninstall_path.write_text('\n'.join(uninstall), encoding='utf-8-sig')
    total = sum((stage / p).stat().st_size for p in files)
    arguments = [str(compiler), '/INPUTCHARSET', 'UTF8', '/V2',
        f'/DVERSION={__version__}', f'/DPROJECT_ROOT={ROOT}', f'/DOUTPUT={output}',
        f'/DINSTALL_FILES={install_path}', f'/DUNINSTALL_FILES={uninstall_path}',
        f'/DINSTALLED_KB={(total + 1023) // 1024}', str(ROOT / 'installer' / 'SnapTrans.nsi')]
    subprocess.run(arguments, check=True, cwd=ROOT, creationflags=subprocess.CREATE_NO_WINDOW)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix('.exe.sha256').write_text(f'{digest}  {output.name}\n', encoding='ascii')
    info = {'version': __version__, 'nsis': NSIS_VERSION, 'compiler_zip_sha256': NSIS_SHA256,
            'compiler_source': NSIS_URL, 'installer_sha256': digest, 'bytes': output.stat().st_size,
            'payload_files': len(files), 'signed': False,
            'payload': {str(p): hashlib.sha256((stage / p).read_bytes()).hexdigest() for p in files}}
    (ROOT / 'output' / f'installer-build-{__version__}.json').write_text(json.dumps(info, indent=2), encoding='utf-8')
    print(f'Installer: {output.name} ({output.stat().st_size / 1048576:.1f} MiB)')


if __name__ == '__main__':
    main()

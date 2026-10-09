"""Verify folder-local installation, opt-in registration, and data preservation."""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid
import winreg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from snaptrans import __version__
KEY = r'Software\Microsoft\Windows\CurrentVersion\Uninstall\SnapTrans.Desktop'


def installed_location():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
            return winreg.QueryValueEx(key, 'InstallLocation')[0]
    except FileNotFoundError:
        return None


def run():
    if installed_location() is not None:
        raise RuntimeError('Existing SnapTrans installation found; verification will not alter it.')
    directory = (ROOT / '.tmp' / ('安装 验证-' + uuid.uuid4().hex[:8])).resolve()
    directory.mkdir(parents=True)
    destination = directory / 'SnapTrans'
    assert destination.is_relative_to((ROOT / '.tmp').resolve())
    # Regression: the user selected an ALREADY EXISTING empty folder. Previous
    # checks only exercised a missing destination and missed this case.
    destination.mkdir()
    assert not any(destination.iterdir())
    setup = ROOT / 'output' / f'SnapTrans-{__version__}-Setup-x64.exe'
    expected = setup.with_suffix('.exe.sha256').read_text().split()[0]
    assert hashlib.sha256(setup.read_bytes()).hexdigest() == expected
    result = {'ok': False, 'setup_sha256': expected, 'shortcuts_skipped': True}
    isolated_profile = directory / 'Unused UserProfile'
    environment = dict(os.environ, LOCALAPPDATA=str(isolated_profile), APPDATA=str(isolated_profile))
    def invoke(command, timeout=180):
        # NSIS requires /D= and _?= as an unquoted final raw tail. Normal
        # Windows argument quoting makes NSIS ignore /D when spaces occur.
        if command[-1].startswith(('/D=', '_?=')):
            if any(c in command[-1] for c in ('"', '\r', '\n')):
                raise ValueError('Invalid NSIS directory argument')
            command = subprocess.list2cmdline(command[:-1]) + ' ' + command[-1]
        return subprocess.run(command, cwd=directory, timeout=timeout, env=environment,
                              creationflags=subprocess.CREATE_NO_WINDOW).returncode
    arguments = [str(setup), '/S', '/D=' + str(destination)]
    try:
        assert invoke(arguments) == 0, 'Fresh install failed'
        assert installed_location() is None
        assert (destination / 'install-mode.ini').is_file()
        result['fresh_install_without_registration'] = True
        result['preexisting_empty_directory_accepted'] = True
        marker = (destination / 'install-mode.ini').read_bytes()
        assert b'Shortcuts' not in marker and 'Shortcuts'.encode('utf-16-le') not in marker
        result['default_no_system_shortcuts'] = True
        info = json.loads((ROOT / 'output' / f'installer-build-{__version__}.json').read_text())
        for name, digest in info['payload'].items():
            assert hashlib.sha256((destination / name).read_bytes()).hexdigest() == digest, name
        result['installed_payload_hashes'] = len(info['payload'])
        report = directory / 'installed-ocr.json'
        assert invoke([str(destination / 'SnapTrans.exe'), '--self-test', '--report', str(report)], 60) == 0
        result['installed_exe_ocr'] = json.loads(report.read_text())
        assert result['installed_exe_ocr']['ok']
        storage_report = directory / 'installed-storage.json'
        assert invoke([str(destination / 'SnapTrans.exe'), '--self-test-storage', '--report', str(storage_report)], 30) == 0
        result['installed_storage'] = json.loads(storage_report.read_text(encoding='utf-8'))
        assert Path(result['installed_storage']['data']).resolve() == destination / 'data'
        assert not isolated_profile.exists()
        result['no_profile_data_created'] = True
        keep = destination / 'user-note.txt'
        keep.write_text('User-owned file. Must survive upgrade and uninstall.')
        legacy = destination / 'data' / 'config.json'
        legacy.write_text('{"test_preserve":true}')
        # A busy app blocks installation without killing it.
        api = ctypes.WinDLL('kernel32', use_last_error=True)
        api.CreateMutexW.restype = ctypes.c_void_p
        api.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
        api.CloseHandle.argtypes = [ctypes.c_void_p]
        mutex = api.CreateMutexW(None, False, 'Local\\SnapTrans-InstallGuard')
        assert mutex
        try:
            assert invoke(arguments) == 10, 'Running-app guard failed'
        finally:
            api.CloseHandle(mutex)
        result['running_app_guard'] = True
        assert invoke(arguments) == 0, 'Same-version upgrade/repair failed'
        assert installed_location() is None
        assert keep.is_file() and legacy.read_text() == '{"test_preserve":true}'
        result['upgrade_preserves_user_files'] = True
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.SetFileAttributesW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32]
        kernel.SetFileAttributesW.restype = ctypes.c_int
        for case in ('visible-file', 'hidden-file', 'empty-subdirectory'):
            foreign = directory / case
            foreign.mkdir()
            item = foreign / 'keep'
            if case == 'empty-subdirectory':
                item.mkdir()
            else:
                item.write_text('Never overwrite this directory.')
                if case == 'hidden-file':
                    assert kernel.SetFileAttributesW(str(item), 0x2)
            assert invoke([*arguments[:-1], '/D=' + str(foreign)]) == 14, case
            assert list(foreign.iterdir()) == [item], case
            if item.is_file():
                assert item.read_text() == 'Never overwrite this directory.', case
            result[case + '_rejected_without_changes'] = True
        # Opt-in registration works, and a later default install removes it.
        assert invoke([*arguments[:-1], '/REGISTER', '/NOSTARTMENU', arguments[-1]]) == 0
        assert Path(installed_location()).resolve() == destination
        result['optional_registration'] = True
        assert invoke(arguments) == 0
        assert installed_location() is None and legacy.read_text() == '{"test_preserve":true}'
        result['return_to_default_removes_registration'] = True
        assert invoke([str(destination / 'Uninstall.exe'), '/S', '_?=' + str(destination)]) == 0
        assert not (destination / 'SnapTrans.exe').exists() and installed_location() is None
        assert keep.is_file() and legacy.read_text() == '{"test_preserve":true}'
        result['uninstall_preserves_user_files_and_removes_registration'] = True
        assert invoke(arguments) == 0, 'Reinstall into retained data directory failed'
        assert legacy.read_text() == '{"test_preserve":true}'
        assert invoke([str(destination / 'Uninstall.exe'), '/S', '_?=' + str(destination)]) == 0
        result['reinstall_with_retained_data'] = True
        missing = directory / 'Not created yet'
        assert not missing.exists()
        assert invoke([*arguments[:-1], '/D=' + str(missing)]) == 0
        assert (missing / 'SnapTrans.exe').is_file() and installed_location() is None
        assert invoke([str(missing / 'Uninstall.exe'), '/S', '_?=' + str(missing)]) == 0
        result['missing_directory_created_and_installed'] = True
        result['ok'] = True
    finally:
        # Only undo our own registration, via its own uninstaller. Never another copy.
        current = installed_location()
        if (not current or Path(current).resolve() == destination) and (destination / 'Uninstall.exe').exists():
            result['cleanup_exit'] = invoke([str(destination / 'Uninstall.exe'), '/S', '_?=' + str(destination)])
        (ROOT / 'output' / f'installer-verification-{__version__}.json').write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    run()

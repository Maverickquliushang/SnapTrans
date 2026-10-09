from pathlib import Path
import tempfile
from snaptrans import paths


def test_installed_and_portable_storage_follow_the_executable(tmp_path, monkeypatch):
    application = tmp_path / 'Programs' / 'SnapTrans'
    application.mkdir(parents=True)
    user = tmp_path / 'UserData'
    monkeypatch.setattr(paths, 'app_root', lambda: application)
    monkeypatch.setenv('LOCALAPPDATA', str(user))
    assert paths.storage_root() == application / 'data'
    (application / 'install-mode.ini').write_text('[SnapTrans]\nProductId=SnapTrans.Desktop\n')
    assert paths.storage_root() == application / 'data'
    for key in ('TEMP', 'TMP', 'TMPDIR', 'MPLCONFIGDIR', 'XDG_CACHE_HOME'):
        monkeypatch.setenv(key, str(tmp_path))
    monkeypatch.setattr(tempfile, 'tempdir', None)
    root = paths.initialize_storage()
    assert (root / 'tmp').is_dir() and (root / 'logs').is_dir()
    sentinel = root / 'config.json'
    sentinel.write_text('{"test": true}')
    assert paths.initialize_storage() == root
    assert sentinel.read_text() == '{"test": true}'
    assert not user.exists()
    import os
    for key in ('TEMP', 'TMP', 'TMPDIR', 'MPLCONFIGDIR', 'XDG_CACHE_HOME'):
        assert Path(os.environ[key]).is_relative_to(root)


def test_storage_does_not_depend_on_windows_profile_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, 'app_root', lambda: tmp_path)
    (tmp_path / 'install-mode.ini').touch()
    monkeypatch.delenv('LOCALAPPDATA', raising=False)
    assert paths.storage_root() == tmp_path / 'data'


def test_unwritable_application_directory_never_falls_back(tmp_path, monkeypatch):
    import pytest
    from unittest.mock import patch
    monkeypatch.setattr(paths, 'app_root', lambda: tmp_path / 'Application')
    user = tmp_path / 'UserData'
    monkeypatch.setenv('LOCALAPPDATA', str(user))
    with patch.object(Path, 'mkdir', side_effect=PermissionError('test readonly directory')):
        with pytest.raises(PermissionError):
            paths.initialize_storage()
    assert not user.exists()


def test_category_icons_are_renderable_and_distinct(qt_app):
    from snaptrans.ui.provider_picker import GROUPS, service_icon
    images = [service_icon(kind).pixmap(96, 96).toImage() for kind in GROUPS]
    assert all(not image.isNull() for image in images)
    assert all(image.pixelColor(0, 0).alpha() == 0 for image in images)
    for index, image in enumerate(images):
        assert all(image != other for other in images[index + 1:])

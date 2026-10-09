from copy import deepcopy
from unittest.mock import Mock
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from snaptrans.app import Application
from snaptrans.config import DEFAULT, ConfigStore
from snaptrans.ui.settings_window import SettingsWindow


def harness(qt_app, tmp_path):
    app = Application.__new__(Application)
    app.config = deepcopy(DEFAULT)
    app.store = ConfigStore(tmp_path / 'config.json')
    app.store.save(app.config)
    app.hotkeys = Mock()
    app.tray = Mock()
    app.stopping = False
    app.settings = SettingsWindow(app.config)
    app.settings.hotkey_change_requested.connect(app.save_hotkey)
    app.settings.show()
    app.settings.activateWindow()
    qt_app.processEvents()
    return app


def test_autosave_does_not_save_other_unfinished_settings(qt_app, tmp_path):
    app = harness(qt_app, tmp_path)
    settings = app.settings
    settings.model.setText('unsaved draft')
    QTest.mouseClick(settings.translate_hotkey_control.record_button, Qt.MouseButton.LeftButton)
    QTest.keyClick(settings.translate_hotkey, Qt.Key.Key_F8)
    assert app.store.load()['hotkeys']['translate'] == 'F8'
    assert app.store.load()['translation'] == DEFAULT['translation']
    assert '已自动保存' in settings.translate_hotkey_control.hint.text()
    settings.close()
    assert app.store.load()['hotkeys']['translate'] == 'F8'


def test_manual_debounce_and_close_flush(qt_app, tmp_path):
    app = harness(qt_app, tmp_path)
    settings = app.settings
    QTest.mouseClick(settings.ocr_hotkey_control.manual_button, Qt.MouseButton.LeftButton)
    QTest.keyClicks(settings.ocr_hotkey, 'Ctrl+Alt+H')
    QTest.qWait(750)
    assert app.store.load()['hotkeys']['ocr'] == 'Ctrl+Alt+H'
    settings.ocr_hotkey.selectAll()
    QTest.keyClicks(settings.ocr_hotkey, 'Ctrl+Alt+J')
    settings.close()
    assert app.store.load()['hotkeys']['ocr'] == 'Ctrl+Alt+J'


def test_disk_failure_rolls_back_config_and_registration(qt_app, tmp_path):
    app = harness(qt_app, tmp_path)
    old = deepcopy(app.config)
    app.store.save = Mock(side_effect=OSError('test failure'))
    app.save_hotkey('translate', 'F6')
    assert app.config == old
    assert ConfigStore(tmp_path / 'config.json').load() == old
    assert app.hotkeys.install.call_args.args[0] == old['hotkeys']
    assert app.settings.translate_hotkey.text() == old['hotkeys']['translate']
    assert '未保存' in app.settings.translate_hotkey_control.hint.text()
    app.settings.close()

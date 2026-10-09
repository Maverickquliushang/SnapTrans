from copy import deepcopy
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
import pytest
from snaptrans.config import DEFAULT, ConfigStore, validate
from snaptrans.hotkeys import Hotkeys
from snaptrans.hotkey_format import parse_hotkey
from snaptrans.ui.settings_window import SettingsWindow


def open_settings(qt_app, store=None):
    window = SettingsWindow(deepcopy(DEFAULT))
    def save(action, value):
        config = deepcopy(window.config)
        config['hotkeys'][action] = value
        try:
            validate(config)
        except ValueError as error:
            window.hotkey_saved(action, window.config['hotkeys'][action], str(error))
        else:
            if store:
                store.save(config)
            window.hotkey_saved(action, value)
    window.hotkey_change_requested.connect(save)
    window.show()
    window.activateWindow()
    qt_app.processEvents()
    return window


def test_both_shortcuts_can_change_by_buttons_and_persist(qt_app, tmp_path):
    store = ConfigStore(tmp_path / 'config.json')
    window = open_settings(qt_app, store)
    QTest.mouseClick(window.translate_hotkey_control.record_button, Qt.MouseButton.LeftButton)
    assert not window.translate_hotkey.text()
    QTest.keyClick(window.translate_hotkey, Qt.Key.Key_F6)
    QTest.mouseClick(window.ocr_hotkey_control.record_button, Qt.MouseButton.LeftButton)
    QTest.keyClick(window.ocr_hotkey, Qt.Key.Key_R, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier)
    assert store.load()['hotkeys'] == {'translate': 'F6', 'ocr': 'Ctrl+Alt+R'}
    window.close()
    reopened = SettingsWindow(store.load())
    assert reopened.translate_hotkey.text() == 'F6'
    assert reopened.ocr_hotkey.text() == 'Ctrl+Alt+R'
    reopened.close()


def test_manual_typing_deletion_and_return_to_recording(qt_app):
    window = open_settings(qt_app)
    control = window.translate_hotkey_control
    QTest.mouseClick(control.manual_button, Qt.MouseButton.LeftButton)
    assert not window.translate_hotkey.isReadOnly()
    QTest.keyClick(window.translate_hotkey, Qt.Key.Key_Backspace)
    QTest.keyClicks(window.translate_hotkey, 'Ctrl+Shift+G')
    assert window.translate_hotkey.text() == 'Ctrl+Shift+G'
    QTest.mouseClick(control.record_button, Qt.MouseButton.LeftButton)
    QTest.keyClick(window.translate_hotkey, Qt.Key.Key_F9)
    assert window.translate_hotkey.text() == 'F9'
    assert window.translate_hotkey.isReadOnly()
    assert not control.manual_button.isChecked()
    window.close()


def test_record_escape_and_empty_blur_keep_previous_value(qt_app):
    window = open_settings(qt_app)
    control = window.translate_hotkey_control
    QTest.mouseClick(control.record_button, Qt.MouseButton.LeftButton)
    QTest.keyClick(window.translate_hotkey, Qt.Key.Key_Escape)
    assert window.translate_hotkey.text() == 'F2'
    assert window.isVisible()
    QTest.mouseClick(control.record_button, Qt.MouseButton.LeftButton)
    window.save_button.setFocus()
    qt_app.processEvents()
    assert window.translate_hotkey.text() == 'F2'
    window.close()


def test_unsupported_key_has_visible_reason_and_duplicate_cannot_save(qt_app):
    window = open_settings(qt_app)
    control = window.translate_hotkey_control
    QTest.mouseClick(control.record_button, Qt.MouseButton.LeftButton)
    QTest.keyClick(window.translate_hotkey, Qt.Key.Key_F12)
    assert '保留键' in control.hint.text()
    QTest.keyClick(window.translate_hotkey, Qt.Key.Key_A)
    assert '搭配' in control.hint.text()
    QTest.keyClick(window.translate_hotkey, Qt.Key.Key_W, Qt.KeyboardModifier.AltModifier)
    assert window.translate_hotkey.text() == 'F2'
    assert '不能相同' in control.hint.text()
    window.close()


@pytest.mark.parametrize('chord,expected', [('Ctrl+Space', (2, 0x20)), ('Alt+Home', (1, 0x24)),
                                         ('Ctrl+Shift+Left', (6, 0x25)), ('F24', (0, 0x87))])
def test_extended_keys(chord, expected):
    assert parse_hotkey(chord) == expected


def test_saving_while_suspended_checks_real_windows_conflicts(qt_app):
    hotkeys = Hotkeys()
    reserved = 0x6020
    original = {'translate': 'Ctrl+Alt+Shift+F10', 'ocr': 'Ctrl+Alt+Shift+F11'}
    try:
        hotkeys.install(original)
        hotkeys.set_suspended(True)
        assert hotkeys.api.RegisterHotKey(None, reserved, 7, 0x77)
        with pytest.raises(ValueError, match='占用'):
            hotkeys.install(dict(original, translate='Ctrl+Alt+Shift+F8'))
        assert hotkeys.suspended
        assert not hotkeys.actions
        assert hotkeys.bindings == original
    finally:
        hotkeys.api.UnregisterHotKey(None, reserved)
        hotkeys.close()

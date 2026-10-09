from copy import deepcopy
import pytest
from PySide6.QtCore import Qt, QRectF
from PySide6.QtTest import QTest
from PySide6.QtGui import QPixmap
from snaptrans.config import DEFAULT, validate
from snaptrans.hotkey_format import parse_hotkey
from snaptrans.ui.hotkey_edit import HotkeyEdit
from snaptrans.ui.result_window import ResultWindow
from snaptrans.ui.settings_window import SettingsWindow
from snaptrans.core.models import TranslationResult
from snaptrans.providers.catalog import default_profile


def test_record_f2_and_chord_from_physical_keys(qt_app):
    field = HotkeyEdit('Alt+Q')
    field.show()
    field.setFocus()
    QTest.keyClick(field, Qt.Key.Key_F2)
    assert field.text() == 'F2'
    assert parse_hotkey(field.text()) == (0, 0x71)
    QTest.keyClick(field, Qt.Key.Key_Q, Qt.KeyboardModifier.AltModifier)
    assert field.text() == 'Alt+Q'
    QTest.keyClick(field, Qt.Key.Key_A)
    assert field.text() == 'Alt+Q'
    with pytest.raises(ValueError):
        parse_hotkey('A')
    field.close()


def test_record_existing_hotkey_suspends_and_restores_registration(qt_app):
    from snaptrans.hotkeys import Hotkeys
    hotkeys = Hotkeys()
    try:
        hotkeys.install({'translate': 'Ctrl+Alt+Shift+F10', 'ocr': 'Ctrl+Alt+Shift+F11'})
        hotkeys.set_suspended(True)
        assert not hotkeys.actions
        assert len(hotkeys.bindings) == 2
        hotkeys.set_suspended(False)
        assert len(hotkeys.actions) == 2
    finally:
        hotkeys.close()


def test_profiles_switch_preserves_models_and_hides_unused_key(qt_app):
    config = deepcopy(DEFAULT)
    config['translation'] = default_profile('ollama')
    config['translation']['model'] = 'my-model'
    config['profiles']['compatible'] = dict(default_profile('compatible'), model='remote-model', base_url='https://example.com/v1')
    window = SettingsWindow(config)
    window.provider.setCurrentIndex(window.provider.findData('mymemory'))
    assert not window.api_key.isEnabled()
    assert window.api_key.placeholderText() == ''
    window.provider.setCurrentIndex(window.provider.findData('compatible'))
    assert window.model.text() == 'remote-model'
    window.provider.setCurrentIndex(window.provider.findData('ollama'))
    assert window.model.text() == 'my-model'
    captured = []
    window.save_requested.connect(lambda c, s: captured.append(c))
    window._emit(window.save_requested)
    assert captured[0]['profiles']['compatible']['model'] == 'remote-model'
    window.close()


def test_overlay_uses_selected_rect_and_closes_with_popup(qt_app):
    window = ResultWindow(dict(DEFAULT['window'], display_mode='overlay'))
    screen = qt_app.primaryScreen()
    geometry = screen.geometry()
    rect = QRectF(geometry.x() + 100, geometry.y() + 250, 400, 40)
    screenshot = QPixmap(geometry.size())
    screenshot.fill(Qt.GlobalColor.white)
    window.attach_capture(screen, screenshot, rect.translated(-geometry.x(), -geometry.y()))
    window.place_near(rect, screen)
    window.show()
    qt_app.processEvents()
    window.set_original('raw', 'source')
    window.set_translation(TranslationResult('x', '这段译文覆盖原句。', 1))
    assert window.overlay.geometry() == geometry
    assert window.overlay.selection.translated(geometry.topLeft()) == rect
    assert window.overlay.isVisible()
    assert window.overlay.translation == '这段译文覆盖原句。'
    window.view_mode.setCurrentIndex(0)
    assert not window.overlay.isVisible()
    assert window.original.isVisible()
    assert window.translated.toPlainText() == '这段译文覆盖原句。'
    window.view_mode.setCurrentIndex(1)
    QTest.keyClick(window.overlay, Qt.Key.Key_Escape)
    qt_app.processEvents()
    assert not window.isVisible()
    assert not window.overlay.isVisible()


def test_old_config_keeps_settings_and_gets_new_fields():
    config = deepcopy(DEFAULT)
    config['translation'] = default_profile('ollama')
    config['hotkeys']['translate'] = 'Alt+Q'
    config.pop('profiles')
    config['window'].pop('display_mode')
    migrated = validate(config)
    assert migrated['translation']['provider'] == 'ollama'
    assert migrated['hotkeys']['translate'] == 'Alt+Q'
    assert migrated['window']['display_mode'] == 'popup'

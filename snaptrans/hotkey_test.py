"""Native keyboard diagnostics; isolated config, no desktop capture or network."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile


def run(report_path):
    if not report_path:
        return 2
    import win32api
    import win32con
    import win32gui
    from PySide6.QtCore import QTimer, Qt, QRect
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from .app import Application
    from .config import DEFAULT, ConfigStore
    from .hotkey_format import parse_hotkey
    from .ui.fonts import initialize_fonts

    report_file = Path(report_path).resolve()
    report_file.parent.mkdir(parents=True, exist_ok=True)
    data = Path(tempfile.mkdtemp(prefix='hotkey-test-', dir=report_file.parent))
    (data / 'logs').mkdir()
    config = deepcopy(DEFAULT)
    config['hotkeys'] = {'translate': 'Ctrl+Alt+Shift+F10', 'ocr': 'Ctrl+Alt+Shift+F11'}
    ConfigStore(data / 'config.json').save(config)
    qt = QApplication([])
    qt.setQuitOnLastWindowClosed(False)
    initialize_fonts(qt)
    application = Application(qt, data)
    # Verify the actual hotkey action dispatch without capturing the user's screen.
    application.hotkeys.activated.disconnect(application.controller.capture)
    triggered = []
    application.hotkeys.activated.connect(triggered.append)
    report = {'ok': False, 'native_keyboard_events': True}

    def require(condition, reason):
        if not condition:
            raise RuntimeError(reason)

    def foreground(settings):
        target = int(settings.winId())
        # Start-Process -WindowStyle Hidden affects the first native ShowWindow
        # call in a frozen GUI EXE; explicitly reveal our diagnostic dialog.
        win32gui.ShowWindow(target, win32con.SW_SHOWNORMAL)
        win32gui.SetWindowPos(target, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                              win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW)
        settings.raise_()
        settings.activateWindow()
        QTest.qWait(100)
        if win32gui.GetForegroundWindow() != target:
            # Background-launched EXEs cannot always request foreground focus.
            # Activate by clicking only a verified point in our own window;
            # never click through another app or inject keys into it.
            point = win32gui.ClientToScreen(target, (8, 8))
            hit = win32gui.WindowFromPoint(point)
            require(hit == target or (hit and win32gui.GetAncestor(hit, 2) == target),
                    'Diagnostic window is covered; no mouse/keyboard input injected')
            cursor = win32api.GetCursorPos()
            try:
                win32api.SetCursorPos(point)
                win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                QTest.qWait(200)
            finally:
                win32api.SetCursorPos(cursor)
        require(win32gui.GetForegroundWindow() == target,
                'Diagnostic window did not receive foreground focus; no keys injected')

    def native_chord(settings, chord, field=None):
        foreground(settings)
        if field is not None:
            # Activate the native window before assigning Qt focus. Activation
            # can otherwise restore the prior widget after field.setFocus().
            QTest.qWait(100)
            field.setFocus()
            QTest.qWait(50)
            require(field.hasFocus(), 'Diagnostic number field did not receive focus')
        mods, key = parse_hotkey(chord)
        keys = [vk for mask, vk in ((2, win32con.VK_CONTROL), (1, win32con.VK_MENU),
                                    (4, win32con.VK_SHIFT)) if mods & mask] + [key]
        pressed = []
        try:
            for vk in keys:
                win32api.keybd_event(vk, 0, 0, 0)
                pressed.append(vk)
                QTest.qWait(25)
        finally:
            for vk in reversed(pressed):
                win32api.keybd_event(vk, 0, win32con.KEYEVENTF_KEYUP, 0)
                QTest.qWait(25)
        QTest.qWait(100)

    def choose_free(choices):
        for chord in choices:
            modifiers, key = parse_hotkey(chord)
            if application.hotkeys.api.RegisterHotKey(None, 0x6060, modifiers, key):
                application.hotkeys.api.UnregisterHotKey(None, 0x6060)
                return chord
        raise RuntimeError('No spare hotkey available for diagnostics')

    def begin():
        try:
            translate = choose_free(['F6', 'F7', 'F8', 'F9'])
            ocr = choose_free(['Ctrl+Alt+Shift+R', 'Ctrl+Alt+Shift+G', 'Ctrl+Alt+Shift+J'])
            application.open_settings()
            settings = application.settings
            foreground(settings)
            QTest.mouseClick(settings.translate_hotkey_control.record_button, Qt.MouseButton.LeftButton)
            require(application.hotkeys.suspended, 'Existing hotkeys were not suspended')
            native_chord(settings, translate)
            require(settings.translate_hotkey.text() == translate, 'Translation shortcut did not change')
            QTest.mouseClick(settings.ocr_hotkey_control.record_button, Qt.MouseButton.LeftButton)
            native_chord(settings, ocr)
            require(settings.ocr_hotkey.text() == ocr, 'OCR shortcut did not change')
            require(not triggered, 'Editing unexpectedly dispatched a capture')
            report['both_recorded'] = {'translate': translate, 'ocr': ocr}
            area = settings.ocr_hotkey_control
            bottom = area.mapTo(settings, area.rect().bottomLeft()).y() + 15
            settings.grab(QRect(0, 0, settings.width(), bottom)).save(str(report_file.with_name('hotkeys-settings.png')))
            require(application.settings is settings, 'Autosave unexpectedly closed settings')
            persisted = ConfigStore(data / 'config.json').load()['hotkeys']
            require(persisted == report['both_recorded'], 'Saved config differs from edited keys')
            require(application.hotkeys.bindings == persisted, 'Windows bindings differ from saved keys')
            report['persisted'] = persisted
            report['saved_without_save_button'] = True
            settings.close()

            application.open_settings()
            settings = application.settings
            foreground(settings)
            require(settings.translate_hotkey.text() == translate and settings.ocr_hotkey.text() == ocr,
                    'Reopened settings did not retain both shortcuts')
            # The save button has focus, so both global shortcuts are active.
            settings.save_button.setFocus()
            QTest.qWait(50)
            native_chord(settings, translate)
            native_chord(settings, ocr)
            require(triggered == ['translate', 'ocr'], 'New shortcuts did not dispatch both actions')
            report['native_actions'] = list(triggered)

            manual = choose_free(['Ctrl+Alt+Shift+K', 'Ctrl+Alt+Shift+L'])
            QTest.mouseClick(settings.ocr_hotkey_control.manual_button, Qt.MouseButton.LeftButton)
            QTest.keyClick(settings.ocr_hotkey, Qt.Key.Key_Backspace)
            QTest.keyClicks(settings.ocr_hotkey, manual)
            require(settings.ocr_hotkey.text() == manual, 'Manual typing did not replace the shortcut')
            QTest.qWait(800)
            require('已自动保存' in settings.ocr_hotkey_control.hint.text(), 'Manual autosave did not finish')
            settings.close()
            persisted = ConfigStore(data / 'config.json').load()['hotkeys']
            require(persisted == {'translate': translate, 'ocr': manual}, 'Manual shortcut not persisted')
            # Unregister and recreate the OS bindings from the on-disk config.
            application.hotkeys.clear()
            application.hotkeys.install(persisted)
            application.open_settings()
            settings = application.settings
            settings.save_button.setFocus()
            native_chord(settings, manual)
            require(triggered == ['translate', 'ocr', 'ocr'], 'Reloaded manual shortcut did not dispatch OCR')
            report['manual_saved_and_reloaded'] = persisted
            settings.tabs.setCurrentIndex(1)
            settings.provider.setCurrentIndex(settings.provider.findData('nvidia'))
            settings.model.setText('deepseek-ai/deepseek-v4.1-flash')
            require(settings.max_tokens.value()==262144, 'Model-specific initial tokens did not apply')
            for field, digits in ((settings.timeout, '180'), (settings.max_tokens, '6000')):
                settings.tabs.widget(1).ensureWidgetVisible(field)
                native_chord(settings, 'Ctrl+A', field)
                for digit in digits:
                    win32api.keybd_event(ord(digit),0,0,0)
                    win32api.keybd_event(ord(digit),0,win32con.KEYEVENTF_KEYUP,0)
                    QTest.qWait(20)
                QTest.qWait(100)
                require(field.value()==int(digits), f'Native number typing failed: expected {digits}, got {field.text()}')
            require(not settings.model_defaults.isChecked(), 'Manual tokens did not disable automatic preset')
            settings.save_button.click()
            values=ConfigStore(data / 'config.json').load()['translation']
            require(values['total_timeout_seconds']==180 and values['max_tokens']==6000, 'Typed parameters not saved')
            report['native_numeric_input'] = {'timeout':180,'max_tokens':6000,'persisted':True}
            report['ok'] = True
        except Exception as error:
            report['error'] = str(error)
        finally:
            application.quit()

    QTimer.singleShot(300, begin)
    qt.exec()
    report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if report['ok'] else 1

"""Native first-run, provider draft and compact-pin checks. Synthetic inputs only."""
def run(report_path):
    if not report_path:
        return 2
    import json, tempfile, multiprocessing, traceback
    from pathlib import Path
    from copy import deepcopy
    import win32api, win32con, win32gui
    from PySide6.QtCore import Qt, QTimer, QPoint, QRectF
    from PySide6.QtGui import QPixmap, QPainter, QColor, QFont
    from PySide6.QtWidgets import QApplication, QScrollArea
    from PySide6.QtTest import QTest
    from .app import Application
    from .config import DEFAULT
    from .ui.fonts import initialize_fonts
    from .ui.pinned_image import PinnedImage
    from .pin_native_test import exercise, verify_pin_pixels

    report_file = Path(report_path).resolve()
    report_file.parent.mkdir(parents=True, exist_ok=True)
    data = Path(tempfile.mkdtemp(prefix='first-run-', dir=report_file.parent))
    (data / 'logs').mkdir()
    # Isolated bindings avoid interfering with any running user copy.
    DEFAULT['hotkeys'] = {'translate': 'Ctrl+Alt+Shift+F10', 'ocr': 'Ctrl+Alt+Shift+F11'}
    qt = QApplication([])
    qt.setQuitOnLastWindowClosed(False)
    initialize_fonts(qt)
    apps = [Application(qt, data)]
    pins = []
    report = {'ok': False}
    cursor = win32api.GetCursorPos()

    def click(widget):
        ancestor = widget.parentWidget()
        while ancestor:
            if isinstance(ancestor, QScrollArea):
                ancestor.ensureWidgetVisible(widget, 8, 8)
                break
            ancestor = ancestor.parentWidget()
        QTest.qWait(30)
        window = widget.window()
        target = int(window.winId())
        win32gui.ShowWindow(target, win32con.SW_SHOWNORMAL)
        win32gui.SetWindowPos(target, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                             win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW)
        window.raise_()
        window.activateWindow()
        QTest.qWait(100)
        if win32gui.GetForegroundWindow() != target:
            activation_point = win32gui.ClientToScreen(target, (8, 8))
            hit = win32gui.WindowFromPoint(activation_point)
            if hit != target and (not hit or win32gui.GetAncestor(hit, 2) != target):
                raise RuntimeError('Activation point covered; no input injected')
            win32api.SetCursorPos(activation_point)
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            QTest.qWait(100)
        if win32gui.GetForegroundWindow() != target:
            raise RuntimeError('Diagnostic window not foreground; no input injected')
        point = widget.mapTo(window, widget.rect().center())
        ratio = window.devicePixelRatioF()
        point = win32gui.ClientToScreen(target, (round(point.x()*ratio), round(point.y()*ratio)))
        hit = win32gui.WindowFromPoint(point)
        if hit != target and (not hit or win32gui.GetAncestor(hit, 2) != target):
            raise RuntimeError('Test control covered; no input injected')
        win32api.SetCursorPos(point)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        QTest.qWait(70)

    def verify():
        try:
            app = apps[0]
            window = app.settings
            assert window and window.isVisible() and window.service_stack.currentIndex() == 0
            assert app.config['translation']['provider'] == 'mymemory' and app.config['ocr']['provider'] == 'local'
            assert app.config['capture']['auto_translate']
            assert app.config['interface']['language'] == 'system'
            report['first_run_defaults_and_picker'] = True
            window.grab().save(str(report_file.with_name('first-run-engines.png')))
            original = deepcopy(app.config)
            click(window.provider_picker.group_buttons['models'])
            window.grab().save(str(report_file.with_name('global-providers.png')))
            click(window.provider_picker.buttons['nvidia'])
            assert window.service_stack.currentIndex() == 1
            window.timeout.setText('180')
            window.grab().save(str(report_file.with_name('engine-detail.png')))
            assert app.config == original and app.store.load() == original
            window.close()
            assert app.config == original and app.store.load() == original
            report['discard_preserves_previous_configuration'] = True
            app.cleanup()
            app = Application(qt, data)
            apps.append(app)
            QTest.qWait(200)
            assert app.settings and app.settings.isVisible()
            report['unconfirmed_first_run_reopens_settings'] = True
            window = app.settings
            window.tabs.setCurrentIndex(1)
            assert window.provider.currentData() == 'mymemory'
            if window.service_stack.currentIndex() != 0:
                click(window.change_provider_button)
            click(window.provider_picker.group_buttons['custom'])
            click(window.provider_picker.buttons['ollama'])
            assert window.provider.currentData() == 'ollama'
            window.model.setText('diagnostic-model')
            click(window.save_button)
            assert app.config['translation']['provider'] == 'ollama', window.message.text()
            assert app.store.load()['translation']['model'] == 'diagnostic-model'
            assert app.store.load()['onboarding']['completed']
            report['native_card_selection_and_save'] = True
            report['save_stays_on_current_page'] = window.isVisible() and window.saved_state.text() == '已保存 ✓'
            assert report['save_stays_on_current_page']
            window.tabs.setCurrentIndex(2)
            click(window.change_ocr_button)
            click(window.ocr_picker.group_buttons['models'])
            click(window.ocr_picker.buttons['qwen_vl'])
            window.ocr_key.setText('synthetic-diagnostic-key')
            click(window.save_button)
            assert app.config['ocr']['provider'] == 'qwen_vl', window.message.text()
            from .providers.ocr_catalog import get_ocr_secret
            assert get_ocr_secret(app.credentials, app.config['ocr']) == 'synthetic-diagnostic-key'
            assert app.credentials.get(app.config['ocr']['base_url']) == ''
            window.grab().save(str(report_file.with_name('ocr-provider-detail.png')))
            window.select_ocr_provider('local')
            click(window.save_button)
            assert app.config['ocr']['provider'] == 'local'
            assert app.config['ocr_profiles']['qwen_vl']['model'] == 'qwen-vl-plus'
            report['native_ocr_picker_save_and_key_isolation'] = True
            window.close()
            app.cleanup()
            app = Application(qt, data)
            apps.append(app)
            QTest.qWait(200)
            assert app.settings is None
            report['confirmed_later_launch_stays_in_tray'] = True
            # Persist interface language independently of translation direction,
            # and verify a fresh application instance reads it from disk.
            app.open_settings()
            window = app.settings
            window.tabs.setCurrentIndex(5)
            window.interface_language.setCurrentIndex(window.interface_language.findData('en'))
            assert app.store.load()['interface']['language'] == 'en'
            assert window.page_title.text() == 'Preferences'
            assert not window._dirty
            report['language_selection_autosaves_without_save_button'] = True
            window.preference_languages.source.setCurrentIndex(window.preference_languages.source.findData('zh-CN'))
            window.preference_languages.target.setCurrentIndex(window.preference_languages.target.findData('en'))
            assert window.translation_languages.pair() == ('zh-CN', 'en')
            click(window.save_button)
            assert app.store.load()['interface']['language'] == 'en'
            assert window.page_title.text() == 'Preferences'
            assert window.save_button.text() == 'Save changes'
            assert window.isVisible() and app.settings is window
            report['interface_language_applies_without_restart'] = True
            report['translation_languages_saved_from_preferences'] = app.config['translation']['target_lang'] == 'en'
            window.grab().save(str(report_file.with_name('live-english-preferences.png')))
            window.interface_language.setCurrentIndex(window.interface_language.findData('zh-CN'))
            assert window.page_title.text() == '偏好设置'
            assert window.preference_languages.pair() == ('zh-CN', 'en')
            window.interface_language.setCurrentIndex(window.interface_language.findData('en'))
            assert window.page_title.text() == 'Preferences'
            report['live_language_round_trip_preserves_translation_pair'] = True
            window.close()
            app.cleanup()
            app = Application(qt, data)
            apps.append(app)
            QTest.qWait(200)
            app.open_settings()
            window = app.settings
            assert window.page_title.text() == 'Capture'
            assert window.translation_languages.pair() == ('zh-CN', 'en')
            window.tabs.setCurrentIndex(5)
            window.grab().save(str(report_file.with_name('english-preferences.png')))
            report['interface_language_persists_after_restart'] = True
            window.close()
            report['pin_pixel_fidelity'] = verify_pin_pixels(qt)

            image = QPixmap(1400, 180)
            image.fill(QColor('white'))
            painter = QPainter(image)
            painter.setPen(QColor('#17202c'))
            font = QFont('Segoe UI'); font.setPixelSize(26); painter.setFont(font)
            painter.drawText(QRectF(22, 18, 1340, 150), Qt.TextFlag.TextWordWrap,
                'SnapTrans screenshot and translation workspace.\nA wide image keeps its original size while the editing toolbar stays compact.\nDraw, erase annotations, copy, save, or return to the workspace.')
            painter.end()
            image.setDevicePixelRatio(1.5)
            area = qt.primaryScreen().availableGeometry()
            pin = PinnedImage(image, area.topLeft()+QPoint(20, 80), state={'diagnostic': True})
            pins.append(pin); pin.show(); QTest.qWait(100)
            report['native_pin_operations'] = exercise(pin, qt)
            pin.set_tool('pen')
            click(pin.options.size)
            QTest.keyClick(pin.options.size, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
            QTest.keyClicks(pin.options.size, '12')
            QTest.keyClick(pin.options.size, Qt.Key.Key_Return)
            assert pin.image.stroke_width == 12
            click(pin.options.swatches['#438cff'])
            assert pin.image.color == '#438cff'
            pin.toolbar.grab().save(str(report_file.with_name('palette-and-size.png')))
            pin.set_tool('eraser'); pin.options.size.setValue(90)
            assert not pin.image.cursor().pixmap().isNull()
            pin.toolbar.grab().save(str(report_file.with_name('eraser-size.png')))
            pin.set_tool('move')
            report['toolbar_keyboard_size_and_palette'] = True
            assert pin.height() == pin.image.height()+6 and pin.toolbar.height() < 110
            assert pin.toolbar.width() < pin.width()
            assert pin.toolbar.geometry().intersected(pin.geometry()).isEmpty()
            pin.grab().save(str(report_file.with_name('wide-pin-image.png')))
            pin.toolbar.grab().save(str(report_file.with_name('compact-pin-toolbar.png')))
            report['wide_pin_compact'] = {'image_width': pin.width(), 'toolbar_width': pin.toolbar.width(), 'toolbar_height': pin.toolbar.height()}
            pin.hide(); assert not pin.toolbar.isVisible()
            pin.show(); QTest.qWait(50); assert pin.toolbar.isVisible()
            pin.close()
            small = PinnedImage(image.copy(0, 0, 240, 75), area.bottomRight()-QPoint(100, 65))
            pins.append(small); small.show(); QTest.qWait(70)
            assert small.width() < 300 and area.contains(small.toolbar.geometry())
            assert small.toolbar.geometry().intersected(small.geometry()).isEmpty()
            small.close()
            report['small_pin_bounds_and_toolbar_lifecycle'] = True
            report['ok'] = True
        except Exception:
            report['error'] = traceback.format_exc()
        finally:
            win32api.SetCursorPos(cursor)
            for pin in pins:
                try: pin.close()
                except RuntimeError: pass
            for app in apps:
                app.cleanup()
            qt.quit()

    QTimer.singleShot(600, verify)
    qt.exec()
    report['children_after_shutdown'] = len(multiprocessing.active_children())
    report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if report['ok'] else 1

"""Native screenshot workspace diagnostics using a public synthetic desktop."""
from copy import deepcopy
import json
import multiprocessing
from pathlib import Path
import tempfile
import time


def run(report_path, online=False, online_provider='mymemory'):
    if not report_path:
        return 2
    from PySide6.QtCore import QTimer, QRectF, QPoint, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QCursor
    from .app import Application
    from .config import DEFAULT, ConfigStore
    from .core.models import State, TranslationResult
    from .demo_scene import screenshot_scene
    from .providers.catalog import default_profile
    from .ui.fonts import initialize_fonts
    from .pin_native_test import exercise, verify_caption, exercise_workspace
    report_file = Path(report_path).resolve()
    report_file.parent.mkdir(parents=True, exist_ok=True)
    data = Path(tempfile.mkdtemp(prefix='ocr-workspace-', dir=report_file.parent))
    (data / 'logs').mkdir()
    config = deepcopy(DEFAULT)
    config['hotkeys'] = {'translate': 'Ctrl+Alt+Shift+F10', 'ocr': 'Ctrl+Alt+Shift+F11'}
    if not online:
        config['translation'] = default_profile('compatible')
    else:
        config['translation'] = default_profile(online_provider)
    ConfigStore(data / 'config.json').save(config)
    qt = QApplication([])
    qt.setQuitOnLastWindowClosed(False)
    initialize_fonts(qt)
    application = Application(qt, data)
    controller = application.controller
    report = {'ok': False, 'online': online, 'online_provider': online_provider if online else None, 'stage': 'starting'}
    sent = []
    pin_sent = []
    test_pins = []
    original_submit = application.network.submit
    def submit(request, secret):
        if request.request_id.startswith('pin-'):
            pin_sent.append(request)
            if not online:
                QTimer.singleShot(80, lambda: application.network.succeeded.emit(
                    TranslationResult(request.request_id, '不匹配平均值', 80)))
                return
            original_submit(request, secret)
            return
        sent.append(request)
        original_submit(request, secret)
    application.network.submit = submit
    started = time.monotonic()

    def require(condition, reason):
        if not condition:
            raise RuntimeError(reason)

    def preview(canvas, filename, include_panel=False):
        area = canvas.selection.united(QRectF(canvas.toolbar.geometry()))
        if include_panel:
            area = area.united(QRectF(canvas.ocr_panel.geometry()))
        area = area.united(QRectF(canvas.message.geometry())).adjusted(-18, -20, 18, 20)
        canvas.grab(area.intersected(QRectF(canvas.rect())).toAlignedRect()).save(str(report_file.with_name(filename)))

    def open_fixture():
        if controller.result:
            controller.result.close()
            controller.result.deleteLater()
            controller.result = None
        controller.screen = qt.primaryScreen()
        controller.snapshot = deepcopy(application.config)
        controller.ocr_only = True
        controller.pixmap, rect = screenshot_scene(controller.screen)
        controller.selected(controller.gate.begin(State.SELECTING), rect)
        qt.processEvents()
        return controller.result.overlay

    def begin():
        try:
            canvas = open_fixture()
            report['image_first'] = controller.frame is None and controller.gate.state == State.COMPLETED
            preview(canvas, 'ocr-capture.png')
            corner = canvas.selection.bottomRight().toPoint()
            QTest.mousePress(canvas, Qt.MouseButton.LeftButton, pos=corner)
            QTest.mouseMove(canvas, corner + QPoint(12, 4))
            QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=corner + QPoint(12, 4))
            report['adjust_without_ocr'] = controller.frame is None and controller.gate.state == State.COMPLETED
            canvas.copy_image()
            report['clean_image_copy'] = qt.clipboard().pixmap().toImage() == canvas.selected_pixmap().toImage()
            report['ocr_workspace_drawing'] = exercise_workspace(canvas, str(report_file.with_name('ocr-workspace-drawing.png')))
            report['workspace_mosaic'] = exercise_workspace(canvas, str(report_file.with_name('workspace-mosaic.png')), 'mosaic')
            controller.pin_selection()
            require(bool(controller.pins), 'Pin not created')
            pin = controller.pins[0]
            report['pin_visible'] = pin.isVisible() and not controller.result.isVisible()
            report['ocr_pin_native_operations'] = exercise(pin, qt)
            pin.grab().save(str(report_file.with_name('ocr-pin.png')))
            pin_config = deepcopy(config)
            pin_config['translation'] = default_profile(online_provider)
            controller.pin_tasks.config_getter = lambda: pin_config
            pin.engine.setCurrentIndex(pin.engine.findData(online_provider))
            test_pins.append((pin, pin.pos(), pin.zoom))
            report['stage'] = 'pin_translate'
            QTest.mouseClick(pin.translate_button, Qt.MouseButton.LeftButton)
        except Exception as error:
            finish_error(error)

    def finish_error(error):
        import traceback
        report['error'] = str(error)
        report['traceback'] = traceback.format_exc()
        application.quit()

    def poll():
        try:
            if controller.gate.state == State.FAILED:
                raise RuntimeError(controller.result.status.text())
            if report['stage'] == 'pin_translate' and not test_pins[0][0].busy:
                pin, position, zoom = test_pins[0]
                require(pin.can_compare, 'Pin-local translation failed: ' + pin.status.text())
                report['pin_local_translation'] = dict(source=pin.state['source'], translated=pin.state['translation'],
                    original_position=pin.pos() == position, original_zoom=pin.zoom == zoom,
                    workspace_hidden=not controller.result.isVisible(), requests=len(pin_sent),
                    network_used=online)
                require(pin.pos() == position and pin.zoom == zoom and not controller.result.isVisible(), 'Pin moved to workspace')
                pin.toolbar.grab().save(str(report_file.with_name('pin-local-translation.png')))
                pin.close()
                canvas = open_fixture()
                report['stage'] = 'extract'
                QTest.mouseClick(canvas.extract_button, Qt.MouseButton.LeftButton)
            elif report['stage'] == 'extract' and controller.gate.state == State.COMPLETED:
                window = controller.result
                canvas = window.overlay
                report['original'] = window.source_text()
                require(report['original'] == 'mismatch_mean', 'Actual OCR returned unexpected text')
                report['local_extraction'] = not sent and canvas.ocr_panel.isVisible()
                preview(canvas, 'ocr-workspace.png', include_panel=True)
                canvas.copy_text()
                report['text_copy'] = qt.clipboard().text() == window.source_text()
                report['stage'] = 'popup'
                QTest.mouseClick(canvas.translate_ocr_button, Qt.MouseButton.LeftButton)
            elif report['stage'] == 'popup' and controller.gate.state == State.COMPLETED:
                report['stage'] = 'interop'
                window = controller.result
                report['popup_transfer'] = window.original.isVisible() and not window.overlay.isVisible()
                report['translation'] = window.translated.toPlainText()
                require((bool(report['translation']) and len(sent) == 1) if online else not sent,
                        'Unexpected translation request count/result')
                window.grab().save(str(report_file.with_name('ocr-to-translation.png')))
                report['popup_dark_caption'] = verify_caption(window, str(report_file.with_name('popup-native-frame.png')))
                original = window.overlay.selected_pixmap().toImage()
                source = window.source_text()
                if not online:
                    report['translation_fixture'] = 'Synthetic UI text; no translation network request'
                    report['translation'] = '不匹配平均值'
                    window.translated.setPlainText(report['translation'])
                    window.translation_source = source
                controller.switch_workspace('translate')
                canvas = window.overlay
                require(not window.ocr_mode and canvas.isVisible(), 'Cannot return to translation workspace')
                report['shared_translation'] = canvas.translation == report['translation']
                # Verify the native Windows cursor over the toolbar's padding.
                import win32gui
                import win32con
                win32gui.ShowWindow(int(canvas.winId()), win32con.SW_SHOWNORMAL)
                win32gui.SetWindowPos(int(canvas.winId()), win32con.HWND_TOPMOST, 0, 0, 0, 0,
                                      win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW)
                previous_cursor = QCursor.pos()
                try:
                    canvas.setCursor(Qt.CursorShape.CrossCursor)
                    QCursor.setPos(canvas.toolbar.mapToGlobal(QPoint(5, 5)))
                    QTest.qWait(100)
                    report['native_toolbar_arrow'] = win32gui.GetCursorInfo()[1] == win32gui.LoadCursor(0, win32con.IDC_ARROW)
                finally:
                    QCursor.setPos(previous_cursor)
                report['translation_workspace_drawing'] = exercise_workspace(canvas, str(report_file.with_name('translation-workspace-drawing.png')))
                preview(canvas, 'translation-workspace.png')
                QTest.mouseClick(canvas.pin_button, Qt.MouseButton.LeftButton)
                translated_pin = controller.pins[-1]
                report['translation_pin'] = translated_pin.isVisible() and not window.isVisible()
                if online:
                    require(translated_pin.pixmap.toImage() != original, 'Pin did not include translation')
                report['translation_pin_native_operations'] = exercise(translated_pin, qt)
                translated_pin.grab().save(str(report_file.with_name('translation-pin.png')))
                translated_image = translated_pin.pixmap.toImage()
                pin_position, pin_size = translated_pin.pos(), translated_pin.size()
                QTest.mouseClick(translated_pin.compare_button, Qt.MouseButton.LeftButton)
                report['pin_compare_in_place'] = (translated_pin.showing_original
                    and translated_pin.pixmap.toImage() == original
                    and translated_pin.pos() == pin_position and translated_pin.size() == pin_size
                    and not window.overlay.isVisible())
                translated_pin.grab().save(str(report_file.with_name('pin-original-in-place.png')))
                QTest.mouseClick(translated_pin.compare_button, Qt.MouseButton.LeftButton)
                report['pin_compare_restores_translation'] = translated_pin.pixmap.toImage() == translated_image
                translated_pin.toolbar.grab().save(str(report_file.with_name('pin-icon-toolbar.png')))
                pin_destroyed = []
                translated_pin.destroyed.connect(lambda: pin_destroyed.append(True))
                QTest.mouseClick(translated_pin.ocr_button, Qt.MouseButton.LeftButton)
                window = controller.result
                report['pin_back_to_original'] = (window.ocr_mode and window.overlay.isVisible()
                    and window.source_text() == source and window.overlay.selected_pixmap().toImage() == original)
                preview(window.overlay, 'pin-back-to-ocr.png', include_panel=True)
                QTest.mouseClick(window.overlay.workspace_translate_button, Qt.MouseButton.LeftButton)
                report['ocr_back_to_translation'] = (not window.ocr_mode and window.overlay.isVisible()
                    and window.translated.toPlainText() == report['translation'])
                require(len(sent) == (1 if online else 0), 'Switching workspaces sent unnecessary requests')
                window.close()
                QTest.qWait(30)
                report['returned_pin_disposed'] = bool(pin_destroyed) and translated_pin not in controller.pins
                application.open_settings()
                settings = application.settings
                qt.processEvents()
                report['settings_dark_caption'] = verify_caption(settings, str(report_file.with_name('settings-native-frame.png')))
                settings.grab().save(str(report_file.with_name('settings-shortcuts.png')))
                settings.tabs.setCurrentIndex(1)
                QTest.qWait(50)
                settings.grab().save(str(report_file.with_name('settings-service.png')))
                settings.provider.setCurrentIndex(settings.provider.findData('ollama'))
                QTest.qWait(50)
                settings.grab().save(str(report_file.with_name('settings-ollama.png')))
                settings.provider.setCurrentIndex(settings.provider.findData('nvidia'))
                QTest.qWait(50)
                settings.grab().save(str(report_file.with_name('settings-nvidia.png')))
                settings.model.setText('deepseek-ai/deepseek-v4.1-flash')
                settings.tabs.widget(1).ensureWidgetVisible(settings.max_tokens)
                QTest.qWait(50)
                settings.grab().save(str(report_file.with_name('settings-model-tokens.png')))
                settings.tabs.setCurrentIndex(2)
                settings.ocr_provider.setCurrentIndex(1)
                QTest.qWait(50)
                settings.grab().save(str(report_file.with_name('settings-cloud-ocr.png')))
                settings.ocr_provider.setCurrentIndex(settings.ocr_provider.findData('nvidia_vl'))
                QTest.qWait(50)
                settings.grab().save(str(report_file.with_name('settings-vision-ocr.png')))
                settings.tabs.setCurrentIndex(4)
                QTest.qWait(50)
                settings.grab().save(str(report_file.with_name('settings-academic-prompt.png')))
                settings.tabs.setCurrentIndex(3)
                QTest.qWait(50)
                settings.grab().save(str(report_file.with_name('settings-reading.png')))
                settings.close()
                menu = application.tray.menu
                menu.popup(qt.primaryScreen().availableGeometry().center())
                QTest.qWait(50)
                menu.grab().save(str(report_file.with_name('tray-menu.png')))
                menu.hide()
                report['ok'] = all(report.get(key) for key in ('image_first', 'adjust_without_ocr',
                    'clean_image_copy', 'pin_visible', 'local_extraction', 'text_copy', 'popup_transfer',
                    'shared_translation', 'native_toolbar_arrow', 'translation_pin', 'pin_back_to_original',
                    'ocr_back_to_translation', 'returned_pin_disposed', 'pin_compare_in_place',
                    'pin_compare_restores_translation', 'pin_local_translation'))
                report['stage'] = 'done'
                application.quit()
            elif time.monotonic() - started > 135:
                raise RuntimeError('Workspace diagnostics timed out')
        except Exception as error:
            finish_error(error)

    timer = QTimer()
    timer.setInterval(100)
    timer.timeout.connect(poll)
    timer.start()
    QTimer.singleShot(300, begin)
    qt.exec()
    report['elapsed_seconds'] = time.monotonic() - started
    report['children_after_shutdown'] = len(multiprocessing.active_children())
    report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if report['ok'] and not report['children_after_shutdown'] else 1

"""Explicit online diagnostics using public synthetic text only."""
from copy import deepcopy
import json
import multiprocessing
from pathlib import Path
import tempfile
import time


def run(report_path, model):
    if not report_path or not model:
        return 2
    from PySide6.QtCore import QTimer, QRectF, Qt, QPoint
    from PySide6.QtGui import QImage, QPixmap
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from .app import Application
    from .config import DEFAULT, ConfigStore
    from .providers.catalog import default_profile
    from .core.models import State
    from .demo_scene import screenshot_scene
    from .ui.fonts import initialize_fonts
    report_file = Path(report_path).resolve()
    report_file.parent.mkdir(parents=True, exist_ok=True)
    data = Path(tempfile.mkdtemp(prefix='features-', dir=report_file.parent))
    (data / 'logs').mkdir()
    config = deepcopy(DEFAULT)
    config['hotkeys'] = {'translate': 'Ctrl+Alt+Shift+F10', 'ocr': 'Ctrl+Alt+Shift+F11'}
    config['window']['display_mode'] = 'overlay'
    config['profiles']['ollama'] = dict(default_profile('ollama'), model=model)
    ConfigStore(data / 'config.json').save(config)
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    initialize_fonts(app)
    application = Application(app, data)
    controller = application.controller
    started = time.monotonic()
    report = {'ok': False, 'stage': 'starting', 'translations': []}

    def begin():
        application.open_settings()
        settings = application.settings
        app.processEvents()
        settings.translate_hotkey.setFocus()
        app.processEvents()
        attempts = []
        settings.translate_hotkey.commit_requested.connect(attempts.append)
        report['hotkeys_suspended_while_recording'] = application.hotkeys.suspended
        QTest.keyClick(settings.translate_hotkey, Qt.Key.Key_F2)
        report['f2_recorded'] = 'F2' in attempts
        settings.test_button.setFocus()
        app.processEvents()
        settings.grab().save(str(report_file.with_name('features-settings.png')))
        report['f2_registered'] = application.hotkeys.bindings.get('translate') == 'F2'
        if '占用' in settings.translate_hotkey_control.hint.text():
            # The user's running copy may already own F2. Do not stop their app.
            report['f2_occupied'] = True
        settings.close()
        report['hotkey_registered'] = bool(application.hotkeys.bindings.get('translate'))
        if application.settings:
            report['error'] = 'settings did not save'
            application.quit()
            return
        request_id = controller.gate.begin(State.SELECTING)
        controller.snapshot = deepcopy(application.config)
        controller.screen = app.primaryScreen()
        canvas, rect = screenshot_scene(controller.screen)
        controller.pixmap = canvas
        controller.selected(request_id, rect)
        report['stage'] = 'free'

    def poll():
        if controller.gate.state == State.FAILED:
            report['error'] = controller.result.status.text()
            application.quit()
        elif controller.gate.state == State.COMPLETED and report['stage'] in ('free', 'ollama', 'resized'):
            window = controller.result
            translated = window.translated.toPlainText()
            report['translations'].append({'stage': report['stage'], 'provider': controller.snapshot['translation']['provider'],
                                            'original': window.source_text(), 'text': translated})
            if not translated:
                report['error'] = window.status.text()
                application.quit()
                return
            if report['stage'] == 'free':
                report['overlay_visible'] = window.overlay.isVisible()
                report['overlay_matches'] = window.overlay.translation == translated
                report['overlay_geometry_matches'] = window.overlay.selection.translated(window.overlay.geometry().topLeft()) == window.anchor
                window.overlay.grab().save(str(report_file.with_name('features-overlay.png')))
                window.overlay.toolbar.grab().save(str(report_file.with_name('features-controls.png')))
                report['stage'] = 'ollama'
                window.engine.setCurrentIndex(window.engine.findData('ollama'))
            elif report['stage'] == 'ollama':
                canvas = window.overlay
                application.open_settings()
                app.processEvents()
                settings = application.settings
                widget = app.widgetAt(settings.mapToGlobal(settings.rect().center()))
                report['settings_above_workspace'] = bool(widget and (
                    widget is settings or settings.isAncestorOf(widget)))
                settings.close()
                app.processEvents()
                canvas.grab().save(str(report_file.with_name('workspace-full.png')))
                preview = canvas.selection.united(QRectF(canvas.toolbar.geometry())).adjusted(-22, -28, 22, 24)
                preview = preview.intersected(QRectF(canvas.rect())).toAlignedRect()
                canvas.grab(preview).save(str(report_file.with_name('workspace-preview.png')))
                canvas.compare.setChecked(True)
                canvas.grab(preview).save(str(report_file.with_name('workspace-original.png')))
                report['compare_enabled'] = canvas.compare.isChecked()
                canvas.compare.setChecked(False)
                report['source_text'] = window.source_text()
                report['stage'] = 'resized'
                report['before_resize_id'] = controller.gate.request_id
                corner = canvas.selection.bottomRight().toPoint()
                QTest.mousePress(canvas, Qt.MouseButton.LeftButton, pos=corner)
                QTest.mouseMove(canvas, corner + QPoint(12, 4))
                QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=corner + QPoint(12, 4))
            else:
                report['resize_reocr'] = controller.gate.request_id != report['before_resize_id']
                window.view_mode.setCurrentIndex(0)
                report['popup_restored'] = window.original.isVisible() and not window.overlay.isVisible()
                window.grab().save(str(report_file.with_name('features-popup.png')))
                report['stage'] = 'done'
                report['ok'] = all(report.get(key) for key in (
                    'f2_recorded', 'hotkey_registered', 'hotkeys_suspended_while_recording',
                    'overlay_visible', 'overlay_matches', 'overlay_geometry_matches', 'popup_restored',
                    'resize_reocr', 'compare_enabled', 'settings_above_workspace'))
                application.quit()
        elif time.monotonic() - started > 180:
            report['error'] = 'features deadline'
            application.quit()

    timer = QTimer()
    timer.setInterval(100)
    timer.timeout.connect(poll)
    timer.start()
    QTimer.singleShot(200, begin)
    app.exec()
    report['elapsed_seconds'] = time.monotonic() - started
    report['children_after_shutdown'] = len(multiprocessing.active_children())
    report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if report['ok'] and not report['children_after_shutdown'] else 1

"""Public synthetic input only; never reads the screen or a user's text."""
import json
import os
from pathlib import Path
import socket
import time

from .core.models import CaptureFrame
from .paths import resource_root


def sample_frame(text='The model achieved 95.2% accuracy.'):
    from PIL import Image, ImageDraw, ImageFont
    image = Image.new('RGB', (1100, 110), 'white')
    font_path = Path(os.environ['WINDIR']) / 'Fonts' / 'arial.ttf'
    font = ImageFont.truetype(str(font_path), 42)
    ImageDraw.Draw(image).text((20, 22), text, font=font, fill='black')
    return CaptureFrame('self-test', 'synthetic', (0, 0, 1100, 110), (0, 0, 1100, 110),
                        (0, 0, 1100, 110), 1100, 110, image.tobytes())


def run(report_path=None):
    started = time.perf_counter()
    original_connect = socket.socket.connect
    def offline(*args, **kwargs):
        raise RuntimeError('Network prohibited during OCR self-test')
    socket.socket.connect = offline
    try:
        from PySide6.QtCore import qVersion
        from .core.ocr_adapter import OcrAdapter
        engine = OcrAdapter(resource_root() / 'assets' / 'ocr')
        result = engine.recognize(sample_frame())
        expected = 'The model achieved 95.2% accuracy.'
        if result.raw_text.strip() != expected:
            raise RuntimeError('OCR sample did not match expected synthetic sentence')
        blank = engine.recognize(sample_frame(''))
        if blank.raw_text or blank.lines:
            raise RuntimeError('Blank image produced OCR text')
        report = {'ok': True, 'qt': qVersion(), 'ocr_ms': result.elapsed_ms,
                  'total_ms': (time.perf_counter() - started) * 1000,
                  'network_blocked': True, 'blank_image': 'passed'}
        code = 0
    except Exception as error:
        report = {'ok': False, 'error_type': type(error).__name__, 'message': str(error)}
        code = 1
    finally:
        socket.socket.connect = original_connect
    if report_path:
        Path(report_path).write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))
    return code


def run_worker(report_path=None):
    from PySide6.QtCore import QCoreApplication, QTimer
    from .core.ocr_process import OcrService
    app = QCoreApplication([])
    service = OcrService(resource_root() / 'assets' / 'ocr')
    report = {'ok': False}
    def done(result):
        report.update(ok=result.raw_text.strip() == 'The model achieved 95.2% accuracy.',
                      worker_ocr_ms=result.elapsed_ms)
        app.quit()
    def failed(request_id, code, message):
        report.update(error=code)
        app.quit()
    service.succeeded.connect(done)
    service.failed.connect(failed)
    service.submit(sample_frame())
    QTimer.singleShot(40000, app.quit)
    app.exec()
    service.close()
    if report_path:
        Path(report_path).write_text(json.dumps(report, indent=2), encoding='utf-8')
    return 0 if report['ok'] else 1


def run_ui(report_path, ollama_model=None):
    """Exercise real widgets, OCR process and optional local translation.

    The input is synthetic. A report path is required to keep diagnostic data
    out of the portable application's normal data directory.
    """
    if not report_path:
        return 2
    from copy import deepcopy
    import multiprocessing
    import shutil
    import tempfile
    from PySide6.QtCore import QTimer, QRectF
    from PySide6.QtGui import QImage, QPixmap
    from PySide6.QtWidgets import QApplication
    from .app import Application
    from .core.models import State
    from .ui.fonts import initialize_fonts

    report_file = Path(report_path).resolve()
    report_file.parent.mkdir(parents=True, exist_ok=True)
    test_data = Path(tempfile.mkdtemp(prefix='ui-test-', dir=report_file.parent))
    (test_data / 'logs').mkdir()
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    initialize_fonts(app)
    application = Application(app, test_data)
    if ollama_model:
        application.config['translation'].update(
            provider='ollama', base_url='http://127.0.0.1:11434/v1',
            model=ollama_model, requires_api_key=False,
            total_timeout_seconds=120, mode='academic')
    controller = application.controller
    started = time.monotonic()
    report = {'ok': False, 'local_translation': bool(ollama_model)}

    def begin():
        application.open_settings()
        application.settings.close()
        frame = sample_frame()
        request_id = controller.gate.begin(State.SELECTING)
        controller.snapshot = deepcopy(application.config)
        controller.ocr_only = not ollama_model
        controller.screen = app.primaryScreen()
        image = QImage(frame.rgb_bytes, frame.width_px, frame.height_px,
                       frame.width_px * 3, QImage.Format.Format_RGB888).copy()
        controller.pixmap = QPixmap.fromImage(image)
        geometry = controller.screen.geometry()
        controller.selected(request_id, QRectF(0, 0, geometry.width(), geometry.height()))
        if not ollama_model:
            controller.extract_text()

    def poll():
        if controller.gate.state in (State.COMPLETED, State.FAILED):
            window = controller.result
            original = window.original.toPlainText() if window else ''
            translated = window.translated.toPlainText() if window else ''
            report.update(ok=controller.gate.state == State.COMPLETED
                          and original == 'The model achieved 95.2% accuracy.'
                          and (not ollama_model or bool(translated)),
                          original=original, translation=translated,
                          elapsed_seconds=time.monotonic() - started)
            application.quit()
        elif time.monotonic() - started > 135:
            report.update(error='UI pipeline timeout')
            application.quit()

    timer = QTimer()
    timer.setInterval(100)
    timer.timeout.connect(poll)
    timer.start()
    QTimer.singleShot(100, begin)
    app.exec()
    report['children_after_shutdown'] = len(multiprocessing.active_children())
    report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    for handler in list(application.logger.handlers):
        handler.close()
        application.logger.removeHandler(handler)
    # Only this freshly created diagnostics directory is removed.
    shutil.rmtree(test_data)
    return 0 if report['ok'] and not report['children_after_shutdown'] else 1

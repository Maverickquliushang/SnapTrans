"""Real UI/controller/OCR-process/network-thread/local-LLM integration."""
from copy import deepcopy
import json
import multiprocessing
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    from PySide6.QtCore import QTimer, QRectF
    from PySide6.QtGui import QImage, QPixmap
    from PySide6.QtWidgets import QApplication
    from snaptrans.app import Application
    from snaptrans.core.models import State
    from snaptrans.self_test import sample_frame
    from snaptrans.ui.fonts import initialize_fonts
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    initialize_fonts(app)
    test_data = ROOT / '.tmp' / 'pipeline-data'
    (test_data / 'logs').mkdir(parents=True, exist_ok=True)
    application = Application(app, test_data)
    application.config['translation'].update(provider='ollama', base_url='http://127.0.0.1:11434/v1',
                                              model='qwen2.5:7b-instruct-q8_0', requires_api_key=False,
                                              total_timeout_seconds=120, mode='academic')
    controller = application.controller
    started = time.monotonic()
    report = {}
    def begin():
        frame = sample_frame()
        request_id = controller.gate.begin(State.SELECTING)
        controller.snapshot = deepcopy(application.config)
        controller.screen = app.primaryScreen()
        image = QImage(frame.rgb_bytes, frame.width_px, frame.height_px, frame.width_px*3, QImage.Format.Format_RGB888).copy()
        controller.pixmap = QPixmap.fromImage(image)
        geometry = controller.screen.geometry()
        controller.selected(request_id, QRectF(0, 0, geometry.width(), geometry.height()))
    def poll():
        if controller.gate.state in (State.COMPLETED, State.FAILED):
            window = controller.result
            translated = window.translated.toPlainText() if window else ''
            report.update(ok=controller.gate.state == State.COMPLETED and bool(translated),
                          original=window.original.toPlainText() if window else '', translation=translated,
                          elapsed_seconds=time.monotonic()-started)
            if window:
                window.grab().save(str(ROOT / '.tmp' / 'ollama-pipeline-window.png'))
            application.quit()
        elif time.monotonic() - started > 130:
            report.update(ok=False, error='pipeline timeout')
            application.quit()
    timer = QTimer()
    timer.setInterval(100)
    timer.timeout.connect(poll)
    timer.start()
    QTimer.singleShot(100, begin)
    app.exec()
    report['children_after_shutdown'] = len(multiprocessing.active_children())
    (ROOT / '.tmp' / 'local-pipeline.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report.get('ok') and not report['children_after_shutdown'] else 1


if __name__ == '__main__':
    multiprocessing.freeze_support()
    raise SystemExit(main())

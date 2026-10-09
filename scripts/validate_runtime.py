"""Exercise real spawn/IPC/model/cancel/shutdown and render our own UI only."""
import json
import multiprocessing
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication
    from snaptrans.core.ocr_process import OcrService
    from snaptrans.self_test import sample_frame
    from snaptrans.config import DEFAULT
    from snaptrans.ui.settings_window import SettingsWindow
    from snaptrans.ui.result_window import ResultWindow
    from snaptrans.core.models import TranslationResult
    app = QApplication([])
    from snaptrans.ui.fonts import initialize_fonts
    initialize_fonts(app)
    app.setQuitOnLastWindowClosed(False)
    output = ROOT / '.tmp' / 'runtime'
    output.mkdir(parents=True, exist_ok=True)
    settings = SettingsWindow(DEFAULT)
    settings.show()
    result = ResultWindow(DEFAULT['window'])
    result.set_original('The model achieved 95.2% accuracy.', 'The model achieved 95.2% accuracy.')
    result.set_translation(TranslationResult('render', '模型的准确率达到了 95.2%。', 0))
    result.show()
    app.processEvents()
    settings.grab().save(str(output / 'settings.png'))
    result.grab().save(str(output / 'result.png'))
    settings.close()
    result.close()
    service = OcrService(ROOT / 'assets' / 'ocr')
    outcomes = []
    errors = []
    started = time.monotonic()

    def failed(request_id, code, message):
        errors.append(code)
        app.quit()

    def received(value):
        outcomes.append(value.raw_text)
        if len(outcomes) == 1:
            service.submit(sample_frame())
            service.cancel()
            QTimer.singleShot(30, lambda: service.submit(sample_frame()))
        else:
            app.quit()

    service.succeeded.connect(received)
    service.failed.connect(failed)
    QTimer.singleShot(60000, lambda: (errors.append('test_deadline'), app.quit()))
    print('Submitting real OCR child task', flush=True)
    service.submit(sample_frame())
    print('Child started; entering Qt event loop', flush=True)
    app.exec()
    service.close()
    report = {'real_ocr_responses': len(outcomes), 'cancel_restart': len(outcomes) == 2,
              'errors': errors, 'children_after_shutdown': len(multiprocessing.active_children()),
              'elapsed_seconds': time.monotonic() - started}
    (output / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report))
    return 0 if len(outcomes) == 2 and not errors and not multiprocessing.active_children() else 1


if __name__ == '__main__':
    multiprocessing.freeze_support()
    raise SystemExit(main())

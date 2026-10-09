"""Real process lifecycle test with 100 synthetic jobs, including cancellations."""
from dataclasses import replace
import json
import multiprocessing
from pathlib import Path
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    from PySide6.QtCore import QCoreApplication, QTimer
    from snaptrans.core.ocr_process import OcrService
    from snaptrans.self_test import sample_frame
    app = QCoreApplication([])
    service = OcrService(ROOT / 'assets' / 'ocr')
    frame = sample_frame()
    report = {'submitted': 0, 'completed': 0, 'cancelled': 0, 'errors': []}
    started = time.monotonic()
    threads_before = threading.active_count()

    def submit():
        if report['submitted'] >= 100:
            app.quit()
            return
        report['submitted'] += 1
        service.submit(replace(frame, request_id=str(report['submitted'])))
        if report['submitted'] % 10 == 0:
            service.cancel()
            report['cancelled'] += 1
            QTimer.singleShot(0, submit)

    def done(result):
        if result.raw_text != 'The model achieved 95.2% accuracy.':
            report['errors'].append('text mismatch')
        report['completed'] += 1
        QTimer.singleShot(0, submit)

    def fail(request_id, code, message):
        report['errors'].append(code)
        app.quit()

    service.succeeded.connect(done)
    service.failed.connect(fail)
    QTimer.singleShot(0, submit)
    QTimer.singleShot(180000, app.quit)
    app.exec()
    service.close()
    # IPC threads have been unblocked by closing the child; wait for their exits.
    for thread in threading.enumerate():
        if thread is not threading.current_thread() and thread.daemon:
            thread.join(timeout=1)
    report.update(elapsed_seconds=time.monotonic() - started,
                  children_after_shutdown=len(multiprocessing.active_children()),
                  threads_before=threads_before, threads_after=threading.active_count())
    report['ok'] = (report['completed'] == 90 and report['cancelled'] == 10
                    and not report['errors'] and not report['children_after_shutdown']
                    and report['threads_after'] == threads_before)
    (ROOT / '.tmp' / 'stress-ocr.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report))
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    multiprocessing.freeze_support()
    raise SystemExit(main())

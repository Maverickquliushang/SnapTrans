"""Capture our own public sentence and reverse-drag the native selector.

Desktop pixels stay in memory; only text and geometry are written to the report.
"""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    from PySide6.QtCore import Qt, QTimer, QPoint
    from PySide6.QtGui import QFont
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QLabel
    from snaptrans.core.capture import make_frame
    from snaptrans.core.ocr_adapter import OcrAdapter
    from snaptrans.ui.selector import Selector
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    screen = app.primaryScreen()
    geometry = screen.geometry()
    area = screen.availableGeometry()
    label = QLabel('The model achieved 95.2% accuracy.')
    label.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
    label.setStyleSheet('background: white; color: black; padding: 20px;')
    label.setFont(QFont('Arial', 24))
    label.setGeometry(area.x() + 40, area.y() + 60, min(850, area.width() - 80), 110)
    label.show()
    resources = []
    report = {'ok': False, 'screen_logical': [geometry.width(), geometry.height()],
              'device_pixel_ratio': screen.devicePixelRatio()}

    def capture():
        pixmap = screen.grabWindow(0)
        rect = label.geometry().translated(-geometry.x(), -geometry.y())
        label.hide()
        selector = Selector(screen, pixmap)
        resources.append(selector)

        def selected(selection):
            frame = make_frame('native-capture', screen, pixmap, selection)
            engine = OcrAdapter(ROOT / 'assets' / 'ocr')
            result = engine.recognize(frame)
            report.update(ok=result.raw_text == label.text(), text=result.raw_text,
                          crop_pixels=[frame.width_px, frame.height_px], reverse_drag=True)
            QTimer.singleShot(0, app.quit)

        selector.selected.connect(selected)
        selector.show()
        selector.activateWindow()

        def drag():
            first = QPoint(rect.x() + rect.width(), rect.y() + rect.height())
            last = rect.topLeft()
            QTest.mousePress(selector, Qt.MouseButton.LeftButton, pos=first)
            QTest.mouseMove(selector, last)
            QTest.mouseRelease(selector, Qt.MouseButton.LeftButton, pos=last)
        QTimer.singleShot(200, drag)

    QTimer.singleShot(700, capture)
    QTimer.singleShot(30000, app.quit)
    app.exec()
    label.close()
    for selector in resources:
        selector.close()
    (ROOT / '.tmp' / 'native-capture.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report))
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

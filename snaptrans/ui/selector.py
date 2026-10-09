from ..i18n import tr
from PySide6.QtCore import Qt, QRectF, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from .localized_widgets import QWidget
from .translation_canvas import paint_handles


class Selector(QWidget):
    selected = Signal(object)
    cancelled = Signal()

    def __init__(self, screen, screenshot):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.screenshot = screenshot
        self.start = None
        self.selection = QRectF()
        self.confirmed = False
        self.setGeometry(screen.geometry())
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMouseTracking(True)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.drawPixmap(self.rect(), self.screenshot)
        painter.fillRect(self.rect(), QColor(10, 13, 18, 125))
        if not self.selection.isEmpty():
            painter.save()
            painter.setClipRect(self.selection)
            painter.drawPixmap(self.rect(), self.screenshot)
            painter.restore()
            paint_handles(painter, self.selection)
        painter.setPen(QColor('white'))
        painter.drawText(20, 30, tr('拖拽选择文字区域 · Esc / 右键取消'))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self.close()
        elif event.button() == Qt.MouseButton.LeftButton:
            self.start = event.position()
            self.selection = QRectF(self.start, self.start)

    def mouseMoveEvent(self, event):
        if self.start is not None:
            self.selection = QRectF(self.start, event.position()).normalized().intersected(QRectF(self.rect()))
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or self.start is None:
            return
        self.selection = QRectF(self.start, event.position()).normalized().intersected(QRectF(self.rect()))
        self.start = None
        if self.selection.width() >= 8 and self.selection.height() >= 8:
            self.confirmed = True
            self.selected.emit(self.selection)
            self.close()
        else:
            self.selection = QRectF()
            self.update()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()

    def closeEvent(self, event):
        if not self.confirmed:
            self.cancelled.emit()
        super().closeEvent(event)

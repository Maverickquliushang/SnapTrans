"""Public synthetic desktop used for UI verification; never reads the user's desktop."""
from PySide6.QtCore import QRectF, Qt, QSize
from PySide6.QtGui import QPixmap, QPainter, QColor, QFont, QPen


def screenshot_scene(screen):
    size = screen.geometry().size()
    ratio = screen.devicePixelRatio()
    pixmap = QPixmap(QSize(round(size.width() * ratio), round(size.height() * ratio)))
    pixmap.setDevicePixelRatio(ratio)
    pixmap.fill(QColor('#f1f3f5'))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.fillRect(0, 0, size.width(), 58, QColor('#e5e8ec'))
    painter.fillRect(0, 58, 190, size.height() - 58, QColor('#e9edf1'))
    font = QFont('Segoe UI')
    font.setPixelSize(15)
    painter.setFont(font)
    painter.setPen(QColor('#5b6370'))
    painter.drawText(24, 36, 'Research workspace')
    for index, label in enumerate(('Overview', 'Datasets', 'Evaluation', 'Results', 'Notes')):
        painter.drawText(28, 108 + index * 44, label)
    left = max(220, size.width() // 2 - 310)
    top = max(120, size.height() // 2 - 190)
    panel = QRectF(left, top, min(660, size.width() - left - 30), 300)
    painter.setPen(QPen(QColor('#d4d9e0'), 1))
    painter.setBrush(QColor('#ffffff'))
    painter.drawRoundedRect(panel, 7, 7)
    painter.fillRect(QRectF(panel.x() + 1, panel.y() + 42, panel.width() - 2, 44), QColor('#f5f6f8'))
    painter.setPen(QColor('#526071'))
    painter.drawText(int(panel.x() + 20), int(panel.y() + 27), 'Evaluation metrics')
    painter.drawText(int(panel.x() + 20), int(panel.y() + 70), 'Metric')
    painter.drawText(int(panel.x() + 420), int(panel.y() + 70), 'Value')
    for row in range(4):
        y = panel.y() + 86 + row * 50
        painter.setPen(QPen(QColor('#e6e9ee'), 1))
        painter.drawLine(int(panel.x()), int(y + 50), int(panel.right()), int(y + 50))
    rect = QRectF(panel.x() + 18, panel.y() + 93, 218, 44)
    painter.fillRect(rect, QColor('white'))
    font.setPixelSize(22)
    painter.setFont(font)
    painter.setPen(QColor('#262a31'))
    painter.drawText(rect.adjusted(12, 0, -8, 0), Qt.AlignmentFlag.AlignVCenter, 'mismatch_mean')
    font.setPixelSize(15)
    painter.setFont(font)
    painter.drawText(int(panel.x() + 420), int(rect.y() + 28), '0.048')
    painter.setPen(QColor('#667385'))
    painter.drawText(int(panel.x() + 30), int(rect.y() + 79), 'confidence_score')
    painter.drawText(int(panel.x() + 420), int(rect.y() + 79), '0.952')
    painter.drawText(int(panel.x() + 30), int(rect.y() + 129), 'sample_count')
    painter.drawText(int(panel.x() + 420), int(rect.y() + 129), '2,400')
    painter.end()
    return pixmap, rect

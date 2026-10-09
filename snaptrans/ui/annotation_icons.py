"""Small vector tool symbols, rendered for normal, checked and disabled states."""
from PySide6.QtCore import Qt, QRectF, QPointF, QSize
from PySide6.QtGui import QIcon, QPixmap, QPainter, QPen, QPainterPath, QPolygonF, QColor
from .themes import palette


def annotation_icon(name, theme=None):
    colors = palette(theme)
    icon = QIcon()
    for mode in (QIcon.Mode.Normal, QIcon.Mode.Active, QIcon.Mode.Disabled):
        for state in (QIcon.State.Off, QIcon.State.On):
            color = colors['muted'] if mode == QIcon.Mode.Disabled else colors['accent' if state == QIcon.State.On else 'text']
            for size in (24, 48, 72):
                pixmap = QPixmap(size, size)
                pixmap.fill(Qt.GlobalColor.transparent)
                painter = QPainter(pixmap)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                painter.scale(size / 24, size / 24)
                pen = QPen(QColor(color), 1.7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
                painter.setPen(pen)
                if mode == QIcon.Mode.Disabled:
                    painter.setOpacity(.55)
                if name == 'select':
                    pen.setStyle(Qt.PenStyle.DashLine)
                    painter.setPen(pen)
                    painter.drawRect(QRectF(4, 4, 16, 16))
                elif name == 'swap':
                    painter.drawLine(4, 8, 20, 8)
                    painter.drawPolyline(QPolygonF([QPointF(16, 4), QPointF(20, 8), QPointF(16, 12)]))
                    painter.drawLine(20, 16, 4, 16)
                    painter.drawPolyline(QPolygonF([QPointF(8, 12), QPointF(4, 16), QPointF(8, 20)]))
                elif name == 'move':
                    painter.drawLine(3, 12, 21, 12)
                    painter.drawLine(12, 3, 12, 21)
                    for angle in (0, 90, 180, 270):
                        painter.save(); painter.translate(12, 12); painter.rotate(angle)
                        painter.drawPolyline(QPolygonF([QPointF(-3, -6), QPointF(0, -9), QPointF(3, -6)]))
                        painter.restore()
                elif name == 'rect':
                    painter.drawRoundedRect(QRectF(3.5, 5, 17, 14), 1, 1)
                elif name == 'ellipse':
                    painter.drawEllipse(QRectF(3.5, 4.5, 17, 15))
                elif name == 'arrow':
                    painter.drawLine(4, 20, 20, 4)
                    painter.drawPolyline(QPolygonF([QPointF(10, 4), QPointF(20, 4), QPointF(20, 14)]))
                elif name == 'pen':
                    painter.drawPolygon(QPolygonF([QPointF(4, 20), QPointF(5, 14), QPointF(16, 3), QPointF(21, 8), QPointF(10, 19)]))
                    painter.drawLine(13, 6, 18, 11)
                    painter.drawLine(5, 14, 10, 19)
                elif name == 'text':
                    painter.drawLine(5, 5, 19, 5); painter.drawLine(12, 5, 12, 20)
                    painter.drawLine(5, 5, 5, 8); painter.drawLine(19, 5, 19, 8)
                    painter.drawLine(9, 20, 15, 20)
                elif name == 'eraser':
                    painter.drawPolygon(QPolygonF([QPointF(3, 14), QPointF(13, 4), QPointF(21, 12), QPointF(13, 20), QPointF(9, 20)]))
                    painter.drawLine(8, 9, 16, 17); painter.drawLine(13, 20, 21, 20)
                elif name == 'mosaic':
                    for row in range(3):
                        for col in range(3):
                            painter.setBrush(QColor(color) if (row + col) % 2 == 0 else Qt.BrushStyle.NoBrush)
                            painter.drawRect(QRectF(4 + col * 6, 4 + row * 6, 4, 4))
                elif name == 'crop':
                    painter.drawPolyline(QPolygonF([QPointF(7, 3), QPointF(7, 17), QPointF(21, 17)]))
                    painter.drawPolyline(QPolygonF([QPointF(3, 7), QPointF(17, 7), QPointF(17, 21)]))
                    painter.drawLine(10, 14, 21, 3)
                elif name in ('undo', 'redo'):
                    if name == 'redo':
                        painter.translate(24, 0); painter.scale(-1, 1)
                    path = QPainterPath(QPointF(4, 9))
                    path.cubicTo(21, 3, 24, 21, 10, 20)
                    painter.drawPath(path)
                    painter.drawPolyline(QPolygonF([QPointF(8, 3), QPointF(3, 9), QPointF(10, 12)]))
                painter.end()
                icon.addPixmap(pixmap, mode, state)
    return icon


def configure_tool_button(button, name, title):
    button.setProperty('annotationIconName', name)
    button.setIcon(annotation_icon(name))
    button.setIconSize(QSize(24, 24))
    button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
    button.setFixedSize(36, 36)
    button.setStyleSheet('QToolButton { padding: 5px; }')
    button.setText(title)
    button.setAccessibleName(title)
    button.setToolTip(title)
    button.setCursor(Qt.CursorShape.PointingHandCursor)

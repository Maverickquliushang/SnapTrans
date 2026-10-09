"""Pixel-based editing for pins, independent from the original OCR capture."""
from ..i18n import tr
import math
from PySide6.QtCore import Qt, QPointF, QRectF, Signal
from PySide6.QtGui import QPixmap, QPainter, QPen, QColor, QPolygonF, QTransform, QFont, QPainterPath, QPainterPathStroker
from .localized_widgets import QWidget, QInputDialog
from .theme import apply_theme
from .brush_options import mosaic_grid, brush_cursor, paint_brush_range


def render_operation(pixmap, operation, background=None):
    kind, points, color, width, text = operation[:5]
    options = operation[5] if len(operation) > 5 else {}
    if kind == 'crop':
        rect = QRectF(points[0], points[-1]).normalized().toAlignedRect().intersected(pixmap.rect())
        return pixmap.copy(rect) if rect.width() >= 3 and rect.height() >= 3 else QPixmap(pixmap)
    if kind in ('rotate', 'flip'):
        transform = QTransform().rotate(90) if kind == 'rotate' else QTransform().scale(-1, 1)
        return pixmap.transformed(transform, Qt.TransformationMode.SmoothTransformation)
    result = QPixmap(pixmap)
    result.setDevicePixelRatio(1)
    painter = QPainter(result)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor(color), width, Qt.PenStyle.SolidLine,
                        Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    if kind in ('eraser', 'mosaic'):
        path = QPainterPath(points[0])
        for point in points[1:]:
            path.lineTo(point)
        stroker = QPainterPathStroker()
        diameter = options.get('diameter', max(18, width * 6))
        stroker.setWidth(diameter)
        stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
        stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        mask = stroker.createStroke(path)
        mask.addEllipse(points[0], diameter / 2, diameter / 2)
        painter.setClipPath(mask)
        if kind == 'mosaic':
            grid = options.get('mosaic_grid')
            if grid is not None:
                painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
                painter.drawPixmap(QRectF(result.rect()), grid, QRectF(grid.rect()))
        elif background is None:
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(result.rect(), Qt.GlobalColor.transparent)
        else:
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
            painter.drawPixmap(0, 0, background)
    elif kind == 'pen':
        if len(points) == 1:
            painter.drawPoint(points[0])
        else:
            painter.drawPolyline(QPolygonF(points))
    elif kind == 'rect':
        painter.drawRect(QRectF(points[0], points[-1]).normalized())
    elif kind == 'ellipse':
        painter.drawEllipse(QRectF(points[0], points[-1]).normalized())
    elif kind == 'arrow':
        start, end = points[0], points[-1]
        painter.drawLine(start, end)
        angle = math.atan2(end.y() - start.y(), end.x() - start.x())
        size = max(12, width * 4)
        for offset in (-.5, .5):
            painter.drawLine(end, end - QPointF(math.cos(angle + offset) * size, math.sin(angle + offset) * size))
    elif kind == 'text':
        font = QFont('Microsoft YaHei')
        font.setPixelSize(options.get('font_size', max(16, width * 7)))
        painter.setFont(font)
        painter.drawText(QRectF(points[0], QPointF(result.width(), result.height())),
                         int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap), text)
    painter.end()
    return result


class PinDocument:
    """Replayable edits avoid retaining a full bitmap for each undo step."""
    def __init__(self, pixmap):
        self.ratio = pixmap.devicePixelRatio()
        self.base = QPixmap(pixmap)
        self.base.setDevicePixelRatio(1)
        self.current = QPixmap(self.base)
        self.background = QPixmap(self.base)
        self.operations = []
        self.index = 0
        self.adaptive_mosaic = False

    def set_base(self, pixmap):
        """Switch the underlying image, retaining the same transform/edit history."""
        self.ratio = pixmap.devicePixelRatio()
        self.base = QPixmap(pixmap)
        self.base.setDevicePixelRatio(1)
        self.replay()

    def _render(self, operation):
        if self.adaptive_mosaic and operation[0] == 'mosaic':
            options = dict(operation[5]) if len(operation) > 5 else {}
            grid = options.get('mosaic_grid')
            options['mosaic_grid'] = (self.current.scaled(grid.size(), Qt.AspectRatioMode.IgnoreAspectRatio,
                                        Qt.TransformationMode.SmoothTransformation)
                                      if grid is not None else mosaic_grid(self.current, 12))
            operation = (*operation[:5], options)
        return render_operation(self.current, operation, self.background)

    def apply(self, operation):
        self.operations = self.operations[:self.index]
        self.operations.append(operation)
        self.index += 1
        if operation[0] in ('crop', 'rotate', 'flip'):
            self.background = render_operation(self.background, operation)
        self.current = self._render(operation)

    def undo(self):
        if self.index:
            self.index -= 1
            self.replay()

    def redo(self):
        if self.index < len(self.operations):
            self.index += 1
            self.replay()

    def replay(self):
        self.current = QPixmap(self.base)
        self.background = QPixmap(self.base)
        for operation in self.operations[:self.index]:
            if operation[0] in ('crop', 'rotate', 'flip'):
                self.background = render_operation(self.background, operation)
            self.current = self._render(operation)

    def export(self):
        result = QPixmap(self.current)
        result.setDevicePixelRatio(self.ratio)
        return result


class PinSurface(QWidget):
    changed = Signal()

    def __init__(self, pin):
        super().__init__(pin)
        self.pin = pin
        self.tool = 'move'
        self.points = []
        self._move_origin = None
        self._resize_origin = None
        self._pan_origin = None
        self.color = '#ff5148'
        self.stroke_width = 3
        self.stroke_options = {}
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def image_rect(self):
        size = self.pin.document.current.size()
        scale = self.pin.zoom / self.pin.document.ratio
        width, height = size.width() * scale, size.height() * scale
        x = max(self.width() - width, min(0, self.pin.pan.x())) if width > self.width() else (self.width() - width) / 2
        y = max(self.height() - height, min(0, self.pin.pan.y())) if height > self.height() else (self.height() - height) / 2
        ratio = self.devicePixelRatioF()
        return QRectF(round(x * ratio) / ratio, round(y * ratio) / ratio, width, height)

    def image_point(self, point):
        area = self.image_rect()
        image = self.pin.document.current
        return QPointF(max(0, min(image.width() - 1, (point.x() - area.x()) * image.width() / area.width())),
                       max(0, min(image.height() - 1, (point.y() - area.y()) * image.height() / area.height())))

    def set_tool(self, tool):
        self.tool = tool
        self.points = []
        self.update_cursor()
        self.update()

    def update_cursor(self):
        if self.tool in ('eraser', 'mosaic') and hasattr(self.pin, 'options'):
            diameter = self.pin.options.values[self.tool] * self.image_rect().width() / self.pin.document.current.width()
            self.setCursor(brush_cursor(self.tool, diameter, self.devicePixelRatioF()))
        else:
            self.setCursor(Qt.CursorShape.OpenHandCursor if self.tool == 'move' else Qt.CursorShape.CrossCursor)

    def operation(self, text=''):
        return (self.tool, list(self.points), self.color, self.stroke_width, text, self.stroke_options)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor('#101319'))
        displayed = self.pin.document.current
        if self.points and self.tool != 'crop':
            displayed = render_operation(displayed, self.operation(), self.pin.document.background)
        physical_scale = self.pin.zoom * self.devicePixelRatioF() / self.pin.document.ratio
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, abs(physical_scale - round(physical_scale)) > .001)
        area = self.image_rect()
        painter.drawPixmap(area, displayed, QRectF(displayed.rect()))
        if self.tool in ('eraser', 'mosaic'):
            painter.save()
            painter.setClipRect(area)
            paint_brush_range(painter, self, area, self.pin.options.values[self.tool] * area.width() / displayed.width())
            painter.restore()
        if self.points and self.tool == 'crop':
            scale = area.width() / displayed.width()
            crop = QRectF(self.points[0], self.points[-1]).normalized()
            crop = QRectF(area.x() + crop.x() * scale, area.y() + crop.y() * scale,
                          crop.width() * scale, crop.height() * scale)
            painter.setPen(QPen(QColor('#ff5148'), 1.5, Qt.PenStyle.DashLine))
            painter.drawRect(crop)
        if self.tool == 'move':
            painter.setPen(QPen(QColor('#8590a4'), 1))
            for offset in (4, 8, 12):
                painter.drawLine(self.width() - offset, self.height() - 2, self.width() - 2, self.height() - offset)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self.pin.reset_view()
            return
        if event.button() == Qt.MouseButton.RightButton:
            self.points = []
            self.update()
            self.pin.context_menu(event.globalPosition().toPoint())
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self.setFocus()
        if self.tool == 'move':
            if event.modifiers() & Qt.KeyboardModifier.AltModifier:
                self._pan_origin = (event.position(), self.image_rect().topLeft())
            elif event.position().x() > self.width() - 16 and event.position().y() > self.height() - 16:
                self._resize_origin = (event.globalPosition(), self.pin.zoom, self.width())
            else:
                self._move_origin = event.globalPosition().toPoint() - self.pin.pos()
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
        elif self.image_rect().contains(event.position()):
            self.points = [self.image_point(event.position())]
            self.stroke_options = self.pin.options.metadata()
            if self.tool == 'mosaic':
                self.stroke_options['mosaic_grid'] = mosaic_grid(self.pin.document.current, self.pin.options.grain.value())
            if self.tool == 'text':
                dialog = QInputDialog(self.pin)
                dialog.setWindowTitle(tr('SnapTrans · 添加文字'))
                dialog.setLabelText(tr('输入标注文字'))
                dialog.setOption(QInputDialog.InputDialogOption.UsePlainTextEditForTextInput)
                apply_theme(dialog)
                if dialog.exec() and dialog.textValue().strip():
                    self.pin.document.apply(self.operation(dialog.textValue()))
                    self.changed.emit()
                self.points = []
            self.update()

    def mouseMoveEvent(self, event):
        if self._pan_origin:
            self.pin.pan = self._pan_origin[1] + event.position() - self._pan_origin[0]
            self.update()
            return
        if self._resize_origin:
            start, zoom, width = self._resize_origin
            self.pin.set_zoom(zoom * max(.1, 1 + (event.globalPosition().x() - start.x()) / width))
        elif self._move_origin is not None:
            self.pin.move(event.globalPosition().toPoint() - self._move_origin)
        elif self.points:
            point = self.image_point(event.position())
            if self.tool in ('pen', 'eraser', 'mosaic'):
                self.points.append(point)
            else:
                self.points = [self.points[0], point]
            self.update()
        elif self.tool == 'move':
            corner = event.position().x() > self.width() - 16 and event.position().y() > self.height() - 16
            self.setCursor(Qt.CursorShape.SizeFDiagCursor if corner else Qt.CursorShape.OpenHandCursor)
        if self.tool in ('eraser', 'mosaic'):
            self.update()

    def leaveEvent(self, event):
        self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self._move_origin = self._resize_origin = self._pan_origin = None
        if self.points:
            self.pin.document.apply(self.operation())
            self.points = []
            self.changed.emit()
            if self.tool == 'crop':
                self.pin.set_tool('move')
        if self.tool == 'move':
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.update()

    def mouseDoubleClickEvent(self, event):
        if self.tool == 'move' and event.button() == Qt.MouseButton.LeftButton:
            self._move_origin = None
            self.pin.reset_view()

    def wheelEvent(self, event):
        if self.points:
            return
        direction = 1 if event.angleDelta().y() > 0 else -1
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.pin.setWindowOpacity(max(.2, min(1., self.pin.windowOpacity() + .1 * direction)))
            self.pin.update_info()
        else:
            self.pin.set_zoom(self.pin.zoom * (1.15 if direction > 0 else 1 / 1.15))
        event.accept()

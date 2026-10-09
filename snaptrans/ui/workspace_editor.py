"""Annotation layer for the selected screenshot, independent of OCR input."""
from ..i18n import tr
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QPixmap, QPainter, QColor
from .localized_widgets import QToolButton, QColorDialog, QInputDialog
from .pin_editor import PinDocument, render_operation
from .theme import apply_theme
from .brush_options import BrushOptions, mosaic_grid, brush_cursor, paint_brush_range
from .annotation_icons import configure_tool_button


class WorkspaceEditor:
    def __init__(self, canvas, row):
        self.canvas, self.document = canvas, None
        self.tool, self.points = 'move', []
        self.color, self.width = '#ff5148', 3
        self.stroke_options = {}
        self.options = BrushOptions(canvas.toolbar)
        self.options.changed.connect(self.options_changed)
        self.buttons = {}
        for name, title in [('move', tr('选区')), ('rect', tr('方框')), ('ellipse', tr('圆形')), ('arrow', tr('箭头')), ('pen', tr('画笔')), ('text', tr('文字')), ('eraser', tr('橡皮擦')), ('mosaic', tr('马赛克'))]:
            button = QToolButton()
            configure_tool_button(button, 'select' if name == 'move' else name, title)
            button.setCheckable(True)
            button.setToolTip(tr('调整选区（会清除当前标注）') if name == 'move' else title + tr(' · 直接在截图选区上操作'))
            if name == 'mosaic':
                button.setToolTip(tr('按住鼠标涂抹遮挡导出的图片；OCR 和翻译仍使用原始截图'))
            elif name == 'eraser':
                button.setToolTip(tr('擦除标注和马赛克，恢复原始截图内容'))
            button.clicked.connect(lambda checked=False, tool=name: self.set_tool(tool))
            row.addWidget(button)
            self.buttons[name] = button
        for name, title, slot in [('undo', tr('撤销'), self.undo), ('redo', tr('重做'), self.redo)]:
            button = QToolButton()
            configure_tool_button(button, name, title + (' · Ctrl+Z' if name == 'undo' else ' · Ctrl+Y'))
            button.clicked.connect(slot)
            row.addWidget(button)
            self.buttons[name] = button
        self.set_tool('move')
        self.sync()

    def reset(self):
        self.document, self.points = None, []
        self.sync()

    def ensure(self):
        if self.document is None:
            base = self.canvas.selected_pixmap()
            base.fill(Qt.GlobalColor.transparent)
            self.document = PinDocument(base)

    def set_tool(self, name):
        self.tool, self.points = name, []
        for key, button in self.buttons.items():
            if key in ('move', 'rect', 'ellipse', 'arrow', 'pen', 'text', 'eraser', 'mosaic'):
                button.setChecked(name == key)
        self.options.set_tool(name)
        self.update_cursor()
        if hasattr(self.canvas, 'ocr_panel'):
            self.canvas._position_toolbar()
        self.canvas.update()

    def options_changed(self):
        self.color, self.width = self.options.color, self.options.values['line']
        self.update_cursor()
        self.canvas.update()

    def update_cursor(self):
        if self.tool in ('eraser', 'mosaic') and self.canvas.selection.width():
            scale = self.display_scale()
            self.canvas.setCursor(brush_cursor(self.tool, self.options.values[self.tool] * scale, self.canvas.devicePixelRatioF()))
        else:
            self.canvas.setCursor(Qt.CursorShape.ArrowCursor if self.tool == 'move' else Qt.CursorShape.CrossCursor)

    def display_scale(self):
        if self.document:
            return self.canvas.selection.width() / max(1, self.document.current.width())
        return self.canvas.width() / max(1, self.canvas.screenshot.width()) if self.canvas.has_capture else 1.

    def choose_color(self):
        self.options.set_tool(self.tool, force=True)
        self.canvas._position_toolbar()

    def point(self, point):
        rect = self.canvas.selection
        size = self.document.current.size()
        return QPointF(max(0, min(size.width()-1, (point.x()-rect.x())*size.width()/rect.width())),
                       max(0, min(size.height()-1, (point.y()-rect.y())*size.height()/rect.height())))

    def operation(self, text=''):
        return (self.tool, list(self.points), self.color, self.width, text, self.stroke_options)

    def press(self, event):
        if self.tool == 'move':
            return False
        if event.button() == Qt.MouseButton.RightButton:
            self.set_tool('move')
            return True
        if event.button() == Qt.MouseButton.LeftButton and self.canvas.selection.contains(event.position()):
            self.ensure()
            self.stroke_options = self.options.metadata()
            if self.tool == 'mosaic':
                source = self.export(self.canvas.unannotated_selection())
                self.stroke_options['mosaic_grid'] = mosaic_grid(source, self.options.grain.value())
            self.points = [self.point(event.position())]
            if self.tool == 'text':
                dialog = QInputDialog(self.canvas)
                dialog.setWindowTitle(tr('截图文字标注'))
                dialog.setLabelText(tr('输入文字'))
                dialog.setOption(QInputDialog.InputDialogOption.UsePlainTextEditForTextInput)
                apply_theme(dialog)
                if dialog.exec() and dialog.textValue().strip():
                    self.document.apply(self.operation(dialog.textValue()))
                self.points = []
                self.sync()
        return True

    def move(self, event):
        if self.tool == 'move':
            return False
        if self.points:
            point = self.point(event.position())
            self.points = self.points + [point] if self.tool in ('pen', 'eraser', 'mosaic') else [self.points[0], point]
        self.canvas.update()
        return True

    def release(self, event):
        if self.tool == 'move':
            return False
        if event.button() == Qt.MouseButton.LeftButton and self.points:
            self.document.apply(self.operation())
            self.points = []
            self.sync()
        return True

    def layer(self):
        if self.document is None:
            return None
        return render_operation(self.document.current, self.operation()) if self.points else self.document.current

    def paint(self, painter):
        image = self.layer()
        if image:
            painter.drawPixmap(self.canvas.selection, image, QRectF(image.rect()))
        if self.tool in ('eraser', 'mosaic'):
            scale = self.display_scale()
            paint_brush_range(painter, self.canvas, self.canvas.selection, self.options.values[self.tool] * scale)

    def export(self, base):
        layer = self.layer()
        if layer is None or base is None:
            return base
        ratio = base.devicePixelRatio()
        base.setDevicePixelRatio(1)
        painter = QPainter(base)
        painter.drawPixmap(base.rect(), layer)
        painter.end()
        base.setDevicePixelRatio(ratio)
        return base

    def undo(self):
        if self.document:
            self.document.undo()
        self.sync()

    def redo(self):
        if self.document:
            self.document.redo()
        self.sync()

    def sync(self):
        self.buttons['undo'].setEnabled(bool(self.document and self.document.index))
        self.buttons['redo'].setEnabled(bool(self.document and self.document.index < len(self.document.operations)))
        self.canvas.update()

    def snapshot(self):
        if self.document is None:
            return None
        return (QPixmap(self.document.base), list(self.document.operations), self.document.index)

    def restore(self, state):
        if state:
            self.document = PinDocument(state[0])
            self.document.operations, self.document.index = list(state[1]), state[2]
            self.document.replay()
        self.sync()

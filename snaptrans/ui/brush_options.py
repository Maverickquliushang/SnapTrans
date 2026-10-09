"""Shared, compact annotation options in source-image pixels."""
from ..i18n import tr
import math
from PySide6.QtCore import Qt, Signal, QRectF, QPointF
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap, QCursor
from .localized_widgets import QWidget, QHBoxLayout, QGridLayout, QLabel, QSlider, QSpinBox, QAbstractSpinBox, QToolButton, QColorDialog
from .theme import apply_theme

COLORS = ('#ff5148', '#ff9800', '#ffd600', '#36bd68', '#00bcd4', '#438cff', '#925bde', '#ffffff',
          '#8b2028', '#aa6338', '#dbb883', '#186b40', '#176975', '#224793', '#e881b2', '#15171c')
RANGES = {'line': (1, 40, 3, '线宽'), 'text': (10, 120, 21, '字号'),
          'eraser': (4, 160, 24, '橡皮擦'), 'mosaic': (8, 200, 40, '涂抹范围')}


class BrushOptions(QWidget):
    changed = Signal()
    def __init__(self, parent=None):
        super().__init__(parent)
        self.tool = 'move'
        self.color = COLORS[0]
        self.values = {key: spec[2] for key, spec in RANGES.items()}
        self.setCursor(Qt.CursorShape.ArrowCursor)
        row = QHBoxLayout(self)
        row.setContentsMargins(4, 5, 4, 3)
        row.setSpacing(8)
        self.title = QLabel(tr('线宽'))
        row.addWidget(self.title)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setFixedWidth(96)
        row.addWidget(self.slider)
        self.size = QSpinBox()
        self.size.setSuffix(' px')
        self.size.setFixedWidth(86)
        self.size.setKeyboardTracking(False)
        self.size.setToolTip(tr('以原始截图像素为单位；可拖动滑块或直接输入'))
        row.addWidget(self.size)
        self.palette = QWidget()
        colors = QGridLayout(self.palette)
        colors.setContentsMargins(4, 0, 4, 0)
        colors.setSpacing(3)
        self.swatches = {}
        for index, color in enumerate(COLORS):
            button = QToolButton()
            button.setProperty('themeExempt', True)
            button.setFixedSize(20, 20)
            button.setToolTip(color)
            button.setCheckable(True)
            button.setStyleSheet(f'QToolButton {{background:{color}; border:1px solid #737985; border-radius:3px; padding:0;}} QToolButton:checked {{border:3px solid #ffffff;}}')
            button.clicked.connect(lambda checked=False, value=color: self.set_color(value))
            colors.addWidget(button, index // 8, index % 8)
            self.swatches[color] = button
        row.addWidget(self.palette)
        self.custom = QToolButton()
        self.custom.setText(tr('更多颜色'))
        self.custom.clicked.connect(self.custom_color)
        row.addWidget(self.custom)
        self.grain_label = QLabel(tr('颗粒'))
        self.grain = QSpinBox()
        self.grain.setRange(4, 40)
        self.grain.setValue(12)
        self.grain.setSuffix(' px')
        self.grain.setFixedWidth(86)
        self.grain.setKeyboardTracking(False)
        self.grain.setToolTip(tr('数值越大，马赛克块越大；橡皮擦可恢复原图'))
        for field in (self.size, self.grain):
            field.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
            field.setStyleSheet('QSpinBox { background:#191d25; color:#edf0f6; border:1px solid #48505e; border-radius:6px; padding:5px 7px; font-size:12px; } QSpinBox:focus { border-color:#ff786f; }')
        row.addWidget(self.grain_label)
        row.addWidget(self.grain)
        row.addStretch()
        self.size.valueChanged.connect(self._size_changed)
        self.slider.valueChanged.connect(self.size.setValue)
        self.grain.valueChanged.connect(lambda _: self.changed.emit())
        self.set_color(self.color)
        self.set_tool('move')

    def key(self):
        return self.tool if self.tool in ('text', 'eraser', 'mosaic') else 'line'

    def set_tool(self, tool, force=False):
        self.tool = tool
        low, high, _, title = RANGES[self.key()]
        self.title.setText(tr(title))
        for widget in (self.slider, self.size):
            widget.blockSignals(True)
            widget.setRange(low, high)
            widget.setValue(self.values[self.key()])
            widget.blockSignals(False)
        colored = tool not in ('eraser', 'mosaic')
        self.palette.setVisible(colored)
        self.custom.setVisible(colored)
        self.grain_label.setVisible(tool == 'mosaic')
        self.grain.setVisible(tool == 'mosaic')
        self.setVisible(force or tool not in ('move', 'crop'))

    def _size_changed(self, value):
        self.values[self.key()] = value
        self.slider.setValue(value)
        self.changed.emit()

    def set_color(self, color):
        self.color = color
        for value, button in self.swatches.items():
            button.setChecked(value == color)
        self.changed.emit()

    def custom_color(self):
        dialog = QColorDialog(QColor(self.color), self)
        dialog.setOption(QColorDialog.ColorDialogOption.DontUseNativeDialog)
        apply_theme(dialog)
        if dialog.exec():
            self.set_color(dialog.selectedColor().name())

    def metadata(self):
        return {'diameter': self.values.get(self.tool, 24), 'font_size': self.values['text']}


def mosaic_grid(source, cell):
    """Keep only a small pixelated snapshot per stroke, not a full undo bitmap."""
    source = QPixmap(source)
    source.setDevicePixelRatio(1)
    return source.scaled(max(1, math.ceil(source.width() / cell)), max(1, math.ceil(source.height() / cell)),
                         Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)


def brush_cursor(tool, diameter, ratio=1.):
    # The glyph scales, while paint_brush_range draws the exact footprint without
    # depending on the operating system's maximum hardware cursor dimensions.
    side = round(max(12, min(40, diameter * .65)))
    pixmap = QPixmap(round((side + 8) * ratio), round((side + 8) * ratio))
    pixmap.setDevicePixelRatio(ratio)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.translate((side + 8) / 2, (side + 8) / 2)
    painter.rotate(-35)
    rect = QRectF(-side * .32, -side * .42, side * .64, side * .84)
    painter.setPen(QPen(QColor('#11151c'), 2))
    painter.setBrush(QColor('#ffb8b1' if tool == 'eraser' else '#dddddd'))
    painter.drawRoundedRect(rect, 2, 2)
    painter.fillRect(QRectF(rect.left()+1, 0, rect.width()-2, rect.height()/2-1), QColor('#ffffff' if tool == 'eraser' else '#555b66'))
    painter.end()
    return QCursor(pixmap, (side + 8) // 2, (side + 8) // 2)


def paint_brush_range(painter, widget, area, diameter):
    point = QPointF(widget.mapFromGlobal(QCursor.pos()))
    if not area.contains(point) or not widget.underMouse():
        return
    painter.save()
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(QColor('#101319'), 3))
    painter.drawEllipse(point, diameter/2, diameter/2)
    painter.setPen(QPen(QColor('#ffffff'), 1))
    painter.drawEllipse(point, diameter/2, diameter/2)
    painter.restore()

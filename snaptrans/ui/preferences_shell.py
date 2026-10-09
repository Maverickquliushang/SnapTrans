"""Quiet settings chrome and an animated, keyboard-accessible switch."""
from PySide6.QtCore import Qt, Property, QPropertyAnimation, QEasingCurve, QRectF, QSize, QEvent
from PySide6.QtGui import QPainter, QColor, QPen, QLinearGradient, QPixmap, QIcon
from .localized_widgets import QCheckBox, QLabel, QGraphicsDropShadowEffect, QStyledItemDelegate, QStyle, QWidget, QHBoxLayout
from .themes import palette, is_light


class CheckRow(QWidget):
    """Keep long checkbox captions readable at narrow window sizes."""
    def __init__(self, checkbox):
        super().__init__()
        from ..i18n import text_source
        text = text_source(checkbox)
        checkbox.setAccessibleName(text)
        checkbox.setText('')
        self.checkbox = checkbox
        self.caption = QLabel(text)
        self.caption.setWordWrap(True)
        self.caption.setCursor(Qt.CursorShape.PointingHandCursor)
        self.caption.installEventFilter(self)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(checkbox, 0, Qt.AlignmentFlag.AlignTop)
        row.addWidget(self.caption, 1)

    def eventFilter(self, watched, event):
        if watched is self.caption and event.type() == QEvent.Type.MouseButtonRelease:
            if event.button() == Qt.MouseButton.LeftButton:
                self.checkbox.click()
                return True
        return super().eventFilter(watched, event)


def elevate(widget, theme=None):
    """A restrained shadow on reading surfaces, never on captured image pixels."""
    widget.setProperty('softElevation', True)
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(22)
    effect.setOffset(0, 4)
    widget.setGraphicsEffect(effect)
    update_elevation(widget, theme)


def update_elevation(widget, theme=None):
    color = QColor(palette(theme)['accent'] if is_light(theme) else '#000000')
    color.setAlpha(18 if is_light(theme) else 36)
    widget.graphicsEffect().setColor(color)


def draw_navigation_icon(painter, index, rect, color):
    painter.save()
    painter.translate(rect.x(), rect.y())
    painter.scale(rect.width() / 24, rect.height() / 24)
    painter.setPen(QPen(QColor(color), 1.65, Qt.PenStyle.SolidLine,
                        Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    if index == 0:
        for x, y, dx, dy in ((4, 4, 6, 6), (20, 4, -6, 6), (4, 20, 6, -6), (20, 20, -6, -6)):
            painter.drawLine(x, y, x + dx, y); painter.drawLine(x, y, x, y + dy)
    elif index == 1:
        painter.drawRoundedRect(QRectF(3, 3, 13, 13), 3, 3)
        painter.drawRoundedRect(QRectF(9, 9, 12, 12), 3, 3)
        painter.drawLine(7, 7, 12, 7); painter.drawLine(13, 14, 18, 14)
        painter.drawLine(15, 12, 15, 18)
    elif index == 2:
        painter.drawRoundedRect(QRectF(4, 3, 16, 18), 3, 3)
        for y, right in ((8, 16), (12, 16), (16, 12)):
            painter.drawLine(8, y, right, y)
    elif index == 3:
        painter.drawEllipse(QRectF(3, 3, 18, 18))
        for x, y in ((9, 7), (15, 7), (7, 13), (14, 15)):
            painter.drawEllipse(QRectF(x - 1, y - 1, 2.5, 2.5))
    elif index == 5:
        for x, y in ((5, 9), (12, 15), (19, 7)):
            painter.drawLine(x, 3, x, y - 2)
            painter.drawLine(x, y + 2, x, 21)
            painter.drawEllipse(QRectF(x - 2, y - 2, 4, 4))
    else:
        painter.drawRoundedRect(QRectF(4, 4, 16, 16), 3, 3)
        painter.drawLine(8, 9, 16, 9); painter.drawLine(12, 9, 12, 16)
        painter.drawLine(10, 16, 14, 16)
    painter.restore()


class NavigationDelegate(QStyledItemDelegate):
    """Paint a roomy navigation pill with real keyboard / selection semantics."""
    def sizeHint(self, option, index):
        return QSize(154, 52)

    def paint(self, painter, option, index):
        colors = palette(self.parent().property('themeName'))
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(option.rect).adjusted(2, 3, -2, -5)
        painter.setPen(Qt.PenStyle.NoPen)
        if selected:
            shadow = QColor(colors['accent']); shadow.setAlpha(24)
            painter.setBrush(shadow); painter.drawRoundedRect(rect.translated(0, 3), 11, 11)
            gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
            gradient.setColorAt(0, QColor(colors['accent']))
            gradient.setColorAt(1, QColor(colors['accent']).lighter(115))
            painter.setBrush(gradient); painter.drawRoundedRect(rect, 10, 10)
        elif hovered:
            painter.setBrush(QColor(colors['soft'])); painter.drawRoundedRect(rect, 10, 10)
        color = colors['on_accent'] if selected else colors['muted']
        draw_navigation_icon(painter, index.row(), QRectF(rect.x() + 13, rect.center().y() - 10, 20, 20), color)
        font = option.font; font.setPixelSize(13); font.setBold(selected)
        painter.setFont(font); painter.setPen(QColor(color))
        text_rect = rect.adjusted(44, 0, -6, 0)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextWordWrap, index.data())
        if option.state & QStyle.StateFlag.State_HasFocus:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(colors['on_accent'] if selected else colors['accent']), 1, Qt.PenStyle.DotLine))
            painter.drawRoundedRect(rect.adjusted(3, 3, -3, -3), 8, 8)
        painter.restore()


def theme_preview(colors):
    """Miniature of the actual sidebar / reading surface, using the theme palette."""
    pixmap = QPixmap(240, 92); pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(colors[0])); painter.drawRoundedRect(QRectF(0, 0, 240, 92), 12, 12)
    painter.setBrush(QColor(colors[1])); painter.drawRoundedRect(QRectF(6, 6, 49, 80), 7, 7)
    painter.drawRoundedRect(QRectF(64, 26, 170, 60), 7, 7)
    painter.setBrush(QColor(colors[8])); painter.drawRoundedRect(QRectF(12, 25, 37, 11), 4, 4)
    painter.drawRoundedRect(QRectF(202, 9, 31, 10), 4, 4)
    painter.setBrush(QColor(colors[5])); painter.drawRoundedRect(QRectF(64, 11, 53, 5), 2, 2)
    for x, y, width in ((13, 47, 26), (13, 62, 20), (75, 38, 140), (75, 51, 121), (75, 64, 78)):
        painter.drawRoundedRect(QRectF(x, y, width, 3), 1.5, 1.5)
    painter.end()
    return QIcon(pixmap)


class InlineMessage(QLabel):
    def setText(self, text):
        from ..i18n import tr
        text = tr(text)
        super().setText(text)
        self.setToolTip(text)
        self.setMaximumHeight(76)
        self.setVisible(bool(text))


class Toggle(QCheckBox):
    def __init__(self, text='', parent=None):
        super().__init__(text, parent)
        self.setAccessibleName(text)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._position = 0.
        self.animation = QPropertyAnimation(self, b'position', self)
        self.animation.setDuration(140)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.toggled.connect(self._animate)

    def _get_position(self):
        return self._position

    def _set_position(self, value):
        self._position = value
        self.update()

    position = Property(float, _get_position, _set_position)

    def _animate(self, checked):
        self.animation.stop()
        if not self.isVisible():
            self._set_position(float(checked))
            return
        self.animation.setStartValue(self._position)
        self.animation.setEndValue(1. if checked else 0.)
        self.animation.start()

    def sizeHint(self):
        return QSize(48, 30)

    def hitButton(self, point):
        return self.rect().contains(point)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        colors = palette(self.property('themeName'))
        if not self.isVisible() or self.animation.state() != QPropertyAnimation.State.Running:
            self._position = float(self.isChecked())
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(colors['accent'] if self.isChecked() else colors['border']))
        painter.drawRoundedRect(QRectF(2, 4, 42, 24), 12, 12)
        painter.setBrush(QColor('#ffffff'))
        painter.drawEllipse(QRectF(5 + self._position * 18, 7, 18, 18))
        if self.hasFocus():
            painter.setPen(QColor(colors['accent']))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(QRectF(0, 2, 46, 28), 14, 14)


PREFERENCES_STYLE = '''
QFrame#settingsSidebar { background: #22262f; border: none; border-radius: 18px; }
QListWidget#settingsNavigation { background: transparent; border: none; outline: none; font-size: 13px; color: #a2adc0; }
QListWidget#settingsNavigation::item { padding: 12px 10px; border-radius: 7px; margin: 2px 0; }
QListWidget#settingsNavigation::item:hover { background: #242932; color: #edf0f6; }
QListWidget#settingsNavigation::item:selected { background: #3a282b; color: #ffaca6; }
QWidget#settingsBody QFrame#card { background: #22262f; border: none; border-radius: 16px; }
QWidget#settingsBody QFrame#card[surfaceRole="hero"] { background: #3a282b; }
QWidget#settingsBody QLabel#title { font-size: 24px; }
QLabel#flowSummary { background: #22262f; color: #ffaca6; border-radius: 8px; padding: 8px 12px; font-size: 12px; }
QWidget#settingsBody QLabel#status { background: transparent; padding: 4px 0; border: none; }
QWidget#settingsBody QLineEdit, QWidget#settingsBody QPlainTextEdit, QWidget#settingsBody QComboBox, QWidget#settingsBody QSpinBox { background: #191d25; border: 1px solid rgba(127,127,127,22); border-radius: 9px; padding: 9px 11px; }
QWidget#settingsBody QLineEdit:hover, QWidget#settingsBody QComboBox:hover, QWidget#settingsBody QSpinBox:hover { border-color: #929caf; }
QWidget#settingsBody QLineEdit:focus, QWidget#settingsBody QPlainTextEdit:focus, QWidget#settingsBody QComboBox:focus, QWidget#settingsBody QSpinBox:focus { border: 1px solid #ff786f; }
QPushButton { border: 1px solid transparent; border-radius: 9px; }
QPushButton:focus { border: 1px solid #ff786f; }
QPushButton#primary { padding: 9px 17px; border-radius: 10px; }
QPushButton#primary:pressed { background: #754842; }
QPushButton#quiet { background: transparent; border: 1px solid transparent; padding: 7px 10px; color: #acb7cb; }
QPushButton#quiet:hover { background: #242932; color: #edf0f6; }
QPushButton#quiet:pressed { background: #3a282b; }
QLabel#savedState { color: #929caf; font-size: 11px; }
QWidget#readingPane { background: #22262f; border: none; border-radius: 16px; }
QWidget#readingPane[target="true"] { background: #22262f; }
QLabel#readingTag { color: #ffaca6; background: #3a282b; padding: 5px 10px; border-radius: 7px; font-size: 11px; }
QWidget#readingContent QPlainTextEdit { border: none; background: transparent; padding: 3px 0; }
QWidget#readingHeader { border: none; }
QWidget#readingHeader QComboBox { border: 1px solid rgba(127,127,127,30); background: #22262f; border-radius: 10px; }
QTabBar::tab { padding: 10px 13px; font-size: 13px; }
QSplitter::handle { background: transparent; height: 12px; }
QSplitter::handle:hover { background: #3a282b; }
'''

"""A frozen-screen translation workspace with an adjustable region and one toolbar."""
from ..i18n import tr
from statistics import median
from PySide6.QtCore import Qt, Signal, QRectF, QPointF, QSize
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QIcon, QPainter, QPen, QPixmap, QShortcut, QKeySequence
from .localized_widgets import QWidget, QFrame, QHBoxLayout, QLabel, QComboBox, QToolButton, QPushButton
from ..providers.catalog import PROVIDERS
from ..core.coordinates import pixel_crop
from .theme import control_icons, palette
from .language_picker import LanguageButton

ACCENT = '#ff5148'
ENGINE_NAMES = {'mymemory': 'MyMemory · 免费', 'ollama': 'Ollama · 本地',
                'compatible': '大模型接口', 'nvidia': 'NVIDIA NIM', 'google': 'Google 翻译', 'microsoft': '微软翻译',
                'deepl': 'DeepL', 'baidu': '百度翻译', 'youdao': '有道翻译', 'libre': 'LibreTranslate',
                'deepseek': 'DeepSeek', 'qwen': '通义千问', 'glm': '智谱 GLM', 'kimi': 'Kimi',
                'siliconflow': '硅基流动', 'openai': 'OpenAI', 'gemini': 'Gemini',
                'claude': 'Claude', 'grok': 'Grok', 'doubao': '豆包', 'hunyuan': '腾讯混元',
                'ernie': '文心一言', 'minimax': 'MiniMax'}


def tool_icon(name):
    pixmap = QPixmap(40, 40)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.scale(2, 2)
    painter.setPen(QPen(QColor(palette()['text']), 1.5))
    if name == 'copy':
        painter.drawRoundedRect(QRectF(6, 6, 10, 11), 1.5, 1.5)
        painter.drawLine(4, 13, 3, 13)
        painter.drawLine(3, 13, 3, 3)
        painter.drawLine(3, 3, 12, 3)
    elif name == 'popup':
        painter.drawRoundedRect(QRectF(3, 4, 14, 12), 1.5, 1.5)
        painter.drawLine(3, 8, 17, 8)
        painter.drawLine(12, 10, 15, 10)
        painter.drawLine(15, 10, 15, 13)
    elif name == 'edit':
        painter.drawLine(4, 15, 7, 14)
        painter.drawLine(7, 14, 16, 5)
        painter.drawLine(16, 5, 13, 2)
        painter.drawLine(13, 2, 4, 11)
        painter.drawLine(4, 11, 4, 15)
        painter.drawLine(4, 18, 17, 18)
    elif name == 'settings':
        for x, y in ((5, 6), (10, 13), (15, 8)):
            painter.drawLine(x, 3, x, 17)
            painter.setBrush(QColor(palette()['surface']))
            painter.drawEllipse(QPointF(x, y), 2, 2)
    elif name == 'close':
        painter.drawLine(5, 5, 15, 15)
        painter.drawLine(15, 5, 5, 15)
    elif name == 'pin':
        painter.drawRoundedRect(QRectF(3, 3, 14, 11), 2, 2)
        painter.drawLine(10, 14, 10, 18)
        painter.drawLine(7, 18, 13, 18)
    painter.end()
    return QIcon(pixmap)


def handles(rect):
    return [rect.topLeft(), QPointF(rect.center().x(), rect.top()), rect.topRight(),
            QPointF(rect.right(), rect.center().y()), rect.bottomRight(),
            QPointF(rect.center().x(), rect.bottom()), rect.bottomLeft(),
            QPointF(rect.left(), rect.center().y())]


def paint_handles(painter, rect):
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor(palette()['accent']), 1.3))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRect(rect)
    painter.setBrush(QColor('white'))
    for point in handles(rect):
        painter.drawEllipse(point, 4, 4)


class TranslationCanvas(QWidget):
    dismissed = Signal()
    provider_changed = Signal(str)
    languages_changed = Signal(str, str)
    retry = Signal()
    copy_requested = Signal()
    popup_requested = Signal()
    settings_requested = Signal()
    adjustment_started = Signal()
    selection_changed = Signal(object)
    pin_requested = Signal()
    workspace_requested = Signal(str)

    def __init__(self):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle(tr('SnapTrans · 截图翻译'))
        self.setMouseTracking(True)
        self.screenshot = None
        self.selection = QRectF()
        self.translation = ''
        self.text_regions = []
        self.background = QColor('white')
        self.foreground = QColor('#182026')
        self.source_font_px = 22
        self.font_adjustment = 0
        self.rendered_font_px = 0
        self.text_overflow = False
        self._drag = None
        self._dragging = False
        self.busy = False
        self.toolbar = QFrame(self)
        self.toolbar.setCursor(Qt.CursorShape.ArrowCursor)
        self.toolbar.setObjectName('translationBar')
        self.toolbar.setStyleSheet('''
            QFrame#translationBar { background: #25282e; border: 1px solid #50545c; border-radius: 12px; }
            QLabel { color: #dde1e9; font-size: 13px; background: transparent; }
            QToolButton { color: #e3e6ed; background: transparent; border: none; border-radius: 7px; padding: 4px; font-size: 13px; }
            QToolButton:hover { background: #3d414a; }
            QToolButton:checked { background: #554044; color: #ffaaa4; }
            QToolButton:disabled { color: #737a87; }
            QComboBox { color: #f0f1f5; background: #32363e; border: 1px solid #454952; border-radius: 7px; padding: 7px 10px; font-size: 13px; }
            QComboBox::drop-down { border: none; width: 20px; }
            QComboBox QAbstractItemView { background: #292d34; color: #f1f3f6; selection-background-color: #505663; padding: 5px; }
            QPushButton { background: #ff5148; color: white; border: none; border-radius: 8px; padding: 8px 16px; font-size: 13px; font-weight: 600; }
            QPushButton:hover { background: #ff685f; }
            QPushButton:disabled { background: #573d3d; color: #ccbab9; }
        ''' + control_icons())
        row = QHBoxLayout(self.toolbar)
        row.setContentsMargins(12, 9, 12, 9)
        row.setSpacing(8)
        self.languages = LanguageButton()
        self.languages.changed.connect(self.languages_changed)
        row.addWidget(self.languages)
        self.compare = QToolButton()
        self.compare.setText(tr('对照'))
        self.compare.setCheckable(True)
        self.compare.setToolTip(tr('查看截图原文 / 查看译文'))
        self.compare.toggled.connect(lambda: self.update())
        row.addWidget(self.compare)
        separator = QFrame()
        separator.setFixedSize(1, 24)
        separator.setStyleSheet('background: #4b4f58; border: none;')
        row.addWidget(separator)
        self.engine = QComboBox()
        self.engine.setMinimumWidth(150)
        self.engine.setMaximumWidth(205)
        for kind in PROVIDERS:
            self.engine.addItem(ENGINE_NAMES.get(kind, PROVIDERS[kind][0]), kind)
        self.engine.setToolTip(tr('切换引擎并用当前原文重新翻译'))
        self.engine.currentIndexChanged.connect(lambda: self.provider_changed.emit(self.engine.currentData()))
        row.addWidget(self.engine)
        self.ocr_button = QToolButton()
        self.ocr_button.setText(tr('文字提取'))
        self.ocr_button.clicked.connect(lambda: self.workspace_requested.emit('ocr'))
        row.addWidget(self.ocr_button)
        for name, tooltip, signal in (
            ('copy', tr('复制译文'), self.copy_requested),
            ('pin', tr('贴图 · 保留当前画面，可返回工作区'), self.pin_requested),
            ('edit', tr('查看或编辑原文'), self.popup_requested),
            ('popup', tr('切换到弹窗'), self.popup_requested),
            ('settings', tr('翻译设置'), self.settings_requested)):
            button = QToolButton()
            button.setIcon(tool_icon(name))
            button.setProperty('toolIconName', name)
            button.setIconSize(QSize(20, 20))
            button.setFixedSize(34, 34)
            button.setToolTip(tooltip)
            button.clicked.connect(signal)
            setattr(self, name + '_button', button)
            row.addWidget(button)
        self.translate_button = QPushButton(tr('重新翻译'))
        self.translate_button.clicked.connect(self.retry)
        row.addWidget(self.translate_button)
        self.close_button = QToolButton()
        self.close_button.setIcon(tool_icon('close'))
        self.close_button.setProperty('toolIconName', 'close')
        self.close_button.setIconSize(QSize(22, 22))
        self.close_button.setFixedSize(34, 34)
        self.close_button.setToolTip(tr('关闭 · Esc'))
        self.close_button.clicked.connect(self.dismissed)
        row.addWidget(self.close_button)
        self.message = QLabel(self)
        self.message.setCursor(Qt.CursorShape.ArrowCursor)
        self.message.setWordWrap(True)
        self.message.setStyleSheet('background: #25282e; color: #e1e5ed; border-radius: 6px; padding: 6px 10px; font-size: 12px;')
        self.message.hide()
        for button in self.toolbar.findChildren(QToolButton) + self.toolbar.findChildren(QPushButton):
            button.setCursor(Qt.CursorShape.PointingHandCursor)
        QShortcut(QKeySequence('Esc'), self, activated=self.dismissed.emit)

    def refresh_icons(self):
        for button in self.findChildren(QToolButton):
            name = button.property('toolIconName')
            if name:
                button.setIcon(tool_icon(name))

    @property
    def has_capture(self):
        return self.screenshot is not None and not self.screenshot.isNull()

    def attach_capture(self, screen, screenshot, selection):
        self.setGeometry(screen.geometry())
        self.screenshot = QPixmap(screenshot)
        self.selection = QRectF(selection).intersected(QRectF(self.rect()))
        self._sample_background()
        self._position_toolbar()
        self.update()

    def _sample_background(self):
        if not self.has_capture or self.selection.isEmpty():
            return
        image = self.screenshot.toImage()
        sx, sy = image.width() / self.width(), image.height() / self.height()
        samples = []
        # Median perimeter pixels resist dark glyphs and give clean flat-label fill.
        for fraction in (.08, .2, .35, .5, .65, .8, .92):
            x = self.selection.left() + self.selection.width() * fraction
            y = self.selection.top() + self.selection.height() * fraction
            for point in ((x, self.selection.top() + 2), (x, self.selection.bottom() - 2),
                          (self.selection.left() + 2, y), (self.selection.right() - 2, y)):
                ix = min(image.width() - 1, max(0, int(point[0] * sx)))
                iy = min(image.height() - 1, max(0, int(point[1] * sy)))
                color = image.pixelColor(ix, iy)
                samples.append((color.red(), color.green(), color.blue()))
        channels = [int(median(v[index] for v in samples)) for index in range(3)]
        self.background = QColor(*channels)
        self.foreground = QColor('#171b20' if sum(channels) > 390 else '#f7f8fa')

    def set_ocr_lines(self, result, frame):
        sx = self.selection.width() / frame.width_px
        sy = self.selection.height() / frame.height_px
        self.text_regions = []
        for line in result.lines:
            xs = [p[0] for p in line.polygon]
            ys = [p[1] for p in line.polygon]
            rect = QRectF(self.selection.x() + min(xs) * sx, self.selection.y() + min(ys) * sy,
                          (max(xs) - min(xs)) * sx, (max(ys) - min(ys)) * sy)
            self.text_regions.append(rect)
        if self.text_regions:
            self.source_font_px = max(12, min(42, median(rect.height() for rect in self.text_regions) * .95))
        self.update()

    def set_content(self, translation, busy=False):
        self.translation = translation
        self.busy = busy
        self.pin_button.setEnabled(not busy)
        self.copy_button.setEnabled(bool(translation))
        self.translate_button.setEnabled(not busy)
        self.translate_button.setText(tr('翻译中…') if busy else tr('重新翻译'))
        if not translation:
            self.compare.setChecked(False)
        self.update()

    def set_status(self, text):
        if self.busy:
            self.translate_button.setText(tr('识别中…') if text == tr('正在识别…') else tr('翻译中…'))
        if text in (tr('翻译完成'), tr('正在翻译…'), tr('正在识别…')):
            self.message.hide()
        else:
            self.message.setText(text)
            self.message.setFixedWidth(min(600, max(240, self.width() - 40)))
            self.message.adjustSize()
            self.message.show()
        self._position_toolbar()

    def _position_toolbar(self):
        self.languages.setVisible(self.width() >= 820)
        self.edit_button.setVisible(self.width() >= 680)
        self.toolbar.adjustSize()
        bar_width = self.toolbar.width()
        x = max(12, min(int(self.selection.center().x() - bar_width / 2), self.width() - bar_width - 12))
        y = int(self.selection.bottom() + 18)
        if y + self.toolbar.height() > self.height() - 12:
            y = int(self.selection.top() - self.toolbar.height() - 18)
        self.toolbar.move(x, max(12, y))
        self.message.move(x, min(self.height() - self.message.height() - 10,
                                self.toolbar.geometry().bottom() + 8))

    def paintEvent(self, event):
        if not self.has_capture:
            return
        painter = QPainter(self)
        painter.drawPixmap(self.rect(), self.screenshot)
        painter.fillRect(self.rect(), QColor(10, 13, 18, 125))
        painter.save()
        painter.setClipRect(self.selection)
        painter.drawPixmap(self.rect(), self.screenshot)
        if self.translation and not self.compare.isChecked() and not self._dragging:
            # Replace only the selected patch, preserving the rest of the screenshot.
            painter.fillRect(self.selection, self.background)
            self._paint_translation(painter)
        if hasattr(self, 'editor'):
            self.editor.paint(painter)
        painter.restore()
        paint_handles(painter, self.selection)

    def selected_pixmap(self):
        """Original pixels without selection handles, dimming, or translated text."""
        if not self.has_capture:
            return None
        left, top, right, bottom = pixel_crop(
            (self.selection.x(), self.selection.y(), self.selection.width(), self.selection.height()),
            (self.width(), self.height()), (self.screenshot.width(), self.screenshot.height()))
        return self.screenshot.copy(left, top, right - left, bottom - top)

    def rendered_selection(self, *, force_translation=False):
        """Export the visible patch while keeping original capture pixels separate."""
        pixmap = self.selected_pixmap()
        if pixmap is None or not self.translation or (self.compare.isChecked() and not force_translation):
            return pixmap
        # Paint in screen logical coordinates, explicitly accounting for source DPI.
        pixmap.setDevicePixelRatio(1)
        painter = QPainter(pixmap)
        painter.scale(pixmap.width() / self.selection.width(), pixmap.height() / self.selection.height())
        painter.translate(-self.selection.left(), -self.selection.top())
        painter.setClipRect(self.selection)
        painter.fillRect(self.selection, self.background)
        self._paint_translation(painter)
        painter.end()
        pixmap.setDevicePixelRatio(self.screenshot.devicePixelRatio())
        return pixmap

    def _paint_translation(self, painter):
        pad_x = min(10, max(3, self.selection.width() * .04))
        pad_y = min(6, max(2, self.selection.height() * .08))
        text_rect = self.selection.adjusted(pad_x, pad_y, -pad_x, -pad_y)
        flags = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextWordWrap
        font = QFont(self.font())
        font.setWeight(QFont.Weight.Medium)
        upper = max(9, min(42, round(self.source_font_px + self.font_adjustment)))
        size = upper
        for size in range(upper, 8, -1):
            font.setPixelSize(size)
            bounds = QFontMetricsF(font).boundingRect(text_rect, int(flags), self.translation)
            if bounds.height() <= text_rect.height() and bounds.width() <= text_rect.width() + 1:
                break
        self.rendered_font_px = size
        self.text_overflow = bounds.height() > text_rect.height() or bounds.width() > text_rect.width() + 1
        painter.setFont(font)
        painter.setPen(self.foreground)
        if self.text_overflow:
            flags = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap
        painter.drawText(text_rect, int(flags), self.translation)
        if self.text_overflow:
            badge = QRectF(text_rect.right() - 22, text_rect.bottom() - 13, 22, 13)
            painter.fillRect(badge, QColor(ACCENT))
            painter.setPen(QColor('white'))
            font.setPixelSize(12)
            painter.setFont(font)
            painter.drawText(badge, int(Qt.AlignmentFlag.AlignCenter), '…')
            self.popup_button.setToolTip(tr('选区较小，打开弹窗查看完整译文'))
        else:
            self.popup_button.setToolTip(tr('切换到弹窗'))

    def _hit_handle(self, point):
        for index, handle in enumerate(handles(self.selection)):
            if abs(handle.x() - point.x()) <= 8 and abs(handle.y() - point.y()) <= 8:
                return index
        return None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self.dismissed.emit()
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        point = event.position()
        hit = self._hit_handle(point)
        kind = hit if hit is not None else ('move' if self.selection.contains(point) else 'new')
        self._drag = (kind, QPointF(point), QRectF(self.selection))
        self._dragging = False

    def mouseMoveEvent(self, event):
        point = event.position()
        if not self._drag:
            hit = self._hit_handle(point)
            cursors = (Qt.CursorShape.SizeFDiagCursor, Qt.CursorShape.SizeVerCursor,
                       Qt.CursorShape.SizeBDiagCursor, Qt.CursorShape.SizeHorCursor)
            self.setCursor(cursors[hit % 4] if hit is not None else
                           (Qt.CursorShape.SizeAllCursor if self.selection.contains(point) else Qt.CursorShape.CrossCursor))
            return
        kind, start, original = self._drag
        delta = point - start
        if not self._dragging and abs(delta.x()) + abs(delta.y()) < 3:
            return
        if not self._dragging:
            self._dragging = True
            self.adjustment_started.emit()
        point.setX(max(0, min(point.x(), self.width())))
        point.setY(max(0, min(point.y(), self.height())))
        rect = QRectF(original)
        if kind == 'move':
            rect.moveLeft(max(0, min(original.left() + delta.x(), self.width() - rect.width())))
            rect.moveTop(max(0, min(original.top() + delta.y(), self.height() - rect.height())))
        elif kind == 'new':
            rect = QRectF(start, point).normalized()
        else:
            if kind in (0, 6, 7): rect.setLeft(point.x())
            if kind in (2, 3, 4): rect.setRight(point.x())
            if kind in (0, 1, 2): rect.setTop(point.y())
            if kind in (4, 5, 6): rect.setBottom(point.y())
            rect = rect.normalized()
        self.selection = rect.intersected(QRectF(self.rect()))
        self._position_toolbar()
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or not self._drag:
            return
        changed = self._dragging
        original = self._drag[2]
        self._drag = None
        self._dragging = False
        if changed:
            if self.selection.width() < 8 or self.selection.height() < 8:
                self.selection = original
            self.translation = ''
            self.text_regions = []
            self._sample_background()
            self._position_toolbar()
            self.selection_changed.emit(QRectF(self.selection))
        self.update()

    def closeEvent(self, event):
        self.dismissed.emit()
        event.accept()

    def release_capture(self):
        self.hide()
        self.screenshot = None

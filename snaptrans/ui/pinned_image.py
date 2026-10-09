from ..i18n import ui_format
from ..i18n import tr
from PySide6.QtCore import Qt, Signal, QPointF, QTimer
from PySide6.QtGui import QShortcut, QKeySequence, QColor, QPixmap
from .localized_widgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QApplication,
                               QComboBox, QLabel, QMenu, QColorDialog, QToolButton)
from .ocr_canvas import save_image
from .theme import apply_theme, STYLE, themed_css
from .pin_editor import PinDocument, PinSurface
from .brush_options import BrushOptions
from .annotation_icons import configure_tool_button


class PinnedImage(QWidget):
    languages_changed = Signal(str, str)
    """Editable desktop pin; original OCR session and image edits are independent."""
    workspace_requested = Signal(str)
    translate_requested = Signal()
    cancel_requested = Signal()
    closing = Signal()

    def __init__(self, pixmap, position, state=None, annotations=None, *,
                 original_pixmap=None, translated_pixmap=None, show_original=False):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setProperty('snaptrans_pin', True)
        self.setWindowTitle(tr('SnapTrans · 可编辑贴图'))
        self.state = state
        self.returning = False
        self.busy = False
        self.pan = QPointF()
        self.original_pixmap = QPixmap(original_pixmap) if original_pixmap is not None else None
        self.translated_pixmap = QPixmap(translated_pixmap) if translated_pixmap is not None else None
        self.showing_original = show_original or self.translated_pixmap is None
        self.document = PinDocument(pixmap)
        self.document.adaptive_mosaic = self.can_compare
        if annotations:
            self.document.operations = list(annotations[1])
            self.document.index = annotations[2]
            self.document.replay()
        self.zoom = 1.0
        layout = QVBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(6)
        self.image = PinSurface(self)
        self.image.changed.connect(self._resize_image)
        self.image.setToolTip(tr('移动工具：拖动图片 · 右下角缩放 · 滚轮缩放 · Ctrl+滚轮透明度 · 中键或双击还原 · 右键菜单'))
        layout.addWidget(self.image)
        # A separate owned tool window stays compact even for a very wide screenshot.
        self.toolbar = QWidget(self, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.toolbar.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.toolbar.setProperty('snaptrans_pin', True)
        self.toolbar.setObjectName('pinToolbar')
        self.toolbar.setWindowTitle(tr('SnapTrans · 贴图工具'))
        self.toolbar.setCursor(Qt.CursorShape.ArrowCursor)
        self.toolbar.setStyleSheet("""
            QWidget#pinToolbar { background: #25282e; border: 1px solid #464b56; border-radius: 10px; }
            QToolButton { color: #edf0f6; background: transparent; border: none; border-radius: 6px; padding: 6px 8px; font-size: 13px; }
            QToolButton:hover { background: #393e48; }
            QToolButton:checked { background: #604247; color: #ffb8af; }
            QToolButton:disabled { color: #697384; }
            QLabel { color: #a5afbf; font-size: 11px; background: transparent; border: none; }
        """)
        bar = QVBoxLayout(self.toolbar)
        bar.setContentsMargins(9, 7, 9, 7)
        bar.setSpacing(3)
        tools = QHBoxLayout()
        tools.setSpacing(2)
        bar.addLayout(tools)
        self.tool_picker = QComboBox(self)
        self.tool_picker.hide()
        self.tool_buttons = {}
        for title, tool in ((tr('移动'), 'move'), (tr('方框'), 'rect'), (tr('圆形'), 'ellipse'), (tr('箭头'), 'arrow'),
                            (tr('画笔'), 'pen'), (tr('文字'), 'text'), (tr('橡皮擦'), 'eraser'), (tr('马赛克'), 'mosaic'), (tr('裁剪'), 'crop')):
            self.tool_picker.addItem(title, tool)
            button = QToolButton()
            configure_tool_button(button, tool, title)
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, value=tool: self.set_tool(value))
            button.setToolTip(tr('只擦除标注，保留截图原始内容') if tool == 'eraser' else title)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            tools.addWidget(button)
            self.tool_buttons[tool] = button
        self.tool_picker.currentIndexChanged.connect(self._tool_changed)
        self.undo_button = self._button(tr('撤销'), self.undo, tools)
        self.redo_button = self._button(tr('重做'), self.redo, tools)
        configure_tool_button(self.undo_button, 'undo', tr('撤销 · Ctrl+Z'))
        configure_tool_button(self.redo_button, 'redo', tr('重做 · Ctrl+Y'))
        self.options = BrushOptions(self.toolbar)
        self.options.changed.connect(self._options_changed)
        bar.addWidget(self.options)
        actions = QHBoxLayout()
        actions.setSpacing(2)
        bar.addLayout(actions)
        self.info = QToolButton()
        self.info.setCursor(Qt.CursorShape.PointingHandCursor)
        self.info.clicked.connect(self.view_menu)
        self.info.setToolTip(tr('缩放 / 透明度；滚轮缩放，Ctrl+滚轮调整透明度'))
        actions.addWidget(self.info)
        self._button(tr('复制'), self.copy_image, actions)
        self._button(tr('保存'), self.save_image, actions)
        self.compare_button = self._button(tr('查看原文'), self.toggle_comparison, actions)
        self.compare_button.setEnabled(self.can_compare)
        self._update_comparison_button()
        self.workspace_button = self._button(tr('工作区'), lambda: self.workspace_requested.emit('resume'), actions)
        self.ocr_button = self._button(tr('提取原文'), lambda: self.workspace_requested.emit('ocr'), actions)
        self.translate_button = self._button(tr('翻译'), self.translate_requested.emit, actions)
        for button in (self.workspace_button, self.ocr_button, self.translate_button):
            button.setEnabled(state is not None)
            button.setToolTip(tr('关闭当前贴图并返回截图工作区；贴图编辑可先复制或保存'))
        self.ocr_button.setToolTip(tr('关闭当前贴图并返回文字工作区提取 / 编辑文字；仅查看原图请点“查看原文”'))
        self.translate_button.setToolTip(tr('在当前贴图完成识别和翻译，不返回工作区'))
        self._button(tr('更多'), lambda: self.context_menu(self.toolbar.mapToGlobal(self.toolbar.rect().center())), actions)
        self.close_button = self._button('×', self.close, actions)
        self.close_button.setToolTip(tr('关闭贴图 · Esc'))
        self.translation_row = QWidget()
        translation_layout = QHBoxLayout(self.translation_row)
        translation_layout.setContentsMargins(0, 2, 0, 0)
        self.engine = QComboBox()
        self.engine.setMaximumWidth(210)
        self.engine.setMinimumWidth(145)
        self.engine.hide()
        self.engine.setToolTip(tr('此贴图使用的翻译服务；选择后点击翻译'))
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setMaximumWidth(350)
        self.cancel_button = self._button(tr('取消'), self.cancel_requested.emit, translation_layout)
        tools.addWidget(self.engine)
        from .language_picker import LanguageButton
        self.languages = LanguageButton()
        self.languages.setVisible(state is not None)
        self.languages.changed.connect(self._languages_changed)
        actions.insertWidget(1, self.languages)
        translation_layout.insertWidget(0, self.status, 1)
        bar.addWidget(self.translation_row)
        self.translation_row.hide()
        self.cancel_button.hide()
        self._tool_changed()
        apply_theme(self)
        for key, slot in (('Esc', self.close), ('Ctrl+W', self.close), ('Ctrl+C', self.copy_image),
                          ('Ctrl+S', self.save_image), ('Ctrl+Z', self.undo), ('Ctrl+Y', self.redo),
                          ('1', self.rotate), ('3', self.flip), ('0', self.reset_view),
                          ('Tab', self.toggle_comparison),
                          ('Ctrl+0', self.actual_pixels), ('Ctrl+9', self.fit_screen),
                          ('+', lambda: self.set_zoom(self.zoom * 1.15)),
                          ('-', lambda: self.set_zoom(self.zoom / 1.15))):
            QShortcut(QKeySequence(key), self, activated=slot)
            QShortcut(QKeySequence(key), self.toolbar, activated=slot)
        self.move(position)
        self.fit_screen()

    def configure_engines(self, config):
        from ..providers.catalog import PROVIDERS
        from .translation_canvas import ENGINE_NAMES
        for kind, (name, _) in PROVIDERS.items():
            self.engine.addItem(tr(ENGINE_NAMES.get(kind, name)), kind)
        self.engine.setCurrentIndex(self.engine.findData(self.state.get('provider', config['translation']['provider'])))
        self.engine.show()
        self.languages.set_pair(self.state.get('source_lang', config['translation']['source_lang']),
                                self.state.get('target_lang', config['translation']['target_lang']))

    def _languages_changed(self, source, target):
        if self.busy or self.state is None:
            return
        self.state.update(source_lang=source, target_lang=target, translation='', translation_source='', compare=True)
        self.translated_pixmap = None
        self.showing_original = True
        self.document.set_base(self.original_pixmap)
        self.compare_button.setEnabled(False)
        self._update_comparison_button()
        self._resize_image()
        self.set_status(tr('语言已修改，点击翻译生成新的译文'))
        self.languages_changed.emit(source, target)

    def set_busy(self, busy):
        self.busy = busy
        self.translate_button.setEnabled(not busy and self.state is not None)
        self.engine.setEnabled(not busy)
        self.languages.setEnabled(not busy)
        self.cancel_button.setVisible(busy)
        self.translate_button.setText(tr('翻译中…') if busy else tr('重新翻译') if self.can_compare else tr('翻译'))
        self._position_toolbar()

    def set_status(self, text):
        text = tr(text)
        self.status.setText(text)
        self.translation_row.setVisible(bool(text))
        self._position_toolbar()
        if text.startswith(tr('翻译完成')):
            QTimer.singleShot(4000, self, lambda: self.set_status('') if self.status.text() == tr(text) else None)

    def set_translation(self, pixmap):
        self.translated_pixmap = QPixmap(pixmap)
        self.document.adaptive_mosaic = True
        self.showing_original = False
        self.document.set_base(pixmap)
        self.compare_button.setEnabled(self.can_compare)
        self._update_comparison_button()
        self._resize_image()

    def closeEvent(self, event):
        self.closing.emit()
        super().closeEvent(event)

    @property
    def pixmap(self):
        return self.document.export()

    @property
    def can_compare(self):
        return (self.original_pixmap is not None and self.translated_pixmap is not None
                and not self.original_pixmap.isNull() and not self.translated_pixmap.isNull()
                and self.original_pixmap.size() == self.translated_pixmap.size())

    def _update_comparison_button(self):
        self.compare_button.setText(tr('查看译文') if self.showing_original and self.can_compare else tr('查看原文'))
        self.compare_button.setToolTip(tr('在贴图当前位置切换原图 / 译文，保留缩放与标注 · Tab')
                                      if self.can_compare else tr('当前就是原始截图；翻译后贴图即可切换原文 / 译文'))
        self.setWindowTitle(tr('SnapTrans · 贴图 · ') + (tr('原文') if self.showing_original else tr('译文')))

    def toggle_comparison(self):
        if not self.can_compare or self.image.points:
            return
        self.showing_original = not self.showing_original
        self.document.set_base(self.original_pixmap if self.showing_original else self.translated_pixmap)
        self._update_comparison_button()
        self._resize_image()

    @staticmethod
    def _button(title, slot, row):
        button = QToolButton()
        button.setText(title)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(slot)
        row.addWidget(button)
        return button

    def set_tool(self, tool):
        self.tool_picker.setCurrentIndex(self.tool_picker.findData(tool))

    def _tool_changed(self):
        tool = self.tool_picker.currentData()
        self.image.set_tool(tool)
        self.options.set_tool(tool)
        for name, button in self.tool_buttons.items():
            button.setChecked(name == tool)
        self._position_toolbar()

    def _options_changed(self):
        self.image.color = self.options.color
        self.image.stroke_width = self.options.values['line']
        self.image.update_cursor()
        self.image.update()

    def showEvent(self, event):
        super().showEvent(event)
        self._position_toolbar()
        self.toolbar.show()

    def hideEvent(self, event):
        self.toolbar.hide()
        super().hideEvent(event)

    def moveEvent(self, event):
        super().moveEvent(event)
        if hasattr(self, 'toolbar'):
            self._position_toolbar()

    def _position_toolbar(self):
        available = self.screen().availableGeometry()
        self.toolbar.adjustSize()
        width, height = self.toolbar.width(), self.toolbar.height()
        x = max(available.left(), min(self.x() + (self.width() - width) // 2, available.right() - width + 1))
        y = self.y() + self.height() + 6
        if y + height > available.bottom() + 1:
            y = self.y() - height - 6
        self.toolbar.move(x, max(available.top(), min(y, available.bottom() - height + 1)))

    def choose_color(self):
        self.options.set_tool(self.image.tool, force=True)
        self._position_toolbar()

    def undo(self):
        self.image.points = []
        self.document.undo()
        self._resize_image()

    def redo(self):
        self.document.redo()
        self._resize_image()

    def rotate(self):
        self.image.points = []
        self.document.apply(('rotate', [], '', 0, ''))
        self._resize_image()

    def flip(self):
        self.image.points = []
        self.document.apply(('flip', [], '', 0, ''))
        self._resize_image()

    def reset_view(self):
        self.pan = QPointF()
        self.setWindowOpacity(1.)
        self.set_zoom(1.)

    def actual_pixels(self):
        self.pan = QPointF()
        self.set_zoom(self.document.ratio / self.devicePixelRatioF())

    def fit_screen(self):
        available = self.screen().availableGeometry()
        logical = self.document.current.size() / self.document.ratio
        self.pan = QPointF()
        self.set_zoom(min(1., (available.width() - 8) / logical.width(), (available.height() - 8) / logical.height()))

    def set_zoom(self, zoom):
        self.zoom = max(.1, min(5., zoom))
        self._resize_image()

    def copy_image(self):
        QApplication.clipboard().setPixmap(self.pixmap)

    def save_image(self):
        result = save_image(self, self.pixmap)
        if result is False:
            self.info.setText(tr('保存失败，请选择可写目录后重试'))

    def context_menu(self, position):
        menu = QMenu(self)
        menu.setStyleSheet(themed_css(STYLE))
        for title, slot in ((tr('复制图片\tCtrl+C'), self.copy_image), (tr('保存图片\tCtrl+S'), self.save_image),
                            (tr('撤销\tCtrl+Z'), self.undo), (tr('重做\tCtrl+Y'), self.redo),
                            (tr('旋转 90°\t1'), self.rotate), (tr('水平翻转\t3'), self.flip),
                            (tr('原始像素 1:1\tCtrl+0'), self.actual_pixels), (tr('适应屏幕\tCtrl+9'), self.fit_screen),
                            (tr('还原大小与透明度\t0'), self.reset_view)):
            menu.addAction(title, slot)
        menu.addSeparator()
        compare = menu.addAction(self.compare_button.text() + '\tTab', self.toggle_comparison)
        compare.setEnabled(self.can_compare)
        menu.addSeparator()
        menu.addAction(tr('工具大小与颜色'), self.choose_color)
        menu.addSeparator()
        menu.addAction(tr('关闭贴图\tEsc'), self.close)
        menu.exec(position)
        menu.deleteLater()

    def view_menu(self):
        menu = QMenu(self)
        menu.setStyleSheet(themed_css(STYLE))
        menu.addAction(ui_format('{} × {}{}', self.document.current.width(), self.document.current.height(), tr(' 原始像素'))).setEnabled(False)
        menu.addAction(tr('原始像素 1:1 · Ctrl+0'), self.actual_pixels)
        menu.addAction(tr('适应屏幕 · Ctrl+9'), self.fit_screen)
        menu.exec(self.info.mapToGlobal(self.info.rect().bottomLeft()))
        menu.deleteLater()

    def update_info(self):
        actual_zoom = self.zoom * self.devicePixelRatioF() / self.document.ratio
        self.info.setText(f'{round(actual_zoom * 100)}% · {round(self.windowOpacity() * 100)}%')
        self.info.setToolTip(ui_format('{}{} × {}{}', tr('原图 '), self.document.current.width(), self.document.current.height(), tr(' px；显示像素比例 / 透明度\nCtrl+0 原始像素，Ctrl+9 适应屏幕；放大后 Alt+拖动查看图片')))

    def _resize_image(self):
        available = self.screen().availableGeometry()
        logical = self.document.current.size() / self.document.ratio
        width, height = max(1, round(logical.width() * self.zoom)), max(1, round(logical.height() * self.zoom))
        self.image.setFixedSize(max(24, min(width, available.width() - 8)), max(24, min(height, available.height() - 8)))
        self.undo_button.setEnabled(self.document.index > 0)
        self.redo_button.setEnabled(self.document.index < len(self.document.operations))
        self.layout().activate()
        self.adjustSize()
        self.move(max(available.left(), min(self.x(), available.right() - self.width() + 1)),
                  max(available.top(), min(self.y(), available.bottom() - self.height() + 1)))
        self.image.update()
        self.image.update_cursor()
        self.update_info()
        self._position_toolbar()

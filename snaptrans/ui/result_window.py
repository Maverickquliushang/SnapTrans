from PySide6.QtCore import Qt, Signal, QRectF
from PySide6.QtGui import QShortcut, QKeySequence, QPixmap
from .localized_widgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QPlainTextEdit, QPushButton, QApplication, QCheckBox, QComboBox, QMenu, QDialog, QScrollArea, QSplitter, QProgressBar)
from ..providers.catalog import PROVIDERS, WEB_PROVIDERS
from .translation_canvas import TranslationCanvas
from .ocr_canvas import OcrCanvas
from .theme import apply_theme, card, label, style_tree
from .preferences_shell import PREFERENCES_STYLE
from .language_picker import LanguagePair
from ..languages import language_name
from ..i18n import tr, text_source


class StatusLabel(QLabel):
    changed = Signal()

    def setText(self, text):
        text = tr(text)
        super().setText(text)
        self.setToolTip(text)
        self.changed.emit()


class ResultWindow(QWidget):
    closed = Signal()
    cancel_requested = Signal()
    retry = Signal(str)
    provider_changed = Signal(str)
    languages_changed = Signal(str, str)
    open_settings = Signal()
    selection_changed = Signal(object)
    adjustment_started = Signal()
    extract_requested = Signal()
    ocr_translate_requested = Signal()
    pin_requested = Signal()
    workspace_requested = Signal(str)

    def __init__(self, settings, config=None, ocr_mode=False):
        super().__init__(None, Qt.WindowType.Window)
        self.setWindowTitle(tr('SnapTrans · 截图翻译'))
        self.raw_text = ''
        self.edit_text = ''
        self.translation_source = ''
        self.busy = False
        self.ocr_mode = ocr_mode
        self.anchor = None
        self.anchor_screen = None
        self.display_mode = settings.get('display_mode', 'popup')
        self.resize(720, 660)
        self.setMinimumSize(480, 320)
        self.status = StatusLabel(tr('正在识别…'))
        self.status.setWordWrap(True)
        self.status.setMaximumHeight(54)
        self.original = QPlainTextEdit()
        self.original.setPlaceholderText(tr('识别后的原文；可修改后重新翻译'))
        self.translated = QPlainTextEdit()
        self.translated.setReadOnly(True)
        self.translated.setPlaceholderText(tr('译文'))
        self.pin = QCheckBox(tr('置顶'))
        self.pin.setChecked(settings['always_on_top'])
        self.pin.toggled.connect(self._pin)
        self._pin(settings['always_on_top'], show=False)
        font = self.original.font()
        font.setPointSize(settings['font_size'])
        self.original.setFont(font)
        self.translated.setFont(font)
        self.overlay = OcrCanvas()
        self.overlay.set_mode(ocr_mode)
        self.overlay.setFont(font)
        self._connect_canvas()
        self.engine = QComboBox()
        self.engine.setToolTip(tr('选择其他引擎后，会用当前原文重新翻译，无需再截图'))
        self.view_mode = QComboBox()
        self.view_mode.addItem(tr('阅读弹窗'), 'popup')
        self.view_mode.addItem(tr('截图工作区'), 'overlay')
        self.view_mode.setCurrentIndex(self.view_mode.findData(self.display_mode))
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 18, 20, 12)
        outer.setSpacing(8)
        header_widget = QWidget()
        header_widget.setObjectName('readingHeader')
        layout = QVBoxLayout(header_widget)
        layout.setContentsMargins(0, 0, 0, 12)
        layout.setSpacing(10)
        outer.addWidget(header_widget)
        header = QHBoxLayout()
        header.addWidget(label(tr('阅读与翻译'), 'title'), 1)
        header.addWidget(self.pin)
        self.close_button = QPushButton(tr('关闭'))
        self.close_button.setObjectName('quiet')
        header.addWidget(self.close_button)
        layout.addLayout(header)
        engine_row = QHBoxLayout()
        engine_row.addWidget(self.engine, 1)
        engine_row.addWidget(self.view_mode)
        layout.addLayout(engine_row)
        trans = (config or {}).get('translation', {})
        self.language_pair = LanguagePair(trans.get('source_lang', 'en'), trans.get('target_lang', 'zh-CN'))
        self.language_pair.changed.connect(self._languages_changed)
        self.overlay.languages_changed.connect(self._languages_changed)
        layout.addWidget(self.language_pair)
        self.status.setObjectName('status')
        self.status.setStyleSheet('QLabel { background: transparent; padding: 2px 0; font-size: 12px; }')
        outer.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(3)
        self.progress.setStyleSheet('QProgressBar {border:none; background:#22262f;} QProgressBar::chunk {background:#f6534b;}')
        outer.addWidget(self.progress)
        self.options = QWidget()
        row = QHBoxLayout(self.options)
        row.setContentsMargins(0, 0, 0, 0)
        self.more_button = QPushButton(tr('更多操作 ⋯'))
        self.more_menu = QMenu(self)
        self.more_menu.addAction(tr('查看识别记录（原始换行）'), self.show_ocr_record)
        self.web_action = self.more_menu.addAction(tr('复制原文并打开翻译网页'), self.open_web_translation)
        self.more_button.setMenu(self.more_menu)
        content = QWidget()
        content.setObjectName('readingContent')
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        self.reading_split = QSplitter(Qt.Orientation.Vertical)
        self.reading_split.setChildrenCollapsible(False)
        content_layout.addWidget(self.reading_split)
        outer.addWidget(content, 1)
        self.copy_source = QPushButton(tr('复制原文'))
        self.copy_target = QPushButton(tr('复制译文'))
        self.retry_button = QPushButton(tr('重新翻译'))
        self.retry_button.setObjectName('primary')
        for title, editor, button, translated in ((tr('原文 · 可编辑'), self.original, self.copy_source, False),
                                                  (tr('译文'), self.translated, self.copy_target, True)):
            pane = QWidget()
            pane.setObjectName('readingPane')
            pane.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            pane_layout = QVBoxLayout(pane)
            pane_layout.setContentsMargins(16, 10, 16, 14)
            pane_layout.setSpacing(8)
            pane_header = QHBoxLayout()
            tag = label(title, 'readingTag')
            if translated:
                self.translation_tag = tag
            pane_header.addWidget(tag)
            pane_header.addStretch()
            pane_header.addWidget(button)
            if translated:
                pane_header.addWidget(self.retry_button)
            pane_layout.addLayout(pane_header)
            pane_layout.addWidget(editor, 1)
            editor.setMinimumHeight(40)
            self.reading_split.addWidget(pane)
        self.reading_split.setStretchFactor(0, 2)
        self.reading_split.setStretchFactor(1, 3)
        self.reading_split.setSizes([180, 280])
        last_row = QHBoxLayout()
        self.edit_button = QPushButton(tr('查看 / 编辑原文'))
        self.ocr_workspace_button = QPushButton(tr('文字工作区'))
        self.translation_workspace_button = QPushButton(tr('原位翻译'))
        self.pin_image_button = QPushButton(tr('贴图'))
        settings_button = QPushButton(tr('设置'))
        self.more_menu.addAction(tr('返回文字工作区'), lambda: self.workspace_requested.emit('ocr'))
        self.ocr_workspace_button.hide()
        self.translation_workspace_button.setText(tr('工作区'))
        self.more_button.setText(tr('更多'))
        last_row.addWidget(self.more_button)
        last_row.addStretch()
        for button in (self.translation_workspace_button, self.pin_image_button, settings_button):
            last_row.addWidget(button)
        outer.addLayout(last_row)
        for button in (self.copy_source, self.copy_target, self.more_button, self.translation_workspace_button,
                       self.pin_image_button, settings_button):
            button.setObjectName('quiet')
        self.edit_button.hide()
        self.ocr_workspace_button.clicked.connect(lambda: self.workspace_requested.emit('ocr'))
        self.translation_workspace_button.clicked.connect(lambda: self.workspace_requested.emit('translate'))
        self.pin_image_button.clicked.connect(self.pin_requested)
        self.copy_source.clicked.connect(lambda: self._copy(self.source_text()))
        self.copy_target.clicked.connect(lambda: self._copy(self.translated.toPlainText()))
        self.retry_button.clicked.connect(lambda: self.retry.emit(self.source_text()))
        self.close_button.clicked.connect(self.close)
        settings_button.clicked.connect(self.open_settings)
        self.original.textChanged.connect(self._edited)
        self.translated.textChanged.connect(self._sync_overlay)
        self.status.changed.connect(lambda: self.overlay.set_status(text_source(self.status)))
        self.view_mode.currentIndexChanged.connect(self._change_view)
        self.engine.currentIndexChanged.connect(self._change_engine)
        self.copy_target.setEnabled(False)
        QShortcut(QKeySequence('Esc'), self, activated=self.close)
        apply_theme(self)
        self.setProperty('themeSource', self.property('themeSource') + PREFERENCES_STYLE)
        style_tree(self)
        self.refresh_profiles(config or {'translation': {'provider': 'mymemory'}})
        self.set_languages(*self.language_pair.pair())
        self.set_busy(True)
        self._apply_view()

    def set_languages(self, source, target):
        self.language_pair.set_pair(source, target)
        self.overlay.languages.set_pair(source, target)
        self.translation_tag.setText(tr('译文') + ' · ' + language_name(target))

    def _languages_changed(self, source, target):
        if self.busy:
            return
        self.set_languages(source, target)
        self.translated.clear()
        self.translation_source = ''
        self.copy_target.setEnabled(False)
        self.languages_changed.emit(source, target)

    def _connect_canvas(self):
        self.overlay.dismissed.connect(self.close)
        self.overlay.copy_requested.connect(lambda: self._copy(self.translated.toPlainText()))
        self.overlay.retry.connect(lambda: self.retry.emit(self.source_text()))
        self.overlay.popup_requested.connect(lambda: self.view_mode.setCurrentIndex(0))
        self.overlay.settings_requested.connect(self.open_settings)
        self.overlay.provider_changed.connect(self._canvas_engine_changed)
        self.overlay.adjustment_started.connect(self.adjustment_started)
        self.overlay.selection_changed.connect(self.selection_changed)
        self.overlay.pin_requested.connect(self.pin_requested)
        self.overlay.workspace_requested.connect(self.workspace_requested)
        self.overlay.extract_requested.connect(self.extract_requested)
        self.overlay.translate_requested.connect(self.ocr_translate_requested)
        self.overlay.text_edited.connect(self._ocr_edited)
        self.overlay.cancel_requested.connect(self.cancel_requested)
        self.destroyed.connect(self.overlay.deleteLater)

    def refresh_profiles(self, config):
        current = self.engine.currentData() or config['translation']['provider']
        self.engine.blockSignals(True)
        self.engine.clear()
        for kind, (label, _) in PROVIDERS.items():
            self.engine.addItem(tr(label), kind)
        self.engine.setCurrentIndex(self.engine.findData(current))
        self.engine.blockSignals(False)
        self.web_action.setVisible(current in WEB_PROVIDERS)
        self.overlay.engine.blockSignals(True)
        self.overlay.engine.setCurrentIndex(self.overlay.engine.findData(current))
        self.overlay.engine.blockSignals(False)

    def capture_state(self):
        canvas = self.overlay
        return dict(screen=self.anchor_screen, screenshot=QPixmap(canvas.screenshot),
                    selection=QRectF(canvas.selection), raw=self.raw_text, source=self.source_text(),
                    translation=self.translated.toPlainText(), translation_source=self.translation_source,
                    provider=self.engine.currentData(), ocr_mode=self.ocr_mode,
                    source_lang=self.language_pair.pair()[0], target_lang=self.language_pair.pair()[1],
                    source_font_px=canvas.source_font_px, compare=canvas.compare.isChecked(),
                    status=text_source(self.status), annotations=canvas.editor.snapshot())

    def restore_state(self, state):
        self.attach_capture(state['screen'], state['screenshot'], state['selection'])
        geometry = state['screen'].geometry()
        self.place_near(state['selection'].translated(geometry.x(), geometry.y()), state['screen'])
        self.engine.blockSignals(True)
        self.engine.setCurrentIndex(self.engine.findData(state['provider']))
        self.engine.blockSignals(False)
        self.refresh_profiles({'translation': {'provider': state['provider']}})
        self.set_languages(state.get('source_lang', 'en'), state.get('target_lang', 'zh-CN'))
        self.set_busy(False)
        self.set_original(state['raw'], state['source'])
        self.translated.setPlainText(state['translation'])
        self.translation_source = state['translation_source']
        self.copy_target.setEnabled(bool(state['translation']))
        self.overlay.source_font_px = state['source_font_px']
        self.overlay.compare.setChecked(state['compare'])
        self.overlay.editor.restore(state.get('annotations'))
        self.status.setText(state['status'])

    def set_workspace_mode(self, mode):
        """Swap the tools, retaining the same original capture, edits and translation."""
        ocr_mode = mode == 'ocr'
        self.ocr_mode = ocr_mode
        self.overlay.set_mode(ocr_mode)
        self._sync_overlay()
        self.view_mode.setCurrentIndex(self.view_mode.findData('overlay'))
        self.show()
        self.activateWindow()

    def update_preferences(self, config):
        self.refresh_profiles(config)
        pair = (config['translation']['source_lang'], config['translation']['target_lang'])
        if not self.busy and pair != self.language_pair.pair():
            self._languages_changed(*pair)
        settings = config['window']
        self.pin.setChecked(settings['always_on_top'])
        for editor in (self.original, self.translated):
            font = editor.font()
            font.setPointSize(settings['font_size'])
            editor.setFont(font)
        self.view_mode.setCurrentIndex(self.view_mode.findData(settings['display_mode']))

    def source_text(self):
        return self.original.toPlainText()

    def _change_engine(self):
        kind = self.engine.currentData()
        self.web_action.setVisible(kind in WEB_PROVIDERS)
        if kind:
            self.overlay.engine.blockSignals(True)
            self.overlay.engine.setCurrentIndex(self.overlay.engine.findData(kind))
            self.overlay.engine.blockSignals(False)
            self.provider_changed.emit(kind)

    def _canvas_engine_changed(self, kind):
        self.engine.setCurrentIndex(self.engine.findData(kind))

    def _pin(self, enabled, show=True):
        visible = QWidget.isVisible(self)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, enabled)
        if show and visible:
            QWidget.show(self)

    def open_web_translation(self):
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        from ..providers.web_translation import website_url
        if self.engine.currentData() in WEB_PROVIDERS and self.source_text().strip():
            from ..core.models import AppError
            try:
                url = website_url(self.engine.currentData(), self.source_text(), *self.language_pair.pair())
            except AppError as error:
                self.status.setText(error.user_message)
                return
            QApplication.clipboard().setText(self.source_text())
            QDesktopServices.openUrl(QUrl(url))
            self.status.setText(tr('原文已复制并打开网页；若未自动填入，可在网页中粘贴。'))

    def _copy(self, text):
        if text:
            QApplication.clipboard().setText(text)
            self.status.setText(tr('已复制到剪贴板'))

    def _edited(self):
        if self.ocr_mode:
            self.overlay.set_ocr_text(self.original.toPlainText(), reveal=not self.overlay.ocr_panel.isHidden())
        if self.translated.toPlainText():
            self.status.setText(tr('原文已修改，译文尚未更新'))

    def _ocr_edited(self, text):
        self.original.blockSignals(True)
        self.original.setPlainText(text)
        self.original.blockSignals(False)
        self.edit_text = text

    def show_translation_popup(self):
        self.view_mode.setCurrentIndex(0)
        self.show()
        self.activateWindow()

    def show_ocr_record(self):
        dialog = QDialog(self)
        dialog.setWindowTitle(tr('SnapTrans · 识别记录'))
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.resize(560, 420)
        layout = QVBoxLayout(dialog)
        layout.addWidget(label(tr('识别记录'), 'title'))
        layout.addWidget(label(tr('保留 OCR 最初的换行，方便核对漏字。此处只读，不影响原文编辑或重新翻译。')))
        editor = QPlainTextEdit(self.raw_text)
        editor.setReadOnly(True)
        layout.addWidget(editor)
        close = QPushButton(tr('关闭'))
        close.clicked.connect(dialog.close)
        layout.addWidget(close)
        apply_theme(dialog)
        self.ocr_record_dialog = dialog
        dialog.show()

    def set_busy(self, busy):
        self.busy = busy
        self.language_pair.setEnabled(not busy)
        self.overlay.languages.setEnabled(not busy)
        if busy:
            self.translated.clear()
            self.copy_target.setEnabled(False)
        self.original.setReadOnly(busy)
        self.retry_button.setEnabled(not busy)
        self.retry_button.setText(tr('翻译中…') if busy else tr('重新翻译'))
        self.progress.setVisible(busy)
        self.pin_image_button.setEnabled(not busy and self.overlay.has_capture)
        self.engine.setEnabled(bool(self.source_text()))
        self.overlay.engine.setEnabled(bool(self.source_text()))
        self._sync_overlay()

    def set_original(self, raw, cleaned):
        self.raw_text = raw
        self.edit_text = cleaned
        self.original.blockSignals(True)
        self.original.setPlainText(cleaned)
        self.original.blockSignals(False)
        self.original.setReadOnly(self.busy)
        if self.ocr_mode:
            self.overlay.set_ocr_text(cleaned)
        self.engine.setEnabled(bool(cleaned))
        self.overlay.engine.setEnabled(bool(cleaned))

    def set_translation(self, result):
        self.translation_source = self.source_text()
        self.translated.setPlainText(result.text)
        self.copy_target.setEnabled(True)
        self.set_busy(False)
        self.status.setText(tr('译文可能不完整，请缩小选区重试') if result.finish_reason == 'length' else tr('翻译完成'))

    def _sync_overlay(self):
        self.overlay.set_content(self.translated.toPlainText(), self.busy)
        self.overlay.set_status(text_source(self.status))

    def _change_view(self):
        self.display_mode = self.view_mode.currentData()
        visible = self.isVisible()
        super().hide()
        self.overlay.hide()
        self._apply_view()
        if visible:
            self.show()

    def _apply_view(self):
        self.edit_button.hide()
        self.layout().activate()
        if self.anchor is not None:
            self._position()
        self._sync_overlay()

    def attach_capture(self, screen, screenshot, selection):
        self.overlay.attach_capture(screen, screenshot, selection)
        self.pin_image_button.setEnabled(not self.busy)

    def set_ocr_geometry(self, result, frame):
        self.overlay.set_ocr_lines(result, frame)

    def place_near(self, selection, screen):
        self.anchor = QRectF(selection)
        self.anchor_screen = screen
        self._apply_view()

    def _position(self):
        screen, selection = self.anchor_screen, self.anchor
        area = screen.availableGeometry()
        self.resize(min(self.width(), area.width()), min(self.height(), area.height()))
        x, y = int(selection.right() + 12), int(selection.top())
        if x + self.width() > area.right() + 1:
            x, y = int(selection.left()), int(selection.bottom() + 12)
        x = max(area.left(), min(x, area.right() + 1 - self.width()))
        y = max(area.top(), min(y, area.bottom() + 1 - self.height()))
        self.move(x, y)

    def show(self):
        if self.display_mode == 'overlay' and self.overlay.has_capture:
            super().hide()
            self.overlay.show()
            self.overlay.raise_()
        else:
            self.overlay.hide()
            super().show()

    def isVisible(self):
        return super().isVisible() or self.overlay.isVisible()

    def activateWindow(self):
        if self.overlay.isVisible():
            self.overlay.activateWindow()
        else:
            super().activateWindow()

    def hide(self):
        self.overlay.hide()
        super().hide()

    def hideEvent(self, event):
        self.overlay.hide()
        super().hideEvent(event)

    def closeEvent(self, event):
        self.overlay.release_capture()
        self.closed.emit()
        super().closeEvent(event)

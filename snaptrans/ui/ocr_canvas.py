"""Screenshot actions and an optional local OCR panel on the frozen capture."""
from ..i18n import tr
from PySide6.QtCore import Qt, Signal, QRectF, QSize
from .localized_widgets import QFrame, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QPlainTextEdit, QApplication, QFileDialog
from .translation_canvas import TranslationCanvas, tool_icon
from .workspace_editor import WorkspaceEditor
from PySide6.QtGui import QShortcut, QKeySequence
from .localized_widgets import QToolButton


def save_image(parent, pixmap):
    filename, _ = QFileDialog.getSaveFileName(parent, tr('保存截图'), 'SnapTrans.png', tr('PNG 图片 (*.png)'))
    if not filename:
        return None
    if not filename.lower().endswith('.png'):
        filename += '.png'
    return pixmap.save(filename, 'PNG')


class OcrCanvas(TranslationCanvas):
    cancel_requested = Signal()
    extract_requested = Signal()
    translate_requested = Signal()
    text_edited = Signal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle(tr('SnapTrans · 截图与文字提取'))
        self.translation_bar = self.toolbar
        self.translation_bar.hide()
        self.toolbar = QFrame(self)
        self.toolbar.setCursor(Qt.CursorShape.ArrowCursor)
        self.toolbar.setObjectName('translationBar')
        self.toolbar.setStyleSheet(self.translation_bar.styleSheet())
        self.ocr_mode = True
        column_bar = QVBoxLayout(self.toolbar)
        column_bar.setContentsMargins(10, 7, 10, 7)
        column_bar.setSpacing(5)
        tools = QHBoxLayout()
        tools.setSpacing(4)
        self.dimensions = QLabel(tr('截图'))
        tools.addWidget(self.dimensions)
        self.editor = WorkspaceEditor(self, tools)
        tools.addStretch()
        tools.addWidget(self.languages)
        column_bar.addLayout(tools)
        column_bar.addWidget(self.editor.options)
        row = QHBoxLayout()
        row.setSpacing(6)
        column_bar.addLayout(row)
        for name, title, slot in (
            ('copy_image', tr('复制'), self.copy_image), ('save_image', tr('保存'), self.save_image),
            ('pin_image', tr('贴图'), self.pin_requested.emit), ('extract', tr('提取文字'), self.extract_requested.emit),
            ('workspace_translate', tr('翻译'), self.translate_current),
            ('translate_ocr', tr('弹窗'), self.translate_requested.emit)):
            button = QToolButton()
            button.setText(title)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(slot)
            row.addWidget(button)
            setattr(self, name + '_button', button)
        # Reparent the existing engine and comparison controls into the same workspace toolbar.
        row.addWidget(self.compare)
        self.engine.setMinimumWidth(130)
        self.engine.setMaximumWidth(205)
        row.addWidget(self.engine)
        self.settings_button.setParent(self.toolbar)
        row.addWidget(self.settings_button)
        self.finish_button = QToolButton()
        self.finish_button.setIcon(tool_icon('close'))
        self.finish_button.setProperty('toolIconName', 'close')
        self.finish_button.setToolTip(tr('关闭 · Esc'))
        self.finish_button.clicked.connect(self.dismissed)
        row.addWidget(self.finish_button)
        self.cancel_button = QToolButton()
        self.cancel_button.setText(tr('取消任务'))
        self.cancel_button.clicked.connect(self.cancel_requested)
        tools.addWidget(self.cancel_button)
        self.cancel_button.hide()
        for key, slot in [('Ctrl+C', self.copy_image), ('Ctrl+S', self.save_image),
                          ('Ctrl+Z', self.editor.undo), ('Ctrl+Y', self.editor.redo)]:
            QShortcut(QKeySequence(key), self, activated=slot)
        self.ocr_panel = QFrame(self)
        self.ocr_panel.setCursor(Qt.CursorShape.ArrowCursor)
        self.ocr_panel.setStyleSheet('QFrame { background: #25282e; border-radius: 10px; }'
                                    'QLabel { color: #e5e8ee; font-size: 12px; }'
                                    'QPlainTextEdit { color: #eef0f5; background: #191c23; border: 1px solid #404652; border-radius: 6px; padding: 8px; }'
                                    'QPushButton { color: white; background: #ff5148; border: none; border-radius: 6px; padding: 7px 14px; }'
                                    'QPushButton:disabled { background: #555; }')
        column = QVBoxLayout(self.ocr_panel)
        top = QHBoxLayout()
        top.addWidget(QLabel(tr('提取的文字 · 可编辑')), 1)
        self.copy_text_button = QPushButton(tr('复制文字'))
        self.copy_text_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.copy_text_button.setEnabled(False)
        self.copy_text_button.clicked.connect(self.copy_text)
        top.addWidget(self.copy_text_button)
        column.addLayout(top)
        self.ocr_editor = QPlainTextEdit()
        self.ocr_editor.viewport().setCursor(Qt.CursorShape.IBeamCursor)
        self.ocr_editor.setPlaceholderText(tr('点击“提取文字”，识别结果会显示在这里'))
        self.ocr_editor.textChanged.connect(self._edited)
        column.addWidget(self.ocr_editor)
        self.ocr_panel.hide()
        from .theme import style_tree
        self.setProperty('themeManaged', True)
        style_tree(self)

    def translate_current(self):
        if self.translation and not self.ocr_mode:
            self.retry.emit()
        else:
            self.workspace_requested.emit('translate')

    def copy_image(self):
        pixmap = self.rendered_selection()
        if pixmap and not pixmap.isNull():
            QApplication.clipboard().setPixmap(pixmap)
            self.set_status(tr('图片已复制；可粘贴到聊天、文档或画图软件'))

    def save_image(self):
        pixmap = self.rendered_selection()
        if pixmap and not pixmap.isNull():
            saved = save_image(self, pixmap)
            if saved is not None:
                self.set_status(tr('图片已保存') if saved else tr('保存失败，请检查所选目录是否可写'))

    def copy_text(self):
        text = self.ocr_editor.toPlainText()
        if text:
            QApplication.clipboard().setText(text)
            self.set_status(tr('文字已复制'))

    def _edited(self):
        text = self.ocr_editor.toPlainText()
        self.copy_text_button.setEnabled(bool(text) and not self.busy)
        self.text_edited.emit(text)
        self._position_toolbar()

    def set_ocr_text(self, text, reveal=True):
        self.ocr_editor.blockSignals(True)
        self.ocr_editor.setPlainText(text)
        self.ocr_editor.blockSignals(False)
        self.copy_text_button.setEnabled(bool(text) and not self.busy)
        self.ocr_panel.setVisible(reveal and bool(text))
        self._position_toolbar()

    def set_content(self, translation, busy=False):
        self.translation = '' if self.ocr_mode else translation
        self.busy = busy
        self.pin_image_button.setEnabled(not busy)
        self.extract_button.setEnabled(not busy)
        self.extract_button.setText(tr('提取文字'))
        self.workspace_translate_button.setEnabled(not busy)
        self.translate_ocr_button.setEnabled(not busy)
        self.ocr_editor.setReadOnly(busy)
        self.copy_text_button.setEnabled(bool(self.ocr_editor.toPlainText()) and not busy)
        self.cancel_button.setVisible(busy)
        self.compare.setVisible(not self.ocr_mode and bool(translation))
        self.workspace_translate_button.setText(tr('重新翻译') if translation else tr('翻译'))
        self._position_toolbar()
        self.update()

    def set_mode(self, ocr_mode):
        self.ocr_mode = ocr_mode
        self.ocr_panel.setVisible(ocr_mode and bool(self.ocr_editor.toPlainText()))

    def rendered_selection(self):
        return self.editor.export(super().rendered_selection())

    def unannotated_selection(self, *, force_translation=False):
        return super().rendered_selection(force_translation=force_translation)

    def mousePressEvent(self, event):
        if not self.editor.press(event):
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not self.editor.move(event):
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if not self.editor.release(event):
            changed = self._dragging
            super().mouseReleaseEvent(event)
            if changed:
                self.editor.reset()

    def _position_toolbar(self):
        if not hasattr(self, 'ocr_panel'):
            return
        self.dimensions.setVisible(self.width() > 720)
        if self.has_capture:
            scale_x = self.screenshot.width() / self.width()
            scale_y = self.screenshot.height() / self.height()
            self.dimensions.setText(f'{round(self.selection.width() * scale_x)} × {round(self.selection.height() * scale_y)}')
        super()._position_toolbar()
        if not self.ocr_panel.isHidden():
            panel_width = min(620, self.width() - 24)
            columns = max(20, (panel_width - 40) // 10)
            lines = sum(max(1, (len(line) + columns - 1) // columns)
                        for line in self.ocr_editor.toPlainText().splitlines())
            panel_height = min(230, max(110, 72 + lines * 24), max(100, self.height() // 3))
            self.ocr_panel.resize(panel_width, panel_height)
            x = max(12, min(self.toolbar.x(), self.width() - panel_width - 12))
            y = self.toolbar.geometry().bottom() + 12
            if y + panel_height > self.height() - 12:
                y = self.toolbar.y() - panel_height - 12
            self.ocr_panel.move(x, max(12, y))
            self.message.move(x, max(8, min(self.height() - self.message.height() - 8,
                                          self.ocr_panel.geometry().bottom() + 8)))

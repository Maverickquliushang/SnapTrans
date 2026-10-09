from ..i18n import tr
from PySide6.QtCore import Signal
from .localized_widgets import QWidget, QVBoxLayout, QHBoxLayout, QPlainTextEdit, QPushButton, QMessageBox, QBoxLayout
from .theme import label


class PromptEditor(QWidget):
    save_requested = Signal(str)

    def __init__(self, text):
        super().__init__()
        self.saved = text
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.addWidget(label(tr('学术翻译提示词'), 'sectionTitle'))
        column.addWidget(label(tr('大模型使用下面的提示词。默认锁定；修改与保存分别确认。Google、微软和 MyMemory 不使用此提示词。')))
        column.addWidget(label(tr('可使用 {source_language} 和 {target_language} 引用所选语言；实际翻译方向始终以语言选择为准。')))
        self.editor = QPlainTextEdit(text)
        self.editor.setReadOnly(True)
        self.editor.setMinimumHeight(220)
        column.addWidget(self.editor)
        row = self.actions = QHBoxLayout()
        self.edit_button = QPushButton(tr('修改提示词'))
        self.save_button = QPushButton(tr('保存提示词'))
        self.cancel_button = QPushButton(tr('取消修改'))
        for button in (self.edit_button, self.save_button, self.cancel_button):
            row.addWidget(button)
        column.addLayout(row)
        self.status = label(tr('已锁定 · 当前提示词已保存'))
        column.addWidget(self.status)
        self.edit_button.clicked.connect(self.unlock)
        self.save_button.clicked.connect(self.commit)
        self.cancel_button.clicked.connect(self.cancel)
        self.lock(True)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.actions.setDirection(QBoxLayout.Direction.TopToBottom if self.width() < 650
                                  else QBoxLayout.Direction.LeftToRight)

    def confirm(self, text):
        return QMessageBox.question(self, tr('确认学术提示词'), text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes

    def lock(self, locked):
        self.editor.setReadOnly(locked)
        self.edit_button.setEnabled(locked)
        self.save_button.setEnabled(not locked)
        self.cancel_button.setEnabled(not locked)

    def unlock(self):
        if self.confirm(tr('确定修改学术翻译提示词？修改会影响之后的学术翻译。')):
            self.lock(False)
            self.editor.setFocus()
            self.status.setText(tr('编辑中 · 尚未保存'))

    def commit(self):
        text = self.editor.toPlainText().strip()
        if not text or len(text) > 16000:
            self.status.setText(tr('提示词不能为空，且不能超过 16000 字符'))
            return
        if self.confirm(tr('确定保存新的学术翻译提示词？保存后对下一次学术翻译生效。')):
            self.save_requested.emit(text)

    def saved_result(self, text, error=''):
        if error:
            self.status.setText(error)
            return
        self.saved = text
        self.editor.setPlainText(text)
        self.lock(True)
        self.status.setText(tr('已保存并锁定'))

    def cancel(self):
        self.editor.setPlainText(self.saved)
        self.lock(True)
        self.status.setText(tr('已取消修改 · 保留原提示词'))

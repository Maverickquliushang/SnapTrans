from PySide6.QtCore import Signal
from .localized_widgets import QWidget, QHBoxLayout, QComboBox, QToolButton, QPushButton, QDialog, QVBoxLayout
from ..languages import LANGUAGES, language_name, validate_pair
from ..i18n import tr


class LanguagePair(QWidget):
    changed = Signal(str, str)

    def __init__(self, source='en', target='zh-CN'):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.source = QComboBox()
        self.target = QComboBox()
        for code in LANGUAGES:
            self.source.addItem(language_name(code), code)
            if code != 'auto':
                self.target.addItem(language_name(code), code)
        for widget in (self.source, self.target):
            widget.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            widget.setMinimumContentsLength(8)
        self.source.setToolTip(tr('原文语言'))
        self.target.setToolTip(tr('目标语言'))
        self.swap = QToolButton()
        from .annotation_icons import configure_tool_button
        configure_tool_button(self.swap, 'swap', tr('交换语言'))
        self.swap.setToolTip(tr('交换语言；自动检测时请先指定原文语言'))
        self.swap.clicked.connect(self.swap_pair)
        layout.addWidget(self.source, 1)
        layout.addWidget(self.swap)
        layout.addWidget(self.target, 1)
        self.set_pair(source, target)
        self.source.currentIndexChanged.connect(self._changed)
        self.target.currentIndexChanged.connect(self._changed)

    def pair(self):
        return self.source.currentData(), self.target.currentData()

    def set_pair(self, source, target):
        validate_pair(source, target)
        for widget, code in ((self.source, source), (self.target, target)):
            widget.blockSignals(True)
            widget.setCurrentIndex(widget.findData(code))
            widget.blockSignals(False)
        self.swap.setEnabled(source != 'auto')

    def _changed(self):
        self.swap.setEnabled(self.source.currentData() != 'auto')
        self.changed.emit(*self.pair())

    def swap_pair(self):
        source, target = self.pair()
        if source != 'auto':
            self.set_pair(target, source)
            self.changed.emit(*self.pair())


class LanguageButton(QPushButton):
    changed = Signal(str, str)

    def __init__(self):
        super().__init__()
        self.setObjectName('quiet')
        self.set_pair('en', 'zh-CN')
        self.setToolTip(tr('选择原文和目标语言'))
        self.clicked.connect(self.choose)

    def pair(self):
        return self._pair

    def set_pair(self, source, target):
        validate_pair(source, target)
        self._pair = source, target
        self.setText(language_name(source) + ' → ' + language_name(target))

    def choose(self):
        from .theme import apply_theme
        dialog = QDialog(self)
        dialog.setWindowTitle(tr('翻译语言'))
        layout = QVBoxLayout(dialog)
        editor = LanguagePair(*self._pair)
        layout.addWidget(editor)
        buttons = QHBoxLayout()
        cancel = QPushButton(tr('取消'))
        cancel.clicked.connect(dialog.reject)
        use = QPushButton(tr('应用语言'))
        use.setObjectName('primary')
        use.clicked.connect(dialog.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(use)
        layout.addLayout(buttons)
        apply_theme(dialog)
        if dialog.exec() == QDialog.DialogCode.Accepted and editor.pair() != self._pair:
            self.set_pair(*editor.pair())
            self.changed.emit(*self._pair)

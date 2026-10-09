from ..i18n import tr
from PySide6.QtCore import Signal
from PySide6.QtGui import QIcon
from .localized_widgets import QSystemTrayIcon, QMenu
from .theme import apply_theme


class Tray(QSystemTrayIcon):
    translate = Signal()
    ocr = Signal()
    settings = Signal()
    about = Signal()
    quit_requested = Signal()

    def __init__(self, icon_path):
        super().__init__(QIcon(str(icon_path)))
        self.setToolTip(tr('SnapTrans · 识别引擎准备中'))
        self.menu = QMenu()
        apply_theme(self.menu)
        self.menu.addAction('SNAPTRANS').setEnabled(False)
        self.menu.addSeparator()
        self.capture_actions = []
        for label, signal in [(tr('截图\tF2'), self.translate), (tr('仅截图一次\tAlt+W'), self.ocr),
                              (tr('设置'), self.settings), (tr('关于'), self.about), (tr('退出'), self.quit_requested)]:
            if label in (tr('设置'), tr('退出')):
                self.menu.addSeparator()
            action = self.menu.addAction(label)
            if signal in (self.translate, self.ocr):
                self.capture_actions.append(action)
            action.triggered.connect(lambda checked=False, target=signal: target.emit())
        self.setContextMenu(self.menu)
        self.activated.connect(lambda reason: self.settings.emit() if reason == self.ActivationReason.DoubleClick else None)

    def notify(self, text):
        self.showMessage('SnapTrans', text, self.MessageIcon.Information, 4000)

    def update_hotkeys(self, bindings):
        self.capture_actions[0].setText(tr('截图\t') + bindings.get('translate', tr('未注册')))
        self.capture_actions[1].setText(tr('仅截图一次\t') + bindings.get('ocr', tr('未注册')))

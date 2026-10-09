from ..i18n import ui_format
from ..i18n import tr
from PySide6.QtGui import QIntValidator
from .localized_widgets import QLineEdit


class NumberEdit(QLineEdit):
    """A plain, directly editable number; no nested spinbox editor hit targets."""
    def __init__(self):
        super().__init__()
        self.minimum, self.maximum = 0, 1048576
        self.setRange(self.minimum, self.maximum)
        self.setText('0')
        self.setToolTip(tr('点击数字后直接输入；Ctrl+A 全选替换'))

    def setRange(self, minimum, maximum):
        self.minimum, self.maximum = minimum, maximum
        self.setValidator(QIntValidator(0, maximum, self))

    def setValue(self, value):
        self.setText(str(value))

    def value(self):
        try:
            value = int(self.text().strip())
        except ValueError:
            raise ValueError(tr('请输入完整的整数参数')) from None
        if not self.minimum <= value <= self.maximum:
            raise ValueError(ui_format('{}{}–{}{}', tr('参数应在 '), self.minimum, self.maximum, tr(' 之间')))
        return value

    def setSuffix(self, suffix):
        self.setPlaceholderText(suffix.strip())

    def setSingleStep(self, step):
        pass

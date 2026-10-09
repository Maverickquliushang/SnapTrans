"""Qt controls that retain translation sources for live language changes.

Only display properties are bound. Editor values, item data, selections and
signals retain Qt's normal behavior. Unchanged Qt classes are re-exported.
"""
from PySide6 import QtWidgets as Qt
from PySide6.QtGui import QAction as QtAction
from ..i18n import tr, remember


def __getattr__(name):
    return getattr(Qt, name)


def _property(target, setter, getter, value):
    remember(target, getter, value, lambda obj: getattr(obj, getter)(),
             lambda obj, text: getattr(obj, setter)(text))


class _DisplayProperties:
    def setWindowTitle(self, value):
        value = tr(value)
        super().setWindowTitle(value)
        _property(self, 'setWindowTitle', 'windowTitle', value)

    def setToolTip(self, value):
        value = tr(value)
        super().setToolTip(value)
        _property(self, 'setToolTip', 'toolTip', value)

    def setAccessibleName(self, value):
        value = tr(value)
        super().setAccessibleName(value)
        _property(self, 'setAccessibleName', 'accessibleName', value)

    def setPlaceholderText(self, value):
        value = tr(value)
        super().setPlaceholderText(value)
        _property(self, 'setPlaceholderText', 'placeholderText', value)


class _TextProperties(_DisplayProperties):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for value in args:
            if isinstance(value, str):
                self.setText(value)
                break

    def setText(self, value):
        value = tr(value)
        super().setText(value)
        _property(self, 'setText', 'text', value)


class QWidget(_DisplayProperties, Qt.QWidget):
    pass


class QDialog(_DisplayProperties, Qt.QDialog):
    pass


class QFrame(_DisplayProperties, Qt.QFrame):
    pass


class QLabel(_TextProperties, Qt.QLabel):
    pass


class QPushButton(_TextProperties, Qt.QPushButton):
    pass


class QToolButton(_TextProperties, Qt.QToolButton):
    pass


class QCheckBox(_TextProperties, Qt.QCheckBox):
    pass


class QLineEdit(_DisplayProperties, Qt.QLineEdit):
    pass


class QPlainTextEdit(_DisplayProperties, Qt.QPlainTextEdit):
    pass


class QSpinBox(_DisplayProperties, Qt.QSpinBox):
    pass


class QSystemTrayIcon(_DisplayProperties, Qt.QSystemTrayIcon):
    pass


class QAction(_TextProperties, QtAction):
    pass


class QMenu(_DisplayProperties, Qt.QMenu):
    def addAction(self, *args):
        if args and isinstance(args[0], str) and len(args) <= 2:
            action = QAction(args[0], self)
            super().addAction(action)
            if len(args) == 2:
                action.triggered.connect(args[1])
            return action
        return super().addAction(*args)


class QComboBox(_DisplayProperties, Qt.QComboBox):
    def addItem(self, *args, **kwargs):
        index = self.count()
        values = list(args)
        text_index = 0 if isinstance(values[0], str) else 1
        value = values[text_index] if self.isEditable() else tr(values[text_index])
        values[text_index] = value
        super().addItem(*values, **kwargs)
        remember(self, ('item', index), value,
                 lambda obj: obj.itemText(index),
                 lambda obj, text: Qt.QComboBox.setItemText(obj, index, text))

    def addItems(self, values):
        for value in values:
            self.addItem(value)

    def clear(self):
        for key in list(getattr(self, '_ui_text_bindings', {})):
            if isinstance(key, tuple) and key[0] == 'item':
                self._ui_text_bindings.pop(key)
        super().clear()


class QTabWidget(_DisplayProperties, Qt.QTabWidget):
    def addTab(self, *args):
        value = tr(args[-1])
        index = super().addTab(*args[:-1], value)
        remember(self, ('tab', index), value,
                 lambda obj: obj.tabText(index),
                 lambda obj, text: obj.setTabText(index, text))
        return index


class QListWidget(_DisplayProperties, Qt.QListWidget):
    def addItem(self, value):
        index = self.count()
        value = tr(value)
        super().addItem(value)
        if isinstance(value, str):
            remember(self, ('item', index), value,
                     lambda obj: obj.item(index).text() if obj.item(index) else None,
                     lambda obj, text: obj.item(index).setText(text))

    def addItems(self, values):
        for value in values:
            self.addItem(value)

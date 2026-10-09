from ..i18n import ui_format
from ..i18n import tr
from PySide6.QtCore import Qt, Signal, QEvent, QTimer
from .localized_widgets import QLineEdit, QWidget, QPushButton, QLabel, QHBoxLayout, QVBoxLayout
from ..hotkey_format import parse_hotkey


class HotkeyEdit(QLineEdit):
    """Physical-key recording, with an explicit editable-text alternative."""
    recording = Signal(bool)
    status_changed = Signal(object, bool)
    commit_requested = Signal(str)

    def __init__(self, value):
        super().__init__(value)
        self.manual_mode = False
        self._before_record = value
        self._saved_value = value
        self._pending_chord = ''
        self._manual_timer = QTimer(self)
        self._manual_timer.setSingleShot(True)
        self._manual_timer.setInterval(650)
        self._manual_timer.timeout.connect(self._commit_manual)
        self.textEdited.connect(lambda: self._manual_timer.start() if self.manual_mode else None)
        self.setReadOnly(True)
        self.setAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled, False)
        self.setPlaceholderText(tr('请按新的快捷键…'))
        self.setToolTip(tr('点击或点“修改”后直接按键；也可选择“手动填写”'))

    def start_recording(self):
        self._manual_timer.stop()
        self._pending_chord = ''
        self.manual_mode = False
        self.setReadOnly(True)
        self.setAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled, False)
        self._before_record = self._saved_value
        self.setFocus(Qt.FocusReason.OtherFocusReason)
        self.recording.emit(True)
        self.clear()
        self.status_changed.emit(tr('请按新的快捷键，例如 F3 或 Ctrl+Q；Esc 撤销'), False)

    def set_manual_mode(self, enabled):
        if not self.text():
            self.setText(self._before_record)
        self.manual_mode = enabled
        self.setReadOnly(not enabled)
        self.setAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled, enabled)
        self.setFocus(Qt.FocusReason.OtherFocusReason)
        self.selectAll()
        self.recording.emit(True)
        self.status_changed.emit(tr('输入完整快捷键后自动保存，例如 F3、Ctrl+Q') if enabled
                                 else tr('请直接按新的快捷键，松键后自动保存'), False)

    def focusInEvent(self, event):
        self._before_record = self._saved_value
        self.recording.emit(True)
        super().focusInEvent(event)
        self.selectAll()
        self.status_changed.emit(tr('手动输入快捷键，停止输入后自动保存') if self.manual_mode
                                 else tr('正在录入：请直接按键，例如 F3 或 Ctrl+Q'), False)

    def focusOutEvent(self, event):
        if self.manual_mode:
            self._commit_manual()
        if not self.manual_mode and not self.text():
            self.setText(self._before_record)
            self.status_changed.emit(tr('未录入新按键，保留原设置'), False)
        super().focusOutEvent(event)
        self.recording.emit(False)

    def _commit_manual(self):
        self._manual_timer.stop()
        value = self.text().strip()
        if not self.manual_mode or value == self._saved_value:
            return
        try:
            parse_hotkey(value)
        except ValueError as error:
            self.status_changed.emit(tr('未保存：') + str(error), True)
            return
        self.commit_requested.emit(value)

    def acknowledge(self, value, error=''):
        self._manual_timer.stop()
        self._pending_chord = ''
        self.setText(value)
        self._saved_value = self._before_record = value
        if not self.manual_mode:
            self.clearFocus()
        self.status_changed.emit((tr('未保存，保留原快捷键。') + error) if error
                                 else ui_format('{}{}', tr('已自动保存 '), value), bool(error))

    def keyReleaseEvent(self, event):
        if not self.manual_mode and self._pending_chord and not event.isAutoRepeat():
            if event.key() not in (Qt.Key.Key_Control, Qt.Key.Key_Alt, Qt.Key.Key_Shift):
                value, self._pending_chord = self._pending_chord, ''
                self.commit_requested.emit(value)
        super().keyReleaseEvent(event)

    def hideEvent(self, event):
        if self.manual_mode:
            self._commit_manual()
        self._manual_timer.stop()
        super().hideEvent(event)

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if not self.manual_mode and event.button() == Qt.MouseButton.LeftButton:
            self.start_recording()

    def event(self, event):
        if event.type() == QEvent.Type.ShortcutOverride and not self.manual_mode:
            event.accept()
            return True
        return super().event(event)

    def keyPressEvent(self, event):
        if self.manual_mode:
            super().keyPressEvent(event)
            return
        event.accept()
        if event.isAutoRepeat():
            return
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self._pending_chord = ''
            self.setText(self._before_record)
            self.status_changed.emit(tr('已撤销本次录入'), False)
            self.clearFocus()
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.clearFocus()
            return
        modifiers = event.modifiers()
        if modifiers & Qt.KeyboardModifier.MetaModifier or key == Qt.Key.Key_Meta:
            self.status_changed.emit(tr('暂不支持 Windows 键组合，请使用 Ctrl / Alt / Shift'), True)
            return
        parts = [name for flag, name in (
            (Qt.KeyboardModifier.ControlModifier, 'Ctrl'),
            (Qt.KeyboardModifier.AltModifier, 'Alt'),
            (Qt.KeyboardModifier.ShiftModifier, 'Shift')) if modifiers & flag]
        if key in (Qt.Key.Key_Control, Qt.Key.Key_Alt, Qt.Key.Key_Shift):
            self.status_changed.emit(tr('已按下 ') + '+'.join(parts) + tr('，请继续按主键'), False)
            return
        if key == Qt.Key.Key_Backspace and not parts:
            self.clear()
            self.status_changed.emit(tr('请按新的快捷键；Esc 恢复原设置'), False)
            return
        named = {Qt.Key.Key_Space: 'Space', Qt.Key.Key_Insert: 'Insert', Qt.Key.Key_Delete: 'Delete',
                 Qt.Key.Key_Home: 'Home', Qt.Key.Key_End: 'End', Qt.Key.Key_PageUp: 'PageUp',
                 Qt.Key.Key_PageDown: 'PageDown', Qt.Key.Key_Left: 'Left', Qt.Key.Key_Right: 'Right',
                 Qt.Key.Key_Up: 'Up', Qt.Key.Key_Down: 'Down'}
        if Qt.Key.Key_F1 <= key <= Qt.Key.Key_F24:
            parts.append('F' + str(key - Qt.Key.Key_F1 + 1))
        elif Qt.Key.Key_A <= key <= Qt.Key.Key_Z or Qt.Key.Key_0 <= key <= Qt.Key.Key_9:
            parts.append(chr(key))
        elif key in named:
            parts.append(named[key])
        else:
            self.status_changed.emit(tr('不支持这个按键，请选择功能键或 Ctrl / Alt / Shift 组合'), True)
            return
        chord = '+'.join(parts)
        try:
            parse_hotkey(chord)
        except ValueError as error:
            self.status_changed.emit(str(error), True)
            return
        self.setText(chord)
        self.selectAll()
        self._pending_chord = chord
        self.status_changed.emit(ui_format('{}{}{}', tr('已录入 '), chord, tr('，松键后自动保存')), False)


class HotkeyControl(QWidget):
    def __init__(self, field):
        super().__init__()
        self.field = field
        self.record_button = QPushButton(tr('修改'))
        self.record_button.setAutoDefault(False)
        self.manual_button = QPushButton(tr('手动填写'))
        self.manual_button.setAutoDefault(False)
        self.manual_button.setCheckable(True)
        self.hint = QLabel(tr('点击“修改”后按键，或选择“手动填写”'))
        self.hint.setWordWrap(True)
        self.hint.setStyleSheet('color: #929caf; font-size: 12px;')
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(field, 1)
        row.addWidget(self.record_button)
        row.addWidget(self.manual_button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        layout.addLayout(row)
        layout.addWidget(self.hint)
        self.record_button.clicked.connect(self._record)
        self.manual_button.toggled.connect(field.set_manual_mode)
        field.status_changed.connect(self._status)

    def _record(self):
        self.manual_button.blockSignals(True)
        self.manual_button.setChecked(False)
        self.manual_button.blockSignals(False)
        self.field.start_recording()

    def _status(self, text, error):
        from .themes import palette
        colors = palette(self.window().property('themeName'))
        self.hint.setText(text)
        self.hint.setStyleSheet('font-size: 12px; color: ' + (colors['accent'] if error else colors['muted']) + ';')

from .i18n import tr
import ctypes
from ctypes import wintypes
from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Signal, QCoreApplication
from .hotkey_format import parse_hotkey


class NativeFilter(QAbstractNativeEventFilter):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner

    def nativeEventFilter(self, event_type, message):
        if bytes(event_type) in (b'windows_generic_MSG', b'windows_dispatcher_MSG'):
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == 0x0312 and msg.wParam in self.owner.actions:
                self.owner.activated.emit(self.owner.actions[msg.wParam])
                return True
        return False


class Hotkeys(QObject):
    activated = Signal(str)

    def __init__(self):
        super().__init__()
        self.api = ctypes.WinDLL('user32', use_last_error=True)
        self.api.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
        self.api.RegisterHotKey.restype = wintypes.BOOL
        self.api.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
        self.api.UnregisterHotKey.restype = wintypes.BOOL
        self.actions = {}
        self.bindings = {}
        self.suspended = False
        self.filter = NativeFilter(self)
        QCoreApplication.instance().installNativeEventFilter(self.filter)

    def _register(self, bindings):
        failures = []
        for index, action in enumerate(('translate', 'ocr'), start=0x4010):
            modifiers, key = parse_hotkey(bindings[action])
            if self.api.RegisterHotKey(None, index, modifiers | 0x4000, key):
                self.actions[index] = action
                self.bindings[action] = bindings[action]
            else:
                failures.append(bindings[action])
        return failures

    def install(self, bindings):
        parsed = [parse_hotkey(bindings[key]) for key in ('translate', 'ocr')]
        if parsed[0] == parsed[1]:
            raise ValueError(tr('两个快捷键不能相同'))
        if self.suspended:
            # Saving while an editor still has focus must check Windows conflicts
            # now, rather than persisting an unregistrable binding and failing on blur.
            self.suspended = False
            try:
                self.install(bindings)
            finally:
                self.set_suspended(True)
            return
        old = self.bindings.copy()
        self.clear()
        failures = self._register(bindings)
        if failures and old:
            self.clear()
            # Restore only bindings that really existed before the transaction.
            restore_failures = []
            for index, action in enumerate(('translate', 'ocr'), start=0x4010):
                if action not in old:
                    continue
                modifiers, key = parse_hotkey(old[action])
                if self.api.RegisterHotKey(None, index, modifiers | 0x4000, key):
                    self.actions[index] = action
                    self.bindings[action] = old[action]
                else:
                    restore_failures.append(old[action])
            detail = tr('；旧快捷键也未能恢复：') + ', '.join(restore_failures) if restore_failures else ''
            raise ValueError(tr('快捷键被占用：') + ', '.join(failures) + detail)
        if failures:
            raise ValueError(tr('快捷键被占用：') + ', '.join(failures) + tr('。仍可从托盘使用。'))

    def clear(self):
        for key in self.actions:
            self.api.UnregisterHotKey(None, key)
        self.actions.clear()
        self.bindings.clear()

    def set_suspended(self, suspended):
        if suspended == self.suspended:
            return
        if suspended:
            for key in self.actions:
                self.api.UnregisterHotKey(None, key)
            self.actions.clear()
            self.suspended = True
        else:
            bindings = self.bindings.copy()
            self.suspended = False
            self.bindings.clear()
            if bindings:
                failures = self._register(bindings)
                if failures:
                    raise ValueError(tr('快捷键被占用：') + ', '.join(failures))

    def close(self):
        self.clear()
        QCoreApplication.instance().removeNativeEventFilter(self.filter)

"""Short Windows message-loop/hotkey/tray probe; no screen capture or API call."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    os.environ.pop('QT_QPA_PLATFORM', None)
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QSystemTrayIcon
    from snaptrans.hotkeys import Hotkeys
    from snaptrans.ui.tray import Tray
    from snaptrans.ui.settings_window import SettingsWindow
    from snaptrans.ui.fonts import initialize_fonts
    from snaptrans.config import DEFAULT
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    initialize_fonts(app)
    tray = Tray(ROOT / 'assets' / 'icon.ico')
    tray.show()
    settings = SettingsWindow(DEFAULT)
    settings.show()
    hotkeys = Hotkeys()
    hotkeys.install({'translate': 'Ctrl+Alt+Shift+F10', 'ocr': 'Ctrl+Alt+Shift+F11'})
    results = {'tray_available': QSystemTrayIcon.isSystemTrayAvailable(), 'timer': False, 'hotkey_messages': []}
    hotkeys.activated.connect(results['hotkey_messages'].append)
    finished = threading.Event()
    def hard_deadline():
        if not finished.wait(15):
            (ROOT / '.tmp' / 'windows-probe-timeout.txt').write_text('Qt event loop did not exit', encoding='utf-8')
            os._exit(2)
    threading.Thread(target=hard_deadline, daemon=True).start()
    def probe():
        results['timer'] = True
        user32 = ctypes.WinDLL('user32', use_last_error=True)
        user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user32.PostThreadMessageW.restype = wintypes.BOOL
        user32.PostThreadMessageW(ctypes.windll.kernel32.GetCurrentThreadId(), 0x0312, 0x4010, 0)
        settings.grab().save(str(ROOT / '.tmp' / 'windows-settings.png'))
        QTimer.singleShot(500, app.quit)
    QTimer.singleShot(300, probe)
    app.exec()
    hotkeys.close()
    tray.hide()
    settings.close()
    finished.set()
    (ROOT / '.tmp' / 'windows-probe.json').write_text(json.dumps(results), encoding='utf-8')
    print(json.dumps(results))
    return 0 if results['timer'] and results['hotkey_messages'] == ['translate'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

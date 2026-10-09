import faulthandler
import os
import threading
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QCoreApplication, QTimer, QAbstractEventDispatcher, qVersion
from PySide6.QtWidgets import QApplication, QWidget

print('Qt', qVersion(), flush=True)
app = QApplication([])
app.setQuitOnLastWindowClosed(False)
widget = QWidget()
widget.show()
if '--hotkeys' in sys.argv:
    from snaptrans.hotkeys import Hotkeys
    hotkeys = Hotkeys()
    hotkeys.install({'translate': 'Ctrl+Alt+Shift+F10', 'ocr': 'Ctrl+Alt+Shift+F11'})
if '--settings' in sys.argv:
    from snaptrans.ui.settings_window import SettingsWindow
    from snaptrans.config import DEFAULT
    settings = SettingsWindow(DEFAULT)
    settings.show()
if '--fonts' in sys.argv:
    from snaptrans.ui.fonts import initialize_fonts
    initialize_fonts(app)
if '--tray' in sys.argv:
    from snaptrans.ui.tray import Tray
    tray = Tray(Path(__file__).resolve().parents[1] / 'assets/icon.ico')
    tray.show()
timer = QTimer()
timer.setInterval(100)
def tick():
    print('timer callback', flush=True)
    app.quit()
timer.timeout.connect(tick)
timer.start()
QTimer.singleShot(10, lambda: print('single shot', flush=True))
print('dispatcher', QAbstractEventDispatcher.instance(), 'timer', timer.timerId(), flush=True)
def watchdog():
    import time
    time.sleep(5)
    print('timer did not complete native loop', flush=True)
    os._exit(2)
threading.Thread(target=watchdog, daemon=True).start()
print('enter', flush=True)
code = app.exec()
print('exit', code, flush=True)
if '--hotkeys' in sys.argv:
    hotkeys.close()

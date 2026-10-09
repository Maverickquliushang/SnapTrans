"""Render settings, result and screenshot toolbar at practical and small sizes."""
from pathlib import Path
import sys, json
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from copy import deepcopy
from PySide6.QtCore import QRectF
from PySide6.QtGui import QPixmap, QColor
from PySide6.QtWidgets import QApplication
from snaptrans.config import DEFAULT
from snaptrans.ui.settings_window import SettingsWindow
from snaptrans.ui.result_window import ResultWindow
from snaptrans.ui.theme import refresh_themes
from snaptrans.ui.themes import THEMES


def run():
    app = QApplication([])
    from snaptrans.ui.fonts import initialize_fonts
    initialize_fonts(app)
    output = ROOT / 'docs' / 'evidence' / 'v1.9.0'
    output.mkdir(parents=True, exist_ok=True)
    report = {}
    for theme in THEMES:
        config = deepcopy(DEFAULT)
        config['window'].update(theme=theme, display_mode='popup')
        refresh_themes(theme)
        window = SettingsWindow(config)
        window.tabs.setCurrentIndex(1)
        window.show_provider_picker()
        window.provider_picker.show_group('domestic')
        window.resize(710, 750)
        window.show(); app.processEvents()
        native = {}
        if app.platformName() == 'windows':
            import ctypes
            from ctypes import wintypes
            import win32gui, win32con
            handle = int(window.winId())
            native['settings_topmost'] = bool(win32gui.GetWindowLong(handle, win32con.GWL_EXSTYLE) & win32con.WS_EX_TOPMOST)
            caption = wintypes.DWORD()
            code = ctypes.windll.dwmapi.DwmGetWindowAttribute(wintypes.HWND(handle), 35, ctypes.byref(caption), ctypes.sizeof(caption))
            native['caption_colorref'] = caption.value if code == 0 else None
        window.grab().save(str(output / f'{theme}-settings.png'))
        window.tabs.setCurrentIndex(3)
        window.resize(540, 460); app.processEvents()
        window.grab().save(str(output / f'{theme}-small.png'))
        report[theme] = {**native, 'settings_size': [window.width(), window.height()], 'save_visible': window.rect().contains(window.save_button.mapTo(window, window.save_button.rect().bottomRight()))}
        result = ResultWindow(config['window'], config)
        result.set_busy(False)
        result.set_original('A clear interface makes everyday tasks easier.', 'A clear interface makes everyday tasks easier.')
        result.translated.setPlainText('清晰的界面让日常操作更轻松。')
        result.resize(520, 420); result.show(); app.processEvents()
        result.grab().save(str(output / f'{theme}-result.png'))
        report[theme]['result_size'] = [result.width(), result.height()]
        canvas = result.overlay
        pixmap = QPixmap(900, 600); pixmap.fill(QColor('white'))
        canvas.attach_capture(app.primaryScreen(), pixmap, QRectF(30, 40, 700, 140))
        canvas.editor.set_tool('pen')
        canvas.toolbar.grab().save(str(output / f'{theme}-toolbar.png'))
        result.close(); window.close(); app.processEvents()
    refresh_themes('ember')
    (output / 'theme-layouts.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    run()

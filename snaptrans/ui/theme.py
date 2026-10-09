from PySide6.QtWidgets import QWidget as QtWidget
"""Shared colors, spacing and cards for the native SnapTrans windows."""
from PySide6.QtCore import Qt, QObject, QEvent
from .localized_widgets import QFrame, QLabel, QVBoxLayout, QPushButton, QToolButton, QWidget, QApplication
from ..paths import resource_root
from .themes import THEMES, palette, current_theme, set_current_theme, themed_css, is_light

STYLE = '''
QWidget#snapWindow { background: #171a20; color: #edf0f6; }
QLabel, QCheckBox { color: #dce1eb; font-size: 13px; background: transparent; }
QLabel#title { font-size: 25px; font-weight: 600; color: #f6f7fb; }
QLabel#subtitle { color: #929caf; font-size: 12px; }
QLabel#sectionTitle { color: #edf0f6; font-size: 14px; font-weight: 600; }
QLabel#badge { color: #ffaca6; background: #3a282b; padding: 5px 10px; border-radius: 7px; font-size: 12px; }
QLabel#status { color: #acb7cb; background: #212630; padding: 9px 12px; border-radius: 8px; font-size: 12px; }
QFrame#card { background: #22262f; border: 1px solid #323845; border-radius: 12px; }
QLineEdit, QPlainTextEdit, QComboBox, QSpinBox { background: #191d25; color: #edf0f6; border: 1px solid #3b4352; border-radius: 7px; padding: 8px; selection-background-color: #754842; }
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus { border: 1px solid #ff786f; }
QLineEdit:disabled, QComboBox:disabled { color: #777f90; background: #20242b; }
QComboBox { padding-right: 26px; font-size: 13px; }
QComboBox::drop-down { border: none; width: 24px; }
QComboBox QAbstractItemView { background: #252a34; color: #edf0f6; selection-background-color: #49404a; border: 1px solid #454d5c; padding: 6px; }
QPushButton, QToolButton { color: #dce2ee; background: #303642; border: 1px solid #3d4656; border-radius: 7px; padding: 8px 13px; font-size: 13px; }
QPushButton:hover, QToolButton:hover { background: #414958; border-color: #596476; }
QPushButton:checked { color: #ffb5af; background: #4a3034; border-color: #9b5954; }
QPushButton#primary { color: white; background: #f6534b; border-color: #f6534b; font-weight: 600; }
QPushButton#primary:hover { background: #ff6c63; }
QPushButton:disabled, QPushButton#primary:disabled { color: #7c8799; background: #2a303a; border-color: #343b48; }
QCheckBox { spacing: 8px; padding: 4px 0; }
QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid #626e81; border-radius: 4px; background: #191d25; }
QCheckBox::indicator:checked { background: #f6534b; border-color: #ff9b95; }
QTabWidget::pane { border: none; }
QTabBar::tab { color: #a2adc0; background: #171a20; padding: 12px 20px; margin-right: 6px; border-bottom: 2px solid transparent; font-size: 14px; }
QTabBar::tab:selected { color: #ffa39c; border-bottom: 2px solid #ff655b; }
QTabBar::tab:hover { background: #242932; }
QScrollArea { background: transparent; border: none; }
QWidget#scrollContent { background: #171a20; }
QScrollBar:vertical { width: 8px; background: #1b1f27; margin: 0; }
QScrollBar::handle:vertical { background: #495366; border-radius: 4px; min-height: 24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
QToolTip { background: #303744; color: #f0f2f7; border: 1px solid #596174; padding: 6px; }
QMenu { background: #20242d; color: #edf0f6; border: 1px solid #424a59; padding: 7px; }
QMenu::item { padding: 9px 26px 9px 16px; border-radius: 6px; }
QMenu::item:selected { background: #543237; color: #ffb9b3; }
QMenu::item:disabled { color: #8993a5; }
QMenu::separator { height: 1px; background: #3b424e; margin: 6px 8px; }
QSlider::groove:horizontal { height: 4px; background: #626e81; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #f6534b; border-radius: 2px; }
QSlider::handle:horizontal { background: #f6534b; border: 2px solid #edf0f6; width: 12px; margin: -5px 0; border-radius: 7px; }
'''


def label(text, name='subtitle'):
    from ..i18n import tr
    result = QLabel(tr(text))
    result.setObjectName(name)
    result.setWordWrap(True)
    return result


def card(title, description=''):
    frame = QFrame()
    frame.setObjectName('card')
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(18, 16, 18, 16)
    layout.setSpacing(10)
    layout.addWidget(label(title, 'sectionTitle'))
    if description:
        layout.addWidget(label(description))
    return frame, layout


def style_tree(window, name=None):
    """Reapply saved styles without accumulating replacements or tinting color swatches."""
    for widget in [window, *window.findChildren(QtWidget)]:
        if widget.property('themeExempt'):
            continue
        raw = widget.property('themeSource')
        if raw is None:
            raw = widget.styleSheet()
            widget.setProperty('themeSource', raw)
        if raw:
            css = themed_css(raw, name)
            if is_light(name):
                css = css.replace('/chevron.png', '/chevron-dark.png')
            widget.setStyleSheet(css)
        widget.setProperty('themeName', name or current_theme())
        if widget.property('softElevation'):
            from .preferences_shell import update_elevation
            update_elevation(widget, name)
        if widget.property('annotationIconName'):
            from .annotation_icons import annotation_icon
            widget.setIcon(annotation_icon(widget.property('annotationIconName'), name))
    apply_native_caption(window)


def refresh_themes(name):
    set_current_theme(name)
    for window in QApplication.topLevelWidgets():
        if window.property('themeManaged'):
            style_tree(window, name)
            if hasattr(window, 'refresh_icons'):
                window.refresh_icons()
            window.update()


def apply_theme(window, name=None):
    window.setObjectName('snapWindow')
    window.setProperty('themeManaged', True)
    window.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    window.setProperty('themeSource', STYLE + control_icons())
    style_tree(window, name)
    if not hasattr(window, '_dark_frame'):
        window._dark_frame = DarkFrame(window)
    for button in window.findChildren(QPushButton) + window.findChildren(QToolButton):
        button.setCursor(Qt.CursorShape.PointingHandCursor)


class DarkFrame(QObject):
    """Color only this window's native caption; keep Windows move/resize behavior."""
    def __init__(self, window):
        super().__init__(window)
        window.installEventFilter(self)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Show:
            apply_native_caption(watched)
        return False


def apply_native_caption(window):
    import sys
    if sys.platform != 'win32' or window.windowFlags() & Qt.WindowType.FramelessWindowHint:
        return {}
    import ctypes
    from ctypes import wintypes
    from PySide6.QtGui import QGuiApplication
    if QGuiApplication.platformName() != 'windows':
        return {}
    setter = ctypes.windll.dwmapi.DwmSetWindowAttribute
    setter.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
    setter.restype = ctypes.c_long
    results = {}
    # Win11 honors explicit colors even when Windows itself uses a light theme.
    colors = palette(window.property('themeName') or current_theme())
    def colorref(hex_color):
        r, g, b = bytes.fromhex(hex_color[1:])
        return r | g << 8 | b << 16
    dark = sum(bytes.fromhex(colors['bg'][1:])) < 390
    for attribute, color in ((20, int(dark)), (35, colorref(colors['bg'])),
                              (36, colorref(colors['text'])), (34, colorref(colors['border']))):
        value = wintypes.DWORD(color)
        results[attribute] = setter(int(window.winId()), attribute, ctypes.byref(value), ctypes.sizeof(value))
    return results


def control_icons():
    directory = resource_root() / 'assets' / 'ui'
    arrow, check = ((directory / name).as_posix() for name in ('chevron.png', 'check.png'))
    return (f'QComboBox::down-arrow {{ image: url("{arrow}"); width: 16px; height: 16px; }}'
            f'QCheckBox::indicator:checked {{ image: url("{check}"); }}')


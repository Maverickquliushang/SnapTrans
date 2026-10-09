"""Semantic themes. Saved artwork/annotation colors are never recolored."""
import re

# background, surface, input, button, hover, border, text, muted, accent, soft, on-accent
THEMES = {
    'ember': ('曜石红', '深色 · 经典黑红', ('#171a20', '#22262f', '#191d25', '#303642', '#414958', '#4a5465', '#edf0f6', '#acb7cb', '#d43a34', '#492b32', '#ffffff')),
    'daylight': ('晴空蓝', '浅色 · 清晰轻盈', ('#f4f7fb', '#ffffff', '#f8faff', '#e7edf6', '#d9e6f7', '#91a3bc', '#172b49', '#50647d', '#205bb8', '#e0ebff', '#ffffff')),
    'studio': ('柔光紫', '浅色 · 柔光与层次', ('#f5f3fa', '#ffffff', '#f8f7fc', '#eeebf7', '#e7e1f5', '#b1a9c8', '#292439', '#706781', '#6651d8', '#eae4fd', '#ffffff')),
    'violet': ('暮夜紫', '深色 · 蓝紫', ('#171727', '#232337', '#1c1c30', '#35354e', '#444463', '#676786', '#f0effa', '#b7b7d2', '#7151c6', '#39304f', '#ffffff')),
    'forest': ('松林绿', '深色 · 沉静护眼', ('#15231f', '#20332b', '#182920', '#30493d', '#3b594b', '#617e6f', '#eaf5ee', '#b0cbbb', '#287951', '#284a3b', '#ffffff')),
    'paper': ('暖纸棕', '浅色 · 温暖阅读', ('#f5f0e7', '#fffaf1', '#fcf7ee', '#e9dfcf', '#dfd1bd', '#ad987f', '#3d3026', '#73604d', '#8c4b24', '#f0dfc7', '#ffffff')),
    'graphite': ('石墨灰', '深色 · 简洁中性', ('#1d1e21', '#292b2f', '#212226', '#3a3c41', '#4b4e55', '#6b6f79', '#f1f2f4', '#b7bbc4', '#59667d', '#3a4352', '#ffffff')),
}
ROLES = ('bg', 'surface', 'input', 'button', 'hover', 'border', 'text', 'muted', 'accent', 'soft', 'on_accent')
_current = 'daylight'


def current_theme():
    return _current


def set_current_theme(name):
    global _current
    _current = name if name in THEMES else 'daylight'


def palette(name=None):
    return dict(zip(ROLES, THEMES[name or _current][2]))


def is_light(name=None):
    return sum(bytes.fromhex(palette(name)['bg'][1:])) >= 390


# Map the existing UI's shared shades once, preserving each widget's unmodified stylesheet.
SHADE_ROLES = {
    'bg': '171a20 1b1f27',
    'surface': '22262f 222730 212630 20242d 25282e 252a34 242932 292d34 20242b',
    'input': '191d25 191c23 15191f',
    'button': '303642 303541 303744 32363e 2a303a',
    'hover': '414958 3d414a 393e48 49404a 505663',
    'border': '323845 353d4c 3b4352 454d5c 3d4656 596476 343b48 626e81 424a59 3b424e 50545c 454952 4b4f58 404652 464b56 48505e 495366 596174 7e6266',
    'text': 'edf0f6 dce1eb f6f7fb dce2ee f0f2f7 dde1e9 e3e6ed f0f1f5 f1f3f6 e1e5ed e5e8ee eef0f5',
    'muted': '929caf acb7cb a2adc0 a5afbf 777f90 7c8799 8993a5 737a87 697384 ccbab9',
    'accent': 'f6534b ff6c63 ff786f ff5148 ff685f ff655b ff9b95 9b5954',
    'soft': '3a282b 4a3034 543237 554044 573d3d 604247 683d40 39282e 754842',
    'accent_text': 'ffaca6 ffb5af ffa39c ffb9b3 ffaaa4 ffb8af',
}
LOOKUP = {shade: role for role, shades in SHADE_ROLES.items() for shade in shades.split()}


def themed_css(css, name=None):
    colors = palette(name)
    colors['accent_text'] = colors['accent'] if is_light(name) else colors['text']
    return re.sub(r'#([0-9a-fA-F]{6})\b', lambda m: colors.get(LOOKUP.get(m[1].lower()), m[0]), css)

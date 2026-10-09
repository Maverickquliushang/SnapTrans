"""Local UI translation only. Captured text, model output and user prompts are untouched."""
import json
from functools import lru_cache
from weakref import WeakSet

_language = 'zh-CN'
_targets = WeakSet()
INTERFACE_LANGUAGES = {
    'zh-CN': '简体中文', 'zh-TW': '繁體中文', 'en': 'English',
    'ja': '日本語', 'ko': '한국어', 'fr': 'Français', 'de': 'Deutsch',
    'es': 'Español', 'pt': 'Português', 'ru': 'Русский',
}


class UiText(str):
    """Display text with its source recipe, independent of the current locale.

    Literal values (model names, user text, numbers) remain literal when composed
    with UI text. Keeping the recipe avoids ambiguous reverse translations.
    """
    def __new__(cls, render):
        value = super().__new__(cls, render())
        value.render = render
        return value

    def __add__(self, other):
        return UiText(lambda: rendered(self) + rendered(other))

    def __radd__(self, other):
        return UiText(lambda: rendered(other) + rendered(self))

    def strip(self, chars=None):
        return UiText(lambda: rendered(self).strip(chars))

    def __copy__(self):
        return UiText(self.render)

    def __deepcopy__(self, memo):
        return self.__copy__()


def rendered(value):
    return value.render() if isinstance(value, UiText) else str(value)


def bilingual(chinese, english):
    return UiText(lambda: chinese if _language == 'zh-CN' else english if _language == 'en'
                  else catalog(_language).get(chinese, english))


def ui_format(template, *values):
    """Format localized fragments while retaining literal interpolation values."""
    return UiText(lambda: template.format(*(rendered(v) if isinstance(v, UiText) else v for v in values)))


def remember(target, key, value, getter, setter):
    """Bind one display property. Callers must never bind editable content."""
    bindings = getattr(target, '_ui_text_bindings', None)
    if bindings is None:
        target._ui_text_bindings = bindings = {}
    if isinstance(value, UiText):
        bindings[key] = (value, getter, setter, getter(target))
        _targets.add(target)
    else:
        bindings.pop(key, None)


def refresh_texts():
    from shiboken6 import isValid
    for target in list(_targets):
        if not isValid(target):
            _targets.discard(target)
            continue
        for key, (value, getter, setter, previous) in list(target._ui_text_bindings.items()):
            # A native edit or item removal invalidates the old binding.
            if getter(target) != previous:
                target._ui_text_bindings.pop(key, None)
                continue
            text = rendered(value)
            if text != previous:
                blocked = target.blockSignals(True)
                try:
                    setter(target, text)
                finally:
                    target.blockSignals(blocked)
            target._ui_text_bindings[key] = (value, getter, setter, text)
    # Floating toolbars have explicit screen-bound positioning. Reflow their
    # translated labels without moving or resizing the actual captured image.
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app:
        for window in app.topLevelWidgets():
            if hasattr(window, '_position_toolbar'):
                window._position_toolbar()


def text_source(widget):
    binding = getattr(widget, '_ui_text_bindings', {}).get('text')
    return tr(binding[0]) if binding else widget.text()


def current_language():
    return _language


def set_language(value):
    global _language
    if value == 'system':
        from PySide6.QtCore import QLocale
        locale = QLocale.system()
        languages = locale.uiLanguages() or [locale.name()]
        tag = languages[0].replace('_', '-').lower()
        if tag.startswith('zh'):
            value = 'zh-TW' if any(p in tag.split('-') for p in ('tw', 'hk', 'mo', 'hant')) else 'zh-CN'
        else:
            value = tag.split('-')[0]
    _language = value if value in INTERFACE_LANGUAGES else 'en'
    refresh_texts()


@lru_cache(maxsize=10)
def catalog(language='en'):
    from .paths import resource_root
    path = resource_root() / 'assets' / 'i18n' / (language + '.json')
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}


def tr(text):
    if isinstance(text, UiText):
        return UiText(text.render)
    if isinstance(text, str) and text in catalog():
        return bilingual(text, catalog()[text])
    return text



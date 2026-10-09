"""Render English/Chinese language controls and check compact-window reachability."""
from pathlib import Path
from copy import deepcopy
import json
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PySide6.QtWidgets import QApplication
from snaptrans import __version__
from snaptrans.config import DEFAULT
from snaptrans.i18n import set_language, INTERFACE_LANGUAGES
from snaptrans.ui.fonts import initialize_fonts
from snaptrans.ui.settings_window import SettingsWindow
from snaptrans.ui.result_window import ResultWindow
from snaptrans.ui.theme import refresh_themes
from snaptrans.core.models import TranslationResult

app = QApplication([])
initialize_fonts(app)
out = ROOT/'docs'/'evidence'/f'v{__version__}'
out.mkdir(parents=True, exist_ok=True)
report = {}
for locale in INTERFACE_LANGUAGES:
    set_language(locale)
    refresh_themes('daylight')
    config = deepcopy(DEFAULT)
    config['window']['theme'] = 'daylight'
    config['translation'].update(source_lang='zh-CN', target_lang='en')
    window = SettingsWindow(config)
    window.resize(1080, 820)
    window.show()
    for page, name in ((1,'language-service'), (5,'language-preferences'), (1,'language-categories')):
        window.tabs.setCurrentIndex(page)
        if name.endswith('categories'):
            window.show_provider_picker()
        app.processEvents()
        window.grab().save(str(out/f'{locale}-{name}.png'))
    window.service_stack.setCurrentIndex(1)
    window.resize(540, 460)
    for page in range(6):
        window.tabs.setCurrentIndex(page)
        app.processEvents()
        assert window.width() == 540
        assert window.tabs.widget(page).horizontalScrollBar().maximum() == 0, (locale, page, window.tabs.widget(page).horizontalScrollBar().maximum())
    window.tabs.setCurrentIndex(5)
    window.grab().save(str(out/f'{locale}-small-preferences.png'))
    window.close()
    config['window']['display_mode'] = 'popup'
    result = ResultWindow(config['window'], config)
    result.set_original('你好，世界。', '你好，世界。')
    result.set_translation(TranslationResult('layout', 'Hello, world.', 1))
    result.resize(760, 620)
    result.show()
    app.processEvents()
    result.grab().save(str(out/f'{locale}-reading-languages.png'))
    result.resize(480, 420)
    app.processEvents()
    assert result.width() == 480, (locale, result.width())
    assert result.rect().contains(result.language_pair.mapTo(result, result.language_pair.rect().bottomRight()))
    result.close()
    report[locale] = {'compact_settings': [540, 460], 'compact_reading': [480, 420], 'six_pages_no_horizontal_scroll': True}
(out/'language-layout.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report))

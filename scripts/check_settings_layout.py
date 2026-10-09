"""Render real settings widgets and verify narrow navigation/save reachability."""
from pathlib import Path
from copy import deepcopy
import sys
import json
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PySide6.QtWidgets import QApplication
from snaptrans import __version__
from snaptrans.config import DEFAULT
from snaptrans.ui.fonts import initialize_fonts
from snaptrans.ui.settings_window import SettingsWindow
from snaptrans.ui.theme import refresh_themes

app = QApplication([])
initialize_fonts(app)
output = ROOT / 'docs' / 'evidence' / f'v{__version__}'
output.mkdir(parents=True, exist_ok=True)
report = {}
for theme in ('daylight', 'studio', 'ember'):
    refresh_themes(theme)
    config = deepcopy(DEFAULT)
    config['window']['theme'] = theme
    window = SettingsWindow(config)
    window.resize(1000, 800)
    window.show()
    for name, page in (('categories', 1), ('ocr-categories', 2), ('themes', 3), ('preferences', 5)):
        window.tabs.setCurrentIndex(page)
        if page == 1:
            window.show_provider_picker()
        if page == 2:
            window.show_ocr_picker()
        app.processEvents()
        window.grab().save(str(output / f'{theme}-{name}.png'))
    window.tabs.setCurrentIndex(2)
    window.select_ocr_provider('openai_vl')
    app.processEvents()
    window.grab().save(str(output / f'{theme}-ocr-detail.png'))
    window.resize(540, 460)
    for page in range(window.tabs.count()):
        window.tabs.setCurrentIndex(page)
        app.processEvents()
        assert window.width() == 540
        assert window.tabs.tabBar().isVisible()
        if page != 4:
            assert window.rect().contains(window.save_button.mapTo(window, window.save_button.rect().bottomRight()))
    window.tabs.setCurrentIndex(2)
    app.processEvents()
    assert window.tabs.widget(2).horizontalScrollBar().maximum() == 0
    window.grab().save(str(output / f'{theme}-small.png'))
    report[theme] = {'width': window.width(), 'height': window.height(), 'six_pages_accessible': True}
    window.close()
(output / 'settings-layout.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report))

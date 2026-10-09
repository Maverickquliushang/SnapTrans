"""Render the real engine picker with original category artwork."""
from pathlib import Path
from copy import deepcopy
import sys
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
for theme in ('daylight', 'studio', 'ember'):
    refresh_themes(theme)
    config = deepcopy(DEFAULT); config['window']['theme'] = theme
    window = SettingsWindow(config)
    window.tabs.setCurrentIndex(1); window.show_provider_picker()
    window.resize(920, 780); window.show(); app.processEvents()
    window.grab().save(str(output / f'{theme}-categories.png'))
    window.resize(540, 460); app.processEvents()
    window.grab().save(str(output / f'{theme}-categories-small.png'))
    window.close()
print('Category picker rendered in three themes, including narrow layout.')

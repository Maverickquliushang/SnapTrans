"""Render settings navigation and the reading layout using public sample text."""
from pathlib import Path
import sys, json
from copy import deepcopy
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PySide6.QtWidgets import QApplication
from snaptrans import __version__
from snaptrans.config import DEFAULT
from snaptrans.ui.settings_window import SettingsWindow
from snaptrans.ui.result_window import ResultWindow
from snaptrans.ui.themes import THEMES
from snaptrans.ui.theme import refresh_themes
from snaptrans.ui.fonts import initialize_fonts


def main():
    app = QApplication([])
    initialize_fonts(app)
    output = ROOT / 'docs' / 'evidence' / f'v{__version__}'
    output.mkdir(parents=True, exist_ok=True)
    report = {}
    for theme in THEMES:
        refresh_themes(theme)
        config = deepcopy(DEFAULT); config['window'].update(theme=theme, display_mode='popup')
        settings = SettingsWindow(config)
        settings.resize(860, 690); settings.show(); app.processEvents()
        for index in range(5):
            settings.tabs.setCurrentIndex(index); app.processEvents()
            settings.grab().save(str(output / f'{theme}-settings-{index}.png'))
        settings.tabs.setCurrentIndex(0)
        settings.resize(540, 460); app.processEvents()
        settings.grab().save(str(output / f'{theme}-settings-small.png'))
        report[theme] = {'settings_size': [settings.width(), settings.height()], 'sidebar_hidden': settings.sidebar.isHidden(),
                         'save_visible': settings.rect().contains(settings.save_button.mapTo(settings, settings.save_button.rect().bottomRight()))}
        result = ResultWindow(config['window'], config)
        result.set_busy(False)
        result.set_original('A clear interface makes everyday tasks easier.', 'A clear interface makes everyday tasks easier.\n\nKeep the image in the same place while translating. Compare the original and translated text without leaving your task.')
        result.translated.setPlainText('清晰的界面让日常操作更轻松。\n\n翻译时让图片保持在原处，无需离开当前任务，即可对照原文与译文。')
        result.status.setText('翻译完成')
        result.copy_target.setEnabled(True)
        result.show(); app.processEvents()
        result.grab().save(str(output / f'{theme}-reading.png'))
        result.resize(520, 420); app.processEvents()
        result.grab().save(str(output / f'{theme}-reading-small.png'))
        report[theme]['reading_size'] = [result.width(), result.height()]
        result.close(); settings.close(); app.processEvents()
    (output / 'layout-check.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()

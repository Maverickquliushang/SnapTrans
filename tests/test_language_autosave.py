from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from snaptrans.app import Application
from snaptrans.config import DEFAULT, ConfigStore
from snaptrans.i18n import INTERFACE_LANGUAGES, catalog, current_language, set_language, tr
from snaptrans.ui.settings_window import SettingsWindow


@pytest.mark.parametrize('dirty', [False, True])
def test_select_language_immediately_saves_only_language(qt_app, tmp_path, dirty):
    set_language('zh-CN')
    config = deepcopy(DEFAULT)
    store = ConfigStore(tmp_path / 'config.json')
    store.save(config)
    window = SettingsWindow(config)
    app = SimpleNamespace(config=deepcopy(config), store=store, settings=window)
    window.interface_language_requested.connect(lambda value: Application.save_interface_language(app, value))
    saves = Mock()
    window.save_requested.connect(saves)
    if dirty:
        window.select_provider('qwen')
        window.model.setText('unsaved-model')
        window.api_key.setText('synthetic-draft')
    window.tabs.setCurrentIndex(5)
    for locale in INTERFACE_LANGUAGES:
        window.interface_language.setCurrentIndex(window.interface_language.findData(locale))
        assert current_language() == locale
        assert window.page_title.text() == str(tr('偏好设置'))
        assert window.interface_language.itemText(0) == str(tr('跟随系统'))
        assert window._dirty == dirty
        expected = deepcopy(config)
        expected['interface']['language'] = locale
        assert store.load() == expected == app.config
        for code, name in INTERFACE_LANGUAGES.items():
            assert window.interface_language.itemText(window.interface_language.findData(code)) == name
        if dirty:
            assert window.model.text() == 'unsaved-model'
            assert window.api_key.text() == 'synthetic-draft'
    saves.assert_not_called()
    window.close()
    set_language('zh-CN')


def test_failed_language_autosave_keeps_previous_locale_and_draft(qt_app):
    set_language('zh-CN')
    config = deepcopy(DEFAULT)
    config['interface']['language'] = 'zh-CN'
    window = SettingsWindow(config)
    window.model.setText('draft-model')
    store = Mock()
    store.save.side_effect = OSError('synthetic failure')
    app = SimpleNamespace(config=deepcopy(config), store=store, settings=window)
    window.interface_language_requested.connect(lambda value: Application.save_interface_language(app, value))
    window.interface_language.setCurrentIndex(window.interface_language.findData('en'))
    assert current_language() == 'zh-CN'
    assert window.interface_language.currentData() == 'zh-CN'
    assert app.config == config
    assert window.model.text() == 'draft-model' and window._dirty
    assert '无法保存' in window.message.text()
    window.close()


def test_all_interface_catalogs_cover_english_catalog():
    assert DEFAULT['window']['theme'] == 'daylight'
    for locale in INTERFACE_LANGUAGES:
        if locale == 'zh-CN':
            continue
        translated = catalog(locale)
        assert set(catalog()) <= set(translated)
        assert not any('ZXQ' in value or 'ZZNLINEZZ' in value or 'ZZTABZZ' in value
                       for value in translated.values())

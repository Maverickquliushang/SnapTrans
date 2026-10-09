from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QLocale, QPointF
from snaptrans.config import DEFAULT, validate
from snaptrans.i18n import set_language, current_language, tr, ui_format
from snaptrans.ui.settings_window import SettingsWindow
from snaptrans.ui.tray import Tray
from snaptrans.paths import resource_root
from snaptrans.core.models import OcrResult, TranslationResult
from test_v1100 import original_pin
from test_workspace_interop import next_capture


@pytest.fixture(autouse=True)
def restore_language():
    set_language('zh-CN')
    yield
    set_language('zh-CN')


@pytest.mark.parametrize('system,expected', [('en_US', 'en'), ('zh_CN', 'zh-CN'), ('zh_TW', 'zh-TW'), ('ja_JP', 'ja'), ('ar_SA', 'en')])
def test_default_follows_system_without_overriding_explicit_choice(monkeypatch, system, expected):
    monkeypatch.setattr(QLocale, 'system', lambda: QLocale(system))
    cfg = deepcopy(DEFAULT)
    assert cfg['interface']['language'] == 'system'
    cfg.pop('interface')
    assert validate(cfg)['interface']['language'] == 'system'
    set_language(DEFAULT['interface']['language'])
    assert current_language() == expected
    cfg['interface'] = {'language': 'en'}
    assert validate(cfg)['interface']['language'] == 'en'


@pytest.mark.parametrize('initial', ['zh-CN', 'en'])
def test_live_settings_and_tray_round_trip_preserves_drafts(qt_app, initial):
    set_language(initial)
    window = SettingsWindow(deepcopy(DEFAULT))
    tray = Tray(resource_root() / 'assets/icon.ico')
    tray.update_hotkeys({'translate': 'F3', 'ocr': 'Alt+X'})
    window.tabs.setCurrentIndex(5)
    window.select_provider('qwen')
    window.model.setText('My original model 模型')
    window.api_key.setText('synthetic-kept-draft')
    window.prompt_editor.editor.setPlainText('设置 原文 Hello {target_language}')
    window.translation_languages.set_pair('ja', 'fr')
    window.interface_language.setCurrentIndex(window.interface_language.findData('system'))
    signals = Mock()
    window.translation_languages.changed.connect(signals)
    window.interface_language.currentIndexChanged.connect(signals)
    window.provider.currentIndexChanged.connect(signals)
    window.save_requested.connect(signals)
    window._dirty = False
    position, size = window.pos(), window.size()
    for locale, title in [('en', 'Preferences'), ('zh-CN', '偏好设置'), ('en', 'Preferences')]:
        set_language(locale)
        assert window.page_title.text() == title
        assert window.navigation.item(5).text() == title
        assert window.tabs.tabText(5) == title
        assert window.save_button.text() == ('Save changes' if locale == 'en' else '保存更改')
        assert window.translation_languages.target.currentText() == ('French' if locale == 'en' else '法语')
        assert window.windowTitle().endswith('Settings' if locale == 'en' else '设置')
        assert tray.capture_actions[0].text() == ('Capture\tF3' if locale == 'en' else '截图\tF3')
        assert window.model.text() == 'My original model 模型'
        assert window.api_key.text() == 'synthetic-kept-draft'
        assert window.prompt_editor.editor.toPlainText() == '设置 原文 Hello {target_language}'
        assert window.translation_languages.pair() == ('ja', 'fr')
        assert window.interface_language.currentData() == 'system'
        assert not window._dirty
        assert (window.pos(), window.size()) == (position, size)
    signals.assert_not_called()
    window.close()
    tray.hide()
    tray.deleteLater()


def test_display_bindings_retain_exact_sources_and_literal_content(qt_app):
    from snaptrans.ui.localized_widgets import QLabel as LiveLabel, QLineEdit, QComboBox as LiveCombo
    first, second = LiveLabel(tr('原文')), LiveLabel(tr('查看原文'))
    # Both source phrases may share one English translation. They must round-trip independently.
    dynamic = LiveLabel(tr('连接成功：') + '设置')
    progress = LiveLabel(ui_format('{} · {}{}', tr('正在翻译'), 7, tr(' 秒')))
    editor = QLineEdit('原文')
    editor.setPlaceholderText(tr('译文'))
    combo = LiveCombo()
    combo.addItem(tr('阅读弹窗'), 'popup')
    combo.clear()
    combo.addItem(tr('截图工作区'), 'overlay')
    set_language('en')
    assert dynamic.text().endswith('设置')
    assert editor.text() == '原文' and editor.placeholderText() == 'Translation'
    assert '7' in progress.text() and '正在翻译' not in progress.text()
    assert combo.currentData() == 'overlay' and combo.currentText() == str(tr('截图工作区'))
    set_language('zh-CN')
    assert (first.text(), second.text()) == ('原文', '查看原文')
    assert dynamic.text() == '连接成功：设置'
    assert progress.text() == '正在翻译 · 7 秒'
    dynamic.setText('literal replacement')
    set_language('en')
    assert dynamic.text() == 'literal replacement'
    for item in (first, second, dynamic, progress, editor, combo):
        item.close()


def test_language_switch_preserves_pin_edits_and_queued_ocr(qt_app):
    controller, first, ocr, _, network = original_pin(qt_app)
    first.document.apply(('pen', [QPointF(4, 10), QPointF(80, 10)], '#ff0000', 3, ''))
    first.set_zoom(1.3)
    first.translate_button.click()
    first_id = ocr.submit.call_args.args[0].request_id
    next_capture(controller)
    controller.pin_selection()
    second = controller.pins[1]
    second.translate_button.click()
    image, index, zoom, position = first.pixmap.toImage(), first.document.index, first.zoom, first.pos()
    assert ocr.submit.call_count == 1
    set_language('en')
    assert first.busy and second.busy
    assert (first.document.index, first.zoom, first.pos()) == (index, zoom, position)
    assert first.pixmap.toImage() == image
    ocr.succeeded.emit(OcrResult(first_id, 'First original.', [], 1))
    assert ocr.submit.call_count == 2  # Locale changes cannot strand the queued job.
    second_id = ocr.submit.call_args.args[0].request_id
    ocr.succeeded.emit(OcrResult(second_id, 'Second original.', [], 1))
    network.succeeded.emit(TranslationResult(first_id, '第一张。', 1))
    network.succeeded.emit(TranslationResult(second_id, '第二张。', 1))
    assert first.state['translation'] == '第一张。'
    assert second.state['translation'] == '第二张。'
    count = len(network.sent)
    set_language('zh-CN')
    assert len(network.sent) == count
    assert first.can_compare and second.can_compare
    controller.close()


@pytest.mark.parametrize('failure', [False, True])
def test_application_changes_language_only_after_successful_save(qt_app, failure):
    from snaptrans.app import Application
    window = SettingsWindow(deepcopy(DEFAULT))
    window.tabs.setCurrentIndex(5)
    config = deepcopy(DEFAULT)
    config['interface']['language'] = 'en'
    store, credentials, hotkeys, tray = Mock(), Mock(), Mock(), Mock()
    if failure:
        store.save.side_effect = OSError('synthetic write failure')
    app = SimpleNamespace(config=deepcopy(DEFAULT), store=store, credentials=credentials,
                          hotkeys=hotkeys, tray=tray, controller=SimpleNamespace(result=None), settings=window)
    Application.save_settings(app, config, '')
    assert current_language() == ('zh-CN' if failure else 'en')
    assert window.page_title.text() == ('偏好设置' if failure else 'Preferences')
    assert app.config['interface']['language'] == ('system' if failure else 'en')
    if not failure:
        assert window.message.text() == 'Interface language updated. No restart needed.'
    window.close()


def test_preferences_translation_languages_sync_save_and_discard(qt_app, tmp_path):
    from snaptrans.config import ConfigStore
    from snaptrans.ui.result_window import ResultWindow
    config = deepcopy(DEFAULT)
    window = SettingsWindow(config)
    window.tabs.setCurrentIndex(5)
    editor = window.preference_languages
    editor.source.setCurrentIndex(editor.source.findData('zh-CN'))
    editor.target.setCurrentIndex(editor.target.findData('en'))
    assert window.translation_languages.pair() == ('zh-CN', 'en')
    assert window._dirty and config == DEFAULT
    window.translation_languages.target.setCurrentIndex(window.translation_languages.target.findData('ja'))
    assert editor.pair() == ('zh-CN', 'ja')
    emitted = []
    window.save_requested.connect(lambda cfg, secret: emitted.append(cfg))
    window.save_button.click()
    assert emitted[0]['translation']['source_lang'] == 'zh-CN'
    assert emitted[0]['translation']['target_lang'] == 'ja'
    store = ConfigStore(tmp_path / 'config.json')
    store.save(emitted[0])
    saved = store.load()
    window.close()
    result = ResultWindow(saved['window'], saved)
    assert result.language_pair.pair() == ('zh-CN', 'ja')
    result.close()
    reopened = SettingsWindow(saved)
    assert reopened.preference_languages.pair() == ('zh-CN', 'ja')
    reopened.preference_languages.target.setCurrentIndex(reopened.preference_languages.target.findData('fr'))
    reopened.close()
    assert store.load()['translation']['target_lang'] == 'ja'

import asyncio
import json
from copy import deepcopy
from dataclasses import replace
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from PySide6.QtWidgets import QLabel, QAbstractButton
from snaptrans.config import DEFAULT, validate, ConfigStore
from snaptrans.core.models import ProviderSettings, TranslationRequest, TranslationResult, AppError
from snaptrans.i18n import set_language, current_language, tr
from snaptrans.providers.catalog import profile_for, default_profile, CHAT_PRESETS
from snaptrans.providers.prompts import translation_prompt, ACADEMIC, LEGACY_ACADEMIC
from snaptrans.providers.translation_services import TranslationServices
from snaptrans.providers.traditional import TraditionalProvider
from snaptrans.providers.compatible import CompatibleProvider
from snaptrans.providers.claude import ClaudeProvider
from snaptrans.providers.web_translation import website_url, extraction_script
from snaptrans.ui.settings_window import SettingsWindow
from snaptrans.ui.provider_picker import GROUPS
from test_ocr_workspace import workspace
from test_v1100 import original_pin


def test_language_config_migration_and_independent_preferences(tmp_path):
    cfg = deepcopy(DEFAULT)
    cfg.pop('interface')
    cfg['prompts']['academic'] = LEGACY_ACADEMIC
    cfg['translation'].update(source_lang='auto', target_lang='ja')
    result = validate(cfg)
    assert result['interface']['language'] == 'system'
    assert result['prompts']['academic'] == ACADEMIC
    result['interface']['language'] = 'en'
    result['prompts']['academic'] = 'Keep my custom prompt 原样 {source_language}.'
    store = ConfigStore(tmp_path / 'config.json')
    store.save(result)
    assert store.load() == result
    assert profile_for(result, 'qwen')['target_lang'] == 'ja'
    assert profile_for(result, 'qwen')['source_lang'] == 'auto'
    assert 'domestic' not in GROUPS and 'global' not in GROUPS
    assert set(CHAT_PRESETS) | {'nvidia'} == set(GROUPS['models'][4])


@pytest.mark.parametrize('kind,source,target,expected', [
    ('baidu', 'zh-CN', 'ja', ('zh', 'jp')),
    ('baidu', 'auto', 'fr', ('auto', 'fra')),
    ('youdao', 'zh-TW', 'en', ('zh-CHT', 'en')),
    ('youdao', 'auto', 'zh-TW', ('auto', 'zh-CHT')),
    ('deepl', 'zh-CN', 'en', ('ZH', 'EN-US')),
    ('deepl', 'auto', 'zh-TW', (None, 'ZH-HANT')),
    ('libre', 'auto', 'zh-CN', ('auto', 'zh')),
    ('libre', 'ja', 'de', ('ja', 'de')),
])
def test_traditional_language_payloads(kind, source, target, expected):
    async def run():
        settings = ProviderSettings(**(default_profile(kind) | dict(source_lang=source, target_lang=target, app_id='synthetic')))
        provider = TranslationServices(trust_env=False)
        try:
            _, payload = provider.payload(TranslationRequest('id', '公开例句', settings), 'synthetic')
            data = payload.get('json', payload.get('data'))
            keys = ('source_lang', 'target_lang') if kind == 'deepl' else ('source', 'target') if kind == 'libre' else ('from', 'to')
            assert (data.get(keys[0]), data[keys[1]]) == expected
        finally:
            await provider.aclose()
    asyncio.run(run())


@pytest.mark.parametrize('kind', ['google', 'microsoft'])
@pytest.mark.parametrize('source', ['auto', 'zh-CN'])
def test_google_microsoft_send_selected_languages(kind, source):
    async def run():
        def handle(req):
            data = json.loads(req.content)
            if kind == 'google':
                assert data['target'] == 'ja'
                assert data.get('source') == (None if source == 'auto' else 'zh-CN')
                return httpx.Response(200, json={'data': {'translations': [{'translatedText': 'こんにちは'}]}})
            assert req.url.params['to'] == 'ja'
            assert req.url.params.get('from') == (None if source == 'auto' else 'zh-Hans')
            return httpx.Response(200, json=[{'translations': [{'text': 'こんにちは'}]}])
        provider = TraditionalProvider(httpx.MockTransport(handle), trust_env=False)
        try:
            settings = ProviderSettings(**(default_profile(kind) | dict(source_lang=source, target_lang='ja')))
            result = await provider.translate(TranslationRequest('id', '你好', settings), 'synthetic')
            assert result.text == 'こんにちは'
        finally:
            await provider.aclose()
    asyncio.run(run())


@pytest.mark.parametrize('kind', ['compatible', 'claude'])
def test_llm_direction_and_prompt_placeholders_reach_protocol(kind):
    async def run():
        settings = ProviderSettings(**(default_profile(kind) | dict(source_lang='zh-CN', target_lang='en', model='synthetic', base_url='https://example.invalid/v1', mode='academic')))
        custom = 'Keep notation {"x": 1}. Translate from {source_language} to {target_language}.'
        settings = replace(settings, academic_prompt=custom)
        def handle(req):
            data = json.loads(req.content)
            prompt = data['system'] if kind == 'claude' else data['messages'][0]['content']
            assert 'Simplified Chinese -> English' in prompt
            assert '{"x": 1}' in prompt and '{target_language}' not in prompt
            if kind == 'claude':
                return httpx.Response(200, json={'content': [{'type': 'text', 'text': 'Hello'}], 'stop_reason': 'end_turn'})
            assert data['messages'][1]['content'] == '你好'
            return httpx.Response(200, json={'choices': [{'message': {'content': 'Hello'}, 'finish_reason': 'stop'}]})
        provider = (ClaudeProvider if kind == 'claude' else CompatibleProvider)(httpx.MockTransport(handle), trust_env=False)
        try:
            assert (await provider.translate(TranslationRequest('id', '你好', settings), 'synthetic')).text == 'Hello'
            assert settings.academic_prompt == custom
        finally:
            await provider.aclose()
    asyncio.run(run())


def test_web_directions_and_explicit_unsupported_entries():
    google = parse_qs(urlsplit(website_url('google_web', '你好', 'zh-CN', 'en')).query)
    assert google['sl'] == ['zh-CN'] and google['tl'] == ['en'] and google['text'] == ['你好']
    bing = parse_qs(urlsplit(website_url('bing_web', 'Bonjour', 'auto', 'zh-TW')).query)
    assert bing['from'] == ['auto-detect'] and bing['to'] == ['zh-Hant']
    assert 'lang=jp2fra' in website_url('baidu_web', 'Hello', 'ja', 'fr')
    assert '#auto/de/' in website_url('deepl_web', 'Hello', 'auto', 'de')
    assert '[lang^=de]' in extraction_script('deepl_web', 'de')
    from snaptrans.languages import service_pair
    for kind in ('youdao_web', 'tencent_web'):
        with pytest.raises(AppError, match='仅支持英译中'):
            website_url(kind, 'Hello', 'ja', 'en')
    with pytest.raises(AppError, match='明确的原文语言'):
        service_pair('mymemory', 'auto', 'en')


def test_mymemory_selected_pair_and_memory_markup():
    from snaptrans.providers.mymemory import MyMemoryProvider
    async def run():
        def handle(req):
            assert req.url.params['langpair'] == 'zh-CN|en'
            return httpx.Response(200, json={'responseStatus': 200, 'responseData': {'translatedText': '<g id="252">Hello </g>World.'}})
        provider = MyMemoryProvider(httpx.MockTransport(handle), trust_env=False)
        try:
            settings = ProviderSettings(**(default_profile('mymemory') | dict(source_lang='zh-CN', target_lang='en')))
            assert (await provider.translate(TranslationRequest('id', '你好，世界。', settings))).text == 'Hello World.'
            assert (await provider.translate(TranslationRequest('id', '<g id="252">你好</g>', settings))).text.startswith('<g')
        finally:
            await provider.aclose()
    asyncio.run(run())


def test_settings_language_drafts_save_and_cancel(qt_app):
    config = deepcopy(DEFAULT)
    window = SettingsWindow(config)
    window.translation_languages.set_pair('zh-CN', 'en')
    window.select_provider('qwen')
    assert window._read_translation('qwen')['target_lang'] == 'en'
    window.interface_language.setCurrentIndex(window.interface_language.findData('en'))
    assert config == DEFAULT and current_language() == 'zh-CN'
    emitted = []
    window.save_requested.connect(lambda cfg, key: emitted.append(cfg))
    window.save_button.click()
    assert emitted[0]['translation']['source_lang'] == 'zh-CN'
    assert emitted[0]['interface']['language'] == 'en'
    window.saved(emitted[0])
    assert '无需重启' in window.message.text()
    window.close()
    cancelled = SettingsWindow(config)
    assert cancelled.translation_languages.pair() == ('en', 'zh-CN')
    cancelled.close()


def test_workspace_pair_switch_retranslation_and_pin_snapshot(qt_app):
    controller, ocr, network = workspace(qt_app)
    result = controller.result
    result.set_original('你好', '你好')
    result.language_pair.swap_pair()
    assert result.overlay.languages.pair() == ('zh-CN', 'en')
    assert not network.sent  # OCR-only workspace waits for explicit translation.
    controller.switch_workspace('translate')
    request = network.sent[-1][0]
    assert request.settings_snapshot.target_lang == 'en'
    assert not result.overlay.languages.isEnabled()
    network.succeeded.emit(TranslationResult(request.request_id, 'Hello', 1))
    assert result.overlay.languages.isEnabled()
    result.language_pair.target.setCurrentIndex(result.language_pair.target.findData('ja'))
    assert network.sent[-1][0].settings_snapshot.target_lang == 'ja'
    assert result.translated.toPlainText() == ''
    network.succeeded.emit(TranslationResult(network.sent[-1][0].request_id, 'こんにちは', 1))
    controller.pin_selection()
    pin = controller.pins[0]
    assert pin.languages.pair() == ('zh-CN', 'ja')
    pin.workspace_button.click()
    assert controller.result.language_pair.pair() == ('zh-CN', 'ja')
    controller.close()


def test_pin_languages_apply_in_place(qt_app):
    controller, pin, ocr, _, network = original_pin(qt_app)
    pin.languages.set_pair('ja', 'en')
    pin.languages.changed.emit('ja', 'en')
    pin.state['source'] = 'こんにちは'
    pin.translate_button.click()
    request = network.sent[-1][0]
    assert (request.settings_snapshot.source_lang, request.settings_snapshot.target_lang) == ('ja', 'en')
    network.succeeded.emit(TranslationResult(request.request_id, 'Hello', 1))
    assert pin.isVisible() and pin.state['target_lang'] == 'en' and pin.can_compare
    assert not controller.result.isVisible()
    controller.close()


def test_english_ui_preserves_inputs_and_translated_content(qt_app):
    set_language('en')
    try:
        config = deepcopy(DEFAULT)
        config['prompts']['academic'] = '原文 {target_language} {"保持": true}'
        window = SettingsWindow(config)
        window.show()
        qt_app.processEvents()
        assert window.page_title.text() == 'Capture'
        window.tabs.setCurrentIndex(1)
        assert window.page_title.text() == 'Translation'
        assert window.save_button.text() == 'Save changes'
        window.provider_picker.show_group('models')
        assert window.provider_picker.heading.text() == 'Large language models · Services'
        assert window.provider_picker.buttons['qwen'].text().startswith('Qwen\n')
        window.select_ocr_provider('openai_vl')
        assert window.ocr_name.text() == 'OpenAI Vision'
        assert window.prompt_editor.editor.toPlainText() == config['prompts']['academic']
        assert window.translation_languages.pair() == ('en', 'zh-CN')
        assert window.translation_languages.target.currentText() == 'Simplified Chinese'
        window.close()
        controller, _, _ = workspace(qt_app)
        result = controller.result
        result.set_original('原文', '原文')
        result.set_translation(TranslationResult('ui', '译文', 0))
        assert result.source_text() == '原文' and result.translated.toPlainText() == '译文'
        assert result.translation_tag.text() == 'Translation · Simplified Chinese'
        assert result.status.text() == 'Translation complete'
        controller.close()
    finally:
        set_language('zh-CN')

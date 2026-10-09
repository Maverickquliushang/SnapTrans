import asyncio
import base64
import io
import json
from copy import deepcopy
from unittest.mock import Mock
import httpx
import pytest
from PIL import Image
from snaptrans.config import DEFAULT, validate, ConfigStore
from snaptrans.credentials import CredentialStore
from snaptrans.core.models import CaptureFrame, AppError
from snaptrans.providers.ocr_catalog import default_ocr, credential_target, get_ocr_secret
from snaptrans.providers.vision_ocr import VisionOcrProvider
from snaptrans.ui.settings_window import SettingsWindow


def frame():
    im = Image.new('RGB', (40, 20), '#e0af95')
    return CaptureFrame('test-vision', 'test-screen', (0, 0, 40, 20), (0, 0, 40, 20),
                        (0, 0, 40, 20), 40, 20, im.tobytes())


@pytest.mark.parametrize('kind', ['qwen_vl', 'glm_vl', 'openai_vl', 'gemini_vl', 'ollama_vl', 'lmstudio_vl', 'compatible_vl'])
def test_vision_payload_preserves_pixels_and_paragraphs(kind):
    settings = default_ocr(kind)
    settings['model'] = settings['model'] or 'vision-model'
    settings['base_url'] = settings['base_url'] or 'https://example.invalid/v1'
    received = []
    def handler(request):
        received.append(request)
        data = json.loads(request.content)
        assert data['model'] == settings['model']
        assert data.get('max_completion_tokens' if kind == 'openai_vl' else 'max_tokens') == settings['max_tokens']
        image = data['messages'][0]['content'][1]['image_url']['url']
        decoded = Image.open(io.BytesIO(base64.b64decode(image.split(',', 1)[1])))
        assert decoded.size == (40, 20) and decoded.tobytes() == frame().rgb_bytes
        assert ('authorization' in request.headers) == settings['requires_api_key']
        return httpx.Response(200, json={'choices': [{'finish_reason': 'stop', 'message': {'content': 'Line one.\n\nLine two.'}}]})
    async def run():
        client = VisionOcrProvider(httpx.MockTransport(handler))
        try:
            result = await client.recognize(frame(), settings, 'synthetic-secret' if settings['requires_api_key'] else '')
            assert result.raw_text == 'Line one.\n\nLine two.' and result.lines == []
        finally:
            await client.aclose()
    asyncio.run(run())
    assert len(received) == 1 and str(received[0].url).endswith('/chat/completions')


@pytest.mark.parametrize('mode,code', [('length', 'OCR_TRUNCATED'), ('empty', 'NO_TEXT'), ('bad', 'OCR_FORMAT'),
                                      ('redirect', 'HTTP'), ('timeout', 'OCR_TIMEOUT')])
def test_vision_failures_have_no_fallback_or_redirect(mode, code):
    seen = []
    def handler(request):
        seen.append(request)
        if mode == 'timeout':
            raise httpx.ReadTimeout('synthetic timeout')
        if mode == 'redirect':
            return httpx.Response(302, headers={'Location': 'https://other.invalid/steal'})
        if mode == 'bad':
            return httpx.Response(200, json={})
        return httpx.Response(200, json={'choices': [{'finish_reason': 'length' if mode == 'length' else 'stop',
                                                     'message': {'content': 'partial' if mode == 'length' else ''}}]})
    async def run():
        client = VisionOcrProvider(httpx.MockTransport(handler))
        try:
            with pytest.raises(AppError) as caught:
                await client.recognize(frame(), default_ocr('openai_vl'), 'synthetic-secret')
            assert caught.value.code == code
        finally:
            await client.aclose()
    asyncio.run(run())
    assert len(seen) == 1


def test_ocr_credentials_are_separate_and_transactional(tmp_path):
    store = CredentialStore(tmp_path / 'keys.json')
    cfg = default_ocr('openai_vl')
    url, scope = credential_target(cfg)
    store.save(url, 'translation-secret', False)
    snapshot = store.snapshot()
    store.save(url, 'ocr-secret', False, scope=scope)
    assert get_ocr_secret(store, cfg) == 'ocr-secret'
    assert store.get(url) == 'translation-secret'
    assert 'secret' not in store.path.read_text()
    store.restore(snapshot)
    assert store.get(url) == 'translation-secret' and get_ocr_secret(store, cfg) == ''


def test_first_run_marker_survives_generated_config_and_legacy_migration(tmp_path):
    store = ConfigStore(tmp_path / 'config.json')
    first = store.load()
    assert store.path.exists() and not store.load()['onboarding']['completed']
    first.pop('onboarding')
    first['hotkeys']['translate'] = 'F4'
    store.path.write_text(json.dumps(first))
    legacy = store.load()
    assert legacy['hotkeys']['translate'] == 'F4' and not legacy['onboarding']['completed']
    legacy['onboarding']['completed'] = True
    store.save(legacy)
    assert store.load()['onboarding']['completed']


def test_ocr_picker_drafts_scoped_keys_and_explicit_save(qt_app):
    original = deepcopy(DEFAULT)
    window = SettingsWindow(original)
    window.show()
    qt_app.processEvents()
    window.tabs.setCurrentIndex(2)
    window.show_ocr_picker()
    window.ocr_picker.show_group('models')
    window.ocr_picker.buttons['openai_vl'].click()
    assert window.ocr_stack.currentIndex() == 1
    window.ocr_model.setCurrentText('my-vision-model')
    window.ocr_key.setText('synthetic-key')
    window.ocr_save_key.setChecked(True)
    window.select_ocr_provider('qwen_vl')
    assert not window.ocr_secret()
    window.select_ocr_provider('openai_vl')
    assert window.ocr_model.currentText() == 'my-vision-model' and window.ocr_secret() == 'synthetic-key'
    assert original == DEFAULT
    emitted = []
    window.save_requested.connect(lambda config, secret: emitted.append(config))
    window.save_button.click()
    assert emitted[0]['ocr']['provider'] == 'openai_vl'
    assert emitted[0]['onboarding']['completed']
    assert 'synthetic-key' not in json.dumps(emitted)
    assert any(item[1] == 'ocr:openai_vl' and item[2] == 'synthetic-key' for item in window.ocr_key_updates())
    window.ocr_key.clear()
    window.ocr_base_url.setText('https://another.invalid/v1')
    assert window.ocr_secret() == ''
    window.close()
    assert window._ocr_draft_keys == {}


def test_themes_preferences_and_version_are_visible(qt_app):
    from snaptrans import __version__
    window = SettingsWindow(DEFAULT)
    assert __version__ in window.windowTitle()
    assert window.tabs.tabText(3) == '主题' and window.tabs.tabText(5) == '偏好设置'
    assert window.tabs.widget(5).isAncestorOf(window.font_size)
    assert not window.tabs.widget(3).isAncestorOf(window.font_size)
    window.open_settings_on_start.setChecked(True)
    emitted = []
    window.save_requested.connect(lambda config, secret: emitted.append(config))
    window.save_button.click()
    assert emitted[0]['startup']['open_settings']
    window.close()

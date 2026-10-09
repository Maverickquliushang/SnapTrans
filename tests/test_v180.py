import asyncio
import hashlib
import json
from copy import deepcopy
from dataclasses import replace
from urllib.parse import parse_qs
import httpx
import pytest
import numpy as np
from PySide6.QtCore import QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QPixmap, QPainter, QColor
from PySide6.QtTest import QTest
from snaptrans.config import DEFAULT, validate_translation, ConfigStore
from snaptrans.core.models import ProviderSettings, TranslationRequest, AppError
from snaptrans.providers.catalog import PROVIDERS, CHAT_PRESETS, default_profile
from snaptrans.providers.compatible import CompatibleProvider
from snaptrans.providers.claude import ClaudeProvider
from snaptrans.providers.translation_services import TranslationServices
from snaptrans.ui.brush_options import mosaic_grid
from snaptrans.ui.pin_editor import PinDocument
from snaptrans.ui.pinned_image import PinnedImage
from snaptrans.ui.ocr_canvas import OcrCanvas
from snaptrans.ui.settings_window import SettingsWindow
from snaptrans.ui.provider_picker import GROUPS, SERVICES


def patterned():
    image = QPixmap(320, 160)
    image.fill(QColor('white'))
    p = QPainter(image)
    for x in range(0, 320, 4):
        p.fillRect(x, 0, 2, 160, QColor('#253e68'))
    p.end()
    return image


def test_mosaic_smear_export_undo_and_eraser(qt_app):
    doc = PinDocument(patterned())
    before = doc.current.toImage()
    points = [QPointF(40, 60), QPointF(140, 60), QPointF(140, 110)]
    doc.apply(('mosaic', points, '', 3, '', {'diameter': 30, 'mosaic_grid': mosaic_grid(doc.current, 12)}))
    after = doc.current.toImage()
    assert after != before
    assert after.pixelColor(90, 60) != before.pixelColor(90, 60)
    assert after.pixelColor(90, 110) == before.pixelColor(90, 110)  # No rectangular fill between bent strokes.
    assert after.pixelColor(90, 30) == before.pixelColor(90, 30)
    doc.undo(); assert doc.current.toImage() == before
    doc.redo(); assert doc.current.toImage() == after
    doc.apply(('eraser', points, '', 3, '', {'diameter': 40}))
    assert doc.current.toImage() == before
    assert doc.base.toImage() == before


def test_independent_sizes_palette_and_cursor(qt_app):
    pin = PinnedImage(patterned(), QPoint(20, 20))
    pin.show(); qt_app.processEvents()
    pin.set_tool('pen'); pin.options.size.setValue(11)
    pin.options.swatches['#438cff'].click()
    assert pin.image.stroke_width == 11 and pin.image.color == '#438cff'
    pin.set_tool('text'); pin.options.size.setValue(36)
    pin.set_tool('eraser'); pin.options.size.setValue(10)
    small = pin.image.cursor().pixmap().size()
    pin.options.size.setValue(90)
    assert pin.image.cursor().pixmap().width() > small.width()
    pin.set_tool('pen'); assert pin.options.size.value() == 11
    pin.set_tool('text'); assert pin.options.size.value() == 36
    pin.set_tool('move'); assert pin.options.isHidden()
    pin.close()


def test_workspace_mosaic_works_on_translated_surface_and_transfers_to_pin(qt_app):
    canvas = OcrCanvas()
    screen = qt_app.primaryScreen()
    source = patterned()
    canvas.attach_capture(screen, source, QRectF(0, 0, screen.size().width(), screen.size().height()))
    canvas.set_mode(False)
    canvas.set_content('示例译文 Sample translation')
    editor = canvas.editor
    editor.set_tool('mosaic')
    base = canvas.unannotated_selection()
    editor.ensure()
    editor.points = [QPointF(10, 40), QPointF(270, 40)]
    editor.stroke_options = {'diameter': 50, 'mosaic_grid': mosaic_grid(base, 16)}
    editor.document.apply(editor.operation()); editor.points = []
    result = canvas.rendered_selection().toImage()
    assert result != base.toImage()
    pin = PinnedImage(base, QPoint(40, 40), annotations=editor.snapshot())
    pinned = pin.pixmap.toImage()
    assert pinned.size() == result.size()
    # Drawing onto RGB vs compositing an ARGB layer rounds antialiased edges
    # differently by at most one channel level. The masked footprint is identical.
    delta = np.frombuffer(pinned.constBits(), dtype=np.uint8).astype(int) - np.frombuffer(result.constBits(), dtype=np.uint8)
    assert abs(delta).max() <= 1
    editor.undo(); assert canvas.rendered_selection().toImage() == base.toImage()
    pin.close(); canvas.close()


def test_grouped_cards_profiles_and_cancel(qt_app, tmp_path):
    assert set(PROVIDERS) == set(SERVICES) == set().union(*(set(spec[4]) for spec in GROUPS.values()))
    store = ConfigStore(tmp_path / 'config.json')
    original = store.load()
    window = SettingsWindow(original)
    window.show_onboarding()
    for group, spec in GROUPS.items():
        window.provider_picker.show_group(group)
        assert all(not window.provider_picker.buttons[k].isHidden() for k in spec[4])
    for kind in PROVIDERS:
        window.select_provider(kind)
        assert window.provider.currentData() == kind
        assert window._read_translation(kind)['provider'] == kind
    window.select_provider('openai'); window.model.setText('custom-openai')
    window.select_provider('gemini'); window.model.setText('custom-gemini')
    window.select_provider('openai'); assert window.model.text() == 'custom-openai'
    assert store.load() == original
    window.close()


def test_app_id_deepl_plan_and_libre_config(qt_app):
    window = SettingsWindow(deepcopy(DEFAULT))
    window.select_provider('baidu'); window.app_id.setText('public-app-id')
    window.select_provider('youdao'); assert window.app_id.text() == ''
    window.select_provider('baidu'); assert window.app_id.text() == 'public-app-id'
    window.select_provider('deepl'); window.api_key.setText('synthetic-only')
    window.deepl_plan.setCurrentIndex(1)
    assert window.api_key.text() == '' and window.base_url.text() == 'https://api.deepl.com'
    assert validate_translation(window._read_translation('deepl'))['deepl_plan'] == 'pro'
    window.select_provider('libre'); window.base_url.setText('http://localhost:5123')
    assert validate_translation(window._read_translation('libre'))['base_url'] == 'http://localhost:5123'
    window.close()


@pytest.mark.parametrize('kind', ['deepl', 'baidu', 'youdao', 'libre'])
def test_translation_services_protocol(kind):
    async def check():
        text = 'A scientific abstract: accuracy improves.'
        settings = ProviderSettings(**{**default_profile(kind), 'app_id': 'public-id'})
        def handle(req):
            assert req.method == 'POST' and not req.url.query
            assert req.url.host == httpx.URL(settings.base_url).host
            if kind in ('baidu', 'youdao'):
                form = {k: v[0] for k, v in parse_qs(req.content.decode()).items()}
                assert form['q'] == text and 'test-secret' not in req.content.decode()
                if kind == 'baidu':
                    expected = hashlib.md5(('public-id' + text + form['salt'] + 'test-secret').encode()).hexdigest()
                    assert form['sign'] == expected
                    return httpx.Response(200, json={'trans_result': [{'dst': '科学摘要'}, {'dst': '准确率提高'}]})
                short = text[:10] + str(len(text)) + text[-10:]
                expected = hashlib.sha256(('public-id' + short + form['salt'] + form['curtime'] + 'test-secret').encode()).hexdigest()
                assert form['sign'] == expected and form['signType'] == 'v3'
                return httpx.Response(200, json={'errorCode': '0', 'translation': ['科学摘要', '准确率提高']})
            body = json.loads(req.content)
            if kind == 'deepl':
                assert req.headers['Authorization'] == 'DeepL-Auth-Key test-secret'
                assert body['text'] == [text] and body['target_lang'] == 'ZH-HANS'
                return httpx.Response(200, json={'translations': [{'text': '科学摘要'}]})
            assert 'api_key' not in body and body['target'] == 'zh'
            return httpx.Response(200, json={'translatedText': '科学摘要'})
        provider = TranslationServices(transport=httpx.MockTransport(handle), trust_env=False)
        try:
            result = await provider.translate(TranslationRequest('test', text, settings), 'test-secret')
            assert result.text.startswith('科学摘要') and result.request_id == 'test'
        finally:
            await provider.aclose()
    asyncio.run(check())


@pytest.mark.parametrize('kind', list(CHAT_PRESETS))
def test_each_llm_protocol_and_independent_endpoint(kind):
    async def check():
        settings = ProviderSettings(**{**default_profile(kind), 'model': CHAT_PRESETS[kind][0] or 'ep-test'})
        def handle(req):
            assert req.url.host == httpx.URL(settings.base_url).host
            body = json.loads(req.content)
            assert body['model'] == settings.model
            if kind == 'claude':
                assert req.url.path == '/v1/messages'
                assert req.headers['x-api-key'] == 'synthetic'
                assert req.headers['anthropic-version'] == '2023-06-01'
                assert 'system' in body and body['messages'][0]['role'] == 'user'
                return httpx.Response(200, json={'content': [{'type': 'thinking', 'thinking': 'hidden'}, {'type': 'text', 'text': '你好'}], 'stop_reason': 'max_tokens'})
            assert req.url.path.endswith('/chat/completions')
            assert req.headers['Authorization'] == 'Bearer synthetic'
            assert body['max_completion_tokens' if kind == 'openai' else 'max_tokens'] == settings.max_tokens
            for key, value in CHAT_PRESETS[kind][1].items():
                assert body[key] == value
            return httpx.Response(200, json={'choices': [{'message': {'content': '<think>hidden</think>你好'}, 'finish_reason': 'stop'}]})
        cls = ClaudeProvider if kind == 'claude' else CompatibleProvider
        provider = cls(transport=httpx.MockTransport(handle), trust_env=False)
        try:
            result = await provider.translate(TranslationRequest('test', 'Hello', settings), 'synthetic')
            assert result.text == '你好'
            assert result.finish_reason == ('length' if kind == 'claude' else 'stop')
        finally:
            await provider.aclose()
    asyncio.run(check())


def test_translation_errors_are_bounded_and_do_not_echo_secrets():
    async def check():
        s = ProviderSettings(**default_profile('deepl'))
        for response, code in ((httpx.Response(456), 'QUOTA'),
                               (httpx.Response(200, content=b'x' * (1024*1024+1)), 'RESPONSE_LIMIT'),
                               (httpx.Response(200, json={'secret': 'do-not-display'}), 'FORMAT')):
            provider = TranslationServices(transport=httpx.MockTransport(lambda _: response), trust_env=False)
            try:
                with pytest.raises(AppError) as error:
                    await provider.translate(TranslationRequest('test', 'Hello', s), 'synthetic')
                assert error.value.code == code and 'do-not-display' not in str(error.value)
            finally:
                await provider.aclose()
        with pytest.raises(AppError):
            TranslationServices.content('youdao', {'errorCode': 'secret-private-text'})
    asyncio.run(check())

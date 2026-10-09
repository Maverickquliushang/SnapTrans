import asyncio
import base64
import io
import json
from copy import deepcopy
from unittest.mock import Mock
import httpx
import pytest
from PIL import Image
from snaptrans.config import DEFAULT, validate
from snaptrans.core.models import ProviderSettings, TranslationRequest, CaptureFrame, AppError, OcrResult, State
from snaptrans.providers.catalog import default_profile
from snaptrans.providers.nvidia import NvidiaProvider, extra_parameters
from snaptrans.providers.nvidia_ocr import NvidiaOcrProvider, OCR_ENDPOINT, parse_detections


def frame():
    return CaptureFrame('ocr-id', 'fixture', (0, 0, 1000, 800), (40, 50, 80, 30),
                        (40, 50, 120, 80), 80, 30, bytes([255]) * 80 * 30 * 3)


def detection():
    return {'data': [{'index': 0, 'text_detections': [{'text_prediction': {'text': 'Hello', 'confidence': .98},
             'bounding_box': {'points': [{'x': .1, 'y': .2}, {'x': .9, 'y': .2}, {'x': .9, 'y': .8}, {'x': .1, 'y': .8}]}}]}]}


def test_nvidia_chat_request_reasoning_and_long_deadline():
    async def run():
        def handler(request):
            assert str(request.url) == 'https://integrate.api.nvidia.com/v1/chat/completions'
            assert request.headers['authorization'] == 'Bearer synthetic'
            assert request.extensions['timeout']['read'] == 300
            body = json.loads(request.content)
            assert body['model'] == 'vendor/custom-chat-id'
            assert body['max_tokens'] == 8192 and body['stream'] is True
            assert body['chat_template_kwargs'] == {'enable_thinking': False}
            assert body['messages'][-1]['content'] == 'Hello'
            return httpx.Response(200, json={'choices': [{'message': {'content': '<think>internal</think>你好',
                'reasoning_content': 'private reasoning'}, 'finish_reason': 'stop'}]})
        provider = NvidiaProvider(httpx.MockTransport(handler))
        settings = default_profile('nvidia')
        settings.update(model='vendor/custom-chat-id', model_defaults=False, max_tokens=8192, total_timeout_seconds=300, extra_body_json='{"chat_template_kwargs":{"enable_thinking":false}}')
        try:
            result = await provider.translate(TranslationRequest('id', 'Hello', ProviderSettings(**settings)), 'synthetic')
            assert result.text == '你好'
        finally:
            await provider.aclose()
    asyncio.run(run())


@pytest.mark.parametrize('value', ['{"messages":[]}', '{"api_key":"secret"}', '[]', 'invalid'])
def test_extra_parameters_cannot_override_request_or_auth(value):
    with pytest.raises(ValueError):
        extra_parameters(value)


def test_nvidia_config_migration_and_provider_ui(qt_app):
    from snaptrans.ui.settings_window import SettingsWindow
    old = deepcopy(DEFAULT)
    old.pop('ocr')
    old['translation'].pop('max_tokens')
    old['translation'].pop('extra_body_json')
    assert validate(old)['ocr']['provider'] == 'local'
    window = SettingsWindow(DEFAULT)
    window.provider.setCurrentIndex(window.provider.findData('nvidia'))
    assert window.timeout.value() == 120 and window.max_tokens.value() == 16384
    assert window.base_url.text() == 'https://integrate.api.nvidia.com/v1'
    assert window.requires_key.isChecked() and not window.requires_key.isEnabled()
    window.model.setText('vendor/any-future-chat-model')
    window.provider.setCurrentIndex(window.provider.findData('mymemory'))
    window.provider.setCurrentIndex(window.provider.findData('nvidia'))
    assert window.model.text() == 'vendor/any-future-chat-model'
    assert window.ocr_provider.currentData() == 'local'
    window.close()


def test_model_list_and_reasoning_only_error():
    async def run():
        provider = NvidiaProvider(httpx.MockTransport(lambda req: httpx.Response(200,
                    json={'data': [{'id': 'b/model'}, {'id': 'a/model'}, {'id': 'b/model'}]})))
        try:
            assert await provider.list_models() == ['a/model', 'b/model']
            with pytest.raises(AppError, match='推理'):
                provider.response_content({'content': '<think>unfinished'}, 'length')
        finally:
            await provider.aclose()
    asyncio.run(run())


def test_model_picker_search_selection_and_provider_isolation(qt_app):
    from PySide6.QtWidgets import QLineEdit, QListWidget, QPushButton
    from snaptrans.ui.settings_window import SettingsWindow
    window = SettingsWindow(DEFAULT)
    window.provider.setCurrentIndex(window.provider.findData('nvidia'))
    window.show_models(['a/chat', 'b/chat'])
    dialog = window.model_dialog
    search = dialog.findChild(QLineEdit)
    listing = dialog.findChild(QListWidget)
    search.setText('B/CHAT')
    assert listing.item(0).isHidden() and not listing.item(1).isHidden()
    listing.setCurrentRow(1)
    dialog.findChild(QPushButton).click()
    assert window.model.text() == 'b/chat'
    window.show_models(['a/chat'])
    dialog = window.model_dialog
    dialog.findChild(QListWidget).setCurrentRow(0)
    window.provider.setCurrentIndex(window.provider.findData('ollama'))
    window.model.setText('local-model')
    dialog.findChild(QPushButton).click()
    assert window.model.text() == 'local-model'
    window.close()


def test_cloud_ocr_settings_save_is_separate_from_translation(qt_app):
    from snaptrans.ui.settings_window import SettingsWindow
    window = SettingsWindow(DEFAULT)
    emitted = []
    window.save_requested.connect(lambda config, secret: emitted.append((config, secret)))
    window.ocr_provider.setCurrentIndex(window.ocr_provider.findData('nvidia'))
    window.ocr_key.setText('synthetic-ocr-secret')
    window.ocr_save_key.setChecked(True)
    window.save_button.click()
    from snaptrans.providers.ocr_catalog import default_ocr
    assert emitted[0][0]['ocr'] == {**default_ocr('nvidia'), 'save_api_key': True}
    assert emitted[0][0]['translation']['provider'] == 'mymemory'
    assert emitted[0][1] == '' and window.ocr_secret() == 'synthetic-ocr-secret'
    assert 'synthetic-ocr-secret' not in json.dumps(emitted[0][0])
    window.ocr_clear_key.setChecked(True)
    assert window.ocr_secret() == ''
    window.close()


def test_cloud_ocr_sends_only_crop_and_parses_normalized_boxes():
    async def run():
        def handler(request):
            assert str(request.url) == OCR_ENDPOINT
            assert request.headers['authorization'] == 'Bearer synthetic-ocr'
            body = json.loads(request.content)
            image_url = body['input'][0]['url']
            image = Image.open(io.BytesIO(base64.b64decode(image_url.split(',')[1])))
            assert image.size == (80, 30)  # selected crop, not 1000 x 800 desktop
            assert body['merge_levels'] == ['sentence']
            return httpx.Response(200, json=detection())
        provider = NvidiaOcrProvider(httpx.MockTransport(handler))
        try:
            result = await provider.recognize(frame(), {'total_timeout_seconds': 120}, 'synthetic-ocr')
            assert result.raw_text == 'Hello'
            assert result.lines[0].polygon[0] == (8, 6)
        finally:
            await provider.aclose()
    asyncio.run(run())


@pytest.mark.parametrize('status,code', [(401, 'AUTH'), (403, 'AUTH'), (413, 'IMAGE_LIMIT'), (429, 'RATE_LIMIT'), (503, 'SERVICE')])
def test_cloud_ocr_errors(status, code):
    async def run():
        provider = NvidiaOcrProvider(httpx.MockTransport(lambda _: httpx.Response(status)))
        try:
            with pytest.raises(AppError) as error:
                await provider.recognize(frame(), {'total_timeout_seconds': 120}, 'synthetic')
            assert error.value.code == code
        finally:
            await provider.aclose()
    asyncio.run(run())


def test_cloud_ocr_without_key_never_sends_image():
    async def run():
        handler = Mock()
        provider = NvidiaOcrProvider(httpx.MockTransport(handler))
        try:
            with pytest.raises(AppError) as error:
                await provider.recognize(frame(), {'total_timeout_seconds': 120}, '')
            assert error.value.code == 'NO_OCR_KEY'
            handler.assert_not_called()
        finally:
            await provider.aclose()
    asyncio.run(run())


def test_ocr_route_is_opt_in_and_late_result_is_discarded(qt_app):
    from test_ocr_workspace import workspace
    controller, ocr, network = workspace(qt_app)
    network.submit_ocr = Mock()
    controller.extract_text()
    assert ocr.submit.call_count == 1 and not network.submit_ocr.called
    controller.ocr_done(OcrResult(controller.gate.request_id, 'local', [], 1))
    config = controller.config_getter()
    config['ocr']['provider'] = 'nvidia'
    controller.credentials.get.return_value = 'synthetic-ocr'
    controller.extract_text()
    request_id = controller.gate.request_id
    assert network.submit_ocr.call_count == 1 and ocr.submit.call_count == 1
    assert network.submit_ocr.call_args.args[0].width_px == 240
    controller.cancel()
    controller.ocr_done(OcrResult(request_id, 'late cloud result', [], 1))
    assert controller.result.source_text() == ''
    assert request_id in network.cancelled
    controller.close()

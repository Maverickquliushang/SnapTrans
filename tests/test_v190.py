import asyncio
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import time
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.parse import urlsplit, parse_qs, unquote
import httpx
import pytest
from PySide6.QtCore import Qt, QObject, QRectF
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QToolButton, QWidget
from snaptrans.config import DEFAULT, ConfigStore, validate
from snaptrans.core.models import ProviderSettings, TranslationRequest
from snaptrans.providers.catalog import default_profile, LOCAL_PROVIDERS, WEB_PROVIDERS
from snaptrans.providers.compatible import CompatibleProvider
from snaptrans.providers.web_translation import WebTranslationService, website_url
from snaptrans.ui.settings_window import SettingsWindow
from snaptrans.ui.result_window import ResultWindow
from snaptrans.ui.theme import refresh_themes
from snaptrans.ui.themes import THEMES, palette, current_theme


def test_theme_preview_discard_save_and_small_window(qt_app, tmp_path):
    store = ConfigStore(tmp_path / 'config.json')
    original = store.load()
    original['window']['theme'] = 'ember'
    store.save(original)
    refresh_themes('ember')
    window = SettingsWindow(original)
    window.preview_theme('daylight')
    assert current_theme() == 'ember'  # A draft preview is scoped to settings.
    assert store.load() == original
    window.resize(540, 460); window.show(); qt_app.processEvents()
    assert window.width() == 540 and window.height() == 460
    assert not window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    assert window.rect().contains(window.save_button.mapTo(window, window.save_button.rect().bottomRight()))
    window.close()
    assert store.load()['window']['theme'] == 'ember'
    window = SettingsWindow(store.load())
    window.preview_theme('forest')
    window.save_requested.connect(lambda config, secret: store.save(config))
    window.save_button.click()
    assert store.load()['window']['theme'] == 'forest'
    window.close()


def test_backward_compatible_window_config_and_invalid_theme():
    config = deepcopy(DEFAULT)
    config['window'].pop('theme')
    config['window']['always_on_top'] = True
    assert validate(config)['window'] == {**DEFAULT['window'], 'always_on_top': True}
    config['window']['theme'] = 'unknown'
    with pytest.raises(ValueError):
        validate(config)


def test_back_navigation_preserves_draft(qt_app):
    window = SettingsWindow(deepcopy(DEFAULT))
    window.show_provider_picker()
    window.provider_picker.show_group('models')
    window.select_provider('qwen')
    window.model.setText('my-qwen-model')
    window.detail_back_button.click()
    assert window.service_stack.currentIndex() == 0
    assert window.provider_picker.current_group == 'models'
    window.provider_picker.buttons['qwen'].click()
    assert window.model.text() == 'my-qwen-model'
    window.provider_picker.groups_back.click()
    assert window.provider_picker.current_group is None
    window.close()


def test_result_size_survives_view_changes_and_hidden_pin_update(qt_app):
    window = ResultWindow({**DEFAULT['window'], 'display_mode': 'popup'})
    window.resize(530, 435)
    window.view_mode.setCurrentIndex(1)
    window.view_mode.setCurrentIndex(0)
    assert window.size().width() == 530 and window.size().height() == 435
    window.pin.setChecked(True)
    assert not QWidget.isVisible(window)
    window.show(); qt_app.processEvents()
    window.pin.setChecked(False)
    assert QWidget.isVisible(window)
    assert not window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    assert window.rect().contains(window.close_button.mapTo(window, window.close_button.rect().center()))
    window.close()


@pytest.mark.parametrize('theme', THEMES)
def test_theme_contrast_and_annotation_colors(qt_app, theme):
    def luminance(hex_color):
        values = [v / 255 for v in bytes.fromhex(hex_color[1:])]
        return sum(w * (c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4) for w, c in zip((.2126, .7152, .0722), values))
    colors = palette(theme)
    for fg, bg in [('text', 'bg'), ('text', 'surface'), ('muted', 'surface'), ('on_accent', 'accent')]:
        a, b = sorted([luminance(colors[fg]), luminance(colors[bg])])
        assert (b + .05) / (a + .05) >= 4.5, (theme, fg)
    refresh_themes(theme)
    window = ResultWindow({**DEFAULT['window'], 'theme': theme})
    swatch = window.overlay.editor.options.swatches['#ff5148']
    assert 'background:#ff5148' in swatch.styleSheet()
    assert not any(button.text() == '颜色' for button in window.overlay.findChildren(QToolButton))
    window.close()
    refresh_themes('ember')


def test_bundled_brand_provenance():
    directory = Path(__file__).resolve().parents[1] / 'assets' / 'providers'
    manifest = json.loads((directory / 'sources.json').read_text())
    assert len(manifest) >= 26
    for key, source in manifest.items():
        path = next(directory.glob(key + '.*'))
        assert hashlib.sha256(path.read_bytes()).hexdigest() == source['sha256']


@pytest.mark.parametrize('kind', LOCAL_PROVIDERS)
def test_local_model_protocol(kind):
    async def verify():
        config = default_profile(kind)
        config['model'] = 'loaded-local-model'
        def handle(req):
            assert req.url.host == '127.0.0.1'
            assert req.url.path == '/v1/chat/completions'
            assert 'authorization' not in req.headers
            assert json.loads(req.content)['model'] == 'loaded-local-model'
            return httpx.Response(200, json={'choices': [{'message': {'content': '本地译文'}, 'finish_reason': 'stop'}]})
        provider = CompatibleProvider(transport=httpx.MockTransport(handle))
        result = await provider.translate(TranslationRequest('local', 'Hello', ProviderSettings(**config)))
        assert result.text == '本地译文'
        await provider.aclose()
    asyncio.run(verify())


def test_web_url_encoding():
    text = 'A & B? x=#value\n"quoted" + more'
    for kind in WEB_PROVIDERS:
        url = urlsplit(website_url(kind, text))
        assert url.scheme == 'https'
        if kind in ('google_web', 'bing_web'):
            assert parse_qs(url.query)['text'] == [text]
        elif kind == 'baidu_web':
            assert parse_qs(url.query)['query'] == [text]
        elif kind == 'deepl_web':
            assert unquote(url.fragment).removeprefix('en/zh-Hans/') == text
        config = deepcopy(DEFAULT)
        config['translation'] = default_profile(kind)
        assert not validate(config)['translation']['requires_api_key']


def web_fixture():
    service = WebTranslationService.__new__(WebTranslationService)
    QObject.__init__(service)
    request = TranslationRequest('web', 'Hello.', ProviderSettings(**default_profile('bing_web')))
    service.jobs = {'web': {'request': request, 'reading': True, 'started': time.monotonic(), 'last': '', 'stable': 0}}
    service.cancel = lambda request_id: service.jobs.pop(request_id, None)
    return service


def test_web_ignores_placeholder_stale_source_and_cancelled_result(qt_app):
    service = web_fixture()
    output = []
    service.succeeded.connect(output.append)
    for source, text in [('Hello.', '...'), ('Hello.', '…'), ('Old request', '旧的结果')]:
        for _ in range(5):
            service._read('web', json.dumps({'source': source, 'text': text, 'url': 'https://www.bing.com/translator'}))
    assert not output
    for _ in range(4):
        service._read('web', json.dumps({'source': 'Hello.', 'text': '你好。', 'url': 'https://www.bing.com/translator'}))
    assert len(output) == 1 and output[0].text == '你好。'
    service._read('web', {'source': 'Hello.', 'text': '迟到结果'})
    assert len(output) == 1


@pytest.mark.parametrize('data,code', [({'blocked': True}, 'WEB_INTERACTION'), ({'url': 'https://example.com'}, 'WEB_REDIRECT'), ({'url': 'https://www.bing.com/translator', 'error': True}, 'WEB_SERVICE')])
def test_web_stops_on_verification_redirect_and_error(qt_app, data, code):
    service = web_fixture()
    failures = []
    service.failed.connect(lambda *args: failures.append(args))
    service._read('web', data)
    assert failures[0][1] == code and not service.jobs

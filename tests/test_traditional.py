import asyncio
import json
import httpx
import pytest
from snaptrans.core.models import ProviderSettings, TranslationRequest, AppError
from snaptrans.providers.traditional import TraditionalProvider
from snaptrans.providers.catalog import PROVIDERS


@pytest.mark.parametrize('kind', ['google', 'microsoft'])
def test_official_request_and_response(kind):
    async def run():
        def handler(req):
            assert 'key' not in req.url.params
            payload = json.loads(req.content)
            if kind == 'google':
                assert req.headers['x-goog-api-key'] == 'synthetic-key'
                assert req.url.path == '/language/translate/v2'
                assert payload['target'] == 'zh-CN' and payload['format'] == 'text'
                return httpx.Response(200, json={'data': {'translations': [{'translatedText': '甲 &amp; 乙'}]}})
            assert req.headers['Ocp-Apim-Subscription-Key'] == 'synthetic-key'
            assert req.headers['Ocp-Apim-Subscription-Region'] == 'eastasia'
            assert payload == [{'Text': 'A and B'}]
            assert req.url.params['to'] == 'zh-Hans'
            return httpx.Response(200, json=[{'translations': [{'text': '甲 & 乙', 'to': 'zh-Hans'}]}])
        provider = TraditionalProvider(httpx.MockTransport(handler))
        settings = ProviderSettings(provider=kind, base_url=PROVIDERS[kind][1], region='eastasia')
        try:
            result = await provider.translate(TranslationRequest('id', 'A and B', settings), 'synthetic-key')
            assert result.text == '甲 & 乙'
        finally:
            await provider.aclose()
    asyncio.run(run())


def test_traditional_rejects_custom_origin():
    async def run():
        provider = TraditionalProvider(httpx.MockTransport(lambda req: pytest.fail('key must not be sent')))
        try:
            with pytest.raises(AppError) as captured:
                await provider.translate(TranslationRequest('id', 'text', ProviderSettings(provider='google', base_url='https://wrong.example')), 'key')
            assert captured.value.code == 'INVALID_URL'
        finally:
            await provider.aclose()
    asyncio.run(run())

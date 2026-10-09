from ..i18n import tr
import asyncio
import html
import json
import time
import httpx
from .compatible import CompatibleProvider
from .catalog import PROVIDERS
from ..core.models import AppError, TranslationResult


class TraditionalProvider(CompatibleProvider):
    """Official Google Basic v2 and Microsoft Translator v3 APIs."""
    async def translate(self, request, api_key=''):
        settings = request.settings_snapshot
        from ..languages import service_pair
        source, target = service_pair(settings.provider, settings.source_lang, settings.target_lang)
        if not api_key:
            raise AppError('NO_KEY', tr('请填写该翻译服务的官方 API Key。'))
        if not request.text.strip():
            raise AppError('EMPTY_INPUT', tr('原文为空，请输入文字。'))
        # Application-level limit, intentionally conservative for both engines.
        if len(request.text) > 5000:
            raise AppError('INPUT_LIMIT', tr('普通翻译单次最多 5000 字符，请缩小选区或编辑。'))
        if settings.provider == 'google':
            endpoint = PROVIDERS['google'][1] + '/language/translate/v2'
            headers = {'X-goog-api-key': api_key}
            params = None
            body = {'q': request.text, 'target': target, 'format': 'text'}
            if settings.source_lang != 'auto':
                body['source'] = source
        elif settings.provider == 'microsoft':
            endpoint = PROVIDERS['microsoft'][1] + '/translate'
            headers = {'Ocp-Apim-Subscription-Key': api_key}
            if settings.region:
                headers['Ocp-Apim-Subscription-Region'] = settings.region
            params = {'api-version': '3.0', 'to': target, 'textType': 'plain'}
            if settings.source_lang != 'auto':
                params['from'] = source
            body = [{'Text': request.text}]
        else:
            raise AppError('PROVIDER', tr('不支持的翻译服务。'))
        # Never redirect a traditional engine's key to a custom host.
        if settings.base_url.rstrip('/') != PROVIDERS[settings.provider][1]:
            raise AppError('INVALID_URL', tr('普通翻译必须使用固定的官方服务地址。'))
        started = time.perf_counter()
        try:
            async with asyncio.timeout(settings.total_timeout_seconds):
                async with self.client.stream('POST', endpoint, params=params, headers=headers, json=body) as response:
                    if response.status_code != 200:
                        self._http_error(response.status_code)
                    raw = bytearray()
                    async for chunk in response.aiter_bytes(chunk_size=65536):
                        raw.extend(chunk)
                        if len(raw) > 1024 * 1024:
                            raise AppError('RESPONSE_LIMIT', tr('翻译服务返回内容过大。'))
                decoded = json.loads(raw)
                text = (decoded['data']['translations'][0]['translatedText'] if settings.provider == 'google'
                        else decoded[0]['translations'][0]['text'])
                if not isinstance(text, str) or not text.strip():
                    raise AppError('EMPTY_RESPONSE', tr('服务未返回有效译文。'))
                if settings.provider == 'google':
                    text = html.unescape(text)
                return TranslationResult(request.request_id, text.strip(), (time.perf_counter()-started)*1000, 'stop')
        except (TimeoutError, httpx.TimeoutException):
            raise AppError('TIMEOUT', tr('翻译超时，原文已保留。'), True) from None
        except httpx.RequestError:
            raise AppError('CONNECTION', tr('无法连接官方翻译服务，请检查网络。'), True) from None
        except (ValueError, KeyError, IndexError, TypeError):
            raise AppError('FORMAT', tr('翻译服务返回格式不兼容。')) from None

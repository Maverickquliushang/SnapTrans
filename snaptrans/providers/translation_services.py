from ..i18n import ui_format
"""Official translation protocols. Secrets stay in headers or signed POST bodies."""
from ..i18n import tr
import asyncio
import hashlib
import json
import time
import uuid
from urllib.parse import urlsplit
import httpx
from .compatible import CompatibleProvider, endpoint_for
from .catalog import PROVIDERS, DEEPL_URLS
from ..core.models import AppError, TranslationResult


class TranslationServices(CompatibleProvider):
    def payload(self, request, secret):
        s, text = request.settings_snapshot, request.text
        kind = s.provider
        from ..languages import service_pair
        source, target = service_pair(kind, s.source_lang, s.target_lang)
        base = s.base_url.rstrip('/')
        if kind == 'libre':
            try:
                endpoint_for(base)
            except ValueError as error:
                raise AppError('INVALID_URL', str(error)) from None
            body = {'q': text, 'source': source, 'target': target, 'format': 'text'}
            if s.requires_api_key:
                body['api_key'] = secret
            return base + '/translate', {'json': body}
        expected = DEEPL_URLS.get(s.deepl_plan) if kind == 'deepl' else PROVIDERS[kind][1]
        if base != expected:
            raise AppError('INVALID_URL', tr('请使用该翻译服务的官方地址。'))
        if kind == 'deepl':
            body = {'text': [text], 'target_lang': target, 'preserve_formatting': True}
            if s.source_lang != 'auto':
                body['source_lang'] = source
            return base + '/v2/translate', {'headers': {'Authorization': f'DeepL-Auth-Key {secret}'},
                'json': body}
        if not s.app_id.strip():
            raise AppError('NO_APP_ID', tr('请填写应用 ID（百度 APP ID / 有道应用 ID），密钥单独填入 API Key。'))
        salt = uuid.uuid4().hex
        if kind == 'baidu':
            sign = hashlib.md5((s.app_id + text + salt + secret).encode('utf-8')).hexdigest()
            return base + '/api/trans/vip/translate', {'data': {'q': text, 'from': source, 'to': target,
                'appid': s.app_id, 'salt': salt, 'sign': sign}}
        shortened = text if len(text) <= 20 else text[:10] + str(len(text)) + text[-10:]
        stamp = str(int(time.time()))
        sign = hashlib.sha256((s.app_id + shortened + salt + stamp + secret).encode('utf-8')).hexdigest()
        return base + '/api', {'data': {'q': text, 'from': source, 'to': target, 'strict': 'true', 'appKey': s.app_id,
            'salt': salt, 'curtime': stamp, 'signType': 'v3', 'sign': sign}}

    @staticmethod
    def content(kind, body):
        if kind in ('baidu', 'youdao'):
            code = str(body.get('error_code', '52000') if kind == 'baidu' else body.get('errorCode', ''))
            if code != ('52000' if kind == 'baidu' else '0'):
                # Do not echo arbitrary provider messages which can contain text or secrets.
                label = code if code.isdigit() and len(code) <= 8 else tr('未知')
                raise AppError('SERVICE', ui_format('{}{}{}', tr('服务返回错误码 '), label, tr('，请检查应用 ID、密钥、额度及服务开通状态。')))
        if kind == 'deepl':
            values = [item['text'] for item in body['translations']]
        elif kind == 'baidu':
            values = [item['dst'] for item in body['trans_result']]
        elif kind == 'youdao':
            values = body['translation']
        else:
            values = [body['translatedText']]
        if not isinstance(values, list) or not values or any(not isinstance(x, str) for x in values):
            raise AppError('FORMAT', tr('翻译服务返回格式不兼容。'))
        result = '\n'.join(values).strip()
        if not result:
            raise AppError('EMPTY_RESPONSE', tr('服务未返回有效译文。'))
        return result

    async def translate(self, request, api_key=''):
        s = request.settings_snapshot
        if not request.text.strip():
            raise AppError('EMPTY_INPUT', tr('原文为空，请先输入文字。'))
        if len(request.text) > 5000:
            raise AppError('INPUT_LIMIT', tr('单次最多 5000 字符，请缩小选区或编辑。'))
        if (s.provider != 'libre' or s.requires_api_key) and not api_key:
            raise AppError('NO_KEY', tr('请填写该服务的 API Key / 应用密钥。'))
        endpoint, kwargs = self.payload(request, api_key)
        local = urlsplit(endpoint).hostname in ('localhost', '127.0.0.1', '::1')
        client = self.local_client if local else self.client
        started = time.perf_counter()
        try:
            async with asyncio.timeout(s.total_timeout_seconds):
                async with client.stream('POST', endpoint, timeout=httpx.Timeout(s.total_timeout_seconds, connect=5), **kwargs) as response:
                    if response.status_code == 456:
                        raise AppError('QUOTA', tr('DeepL 本期翻译额度已用完。'))
                    if response.status_code != 200:
                        self._http_error(response.status_code)
                    raw = bytearray()
                    async for chunk in response.aiter_bytes(chunk_size=65536):
                        raw.extend(chunk)
                        if len(raw) > 1024 * 1024:
                            raise AppError('RESPONSE_LIMIT', tr('服务返回内容过大。'))
                text = self.content(s.provider, json.loads(raw))
                return TranslationResult(request.request_id, text, (time.perf_counter()-started)*1000, 'stop')
        except (TimeoutError, httpx.TimeoutException):
            raise AppError('TIMEOUT', tr('翻译超时，原文已保留。'), True) from None
        except httpx.RequestError:
            raise AppError('CONNECTION', tr('无法连接翻译服务，请检查服务地址和网络。'), True) from None
        except (ValueError, KeyError, IndexError, TypeError, AttributeError):
            raise AppError('FORMAT', tr('翻译服务返回格式不兼容。')) from None

"""Public MyMemory GET endpoint; never calls its translation-memory SET API."""
from ..i18n import tr
import asyncio
import html
import re
import json
import time
import httpx
from .compatible import CompatibleProvider
from .catalog import PROVIDERS
from .text_input import translation_input
from ..core.models import AppError, TranslationResult


def split_utf8(text, limit=500):
    chunks = []
    remaining = text.strip()
    while remaining:
        used = 0
        end = 0
        for character in remaining:
            size = len(character.encode('utf-8'))
            if used + size > limit:
                break
            used += size
            end += 1
        if end < len(remaining):
            # Prefer a sentence/word boundary without losing any characters.
            prefix = remaining[:end]
            boundary = max(prefix.rfind('\n'), prefix.rfind('. '), prefix.rfind('? '),
                           prefix.rfind('! '), prefix.rfind('; '))
            if boundary < end // 2:
                boundary = prefix.rfind(' ')
            if boundary > 0:
                end = boundary + 1
        if not end:
            raise ValueError('Chunk limit too small for a UTF-8 character')
        chunks.append(remaining[:end])
        remaining = remaining[end:]
    return chunks


class MyMemoryProvider(CompatibleProvider):
    async def translate(self, request, api_key=''):
        settings = request.settings_snapshot
        from ..languages import service_pair
        source, target = service_pair('mymemory', settings.source_lang, settings.target_lang)
        if settings.base_url.rstrip('/') != PROVIDERS['mymemory'][1]:
            raise AppError('INVALID_URL', tr('免费翻译必须使用官方服务地址。'))
        if not request.text.strip():
            raise AppError('EMPTY_INPUT', tr('原文为空，请输入文字。'))
        if len(request.text) > 5000:
            raise AppError('INPUT_LIMIT', tr('免费翻译单次最多 5000 字符，请缩小选区。'))
        started = time.perf_counter()
        translated = []
        try:
            async with asyncio.timeout(settings.total_timeout_seconds):
                for chunk in split_utf8(translation_input(request.text)):
                    async with self.client.stream('GET', settings.base_url + '/get',
                            params={'q': chunk, 'langpair': source + '|' + target}) as response:
                        if response.status_code != 200:
                            self._http_error(response.status_code)
                        raw = bytearray()
                        async for block in response.aiter_bytes(chunk_size=65536):
                            raw.extend(block)
                            if len(raw) > 1024 * 1024:
                                raise AppError('RESPONSE_LIMIT', tr('免费服务返回内容过大。'))
                    data = json.loads(raw)
                    if data.get('quotaFinished') or str(data.get('responseStatus')) == '429':
                        raise AppError('FREE_QUOTA', tr('免费翻译今日额度已用完，可切换 Ollama 或其他引擎。'))
                    if str(data.get('responseStatus')) != '200':
                        raise AppError('FREE_SERVICE', tr('免费翻译暂时不可用，可切换其他引擎后重译。'), True)
                    text = data['responseData']['translatedText']
                    if not isinstance(text, str) or not text.strip():
                        raise AppError('EMPTY_RESPONSE', tr('免费服务未返回译文。'))
                    text = html.unescape(text).strip()
                    # Translation-memory entries sometimes leak XLIFF group wrappers.
                    # Remove only this known wrapper, and preserve literal markup in source.
                    if not re.search(r'</?g\b', html.unescape(chunk), re.I):
                        text = re.sub(r'</?g\b[^<>]*>', '', text, flags=re.I)
                    translated.append(text)
            return TranslationResult(request.request_id, '\n'.join(translated),
                                     (time.perf_counter() - started) * 1000, 'stop')
        except (TimeoutError, httpx.TimeoutException):
            raise AppError('TIMEOUT', tr('免费翻译超时，原文已保留，可以切换引擎重译。'), True) from None
        except httpx.RequestError:
            raise AppError('CONNECTION', tr('无法连接免费翻译服务，请检查网络或切换引擎。'), True) from None
        except (ValueError, KeyError, TypeError):
            raise AppError('FORMAT', tr('免费翻译返回格式异常，请稍后重试。')) from None

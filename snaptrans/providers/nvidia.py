from ..i18n import ui_format
"""NVIDIA's hosted text chat API; catalog discovery does not imply model access."""
from ..i18n import tr
import asyncio
import json
import re
import time
from .nvidia_http import response_json
from .model_cards import model_card
from ..core.models import TranslationResult
import httpx
from ..core.models import AppError
from .compatible import CompatibleProvider
from .catalog import PROVIDERS


def extra_parameters(value):
    if len(value) > 8192:
        raise ValueError(tr('高级参数不能超过 8192 字符'))
    try:
        result = json.loads(value or '{}', parse_constant=lambda value: None)
    except (ValueError, RecursionError):
        raise ValueError(tr('高级参数必须是有效 JSON 对象')) from None
    allowed = {'temperature', 'top_p', 'top_k', 'seed', 'stop', 'presence_penalty',
               'frequency_penalty', 'repetition_penalty', 'reasoning_effort', 'reasoning_budget', 'chat_template_kwargs',
               'thinking', 'enable_thinking'}
    if not isinstance(result, dict) or set(result) - allowed:
        raise ValueError(tr('高级参数仅支持采样、reasoning_effort、chat_template_kwargs 等模型参数；不可覆盖模型、消息、密钥或请求地址'))
    return result


class NvidiaProvider(CompatibleProvider):
    def request_body(self, request):
        body = super().request_body(request)
        try:
            body.update(extra_parameters(request.settings_snapshot.extra_body_json))
        except ValueError as error:
            raise AppError('PARAMETERS', str(error)) from None
        settings = request.settings_snapshot
        card = model_card(settings.model)
        tokens = card['tokens'] if settings.model_defaults else settings.max_tokens
        if tokens:
            if tokens > card['limit']:
                raise AppError('PARAMETERS', ui_format('{}{}{}', tr('该模型官方输出上限为 '), card['limit'], tr(' tokens，请降低参数。')))
            body['max_tokens'] = tokens
        # Editing the token count must not unexpectedly turn reasoning back on.
        body = {**card['extra'], **body}
        body['stream'] = True
        return body

    def response_content(self, message, reason):
        content = message.get('content') or ''
        if isinstance(content, list):
            content = ''.join(part.get('text', '') for part in content
                              if isinstance(part, dict) and part.get('type') == 'text')
        if isinstance(content, str):
            # Some reasoning models use a separate field; others embed think tags.
            # Never display chain-of-thought as if it were a translation.
            content = re.sub(r'<think>.*?</think>', '', content, flags=re.S | re.I).strip()
            if '<think>' in content.lower():
                content = content[:content.lower().index('<think>')].strip()
            if not content and (reason == 'length' or message.get('reasoning_content')):
                raise AppError('REASONING_ONLY', tr('模型只完成了推理，尚未生成译文。请增加最大输出 tokens，或按模型示例关闭思考模式。'))
        return content

    async def translate(self, request, api_key=''):
        if request.settings_snapshot.base_url.rstrip('/') != PROVIDERS['nvidia'][1]:
            raise AppError('INVALID_URL', tr('NVIDIA 使用官方 API 地址；自部署 NIM 请使用“大模型兼容接口”。'))
        if not api_key:
            raise AppError('NO_KEY', tr('请在设置中填写 NVIDIA API Key。'))
        if not request.text.strip() or len(request.text) > 8000:
            raise AppError('INPUT_LIMIT', tr('原文不能为空或超过 8000 字符。'))
        started = time.monotonic()
        try:
            decoded = await response_json(self.client, PROVIDERS['nvidia'][1] + '/chat/completions',
                self.request_body(request), api_key, request.settings_snapshot.total_timeout_seconds,
                lambda text: getattr(self, 'progress', lambda *args: None)(request.request_id, text))
            choice = decoded['choices'][0]
            content = self.response_content(choice['message'], choice.get('finish_reason'))
            if not isinstance(content, str) or not content.strip():
                raise AppError('EMPTY_RESPONSE', tr('模型未生成有效译文，请检查模型参数或更换模型。'))
            return TranslationResult(request.request_id, content.strip(), (time.monotonic()-started)*1000,
                                     choice.get('finish_reason'))
        except (TimeoutError, httpx.TimeoutException):
            raise AppError('TIMEOUT', tr('NVIDIA 等待超时，可能仍在排队或推理。可增加超时、关闭该模型的思考模式或换模型；不会自动重试。'), True) from None
        except httpx.RequestError:
            raise AppError('CONNECTION', tr('无法连接 NVIDIA，请检查网络后重试。'), True) from None
        except (ValueError, KeyError, IndexError, TypeError):
            raise AppError('FORMAT', tr('NVIDIA 返回内容格式异常，请稍后重试。')) from None

    async def list_models(self, api_key=''):
        try:
            async with asyncio.timeout(25):
                headers = {'Authorization': f'Bearer {api_key}'} if api_key else {}
                async with self.client.stream('GET', PROVIDERS['nvidia'][1] + '/models', headers=headers) as response:
                    if response.status_code != 200:
                        self._http_error(response.status_code)
                    data = bytearray()
                    async for chunk in response.aiter_bytes():
                        data.extend(chunk)
                        if len(data) > 2 * 1024 * 1024:
                            raise AppError('RESPONSE_LIMIT', tr('模型目录过大，请直接填写模型 ID。'))
                items = json.loads(data)['data']
                return sorted({item['id'] for item in items if isinstance(item, dict)
                               and isinstance(item.get('id'), str) and 0 < len(item['id']) < 256})
        except (TimeoutError, httpx.TimeoutException):
            raise AppError('TIMEOUT', tr('读取模型目录超时，可直接填写模型 ID。'), True) from None
        except httpx.RequestError:
            raise AppError('CONNECTION', tr('无法读取 NVIDIA 模型目录，请检查网络；也可直接填写模型 ID。'), True) from None
        except (ValueError, KeyError, TypeError):
            raise AppError('FORMAT', tr('模型目录格式不兼容，请直接填写模型 ID。')) from None

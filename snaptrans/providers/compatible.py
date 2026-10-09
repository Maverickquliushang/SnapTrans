from ..i18n import ui_format
from ..i18n import tr
import asyncio
import json
import time
from urllib.parse import urlsplit
import httpx

from ..core.models import AppError, TranslationRequest, TranslationResult
from .prompts import NORMAL, ACADEMIC, translation_prompt
from .text_input import translation_input


def endpoint_for(base_url: str) -> str:
    base = base_url.strip().rstrip('/')
    try:
        parts = urlsplit(base)
        _ = parts.port
    except ValueError:
        raise ValueError(tr('API 根地址无效')) from None
    if (parts.scheme not in ('https', 'http') or not parts.hostname or parts.username
            or parts.password or parts.query or parts.fragment or any(c.isspace() for c in base)):
        raise ValueError(tr('请填写没有账号、查询参数或片段的 HTTP(S) API 根地址'))
    if parts.scheme == 'http' and parts.hostname.lower() not in ('localhost', '127.0.0.1', '::1'):
        raise ValueError(tr('远程服务必须使用 HTTPS；仅本机允许 HTTP'))
    if parts.path.endswith('/chat/completions'):
        raise ValueError(tr('请填写 API 根地址，例如 https://服务域名/v1，不包含 /chat/completions'))
    return base + '/chat/completions'


class CompatibleProvider:
    def request_endpoint(self, settings):
        return endpoint_for(settings.base_url)

    def request_headers(self, settings, api_key):
        return {'Authorization': f'Bearer {api_key}'} if settings.requires_api_key else {}

    def parse_response(self, decoded):
        choice = decoded['choices'][0]
        reason = choice.get('finish_reason')
        return self.response_content(choice['message'], reason), reason

    def request_body(self, request):
        settings = request.settings_snapshot
        body = {'model': settings.model, 'stream': False, 'messages': [
            {'role': 'system', 'content': translation_prompt(settings)},
            {'role': 'user', 'content': translation_input(request.text)},
        ]}
        if settings.provider != 'nvidia':
            from .nvidia import extra_parameters
            try:
                body.update(extra_parameters(settings.extra_body_json))
            except ValueError as error:
                raise AppError('PARAMETERS', str(error)) from None
            if settings.max_tokens:
                body['max_completion_tokens' if settings.provider == 'openai' else 'max_tokens'] = settings.max_tokens
        return body

    def response_content(self, message, reason):
        from .nvidia import NvidiaProvider
        return NvidiaProvider.response_content(self, message, reason)

    def __init__(self, transport=None, trust_env=True):
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=5, read=30, write=10, pool=5),
            follow_redirects=False, transport=transport, trust_env=trust_env,
        )
        self.local_client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=5, read=120, write=10, pool=5),
            follow_redirects=False, transport=transport, trust_env=False)

    async def translate(self, request: TranslationRequest, api_key: str = '') -> TranslationResult:
        settings = request.settings_snapshot
        if not settings.base_url or not settings.model.strip():
            raise AppError('NOT_CONFIGURED', tr('尚未配置翻译服务，请打开设置。'))
        if not request.text.strip():
            raise AppError('EMPTY_INPUT', tr('原文为空，请先输入要翻译的文字。'))
        if len(request.text) > 8000:
            raise AppError('INPUT_LIMIT', tr('原文超过 8000 字符，请缩小选区或编辑。'))
        if settings.requires_api_key and not api_key:
            raise AppError('NO_KEY', tr('请在设置中填写 API Key。'))
        try:
            endpoint = self.request_endpoint(settings)
        except ValueError as error:
            raise AppError('INVALID_URL', str(error)) from None
        headers = self.request_headers(settings, api_key)
        body = self.request_body(request)
        started = time.perf_counter()
        try:
            async with asyncio.timeout(settings.total_timeout_seconds):
                local = urlsplit(endpoint).hostname in ('127.0.0.1', 'localhost', '::1')
                read_timeout = settings.total_timeout_seconds
                timeout = httpx.Timeout(connect=5, read=read_timeout, write=10, pool=5)
                client = self.local_client if local else self.client
                async with client.stream('POST', endpoint, headers=headers, json=body, timeout=timeout) as response:
                    if response.status_code != 200:
                        self._http_error(response.status_code)
                    data = bytearray()
                    async for chunk in response.aiter_bytes(chunk_size=65536):
                        data.extend(chunk)
                        if len(data) > 1024 * 1024:
                            raise AppError('RESPONSE_LIMIT', tr('服务返回内容过大，请缩小选区。'))
                decoded = json.loads(data)
                content, reason = self.parse_response(decoded)
                if reason == 'content_filter':
                    raise AppError('CONTENT_FILTER', tr('服务未返回译文，内容可能被服务拦截。'))
                if not isinstance(content, str) or not content.strip():
                    raise AppError('EMPTY_RESPONSE', tr('服务未返回有效译文，请检查模型。'))
                return TranslationResult(request.request_id, content.strip(),
                                         (time.perf_counter() - started) * 1000, reason)
        except (TimeoutError, httpx.TimeoutException):
            raise AppError('TIMEOUT', tr('翻译超时，原文已保留。'), True) from None
        except httpx.RequestError:
            if local:
                message = (tr('无法连接本机 Ollama，请启动 Ollama（ollama serve）后重试。')
                           if settings.provider == 'ollama' else tr('无法连接本机服务，请检查服务是否启动及端口是否正确。'))
            else:
                message = tr('无法连接翻译服务，请检查网络或系统代理。')
            raise AppError('CONNECTION', message, True) from None
        except (ValueError, KeyError, IndexError, TypeError, AttributeError):
            raise AppError('FORMAT', tr('服务返回格式不兼容，请检查模型与接口。')) from None

    @staticmethod
    def _http_error(status: int):
        if status in (401, 403):
            raise AppError('AUTH', tr('密钥无效或无访问权限，请检查设置。'))
        if status == 404:
            raise AppError('NOT_FOUND', tr('接口路径或模型不存在，请检查设置。'))
        if status == 429:
            raise AppError('RATE_LIMIT', tr('服务限流或额度不足，请稍后手动重试。'), True)
        if status == 402:
            raise AppError('QUOTA', tr('服务额度不足或需要启用计费，请检查服务账号。'))
        if status in (400, 422):
            raise AppError('PARAMETERS', tr('模型不接受当前参数，请核对模型 ID、输出上限和高级参数。'))
        if status >= 500:
            raise AppError('SERVICE', ui_format('{}{}{}', tr('翻译服务暂时不可用（HTTP '), status, tr('），请稍后重试或切换引擎。')), True)
        raise AppError('HTTP', ui_format('{}{}{}', tr('服务拒绝请求（HTTP '), status, tr('），请检查接口设置。')))

    async def aclose(self) -> None:
        await self.client.aclose()
        await self.local_client.aclose()

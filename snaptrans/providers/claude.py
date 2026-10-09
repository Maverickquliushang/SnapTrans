"""Anthropic's native Messages API, independently configured from chat APIs."""
from ..i18n import tr
from .compatible import CompatibleProvider, endpoint_for
from .nvidia import extra_parameters
from .prompts import translation_prompt
from .text_input import translation_input
from ..core.models import AppError


class ClaudeProvider(CompatibleProvider):
    def request_endpoint(self, settings):
        endpoint_for(settings.base_url)  # Same HTTPS and URL checks as other providers.
        return settings.base_url.rstrip('/') + '/messages'

    def request_headers(self, settings, api_key):
        return {'x-api-key': api_key, 'anthropic-version': '2023-06-01'}

    def request_body(self, request):
        s = request.settings_snapshot
        try:
            extra = extra_parameters(s.extra_body_json)
        except ValueError as error:
            raise AppError('PARAMETERS', str(error)) from None
        if set(extra) - {'temperature', 'top_p', 'top_k', 'stop', 'thinking'}:
            raise AppError('PARAMETERS', tr('Claude 高级参数仅支持 temperature、top_p、top_k、stop、thinking。'))
        if 'stop' in extra:
            stop = extra.pop('stop')
            extra['stop_sequences'] = [stop] if isinstance(stop, str) else stop
        return {'model': s.model, 'stream': False, 'max_tokens': s.max_tokens or 4096,
                'system': translation_prompt(s),
                'messages': [{'role': 'user', 'content': translation_input(request.text)}], **extra}

    def parse_response(self, decoded):
        content = ''.join(part['text'] for part in decoded['content'] if part.get('type') == 'text')
        reason = decoded.get('stop_reason')
        if reason == 'refusal':
            raise AppError('CONTENT_FILTER', tr('服务未返回译文，内容可能被服务拦截。'))
        return content, 'length' if reason == 'max_tokens' else 'stop'

import asyncio
import json
import pytest
import httpx
from snaptrans.core.models import AppError, ProviderSettings, TranslationRequest
from snaptrans.providers.compatible import CompatibleProvider, endpoint_for
from snaptrans.providers.text_input import translation_input


@pytest.mark.parametrize('source,expected', [('mismatch_mean', 'mismatch mean'),
    ('f(x) = mismatch_mean + 1', 'f(x) = mismatch_mean + 1'),
    ('Please keep model_name unchanged.', 'Please keep model_name unchanged.'),
    ('HTTP_PROXY', 'HTTP PROXY')])
def test_standalone_identifier_translation(source, expected):
    assert translation_input(source) == expected


def request(text='Public sample', **changes):
    values = dict(base_url='https://example.com/gateway/v1', model='example-model')
    values.update(changes)
    return TranslationRequest('id', text, ProviderSettings(**values))


def test_endpoint_prefix():
    assert endpoint_for('https://example.com/gateway/v1/') == 'https://example.com/gateway/v1/chat/completions'


@pytest.mark.parametrize('url', ['http://example.com/v1', 'https://user:password@example.com/v1',
                                'https://example.com/v1?key=secret', 'https://example.com/v1#key',
                                'file:///tmp/x', 'https://example.com/v1/chat/completions'])
def test_unsafe_endpoint(url):
    with pytest.raises(ValueError):
        endpoint_for(url)


def test_protocol():
    async def run():
        def handler(req):
            assert req.url.path == '/gateway/v1/chat/completions'
            assert req.headers['authorization'] == 'Bearer synthetic-key'
            body = json.loads(req.content)
            assert body['messages'][1]['content'] == 'Public sample'
            assert 'temperature' not in body
            return httpx.Response(200, json={'choices': [{'message': {'content': '测试译文'}, 'finish_reason': 'stop'}]})
        provider = CompatibleProvider(httpx.MockTransport(handler))
        try:
            assert (await provider.translate(request(), 'synthetic-key')).text == '测试译文'
        finally:
            await provider.aclose()
    asyncio.run(run())


@pytest.mark.parametrize('status,code', [(401, 'AUTH'), (403, 'AUTH'), (404, 'NOT_FOUND'), (429, 'RATE_LIMIT'), (503, 'SERVICE'), (302, 'HTTP')])
def test_http_errors(status, code):
    async def run():
        provider = CompatibleProvider(httpx.MockTransport(lambda req: httpx.Response(status)))
        try:
            with pytest.raises(AppError) as captured:
                await provider.translate(request(), 'synthetic-key')
            assert captured.value.code == code
        finally:
            await provider.aclose()
    asyncio.run(run())


@pytest.mark.parametrize('body,code', [(b'not-json', 'FORMAT'), (b'{}', 'FORMAT'),
                                     (b'{"choices":[{"message":{"content":""}}]}', 'EMPTY_RESPONSE'),
                                     (b'x' * (1024*1024+1), 'RESPONSE_LIMIT')],
                         ids=['not-json', 'missing-choices', 'empty-content', 'oversized'])
def test_bad_response(body, code):
    async def run():
        provider = CompatibleProvider(httpx.MockTransport(lambda req: httpx.Response(200, content=body)))
        try:
            with pytest.raises(AppError) as captured:
                await provider.translate(request(), 'synthetic-key')
            assert captured.value.code == code
        finally:
            await provider.aclose()
    asyncio.run(run())


def test_cancellation_and_deadline():
    async def run():
        async def slow(req):
            await asyncio.sleep(5)
        provider = CompatibleProvider(httpx.MockTransport(slow))
        try:
            with pytest.raises(AppError) as captured:
                await provider.translate(request(total_timeout_seconds=.01), 'key')
            assert captured.value.code == 'TIMEOUT'
            task = asyncio.create_task(provider.translate(request(), 'key'))
            await asyncio.sleep(.01)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        finally:
            await provider.aclose()
    asyncio.run(run())


def test_local_no_auth():
    async def run():
        def handler(req):
            assert 'authorization' not in req.headers
            return httpx.Response(200, json={'choices': [{'message': {'content': '你好'}}]})
        provider = CompatibleProvider(httpx.MockTransport(handler))
        try:
            await provider.translate(request(base_url='http://127.0.0.1:11434/v1', requires_api_key=False), 'ignored')
        finally:
            await provider.aclose()
    asyncio.run(run())

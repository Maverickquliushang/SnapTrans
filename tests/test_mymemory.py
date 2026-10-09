import asyncio
import httpx
import pytest
from snaptrans.providers.mymemory import MyMemoryProvider, split_utf8
from snaptrans.providers.catalog import default_profile
from snaptrans.core.models import ProviderSettings, TranslationRequest, AppError


def request(text):
    return TranslationRequest('free-test', text, ProviderSettings(**default_profile('mymemory')))


def test_chunk_boundaries_preserve_unicode_and_byte_limit():
    original = ('An English sentence. 中文🙂测试。 ' * 60).strip()
    chunks = split_utf8(original)
    assert ''.join(chunks) == original
    assert all(len(part.encode('utf-8')) <= 500 for part in chunks)


def test_free_endpoint_no_key_and_reassembly():
    async def run():
        sent = []
        def handler(req):
            assert req.method == 'GET' and req.url.path == '/get'
            assert set(req.url.params.keys()) == {'q', 'langpair'}
            assert req.url.params['langpair'] == 'en|zh-CN'
            assert 'authorization' not in req.headers
            sent.append(req.url.params['q'])
            return httpx.Response(200, json={'responseStatus': 200, 'quotaFinished': False,
                                            'responseData': {'translatedText': '甲 &amp; 乙'}})
        provider = MyMemoryProvider(httpx.MockTransport(handler))
        try:
            result = await provider.translate(request('test ' * 200), 'ignored-secret')
            assert len(sent) > 1
            assert result.text == '\n'.join(['甲 & 乙'] * len(sent))
        finally:
            await provider.aclose()
    asyncio.run(run())


@pytest.mark.parametrize('data,code', [
    ({'responseStatus': 200, 'quotaFinished': True}, 'FREE_QUOTA'),
    ({'responseStatus': 429}, 'FREE_QUOTA'),
    ({'responseStatus': 500}, 'FREE_SERVICE'),
    ({'responseStatus': 200, 'responseData': {'translatedText': ''}}, 'EMPTY_RESPONSE')])
def test_free_errors_are_not_shown_as_translation(data, code):
    async def run():
        provider = MyMemoryProvider(httpx.MockTransport(lambda r: httpx.Response(200, json=data)))
        try:
            with pytest.raises(AppError) as captured:
                await provider.translate(request('Hello.'))
            assert captured.value.code == code
        finally:
            await provider.aclose()
    asyncio.run(run())

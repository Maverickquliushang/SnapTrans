"""Bounded NVIDIA requests, SSE progress and official 202 status polling."""
from ..i18n import tr
import asyncio
import json
from uuid import UUID
import httpx
from ..core.models import AppError
from .compatible import CompatibleProvider


async def response_json(client, endpoint, body, secret, timeout_seconds, progress=lambda text: None):
    headers = {'Authorization': 'Bearer ' + secret, 'Accept': 'text/event-stream' if body.get('stream') else 'application/json'}
    timeout = httpx.Timeout(connect=10, read=timeout_seconds, write=30, pool=5)
    url, method, payload = endpoint, 'POST', body
    async with asyncio.timeout(timeout_seconds):
        while True:
            async with client.stream(method, url, headers=headers, json=payload, timeout=timeout) as response:
                if response.status_code == 202:
                    request_id = response.headers.get('NVCF-REQID', '')
                    try:
                        request_id = str(UUID(request_id))
                    except ValueError:
                        raise AppError('PENDING', tr('服务正在排队，但没有返回有效任务编号，请稍后重试。'), True) from None
                    # Fixed origin and path: never follow an untrusted redirect or status URL.
                    root = 'https://ai.api.nvidia.com' if endpoint.startswith('https://ai.api.nvidia.com/') else 'https://integrate.api.nvidia.com'
                    url, method, payload = root + '/v1/status/' + request_id, 'GET', None
                    progress(tr('服务正在排队'))
                else:
                    if response.status_code == 410:
                        raise AppError('RETIRED', tr('该模型的 NVIDIA 托管端点已下线，请换用模型页面标为可用的模型。'))
                    if response.status_code != 200:
                        CompatibleProvider._http_error(response.status_code)
                    if 'text/event-stream' in response.headers.get('content-type', ''):
                        content, reasoning, reason, size, complete = [], False, None, 0, False
                        async for line in response.aiter_lines():
                            size += len(line.encode('utf-8'))
                            if size > 4 * 1024 * 1024:
                                raise AppError('RESPONSE_LIMIT', tr('服务返回内容过大，请缩小选区。'))
                            if not line.startswith('data:'):
                                continue
                            item = line[5:].strip()
                            if item == '[DONE]':
                                complete = True
                                break
                            decoded = json.loads(item)
                            if decoded.get('error'):
                                raise AppError('STREAM_ERROR', tr('服务中断了生成，请稍后重试。'), True)
                            choices = decoded.get('choices') or []
                            if not choices:
                                continue
                            choice = choices[0]
                            delta = choice.get('delta', {})
                            if delta.get('reasoning_content'):
                                reasoning = True
                                progress(tr('模型正在推理'))
                            if delta.get('content'):
                                content.append(delta['content'])
                                progress(tr('正在接收结果'))
                            reason = choice.get('finish_reason') or reason
                        if not complete and reason is None:
                            raise AppError('STREAM_INTERRUPTED', tr('服务连接提前结束，未收到完整结果，请重试。'), True)
                        return {'choices': [{'message': {'content': ''.join(content), 'reasoning_content': reasoning}, 'finish_reason': reason}]}
                    data = bytearray()
                    async for chunk in response.aiter_bytes():
                        data.extend(chunk)
                        if len(data) > 4 * 1024 * 1024:
                            raise AppError('RESPONSE_LIMIT', tr('服务返回内容过大，请缩小选区。'))
                    return json.loads(data)
            await asyncio.sleep(1)

"""Hosted Nemotron OCR v2 adapter. Sends only a user-selected crop, never the desktop."""
from ..i18n import tr
import asyncio
import base64
import io
import json
import math
import time
import httpx
from PIL import Image
from ..core.models import AppError, OcrResult, OcrLine
from .compatible import CompatibleProvider

OCR_ENDPOINT = 'https://ai.api.nvidia.com/v1/cv/nvidia/nemotron-ocr-v2'


def encode_crop(frame):
    image = Image.frombytes('RGB', (frame.width_px, frame.height_px), frame.rgb_bytes)
    # Preserve native text pixels; ask for a smaller region if inline budget is exceeded.
    # Hosted inline requests have a small payload budget. Prefer lossless PNG
    # for text; use JPEG if necessary, and reject instead of silently blurring it.
    output = io.BytesIO()
    image.save(output, 'PNG', optimize=True)
    fmt = 'png'
    if len(output.getvalue()) > 130_000:
        for quality in (95, 90):
            output = io.BytesIO()
            image.save(output, 'JPEG', quality=quality, optimize=True)
            fmt = 'jpeg'
            if len(output.getvalue()) <= 130_000:
                break
    if len(output.getvalue()) > 130_000:
        raise AppError('IMAGE_LIMIT', tr('云端 OCR 的图片请求过大，请缩小选区，或切换本地 OCR。'))
    return f'data:image/{fmt};base64,' + base64.b64encode(output.getvalue()).decode('ascii')


def parse_detections(decoded, frame, elapsed):
    detections = decoded['data'][0]['text_detections']
    if not isinstance(detections, list):
        raise ValueError('Invalid detections')
    lines = []
    for detection in detections:
        prediction = detection['text_prediction']
        text = prediction['text']
        if not isinstance(text, str):
            raise ValueError('Invalid text')
        points = detection['bounding_box']['points']
        if len(points) < 4:
            raise ValueError('Invalid polygon')
        coordinates = [(float(point['x']), float(point['y'])) for point in points]
        if any(not math.isfinite(v) or not 0 <= v <= 1 for point in coordinates for v in point):
            raise ValueError('Invalid normalized coordinates')
        polygon = tuple((x * frame.width_px, y * frame.height_px) for x, y in coordinates)
        confidence = prediction.get('confidence')
        if text.strip():
            lines.append(OcrLine(text.strip(), polygon, confidence))
    # The server supplies its reading order; preserve it (especially columns).
    return OcrResult(frame.request_id, '\n'.join(line.text for line in lines), lines, elapsed)


class NvidiaOcrProvider:
    def __init__(self, transport=None):
        self.client = httpx.AsyncClient(follow_redirects=False, transport=transport)

    async def recognize(self, frame, settings, secret):
        if not secret:
            raise AppError('NO_OCR_KEY', tr('请在设置 → 文字识别中填写 NVIDIA OCR API Key，或选择本地 OCR。'))
        started = time.perf_counter()
        try:
            async with asyncio.timeout(settings['total_timeout_seconds']):
                encoded = await asyncio.to_thread(encode_crop, frame)
                body = {'input': [{'type': 'image_url', 'url': encoded}], 'merge_levels': ['sentence']}
                timeout = httpx.Timeout(connect=10, read=settings['total_timeout_seconds'], write=20, pool=5)
                headers = {'Authorization': 'Bearer ' + secret, 'Accept': 'application/json'}
                async with self.client.stream('POST', OCR_ENDPOINT, headers=headers, json=body, timeout=timeout) as response:
                    if response.status_code == 413:
                        raise AppError('IMAGE_LIMIT', tr('云端 OCR 拒绝了过大的图片，请缩小选区。'))
                    if response.status_code == 202:
                        raise AppError('OCR_PENDING', tr('云端 OCR 仍在排队，本次未返回文字，请稍后重试或使用本地 OCR。'), True)
                    if response.status_code != 200:
                        CompatibleProvider._http_error(response.status_code)
                    data = bytearray()
                    async for chunk in response.aiter_bytes():
                        data.extend(chunk)
                        if len(data) > 2 * 1024 * 1024:
                            raise AppError('RESPONSE_LIMIT', tr('云端 OCR 返回内容过大，请缩小选区。'))
                return parse_detections(json.loads(data), frame, (time.perf_counter() - started) * 1000)
        except (TimeoutError, httpx.TimeoutException):
            raise AppError('OCR_TIMEOUT', tr('NVIDIA OCR 超时，图片选区已保留，可重试或切换本地识别。'), True) from None
        except httpx.RequestError:
            raise AppError('OCR_CONNECTION', tr('无法连接 NVIDIA OCR，请检查网络与账号权限。'), True) from None
        except (ValueError, KeyError, IndexError, TypeError):
            raise AppError('OCR_FORMAT', tr('NVIDIA OCR 返回格式不兼容，未用异常内容替换原文。')) from None

    async def aclose(self):
        await self.client.aclose()

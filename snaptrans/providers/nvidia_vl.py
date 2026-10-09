"""NVIDIA VLM text transcription: preserve crop pixels and paragraph breaks."""
from ..i18n import tr
import asyncio
import base64
import io
import time
import httpx
from PIL import Image
from ..core.models import AppError, OcrResult
from .nvidia_http import response_json
from .nvidia import NvidiaProvider
from .model_cards import model_card


def image_content(frame):
    image = Image.frombytes('RGB', (frame.width_px, frame.height_px), frame.rgb_bytes)
    output = io.BytesIO()
    image.save(output, 'PNG', optimize=True)
    if len(output.getvalue()) > 130000:
        raise AppError('IMAGE_LIMIT', tr('视觉识别图片过大，请按段落缩小选区；为保证小字清晰，本模式不压缩分辨率。'))
    return 'data:image/png;base64,' + base64.b64encode(output.getvalue()).decode('ascii')


class NvidiaVisionProvider:
    def __init__(self, transport=None):
        self.client = httpx.AsyncClient(follow_redirects=False, transport=transport)
        self.progress = lambda *args: None

    async def recognize(self, frame, settings, secret):
        if not secret:
            raise AppError('NO_OCR_KEY', tr('请在文字识别中填写 NVIDIA Key。'))
        started = time.monotonic()
        try:
            async with asyncio.timeout(settings['total_timeout_seconds']):
                url = await asyncio.to_thread(image_content, frame)
                model = settings['model']
                body = {**model_card(model)['extra'], 'model': model, 'max_tokens': settings['max_tokens'], 'stream': True,
                    'messages': [{'role': 'user', 'content': [
                        {'type': 'text', 'text': 'Transcribe all visible text exactly in reading order. Preserve paragraphs, punctuation, numbers, symbols and original language. Do not translate, summarize, explain, or complete missing text. Output only the transcription. Mark unreadable text as [unclear].'},
                        {'type': 'image_url', 'image_url': {'url': url}}]}]}
                data = await response_json(self.client, 'https://integrate.api.nvidia.com/v1/chat/completions',
                    body, secret, settings['total_timeout_seconds'], lambda text: self.progress(frame.request_id, text))
                choice = data['choices'][0]
                text = NvidiaProvider.response_content(self, choice['message'], choice.get('finish_reason'))
                if choice.get('finish_reason') == 'length':
                    raise AppError('OCR_TRUNCATED', tr('视觉识别达到输出上限，结果未完整返回。请增加识别 tokens 或缩小选区。'))
                if not text.strip():
                    raise AppError('NO_TEXT', tr('视觉模型没有返回文字，请缩小选区或切换本地识别。'))
                return OcrResult(frame.request_id, text.strip(), [], (time.monotonic()-started)*1000)
        except (TimeoutError, httpx.TimeoutException):
            raise AppError('OCR_TIMEOUT', tr('NVIDIA 视觉识别超时，可稍后重试或选择本地识别。'), True) from None
        except httpx.RequestError:
            raise AppError('OCR_CONNECTION', tr('无法连接 NVIDIA 视觉识别服务。'), True) from None
        except (ValueError, KeyError, IndexError, TypeError):
            raise AppError('OCR_FORMAT', tr('视觉识别返回格式异常。')) from None

    async def aclose(self):
        await self.client.aclose()

"""Read a key from stdin, probe public samples; never persist credentials or raw errors."""
import asyncio
import base64
import io
import json
from pathlib import Path
import sys
import time
import httpx
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]


async def probe(client, secret, model, vision=False):
    content = 'Translate into Simplified Chinese. Return only the translation: Hello world.'
    if vision:
        picture = Image.new('RGB', (1100, 150), 'white')
        draw = ImageDraw.Draw(picture)
        draw.text((15, 20), 'The model achieved 95.2% accuracy.', fill='black', font_size=35)
        draw.text((15, 75), 'Preserve visual evidence across agents.', fill='black', font_size=35)
        data = io.BytesIO()
        picture.save(data, 'PNG')
        content = [{'type': 'text', 'text': 'Read all text in this image. Output only the exact text, without translation or explanation.'},
                   {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,' + base64.b64encode(data.getvalue()).decode()}}]
    body = {'model': model, 'messages': [{'role': 'user', 'content': content}], 'max_tokens': 256, 'stream': False}
    if model == 'nvidia/nemotron-3-super-120b-a12b':
        body['reasoning_effort'] = 'none'
    if model == 'nvidia/nemotron-3-nano-omni-30b-a3b-reasoning':
        body['chat_template_kwargs'] = {'enable_thinking': False}
    started = time.monotonic()
    result = {'model': model, 'vision': vision}
    try:
        response = await client.post('https://integrate.api.nvidia.com/v1/chat/completions',
                                     headers={'Authorization': 'Bearer ' + secret}, json=body)
        result['status'] = response.status_code
        if response.status_code == 200:
            answer = response.json()['choices'][0]
            result.update(text=answer['message'].get('content', '')[:500], finish_reason=answer.get('finish_reason'))
        else:
            # Bound and redact the server error; never print headers or payload.
            result['message'] = response.text.replace(secret, '[redacted]')[:700]
    except Exception as error:
        result['error_type'] = type(error).__name__
    result['seconds'] = round(time.monotonic() - started, 2)
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return result


async def main():
    secret = sys.stdin.readline().strip()
    async with httpx.AsyncClient(timeout=45, follow_redirects=False) as client:
        results = await asyncio.gather(*(probe(client, secret, model, vision) for model, vision in [
            ('deepseek-ai/deepseek-v4.1-flash', False),
            ('nvidia/nemotron-3-nano-omni-30b-a3b-reasoning', True)]))
    destination = ROOT / '.tmp' / 'v160-nvidia-probe-selected.json'
    destination.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    asyncio.run(main())

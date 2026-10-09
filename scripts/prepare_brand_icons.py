"""Fetch pinned, attributed brand artwork once; the app only reads bundled assets."""
from pathlib import Path
import concurrent.futures
import hashlib
import json
import xml.etree.ElementTree as ET
import httpx

ROOT = Path(__file__).resolve().parents[1]
REVISION = 'c385b2b8d1f9e19aa86e628d4e23c91ee1111a47'
BASE = f'https://raw.githubusercontent.com/lobehub/lobe-icons/{REVISION}'
ICONS = {
    'deepseek': 'deepseek-color', 'qwen': 'qwen-color', 'glm': 'zhipu-color',
    'kimi': 'kimi-color', 'doubao': 'doubao-color', 'hunyuan': 'hunyuan-color',
    'ernie': 'baidu-color', 'minimax': 'minimax-color', 'siliconflow': 'siliconcloud-color',
    'openai': 'openai', 'gemini': 'gemini-color', 'claude': 'claude-color', 'grok': 'grok',
    'nvidia': 'nvidia-color', 'google': 'googlecloud-color', 'microsoft': 'microsoft-color',
    'deepl': 'deepl-color', 'baidu': 'baidu-color', 'ollama': 'ollama',
    'lmstudio': 'lmstudio', 'vllm': 'vllm-color', 'google_web': 'google-color', 'bing_web': 'bing-color',
}


def main():
    directory = ROOT / 'assets' / 'providers'
    directory.mkdir(parents=True, exist_ok=True)
    previous = json.loads((directory / 'sources.json').read_text()) if (directory / 'sources.json').exists() else {}
    def download(item):
        name, filename = item
        url = f'{BASE}/packages/static-svg/icons/{filename}.svg'
        path = directory / f'{name}.svg'
        if path.exists() and previous.get(name, {}).get('url') == url and hashlib.sha256(path.read_bytes()).hexdigest() == previous[name]['sha256']:
            return name, previous[name]
        response = httpx.get(url, timeout=40)
        response.raise_for_status()
        data = response.content
        root = ET.fromstring(data)
        assert root.tag.endswith('svg') and len(data) < 200000
        assert b'<script' not in data and b'<image' not in data
        (directory / f'{name}.svg').write_bytes(data)
        return name, {'url': url, 'sha256': hashlib.sha256(data).hexdigest()}
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        manifest = dict(executor.map(download, ICONS.items()))
    # Brand-owned public favicons for services not represented by Lobe Icons.
    for name, url, suffix in (
        ('youdao', 'https://ydlunacommon-cdn.nosdn.127.net/31cf4b56e6c0b3af668aa079de1a898c.png', 'png'),
        ('mymemory', 'https://mymemory.translated.net/public/img/favicon-32x32.png', 'png'),
        ('libre', 'https://libretranslate.com/static/icon.svg', 'svg'),
        ('tencent_web', 'https://fanyi.qq.com/favicon.ico', 'ico'),
    ):
        path = directory / f'{name}.{suffix}'
        if path.exists() and previous.get(name, {}).get('url') == url and hashlib.sha256(path.read_bytes()).hexdigest() == previous[name]['sha256']:
            manifest[name] = previous[name]
            continue
        response = httpx.get(url, timeout=40)
        response.raise_for_status()
        (directory / f'{name}.{suffix}').write_bytes(response.content)
        manifest[name] = {'url': url, 'sha256': hashlib.sha256(response.content).hexdigest(), 'attribution': 'Brand-owned site artwork; trademarks belong to their owners.'}
    if not (directory / 'LICENSE-lobe-icons.txt').exists():
        license_text = httpx.get(f'{BASE}/LICENSE', timeout=40)
        license_text.raise_for_status()
        (directory / 'LICENSE-lobe-icons.txt').write_text(license_text.text, encoding='utf-8')
    (directory / 'sources.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(f'Prepared {len(manifest)} brand SVGs and their source/license records.')


if __name__ == '__main__':
    main()

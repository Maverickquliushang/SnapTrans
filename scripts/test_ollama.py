"""Explicit live local test, using public synthetic input. No model download."""
import argparse
import asyncio
from dataclasses import replace
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from snaptrans.core.models import ProviderSettings, TranslationRequest
from snaptrans.core.ocr_adapter import OcrAdapter
from snaptrans.providers.compatible import CompatibleProvider
from snaptrans.self_test import sample_frame


async def run(model):
    engine = OcrAdapter(ROOT / 'assets' / 'ocr')
    ocr = engine.recognize(sample_frame())
    settings = ProviderSettings(provider='ollama', base_url='http://127.0.0.1:11434/v1', model=model,
                                requires_api_key=False, total_timeout_seconds=120)
    provider = CompatibleProvider(trust_env=False)
    records = []
    try:
        for mode, text in [('normal', 'Hello.'), ('academic', ocr.raw_text)]:
            print(f'Testing local model: {mode}', flush=True)
            result = await provider.translate(TranslationRequest('ollama-test', text, replace(settings, mode=mode)))
            if not any('\u4e00' <= char <= '\u9fff' for char in result.text):
                raise RuntimeError('Local model did not return Chinese')
            records.append({'mode': mode, 'input': text, 'output': result.text, 'elapsed_ms': result.elapsed_ms})
            print(json.dumps(records[-1], ensure_ascii=False), flush=True)
        report = {'model': model, 'endpoint': settings.base_url, 'real_ocr_to_translation': True, 'results': records}
        (ROOT / '.tmp' / 'ollama-test.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    finally:
        await provider.aclose()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', required=True)
    asyncio.run(run(parser.parse_args().model))

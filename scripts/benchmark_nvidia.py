"""Small reproducible translation comparison. Private API key is read only from stdin."""
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from snaptrans.core.models import AppError, ProviderSettings, TranslationRequest
from snaptrans.providers.nvidia import NvidiaProvider

SAMPLES = [
    ('visual-evidence', 'Vision-language models (VLMs) can lose visual evidence across agent turns. '
     'We introduce Visual Flow, a lightweight method that preserves selected visual tokens. '
     'Across 120 samples, accuracy increased from 89.1% to 95.2% [12]. '
     'This result suggests an association, but does not establish causality.',
     ['VLMs', 'Visual Flow', '120', '89.1%', '95.2%', '[12]']),
    ('balanced-labels', 'Balanced pseudolabeling improves emotion recognition in conversation (ERC) '
     'by controlling class imbalance. The macro-F1 score was 68.4, compared with 65.7 for the baseline. '
     'However, the improvement was not statistically significant (p = 0.08). '
     'We minimize L = L_sup + 0.5 L_unsup and report the mean over 3 random seeds.',
     ['ERC', '68.4', '65.7', '0.08', 'L_sup', '0.5', 'L_unsup', '3']),
]
MODELS = [
    ('nvidia/nemotron-3-super-120b-a12b', {'reasoning_effort': 'none'}),
    ('nvidia/nemotron-3.5-lightning-30b-a3b',
     {'temperature': 1, 'top_p': 0.95, 'chat_template_kwargs': {'enable_thinking': True}, 'reasoning_budget': 2048}),
    ('moonshotai/kimi-k3', {'temperature': 1, 'reasoning_effort': 'low'}),
    ('z-ai/glm-5.3-flash', {'temperature': 0.5, 'top_p': 1}),
]

async def main():
    key = sys.stdin.readline().strip()
    if not key:
        raise SystemExit('API key required on stdin')
    semaphore = asyncio.Semaphore(2)
    async def run(model, extra, sample):
        async with semaphore:
            provider = NvidiaProvider()
            started = time.monotonic()
            phases = []
            provider.progress = lambda request_id, phase: phases.append(phase) if phase not in phases else None
            name, source, markers = sample
            record = dict(model=model, sample=name, source=source, parameters=extra,
                          max_tokens=4096, timeout_seconds=60)
            try:
                settings = ProviderSettings(provider='nvidia', base_url='https://integrate.api.nvidia.com/v1',
                    model=model, mode='academic', max_tokens=4096, model_defaults=False,
                    extra_body_json=json.dumps(extra), total_timeout_seconds=60)
                result = await provider.translate(TranslationRequest('benchmark-' + name, source, settings), key)
                record.update(ok=True, translation=result.text, finish_reason=result.finish_reason,
                    retained_markers={value: value in result.text for value in markers})
            except AppError as error:
                record.update(ok=False, code=error.code, message=error.user_message)
            finally:
                await provider.aclose()
            record.update(seconds=round(time.monotonic()-started, 2), phases=phases)
            print(json.dumps(record, ensure_ascii=False), flush=True)
            return record
    fast = '--fast' in sys.argv
    models = [
        ('nvidia/nemotron-3.5-lightning-30b-a3b', {'chat_template_kwargs': {'enable_thinking': False}}),
        ('nvidia/nemotron-3-nano-omni-30b-a3b-reasoning', {'chat_template_kwargs': {'enable_thinking': False}}),
    ] if fast else MODELS
    records = await asyncio.gather(*(run(model, extra, sample) for sample in SAMPLES for model, extra in models))
    report = dict(date=datetime.now(timezone.utc).isoformat(), samples_per_model=2,
                  notes='Synthetic public text; small smoke comparison, not a general quality benchmark.', results=records)
    target = ROOT / ('.tmp/v160-model-comparison-fast.json' if fast else '.tmp/v160-model-comparison.json')
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')

if __name__ == '__main__':
    asyncio.run(main())

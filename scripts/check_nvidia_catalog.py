"""Public catalog connectivity check; no API key or inference requests."""
import asyncio
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from snaptrans.providers.nvidia import NvidiaProvider
from snaptrans.providers.catalog import default_profile
from snaptrans import __version__


async def main():
    provider = NvidiaProvider()
    try:
        models = await provider.list_models()
        default_model = default_profile('nvidia')['model']
        report = {'ok': bool(models), 'model_count': len(models), 'api_key_used': False,
                  'inference_tested': False, 'default_model': default_model,
                  'default_model_listed': default_model in models}
        (ROOT / 'output' / f'nvidia-catalog-{__version__}.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(report))
    finally:
        await provider.aclose()


if __name__ == '__main__':
    asyncio.run(main())

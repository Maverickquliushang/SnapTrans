"""Copy the pinned wheel's models; emit verifiable, offline runtime assets."""
import hashlib
import importlib.metadata
import json
from pathlib import Path
import shutil
import urllib.request
import yaml

ROOT = Path(__file__).resolve().parents[1]


def main():
    if importlib.metadata.version('rapidocr') != '3.9.2':
        raise RuntimeError('Expected rapidocr 3.9.2')
    package = Path(importlib.metadata.distribution('rapidocr').locate_file('rapidocr'))
    destination = ROOT / 'assets' / 'ocr'
    (destination / 'models').mkdir(parents=True, exist_ok=True)
    (destination / 'licenses').mkdir(exist_ok=True)
    config = yaml.safe_load((package / 'config.yaml').read_text(encoding='utf-8'))
    mapping = {'Det': 'PP-OCRv6_det_small.onnx', 'Cls': 'ch_ppocr_mobile_v2.0_cls_mobile.onnx',
               'Rec': 'PP-OCRv6_rec_small.onnx'}
    records = []
    for section, filename in mapping.items():
        source = package / 'models' / filename
        target = destination / 'models' / filename
        shutil.copyfile(source, target)
        config[section]['model_path'] = 'models/' + filename
        records.append({'role': section, 'path': 'models/' + filename,
                        'source': f'rapidocr-3.9.2 wheel: rapidocr/models/{filename}',
                        'upstream_version': config[section]['ocr_version'],
                        'size': target.stat().st_size,
                        'sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
                        'license': 'licenses/PaddleOCR-LICENSE',
                        'dictionary': 'embedded ONNX character metadata' if section == 'Rec' else None})
    config['Global']['log_level'] = 'critical'
    config['Global']['max_side_len'] = 8192
    # Desktop text strips must not be enlarged until their short side reaches
    # 736 pixels: that fragments lines and duplicates overlapping detections.
    config['Det']['limit_type'] = 'max'
    config['Det']['limit_side_len'] = 1600
    (destination / 'config.yaml').write_text(yaml.safe_dump(config, sort_keys=False), encoding='utf-8')
    for name, url in {
        'PaddleOCR-LICENSE': 'https://raw.githubusercontent.com/PaddlePaddle/PaddleOCR/main/LICENSE',
        'RapidOCR-LICENSE': 'https://raw.githubusercontent.com/RapidAI/RapidOCR/main/LICENSE',
    }.items():
        target = destination / 'licenses' / name
        if not target.exists():
            with urllib.request.urlopen(url, timeout=30) as response:
                target.write_bytes(response.read())
    manifest = {'rapidocr_version': '3.9.2', 'models': records,
                'model_license_sources': ['https://github.com/PaddlePaddle/PaddleOCR',
                                          'https://huggingface.co/RapidAI/RapidOCR'],
                'config_sha256': hashlib.sha256((destination / 'config.yaml').read_bytes()).hexdigest()}
    (destination / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print('Prepared 3 bundled OCR models and license materials.')


if __name__ == '__main__':
    main()

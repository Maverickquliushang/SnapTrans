"""Synthetic regression corpus, not a claim of accuracy on real papers."""
from dataclasses import replace
import json
import os
from pathlib import Path
import statistics
import sys
import time
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from snaptrans.core.models import CaptureFrame
from snaptrans.core.ocr_adapter import OcrAdapter


def distance(a, b):
    row = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        new = [i]
        for j, cb in enumerate(b, 1):
            new.append(min(new[-1]+1, row[j]+1, row[j-1]+(ca != cb)))
        row = new
    return row[-1]


def main():
    texts = [
        'The model achieved 95.2% accuracy.',
        'We evaluate the proposed method on three datasets.',
        'The results show a significant improvement.',
        'Please select a file and click Save.',
        'The training process uses a batch size of 32.',
        'This method does not require additional labels.',
        'The learning rate is set to 0.001.',
        'Figure 2 presents the experimental results.',
        'We use a low-rank approximation in this experiment.',
        'The average response time was 120 ms.',
    ]
    engine = OcrAdapter(ROOT / 'assets' / 'ocr')
    samples = []
    for size in (24, 32, 42):
        font = ImageFont.truetype(str(Path(os.environ['WINDIR']) / 'Fonts' / 'arial.ttf'), size)
        for index, text in enumerate(texts):
            width = int(font.getlength(text)) + 60
            image = Image.new('RGB', (width, size+60), 'white')
            ImageDraw.Draw(image).text((20, 20), text, font=font, fill='black')
            frame = CaptureFrame(str(index), 'synthetic', (0,0,width,size+60), (0,0,width,size+60),
                                 (0,0,width,size+60), width, size+60, image.tobytes())
            result = engine.recognize(frame)
            cer = distance(result.raw_text.strip(), text) / len(text)
            samples.append({'font_size': size, 'input': text, 'recognized': result.raw_text,
                            'cer': cer, 'elapsed_ms': result.elapsed_ms})
    times = sorted(sample['elapsed_ms'] for sample in samples)
    report = {'scope': '30 synthetic English samples; not real-paper accuracy', 'samples': samples,
              'mean_cer': statistics.mean(sample['cer'] for sample in samples),
              'ocr_p50_ms': statistics.median(times), 'ocr_p95_ms': times[int(.95*(len(times)-1))]}
    output = ROOT / 'docs' / 'ocr-benchmark.json'
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({key:value for key,value in report.items() if key != 'samples'}))
    return 0 if report['mean_cer'] <= .03 else 1


if __name__ == '__main__':
    raise SystemExit(main())

"""Deterministic icon and default configuration; no external artwork."""
import json
from pathlib import Path
import sys
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from snaptrans.config import DEFAULT

assets = ROOT / 'assets'
assets.mkdir(exist_ok=True)
image = Image.new('RGBA', (256, 256), (0, 0, 0, 0))
draw = ImageDraw.Draw(image)
draw.rounded_rectangle((8, 8, 248, 248), 48, fill='#15344a')
for points in [((48, 93), (48, 48), (93, 48)), ((163, 48), (208, 48), (208, 93)),
               ((48, 163), (48, 208), (93, 208)), ((163, 208), (208, 208), (208, 163))]:
    draw.line(points, fill='#67e8f9', width=12)
draw.line([(86, 94), (170, 94)], fill='white', width=13)
draw.line([(128, 94), (128, 166)], fill='white', width=13)
image.save(assets / 'icon.png')
image.save(assets / 'icon.ico', sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
# PNG controls work without optional Qt SVG plugins in the portable build.
(assets / 'ui').mkdir(exist_ok=True)
for name, points, color in (
    ('chevron', [(16, 24), (32, 40), (48, 24)], '#b8c2d3'),
    ('chevron-dark', [(16, 24), (32, 40), (48, 24)], '#40536b'),
    ('check', [(14, 32), (26, 44), (50, 20)], 'white')):
    control = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
    ImageDraw.Draw(control).line(points, fill=color, width=7, joint='curve')
    control.resize((32, 32), Image.Resampling.LANCZOS).save(assets / 'ui' / (name + '.png'))
(assets / 'default.json').write_text(json.dumps(DEFAULT, ensure_ascii=False, indent=2), encoding='utf-8')
print('Icon and defaults generated.')

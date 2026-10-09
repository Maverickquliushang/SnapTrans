"""Deterministic installer surfaces using the application's daylight palette."""
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]


def generate():
    target = ROOT/'assets/installer'
    target.mkdir(exist_ok=True)
    scale = 3
    canvas = Image.new('RGB', (164*scale, 314*scale), '#e0ebff')
    draw = ImageDraw.Draw(canvas)
    def box(rect, color, radius=12):
        draw.rounded_rectangle(tuple(int(x*scale) for x in rect), radius*scale, fill=color)
    box((12,12,152,302),'#f4f7fb',18)
    box((24,96,140,160),'#ffffff')
    box((24,174,140,238),'#ffffff')
    box((24,254,140,280),'#205bb8',8)
    for top in (110,188):
        box((35,top,90,top+6),'#172b49',3)
        box((35,top+14,126,top+18),'#d9e6f7',2)
        box((35,top+26,112,top+30),'#d9e6f7',2)
    draw.rounded_rectangle((39*scale,35*scale,125*scale,79*scale),8*scale,outline='#205bb8',width=2*scale)
    for x,y in ((39,35),(125,35),(39,79),(125,79)):
        draw.ellipse(((x-3)*scale,(y-3)*scale,(x+3)*scale,(y+3)*scale),fill='#205bb8')
    canvas.resize((164,314),Image.Resampling.LANCZOS).save(target/'welcome.bmp')
    header=Image.new('RGB',(150,57),'#f4f7fb')
    icon=Image.open(ROOT/'assets/icon.png').convert('RGBA').resize((40,40),Image.Resampling.LANCZOS)
    header.paste(icon,(95,8),icon)
    header.save(target/'header.bmp')


if __name__ == '__main__':
    generate()

import re
from statistics import median
from .models import OcrResult


def clean_text(result: OcrResult) -> str:
    if not result.lines:
        return result.raw_text.replace('\x00', '').replace('\r\n', '\n').strip()
    lines = result.lines
    heights = [max(p[1] for p in line.polygon) - min(p[1] for p in line.polygon) for line in lines]
    line_height = max(1, median(heights))
    paragraphs = []
    buffer = ''
    previous = None
    for line in lines:
        text = line.text.replace('\x00', '').strip()
        if not text:
            continue
        top = min(p[1] for p in line.polygon)
        gap = 0 if previous is None else top - max(p[1] for p in previous.polygon)
        listing = bool(re.match(r'^(?:[-•*]|\d+[.)])\s', text))
        short_previous = previous is not None and len(previous.text.strip()) < 24
        if buffer and (gap > 1.5 * line_height or listing or short_previous):
            paragraphs.append(buffer)
            buffer = ''
        buffer = f'{buffer} {text}'.strip()
        previous = line
    if buffer:
        paragraphs.append(buffer)
    return '\n\n'.join(paragraphs)

"""Render actual pin widgets in every theme using public synthetic text."""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PySide6.QtCore import Qt, QPoint, QPointF, QRectF
from PySide6.QtGui import QPixmap, QPainter, QFont, QColor
from PySide6.QtWidgets import QApplication
from snaptrans import __version__
from snaptrans.ui.pinned_image import PinnedImage
from snaptrans.ui.theme import refresh_themes
from snaptrans.ui.themes import THEMES, palette
from snaptrans.ui.fonts import initialize_fonts


def sample(text):
    image = QPixmap(900, 180)
    image.fill(QColor('#ffffff'))
    painter = QPainter(image)
    painter.setPen(QColor('#202532'))
    font = QFont('Microsoft YaHei'); font.setPixelSize(22)
    painter.setFont(font)
    painter.drawText(QRectF(22, 20, 856, 125), Qt.TextFlag.TextWordWrap, text)
    painter.end()
    return image


def preview(pin, path):
    picture, toolbar = pin.grab(), pin.toolbar.grab()
    ratio = max(picture.devicePixelRatio(), toolbar.devicePixelRatio())
    picture_size, toolbar_size = picture.deviceIndependentSize(), toolbar.deviceIndependentSize()
    width = int(max(picture_size.width(), toolbar_size.width()) + 24)
    height = int(picture_size.height() + toolbar_size.height() + 36)
    output = QPixmap(round(width * ratio), round(height * ratio))
    output.setDevicePixelRatio(ratio); output.fill(QColor(palette()['bg']))
    painter = QPainter(output)
    painter.drawPixmap(QPointF((width - picture_size.width()) / 2, 12), picture)
    painter.drawPixmap(QPointF((width - toolbar_size.width()) / 2, picture_size.height() + 24), toolbar)
    painter.end(); output.save(str(path))


def main():
    app = QApplication([])
    initialize_fonts(app)
    output = ROOT / 'docs' / 'evidence' / f'v{__version__}'
    output.mkdir(parents=True, exist_ok=True)
    original = sample('A clear interface makes everyday tasks easier.\nCompare the original and translation right here, while keeping the image in the same place.')
    translated = sample('清晰的界面让日常操作更轻松。\n直接在贴图当前位置对照原文和译文，同时保留缩放、裁剪和标注。')
    for theme in THEMES:
        refresh_themes(theme)
        pin = PinnedImage(translated, QPoint(20, 30), original_pixmap=original, translated_pixmap=translated)
        pin.document.apply(('arrow', [QPointF(35, 140), QPointF(270, 140)], '#36bd68', 3, ''))
        pin.set_tool('ellipse'); pin.show(); app.processEvents()
        preview(pin, output / f'pin-{theme}-translated.png')
        pin.toggle_comparison(); app.processEvents()
        preview(pin, output / f'pin-{theme}-original.png')
        pin.close(); app.processEvents()
    print(f'Rendered 12 pin previews in {output.name}.')


if __name__ == '__main__':
    main()

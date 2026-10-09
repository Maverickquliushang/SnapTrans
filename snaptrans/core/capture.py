from PySide6.QtGui import QImage
from PySide6.QtCore import QRect
from .coordinates import pixel_crop
from .models import AppError, CaptureFrame


class CaptureScreen:
    """Value snapshot of the screen coordinates used by a frozen screenshot."""
    def __init__(self, screen):
        self._name = screen.name()
        self._geometry = screen.geometry().getRect()
        self._available = screen.availableGeometry().getRect()

    def name(self):
        return self._name

    def geometry(self):
        return QRect(*self._geometry)

    def availableGeometry(self):
        return QRect(*self._available)


def make_frame(request_id, screen, pixmap, rect):
    bounds = pixel_crop((rect.x(), rect.y(), rect.width(), rect.height()),
                        (screen.geometry().width(), screen.geometry().height()),
                        (pixmap.width(), pixmap.height()))
    left, top, right, bottom = bounds
    width, height = right - left, bottom - top
    if width <= 0 or height <= 0:
        raise AppError('EMPTY_SELECTION', '请选择有效文字区域。')
    if max(width, height) > 8192 or width * height > 20_000_000:
        raise AppError('IMAGE_LIMIT', '选区过大，请缩小到一个文字段落。')
    image = pixmap.toImage().copy(left, top, width, height).convertToFormat(QImage.Format.Format_RGB888)
    memory = bytes(image.constBits())
    stride = image.bytesPerLine()
    rgb = b''.join(memory[row * stride:row * stride + width * 3] for row in range(height))
    geometry = screen.geometry()
    return CaptureFrame(request_id, screen.name(),
                        (geometry.x(), geometry.y(), geometry.width(), geometry.height()),
                        (rect.x(), rect.y(), rect.width(), rect.height()), bounds, width, height, rgb)

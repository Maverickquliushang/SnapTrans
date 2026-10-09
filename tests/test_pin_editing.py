from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QPixmap, QColor, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from snaptrans.ui.pinned_image import PinnedImage


def pin_fixture(qt_app):
    pixmap = QPixmap(400, 220)
    pixmap.fill(QColor('white'))
    pin = PinnedImage(pixmap, QPoint(60, 60))
    pin.show()
    qt_app.processEvents()
    return pin


def drag(surface, start, end):
    QTest.mousePress(surface, Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(surface, end)
    QTest.mouseRelease(surface, Qt.MouseButton.LeftButton, pos=end)


def test_pin_draw_undo_redo_export_and_crop(qt_app):
    pin = pin_fixture(qt_app)
    original = pin.pixmap.toImage()
    pin.set_tool('arrow')
    drag(pin.image, QPoint(40, 50), QPoint(200, 120))
    marked = pin.pixmap.toImage()
    assert marked != original
    pin.copy_image()
    assert qt_app.clipboard().pixmap().toImage() == marked
    pin.undo()
    assert pin.pixmap.toImage() == original
    pin.redo()
    assert pin.pixmap.toImage() == marked
    pin.set_tool('crop')
    drag(pin.image, QPoint(20, 20), QPoint(160, 100))
    assert pin.pixmap.width() == 140 and pin.pixmap.height() == 80
    assert pin.tool_picker.currentData() == 'move'
    pin.undo()
    assert pin.pixmap.toImage() == marked
    pin.rotate()
    assert pin.pixmap.width() == 220 and pin.pixmap.height() == 400
    pin.undo()
    assert pin.pixmap.toImage() == marked
    pin.flip()
    pin.undo()
    assert pin.pixmap.toImage() == marked
    pin.close()


def test_pin_drag_zoom_opacity_reset(qt_app):
    pin = pin_fixture(qt_app)
    start_pos = pin.pos()
    drag(pin.image, QPoint(80, 60), QPoint(110, 80))
    assert pin.pos() != start_pos
    original = pin.pixmap.toImage()
    pin.set_zoom(1.5)
    assert pin.image.height() == 330
    assert pin.pixmap.toImage() == original
    local = QPointF(80, 60)
    event = QWheelEvent(local, QPointF(pin.image.mapToGlobal(local.toPoint())), QPoint(), QPoint(0, -120),
                        Qt.MouseButton.NoButton, Qt.KeyboardModifier.ControlModifier,
                        Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(pin.image, event)
    assert pin.windowOpacity() < 1
    pin.reset_view()
    assert pin.zoom == 1 and pin.windowOpacity() == 1
    assert pin.pixmap.toImage() == original
    pin.close()


def test_pin_dpi_mapping_and_branch_after_undo(qt_app):
    pixmap = QPixmap(800, 440)
    pixmap.fill(QColor('white'))
    pixmap.setDevicePixelRatio(2)
    pin = PinnedImage(pixmap, QPoint(60, 60))
    pin.set_tool('rect')
    drag(pin.image, QPoint(20, 20), QPoint(100, 80))
    assert pin.document.operations[0][1][0] == QPointF(40, 40)
    assert pin.pixmap.devicePixelRatio() == 2
    pin.undo()
    pin.set_tool('pen')
    drag(pin.image, QPoint(30, 30), QPoint(150, 70))
    assert len(pin.document.operations) == 1 and not pin.redo_button.isEnabled()
    pin.close()

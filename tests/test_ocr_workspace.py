from unittest.mock import Mock, patch
from PySide6.QtCore import Qt, QRectF, QEvent
from PySide6.QtGui import QPixmap, QColor
from PySide6.QtTest import QTest
from snaptrans.core.models import OcrResult, State
from snaptrans.core.controller import Controller
from snaptrans.config import DEFAULT
from copy import deepcopy
from test_pipeline import OcrDouble, NetworkDouble


def workspace(qt_app):
    config = deepcopy(DEFAULT)
    ocr, network = OcrDouble(), NetworkDouble()
    ocr.submit = Mock()
    controller = Controller(ocr, network, Mock(), lambda: config, Mock(), Mock())
    controller.screen = qt_app.primaryScreen()
    controller.pixmap = QPixmap(controller.screen.size())
    controller.pixmap.fill(QColor('#eeddcc'))
    controller.snapshot = config
    controller.ocr_only = True
    controller.selected(controller.gate.begin(State.SELECTING), QRectF(30, 40, 240, 60))
    qt_app.processEvents()
    return controller, ocr, network


def test_screenshot_waits_for_action_and_copies_clean_image(qt_app, tmp_path):
    controller, ocr, network = workspace(qt_app)
    canvas = controller.result.overlay
    assert canvas.isVisible()
    assert not controller.result.original.isVisible()
    assert not ocr.submit.called and not network.sent
    QTest.mouseClick(canvas.copy_image_button, Qt.MouseButton.LeftButton)
    image = qt_app.clipboard().pixmap().toImage()
    assert (image.width(), image.height()) == (240, 60)
    assert image.pixelColor(0, 0) == QColor('#eeddcc')
    assert image.pixelColor(239, 59) == QColor('#eeddcc')
    filename = tmp_path / 'saved.png'
    with patch('snaptrans.ui.ocr_canvas.QFileDialog.getSaveFileName', return_value=(str(filename), 'PNG')):
        canvas.save_image()
    assert QPixmap(str(filename)).toImage() == image
    controller.close()


def test_extract_edit_copy_and_transfer_without_reocr(qt_app):
    controller, ocr, network = workspace(qt_app)
    canvas = controller.result.overlay
    QTest.mouseClick(canvas.extract_button, Qt.MouseButton.LeftButton)
    assert ocr.submit.call_count == 1
    ocr.succeeded.emit(OcrResult(controller.gate.request_id, 'Hello world.', [], 1))
    assert not network.sent
    assert canvas.ocr_panel.isVisible()
    canvas.ocr_editor.setPlainText('Edited public text.')
    canvas.copy_text()
    assert qt_app.clipboard().text() == 'Edited public text.'
    QTest.mouseClick(canvas.translate_ocr_button, Qt.MouseButton.LeftButton)
    assert controller.result.original.isVisible()
    assert not canvas.isVisible()
    assert ocr.submit.call_count == 1
    assert network.sent[-1][0].text == 'Edited public text.'
    controller.close()


def test_translate_from_image_runs_ocr_then_opens_popup(qt_app):
    controller, ocr, network = workspace(qt_app)
    controller.extract_text(translate=True)
    assert not network.sent
    ocr.succeeded.emit(OcrResult(controller.gate.request_id, 'Hello.', [], 1))
    assert len(network.sent) == 1
    assert controller.result.original.isVisible()
    controller.close()


def test_resize_cancels_pending_translation_and_discards_old_ocr(qt_app):
    controller, ocr, network = workspace(qt_app)
    controller.extract_text(translate=True)
    old = controller.gate.request_id
    controller.reselect(QRectF(40, 40, 180, 50))
    ocr.succeeded.emit(OcrResult(old, 'stale', [], 1))
    assert not network.sent
    assert not controller.result.source_text()
    assert ocr.submit.call_count == 1
    assert controller.gate.state == State.COMPLETED
    controller.close()


def test_pin_retains_original_image_and_closes_workspace(qt_app):
    controller, ocr, network = workspace(qt_app)
    controller.pin_selection()
    assert not controller.result.isVisible()
    assert len(controller.pins) == 1
    pin = controller.pins[0]
    assert pin.isVisible() and pin.property('snaptrans_pin')
    assert pin.pixmap.toImage().pixelColor(0, 0) == QColor('#eeddcc')
    pin.zoom = 1.5
    pin._resize_image()
    assert pin.image.height() == 90
    controller.close()
    qt_app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert not controller.pins


def test_frozen_capture_survives_expired_live_screen_wrapper(qt_app):
    controller, ocr, network = workspace(qt_app)
    controller.screen = Mock()
    controller.screen.geometry.side_effect = RuntimeError('QScreen wrapper expired')
    controller.extract_text()
    assert ocr.submit.call_count == 1
    assert ocr.submit.call_args.args[0].width_px == 240
    controller.reselect(QRectF(20, 30, 200, 50))
    assert controller.gate.state == State.COMPLETED
    assert not network.sent
    controller.close()

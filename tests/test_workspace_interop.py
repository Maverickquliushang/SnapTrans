from PySide6.QtCore import Qt, QEvent, QRectF
from PySide6.QtTest import QTest
from PySide6.QtGui import QColor, QPixmap, QGuiApplication
from snaptrans.core.models import OcrResult, TranslationResult, State
from test_ocr_workspace import workspace


def complete_translation(controller, ocr, network):
    controller.switch_workspace('translate')
    ocr.succeeded.emit(OcrResult(controller.gate.request_id, 'Hello world.', [], 1))
    network.succeeded.emit(TranslationResult(controller.gate.request_id, '你好，世界。', 1))


def next_capture(controller, selection=QRectF(30, 40, 240, 60)):
    controller.result.deleteLater()
    controller.result = None
    controller.screen = QGuiApplication.primaryScreen()
    controller.pixmap = QPixmap(controller.screen.size())
    controller.pixmap.fill(QColor('#eeddcc'))
    controller.ocr_only = True
    controller.selected(controller.gate.begin(State.SELECTING), selection)


def test_toolbar_cursor_and_ocr_editor_do_not_inherit_crosshair(qt_app):
    controller, ocr, network = workspace(qt_app)
    canvas = controller.result.overlay
    canvas.setCursor(Qt.CursorShape.CrossCursor)
    assert canvas.toolbar.cursor().shape() == Qt.CursorShape.ArrowCursor
    assert canvas.extract_button.cursor().shape() == Qt.CursorShape.PointingHandCursor
    assert canvas.ocr_panel.cursor().shape() == Qt.CursorShape.ArrowCursor
    assert canvas.ocr_editor.viewport().cursor().shape() == Qt.CursorShape.IBeamCursor
    controller.switch_workspace('translate')
    canvas = controller.result.overlay
    canvas.setCursor(Qt.CursorShape.CrossCursor)
    assert canvas.toolbar.cursor().shape() == Qt.CursorShape.ArrowCursor
    assert canvas.pin_button.cursor().shape() == Qt.CursorShape.PointingHandCursor
    assert canvas.engine.cursor().shape() == Qt.CursorShape.ArrowCursor
    controller.close()


def test_modes_reuse_text_and_translation_until_edited(qt_app):
    controller, ocr, network = workspace(qt_app)
    controller.extract_text()
    ocr.succeeded.emit(OcrResult(controller.gate.request_id, 'Hello.', [], 1))
    controller.result.overlay.ocr_editor.setPlainText('Edited original.')
    QTest.mouseClick(controller.result.overlay.workspace_translate_button, Qt.MouseButton.LeftButton)
    assert not controller.result.ocr_mode and controller.result.overlay.isVisible()
    assert ocr.submit.call_count == 1
    assert network.sent[-1][0].text == 'Edited original.'
    network.succeeded.emit(TranslationResult(controller.gate.request_id, '编辑后的原文。', 1))
    controller.switch_workspace('ocr')
    assert controller.result.overlay.ocr_editor.toPlainText() == 'Edited original.'
    controller.switch_workspace('translate')
    assert controller.result.overlay.translation == '编辑后的原文。'
    assert len(network.sent) == 1 and ocr.submit.call_count == 1
    controller.switch_workspace('ocr')
    controller.result.overlay.ocr_editor.setPlainText('A second edit.')
    controller.switch_workspace('translate')
    assert network.sent[-1][0].text == 'A second edit.' and len(network.sent) == 2
    controller.close()


def test_translated_pin_reopens_original_capture_and_preserves_edits(qt_app):
    controller, ocr, network = workspace(qt_app)
    complete_translation(controller, ocr, network)
    original_pixels = controller.result.overlay.selected_pixmap().toImage()
    QTest.mouseClick(controller.result.overlay.pin_button, Qt.MouseButton.LeftButton)
    pin = controller.pins[0]
    assert pin.pixmap.toImage() != original_pixels
    assert pin.state['source'] == 'Hello world.'
    assert pin.state['translation'] == '你好，世界。'
    assert pin.pixmap.toImage().pixelColor(0, 0) == QColor('#eeddcc')  # no handles
    QTest.mouseClick(pin.ocr_button, Qt.MouseButton.LeftButton)
    assert not pin.isVisible()
    assert controller.result.ocr_mode and controller.result.overlay.isVisible()
    assert controller.result.overlay.selected_pixmap().toImage() == original_pixels
    assert controller.result.source_text() == 'Hello world.'
    assert controller.result.translated.toPlainText() == '你好，世界。'
    assert ocr.submit.call_count == 1 and len(network.sent) == 1
    assert not pin.isVisible() and not controller.pins
    controller.switch_workspace('translate')
    assert not controller.result.ocr_mode and controller.result.overlay.translation == '你好，世界。'
    assert len(network.sent) == 1
    controller.result.close()
    assert not pin.isVisible()
    controller.close()
    qt_app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert not controller.pins


def test_pin_without_text_uses_retained_original_and_ignores_previous_request(qt_app):
    controller, ocr, network = workspace(qt_app)
    controller.pin_selection()
    pin = controller.pins[0]
    controller.restore_pin(pin, 'translate')
    first_id = controller.gate.request_id
    assert ocr.submit.call_count == 1
    controller.switch_workspace('ocr')
    ocr.succeeded.emit(OcrResult(first_id, 'stale OCR', [], 1))
    assert not controller.result.source_text() and not network.sent
    controller.extract_text()
    assert ocr.submit.call_count == 2
    assert ocr.submit.call_args.args[0].width_px == 240
    ocr.succeeded.emit(OcrResult(controller.gate.request_id, 'Retained original.', [], 1))
    controller.switch_workspace('translate')
    stale_translation = controller.gate.request_id
    controller.switch_workspace('ocr')
    network.succeeded.emit(TranslationResult(stale_translation, 'stale translation', 1))
    assert not controller.result.translated.toPlainText()
    controller.close()


def test_pins_keep_independent_sessions(qt_app):
    controller, ocr, network = workspace(qt_app)
    controller.result.set_original('first', 'first edit')
    controller.pin_selection()
    first = controller.pins[0]
    next_capture(controller, QRectF(100, 150, 320, 100))
    controller.result.set_original('second', 'second edit')
    controller.pin_selection()
    second = controller.pins[1]
    controller.restore_pin(first)
    assert first not in controller.pins and second.isVisible()
    assert controller.result.source_text() == 'first edit'
    assert controller.result.overlay.selection.width() == 240
    controller.restore_pin(second)
    assert not controller.pins
    assert controller.result.source_text() == 'second edit'
    assert controller.result.overlay.selection.width() == 320
    controller.close()


def test_translated_pin_dpi_and_compare(qt_app):
    controller, ocr, network = workspace(qt_app)
    complete_translation(controller, ocr, network)
    canvas = controller.result.overlay
    scaled = QPixmap(canvas.screenshot.size() * 2)
    scaled.fill(QColor('#eeddcc'))
    scaled.setDevicePixelRatio(2)
    canvas.screenshot = scaled
    rendered = canvas.rendered_selection()
    assert rendered.width() == 480 and rendered.height() == 120
    assert rendered.devicePixelRatio() == 2
    assert rendered.toImage() != canvas.selected_pixmap().toImage()
    canvas.compare.setChecked(True)
    assert canvas.rendered_selection().toImage() == canvas.selected_pixmap().toImage()
    controller.close()

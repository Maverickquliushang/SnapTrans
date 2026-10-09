from unittest.mock import Mock
from PySide6.QtCore import QPoint, QRectF, Qt
from PySide6.QtGui import QPixmap, QColor
from PySide6.QtTest import QTest
from snaptrans.ui.translation_canvas import TranslationCanvas, handles
from snaptrans.core.models import TranslationResult, State
from test_pipeline import setup_controller


def canvas_fixture(qt_app, color='white', selection=None):
    canvas = TranslationCanvas()
    screen = qt_app.primaryScreen()
    screenshot = QPixmap(screen.size())
    screenshot.fill(QColor(color))
    canvas.attach_capture(screen, screenshot, selection or QRectF(200, 200, 200, 48))
    canvas.show()
    qt_app.processEvents()
    return canvas


def test_contrast_fits_text_and_compare_restores_pixels(qt_app):
    canvas = canvas_fixture(qt_app)
    canvas.set_content('不匹配平均值')
    canvas.grab()
    assert not canvas.text_overflow
    assert canvas.rendered_font_px >= 12
    canvas.compare.setChecked(True)
    sample = canvas.grab(canvas.selection.toRect()).toImage()
    assert sample.pixelColor(sample.width() // 2, sample.height() // 2) == QColor('white')
    assert not canvas.selection.intersects(QRectF(canvas.toolbar.geometry()))
    assert len(handles(canvas.selection)) == 8
    canvas.close()


def test_dark_background_and_bottom_toolbar_clamp(qt_app):
    screen = qt_app.primaryScreen()
    rect = QRectF(screen.size().width() - 220, screen.size().height() - 75, 200, 48)
    canvas = canvas_fixture(qt_app, '#20242a', rect)
    canvas.set_content('深色背景译文')
    canvas.grab()
    assert canvas.background == QColor('#20242a')
    assert canvas.foreground.lightness() > 220
    assert canvas.rect().contains(canvas.toolbar.geometry())
    assert not rect.intersects(QRectF(canvas.toolbar.geometry()))
    canvas.close()


def test_long_translation_marks_overflow_and_preserves_full_text(qt_app):
    canvas = canvas_fixture(qt_app, selection=QRectF(100, 100, 100, 30))
    text = '这是一段无法在小选区中完整放下的译文。' * 15
    canvas.set_content(text)
    canvas.grab()
    assert canvas.text_overflow
    assert canvas.rendered_font_px == 9
    assert canvas.translation == text
    assert '完整译文' in canvas.popup_button.toolTip()
    canvas.set_content('中文')
    canvas.grab()
    assert not canvas.text_overflow
    assert canvas.popup_button.toolTip() == '切换到弹窗'
    canvas.close()


def test_reocr_record_does_not_replace_editable_original(qt_app):
    from snaptrans.ui.result_window import ResultWindow
    from snaptrans.config import DEFAULT
    window = ResultWindow(DEFAULT['window'])
    window.set_original('old raw', 'old cleaned')
    window.show_ocr_record()
    window.set_original('new raw', 'new cleaned')
    assert window.raw_text == 'new raw'
    window.ocr_record_dialog.close()
    assert window.source_text() == 'new cleaned'
    window.close()


def test_resize_emits_one_reocr_after_release(qt_app):
    canvas = canvas_fixture(qt_app)
    before = QRectF(canvas.selection)
    starts, changed = [], []
    canvas.adjustment_started.connect(lambda: starts.append(True))
    canvas.selection_changed.connect(changed.append)
    corner = before.bottomRight().toPoint()
    QTest.mousePress(canvas, Qt.MouseButton.LeftButton, pos=corner)
    QTest.mouseMove(canvas, corner + QPoint(60, 20))
    assert not changed
    QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=corner + QPoint(60, 20))
    assert len(starts) == len(changed) == 1
    assert changed[0].size().width() == before.width() + 60
    assert changed[0].size().height() == before.height() + 20
    assert not canvas.translation
    canvas.close()


def test_move_clamps_region_and_click_does_not_reocr(qt_app):
    canvas = canvas_fixture(qt_app)
    changed = []
    canvas.selection_changed.connect(changed.append)
    center = canvas.selection.center().toPoint()
    QTest.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=center)
    assert not changed
    QTest.mousePress(canvas, Qt.MouseButton.LeftButton, pos=center)
    # QTest treats a null QPoint as "widget center" rather than the origin.
    QTest.mouseMove(canvas, QPoint(1, 1))
    QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=QPoint(1, 1))
    assert canvas.selection.topLeft() == QPoint(0, 0)
    assert len(changed) == 1
    canvas.close()


def test_reselect_uses_retained_screen_and_discards_old_results(qt_app):
    controller, config, ocr, network = setup_controller(qt_app, configured=True)
    screen = qt_app.primaryScreen()
    screenshot = QPixmap(screen.size())
    screenshot.fill(Qt.GlobalColor.white)
    controller.screen = screen
    controller.result.attach_capture(screen, screenshot, QRectF(20, 20, 200, 50))
    ocr.submit = Mock()
    old_id = controller.gate.begin(State.TRANSLATING)
    controller.adjust_selection()
    network.succeeded.emit(TranslationResult(old_id, 'stale', 1))
    assert not controller.result.translated.toPlainText()
    controller.reselect(QRectF(30, 40, 230, 60))
    frame = ocr.submit.call_args[0][0]
    assert frame.request_id != old_id
    assert (frame.width_px, frame.height_px) == (230, 60)
    assert frame.rgb_bytes == bytes([255]) * (230 * 60 * 3)
    assert controller.gate.state == State.RECOGNIZING
    controller.close()

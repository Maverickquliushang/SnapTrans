from copy import deepcopy
from unittest.mock import Mock
import time
import pytest
from PySide6.QtCore import Qt, QPoint, QPointF, QEvent, QObject, Signal
from PySide6.QtGui import QPixmap, QColor, QImage
from PySide6.QtTest import QTest
from snaptrans.config import DEFAULT
from snaptrans.core.models import OcrResult, TranslationResult
from snaptrans.ui.settings_window import SettingsWindow
from snaptrans.ui.result_window import ResultWindow
from snaptrans.ui.pinned_image import PinnedImage
from test_ocr_workspace import workspace
from test_workspace_interop import next_capture


class PinOcr(QObject):
    succeeded = Signal(object)
    failed = Signal(str, str, str)
    def __init__(self):
        super().__init__()
        self.submit, self.cancel, self.close = Mock(), Mock(), Mock()


def original_pin(app):
    controller, workspace_ocr, network = workspace(app)
    controller.pin_selection()
    ocr = PinOcr()
    controller.pin_tasks.ocr_factory = lambda: ocr
    pin = controller.pins[0]
    return controller, pin, ocr, workspace_ocr, network


def test_pin_translates_in_place_and_keeps_edits_and_original(qt_app):
    controller, pin, ocr, workspace_ocr, network = original_pin(qt_app)
    pin.move(70, 160); pin.set_zoom(1.3)
    original = pin.original_pixmap.toImage()
    pin.document.apply(('pen', [QPointF(4, 10), QPointF(80, 10)], '#ff0000', 3, ''))
    position, zoom, index = pin.pos(), pin.zoom, pin.document.index
    pin.translate_button.click()
    assert pin.busy and pin.isVisible() and not controller.result.isVisible()
    frame = ocr.submit.call_args.args[0]
    assert frame.width_px == 240 and frame.height_px == 60 and not workspace_ocr.submit.called
    ocr.succeeded.emit(OcrResult(frame.request_id, 'Hello world.', [], 1))
    request = network.sent[-1][0]
    assert request.text == 'Hello world.'
    network.succeeded.emit(TranslationResult(request.request_id, '你好，世界。', 1))
    assert not pin.busy and pin.can_compare and not pin.showing_original
    assert (pin.pos(), pin.zoom, pin.document.index) == (position, zoom, index)
    assert pin.state['source'] == 'Hello world.' and pin.state['translation'] == '你好，世界。'
    assert pin.original_pixmap.toImage() == original
    assert not controller.result.overlay.isVisible()
    pin.toggle_comparison()
    assert pin.document.current.toImage().pixelColor(40, 10) == QColor('#ff0000')
    pin.undo()
    assert pin.pixmap.toImage() == original
    pin.workspace_button.click()
    assert controller.result.translated.toPlainText() == '你好，世界。'
    assert pin not in controller.pins
    controller.close()


@pytest.mark.parametrize('action', ['cancel', 'close', 'workspace', 'timeout'])
def test_pin_job_cancel_late_results_do_not_reopen_or_overwrite(qt_app, action):
    controller, pin, ocr, _, network = original_pin(qt_app)
    pin.translate_button.click()
    request_id = next(iter(controller.pin_tasks.jobs))
    if action == 'cancel':
        pin.cancel_button.click()
    elif action == 'close':
        pin.close()
    elif action == 'workspace':
        pin.workspace_button.click()
    else:
        controller.pin_tasks.jobs[request_id]['started'] = time.monotonic() - 1000
        controller.pin_tasks.tick()
    assert not controller.pin_tasks.jobs and not pin.busy
    assert ocr.cancel.called and ocr.close.called
    ocr.succeeded.emit(OcrResult(request_id, 'late original', [], 1))
    network.succeeded.emit(TranslationResult(request_id, 'late translation', 1))
    assert pin.state['translation'] == '' and not network.sent
    controller.close()


def test_multiple_pins_queue_ocr_and_do_not_cancel_workspace(qt_app):
    controller, first, ocr, workspace_ocr, network = original_pin(qt_app)
    first.translate_button.click()
    first_id = ocr.submit.call_args.args[0].request_id
    next_capture(controller)
    controller.pin_selection()
    second = controller.pins[1]
    second.translate_button.click()
    assert ocr.submit.call_count == 1
    controller.cancel()  # Workspace lifecycle is separate.
    assert len(controller.pin_tasks.jobs) == 2
    ocr.succeeded.emit(OcrResult(first_id, 'First original.', [], 1))
    second_id = ocr.submit.call_args.args[0].request_id
    assert second_id != first_id
    ocr.succeeded.emit(OcrResult(second_id, 'Second original.', [], 1))
    network.succeeded.emit(TranslationResult(second_id, '第二张。', 1))
    network.succeeded.emit(TranslationResult(first_id, '第一张。', 1))
    assert first.state['translation'] == '第一张。' and second.state['translation'] == '第二张。'
    assert first.isVisible() and second.isVisible()
    controller.close()


def test_pin_retry_uses_recognized_text_and_selected_provider(qt_app):
    controller, pin, ocr, _, network = original_pin(qt_app)
    pin.state['source'] = 'Retained source.'
    pin.engine.setCurrentIndex(pin.engine.findData('google_web'))
    pin.translate_button.click()
    request = network.sent[-1][0]
    assert request.settings_snapshot.provider == 'google_web' and not ocr.submit.called
    network.failed.emit(request.request_id, 'OFFLINE', '网络失败')
    assert '网络失败' in pin.status.text() and not pin.busy
    pin.translate_button.click()
    current = network.sent[-1][0].request_id
    network.succeeded.emit(TranslationResult(request.request_id, '过期。', 1))
    assert pin.busy and not pin.can_compare
    network.succeeded.emit(TranslationResult(current, '重试成功。', 1))
    assert pin.can_compare and pin.state['provider'] == 'google_web'
    controller.close()


def test_pin_translation_arriving_during_drawing_keeps_stroke(qt_app):
    controller, pin, _, _, network = original_pin(qt_app)
    pin.state['source'] = 'Hello'
    pin.translate_button.click()
    pin.set_tool('pen')
    QTest.mousePress(pin.image, Qt.MouseButton.LeftButton, pos=QPoint(12, 14))
    QTest.mouseMove(pin.image, QPoint(90, 14))
    network.succeeded.emit(TranslationResult(network.sent[-1][0].request_id, '你好', 1))
    assert pin.image.points
    QTest.mouseRelease(pin.image, Qt.MouseButton.LeftButton, pos=QPoint(90, 14))
    assert pin.document.index == 1 and not pin.image.points
    controller.close()


def test_pin_cloud_ocr_uses_original_capture_and_checks_credential(qt_app):
    controller, pin, local, _, network = original_pin(qt_app)
    config = deepcopy(DEFAULT)
    config['ocr']['provider'] = 'nvidia_vl'
    controller.pin_tasks.config_getter = lambda: config
    controller.credentials.get.return_value = ''
    network.submit_ocr = Mock()
    pin.translate_button.click()
    assert not pin.busy and 'OCR 密钥' in pin.status.text()
    assert not network.submit_ocr.called and not local.submit.called
    controller.credentials.get.return_value = 'synthetic-test-credential'
    pin.translate_button.click()
    frame, settings, secret = network.submit_ocr.call_args.args
    assert frame.width_px == 240 and settings['provider'] == 'nvidia_vl'
    assert secret == 'synthetic-test-credential' and not local.submit.called
    controller.pin_tasks.recognized(OcrResult(frame.request_id, 'Cloud original', [], 1))
    assert network.sent[-1][0].text == 'Cloud original'
    controller.close()


def test_pixel_display_does_not_resample_export_or_force_shrink(qt_app):
    image = QImage(306, 90, QImage.Format.Format_RGB32)
    for x in range(image.width()):
        for y in range(image.height()):
            image.setPixelColor(x, y, QColor('#ffffff' if (x + y) % 2 else '#000000'))
    source = QPixmap.fromImage(image); source.setDevicePixelRatio(1.5)
    pin = PinnedImage(source, QPoint(30, 30))
    pin.show(); pin.actual_pixels(); qt_app.processEvents()
    area = pin.image.image_rect()
    assert abs(area.width() * pin.devicePixelRatioF() - 306) < .01
    displayed = pin.image.grab().toImage().convertToFormat(QImage.Format.Format_RGB32)
    assert displayed.copy(2, 2, 260, 40) == image.copy(2, 2, 260, 40)
    before = pin.pixmap.toImage()
    pin.set_zoom(5)
    assert pin.zoom == 5
    assert pin.image.image_rect().width() > pin.image.width()
    pin.copy_image()
    assert qt_app.clipboard().pixmap().toImage() == before
    pin.fit_screen()
    assert pin.pixmap.toImage() == before and pin.pixmap.size() == source.size()
    pin.close()


def test_contextual_settings_save_state_and_responsive_navigation(qt_app):
    window = SettingsWindow(deepcopy(DEFAULT))
    window.resize(860, 700); window.show(); qt_app.processEvents()
    assert window.sidebar.isVisible() and not window.tabs.tabBar().isVisible()
    assert not window.test_button.isVisible()
    window.navigation.setCurrentRow(1); qt_app.processEvents()
    assert window.tabs.currentIndex() == 1 and window.test_button.isVisible()
    window.timeout.setValue(50)
    assert window.saved_state.text() == '未保存'
    saved = []
    window.save_requested.connect(lambda config, secret: (saved.append(config), window.saved(config)))
    window.save_button.click()
    assert saved and window.isVisible() and window.saved_state.text() == '已保存 ✓'
    window.tabs.setCurrentIndex(0)
    window.auto_translate.click()
    assert window._dirty and window.auto_translate.accessibleName()
    window.resize(540, 460); qt_app.processEvents()
    assert window.sidebar.isHidden() and window.tabs.tabBar().isVisible()
    assert window.rect().contains(window.save_button.mapTo(window, window.save_button.rect().bottomRight()))
    window.tabs.setCurrentIndex(4)
    assert not window.save_button.isVisible()  # Prompt has its own confirmation flow.
    window.close()


def test_reading_actions_stay_beside_text_on_small_window(qt_app):
    window = ResultWindow({**DEFAULT['window'], 'display_mode': 'popup'})
    window.set_original('Hello', 'Hello'); window.set_busy(False)
    window.resize(520, 420); window.show(); qt_app.processEvents()
    assert window.reading_split.count() == 2
    for button in (window.copy_source, window.copy_target, window.retry_button, window.close_button):
        assert window.rect().contains(button.mapTo(window, button.rect().center()))
    window.copy_source.click()
    assert qt_app.clipboard().text() == 'Hello' and '复制' in window.status.text()
    window.set_busy(True)
    assert window.progress.isVisible() and not window.retry_button.isEnabled()
    window.close()

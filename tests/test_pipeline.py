from copy import deepcopy
from unittest.mock import Mock
from PySide6.QtCore import QObject, Signal
from snaptrans.config import DEFAULT
from snaptrans.core.controller import Controller
from snaptrans.core.models import OcrResult, State, TranslationResult
from snaptrans.ui.result_window import ResultWindow
from snaptrans.providers.catalog import default_profile


class OcrDouble(QObject):
    succeeded = Signal(object)
    failed = Signal(str, str, str)
    def cancel(self):
        self.cancelled = True


class NetworkDouble(QObject):
    succeeded = Signal(object)
    failed = Signal(str, str, str)
    def __init__(self):
        super().__init__()
        self.sent = []
        self.cancelled = []
    def submit(self, request, secret):
        self.sent.append((request, secret))
    def cancel(self, request_id):
        self.cancelled.append(request_id)


def setup_controller(qt_app, configured=False):
    config = deepcopy(DEFAULT)
    config['translation'] = default_profile('compatible')
    if configured:
        config['translation'].update(base_url='https://example.com/v1', model='model-a')
    ocr, network = OcrDouble(), NetworkDouble()
    credentials = Mock()
    credentials.get.return_value = 'test-only'
    controller = Controller(ocr, network, credentials, lambda: config, Mock(), Mock())
    controller.snapshot = deepcopy(config)
    controller.result = ResultWindow(config['window'], config)
    controller.result.show()
    return controller, config, ocr, network


def test_unconfigured_keeps_original(qt_app):
    controller, config, ocr, network = setup_controller(qt_app)
    request_id = controller.gate.begin(State.RECOGNIZING)
    ocr.succeeded.emit(OcrResult(request_id, 'Actual recognized text', [], 1))
    assert controller.result.original.toPlainText() == 'Actual recognized text'
    assert controller.gate.state == State.COMPLETED
    assert not network.sent
    controller.close()


def test_snapshot_and_stale_response(qt_app):
    controller, config, ocr, network = setup_controller(qt_app, configured=True)
    request_id = controller.gate.begin(State.RECOGNIZING)
    config['translation']['model'] = 'model-b'
    ocr.succeeded.emit(OcrResult(request_id, 'Public text', [], 1))
    assert network.sent[0][0].settings_snapshot.model == 'model-a'
    controller.cancel()
    network.succeeded.emit(TranslationResult(request_id, 'Late result', 1))
    assert controller.result.translated.toPlainText() == ''
    assert network.cancelled == [request_id]
    controller.close()


def test_ocr_only_never_translates(qt_app):
    controller, config, ocr, network = setup_controller(qt_app, configured=True)
    controller.ocr_only = True
    request_id = controller.gate.begin(State.RECOGNIZING)
    ocr.succeeded.emit(OcrResult(request_id, 'Public text', [], 1))
    assert not network.sent
    controller.close()


def test_switch_during_translation_cancels_old_and_keeps_original(qt_app):
    controller, config, ocr, network = setup_controller(qt_app, configured=True)
    controller.result.provider_changed.connect(controller.switch_provider)
    old_id = controller.gate.begin(State.RECOGNIZING)
    ocr.succeeded.emit(OcrResult(old_id, 'Public text', [], 1))
    controller.result.engine.setCurrentIndex(controller.result.engine.findData('mymemory'))
    assert old_id in network.cancelled
    request, secret = network.sent[-1]
    assert request.settings_snapshot.provider == 'mymemory'
    assert request.text == 'Public text'
    assert not secret
    network.succeeded.emit(TranslationResult(old_id, 'stale text', 1))
    assert controller.result.translated.toPlainText() == ''
    network.succeeded.emit(TranslationResult(request.request_id, '新译文', 1))
    assert controller.result.translated.toPlainText() == '新译文'
    controller.close()


def test_switch_uses_saved_engine_profile_and_edited_text(qt_app):
    controller, config, ocr, network = setup_controller(qt_app, configured=True)
    ollama = default_profile('ollama')
    ollama['model'] = 'saved-model'
    config['profiles']['ollama'] = ollama
    controller.result.provider_changed.connect(controller.switch_provider)
    controller.result.set_original('raw', 'Edited sentence')
    controller.gate.state = State.COMPLETED
    controller.result.engine.setCurrentIndex(controller.result.engine.findData('ollama'))
    request, secret = network.sent[-1]
    assert request.text == 'Edited sentence'
    assert request.settings_snapshot.model == 'saved-model'
    assert not secret
    assert config['translation']['provider'] == 'compatible'
    controller.close()

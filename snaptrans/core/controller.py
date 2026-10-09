from ..i18n import ui_format
from ..i18n import tr
from copy import deepcopy
import logging
import time
from uuid import uuid4
from PySide6.QtCore import QObject, QTimer, QRectF, Signal
from PySide6.QtGui import QCursor, QGuiApplication
from PySide6.QtWidgets import QApplication

from .models import AppError, State, ProviderSettings, TranslationRequest
from .capture import make_frame, CaptureScreen
from .text_cleanup import clean_text
from ..ui.selector import Selector
from ..ui.result_window import ResultWindow
from ..ui.pinned_image import PinnedImage
from ..providers.catalog import is_configured, profile_for


class TaskGate:
    """Only the current request can affect UI state."""
    def __init__(self):
        self.request_id = ''
        self.state = State.IDLE

    @property
    def busy(self):
        return self.state in (State.SELECTING, State.RECOGNIZING, State.TRANSLATING)

    def begin(self, state):
        self.request_id = uuid4().hex
        self.state = state
        return self.request_id

    def invalidate(self):
        self.request_id = ''
        self.state = State.IDLE

    def accepts(self, request_id):
        return bool(request_id) and request_id == self.request_id


class Controller(QObject):
    languages_changed = Signal(str, str)
    def __init__(self, ocr, network, credentials, config_getter, tray, settings_callback):
        super().__init__()
        self.ocr = ocr
        self.network = network
        self.credentials = credentials
        self.config_getter = config_getter
        self.tray = tray
        self.settings_callback = settings_callback
        self.gate = TaskGate()
        self.result = None
        self.selector = None
        self.snapshot = None
        self.secret = ''
        self.ocr_only = False
        self.closing = False
        self.frame = None
        self.capture_screen = None
        self.pins = []
        from .pin_tasks import PinTasks
        self.pin_tasks = PinTasks(network, credentials, config_getter, self)
        self.pending_ocr_translation = False
        self.request_started = 0
        self.request_phase = ''
        self.request_limit = 0
        self.progress_timer = QTimer(self)
        self.progress_timer.setInterval(500)
        self.progress_timer.timeout.connect(self.progress_tick)
        if hasattr(network, 'progress'):
            network.progress.connect(self.network_progress)
        self.log = logging.getLogger('snaptrans')
        ocr.succeeded.connect(self.ocr_done)
        ocr.failed.connect(self.failed)
        network.succeeded.connect(self.translation_done)
        network.failed.connect(self.failed)
        if hasattr(network, 'ocr_succeeded'):
            network.ocr_succeeded.connect(self.ocr_done)

    def capture(self, mode='translate'):
        if self.closing:
            return
        if self.gate.busy:
            self.tray.notify(tr('任务进行中，可关闭结果窗口取消。'))
            return
        self.cancel()
        if self.result:
            old, self.result = self.result, None
            old.close()
            old.deleteLater()
        request_id = self.gate.begin(State.SELECTING)
        self.snapshot = deepcopy(self.config_getter())
        self.ocr_only = mode == 'ocr' or not self.snapshot.get('capture', {}).get('auto_translate', True)
        self.secret = ''
        if not self.ocr_only:
            try:
                self.secret = self.credentials.get(self.snapshot['translation']['base_url'])
            except AppError:
                self.tray.notify(tr('已保存密钥无法读取，OCR 仍可用，请重新填写密钥。'))
        self.screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        # Hide our other windows before the next desktop capture.
        for window in QApplication.topLevelWidgets():
            if window.isVisible() and not window.property('snaptrans_pin'):
                window.hide()
        QTimer.singleShot(80, lambda: self._show_selector(request_id))

    def _show_selector(self, request_id):
        if not self.gate.accepts(request_id) or self.closing:
            return
        try:
            if self.screen not in QGuiApplication.screens():
                raise AppError('SCREEN_REMOVED', tr('显示器已移除，请重试。'))
            self.pixmap = self.screen.grabWindow(0)
            if self.pixmap.isNull():
                raise AppError('CAPTURE', tr('无法截取此屏幕，请重试。'))
            self.selector = Selector(self.screen, self.pixmap)
            self.selector.selected.connect(lambda rect: self.selected(request_id, rect))
            self.selector.cancelled.connect(self.cancel)
            self.selector.show()
            self.selector.activateWindow()
        except (AppError, RuntimeError) as error:
            self.failed(request_id, 'CAPTURE', str(error))

    def selected(self, request_id, rect):
        if not self.gate.accepts(request_id):
            return
        try:
            self.capture_screen = screen = CaptureScreen(self.screen)
            frame = None if self.ocr_only else make_frame(request_id, screen, self.pixmap, rect)
            selector, self.selector = self.selector, None
            if selector:
                selector.hide()
                selector.deleteLater()
            window_settings = deepcopy(self.snapshot['window'])
            if self.ocr_only:
                window_settings['display_mode'] = 'overlay'
            self.result = ResultWindow(window_settings, self.snapshot, ocr_mode=self.ocr_only)
            self._connect_result()
            geometry = screen.geometry()
            global_rect = QRectF(rect).translated(geometry.x(), geometry.y())
            self.result.attach_capture(screen, self.pixmap, rect)
            self.result.place_near(global_rect, screen)
            self.result.show()
            self.result.activateWindow()
            self.frame = frame
            if self.ocr_only:
                self.gate.state = State.COMPLETED
                self.result.set_busy(False)
                self.result.status.setText(tr('可调整选区，然后复制图片、贴图、提取文字或打开弹窗翻译'))
            else:
                self.gate.state = State.RECOGNIZING
                self._submit_ocr(frame)
        except (AppError, RuntimeError) as error:
            self.failed(request_id, 'OCR_SUBMIT', str(error))
        finally:
            self.pixmap = None

    def ocr_done(self, result):
        if self.closing or not self.gate.accepts(result.request_id) or not self.result:
            return
        text = clean_text(result)
        self.result.set_original(result.raw_text, text)
        if self.frame is not None:
            self.result.set_ocr_geometry(result, self.frame)
        self.log.info('request=%s stage=ocr elapsed_ms=%.1f', result.request_id, result.elapsed_ms)
        if not text:
            self.failed(result.request_id, 'NO_TEXT', tr('未识别到文字，请缩小到清晰文本区域重试。'))
        elif self.pending_ocr_translation:
            self.pending_ocr_translation = False
            self.result.show_translation_popup()
            self._translate(text)
        elif self.ocr_only:
            self.gate.state = State.COMPLETED
            self.result.set_busy(False)
            self.result.status.setText(tr('识别完成（本地 OCR，未联网）') if self.snapshot.get('ocr', {}).get('provider', 'local') == 'local'
                                       else tr('识别完成（云端服务）'))
            self.secret = ''
        else:
            self._translate(text)

    def extract_text(self, translate=False):
        if self.closing or self.gate.busy or not self.result:
            return
        self.ocr_only = True
        if not translate:
            self.result.set_workspace_mode('ocr')
        if translate and self.result.source_text().strip():
            self.result.show_translation_popup()
            self.retry(self.result.source_text())
            return
        self.snapshot = deepcopy(self.config_getter())
        self.snapshot['translation'] = profile_for(self.snapshot, self.result.engine.currentData())
        request_id = self.gate.begin(State.RECOGNIZING)
        self.pending_ocr_translation = translate
        try:
            canvas = self.result.overlay
            self.frame = make_frame(request_id, self.capture_screen, canvas.screenshot, canvas.selection)
            values = self.snapshot['translation']
            self.secret = self.credentials.get(values['base_url']) if translate and values['requires_api_key'] else ''
            self.result.set_original('', '')
            self.result.set_busy(True)
            self.result.status.setText(tr('正在识别…'))
            self._submit_ocr(self.frame)
        except (AppError, RuntimeError) as error:
            self.failed(request_id, 'OCR_SUBMIT', str(error))

    def pin_selection(self):
        if self.gate.busy or not self.result or not self.result.overlay.has_capture:
            return
        canvas = self.result.overlay
        pixmap = canvas.unannotated_selection()
        if pixmap is None or pixmap.isNull():
            return
        position = canvas.mapToGlobal(canvas.selection.topLeft().toPoint())
        translated = canvas.unannotated_selection(force_translation=True) if canvas.translation else None
        pin = PinnedImage(pixmap, position, self.result.capture_state(), canvas.editor.snapshot(),
                          original_pixmap=canvas.selected_pixmap(), translated_pixmap=translated,
                          show_original=canvas.compare.isChecked() or not canvas.translation)
        pin.workspace_requested.connect(lambda mode: self.restore_pin(pin, mode))
        pin.configure_engines(self.config_getter())
        pin.languages_changed.connect(self.languages_changed)
        pin.translate_requested.connect(lambda: self.pin_tasks.start(pin))
        pin.cancel_requested.connect(lambda: self.pin_tasks.cancel(pin))
        pin.closing.connect(lambda: self.pin_tasks.cancel(pin))
        self.pins.append(pin)
        pin.destroyed.connect(lambda: self.pins.remove(pin) if pin in self.pins else None)
        self.result.close()
        pin.show()
        pin.activateWindow()

    def _connect_result(self):
        self.result.closed.connect(self.cancel)
        self.result.cancel_requested.connect(self.stop_current)
        self.result.retry.connect(self.retry)
        self.result.provider_changed.connect(self.switch_provider)
        self.result.languages_changed.connect(self.switch_languages)
        self.result.adjustment_started.connect(self.adjust_selection)
        self.result.selection_changed.connect(self.reselect)
        self.result.open_settings.connect(self.settings_callback)
        self.result.extract_requested.connect(self.extract_text)
        self.result.ocr_translate_requested.connect(lambda: self.extract_text(translate=True))
        self.result.pin_requested.connect(self.pin_selection)
        self.result.workspace_requested.connect(self.switch_workspace)

    def switch_languages(self, source, target):
        if self.closing or self.gate.busy or not self.result:
            return
        self.languages_changed.emit(source, target)
        if self.result.source_text().strip() and not self.result.ocr_mode:
            self.retry(self.result.source_text())

    def switch_workspace(self, mode):
        if self.closing or not self.result or not self.result.overlay.has_capture:
            return
        previous = self.gate.request_id
        self.gate.invalidate()
        self.network.cancel(previous)
        self.ocr.cancel()
        self.pending_ocr_translation = False
        self.secret = ''
        self.ocr_only = mode == 'ocr'
        self.result.set_busy(False)
        self.result.set_workspace_mode(mode)
        self.gate.state = State.COMPLETED
        if self.ocr_only:
            self.result.status.setText(tr('文字工作区 · 原文、译文与贴图共用当前截图'))
        elif (not self.result.translated.toPlainText()
              or self.result.translation_source != self.result.source_text()):
            if self.result.source_text().strip():
                self.retry(self.result.source_text())
            else:
                self.reselect(self.result.overlay.selection)
        else:
            self.result.status.setText(tr('翻译完成'))

    def restore_pin(self, pin, mode='resume'):
        if self.closing or pin.returning or not pin.state:
            return
        state = pin.state
        # Each pin owns its capture; never OCR the rendered Chinese patch.
        if self.result:
            old, self.result = self.result, None
            old.close()
            old.deleteLater()
        else:
            self.cancel()
        self.capture_screen = state['screen']
        self.snapshot = deepcopy(self.config_getter())
        self.snapshot['translation'] = profile_for(self.snapshot, state['provider'])
        settings = deepcopy(self.snapshot['window'])
        settings['display_mode'] = 'overlay'
        self.ocr_only = state['ocr_mode'] if mode == 'resume' else mode == 'ocr'
        self.result = ResultWindow(settings, self.snapshot, ocr_mode=self.ocr_only)
        self._connect_result()
        self.result.restore_state(state)
        self.gate.state = State.COMPLETED
        self.result.show()
        self.result.activateWindow()
        # Returning consumes this pin; unrelated desktop pins keep their lifetime.
        pin.returning = True
        if pin in self.pins:
            self.pins.remove(pin)
        pin.close()
        if mode == 'translate':
            self.switch_workspace('translate')
        elif mode == 'ocr' and not self.result.source_text().strip():
            self.extract_text()

    def _translate(self, text):
        values = dict(self.snapshot['translation'])
        values['source_lang'], values['target_lang'] = self.result.language_pair.pair()
        values['academic_prompt'] = self.snapshot.get('prompts', {}).get('academic', '')
        settings = ProviderSettings(**values)
        if not is_configured(settings):
            self.gate.state = State.COMPLETED
            self.result.set_busy(False)
            self.result.status.setText(tr('尚未配置翻译服务；可以复制原文或打开设置。'))
            self.secret = ''
            return
        self.gate.state = State.TRANSLATING
        self.result.set_busy(True)
        self.watch_request(settings.total_timeout_seconds, tr('正在等待翻译服务'))
        self.result.status.setText(tr('正在翻译…'))
        self.network.submit(TranslationRequest(self.gate.request_id, text, settings), self.secret)
        self.secret = ''

    def retry(self, text):
        if self.closing or self.gate.busy or not self.result:
            return
        self.gate.begin(State.TRANSLATING)
        self.snapshot = deepcopy(self.config_getter())
        self.snapshot['translation'] = profile_for(self.snapshot, self.result.engine.currentData())
        try:
            self.secret = self.credentials.get(self.snapshot['translation']['base_url'])
            self._translate(text)
        except AppError as error:
            self.failed(self.gate.request_id, error.code, error.user_message)

    def switch_provider(self, kind):
        if self.closing or not self.result or self.gate.state == State.RECOGNIZING:
            return
        text = self.result.source_text()
        if not text.strip():
            return
        previous = self.gate.request_id
        self.gate.invalidate()
        self.network.cancel(previous)
        self.ocr_only = self.result.ocr_mode
        self.gate.begin(State.TRANSLATING)
        self.snapshot = deepcopy(self.config_getter())
        self.snapshot['translation'] = profile_for(self.snapshot, kind)
        self.result.set_busy(True)
        try:
            values = self.snapshot['translation']
            self.secret = self.credentials.get(values['base_url']) if values['requires_api_key'] else ''
            self._translate(text)
        except AppError as error:
            self.failed(self.gate.request_id, error.code, error.user_message)

    def adjust_selection(self):
        self.pending_ocr_translation = False
        previous = self.gate.request_id
        self.gate.invalidate()
        self.network.cancel(previous)
        self.ocr.cancel()
        self.gate.state = State.SELECTING
        self.secret = ''
        if self.result:
            self.result.set_busy(True)
            self.result.status.setText(tr('松开鼠标确认新选区') if self.result.ocr_mode else tr('松开鼠标后识别并翻译新选区'))

    def reselect(self, rect):
        if self.closing or not self.result or not self.result.overlay.has_capture:
            return
        self.adjust_selection()
        request_id = self.gate.begin(State.RECOGNIZING)
        screen = self.capture_screen or CaptureScreen(self.screen)
        self.snapshot = deepcopy(self.config_getter())
        self.snapshot['translation'] = profile_for(self.snapshot, self.result.engine.currentData())
        if self.result.ocr_mode:
            self.ocr_only = True
            self.frame = None
            self.result.set_original('', '')
            self.result.set_busy(False)
            self.gate.state = State.COMPLETED
            geometry = screen.geometry()
            self.result.place_near(QRectF(rect).translated(geometry.x(), geometry.y()), screen)
            self.result.status.setText(tr('选区已更新，可提取文字或打开弹窗翻译'))
            return
        try:
            self.frame = make_frame(request_id, screen, self.result.overlay.screenshot, rect)
            self.secret = self.credentials.get(self.snapshot['translation']['base_url'])
            self.result.set_original('', '')
            self.result.status.setText(tr('正在识别…'))
            self.result.overlay.set_status(tr('正在识别…'))
            geometry = screen.geometry()
            self.result.place_near(QRectF(rect).translated(geometry.x(), geometry.y()), screen)
            self._submit_ocr(self.frame)
        except (AppError, RuntimeError) as error:
            self.failed(request_id, 'OCR_SUBMIT', str(error))

    def translation_done(self, result):
        if self.closing or not self.gate.accepts(result.request_id) or not self.result:
            return
        self.gate.state = State.COMPLETED
        self.result.set_translation(result)
        self.log.info('request=%s stage=translation elapsed_ms=%.1f', result.request_id, result.elapsed_ms)

    def watch_request(self, limit, phase):
        self.request_started, self.request_limit, self.request_phase = time.monotonic(), limit, phase
        self.progress_timer.start()

    def network_progress(self, request_id, phase):
        if self.gate.accepts(request_id):
            self.request_phase = phase

    def progress_tick(self):
        if not self.gate.busy or not self.result:
            self.progress_timer.stop()
            return
        elapsed = int(time.monotonic() - self.request_started)
        if elapsed >= self.request_limit:
            self.stop_current()
            self.result.status.setText(tr('等待超时，原文和选区已保留；可调整超时或换模型重试。'))
        else:
            self.result.status.setText(ui_format('{} · {} / {}{}', self.request_phase, elapsed, self.request_limit, tr(' 秒')))

    def stop_current(self):
        previous = self.gate.request_id
        self.gate.invalidate()
        self.network.cancel(previous)
        self.ocr.cancel()
        self.pending_ocr_translation = False
        self.secret = ''
        if self.result:
            self.result.set_busy(False)
            self.result.status.setText(tr('已取消，选区和原文已保留'))

    def _submit_ocr(self, frame):
        settings = self.snapshot.get('ocr', {'provider': 'local'})
        if settings['provider'] != 'local':
            self.watch_request(settings.get('total_timeout_seconds', 120), tr('正在等待云端识别'))
        if settings['provider'] != 'local':
            from ..providers.ocr_catalog import get_ocr_secret, requires_ocr_key
            secret = get_ocr_secret(self.credentials, settings)
            if requires_ocr_key(settings) and not secret:
                raise AppError('NO_OCR_KEY', tr('请在设置 → 文字识别中填写所选服务的 API Key。'))
            self.result.status.setText(tr('正在识别框选图片…'))
            self.network.submit_ocr(frame, settings, secret)
        else:
            self.ocr.submit(frame)

    def failed(self, request_id, code, message):
        if self.closing:
            return
        if not request_id:
            self.tray.setToolTip(tr('SnapTrans · 识别引擎不可用'))
            self.tray.notify(message)
            return
        if not self.gate.accepts(request_id):
            return
        self.gate.state = State.FAILED
        self.pending_ocr_translation = False
        self.secret = ''
        self.log.warning('request=%s error=%s', request_id, code)
        if self.result and self.result.isVisible():
            self.result.set_busy(False)
            self.result.status.setText(message)
        else:
            self.tray.notify(message)

    def cancel(self):
        self.progress_timer.stop()
        self.pending_ocr_translation = False
        previous = self.gate.request_id
        self.gate.invalidate()
        self.secret = ''
        if previous:
            self.network.cancel(previous)
        self.ocr.cancel()
        if self.selector:
            selector, self.selector = self.selector, None
            selector.confirmed = True
            selector.close()
            selector.deleteLater()
        self.pixmap = None
        self.frame = None
        self.capture_screen = None

    def close(self):
        self.closing = True
        self.pin_tasks.close()
        self.cancel()
        if self.result:
            self.result.close()
        for pin in list(self.pins):
            pin.close()

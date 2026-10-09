from ..i18n import ui_format
"""Pin-local translation jobs; workspace cancellation cannot consume their results."""
from ..i18n import tr
from copy import deepcopy
import time
from uuid import uuid4
from PySide6.QtCore import QObject, QTimer
from .capture import make_frame
from .models import AppError, ProviderSettings, TranslationRequest
from .text_cleanup import clean_text
from ..providers.catalog import profile_for, is_configured


class PinTasks(QObject):
    def __init__(self, network, credentials, config_getter, parent=None, ocr_factory=None):
        super().__init__(parent)
        self.network, self.credentials, self.config_getter = network, credentials, config_getter
        self.ocr_factory = ocr_factory
        self.ocr = None
        self.local_id = ''
        self.jobs = {}
        self.timer = QTimer(self)
        self.timer.setInterval(250)
        self.timer.timeout.connect(self.tick)
        network.succeeded.connect(self.translated)
        network.failed.connect(self.failed)
        if hasattr(network, 'ocr_succeeded'):
            network.ocr_succeeded.connect(self.recognized)
        if hasattr(network, 'progress'):
            network.progress.connect(self.progress)

    def start(self, pin):
        if pin.busy or not pin.state or pin.returning:
            return
        config = deepcopy(self.config_getter())
        values = profile_for(config, pin.engine.currentData())
        values['source_lang'], values['target_lang'] = pin.languages.pair()
        values['academic_prompt'] = config.get('prompts', {}).get('academic', '')
        settings = ProviderSettings(**values)
        if not is_configured(settings):
            pin.set_status(tr('请先在设置中配置此翻译服务，再重试。'))
            return
        request_id = 'pin-' + uuid4().hex
        job = dict(pin=pin, state=pin.state, config=config, settings=settings, phase=tr('准备翻译'),
                   started=time.monotonic(), limit=60, frame=None)
        self.jobs[request_id] = job
        pin.set_busy(True)
        self.timer.start()
        if pin.state.get('source', '').strip():
            self._translate(request_id)
            return
        try:
            state = pin.state
            job['frame'] = make_frame(request_id, state['screen'], state['screenshot'], state['selection'])
            ocr = config.get('ocr', {'provider': 'local'})
            if ocr['provider'] == 'local':
                job['phase'] = tr('等待本地识别')
                job['waiting_local'] = True
                self._dispatch_local()
            else:
                from ..providers.ocr_catalog import get_ocr_secret, requires_ocr_key
                secret = get_ocr_secret(self.credentials, ocr)
                if requires_ocr_key(ocr) and not secret:
                    raise AppError('NO_OCR_KEY', tr('请在设置的文字识别页填写 OCR 密钥。'))
                job.update(phase=tr('视觉识别'), limit=ocr['total_timeout_seconds'])
                self.network.submit_ocr(job['frame'], ocr, secret)
        except (AppError, ValueError, RuntimeError) as error:
            self.failed(request_id, 'PIN_OCR', str(error))

    def _dispatch_local(self):
        if self.local_id:
            return
        item = next(((key, value) for key, value in self.jobs.items() if value.get('waiting_local')), None)
        if item is None:
            return
        request_id, job = item
        try:
            if self.ocr is None:
                from .ocr_process import OcrService
                from ..paths import resource_root
                self.ocr = self.ocr_factory() if self.ocr_factory else OcrService(resource_root() / 'assets' / 'ocr')
                self.ocr.succeeded.connect(self.recognized)
                self.ocr.failed.connect(self.local_failed)
            self.local_id = request_id
            job.update(phase=tr('本地识别'), started=time.monotonic())
            job['waiting_local'] = False
            self.ocr.submit(job['frame'])
        except Exception:
            self.failed(request_id, 'PIN_OCR', tr('本地识别启动失败，请重试。'))

    def local_failed(self, request_id, code, message):
        self.failed(request_id or self.local_id, code, message)

    def recognized(self, result):
        job = self.jobs.get(result.request_id)
        if job is None:
            return
        if self.local_id == result.request_id:
            self.local_id = ''
        text = clean_text(result)
        if not text:
            self.failed(result.request_id, 'NO_TEXT', tr('未识别到文字，原图已保留。'))
        else:
            job['state'].update(raw=result.raw_text, source=text)
            job['ocr_result'] = result
            self._translate(result.request_id)
        self._dispatch_local()

    def _translate(self, request_id):
        job = self.jobs[request_id]
        try:
            settings = job['settings']
            secret = self.credentials.get(settings.base_url) if settings.requires_api_key else ''
            if settings.requires_api_key and not secret:
                raise AppError('NO_KEY', tr('此服务需要 API Key，请在设置中填写后重试。'))
            job.update(phase=tr('正在翻译'), started=time.monotonic(), limit=settings.total_timeout_seconds)
            job['pin'].set_status(tr('正在翻译… 可继续移动和标注贴图'))
            self.network.submit(TranslationRequest(request_id, job['state']['source'], settings), secret)
        except (AppError, ValueError, RuntimeError) as error:
            self.failed(request_id, 'PIN_TRANSLATION', str(error))

    def translated(self, result):
        job = self.jobs.get(result.request_id)
        if job is None:
            return
        # Reuse screenshot rendering at the original capture DPI, without displaying a workspace.
        from ..ui.translation_canvas import TranslationCanvas
        canvas = TranslationCanvas()
        try:
            state = job['state']
            canvas.attach_capture(state['screen'], state['screenshot'], state['selection'])
            canvas.source_font_px = state.get('source_font_px', 18)
            if job.get('ocr_result') is not None:
                canvas.set_ocr_lines(job['ocr_result'], job['frame'])
            canvas.translation = result.text
            translated = canvas.rendered_selection(force_translation=True)
            state.update(translation=result.text, translation_source=state['source'],
                         provider=job['settings'].provider, source_font_px=canvas.source_font_px,
                         source_lang=job['settings'].source_lang, target_lang=job['settings'].target_lang,
                         ocr_mode=False, compare=False, status=tr('翻译完成'))
            job['pin'].set_translation(translated)
            self._finish(result.request_id, tr('翻译完成 · 可在这里对照原文'))
        except (ValueError, RuntimeError):
            self.failed(result.request_id, 'PIN_RENDER', tr('译文排版失败，原图已保留，请重试。'))
        finally:
            canvas.deleteLater()

    def progress(self, request_id, phase):
        if request_id in self.jobs:
            self.jobs[request_id]['phase'] = phase

    def tick(self):
        for key, job in list(self.jobs.items()):
            elapsed = int(time.monotonic() - job['started'])
            if elapsed >= job['limit']:
                self._finish(key, tr('等待超时，原图和已识别文字已保留，可重试。'), cancel=True)
            else:
                job['pin'].set_status(ui_format('{} · {} / {}{}', job['phase'], elapsed, job['limit'], tr(' 秒')))

    def failed(self, request_id, code, message):
        if request_id in self.jobs:
            self._finish(request_id, message, cancel=True)

    def _finish(self, request_id, message='', cancel=False):
        job = self.jobs.pop(request_id, None)
        if job is None:
            return
        if cancel:
            self.network.cancel(request_id)
        if self.local_id == request_id:
            self.local_id = ''
            if self.ocr:
                self.ocr.cancel()
        job['pin'].set_busy(False)
        job['pin'].set_status(message)
        if not self.jobs:
            self.timer.stop()
            if self.ocr:
                self.ocr.close()
                self.ocr.deleteLater()
                self.ocr = None
        self._dispatch_local()

    def cancel(self, pin):
        for request_id, job in list(self.jobs.items()):
            if job['pin'] is pin:
                self._finish(request_id, tr('已取消 · 原图保留'), cancel=True)

    def close(self):
        for key in list(self.jobs):
            self._finish(key, cancel=True)

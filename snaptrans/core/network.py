import asyncio
from concurrent.futures import CancelledError
import threading
from PySide6.QtCore import QObject, Signal

from ..providers.compatible import CompatibleProvider
from .models import AppError


class NetworkService(QObject):
    succeeded = Signal(object)
    failed = Signal(str, str, str)
    models_ready = Signal(str, object)
    ocr_succeeded = Signal(object)
    progress = Signal(str, object)

    def __init__(self):
        super().__init__()
        self.loop = asyncio.new_event_loop()
        self.providers = {}
        self.pending = {}
        self.closing = False
        self.web = None
        self.thread = threading.Thread(target=self._run, name='SnapTrans-network', daemon=True)
        self.thread.start()

    def _run(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()
        self.loop.close()

    async def _translate(self, request, secret):
        kind = request.settings_snapshot.provider
        if kind not in self.providers:
            if kind == 'mymemory':
                from ..providers.mymemory import MyMemoryProvider
                self.providers[kind] = MyMemoryProvider()
            elif kind in ('google', 'microsoft'):
                from ..providers.traditional import TraditionalProvider
                self.providers[kind] = TraditionalProvider()
            elif kind in ('deepl', 'baidu', 'youdao', 'libre'):
                from ..providers.translation_services import TranslationServices
                self.providers[kind] = TranslationServices()
            elif kind == 'claude':
                from ..providers.claude import ClaudeProvider
                self.providers[kind] = ClaudeProvider()
            elif kind == 'nvidia':
                from ..providers.nvidia import NvidiaProvider
                self.providers[kind] = NvidiaProvider()
                self.providers[kind].progress = self.progress.emit
            else:
                self.providers[kind] = CompatibleProvider(trust_env=kind != 'ollama')
        if kind == 'nvidia':
            self.providers[kind].progress = self.progress.emit
        return await self.providers[kind].translate(request, secret)

    def submit(self, request, secret):
        if self.closing:
            return
        from ..providers.catalog import WEB_PROVIDERS
        if request.settings_snapshot.provider in WEB_PROVIDERS:
            if self.web is None:
                from ..providers.web_translation import WebTranslationService
                self.web = WebTranslationService(self)
                self.web.succeeded.connect(self.succeeded)
                self.web.failed.connect(self.failed)
                self.web.progress.connect(self.progress)
            self.web.submit(request)
            return
        future = asyncio.run_coroutine_threadsafe(self._translate(request, secret), self.loop)
        self.pending[request.request_id] = future
        future.add_done_callback(lambda item: self._done(request.request_id, item))

    async def _models(self, secret):
        from ..providers.nvidia import NvidiaProvider
        if 'nvidia' not in self.providers:
            self.providers['nvidia'] = NvidiaProvider()
        return await self.providers['nvidia'].list_models(secret)

    def submit_models(self, request_id, secret):
        if self.closing:
            return
        future = asyncio.run_coroutine_threadsafe(self._models(secret), self.loop)
        self.pending[request_id] = future
        future.add_done_callback(lambda item: self._done(request_id, item, models=True))

    async def _recognize(self, frame, settings, secret):
        from ..providers.nvidia_ocr import NvidiaOcrProvider
        if settings['provider'] not in ('nvidia', 'nvidia_vl'):
            from ..providers.vision_ocr import VisionOcrProvider
            if 'vision_ocr' not in self.providers:
                self.providers['vision_ocr'] = VisionOcrProvider()
                self.providers['vision_ocr'].progress = self.progress.emit
            return await self.providers['vision_ocr'].recognize(frame, settings, secret)
        if settings['provider'] == 'nvidia_vl':
            from ..providers.nvidia_vl import NvidiaVisionProvider
            if 'nvidia_vl' not in self.providers:
                self.providers['nvidia_vl'] = NvidiaVisionProvider()
                self.providers['nvidia_vl'].progress = self.progress.emit
            return await self.providers['nvidia_vl'].recognize(frame, settings, secret)
        if 'nvidia_ocr' not in self.providers:
            self.providers['nvidia_ocr'] = NvidiaOcrProvider()
        return await self.providers['nvidia_ocr'].recognize(frame, settings, secret)

    def submit_ocr(self, frame, settings, secret):
        if self.closing:
            return
        future = asyncio.run_coroutine_threadsafe(self._recognize(frame, settings, secret), self.loop)
        self.pending[frame.request_id] = future
        future.add_done_callback(lambda item: self._done(frame.request_id, item, ocr=True))

    def _done(self, request_id, future, models=False, ocr=False):
        self.pending.pop(request_id, None)
        if self.closing:
            return
        try:
            if models:
                self.models_ready.emit(request_id, future.result())
            elif ocr:
                self.ocr_succeeded.emit(future.result())
            else:
                self.succeeded.emit(future.result())
        except CancelledError:
            return
        except AppError as error:
            self.failed.emit(request_id, error.code, error.user_message)
        except Exception:
            self.failed.emit(request_id, 'NETWORK_INTERNAL', '翻译请求失败，请检查服务配置。')

    def cancel(self, request_id):
        if self.web:
            self.web.cancel(request_id)
        future = self.pending.get(request_id)
        if future:
            future.cancel()

    async def _shutdown(self):
        tasks = [task for task in asyncio.all_tasks() if task is not asyncio.current_task()]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        for provider in self.providers.values():
            await provider.aclose()

    def close(self):
        self.closing = True
        if self.web:
            self.web.close()
        future = asyncio.run_coroutine_threadsafe(self._shutdown(), self.loop)
        try:
            future.result(timeout=5)
        finally:
            self.loop.call_soon_threadsafe(self.loop.stop)
            self.thread.join(timeout=5)

import multiprocessing
from pathlib import Path
import queue
import threading
import time
from PySide6.QtCore import QObject, QTimer, Signal
from .models import AppError


def ocr_worker(connection, resource_dir):
    try:
        from .ocr_adapter import OcrAdapter
        engine = OcrAdapter(Path(resource_dir))
        connection.send(('ready', None))
        while True:
            frame = connection.recv()
            if frame is None:
                return
            try:
                connection.send(('result', engine.recognize(frame)))
            except AppError as error:
                connection.send(('error', (frame.request_id, error.code, error.user_message)))
            except Exception:
                connection.send(('error', (frame.request_id, 'OCR_FAILED', '文字识别失败，请重新框选。')))
    except AppError as error:
        connection.send(('init_error', (error.code, error.user_message)))
    except Exception:
        try:
            connection.send(('init_error', ('OCR_INIT', '识别引擎初始化失败，请检查完整软件包和运行库。')))
        except (OSError, EOFError):
            return
    finally:
        connection.close()


class OcrService(QObject):
    ready = Signal()
    succeeded = Signal(object)
    failed = Signal(str, str, str)
    _event = Signal(int, object)

    def __init__(self, resource_dir):
        super().__init__()
        self.resource_dir = resource_dir
        self.process = None
        self.connection = None
        self.sender_queue = None
        self.generation = 0
        self.is_ready = False
        self.pending = None
        self.active_id = ''
        self.deadline = 0
        self.rebuilt = False
        self.closed = False
        self._event.connect(self._receive)
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self._watch)
        self.timer.start()

    def start(self):
        if self.closed or self.process is not None:
            return
        context = multiprocessing.get_context('spawn')
        parent, child = context.Pipe()
        self.connection = parent
        self.process = context.Process(target=ocr_worker, args=(child, str(self.resource_dir)), daemon=True)
        self.process.start()
        child.close()
        self.deadline = time.monotonic() + 30
        self.sender_queue = queue.Queue(maxsize=2)
        generation = self.generation
        threading.Thread(target=self._listen, args=(parent, generation), daemon=True).start()
        threading.Thread(target=self._send, args=(parent, self.sender_queue, generation), daemon=True).start()

    def _listen(self, connection, generation):
        try:
            while True:
                message = connection.recv()
                self._event.emit(generation, message)
        except (OSError, EOFError, TypeError):
            return

    def _send(self, connection, outbound, generation):
        while True:
            frame = outbound.get()
            if frame is None:
                return
            try:
                connection.send(frame)
            except (OSError, EOFError, TypeError):
                self._event.emit(generation, ('error', (frame.request_id, 'OCR_IPC', '识别进程通信中断，请重试。')))
                return

    def submit(self, frame):
        if self.active_id:
            raise RuntimeError('OCR already busy')
        self.active_id = frame.request_id
        self.pending = frame
        self.start()
        if self.is_ready:
            self._dispatch()

    def _dispatch(self):
        frame, self.pending = self.pending, None
        self.sender_queue.put_nowait(frame)
        self.deadline = time.monotonic() + 30

    def _receive(self, generation, message):
        if generation != self.generation or self.closed:
            return
        kind, payload = message
        if kind == 'ready':
            self.is_ready = True
            self.deadline = 0
            self.ready.emit()
            if self.pending:
                self._dispatch()
        elif kind == 'result':
            self.active_id = ''
            self.deadline = 0
            self.succeeded.emit(payload)
        elif kind == 'error':
            self.active_id = ''
            self.deadline = 0
            self.failed.emit(*payload)
        elif kind == 'init_error':
            request_id = self.active_id
            self._stop()
            self.failed.emit(request_id, *payload)

    def _watch(self):
        if self.process is None:
            return
        timeout = self.deadline and time.monotonic() > self.deadline
        if timeout or not self.process.is_alive():
            request_id = self.active_id
            self._stop()
            self.failed.emit(request_id, 'OCR_TIMEOUT' if timeout else 'OCR_CRASH',
                             '识别超时或进程已退出，请重新截图。')
            if not self.rebuilt:
                self.rebuilt = True
                self.start()

    def _stop(self):
        self.generation += 1
        if self.process is not None:
            if self.process.is_alive():
                self.process.terminate()
            self.process.join(timeout=2)
            if self.process.is_alive():
                self.process.kill()
                self.process.join(timeout=2)
            self.process.close()
        if self.connection:
            self.connection.close()
        if self.sender_queue:
            try:
                self.sender_queue.put_nowait(None)
            except queue.Full:
                self.sender_queue.get_nowait()
                self.sender_queue.put_nowait(None)
        self.process = self.connection = self.sender_queue = None
        self.is_ready = False
        self.pending = None
        self.active_id = ''
        self.deadline = 0

    def cancel(self):
        if self.active_id:
            self._stop()

    def close(self):
        self.closed = True
        self.timer.stop()
        self._stop()

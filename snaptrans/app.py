from .i18n import ui_format
from copy import deepcopy
from dataclasses import replace
import time
import sys
from uuid import uuid4
from PySide6.QtCore import QObject, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from . import __version__
from .paths import initialize_storage, resource_root
from .config import ConfigStore
from .credentials import CredentialStore
from .core.models import AppError, ProviderSettings, TranslationRequest
from .core.ocr_process import OcrService
from .core.network import NetworkService
from .core.controller import Controller
from .hotkeys import Hotkeys
from .instance import SingleInstance
from .logging_config import setup_logging
from .ui.tray import Tray
from .ui.settings_window import SettingsWindow
from .providers.nvidia_ocr import OCR_ENDPOINT
from .i18n import set_language, tr


class Application(QObject):
    def __init__(self, qt, data):
        super().__init__()
        self.qt = qt
        self.data = data
        self.logger = setup_logging(data)
        self.store = ConfigStore(data / 'config.json')
        self.config = self.store.load()
        set_language(self.config.get('interface', {}).get('language', 'system'))
        first_run = not self.config['onboarding']['completed']
        from .ui.themes import set_current_theme
        set_current_theme(self.config['window']['theme'])
        self._settings_workspace = None
        self.credentials = CredentialStore(data / 'credentials.json')
        self.settings = None
        self.test_id = ''
        self.models_id = ''
        self.ocr_test_id = ''
        self.stopping = False
        self.test_started = 0
        self.test_limit = 0
        self.test_phase = ''
        self.test_timer = QTimer(self)
        self.test_timer.setInterval(250)
        self.test_timer.timeout.connect(self.test_tick)
        self.tray = Tray(resource_root() / 'assets' / 'icon.ico')
        self.ocr = OcrService(resource_root() / 'assets' / 'ocr')
        self.network = NetworkService()
        self.hotkeys = Hotkeys()
        self.controller = Controller(self.ocr, self.network, self.credentials, lambda: self.config, self.tray, self.open_settings)
        self.controller.languages_changed.connect(self.save_languages)
        self.tray.translate.connect(lambda: self.controller.capture('translate'))
        self.tray.ocr.connect(lambda: self.controller.capture('ocr'))
        self.tray.settings.connect(self.open_settings)
        self.tray.about.connect(self.about)
        self.tray.quit_requested.connect(self.quit)
        self.hotkeys.activated.connect(self.controller.capture)
        self.ocr.ready.connect(lambda: self.tray.setToolTip(tr('SnapTrans · 就绪')))
        self.network.succeeded.connect(self.test_done)
        self.network.failed.connect(self.test_failed)
        self.network.progress.connect(self.test_progress)
        self.network.models_ready.connect(self.models_done)
        self.network.ocr_succeeded.connect(self.ocr_test_done)
        self.tray.show()
        try:
            self.hotkeys.install(self.config['hotkeys'])
        except ValueError as error:
            QTimer.singleShot(200, lambda message=str(error): self.tray.notify(message))
        self.tray.update_hotkeys(self.hotkeys.bindings)
        QTimer.singleShot(0, self.ocr.start)
        if self.store.warning:
            QTimer.singleShot(500, lambda: self.tray.notify(self.store.warning))
        elif not self.config['translation']['base_url']:
            QTimer.singleShot(500, lambda: self.tray.notify(tr('Alt+W 可离线识字。在线翻译请从托盘打开设置。')))
        qt.aboutToQuit.connect(self.cleanup)
        if first_run:
            QTimer.singleShot(0, self.open_first_run_settings)
        elif self.config.get('startup', {}).get('open_settings', False):
            QTimer.singleShot(0, self.open_settings)

    def save_languages(self, source, target):
        config = deepcopy(self.config)
        config['translation'].update(source_lang=source, target_lang=target)
        try:
            self.store.save(config)
        except (OSError, ValueError):
            self.tray.notify(tr('本次语言已应用，但无法保存为默认值。请检查程序目录写入权限。'))
            return
        self.config = config
        if self.settings:
            # Keep unrelated drafts intact when a desktop pin changes direction.
            self.settings.config['translation'].update(source_lang=source, target_lang=target)

    def open_first_run_settings(self):
        if not self.stopping:
            self.open_settings()
            self.settings.show_onboarding()

    def open_settings(self):
        if self.settings is None:
            result = self.controller.result
            if result and result.isVisible():
                self._settings_workspace = result
                result.hide()
            warning, secret = '', ''
            try:
                secret = self.credentials.get(self.config['translation']['base_url'])
            except AppError as error:
                warning = error.user_message
            from .providers.ocr_catalog import get_ocr_secret
            self.settings = SettingsWindow(self.config, secret, warning, self.credentials.get,
                lambda settings: get_ocr_secret(self.credentials, settings))
            self.settings.save_requested.connect(self.save_settings)
            self.settings.interface_language_requested.connect(self.save_interface_language)
            self.settings.test_requested.connect(self.test_connection)
            self.settings.prompt_save_requested.connect(self.save_prompt)
            self.settings.cancel_test_requested.connect(self.cancel_tests)
            self.settings.models_requested.connect(self.request_models)
            self.settings.ocr_test_requested.connect(self.test_cloud_ocr)
            self.settings.closed.connect(self.settings_closed)
            self.settings.hotkey_recording.connect(self.record_hotkey)
            self.settings.hotkey_change_requested.connect(self.save_hotkey)
        self.settings.show()
        self.settings.raise_()
        self.settings.activateWindow()

    def record_hotkey(self, recording):
        if self.stopping:
            return
        try:
            self.hotkeys.set_suspended(recording)
        except ValueError as error:
            self.tray.notify(str(error))

    def settings_closed(self):
        self.test_timer.stop()
        if self.ocr_test_id:
            self.network.cancel(self.ocr_test_id)
            self.ocr_test_id = ''
        if self.models_id:
            self.network.cancel(self.models_id)
            self.models_id = ''
        if self.test_id:
            self.network.cancel(self.test_id)
            self.test_id = ''
        old, self.settings = self.settings, None
        if old:
            old.deleteLater()
        previous, self._settings_workspace = self._settings_workspace, None
        if not self.stopping and previous is not None and previous is self.controller.result and previous.overlay.has_capture:
            previous.show()
            previous.activateWindow()

    def save_hotkey(self, action, value):
        if self.stopping or action not in ('translate', 'ocr'):
            return
        previous = deepcopy(self.config)
        updated = deepcopy(previous)
        updated['hotkeys'][action] = value
        error = ''
        try:
            self.hotkeys.install(updated['hotkeys'])
            self.store.save(updated)
        except (ValueError, OSError) as failure:
            error = str(failure) if isinstance(failure, ValueError) else tr('配置写入失败，请检查目录权限。')
            try:
                self.hotkeys.install(previous['hotkeys'])
            except ValueError as restore_error:
                error += '；' + str(restore_error)
        else:
            self.config = updated
        if self.settings:
            self.settings.hotkey_saved(action, self.config['hotkeys'][action], error)
        self.tray.update_hotkeys(self.hotkeys.bindings)

    def save_interface_language(self, language):
        updated = deepcopy(self.config)
        updated['interface'] = {'language': language}
        try:
            self.store.save(updated)
        except (OSError, ValueError):
            if self.settings:
                self.settings.interface_language_saved(self.config['interface']['language'],
                    tr('无法保存界面语言，已保留原设置。请检查目录写入权限。'))
            return
        self.config = updated
        set_language(language)
        if self.settings:
            self.settings.interface_language_saved(language)

    def save_settings(self, config, secret):
        previous = deepcopy(self.config)
        key_snapshot = None
        try:
            key_snapshot = self.credentials.snapshot()
            self.hotkeys.install(config['hotkeys'])
            trans = config['translation']
            self.credentials.save(trans['base_url'], secret, trans['save_api_key'])
            if self.settings:
                for url, scope, value, persist in self.settings.ocr_key_updates():
                    self.credentials.save(url, value, persist, scope=scope)
            self.store.save(config)
        except Exception as error:
            try:
                self.hotkeys.install(previous['hotkeys'])
                if key_snapshot is not None:
                    self.credentials.restore(key_snapshot)
            except Exception:
                self.tray.notify(tr('设置恢复不完整，请检查快捷键与密钥。'))
            self.tray.update_hotkeys(self.hotkeys.bindings)
            if self.settings:
                self.settings.message.setText(str(error) if isinstance(error, (ValueError, AppError)) else tr('保存失败，请检查目录写入权限。'))
            return
        self.config = deepcopy(config)
        set_language(config['interface']['language'])
        from .ui.theme import refresh_themes
        refresh_themes(config['window']['theme'])
        self.tray.update_hotkeys(self.hotkeys.bindings)
        if self.controller.result:
            self.controller.result.update_preferences(self.config)
        if self.settings:
            self.settings.saved(self.config)

    def test_connection(self, config, secret):
        if self.test_id:
            self.network.cancel(self.test_id)
        self.test_id = 'test-' + uuid4().hex
        self.start_test_watch(config['translation']['total_timeout_seconds'], tr('等待 NVIDIA / 翻译服务响应'))
        self.settings.test_button.setEnabled(False)
        values = dict(config['translation'])
        values['academic_prompt'] = config.get('prompts', {}).get('academic', '')
        # A connectivity probe is deliberately small even if a model card permits a huge output.
        if values['provider'] == 'nvidia':
            values.update(max_tokens=512, model_defaults=False)
            from .providers.model_cards import model_card
            import json
            values['extra_body_json'] = json.dumps({**model_card(values['model'])['extra'], **json.loads(values['extra_body_json'])})
        self.network.submit(TranslationRequest(self.test_id, 'Hello.', ProviderSettings(**values)), secret)

    def test_done(self, result):
        if result.request_id == self.test_id and self.settings:
            self.finish_test_watch()
            self.settings.message.setText(tr('连接成功：') + result.text[:120])
            self.settings.test_button.setEnabled(True)
            self.test_id = ''

    def test_failed(self, request_id, code, message):
        if request_id in (self.test_id, self.ocr_test_id):
            self.finish_test_watch()
        if request_id == self.ocr_test_id and self.settings:
            self.settings.message.setText(message)
            self.settings.ocr_test_button.setEnabled(True)
            self.ocr_test_id = ''
        if request_id == self.models_id and self.settings:
            self.settings.message.setText(message)
            self.settings.fetch_models_button.setEnabled(True)
            self.models_id = ''
        if request_id == self.test_id and self.settings:
            self.settings.message.setText(message)
            self.settings.test_button.setEnabled(True)
            self.test_id = ''

    def request_models(self, secret):
        if self.models_id:
            self.network.cancel(self.models_id)
        self.models_id = 'models-' + uuid4().hex
        self.network.submit_models(self.models_id, secret)

    def test_cloud_ocr(self, settings, secret):
        from PIL import Image, ImageDraw
        from .core.models import CaptureFrame
        if self.ocr_test_id:
            self.network.cancel(self.ocr_test_id)
        self.ocr_test_id = 'ocr-test-' + uuid4().hex
        image = Image.new('RGB', (400, 100), 'white')
        ImageDraw.Draw(image).text((20, 25), 'Hello SnapTrans', fill='black', font_size=32)
        frame = CaptureFrame(self.ocr_test_id, 'public-test', (0, 0, 400, 100), (0, 0, 400, 100),
                             (0, 0, 400, 100), 400, 100, image.tobytes())
        self.settings.ocr_test_button.setEnabled(False)
        self.start_test_watch(settings['total_timeout_seconds'], tr('等待识别服务（Hello 示例图片）'))
        self.network.submit_ocr(frame, settings, secret)

    def ocr_test_done(self, result):
        if result.request_id == self.ocr_test_id and self.settings:
            self.ocr_test_id = ''
            self.finish_test_watch()
            self.settings.ocr_test_button.setEnabled(True)
            self.settings.message.setText(tr('识别服务连接成功，已识别示例图片。') if result.raw_text.strip() else tr('识别服务已响应，但未识别到示例文字。'))

    def models_done(self, request_id, models):
        if request_id == self.models_id and self.settings:
            self.models_id = ''
            self.settings.show_models(models)

    def save_prompt(self, text):
        updated = deepcopy(self.config)
        updated['prompts'] = {'academic': text}
        try:
            self.store.save(updated)
        except (OSError, ValueError):
            self.settings.prompt_saved(text, tr('保存失败，原提示词未变，请检查目录权限'))
            return
        self.config = updated
        self.settings.prompt_saved(text)

    def start_test_watch(self, limit, phase):
        self.test_started, self.test_limit, self.test_phase = time.monotonic(), limit, phase
        self.settings.test_button.setEnabled(False)
        self.settings.ocr_test_button.setEnabled(False)
        self.settings.cancel_test_button.setVisible(True)
        self.test_timer.start()
        self.test_tick()

    def finish_test_watch(self):
        self.test_timer.stop()
        if self.settings:
            self.settings.cancel_test_button.setVisible(False)
            self.settings.test_button.setEnabled(True)
            self.settings.ocr_test_button.setEnabled(True)

    def test_progress(self, request_id, phase):
        if request_id in (self.test_id, self.ocr_test_id):
            self.test_phase = phase

    def test_tick(self):
        if not self.settings:
            self.test_timer.stop()
            return
        elapsed = int(time.monotonic() - self.test_started)
        if elapsed >= self.test_limit:
            self.cancel_tests(tr('测试已超时，服务可能仍在排队或推理。可调整等待时间或换模型。'))
        else:
            self.settings.message.setText(ui_format('{} · {} / {}{}', self.test_phase, elapsed, self.test_limit, tr(' 秒，可随时取消')))

    def cancel_tests(self, message='已取消测试'):
        for name in ('test_id', 'ocr_test_id'):
            request_id = getattr(self, name)
            if request_id:
                self.network.cancel(request_id)
            setattr(self, name, '')
        self.finish_test_watch()
        if self.settings:
            self.settings.test_button.setEnabled(True)
            self.settings.ocr_test_button.setEnabled(True)
            self.settings.message.setText(message)

    def about(self):
        dialog = QMessageBox(QMessageBox.Icon.Information, tr('关于 SnapTrans'),
                             ui_format('SnapTrans {}{}', __version__, tr('\n本地 OCR：RapidOCR 3.9.2 / PP-OCRv6\n默认本地识别，不保存截图、原文和译文。在线翻译发送文本。\n启用云端 OCR 或视觉模型后，会向所选服务发送框选图片。\n软件免费，第三方翻译服务可能收费。')))
        licenses = dialog.addButton(tr('第三方许可'), QMessageBox.ButtonRole.ActionRole)
        dialog.addButton(tr('关闭'), QMessageBox.ButtonRole.RejectRole)
        from .ui.theme import apply_theme
        apply_theme(dialog)
        dialog.exec()
        if dialog.clickedButton() == licenses:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(resource_root() / 'THIRD_PARTY_NOTICES.md')))

    def cleanup(self):
        if self.stopping:
            return
        if self.settings:
            self.settings.translate_hotkey._commit_manual()
            self.settings.ocr_hotkey._commit_manual()
        self.stopping = True
        self.hotkeys.close()
        self.controller.close()
        if self.settings:
            self.settings.close()
        self.ocr.close()
        self.network.close()
        self.credentials.clear_session()
        self.tray.hide()

    def quit(self):
        self.cleanup()
        self.qt.quit()


def run():
    qt = QApplication(sys.argv)
    from .ui.fonts import initialize_fonts
    initialize_fonts(qt)
    qt.setApplicationName('SnapTrans')
    qt.setQuitOnLastWindowClosed(False)
    qt.setWindowIcon(QIcon(str(resource_root() / 'assets' / 'icon.ico')))
    instance = None
    try:
        data = initialize_storage()
        instance = SingleInstance()
        if instance.already_running:
            QMessageBox.information(None, f'SnapTrans {__version__}',
                ui_format('{}{}{}', tr('已有 SnapTrans 在系统托盘运行，本次打开的 '), __version__, tr(' 尚未启动。\n\n若要体验新版本，请先右击任务栏托盘中的 SnapTrans 图标并选择「退出」，再打开这个版本。')))
            return 0
        if not QSystemTrayIcon.isSystemTrayAvailable():
            raise AppError('NO_TRAY', tr('系统托盘不可用，无法启动 SnapTrans。'))
        application = Application(qt, data)
        return qt.exec()
    except (AppError, OSError) as error:
        QMessageBox.critical(None, tr('SnapTrans 启动失败'),
                             str(error) if isinstance(error, AppError) else tr('无法写入安装目录下的 data 文件夹。请将 SnapTrans 安装或解压到当前用户可写的目录；程序不会改用 C 盘保存数据。'))
        return 1
    finally:
        if instance:
            instance.close()

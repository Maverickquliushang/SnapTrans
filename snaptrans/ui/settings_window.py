from ..i18n import ui_format
from PySide6.QtWidgets import QWidget as QtWidget
from ..i18n import tr
from copy import deepcopy
from .. import __version__
from .ocr_settings import OcrSettingsMixin
import json
from .number_edit import NumberEdit
from .language_picker import LanguagePair
from .prompt_editor import PromptEditor
from .provider_picker import ProviderPicker, SERVICES, service_icon, EngineStack
from ..providers.model_cards import model_card, VISION_MODEL
from ..providers.prompts import ACADEMIC
from PySide6.QtCore import Signal, Qt, QUrl, QTimer, QSize
from PySide6.QtGui import QCursor, QGuiApplication, QDesktopServices, QShortcut, QKeySequence
from .localized_widgets import (QDialog, QVBoxLayout, QLineEdit, QCheckBox, QFrame,
                               QComboBox, QSpinBox, QLabel, QPushButton, QHBoxLayout,
                               QScrollArea, QWidget, QTabWidget, QSizePolicy, QPlainTextEdit, QListWidget, QInputDialog, QStackedWidget, QGridLayout, QToolButton)
from ..config import validate
from ..credentials import origin
from ..providers.catalog import PROVIDERS, TRADITIONAL, CHAT_PRESETS, DEEPL_URLS, WEB_PROVIDERS, LOCAL_PROVIDERS, default_profile
from .hotkey_edit import HotkeyEdit, HotkeyControl
from .theme import apply_theme, card, label, style_tree, THEMES
from ..providers.nvidia_ocr import OCR_ENDPOINT
from .preferences_shell import Toggle, InlineMessage, PREFERENCES_STYLE, NavigationDelegate, elevate, theme_preview, CheckRow


class SettingsWindow(QDialog, OcrSettingsMixin):
    interface_language_requested = Signal(str)
    save_requested = Signal(object, str)
    test_requested = Signal(object, str)
    closed = Signal()
    hotkey_recording = Signal(bool)
    hotkey_change_requested = Signal(str, str)
    models_requested = Signal(str)
    prompt_save_requested = Signal(str)
    cancel_test_requested = Signal()
    ocr_test_requested = Signal(object, str)

    def __init__(self, config, secret='', key_warning='', secret_lookup=None, ocr_secret_lookup=None):
        super().__init__()
        self.setWindowFlag(Qt.WindowType.WindowMinMaxButtonsHint, True)
        self.setSizeGripEnabled(True)
        self.setWindowTitle(ui_format('SnapTrans {}{}', __version__, tr(' · 设置')))
        self.setMinimumWidth(540)
        self.config = deepcopy(config)
        self.profiles = deepcopy(config.get('profiles', {}))
        self.profiles[config['translation']['provider']] = deepcopy(config['translation'])
        self._active_kind = config['translation']['provider']
        self.secret_lookup = secret_lookup
        self.saved_secret = secret
        self.original_origin = origin(config['translation']['base_url'])
        self._released = False
        self.saved_ocr_secret = ''
        self.finished.connect(self._release)
        self.translate_hotkey = HotkeyEdit(config['hotkeys']['translate'])
        self.ocr_hotkey = HotkeyEdit(config['hotkeys']['ocr'])
        self.translate_hotkey_control = HotkeyControl(self.translate_hotkey)
        self.ocr_hotkey_control = HotkeyControl(self.ocr_hotkey)
        self.translate_hotkey.recording.connect(self.hotkey_recording)
        self.ocr_hotkey.recording.connect(self.hotkey_recording)
        self.translate_hotkey.commit_requested.connect(lambda value: self.hotkey_change_requested.emit('translate', value))
        self.ocr_hotkey.commit_requested.connect(lambda value: self.hotkey_change_requested.emit('ocr', value))
        trans = config['translation']
        self.translation_languages = LanguagePair(trans.get('source_lang', 'en'), trans.get('target_lang', 'zh-CN'))
        self.provider = QComboBox(self)
        self.provider.hide()  # Internal selection model; visible entry points are icon cards.
        for key, (provider_label, url) in PROVIDERS.items():
            self.provider.addItem(provider_label, key)
        self.provider.setCurrentIndex(self.provider.findData(trans['provider']))
        self.base_url = QLineEdit(trans['base_url'])
        self.base_url.setPlaceholderText(tr('https://服务域名/v1 或 http://localhost:11434/v1'))
        self.model = QLineEdit(trans['model'])
        self.model.setPlaceholderText(tr('复制模型页代码中的 model，或点击下方获取模型'))
        self.model_tools = QWidget()
        model_tools = QHBoxLayout(self.model_tools)
        model_tools.setContentsMargins(0, 0, 0, 0)
        self.fetch_models_button = QPushButton(tr('获取模型'))
        self.fetch_models_button.clicked.connect(self._request_models)
        self.catalog_button = QPushButton(tr('模型网站 ↗'))
        self.catalog_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl('https://build.nvidia.com/models')))
        model_tools.addWidget(self.fetch_models_button)
        presets = QPushButton(tr('实测预设'))
        presets.clicked.connect(self._choose_preset)
        model_tools.addWidget(presets)
        model_tools.addWidget(self.catalog_button)
        self.region = QLineEdit(trans['region'])
        self.region.setPlaceholderText(tr('例如 eastasia；全局 Translator 资源可留空'))
        self.app_id = QLineEdit(trans.get('app_id', ''))
        self.app_id.setPlaceholderText(tr('百度 APP ID / 有道应用 ID；不是密钥'))
        self.deepl_plan = QComboBox()
        self.deepl_plan.addItem('DeepL API Free', 'free')
        self.deepl_plan.addItem('DeepL API Pro', 'pro')
        self.deepl_plan.setCurrentIndex(self.deepl_plan.findData(trans.get('deepl_plan', 'free')))
        self.deepl_plan.currentIndexChanged.connect(self._deepl_plan_changed)
        self.requires_key = QCheckBox(tr('服务需要 API Key'))
        self.requires_key.setChecked(trans['requires_api_key'])
        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key.setPlaceholderText(tr('留空保留当前密钥') if secret else tr('填写密钥，不会写入普通配置'))
        self.save_key = QCheckBox(tr('使用当前 Windows 用户加密保存'))
        self.save_key.setChecked(trans['save_api_key'])
        self.clear_key = QCheckBox(tr('清除已有密钥'))
        self.mode = QComboBox()
        self.mode.addItem(tr('普通翻译'), 'normal')
        self.mode.addItem(tr('学术翻译'), 'academic')
        self.mode.setCurrentIndex(1 if trans['mode'] == 'academic' else 0)
        self.timeout = NumberEdit()
        self.timeout.setRange(10, 600 if trans['provider'] == 'nvidia' or trans['provider'] in CHAT_PRESETS else 120)
        self.timeout.setSuffix(tr(' 秒'))
        self.timeout.setValue(trans['total_timeout_seconds'])
        self.max_tokens = NumberEdit()
        self.max_tokens.setRange(0, 1048576)
        self.max_tokens.setSingleStep(1024)
        self.max_tokens.setValue(trans.get('max_tokens', 4096))
        self.extra_body = QPlainTextEdit(trans.get('extra_body_json', '{}'))
        self.extra_body.setPlaceholderText('{"chat_template_kwargs": {"enable_thinking": false}}')
        self.extra_body.setMaximumHeight(110)
        self.extra_body.setToolTip(tr('按模型页面示例填写请求体参数。留 {} 使用模型默认值；不要在这里填写密钥。'))
        self.model_defaults = QCheckBox(tr('使用模型卡片初始输出值（可手动修改）'))
        self.model_defaults.setChecked(trans.get('model_defaults', True))
        self.model_hint = label('')
        self.model.textChanged.connect(self._model_defaults_changed)
        self.model_defaults.toggled.connect(self._model_defaults_changed)
        self.max_tokens.textEdited.connect(lambda _: self.model_defaults.setChecked(False))
        self.pin = QCheckBox(tr('结果窗口默认置顶'))
        self.pin.setChecked(config['window']['always_on_top'])
        self.font_size = NumberEdit()
        self.font_size.setMaximumWidth(100)
        self.font_size.setRange(10, 32)
        self.font_size.setValue(config['window']['font_size'])
        self.display_mode = QComboBox()
        self.display_mode.addItem(tr('弹窗显示原文和译文'), 'popup')
        self.display_mode.addItem(tr('截图工作区 · 原位替换（可调选区）'), 'overlay')
        self.display_mode.setCurrentIndex(self.display_mode.findData(config['window'].get('display_mode', 'popup')))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        body_row = QHBoxLayout()
        body_row.setSpacing(8)
        layout.addLayout(body_row)
        self.sidebar = QFrame()
        self.sidebar.setObjectName('settingsSidebar')
        self.sidebar.setFixedWidth(210)
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(12, 24, 12, 20)
        sidebar_layout.setSpacing(12)
        sidebar_layout.addWidget(label('SnapTrans', 'sectionTitle'))
        sidebar_layout.addWidget(label('v' + __version__))
        sidebar_layout.addSpacing(14)
        self.navigation = QListWidget()
        self.navigation.setObjectName('settingsNavigation')
        self.navigation.addItems([tr('截图'), tr('翻译服务'), tr('文字识别'), tr('主题'), tr('学术提示词'), tr('偏好设置')])
        self.navigation.setItemDelegate(NavigationDelegate(self.navigation))
        self.navigation.setMouseTracking(True)
        self.navigation.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        sidebar_layout.addWidget(self.navigation, 1)
        self.appearance_link = QPushButton(tr('主题与外观  →'))
        self.appearance_link.setObjectName('quiet')
        self.appearance_link.clicked.connect(lambda: self.tabs.setCurrentIndex(3))
        sidebar_layout.addWidget(self.appearance_link)
        body_row.addWidget(self.sidebar)
        body = QWidget()
        body.setObjectName('settingsBody')
        body_row.addWidget(body, 1)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(18, 16, 10, 8)
        layout.setSpacing(10)
        heading = QHBoxLayout()
        self.page_title = label(tr('截图'), 'title')
        heading.addWidget(self.page_title, 1)
        self.saved_state = label(tr('已保存'), 'savedState')
        heading.addWidget(self.saved_state)
        self.save_button = save = QPushButton(tr('保存更改'))
        save.setObjectName('primary')
        save.setAutoDefault(False)
        save.clicked.connect(lambda: self._emit(self.save_requested))
        heading.addWidget(save)
        layout.addLayout(heading)
        self.page_description = label(tr('选择截图后的行为，设置顺手的快捷键。'))
        layout.addWidget(self.page_description)
        self.message = InlineMessage()
        self.message.setObjectName('status')
        self.message.setWordWrap(True)
        self.message.setText(key_warning)
        layout.addWidget(self.message)
        self.tabs = QTabWidget()
        self.tabs.setUsesScrollButtons(True)
        self.tabs.tabBar().hide()
        layout.addWidget(self.tabs, 1)
        self.navigation.currentRowChanged.connect(self.tabs.setCurrentIndex)

        def page(title):
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            content = QWidget()
            content.setObjectName('scrollContent')
            column = QVBoxLayout(content)
            column.setContentsMargins(8, 14, 12, 14)
            column.setSpacing(16)
            scroll.setWidget(content)
            self.tabs.addTab(scroll, title)
            return column

        shortcuts = page(tr('截图'))
        capture_card, capture_column = card(tr('截图后自动翻译'))
        capture_card.setProperty('surfaceRole', 'hero')
        capture_action = QHBoxLayout()
        capture_action.addWidget(label(tr('框选完成后识别文字，并显示译文。')), 1)
        self.auto_translate = Toggle(tr('开启自动翻译'))
        self.auto_translate.setFixedSize(48, 32)
        self.auto_translate.setChecked(config.get('capture', {}).get('auto_translate', True))
        capture_action.addWidget(self.auto_translate)
        capture_column.addLayout(capture_action)
        self.capture_summary = label('')
        self.capture_summary.setObjectName('flowSummary')
        capture_column.addWidget(self.capture_summary)
        self.auto_translate.toggled.connect(self._capture_summary)
        self._capture_summary()
        shortcuts.addWidget(capture_card)
        for title, description, control in (
            (tr('截图快捷键'), tr('按上述自动翻译选项打开统一工作区。'), self.translate_hotkey_control),
            (tr('仅截图快捷键'), tr('打开同一工作区，此次仅截图，按需提取或翻译。'), self.ocr_hotkey_control)):
            frame, column = card(title, description)
            column.addWidget(control)
            shortcuts.addWidget(frame)
        shortcuts.addWidget(label(tr('快捷键录入后自动保存。其他偏好在右上角保存。')))
        shortcuts.addStretch()

        services = page(tr('翻译服务'))
        self.service_stack = EngineStack()
        services.addWidget(self.service_stack)
        self.provider_picker = ProviderPicker()
        self.provider_picker.selected.connect(self.select_provider)
        self.provider_picker.back_requested.connect(lambda: self.service_stack.setCurrentIndex(1))
        self.service_stack.addWidget(self.provider_picker)
        detail = QWidget()
        self.service_stack.addWidget(detail)
        services = QVBoxLayout(detail)
        services.setContentsMargins(0, 0, 0, 0)
        services.setSpacing(14)
        self.detail_back_button = QPushButton(tr('← 返回上一级 · 选择服务'))
        self.detail_back_button.clicked.connect(self.return_to_services)
        services.addWidget(self.detail_back_button)
        frame, column = card(tr('翻译引擎'), tr('各引擎分别保留配置，翻译后也能切换。'))
        engine_row = QHBoxLayout()
        self.provider_name = QLabel()
        self.provider_name.setObjectName('sectionTitle')
        self.provider_badge = QLabel()
        engine_row.addWidget(self.provider_badge)
        engine_row.addWidget(self.provider_name, 1)
        self.change_provider_button = QPushButton(tr('修改翻译引擎'))
        self.change_provider_button.clicked.connect(self.show_provider_picker)
        engine_row.addWidget(self.change_provider_button)
        column.addLayout(engine_row)
        self.provider_info = label('')
        column.addWidget(self.provider_info)
        self.open_website_button = QPushButton(tr('打开翻译网页'))
        self.open_website_button.clicked.connect(self.open_translation_website)
        column.addWidget(self.open_website_button)
        services.addWidget(frame)
        frame, column = card(tr('连接与模型'))
        self.connection_title = column.itemAt(0).widget()
        self.service_rows = {}
        for caption, field in ((tr('API 根地址'), self.base_url), (tr('模型名称'), self.model),
                               (tr('DeepL 套餐'), self.deepl_plan), (tr('应用 ID'), self.app_id),
                               ('', self.model_tools),
                               (tr('微软资源区域'), self.region), (tr('翻译模式'), self.mode),
                               (tr('总超时（秒）'), self.timeout), ('', self.requires_key),
                               ('API Key', self.api_key), ('', self.save_key), ('', self.clear_key),
                               (tr('输出上限 tokens'), self.max_tokens), ('', self.model_defaults), ('', self.model_hint), (tr('高级参数 JSON'), self.extra_body)):
            row_widget = QWidget()
            row_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
            row = QHBoxLayout(row_widget)
            row.setContentsMargins(0, 0, 0, 0)
            if caption:
                caption_label = label(caption)
                caption_label.setFixedWidth(95)
                row.addWidget(caption_label)
            row.addWidget(field, 1)
            column.addWidget(row_widget)
            self.service_rows[field] = row_widget
        services.addWidget(frame)
        self.test_button = QPushButton(tr('测试连接'))
        self.test_button.setAutoDefault(False)
        self.test_button.clicked.connect(lambda: self._emit(self.test_requested))
        self.cancel_test_button = QPushButton(tr('取消测试'))
        self.cancel_test_button.setAutoDefault(False)
        self.cancel_test_button.setVisible(False)
        self.cancel_test_button.clicked.connect(self.cancel_test_requested)
        # A contextual test action belongs to the translation service, not every settings page.
        self.service_test_row = QHBoxLayout()
        self.service_test_row.addWidget(self.test_button)
        self.service_test_row.addStretch()
        column.addLayout(self.service_test_row)
        services.addWidget(label(tr('翻译服务接收识别后的文本。若启用云端 OCR，框选图片会另行发送给 OCR 服务。测试连接发送公开短句。')))
        services.addStretch()
        self.service_stack.setCurrentIndex(1)

        frame, column = card(tr('翻译语言'), tr('选择原文和译文语言。切换引擎时沿用；工作区与贴图也可修改。MyMemory 需指定原文语言。'))
        column.addWidget(self.translation_languages)
        services.insertWidget(1, frame)

        recognition = page(tr('文字识别'))
        self.build_ocr_page(recognition, config, ocr_secret_lookup)

        appearance = page(tr('主题'))
        frame, column = card(tr('界面主题'), tr('点击预览。保存后应用到设置、弹窗和工具栏；直接关闭会保留原主题。'))
        self.theme_name = config['window'].get('theme', 'daylight')
        self.theme_buttons = {}
        theme_grid = QGridLayout()
        theme_grid.setSpacing(8)
        for index, (key, (title, description, colors)) in enumerate(THEMES.items()):
            button = QToolButton()
            button.setText(tr(title) + '\n' + tr(description))
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            button.setIcon(theme_preview(colors))
            button.setIconSize(QSize(120, 46))
            button.setCheckable(True)
            button.setChecked(key == self.theme_name)
            button.setMinimumHeight(106)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            button.setProperty('themeExempt', True)
            button.setStyleSheet(f'QToolButton {{background:{colors[0]}; color:{colors[6]}; border:2px solid transparent; border-radius:12px; padding:10px; font-size:12px;}} QToolButton:hover {{border-color:{colors[5]};}} QToolButton:checked {{border-color:{colors[8]};}} QToolButton:focus {{border-color:{colors[8]};}}')
            button.clicked.connect(lambda checked=False, value=key: self.preview_theme(value))
            self.theme_buttons[key] = button
            theme_grid.addWidget(button, index // 2, index % 2)
        column.addLayout(theme_grid)
        appearance.addWidget(frame)
        appearance.addStretch()
        prompts_page = page(tr('学术提示词'))
        self.prompt_editor = PromptEditor(config.get('prompts', {}).get('academic', ACADEMIC))
        self.prompt_editor.save_requested.connect(self.prompt_save_requested)
        prompts_page.addWidget(self.prompt_editor)
        prompts_page.addStretch()
        preferences = page(tr('偏好设置'))
        frame, column = card(tr('默认翻译语言'), tr('提前选择原文和目标语言，保存后用于新的截图翻译。工作区仍可随时切换语言。MyMemory 需指定原文语言。'))
        self.preference_languages = LanguagePair(*self.translation_languages.pair())
        self.preference_languages.changed.connect(self.translation_languages.set_pair)
        self.translation_languages.changed.connect(self.preference_languages.set_pair)
        column.addWidget(self.preference_languages)
        preferences.addWidget(frame)
        frame, column = card(tr('界面语言'), tr('选择后立即切换并自动保存，不改变翻译方向。'))
        self.interface_language = QComboBox()
        from ..i18n import INTERFACE_LANGUAGES, UiText
        choices = [(tr('跟随系统'), 'system')]
        choices.extend((UiText(lambda title=title: title), code) for code, title in INTERFACE_LANGUAGES.items())
        for title, code in choices:
            self.interface_language.addItem(title, code)
        self.interface_language.setCurrentIndex(self.interface_language.findData(config.get('interface', {}).get('language', 'system')))
        column.addWidget(self.interface_language)
        preferences.addWidget(frame)
        frame, column = card(tr('截图翻译的打开方式'), tr('工作区与弹窗内都可继续切换，无需重新截图。'))
        column.addWidget(self.display_mode)
        preferences.addWidget(frame)
        frame, column = card(tr('阅读偏好'), tr('设置窗口正常切换，不会强制置顶。弹窗的“置顶”可随时开关；拖动窗口边缘调整大小。'))
        row = QHBoxLayout()
        row.addWidget(label(tr('原文与译文字号')), 1)
        row.addWidget(self.font_size)
        column.addLayout(row)
        column.addWidget(CheckRow(self.pin))
        preferences.addWidget(frame)
        preferences.addWidget(label(tr('贴图可以拖动、滚轮缩放，并返回工作区继续操作。'), 'status'))
        preferences.addStretch()
        self.open_settings_on_start = QCheckBox(tr('每次启动时打开设置'))
        self.open_settings_on_start.setChecked(config.get('startup', {}).get('open_settings', False))
        frame, column = card(tr('启动与数据'), tr('首次使用会先进入设置。配置、日志与缓存保存在程序目录的 data 文件夹。'))
        column.addWidget(CheckRow(self.open_settings_on_start))
        column.addWidget(label('SnapTrans ' + __version__))
        preferences.insertWidget(preferences.count() - 1, frame)
        layout.insertWidget(3, self.cancel_test_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.base_url.textChanged.connect(self._url_changed)
        self.requires_key.toggled.connect(self._key_state)
        self.provider.currentIndexChanged.connect(lambda: self._provider_changed(True))
        self._provider_changed(False)
        self._model_defaults_changed()
        apply_theme(self, self.theme_name)
        self.setProperty('themeSource', self.property('themeSource') + PREFERENCES_STYLE)
        for frame in self.findChildren(QFrame):
            if frame.objectName() == 'card' and frame.layout():
                frame.layout().setContentsMargins(20, 18, 20, 20)
                elevate(frame, self.theme_name)
        for button in (self.detail_back_button, self.change_provider_button,
                       self.translate_hotkey_control.record_button, self.translate_hotkey_control.manual_button,
                       self.ocr_hotkey_control.record_button, self.ocr_hotkey_control.manual_button):
            button.setObjectName('quiet')
        style_tree(self, self.theme_name)
        self.tabs.currentChanged.connect(self._page_changed)
        self._page_changed(0)
        self._dirty = False
        for widget in self.findChildren(QtWidget):
            if isinstance(widget, QLineEdit) and widget not in (self.translate_hotkey, self.ocr_hotkey):
                widget.textChanged.connect(self.mark_dirty)
            elif isinstance(widget, QCheckBox):
                widget.toggled.connect(self.mark_dirty)
            elif isinstance(widget, QComboBox) and widget is not self.interface_language:
                widget.currentIndexChanged.connect(self.mark_dirty)
            elif isinstance(widget, QSpinBox):
                widget.valueChanged.connect(self.mark_dirty)
            elif widget is self.extra_body:
                widget.textChanged.connect(self.mark_dirty)
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        if screen:
            area = screen.availableGeometry()
            self.resize(min(920, area.width() - 32), min(740, max(380, area.height() - 72)))
        save.setFocus()
        self.interface_language.currentIndexChanged.connect(
            lambda: self.interface_language_requested.emit(self.interface_language.currentData()))
        save.setToolTip(tr('保存全部待保存的偏好 · Ctrl+S；快捷键与学术提示词分别保存'))
        QShortcut(QKeySequence('Ctrl+S'), self, activated=lambda: self._emit(self.save_requested) if self.tabs.currentIndex() != 4 else None)

    def interface_language_saved(self, language, error=''):
        blocked = self.interface_language.blockSignals(True)
        self.interface_language.setCurrentIndex(self.interface_language.findData(language))
        self.interface_language.blockSignals(blocked)
        self.config['interface'] = {'language': language}
        self.message.setText(error or tr('界面语言已自动保存'))

    def mark_dirty(self, *args):
        self._dirty = True
        self.saved_state.setText(tr('未保存'))

    def saved(self, config):
        language_changed = self.config.get('interface') != config.get('interface')
        self.config = deepcopy(config)
        self.profiles = deepcopy(config.get('profiles', {}))
        self.saved_secret = self.api_key.text().strip() or self.saved_secret
        if self.clear_key.isChecked() or not self.requires_key.isChecked():
            self.saved_secret = ''
        self.saved_ocr_secret = self.ocr_secret()
        self.ocr_profiles = deepcopy(config.get('ocr_profiles', {}))
        self._ocr_draft_keys.clear()
        self._ocr_original_target = self._ocr_target()
        self.ocr_key.clear()
        self.ocr_clear_key.setChecked(False)
        self.original_origin = origin(config['translation']['base_url'])
        self._dirty = False
        self.saved_state.setText(tr('已保存 ✓'))
        self.message.setText(tr('界面语言已切换，无需重启。') if language_changed else '')

    def _page_changed(self, index):
        self.navigation.blockSignals(True)
        self.navigation.setCurrentRow(index)
        self.navigation.blockSignals(False)
        self.page_title.setText([tr('截图'), tr('翻译服务'), tr('文字识别'), tr('主题'), tr('学术提示词'), tr('偏好设置')][index])
        self.page_description.setText([tr('选择截图后的行为，设置顺手的快捷键。'),
            tr('选择服务，在这里配置和测试连接。'), tr('选择文字识别方式，默认在本机完成。'),
            tr('选择配色，预览你的工作空间。'), tr('查看和调整学术翻译使用的提示词。'),
            tr('调整阅读、结果显示与启动习惯。')][index])
        self.save_button.setVisible(index != 4)
        self.saved_state.setVisible(index != 4)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        compact = self.width() < 760
        self.sidebar.setVisible(not compact)
        self.tabs.tabBar().setVisible(compact)

    def hotkey_saved(self, action, value, error=''):
        self.config['hotkeys'][action] = value
        field = self.translate_hotkey if action == 'translate' else self.ocr_hotkey
        field.acknowledge(value, error)

    def show_provider_picker(self):
        self.provider_picker.set_current(self.provider.currentData())
        self.provider_picker.show_groups()
        self.service_stack.setCurrentIndex(0)
        QTimer.singleShot(0, self, lambda: self.tabs.widget(1).verticalScrollBar().setValue(0))

    def return_to_services(self):
        from .provider_picker import GROUPS
        key = self.provider_picker.current_group
        if key is None:
            kind = self.provider.currentData()
            key = next((key for key, spec in GROUPS.items() if kind in spec[4]), 'custom')
        self.provider_picker.set_current(self.provider.currentData())
        self.provider_picker.show_group(key)
        self.service_stack.setCurrentIndex(0)
        self.tabs.widget(1).verticalScrollBar().setValue(0)

    def preview_theme(self, name):
        self.theme_name = name
        for key, button in self.theme_buttons.items():
            button.setChecked(key == name)
        style_tree(self, name)
        self.mark_dirty()

    def _capture_summary(self):
        self.capture_summary.setText(tr('当前：截图 → 识别文字 → 自动翻译') if self.auto_translate.isChecked() else tr('当前：截图 → 编辑图片；需要时再点翻译'))

    def select_provider(self, kind):
        self.provider.setCurrentIndex(self.provider.findData(kind))
        if self.provider.currentData() == kind:
            self.service_stack.setCurrentIndex(1)
            QTimer.singleShot(0, self, lambda: self.tabs.widget(1).verticalScrollBar().setValue(0))
            self.message.setText('')
        else:
            self.provider_picker.set_current(self.provider.currentData())

    def show_onboarding(self):
        self.tabs.setCurrentIndex(1)
        self.show_provider_picker()
        self.message.setText(tr('欢迎使用。默认本地 OCR + MyMemory 免费翻译，F2 截图自动翻译。可以保持默认并点击右上角保存，也可选择引擎配置后保存。'))

    def _provider_changed(self, reset):
        kind = self.provider.currentData()
        if reset:
            try:
                self.profiles[self._active_kind] = self._read_translation(self._active_kind)
            except ValueError as error:
                self.provider.blockSignals(True)
                self.provider.setCurrentIndex(self.provider.findData(self._active_kind))
                self.provider.blockSignals(False)
                self.message.setText(ui_format('{}{}', tr('请先填写有效数字再切换服务：'), error))
                return
            values = self.profiles.get(kind, default_profile(kind))
            self._active_kind = kind
            self.api_key.clear()
            self.clear_key.setChecked(False)
            self.saved_secret = ''
            self.original_origin = origin(values['base_url'])
            if self.secret_lookup:
                try:
                    self.saved_secret = self.secret_lookup(values['base_url'])
                except Exception:
                    self.saved_secret = ''
            self.base_url.setText(values['base_url'])
            self.model.blockSignals(True)
            self.model.setText(values['model'])
            self.model.blockSignals(False)
            self.region.setText(values['region'])
            self.app_id.setText(values.get('app_id', ''))
            self.deepl_plan.blockSignals(True)
            self.deepl_plan.setCurrentIndex(self.deepl_plan.findData(values.get('deepl_plan', 'free')))
            self.deepl_plan.blockSignals(False)
            self.requires_key.setChecked(values['requires_api_key'])
            self.save_key.setChecked(values['save_api_key'])
            self.mode.setCurrentIndex(self.mode.findData(values['mode']))
            self.timeout.setRange(10, 600 if kind == 'nvidia' or kind in CHAT_PRESETS else 120)
            self.timeout.setValue(values['total_timeout_seconds'])
            self.max_tokens.setValue(values.get('max_tokens', 4096))
            self.model_defaults.setChecked(values.get('model_defaults', True))
            self.extra_body.setPlainText(values.get('extra_body_json', '{}'))
        traditional = kind in TRADITIONAL
        self.connection_title.setText(tr('网页选项') if kind in WEB_PROVIDERS else tr('连接设置') if traditional else tr('连接与模型'))
        self.service_rows[self.base_url].setVisible(kind not in WEB_PROVIDERS)
        self.open_website_button.setVisible(kind in WEB_PROVIDERS)
        self.provider_name.setText(tr(SERVICES[kind][0]))
        self.provider_badge.setPixmap(service_icon(kind).pixmap(36, 36))
        self.provider_picker.set_current(kind)
        self.model.setEnabled(not traditional)
        self.region.setEnabled(kind == 'microsoft')
        self.base_url.setReadOnly((traditional and kind != 'libre') or kind == 'nvidia')
        self.mode.setEnabled(not traditional)
        self.requires_key.setEnabled((not traditional and kind != 'nvidia') or kind == 'libre')
        if (traditional and kind != 'libre') or kind == 'nvidia':
            if traditional:
                self.mode.setCurrentIndex(0)
            self.requires_key.setChecked(kind not in ('mymemory', *WEB_PROVIDERS))
        for field, visible in ((self.model, not traditional), (self.mode, not traditional),
                               (self.app_id, kind in ('baidu', 'youdao')), (self.deepl_plan, kind == 'deepl'),
                               (self.region, kind == 'microsoft'), (self.requires_key, (not traditional and kind != 'nvidia') or kind == 'libre'),
                               (self.model_tools, kind == 'nvidia'), (self.max_tokens, not traditional),
                               (self.extra_body, not traditional), (self.model_defaults, kind == 'nvidia'), (self.model_hint, kind == 'nvidia')):
            self.service_rows[field].setVisible(visible)
        self.provider_info.setText({
            'mymemory': tr('社区翻译服务，每日可用额度以服务说明为准。'),
            'ollama': tr('本地 · 连接已启动的 Ollama，识别文本留在本机。'),
            'lmstudio': tr('在 LM Studio 下载并加载模型，然后在 Developer 中启动本地服务（默认 1234）。模型名称填已加载的模型 ID；无需云端密钥。'),
            'llamacpp': tr('先运行 llama-server -m 模型.gguf --port 8080，模型名称填服务 /v1/models 返回的 ID。本软件不自动下载或启动模型。'),
            'vllm': tr('先运行 vllm serve 模型 --port 8000，再填写服务返回的模型 ID。通常部署于 Linux / WSL；远程服务使用 HTTPS。'),
            'google_web': tr('在后台网页中翻译，每次最多 5000 字符。需要能访问 Google；验证码或网页变化会停止并提示。可在结果页打开原网页手动处理。'),
            'bing_web': tr('在后台网页中翻译，每次最多 1000 字符。验证码或网页变化会停止并提示。可在结果页打开原网页手动处理。'),
            'baidu_web': tr('后台使用百度翻译网页。每次最多 1000 字符；受网站登录、验证、额度与网页变化影响，无法保证始终免登录。'),
            'youdao_web': tr('后台使用有道普通翻译。每次最多 1000 字符；不使用 AI 对话或会员功能，验证失败时可打开原网页手动处理。'),
            'deepl_web': tr('后台使用 DeepL 翻译网页。每次最多 1000 字符；网站可能要求验证或限制频率，与 DeepL API Free / Pro 独立。'),
            'tencent_web': tr('后台使用腾讯翻译君网页。每次最多 1000 字符；与腾讯混元 API 独立，受网页本身可用性影响。'),
            'compatible': tr('支持兼容聊天接口的服务，填写地址与模型名称。'),
            'nvidia': tr('使用自己的 NVIDIA API Key。选择支持文本对话的模型；目录可见不代表账号有调用权限。思考模型可调整下方输出上限与高级参数。'),
            'google': tr('Google Cloud Translation 官方接口，需自行配置密钥与计费。'),
            'microsoft': tr('Microsoft Translator 官方接口，使用自己的资源密钥。'),
            'deepl': tr('选择与你的 API 密钥一致的 Free / Pro 套餐；切换套餐后需填写对应密钥。'),
            'baidu': tr('开通百度通用文本翻译，填写 APP ID，并在 API Key 中填写应用密钥。'),
            'youdao': tr('开通有道文本翻译，填写应用 ID，并在 API Key 中填写应用密钥。'),
            'libre': tr('开源免费自部署；需先运行 LibreTranslate 并安装英中模型，再填写地址。官方托管站需要付费密钥。'),
            'deepseek': tr('DeepSeek 官方 API，预设非思考翻译；模型可自行修改。'),
            'qwen': tr('阿里云百炼，默认北京地域地址。可改为控制台业务空间专属地址；密钥须与地域一致。'),
            'glm': tr('默认 GLM-4.7-Flash 免费模型，需注册并获取密钥；其他模型可能收费，以账号控制台为准。'),
            'kimi': tr('月之暗面官方 API，默认 Kimi K2.5 非思考模式；修改模型时请核对高级参数。'),
            'siliconflow': tr('硅基流动模型平台。按控制台填写模型 ID；是否免费及限额以所选模型和账号为准。'),
            'openai': tr('OpenAI 官方 API。与 ChatGPT 网页订阅独立；填写平台 API Key 和支持聊天接口的模型。'),
            'gemini': tr('Google AI Studio 的 Gemini API，与 Google Cloud 翻译独立。默认 2.5 Flash 关闭思考；更换为 3 系列时请移除 reasoning_effort: none。'),
            'claude': tr('Anthropic 官方 Messages 接口。填写 Claude Console API Key；输出上限为 0 时使用应用默认 4096。'),
            'grok': tr('xAI 官方 Grok API。填写 API Key 与账号可调用的模型名称。'),
            'doubao': tr('火山方舟。将控制台的模型 ID 或 ep- 开头的推理接入点 ID 填入模型名称，并填写方舟 API Key。'),
            'hunyuan': tr('腾讯混元官方接口。使用混元 API Key，不是腾讯云 SecretId / SecretKey。'),
            'ernie': tr('百度千帆 v2 API，与百度翻译独立。填写千帆 API Key 和已开通的模型 ID。'),
            'minimax': tr('MiniMax 国内官方 API，默认 M3 非思考翻译。更换模型时核对思考参数与输出上限。'),
        }[kind])
        self._key_state()
        self._model_defaults_changed()

    def _read_translation(self, kind):
        values = default_profile(kind)
        values.update(base_url=self.base_url.text().strip(), model=self.model.text().strip(),
                      region=self.region.text().strip(), requires_api_key=self.requires_key.isChecked(),
                      app_id=self.app_id.text().strip(), deepl_plan=self.deepl_plan.currentData(),
                      save_api_key=self.save_key.isChecked(), mode=self.mode.currentData(),
                      total_timeout_seconds=self.timeout.value(), max_tokens=self.max_tokens.value(),
                      extra_body_json=self.extra_body.toPlainText().strip() or '{}',
                      model_defaults=self.model_defaults.isChecked())
        values['source_lang'], values['target_lang'] = self.translation_languages.pair()
        return values

    def open_translation_website(self):
        from ..providers.web_translation import website_url
        kind = self.provider.currentData()
        if kind in WEB_PROVIDERS:
            from ..core.models import AppError
            try:
                QDesktopServices.openUrl(QUrl(website_url(kind, '', *self.translation_languages.pair())))
            except AppError as error:
                self.message.setText(error.user_message)

    def _deepl_plan_changed(self):
        if self.provider.currentData() == 'deepl':
            self.api_key.clear()
            self.base_url.setText(DEEPL_URLS[self.deepl_plan.currentData()])

    def _request_models(self):
        if self.provider.currentData() != 'nvidia':
            return
        secret = self.api_key.text().strip()
        if not secret and origin(self.base_url.text()) == self.original_origin:
            secret = self.saved_secret
        if self.clear_key.isChecked():
            secret = ''
        self.fetch_models_button.setEnabled(False)
        self.message.setText(tr('正在读取 NVIDIA 模型目录…'))
        self.models_requested.emit(secret)

    def _choose_preset(self):
        options = {
            tr('翻译首选 · Nemotron Super'): 'nvidia/nemotron-3-super-120b-a12b',
            tr('翻译备选 · Lightning（关闭思考）'): 'nvidia/nemotron-3.5-lightning-30b-a3b',
            tr('视觉识别模型 · Omni（亦支持文本）'): VISION_MODEL,
        }
        dialog = QInputDialog(self)
        dialog.setWindowTitle(tr('SnapTrans · 实测模型配置'))
        dialog.setLabelText(tr('选择后使用模型卡片初始输出值，并重置高级参数。\n小样本实测仅供参考，效果和等待时间可能变化。'))
        dialog.setComboBoxItems(list(options))
        dialog.setComboBoxEditable(False)
        apply_theme(dialog)
        if dialog.exec():
            self.model_defaults.setChecked(True)
            self.model.setText(options[dialog.textValue()])
            self.extra_body.setPlainText('{}')
            self._model_defaults_changed()

    def show_models(self, models):
        self.fetch_models_button.setEnabled(True)
        if self.provider.currentData() != 'nvidia':
            return
        dialog = QDialog(self)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.setWindowTitle(tr('SnapTrans · NVIDIA 模型'))
        dialog.resize(650, 520)
        layout = QVBoxLayout(dialog)
        layout.addWidget(label(tr('选择 NVIDIA 模型'), 'title'))
        layout.addWidget(label(tr('请选支持文本对话的模型。图像、嵌入、语音模型不能用于此翻译接口；也可关闭后直接填写模型 ID。')))
        search = QLineEdit()
        search.setPlaceholderText(tr('搜索模型 ID…'))
        listing = QListWidget()
        listing.addItems(models)
        listing.setStyleSheet('QListWidget { background: #191d25; color: #edf0f6; border: none; padding: 6px; } QListWidget::item:selected { background: #683d40; }')
        layout.addWidget(search)
        layout.addWidget(listing, 1)
        def filter_models(text):
            for index in range(listing.count()):
                item = listing.item(index)
                item.setHidden(text.casefold() not in item.text().casefold())
        search.textChanged.connect(filter_models)
        choose = QPushButton(tr('使用选中模型'))
        choose.setObjectName('primary')
        def select_model():
            item = listing.currentItem()
            if item and not item.isHidden() and self.provider.currentData() == 'nvidia':
                self.model.setText(item.text())
                dialog.close()
        choose.clicked.connect(select_model)
        listing.itemDoubleClicked.connect(lambda _: select_model())
        layout.addWidget(choose)
        apply_theme(dialog)
        self.model_dialog = dialog
        self.message.setText(ui_format('{}{}{}', tr('已读取 '), len(models), tr(' 个模型 ID；调用权限与参数以模型页面和测试连接结果为准。')))
        dialog.show()

    def _key_state(self, *args):
        required = self.requires_key.isChecked()
        for field in (self.api_key, self.save_key, self.clear_key):
            field.setEnabled(required)
            if hasattr(self, 'service_rows'):
                self.service_rows[field].setVisible(required)
        self._url_changed()

    def _url_changed(self):
        if not self.requires_key.isChecked():
            self.api_key.setPlaceholderText('')
            return
        try:
            changed = origin(self.base_url.text()) != self.original_origin
        except ValueError:
            changed = True
        if changed:
            self.api_key.setPlaceholderText(tr('服务地址已变更，请重新填写密钥'))
        else:
            self.api_key.setPlaceholderText(tr('留空保留当前密钥') if self.saved_secret else tr('填写密钥'))

    def _emit(self, signal):
        try:
            config = deepcopy(self.config)
            config['hotkeys'] = deepcopy(self.config['hotkeys'])
            trans = self._read_translation(self.provider.currentData())
            config['translation'] = trans
            config['ocr'] = self.ocr_values()
            self._remember_ocr()
            config['ocr_profiles'] = deepcopy(self.ocr_profiles)
            config['startup'] = {'open_settings': self.open_settings_on_start.isChecked()}
            config['interface'] = {'language': self.interface_language.currentData()}
            if signal == self.save_requested:
                config['onboarding'] = {'completed': True}
            config['capture'] = {'auto_translate': self.auto_translate.isChecked()}
            config['profiles'] = deepcopy(self.profiles)
            config['profiles'][trans['provider']] = deepcopy(trans)
            config['window'] = {'always_on_top': self.pin.isChecked(), 'font_size': self.font_size.value(),
                                'display_mode': self.display_mode.currentData(), 'theme': self.theme_name}
            config = validate(config)
            secret = self.api_key.text().strip()
            if not secret and origin(trans['base_url']) == self.original_origin:
                secret = self.saved_secret
            if self.clear_key.isChecked() or not self.requires_key.isChecked():
                secret = ''
            signal.emit(config, secret)
        except (ValueError, OSError) as error:
            self.message.setText(str(error))

    def _release(self, result):
        if self._released:
            return
        self._released = True
        self.hotkey_recording.emit(False)
        self.api_key.clear()
        self.saved_secret = ''
        self.saved_ocr_secret = ''
        self.ocr_key.clear()
        self._ocr_draft_keys.clear()
        self.closed.emit()

    def _model_defaults_changed(self, *args):
        if self.provider.currentData() != 'nvidia':
            return
        info = model_card(self.model.text())
        if self.model_defaults.isChecked():
            self.max_tokens.setValue(info['tokens'])
        self.model_hint.setText((ui_format('{}{}。', tr('模型卡片初始值 '), info['tokens']) + (ui_format('{}{}。', tr('官方输出上限 '), info['limit']) if info.get('limit_verified', True) else tr('官方未明确输出硬上限。')) if info['tokens'] else
            tr('尚无已核对的模型默认值；0 表示不传输出限制，由服务决定。')) + tr(' 点击数字可输入。模型卡片与示例不是上下文容量。'))
        self.model_hint.setToolTip(info['url'])

    def prompt_saved(self, text, error=''):
        if not error:
            self.config['prompts'] = {'academic': text}
        self.prompt_editor.saved_result(text, error)

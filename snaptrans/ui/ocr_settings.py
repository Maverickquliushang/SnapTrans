"""OCR service picker and unsaved profiles, shared by the settings shell."""
from ..i18n import tr
from copy import deepcopy
from PySide6.QtCore import QTimer
from .localized_widgets import (QComboBox, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                               QLineEdit, QCheckBox, QLabel)
from .provider_picker import ProviderPicker, EngineStack, service_icon
from .number_edit import NumberEdit
from .theme import card, label
from ..credentials import origin
from ..providers.ocr_catalog import OCR_SERVICES, OCR_GROUPS, default_ocr, validate_ocr, credential_target


class OcrSettingsMixin:
    def build_ocr_page(self, column, config, secret_lookup):
        self.ocr_secret_lookup = secret_lookup
        self.ocr_profiles = deepcopy(config.get('ocr_profiles', {}))
        values = {**default_ocr(config['ocr']['provider']), **config['ocr']}
        self.ocr_profiles[values['provider']] = values
        self._ocr_active = values['provider']
        self._ocr_draft_keys = {}
        self.ocr_provider = QComboBox(self)
        self.ocr_provider.hide()
        for kind, spec in OCR_SERVICES.items():
            self.ocr_provider.addItem(spec[0], kind)
        self.ocr_provider.setCurrentIndex(self.ocr_provider.findData(self._ocr_active))
        self.ocr_stack = EngineStack()
        column.addWidget(self.ocr_stack)
        services = {kind: (spec[0], spec[1], '', '') for kind, spec in OCR_SERVICES.items()}
        self.ocr_picker = ProviderPicker(OCR_GROUPS, services, tr('选择识别引擎'),
                                         {kind: spec[2] for kind, spec in OCR_SERVICES.items()})
        self.ocr_picker.selected.connect(self.select_ocr_provider)
        self.ocr_picker.back_requested.connect(lambda: self.ocr_stack.setCurrentIndex(1))
        self.ocr_stack.addWidget(self.ocr_picker)
        details = QWidget()
        detail = QVBoxLayout(details)
        detail.setContentsMargins(0, 0, 0, 0)
        detail.setSpacing(16)
        self.ocr_stack.addWidget(details)
        back = QPushButton(tr('← 返回识别服务'))
        back.setObjectName('quiet')
        back.clicked.connect(self.return_to_ocr_services)
        detail.addWidget(back)
        frame, layout = card(tr('文字识别'), tr('从截图提取文字，独立于翻译服务。'))
        row = QHBoxLayout()
        self.ocr_badge = QLabel()
        self.ocr_name = label('', 'sectionTitle')
        row.addWidget(self.ocr_badge)
        row.addWidget(self.ocr_name, 1)
        self.change_ocr_button = QPushButton(tr('修改识别引擎'))
        self.change_ocr_button.setObjectName('quiet')
        self.change_ocr_button.clicked.connect(self.show_ocr_picker)
        row.addWidget(self.change_ocr_button)
        layout.addLayout(row)
        self.ocr_description = label('')
        layout.addWidget(self.ocr_description)
        detail.addWidget(frame)
        self.ocr_cloud_card, layout = card(tr('连接与识别'))
        self.ocr_base_url = QLineEdit()
        self.ocr_base_url.setPlaceholderText(tr('https://服务地址/v1 或本地 http://127.0.0.1:端口/v1'))
        self.ocr_model = QComboBox()
        self.ocr_model.setEditable(True)
        self.ocr_model.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.ocr_model.setMinimumContentsLength(12)
        self.ocr_model.lineEdit().setPlaceholderText(tr('填写已加载的视觉模型名称，须支持图片输入'))
        self.ocr_tokens = NumberEdit()
        self.ocr_tokens.setRange(1, 1048576)
        self.ocr_tokens_label = label(tr('输出上限 tokens'))
        self.ocr_timeout = NumberEdit()
        self.ocr_timeout.setRange(10, 600)
        self.ocr_requires_key = QCheckBox(tr('服务需要 API Key'))
        self.ocr_key = QLineEdit()
        self.ocr_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.ocr_save_key = QCheckBox(tr('使用当前 Windows 用户加密保存识别密钥'))
        self.ocr_clear_key = QCheckBox(tr('清除识别密钥'))
        self._ocr_rows = {}
        for caption, field in [(tr('API 根地址'), self.ocr_base_url), (tr('视觉模型'), self.ocr_model),
                               (self.ocr_tokens_label, self.ocr_tokens), (tr('总超时（秒）'), self.ocr_timeout),
                               ('', self.ocr_requires_key), ('API Key', self.ocr_key),
                               ('', self.ocr_save_key), ('', self.ocr_clear_key)]:
            container = QWidget()
            row = QHBoxLayout(container)
            row.setContentsMargins(0, 0, 0, 0)
            if caption:
                caption = label(caption) if isinstance(caption, str) else caption
                caption.setFixedWidth(95)
                row.addWidget(caption)
            row.addWidget(field, 1)
            layout.addWidget(container)
            self._ocr_rows[field] = container
        self.ocr_test_button = QPushButton(tr('测试识别 · Hello 示例图片'))
        self.ocr_test_button.clicked.connect(self._test_ocr)
        layout.addWidget(self.ocr_test_button)
        layout.addWidget(label(tr('测试只发送公开示例图片。识别时只发送框选区域；视觉模型可能漏字或改写，重要内容请核对原图。')))
        detail.addWidget(self.ocr_cloud_card)
        detail.addStretch()
        self.ocr_requires_key.toggled.connect(self._ocr_key_state)
        self.ocr_base_url.textChanged.connect(self._ocr_url_changed)
        self._load_ocr(values)
        self.ocr_provider.currentIndexChanged.connect(self._ocr_provider_changed)
        self.ocr_stack.setCurrentIndex(1)
        column.addStretch()

    def _ocr_target(self):
        return credential_target({'provider': self._ocr_active, 'base_url': self.ocr_base_url.text().strip()})

    def _remember_ocr(self):
        self.ocr_profiles[self._ocr_active] = self.ocr_values()
        # Keys remain in memory until explicit Save, and are cleared on closing settings.
        self._ocr_draft_keys[self._ocr_target()] = (self.ocr_secret(), self.ocr_save_key.isChecked())

    def ocr_key_updates(self):
        self._remember_ocr()
        return [(url, scope, secret, persist) for (url, scope), (secret, persist) in self._ocr_draft_keys.items()
                if url and scope != 'ocr:local']

    def _load_ocr(self, values):
        kind = values['provider']
        spec = OCR_SERVICES[kind]
        self._ocr_active = kind
        self.saved_ocr_secret = ''
        self._ocr_original_target = credential_target(values)
        if self._ocr_original_target in self._ocr_draft_keys:
            self.saved_ocr_secret = self._ocr_draft_keys[self._ocr_original_target][0]
        elif self.ocr_secret_lookup:
            try:
                self.saved_ocr_secret = self.ocr_secret_lookup(values)
            except Exception:
                self.message.setText(tr('无法读取此识别服务的密钥，请重新填写。'))
        self.ocr_key.clear()
        self.ocr_clear_key.setChecked(False)
        self.ocr_name.setText(tr(spec[0]))
        self.ocr_badge.setPixmap(service_icon(spec[2]).pixmap(40, 40))
        local = kind in ('local', 'ollama_vl', 'lmstudio_vl')
        self.ocr_description.setText(tr('离线运行，截图留在本机。附带模型主要识别中文和英文；其他语种建议选择对应的视觉模型。') if kind == 'local' else
            (tr('先在本机加载支持图片的视觉模型，再填写模型名称。') if local else
             tr('框选图片将发送给此服务。识别配置和翻译配置分别保存。')))
        self.ocr_base_url.setText(values['base_url'])
        self.ocr_base_url.setReadOnly(kind in ('nvidia', 'nvidia_vl'))
        self.ocr_model.clear()
        if spec[4]:
            self.ocr_model.addItem(spec[4])
        self.ocr_model.setCurrentText(values['model'])
        self.ocr_tokens.setValue(values['max_tokens'])
        self.ocr_timeout.setValue(values['total_timeout_seconds'])
        self.ocr_save_key.setChecked(values['save_api_key'])
        self.ocr_requires_key.setChecked(values['requires_api_key'])
        self.ocr_requires_key.setEnabled(kind not in ('nvidia', 'nvidia_vl'))
        self.ocr_cloud_card.setVisible(kind != 'local')
        for field in (self.ocr_model, self.ocr_tokens):
            self._ocr_rows[field].setVisible(kind != 'nvidia')
        self._ocr_key_state()
        self.ocr_picker.set_current(kind)

    def _ocr_key_state(self):
        required = self.ocr_requires_key.isChecked()
        for field in (self.ocr_key, self.ocr_save_key, self.ocr_clear_key):
            self._ocr_rows[field].setVisible(required)
        self._ocr_url_changed()

    def _ocr_url_changed(self):
        try:
            url, scope = self._ocr_target()
            old_url, old_scope = self._ocr_original_target
            same = scope == old_scope and origin(url) == origin(old_url)
        except (ValueError, AttributeError):
            same = False
        self.ocr_key.setPlaceholderText(tr('留空保留已保存密钥') if same and self.saved_ocr_secret else tr('填写所选服务的 API Key'))

    def ocr_values(self):
        return dict(provider=self._ocr_active, base_url=self.ocr_base_url.text().strip(),
                    model=self.ocr_model.currentText().strip(), requires_api_key=self.ocr_requires_key.isChecked(),
                    total_timeout_seconds=self.ocr_timeout.value(), max_tokens=self.ocr_tokens.value(),
                    save_api_key=self.ocr_save_key.isChecked())

    def ocr_secret(self):
        if self.ocr_clear_key.isChecked() or not self.ocr_requires_key.isChecked():
            return ''
        if self.ocr_key.text().strip():
            return self.ocr_key.text().strip()
        url, scope = self._ocr_target()
        old_url, old_scope = self._ocr_original_target
        return self.saved_ocr_secret if scope == old_scope and origin(url) == origin(old_url) else ''

    def _ocr_provider_changed(self):
        kind = self.ocr_provider.currentData()
        try:
            self._remember_ocr()
        except ValueError as error:
            self.ocr_provider.blockSignals(True)
            self.ocr_provider.setCurrentIndex(self.ocr_provider.findData(self._ocr_active))
            self.ocr_provider.blockSignals(False)
            self.message.setText(str(error))
            return
        self._load_ocr(self.ocr_profiles.get(kind, default_ocr(kind)))

    def select_ocr_provider(self, kind):
        self.ocr_provider.setCurrentIndex(self.ocr_provider.findData(kind))
        if self.ocr_provider.currentData() == kind:
            self.ocr_stack.setCurrentIndex(1)
            QTimer.singleShot(0, self, lambda: self.tabs.widget(2).verticalScrollBar().setValue(0))

    def show_ocr_picker(self):
        self.ocr_picker.show_groups()
        self.ocr_stack.setCurrentIndex(0)
        self.tabs.widget(2).verticalScrollBar().setValue(0)

    def return_to_ocr_services(self):
        group = next(k for k, spec in OCR_GROUPS.items() if self._ocr_active in spec[4])
        self.ocr_picker.show_group(group)
        self.ocr_stack.setCurrentIndex(0)
        self.tabs.widget(2).verticalScrollBar().setValue(0)

    def _test_ocr(self):
        try:
            settings = validate_ocr(self.ocr_values())
            if settings['requires_api_key'] and not self.ocr_secret():
                raise ValueError(tr('请先填写此识别服务的 API Key'))
            self.ocr_test_requested.emit(settings, self.ocr_secret())
        except ValueError as error:
            self.message.setText(str(error))

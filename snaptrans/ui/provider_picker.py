"""Bundled brand artwork and explicit category / service navigation."""
from ..i18n import tr
from PySide6.QtCore import Qt, Signal, QSize, QRectF
from PySide6.QtGui import QPixmap, QPainter, QColor, QFont, QIcon
from .localized_widgets import QWidget, QGridLayout, QVBoxLayout, QHBoxLayout, QToolButton, QPushButton, QStackedWidget, QSizePolicy
from .theme import label
from ..paths import resource_root

SERVICES = {
    'mymemory': ('MyMemory', '社区翻译服务', 'M', '#a44853'),
    'ollama': ('Ollama', '本地运行 · 自选模型', 'O', '#555d6a'),
    'lmstudio': ('LM Studio', '图形界面 · 本地模型服务', 'LM', '#7265c7'),
    'llamacpp': ('llama.cpp', '轻量本地推理 · GGUF 模型', 'L', '#68847b'),
    'vllm': ('vLLM', '本地 / 自有服务器推理', 'V', '#e17846'),
    'google_web': ('Google 网页', '在线网页翻译', 'G', '#4285c4'),
    'bing_web': ('Bing 网页', '在线网页翻译', 'B', '#328c9d'),
    'baidu_web': ('百度网页', '在线网页翻译', '百', '#426fe2'),
    'youdao_web': ('有道网页', '在线网页翻译', '有', '#d94450'),
    'deepl_web': ('DeepL 网页', '在线网页翻译', 'DL', '#376484'),
    'tencent_web': ('腾讯翻译君', '在线网页翻译', '译', '#4886bf'),
    'nvidia': ('NVIDIA', '云端模型 · 自备 API Key', 'NV', '#658d24'),
    'compatible': ('兼容接口', '自定义地址与模型', 'API', '#6079a8'),
    'google': ('Google Cloud', '官方翻译 · 需配置资源', 'G', '#4285c4'),
    'microsoft': ('Microsoft', '官方翻译 · 需配置资源', 'MS', '#8869a8'),
    'deepl': ('DeepL', 'Free / Pro · 自备密钥', 'DL', '#376484'),
    'baidu': ('百度翻译', '应用 ID + 密钥', '百', '#426fe2'),
    'youdao': ('有道翻译', '应用 ID + 密钥', '有', '#d94450'),
    'libre': ('LibreTranslate', '免费自部署 · 需先启动服务', 'LT', '#3b956b'),
    'deepseek': ('DeepSeek', '官方模型 · 自备密钥', 'DS', '#5579e6'),
    'qwen': ('通义千问', '阿里云百炼 · 自备密钥', 'Q', '#8861d7'),
    'glm': ('智谱 GLM', 'Flash 免费模型 · 需注册密钥', 'GLM', '#4b72ac'),
    'kimi': ('Kimi', '月之暗面 · 自备密钥', 'K', '#626bdc'),
    'siliconflow': ('硅基流动', '模型平台 · 自备密钥', 'SF', '#8e68cb'),
    'openai': ('OpenAI', '官方 API · 自备密钥', 'AI', '#299483'),
    'gemini': ('Google Gemini', 'AI Studio · 自备密钥', 'Gm', '#527ede'),
    'claude': ('Claude', 'Anthropic · 自备密钥', 'C', '#bd8061'),
    'grok': ('Grok', 'xAI · 自备密钥', 'X', '#535761'),
    'doubao': ('豆包', '火山方舟 · 自选接入点', '豆', '#4f95db'),
    'hunyuan': ('腾讯混元', '混元 API Key', '混', '#4886bf'),
    'ernie': ('文心一言', '百度千帆 · API Key', '文', '#3977d7'),
    'minimax': ('MiniMax', '官方 API · 自备密钥', 'MM', '#d0698e'),
}

GROUPS = {
    'free': ('免费服务', '社区服务与开放模型', '免', '#3c9876', ('mymemory', 'glm', 'libre')),
    'web': ('网页翻译', 'Google · Bing · DeepL 等', 'Web', '#378c98', ('google_web', 'bing_web', 'baidu_web', 'youdao_web', 'deepl_web', 'tencent_web')),
    'models': ('大模型', 'OpenAI · Gemini · DeepSeek · 千问等', 'AI', '#5a72b9', ('openai', 'gemini', 'claude', 'deepseek', 'qwen', 'nvidia', 'doubao', 'glm', 'kimi', 'grok', 'hunyuan', 'ernie', 'minimax', 'siliconflow')),
    'translation': ('专业翻译', 'DeepL · 百度 · 有道 · Google', '译', '#a97947', ('deepl', 'baidu', 'youdao', 'google', 'microsoft')),
    'custom': ('本地与自定义', 'Ollama · LM Studio 等', 'API', '#696d85', ('ollama', 'lmstudio', 'llamacpp', 'vllm', 'compatible')),
}


class EngineStack(QStackedWidget):
    def __init__(self):
        super().__init__()
        self.currentChanged.connect(lambda _: self.updateGeometry())

    def sizeHint(self):
        return self.currentWidget().sizeHint() if self.currentWidget() else super().sizeHint()

    def minimumSizeHint(self):
        return self.currentWidget().minimumSizeHint() if self.currentWidget() else super().minimumSizeHint()


def service_icon(kind):
    if kind in GROUPS:
        from .category_icons import category_icon
        return category_icon(kind)
    _, _, text, color = SERVICES[kind] if kind in SERVICES else GROUPS[kind][:4]
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    artwork_kind = {'baidu_web': 'baidu', 'youdao_web': 'youdao', 'deepl_web': 'deepl'}.get(kind, kind)
    artwork = resource_root() / 'assets' / 'providers' / f'{artwork_kind}.svg'
    if artwork.exists():
        from PySide6.QtSvg import QSvgRenderer
        painter.setBrush(QColor('#15171c' if kind == 'kimi' else '#ffffff'))
        painter.drawRoundedRect(QRectF(2, 2, 60, 60), 14, 14)
        renderer = QSvgRenderer(str(artwork))
        renderer.render(painter, QRectF(10, 10, 44, 44))
        painter.end()
        return QIcon(pixmap)
    bitmap = artwork.with_suffix('.png')
    if not bitmap.exists():
        bitmap = artwork.with_suffix('.ico')
    if bitmap.exists():
        painter.setBrush(QColor('#ffffff'))
        painter.drawRoundedRect(QRectF(2, 2, 60, 60), 14, 14)
        painter.drawPixmap(10, 10, 44, 44, QPixmap(str(bitmap)))
        painter.end()
        return QIcon(pixmap)
    painter.setBrush(QColor(color))
    painter.drawRoundedRect(QRectF(2, 2, 60, 60), 16, 16)
    font = QFont('Segoe UI')
    font.setPixelSize(20 if len(text) > 1 else 30)
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(QColor('white'))
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, text)
    painter.end()
    return QIcon(pixmap)


class ProviderPicker(QWidget):
    selected = Signal(str)
    back_requested = Signal()

    def __init__(self, groups=None, services=None, title='选择翻译引擎', icons=None):
        super().__init__()
        self.groups = GROUPS if groups is None else groups
        self.services = SERVICES if services is None else services
        self.title = title
        self.icons = icons or {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        self.current_group = None
        navigation = QHBoxLayout()
        self.groups_back = QPushButton(tr('← 返回服务分类'))
        self.groups_back.clicked.connect(self.show_groups)
        navigation.addWidget(self.groups_back)
        self.back = QPushButton(tr('← 返回当前配置'))
        self.back.clicked.connect(self.back_requested)
        navigation.addWidget(self.back)
        layout.addLayout(navigation)
        self.heading = label(tr('选择翻译引擎'), 'sectionTitle')
        layout.addWidget(self.heading)
        layout.addWidget(label(tr('点击图标配置服务。保存后才会启用；关闭设置将保留原来的配置。')))
        self.group_page = QWidget()
        group_grid = QGridLayout(self.group_page)
        group_grid.setContentsMargins(0, 0, 0, 0)
        group_grid.setSpacing(12)
        self.group_buttons = {}
        for index, (key, spec) in enumerate(self.groups.items()):
            button = self.make_button(key, spec[0], spec[1], category=True)
            button.clicked.connect(lambda checked=False, value=key: self.show_group(value))
            group_grid.addWidget(button, index // 2, index % 2)
            self.group_buttons[key] = button
        layout.addWidget(self.group_page)
        self.service_page = QWidget()
        self.grid = QGridLayout(self.service_page)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(12)
        self.buttons = {}
        for index, (kind, (title, description, _, _)) in enumerate(self.services.items()):
            button = self.make_button(kind, title, description)
            button.setParent(self.service_page)
            button.clicked.connect(lambda checked=False, value=kind: self.selected.emit(value))
            self.buttons[kind] = button
        layout.addWidget(self.service_page)
        layout.addStretch()
        self.show_groups()

    def make_button(self, kind, title, description, category=False):
        button = QToolButton()
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        button.setIcon(service_icon(self.icons.get(kind, kind)))
        button.setIconSize(QSize(60, 60) if category else QSize(42, 42))
        button.setText(tr(title) + '\n' + tr(description))
        button.setCheckable(True)
        button.setMinimumSize(170, 104)
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        button.setStyleSheet('QToolButton { background: #222730; color: #edf0f6; border: 1px solid rgba(127,127,127,22); border-radius: 16px; padding: 14px; font-size: 13px; } QToolButton:hover { background: #39282e; border-color: #ff5148; } QToolButton:checked { background: #39282e; border: 1px solid #ff5148; } QToolButton:focus {border-color: #ff5148;}')
        return button

    def show_groups(self):
        self.current_group = None
        self.heading.setText(tr(self.title) + tr(' · 先选择分类'))
        self.group_page.show()
        self.service_page.hide()
        self.groups_back.hide()
        for button in self.group_buttons.values():
            button.setChecked(False)
        self.updateGeometry()

    def show_group(self, key):
        self.current_group = key
        self.heading.setText(tr(self.groups[key][0]) + tr(' · 选择服务'))
        for button in self.buttons.values():
            self.grid.removeWidget(button)
            button.hide()
        for index, kind in enumerate(self.groups[key][4]):
            self.grid.addWidget(self.buttons[kind], index // 2, index % 2)
            self.buttons[kind].show()
        self.group_page.hide()
        self.service_page.show()
        self.groups_back.show()
        self.updateGeometry()

    def set_current(self, kind):
        for key, button in self.buttons.items():
            button.setChecked(kind == key)

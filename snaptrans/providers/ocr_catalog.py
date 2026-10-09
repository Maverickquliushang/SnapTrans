"""OCR presets. Only the bundled local engine is enabled by default."""
from ..i18n import tr
from .model_cards import VISION_MODEL

# name, description, brand icon, endpoint, model, key required
OCR_SERVICES = {
    'local': ('RapidOCR', '随软件附带 · 离线识别', 'custom', '', VISION_MODEL, False),
    'nvidia': ('NVIDIA OCR', '专用文字检测 · 返回文字坐标', 'nvidia', 'https://ai.api.nvidia.com/v1/cv/nvidia/nemotron-ocr-v2', 'nemotron-ocr-v2', True),
    'nvidia_vl': ('NVIDIA 视觉模型', '读取段落 · 自选视觉模型', 'nvidia', 'https://integrate.api.nvidia.com/v1', VISION_MODEL, True),
    'qwen_vl': ('通义千问 VL', '阿里云百炼 · 视觉识别', 'qwen', 'https://dashscope.aliyuncs.com/compatible-mode/v1', 'qwen-vl-plus', True),
    'glm_vl': ('智谱 GLM 视觉', '支持图片的 GLM 模型', 'glm', 'https://open.bigmodel.cn/api/paas/v4', 'glm-4.6v', True),
    'openai_vl': ('OpenAI 视觉', 'GPT 图像输入 · 提取文字', 'openai', 'https://api.openai.com/v1', 'gpt-4.1-mini', True),
    'gemini_vl': ('Gemini 视觉', 'Google AI · 图像输入', 'gemini', 'https://generativelanguage.googleapis.com/v1beta/openai', 'gemini-3.8-flash', True),
    'ollama_vl': ('Ollama 视觉', '本机服务 · 需加载视觉模型', 'ollama', 'http://127.0.0.1:11434/v1', '', False),
    'lmstudio_vl': ('LM Studio 视觉', '本机服务 · 需加载视觉模型', 'lmstudio', 'http://127.0.0.1:1234/v1', '', False),
    'compatible_vl': ('自定义视觉接口', '兼容 Chat Completions 图像输入', 'compatible', '', '', True),
}
OCR_GROUPS = {
    'custom': ('本地识别', '离线 OCR / 本地视觉模型', '', '', ('local', 'ollama_vl', 'lmstudio_vl')),
    'translation': ('专用 OCR', '检测文字与位置', '', '', ('nvidia',)),
    'models': ('视觉大模型', 'NVIDIA / OpenAI / Gemini / 千问 / GLM', '', '', ('nvidia_vl', 'openai_vl', 'gemini_vl', 'qwen_vl', 'glm_vl')),
    'web': ('自定义接口', '连接自己的视觉模型服务', '', '', ('compatible_vl',)),
}


def default_ocr(kind='local'):
    spec = OCR_SERVICES[kind]
    return dict(provider=kind, base_url=spec[3], model=spec[4], requires_api_key=spec[5],
                total_timeout_seconds=120, max_tokens=1024 if kind == 'local' else 4096, save_api_key=False)


def validate_ocr(value, require_ready=True):
    if not isinstance(value, dict) or value.get('provider') not in OCR_SERVICES:
        raise ValueError(tr('不支持的文字识别服务'))
    result = default_ocr(value['provider'])
    for key, default in result.items():
        item = value.get(key, default)
        if type(item) is not type(default):
            raise ValueError(tr('文字识别配置字段类型错误'))
        result[key] = item.strip() if isinstance(item, str) else item
    kind = result['provider']
    if kind in ('nvidia', 'nvidia_vl'):
        result['base_url'] = OCR_SERVICES[kind][3]
        result['requires_api_key'] = True
    if not 10 <= result['total_timeout_seconds'] <= 600 or not 1 <= result['max_tokens'] <= 1048576:
        raise ValueError(tr('识别超时应为 10–600 秒，输出上限应为 1–1048576 tokens'))
    if kind != 'local':
        if require_ready and (not result['base_url'] or not result['model']):
            raise ValueError(tr('请填写识别服务地址与支持图片输入的模型名称'))
        from .compatible import endpoint_for
        if result['base_url']:
            endpoint_for(result['base_url'])
    return result


def credential_target(settings):
    # Preserve credentials from pre-1.12 NVIDIA OCR. Other OCR keys are kept separate
    # from translation, including when both use the same service origin.
    if settings['provider'] in ('nvidia', 'nvidia_vl'):
        return OCR_SERVICES['nvidia'][3], ''
    return settings.get('base_url', ''), 'ocr:' + settings['provider']


def get_ocr_secret(store, settings):
    if not requires_ocr_key(settings):
        return ''
    url, scope = credential_target(settings)
    return store.get(url, scope=scope) if scope else store.get(url)


def requires_ocr_key(settings):
    return settings['provider'] in ('nvidia', 'nvidia_vl') or settings.get(
        'requires_api_key', default_ocr(settings['provider'])['requires_api_key'])

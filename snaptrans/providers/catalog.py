PROVIDERS = {
    'mymemory': ('MyMemory 翻译', 'https://api.mymemory.translated.net'),
    'compatible': ('大模型兼容接口', ''),
    'ollama': ('Ollama 本地模型', 'http://127.0.0.1:11434/v1'),
    'lmstudio': ('LM Studio 本地模型', 'http://127.0.0.1:1234/v1'),
    'llamacpp': ('llama.cpp 本地模型', 'http://127.0.0.1:8080/v1'),
    'vllm': ('vLLM 本地服务', 'http://127.0.0.1:8000/v1'),
    'google_web': ('Google 网页翻译', 'https://translate.google.com'),
    'bing_web': ('Bing 网页翻译', 'https://www.bing.com'),
    'baidu_web': ('百度网页翻译', 'https://fanyi.baidu.com'),
    'youdao_web': ('有道网页翻译', 'https://fanyi.youdao.com'),
    'deepl_web': ('DeepL 网页翻译', 'https://www.deepl.com'),
    'tencent_web': ('腾讯翻译君网页', 'https://fanyi.qq.com'),
    'nvidia': ('NVIDIA NIM / API Catalog', 'https://integrate.api.nvidia.com/v1'),
    'google': ('Google Cloud 翻译', 'https://translation.googleapis.com'),
    'microsoft': ('微软 Translator', 'https://api.cognitive.microsofttranslator.com'),
    'deepl': ('DeepL 翻译', 'https://api-free.deepl.com'),
    'baidu': ('百度翻译', 'https://fanyi-api.baidu.com'),
    'youdao': ('有道智云翻译', 'https://openapi.youdao.com'),
    'libre': ('LibreTranslate · 自部署免费', 'http://127.0.0.1:5000'),
    'deepseek': ('DeepSeek 官方', 'https://api.deepseek.com/v1'),
    'qwen': ('通义千问 · 百炼', 'https://dashscope.aliyuncs.com/compatible-mode/v1'),
    'glm': ('智谱 GLM', 'https://open.bigmodel.cn/api/paas/v4'),
    'kimi': ('Kimi · 月之暗面', 'https://api.moonshot.cn/v1'),
    'siliconflow': ('硅基流动', 'https://api.siliconflow.cn/v1'),
    'openai': ('OpenAI 官方', 'https://api.openai.com/v1'),
    'gemini': ('Google Gemini', 'https://generativelanguage.googleapis.com/v1beta/openai'),
    'claude': ('Anthropic Claude', 'https://api.anthropic.com/v1'),
    'grok': ('xAI Grok', 'https://api.x.ai/v1'),
    'doubao': ('豆包 · 火山方舟', 'https://ark.cn-beijing.volces.com/api/v3'),
    'hunyuan': ('腾讯混元', 'https://api.hunyuan.cloud.tencent.com/v1'),
    'ernie': ('文心一言 · 百度千帆', 'https://qianfan.baidubce.com/v2'),
    'minimax': ('MiniMax', 'https://api.minimax.cn/v1'),
}

LOCAL_PROVIDERS = ('ollama', 'lmstudio', 'llamacpp', 'vllm')
WEB_PROVIDERS = ('google_web', 'bing_web', 'baidu_web', 'youdao_web', 'deepl_web', 'tencent_web')
TRADITIONAL = ('google', 'microsoft', 'mymemory', 'deepl', 'baidu', 'youdao', 'libre', *WEB_PROVIDERS)
CHAT_PRESETS = {
    'deepseek': ('deepseek-flash', {'thinking': {'type': 'disabled'}}),
    'qwen': ('qwen-plus', {'enable_thinking': False}),
    'glm': ('glm-4.7-flash', {'thinking': {'type': 'disabled'}}),
    'kimi': ('kimi-k2.5', {'thinking': {'type': 'disabled'}}),
    'siliconflow': ('Qwen/Qwen2.5-7B-Instruct', {}),
    'openai': ('gpt-4.1-mini', {}),
    'gemini': ('gemini-2.5-flash', {'reasoning_effort': 'none'}),
    'claude': ('claude-haiku-4-5', {}),
    'grok': ('grok-4.7', {}),
    'doubao': ('', {}),  # Console-issued endpoint or model ID, never a made-up ep- ID.
    'hunyuan': ('hunyuan-turbos-latest', {}),
    'ernie': ('ernie-4.5-turbo-128k', {}),
    'minimax': ('MiniMax-M3', {'thinking': {'type': 'disabled'}}),
}
DEEPL_URLS = {'free': 'https://api-free.deepl.com', 'pro': 'https://api.deepl.com'}


def default_profile(kind):
    from ..core.models import ProviderSettings
    values = dict(vars(ProviderSettings()))
    values.update(provider=kind, base_url=PROVIDERS[kind][1],
                  requires_api_key=kind not in (*LOCAL_PROVIDERS, *WEB_PROVIDERS, 'mymemory', 'libre'))
    if kind in CHAT_PRESETS:
        import json
        model, extra = CHAT_PRESETS[kind]
        values.update(model=model, total_timeout_seconds=120, model_defaults=False,
                      extra_body_json=json.dumps(extra))
    if kind in LOCAL_PROVIDERS:
        values['total_timeout_seconds'] = 120
    if kind in WEB_PROVIDERS:
        values['total_timeout_seconds'] = 75
    if kind == 'nvidia':
        from .model_cards import DEFAULT_MODEL, model_card
        values.update(model=DEFAULT_MODEL, total_timeout_seconds=120, max_tokens=model_card(DEFAULT_MODEL)['tokens'])
    return values


def profile_for(config, kind):
    from copy import deepcopy
    if config['translation']['provider'] == kind:
        return deepcopy(config['translation'])
    profile = deepcopy(config.get('profiles', {}).get(kind, default_profile(kind)))
    for key in ('source_lang', 'target_lang'):
        profile[key] = config['translation'].get(key, profile[key])
    return profile


def is_configured(settings):
    return bool(settings.base_url and (settings.model or settings.provider in TRADITIONAL))

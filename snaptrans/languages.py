"""Application language IDs and explicit service mappings; never infer a Latin language."""
from .i18n import tr
LANGUAGES = {
    'auto': ('自动检测', 'Auto-detect'), 'zh-CN': ('简体中文', 'Simplified Chinese'),
    'zh-TW': ('繁体中文', 'Traditional Chinese'), 'en': ('英语', 'English'),
    'ja': ('日语', 'Japanese'), 'ko': ('韩语', 'Korean'), 'fr': ('法语', 'French'),
    'de': ('德语', 'German'), 'es': ('西班牙语', 'Spanish'), 'pt': ('葡萄牙语', 'Portuguese'),
    'it': ('意大利语', 'Italian'), 'ru': ('俄语', 'Russian'), 'ar': ('阿拉伯语', 'Arabic'),
    'th': ('泰语', 'Thai'), 'vi': ('越南语', 'Vietnamese'), 'id': ('印尼语', 'Indonesian'),
    'hi': ('印地语', 'Hindi'),
}


def language_name(code):
    from .i18n import bilingual
    return bilingual(*LANGUAGES.get(code, (code, code)))


def validate_pair(source, target):
    if source not in LANGUAGES or target not in LANGUAGES or target == 'auto':
        raise ValueError(tr('请选择有效的原文语言和目标语言'))


def service_pair(kind, source, target):
    from .core.models import AppError
    validate_pair(source, target)
    if kind == 'mymemory' and source == 'auto':
        raise AppError('LANGUAGE_UNSUPPORTED', tr('MyMemory 需要明确的原文语言，请手动选择或切换支持自动检测的服务。'))
    if kind in ('youdao_web', 'tencent_web') and (source, target) != ('en', 'zh-CN'):
        raise AppError('LANGUAGE_UNSUPPORTED', tr('此网页入口目前仅支持英译中；其他语言请选择 Google、Bing、百度网页或 API 服务。'))
    mapping = {}
    if kind in ('microsoft', 'bing_web'):
        mapping = {'zh-CN': 'zh-Hans', 'zh-TW': 'zh-Hant', 'auto': 'auto-detect'}
    elif kind in ('baidu', 'baidu_web'):
        mapping = {'zh-CN': 'zh', 'zh-TW': 'cht', 'ja': 'jp', 'ko': 'kor', 'fr': 'fra',
                   'es': 'spa', 'ar': 'ara', 'vi': 'vie'}
    elif kind == 'youdao':
        mapping = {'zh-CN': 'zh-CHS', 'zh-TW': 'zh-CHT'}
    elif kind in ('deepl', 'deepl_web'):
        if source in ('th', 'vi', 'hi') or target in ('th', 'vi', 'hi'):
            raise AppError('LANGUAGE_UNSUPPORTED', tr('当前 DeepL 入口尚未核对该语种，请选择其他服务。'))
        if kind == 'deepl':
            return ('ZH' if source.startswith('zh-') else source.upper(),
                    {'zh-CN': 'ZH-HANS', 'zh-TW': 'ZH-HANT', 'en': 'EN-US', 'pt': 'PT-PT'}.get(target, target.upper()))
        mapping = {'zh-CN': 'zh-Hans', 'zh-TW': 'zh-Hant'}
    elif kind == 'libre':
        mapping = {'zh-CN': 'zh', 'zh-TW': 'zt'}
    return mapping.get(source, source), mapping.get(target, target)

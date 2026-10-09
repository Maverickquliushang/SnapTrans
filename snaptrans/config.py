from .i18n import ui_format
from .i18n import tr
from copy import deepcopy
from datetime import datetime
import json
import os
from pathlib import Path
import tempfile

from .core.models import AppError, ProviderSettings
from .providers.prompts import ACADEMIC
from .providers.model_cards import VISION_MODEL
from .providers.ocr_catalog import default_ocr, validate_ocr
from .providers.catalog import default_profile, PROVIDERS, TRADITIONAL, CHAT_PRESETS, DEEPL_URLS, WEB_PROVIDERS

DEFAULT = {
    'schema_version': 1,
    'hotkeys': {'translate': 'F2', 'ocr': 'Alt+W'},
    'translation': default_profile('mymemory'),
    'profiles': {},
    'ocr': default_ocr(),
    'ocr_profiles': {},
    'onboarding': {'completed': False},
    'startup': {'open_settings': False},
    'interface': {'language': 'system'},
    'capture': {'auto_translate': True},
    'prompts': {'academic': ACADEMIC},
    'window': {'always_on_top': False, 'font_size': 14, 'display_mode': 'overlay', 'theme': 'daylight'},
}


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def validate(config: dict) -> dict:
    if not isinstance(config, dict):
        raise ValueError(tr('配置必须是 JSON 对象'))
    version = config.get('schema_version')
    if type(version) is int and version > 1:
        raise AppError('CONFIG_VERSION', tr('配置来自更新版本，请使用兼容版本；原文件未改动。'))
    if type(version) is not int or version != 1:
        raise ValueError(tr('无效的配置版本'))
    for section in ('hotkeys', 'translation', 'window'):
        if not isinstance(config.get(section), dict):
            raise ValueError(tr('配置节缺失'))
    result = deepcopy(DEFAULT)
    for section in ('hotkeys', 'translation', 'window'):
        for key, default in DEFAULT[section].items():
            # Missing display_mode belongs to legacy popup-only settings.
            fallback = 'popup' if section == 'window' and key == 'display_mode' else default
            value = config[section].get(key, fallback)
            if type(value) is not type(default):
                raise ValueError(tr('配置字段类型错误'))
            result[section][key] = value
    trans = validate_translation(result['translation'])
    result['translation'] = trans
    interface = config.get('interface', DEFAULT['interface'])
    from .i18n import INTERFACE_LANGUAGES
    if not isinstance(interface, dict) or interface.get('language') not in (*INTERFACE_LANGUAGES, 'system'):
        raise ValueError(tr('界面语言无效'))
    result['interface'] = dict(language=interface['language'])
    result['ocr'] = validate_ocr(config.get('ocr', DEFAULT['ocr']))
    ocr_profiles = config.get('ocr_profiles', {})
    if not isinstance(ocr_profiles, dict):
        raise ValueError(tr('识别服务配置格式错误'))
    for kind, profile in ocr_profiles.items():
        if not isinstance(profile, dict) or profile.get('provider') != kind:
            raise ValueError(tr('识别服务配置无效'))
        result['ocr_profiles'][kind] = validate_ocr(profile, require_ready=False)
    for section, key in (('onboarding', 'completed'), ('startup', 'open_settings')):
        value = config.get(section, DEFAULT[section])
        if not isinstance(value, dict) or type(value.get(key)) is not bool:
            raise ValueError(tr('启动偏好格式错误'))
        result[section] = {key: value[key]}
    capture = config.get('capture', DEFAULT['capture'])
    if not isinstance(capture, dict) or type(capture.get('auto_translate', True)) is not bool:
        raise ValueError(tr('自动翻译选项无效'))
    result['capture'] = {'auto_translate': capture.get('auto_translate', True)}
    prompts = config.get('prompts', DEFAULT['prompts'])
    if not isinstance(prompts, dict) or not isinstance(prompts.get('academic'), str) or not 1 <= len(prompts['academic'].strip()) <= 16000:
        raise ValueError(tr('学术提示词应为 1–16000 字符'))
    from .providers.prompts import LEGACY_ACADEMIC
    result['prompts'] = {'academic': ACADEMIC if prompts['academic'].strip() == LEGACY_ACADEMIC else prompts['academic'].strip()}
    profiles = config.get('profiles', {})
    if not isinstance(profiles, dict):
        raise ValueError(tr('翻译引擎配置格式错误'))
    for kind, profile in profiles.items():
        if kind not in PROVIDERS or not isinstance(profile, dict) or profile.get('provider') != kind:
            raise ValueError(tr('翻译引擎配置无效'))
        result['profiles'][kind] = validate_translation(profile)
    if result['window']['display_mode'] not in ('popup', 'overlay'):
        raise ValueError(tr('无效的译文显示方式'))
    if not 10 <= result['window']['font_size'] <= 32:
        raise ValueError(tr('字号必须为 10–32'))
    from .ui.themes import THEMES
    if result['window']['theme'] not in THEMES:
        raise ValueError(tr('未知的界面主题'))
    from .hotkey_format import parse_hotkey
    bindings = [parse_hotkey(v) for v in result['hotkeys'].values()]
    if len(set(bindings)) != 2:
        raise ValueError(tr('两个快捷键不能相同'))
    return result


def validate_translation(value):
    defaults = dict(vars(ProviderSettings()))
    trans = {}
    for key, default in defaults.items():
        item = value.get(key, default)
        if type(item) is not type(default):
            raise ValueError(tr('翻译配置字段类型错误'))
        trans[key] = item
    if trans['provider'] not in PROVIDERS:
        raise ValueError(tr('不支持的翻译服务'))
    if trans['provider'] in TRADITIONAL:
        if trans['provider'] != 'libre':
            trans['base_url'] = PROVIDERS[trans['provider']][1]
            trans['requires_api_key'] = trans['provider'] not in ('mymemory', *WEB_PROVIDERS)
        trans['mode'] = 'normal'
    if trans['deepl_plan'] not in DEEPL_URLS:
        raise ValueError(tr('DeepL 套餐必须为 Free 或 Pro'))
    if trans['provider'] == 'deepl':
        trans['base_url'] = DEEPL_URLS[trans['deepl_plan']]
    max_timeout = 600 if trans['provider'] == 'nvidia' or trans['provider'] in CHAT_PRESETS else 120
    if not 10 <= trans['total_timeout_seconds'] <= max_timeout:
        raise ValueError(ui_format('{}{}{}', tr('总超时必须为 10–'), max_timeout, tr(' 秒')))
    if not 0 <= trans['max_tokens'] <= 1048576:
        raise ValueError(tr('最大输出 tokens 必须为 0–1048576，0 表示使用服务默认'))
    from .providers.nvidia import extra_parameters
    extra_parameters(trans['extra_body_json'])
    if trans['provider'] == 'nvidia':
        trans['base_url'] = PROVIDERS['nvidia'][1]
        trans['requires_api_key'] = True
    if trans['mode'] not in ('normal', 'academic'):
        raise ValueError(tr('无效翻译模式'))
    from .languages import validate_pair
    validate_pair(trans['source_lang'], trans['target_lang'])
    if trans['base_url']:
        from .providers.compatible import endpoint_for
        endpoint_for(trans['base_url'])
    return trans


class ConfigStore:
    def __init__(self, path: Path):
        self.path = path
        self.warning = ''

    def load(self) -> dict:
        if not self.path.exists():
            self.save(DEFAULT)
            return deepcopy(DEFAULT)
        try:
            return validate(json.loads(self.path.read_text(encoding='utf-8')))
        except AppError:
            raise
        except (ValueError, TypeError, KeyError):
            suffix = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
            self.path.replace(self.path.with_suffix(f'.broken-{suffix}.json'))
            self.warning = tr('配置损坏，已保留备份并恢复默认设置。')
            self.save(DEFAULT)
            return deepcopy(DEFAULT)

    def save(self, config: dict) -> None:
        atomic_json(self.path, validate(config))

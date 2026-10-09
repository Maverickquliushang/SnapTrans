from dataclasses import dataclass
from enum import Enum


class State(str, Enum):
    IDLE = 'idle'
    SELECTING = 'selecting'
    RECOGNIZING = 'recognizing'
    TRANSLATING = 'translating'
    COMPLETED = 'completed'
    FAILED = 'failed'


@dataclass(frozen=True)
class CaptureFrame:
    request_id: str
    screen_name: str
    screen_rect_logical: tuple[float, float, float, float]
    selection_rect_logical: tuple[float, float, float, float]
    crop_rect_pixels: tuple[int, int, int, int]
    width_px: int
    height_px: int
    rgb_bytes: bytes


@dataclass(frozen=True)
class OcrLine:
    text: str
    polygon: tuple[tuple[float, float], ...]
    confidence: float | None = None


@dataclass(frozen=True)
class OcrResult:
    request_id: str
    raw_text: str
    lines: list[OcrLine]
    elapsed_ms: float


@dataclass(frozen=True)
class ProviderSettings:
    provider: str = 'compatible'
    base_url: str = ''
    model: str = ''
    region: str = ''
    app_id: str = ''
    deepl_plan: str = 'free'
    requires_api_key: bool = True
    save_api_key: bool = False
    credential_id: str = 'default'
    mode: str = 'normal'
    source_lang: str = 'en'
    target_lang: str = 'zh-CN'
    total_timeout_seconds: int = 45
    max_tokens: int = 4096
    extra_body_json: str = '{}'
    model_defaults: bool = True
    academic_prompt: str = ''


@dataclass(frozen=True)
class TranslationRequest:
    request_id: str
    text: str
    settings_snapshot: ProviderSettings


@dataclass(frozen=True)
class TranslationResult:
    request_id: str
    text: str
    elapsed_ms: float
    finish_reason: str | None = None


class AppError(Exception):
    def __init__(self, code: str, user_message: str, retryable: bool = False):
        from ..i18n import tr
        user_message = tr(user_message)
        super().__init__(user_message)
        self.code = code
        self.user_message = user_message
        self.retryable = retryable

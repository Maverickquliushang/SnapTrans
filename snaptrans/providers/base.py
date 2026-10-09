from typing import Protocol
from ..core.models import TranslationRequest, TranslationResult


class TranslationProvider(Protocol):
    async def translate(self, request: TranslationRequest, api_key: str = '') -> TranslationResult: ...
    async def aclose(self) -> None: ...

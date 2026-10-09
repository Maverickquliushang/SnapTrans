import base64
import json
from pathlib import Path
from urllib.parse import urlsplit

from .config import atomic_json
from .core.models import AppError


def origin(url: str) -> str:
    parts = urlsplit(url)
    port = parts.port or (443 if parts.scheme == 'https' else 80)
    return f'{parts.scheme.lower()}://{(parts.hostname or "").lower()}:{port}'


class CredentialStore:
    def __init__(self, path: Path):
        self.path = path
        self._session: dict[str, str] = {}

    def get(self, url: str, *, scope: str = '') -> str:
        key = origin(url) + ('|' + scope if scope else '')
        if key in self._session:
            return self._session[key]
        if not self.path.exists():
            return ''
        try:
            record = json.loads(self.path.read_text(encoding='utf-8'))
            if 'entries' in record:
                record = record['entries'].get(key, {})
            if record.get('origin') != key or not record.get('ciphertext'):
                return ''
            import win32crypt
            data = base64.b64decode(record['ciphertext'], validate=True)
            secret = win32crypt.CryptUnprotectData(data, None, None, None, 1)[1].decode('utf-8')
            self._session[key] = secret
            return secret
        except Exception:
            raise AppError('KEY_DECRYPT', '无法解密已保存密钥，请重新填写（可能更换了 Windows 用户或机器）。') from None

    def save(self, url: str, secret: str, persist: bool, *, scope: str = '') -> None:
        key = origin(url) + ('|' + scope if scope else '')
        record: dict = {}
        if persist and secret:
            import win32crypt
            encrypted = win32crypt.CryptProtectData(secret.encode('utf-8'), 'SnapTrans', None, None, None, 1)
            record = {'origin': key, 'ciphertext': base64.b64encode(encrypted).decode('ascii')}
        existing = {}
        if self.path.exists():
            try:
                stored = json.loads(self.path.read_text(encoding='utf-8'))
                existing = stored.get('entries', {})
                if stored.get('origin'):
                    existing[stored['origin']] = stored
            except (OSError, ValueError):
                existing = {}
        if record:
            existing[key] = record
        else:
            existing.pop(key, None)
        atomic_json(self.path, {'entries': existing})
        self._session[key] = secret

    def clear_session(self) -> None:
        self._session.clear()

    def snapshot(self):
        return (json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else None,
                dict(self._session))

    def restore(self, snapshot):
        record, session = snapshot
        if record is None:
            self.path.unlink(missing_ok=True)
        else:
            atomic_json(self.path, record)
        self._session = session

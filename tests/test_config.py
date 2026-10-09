from copy import deepcopy
import json
import pytest
from snaptrans.config import DEFAULT, ConfigStore, validate
from snaptrans.core.models import AppError
from snaptrans.credentials import CredentialStore


def test_default_and_round_trip(tmp_path):
    store = ConfigStore(tmp_path / 'config.json')
    assert store.load() == DEFAULT
    edited = deepcopy(DEFAULT)
    edited['window']['font_size'] = 19
    store.save(edited)
    assert store.load() == edited


def test_corrupt_config_is_backed_up(tmp_path):
    path = tmp_path / 'config.json'
    path.write_text('{broken', encoding='utf-8')
    store = ConfigStore(path)
    assert store.load() == DEFAULT
    assert list(tmp_path.glob('*.broken-*.json'))
    assert store.warning


def test_newer_config_is_never_overwritten(tmp_path):
    path = tmp_path / 'config.json'
    original = '{"schema_version": 2}'
    path.write_text(original)
    with pytest.raises(AppError):
        ConfigStore(path).load()
    assert path.read_text() == original


@pytest.mark.parametrize('value', ['45', True, 200, 0])
def test_bad_timeout(value):
    config = deepcopy(DEFAULT)
    config['translation']['total_timeout_seconds'] = value
    with pytest.raises(ValueError):
        validate(config)


def test_dpapi_and_origin_binding(tmp_path):
    path = tmp_path / 'credentials.json'
    store = CredentialStore(path)
    store.save('https://example.com/v1', 'synthetic-test-key', True)
    assert 'synthetic-test-key' not in path.read_text()
    reopened = CredentialStore(path)
    assert reopened.get('https://example.com/v2') == 'synthetic-test-key'
    assert reopened.get('https://different.example/v1') == ''
    reopened.save('https://example.com/v1', 'session-only', False)
    assert CredentialStore(path).get('https://example.com/v1') == ''

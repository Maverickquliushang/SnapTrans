import hashlib
import json
import pytest
from snaptrans.core.models import AppError
from snaptrans.core.ocr_adapter import verify_models


@pytest.mark.parametrize('failure', ['missing', 'corrupt', 'traversal', 'config'])
def test_bad_model_assets_fail_before_engine_import(tmp_path, failure):
    root = tmp_path / 'ocr'
    root.mkdir()
    data = b'synthetic model bytes'
    (root / 'model.onnx').write_bytes(data)
    (root / 'config.yaml').write_bytes(b'config')
    item = {'path': 'model.onnx', 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    manifest = {'models': [item.copy() for _ in range(3)],
                'config_sha256': hashlib.sha256(b'config').hexdigest()}
    if failure == 'missing':
        (root / 'model.onnx').unlink()
    elif failure == 'corrupt':
        (root / 'model.onnx').write_bytes(b'x' * len(data))
    elif failure == 'traversal':
        (tmp_path / 'outside.onnx').write_bytes(data)
        manifest['models'][0]['path'] = '../outside.onnx'
    else:
        (root / 'config.yaml').write_bytes(b'changed')
    (root / 'manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(AppError) as raised:
        verify_models(root)
    assert raised.value.code == 'MODEL_ASSETS'

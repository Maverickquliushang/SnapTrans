import hashlib
import json
import os
from pathlib import Path
import time
from .models import AppError, OcrLine, OcrResult


def verify_models(root: Path):
    try:
        manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
        if len(manifest['models']) != 3:
            raise ValueError('invalid model list')
        for item in manifest['models']:
            path = (root / item['path']).resolve()
            if not path.is_relative_to(root.resolve()):
                raise ValueError('invalid resource path')
            if path.stat().st_size != item['size'] or hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
                raise ValueError('checksum mismatch')
        if hashlib.sha256((root / 'config.yaml').read_bytes()).hexdigest() != manifest['config_sha256']:
            raise ValueError('config checksum mismatch')
        return manifest
    except (OSError, ValueError, KeyError, TypeError):
        raise AppError('MODEL_ASSETS', 'OCR 模型缺失或损坏，请重新解压完整软件包。') from None


class OcrAdapter:
    def __init__(self, root: Path):
        manifest = verify_models(root)
        from rapidocr import RapidOCR
        # No runtime download is permitted, including optional dictionary/font paths.
        from rapidocr.utils.download_file import DownloadFile
        def blocked_download(*args, **kwargs):
            raise AppError('MODEL_DOWNLOAD', '离线 OCR 资源不完整，请重新准备模型。')
        DownloadFile.run = staticmethod(blocked_download)
        params = {f'{item["role"]}.model_path': str((root / item['path']).resolve()) for item in manifest['models']}
        params.update({'EngineConfig.onnxruntime.intra_op_num_threads': min(4, os.cpu_count() or 1),
                       'EngineConfig.onnxruntime.inter_op_num_threads': 1,
                       'Global.model_root_dir': str((root / 'models').resolve())})
        self.engine = RapidOCR(config_path=str(root / 'config.yaml'), params=params)

    def recognize(self, frame):
        import numpy as np
        started = time.perf_counter()
        image = np.frombuffer(frame.rgb_bytes, dtype=np.uint8).reshape(frame.height_px, frame.width_px, 3)
        output = self.engine(image[:, :, ::-1].copy())
        lines = []
        if output.txts:
            for text, box, score in zip(output.txts, output.boxes, output.scores):
                polygon = tuple((float(point[0]), float(point[1])) for point in box)
                lines.append(OcrLine(text, polygon, float(score)))
        return OcrResult(frame.request_id, '\n'.join(line.text for line in lines), lines,
                         (time.perf_counter() - started) * 1000)

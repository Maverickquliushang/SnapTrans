import importlib.metadata as metadata
from pathlib import Path
import shutil
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
destination = ROOT / 'licenses'
destination.mkdir(exist_ok=True)
for distribution in metadata.distributions():
    name = distribution.metadata.get('Name', 'unknown')
    target = destination / name
    target.mkdir(exist_ok=True)
    (target / 'METADATA.txt').write_text(distribution.read_text('METADATA') or '', encoding='utf-8')
    for item in distribution.files or []:
        if any(marker in Path(item).name.lower() for marker in ('license', 'copying', 'notice')):
            source = Path(distribution.locate_file(item))
            if source.is_file():
                filename = str(item).replace('/', '_').replace('\\', '_')
                # Keep Windows paths short; distinct hashes avoid filename collisions.
                import hashlib
                filename = hashlib.sha256(str(item).encode()).hexdigest()[:8] + '-' + source.name
                shutil.copyfile(source, target / filename)
for source in (ROOT / 'assets' / 'ocr' / 'licenses').iterdir():
    shutil.copyfile(source, destination / source.name)
for name, url in {
    'ANTLR-LICENSE.txt': 'https://raw.githubusercontent.com/antlr/antlr4/4.9.3/LICENSE.txt',
    'LGPL-3.0.txt': 'https://raw.githubusercontent.com/qt/qtbase/6.11/LICENSES/LGPL-3.0-only.txt',
    'GPL-3.0.txt': 'https://raw.githubusercontent.com/qt/qtbase/6.11/LICENSES/GPL-3.0-only.txt',
}.items():
    target = destination / name
    if not target.exists():
        with urllib.request.urlopen(url, timeout=30) as response:
            target.write_bytes(response.read())
for source in (Path(sys.base_prefix) / 'LICENSE.txt', Path(sys.base_prefix) / 'LICENSE'):
    if source.exists():
        shutil.copyfile(source, destination / 'Python-LICENSE.txt')
print('Collected dependency and model licenses.')

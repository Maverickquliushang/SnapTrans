"""Build upstream's small pure-Python ANTLR dependency at a short project path."""
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import urllib.request

temp = Path(os.environ['TEMP']) / 'antlr'
wheels = Path(os.environ['PIP_CACHE_DIR']).parent / 'wheels'
wheels.mkdir(parents=True, exist_ok=True)
if not list(wheels.glob('antlr4_python3_runtime-4.9.3-*.whl')):
    with urllib.request.urlopen('https://pypi.org/pypi/antlr4-python3-runtime/4.9.3/json', timeout=30) as response:
        metadata = json.load(response)
    source = next(item for item in metadata['urls'] if item['packagetype'] == 'sdist')
    with urllib.request.urlopen(source['url'], timeout=60) as response:
        archive = response.read()
    if hashlib.sha256(archive).hexdigest() != source['digests']['sha256']:
        raise RuntimeError('Upstream archive checksum mismatch')
    temp.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(archive), mode='r:gz') as bundle:
        for item in bundle.getmembers():
            components = Path(item.name).parts[1:]
            if not components:
                continue
            item.name = str(Path(*components))
            bundle.extract(item, temp, filter='data')
    subprocess.run([sys.executable, 'setup.py', 'bdist_wheel', '--dist-dir', str(wheels)],
                   cwd=temp, check=True)
print(wheels)

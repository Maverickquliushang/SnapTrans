"""Inspect distributable files without logging credential values or private paths."""
import argparse
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]
KEYS = re.compile(rb'(?:nvapi-[A-Za-z0-9_-]{20,}|sk-(?:proj-|ant-)?[A-Za-z0-9_-]{30,}|gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|AIza[A-Za-z0-9_-]{30,})')
PRIVATE_FILES = {'credentials.json', 'app.log', 'cookies', 'login data', '.env'}
# Chromium explicitly publishes this frontend CrUX identifier, not a user secret.
# Source: github.com/ChromeDevTools/devtools-frontend/blob/main/front_end/models/crux-manager/CrUXManager.ts
# Scope the exception to the exact digest AND the bundled upstream resource.
PUBLIC_CRUX_HASH = '431da6019dba7ceec802b3b4fe7ca97c5dfe4c7e36341a23489e5aa585955b6a'


def private_markers():
    # Read the current build location, never embed it in the audit's source.
    names = [str(ROOT)]
    if os.environ.get('USERPROFILE'):
        names.append(os.environ['USERPROFILE'])
    if (ROOT.parents[1]/'project-env.ps1').is_file():
        names.append(str(ROOT.parents[1]))
    markers = set()
    for value in names:
        for variant in (value, value.replace('\\', '/'), value.replace('\\', '\\\\')):
            for encoding in ('utf-8', 'utf-16-le'):
                markers.add(variant.lower().encode(encoding))
    return markers


def audit_files(entries):
    markers = private_markers()
    failures, upstream, count = [], [], 0
    def inspect(name, data, depth=0):
        nonlocal count
        count += 1
        lower = data.lower()
        reasons = []
        if Path(name).name.lower() in PRIVATE_FILES:
            reasons.append('private runtime filename')
        for match in KEYS.finditer(data):
            if (name.replace('\\', '/').endswith('/PySide6/resources/qtwebengine_devtools_resources.debug.pak')
                    and hashlib.sha256(match.group()).hexdigest() == PUBLIC_CRUX_HASH):
                upstream.append({'file': name, 'reason': 'Published Chromium frontend identifier', 'sha256': PUBLIC_CRUX_HASH})
            else:
                reasons.append('credential-shaped literal')
        if any(marker in lower for marker in markers):
            reasons.append('local build or user path')
        if reasons:
            failures.append({'file': name, 'reasons': reasons})
        if depth < 3 and name.lower().endswith('.zip'):
            with zipfile.ZipFile(BytesIO(data)) as archive:
                for item in archive.infolist():
                    if not item.is_dir():
                        inspect(name+'!/'+item.filename, archive.read(item), depth+1)
    for name, data in entries:
        inspect(name, data)
    return {'ok': not failures, 'files_checked': count, 'findings': failures, 'public_upstream_identifiers': upstream}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('path', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    if args.path.is_dir():
        entries = ((p.relative_to(args.path).as_posix(), p.read_bytes())
                   for p in args.path.rglob('*') if p.is_file())
        result = audit_files(entries)
    else:
        with zipfile.ZipFile(args.path) as archive:
            result = audit_files((i.filename, archive.read(i)) for i in archive.infolist() if not i.is_dir())
    if args.report:
        args.report.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result))
    if not result['ok']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()

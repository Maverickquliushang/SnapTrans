"""Check decompressed Python code in our PyInstaller executable before publication."""
import argparse
import json
from pathlib import Path
from PyInstaller.archive.readers import CArchiveReader
from audit_public_release import audit_files


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('executable', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    archive = CArchiveReader(str(args.executable))
    def entries():
        for name, info in archive.toc.items():
            if info[-1] == 'z':
                embedded = archive.open_embedded_archive(name)
                for module in embedded.toc:
                    data = embedded.extract(module, raw=True)
                    if data:
                        yield module, data
            elif info[-1] == 's':
                yield name, archive.extract(name)
    result = audit_files(entries())
    if args.report:
        args.report.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result))
    if not result['ok']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()

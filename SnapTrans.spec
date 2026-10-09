# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import hashlib
import shutil
import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, copy_metadata

root = Path(SPECPATH)
# Resolve system DLLs from Windows, not unrelated tools injected into PATH.
# In particular, Qt's Windows ICU API is incompatible with Poppler's icuuc.dll.
windows = Path(os.environ['SystemRoot'])
os.environ['PATH'] = os.pathsep.join(str(p) for p in (
    Path(sys.executable).parent, Path(sys.base_prefix),
    windows / 'System32', windows, windows / 'System32' / 'Wbem'))
license_archive = shutil.make_archive(str(root / '.tmp' / 'third-party-licenses'), 'zip', root / 'licenses')
datas = [(str(root / 'assets'), 'assets'),
         (str(root / 'THIRD_PARTY_NOTICES.md'), '.'),
         (license_archive, 'licenses')]
datas += collect_data_files('rapidocr', includes=['*.yaml'])
datas += copy_metadata('rapidocr') + copy_metadata('onnxruntime')
binaries = collect_dynamic_libs('onnxruntime')
a = Analysis([str(root / 'main.py')], pathex=[str(root)], binaries=binaries, datas=datas,
             hiddenimports=['onnxruntime', 'win32crypt', 'rapidocr.inference_engine.onnxruntime',
                            'PIL._tkinter_finder'],
             excludes=['torch', 'tensorflow', 'paddle', 'openvino', 'matplotlib', 'tkinter',
                       'PySide6.QtQml', 'PySide6.QtQuick',
                       'rapidocr.inference_engine.pytorch',
                       'rapidocr.inference_engine.tensorrt', 'rapidocr.inference_engine.mnn',
                       'rapidocr.inference_engine.openvino', 'rapidocr.inference_engine.paddle'],
             noarchive=False)
pyz = PYZ(a.pure)
# Widgets does not use Qt's optional PDF reader or virtual keyboard. Their
# plugins otherwise pull in PDF/QML/Quick modules and unrelated licensing.
unused_qt = {'Qt6Pdf.dll', 'Qt6VirtualKeyboard.dll',
             'qpdf.dll', 'qtvirtualkeyboardplugin.dll'}
a.binaries = [(name, source, kind) for name, source, kind in a.binaries
              if not (name.replace('\\', '/').startswith('PySide6/')
                      and Path(source).name in unused_qt)]
# License texts also exist in our archive; flatten hook-provided copies to stay
# below Windows' legacy path limit in this unusually deep project directory.
a.datas = [(('licenses/' + hashlib.sha256(name.encode()).hexdigest()[:12] + '.txt')
            if '.dist-info/licenses/' in name.replace('\\', '/') else name, source, kind)
           for name, source, kind in a.datas]
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='SnapTrans', debug=False,
          bootloader_ignore_signals=False, strip=False, upx=False, console=False,
          icon=str(root / 'assets' / 'icon.ico'))
collection = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='SnapTrans')

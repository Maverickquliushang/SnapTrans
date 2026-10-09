import os
from pathlib import Path
from PySide6.QtGui import QFontDatabase, QFont


def initialize_fonts(app):
    directory = Path(os.environ['WINDIR']) / 'Fonts'
    for name in ('msyh.ttc', 'msyhbd.ttc', 'segoeui.ttf'):
        path = directory / name
        if path.is_file():
            QFontDatabase.addApplicationFont(str(path))
    app.setFont(QFont('Microsoft YaHei', 10))

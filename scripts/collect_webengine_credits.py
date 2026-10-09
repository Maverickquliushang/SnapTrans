"""Extract notices from the exact bundled Chromium build, entirely offline."""
from pathlib import Path
from PySide6.QtCore import QCoreApplication, Qt, QTimer, QUrl, QEvent
QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
from PySide6.QtWidgets import QApplication
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile

ROOT = Path(__file__).resolve().parents[1]
app = QApplication([])
profile = QWebEngineProfile()
page = QWebEnginePage(profile)
result = []
def save(html):
    if len(html) > 10000 and ('Chromium' in html or 'chromium' in html):
        destination = ROOT / 'licenses' / 'QtWebEngine-Chromium-credits.html'
        destination.write_text(html, encoding='utf-8')
        result.append(True)
        print(f'Bundled Chromium notices: {len(html)} characters')
    else:
        print('Credits page could not be extracted:', page.url().toString(), len(html), html[:180])
    app.quit()
page.loadFinished.connect(lambda ok: page.toHtml(save))
page.setUrl(QUrl('chrome://credits'))
QTimer.singleShot(20000, app.quit)
app.exec()
page.deleteLater()
QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
raise SystemExit(0 if result else 1)

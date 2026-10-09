"""Public-phrase diagnostic comparing website readiness; never logs URL queries."""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PySide6.QtCore import Qt, QCoreApplication, QTimer
QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
from PySide6.QtWidgets import QApplication
from snaptrans.providers.web_translation import WebTranslationService
from snaptrans.providers.catalog import default_profile
from snaptrans.core.models import ProviderSettings, TranslationRequest
app = QApplication([]); app.setQuitOnLastWindowClosed(False)
service = WebTranslationService()
values = default_profile('tencent_web')
service.submit(TranslationRequest('diagnostic', 'Hello. This is a translation test.', ProviderSettings(**values)))
def diagnostic():
    job = service.jobs.get('diagnostic')
    if job:
        job['page'].runJavaScript("JSON.stringify({body:document.body?.innerText,requests:performance.getEntriesByType('resource').filter(x=>['fetch','xmlhttprequest'].includes(x.initiatorType)).map(x=>({url:new URL(x.name).origin+new URL(x.name).pathname,status:x.responseStatus,duration:Math.round(x.duration)}))})", print)
def finish(*args):
    print(args); service.close(); QTimer.singleShot(500, app.quit)
service.succeeded.connect(finish)
service.failed.connect(finish)
QTimer.singleShot(22000, diagnostic)
app.exec()

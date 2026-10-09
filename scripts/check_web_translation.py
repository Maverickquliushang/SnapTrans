"""Live public-phrase website probes. No account or API keys are used."""
from pathlib import Path
import json
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PySide6.QtCore import QCoreApplication, Qt, QTimer
QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
from PySide6.QtWidgets import QApplication
from snaptrans.providers.web_translation import WebTranslationService
from snaptrans.providers.catalog import default_profile, WEB_PROVIDERS
from snaptrans.core.models import ProviderSettings, TranslationRequest


def run():
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    service = WebTranslationService()
    results = {}
    kinds = list(WEB_PROVIDERS) if '--all' in sys.argv else ['google_web', 'bing_web']
    if '--only' in sys.argv:
        kinds = [sys.argv[sys.argv.index('--only') + 1]]
    pending = list(kinds)
    def start_next():
        if pending:
            kind = pending.pop(0)
            values = default_profile(kind)
            values['total_timeout_seconds'] = 75
            service.submit(TranslationRequest(kind, 'Hello. This is a translation test.', ProviderSettings(**values)))
    def finish(kind, status, detail):
        if status == 'passed' and not any('\u4e00' <= c <= '\u9fff' for c in detail):
            status = 'invalid_result'
        results[kind] = {'status': status, 'detail': detail}
        print(kind, status, detail, flush=True)
        if len(results) == len(kinds):
            QTimer.singleShot(500, app.quit)
        else:
            QTimer.singleShot(500, start_next)
    service.succeeded.connect(lambda result: finish(result.request_id, 'passed', result.text))
    service.failed.connect(lambda kind, code, message: finish(kind, code, message))
    start_next()
    if '--diagnostic' in sys.argv:
        def inspect():
            for kind, job in service.jobs.items():
                job['page'].runJavaScript("JSON.stringify({url:location.origin+location.pathname,title:document.title,body:document.body?.innerText.slice(-2500),inputs:Array.from(document.querySelectorAll('textarea,[contenteditable],#tta_output_ta,#tta_input_ta,[role=textbox]')).map(x=>({id:x.id,value:x.value,text:x.innerText,html:x.outerHTML.slice(0,1000)})),results:Array.from(document.querySelectorAll('[jsname=W297wb]')).map(x=>x.innerText)})", lambda value, k=kind: print(k, value, flush=True))
        QTimer.singleShot(18000, inspect)
    app.exec()
    output = ROOT / '.tmp' / 'web-translation-probe.json'
    output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    service.close()
    QCoreApplication.sendPostedEvents(None, 52)
    return 0


if __name__ == '__main__':
    raise SystemExit(run())

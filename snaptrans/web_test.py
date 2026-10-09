"""Opt-in packaged-browser verification with public text only."""
def run(report_path):
    if not report_path:
        return 2
    from pathlib import Path
    import json
    from PySide6.QtCore import QTimer, QCoreApplication, QEvent
    from PySide6.QtWidgets import QApplication
    from .providers.web_translation import WebTranslationService
    from .providers.catalog import WEB_PROVIDERS, default_profile
    from .core.models import TranslationRequest, ProviderSettings
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    service = WebTranslationService()
    pending = list(WEB_PROVIDERS)
    results = {}
    path = Path(report_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    def next_request():
        if not pending:
            service.close()
            QTimer.singleShot(300, app.quit)
            return
        kind = pending.pop(0)
        settings = default_profile(kind)
        settings['total_timeout_seconds'] = 75
        service.submit(TranslationRequest(kind, 'Hello. This is a translation test.', ProviderSettings(**settings)))
    def finish(kind, status, text):
        results[kind] = {'status': status, 'detail': text}
        path.write_text(json.dumps({'complete': not pending, 'results': results}, ensure_ascii=False, indent=2), encoding='utf-8')
        QTimer.singleShot(300, next_request)
    def success(result):
        status = 'passed' if any('\u4e00' <= char <= '\u9fff' for char in result.text) else 'invalid_result'
        finish(result.request_id, status, result.text)
    service.succeeded.connect(success)
    service.failed.connect(finish)
    QTimer.singleShot(0, next_request)
    app.exec()
    service.close()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    return 0 if len(results) == len(WEB_PROVIDERS) and all(v['status'] == 'passed' for v in results.values()) else 1

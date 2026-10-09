from ..i18n import ui_format
"""Opt-in website translation, using an isolated Qt browser on the GUI thread.

No API credentials, private endpoints, personal browser profile, login automation,
or CAPTCHA bypass. Read the result rendered by the selected public website.
"""
from ..i18n import tr
import json
import time
from urllib.parse import urlencode, urlsplit, quote
from PySide6.QtCore import QObject, Signal, QTimer, QUrl
from ..core.models import TranslationResult

LIMITS = {'google_web': 5000, 'bing_web': 1000, 'baidu_web': 1000, 'youdao_web': 1000, 'deepl_web': 1000, 'tencent_web': 1000}
HOSTS = {'google_web': 'translate.google.com', 'bing_web': 'www.bing.com',
         'baidu_web': 'fanyi.baidu.com', 'youdao_web': 'fanyi.youdao.com',
         'deepl_web': 'www.deepl.com', 'tencent_web': 'fanyi.qq.com'}


def website_url(kind, text, source_lang='en', target_lang='zh-CN'):
    from ..languages import service_pair
    source, target = service_pair(kind, source_lang, target_lang)
    if kind == 'google_web':
        return 'https://translate.google.com/?' + urlencode({'sl': source, 'tl': target, 'text': text, 'op': 'translate'})
    if kind == 'bing_web':
        return 'https://www.bing.com/translator?' + urlencode({'from': source, 'to': target, 'text': text})
    if kind == 'baidu_web':
        return 'https://fanyi.baidu.com/mtpe-individual/multimodal?' + urlencode({'query': text, 'lang': source + '2' + target})
    if kind == 'deepl_web':
        return 'https://www.deepl.com/en/translator#' + source + '/' + target + '/' + quote(text, safe='')
    if kind == 'youdao_web':
        return 'https://fanyi.youdao.com/index.html#/TextTranslate'
    if kind == 'tencent_web':
        return 'https://fanyi.qq.com/'
    raise ValueError(tr('未知网页翻译服务'))


def extraction_script(kind, target_lang='zh-CN'):
    # Check both source and output: an old result must never satisfy a new request.
    target = "Array.from(document.querySelectorAll('span[jsname=\"W297wb\"]')).map(x=>x.innerText).filter(Boolean).join('\\n')" if kind == 'google_web' else "document.querySelector('#tta_output_ta')?.value || document.querySelector('#tta_output_ta')?.innerText || ''"
    source = "document.querySelector('textarea')?.value || ''" if kind == 'google_web' else "document.querySelector('#tta_input_ta')?.value || document.querySelector('#tta_input_ta')?.innerText || ''"
    if kind == 'baidu_web':
        source = "document.querySelector('[data-slate-editor=true]')?.innerText || ''"
        target = "(() => {const groups=new Map();document.querySelectorAll('span.sentId[contenteditable=false]').forEach(x=>{const k=x.dataset.paraId;groups.set(k,(groups.get(k)||'')+x.innerText);});return Array.from(groups.values()).join('\\n');})()"
    elif kind == 'deepl_web':
        source = "document.querySelector('div[contenteditable][aria-labelledby=translation-source-heading]')?.innerText || ''"
        from ..languages import service_pair
        _, code = service_pair(kind, 'auto', target_lang)
        target = "document.querySelector('div[contenteditable][aria-labelledby=translation-target-heading][lang^=" + code.split('-')[0] + "]')?.innerText || ''"
    elif kind == 'youdao_web':
        source = "document.querySelector('#js_fanyi_input')?.innerText || ''"
        target = "document.querySelector('#js_fanyi_output_resultOutput')?.innerText || ''"
    elif kind == 'tencent_web':
        source = "document.querySelector('textarea')?.value || ''"
        target = "Array.from(document.querySelectorAll('.target-text-list')).map(x=>x.innerText).join('\\n')"
    return """JSON.stringify((() => {
        const body = (document.body?.innerText || '').slice(0, 16000);
        const visible = el => el && el.getBoundingClientRect().width > 0 && getComputedStyle(el).visibility !== 'hidden';
        const blocked = /unusual traffic|verify you are human|人机验证|请完成验证/i.test(body)
            || Array.from(document.querySelectorAll('#captcha, #b_captcha, iframe[title*=challenge]')).some(visible);
        return {source: SOURCE, text: TARGET, blocked, url: location.href,
                error: /Sorry, something went wrong|出了点问题|无法翻译|Can't translate/i.test(body)};
    })())""".replace('SOURCE', source).replace('TARGET', target)


def prepare_script(kind, text):
    """Only the two sites without text deep links need ordinary form input."""
    if kind == 'youdao_web':
        code = """
            let el = document.querySelector('#js_fanyi_input');
            if (!el) {
                const tab = Array.from(document.querySelectorAll('.tab-item')).find(x=>x.textContent.trim()==='翻译');
                if(tab && !tab.classList.contains('active')) tab.click();
                return 'waiting';
            }
            el.focus();
            const range = document.createRange(); range.selectNodeContents(el);
            const selection = getSelection(); selection.removeAllRanges(); selection.addRange(range);
            document.execCommand('insertText', false, TEXT);
            return el.innerText.trim() === TEXT.trim() ? 'filled' : 'waiting';
        """
    elif kind == 'tencent_web':
        code = """
            // The page silently drops edits before its anonymous session is ready.
            // Observe completion only: never read, mint or reuse the site's token.
            const boot = performance.getEntriesByType('resource').find(x=>{
                const u = new URL(x.name);
                return u.hostname==='api.fanyi.qq.com' && u.pathname==='/api/v1/token/create';
            });
            if(!boot || performance.now() < boot.responseEnd + 700) return 'waiting';
            const el = document.querySelector('textarea[placeholder="输入文本内容"]');
            if(!el) return 'waiting';
            Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set.call(el, TEXT);
            el.dispatchEvent(new Event('input', {bubbles: true}));
            el.dispatchEvent(new Event('change', {bubbles: true}));
            return 'filled';
        """
    else:
        return "'filled'"
    # JSON serialization keeps all submitted text data, never JavaScript syntax.
    return "(() => { if(location.hostname !== " + json.dumps(HOSTS[kind]) + ") return 'waiting'; " + code.replace('TEXT', json.dumps(text)) + '})()'


class WebTranslationService(QObject):
    succeeded = Signal(object)
    failed = Signal(str, str, str)
    progress = Signal(str, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        from PySide6.QtWebEngineCore import QWebEngineProfile
        self.profile = QWebEngineProfile(self)  # No storage name => off-the-record.
        self.profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.MemoryHttpCache)
        self.profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies)
        self.profile.downloadRequested.connect(lambda download: download.cancel())
        self.jobs = {}

    def submit(self, request):
        from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
        from PySide6.QtWebEngineWidgets import QWebEngineView
        from PySide6.QtCore import Qt
        kind = request.settings_snapshot.provider
        from ..core.models import AppError
        try:
            url = website_url(kind, request.text, request.settings_snapshot.source_lang, request.settings_snapshot.target_lang)
        except (AppError, ValueError) as error:
            self.failed.emit(request.request_id, 'LANGUAGE_UNSUPPORTED', str(error))
            return
        if not request.text.strip() or len(request.text) > LIMITS[kind]:
            self.failed.emit(request.request_id, 'INPUT_LIMIT', ui_format('{}{}{}', tr('此网页每次支持 1–'), LIMITS[kind], tr(' 字符，请缩小选区；原文已保留。')))
            return
        if len(self.jobs) >= 2:
            self.failed.emit(request.request_id, 'WEB_BUSY', tr('网页翻译正在运行，请取消前一个任务或稍后再试。'))
            return
        class QuietPage(QWebEnginePage):
            def javaScriptConsoleMessage(self, level, message, line, source):
                pass  # Website diagnostics can contain submitted text; never log them.
        page = QuietPage(self.profile, self)
        view = QWebEngineView()
        view.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
        view.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        view.resize(1024, 768)
        view.setPage(page)
        view.show()
        # Chromium throttles invisible documents; visibility here enables page work,
        # without creating or showing a browser window.
        page.setVisible(True)
        for option in ('LocalContentCanAccessFileUrls', 'LocalContentCanAccessRemoteUrls', 'JavascriptCanOpenWindows', 'ScreenCaptureEnabled', 'HyperlinkAuditingEnabled'):
            attribute = getattr(QWebEngineSettings.WebAttribute, option, None)
            if attribute is not None:
                page.settings().setAttribute(attribute, False)
        page.settings().setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, True)
        if hasattr(page, 'permissionRequested'):
            page.permissionRequested.connect(lambda permission: permission.deny())
        timer = QTimer(page)
        timer.setInterval(450)
        deadline = QTimer(page)
        deadline.setSingleShot(True)
        job = {'request': request, 'page': page, 'view': view, 'timer': timer, 'deadline': deadline,
               'started': time.monotonic(), 'last': '', 'stable': 0, 'reading': False,
               'ready_after': None,
               'prepared': kind not in ('youdao_web', 'tencent_web')}
        self.jobs[request.request_id] = job
        timer.timeout.connect(lambda: self._poll(request.request_id))
        deadline.timeout.connect(lambda: self._fail(request.request_id, 'WEB_TIMEOUT', tr('网页翻译超时。请检查网络，或在“更多操作”中打开原网页；原文已保留。')))
        page.renderProcessTerminated.connect(lambda *_: self._fail(request.request_id, 'WEB_PROCESS', tr('网页进程已退出，请重试或切换引擎。')))
        def loaded(ok):
            if request.request_id not in self.jobs:
                return
            if ok:
                job['ready_after'] = time.monotonic() + 2
                timer.start()
            else:
                self._fail(request.request_id, 'WEB_CONNECTION', tr('无法打开翻译网页，请检查网络；可在“更多操作”中打开原网页。'))
        page.loadFinished.connect(loaded)
        self.progress.emit(request.request_id, tr('正在网页翻译'))
        deadline.start(request.settings_snapshot.total_timeout_seconds * 1000)
        page.setUrl(QUrl(url))
        timer.start()  # DOM can be ready while third-party page resources are still loading.

    def _poll(self, request_id):
        job = self.jobs.get(request_id)
        if job is None or job['reading']:
            return
        job['reading'] = True
        if not job['prepared']:
            if job['request'].settings_snapshot.provider == 'tencent_web' and (job['ready_after'] is None or time.monotonic() < job['ready_after']):
                job['reading'] = False
                return
            job['page'].runJavaScript(prepare_script(job['request'].settings_snapshot.provider, job['request'].text),
                                     lambda result: self._prepared(request_id, result))
            return
        job['page'].runJavaScript(extraction_script(job['request'].settings_snapshot.provider, job['request'].settings_snapshot.target_lang),
                                 lambda result: self._read(request_id, result))

    def _prepared(self, request_id, result):
        job = self.jobs.get(request_id)
        if job:
            job['reading'] = False
            job['prepared'] = result == 'filled'

    def _read(self, request_id, result):
        job = self.jobs.get(request_id)
        if job is None:
            return
        job['reading'] = False
        if isinstance(result, str):
            try:
                result = json.loads(result)
            except ValueError:
                return
        if not isinstance(result, dict):
            return
        kind = job['request'].settings_snapshot.provider
        host = urlsplit(result.get('url', '')).hostname
        if result.get('blocked') or host in ('consent.google.com', 'accounts.google.com', 'login.live.com'):
            self._fail(request_id, 'WEB_INTERACTION', tr('网页需要验证或登录。请在“更多操作”中打开网页手动翻译，或切换引擎。'))
            return
        expected = HOSTS[kind]
        if host is None or result.get('url') == 'about:blank':
            return
        if host != expected:
            self._fail(request_id, 'WEB_REDIRECT', tr('网页跳转到了其他地址，已停止读取。请在浏览器中检查翻译网站。'))
            return
        if result.get('error'):
            self._fail(request_id, 'WEB_SERVICE', tr('翻译网页返回错误，请稍后重试或更换引擎。'))
            return
        text = result.get('text', '').strip()
        source = result.get('source', '').replace('\r\n', '\n').strip()
        if ' '.join(source.split()) != ' '.join(job['request'].text.split()) or not any(char.isalnum() for char in text):
            job['stable'] = 0
            return
        if len(text) > 40000:
            self._fail(request_id, 'WEB_FORMAT', tr('网页返回结果异常，请打开原网页检查。'))
            return
        job['stable'] = job['stable'] + 1 if text == job['last'] else 0
        job['last'] = text
        if job['stable'] >= (6 if kind == 'baidu_web' else 3):
            elapsed = (time.monotonic() - job['started']) * 1000
            self.cancel(request_id)
            self.succeeded.emit(TranslationResult(request_id, text, elapsed, 'stop'))

    def _fail(self, request_id, code, message):
        if request_id in self.jobs:
            self.cancel(request_id)
            self.failed.emit(request_id, code, message)

    def cancel(self, request_id):
        job = self.jobs.pop(request_id, None)
        if job:
            job['timer'].stop()
            job['deadline'].stop()
            from PySide6.QtWebEngineCore import QWebEnginePage
            job['page'].triggerAction(QWebEnginePage.WebAction.Stop)
            job['view'].close()
            job['view'].deleteLater()
            job['page'].deleteLater()

    def close(self):
        for request_id in list(self.jobs):
            self.cancel(request_id)

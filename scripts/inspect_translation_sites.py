"""Inspect public page controls with synthetic input; no user data or logins."""
from pathlib import Path
import json, sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PySide6.QtCore import Qt, QCoreApplication, QTimer, QUrl
QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
from PySide6.QtWidgets import QApplication
from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView
from urllib.parse import quote


def run():
    app = QApplication([]); app.setQuitOnLastWindowClosed(False)
    profile = QWebEngineProfile()
    pages = {}
    text = quote('Hello. This is a translation test.', safe='')
    urls = {
        'baidu_web': 'https://fanyi.baidu.com/mtpe-individual/multimodal?query=' + text + '&lang=en2zh',
        'youdao_web': 'https://fanyi.youdao.com/index.html#/',
        'deepl_web': 'https://www.deepl.com/en/translator#en/zh/' + text,
        'tencent_web': 'https://fanyi.qq.com/?source=en&target=zh&sourceText=' + text,
    }
    for kind, url in urls.items():
        view = QWebEngineView()
        view.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
        view.resize(1100, 800)
        page = QWebEnginePage(profile, view)
        view.setPage(page); view.show()
        page.setUrl(QUrl(url))
        pages[kind] = (view, page)
    reports = {}
    def prepare():
        pages['youdao_web'][1].runJavaScript("(() => { const el=Array.from(document.querySelectorAll('a,button,span,div')).find(x=>x.children.length===0&&x.innerText.trim()==='翻译'); if(el) {el.click(); return el.outerHTML;} })()", lambda value: print('youdao-tab', value, flush=True))
        pages['tencent_web'][1].runJavaScript("(() => {const el=document.querySelector('textarea'); if(el) {Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set.call(el,'Hello. This is a translation test.');el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));return el.outerHTML;}})()", lambda value: print('tencent-input', value, flush=True))
    def fill_youdao():
        pages['youdao_web'][1].runJavaScript("(() => {const el=document.querySelector('#js_fanyi_input, textarea');if(!el)return 'no classic input';el.focus();if(el.tagName==='TEXTAREA'){Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set.call(el,'Hello. This is a translation test.');el.dispatchEvent(new Event('input',{bubbles:true}));}else{document.execCommand('insertText',false,'Hello. This is a translation test.');} return el.outerHTML;})()", lambda value: print('youdao-input', value, flush=True))
    QTimer.singleShot(18000, prepare)
    QTimer.singleShot(25000, fill_youdao)
    def inspect():
        for kind, (_, page) in pages.items():
            page.runJavaScript("JSON.stringify({url:location.origin+location.pathname,title:document.title,inputs:Array.from(document.querySelectorAll('textarea,[contenteditable],[role=textbox]')).map(x=>({html:x.outerHTML.slice(0,1800),parent:x.parentElement.outerHTML.slice(0,2000)})),controls:Array.from(document.querySelectorAll('a,button,span,div')).filter(x=>x.children.length==0 && /^(翻译|译文|翻译结果|立即翻译|开始翻译)$/.test(x.textContent.trim())).slice(0,15).map(x=>x.parentElement.outerHTML.slice(0,1800)),chinese:Array.from(document.querySelectorAll('p,span,div')).filter(x=>x.children.length==0 && /你好|翻译测试/.test(x.innerText)).slice(0,10).map(x=>x.outerHTML)})", lambda result, name=kind: done(name, result))
    def done(kind, result):
        reports[kind] = json.loads(result) if result else {}
        print(kind, result, flush=True)
        if len(reports) == len(pages):
            (ROOT / '.tmp' / 'websites-dom.json').write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding='utf-8')
            for view, page in pages.values():
                view.close(); page.deleteLater(); view.deleteLater()
            QTimer.singleShot(200, app.quit)
    QTimer.singleShot(38000, inspect)
    QTimer.singleShot(50000, app.quit)
    app.exec()


if __name__ == '__main__':
    run()

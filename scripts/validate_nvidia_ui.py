"""Live settings test with transient stdin credential; no key persistence."""
from pathlib import Path
import sys,json,tempfile,time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from snaptrans.app import Application
from snaptrans.config import DEFAULT,ConfigStore
from copy import deepcopy
def main():
    key=sys.stdin.readline().strip()
    folder=ROOT/'.tmp/v160-live-ui';folder.mkdir(parents=True,exist_ok=True)
    data=Path(tempfile.mkdtemp(dir=folder));(data/'logs').mkdir()
    config=deepcopy(DEFAULT);config['hotkeys']={'translate':'Ctrl+Alt+Shift+F10','ocr':'Ctrl+Alt+Shift+F11'}
    ConfigStore(data/'config.json').save(config)
    qt=QApplication([]);qt.setQuitOnLastWindowClosed(False)
    app=Application(qt,data);results={};stage='translation';started=time.monotonic()
    app.open_settings();w=app.settings;w.tabs.setCurrentIndex(1)
    w.provider.setCurrentIndex(w.provider.findData('nvidia'));w.api_key.setText(key)
    w.test_button.click()
    def poll():
        nonlocal stage
        if time.monotonic()-started>55:
            results['error']='diagnostic timeout';app.quit();return
        if stage=='translation' and not app.test_id:
            results['translation']=w.message.text();stage='ocr'
            w.tabs.setCurrentIndex(2);w.ocr_provider.setCurrentIndex(w.ocr_provider.findData('nvidia_vl'))
            w.ocr_key.setText(key);w.ocr_test_button.click()
        elif stage=='ocr' and not app.ocr_test_id:
            results['ocr']=w.message.text();stage='done'
            results['ok']='连接成功' in results['translation'] and '连接成功' in results['ocr']
            results['no_credential_file']=not (data/'credentials.json').exists()
            # Clear inputs before any screenshot; key remains transient in process memory.
            w.api_key.clear();w.ocr_key.clear()
            app.quit()
    timer=QTimer();timer.timeout.connect(poll);timer.start(100)
    qt.exec()
    (folder/'report.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(results,ensure_ascii=False))

if __name__ == '__main__':
    import multiprocessing
    multiprocessing.freeze_support()
    main()

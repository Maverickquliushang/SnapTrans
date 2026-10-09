from snaptrans.core.controller import TaskGate
from snaptrans.core.models import State


def test_old_results_rejected_after_cancel_and_restart():
    gate = TaskGate()
    previous = gate.begin(State.RECOGNIZING)
    assert gate.busy
    gate.invalidate()
    assert not gate.accepts(previous)
    current = gate.begin(State.TRANSLATING)
    assert gate.accepts(current)
    assert not gate.accepts(previous)
    assert not gate.accepts('')


def test_result_window_edit_and_retry(qt_app):
    from snaptrans.ui.result_window import ResultWindow
    from snaptrans.core.models import TranslationResult
    window = ResultWindow({'always_on_top': False, 'font_size': 14})
    window.set_original('raw\ntext', 'raw text')
    window.set_translation(TranslationResult('id', '译文', 10))
    window.original.setPlainText('edited')
    assert '尚未更新' in window.status.text()
    retries = []
    window.retry.connect(retries.append)
    window.retry_button.click()
    assert retries == ['edited']
    window.show_ocr_record()
    assert window.ocr_record_dialog.isVisible()
    assert not window.original.isReadOnly()
    assert window.retry_button.isEnabled()
    window.ocr_record_dialog.close()
    assert window.original.toPlainText() == 'edited'
    window.set_busy(True)
    assert not window.translated.toPlainText()
    assert not window.copy_target.isEnabled()
    window.close()
    window.deleteLater()


def test_settings_close_accepts_and_clears_secret(qt_app):
    from snaptrans.config import DEFAULT
    from snaptrans.ui.settings_window import SettingsWindow
    settings = SettingsWindow(DEFAULT, 'synthetic-only')
    closed = []
    settings.closed.connect(lambda: closed.append(True))
    settings.show()
    assert settings.close()
    assert closed == [True]
    assert not settings.saved_secret

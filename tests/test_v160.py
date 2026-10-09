import asyncio
import json
from copy import deepcopy
from unittest.mock import Mock, patch
import httpx
from PySide6.QtCore import Qt, QPoint
from PySide6.QtTest import QTest
from snaptrans.config import DEFAULT, validate
from snaptrans.core.models import ProviderSettings, TranslationRequest, AppError
from snaptrans.providers.nvidia import NvidiaProvider
from snaptrans.providers.nvidia_http import response_json
from snaptrans.providers.nvidia_vl import NvidiaVisionProvider
from snaptrans.ui.settings_window import SettingsWindow


def test_number_typing_and_model_defaults(qt_app):
    window=SettingsWindow(DEFAULT)
    window.provider.setCurrentIndex(window.provider.findData('nvidia'))
    window.model.setText('deepseek-ai/deepseek-v4.1-flash')
    assert window.max_tokens.value()==262144
    window.timeout.selectAll(); QTest.keyClicks(window.timeout,'180')
    window.max_tokens.selectAll(); QTest.keyClicks(window.max_tokens,'4096')
    assert window.timeout.value()==180 and window.max_tokens.value()==4096
    assert not window.model_defaults.isChecked()
    window.model.setText('unknown/model')
    assert window.max_tokens.value()==4096
    window.model_defaults.setChecked(True)
    assert window.max_tokens.value()==0
    window.close()


def test_prompt_confirmations_and_cancel(qt_app):
    from snaptrans.ui.prompt_editor import PromptEditor
    widget=PromptEditor('original')
    saved=[];widget.save_requested.connect(saved.append)
    with patch.object(widget,'confirm',return_value=False):
        widget.unlock()
        assert widget.editor.isReadOnly()
    with patch.object(widget,'confirm',return_value=True):
        widget.unlock();widget.editor.setPlainText('new prompt')
    with patch.object(widget,'confirm',return_value=False):
        widget.commit();assert saved==[] and widget.saved=='original'
    with patch.object(widget,'confirm',return_value=True):
        widget.commit();assert saved==['new prompt']
    assert not widget.editor.isReadOnly() # Remains editable until disk save acknowledgement.
    widget.saved_result('new prompt'); assert widget.editor.isReadOnly()
    with patch.object(widget,'confirm',return_value=True):
        widget.unlock();widget.editor.setPlainText('discarded');widget.cancel()
    assert widget.editor.toPlainText()=='new prompt'
    widget.close()


def test_academic_prompt_used_only_in_academic_requests():
    from snaptrans.providers.compatible import CompatibleProvider
    provider=CompatibleProvider()
    async def run():
        try:
            settings=ProviderSettings(mode='academic',academic_prompt='custom saved instructions')
            body=provider.request_body(TranslationRequest('id','Hello',settings))
            assert body['messages'][0]['content'].startswith('custom saved instructions\n')
            assert 'English -> Simplified Chinese' in body['messages'][0]['content']
            assert 'custom saved' not in provider.request_body(TranslationRequest('id','Hello',ProviderSettings()))['messages'][0]['content']
        finally: await provider.aclose()
    asyncio.run(run())


def test_workspace_edit_export_and_original_isolation(qt_app):
    from test_ocr_workspace import workspace
    controller,ocr,network=workspace(qt_app)
    canvas=controller.result.overlay
    original=canvas.selected_pixmap().toImage()
    canvas.editor.buttons['arrow'].click()
    start=canvas.selection.topLeft().toPoint()+QPoint(20,20)
    QTest.mousePress(canvas,Qt.MouseButton.LeftButton,pos=start)
    QTest.mouseMove(canvas,start+QPoint(120,20))
    QTest.mouseRelease(canvas,Qt.MouseButton.LeftButton,pos=start+QPoint(120,20))
    assert canvas.rendered_selection().toImage()!=original
    assert canvas.selected_pixmap().toImage()==original and not ocr.submit.called
    controller.result.set_workspace_mode('translate')
    assert controller.result.overlay is canvas and canvas.editor.document.index==1
    canvas.editor.undo();assert canvas.rendered_selection().toImage()==original
    canvas.editor.redo();canvas.copy_image();assert qt_app.clipboard().pixmap().toImage()!=original
    controller.close()


def test_auto_translate_preference_and_migration(qt_app):
    from test_ocr_workspace import workspace
    assert validate(DEFAULT)['capture']['auto_translate'] is True
    controller,_,_=workspace(qt_app)
    config=controller.config_getter();config['capture']['auto_translate']=False
    with patch.object(controller,'_show_selector'):
        controller.capture('translate')
        assert controller.ocr_only
    controller.close()


def test_sse_reasoning_hidden_and_partial_events():
    async def run():
        data='data: '+json.dumps({'choices':[{'delta':{'reasoning_content':'private'}}]})+'\n\n'
        data+='data: '+json.dumps({'choices':[{'delta':{'content':'你好'},'finish_reason':'stop'}]})+'\n\ndata: [DONE]\n\n'
        provider=NvidiaProvider(httpx.MockTransport(lambda req:httpx.Response(200,headers={'content-type':'text/event-stream'},text=data)))
        phases=[];provider.progress=lambda rid,phase:phases.append(phase)
        try:
            result=await provider.translate(TranslationRequest('id','Hello',ProviderSettings(provider='nvidia',base_url='https://integrate.api.nvidia.com/v1',model='custom')), 'test')
            assert result.text=='你好' and phases==['模型正在推理','正在接收结果']
        finally:await provider.aclose()
    asyncio.run(run())


def test_poll_202_uses_fixed_origin():
    async def run():
        seen=[]
        def handler(req):
            seen.append(str(req.url))
            return httpx.Response(202,headers={'NVCF-REQID':'12345678-1234-1234-1234-123456789abc','location':'https://evil.invalid'}) if len(seen)==1 else httpx.Response(200,json={'ok':True})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result=await response_json(client,'https://integrate.api.nvidia.com/v1/chat/completions',{},'test',10)
        assert result['ok'] and seen[-1]=='https://integrate.api.nvidia.com/v1/status/12345678-1234-1234-1234-123456789abc'
    asyncio.run(run())


def test_vl_ocr_preserves_pixels_and_paragraphs():
    from test_nvidia import frame
    import base64,io
    from PIL import Image
    async def run():
        def handler(req):
            body=json.loads(req.content)
            url=body['messages'][0]['content'][1]['image_url']['url']
            assert Image.open(io.BytesIO(base64.b64decode(url.split(',')[1]))).size==(80,30)
            return httpx.Response(200,json={'choices':[{'message':{'content':'first\n\nsecond'},'finish_reason':'stop'}]})
        provider=NvidiaVisionProvider(httpx.MockTransport(handler))
        try:
            result=await provider.recognize(frame(),{**DEFAULT['ocr'],'provider':'nvidia_vl'},'test')
            assert result.raw_text=='first\n\nsecond' and result.lines==[]
        finally:await provider.aclose()
    asyncio.run(run())


def test_test_cancel_timeout_and_late_callback(qt_app):
    from PySide6.QtCore import QObject, QTimer
    from snaptrans.app import Application
    from snaptrans.core.models import TranslationResult
    import time
    app=Application.__new__(Application);QObject.__init__(app)
    app.settings=SettingsWindow(DEFAULT);app.network=Mock()
    app.test_timer=QTimer(app);app.test_id='test-1';app.ocr_test_id='';app.models_id=''
    app.start_test_watch(10,'waiting')
    assert not app.settings.test_button.isEnabled() and not app.settings.ocr_test_button.isEnabled()
    app.test_started=time.monotonic()-11
    app.test_tick()
    assert app.test_id=='' and app.settings.test_button.isEnabled()
    assert app.settings.ocr_test_button.isEnabled()
    message=app.settings.message.text()
    assert '超时' in message and not app.test_timer.isActive()
    app.test_done(TranslationResult('test-1','late',1))
    assert app.settings.message.text()==message
    app.settings.close()


def test_stream_timeout_cancellation_and_partial_result_rejected():
    class Stalled(httpx.AsyncByteStream):
        async def __aiter__(self):
            await asyncio.sleep(30)
            yield b'data: [DONE]\n\n'
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req:httpx.Response(200,
                headers={'content-type':'text/event-stream'},stream=Stalled()))) as client:
            import pytest
            with pytest.raises(TimeoutError):
                await response_json(client,'https://integrate.api.nvidia.com/v1/chat/completions',{},'test',.02)
            task=asyncio.create_task(response_json(client,'https://integrate.api.nvidia.com/v1/chat/completions',{},'test',30))
            await asyncio.sleep(.01);task.cancel()
            with pytest.raises(asyncio.CancelledError):await task
        data='data: '+json.dumps({'choices':[{'delta':{'content':'partial'}}]})+'\n\n'
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req:httpx.Response(200,
                headers={'content-type':'text/event-stream'},text=data))) as client:
            with pytest.raises(AppError) as error:
                await response_json(client,'https://integrate.api.nvidia.com/v1/chat/completions',{},'test',10)
            assert error.value.code=='STREAM_INTERRUPTED'
    asyncio.run(run())


def test_invalid_numeric_draft_does_not_break_provider_switch(qt_app):
    window = SettingsWindow(DEFAULT)
    original = window.provider.currentData()
    window.timeout.clear()
    window.provider.setCurrentIndex(window.provider.findData('nvidia'))
    assert window.provider.currentData() == original and '有效数字' in window.message.text()
    window.timeout.setText('45')
    window.provider.setCurrentIndex(window.provider.findData('nvidia'))
    assert window.provider.currentData() == 'nvidia'
    window.close()


def test_manual_token_count_keeps_model_nonreasoning_defaults():
    settings = ProviderSettings(provider='nvidia', model='nvidia/nemotron-3-super-120b-a12b',
                                model_defaults=False, max_tokens=6000)
    body = NvidiaProvider.request_body(NvidiaProvider.__new__(NvidiaProvider), TranslationRequest('id','Hello',settings))
    assert body['max_tokens'] == 6000 and body['reasoning_effort'] == 'none'

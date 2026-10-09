import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
from snaptrans.providers.compatible import CompatibleProvider
from snaptrans.core.models import ProviderSettings, TranslationRequest


def test_compatible_localhost_bypasses_broken_system_proxy(monkeypatch):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers['content-length']))
            data = json.dumps({'choices': [{'message': {'content': '直连成功'}}]}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        def log_message(self, *args):
            return
    # Keep sockets local; no dependency on an external proxy or Ollama model.
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    async def run():
        with patch('httpx._utils.getproxies', return_value={'http': 'http://127.0.0.1:1', 'https': 'http://127.0.0.1:1'}):
            provider = CompatibleProvider()
        try:
            settings = ProviderSettings(provider='compatible',
                base_url=f'http://127.0.0.1:{server.server_port}/v1', model='synthetic', requires_api_key=False)
            result = await provider.translate(TranslationRequest('proxy-test', 'Public text', settings))
            assert result.text == '直连成功'
        finally:
            await provider.aclose()
    try:
        asyncio.run(run())
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

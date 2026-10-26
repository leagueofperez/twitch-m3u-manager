import importlib.util
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path


def _load_healthcheck():
    path = Path(__file__).resolve().parents[1] / "healthcheck.py"
    spec = importlib.util.spec_from_file_location("healthcheck", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _serve(status: int) -> tuple[HTTPServer, str]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_port}/health"


def test_healthcheck_passes_when_the_endpoint_answers():
    module = _load_healthcheck()
    server, url = _serve(200)
    try:
        assert module.check(url) == 0
    finally:
        server.shutdown()
        server.server_close()


def test_healthcheck_fails_when_the_endpoint_errors_or_is_unreachable():
    module = _load_healthcheck()
    server, url = _serve(500)
    try:
        assert module.check(url) == 1
    finally:
        server.shutdown()
        server.server_close()

    assert module.check("http://127.0.0.1:1/health") == 1


def test_healthcheck_uses_the_configured_port(monkeypatch):
    module = _load_healthcheck()
    server, _url = _serve(200)
    monkeypatch.setenv("PORT", str(server.server_port))
    monkeypatch.setattr(module, "check_internal_services", lambda: 0)
    try:
        assert module.main() == 0
    finally:
        server.shutdown()
        server.server_close()

    monkeypatch.setenv("PORT", "1")
    assert module.main() == 1

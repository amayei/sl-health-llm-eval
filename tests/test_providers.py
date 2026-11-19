import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from slheval.providers import AnthropicProvider, OpenAIProvider, make_provider


def serve(handler_fn):
    seen = []

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            seen.append(({k.lower(): v for k, v in self.headers.items()}, body))
            code, payload = handler_fn(body)
            raw = json.dumps(payload).encode()
            self.send_response(code)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    httpd = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, seen


def test_anthropic_request_and_parse(monkeypatch):
    httpd, seen = serve(lambda b: (200, {"model": "m-1", "stop_reason": "end_turn", "content": [{"type": "text", "text": "B"}]}))
    monkeypatch.setattr(AnthropicProvider, "URL", f"http://127.0.0.1:{httpd.server_address[1]}/v1/messages")
    out = make_provider({"provider": "anthropic", "model": "x", "max_tokens": 16}, "KEY").complete("sys", "user")
    httpd.shutdown()
    headers, body = seen[0]
    assert headers["x-api-key"] == "KEY" and headers["anthropic-version"] == "2023-06-01"
    assert body["system"] == "sys" and body["temperature"] == 0 and body["max_tokens"] == 16
    assert out == {"text": "B", "model_returned": "m-1", "note": "end_turn"}


def test_openai_request_and_parse(monkeypatch):
    httpd, seen = serve(lambda b: (200, {"model": "g-1", "choices": [{"message": {"content": "C"}, "finish_reason": "stop"}]}))
    monkeypatch.setattr(OpenAIProvider, "URL", f"http://127.0.0.1:{httpd.server_address[1]}/v1/chat/completions")
    out = make_provider({"provider": "openai", "model": "x", "max_tokens": 16}, "KEY").complete("sys", "user")
    httpd.shutdown()
    headers, body = seen[0]
    assert headers["authorization"] == "Bearer KEY"
    assert body["max_completion_tokens"] == 16 and "max_tokens" not in body and body["temperature"] == 0
    assert out["text"] == "C" and out["model_returned"] == "g-1"


@pytest.mark.parametrize("cls,name,ok", [
    (OpenAIProvider, "openai", {"model": "g", "choices": [{"message": {"content": "A"}, "finish_reason": "stop"}]}),
    (AnthropicProvider, "anthropic", {"model": "c", "stop_reason": "end_turn", "content": [{"type": "text", "text": "A"}]}),
])
def test_temperature_rejected_falls_back_and_is_noted(monkeypatch, cls, name, ok):
    def handler(body):
        if "temperature" in body:
            return 400, {"error": {"message": "temperature is not supported with this model"}}
        return 200, ok
    httpd, seen = serve(handler)
    monkeypatch.setattr(cls, "URL", f"http://127.0.0.1:{httpd.server_address[1]}/x")
    out = make_provider({"provider": name, "model": "x"}, "K").complete("s", "u")
    httpd.shutdown()
    assert len(seen) == 2 and "temperature" not in seen[1][1]
    assert out["note"] == "temperature_not_supported" and out["text"] == "A"


def test_other_http_errors_are_not_swallowed(monkeypatch):
    httpd, _ = serve(lambda b: (401, {"error": "bad key"}))
    monkeypatch.setattr(OpenAIProvider, "URL", f"http://127.0.0.1:{httpd.server_address[1]}/x")
    with pytest.raises(Exception, match="401"):
        make_provider({"provider": "openai", "model": "x"}, "K").complete("s", "u")
    httpd.shutdown()

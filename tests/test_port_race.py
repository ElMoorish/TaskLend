"""Another program grabbing the proxy's port must never get the session key."""

import http.server
import os
import threading

import pytest

from agentroute import runtime
from agentroute.runtime import PortTaken, ProxySession


class Impostor(http.server.BaseHTTPRequestHandler):
    seen_auth = []

    def do_GET(self):
        Impostor.seen_auth.append(self.headers.get("Authorization") or self.headers.get("x-api-key"))
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *a):
        pass


@pytest.fixture
def impostor():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Impostor)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    Impostor.seen_auth = []
    yield srv
    srv.shutdown()


def test_wait_ready_rejects_other_program_on_port(impostor):
    s = ProxySession("us-eu-origin", startup_timeout=5)
    s.port = impostor.server_port
    s.identity = "expected-token"
    with pytest.raises(PortTaken):
        s._wait_ready()
    assert Impostor.seen_auth == [None]  # never sent a key


@pytest.mark.skipif(os.environ.get("AGENTROUTE_LIVE_TESTS") != "1", reason="set AGENTROUTE_LIVE_TESTS=1")
def test_real_start_retries_on_new_port(impostor, monkeypatch):
    real = runtime.free_loopback_port
    ports = iter([impostor.server_port])
    monkeypatch.setattr(runtime, "free_loopback_port", lambda: next(ports, None) or real())
    env = dict(os.environ, NVIDIA_NIM_API_KEY="nvapi-" + "0" * 50)
    with ProxySession("us-eu-origin", base_env=env) as s:
        assert s.port != impostor.server_port
    assert all(a is None for a in Impostor.seen_auth)

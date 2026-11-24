"""Another program grabbing the proxy's port must never get the session key."""

import http.server
import os
import threading

import pytest

from tasklend import runtime
from tasklend.runtime import PortTaken, ProxySession


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


@pytest.mark.skipif(os.environ.get("TASKLEND_LIVE_TESTS") != "1", reason="set TASKLEND_LIVE_TESTS=1")
def test_real_start_retries_on_new_port(impostor, monkeypatch):
    real = runtime.free_loopback_port
    ports = iter([impostor.server_port])
    monkeypatch.setattr(runtime, "free_loopback_port", lambda: next(ports, None) or real())
    env = dict(os.environ, NVIDIA_NIM_API_KEY="nvapi-" + "0" * 50)
    with ProxySession("us-eu-origin", base_env=env) as s:
        assert s.port != impostor.server_port
    assert all(a is None for a in Impostor.seen_auth)


@pytest.fixture
def banner_server():
    """A non-HTTP service (like SSH) that sends a greeting line on connect."""
    import socket

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen()
    stop = threading.Event()

    def serve():
        srv.settimeout(0.2)
        while not stop.is_set():
            try:
                conn, _ = srv.accept()
            except OSError:
                continue
            with conn:
                conn.sendall(b"SSH-2.0-OpenSSH_9.0\r\n")

    threading.Thread(target=serve, daemon=True).start()
    yield srv.getsockname()[1]
    stop.set()
    srv.close()


def test_wait_ready_treats_non_http_service_as_port_taken(banner_server):
    s = ProxySession("us-eu-origin", startup_timeout=5)
    s.port = banner_server
    s.identity = "expected-token"
    with pytest.raises(PortTaken):
        s._wait_ready()

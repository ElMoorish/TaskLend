"""Starts a real LiteLLM proxy on loopback. Slow (~15 s), so opt in with
TASKLEND_LIVE_TESTS=1. Uses a dummy NVIDIA key and sends nothing upstream."""

import os

import pytest

from tasklend.runtime import ProxySession, http_status

pytestmark = pytest.mark.skipif(
    os.environ.get("TASKLEND_LIVE_TESTS") != "1", reason="set TASKLEND_LIVE_TESTS=1"
)


def test_real_proxy_is_locked_down():
    env = dict(os.environ, NVIDIA_NIM_API_KEY="nvapi-" + "0" * 50)
    with ProxySession("us-eu-origin", base_env=env) as s:
        workdir = s.workdir
        assert s.base_url.startswith("http://127.0.0.1:")
        auth = {"Authorization": "Bearer " + s.master_key}
        assert http_status(s.base_url + "/v1/models", headers=auth) == 200
        assert http_status(s.base_url + "/v1/models") != 200
        for path in ("/ui", "/sso/debug/login", "/login"):
            assert http_status(s.base_url + path) == 404
        assert s.master_key not in s.log_path.read_text(encoding="utf-8", errors="replace")
    assert not workdir.exists()

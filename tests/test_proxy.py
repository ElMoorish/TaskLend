import json

from agentroute import proxy


def test_master_key_is_random_and_long():
    keys = {proxy.new_master_key() for _ in range(50)}
    assert len(keys) == 50
    assert all(len(k) > 40 for k in keys)


def test_config_holds_no_secrets(tmp_path):
    path = proxy.write_config("us-eu-origin", tmp_path / "litellm.json")
    text = path.read_text(encoding="utf-8")
    assert "os.environ/LITELLM_MASTER_KEY" in text
    assert "os.environ/NVIDIA_NIM_API_KEY" in text
    assert "nvapi-" not in text


def test_config_is_stateless():
    cfg = proxy.build_config("us-eu-origin")
    general = cfg["general_settings"]
    assert general["store_model_in_db"] is False
    assert "database_url" not in json.dumps(cfg).lower()


def test_config_orders_fallbacks_per_role():
    cfg = proxy.build_config("us-eu-origin")
    plan = [m for m in cfg["model_list"] if m["model_name"] == "nim-plan"]
    assert [m["litellm_params"]["order"] for m in plan] == [1, 2]
    assert all(m["litellm_params"]["model"].startswith("nvidia_nim/") for m in plan)


def test_proxy_always_binds_loopback(tmp_path):
    args = proxy.proxy_args(tmp_path / "c.json", 4123)
    assert args[args.index("--host") + 1] == "127.0.0.1"
    assert "0.0.0.0" not in args


def test_free_port_is_on_loopback():
    port = proxy.free_loopback_port()
    assert 0 < port < 65536


def test_preflight_flags_forbidden_features():
    assert proxy.preflight_env({}) == []
    problems = proxy.preflight_env({"DATABASE_URL": "postgres://x", "UI_USERNAME": "a"})
    assert len(problems) == 2


def test_proxy_env_strips_anthropic_credentials_and_forbidden_vars():
    base = {
        "PATH": "/bin",
        "ANTHROPIC_API_KEY": "secret",
        "ANTHROPIC_AUTH_TOKEN": "secret",
        "CLAUDE_CODE_OAUTH_TOKEN": "secret",
        "DATABASE_URL": "postgres://x",
    }
    env = proxy.proxy_env(base, "sk-ar-test")
    assert env["PATH"] == "/bin"
    assert env["LITELLM_MASTER_KEY"] == "sk-ar-test"
    for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN", "DATABASE_URL"):
        assert name not in env

from pathlib import Path

import pytest

from agentroute import worker
from agentroute._proxy_main import is_blocked
from agentroute.launch import main_args, main_env, orchestrator_prompt
from agentroute.runtime import unsafe_sso_routes

ROLE = worker.ROLES["code"]


def test_worker_env_strips_user_anthropic_credentials(tmp_path):
    base = {
        "PATH": "/bin",
        "ANTHROPIC_API_KEY": "sk-ant-user",
        "ANTHROPIC_AUTH_TOKEN": "user-token",
        "CLAUDE_CODE_OAUTH_TOKEN": "sk-ant-oat-user",
        "ANTHROPIC_BASE_URL": "https://example.invalid",
        "CLAUDE_CODE_USE_BEDROCK": "1",
        "ANTHROPIC_MODEL": "opus",
        worker.ENV_SESSION_KEY: "sk-ar-session",
    }
    env = worker.worker_env(base, ROLE, "http://127.0.0.1:4000/v1", "sk-ar-session", tmp_path)
    assert env["ANTHROPIC_API_KEY"] == "sk-ar-session"
    assert env["ANTHROPIC_BASE_URL"] == "http://127.0.0.1:4000"  # no /v1
    assert env["CLAUDE_CONFIG_DIR"] == str(tmp_path)
    for name in ("ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_CODE_USE_BEDROCK"):
        assert name not in env
    assert worker.ENV_SESSION_KEY not in env
    assert "sk-ant" not in " ".join(env.values())


def test_worker_env_pins_every_model_alias(tmp_path):
    env = worker.worker_env({}, ROLE, "http://127.0.0.1:1", "k", tmp_path)
    for name in worker.MODEL_ALIAS_ENV:
        assert env[name] == "nim-code"


def test_worker_args_use_bare_mode_and_role_tools(tmp_path):
    args = worker.worker_args("claude", worker.ROLES["explore"], "look around", tmp_path)
    assert "--bare" in args  # never reads OAuth or keychain
    assert args[args.index("--tools") + 1] == "Read,Grep,Glob"
    assert args[args.index("--model") + 1] == "nim-explore"
    assert "bypassPermissions" not in args


def test_only_code_role_can_edit():
    for name, role in worker.ROLES.items():
        writes = {"Edit", "Write"} & set(role.tools)
        assert bool(writes) == (name == "code"), name
        assert "Bash" not in role.tools
        assert role.permission_mode != "bypassPermissions"


def test_cap_output():
    assert worker.cap_output("short", 100) == "short"
    capped = worker.cap_output("x" * 1000, 100)
    assert len(capped) < 300
    assert "characters cut" in capped


def test_run_worker_requires_session():
    with pytest.raises(worker.WorkerError):
        worker.run_worker("code", "task", {})


def test_run_worker_rejects_unknown_role():
    with pytest.raises(worker.WorkerError):
        worker.run_worker("admin", "task", {})


def test_admin_routes_blocked():
    for path in ("/ui", "/ui/", "/UI/login", "/sso/debug/login", "/login", "/litellm-asset-prefix/a.js"):
        assert is_blocked(path), path
    for path in ("/v1/messages", "/health/liveliness", "/v1/models", "/uix"):
        assert not is_blocked(path), path


def test_unsafe_sso_routes():
    assert unsafe_sso_routes("http://x", lambda url: 404) == []
    assert unsafe_sso_routes("http://x", lambda url: None) == []
    assert len(unsafe_sso_routes("http://x", lambda url: 200)) == 3


class FakeSession:
    base_url = "http://127.0.0.1:4321"
    master_key = "sk-ar-session"


def test_main_session_keeps_user_environment(tmp_path):
    base = {"ANTHROPIC_API_KEY": "sk-ant-user", "PATH": "/bin"}
    env = main_env(base, FakeSession(), tmp_path)
    # The main Claude session talks to Anthropic exactly as before.
    assert env["ANTHROPIC_API_KEY"] == "sk-ant-user"
    assert "ANTHROPIC_BASE_URL" not in env
    assert env[worker.ENV_PROXY_URL] == FakeSession.base_url
    assert env[worker.ENV_SESSION_DIR] == str(tmp_path)


def test_main_args_pass_user_args_through():
    args = main_args("claude", ["--model", "opus", "-c"])
    assert args[0] == "claude"
    assert args[-3:] == ["--model", "opus", "-c"]
    assert "--append-system-prompt" in args


def test_orchestrator_prompt_mentions_roles_and_warning():
    text = orchestrator_prompt("agentroute work")
    for name in worker.ROLES:
        assert name in text
    assert "train" in text

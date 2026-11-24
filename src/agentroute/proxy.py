"""LiteLLM proxy configuration and safety checks.

The proxy is always:
- bound to 127.0.0.1, never 0.0.0.0;
- protected by a random master key made fresh for each session, passed only
  through the child process environment and never written to disk;
- stateless: no database, no STORE_MODEL_IN_DB, no admin UI users, no SSO or
  JWT settings, no enterprise licence key, no MCP stdio servers.
"""

from __future__ import annotations

import json
import secrets
import socket
from pathlib import Path
from typing import Mapping

from .profiles import ROLES, get_profile

LOOPBACK = "127.0.0.1"
MASTER_KEY_ENV = "LITELLM_MASTER_KEY"
NVIDIA_KEY_ENV = "NVIDIA_NIM_API_KEY"

# Environment variables that turn on LiteLLM features AgentRoute does not use and
# that carry the known unfixed advisories (database, SSO, JWT, UI login,
# enterprise). If any is set, the proxy must not start.
FORBIDDEN_ENV = (
    "DATABASE_URL",
    "STORE_MODEL_IN_DB",
    "LITELLM_LICENSE",
    "UI_USERNAME",
    "UI_PASSWORD",
    "JWT_PUBLIC_KEY_URL",
    "GOOGLE_CLIENT_ID",
    "MICROSOFT_CLIENT_ID",
    "GENERIC_CLIENT_ID",
    "LITELLM_ENABLE_MCP_STDIO",
)

# Never pass Anthropic credentials into the proxy process.
STRIPPED_ENV = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN")


def new_master_key() -> str:
    return "sk-ar-" + secrets.token_urlsafe(32)


def build_config(profile: str) -> dict:
    """LiteLLM proxy config for a profile.

    Secrets are referenced as os.environ/... so the rendered file holds none.
    """
    routes = get_profile(profile)
    model_list = []
    for role in ROLES:
        for order, model_id in enumerate(routes[role], start=1):
            model_list.append(
                {
                    "model_name": role,
                    "litellm_params": {
                        "model": f"nvidia_nim/{model_id}",
                        "api_key": f"os.environ/{NVIDIA_KEY_ENV}",
                        "order": order,
                        # Headroom under NVIDIA's best-effort 40 RPM trial ceiling.
                        "rpm": 25,
                        "max_parallel_requests": 3,
                    },
                }
            )
    return {
        "model_list": model_list,
        "litellm_settings": {"drop_params": True},
        "router_settings": {
            "routing_strategy": "simple-shuffle",
            "num_retries": 2,
            "allowed_fails": 2,
            "cooldown_time": 60,
            "enable_pre_call_checks": True,
        },
        "general_settings": {
            "master_key": f"os.environ/{MASTER_KEY_ENV}",
            "store_model_in_db": False,
            "disable_spend_logs": True,
        },
    }


def write_config(profile: str, path: Path) -> Path:
    """Write the config as JSON (valid YAML, which LiteLLM reads)."""
    config = build_config(profile)
    text = json.dumps(config, indent=2)
    assert "sk-" not in text and "nvapi-" not in text, "config must not hold secrets"
    path.write_text(text + "\n", encoding="utf-8")
    return path


def preflight_env(env: Mapping[str, str]) -> list[str]:
    """Problems that must stop the proxy from starting."""
    problems = []
    for name in FORBIDDEN_ENV:
        if env.get(name):
            problems.append(
                f"{name} is set. AgentRoute runs LiteLLM without this feature; unset it."
            )
    return problems


def proxy_env(base: Mapping[str, str], master_key: str) -> dict[str, str]:
    """Environment for the LiteLLM child process."""
    env = {
        k: v
        for k, v in base.items()
        if k not in FORBIDDEN_ENV and k not in STRIPPED_ENV
    }
    env[MASTER_KEY_ENV] = master_key
    env["DISABLE_ADMIN_UI"] = "True"
    return env


def free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((LOOPBACK, 0))
        return s.getsockname()[1]


def proxy_args(config_path: Path, port: int) -> list[str]:
    """Arguments for the `litellm` CLI. The host is always loopback."""
    return ["--config", str(config_path), "--host", LOOPBACK, "--port", str(port)]


def non_loopback_addresses() -> list[str]:
    try:
        _, _, addrs = socket.gethostbyname_ex(socket.gethostname())
    except OSError:
        return []
    return [a for a in addrs if not a.startswith("127.")]


def reachable_from_outside(port: int, timeout: float = 0.5) -> list[str]:
    """Non-loopback addresses on which `port` accepts connections.

    Run after the proxy starts: any result means it is exposed and must be stopped.
    """
    exposed = []
    for addr in non_loopback_addresses():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            if s.connect_ex((addr, port)) == 0:
                exposed.append(addr)
    return exposed

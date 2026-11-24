"""`agentroute launch`: run the user's own Claude Code as the orchestrator.

The main `claude` process is started unmodified, with the user's own login and
environment. AgentRoute does not set ANTHROPIC_BASE_URL or touch any Anthropic
credential for it, so all main-session traffic goes straight to Anthropic. It
only adds three AGENTROUTE_* variables so that `agentroute work` can reach the
local proxy, plus an appended system prompt explaining how to dispatch workers.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path
from typing import Mapping, Sequence

from .runtime import ProxySession
from .worker import ENV_PROXY_URL, ENV_SESSION_DIR, ENV_SESSION_KEY, ROLES


def work_command() -> str:
    return f'"{Path(sys.executable).as_posix()}" -m agentroute work'


def orchestrator_prompt(command: str) -> str:
    roles = "\n".join(f"- {name}: {role.brief}" for name, role in ROLES.items())
    return f"""\
# AgentRoute worker agents

You are the orchestrator. To save your own context and usage, delegate
self-contained pieces of work to worker agents that run on open models:

    {command} --role <role> "<complete, self-contained task>"

Run it with your Bash tool from the project directory. Roles:
{roles}

Workers cannot see this conversation, so put everything they need in the task.
Workers start with no tools beyond those of their role and cannot run commands.
Their output is capped; the path of the full output is printed at the end.
Treat worker output as a draft: check it before relying on it, and review any
file a code worker changed.

Workers use NVIDIA's hosted trial API, which is for non-production testing and
may use prompts to train models. Do not include secrets, credentials, personal
data, or HIPAA or PCI data in a worker task.
"""


def main_env(base: Mapping[str, str], session: ProxySession, session_dir: Path) -> dict[str, str]:
    env = dict(base)
    env[ENV_PROXY_URL] = session.base_url
    env[ENV_SESSION_KEY] = session.master_key
    env[ENV_SESSION_DIR] = str(session_dir)
    return env


def main_args(claude: str, user_args: Sequence[str]) -> list[str]:
    return [claude, "--append-system-prompt", orchestrator_prompt(work_command()), *user_args]


def run_launch(profile: str, user_args: Sequence[str], out=print) -> int:
    claude = shutil.which("claude")
    if not claude:
        out("Claude Code (`claude`) not found on PATH.")
        return 1
    out(f"Starting the local proxy (profile {profile})...")
    with ProxySession(profile) as session:
        assert session.workdir
        session_dir = session.workdir / "session"
        session_dir.mkdir()
        out(f"Proxy ready on {session.base_url}. Starting Claude Code.")
        # Let Claude Code handle Ctrl+C itself; we only clean up after it exits.
        previous = signal.signal(signal.SIGINT, signal.SIG_IGN)
        try:
            return subprocess.call(
                main_args(claude, user_args), env=main_env(os.environ, session, session_dir)
            )
        finally:
            signal.signal(signal.SIGINT, previous)
            out("Claude Code exited. Proxy stopped.")

"""Worker agents: headless Claude Code runs routed to open models.

A worker is a separate `claude --bare -p` process. In bare mode Claude Code
never reads OAuth tokens or the keychain, and its only credential is
ANTHROPIC_API_KEY, which Tasklend sets to the per-session proxy key. Its
config dir is a private session folder, so the user's own Claude login and
settings are never seen by a worker. The main Claude session is not involved.
"""

from __future__ import annotations

import datetime as _dt
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

# Environment the launcher gives the main Claude session so workers can find
# the proxy. These are local-only values that die with the session.
ENV_PROXY_URL = "TASKLEND_PROXY_URL"
ENV_SESSION_KEY = "TASKLEND_SESSION_KEY"
ENV_SESSION_DIR = "TASKLEND_SESSION_DIR"
ENV_PROFILE = "TASKLEND_PROFILE"

# Anything that could carry the user's Anthropic credentials or redirect auth.
CREDENTIAL_ENV = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "CLAUDE_CODE_OAUTH_TOKEN",
    "ANTHROPIC_BASE_URL",
    "CLAUDE_CODE_USE_BEDROCK",
    "CLAUDE_CODE_USE_VERTEX",
    "CLAUDE_CODE_USE_FOUNDRY",
    # Workers reach NVIDIA only through the proxy; they never need the key.
    "NVIDIA_NIM_API_KEY",
)

MODEL_ALIAS_ENV = (
    "ANTHROPIC_MODEL",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL",
    "ANTHROPIC_DEFAULT_SONNET_MODEL",
    "ANTHROPIC_DEFAULT_OPUS_MODEL",
    "ANTHROPIC_DEFAULT_FABLE_MODEL",
    "ANTHROPIC_SMALL_FAST_MODEL",
    "CLAUDE_CODE_SUBAGENT_MODEL",
)

DEFAULT_OUTPUT_CAP = 8000  # characters returned to the orchestrator


@dataclass(frozen=True)
class Role:
    name: str  # proxy model group
    tools: tuple[str, ...]
    permission_mode: str
    max_turns: int
    brief: str


READ_ONLY = ("Read", "Grep", "Glob")

ROLES: dict[str, Role] = {
    "explore": Role(
        "nim-explore", READ_ONLY, "default", 25,
        "Explore the codebase read-only and report what you find, with file paths and line numbers.",
    ),
    "plan": Role(
        "nim-plan", READ_ONLY, "default", 25,
        "Produce a concrete implementation plan. Do not change any files.",
    ),
    "code": Role(
        "nim-code", READ_ONLY + ("Edit", "Write"), "acceptEdits", 40,
        "Make the requested code change, then summarise exactly which files you changed and why.",
    ),
    "research": Role(
        "nim-research", READ_ONLY, "default", 20,
        "Research the question from local files and summarise the answer with sources.",
    ),
}


class WorkerError(RuntimeError):
    pass


def worker_env(
    base: Mapping[str, str],
    role: Role,
    proxy_url: str,
    session_key: str,
    config_dir: Path,
    context_tokens: int | None = None,
) -> dict[str, str]:
    env = {k: v for k, v in base.items() if k not in CREDENTIAL_ENV and k not in MODEL_ALIAS_ENV}
    env.pop(ENV_SESSION_KEY, None)
    env["ANTHROPIC_BASE_URL"] = proxy_url.rstrip("/").removesuffix("/v1")
    env["ANTHROPIC_API_KEY"] = session_key
    env["CLAUDE_CONFIG_DIR"] = str(config_dir)
    for name in MODEL_ALIAS_ENV:
        env[name] = role.name
    if context_tokens:
        # Role names are not Claude model ids, so Claude Code can't know the window.
        env["CLAUDE_CODE_MAX_CONTEXT_TOKENS"] = str(context_tokens)
    env["CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS"] = "1"
    env["DISABLE_TELEMETRY"] = "1"
    env["DISABLE_ERROR_REPORTING"] = "1"
    return env


def worker_args(claude: str, role: Role, task: str, cwd: Path) -> list[str]:
    return [
        claude,
        "--bare",
        "-p",
        task,
        "--model", role.name,
        "--tools", ",".join(role.tools),
        "--permission-mode", role.permission_mode,
        "--max-turns", str(role.max_turns),
        "--strict-mcp-config",
        "--add-dir", str(cwd),
        "--append-system-prompt", role.brief,
        "--output-format", "text",
    ]


def cap_output(text: str, limit: int = DEFAULT_OUTPUT_CAP) -> str:
    if len(text) <= limit:
        return text
    head = text[: limit * 3 // 4]
    tail = text[-(limit // 4):]
    return f"{head}\n\n[... {len(text) - len(head) - len(tail)} characters cut; full output in the saved file ...]\n\n{tail}"


# Claude Code's machine-readable diagnostic tags, e.g.
# [claude-code:unrecognized_model] {...}. Expected for proxy role names; noise here.
_DIAG_TAG = re.compile(r"^\[claude-code:[a-z_]+\]")


def clean_stderr(err: str) -> str:
    return "\n".join(line for line in err.splitlines() if not _DIAG_TAG.match(line.strip()))


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "task"


def run_worker(
    role_name: str,
    task: str,
    env: Mapping[str, str],
    *,
    cwd: Path | None = None,
    timeout: float = 900,
    output_cap: int = DEFAULT_OUTPUT_CAP,
) -> tuple[int, str, Path]:
    """Run one worker. Returns (exit code, capped output, path of full output)."""
    if role_name not in ROLES:
        raise WorkerError(f"Unknown role {role_name!r}. Roles: {', '.join(ROLES)}")
    proxy_url = env.get(ENV_PROXY_URL)
    session_key = env.get(ENV_SESSION_KEY)
    session_dir = env.get(ENV_SESSION_DIR)
    if not (proxy_url and session_key and session_dir):
        raise WorkerError("No Tasklend session found. Start one with `tasklend launch`.")
    claude = shutil.which("claude")
    if not claude:
        raise WorkerError("Claude Code (`claude`) not found on PATH.")

    role = ROLES[role_name]
    context_tokens = None
    profile = env.get(ENV_PROFILE)
    if not profile:  # sessions started by an older launch
        from .state import State

        profile = State.load().profile
    if profile:
        from .profiles import role_context_tokens

        try:
            context_tokens = role_context_tokens(profile, role.name)
        except (ValueError, KeyError):
            context_tokens = None
    cwd = cwd or Path.cwd()
    session = Path(session_dir)
    config_dir = session / "worker-home"
    config_dir.mkdir(parents=True, exist_ok=True)
    runs = session / "runs"
    runs.mkdir(parents=True, exist_ok=True)

    try:
        proc = subprocess.run(
            worker_args(claude, role, task, cwd),
            env=worker_env(env, role, proxy_url, session_key, config_dir, context_tokens),
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            stdin=subprocess.DEVNULL,
        )
        code, out, err = proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as exc:
        code, out, err = 124, exc.stdout or "", f"Worker timed out after {timeout:.0f}s."
        if isinstance(out, bytes):
            out = out.decode("utf-8", "replace")

    err = clean_stderr(err)
    full = out if not err.strip() else f"{out}\n\n[stderr]\n{err}"
    full = full.replace(session_key, "<redacted>")
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    saved = runs / f"{stamp}-{role_name}-{_slug(task)}.md"
    saved.write_text(full, encoding="utf-8")
    return code, cap_output(full, output_cap), saved

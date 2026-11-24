"""Command-line entry point: `agentroute`."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from importlib import metadata
from typing import Callable, Sequence

from . import LITELLM_PIN, __version__
from .notices import FREE_TIER_KEY, FREE_TIER_WARNING, is_accepted, require_acceptance
from .profiles import (
    DEFAULT_PROFILE,
    PROFILE_DESCRIPTIONS,
    PROFILE_WARNINGS,
    PROFILES,
    get_profile,
    models_in,
    notices_for,
)
from .proxy import NVIDIA_KEY_ENV, preflight_env
from .state import State

NOT_AFFILIATED = (
    "AgentRoute is not affiliated with or endorsed by Anthropic or NVIDIA."
)


def cmd_profiles(args, state: State, out: Callable[[str], None]) -> int:
    for name in PROFILES:
        mark = " (default)" if name == DEFAULT_PROFILE else ""
        current = "  <- current" if state.profile == name else ""
        out(f"{name}{mark}{current}")
        out(f"    {PROFILE_DESCRIPTIONS[name]}")
        for role, ids in get_profile(name).items():
            out(f"    {role:<13} {' -> '.join(ids)}")
    return 0


def cmd_init(args, state: State, out: Callable[[str], None], ask: Callable[[str], str]) -> int:
    profile = args.profile
    get_profile(profile)  # validates the name

    if profile in PROFILE_WARNINGS:
        out("")
        out("Warning: " + PROFILE_WARNINGS[profile])

    # Model licence notices: informational only.
    notices = notices_for(profile)
    if notices:
        out("")
        out("Model licence notices (for your information):")
        for text in notices:
            out("- " + text)
        out("Full licence names and links are in MODEL_LICENSES.md.")

    if not require_acceptance(
        state, FREE_TIER_KEY, FREE_TIER_WARNING, input_fn=ask, print_fn=out
    ):
        return 1

    state.profile = profile
    path = state.save()
    out("")
    out(f"Profile set to {profile}. Settings saved to {path}")
    return 0


def cmd_doctor(args, state: State, out: Callable[[str], None]) -> int:
    failures = 0

    def check(ok: bool, good: str, bad: str) -> None:
        nonlocal failures
        out(("[ok]   " if ok else "[fail] ") + (good if ok else bad))
        failures += 0 if ok else 1

    try:
        installed = metadata.version("litellm")
    except metadata.PackageNotFoundError:
        installed = None
    check(
        installed == LITELLM_PIN,
        f"LiteLLM {installed} matches the pin",
        f"LiteLLM is {installed or 'not installed'}; AgentRoute needs exactly {LITELLM_PIN}",
    )

    check(
        shutil.which("claude") is not None,
        "Claude Code (`claude`) found on PATH",
        "Claude Code (`claude`) not found on PATH",
    )

    key = nvidia_key()
    check(
        _key_looks_valid(key),
        f"{NVIDIA_KEY_ENV} is set",
        f"{NVIDIA_KEY_ENV} is missing or does not look like an nvapi- key",
    )

    redirect = main_session_redirect(os.environ)
    check(
        redirect is None,
        "Main Claude session will talk to Anthropic",
        f"ANTHROPIC_BASE_URL={redirect} sends your main Claude session elsewhere; "
        "clear it for this window (see `agentroute launch`)",
    )

    if redirect is None:
        leftover = leftover_credentials(os.environ)
        check(
            not leftover,
            "No leftover gateway credentials for the main session",
            f"{' and '.join(leftover)} would override your Anthropic login with a "
            "credential for another service; clear it for this window (see `agentroute launch`)",
        )

    problems = preflight_env(os.environ)
    check(not problems, "No disallowed LiteLLM features configured", "; ".join(problems))

    check(
        state.profile in PROFILES,
        f"Profile: {state.profile}",
        "No profile chosen yet; run `agentroute init`",
    )

    check(
        is_accepted(state, FREE_TIER_KEY, FREE_TIER_WARNING),
        "Free-tier notice accepted",
        "Free-tier notice not accepted (or its text changed); run `agentroute init`",
    )

    if state.profile in PROFILES and _key_looks_valid(key) and not args.offline:
        try:
            hosted = hosted_model_ids(key)
        except OSError as err:
            out(f"[note] Could not read NVIDIA's model list ({err.__class__.__name__}); skipped.")
        else:
            missing = [m.id for m in models_in(state.profile) if m.id not in hosted]
            check(
                not missing,
                f"All {state.profile} models are on NVIDIA's hosted list",
                "Not on NVIDIA's hosted list: " + ", ".join(missing),
            )

    if state.profile in PROFILES:
        for model in models_in(state.profile):
            if model.license == "not yet checked":
                out(f"[note] Licence not yet checked: {model.id}")

    out("")
    out("All checks passed." if not failures else f"{failures} check(s) failed.")
    return 0 if not failures else 1


NVIDIA_MODELS_URL = "https://integrate.api.nvidia.com/v1/models"


def hosted_model_ids(key: str, timeout: float = 15.0) -> set[str]:
    """Model ids on NVIDIA's hosted API. Sends only the key, no prompts."""
    import json
    import urllib.request

    request = urllib.request.Request(NVIDIA_MODELS_URL, headers={"Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(request, timeout=timeout) as resp:
        data = json.load(resp)
    return {m["id"] for m in data.get("data", [])}


def main_session_redirect(env) -> str | None:
    """The base URL if the main session would be sent somewhere other than Anthropic."""
    from urllib.parse import urlparse

    url = env.get("ANTHROPIC_BASE_URL", "").strip()
    if not url:
        return None
    host = (urlparse(url).hostname or "").lower()
    if host == "anthropic.com" or host.endswith(".anthropic.com"):
        return None
    return url


def leftover_credentials(env) -> list[str]:
    """Names (never values) of credentials that would replace the user's
    Anthropic login for the main session but don't look like Anthropic ones.

    Only meaningful when the main session talks to Anthropic (no redirect).
    ANTHROPIC_AUTH_TOKEN is a gateway bearer token; with no gateway it makes
    Anthropic reject the session (401) even after /login. ANTHROPIC_API_KEY is
    fine when it is a real Anthropic key (sk-ant-...).
    """
    found = []
    if env.get("ANTHROPIC_AUTH_TOKEN", "").strip():
        found.append("ANTHROPIC_AUTH_TOKEN")
    api_key = env.get("ANTHROPIC_API_KEY", "").strip()
    if api_key and not api_key.startswith("sk-ant-"):
        found.append("ANTHROPIC_API_KEY")
    return found


def _key_looks_valid(key: str) -> bool:
    return key.startswith("nvapi-") and len(key) > 40


def cmd_launch(args, state: State, out: Callable[[str], None], ask: Callable[[str], str]) -> int:
    from .launch import run_launch
    from .runtime import ProxyError

    if state.profile not in PROFILES:
        out("No profile chosen yet. Run `agentroute init` first.")
        return 1
    if not require_acceptance(state, FREE_TIER_KEY, FREE_TIER_WARNING, input_fn=ask, print_fn=out):
        return 1
    state.save()
    try:
        installed = metadata.version("litellm")
    except metadata.PackageNotFoundError:
        installed = None
    if installed != LITELLM_PIN:
        out(f"LiteLLM is {installed or 'not installed'}; AgentRoute needs exactly {LITELLM_PIN}.")
        return 1
    key = nvidia_key()
    if not _key_looks_valid(key):
        out(f"Set {NVIDIA_KEY_ENV} to your nvapi- key first.")
        return 1
    os.environ[NVIDIA_KEY_ENV] = key
    redirect = main_session_redirect(os.environ)
    if redirect and not args.keep_base_url:
        out(
            f"ANTHROPIC_BASE_URL is set to {redirect}, so your main Claude session would "
            "not talk to Anthropic. AgentRoute keeps the main session on Anthropic.\n"
            "Clear it for this window, then launch again:\n"
            "  PowerShell: Remove-Item Env:ANTHROPIC_BASE_URL, Env:ANTHROPIC_AUTH_TOKEN\n"
            "  bash:       unset ANTHROPIC_BASE_URL ANTHROPIC_AUTH_TOKEN\n"
            "If this gateway is deliberate, pass --keep-base-url."
        )
        return 1
    leftover = [] if redirect else leftover_credentials(os.environ)
    if leftover and not args.keep_base_url:
        names = " and ".join(leftover)
        items = ", ".join(f"Env:{n}" for n in leftover)
        out(
            f"{names} is set but doesn't look like an Anthropic credential (often left "
            "over from an Ollama or gateway setup). It would replace your Anthropic "
            "login and Claude would fail with \"401 Invalid bearer token\".\n"
            "Clear it for this window, then launch again:\n"
            f"  PowerShell: Remove-Item {items}\n"
            f"  bash:       unset {' '.join(leftover)}\n"
            "If it is deliberate, pass --keep-base-url."
        )
        return 1
    user_args = list(args.claude_args)
    if user_args and user_args[0] == "--":
        user_args = user_args[1:]
    try:
        return run_launch(state.profile, user_args, out=out)
    except ProxyError as err:
        out(f"Could not start the proxy: {err}")
        return 1


def nvidia_key(env=os.environ) -> str:
    """The NVIDIA key from the environment, or on Windows from the user's saved
    environment (apps started before `setx` don't see it yet)."""
    key = env.get(NVIDIA_KEY_ENV, "")
    if key or sys.platform != "win32":
        return key
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as reg:
            value, _ = winreg.QueryValueEx(reg, NVIDIA_KEY_ENV)
            return str(value)
    except OSError:
        return ""


def cmd_work(args, state: State, out: Callable[[str], None]) -> int:
    from .worker import ENV_SESSION_KEY, WorkerError, run_worker

    def run(env) -> tuple[int, str, object]:
        return run_worker(
            args.role, args.task, env, timeout=args.timeout, output_cap=args.max_chars
        )

    try:
        if os.environ.get(ENV_SESSION_KEY):
            code, output, saved = run(os.environ)
        else:
            result = _work_standalone(state, out, run)
            if isinstance(result, int):
                return result
            code, output, saved = result
    except WorkerError as err:
        out(str(err))
        return 1
    out(output.rstrip())
    out("")
    out(f"[agentroute] worker {args.role} exited {code}. Full output: {saved}")
    return code


def _work_standalone(state: State, out, run):
    """Run one worker outside `agentroute launch` (e.g. from the Claude Desktop
    app): start a private proxy for this worker only, then stop it. The proxy
    key lives only in memory for the length of this call."""
    from .runtime import ProxyError, ProxySession
    from .state import config_dir
    from .worker import ENV_PROFILE, ENV_PROXY_URL, ENV_SESSION_DIR, ENV_SESSION_KEY

    if state.profile not in PROFILES:
        out("No profile chosen yet. Ask the user to run `agentroute init` in a terminal.")
        return 1
    if not is_accepted(state, FREE_TIER_KEY, FREE_TIER_WARNING):
        out("The free-tier notice has not been accepted. Ask the user to run `agentroute init`.")
        return 1
    key = nvidia_key()
    if not _key_looks_valid(key):
        out(f"{NVIDIA_KEY_ENV} is not set. Ask the user to set it (see the README).")
        return 1
    base = dict(os.environ)
    base[NVIDIA_KEY_ENV] = key
    try:
        with ProxySession(state.profile, base_env=base) as session:
            env = dict(base)
            env.pop(NVIDIA_KEY_ENV)  # workers only need the proxy key
            env[ENV_PROXY_URL] = session.base_url
            env[ENV_SESSION_KEY] = session.master_key
            env[ENV_SESSION_DIR] = str(config_dir() / "standalone")
            env[ENV_PROFILE] = state.profile
            return run(env)
    except ProxyError as err:
        out(f"Could not start the proxy: {err}")
        return 1


def cmd_install_skill(args, out: Callable[[str], None]) -> int:
    from .skill import install_skill, remove_skill

    if args.remove:
        path = remove_skill()
        out(f"Removed {path}" if path else "No AgentRoute skill was installed.")
        return 0
    path = install_skill()
    out(f"Installed the AgentRoute skill at {path}")
    out("Claude Code sessions, including the Desktop app, can now dispatch workers.")
    return 0


def _utf8_stdio() -> None:
    """Model output often has characters a Windows cp1252 console can't encode."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agentroute",
        description="Run Claude Code as the orchestrator with worker subagents on open models.",
        epilog=NOT_AFFILIATED,
    )
    parser.add_argument("--version", action="version", version=f"agentroute {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Choose a model profile and accept the free-tier notice.")
    p_init.add_argument(
        "--profile",
        choices=list(PROFILES),
        default=DEFAULT_PROFILE,
        help=f"Model profile (default: {DEFAULT_PROFILE}).",
    )

    sub.add_parser("profiles", help="List model profiles and their routes.")
    p_doctor = sub.add_parser("doctor", help="Check that everything is set up.")
    p_doctor.add_argument(
        "--offline", action="store_true", help="Skip checking NVIDIA's live model list."
    )

    p_launch = sub.add_parser(
        "launch",
        help="Start the local proxy and your own Claude Code as the orchestrator.",
        description="Extra arguments after -- are passed to claude unchanged.",
    )
    p_launch.add_argument(
        "--keep-base-url",
        action="store_true",
        help="Start even if ANTHROPIC_BASE_URL or a gateway token would send the main session elsewhere.",
    )
    p_launch.add_argument("claude_args", nargs=argparse.REMAINDER)

    from .worker import DEFAULT_OUTPUT_CAP, ROLES as WORKER_ROLES

    p_work = sub.add_parser(
        "work", help="Run one worker agent (Claude runs this to delegate a task)."
    )
    p_work.add_argument("--role", required=True, choices=list(WORKER_ROLES))
    p_work.add_argument("--timeout", type=float, default=900, help="Seconds (default 900).")
    p_work.add_argument(
        "--max-chars", type=int, default=DEFAULT_OUTPUT_CAP,
        help=f"Cap on output returned (default {DEFAULT_OUTPUT_CAP}).",
    )
    p_work.add_argument("task")

    p_skill = sub.add_parser(
        "install-skill",
        help="Teach Claude Code (including the Desktop app) how to dispatch workers.",
    )
    p_skill.add_argument("--remove", action="store_true", help="Remove the skill instead.")
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    out: Callable[[str], None] = print,
    ask: Callable[[str], str] = input,
) -> int:
    _utf8_stdio()
    args = build_parser().parse_args(argv)
    state = State.load()
    if args.command == "init":
        return cmd_init(args, state, out, ask)
    if args.command == "profiles":
        return cmd_profiles(args, state, out)
    if args.command == "doctor":
        return cmd_doctor(args, state, out)
    if args.command == "launch":
        return cmd_launch(args, state, out, ask)
    if args.command == "work":
        return cmd_work(args, state, out)
    if args.command == "install-skill":
        return cmd_install_skill(args, out)
    return 2


if __name__ == "__main__":
    sys.exit(main())

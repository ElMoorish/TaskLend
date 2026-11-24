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

    key = os.environ.get(NVIDIA_KEY_ENV, "")
    check(
        _key_looks_valid(key),
        f"{NVIDIA_KEY_ENV} is set",
        f"{NVIDIA_KEY_ENV} is missing or does not look like an nvapi- key",
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
    if not _key_looks_valid(os.environ.get(NVIDIA_KEY_ENV, "")):
        out(f"Set {NVIDIA_KEY_ENV} to your nvapi- key first.")
        return 1
    user_args = list(args.claude_args)
    if user_args and user_args[0] == "--":
        user_args = user_args[1:]
    try:
        return run_launch(state.profile, user_args, out=out)
    except ProxyError as err:
        out(f"Could not start the proxy: {err}")
        return 1


def cmd_work(args, out: Callable[[str], None]) -> int:
    from .worker import WorkerError, run_worker

    try:
        code, output, saved = run_worker(
            args.role, args.task, os.environ, timeout=args.timeout, output_cap=args.max_chars
        )
    except WorkerError as err:
        out(str(err))
        return 1
    out(output.rstrip())
    out("")
    out(f"[agentroute] worker {args.role} exited {code}. Full output: {saved}")
    return code


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
    p_launch.add_argument("claude_args", nargs=argparse.REMAINDER)

    from .worker import DEFAULT_OUTPUT_CAP, ROLES as WORKER_ROLES

    p_work = sub.add_parser(
        "work", help="Run one worker agent (used by Claude inside `agentroute launch`)."
    )
    p_work.add_argument("--role", required=True, choices=list(WORKER_ROLES))
    p_work.add_argument("--timeout", type=float, default=900, help="Seconds (default 900).")
    p_work.add_argument(
        "--max-chars", type=int, default=DEFAULT_OUTPUT_CAP,
        help=f"Cap on output returned (default {DEFAULT_OUTPUT_CAP}).",
    )
    p_work.add_argument("task")
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    out: Callable[[str], None] = print,
    ask: Callable[[str], str] = input,
) -> int:
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
        return cmd_work(args, out)
    return 2


if __name__ == "__main__":
    sys.exit(main())

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
        key.startswith("nvapi-") and len(key) > 40,
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

    if state.profile in PROFILES:
        unverified = [m.id for m in models_in(state.profile) if not m.id_verified]
        for model_id in unverified:
            out(f"[note] Model id not yet confirmed on build.nvidia.com: {model_id}")

    out("")
    out("All checks passed." if not failures else f"{failures} check(s) failed.")
    return 0 if not failures else 1


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
    sub.add_parser("doctor", help="Check that everything is set up.")
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
    return 2


if __name__ == "__main__":
    sys.exit(main())

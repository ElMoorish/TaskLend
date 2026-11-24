"""A Claude Code skill that tells any session how to dispatch Tasklend workers.

`tasklend launch` passes these instructions with --append-system-prompt. The
Claude Desktop app starts Claude Code itself, so there the same instructions
come from a user skill instead. Installing it is an explicit, opt-in command;
Tasklend never changes Claude Code's settings files.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from .launch import orchestrator_prompt, work_command

SKILL_NAME = "tasklend"
MARKER = "<!-- installed by tasklend install-skill -->"
# The skill installed before the rename from AgentRoute to Tasklend.
LEGACY_SKILL_NAME = "agentroute"
LEGACY_MARKER = "<!-- installed by agentroute install-skill -->"


def claude_config_dir() -> Path:
    override = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(override) if override else Path.home() / ".claude"


def skill_dir() -> Path:
    return claude_config_dir() / "skills" / SKILL_NAME


def skill_text() -> str:
    body = orchestrator_prompt(work_command())
    return f"""---
name: {SKILL_NAME}
description: Delegate self-contained explore, plan, code or research tasks to Tasklend worker agents that run on open models, to save context and usage. Use when a task can be handed off with a complete brief, such as surveying a codebase, drafting a plan, or making a well-specified edit.
---

{MARKER}

{body}
Outside `tasklend launch` (for example in the Claude Desktop app), each worker
starts its own short-lived local proxy, which adds about 15 seconds per worker.
If the command says no profile is set or the notice was not accepted, ask the
user to run `tasklend init` in a terminal; do not try to accept it yourself.
"""


def install_skill() -> Path:
    target = skill_dir()
    target.mkdir(parents=True, exist_ok=True)
    path = target / "SKILL.md"
    if path.exists() and MARKER not in path.read_text(encoding="utf-8", errors="replace"):
        raise FileExistsError(f"{path} exists and was not created by Tasklend; not overwriting.")
    path.write_text(skill_text(), encoding="utf-8")
    return path


def remove_skill() -> Path | None:
    target = skill_dir()
    path = target / "SKILL.md"
    if not path.exists():
        return None
    if MARKER not in path.read_text(encoding="utf-8", errors="replace"):
        raise FileExistsError(f"{path} was not created by Tasklend; not removing.")
    shutil.rmtree(target)
    return path


def remove_legacy_skill() -> Path | None:
    """Remove the old AgentRoute skill, but only if AgentRoute installed it."""
    target = claude_config_dir() / "skills" / LEGACY_SKILL_NAME
    path = target / "SKILL.md"
    if not path.is_file():
        return None
    if LEGACY_MARKER not in path.read_text(encoding="utf-8", errors="replace"):
        return None
    shutil.rmtree(target)
    return path

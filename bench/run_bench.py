"""Token benchmark: plain Claude Code (A) vs Claude Code + AgentRoute workers (B).

Usage (from the repo root, any shell):
    python bench/run_bench.py A 1
    python bench/run_bench.py B 1

Writes bench/logs/run<MODE><N>.json (Claude's -p JSON result plus wall time)
and, for B, a copy of AgentRoute's temporary session folder (proxy log, worker
outputs, worker transcripts), which AgentRoute deletes when Claude exits.
No AgentRoute source is changed.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LOGS = REPO / "bench" / "logs"

TASK = (
    "Explain how AgentRoute starts its LiteLLM proxy and runs its preflight checks. "
    "List every file involved and point out one possible bug."
)
DELEGATE = (
    "\n\nDelegate the file reading to an AgentRoute explore worker (role explore) "
    "instead of reading the source files yourself. Only open a file yourself if you "
    "need to check a specific claim the worker made."
)
MODEL = "sonnet"

# Same isolation for both runs: no user-level settings (plugins, hooks) and no
# skills, so the only difference is AgentRoute's appended prompt + Bash access to it.
COMMON = [
    "--output-format", "json",
    "--model", MODEL,
    "--setting-sources", "project,local",
    "--disable-slash-commands",
]
TOOLS_A = ["--allowedTools", "Read", "Grep", "Glob", "Task", "Agent"]
TOOLS_B = TOOLS_A + ["Bash(*agentroute work*)"]


def clean_env() -> dict[str, str]:
    env = dict(os.environ)
    for k in ("ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN"):
        env.pop(k, None)
    local_bin = str(Path.home() / ".local" / "bin")
    env["PATH"] = local_bin + os.pathsep + env.get("PATH", "")
    return env


def snapshot_agentroute_tmp(dest: Path, stop: threading.Event, before: set[str]) -> None:
    """Copy new %TEMP%/agentroute-* folders while they exist (they are deleted on exit)."""
    tmp = Path(tempfile.gettempdir())
    while not stop.is_set():
        for d in tmp.glob("agentroute-*"):
            if d.name in before or not d.is_dir():
                continue
            for f in d.rglob("*"):
                if not f.is_file():
                    continue
                target = dest / d.name / f.relative_to(d)
                try:
                    st = f.stat()
                    if target.exists() and target.stat().st_size == st.st_size:
                        continue
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(f, target)
                except OSError:
                    pass
        stop.wait(0.5)


def main() -> int:
    mode, n = sys.argv[1].upper(), sys.argv[2]
    LOGS.mkdir(parents=True, exist_ok=True)
    claude = shutil.which("claude", path=clean_env()["PATH"])
    uv = shutil.which("uv", path=clean_env()["PATH"])
    if mode == "A":
        cmd = [claude, "-p", TASK, *COMMON, *TOOLS_A]
    else:
        cmd = [uv, "run", "agentroute", "launch", "--", "-p", TASK + DELEGATE, *COMMON, *TOOLS_B]

    stop = threading.Event()
    watcher = None
    if mode == "B":
        before = {d.name for d in Path(tempfile.gettempdir()).glob("agentroute-*")}
        watcher = threading.Thread(
            target=snapshot_agentroute_tmp, args=(LOGS / f"run{mode}{n}-session", stop, before)
        )
        watcher.start()

    t0 = time.monotonic()
    proc = subprocess.run(cmd, cwd=REPO, env=clean_env(), capture_output=True,
                          text=True, encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL)
    wall = time.monotonic() - t0
    stop.set()
    if watcher:
        watcher.join()

    (LOGS / f"run{mode}{n}.stdout.txt").write_text(proc.stdout, encoding="utf-8")
    (LOGS / f"run{mode}{n}.stderr.txt").write_text(proc.stderr, encoding="utf-8")
    result = None
    for line in reversed(proc.stdout.splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                result = json.loads(line)
                break
            except json.JSONDecodeError:
                pass
    record = {"mode": mode, "run": n, "cmd": cmd, "exit": proc.returncode,
              "wall_seconds": round(wall, 1), "result": result}
    (LOGS / f"run{mode}{n}.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(f"exit={proc.returncode} wall={wall:.1f}s parsed={'yes' if result else 'no'}")
    return 0 if result else 1


if __name__ == "__main__":
    sys.exit(main())

"""Summarise benchmark runs: python bench/analyze.py A1 B1 [A2 B2 ...]"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LOGS = REPO / "bench" / "logs"
MAIN_PROJECTS = Path.home() / ".claude" / "projects" / "E--AgentRoute"


def assistant_usages(jsonl: Path):
    """Deduplicated usage per API message (Claude Code writes one line per content block)."""
    seen, out = set(), []
    for line in jsonl.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        msg = rec.get("message") or {}
        if rec.get("type") != "assistant" or "usage" not in msg:
            continue
        mid = msg.get("id") or rec.get("uuid")
        if mid in seen:
            continue
        seen.add(mid)
        out.append((msg.get("model"), msg["usage"]))
    return out


def ctx(u):
    return u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0) + u.get("cache_creation_input_tokens", 0)


def summarise(tag: str) -> dict:
    rec = json.loads((LOGS / f"run{tag}.json").read_text(encoding="utf-8"))
    r = rec["result"]
    u = r["usage"]
    row = {
        "run": tag,
        "wall_s": rec["wall_seconds"],
        "turns": r["num_turns"],
        "input": u["input_tokens"],
        "cache_create": u["cache_creation_input_tokens"],
        "cache_read": u["cache_read_input_tokens"],
        "output": u["output_tokens"],
        "total": u["input_tokens"] + u["cache_creation_input_tokens"] + u["cache_read_input_tokens"] + u["output_tokens"],
        "cost_usd_list": round(r["total_cost_usd"], 4),
        "subagents": r.get("subagent_stats", {}).get("spawned", 0),
    }
    main = MAIN_PROJECTS / f"{r['session_id']}.jsonl"
    if main.exists():
        us = assistant_usages(main)
        row["api_calls"] = len(us)
        row["final_context"] = ctx(us[-1][1]) + us[-1][1].get("output_tokens", 0) if us else None
    # Worker side (B only): transcripts copied from AgentRoute's temp folder.
    workers = []
    for jl in (LOGS / f"run{tag}-session").rglob("worker-home/projects/**/*.jsonl") if (LOGS / f"run{tag}-session").exists() else []:
        us = assistant_usages(jl)
        workers.append({
            "transcript": str(jl.relative_to(REPO)),
            "models": sorted({m for m, _ in us if m}),
            "api_calls": len(us),
            "input_incl_cache": sum(ctx(x) for _, x in us),
            "output": sum(x.get("output_tokens", 0) for _, x in us),
            "peak_context": max((ctx(x) for _, x in us), default=0),
        })
    if workers:
        row["workers"] = workers
    return row


if __name__ == "__main__":
    rows = [summarise(t) for t in sys.argv[1:]]
    print(json.dumps(rows, indent=2))
    (LOGS / "summary.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")

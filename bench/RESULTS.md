# AgentRoute token benchmark (2026-11-24)

**Task (same for every run):** "Explain how AgentRoute starts its LiteLLM proxy and
runs its preflight checks. List every file involved and point out one possible
bug." Repo: this one (about 1,400 lines of Python).

**Run B adds one instruction:** delegate the file reading to an AgentRoute explore
worker, and open a file yourself only to check a specific claim.

**Setup:**
- Main model: Claude Sonnet 5.5 (`--model sonnet`) for every run.
- Claude Code 2.1.331.
- Both runs used `--setting-sources project,local --disable-slash-commands`, so no user plugins, hooks or skills were loaded.
- Run A was allowed `Read`, `Grep`, `Glob`, `Task` and `Agent`. Run B was allowed the same plus `Bash(*agentroute work*)`.
- Run B went through `agentroute launch` (profile `us-eu-origin`).

## Main Claude session (what your Anthropic plan pays for)

| Run | Wall time | Turns | API calls | Input | Cache write | Cache read | Output | Total tokens | List cost | Final context |
|---|---|---|---|---|---|---|---|---|---|---|
| A1 plain | 28.9 s | 8 | 5 | 10 | 60,944 | 199,148 | 2,773 | 262,875 | $0.291 | 62.8k |
| A2 plain | 30.8 s | 9 | 5 | 10 | 28,196 | 228,221 | 3,654 | 260,081 | $0.172 | 63.6k |
| B1 AgentRoute | 198.9 s | 4 | 3 | 6 | 55,705 | 89,495 | 2,301 | 147,507 | $0.255 | 57.4k |
| B2 AgentRoute | 134.3 s | 4 | 4 | 8 | 23,543 | 180,180 | 2,832 | 206,563 | $0.141 | 59.8k |
| **A average** | 29.9 s | 8.5 | 5 | | | | 3,214 | 261,478 | $0.231 | 63.2k |
| **B average** | 166.6 s | 4 | 3.5 | | | | 2,567 | 177,035 | $0.198 | 58.6k |
| **B vs A** | **5.6x slower** | | | | | | -20% | **-32%** | **-15%** | **-7% (-4.6k)** |

- "Final context" is the input of the last API call plus its output, from the session transcript.
- "List cost" is Claude Code's `total_cost_usd`. On a Pro or Max plan this shows usage weight, not money billed.
- The cost difference between runs 1 and 2 comes mostly from prompt-cache warmth (cache write of about 60k tokens vs about 25k). It isn't caused by AgentRoute.

## Worker side (NVIDIA NIM free tier, not Anthropic)

| Run | Worker | Proxy group | API calls | Input tokens (sum over calls) | Output | Peak worker context |
|---|---|---|---|---|---|---|
| B1 | explore | `nim-explore` | 9 | 111,270 | 16,810 | 18.7k |
| B2 | explore | `nim-explore` | 7 | 63,700 | 9,479 | 18.7k |

- `nim-explore` in profile `us-eu-origin` is `nvidia/nemotron-3.5-super-vl-120b-a12b`, falling back to `nemotron-3.5-lightning-30b-a3b`.
- The proxy log at INFO level records only `POST /v1/messages 200`. It doesn't show which of the two models served each call.
- Worker token counts are as LiteLLM reported them back to the worker's Claude Code. They come from the worker transcripts copied out of AgentRoute's temp folder.

## Where the savings come from, and their limit

- About 52k of the main context is fixed: system prompt, tool definitions and CLAUDE.md. That is identical in A and B, which is why the final context shrinks only about 7%.
- What AgentRoute removes is the source text.
  - Run A1 pulled about 29k characters of files into the main context: `proxy.py`, `_proxy_main.py`, `runtime.py` and part of `cli.py`.
  - Run B1 pulled in about 8.8k characters of capped worker output, plus about 5.7k of follow-up checks: a grep of the worker's saved output and a 65-line `Read` of `proxy.py`.
- Because there are fewer round trips (3–4 API calls instead of 5), the cache-read total drops about 32%. Re-reading the growing context on every call is the biggest token line item.
- On a repo this small, the savings are modest. They should grow with the amount of code a task needs to read. That is not measured here.
- The cost is wall time: 2–3 minutes instead of 30 seconds. Most of it is the worker on the NVIDIA free tier (7–9 sequential calls).

## Answer quality

| Run | Right files? | Bug named | Real? |
|---|---|---|---|
| A1 | Yes. `cli.py`, `launch.py`, `runtime.py`, `proxy.py`, `_proxy_main.py`, `__init__.py`, `profiles.py`, the pin in `pyproject.toml`/`uv.lock`. Says it only grepped `launch.py`. | `non_loopback_addresses()` uses `gethostbyname_ex` and returns `[]` on `OSError`, so the exposure check can pass without testing anything (IPv4 only, misses some adapters). | Yes. It is a fail-open in a defence-in-depth check, and low risk because the proxy binds to 127.0.0.1. |
| A2 | Yes, the same set. Says it didn't open `launch.py`/`worker.py`. | `ProxySession.start()` creates the temp dir and writes the config before the `try`. If `write_config`, `open` or `Popen` raises, `stop()` never runs and the `agentroute-*` dir leaks. Also mentions the port race. | Yes. `runtime.py` `mkdtemp` and `write_config` are outside the `try`/`stop()` path. Minor. |
| B1 | Yes. Lists `__init__`, `__main__`, `cli`, `launch`, `runtime`, `proxy`, `_proxy_main`, `state`, `notices`, `profiles`. Correctly says `worker.py`/`skill.py` aren't on the path. Checked the worker's `proxy.py` claims itself. | TOCTOU in `free_loopback_port()`: the port is closed before LiteLLM binds it. Also mentions the same exposure-check fail-open as A1. | Yes. It is a classic race. It's rare, and it surfaces as "LiteLLM exited during startup". |
| B2 | Yes. Same files, plus `worker.py`/`skill.py` described by role, plus `pyproject.toml`. | The same port race, plus the same temp-dir leak as A2. | Yes, both. |

All four answers were correct and of similar depth. The B answers named more peripheral files (`state.py`, `notices.py`), and both B runs checked the worker's key claim before reporting.

## Reproduce

From the repo root, in any shell (the scripts clear `ANTHROPIC_BASE_URL`/`ANTHROPIC_AUTH_TOKEN` themselves):

```
python bench/run_bench.py A 1
python bench/run_bench.py B 1
python bench/analyze.py A1 B1
python bench/record_b.py      # optional: records Run B in a console window with ffmpeg
```

What `run_bench.py` runs:

```
# A
claude -p "<task>" --output-format json --model sonnet --setting-sources project,local --disable-slash-commands --allowedTools Read Grep Glob Task Agent
# B
uv run agentroute launch -- -p "<task + delegate instruction>" --output-format json --model sonnet --setting-sources project,local --disable-slash-commands --allowedTools Read Grep Glob Task Agent "Bash(*agentroute work*)"
```

For Run B, `run_bench.py` copies AgentRoute's `%TEMP%\agentroute-*` folder while the run is live, because AgentRoute deletes it on exit. That copy holds the proxy log, the worker's saved output and the worker transcript. I checked the copied logs: they contain no `sk-ar-` or `nvapi-` key strings.

## Caveats

- All four runs were started from inside a Claude Code Desktop session, so the child `claude` inherited that session's `CLAUDE_*` environment variables. A and B inherited the same set, so the comparison holds, but absolute numbers in a fresh terminal may differ slightly.
- One run of each kind is not much data. Each pair agreed in direction: B used fewer main-session tokens and took longer in both pairs.

## Media

- `media/runB-final-answer.png` is the end of an interactive Run B in a real console window (`agentroute launch`, "Brewed for 2m 41s").
- The video recording (`record_b.py`, ffmpeg gdigrab by window handle) did not produce a usable file:
  - Attempt 1: the script couldn't find the console window.
  - Attempt 2: ffmpeg stopped partway and left an MP4 with no index. The script now writes fragmented MP4 to avoid that.
  - Attempt 3: the console window closed before Claude started, so ffmpeg reported "invalid window handle".
- I stopped there.

# AgentRoute

AgentRoute is a Python command-line tool that works with Claude Code. Claude
stays the orchestrator under your own Anthropic login, and worker subagents
(explore, plan, code, research) run on open models through a local LiteLLM
proxy and NVIDIA NIM, with fallbacks.

> Status: pre-alpha. Not yet tested end to end against NVIDIA's API.

## How it works

1. `agentroute launch` starts a LiteLLM proxy on `127.0.0.1`, then starts your
   own `claude`, unmodified. The main session talks straight to Anthropic with
   your own login; AgentRoute does not proxy, read or store it.
2. Claude is told it can hand self-contained tasks to workers by running
   `agentroute work --role explore|plan|code|research "<task>"`.
3. Each worker is a separate headless Claude Code run (`claude --bare -p`) whose
   model calls go to the local proxy and on to NVIDIA NIM. In `--bare` mode
   Claude Code never reads OAuth tokens or the keychain, and the worker's only
   credential is the proxy's per-session key. Workers get a private config
   folder, so they never see your Claude login or settings.
4. Worker output is capped before it returns to Claude (full output is saved
   to a file), which keeps the main session's context small.

Workers have only the tools their role needs: explore, plan and research are
read-only; code can also edit files. No worker can run shell commands.

## Before you start: the NVIDIA free tier

NVIDIA's hosted API (`integrate.api.nvidia.com` with an `nvapi-` key) is a
trial service. It is for non-production testing and evaluation only, and NVIDIA
may use your prompts and outputs to train models. Do not send confidential code,
client IP, personal data, or HIPAA or PCI data. AgentRoute asks you to type
`I understand` before first use, and asks again only if this notice changes. The
same notice applies to OpenRouter `:free` models, which are off by default.

Sessions routed through AgentRoute fall outside any business associate
agreement (BAA) you may have with Anthropic. Self-hosted NIM through the NVIDIA
Developer Program is also for prototyping, research, development and testing
only; production use needs an NVIDIA AI Enterprise licence.

## Install

Planned: installation with [uv](https://docs.astral.sh/uv/). Until a release
exists, run from a checkout:

```
uv sync --locked
uv run agentroute init
uv run agentroute doctor
uv run agentroute launch
```

Arguments after `--` go to `claude` unchanged, for example
`uv run agentroute launch -- --continue`.

### From the Claude Desktop app

The Desktop app starts Claude Code itself, so `agentroute launch` isn't used
there. Instead, run this once in a terminal:

```
uv run agentroute install-skill
```

It adds an `agentroute` skill to your Claude Code skills folder, so every
session, including the Desktop app's, knows how to dispatch workers. Outside
`launch`, each worker starts its own private proxy and stops it when done,
which adds about 15 seconds per worker. Remove the skill with
`uv run agentroute install-skill --remove`.

`NVIDIA_NIM_API_KEY` must be set in your environment. AgentRoute never writes
API keys to disk and never reads or stores your Anthropic credentials.

## Model profiles

| Profile | What it contains |
| --- | --- |
| `us-eu-origin` (default) | US and EU models only. No PRC-origin models in any role. |
| `permissive` | Only weights under Apache 2.0, MIT or OpenMDW. |
| `research-all` | Every catalog model, including PRC-origin ones, with a warning. |

Run `agentroute profiles` to see which model serves each role. Licence details
are in [MODEL_LICENSES.md](MODEL_LICENSES.md).

## How the proxy is run

- Bound to `127.0.0.1` only.
- A new random master key for each session, kept in memory and passed to the
  proxy through its environment.
- No database, admin UI users, SSO, JWT or enterprise licence. AgentRoute
  refuses to start the proxy if any of these are configured, and the admin UI,
  login and SSO routes answer 404.
- Stopped, and its temporary files deleted, when Claude Code exits.
- LiteLLM pinned to exactly `1.106.3`, installed from `uv.lock` with hashes.
  See [SECURITY.md](SECURITY.md).

## License

Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE) and
[NOTICE](NOTICE). Contributions need a DCO sign-off; see
[CONTRIBUTING.md](CONTRIBUTING.md).

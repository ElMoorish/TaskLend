# AgentRoute

AgentRoute is a Python command-line tool that works with Claude Code. Claude
stays the orchestrator under your own Anthropic login, and worker subagents
(explore, plan, code, research) run on open models through a local LiteLLM
proxy and NVIDIA NIM, with fallbacks.

> Status: pre-alpha. `init`, `profiles` and `doctor` work. Launching Claude Code
> with routed subagents is not built yet.

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
```

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
  refuses to start the proxy if any of these are configured.
- LiteLLM pinned to exactly `1.106.3`, installed from `uv.lock` with hashes.
  See [SECURITY.md](SECURITY.md).

## License

Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE) and
[NOTICE](NOTICE). Contributions need a DCO sign-off; see
[CONTRIBUTING.md](CONTRIBUTING.md).

# AgentRoute

AgentRoute (working name: nimcc) is a Python command-line tool that launches an
unmodified Claude Code session and routes its worker subagents to open models.

> Status: pre-alpha. Project skeleton only; no working code yet.

## How it works

- **Claude stays the orchestrator.** The main Claude Code session runs under your
  own Anthropic login and acts as the "CEO": it plans, delegates, and reviews.
- **Workers run on open models.** Subagents for exploring, planning, coding and
  research are sent through a LiteLLM proxy to NVIDIA NIM models, with fallbacks.
- **Goals:** get more done through agent dispatch, keep the main context small,
  and use less of your main Claude allowance.

## Design decisions so far

- Default profile `us-eu-origin`: no Chinese-origin models by default.
- Planning worker model: Nemotron 3.5.
- LiteLLM pinned exactly to `1.106.3`, installed with hash checking.
- The proxy binds to `localhost` only, uses a random master key per session,
  and runs with no admin UI, database or SSO.
- Before first use you must type `I understand` to accept the NVIDIA free-tier
  notice. It is shown again only when its text changes. The same notice is
  reused for OpenRouter free models.
- Model license notices are shown for information only.

## Install

Planned: installation with [uv](https://docs.astral.sh/uv/).

```
uv tool install agentroute   # not published yet
```

## License

Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE) and
[NOTICE](NOTICE).

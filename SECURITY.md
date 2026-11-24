# Security

## LiteLLM pin

LiteLLM is pinned to exactly `1.106.3` in `pyproject.toml`, and `uv.lock`
records the hash of every file. Release 1.107.0 (2026-10-21) was trojanized, so
a version range must never be used.

To bump the pin:

1. Read LiteLLM's security advisories for the new version.
2. Wait a few days after the release before adopting it.
3. Change `pyproject.toml` and `LITELLM_PIN` in `src/tasklend/__init__.py`,
   run `uv lock`, and land the version and hash changes in one reviewed commit.

Install only with `uv sync --locked`. The test suite fails if the files dropped
by the 1.107.0 release are present, or if Tasklend imports LiteLLM's
proprietary `enterprise` code.

## Known LiteLLM advisories

Six unfixed advisories affect LiteLLM 1.106.x. All of them sit in login, SSO,
JWT or team-admin features. Tasklend runs the proxy on loopback with one
master key and none of those features, and refuses to start if they are
configured. They are recorded as accepted, with reasons, in the project's
pre-release checklist.

## Reporting a problem

Please report security issues privately to the maintainer rather than in a
public issue.

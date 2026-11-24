"""Entry point for the LiteLLM proxy child process.

Runs LiteLLM's own CLI in this Python process (so stopping it stops the real
server, with no launcher in between) after adding one middleware that answers
404 for the admin UI, login and SSO routes. AgentRoute uses none of them.
"""

from __future__ import annotations

BLOCKED_PREFIXES = (
    "/ui",
    "/sso",
    "/litellm-asset-prefix",
    "/login",
    "/v2/login",
    "/fallback/login",
    "/onboarding",
)


def is_blocked(path: str) -> bool:
    path = path.lower()
    return any(path == p or path.startswith(p + "/") for p in BLOCKED_PREFIXES)


def main() -> None:
    from litellm.proxy import proxy_server
    from litellm.proxy.proxy_cli import run_server
    from starlette.responses import PlainTextResponse

    @proxy_server.app.middleware("http")
    async def _block_admin_routes(request, call_next):
        if is_blocked(request.url.path):
            return PlainTextResponse("Not found", status_code=404)
        return await call_next(request)

    # uvicorn loads "litellm.proxy.proxy_server:app", which is the module object
    # imported above, so the middleware applies.
    run_server(prog_name="litellm")


if __name__ == "__main__":
    main()

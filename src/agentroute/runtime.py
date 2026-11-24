"""Running the LiteLLM proxy for one session.

Lifecycle: write a secret-free config to a private temp dir, start LiteLLM on
127.0.0.1 with a fresh master key passed only through the child environment,
wait for it to be healthy, refuse to continue if it is reachable from another
interface or serves the unauthenticated SSO debug routes, and stop it on exit.
"""

from __future__ import annotations

import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping

from .proxy import (
    LOOPBACK,
    free_loopback_port,
    new_master_key,
    preflight_env,
    proxy_args,
    proxy_env,
    reachable_from_outside,
    write_config,
)
from ._proxy_main import IDENTITY_ENV, IDENTITY_PATH

SSO_PROBE_PATHS = ("/sso/debug/login", "/sso/debug/callback", "/ui")
SAFE_PROBE_STATUSES = {401, 403, 404, 405}


class ProxyError(RuntimeError):
    pass


class PortTaken(Exception):
    """The chosen port was taken by another process before LiteLLM bound it."""


START_ATTEMPTS = 3


def proxy_command() -> list[str]:
    # Run in this interpreter directly, not via the litellm.exe launcher, so
    # terminating the child stops the real server.
    return [sys.executable, "-m", "agentroute._proxy_main"]


def _remove_dir(path: Path, attempts: int = 20) -> None:
    # On Windows the log file can stay locked for a moment after the child exits.
    for _ in range(attempts):
        shutil.rmtree(path, ignore_errors=True)
        if not path.exists():
            return
        time.sleep(0.25)


def http_status(url: str, timeout: float = 2.0, headers: Mapping[str, str] | None = None) -> int | None:
    """Status code for a GET, or None when nothing answers."""
    request = urllib.request.Request(url, headers=dict(headers or {}))
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            return resp.status
    except urllib.error.HTTPError as err:
        return err.code
    except (urllib.error.URLError, OSError):
        return None


def unsafe_sso_routes(base_url: str, status_fn: Callable[[str], int | None] = http_status) -> list[str]:
    """SSO debug routes that answer without auth (they must not)."""
    bad = []
    for path in SSO_PROBE_PATHS:
        status = status_fn(base_url + path)
        if status is not None and status not in SAFE_PROBE_STATUSES:
            bad.append(f"{path} answered {status}")
    return bad


@dataclass
class ProxySession:
    profile: str
    base_env: Mapping[str, str] = field(default_factory=lambda: dict(os.environ))
    startup_timeout: float = 90.0

    master_key: str = field(init=False, default="")
    port: int = field(init=False, default=0)
    workdir: Path | None = field(init=False, default=None)
    process: subprocess.Popen | None = field(init=False, default=None)
    identity: str = field(init=False, default="")

    @property
    def base_url(self) -> str:
        # No trailing /v1: the Anthropic SDK adds /v1/messages itself.
        return f"http://{LOOPBACK}:{self.port}"

    @property
    def log_path(self) -> Path:
        assert self.workdir
        return self.workdir / "proxy.log"

    def start(self) -> "ProxySession":
        problems = preflight_env(self.base_env)
        if problems:
            raise ProxyError("\n".join(problems))
        self.workdir = Path(tempfile.mkdtemp(prefix="agentroute-"))
        config = write_config(self.profile, self.workdir / "litellm_config.json")
        self.master_key = new_master_key()
        try:
            for attempt in range(1, START_ATTEMPTS + 1):
                try:
                    self._spawn(config)
                    self._wait_ready()
                    break
                except PortTaken:
                    self._kill_child()
                    if attempt == START_ATTEMPTS:
                        raise ProxyError(
                            "Could not get a free local port for the proxy.\n" + self.log_tail()
                        ) from None
            self._check_exposure()
        except BaseException:
            self.stop()
            raise
        return self

    def _spawn(self, config: Path) -> None:
        # The port is chosen, then released, then bound by LiteLLM, so another
        # process can take it in between. _wait_ready detects that (identity
        # token) and start() retries on a new port.
        self.port = free_loopback_port()
        self.identity = secrets.token_urlsafe(24)
        env = proxy_env(self.base_env, self.master_key)
        env[IDENTITY_ENV] = self.identity
        with open(self.log_path, "wb") as log:
            self.process = subprocess.Popen(
                [*proxy_command(), *proxy_args(config, self.port)],
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
            )

    def _is_ours(self) -> bool | None:
        """True if our proxy answers, False if something else does, None if nothing."""
        try:
            with urllib.request.urlopen(self.base_url + IDENTITY_PATH, timeout=2.0) as resp:
                return resp.read().decode("utf-8", "replace").strip() == self.identity
        except urllib.error.HTTPError:
            return False
        except (urllib.error.URLError, OSError):
            return None

    def _wait_ready(self) -> None:
        deadline = time.monotonic() + self.startup_timeout
        while time.monotonic() < deadline:
            ours = self._is_ours()
            if ours:
                return
            if self.process and self.process.poll() is not None:
                if "address already in use" in self.log_tail(80).lower() or "10048" in self.log_tail(80):
                    raise PortTaken()
                raise ProxyError("LiteLLM exited during startup.\n" + self.log_tail())
            if ours is False:
                # Another program is listening on our port: never send it the key.
                raise PortTaken()
            time.sleep(0.5)
        raise ProxyError("LiteLLM did not become ready in time.\n" + self.log_tail())

    def _kill_child(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.kill()
            self.process.wait(timeout=10)
        self.process = None

    def _check_exposure(self) -> None:
        exposed = reachable_from_outside(self.port)
        if exposed:
            raise ProxyError(f"Proxy is reachable from {', '.join(exposed)}; stopping.")
        bad = unsafe_sso_routes(self.base_url)
        if bad:
            raise ProxyError("Proxy serves admin or SSO routes without auth: " + "; ".join(bad))

    def log_tail(self, lines: int = 20) -> str:
        try:
            text = self.log_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""
        return "\n".join(text.splitlines()[-lines:]).replace(self.master_key, "<redacted>")

    def stop(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        self.process = None
        self.master_key = ""
        if self.workdir:
            _remove_dir(self.workdir)
            self.workdir = None

    def __enter__(self) -> "ProxySession":
        return self.start()

    def __exit__(self, *exc) -> None:
        self.stop()

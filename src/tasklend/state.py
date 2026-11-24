"""Small on-disk settings file.

Holds only non-secret settings: the chosen profile and which notice texts were
accepted. API keys, the proxy master key and any Anthropic credentials are never
written here.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path


def config_dir() -> Path:
    override = os.environ.get("TASKLEND_CONFIG_DIR")
    if override:
        return Path(override)
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "tasklend"
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "tasklend"


# The project was called AgentRoute before it became Tasklend.
LEGACY_NAME = "agentroute"


def _migrate_legacy_settings(path: Path) -> None:
    """Copy settings saved under the old name, once, if there are none yet."""
    if path.exists() or os.environ.get("TASKLEND_CONFIG_DIR"):
        return
    legacy = path.parent.parent / LEGACY_NAME / "settings.json"
    if legacy.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(legacy.read_text(encoding="utf-8"), encoding="utf-8")


@dataclass
class State:
    profile: str | None = None
    accepted_notices: dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path | None = None) -> "State":
        if path is None:
            path = config_dir() / "settings.json"
            _migrate_legacy_settings(path)
        if not path.exists():
            return cls()
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            profile=data.get("profile"),
            accepted_notices=dict(data.get("accepted_notices", {})),
        )

    def save(self, path: Path | None = None) -> Path:
        path = path or config_dir() / "settings.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {"profile": self.profile, "accepted_notices": self.accepted_notices}
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        return path

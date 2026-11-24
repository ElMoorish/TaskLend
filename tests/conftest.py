import pytest


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    """Keep every test's settings file out of the real user config dir."""
    monkeypatch.setenv("AGENTROUTE_CONFIG_DIR", str(tmp_path / "config"))
    return tmp_path / "config"


@pytest.fixture(autouse=True)
def no_registry_key(monkeypatch):
    """Tests must not pick up the real NVIDIA key from the Windows registry."""
    import os

    monkeypatch.setattr(
        "agentroute.cli.nvidia_key", lambda env=None: os.environ.get("NVIDIA_NIM_API_KEY", "")
    )


@pytest.fixture(autouse=True)
def isolated_claude_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))

import pytest


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    """Keep every test's settings file out of the real user config dir."""
    monkeypatch.setenv("AGENTROUTE_CONFIG_DIR", str(tmp_path / "config"))
    return tmp_path / "config"

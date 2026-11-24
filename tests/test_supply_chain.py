"""Supply-chain guards from the pre-release legal checklist."""

import site
import sys
from importlib import metadata
from pathlib import Path

import agentroute

SRC = Path(agentroute.__file__).parent

# Files dropped by the trojanized LiteLLM 1.107.0 release (2026-10-21).
MALICIOUS_FILES = ("litellm_init.pth", "cook.pth", "cook.py")


def site_dirs():
    dirs = set(site.getsitepackages()) | {site.getusersitepackages()}
    dirs |= {p for p in sys.path if p.endswith("site-packages")}
    return [Path(d) for d in dirs if Path(d).is_dir()]


def test_litellm_pin_matches():
    assert metadata.version("litellm") == agentroute.LITELLM_PIN


def test_pyproject_pins_litellm_exactly():
    pyproject = (SRC.parent.parent / "pyproject.toml").read_text(encoding="utf-8")
    assert f'"litellm[proxy]=={agentroute.LITELLM_PIN}"' in pyproject


def test_no_known_malicious_files_installed():
    for d in site_dirs():
        for name in MALICIOUS_FILES:
            assert not (d / name).exists(), d / name


def test_no_dependency_sitecustomize():
    for d in site_dirs():
        assert not (d / "sitecustomize.py").exists(), d / "sitecustomize.py"


def test_never_imports_litellm_enterprise():
    for path in SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "litellm.enterprise" not in text, path
        assert "litellm_enterprise" not in text, path

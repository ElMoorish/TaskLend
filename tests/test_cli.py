from tasklend.cli import main
from tasklend.state import State


def run(argv, answers=()):
    lines = []
    answers = list(answers)
    code = main(argv, out=lines.append, ask=lambda _: answers.pop(0))
    return code, "\n".join(lines)


def test_init_defaults_to_us_eu_origin():
    code, out = run(["init"], ["I understand"])
    assert code == 0
    assert State.load().profile == "us-eu-origin"


def test_init_declined_saves_nothing():
    code, _ = run(["init"], ["ok"])
    assert code == 1
    assert State.load().profile is None


def test_init_second_time_does_not_ask_again():
    run(["init"], ["I understand"])
    code, out = run(["init", "--profile", "permissive"], [])
    assert code == 0
    assert "Type" not in out
    assert State.load().profile == "permissive"


def test_research_all_shows_origin_warning():
    _, out = run(["init", "--profile", "research-all"], ["I understand"])
    assert "PRC" in out


def test_profiles_lists_all():
    code, out = run(["profiles"])
    assert code == 0
    for name in ("us-eu-origin", "permissive", "research-all"):
        assert name in out


def test_doctor_reports_missing_setup(monkeypatch):
    monkeypatch.delenv("NVIDIA_NIM_API_KEY", raising=False)
    code, out = run(["doctor"])
    assert code == 1
    assert "tasklend init" in out


def _ready(monkeypatch):
    monkeypatch.setenv("NVIDIA_NIM_API_KEY", "nvapi-" + "x" * 50)
    run(["init"], ["I understand"])


def test_doctor_flags_models_missing_from_nvidia(monkeypatch):
    _ready(monkeypatch)
    monkeypatch.setattr("tasklend.cli.hosted_model_ids", lambda key: {"nvidia/other"})
    code, out = run(["doctor"])
    assert code == 1
    assert "Not on NVIDIA's hosted list" in out


def test_doctor_passes_model_check_when_all_hosted(monkeypatch):
    from tasklend.profiles import models_in

    _ready(monkeypatch)
    ids = {m.id for m in models_in("us-eu-origin")}
    monkeypatch.setattr("tasklend.cli.hosted_model_ids", lambda key: ids)
    _, out = run(["doctor"])
    assert "All us-eu-origin models are on NVIDIA's hosted list" in out


def test_doctor_offline_skips_network(monkeypatch):
    _ready(monkeypatch)

    def boom(key):
        raise AssertionError("network used")

    monkeypatch.setattr("tasklend.cli.hosted_model_ids", boom)
    run(["doctor", "--offline"])


def test_main_session_redirect_detection():
    from tasklend.cli import main_session_redirect

    assert main_session_redirect({}) is None
    assert main_session_redirect({"ANTHROPIC_BASE_URL": "https://api.anthropic.com"}) is None
    assert main_session_redirect({"ANTHROPIC_BASE_URL": "http://localhost:11434"}) == "http://localhost:11434"
    assert main_session_redirect({"ANTHROPIC_BASE_URL": "https://anthropic.com.evil.test"})


def test_launch_refuses_redirected_main_session(monkeypatch):
    _ready(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://localhost:11434")
    monkeypatch.setattr("tasklend.launch.run_launch", lambda *a, **k: 0)
    code, out = run(["launch"])
    assert code == 1
    assert "Remove-Item Env:ANTHROPIC_BASE_URL" in out


def test_launch_keep_base_url_overrides(monkeypatch):
    _ready(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://localhost:11434")
    monkeypatch.setattr("tasklend.launch.run_launch", lambda *a, **k: 0)
    code, _ = run(["launch", "--keep-base-url"])
    assert code == 0


def test_stdout_survives_non_cp1252_text():
    import io
    import sys

    from tasklend.cli import _utf8_stdio

    raw = io.BytesIO()
    old = sys.stdout
    wrapper = io.TextIOWrapper(raw, encoding="cp1252")
    sys.stdout = wrapper
    try:
        _utf8_stdio()
        print("about ≈ 3 → done")
        wrapper.flush()
        written = raw.getvalue()
    finally:
        sys.stdout = old
        wrapper.detach()
    assert "≈".encode("utf-8") in written


def test_leftover_credentials_detection():
    from tasklend.cli import leftover_credentials

    assert leftover_credentials({}) == []
    assert leftover_credentials({"ANTHROPIC_API_KEY": "sk-ant-api03-abc"}) == []
    assert leftover_credentials({"ANTHROPIC_AUTH_TOKEN": "ollama"}) == ["ANTHROPIC_AUTH_TOKEN"]
    assert leftover_credentials({"ANTHROPIC_API_KEY": "ollama"}) == ["ANTHROPIC_API_KEY"]


def test_launch_refuses_leftover_token_without_printing_it(monkeypatch):
    _ready(monkeypatch)
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "secret-ollama-token")
    monkeypatch.setattr("tasklend.launch.run_launch", lambda *a, **k: 0)
    code, out = run(["launch"])
    assert code == 1
    assert "Remove-Item Env:ANTHROPIC_AUTH_TOKEN" in out
    assert "secret-ollama-token" not in out


def test_doctor_flags_leftover_token_without_printing_it(monkeypatch):
    _ready(monkeypatch)
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "secret-ollama-token")
    monkeypatch.setattr("tasklend.cli.hosted_model_ids", lambda key: set())
    _, out = run(["doctor"])
    assert "[fail] ANTHROPIC_AUTH_TOKEN" in out
    assert "secret-ollama-token" not in out

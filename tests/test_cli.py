from agentroute.cli import main
from agentroute.state import State


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
    assert "agentroute init" in out


def _ready(monkeypatch):
    monkeypatch.setenv("NVIDIA_NIM_API_KEY", "nvapi-" + "x" * 50)
    run(["init"], ["I understand"])


def test_doctor_flags_models_missing_from_nvidia(monkeypatch):
    _ready(monkeypatch)
    monkeypatch.setattr("agentroute.cli.hosted_model_ids", lambda key: {"nvidia/other"})
    code, out = run(["doctor"])
    assert code == 1
    assert "Not on NVIDIA's hosted list" in out


def test_doctor_passes_model_check_when_all_hosted(monkeypatch):
    from agentroute.profiles import models_in

    _ready(monkeypatch)
    ids = {m.id for m in models_in("us-eu-origin")}
    monkeypatch.setattr("agentroute.cli.hosted_model_ids", lambda key: ids)
    _, out = run(["doctor"])
    assert "All us-eu-origin models are on NVIDIA's hosted list" in out


def test_doctor_offline_skips_network(monkeypatch):
    _ready(monkeypatch)

    def boom(key):
        raise AssertionError("network used")

    monkeypatch.setattr("agentroute.cli.hosted_model_ids", boom)
    run(["doctor", "--offline"])

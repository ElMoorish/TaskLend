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
    assert "Devstral 2" in out  # informational licence notice


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

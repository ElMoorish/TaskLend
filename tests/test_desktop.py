from pathlib import Path

from agentroute import skill
from agentroute.cli import main


def run(argv, answers=()):
    lines = []
    answers = list(answers)
    code = main(argv, out=lines.append, ask=lambda _: answers.pop(0))
    return code, "\n".join(lines)


def test_install_skill_writes_instructions():
    code, out = run(["install-skill"])
    assert code == 0
    path = skill.skill_dir() / "SKILL.md"
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\nname: agentroute\n")
    assert "-m agentroute work" in text
    assert "Name the files or folders" in text


def test_install_skill_is_idempotent_and_removable():
    run(["install-skill"])
    run(["install-skill"])
    code, out = run(["install-skill", "--remove"])
    assert code == 0
    assert not skill.skill_dir().exists()


def test_install_skill_never_overwrites_foreign_file():
    d = skill.skill_dir()
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text("someone else's skill", encoding="utf-8")
    try:
        skill.install_skill()
    except FileExistsError:
        pass
    else:
        raise AssertionError("overwrote a foreign skill")
    assert (d / "SKILL.md").read_text(encoding="utf-8") == "someone else's skill"


def test_work_without_session_needs_init(monkeypatch):
    for name in ("AGENTROUTE_SESSION_KEY", "AGENTROUTE_PROXY_URL"):
        monkeypatch.delenv(name, raising=False)
    code, out = run(["work", "--role", "explore", "x"])
    assert code == 1
    assert "agentroute init" in out


def test_work_without_session_starts_private_proxy(monkeypatch):
    monkeypatch.delenv("AGENTROUTE_SESSION_KEY", raising=False)
    monkeypatch.setenv("NVIDIA_NIM_API_KEY", "nvapi-" + "x" * 50)
    run(["init"], ["I understand"])

    events = []

    class FakeProxy:
        def __init__(self, profile, base_env):
            events.append(("start", profile, base_env["NVIDIA_NIM_API_KEY"][:6]))
            self.base_url = "http://127.0.0.1:9"
            self.master_key = "sk-ar-temp"

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            events.append(("stop",))

    def fake_run_worker(role, task, env, **kw):
        events.append(("work", env["AGENTROUTE_SESSION_KEY"], "NVIDIA_NIM_API_KEY" in env))
        return 0, "done", Path("out.md")

    monkeypatch.setattr("agentroute.runtime.ProxySession", FakeProxy)
    monkeypatch.setattr("agentroute.worker.run_worker", fake_run_worker)
    code, out = run(["work", "--role", "explore", "x"])
    assert code == 0
    assert events == [("start", "us-eu-origin", "nvapi-"), ("work", "sk-ar-temp", False), ("stop",)]
    assert "done" in out

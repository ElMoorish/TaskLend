from agentroute.notices import (
    FREE_TIER_KEY,
    FREE_TIER_WARNING,
    is_accepted,
    require_acceptance,
)
from agentroute.state import State


def run(state, answer, text=FREE_TIER_WARNING):
    shown = []
    ok = require_acceptance(
        state, FREE_TIER_KEY, text, input_fn=lambda _: answer, print_fn=shown.append
    )
    return ok, shown


def test_exact_phrase_accepts():
    state = State()
    ok, shown = run(state, "I understand")
    assert ok
    assert FREE_TIER_WARNING in shown
    assert is_accepted(state, FREE_TIER_KEY, FREE_TIER_WARNING)


def test_other_answers_decline():
    for answer in ["yes", "y", "i understand", "I understand.", ""]:
        state = State()
        ok, _ = run(state, answer)
        assert not ok, answer
        assert not is_accepted(state, FREE_TIER_KEY, FREE_TIER_WARNING)


def test_not_shown_again_for_same_text():
    state = State()
    run(state, "I understand")
    ok, shown = run(state, "anything")
    assert ok
    assert shown == []


def test_shown_again_when_text_changes():
    state = State()
    run(state, "I understand")
    ok, shown = run(state, "no", text=FREE_TIER_WARNING + " New sentence.")
    assert not ok
    assert shown


def test_acceptance_survives_save_and_load(isolated_config):
    state = State()
    run(state, "I understand")
    state.save()
    assert is_accepted(State.load(), FREE_TIER_KEY, FREE_TIER_WARNING)


def test_eof_declines():
    def eof(_):
        raise EOFError

    state = State()
    assert not require_acceptance(
        state, FREE_TIER_KEY, FREE_TIER_WARNING, input_fn=eof, print_fn=lambda _: None
    )

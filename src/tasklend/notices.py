"""User-facing notices and their acceptance.

The free-tier warning must be accepted by typing the exact phrase "I understand".
Acceptance is stored as a hash of the notice text, so the warning is shown again
only when its wording changes.
"""

from __future__ import annotations

import hashlib
from typing import Callable

from .state import State

ACCEPT_PHRASE = "I understand"

# Shown before the first request to NVIDIA's hosted trial API
# (integrate.api.nvidia.com with an nvapi- key) or to any OpenRouter ":free" model.
# Source: NVIDIA API Trial Terms ss. 1.2, 1.4, 2.6(a), 3.3(iv), 4.3.
FREE_TIER_KEY = "free-tier"
FREE_TIER_WARNING = (
    "Hosted free-tier endpoint active. For non-production testing and evaluation "
    "only. Prompts and outputs may be used to train models. Do not send "
    "confidential code, client IP, personal data, or HIPAA or PCI data."
)


def notice_id(text: str) -> str:
    """Stable fingerprint of a notice's exact wording."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def is_accepted(state: State, key: str, text: str) -> bool:
    return state.accepted_notices.get(key) == notice_id(text)


def require_acceptance(
    state: State,
    key: str,
    text: str,
    *,
    input_fn: Callable[[str], str] = input,
    print_fn: Callable[[str], None] = print,
) -> bool:
    """Show a notice unless this exact text was already accepted.

    Returns True when the notice is (or already was) accepted. The user must
    type the accept phrase exactly; anything else declines.
    """
    if is_accepted(state, key, text):
        return True
    print_fn("")
    print_fn(text)
    print_fn("")
    try:
        answer = input_fn(f'Type "{ACCEPT_PHRASE}" to continue: ')
    except EOFError:
        answer = ""
    if answer.strip() != ACCEPT_PHRASE:
        print_fn("Not accepted. Nothing was sent.")
        return False
    state.accepted_notices[key] = notice_id(text)
    return True

"""Model catalog and routing profiles.

Each profile maps the four worker roles (nim-explore, nim-plan, nim-code,
nim-research) to an ordered list of models: the first is the primary, the rest
are fallbacks.

Rules from the pre-release legal checklist:
- DeepSeek and Codestral are not in any profile.
- The default profile, us-eu-origin, has no models of PRC origin in any role.
- "permissive" only uses weights under Apache 2.0, MIT or OpenMDW.
- Model licence notices are informational; they are shown, not gated.
"""

from __future__ import annotations

from dataclasses import dataclass

ROLES = ("nim-explore", "nim-plan", "nim-code", "nim-research")
DEFAULT_PROFILE = "us-eu-origin"

# Model ids that must never appear in any profile.
BANNED_SUBSTRINGS = ("deepseek", "codestral")


@dataclass(frozen=True)
class Model:
    id: str  # NVIDIA NIM catalog id, used as nvidia_nim/<id> in LiteLLM
    origin: str  # country of the model's developer: "US", "FR", "CN"
    license: str
    license_url: str | None = None
    # Informational notice shown in `tasklend init` when the model is in use.
    notice: str | None = None
    # Context window in tokens, when known. Unknown windows use a safe default.
    context_tokens: int | None = None


# Every id below was on NVIDIA's hosted model list (integrate.api.nvidia.com/v1/models)
# on 2026-11-24. `tasklend doctor` re-checks against the live list.
# Licences marked "not yet checked" must be read on the model card before release.
MODELS: dict[str, Model] = {
    m.id: m
    for m in [
        Model(
            "nvidia/nemotron-3.5-super-vl-120b-a12b",
            "US",
            "OpenMDW-1.1",
            "https://openmdw.ai/license/1-1/",
            context_tokens=1_000_000,
        ),
        Model("nvidia/nemotron-3-ultra-550b-a55b", "US", "not yet checked"),
        Model("nvidia/nemotron-3.5-lightning-30b-a3b", "US", "not yet checked"),
        # research-all only
        Model("z-ai/glm-5.3-flash", "CN", "not yet checked"),
        Model("moonshotai/kimi-k3.1-pro", "CN", "not yet checked"),
        Model("minimaxai/minimax-m3.1-flash", "CN", "not yet checked"),
    ]
}

SUPER_VL = "nvidia/nemotron-3.5-super-vl-120b-a12b"  # 1M context, tool calling
ULTRA = "nvidia/nemotron-3-ultra-550b-a55b"
LIGHTNING = "nvidia/nemotron-3.5-lightning-30b-a3b"  # small and fast

PROFILES: dict[str, dict[str, list[str]]] = {
    "us-eu-origin": {
        "nim-explore": [SUPER_VL, LIGHTNING],
        "nim-plan": [SUPER_VL, ULTRA],
        "nim-code": [ULTRA, SUPER_VL],
        "nim-research": [SUPER_VL, LIGHTNING],
    },
    "permissive": {
        "nim-explore": [SUPER_VL],
        "nim-plan": [SUPER_VL],
        "nim-code": [SUPER_VL],
        "nim-research": [SUPER_VL],
    },
    "research-all": {
        "nim-explore": ["minimaxai/minimax-m3.1-flash", LIGHTNING],
        "nim-plan": ["z-ai/glm-5.3-flash", SUPER_VL],
        "nim-code": ["moonshotai/kimi-k3.1-pro", ULTRA],
        "nim-research": ["minimaxai/minimax-m3.1-flash", SUPER_VL],
    },
}

PROFILE_DESCRIPTIONS = {
    "us-eu-origin": "Default. US and EU models only; no PRC-origin models in any role.",
    "permissive": "Only weights under Apache 2.0, MIT or OpenMDW.",
    "research-all": "Every catalog model, including PRC-origin ones. For research use.",
}

PROFILE_WARNINGS = {
    "research-all": (
        "research-all includes models developed in the PRC (GLM, Kimi, "
        "MiniMax). Some organisations, including US federal contractors, may be "
        "barred from using some of them. Check your own obligations."
    ),
}


def get_profile(name: str) -> dict[str, list[str]]:
    try:
        return PROFILES[name]
    except KeyError:
        known = ", ".join(PROFILES)
        raise ValueError(f"Unknown profile {name!r}. Known profiles: {known}") from None


def models_in(profile: str) -> list[Model]:
    seen: dict[str, Model] = {}
    for ids in get_profile(profile).values():
        for model_id in ids:
            seen.setdefault(model_id, MODELS[model_id])
    return list(seen.values())


DEFAULT_CONTEXT_TOKENS = 128_000


def role_context_tokens(profile: str, role: str) -> int:
    """Smallest window among a role's models, so a fallback never overflows."""
    windows = [MODELS[m].context_tokens or DEFAULT_CONTEXT_TOKENS for m in get_profile(profile)[role]]
    return min(windows)


def notices_for(profile: str) -> list[str]:
    return [m.notice for m in models_in(profile) if m.notice]

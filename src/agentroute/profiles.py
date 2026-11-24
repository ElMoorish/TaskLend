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
    # False until the hosted API id has been checked on build.nvidia.com.
    id_verified: bool = True
    # Informational notice shown in `agentroute init` when the model is in use.
    notice: str | None = None


DEVSTRAL_2_NOTICE = (
    "Devstral 2 (Mistral Modified MIT licence): you have no rights under this "
    "licence if your company's, or your employer's, global revenue topped $20M "
    "in the previous month. Internal use is not exempt. Above that, get a "
    "commercial licence from Mistral or use Mistral's hosted API."
)
KIMI_NOTICE = (
    "Kimi (Moonshot Modified MIT licence): a product above 100M monthly active "
    "users or $20M monthly revenue must show Kimi attribution in its UI."
)

MODELS: dict[str, Model] = {
    m.id: m
    for m in [
        Model(
            "nvidia/nemotron-3.5-super-vl-120b-a12b",
            "US",
            "OpenMDW-1.1",
            "https://openmdw.ai/license/1-1/",
            id_verified=False,
        ),
        Model(
            "nvidia/nemotron-3-super-120b-a12b",
            "US",
            "NVIDIA open model licence (not yet checked)",
        ),
        Model(
            "mistralai/devstral-2-123b-instruct-2512",
            "FR",
            "Mistral Modified MIT",
            "https://huggingface.co/mistralai/Devstral-2-123B-Instruct-2512/raw/main/LICENSE",
            notice=DEVSTRAL_2_NOTICE,
        ),
        Model(
            "mistralai/devstral-small-2505",
            "FR",
            "Apache-2.0",
            id_verified=False,
        ),
        # research-all only
        Model("z-ai/glm-5.1", "CN", "not yet checked"),
        Model("moonshotai/kimi-k2.5", "CN", "Moonshot Modified MIT", notice=KIMI_NOTICE),
        Model("qwen/qwen3.5-122b-a10b", "CN", "not yet checked"),
        Model("minimaxai/minimax-m2.5", "CN", "not yet checked"),
    ]
}

NEMOTRON_35 = "nvidia/nemotron-3.5-super-vl-120b-a12b"
NEMOTRON_3 = "nvidia/nemotron-3-super-120b-a12b"
DEVSTRAL_2 = "mistralai/devstral-2-123b-instruct-2512"
DEVSTRAL_SMALL = "mistralai/devstral-small-2505"

PROFILES: dict[str, dict[str, list[str]]] = {
    "us-eu-origin": {
        "nim-explore": [NEMOTRON_35, NEMOTRON_3],
        "nim-plan": [NEMOTRON_35, NEMOTRON_3],
        "nim-code": [DEVSTRAL_2, DEVSTRAL_SMALL],
        "nim-research": [NEMOTRON_3, NEMOTRON_35],
    },
    "permissive": {
        "nim-explore": [NEMOTRON_35],
        "nim-plan": [NEMOTRON_35],
        "nim-code": [DEVSTRAL_SMALL, NEMOTRON_35],
        "nim-research": [NEMOTRON_35],
    },
    "research-all": {
        "nim-explore": [NEMOTRON_3, "moonshotai/kimi-k2.5"],
        "nim-plan": ["z-ai/glm-5.1", NEMOTRON_35],
        "nim-code": ["qwen/qwen3.5-122b-a10b", DEVSTRAL_2],
        "nim-research": ["minimaxai/minimax-m2.5", NEMOTRON_3],
    },
}

PROFILE_DESCRIPTIONS = {
    "us-eu-origin": "Default. US and EU models only; no PRC-origin models in any role.",
    "permissive": "Only weights under Apache 2.0, MIT or OpenMDW.",
    "research-all": "Every catalog model, including PRC-origin ones. For research use.",
}

PROFILE_WARNINGS = {
    "research-all": (
        "research-all includes models developed in the PRC (GLM, Kimi, Qwen, "
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


def notices_for(profile: str) -> list[str]:
    return [m.notice for m in models_in(profile) if m.notice]

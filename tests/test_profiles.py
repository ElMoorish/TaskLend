import pytest

from agentroute.profiles import (
    BANNED_SUBSTRINGS,
    DEFAULT_PROFILE,
    MODELS,
    PROFILES,
    ROLES,
    get_profile,
    models_in,
)


def test_default_is_us_eu_origin():
    assert DEFAULT_PROFILE == "us-eu-origin"


@pytest.mark.parametrize("profile", list(PROFILES))
def test_every_profile_covers_every_role(profile):
    routes = get_profile(profile)
    assert set(routes) == set(ROLES)
    for ids in routes.values():
        assert ids, "each role needs at least a primary model"
        for model_id in ids:
            assert model_id in MODELS


def test_no_banned_models_anywhere():
    for model_id in MODELS:
        for banned in BANNED_SUBSTRINGS:
            assert banned not in model_id.lower()


def test_default_profile_has_no_prc_origin_models():
    for model in models_in("us-eu-origin"):
        assert model.origin != "CN", model.id


def test_plan_primary_is_nemotron_35_in_default():
    assert get_profile("us-eu-origin")["nim-plan"][0].startswith("nvidia/nemotron-3.5")


def test_permissive_only_permissive_licences():
    allowed = {"Apache-2.0", "MIT", "OpenMDW-1.1"}
    for model in models_in("permissive"):
        assert model.license in allowed, model.id


def test_unknown_profile_rejected():
    with pytest.raises(ValueError):
        get_profile("nope")

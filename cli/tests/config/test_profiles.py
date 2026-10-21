import pytest
from i2g_admin import config
from i2g_admin.config import profiles
from i2g_admin.core.errors import CliError


def test_resolve_profile_precedence():
    # Explicit arg wins.
    assert config.resolve_profile("staging") == "staging"
    # Falls back to default when nothing stored.
    assert config.resolve_profile(None) == config.DEFAULT_PROFILE


def test_resolve_profile_uses_stored_default():
    profiles._save_config({"default_profile": "prod"})
    assert config.resolve_profile(None) == "prod"


def test_list_profiles_includes_default_and_stored():
    profiles._save_config({"profiles": {"prod": {"base_url": "https://prod"}, "stg": {}}})
    assert config.list_profiles() == ["default", "prod", "stg"]


def test_default_profile_helper():
    assert config.default_profile() == "default"
    profiles._save_config({"default_profile": "x"})
    assert config.default_profile() == "x"


# --- hardening: profile-name validation & corrupt config -------------------
@pytest.mark.parametrize("bad", ["../escape", "a/b", "with space", "tab\t"])
def test_resolve_profile_rejects_unsafe_names(bad):
    with pytest.raises(CliError):
        config.resolve_profile(bad)


def test_resolve_profile_empty_falls_back_to_default():
    # An empty/falsy --profile is not an error; it means "use the default profile".
    assert config.resolve_profile("") == config.DEFAULT_PROFILE


def test_current_base_url_tolerates_non_dict_profile_entry(monkeypatch):
    monkeypatch.setenv("I2G_ADMIN_BASE_URL", "https://env-default")
    # A hand-edited/corrupt config.json where a profile maps to a string.
    profiles._save_config({"profiles": {"staging": "https://oops"}})
    assert config.current_base_url("staging") == "https://env-default"


def test_set_base_url_repairs_non_dict_profile_entry():
    profiles._save_config({"profiles": {"staging": "https://oops"}})
    config.set_base_url("https://fixed.example.com", profile="staging")
    assert config.current_base_url("staging") == "https://fixed.example.com"


def test_set_base_url_repairs_non_dict_profiles_map():
    profiles._save_config({"profiles": "not-a-dict"})
    config.set_base_url("https://fixed.example.com", profile="staging")
    assert config.current_base_url("staging") == "https://fixed.example.com"


def test_list_profiles_tolerates_non_dict_profiles():
    profiles._save_config({"profiles": "not-a-dict"})
    assert config.list_profiles() == ["default"]


def test_configured_base_url_tolerates_non_dict_entry():
    profiles._save_config({"profiles": {"staging": "https://oops"}})
    assert config.configured_base_url("staging") is None

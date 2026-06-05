import os
import stat

import pytest
from i2g_admin import config
from i2g_admin.errors import CliError


def _mode(path):
    return stat.S_IMODE(os.stat(path).st_mode)


def test_save_credentials_sets_owner_only_permissions():
    config.save_credentials({"base_url": "http://x", "access_token": "t"})
    path = config.credentials_path()
    assert path.exists()
    assert _mode(path) == 0o600
    assert _mode(config.config_dir()) == 0o700


def test_load_roundtrip():
    config.save_credentials({"a": 1})
    assert config.load_credentials() == {"a": 1}


def test_load_missing_returns_none():
    assert config.load_credentials() is None


def test_load_bad_json_returns_none():
    path = config.credentials_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json")
    assert config.load_credentials() is None


def test_clear_credentials():
    config.save_credentials({"a": 1})
    assert config.clear_credentials() is True
    assert config.clear_credentials() is False


def test_default_base_url_from_env(monkeypatch):
    monkeypatch.setenv("I2G_ADMIN_BASE_URL", "https://env-host")
    assert config.default_base_url() == "https://env-host"


def test_default_base_url_missing_raises(monkeypatch):
    # No baked-in default: a missing base URL is a clear configuration error.
    monkeypatch.delenv("I2G_ADMIN_BASE_URL", raising=False)
    monkeypatch.setattr(config, "load_dotenv", lambda: None)  # ignore any stray .env
    with pytest.raises(CliError):
        config.default_base_url()


def test_current_base_url_and_set(monkeypatch):
    monkeypatch.setenv("I2G_ADMIN_BASE_URL", "https://env-default")
    assert config.current_base_url() == "https://env-default"
    config.set_base_url("https://configured.example.com")
    assert config.current_base_url() == "https://configured.example.com"


def test_validate_base_url_accepts_https_and_loopback_http():
    assert config.validate_base_url("https://api.example.com") == "https://api.example.com"
    assert config.validate_base_url("http://127.0.0.1:8000") == "http://127.0.0.1:8000"
    assert config.validate_base_url("http://localhost:8000") == "http://localhost:8000"


def test_validate_base_url_rejects_remote_http_and_other_schemes():
    for bad in ("http://remote.example.com", "ftp://host", "", "https://"):
        with pytest.raises(CliError):
            config.validate_base_url(bad)


def test_set_base_url_rejects_invalid():
    with pytest.raises(CliError):
        config.set_base_url("http://remote.example.com")


# --- named profiles --------------------------------------------------------
def test_resolve_profile_precedence():
    # Explicit arg wins.
    assert config.resolve_profile("staging") == "staging"
    # Falls back to default when nothing stored.
    assert config.resolve_profile(None) == config.DEFAULT_PROFILE


def test_resolve_profile_uses_stored_default():
    config._save_config({"default_profile": "prod"})
    assert config.resolve_profile(None) == "prod"


def test_list_profiles_includes_default_and_stored():
    config._save_config({"profiles": {"prod": {"base_url": "https://prod"}, "stg": {}}})
    assert config.list_profiles() == ["default", "prod", "stg"]


def test_default_profile_helper():
    assert config.default_profile() == "default"
    config._save_config({"default_profile": "x"})
    assert config.default_profile() == "x"


def test_credentials_path_default_vs_named():
    assert config.credentials_path("default").name == "credentials.json"
    assert config.credentials_path("staging").name == "credentials-staging.json"


def test_credentials_roundtrip_per_profile():
    config.save_credentials({"access_token": "A"}, profile="staging")
    config.save_credentials({"access_token": "B"}, profile="default")
    assert config.load_credentials("staging") == {"access_token": "A"}
    assert config.load_credentials("default") == {"access_token": "B"}
    assert config.clear_credentials("staging") is True
    assert config.load_credentials("staging") is None


def test_configured_base_url_returns_none_when_absent():
    assert config.configured_base_url("staging") is None
    config.set_base_url("https://stg.example.com", profile="staging")
    assert config.configured_base_url("staging") == "https://stg.example.com"


def test_current_base_url_falls_back_to_legacy_credentials(monkeypatch):
    monkeypatch.delenv("I2G_ADMIN_BASE_URL", raising=False)
    monkeypatch.setattr(config, "load_dotenv", lambda: None)
    # No config.json base_url, but a legacy credentials.json carries one.
    config.save_credentials({"base_url": "https://legacy.example.com", "access_token": "T"})
    assert config.current_base_url() == "https://legacy.example.com"


def test_set_base_url_for_named_profile_isolated():
    config.set_base_url("https://stg", profile="staging")
    config.set_base_url("https://prod", profile="prod")
    assert config.current_base_url("staging") == "https://stg"
    assert config.current_base_url("prod") == "https://prod"


def test_load_config_handles_corrupt_file():
    path = config._config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json")
    assert config._load_config() == {}


def test_load_dotenv_populates_env(tmp_path, monkeypatch):
    monkeypatch.delenv("I2G_ADMIN_BASE_URL", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text('# comment\nI2G_ADMIN_BASE_URL="https://from-dotenv"\nBLANK\n')
    monkeypatch.setattr(config, "_dotenv_paths", lambda: [env_file])
    config.load_dotenv()
    assert os.environ["I2G_ADMIN_BASE_URL"] == "https://from-dotenv"


# --- hardening: profile-name validation & corrupt config -------------------
@pytest.mark.parametrize("bad", ["../escape", "a/b", "with space", "tab\t"])
def test_resolve_profile_rejects_unsafe_names(bad):
    with pytest.raises(CliError):
        config.resolve_profile(bad)


def test_resolve_profile_empty_falls_back_to_default():
    # An empty/falsy --profile is not an error; it means "use the default profile".
    assert config.resolve_profile("") == config.DEFAULT_PROFILE


def test_credentials_path_rejects_unsafe_profile():
    with pytest.raises(CliError):
        config.credentials_path("../../etc/passwd")


def test_current_base_url_tolerates_non_dict_profile_entry(monkeypatch):
    monkeypatch.setenv("I2G_ADMIN_BASE_URL", "https://env-default")
    # A hand-edited/corrupt config.json where a profile maps to a string.
    config._save_config({"profiles": {"staging": "https://oops"}})
    assert config.current_base_url("staging") == "https://env-default"


def test_set_base_url_repairs_non_dict_profile_entry():
    config._save_config({"profiles": {"staging": "https://oops"}})
    config.set_base_url("https://fixed.example.com", profile="staging")
    assert config.current_base_url("staging") == "https://fixed.example.com"


def test_set_base_url_repairs_non_dict_profiles_map():
    config._save_config({"profiles": "not-a-dict"})
    config.set_base_url("https://fixed.example.com", profile="staging")
    assert config.current_base_url("staging") == "https://fixed.example.com"


def test_list_profiles_tolerates_non_dict_profiles():
    config._save_config({"profiles": "not-a-dict"})
    assert config.list_profiles() == ["default"]


def test_configured_base_url_tolerates_non_dict_entry():
    config._save_config({"profiles": {"staging": "https://oops"}})
    assert config.configured_base_url("staging") is None

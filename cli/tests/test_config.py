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


def test_load_config_handles_non_dict_top_level():
    # A valid JSON document whose top level is not an object degrades to {}.
    config._config_path().parent.mkdir(parents=True, exist_ok=True)
    config._config_path().write_text("[1, 2, 3]")
    assert config._load_config() == {}


# --- #15: never clobber a corrupt config.json on the write path -------------
def test_load_config_strict_missing_returns_empty():
    # No file yet: strict load is happy to start fresh.
    assert config._load_config_strict() == {}


def test_load_config_strict_non_dict_top_level_returns_empty():
    config._config_path().parent.mkdir(parents=True, exist_ok=True)
    config._config_path().write_text("[1, 2, 3]")
    assert config._load_config_strict() == {}


def test_load_config_strict_raises_on_corrupt():
    path = config._config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json")
    with pytest.raises(CliError):
        config._load_config_strict()


def test_set_base_url_refuses_to_clobber_corrupt_config():
    path = config._config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    original = '{"profiles": {"prod": {"base_url": "https://prod"}}'  # truncated -> corrupt
    path.write_text(original)
    with pytest.raises(CliError):
        config.set_base_url("https://new.example.com", profile="staging")
    # The corrupt file must be left exactly as it was (no silent overwrite).
    assert path.read_text() == original


def test_set_base_url_creates_config_when_absent():
    # No config.json on disk: a normal create still works.
    assert not config._config_path().exists()
    config.set_base_url("https://fresh.example.com", profile="staging")
    assert config.configured_base_url("staging") == "https://fresh.example.com"


def test_set_base_url_preserves_other_profiles():
    config._save_config(
        {
            "default_profile": "prod",
            "profiles": {
                "prod": {"base_url": "https://prod"},
                "stg": {"base_url": "https://stg"},
            },
        }
    )
    config.set_base_url("https://new-dev.example.com", profile="dev")
    # The freshly set profile is stored...
    assert config.configured_base_url("dev") == "https://new-dev.example.com"
    # ...and the pre-existing profiles + default survive (regression guard).
    assert config.configured_base_url("prod") == "https://prod"
    assert config.configured_base_url("stg") == "https://stg"
    assert config.default_profile() == "prod"


# --- #13: current_base_url reads config.json exactly once -------------------
def test_current_base_url_reads_config_once(monkeypatch):
    monkeypatch.setenv("I2G_ADMIN_BASE_URL", "https://env-default")
    config.set_base_url("https://stg.example.com", profile="staging")

    config_path = config._config_path()
    calls = {"config": 0}
    real_read_json = config._read_json

    def counting_read_json(path):
        if path == config_path:
            calls["config"] += 1
        return real_read_json(path)

    monkeypatch.setattr(config, "_read_json", counting_read_json)
    assert config.current_base_url("staging") == "https://stg.example.com"
    # Exactly one config.json read on the hit path (credentials.json reads
    # go to a different file and are not counted here).
    assert calls["config"] == 1


def test_current_base_url_reads_config_once_on_default_profile(monkeypatch):
    # Default-profile path: resolve_profile must reuse the cfg passed in rather
    # than re-reading config.json to discover the default profile.
    monkeypatch.setenv("I2G_ADMIN_BASE_URL", "https://env-default")
    config._save_config({"default_profile": "staging", "profiles": {"staging": {"base_url": "https://stg"}}})

    config_path = config._config_path()
    calls = {"config": 0}
    real_read_json = config._read_json

    def counting_read_json(path):
        if path == config_path:
            calls["config"] += 1
        return real_read_json(path)

    monkeypatch.setattr(config, "_read_json", counting_read_json)
    assert config.current_base_url() == "https://stg"
    assert calls["config"] == 1


def test_resolve_profile_reuses_passed_cfg(monkeypatch):
    # When cfg is supplied and no explicit profile is given, config.json is not read.
    def boom(path):
        raise AssertionError(f"unexpected config read: {path}")

    monkeypatch.setattr(config, "_read_json", boom)
    assert config.resolve_profile(None, cfg={"default_profile": "prod"}) == "prod"
    # An explicit profile also avoids any read.
    assert config.resolve_profile("staging", cfg=None) == "staging"


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

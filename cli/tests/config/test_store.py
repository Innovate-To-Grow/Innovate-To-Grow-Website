import pytest
from i2g_admin import config
from i2g_admin.config import profiles, store
from i2g_admin.core.errors import CliError


def test_load_config_handles_corrupt_file():
    path = profiles._config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json")
    assert profiles._load_config() == {}


def test_load_config_handles_non_dict_top_level():
    # A valid JSON document whose top level is not an object degrades to {}.
    profiles._config_path().parent.mkdir(parents=True, exist_ok=True)
    profiles._config_path().write_text("[1, 2, 3]")
    assert profiles._load_config() == {}


# --- #15: never clobber a corrupt config.json on the write path -------------
def test_load_config_strict_missing_returns_empty():
    # No file yet: strict load is happy to start fresh.
    assert profiles._load_config_strict() == {}


def test_load_config_strict_non_dict_top_level_returns_empty():
    profiles._config_path().parent.mkdir(parents=True, exist_ok=True)
    profiles._config_path().write_text("[1, 2, 3]")
    assert profiles._load_config_strict() == {}


def test_load_config_strict_raises_on_corrupt():
    path = profiles._config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json")
    with pytest.raises(CliError):
        profiles._load_config_strict()


def test_set_base_url_refuses_to_clobber_corrupt_config():
    path = profiles._config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    original = '{"profiles": {"prod": {"base_url": "https://prod"}}'  # truncated -> corrupt
    path.write_text(original)
    with pytest.raises(CliError):
        config.set_base_url("https://new.example.com", profile="staging")
    # The corrupt file must be left exactly as it was (no silent overwrite).
    assert path.read_text() == original


def test_set_base_url_creates_config_when_absent():
    # No config.json on disk: a normal create still works.
    assert not profiles._config_path().exists()
    config.set_base_url("https://fresh.example.com", profile="staging")
    assert config.configured_base_url("staging") == "https://fresh.example.com"


def test_set_base_url_preserves_other_profiles():
    profiles._save_config(
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

    config_path = profiles._config_path()
    calls = {"config": 0}
    real_read_json = store._read_json

    def counting_read_json(path):
        if path == config_path:
            calls["config"] += 1
        return real_read_json(path)

    monkeypatch.setattr(store, "_read_json", counting_read_json)
    assert config.current_base_url("staging") == "https://stg.example.com"
    # Exactly one config.json read on the hit path (credentials.json reads
    # go to a different file and are not counted here).
    assert calls["config"] == 1


def test_current_base_url_reads_config_once_on_default_profile(monkeypatch):
    # Default-profile path: resolve_profile must reuse the cfg passed in rather
    # than re-reading config.json to discover the default profile.
    monkeypatch.setenv("I2G_ADMIN_BASE_URL", "https://env-default")
    profiles._save_config({"default_profile": "staging", "profiles": {"staging": {"base_url": "https://stg"}}})

    config_path = profiles._config_path()
    calls = {"config": 0}
    real_read_json = store._read_json

    def counting_read_json(path):
        if path == config_path:
            calls["config"] += 1
        return real_read_json(path)

    monkeypatch.setattr(store, "_read_json", counting_read_json)
    assert config.current_base_url() == "https://stg"
    assert calls["config"] == 1


def test_resolve_profile_reuses_passed_cfg(monkeypatch):
    # When cfg is supplied and no explicit profile is given, config.json is not read.
    def boom(path):
        raise AssertionError(f"unexpected config read: {path}")

    monkeypatch.setattr(store, "_read_json", boom)
    assert config.resolve_profile(None, cfg={"default_profile": "prod"}) == "prod"
    # An explicit profile also avoids any read.
    assert config.resolve_profile("staging", cfg=None) == "staging"

import os
import stat

import pytest
from i2g_admin import config
from i2g_admin.core.errors import CliError


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


def test_credentials_path_rejects_unsafe_profile():
    with pytest.raises(CliError):
        config.credentials_path("../../etc/passwd")

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
    monkeypatch.setenv("I2G_ADMIN_BASE_URL", "http://env-host")
    assert config.default_base_url() == "http://env-host"


def test_default_base_url_fallback():
    assert config.default_base_url() == config.DEFAULT_BASE_URL


def test_current_base_url_and_set():
    assert config.current_base_url() == config.DEFAULT_BASE_URL
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

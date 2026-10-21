import pytest
from i2g_admin import config
from i2g_admin.config import dotenv
from i2g_admin.core.errors import CliError


def test_default_base_url_from_env(monkeypatch):
    monkeypatch.setenv("I2G_ADMIN_BASE_URL", "https://env-host")
    assert config.default_base_url() == "https://env-host"


def test_default_base_url_missing_raises(monkeypatch):
    # No baked-in default: a missing base URL is a clear configuration error.
    monkeypatch.delenv("I2G_ADMIN_BASE_URL", raising=False)
    monkeypatch.setattr(dotenv, "load_dotenv", lambda: None)  # ignore any stray .env
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


def test_configured_base_url_returns_none_when_absent():
    assert config.configured_base_url("staging") is None
    config.set_base_url("https://stg.example.com", profile="staging")
    assert config.configured_base_url("staging") == "https://stg.example.com"


def test_current_base_url_falls_back_to_legacy_credentials(monkeypatch):
    monkeypatch.delenv("I2G_ADMIN_BASE_URL", raising=False)
    monkeypatch.setattr(dotenv, "load_dotenv", lambda: None)
    # No config.json base_url, but a legacy credentials.json carries one.
    config.save_credentials({"base_url": "https://legacy.example.com", "access_token": "T"})
    assert config.current_base_url() == "https://legacy.example.com"


def test_set_base_url_for_named_profile_isolated():
    config.set_base_url("https://stg", profile="staging")
    config.set_base_url("https://prod", profile="prod")
    assert config.current_base_url("staging") == "https://stg"
    assert config.current_base_url("prod") == "https://prod"

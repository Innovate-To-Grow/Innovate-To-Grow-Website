import time
from urllib.parse import parse_qs, urlparse

import pytest
import responses
from i2g_admin import auth, config
from i2g_admin.errors import AuthError, CliError


class FakeServer:
    redirect_uri = "http://127.0.0.1:55555/callback"

    def __init__(self, captured, query_factory):
        self._captured = captured
        self._query_factory = query_factory
        self.closed = False

    def wait_for_callback(self, timeout):
        return self._query_factory(self._captured)

    def close(self):
        self.closed = True


def _state_from(captured):
    return parse_qs(urlparse(captured["url"]).query)["state"][0]


def _factory(captured, query_factory):
    return lambda: FakeServer(captured, query_factory)


@responses.activate
def test_login_happy_path_caches_token():
    responses.add(
        responses.POST,
        "https://b/admin-api/oauth/token/",
        json={"access_token": "TOK", "token_type": "Bearer", "expires_in": 28800},
        status=200,
    )
    captured = {}
    token = auth.login(
        "https://b",
        open_browser=lambda url: captured.__setitem__("url", url),
        server_factory=_factory(captured, lambda c: {"code": "CODE", "state": _state_from(c)}),
    )
    assert token["access_token"] == "TOK"
    assert "code_challenge" in captured["url"]
    creds = config.load_credentials()
    assert creds["access_token"] == "TOK"
    assert creds["base_url"] == "https://b"
    assert creds["expires_at"] > time.time()


def test_login_missing_code_raises():
    captured = {}
    with pytest.raises(AuthError):
        auth.login(
            "https://b",
            open_browser=lambda url: captured.__setitem__("url", url),
            server_factory=_factory(captured, lambda c: {}),
        )


def test_login_state_mismatch_raises():
    captured = {}
    with pytest.raises(AuthError):
        auth.login(
            "https://b",
            open_browser=lambda url: captured.__setitem__("url", url),
            server_factory=_factory(captured, lambda c: {"code": "CODE", "state": "WRONG"}),
        )


@responses.activate
def test_login_exchange_failure_raises():
    responses.add(responses.POST, "https://b/admin-api/oauth/token/", status=400, json={})
    captured = {}
    with pytest.raises(AuthError):
        auth.login(
            "https://b",
            open_browser=lambda url: captured.__setitem__("url", url),
            server_factory=_factory(captured, lambda c: {"code": "CODE", "state": _state_from(c)}),
        )


def test_login_rejects_non_https_base_url():
    with pytest.raises(CliError) as exc:
        auth.login(
            "http://remote.example.com", open_browser=lambda url: None, server_factory=_factory({}, lambda c: {})
        )
    assert "https" in str(exc.value).lower()


def test_is_expired_branches():
    assert auth._is_expired({}) is True
    assert auth._is_expired({"expires_at": time.time() + 10000}) is False
    assert auth._is_expired({"expires_at": time.time() - 10}) is True


def test_ensure_token_uses_cached_valid_token():
    config.save_credentials({"base_url": "https://b", "access_token": "TOK", "expires_at": time.time() + 10000})
    assert auth.ensure_token() == ("https://b", "TOK")


def test_ensure_token_logs_in_when_missing(monkeypatch):
    def fake_login(base_url):
        config.save_credentials({"base_url": base_url, "access_token": "NEW", "expires_at": time.time() + 10000})

    monkeypatch.setattr(auth, "login", fake_login)
    base_url, token = auth.ensure_token()
    assert token == "NEW"


def test_ensure_token_relogins_when_expired(monkeypatch):
    config.save_credentials({"base_url": "https://b", "access_token": "OLD", "expires_at": time.time() - 10})
    calls = []

    def fake_login(base_url):
        calls.append(base_url)
        config.save_credentials({"base_url": base_url, "access_token": "FRESH", "expires_at": time.time() + 10000})

    monkeypatch.setattr(auth, "login", fake_login)
    base_url, token = auth.ensure_token()
    assert token == "FRESH"
    assert calls == ["https://b"]


def test_ensure_token_raises_if_login_produces_no_token(monkeypatch):
    monkeypatch.setattr(auth, "login", lambda base_url: None)
    with pytest.raises(AuthError):
        auth.ensure_token()

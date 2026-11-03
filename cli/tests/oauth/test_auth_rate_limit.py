"""The OAuth token exchange under 429: the unused code is resent after a short Retry-After, never after a long one."""

import pytest
import responses
from i2g_admin import auth
from i2g_admin.client import rate_limit
from i2g_admin.core.errors import AuthError

TOKEN_URL = "https://b/admin-api/oauth/token/"


@pytest.fixture
def sleeps(monkeypatch):
    delays = []
    monkeypatch.setattr(rate_limit.time, "sleep", delays.append)
    monkeypatch.setattr(rate_limit.random, "random", lambda: 0.0)
    return delays


def _exchange():
    return auth._exchange("https://b", "CODE", "verifier", "http://127.0.0.1/callback")


@responses.activate
def test_refused_exchange_is_resent_after_retry_after(sleeps):
    responses.add(responses.POST, TOKEN_URL, status=429, headers={"Retry-After": "3"}, json={})
    responses.add(responses.POST, TOKEN_URL, status=200, json={"access_token": "TOK", "expires_in": 60})
    assert _exchange()["access_token"] == "TOK"
    assert sleeps == [3.0]
    assert [call.request.body for call in responses.calls][0] == responses.calls[1].request.body


@responses.activate
def test_wait_longer_than_the_code_can_live_fails_with_a_hint(sleeps):
    responses.add(responses.POST, TOKEN_URL, status=429, headers={"Retry-After": "45"}, json={})
    with pytest.raises(AuthError) as excinfo:
        _exchange()
    assert str(excinfo.value) == (
        "Token exchange was rate limited (429). Try again in 45 seconds. Run `i2g-admin login` again."
    )
    assert sleeps == []
    assert len(responses.calls) == 1


@responses.activate
def test_resends_are_bounded(sleeps):
    for _ in range(rate_limit.RATE_LIMIT_RETRIES + 1):
        responses.add(responses.POST, TOKEN_URL, status=429, json={"retry_after": 1})
    with pytest.raises(AuthError, match=r"rate limited \(429\)\. Try again in 1 second\."):
        _exchange()
    assert len(responses.calls) == rate_limit.RATE_LIMIT_RETRIES + 1
    assert sleeps == [1.0] * rate_limit.RATE_LIMIT_RETRIES


@responses.activate
def test_other_failures_keep_their_message(sleeps):
    responses.add(responses.POST, TOKEN_URL, status=400, json={})
    with pytest.raises(AuthError, match=r"^Token exchange failed \(400\)\.$"):
        _exchange()
    assert sleeps == []

"""429 Too Many Requests: reads wait out Retry-After and are resent (bounded) whatever --max-attempts says."""

import pytest
import requests
import responses
from i2g_admin import client as client_module
from i2g_admin.client import ApiClient, rate_limit
from i2g_admin.core.errors import ApiError

BASE = "https://testserver"


@pytest.fixture(autouse=True)
def no_jitter(monkeypatch):
    monkeypatch.setattr(rate_limit.random, "random", lambda: 0.0)


def _refuse(method=responses.GET, retry_after="2", body=None):
    headers = {"Retry-After": retry_after} if retry_after is not None else {}
    responses.add(method, f"{BASE}/x/", status=429, headers=headers, json=body if body is not None else {})


@responses.activate
def test_read_refused_once_is_resent_after_retry_after_with_default_single_attempt(captured_sleeps):
    _refuse(retry_after="2")
    responses.add(responses.GET, f"{BASE}/x/", status=200, json={"ok": True})
    client = ApiClient(BASE, "tok")  # default max_attempts == 1
    assert client.get("/x/") == {"ok": True}
    assert captured_sleeps == [2.0]
    assert len(responses.calls) == 2


@responses.activate
def test_jitter_is_added_to_the_wait(captured_sleeps, monkeypatch):
    monkeypatch.setattr(rate_limit.random, "random", lambda: 1.0)
    _refuse(retry_after="2")
    responses.add(responses.GET, f"{BASE}/x/", status=200, json={})
    ApiClient(BASE, "tok").get("/x/")
    assert captured_sleeps == [2.0 + rate_limit.RATE_LIMIT_JITTER]


@responses.activate
def test_wait_read_from_body_when_header_missing(captured_sleeps):
    _refuse(retry_after=None, body={"detail": "slow down", "retry_after": 4})
    responses.add(responses.GET, f"{BASE}/x/", status=200, json={})
    ApiClient(BASE, "tok").get("/x/")
    assert captured_sleeps == [4.0]


@responses.activate
def test_doubling_fallback_when_no_wait_is_named(captured_sleeps):
    for _ in range(3):
        _refuse(retry_after=None)
    responses.add(responses.GET, f"{BASE}/x/", status=200, json={})
    ApiClient(BASE, "tok").get("/x/")
    assert captured_sleeps == [1.0, 2.0, 4.0]


@responses.activate
def test_retries_are_bounded_and_the_last_429_surfaces_with_the_server_detail(captured_sleeps):
    for _ in range(rate_limit.RATE_LIMIT_RETRIES + 1):
        _refuse(retry_after="1", body={"detail": "Too many requests. Please try again in 1 second."})
    with pytest.raises(ApiError) as excinfo:
        ApiClient(BASE, "tok").get("/x/")
    assert excinfo.value.status_code == 429
    assert "try again in 1 second" in str(excinfo.value)
    assert len(responses.calls) == rate_limit.RATE_LIMIT_RETRIES + 1
    assert captured_sleeps == [1.0] * rate_limit.RATE_LIMIT_RETRIES


@responses.activate
def test_a_wait_longer_than_the_maximum_fails_at_once(captured_sleeps):
    _refuse(retry_after="3600", body={})
    with pytest.raises(ApiError) as excinfo:
        ApiClient(BASE, "tok").get("/x/")
    assert str(excinfo.value) == "Too many requests (429). Try again in 3600 seconds."
    assert captured_sleeps == []
    assert len(responses.calls) == 1


@responses.activate
def test_detail_without_a_wait_or_json(captured_sleeps):
    responses.add(responses.GET, f"{BASE}/x/", status=429, body="busy", headers={"Retry-After": "999"})
    with pytest.raises(ApiError) as excinfo:
        ApiClient(BASE, "tok").get("/x/")
    assert str(excinfo.value) == "Too many requests (429). Try again in 999 seconds."

    responses.replace(responses.GET, f"{BASE}/x/", status=429, body="busy")
    with pytest.raises(ApiError) as excinfo:
        ApiClient(BASE, "tok", rate_limit_retries=0).get("/x/")
    assert str(excinfo.value) == "Too many requests (429)."


@responses.activate
def test_rate_limit_retries_can_be_turned_off(captured_sleeps):
    _refuse()
    client = ApiClient(BASE, "tok", rate_limit_retries=0)
    with pytest.raises(ApiError):
        client.get("/x/")
    assert captured_sleeps == []
    assert ApiClient(BASE, "tok", rate_limit_retries=-2).rate_limit_retries == 0


@responses.activate
@pytest.mark.parametrize("method", ["POST", "PATCH", "DELETE"])
def test_writes_are_never_resent(captured_sleeps, method):
    _refuse(method=method)
    client = ApiClient(BASE, "tok", max_attempts=3)
    with pytest.raises(ApiError) as excinfo:
        client.request(method, "/x/", json_body={})
    assert excinfo.value.status_code == 429
    assert captured_sleeps == []
    assert len(responses.calls) == 1


@responses.activate
def test_429_resends_do_not_use_up_transient_attempts(captured_sleeps, monkeypatch):
    monkeypatch.setattr(client_module.random, "random", lambda: 0.0)
    _refuse(retry_after="1")
    responses.add(responses.GET, f"{BASE}/x/", status=503, json={})
    responses.add(responses.GET, f"{BASE}/x/", status=200, json={"ok": True})
    assert ApiClient(BASE, "tok", max_attempts=2).get("/x/") == {"ok": True}
    assert len(responses.calls) == 3


@responses.activate
def test_connection_error_during_a_resend_follows_the_transient_rules(captured_sleeps):
    _refuse(retry_after="1")
    responses.add(responses.GET, f"{BASE}/x/", body=requests.ConnectionError("boom"))
    with pytest.raises(requests.ConnectionError):
        ApiClient(BASE, "tok").get("/x/")


def test_requested_wait_edge_cases():
    class Fake:
        def __init__(self, headers=None, payload=None, raises=False):
            self.headers = headers or {}
            self._payload = payload
            self._raises = raises

        def json(self):
            if self._raises:
                raise ValueError("not json")
            return self._payload

    assert rate_limit.requested_wait(Fake({"Retry-After": "5"}, {"retry_after": 9})) == 5.0
    assert rate_limit.requested_wait(Fake(payload={"retry_after": 2.5})) == 2.5
    assert rate_limit.requested_wait(Fake(payload={"retry_after": True})) is None
    assert rate_limit.requested_wait(Fake(payload={"retry_after": -1})) is None
    assert rate_limit.requested_wait(Fake(payload={"retry_after": "3"})) is None
    assert rate_limit.requested_wait(Fake(payload=["not", "a", "dict"])) is None
    assert rate_limit.requested_wait(Fake(raises=True)) is None
    assert rate_limit.wait_hint(Fake(payload={"retry_after": 0.2})) == " Try again in 1 second."
    assert rate_limit.wait_hint(Fake(payload={"retry_after": 2.1})) == " Try again in 3 seconds."
    assert rate_limit.wait_hint(Fake(payload={})) == ""


def test_send_with_rate_limit_retries_passes_other_statuses_through(captured_sleeps):
    class Ok:
        status_code = 200

    calls = []
    assert rate_limit.send_with_rate_limit_retries(lambda: calls.append(1) or Ok()).status_code == 200
    assert calls == [1]
    assert captured_sleeps == []

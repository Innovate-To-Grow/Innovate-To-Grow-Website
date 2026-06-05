from datetime import UTC, datetime, timedelta
from email.utils import format_datetime, parsedate_to_datetime

import pytest
import requests
import responses
from i2g_admin import client as client_module
from i2g_admin.client import ApiClient, _parse_retry_after
from i2g_admin.errors import ApiError, AuthError, CliError

BASE = "https://testserver"


@responses.activate
def test_get_returns_payload():
    responses.add(responses.GET, f"{BASE}/admin-api/whoami/", json={"ok": True}, status=200)
    assert ApiClient(BASE + "/", "tok").get("/admin-api/whoami/") == {"ok": True}


@responses.activate
def test_401_raises_auth_error():
    responses.add(responses.GET, f"{BASE}/x/", status=401, json={})
    with pytest.raises(AuthError):
        ApiClient(BASE, "tok").get("/x/")


@responses.activate
def test_204_returns_none():
    responses.add(responses.DELETE, f"{BASE}/x/", status=204)
    assert ApiClient(BASE, "tok").delete("/x/") is None


@responses.activate
def test_400_with_detail():
    responses.add(responses.POST, f"{BASE}/x/", status=400, json={"detail": "bad input"})
    with pytest.raises(ApiError) as excinfo:
        ApiClient(BASE, "tok").post("/x/", json_body={})
    assert excinfo.value.status_code == 400
    assert "bad input" in str(excinfo.value)


@responses.activate
def test_400_without_json_body():
    responses.add(responses.PATCH, f"{BASE}/x/", status=400, body="not json")
    with pytest.raises(ApiError) as excinfo:
        ApiClient(BASE, "tok").patch("/x/", json_body={})
    assert "Request failed (400)" in str(excinfo.value)


@responses.activate
def test_error_payload_not_dict():
    responses.add(responses.GET, f"{BASE}/x/", status=422, json=["a", "b"])
    with pytest.raises(ApiError) as excinfo:
        ApiClient(BASE, "tok").get("/x/")
    assert excinfo.value.status_code == 422


def test_bearer_header_is_set():
    client = ApiClient(BASE, "secret-token")
    assert client.session.headers["Authorization"] == "Bearer secret-token"


def test_rejects_non_https_remote_base_url():
    with pytest.raises(CliError):
        ApiClient("http://remote.example.com", "tok")


def test_allows_http_loopback_base_url():
    client = ApiClient("http://127.0.0.1:8000", "tok")
    assert client.base_url == "http://127.0.0.1:8000"


# --- U5: retries + backoff -------------------------------------------------


@pytest.fixture
def captured_sleeps(monkeypatch):
    """Patch ``time.sleep`` to record delays without actually waiting."""
    delays = []
    monkeypatch.setattr(client_module.time, "sleep", delays.append)
    return delays


@responses.activate
def test_retries_transient_status_then_succeeds(captured_sleeps):
    responses.add(responses.GET, f"{BASE}/x/", status=503, json={})
    responses.add(responses.GET, f"{BASE}/x/", status=200, json={"ok": True})
    client = ApiClient(BASE, "tok", max_attempts=3)
    assert client.get("/x/") == {"ok": True}
    # Exactly one backoff slept between the two attempts.
    assert len(captured_sleeps) == 1
    assert len(responses.calls) == 2


@responses.activate
def test_exhausts_attempts_raises_api_error(captured_sleeps):
    for _ in range(3):
        responses.add(responses.GET, f"{BASE}/x/", status=503, json={"detail": "down"})
    client = ApiClient(BASE, "tok", max_attempts=3)
    with pytest.raises(ApiError) as excinfo:
        client.get("/x/")
    assert excinfo.value.status_code == 503
    # 3 attempts → 2 sleeps between them (no sleep after the final attempt).
    assert len(captured_sleeps) == 2
    assert len(responses.calls) == 3


@responses.activate
def test_retry_after_seconds_overrides_backoff(captured_sleeps, monkeypatch):
    # Force backoff jitter to ~0 so Retry-After clearly wins the max().
    monkeypatch.setattr(client_module.random, "random", lambda: 0.0)
    responses.add(responses.GET, f"{BASE}/x/", status=429, headers={"Retry-After": "7"}, json={})
    responses.add(responses.GET, f"{BASE}/x/", status=200, json={"ok": True})
    client = ApiClient(BASE, "tok", max_attempts=2)
    assert client.get("/x/") == {"ok": True}
    assert captured_sleeps == [7.0]


@responses.activate
def test_backoff_used_when_larger_than_retry_after(captured_sleeps, monkeypatch):
    # Full jitter at its ceiling; Retry-After is small, so backoff wins.
    monkeypatch.setattr(client_module.random, "random", lambda: 1.0)
    monkeypatch.setattr(client_module, "BACKOFF_BASE", 4.0)
    responses.add(responses.GET, f"{BASE}/x/", status=503, headers={"Retry-After": "1"}, json={})
    responses.add(responses.GET, f"{BASE}/x/", status=200, json={"ok": True})
    client = ApiClient(BASE, "tok", max_attempts=2)
    assert client.get("/x/") == {"ok": True}
    assert captured_sleeps == [4.0]


@responses.activate
def test_retry_after_http_date_is_honored(captured_sleeps, monkeypatch):
    monkeypatch.setattr(client_module.random, "random", lambda: 0.0)
    future = datetime.now(UTC) + timedelta(seconds=30)
    responses.add(responses.GET, f"{BASE}/x/", status=503, headers={"Retry-After": format_datetime(future)}, json={})
    responses.add(responses.GET, f"{BASE}/x/", status=200, json={"ok": True})
    client = ApiClient(BASE, "tok", max_attempts=2)
    assert client.get("/x/") == {"ok": True}
    assert len(captured_sleeps) == 1
    # ~30s in the future; allow scheduling slack.
    assert 25.0 <= captured_sleeps[0] <= 30.0


@responses.activate
def test_unparseable_retry_after_falls_back_to_backoff(captured_sleeps, monkeypatch):
    monkeypatch.setattr(client_module.random, "random", lambda: 1.0)
    monkeypatch.setattr(client_module, "BACKOFF_BASE", 2.0)
    responses.add(responses.GET, f"{BASE}/x/", status=503, headers={"Retry-After": "soon"}, json={})
    responses.add(responses.GET, f"{BASE}/x/", status=200, json={"ok": True})
    client = ApiClient(BASE, "tok", max_attempts=2)
    assert client.get("/x/") == {"ok": True}
    assert captured_sleeps == [2.0]


@responses.activate
def test_oversized_retry_after_is_capped(captured_sleeps):
    # A hostile/buggy upstream sending a huge Retry-After must not hang the CLI.
    responses.add(responses.GET, f"{BASE}/x/", status=503, headers={"Retry-After": "inf"}, json={})
    responses.add(responses.GET, f"{BASE}/x/", status=200, json={"ok": True})
    client = ApiClient(BASE, "tok", max_attempts=2)
    assert client.get("/x/") == {"ok": True}
    assert captured_sleeps == [client_module.MAX_RETRY_SLEEP]


@responses.activate
def test_transient_exception_retried_then_succeeds(captured_sleeps):
    responses.add(responses.GET, f"{BASE}/x/", body=requests.ConnectionError("boom"))
    responses.add(responses.GET, f"{BASE}/x/", status=200, json={"ok": True})
    client = ApiClient(BASE, "tok", max_attempts=2)
    assert client.get("/x/") == {"ok": True}
    assert len(captured_sleeps) == 1


@responses.activate
def test_transient_exception_exhausts_attempts_reraises(captured_sleeps):
    responses.add(responses.GET, f"{BASE}/x/", body=requests.Timeout("slow"))
    responses.add(responses.GET, f"{BASE}/x/", body=requests.Timeout("slow"))
    client = ApiClient(BASE, "tok", max_attempts=2)
    with pytest.raises(requests.Timeout):
        client.get("/x/")
    assert len(captured_sleeps) == 1


@responses.activate
def test_single_attempt_does_not_retry_or_sleep(captured_sleeps):
    responses.add(responses.GET, f"{BASE}/x/", status=503, json={"detail": "down"})
    client = ApiClient(BASE, "tok")  # default max_attempts == 1
    with pytest.raises(ApiError) as excinfo:
        client.get("/x/")
    assert excinfo.value.status_code == 503
    assert captured_sleeps == []
    assert len(responses.calls) == 1


def test_max_attempts_normalized_to_at_least_one():
    assert ApiClient(BASE, "tok", max_attempts=0).max_attempts == 1
    assert ApiClient(BASE, "tok", max_attempts=-5).max_attempts == 1


# --- only idempotent methods are retried ------------------------------------


@responses.activate
def test_post_does_not_retry_transient_status(captured_sleeps):
    # A non-idempotent write that 503s may already have committed server-side;
    # resending it would duplicate the row, so POST is sent exactly once.
    for _ in range(3):
        responses.add(responses.POST, f"{BASE}/x/", status=503, json={"detail": "down"})
    client = ApiClient(BASE, "tok", max_attempts=3)
    with pytest.raises(ApiError) as excinfo:
        client.post("/x/", json_body={})
    assert excinfo.value.status_code == 503
    assert captured_sleeps == []
    assert len(responses.calls) == 1


@responses.activate
def test_patch_does_not_retry_transient_status(captured_sleeps):
    for _ in range(3):
        responses.add(responses.PATCH, f"{BASE}/x/", status=503, json={"detail": "down"})
    client = ApiClient(BASE, "tok", max_attempts=3)
    with pytest.raises(ApiError) as excinfo:
        client.patch("/x/", json_body={})
    assert excinfo.value.status_code == 503
    assert captured_sleeps == []
    assert len(responses.calls) == 1


@responses.activate
def test_post_does_not_retry_transient_exception(captured_sleeps):
    responses.add(responses.POST, f"{BASE}/x/", body=requests.ConnectionError("boom"))
    responses.add(responses.POST, f"{BASE}/x/", status=200, json={"ok": True})
    client = ApiClient(BASE, "tok", max_attempts=3)
    with pytest.raises(requests.ConnectionError):
        client.post("/x/", json_body={})
    assert captured_sleeps == []
    assert len(responses.calls) == 1


@responses.activate
def test_get_retries_transient_status_then_succeeds(captured_sleeps):
    # Idempotent reads still retry the configured number of attempts.
    responses.add(responses.GET, f"{BASE}/x/", status=503, json={})
    responses.add(responses.GET, f"{BASE}/x/", status=200, json={"ok": True})
    client = ApiClient(BASE, "tok", max_attempts=3)
    assert client.get("/x/") == {"ok": True}
    assert len(captured_sleeps) == 1
    assert len(responses.calls) == 2


@responses.activate
def test_get_all_transient_exhausts_attempts(captured_sleeps):
    for _ in range(3):
        responses.add(responses.GET, f"{BASE}/x/", status=503, json={"detail": "down"})
    client = ApiClient(BASE, "tok", max_attempts=3)
    with pytest.raises(ApiError) as excinfo:
        client.get("/x/")
    assert excinfo.value.status_code == 503
    assert len(captured_sleeps) == 2
    assert len(responses.calls) == 3


@responses.activate
def test_get_single_attempt_not_retried(captured_sleeps):
    # max_attempts == 1 leaves GET behavior unchanged: one call, no sleep.
    responses.add(responses.GET, f"{BASE}/x/", status=503, json={"detail": "down"})
    client = ApiClient(BASE, "tok")  # default max_attempts == 1
    with pytest.raises(ApiError) as excinfo:
        client.get("/x/")
    assert excinfo.value.status_code == 503
    assert captured_sleeps == []
    assert len(responses.calls) == 1


def test_parse_retry_after_edge_cases(monkeypatch):
    assert _parse_retry_after(None) is None
    assert _parse_retry_after("") is None
    assert _parse_retry_after("  ") is None
    assert _parse_retry_after("not-a-date") is None
    assert _parse_retry_after("3") == 3.0
    # A past HTTP-date clamps to 0 rather than going negative.
    past = datetime.now(UTC) - timedelta(seconds=60)
    assert _parse_retry_after(format_datetime(past)) == 0.0
    # A naive (timezone-less) HTTP-date is still parsed to a non-negative delay.
    # parsedate_to_datetime returns a naive datetime here, so .timestamp() reads it
    # in local time; pin time.time() so the assertion is timezone-independent.
    naive = "Fri, 05 Jun 2026 06:57:22"
    expected = parsedate_to_datetime(naive).timestamp()
    monkeypatch.setattr(client_module.time, "time", lambda: expected - 15.0)
    assert _parse_retry_after(naive) == pytest.approx(15.0)

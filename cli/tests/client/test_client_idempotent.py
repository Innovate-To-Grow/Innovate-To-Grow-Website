"""Only idempotent methods (GET) are retried; POST/PATCH are sent exactly once."""

import pytest
import requests
import responses
from i2g_admin.client import ApiClient
from i2g_admin.core.errors import ApiError

BASE = "https://testserver"


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

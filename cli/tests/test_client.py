import pytest
import responses
from i2g_admin.client import ApiClient
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

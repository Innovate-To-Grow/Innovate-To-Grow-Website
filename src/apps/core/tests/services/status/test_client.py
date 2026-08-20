import json
from io import BytesIO
from unittest.mock import MagicMock
from urllib.error import HTTPError, URLError

from botocore.credentials import Credentials
from django.test import SimpleTestCase, override_settings

from apps.core.services.status.client import (
    MAX_RESPONSE_BYTES,
    InternalStatusApiClient,
    StatusFetchError,
    validate_status_payload,
)

VALID_URL = "https://abc123def4.execute-api.us-west-2.amazonaws.com/prod/internal/status"


def status_payload(**overrides):
    payload = {
        "schemaVersion": 1,
        "generatedAt": "2026-08-20T10:00:00Z",
        "partial": False,
        "errors": [],
        "stack": {"name": "i2g-status", "resources": []},
        "services": [],
        "probes": [],
        "alarms": [],
    }
    payload.update(overrides)
    return payload


class FakeResponse:
    def __init__(self, payload=None, *, status=200, content_type="application/json", raw=None):
        self.status = status
        self.headers = {"Content-Type": content_type}
        self.raw = raw if raw is not None else json.dumps(payload).encode()
        self.read_size = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def getcode(self):
        return self.status

    def read(self, size=-1):
        self.read_size = size
        return self.raw[:size] if size >= 0 else self.raw


class FakeOpener:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.request = None
        self.timeout = None

    def open(self, request, *, timeout):
        self.request = request
        self.timeout = timeout
        if self.error:
            raise self.error
        return self.response


def session_factory_with_credentials(**_kwargs):
    session = MagicMock()
    session.get_credentials.return_value = Credentials("AKIATEST", "test-secret", "session-token")
    return session


@override_settings(STATUS_INTERNAL_API_URL=VALID_URL, STATUS_API_REGION="us-west-2")
class InternalStatusApiClientTests(SimpleTestCase):
    def _client(self, opener):
        return InternalStatusApiClient(
            session_factory=session_factory_with_credentials,
            opener_factory=lambda: opener,
        )

    def test_fetch_signs_execute_api_get_with_ambient_credentials(self):
        response = FakeResponse(status_payload())
        opener = FakeOpener(response)

        result = self._client(opener).fetch()

        self.assertEqual(result["schemaVersion"], 1)
        self.assertEqual(opener.timeout, 8)
        self.assertEqual(opener.request.full_url, VALID_URL)
        self.assertEqual(opener.request.method, "GET")
        self.assertTrue(opener.request.get_header("Authorization").startswith("AWS4-HMAC-SHA256"))
        self.assertEqual(opener.request.get_header("X-amz-security-token"), "session-token")
        self.assertIn("execute-api/aws4_request", opener.request.get_header("Authorization"))
        self.assertEqual(response.read_size, MAX_RESPONSE_BYTES + 1)

    def test_missing_ambient_credentials_is_sanitized(self):
        session = MagicMock()
        session.get_credentials.return_value = None
        client = InternalStatusApiClient(
            session_factory=lambda **kwargs: session,
            opener_factory=lambda: FakeOpener(FakeResponse(status_payload())),
        )

        with self.assertRaises(StatusFetchError) as raised:
            client.fetch()

        self.assertEqual(raised.exception.reason, "credentials")
        self.assertNotIn("AKIA", str(raised.exception))

    def test_unexpected_transport_error_does_not_log_raw_exception_details(self):
        opener = FakeOpener(error=RuntimeError("Authorization: secret-signed-header"))

        with self.assertLogs("apps.core.services.status.client", level="ERROR") as captured:
            with self.assertRaises(StatusFetchError) as raised:
                self._client(opener).fetch()

        self.assertEqual(raised.exception.reason, "error")
        self.assertNotIn("secret-signed-header", "\n".join(captured.output))

    def test_configuration_requires_exact_https_regional_execute_api_route(self):
        invalid_urls = (
            "",
            "http://abc123def4.execute-api.us-west-2.amazonaws.com/prod/internal/status",
            "https://abc123def4.execute-api.us-east-1.amazonaws.com/prod/internal/status",
            "https://example.com/prod/internal/status",
            "https://abc123def4.execute-api.us-west-2.amazonaws.com/dev/internal/status",
            "https://abc123def4.execute-api.us-west-2.amazonaws.com/prod/internal/status/",
            "https://abc123def4.execute-api.us-west-2.amazonaws.com/prod/internal/status?debug=1",
            "https://user@abc123def4.execute-api.us-west-2.amazonaws.com/prod/internal/status",
            "https://abc123def4.execute-api.us-west-2.amazonaws.com:bad/prod/internal/status",
        )
        for value in invalid_urls:
            with self.subTest(value=value):
                client = InternalStatusApiClient(
                    url=value,
                    region="us-west-2",
                    session_factory=session_factory_with_credentials,
                    opener_factory=lambda: FakeOpener(FakeResponse(status_payload())),
                )
                with self.assertRaises(StatusFetchError) as raised:
                    client.fetch()
                self.assertIn(raised.exception.reason, {"unconfigured", "invalid_configuration"})

    def test_rejects_redirect_without_following_it(self):
        error = HTTPError(VALID_URL, 302, "Found", {"Location": "https://attacker.example"}, BytesIO())
        with self.assertRaises(StatusFetchError) as raised:
            self._client(FakeOpener(error=error)).fetch()
        self.assertEqual(raised.exception.reason, "redirect")

    def test_maps_permission_throttle_upstream_and_timeout_errors(self):
        cases = (
            (HTTPError(VALID_URL, 403, "Forbidden", {}, BytesIO()), "permission"),
            (HTTPError(VALID_URL, 429, "Slow down", {}, BytesIO()), "throttled"),
            (HTTPError(VALID_URL, 503, "Unavailable", {}, BytesIO()), "upstream"),
            (URLError(TimeoutError("private endpoint detail")), "timeout"),
        )
        for error, reason in cases:
            with self.subTest(reason=reason):
                with self.assertRaises(StatusFetchError) as raised:
                    self._client(FakeOpener(error=error)).fetch()
                self.assertEqual(raised.exception.reason, reason)
                self.assertNotIn("private endpoint detail", str(raised.exception))

    def test_rejects_non_json_invalid_json_and_oversized_responses(self):
        cases = (
            FakeResponse(status_payload(), content_type="text/html"),
            FakeResponse(raw=b"not-json"),
            FakeResponse(raw=b"{" + (b"x" * MAX_RESPONSE_BYTES) + b"}"),
        )
        for response in cases:
            with self.subTest(content_type=response.headers["Content-Type"], size=len(response.raw)):
                with self.assertRaises(StatusFetchError) as raised:
                    self._client(FakeOpener(response)).fetch()
                self.assertEqual(raised.exception.reason, "invalid_response")

    def test_rejects_wrong_or_oversized_schema(self):
        invalid_payloads = (
            status_payload(schemaVersion=2),
            status_payload(schemaVersion=True),
            status_payload(generatedAt=""),
            status_payload(services="not-a-list"),
            status_payload(services=[{}] * 51),
            status_payload(stack={"resources": [{}] * 251}),
            status_payload(errors=[{"message": "x" * 4097}]),
            status_payload(stack={"resources": [], "value": float("nan")}),
        )
        for payload in invalid_payloads:
            with self.subTest(keys=list(payload)):
                with self.assertRaises(StatusFetchError) as raised:
                    validate_status_payload(payload)
                self.assertEqual(raised.exception.reason, "invalid_response")

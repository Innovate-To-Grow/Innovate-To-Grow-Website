import requests

from .config import validate_base_url
from .errors import ApiError, AuthError

# (connect, read) timeout so a hung server can never block the CLI indefinitely.
REQUEST_TIMEOUT = (5, 30)
# Transient statuses U5 retries; declared here so the seam is visible from U1.
RETRY_STATUSES = (429, 500, 502, 503, 504)


class ApiClient:
    """Thin wrapper over a requests.Session with a bearer header and status→error mapping.

    The ``timeout`` / ``max_attempts`` / ``retry_statuses`` knobs are accepted now
    (with today's behavior as defaults: a single attempt) so U5 can implement
    retry/backoff inside ``_send`` without changing this signature or any caller.
    """

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        timeout=REQUEST_TIMEOUT,
        max_attempts: int = 1,
        retry_statuses=RETRY_STATUSES,
    ):
        validate_base_url(base_url)
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_attempts = max_attempts
        self.retry_statuses = tuple(retry_statuses)
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {token}"

    def _send(self, method, url, *, params=None, json_body=None, headers=None):
        """Issue a single HTTP request. U5 turns this into a retry loop."""
        return self.session.request(method, url, params=params, json=json_body, headers=headers, timeout=self.timeout)

    def request(self, method, path, *, params=None, json_body=None, headers=None):
        response = self._send(method, f"{self.base_url}{path}", params=params, json_body=json_body, headers=headers)
        return self._handle(response)

    @staticmethod
    def _handle(response):
        if response.status_code == 401:
            raise AuthError("Token expired or invalid. Run `i2g-admin login`.")
        if response.status_code == 204:
            return None
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if response.status_code >= 400:
            detail = payload.get("detail") if isinstance(payload, dict) else None
            raise ApiError(response.status_code, detail or f"Request failed ({response.status_code}).", payload)
        return payload

    def get(self, path, **kwargs):
        return self.request("GET", path, **kwargs)

    def post(self, path, **kwargs):
        return self.request("POST", path, **kwargs)

    def patch(self, path, **kwargs):
        return self.request("PATCH", path, **kwargs)

    def delete(self, path, **kwargs):
        return self.request("DELETE", path, **kwargs)

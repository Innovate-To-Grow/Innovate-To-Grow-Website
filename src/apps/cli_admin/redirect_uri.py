from urllib.parse import urlsplit

from .constants import LOOPBACK_REDIRECT_HOSTS, LOOPBACK_REDIRECT_PATH


class RedirectUriError(ValueError):
    """Raised when an OAuth redirect_uri is not an allowed loopback URI."""


def validate_loopback_redirect_uri(uri: str) -> str:
    """Enforce an RFC 8252 loopback redirect: http://<loopback-ip>:<port>/callback.

    Rejects https, non-loopback hosts, embedded credentials, query strings,
    fragments, and unexpected paths. Returns the URI unchanged when valid;
    raises RedirectUriError otherwise. There is no default fallback.
    """
    parts = urlsplit(uri or "")
    if parts.scheme != "http":
        raise RedirectUriError("redirect_uri must use the http scheme on a loopback address.")
    if parts.hostname not in LOOPBACK_REDIRECT_HOSTS:
        raise RedirectUriError("redirect_uri host must be a loopback address (127.0.0.1 or ::1).")
    if parts.username or parts.password:
        raise RedirectUriError("redirect_uri must not contain credentials.")
    if parts.query or parts.fragment:
        raise RedirectUriError("redirect_uri must not contain a query string or fragment.")
    if parts.path != LOOPBACK_REDIRECT_PATH:
        raise RedirectUriError(f"redirect_uri path must be {LOOPBACK_REDIRECT_PATH}.")
    try:
        port = parts.port
    except ValueError as exc:
        raise RedirectUriError("redirect_uri has an invalid port.") from exc
    if port is None:
        raise RedirectUriError("redirect_uri must specify a loopback port.")
    return uri

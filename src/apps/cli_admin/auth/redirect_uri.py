from urllib.parse import urlsplit, urlunsplit

from .constants import LOOPBACK_REDIRECT_HOSTS, LOOPBACK_REDIRECT_PATH


class RedirectUriError(ValueError):
    """Raised when an OAuth redirect_uri is not an allowed loopback URI.

    ``public_message`` holds a fixed, developer-facing string that is safe to
    surface in an HTTP response (no user input, no exception/traceback text).
    """

    def __init__(self, public_message: str):
        super().__init__(public_message)
        self.public_message = public_message


def validate_loopback_redirect_uri(uri: str) -> str:
    """Enforce an RFC 8252 loopback redirect: http://<loopback-ip>:<port>/callback.

    Rejects https, non-loopback hosts, embedded credentials, query strings,
    fragments, and unexpected paths. Returns a URL rebuilt from the validated
    components (byte-identical to a valid input) so callers redirect to a value
    assembled from a vetted host allowlist and fixed scheme/path rather than the
    raw user-supplied string. Raises RedirectUriError otherwise; there is no
    default fallback.
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
    # Rebuild from validated parts: the host comes from the loopback allowlist, the
    # scheme/path are constants, and only the vetted port is carried over. IPv6 hosts
    # must be re-bracketed for the netloc. This yields a value byte-identical to a
    # valid input while severing the taint from the raw user string.
    host = parts.hostname
    netloc = f"[{host}]:{port}" if ":" in host else f"{host}:{port}"
    return urlunsplit(("http", netloc, LOOPBACK_REDIRECT_PATH, "", ""))

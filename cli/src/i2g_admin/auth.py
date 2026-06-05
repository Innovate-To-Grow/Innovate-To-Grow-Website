import secrets
import time
import webbrowser
from urllib.parse import urlencode

import requests

from . import config
from .callback_server import CallbackServer
from .errors import AuthError
from .pkce import challenge_s256, generate_verifier

CLIENT_ID = "i2g-admin-cli"
AUTHORIZE_PATH = "/admin-api/oauth/authorize/"
TOKEN_PATH = "/admin-api/oauth/token/"
# Treat a token as expired slightly early to avoid using it mid-request.
EXPIRY_SKEW_SECONDS = 60
# (connect, read) timeout for the token exchange.
EXCHANGE_TIMEOUT = (5, 30)


def login(base_url, *, open_browser=webbrowser.open, server_factory=CallbackServer, timeout=300, profile=None):
    """Run the full Authorization Code + PKCE dance and cache the resulting token."""
    config.validate_base_url(base_url)
    verifier = generate_verifier()
    challenge = challenge_s256(verifier)
    state = generate_verifier()
    server = server_factory()
    try:
        redirect_uri = server.redirect_uri
        authorize_url = (
            base_url.rstrip("/")
            + AUTHORIZE_PATH
            + "?"
            + urlencode(
                {
                    "response_type": "code",
                    "client_id": CLIENT_ID,
                    "code_challenge": challenge,
                    "code_challenge_method": "S256",
                    "redirect_uri": redirect_uri,
                    "state": state,
                }
            )
        )
        open_browser(authorize_url)
        query = server.wait_for_callback(timeout=timeout)
    finally:
        server.close()

    if not query or "code" not in query:
        raise AuthError("Did not receive an authorization code from the browser.")
    if not secrets.compare_digest(query.get("state", ""), state):
        raise AuthError("OAuth state mismatch; aborting (possible CSRF).")

    token = _exchange(base_url, query["code"], verifier, redirect_uri)
    config.save_credentials(
        {
            "base_url": base_url,
            "access_token": token["access_token"],
            "expires_at": time.time() + int(token.get("expires_in", 0)),
        },
        profile=profile,
    )
    return token


def _exchange(base_url, code, verifier, redirect_uri):
    response = requests.post(
        base_url.rstrip("/") + TOKEN_PATH,
        json={
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": verifier,
            "redirect_uri": redirect_uri,
            "client_id": CLIENT_ID,
        },
        timeout=EXCHANGE_TIMEOUT,
    )
    if response.status_code != 200:
        raise AuthError(f"Token exchange failed ({response.status_code}).")
    return response.json()


def _is_expired(creds) -> bool:
    expires_at = creds.get("expires_at")
    if not expires_at:
        return True
    return time.time() >= float(expires_at) - EXPIRY_SKEW_SECONDS


def ensure_token(profile=None):
    """Return (base_url, access_token), reusing a cached token or running login()."""
    creds = config.load_credentials(profile)
    if creds and creds.get("access_token") and creds.get("base_url") and not _is_expired(creds):
        return creds["base_url"], creds["access_token"]
    base_url = config.current_base_url(profile)
    login(base_url, profile=profile)
    creds = config.load_credentials(profile)
    if not creds or not creds.get("access_token"):
        raise AuthError("Login did not produce a token.")
    return creds["base_url"], creds["access_token"]

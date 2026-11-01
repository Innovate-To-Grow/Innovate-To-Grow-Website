"""Shared fixtures for the Gmail API provider tests: generated service-account keys and configured rows.

Nothing here talks to Google: keys are generated locally, and token or send answers are canned ``HttpResponse``s.
"""

import json
import uuid
from datetime import timedelta
from functools import lru_cache

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from django.utils import timezone

from apps.core.models import EmailServiceConfig, GmailApiProviderConfig, GmailApiSubject

SUBJECT = "i2g@g.ucmerced.edu"
SERVICE_ACCOUNT = "i2g-mailer@i2g-mail-project.iam.gserviceaccount.com"
PROJECT = "i2g-mail-project"
CLIENT_ID = "109876543210987654321"
KEY_ID = "0123456789abcdef0123456789abcdef01234567"
TOKEN = "ya29.a0-test-access-token"  # nosec B105 - a canned test token


@lru_cache(maxsize=4)
def rsa_key(bits: int = 2048) -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=bits)


def pem(key=None, *, password: bytes | None = None) -> str:
    key = key or rsa_key()
    encryption = serialization.BestAvailableEncryption(password) if password else serialization.NoEncryption()
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, encryption).decode()


def ec_pem() -> str:
    return pem(ec.generate_private_key(ec.SECP256R1()))


def key_file(**overrides) -> dict:
    """A service-account key file as Google's console writes it (``token_uri`` in its accounts.google.com form)."""
    data = {
        "type": "service_account",
        "project_id": PROJECT,
        "private_key_id": KEY_ID,
        "private_key": pem(),
        "client_email": SERVICE_ACCOUNT,
        "client_id": CLIENT_ID,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://accounts.google.com/o/oauth2/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/i2g-mailer",
        "universe_domain": "googleapis.com",
    }
    data.update(overrides)
    return {key: value for key, value in data.items() if value is not None}


def key_json(**overrides) -> str:
    return json.dumps(key_file(**overrides))


def make_config(
    *, subjects=(SUBJECT,), active=True, key=True, checked=True, verified=True, **fields
) -> GmailApiProviderConfig:
    """A Gmail API config with fake key facts (no stored key) and an allow-list, saved."""
    now = timezone.now()
    values = {"name": "Gmail", "is_active": False}
    if key:
        values.update(
            key_secret_ref="memory:itg/backend/gmail-api/service-account-key",
            key_version_id=str(uuid.uuid4()),
            service_account_email=SERVICE_ACCOUNT,
            client_id=CLIENT_ID,
            key_id=KEY_ID,
            project_id=PROJECT,
            key_installed_at=now - timedelta(hours=1),
        )
        if checked:
            values["access_checked_at"] = now - timedelta(minutes=30)
    values.update(fields)
    config = GmailApiProviderConfig.objects.create(**values)
    for subject in subjects:
        GmailApiSubject.objects.create(
            config=config, subject=subject, verified_at=now - timedelta(minutes=30) if key and verified else None
        )
    if active:
        config.is_active = True
        config.save()
    return config


def make_email_config(*, provider=EmailServiceConfig.Provider.GMAIL, from_email=SUBJECT) -> EmailServiceConfig:
    """An active Notification Delivery row saved without activation checks (as a test fixture)."""
    return EmailServiceConfig.objects.create(name="Gmail", is_active=True, provider=provider, from_email=from_email)


def _response(status: int, body: dict, headers=None):
    from apps.core.services.email.transport import HttpResponse

    return HttpResponse(status=status, headers=headers or {}, body=json.dumps(body).encode())


def token_response(*, status=200, expires_in=3599, scope="https://www.googleapis.com/auth/gmail.send", **extra):
    if status != 200:
        return _response(status, extra)
    body = {"access_token": TOKEN, "expires_in": expires_in, "token_type": "Bearer", **extra}
    if scope is not None:
        body["scope"] = scope
    return _response(200, body)


def token_error(error: str, description: str = "", *, status=400, headers=None):
    body = {"error": error}
    if description:
        body["error_description"] = description
    return _response(status, body, headers)


def send_response(*, status=200, labels=("SENT",), headers=None, error=None):
    if status == 200:
        body = {"id": "18c0ffee1234abcd", "threadId": "18c0ffee1234abcd", "labelIds": list(labels)}
    else:
        body = {"error": error or {"code": status, "message": "error"}}
    return _response(status, body, headers)


def gmail_error(status: int, *, reason="", message="", status_text="", details_reason=""):
    """A Gmail error body in the legacy shape (``errors[0].reason``) and/or the ErrorInfo shape (``details``)."""
    error = {"code": status, "message": message}
    if reason:
        error["errors"] = [{"domain": "usageLimits", "reason": reason, "message": message}]
    if status_text:
        error["status"] = status_text
    if details_reason:
        error["details"] = [
            {"@type": "type.googleapis.com/google.rpc.ErrorInfo", "reason": details_reason, "domain": "googleapis.com"}
        ]
    return send_response(status=status, error=error)

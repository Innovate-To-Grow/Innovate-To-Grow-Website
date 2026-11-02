"""Google service-account JWT assertions (RS256) for domain-wide delegation, and the RSA keys that sign them.

Google documents the format in "Using OAuth 2.0 for Server to Server Applications": the header names ``RS256`` and
may carry the key id as ``kid``; the claims name the service account as ``iss``, the impersonated user as ``sub``,
the requested scopes as ``scope``, ``https://oauth2.googleapis.com/token`` as ``aud`` ("always", whatever the key
file's ``token_uri`` says), and expire at most an hour after ``iat``. An assertion is itself a bearer credential
for its lifetime: it is never logged or stored.
"""

import time

import jwt
from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.conf import settings
from django.views.decorators.debug import sensitive_variables

GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"
TOKEN_URI = "https://oauth2.googleapis.com/token"  # nosec B105 - a URL, not a credential

UNREADABLE_KEY = "The private key could not be read. Use the unencrypted PEM key Google wrote into the key file."
RSA_ONLY = "Google service-account keys are RSA keys; this is another kind of key."
KEY_TOO_SMALL = "The RSA key is smaller than the site accepts."


class SigningKeyError(ValueError):
    """The private key cannot sign assertions. Fixed text, never any part of the key."""


@sensitive_variables()
def load_signing_key(private_key_pem) -> rsa.RSAPrivateKey:
    """An unencrypted RSA private key of at least ``GMAIL_API["min_rsa_key_bits"]``; anything else is refused."""
    key = None
    if isinstance(private_key_pem, str) and private_key_pem.isascii():
        try:
            key = serialization.load_pem_private_key(private_key_pem.encode("ascii"), password=None)
        except UnsupportedAlgorithm:
            raise SigningKeyError(RSA_ONLY) from None
        except (ValueError, TypeError):
            key = None  # unreadable, or encrypted (cryptography raises TypeError when a password is needed)
    if key is None:
        raise SigningKeyError(UNREADABLE_KEY)
    if not isinstance(key, rsa.RSAPrivateKey):
        raise SigningKeyError(RSA_ONLY)
    if key.key_size < settings.GMAIL_API["min_rsa_key_bits"]:
        raise SigningKeyError(KEY_TOO_SMALL)
    return key


@sensitive_variables()
def build_assertion(
    *, client_email: str, key_id: str, private_key: rsa.RSAPrivateKey, subject: str, scope: str = GMAIL_SEND_SCOPE
) -> str:
    """A signed assertion asking for *scope* as *subject*. The send path always uses gmail.send; only the access
    check's breadth probe passes another scope (and never uses what it gets)."""
    now = int(time.time())
    claims = {
        "iss": client_email,
        "sub": subject,
        "scope": scope,
        "aud": TOKEN_URI,
        "iat": now,
        "exp": now + settings.GMAIL_API["assertion_lifetime_seconds"],
    }
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"typ": "JWT", "kid": key_id})

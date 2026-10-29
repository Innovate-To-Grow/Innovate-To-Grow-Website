"""Shared fixtures for Microsoft Graph tests: configs with a mailbox scope, and throwaway certificates."""

import datetime
from functools import lru_cache

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.x509.oid import NameOID

from apps.core.models import MicrosoftGraphMailboxScope, MicrosoftGraphProviderConfig

SEND_AND_READ = MicrosoftGraphMailboxScope.Permission.SEND_AND_READ


def create_graph_config(*, scope=(), permission=SEND_AND_READ, **values):
    """Save a Graph config (client-secret auth unless *values* say otherwise) and grant *permission* on *scope*."""
    values.setdefault("auth_method", MicrosoftGraphProviderConfig.AuthMethod.CLIENT_SECRET)
    config = MicrosoftGraphProviderConfig.objects.create(**values)
    grant(config, *scope, permission=permission)
    return config


def grant(config, *mailboxes, permission=SEND_AND_READ):
    for mailbox in mailboxes:
        MicrosoftGraphMailboxScope.objects.create(config=config, mailbox=mailbox, permission=permission)
    return config


def certificate_pair(*, days_valid=365, key_size=2048, not_before_days=-1, ec_key=False):
    """A self-signed certificate and its unencrypted private key, both PEM text."""
    key = _ec_key() if ec_key else _rsa_key(key_size)
    now = datetime.datetime.now(datetime.UTC)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "i2g-graph-test")])
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now + datetime.timedelta(days=not_before_days))
        .not_valid_after(now + datetime.timedelta(days=days_valid))
        .sign(key, hashes.SHA256())
    )
    certificate_pem = certificate.public_bytes(serialization.Encoding.PEM).decode()
    key_pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
    return certificate_pem, key_pem


@lru_cache(maxsize=4)
def _rsa_key(key_size):
    # RSA generation is slow, so one key per size serves every test; certificates still differ per call.
    return rsa.generate_private_key(public_exponent=65537, key_size=key_size)


def _ec_key():
    return ec.generate_private_key(ec.SECP256R1())

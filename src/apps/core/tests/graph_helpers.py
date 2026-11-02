"""Shared fixtures for Microsoft Graph tests: configs with a mailbox scope and an installed certificate.

Certificates are throwaway and self-signed; their private keys go to the configured credential store, which is the
process-memory store under the test settings, so nothing touches disk or AWS.
"""

import dataclasses
import datetime
from functools import lru_cache

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.x509.oid import NameOID
from django.utils import timezone

from apps.core.models import MicrosoftGraphCertificate, MicrosoftGraphMailboxScope, MicrosoftGraphProviderConfig
from apps.core.services.email.graph.auth import GraphCredential
from apps.core.services.email.graph.certificate import describe_certificate
from apps.core.services.email.graph.credential import stored_key

SEND_AND_READ = MicrosoftGraphMailboxScope.Permission.SEND_AND_READ
TENANT_ID = "11111111-2222-3333-4444-555555555555"
CLIENT_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def create_graph_config(*, scope=(), permission=SEND_AND_READ, certificate=True, **values):
    """Save a Graph config, install a current certificate (unless ``certificate=False``) and grant *scope*.

    An active config with a certificate is saved inactive and activated once the certificate is installed, as an
    admin would, so it also passes the takeover rule when email already uses Graph.
    """
    values.setdefault("tenant_id", TENANT_ID)
    values.setdefault("client_id", CLIENT_ID)
    activate = bool(values.get("is_active") and certificate)
    config = MicrosoftGraphProviderConfig.objects.create(**values | ({"is_active": False} if activate else {}))
    if certificate:
        install_test_certificate(config)
    grant(config, *scope, permission=permission)
    if activate:
        config.is_active = True
        config.save()
    return config


def grant(config, *mailboxes, permission=SEND_AND_READ):
    for mailbox in mailboxes:
        MicrosoftGraphMailboxScope.objects.create(config=config, mailbox=mailbox, permission=permission)
    return config


def install_test_certificate(
    config, *, state=MicrosoftGraphCertificate.State.CURRENT, fresh_key=False, entra_check="ok", **certificate_options
):
    """A certificate row pinned to its key in the credential store, written directly (no Entra check)."""
    certificate, key = make_certificate(fresh_key=fresh_key, **certificate_options)
    stored = stored_key.store_key(key)
    return MicrosoftGraphCertificate.objects.create(
        config=config,
        state=state,
        tenant_id=config.tenant_id,
        client_id=config.client_id,
        store_arn=stored.arn,
        store_version_id=stored.version_id,
        entra_check=entra_check,
        entra_checked_at=timezone.now(),
        **dataclasses.asdict(describe_certificate(certificate)),
    )


def make_test_credential(*, tenant_id=TENANT_ID, client_id=CLIENT_ID, fresh_key=False, **certificate_options):
    """A ``GraphCredential`` whose pinned key is in the credential store (works without a database)."""
    certificate, key = make_certificate(fresh_key=fresh_key, **certificate_options)
    facts = describe_certificate(certificate)
    stored = stored_key.store_key(key)
    return GraphCredential(
        tenant_id=tenant_id,
        client_id=client_id,
        x5t_s256=facts.x5t_s256,
        public_key_sha256=facts.public_key_sha256,
        key_arn=stored.arn,
        key_version_id=stored.version_id,
    )


def make_certificate(
    *, days_valid=365, key_size=2048, not_before_days=-1, ec_key=False, fresh_key=False, key_index=0, key=None
):
    """A self-signed certificate object and its private key object.

    The RSA key is shared per (*key_size*, *key_index*) across tests; ``fresh_key=True`` generates a new one.
    """
    if key is None:
        key = _ec_key() if ec_key else (_new_rsa_key(key_size) if fresh_key else _rsa_key(key_size, key_index))
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
    return certificate, key


def certificate_pair(**options):
    """A self-signed certificate and its unencrypted private key, both PEM text."""
    certificate, key = make_certificate(**options)
    certificate_pem = certificate.public_bytes(serialization.Encoding.PEM).decode()
    key_pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
    return certificate_pem, key_pem


def private_key_lines(key=None, *, key_size=2048):
    """The base64 body lines of a private key's PKCS#8 PEM (the shared test key by default), for leak scans."""
    key = key or _rsa_key(key_size)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    return [line for line in pem.decode().splitlines() if line and not line.startswith("-----")]


@lru_cache(maxsize=8)
def _rsa_key(key_size, key_index=0):
    # RSA generation is slow, so one key per size (and index) serves every test; certificates still differ per call.
    return _new_rsa_key(key_size)


def _new_rsa_key(key_size):
    return rsa.generate_private_key(public_exponent=65537, key_size=key_size)


def _ec_key():
    return ec.generate_private_key(ec.SECP256R1())

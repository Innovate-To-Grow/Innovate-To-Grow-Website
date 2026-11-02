"""Fixtures for the Microsoft Graph certificate admin pages: a superuser, an active config and the faked Entra."""

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse

from apps.core.services.email.graph.credential.lifecycle import install_certificate
from apps.core.tests.graph_helpers import create_graph_config, make_certificate
from apps.core.tests.services.graph_credential.helpers import LifecycleFixtureMixin, make_superuser, parsed_certificate
from apps.core.tests.services.graph_credential.test_parsing import PASSPHRASE, key_pem, p12, pem

SENDER = "i2g@contoso.com"
P12_PASSWORD = "p12-password-that-must-never-leak"
PREFIX = "admin:core_microsoftgraphproviderconfig"


def upload(name, content):
    return SimpleUploadedFile(name, content if isinstance(content, bytes) else content.encode())


class CertificatePagesMixin(LifecycleFixtureMixin):
    """Logged in as a superuser; ``self.config`` is active and scoped, with no certificate yet."""

    def setUp(self):
        super().setUp()
        self.enterContext(override_settings(ADMIN_REQUIRE_CONFIRMATION=False))
        cache.clear()
        self.superuser = make_superuser()
        self.client.force_login(self.superuser)
        self.config = create_graph_config(name="Graph", is_active=True, certificate=False, scope=(SENDER,))
        self.certificate, self.key = make_certificate()

    def url(self, name, config=None):
        return reverse(f"{PREFIX}_{name}", args=[(config or self.config).pk])

    @property
    def change_url(self):
        return self.url("change")

    def install_existing(self, **certificate_options):
        """Install a certificate through the service, as an earlier admin session would have."""
        parsed, key = parsed_certificate(**certificate_options)
        return install_certificate(self.config, parsed, actor=self.superuser), key

    def pem_data(self, *, certificate=None, key=None, **extra):
        return {
            "certificate_text": pem(certificate or self.certificate),
            "private_key_text": key_pem(key or self.key),
            **extra,
        }

    def p12_data(self, password=P12_PASSWORD, **extra):
        return {"bundle": upload("i2g.p12", p12(self.key, self.certificate, password)), "password": password, **extra}

    def encrypted_pem_data(self):
        return {
            "certificate_text": pem(self.certificate),
            "private_key_text": key_pem(self.key, passphrase=PASSPHRASE),
            "password": PASSPHRASE,
        }


__all__ = ["P12_PASSWORD", "PASSPHRASE", "SENDER", "CertificatePagesMixin", "key_pem", "p12", "pem", "upload"]

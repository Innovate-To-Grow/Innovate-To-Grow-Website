from django.db import models
from django.utils import timezone

from ..control import ProjectControlModel


class MicrosoftGraphCertificate(ProjectControlModel):
    """A certificate installed for a Microsoft Graph config: public data and a pointer, never the private key.

    The private key lives in the credential store (AWS Secrets Manager in production). ``store_arn`` and
    ``store_version_id`` pin the exact stored version the site signs with, so nothing ever reads "whatever is
    current" in the store. A config has at most one current certificate and keeps the one it replaced as previous,
    for rollback; replaced and removed rows stay as history.
    """

    class State(models.TextChoices):
        CURRENT = "current", "Current"
        PREVIOUS = "previous", "Previous (kept for rollback)"
        REMOVED = "removed", "Removed"

    class EntraCheck(models.TextChoices):
        OK = "ok", "Token issued"
        NOT_TRUSTED = "not_trusted", "Not trusted by Entra yet"
        UNREACHABLE = "unreachable", "Entra could not be reached"

    LIVE_STATES = (State.CURRENT, State.PREVIOUS)

    config = models.ForeignKey(
        "core.MicrosoftGraphProviderConfig", on_delete=models.CASCADE, related_name="certificates"
    )
    state = models.CharField(max_length=16, choices=State.choices, db_index=True)
    tenant_id = models.CharField(max_length=253, verbose_name="Tenant ID", help_text="The tenant it was tested in.")
    client_id = models.CharField(max_length=64, verbose_name="Client ID", help_text="The app it was tested for.")
    certificate_pem = models.TextField(verbose_name="Certificate (PEM)", help_text="The leaf certificate only.")
    sha1_thumbprint = models.CharField(
        max_length=40,
        verbose_name="Thumbprint (SHA-1)",
        help_text="Upper-case hex, as Entra shows it under Certificates & secrets.",
    )
    sha256_fingerprint = models.CharField(max_length=64, verbose_name="SHA-256 Fingerprint")
    x5t_s256 = models.CharField(
        max_length=43, verbose_name="x5t#S256", help_text="Base64url SHA-256 thumbprint sent in each assertion."
    )
    public_key_sha256 = models.CharField(
        max_length=64,
        verbose_name="Public Key SHA-256",
        help_text="SHA-256 of the public key (SubjectPublicKeyInfo); the stored private key must match it.",
    )
    subject = models.TextField(verbose_name="Subject")
    issuer = models.TextField(verbose_name="Issuer")
    serial_number = models.CharField(max_length=128, verbose_name="Serial Number")
    key_bits = models.PositiveIntegerField(verbose_name="RSA Key Size")
    not_before = models.DateTimeField(verbose_name="Valid From")
    not_after = models.DateTimeField(verbose_name="Valid Until")
    store_arn = models.CharField(max_length=2048, verbose_name="Key Store Reference")
    store_version_id = models.CharField(max_length=64, verbose_name="Key Store Version")
    entra_check = models.CharField(max_length=16, choices=EntraCheck.choices, verbose_name="Entra Check")
    entra_check_code = models.CharField(max_length=96, blank=True, default="", verbose_name="Entra Error Code")
    entra_checked_at = models.DateTimeField(verbose_name="Entra Checked")
    removed_at = models.DateTimeField(null=True, blank=True, verbose_name="Removed")
    removal_note = models.CharField(max_length=255, blank=True, default="", verbose_name="Removal Note")

    class Meta:
        verbose_name = "Microsoft Graph Certificate"
        verbose_name_plural = "Microsoft Graph Certificates"
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["config"], condition=models.Q(state="current"), name="core_one_current_graph_certificate"
            ),
            models.UniqueConstraint(
                fields=["config"], condition=models.Q(state="previous"), name="core_one_previous_graph_certificate"
            ),
        ]

    def __str__(self):
        return f"{self.sha1_thumbprint} ({self.get_state_display()}, valid until {self.not_after:%Y-%m-%d})"

    @property
    def expired(self) -> bool:
        return self.not_after <= timezone.now()

    def valid_now(self) -> bool:
        """Entra refuses a certificate before its start and after its end date."""
        return self.not_before <= timezone.now() < self.not_after

    def usable_for(self, config) -> bool:
        """Current, valid now, pinned to a stored key, and tested for the config's own tenant and app."""
        return bool(
            self.state == self.State.CURRENT
            and self.store_arn
            and self.store_version_id
            and self.tenant_id == config.tenant_id
            and self.client_id == config.client_id
            and self.valid_now()
        )

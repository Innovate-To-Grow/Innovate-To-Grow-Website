import uuid

from django.db import models
from django.utils import timezone


class RSAKeypair(models.Model):
    """
    Stores an RSA keypair for the site (PEM formatted).
    """

    key_id = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        help_text="Key identifier (UUID).",
    )

    # Optional display name to distinguish usages (e.g., signing, encryption).
    name = models.CharField(
        max_length=255,
        default="site-signing",
        help_text="Human friendly label for this keypair.",
    )

    public_key_pem = models.TextField(
        help_text="Public key in PEM format."
    )

    private_key_pem = models.TextField(
        help_text="Private key in PEM format."
    )

    # Mark which keypair should be used for current operations.
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this keypair is currently active.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    rotated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "RSA Keypair"
        verbose_name_plural = "RSA Keypairs"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.key_id})"

    def rotate(self, public_key_pem: str, private_key_pem: str):
        """
        Replace keys and timestamp the rotation.
        """
        self.public_key_pem = public_key_pem
        self.private_key_pem = private_key_pem
        self.rotated_at = timezone.now()
        self.save(
            update_fields=[
                "public_key_pem",
                "private_key_pem",
                "rotated_at",
            ]
        )

    def deactivate(self):
        """
        Mark this keypair as inactive without deleting it.
        """
        self.is_active = False
        self.save(update_fields=["is_active"])


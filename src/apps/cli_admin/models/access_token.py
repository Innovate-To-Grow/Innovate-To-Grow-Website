import hashlib
import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import ProjectControlModel

from ..constants import ACCESS_TOKEN_TTL

# Record last_used_at at most this often to avoid a DB write on every request.
LAST_USED_THROTTLE_SECONDS = 300


def default_access_token_expiry():
    return timezone.now() + ACCESS_TOKEN_TTL


class CliAccessToken(ProjectControlModel):
    """Bearer token for the i2g-admin CLI. Only the SHA-256 hash is stored.

    A token is valid while it is neither revoked nor expired; validity never
    depends on ``last_used_at``.
    """

    token_hash = models.CharField(max_length=64, unique=True, db_index=True, editable=False)
    member = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="cli_access_tokens")
    expires_at = models.DateTimeField(default=default_access_token_expiry)
    revoked_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    created_ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=300, blank=True, default="")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"CLI token for {self.member_id} (valid={self.is_valid})"

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at

    @property
    def is_revoked(self):
        return self.revoked_at is not None

    @property
    def is_valid(self):
        return not self.is_revoked and not self.is_expired

    @staticmethod
    def generate_raw_token():
        return secrets.token_urlsafe(48)

    @staticmethod
    def hash_token(raw):
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def touch_last_used(self):
        """Throttled write of ``last_used_at`` so auth does not write on every request."""
        now = timezone.now()
        if self.last_used_at is None or (now - self.last_used_at).total_seconds() >= LAST_USED_THROTTLE_SECONDS:
            type(self).objects.filter(pk=self.pk).update(last_used_at=now)
            self.last_used_at = now

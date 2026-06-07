import hashlib
import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import ProjectControlModel

from ..constants import AUTH_CODE_TTL


def default_auth_code_expiry():
    return timezone.now() + AUTH_CODE_TTL


class CliAuthorizationCode(ProjectControlModel):
    """Short-lived, single-use OAuth authorization code for the i2g-admin CLI.

    Only the SHA-256 hash of the raw code is stored. The atomic single-use claim
    (``try_mark_used``) mirrors ``LoginLinkToken`` so a replayed code cannot mint
    a token even under concurrent exchange attempts.
    """

    code_hash = models.CharField(max_length=64, unique=True, db_index=True, editable=False)
    member = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="cli_authorization_codes"
    )
    code_challenge = models.CharField(max_length=128)
    redirect_uri = models.URLField()
    expires_at = models.DateTimeField(default=default_auth_code_expiry)
    is_used = models.BooleanField(default=False)
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"CLI auth code for {self.member_id} (used={self.is_used})"

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at

    @staticmethod
    def generate_raw_code():
        return secrets.token_urlsafe(48)

    @staticmethod
    def hash_code(raw):
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def try_mark_used(self):
        """Atomically claim this code. Returns True on success, False if already used.

        A conditional ``UPDATE ... WHERE is_used=False`` serializes at the DB level
        so only one concurrent exchange attempt wins; the rest get False.
        """
        now = timezone.now()
        updated = type(self).objects.filter(pk=self.pk, is_used=False).update(is_used=True, used_at=now)
        if updated:
            self.is_used = True
            self.used_at = now
        return bool(updated)

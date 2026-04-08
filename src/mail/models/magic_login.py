"""Reusable magic login token for campaign email recipients."""

import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone


def default_expiry():
    return timezone.now() + timezone.timedelta(days=30)


class MagicLoginToken(models.Model):
    token = models.CharField(max_length=128, unique=True, db_index=True, editable=False)
    member = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="magic_login_tokens")
    campaign = models.ForeignKey(
        "mail.EmailCampaign", on_delete=models.SET_NULL, null=True, blank=True, related_name="login_tokens"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(default=default_expiry)
    used_at = models.DateTimeField(null=True, blank=True)
    is_used = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        status = "expired" if self.is_expired else "active"
        return f"MagicLogin for {self.member} ({status})"

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at

    @property
    def is_valid(self):
        return not self.is_expired

    @staticmethod
    def generate_token():
        return secrets.token_urlsafe(48)

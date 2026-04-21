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
        return not self.is_expired and not self.is_used

    def mark_used(self):
        self.is_used = True
        self.used_at = timezone.now()
        self.save(update_fields=["is_used", "used_at"])

    def try_mark_used(self):
        """Atomically claim this token. Returns True on success, False if another
        request consumed it first.

        Guards against the read-then-write race in the login view: two
        concurrent requests could otherwise both read `is_used=False` before
        either saved, and both would be issued JWTs. A conditional UPDATE
        (``WHERE is_used=False``) serializes at the DB level so only one
        request wins.
        """
        now = timezone.now()
        updated = type(self).objects.filter(pk=self.pk, is_used=False).update(is_used=True, used_at=now)
        if updated:
            self.is_used = True
            self.used_at = now
        return bool(updated)

    @staticmethod
    def generate_token():
        return secrets.token_urlsafe(48)

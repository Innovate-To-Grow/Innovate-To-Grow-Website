"""Login link token — the single primitive behind emailed one-click login links.

Issued for campaign emails ({{login_link}}) and event ticket confirmation
emails. One-time by default; the issuing source (campaign or event) can opt
into reusable links, and that flag is read live at login time so unticking it
acts as a kill switch.
"""

import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone


def default_expiry():
    return timezone.now() + timezone.timedelta(days=7)


class LoginLinkToken(models.Model):
    token = models.CharField(max_length=128, unique=True, db_index=True, editable=False)
    member = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="login_link_tokens")
    campaign = models.ForeignKey(
        "mail.EmailCampaign", on_delete=models.SET_NULL, null=True, blank=True, related_name="login_tokens"
    )
    registration = models.ForeignKey(
        "event.EventRegistration",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="login_tokens",
        help_text="Set when this link was issued by a ticket confirmation email.",
    )
    redirect_path = models.CharField(
        max_length=200,
        blank=True,
        default="",
        editable=False,
        help_text="Per-token post-login destination; used when the token has no campaign.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(default=default_expiry)
    used_at = models.DateTimeField(null=True, blank=True)
    is_used = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        status = "expired" if self.is_expired else "active"
        return f"LoginLink for {self.member} ({status})"

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at

    @property
    def is_valid(self):
        return not self.is_expired and not self.is_used

    @property
    def is_reusable(self):
        """Whether the issuing source currently allows repeated logins.

        Read live from the source (campaign or event) rather than stamped on
        the row, so operators can untick the source flag to immediately stop
        further reuse. Orphaned tokens (source deleted) degrade to one-time.
        """
        if self.campaign is not None:
            return self.campaign.login_link_reusable
        if self.registration is not None:
            return self.registration.event.ticket_login_reusable
        return False

    @property
    def effective_redirect_path(self):
        """Post-login destination: campaign setting first, then the per-token path."""
        # Imported lazily: utils.redirects pulls in cms models at import time.
        from apps.mail.utils.redirects import (
            DEFAULT_LOGIN_REDIRECT_PATH,
            get_login_link_redirect_path,
            is_safe_internal_redirect_path,
        )

        if self.campaign is not None:
            return get_login_link_redirect_path(self.campaign)
        if is_safe_internal_redirect_path(self.redirect_path):
            return self.redirect_path.strip()
        return DEFAULT_LOGIN_REDIRECT_PATH

    def mark_used(self):
        self.is_used = True
        self.used_at = timezone.now()
        self.save(update_fields=["is_used", "used_at"])

    def record_reusable_use(self):
        """Audit a login on a reusable link without consuming the token.

        Only called when :attr:`is_reusable` is true; every other path must go
        through :meth:`try_mark_used`. Because this still sets ``is_used``,
        turning the source's reusable flag off later sends the next login
        through ``try_mark_used``, which then rejects the token — a kill switch.
        """
        self.is_used = True
        self.used_at = timezone.now()
        self.save(update_fields=["is_used", "used_at"])

    def try_mark_used(self):
        """Atomically claim this token. Returns True on success, False if another
        request consumed it first.

        Guards against the read-then-write race in the login view: two
        concurrent requests could otherwise both read `is_used=False` before
        either saved, and both would be issued JWTs. A conditional UPDATE
        (``WHERE is_used=False AND expires_at > now``) serializes at the DB
        level so only one unexpired request wins.
        """
        now = timezone.now()
        updated = (
            type(self).objects.filter(pk=self.pk, is_used=False, expires_at__gt=now).update(is_used=True, used_at=now)
        )
        if updated:
            self.is_used = True
            self.used_at = now
        return bool(updated)

    @staticmethod
    def generate_token():
        return secrets.token_urlsafe(48)

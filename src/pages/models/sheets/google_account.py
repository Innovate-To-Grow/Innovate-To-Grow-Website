from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models.base import TimeStampedModel


class OAuthProvider(models.TextChoices):
    GOOGLE = "google", "Google"


class OAuthCredential(TimeStampedModel):
    """
    Stores OAuth 2.0 credentials for a third-party provider (e.g., Google).
    Intended for long-lived API access via refresh tokens.

    Security:
      - refresh_token and access_token should be encrypted at rest.
      - never log tokens.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="oauth_credentials",
        db_index=True,
    )

    provider = models.CharField(
        max_length=32,
        choices=OAuthProvider.choices,
        default=OAuthProvider.GOOGLE,
        db_index=True,
    )

    # For Google: OpenID Connect "sub" (stable unique identifier for the Google account)
    provider_account_id = models.CharField(
        max_length=255,
        help_text="Provider account stable ID (Google OIDC sub).",
        db_index=True,
    )

    # Helpful profile fields (not primary identifiers)
    email = models.EmailField(blank=True, null=True, db_index=True)
    email_verified = models.BooleanField(default=False)
    display_name = models.CharField(max_length=255, blank=True, default="")
    picture_url = models.URLField(blank=True, default="")

    # Scopes granted by the user (store normalized space-separated string or JSON)
    scopes = models.TextField(
        help_text="Granted scopes (space-separated or JSON)."
    )

    # Token endpoint (Google default), keep for portability
    token_uri = models.URLField(
        default="https://oauth2.googleapis.com/token",
        help_text="OAuth token endpoint.",
    )

    token_type = models.CharField(max_length=32, blank=True, default="Bearer")

    # Tokens (SHOULD BE ENCRYPTED)
    refresh_token = models.TextField(
        blank=True,
        null=True,
        help_text="Long-lived refresh token (encrypt at rest).",
    )
    access_token = models.TextField(
        blank=True,
        null=True,
        help_text="Short-lived access token cache (encrypt at rest).",
    )

    # Access token expiry time (UTC)
    expires_at = models.DateTimeField(blank=True, null=True)

    # Operational fields
    revoked_at = models.DateTimeField(blank=True, null=True)
    last_used_at = models.DateTimeField(blank=True, null=True)
    failure_count = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True, default="")

    class Meta:
        constraints = [
            # Prevent the same provider account being linked multiple times
            models.UniqueConstraint(
                fields=["provider", "provider_account_id"],
                name="uniq_provider_provider_account_id",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "provider"]),
            models.Index(fields=["provider", "email"]),
            models.Index(fields=["revoked_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.provider}:{self.provider_account_id} -> user={self.user_id}"

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None

    @property
    def access_token_is_expired(self) -> bool:
        if not self.expires_at:
            return True
        # give a small safety buffer
        return self.expires_at <= timezone.now() + timezone.timedelta(seconds=60)

    def mark_used(self, *, save: bool = True) -> None:
        self.last_used_at = timezone.now()
        if save:
            self.save(update_fields=["last_used_at", "updated_at"])

    def mark_revoked(self, *, reason: str = "", save: bool = True) -> None:
        self.revoked_at = timezone.now()
        if reason:
            self.last_error = reason
        if save:
            self.save(update_fields=["revoked_at", "last_error", "updated_at"])
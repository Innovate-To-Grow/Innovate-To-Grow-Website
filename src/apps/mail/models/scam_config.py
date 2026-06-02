from django.db import models

from apps.core.models.base.control import ProjectControlModel
from apps.mail.services.scam_detector.patterns import BRAND_NAMES


class ScamDetectorConfig(ProjectControlModel):
    """Tunable settings for the inbox scam/phishing detector.

    A singleton-style config (one active row, loaded via ``load()``) so the
    risk thresholds, brand list, trusted-sender allowlist, and the AI review
    toggle can be adjusted from the admin without a deploy.
    """

    RISK_BANDS = [("low", "Low"), ("medium", "Medium"), ("high", "High")]

    name = models.CharField(
        max_length=128,
        default="Default",
        verbose_name="Config Name",
        help_text="A label to identify this configuration.",
    )
    is_active = models.BooleanField(
        default=False,
        verbose_name="Active",
        help_text="Only one config can be active. Activating this will deactivate others.",
    )
    medium_threshold = models.PositiveIntegerField(
        default=3,
        verbose_name="Medium-risk threshold",
        help_text="Total signal score at which a message is flagged medium risk.",
    )
    high_threshold = models.PositiveIntegerField(
        default=7,
        verbose_name="High-risk threshold",
        help_text="Total signal score at which a message is flagged high risk.",
    )
    extra_brands = models.TextField(
        blank=True,
        default="",
        verbose_name="Additional brands",
        help_text="Extra brand names to detect impersonation of, one per line.",
    )
    trusted_senders = models.TextField(
        blank=True,
        default="",
        verbose_name="Trusted senders",
        help_text=(
            "Email addresses or domains to always treat as safe, one per line "
            "(e.g. ucmerced.edu or dean@ucmerced.edu). Skips all scam checks."
        ),
    )
    ai_review_enabled = models.BooleanField(
        default=True,
        verbose_name="Enable AI review",
        help_text=(
            "When on, uncertain (medium-risk) messages are sent to Amazon Bedrock "
            "for a second opinion. Requires an active AWS Credential Config. The "
            "message body (truncated) is sent to your own AWS account."
        ),
    )
    ai_review_band = models.CharField(
        max_length=8,
        choices=RISK_BANDS,
        default="medium",
        verbose_name="AI review band",
        help_text="Only messages at this rule-based risk level are sent for AI review.",
    )

    class Meta:
        verbose_name = "Scam Detector Config"
        verbose_name_plural = "Scam Detector Configs"

    def __str__(self):
        status = " (active)" if self.is_active else ""
        return f"{self.name}{status}"

    def save(self, *args, **kwargs):
        if self.is_active:
            ScamDetectorConfig.objects.filter(is_active=True).exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj = cls.objects.filter(is_active=True).first()
        if obj is None:
            obj = cls.objects.order_by("-updated_at").first()
        return obj if obj is not None else cls(id=None)

    @staticmethod
    def _lines(text: str) -> list[str]:
        return [line.strip().lower() for line in (text or "").splitlines() if line.strip()]

    def brand_keywords(self) -> list[str]:
        return [*BRAND_NAMES, *self._lines(self.extra_brands)]

    def is_trusted_sender(self, from_email: str) -> bool:
        email = (from_email or "").strip().lower()
        if not email:
            return False
        domain = email.rsplit("@", 1)[-1] if "@" in email else ""
        for entry in self._lines(self.trusted_senders):
            if email == entry:
                return True
            if domain and (domain == entry or domain.endswith("." + entry)):
                return True
        return False

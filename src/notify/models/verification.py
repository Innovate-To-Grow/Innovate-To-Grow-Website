from django.db import models


class VerificationRequest(models.Model):
    """
    Verification challenge for email/SMS using either code or link.
    """

    CHANNEL_EMAIL = "email"
    CHANNEL_SMS = "sms"
    CHANNEL_CHOICES = [
        (CHANNEL_EMAIL, "Email"),
        (CHANNEL_SMS, "SMS"),
    ]

    METHOD_CODE = "code"
    METHOD_LINK = "link"
    METHOD_CHOICES = [
        (METHOD_CODE, "Code"),
        (METHOD_LINK, "Link"),
    ]

    STATUS_PENDING = "pending"
    STATUS_VERIFIED = "verified"
    STATUS_EXPIRED = "expired"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_VERIFIED, "Verified"),
        (STATUS_EXPIRED, "Expired"),
        (STATUS_FAILED, "Failed"),
    ]

    channel = models.CharField(
        max_length=10,
        choices=CHANNEL_CHOICES,
        help_text="Verification channel (email or SMS).",
    )
    method = models.CharField(
        max_length=10,
        choices=METHOD_CHOICES,
        help_text="Verification delivery method (code or link).",
    )
    target = models.CharField(
        max_length=255,
        help_text="Email address or phone number to verify.",
    )
    purpose = models.CharField(
        max_length=64,
        default="contact_verification",
        help_text="Purpose of the verification (e.g., contact_verification).",
    )
    code = models.CharField(
        max_length=12,
        blank=True,
        null=True,
        help_text="Verification code when method is code.",
    )
    token = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        db_index=True,
        help_text="Verification token when method is link.",
    )
    expires_at = models.DateTimeField(
        help_text="Expiration timestamp for this verification request.",
    )
    attempts = models.PositiveIntegerField(
        default=0,
        help_text="Number of verification attempts made.",
    )
    max_attempts = models.PositiveIntegerField(
        default=5,
        help_text="Maximum allowed verification attempts.",
    )
    status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        help_text="Current status of the verification request.",
    )
    verified_at = models.DateTimeField(
        blank=True,
        null=True,
        help_text="Timestamp when verification succeeded.",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this verification was created.",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="When this verification was last updated.",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["channel", "target", "method", "purpose"]),
            models.Index(fields=["expires_at"]),
            models.Index(fields=["status"]),
            models.Index(fields=["code"]),
            models.Index(fields=["token"]),
        ]
        verbose_name = "Verification Request"
        verbose_name_plural = "Verification Requests"

    def __str__(self) -> str:
        return f"{self.channel}:{self.method}:{self.target} ({self.purpose})"


class NotificationLog(models.Model):
    """
    Delivery log for outgoing notifications (email/SMS).
    """

    CHANNEL_EMAIL = VerificationRequest.CHANNEL_EMAIL
    CHANNEL_SMS = VerificationRequest.CHANNEL_SMS
    CHANNEL_CHOICES = VerificationRequest.CHANNEL_CHOICES

    STATUS_PENDING = "pending"
    STATUS_SENT = "sent"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_SENT, "Sent"),
        (STATUS_FAILED, "Failed"),
    ]

    channel = models.CharField(
        max_length=10,
        choices=CHANNEL_CHOICES,
        help_text="Notification channel (email or SMS).",
    )
    target = models.CharField(
        max_length=255,
        help_text="Email address or phone number notified.",
    )
    subject = models.CharField(
        max_length=255,
        blank=True,
        help_text="Subject for email notifications.",
    )
    message = models.TextField(
        help_text="Notification body content.",
    )
    provider = models.CharField(
        max_length=64,
        default="console",
        help_text="Provider used to send the notification.",
    )
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        help_text="Delivery status.",
    )
    error_message = models.TextField(
        blank=True,
        help_text="Error details if delivery failed.",
    )
    sent_at = models.DateTimeField(
        blank=True,
        null=True,
        help_text="When the notification was sent.",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the notification log was created.",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="When the notification log was last updated.",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["channel", "target"]),
            models.Index(fields=["status"]),
            models.Index(fields=["created_at"]),
        ]
        verbose_name = "Notification Log"
        verbose_name_plural = "Notification Logs"

    def __str__(self) -> str:
        return f"{self.channel}:{self.target} [{self.status}]"


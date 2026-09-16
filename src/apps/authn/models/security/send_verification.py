from django.db import models

from apps.core.models import ProjectControlModel


class SendVerificationChallenge(ProjectControlModel):
    """Server-issued ALTCHA challenge bound to one operation and destination."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CONSUMED = "consumed", "Consumed"
        EXPIRED = "expired", "Expired"

    class DestinationKind(models.TextChoices):
        EMAIL = "email", "Email"
        PHONE = "phone", "Phone"

    class PrincipalType(models.TextChoices):
        MEMBER = "member", "Member"
        SESSION = "session", "Session"
        ANONYMOUS = "anonymous", "Anonymous"

    operation = models.CharField(max_length=64, db_index=True)
    destination_kind = models.CharField(max_length=8, choices=DestinationKind.choices)
    destination_normalized = models.CharField(max_length=254, db_index=True)
    principal_type = models.CharField(max_length=16, choices=PrincipalType.choices)
    principal_key = models.CharField(max_length=64, blank=True, default="")
    algorithm = models.CharField(max_length=32)
    cost = models.PositiveIntegerField()
    expires_at = models.DateTimeField(db_index=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True)
    consumed_at = models.DateTimeField(null=True, blank=True)
    context_fingerprint = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        indexes = [
            models.Index(fields=["status", "expires_at"]),
            models.Index(fields=["operation", "destination_normalized", "status"]),
        ]


class SendDestinationState(ProjectControlModel):
    """Per-destination cooldown mutex used to serialize quota reservations."""

    destination_kind = models.CharField(max_length=8, db_index=True)
    destination_normalized = models.CharField(max_length=254)
    last_reserved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["destination_kind", "destination_normalized"],
                name="authn_send_destination_state_unique",
            ),
        ]


class SendQuotaWindow(ProjectControlModel):
    """Authoritative reserved-send counters for destination-hourly and SMS daily caps."""

    class Kind(models.TextChoices):
        DESTINATION_HOURLY = "destination_hourly", "Destination hourly"
        SMS_DAILY = "sms_daily", "SMS daily"

    kind = models.CharField(max_length=32, choices=Kind.choices)
    scope_key = models.CharField(max_length=254)
    window_started_at = models.DateTimeField()
    reserved_count = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["kind", "scope_key", "window_started_at"],
                name="authn_send_quota_window_unique",
            ),
        ]
        indexes = [
            models.Index(fields=["kind", "scope_key", "window_started_at"]),
        ]


class SendVerificationRequest(ProjectControlModel):
    """Idempotent protected-send request. Provider acceptance is not delivery."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SENDING = "sending", "Sending"
        PROVIDER_ACCEPTED = "provider_accepted", "Provider accepted"
        DEFINITELY_FAILED = "definitely_failed", "Definitely failed"
        UNKNOWN = "unknown", "Unknown"

    class Channel(models.TextChoices):
        EMAIL = "email", "Email"
        SMS = "sms", "SMS"

    request_id = models.UUIDField(unique=True)
    challenge = models.OneToOneField(
        SendVerificationChallenge,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="send_request",
    )
    operation = models.CharField(max_length=64, db_index=True)
    channel = models.CharField(max_length=8, choices=Channel.choices)
    destination_kind = models.CharField(max_length=8)
    destination_normalized = models.CharField(max_length=254, db_index=True)
    principal_type = models.CharField(max_length=16)
    principal_key = models.CharField(max_length=64, blank=True, default="")
    request_fingerprint = models.CharField(max_length=64)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.PENDING, db_index=True)
    quota_reserved = models.BooleanField(default=False)
    reserved_at = models.DateTimeField(null=True, blank=True)
    result_payload = models.JSONField(default=dict, blank=True)
    http_status = models.PositiveIntegerField(default=202)
    client_error_code = models.CharField(max_length=64, blank=True, default="")
    otp_challenge_id = models.CharField(max_length=64, blank=True, default="")
    provider_message_id = models.CharField(max_length=128, blank=True, default="")
    idempotency_expires_at = models.DateTimeField(db_index=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["destination_kind", "destination_normalized", "quota_reserved", "reserved_at"],
                name="authn_send_req_dest_quota_idx",
            ),
            models.Index(fields=["channel", "quota_reserved", "reserved_at"]),
            models.Index(fields=["status", "idempotency_expires_at"]),
        ]

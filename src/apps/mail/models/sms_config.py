"""SMS settings (Mail → SMS Settings) and the state of the AWS opt-out list sync.

``SmsConfig`` is one row (``SmsConfig.load()``): the opt-out footer, quiet hours, the cost estimate, links in SMS,
ticket texts, the AWS opt-out list sync and where the short ``/register`` link leads. Its defaults are the
conservative ones: footer on, quiet hours 20:00–09:00 Pacific, links (and with them ticket texts) off until the
sending number's registration is confirmed to allow embedded links.

``SmsOptOutSyncState`` is written only by the sync (``services.sms.opt_out_sync``), with UPDATEs, never by a form,
so saving the settings can never overwrite what a running sync records.
"""

import uuid
from datetime import time
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from apps.core.models import ProjectControlModel

SETTINGS_PK = uuid.UUID("00000000-0000-4000-8000-000000005301")
SYNC_STATE_PK = uuid.UUID("00000000-0000-4000-8000-000000005302")

DEFAULT_FOOTER = "Reply STOP to opt out."
DEFAULT_TICKET_TEMPLATE = "Innovate to Grow: you're registered for {{event_name}}. Your ticket: {{ticket_link}}"
DEFAULT_REGISTER_PATH = "/login"
REGISTER_PATH = "/register"


class SmsConfig(ProjectControlModel):
    footer_enabled = models.BooleanField(
        default=True,
        verbose_name="Add the opt-out footer",
        help_text="Append the footer to each Broadcast SMS and ticket text that does not already say STOP.",
    )
    footer_text = models.CharField(
        max_length=80,
        default=DEFAULT_FOOTER,
        verbose_name="Opt-out footer",
        help_text="Must say STOP. Plain characters only (no emoji or curly quotes), or every text costs double.",
    )

    quiet_hours_enabled = models.BooleanField(
        default=True,
        verbose_name="Quiet hours",
        help_text="No Broadcast SMS or ticket text is sent inside the window: queued texts wait until it ends. "
        "Sign-in and verification codes, which a person asks for, are not held.",
    )
    quiet_hours_start = models.TimeField(default=time(20, 0), verbose_name="Quiet from")
    quiet_hours_end = models.TimeField(default=time(9, 0), verbose_name="Quiet until")
    quiet_hours_timezone = models.CharField(
        max_length=64,
        default="America/Los_Angeles",
        verbose_name="Quiet hours time zone",
        help_text="An IANA time zone name, for example America/Los_Angeles.",
    )

    cost_per_segment = models.DecimalField(
        max_digits=7,
        decimal_places=4,
        default=Decimal("0.0100"),
        validators=[MinValueValidator(Decimal("0"))],
        verbose_name="Estimated cost per segment (USD)",
        help_text="Only for the composer's estimate. AWS bills each message part (segment) at its base price plus "
        "carrier fees: check the AWS End User Messaging SMS pricing page for the United States and set it here.",
    )

    links_enabled = models.BooleanField(
        default=False,
        verbose_name="Allow links in SMS",
        help_text="Turns on {{login_link}}, {{ticket_link}} and {{event_link}} (short /l/… links) and ticket texts. "
        "Leave off until the sending number's 10DLC or toll-free registration is confirmed to declare embedded "
        "links with sample messages on this site's domain: carriers filter or suspend numbers whose texts don't "
        "match their registration.",
    )
    personal_links_enabled = models.BooleanField(
        default=False,
        verbose_name="Personal sign-in links",
        help_text="On: {{login_link}} and {{ticket_link}} sign a member in with one tap (single use, never for "
        "staff, only when the text goes to the member's own verified phone). Off: they open the sign-in page and "
        "land on the same page after a code sign-in. A recycled phone number could receive someone else's personal "
        "link. Only the I2G Master can change this.",
    )

    ticket_sms_enabled = models.BooleanField(
        default=False,
        verbose_name="Text tickets to phone-only registrants",
        help_text="A registrant without an email address gets their ticket link by SMS. Needs links in SMS.",
    )
    ticket_sms_template = models.CharField(
        max_length=320,
        default=DEFAULT_TICKET_TEMPLATE,
        verbose_name="Ticket text",
        help_text="Supports {{first_name}}, {{event_name}} and {{ticket_link}} (required).",
    )
    ticket_link_validity_days = models.PositiveSmallIntegerField(
        default=7,
        validators=[MinValueValidator(1)],
        verbose_name="Ticket link validity (days)",
    )

    opt_out_sync_enabled = models.BooleanField(
        default=True,
        verbose_name="Sync AWS opt-outs",
        help_text="Read the sending number's opted-out list from AWS every hour (read only). A number that replied "
        "STOP is never texted again and its member's phone is unsubscribed; replying START later does not "
        "subscribe it again.",
    )
    opt_out_list_name = models.CharField(
        max_length=128,
        blank=True,
        default="",
        verbose_name="AWS opt-out list",
        help_text="Leave blank to use the sending number's own list (AWS's Default unless changed).",
    )

    register_redirect_path = models.CharField(
        max_length=200,
        default=DEFAULT_REGISTER_PATH,
        verbose_name="/register leads to",
        help_text="Where the short /register link (and its QR code) sends people. The sign-in page takes an email "
        "address or a phone number and creates the account.",
    )

    class Meta:
        verbose_name = "SMS settings"
        verbose_name_plural = "SMS settings"

    def __str__(self):
        return "SMS settings"

    def save(self, *args, **kwargs):
        # One row: a new instance saved while it exists replaces its values (keeping when it was created).
        self.pk = SETTINGS_PK
        if self._state.adding:
            created_at = type(self).objects.filter(pk=SETTINGS_PK).values_list("created_at", flat=True).first()
            if created_at is not None:
                self._state.adding = False
                self.created_at = created_at
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> "SmsConfig":
        obj, _created = cls.objects.get_or_create(pk=SETTINGS_PK)
        return obj

    @property
    def zone(self) -> ZoneInfo:
        return ZoneInfo(self.quiet_hours_timezone)

    def clean(self):
        super().clean()
        errors = {}
        try:
            ZoneInfo(self.quiet_hours_timezone or "")
        except (ZoneInfoNotFoundError, ValueError):
            errors["quiet_hours_timezone"] = "Enter a time zone name such as America/Los_Angeles."
        if self.quiet_hours_start == self.quiet_hours_end:
            errors["quiet_hours_end"] = "Quiet hours must end at a different time than they start."
        if self.footer_enabled and "stop" not in (self.footer_text or "").lower():
            errors["footer_text"] = "The footer must tell people to reply STOP."
        if "{{ticket_link}}" not in (self.ticket_sms_template or ""):
            errors["ticket_sms_template"] = "The ticket text must contain {{ticket_link}}."
        if self.ticket_sms_enabled and not self.links_enabled:
            errors["ticket_sms_enabled"] = "Ticket texts carry a link: allow links in SMS first."
        maximum = settings.SMS_POLICY["link_max_validity_days"]
        if not 1 <= (self.ticket_link_validity_days or 0) <= maximum:
            errors["ticket_link_validity_days"] = f"Choose 1 to {maximum} days."
        errors.update(register_path_errors(self.register_redirect_path))
        if errors:
            raise ValidationError(errors)


def register_path_errors(path: str) -> dict:
    from apps.mail.redirects import is_strict_internal_path

    value = (path or "").strip()
    if not is_strict_internal_path(value):
        return {"register_redirect_path": "Choose a page on this site (a path starting with /)."}
    if value.split("?", 1)[0].rstrip("/") == REGISTER_PATH:
        return {"register_redirect_path": "/register cannot lead to itself."}
    return {}


class SmsOptOutSyncState(ProjectControlModel):
    class Status(models.TextChoices):
        NEVER = "", "Not run yet"
        OK = "ok", "Up to date"
        PARTIAL = "partial", "Partly read (list longer than one run reads)"
        FAILED = "failed", "Failed"
        NOT_CONFIGURED = "not_configured", "SMS is not configured"
        DISABLED = "disabled", "Turned off"

    status = models.CharField(max_length=16, choices=Status.choices, blank=True, default="")
    message = models.CharField(max_length=300, blank=True, default="")
    list_name = models.CharField(max_length=128, blank=True, default="")
    last_run_at = models.DateTimeField(null=True, blank=True)
    last_success_at = models.DateTimeField(null=True, blank=True)
    listed_count = models.PositiveIntegerField(default=0)
    added_count = models.PositiveIntegerField(default=0)
    cleared_count = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "SMS opt-out sync state"
        verbose_name_plural = "SMS opt-out sync state"

    def __str__(self):
        return f"SMS opt-out sync ({self.get_status_display()})"

    @classmethod
    def load(cls) -> "SmsOptOutSyncState":
        obj, _created = cls.objects.get_or_create(pk=SYNC_STATE_PK)
        return obj

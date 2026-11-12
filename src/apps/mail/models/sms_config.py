"""SMS settings (Mail → SMS Settings) and the state of the AWS opt-out list sync.

``SmsConfig`` is one row (``SmsConfig.load()``): the opt-out footer, quiet hours, the cost estimate, links in SMS,
ticket texts, the AWS opt-out list sync and where the short ``/register`` link leads. Its defaults are the
conservative ones: footer on, quiet hours 20:00–09:00 Pacific, links (and with them ticket texts) off until the
sending number's registration is confirmed to allow embedded links.

Turning personal sign-in links off (the switch, or links in SMS) revokes them for good. Every write to the row, a
save or a bulk ``update()``, locks it and ends in ``settle_personal_links`` in the same transaction: unless personal
sign-in links were on before and are still on, ``personal_links_epoch`` moves on and every outstanding personal link
is revoked, with a ``SmsLinkRevocation`` for the audit. A personal link carries the epoch it was issued in and signs
in only while that is still the epoch, so it can't come back: not when the switch is turned on again, not when its
own row is edited, and not when it was being issued while the switch went off.

``SmsOptOutSyncState`` is written only by the sync (``services.sms.opt_out_sync``), with UPDATEs, never by a form,
so saving the settings can never overwrite what a running sync records.
"""

import logging
import uuid
from datetime import time
from decimal import Decimal
from typing import NamedTuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import DEFAULT_DB_ALIAS, models, router, transaction
from django.db.models import Max
from django.utils import timezone

from apps.core.models import ProjectControlModel
from apps.core.models.managers import ProjectControlQuerySet

from .sms_link import SmsLinkRevocation, SmsLinkToken

logger = logging.getLogger(__name__)

SETTINGS_PK = uuid.UUID("00000000-0000-4000-8000-000000005301")
SYNC_STATE_PK = uuid.UUID("00000000-0000-4000-8000-000000005302")

DEFAULT_FOOTER = "Reply STOP to opt out."
DEFAULT_TICKET_TEMPLATE = "Innovate to Grow: you're registered for {{event_name}}. Your ticket: {{ticket_link}}"
DEFAULT_REGISTER_PATH = "/login"
REGISTER_PATH = "/register"
STATE_FIELDS = ("links_enabled", "personal_links_enabled", "personal_links_epoch")
Via = SmsLinkRevocation.Via


class PersonalLinkState(NamedTuple):
    """SMS Settings as personal sign-in links see them: both switches, and the epoch a link must carry."""

    links_enabled: bool
    personal_links_enabled: bool
    epoch: int

    @property
    def on(self) -> bool:
        return bool(self.links_enabled and self.personal_links_enabled)


class SmsConfigQuerySet(ProjectControlQuerySet):
    def update(self, **kwargs):
        """A bulk update (a shell or a script) settles personal sign-in links as a save does."""
        using = self._db or router.db_for_write(self.model)
        with transaction.atomic(using=using):
            before = locked_state(using)
            rows = super().update(**kwargs)
            settle_personal_links(before, via=Via.BULK_UPDATE, using=using)
        return rows


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
        "match their registration. Turning it off also revokes every personal sign-in link already texted, for good.",
    )
    personal_links_enabled = models.BooleanField(
        default=False,
        verbose_name="Personal sign-in links",
        help_text="On: {{login_link}} and {{ticket_link}} sign a member in with one tap (single use, never for "
        "staff, only when the text goes to the member's own verified phone). Off: they open the sign-in page and "
        "land on the same page after a code sign-in. Turning this off revokes every personal link already texted, "
        "for good: turning it back on does not bring them back. A recycled phone number could receive someone "
        "else's personal link. Only the I2G Master can change this.",
    )
    personal_links_epoch = models.PositiveIntegerField(
        default=1,
        editable=False,
        verbose_name="Personal sign-in link epoch",
        help_text="Moves on whenever personal sign-in links are turned off: a personal link issued in an earlier "
        "epoch never signs anyone in. Only saving these settings changes it.",
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

    objects = SmsConfigQuerySet.as_manager()
    # The SmsLinkRevocation the last save() recorded, if it revoked personal sign-in links.
    revocation = None

    class Meta:
        verbose_name = "SMS settings"
        verbose_name_plural = "SMS settings"

    def __str__(self):
        return "SMS settings"

    def save(self, *args, actor=None, via=Via.SAVE, **kwargs):
        """Save the one row and settle personal sign-in links in the same transaction (``settle_personal_links``);
        ``actor`` and ``via`` say who and how for the audit of a revocation (then ``self.revocation``)."""
        self.pk = SETTINGS_PK
        using = kwargs.get("using") or router.db_for_write(type(self), instance=self)
        with transaction.atomic(using=using):
            before = locked_state(using)
            if self._state.adding and before is not None:
                # One row: a new instance saved while it exists replaces its values (keeping when it was created).
                self._state.adding = False
                rows = type(self)._base_manager.db_manager(using).filter(pk=SETTINGS_PK)
                self.created_at = rows.values_list("created_at", flat=True).get()
            if before is not None:
                # The epoch only ever moves on: a stale instance must not write an older one back.
                self.personal_links_epoch = before.epoch
            super().save(*args, **kwargs)
            self.personal_links_epoch, self.revocation = settle_personal_links(
                before, actor=actor, via=via, using=using
            )

    @classmethod
    def load(cls) -> "SmsConfig":
        obj, _created = cls.objects.get_or_create(pk=SETTINGS_PK)
        return obj

    @property
    def personal_link_state(self) -> PersonalLinkState:
        return PersonalLinkState(self.links_enabled, self.personal_links_enabled, self.personal_links_epoch)

    @property
    def personal_sign_in_on(self) -> bool:
        """Personal sign-in links may sign members in: links in SMS and personal sign-in links both on."""
        return self.personal_link_state.on

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


class Settled(NamedTuple):
    epoch: int
    revocation: SmsLinkRevocation | None = None


def locked_state(using=DEFAULT_DB_ALIAS) -> PersonalLinkState | None:
    """The switches and the epoch, locking the row until the caller's transaction ends (None while there is no row)."""
    rows = SmsConfig._base_manager.db_manager(using).select_for_update().filter(pk=SETTINGS_PK)
    row = rows.values_list(*STATE_FIELDS).first()
    return PersonalLinkState(*row) if row else None


def revoke_personal_links(*, actor=None, via, using=DEFAULT_DB_ALIAS) -> Settled:
    """Settle personal sign-in links as they stand, without a write: what to do on finding links still live while
    they are off (turned off outside the app, by raw SQL)."""
    with transaction.atomic(using=using):
        return settle_personal_links(locked_state(using), actor=actor, via=via, using=using)


def settle_personal_links(before: PersonalLinkState | None, *, actor=None, via, using=DEFAULT_DB_ALIAS) -> Settled:
    """Run in the transaction of a write to SMS Settings, after it, with the row still locked; ``before`` is how the
    row stood before the write. Unless personal sign-in links were on before and are still on, the epoch moves on,
    so no personal link issued earlier ever signs in again, and every outstanding one is revoked. The revocation is
    recorded when the write turned them off, or when it found links still live while they were off."""
    after = locked_state(using)
    if after is None:  # No row (a bulk update that matched none, the row deleted): nothing to settle.
        return Settled(before.epoch if before is not None else 0)
    if before is not None and before.on and after.on:
        if after.epoch < before.epoch:  # A bulk update must not move the epoch back either.
            _set_epoch(before.epoch, using)
        return Settled(max(before.epoch, after.epoch))
    floor = before.epoch if before is not None else _highest_issued_epoch(using)
    epoch = max(floor, after.epoch) + 1
    _set_epoch(epoch, using)
    revoked = _revoke_outstanding(before, using)
    reason = _revocation_reason(before, after, revoked)
    if reason is None:
        return Settled(epoch)
    revocation = SmsLinkRevocation.objects.using(using).create(
        reason=reason, via=via, actor=actor, actor_label=_who(actor), revoked_count=revoked, epoch=epoch
    )
    # Links found live while off mean the switch was changed outside the app: worth a warning.
    log = logger.warning if reason == SmsLinkRevocation.Reason.FOUND_OFF else logger.info
    log("Revoked %d personal SMS sign-in link(s): %s (%s); epoch now %d.", revoked, reason, via, epoch)
    return Settled(epoch, revocation)


def _revoke_outstanding(before: PersonalLinkState | None, using) -> int:
    """Revoke every outstanding personal link; the number that still worked until now (issued in the epoch that was
    current). One from an earlier epoch (stored while a switch-off committed) never worked: tidied, not counted."""
    now = timezone.now()
    values = {"revoked_at": now, "expires_at": now, "updated_at": now}
    outstanding = SmsLinkToken.objects.using(using).outstanding_personal()
    if before is None:  # No row to say which epoch was current: count them all.
        return outstanding.update(**values)
    revoked = outstanding.filter(epoch=before.epoch).update(**values)
    outstanding.update(**values)
    return revoked


def _revocation_reason(before: PersonalLinkState | None, after: PersonalLinkState, revoked: int) -> str | None:
    if before is not None and before.on:
        if not after.personal_links_enabled:
            return SmsLinkRevocation.Reason.PERSONAL_LINKS_OFF
        return SmsLinkRevocation.Reason.LINKS_OFF
    # They were already off, yet links were still live: they were turned off without going through a write here.
    return SmsLinkRevocation.Reason.FOUND_OFF if revoked else None


def _set_epoch(epoch: int, using) -> None:
    SmsConfig._base_manager.db_manager(using).filter(pk=SETTINGS_PK).update(personal_links_epoch=epoch)


def _highest_issued_epoch(using) -> int:
    # The row is new (or was deleted): start past every link ever issued, so none can match it again.
    return SmsLinkToken.objects.using(using).aggregate(top=Max("epoch"))["top"] or 0


def _who(actor) -> str:
    if actor is None:
        return ""
    name, email = actor.get_full_name(), actor.get_primary_email()
    return (f"{name} <{email}>" if name and email else name or email or str(actor.pk))[:255]


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

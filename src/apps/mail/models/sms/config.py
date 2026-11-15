"""SMS settings (Mail → SMS Settings).

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

The settlement itself is ``personal_links``; the validation is ``config_rules``.
"""

from datetime import time
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models, router, transaction

from apps.core.models import ProjectControlModel, ProjectControlQuerySet

from .config_rules import DEFAULT_REGISTER_PATH, SmsConfigRulesMixin
from .links import SmsLinkRevocation
from .personal_links import SETTINGS_PK, locked_state, settle_personal_links

DEFAULT_FOOTER = "Reply STOP to opt out."
DEFAULT_TICKET_TEMPLATE = "Innovate to Grow: you're registered for {{event_name}}. Your ticket: {{ticket_link}}"
Via = SmsLinkRevocation.Via


class SmsConfigQuerySet(ProjectControlQuerySet):
    def update(self, **kwargs):
        """A bulk update (a shell or a script) settles personal sign-in links as a save does."""
        using = self._db or router.db_for_write(self.model)
        with transaction.atomic(using=using):
            before = locked_state(using)
            rows = super().update(**kwargs)
            settle_personal_links(before, via=Via.BULK_UPDATE, using=using)
        return rows


class SmsConfig(SmsConfigRulesMixin, ProjectControlModel):
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

"""The helpdesk's admin-editable settings (one row; ``load()`` returns the defaults while none is saved).

Every limit and retention period is a field with a documented default (docs/integrations/messaging/helpdesk.md), so staff
with the Helpdesk grant can tune them without a deploy. ``shadow_mode`` is on by default: nothing is sent (no replies,
acknowledgements or notifications) until an I2G Master switches it off here; the mailbox is only ever read.
"""

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.models import ProjectControlModel

MB = 1024 * 1024
DEFAULT_BLOCKED_EXTENSIONS = (
    "exe com scr bat cmd ps1 vbs vbe js jse wsf wsh msi msp hta cpl jar lnk reg "
    "iso img vhd vhdx html htm svg xhtml shtml docm xlsm pptm dotm xltm one chm"
)
DEFAULT_WARN_EXTENSIONS = "zip 7z rar gz tgz tar bz2 xz cab arj"
_SINGLETON = "helpdesk"
# Only {ticket}: the requester's name and subject are the sender's own words, and an acknowledgement goes to an
# address nobody verified (services.outbound.acknowledgement). The email's footer says how to reply.
DEFAULT_ACKNOWLEDGEMENT = (
    "Hello,\n\n"
    "Thank you for contacting Innovate to Grow. We have received your message and opened ticket {ticket}. "
    "A member of our team will get back to you soon.\n\n"
    "Innovate to Grow, UC Merced"
)


def _bounded(low: int, high: int) -> list:
    return [MinValueValidator(low), MaxValueValidator(high)]


class HelpdeskSettings(ProjectControlModel):
    singleton = models.CharField(max_length=16, unique=True, default=_SINGLETON, editable=False)
    enabled = models.BooleanField(
        default=True,
        help_text="Read the Inbox and turn its mail into tickets. Off: the helpdesk neither reads nor imports; "
        "switched back on, it continues from where its intake stopped, so mail that arrived meanwhile (and is still "
        "in the Inbox) becomes tickets then.",
    )
    shadow_mode = models.BooleanField(
        default=True,
        help_text="On: nothing is ever sent (no replies, acknowledgements or notifications); staff answer from Outlook. "
        "Off: staff can reply to the requester from the ticket page, and the acknowledgement and notifications "
        "below are sent when they are switched on. The mailbox is only ever read either way.",
    )
    send_acknowledgement = models.BooleanField(
        default=False,
        db_default=False,
        help_text="Email the requester when their message opens a new ticket: only when its sender passed DMARC, never "
        "for automated mail, spam, backfilled mail, or a message that asks for no automatic reply; at most one per "
        "address a day and 200 a day in all. Needs shadow mode off. Only an I2G Master can change it.",
    )
    acknowledgement_text = models.TextField(
        default=DEFAULT_ACKNOWLEDGEMENT,
        db_default=DEFAULT_ACKNOWLEDGEMENT,
        help_text="The acknowledgement's text. {ticket} is replaced ({requester_name} and {subject} too, with any link "
        "removed). Only an I2G Master can change it.",
    )
    notify_assignment = models.BooleanField(
        default=True,
        db_default=True,
        help_text="Email staff when a ticket is assigned to them (or to their group, with nobody in it) by someone "
        "else. Needs shadow mode off.",
    )
    auto_close_resolved_days = models.PositiveSmallIntegerField(
        default=7,
        db_default=7,
        validators=_bounded(0, 365),
        help_text="Resolved tickets close by themselves after this many days without a reply (0: never). A reply "
        "before then reopens the ticket.",
    )
    sla_warning_percent = models.PositiveSmallIntegerField(
        default=75,
        db_default=75,
        validators=_bounded(1, 99),
        help_text="A running SLA is shown as at risk once this share of its time is used.",
    )
    pause_while_campaign_sending = models.BooleanField(
        default=True,
        help_text="Wait while a campaign is sending: reads and sends share Outlook's per-mailbox limits.",
    )
    ingest_batch_size = models.PositiveSmallIntegerField(
        default=100, validators=_bounded(1, 500), help_text="Messages imported per run of the ingest job."
    )
    ingest_max_seconds = models.PositiveSmallIntegerField(
        default=60,
        validators=_bounded(5, 600),
        help_text="Seconds one ingest run may take (it shares the background worker with every queued email).",
    )
    max_attempts = models.PositiveSmallIntegerField(
        default=5,
        validators=_bounded(1, 20),
        help_text="Attempts per message before it is listed under Ingest problems (with a Retry button).",
    )
    message_max_bytes = models.PositiveIntegerField(
        default=25 * MB,
        validators=_bounded(64 * 1024, 25 * MB),
        help_text="Most of one message's raw MIME read (Microsoft Graph's own limit is 25 MB). A longer message keeps "
        "what was read; its attachments are listed but not stored.",
    )
    attachment_max_bytes = models.PositiveIntegerField(
        default=10 * MB, validators=_bounded(0, 25 * MB), help_text="Larger attachments are listed but not stored."
    )
    body_text_max_chars = models.PositiveIntegerField(
        default=256 * 1024, validators=_bounded(1000, 4 * MB), help_text="Longer text is cut (open it in Outlook)."
    )
    body_html_max_chars = models.PositiveIntegerField(
        default=1 * MB, validators=_bounded(1000, 4 * MB), help_text="Longer sanitized HTML is cut."
    )
    blocked_extensions = models.TextField(
        default=DEFAULT_BLOCKED_EXTENSIONS,
        help_text="File types whose content is never stored (only name, size and type), separated by spaces.",
    )
    warn_extensions = models.TextField(
        default=DEFAULT_WARN_EXTENSIONS,
        blank=True,
        help_text="File types stored but downloaded only after a warning (archives cannot be inspected).",
    )
    reopen_window_days = models.PositiveSmallIntegerField(
        default=14,
        validators=_bounded(0, 365),
        help_text="A reply to a ticket closed less than this many days ago reopens it; a later one opens a "
        "follow-up ticket. Automated mail never reopens a ticket.",
    )
    flood_threshold = models.PositiveSmallIntegerField(
        default=10,
        validators=_bounded(1, 1000),
        help_text="More new tickets than this from one sender within the flood window are grouped into one.",
    )
    flood_window_minutes = models.PositiveSmallIntegerField(default=60, validators=_bounded(1, 1440))
    spam_scl_threshold = models.PositiveSmallIntegerField(
        default=5,
        validators=_bounded(1, 9),
        help_text="Exchange's spam confidence level (SCL) from which a message counts as spam.",
    )
    bulk_bcl_threshold = models.PositiveSmallIntegerField(
        default=7,
        db_default=7,
        validators=_bounded(1, 9),
        help_text="Exchange's bulk complaint level (BCL) from which a message counts as list or bulk mail (Exchange "
        "Online's own default bulk threshold is 7). A reply to an email the site sent is never bulk on this alone.",
    )
    reply_match_window_days = models.PositiveSmallIntegerField(
        default=30,
        db_default=30,
        validators=_bounded(1, 180),
        help_text="A reply to an email the site sent without a Message-ID it knows (one carrying a sign-in link) is "
        "recognised by its sender and subject when that email went out at most this many days before.",
    )
    automated_retention_days = models.PositiveSmallIntegerField(
        default=90, validators=_bounded(1, 3650), help_text="Days the bodies of automated mail are kept."
    )
    spam_retention_days = models.PositiveSmallIntegerField(
        default=30, validators=_bounded(1, 3650), help_text="Days the bodies of spam are kept."
    )
    closed_body_retention_days = models.PositiveSmallIntegerField(
        default=730, validators=_bounded(1, 3650), help_text="Days message bodies are kept after a ticket closed."
    )
    attachment_retention_days = models.PositiveSmallIntegerField(
        default=365, validators=_bounded(1, 3650), help_text="Days attachments are kept after a ticket closed."
    )
    ticket_retention_days = models.PositiveSmallIntegerField(
        default=1095,
        validators=_bounded(30, 3650),
        help_text="Days a closed ticket (number, subject, requester, dates) is kept before it is deleted.",
    )
    backfill_age_hours = models.PositiveSmallIntegerField(
        default=24,
        validators=_bounded(1, 8760),
        help_text="Mail imported more than this many hours after it arrived (the first intake scan's lookback, or "
        "a Rescan since on the intake card) opens tickets marked as backfilled.",
    )

    class Meta:
        verbose_name = "Helpdesk Settings"
        verbose_name_plural = "Helpdesk Settings"

    def __str__(self):
        return "Helpdesk Settings"

    @classmethod
    def load(cls) -> "HelpdeskSettings":
        """The saved settings, or an unsaved row of defaults (shadow mode on) while none is saved."""
        return cls.objects.filter(singleton=_SINGLETON).first() or cls()

    @staticmethod
    def extensions(value: str) -> frozenset[str]:
        return frozenset(item.strip(" .").lower() for item in str(value or "").replace(",", " ").split() if item)

    @property
    def blocked_extension_set(self) -> frozenset[str]:
        return self.extensions(self.blocked_extensions)

    @property
    def warn_extension_set(self) -> frozenset[str]:
        return self.extensions(self.warn_extensions)

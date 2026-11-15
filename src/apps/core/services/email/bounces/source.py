"""Where bounce reports come from: the Graph sending mailbox a scan may read, and which of its messages look like
reports worth opening."""

from datetime import UTC, datetime

from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.core.models import EmailServiceConfig, MicrosoftGraphProviderConfig

from ..exceptions import EmailDeliveryError
from ..graph.access import READ
from ..graph.mailbox import GraphMailboxReader
from ..telemetry import text


def monitoring() -> dict:
    return settings.EMAIL_MONITORING


def active_reader() -> tuple[GraphMailboxReader | None, str, str]:
    """``(reader, mailbox, "")`` for the Graph sending mailbox, or ``(None, mailbox or "", why it cannot be read)``."""
    graph = MicrosoftGraphProviderConfig.load()
    if not graph.is_configured:
        return None, "", "Microsoft Graph is not configured (no active configuration with a usable certificate)."
    mailbox = graph.sender_mailbox(EmailServiceConfig.load().from_email)
    if mailbox not in monitoring()["bounce_mailboxes"]:
        return None, mailbox, f"{mailbox} is not in the bounce-processing mailbox allow-list (EMAIL_BOUNCE_MAILBOXES)."
    if not graph.allows(mailbox, READ):
        return None, mailbox, f"The Microsoft Graph mailbox scope does not grant read permission on {mailbox}."
    try:
        return GraphMailboxReader(graph, mailbox), mailbox, ""
    except EmailDeliveryError as exc:
        return None, mailbox, str(exc)


def is_candidate(message: dict) -> bool:
    """Whether a listed message looks like a bounce report (by subject prefix or sender), so is worth opening."""
    config = monitoring()
    subject = str(message.get("subject") or "").strip().casefold()
    sender = text.address(((message.get("from") or {}).get("emailAddress") or {}).get("address"))
    local = sender.partition("@")[0]
    return (
        subject.startswith(tuple(config["ndr_subject_prefixes"]))
        or local in config["ndr_sender_local_parts"]
        or local.startswith("microsoftexchange")
    )


def received_at(message: dict) -> datetime | None:
    parsed = parse_datetime(str(message.get("receivedDateTime") or ""))
    if parsed is None:
        return None
    return parsed if timezone.is_aware(parsed) else parsed.replace(tzinfo=UTC)

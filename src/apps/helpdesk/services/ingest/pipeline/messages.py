"""Adding a message to a ticket (its participants, attachments and references), and joining or moving tickets."""

from django.utils import timezone

from apps.core.services.email.inbound import scrub_links, scrub_subject

from ....models import Ticket, TicketAttachment, TicketEvent, TicketMessage
from ... import sla
from ...tickets import events
from ...tickets.changes import reopen_values
from ..reading import attachments
from ..reading.message import ParsedMessage
from ..reading.sanitize import sanitize_html
from ..routing import people
from ..routing.classify import Classified

Status = Ticket.Status
OWN_MAIL_NOTE = "Sent from the site's own address: its content is not stored (it may hold sign-in codes)."
MAX_PARTICIPANTS = 50
MAX_REFERENCES = 20
SCAM_REASON = TicketMessage.SCAM_REASON  # a scam check's reason, kept among the message's signals


def _participants(addresses, own) -> list[str]:
    return [address for address in dict.fromkeys(addresses) if address and address not in own][:MAX_PARTICIPANTS]


def _attached(parsed: ParsedMessage, *, keep_text: bool) -> list[dict]:
    left_out = [{"omitted": parsed.attached_dropped}] if parsed.attached_dropped else []
    return [
        {
            "from": scrub_subject(item["from"]),
            "date": item["date"],
            "subject": scrub_subject(item["subject"]),
            "text": scrub_links(item["text"]) if keep_text else "",
        }
        for item in parsed.attached_messages
    ] + left_out


def _add_message(ticket, row, parsed, classified, settings, fingerprint, own=frozenset()) -> TicketMessage:
    verdict = classified.verdict
    own_mail = verdict.classification == "own"
    html, html_cut = (
        ("", False) if own_mail else sanitize_html(parsed.html, max_chars=int(settings.body_html_max_chars))
    )
    body_text = OWN_MAIL_NOTE if own_mail else scrub_links(parsed.text)
    text_cut = len(body_text) > int(settings.body_text_max_chars)
    speaker = people.speaks_for(parsed, own)
    message = TicketMessage.objects.create(
        ticket=ticket,
        kind=TicketMessage.Kind.AUTOMATED if classified.automated else TicketMessage.Kind.CUSTOMER,
        inbound=row,
        internet_message_id=(parsed.message_id or row.internet_message_id)[:255],
        in_reply_to=parsed.in_reply_to[:255],
        references=parsed.references[-MAX_REFERENCES:],
        conversation_id=row.conversation_id[:255],
        fingerprint=fingerprint,
        from_address=parsed.from_address[:254],
        from_name=scrub_subject(parsed.from_name),
        to_addresses=parsed.to[:MAX_PARTICIPANTS],
        cc_addresses=parsed.cc[:MAX_PARTICIPANTS],
        reply_to=parsed.reply_to[:254],
        on_behalf_of=speaker.address[:254],
        on_behalf_name=scrub_subject(speaker.name),
        list_address=speaker.list_address[:254],
        subject=scrub_subject(parsed.subject),
        occurred_at=row.received_at,
        sent_at=parsed.sent_at,
        body_text=body_text[: int(settings.body_text_max_chars)],
        body_html=html,
        body_truncated=parsed.truncated or parsed.incomplete or html_cut or text_cut,
        attached_messages=[] if own_mail else _attached(parsed, keep_text=not classified.automated),
        auth_summary=classified.auth,
        scam_level=classified.scam_level,
        classification=verdict.classification,
        subtype=verdict.subtype,
        signals=[
            *list(dict.fromkeys((*verdict.signals, *verdict.hints)))[:20],
            *(f"{SCAM_REASON}{reason}"[:200] for reason in classified.scam_reasons),
        ],
    )
    if not own_mail:
        values = attachments.prepare(parsed.attachments, settings, truncated=parsed.truncated)
        TicketAttachment.objects.bulk_create([TicketAttachment(message=message, **item) for item in values])
    return message


def _joined(ticket: Ticket, message: TicketMessage, classified: Classified, rule: str, own) -> None:
    if classified.automated:
        events.record(ticket, TicketEvent.Kind.AUTOMATED_MESSAGE, **{"from": message.from_address, "rule": rule})
        return
    seen = [message.from_address, message.reply_to, message.on_behalf_of, *message.to_addresses, *message.cc_addresses]
    updates = {
        "participants": _participants([*ticket.participants, *seen], {*own, message.list_address} - {""}),
        "unread": True,
        "last_activity_at": max(ticket.last_activity_at, message.occurred_at),
        "updated_at": timezone.now(),
    }
    events.record(ticket, TicketEvent.Kind.CUSTOMER_MESSAGE, **{"from": message.from_address, "rule": rule})
    if rule == "reopened":
        cleared = reopen_values(ticket, Status.OPEN)
        updates.update(status=Status.OPEN, closed_at=None, resolved_at=None, **cleared)
        events.record(ticket, TicketEvent.Kind.REOPENED, reason="the requester replied", **_move(ticket.status))
        if cleared and ticket.resolution_code:
            # Resolving it again asks for a new code.
            events.record(ticket, TicketEvent.Kind.RESOLUTION, cleared=ticket.resolution_code)
    elif ticket.status == Status.PENDING_CUSTOMER:
        updates["status"] = Status.OPEN
        events.record(ticket, TicketEvent.Kind.STATUS, reason="the requester replied", **_move(ticket.status))
    if updates.get("status") == Status.OPEN:
        # The requester answered: a resolution clock that stood still (waiting for them, or resolved) runs again.
        updates.update(sla.status_values(ticket, Status.OPEN, timezone.now()))
    if rule == "flood":
        updates["flags"] = list(dict.fromkeys([*ticket.flags, "flood"]))
        events.record(ticket, TicketEvent.Kind.FLOOD, **{"from": message.from_address})
    Ticket.objects.filter(pk=ticket.pk).update(**updates)


def _move(status: str) -> dict:
    return {"from": status, "to": Status.OPEN}

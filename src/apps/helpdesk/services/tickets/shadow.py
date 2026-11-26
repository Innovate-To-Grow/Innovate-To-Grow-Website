"""Shadow mode: the helpdesk reads the mailbox and writes tickets, and sends nothing.

While ``HelpdeskSettings.shadow_mode`` is on (the default) there is no reply form, no acknowledgement and no
notification. Staff switch it off in Helpdesk → Settings to reply from the ticket page and, when those switches are
on, to send acknowledgements and assignment notifications (``services.outbound``). The mailbox never changes either
way (nothing is marked read, moved, flagged or forwarded; the Graph transport refuses such requests anyway).
``sending_allowed`` is the one switch all sending code checks first, when it queues and again when the job runs.
``automatic_reply_allowed`` is the one any automatic answer (an acknowledgement, a notification) must check: it is
also False for automated mail, so an automatic reply is never answered with another (a mail loop), for a message on a
ticket that is automated mail or spam, and for a person's message the classifier marked ``no_auto_response`` (RFC
3834: it came through a list or a bulk sender, or asked for no automatic reply; or its text looks automated, or it
claims the site's own address without proof, so a responder that marks nothing is never answered either).
"""

from apps.core.services.email.inbound import NO_AUTO_RESPONSE

from ...models import HelpdeskSettings, Ticket, TicketMessage

# The release that added replies and notifications (``services.outbound``); a code-level kill switch beside the setting.
SENDING_IMPLEMENTED = True


def shadow_mode_on(settings: HelpdeskSettings | None = None) -> bool:
    settings = settings or HelpdeskSettings.load()
    return bool(settings.shadow_mode) or not SENDING_IMPLEMENTED


def sending_allowed(settings: HelpdeskSettings | None = None) -> bool:
    return not shadow_mode_on(settings)


def automatic_reply_allowed(message: TicketMessage, settings: HelpdeskSettings | None = None) -> bool:
    """Whether ``message`` may ever be answered automatically (see the module docstring)."""
    if not sending_allowed(settings):
        return False
    if message.kind != TicketMessage.Kind.CUSTOMER or NO_AUTO_RESPONSE in (message.signals or []):
        return False
    ticket = message.ticket
    return not (ticket.automated or ticket.status == Ticket.Status.SPAM)

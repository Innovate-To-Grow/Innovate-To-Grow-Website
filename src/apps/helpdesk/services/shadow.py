"""Shadow mode: the helpdesk reads the mailbox and writes tickets, and sends nothing.

This release has no sending code: no reply composer, no acknowledgement, no notification, and no change to the
mailbox (nothing is marked read, moved, flagged or forwarded; the Graph transport refuses such requests anyway).
``sending_allowed`` is the one switch any later sending code must check first; it stays False while
``HelpdeskSettings.shadow_mode`` is on (the default), and it is False in this release whatever the setting says.
``automatic_reply_allowed`` is the one any automatic answer (an acknowledgement, a notification) must check: it is
also False for automated mail, so an automatic reply is never answered with another (a mail loop), and for a person's
message the classifier marked ``no_auto_response`` (RFC 3834: it came through a list or a bulk sender, or asked for no
automatic reply).
"""

from apps.core.services.email.inbound import NO_AUTO_RESPONSE

from ..models import HelpdeskSettings, TicketMessage

# Flipped by the release that adds replies and notifications; until then nothing can send, whatever the settings say.
SENDING_IMPLEMENTED = False


def shadow_mode_on(settings: HelpdeskSettings | None = None) -> bool:
    settings = settings or HelpdeskSettings.load()
    return bool(settings.shadow_mode) or not SENDING_IMPLEMENTED


def sending_allowed(settings: HelpdeskSettings | None = None) -> bool:
    return not shadow_mode_on(settings)


def automatic_reply_allowed(message: TicketMessage, settings: HelpdeskSettings | None = None) -> bool:
    """Whether ``message`` may ever be answered automatically (see the module docstring)."""
    if not sending_allowed(settings):
        return False
    return message.kind == TicketMessage.Kind.CUSTOMER and NO_AUTO_RESPONSE not in (message.signals or [])

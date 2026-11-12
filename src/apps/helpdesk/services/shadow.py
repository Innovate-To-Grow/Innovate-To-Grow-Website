"""Shadow mode: the helpdesk reads the mailbox and writes tickets, and sends nothing.

This release has no sending code: no reply composer, no acknowledgement, no notification, and no change to the
mailbox (nothing is marked read, moved, flagged or forwarded; the Graph transport refuses such requests anyway).
``sending_allowed`` is the one switch any later sending code must check first; it stays False while
``HelpdeskSettings.shadow_mode`` is on (the default), and it is False in this release whatever the setting says.
"""

from ..models import HelpdeskSettings

# Flipped by the release that adds replies and notifications; until then nothing can send, whatever the settings say.
SENDING_IMPLEMENTED = False


def shadow_mode_on(settings: HelpdeskSettings | None = None) -> bool:
    settings = settings or HelpdeskSettings.load()
    return bool(settings.shadow_mode) or not SENDING_IMPLEMENTED


def sending_allowed(settings: HelpdeskSettings | None = None) -> bool:
    return not shadow_mode_on(settings)

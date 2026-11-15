"""Microsoft Graph (Outlook / Exchange Online): the provider configuration (``provider``, with its checks in
``provider_validation`` and its readiness in ``provider_status``), the mailboxes it may use (``mailboxes``), its certificates (``certificate``) and access checks (``access_check``).

Migration 0043 imports the sending-limit defaults from this package, so it re-exports them from ``limits``.
"""

from .access_check import MicrosoftGraphAccessCheck, go_live_problem, takeover_problem
from .certificate import MicrosoftGraphCertificate
from .limits import (
    SENDING_LIMIT_FIELDS,
    default_external_recipients_per_hour_limit,
    default_internal_recipients_per_hour_limit,
    default_max_recipients_per_message,
    default_messages_per_minute_limit,
    default_recipients_per_day_limit,
)
from .mailboxes import MicrosoftGraphMailboxScope, is_deny_mailbox, normalize_mailbox
from .provider import MicrosoftGraphProviderConfig
from .provider_validation import SENDING_APP_CHANGE, TAKEOVER_REFUSED

__all__ = [
    "SENDING_APP_CHANGE",
    "SENDING_LIMIT_FIELDS",
    "TAKEOVER_REFUSED",
    "MicrosoftGraphAccessCheck",
    "MicrosoftGraphCertificate",
    "MicrosoftGraphMailboxScope",
    "MicrosoftGraphProviderConfig",
    "default_external_recipients_per_hour_limit",
    "default_internal_recipients_per_hour_limit",
    "default_max_recipients_per_message",
    "default_messages_per_minute_limit",
    "default_recipients_per_day_limit",
    "go_live_problem",
    "is_deny_mailbox",
    "normalize_mailbox",
    "takeover_problem",
]

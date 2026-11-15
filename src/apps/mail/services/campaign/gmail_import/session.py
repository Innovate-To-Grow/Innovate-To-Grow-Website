"""One Gmail IMAP login session under the delivery-rate limiter, shared by the admin inbox and "Import from Gmail".

Each uncached read logs in once, so each session takes one slot on the ``gmail_imap`` channel for the account
(``<imap host>:<username>``; Gmail's limits are per account, which is the cooldown group). The session waits for its
slot up to the read wait, connects with the channel's timeout, and its outcome is recorded
(``delivery_rates.adapters.imap``). While Gmail asked to wait, or a breaker holds the account, no connection is
made at all: ``RateDeferred``, which the inbox and the import turn into their "busy" errors.
"""

from contextlib import contextmanager

from apps.core.models.base.delivery_rates import DeliveryChannel
from apps.core.services.delivery_rates import Reason, WaitMode, controlled, imap_identity, wait_cap
from apps.core.services.delivery_rates.adapters.imap import login_signal, session_signal
from apps.core.services.delivery_rates.rules.defaults import channel_settings


@contextmanager
def gmail_imap_session(mailbox_class, config, username: str, *, initial_folder):
    """Log in to ``config``'s IMAP host as ``username`` with an ``imap_tools`` ``mailbox_class``; yield the client.

    Raises ``RateDeferred`` (nothing was connected) when the account is held back for longer than the read wait.
    """
    identity = imap_identity(config.imap_host, username)
    timeout = channel_settings(DeliveryChannel.GMAIL_IMAP)["timeout_seconds"]
    with controlled(
        DeliveryChannel.GMAIL_IMAP, identity, classify=session_signal, max_wait=wait_cap(WaitMode.READ)
    ) as admission:
        mailbox = mailbox_class(config.imap_host, timeout=timeout)
        with mailbox.login(username, config.gmail_password, initial_folder=initial_folder) as client:
            # Gmail may accept the login while saying it throttles the account: slow down after this session.
            admission.signal = login_signal(getattr(client, "login_result", None))
            yield client


def busy_text(deferred) -> str:
    """What staff see while Gmail reads are held back (``deferred``: the limiter's ``RateDeferred``)."""
    seconds = max(1, deferred.retry_after)
    if deferred.reason == f"breaker:{Reason.AUTH}":
        return (
            "Gmail refused the sign-in of the Gmail import account; check its app password. Reading tries again in "
            f"about {seconds} seconds, or as soon as the account is saved."
        )
    return f"Gmail is busy; try again in about {seconds} seconds."

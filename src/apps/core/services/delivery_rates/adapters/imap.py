"""Gmail IMAP answers (``DELIVERY_RATES["signals"]["imap"]``), for the admin inbox and "Import from Gmail".

Google publishes no IMAP rate, so the channel only reacts: too many simultaneous connections pauses it, a bandwidth
suspension ("typically lasts for 1 hour, but can last up to 24 hours") opens a breaker, ``[UNAVAILABLE]`` and a
login Gmail accepted while marking it ``[THROTTLED]`` slow it down, and refused credentials stop it until the Gmail
account is saved again. The error text is only matched against the settings' patterns, never stored or shown.
"""

import imaplib

from imap_tools.errors import ImapToolsError

from apps.core.models.base.delivery_rates import DeliveryChannel

from ..rules.defaults import channel_settings, signal_patterns
from ..rules.signals import RateSignal, Reason, blocked, ok, pause, quota, text_has, throttle

# What a failing IMAP connection or command raises: imaplib's errors, imap_tools' status errors, and socket / TLS
# errors (timeouts included).
_IMAP_FAILURES = (imaplib.IMAP4.error, ImapToolsError, OSError)


def imap_signal(exc: BaseException) -> RateSignal | None:
    """The signal of a failed IMAP session (its error, or any error behind it); None when it says nothing about the
    rate (a timeout, a missing message)."""
    text = _error_text(exc)
    patterns = signal_patterns("imap")
    config = channel_settings(DeliveryChannel.GMAIL_IMAP)
    if text_has(text, patterns["auth_blocked_texts"]):
        return blocked(Reason.AUTH)
    if text_has(text, patterns["bandwidth_texts"]):
        return quota("bandwidth", seconds=config["bandwidth_breaker_seconds"])
    if text_has(text, patterns["pause_texts"]):
        return pause("connections", seconds=config["connections_pause_seconds"])
    if text_has(text, patterns["throttle_texts"]):
        return throttle("throttled")
    return None


def session_signal(exc: BaseException) -> RateSignal | None:
    """The signal of a session that ended with ``exc``: ``imap_signal``, else OK when nothing behind ``exc`` failed
    in IMAP (the session worked; the site's own code raised, for a missing message or Sent folder), else None (the
    outcome says nothing certain)."""
    signal = imap_signal(exc)
    if signal is None and not any(isinstance(item, _IMAP_FAILURES) for item in _chain(exc)):
        return ok()
    return signal


def login_signal(login_result) -> RateSignal | None:
    """A login Gmail accepted but marked as throttled (``MailBox.login_result``, ``(status, [lines])``)."""
    if text_has(_result_text(login_result), signal_patterns("imap")["throttle_texts"]):
        return throttle("throttled")
    return None


def _result_text(result) -> str:
    """An imaplib command result (``(status, [bytes, ...])``) as text; anything else (no result yet) as ""."""
    if not isinstance(result, tuple | list) or len(result) != 2:
        return ""
    status, lines = result
    parts = [status, *(lines if isinstance(lines, list | tuple) else [lines])]
    return " ".join(part.decode("utf-8", errors="replace") if isinstance(part, bytes) else str(part) for part in parts)


def _chain(exc: BaseException):
    seen, current = set(), exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


def _error_text(exc: BaseException) -> str:
    """The text of ``exc`` and of every error behind it, with any IMAP command result they carry."""
    return " ".join(f"{item} {_result_text(getattr(item, 'command_result', None))}" for item in _chain(exc))

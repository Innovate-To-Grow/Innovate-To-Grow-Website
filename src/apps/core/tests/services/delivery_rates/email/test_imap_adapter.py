"""Gmail IMAP answers to rate signals: the patterns in DELIVERY_RATES["signals"]["imap"], a throttled login seen in
``MailBox.login_result``, and the outcome of a whole session."""

import imaplib

from django.test import SimpleTestCase
from imap_tools.errors import MailboxFetchError, MailboxLoginError

from apps.core.services.delivery_rates import Reason, SignalKind
from apps.core.services.delivery_rates.adapters.imap import imap_signal, login_signal, session_signal


def login_refused(text: bytes):
    return MailboxLoginError(command_result=("NO", [text]), expected="OK")


class ImapSignalTests(SimpleTestCase):
    def test_gmail_answers_are_told_apart_by_their_text(self):
        cases = [
            (login_refused(b"[AUTHENTICATIONFAILED] Invalid credentials (Failure)"), SignalKind.BLOCKED, Reason.AUTH),
            (
                login_refused(b"[ALERT] Application-specific password required: https://support.google.com/accounts"),
                SignalKind.BLOCKED,
                Reason.AUTH,
            ),
            (login_refused(b"[ALERT] Too many simultaneous connections. (Failure)"), SignalKind.PAUSE, "connections"),
            (
                imaplib.IMAP4.abort("[OVERQUOTA] Account exceeded command or bandwidth limits."),
                SignalKind.QUOTA,
                "bandwidth",
            ),
            (imaplib.IMAP4.abort("[UNAVAILABLE] Temporary System Error"), SignalKind.THROTTLE, "throttled"),
        ]
        for exc, kind, reason in cases:
            with self.subTest(exc=str(exc)):
                signal = imap_signal(exc)
                self.assertEqual((signal.kind, signal.reason), (kind, reason))

    def test_pauses_and_suspensions_last_as_the_settings_say(self):
        self.assertEqual(imap_signal(login_refused(b"Too many simultaneous connections")).pause_seconds, 60)
        self.assertEqual(imap_signal(imaplib.IMAP4.abort("[OVERQUOTA]")).breaker_seconds, 3600)

    def test_an_error_behind_another_one_is_matched(self):
        try:
            try:
                raise MailboxFetchError(command_result=("NO", [b"[OVERQUOTA] Account exceeded"]), expected="OK")
            except MailboxFetchError as exc:
                raise RuntimeError("Unable to connect to inbox.") from exc
        except RuntimeError as wrapped:
            self.assertEqual(imap_signal(wrapped).kind, SignalKind.QUOTA)

    def test_a_timeout_or_an_unknown_refusal_is_no_signal(self):
        self.assertIsNone(imap_signal(TimeoutError("timed out")))
        self.assertIsNone(imap_signal(login_refused(b"[UNKNOWN] something else")))


class LoginAndSessionSignalTests(SimpleTestCase):
    def test_a_login_marked_throttled_slows_down_and_a_plain_one_does_not(self):
        throttled = ("OK", [b"[THROTTLED] i2g@example.edu authenticated (Success)"])

        self.assertEqual(login_signal(throttled).kind, SignalKind.THROTTLE)
        self.assertIsNone(login_signal(("OK", [b"i2g@example.edu authenticated (Success)"])))
        self.assertIsNone(login_signal(None))
        self.assertIsNone(login_signal(object()))

    def test_the_sites_own_error_inside_a_working_session_is_ok(self):
        self.assertEqual(session_signal(LookupError("Message not found.")).kind, SignalKind.OK)

    def test_an_imap_or_network_failure_without_a_pattern_is_uncertain(self):
        self.assertIsNone(session_signal(TimeoutError("timed out")))
        self.assertIsNone(session_signal(imaplib.IMAP4.abort("socket error: EOF")))
        self.assertEqual(session_signal(login_refused(b"[AUTHENTICATIONFAILED]")).kind, SignalKind.BLOCKED)

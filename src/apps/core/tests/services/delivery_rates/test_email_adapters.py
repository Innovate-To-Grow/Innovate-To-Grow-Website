"""Provider answers to rate signals: SES, SMTP (Gmail SMTP and the relay included) and Microsoft Graph."""

from botocore.exceptions import ClientError, ReadTimeoutError
from django.test import SimpleTestCase

from apps.core.services.delivery_rates import Reason, Scope, SignalKind
from apps.core.services.delivery_rates.adapters.graph import graph_signal, token_signal
from apps.core.services.delivery_rates.adapters.ses import ses_signal
from apps.core.services.delivery_rates.adapters.smtp import reply_text, smtp_signal


def client_error(code, message=""):
    return ClientError({"Error": {"Code": code, "Message": message}}, "SendRawEmail")


class SesSignalTests(SimpleTestCase):
    def test_the_rate_and_the_daily_quota_both_answer_throttling(self):
        rate = ses_signal(client_error("Throttling", "Maximum sending rate exceeded."))
        daily = ses_signal(client_error("Throttling", "Daily message quota exceeded."))

        self.assertEqual(rate.kind, SignalKind.THROTTLE)
        self.assertEqual((daily.kind, daily.breaker_seconds), (SignalKind.QUOTA, 600))

    def test_account_and_configuration_set_pauses_stop_sending(self):
        account = ses_signal(client_error("AccountSendingPausedException"))
        campaigns = ses_signal(client_error("ConfigurationSetSendingPausedException"))

        self.assertEqual(
            (account.kind, account.reason, account.scope), (SignalKind.BLOCKED, Reason.ACCOUNT_PAUSED, Scope.ALL)
        )
        self.assertEqual((campaigns.kind, campaigns.scope), (SignalKind.BLOCKED, Scope.BULK))

    def test_rejections_are_about_the_message_and_timeouts_are_no_answer(self):
        self.assertEqual(ses_signal(client_error("MessageRejected", "Email address is not verified.")).kind, "none")
        self.assertEqual(ses_signal(client_error("InternalFailure")).kind, SignalKind.NONE)
        self.assertIsNone(ses_signal(ReadTimeoutError(endpoint_url="https://email.us-west-2.amazonaws.com")))
        self.assertIsNone(ses_signal(RuntimeError("no answer")))


class SmtpSignalTests(SimpleTestCase):
    def test_google_reply_codes_are_told_apart_by_their_enhanced_status_and_text(self):
        cases = [
            (421, "4.7.0 Try again later, closing connection.", SignalKind.THROTTLE),
            (450, "4.2.1 Peak SMTP relay limit exceeded for customer.", SignalKind.THROTTLE),
            (454, "Throttling failure: Maximum sending rate exceeded.", SignalKind.THROTTLE),
            (454, "4.7.0 Too many login attempts, please try again later. Too many sign-in attempts", SignalKind.PAUSE),
            (550, "5.4.5 Daily user sending limit exceeded.", SignalKind.QUOTA),
            (550, "5.7.1 Daily SMTP relay sending limit exceeded for customer.", SignalKind.QUOTA),
            (454, "Throttling failure: Daily message quota exceeded.", SignalKind.QUOTA),
            (450, "4.2.1 The user you are trying to contact is receiving mail too quickly.", SignalKind.NONE),
            (550, "5.2.1 The email account that you tried to reach is receiving mail at a rate", SignalKind.NONE),
            (452, "4.5.3 Your message has too many recipients.", SignalKind.NONE),
            (535, "5.7.8 Username and Password not accepted.", SignalKind.BLOCKED),
            (550, "5.1.1 The email account that you tried to reach does not exist.", SignalKind.NONE),
        ]
        for code, text, kind in cases:
            with self.subTest(code=code, text=text):
                self.assertEqual(smtp_signal(code, text).kind, kind)

    def test_sign_in_pauses_use_the_settings_and_auth_refusals_name_their_reason(self):
        self.assertEqual(smtp_signal(454, "4.7.0 Too many sign-in attempts").pause_seconds, 300)
        self.assertEqual(smtp_signal(534, "5.7.9 Application-specific password required.").reason, Reason.AUTH)

    def test_reply_bytes_are_decoded_for_matching(self):
        self.assertEqual(reply_text(b"4.2.1 Peak SMTP relay limit"), "4.2.1 Peak SMTP relay limit")
        self.assertEqual(reply_text(b"\xff bad"), "� bad")
        self.assertEqual(reply_text(None), "")


class GraphSignalTests(SimpleTestCase):
    def test_throttles_carry_retry_after_as_seconds_or_an_http_date(self):
        for status in (429, 503, 509):
            with self.subTest(status=status):
                signal = graph_signal(status, {"retry-after": "12"}, "")
                self.assertEqual((signal.kind, signal.retry_after), (SignalKind.THROTTLE, 12.0))
        dated = graph_signal(429, {"retry-after": "Wed, 21 Oct 2015 07:28:00 GMT"}, "")
        self.assertEqual(dated.retry_after, 1.0)  # a past date still means "wait", for at least a second
        self.assertEqual(graph_signal(429, {"retry-after": "99999"}, "").retry_after, 3600.0)

    def test_the_innermost_codes_name_quota_and_pushback(self):
        quota = graph_signal(403, {}, "ErrorSubmissionQuotaExceeded")
        pushback = graph_signal(403, {}, "ApplicationThrottled")

        self.assertEqual(quota.kind, SignalKind.QUOTA)
        self.assertEqual((pushback.kind, pushback.uncertain), (SignalKind.PAUSE, True))
        self.assertEqual(graph_signal(429, {}, "ApplicationThrottled").kind, SignalKind.THROTTLE)

    def test_sends_the_app_may_not_make_stop_sending_but_reads_answer_per_request(self):
        self.assertEqual(graph_signal(403, {}, "ErrorAccessDenied").reason, Reason.PERMISSION)
        self.assertEqual(graph_signal(404, {}, "ErrorInvalidUser").kind, SignalKind.BLOCKED)
        self.assertEqual(graph_signal(507, {}, "").reason, "mailbox_full")
        for status in (401, 403, 404):
            with self.subTest(status=status):
                self.assertEqual(graph_signal(status, {}, "ErrorAccessDenied", read=True).kind, SignalKind.NONE)

    def test_other_answers(self):
        self.assertEqual(graph_signal(202, {}, "").kind, SignalKind.OK)
        self.assertEqual(graph_signal(200, {}, "", read=True).kind, SignalKind.OK)
        self.assertEqual(graph_signal(400, {}, "ErrorInvalidRecipients").kind, SignalKind.NONE)
        self.assertEqual(graph_signal(502, {}, "").kind, SignalKind.UNCERTAIN)

    def test_the_token_endpoint_pauses_while_busy_and_stops_on_refused_credentials(self):
        busy = token_signal(429, {"retry-after": "7"}, "", retryable=True)
        unavailable = token_signal(400, {}, "temporarily_unavailable", retryable=False)
        throttled_app = token_signal(400, {}, "invalid_request AADSTS50196", retryable=False)
        refused = token_signal(401, {}, "invalid_client AADSTS7000215", retryable=False)

        self.assertEqual((busy.kind, busy.retry_after), (SignalKind.PAUSE, 7.0))
        self.assertEqual({unavailable.kind, throttled_app.kind}, {SignalKind.PAUSE})
        self.assertEqual((refused.kind, refused.reason), (SignalKind.BLOCKED, Reason.AUTH))

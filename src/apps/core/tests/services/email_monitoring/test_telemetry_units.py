"""Telemetry pieces on their own: classification, text bounds, notes, access-check probes, retention, and the
safe-ORM denylist that keeps the telemetry away from the CLI and the assistant."""

from datetime import timedelta

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.core.models import EmailBounce, EmailCategory, EmailMonitorState, OutboundEmail, OutboundEmailAttempt
from apps.core.services.db_tools.safe_orm import DENIED_MODEL_LABELS, is_model_denied
from apps.core.services.email import PermanentEmailDeliveryError, TransientEmailDeliveryError
from apps.core.services.email.graph.access_check.probes import OUTCOME_UNKNOWN, RATE_HELD, UNREACHABLE
from apps.core.services.email.graph.access_check.report import ProbeResult
from apps.core.services.email.telemetry import classify, kind_label, text
from apps.core.services.email.telemetry.context import TrackingContext, correlation_id, email_tracking
from apps.core.services.email.telemetry.notes import AttemptNotes, diagnostic_headers
from apps.core.services.email.telemetry.probes import record_probe_send, tracked_probe
from apps.core.services.email.telemetry.retention import purge_expired
from apps.core.services.email.transport import ConnectFailed, ResponseLost

from .helpers import make_attempt, make_bounce, make_email, monitoring_settings

Outcome = OutboundEmailAttempt.Outcome
Status = OutboundEmail.Status


class ClassifyTests(SimpleTestCase):
    def notes(self, **values):
        notes = AttemptNotes()
        for name, value in values.items():
            setattr(notes, name, value)
        return notes

    def test_attempt_outcomes_follow_the_error_class_and_the_provider_boundary(self):
        self.assertEqual(classify.attempt_outcome(None, entered=True), Outcome.ACCEPTED)
        self.assertEqual(classify.attempt_outcome(TransientEmailDeliveryError("x"), entered=True), Outcome.TRANSIENT)
        self.assertEqual(classify.attempt_outcome(PermanentEmailDeliveryError("x"), entered=False), Outcome.PERMANENT)
        self.assertEqual(classify.attempt_outcome(RuntimeError(), entered=True), Outcome.UNCERTAIN)
        self.assertEqual(classify.attempt_outcome(RuntimeError(), entered=False), Outcome.NOT_SENT)

    def test_an_api_failure_needs_the_api_to_have_been_reached(self):
        self.assertEqual(classify.email_status(Outcome.PERMANENT, reached_api=True), Status.FAILED)
        self.assertEqual(classify.email_status(Outcome.PERMANENT, reached_api=False), Status.NOT_SENT)
        self.assertEqual(classify.email_status(Outcome.UNCERTAIN, reached_api=False), Status.UNCERTAIN)
        self.assertEqual(classify.email_status(Outcome.ACCEPTED, reached_api=True), Status.ACCEPTED)

    def test_error_kinds(self):
        error = PermanentEmailDeliveryError("x")
        cases = (
            ({"http_status": 429}, "throttled"),
            ({"http_status": 509}, "server_busy"),
            ({"http_status": 400, "error_code": "ErrorSubmissionQuotaExceeded"}, "quota"),
            ({"http_status": 400, "inner_error_code": "ErrorExceededMessageLimit"}, "pushback"),
            ({"http_status": 400, "error_code": "ErrorSendAsDenied"}, "mailbox_restricted"),
            ({"http_status": 422}, "bad_request"),
            ({"http_status": 502}, "server_error"),
            ({"http_status": 503, "operation": "token"}, "server_busy"),
            ({"http_status": 429, "operation": "token"}, "throttled"),
            ({"http_status": 400, "operation": "token"}, "auth"),
            ({"transport_error": "tls"}, "tls"),
            ({"operation": "token"}, "auth"),
            ({"operation": "compose"}, "compose"),
            ({}, "unexpected"),
        )
        for values, kind in cases:
            with self.subTest(values=values):
                self.assertEqual(classify.error_kind(error, self.notes(**values)), kind)
        self.assertEqual(classify.error_kind(None, self.notes()), "")
        self.assertEqual(classify.error_kind(error, self.notes(), provider="ses"), "provider_error")

    def test_every_kind_has_a_label(self):
        self.assertEqual(kind_label("throttled"), "Throttled (HTTP 429)")
        self.assertEqual(kind_label("some_new_kind"), "Some new kind")
        self.assertEqual(kind_label(""), "")

    def test_transport_failures_tell_apart_what_may_have_been_sent(self):
        timed_out = ResponseLost()
        timed_out.__cause__ = TimeoutError()
        tls = ConnectFailed(verification_failed=True)
        for exc, kind in (
            (ConnectFailed(), "connect_failed"),
            (ResponseLost(), "response_lost"),
            (timed_out, "timeout"),
            (tls, "tls"),
        ):
            notes = AttemptNotes()
            notes.step("send_mail")
            notes.transport_failed(exc)
            self.assertEqual(notes.transport_error, kind)


class TextTests(SimpleTestCase):
    def test_error_texts_are_scrubbed_of_tokens_and_bounded(self):
        scrubbed = text.scrub("failed with Bearer eyJhbGciOi.secret and " + "A" * 80 + "\nnext line", 500)

        self.assertNotIn("eyJhbGciOi", scrubbed)
        self.assertNotIn("A" * 80, scrubbed)
        self.assertNotIn("\n", scrubbed)
        self.assertEqual(len(text.scrub("word " * 200, 500)), 500)

    def test_addresses_are_bare_and_lower_case(self):
        self.assertEqual(
            text.addresses(["Ann <ANN@Example.com>", "ann@example.com", "not an address"]), ["ann@example.com"]
        )

    def test_message_ids_and_subject_digests(self):
        self.assertEqual(text.message_id(" <a@b>  "), "<a@b>")
        self.assertEqual(text.message_id("no id"), "")
        self.assertEqual(text.subject_digest("Hello  World"), text.subject_digest(" hello world "))
        self.assertEqual(text.subject_digest(""), "")

    def test_only_short_printable_diagnostic_headers_are_kept(self):
        kept = diagnostic_headers(
            {
                "x-ms-ags-diagnostic": '{"ServerInfo":{"DataCenter":"West US"}}',
                "x-ms-throttle-scope": "x" * 300,
                "authorization": "Bearer t",
            }
        )

        self.assertEqual(list(kept), ["x-ms-ags-diagnostic"])


class ContextTests(SimpleTestCase):
    def test_nested_blocks_merge_and_the_inner_value_wins(self):
        with (
            email_tracking(category="campaign", campaign_id="c1"),
            email_tracking(category="", source_id="s1") as context,
        ):
            self.assertEqual((context.category, context.campaign_id, context.source_id), ("campaign", "c1", "s1"))

    def test_an_unknown_field_is_a_programming_error(self):
        with self.assertRaises(TypeError), email_tracking(no_such_field="x"):
            pass

    def test_correlation_ids_repeat_only_under_a_retry_key(self):
        keyed = TrackingContext(retry_key="mail.recipientlog:1")

        self.assertEqual(correlation_id(keyed, ["a@x"], "S"), correlation_id(keyed, ["a@x"], "S"))
        self.assertNotEqual(correlation_id(keyed, ["a@x"], "S"), correlation_id(keyed, ["b@x"], "S"))
        self.assertNotEqual(
            correlation_id(TrackingContext(), ["a@x"], "S"), correlation_id(TrackingContext(), ["a@x"], "S")
        )


class ProbeTelemetryTests(TestCase):
    def result(self, status=None, note="", code=""):
        return ProbeResult(
            "send", "i2g@ucmerced.edu", "allowed", "pass", status=status, code=code, note=note, request_id="req-1"
        )

    def record(self, result):
        record_probe_send(result, recipient="i2g@ucmerced.edu", send_format="mime", subject="I2G access check")

    def test_an_accepted_probe_is_an_access_check_email(self):
        self.record(self.result(202))

        email = OutboundEmail.objects.get()
        self.assertEqual(
            (email.category, email.status, email.delivery_status),
            (EmailCategory.ACCESS_CHECK, Status.ACCEPTED, "unknown"),
        )
        attempt = email.attempts.get()
        self.assertEqual((attempt.operation, attempt.outcome, attempt.request_id), ("probe", Outcome.ACCEPTED, "req-1"))

    def test_refused_unreachable_and_unknown_probes(self):
        self.record(self.result(403, code="ErrorAccessDenied", note="refused"))
        self.record(self.result(None, note=UNREACHABLE))
        self.record(self.result(None, note=OUTCOME_UNKNOWN))

        statuses = list(OutboundEmail.objects.order_by("created_at").values_list("status", "last_error_code"))
        self.assertEqual(statuses, [(Status.FAILED, "ErrorAccessDenied"), (Status.FAILED, ""), (Status.UNCERTAIN, "")])

    def test_a_probe_that_was_never_sent_is_not_recorded(self):
        self.record(self.result(None, note=RATE_HELD.format(30)))

        self.assertFalse(OutboundEmail.objects.exists())

    @monitoring_settings(telemetry_enabled=False)
    def test_switched_off_probes_are_not_recorded(self):
        self.record(self.result(202))

        self.assertFalse(OutboundEmail.objects.exists())

    def test_the_decorator_records_the_recipient_keyword_or_the_sending_mailbox(self):
        class Prober:
            @tracked_probe("json", "Probe")
            def send_json(self, check, *, recipient):
                return ProbeResult(check, "i2g@ucmerced.edu", "denied", "pass", status=403)

            @tracked_probe("mime", "Probe")
            def send_mime(self, mailbox):
                return ProbeResult("send", mailbox, "allowed", "pass", status=202)

        Prober().send_json("send_as", recipient="deny@ucmerced.edu")
        Prober().send_mime("i2g@ucmerced.edu")

        self.assertEqual(
            set(OutboundEmail.objects.values_list("recipient", "send_format")),
            {("deny@ucmerced.edu", "json"), ("i2g@ucmerced.edu", "mime")},
        )


class RetentionTests(TestCase):
    def test_emails_and_bounces_past_their_windows_are_deleted_with_their_attempts(self):
        now = timezone.now()
        old = make_email(created_at=now - timedelta(days=200))
        make_attempt(old)
        kept = make_email(created_at=now - timedelta(days=10))
        make_bounce(email=old, received_at=now - timedelta(days=200))
        make_bounce(received_at=now - timedelta(days=400))

        with monitoring_settings(retention_days=180, bounce_retention_days=365, purge_batch_size=1):
            result = purge_expired(now=now)

        self.assertEqual(result, {"emails": 1, "bounces": 1})
        self.assertEqual(list(OutboundEmail.objects.all()), [kept])
        self.assertFalse(OutboundEmailAttempt.objects.exists())
        self.assertIsNone(EmailBounce.objects.get().email)

    def test_a_stop_request_ends_the_purge(self):
        make_email(created_at=timezone.now() - timedelta(days=400))

        self.assertEqual(purge_expired(should_stop=lambda: True), {"emails": 0, "bounces": 0})


class SafeOrmDenylistTests(SimpleTestCase):
    def test_the_assistant_and_the_cli_can_neither_read_nor_write_the_telemetry(self):
        for model in (OutboundEmail, OutboundEmailAttempt, EmailBounce, EmailMonitorState):
            with self.subTest(model=model.__name__):
                self.assertIn(model._meta.label_lower, DENIED_MODEL_LABELS)
                self.assertTrue(is_model_denied(model, write=False))
                self.assertTrue(is_model_denied(model, write=True))

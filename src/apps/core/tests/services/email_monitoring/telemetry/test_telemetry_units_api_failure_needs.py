from apps.core.services.email import PermanentEmailDeliveryError
from apps.core.services.email.sending.transport import ConnectFailed, ResponseLost
from apps.core.services.email.telemetry import classify, kind_label
from apps.core.services.email.telemetry.notes import AttemptNotes
from apps.core.tests.services.email_monitoring.telemetry.test_telemetry_units import Outcome, Status, _ClassifyCase


class ClassifyTests(_ClassifyCase):
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

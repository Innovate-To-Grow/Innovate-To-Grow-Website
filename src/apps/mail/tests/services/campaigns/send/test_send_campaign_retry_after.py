"""A provider's Retry-After hint survives the campaign transport and becomes the job error's retry hint."""

from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.core.services.background_jobs import PermanentJobError, TransientJobError, UncertainJobError
from apps.core.services.email import PermanentEmailDeliveryError, TransientEmailDeliveryError
from apps.mail.services.campaign.dispatch.failures import _job_error_for_ses_result
from apps.mail.services.send_campaign.transport import SesSendResult, _send_via_ses


def send(**kwargs):
    return _send_via_ses(
        ses_client=SimpleNamespace(provider="graph"),
        source="ignored@example.com",
        recipient="to@example.com",
        subject="Subject",
        html_body="<p>Hi</p>",
        **kwargs,
    )


class SendViaProviderRetryAfterTests(SimpleTestCase):
    @patch("apps.mail.services.send_campaign.transport.deliver_email")
    def test_a_transient_failure_keeps_the_providers_hint(self, deliver):
        deliver.side_effect = TransientEmailDeliveryError("throttled", retry_after=45.0)

        result = send()

        self.assertEqual((result.outcome, result.error, result.retry_after), ("transient", "throttled", 45.0))
        self.assertEqual(result.provider, "graph")

    @patch("apps.mail.services.send_campaign.transport.deliver_email")
    def test_a_transient_failure_without_a_hint_has_none(self, deliver):
        deliver.side_effect = TransientEmailDeliveryError("busy")

        self.assertIsNone(send().retry_after)

    @patch("apps.mail.services.send_campaign.transport.deliver_email")
    def test_other_failures_have_no_hint(self, deliver):
        deliver.side_effect = PermanentEmailDeliveryError("no")

        result = send()

        self.assertEqual(result.outcome, "permanent")
        self.assertIsNone(result.retry_after)

    def test_results_default_to_no_hint(self):
        self.assertIsNone(SesSendResult(message_id="id").retry_after)


class JobErrorForResultTests(SimpleTestCase):
    def test_a_transient_result_hands_its_hint_to_the_job_error(self):
        error = _job_error_for_ses_result(SesSendResult(error="throttled", outcome="transient", retry_after=45.0))

        self.assertIsInstance(error, TransientJobError)
        self.assertEqual((str(error), error.retry_after), ("throttled", 45.0))

    def test_results_without_the_field_map_to_no_hint(self):
        error = _job_error_for_ses_result(SimpleNamespace(error="busy", outcome="transient"))

        self.assertIsInstance(error, TransientJobError)
        self.assertIsNone(error.retry_after)

    def test_permanent_and_uncertain_results_are_unchanged(self):
        permanent = _job_error_for_ses_result(SesSendResult(error="no", outcome="permanent"))
        uncertain = _job_error_for_ses_result(SesSendResult(error="maybe", outcome="uncertain"))

        self.assertIsInstance(permanent, PermanentJobError)
        self.assertIsInstance(uncertain, UncertainJobError)

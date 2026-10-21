from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase

from apps.authn.services.email.notification_jobs import enqueue_notification_email
from apps.core.services.aws.provider_outcomes import PROVIDER_OUTCOME_TRANSIENT, ProviderDeliveryError
from apps.core.services.background_jobs import TransientJobError


class NotificationEmailJobTests(TestCase):
    def test_identical_notification_events_are_distinct_jobs(self):
        notification = {
            "recipient": "owner@example.com",
            "subject": "Security notice",
            "template": "notice.html",
            "context": {"account_url": "https://example.com/account"},
        }

        first, _created = enqueue_notification_email(**notification)
        second, _created = enqueue_notification_email(**notification)

        self.assertNotEqual(first.pk, second.pk)
        self.assertNotEqual(first.dedupe_key, second.dedupe_key)

    @patch("apps.authn.services.email.notification_jobs.wait_for_email_slot")
    @patch(
        "apps.authn.services.email.send_email.send_notification_email",
        side_effect=ProviderDeliveryError(
            "SES temporarily rejected the request.",
            outcome=PROVIDER_OUTCOME_TRANSIENT,
        ),
    )
    def test_notification_handler_preserves_definitive_transient_outcome(
        self,
        send_notification,
        wait_for_slot,
    ):
        from apps.authn.services.email.notification_jobs import send_notification_email_job

        job = SimpleNamespace(
            payload={
                "recipient": "owner@example.com",
                "subject": "Security notice",
                "template": "notice.html",
                "context": {},
            },
            begin_provider_call=lambda: True,
        )

        with self.assertRaises(TransientJobError):
            send_notification_email_job(job)

        wait_for_slot.assert_called_once_with()
        self.assertTrue(send_notification.call_args.kwargs["raise_provider_errors"])

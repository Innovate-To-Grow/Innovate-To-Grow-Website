from unittest.mock import MagicMock, patch

from django.utils import timezone

from apps.core.services.email import (
    PermanentEmailDeliveryError,
    UncertainEmailDeliveryError,
)
from apps.event.services.ticket.mail import _send_via_ses, send_ticket_email
from apps.event.services.ticket.message import _issue_ticket_login_link
from apps.event.tests.services.tickets.mail.test_ticket_mail import _mock_config, _SendTicketEmailCase
from apps.mail.models import LoginLinkToken


class SendTicketEmailTest(_SendTicketEmailCase):
    @patch("apps.event.services.ticket.mail._send_via_ses")
    @patch("apps.event.services.ticket.mail._load_config")
    def test_lost_claim_at_provider_boundary_discards_only_provisional_link(
        self,
        mock_load_config,
        mock_ses,
    ):
        from apps.core.services.background_jobs import JobClaimLost

        mock_load_config.return_value = _mock_config(ses_configured=True)
        _issue_ticket_login_link(self.registration)
        previous = LoginLinkToken.objects.get(registration=self.registration)
        newer_worker_error = "Newer worker recorded this failure"
        self.registration.ticket_email_error = newer_worker_error
        self.registration.save(update_fields=["ticket_email_error"])

        def lose_claim(**kwargs):
            kwargs["before_provider_call"]()
            return True

        mock_ses.side_effect = lose_claim
        with self.assertRaises(JobClaimLost):
            send_ticket_email(
                self.registration,
                before_provider_call=MagicMock(side_effect=JobClaimLost("claim replaced")),
            )

        previous.refresh_from_db()
        self.registration.refresh_from_db()
        self.assertTrue(previous.is_valid)
        self.assertEqual(
            list(self.registration.login_tokens.values_list("pk", flat=True)),
            [previous.pk],
        )
        self.assertEqual(self.registration.ticket_email_error, newer_worker_error)

    @patch("apps.event.services.ticket.mail.deliver_email")
    @patch("apps.event.services.ticket.mail._load_config")
    def test_definitive_provider_rejection_discards_provisional_but_keeps_previous_link(
        self,
        mock_load_config,
        mock_deliver,
    ):
        mock_load_config.return_value = _mock_config(ses_configured=True)
        mock_deliver.side_effect = PermanentEmailDeliveryError("rejected")
        _issue_ticket_login_link(self.registration)
        previous = LoginLinkToken.objects.get(registration=self.registration)

        with self.assertRaises(RuntimeError):
            send_ticket_email(self.registration)

        previous.refresh_from_db()
        self.assertTrue(previous.is_valid)
        self.assertEqual(
            list(self.registration.login_tokens.values_list("pk", flat=True)),
            [previous.pk],
        )

    @patch("apps.event.services.ticket.mail.send_ticket_email")
    def test_ticket_job_fences_login_link_mutation_with_current_claim(self, mock_send):
        from django.db import transaction

        from apps.core.models import BackgroundJob
        from apps.core.services.background_jobs import JobClaimLost
        from apps.event.services.ticket.jobs import send_ticket_email_job

        stale_claim = BackgroundJob.new_claim_token()
        job = BackgroundJob.objects.create(
            kind="event.ticket_email",
            dedupe_key="lost-ticket-claim",
            payload={"registration_id": str(self.registration.pk)},
            status=BackgroundJob.Status.PROCESSING,
            claim_token=stale_claim,
            claimed_at=timezone.now(),
            can_retry_after_claim=False,
        )
        BackgroundJob.objects.filter(pk=job.pk).update(claim_token=BackgroundJob.new_claim_token())

        def run_token_fence(_registration, **kwargs):
            with transaction.atomic():
                kwargs["before_token_mutation"]()

        mock_send.side_effect = run_token_fence

        with self.assertRaises(JobClaimLost):
            send_ticket_email_job(job)

        mock_send.assert_called_once()

    @patch("apps.event.services.ticket.mail.deliver_email")
    @patch("apps.event.services.ticket.mail._load_config")
    def test_sends_to_secondary_email(self, mock_load_config, mock_deliver):
        mock_load_config.return_value = _mock_config(ses_configured=True)
        self.registration.attendee_secondary_email = "secondary@example.com"
        self.registration.save(update_fields=["attendee_secondary_email"])

        send_ticket_email(self.registration)

        message = mock_deliver.call_args.args[0]
        self.assertEqual(message.to, (self.registration.attendee_email, "secondary@example.com"))

    @patch("apps.event.services.ticket.mail.deliver_email")
    @patch("apps.event.services.ticket.mail._load_config")
    def test_send_via_ses_returns_false_on_delivery_error(self, mock_load_config, mock_deliver):
        mock_load_config.return_value = _mock_config(ses_configured=True)
        mock_deliver.side_effect = PermanentEmailDeliveryError("missing credentials")

        with self.assertRaises(RuntimeError):
            send_ticket_email(self.registration)

        self.registration.refresh_from_db()
        self.assertIsNone(self.registration.ticket_email_sent_at)
        self.assertIn("delivery provider", self.registration.ticket_email_error)

    @patch("apps.event.services.ticket.mail.deliver_email")
    @patch("apps.event.services.ticket.mail._load_config")
    def test_send_via_ses_returns_false_on_client_error(self, mock_load_config, mock_deliver):
        mock_load_config.return_value = _mock_config(ses_configured=True)
        mock_deliver.side_effect = PermanentEmailDeliveryError("rejected")

        with self.assertRaises(RuntimeError):
            send_ticket_email(self.registration)

        self.registration.refresh_from_db()
        self.assertIsNone(self.registration.ticket_email_sent_at)
        self.assertIn("delivery provider", self.registration.ticket_email_error)

    @patch("apps.event.services.ticket.mail.deliver_email")
    def test_worker_mode_classifies_lost_response_as_uncertain(self, mock_deliver):
        from apps.core.services.aws.provider_outcomes import (
            PROVIDER_OUTCOME_UNCERTAIN,
            ProviderDeliveryError,
        )

        def lose_response(*args, **kwargs):
            kwargs["before_provider_call"]()
            raise UncertainEmailDeliveryError("response lost")

        mock_deliver.side_effect = lose_response

        with self.assertRaises(ProviderDeliveryError) as raised:
            _send_via_ses(
                config=_mock_config(ses_configured=True),
                mime_message=MagicMock(),
                before_provider_call=MagicMock(),
                raise_provider_errors=True,
            )

        self.assertEqual(raised.exception.outcome, PROVIDER_OUTCOME_UNCERTAIN)

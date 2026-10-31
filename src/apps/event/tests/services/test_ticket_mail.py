import base64
import datetime
import json
from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.utils import timezone

from apps.core.services.aws.provider_outcomes import ProviderDeliveryError
from apps.core.services.background_jobs import TransientJobError
from apps.core.services.email import (
    DeliveryResult,
    PermanentEmailDeliveryError,
    TransientEmailDeliveryError,
    UncertainEmailDeliveryError,
)
from apps.core.tests.services.test_email_graph import GraphFixtureMixin, make_provider
from apps.event.models import EventRegistration, Ticket
from apps.event.services.ticket.jobs import send_ticket_email_job
from apps.event.services.ticket.mail import (
    _build_mime_message,
    _build_ticket_message,
    _issue_ticket_login_link,
    _send_via_ses,
    send_ticket_email,
)
from apps.event.tests.helpers import make_event, make_member
from apps.mail.models import LoginLinkToken


def _mock_config(ses_configured=True):
    config = MagicMock()
    config.delivery_configured = ses_configured
    config.source_address = "Innovate to Grow <i2g@test.com>"
    return config


class SendTicketEmailTest(TestCase):
    def setUp(self):
        self.member = make_member()
        self.event = make_event()
        self.ticket = Ticket.objects.create(event=self.event, name="GA")
        self.registration = EventRegistration.objects.create(member=self.member, event=self.event, ticket=self.ticket)

    def test_builds_provider_neutral_pdf417_and_ics_attachments(self):
        message = _build_mime_message(
            subject="Ticket",
            from_address="ignored@example.com",
            recipients=["primary@example.com", "secondary@example.com"],
            html_body='<img src="cid:ticket-barcode">',
            barcode_bytes=b"png-data",
            ics_data="BEGIN:VCALENDAR",
        )
        self.assertEqual(message.to, ("primary@example.com", "secondary@example.com"))
        self.assertEqual(message.attachments[0].content_type, "image/png")
        self.assertEqual(message.attachments[0].filename, "ticket-barcode.png")
        self.assertEqual(message.attachments[1].content_type, "text/calendar")
        self.assertEqual(message.attachments[1].filename, "event.ics")
        self.assertIn("cid:ticket-barcode", message.html_body)
        # The ticket code and the login link are credentials: no copy may stay in the sender's Sent Items.
        self.assertIs(message.keep_sent_copy, False)

    @patch("apps.event.services.ticket.mail.deliver_email")
    @patch("apps.event.services.ticket.mail._load_config")
    def test_sends_via_ses(self, mock_load_config, mock_deliver):
        mock_load_config.return_value = _mock_config(ses_configured=True)
        mock_deliver.return_value = DeliveryResult(provider="ses", message_id="ticket-1")

        send_ticket_email(self.registration)

        mock_deliver.assert_called_once()
        message = mock_deliver.call_args.args[0]
        self.assertEqual(message.attachments[0].content_id, "ticket-barcode")
        self.assertEqual(message.attachments[0].disposition, "inline")
        self.assertEqual(message.attachments[1].content_type, "text/calendar")
        self.assertIn(self.event.name, message.html_body)

        self.registration.refresh_from_db()
        self.assertIsNotNone(self.registration.ticket_email_sent_at)
        self.assertEqual(self.registration.ticket_email_error, "")

    @patch("apps.event.services.ticket.mail._send_via_ses", return_value=False)
    @patch("apps.event.services.ticket.mail._load_config")
    def test_records_error_when_ses_is_not_configured(self, mock_load_config, mock_ses):
        mock_load_config.return_value = _mock_config(ses_configured=False)

        with self.assertRaises(RuntimeError):
            send_ticket_email(self.registration)

        self.registration.refresh_from_db()
        self.assertIsNone(self.registration.ticket_email_sent_at)
        self.assertIn("delivery provider", self.registration.ticket_email_error)

    @patch("apps.event.services.ticket.mail._send_via_ses")
    @patch("apps.event.services.ticket.mail._load_config")
    def test_unconfigured_resend_keeps_previous_login_link(self, mock_load_config, mock_ses):
        mock_load_config.return_value = _mock_config(ses_configured=False)
        _issue_ticket_login_link(self.registration)
        previous = LoginLinkToken.objects.get(registration=self.registration)

        with self.assertRaises(RuntimeError):
            send_ticket_email(self.registration)

        previous.refresh_from_db()
        self.assertTrue(previous.is_valid)
        self.assertEqual(self.registration.login_tokens.count(), 1)
        mock_ses.assert_not_called()

    @patch("apps.event.services.ticket.mail._send_via_ses", return_value=False)
    @patch("apps.event.services.ticket.mail._load_config")
    def test_records_error_on_ses_failure(self, mock_load_config, mock_ses):
        mock_load_config.return_value = _mock_config(ses_configured=True)

        with self.assertRaises(RuntimeError):
            send_ticket_email(self.registration)

        self.registration.refresh_from_db()
        self.assertIsNone(self.registration.ticket_email_sent_at)
        self.assertIn("delivery provider", self.registration.ticket_email_error)

    @patch("apps.event.services.ticket.mail._send_via_ses", return_value=False)
    @patch("apps.event.services.ticket.mail._load_config")
    def test_failed_resend_keeps_previous_login_link(self, mock_load_config, _mock_ses):
        mock_load_config.return_value = _mock_config(ses_configured=True)
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

    @patch("apps.event.services.ticket.mail._send_via_ses")
    @patch("apps.event.services.ticket.mail._load_config")
    def test_lost_claim_before_token_mutation_keeps_previous_link(self, mock_load_config, mock_ses):
        from apps.core.services.background_jobs import JobClaimLost

        mock_load_config.return_value = _mock_config(ses_configured=True)
        _issue_ticket_login_link(self.registration)
        previous = LoginLinkToken.objects.get(registration=self.registration)

        with self.assertRaises(JobClaimLost):
            send_ticket_email(
                self.registration,
                before_token_mutation=MagicMock(side_effect=JobClaimLost("claim replaced")),
            )

        previous.refresh_from_db()
        self.registration.refresh_from_db()
        self.assertTrue(previous.is_valid)
        self.assertEqual(self.registration.login_tokens.count(), 1)
        self.assertEqual(self.registration.ticket_email_error, "")
        mock_ses.assert_not_called()

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

    @patch("apps.event.services.ticket.jobs.wait_for_email_slot")
    @patch("apps.event.services.ticket.mail.send_ticket_email")
    def test_ticket_job_fences_login_link_mutation_with_current_claim(self, mock_send, _wait_for_slot):
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

    @patch("apps.event.services.ticket.mail.deliver_email")
    @patch("apps.event.services.ticket.mail._load_config")
    def test_uncertain_resend_keeps_previous_and_provisional_links(
        self,
        mock_load_config,
        mock_deliver,
    ):
        mock_load_config.return_value = _mock_config(ses_configured=True)

        def lose_response(*args, **kwargs):
            kwargs["before_provider_call"]()
            raise UncertainEmailDeliveryError("response lost")

        mock_deliver.side_effect = lose_response
        _issue_ticket_login_link(self.registration)
        previous = LoginLinkToken.objects.get(registration=self.registration)

        with self.assertRaises(RuntimeError):
            send_ticket_email(self.registration)

        previous.refresh_from_db()
        self.assertTrue(previous.is_valid)
        self.assertEqual(
            self.registration.login_tokens.filter(expires_at__gt=timezone.now()).count(),
            2,
        )

    @patch("apps.event.services.ticket.mail.deliver_email")
    @patch("apps.event.services.ticket.mail._load_config")
    def test_clears_previous_error_on_success(self, mock_load_config, mock_deliver):
        mock_load_config.return_value = _mock_config(ses_configured=True)
        mock_deliver.return_value = DeliveryResult(provider="ses", message_id="ticket-1")

        self.registration.ticket_email_error = "Previous failure"
        self.registration.save(update_fields=["ticket_email_error"])

        send_ticket_email(self.registration)

        self.registration.refresh_from_db()
        self.assertEqual(self.registration.ticket_email_error, "")
        self.assertIsNotNone(self.registration.ticket_email_sent_at)

    @patch("apps.event.services.ticket.mail.deliver_email")
    @patch("apps.event.services.ticket.mail._load_config")
    def test_cross_year_range_is_in_email_and_calendar_links(self, mock_load_config, mock_deliver):
        mock_load_config.return_value = _mock_config(ses_configured=True)
        self.event.date = datetime.date(2026, 12, 31)
        self.event.end_date = datetime.date(2027, 1, 2)
        self.event.save(update_fields=["date", "end_date", "updated_at"])

        send_ticket_email(self.registration)

        message = mock_deliver.call_args.args[0]
        html = message.html_body
        calendar = message.attachments[1].content.decode()
        self.assertIn("December 31, 2026–January 2, 2027", html)
        self.assertIn("dates=20261231%2F20270103", html)
        self.assertIn("DTSTART;VALUE=DATE:20261231", calendar)
        self.assertIn("DTEND;VALUE=DATE:20270103", calendar)


class TicketLoginLinkIssuanceTest(TestCase):
    """Ticket emails issue unified LoginLinkToken rows scoped to the registration."""

    def setUp(self):
        self.member = make_member()
        self.event = make_event()
        self.ticket = Ticket.objects.create(event=self.event, name="GA")
        self.registration = EventRegistration.objects.create(member=self.member, event=self.event, ticket=self.ticket)

    def test_issues_token_bound_to_registration_with_ticket_redirect(self):
        url = _issue_ticket_login_link(self.registration)

        token = LoginLinkToken.objects.get(registration=self.registration)
        self.assertEqual(token.member_id, self.member.pk)
        self.assertIsNone(token.campaign)
        self.assertEqual(token.redirect_path, "/event-registration?event=demo-day")
        self.assertIn(f"/login-link#token={token.token}", url)

    def test_validity_comes_from_event_config(self):
        self.event.ticket_login_validity_days = 5
        self.event.save(update_fields=["ticket_login_validity_days", "updated_at"])

        before = timezone.now() + timedelta(days=5)
        _issue_ticket_login_link(self.registration)
        after = timezone.now() + timedelta(days=5)

        token = LoginLinkToken.objects.get(registration=self.registration)
        self.assertGreaterEqual(token.expires_at, before)
        self.assertLessEqual(token.expires_at, after)

    def test_reissue_revokes_previous_token(self):
        _issue_ticket_login_link(self.registration)
        first = LoginLinkToken.objects.get(registration=self.registration)

        _issue_ticket_login_link(self.registration)

        first.refresh_from_db()
        self.assertTrue(first.is_expired)
        active = self.registration.login_tokens.filter(expires_at__gt=timezone.now())
        self.assertEqual(active.count(), 1)

    def test_reissue_creation_failure_rolls_back_previous_token_revocation(self):
        _issue_ticket_login_link(self.registration)
        previous = LoginLinkToken.objects.get(registration=self.registration)

        with (
            patch(
                "apps.mail.services.tokens.login_links.create_login_link",
                side_effect=RuntimeError("token creation failed"),
            ),
            self.assertRaises(RuntimeError),
        ):
            _issue_ticket_login_link(self.registration)

        previous.refresh_from_db()
        self.assertTrue(previous.is_valid)
        self.assertEqual(
            list(self.registration.login_tokens.values_list("pk", flat=True)),
            [previous.pk],
        )

    def test_returns_empty_string_without_member(self):
        unsaved = EventRegistration(member=None, event=self.event, ticket=self.ticket)
        self.assertEqual(_issue_ticket_login_link(unsaved), "")

    @patch("apps.event.services.ticket.mail.deliver_email")
    @patch("apps.event.services.ticket.mail._load_config")
    def test_send_ticket_email_embeds_login_link(self, mock_load_config, mock_deliver):
        mock_load_config.return_value = _mock_config(ses_configured=True)

        send_ticket_email(self.registration)

        token = LoginLinkToken.objects.get(registration=self.registration)
        html = mock_deliver.call_args.args[0].html_body
        self.assertIn(f"/login-link#token={token.token}", html)

    @patch("apps.event.services.ticket.mail.deliver_email")
    @patch("apps.event.services.ticket.mail._load_config")
    def test_successful_resend_revokes_previous_login_link(self, mock_load_config, mock_deliver):
        mock_load_config.return_value = _mock_config(ses_configured=True)
        mock_deliver.return_value = DeliveryResult(provider="ses", message_id="ticket-1")
        _issue_ticket_login_link(self.registration)
        previous = LoginLinkToken.objects.get(registration=self.registration)

        send_ticket_email(self.registration)

        previous.refresh_from_db()
        self.assertTrue(previous.is_expired)
        active = self.registration.login_tokens.filter(expires_at__gt=timezone.now())
        self.assertEqual(active.count(), 1)

    def test_registration_delete_cascades_tokens(self):
        _issue_ticket_login_link(self.registration)
        self.assertEqual(LoginLinkToken.objects.filter(registration=self.registration).count(), 1)

        registration_id = self.registration.pk
        self.registration.delete()
        self.assertEqual(LoginLinkToken.objects.filter(registration_id=registration_id).count(), 0)


class TicketSendRetryAfterTest(TestCase):
    @patch("apps.event.services.ticket.mail.deliver_email")
    def test_the_provider_error_keeps_the_retry_after_hint(self, deliver):
        deliver.side_effect = TransientEmailDeliveryError("throttled", retry_after=45.0)

        with self.assertRaises(ProviderDeliveryError) as caught:
            _send_via_ses(config=_mock_config(), mime_message=MagicMock(), raise_provider_errors=True)

        self.assertEqual((caught.exception.outcome, caught.exception.retry_after), ("transient", 45.0))
        self.assertIsInstance(caught.exception.__cause__, TransientEmailDeliveryError)

    @patch("apps.event.services.ticket.mail.deliver_email")
    def test_errors_without_a_hint_stay_without_one(self, deliver):
        deliver.side_effect = PermanentEmailDeliveryError("rejected")

        with self.assertRaises(ProviderDeliveryError) as caught:
            _send_via_ses(config=_mock_config(), mime_message=MagicMock(), raise_provider_errors=True)

        self.assertEqual(caught.exception.outcome, "permanent")
        self.assertIsNone(caught.exception.retry_after)


class TicketJobRetryAfterTest(TestCase):
    def setUp(self):
        event = make_event()
        ticket = Ticket.objects.create(event=event, name="GA")
        self.registration = EventRegistration.objects.create(member=make_member(), event=event, ticket=ticket)

    @patch("apps.event.services.ticket.jobs.wait_for_email_slot")
    @patch("apps.event.services.ticket.mail.deliver_email")
    @patch("apps.event.services.ticket.mail._load_config", return_value=_mock_config())
    def test_a_throttled_ticket_job_retries_no_sooner_than_the_provider_asked(self, _config, deliver, _slot):
        deliver.side_effect = TransientEmailDeliveryError("throttled", retry_after=120.0)
        job = MagicMock(payload={"registration_id": str(self.registration.pk)})

        with patch("apps.core.models.BackgroundJob.objects") as jobs:
            jobs.select_for_update.return_value.filter.return_value.exists.return_value = True
            with self.assertRaises(TransientJobError) as caught:
                send_ticket_email_job(job)

        self.assertEqual(caught.exception.retry_after, 120.0)

    @patch("apps.event.services.ticket.mail.deliver_email")
    @patch("apps.event.services.ticket.mail._load_config", return_value=_mock_config())
    def test_a_direct_send_still_reports_a_generic_failure(self, _config, deliver):
        deliver.side_effect = TransientEmailDeliveryError("throttled", retry_after=30.0)

        with self.assertRaises(RuntimeError) as caught:
            send_ticket_email(self.registration)

        self.assertNotIsInstance(caught.exception, ProviderDeliveryError)
        self.registration.refresh_from_db()
        self.assertNotEqual(self.registration.ticket_email_error, "")


class TicketThroughGraphTest(GraphFixtureMixin, TestCase):
    """Through Microsoft Graph the ticket goes as JSON sendMail: no Sent Items copy, barcode still inline."""

    def test_the_ticket_is_json_with_save_to_sent_items_false_and_its_attachments(self):
        event = make_event()
        registration = EventRegistration.objects.create(
            member=make_member(), event=event, ticket=Ticket.objects.create(event=event, name="GA")
        )
        message = _build_ticket_message(registration, config=_mock_config(), login_url="https://i2g.example/l#token=t")

        make_provider().send(message)

        request = self.fake.send_requests[0]
        self.assertEqual(request.headers["Content-Type"], "application/json")
        body = json.loads(request.body)
        self.assertIs(body["saveToSentItems"], False)
        sent = body["message"]
        self.assertIn("https://i2g.example/l#token=t", sent["body"]["content"])
        self.assertIn("cid:ticket-barcode", sent["body"]["content"])
        barcode, calendar = sent["attachments"]
        self.assertEqual(
            {key: barcode[key] for key in ("name", "contentType", "isInline", "contentId")},
            {"name": "ticket-barcode.png", "contentType": "image/png", "isInline": True, "contentId": "ticket-barcode"},
        )
        self.assertEqual(base64.b64decode(barcode["contentBytes"]), message.attachments[0].content)
        self.assertEqual((calendar["name"], calendar["contentType"]), ("event.ics", "text/calendar"))
        self.assertNotIn("isInline", calendar)

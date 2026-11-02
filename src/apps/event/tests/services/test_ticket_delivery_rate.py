"""Ticket emails go through the delivery-rate limiter on the transactional lane, counting both attendee addresses."""

from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.core.models import AWSCredentialConfig, EmailServiceConfig
from apps.core.services.delivery_rates import Lane
from apps.core.tests.services.delivery_rates.helpers import FakeClock, spy_on_email_admissions
from apps.event.services.ticket.mail import send_ticket_email
from apps.event.tests.helpers import make_event, make_member, make_registration, make_ticket


class TicketDeliveryRateTests(TestCase):
    def setUp(self):
        FakeClock(timezone.now()).install(self)
        AWSCredentialConfig.objects.create(
            name="AWS", is_active=True, access_key_id="AKID", secret_access_key="SECRET", default_region="us-west-2"
        )
        EmailServiceConfig.objects.create(name="Mail", is_active=True, provider="ses", from_email="i2g@example.edu")
        patcher = patch("apps.core.services.email.ses.boto3.client")
        patcher.start().return_value.send_raw_email.return_value = {"MessageId": "ses-1"}
        self.addCleanup(patcher.stop)
        event = make_event()
        self.registration = make_registration(
            make_member(email="guest@example.com"),
            event,
            make_ticket(event),
            attendee_email="guest@example.com",
            attendee_secondary_email="guest.other@example.com",
        )

    def test_a_ticket_is_admitted_for_both_addresses_on_the_transactional_lane(self):
        admissions = spy_on_email_admissions(self)

        send_ticket_email(self.registration)

        self.assertEqual(admissions.call_args.kwargs["lane"], Lane.TRANSACTIONAL)
        self.assertEqual(admissions.call_args.kwargs["budget_cost"], 2)
        self.registration.refresh_from_db()
        self.assertIsNotNone(self.registration.ticket_email_sent_at)

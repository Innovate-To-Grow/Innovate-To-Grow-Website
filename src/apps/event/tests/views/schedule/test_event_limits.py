"""Per-member limits on the event endpoints that had none: the phone code check (the shared code-check bucket),
ticket email resends and registrations (each sends an email). Every rate is a live request-limit policy."""

import datetime
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from apps.core.tests.request_limits.helpers import isolate, view_limit
from apps.event.models import EventRegistration, Ticket
from apps.event.tests.helpers import make_event, make_member
from apps.event.throttles import (
    PhoneCodeVerifyThrottle,
    RegistrationCreateThrottle,
    SecondaryEmailCodeVerifyThrottle,
    TicketEmailResendThrottle,
)
from apps.event.views.registration.create import EventRegistrationCreateView
from apps.event.views.registration.sms import VerifyPhoneCodeView
from apps.event.views.registration.tickets import ResendTicketEmailView


class EventLimitTestCase(TestCase):
    def setUp(self):
        cache.clear()
        isolate(self)
        self.client = APIClient()
        self.member = make_member()
        self.client.force_authenticate(self.member)

    def other_client(self, email):
        client = APIClient()
        client.force_authenticate(make_member(email=email))
        return client


@view_limit(**{"view-code-verify": (2, 60)})
class PhoneCodeCheckLimitTests(EventLimitTestCase):
    def test_phone_code_guesses_are_bounded_per_member(self):
        statuses = [self.client.post("/event/verify-phone-code/", {}, format="json").status_code for _ in range(3)]
        self.assertEqual(statuses, [400, 400, 429])
        other = self.other_client("other-phone@example.com")
        self.assertEqual(other.post("/event/verify-phone-code/", {}, format="json").status_code, 400)

    def test_it_shares_the_members_code_check_bucket(self):
        self.client.post("/event/verify-secondary-email-code/", {}, format="json")
        self.client.post("/event/verify-secondary-email-code/", {}, format="json")
        self.assertEqual(self.client.post("/event/verify-phone-code/", {}, format="json").status_code, 429)


@view_limit(**{"view-ticket-email-resend": (2, 3600)})
class TicketResendLimitTests(EventLimitTestCase):
    def setUp(self):
        super().setUp()
        event = make_event(date=datetime.date(2026, 12, 31), end_date=datetime.date(2027, 1, 2))
        ticket = Ticket.objects.create(event=event, name="GA")
        self.registration = EventRegistration.objects.create(member=self.member, event=event, ticket=ticket)

    @patch("apps.event.services.ticket.mail.send_ticket_email")
    def test_resends_are_bounded_per_member(self, send):
        url = f"/event/my-tickets/{self.registration.pk}/resend-email/"
        statuses = [self.client.post(url).status_code for _ in range(3)]
        self.assertEqual(statuses, [200, 200, 429])
        self.assertEqual(send.call_count, 2)


@view_limit(**{"view-registration-create": (2, 3600)})
class RegistrationLimitTests(EventLimitTestCase):
    def test_registrations_are_bounded_per_member(self):
        statuses = [self.client.post("/event/registrations/", {}, format="json").status_code for _ in range(3)]
        self.assertEqual(statuses, [400, 400, 429])
        other = self.other_client("other-reg@example.com")
        self.assertEqual(other.post("/event/registrations/", {}, format="json").status_code, 400)


class EventLimitWiringTests(TestCase):
    def test_each_view_carries_its_limit_and_the_defaults(self):
        self.assertEqual(VerifyPhoneCodeView.throttle_classes, [PhoneCodeVerifyThrottle])
        self.assertEqual(ResendTicketEmailView.throttle_classes, [TicketEmailResendThrottle])
        self.assertEqual(EventRegistrationCreateView.throttle_classes, [RegistrationCreateThrottle])
        self.assertEqual(PhoneCodeVerifyThrottle.scope, SecondaryEmailCodeVerifyThrottle.scope)
        self.assertEqual((RegistrationCreateThrottle().num_requests, RegistrationCreateThrottle().duration), (20, 3600))
        self.assertEqual((TicketEmailResendThrottle().num_requests, TicketEmailResendThrottle().duration), (10, 3600))

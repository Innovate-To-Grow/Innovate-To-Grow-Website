from django.test import TestCase
from rest_framework.test import APIClient

from event.models import EventRegistration, Ticket
from event.tests.helpers import make_event, make_member

# ---------- MyTicketsView ----------


class MyTicketsViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.member = make_member()
        self.event = make_event(is_live=True)
        self.ticket = Ticket.objects.create(event=self.event, name="GA")

    def test_unauthenticated_returns_401(self):
        response = self.client.get("/event/my-tickets/")
        self.assertEqual(response.status_code, 401)

    def test_authenticated_returns_own_tickets(self):
        EventRegistration.objects.create(member=self.member, event=self.event, ticket=self.ticket)
        self.client.force_authenticate(self.member)
        response = self.client.get("/event/my-tickets/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)

    def test_empty_list_when_no_registrations(self):
        self.client.force_authenticate(self.member)
        response = self.client.get("/event/my-tickets/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 0)

    def test_does_not_return_other_users_tickets(self):
        other = make_member(username="other", email="other@example.com")
        EventRegistration.objects.create(member=other, event=self.event, ticket=self.ticket)
        self.client.force_authenticate(self.member)
        response = self.client.get("/event/my-tickets/")
        self.assertEqual(len(response.data), 0)

    def test_response_payload_structure(self):
        EventRegistration.objects.create(member=self.member, event=self.event, ticket=self.ticket)
        self.client.force_authenticate(self.member)
        response = self.client.get("/event/my-tickets/")
        entry = response.data[0]
        self.assertIn("id", entry)
        self.assertIn("ticket_code", entry)
        self.assertIn("event", entry)
        self.assertIn("ticket", entry)
        self.assertIn("barcode_image", entry)

    def test_multiple_registrations_returned(self):
        event2 = make_event(name="Event 2", slug="event-2")
        ticket2 = Ticket.objects.create(event=event2, name="VIP")
        EventRegistration.objects.create(member=self.member, event=self.event, ticket=self.ticket)
        EventRegistration.objects.create(member=self.member, event=event2, ticket=ticket2)
        self.client.force_authenticate(self.member)
        response = self.client.get("/event/my-tickets/")
        self.assertEqual(len(response.data), 2)


# ---------- ResendTicketEmailView ----------


class ResendTicketEmailViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.member = make_member()
        self.event = make_event(is_live=True)
        self.ticket = Ticket.objects.create(event=self.event, name="GA")
        self.registration = EventRegistration.objects.create(member=self.member, event=self.event, ticket=self.ticket)

    def test_unauthenticated_returns_401(self):
        url = f"/event/my-tickets/{self.registration.pk}/resend-email/"
        response = self.client.post(url)
        self.assertEqual(response.status_code, 401)

    def test_returns_501_not_implemented(self):
        self.client.force_authenticate(self.member)
        url = f"/event/my-tickets/{self.registration.pk}/resend-email/"
        response = self.client.post(url)
        self.assertEqual(response.status_code, 501)
        self.assertIn("not configured", response.data["detail"])

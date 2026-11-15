import datetime

from django.test import TestCase
from rest_framework.test import APIClient

from apps.event.models import EventRegistration, Ticket
from apps.event.tests.helpers import make_event, make_member


class EventRegistrationEventsViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_returns_open_events_only(self):
        open_event = make_event(
            name="Open Showcase",
            slug="open-showcase",
            date=datetime.date(2026, 12, 31),
            end_date=datetime.date(2027, 1, 2),
            registration_open=True,
        )
        make_event(name="Closed Showcase", slug="closed-showcase", registration_open=False)

        response = self.client.get("/event/registration-events/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual([event["slug"] for event in response.data], [open_event.slug])
        self.assertEqual(response.data[0]["date"], "2026-12-31")
        self.assertEqual(response.data[0]["end_date"], "2027-01-02")

    def test_returns_events_sorted_by_date_then_name(self):
        later = make_event(
            name="B Showcase",
            slug="b-showcase",
            date=datetime.date(2026, 5, 2),
            registration_open=True,
        )
        earlier = make_event(
            name="A Showcase",
            slug="a-showcase",
            date=datetime.date(2026, 5, 1),
            registration_open=True,
        )

        response = self.client.get("/event/registration-events/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual([event["slug"] for event in response.data], [earlier.slug, later.slug])

    def test_authenticated_user_receives_registration_status(self):
        event = make_event(registration_open=True)
        ticket = Ticket.objects.create(event=event, name="GA")
        member = make_member()
        registration = EventRegistration.objects.create(member=member, event=event, ticket=ticket)
        self.client.force_authenticate(member)

        response = self.client.get("/event/registration-events/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data[0]["registration"]["id"], str(registration.pk))

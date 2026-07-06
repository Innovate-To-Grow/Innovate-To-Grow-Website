import datetime

from django.test import TestCase
from rest_framework.test import APIClient

from apps.authn.models import ContactEmail, ContactPhone
from apps.event.models import EventRegistration, Question, Ticket
from apps.event.tests.helpers import make_event, make_member


class EventRegistrationOptionsViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_no_open_event_returns_404(self):
        response = self.client.get("/event/registration-options/")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data["detail"], "No event is currently accepting registrations.")

    def test_closed_event_returns_404(self):
        make_event(registration_open=False)
        response = self.client.get("/event/registration-options/")
        self.assertEqual(response.status_code, 404)

    def test_open_event_returns_200(self):
        make_event(registration_open=True)
        response = self.client.get("/event/registration-options/")
        self.assertEqual(response.status_code, 200)

    def test_multiple_open_events_without_slug_returns_choose_response(self):
        make_event(name="Spring Showcase", slug="spring-showcase", registration_open=True)
        make_event(name="Fall Showcase", slug="fall-showcase", registration_open=True)
        response = self.client.get("/event/registration-options/")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["detail"], "Please choose an event.")
        self.assertEqual(len(response.data["events"]), 2)

    def test_selected_open_event_returns_options(self):
        make_event(name="Spring Showcase", slug="spring-showcase", registration_open=True)
        event = make_event(name="Fall Showcase", slug="fall-showcase", registration_open=True)
        Ticket.objects.create(event=event, name="GA")
        response = self.client.get("/event/registration-options/", {"event_slug": "fall-showcase"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["slug"], "fall-showcase")
        self.assertEqual(response.data["tickets"][0]["name"], "GA")

    def test_selected_closed_event_returns_404(self):
        make_event(name="Closed Showcase", slug="closed-showcase", registration_open=False)
        response = self.client.get("/event/registration-options/", {"event_slug": "closed-showcase"})
        self.assertEqual(response.status_code, 404)

    def test_response_includes_event_fields(self):
        event = make_event(name="Spring Showcase", registration_open=True)
        response = self.client.get("/event/registration-options/")
        data = response.data
        self.assertEqual(data["name"], "Spring Showcase")
        self.assertEqual(data["slug"], event.slug)
        self.assertEqual(data["location"], event.location)

    def test_response_includes_tickets_array(self):
        event = make_event(registration_open=True)
        Ticket.objects.create(event=event, name="GA")
        response = self.client.get("/event/registration-options/")
        self.assertEqual(len(response.data["tickets"]), 1)
        self.assertEqual(response.data["tickets"][0]["name"], "GA")

    def test_response_includes_questions_array(self):
        event = make_event(registration_open=True)
        Question.objects.create(event=event, text="Role?", order=0)
        response = self.client.get("/event/registration-options/")
        self.assertEqual(len(response.data["questions"]), 1)
        self.assertEqual(response.data["questions"][0]["text"], "Role?")

    def test_anonymous_user_sees_registration_null(self):
        make_event(registration_open=True)
        response = self.client.get("/event/registration-options/")
        self.assertIsNone(response.data["registration"])

    def test_authenticated_user_without_registration_sees_null(self):
        make_event(registration_open=True)
        member = make_member()
        self.client.force_authenticate(member)
        response = self.client.get("/event/registration-options/")
        self.assertIsNone(response.data["registration"])

    def test_authenticated_user_sees_own_registration(self):
        event = make_event(registration_open=True)
        ticket = Ticket.objects.create(event=event, name="GA")
        member = make_member()
        reg = EventRegistration.objects.create(member=member, event=event, ticket=ticket)
        self.client.force_authenticate(member)
        response = self.client.get("/event/registration-options/")
        self.assertIsNotNone(response.data["registration"])
        self.assertEqual(response.data["registration"]["id"], str(reg.pk))

    # ---------- Feature flags + member_emails ----------

    def test_options_include_feature_flags(self):
        make_event(registration_open=True, allow_secondary_email=True, collect_phone=True)
        response = self.client.get("/event/registration-options/")
        self.assertTrue(response.data["allow_secondary_email"])
        self.assertTrue(response.data["collect_phone"])
        self.assertFalse(response.data["verify_phone"])

    def test_options_include_member_emails_when_authenticated(self):
        make_event(registration_open=True)
        member = make_member(email="primary@example.com")
        ContactEmail.objects.create(member=member, email_address="secondary@example.com", email_type="secondary")
        self.client.force_authenticate(member)
        response = self.client.get("/event/registration-options/")
        self.assertEqual(response.data["member_emails"], ["primary@example.com", "secondary@example.com"])

    def test_options_member_emails_empty_when_anonymous(self):
        make_event(registration_open=True)
        response = self.client.get("/event/registration-options/")
        self.assertEqual(response.data["member_emails"], [])

    def test_options_include_member_phone_when_authenticated(self):
        make_event(registration_open=True, collect_phone=True, verify_phone=True)
        member = make_member(email="primary@example.com")
        ContactPhone.objects.create(
            member=member,
            phone_number="5551234567",
            region="1-US",
            verified=True,
        )
        self.client.force_authenticate(member)
        response = self.client.get("/event/registration-options/")
        self.assertEqual(
            response.data["member_phone"],
            {
                "phone_number": "5551234567",
                "region": "1-US",
                "verified": True,
            },
        )


class EventRegistrationEventsViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_returns_open_events_only(self):
        open_event = make_event(name="Open Showcase", slug="open-showcase", registration_open=True)
        make_event(name="Closed Showcase", slug="closed-showcase", registration_open=False)

        response = self.client.get("/event/registration-events/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual([event["slug"] for event in response.data], [open_event.slug])

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

from django.test import TestCase
from rest_framework.test import APIClient

from authn.models import ContactEmail
from event.models import EventRegistration, Question, Ticket
from event.tests.helpers import make_event, make_member


class EventRegistrationOptionsViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_no_live_event_returns_404(self):
        response = self.client.get("/event/registration-options/")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data["detail"], "No live event available.")

    def test_non_live_event_returns_404(self):
        make_event(is_live=False)
        response = self.client.get("/event/registration-options/")
        self.assertEqual(response.status_code, 404)

    def test_live_event_returns_200(self):
        make_event(is_live=True)
        response = self.client.get("/event/registration-options/")
        self.assertEqual(response.status_code, 200)

    def test_response_includes_event_fields(self):
        event = make_event(name="Spring Showcase", is_live=True)
        response = self.client.get("/event/registration-options/")
        data = response.data
        self.assertEqual(data["name"], "Spring Showcase")
        self.assertEqual(data["slug"], event.slug)
        self.assertEqual(data["location"], event.location)

    def test_response_includes_tickets_array(self):
        event = make_event(is_live=True)
        Ticket.objects.create(event=event, name="GA")
        response = self.client.get("/event/registration-options/")
        self.assertEqual(len(response.data["tickets"]), 1)
        self.assertEqual(response.data["tickets"][0]["name"], "GA")

    def test_response_includes_questions_array(self):
        event = make_event(is_live=True)
        Question.objects.create(event=event, text="Role?", order=0)
        response = self.client.get("/event/registration-options/")
        self.assertEqual(len(response.data["questions"]), 1)
        self.assertEqual(response.data["questions"][0]["text"], "Role?")

    def test_anonymous_user_sees_registration_null(self):
        make_event(is_live=True)
        response = self.client.get("/event/registration-options/")
        self.assertIsNone(response.data["registration"])

    def test_authenticated_user_without_registration_sees_null(self):
        make_event(is_live=True)
        member = make_member()
        self.client.force_authenticate(member)
        response = self.client.get("/event/registration-options/")
        self.assertIsNone(response.data["registration"])

    def test_authenticated_user_sees_own_registration(self):
        event = make_event(is_live=True)
        ticket = Ticket.objects.create(event=event, name="GA")
        member = make_member()
        reg = EventRegistration.objects.create(member=member, event=event, ticket=ticket)
        self.client.force_authenticate(member)
        response = self.client.get("/event/registration-options/")
        self.assertIsNotNone(response.data["registration"])
        self.assertEqual(response.data["registration"]["id"], str(reg.pk))

    # ---------- Feature flags + member_emails ----------

    def test_options_include_feature_flags(self):
        make_event(is_live=True, allow_secondary_email=True, collect_phone=True)
        response = self.client.get("/event/registration-options/")
        self.assertTrue(response.data["allow_secondary_email"])
        self.assertTrue(response.data["collect_phone"])
        self.assertFalse(response.data["verify_phone"])

    def test_options_include_member_emails_when_authenticated(self):
        make_event(is_live=True)
        member = make_member(email="primary@example.com")
        ContactEmail.objects.create(member=member, email_address="secondary@example.com", email_type="secondary")
        self.client.force_authenticate(member)
        response = self.client.get("/event/registration-options/")
        self.assertEqual(response.data["member_emails"], ["primary@example.com", "secondary@example.com"])

    def test_options_member_emails_empty_when_anonymous(self):
        make_event(is_live=True)
        response = self.client.get("/event/registration-options/")
        self.assertEqual(response.data["member_emails"], [])

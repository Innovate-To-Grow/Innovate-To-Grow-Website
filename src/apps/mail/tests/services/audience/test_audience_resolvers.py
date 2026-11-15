from django.test import TestCase

from apps.authn.models import ContactEmail
from apps.event.tests.helpers import make_event, make_member, make_registration, make_ticket
from apps.mail.services.audience.resolvers import recipients_for_audience


class SubscribersResolverTests(TestCase):
    def setUp(self):
        self.m1 = make_member(email="alice@example.com", first_name="Alice", last_name="A")
        self.m2 = make_member(email="bob@example.com", first_name="Bob", last_name="B")
        self.m3 = make_member(email="unsub@example.com", first_name="Unsub", last_name="U")
        ContactEmail.objects.filter(member=self.m3).update(subscribe=False)
        ContactEmail.objects.create(
            member=self.m1, email_address="alice2@example.com", email_type="secondary", subscribe=True
        )

    def test_returns_only_subscribed_primary_emails(self):
        result = recipients_for_audience(
            "subscribers", send_all=False, event=None, ticket_uuid_str="", selected_members=None, manual_emails_body=""
        )
        emails = [r["email"] for r in result]
        self.assertIn("alice@example.com", emails)
        self.assertIn("bob@example.com", emails)
        self.assertNotIn("unsub@example.com", emails)
        self.assertNotIn("alice2@example.com", emails)

    def test_send_all_includes_secondary_emails(self):
        result = recipients_for_audience(
            "subscribers", send_all=True, event=None, ticket_uuid_str="", selected_members=None, manual_emails_body=""
        )
        emails = [r["email"] for r in result]
        self.assertIn("alice@example.com", emails)
        self.assertIn("alice2@example.com", emails)


class EventRegistrantsResolverTests(TestCase):
    def setUp(self):
        self.m1 = make_member(email="reg1@example.com", first_name="Reg", last_name="One")
        self.event = make_event(name="Gala")
        self.ticket = make_ticket(self.event)
        make_registration(
            self.m1,
            self.event,
            self.ticket,
            attendee_email="custom@example.com",
            attendee_first_name="Custom",
            attendee_last_name="Name",
        )

    def test_returns_registrants_for_event(self):
        result = recipients_for_audience(
            "event_registrants",
            send_all=False,
            event=self.event,
            ticket_uuid_str="",
            selected_members=None,
            manual_emails_body="",
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["email"], "custom@example.com")

    def test_returns_empty_when_event_is_none(self):
        result = recipients_for_audience(
            "event_registrants",
            send_all=False,
            event=None,
            ticket_uuid_str="",
            selected_members=None,
            manual_emails_body="",
        )
        self.assertEqual(result, [])

    def test_uses_attendee_email_when_set(self):
        result = recipients_for_audience(
            "event_registrants",
            send_all=False,
            event=self.event,
            ticket_uuid_str="",
            selected_members=None,
            manual_emails_body="",
        )
        self.assertEqual(result[0]["email"], "custom@example.com")

    def test_falls_back_to_member_primary_email(self):
        m2 = make_member(email="primary@example.com", first_name="Primary", last_name="User")
        make_registration(m2, self.event, self.ticket, attendee_email="", attendee_first_name="", attendee_last_name="")
        result = recipients_for_audience(
            "event_registrants",
            send_all=False,
            event=self.event,
            ticket_uuid_str="",
            selected_members=None,
            manual_emails_body="",
        )
        emails = [r["email"] for r in result]
        self.assertIn("primary@example.com", emails)


class TicketTypeResolverTests(TestCase):
    def setUp(self):
        self.m1 = make_member(email="t1@example.com", first_name="T1", last_name="M")
        self.m2 = make_member(email="t2@example.com", first_name="T2", last_name="M")
        self.event = make_event(name="Conference")
        self.ticket_a = make_ticket(self.event, name="VIP")
        self.ticket_b = make_ticket(self.event, name="GA")
        make_registration(self.m1, self.event, self.ticket_a, attendee_email="t1@example.com")
        make_registration(self.m2, self.event, self.ticket_b, attendee_email="t2@example.com")

    def test_returns_registrations_for_specified_ticket(self):
        result = recipients_for_audience(
            "ticket_type",
            send_all=False,
            event=self.event,
            ticket_uuid_str=str(self.ticket_a.pk),
            selected_members=None,
            manual_emails_body="",
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["email"], "t1@example.com")

    def test_returns_empty_when_event_is_none(self):
        result = recipients_for_audience(
            "ticket_type",
            send_all=False,
            event=None,
            ticket_uuid_str=str(self.ticket_a.pk),
            selected_members=None,
            manual_emails_body="",
        )
        self.assertEqual(result, [])

    def test_returns_empty_when_ticket_id_empty(self):
        result = recipients_for_audience(
            "ticket_type",
            send_all=False,
            event=self.event,
            ticket_uuid_str="",
            selected_members=None,
            manual_emails_body="",
        )
        self.assertEqual(result, [])

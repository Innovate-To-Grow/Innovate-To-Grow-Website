from django.test import TestCase

from apps.authn.models import ContactEmail, Member
from apps.event.tests.helpers import make_event, make_member, make_registration, make_ticket
from apps.mail.services.audience.converters import (
    manual_emails_from_body,
    members_to_recipients,
    registrations_to_recipients,
)
from apps.mail.services.audience.resolvers import recipients_for_audience


class SelectedMembersResolverTests(TestCase):
    def setUp(self):
        self.m1 = make_member(email="sel1@example.com", first_name="Sel", last_name="One")
        self.m2 = make_member(email="sel2@example.com", first_name="Sel", last_name="Two")
        make_member(email="other@example.com", first_name="Other", last_name="M")

    def test_returns_selected_members_only(self):
        selected = Member.objects.filter(pk__in=[self.m1.pk, self.m2.pk])
        result = recipients_for_audience(
            "selected_members",
            send_all=False,
            event=None,
            ticket_uuid_str="",
            selected_members=selected,
            manual_emails_body="",
        )
        emails = [r["email"] for r in result]
        self.assertIn("sel1@example.com", emails)
        self.assertIn("sel2@example.com", emails)
        self.assertNotIn("other@example.com", emails)


class ManualEmailsTests(TestCase):
    def test_parses_one_email_per_line(self):
        result = manual_emails_from_body("a@b.com\nc@d.com")
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["email"], "a@b.com")
        self.assertEqual(result[1]["email"], "c@d.com")

    def test_strips_whitespace(self):
        result = manual_emails_from_body("  a@b.com  \n  c@d.com  ")
        self.assertEqual(result[0]["email"], "a@b.com")

    def test_skips_empty_lines(self):
        result = manual_emails_from_body("a@b.com\n\n\nc@d.com")
        self.assertEqual(len(result), 2)

    def test_deduplicates_emails(self):
        result = manual_emails_from_body("a@b.com\na@b.com")
        self.assertEqual(len(result), 1)

    def test_returns_empty_for_empty_body(self):
        self.assertEqual(manual_emails_from_body(""), [])
        self.assertEqual(manual_emails_from_body(None), [])

    def test_member_id_is_none_for_manual(self):
        result = manual_emails_from_body("x@y.com")
        self.assertIsNone(result[0]["member_id"])


class MembersToRecipientsTests(TestCase):
    def setUp(self):
        self.m1 = make_member(email="m1@example.com", first_name="M1", last_name="Last")
        ContactEmail.objects.create(
            member=self.m1, email_address="m1alt@example.com", email_type="secondary", subscribe=True
        )
        self.m2 = make_member(email="m2@example.com", first_name="M2", last_name="Last")

    def test_primary_only_returns_one_per_member(self):
        result = members_to_recipients(Member.objects.filter(pk__in=[self.m1.pk, self.m2.pk]), send_all=False)
        emails = [r["email"] for r in result]
        self.assertIn("m1@example.com", emails)
        self.assertIn("m2@example.com", emails)
        self.assertNotIn("m1alt@example.com", emails)

    def test_send_all_returns_all_contact_emails(self):
        result = members_to_recipients(Member.objects.filter(pk=self.m1.pk), send_all=True)
        emails = [r["email"] for r in result]
        self.assertIn("m1@example.com", emails)
        self.assertIn("m1alt@example.com", emails)

    def test_does_not_duplicate_when_member_appears_in_queryset(self):
        qs = Member.objects.filter(pk__in=[self.m1.pk, self.m2.pk])
        result = members_to_recipients(qs, send_all=False)
        emails = [r["email"] for r in result]
        self.assertEqual(len(emails), len(set(emails)))

    def test_result_dict_structure(self):
        result = members_to_recipients(Member.objects.filter(pk=self.m1.pk), send_all=False)
        self.assertEqual(set(result[0].keys()), {"member_id", "email", "first_name", "last_name", "full_name"})


class RegistrationsToRecipientsTests(TestCase):
    def setUp(self):
        self.m1 = make_member(email="mem@example.com", first_name="Mem", last_name="Ber")
        self.event = make_event(name="Expo")
        self.ticket = make_ticket(self.event)

    def test_uses_attendee_email_when_present(self):
        from apps.event.models import EventRegistration

        make_registration(self.m1, self.event, self.ticket, attendee_email="attendee@example.com")
        result = registrations_to_recipients(EventRegistration.objects.filter(event=self.event))
        self.assertEqual(result[0]["email"], "attendee@example.com")

    def test_falls_back_to_member_primary(self):
        from apps.event.models import EventRegistration

        make_registration(self.m1, self.event, self.ticket, attendee_email="")
        result = registrations_to_recipients(EventRegistration.objects.filter(event=self.event))
        self.assertEqual(result[0]["email"], "mem@example.com")

    def test_deduplicates_by_email(self):
        from apps.event.models import EventRegistration

        m2 = make_member(email="dup@example.com", first_name="Dup", last_name="Two")
        make_registration(self.m1, self.event, self.ticket, attendee_email="dup@example.com")
        make_registration(m2, self.event, self.ticket, attendee_email="dup@example.com")
        result = registrations_to_recipients(EventRegistration.objects.filter(event=self.event))
        emails = [r["email"] for r in result]
        self.assertEqual(emails.count("dup@example.com"), 1)

    def test_result_dict_structure(self):
        from apps.event.models import EventRegistration

        make_registration(self.m1, self.event, self.ticket, attendee_email="x@y.com")
        result = registrations_to_recipients(EventRegistration.objects.filter(event=self.event))
        self.assertEqual(set(result[0].keys()), {"member_id", "email", "first_name", "last_name", "full_name"})


class RecipientsForAudienceDispatchTests(TestCase):
    def setUp(self):
        self.m1 = make_member(email="dispatch@example.com", first_name="Dispatch", last_name="Test")

    def test_dispatches_manual_type(self):
        result = recipients_for_audience(
            "manual",
            send_all=False,
            event=None,
            ticket_uuid_str="",
            selected_members=None,
            manual_emails_body="manual@test.com",
        )
        self.assertEqual(result[0]["email"], "manual@test.com")

    def test_unknown_type_returns_empty_list(self):
        result = recipients_for_audience(
            "nonexistent_type",
            send_all=False,
            event=None,
            ticket_uuid_str="",
            selected_members=None,
            manual_emails_body="",
        )
        self.assertEqual(result, [])

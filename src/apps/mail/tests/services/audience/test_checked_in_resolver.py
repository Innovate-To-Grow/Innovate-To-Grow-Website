from django.test import TestCase

from apps.authn.models import ContactEmail
from apps.event.models import CheckIn, CheckInRecord
from apps.event.tests.helpers import make_event, make_member, make_registration, make_ticket
from apps.mail.services.audience.resolvers import recipients_for_audience


class CheckedInResolverTests(TestCase):
    def setUp(self):
        self.m1 = make_member(email="checked@example.com", first_name="Checked", last_name="In")
        self.m2 = make_member(email="notchecked@example.com", first_name="Not", last_name="Checked")
        self.event = make_event(name="Workshop")
        self.ticket = make_ticket(self.event)
        self.reg1 = make_registration(self.m1, self.event, self.ticket, attendee_email="checked@example.com")
        self.reg2 = make_registration(self.m2, self.event, self.ticket, attendee_email="notchecked@example.com")
        self.checkin = CheckIn.objects.create(event=self.event, name="Main")
        CheckInRecord.objects.create(check_in=self.checkin, registration=self.reg1)

    def test_returns_only_checked_in_registrations(self):
        result = recipients_for_audience(
            "checked_in",
            send_all=False,
            event=self.event,
            ticket_uuid_str="",
            selected_members=None,
            manual_emails_body="",
        )
        emails = [r["email"] for r in result]
        self.assertIn("checked@example.com", emails)
        self.assertNotIn("notchecked@example.com", emails)

    def test_returns_empty_when_no_checkins(self):
        CheckInRecord.objects.all().delete()
        result = recipients_for_audience(
            "checked_in",
            send_all=False,
            event=self.event,
            ticket_uuid_str="",
            selected_members=None,
            manual_emails_body="",
        )
        self.assertEqual(result, [])

    def test_returns_empty_when_event_is_none(self):
        result = recipients_for_audience(
            "checked_in",
            send_all=False,
            event=None,
            ticket_uuid_str="",
            selected_members=None,
            manual_emails_body="",
        )
        self.assertEqual(result, [])


class NotCheckedInResolverTests(TestCase):
    def setUp(self):
        self.m1 = make_member(email="present@example.com", first_name="Present", last_name="P")
        self.m2 = make_member(email="absent@example.com", first_name="Absent", last_name="A")
        self.event = make_event(name="Meetup")
        self.ticket = make_ticket(self.event)
        self.reg1 = make_registration(self.m1, self.event, self.ticket, attendee_email="present@example.com")
        self.reg2 = make_registration(self.m2, self.event, self.ticket, attendee_email="absent@example.com")
        self.checkin = CheckIn.objects.create(event=self.event, name="Door")
        CheckInRecord.objects.create(check_in=self.checkin, registration=self.reg1)

    def test_returns_only_unchecked_registrations(self):
        result = recipients_for_audience(
            "not_checked_in",
            send_all=False,
            event=self.event,
            ticket_uuid_str="",
            selected_members=None,
            manual_emails_body="",
        )
        emails = [r["email"] for r in result]
        self.assertIn("absent@example.com", emails)
        self.assertNotIn("present@example.com", emails)

    def test_returns_all_when_no_checkins_exist(self):
        CheckInRecord.objects.all().delete()
        result = recipients_for_audience(
            "not_checked_in",
            send_all=False,
            event=self.event,
            ticket_uuid_str="",
            selected_members=None,
            manual_emails_body="",
        )
        self.assertEqual(len(result), 2)

    def test_returns_empty_when_event_is_none(self):
        result = recipients_for_audience(
            "not_checked_in",
            send_all=False,
            event=None,
            ticket_uuid_str="",
            selected_members=None,
            manual_emails_body="",
        )
        self.assertEqual(result, [])


class AllMembersResolverTests(TestCase):
    def setUp(self):
        self.active = make_member(email="active@example.com", first_name="Active", last_name="M")
        self.inactive = make_member(email="inactive@example.com", first_name="Inactive", last_name="M")
        self.inactive.is_active = False
        self.inactive.save()

    def test_returns_only_active_members(self):
        result = recipients_for_audience(
            "all_members",
            send_all=False,
            event=None,
            ticket_uuid_str="",
            selected_members=None,
            manual_emails_body="",
        )
        emails = [r["email"] for r in result]
        self.assertIn("active@example.com", emails)
        self.assertNotIn("inactive@example.com", emails)

    def test_send_all_includes_secondary_emails(self):
        ContactEmail.objects.create(
            member=self.active, email_address="active2@example.com", email_type="secondary", subscribe=True
        )
        result = recipients_for_audience(
            "all_members",
            send_all=True,
            event=None,
            ticket_uuid_str="",
            selected_members=None,
            manual_emails_body="",
        )
        emails = [r["email"] for r in result]
        self.assertIn("active@example.com", emails)
        self.assertIn("active2@example.com", emails)


class StaffResolverTests(TestCase):
    def setUp(self):
        self.staff_active = make_member(email="staff@example.com", first_name="Staff", last_name="Active")
        self.staff_active.is_staff = True
        self.staff_active.save()
        self.staff_inactive = make_member(email="staff2@example.com", first_name="Staff", last_name="Inactive")
        self.staff_inactive.is_staff = True
        self.staff_inactive.is_active = False
        self.staff_inactive.save()
        self.non_staff = make_member(email="nope@example.com", first_name="Not", last_name="Staff")

    def test_returns_only_active_staff(self):
        result = recipients_for_audience(
            "staff", send_all=False, event=None, ticket_uuid_str="", selected_members=None, manual_emails_body=""
        )
        emails = [r["email"] for r in result]
        self.assertIn("staff@example.com", emails)
        self.assertNotIn("staff2@example.com", emails)
        self.assertNotIn("nope@example.com", emails)

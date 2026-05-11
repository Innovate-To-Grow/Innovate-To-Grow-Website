from django.test import TestCase

from authn.models import ContactEmail, Member
from event.models import CheckIn, CheckInRecord
from event.tests.helpers import make_event, make_member, make_registration, make_ticket
from mail.models import EmailCampaign
from mail.services.audience import get_recipients
from mail.services.audience.converters import (
    manual_emails_from_body,
    members_to_recipients,
    registrations_to_recipients,
)
from mail.services.audience.resolvers import recipients_for_audience


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
        from event.models import EventRegistration

        make_registration(self.m1, self.event, self.ticket, attendee_email="attendee@example.com")
        result = registrations_to_recipients(EventRegistration.objects.filter(event=self.event))
        self.assertEqual(result[0]["email"], "attendee@example.com")

    def test_falls_back_to_member_primary(self):
        from event.models import EventRegistration

        make_registration(self.m1, self.event, self.ticket, attendee_email="")
        result = registrations_to_recipients(EventRegistration.objects.filter(event=self.event))
        self.assertEqual(result[0]["email"], "mem@example.com")

    def test_deduplicates_by_email(self):
        from event.models import EventRegistration

        m2 = make_member(email="dup@example.com", first_name="Dup", last_name="Two")
        make_registration(self.m1, self.event, self.ticket, attendee_email="dup@example.com")
        make_registration(m2, self.event, self.ticket, attendee_email="dup@example.com")
        result = registrations_to_recipients(EventRegistration.objects.filter(event=self.event))
        emails = [r["email"] for r in result]
        self.assertEqual(emails.count("dup@example.com"), 1)

    def test_result_dict_structure(self):
        from event.models import EventRegistration

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


class GetRecipientsExclusionTests(TestCase):
    def setUp(self):
        self.m1 = make_member(email="keep@example.com", first_name="Keep", last_name="Me")
        self.m2 = make_member(email="exclude@example.com", first_name="Exclude", last_name="Me")
        self.m2.is_staff = True
        self.m2.save()

    def test_exclusion_removes_matching_emails(self):
        campaign = EmailCampaign.objects.create(
            subject="Test",
            body="body",
            audience_type="all_members",
            member_email_scope="primary",
            exclude_audience_type="staff",
            exclude_member_email_scope="primary",
        )
        result = get_recipients(campaign)
        emails = [r["email"] for r in result]
        self.assertIn("keep@example.com", emails)
        self.assertNotIn("exclude@example.com", emails)

    def test_no_exclusion_returns_all(self):
        campaign = EmailCampaign.objects.create(
            subject="Test",
            body="body",
            audience_type="all_members",
            member_email_scope="primary",
            exclude_audience_type="",
        )
        result = get_recipients(campaign)
        emails = [r["email"] for r in result]
        self.assertIn("keep@example.com", emails)
        self.assertIn("exclude@example.com", emails)

    def test_exclusion_is_case_insensitive(self):
        ContactEmail.objects.filter(member=self.m2).update(email_address="EXCLUDE@EXAMPLE.COM")
        campaign = EmailCampaign.objects.create(
            subject="Test",
            body="body",
            audience_type="manual",
            manual_emails="exclude@example.com\nkeep@example.com",
            exclude_audience_type="staff",
            exclude_member_email_scope="primary",
        )
        result = get_recipients(campaign)
        emails = [r["email"] for r in result]
        self.assertNotIn("exclude@example.com", emails)
        self.assertIn("keep@example.com", emails)

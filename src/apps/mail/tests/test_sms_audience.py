from django.test import TestCase

from apps.authn.models import ContactPhone
from apps.event.models import CheckIn, CheckInRecord
from apps.event.tests.helpers import make_event, make_member, make_registration, make_ticket
from apps.mail.models import SmsCampaign
from apps.mail.services.sms_audience import (
    get_sms_recipients,
    manual_sms_recipients_from_body,
    recipients_for_sms_audience,
)


def _add_phone(member, number, *, subscribe=True, verified=True):
    return ContactPhone.objects.create(
        member=member,
        phone_number=number,
        region="1-US",
        subscribe=subscribe,
        verified=verified,
    )


class SmsAudienceResolverTests(TestCase):
    def test_default_policy_returns_verified_opt_in_phone_only(self):
        opted_in = make_member(email="opt@example.com", first_name="Opt", last_name="In")
        not_subscribed = make_member(email="nosub@example.com", first_name="No", last_name="Sub")
        unverified = make_member(email="unverified@example.com", first_name="Un", last_name="Verified")
        _add_phone(opted_in, "2095551001", subscribe=True, verified=True)
        _add_phone(not_subscribed, "2095551002", subscribe=False, verified=True)
        _add_phone(unverified, "2095551003", subscribe=True, verified=False)
        campaign = SmsCampaign.objects.create(message="Hello {{first_name}}", audience_type="all_members")

        recipients = get_sms_recipients(campaign)

        self.assertEqual([recipient["phone"] for recipient in recipients], ["+12095551001"])
        self.assertEqual(recipients[0]["full_name"], "Opt In")

    def test_any_verified_policy_includes_unsubscribed_verified_phone(self):
        opted_in = make_member(email="opt@example.com")
        not_subscribed = make_member(email="nosub@example.com")
        _add_phone(opted_in, "2095551001", subscribe=True, verified=True)
        _add_phone(not_subscribed, "2095551002", subscribe=False, verified=True)
        campaign = SmsCampaign.objects.create(
            message="Hello",
            audience_type="all_members",
            phone_policy="any_verified",
        )

        recipients = get_sms_recipients(campaign)

        self.assertEqual({recipient["phone"] for recipient in recipients}, {"+12095551001", "+12095551002"})

    def test_any_verified_event_audience_can_use_verified_registration_phone(self):
        member = make_member(email="event@example.com", first_name="Event", last_name="User")
        event = make_event()
        ticket = make_ticket(event)
        make_registration(
            member,
            event,
            ticket,
            attendee_phone="+12095551004",
            phone_verified=True,
            attendee_first_name="Ticket",
            attendee_last_name="Holder",
        )
        default_campaign = SmsCampaign.objects.create(
            message="Hello",
            audience_type="event_registrants",
            event=event,
        )
        any_verified_campaign = SmsCampaign.objects.create(
            message="Hello",
            audience_type="event_registrants",
            event=event,
            phone_policy="any_verified",
        )

        self.assertEqual(get_sms_recipients(default_campaign), [])
        recipients = get_sms_recipients(any_verified_campaign)
        self.assertEqual(recipients[0]["phone"], "+12095551004")
        self.assertEqual(recipients[0]["full_name"], "Ticket Holder")

    def test_exclusion_removes_matching_phone(self):
        included = make_member(email="included@example.com")
        excluded = make_member(email="excluded@example.com")
        _add_phone(included, "2095551001", subscribe=True, verified=True)
        _add_phone(excluded, "2095551002", subscribe=True, verified=True)
        campaign = SmsCampaign.objects.create(
            message="Hello",
            audience_type="all_members",
            exclude_audience_type="selected_members",
        )
        campaign.exclude_members.add(excluded)

        recipients = get_sms_recipients(campaign)

        self.assertEqual([recipient["phone"] for recipient in recipients], ["+12095551001"])

    def test_manual_phone_audience_deduplicates_e164_numbers(self):
        recipients = manual_sms_recipients_from_body("+12095551001\n+12095551001\ninvalid\n+12095551002")

        self.assertEqual([recipient["phone"] for recipient in recipients], ["+12095551001", "+12095551002"])


class SmsAudienceEventResolverTests(TestCase):
    def setUp(self):
        self.event = make_event()
        self.ticket = make_ticket(self.event, name="GA")
        self.member = make_member(email="evt@example.com", first_name="Evt", last_name="User")
        _add_phone(self.member, "2095551001")
        self.registration = make_registration(self.member, self.event, self.ticket)

    def _campaign(self, **kwargs):
        defaults = {"message": "Hi", "phone_policy": "verified_opt_in"}
        defaults.update(kwargs)
        return SmsCampaign.objects.create(**defaults)

    def test_staff_audience_returns_staff_with_phones(self):
        staff = make_member(email="staff@example.com", first_name="Staff", last_name="Member", is_staff=True)
        _add_phone(staff, "2095551099")
        campaign = self._campaign(audience_type="staff")

        recipients = get_sms_recipients(campaign)

        phones = {r["phone"] for r in recipients}
        self.assertIn("+12095551099", phones)

    def test_event_registrants_returns_registered_members(self):
        campaign = self._campaign(audience_type="event_registrants", event=self.event)

        recipients = get_sms_recipients(campaign)

        self.assertEqual([r["phone"] for r in recipients], ["+12095551001"])

    def test_event_registrants_without_event_returns_empty(self):
        campaign = self._campaign(audience_type="event_registrants", event=None)

        self.assertEqual(get_sms_recipients(campaign), [])

    def test_ticket_type_returns_ticket_holders(self):
        campaign = self._campaign(audience_type="ticket_type", event=self.event, ticket_id=str(self.ticket.pk))

        recipients = get_sms_recipients(campaign)

        self.assertEqual([r["phone"] for r in recipients], ["+12095551001"])

    def test_ticket_type_without_ticket_returns_empty(self):
        campaign = self._campaign(audience_type="ticket_type", event=self.event, ticket_id="")
        # get_sms_recipients passes "" because audience is ticket_type with empty id.
        self.assertEqual(get_sms_recipients(campaign), [])

    def test_checked_in_returns_only_scanned_registrations(self):
        check_in = CheckIn.objects.create(event=self.event, name="Gate")
        CheckInRecord.objects.create(check_in=check_in, registration=self.registration)
        campaign = self._campaign(audience_type="checked_in", event=self.event)

        recipients = get_sms_recipients(campaign)

        self.assertEqual([r["phone"] for r in recipients], ["+12095551001"])

    def test_checked_in_without_event_returns_empty(self):
        result = recipients_for_sms_audience(
            "checked_in",
            phone_policy="verified_opt_in",
            event=None,
            ticket_uuid_str="",
            selected_members=None,
            manual_phones_body="",
        )
        self.assertEqual(result, [])

    def test_not_checked_in_returns_unscanned_registrations(self):
        other = make_member(email="noshow@example.com", first_name="No", last_name="Show")
        _add_phone(other, "2095552002")
        make_registration(other, self.event, self.ticket, attendee_first_name="No", attendee_last_name="Show")
        check_in = CheckIn.objects.create(event=self.event, name="Gate")
        CheckInRecord.objects.create(check_in=check_in, registration=self.registration)
        campaign = self._campaign(audience_type="not_checked_in", event=self.event)

        recipients = get_sms_recipients(campaign)

        phones = {r["phone"] for r in recipients}
        self.assertIn("+12095552002", phones)
        self.assertNotIn("+12095551001", phones)

    def test_not_checked_in_without_event_returns_empty(self):
        result = recipients_for_sms_audience(
            "not_checked_in",
            phone_policy="verified_opt_in",
            event=None,
            ticket_uuid_str="",
            selected_members=None,
            manual_phones_body="",
        )
        self.assertEqual(result, [])

    def test_unknown_audience_returns_empty(self):
        result = recipients_for_sms_audience(
            "nonexistent",
            phone_policy="verified_opt_in",
            event=None,
            ticket_uuid_str="",
            selected_members=None,
            manual_phones_body="",
        )
        self.assertEqual(result, [])

    def test_registration_uses_any_verified_attendee_phone_fallback(self):
        member = make_member(email="att@example.com", first_name="Att", last_name="Endee")
        # No contact phone for the member; the registration carries a verified phone.
        make_registration(
            member,
            self.event,
            self.ticket,
            attendee_phone="+12095553003",
            phone_verified=True,
            attendee_first_name="Att",
            attendee_last_name="Endee",
        )
        campaign = self._campaign(audience_type="event_registrants", event=self.event, phone_policy="any_verified")

        recipients = get_sms_recipients(campaign)

        phones = {r["phone"] for r in recipients}
        self.assertIn("+12095553003", phones)

    def test_members_dedup_skips_duplicate_phone(self):
        from apps.mail.services.sms_audience import members_to_sms_recipients

        # The same member appearing twice exercises the "phone already seen" dedup.
        recipients = members_to_sms_recipients([self.member, self.member], phone_policy="verified_opt_in")

        phone_list = [r["phone"] for r in recipients]
        self.assertEqual(phone_list, ["+12095551001"])

from django.test import TestCase

from apps.authn.models import ContactPhone
from apps.event.tests.helpers import make_event, make_member, make_registration, make_ticket
from apps.mail.models import SmsCampaign
from apps.mail.services.sms_audience import get_sms_recipients, manual_sms_recipients_from_body


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

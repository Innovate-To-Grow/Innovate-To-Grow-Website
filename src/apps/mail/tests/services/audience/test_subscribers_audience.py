"""The per-address ``ContactEmail.subscribe`` flag is authoritative for the "subscribers" audience."""

import importlib
from unittest.mock import patch

from django.apps import apps as global_apps
from django.core.cache import cache
from django.db import connection
from django.test import TestCase
from rest_framework.test import APITestCase

from apps.authn.models import ContactEmail, Member
from apps.authn.services.contacts.contact_emails import delete_contact_email, make_contact_email_primary
from apps.event.services.registration.sync_email import sync_secondary_email_to_account
from apps.event.tests.helpers import make_member
from apps.mail.admin.campaign.forms import SUBSCRIBERS_SCOPE_NOTE, EmailCampaignForm
from apps.mail.models import EmailCampaign
from apps.mail.services.audience import get_recipients
from apps.mail.services.audience.resolvers import recipients_for_audience
from apps.mail.services.campaign.preview import render_email_html
from apps.mail.services.tokens.unsubscribe import build_oneclick_unsubscribe_token

_carry_primary_opt_out = importlib.import_module(
    "apps.mail.migrations.0019_carry_primary_opt_out_to_all_addresses"
).carry_primary_opt_out


def _subscriber_emails(*, send_all):
    recipients = recipients_for_audience(
        "subscribers",
        send_all=send_all,
        event=None,
        ticket_uuid_str="",
        selected_members=None,
        manual_emails_body="",
    )
    return [recipient["email"] for recipient in recipients]


def _add_email(member, address, email_type, *, subscribe, verified=True):
    return ContactEmail.objects.create(
        member=member, email_address=address, email_type=email_type, subscribe=subscribe, verified=verified
    )


class SubscribersPerAddressTests(TestCase):
    def setUp(self):
        cache.clear()
        # Primary subscribed, secondary unsubscribed, other subscribed.
        self.mixed = make_member(email="mixed@example.com", first_name="Mixed")
        _add_email(self.mixed, "mixed-2@example.com", "secondary", subscribe=False)
        _add_email(self.mixed, "mixed-3@example.com", "other", subscribe=True)
        # Primary unsubscribed (from /account), secondary still subscribed.
        self.secondary_only = make_member(email="sec-only@example.com", first_name="Secondary")
        ContactEmail.objects.filter(member=self.secondary_only).update(subscribe=False)
        _add_email(self.secondary_only, "sec-only-2@example.com", "secondary", subscribe=True)
        # Nothing subscribed.
        self.opted_out = make_member(email="out@example.com", first_name="Out")
        _add_email(self.opted_out, "out-2@example.com", "secondary", subscribe=False)
        ContactEmail.objects.filter(member=self.opted_out).update(subscribe=False)

    def test_scope_primary_mails_only_a_subscribed_primary(self):
        self.assertCountEqual(_subscriber_emails(send_all=False), ["mixed@example.com"])

    def test_scope_all_mails_every_subscribed_address_and_nothing_else(self):
        self.assertCountEqual(
            _subscriber_emails(send_all=True),
            ["mixed@example.com", "mixed-3@example.com", "sec-only-2@example.com"],
        )

    def test_inactive_members_are_excluded(self):
        Member.objects.filter(pk=self.mixed.pk).update(is_active=False)

        self.assertEqual(_subscriber_emails(send_all=False), [])
        self.assertCountEqual(_subscriber_emails(send_all=True), ["sec-only-2@example.com"])

    def test_unverified_addresses_are_included(self):
        """Excel import creates addresses with verified=False; they are still real subscribers."""
        imported = Member.objects.create_user(password="x", first_name="Imported")
        _add_email(imported, "imported@example.com", "primary", subscribe=True, verified=False)

        self.assertIn("imported@example.com", _subscriber_emails(send_all=False))

    def test_recipient_shape_is_unchanged(self):
        recipients = recipients_for_audience(
            "subscribers", send_all=False, event=None, ticket_uuid_str="", selected_members=None, manual_emails_body=""
        )

        self.assertEqual(
            recipients,
            [
                {
                    "member_id": self.mixed.pk,
                    "email": "mixed@example.com",
                    "first_name": "Mixed",
                    "last_name": "",
                    "full_name": "Mixed",
                }
            ],
        )

    def test_resolver_runs_a_fixed_number_of_queries(self):
        for index in range(5):
            member = make_member(email=f"bulk-{index}@example.com")
            _add_email(member, f"bulk-{index}-2@example.com", "secondary", subscribe=False)

        for send_all in (False, True):
            with self.subTest(send_all=send_all), self.assertNumQueries(2):  # members + contact_emails prefetch
                _subscriber_emails(send_all=send_all)

    def test_other_audiences_still_ignore_the_flag(self):
        emails = [
            recipient["email"]
            for recipient in recipients_for_audience(
                "all_members",
                send_all=True,
                event=None,
                ticket_uuid_str="",
                selected_members=None,
                manual_emails_body="",
            )
        ]

        self.assertIn("out@example.com", emails)
        self.assertIn("mixed-2@example.com", emails)


class SubscribersExclusionTests(TestCase):
    def setUp(self):
        cache.clear()
        self.member = make_member(email="excl@example.com")
        ContactEmail.objects.filter(member=self.member).update(subscribe=False)
        _add_email(self.member, "excl-2@example.com", "secondary", subscribe=True)
        self.subscriber = make_member(email="sub@example.com")

    def _campaign(self, **overrides):
        fields = {
            "subject": "Blast",
            "body": "Hello",
            "audience_type": "all_members",
            "member_email_scope": "all",
            "exclude_audience_type": "subscribers",
        }
        fields.update(overrides)
        return EmailCampaign.objects.create(**fields)

    def test_excluding_subscribers_with_scope_all_removes_only_subscribed_addresses(self):
        emails = {r["email"] for r in get_recipients(self._campaign(exclude_member_email_scope="all"))}

        self.assertEqual(emails, {"excl@example.com"})

    def test_excluding_subscribers_with_scope_primary_removes_only_subscribed_primaries(self):
        emails = {r["email"] for r in get_recipients(self._campaign(exclude_member_email_scope="primary"))}

        self.assertEqual(emails, {"excl@example.com", "excl-2@example.com"})

    def test_subscribers_minus_primary_subscribers_leaves_other_subscribed_addresses(self):
        campaign = self._campaign(audience_type="subscribers", exclude_member_email_scope="primary")

        self.assertEqual({r["email"] for r in get_recipients(campaign)}, {"excl-2@example.com"})


class UnsubscribeSurvivesContactEmailChangesTests(APITestCase):
    """After a one-click unsubscribe, reshuffling the member's addresses must not re-subscribe them."""

    def setUp(self):
        cache.clear()
        task_patcher = patch("apps.mail.services.tokens.notifications.start_in_process_task")
        task_patcher.start()
        self.addCleanup(task_patcher.stop)
        self.member = make_member(email="reshuffle@example.com")
        self.primary = ContactEmail.objects.get(member=self.member, email_type="primary")
        self.secondary = _add_email(self.member, "reshuffle-2@example.com", "secondary", subscribe=True)
        self.other = _add_email(self.member, "reshuffle-3@example.com", "other", subscribe=True)
        self.assertIn("reshuffle@example.com", _subscriber_emails(send_all=False))

        response = self.client.post(f"/mail/unsubscribe/{build_oneclick_unsubscribe_token(self.member)}/")
        self.assertEqual(response.status_code, 200)

    def _assert_not_a_subscriber(self):
        for send_all in (False, True):
            with self.subTest(send_all=send_all):
                emails = _subscriber_emails(send_all=send_all)
                self.assertFalse([email for email in emails if email.startswith("reshuffle")], emails)

    def test_unsubscribe_removes_the_member_from_both_scopes(self):
        self._assert_not_a_subscriber()

    def test_make_primary_does_not_resubscribe(self):
        make_contact_email_primary(member=self.member, contact_email_id=self.secondary.pk)

        self.secondary.refresh_from_db()
        self.assertEqual(self.secondary.email_type, "primary")
        self._assert_not_a_subscriber()

    def test_deleting_the_primary_does_not_resubscribe(self):
        delete_contact_email(member=self.member, contact_email_id=self.primary.pk)

        self.assertEqual(ContactEmail.objects.get(member=self.member, email_type="primary").pk, self.secondary.pk)
        self._assert_not_a_subscriber()

    def test_event_registration_email_does_not_resubscribe(self):
        sync_secondary_email_to_account(self.member, "reshuffle-event@example.com", verified=True)

        self.assertFalse(ContactEmail.objects.get(email_address="reshuffle-event@example.com").subscribe)
        self._assert_not_a_subscriber()

    def test_turning_one_address_back_on_mails_only_that_address(self):
        ContactEmail.objects.filter(pk=self.other.pk).update(subscribe=True)

        self.assertFalse([e for e in _subscriber_emails(send_all=False) if e.startswith("reshuffle")])
        self.assertIn("reshuffle-3@example.com", _subscriber_emails(send_all=True))


class EventRegistrationEmailSubscriptionTests(TestCase):
    """An address an event registration adds follows the member's newsletter choice."""

    def setUp(self):
        cache.clear()

    def test_address_of_a_subscribed_member_is_subscribed(self):
        member = make_member(email="reg@example.com")
        ContactEmail.objects.filter(member=member).update(subscribe=False)
        _add_email(member, "reg-other@example.com", "other", subscribe=True)

        sync_secondary_email_to_account(member, "reg-event@example.com")

        self.assertTrue(ContactEmail.objects.get(email_address="reg-event@example.com").subscribe)
        self.assertIn("reg-event@example.com", _subscriber_emails(send_all=True))

    def test_address_of_an_unsubscribed_member_is_not_subscribed(self):
        member = make_member(email="reg-out@example.com")
        ContactEmail.objects.filter(member=member).update(subscribe=False)

        sync_secondary_email_to_account(member, "reg-out-event@example.com")

        self.assertFalse(ContactEmail.objects.get(email_address="reg-out-event@example.com").subscribe)
        self.assertNotIn("reg-out-event@example.com", _subscriber_emails(send_all=True))


class CarryPrimaryOptOutMigrationTests(TestCase):
    """``mail.0019`` keeps everyone who opted out under the old primary-only rule out of the new audience."""

    def setUp(self):
        cache.clear()

    @staticmethod
    def _run_migration():
        _carry_primary_opt_out(global_apps, connection.schema_editor())

    @staticmethod
    def _flags(member):
        return {row.email_address: row.subscribe for row in ContactEmail.objects.filter(member=member)}

    def test_primary_opt_out_turns_off_the_other_addresses(self):
        # What the old one-click link and /account primary toggle left behind: only the primary row cleared.
        legacy = make_member(email="legacy@example.com")
        ContactEmail.objects.filter(member=legacy).update(subscribe=False)
        _add_email(legacy, "legacy-2@example.com", "secondary", subscribe=True)
        _add_email(legacy, "legacy-3@example.com", "other", subscribe=True)
        self.assertCountEqual(_subscriber_emails(send_all=True), ["legacy-2@example.com", "legacy-3@example.com"])

        self._run_migration()

        self.assertEqual(
            self._flags(legacy),
            {"legacy@example.com": False, "legacy-2@example.com": False, "legacy-3@example.com": False},
        )
        self.assertEqual(_subscriber_emails(send_all=True), [])

    def test_subscribed_primary_and_other_flags_are_kept(self):
        subscriber = make_member(email="keep@example.com")
        _add_email(subscriber, "keep-2@example.com", "secondary", subscribe=False)
        _add_email(subscriber, "keep-3@example.com", "other", subscribe=True)
        no_primary = Member.objects.create_user(password="x", first_name="NoPrimary")
        _add_email(no_primary, "np@example.com", "secondary", subscribe=True)
        anonymous = ContactEmail.objects.create(email_address="anon@example.com", email_type="primary", subscribe=False)
        before = {member.pk: self._flags(member) for member in (subscriber, no_primary)}

        self._run_migration()
        self._run_migration()  # idempotent

        self.assertEqual({member.pk: self._flags(member) for member in (subscriber, no_primary)}, before)
        anonymous.refresh_from_db()
        self.assertFalse(anonymous.subscribe)


class CampaignFooterTests(TestCase):
    def test_footer_is_neutral_and_labels_the_newsletter_unsubscribe(self):
        html = render_email_html("Hello", unsubscribe_url="https://api.example.com/mail/unsubscribe/t/")

        self.assertNotIn("because you are subscribed", html)
        self.assertIn("Unsubscribe from newsletters</a>", html)
        self.assertIn('href="https://api.example.com/mail/unsubscribe/t/"', html)

    def test_footer_without_unsubscribe_url_has_no_link(self):
        html = render_email_html("Hello")

        self.assertNotIn("Unsubscribe from newsletters", html)
        self.assertNotIn("because you are subscribed", html)


class CampaignFormScopeHelpTests(TestCase):
    def test_send_to_help_explains_subscriber_addresses(self):
        form = EmailCampaignForm()

        self.assertTrue(form.fields["member_email_scope"].help_text.endswith(SUBSCRIBERS_SCOPE_NOTE))
        # The model's help text (and so the migration state) is untouched.
        self.assertNotIn(SUBSCRIBERS_SCOPE_NOTE, EmailCampaign._meta.get_field("member_email_scope").help_text)

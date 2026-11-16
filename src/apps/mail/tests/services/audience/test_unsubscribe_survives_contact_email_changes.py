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
from apps.mail.admin.campaign.forms import EmailCampaignForm
from apps.mail.models import EmailCampaign
from apps.mail.services.campaign.preview import render_email_html
from apps.mail.services.tokens.unsubscribe import build_oneclick_unsubscribe_token
from apps.mail.tests.services.audience.test_subscribers_audience import (
    _add_email,
    _carry_primary_opt_out,
    _subscriber_emails,
)


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

        help_text = form.fields["member_email_scope"].help_text
        self.assertIn(
            "For All subscribers, only the addresses that are themselves subscribed receive the email", help_text
        )
        self.assertEqual(help_text, EmailCampaign._meta.get_field("member_email_scope").help_text)

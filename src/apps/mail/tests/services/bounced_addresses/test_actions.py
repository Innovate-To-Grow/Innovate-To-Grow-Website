"""Bounced-address actions on queue state, suppression and contact emails: each effect, its audit row and history
line, the reversible ones reversed, and every guard."""

from unittest.mock import patch

from django.contrib.admin.models import LogEntry
from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.authn.models import ContactEmail, ContactPhone
from apps.event.tests.helpers import make_admin, make_superuser
from apps.mail.models import BouncedAddress, BouncedAddressAction, EmailCampaign
from apps.mail.services.audience import get_recipients
from apps.mail.services.email_monitoring.addresses.actions import ActionRefused, StaleConfirmation, apply_action
from apps.mail.services.email_monitoring.addresses.guards import NEEDS_AUTHN, PRIVILEGED, fingerprint, load_target

from .helpers import add_email, make_person, make_row, request_for

Action = BouncedAddressAction.Action
Role = BouncedAddress.Role
Status = BouncedAddress.Status


def apply(user, row, action, **values):
    """Apply ``action`` as ``user`` after "seeing" the current state (as the confirmation page does)."""
    row.refresh_from_db()
    seen = fingerprint(load_target(row))
    return apply_action(request_for(user), row.pk, action, seen=seen, values=values)


def history(obj) -> list[str]:
    return list(LogEntry.objects.filter(object_id=str(obj.pk)).values_list("change_message", flat=True))


class ActionTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.master = make_superuser()
        self.mail_only = make_admin(apps=["mail"], email="mailstaff@example.org")
        self.mail_authn = make_admin(apps=["mail", "authn"], email="memberstaff@example.org")

    def assert_refused(self, user, row, action, reason=None, **values):
        before = (
            list(BouncedAddress.objects.filter(pk=row.pk).values()),
            list(ContactEmail.objects.order_by("pk").values()),
        )
        with self.assertRaises(ActionRefused) as raised:
            apply(user, row, action, **values)
        if reason is not None:
            self.assertIn(reason, str(raised.exception))
        after = (
            list(BouncedAddress.objects.filter(pk=row.pk).values()),
            list(ContactEmail.objects.order_by("pk").values()),
        )
        self.assertEqual(before, after, "a refused action changed something")
        return raised.exception


class QueueStateTests(ActionTestCase):
    def test_dismiss_needs_a_reason_and_reopen_reverses_it(self):
        row = make_row("q@example.org")
        self.assert_refused(self.mail_only, row, Action.DISMISS, "reason")

        apply(self.mail_only, row, Action.DISMISS, note="Typo in a manual list")

        row.refresh_from_db()
        self.assertEqual(
            (row.status, row.reviewed_by, row.review_note), (Status.DISMISSED, self.mail_only, "Typo in a manual list")
        )
        entry = BouncedAddressAction.objects.get(action=Action.DISMISS)
        self.assertEqual(
            (entry.actor, entry.address, entry.note), (self.mail_only, "q@example.org", "Typo in a manual list")
        )
        self.assertIn("Bounced addresses: dismissed q@example.org", history(row)[0])
        self.assert_refused(self.mail_only, row, Action.DISMISS, "Only an open address")

        apply(self.mail_only, row, Action.REOPEN)

        row.refresh_from_db()
        self.assertEqual(row.status, Status.OPEN)
        self.assert_refused(self.mail_only, row, Action.REOPEN, "already open")

    def test_a_changed_address_refuses_the_confirmation_it_showed(self):
        member = make_person("stale@example.org")
        row = make_row("stale@example.org")
        seen = fingerprint(load_target(row))
        ContactEmail.objects.filter(member=member).update(subscribe=False)  # someone edits the member meanwhile

        with self.assertRaises(StaleConfirmation):
            apply_action(request_for(self.master), row.pk, Action.MARK_UNDELIVERABLE, seen=seen, values={})

        row.refresh_from_db()
        self.assertIsNone(row.suppressed_at)
        self.assertFalse(BouncedAddressAction.objects.exists())

    def test_an_unknown_action_is_refused(self):
        row = make_row("u@example.org")

        with self.assertRaises(ActionRefused):
            apply(self.master, row, "explode")


class SuppressionTests(ActionTestCase):
    def test_an_address_of_no_contact_is_suppressed_by_mail_staff_and_cleared_again(self):
        row = make_row("list@example.org")
        manual = EmailCampaign.objects.create(
            name="M", subject="M", body="x", audience_type="manual", manual_emails="list@example.org"
        )
        self.assert_refused(self.mail_only, row, Action.MARK_UNDELIVERABLE, "use Suppress address")

        apply(self.mail_only, row, Action.SUPPRESS, note="Old manual list")

        row.refresh_from_db()
        self.assertEqual(
            (row.suppression, row.suppressed_by, row.status), ("suppressed", self.mail_only, Status.RESOLVED)
        )
        self.assertEqual(row.suggestion, "")
        self.assertEqual(list(get_recipients(manual)), [])
        self.assertIn("suppressed list@example.org", history(row)[0])

        apply(self.mail_only, row, Action.CLEAR_SUPPRESSION)

        row.refresh_from_db()
        self.assertEqual((row.suppressed_at, row.suppression, row.status), (None, "", Status.OPEN))
        self.assertEqual([item["email"] for item in get_recipients(manual)], ["list@example.org"])

    def test_marking_a_members_address_undeliverable_needs_the_members_app(self):
        member = make_person("member@example.org")
        row = make_row("member@example.org")
        self.assert_refused(self.mail_only, row, Action.MARK_UNDELIVERABLE, NEEDS_AUTHN)
        self.assert_refused(self.mail_authn, row, Action.SUPPRESS, "use Mark undeliverable")

        apply(self.mail_authn, row, Action.MARK_UNDELIVERABLE)

        row.refresh_from_db()
        self.assertEqual((row.suppression, row.role), ("undeliverable", Role.PRIMARY))
        self.assertIn("marked undeliverable member@example.org (hard bounce 5.1.1, 1 report)", history(member)[0])
        entry = BouncedAddressAction.objects.get(action=Action.MARK_UNDELIVERABLE)
        self.assertEqual((entry.member, entry.member_ref, entry.role_before), (member, member.pk, Role.PRIMARY))
        self.assert_refused(self.mail_authn, row, Action.MARK_UNDELIVERABLE, "already")
        self.assert_refused(self.mail_only, row, Action.CLEAR_SUPPRESSION, NEEDS_AUTHN)

    def test_only_an_i2g_master_changes_a_staff_account(self):
        make_person("boss@example.org", is_staff=True)
        row = make_row("boss@example.org")

        self.assert_refused(self.mail_authn, row, Action.MARK_UNDELIVERABLE, PRIVILEGED)
        apply(self.master, row, Action.MARK_UNDELIVERABLE)

        row.refresh_from_db()
        self.assertIsNotNone(row.suppressed_at)

    def test_an_ambiguous_address_is_marked_for_every_owner_but_allows_no_contact_change(self):
        first = make_person("Twin@Example.org", first="Ann")
        second = make_person("twin@example.org", first="Bob")
        row = make_row("twin@example.org")

        for action in (
            Action.UNSUBSCRIBE,
            Action.DELETE_EMAIL,
            Action.REPLACE,
            Action.DEACTIVATE,
            Action.DELETE_ACCOUNT,
        ):
            with self.subTest(action=action):
                self.assert_refused(self.master, row, action, "several letter cases")
        apply(self.master, row, Action.MARK_UNDELIVERABLE)

        entry = BouncedAddressAction.objects.get(action=Action.MARK_UNDELIVERABLE)
        self.assertEqual(set(entry.details["members"]), {str(first.pk), str(second.pk)})
        self.assertTrue(history(first) and history(second))


class UnsubscribeTests(ActionTestCase):
    def test_only_this_address_is_unsubscribed(self):
        member = make_person("one@example.org")
        add_email(member, "two@example.org")
        row = make_row("one@example.org")

        apply(self.mail_authn, row, Action.UNSUBSCRIBE)

        flags = dict(ContactEmail.objects.filter(member=member).values_list("email_address", "subscribe"))
        self.assertEqual(flags, {"one@example.org": False, "two@example.org": True})
        self.assertIn("unsubscribed one@example.org", history(member)[0])
        self.assert_refused(self.mail_authn, row, Action.UNSUBSCRIBE, "already unsubscribed")


class MakePrimaryTests(ActionTestCase):
    def setUp(self):
        super().setUp()
        self.member = make_person("old@example.org")
        self.verified = add_email(self.member, "verified@example.org", email_type="other", verified=True)
        self.secondary = add_email(self.member, "second@example.org", email_type="secondary")
        self.row = make_row("old@example.org")

    def test_a_verified_address_becomes_primary_and_the_old_one_secondary(self):
        apply(self.mail_authn, self.row, Action.MAKE_PRIMARY, new_primary=str(self.verified.pk))

        types = dict(ContactEmail.objects.filter(member=self.member).values_list("email_address", "email_type"))
        self.assertEqual(
            types, {"verified@example.org": "primary", "old@example.org": "secondary", "second@example.org": "other"}
        )
        self.row.refresh_from_db()
        self.assertEqual((self.row.role, self.row.status), (Role.SECONDARY, Status.RESOLVED))
        self.assertIn("made verified@example.org the primary email instead of old@example.org", history(self.member)[0])

    def test_only_a_verified_address_of_the_member_may_be_picked(self):
        self.assert_refused(
            self.mail_authn, self.row, Action.MAKE_PRIMARY, "verified", new_primary=str(self.secondary.pk)
        )
        self.assert_refused(self.mail_authn, self.row, Action.MAKE_PRIMARY, "verified", new_primary="")

    def test_it_applies_only_to_a_primary_with_a_verified_alternative(self):
        other_row = make_row("second@example.org")
        self.assert_refused(self.mail_authn, other_row, Action.MAKE_PRIMARY, "Only for the member's primary")
        ContactEmail.objects.filter(pk=self.verified.pk).update(verified=False)
        self.assert_refused(self.mail_authn, self.row, Action.MAKE_PRIMARY, "no other verified")


@override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
class DeleteEmailTests(ActionTestCase):
    def test_a_secondary_address_is_deleted_after_typing_it(self):
        member = make_person("keep@example.org")
        add_email(member, "Gone@Example.org")
        row = make_row("gone@example.org")
        self.assert_refused(
            self.mail_authn, row, Action.DELETE_EMAIL, "Type Gone@Example.org", confirm="wrong@example.org"
        )

        apply(self.mail_authn, row, Action.DELETE_EMAIL, confirm="gone@example.org")

        self.assertFalse(ContactEmail.objects.filter(email_address__iexact="gone@example.org").exists())
        row.refresh_from_db()
        self.assertEqual((row.role, row.member_id, row.status), (Role.NONE, None, Status.RESOLVED))
        entry = BouncedAddressAction.objects.get(action=Action.DELETE_EMAIL)
        self.assertEqual(
            (entry.role_before, entry.role_after, entry.member_ref), (Role.SECONDARY, Role.NONE, member.pk)
        )
        self.assertIn("deleted the contact email Gone@Example.org", history(member)[0])

    @override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
    def test_the_typed_confirmation_follows_the_admin_setting(self):
        member = make_person("keep@example.org")
        add_email(member, "gone@example.org")

        apply(self.mail_authn, make_row("gone@example.org"), Action.DELETE_EMAIL)

        self.assertFalse(ContactEmail.objects.filter(email_address="gone@example.org").exists())

    def test_the_primary_is_deleted_only_with_a_chosen_verified_replacement(self):
        member = make_person("primary@example.org")
        replacement = add_email(member, "new@example.org", email_type="other", verified=True)
        row = make_row("primary@example.org")
        self.assert_refused(self.mail_authn, row, Action.DELETE_EMAIL, "new primary", confirm="primary@example.org")

        apply(self.mail_authn, row, Action.DELETE_EMAIL, confirm="primary@example.org", new_primary=str(replacement.pk))

        self.assertEqual(
            list(ContactEmail.objects.filter(member=member).values_list("email_address", "email_type")),
            [("new@example.org", "primary")],
        )
        entry = BouncedAddressAction.objects.get(action=Action.DELETE_EMAIL)
        self.assertEqual(entry.details, {"new_primary": "new@example.org"})

    def test_the_primary_without_a_verified_alternative_is_kept(self):
        member = make_person("primary@example.org")
        add_email(member, "unverified@example.org")

        self.assert_refused(
            self.master, make_row("primary@example.org"), Action.DELETE_EMAIL, "no other verified address"
        )

    def test_the_only_email_is_kept(self):
        make_person("only@example.org")

        self.assert_refused(self.master, make_row("only@example.org"), Action.DELETE_EMAIL, "only email address")

    def test_the_last_verified_sign_in_contact_is_kept_unless_a_phone_is_verified(self):
        member = make_person("primary@example.org", verified=False)
        add_email(member, "last@example.org", verified=True)
        row = make_row("last@example.org")
        self.assert_refused(self.master, row, Action.DELETE_EMAIL, "last verified sign-in contact")

        ContactPhone.objects.create(member=member, phone_number="2095550188", verified=True)
        apply(self.master, row, Action.DELETE_EMAIL, confirm="last@example.org")

        self.assertFalse(ContactEmail.objects.filter(email_address="last@example.org").exists())

    def test_an_unlinked_contact_is_deleted_only_by_an_i2g_master(self):
        ContactEmail.objects.create(member=None, email_address="orphan@example.org", email_type="other")
        row = make_row("orphan@example.org")
        self.assert_refused(self.mail_authn, row, Action.DELETE_EMAIL, "I2G Master")
        self.assert_refused(self.mail_only, row, Action.DELETE_EMAIL, NEEDS_AUTHN)

        apply(self.master, row, Action.DELETE_EMAIL, confirm="orphan@example.org")

        self.assertFalse(ContactEmail.objects.filter(email_address="orphan@example.org").exists())
        self.assertIn("deleted the contact email orphan@example.org", history(row)[0])

    def test_an_unlinked_contact_linked_meanwhile_is_not_reported_deleted(self):
        ContactEmail.objects.create(member=None, email_address="orphan@example.org", email_type="other")
        row = make_row("orphan@example.org")
        nothing_deleted = patch("apps.mail.services.email_monitoring.addresses.actions.ContactEmail")

        with nothing_deleted as contact_model:
            contact_model.objects.filter.return_value.delete.return_value = (0, {})
            with self.assertRaisesMessage(ActionRefused, "changed meanwhile"):
                apply(self.master, row, Action.DELETE_EMAIL, confirm="orphan@example.org")

        self.assertFalse(BouncedAddressAction.objects.filter(action=Action.DELETE_EMAIL).exists())
        self.assertEqual(history(row), [])

    def test_an_address_of_no_contact_has_nothing_to_delete(self):
        self.assert_refused(self.master, make_row("nobody@example.org"), Action.DELETE_EMAIL, "no contact email")

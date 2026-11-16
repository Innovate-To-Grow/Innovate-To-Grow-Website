from unittest.mock import patch

from django.test import override_settings

from apps.authn.models import ContactEmail, ContactPhone
from apps.mail.models import BouncedAddressAction
from apps.mail.services.email_monitoring.addresses.actions import ActionRefused
from apps.mail.services.email_monitoring.addresses.actions.targets import (
    NEEDS_AUTHN,
)
from apps.mail.tests.services.bounced_addresses.actions.test_actions import (
    Action,
    ActionTestCase,
    Role,
    Status,
    apply,
    history,
)

from ..helpers import add_email, make_person, make_row


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
        nothing_deleted = patch("apps.mail.services.email_monitoring.addresses.actions.handlers.ContactEmail")

        with nothing_deleted as contact_model:
            contact_model.objects.filter.return_value.delete.return_value = (0, {})
            with self.assertRaisesMessage(ActionRefused, "changed meanwhile"):
                apply(self.master, row, Action.DELETE_EMAIL, confirm="orphan@example.org")

        self.assertFalse(BouncedAddressAction.objects.filter(action=Action.DELETE_EMAIL).exists())
        self.assertEqual(history(row), [])

    def test_an_address_of_no_contact_has_nothing_to_delete(self):
        self.assert_refused(self.master, make_row("nobody@example.org"), Action.DELETE_EMAIL, "no contact email")

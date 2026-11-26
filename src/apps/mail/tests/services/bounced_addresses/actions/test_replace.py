from datetime import timedelta

from django.test import override_settings
from django.utils import timezone

from apps.authn.models import AdminInvitation, ContactEmail
from apps.mail.models import BouncedAddressAction
from apps.mail.tests.services.bounced_addresses.actions.test_actions_accounts import Action, Role, Status

from ..helpers import add_email, make_person, make_row
from .test_actions import ActionTestCase, apply, history


@override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
class ReplaceTests(ActionTestCase):
    def setUp(self):
        super().setUp()
        self.member = make_person("bounced@example.org")
        self.row = make_row("bounced@example.org")

    def types(self):
        return dict(ContactEmail.objects.filter(member=self.member).values_list("email_address", "email_type"))

    def test_a_new_secondary_is_added_and_the_old_address_marked_undeliverable(self):
        apply(
            self.actor,
            self.row,
            Action.REPLACE,
            new_address="New@Example.org",
            new_role="secondary",
            subscribe="1",
        )

        new = ContactEmail.objects.get(email_address="new@example.org")
        self.assertEqual(
            (new.member, new.email_type, new.verified, new.subscribe), (self.member, "secondary", False, True)
        )
        self.row.refresh_from_db()
        self.assertEqual(
            (self.row.suppression, self.row.status, self.row.role), ("undeliverable", Status.RESOLVED, Role.PRIMARY)
        )
        audit = BouncedAddressAction.objects.get(action=Action.REPLACE)
        self.assertEqual(audit.details["new_address"], "new@example.org")
        self.assertEqual(audit.details["old_address"], "marked undeliverable")
        self.assertIn("replaced bounced@example.org with new@example.org", history(self.member)[0])

    def test_a_verified_new_primary_replaces_a_deleted_old_primary(self):
        apply(
            self.actor,
            self.row,
            Action.REPLACE,
            new_address="fresh@example.org",
            new_role="primary",
            attest_verified="1",
            old_address="delete",
            confirm="bounced@example.org",
        )

        self.assertEqual(self.types(), {"fresh@example.org": "primary"})
        self.assertTrue(ContactEmail.objects.get(email_address="fresh@example.org").verified)
        self.row.refresh_from_db()
        self.assertEqual((self.row.role, self.row.suppressed_at), (Role.NONE, None))

    def test_a_deleted_secondary_frees_the_secondary_slot(self):
        add_email(self.member, "old-second@example.org", email_type="secondary", verified=False)
        row = make_row("old-second@example.org")

        apply(
            self.actor,
            row,
            Action.REPLACE,
            new_address="next@example.org",
            new_role="secondary",
            old_address="delete",
            confirm="old-second@example.org",
        )

        self.assertEqual(self.types(), {"bounced@example.org": "primary", "next@example.org": "secondary"})

    def test_the_inputs_are_checked(self):
        add_email(self.member, "taken-second@example.org", email_type="secondary")
        make_person("Someone@Example.org")
        cases = [
            ({"new_address": "not-an-address"}, "valid new email"),
            ({"new_address": "bounced@example.org"}, "bounced address itself"),
            ({"new_address": "SOMEONE@example.org"}, "already belongs"),
            ({"new_address": "n@example.org", "new_role": "boss"}, "Choose primary"),
            ({"new_address": "n@example.org", "new_role": "primary"}, "must be verified"),
            ({"new_address": "n@example.org", "new_role": "secondary"}, "already has a secondary"),
            ({"new_address": "n@example.org", "new_role": "other", "old_address": "delete"}, "make the new address"),
            (
                {
                    "new_address": "n@example.org",
                    "new_role": "primary",
                    "attest_verified": "1",
                    "old_address": "delete",
                },
                "Type bounced@example.org",
            ),
        ]
        for values, reason in cases:
            with self.subTest(values=values):
                self.assert_refused(self.actor, self.row, Action.REPLACE, reason, **values)

    def test_an_address_with_a_pending_admin_invitation_is_refused(self):
        AdminInvitation.objects.create(
            email="Invited@Example.org", token="t" * 40, expires_at=timezone.now() + timedelta(days=3)
        )
        values = {"new_address": "invited@example.org", "new_role": "primary", "attest_verified": "1"}

        self.assert_refused(self.admin_user, self.row, Action.REPLACE, "pending admin invitation", **values)

        AdminInvitation.objects.update(status=AdminInvitation.Status.ACCEPTED)
        apply(self.admin_user, self.row, Action.REPLACE, new_address="invited@example.org", new_role="other")
        self.assertTrue(ContactEmail.objects.filter(email_address="invited@example.org", member=self.member).exists())

    def test_an_admin_attests_a_new_primary_address_on_another_admins_account(self):
        row = make_row("mailstaff@example.org")
        values = {"new_address": "theirs@example.org", "new_role": "primary", "attest_verified": "1"}

        apply(self.actor, row, Action.REPLACE, **values)

        self.assertEqual(self.other_admin.get_primary_email(), "theirs@example.org")
        self.assertTrue(ContactEmail.objects.get(email_address="theirs@example.org").verified)

    def test_the_last_verified_contact_is_not_deleted_for_an_unverified_replacement(self):
        add_email(self.member, "spare@example.org", email_type="secondary", verified=False)
        ContactEmail.objects.filter(email_address="bounced@example.org").update(email_type="other")
        ContactEmail.objects.filter(email_address="spare@example.org").update(email_type="primary")
        row = self.row
        values = {
            "new_address": "n@example.org",
            "new_role": "other",
            "old_address": "delete",
            "confirm": "bounced@example.org",
        }

        self.assert_refused(self.actor, row, Action.REPLACE, "only verified recovery method", **values)

        self.assertFalse(ContactEmail.objects.filter(email_address="n@example.org").exists())

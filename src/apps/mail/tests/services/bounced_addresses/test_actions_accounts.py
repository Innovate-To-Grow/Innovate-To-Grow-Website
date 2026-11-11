"""Bounced-address actions on accounts (deactivate, delete) and Replace email."""

from django.contrib.admin.models import DELETION, LogEntry
from django.test import override_settings

from apps.authn.models import ContactEmail, Member
from apps.event.models import CheckIn, CheckInRecord, EventRegistration
from apps.event.tests.helpers import make_event, make_registration, make_ticket
from apps.mail.models import BouncedAddress, BouncedAddressAction, RecipientLog
from apps.mail.services.email_monitoring.addresses.actions import deletion_summary

from .helpers import add_email, make_campaign, make_person, make_row, request_for
from .test_actions import ActionTestCase, apply, history

Action = BouncedAddressAction.Action
Role = BouncedAddress.Role
Status = BouncedAddress.Status


class DeactivateTests(ActionTestCase):
    def test_deactivation_keeps_the_history_and_ends_an_unfinished_sign_up(self):
        member = make_person("leaver@example.org", registration_pending=False)
        Member.objects.filter(pk=member.pk).update(registration_pending=True)
        row = make_row("leaver@example.org")

        apply(self.mail_authn, row, Action.DEACTIVATE, note="Left the company")

        member.refresh_from_db()
        self.assertEqual((member.is_active, member.registration_pending), (False, False))
        self.assertIn("deactivated the account", history(member)[0])
        row.refresh_from_db()
        self.assertEqual((row.status, row.resolution), (Status.RESOLVED, Action.DEACTIVATE))
        self.assert_refused(self.mail_authn, row, Action.DEACTIVATE, "already inactive")

    def test_nobody_deactivates_their_own_account_and_staff_accounts_need_an_i2g_master(self):
        self.assert_refused(self.mail_authn, make_row("memberstaff@example.org"), Action.DEACTIVATE, "your own")
        make_person("colleague@example.org", is_staff=True)
        self.assert_refused(self.mail_authn, make_row("colleague@example.org"), Action.DEACTIVATE, "I2G Master")
        self.assert_refused(self.mail_only, make_row("plain@example.org"), Action.DEACTIVATE, "no contact email")


@override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
class DeleteAccountTests(ActionTestCase):
    def setUp(self):
        super().setUp()
        self.member = make_person("doomed@example.org", first="Dee")
        add_email(self.member, "doomed-alt@example.org")
        event = make_event()
        self.registration = make_registration(self.member, event, make_ticket(event))
        CheckInRecord.objects.create(
            check_in=CheckIn.objects.create(event=event, name="Door"), registration=self.registration
        )
        self.log = RecipientLog.objects.create(
            campaign=make_campaign(), member=self.member, email_address="doomed@example.org", status="sent"
        )
        self.row = make_row("doomed-alt@example.org")

    def test_the_summary_lists_what_the_cascade_deletes(self):
        summary = deletion_summary(request_for(self.master), self.member)

        counts = {str(name).lower(): count for name, count in summary["model_count"]}
        self.assertEqual(counts.get("event registrations"), 1)
        self.assertEqual(counts.get("check in records"), 1)
        self.assertEqual(counts.get("contact emails"), 2)
        self.assertEqual(summary["protected"], [])

    def test_the_typed_primary_address_is_required(self):
        self.assert_refused(
            self.master, self.row, Action.DELETE_ACCOUNT, "Type doomed@example.org", confirm="doomed-alt@example.org"
        )

        self.assertTrue(Member.objects.filter(pk=self.member.pk).exists())

    def test_the_account_and_its_registrations_go_while_campaign_records_and_the_audit_stay(self):
        member_pk = self.member.pk

        apply(self.master, self.row, Action.DELETE_ACCOUNT, confirm="DOOMED@example.org", note="Duplicate account")

        self.assertFalse(Member.objects.filter(pk=member_pk).exists())
        self.assertFalse(EventRegistration.objects.filter(pk=self.registration.pk).exists())
        self.assertFalse(CheckInRecord.objects.exists())
        self.log.refresh_from_db()
        self.assertIsNone(self.log.member_id)
        entry = LogEntry.objects.get(object_id=str(member_pk), action_flag=DELETION)
        self.assertIn("Bounced addresses: deleted the account", entry.change_message)
        self.assertEqual(entry.object_repr, "Dee Doe")
        audit = BouncedAddressAction.objects.get(action=Action.DELETE_ACCOUNT)
        self.assertEqual((audit.member, audit.member_ref, audit.note), (None, member_pk, "Duplicate account"))
        self.assertIn("Dee Doe", audit.member_name)
        self.row.refresh_from_db()
        self.assertEqual((self.row.role, self.row.member_id, self.row.status), (Role.NONE, None, Status.RESOLVED))

    def test_permissions_and_self_protection(self):
        self.assert_refused(self.mail_only, self.row, Action.DELETE_ACCOUNT, "Members (authn) app")
        self.assert_refused(self.mail_authn, make_row("memberstaff@example.org"), Action.DELETE_ACCOUNT, "your own")
        make_person("other-staff@example.org", is_staff=True)
        self.assert_refused(self.mail_authn, make_row("other-staff@example.org"), Action.DELETE_ACCOUNT, "I2G Master")

    def test_staff_with_the_members_app_may_delete_an_ordinary_account(self):
        apply(self.mail_authn, self.row, Action.DELETE_ACCOUNT, confirm="doomed@example.org")

        self.assertFalse(Member.objects.filter(pk=self.member.pk).exists())


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
            self.mail_authn,
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
            self.mail_authn,
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
            self.mail_authn,
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
                self.assert_refused(self.mail_authn, self.row, Action.REPLACE, reason, **values)

    def test_only_an_i2g_master_attests_an_address_on_a_staff_account(self):
        self_row = make_row("memberstaff@example.org")
        values = {"new_address": "mine@example.org", "new_role": "primary", "attest_verified": "1"}

        self.assert_refused(self.mail_authn, self_row, Action.REPLACE, "Only an I2G Master may mark", **values)

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

        self.assert_refused(self.mail_authn, row, Action.REPLACE, "only verified recovery method", **values)

        self.assertFalse(ContactEmail.objects.filter(email_address="n@example.org").exists())

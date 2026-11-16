"""Bounced-address actions on accounts (deactivate, delete) and Replace email."""

from django.contrib.admin.models import DELETION, LogEntry
from django.db.models.signals import post_save
from django.test import override_settings

from apps.authn.models import ContactEmail, Member
from apps.event.models import CheckIn, CheckInRecord, EventRegistration
from apps.event.tests.helpers import make_event, make_registration, make_ticket
from apps.mail.models import BouncedAddress, BouncedAddressAction, RecipientLog
from apps.mail.services.email_monitoring.addresses.actions import deletion_summary

from ..helpers import add_email, make_campaign, make_person, make_row, request_for
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


class SignalTests(ActionTestCase):
    """Deactivate, Unsubscribe and Replace save the member or the contact (not a queryset update), so the
    ``post_save`` receivers, such as the member Google Sheet sync, see the change."""

    def setUp(self):
        super().setUp()
        self.received = []

        def receiver(sender, instance, **_kwargs):
            self.received.append((sender.__name__, instance.pk))

        for model in (Member, ContactEmail):
            uid = f"bounced-test-{model.__name__}"
            post_save.connect(receiver, sender=model, dispatch_uid=uid, weak=False)
            self.addCleanup(post_save.disconnect, sender=model, dispatch_uid=uid)

    def saved(self, action, address, **values):
        self.received.clear()
        apply(self.master, make_row(address), action, **values)
        return list(self.received)

    def test_deactivating_saves_the_member(self):
        member = make_person("deact@example.org")

        self.assertIn(("Member", member.pk), self.saved(Action.DEACTIVATE, "deact@example.org"))

    def test_unsubscribing_saves_the_contact_email(self):
        make_person("unsub@example.org")
        contact = ContactEmail.objects.get(email_address="unsub@example.org")

        self.assertIn(("ContactEmail", contact.pk), self.saved(Action.UNSUBSCRIBE, "unsub@example.org"))

    def test_replacing_saves_the_new_contact_email_in_its_final_role(self):
        owner = make_person("old@example.org")
        add_email(owner, "old-second@example.org", email_type="secondary")

        received = self.saved(
            Action.REPLACE,
            "old-second@example.org",
            new_address="next@example.org",
            new_role="secondary",
            old_address="delete",
            confirm="old-second@example.org",
        )

        created = ContactEmail.objects.get(email_address="next@example.org")
        self.assertEqual(created.email_type, "secondary")
        self.assertEqual(received.count(("ContactEmail", created.pk)), 2)


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

    def test_only_an_i2g_master_deletes_an_account(self):
        # The hard delete also removes the member's records in apps the admin may not hold (registrations,
        # check-ins, admin history), so holding Mail and Members is not enough.
        for user in (self.mail_only, self.mail_authn):
            with self.subTest(user=user.admin_apps):
                self.assert_refused(
                    user,
                    self.row,
                    Action.DELETE_ACCOUNT,
                    "Only an I2G Master may delete an account",
                    confirm="doomed@example.org",
                )
        self.assertTrue(Member.objects.filter(pk=self.member.pk).exists())
        self.assertEqual(EventRegistration.objects.filter(member=self.member).count(), 1)

    def test_nobody_deletes_their_own_account(self):
        self.assert_refused(self.mail_authn, make_row("memberstaff@example.org"), Action.DELETE_ACCOUNT, "your own")
        self.assert_refused(self.master, make_row("admin@example.com"), Action.DELETE_ACCOUNT, "your own")

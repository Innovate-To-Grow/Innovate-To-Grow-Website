"""Bounced-address actions on queue state, suppression and contact emails: each effect, its audit row and history
line, the reversible ones reversed, and every guard."""

from django.contrib.admin.models import LogEntry
from django.core.cache import cache
from django.test import TestCase

from apps.authn.models import ContactEmail
from apps.event.tests.helpers import make_admin, make_superuser
from apps.mail.models import BouncedAddress, BouncedAddressAction, EmailCampaign
from apps.mail.services.audience import get_recipients
from apps.mail.services.email_monitoring.addresses.actions import ActionRefused, StaleConfirmation, apply_action
from apps.mail.services.email_monitoring.addresses.actions.targets import (
    NEEDS_AUTHN,
    PRIVILEGED,
    fingerprint,
    load_target,
)

from ..helpers import make_person, make_row, request_for

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
        self.assertIn(
            "marked undeliverable member@example.org (address does not exist 5.1.1, 1 report)", history(member)[0]
        )
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
